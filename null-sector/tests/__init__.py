"""Shared test support: an isolated game sandbox and the exact §3.3 payload shapes.

Every test runs against `Paths.rooted(<temp dir>)`, so save.json, config.json,
missions/ and cutscenes/ are created in a throwaway folder and the real game
files are never read or written. Higgsfield credentials are scrubbed from the
environment so the cutscene feed is deterministically offline unless a test
fakes it.

Run from the game folder:  python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import cinematics  # noqa: E402
from engine.cinematics import CutsceneRenderer  # noqa: E402
from engine.session import GameSession  # noqa: E402
from engine.state import Paths  # noqa: E402
from levels import load_mission  # noqa: E402

HF_ENV = ("HF_KEY", "HF_API_KEY", "HF_API_SECRET")

# A correct Level 1 solution.
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
STARTER = load_mission("level_01_cold_boot").starter.lstrip("\n")


class SandboxTestCase(unittest.TestCase):
    """Gives each test a fresh GameSession rooted in its own temp directory."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="ns-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.paths = Paths.rooted(self.root)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for key in HF_ENV:
            os.environ.pop(key, None)
        self.session = GameSession(self.paths)

    def mission_file(self, name: str = "level_01_cold_boot.py") -> Path:
        return self.paths.missions_dir / name


