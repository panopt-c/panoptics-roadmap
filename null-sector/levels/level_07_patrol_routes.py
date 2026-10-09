"""LEVEL 07 // PATROL ROUTES — for, range, enumerate, zip, accumulators, nested loops, comprehensions.

Graded with the L06 replay grader: the PATROL FEED is swapped for fresh routes and grids, so
every answer must come from a loop over the data. VEX makes a first appearance.
"""
from __future__ import annotations

import ast

from engine.mission import Fail, Mission
from levels.level_06_tripwire import feed_text, need, replay

BASE = {
    "route": ["N4", "N5", "E2", "E3", "S1"],
    "dwell": [12, 7, 30, 4, 9],
    "laps": 3,
    "grid": [[0, 2, 0, 1], [3, 0, 0, 0], [0, 1, 4, 0]],
}

# Fresh patrol logs the grader swaps in: one-stop routes, ties, ragged grids, zero laps.
FEEDS = [
    BASE,
    {"route": ["W1"], "dwell": [5], "laps": 1, "grid": [[1]]},
    {"route": ["C1", "C2", "C3", "C4"], "dwell": [8, 20, 20, 3], "laps": 2,
     "grid": [[0, 0], [0, 0], [6, 0]]},
    {"route": ["S9", "S8", "S7"], "dwell": [3, 2, 1], "laps": 0, "grid": [[2, 2, 2], [2, 2, 2]]},
    {"route": ["E1", "E5", "N2", "N3", "W4", "W5"], "dwell": [10, 41, 15, 9, 10, 2], "laps": 4,
     "grid": [[0], [0, 5, 0], [7, 0, 0, 0]]},
]


def _sweep(f):
    return sum(f["dwell"])


def _checkpoints(f):
    return [f"{n}:{sector}" for n, sector in enumerate(f["route"], start=1)]


def _longest(f):
    best, most = None, -1
    for sector, seconds in zip(f["route"], f["dwell"]):
        if seconds > most:
            best, most = sector, seconds
    return best


def _lap_starts(f):
    return [lap * _sweep(f) for lap in range(f["laps"])]


def _quick(f):
    return [s for s, t in zip(f["route"], f["dwell"]) if t < 10]


def _sentinels(f):
    return sum(sum(row) for row in f["grid"])


def _safe(f):
    return [(r, c) for r, row in enumerate(f["grid"]) for c, count in enumerate(row) if count == 0]


def _line(f):
    return f"PATROL | sweep={_sweep(f)}s | sentinels={_sentinels(f)} | safe={len(_safe(f))}"


