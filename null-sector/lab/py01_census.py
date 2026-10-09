"""LAB PY01 // THE CENSUS — list, dict and set comprehensions over records."""
from __future__ import annotations

import ast
import copy
import random

from engine.mission import Fail, Mission

MISSION = Mission(
    id="PY01",
    slug="py01_census",
    title="THE CENSUS",
    concept="Comprehensions for data",
    enemy="HEADCOUNT.ghost",
    xp=120,
    par_seconds=25 * 60,
    tier=2,
    concepts=("comprehensions", "lists", "dicts", "tuples-sets"),
    requires=(),
    timeout=10,
    run_as_main=False,
    enemy_art="""\
   ▄▄▄▄▄▄▄▄▄▄
  █ ▀▄  ▄▀ ▄ █
  █  ▓▓  ▓▓  █
  █ ▄▄▄▄▄▄▄▄ █
  █▀ 1 2 ? 4 ▀█
  ▀▄▀▄▀▄▀▄▀▄▀▄▀""",
    briefing="""\
The Scriptorium Lab smells of solder and old paper. **MOTHER ADA** sits among the ashes of the
Order's library: the canon on learning machines, burned in the Null Event. She is rewriting it
from memory, one rite at a time.

"The old world taught machines before it looked at what it fed them," she says. "We start
where they didn't. We count."

The Monastery's census is a list of records, and **HEADCOUNT.ghost** is gnawing at it:
names drift, ages vanish, whole sectors go missing from the totals. Ada wants each question
answered in one clean line of Python.

**Write the census functions as comprehensions, and make the headcount true again.**
""",
    why="""\
A dataset, before any library touches it, is usually a **list of records**: one dict per
sample. Turning those records into what a model eats is a comprehension:

```python
X = [[r["age"], r["hours"]] for r in rows]          # feature matrix
y = [r["label"] for r in rows]                       # targets
train = [r for r in rows if r["split"] == "train"]   # filtering samples
vocab = {w for r in rows for w in r["text"].split()} # a vocabulary
```

You'll write exactly these lines in data loaders, in a PyTorch `Dataset.__init__`, and when
cleaning a Hugging Face dataset with `.filter(...)` and `.map(...)`. Comprehensions are fast,
they say *what* you want instead of *how* to loop, and they make a new list instead of
quietly changing the old one, which matters once a bug in your data costs a week of GPU time.
""",
    manual="""\
**1. A list comprehension builds a new list from an old one.** Read it right to left:
"for each `r` in `rows`, give me `r["name"]`".

```python
rows = [{"name": "Ines", "age": 34}, {"name": "Tomo", "age": 15}]
[r["name"] for r in rows]            # ['Ines', 'Tomo']
[r["age"] * 12 for r in rows]        # [408, 180]   any expression works
```

**2. Add `if` at the end to filter.** Only items where the condition is true get in:

```python
[r for r in rows if r["age"] >= 18]  # [{'name': 'Ines', 'age': 34}]
```

(An `if/else` that *changes* values goes at the front instead:
`["adult" if r["age"] >= 18 else "minor" for r in rows]`.)

**3. Dict and set comprehensions** use curly braces. A dict needs `key: value`:

```python
{r["name"]: r["age"] for r in rows}  # {'Ines': 34, 'Tomo': 15}
{r["age"] // 10 for r in rows}       # {1, 3}  a set: unique values, no order
```

Careful: `{}` on its own is an empty **dict**. An empty set is `set()`.

**4. Nested comprehensions flatten.** The `for` clauses go in the same order you'd write
the loops:

```python
crews = [{"tools": ["saw", "torch"]}, {"tools": ["torch"]}]
{t for c in crews for t in c["tools"]}       # {'saw', 'torch'}
# same as:  for c in crews:
#               for t in c["tools"]: ...
[[r[k] for k in ("name", "age")] for r in rows]   # a list of rows: [['Ines', 34], ['Tomo', 15]]
```

**5. The common mistake: forgetting the call parentheses.**

```python
[r["name"].lower for r in rows]      # [<built-in method lower ...>, ...]  NOT names
[r["name"].lower() for r in rows]    # ['ines', 'tomo']
```

Without `()` you collect the *method itself*, not its result. No crash, just wrong data,
the most dangerous kind.

**The library version.** In pandas these are one-liners too: `df["name"].tolist()`,
`df[df["age"] >= 18]`, `df[["age", "hours"]].to_numpy()`. You'll use those in the ARCHIVE OF
NOISE track; comprehensions are what they do underneath, and what you reach for when there's
no DataFrame in sight.
""",
    starter='''
"""
==============================================================================
  LAB PY01 // THE CENSUS                           TARGET: HEADCOUNT.ghost
==============================================================================
  Every record in the census looks like this:
      {"name": "Ines", "age": 34, "sector": "foundry", "skills": ["welding", "python"]}

  Write each function as ONE comprehension. The grader calls your functions
  with FRESH census data, so they must work for any records, not just these.
  Save, then HACK.
"""

CENSUS = [
    {"name": "Ines", "age": 34, "sector": "foundry", "skills": ["welding", "python"]},
    {"name": "Tomo", "age": 15, "sector": "grid", "skills": ["running"]},
    {"name": "Okoye", "age": 61, "sector": "archive", "skills": ["python", "sql", "botany"]},
    {"name": "Ren", "age": 18, "sector": "grid", "skills": []},
]


# -- OBJECTIVE 1 -------------------------------------------------------------
# names_of(records) -> list of every name, in the same order.
#   names_of(CENSUS)  ->  ['Ines', 'Tomo', 'Okoye', 'Ren']
#   example:  [r["age"] for r in rows]
def names_of(records):
    pass  # TODO


# -- OBJECTIVE 2 -------------------------------------------------------------
# adults(records, min_age=18) -> the records whose age is AT LEAST min_age.
#   adults(CENSUS)              ->  the records for Ines, Okoye and Ren
#   adults(CENSUS, min_age=40)  ->  just Okoye's record
#   example:  [r for r in rows if r["age"] > 99]
def adults(records, min_age=18):
    pass  # TODO


# -- OBJECTIVE 3 -------------------------------------------------------------
# name_to_age(records) -> a dict {name: age}.
#   name_to_age(CENSUS)  ->  {'Ines': 34, 'Tomo': 15, 'Okoye': 61, 'Ren': 18}
#   example:  {r["name"]: r["sector"] for r in rows}
def name_to_age(records):
    pass  # TODO


# -- OBJECTIVE 4 -------------------------------------------------------------
# sectors(records) -> the SET of sectors that appear (each one once).
#   sectors(CENSUS)  ->  {'foundry', 'grid', 'archive'}
#   sectors([])      ->  set()        (careful: {} is an empty DICT)
def sectors(records):
    pass  # TODO


# -- OBJECTIVE 5 -------------------------------------------------------------
# all_skills(records) -> the set of every skill anyone has.
#   all_skills(CENSUS)  ->  {'welding', 'python', 'running', 'sql', 'botany'}
#   example:  {t for c in crews for t in c["tools"]}
def all_skills(records):
    pass  # TODO


# -- OBJECTIVE 6 -------------------------------------------------------------
# feature_rows(records, keys) -> one inner list per record, holding the values
# of `keys` in that order. This is how a feature matrix X gets built.
#   feature_rows(CENSUS[:2], ["age", "name"])  ->  [[34, 'Ines'], [15, 'Tomo']]
def feature_rows(records, keys):
    pass  # TODO


# -- OBJECTIVE 7 // CORRUPTED CODE -------------------------------------------
# clean_names(records) should return every name stripped of surrounding
# whitespace and lowercased:   "  KAEL " -> "kael"
# HEADCOUNT.ghost got to it. It doesn't crash. It returns the wrong things.
# Hack once, read what it returned, and fix it.
def clean_names(records):
    return [r["name"].strip().lower for r in records]
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Sit. Before we teach any machine to learn, tell me: how many people live in this Monastery?"},
            {"speaker": "ada", "mood": "smirk",
             "text": "You don't know. Neither did the old world about its data. That is where the rot started, {callsign}."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "HEADCOUNT.ghost is rewriting the census as we speak. One comprehension per question. Short lines, no loose ends."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "A crash is a question the code asked you. Read the COMBAT LOG; it tells you which line asked it."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "NameError inside a nested comprehension usually means the for clauses are in the wrong order."}],
            [{"speaker": "ada", "mood": "smirk",
              "text": "KeyError means you asked a record for a key it doesn't have. Check the spelling against the record shape."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "The grader brings its own census. If your function only knows Ines and Tomo, it knows nothing."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "Read the failing input slowly. What did you return, and what would a careful clerk have written down?"}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Boundary check: 'at least 18' includes 18. Off-by-one errors live exactly at the edge."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "There. Every soul accounted for, in lines a tired engineer can read at 3 a.m. HEADCOUNT has nothing left to eat."},
            {"speaker": "ada", "mood": "neutral",
             "text": "First page of the canon, restored: know what is in front of you before you ask a machine to learn it."},
            {"speaker": "cipher", "mood": "smirk",
             "text": "Next she'll want to know how often things happen. Counting, {callsign}. Properly this time."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

NAMES = ("Ines", "Tomo", "Okoye", "Ren", "Mira", "Kael", "Sora", "Bex", "Juno", "Ash", "Pell",
         "Vik", "Ola", "Dov", "Yara", "Tam", "Lio", "Quill", "Nadia", "Eskil")
SECTORS = ("foundry", "grid", "archive", "dead-zone", "undercroft", "reactor")
SKILLS = ("welding", "python", "sql", "running", "botany", "radio", "medicine", "cooking",
          "soldering", "climbing", "statistics")


def _short(value, limit: int = 140) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _census(rng: random.Random, n: int) -> list[dict]:
    names = rng.sample(NAMES, n)
    return [{"name": name, "age": rng.randint(5, 80), "sector": rng.choice(SECTORS),
             "skills": rng.sample(SKILLS, rng.randint(0, 3))} for name in names]


def _func(ctx, name: str):
    if name not in ctx.ns:
        if ctx.crashed and _func_def(ctx, name):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.", hint=f"Keep the starter's  def {name}(...):  line.")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return fn


def _func_def(ctx, name: str):
    found = [n for n in ctx.tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return found[-1] if found else None


def _call(ctx, name: str, *args, **kwargs):
    """Call the player's function on deep copies; a crash becomes a failed layer showing the input."""
    fn = _func(ctx, name)
    shown = ", ".join([_short(a, 70) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()])
    try:
        result = fn(*copy.deepcopy(args), **copy.deepcopy(kwargs))
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        hint = "Call it yourself on this input and read the error."
        if isinstance(exc, KeyError):
            hint = "A record was asked for a key it doesn't have. Each record has: name, age, sector, skills."
        elif isinstance(exc, NameError):
            hint = ("In a nested comprehension, the for clauses go in loop order: "
                    "the outer `for r in records` comes first, the inner one second.")
        raise Fail(f"`{name}({shown})` crashed: {type(exc).__name__}: {exc}", hint=hint)
    if result is None:
        raise Fail(f"`{name}({shown})` returned None.",
                   hint="Finish the TODO: the function needs  return <your comprehension>.")
    return result, shown


def _expect(name: str, shown: str, got, expected, hint: str = "") -> None:
    if type(got) is not type(expected):
        raise Fail(f"`{name}({shown})` returned {type(got).__name__}; it should return a "
                   f"{type(expected).__name__}.", hint=hint)
    if got != expected:
        raise Fail(f"`{name}({shown})` returned {_short(got)}, expected {_short(expected)}.", hint=hint)


COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _uses_comprehension(ctx, name: str) -> None:
    node = _func_def(ctx, name)
    if node is not None and not any(isinstance(n, COMPREHENSIONS) for n in ast.walk(node)):
        raise Fail(f"`{name}` gives the right answer, but it's built with a loop, not a comprehension.",
                   hint="This rite is about comprehensions: write the whole result as one expression, "
                        "like  [expr for r in records if condition].")


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Roll call — `names_of` keeps every name in order")
def _names(ctx):
    rng = random.Random("PY01:names")
    for records in (_census(rng, 7), _census(rng, 1), []):
        got, shown = _call(ctx, "names_of", records)
        _expect("names_of", shown, got, [r["name"] for r in records],
                hint="One item per record, same order:  [r[\"name\"] for r in records]")
    _uses_comprehension(ctx, "names_of")


@MISSION.check("Of age — `adults` filters with `if`, edge included")
def _adults(ctx):
    rng = random.Random("PY01:adults")
    edge = [{"name": "Edge", "age": 18, "sector": "grid", "skills": []},
            {"name": "Kid", "age": 17, "sector": "grid", "skills": []}]
    mixed = [{"name": "Vet", "age": 52, "sector": "grid", "skills": []},
             {"name": "Mid", "age": 30, "sector": "grid", "skills": []},
             {"name": "Teen", "age": 13, "sector": "grid", "skills": []}]
    for records, kwargs in ((_census(rng, 9), {}), (edge, {}), (_census(rng, 8), {"min_age": 40}),
                            (mixed, {"min_age": 40}), (mixed, {"min_age": 13}), ([], {})):
        expected = [r for r in records if r["age"] >= kwargs.get("min_age", 18)]
        got, shown = _call(ctx, "adults", records, **kwargs)
        hint = "Keep whole records whose age is AT LEAST min_age: compare with >=, and use the min_age parameter."
        if isinstance(got, list) and got and not isinstance(got[0], dict):
            hint = "Return the records themselves (the dicts), not just names or ages."
        _expect("adults", shown, got, expected, hint=hint)
    original = _census(rng, 6)
    snapshot = copy.deepcopy(original)
    fn = _func(ctx, "adults")
    try:
        fn(original)
    except Exception:  # noqa: BLE001 — already reported above
        pass
    if original != snapshot:
        raise Fail("`adults` changed the census it was given. A filter must build a NEW list.",
                   hint="A comprehension never touches the original list; don't remove items from `records`.")
    _uses_comprehension(ctx, "adults")


@MISSION.check("Lookup table — `name_to_age` is a dict comprehension")
def _lookup(ctx):
    rng = random.Random("PY01:lookup")
    for records in (_census(rng, 8), []):
        got, shown = _call(ctx, "name_to_age", records)
        _expect("name_to_age", shown, got, {r["name"]: r["age"] for r in records},
                hint="Curly braces with key: value  ->  {r[\"name\"]: r[\"age\"] for r in records}")
    _uses_comprehension(ctx, "name_to_age")


@MISSION.check("Territory — `sectors` returns a set of unique sectors")
def _sectors(ctx):
    rng = random.Random("PY01:sectors")
    for records in (_census(rng, 12), _census(rng, 2), []):
        got, shown = _call(ctx, "sectors", records)
        hint = "A set comprehension uses curly braces with no colon:  {r[\"sector\"] for r in records}"
        if isinstance(got, dict) and not records:
            hint = "{} is an empty DICT. A set comprehension over no records already gives set()."
        _expect("sectors", shown, got, {r["sector"] for r in records}, hint=hint)
    _uses_comprehension(ctx, "sectors")


@MISSION.check("Skill registry — `all_skills` flattens nested lists")
def _skills(ctx):
    rng = random.Random("PY01:skills")
    loner = [{"name": "Solo", "age": 40, "sector": "grid", "skills": []}]
    for records in (_census(rng, 10), loner, []):
        got, shown = _call(ctx, "all_skills", records)
        hint = "Two for clauses, outer loop first:  {s for r in records for s in r[\"skills\"]}"
        if isinstance(got, (set, list)) and any(isinstance(s, list) for s in got):
            hint = "You collected whole skill LISTS. Add a second for clause to reach each skill inside them."
        _expect("all_skills", shown, got, {s for r in records for s in r["skills"]}, hint=hint)
    _uses_comprehension(ctx, "all_skills")


@MISSION.check("Feature matrix — `feature_rows` builds one row per record")
def _features(ctx):
    rng = random.Random("PY01:features")
    cases = ((_census(rng, 5), ["age", "sector"]), (_census(rng, 4), ["sector", "name", "age"]),
             (_census(rng, 3), []), ([], ["age"]))
    for records, keys in cases:
        got, shown = _call(ctx, "feature_rows", records, keys)
        expected = [[r[k] for k in keys] for r in records]
        hint = "A comprehension inside a comprehension:  [[r[k] for k in keys] for r in records]"
        if isinstance(got, list) and got and isinstance(got[0], tuple):
            hint = "Each row should be a list (square brackets), not a tuple."
        elif isinstance(got, list) and len(got) != len(records):
            hint = "One inner list per RECORD. The outer comprehension loops over records, the inner over keys."
        _expect("feature_rows", shown, got, expected, hint=hint)


@MISSION.check("Purge the ghost — corrupted `clean_names` repaired")
def _clean(ctx):
    rng = random.Random("PY01:clean")
    messy = [{"name": f"{' ' * rng.randint(0, 3)}{n.upper() if i % 2 else n}{' ' * rng.randint(1, 3)}",
              "age": 30, "sector": "grid", "skills": []} for i, n in enumerate(rng.sample(NAMES, 5))]
    messy[0]["name"] = "\t" + messy[0]["name"]
    got, shown = _call(ctx, "clean_names", messy)
    if isinstance(got, list) and any(callable(item) for item in got):
        raise Fail(f"`clean_names` returned {_short(got[:2], 100)}: method objects, not names.",
                   hint="`.lower` without parentheses is the method itself. Add () to CALL it.")
    _expect("clean_names", shown, got, [r["name"].strip().lower() for r in messy],
            hint="Strip the whitespace AND lowercase, each with its call parentheses.")
