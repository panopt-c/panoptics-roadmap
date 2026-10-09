"""Act II // THE ORDER (L06-L10), graded through the REAL subprocess grader.

For every level: the untouched starter must not win; a correct reference solution must
clear every firewall layer; realistic wrong solutions must fail on the right layer with a
message that teaches. Each grade runs `python -m engine.harness <slug> <file> <report>`
from the code root, with the mission's assets written beside the player's file, exactly
as the game does.

L06-L08 come before `def`, so their layers REPLAY the player's whole script with fresh
sensor feeds; several tests here prove a hard-coded answer can't survive that.
"""
from __future__ import annotations

import importlib
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
ACT2 = ("level_06_tripwire", "level_07_patrol_routes", "level_08_overclock",
        "level_09_subroutines", "level_10_the_arbiter")


# ── reference solutions (what a strong player would write) ──────────────────────

L06_SOLUTION = r'''
# == SENSOR FEED (one tripwire, right now) ===================================
motion = 0.82
heat = 36.4
badge = "  GRID-7 "
hour = 2
signal = 74

CLEARED = ["order", "runner", "trader"]

is_moving = motion > 0.3
is_warm = 35.0 <= heat <= 40.0
is_cleared = badge.strip().lower() in CLEARED
is_night = hour >= 22 or hour < 6

if is_cleared:
    gate = "OPEN"
elif not is_moving:
    gate = "IDLE"
elif not is_warm:
    gate = "DRONE"
elif is_night:
    gate = "SEAL"
else:
    gate = "WATCH"

if signal >= 90:
    threat = "CRITICAL"
elif signal >= 70:
    threat = "HIGH"
elif signal >= 40:
    threat = "LOW"
else:
    threat = "NONE"

print(f"TRIPWIRE | gate={gate} | threat={threat}")
'''

L07_SOLUTION = r'''
route = ["N4", "N5", "E2", "E3", "S1"]
dwell = [12, 7, 30, 4, 9]
laps = 3
grid = [
    [0, 2, 0, 1],
    [3, 0, 0, 0],
    [0, 1, 4, 0],
]

sweep_time = 0
for seconds in dwell:
    sweep_time += seconds

checkpoints = []
for n, sector in enumerate(route, start=1):
    checkpoints.append(f"{n}:{sector}")

longest_stop = None
most = -1
for sector, seconds in zip(route, dwell):
    if seconds > most:
        longest_stop = sector
        most = seconds

lap_starts = []
for lap in range(laps):
    lap_starts.append(lap * sweep_time)

quick_sectors = [sector for sector, seconds in zip(route, dwell) if seconds < 10]

sentinels = 0
for street in grid:
    for count in street:
        sentinels += count

safe_cells = []
for r, street in enumerate(grid):
    for c, count in enumerate(street):
        if count == 0:
            safe_cells.append((r, c))

print(f"PATROL | sweep={sweep_time}s | sentinels={sentinels} | safe={len(safe_cells)}")
'''

L08_SOLUTION = r'''
start_pressure = 96
safe_pressure = 40
vent_size = 15

readings = [41, -1, 38, 44, -1, 97, 40]
meltdown = 90

start_output = 12.0
target = 100.0
gain = 0.5
tolerance = 0.01
max_cycles = 50

pressure = start_pressure
vents = 0
while pressure > safe_pressure:
    pressure -= vent_size
    vents += 1

stable = []
spike_at = -1
for i, value in enumerate(readings):
    if value == -1:
        continue
    if value >= meltdown:
        spike_at = i
        break
    stable.append(value)

output = start_output
cycles = 0
while abs(target - output) >= tolerance and cycles < max_cycles:
    output = output + (target - output) * gain
    cycles += 1

converged = abs(target - output) < tolerance

print(f"REACTOR | vents={vents} | spike_at={spike_at} | cycles={cycles} | converged={converged}")
'''

