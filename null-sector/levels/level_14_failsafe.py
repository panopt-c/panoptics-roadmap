"""LEVEL 14 // FAILSAFE — try/except/else/finally, raise, custom exceptions, validation."""
from __future__ import annotations

import ast
import contextlib
import io

from engine.mission import Fail, Mission

FEED = ["612.0", " 640.5 ", "ERR#", "955.2", "", "701", "-999", "880.25", "1200", "88O"]

MISSION = Mission(
    id="L14",
    slug="level_14_failsafe",
    title="FAILSAFE",
    concept="Exceptions & validation",
    enemy="GREMLIN.worm",
    xp=280,
    par_seconds=35 * 60,
    tier=3,
    concepts=("exceptions", "inheritance"),
    enemy_art="""\
    ▄▀▄     ▄▀▄
   █ ▀▄▀▀▀▀▀▄▀ █
   █  ▄█▄ ▄█▄  █
   ▀▄  ▀▀ ▀▀  ▄▀
  ▄▀▀█▄ ▀▀▀ ▄█▀▀▄
  ▀  ▀▀█▄▄▄█▀▀  ▀
        ▀▀▀""",
    briefing="""\
NOVA was right. Every failsafe in the Foundry has been stripped out.

The smelter controllers still run, but one bad sensor reading and they crash, and a crashed
controller can't close a valve. **GREMLIN.worm** knows it. It's feeding the sensors garbage:
typos, dead channels, impossible temperatures. Somewhere above the furnaces, someone is
watching to see what breaks first.

Crucible Three is already past 900°C and climbing.

In Python, a failsafe is an **exception handler**: code that expects things to go wrong and
decides, calmly, what happens next.

**Rebuild the failsafes, triage the sensor feed, and keep Crucible Three from melting down.**
""",
    why="""\
Real data is dirty, and real systems fail halfway through. A training pipeline that crashes
on sample 48,113 of 50,000 because one row says `"N/A"` wastes a night of compute. Robust
code decides **which** errors it can handle, handles exactly those, and lets everything else
fail loudly:

```python
class BadSample(ValueError):
    pass

for row in rows:
    try:
        sample = parse(row)          # may raise BadSample
    except BadSample:
        skipped += 1                 # expected: log it, move on
    else:
        dataset.append(sample)
```

`finally` is how GPU memory, file handles and locks get released even when a run dies. And
`raise` is how your own functions refuse bad input at the door, before it poisons a model
three steps later.
""",
    manual="""\
**1. `try` / `except`: catch one specific error.** When a line inside `try` raises, Python
jumps to the first matching `except`. Name the error you expect:

```python
try:
    shells = int("12x")
except ValueError:
    shells = 0                 # the text wasn't a number
```

**2. `else` and `finally`.** `else` runs only if `try` raised **nothing**. `finally` runs
**no matter what**: success, a caught error, an uncaught error, even a `return`:

```python
door.lock()                    # BEFORE try: if locking fails, there's nothing to release
try:
    cargo = scan(door)
except ScanError:
    print("scan failed")
else:
    print("scan ok:", cargo)
finally:
    door.unlock()              # always, even if scan() raised something unexpected
```

An error that no `except` matches still runs `finally`, then keeps going up to the caller.

**3. `raise`: refuse bad input.** Validate first, and fail with a clear message:

```python
def set_speed(kph):
    if kph < 0:
        raise ValueError(f"speed can't be negative: {kph}")
    return kph
```

**4. Custom exceptions are classes.** Inherit from `Exception` (or from one of your own) and
you get a whole family. A child can carry extra data, like any class (L12):

```python
class ScanError(Exception):
    pass

class JamError(ScanError):                 # a JamError IS a ScanError
    def __init__(self, door):
        super().__init__(f"door {door} jammed")   # the message
        self.door = door

try:
    raise JamError(7)
except ScanError as exc:                   # catches JamError too
    print(exc, exc.door)                   # door 7 jammed 7
```

**Order matters.** Python checks `except` clauses top to bottom and uses the first match.
A parent catches all its children, so put the **most specific** one first:

```python
except JamError:     # first: the specific case
    ...
except ScanError:    # then: everything else in the family
    ...
```

**5. Turn a low-level error into your own.** Catch it, then raise the one your callers expect:

```python
try:
    value = float(text)
except ValueError:
    raise ScanError(f"unreadable: {text!r}")
```

**6. Never catch everything.** `except:` or `except Exception:` also swallows your own bugs
(a typo becomes a silent wrong answer). Catch only what you can actually handle.
""",
    starter='''
"""
==============================================================================
  LEVEL 14 // FAILSAFE                                 TARGET: GREMLIN.worm
==============================================================================
  The grader attacks your failsafes with its OWN readings and its OWN
  furnaces, including ones that jam. Handle what you're asked to handle,
  and let everything else escape.
"""


# == THE FURNACE (given: don't edit it) ========================================
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


# -- OBJECTIVE 1 -------------------------------------------------------------
# Build the alarm family:
#   class SensorError(Exception)       a bad or impossible reading
#   class OverheatError(SensorError)   a real reading that is too hot.
#     __init__(self, temp, limit) passes the message
#         f"core at {temp} exceeds limit {limit}"
#     up with super().__init__(...), then stores self.temp and self.limit.
#        example:  class JamError(ScanError):
#                      def __init__(self, door):
#                          super().__init__(f"door {door} jammed")
#                          self.door = door



# -- OBJECTIVE 2 -------------------------------------------------------------
# Write parse_reading(text): turn sensor text into a float.
#   " 451.5 " -> 451.5        "12" -> 12.0        "1e3" -> 1000.0
# If float() can't read it, catch the ValueError and raise SensorError
# instead, with a message that includes the text. Anything colder than
# absolute zero (below -273.15) is impossible: raise SensorError too.
#   "ERR#" -> SensorError      "" -> SensorError      "-300" -> SensorError



# -- OBJECTIVE 3 -------------------------------------------------------------
# Write check_temp(temp, limit=900):
#   limit must be above 0: if it isn't, raise ValueError (check this FIRST).
#   temp above limit      -> raise OverheatError(temp, limit)
#   otherwise             -> return temp unchanged
#   check_temp(900) -> 900     check_temp(901) -> OverheatError     check_temp(5, 0) -> ValueError



# -- OBJECTIVE 4 // CORRUPTED CODE ---------------------------------------------
# triage() sorts a whole feed: good values, faults, overheats. But the alarm
# board says the Foundry has had ZERO overheats today, with Crucible Three
# at 955 degrees. Once objectives 1-3 work, run it on ["950"] and see.
# One thing is in the wrong place. Find it and fix it.
def triage(readings, limit=900):
    report = {"ok": [], "faults": 0, "overheats": 0}
    for text in readings:
        try:
            value = check_temp(parse_reading(text), limit)
        except SensorError:
            report["faults"] += 1
        except OverheatError:
            report["overheats"] += 1
        else:
            report["ok"].append(value)
    return report


# -- OBJECTIVE 5 -------------------------------------------------------------
# Write run_cycle(furnace, readings, limit=900):
#   1. furnace.lock()  (BEFORE the try: if it fails, there's nothing to release)
#   2. try: report = triage(readings, limit); if there was at least one
#      overheat, call furnace.vent() ONCE; return the report.
#   3. finally: furnace.unlock(), always, even if vent() blows up.
# Don't catch anything here. If a valve jams, the error must reach the
# operator, but the furnace must still come unlocked.



# -- OBJECTIVE 6 -------------------------------------------------------------
# Crucible Three's live feed (don't edit it):
FEED = ["612.0", " 640.5 ", "ERR#", "955.2", "", "701", "-999", "880.25", "1200", "88O"]
# Create `crucible`, a Furnace named "CRUCIBLE-3", and run it through
# run_cycle with FEED. Store what run_cycle returns in `report`.



# -- OBJECTIVE 7 -------------------------------------------------------------
# Report to ops. Print this line, reading the numbers from `report`:
#   FAILSAFE | ok=4 | faults=4 | overheats=2

''',
    dialogue={
        "intro": [
            {"speaker": "nova", "mood": "alarm",
             "text": "Ops board is all red, {callsign}. Crucible Three at 912 degrees and climbing. Every failsafe reads OFFLINE."},
            {"speaker": "rust", "mood": "neutral",
             "text": "Somebody pulled them on purpose. Clean cuts. Whoever runs this place wants us cooked."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "A failsafe is just code that expects the worst. Decide which errors you can handle. Let the rest scream."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Uncaught exception. That's exactly what GREMLIN wants. Read which error it was, then decide who should catch it."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "A NameError on SensorError means the class isn't defined yet, or it's defined below the line that uses it."}],
            [{"speaker": "nova", "mood": "alarm",
              "text": "Controller down! Temperature still climbing. Get it back up, {callsign}."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "except clauses are checked top to bottom. A parent catches its children. Specific first."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "finally runs no matter what. If the lock isn't released in every path, it isn't a failsafe."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "Swallowing every error isn't safety. It's a furnace that melts quietly."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "Some layers holding. Keep going, {callsign}. One more fix and ops can breathe."}],
        ],
        "victory": [
            {"speaker": "nova", "mood": "warm",
             "text": "Crucible Three venting! 955 down to 870 and falling. Failsafes ONLINE. Ops is breathing again."},
            {"speaker": "cipher", "mood": "warm",
             "text": "Four bad readings caught, two overheats vented, zero crashes. That's what calm looks like in code."},
            {"speaker": "rust", "mood": "neutral",
             "text": "The Forge doors just unlocked themselves. That's not a welcome. That's an invitation."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "The shards from HALCYON-9 were headed there. Whatever the Forgemaster is making, it's made of data."},
        ],
    },
)


# ── grader reference ───────────────────────────────────────────────────────────

def _ref_kind(text: str, limit: float):
    try:
        value = float(text)
    except ValueError:
        return "fault", None
    if value < -273.15:
        return "fault", None
    if value > limit:
        return "overheat", value
    return "ok", value


def _ref_triage(readings, limit=900):
    report = {"ok": [], "faults": 0, "overheats": 0}
    for text in readings:
        kind, value = _ref_kind(text, limit)
        if kind == "fault":
            report["faults"] += 1
        elif kind == "overheat":
            report["overheats"] += 1
        else:
            report["ok"].append(value)
    return report


EXPECTED_REPORT = _ref_triage(FEED)
EXPECTED_LINE = (f"FAILSAFE | ok={len(EXPECTED_REPORT['ok'])} | faults={EXPECTED_REPORT['faults']} "
                 f"| overheats={EXPECTED_REPORT['overheats']}")


class _ProbeFurnace:
    """The grader's own furnace: records every call, and can be rigged to jam."""

    def __init__(self, name, *, jam=False, locked=False):
        self.name = name
        self.locked = locked
        self.vented = 0
        self.jam = jam
        self.log = []

    def lock(self):
        self.log.append("lock")
        if self.locked:
            raise RuntimeError(f"{self.name} is already locked")
        self.locked = True

    def unlock(self):
        self.log.append("unlock")
        self.locked = False

    def vent(self):
        self.log.append("vent")
        if self.jam:
            raise RuntimeError(f"{self.name}: vent valve jammed")
        self.vented += 1


# ── grader helpers ──────────────────────────────────────────────────────────────

def _defined(ctx, kinds, name: str) -> bool:
    return any(isinstance(n, kinds) and n.name == name for n in ctx.tree.body)


def _lookup(ctx, name: str, kinds, hint: str):
    if name in ctx.ns:
        return ctx.ns[name]
    if ctx.crashed and _defined(ctx, kinds, name):
        raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                   "Fix the crash in the COMBAT LOG first.")
    raise Fail(f"No `{name}` found.", hint=hint)


