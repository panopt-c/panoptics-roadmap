"""LEVEL 06 // TRIPWIRE — comparisons, and/or/not, if/elif/else.

Act II opens inside the Monastery. NOVA's first trial: rewrite the perimeter tripwires.

Grading model (shared by L06–L08, which come before `def` is taught): the starter has a
SENSOR FEED of plain assignments. Checks REPLAY the player's whole script with fresh values
swapped into those lines (an AST rewrite, executed under a line budget), so a hard-coded
answer fails the moment the readings change. `replay`, `need` and `feed_text` are imported
by levels 07 and 08.
"""
from __future__ import annotations

import ast
import contextlib
import copy
import io
import sys
import traceback
from dataclasses import dataclass

from engine.mission import Fail, Mission

# ── replay grader (shared with L07, L08) ─────────────────────────────────────────


class _Runaway(BaseException):
    """Raised by the line budget. BaseException, so `except Exception` in player code can't swallow it."""


@dataclass
class Replay:
    feed: dict
    ns: dict
    stdout: str
    error: BaseException | None
    line: int | None          # player line that crashed, if any
    runaway: bool             # True: the line budget ran out (a loop that never ends)


def feed_text(feed: dict, limit: int = 110) -> str:
    text = ", ".join(f"{k}={v!r}" for k, v in feed.items())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _literal(value, where: ast.AST) -> ast.AST:
    node = ast.parse(repr(value), mode="eval").body
    for sub in ast.walk(node):
        ast.copy_location(sub, where)
    return node


def replay(ctx, feed: dict, *, budget: int = 60_000) -> Replay:
    """Re-run the player's file with `feed` values swapped into its top-level feed assignments."""
    filename = ctx.ns.get("__file__") or "<mission>"
    tree = copy.deepcopy(ctx.tree)
    pending = dict(feed)
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id in pending):
            node.value = _literal(pending.pop(node.targets[0].id), node.value)
    if pending:
        name = next(iter(pending))
        raise Fail(f"The feed line `{name} = ...` is missing, so the grader can't swap in fresh readings.",
                   hint=f"Put  {name} = ...  back at the left edge near the top of the file, as in the starter.")
    code = compile(ast.fix_missing_locations(tree), filename, "exec")
    ns = {"__name__": ctx.ns.get("__name__", "__main__"), "__file__": filename, "__builtins__": __builtins__}
    steps = 0

    def local(frame, event, arg):
        nonlocal steps
        if event == "line":
            steps += 1
            if steps > budget:
                raise _Runaway
        return local

    def tracer(frame, event, arg):
        return local if frame.f_code.co_filename == filename else None

    out, error, runaway = io.StringIO(), None, False
    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        with contextlib.redirect_stdout(out):
            exec(code, ns)
    except _Runaway:
        runaway = True
    except SystemExit as exc:
        if exc.code not in (None, 0):
            error = exc
    except BaseException as exc:  # noqa: BLE001 — the player's crash, reported by the check
        error = exc
    finally:
        sys.settrace(previous)
    line = None
    if error is not None:
        frames = [f for f in traceback.extract_tb(error.__traceback__) if f.filename == filename]
        line = frames[-1].lineno if frames else None
    return Replay(feed, ns, out.getvalue(), error, line, runaway)


def need(run: Replay, name: str, keys=None):
    """A variable from a replay, or a Fail that says exactly why it isn't there.

    `keys` limits which feed values the message shows (the ones this layer is about)."""
    if name in run.ns:
        return run.ns[name]
    feed = {k: run.feed[k] for k in keys} if keys else run.feed
    if run.runaway:
        raise Fail(f"With {feed_text(feed, 160)}, your script never finished: a loop kept running forever.",
                   hint="Every while loop needs something inside it that eventually makes its condition False, "
                        "or a break.")
    if run.error is not None:
        where = f"line {run.line}" if run.line else "a line"
        raise Fail(f"With {feed_text(feed, 160)}, your script crashed on {where} "
                   f"({type(run.error).__name__}: {run.error}) before creating `{name}`.",
                   hint="Your code has to survive ANY valid reading, not just the starter's. "
                        "Paste these values into the feed and run it yourself.")
    raise Fail(f"With {feed_text(feed, 160)}, your script finished without ever creating `{name}`.",
               hint=f"Make sure every path through your if/elif/else sets `{name}`. "
                    "An `else:` branch catches whatever the others miss.")


