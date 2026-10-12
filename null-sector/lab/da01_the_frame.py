"""LAB DA01 // THE FRAME — DataFrames: load, inspect, select (ARCHIVE OF NOISE, docs/GAME_DESIGN.md §13)."""
from __future__ import annotations

import ast
import math
import random
import tempfile
import warnings
from pathlib import Path

from engine.mission import Fail, Mission

try:
    import numpy as np
    import pandas as pd
except ImportError:      # the Lab shows `pip install pandas`; the module must still import without it
    np = pd = None


# ── the archive (asset + fresh grader data come from the same generator) ─────────────────

SECTORS = ("ASH", "BRINE", "CINDER", "DUST", "EMBER")
CREWS = ("KITE", "MULE", "WREN", "TERN", "MOTH", "GALE")
COLUMNS = ("run_id", "date", "sector", "crew", "distance_km", "rad_level", "hours", "haul_kg", "returned")


def _rows(seed: int, n: int) -> list[dict]:
    """Scavenger runs into the Dead Zone: one dict per run, deterministic for a seed."""
    rng = random.Random(seed)
    ids = rng.sample(range(100, 1000), n)
    rows = []
    for run_id in ids:
        distance = round(rng.uniform(2, 40), 1)
        rad = round(rng.uniform(0.1, 9.9), 2)
        rows.append({
            "run_id": run_id,
            "date": f"2088-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            "sector": rng.choice(SECTORS),
            "crew": rng.choice(CREWS),
            "distance_km": distance,
            "rad_level": rad,
            "hours": rng.randint(2, 30),
            "haul_kg": round(rng.uniform(0, 3) * distance, 1),
            "returned": rng.random() > rad / 14,
        })
    return rows


def _csv(rows: list[dict]) -> str:
    lines = [",".join(COLUMNS)]
    lines += [",".join(str(r[c]) for c in COLUMNS) for r in rows]
    return "\n".join(lines) + "\n"


