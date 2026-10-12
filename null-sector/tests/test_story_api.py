"""Story hooks on the server: `State.story`, GET /api/story/<event>, POST /api/story/seen,
`Save.seen`, and the reward's `xp_before` / `callsign_before`.

Run from the game folder:  python -m unittest tests.test_story_api -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import SOLUTION, STORY_IDS, SandboxTestCase, assert_hack_result, assert_state, assert_story  # noqa: E402
from tests.test_server import ServerTestCase  # noqa: E402

from engine.session import GameSession, SessionError, story_api_id, story_event  # noqa: E402
from engine.state import Save  # noqa: E402
from levels import CAMPAIGN  # noqa: E402
from levels import story as story_content  # noqa: E402

FRESH = {"prologue": False, "intros": [], "epilogue": False}


class StoryIdTests(unittest.TestCase):
    def test_api_ids_map_to_story_events_and_back(self):
        self.assertEqual([story_event(i) for i in STORY_IDS], list(story_content.EVENTS))
        self.assertEqual([story_api_id(e) for e in story_content.EVENTS], list(STORY_IDS))
        self.assertEqual(story_event("intro:3"), "intro:3", "the module's own ids are accepted too")

    def test_unknown_ids_are_404(self):
        for bad in ("", "Prologue", "intro-5", "intro-01", "intro-", "intro:9", "seen", "../save", None, 3, "x" * 500):
            with self.subTest(bad=bad), self.assertRaises(SessionError) as caught:
                story_event(bad)
            self.assertEqual(caught.exception.status, 404)
            self.assertLess(len(caught.exception.message), 120)


class StorySessionTests(SandboxTestCase):
    def test_a_new_save_has_seen_nothing(self):
        state = self.session.snapshot()
        assert_state(self, state)
        self.assertEqual(state["story"], FRESH)
        self.assertEqual(self.session.save.seen, {})

    def test_payload_is_the_cutscene_screen_shape(self):
        for api_id, (event, cutscene) in zip(STORY_IDS, story_content.ALL):
            with self.subTest(api_id=api_id):
                payload = self.session.story(api_id)
                assert_story(self, payload)
                self.assertEqual(payload["id"], api_id)
                self.assertEqual(payload["cutscene"], {"title": cutscene.title, "narration": list(cutscene.narration)})
                self.assertIsNone(payload["media"])
                self.assertFalse(payload["seen"])
        intro = self.session.story("intro-2")
        sector = next(s for s in CAMPAIGN if s.tier == 2)
        self.assertEqual(intro["chapter"], "ACT III")
        self.assertEqual(intro["sector"], {"name": sector.name, "zone": sector.zone, "color": sector.color})
        self.assertEqual(self.session.story("prologue")["chapter"], "PROLOGUE")

    def test_mark_seen_is_idempotent_and_persists(self):
        reply = self.session.mark_story_seen("prologue")
        self.assertEqual(reply, {"ok": True, "id": "prologue", "story": {**FRESH, "prologue": True}})
        mtime = self.paths.save_path.stat().st_mtime_ns
        self.assertEqual(self.session.mark_story_seen("prologue")["story"], {**FRESH, "prologue": True})
        self.assertEqual(self.paths.save_path.stat().st_mtime_ns, mtime, "seeing it again writes nothing")
        self.session.mark_story_seen("intro-3")
        self.session.mark_story_seen("intro:0")
        self.session.mark_story_seen("epilogue")
        on_disk = json.loads(self.paths.save_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["seen"], {"story": ["prologue", "intro:3", "intro:0", "epilogue"]})
        again = GameSession(self.paths).snapshot()["story"]
        self.assertEqual(again, {"prologue": True, "intros": [0, 3], "epilogue": True})
        self.assertTrue(self.session.story("intro-3")["seen"])
        self.assertFalse(self.session.story("intro-1")["seen"])

    def test_mark_seen_validates(self):
        for bad, status in ((None, 400), (7, 400), (["prologue"], 400), ("nope", 404), ("intro-7", 404)):
            with self.subTest(bad=bad), self.assertRaises(SessionError) as caught:
                self.session.mark_story_seen(bad)
            self.assertEqual(caught.exception.status, status)
        self.assertFalse(self.paths.save_path.exists() and json.loads(self.paths.save_path.read_text()).get("seen"))

    def test_old_saves_load_unchanged_and_odd_seen_values_are_tolerated(self):
        legacy = {"callsign": "Nyx", "xp": 150, "cleared": {"L01": {"xp": 150, "attempts": 2, "seconds": 300}}, "attempts": {"L01": 2}}
        self.paths.save_path.write_text(json.dumps(legacy), encoding="utf-8")
        save = Save.load(self.paths.save_path)
        self.assertEqual(save.seen, {})
        self.assertEqual((save.callsign, save.xp), ("Nyx", 150))
        self.assertEqual(GameSession(self.paths).snapshot()["story"], FRESH)

        # Ids a newer game wrote are kept; junk is ignored; other keys of `seen` survive a write.
        self.paths.save_path.write_text(json.dumps({**legacy, "seen": {
            "story": ["intro:1", 5, "chapter:9", "intro:1"], "lore": ["x"]}}), encoding="utf-8")
        session = GameSession(self.paths)
        self.assertEqual(session.snapshot()["story"], {**FRESH, "intros": [1]})
        session.mark_story_seen("epilogue")
        on_disk = json.loads(self.paths.save_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["seen"], {"story": ["intro:1", "chapter:9", "intro:1", "epilogue"], "lore": ["x"]})
        self.assertEqual(session.snapshot()["story"], {**FRESH, "intros": [1], "epilogue": True})

        # A `seen` of the wrong shape is reset alone, keeping the rest of the progress.
        self.paths.save_path.write_text(json.dumps({**legacy, "seen": ["prologue"]}), encoding="utf-8")
        session = GameSession(self.paths)
        self.assertEqual(session.snapshot()["story"], FRESH)
        self.assertEqual(session.snapshot()["profile"]["callsign"], "Nyx")

    def test_rendered_media_is_offered_only_when_the_file_exists(self):
        self.paths.cutscene_dir.mkdir(parents=True, exist_ok=True)
        key = story_content.media_id("intro:1")
        (self.paths.cutscene_dir / f"{key}_still.png").write_bytes(b"\x89PNG")
        self.assertEqual(self.session.story("intro-1")["media"], {"url": f"/cutscenes/{key}_still.png", "kind": "image"})
        (self.paths.cutscene_dir / f"{key}_cinematic.mp4").write_bytes(b"mp4")
        self.assertEqual(self.session.story("intro-1")["media"], {"url": f"/cutscenes/{key}_cinematic.mp4", "kind": "video"})
        self.assertIsNone(self.session.story("intro-2")["media"])
        # A gallery entry whose file is gone is not offered.
        prologue = story_content.media_id("prologue")
        gone = {"mission": prologue, "title": "x", "url": "https://cdn.example/still.png", "kind": "image",
                "path": str(self.paths.cutscene_dir / f"{prologue}_still.png")}
        self.session.save.gallery = [gone]
        self.assertIsNone(self.session.story("prologue")["media"])
        (self.paths.cutscene_dir / f"{prologue}_still.png").write_bytes(b"\x89PNG")
        self.assertEqual(self.session.story("prologue")["media"], {"url": f"/cutscenes/{prologue}_still.png", "kind": "image"})

    def test_reward_carries_the_profile_before_the_clear(self):
        self.session.deploy("L01")
        self.session.write_source("L01", SOLUTION)
        first = self.session.attack("L01")
        assert_hack_result(self, first)
        self.assertEqual((first["reward"]["xp_before"], first["reward"]["callsign_before"]), (0, ""))
        self.assertEqual(first["reward"]["callsign"], "Nyx")
        replay = self.session.attack("L01")
        assert_hack_result(self, replay)
        self.assertTrue(replay["reward"]["replay"])
        self.assertEqual((replay["reward"]["xp_before"], replay["reward"]["callsign_before"]), (150, "Nyx"))


class StoryApiTests(ServerTestCase):
    def test_get_every_story_event(self):
        for api_id in STORY_IDS:
            with self.subTest(api_id=api_id):
                resp = self.request("GET", f"/api/story/{api_id}")
                self.assertEqual(resp.status, 200)
                self.assertEqual(resp.headers["Content-Type"], "application/json; charset=utf-8")
                self.assertEqual(resp.headers["Cache-Control"], "no-store")
                assert_story(self, resp.json())
        assert_state(self, self.request("GET", "/api/state").json())

    def test_unknown_events_and_wrong_methods(self):
        for method, path, status in (("GET", "/api/story/nope", 404), ("GET", "/api/story/intro-5", 404),
                                     ("GET", "/api/story/seen", 404), ("GET", "/api/story/%2e%2e", 404),
                                     ("GET", "/api/story/", 404), ("GET", "/api/story/" + "a" * 40, 404),
                                     ("POST", "/api/story/prologue", 405), ("DELETE", "/api/story/seen", 405)):
            with self.subTest(method=method, path=path):
                resp = self.request(method, path, {} if method == "POST" else None)
                self.assertEqual(resp.status, status)
                self.assertEqual(set(resp.json()), {"error"})

    def test_mark_seen_round_trip(self):
        resp = self.request("POST", "/api/story/seen", {"id": "intro-0"})
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.json(), {"ok": True, "id": "intro-0", "story": {**FRESH, "intros": [0]}})
        self.assertEqual(self.request("POST", "/api/story/seen", {"id": "intro-0"}).json()["story"]["intros"], [0])
        self.assertEqual(self.request("GET", "/api/state").json()["story"], {**FRESH, "intros": [0]})
        self.assertTrue(self.request("GET", "/api/story/intro-0").json()["seen"])

    def test_mark_seen_rejects_bad_bodies(self):
        for body, status in (({}, 400), ({"id": 3}, 400), ([], 400), ("null", 400), ("{bad", 400),
                             ({"id": "nope"}, 404), ({"id": "../save.json"}, 404)):
            with self.subTest(body=body):
                resp = self.request("POST", "/api/story/seen", body)
                self.assertEqual(resp.status, status)
                self.assertEqual(set(resp.json()), {"error"})
        self.assertEqual(self.request("GET", "/api/state").json()["story"], FRESH)

    def test_story_routes_need_the_token_and_host(self):
        for method, path, body in (("GET", "/api/story/prologue", None), ("POST", "/api/story/seen", {"id": "prologue"})):
            with self.subTest(path=path):
                self.assertEqual(self.request(method, path, body, token=None).status, 401)
                self.assertEqual(self.request(method, path, body, token="nope").status, 403)
                self.assertEqual(self.request(method, path, body, host="evil.example").status, 403)
        self.assertEqual(self.session.snapshot()["story"], FRESH, "an unauthorised request marked nothing")


if __name__ == "__main__":
    unittest.main()
