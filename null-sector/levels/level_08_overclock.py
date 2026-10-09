"""LEVEL 08 // OVERCLOCK — while, break, continue, loop-until-converged.

Graded with the L06 replay grader. The line budget turns a loop that never ends on a fresh
reactor feed into a precise failed layer instead of a grader timeout.
"""
from __future__ import annotations

import ast
import math

from engine.mission import Fail, Mission
from levels.level_06_tripwire import feed_text, need, replay

BASE = {
    "start_pressure": 96, "safe_pressure": 40, "vent_size": 15,
    "readings": [41, -1, 38, 44, -1, 97, 40], "meltdown": 90,
    "start_output": 12.0, "target": 100.0, "gain": 0.5, "tolerance": 0.01, "max_cycles": 50,
}
_VENT = ("start_pressure", "safe_pressure", "vent_size")
_SCAN = ("readings", "meltdown")
_CLOCK = ("start_output", "target", "gain", "tolerance", "max_cycles")


def _feed(**changes):
    return {**BASE, **changes}


def _vent(f):
    pressure, vents = f["start_pressure"], 0
    while pressure > f["safe_pressure"]:
        pressure -= f["vent_size"]
        vents += 1
    return pressure, vents


def _scan(f):
    stable, spike_at = [], -1
    for i, r in enumerate(f["readings"]):
        if r == -1:
            continue
        if r >= f["meltdown"]:
            spike_at = i
            break
        stable.append(r)
    return stable, spike_at


def _clock(f):
    output, cycles = f["start_output"], 0
    while abs(f["target"] - output) >= f["tolerance"] and cycles < f["max_cycles"]:
        output = output + (f["target"] - output) * f["gain"]
        cycles += 1
    return output, cycles, abs(f["target"] - output) < f["tolerance"]


def _line(f):
    _, vents = _vent(f)
    _, spike_at = _scan(f)
    _, cycles, converged = _clock(f)
    return f"REACTOR | vents={vents} | spike_at={spike_at} | cycles={cycles} | converged={converged}"


