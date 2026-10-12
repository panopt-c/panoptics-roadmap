"""LAB DA02 // MISSING PIECES — missing values & type repair (ARCHIVE OF NOISE, docs/GAME_DESIGN.md §13)."""
from __future__ import annotations

import ast
import math
import random
import warnings

from engine.mission import Fail, Mission

try:
    import numpy as np
    import pandas as pd
except ImportError:      # the Lab shows `pip install pandas`; the module must still import without it
    np = pd = None


SECTORS = ("ASH", "BRINE", "CINDER", "DUST", "EMBER")
CREWS = ("KITE", "MULE", "WREN", "TERN", "MOTH", "GALE")
JUNK = ("n/a", "?", "", "ERR", "--", "null")
FEATURES = ("sector", "crew", "distance_km", "rad_level", "hours", "haul_kg")


def _records(seed: int, n: int, *, holes: float = 0.18, shift: float = 0.0) -> list[dict]:
    """Run logs with holes (None) punched in; `shift` moves the numbers (a different time period)."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        distance = round(rng.uniform(2, 40) + shift * 10, 1)
        rad = round(rng.uniform(0.1, 9.9) + shift, 2)
        row = {
            "run_id": 500 + i * 7 + rng.randint(0, 6),
            "sector": rng.choice(SECTORS[: 3 + (i % 3)]),
            "crew": rng.choice(CREWS),
            "distance_km": distance,
            "rad_level": rad,
            "hours": float(rng.randint(2, 30)),
            "haul_kg": round(rng.uniform(0, 3) * distance, 1),
            "returned": float(rng.random() > rad / 14),
        }
        for col in ("sector", "crew", "rad_level", "hours", "haul_kg"):
            if rng.random() < holes:
                row[col] = None
        if rng.random() < holes / 2:
            row["returned"] = None
        rows.append(row)
    return rows


def _asset() -> str:
    """The shipped log: holes as blank cells, plus the junk the old loggers wrote into `hours`."""
    rng = random.Random(4242)
    cols = ("run_id",) + FEATURES + ("returned",)
    lines = [",".join(cols)]
    for r in _records(4242, 36):
        cells = []
        for c in cols:
            v = r[c]
            if c == "hours" and v is not None and rng.random() < 0.15:
                cells.append(rng.choice(JUNK))
            elif v is None:
                cells.append("")
            elif c in ("hours", "returned"):
                cells.append(str(int(v)))
            else:
                cells.append(str(v))
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


MISSION = Mission(
    id="DA02",
    slug="da02_missing_pieces",
    title="MISSING PIECES",
    concept="Missing values & type repair",
    enemy="HOLLOW.wraith",
    xp=200,
    par_seconds=35 * 60,
    tier=3,
    concepts=("pandas", "statistics"),
    requires=("numpy", "pandas"),
    timeout=15,
    run_as_main=False,
    assets={"archive_holes.csv": _asset()},
    enemy_art="""\
  ▄▀▀▀▀▀▀▀▀▀▀▄
 █ ▓▓  ░░  ▓▓ █
 █ ░░  NaN ░░ █
 █ ▓▓  ░░  ▓▓ █
  ▀▄  ▄▀▀▄  ▄▀
    ▀▀    ▀▀""",
    briefing="""\
The second drive is worse. Whole cells eaten out of the run logs: a sector here, a radiation
reading there. In the `hours` column someone wrote `n/a`, `?`, `ERR`, so pandas reads every
number in it as text.

**HOLLOW.wraith** feeds on the gaps. Fill them carelessly and it grows fat on the lie.

**MOTHER ADA** taps a blank cell. "The old world filled holes with whatever made the chart look
smooth. Worse, they filled them using numbers from the exam. A hole is information. Treat it with
respect."

**Measure the holes, repair the types, and fill the gaps with statistics from the training runs
only.**
""",
    why="""\
