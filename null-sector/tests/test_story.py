"""levels/story.py: the prologue, the five act openings and the epilogue.

Checks the Cutscene contract (GAME_DESIGN §9), the event lookups the engine will call,
a clean import in a fresh process, and that every story cutscene fits the payload, the
terminal transmission and the Higgsfield prompt the engine already builds for
`Mission.cutscene`, without touching any engine file.

Run from the game folder:  python3 -m unittest tests.test_story -v
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import SandboxTestCase  # noqa: E402

from rich.console import Console  # noqa: E402

from engine import ui  # noqa: E402
from engine.mission import Cutscene  # noqa: E402
from levels import CAMPAIGN, load_mission  # noqa: E402
from levels import story  # noqa: E402

SPEAKERS = {"CIPHER", "VEX", "RUST", "NOVA", "ORACLE",
            "WARDEN", "ARBITER", "FORGEMASTER", "LIBRARIAN", "CORE"}
PALETTE = ("#05060a", "#0a0d14", "#00f0ff", "#ff2bd6", "#39ff14", "#ffb000", "#ff3355",
           "#8892a6", "#4a5160", "#b388ff")
TWIST_WORDS = ("operator-0", "training loop", "archived", "you built", "loom", "architect")
EXPECTED_EVENTS = ["prologue", "intro:0", "intro:1", "intro:2", "intro:3", "intro:4", "epilogue"]


class CutsceneContractTests(unittest.TestCase):
    def test_all_lists_every_event_in_play_order(self):
        self.assertEqual([event for event, _ in story.ALL], EXPECTED_EVENTS)
        self.assertEqual(list(story.EVENTS), EXPECTED_EVENTS)
        self.assertIs(dict(story.ALL)["prologue"], story.PROLOGUE)
        self.assertIs(dict(story.ALL)["epilogue"], story.EPILOGUE)
        for tier, cutscene in story.SECTOR_INTROS.items():
            self.assertIs(dict(story.ALL)[f"intro:{tier}"], cutscene)

    def test_every_cutscene_is_valid(self):
        titles = set()
        for event, cutscene in story.ALL:
            with self.subTest(event=event):
                self.assertIsInstance(cutscene, Cutscene)
                self.assertIsInstance(cutscene.title, str)
                self.assertTrue(cutscene.title.strip())
                self.assertEqual(cutscene.title, cutscene.title.upper(), "titles are display caps")
                self.assertNotIn("[", cutscene.title, "the title is inserted into Rich markup")
                titles.add(cutscene.title)
                self.assertIsInstance(cutscene.narration, list)
                self.assertTrue(3 <= len(cutscene.narration) <= 6, len(cutscene.narration))
                for line in cutscene.narration:
                    self.assertIsInstance(line, str)
                    self.assertTrue(line.strip())
                    self.assertEqual(line, line.strip())
                    self.assertLessEqual(len(line), 160, line)
                    # ui.transmission prints narration verbatim: no unfilled placeholders.
                    self.assertNotIn("{", line)
                    self.assertNotIn("}", line)
                self.assertIsInstance(cutscene.shot, str)
                self.assertGreater(len(cutscene.shot.strip()), 80, "a cinematographer's shot, not a caption")
                self.assertTrue(cutscene.camera.strip())
                self.assertFalse(cutscene.anchor, "L01 owns the avatar anchor")
                self.assertTrue(any(colour in cutscene.shot.lower() for colour in PALETTE),
                                "shots use the art-bible palette")
                self.assertRegex(cutscene.shot, r"\d+mm", "shots name a lens")
        self.assertEqual(len(titles), len(story.ALL), "titles are unique")

    def test_prologue_has_four_to_six_lines_and_hides_the_face(self):
        self.assertTrue(4 <= len(story.PROLOGUE.narration) <= 6)
        text = " ".join(story.PROLOGUE.narration)
        for beat in ("2089", "Null Event", "Dead Zone", "CIPHER", "No name. No memory."):
            self.assertIn(beat, text)
        # Played before L01 locks the avatar: the hero's face must not be shown.
        for cutscene in (story.PROLOGUE, story.SECTOR_INTROS[0]):
            self.assertNotIn("avatar reference", cutscene.shot)
            self.assertTrue(re.search(r"face (hidden|turned away)", cutscene.shot), cutscene.shot)

    def test_speakers_are_the_established_cast(self):
        for event, cutscene in story.ALL:
            for line in cutscene.narration:
                match = re.match(r"([A-Z][A-Z0-9.]+): ", line)
                if match:
                    with self.subTest(event=event, line=line):
                        self.assertIn(match.group(1), SPEAKERS)

    def test_sector_intros_cover_every_campaign_sector(self):
        self.assertEqual(sorted(story.SECTOR_INTROS), [0, 1, 2, 3, 4])
        self.assertEqual(sorted(story.SECTOR_INTROS), sorted(sector.tier for sector in CAMPAIGN))
        for sector in CAMPAIGN:
            self.assertIn("ACT ", story.SECTOR_INTROS[sector.tier].title)
        acts = ["COLD BOOT", "THE ORDER", "THE FORGE", "THE ARCHIVE", "ALIGNMENT"]
        for tier, name in enumerate(acts):
            self.assertIn(name, story.SECTOR_INTROS[tier].title)

    def test_each_act_ties_to_the_previous_boss(self):
        intros = {tier: " ".join(c.narration) for tier, c in story.SECTOR_INTROS.items()}
        self.assertIn("WATCHDOG", intros[0])
        self.assertIn("gate seals", intros[1])          # the WARDEN opened the Monastery (L05)
        self.assertIn("ARBITER", intros[2])             # beaten in L10
        self.assertIn("K-7F3A", intros[3])              # the Forgemaster's signature (L15)
        self.assertIn("Librarian", intros[4])           # the reveal (L20)
        self.assertIn("L15", [lvl.id for s in CAMPAIGN for lvl in s.levels])
        l15 = next(lvl for s in CAMPAIGN for lvl in s.levels if lvl.id == "L15")
        if l15.slug:   # keep the key in sync with the Forgemaster's own cutscene once it exists
            cutscene = load_mission(l15.slug).cutscene
            if cutscene is not None:
                self.assertIn("K-7F3A", " ".join(cutscene.narration))

    def test_the_twist_is_foreshadowed_then_revealed_then_paid_off(self):
        for event in ("prologue", "intro:0", "intro:1", "intro:2", "intro:3"):
            text = " ".join(story.cutscene_for(event).narration).lower()
            for word in TWIST_WORDS:
                with self.subTest(event=event, word=word):
                    self.assertNotIn(word, text, "the twist is only revealed from Act V's opening")
        act4 = " ".join(story.SECTOR_INTROS[3].narration)
        self.assertIn("CIPHER:", act4)
        self.assertIn("memory", act4)                   # pressed hard, not yet stated
        act5 = " ".join(story.SECTOR_INTROS[4].narration).lower()
        for beat in ("operator-0", "training loop", "you built it", "archived"):
            self.assertIn(beat, act5)
        epilogue = " ".join(story.EPILOGUE.narration)
        for beat in ("CIPHER:", "part of you", "dawn", "Dead Zone", "Order", "teachers"):
            self.assertIn(beat, epilogue)
        self.assertNotRegex(epilogue.lower(), r"\b(destroy|destroyed|deleted the core|kill)\b")


class LookupTests(unittest.TestCase):
    def test_cutscene_for_resolves_every_event(self):
        self.assertIs(story.cutscene_for("prologue"), story.PROLOGUE)
        self.assertIs(story.cutscene_for("epilogue"), story.EPILOGUE)
        for tier in range(5):
            self.assertIs(story.cutscene_for(f"intro:{tier}"), story.SECTOR_INTROS[tier])

    def test_cutscene_for_unknown_events_is_none(self):
        for event in ("", "intro", "intro:", "intro:5", "intro:-1", "intro:01", "intro: 1", "intro:x",
                      "Prologue", "PROLOGUE", " prologue", "finale", "L05", "outro:0", None, 0, 3.0, ["prologue"]):
            with self.subTest(event=event):
                self.assertIsNone(story.cutscene_for(event))

    def test_intro_event_marks_the_first_level_of_each_sector(self):
        firsts = {sector.levels[0].id: f"intro:{sector.tier}" for sector in CAMPAIGN}
        self.assertEqual(firsts, {"L01": "intro:0", "L06": "intro:1", "L11": "intro:2",
                                  "L16": "intro:3", "L21": "intro:4"})
        for sector in CAMPAIGN:
            for level in sector.levels:
                with self.subTest(level=level.id):
                    self.assertEqual(story.intro_event(level.id), firsts.get(level.id))
                    if level.id in firsts:
                        self.assertIsNotNone(story.cutscene_for(story.intro_event(level.id)))
        for unknown in ("", "L00", "L26", "l01", "intro:0"):
            self.assertIsNone(story.intro_event(unknown))

    def test_media_ids_are_unique_filename_safe_and_never_a_level_id(self):
        ids = [story.media_id(event) for event in story.EVENTS]
        self.assertEqual(len(set(ids)), len(ids))
        level_ids = {lvl.id for sector in CAMPAIGN for lvl in sector.levels}
        for media in ids:
            self.assertRegex(media, r"^STORY_[A-Z0-9_]+$")
            self.assertNotIn(media, level_ids)
        self.assertEqual(story.media_id("intro:2"), "STORY_INTRO_2")
        with self.assertRaises(KeyError):
            story.media_id("intro:9")

    def test_imports_cleanly_in_a_fresh_process(self):
        code = ("import json, sys; import levels.story as s; "
                "print(json.dumps({'events': [e for e, _ in s.ALL], "
                "'intros': sorted(s.SECTOR_INTROS), "
                "'loaded_harness': 'engine.harness' in sys.modules}))")
        done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                              timeout=60, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr, "")
        result = json.loads(done.stdout)
        self.assertEqual(result["events"], EXPECTED_EVENTS)
        self.assertEqual(result["intros"], [0, 1, 2, 3, 4])
        self.assertFalse(result["loaded_harness"])


class EnginePayloadTests(SandboxTestCase):
    """Every story cutscene goes through the paths the engine uses for Mission.cutscene today."""

    def test_session_payload_builds_from_each_cutscene(self):
        base = load_mission("level_01_cold_boot")
        for event, cutscene in story.ALL:
            with self.subTest(event=event):
                payload = self.session._mission_payload(replace(base, cutscene=cutscene))["cutscene"]
                self.assertEqual(payload, {"title": cutscene.title, "narration": list(cutscene.narration)})
                self.assertIsNot(payload["narration"], cutscene.narration)
                json.dumps(payload)   # it goes over the wire as JSON

    def test_higgsfield_prompt_carries_shot_and_camera(self):
        renderer = self.session.cinema
        for event, cutscene in story.ALL:
            with self.subTest(event=event):
                still = renderer._prompt(cutscene)
                motion = renderer._prompt(cutscene, motion=True)
                self.assertIn(cutscene.shot, still)
                self.assertNotIn(cutscene.camera, still)
                self.assertIn(f"Camera: {cutscene.camera}", motion)

    def test_terminal_transmission_prints_every_line(self):
        for event, cutscene in story.ALL:
            with self.subTest(event=event):
                console = Console(file=io.StringIO(), width=200, record=True, color_system=None)
                ui.transmission(console, cutscene, animate=False, speed=0)
                text = console.export_text()
                self.assertIn(cutscene.title, text)
                for line in cutscene.narration:
                    self.assertIn(line.split()[0], text)

    def test_story_does_not_change_level_cutscenes(self):
        self.assertTrue(load_mission("level_01_cold_boot").cutscene.anchor)
        warden = load_mission("level_05_the_warden").cutscene
        self.assertIsNotNone(warden)
        self.assertNotIn(warden, [c for _, c in story.ALL])


if __name__ == "__main__":
    unittest.main()