MISSION = Mission(
    id="L08",
    slug="level_08_overclock",
    title="OVERCLOCK",
    concept="while loops & break",
    enemy="GOVERNOR.loop",
    xp=200,
    par_seconds=25 * 60,
    tier=2,
    concepts=("loops", "numeric"),
    timeout=6.0,
    enemy_art="""\
   ▄▀▀▀▀▀▀▀▀▀▀▀▀▄
  █ ▄▀▀▀▄  ▄▀▀▀▄ █
  █ █ ↻ █  █ ↻ █ █
  █ ▀▄▄▄▀  ▀▄▄▄▀ █
  █▓▓▓▓▓▓▓▓▓▓▓▓▓▓█
   ▀▄▄▄▄▄▄▄▄▄▄▄▄▀""",
    briefing="""\
The relay readings were right. Deep in the base of the cooling tower, the Monastery's flux
reactor is drifting: lamps dim in the nave, the Scriptorium terminals brown out, and the
undercroft smells of hot copper.

Its controller, **GOVERNOR.loop**, is stuck in a cycle it can't leave. Pressure climbing,
sensors lying, output nowhere near target.

RUST slides you a maintenance jack and a look. "Old reactors want to be talked down slowly.
Push too hard and they oscillate. Never stop pushing and they melt."

The grader replays your control code against other reactors' feeds too. One loop that
never ends and you'll know.

**Vent the line, read the core, then overclock it until it converges. And know when to stop.**
""",
    why="""\
Training a model is a loop that doesn't know in advance how many steps it needs:

```python
loss, epochs = 1.0, 0
while loss > 0.001 and epochs < 1000:   # converged, or out of budget
    loss = train_one_epoch(model)
    epochs += 1
```

It runs **until** the loss is small enough (it has *converged*) and never past a hard cap.
That cap is not optional. Real training runs diverge, and a loop with no guardrail burns a
GPU cluster all weekend. `break` gives you *early stopping*: quit the moment validation
loss gets worse. `continue` skips bad samples without stopping the run. Every training
script you'll write in Sector 4 is this level, with bigger numbers.
""",
    manual="""\
**1 · `while` repeats as long as its condition is True.** It checks the condition *before*
every pass, so if it's False at the start, the block never runs. Something inside the loop
has to move the condition toward False:

```python
fuel = 10
burns = 0
while fuel > 0:
    fuel -= 3          # without this line, the loop never ends
    burns += 1
# fuel is -2, burns is 4
```

**2 · `continue` skips to the next pass. `break` leaves the loop immediately.** They work in
`for` loops too:

```python
for n in [3, -1, 8, 99, 5]:
    if n < 0:
        continue       # skip this one, keep looping
    if n > 50:
        break          # stop the whole loop here
    print(n)           # prints 3, then 8
```

**3 · Distance with `abs()`.** `abs(x)` drops the minus sign: `abs(-4)` is 4. The distance
between two numbers is `abs(a - b)`, whichever is bigger. If a value can *overshoot* its
target, `target - value` goes negative, and only `abs` still measures how far away it is.

**4 · Loop until converged, with a guardrail.** Close part of the gap each step. Stop when
you're close enough, or when you've tried too many times. Both conditions, joined with `and`:

```python
level, steps = 0.0, 0
while abs(80.0 - level) >= 0.5 and steps < 20:
    level = level + (80.0 - level) * 0.3
    steps += 1
reached = abs(80.0 - level) < 0.5        # True or False: did it converge?
```

The same loop can be written `while True:` with an `if ...: break` at the top. Either way,
check the condition *before* each step, so a value that starts converged takes 0 steps.

**5 · When it never stops.** A script that never finishes is graded as a timeout. Look for a
`while` whose condition can't become False: nothing in the loop changes it, or it's
compared the wrong way round.
""",
    starter='''
"""
==============================================================================
  LEVEL 08 // OVERCLOCK                               TARGET: GOVERNOR.loop
==============================================================================
  The Monastery's reactor. The grader REPLAYS this file with other reactors'
  feeds swapped in, including ones that never settle. Your loops must end on
  every one of them.
"""

# == REACTOR FEED ============================================================
start_pressure = 96     # bar in the coolant line right now
safe_pressure = 40      # at or below this, the line is safe
vent_size = 15          # each vent releases this many bar

readings = [41, -1, 38, 44, -1, 97, 40]   # core samples in order; -1 = glitched sensor
meltdown = 90           # a reading at or above this is a spike

start_output = 12.0     # reactor output when you take the controls
target = 100.0          # the output the Monastery needs
gain = 0.5              # share of the remaining gap each overclock cycle closes
tolerance = 0.01        # converged when abs(target - output) is UNDER this
max_cycles = 50         # guardrail: never run more cycles than this


# -- OBJECTIVE 1 // CORRUPTED CODE --------------------------------------------
# Vent the coolant line: release vent_size bar per vent until the pressure is
# at or below safe_pressure. `vents` counts how many vents it took.
# With the feed above it should end at pressure 36 after 4 vents.
# Right now it reports 0 vents. Find the bug. (Careful: a while loop that can
# never become False doesn't finish. Save a copy before you experiment.)
pressure = start_pressure
vents = 0
while pressure < safe_pressure:
    pressure -= vent_size
    vents += 1


# -- OBJECTIVE 2 -------------------------------------------------------------
# Read the core. Walk `readings` in order and build:
#   `stable`   : the list of good readings BEFORE the first spike
#   `spike_at` : the index of the first spike (a reading >= meltdown),
#                or -1 if there is no spike at all
# Skip glitched readings (-1) with `continue`. Stop at the spike with `break`.
# For the feed above:  stable == [41, 38, 44]   and   spike_at == 5
#        example:  for i, value in enumerate(values):   gives index and value



# -- OBJECTIVE 3 -------------------------------------------------------------
# OVERCLOCK. Create `output` (start it at start_output) and `cycles` (at 0).
# Use a WHILE loop. Before each cycle, check BOTH:
#   - converged? abs(target - output) is under tolerance  ->  stop
#   - guardrail? cycles has reached max_cycles             ->  stop
# Each cycle does exactly this, then counts itself:
#     output = output + (target - output) * gain
# For the feed above: 14 cycles, output about 99.995.



# -- OBJECTIVE 4 -------------------------------------------------------------
# After the loop, create `converged`: True when abs(target - output) is under
# tolerance, False when the guardrail stopped it first.



# -- OBJECTIVE 5 -------------------------------------------------------------
# Report to the Order. Print exactly this format from your variables:
#   REACTOR | vents=4 | spike_at=5 | cycles=14 | converged=True

''',
    dialogue={
        "intro": [
            {"speaker": "nova", "mood": "alarm",
             "text": "Ops alert: reactor output at twelve percent and falling. Scriptorium's on backup. {callsign}, it's yours."},
            {"speaker": "rust", "mood": "neutral",
             "text": "That core's older than me and twice as moody. Talk it down slow. And don't hug it."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "A while loop repeats until its question turns False. Make sure the loop itself is what turns it."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "If the log says your code never finished, a while condition never became False. What inside it was meant to change?"}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "Reactor's still here. So's the undercroft. Small mercies. Read the log."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "A crash inside a loop happens on one specific pass. Print the values at the top of the loop to see which one."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader runs reactors that overshoot and ones that never settle. Measure distance with abs(), and keep the guardrail."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Check before you step. A reactor that starts converged should take zero cycles."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "Output's holding, not climbing. Next red layer, {callsign}. Nave lights are counting on you."}],
        ],
        "victory": [
            {"speaker": "nova", "mood": "warm",
             "text": "Output at target. Converged in fourteen cycles. The whole nave just lit up, {callsign}."},
            {"speaker": "rust", "mood": "smirk",
             "text": "Didn't melt. Didn't even oscillate much. I'll stop charging you for the jack."},
            {"speaker": "cipher", "mood": "warm",
             "text": "The Order has been watching. They want to teach you the rites. The Scriptorium is open to you now."},
        ],
    },
)


