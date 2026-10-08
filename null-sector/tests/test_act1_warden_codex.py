"""Exercise Act I's boss through the same subprocess grader used by the game."""
import ast
from pathlib import Path
import tempfile
import unittest

from engine.runner import hack
from levels import load_mission


SOLUTION = '''raw_log = "  OPEN,ERROR,OPEN,OPEN|12,20,17,24  "
clean_log = raw_log.strip().lower()
sections = clean_log.split("|")
events = sections[0].split(",")
samples = sections[1].split(",")
latencies = [int(samples[0]), int(samples[1]), int(samples[2]), int(samples[3])]
counts = {"open": events.count("open"), "error": events.count("error")}
total_latency = sum(latencies)
fastest = min(latencies)
slowest = max(latencies)
mean_latency = total_latency / len(latencies)
report = {"events": len(events), "counts": counts, "total_ms": total_latency,
          "min_ms": fastest, "max_ms": slowest, "mean_ms": mean_latency}
print(f"WARDEN AUDIT | events={report['events']} | open={report['counts']['open']} | error={report['counts']['error']} | mean_ms={report['mean_ms']}")
'''


class WardenMissionTests(unittest.TestCase):
    def setUp(self):
        self.mission = load_mission("level_05_the_warden")
        temp = tempfile.TemporaryDirectory(prefix="ns-warden-")
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / self.mission.filename

    def grade(self, source):
        self.path.write_text(source, encoding="utf-8")
        return hack(self.mission, path=self.path)

    def test_correct_beginner_solution_passes_all_eight_layers(self):
        advanced = (ast.For, ast.While, ast.If, ast.FunctionDef, ast.Lambda,
                    ast.ListComp, ast.DictComp, ast.GeneratorExp)
        self.assertFalse(any(isinstance(node, advanced) for node in ast.walk(ast.parse(SOLUTION))))
        report = self.grade(SOLUTION)
        self.assertTrue(report.victory, report)
        self.assertEqual(report.total, 8)
        self.assertIn("mean_ms=18.25", report.stdout)

    def test_starter_requires_repairs(self):
        report = self.grade(self.mission.starter)
        self.assertFalse(report.victory)
        self.assertNotEqual(report.status, "harness_error")
        self.assertTrue(any(not item["passed"] and item["hint"] for item in report.checks))

    def test_wrong_event_counts_explain_list_count(self):
        source = SOLUTION.replace('events.count("error")}', 'events.count("open")}')
        report = self.grade(source)
        self.assertEqual(report.status, "ok")
        self.assertFalse(report.victory)
        failed = next(item for item in report.checks if item["name"] == "Count openings and errors")
        self.assertFalse(failed["passed"])
        self.assertIn("events.count", failed["hint"])

    def test_floor_division_explains_lost_fraction(self):
        report = self.grade(SOLUTION.replace("total_latency / len", "total_latency // len"))
        self.assertEqual(report.status, "ok")
        self.assertFalse(report.victory)
        failed = next(item for item in report.checks if item["name"] == "Retain the fractional mean")
        self.assertFalse(failed["passed"])
        self.assertIn("fractional", failed["hint"])

    def test_typed_answers_do_not_replace_the_pipeline(self):
        source = SOLUTION.replace("total_latency = sum(latencies)", "total_latency = 73")
        report = self.grade(source)
        self.assertEqual(report.status, "ok")
        self.assertFalse(report.victory)
        failed = next(item for item in report.checks if item["name"] == "Sum every latency sample")
        self.assertIn("latencies", failed["hint"])

    def test_boss_story_and_dialogue_contract(self):
        self.assertTrue(self.mission.boss)
        self.assertEqual(self.mission.tier, 1)
        self.assertIsNotNone(self.mission.cutscene)
        self.assertFalse(self.mission.cutscene.anchor)
        self.assertIn("Monastery", " ".join(self.mission.cutscene.narration))
        self.assertGreaterEqual(len(self.mission.cutscene.narration), 3)
        self.assertLessEqual(len(self.mission.cutscene.narration), 5)
        for event in ("intro", "crash", "fail", "victory"):
            sequences = self.mission.dialogue[event]
            if event in ("intro", "victory"):
                sequences = [sequences]
            for sequence in sequences:
                self.assertTrue(sequence)
                for line in sequence:
                    self.assertEqual(set(line), {"speaker", "text", "mood"})
                    self.assertLessEqual(len(line["text"]), 160)
                    self.assertIn(line["mood"], ("neutral", "smirk", "alarm", "warm", "cold"))
