"""SQLite persistence for Neon Command. Python 3.11+, standard library only.

One Database can be shared by TUI workers. Writes use BEGIN IMMEDIATE and a
reentrant lock; separate processes coordinate through SQLite's busy timeout.
Services commit logs, XP and milestones in the same transaction.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from threading import RLock
import time
from typing import Iterator

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "productivity.sqlite3"
SCHEMA_VERSION = 1
XP_PER_LEVEL = 1000
SQLITE_TIMEOUT_SECONDS = 10

SCHEMA = """
CREATE TABLE players (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK(length(trim(name)) BETWEEN 1 AND 80),
    xp INTEGER NOT NULL DEFAULT 0 CHECK(xp >= 0),
    study_goal_minutes INTEGER NOT NULL DEFAULT 360 CHECK(study_goal_minutes BETWEEN 1 AND 1440),
    target_weight_lbs REAL NOT NULL DEFAULT 170 CHECK(target_weight_lbs > 0),
    created_at TEXT NOT NULL
);
CREATE TABLE xp_events (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount > 0),
    created_at TEXT NOT NULL,
    UNIQUE(player_id, source)
);
CREATE TRIGGER apply_xp AFTER INSERT ON xp_events BEGIN
    UPDATE players SET xp = xp + NEW.amount WHERE id = NEW.player_id;
