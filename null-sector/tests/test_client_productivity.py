"""Browser tests for the COMMAND CENTER (client/js/ui/screens/productivity.js).

These drive the real client in headless Chromium against a mocked API (Playwright request
interception), so they need neither the productivity backend nor a running server:
static files come straight from client/, /api/state comes from a real GameSession sandbox,
and /api/productivity* is scripted per test (success, network drop, 5xx, 400, SSE push).

Skipped automatically when Playwright or a Chromium build is unavailable. Point
NS_CHROMIUM at a Chromium/Chrome executable to use a specific browser.

Run from the game folder:  python -m unittest tests.test_client_productivity -v
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import mimetypes
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from tests import ROOT

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - depends on the machine
    sync_playwright = None

CLIENT = ROOT / "client"
ORIGIN = "http://nullsector.test"
TOKEN = "test-token-123"
SANDBOX_CHROMIUM = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
# Fixture days are relative to the real calendar: the client compares snapshot days with the
# browser's local "today" (the same machine and clock as this test).
TODAY = date.today()


def day(offset: int = 0) -> str:
    """YYYY-MM-DD `offset` days before today (negative: in the future)."""
    return (TODAY - timedelta(days=offset)).isoformat()


UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

BASE_SNAPSHOT = {
    "date": day(0),
    "player": {"callsign": "Nyx"},
    "study": {
        "today_minutes": 120, "goal_minutes": 360, "remaining_minutes": 240, "progress": 1 / 3,
        "total_minutes": 2045, "current_streak_days": 4, "best_streak_days": 9,
        "course_minutes": {"Algebra 2": 900, "Trigonometry": 600, "Precalculus": 545},
    },
    "fitness": {
        "today_workout_minutes": 35, "target_weight_lbs": 170, "baseline_weight_lbs": 192.0,
        "latest_weight_lbs": 184.6, "weight_progress": 0.336,
        "weight_history": [
            {"log_date": day(7), "weight_lbs": 192.0},
            {"log_date": day(4), "weight_lbs": 188.2},
            {"log_date": day(0), "weight_lbs": 184.6},
        ],
    },
    "game": {"callsign": "Nyx", "campaign_xp": 150, "productivity_xp": 420, "total_xp": 570},
    "inventory": [
        {"name": "Focus Stim", "quantity": 2, "rarity": "rare", "description": "Earned for a 60-minute session"},
        {"name": "Kinetic Plating", "quantity": 1, "rarity": "epic"},
    ],
    "habits": [{"name": "study_360", "done_today": False, "streak": 4}, {"name": "workout", "done_today": True, "streak": 2}],
    "milestones": [{"title": "First 10 hours", "achieved": True}, {"title": "Precalculus cleared", "progress": 0.4}],
    "recent_activity": [
        {"id": 12, "kind": "study", "log_date": day(0), "details": {"course": "Precalculus", "minutes": 60, "topic": "Unit circle"},
         "xp_awarded": 60, "created_at": f"{day(0)}T10:00:00"},
        {"id": 11, "kind": "workout", "log_date": day(0), "details": {"activity": "Strength", "minutes": 35, "sets": 5, "reps": 5, "load_lbs": 135},
         "xp_awarded": 35, "created_at": f"{day(0)}T08:00:00"},
        {"id": 10, "kind": "weight", "log_date": day(0), "details": {"weight_lbs": 184.6}, "xp_awarded": 5, "created_at": f"{day(0)}T07:30:00"},
    ],
    "cinematic_jobs": [],
}

EMPTY_SNAPSHOT = {
    "date": day(0), "player": {}, "study": {"today_minutes": 0, "goal_minutes": 360, "remaining_minutes": 360, "progress": 0,
                                                  "total_minutes": 0, "course_minutes": {}, "current_streak_days": 0, "best_streak_days": 0},
    "fitness": {"today_workout_minutes": 0, "target_weight_lbs": 170, "baseline_weight_lbs": None, "latest_weight_lbs": None,
                "weight_progress": None, "weight_history": []},
    "game": {"callsign": "", "campaign_xp": 0, "productivity_xp": 0, "total_xp": 0},
    "inventory": [], "habits": [], "milestones": [], "recent_activity": [], "cinematic_jobs": [],
}


def _chromium_path() -> str | None:
    if os.environ.get("NS_CHROMIUM"):
        return os.environ["NS_CHROMIUM"]
    return str(SANDBOX_CHROMIUM) if SANDBOX_CHROMIUM.exists() else None


def _game_state() -> dict:
    from engine.session import GameSession
    from engine.state import Paths

    with tempfile.TemporaryDirectory() as tmp:
        return GameSession(Paths.rooted(tmp)).snapshot()


class MockBackend:
    """Scripted /api responses. `plans[kind]` is a queue of 'abort' | (status, body) consumed per POST."""

    def __init__(self, snapshot: dict, state: dict):
        self.snapshot = copy.deepcopy(snapshot)
        self.state = state
        self.posts: list[tuple[str, dict]] = []
        self.plans: dict[str, list] = {"study": [], "workout": [], "weight": []}
        self.get_plan: list = []          # queue for GET /api/productivity
        self.sse_snapshot: dict | None = None
        self.sse_cycle = False            # True: end each stream at once so the client keeps reconnecting
        self.legacy_backdated = False     # True: a backdated POST answers that day's dashboard (old server)
        self.gets = 0                     # GET /api/productivity count
        self.next_id = 100

    def handle(self, route, request):
        url = urlsplit(request.url)
        if url.hostname != "nullsector.test":
            if "fonts" in (url.hostname or ""):
                return route.fulfill(status=200, content_type="text/css", body="")
            return route.abort()
        path = url.path
        if path.startswith("/api/"):
            return self._api(route, request, path)
        return self._static(route, path)

    def _static(self, route, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        file = (CLIENT / rel).resolve()
        if CLIENT not in file.parents or not file.is_file():
            return route.fulfill(status=404, body="")
        body = file.read_bytes()
        if rel == "index.html":
            body = body.replace(b"{{NS_TOKEN}}", TOKEN.encode())
        ctype = "text/javascript" if file.suffix == ".js" else (mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        return route.fulfill(status=200, content_type=ctype, body=body)

    def _json(self, route, status, payload):
        return route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def _api(self, route, request, path):
        if request.headers.get("x-ns-token") != TOKEN and path != "/api/events":
            return self._json(route, 401, {"error": "missing token"})
        if path == "/api/events":
            if self.sse_snapshot is not None:
                snap, self.sse_snapshot = self.sse_snapshot, None
                body = "event: hello\ndata: {}\n\n" + f"event: productivity\ndata: {json.dumps(snap)}\n\n"
                return route.fulfill(status=200, content_type="text/event-stream", body=body)
            if self.sse_cycle:
                return route.fulfill(status=200, content_type="text/event-stream", body="event: hello\ndata: {}\n\n")
            return None  # leave the stream open forever: a quiet, healthy link
        if path == "/api/state":
            return self._json(route, 200, self.state)
        if path == "/api/productivity" and request.method == "GET":
            self.gets += 1
            if self.get_plan:
                step = self.get_plan.pop(0)
                if step == "abort":
                    return route.abort()
                return self._json(route, step[0], step[1])
            return self._json(route, 200, self.snapshot)
        match = re.fullmatch(r"/api/productivity/(study|workout|weight)", path)
        if match and request.method == "POST":
            kind = match.group(1)
            body = json.loads(request.post_data or "{}")
            self.posts.append((kind, body))
            plan = self.plans[kind]
            if plan:
                step = plan.pop(0)
                if step == "abort":
                    return route.abort()
                return self._json(route, step[0], step[1])
            return self._json(route, 200, self._record(kind, body))
        return self._json(route, 404, {"error": "not found"})

    def _record(self, kind, body):
        snap = self.snapshot
        xp = 0
        filed = body.get("on_date", snap["date"])
        today = filed == snap["date"]  # a backfill is filed under its own day: today's numbers stay
        details = {k: v for k, v in body.items() if k not in ("request_id", "on_date")}
        if kind == "study":
            xp = body["minutes"]
            study = snap["study"]
            study["total_minutes"] += body["minutes"]
            if today:
                study["today_minutes"] += body["minutes"]
                study["remaining_minutes"] = max(0, study["goal_minutes"] - study["today_minutes"])
                study["progress"] = min(1, study["today_minutes"] / study["goal_minutes"])
        elif kind == "workout":
            xp = body["minutes"]
            if today:
                snap["fitness"]["today_workout_minutes"] += body["minutes"]
        else:
            xp = 5
            snap["fitness"]["latest_weight_lbs"] = body["weight_lbs"]
            snap["fitness"]["weight_history"].append({"log_date": filed, "weight_lbs": body["weight_lbs"]})
        snap["game"]["productivity_xp"] += xp
        snap["game"]["total_xp"] += xp
        self.next_id += 1
        activity = {"id": self.next_id, "kind": kind, "log_date": filed, "details": details,
                    "xp_awarded": xp, "created_at": f"{day(0)}T12:00:00"}
        snap["recent_activity"].insert(0, activity)
        snap["recent_activity"].sort(key=lambda a: a["log_date"], reverse=True)  # newest day first, stable
        answer = copy.deepcopy(snap)
        if self.legacy_backdated and not today:
            # The pre-fix server answered (and broadcast) the dashboard *of the backdated day*.
            answer["date"] = filed
            answer["recent_activity"] = [a for a in answer["recent_activity"] if a["log_date"] <= filed]
            minutes = sum(a["details"].get("minutes", 0) for a in answer["recent_activity"]
                          if a["kind"] == "study" and a["log_date"] == filed)
            answer["study"].update(today_minutes=minutes, remaining_minutes=max(0, 360 - minutes), progress=minutes / 360)
            answer["fitness"]["today_workout_minutes"] = 0
        return {"activity": activity, "snapshot": answer}


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class CommandCenterBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The mock leaves the event stream open forever; Playwright logs its cancellation at
        # page close as an asyncio error. It is expected, so keep it out of the test output.
        logging.getLogger("asyncio").addFilter(
            lambda rec: not (rec.exc_info and isinstance(rec.exc_info[1], asyncio.CancelledError)))
        cls._pw = sync_playwright().start()
        try:
            cls.browser = cls._pw.chromium.launch(
                executable_path=_chromium_path(),
                # Software WebGL is slow headless; the CSS fallback skyline keeps these tests fast.
                args=["--disable-webgl", "--disable-3d-apis", "--autoplay-policy=no-user-gesture-required"],
            )
        except Exception as exc:  # pragma: no cover - depends on the machine
            cls._pw.stop()
            raise unittest.SkipTest(f"Chromium unavailable: {exc}")
        cls.state = _game_state()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()

    def setUp(self):
        self.backend = MockBackend(BASE_SNAPSHOT, self.state)
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 900})
        self.problems: list[str] = []
        self.page.on("pageerror", lambda e: self.problems.append(f"pageerror: {e}"))
        self.page.on("console", lambda m: self.problems.append(f"{m.type}: {m.text}")
                     if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
        self.page.route("**/*", self.backend.handle)

    def tearDown(self):
        self.page.unroute_all(behavior="ignoreErrors")  # drop the never-ending event stream quietly
        self.page.close()
        self.assertEqual(self.problems, [], "console errors / page errors")

    # ── helpers ────────────────────────────────────────────────────────────
    def open_hub(self):
        page = self.page
        page.goto(ORIGIN + "/")
        page.wait_for_function("window.__nsBooted === true", timeout=20000)
        page.wait_for_selector(".screen--boot", timeout=10000)
        page.wait_for_timeout(400)
        page.keyboard.press("Space")
        page.wait_for_selector(".screen--hub.is-active .hub-ops", timeout=15000)

    def open_command_center(self):
        self.open_hub()
        self.page.wait_for_function(
            "document.querySelector('.hub-ops__title')?.textContent.startsWith('Study')", timeout=10000)
        self.page.keyboard.press("o")
        self.page.wait_for_selector(".screen--productivity.is-active", timeout=10000)
        self.page.wait_for_function("!document.querySelector('.screen--productivity').classList.contains('is-loading')", timeout=10000)

    def text(self, selector):
        return " ".join((self.page.locator(selector).first.text_content() or "").split())

    def study_form(self):
        return self.page.locator("#ops-form-study")

    def wait_status(self, form, needle, timeout=10000):
        self.page.wait_for_function(
            "([sel, needle]) => document.querySelector(sel + ' .ops-form__status')?.textContent.includes(needle)",
            arg=[f"#ops-form-{form}", needle], timeout=timeout)

    # ── tests ──────────────────────────────────────────────────────────────
    def test_hub_entry_shows_daily_progress_and_opens_with_O(self):
        self.open_hub()
        self.page.wait_for_function("document.querySelector('.hub-ops__title').textContent === 'Study 120 / 360 min'")
        self.assertIn("Training 35 min", self.text(".hub-ops__sub"))
        self.assertIn("184.6 → 170 lb", self.text(".hub-ops__sub"))
        self.page.keyboard.press("o")
        self.page.wait_for_selector(".screen--productivity.is-active", timeout=10000)

    def test_dashboard_renders_snapshot(self):
        self.open_command_center()
        page = self.page
        ring = page.locator(".ops-ring")
        self.assertEqual(ring.get_attribute("aria-valuenow"), "120")
        self.assertEqual(ring.get_attribute("aria-valuemax"), "360")
        self.assertEqual(self.text(".ops-xp__chip--campaign .ops-xp__value"), "150")
        self.assertEqual(self.text(".ops-xp__chip--productivity .ops-xp__value"), "420")
        self.assertEqual(self.text(".ops-xp__chip--total .ops-xp__value"), "570")
        self.assertEqual(self.text(".ops-stat__value"), "4h")  # remaining 240 min
        self.assertEqual(page.locator(".ops-course").count(), 7)  # the whole curriculum, in order
        self.assertEqual(self.text(".ops-course .ops-course__name"), "Algebra 2")
        self.assertIn("14.6 lb to go", self.text(".ops-weight__togo"))
        self.assertIn("3 weigh-ins", page.locator(".ops-chart").get_attribute("aria-label"))
        self.assertIn("Focus Stim", self.text(".ops-items"))
        self.assertIn("×2", self.text(".ops-items"))
        self.assertIn("Precalculus", self.text(".ops-feed"))
        self.assertIn("+60 XP", self.text(".ops-feed"))
        self.assertIn("5×5", self.text(".ops-feed"))
        self.assertIn("study 360", self.text(".ops-habits").lower())

    def test_study_submit_matches_contract_and_updates_ui(self):
        self.open_command_center()
        page = self.page
        page.select_option("#ops-study-course", "Calculus 1")
        page.fill("#ops-study-minutes", "45")
        page.fill("#ops-study-topic", "Limits")
        page.keyboard.press("Control+Enter")
        self.wait_status("study", "+45 XP")
        self.assertEqual(len(self.backend.posts), 1)
        kind, body = self.backend.posts[0]
        self.assertEqual(kind, "study")
        # An empty Date field means today; the client pins today's date into the request.
        self.assertEqual(set(body), {"course", "minutes", "topic", "on_date", "request_id"})
        self.assertEqual(body["on_date"], day(0))
        self.assertEqual(body["course"], "Calculus 1")
        self.assertIs(type(body["minutes"]), int)
        self.assertEqual(body["minutes"], 45)
        self.assertRegex(body["request_id"], UUID)
        page.wait_for_function("document.querySelector('.ops-ring').getAttribute('aria-valuenow') === '165'")
        page.wait_for_function("document.querySelector('.ops-xp__chip--total .ops-xp__value').textContent === '615'", timeout=5000)
        self.assertEqual(page.input_value("#ops-study-minutes"), "")      # cleared after success
        self.assertEqual(page.input_value("#ops-study-course"), "Calculus 1")  # course kept
        self.assertIn("Limits", self.text(".ops-feed .ops-event"))

    def test_uncertain_failures_retry_with_the_same_request_id(self):
        self.backend.plans["study"] = ["abort", (503, {"error": "busy"})]
        self.open_command_center()
        self.page.fill("#ops-study-minutes", "30")
        self.page.click("#ops-form-study .ops-form__submit")
        self.wait_status("study", "+30 XP", timeout=15000)
        bodies = [b for k, b in self.backend.posts if k == "study"]
        self.assertEqual(len(bodies), 3)
        self.assertEqual(len({b["request_id"] for b in bodies}), 1, "every retry reuses one id")
        self.assertEqual(len({json.dumps(b, sort_keys=True) for b in bodies}), 1, "and the identical payload")
        self.assertEqual(bodies[0]["on_date"], day(0), "the day is pinned at the first submit, so a retry keeps it")

    def test_manual_retry_reuses_id_until_the_payload_changes(self):
        self.backend.plans["study"] = ["abort", "abort", "abort"]
        self.open_command_center()
        page = self.page
        page.fill("#ops-study-minutes", "25")
        page.click("#ops-form-study .ops-form__submit")
        self.wait_status("study", "Not confirmed", timeout=15000)
        first_id = self.backend.posts[-1][1]["request_id"]
        self.assertEqual(page.input_value("#ops-study-minutes"), "25")  # nothing lost
        self.backend.plans["study"] = ["abort", "abort", "abort"]
        page.click("#ops-form-study .ops-form__submit")
        self.wait_status("study", "Not confirmed", timeout=15000)
        self.assertEqual(self.backend.posts[-1][1]["request_id"], first_id, "same payload → same id")
        page.fill("#ops-study-minutes", "26")
        page.click("#ops-form-study .ops-form__submit")
        self.wait_status("study", "+26 XP", timeout=15000)
        self.assertNotEqual(self.backend.posts[-1][1]["request_id"], first_id, "changed payload → new id")

    def test_server_rejection_marks_the_field_and_settles_the_id(self):
        self.backend.plans["study"] = [(400, {"error": "minutes must be between 1 and 1440"})]
        self.open_command_center()
        page = self.page
        page.fill("#ops-study-minutes", "90")
        page.click("#ops-form-study .ops-form__submit")
        self.wait_status("study", "Rejected")
        self.assertEqual(len(self.backend.posts), 1, "a 400 is never retried automatically")
        self.assertEqual(page.get_attribute("#ops-study-minutes", "aria-invalid"), "true")
        self.assertIn("minutes must be", self.text("#ops-study-minutes-err"))
        rejected_id = self.backend.posts[0][1]["request_id"]
        page.click("#ops-form-study .ops-form__submit")
        self.wait_status("study", "+90 XP")
        self.assertNotEqual(self.backend.posts[-1][1]["request_id"], rejected_id)

    def test_client_validation_blocks_bad_input(self):
        self.open_command_center()
        page = self.page
        page.click("#ops-form-study .ops-form__submit")
        self.wait_status("study", "Fix the highlighted fields")
        self.assertIn("Minutes is required", self.text("#ops-study-minutes-err"))
        page.fill("#ops-study-minutes", "2000")
        page.click("#ops-form-study .ops-form__submit")
        self.assertIn("1–1440", self.text("#ops-study-minutes-err"))
        page.fill("#ops-study-minutes", "30")
        page.fill("#ops-study-date", day(-60))
        page.click("#ops-form-study .ops-form__submit")
        self.assertIn("Future dates", self.text("#ops-study-date-err"))
        page.click("#ops-tab-weight")
        page.fill("#ops-weight-lbs", "12")
        page.click("#ops-form-weight .ops-form__submit")
        self.assertIn("50–800", self.text("#ops-weight-lbs-err"))
        self.assertEqual(self.backend.posts, [], "invalid entries never reach the server")

    def test_workout_and_weight_payloads(self):
        self.open_command_center()
        page = self.page
        page.keyboard.press("2")
        self.assertEqual(page.get_attribute("#ops-tab-workout", "aria-selected"), "true")
        page.fill("#ops-workout-activity", "Run")
        page.fill("#ops-workout-minutes", "28")
        page.fill("#ops-workout-distance_miles", "3.1")
        page.fill("#ops-workout-date", day(1))
        page.click("#ops-form-workout .ops-form__submit")
        self.wait_status("workout", "+28 XP")
        kind, body = self.backend.posts[-1]
        self.assertEqual(kind, "workout")
        self.assertEqual(set(body), {"activity", "minutes", "distance_miles", "on_date", "request_id"})
        self.assertEqual(body["distance_miles"], 3.1)
        self.assertEqual(body["on_date"], day(1))
        page.evaluate("document.activeElement.blur()")  # leave the field so digit keys switch tabs
        page.keyboard.press("3")
        page.fill("#ops-weight-lbs", "183.2")
        page.keyboard.press("Control+Enter")
        self.wait_status("weight", "Weigh-in logged")
        kind, body = self.backend.posts[-1]
        self.assertEqual((kind, set(body)), ("weight", {"weight_lbs", "on_date", "request_id"}))
        self.assertEqual(body["on_date"], day(0))
        self.assertEqual(body["weight_lbs"], 183.2)
        self.page.wait_for_function("document.querySelector('.ops-chart').getAttribute('aria-label').includes('4 weigh-ins')")

    def test_loading_fault_and_retry(self):
        self.backend.get_plan = [(500, {"error": "database locked"}), (500, {"error": "database locked"})]
        self.open_hub()  # the hub's own fetch consumes the first failure
        self.page.wait_for_selector(".hub-ops.is-offline", timeout=10000)
        self.page.keyboard.press("o")
        self.page.wait_for_selector(".ops-fault:not([hidden])", timeout=10000)
        self.assertIn("database locked", self.text(".ops-fault__msg"))
        self.page.click(".ops-fault .btn--primary")
        self.page.wait_for_selector(".ops-fault[hidden]", state="attached", timeout=10000)
        self.page.wait_for_function("document.querySelector('.ops-ring').getAttribute('aria-valuenow') === '120'")

    def test_empty_states(self):
        self.backend.snapshot = copy.deepcopy(EMPTY_SNAPSHOT)
        self.open_command_center()
        self.assertIn("No weigh-ins yet", self.text(".ops-chart"))
        # Gear drops from milestones (tracker.py ITEM_DROPS): the copy names the reachable ones.
        self.assertIn("No gear yet", self.text(".ops-items"))
        self.assertIn("Milestones drop gear", self.text(".ops-items"))
        self.assertIn("first workout", self.text(".ops-items"))
        self.assertIn("clear a mission", self.text(".ops-items"))
        self.assertIn("No milestones", self.text(".ops-milestones"))
        self.assertIn("No activity yet", self.text(".ops-feed"))
        self.assertIn("Log a weigh-in", self.text(".ops-weight__togo"))
        self.assertEqual(self.page.locator(".ops-course.is-idle").count(), 7)

    def test_sse_productivity_event_refreshes_the_screen(self):
        self.backend.sse_cycle = True
        self.open_command_center()
        pushed = copy.deepcopy(BASE_SNAPSHOT)
        pushed["study"].update(today_minutes=300, remaining_minutes=60, progress=300 / 360)
        pushed["game"].update(productivity_xp=600, total_xp=750)
        self.backend.sse_snapshot = pushed  # delivered on the client's next reconnect
        self.page.wait_for_function("document.querySelector('.ops-ring').getAttribute('aria-valuenow') === '300'", timeout=20000)
        self.page.wait_for_function("document.querySelector('.ops-xp__chip--total .ops-xp__value').textContent === '750'", timeout=5000)

    # ── backfill / day handling (review finding: a backdated log switched the dashboard's day) ──
    def test_backfill_keeps_today_on_screen_and_files_the_entry_under_its_day(self):
        self.backend.legacy_backdated = True  # the old server answered with the backdated day's view
        self.open_command_center()
        page = self.page
        gets = self.backend.gets
        page.fill("#ops-study-minutes", "30")
        page.fill("#ops-study-date", day(1))
        page.click("#ops-form-study .ops-form__submit")
        self.wait_status("study", f"logged for {day(1)}")
        self.assertIn("+30 XP", self.text("#ops-form-study .ops-form__status"))
        _, body = self.backend.posts[-1]
        self.assertEqual(body["on_date"], day(1))
        # The backdated dashboard is never shown: a quiet GET brings today's back.
        page.wait_for_timeout(600)
        self.assertGreater(self.backend.gets, gets, "today's dashboard is re-fetched")
        self.assertIn(day(0), self.text(".ops-topbar__date"))
        self.assertEqual(page.get_attribute(".ops-ring", "aria-valuenow"), "120")
        self.assertIn("Training today", self.text(".ops-fitness"))
        self.assertEqual(self.text(".ops-fitness .ops-big"), "35")
        # Today's entries stay in the feed and the backfill is listed under its own date.
        feed = [" ".join(t.split()) for t in page.locator(".ops-event").all_inner_texts()]
        self.assertTrue(any("Precalculus" in row and day(0) in row for row in feed), feed)
        self.assertTrue(any("Algebra 2" in row and day(1) in row for row in feed), feed)
        # The Date field is back to empty (= today) and today is still allowed.
        self.assertEqual(page.input_value("#ops-study-date"), "")
        self.assertEqual(page.get_attribute("#ops-study-date", "max"), day(0))
        page.fill("#ops-study-minutes", "15")
        page.fill("#ops-study-date", day(0))
        page.click("#ops-form-study .ops-form__submit")
        self.wait_status("study", "+15 XP")
        self.assertEqual(self.text("#ops-study-date-err"), "")
        self.assertNotIn("logged for", self.text("#ops-form-study .ops-form__status"))
        page.wait_for_function("document.querySelector('.ops-ring').getAttribute('aria-valuenow') === '135'")

    def test_backdated_sse_push_is_ignored_and_today_is_refetched(self):
        self.backend.sse_cycle = True
        self.open_command_center()
        gets = self.backend.gets
        pushed = copy.deepcopy(BASE_SNAPSHOT)
        pushed["date"] = day(1)
        pushed["study"].update(today_minutes=30, remaining_minutes=330, progress=30 / 360)
        self.backend.sse_snapshot = pushed  # delivered on the client's next reconnect
        deadline = 20
        while self.backend.sse_snapshot is not None and deadline > 0:
            self.page.wait_for_timeout(500)
            deadline -= 1
        self.assertIsNone(self.backend.sse_snapshot, "the push was delivered")
        self.page.wait_for_timeout(800)
        self.assertGreater(self.backend.gets, gets, "a backdated push triggers a re-fetch")
        self.assertEqual(self.page.get_attribute(".ops-ring", "aria-valuenow"), "120")
        self.assertIn(day(0), self.text(".ops-topbar__date"))
        self.assertEqual(self.page.evaluate("window.__NS__.productivity.date"), day(0), "the cache keeps today's view")
        # The hub card shows today's numbers too.
        self.page.keyboard.press("h")
        self.page.wait_for_function("document.querySelector('.hub-ops__title')?.textContent === 'Study 120 / 360 min'", timeout=10000)

    def test_a_new_day_refetches_the_dashboard(self):
        self.open_command_center()
        gets = self.backend.gets
        tomorrow = TODAY + timedelta(days=1)
        self.page.clock.set_system_time(f"{tomorrow.isoformat()}T09:00:00")
        self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        self.page.wait_for_timeout(600)
        self.assertGreater(self.backend.gets, gets, "returning to the tab on a new day fetches that day")

    def test_workout_sets_and_reps_must_be_positive_like_the_server(self):
        self.open_command_center()
        page = self.page
        page.keyboard.press("2")
        page.fill("#ops-workout-activity", "Run")
        page.fill("#ops-workout-minutes", "30")
        page.fill("#ops-workout-sets", "0")
        page.fill("#ops-workout-reps", "0")
        page.click("#ops-form-workout .ops-form__submit")
        self.wait_status("workout", "Fix the highlighted fields")
        self.assertIn("at least 1", self.text("#ops-workout-sets-err"))
        self.assertIn("Leave it empty", self.text("#ops-workout-sets-err"))
        self.assertIn("at least 1", self.text("#ops-workout-reps-err"))
        self.assertEqual(page.get_attribute("#ops-workout-sets", "min"), "1")
        self.assertEqual(self.backend.posts, [], "0 sets never reaches the server (it would reject it)")
        page.fill("#ops-workout-sets", "-2")
        page.fill("#ops-workout-reps", "")
        page.click("#ops-form-workout .ops-form__submit")
        self.assertIn("1–1000", self.text("#ops-workout-sets-err"))
        page.fill("#ops-workout-sets", "")
        page.fill("#ops-workout-load_lbs", "0")  # load and distance may be 0
        page.click("#ops-form-workout .ops-form__submit")
        self.wait_status("workout", "+30 XP")
        _, body = self.backend.posts[-1]
        self.assertNotIn("sets", body)
        self.assertEqual(body["load_lbs"], 0)

    def test_long_milestone_history_is_capped(self):
        snap = copy.deepcopy(BASE_SNAPSHOT)
        snap["milestones"] = [{"id": i, "title": f"Daily goal {i:03d}", "achieved_at": day(0)} for i in range(1, 41)]
        snap["milestones"].append({"id": 99, "title": "Precalculus cleared", "progress": 0.4})
        self.backend.snapshot = snap
        self.open_command_center()
        rows = self.page.locator(".ops-milestone")
        self.assertEqual(rows.count(), 20)
        self.assertIn("Precalculus cleared", self.text(".ops-milestone"))  # in progress first
        self.assertIn("Daily goal 040", self.text(".ops-milestone:nth-child(2)"))  # then newest achieved
        self.assertIn("+21 earlier milestones", self.text(".ops-milestones__more"))

    def test_server_milestone_shape_newest_first_with_counts(self):
        # The real tracker sends its newest 20 milestones (id DESC) plus milestone_counts.
        snap = copy.deepcopy(BASE_SNAPSHOT)
        snap["milestones"] = [{"id": i, "key": f"study-goal:{i}", "title": f"Daily goal {i:03d}", "category": "study",
                               "achieved_at": f"{day(0)}T10:00:00"} for i in range(45, 25, -1)]
        snap["milestone_counts"] = {"study": 45, "fitness": 0, "coding": 0, "total": 45}
        snap["inventory"] = [{"item_key": "focus_chip", "quantity": 45,
                              "metadata": {"name": "Focus Chip", "rarity": "uncommon", "icon": "\u25c8",
                                           "description": "Compiled from a completed daily math objective."}}]
        self.backend.snapshot = snap
        self.open_command_center()
        rows = self.page.locator(".ops-milestone")
        self.assertEqual(rows.count(), 20)
        self.assertIn("Daily goal 045", self.text(".ops-milestone:nth-child(1)"))  # newest stays first
        self.assertIn("Daily goal 026", self.text(".ops-milestone:nth-child(20)"))
        self.assertIn("+25 earlier milestones", self.text(".ops-milestones__more"))
        self.assertIn("Focus Chip", self.text(".ops-items"))
        self.assertIn("45 items", self.text(".ops-armory"))

    def test_short_milestone_list_has_no_overflow_row(self):
        snap = copy.deepcopy(BASE_SNAPSHOT)
        snap["milestones"] = [{"id": 2, "key": "coding:L01", "title": "Mission L01 cleared", "category": "coding", "achieved_at": f"{day(0)}T10:00:00"},
                              {"id": 1, "key": "first-workout", "title": "Training protocol activated", "category": "fitness", "achieved_at": f"{day(0)}T09:00:00"}]
        snap["milestone_counts"] = {"study": 0, "fitness": 1, "coding": 1, "total": 2}
        self.backend.snapshot = snap
        self.open_command_center()
        self.assertEqual(self.page.locator(".ops-milestone").count(), 2)
        self.assertEqual(self.page.locator(".ops-milestones__more").count(), 0)
        self.assertNotIn("null", self.text(".ops-milestones"))
        self.assertNotIn("null", self.text(".ops-armory"))

    def test_form_follows_the_servers_limit_table(self):
        snap = copy.deepcopy(BASE_SNAPSHOT)
        snap["limits"] = {"minutes": [1, 1440], "sets": [1, 50], "reps": [1, 10000], "load_lbs": [0, 2000],
                          "distance_miles": [0, 500], "weight_lbs": [50, 800]}
        self.backend.snapshot = snap
        self.open_command_center()
        page = self.page
        page.keyboard.press("2")
        page.fill("#ops-workout-activity", "Strength")
        page.fill("#ops-workout-minutes", "30")
        page.fill("#ops-workout-sets", "60")
        page.click("#ops-form-workout .ops-form__submit")
        self.wait_status("workout", "Fix the highlighted fields")
        self.assertIn("1–50", self.text("#ops-workout-sets-err"))
        self.assertEqual(self.backend.posts, [])
        page.fill("#ops-workout-sets", "5")
        page.click("#ops-form-workout .ops-form__submit")
        self.wait_status("workout", "+30 XP")
        self.assertEqual(self.backend.posts[-1][1]["sets"], 5)

    def test_keyboard_navigation(self):
        self.open_command_center()
        page = self.page
        page.keyboard.press("2")
        page.focus("#ops-tab-workout")
        page.keyboard.press("ArrowRight")
        self.assertEqual(page.get_attribute("#ops-tab-weight", "aria-selected"), "true")
        self.assertTrue(page.evaluate("document.activeElement.id === 'ops-tab-weight'"))
        self.assertTrue(page.is_visible("#ops-form-weight"))
        self.assertFalse(page.is_visible("#ops-form-study"))
        page.keyboard.press("Home")
        self.assertEqual(page.get_attribute("#ops-tab-study", "aria-selected"), "true")
        page.keyboard.press("h")
        page.wait_for_selector(".screen--hub.is-active", timeout=10000)

    def test_responsive_layouts_do_not_overflow(self):
        for width, height in ((1024, 768), (390, 844)):
            self.page.set_viewport_size({"width": width, "height": height})
            if width == 1024:
                self.open_command_center()
            self.page.wait_for_timeout(300)
            overflow = self.page.evaluate(
                "() => { const el = document.querySelector('.ops');"
                " return {page: document.documentElement.scrollWidth - innerWidth, grid: el.scrollWidth - el.clientWidth}; }")
            self.assertLessEqual(overflow["page"], 0, f"page scrolls sideways at {width}px")
            self.assertLessEqual(overflow["grid"], 1, f"grid overflows at {width}px")


if __name__ == "__main__":
    unittest.main()
