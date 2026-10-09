"""Regression tests for the backend review findings (save safety, campaign path, command center).

Every test runs in a throwaway sandbox (`Paths.rooted(tmp)`); the real save.json,
config.json and data/ folder are never touched. Cross-process behaviour is tested
with real child processes sharing the sandbox's save.json.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from engine import state as state_mod
from engine.productivity import tracker as tracker_mod
from engine.productivity.backend import CommandCenter
from engine.productivity.cli import main as cli_main
from engine.productivity.db import SCHEMA
from engine.server import json_bytes
from engine.session import GameSession, SessionError
from engine.state import Save, interprocess_lock
from engine.tui import Game
from tests import ROOT, SOLUTION, SandboxTestCase
from tests.test_server import ServerTestCase

BUGGY = SOLUTION.replace('scrap_from_crate = "12"', "scrap_from_crate = 12 +")


def run_child(code: str, root: Path, timeout: float = 60) -> subprocess.CompletedProcess:
    """Run `code` in a separate Python process with `paths` rooted in the sandbox."""
    prelude = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(ROOT)!r})
        from pathlib import Path
        from engine.state import Paths, Save
        from engine.session import GameSession
        paths = Paths.rooted(Path({str(root)!r}))
    """)
    env = {k: v for k, v in os.environ.items() if not k.startswith("HF_")}
    result = subprocess.run([sys.executable, "-c", prelude + textwrap.dedent(code)], capture_output=True,
                            text=True, timeout=timeout, env=env)
    if result.returncode != 0:
        raise AssertionError(f"child process failed:\n{result.stdout}\n{result.stderr}")
    return result


