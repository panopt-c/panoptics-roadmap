"""Play the first story arc using the real grader and an isolated on-disk save."""
from __future__ import annotations

import json

from engine.session import GameSession, SessionError
from tests import SOLUTION as L01_SOLUTION, SandboxTestCase, assert_hack_result, assert_mission
from tests.test_act1_signal_codex import SOLUTION as L02_SOLUTION
from tests.test_act1_warden_codex import SOLUTION as L05_SOLUTION


class ActOneProgressionTests(SandboxTestCase):
    def test_first_arc_unlocks_in_order_and_survives_restarts_without_repeat_xp(self):
        from tests.test_act1_inventory_codex import SALVAGE, CACHE_RAID

        solutions = [L01_SOLUTION, L02_SOLUTION, SALVAGE, CACHE_RAID, L05_SOLUTION]
        total_xp = 0
        first_records = {}
        for number, source in enumerate(solutions, 1):
            mission_id = f"L{number:02}"
            upcoming_id = f"L{number + 1:02}"
            with self.subTest(mission=mission_id):
                self.assertEqual(self.session.snapshot()["current"], mission_id)
                self.assertTrue(self.session.playable(mission_id))
                self.assertFalse(self.session.playable(upcoming_id))
                with self.assertRaises(SessionError) as locked:
                    self.session.deploy(upcoming_id)
                self.assertEqual(locked.exception.status, 403)

                mission = self.session.deploy(mission_id)
                assert_mission(self, mission)
                if number > 1:
                    # The same payload drives intro and combat-result dialogue in the client.
                    for event in ("intro", "victory", "fail", "crash"):
                        self.assertTrue(mission["dialogue"].get(event), (mission_id, event))
                failed = self.session.attack(mission_id)
                assert_hack_result(self, failed)
                self.assertFalse(failed["victory"], "a fresh starter cannot award a clear")
                self.assertEqual(failed["state"]["profile"]["xp"], total_xp)
                self.assertIsNone(failed["next"])

                self.session.write_source(mission_id, source)
                # Re-deploy and restart must never overwrite a player's solution.
                self.assertEqual(self.session.deploy(mission_id)["source"], source)
                self.session = GameSession(self.paths)
                self.assertEqual(self.session.mission(mission_id)["source"], source)
                result = self.session.attack(mission_id)
                assert_hack_result(self, result)
                self.assertTrue(result["victory"], result["report"])
                self.assertTrue(all(check["passed"] for check in result["report"]["checks"]))
                self.assertEqual(result["attempt"], 2)
                expected_xp = mission["xp"] + mission["xp"] // 2
                self.assertEqual(result["reward"]["gained"], expected_xp)
                total_xp += expected_xp
                first_records[mission_id] = dict(self.session.save.cleared[mission_id])
                self.assertEqual(result["next"]["id"], upcoming_id)
                if number < 5:
                    self.assertEqual(result["next"]["status"], "current")

                self.session = GameSession(self.paths)
                self.assertEqual(self.session.snapshot()["profile"]["xp"], total_xp)
                self.assertEqual(self.session.snapshot()["current"], upcoming_id)
                self.assertEqual(self.session.save.cleared, first_records)
                self.assertEqual(self.session.save.callsign, "Nyx")

        # The Act I payoff remains available offline after a restart.
        boss = self.session.mission("L05")
        self.assertTrue(boss["boss"])
        self.assertTrue(boss["cutscene"]["narration"])
        self.assertEqual(self.session.cutscene("L05").title, boss["cutscene"]["title"])
        for number in range(1, 6):
            mission_id = f"L{number:02}"
            with self.subTest(replay=mission_id):
                replay = self.session.attack(mission_id)
                self.assertTrue(replay["victory"], replay["report"])
                self.assertTrue(replay["reward"]["replay"])
                self.assertEqual(replay["reward"]["gained"], 0)
                self.assertEqual(replay["state"]["profile"]["xp"], total_xp)
                self.assertEqual(replay["attempt"], 3)
                self.assertEqual(self.session.save.cleared, first_records)

        disk_save = json.loads(self.paths.save_path.read_text(encoding="utf-8"))
        self.assertEqual(disk_save["xp"], total_xp)
        self.assertEqual(disk_save["cleared"], first_records)
        self.assertEqual(len(disk_save["cleared"]), 5)
        self.assertEqual(len(list(self.paths.missions_dir.glob("level_*.py"))), 5)


if __name__ == "__main__":
    import unittest
    unittest.main()