Real tables have holes: sensors drop out, forms get skipped, joins miss. Most models crash on
NaN (scikit-learn's `LinearRegression` refuses it outright), so every project needs a missing-value
policy, and it is one of the most common places leakage sneaks in:

```python
from sklearn.impute import SimpleImputer
imp = SimpleImputer(strategy="median", add_indicator=True)
X_train = imp.fit_transform(train)   # medians learned from TRAIN only
X_test = imp.transform(test)         # test filled with TRAIN's medians
```

If you compute the fill value on all the data, information from the test set leaks into
training and your score lies. If you fill with 0, you invent measurements. And "was this value
missing?" is often itself predictive: a skipped income field says something.
""",
    manual="""\
**1. Find the holes.** pandas marks missing values as `NaN` (or `None`/`NaT`). Ask with `isna()`:

```python
df.isna().sum()      # missing count per column
df.isna().mean()     # missing FRACTION per column (True counts as 1)
df["rad_level"].isna()        # a True/False mask
```

**Common mistake:** `df["rad_level"] == np.nan` is **always False**. NaN is not equal to
anything, not even itself. Use `isna()`.

**2. Repair types.** One junk string makes a whole column text. `pd.to_numeric` with
`errors="coerce"` turns what parses into numbers and the junk into NaN:

```python
s = pd.Series(["12", " 7", "n/a", "?"])
s.astype(float)                      # ValueError: could not convert string to float: 'n/a'
pd.to_numeric(s, errors="coerce")    # 12.0, 7.0, NaN, NaN   (dtype float64)
```

Don't replace junk with 0: zero hours is a real measurement. Unknown is NaN.

**3. Drop or fill?** `dropna()` drops every row with ANY hole, which can throw away half your
data. Use `subset=` to drop only when a specific column is missing, like the label (never invent
a label):

```python
df.dropna(subset=["returned"])     # rows without a label are useless for training
```

**4. Fill with statistics from TRAIN only.** Median for numbers (one 999 can't drag it), most
common value for categories:

```python
fill = {"rad_level": train["rad_level"].median(), "sector": train["sector"].mode()[0]}
train_f = train.fillna(fill)     # fillna returns a NEW frame...
test_f = test.fillna(fill)       # ...with TRAIN's numbers, also for test
```

The test set stands in for the future. You don't get the future's median.

**5. Remember where the holes were.** Flag them *before* filling:

```python
df["rad_level_missing"] = df["rad_level"].isna().astype(int)
```

`df.fillna(..., inplace=True)` edits `df` and returns **None**. `return df.fillna(x, inplace=True)`
returns nothing at all. Prefer the plain form: `out = df.fillna(x)`.

**In the wild:** `SimpleImputer(strategy="median" | "most_frequent", add_indicator=True)` in
scikit-learn does steps 4 and 5; `fit` on train, `transform` on everything.
""",
    starter='''
"""
==============================================================================
  LAB DA02 // MISSING PIECES                            TARGET: HOLLOW.wraith
==============================================================================
  The run logs have holes. archive_holes.csv (next to this file) is a sample.
  Write the functions below. The grader calls them with FRESH frames it
  builds itself, with holes in new places. Never change the frames you are
  given; return new ones. Save, then HACK from the Lab.
"""
import numpy as np
import pandas as pd


# -- OBJECTIVE 1 -------------------------------------------------------------
def missing_share(df):
    """A Series: for each column, the FRACTION of its values that are missing (0.0 to 1.0).

    Index = the column names, in order.  A column with 2 holes in 8 rows -> 0.25
    """
    # TODO: isna() gives True/False; the mean of True/False is a fraction.
    pass


# -- OBJECTIVE 2 -------------------------------------------------------------
def to_number(series):
    """Turn a column of text into float64 numbers. Anything that isn't a number
    ("n/a", "?", "", "ERR", ...) becomes NaN. Keep the index and the name.

    to_number(pd.Series(["12", " 7", "n/a"]))  ->  12.0, 7.0, NaN
    """
    # TODO: pd.to_numeric(..., errors="coerce")
    pass


# -- OBJECTIVE 3 -------------------------------------------------------------
def drop_unlabeled(df, target):
    """Drop only the rows whose `target` is missing. Rows with holes in OTHER
    columns stay (we can fill those). Keep the row labels."""
    # TODO: dropna with subset=...
    pass


# -- OBJECTIVE 4 -------------------------------------------------------------
def add_missing_flags(df, cols):
    """Return a COPY of df with one extra column per name in `cols`, appended in that order:
        "<col>_missing" = 1 where df[col] is missing, else 0.
    The original columns stay exactly as they were (holes included).
    """
    # TODO: out = df.copy(); out[f"{col}_missing"] = ...
    pass


# -- OBJECTIVE 5 -------------------------------------------------------------
def fit_fill_values(train):
    """Learn one fill value per column of `train`, as a dict {column: value}:
        number columns -> the median (NaN skipped)
        other columns  -> the most common value (ties: .mode()[0], the first in sorted order)
    """
    # TODO: loop over train.columns; pd.api.types.is_numeric_dtype(train[col]) tells them apart.
    pass


# -- OBJECTIVE 6 // CORRUPTED CODE -------------------------------------------
def impute(train, test):
    """Fill the holes in BOTH frames using values learned from `train` only.
    Return (train_filled, test_filled)."""
    # HOLLOW whispered in this one. It runs. It even looks reasonable.
    # The grader will tell you what it gets wrong.
    train_filled = train.fillna(fit_fill_values(train))
    test_filled = test.fillna(fit_fill_values(test))
    return train_filled, test_filled


# Try your code here. The grader ignores this block; `python da02_missing_pieces.py` runs it.
if __name__ == "__main__":
    logs = pd.read_csv("archive_holes.csv", index_col="run_id")
    print(logs.dtypes)
    print(missing_share(logs))
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "A blank cell is not zero. It's 'we don't know'. The difference has killed more models than bad maths."},
            {"speaker": "ada", "mood": "neutral",
             "text": "When you fill a hole, you are inventing data. Invent it honestly: from the past you trained on, never from the exam."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Hours column is reading as text, {callsign}. Someone typed 'n/a' into a number field and poisoned the lot."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "'could not convert string to float': one junk cell, and astype gives up on the whole column. Coerce instead."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "Read the error, then print the column's dtype. Text pretending to be numbers looks fine until you do arithmetic."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Script crashed before HOLLOW even noticed. COMBAT LOG has the line."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "cold",
              "text": "You filled the test set with its own median. That number came from the future. The score you'd get is a lie."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "x == NaN is always False. NaN isn't even equal to itself. Ask isna()."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader punches holes in fresh places every time. Fit the method, not the file."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Medians from the training runs, flags where the holes were, labels never invented. That's an honest fill."},
            {"speaker": "ada", "mood": "neutral",
             "text": "The Core's census had holes where the poor districts were. They filled them with the city average. The poor vanished."},
            {"speaker": "cipher", "mood": "warm",
             "text": "HOLLOW starved. The logs are whole enough to count now, {callsign}. NOVA's been asking for sector totals."},
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
    if value is None:
        return "None"
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
    if "could not convert" in msg or "Unable to parse string" in msg:
        return ("One junk value stops a plain conversion. pd.to_numeric(series, errors=\"coerce\") turns what it "
                "can't parse into NaN instead of crashing.")
    if "truth value of a" in msg and "ambiguous" in msg:
        return "Combine masks with & and |, not `and`/`or`, and wrap each condition in parentheses."
    if isinstance(exc, KeyError):
        return "pandas couldn't find that label. Print df.columns: are you using the column name you were given?"
    if isinstance(exc, TypeError) and ("median" in msg or "could not convert" in msg or "agg function" in msg):
        return "Text columns have no median. Check is_numeric_dtype(col) first; use .mode()[0] for the others."
    if isinstance(exc, (AttributeError, TypeError)) and "NoneType" in msg:
        return ("Something is None. A function with no `return` gives back None, and so does "
                "df.fillna(..., inplace=True). Use out = df.fillna(...) and return out.")
    return "Call the function at the bottom of your file on archive_holes.csv and read the full error."


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
                   hint="A function without a `return` line gives back None, and so does anything called with "
                        "inplace=True. Build a new object and return it.")
    if not isinstance(got, kind):
        raise Fail(f"`{label}` returned {_show(got)}, not a {kind.__name__}.",
                   hint="Stay in pandas: isna(), dropna(), fillna() and to_numeric() all return pandas objects.")
    return got


def _differs(got, want, tol: float = 1e-6):
    """Positional mask of cells that differ (NaN equals NaN)."""
    g, w = got.reset_index(drop=True), want.reset_index(drop=True)
    num = pd.api.types.is_numeric_dtype
    if num(g) and num(w):
        return ~np.isclose(g.astype("float64").to_numpy(), w.astype("float64").to_numpy(),
                           rtol=tol, atol=tol, equal_nan=True)
    gn, wn = g.isna().to_numpy(), w.isna().to_numpy()
    same = np.array([bool(a == b) if not (x or y) else False
                     for a, b, x, y in zip(g.tolist(), w.tolist(), gn, wn)], dtype=bool)
    return ~(same | (gn & wn))


def _same_frame(got, want, label: str, hint: str = "", tol: float = 1e-6) -> None:
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
    if list(got.index) != list(want.index):
        raise Fail(f"`{label}` has row labels {_short(list(got.index), 80)}; expected "
                   f"{_short(list(want.index), 80)}.", hint=hint or "Keep the original row labels.")
    for col in want.columns:
        bad = _differs(got[col], want[col], tol)
        if bad.any():
            i = int(np.argmax(bad))
            raise Fail(f"`{label}` is wrong in column {col!r}, row {_cell(want.index[i])}: got "
                       f"{_cell(got[col].iloc[i])}, expected {_cell(want[col].iloc[i])}.", hint=hint)


def _frame(seed: int, n: int, **kw) -> "pd.DataFrame":
    df = pd.DataFrame(_records(seed, n, **kw)).set_index("run_id")
    for col in ("distance_km", "rad_level", "hours", "haul_kg", "returned"):
        df[col] = df[col].astype("float64")
    return df


def _ref_fill_values(train) -> dict:
    out = {}
    for col in train.columns:
        if pd.api.types.is_numeric_dtype(train[col]):
            out[col] = float(train[col].median())
        else:
            out[col] = train[col].mode()[0]
    return out


def _guarded(fn, label: str, *frames):
    """Call fn on copies, then complain if the caller's frames were edited."""
    watched = [(f, f.copy()) for f in frames if isinstance(f, (pd.DataFrame, pd.Series))]
    got = _call(fn, label, *frames)
    for f, o in watched:
        same = f.equals(o) and f.index.equals(o.index) and str(f.dtypes) == str(o.dtypes)
        if isinstance(f, pd.DataFrame):
            same = same and f.columns.equals(o.columns)
        if not same:
            raise Fail(f"`{label}` changed a frame it was given (its holes or columns are different now).",
                       hint="Work on a copy: out = df.copy(), or use methods that return new frames "
                            "(fillna/dropna without inplace=True).")
    return got


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Survey the holes — `missing_share` per column")
def _share(ctx):
    missing_share = _fn(ctx, "missing_share")
    full = _frame(3101, 6, holes=0.0).drop(columns=["returned"])
    for df in (_frame(3102, 20), _frame(3103, 7, holes=0.45), full):
        label = f"missing_share(frame of shape {df.shape})"
        got = _need(_guarded(missing_share, label, df), pd.Series, label)
        want = df.isna().mean()
        if [str(i) for i in got.index] != [str(c) for c in df.columns]:
            raise Fail(f"`{label}` is indexed by {_short(list(got.index), 90)}; expected one entry per column: "
                       f"{list(df.columns)}.", hint="df.isna().mean() works column by column and keeps their names.")
        if _differs(got, want).any():
            i = int(np.argmax(_differs(got, want)))
            col = df.columns[i]
            hint = "The fraction is (number missing) / (number of rows): df.isna().mean()."
            if math.isclose(float(got.iloc[i]), float(df[col].isna().sum()), abs_tol=1e-9) and want.iloc[i]:
                hint = "That's a COUNT. Divide by len(df), or use .mean() instead of .sum()."
            elif float(got.iloc[i]) == 0 and want.iloc[i]:
                hint = "Your test never sees a hole. x == np.nan is always False; use isna()."
            raise Fail(f"`{label}`[{col!r}] is {_cell(got.iloc[i])}; expected {_cell(want.iloc[i])}.", hint=hint)


@MISSION.check("Type repair — `to_number` turns junk into NaN")
def _to_number(ctx):
    to_number = _fn(ctx, "to_number")
    rng = random.Random(3201)
    values = [rng.choice([str(rng.randint(0, 40)), f"{rng.uniform(-5, 50):.2f}", f" {rng.randint(1, 9)}",
                          rng.choice(JUNK)]) for _ in range(14)]
    values[0], values[1] = "0", rng.choice(JUNK[:3])
    cases = [pd.Series(values, index=range(900, 900 + 14 * 3, 3), name="hours"),
             pd.Series(["7", "1e2", "-3.5"], name="rad_level"),
             pd.Series(["?", "n/a"], name="haul_kg")]
    for s in cases:
        label = f"to_number({_short(s.tolist(), 70)})"
        got = _need(_guarded(to_number, label, s), pd.Series, label)
        want = pd.to_numeric(s, errors="coerce").astype("float64")
        if not pd.api.types.is_numeric_dtype(got) or pd.api.types.is_bool_dtype(got):
            raise Fail(f"`{label}` still returns {got.dtype} values, not numbers.",
                       hint="pd.to_numeric(series, errors=\"coerce\") returns float64.")
        if len(got) != len(want) or list(got.index) != list(want.index):
            raise Fail(f"`{label}` has {len(got)} values labelled {_short(list(got.index), 60)}; expected the "
                       f"same {len(want)} labels as the input.",
                       hint="Convert in place of each value; don't drop the junk rows here.")
        bad = _differs(got, want)
        if bad.any():
            i = int(np.argmax(bad))
            hint = "Numbers parse to floats; everything else becomes NaN."
            if math.isnan(want.iloc[i]) and float(got.iloc[i]) == 0:
                hint = "Junk isn't zero. Zero hours is a real measurement; unknown is NaN. Don't fill here."
            raise Fail(f"`{label}`: {s.iloc[i]!r} became {_cell(got.iloc[i])}; expected {_cell(want.iloc[i])}.",
                       hint=hint)
        if got.name != s.name:
            raise Fail(f"`{label}` lost the column name {s.name!r} (it's {got.name!r}).",
                       hint="pd.to_numeric keeps the name; building a new Series by hand doesn't.")


@MISSION.check("Keep the evidence — `drop_unlabeled` drops only unlabeled rows")
def _drop(ctx):
    drop_unlabeled = _fn(ctx, "drop_unlabeled")
    for seed, target in ((3301, "returned"), (3302, "haul_kg")):
        df = _frame(seed, 18, holes=0.3)
        label = f"drop_unlabeled(frame, {target!r})"
        got = _need(_guarded(drop_unlabeled, label, df, target), pd.DataFrame, label)
        want = df.dropna(subset=[target])
        if len(got) == len(df.dropna()) and len(got) < len(want):
            raise Fail(f"`{label}` kept {len(got)} of {len(df)} rows; only {len(df) - len(want)} have no label, "
                       f"so {len(want)} should survive.",
                       hint="dropna() with no arguments drops a row for ANY hole. Only the label matters here: "
                            "dropna(subset=[target]).")
        _same_frame(got, want, label, hint="Drop exactly the rows where the target is missing; keep everything else.")


@MISSION.check("Remember the holes — `add_missing_flags`")
def _flags(ctx):
    add_missing_flags = _fn(ctx, "add_missing_flags")
    df = _frame(3401, 16, holes=0.3)
    for cols in (["rad_level", "sector"], ["haul_kg"], []):
        label = f"add_missing_flags(frame, {cols})"
        got = _need(_guarded(add_missing_flags, label, df, list(cols)), pd.DataFrame, label)
        want = df.copy()
        for col in cols:
            want[f"{col}_missing"] = df[col].isna().astype(int)
        for col in cols:
            name = f"{col}_missing"
            if name in got.columns and name in want.columns and not got[name].isna().any():
                values = set(pd.unique(got[name].astype("float64")))
                if not values <= {0.0, 1.0}:
                    raise Fail(f"`{label}`[{name!r}] holds {_short(sorted(values), 60)}; flags are 0 or 1.",
                               hint="df[col].isna().astype(int)")
        _same_frame(got, want, label,
                    hint="Copy the frame, then add f\"{col}_missing\" = df[col].isna().astype(int) for each col, in order. "
                         "Leave the holes in the original columns alone.")


@MISSION.check("Train statistics — `fit_fill_values` (median / most common)")
def _fit(ctx):
    fit_fill_values = _fn(ctx, "fit_fill_values")
    train = _frame(3501, 25).drop(columns=["returned"])
    train.loc[train.index[0], "haul_kg"] = 999.0          # one wild reading: the median shrugs, the mean doesn't
    tied = pd.DataFrame({"crew": ["TERN", "KITE", None, "TERN", "KITE", "MOTH"],
                         "hours": [4.0, np.nan, 10.0, 8.0, np.nan, 6.0]})
    for df in (train, tied):
        label = f"fit_fill_values(frame of shape {df.shape})"
        got = _guarded(fit_fill_values, label, df)
        if not isinstance(got, dict):
            raise Fail(f"`{label}` returned {_show(got)}, not a dict.",
                       hint="Return {column: fill value} for every column, e.g. {\"hours\": 12.0, \"crew\": \"KITE\"}.")
        want = _ref_fill_values(df)
        for col, value in want.items():
            if col not in got:
                raise Fail(f"`{label}` has no fill value for {col!r}. Keys: {_short(sorted(map(str, got)), 90)}.",
                           hint="One entry per column of train, numeric or not.")
            mine = got[col]
            if isinstance(value, float):
                try:
                    ok = math.isclose(float(mine), value, rel_tol=1e-9, abs_tol=1e-9)
                except (TypeError, ValueError):
                    ok = False
                if not ok:
                    hint = "Numbers get the median of the training column: train[col].median() (it skips NaN)."
                    try:
                        if math.isclose(float(mine), float(df[col].mean()), rel_tol=1e-9):
                            hint = ("That's the mean. One 999 kg reading dragged it; the median ignores outliers. "
                                    "Use train[col].median().")
                        elif math.isnan(float(mine)):
                            hint = "NaN in, NaN out: np.median doesn't skip holes. pandas' train[col].median() does."
                    except (TypeError, ValueError):
                        pass
                    raise Fail(f"`{label}`[{col!r}] is {_cell(mine)}; expected the median {_cell(value)}.", hint=hint)
            elif mine != value:
                hint = "Categories get the most common training value: train[col].mode()[0]."
                if col == "crew" and df is tied:
                    hint = ("KITE and TERN are tied. .mode() returns every tied value, sorted; take the first: "
                            "train[col].mode()[0].")
                raise Fail(f"`{label}`[{col!r}] is {_cell(mine)}; expected {_cell(value)}.", hint=hint)


@MISSION.check("CORRUPTED CODE — `impute` fills test with TRAIN values")
def _impute(ctx):
    impute = _fn(ctx, "impute")
    train = _frame(3601, 24).drop(columns=["returned"])
    test = _frame(3602, 12, holes=0.35, shift=3.0).drop(columns=["returned"])
    label = "impute(train, test)"
    got = _guarded(impute, label, train, test)
    if not isinstance(got, tuple) or len(got) != 2:
        raise Fail(f"`{label}` returned {_show(got)}; expected a pair (train_filled, test_filled).",
                   hint="return train_filled, test_filled")
    tr, te = (_need(g, pd.DataFrame, f"{label}[{i}]") for i, g in enumerate(got))
    values = _ref_fill_values(train)
    _same_frame(tr, train.fillna(values), f"{label}[0] (train)",
                hint="Fill train with the values learned from train.")
    if te.isna().any().any():
        col = te.columns[int(np.argmax(te.isna().any().to_numpy()))]
        raise Fail(f"The filled test frame still has holes in {col!r}.",
                   hint="Every column of test needs a fill value learned from train.")
    own = test.fillna(_ref_fill_values(test))
    pooled = test.fillna(_ref_fill_values(pd.concat([train, test])))
    want = test.fillna(values)
    if not _differs(te["rad_level"], own["rad_level"]).any() and _differs(te["rad_level"], want["rad_level"]).any():
        raise Fail("LEAKAGE: the test set was filled with ITS OWN medians and modes. In production you never see "
                   "the future's statistics; your validation score would be quietly optimistic.",
                   hint="Learn the fill values ONCE, from train, and use that same dict for both frames.")
    if not _differs(te["rad_level"], pooled["rad_level"]).any() and _differs(te["rad_level"], want["rad_level"]).any():
        raise Fail("LEAKAGE: the fill values were computed on train and test together, so test rows shaped the "
                   "numbers used to fill them.", hint="Fit on train only: fit_fill_values(train).")
    _same_frame(te, want, f"{label}[1] (test)", hint="Fill test with the values learned from train.")