MISSION = Mission(
    id="L07",
    slug="level_07_patrol_routes",
    title="PATROL ROUTES",
    concept="Loops & comprehensions",
    enemy="SENTINEL.route",
    xp=190,
    par_seconds=30 * 60,
    tier=2,
    concepts=("loops", "comprehensions"),
    timeout=8.0,
    enemy_art="""\
    ▄▄████████▄▄
  ▄█▀ ▄▄    ▄▄ ▀█▄
  █▌ ▐██▌  ▐██▌ ▐█
  ▀█▄  ▀▀▄▄▀▀  ▄█▀
    ▀█▄▄▄▄▄▄▄▄█▀
   ▄▀ ▀  ▀▀  ▀ ▀▄""",
    briefing="""\
Dawn on the Grid is just the neon getting paler. A lattice of dead city blocks, and walking
it, the **SENTINELS**: the ARBITER's patrol daemons, sweeping the same routes they've swept
for eleven years.

NOVA needs a supply run through to the old relay. The Order's last surveyor died logging
these routes. His numbers survived him: every stop, every second, every street.

Someone else is up here too. Magenta coat, perched on a dead billboard, timing you out loud.

Sentinels never improvise. Read the log once, loop over it right, and you know where they'll
be for the rest of the day.

**Map the patrol, count the watchers, find the gaps. Then get the runners through.**
""",
    why="""\
Training a model is a loop over data, inside another loop:

```python
for epoch in range(3):                    # pass over the dataset 3 times
    total_error = 0.0                     # reset once per epoch, ON PURPOSE
    for x, target in zip(inputs, targets):
        error = model(x) - target
        total_error += error * error      # the accumulator
    print(f"epoch {epoch}: {total_error}")
```

`range` counts the passes (*epochs*), `zip` walks inputs and answers side by side, and an
accumulator adds up the error. Where the `= 0.0` line sits decides whether you measure one
epoch or the whole run. Comprehensions are how data gets filtered before training:
`clean = [x for x in raw if x is not None]`. Same loops, one line.
""",
    manual="""\
**1 · A `for` loop runs its block once per item.** The loop variable takes each value in
turn. An **accumulator** starts *before* the loop and is updated *inside* it:

```python
ammo = [4, 9, 2]
total = 0                  # start ONCE, outside
for clip in ammo:
    total += clip          # same as total = total + clip
# total is 15
```

**2 · `range` makes numbers to loop over.** `range(4)` is 0, 1, 2, 3 (it stops *before* 4).
`range(0)` is empty, so the loop simply doesn't run:

```python
for shift in range(3):
    print(shift * 8)       # 0, 8, 16
```

**3 · `enumerate` gives you a counter; `zip` walks two lists together:**

```python
crew = ["ana", "kade"]
for n, name in enumerate(crew, start=1):
    print(f"{n}. {name}")              # 1. ana  /  2. kade
ages = [31, 27]
for name, age in zip(crew, ages):
    print(name, age)                   # pairs line up by position
```

**4 · Nested loops and building lists.** A loop inside a loop visits every cell of a grid
(a list of lists). `.append` builds a result; a tuple `(a, b)` keeps a pair together:

```python
shelves = [[5, 0], [0, 3]]
empty = []
for r, shelf in enumerate(shelves):
    for c, count in enumerate(shelf):
        if count == 0:
            empty.append((r, c))       # [(0, 1), (1, 0)]
```

Every row can have its own length, so loop over each row itself, not a fixed number.

**5 · List comprehensions** build a list in one line: *expression*, `for`, optional `if`:

```python
heavy = [w for w in weights if w > 20]
names = [f"{n}:{c}" for n, c in enumerate(crew, start=1)]
```

**6 · Where a line sits is logic.** A line indented under the loop runs every pass. A line
before it runs once. If a total keeps "forgetting" earlier items, look at what runs every pass.
""",
    starter='''
"""
==============================================================================
  LEVEL 07 // PATROL ROUTES                        TARGET: SENTINEL.route
==============================================================================
  The surveyor's log. The grader REPLAYS this file with OTHER patrol logs
  swapped into the PATROL FEED (different lengths, ties, empty laps), so
  every answer has to come from looping over the data.
"""

# == PATROL FEED =============================================================
route = ["N4", "N5", "E2", "E3", "S1"]    # sectors one sentinel sweeps, in order
dwell = [12, 7, 30, 4, 9]                 # seconds it spends in each, same order
laps = 3                                  # sweeps per shift
grid = [                                  # sentinels per block; one row per street
    [0, 2, 0, 1],
    [3, 0, 0, 0],
    [0, 1, 4, 0],
]


# -- OBJECTIVE 1 -------------------------------------------------------------
# One full sweep: create `sweep_time`, the total of `dwell`, with a FOR LOOP
# and an accumulator (no sum() this time: the loop is the lesson).
#     example:  total = 0
#               for clip in ammo:
#                   total += clip



# -- OBJECTIVE 2 -------------------------------------------------------------
# Number the stops for the runners. Create `checkpoints`, a list of text like
#   ["1:N4", "2:N5", "3:E2", "4:E3", "5:S1"]
# using enumerate(route, start=1).   example:  f"{n}:{name}"



# -- OBJECTIVE 3 -------------------------------------------------------------
# Where does the sentinel linger longest? Walk `route` and `dwell` TOGETHER
# with zip(), and create `longest_stop`: the sector with the biggest dwell.
# On a tie, keep the FIRST one.  (Hint: remember the best so far, and only
# replace it when a dwell is strictly bigger.)



# -- OBJECTIVE 4 -------------------------------------------------------------
# Create `lap_starts`: the second each lap begins, one entry per lap.
# With laps = 3 and a 62 s sweep:  [0, 62, 124]
# Loop over range(laps); lap number times sweep_time.



# -- OBJECTIVE 5 -------------------------------------------------------------
# The gaps: create `quick_sectors` with a LIST COMPREHENSION, holding every
# sector the sentinel leaves in UNDER 10 seconds, in route order.
#              example:  heavy = [w for w in weights if w > 20]
# (zip works inside a comprehension too.)



# -- OBJECTIVE 6 // CORRUPTED CODE --------------------------------------------
# The surveyor's census should count EVERY sentinel on the grid. It reports
# only 5 of them. One line is in the wrong place. Find it and fix it.
sentinels = 0
for street in grid:
    sentinels = 0
    for count in street:
        sentinels += count


# -- OBJECTIVE 7 -------------------------------------------------------------
# Create `safe_cells`: a list of (row, column) tuples for every block with
# ZERO sentinels, scanning street by street, left to right.
# For the feed above it starts:  [(0, 0), (0, 2), (1, 1), ...]
# Nested loops: one over the streets, one over each street's blocks.



# -- OBJECTIVE 8 -------------------------------------------------------------
# Send the map to NOVA. Print exactly this format from your variables:
#   PATROL | sweep=62s | sentinels=11 | safe=7
# (len() counts the safe cells.)

''',
    dialogue={
        "intro": [
            {"speaker": "nova", "mood": "neutral",
             "text": "Runners are staged, {callsign}. They go when you give me the gaps. Not a second before."},
            {"speaker": "vex", "mood": "smirk",
             "text": "So you're NOVA's new monk. I mapped these routes in forty seconds. Go on. I'm timing you."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Ignore the commentary. Every sentinel repeats. A loop reads a repeating thing in a few lines."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "IndexError inside a loop usually means you counted past the end. Let the loop hand you the items."}],
            [{"speaker": "vex", "mood": "smirk",
              "text": "Crashed on a for loop? Bold. Most people wait for the hard levels."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Check the colon after the for line and the indent under it. The block is what repeats."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader swaps in other patrol logs. A total you typed in won't follow a route it's never seen."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "If a total only remembers the last row, something is resetting it every pass. Read the indentation."}],
            [{"speaker": "vex", "mood": "smirk",
              "text": "Still mapping? The sentinels have done two laps. I've done six. Just saying, {callsign}."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "Runners holding. One layer at a time. I'd rather late than flattened."}],
        ],
        "victory": [
            {"speaker": "nova", "mood": "warm",
             "text": "Gaps confirmed. Runners through, all of them, relay reached. Patrol logged, {callsign}. Nice work."},
            {"speaker": "vex", "mood": "smirk",
             "text": "Not terrible. Slow, but not terrible. Name's VEX. Remember it. You'll be seeing it above yours."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "The relay's power readings are wrong. The Monastery's reactor is drifting. We should get back."},
        ],
    },
)


# ── helpers ──────────────────────────────────────────────────────────────────────

def _assigned_in_loop(ctx, name: str) -> bool:
    """True if `name` is updated somewhere inside a for loop."""
    for loop in ast.walk(ctx.tree):
        if isinstance(loop, ast.For):
            for node in ast.walk(loop):
                targets = node.targets if isinstance(node, ast.Assign) else \
                    [node.target] if isinstance(node, ast.AugAssign) else []
                if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                    return True
    return False


def _compare(ctx, name: str, reference, hint_for, show, feeds=FEEDS, kind=None):
    ctx.get(name)
    for feed in feeds:
        run = replay(ctx, feed)
        value = need(run, name)
        expected = reference(feed)
        if kind is not None and type(value) is not kind:
            raise Fail(f"`{name}` is {type(value).__name__} {value!r}, but it must be {kind.__name__}.",
                       hint=hint_for(feed, value, expected))
        if value != expected:
            raise Fail(f"With {feed_text({k: feed[k] for k in show}, 160)}: `{name}` is {value!r}, "
                       f"expected {expected!r}.",
                       hint=hint_for(feed, value, expected))


# ── firewall layers ──────────────────────────────────────────────────────────────

@MISSION.check("Full sweep — `sweep_time` accumulator")
def _sweep_check(ctx):
    ctx.get("sweep_time")
    if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "sum"
           for v in ctx.assignments("sweep_time") for n in ast.walk(v)):
        raise Fail("`sweep_time` uses sum(). It works, but this layer trains the loop that sum() hides.",
                   hint="Start sweep_time at 0 before a for loop over dwell, and add each value inside it.")
    if not _assigned_in_loop(ctx, "sweep_time"):
        raise Fail("`sweep_time` is never updated inside a for loop.",
                   hint="Accumulator pattern: total = 0 once, then  for x in data:  with  total += x  indented.")
    _compare(ctx, "sweep_time", _sweep, lambda f, v, e: (
        "Your total is too small: did the accumulator restart inside the loop?" if isinstance(v, int) and v < e
        else "Start at 0 ONCE, before the loop, then add each dwell value inside it."), ("dwell",), kind=int)


