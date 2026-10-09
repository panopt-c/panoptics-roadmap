"""Play the whole campaign, L01 → L25, through the real GameSession and grader on one save.

Each act's own tests prove its levels are solvable in isolation. This proves the campaign is
playable end to end: levels unlock in order, data files land beside each mission, a restart
never loses work, XP accumulates exactly once, and the last clear leaves nothing locked.
"""
from __future__ import annotations

import json

from engine.session import GameSession
from levels import ALL_LEVELS
from tests import SOLUTION as L01_SOLUTION, SandboxTestCase
from tests.test_act1_inventory_codex import CACHE_RAID, SALVAGE
from tests.test_act1_signal_codex import SOLUTION as L02_SOLUTION
from tests.test_act1_warden_codex import SOLUTION as L05_SOLUTION
from tests import test_levels_act2 as act2, test_levels_act3 as act3
from tests import test_levels_act4 as act4, test_levels_act5 as act5


def solutions() -> dict[str, str]:
    found = {"L01": L01_SOLUTION, "L02": L02_SOLUTION, "L03": SALVAGE, "L04": CACHE_RAID, "L05": L05_SOLUTION}
    for module in (act2, act3, act4, act5):
        for name in dir(module):
            if name.endswith("_SOLUTION") and name[:1] == "L":
                found[name.split("_")[0]] = getattr(module, name)
    return found


class CampaignProgressionTests(SandboxTestCase):
    def test_the_whole_campaign_plays_in_order_on_one_save(self):
        sources = solutions()
        ids = [level.id for level in ALL_LEVELS]
        self.assertEqual(ids, [f"L{n:02}" for n in range(1, 26)])
        self.assertTrue(all(level.slug for level in ALL_LEVELS), "every level is built")
        self.assertEqual(sorted(sources), ids, "a reference solution exists for every level")

        total_xp = 0
        for index, mission_id in enumerate(ids):
            with self.subTest(mission=mission_id):
                snapshot = self.session.snapshot()
                self.assertEqual(snapshot["current"], mission_id)
                if index + 1 < len(ids):
                    self.assertFalse(self.session.playable(ids[index + 1]), "the next level stays locked")

                mission = self.session.deploy(mission_id)
                for event in ("intro", "victory"):
                    self.assertTrue(mission["dialogue"].get(event), (mission_id, event))

                self.session.write_source(mission_id, sources[mission_id])
                self.session = GameSession(self.paths)          # a restart between write and hack
                result = self.session.attack(mission_id)
                failing = [c for c in result["report"]["checks"] if not c["passed"]]
                self.assertTrue(result["victory"], (mission_id, result["report"]["status"],
                                                    result["report"]["error"], failing[:1]))
                self.assertFalse(result["reward"]["replay"])
                total_xp += result["reward"]["gained"]
                self.assertEqual(result["state"]["profile"]["xp"], total_xp)
                if mission["boss"]:
                    self.assertTrue(mission["cutscene"] and mission["cutscene"]["narration"], mission_id)

        final = GameSession(self.paths).snapshot()
        self.assertIsNone(final["current"], "nothing is left to play after L25")
        disk = json.loads(self.paths.save_path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(disk["cleared"]), ids)
        self.assertEqual(disk["xp"], total_xp)


if __name__ == "__main__":
    import unittest
    unittest.main()
