"""LEVEL 09 // SUBROUTINES — def, parameters, return, defaults, keyword args, docstrings, scope, sorted(key=lambda).

From here on the player writes functions, and every layer calls them on fresh inputs.
"""
from __future__ import annotations

import ast
import copy

from engine.drills import compare_cases
from engine.mission import Fail, Mission

CENSUS = [
    {"id": "  sig-0412 ", "strength": 88},
    {"id": "vx-0007", "strength": 140},
    {"id": " SIG-0099\n", "strength": -5},
    {"id": "grid-3", "strength": 88},
    {"id": "Sig-0150", "strength": 61},
]
RITES = ("clean_id", "clamp", "normalize", "count_red", "rank")


def _clean_id(raw):
    return raw.strip().upper()


def _clamp(value, low=0, high=100):
    return min(max(value, low), high)


def _normalize(value, low, high):
    if high == low:
        return 0.0
    return (_clamp(value, low, high) - low) / (high - low)


def _count_red(levels):
    return sum(1 for level in levels if level == "RED")


def _rank(records, top=3):
    return [r["id"] for r in sorted(records, key=lambda r: (-r["strength"], r["id"]))][:top]


def _cleaned():
    return [{"id": _clean_id(r["id"]), "strength": _clamp(r["strength"])} for r in CENSUS]