def _exc_class(ctx, name: str, parent_hint: str) -> type:
    cls = _lookup(ctx, name, ast.ClassDef, f"class {name}({parent_hint}):")
    if not (isinstance(cls, type) and issubclass(cls, BaseException)):
        raise Fail(f"`{name}` isn't an exception class.", hint=f"Inherit from an exception:  class {name}({parent_hint}):")
    return cls


def _func(ctx, name: str, signature: str):
    fn = _lookup(ctx, name, ast.FunctionDef, f"def {signature}:")
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"def {signature}:")
    return fn


def _run(fn, *args, **kwargs):
    """Call player code with its prints silenced. Returns (value, exception)."""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args, **kwargs), None
    except Exception as exc:  # noqa: BLE001 — inspected by the caller
        return None, exc


def _blanket_handlers(tree: ast.AST) -> list[int]:
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            t = node.type
            if t is None or (isinstance(t, ast.Name) and t.id in ("Exception", "BaseException")):
                lines.append(node.lineno)
    return sorted(lines)


def _upstream(_ctx) -> str:
    return " (triage() uses your parse_reading() and check_temp(): if their layers are red, fix those first.)"


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Alarm family — `SensorError` and `OverheatError`")
def _family(ctx):
    SensorError = _exc_class(ctx, "SensorError", "Exception")
    OverheatError = _exc_class(ctx, "OverheatError", "SensorError")
    if not issubclass(SensorError, Exception):
        raise Fail("SensorError should inherit from Exception.", hint="class SensorError(Exception):")
    if not issubclass(OverheatError, SensorError):
        raise Fail("OverheatError isn't a kind of SensorError, so `except SensorError` won't catch it.",
                   hint="Name the parent in brackets:  class OverheatError(SensorError):")
    plain = SensorError("dead channel")
    if str(plain) != "dead channel":
        raise Fail(f'SensorError("dead channel") reads {str(plain)!r}. A plain SensorError should keep its message.',
                   hint="SensorError needs no body of its own:  pass  is enough.")
    err, exc = _run(OverheatError, 950.5, 900)
    if exc is not None:
        raise Fail(f"Building OverheatError(950.5, 900) crashed: {type(exc).__name__}: {exc}",
                   hint="def __init__(self, temp, limit):")
    if getattr(err, "temp", None) != 950.5 or getattr(err, "limit", None) != 900:
        raise Fail(f"OverheatError(950.5, 900) has temp={getattr(err, 'temp', None)!r} and limit="
                   f"{getattr(err, 'limit', None)!r}, expected 950.5 and 900.",
                   hint="Store both after super().__init__(...):  self.temp = temp  and  self.limit = limit")
    if len(err.args) != 1 or not isinstance(err.args[0], str):
        raise Fail(f"OverheatError(950.5, 900) reads {str(err)!r}: its message was never set.",
                   hint='Pass ONE message string up:  super().__init__(f"core at {temp} exceeds limit {limit}")')
    if "950.5" not in str(err) or "900" not in str(err):
        raise Fail(f"OverheatError(950.5, 900) reads {str(err)!r}. The message should name the temperature and the limit.",
                   hint='f"core at {temp} exceeds limit {limit}"')
    try:
        raise OverheatError(1200, 900)
    except SensorError as caught:
        if getattr(caught, "temp", None) != 1200:
            raise Fail("A caught OverheatError lost its temperature.", hint="self.temp = temp")