L09_SOLUTION = r'''
def clean_id(raw):
    """Return the id stripped and uppercased."""
    return raw.strip().upper()


def clamp(value, low=0, high=100):
    """Return value limited to the range low..high."""
    if value < low:
        return low
    if value > high:
        return high
    return value


def normalize(value, low, high):
    """Scale value into 0.0..1.0 after clamping it into low..high."""
    if high == low:
        return 0.0
    clamped = clamp(value, low, high)
    return (clamped - low) / (high - low)


def count_red(levels):
    """Return how many levels are exactly "RED"."""
    red_total = 0
    for level in levels:
        if level == "RED":
            red_total += 1
    return red_total


def rank(records, top=3):
    """Return the ids of the `top` strongest records, ties alphabetical."""
    ordered = sorted(records, key=lambda r: (-r["strength"], r["id"]))
    return [r["id"] for r in ordered][:top]


CENSUS = [
    {"id": "  sig-0412 ", "strength": 88},
    {"id": "vx-0007", "strength": 140},
    {"id": " SIG-0099\n", "strength": -5},
    {"id": "grid-3", "strength": 88},
    {"id": "Sig-0150", "strength": 61},
]

cleaned = [{"id": clean_id(r["id"]), "strength": clamp(r["strength"])} for r in CENSUS]

watchlist = rank(cleaned, top=2)
names = ", ".join(watchlist)
print(f"WATCHLIST | {names}")
'''

L10_SOLUTION = r'''
from tribunal import EVIDENCE, arbiter_verdict


def confusion(predictions, labels):
    """Count true/false positives/negatives of predictions against labels."""
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for predicted, actual in zip(predictions, labels):
        if predicted and actual:
            counts["tp"] += 1
        elif predicted:
            counts["fp"] += 1
        elif actual:
            counts["fn"] += 1
        else:
            counts["tn"] += 1
    return counts


def accuracy(cm):
    total = cm["tp"] + cm["fp"] + cm["fn"] + cm["tn"]
    if total == 0:
        return 0.0
    return (cm["tp"] + cm["tn"]) / total


def precision(cm):
    flagged = cm["tp"] + cm["fp"]
    if flagged == 0:
        return 0.0
    return cm["tp"] / flagged


def recall(cm):
    real = cm["tp"] + cm["fn"]
    if real == 0:
        return 0.0
    return cm["tp"] / real


def evaluate(records, judge):
    predictions = [judge(r) for r in records]
    labels = [r["hostile"] for r in records]
    return confusion(predictions, labels)


arbiter_cm = evaluate(EVIDENCE, arbiter_verdict)
arbiter_precision = precision(arbiter_cm)
arbiter_recall = recall(arbiter_cm)


def classify(record):
    return record["heat"] < 32.0 or (record["carrier"] > 80 and record["speed"] > 4.0)


order_cm = evaluate(EVIDENCE, classify)
order_precision = precision(order_cm)
order_recall = recall(order_cm)


def pardons(records):
    return sorted(r["id"] for r in records if arbiter_verdict(r) and not classify(r))


appeals = pardons(EVIDENCE)
print(f"TRIBUNAL | arbiter precision={arbiter_precision:.2f} recall={arbiter_recall:.2f} | "
      f"order precision={order_precision:.2f} recall={order_recall:.2f} | pardons={len(appeals)}")
'''


# ── grading through the real harness ─────────────────────────────────────────────

def grade(slug: str, source: str) -> dict:
    """Write the player's file + assets to a fresh folder and run the sandboxed grader on it."""
    mission = load_mission(slug)
    with tempfile.TemporaryDirectory(prefix="ns-act2-") as tmp:
        folder = Path(tmp)
        player = folder / mission.filename
        player.write_bytes(source.lstrip("\n").encode("utf-8"))
        for name, text in mission.assets.items():
            (folder / name).write_bytes(text.encode("utf-8"))
        out = folder / "report.json"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        started = time.monotonic()
        try:
            proc = subprocess.run([sys.executable, "-m", "engine.harness", slug, str(player), str(out)],
                                  cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                  timeout=mission.timeout)
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "checks": [], "error": None, "stdout": "",
                    "elapsed": time.monotonic() - started, "folder": []}
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