MISSION = Mission(
    id="L09",
    slug="level_09_subroutines",
    title="SUBROUTINES",
    concept="Functions, params & return",
    enemy="PROCTOR.ice",
    xp=210,
    par_seconds=30 * 60,
    tier=2,
    concepts=("functions", "sorting"),
    timeout=8.0,
    enemy_art="""\
      ▄▄████▄▄
    ▄█▀▀    ▀▀█▄
   ██  ▄▄  ▄▄  ██
   ██  ▀▀  ▀▀  ██
   ▐█▄  ▄▀▀▄  ▄█▌
    ▀██▄▄▄▄▄▄██▀
   ▄▄█▀▀▀▀▀▀▀▀█▄▄""",
    briefing="""\
With the reactor stable, the Scriptorium wakes: a ring of terminals under a ceiling of
cables, lit like candles. The Order keeps its codex here. Not books. **Subroutines**,
written once, named, trusted, and passed from hand to hand since before the Null Event.

To be allowed to add to the codex, you sit the rites. The examiner is **PROCTOR.ice**, as old
as the tower. It never asks the same question twice. Whatever you write, it will call with
inputs you have never seen.

The four rites are carved over the door: *Name it. Take only what you are given. Return
what you promised. Leave the world as you found it.*

**Write your rites, prove them on the Proctor's questions, and earn your place in the
codex.**
""",
    why="""\
Every serious AI pipeline is built from small, named functions. The same preprocessing
must run identically on training data, on test data, and on live requests a year later:

```python
def normalize(x, low, high):
    \"\"\"Scale x into the range 0..1.\"\"\"
    return (x - low) / (high - low)

features = [normalize(t, 35.0, 40.0) for t in temperatures]
```

Copy-paste that formula into three places and one of them *will* drift. A function is
written once, tested once, and trusted everywhere. Parameters make it reusable, `return`
makes it composable, and a function that never edits anything outside itself can be
tested in isolation: same input, same output, every time. That property is what lets
teams of engineers build on each other's code.
""",
    manual="""\
**1 · `def` names a block of code; calling it runs the block.** `return` hands a value back
to whoever called. `print` only shows text: a function that prints but never returns gives
back `None`.

```python
def double(n):
    return n * 2

ammo = double(6)        # 12
```

**2 · Parameters, defaults and keyword arguments.** A default is used when the caller
leaves that argument out. Callers can name arguments, in any order:

```python
def greet(name, greeting="hi", mark="!"):
    return f"{greeting} {name}{mark}"

greet("kade")                    # 'hi kade!'
greet("kade", mark="?")          # 'hi kade?'  (greeting keeps its default)
```

`min(a, b)` and `max(a, b)` return the smaller and larger of two values, handy for limits.

**3 · Docstrings.** A string on the first line inside a function says what it does. Tools
and teammates read it with `help(double)`:

```python
def double(n):
    \"\"\"Return n times two.\"\"\"
    return n * 2
```

**4 · Scope: a function has its own private names.** Variables created inside it vanish
when it returns. If a function *assigns* to a name, Python treats that name as local to it,
so this crashes with `UnboundLocalError`:

```python
hits = 0
def score():
    hits += 1       # local hits, read before it has a value
```

The fix isn't to reach outside. Keep the count inside and `return` it.

**5 · Functions call functions.** Once `double` exists, any other function can use it. Build
big rites out of small, tested ones.

**6 · `sorted(items, key=...)`** returns a NEW sorted list (`.sort()` changes the original).
`key` is a function that turns each item into the thing to sort by. A `lambda` is a tiny
unnamed function. A tuple key sorts by the first part, then breaks ties with the next;
a minus sign flips numbers to biggest-first:

```python
crew = [{"name": "ana", "age": 31}, {"name": "kade", "age": 27}, {"name": "bo", "age": 31}]
oldest = sorted(crew, key=lambda c: (-c["age"], c["name"]))
[c["name"] for c in oldest][:2]      # ['ana', 'bo']
```
""",
    starter='''
"""
==============================================================================
  LEVEL 09 // SUBROUTINES                             TARGET: PROCTOR.ice
==============================================================================
  The rites. PROCTOR.ice calls every function you write with inputs you've
  never seen, edge cases included. Match the names and parameters exactly.
"""


# -- OBJECTIVE 1 // THE FIRST RITE: RETURN WHAT YOU PROMISED ------------------
# Finish clean_id(raw): RETURN the id with spaces stripped from both ends and
# in UPPERCASE.        clean_id("  sig-0412 \\n")  ->  "SIG-0412"
# (A rite that prints instead of returning gives back None.)
def clean_id(raw):
    pass


# -- OBJECTIVE 2 // DEFAULTS AND KEYWORDS -------------------------------------
# Write clamp(value, low=0, high=100): return value, but never below low and
# never above high.
#   clamp(150) -> 100      clamp(-5) -> 0      clamp(42) -> 42
#   clamp(150, high=120) -> 120          clamp(3, low=5, high=10) -> 5
#                     example:  def greet(name, greeting="hi"):



# -- OBJECTIVE 3 // A RITE MAY CALL A RITE ------------------------------------
# Write normalize(value, low, high): squeeze value into the range 0.0 to 1.0.
#   1. clamp value into low..high by calling YOUR clamp()
#   2. return (clamped - low) / (high - low)
# If high == low there is no range at all: return 0.0 instead of dividing.
#   normalize(50, 0, 200) -> 0.25        normalize(250, 0, 200) -> 1.0



# -- OBJECTIVE 4 // CORRUPTED CODE: LEAVE THE WORLD AS YOU FOUND IT -----------
# count_red(levels) should return how many entries in `levels` are exactly
# "RED". Calling it crashes: count_red(["RED", "GREEN"]). Read the error.
# Fix it the Order's way: the rite keeps its OWN count and returns it.
# (Don't reach for `global`: the Proctor calls your rite more than once.)
red_total = 0


def count_red(levels):
    for level in levels:
        if level == "RED":
            red_total += 1
    return red_total


# -- OBJECTIVE 5 // ORDER OF STANDING -----------------------------------------
# Write rank(records, top=3). `records` is a list of dicts like
#   {"id": "SIG-1", "strength": 80}
# Return a list of the ids of the `top` strongest records, strongest first.
# Ties: alphabetical by id. Don't change the list you were given.
#   example:  sorted(crew, key=lambda c: (-c["age"], c["name"]))



# -- OBJECTIVE 6 // NAME IT ---------------------------------------------------
# Every rite needs words: give clean_id, clamp, normalize, count_red and rank
# each a docstring: a """triple-quoted string""" as the first line inside the def.


# -- OBJECTIVE 7 // THE GRID CENSUS -------------------------------------------
# Raw signals the Order intercepted. The ids are messy and two strengths
# overflowed the sensor. Build `cleaned`: a NEW list with one dict per record,
#   {"id": <clean_id of the id>, "strength": <clamp of the strength>}
# using your rites (a loop with append, or a comprehension).
CENSUS = [
    {"id": "  sig-0412 ", "strength": 88},
    {"id": "vx-0007", "strength": 140},
    {"id": " SIG-0099\\n", "strength": -5},
    {"id": "grid-3", "strength": 88},
    {"id": "Sig-0150", "strength": 61},
]



# -- OBJECTIVE 8 // THE WATCHLIST ---------------------------------------------
# Create `watchlist` by calling rank on `cleaned` with top=2 (as a keyword).
# Then print exactly:   WATCHLIST | VX-0007, GRID-3
#             example:  names = ", ".join(crew)

''',
    dialogue={
        "intro": [
            {"speaker": "cipher", "mood": "warm",
             "text": "The Scriptorium. Every function in here has outlived the engineer who wrote it. That's the point."},
            {"speaker": "nova", "mood": "smirk",
             "text": "Proctor's harsh but fair. Nobody's passed first try since the blackout. No pressure, {callsign}."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Name it. Take only what you're given. Return what you promised. Leave the world as you found it."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "UnboundLocalError: the rite assigns to a name it doesn't own. Give it its own count and return it."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "A def line ends with a colon, and its body is indented under it. The Proctor can't call a broken rite."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "Scriptorium's very quiet when someone crashes in it. Everyone pretends not to look. Read the log."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "If a layer says 'returned None', your function printed or forgot to return. The Proctor only hears return."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The Proctor calls with the edges: empty lists, equal limits, ties. Ask yourself what your rite does there."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "That's a partial pass. Fix the red layer and resubmit. The Proctor doesn't hold grudges. Mostly."}],
        ],
        "victory": [
            {"speaker": "cipher", "mood": "warm",
             "text": "PROCTOR.ice has closed its examination. Your rites are in the codex, {callsign}. Signed with your callsign."},
            {"speaker": "nova", "mood": "alarm",
             "text": "Ops alert. The ARBITER just posted its docket. It judges the Grid at dawn. Every signal it calls hostile gets deleted."},
            {"speaker": "cipher", "mood": "cold",
             "text": "Your watchlist and its docket overlap. It's judging people. We're going to argue with a judge."},
        ],
    },
)


