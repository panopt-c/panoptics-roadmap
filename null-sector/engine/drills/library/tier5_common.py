"""Tier-5 drill toolkit: shared check helpers for the endgame drills.

This module registers no drills. The other `tier5_*` modules use it so every endgame drill
fails the same way: the exact call that broke, what came back, what was expected, and, when a
classic mistake is recognisable, a message aimed squarely at that mistake.

Vocabulary used by the helpers:

* a **case** is a tuple of positional arguments, or a dict of keyword arguments;
* a **spot** is `spot(got, args, kwargs) -> (message, hint) | None`, called on a wrong answer
  to name a known mistake ("you divided by n - 1", "you forgot the minus sign");
* an **errors** diagnoser is `errors(exc) -> (message, hint) | None`, called when the player's
  code raises, to explain a known crash (`OverflowError` from `math.exp`, `math domain error`).
"""
from __future__ import annotations

import contextlib
import copy
import math
import time
from typing import Callable

from engine.mission import Fail, type_name

TIER = 5
SEQ_PREVIEW = 10          # items shown per list/tuple/dict in a failure message


class Runaway(BaseException):
    """Raised by the fakes in a check when the player's loop never stops.

    It derives from BaseException on purpose: a retry loop that catches `Exception` can't
    swallow it, so a runaway loop ends the layer cleanly instead of timing out the grader.
    """


# ── showing values ────────────────────────────────────────────────────────────────────

def _fmt(value) -> str:
    if value is None or isinstance(value, bool):
        return repr(value)
    if isinstance(value, float):
        text = repr(value)
        if math.isfinite(value) and len(text) > 13:
            text = f"{value:.10g}"
            if not any(ch in text for ch in ".e"):
                text += ".0"
        return text
    if isinstance(value, (list, tuple)):
        items = [_fmt(v) for v in value[:SEQ_PREVIEW]]
        if len(value) > SEQ_PREVIEW:
            items.append("…")
        inner = ", ".join(items)
        if isinstance(value, list):
            return f"[{inner}]"
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    if isinstance(value, dict):
        pairs = [f"{_fmt(k)}: {_fmt(v)}" for k, v in list(value.items())[:SEQ_PREVIEW]]
        if len(value) > SEQ_PREVIEW:
            pairs.append("…")
        return "{" + ", ".join(pairs) + "}"
    try:
        return repr(value)
    except Exception:  # noqa: BLE001 — a broken __repr__ in player code must not crash the check
        return f"<{type(value).__name__}>"


def show(value, limit: int = 140) -> str:
    """A short, readable repr: floats trimmed to 10 significant digits, long data elided."""
    text = _fmt(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def rounded(value, digits: int = 4):
    """Floats rounded to `digits` inside any nest of lists/tuples/dicts (for display only)."""
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, list):
        return [rounded(v, digits) for v in value]
    if isinstance(value, tuple):
        return tuple(rounded(v, digits) for v in value)
    if isinstance(value, dict):
        return {k: rounded(v, digits) for k, v in value.items()}
    return value


def call_text(name: str, args=(), kwargs=None) -> str:
    parts = [show(a, 70) for a in args] + [f"{k}={show(v, 50)}" for k, v in (kwargs or {}).items()]
    return f"{name}({', '.join(parts)})"


def r(value: float, digits: int = 4) -> float:
    """Round for display in a prompt example."""
    return round(value, digits)


# ── comparing values ──────────────────────────────────────────────────────────────────

def same(got, expected, *, approx: bool = True, rel_tol: float = 1e-6, abs_tol: float = 1e-9) -> bool:
    """Structural equality; numbers within tolerance when `approx`. Container types must match."""
    if isinstance(expected, bool) or isinstance(got, bool):
        return type(got) is type(expected) and got == expected
    if isinstance(expected, (int, float)):
        if not isinstance(got, (int, float)):
            return False
        if approx:
            return math.isclose(got, expected, rel_tol=rel_tol, abs_tol=abs_tol)
        return type(got) is type(expected) and got == expected
    if isinstance(expected, (list, tuple)):
        return (type(got) is type(expected) and len(got) == len(expected)
                and all(same(g, e, approx=approx, rel_tol=rel_tol, abs_tol=abs_tol)
                        for g, e in zip(got, expected)))
    if isinstance(expected, dict):
        return (isinstance(got, dict) and got.keys() == expected.keys()
                and all(same(got[k], expected[k], approx=approx, rel_tol=rel_tol, abs_tol=abs_tol)
                        for k in expected))
    return type(got) is type(expected) and got == expected