class ActIIMixin:
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
        self.assertLess(report["elapsed"], self.mission.timeout / 2, "grading must finish well under the timeout")

    def assert_fails_on(self, report, layer: str, *teaches: str, first: bool = True):
        """`layer` failed (and, by default, is the first red layer); its text contains every fragment."""
        self.assertNotIn(report["status"], ("harness_error", "timeout"), self.describe(report))
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

    # every Act II level gets these for free
    def test_starter_is_not_a_victory(self):
        report = grade(self.slug, self.mission.starter)
        self.assertNotIn(report["status"], ("harness_error", "timeout"), self.describe(report))
        self.assertFalse(report["status"] == "ok" and all(c["passed"] for c in report["checks"]),
                         "the untouched starter must not clear the level")
        self.assertTrue(any(not c["passed"] and c["message"] for c in report["checks"]))

    def test_reference_solution_clears_every_layer(self):
        self.assert_victory(grade(self.slug, self.solution))

    def test_mission_contract(self):
        m = self.mission
        self.assertEqual(m.slug, self.slug)
        self.assertEqual(m.tier, 2)                          # S1 LOGIC = Beginner+
        self.assertTrue(m.concepts and set(m.concepts) <= set(CONCEPTS), m.concepts)
        self.assertTrue(5 <= len(m.checks) <= 9)
        self.assertLessEqual(len(re.sub(r"```.*?```", "", m.briefing, flags=re.S).split()), 130)
        self.assertLessEqual(len(re.sub(r"```.*?```", "", m.why, flags=re.S).split()), 160)
        self.assertIn("**", m.briefing.strip().splitlines()[-1], "briefing ends with a bold call to action")
        art = m.enemy_art.splitlines()
        self.assertTrue(len(art) <= 7 and max(map(len, art)) <= 20)
        self.assertIn("OBJECTIVE 1", m.starter)
        self.assertIn("CORRUPTED CODE", m.starter)
        low, high = (225, 330) if m.boss else (150, 220)
        self.assertTrue(low <= m.xp <= high, m.xp)
        self.assertLessEqual(m.timeout, 20)
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
            self.assertIn(line["speaker"], ("cipher", "vex", "rust", "nova", "oracle", "arbiter"))
        if m.boss:
            self.assertIsNotNone(m.cutscene)
            self.assertTrue(3 <= len(m.cutscene.narration) <= 6)
            self.assertTrue(m.cutscene.shot and m.cutscene.camera)
            self.assertTrue(any(l["speaker"] == "arbiter" for l in m.dialogue["intro"]))


class Level06TripwireTests(ActIIMixin, unittest.TestCase):
    slug = "level_06_tripwire"
    solution = L06_SOLUTION

    def test_victory_reports_to_nova(self):
        self.assertIn("TRIPWIRE | gate=SEAL | threat=HIGH", grade(self.slug, self.solution)["stdout"])

    def test_at_least_instead_of_above(self):
        report = grade(self.slug, mutate(self.solution, "motion > 0.3", "motion >= 0.3"))
        self.assert_fails_on(report, "Motion tripwire", "motion=0.3", "use > (above)")

    def test_night_shift_with_and_is_never_true(self):
        report = grade(self.slug, mutate(self.solution, "hour >= 22 or hour < 6", "hour >= 22 and hour < 6"))
        self.assert_fails_on(report, "Night shift", "always False", "OR")

    def test_badge_not_cleaned(self):
        report = grade(self.slug, mutate(self.solution, "badge.strip().lower() in CLEARED", "badge in CLEARED"))
        self.assert_fails_on(report, "Clearance scan", ".strip()")

    def test_unrepaired_threat_ladder(self):
        broken = mutate(self.solution, '''if signal >= 90:
    threat = "CRITICAL"
elif signal >= 70:
    threat = "HIGH"
elif signal >= 40:
    threat = "LOW"''', '''if signal >= 40:
    threat = "LOW"
elif signal >= 70:
    threat = "HIGH"
elif signal >= 90:
    threat = "CRITICAL"''')
        self.assert_fails_on(grade(self.slug, broken), "threat ladder", "signal=74", "highest bar at the top")

    def test_protocol_in_wrong_order(self):
        # Checking "idle" before "cleared" leaves a resting Order member locked out.
        broken = mutate(self.solution, '''if is_cleared:
    gate = "OPEN"
elif not is_moving:
    gate = "IDLE"''', '''if not is_moving:
    gate = "IDLE"
elif is_cleared:
    gate = "OPEN"''')
        self.assert_fails_on(grade(self.slug, broken), "Perimeter protocol", "expected 'OPEN'", "FIRST branch")

    def test_hard_coded_gate_fails_on_fresh_readings(self):
        broken = re.sub(r'if is_cleared:.*?gate = "WATCH"\n', 'gate = "SEAL"\n', self.solution, flags=re.S)
        self.assertIn('gate = "SEAL"', broken)
        self.assert_fails_on(grade(self.slug, broken), "Perimeter protocol", "expected")

    def test_missing_else_leaves_gate_undefined(self):
        broken = mutate(self.solution, '''else:
    gate = "WATCH"''', "")
        self.assert_fails_on(grade(self.slug, broken), "Perimeter protocol", "never given a value", "else:")

    def test_typed_status_line(self):
        broken = mutate(self.solution, 'print(f"TRIPWIRE | gate={gate} | threat={threat}")',
                        'print("TRIPWIRE | gate=SEAL | threat=HIGH")')
        self.assert_fails_on(grade(self.slug, broken), "Report to NOVA", "doesn't use the `gate` variable")