# ── level data ───────────────────────────────────────────────────────────────────

CLEARED = ["order", "runner", "trader"]
BASE = {"motion": 0.82, "heat": 36.4, "badge": "  GRID-7 ", "hour": 2, "signal": 74}


def _moving(f):
    return f["motion"] > 0.3


def _warm(f):
    return 35.0 <= f["heat"] <= 40.0


def _cleared(f):
    return f["badge"].strip().lower() in CLEARED


def _night(f):
    return f["hour"] >= 22 or f["hour"] < 6


def _gate(f):
    if _cleared(f):
        return "OPEN"
    if not _moving(f):
        return "IDLE"
    if not _warm(f):
        return "DRONE"
    if _night(f):
        return "SEAL"
    return "WATCH"


def _threat(f):
    s = f["signal"]
    if s >= 90:
        return "CRITICAL"
    if s >= 70:
        return "HIGH"
    if s >= 40:
        return "LOW"
    return "NONE"


def _line(f):
    return f"TRIPWIRE | gate={_gate(f)} | threat={_threat(f)}"


def _feed(**changes):
    return {**BASE, **changes}


MISSION = Mission(
    id="L06",
    slug="level_06_tripwire",
    title="TRIPWIRE",
    concept="if / elif / else",
    enemy="HUNTER.sim",
    xp=160,
    par_seconds=20 * 60,
    tier=2,
    concepts=("conditionals",),
    timeout=8.0,
    enemy_art="""\
 ▄▀▀▀▀▀▀▀▀▀▀▀▀▀▀▄
 █  ◢██◣  ◢██◣  █
 █  ◥██◤  ◥██◤  █
 ▀▄▄▄▄▄▄▄▄▄▄▄▄▄▄▀
━━━━━━━━╋━━━━━━━━━
        ▀""",
    briefing="""\
The Monastery's gate seals behind you, and for the first time since you woke, nothing is
hunting you. That lasts about an hour.

**NOVA**, the Order's dispatcher, drops a trial into your visor before you've found a place
to sit. The tripwires facing the Grid run on firmware older than the blackout. They howl at
rats and wave hunters straight through.

Every new arrival rewrites them. Tonight NOVA runs a simulated Grid hunter, **HUNTER.sim**,
against your logic. Mostly simulated.

The grader won't trust one reading. It will replay your script against fresh sensor data
until your rules hold for anything that walks out of the dark.

**Teach the tripwires to decide: open, ignore, track or seal. The Order sleeps behind
whatever you write.**
""",
    why="""\
Every deployed model ends in a decision like this. The model produces a number; your code
turns it into an action:

```python
confidence = 0.91
if confidence >= 0.9:
    action = "approve"
elif confidence >= 0.6:
    action = "send to a human"
else:
    action = "reject"
```

Spam filters, fraud alerts, medical triage and content moderation are all thresholds and
rules wrapped around a model. Two details decide who ends up on the wrong side: whether
the boundary is `>` or `>=`, and which branch is checked first. Python takes the **first**
branch that matches and skips the rest, so the order of your rules is part of the logic.
""",
    manual="""\
**1 · Comparisons answer with a bool.** `==` *asks* whether two values are equal (`=` *stores*
a value). The others are `!=`, `<`, `>`, `<=`, `>=`:

```python
ammo = 12
low = ammo < 20          # True
empty = ammo == 0        # False
in_band = 10 <= ammo <= 20   # True: a chained comparison, both ends included
```

**2 · Combine conditions with `and`, `or`, `not`.** `and` needs both sides True. `or` needs
at least one. `not` flips a bool:

```python
off_shift = hour < 9 or hour >= 17       # before 9 OR from 17 on
can_enter = has_ticket and not is_banned
```

Read an `and` out loud before you trust it: can one value really be both at once?

**3 · Membership with `in`.** Clean scanned text first (SIGNAL NOISE), then ask whether it's
in a list. A list match is exact: `"orderly"` is not `"order"`:

```python
guests = ["ana", "kade"]
is_guest = name.strip().lower() in guests
```

**4 · `if` / `elif` / `else`.** A colon ends each condition, and the indented block below it
runs only when that branch is chosen. Python tests from the top and runs the **first**
branch that's True. Everything after it is skipped. `else` catches the rest:

```python
if score >= 90:
    rank = "S"
elif score >= 60:
    rank = "B"
else:
    rank = "F"
```

Put the *strictest* test first. If `score >= 60` came first, a 95 would stop there and
never reach the `"S"` branch.

**5 · Reading the classic error.** `if hour = 3:` stops the whole file with
`SyntaxError: invalid syntax. Maybe you meant '==' ...`. Inside a condition you are asking,
so use `==`.
""",
    starter='''
"""
==============================================================================
  LEVEL 06 // TRIPWIRE                                 TARGET: HUNTER.sim
==============================================================================
  NOVA's first trial. The grader REPLAYS this whole file with fresh readings
  swapped into the SENSOR FEED below, so your rules must work for ANY values,
  not just these. Keep the feed lines; change their values to test yourself.
"""

# == SENSOR FEED (one tripwire, right now) ===================================
motion = 0.82          # 0.0 (still) to 1.0 (sprinting)
heat = 36.4            # surface heat in degrees C
badge = "  GRID-7 "    # raw badge scan; "" when nothing is worn
hour = 2               # Monastery clock, 0 to 23
signal = 74            # carrier strength, 0 to 100

CLEARED = ["order", "runner", "trader"]    # badges the Order lets in


# -- OBJECTIVE 1 -------------------------------------------------------------
# Create `is_moving`: True when motion is ABOVE 0.3 (0.3 itself is not moving).
# A comparison already gives True/False.     example:  is_heavy = weight > 20



# -- OBJECTIVE 2 -------------------------------------------------------------
# Create `is_warm`: True when heat is between 35.0 and 40.0, BOTH ends included.
# Living bodies sit in that window; Grid machines don't.
#                                   example:  in_band = 10 <= ammo <= 20



# -- OBJECTIVE 3 -------------------------------------------------------------
# Create `is_cleared`: clean the raw badge (strip the spaces, make it lowercase),
# then True when the cleaned badge is IN the CLEARED list.
#                     example:  is_guest = name.strip().lower() in guests



# -- OBJECTIVE 4 -------------------------------------------------------------
# Create `is_night`: the night shift runs from 22:00, past midnight, to 05:59.
# So it's night when hour is 22 or more, OR when hour is less than 6.
#                         example:  off_shift = hour < 9 or hour >= 17



# -- OBJECTIVE 5 -------------------------------------------------------------
# Create `gate` with if / elif / else, following the PERIMETER PROTOCOL.
# Check the rules IN THIS ORDER. The first one that matches wins:
#   1. the badge is cleared                    ->  "OPEN"
#   2. nothing is moving                       ->  "IDLE"
#   3. something is moving but it isn't warm   ->  "DRONE"
#   4. moving, warm, and it's night            ->  "SEAL"
#   5. anything else                           ->  "WATCH"
# Use your flags from objectives 1-4 (and `not` where the rule says "isn't").



# -- OBJECTIVE 6 // CORRUPTED CODE --------------------------------------------
# The threat ladder should rank the carrier signal:
#   90 or more -> "CRITICAL",  70 or more -> "HIGH",  40 or more -> "LOW",
#   anything lower -> "NONE".
# It reports "LOW" for a 74, and even for a 99. Find out why, then fix it.
if signal >= 40:
    threat = "LOW"
elif signal >= 70:
    threat = "HIGH"
elif signal >= 90:
    threat = "CRITICAL"
else:
    threat = "NONE"


# -- OBJECTIVE 7 -------------------------------------------------------------
# Report to NOVA. Print exactly this format, built from `gate` and `threat`:
#   TRIPWIRE | gate=SEAL | threat=HIGH
#                       example:  print(f"STATUS | ammo={ammo}")

''',
    dialogue={
        "intro": [
            {"speaker": "nova", "mood": "warm",
             "text": "Ops online. I'm NOVA, dispatch. Welcome inside, {callsign}. Everyone who walks in runs the tripwire trial."},
            {"speaker": "nova", "mood": "smirk",
             "text": "Old firmware screams at rats and waves hunters through. You're going to give it judgement."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "A decision is just a question with a True or False answer. Ask them in the right order."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Crash. If the log says 'Maybe you meant ==', you stored a value where you meant to ask about one."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "An if line ends with a colon, and the block under it is indented. Python is strict about both."}],
            [{"speaker": "nova", "mood": "alarm",
              "text": "Tripwire controller just rebooted on us. Combat log has the line number, {callsign}."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader replays your file with new readings. If it only works for the starter's numbers, it doesn't work."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Check the boundary. 'Above 0.3' and 'at least 0.3' disagree about exactly one value, and the grader tests it."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "Sim hunter's still probing layer by layer. Fix the first red one. Scoreboard's patient."}],
        ],
        "victory": [
            {"speaker": "nova", "mood": "smirk",
             "text": "Trial complete. HUNTER.sim got zero passes. That's a clean sheet, {callsign}. On the board."},
            {"speaker": "cipher", "mood": "alarm",
             "text": "One signature in that run wasn't simulated. It came from inside the Grid and carried the ARBITER's mark."},
            {"speaker": "nova", "mood": "neutral",
             "text": "...Logging it. Something out there is counting us. Get some rest. Patrol routes at dawn."},
        ],
    },
)


# ── firewall layers ──────────────────────────────────────────────────────────────

def _flag_check(ctx, name: str, reference, cases, hint_for):
    """Replay each (feed, note) case and compare the bool `name` with the reference."""
    ctx.get(name)
    for feed, note in cases:
        run = replay(ctx, feed)
        value = need(run, name)
        if type(value) is not bool:
            raise Fail(f"`{name}` is {type(value).__name__} {value!r}, but it must be a bool (True or False).",
                       hint="A comparison like  x > 5  already produces True or False. Store it directly.")
        expected = reference(feed)
        if value != expected:
            raise Fail(f"With {feed_text({k: feed[k] for k in note[0]})}: `{name}` is {value}, "
                       f"expected {expected}. ({note[1]})", hint=hint_for(feed, value))


@MISSION.check("Motion tripwire — `is_moving`")
def _is_moving(ctx):
    cases = [(_feed(motion=m), (("motion",), why)) for m, why in (
        (0.82, "the starter reading"), (0.3, "exactly 0.3 is not ABOVE 0.3"),
        (0.31, "just above the line"), (0.0, "dead still"), (1.0, "a full sprint"))]
    _flag_check(ctx, "is_moving", _moving, cases, lambda f, v: (
        "At exactly 0.3 the answer is False: use > (above), not >= (at least)."
        if f["motion"] == 0.3 else "Compare the `motion` variable with 0.3. Don't type True or False yourself."))


@MISSION.check("Heat window — `is_warm`")
def _is_warm(ctx):
    cases = [(_feed(heat=h), (("heat",), why)) for h, why in (
        (36.4, "the starter reading"), (35.0, "the low edge is included"), (40.0, "the high edge is included"),
        (34.9, "just too cold"), (40.1, "just too hot"), (21.0, "a cold machine"))]
    _flag_check(ctx, "is_warm", _warm, cases, lambda f, v: (
        "Both ends are included, so use <= on each side:  35.0 <= heat <= 40.0"
        if f["heat"] in (35.0, 40.0) else
        "The value must sit inside BOTH limits. A chained comparison or `and` checks both at once."))


@MISSION.check("Clearance scan — `is_cleared`")
def _is_cleared(ctx):
    cases = [(_feed(badge=b), (("badge",), why)) for b, why in (
        ("  GRID-7 ", "a spoofed Grid badge"), ("  ORDER ", "an Order badge with scanner padding"),
        ("Runner", "capital letters still count"), ("trader\n", "a trailing newline from the scanner"),
        ("", "no badge at all"), ("orderly", "close isn't cleared: list matches are exact"))]

    def hint(f, v):
        if f["badge"] == "orderly":
            return "Test the whole cleaned badge against the list:  cleaned in CLEARED  (not  \"order\" in cleaned)."
        if f["badge"] != f["badge"].strip().lower():
            return "Clean first, compare second: .strip() removes the padding, .lower() fixes the capitals."
        return "Use `in` with the CLEARED list to get True or False."
    _flag_check(ctx, "is_cleared", _cleared, cases, hint)


@MISSION.check("Night shift — `is_night`")
def _is_night(ctx):
    cases = [(_feed(hour=h), (("hour",), why)) for h, why in (
        (2, "the starter hour"), (22, "the shift starts at 22"), (23, "late night"), (0, "midnight"),
        (5, "05:59 is still night"), (6, "06:00 is morning"), (12, "noon"), (21, "an hour before the shift"))]

    def hint(f, v):
        if v is False and f["hour"] in (0, 2, 5, 22, 23):
            return ("No hour is both 22-or-more AND under 6, so an `and` here is always False. "
                    "Night is one condition OR the other.")
        if f["hour"] in (6, 22):
            return "Check the edges: 22 is night (>= 22), and 6 is not (< 6)."
        return "Two comparisons on `hour`, joined so that either one is enough."
    _flag_check(ctx, "is_night", _night, cases, hint)


_GATE_CASES = [
    (_feed(), "the starter reading: warm intruder at night"),
    (_feed(badge=" Order ", motion=0.0), "cleared beats idle: rule 1 comes first"),
    (_feed(badge="RUNNER", heat=12.0), "a cleared runner, cold from the rain"),
    (_feed(motion=0.1, heat=15.0), "nothing moving: idle, even if it's cold"),
    (_feed(motion=0.3), "exactly 0.3 isn't moving"),
    (_feed(heat=22.5), "moving but cold: a Grid machine"),
    (_feed(heat=41.0, hour=14), "moving and overheated: still not a living body"),
    (_feed(hour=13), "moving, warm, daytime"),
    (_feed(hour=22, heat=35.0), "moving, warm, first hour of the night"),
    (_feed(hour=6, badge=""), "moving, warm, first hour of the morning"),
]


@MISSION.check("Perimeter protocol — `gate`")
def _gate_check(ctx):
    ctx.get("gate")
    flags = (("is_cleared", _cleared), ("is_moving", _moving), ("is_warm", _warm), ("is_night", _night))
    for feed, note in _GATE_CASES:
        run = replay(ctx, feed)
        value = need(run, "gate")
        expected = _gate(feed)
        if value == expected:
            continue
        shown = feed_text({k: feed[k] for k in ("badge", "motion", "heat", "hour")})
        for flag, ref in flags:
            if run.ns.get(flag) != ref(feed):
                raise Fail(f"With {shown}: `gate` is {value!r}, expected {expected!r}. "
                           f"Your `{flag}` is {run.ns.get(flag)!r} here, which isn't right.",
                           hint=f"Fix the `{flag}` layer first. The protocol can only be as good as its flags.")
        if value not in ("OPEN", "IDLE", "DRONE", "SEAL", "WATCH"):
            raise Fail(f"With {shown}: `gate` is {value!r}. It must be exactly one of "
                       "'OPEN', 'IDLE', 'DRONE', 'SEAL' or 'WATCH'.", hint="Capital letters, inside quotes.")
        raise Fail(f"With {shown}: `gate` is {value!r}, expected {expected!r} ({note}).",
                   hint="Python runs the FIRST branch that's True. Write the rules top to bottom in protocol "
                        "order, each as an if or elif, and finish with else for rule 5.")


@MISSION.check("Repair the threat ladder — `threat`")
def _threat_check(ctx):
    ctx.get("threat")
    for s in (74, 99, 90, 70, 69, 40, 39, 0, 100):
        feed = _feed(signal=s)
        value = need(replay(ctx, feed), "threat")
        expected = _threat(feed)
        if value != expected:
            if value == "LOW" and s >= 70:
                hint = ("A signal of {0} is also >= 40, and that branch comes first, so the higher rungs are never "
                        "reached. Put the highest bar at the top of the ladder.").format(s)
            elif s in (90, 70, 40):
                hint = "\"Or more\" includes the number itself: use >=."
            else:
                hint = "Each rung is one if/elif. The final else catches everything below 40."
            raise Fail(f"With signal={s}: `threat` is {value!r}, expected {expected!r}.", hint=hint)


@MISSION.check("Report to NOVA — status line")
def _report(ctx):
    if not ctx.stdout.strip():
        if ctx.crashed:
            raise Fail("Nothing was printed. Your script crashed before it reached the print().")
        raise Fail("Nothing was printed.",
                   hint="print() an f-string in the objective 7 format, with {gate} and {threat} inside it.")
    for var in ("gate", "threat"):
        if not ctx.call_uses("print", var):
            raise Fail(f"Your print() doesn't use the `{var}` variable. Typed-in words can't follow new readings.",
                       hint=f"Put {{{var}}} inside the f-string.")
    for feed in (_feed(), _feed(badge="order", motion=0.0, signal=12), _feed(heat=20.0, signal=95)):
        run = replay(ctx, feed)
        expected = _line(feed)
        if expected not in run.stdout.splitlines():
            got = run.stdout.strip().splitlines()
            shown = repr(got[-1]) if got else "nothing"
            raise Fail(f"With {feed_text(feed)}, NOVA expected the line {expected!r} but your script printed {shown}.",
                       hint="Match it character for character: spaces around each |, no spaces around =.")