@MISSION.check("Sensor parser — `parse_reading()` raises SensorError")
def _parse(ctx):
    SensorError = _exc_class(ctx, "SensorError", "Exception")
    fn = _func(ctx, "parse_reading", "parse_reading(text)")
    good = [(" 451.5 ", 451.5), ("12", 12.0), ("-40", -40.0), ("1e3", 1000.0), ("-273.15", -273.15)]
    for text, expected in good:
        got, exc = _run(fn, text)
        if exc is not None:
            raise Fail(f"parse_reading({text!r}) raised {type(exc).__name__}: {exc}. That's a valid reading.",
                       hint="float() reads numbers like \" 451.5 \" and \"1e3\" on its own, spaces included.")
        if type(got) is not float or got != expected:
            raise Fail(f"parse_reading({text!r}) returned {got!r}, expected {expected!r} (a float).",
                       hint="Return float(text).")
    bad = [("ERR#", "garbage"), ("", "an empty reading"), ("   ", "a blank channel"),
           ("88O", "a typo (letter O, not zero)"), ("-300", "a temperature below absolute zero"),
           ("-273.16", "a hair below absolute zero")]
    for text, what in bad:
        got, exc = _run(fn, text)
        if exc is None:
            raise Fail(f"parse_reading({text!r}), {what}, returned {got!r} instead of raising SensorError.",
                       hint=("Anything below -273.15 is impossible:  raise SensorError(...)" if text.startswith("-")
                             else "Wrap float(text) in try/except ValueError, and raise SensorError in the except."))
        if isinstance(exc, ValueError) and not isinstance(exc, SensorError):
            raise Fail(f"parse_reading({text!r}) let the raw ValueError escape: {exc}.",
                       hint="Catch the ValueError and raise SensorError instead. Callers only know about SensorError.")
        if not isinstance(exc, SensorError):
            raise Fail(f"parse_reading({text!r}) raised {type(exc).__name__}: {exc}, expected a SensorError.",
                       hint="raise SensorError(f\"unreadable: {text!r}\")")
        if not str(exc).strip():
            raise Fail(f"parse_reading({text!r}) raised a SensorError with no message. Ops needs to know what was wrong.",
                       hint="Put the text in the message:  raise SensorError(f\"unreadable: {text!r}\")")


