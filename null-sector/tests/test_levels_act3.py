"""Act III // THE FORGE (L11-L15), graded through the REAL subprocess grader.

For every level: the untouched starter must not win; a correct reference solution must
clear every firewall layer; realistic wrong solutions must fail on the right layer with a
message that teaches. Each grade runs `python -m engine.harness <slug> <file> <report>`
from the code root, with the mission's assets written beside the player's file, exactly
as the game does.
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

from engine.drills import CONCEPTS
from levels import load_mission

ROOT = Path(__file__).resolve().parents[1]
ACT3 = ("level_11_blueprints", "level_12_bloodlines", "level_13_black_box",
        "level_14_failsafe", "level_15_the_forgemaster")


# ── reference solutions (what a strong player would write) ──────────────────────

L11_SOLUTION = r'''
class Drone:
    """Blueprint for an Order drone."""

    def __init__(self, name, battery=100):
        self.name = name
        self.battery = battery
        self.cargo = []

    def charge(self, amount):
        self.battery = min(100, self.battery + amount)

    def fly(self, distance):
        cost = distance * 2
        if cost > self.battery:
            return False
        self.battery -= cost
        return True

    def __repr__(self):
        return f"Drone(name='{self.name}', battery={self.battery})"

    def load(self, item):
        self.cargo.append(item)
        return len(self.cargo)


scout = Drone("Kite", 80)
hauler = Drone("Mule")
hauler.load("relay chip")
print(scout)
'''


L12_SOLUTION = r'''
from dataclasses import dataclass      # you'll need this for OBJECTIVE 6


class Drone:
    """Every Order drone descends from this chassis."""

    def __init__(self, name, battery=100):
        self.name = name
        self.battery = battery
        self.cargo = []

    def role(self):
        return "drone"

    def burn_rate(self):
        """Battery burned per km of flight."""
        return 2

    def fly(self, distance):
        cost = distance * self.burn_rate()      # asks THIS drone for its burn rate
        if cost > self.battery:
            return False
        self.battery -= cost
        return True

    def load(self, item):
        self.cargo.append(item)
        return len(self.cargo)

    def status(self):
        return f"{self.name} [{self.role()}] {self.battery}%"

    def __repr__(self):
        return f"{type(self).__name__}(name='{self.name}', battery={self.battery})"


class Scout(Drone):
    def __init__(self, name, battery=100, sensor_range=50):
        super().__init__(name, battery)
        self.sensor_range = sensor_range

    def role(self):
        return "scout"

    def burn_rate(self):
        return 1


class Hauler(Drone):
    def role(self):
        return "hauler"

    def burn_rate(self):
        return super().burn_rate() + len(self.cargo)


class Medic(Drone):
    def __init__(self, name, battery=100, kits=2):
        super().__init__(name, battery)
        self.kits = kits

    def role(self):
        return "medic"

    def heal(self, other):
        """Spend one repair kit: another drone gains 30 battery (max 100)."""
        if self.kits == 0:
            return False
        self.kits -= 1
        other.battery = min(100, other.battery + 30)
        return True


def in_range(drones, distance):
    return [d.name for d in drones if distance * d.burn_rate() <= d.battery]


@dataclass
class Pedigree:
    name: str
    line: str
    generation: int = 1


squad = [Scout("Kite", 80), Hauler("Mule"), Medic("Sal", 60)]
registry = [Pedigree(d.name, d.role()) for d in squad]
for drone in squad:
    print(drone.status())
'''


L13_SOLUTION = r'''
import csv
from pathlib import Path

HERE = Path(__file__).parent

log_path = HERE / "flight_log.csv"
voice_path = HERE / "voice_recorder.txt"


def read_lines(path):
    lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            clean = line.strip()
            if clean:
                lines.append(clean)
    return lines


def load_flight_log(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({"t": int(row["t"]), "altitude": int(row["altitude"]),
                         "speed": int(row["speed"]), "event": row["event"]})
    return rows


def write_transcript(lines, path):
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def export_events(rows, path):
    count = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["t", "event"])
        for row in rows:
            if row["event"]:
                writer.writerow([row["t"], row["event"]])
                count += 1
    return count


flight = load_flight_log(log_path)
voice = read_lines(voice_path)
unknown = [line for line in voice if "UNKNOWN:" in line]
write_transcript(unknown, HERE / "recovered_voice.txt")
export_events(flight, HERE / "flight_events.csv")

for line in unknown:
    print(line)
'''


L14_SOLUTION = r'''
class Furnace:
    """A smelting furnace. Lock it before feeding it readings; always unlock it."""

    def __init__(self, name):
        self.name = name
        self.locked = False
        self.vented = 0

    def lock(self):
        if self.locked:
            raise RuntimeError(f"{self.name} is already locked")
        self.locked = True

    def unlock(self):
        self.locked = False

    def vent(self):
        self.vented += 1


class SensorError(Exception):
    pass


class OverheatError(SensorError):
    def __init__(self, temp, limit):
        super().__init__(f"core at {temp} exceeds limit {limit}")
        self.temp = temp
        self.limit = limit


def parse_reading(text):
    try:
        value = float(text)
    except ValueError:
        raise SensorError(f"unreadable: {text!r}")
    if value < -273.15:
        raise SensorError(f"impossible: {value}")
    return value


def check_temp(temp, limit=900):
    if limit <= 0:
        raise ValueError(f"limit must be above 0: {limit}")
    if temp > limit:
        raise OverheatError(temp, limit)
    return temp


def triage(readings, limit=900):
    report = {"ok": [], "faults": 0, "overheats": 0}
    for text in readings:
        try:
            value = check_temp(parse_reading(text), limit)
        except OverheatError:
            report["overheats"] += 1
        except SensorError:
            report["faults"] += 1
        else:
            report["ok"].append(value)
    return report


def run_cycle(furnace, readings, limit=900):
    furnace.lock()
    try:
        report = triage(readings, limit)
        if report["overheats"]:
            furnace.vent()
        return report
    finally:
        furnace.unlock()


FEED = ["612.0", " 640.5 ", "ERR#", "955.2", "", "701", "-999", "880.25", "1200", "88O"]


crucible = Furnace("CRUCIBLE-3")
report = run_cycle(crucible, FEED)
print(f"FAILSAFE | ok={len(report['ok'])} | faults={report['faults']} | overheats={report['overheats']}")
'''


L15_SOLUTION = r'''
import csv
import random
from pathlib import Path

HERE = Path(__file__).parent
LABELS = {"signal": 1, "noise": 0}     # label text -> the number a model trains on


class CorruptSample(ValueError):
    pass


def parse_row(row):
    shard = row["shard"]
    try:
        features = [float(row["heat"]), float(row["flux"])]
    except (ValueError, TypeError):
        raise CorruptSample(f"{shard}: unreadable features")
    label = (row["label"] or "").strip().lower()
    if label not in LABELS:
        raise CorruptSample(f"{shard}: unknown label {row['label']!r}")
    return features, LABELS[label]


class ForgeDataset:
    """A PyTorch-style dataset over a CSV of forge shards."""


    def __init__(self, path):
        self.samples = []
        self.rejected = 0
        self.signers = set()
        seen = set()
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    sample = parse_row(row)
                except CorruptSample:
                    self.rejected += 1
                    continue
                shard = row["shard"].strip()
                if shard in seen:
                    self.rejected += 1
                    continue
                seen.add(shard)
                self.samples.append(sample)
                self.signers.add(row["signer"].strip())


    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        return self.samples[index]

    def __repr__(self):
        return f"ForgeDataset(samples={len(self)}, rejected={self.rejected})"

    def split(self, test_ratio=0.25, seed=0):
        """Shuffle the sample positions with a fixed seed, then cut them in two."""
        if not 0 < test_ratio < 1:
            raise ValueError(f"test_ratio must be between 0 and 1, got {test_ratio}")
        order = list(range(len(self)))
        random.Random(seed).shuffle(order)
        n_test = int(len(self) * test_ratio)
        test = [self[i] for i in order[:n_test]]
        train = [self[i] for i in order[n_test:]]
        return train, test


forge = ForgeDataset(HERE / "forge_shards.csv")
train, test = forge.split(0.2, seed=2089)
signature = ", ".join(sorted(forge.signers))
print(f"FORGE AUDIT | samples={len(forge)} | rejected={forge.rejected} | train={len(train)} | test={len(test)} | signer={signature}")
'''


# ── grading through the real harness ─────────────────────────────────────────────

def grade(slug: str, source: str) -> dict:
    """Write the player's file + assets to a fresh folder and run the sandboxed grader on it."""
    mission = load_mission(slug)
    with tempfile.TemporaryDirectory(prefix="ns-act3-") as tmp:
        folder = Path(tmp)
        player = folder / mission.filename
        player.write_bytes(source.encode("utf-8"))
        for name, text in mission.assets.items():
            (folder / name).write_bytes(text.encode("utf-8"))
        out = folder / "report.json"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        started = time.monotonic()
        proc = subprocess.run([sys.executable, "-m", "engine.harness", slug, str(player), str(out)],
                              cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=mission.timeout + 20)
        elapsed = time.monotonic() - started
        if not out.exists():
            raise AssertionError(f"grader produced no report:\n{proc.stderr.decode(errors='replace')[-1500:]}")
        report = json.loads(out.read_text(encoding="utf-8"))
        report["elapsed"] = elapsed
        report["folder"] = sorted(p.name for p in folder.iterdir())
        report["files"] = {p.name: p.read_text(encoding="utf-8") for p in folder.iterdir()
                           if p.is_file() and p.suffix in (".txt", ".csv")}
    return report