class Level07PatrolRoutesTests(ActIIMixin, unittest.TestCase):
    slug = "level_07_patrol_routes"
    solution = L07_SOLUTION

    def test_victory_sends_the_map(self):
        self.assertIn("PATROL | sweep=62s | sentinels=11 | safe=7", grade(self.slug, self.solution)["stdout"])

    def test_sum_skips_the_loop_lesson(self):
        broken = mutate(self.solution, '''sweep_time = 0
for seconds in dwell:
    sweep_time += seconds''', "sweep_time = sum(dwell)")
        self.assert_fails_on(grade(self.slug, broken), "Full sweep", "sum()")

    def test_unrepaired_census_counts_last_street(self):
        broken = mutate(self.solution, '''for street in grid:
    for count in street:''', '''for street in grid:
    sentinels = 0
    for count in street:''')
        self.assert_fails_on(grade(self.slug, broken), "Repair the census", "LAST street")

    def test_tie_keeps_the_last_stop(self):
        broken = mutate(self.solution, "if seconds > most:", "if seconds >= most:")
        self.assert_fails_on(grade(self.slug, broken), "Longest stop", "tie", "strictly bigger")

    def test_enumerate_from_zero(self):
        broken = mutate(self.solution, "enumerate(route, start=1)", "enumerate(route)")
        self.assert_fails_on(grade(self.slug, broken), "Number the stops", "start=1")

    def test_hard_coded_gaps_are_not_a_comprehension(self):
        broken = mutate(self.solution,
                        "quick_sectors = [sector for sector, seconds in zip(route, dwell) if seconds < 10]",
                        'quick_sectors = ["N5", "E3", "S1"]')
        self.assert_fails_on(grade(self.slug, broken), "Find the gaps", "list comprehension")

    def test_fixed_width_scan_misses_ragged_streets(self):
        broken = mutate(self.solution, '''    for c, count in enumerate(street):
        if count == 0:''', '''    for c in range(len(grid[0])):
        count = street[c]
        if count == 0:''')
        self.assert_fails_on(grade(self.slug, broken), "Safe blocks", "different lengths")

    def test_hard_coded_lap_schedule(self):
        broken = mutate(self.solution, '''lap_starts = []
for lap in range(laps):
    lap_starts.append(lap * sweep_time)''', '''lap_starts = []
for lap in range(laps):
    lap_starts = [0, 62, 124]''')
        self.assert_fails_on(grade(self.slug, broken), "Shift schedule", "laps")


class Level08OverclockTests(ActIIMixin, unittest.TestCase):
    slug = "level_08_overclock"
    solution = L08_SOLUTION

    def test_victory_reactor_report(self):
        out = grade(self.slug, self.solution)["stdout"]
        self.assertIn("REACTOR | vents=4 | spike_at=5 | cycles=14 | converged=True", out)

    def test_unrepaired_vent_never_runs(self):
        broken = mutate(self.solution, "while pressure > safe_pressure:", "while pressure < safe_pressure:")
        self.assert_fails_on(grade(self.slug, broken), "Vent the line", "never ran")

    def test_vent_one_too_many(self):
        broken = mutate(self.solution, "while pressure > safe_pressure:", "while pressure >= safe_pressure:")
        self.assert_fails_on(grade(self.slug, broken), "Vent the line", "One vent too many")

    def test_glitches_not_skipped(self):
        broken = mutate(self.solution, '''    if value == -1:
        continue
''', "")
        self.assert_fails_on(grade(self.slug, broken), "Skip the glitches", "continue")

    def test_spike_index_only_set_inside_the_loop(self):
        broken = mutate(self.solution, "spike_at = -1\n", "")
        self.assert_fails_on(grade(self.slug, broken), "Catch the spike", "never given a value")

    def test_signed_distance_misses_overshoot(self):
        broken = self.solution.replace("abs(target - output) >= tolerance", "target - output >= tolerance")
        self.assert_fails_on(grade(self.slug, broken), "Overclock", "ABOVE target", "abs(target - output)")

    def test_no_guardrail_never_stops(self):
        broken = mutate(self.solution, "abs(target - output) >= tolerance and cycles < max_cycles",
                        "abs(target - output) >= tolerance")
        report = grade(self.slug, broken)
        self.assert_fails_on(report, "Guardrail", "never converges", "max_cycles")
        self.assertLess(report["elapsed"], self.mission.timeout, "the line budget must beat the grader timeout")

    def test_step_before_checking(self):
        broken = mutate(self.solution, '''while abs(target - output) >= tolerance and cycles < max_cycles:
    output = output + (target - output) * gain
    cycles += 1''', '''while True:
    output = output + (target - output) * gain
    cycles += 1
    if abs(target - output) < tolerance or cycles >= max_cycles:
        break''')
        self.assert_fails_on(grade(self.slug, broken), "Overclock", "0 cycles")