# ── a fake Higgsfield (no network, no SDK needed) ───────────
class FakeHiggsfield:
    """Stands in for higgsfield_client.SyncClient: records calls, returns canned media URLs."""

    def __init__(self, reject_reference: bool = False, fail: str | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.reject_reference = reject_reference
        self.fail = fail

    def subscribe(self, model: str, args: dict) -> dict:
        self.calls.append((model, dict(args)))
        stage = "video" if "dop" in model else "still"
        if self.fail == stage:
            raise RuntimeError(f"{stage} quota exhausted")
        if self.reject_reference and "image_url" in args:
            raise RuntimeError("reference not supported")
        if stage == "video":
            return {"video": {"url": "https://cdn.example/render/clip.mp4"}}
        return {"images": [{"url": f"https://cdn.example/render/still{len(self.calls)}.png"}]}


def fake_httpx(payload: bytes = b"\x89PNG fake"):
    """A stand-in `httpx` module whose get() returns `payload` with a content type from the URL."""

    def get(url, **_kwargs):
        ctype = "video/mp4" if url.endswith(".mp4") else "image/png"
        return types.SimpleNamespace(content=payload, headers={"content-type": ctype},
                                     raise_for_status=lambda: None)

    return types.SimpleNamespace(get=get)


def online_higgsfield(test: unittest.TestCase, client: FakeHiggsfield) -> None:
    """Make every CutsceneRenderer in this test talk to `client` (no network, no real SDK needed)."""
    os.environ["HF_KEY"] = "test-key:test-secret"
    for patcher in (mock.patch.object(cinematics, "_SDK_STATUS", (True, "online")),
                    mock.patch.object(CutsceneRenderer, "_client", lambda self: client),
                    mock.patch.dict(sys.modules, {"httpx": fake_httpx()})):
        patcher.start()
        test.addCleanup(patcher.stop)


# ── payload shapes (docs/ARCHITECTURE.md §3.3) ──────────────
STATE_KEYS = {"profile", "campaign", "current", "higgsfield", "gallery"}
PROFILE_KEYS = {"callsign", "xp", "rank", "rank_floor", "rank_next", "breaches", "total_levels"}
SECTOR_KEYS = {"tier", "name", "zone", "color", "levels"}
LEVEL_KEYS = {"id", "title", "concept", "status", "boss"}
HIGGSFIELD_KEYS = {"online", "reason"}
GALLERY_KEYS = {"mission", "title", "url", "kind"}
MISSION_KEYS = {"id", "title", "concept", "tier", "sector", "enemy", "enemy_art", "xp", "par_seconds",
                "briefing_html", "why_html", "manual_html", "objectives", "file", "source", "attempts",
                "elapsed", "cleared", "cutscene", "difficulty_tier", "concepts", "boss", "dialogue"}
MISSION_SECTOR_KEYS = {"name", "zone", "color"}
CUTSCENE_KEYS = {"title", "narration"}
HACK_KEYS = {"report", "attempt", "victory", "reward", "next", "state"}
REPORT_KEYS = {"status", "checks", "stdout", "error"}
CHECK_KEYS = {"name", "passed", "message", "hint"}
ERROR_KEYS = {"type", "message", "line", "code", "traceback", "decoded"}
REWARD_KEYS = {"lines", "gained", "rank_before", "rank_after", "rank_up", "breach_seconds", "attempts",
               "callsign", "replay"}
REWARD_LINE_KEYS = {"label", "amount"}
NEXT_KEYS = {"id", "title", "concept", "status"}
LEVEL_STATUSES = {"cleared", "current", "encrypted", "locked"}
REPORT_STATUSES = {"ok", "crash", "syntax_error", "timeout", "harness_error"}


def assert_state(tc: unittest.TestCase, state: dict) -> None:
    tc.assertEqual(set(state), STATE_KEYS)
    profile = state["profile"]
    tc.assertEqual(set(profile), PROFILE_KEYS)
    tc.assertIsInstance(profile["callsign"], str)
    for key in ("xp", "rank_floor", "breaches", "total_levels"):
        tc.assertIsInstance(profile[key], int, key)
    tc.assertIsInstance(profile["rank"], str)
    tc.assertTrue(profile["rank_next"] is None or isinstance(profile["rank_next"], int))
    tc.assertEqual(len(state["campaign"]), 5)
    for sector in state["campaign"]:
        tc.assertEqual(set(sector), SECTOR_KEYS)
        tc.assertRegex(sector["color"], r"^#[0-9a-f]{6}$")
        for level in sector["levels"]:
            tc.assertEqual(set(level), LEVEL_KEYS)
            tc.assertIn(level["status"], LEVEL_STATUSES)
            tc.assertIsInstance(level["boss"], bool)
    tc.assertTrue(state["current"] is None or isinstance(state["current"], str))
    tc.assertEqual(set(state["higgsfield"]), HIGGSFIELD_KEYS)
    tc.assertIsInstance(state["higgsfield"]["online"], bool)
    tc.assertIsInstance(state["higgsfield"]["reason"], str)
    for entry in state["gallery"]:
        tc.assertEqual(set(entry), GALLERY_KEYS)
        tc.assertIn(entry["kind"], ("image", "video"))


def assert_mission(tc: unittest.TestCase, mission: dict) -> None:
    tc.assertEqual(set(mission), MISSION_KEYS)
    tc.assertEqual(set(mission["sector"]), MISSION_SECTOR_KEYS)
    for key in ("xp", "par_seconds", "tier", "attempts"):
        tc.assertIsInstance(mission[key], int, key)
    tc.assertIsInstance(mission["elapsed"], float)
    tc.assertIsInstance(mission["cleared"], bool)
    tc.assertIsInstance(mission["difficulty_tier"], int)
    tc.assertIsInstance(mission["boss"], bool)
    tc.assertIsInstance(mission["concepts"], list)
    tc.assertTrue(all(isinstance(tag, str) for tag in mission["concepts"]))
    tc.assertIsInstance(mission["dialogue"], dict)
    for key in ("briefing_html", "why_html", "manual_html", "source", "file", "enemy", "enemy_art"):
        tc.assertIsInstance(mission[key], str, key)
    tc.assertTrue(all(isinstance(o, str) for o in mission["objectives"]))
    if mission["cutscene"] is not None:
        tc.assertEqual(set(mission["cutscene"]), CUTSCENE_KEYS)
        tc.assertTrue(all(isinstance(line, str) for line in mission["cutscene"]["narration"]))


def assert_hack_result(tc: unittest.TestCase, result: dict) -> None:
    tc.assertEqual(set(result), HACK_KEYS)
    report = result["report"]
    tc.assertEqual(set(report), REPORT_KEYS)
    tc.assertIn(report["status"], REPORT_STATUSES)
    tc.assertIsInstance(report["stdout"], str)
    for check in report["checks"]:
        tc.assertEqual(set(check), CHECK_KEYS)
        tc.assertIsInstance(check["passed"], bool)
    if report["error"] is None:
        tc.assertEqual(report["status"], "ok")
    else:
        tc.assertEqual(set(report["error"]), ERROR_KEYS)
        tc.assertTrue(report["error"]["decoded"])
    tc.assertIsInstance(result["attempt"], int)
    tc.assertIsInstance(result["victory"], bool)
    if result["victory"]:
        reward = result["reward"]
        tc.assertEqual(set(reward), REWARD_KEYS)
        for line in reward["lines"]:
            tc.assertEqual(set(line), REWARD_LINE_KEYS)
        tc.assertEqual(reward["gained"], sum(line["amount"] for line in reward["lines"]))
        if result["next"] is not None:
            tc.assertEqual(set(result["next"]), NEXT_KEYS)
    else:
        tc.assertIsNone(result["reward"])
        tc.assertIsNone(result["next"])
    assert_state(tc, result["state"])