def near(got, expected, tol: float = 1e-6) -> bool:
    """Loose numeric match used by spotters to recognise a known wrong answer."""
    try:
        return same(got, expected, approx=True, rel_tol=tol, abs_tol=tol)
    except Exception:  # noqa: BLE001
        return False


def shape_note(got, expected) -> str:
    """One sentence on HOW a result is off, when the problem is structural."""
    if got is None and expected is not None:
        return " It returned None: every path through the function needs a `return`."
    if isinstance(expected, (list, tuple, dict)) and type(got) is not type(expected):
        return f" That's {type_name(type(got))}; the contract asks for {type_name(type(expected))}."
    if isinstance(expected, (list, tuple)) and len(got) != len(expected):
        return f" It has {len(got)} items; it should have {len(expected)}."
    if isinstance(expected, (int, float)) and not isinstance(expected, bool) \
            and (not isinstance(got, (int, float)) or isinstance(got, bool)):
        return f" That's {type_name(type(got))}, not a number."
    if isinstance(expected, (list, tuple)) and expected and isinstance(got, (list, tuple)) and got:
        inner_e, inner_g = expected[0], got[0]
        if isinstance(inner_e, (list, tuple, dict)) and type(inner_g) is not type(inner_e):
            return (f" Each item should be {type_name(type(inner_e))}; yours are "
                    f"{type_name(type(inner_g))}.")
    return ""


# ── calling the player's code ─────────────────────────────────────────────────────────

def function(ctx, name: str):
    fn = ctx.get(name)
    if isinstance(fn, type) or not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return fn


def klass(ctx, name: str):
    cls = ctx.get(name)
    if not isinstance(cls, type):
        raise Fail(f"`{name}` exists but isn't a class.", hint=f"Define it with  class {name}:")
    return cls


def _split(case):
    if isinstance(case, dict):
        return (), dict(case)
    return tuple(case), {}


def invoke(fn, shown: str, args=(), kwargs=None, *, hint: str = "",
           errors: Callable | None = None, runaway: str = ""):
    """Call player code; any crash becomes a Fail that names the exact call."""
    try:
        return fn(*args, **(kwargs or {}))
    except Runaway:
        raise Fail(f"`{shown}` never stopped. {runaway or 'Your loop kept going past every limit.'}",
                   hint=hint) from None
    except Fail:
        raise
    except SystemExit:
        raise Fail(f"`{shown}` called exit(), which would shut down the whole program it lives in.",
                   hint="Report problems by raising an exception or returning a value, never by exiting.") from None
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        found = errors(exc) if errors else None
        if found:
            raise Fail(f"`{shown}` raised {type(exc).__name__}: {exc}. {found[0]}", hint=found[1] or hint) from None
        raise Fail(f"`{shown}` raised {type(exc).__name__}: {exc}",
                   hint=hint or "Call your function on this input yourself and read the traceback.") from None


def expect(ctx, name: str, cases, reference: Callable, *, approx: bool = True, rel_tol: float = 1e-6,
           abs_tol: float = 1e-9, hint: str = "", pure: bool = False, spot: Callable | None = None,
           errors: Callable | None = None) -> None:
    """Call `name` on every case and compare with `reference` (both on deep copies).

    `pure=True` also fails if the function changed the arguments it was given.
    """
    fn = function(ctx, name)
    for case in cases:
        args, kwargs = _split(case)
        shown = call_text(name, args, kwargs)
        expected = reference(*copy.deepcopy(args), **copy.deepcopy(kwargs))
        given_args, given_kwargs = copy.deepcopy(args), copy.deepcopy(kwargs)
        got = invoke(fn, shown, given_args, given_kwargs, hint=hint, errors=errors)
        if not same(got, expected, approx=approx, rel_tol=rel_tol, abs_tol=abs_tol):
            found = spot(got, copy.deepcopy(args), copy.deepcopy(kwargs)) if spot else None
            if found:
                raise Fail(f"`{shown}` returned {show(got)}. {found[0]}", hint=found[1] or hint)
            raise Fail(f"`{shown}` returned {show(got)} — expected {show(expected)}.{shape_note(got, expected)}",
                       hint=hint)
        if pure and (given_args != args or given_kwargs != kwargs):
            raise Fail(f"`{shown}` returned the right answer but changed the data it was given "
                       f"(the caller's input is now {show(given_args or given_kwargs, 90)}).",
                       hint="Never edit the caller's lists in place. Build new lists (a comprehension, "
                            "or list(x) to copy) and return those.")