def mutate(source: str, old: str, new: str) -> str:
    assert old in source, f"mutation anchor not found: {old!r}"
    return source.replace(old, new, 1)


class ActIIIMixin:
    """Shared checks; each level's TestCase mixes this in."""
    slug = ""
    solution = ""

    @classmethod
    def setUpClass(cls):
        cls.mission = load_mission(cls.slug)

    def describe(self, report) -> str:
        lines = [f"status={report['status']} error={report['error']}"]
        lines += [f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['name']}: {c['message']} | {c['hint']}"
                  for c in report["checks"]]
        return "\n".join(lines)

    def assert_victory(self, report):
        self.assertEqual(report["status"], "ok", self.describe(report))
        self.assertEqual(len(report["checks"]), len(self.mission.checks))
        self.assertTrue(all(c["passed"] for c in report["checks"]), self.describe(report))
        self.assertLess(report["elapsed"], self.mission.timeout, "grading must finish well under the timeout")
        self.assertFalse([n for n in report["folder"] if n.startswith(".grader")],
                         "the grader's scratch files must be cleaned up")

    def assert_fails_on(self, report, layer: str, *teaches: str, first: bool = True):
        """`layer` failed (and, by default, is the first red layer); its text contains every fragment."""
        self.assertNotEqual(report["status"], "harness_error", self.describe(report))
        failed = [c for c in report["checks"] if not c["passed"]]
        self.assertTrue(failed, "expected a failing layer:\n" + self.describe(report))
        target = next((c for c in failed if layer in c["name"]), None)
        self.assertIsNotNone(target, f"layer {layer!r} should fail:\n" + self.describe(report))
        if first:
            self.assertIs(target, failed[0], f"{layer!r} should be the first red layer:\n" + self.describe(report))
        self.assertTrue(target["message"].strip(), "failure needs a message")
        self.assertTrue(target["hint"].strip(), "failure needs a teaching hint")
        text = target["message"] + " " + target["hint"]
        for fragment in teaches:
            self.assertIn(fragment, text, self.describe(report))
        return target

    # every Act III level gets these three for free
    def test_starter_is_not_a_victory(self):
        report = grade(self.slug, self.mission.starter.lstrip("\n"))
        self.assertNotIn(report["status"], ("harness_error", "timeout"), self.describe(report))
        self.assertFalse(report["status"] == "ok" and all(c["passed"] for c in report["checks"]),
                         "the untouched starter must not clear the level")
        self.assertTrue(any(not c["passed"] and c["message"] for c in report["checks"]))

    def test_reference_solution_clears_every_layer(self):
        self.assert_victory(grade(self.slug, self.solution))

    def test_mission_contract(self):
        m = self.mission
        self.assertEqual(m.slug, self.slug)
        self.assertEqual(m.tier, 3)                          # S2 ARCHITECT = Intermediate
        self.assertTrue(m.concepts and set(m.concepts) <= set(CONCEPTS), m.concepts)
        self.assertTrue(5 <= len(m.checks) <= 9)
        self.assertLessEqual(len(re.sub(r"```.*?```", "", m.briefing, flags=re.S).split()), 130)
        self.assertLessEqual(len(re.sub(r"```.*?```", "", m.why, flags=re.S).split()), 160)
        self.assertIn("**", m.briefing.strip().splitlines()[-1], "briefing ends with a bold call to action")
        art = m.enemy_art.splitlines()
        self.assertTrue(len(art) <= 7 and max(map(len, art)) <= 20)
        self.assertIn("OBJECTIVE 1", m.starter)
        self.assertIn("CORRUPTED CODE", m.starter)
        low, high = (330, 450) if m.boss else (220, 300)
        self.assertTrue(low <= m.xp <= high, m.xp)
        self.assertEqual(set(m.dialogue), {"intro", "crash", "fail", "victory"})
        lines = list(m.dialogue["intro"]) + list(m.dialogue["victory"])
        for pool in ("crash", "fail"):
            self.assertTrue(m.dialogue[pool])
            for sequence in m.dialogue[pool]:
                self.assertTrue(1 <= len(sequence) <= 2)
                lines += sequence
        for line in lines:
            self.assertLessEqual(len(line["text"]), 160, line["text"])
            self.assertIn(line["mood"], ("neutral", "smirk", "alarm", "warm", "cold"))
            self.assertIn(line["speaker"], ("cipher", "vex", "rust", "nova", "oracle", "forgemaster"))