# ── helpers ──────────────────────────────────────────────────────────────────────

def _function(ctx, name: str):
    if name not in ctx.ns:
        if ctx.crashed and _def(ctx, name):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.",
                   hint=f"Write it at the left edge:  def {name}(...):  with its body indented underneath.")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return fn


def _not_none(ctx, name: str, *args, **kwargs):
    """Catch the classic print-instead-of-return before comparing values."""
    fn = _function(ctx, name)
    try:
        got = fn(*copy.deepcopy(args), **copy.deepcopy(kwargs))
    except Exception:  # noqa: BLE001 — compare_cases reports the crash with the exact input
        return
    if got is None:
        shown = ", ".join([repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()])
        raise Fail(f"`{name}({shown})` returned None, so the Proctor got nothing back.",
                   hint="Use `return` to hand the value back. print() only shows text on the screen; "
                        "a function that ends without return gives None.")


def _def(ctx, name: str):
    found = [n for n in ctx.tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return found[-1] if found else None


def _calls(node: ast.AST, name: str) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name for n in ast.walk(node))


def _calls_outside_defs(ctx, name: str) -> bool:
    return any(_calls(stmt, name) for stmt in ctx.tree.body if not isinstance(stmt, ast.FunctionDef))


# ── firewall layers ──────────────────────────────────────────────────────────────

@MISSION.check("First rite — `clean_id` returns")
def _clean_check(ctx):
    _not_none(ctx, "clean_id", "  sig-0412 \n")
    compare_cases(ctx, "clean_id", [("  sig-0412 \n",), ("vx-0007",), ("VX-0007",), ("\tgrid-3   ",),
                                    ("",), ("   ",), ("  a b  ",)], _clean_id,
                  hint="Chain the string methods from SIGNAL NOISE: strip the ends, then make it uppercase. "
                       "Inner spaces stay.")