@MISSION.check("Number the stops — `checkpoints` with enumerate")
def _checkpoints_check(ctx):
    ctx.get("checkpoints")
    if not ctx.call_uses("enumerate", "route"):
        raise Fail("`checkpoints` should come from enumerate(route, ...). It hands you a counter and the sector.",
                   hint="for n, sector in enumerate(route, start=1):  or the same inside a comprehension.")
    _compare(ctx, "checkpoints", _checkpoints, lambda f, v, e: (
        "Numbering starts at 1 for the runners: enumerate(route, start=1)."
        if isinstance(v, list) and v and str(v[0]).startswith("0") else
        "Each entry is text like \"1:N4\": number, colon, sector, no spaces."), ("route",), kind=list)


@MISSION.check("Longest stop — `longest_stop` with zip")
def _longest_check(ctx):
    ctx.get("longest_stop")
    if not (ctx.call_uses("zip", "route") and ctx.call_uses("zip", "dwell")):
        raise Fail("Walk the two lists together with zip(route, dwell).",
                   hint="for sector, seconds in zip(route, dwell):  pairs each sector with its own dwell time.")

    def hint(f, v, e):
        dwell = f["dwell"]
        if v in f["route"] and dwell[f["route"].index(v)] == max(dwell):
            return "That's a tie, and you kept the LAST one. Only replace your best when the new dwell is strictly bigger (>)."
        if v == f["route"][-1]:
            return "You returned the last sector. Keep the best so far in a variable, and update it inside an if."
        return "Track two things: the best sector so far and its dwell. Replace both when you find a bigger dwell."
    _compare(ctx, "longest_stop", _longest, hint, ("route", "dwell"))