@MISSION.check("Temperature gate — `check_temp()` validates and raises")
def _gate(ctx):
    OverheatError = _exc_class(ctx, "OverheatError", "SensorError")
    fn = _func(ctx, "check_temp", "check_temp(temp, limit=900)")
    for args, expected in (((500,), 500), ((900,), 900), ((12.5, 40), 12.5), ((-50, 1),  -50)):
        got, exc = _run(fn, *args)
        shown = ", ".join(map(repr, args))
        if exc is not None:
            raise Fail(f"check_temp({shown}) raised {type(exc).__name__}: {exc}, but that temperature is safe.",
                       hint="Exactly at the limit is still safe: only raise when temp > limit.")
        if got != expected:
            raise Fail(f"check_temp({shown}) returned {got!r}, expected {expected!r}.",
                       hint="When the temperature is safe, return it unchanged.")
    for args, temp, limit in (((900.5,), 900.5, 900), ((50, 40), 50, 40)):
        got, exc = _run(fn, *args)
        shown = ", ".join(map(repr, args))
        if exc is None:
            raise Fail(f"check_temp({shown}) returned {got!r}. {temp} is over the limit of {limit}: raise OverheatError.",
                       hint="if temp > limit:  raise OverheatError(temp, limit)")
        if not isinstance(exc, OverheatError):
            raise Fail(f"check_temp({shown}) raised {type(exc).__name__}, expected OverheatError.")
        if getattr(exc, "temp", None) != temp or getattr(exc, "limit", None) != limit:
            raise Fail(f"check_temp({shown}) raised an OverheatError with temp={getattr(exc, 'temp', None)!r}, "
                       f"limit={getattr(exc, 'limit', None)!r}. Expected {temp} and {limit}.",
                       hint="raise OverheatError(temp, limit), with the values you were given.")
    for args in ((10, 0), (10, -5), (-20, -30)):
        got, exc = _run(fn, *args)
        shown = ", ".join(map(repr, args))
        if exc is None or isinstance(exc, OverheatError) or not isinstance(exc, ValueError):
            what = f"returned {got!r}" if exc is None else f"raised {type(exc).__name__}"
            raise Fail(f"check_temp({shown}) {what}. A limit of {args[1]} makes no sense: raise ValueError.",
                       hint="Validate the limit FIRST, before comparing:  if limit <= 0: raise ValueError(...)")


