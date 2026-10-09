"""Browser tests for the campaign-path client fixes (mission → victory → hub).

Same approach as tests/test_client_productivity.py: the real client runs in headless Chromium
and every request is intercepted. Campaign routes (/api/state, /api/missions/...) are served by
a real GameSession rooted in a temporary folder, so the grader, rewards and the starter file are
the game's own; /api/productivity* comes from the scripted MockBackend.

Covers:
  * the victory screen shows the HackResult's own numbers (rank, XP meter, IDENTITY REGISTERED)
    even when the server's SSE `state` push lands before the hack response;
  * RESTORE on the mission screen (in-page confirm, keyboard path, api.reset, failure path);
  * the hub's memory gallery after the first clear (in-engine transmission card, honest copy).

Skipped automatically when Playwright or a Chromium build is unavailable.
Run from the game folder:  python -m unittest tests.test_client_fixes -v
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import tempfile
import time
import unittest

from tests.test_client_productivity import BASE_SNAPSHOT, ORIGIN, TOKEN, MockBackend, _chromium_path, sync_playwright

SOLUTION = (
    'callsign = "Nyx"\n'
    "integrity = 100\n"
    "battery = 0.35\n"
    "is_online = True\n"
    "power_needed = 1.0 - battery\n"
    'scrap_from_crate = "12"\n'
    "scrap_total = int(scrap_from_crate) + 8\n"
    'print(f"{callsign} online")\n'
)
MISSION_ROUTE = re.compile(r"/api/missions/(?P<id>[A-Z]\d{2})(?:/(?P<action>deploy|source|hack|reset|cutscene))?")


class CampaignBackend(MockBackend):
    """MockBackend plus the campaign API, answered by a real GameSession."""

    def __init__(self, session):
        super().__init__(BASE_SNAPSHOT, session.snapshot())
        self.session = session
        self.hold_hack = False       # True: keep the hack response until the test releases it
        self.held: list = []         # [(route, result)]
        self.reset_plan: list = []   # queue of (status, body) answers for POST .../reset
        self.calls: list[tuple[str, str]] = []

    def _api(self, route, request, path):
        from engine.session import SessionError

        if request.headers.get("x-ns-token") != TOKEN and path != "/api/events":
            return self._json(route, 401, {"error": "missing token"})
        if path == "/api/state":
            return self._json(route, 200, self.session.snapshot())
        match = MISSION_ROUTE.fullmatch(path)
        if not match:
            return super()._api(route, request, path)
        mid, action = match["id"], match["action"]
        self.calls.append((request.method, action or "mission"))
        try:
            if action is None and request.method == "GET":
                return self._json(route, 200, self.session.mission(mid))
            if action == "deploy":
                return self._json(route, 200, self.session.deploy(mid))
            if action == "source" and request.method == "PUT":
                body = json.loads(request.post_data or "{}")
                return self._json(route, 200, self.session.write_source(mid, body["source"]))
            if action == "hack":
                result = self.session.attack(mid)
                if self.hold_hack:
                    self.held.append((route, result))
                    return None
                return self._json(route, 200, result)
            if action == "reset":
                if self.reset_plan:
                    status, body = self.reset_plan.pop(0)
                    return self._json(route, status, body)
                return self._json(route, 200, self.session.reset(mid))
            if action == "cutscene":
                return self._json(route, 200, {"mission": mid, "state": "offline", "reason": "no API key in config.json"})
        except SessionError as err:
            return self._json(route, err.status, {"error": err.message})
        return self._json(route, 404, {"error": "not found"})


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class CampaignClientFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.getLogger("asyncio").addFilter(
            lambda rec: not (rec.exc_info and isinstance(rec.exc_info[1], asyncio.CancelledError)))
        cls._pw = sync_playwright().start()
        try:
            cls.browser = cls._pw.chromium.launch(
                executable_path=_chromium_path(),
                args=["--disable-webgl", "--disable-3d-apis", "--autoplay-policy=no-user-gesture-required"],
            )
        except Exception as exc:  # pragma: no cover - depends on the machine
            cls._pw.stop()
            raise unittest.SkipTest(f"Chromium unavailable: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()

    def setUp(self):
        from engine.session import GameSession
        from engine.state import Paths

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.session = GameSession(Paths.rooted(self._tmp.name))
        self.backend = CampaignBackend(self.session)
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 900})
        self.problems: list[str] = []
        self.page.on("pageerror", lambda e: self.problems.append(f"pageerror: {e}"))
        self.page.on("console", lambda m: self.problems.append(f"{m.type}: {m.text}")
                     if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
        self.page.route("**/*", self.backend.handle)

    def tearDown(self):
        for route, _ in self.backend.held:  # never leave a request hanging
            try:
                route.abort()
            except Exception:
                pass
        self.page.unroute_all(behavior="ignoreErrors")
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
        page.wait_for_selector(".screen--hub.is-active .deploy", timeout=15000)

    def skip_story(self, timeout=4000):
        """Close the CIPHER dialogue overlay if it opens (it does on a first deploy and a victory)."""
        try:
            self.page.wait_for_selector("dialog.dialogue[open]", timeout=timeout)
        except Exception:
            return False
        self.page.locator("dialog.dialogue[open] button", has_text="SKIP STORY").click()
        self.page.wait_for_selector("dialog.dialogue[open]", state="detached", timeout=5000)
        return True

    def open_mission(self):
        self.open_hub()
        self.page.wait_for_timeout(300)
        self.page.keyboard.press("Enter")
        self.page.wait_for_selector(".screen--mission.is-active .mission-editor textarea", timeout=15000)
        self.skip_story()

    def editor_value(self):
        return self.page.input_value(".mission-editor textarea")

    def type_code(self, text):
        self.page.fill(".mission-editor textarea", text)
        self.wait_until(lambda: self.disk() == text, message="the autosave")
        self.page.wait_for_function(
            "document.querySelector('.mission-sync')?.textContent.trim().toUpperCase() === 'SYNCED'", timeout=10000)

    def disk(self):
        return self.session.mission_path("L01").read_text(encoding="utf-8")

    def wait_until(self, predicate, timeout=15.0, message="condition"):
        end = time.time() + timeout
        while time.time() < end:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(f"timed out waiting for {message}")

    def clear_l01_in_backend(self):
        self.session.deploy("L01")
        self.session.write_source("L01", SOLUTION)
        result = self.session.attack("L01")
        self.assertTrue(result["victory"], result["report"])

    # ── victory: the HackResult's own numbers, whenever the SSE push lands ──
    def _victory_with_state_push_first(self, *, skip_reveal: bool):
        page = self.page
        self.open_mission()
        self.type_code(SOLUTION)
        self.backend.hold_hack = True
        page.keyboard.press("Control+Enter")
        self.wait_until(lambda: self.backend.held, message="the hack request")
        route, result = self.backend.held.pop()
        self.assertTrue(result["victory"], result["report"])
        self.assertEqual(result["reward"]["rank_before"], "GHOST PROCESS")
        # Exactly what main.js does with an SSE `state` event: the post-victory profile becomes
        # ctx.state *before* the hack response arrives (the worst case of the race).
        page.evaluate(
            """(s) => { const ctx = window.__NS__; ctx.state = s; ctx.bus.emit('server:state', s); ctx.bus.emit('state:changed', s); }""",
            result["state"],
        )
        route.fulfill(status=200, content_type="application/json", body=json.dumps(result))
        self.skip_story(timeout=15000)  # the victory transmission
        page.wait_for_selector(".screen--victory.is-active", timeout=15000)
        if skip_reveal:
            page.wait_for_timeout(300)
            page.keyboard.press("Space")
        page.wait_for_selector(".screen--victory.is-revealed", timeout=30000)
        return result

    def assert_first_clear_rewards(self):
        page = self.page
        self.assertEqual(page.text_content(".victory__rank").strip(), "SCRIPT KIDDIE")
        self.assertEqual(" ".join(page.text_content(".victory__xp-num").split()), "150 / 400 XP")
        value = float(page.evaluate("document.querySelector('.victory__meter').style.getPropertyValue('--value')"))
        self.assertAlmostEqual(value, (150 - 100) / (400 - 100), places=3)
        self.assertIn("SCRIPT KIDDIE", page.text_content(".victory__rankup"))
        identity = " ".join((page.text_content(".victory__identity") or "").split())
        self.assertIn("IDENTITY REGISTERED", identity)
        self.assertIn("NYX", identity)

    def test_victory_numbers_survive_an_early_state_push(self):
        self._victory_with_state_push_first(skip_reveal=False)
        self.assert_first_clear_rewards()

    def test_victory_numbers_survive_an_early_state_push_when_skipped(self):
        self._victory_with_state_push_first(skip_reveal=True)
        self.assert_first_clear_rewards()
        self.page.keyboard.press("h")
        self.page.wait_for_selector(".screen--hub.is-active", timeout=15000)

    def test_prior_profile_ignores_a_snapshot_taken_after_the_victory(self):
        self.open_hub()
        out = self.page.evaluate("""async () => {
          const { priorProfile } = await import('/js/ui/screens/victory.js');
          const after = {callsign: 'Nyx', xp: 150, rank: 'SCRIPT KIDDIE', rank_floor: 100, rank_next: 400};
          const result = {reward: {gained: 150, rank_up: true, replay: false}, state: {profile: after}};
          return {
            late: priorProfile(result, after),
            early: priorProfile(result, {callsign: '', xp: 0, rank: 'GHOST PROCESS', rank_floor: 0, rank_next: 100}),
            none: priorProfile(result, null),
            server: priorProfile({...result, reward: {...result.reward, xp_before: 0, callsign_before: ''}}, after),
          };
        }""")
        self.assertEqual(out["late"], {"xp": 0, "rankFloor": None, "callsign": None, "trusted": False})
        self.assertEqual(out["early"], {"xp": 0, "rankFloor": 0, "callsign": "", "trusted": True})
        self.assertEqual(out["none"]["xp"], 0)
        self.assertEqual(out["server"]["callsign"], "")

    # ── restore starter code ─────────────────────────────────────────────
    def test_restore_starter_code_with_confirm_and_keyboard(self):
        page = self.page
        starter = self.session.mission("L01")["source"]
        self.open_mission()
        self.type_code("garbage = 1\n")
        self.assertEqual(self.disk(), "garbage = 1\n")

        # Click RESTORE: an in-page confirm opens with the safe choice focused; Esc backs out.
        page.click(".mission-restore")
        page.wait_for_selector(".mission-restore-bar:not([hidden])", timeout=5000)
        self.assertEqual(page.get_attribute(".mission-restore", "aria-expanded"), "true")
        self.assertTrue(page.evaluate("document.activeElement.classList.contains('mission-restore-bar__cancel')"))
        page.keyboard.press("Escape")
        page.wait_for_selector(".mission-restore-bar", state="hidden", timeout=5000)
        self.assertTrue(page.evaluate("document.activeElement.classList.contains('mission-restore')"))
        self.assertEqual(self.editor_value(), "garbage = 1\n")
        self.assertNotIn(("POST", "reset"), self.backend.calls)

        # Keyboard all the way: Alt+R from inside the editor, Shift+Tab to the confirm, Enter.
        page.focus(".mission-editor textarea")
        page.keyboard.press("Alt+r")
        page.wait_for_selector(".mission-restore-bar:not([hidden])", timeout=5000)
        page.keyboard.press("Shift+Tab")
        self.assertTrue(page.evaluate("document.activeElement.classList.contains('mission-restore-bar__go')"))
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('#toasts')?.textContent.includes('RESTORED')", timeout=10000)
        self.assertIn(("POST", "reset"), self.backend.calls)
        self.assertEqual(self.editor_value(), starter)
        self.assertEqual(self.disk(), starter)
        self.assertEqual(page.text_content(".mission-sync").strip().upper(), "SYNCED")
        page.wait_for_selector(".mission-restore-bar", state="hidden", timeout=5000)
        self.assertIn("Starter code restored", page.text_content(".mission-log"))
        # No late autosave puts the old text back.
        page.wait_for_timeout(1500)
        self.assertEqual(self.disk(), starter)

    def test_restore_failure_keeps_the_players_code(self):
        page = self.page
        self.open_mission()
        self.type_code("mine = 2\n")
        self.backend.reset_plan = [(500, {"error": "disk is read-only"})]
        page.click(".mission-restore")
        page.click(".mission-restore-bar__go")
        page.wait_for_function("document.querySelector('#toasts')?.textContent.includes('RESTORE FAILED')", timeout=10000)
        self.assertIn("disk is read-only", page.text_content("#toasts"))
        self.assertEqual(self.editor_value(), "mine = 2\n")
        self.assertEqual(self.disk(), "mine = 2\n")
        self.assertFalse(page.is_disabled(".mission-restore"))
        self.assertFalse(page.is_disabled(".hack-btn"), "HACK is usable again")

    # ── hub memory gallery ───────────────────────────────────────────────
    def test_gallery_before_the_first_clear_invites_one(self):
        self.open_hub()
        self.page.wait_for_selector(".hub-gallery__empty", timeout=10000)
        self.assertIn("Clear your first level", self.page.text_content(".hub-gallery__list"))

    def test_gallery_after_the_first_clear_offers_the_transmission(self):
        self.clear_l01_in_backend()
        self.open_hub()
        page = self.page
        card = page.wait_for_selector(".frag--transmission", timeout=10000)
        text = " ".join(page.text_content(".hub-gallery__list").split())
        self.assertNotIn("Clear your first level", text)
        self.assertIn("L01", text)
        self.assertIn("IDENTITY ACCEPTED", text.upper())
        self.assertIn("In-engine", text)
        self.assertEqual(page.text_content(".hub-gallery__count").strip(), "01")
        self.assertIn("Replay transmission L01", card.get_attribute("aria-label"))
        card.click()
        page.wait_for_selector(".screen--cutscene.is-active", timeout=15000)


if __name__ == "__main__":
    unittest.main()
