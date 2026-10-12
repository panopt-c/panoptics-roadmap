"""LAB PY03 // ORDER OF RANKS — sorted(key=...) with tuples, argsort, zip and enumerate."""
from __future__ import annotations

import ast
import copy
import random

from engine.mission import Fail, Mission

MISSION = Mission(
    id="PY03",
    slug="py03_order_of_ranks",
    title="ORDER OF RANKS",
    concept="Sorting with keys, zip & enumerate",
    enemy="RANKFALL.daemon",
    xp=120,
    par_seconds=25 * 60,
    tier=2,
    concepts=("sorting", "tuples-sets", "loops"),
    requires=(),
    timeout=10,
    run_as_main=False,
    enemy_art="""\
   ▄▄       ▄▄
  █▓▓█ ▄▄  █▓▓█
  █▓▓█ ██ ▄█▓▓█▄
 ▄█▓▓█▄██▄██▓▓██
 ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
  3   1  ?  2""",
    briefing="""\
The Arena board in the cooling chamber flickers. **RANKFALL.daemon** has been shuffling it: ties
broken at random, sorted lists that come back empty, names paired with someone else's score. VEX is
furious. Ada is not.

"Sorting is a decision about what matters first," she says. "The machine can't make it for you. Say
it in a key, or the machine will decide by accident."

Ada wants the ranking rites written so that the same data gives the same order, every time, on any
machine. Reproducibility starts here.

**Rebuild the rankings with `sorted(key=...)`, `zip` and `enumerate`, and break every tie on purpose.**
""",
    why="""\
Ranking is everywhere in ML. **Top-k predictions** are an argsort of scores. **Retrieval** in a RAG
system sorts documents by similarity. A **leaderboard** sorts models by metric, and a tie broken
differently on two machines makes two reports disagree.

```python
top5 = sorted(range(len(probs)), key=lambda i: -probs[i])[:5]   # np.argsort(-probs)[:5]
for epoch, (x, y) in enumerate(zip(X, y_true), start=1): ...
cols = [list(c) for c in zip(*rows)]                            # rows -> feature columns
```

`zip` silently stops at the shorter input. If `X` has 1000 rows and `y` has 999, a plain `zip` trains
on misaligned pairs without a word. `zip(..., strict=True)` turns that into an error you can see.
""",
    manual="""\
**1. `sorted(items, key=f)` sorts by whatever `f` returns.** It returns a NEW list:

```python
people = [("Ines", 34), ("Tomo", 15), ("Ren", 34)]
sorted(people, key=lambda p: p[1])              # by age: Tomo, Ines, Ren
sorted(people, key=lambda p: p[1], reverse=True)  # oldest first: Ines, Ren, Tomo
```

Python's sort is **stable**: items with equal keys keep their original order (Ines before Ren).

**2. A tuple key sorts by several things.** Tuples compare left to right, so the second item only
matters on a tie in the first. Negate a number to flip *just that part*:

```python
sorted(people, key=lambda p: (-p[1], p[0]))     # age high->low, then name A->Z
# [('Ines', 34), ('Ren', 34), ('Tomo', 15)]
```

`reverse=True` flips EVERY part of the key, names included. Negation flips one.

**3. Argsort: sort the positions, not the values.**

```python
scores = [0.2, 0.9, 0.5]
sorted(range(len(scores)), key=lambda i: scores[i])   # [0, 2, 1]
```

**4. `enumerate` counts for you; `zip` walks lists side by side.**

```python
for rank, name in enumerate(["Vex", "Ines"], start=1):
    print(rank, name)                       # 1 Vex / 2 Ines
list(zip([1, 2, 3], "abc"))                 # [(1, 'a'), (2, 'b'), (3, 'c')]
list(zip([1, 2, 3], "ab", strict=True))     # ValueError: lengths differ (Python 3.10+)
[list(col) for col in zip(*[[1, 2], [3, 4], [5, 6]])]   # [[1, 3, 5], [2, 4, 6]]
```

**5. The common mistake: `.sort()` returns `None`.**

```python
ranked = people.sort(key=lambda p: p[1])    # ranked is None, and people itself got reordered
ranked = sorted(people, key=lambda p: p[1]) # a new sorted list; people is untouched
```

**The library version:** `np.argsort(scores)[::-1][:k]` for top-k, `torch.topk(logits, k)` on GPU,
`df.sort_values(["sector", "age"], ascending=[True, False])` in pandas. They all need the same
decision: what matters first, and how do ties break?
""",
    starter='''
"""
==============================================================================
  LAB PY03 // ORDER OF RANKS                      TARGET: RANKFALL.daemon
==============================================================================
  The grader calls every function with FRESH data. Return new lists; never
  reorder the list you were given. Save, then HACK.
"""

ARENA = {"Vex": 940, "Ines": 870, "Kael": 940, "Tomo": 610}

CREW = [
    {"name": "Ines", "age": 34, "sector": "grid"},
    {"name": "Okoye", "age": 61, "sector": "archive"},
    {"name": "Ren", "age": 34, "sector": "grid"},
    {"name": "Tomo", "age": 15, "sector": "grid"},
]


# -- OBJECTIVE 1 -------------------------------------------------------------
# leaderboard(scores) -> list of names, highest score first.
# Ties: alphabetical by name.
#   leaderboard(ARENA)  ->  ['Kael', 'Vex', 'Ines', 'Tomo']
#   example:  sorted(items, key=lambda kv: (-kv[1], kv[0]))
def leaderboard(scores):
    pass  # TODO


# -- OBJECTIVE 2 -------------------------------------------------------------
# rank_records(records) -> NEW list sorted by sector A->Z, then age
# OLDEST first, then name A->Z.
#   rank_records(CREW)  ->  records of Okoye, Ines, Ren, Tomo
def rank_records(records):
    pass  # TODO


# -- OBJECTIVE 3 -------------------------------------------------------------
# argsort(values) -> the list of INDICES that would sort values ascending.
# Equal values keep their original index order.
#   argsort([0.2, 0.9, 0.5])  ->  [0, 2, 1]
def argsort(values):
    pass  # TODO


# -- OBJECTIVE 4 -------------------------------------------------------------
# paired(features, labels) -> list of (feature, label) tuples, in order.
# If the two lists have different lengths, raise ValueError.
# (a plain zip would quietly drop the extras: a silent data bug)
#   paired([1.5, 2.0], ["ok", "bad"])  ->  [(1.5, 'ok'), (2.0, 'bad')]
def paired(features, labels):
    pass  # TODO


# -- OBJECTIVE 5 -------------------------------------------------------------
# ranked(scores) -> [(rank, name, score), ...] in leaderboard order,
# rank counting from 1.
#   ranked(ARENA)  ->  [(1, 'Kael', 940), (2, 'Vex', 940), (3, 'Ines', 870), (4, 'Tomo', 610)]
def ranked(scores):
    pass  # TODO


# -- OBJECTIVE 6 -------------------------------------------------------------
# columns(rows) -> list of column lists (rows -> columns).
#   columns([[1, 2, 3], [4, 5, 6]])  ->  [[1, 4], [2, 5], [3, 6]]
#   columns([])                      ->  []
def columns(rows):
    pass  # TODO


# -- OBJECTIVE 7 // CORRUPTED CODE -------------------------------------------
# youngest_first(records) should return a NEW list of the records,
# youngest first, and leave the caller's list in its original order.
# RANKFALL got to it. Hack once and see what it returns.
def youngest_first(records):
    return records.sort(key=lambda r: r["age"])
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Two engineers tie on the Arena board. Who ranks first? Don't guess. Tell me the rule."},
            {"speaker": "vex", "mood": "smirk",
             "text": "The rule is me. Ranked first since before you had a callsign. RANKFALL keeps putting Kael above me."},
            {"speaker": "ada", "mood": "smirk",
             "text": "Then the rule is alphabetical, Vex, and Kael has a K. Write it down, {callsign}. In a key."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "TypeError comparing None and int? Something in your key returned None. Read the key function slowly."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "IndexError inside a lambda: your key reached for a position the item doesn't have."}],
            [{"speaker": "vex", "mood": "smirk",
              "text": "Crashed on a sort. Bold. Most people at least get the list back."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "If ties came out backwards, ask what reverse=True flipped. All of the key, not just the score."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Got None back? That's .sort(). It sorts in place and returns nothing. sorted() returns a list."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "zip stops at the shorter list without telling you. That silence costs weeks. Make it loud."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Same data, same order, on any machine. That's the whole of reproducibility, in one key."},
            {"speaker": "vex", "mood": "cold",
             "text": "Second on a tiebreak. Alphabetical. Fine. I'll just score higher. Watch the board, {callsign}."},
            {"speaker": "ada", "mood": "neutral",
             "text": "The old world ranked people by scores it never explained. A key you can read is a key you can argue with."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

NAMES = ("Ines", "Tomo", "Okoye", "Ren", "Mira", "Kael", "Sora", "Bex", "Juno", "Ash", "Pell",
         "Vik", "Ola", "Dov", "Yara", "Tam", "Vex", "Lio", "Quill", "Nadia")
SECTORS = ("foundry", "grid", "archive", "dead-zone", "undercroft")


def _short(value, limit: int = 140) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _func(ctx, name: str):
    if name not in ctx.ns:
        if ctx.crashed and any(isinstance(n, ast.FunctionDef) and n.name == name for n in ctx.tree.body):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.", hint=f"Keep the starter's  def {name}(...):  line.")
    if not callable(ctx.ns[name]):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return ctx.ns[name]


def _call(ctx, name: str, *args, allow_none: bool = False):
    fn = _func(ctx, name)
    shown = ", ".join(_short(a, 90) for a in args)
    try:
        result = fn(*copy.deepcopy(args))
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        hint = "Call it yourself on this input and read the error."
        if isinstance(exc, TypeError) and "NoneType" in str(exc):
            hint = "Something returned None. .sort() returns None; sorted() returns the new list."
        raise Fail(f"`{name}({shown})` crashed: {type(exc).__name__}: {exc}", hint=hint)
    if result is None and not allow_none:
        hint = "Finish the TODO: the function needs a return."
        node = next((n for n in ctx.tree.body if isinstance(n, ast.FunctionDef) and n.name == name), None)
        if node is not None and any(isinstance(n, ast.Attribute) and n.attr == "sort" for n in ast.walk(node)):
            hint = "list.sort() sorts in place and returns None. Return sorted(...) instead, which builds a new list."
        raise Fail(f"`{name}({shown})` returned None.", hint=hint)
    return result, shown


def _scores(rng: random.Random, n: int) -> dict:
    names = rng.sample(NAMES, n)
    pool = [rng.randint(5, 30) * 10 for _ in range(max(2, n // 2))]   # few distinct values -> real ties
    return {name: rng.choice(pool) for name in names}


def _ref_board(scores: dict) -> list:
    return [name for name, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def _crew(rng: random.Random, n: int) -> list:
    ages = [rng.randint(16, 70) for _ in range(3)]
    return [{"name": name, "age": rng.choice(ages), "sector": rng.choice(SECTORS[:3])}
            for name in rng.sample(NAMES, n)]


def _same(name: str, shown: str, got, expected, hint: str) -> None:
    if got != expected or type(got) is not type(expected):
        raise Fail(f"`{name}({shown})` returned {_short(got)}, expected {_short(expected)}.", hint=hint)


def _untouched(ctx, name: str, original: list) -> None:
    snapshot = copy.deepcopy(original)
    try:
        _func(ctx, name)(original)
    except Exception:  # noqa: BLE001 — reported by the comparison above
        return
    if original != snapshot:
        raise Fail(f"`{name}` reordered the caller's list. It must build and return a NEW list.",
                   hint="records.sort(...) changes `records` itself. sorted(records, key=...) leaves it alone.")


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Leaderboard — highest first, ties alphabetical")
def _leaderboard(ctx):
    rng = random.Random("PY03:board")
    cases = (_scores(rng, 9), {"Vex": 940, "Ines": 870, "Kael": 940, "Tomo": 610}, _scores(rng, 12),
             {"Zed": 5, "Amy": 5, "Mo": 5}, {"Solo": 1}, {})
    for scores in cases:
        got, shown = _call(ctx, "leaderboard", scores)
        expected = _ref_board(scores)
        hint = "Sort the (name, score) pairs with key=lambda kv: (-kv[1], kv[0]) and keep the names."
        backwards = [n for n, _ in sorted(scores.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)]
        if got == backwards and got != expected:
            hint = ("reverse=True flipped the WHOLE key, so tied names came out Z->A. Negate only the score: "
                    "key=lambda kv: (-kv[1], kv[0]).")
        elif isinstance(got, list) and got and isinstance(got[0], tuple):
            hint = "Return just the names, in order: a list of strings."
        _same("leaderboard", shown, got, expected, hint)


@MISSION.check("Chain of command — `rank_records` sorts by three keys")
def _rank_records(ctx):
    rng = random.Random("PY03:records")
    for records in (_crew(rng, 10), _crew(rng, 7), []):
        got, shown = _call(ctx, "rank_records", records)
        expected = sorted(records, key=lambda r: (r["sector"], -r["age"], r["name"]))
        hint = "One tuple key: (sector, -age, name). The minus flips only the age."
        if isinstance(got, list) and len(got) == len(expected) and got != expected:
            if [r["sector"] for r in got] == [r["sector"] for r in expected]:
                if [r["age"] for r in got] == [r["age"] for r in expected]:
                    hint = "Sectors and ages are right; equal ages must be broken by name A->Z (third key)."
                else:
                    hint = "Sectors are right; inside a sector the OLDEST comes first. Negate the age in the key."
        _same("rank_records", "<records>", got, expected, hint)
    _untouched(ctx, "rank_records", _crew(rng, 8))


@MISSION.check("Argsort — indices that would sort the values")
def _argsort(ctx):
    rng = random.Random("PY03:argsort")
    cases = ([round(rng.random(), 2) for _ in range(9)], [rng.randint(0, 4) for _ in range(11)],
             [0.2, 0.9, 0.5], [7], [])
    for values in cases:
        got, shown = _call(ctx, "argsort", values)
        expected = sorted(range(len(values)), key=lambda i: values[i])
        hint = "Sort the positions:  sorted(range(len(values)), key=lambda i: values[i])"
        if isinstance(got, list) and got == sorted(values) and got != expected:
            hint = "Those are the sorted VALUES. argsort returns their positions (indices) in the original list."
        elif isinstance(got, list) and sorted(got) == expected and got != expected:
            hint = "Equal values must keep their original index order. Python's sort is stable; don't reverse it."
        _same("argsort", shown, got, expected, hint)


@MISSION.check("Aligned pairs — `paired` zips, and refuses ragged lists")
def _paired(ctx):
    rng = random.Random("PY03:paired")
    xs = [round(rng.uniform(0, 9), 1) for _ in range(6)]
    ys = [rng.choice(("ok", "bad")) for _ in range(6)]
    for f, l in ((xs, ys), ([1.5], ["ok"]), ([], [])):
        got, shown = _call(ctx, "paired", f, l)
        _same("paired", shown, got, list(zip(f, l)),
              hint="A list of (feature, label) tuples:  list(zip(features, labels))")
    fn = _func(ctx, "paired")
    for f, l in ((xs, ys[:-1]), (xs[:3], ys)):
        try:
            got = fn(list(f), list(l))
        except ValueError:
            continue
        except Exception as exc:  # noqa: BLE001
            raise Fail(f"`paired` on lists of length {len(f)} and {len(l)} raised {type(exc).__name__}: {exc}; "
                       "it should raise ValueError.", hint="zip(features, labels, strict=True) raises ValueError.")
        raise Fail(f"`paired` on lists of length {len(f)} and {len(l)} returned {_short(got, 80)} instead of "
                   "raising ValueError. A label just went missing without a sound.",
                   hint="Use zip(..., strict=True), or compare len() first and  raise ValueError(...).")


@MISSION.check("Podium — `ranked` numbers places from 1 with enumerate")
def _ranked(ctx):
    rng = random.Random("PY03:ranked")
    for scores in (_scores(rng, 8), {"Vex": 940, "Ines": 870, "Kael": 940}, {}):
        got, shown = _call(ctx, "ranked", scores)
        board = _ref_board(scores)
        expected = [(i, name, scores[name]) for i, name in enumerate(board, start=1)]
        hint = "enumerate(<the leaderboard>, start=1), building (rank, name, score) tuples."
        if isinstance(got, list) and got and isinstance(got[0], tuple) and got[0][0] == 0:
            hint = "Ranks start at 1, not 0:  enumerate(..., start=1)"
        elif isinstance(got, list) and got and isinstance(got[0], list):
            hint = "Each entry should be a tuple (rank, name, score), in round brackets."
        _same("ranked", shown, got, expected, hint)


@MISSION.check("Transpose — `columns` turns rows into feature columns")
def _columns(ctx):
    rng = random.Random("PY03:columns")
    width = rng.randint(3, 5)
    cases = ([[rng.randint(0, 9) for _ in range(width)] for _ in range(4)], [[1, 2, 3], [4, 5, 6]],
             [["a", 1]], [])
    for rows in cases:
        got, shown = _call(ctx, "columns", rows)
        expected = [list(col) for col in zip(*rows)]
        hint = "zip(*rows) walks the rows side by side; wrap each column in list()."
        if isinstance(got, list) and got and isinstance(got[0], tuple):
            hint = "zip gives tuples. Turn each column into a list:  [list(c) for c in zip(*rows)]"
        _same("columns", shown, got, expected, hint)


@MISSION.check("Purge the daemon — corrupted `youngest_first` repaired")
def _youngest(ctx):
    rng = random.Random("PY03:youngest")
    records = [{"name": n, "age": rng.randint(10, 80)} for n in rng.sample(NAMES, 6)]
    got, shown = _call(ctx, "youngest_first", records)
    _same("youngest_first", "<records>", got, sorted(records, key=lambda r: r["age"]),
          hint="sorted(records, key=lambda r: r['age']) returns the new list.")
    _untouched(ctx, "youngest_first", [{"name": n, "age": rng.randint(10, 80)} for n in rng.sample(NAMES, 6)])