@MISSION.check("Shift schedule — `lap_starts` with range")
def _laps_check(ctx):
    ctx.get("lap_starts")
    if not ctx.call_uses("range", "laps"):
        raise Fail("`lap_starts` should loop over range(laps): one pass per lap.",
                   hint="range(laps) gives 0, 1, 2 ... laps-1. Lap 0 starts at second 0.")
    _compare(ctx, "lap_starts", _lap_starts, lambda f, v, e: (
        "With laps = 0 there are no laps, so the list is empty. range(0) never runs." if f["laps"] == 0 else
        "Lap n starts at n * sweep_time. The first lap is lap 0, so it starts at 0."
        if isinstance(v, list) and v and v[0] != 0 else
        "One entry per lap: range(laps), and each entry is the lap number times sweep_time."), ("laps", "dwell"),
        kind=list)


@MISSION.check("Find the gaps — `quick_sectors` comprehension")
def _quick_check(ctx):
    ctx.get("quick_sectors")
    if not any(isinstance(v, ast.ListComp) for v in ctx.assignments("quick_sectors")):
        raise Fail("`quick_sectors` must be built with a list comprehension: [... for ... in ... if ...].",
                   hint="[sector for sector, seconds in zip(route, dwell) if ...] has the same shape as the manual's.")
    _compare(ctx, "quick_sectors", _quick, lambda f, v, e: (
        "UNDER 10 means 10 itself doesn't count: use < 10." if 10 in f["dwell"] else
        "Keep the SECTOR names (not the seconds) whose dwell is under 10, in route order."), ("route", "dwell"),
        kind=list)


@MISSION.check("Repair the census — `sentinels`")
def _census_check(ctx):
    def hint(f, v, e):
        if f["grid"] and v == sum(f["grid"][-1]) and v != e:
            return ("Your total equals the LAST street only. A line inside the outer loop wipes the count at the "
                    "start of every street. Count from zero once, before both loops.")
        return "Add every block's count, across every street, into one total that starts before the loops."
    _compare(ctx, "sentinels", _sentinels, hint, ("grid",), kind=int)


@MISSION.check("Safe blocks — `safe_cells` nested scan")
def _safe_check(ctx):
    def hint(f, v, e):
        if isinstance(v, list) and v and not isinstance(v[0], tuple):
            return "Each entry is a (row, column) tuple, like (0, 2). Build it with parentheses."
        if isinstance(v, list) and sorted(v) == sorted(e) and v != e:
            return "Right cells, wrong order: scan street by street (outer loop), left to right (inner loop)."
        if any(len(row) != len(f["grid"][0]) for row in f["grid"]):
            return "Streets can have different lengths. Loop over each street's own blocks, not a fixed count."
        return "Outer loop: enumerate(grid) gives the row number and the street. Inner: enumerate(street)."
    _compare(ctx, "safe_cells", _safe, hint, ("grid",), kind=list)


@MISSION.check("Send the map — patrol report")
def _report(ctx):
    if not ctx.stdout.strip():
        if ctx.crashed:
            raise Fail("Nothing was printed. Your script crashed before it reached the print().")
        raise Fail("Nothing was printed.", hint="print() an f-string in the objective 8 format.")
    for var in ("sweep_time", "sentinels", "safe_cells"):
        if not ctx.call_uses("print", var):
            raise Fail(f"Your report doesn't use `{var}`. Typed-in numbers can't follow a new patrol log.",
                       hint="Build the line from your variables; len(safe_cells) gives the count.")
    for feed in FEEDS[:3]:
        run = replay(ctx, feed)
        expected = _line(feed)
        if expected not in run.stdout.splitlines():
            got = run.stdout.strip().splitlines()
            raise Fail(f"With {feed_text(feed)}, NOVA expected {expected!r} but got {got[-1]!r}." if got else
                       f"With {feed_text(feed)}, nothing was printed.",
                       hint="Match the format exactly, including the s after the sweep seconds.")