class Level11BlueprintsTests(ActIIIMixin, unittest.TestCase):
    slug = "level_11_blueprints"
    solution = L11_SOLUTION

    def test_victory_broadcasts_the_scout(self):
        self.assertIn("Drone(name='Kite', battery=80)", grade(self.slug, self.solution)["stdout"])

    def test_method_without_self_is_explained(self):
        report = grade(self.slug, mutate(self.solution, "def load(self, item):", "def load(item):"))
        self.assert_fails_on(report, "Cargo bay", "self")

    def test_local_variable_instead_of_attribute(self):
        report = grade(self.slug, mutate(self.solution, "self.battery = min(100, self.battery + amount)",
                                         "battery = min(100, self.battery + amount)"))
        self.assert_fails_on(report, "Recharge", "self.battery")

    def test_hard_coded_repr_is_caught_by_fresh_drones(self):
        report = grade(self.slug, mutate(self.solution, "return f\"Drone(name='{self.name}', battery={self.battery})\"",
                                         "return \"Drone(name='Kite', battery=80)\""))
        self.assert_fails_on(report, "Identity readout", "THIS drone")

    def test_exactly_enough_battery_is_enough(self):
        report = grade(self.slug, mutate(self.solution, "if cost > self.battery:", "if cost >= self.battery:"))
        self.assert_fails_on(report, "Flight", "<=")