def expect_raises(ctx, name: str, args=(), kwargs=None, *, exc=ValueError, why: str = "", hint: str = "",
                  spot: Callable | None = None) -> None:
    """`name(*args)` must raise `exc` (or a subclass)."""
    fn = function(ctx, name)
    kwargs = kwargs or {}
    shown = call_text(name, args, kwargs)
    reason = f" ({why})" if why else ""
    try:
        got = fn(*copy.deepcopy(args), **copy.deepcopy(kwargs))
    except Runaway:
        raise Fail(f"`{shown}` never stopped.", hint=hint) from None
    except SystemExit:
        raise Fail(f"`{shown}` called exit() instead of raising {exc.__name__}.", hint=hint) from None
    except exc:
        return
    except Exception as other:  # noqa: BLE001
        raise Fail(f"`{shown}` raised {type(other).__name__}: {other}. The contract says {exc.__name__}{reason}.",
                   hint=hint or f"Check the input yourself at the top of the function and  raise {exc.__name__}(...)") from None
    found = spot(got, copy.deepcopy(args), dict(kwargs)) if spot else None
    if found:
        raise Fail(f"`{shown}` returned {show(got)}. {found[0]}", hint=found[1] or hint)
    raise Fail(f"`{shown}` returned {show(got)} instead of raising {exc.__name__}{reason}.",
               hint=hint or f"Check the input at the top of the function and  raise {exc.__name__}(\"...\")")


def construct(ctx, cls_name: str, args=(), kwargs=None, *, hint: str = ""):
    cls = klass(ctx, cls_name)
    return invoke(cls, call_text(cls_name, args, kwargs), args, kwargs, hint=hint)


def method(obj, label: str, meth: str, args=(), kwargs=None, *, hint: str = ""):
    """Call obj.meth(*args) with crash reporting, shown as `label.meth(...)`."""
    shown = call_text(f"{label}.{meth}", args, kwargs)
    bound = getattr(obj, meth, None)
    if not callable(bound):
        raise Fail(f"`{label}` has no `{meth}()` method.", hint=f"Add  def {meth}(self, ...):  inside the class.")
    return invoke(bound, shown, args, kwargs, hint=hint)


# ── fakes for time-dependent code ─────────────────────────────────────────────────────

class FakeClock:
    """An injectable clock: `clock()` returns `clock.now`, which only moves when a check says so."""

    def __init__(self, start: float = 0.0):
        self.now = float(start)
        self.reads = 0

    def __call__(self) -> float:
        self.reads += 1
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SleepRecorder:
    """An injectable `sleep`: records every delay, never blocks, stops runaway loops."""

    def __init__(self, cap: int = 40):
        self.delays: list[float] = []
        self.cap = cap

    def __call__(self, seconds: float = 0) -> None:
        self.delays.append(seconds)
        if len(self.delays) > self.cap:
            raise Runaway("sleep() called too many times")


_CLOCK_NAMES = ("time", "monotonic", "perf_counter", "time_ns", "monotonic_ns", "perf_counter_ns")


@contextlib.contextmanager
def guard_real_time(ctx):
    """Inside the block, `time.sleep` never blocks and reads of the real clock are recorded.

    Yields a dict {"sleeps": [...], "clock": [...]} so a check can fail with a precise message
    when player code reaches for the real clock instead of the one it was handed. Aliases such
    as `from time import sleep` in the player's module are patched too.
    """
    seen = {"sleeps": [], "clock": []}
    originals = {"sleep": time.sleep, **{n: getattr(time, n) for n in _CLOCK_NAMES}}

    def fake_sleep(seconds=0):
        seen["sleeps"].append(seconds)
        if len(seen["sleeps"]) > 200:
            raise Runaway("time.sleep called too many times")

    def spy(name, real):
        def read(*a, **k):
            seen["clock"].append(name)
            return real(*a, **k)
        return read

    patched = {"sleep": fake_sleep, **{n: spy(n, originals[n]) for n in _CLOCK_NAMES}}
    aliases = {}
    for key, value in list(ctx.ns.items()):
        for name, real in originals.items():
            if value is real:
                aliases[key] = name
    for name, fake in patched.items():
        setattr(time, name, fake)
    for key, name in aliases.items():
        ctx.ns[key] = patched[name]
    try:
        yield seen
    finally:
        for name, real in originals.items():
            setattr(time, name, real)
        for key, name in aliases.items():
            ctx.ns[key] = originals[name]