MISSION = Mission(
    id="DA01",
    slug="da01_the_frame",
    title="THE FRAME",
    concept="DataFrames: load, inspect, select",
    enemy="MISFILE.daemon",
    xp=200,
    par_seconds=30 * 60,
    tier=3,
    concepts=("pandas", "files"),
    requires=("numpy", "pandas"),
    timeout=15,
    run_as_main=False,
    assets={"archive_runs.csv": _csv(_rows(1337, 40))},
    enemy_art="""\
 ┌──┬──┬──┬──┐
 │▓▓│░?│▓▓│?░│
 ├──┼──┼──┼──┤
 │?░│▓▓│░?│▓▓│
 └──┴─▀▄▄▀─┴──┘
    ▀▄▀  ▀▄▀""",
    briefing="""\
The Archive came back from the flood as paper pulp and one working drive. On it: the scavenger
logs, every run the Order's crews ever made into the Dead Zone. Who went, where, how far, how
much radiation, what they hauled, and whether they came home.

**MOTHER ADA** wipes the drive on her sleeve. "This is the chapter the old world skipped. They
had more data than any civilisation in history, and they never looked at it."

Something lives in the file table. **MISFILE.daemon** swaps labels for positions and hands you
the wrong rows with a straight face.

**Load the run logs into a DataFrame, read its vital signs, and select exactly what you ask for.**
""",
    why="""\
Almost every ML project starts with a table, and in Python a table is a pandas `DataFrame`. The
first hour of any project is this mission: load, check dtypes, look at the numbers, split
features from the label.

```python
df = pd.read_csv("loans.csv", index_col="loan_id", parse_dates=["opened"])
df.info()                 # dtypes + missing counts: is "income" text by mistake?
df.describe()             # ranges: is anyone 400 years old?
X = df.drop(columns=["defaulted"])
y = df["defaulted"]
model.fit(X, y)           # scikit-learn takes DataFrames directly
```

Selecting the wrong rows is the quiet killer: `loc` and `iloc` look alike and disagree as soon as
the index isn't 0, 1, 2… Get it wrong and your labels shift by one row against your features:
the model trains, the numbers look fine, and every prediction is nonsense.
""",
    manual="""\
**1. Load a CSV.** `pd.read_csv` turns a file into a DataFrame: named columns, one dtype each,
and an **index** (the row labels).

```python
import pandas as pd
df = pd.read_csv("archive_runs.csv", index_col="run_id", parse_dates=["date"])
df.shape      # (40, 8)    rows, columns (run_id is now the index, not a column)
df.head(3)    # first 3 rows        df.tail(3)  last 3
df.dtypes     # one dtype per column: float64, int64, bool, datetime64, str/object
df.info()     # dtypes + non-null counts in one look
```

`index_col` makes a column the row labels. `parse_dates` turns text like `2088-03-14` into
real datetimes (without it, dates are just strings and you can't compare or subtract them).

**2. Columns.** One name gives a **Series** (one column); a list gives a **DataFrame**:

```python
df["haul_kg"]                    # Series
df[["haul_kg", "hours"]]         # DataFrame with 2 columns
df.select_dtypes("number").columns   # the numeric columns (bool doesn't count)
X = df.drop(columns=["returned"])    # a NEW frame without the label
y = df["returned"]
```

`df.pop("returned")` also gives you `y`, but it **deletes the column from `df` itself**: whoever
handed you that frame just lost their labels.

**3. `loc` = by label, `iloc` = by position.** They only agree when the index is 0, 1, 2, …

```python
df.iloc[0:3]                       # the first 3 rows, whatever their labels
df.loc[[412, 108], ["sector", "haul_kg"]]   # rows labelled 412 and 108, two columns
df.loc[0:3]    # label slice: rows whose LABELS run from 0 to 3, INCLUSIVE. Not what you want here.
```

**4. Filter with a boolean mask.** Combine conditions with `&` (and), `|` (or), `~` (not), and
wrap each condition in **parentheses**:

```python
df[(df["sector"] == "ASH") & (df["rad_level"] >= 5)]
```

**Common mistake:** writing `and` instead of `&`. Python's `and` wants ONE True/False, a column
has forty, so pandas raises *"The truth value of a Series is ambiguous"*.

**5. Describe.** `df.describe()` gives count/mean/std/min/quartiles/max for each numeric column;
`df["haul_kg"].describe()["std"]` reads one number. Missing values (NaN) are skipped, and
pandas' `std` divides by **n − 1** (sample std, `ddof=1`), while `np.std` divides by **n**
(`ddof=0`). Same data, different numbers. Know which one you're quoting.

**In the wild:** scikit-learn estimators accept `X` as a DataFrame and remember its column names
(`model.feature_names_in_`). PyTorch wants arrays: `torch.tensor(X.to_numpy(dtype="float32"))`.
""",
    starter='''
"""
==============================================================================
  LAB DA01 // THE FRAME                               TARGET: MISFILE.daemon
==============================================================================
  The scavenger logs survived the flood in archive_runs.csv (next to this
  file). Write the functions below. The grader calls them with FRESH frames
  and files it builds itself, so they must work for any run log.
  Save, then HACK from the Lab.
"""
import pandas as pd


# -- OBJECTIVE 1 -------------------------------------------------------------
def load_runs(path):
    """Read the run log CSV at `path` into a DataFrame.

    - the `run_id` column becomes the index (the row labels)
    - the `date` column is parsed into real datetimes
    load_runs("archive_runs.csv").shape  ->  (40, 8)
    """
    # TODO: pd.read_csv(path, index_col=..., parse_dates=[...])
    pass


# -- OBJECTIVE 2 -------------------------------------------------------------
def profile(df):
    """The frame's vital signs, as a dict:
        {"rows": int, "cols": int,
         "dtypes": {column name: str(dtype)},        e.g. {"hours": "int64", ...}
         "numeric": [names of the number columns, in order]}
    "numeric" lists exactly what df.select_dtypes("number") keeps (bool columns are not numbers).
    """
    # TODO: df.shape, df.dtypes.items(), df.select_dtypes("number").columns
    pass


# -- OBJECTIVE 3 -------------------------------------------------------------
def split_xy(df, target):
    """Split into features X (every column except `target`) and label y (the `target` column).

    Return (X, y): X a DataFrame, y a Series. Do NOT change `df` itself.
    """
    # TODO: df.drop(columns=[...]) and df[target]. Careful: df.pop() edits df in place.
    pass


# -- OBJECTIVE 4 -------------------------------------------------------------
def rows_at(df, start, stop):
    """The rows at POSITIONS start..stop-1 (like list slicing), all columns."""
    # TODO: position, not label.
    pass


def records(df, run_ids, columns):
    """The rows whose LABELS (run_ids) are in `run_ids`, in that order, with only `columns`."""
    # TODO: label, not position.
    pass


# -- OBJECTIVE 5 // CORRUPTED CODE -------------------------------------------
def hot_zone(df, sector, min_rad):
    """Runs in `sector` with rad_level of at least `min_rad` (all columns, original labels)."""
    # MISFILE rewrote this filter. Hack once, read the error, and fix it.
    return df[df["sector"] == sector and df["rad_level"] >= min_rad]


# -- OBJECTIVE 6 -------------------------------------------------------------
def column_stats(df, col):
    """Summary numbers for column `col`, exactly as df[col].describe() reports them:
        {"count": ..., "mean": ..., "std": ..., "min": ..., "max": ...}
    Missing values are skipped. std is pandas' sample std (divides by n - 1).
    """
    # TODO: read them from df[col].describe() (or the matching Series methods).
    pass


# Try your code here. The grader ignores this block; `python da01_the_frame.py` runs it.
if __name__ == "__main__":
    runs = load_runs("archive_runs.csv")
    print(runs.head())
    print(profile(runs))
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Before a model, a table. Before a table, a question: what is in it? Don't guess. Look."},
            {"speaker": "ada", "mood": "neutral",
             "text": "A DataFrame is columns with names and rows with labels. Labels are not positions. Remember that, it will save you."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Forty runs on the drive, {callsign}. MISFILE has been shuffling the row labels since the flood."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "'Truth value of a Series is ambiguous': you asked forty rows one yes-or-no question. Use & and parentheses."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "A KeyError names a column that isn't there. Print df.columns. Spelling is data too."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Script went down before the checks ran. The COMBAT LOG has the line."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "loc asks for a name. iloc asks for a seat number. MISFILE is betting you can't tell them apart."}],
            [{"speaker": "ada", "mood": "cold",
              "text": "Never hand back a frame you've quietly cut a column out of. Whoever passed it to you still needs it."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader writes its own logs with fresh run ids. Code that fits archive_runs.csv alone won't pass."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Shape, dtypes, describe. You looked before you touched. Most of the old world's models never got that courtesy."},
            {"speaker": "ada", "mood": "neutral",
             "text": "The Core's first training table had its labels shifted one row. Nobody looked. It learned to be wrong, very precisely."},
            {"speaker": "cipher", "mood": "warm",
             "text": "MISFILE is out of the file table. Ada's turning the drive over. There are holes in these logs, {callsign}."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

def _short(text, limit: int = 150) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _show(value) -> str:
    if isinstance(value, pd.DataFrame):
        cols = [str(c) for c in value.columns]
        shown = ", ".join(cols[:8]) + (", …" if len(cols) > 8 else "")
        return f"a DataFrame of shape {value.shape} with columns [{shown}]"
    if isinstance(value, pd.Series):
        return f"a Series named {value.name!r} of length {len(value)} ({value.dtype})"
    return _short(repr(value), 120)


def _cell(value) -> str:
    if isinstance(value, (float, np.floating)):
        return "NaN" if math.isnan(value) else f"{float(value):.6g}"
    if isinstance(value, np.generic):
        value = value.item()
    return _short(repr(value), 40)


def _fn(ctx, name: str):
    obj = ctx.ns.get(name)
    if callable(obj):
        return obj
    if ctx.crashed and any(isinstance(n, ast.FunctionDef) and n.name == name for n in ctx.tree.body):
        raise Fail(f"`{name}` is in your file, but the script crashed before Python defined it. "
                   "Fix the crash in the COMBAT LOG first.")
    raise Fail(f"No function named `{name}` found.",
               hint=f"Keep the starter's  def {name}(...):  line; spelling and underscores must match.")


def _crash_hint(exc: BaseException) -> str:
    msg = str(exc)
    if "truth value of a" in msg and "ambiguous" in msg:
        return ("`and`/`or` want ONE True/False; a column holds many. Combine masks with & and |, and wrap "
                "each condition in parentheses: (df[a] == x) & (df[b] >= y).")
    if "slice bound" in msg:
        return ("df.loc[a:b] slices by LABEL, and these run ids aren't 0, 1, 2… For positions (like list "
                "slicing) use df.iloc[a:b].")
    if isinstance(exc, KeyError):
        return "pandas couldn't find that label. Print df.columns and df.index: is it a column name, a row label, or a position?"
    if isinstance(exc, IndexError) and "positional" in msg:
        return "iloc takes positions (0, 1, 2…). To pick rows by their run_id labels, use loc."
    if isinstance(exc, (AttributeError, TypeError)) and "NoneType" in msg:
        return "Something is None: a function with no `return` gives back None."
    if isinstance(exc, FileNotFoundError):
        return "Open the `path` you were given; don't hard-code a filename."
    return "Call the function at the bottom of your file on archive_runs.csv and read the full error."


def _call(fn, label: str, *args):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return fn(*args)
    except Fail:
        raise
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {_short(exc, 160)}", hint=_crash_hint(exc))


def _need(got, kind, label: str):
    if got is None:
        raise Fail(f"`{label}` returned None.",
                   hint="A function without a `return` line gives back None. Return what you built.")
    if not isinstance(got, kind):
        raise Fail(f"`{label}` returned {_show(got)}, not a {kind.__name__}.",
                   hint="Stay in pandas: df[...], df.loc[...], df.iloc[...] and df.drop(...) all return pandas objects.")
    return got


def _differs(got: "pd.Series", want: "pd.Series", tol: float = 1e-6):
    """Positional mask of cells that differ (NaN equals NaN)."""
    g, w = got.reset_index(drop=True), want.reset_index(drop=True)
    num = pd.api.types.is_numeric_dtype
    if num(g) and num(w):
        gf = g.astype("float64").to_numpy()
        wf = w.astype("float64").to_numpy()
        return ~np.isclose(gf, wf, rtol=tol, atol=tol, equal_nan=True)
    gn, wn = g.isna().to_numpy(), w.isna().to_numpy()
    same = np.array([bool(a == b) if not (x or y) else False
                     for a, b, x, y in zip(g.tolist(), w.tolist(), gn, wn)], dtype=bool)
    return ~(same | (gn & wn))


def _same_frame(got, want, label: str, hint: str = "", index: bool = True, tol: float = 1e-6) -> None:
    gcols, wcols = [str(c) for c in got.columns], [str(c) for c in want.columns]
    if gcols != wcols:
        missing = [c for c in wcols if c not in gcols]
        extra = [c for c in gcols if c not in wcols]
        detail = (f"missing {missing}" if missing else "") + (" and " if missing and extra else "") + \
                 (f"unexpected {extra}" if extra else "")
        raise Fail(f"`{label}` has columns {_short(gcols, 120)}; expected {_short(wcols, 120)}"
                   f"{' (' + detail + ')' if detail else ' (same names, different order)'}.", hint=hint)
    if len(got) != len(want):
        raise Fail(f"`{label}` has {len(got)} rows; expected {len(want)}.", hint=hint)
    if index and list(got.index) != list(want.index):
        raise Fail(f"`{label}` has row labels {_short(list(got.index), 80)}; expected "
                   f"{_short(list(want.index), 80)}.", hint=hint)
    for col in want.columns:
        bad = _differs(got[col], want[col], tol)
        if bad.any():
            i = int(np.argmax(bad))
            raise Fail(f"`{label}` is wrong in column {col!r}, row label {_cell(want.index[i])}: got "
                       f"{_cell(got[col].iloc[i])}, expected {_cell(want[col].iloc[i])}.", hint=hint)


def _frame(seed: int, n: int, nan_haul: int = 0) -> "pd.DataFrame":
    df = pd.DataFrame(_rows(seed, n)).set_index("run_id")
    df["date"] = pd.to_datetime(df["date"])
    if nan_haul:
        df.iloc[random.Random(seed).sample(range(n), nan_haul), df.columns.get_loc("haul_kg")] = np.nan
    return df


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Open the archive — `load_runs` reads the CSV")
def _load(ctx):
    load_runs = _fn(ctx, "load_runs")
    with tempfile.TemporaryDirectory(prefix="da01-") as tmp:
        fresh = Path(tmp) / "intercepted_runs.csv"
        fresh.write_text(_csv(_rows(2101, 11)), encoding="utf-8")
        shipped = Path(tmp) / "archive_runs.csv"
        shipped.write_text(MISSION.assets["archive_runs.csv"], encoding="utf-8")
        for path in (fresh, shipped):
            label = f"load_runs({path.name!r})"
            got = _need(_call(load_runs, label, str(path)), pd.DataFrame, label)
            want = pd.read_csv(path, index_col="run_id", parse_dates=["date"])
            if "run_id" in got.columns:
                raise Fail(f"`{label}` kept run_id as an ordinary column; the index is {_short(list(got.index[:4]))}….",
                           hint="Make it the row labels while reading: pd.read_csv(path, index_col=\"run_id\", ...).")
            if got.index.name != "run_id" or list(got.index) != list(want.index):
                raise Fail(f"`{label}` has row labels {_short(list(got.index[:5]), 60)}… named {got.index.name!r}; "
                           f"expected the run ids {_short(list(want.index[:5]), 60)}… named 'run_id'.",
                           hint="index_col=\"run_id\" turns that column into the index.")
            if "date" in got.columns and not pd.api.types.is_datetime64_any_dtype(got["date"]):
                raise Fail(f"`{label}`: the date column is {got['date'].dtype}, still text. You can't compare or "
                           "subtract dates stored as strings.", hint="Ask read_csv to parse it: parse_dates=[\"date\"].")
            _same_frame(got, want, label, hint="Read the file you were given, as is: no columns added, dropped or renamed.")


@MISSION.check("Vital signs — `profile` reads shape, dtypes, numeric columns")
def _profile(ctx):
    profile = _fn(ctx, "profile")
    holes = _frame(2201, 9)
    holes["hours"] = holes["hours"].astype("float64")   # what read_csv does to an int column with a hole
    holes.loc[holes.index[3], "hours"] = np.nan
    cases = [_frame(2202, 7), holes, _frame(2203, 5)[["sector", "returned"]]]
    for df in cases:
        label = f"profile(frame of shape {df.shape})"
        got = _call(profile, label, df.copy())
        if not isinstance(got, dict):
            raise Fail(f"`{label}` returned {_show(got)}, not a dict.",
                       hint='Return a dict: {"rows": ..., "cols": ..., "dtypes": ..., "numeric": ...}')
        for key in ("rows", "cols", "dtypes", "numeric"):
            if key not in got:
                raise Fail(f"`{label}` has no {key!r} key. Keys: {sorted(map(str, got))}.",
                           hint="Exactly these keys: 'rows', 'cols', 'dtypes', 'numeric'.")
        if (got["rows"], got["cols"]) != df.shape:
            raise Fail(f"`{label}` reports rows={got['rows']!r}, cols={got['cols']!r}; expected {df.shape[0]} and "
                       f"{df.shape[1]}.", hint="rows, cols = df.shape  (len(df) counts rows; len(df.columns) counts columns).")
        want = {str(c): str(t) for c, t in df.dtypes.items()}
        dtypes = got["dtypes"]
        if not isinstance(dtypes, dict):
            raise Fail(f"`{label}`['dtypes'] is {_show(dtypes)}, not a dict.",
                       hint="Build it from df.dtypes.items(): {col: str(dtype) for col, dtype in df.dtypes.items()}.")
        shown = {str(k): (v if isinstance(v, str) else repr(v)) for k, v in dtypes.items()}
        if shown != want:
            wrong = next((c for c in want if shown.get(c) != want[c]), next(iter(set(shown) - set(want)), "?"))
            hint = "Read each dtype from the frame and wrap it in str(...)."
            if wrong == "hours" and want.get("hours") == "float64":
                hint = ("An int column with even one NaN is stored as float64: NaN is a float. Read the dtype from the "
                        "frame, don't assume it.")
            raise Fail(f"`{label}`['dtypes'][{wrong!r}] is {shown.get(wrong)!r}; expected {want.get(wrong)!r}.",
                       hint=hint)
        numeric = [str(c) for c in df.select_dtypes("number").columns]
        if not isinstance(got["numeric"], (list, tuple)) or [str(c) for c in got["numeric"]] != numeric:
            hint = "df.select_dtypes(\"number\").columns lists them; turn it into a list."
            if isinstance(got["numeric"], (list, tuple)) and "returned" in got["numeric"]:
                hint = "`returned` is bool. select_dtypes(\"number\") leaves bool columns out; so should you."
            raise Fail(f"`{label}`['numeric'] is {_short(got['numeric'], 100)}; expected {numeric}.", hint=hint)


@MISSION.check("Features and label — `split_xy` without touching the source")
def _split(ctx):
    split_xy = _fn(ctx, "split_xy")
    for seed, target in ((2301, "returned"), (2302, "haul_kg")):
        df = _frame(seed, 8)
        original = df.copy()
        label = f"split_xy(frame, {target!r})"
        got = _call(split_xy, label, df, target)
        if not isinstance(got, tuple) or len(got) != 2:
            raise Fail(f"`{label}` returned {_show(got)}; expected a pair (X, y).", hint="return X, y")
        X, y = got
        _need(X, pd.DataFrame, label + "[0] (X)")
        if not df.equals(original) or list(df.columns) != list(original.columns):
            raise Fail(f"`{label}` changed the caller's frame: its columns are now {list(df.columns)}.",
                       hint="df.pop(target) deletes the column from df itself. Use df.drop(columns=[target]) and df[target].")
        if target in X.columns:
            raise Fail(f"X still contains the label column {target!r}. A model trained on that just reads the answer.",
                       hint="X is every column EXCEPT the target: df.drop(columns=[target]).")
        if isinstance(y, pd.DataFrame):
            raise Fail(f"y is a one-column DataFrame, not a Series.",
                       hint="df[target] (one name) gives a Series; df[[target]] (a list) gives a DataFrame.")
        _need(y, pd.Series, label + "[1] (y)")
        _same_frame(X, original.drop(columns=[target]), label + "[0] (X)",
                    hint="Keep every other column, in the original order, with the original row labels.")
        if y.name != target or list(y.index) != list(original.index) or _differs(y, original[target]).any():
            raise Fail(f"y should be the {target!r} column with the original row labels; got {_show(y)}.",
                       hint="y = df[target]")


@MISSION.check("Labels vs positions — `rows_at` (iloc) and `records` (loc)")
def _select(ctx):
    rows_at, records = _fn(ctx, "rows_at"), _fn(ctx, "records")
    df = _frame(2401, 12)
    rng = random.Random(2402)
    start = rng.randint(1, 4)
    stop = start + rng.randint(2, 4)
    label = f"rows_at(frame, {start}, {stop})"
    got = _need(_call(rows_at, label, df.copy(), start, stop), pd.DataFrame, label)
    want = df.iloc[start:stop]
    if len(got) != len(want) or list(got.index) != list(want.index):
        hint = f"Positions {start}..{stop - 1} are the rows SEATED there, whatever their labels: df.iloc[start:stop]."
        if len(got) == 0:
            hint = ("The run ids are labels like 412 or 108. df.loc[start:stop] looks for those LABELS and finds nothing. "
                    "Use iloc for positions.")
        raise Fail(f"`{label}` returned rows labelled {_short(list(got.index), 60)}; expected the rows at positions "
                   f"{start}..{stop - 1}: labels {list(want.index)}.", hint=hint)
    _same_frame(got, want, label)
    empty = _need(_call(rows_at, "rows_at(frame, 3, 3)", df.copy(), 3, 3), pd.DataFrame, "rows_at(frame, 3, 3)")
    if len(empty):
        raise Fail(f"`rows_at(frame, 3, 3)` returned {len(empty)} rows; an empty range gives an empty frame.",
                   hint="Slices stop BEFORE `stop`, like list slicing.")

    ids = [int(i) for i in rng.sample(list(df.index), 4)]
    for ask, cols in ((ids, ["sector", "haul_kg"]), (ids[:1], ["crew", "rad_level", "returned"])):
        label = f"records(frame, {ask}, {cols})"
        got = _need(_call(records, label, df.copy(), ask, cols), pd.DataFrame, label)
        want = df.loc[ask, cols]
        if list(got.index) != list(want.index):
            raise Fail(f"`{label}` returned rows labelled {_short(list(got.index), 60)}; expected {ask}.",
                       hint="These are run_id LABELS, not positions: df.loc[run_ids, columns] picks by label.")
        _same_frame(got, want, label, hint="df.loc[rows, columns] selects both at once.")


@MISSION.check("CORRUPTED CODE — `hot_zone` filters with a boolean mask")
def _hot(ctx):
    hot_zone = _fn(ctx, "hot_zone")
    df = _frame(2501, 30)
    sector = df["sector"].iloc[0]
    edge = float(df.loc[df["sector"] == sector, "rad_level"].iloc[0])     # a run sits exactly on the bar
    for sec, bar in ((sector, edge), (df["sector"].iloc[5], 4.0), ("VOID", 0.0)):
        label = f"hot_zone(frame, {sec!r}, {bar})"
        got = _need(_call(hot_zone, label, df.copy(), sec, bar), pd.DataFrame, label)
        want = df[(df["sector"] == sec) & (df["rad_level"] >= bar)]
        if len(got) == len(want) - int(((df["sector"] == sec) & (df["rad_level"] == bar)).sum()) and len(got) != len(want):
            raise Fail(f"`{label}` dropped the run whose rad_level is exactly {bar}.",
                       hint="\"At least\" includes the bar itself: >= not >.")
        _same_frame(got, want, label,
                    hint="Keep rows where BOTH hold: (df[\"sector\"] == sector) & (df[\"rad_level\"] >= min_rad). "
                         "Keep all columns and the original row labels.")


@MISSION.check("Read the spread — `column_stats` matches describe()")
def _stats(ctx):
    column_stats = _fn(ctx, "column_stats")
    df = _frame(2601, 15, nan_haul=3)
    for col in ("haul_kg", "rad_level", "hours"):
        label = f"column_stats(frame, {col!r})"
        got = _call(column_stats, label, df.copy(), col)
        if not isinstance(got, dict):
            raise Fail(f"`{label}` returned {_show(got)}, not a dict.",
                       hint='{"count": ..., "mean": ..., "std": ..., "min": ..., "max": ...}')
        d = df[col].describe()
        for key in ("count", "mean", "std", "min", "max"):
            if key not in got:
                raise Fail(f"`{label}` has no {key!r} key.", hint="Keys: count, mean, std, min, max.")
            try:
                value = float(got[key])
            except (TypeError, ValueError):
                raise Fail(f"`{label}`[{key!r}] is {_short(repr(got[key]), 60)}, not a number.",
                           hint="Read single numbers, e.g. df[col].describe()[\"mean\"] or df[col].mean().")
            if not math.isclose(value, float(d[key]), rel_tol=1e-6, abs_tol=1e-9):
                hint = f"df[col].describe()[{key!r}] is the number to match."
                if key == "count":
                    hint = "count skips missing values: it's df[col].count(), not len(df)."
                elif key == "std" and math.isclose(value, float(df[col].std(ddof=0)), rel_tol=1e-6):
                    hint = ("That's the population std (divides by n, numpy's default). describe() reports the sample "
                            "std, which divides by n - 1: df[col].std().")
                elif key == "mean" and df[col].isna().any() and math.isnan(value):
                    hint = "Missing values poisoned the mean. pandas' df[col].mean() skips NaN for you."
                raise Fail(f"`{label}`[{key!r}] is {_cell(value)}; expected {_cell(float(d[key]))}.", hint=hint)