class Level12BloodlinesTests(ActIIIMixin, unittest.TestCase):
    slug = "level_12_bloodlines"
    solution = L12_SOLUTION

    def test_victory_roll_call(self):
        out = grade(self.slug, self.solution)["stdout"]
        for line in ("Kite [scout] 80%", "Mule [hauler] 100%", "Sal [medic] 60%"):
            self.assertIn(line, out)

    def test_unrepaired_medic_must_call_super(self):
        report = grade(self.slug, mutate(self.solution, "        super().__init__(name, battery)\n        self.kits = kits",
                                         "        self.kits = kits"))
        self.assert_fails_on(report, "Medic line", "super().__init__")

    def test_type_checks_miss_unknown_bloodlines(self):
        report = grade(self.slug, mutate(self.solution, "if distance * d.burn_rate() <= d.battery",
                                         "if distance * (1 if isinstance(d, Scout) else 2) <= d.battery"))
        self.assert_fails_on(report, "Polymorphism", "never seen")

    def test_hauler_must_build_on_parent_rate(self):
        report = grade(self.slug, mutate(self.solution, "return super().burn_rate() + len(self.cargo)",
                                         "return 2 + len(self.cargo)"))
        self.assert_fails_on(report, "Hauler line", "super().burn_rate()")

    def test_plain_class_is_not_a_dataclass(self):
        report = grade(self.slug, mutate(self.solution, "@dataclass\nclass Pedigree:", "class Pedigree:"))
        self.assert_fails_on(report, "Paperwork", "@dataclass")


