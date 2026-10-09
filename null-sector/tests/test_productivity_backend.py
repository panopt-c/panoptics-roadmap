from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from engine.productivity.cinematics import CinematicRouter
from engine.productivity.db import SCHEMA_VERSION, Database
from engine.productivity.tracker import COURSES, Tracker


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.db = Database(self.path)
        self.addCleanup(self.db.close)
        self.player = self.db.create_player("Netrunner")
        self.pid = self.player["id"]
        self.tracker = Tracker(self.db, self.pid)
        self.day = date(2026, 1, 10)

    def test_defaults_and_idempotent_player_creation(self):
        self.assertEqual(self.player["study_goal_minutes"], 360)
        self.assertEqual(self.player["target_weight_lbs"], 170)
        self.assertEqual(self.player["level"], 1)
        self.assertEqual(self.db.create_player("Netrunner")["id"], self.pid)

    def test_schema_and_foreign_keys(self):
        with self.db.transaction() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO inventory(player_id,item_key,quantity) VALUES (999,'x',1)")

    def test_persistence_after_reopen(self):
        self.tracker.log_study("Algebra 2", 120, on_date=self.day, request_id="persist")
        self.db.add_item(self.pid, "neural-chip", 2, metadata={"rarity": "rare"})
        self.db.close()
        with Database(self.path) as reopened:
            tracker = Tracker(reopened, self.pid)
            self.assertEqual(tracker.dashboard(self.day)["study"]["today_minutes"], 120)
            self.assertEqual(reopened.get_player(self.pid)["xp"], 120)
            self.assertEqual(reopened.inventory(self.pid)[0]["metadata"], {"rarity": "rare"})

    def test_xp_deduplication_and_level(self):
        self.assertTrue(self.db.award_xp(self.pid, 1250, "mission:one"))
        self.assertFalse(self.db.award_xp(self.pid, 1250, "mission:one"))
        state = self.db.get_player(self.pid)
        self.assertEqual((state["xp"], state["level"], state["level_xp"], state["xp_to_next_level"]), (1250, 2, 250, 750))
        with self.assertRaises(ValueError):
            self.db.award_xp(self.pid, 100, "mission:one")

    def test_inventory_cannot_go_negative(self):
        self.db.add_item(self.pid, "chip", 2)
        self.db.add_item(self.pid, "chip", 1)
        with self.assertRaises(ValueError):
            self.db.consume_item(self.pid, "chip", 4)
        self.assertEqual(self.db.inventory(self.pid)[0]["quantity"], 3)
        self.db.consume_item(self.pid, "chip", 2)
        self.db.consume_item(self.pid, "chip")
        self.assertEqual(self.db.inventory(self.pid), [])

    def test_transaction_rolls_back_log_xp_and_habits(self):
        with self.db.transaction() as conn:
            conn.execute("""CREATE TRIGGER reject_reward BEFORE INSERT ON milestones
                BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.tracker.log_study("Algebra 2", 360, on_date=self.day)
        dashboard = self.tracker.dashboard(self.day)
        self.assertEqual(dashboard["player"]["xp"], 0)
        self.assertEqual(dashboard["recent_activity"], [])
        self.assertEqual(dashboard["habits"], [])

    def test_six_hour_goal_across_courses_awards_bonus_once(self):
        self.tracker.log_study("Algebra 2", 180, on_date=self.day)
        self.tracker.log_study("Linear Algebra", 180, on_date=self.day)
        snapshot = self.tracker.dashboard(self.day)
        self.assertEqual(snapshot["study"]["progress"], 1)
        self.assertEqual(snapshot["player"]["xp"], 460)
        self.assertEqual(len(snapshot["milestones"]), 1)
        extra = self.tracker.log_study("Trigonometry", 60, on_date=self.day)
        self.assertEqual(extra["xp_awarded"], 60)
        self.assertEqual(self.db.get_player(self.pid)["xp"], 520)

    def test_study_submission_retry(self):
        first = self.tracker.log_study("Algebra 2", 360, on_date=self.day, request_id="same")
        again = self.tracker.log_study("Algebra 2", 360, on_date=self.day, request_id="same")
        self.assertEqual(first, again)
        self.assertEqual(self.db.get_player(self.pid)["xp"], 460)
        with self.assertRaises(ValueError):
            self.tracker.log_study("Algebra 2", 60, on_date=self.day, request_id="same")
        with self.assertRaises(ValueError):
            self.tracker.log_weight(190, on_date=self.day, request_id="same")

    def test_course_progress_and_partial_day(self):
        self.tracker.log_study("Calculus 1", 90, on_date=self.day)
        state = self.tracker.dashboard(self.day)["study"]
        self.assertEqual(state["progress"], 0.25)
        self.assertEqual(state["remaining_minutes"], 270)
        self.assertEqual(state["course_minutes"]["Calculus 1"], 90)
        self.assertEqual(set(state["course_minutes"]), set(COURSES))

    def test_calendar_streak_and_gap(self):
        for offset in (0, 1, 3):
            self.tracker.log_study("Algebra 2", 360, on_date=self.day + timedelta(days=offset))
        before = self.tracker.dashboard(self.day + timedelta(days=2))["study"]
        self.assertEqual(before["current_streak_days"], 2)
        self.assertEqual(before["best_streak_days"], 2)
        after = self.tracker.dashboard(self.day + timedelta(days=3))["study"]
        self.assertEqual(after["current_streak_days"], 1)
        self.assertEqual(after["best_streak_days"], 2)
        self.assertEqual(self.tracker.dashboard(self.day + timedelta(days=5))["study"]["current_streak_days"], 0)

    def test_workout_metrics_and_first_milestone(self):
        first = self.tracker.log_workout("Squats", 45, sets=3, reps=8, load_lbs=95, on_date=self.day, request_id="workout")
        self.assertEqual(first["details"]["load_lbs"], 95)
        self.assertEqual(first["xp_awarded"], 140)
        self.assertEqual(self.tracker.log_workout("Squats", 45, sets=3, reps=8, load_lbs=95, on_date=self.day, request_id="workout"), first)
        second = self.tracker.log_workout("Walk", 30, distance_miles=1.5, on_date=self.day)
        self.assertEqual(second["xp_awarded"], 60)
        self.assertEqual(self.tracker.dashboard(self.day)["fitness"]["today_workout_minutes"], 75)

    def test_weight_goal_loss_and_once_only_reward(self):
        self.tracker.log_weight(200, on_date=self.day)
        self.tracker.log_weight(185, on_date=self.day + timedelta(days=1))
        state = self.tracker.dashboard(self.day + timedelta(days=1))["fitness"]
        self.assertAlmostEqual(state["weight_progress"], 0.5)
        self.tracker.log_weight(169, on_date=self.day + timedelta(days=2), request_id="goal")
        self.tracker.log_weight(170, on_date=self.day + timedelta(days=3))
        self.assertEqual(self.db.get_player(self.pid)["xp"], 250)

    def test_weight_goal_gain_direction(self):
        self.tracker.log_weight(150, on_date=self.day)
        self.assertEqual(self.db.get_player(self.pid)["xp"], 0)
        self.tracker.log_weight(171, on_date=self.day + timedelta(days=1))
        self.assertEqual(self.db.get_player(self.pid)["xp"], 250)

    def test_backdated_weight_does_not_replace_latest(self):
        self.tracker.log_weight(180, on_date=self.day + timedelta(days=2))
        self.tracker.log_weight(200, on_date=self.day)
        state = self.tracker.dashboard(self.day + timedelta(days=2))["fitness"]
        self.assertEqual(state["baseline_weight_lbs"], 200)
        self.assertEqual(state["latest_weight_lbs"], 180)
        self.assertEqual(self.db.get_player(self.pid)["xp"], 0)

    def test_no_weight_returns_unknown_not_fabricated_measurement(self):
        state = self.tracker.dashboard(self.day)["fitness"]
        self.assertIsNone(state["latest_weight_lbs"])
        self.assertIsNone(state["weight_progress"])

    def test_habits_persist_and_upsert(self):
        self.tracker.set_habit("sleep_hours", 7, on_date=self.day)
        self.tracker.set_habit("sleep_hours", 8, on_date=self.day)
        self.assertEqual(self.tracker.dashboard(self.day)["habits"][0]["value"], 8)
        with self.assertRaises(ValueError):
            self.tracker.set_habit("study_minutes", 500, on_date=self.day)

    def test_validation_rejects_bad_numbers_and_unknown_courses(self):
        for invalid in (0, -1, True, 1.5, 1441, "60"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.tracker.log_study("Algebra 2", invalid, on_date=self.day)
        for invalid in (0, -1, True, float("nan"), float("inf"), "170"):
            with self.subTest(weight=invalid), self.assertRaises(ValueError):
                self.tracker.log_weight(invalid, on_date=self.day)
        with self.assertRaises(ValueError):
            self.tracker.log_study("Unknown", 60)
        with self.assertRaises(ValueError):
            self.tracker.log_workout("Squats", 30, reps=0)
        with self.assertRaises(ValueError):
            self.tracker.log_workout("Run", 30, distance_miles=float("nan"))

    def test_validation_rejects_bad_dates_and_day_overflow(self):
        for invalid in ("2026-02-30", "20260110", "2026-W02-6", date.today() + timedelta(days=1)):
            with self.subTest(day=invalid), self.assertRaises(ValueError):
                self.tracker.log_study("Algebra 2", 1, on_date=invalid)
        self.tracker.log_study("Algebra 2", 1440, on_date=self.day)
        with self.assertRaises(ValueError):
            self.tracker.log_study("Algebra 2", 1, on_date=self.day)

    def test_empty_retry_key_rejected(self):
        with self.assertRaises(ValueError):
            self.tracker.log_weight(170, request_id=" ")

    def test_parameterized_strings_and_json_snapshot(self):
        text = "'); DROP TABLE players; --"
        self.tracker.log_workout(text, 10, note="Unicode: \u03bb", on_date=self.day)
        self.assertIn("Unicode", json.dumps(self.tracker.dashboard(self.day)))
        self.assertEqual(self.db.get_player(self.pid)["name"], "Netrunner")

    def test_multiple_players_are_isolated(self):
        other = self.db.create_player("Other")["id"]
        self.tracker.log_study("Algebra 2", 360, on_date=self.day, request_id="shared")
        tracker = Tracker(self.db, other)
        tracker.log_study("Algebra 2", 10, on_date=self.day, request_id="shared")
        self.assertEqual(tracker.dashboard(self.day)["player"]["xp"], 10)
        self.assertEqual(tracker.dashboard(self.day)["milestones"], [])
        with self.assertRaises(LookupError):
            Tracker(self.db, 999)

    def test_concurrent_retry_across_connections(self):
        def write(_):
            with Database(self.path) as db:
                return Tracker(db, self.pid).log_study("Algebra 2", 360, on_date=self.day, request_id="concurrent")["id"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(write, range(8)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(self.db.get_player(self.pid)["xp"], 460)
        self.assertEqual(len(self.tracker.dashboard(self.day)["recent_activity"]), 1)

    def test_newer_schema_is_not_overwritten(self):
        with self.db.transaction() as conn:
            conn.execute("PRAGMA user_version = 999")
        with self.assertRaises(RuntimeError):
            Database(self.path)

    def test_nested_transaction_is_rejected_without_losing_outer_write(self):
        with self.db.transaction() as conn:
            self.db.award_xp_in(conn, self.pid, 10, "test")
            with self.assertRaises(RuntimeError):
                self.db.get_player(self.pid)
        self.assertEqual(self.db.get_player(self.pid)["xp"], 10)

    def test_cinematics_are_durable_deduplicated_and_omit_measurements(self):
        self.tracker.log_weight(170, on_date=self.day)
        router = CinematicRouter(self.db, self.pid)
        jobs = router.queue_rewards()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(router.queue_rewards(), [])
        self.assertEqual(router.jobs(), jobs)
        encoded = json.dumps(jobs)
        self.assertNotIn("weight_lbs", encoded)
        self.assertNotIn("Netrunner", encoded)
        self.db.close()
        with Database(self.path) as reopened:
            self.assertEqual(CinematicRouter(reopened, self.pid).jobs(), jobs)

    def test_cinematic_player_isolation(self):
        self.tracker.log_study("Algebra 2", 360, on_date=self.day)
        CinematicRouter(self.db, self.pid).queue_rewards()
        other = self.db.create_player("Other")["id"]
        self.assertEqual(CinematicRouter(self.db, other).jobs(), [])


if __name__ == "__main__":
    unittest.main()