# ── firewall layers ──────────────────────────────────────────────────────────────

def _count(n):
    return f"{n!r} cycle" if n == 1 else f"{n!r} cycles"


def _shown(feed, keys):
    return feed_text({k: feed[k] for k in keys}, 160)


@MISSION.check("Vent the line — repair the `while` condition")
def _vent_check(ctx):
    ctx.get("vents")
    for feed in (_feed(), _feed(start_pressure=55), _feed(start_pressure=40), _feed(start_pressure=31),
                 _feed(start_pressure=100, safe_pressure=0, vent_size=25), _feed(start_pressure=200, vent_size=7)):
        run = replay(ctx, feed)
        vents, pressure = need(run, "vents", _VENT), need(run, "pressure", _VENT)
        want_pressure, want_vents = _vent(feed)
        if (pressure, vents) == (want_pressure, want_vents):
            continue
        if vents == 0 and want_vents:
            hint = ("The loop never ran: its condition was False from the start. Read it out loud: "
                    "keep venting WHILE the pressure is ... the safe level?")
        elif vents == want_vents + 1:
            hint = "One vent too many. At or below safe IS safe, so a pressure equal to safe_pressure must stop the loop."
        else:
            hint = "Each pass should vent once (pressure -= vent_size) and count once (vents += 1)."
        raise Fail(f"With {_shown(feed, _VENT)}: you ended at pressure {pressure!r} after {vents!r} vents. "
                   f"Expected pressure {want_pressure} after {want_vents}.", hint=hint)


_SCAN_FEEDS = [
    _feed(),
    _feed(readings=[12, 30, 55, 60]),
    _feed(readings=[95, 20, 30]),
    _feed(readings=[-1, -1, 88, -1, 90, 10]),
    _feed(readings=[-1, -1]),
    _feed(readings=[]),
    _feed(readings=[70, 89, 91, 99], meltdown=95),
]