class Level13BlackBoxTests(ActIIIMixin, unittest.TestCase):
    slug = "level_13_black_box"
    solution = L13_SOLUTION

    def test_victory_writes_the_evidence_to_disk(self):
        report = grade(self.slug, self.solution)
        self.assert_victory(report)
        self.assertEqual(report["files"]["recovered_voice.txt"].count("UNKNOWN:"), 4)
        self.assertIn('"ENGINE 2 FIRE, SUPPRESSION FAILED"', report["files"]["flight_events.csv"])
        self.assertEqual(report["files"]["flight_log.csv"], self.mission.assets["flight_log.csv"],
                         "the black box asset must be left untouched")
        self.assertIn("finish what I started", report["stdout"])

    def test_splitting_csv_on_commas_breaks_quoted_events(self):
        source = mutate(self.solution, '''    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({"t": int(row["t"]), "altitude": int(row["altitude"]),
                         "speed": int(row["speed"]), "event": row["event"]})''', '''    with open(path, encoding="utf-8") as f:
        next(f)
        for line in f:
            t, altitude, speed, event = line.rstrip("\\n").split(",", 3)
            rows.append({"t": int(t), "altitude": int(altitude), "speed": int(speed), "event": event})''')
        self.assert_fails_on(grade(self.slug, source), "Decode the telemetry", "csv")

    def test_append_mode_piles_up_transcripts(self):
        report = grade(self.slug, mutate(self.solution, 'open(path, "w", encoding="utf-8")',
                                         'open(path, "a", encoding="utf-8")'))
        self.assert_fails_on(report, "transcript writer", 'Mode "a"')

    def test_untouched_corrupted_writer(self):
        source = mutate(self.solution, '''    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\\n")''', '''    with open(path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line)''')
        self.assert_fails_on(grade(self.slug, source), "transcript writer", "newline")

    def test_reader_that_ignores_its_path_fails_on_fresh_files(self):
        report = grade(self.slug, mutate(self.solution, "def read_lines(path):\n    lines = []\n    with open(path,",
                                         "def read_lines(path):\n    lines = []\n    with open(HERE / \"voice_recorder.txt\","))
        self.assert_fails_on(report, "Read the recording", "read_lines() returned")

    def test_open_without_with(self):
        source = mutate(self.solution, '''    lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            clean = line.strip()
            if clean:
                lines.append(clean)
    return lines''', '''    lines = []
    f = open(path, encoding="utf-8")
    for line in f:
        clean = line.strip()
        if clean:
            lines.append(clean)
    f.close()
    return lines''')
        self.assert_fails_on(grade(self.slug, source), "Read the recording", "with")

    def test_hand_typed_evidence_is_rejected(self):
        unknown = [line.strip() for line in self.mission.assets["voice_recorder.txt"].splitlines() if "UNKNOWN:" in line]
        report = grade(self.slug, mutate(self.solution, 'unknown = [line for line in voice if "UNKNOWN:" in line]',
                                         f"unknown = {unknown!r}"))
        self.assert_fails_on(report, "Pull the evidence", "typed in")