@MISSION.check("Alarm board — corrupted `triage()` repaired")
def _triage(ctx):
    fn = _func(ctx, "triage", "triage(readings, limit=900)")
    cases = [
        ((["100", " 905.5", "x", "-500", "899.9", "1e4", ""],), {}),
        ((["450", "451", "abc", "450.0"],), {"limit": 450}),
        (([],), {}),
        ((["950"],), {}),
    ]
    for args, kwargs in cases:
        expected = _ref_triage(*args, **kwargs)
        got, exc = _run(fn, *[list(a) for a in args], **kwargs)
        shown = repr(args[0]) + "".join(f", {k}={v!r}" for k, v in kwargs.items())
        if exc is not None:
            raise Fail(f"triage({shown}) crashed: {type(exc).__name__}: {exc}." + _upstream(ctx),
                       hint="Every reading GREMLIN sends should land in ok, faults or overheats.")
        if got != expected:
            hint = "Compare your result with the reading list one value at a time." + _upstream(ctx)
            if (isinstance(got, dict) and expected["overheats"] and got.get("overheats") == 0
                    and got.get("faults") == expected["faults"] + expected["overheats"]):
                hint = ("Every overheat was filed as a fault. An OverheatError IS a SensorError, and Python uses the "
                        "FIRST except that matches. Which clause should come first?")
            raise Fail(f"triage({shown}) returned {got!r}, expected {expected!r}.", hint=hint)


