"""Exercise SIGNAL NOISE through the same subprocess grader used by players."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from engine.runner import hack
from levels.level_02_signal_noise import MISSION

SOLUTION = '''raw_signal = "  SOS::MONASTERY::SECTOR-0::GATE-7  "
clean_signal = raw_signal.strip().lower().replace("::", "|")
fields = clean_signal.split("|")
destination = fields[1]
coordinates = "/".join(fields[2:])
sector = coordinates[:8]
coordinate_length = len(coordinates)
has_sanctuary = "monastery" in clean_signal
print(f"ROUTE {coordinates}")
'''


class SignalMissionTests(unittest.TestCase):
    def grade(self, source):
        with TemporaryDirectory() as folder:
            path = Path(folder) / MISSION.filename
            path.write_text(source, encoding="utf-8")
            return hack(MISSION, path=path)

    def test_reference_solution_passes_every_layer(self):
        report = self.grade(SOLUTION)
        self.assertTrue(report.victory, report)
        self.assertEqual(report.total, 8)

    def test_starter_runs_but_does_not_win(self):
        report = self.grade(MISSION.starter)
        self.assertEqual(report.status, "ok")
        self.assertFalse(report.victory)
        self.assertEqual(report.passed, 0)
        self.assertTrue(report.first_failure["hint"])

    def test_wrong_case_is_explained_at_cleanup_layer(self):
        report = self.grade(SOLUTION.replace(".lower()", ".upper()"))
        self.assertEqual(report.status, "ok")
        self.assertFalse(report.victory)
        self.assertEqual(report.first_failure["name"], "Clean the preserved signal")
        self.assertIn("lower()", report.first_failure["hint"])

    def test_exclusive_slice_boundary_has_targeted_hint(self):
        report = self.grade(SOLUTION.replace("coordinates[:8]", "coordinates[:7]"))
        self.assertEqual(report.status, "ok")
        self.assertEqual(report.passed, 7)
        self.assertEqual(report.first_failure["name"], "Extract the sector")
        self.assertIn("stop index", report.first_failure["hint"])

    def test_retyping_expected_address_is_rejected(self):
        report = self.grade(SOLUTION.replace('"/".join(fields[2:])', '"sector-0/gate-7"'))
        self.assertFalse(report.victory)
        self.assertEqual(report.first_failure["name"], "Rebuild the coordinates")
        self.assertIn("from `fields`", report.first_failure["message"])


if __name__ == "__main__":
    unittest.main()