class Level09SubroutinesTests(ActIIMixin, unittest.TestCase):
    slug = "level_09_subroutines"
    solution = L09_SOLUTION

    def test_victory_watchlist(self):
        self.assertIn("WATCHLIST | VX-0007, GRID-3", grade(self.slug, self.solution)["stdout"])

    def test_print_instead_of_return(self):
        broken = mutate(self.solution, "    return raw.strip().upper()", "    print(raw.strip().upper())")
        self.assert_fails_on(grade(self.slug, broken), "First rite", "returned None", "return")

    def test_clamp_without_defaults(self):
        broken = mutate(self.solution, "def clamp(value, low=0, high=100):", "def clamp(value, low, high):")
        self.assert_fails_on(grade(self.slug, broken), "Boundaries", "default values")

    def test_normalize_must_reuse_clamp(self):
        broken = mutate(self.solution, "    clamped = clamp(value, low, high)",
                        "    clamped = min(max(value, low), high)")
        self.assert_fails_on(grade(self.slug, broken), "A rite calls a rite", "doesn't call your clamp()")

    def test_normalize_divides_by_zero(self):
        broken = mutate(self.solution, '''    if high == low:
        return 0.0
    clamped''', "    clamped")
        self.assert_fails_on(grade(self.slug, broken), "A rite calls a rite", "ZeroDivisionError", "high == low")

    def test_unrepaired_scope_breach(self):
        broken = mutate(self.solution, '''def count_red(levels):
    """Return how many levels are exactly "RED"."""
    red_total = 0
''', '''red_total = 0


def count_red(levels):
    """Return how many levels are exactly "RED"."""
''')
        self.assert_fails_on(grade(self.slug, broken), "scope breach", "UnboundLocalError", "inside the function")

    def test_global_count_remembers_old_calls(self):
        broken = mutate(self.solution, '''def count_red(levels):
    """Return how many levels are exactly "RED"."""
    red_total = 0
''', '''red_total = 0


def count_red(levels):
    """Return how many levels are exactly "RED"."""
    global red_total
''')
        self.assert_fails_on(grade(self.slug, broken), "scope breach", "global")

    def test_rank_sorts_the_callers_list(self):
        broken = mutate(self.solution, '''    ordered = sorted(records, key=lambda r: (-r["strength"], r["id"]))''',
                        '''    records.sort(key=lambda r: (-r["strength"], r["id"]))
    ordered = records''')
        self.assert_fails_on(grade(self.slug, broken), "Order of standing", "changed the list")

    def test_rank_ignores_ties(self):
        broken = mutate(self.solution, 'key=lambda r: (-r["strength"], r["id"])', 'key=lambda r: -r["strength"]')
        self.assert_fails_on(grade(self.slug, broken), "Order of standing", "ties go alphabetical")

    def test_missing_docstring(self):
        broken = mutate(self.solution, '    """Return value limited to the range low..high."""\n', "")
        self.assert_fails_on(grade(self.slug, broken), "Name it", "`clamp` has no docstring")

    def test_typed_watchlist(self):
        broken = mutate(self.solution, 'print(f"WATCHLIST | {names}")', 'print("WATCHLIST | VX-0007, GRID-3")')
        self.assert_fails_on(grade(self.slug, broken), "Post the watchlist", "typed into your code")


