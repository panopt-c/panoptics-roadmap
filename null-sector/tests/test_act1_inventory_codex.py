"""Act I salvage/cache checks through the real subprocess harness, in temporary folders."""
from pathlib import Path
import tempfile
import unittest

from engine.runner import hack
from levels import load_mission


SALVAGE = '''\
scanned_parts = ["wire", "battery", "cracked optic", "relay"]
inventory = scanned_parts[:]
inventory[2] = "lens"
inventory.append("fuse")
first_part = inventory[0]
last_part = inventory[-1]
field_kit = inventory[1:4]
reserve = inventory[:]
reserve.append("spare wire")
part_count = len(inventory)
print(f"First: {first_part}; last: {last_part}; parts: {part_count}")
'''

CACHE_RAID = '''\
cache = {"gate": "M-17", "district": "dead zone", "charge": "4", "owner": "LOCKSMITH"}
access_key = cache["gate"]
charge_total = int(cache["charge"]) + 6
alarm = cache.get("alarm", "silent")
route = cache.copy()
route["owner"] = "RUST"
route["charge"] = charge_total
route["verified"] = True
field_count = len(route)
print(f"Gate {access_key}; sponsor {route['owner']}; fields {field_count}")
'''


class ActOneInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ns-act1-inventory-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def grade(self, slug, source):
        mission = load_mission(slug)
        path = self.root / mission.filename
        path.write_text(source, encoding="utf-8")
        report = hack(mission, path=path)
        self.assertNotIn(report.status, ("harness_error", "timeout"), report.error)
        self.assertEqual(report.total, 8)
        return report

    def assert_failed_layer(self, report, phrase):
        self.assertFalse(report.victory)
        matching = [check for check in report.checks if phrase in check["name"]]
        self.assertEqual(len(matching), 1)
        self.assertFalse(matching[0]["passed"], matching[0])
        self.assertTrue(matching[0]["message"])

    def test_correct_salvage_solution(self):
        report = self.grade("level_03_scrap_inventory", SALVAGE)
        self.assertTrue(report.victory, report.checks)
        self.assertEqual(report.passed, 8)

    def test_correct_cache_solution(self):
        report = self.grade("level_04_cache_raid", CACHE_RAID)
        self.assertTrue(report.victory, report.checks)
        self.assertEqual(report.passed, 8)

    def test_starters_are_unsolved_and_have_readable_failures(self):
        for slug in ("level_03_scrap_inventory", "level_04_cache_raid"):
            with self.subTest(slug=slug):
                report = self.grade(slug, load_mission(slug).starter)
                self.assertFalse(report.victory)
                self.assertTrue(any(not check["passed"] and check["message"] for check in report.checks))
        self.assertEqual(report.status, "crash")
        self.assertEqual(report.error["type"], "KeyError")

    def test_salvage_reports_common_list_mistakes(self):
        cases = (
            ("inventory = scanned_parts[:]", "inventory = scanned_parts", "scanner record"),
            ('inventory[2] = "lens"', 'inventory[1] = "lens"', "cracked optic"),
            ('inventory.append("fuse")', 'inventory = inventory.append("fuse")', "Collect the fuse"),
            ("last_part = inventory[-1]", "last_part = inventory[4:5]", "Read both ends"),
            ("field_kit = inventory[1:4]", "field_kit = inventory[1:3]", "middle three"),
            ("reserve = inventory[:]", "reserve = inventory", "spare separate"),
            ("part_count = len(inventory)", "part_count = len(reserve)", "Count the shipment"),
            ("part_count = len(inventory)", "part_count = True", "Count the shipment"),
        )
        for old, new, layer in cases:
            with self.subTest(mistake=new):
                report = self.grade("level_03_scrap_inventory", SALVAGE.replace(old, new))
                self.assert_failed_layer(report, layer)

    def test_salvage_rejects_retyped_results_and_missing_broadcast(self):
        cases = (
            ("first_part = inventory[0]", 'first_part = "wire"', "Read both ends"),
            ("field_kit = inventory[1:4]", 'field_kit = ["battery", "lens", "relay"]', "middle three"),
            ("part_count = len(inventory)", "part_count = 5", "Count the shipment"),
            ('print(f"First: {first_part}; last: {last_part}; parts: {part_count}")',
             'print("First: wire; last: fuse; parts: 5")', "Deliver RUST"),
        )
        for old, new, layer in cases:
            with self.subTest(mistake=new):
                self.assert_failed_layer(self.grade("level_03_scrap_inventory", SALVAGE.replace(old, new)), layer)

    def test_cache_reports_common_dictionary_mistakes(self):
        cases = (
            ('access_key = cache["gate"]', "access_key = cache[0]", "named gate key"),
            ('charge_total = int(cache["charge"]) + 6', 'charge_total = cache["charge"] + "6"', "Recharge the pass"),
            ('alarm = cache.get("alarm", "silent")', 'alarm = cache["alarm"]', "absent field"),
            ("route = cache.copy()", "route = cache", "working copy"),
            ('route["owner"] = "RUST"', 'route["Owner"] = "RUST"', "working copy"),
            ('route["charge"] = charge_total', 'route["charge"] = str(charge_total)', "working copy"),
            ('route["verified"] = True', 'route["verified"] = "True"', "boolean field"),
            ('route["verified"] = True', 'route["verified"] = 1', "boolean field"),
            ("field_count = len(route)", "field_count = len(cache)", "Count the named fields"),
        )
        for old, new, layer in cases:
            with self.subTest(mistake=new):
                self.assert_failed_layer(self.grade("level_04_cache_raid", CACHE_RAID.replace(old, new)), layer)

    def test_cache_rejects_retyped_results(self):
        cases = (
            ('access_key = cache["gate"]', 'access_key = "M-17"', "named gate key"),
            ('charge_total = int(cache["charge"]) + 6', "charge_total = 10", "Recharge the pass"),
            ('alarm = cache.get("alarm", "silent")', 'alarm = "silent"', "absent field"),
            ("field_count = len(route)", "field_count = 5", "Count the named fields"),
        )
        for old, new, layer in cases:
            with self.subTest(mistake=new):
                self.assert_failed_layer(self.grade("level_04_cache_raid", CACHE_RAID.replace(old, new)), layer)

    def test_alternative_taught_copy_and_lookup_forms_pass(self):
        salvage = SALVAGE.replace("inventory = scanned_parts[:]", "inventory = scanned_parts[0:]")
        salvage = salvage.replace("last_part = inventory[-1]", "last_part = inventory[len(inventory) - 1]")
        self.assertTrue(self.grade("level_03_scrap_inventory", salvage).victory)
        cache = CACHE_RAID.replace('access_key = cache["gate"]', 'access_key = cache.get("gate")')
        self.assertTrue(self.grade("level_04_cache_raid", cache).victory)


if __name__ == "__main__":
    unittest.main()