@MISSION.check("Skip the glitches — `stable` with continue")
def _stable_check(ctx):
    ctx.get("stable")
    if not any(isinstance(n, ast.Continue) for n in ast.walk(ctx.tree)):
        raise Fail("No `continue` in your file. This layer is about skipping a pass without stopping the loop.",
                   hint="Inside the loop:  if value == -1:  then  continue  on the next, indented line.")
    for feed in _SCAN_FEEDS:
        value = need(replay(ctx, feed), "stable", _SCAN)
        expected, spike_at = _scan(feed)
        if value == expected:
            continue
        if isinstance(value, list) and -1 in value:
            hint = "A glitched -1 got into `stable`. Skip it with continue BEFORE the line that appends."
        elif isinstance(value, list) and spike_at != -1 and len(value) > len(expected):
            hint = "`stable` kept going past the spike. Readings after the first spike don't count: break out."
        elif isinstance(value, list) and any(v >= feed["meltdown"] for v in value):
            hint = "The spike itself went into `stable`. Check for the spike before appending."
        else:
            hint = "Good readings go in, in order, until the first spike. Glitches (-1) are skipped."
        raise Fail(f"With {_shown(feed, _SCAN)}: `stable` is {value!r}, expected {expected!r}.", hint=hint)


@MISSION.check("Catch the spike — `spike_at` with break")
def _spike_check(ctx):
    ctx.get("spike_at")
    if not any(isinstance(n, ast.Break) for n in ast.walk(ctx.tree)):
        raise Fail("No `break` in your file. The scan must stop at the first spike.",
                   hint="When you find a reading >= meltdown: store its index, then  break.")
    for feed in _SCAN_FEEDS:
        value = need(replay(ctx, feed), "spike_at", _SCAN)
        _, expected = _scan(feed)
        if value == expected and type(value) is int:
            continue
        if expected == -1:
            hint = "No reading reached meltdown here, so spike_at must stay -1. Set it to -1 BEFORE the loop."
        elif isinstance(value, int) and value > expected:
            hint = "That's a later spike. Without break, the loop keeps going and overwrites the first one."
        elif any(r == feed["meltdown"] for r in feed["readings"]):
            hint = "A reading exactly AT meltdown is a spike too: use >=."
        else:
            hint = "spike_at is the INDEX (position) of the reading, not the reading itself. enumerate gives both."
        raise Fail(f"With {_shown(feed, _SCAN)}: `spike_at` is {value!r}, expected {expected}.", hint=hint)


def _clock_case(ctx, feed, hint_for):
    run = replay(ctx, feed)
    output, cycles = need(run, "output", _CLOCK), need(run, "cycles", _CLOCK)
    want_output, want_cycles, _ = _clock(feed)
    if type(output) not in (int, float):
        raise Fail(f"`output` is {type(output).__name__} {output!r}. It should be the reactor's output number.")
    if cycles != want_cycles or not math.isclose(output, want_output, rel_tol=1e-9, abs_tol=1e-9):
        raise Fail(f"With {_shown(feed, _CLOCK)}: {_count(cycles)}, output {output!r}. "
                   f"Expected {want_cycles} cycles, output about {round(want_output, 4)}.",
                   hint=hint_for(feed, cycles, want_cycles))
    return run


@MISSION.check("Overclock — `output` converges")
def _clock_check(ctx):
    ctx.get("cycles")
    if not any(isinstance(n, ast.While) for n in ast.walk(ctx.tree)):
        raise Fail("No while loop in your file.", hint="The overclock runs WHILE it isn't converged.")

    def hint(feed, got, want):
        if got == want + 1 or (want == 0 and got):
            return "Check BEFORE each cycle: a reactor already within tolerance must take 0 cycles."
        if isinstance(got, int) and got == want - 1:
            return "Stopped one cycle early. Converged means the distance is UNDER tolerance, so keep going while it's >= ."
        if feed["start_output"] > feed["target"] and isinstance(got, int) and got < want:
            return ("This reactor starts ABOVE target, so target - output is negative. "
                    "Distance is abs(target - output), whichever side you're on.")
        return "Each pass: output = output + (target - output) * gain, then cycles += 1."
    for feed in (_feed(), _feed(gain=1.0), _feed(start_output=99.995), _feed(start_output=250.0, gain=0.25),
                 _feed(start_output=0.0, target=-40.0, gain=0.6, tolerance=0.001)):
        _clock_case(ctx, feed, hint)