@MISSION.check("Boundaries — `clamp` with defaults & keywords")
def _clamp_check(ctx):
    _not_none(ctx, "clamp", 150)
    compare_cases(ctx, "clamp", [(42,)], _clamp)
    try:
        compare_cases(ctx, "clamp", [(150,), (-5,), (0,), (100,), (42.5,)], _clamp,
                      hint="With no low/high given, the defaults 0 and 100 apply: def clamp(value, low=0, high=100):")
    except Fail as fail:
        if "missing" in fail.message and "argument" in fail.message:
            raise Fail(fail.message, hint="Give low and high default values in the def line so clamp(150) works.")
        raise
    compare_cases(ctx, "clamp", [{"value": 150, "high": 120}, {"value": 3, "low": 5, "high": 10},
                                 {"value": 7.5, "low": 0, "high": 5}, {"value": -40, "low": -20, "high": 20},
                                 {"high": 50, "value": 49}], _clamp,
                  hint="The parameters must be named exactly value, low and high, so callers can pass them by name. "
                       "Too big: give back high. Too small: give back low.")


@MISSION.check("A rite calls a rite — `normalize`")
def _normalize_check(ctx):
    node = _def(ctx, "normalize")
    _function(ctx, "normalize")
    if node is not None and not _calls(node, "clamp"):
        raise Fail("normalize() doesn't call your clamp(). The rite says: clamp first, then scale.",
                   hint="Inside normalize:  clamped = clamp(value, low, high)  then use `clamped` in the formula.")
    _not_none(ctx, "normalize", 50, 0, 200)
    cases = [(50, 0, 200), (250, 0, 200), (-3, 0, 10), (36.6, 35.0, 40.0), (0, -10, 10), (7, 5, 5), (5, 5, 5)]
    compare_cases(ctx, "normalize", cases, _normalize, approx=True,
                  hint="Clamp into low..high, subtract low, divide by the width (high - low). "
                       "When high == low, return 0.0 before you divide.")


@MISSION.check("Repair the scope breach — `count_red`")
def _count_check(ctx):
    fn = _function(ctx, "count_red")
    node = _def(ctx, "count_red")
    if node is not None and any(isinstance(n, (ast.Global, ast.Nonlocal)) for n in ast.walk(node)):
        raise Fail("count_red() reaches outside itself with `global`. It works once, then remembers old counts.",
                   hint="Start the count at 0 INSIDE the function, add to it in the loop, and return it.")
    try:
        first = fn(["RED", "GREEN"])
    except UnboundLocalError as exc:
        raise Fail(f"count_red still crashes: UnboundLocalError: {exc}",
                   hint="The function assigns to red_total, so Python treats it as the function's own (local) name, "
                        "and it has no value yet. Create the count inside the function before the loop.")
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"count_red(['RED', 'GREEN']) raised {type(exc).__name__}: {exc}")
    if first is None:
        raise Fail("count_red returned None.", hint="return the count at the end, after the loop (not inside it).")
    levels = ["RED", "GREEN", "RED", "AMBER", "RED"]
    again = [fn(list(levels)), fn(list(levels))]
    if again[0] != again[1]:
        raise Fail(f"Called twice on the same list, count_red returned {again[0]!r} then {again[1]!r}. "
                   "A rite must give the same answer every time.",
                   hint="Something outside the function is keeping the count between calls. Keep it inside.")
    compare_cases(ctx, "count_red", [(levels,), ([],), (["GREEN", "AMBER"],), (["red", "RED ", "Red"],),
                                     (["RED"] * 6,)], _count_red,
                  hint="Count only entries exactly equal to \"RED\". An empty list has 0. "
                       "Is the return inside the loop? Then it stops after the first item.")


_RANK_CASES = [
    [{"id": "SIG-1", "strength": 80}, {"id": "SIG-2", "strength": 95}, {"id": "SIG-3", "strength": 12},
     {"id": "SIG-4", "strength": 60}],
    [{"id": "B", "strength": 50}, {"id": "A", "strength": 50}, {"id": "C", "strength": 70}],
    [{"id": "ONLY", "strength": 3}],
    [],
]