END;
CREATE TABLE inventory (
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(player_id, item_key)
);
CREATE TABLE activity_logs (
    id TEXT PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    request_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('study', 'workout', 'weight')),
    log_date TEXT NOT NULL,
    details_json TEXT NOT NULL,
    xp_awarded INTEGER NOT NULL DEFAULT 0 CHECK(xp_awarded >= 0),
    created_at TEXT NOT NULL,
    UNIQUE(player_id, request_id)
);
CREATE INDEX activity_by_day ON activity_logs(player_id, log_date, kind);
CREATE TABLE study_sessions (
    log_id TEXT PRIMARY KEY REFERENCES activity_logs(id) ON DELETE CASCADE,
    course TEXT NOT NULL,
    minutes INTEGER NOT NULL CHECK(minutes BETWEEN 1 AND 1440),
    topic TEXT NOT NULL DEFAULT ''
);
CREATE TABLE fitness_logs (
    log_id TEXT PRIMARY KEY REFERENCES activity_logs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('workout', 'weight')),
    minutes INTEGER,
    weight_lbs REAL,
    CHECK((kind = 'workout' AND minutes IS NOT NULL AND minutes BETWEEN 1 AND 1440 AND weight_lbs IS NULL)
       OR (kind = 'weight' AND minutes IS NULL AND weight_lbs IS NOT NULL AND weight_lbs > 0))
);
CREATE TABLE habit_logs (
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    habit_key TEXT NOT NULL,
    log_date TEXT NOT NULL,
    value REAL NOT NULL CHECK(value >= 0),
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY(player_id, habit_key, log_date)
);
CREATE TABLE milestones (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    milestone_key TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('study','fitness','coding')),
    details_json TEXT NOT NULL,
    achieved_at TEXT NOT NULL,
    UNIQUE(player_id, milestone_key)
);
CREATE TABLE cinematic_jobs (
    id TEXT PRIMARY KEY,
    milestone_id INTEGER NOT NULL UNIQUE REFERENCES milestones(id) ON DELETE CASCADE,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def clean_text(value: str, field: str, maximum: int = 200, *, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value.strip()) > maximum or (not empty and not value.strip()):
        raise ValueError(f"{field} must be {'at most' if empty else '1 to'} {maximum} characters")
    return value.strip()


def positive_int(value: int, field: str, maximum: int = 1_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{field} must be an integer between 1 and {maximum}")
    return value


def finite_number(value: float, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f"{field} must be a finite {'positive' if positive else 'nonnegative'} number")
    return result


def json_text(value: dict) -> str:
    if not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def player_state(row: sqlite3.Row) -> dict:
    result = dict(row)
    result.update(level=result["xp"] // XP_PER_LEVEL + 1,
                  level_xp=result["xp"] % XP_PER_LEVEL,
                  xp_to_next_level=XP_PER_LEVEL - result["xp"] % XP_PER_LEVEL)
    return result


class Database:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH):
        self.path = str(path) if str(path) == ":memory:" else str(Path(path).expanduser().resolve())
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._closed = False
        self._conn = sqlite3.connect(self.path, timeout=SQLITE_TIMEOUT_SECONDS, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute(f"PRAGMA busy_timeout = {SQLITE_TIMEOUT_SECONDS * 1000}")
            self._enable_wal()
            self._migrate()
        except BaseException:
            self._conn.close()
            raise

    def _enable_wal(self) -> None:
        """Retry WAL initialization locks that can bypass SQLite's busy handler.

        Separate processes may open a new database simultaneously. Only SQLite
        BUSY/LOCKED errors are transient here; preserve other failures immediately.
        Do not start another attempt after the deadline. Each SQLite call also
        retains the connection's bounded busy timeout.
        """
        deadline = time.monotonic() + SQLITE_TIMEOUT_SECONDS
        delay = 0.01
        while True:
            try:
                self._conn.execute("PRAGMA journal_mode = WAL")
                return
            except sqlite3.OperationalError as exc:
                code = getattr(exc, "sqlite_errorcode", 0)
                if code & 0xFF not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                time.sleep(min(delay, remaining))
                if time.monotonic() >= deadline:
                    raise
                delay = min(delay * 2, 0.1)

    def _migrate(self) -> None:
        # Serialize version inspection as well as schema creation across processes.
        with self.transaction() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(f"Database schema {version} is newer than supported {SCHEMA_VERSION}")
            if version == 0:
                statement = ""
                for line in SCHEMA.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        conn.execute(statement)
                        statement = ""
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Atomic unit of work. Nested transactions are intentionally rejected."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Database is closed")
            if self._conn.in_transaction:
                raise RuntimeError("Use the existing transaction instead of nesting transactions")
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise

    @staticmethod
    def require_player(conn: sqlite3.Connection, player_id: int) -> sqlite3.Row:
        positive_int(player_id, "player_id", 2**63 - 1)
        row = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
        if row is None:
            raise LookupError(f"Player {player_id} does not exist")
        return row

    @staticmethod
    def award_xp_in(conn: sqlite3.Connection, player_id: int, amount: int, source: str) -> bool:
        """Insert once; the database trigger updates the cached player total."""
        positive_int(amount, "amount")
        source = clean_text(source, "source", 300)
        Database.require_player(conn, player_id)
        existing = conn.execute("SELECT amount FROM xp_events WHERE player_id=? AND source=?", (player_id, source)).fetchone()
        if existing is not None:
            if existing["amount"] != amount:
                raise ValueError("XP source already exists with a different amount")
            return False
        conn.execute("INSERT INTO xp_events(player_id,source,amount,created_at) VALUES (?,?,?,?)",
                     (player_id, source, amount, utc_now()))
        return True

    def create_player(self, name: str, *, study_goal_minutes: int = 360, target_weight_lbs: float = 170) -> dict:
        name = clean_text(name, "name", 80)
        positive_int(study_goal_minutes, "study_goal_minutes", 1440)
        weight = finite_number(target_weight_lbs, "target_weight_lbs", positive=True)
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM players WHERE name=?", (name,)).fetchone()
            if row is None:
                cursor = conn.execute("INSERT INTO players(name,study_goal_minutes,target_weight_lbs,created_at) VALUES (?,?,?,?)",
                                      (name, study_goal_minutes, weight, utc_now()))
                row = self.require_player(conn, cursor.lastrowid)
            return player_state(row)

    def get_player(self, player_id: int) -> dict:
        with self.transaction() as conn:
            return player_state(self.require_player(conn, player_id))

    def award_xp(self, player_id: int, amount: int, source: str) -> bool:
        with self.transaction() as conn:
            return self.award_xp_in(conn, player_id, amount, source)

    def add_item(self, player_id: int, item_key: str, quantity: int = 1, *, metadata: dict | None = None) -> None:
        item_key = clean_text(item_key, "item_key")
        positive_int(quantity, "quantity")
        encoded = json_text(metadata or {})
        with self.transaction() as conn:
            self.require_player(conn, player_id)
            conn.execute("""INSERT INTO inventory(player_id,item_key,quantity,metadata_json) VALUES (?,?,?,?)
                ON CONFLICT(player_id,item_key) DO UPDATE SET quantity=inventory.quantity+excluded.quantity""",
                         (player_id, item_key, quantity, encoded))

    def consume_item(self, player_id: int, item_key: str, quantity: int = 1) -> None:
        item_key = clean_text(item_key, "item_key")
        positive_int(quantity, "quantity")
        with self.transaction() as conn:
            self.require_player(conn, player_id)
            row = conn.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_key=?", (player_id, item_key)).fetchone()
            if row is None or row[0] < quantity:
                raise ValueError("Insufficient inventory")
            if row[0] == quantity:
                conn.execute("DELETE FROM inventory WHERE player_id=? AND item_key=?", (player_id, item_key))
            else:
                conn.execute("UPDATE inventory SET quantity=quantity-? WHERE player_id=? AND item_key=?", (quantity, player_id, item_key))

    def inventory(self, player_id: int) -> list[dict]:
        with self.transaction() as conn:
            self.require_player(conn, player_id)
            return [dict(item_key=row[0], quantity=row[1], metadata=json.loads(row[2])) for row in conn.execute(
                "SELECT item_key,quantity,metadata_json FROM inventory WHERE player_id=? ORDER BY item_key", (player_id,))]

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._conn.close()
                self._closed = True

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
