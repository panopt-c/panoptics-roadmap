"""LAB PY04 // SCROLLS OF THE ORDER — csv.DictReader/DictWriter and turning text into typed records."""
from __future__ import annotations

import ast
import copy
import csv
import io
import random
import tempfile
from pathlib import Path

from engine.mission import Fail, Mission

FIELDS = ["id", "name", "sector", "age", "yield_kg", "active"]

SCROLLS_CSV = """\
id,name,sector,age,yield_kg,active
1,Ines Calder,grid,34,12.5,yes
2,"Okoye, Elder",archive,61,3.25,no
3, Ren ,GRID,9,0.0,TRUE
4,"Kael ""Spark"" Voss",foundry,100,41.75,False
5,Tomo,grid,15,7,1
6,Mira Sol,undercroft,47,19.5,0
"""

MISSION = Mission(
    id="PY04",
    slug="py04_scrolls",
    title="SCROLLS OF THE ORDER",
    concept="The csv module & typed records",
    enemy="INKROT.scribe",
    xp=120,
    par_seconds=30 * 60,
    tier=2,
    concepts=("files", "parsing", "types"),
    requires=(),
    timeout=10,
    run_as_main=False,
    assets={"scrolls.csv": SCROLLS_CSV},
    enemy_art="""\
    ▄▄▄▄▄▄▄▄▄▄▄
   █ ,  "  ,  "█
   █ "4" > "10"█
   █  , ,  "  ,█
   ▀█▄▄▄▄▄▄▄▄▄▀
     ▀ ▓ ▀ ▓ ▀""",
    briefing="""\
The Order kept its records on scrolls. After the Null Event the surviving ones were transcribed
into `.csv` files, and **INKROT.scribe** has been in them ever since. It splits names at their
commas. It swears the oldest monk in the Monastery is nine. It reads "no" as yes.

"Every value in a file is text," Ada says, "until you prove otherwise. The old world forgot that.
It trained on numbers that were never numbers."

`scrolls.csv` sits beside your file. Read it with the `csv` module, then give every column its real
type.

**Read the scrolls with `csv`, type every field, write them back, and fix INKROT's oldest monk.**
""",
    why="""\
Most datasets you'll touch first arrive as CSV: Kaggle files, database exports, logs, labelling-tool
output. Two things go wrong every time. A field contains a comma (`"Okoye, Elder"`), so
`line.split(",")` shifts every column after it. And every value comes in as a **string**, so `"9" >
"10"` and `bool("False")` is `True`.

```python
with open("train.csv", newline="", encoding="utf-8") as f:
    rows = [{**r, "age": int(r["age"]), "y": float(r["y"])} for r in csv.DictReader(f)]
```

A PyTorch `Dataset.__init__` often looks exactly like that. `pandas.read_csv` does the quoting and
type inference for you, and still guesses wrong on mixed columns, so you need to know what it does.
""",
    manual="""\
**1. `csv.DictReader` turns each line into a dict keyed by the header.** Open with `newline=""` (the
csv module handles line endings itself) and an explicit encoding:

```python
import csv
with open("scrolls.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
rows[1]   # {'id': '2', 'name': 'Okoye, Elder', 'sector': 'archive', 'age': '61', ...}
```

Quoted fields keep their commas and `""` becomes one `"`. `line.split(",")` gets both wrong.

**2. Every value is a `str`. Convert it yourself.**

```python
int("61")          # 61
float("3.25")      # 3.25
float("7")         # 7.0
" Ren ".strip()    # 'Ren'
"GRID".lower()     # 'grid'
```

**3. The truth trap.** `bool()` of any non-empty string is `True`:

```python
bool("False")   # True   (!)
bool("no")      # True   (!)
bool("")        # False
```

Compare the text instead: `text.strip().lower() in {"yes", "true", "1"}`. And when the text is
neither yes nor no, `raise ValueError(...)`: refusing bad data beats guessing.

**4. Strings sort and compare as text.** `"9" > "100"` is `True` because `"9" > "1"`. Convert first:
`max(int(r["age"]) for r in rows)`, or `max(rows, key=lambda r: int(r["age"]))`.

**5. `csv.DictWriter` writes dicts back out.**

```python
with open("out.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["id", "name"], extrasaction="ignore")
    w.writeheader()
    w.writerows(records)   # quotes values that need it; extra keys are ignored
```

Without `extrasaction="ignore"`, a record with a key not in `fieldnames` raises `ValueError`.

**The common mistake:** forgetting `newline=""`. On Windows, writing without it puts a blank line
between every row.

**The library version:** `pd.read_csv("scrolls.csv", dtype={"age": int})`,
`df.to_csv("out.csv", columns=[...], index=False)`. You'll meet them in ARCHIVE OF NOISE.
""",
    starter='''
"""
==============================================================================
  LAB PY04 // SCROLLS OF THE ORDER                  TARGET: INKROT.scribe
==============================================================================
  scrolls.csv is in this folder. Columns:
      id, name, sector, age, yield_kg, active
  The grader writes FRESH csv files and passes you their paths. Save, then HACK.
"""
import csv


# -- OBJECTIVE 1 -------------------------------------------------------------
# read_rows(path) -> list of dicts, one per data row, keyed by the header.
# Values stay strings here. Use csv.DictReader, not split(",").
#   read_rows("scrolls.csv")[1]["name"]  ->  'Okoye, Elder'
#   a file holding only the header line  ->  []
def read_rows(path):
    pass  # TODO


# -- OBJECTIVE 2 -------------------------------------------------------------
# parse_record(row) -> a NEW dict with real types:
#     id        int
#     name      str, surrounding whitespace stripped
#     sector    str, stripped and lowercased
#     age       int
#     yield_kg  float
#     active    bool: "yes" / "true" / "1"  -> True
#                     "no" / "false" / "0"  -> False
#               (any capitals, any surrounding spaces)
#               anything else -> raise ValueError
#   parse_record({"id": "3", "name": " Ren ", "sector": "GRID", "age": "9",
#                 "yield_kg": "0.0", "active": "TRUE"})
#   -> {'id': 3, 'name': 'Ren', 'sector': 'grid', 'age': 9, 'yield_kg': 0.0, 'active': True}
TRUE_WORDS = {"yes", "true", "1"}
FALSE_WORDS = {"no", "false", "0"}


def parse_record(row):
    pass  # TODO


# -- OBJECTIVE 3 -------------------------------------------------------------
# load_typed(path) -> list of parsed records (read_rows + parse_record).
def load_typed(path):
    pass  # TODO


# -- OBJECTIVE 4 -------------------------------------------------------------
# write_rows(path, records, fields) -> writes a CSV with a header row and the
# columns in `fields`, in that order. Records may carry extra keys: ignore them.
# Return the number of data rows written.
#   write_rows("out.csv", load_typed("scrolls.csv"), ["name", "age"])  ->  6
def write_rows(path, records, fields):
    pass  # TODO


# -- OBJECTIVE 5 // CORRUPTED CODE -------------------------------------------
# oldest_age(path) should return the largest age in the file, as an int.
# INKROT rewrote it. On scrolls.csv it swears the oldest monk is nine.
def oldest_age(path):
    with open(path, newline="", encoding="utf-8") as f:
        return max(row["age"] for row in csv.DictReader(f))
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "This scroll says Brother Kael is a hundred. INKROT says the oldest of us is nine. Which do you believe?"},
            {"speaker": "ada", "mood": "smirk",
             "text": "Neither, yet. A file only holds text. Types are a claim you make about it, so make them carefully."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "scrolls.csv is beside your mission file. Open it in the editor first. Look before you parse."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "ValueError: invalid literal for int()? A column isn't what you assumed. Print the row and look."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "FileNotFoundError: use the path you were given. The grader's files aren't named scrolls.csv."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "DictWriter raised ValueError on extra keys? extrasaction='ignore' tells it to skip them."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "If a name came back cut in half, something split on a comma inside quotes. Let csv do the reading."}],
            [{"speaker": "cipher", "mood": "smirk",
              "text": "bool('False') is True. Every non-empty string is. Compare the text instead."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "'9' beats '100' when they're both text. Convert before you compare. Always."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Brother Kael is a hundred again. He'll be insufferable about it. The scrolls are honest now."},
            {"speaker": "ada", "mood": "neutral",
             "text": "The old world's models ate columns of numbers that were really text, and nobody checked. We check."},
            {"speaker": "cipher", "mood": "smirk",
             "text": "Next she'll ask what the numbers mean. Averages, {callsign}. By hand. I can already hear it."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

NAMES = ("Ines Calder", "Okoye, Elder", 'Kael "Spark" Voss', "Tomo", "Mira Sol", "Ren", "Juno, the Younger",
         "Bex Arno", "Sora", "Pell Vance", "Yara, Keeper", "Dov")
SECTORS = ("grid", "archive", "foundry", "undercroft", "reactor")
TRUE_TEXT = ("yes", "Yes", "TRUE", "true", "1", " yes ", "True")
FALSE_TEXT = ("no", "No", "FALSE", "false", "0", " no", "False")


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


def _call(ctx, name: str, *args, shown: str = ""):
    fn = _func(ctx, name)
    shown = shown or ", ".join(_short(a, 90) for a in args)
    try:
        result = fn(*copy.deepcopy(args))
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        hint = "Call it yourself on this input and read the error."
        if isinstance(exc, FileNotFoundError):
            hint = "Open the `path` argument you were given, not a fixed file name."
        elif isinstance(exc, ValueError) and "invalid literal" in str(exc):
            hint = "A conversion met text it didn't expect. Strip whitespace before int()/float(), and check the column."
        elif isinstance(exc, ValueError) and "dict contains fields not in fieldnames" in str(exc):
            hint = "Records carry extra keys. csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')."
        elif isinstance(exc, KeyError):
            hint = "A row was asked for a column it doesn't have. Is the header being read as the header?"
        raise Fail(f"`{name}({shown})` crashed: {type(exc).__name__}: {exc}", hint=hint)
    if result is None:
        raise Fail(f"`{name}({shown})` returned None.", hint="Finish the TODO: the function needs a return.")
    return result


def _raw_row(rng: random.Random, i: int) -> dict:
    """A row as csv.DictReader would give it: every value a string, some untidy."""
    name = rng.choice(NAMES)
    return {"id": str(i), "name": rng.choice(("", " ", "")) + name + rng.choice(("", " ")),
            "sector": rng.choice((str.upper, str.lower, str.capitalize))(rng.choice(SECTORS)),
            "age": str(rng.choice((rng.randint(5, 9), rng.randint(10, 99), rng.randint(100, 104)))),
            "yield_kg": rng.choice((str(rng.randint(0, 40)), f"{rng.uniform(0, 50):.2f}")),
            "active": rng.choice(TRUE_TEXT + FALSE_TEXT)}


def _ref_parse(row: dict) -> dict:
    flag = row["active"].strip().lower()
    return {"id": int(row["id"]), "name": row["name"].strip(), "sector": row["sector"].strip().lower(),
            "age": int(row["age"]), "yield_kg": float(row["yield_kg"]), "active": flag in {"yes", "true", "1"}}


def _csv_text(rows: list, fields=FIELDS) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _write(folder: Path, name: str, text: str) -> str:
    path = folder / name
    path.write_bytes(text.encode("utf-8"))
    return str(path)


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Unroll — `read_rows` reads quoted fields with csv")
def _read(ctx):
    rng = random.Random("PY04:read")
    rows = [_raw_row(rng, i) for i in range(1, 9)]
    rows[2]["name"] = "Okoye, Elder"
    rows[5]["name"] = 'Kael "Spark" Voss'
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for fname, expected in (("census_a.csv", rows), ("only_header.csv", [])):
            path = _write(folder, fname, _csv_text(expected))
            got = _call(ctx, "read_rows", path, shown=f"<{fname}>")
            if not isinstance(got, list):
                raise Fail(f"`read_rows(<{fname}>)` returned {type(got).__name__}; it should return a list of dicts.",
                           hint="list(csv.DictReader(f)) gives one dict per data row.")
            got = [dict(r) if isinstance(r, dict) else r for r in got]
            if got != expected:
                hint = "with open(path, newline='', encoding='utf-8') as f: return list(csv.DictReader(f))"
                if len(got) == len(expected) + 1:
                    hint = "You returned the header as a row. DictReader uses the first line as keys, not data."
                elif any(isinstance(r, dict) and None in r for r in got) or (
                        len(got) == len(expected) and got[2] != expected[2]):
                    hint = ("A quoted field like \"Okoye, Elder\" holds a comma. split(',') cuts it in two; "
                            "csv.DictReader keeps it whole.")
                first_bad = next((i for i, (g, e) in enumerate(zip(got, expected)) if g != e), min(len(got), 1))
                shown_got = got[first_bad] if first_bad < len(got) else "(missing)"
                shown_exp = expected[first_bad] if first_bad < len(expected) else "(no such row)"
                raise Fail(f"`read_rows(<{fname}>)`: {len(got)} rows, expected {len(expected)}. Row {first_bad}: "
                           f"got {_short(shown_got, 160)}, expected {_short(shown_exp, 160)}.", hint=hint)


@MISSION.check("Type rite — `parse_record` gives every field its real type")
def _types(ctx):
    rng = random.Random("PY04:types")
    for i in range(1, 9):
        row = _raw_row(rng, rng.randint(1, 999))
        row["active"] = "yes" if i % 2 else "1"
        got = _call(ctx, "parse_record", row)
        expected = _ref_parse(row)
        if not isinstance(got, dict):
            raise Fail(f"`parse_record` returned {type(got).__name__}; it should return a dict.",
                       hint="Build and return a new dict with the six converted fields.")
        for key, want in expected.items():
            have = got.get(key, "(missing)")
            if type(have) is not type(want) or have != want:
                hints = {"id": "int(row['id'])", "age": "int(row['age']); '61' is text, 61 is a number.",
                         "yield_kg": "float(row['yield_kg']); float('7') is 7.0.",
                         "name": "row['name'].strip() removes the spaces around the name.",
                         "sector": "row['sector'].strip().lower()",
                         "active": "Compare the stripped, lowercased text against the TRUE_WORDS set."}
                raise Fail(f"`parse_record({_short(row, 150)})`[{key!r}] is {have!r} "
                           f"({type(have).__name__}), expected {want!r} ({type(want).__name__}).", hint=hints[key])
        if set(got) != set(expected):
            raise Fail(f"`parse_record` returned keys {sorted(got)}, expected exactly {sorted(expected)}.",
                       hint="One key per CSV column, same names.")


@MISSION.check("The truth trap — 'False' and 'no' must become False")
def _truth(ctx):
    rng = random.Random("PY04:truth")
    base = _raw_row(rng, 7)
    for text in TRUE_TEXT + FALSE_TEXT:
        row = {**base, "active": text}
        got = _call(ctx, "parse_record", row)
        want = text.strip().lower() in {"yes", "true", "1"}
        if not isinstance(got, dict) or got.get("active") is not want:
            have = got.get("active") if isinstance(got, dict) else got
            hint = "Compare text, don't cast it:  flag = row['active'].strip().lower(); flag in TRUE_WORDS"
            if have is True and not want:
                hint = f"bool({text!r}) is True: every non-empty string is truthy. Compare the text instead."
            raise Fail(f"active={text!r} became {have!r}; it should be {want}.", hint=hint)
    fn = _func(ctx, "parse_record")
    for junk in ("maybe", "", "2"):
        try:
            got = fn({**base, "active": junk})
        except ValueError:
            continue
        except Exception as exc:  # noqa: BLE001
            raise Fail(f"active={junk!r} raised {type(exc).__name__}; it should raise ValueError.",
                       hint="raise ValueError(f'bad active flag: {text!r}')")
        raise Fail(f"active={junk!r} was accepted as {_short(got.get('active') if isinstance(got, dict) else got)}. "
                   "Neither yes nor no is a lie waiting to happen.",
                   hint="If the text isn't in TRUE_WORDS or FALSE_WORDS, raise ValueError.")


@MISSION.check("Whole scroll — `load_typed` loads a typed file")
def _load(ctx):
    rng = random.Random("PY04:load")
    rows = [_raw_row(rng, i) for i in range(1, 11)]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for fname, data in (("scroll_b.csv", rows), ("blank.csv", [])):
            path = _write(folder, fname, _csv_text(data))
            got = _call(ctx, "load_typed", path, shown=f"<{fname}>")
            expected = [_ref_parse(r) for r in data]
            if got != expected:
                raise Fail(f"`load_typed(<{fname}>)` returned {_short(got, 200)}, expected {_short(expected, 200)}.",
                           hint="[parse_record(r) for r in read_rows(path)]")


@MISSION.check("Inscribe — `write_rows` writes a CSV that reads back")
def _write_rows(ctx):
    rng = random.Random("PY04:write")
    records = [_ref_parse(_raw_row(rng, i)) for i in range(1, 8)]
    records[1]["name"] = "Okoye, Elder"
    records[3]["name"] = 'Kael "Spark" Voss'
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for fields in (["name", "age", "active"], ["yield_kg", "id", "sector", "name"]):
            path = folder / "inscribed.csv"
            got = _call(ctx, "write_rows", str(path), records, fields,
                        shown=f"<out.csv>, <{len(records)} records>, {fields!r}")
            if not path.exists():
                raise Fail("`write_rows` returned but no file was written at the path it was given.",
                           hint="open(path, 'w', newline='', encoding='utf-8') and write through csv.DictWriter.")
            with open(path, newline="", encoding="utf-8") as f:
                back = list(csv.reader(f))
            expected = [fields] + [[str(r[k]) for k in fields] for r in records]
            if back != expected:
                hint = "DictWriter(f, fieldnames=fields, extrasaction='ignore'), then writeheader() and writerows()."
                if back and back[0] != fields:
                    hint = "The first line must be the header, with exactly the `fields` columns in that order."
                elif any(r == [] for r in back):
                    hint = "Blank lines between rows: open the file with newline=''."
                elif len(back) == len(expected) and back[1:] != expected[1:]:
                    hint = "Let csv.DictWriter write values; it quotes names that contain commas or quotes."
                bad = next((i for i, (b, e) in enumerate(zip(back, expected)) if b != e), len(back))
                raise Fail(f"Reading the file back with csv.reader, line {bad} is "
                           f"{_short(back[bad] if bad < len(back) else '(missing)', 120)}, expected "
                           f"{_short(expected[bad] if bad < len(expected) else '(nothing)', 120)}.", hint=hint)
            if got != len(records):
                raise Fail(f"`write_rows` returned {got!r}; it should return {len(records)}, the data rows written.",
                           hint="Return len(records). The header doesn't count.")


@MISSION.check("Purge the rot — corrupted `oldest_age` compares numbers")
def _oldest(ctx):
    rng = random.Random("PY04:oldest")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for n in (7, 5):
            rows = [_raw_row(rng, i) for i in range(1, n + 1)]
            rows[0]["age"] = str(rng.randint(5, 9))
            rows[-1]["age"] = str(rng.randint(100, 104))
            rng.shuffle(rows)
            path = _write(folder, f"ages_{n}.csv", _csv_text(rows))
            got = _call(ctx, "oldest_age", path, shown=f"<ages_{n}.csv>")
            expected = max(int(r["age"]) for r in rows)
            if got != expected or type(got) is not int:
                hint = "Convert before comparing:  max(int(row['age']) for row in ...)"
                if isinstance(got, str):
                    hint = (f"You returned the text {got!r}. As text, '9' > '100' because '9' > '1'. "
                            "Convert each age with int() before max().")
                raise Fail(f"`oldest_age` on ages {[int(r['age']) for r in rows]} returned {got!r}, "
                           f"expected {expected}.", hint=hint)