# ── campaign save safety ────────────────────────────────────
class CrossProcessSaveTests(SandboxTestCase):
    def write_mission(self, text: str) -> None:
        self.mission_file().parent.mkdir(parents=True, exist_ok=True)
        self.mission_file().write_text(text, encoding="utf-8")

    def test_terminal_clear_survives_a_stale_web_session(self):
        """The reviewer's repro: web hacks, terminal clears, web hacks again → the clear must survive."""
        web = self.session
        web.deploy("L01")
        self.assertFalse(web.attack("L01")["victory"])                       # starter crashes: attempt 1
        self.write_mission(SOLUTION)
        out = run_child("""
            result = GameSession(paths).attack("L01")
            print(result["victory"], result["state"]["profile"]["xp"])
        """, self.root)
        self.assertEqual(out.stdout.split(), ["True", "150"])
        profile = web.snapshot()["profile"]                                  # web adopts the terminal clear
        self.assertEqual((profile["callsign"], profile["xp"], profile["breaches"]), ("Nyx", 150, 1))
        self.write_mission(BUGGY)
        self.assertFalse(web.attack("L01")["victory"])
        on_disk = json.loads(self.paths.save_path.read_text(encoding="utf-8"))
        self.assertEqual((on_disk["xp"], on_disk["callsign"], list(on_disk["cleared"])), (150, "Nyx", ["L01"]))
        self.assertEqual(on_disk["attempts"]["L01"], 3)
        self.assertEqual(GameSession(self.paths).snapshot()["profile"]["xp"], 150)

    def test_web_clear_survives_a_stale_terminal_session(self):
        terminal = GameSession(self.paths)
        terminal.deploy("L01")
        self.write_mission(SOLUTION)
        self.assertTrue(self.session.attack("L01")["victory"])
        self.write_mission(BUGGY)
        self.assertFalse(terminal.attack("L01")["victory"])
        self.assertEqual(Save.load(self.paths.save_path).xp, 150)
        self.assertIn("L01", terminal.save.cleared)

    def test_racing_victories_in_two_sessions_pay_out_once(self):
        other = GameSession(self.paths)
        self.write_mission(SOLUTION)
        first = self.session.attack("L01")
        second = other.attack("L01")
        self.assertFalse(first["reward"]["replay"])
        self.assertTrue(second["reward"]["replay"])
        self.assertEqual(second["reward"]["gained"], 0)
        self.assertEqual(Save.load(self.paths.save_path).xp, 150)

    def test_concurrent_processes_never_lose_an_update(self):
        Save.load(self.paths.save_path).write()
        code = """
            save = Save.load(paths.save_path)
            for _ in range(25):
                save.record_attempt("L01")
        """
        procs = [subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(ROOT)!r})
            from pathlib import Path
            from engine.state import Paths, Save
            paths = Paths.rooted(Path({str(self.root)!r}))
        """) + textwrap.dedent(code)]) for _ in range(4)]
        for proc in procs:
            self.assertEqual(proc.wait(timeout=60), 0)
        self.assertEqual(Save.load(self.paths.save_path).attempts["L01"], 100)

    def test_grading_runs_without_the_save_lock(self):
        held = []

        def fake_hack(mission, missions_dir):
            def probe():
                with interprocess_lock(self.session.save.lock_path, timeout=0.5):
                    held.append(True)
            t = threading.Thread(target=probe)
            t.start()
            t.join()
            from engine.runner import hack
            return hack(mission, missions_dir)

        with mock.patch("engine.session.hack", fake_hack):
            self.session.attack("L01")
        self.assertEqual(held, [True])

    def test_tui_refreshes_before_drawing(self):
        game = Game(fast=True, session=self.session)
        self.write_mission(SOLUTION)
        GameSession(self.paths).attack("L01")
        game.sync()
        self.assertEqual((game.save.xp, game.save.callsign), (150, "Nyx"))

    def test_refresh_is_in_place_for_shared_references(self):
        renderer_save = self.session.cinema.save
        self.write_mission(SOLUTION)
        GameSession(self.paths).attack("L01")
        self.session.snapshot()
        self.assertIs(renderer_save, self.session.save)
        self.assertEqual(renderer_save.xp, 150)


class CampaignPathTests(SandboxTestCase):
    """deploy -> edit -> reset -> hack -> victory, through the session the web and the TUI share."""

    def write_mission(self, text: str) -> None:
        self.mission_file().parent.mkdir(parents=True, exist_ok=True)
        self.mission_file().write_text(text, encoding="utf-8")

    def test_victory_reward_lets_the_client_derive_the_profile_before_it(self):
        """The reward screen derives xp_before = state.xp - gained; that must hold on first clears."""
        self.write_mission(SOLUTION)
        result = self.session.attack("L01")
        reward = result["reward"]
        self.assertEqual(result["state"]["profile"]["xp"] - reward["gained"], 0)
        self.assertEqual(reward["rank_before"], "GHOST PROCESS")

    def test_reset_then_hack_restores_a_playable_starter(self):
        self.session.deploy("L01")
        self.write_mission(BUGGY)
        self.assertEqual(self.session.reset("L01")["source"], self.mission_file().read_text(encoding="utf-8"))
        result = self.session.attack("L01")
        self.assertFalse(result["victory"])
        self.assertEqual(result["attempt"], 1)
        self.write_mission(SOLUTION)
        self.assertTrue(self.session.attack("L01")["victory"])


class SaveFileTests(SandboxTestCase):
    def test_empty_save_does_not_stop_launch(self):
        self.paths.save_path.write_text("", encoding="utf-8")
        session = GameSession(self.paths)
        self.assertEqual(session.snapshot()["profile"]["xp"], 0)
        notices = session.take_notices()
        self.assertTrue(any("save.json could not be read" in n and "Starting a fresh save" in n for n in notices))
        self.assertTrue(any("(the file is empty)" in n for n in notices), notices)
        kept = list(self.root.glob("save.json.corrupt-*"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(encoding="utf-8"), "")

    def test_garbage_and_wrong_shapes(self):
        for text in ("{not json", "[1, 2]", "\udcff".encode("utf-8", "surrogateescape").decode("latin-1"), "[" * 100000):
            with self.subTest(text=text[:10]):
                self.paths.save_path.write_text(text, encoding="latin-1")
                session = GameSession(self.paths)
                self.assertEqual(session.snapshot()["profile"]["xp"], 0)
        self.paths.save_path.write_text(json.dumps({"callsign": "Nyx", "xp": "lots", "cleared": {"L01": 5}}))
        session = GameSession(self.paths)
        self.assertEqual((session.save.callsign, session.save.xp, session.save.cleared), ("Nyx", 0, {}))
        self.assertTrue(any("invalid values for xp, cleared" in n for n in session.take_notices()))

    def test_game_launch_survives_an_empty_save(self):
        """`python game.py` with an empty save.json reaches the server with a notice, not a traceback."""
        sandbox = self.root / "game"
        sandbox.mkdir()
        for name in ("game.py", "config.example.json"):
            (sandbox / name).write_bytes((ROOT / name).read_bytes())
        for folder in ("engine", "levels"):      # copies, so GAME_DIR resolves inside the sandbox
            shutil.copytree(ROOT / folder, sandbox / folder, ignore=shutil.ignore_patterns("__pycache__"))
        (sandbox / "save.json").write_text("", encoding="utf-8")
        script = textwrap.dedent(f"""
            import runpy, sys
            sys.argv = ["game.py", "--no-browser", "--port", "0"]
            sys.path.insert(0, {str(sandbox)!r})
            import engine.server as srv

            def serve(session, *args, on_ready=None, **kwargs):   # stand-in: report instead of serving
                print("PROFILE", session.snapshot()["profile"]["xp"])
                for notice in session.take_notices():
                    print("NOTICE", notice)

            srv.serve = serve
            runpy.run_path({str(sandbox / "game.py")!r}, run_name="__main__")
        """)
        env = {k: v for k, v in os.environ.items() if not k.startswith("HF_")}
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60,
                                env=env, cwd=sandbox)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("PROFILE 0", result.stdout)
        self.assertIn("NOTICE save.json could not be read", result.stdout)
        self.assertEqual(len(list(sandbox.glob("save.json.corrupt-*"))), 1)
        self.assertFalse((ROOT / "save.json.corrupt").exists())

    def test_damage_mid_session_writes_progress_back(self):
        self.mission_file().parent.mkdir(parents=True, exist_ok=True)
        self.mission_file().write_text(SOLUTION, encoding="utf-8")
        self.session.attack("L01")
        self.paths.save_path.write_text("{oops", encoding="utf-8")
        self.assertEqual(self.session.snapshot()["profile"]["xp"], 150)
        self.assertEqual(Save.load(self.paths.save_path).xp, 150)
        self.assertTrue(any("damaged on disk" in n for n in self.session.take_notices()))

    def test_writes_are_fsynced(self):
        calls = []
        real = os.fsync
        with mock.patch.object(state_mod.os, "fsync", side_effect=lambda fd: (calls.append(fd), real(fd))):
            self.session.deploy("L01")
        self.assertGreaterEqual(len(calls), 2 if os.name != "nt" else 1)    # the file, then its folder

    def test_unknown_keys_are_preserved(self):
        self.paths.save_path.write_text(json.dumps({"xp": 10, "credits": 42, "mastery": {"strings": 60}}))
        session = GameSession(self.paths)
        session.deploy("L01")
        data = json.loads(self.paths.save_path.read_text())
        self.assertEqual((data["credits"], data["mastery"], data["xp"]), (42, {"strings": 60}, 10))
        self.assertIn("L01", data["started_at"])

    def test_failed_transaction_rolls_back_memory(self):
        save = self.session.save
        with self.assertRaises(RuntimeError):
            with save.transaction():
                save.xp = 999
                raise RuntimeError("boom")
        self.assertEqual(save.xp, 0)
        self.session.deploy("L01")
        self.assertEqual(Save.load(self.paths.save_path).xp, 0)


class WatcherStateEventTests(ServerTestCase):
    def test_external_clear_is_pushed_as_state_event(self):
        stream = self.sse()
        stream.next("hello")
        self.mission_file().parent.mkdir(parents=True, exist_ok=True)
        self.mission_file().write_text(SOLUTION, encoding="utf-8")
        run_child('GameSession(paths).attack("L01")', self.root)
        # The child's attempt counter is saved before its clear, so an earlier `state` event
        # (xp 0, one more attempt) may arrive first; the clear must follow within the timeout.
        deadline = time.monotonic() + 10
        while True:
            _name, event = stream.next("state", timeout=max(0.1, deadline - time.monotonic()))
            if event["profile"]["xp"]:
                break
        self.assertEqual((event["profile"]["xp"], event["profile"]["callsign"]), (150, "Nyx"))
        self.assertEqual(self.request("GET", "/api/state").json()["profile"]["xp"], 150)

    def test_own_victory_is_not_published_twice(self):
        stream = self.sse()
        stream.next("hello")
        self.win()
        stream.next("state")
        time.sleep(1.0)
        with self.assertRaises(AssertionError):
            stream.next("state", timeout=0.5)


# ── malformed input over HTTP ───────────────────────────────
class MalformedInputTests(ServerTestCase):
    def post(self, path: str, body) -> tuple[int, dict]:
        resp = self.request("POST", path, body)
        return resp.status, resp.json()

    def test_parseable_but_unconvertible_json_is_400(self):
        huge = '{"course":"Algebra 2","minutes":' + "9" * 5000 + "}"
        deep = "[" * 100000 + "]" * 100000
        for body in (huge, deep):
            status, payload = self.post("/api/productivity/study", body)
            self.assertEqual((status, payload), (400, {"error": "body is not valid JSON"}))
        status, _ = self.post("/api/missions/L01/hack", None)
        self.assertEqual(status, 200)

    def test_unknown_and_missing_fields_get_clean_messages(self):
        base = {"course": "Algebra 2", "minutes": 10}
        cases = (({**base, "extra": 1}, "unknown field for study: extra"),
                 ({**base, "self": 1}, "unknown field for study: self"),
                 ({**base, "command": "x"}, "unknown field for study: command"),
                 ({"course": "Algebra 2"}, "missing required field for study: minutes"))
        for body, message in cases:
            status, payload = self.post("/api/productivity/study", body)
            self.assertEqual((status, payload["error"]), (400, message))
            self.assertNotIn("Tracker", payload["error"])
        self.assertEqual(self.request("GET", "/api/productivity").json()["recent_activity"], [])

    def test_lone_surrogate_is_rejected_and_never_poisons_reads(self):
        raw = '{"activity":"Run","minutes":5,"note":"felt great \\ud83d","request_id":"surr-1"}'
        status, payload = self.post("/api/productivity/workout", raw)
        self.assertEqual(status, 400)
        self.assertIn("not valid text", payload["error"])
        self.assertEqual(self.request("GET", "/api/productivity").status, 200)
        good = '{"activity":"Run","minutes":5,"note":"felt great \\ud83d\\ude00","request_id":"emoji"}'
        status, payload = self.post("/api/productivity/workout", good)
        self.assertEqual(status, 200)
        self.assertEqual(payload["activity"]["details"]["note"], "felt great \U0001F600")
        self.assertEqual(self.request("GET", "/api/productivity").status, 200)

    def test_mission_source_with_a_lone_surrogate_still_saves(self):
        self.request("POST", "/api/missions/L01/deploy")
        resp = self.request("PUT", "/api/missions/L01/source", '{"source":"x = \\"\\udce9\\"\\n"}')
        self.assertEqual(resp.status, 200)
        self.assertEqual(self.mission_file().read_text(encoding="utf-8"), 'x = "\ufffd"\n')
        self.assertEqual(self.request("GET", "/api/missions/L01").status, 200)

    def test_cli_argv_bytes_are_repaired_not_stored_as_surrogates(self):
        db = self.root / "data" / "productivity.sqlite3"
        with mock.patch("sys.stdout"):
            self.assertEqual(cli_main(["--db", str(db), "workout", "--activity", "Run", "--minutes", "10",
                                       "--note", "caf\udce9"]), 0)
        resp = self.request("GET", "/api/productivity")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.json()["recent_activity"][0]["details"]["note"], "caf�")

    def test_response_encoder_cannot_fail(self):
        body = json_bytes({"note": "caf\udce9", "ok": "é"})
        self.assertEqual(json.loads(body.decode("ascii")), {"note": "caf\udce9", "ok": "é"})
        self.assertEqual(json_bytes({"ok": "é"}), '{"ok":"é"}'.encode("utf-8"))


class SchemaRepairTests(SandboxTestCase):
    def test_v1_database_with_poisoned_rows_is_repaired_and_gets_retroactive_items(self):
        path = self.root / "data" / "productivity.sqlite3"
        path.parent.mkdir()
        # A genuine version-1 database, as the previous release created it.
        conn = sqlite3.connect(path, isolation_level=None)
        conn.executescript(SCHEMA + "\nPRAGMA user_version = 1;")
        conn.execute("INSERT INTO players(name,created_at) VALUES ('Netrunner','2026-01-01T00:00:00+00:00')")
        conn.execute("""INSERT INTO activity_logs(id,player_id,request_id,kind,log_date,details_json,created_at)
            VALUES ('a1',1,'r1','workout','2026-01-01',?, '2026-01-01T00:00:00+00:00')""",
                     ('{"activity":"Run","minutes":5,"note":"caf\\udce9"}',))
        conn.execute("INSERT INTO fitness_logs(log_id,kind,minutes) VALUES ('a1','workout',5)")
        conn.execute("""INSERT INTO milestones(player_id,milestone_key,title,category,details_json,achieved_at)
            VALUES (1,'first-workout','Training protocol activated','fitness','{}','2026-01-01T00:00:00+00:00')""")
        conn.close()
        snap = self.session.productivity_snapshot()
        json_bytes(snap).decode("utf-8")
        note = snap["recent_activity"][0]["details"]["note"]
        self.assertEqual(note, "caf�")
        json.dumps(snap, ensure_ascii=False).encode("utf-8")                # strict UTF-8 works again
        self.assertEqual([i["item_key"] for i in snap["inventory"]], ["training_wraps"])
        self.assertEqual(self.session.productivity_snapshot()["inventory"][0]["quantity"], 1)


# ── command center: dates, weight, idempotency, size, items, limits ─
class FakeDate(date):
    today_value = date(2026, 10, 6)

    @classmethod
    def today(cls):
        return cls.today_value


class CommandCenterTests(SandboxTestCase):
    def log(self, command: str, **payload) -> dict:
        return self.session.log_productivity(command, payload)

    def test_backfill_keeps_todays_dashboard(self):
        today = date.today()
        yesterday = (today - timedelta(days=1)).isoformat()
        self.log("study", course="Calculus 1", minutes=60)
        self.log("workout", activity="Run", minutes=30)
        result = self.log("study", course="Calculus 1", minutes=30, on_date=yesterday)
        snap = result["snapshot"]
        self.assertEqual(snap["date"], today.isoformat())
        self.assertEqual(snap["study"]["today_minutes"], 60)
        self.assertEqual(snap["fitness"]["today_workout_minutes"], 30)
        self.assertEqual(snap["study"]["total_minutes"], 90)
        self.assertEqual(len(snap["recent_activity"]), 3)
        self.assertEqual(result["activity"]["log_date"], yesterday)
        explicit_today = self.log("study", course="Calculus 1", minutes=5, on_date=today.isoformat())
        self.assertEqual(explicit_today["snapshot"]["study"]["today_minutes"], 65)

    def test_backfilled_weigh_in_cannot_flip_the_goal(self):
        """The reviewer's repro: 190 today, 192, then 165 dated in January → no goal, no XP."""
        self.log("weight", weight_lbs=190, request_id="w1")
        self.log("weight", weight_lbs=192, request_id="w2")
        old = self.log("weight", weight_lbs=165, on_date=f"{date.today().year}-01-01", request_id="w3")
        self.assertEqual(old["activity"]["xp_awarded"], 0)
        fitness = old["snapshot"]["fitness"]
        self.assertEqual((fitness["baseline_weight_lbs"], fitness["latest_weight_lbs"]), (190, 192))
        self.assertEqual(fitness["weight_progress"], 0.0)
        self.assertEqual(fitness["goal_direction"], "lose")
        self.assertEqual(old["snapshot"]["player"]["xp"], 0)
        self.assertEqual(old["snapshot"]["milestone_counts"]["fitness"], 0)
        history = [row["log_date"] for row in fitness["weight_history"]]
        self.assertEqual(history, sorted(history))
        reached = self.log("weight", weight_lbs=169.5, request_id="w4")
        self.assertEqual(reached["activity"]["xp_awarded"], 250)

    def test_weight_and_workout_limits(self):
        for value in (1e308, 17.5, 801, 0):
            with self.subTest(weight=value), self.assertRaises(SessionError) as caught:
                self.log("weight", weight_lbs=value)
            self.assertEqual(caught.exception.status, 400)
        for field, value in (("sets", 0), ("reps", 0), ("sets", 1001), ("reps", 10001),
                             ("load_lbs", 2001), ("distance_miles", 501), ("load_lbs", -1)):
            with self.subTest(field=field, value=value), self.assertRaises(SessionError) as caught:
                self.log("workout", activity="Run", minutes=30, **{field: value})
            self.assertEqual(caught.exception.status, 400)
        with self.assertRaisesRegex(SessionError, "leave it empty"):
            self.log("workout", activity="Run", minutes=30, sets=0)
        ok = self.log("workout", activity="Squat", minutes=30, sets=1000, reps=10000, load_lbs=0, distance_miles=500)
        self.assertEqual(ok["activity"]["details"]["sets"], 1000)
        self.assertEqual(ok["snapshot"]["limits"]["sets"], [1, 1000])

    def test_retry_after_midnight_without_on_date_returns_the_original(self):
        with mock.patch.object(tracker_mod, "date", FakeDate):
            FakeDate.today_value = date(2026, 10, 6)
            first = self.log("study", course="Calculus 1", minutes=45, request_id="late-night-1")
            FakeDate.today_value = date(2026, 10, 7)
            retry = self.log("study", course="Calculus 1", minutes=45, request_id="late-night-1")
            self.assertEqual(retry["activity"], first["activity"])
            self.assertEqual(retry["snapshot"]["player"]["xp"], 45)
            with self.assertRaises(SessionError):          # an explicit, different day is still a conflict
                self.log("study", course="Calculus 1", minutes=45, on_date="2026-10-07", request_id="late-night-1")
            with self.assertRaises(SessionError):          # so is a different payload
                self.log("study", course="Calculus 1", minutes=50, request_id="late-night-1")

    def test_snapshot_payload_is_capped(self):
        with CommandCenter(self.root / "data" / "productivity.sqlite3") as backend:
            start = date.today() - timedelta(days=100)
            for offset in range(45):
                backend.tracker.log_study("Algebra 2", 360, on_date=start + timedelta(days=offset * 2))
        snap = self.session.productivity_snapshot()
        self.assertEqual(len(snap["milestones"]), 20)
        self.assertEqual(snap["milestone_counts"], {"study": 45, "fitness": 0, "coding": 0, "total": 45})
        ids = [m["id"] for m in snap["milestones"]]
        self.assertEqual(ids, sorted(ids, reverse=True))                    # newest first
        self.assertEqual(len(snap["cinematic_jobs"]), 20)
        self.assertEqual(snap["cinematic_job_count"], 45)
        self.assertEqual(snap["cinematic_jobs"][0]["reward"]["milestone_id"], ids[0])
        self.assertEqual(len(self.session.productivity_rewards()), 45)
        self.assertLess(len(json.dumps(snap)), 40_000)

    def test_milestones_drop_armory_items_exactly_once(self):
        today = date.today()
        days = [(today - timedelta(days=n)).isoformat() for n in (2, 1, 0)]
        result = None
        for day in days:
            result = self.log("study", course="Precalculus", minutes=360, on_date=day, request_id=f"goal-{day}")
        granted = [item["item_key"] for item in result["items_granted"]]
        self.assertIn("focus_chip", granted)
        self.assertIn("overclock_module", granted)                         # three-day streak
        workout = self.log("workout", activity="Run", minutes=20)
        self.assertEqual([i["item_key"] for i in workout["items_granted"]], ["training_wraps"])
        self.session.save.cleared["L01"] = {"xp": 150, "attempts": 1, "seconds": 9}
        self.session.save.write()
        snap = self.session.productivity_snapshot()
        inventory = {i["item_key"]: i for i in snap["inventory"]}
        self.assertEqual(inventory["focus_chip"]["quantity"], 3)
        self.assertEqual(inventory["overclock_module"]["metadata"]["rarity"], "rare")
        self.assertEqual(set(inventory), {"focus_chip", "overclock_module", "training_wraps", "breach_shard"})
        for item in inventory.values():
            self.assertTrue({"name", "rarity", "icon", "description"} <= set(item["metadata"]))
        again = self.session.productivity_snapshot()
        self.assertEqual(again["inventory"], snap["inventory"])           # no double drops
        retry = self.log("study", course="Precalculus", minutes=360, on_date=days[-1], request_id=f"goal-{days[-1]}")
        self.assertEqual(retry["items_granted"], [])
        self.assertEqual(retry["snapshot"]["player"]["xp"], snap["player"]["xp"])
        self.assertIn("3-day study streak", [m["title"] for m in snap["milestones"]])

    def test_sqlite_work_does_not_hold_the_session_lock(self):
        self.session.productivity_snapshot()                                 # create the database
        blocker = sqlite3.connect(self.root / "data" / "productivity.sqlite3", isolation_level=None)
        blocker.execute("BEGIN IMMEDIATE")
        outcome = {}

        def slow():
            try:
                self.session.log_productivity("study", {"course": "Algebra 2", "minutes": 5})
            except SessionError as exc:
                outcome["error"] = exc

        with mock.patch("engine.productivity.db.SQLITE_TIMEOUT_SECONDS", 1.5):
            worker = threading.Thread(target=slow)
            worker.start()
            time.sleep(0.3)
            started = time.monotonic()
            self.session.snapshot()
            self.session.mission("L01")
            self.assertLess(time.monotonic() - started, 0.5)
            worker.join(timeout=10)
        blocker.rollback()
        blocker.close()
        self.assertEqual(outcome["error"].status, 503)
        self.assertIn("busy", outcome["error"].message)