@MISSION.check("Order of standing — `rank` with sorted(key=lambda)")
def _rank_check(ctx):
    fn = _function(ctx, "rank")
    _not_none(ctx, "rank", copy.deepcopy(_RANK_CASES[0]))
    records = copy.deepcopy(_RANK_CASES[0])
    try:
        fn(records)
    except Exception:  # noqa: BLE001 — reported below with the exact input
        pass
    if records != _RANK_CASES[0]:
        raise Fail("rank() changed the list it was given. The Proctor's records came back reordered.",
                   hint="sorted(records, key=...) returns a NEW list. records.sort() rearranges the original.")
    cases = [(c,) for c in _RANK_CASES] + [{"records": _RANK_CASES[0], "top": 1},
                                           {"records": _RANK_CASES[1], "top": 3},
                                           {"records": _RANK_CASES[0], "top": 10}]
    compare_cases(ctx, "rank", cases, _rank,
                  hint="Sort with key=lambda r: (-r[\"strength\"], r[\"id\"]) so the strongest come first and ties go "
                       "alphabetical. Return just the ids, then slice the first `top`.")


@MISSION.check("Name it — every rite has a docstring")
def _docstrings(ctx):
    for name in RITES:
        fn = _function(ctx, name)
        doc = getattr(fn, "__doc__", None)
        if not (isinstance(doc, str) and doc.strip()):
            raise Fail(f"`{name}` has no docstring. A rite without words isn't a rite.",
                       hint='Make the FIRST line inside the def a string:  """What this function returns."""')


@MISSION.check("Preprocess the census — `cleaned`")
def _cleaned_check(ctx):
    value = ctx.get("cleaned")
    if ctx.get("CENSUS") != CENSUS:
        raise Fail("The CENSUS data was edited. Raw intercepts are evidence: clean a copy, not the original.",
                   hint="Restore CENSUS from the starter and build `cleaned` as a new list.")
    for rite in ("clean_id", "clamp"):
        if not _calls_outside_defs(ctx, rite):
            raise Fail(f"`cleaned` isn't built with your {rite}() rite. Typed-in values don't count as preprocessing.",
                       hint="For each record r in CENSUS: a dict with clean_id(r[\"id\"]) and clamp(r[\"strength\"]).")
    expected = _cleaned()
    if not isinstance(value, list) or len(value) != len(expected):
        raise Fail(f"`cleaned` should be a list of {len(expected)} dicts, one per CENSUS record.",
                   hint="Start with an empty list and append one new dict for each record, or use a comprehension.")
    for i, (got, want) in enumerate(zip(value, expected)):
        if got != want:
            raise Fail(f"cleaned[{i}] is {got!r}, expected {want!r} (from CENSUS[{i}] = {CENSUS[i]!r}).",
                       hint="Each dict has exactly two keys, \"id\" and \"strength\": the cleaned id and the "
                            "clamped strength (default limits 0..100).")


@MISSION.check("Post the watchlist")
def _watchlist(ctx):
    value = ctx.get("watchlist")
    calls = [n for v in ctx.assignments("watchlist") for n in ast.walk(v)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "rank"]
    if not calls:
        raise Fail("`watchlist` must come from calling your rank() rite.", hint="watchlist = rank(cleaned, ...)")
    if not any(any(k.arg == "top" for k in c.keywords) for c in calls):
        raise Fail("Pass the size as a keyword argument: top=2.", hint="Keyword arguments name the parameter: f(x, top=2)")
    if value != ["VX-0007", "GRID-3"]:
        raise Fail(f"`watchlist` is {value!r}, expected ['VX-0007', 'GRID-3'].",
                   hint="Rank the CLEANED records (clamped strengths, clean ids). GRID-3 and SIG-0412 tie at 88: "
                        "alphabetical breaks it.")
    typed = [n.value for n in ast.walk(ctx.tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
             and ("VX-0007" in n.value or "GRID-3" in n.value)]
    if typed:
        raise Fail(f"The ids are typed into your code ({typed[0]!r}). Print them from `watchlist` instead.",
                   hint="Join the list into one string with \", \".join(...), then put that in the f-string.")
    line = "WATCHLIST | VX-0007, GRID-3"
    if line not in ctx.stdout.splitlines():
        got = ctx.stdout.strip().splitlines()
        raise Fail(f"The Proctor expected the line {line!r}" + (f" but you printed {got[-1]!r}." if got else ", and nothing was printed."),
                   hint='Join the ids with ", ".join(watchlist), then print it inside the f-string.')