@MISSION.check("Furnace failsafe — `run_cycle()` always unlocks")
def _cycle(ctx):
    fn = _func(ctx, "run_cycle", "run_cycle(furnace, readings, limit=900)")
    blanket = _blanket_handlers(ctx.tree)
    if blanket:
        raise Fail(f"Line {blanket[0]} catches every possible error. That also hides real bugs, like a jammed valve.",
                   hint="Catch only the errors you can handle by name (SensorError, ValueError...). Let the rest escape.")

    hot = ["400", "1300", "bad", "910"]
    triage = ctx.ns.get("triage")
    if callable(triage):
        sample, exc = _run(triage, list(hot))
        if exc is not None or sample != _ref_triage(hot):
            raise Fail("run_cycle() stands on triage(), and triage() still sorts the feed wrong.",
                       hint="Turn the Alarm board layer green first, then come back to the furnace.")
    oven = _ProbeFurnace("PROBE-1")
    got, exc = _run(fn, oven, list(hot))
    if exc is not None:
        raise Fail(f"run_cycle() crashed on a normal feed: {type(exc).__name__}: {exc}.",
                   hint="Lock, then triage the readings, vent if there were overheats, unlock in finally.")
    if got != _ref_triage(hot):
        raise Fail(f"run_cycle() returned {got!r}, expected the triage report {_ref_triage(hot)!r}.",
                   hint="Return what triage(readings, limit) gives you.")
    if oven.log[:1] != ["lock"]:
        raise Fail(f"The furnace was never locked first (calls: {oven.log}).", hint="Start with furnace.lock()")
    if oven.vented != 1:
        raise Fail(f"A feed with 2 overheats vented the furnace {oven.vented} times. Vent exactly once if there were any.",
                   hint='if report["overheats"]:  furnace.vent()')
    if oven.locked or oven.log[-1:] != ["unlock"]:
        raise Fail(f"After a normal cycle the furnace is still locked (calls: {oven.log}).",
                   hint="Put furnace.unlock() in a finally: block so it runs on every path.")

    calm = _ProbeFurnace("PROBE-2")
    got, exc = _run(fn, calm, ["40", "45"], 50)
    if exc is not None or got != _ref_triage(["40", "45"], 50):
        raise Fail(f"run_cycle(furnace, ['40', '45'], 50) gave {got!r} ({exc!r}), expected {_ref_triage(['40', '45'], 50)!r}.",
                   hint="Pass the limit through to triage(readings, limit).")
    if calm.vented or "vent" in calm.log:
        raise Fail("A calm feed with no overheats still vented the furnace.", hint="Only vent when report[\"overheats\"] > 0.")

    jammed = _ProbeFurnace("PROBE-3", jam=True)
    got, exc = _run(fn, jammed, ["2000"])
    if exc is None:
        raise Fail("A jammed vent valve raised RuntimeError, and run_cycle() swallowed it. The operator never found out.",
                   hint="Don't catch anything in run_cycle(). try/finally releases the lock and lets the error through.")
    if not (isinstance(exc, RuntimeError) and "jammed" in str(exc)):
        raise Fail(f"A jammed valve should reach the caller as its own RuntimeError, but run_cycle() raised "
                   f"{type(exc).__name__}: {exc}.", hint="Let the original error escape: no except, just finally.")
    if jammed.locked:
        raise Fail("The vent valve jammed, and the furnace was left LOCKED. That's the meltdown.",
                   hint="finally:  furnace.unlock()  runs even while an error is escaping.")

    held = _ProbeFurnace("PROBE-4", locked=True)
    got, exc = _run(fn, held, ["10"])
    if exc is None:
        raise Fail("run_cycle() on a furnace someone else had locked carried on anyway.",
                   hint="Let furnace.lock()'s RuntimeError escape.")
    if "unlock" in held.log:
        raise Fail("lock() failed because another operator holds the furnace, and run_cycle() unlocked it anyway.",
                   hint="Call furnace.lock() BEFORE try: if locking fails, you never held the lock, so there's nothing to release.")