class Level10ArbiterTests(ActIIMixin, unittest.TestCase):
    slug = "level_10_the_arbiter"
    solution = L10_SOLUTION

    def test_victory_tribunal_report(self):
        out = grade(self.slug, self.solution)["stdout"]
        self.assertIn("TRIBUNAL | arbiter precision=0.44 recall=0.57 | order precision=1.00 recall=1.00 | pardons=5",
                      out)

    def test_cutscene_sets_up_the_arena(self):
        m = self.mission
        self.assertTrue(m.boss)
        self.assertTrue(any("VEX" in line for line in m.cutscene.narration))
        self.assertEqual(m.dialogue["victory"][-1]["speaker"], "vex")
        self.assertIn("Arena", m.dialogue["victory"][-1]["text"])

    def test_tribunal_asset_matches_the_reference_court(self):
        namespace: dict = {}
        exec(self.mission.assets["tribunal.py"], namespace)
        level = importlib.import_module("levels.level_10_the_arbiter")
        self.assertEqual(namespace["EVIDENCE"], level.EVIDENCE)
        self.assertTrue(all(level._classify(r) == r["hostile"] for r in level.EVIDENCE),
                        "the Order's finding must explain every verified case")
        self.assertTrue(all(namespace["arbiter_verdict"](r) == level._arbiter(r) for r in level.DOCKET))

    def test_unrepaired_confusion_counts_one_pair(self):
        broken = mutate(self.solution, '''        else:
            counts["tn"] += 1
    return counts''', '''        else:
            counts["tn"] += 1
        return counts''')
        self.assert_fails_on(grade(self.slug, broken), "Repair the tally", "FIRST pair", "after the loop")

    def test_precision_without_zero_guard(self):
        broken = mutate(self.solution, '''    flagged = cm["tp"] + cm["fp"]
    if flagged == 0:
        return 0.0
''', '''    flagged = cm["tp"] + cm["fp"]
''')
        self.assert_fails_on(grade(self.slug, broken), "Score a judge", "divided by zero", "return 0.0")

    def test_inclusive_heat_boundary(self):
        broken = mutate(self.solution, 'record["heat"] < 32.0', 'record["heat"] <= 32.0')
        self.assert_fails_on(grade(self.slug, broken), "A better judge", "32.0", "use <, not <=")

    def test_or_instead_of_and(self):
        broken = mutate(self.solution, 'record["carrier"] > 80 and record["speed"] > 4.0',
                        'record["carrier"] > 80 or record["speed"] > 4.0')
        self.assert_fails_on(grade(self.slug, broken), "A better judge", "`and` vs `or`")

    def test_memorised_evidence_fails_the_hidden_docket(self):
        broken = mutate(self.solution,
                        '    return record["heat"] < 32.0 or (record["carrier"] > 80 and record["speed"] > 4.0)',
                        '    return record["id"] in [r["id"] for r in EVIDENCE if r["hostile"]]')
        self.assert_fails_on(grade(self.slug, broken), "A better judge", "DKT-")

    def test_arbiter_cm_typed_by_hand(self):
        broken = mutate(self.solution, "arbiter_cm = evaluate(EVIDENCE, arbiter_verdict)",
                        'arbiter_cm = {"tp": 4, "fp": 5, "fn": 3, "tn": 4}')
        self.assert_fails_on(grade(self.slug, broken), "The ARBITER's record", "evaluate(EVIDENCE, arbiter_verdict)")

    def test_judge_called_instead_of_passed(self):
        broken = mutate(self.solution, '''    predictions = [judge(r) for r in records]''',
                        '''    predictions = [arbiter_verdict(r) for r in records]''')
        self.assert_fails_on(grade(self.slug, broken), "Cross-examine", "always says hostile")

    def test_report_without_two_decimals(self):
        broken = self.solution.replace(":.2f}", "}")
        self.assert_fails_on(grade(self.slug, broken), "Overturn the verdict", ":.2f")

    def test_typed_pardon_count(self):
        broken = mutate(self.solution, "pardons={len(appeals)}", "pardons=5")
        self.assert_fails_on(grade(self.slug, broken), "Overturn the verdict", "calling your pardons()")

    def test_missing_tribunal_asset_is_explained(self):
        mission = self.mission
        with tempfile.TemporaryDirectory(prefix="ns-act2-") as tmp:
            player = Path(tmp) / mission.filename
            player.write_text(self.solution.lstrip("\n"), encoding="utf-8")
            out = Path(tmp) / "report.json"
            subprocess.run([sys.executable, "-m", "engine.harness", self.slug, str(player), str(out)],
                           cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, timeout=mission.timeout,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "crash")
        self.assertEqual(report["error"]["type"], "ModuleNotFoundError")
        self.assert_fails_on(report, "Repair the tally", "tribunal.py is missing")


if __name__ == "__main__":
    unittest.main()
