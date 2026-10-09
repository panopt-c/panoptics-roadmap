"""THE LAB // track PY "DATA RITES" (PY01-PY07), graded through the REAL subprocess grader.

For every mission: the untouched starter must not win; a correct reference solution must
clear every firewall layer; realistic learner mistakes must fail on the right layer with a
message that teaches. Each grade runs `python -m engine.harness lab:<slug> <file> <report>`
from the code root, with the mission's assets written beside the player's file, exactly as
the game does.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import lab
from engine.drills import CONCEPTS
from tools.validate_content import validate_mission

ROOT = Path(__file__).resolve().parents[1]
TRACK = next(t for t in lab.TRACKS if t.code == "PY")


def _importable(entry_id: str) -> bool:
    found = lab.find(entry_id)
    return bool(found and found[1].slug and not lab.missing_requirements(found[1]))


def grade(slug: str, source: str) -> dict:
    """Write the player's file + assets to a fresh folder and run the sandboxed grader on it."""
    mission = lab.load_mission(slug)
    with tempfile.TemporaryDirectory(prefix="ns-labpy-") as tmp:
        folder = Path(tmp)
        player = folder / mission.filename
        player.write_bytes(source.lstrip("\n").encode("utf-8"))
        for name, text in mission.assets.items():
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode("utf-8"))
        out = folder / "report.json"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        started = time.monotonic()
        proc = subprocess.run([sys.executable, "-m", "engine.harness", f"lab:{slug}", str(player), str(out)],
                              cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=mission.timeout + 20)
        elapsed = time.monotonic() - started
        if not out.exists():
            raise AssertionError(f"grader produced no report:\n{proc.stderr.decode(errors='replace')[-1500:]}")
        report = json.loads(out.read_text(encoding="utf-8"))
        report["elapsed"] = elapsed
        report["folder"] = sorted(p.name for p in folder.iterdir())
    return report


def mutate(source: str, old: str, new: str) -> str:
    assert old in source, f"mutation anchor not found: {old!r}"
    return source.replace(old, new, 1)


class LabPYMixin:
    """Shared checks; each mission's TestCase mixes this in."""
    entry_id = ""
    solution = ""
    # (label, wrong source, layer-name fragment, fragments the message+hint must contain)
    mistakes: tuple = ()

    @classmethod
    def setUpClass(cls):
        cls.track, cls.entry = lab.find(cls.entry_id)
        cls.slug = cls.entry.slug
        cls.mission = lab.load_mission(cls.slug)

    def describe(self, report) -> str:
        lines = [f"status={report['status']} error={report['error']}"]
        lines += [f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['name']}: {c['message']} | {c['hint']}"
                  for c in report["checks"]]
        return "\n".join(lines)

    def assert_victory(self, report):
        self.assertEqual(report["status"], "ok", self.describe(report))
        self.assertEqual(len(report["checks"]), len(self.mission.checks))
        self.assertTrue(all(c["passed"] for c in report["checks"]), self.describe(report))
        self.assertLess(report["elapsed"], self.mission.timeout / 2, "grading must finish well under the timeout")

    def assert_fails_on(self, report, layer: str, *teaches: str):
        """`layer` is the first red layer and its message + hint contain every fragment."""
        self.assertNotIn(report["status"], ("harness_error", "timeout"), self.describe(report))
        failed = [c for c in report["checks"] if not c["passed"]]
        self.assertTrue(failed, "expected a failing layer:\n" + self.describe(report))
        self.assertIn(layer, failed[0]["name"], f"{layer!r} should be the first red layer:\n" + self.describe(report))
        target = failed[0]
        self.assertTrue(target["message"].strip(), "failure needs a message")
        self.assertTrue(target["hint"].strip(), "failure needs a teaching hint")
        text = target["message"] + " " + target["hint"]
        for fragment in teaches:
            self.assertIn(fragment, text, self.describe(report))
        self.assertLessEqual(len(target["message"]), 600, "failure messages stay small")
        return target

    def test_starter_is_not_a_victory(self):
        report = grade(self.slug, self.mission.starter)
        self.assertNotIn(report["status"], ("harness_error", "timeout"), self.describe(report))
        self.assertFalse(report["status"] == "ok" and all(c["passed"] for c in report["checks"]),
                         "the untouched starter must not clear the mission")
        self.assertTrue(any(not c["passed"] and c["message"] for c in report["checks"]))

    def test_reference_solution_clears_every_layer(self):
        self.assert_victory(grade(self.slug, self.solution))

    def test_learner_mistakes_fail_on_the_right_layer(self):
        self.assertGreaterEqual(len(self.mistakes), 2)
        for label, source, layer, teaches in self.mistakes:
            with self.subTest(mistake=label):
                self.assert_fails_on(grade(self.slug, source), layer, *teaches)

    def test_mission_contract(self):
        m, e = self.mission, self.entry
        self.assertEqual((m.id, m.slug, m.title, m.concept), (e.id, e.slug, e.title, e.concept))
        self.assertEqual(m.requires, e.requires)
        self.assertEqual(m.tier, 2)
        self.assertEqual(m.xp, 180 if e.capstone else 120)
        self.assertEqual(m.boss, e.capstone)
        self.assertEqual(m.grader_key, f"lab:{e.slug}")
        self.assertFalse(m.run_as_main)
        self.assertLessEqual(m.timeout, 20)
        self.assertTrue(m.concepts and set(m.concepts) <= set(CONCEPTS), m.concepts)
        self.assertTrue(5 <= len(m.checks) <= 8, len(m.checks))
        self.assertEqual(validate_mission(m, campaign=True), [])
        self.assertLessEqual(len(re.sub(r"```.*?```", "", m.briefing, flags=re.S).split()), 130)
        self.assertLessEqual(len(re.sub(r"```.*?```", "", m.why, flags=re.S).split()), 160)
        self.assertIn("**", m.briefing.strip().splitlines()[-1], "briefing ends with a bold objective")
        self.assertIn("```", m.manual)
        art = m.enemy_art.splitlines()
        self.assertTrue(art and len(art) <= 7 and max(map(len, art)) <= 20)
        # dialogue (GAME_DESIGN §5.2): Ada leads
        d = m.dialogue
        self.assertEqual(set(d), {"intro", "crash", "fail", "victory"})
        self.assertEqual(d["intro"][0]["speaker"], "ada")
        lines = d["intro"] + d["victory"] + [l for seq in d["crash"] + d["fail"] for l in seq]
        for line in lines:
            self.assertIn(line["speaker"], {"ada", "cipher", "rust", "nova", "vex"})
            self.assertIn(line["mood"], {"neutral", "smirk", "alarm", "warm", "cold"})
            self.assertLessEqual(len(line["text"]), 160, line["text"])
        for pool in ("crash", "fail"):
            self.assertTrue(all(1 <= len(seq) <= 2 for seq in d[pool]))
        if e.capstone:
            c = m.cutscene
            self.assertIsNotNone(c)
            self.assertTrue(3 <= len(c.narration) <= 6)
            self.assertTrue(c.shot and c.camera)
        else:
            self.assertIsNone(m.cutscene)


