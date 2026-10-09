"""Regression tests for the content gate, independent of unfinished v2 content."""
import ast
import subprocess
import unittest
from unittest import mock

from engine.mission import Check, Context, Fail, Mission
from tools.validate_content import asset_errors, call_worker, mission_fingerprint, validate_content, validate_mission


def sample():
    mission = Mission(id="L99", slug="level_99_fixture", title="Fixture", concept="types",
                      enemy="TEST", xp=100, par_seconds=60, briefing="Brief", why="Why",
                      manual="Manual", starter="value = None", tier=1, concepts=("types",))
    mission.checks = [Check(f"Check {i}", lambda ctx: None) for i in range(5)]
    return mission


class ContentContractTests(unittest.TestCase):
    def test_valid_contract_and_nested_text_assets(self):
        mission = sample()
        mission.assets = {"data/input.csv": "x,y\n1,2\n", "mock_api.py": "VALUE = 1"}
        self.assertEqual(validate_mission(mission, campaign=True), [])

    def test_concepts_must_be_known_mastery_tags(self):
        for concepts in ((), ("types", "text_cleaning")):
            with self.subTest(concepts=concepts):
                mission = sample()
                mission.concepts = concepts
                self.assertTrue(any("concepts" in e for e in validate_mission(mission, campaign=True)))

    def test_incomplete_module_is_not_a_valid_mission(self):
        self.assertTrue(validate_mission(None, campaign=True))
        mission = sample()
        mission.checks = []
        self.assertIn("mission must register at least one check", validate_mission(mission, campaign=True))
        mission = sample()
        mission.slug = "../escape"
        self.assertTrue(validate_mission(mission, campaign=True))

    def test_invalid_timeout_and_boolean_rewards(self):
        for timeout in (float("nan"), float("inf"), -1, 0, 21, True):
            with self.subTest(timeout=timeout):
                mission = sample()
                mission.timeout = timeout
                self.assertTrue(validate_mission(mission, campaign=True))
        mission = sample()
        mission.xp = True
        self.assertTrue(validate_mission(mission, campaign=True))

    def test_cross_platform_asset_escape_devices_and_source_collision(self):
        for name in ("../outside", "..\\outside", "/tmp/outside", "C:\\outside", "C:relative",
                     "\\\\host\\share", "data/file:stream", "NUL.txt", "dir/COM1", "data/file.",
                     "data//file", "level_99_fixture.py", "LEVEL_99_FIXTURE.PY"):
            with self.subTest(name=name):
                self.assertTrue(asset_errors({name: "text"}, "level_99_fixture.py"))
        self.assertTrue(asset_errors({"data/a.csv": "one", "DATA/A.csv": "two"}, "mission.py"))
        self.assertTrue(asset_errors({"x": 123}, "mission.py"))

    def test_duplicate_check_names_are_reported(self):
        mission = sample()
        mission.checks[1].name = mission.checks[0].name
        self.assertTrue(any("duplicate" in error for error in validate_mission(mission, campaign=True)))

    def test_fingerprint_ignores_function_addresses_but_catches_changed_cases(self):
        def build(case):
            mission = sample()
            mission.checks = [Check("Captured case", lambda ctx: case)]
            return mission
        self.assertEqual(mission_fingerprint(build([1, 2])), mission_fingerprint(build([1, 2])))
        self.assertNotEqual(mission_fingerprint(build([1, 2])), mission_fingerprint(build([1, 3])))

    def test_missing_content_is_explicit_and_full_release_gate_fails(self):
        catalog = {"campaign": [{"id": "L02", "slug": "level_02_missing", "present": False}],
                   "drills": []}
        with mock.patch("tools.validate_content.call_worker", return_value=catalog):
            partial = validate_content()
            complete = validate_content(require_complete=True)
        self.assertTrue(partial["ok"])
        self.assertEqual(partial["missing"], ["L02"])
        self.assertFalse(complete["ok"])
        self.assertTrue(any("tier 5 has 0/12" in error for error in complete["errors"]))

    def test_orphan_module_and_broken_registry_are_reported(self):
        catalog = {"campaign": [], "drills": [], "orphans": ["level_02_typo.py"],
                   "drill_error": "SyntaxError: incomplete file"}
        with mock.patch("tools.validate_content.call_worker", return_value=catalog):
            report = validate_content()
        self.assertFalse(report["ok"])
        self.assertEqual(len(report["errors"]), 2)

    def test_nondeterministic_content_is_an_error_and_hash_seeds_differ(self):
        catalog = {"campaign": [], "drills": [{"id": "t1-fixture", "tier": 1}]}
        with mock.patch("tools.validate_content.call_worker", side_effect=[catalog,
                         {"errors": [], "fingerprint": "first"},
                         {"errors": [], "fingerprint": "different"}]) as runner:
            report = validate_content(seeds=(7,))
        self.assertFalse(report["ok"])
        self.assertIn("same seed", report["errors"][0])
        self.assertEqual(runner.call_args.kwargs["hash_seed"], 923)

    def test_worker_deadline_and_invalid_json_do_not_crash_the_validator(self):
        with mock.patch("tools.validate_content.subprocess.run", side_effect=subprocess.TimeoutExpired("test", 1)):
            self.assertIn("deadline", call_worker("catalog", timeout=1)["errors"][0])
        with mock.patch("tools.validate_content.subprocess.run",
                        return_value=subprocess.CompletedProcess([], 0, stdout="noise", stderr="")):
            self.assertIn("invalid worker report", call_worker("catalog")["errors"][0])

    def test_real_l01_starter_is_rejected_without_being_a_content_error(self):
        result = call_worker("campaign", "level_01_cold_boot", exercise=True)
        self.assertEqual(result["errors"], [])
        self.assertIn(result["starter"], {"ok", "crash", "syntax_error"})
        self.assertEqual(result["id"], "L01")

    def test_softmax_keyword_mistake_has_teaching_feedback(self):
        from engine.drills import instance
        from engine.drills.library.tier5_neural import _ref_softmax

        def learner(*args, **kwargs):
            if args:
                return _ref_softmax(*args, **kwargs)
            # A realistic error: ignoring temperature when unpacking keywords.
            return _ref_softmax(kwargs["logits"])

        mission = instance("t5-softmax-heat", 42)
        context = Context({"softmax": learner}, "", "", ast.parse(""), False)
        layer = next(c for c in mission.checks if c.name.startswith("temperature"))
        with self.assertRaises(Fail) as caught:
            layer.fn(context)
        self.assertIn("temperature", str(caught.exception).lower())
        self.assertNotIn("IndexError", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