# ── small math helpers shared by references ───────────────────────────────────────────

def stable_softmax(values: list[float]) -> list[float]:
    if not values:
        return []
    top = max(values)
    exps = [math.exp(v - top) for v in values]
    total = sum(exps)
    return [e / total for e in exps]


def dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


STARTER_HEADER = '''"""
==============================================================================
  DRILL // {title:<44}TIER 5 // EXPERT
==============================================================================
  Implement everything below, save, then HACK.
  Running this file yourself executes the sample at the bottom; the grader
  ignores that block and calls your code on fresh, hidden inputs.
"""
'''


def header(title: str) -> str:
    return STARTER_HEADER.format(title=title)


# ── building a tier-5 drill mission ───────────────────────────────────────────────────

def line(speaker: str, text: str, mood: str = "neutral") -> dict:
    """One dialogue line (GAME_DESIGN §5.2)."""
    return {"speaker": speaker, "text": text, "mood": mood}


CRASH_POOL = [
    [line("cipher", "Your file crashed before the grader could ask it anything. The last line of the trace names the problem.", "alarm")],
    [line("cipher", "Crash on load. Run the file yourself once: the sample block at the bottom will show you the same error.", "alarm")],
    [line("rust", "Code fell over before the test even started. I don't pay for parts that arrive in pieces.", "smirk")],
]

FAIL_POOL = [
    [line("cipher", "The failing layer shows the exact input. Run that one case by hand and compare each step.", "neutral")],
    [line("cipher", "Close is not equal. Check the edge case in the message first: empty input, a tie, a huge value.", "neutral")],
    [line("vex", "Still stuck? I cleared this one between breakfast and the Arena. Read the hint, {callsign}.", "smirk")],
    [line("nova", "Contract's still open, {callsign}. One layer at a time. The log tells you which one.", "warm")],
]


def dialogue(intro: list[dict], victory: list[dict]) -> dict:
    return {"intro": intro, "crash": CRASH_POOL, "fail": FAIL_POOL, "victory": victory}


def build(*, title: str, enemy: str, prompt: str, manual: str, starter: str, concepts: tuple[str, ...],
          intro: list[dict], victory: list[dict], timeout: float = 10.0):
    """A tier-5 drill Mission with the house header, dialogue and enemy name."""
    from engine.drills import make_mission   # late import: engine.drills imports this package
    mission = make_mission(title=title, prompt=prompt, starter=header(title) + starter.lstrip("\n"),
                           tier=TIER, concepts=concepts, manual=manual, enemy=enemy, timeout=timeout)
    mission.dialogue = dialogue(intro, victory)
    return mission


# ── seeded data ───────────────────────────────────────────────────────────────────────

def num(rng, lo: float = -3.0, hi: float = 3.0, digits: int = 2) -> float:
    """A random float rounded for readable failure messages (never -0.0)."""
    return round(rng.uniform(lo, hi), digits) + 0.0


def vector(rng, n: int, lo: float = -3.0, hi: float = 3.0, digits: int = 2) -> list[float]:
    return [num(rng, lo, hi, digits) for _ in range(n)]


def matrix(rng, rows: int, cols: int, lo: float = -3.0, hi: float = 3.0, digits: int = 2) -> list[list[float]]:
    return [vector(rng, cols, lo, hi, digits) for _ in range(rows)]


def overflow_errors(exc):
    """Diagnoser for the classic exp() blow-ups in softmax, sigmoid and cross-entropy."""
    text = str(exc)
    if isinstance(exc, OverflowError):
        return ("math.exp() overflows for inputs above about 709.",
                "Shift before exponentiating: subtract the largest value first, so the biggest exponent is exp(0) = 1.")
    if isinstance(exc, ZeroDivisionError):
        return ("Every exp() underflowed to 0.0, so the total was 0.",
                "Subtract the largest value before calling exp(): the top term becomes exp(0) = 1 and the sum can't be 0.")
    if isinstance(exc, ValueError) and "math domain error" in text:
        return ("math.log() was handed 0 (or a negative number).",
                "A probability can round down to exactly 0.0. Clip it, or work with logits and log-sum-exp.")
    return None
