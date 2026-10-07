"""GameSession rules, the markdown pipeline, the cutscene renderer and the terminal front end.

Everything runs inside a per-test temp directory (see tests/__init__.py).
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import (SOLUTION, STARTER, FakeHiggsfield, SandboxTestCase, assert_hack_result,  # noqa: E402
                   assert_mission, assert_state, online_higgsfield)

from engine import cinematics, state as state_module  # noqa: E402
from engine.cinematics import _first_url, entry_kind  # noqa: E402
from engine.content import highlight_code, render_markdown  # noqa: E402
from engine.mission import Cutscene  # noqa: E402
from engine.runner import HackReport  # noqa: E402
from engine.session import PROFILE_EXPORTS, GameSession, SessionError, clean_callsign  # noqa: E402
from engine.state import Paths, Save  # noqa: E402
from levels import load_mission  # noqa: E402

L01 = load_mission("level_01_cold_boot")


def level_status(state: dict, level_id: str) -> str:
    return next(lvl["status"] for sector in state["campaign"] for lvl in sector["levels"] if lvl["id"] == level_id)


class PathsTests(SandboxTestCase):
    def test_defaults_are_the_real_game_folders(self):
        paths = Paths()
        self.assertEqual(paths.game_dir, state_module.GAME_DIR)
        self.assertEqual(paths.missions_dir, state_module.MISSIONS_DIR)
        self.assertEqual(paths.save_path, state_module.SAVE_PATH)
        self.assertEqual(paths.config_path, state_module.CONFIG_PATH)
        self.assertEqual(paths.cutscene_dir, state_module.CUTSCENE_DIR)

    def test_rooted_session_writes_only_inside_its_root(self):
        for location in (self.paths.missions_dir, self.paths.save_path, self.paths.config_path,
                         self.paths.cutscene_dir):
            self.assertTrue(location.is_relative_to(self.root), location)
        self.session.deploy("L01")
        self.session.attack("L01")
        written = {p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(written, {"config.json", "save.json", "missions/level_01_cold_boot.py"})

    def test_save_writes_are_atomic_and_leave_no_temp_files(self):
        self.session.deploy("L01")
        for _ in range(3):
            self.session.save.record_attempt("L01")
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".")], [])
        reloaded = Save.load(self.paths.save_path)
        self.assertEqual(reloaded.attempts["L01"], 3)
        self.assertEqual(reloaded.path, self.paths.save_path)


class SnapshotTests(SandboxTestCase):
    def test_fresh_profile(self):
        with mock.patch.object(cinematics, "_SDK_STATUS", (True, "online")):   # SDK installed, no key
            state = self.session.snapshot()
        assert_state(self, state)
        self.assertEqual(state["profile"], {"callsign": "", "xp": 0, "rank": "GHOST PROCESS", "rank_floor": 0,
                                            "rank_next": 100, "breaches": 0, "total_levels": 25})
        self.assertEqual(state["current"], "L01")
        self.assertEqual(level_status(state, "L01"), "current")
        self.assertEqual(level_status(state, "L02"), "locked")
        self.assertEqual(state["higgsfield"], {"online": False, "reason": "no API key in config.json"})
        self.assertEqual(state["gallery"], [])
        bosses = [lvl["id"] for s in state["campaign"] for lvl in s["levels"] if lvl["boss"]]
        self.assertEqual(bosses, ["L05", "L10", "L15", "L20", "L25"])

    def test_payloads_are_json_serialisable(self):
        json.dumps(self.session.snapshot())
        json.dumps(self.session.mission("L01"))


class MissionTests(SandboxTestCase):
    def test_mission_is_read_only(self):
        mission = self.session.mission("L01")
        assert_mission(self, mission)
        self.assertFalse(self.mission_file().exists(), "mission() must not create the file")
        self.assertNotIn("L01", self.session.save.started_at)
        self.assertEqual(mission["source"], STARTER)
        self.assertEqual(mission["file"], "missions/level_01_cold_boot.py")
        self.assertEqual(mission["elapsed"], 0.0)
        self.assertEqual(mission["attempts"], 0)
        self.assertFalse(mission["cleared"])
        self.assertEqual(mission["sector"], {"name": "ZERO", "zone": "The Dead Zone", "color": "#39ff14"})
        self.assertEqual(mission["cutscene"]["title"], "IDENTITY ACCEPTED")
        self.assertEqual(len(mission["objectives"]), 7)
        self.assertEqual(mission["objectives"][0], "Register identity — `callsign`")   # backticks kept
        self.assertIn("<strong>WATCHDOG.exe</strong>", mission["briefing_html"])
        self.assertIn('<pre class="code"><code class="language-python">', mission["manual_html"])

    def test_deploy_writes_starter_and_starts_the_timer_once(self):
        mission = self.session.deploy("L01")
        assert_mission(self, mission)
        self.assertEqual(self.mission_file().read_text(encoding="utf-8"), STARTER)
        self.assertLess(time.time() - self.session.save.started_at["L01"], 5)
        started = self.session.save.started_at["L01"] = time.time() - 30   # half a minute into the mission
        self.session.write_source("L01", "x = 1\n")
        again = self.session.deploy("L01")
        self.assertEqual(self.session.save.started_at["L01"], started, "the par timer must start only once")
        self.assertEqual(again["source"], "x = 1\n", "deploy must never overwrite the player's work")
        self.assertGreaterEqual(again["elapsed"], 30.0)

    def test_write_source_then_hack(self):
        self.session.deploy("L01")
        result = self.session.write_source("L01", SOLUTION.replace("\n", "\r\n"))
        self.assertEqual(set(result), {"ok", "saved_at"})
        self.assertIs(result["ok"], True)
        self.assertIsInstance(result["saved_at"], float)
        self.assertAlmostEqual(result["saved_at"], self.mission_file().stat().st_mtime, places=3)
        self.assertEqual(self.mission_file().read_bytes(), SOLUTION.encode(), "CRLF is normalised to LF")
        self.assertEqual(self.session.mission("L01")["source"], SOLUTION)
        self.assertTrue(self.session.attack("L01")["victory"])

    def test_write_source_rejects_non_strings(self):
        with self.assertRaises(SessionError) as ctx:
            self.session.write_source("L01", b"bytes")
        self.assertEqual(ctx.exception.status, 400)

    def test_reset_restores_the_starter(self):
        self.session.deploy("L01")
        self.session.write_source("L01", "garbage\n")
        self.assertEqual(self.session.reset("L01"), {"source": STARTER})
        self.assertEqual(self.mission_file().read_text(encoding="utf-8"), STARTER)


class AccessTests(SandboxTestCase):
    CALLS = {
        "mission": lambda s, i: s.mission(i),
        "deploy": lambda s, i: s.deploy(i),
        "write_source": lambda s, i: s.write_source(i, "x = 1\n"),
        "attack": lambda s, i: s.attack(i),
        "reset": lambda s, i: s.reset(i),
    }

    def assert_refused(self, mission_id, status: int) -> None:
        for name, call in self.CALLS.items():
            with self.subTest(method=name, mission=mission_id), self.assertRaises(SessionError) as ctx:
                call(self.session, mission_id)
            self.assertEqual(ctx.exception.status, status)
            self.assertTrue(ctx.exception.message)

    def test_unknown_ids_are_404(self):
        for bad in ("L99", "", "l01", "../L01", None):
            self.assert_refused(bad, 404)
            self.assertFalse(self.session.playable(bad))

    def test_locked_levels_are_403(self):
        self.assert_refused("L03", 403)
        self.assert_refused("L25", 403)
        self.assertFalse(self.session.playable("L02"))
        self.assertTrue(self.session.playable("L01"))

    def test_encrypted_next_level_is_not_playable(self):
        self.session.deploy("L01")
        self.session.write_source("L01", SOLUTION)
        self.session.attack("L01")
        self.assertEqual(level_status(self.session.snapshot(), "L02"), "encrypted")
        self.assert_refused("L02", 403)
        self.assertFalse(self.session.playable("L02"))
        self.assertTrue(self.session.playable("L01"), "cleared levels stay playable")
        self.assertFalse(any(p.name != "level_01_cold_boot.py" for p in self.paths.missions_dir.iterdir()))


class CombatTests(SandboxTestCase):
    def hack(self) -> dict:
        result = self.session.attack("L01")
        assert_hack_result(self, result)
        return result

    def test_starter_crashes_for_zero_xp(self):
        self.session.deploy("L01")
        result = self.hack()
        report = result["report"]
        self.assertEqual(report["status"], "crash")
        self.assertEqual(report["error"]["type"], "TypeError")
        self.assertIsInstance(report["error"]["line"], int)
        self.assertIn("scrap_from_crate + 8", report["error"]["code"])
        self.assertIn("int(", report["error"]["decoded"])
        self.assertEqual(len(report["checks"]), 7)
        self.assertFalse(any(c["passed"] for c in report["checks"]))
        self.assertFalse(result["victory"])
        self.assertEqual(result["attempt"], 1)
        self.assertEqual(result["state"]["profile"]["xp"], 0)
        self.assertEqual(self.session.save.xp, 0)
        self.assertEqual(self.session.mission("L01")["attempts"], 1)

    def test_correct_solution_is_a_victory_with_speed_bonus(self):
        self.session.deploy("L01")
        self.hack()                                   # attempt 1: the starter crash
        self.session.write_source("L01", SOLUTION)
        result = self.hack()
        self.assertEqual(result["report"]["status"], "ok")
        self.assertIsNone(result["report"]["error"])
        self.assertEqual(result["report"]["stdout"], "Nyx online\n")
        self.assertTrue(all(c["passed"] for c in result["report"]["checks"]))
        self.assertTrue(result["victory"])
        self.assertEqual(result["attempt"], 2)
        reward = result["reward"]
        self.assertEqual(reward["lines"], [{"label": "BASE XP", "amount": 100},
                                           {"label": "SPEED BONUS", "amount": 50}])
        self.assertEqual(reward["gained"], 150)
        self.assertEqual((reward["rank_before"], reward["rank_after"], reward["rank_up"]),
                         ("GHOST PROCESS", "SCRIPT KIDDIE", True))
        self.assertEqual(reward["callsign"], "Nyx")
        self.assertEqual(reward["attempts"], 2)
        self.assertIs(reward["replay"], False)
        self.assertLessEqual(reward["breach_seconds"], L01.par_seconds)
        self.assertEqual(result["next"], {"id": "L02", "title": "SIGNAL NOISE",
                                          "concept": "Strings & cleaning text", "status": "encrypted"})
        state = result["state"]
        self.assertEqual(state["profile"], {"callsign": "Nyx", "xp": 150, "rank": "SCRIPT KIDDIE", "rank_floor": 100,
                                            "rank_next": 400, "breaches": 1, "total_levels": 25})
        self.assertEqual(state["current"], "L02")
        self.assertEqual(level_status(state, "L01"), "cleared")
        self.assertEqual(level_status(state, "L02"), "encrypted")
        self.assertTrue(self.session.mission("L01")["cleared"])

        saved = Save.load(self.paths.save_path)       # persisted, not just in memory
        self.assertEqual((saved.callsign, saved.xp), ("Nyx", 150))
        self.assertEqual(saved.cleared["L01"]["xp"], 150)
        self.assertEqual(saved.cleared["L01"]["attempts"], 2)

    def test_over_par_has_no_speed_bonus(self):
        self.session.deploy("L01")
        self.session.save.started_at["L01"] = time.time() - L01.par_seconds - 5
        self.session.write_source("L01", SOLUTION)
        reward = self.hack()["reward"]
        self.assertEqual(reward["lines"], [{"label": "BASE XP", "amount": 100}])
        self.assertEqual(reward["gained"], 100)
        self.assertGreater(reward["breach_seconds"], L01.par_seconds)
        self.assertEqual(reward["rank_after"], "SCRIPT KIDDIE")

    def test_hacking_without_deploying_still_starts_the_clock(self):
        self.session.write_source("L01", SOLUTION)
        result = self.hack()
        self.assertTrue(result["victory"])
        self.assertIn("L01", self.session.save.started_at)
        self.assertEqual(result["reward"]["gained"], 150)

    def test_replay_grants_no_xp(self):
        self.session.deploy("L01")
        self.session.write_source("L01", SOLUTION)
        first = self.hack()
        record = dict(self.session.save.cleared["L01"])
        replay = self.hack()
        self.assertTrue(replay["victory"])
        reward = replay["reward"]
        self.assertIs(reward["replay"], True)
        self.assertEqual((reward["gained"], reward["lines"]), (0, []))
        self.assertEqual(reward["rank_before"], reward["rank_after"])
        self.assertIs(reward["rank_up"], False)
        self.assertEqual(reward["breach_seconds"], first["reward"]["breach_seconds"])
        self.assertEqual(replay["state"]["profile"]["xp"], 150)
        self.assertEqual(self.session.save.cleared["L01"], record, "the first-clear record is never rewritten")
        self.assertEqual(replay["attempt"], 2)

    def test_callsign_export_flows_into_the_profile(self):
        self.session.write_source("L01", SOLUTION.replace('"Nyx"', '"  Zero Cool  "'))
        result = self.hack()
        self.assertEqual(result["reward"]["callsign"], "Zero Cool")
        self.assertEqual(result["state"]["profile"]["callsign"], "Zero Cool")

    def test_only_whitelisted_exports_reach_the_profile(self):
        self.assertEqual(PROFILE_EXPORTS, {"callsign"})
        forged = HackReport("ok", [{"name": "layer", "passed": True, "message": "", "hint": ""}], "", None,
                            {"callsign": "Ghost\x1b[31m\x00", "xp": 999999, "cleared": {}})
        with mock.patch("engine.session.hack", return_value=forged):
            result = self.hack()
        self.assertEqual(result["state"]["profile"]["xp"], 150)
        self.assertEqual(result["state"]["profile"]["callsign"], "Ghost[31m")

    def test_failed_layers_are_not_a_victory(self):
        self.session.write_source("L01", SOLUTION.replace("integrity = 100", "integrity = 99"))
        result = self.hack()
        self.assertEqual(result["report"]["status"], "ok")
        self.assertIsNone(result["report"]["error"])
        self.assertFalse(result["victory"])
        failed = [c for c in result["report"]["checks"] if not c["passed"]]
        self.assertEqual([c["name"] for c in failed], ["Frame integrity — `integrity`"])
        self.assertIn("100", failed[0]["message"])

    def test_syntax_error_is_decoded(self):
        self.session.write_source("L01", 'callsign = "Nyx\n')
        report = self.hack()["report"]
        self.assertEqual(report["status"], "syntax_error")
        self.assertEqual(report["error"]["type"], "SyntaxError")
        self.assertEqual(report["error"]["line"], 1)
        self.assertIn("quote", report["error"]["decoded"])

    def test_infinite_loop_times_out(self):
        self.session.write_source("L01", "while True:\n    pass\n")
        with mock.patch.object(L01, "timeout", 1.0):
            report = self.hack()["report"]
        self.assertEqual(report["status"], "timeout")
        self.assertEqual(report["error"]["type"], "Timeout")
        self.assertIn("loop", report["error"]["decoded"])

    def test_huge_output_is_truncated(self):
        self.session.write_source("L01", 'print("x" * 200_000)\n')
        stdout = self.hack()["report"]["stdout"]
        self.assertLess(len(stdout), 70_000)
        self.assertIn("truncated", stdout.splitlines()[0])

    def test_concurrent_hacks_pay_out_once(self):
        self.session.deploy("L01")
        self.session.write_source("L01", SOLUTION)
        results: list[dict] = []
        threads = [threading.Thread(target=lambda: results.append(self.session.attack("L01"))) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(len(results), 3)
        self.assertEqual(sorted(r["reward"]["replay"] for r in results), [False, True, True])
        self.assertEqual(self.session.save.xp, 150)
        self.assertEqual(sorted(r["attempt"] for r in results), [1, 2, 3])

    def test_progress_survives_a_restart(self):
        self.session.write_source("L01", SOLUTION)
        self.hack()
        reborn = GameSession(self.paths)
        state = reborn.snapshot()
        self.assertEqual(state["profile"]["xp"], 150)
        self.assertEqual(state["current"], "L02")


class CallsignTests(unittest.TestCase):
    def test_clean_callsign(self):
        self.assertEqual(clean_callsign("  Nyx  "), "Nyx")
        self.assertEqual(clean_callsign("a\tb\nc"), "abc")
        self.assertEqual(clean_callsign("x" * 40), "x" * 24)
        self.assertEqual(clean_callsign(42), "")
        self.assertEqual(clean_callsign("\x00\x07"), "")


class ContentTests(unittest.TestCase):
    def test_raw_html_is_escaped(self):
        html = render_markdown("Hi <script>alert(1)</script> <img src=x onerror=alert(1)>\n\n<div>block</div>")
        self.assertNotIn("<script", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("<div", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;div&gt;block&lt;/div&gt;", html)

    def test_inline_markup(self):
        html = render_markdown("**bold** *em* `code` [link](https://example.com) [bad](javascript:alert(1))")
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<em>em</em>", html)
        self.assertIn("<code>code</code>", html)
        self.assertIn('<a href="https://example.com" target="_blank" rel="noopener noreferrer">', html)
        self.assertNotIn('href="javascript', html)

    def test_python_fences_are_highlighted(self):
        source = 'def f(x):\n    # note\n    return print(int("12") + 3.5 * x - 1)\n'
        html = render_markdown(f"```python\n{source}```")
        self.assertTrue(html.startswith('<pre class="code"><code class="language-python">'))
        self.assertTrue(html.endswith("</code></pre>"))
        for cls in ("tk-k", "tk-nf", "tk-c1", "tk-nb", "tk-s2", "tk-mi", "tk-mf", "tk-o"):
            self.assertIn(f'class="{cls}"', html, cls)
        self.assertIn('<span class="tk-k">def</span>', html)
        self.assertIn('<span class="tk-c1"># note</span>', html)

    def test_fence_code_is_escaped(self):
        html = render_markdown('```python\nx = "<b>&"\n```')
        self.assertNotIn("<b>", html)
        self.assertIn("&lt;b&gt;&amp;", html)
        plain = render_markdown("```\n<i>raw</i>\n```")
        self.assertEqual(plain, '<pre class="code"><code>&lt;i&gt;raw&lt;/i&gt;</code></pre>')

    def test_unknown_language_falls_back_to_escaped_text(self):
        html = highlight_code("<x>", "no-such-language")
        self.assertEqual(html, '<pre class="code"><code class="language-no-such-language">&lt;x&gt;</code></pre>')

    def test_results_are_cached(self):
        text = "Cache me: `x = 1`"
        first = render_markdown(text)
        hits = render_markdown.cache_info().hits
        self.assertIs(render_markdown(text), first)
        self.assertEqual(render_markdown.cache_info().hits, hits + 1)


class CutsceneRendererTests(SandboxTestCase):
    SCENE = Cutscene(title="SCENE", narration=["..."], shot="a shot", camera="slow orbit")

    def test_status_offline_without_credentials(self):
        with mock.patch.object(cinematics, "_SDK_STATUS", (True, "online")):
            self.assertEqual(self.session.cinema.status(), (False, "no API key in config.json"))
        with mock.patch.object(cinematics, "_SDK_STATUS", (False, "higgsfield-client not installed")):
            os.environ["HF_KEY"] = "k:s"
            self.assertEqual(self.session.cinema.status(), (False, "higgsfield-client not installed"))

    def test_anchor_still_then_video_with_progress(self):
        client = FakeHiggsfield()
        online_higgsfield(self, client)
        self.session.config["higgsfield"]["video_enabled"] = True
        events = []
        anchor = Cutscene(title="IDENTITY", narration=[], shot="portrait", camera="dolly-in", anchor=True)
        entries = self.session.cinema.render(anchor, "L01", on_progress=lambda *a, **k: events.append((a, k)))
        self.assertEqual([(a[0], a[1]) for a, _ in events],
                         [("still", "rendering"), ("still", "done"), ("video", "rendering"), ("video", "done")])
        self.assertEqual([e["kind"] for e in entries], ["image", "video"])
        still, video = entries
        self.assertEqual(Path(still["path"]), self.paths.cutscene_dir / "L01_still.png")
        self.assertEqual(Path(video["path"]), self.paths.cutscene_dir / "L01_cinematic.mp4")
        self.assertEqual(self.session.save.avatar_url, still["url"], "the anchor still becomes the avatar")
        (image_model, image_args), (video_model, video_args) = client.calls
        self.assertNotIn("image_url", image_args, "an anchor shot is rendered without a reference")
        self.assertIn("The hero:", image_args["prompt"])
        self.assertEqual(video_args["image_url"], still["url"])
        self.assertIn("Camera: dolly-in", video_args["prompt"])
        self.assertTrue(self.session.cinema.is_rendered("L01"))
        # A second render is free: every stage is already on file.
        self.session.cinema.render(anchor, "L01")
        self.assertEqual(len(client.calls), 2)
        gallery = self.session.snapshot()["gallery"]
        self.assertEqual([(g["url"], g["kind"]) for g in gallery],
                         [("/cutscenes/L01_still.png", "image"), ("/cutscenes/L01_cinematic.mp4", "video")])

    def test_rejected_reference_falls_back_to_the_character_bible(self):
        client = FakeHiggsfield(reject_reference=True)
        online_higgsfield(self, client)
        self.session.save.avatar_url = "https://cdn.example/avatar.png"
        events = []
        self.session.cinema.render(self.SCENE, "L01", on_progress=lambda *a, **k: events.append((a, k)))
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0][1]["image_url"], "https://cdn.example/avatar.png")
        self.assertNotIn("image_url", client.calls[1][1])
        self.assertIn(("still", "fallback"), [(a[0], a[1]) for a, _ in events])

    def test_failed_stage_raises_and_reports(self):
        online_higgsfield(self, FakeHiggsfield(fail="still"))
        events = []
        with self.assertRaises(cinematics.CutsceneError) as ctx:
            self.session.cinema.render(self.SCENE, "L01", on_progress=lambda *a, **k: events.append((a, k)))
        self.assertEqual(ctx.exception.stage, "still")
        self.assertEqual(events[-1][0][:2], ("still", "failed"))
        self.assertIn("quota", events[-1][1]["error"])
        self.assertEqual(self.session.save.gallery, [])

    def test_first_url_and_entry_kind(self):
        self.assertEqual(_first_url({"images": [{"url": "https://a/b.png"}]}), "https://a/b.png")
        self.assertEqual(_first_url({"data": {"outputs": [{"x": 1}, "https://a/v.mp4"]}}), "https://a/v.mp4")
        with self.assertRaises(ValueError):
            _first_url({"status": "queued"})
        self.assertEqual(entry_kind({"path": "/x/L01_cinematic.mp4"}), "video")
        self.assertEqual(entry_kind({"url": "https://a/still.png"}), "image")
        self.assertEqual(entry_kind({"title": "SCENE (cinematic)", "url": "https://a/x"}), "video")
        self.assertEqual(entry_kind({"kind": "image", "url": "https://a/x.mp4"}), "image")


class TerminalFrontEndTests(SandboxTestCase):
    """The Rich TUI must play exactly as before, with GameSession deciding every reward."""

    def run_tui(self, command: str, inputs=()) -> str:
        from engine import tui

        answers = iter(inputs)

        def fake_input(*_args):
            try:
                return next(answers)
            except StopIteration:
                raise EOFError from None

        out = io.StringIO()
        with mock.patch("builtins.input", fake_input), contextlib.redirect_stdout(out):
            tui.run(command, fast=True, session=self.session)
        return out.getvalue()

    def test_hack_command(self):
        text = self.run_tui("hack")
        self.assertIn("TARGET LOCKED", text)
        self.assertIn("COMBAT LOG", text)
        self.assertIn("TypeError", text)
        self.assertEqual(self.session.save.attempts["L01"], 1)
        self.assertEqual(self.session.save.xp, 0)

    def test_menu_deploy_hack_victory(self):
        self.session.write_source("L01", SOLUTION)
        # main menu: D(eploy) → mission menu: H(ack) → enter (play transmission) → enter → Q(uit)
        text = self.run_tui("tui", ["d", "h", "", "", "q"])
        for fragment in ("WATCHDOG.exe", "REWARDS", "SPEED BONUS", "+150", "RANK UP", "SCRIPT KIDDIE",
                         "TRANSMISSION // IDENTITY ACCEPTED", "visual feed offline", "SIGNAL NOISE",
                         "Jacking out"):
            self.assertIn(fragment, text)
        self.assertEqual(self.session.save.xp, 150)
        self.assertEqual(self.session.save.callsign, "Nyx")

    def test_reset_command(self):
        self.session.deploy("L01")
        self.session.write_source("L01", "garbage\n")
        self.run_tui("reset", ["y"])
        self.assertEqual(self.mission_file().read_text(encoding="utf-8"), STARTER)


if __name__ == "__main__":
    unittest.main()
