"""Boundary and recovery checks for the public productivity integrations.

All sessions and HTTP servers use throwaway directories from the shared fixtures.
No real player data or external generation providers are used.
"""
from datetime import date
import json
from unittest import mock

from engine.productivity.cinematics import CinematicRouter
from engine.session import GameSession
from tests import SandboxTestCase
from tests.test_server import ServerTestCase


class ProductivityRecoveryTests(SandboxTestCase):
    def test_committed_activity_recovers_reward_after_queue_interruption(self):
        payload = {"activity": "Walk", "minutes": 30, "request_id": "recover-walk"}
        with mock.patch.object(CinematicRouter, "queue_rewards", side_effect=RuntimeError("interrupted")):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                self.session.log_productivity("workout", payload)

        restarted = GameSession(self.paths)
        recovered = restarted.productivity_snapshot()
        self.assertEqual(recovered["game"]["productivity_xp"], 110)
        self.assertEqual(len(recovered["recent_activity"]), 1)
        self.assertEqual(len(recovered["cinematic_jobs"]), 1)
        retry = restarted.log_productivity("workout", payload)
        self.assertEqual(retry["activity"], recovered["recent_activity"][0])
        self.assertEqual(retry["snapshot"]["cinematic_jobs"], recovered["cinematic_jobs"])
        self.assertEqual(retry["snapshot"]["game"]["productivity_xp"], 110)

    def test_reconciliation_recovers_new_clears_without_changing_campaign_save(self):
        self.session.save.xp = 150
        self.session.save.cleared["L01"] = {"xp": 150, "attempts": 1, "seconds": 30}
        self.session.save.write()
        first = self.session.productivity_snapshot()["cinematic_jobs"]
        self.assertEqual(len(first), 1)

        self.session.save.xp = 320
        self.session.save.cleared["L02"] = {"xp": 170, "attempts": 2, "seconds": 40}
        self.session.save.write()
        original = self.paths.save_path.read_bytes()
        restarted = GameSession(self.paths)
        recovered = restarted.productivity_snapshot()
        self.assertEqual(len(recovered["cinematic_jobs"]), 2)
        self.assertEqual(recovered["cinematic_jobs"][-1], first[0])     # newest first
        self.assertEqual(recovered["game"]["campaign_xp"], 320)
        self.assertEqual(recovered["game"]["productivity_xp"], 0)
        self.assertEqual(restarted.productivity_snapshot()["cinematic_jobs"], recovered["cinematic_jobs"])
        self.assertEqual(self.paths.save_path.read_bytes(), original)

    def test_all_activity_kinds_and_habit_updates_survive_restart(self):
        self.session.save.xp = 123
        self.session.save.write()
        original = self.paths.save_path.read_bytes()
        events = (
            ("study", {"course": "Algebra 2", "minutes": 60, "on_date": "2026-01-01", "request_id": "s"}),
            ("workout", {"activity": "Squat", "minutes": 20, "sets": 3, "reps": 8,
                         "load_lbs": 95, "on_date": "2026-01-01", "request_id": "w"}),
            ("weight", {"weight_lbs": 190, "on_date": "2026-01-01", "request_id": "v"}),
        )
        activities = [self.session.log_productivity(kind, body)["activity"] for kind, body in events]
        for value in (6, 8):
            result = self.session.log_productivity("habit", {"habit_key": "sleep_hours", "value": value,
                                                            "on_date": "2026-01-01"})
            self.assertIsNone(result["activity"])
        restarted = GameSession(self.paths)
        for (kind, body), expected in zip(events, activities):
            self.assertEqual(restarted.log_productivity(kind, body)["activity"], expected)
        recovered = restarted.productivity_snapshot("2026-01-01")
        self.assertEqual(recovered["game"]["productivity_xp"], 150)
        self.assertEqual(recovered["study"]["today_minutes"], 60)
        self.assertEqual(recovered["fitness"]["today_workout_minutes"], 20)
        self.assertEqual(recovered["fitness"]["latest_weight_lbs"], 190)
        sleep = [habit for habit in recovered["habits"] if habit["habit_key"] == "sleep_hours"]
        self.assertEqual(len(sleep), 1)
        self.assertEqual(sleep[0]["value"], 8)
        self.assertEqual(self.paths.save_path.read_bytes(), original)
        self.assertEqual(restarted.snapshot()["profile"]["xp"], 123)

    def test_earliest_iso_calendar_day_logs_and_snapshots_successfully(self):
        day = date.min.isoformat()
        self.assertEqual(self.session.productivity_snapshot(day)["study"]["current_streak_days"], 0)
        result = self.session.log_productivity("study", {
            "course": "Algebra 2", "minutes": 360, "on_date": day, "request_id": "earliest-day"})
        # The write response always shows today; the backfilled day is read back explicitly.
        self.assertEqual(result["snapshot"]["date"], date.today().isoformat())
        self.assertEqual(result["snapshot"]["study"]["best_streak_days"], 1)
        self.assertEqual(result["snapshot"]["game"]["productivity_xp"], 460)
        backfilled = self.session.productivity_snapshot(day)
        self.assertEqual(backfilled["study"]["current_streak_days"], 1)
        self.assertEqual(backfilled["study"]["best_streak_days"], 1)

    def test_backfilled_weight_crossing_awards_once_despite_later_rebound(self):
        for weight, day, key in ((200, "2026-01-01", "baseline"),
                                 (180, "2026-01-03", "latest"),
                                 (169, "2026-01-02", "crossed")):
            self.session.log_productivity("weight", {
                "weight_lbs": weight, "on_date": day, "request_id": key})
        result = self.session.productivity_snapshot("2026-01-03")
        self.assertEqual(result["fitness"]["latest_weight_lbs"], 180)
        self.assertEqual(result["game"]["productivity_xp"], 250)
        self.assertEqual(len(result["cinematic_jobs"]), 1)
        restarted = GameSession(self.paths)
        retry = restarted.log_productivity("weight", {
            "weight_lbs": 169, "on_date": "2026-01-02", "request_id": "crossed"})
        self.assertEqual(retry["activity"]["xp_awarded"], 250)
        self.assertEqual(retry["snapshot"]["game"]["productivity_xp"], 250)
        self.assertEqual(retry["snapshot"]["cinematic_jobs"], result["cinematic_jobs"])