# ── PY01 THE CENSUS ─────────────────────────────────────────────────────────────

PY01_SOLUTION = r'''
CENSUS = []


def names_of(records):
    return [r["name"] for r in records]


def adults(records, min_age=18):
    return [r for r in records if r["age"] >= min_age]


def name_to_age(records):
    return {r["name"]: r["age"] for r in records}


def sectors(records):
    return {r["sector"] for r in records}


def all_skills(records):
    return {s for r in records for s in r["skills"]}


def feature_rows(records, keys):
    return [[r[k] for k in keys] for r in records]


def clean_names(records):
    return [r["name"].strip().lower() for r in records]
'''


@unittest.skipUnless(_importable("PY01"), "PY01 not built or requirements missing")
class PY01CensusTests(LabPYMixin, unittest.TestCase):
    entry_id = "PY01"
    solution = PY01_SOLUTION
    mistakes = (
        ("off-by-one: > instead of >=", mutate(PY01_SOLUTION, 'r["age"] >= min_age', 'r["age"] > min_age'),
         "Of age", ">="),
        ("ignores the min_age parameter", mutate(PY01_SOLUTION, 'r["age"] >= min_age', 'r["age"] >= 18'),
         "Of age", "min_age"),
        ("loop instead of a comprehension",
         mutate(PY01_SOLUTION, '    return [r["name"] for r in records]',
                '    out = []\n    for r in records:\n        out.append(r["name"])\n    return out'),
         "Roll call", "comprehension"),
        ("set built as a list", mutate(PY01_SOLUTION, '{r["sector"] for r in records}', '[r["sector"] for r in records]'),
         "Territory", "set"),
        ("collects skill lists instead of skills",
         mutate(PY01_SOLUTION, '{s for r in records for s in r["skills"]}', '[r["skills"] for r in records]'),
         "Skill registry", "second for clause"),
        ("forgot the call parentheses",
         mutate(PY01_SOLUTION, '.strip().lower()', '.strip().lower'), "Purge", "()"),
    )


if __name__ == "__main__":
    unittest.main()
