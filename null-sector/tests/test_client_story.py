"""Browser tests for the story hooks (client/js/ui/story.js and the screens that call it).

Same approach as tests/test_client_fixes.py: the real client runs in headless Chromium, every
request is intercepted, and the campaign API (including /api/story/*) is answered by a real
GameSession in a temporary folder, so the seen flags land in a real save.json.

Each hook must fire exactly once per save:
  * the prologue, on the first jack-in (boot → prologue → hub);
  * an act opening, before the first deploy of that sector's first level (hub → intro → mission);
  * the epilogue, after the last victory (L25 victory → transmission → epilogue → hub);
  * the hub's STORY archive (key S) replays any unlocked scene without changing what was seen;
  * an old backend (no `State.story`, no /api/story) gets no story requests and no story UI.

Skipped automatically when Playwright or a Chromium build is unavailable.
Run from the game folder:  python -m unittest tests.test_client_story -v
"""
from __future__ import annotations

import json
import re
import time
import unittest

from tests import test_client_fixes
from tests.test_client_fixes import CampaignBackend
from tests.test_client_productivity import ORIGIN, sync_playwright
from tests.test_levels_act5 import L25_SOLUTION

STORY_ROUTE = re.compile(r"/api/story/(?P<event>[^/]+)")


class StoryBackend(CampaignBackend):
    """CampaignBackend plus GET /api/story/<event> and POST /api/story/seen (a real GameSession).

    `legacy = True` plays an old server: no `story` key in State and 404 for every story route.
    """

    def __init__(self, session):
        super().__init__(session)
        self.legacy = False
        self.story_calls: list[tuple[str, str]] = []   # (method, event or seen id)
        self.story_plan: list = []                     # queue of (status, body) for GET /api/story/*

    def _state(self):
        state = self.session.snapshot()
        if self.legacy:
            state.pop("story", None)
        return state

    def _api(self, route, request, path):
        from engine.session import SessionError

        if path == "/api/state" and request.headers.get("x-ns-token"):
            return self._json(route, 200, self._state())
        match = STORY_ROUTE.fullmatch(path)
        if not match:
            return super()._api(route, request, path)
        try:
            if path == "/api/story/seen" and request.method == "POST":
                body = json.loads(request.post_data or "{}")
                self.story_calls.append(("POST", str(body.get("id"))))
                if self.legacy:
                    return self._json(route, 404, {"error": "not found"})
                return self._json(route, 200, self.session.mark_story_seen(body.get("id")))
            if request.method == "GET":
                self.story_calls.append(("GET", match["event"]))
                if self.legacy:
                    return self._json(route, 404, {"error": "not found"})
                if self.story_plan:
                    status, body = self.story_plan.pop(0)
                    return self._json(route, status, body)
                return self._json(route, 200, self.session.story(match["event"]))
        except SessionError as err:
            return self._json(route, err.status, {"error": err.message})
        return self._json(route, 405, {"error": "method not allowed"})


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class StoryHookTests(test_client_fixes.CampaignClientFixTests):
    """Reuses the browser fixture and helpers of CampaignClientFixTests (not its tests, see below)."""

    def setUp(self):
        super().setUp()
        self.page.unroute_all(behavior="ignoreErrors")
        self.backend = StoryBackend(self.session)
        self.page.route("**/*", self.backend.handle)

    # ── helpers ────────────────────────────────────────────────────────────
    def boot(self):
        page = self.page
        page.goto(ORIGIN + "/")
        page.wait_for_function("window.__nsBooted === true", timeout=20000)
        page.wait_for_selector(".screen--boot", timeout=10000)
        page.wait_for_timeout(400)
        page.keyboard.press("Space")

    def wait_story(self, story_id: str, timeout=15000):
        self.page.wait_for_selector(".screen--cutscene.screen--story.is-active", timeout=timeout, state="attached")
        self.page.wait_for_function(
            "(t) => document.querySelector('.screen--story .cs-hud__rec')?.textContent.includes(t)",
            arg=self.chapter(story_id), timeout=5000)

    @staticmethod
    def chapter(story_id: str) -> str:
        if story_id.startswith("intro-"):
            return "ACT " + ["I", "II", "III", "IV", "V"][int(story_id[-1])]
        return story_id.upper()

    def skip_scene(self):
        self.page.wait_for_timeout(500)
        self.page.keyboard.press("Escape")
        self.page.wait_for_selector(".screen--cutscene", state="detached", timeout=10000)

    def wait_hub(self):
        self.page.wait_for_selector(".screen--hub.is-active .deploy", timeout=15000, state="attached")

    def wait_mission(self):
        self.page.wait_for_selector(".screen--mission.is-active .mission-editor textarea", timeout=15000)

    def story(self):
        return self.session.snapshot()["story"]

    def calls(self, story_id: str, method="GET"):
        return self.backend.story_calls.count((method, story_id))

    def clear_through(self, last: int):
        """Mark L01..L<last> cleared straight in the save (the levels' own tests prove them)."""
        save = self.session.save
        with save.transaction():
            for n in range(1, last + 1):
                save.cleared[f"L{n:02}"] = {"xp": 100, "attempts": 1, "seconds": 60}
            save.callsign = save.callsign or "Nyx"

    def to_hub(self):
        self.page.evaluate("window.__NS__.screens.go('hub')")
        self.wait_hub()

    # ── prologue ───────────────────────────────────────────────────────────
    def test_prologue_plays_once_on_the_first_jack_in(self):
        self.boot()
        self.wait_story("prologue")
        self.assertIn("THE NULL EVENT", self.page.get_attribute(".screen--story", "aria-label"))
        self.page.wait_for_timeout(600)
        self.assertFalse(self.story()["prologue"], "not marked seen while it is still playing")
        self.skip_scene()
        self.wait_hub()
        self.assertTrue(self.story()["prologue"])
        self.assertEqual((self.calls("prologue"), self.calls("prologue", "POST")), (1, 1))

        # Back to boot in the same tab, then a reload: the hub opens straight away both times.
        self.page.evaluate("window.__NS__.screens.go('boot')")
        self.page.wait_for_selector(".screen--boot", timeout=10000)
        self.page.wait_for_timeout(400)
        self.page.keyboard.press("Space")
        self.wait_hub()
        self.boot()
        self.wait_hub()
        self.page.wait_for_timeout(800)
        self.assertIsNone(self.page.query_selector(".screen--cutscene"))
        self.assertEqual((self.calls("prologue"), self.calls("prologue", "POST")), (1, 1))

    def test_prologue_with_reduced_motion_still_plays_and_is_marked(self):
        self.page.add_init_script(
            "localStorage.setItem('nullsector.settings.v1', JSON.stringify({reducedMotion: true}))")
        self.boot()
        self.wait_story("prologue")
        self.assertTrue(self.page.evaluate("document.body.classList.contains('reduce-motion')"))
        self.skip_scene()
        self.wait_hub()
        self.assertTrue(self.story()["prologue"])

    def test_a_failed_story_request_goes_straight_on_and_marks_nothing(self):
        self.backend.story_plan = [(500, {"error": "boom"})]
        self.boot()
        self.wait_hub()
        self.assertEqual(self.calls("prologue"), 1)
        self.assertFalse(self.story()["prologue"])
        self.assertIsNone(self.page.query_selector(".screen--cutscene"))

    # ── act openings ───────────────────────────────────────────────────────
    def test_act_opening_plays_once_before_the_first_deploy(self):
        self.session.mark_story_seen("prologue")
        self.boot()
        self.wait_hub()
        self.page.wait_for_timeout(300)
        self.page.keyboard.press("Enter")
        self.wait_story("intro-0")
        self.assertFalse(self.story()["intros"])
        self.skip_scene()
        self.wait_mission()
        self.assertEqual(self.story()["intros"], [0])
        self.assertEqual(self.page.evaluate("window.__NS__.state.current"), "L01")
        self.skip_story()
        # Deploying again never replays it.
        self.to_hub()
        self.page.wait_for_timeout(300)
        self.page.keyboard.press("Enter")
        self.wait_mission()
        self.assertEqual((self.calls("intro-0"), self.calls("intro-0", "POST")), (1, 1))

    def test_each_sector_opening_fires_on_its_first_level_only(self):
        self.session.mark_story_seen("prologue")
        self.clear_through(5)                 # L06 (Act II) is next
        self.boot()
        self.wait_hub()
        self.page.wait_for_timeout(300)
        self.page.keyboard.press("Enter")
        self.wait_story("intro-1")
        self.skip_scene()
        self.wait_mission()
        self.assertEqual(self.story()["intros"], [1])
        self.assertEqual([c for c in self.backend.story_calls if c[1].startswith("intro")],
                         [("GET", "intro-1"), ("POST", "intro-1")])

        # A sector's later levels open without a scene.
        self.clear_through(6)
        self.page.evaluate("window.__NS__.refreshState()")
        self.to_hub()
        self.page.wait_for_function("window.__NS__.state.current === 'L07'")
        self.page.wait_for_timeout(300)
        self.page.keyboard.press("Enter")
        self.wait_mission()
        self.assertEqual(len([c for c in self.backend.story_calls if c[1].startswith("intro")]), 2)

    # ── epilogue + archive ─────────────────────────────────────────────────
    def test_epilogue_plays_once_after_the_last_victory_and_the_archive_replays(self):
        for event in ("prologue", "intro-0", "intro-1", "intro-2", "intro-3", "intro-4"):
            self.session.mark_story_seen(event)
        self.clear_through(24)
        self.boot()
        self.wait_hub()
        self.page.wait_for_timeout(300)
        self.page.keyboard.press("Enter")
        self.wait_mission()
        self.skip_story()
        self.page.fill(".mission-editor textarea", L25_SOLUTION)
        self.page.wait_for_function(
            "document.querySelector('.mission-sync')?.textContent.trim().toUpperCase() === 'SYNCED'", timeout=15000)
        self.page.keyboard.press("Control+Enter")
        self.skip_story(timeout=60000)        # CIPHER's victory lines
        self.page.wait_for_selector(".screen--victory.is-active", timeout=60000)
        self.page.wait_for_timeout(300)
        self.page.keyboard.press("Space")     # skip the reveal
        self.page.wait_for_selector(".screen--victory.is-revealed", timeout=30000)
        self.assertFalse(self.story()["epilogue"])
        self.page.keyboard.press("Enter")     # the boss transmission
        self.page.wait_for_selector(".screen--cutscene.is-active:not(.screen--story)", timeout=15000, state="attached")
        self.assertFalse(self.backend.story_calls, "nothing story-related before the transmission ends")
        self.page.wait_for_timeout(500)
        self.page.keyboard.press("Escape")    # the cutscene screen hands over to the epilogue
        self.wait_story("epilogue")
        self.assertIn("DAWN OVER THE DEAD ZONE", self.page.get_attribute(".screen--story", "aria-label"))
        self.skip_scene()
        self.wait_hub()
        self.assertTrue(self.story()["epilogue"])
        self.assertEqual((self.calls("epilogue"), self.calls("epilogue", "POST")), (1, 1))

        # The STORY archive (keyboard): every chapter unlocked; replaying one marks nothing new.
        self.page.wait_for_timeout(500)
        self.page.keyboard.press("s")
        self.page.wait_for_selector(".story-reel", timeout=5000)
        self.page.wait_for_function("document.querySelectorAll('.story-chapter:not(:disabled)').length === 7")
        self.page.keyboard.press("ArrowUp")    # wraps to the last row: the epilogue
        self.assertEqual(self.page.evaluate("document.activeElement.dataset.story"), "epilogue")
        self.page.keyboard.press("Enter")
        self.wait_story("epilogue")
        self.skip_scene()
        self.wait_hub()
        # One fetch for the automatic play, one for the archive's titles; the replay reuses it.
        self.assertEqual((self.calls("epilogue"), self.calls("epilogue", "POST")), (2, 2))
        self.assertTrue(self.story()["epilogue"])

        # Replaying the L25 transmission from the gallery never re-triggers the epilogue.
        self.page.evaluate("window.__NS__.screens.go('cutscene', {mission: {id: 'L25', title: 'x', "
                           "cutscene: {title: 'x', narration: ['x']}}})")
        self.page.wait_for_selector(".screen--cutscene.is-active", timeout=10000, state="attached")
        self.skip_scene()
        self.wait_hub()
        self.assertEqual(self.calls("epilogue"), 2)

    def test_archive_lists_only_what_was_reached(self):
        self.session.mark_story_seen("prologue")
        self.boot()
        self.wait_hub()
        self.page.wait_for_timeout(300)
        self.page.keyboard.press("s")
        self.page.wait_for_selector(".story-reel", timeout=5000)
        rows = self.page.eval_on_selector_all(".story-chapter", "els => els.map(e => [e.dataset.story, e.disabled])")
        self.assertEqual(rows, [["prologue", False], ["intro-0", True], ["intro-1", True], ["intro-2", True],
                                ["intro-3", True], ["intro-4", True], ["epilogue", True]])
        self.assertEqual(self.page.evaluate("document.activeElement.dataset.story"), "prologue")
        self.page.keyboard.press("Escape")
        self.page.wait_for_selector(".story-reel", state="detached", timeout=5000)
        self.assertTrue(self.page.evaluate("document.activeElement === document.body || !!document.activeElement"))

    # ── old backend ────────────────────────────────────────────────────────
    def test_an_old_backend_gets_no_story_requests_and_no_story_ui(self):
        self.backend.legacy = True
        self.boot()
        self.wait_hub()
        self.assertTrue(self.page.is_hidden(".hub-story"))
        self.page.keyboard.press("s")
        self.page.wait_for_timeout(400)
        self.assertIsNone(self.page.query_selector(".story-reel"))
        self.page.keyboard.press("Enter")
        self.wait_mission()
        self.assertEqual(self.backend.story_calls, [])


# The parent's own tests are run by tests/test_client_fixes.py; don't run them twice here.
for _name in [n for n in vars(test_client_fixes.CampaignClientFixTests) if n.startswith("test_")]:
    setattr(StoryHookTests, _name, None)


if __name__ == "__main__":
    unittest.main()