class ProductivityHttpEdgeTests(ServerTestCase):
    def test_wrong_field_types_do_not_log_or_award_xp(self):
        cases = (
            ("study", {"course": ["Algebra 2"], "minutes": 30}),
            ("study", {"course": "Algebra 2", "minutes": True}),
            ("study", {"course": "Algebra 2", "minutes": 30, "topic": None}),
            ("study", {"course": "Algebra 2", "minutes": 30, "request_id": {}}),
            ("study", {"course": "Algebra 2", "minutes": 30, "on_date": 20260101}),
            ("workout", {"activity": "Walk", "minutes": "30"}),
            ("workout", {"activity": "Squat", "minutes": 30, "sets": False}),
            ("workout", {"activity": "Squat", "minutes": 30, "reps": 1.5}),
            ("workout", {"activity": "Squat", "minutes": 30, "load_lbs": "95"}),
            ("workout", {"activity": "Walk", "minutes": 30, "distance_miles": []}),
            ("weight", {"weight_lbs": "170"}),
            ("weight", {"weight_lbs": None}),
            ("habit", {"habit_key": "sleep_hours", "value": True}),
            ("habit", {"habit_key": "sleep_hours", "value": 8, "note": []}),
            ("habit", {"habit_key": "study_minutes", "value": 360}),
        )
        for command, payload in cases:
            with self.subTest(command=command, payload=payload):
                response = self.request("POST", f"/api/productivity/{command}", payload)
                self.assertEqual(response.status, 400, response.text)
        result = self.request("GET", "/api/productivity").json()
        self.assertEqual(result["game"]["total_xp"], 0)
        self.assertEqual(result["recent_activity"], [])
        self.assertEqual(result["habits"], [])
        self.assertEqual(result["cinematic_jobs"], [])

    def test_unrepresentable_json_numbers_return_400_without_mutation(self):
        huge = 10 ** 400
        cases = (
            ("weight", {"weight_lbs": huge}),
            ("habit", {"habit_key": "sleep_hours", "value": huge}),
            ("workout", {"activity": "Squat", "minutes": 30, "load_lbs": huge}),
            ("workout", {"activity": "Walk", "minutes": 30, "distance_miles": huge}),
        )
        for command, payload in cases:
            with self.subTest(command=command, field=next(reversed(payload))):
                response = self.request("POST", f"/api/productivity/{command}", payload)
                self.assertEqual(response.status, 400, response.text)
        result = self.request("GET", "/api/productivity").json()
        self.assertEqual(result["recent_activity"], [])
        self.assertEqual(result["habits"], [])
        self.assertEqual(result["game"]["productivity_xp"], 0)

    def test_retry_key_conflicts_preserve_original_activity(self):
        body = {"activity": "Walk", "minutes": 30, "on_date": "2026-01-01", "request_id": "original"}
        first = self.request("POST", "/api/productivity/workout", body)
        self.assertEqual(first.status, 200)
        initial = self.request("GET", "/api/productivity").json()
        cases = (
            ("workout", dict(body, minutes=31)),
            ("workout", dict(body, on_date="2026-01-02")),
            ("workout", dict(body, note="different")),
            ("weight", {"weight_lbs": 190, "on_date": "2026-01-01", "request_id": "original"}),
        )
        for command, payload in cases:
            with self.subTest(command=command, payload=payload):
                self.assertEqual(self.request("POST", f"/api/productivity/{command}", payload).status, 400)
        self.assertEqual(self.request("GET", "/api/productivity").json(), initial)
        replay = self.request("POST", "/api/productivity/workout", body)
        self.assertEqual(replay.status, 200)
        self.assertEqual(replay.json()["activity"], first.json()["activity"])

    def test_reward_extraction_excludes_private_activity_data(self):
        note = "private-personal-training-note"
        response = self.request("POST", "/api/productivity/workout", {
            "activity": "private-activity-label", "minutes": 20, "note": note, "request_id": "private-retry-key"})
        self.assertEqual(response.status, 200)
        self.assertEqual(self.request("POST", "/api/productivity/weight", {"weight_lbs": 200}).status, 200)
        self.assertEqual(self.request("POST", "/api/productivity/weight", {"weight_lbs": 170}).status, 200)
        first = self.request("GET", "/api/productivity/rewards").json()
        second = self.request("GET", "/api/productivity/rewards").json()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        encoded = json.dumps(first)
        for private in (note, "private-activity-label", "private-retry-key", "weight_lbs", "Netrunner"):
            self.assertNotIn(private, encoded)
        self.assertEqual(len({job["request_id"] for job in first}), 2)

    def test_query_string_token_is_not_accepted_for_productivity_routes(self):
        for method, route, body in (("GET", "/api/productivity", None),
                                    ("GET", "/api/productivity/rewards", None),
                                    ("POST", "/api/productivity/weight", {"weight_lbs": 170})):
            with self.subTest(route=route):
                response = self.request(method, f"{route}?token={self.token}", body, token=None)
                self.assertEqual(response.status, 401)