class Level14FailsafeTests(ActIIIMixin, unittest.TestCase):
    slug = "level_14_failsafe"
    solution = L14_SOLUTION

    def test_victory_report_line(self):
        self.assertIn("FAILSAFE | ok=4 | faults=4 | overheats=2", grade(self.slug, self.solution)["stdout"])

    def test_unrepaired_except_order(self):
        source = mutate(self.solution, '''        except OverheatError:
            report["overheats"] += 1
        except SensorError:
            report["faults"] += 1''', '''        except SensorError:
            report["faults"] += 1
        except OverheatError:
            report["overheats"] += 1''')
        self.assert_fails_on(grade(self.slug, source), "Alarm board", "FIRST except")

    def test_raw_value_error_must_not_escape(self):
        source = mutate(self.solution, '''    try:
        value = float(text)
    except ValueError:
        raise SensorError(f"unreadable: {text!r}")''', "    value = float(text)")
        self.assert_fails_on(grade(self.slug, source), "Sensor parser", "ValueError", "SensorError")

    def test_custom_exception_needs_super_message(self):
        report = grade(self.slug, mutate(self.solution, '        super().__init__(f"core at {temp} exceeds limit {limit}")\n', ""))
        self.assert_fails_on(report, "Alarm family", "super().__init__")

    def test_unlock_without_finally_leaves_furnace_locked(self):
        source = mutate(self.solution, '''    furnace.lock()
    try:
        report = triage(readings, limit)
        if report["overheats"]:
            furnace.vent()
        return report
    finally:
        furnace.unlock()''', '''    furnace.lock()
    report = triage(readings, limit)
    if report["overheats"]:
        furnace.vent()
    furnace.unlock()
    return report''')
        self.assert_fails_on(grade(self.slug, source), "Furnace failsafe", "LOCKED", "finally")

    def test_lock_inside_try_releases_someone_elses_lock(self):
        source = mutate(self.solution, "    furnace.lock()\n    try:\n        report", "    try:\n        furnace.lock()\n        report")
        self.assert_fails_on(grade(self.slug, source), "Furnace failsafe", "BEFORE try")

    def test_swallowing_every_error_is_not_a_failsafe(self):
        source = mutate(self.solution, '''        return report
    finally:''', '''        return report
    except Exception:
        return None
    finally:''')
        self.assert_fails_on(grade(self.slug, source), "Furnace failsafe", "catches every possible error")


class Level15ForgemasterTests(ActIIIMixin, unittest.TestCase):
    slug = "level_15_the_forgemaster"
    solution = L15_SOLUTION

    def test_victory_reveals_the_signature(self):
        report = grade(self.slug, self.solution)
        self.assert_victory(report)
        self.assertIn("FORGE AUDIT | samples=15 | rejected=7 | train=12 | test=3 | signer=K-7F3A", report["stdout"])

    def test_boss_cutscene_and_voice(self):
        m = self.mission
        self.assertTrue(m.boss)
        self.assertIsNotNone(m.cutscene)
        self.assertTrue(3 <= len(m.cutscene.narration) <= 6)
        self.assertTrue(m.cutscene.shot and m.cutscene.camera)
        self.assertFalse(any("{callsign}" in line for line in m.cutscene.narration),
                         "narration isn't callsign-substituted by the client")
        self.assertEqual(m.dialogue["intro"][0]["speaker"], "forgemaster")
        self.assertEqual(m.dialogue["victory"][0]["speaker"], "forgemaster")
        self.assertIn("forge_shards.csv", m.assets)

    def test_leaky_split_is_caught(self):
        report = grade(self.slug, mutate(self.solution, "order[n_test:]", "order[n_test - 1:]"))
        self.assert_fails_on(report, "leak sealed", "BOTH")

    def test_split_without_validation(self):
        report = grade(self.slug, mutate(self.solution, '''        if not 0 < test_ratio < 1:
            raise ValueError(f"test_ratio must be between 0 and 1, got {test_ratio}")
''', ""))
        self.assert_fails_on(report, "refuses bad ratios", "ValueError")

    def test_short_rows_need_type_error_too(self):
        report = grade(self.slug, mutate(self.solution, "except (ValueError, TypeError):", "except ValueError:"))
        self.assert_fails_on(report, "parse_row", "TypeError")

    def test_signers_of_rejected_rows_leak_into_the_audit(self):
        source = mutate(self.solution, '''                try:
                    sample = parse_row(row)''', '''                self.signers.add((row["signer"] or "").strip())
                try:
                    sample = parse_row(row)''')
        self.assert_fails_on(grade(self.slug, source), "signers recorded", "KEPT")

    def test_dataset_that_ignores_its_path_fails_on_grader_files(self):
        report = grade(self.slug, mutate(self.solution, 'with open(path, newline="", encoding="utf-8") as f:',
                                         'with open(HERE / "forge_shards.csv", newline="", encoding="utf-8") as f:'))
        self.assert_fails_on(report, "loads and cleans a CSV", "kept 15 samples")

    def test_hand_typed_signature_is_rejected(self):
        report = grade(self.slug, mutate(self.solution, 'signature = ", ".join(sorted(forge.signers))',
                                         'signature = "K-7F3A"'))
        self.assert_fails_on(report, "Final stage", "typed in")


if __name__ == "__main__":
    unittest.main()