@MISSION.check("Crucible Three — live feed `report`")
def _live(ctx):
    feed = ctx.get("FEED")
    if feed != FEED:
        raise Fail("FEED was changed. That's GREMLIN's live data; you don't get to pick nicer readings.",
                   hint="Restore the FEED line from the starter.")
    Furnace = _lookup(ctx, "Furnace", ast.ClassDef, "Restore the given Furnace class from the starter.")
    crucible = ctx.get("crucible")
    if not isinstance(crucible, Furnace):
        raise Fail(f"`crucible` is {type(crucible).__name__}, not a Furnace.", hint='crucible = Furnace("CRUCIBLE-3")')
    if getattr(crucible, "name", None) != "CRUCIBLE-3":
        raise Fail(f"`crucible` is named {getattr(crucible, 'name', None)!r}, expected 'CRUCIBLE-3'.")
    report = ctx.get("report")
    if not ctx.call_uses("run_cycle", "FEED") or not ctx.derived_from("report", "crucible"):
        raise Fail("`report` didn't come from run_cycle(crucible, FEED).", hint="report = run_cycle(crucible, FEED)")
    if report != EXPECTED_REPORT:
        raise Fail(f"`report` is {report!r}, expected {EXPECTED_REPORT!r}.",
                   hint="If your function layers are green, check that you ran the untouched FEED.")
    if crucible.locked:
        raise Fail("Crucible Three is still locked after the cycle.", hint="run_cycle() must unlock in finally.")
    if crucible.vented != 1:
        raise Fail(f"Crucible Three vented {crucible.vented} times. Two overheats in one cycle means one vent.")


@MISSION.check("Report to ops")
def _broadcast(ctx):
    if not ctx.stdout.strip():
        if ctx.crashed:
            raise Fail("Nothing was reported. Your script crashed before the print().")
        raise Fail("Nothing was printed.", hint=f"print(f\"FAILSAFE | ok={{len(report['ok'])}} | ...\")")
    if not ctx.call_uses("print", "report"):
        raise Fail("Your print() doesn't read from `report`. Don't type the numbers in yourself.",
                   hint="Use an f-string: len(report['ok']), report['faults'], report['overheats'].")
    if EXPECTED_LINE not in [line.strip() for line in ctx.stdout.splitlines()]:
        raise Fail(f"Ops expected the line {EXPECTED_LINE!r}.",
                   hint=f"Your output was: {ctx.stdout.strip()[:140]!r}. Spacing and labels must match exactly.")