@MISSION.check("Overshoot — measure distance with abs()")
def _overshoot_check(ctx):
    ctx.get("cycles")

    def hint(feed, got, want):
        if isinstance(got, int) and got < want:
            return ("With gain above 1, each cycle OVERSHOOTS the target, so target - output goes negative and "
                    "looks 'small'. Measure the distance with abs(target - output).")
        return "Keep cycling until abs(target - output) is under tolerance, whichever side of target you're on."
    for feed in (_feed(gain=1.5), _feed(start_output=180.0, gain=1.8, tolerance=0.05)):
        _clock_case(ctx, feed, hint)


@MISSION.check("Guardrail — `max_cycles` and `converged`")
def _guardrail_check(ctx):
    ctx.get("converged")
    for feed in (_feed(), _feed(gain=0.0), _feed(gain=2.0, max_cycles=9), _feed(gain=2.5, max_cycles=30),
                 _feed(start_output=99.995), _feed(gain=0.1, max_cycles=5)):
        run = replay(ctx, feed)
        if run.runaway:
            raise Fail(f"With {_shown(feed, _CLOCK)}, this reactor never converges, and your loop never stopped.",
                       hint="Only the guardrail can end this one: keep looping only while cycles < max_cycles "
                            "(joined to the distance test with `and`).")
        converged = need(run, "converged", _CLOCK)
        cycles = need(run, "cycles", _CLOCK)
        _, want_cycles, want_converged = _clock(feed)
        if type(converged) is not bool:
            raise Fail(f"`converged` is {type(converged).__name__} {converged!r}. It must be True or False.",
                       hint="Store the comparison itself:  converged = abs(target - output) < tolerance")
        if cycles != want_cycles:
            early = isinstance(cycles, int) and cycles < want_cycles and not want_converged
            raise Fail(f"With {_shown(feed, _CLOCK)}: the loop ran {_count(cycles)}, expected {want_cycles}. "
                       "This reactor never settles, so only the guardrail should stop it.",
                       hint=("It stopped early: your distance test thinks it converged. With this gain the output "
                             "swings past target, so measure with abs(target - output).") if early and feed["gain"] > 1
                       else "Join both stop rules in the while condition with `and`: "
                            "still too far away AND cycles < max_cycles.")
        if converged != want_converged:
            raise Fail(f"With {_shown(feed, _CLOCK)}: `converged` is {converged}, expected {want_converged}.",
                       hint="Compute it AFTER the loop, from the final output. Running out of cycles is not converging.")


@MISSION.check("Report to the Order — reactor status")
def _report(ctx):
    if not ctx.stdout.strip():
        if ctx.crashed:
            raise Fail("Nothing was printed. Your script crashed before it reached the print().")
        raise Fail("Nothing was printed.", hint="print() an f-string in the objective 5 format.")
    for var in ("vents", "spike_at", "cycles", "converged"):
        if not ctx.call_uses("print", var):
            raise Fail(f"Your report doesn't use `{var}`. Typed-in numbers can't follow another reactor's feed.",
                       hint="Build the line from your variables inside an f-string.")
    for feed in (_feed(), _feed(gain=0.0, readings=[1, 2], start_pressure=10)):
        run = replay(ctx, feed)
        if run.runaway:
            raise Fail("With another reactor's feed, your script never finished, so nothing was reported.",
                       hint="Fix the loop layers above first: every while loop must end on every feed.")
        expected = _line(feed)
        if expected not in run.stdout.splitlines():
            got = run.stdout.strip().splitlines()
            raise Fail(f"With another reactor's feed, the Order expected {expected!r} but got {got[-1]!r}." if got
                       else "With another reactor's feed, nothing was printed.",
                       hint="Match the format exactly: spaces around each |, no spaces around =.")
