import io
import json
from unittest import mock

from rich.console import Console

from engine.productivity.tui import render_dashboard, show_command_center
from engine.session import GameSession, SessionError
from tests import SandboxTestCase
from tests.test_server import ServerTestCase


class ProductivitySessionTests(SandboxTestCase):
    def test_campaign_and_productivity_awards_are_counted_once(self):
        self.session.save.xp = 150
        self.session.save.cleared["L01"] = {"xp": 150, "attempts": 1, "seconds": 30}
        self.session.save.write()
        original_save = self.paths.save_path.read_bytes()
        request = dict(course="Algebra 2", minutes=360, request_id="daily")
        result = self.session.log_productivity("study", request)
        self.assertEqual(result["snapshot"]["game"], {
            "callsign": "", "campaign_xp": 150, "productivity_xp": 460, "total_xp": 610})
        self.assertEqual(self.paths.save_path.read_bytes(), original_save)
        self.assertEqual(len(result["snapshot"]["cinematic_jobs"]), 2)
        self.session.log_productivity("study", request)
        restarted = GameSession(self.paths)
        self.assertEqual(restarted.productivity_snapshot()["game"]["total_xp"], 610)
        self.assertEqual(len(restarted.productivity_snapshot()["cinematic_jobs"]), 2)
        self.assertEqual(restarted.snapshot()["profile"]["xp"], 150)

    def test_bad_command_and_payload_are_session_errors(self):
        for command, payload in (("delete", {}), ("study", {}), ("weight", {"weight_lbs": True}),
                                 ("study", {"course": "Algebra 2", "minutes": 60, "unexpected": 1})):
            with self.subTest(command=command), self.assertRaises(SessionError) as error:
                self.session.log_productivity(command, payload)
            self.assertEqual(error.exception.status, 400)

    def test_existing_rich_tui_can_log_and_display_progress(self):
        output = io.StringIO()
        console = Console(file=output, width=120, color_system=None)
        with mock.patch.object(console, "input", side_effect=["s", "1", "90", "Quadratics", "b"]):
            show_command_center(console, self.session)
        state = self.session.productivity_snapshot()
        self.assertEqual(state["study"]["today_minutes"], 90)
        self.assertIn("90 / 360 min", output.getvalue())
        self.assertIn("No measurement", output.getvalue())
        console.print(render_dashboard(state))


class ProductivityApiTests(ServerTestCase):
    def test_productivity_routes_require_existing_token(self):
        self.assertEqual(self.request("GET", "/api/productivity", token=None).status, 401)
        self.assertEqual(self.request("POST", "/api/productivity/study", {}, token="bad").status, 403)
        self.assertEqual(self.request("GET", "/api/productivity/rewards", token=None).status, 401)

    def test_log_read_and_retry_through_http(self):
        body = {"course": "Linear Algebra", "minutes": 360, "request_id": "http-event"}
        first = self.request("POST", "/api/productivity/study", body)
        self.assertEqual(first.status, 200)
        self.assertEqual(first.json()["snapshot"]["study"]["progress"], 1)
        second = self.request("POST", "/api/productivity/study", body)
        self.assertEqual(first.json()["activity"], second.json()["activity"])
        state = self.request("GET", "/api/productivity").json()
        self.assertEqual(state["game"]["total_xp"], 460)
        rewards = self.request("GET", "/api/productivity/rewards").json()
        self.assertEqual(len(rewards), 1)
        self.assertEqual(rewards[0]["schema_version"], "neon.cinematic.v1")

    def test_invalid_payloads_return_400_without_mutation(self):
        for body in ([], {}, {"minutes": -1, "course": "Algebra 2"},
                     {"minutes": 20, "course": "Algebra 2", "extra": 4}):
            with self.subTest(body=body):
                self.assertEqual(self.request("POST", "/api/productivity/study", body).status, 400)
        self.assertEqual(self.request("GET", "/api/productivity").json()["game"]["total_xp"], 0)

    def test_success_broadcasts_productivity_event(self):
        stream = self.sse()
        stream.next("hello")
        self.request("POST", "/api/productivity/workout", {"activity": "Walk", "minutes": 30, "request_id": "walk"})
        _, data = stream.next("productivity")
        self.assertEqual(data["fitness"]["today_workout_minutes"], 30)
