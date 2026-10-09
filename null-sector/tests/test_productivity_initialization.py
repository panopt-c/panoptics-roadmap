"""Concurrent first-open and error handling checks for the SQLite backend."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest
from unittest import mock

from engine.productivity import db as db_module
from engine.productivity.db import Database
from engine.productivity.tracker import Tracker


WAL_PRAGMA = "PRAGMA journal_mode = WAL"


def lock_error(code):
    error = sqlite3.OperationalError("injected SQLite failure")
    error.sqlite_errorcode = code
    return error


class InitializationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="ns-init-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_simultaneous_first_open_preserves_every_write_and_one_schema(self):
        workers = 8
        real_connect = sqlite3.connect
        for round_number in range(3):
            with self.subTest(round=round_number):
                barrier = Barrier(workers, timeout=10)

                class SynchronizedConnection(sqlite3.Connection):
                    waited = False

                    def execute(self, sql, *args, **kwargs):
                        if sql == WAL_PRAGMA and not self.waited:
                            self.waited = True
                            barrier.wait()
                        return super().execute(sql, *args, **kwargs)

                def connect(*args, **kwargs):
                    return real_connect(*args, factory=SynchronizedConnection, **kwargs)

                path = self.root / f"fresh-{round_number}.sqlite3"

                def initialize(worker):
                    with Database(path) as database:
                        player = database.create_player("Netrunner")
                        activity = Tracker(database, player["id"]).log_study(
                            "Algebra 2", 10, on_date="2026-01-01", request_id=f"worker-{worker}")
                        return player["id"], activity["id"]

                with mock.patch.object(db_module.sqlite3, "connect", side_effect=connect):
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        results = list(pool.map(initialize, range(workers)))
                self.assertEqual(len({player_id for player_id, _ in results}), 1)
                self.assertEqual(len({activity_id for _, activity_id in results}), workers)
                with Database(path) as database:
                    state = Tracker(database, results[0][0]).dashboard("2026-01-01")
                    self.assertEqual(state["study"]["today_minutes"], workers * 10)
                    self.assertEqual(state["player"]["xp"], workers * 10)
                    self.assertEqual(len(state["recent_activity"]), workers)
                    with database.transaction() as connection:
                        self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                        self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                        self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 10000)

    def faulting_connection(self, errors):
        """Keep SQLite real, injecting failures only at the WAL boundary."""
        real_connect = sqlite3.connect
        connections = []

        class FaultingConnection(sqlite3.Connection):
            wal_attempts = 0

            def execute(self, sql, *args, **kwargs):
                if sql == WAL_PRAGMA:
                    self.wal_attempts += 1
                    if errors:
                        raise errors.pop(0)
                return super().execute(sql, *args, **kwargs)

        def connect(*args, **kwargs):
            connection = real_connect(*args, factory=FaultingConnection, **kwargs)
            connections.append(connection)
            return connection

        patcher = mock.patch.object(db_module.sqlite3, "connect", side_effect=connect)
        patcher.start()
        self.addCleanup(patcher.stop)
        return connections

    def test_busy_locked_and_extended_busy_errors_are_retried(self):
        errors = [lock_error(code) for code in
                  (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_BUSY | (2 << 8))]
        connections = self.faulting_connection(errors)
        with mock.patch.object(db_module.time, "sleep"):
            with Database(self.root / "transient.sqlite3") as database:
                player = database.create_player("Ready")
                self.assertEqual(database.get_player(player["id"])["name"], "Ready")
                self.assertEqual(connections[0].wal_attempts, 4)

    def test_non_lock_error_is_immediate_and_closes_connection(self):
        error = lock_error(sqlite3.SQLITE_READONLY)
        connections = self.faulting_connection([error])
        with mock.patch.object(db_module.time, "sleep") as sleep:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                Database(self.root / "readonly.sqlite3")
        self.assertIs(caught.exception, error)
        self.assertEqual(connections[0].wal_attempts, 1)
        sleep.assert_not_called()
        with self.assertRaises(sqlite3.ProgrammingError):
            connections[0].execute("SELECT 1")

    def test_retry_deadline_preserves_error_and_closes_connection(self):
        errors = [lock_error(sqlite3.SQLITE_BUSY) for _ in range(10)]
        connections = self.faulting_connection(errors.copy())
        with mock.patch.object(db_module.time, "monotonic", side_effect=[0, 0, 1, 9, 10]), \
                mock.patch.object(db_module.time, "sleep"):
            with self.assertRaises(sqlite3.OperationalError) as caught:
                Database(self.root / "locked.sqlite3")
        self.assertIs(caught.exception, errors[1])
        self.assertEqual(connections[0].wal_attempts, 2)
        with self.assertRaises(sqlite3.ProgrammingError):
            connections[0].execute("SELECT 1")
