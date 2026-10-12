"""LAB NP02 // MASKS — indexing, slicing, boolean masks, fancy indexing, views vs copies (TENSOR SUTRAS, §13)."""
from __future__ import annotations

import ast
import warnings

from engine.mission import Fail, Mission

try:
    import numpy as np
except ImportError:      # the Lab shows `pip install numpy`; the module must still import without it
    np = None


MISSION = Mission(
    id="NP02",
    slug="np02_masks",
    title="MASKS",
    concept="Indexing, slicing & boolean masks",
    enemy="MASQUE.daemon",
    xp=160,
    par_seconds=30 * 60,
    tier=3,
    concepts=("numpy", "conditionals"),
    requires=("numpy",),
    timeout=15,
    run_as_main=False,
    enemy_art="""\
   ▄▄▀▀▀▀▀▀▀▀▄▄
  █ ▄▄▄    ▄▄▄ █
  █ ▀█▀ ░░ ▀█▀ █
  █    ▄▀▀▄    █
   ▀▄ ▀▄▄▄▄▀ ▄▀
     ▀▀▄▄▄▄▀▀""",
    briefing="""\
**MOTHER ADA** unrolls the Order's old census of the Lower Stacks. The Null Event burned holes
straight through it: cells of ash where numbers used to be. Some rows were never labelled. Some
were labelled by people who weren't sure.

"A model eats whatever you feed it," she says. "Ash included. So you choose what goes in. Choose
with a mask, not with a guess."

**MASQUE.daemon** got to the slate first. It wears the rows like faces, and it writes through any
window you open onto the data, so the original rots while you look at a copy that isn't one.

**Cut features from labels, mask out the ash, and seal every window MASQUE left open.**
""",
    why="""\
Selecting rows is half of real data work. Dropping incomplete samples, keeping only labelled ones,
pulling one class out for a sanity check, gathering a random mini-batch: every one of these is a
slice, a boolean mask or an index array.

```python
X, y = data[:, :-1], data[:, -1]                  # features | label
keep = ~np.isnan(X).any(axis=1) & (y != -1)       # complete AND labelled
X, y = X[keep], y[keep]                           # one mask, both arrays
batch = X[rng.integers(0, len(X), size=32)]       # fancy indexing: a mini-batch
```

The dangerous part is quiet: a slice is a **view** that shares memory with the original. Write into
it and you have edited your raw dataset, and every experiment after that is built on the edit.
PyTorch tensors behave the same way (`t[:5]` is a view; `.clone()` copies), so this habit
transfers directly.
""",
    manual="""\
**1. Slicing picks rows and columns: `a[rows, cols]`.**

```python
import numpy as np
data = np.array([[0.2, 1.5, 1.0],
                 [0.7, 0.1, 0.0],
                 [0.9, 2.2, 1.0]])
X = data[:, :-1]     # every row, all columns but the last  -> shape (3, 2)
y = data[:, -1]      # every row, only the last column      -> shape (3,)
data[:, -1:]         # shape (3, 1)  a slice KEEPS the axis; a single index drops it
data[1:]             # rows 1 and 2
```

**2. A boolean mask is an array of True/False the same length as the axis it filters.**

```python
y = np.array([1, -1, 0, 1])
y != -1                       # array([ True, False,  True,  True])
X = np.arange(8).reshape(4, 2)
X[y != -1]                    # rows 0, 2, 3: whole rows survive
conf = np.array([0.9, 0.4, 0.5, 0.7])
X[(y != -1) & (conf >= 0.5)]  # combine with & | ~, and ALWAYS wrap each condition in ( )
```

`and`/`or` don't work on arrays (they want ONE True or False, so numpy raises "truth value of an
array is ambiguous"). Without the parentheses, `y != -1 & conf >= 0.5` is parsed as
`y != (-1 & conf) >= 0.5`, because `&` binds tighter than comparisons.

**3. NaN is never equal to anything, not even itself.** Use `np.isnan`:

```python
X = np.array([[1.0, np.nan], [3.0, 4.0]])
X == np.nan                    # all False: useless
np.isnan(X)                    # [[False, True], [False, False]]
np.isnan(X).any(axis=1)        # per ROW: [True, False]
X[~np.isnan(X).any(axis=1)]    # [[3., 4.]]  rows with no NaN at all
X[~np.isnan(X)]                # [1., 3., 4.]  cells, not rows: the table is gone
```

**4. Fancy indexing: index with an array of positions.** It can repeat and reorder, and it always
builds a NEW array. Pair two index arrays to pick one cell per row:

```python
y = np.array([2, 0, 1])
np.array([10, 20, 30])[[2, 2, 0]]     # array([30, 30, 10])
out = np.zeros((3, 4))
out[np.arange(3), y] = 1              # row 0 col 2, row 1 col 0, row 2 col 1
np.eye(4)[y]                          # the same one-hot rows, in one line
```

**5. Views vs copies. Common mistake:** editing a slice and thinking the original is safe.

```python
X = np.array([[-1.0, 2.0], [3.0, -4.0], [5.0, 6.0]])
window = X[0:2]          # a VIEW: same memory as X
window[window < 0] = 0   # ...so this just rewrote X itself
np.shares_memory(window, X)   # True
safe = X[0:2].copy()     # an independent copy; edit freely
```

Slices are views. Boolean masks and fancy indexing return copies. When unsure, `.copy()`.

**6. The same moves elsewhere.** PyTorch: `t[:, :-1]`, `t[mask]`, `t[idx]`, and
`F.one_hot(labels, num_classes)`; `t.clone()` is `.copy()`. pandas: `df[df["y"] != -1]`,
`df.dropna()`. scikit-learn's `OneHotEncoder` builds the same matrix for categorical features.
""",
    starter='''
"""
==============================================================================
  LAB NP02 // MASKS                                     TARGET: MASQUE.daemon
==============================================================================
  The census is burned and half-labelled. Write the functions below; the
  grader calls them with FRESH arrays every time, so they must work for any
  shape, not just the examples. Save, then HACK from the Lab.
"""
import numpy as np


# -- OBJECTIVE 1 -------------------------------------------------------------
def split_xy(data):
    """Split a table into (X, y): every column but the last, and the last column.

    data has shape (n, d). Return X with shape (n, d - 1) and y with shape (n,).
    split_xy(np.array([[0.2, 1.5, 1.0], [0.7, 0.1, 0.0]]))
        -> (array([[0.2, 1.5], [0.7, 0.1]]), array([1., 0.]))
    """
    # TODO: slicing. Careful: y must be 1-D, shape (n,), not (n, 1).
    pass


# -- OBJECTIVE 2 -------------------------------------------------------------
def drop_burned(X, y):
    """Return (X, y) without the rows of X that contain ANY NaN. Keep row order.

    X = [[1, nan], [3, 4], [nan, nan]], y = [0, 1, 2]  ->  ([[3, 4]], [1])
    If every row is burned, return shapes (0, d) and (0,).
    """
    # TODO: one boolean mask per row (np.isnan + .any(axis=1)), applied to BOTH arrays.
    pass


# -- OBJECTIVE 3 -------------------------------------------------------------
def trusted(X, y, conf, min_conf):
    """Keep rows that are labelled (y != -1) AND confident (conf >= min_conf).

    Returns (X_kept, y_kept). A confidence exactly equal to min_conf counts.
    """
    # TODO: two conditions, combined with &, each wrapped in parentheses.
    pass


# -- OBJECTIVE 4 // CORRUPTED CODE -------------------------------------------
def sensor_window(X, start, stop):
    """Return rows start..stop-1 of X with every negative reading replaced by 0.

    X itself must NOT change: the raw census is evidence.
    """
    # MASQUE wrote this. The answer looks right, and the raw census rots
    # behind it. Find out why (hint: what does slicing return?) and fix it.
    window = X[start:stop]
    window[window < 0] = 0
    return window


# -- OBJECTIVE 5 -------------------------------------------------------------
def one_hot(y, n_classes):
    """Turn integer labels into one-hot rows: shape (len(y), n_classes), floats.

    one_hot(np.array([2, 0]), 3)  ->  [[0., 0., 1.], [1., 0., 0.]]
    one_hot(np.array([], dtype=int), 3).shape  ->  (0, 3)
    No Python loops: fancy indexing does it in one move.
    """
    # TODO: np.zeros(...) then out[np.arange(len(y)), y] = 1   (or np.eye)
    pass


# Try your rites here. The grader ignores this block; `python np02_masks.py` runs it.
if __name__ == "__main__":
    data = np.array([[0.2, 1.5, 1.0], [0.7, 0.1, 0.0]])
    print(split_xy(data))
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Every dataset is a decision about what to leave out. Most people make that decision by accident. You will make it on purpose."},
            {"speaker": "ada", "mood": "neutral",
             "text": "A mask is a question asked of every row at once. True stays, False goes. Ask precisely."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Careful with MASQUE, {callsign}. It hides in the difference between a view and a copy."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "'Truth value of an array is ambiguous.' You asked numpy one question about many rows. Use & and parentheses, not 'and'."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "IndexError means you asked for a row or column that isn't there. Print the shape first, then index."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Script went down before the masks ran. The COMBAT LOG names the line."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Count the rows you returned, then count the labels. If those numbers differ, your X and y no longer describe the same people."}],
            [{"speaker": "ada", "mood": "cold",
              "text": "NaN is not equal to NaN. It isn't equal to anything. That is the whole point of it. Ask np.isnan."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Check whether the caller's array survived your function. MASQUE lives in slices that write back."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Clean rows, aligned labels, and the raw census untouched. That's the second sutra: what you leave out is a choice."},
            {"speaker": "ada", "mood": "neutral",
             "text": "Before the Null Event, a lab I knew 'cleaned' its data in place. Six months of results stood on a slice nobody copied."},
            {"speaker": "cipher", "mood": "warm",
             "text": "MASQUE has no faces left to wear, {callsign}. The census holds."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

_LOOPS = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_HIDDEN_LOOPS = {"vectorize", "apply_along_axis", "apply_over_axes", "frompyfunc", "map", "fromiter"}


def _defs(ctx) -> dict:
    return {n.name: n for n in ctx.tree.body if isinstance(n, ast.FunctionDef)}


def _fn(ctx, name: str):
    obj = ctx.ns.get(name)
    if callable(obj):
        return obj
    if ctx.crashed and name in _defs(ctx):
        raise Fail(f"`{name}` is in your file, but the script crashed before Python defined it. "
                   "Fix the crash in the COMBAT LOG first.")
    raise Fail(f"No function named `{name}` found.",
               hint=f"Keep the starter's  def {name}(...):  line; spelling and underscores must match.")


def _reach(ctx, name: str) -> list:
    """`name` plus every top-level helper function it calls (so a loop can't hide in a helper)."""
    defs, seen, todo = _defs(ctx), [], [name]
    while todo:
        cur = todo.pop()
        if cur in seen or cur not in defs:
            continue
        seen.append(cur)
        todo += [n.func.id for n in ast.walk(defs[cur]) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    return [defs[n] for n in seen]


def _no_loops(ctx, name: str, why: str) -> None:
    for node in _reach(ctx, name):
        for sub in ast.walk(node):
            hidden = isinstance(sub, ast.Call) and (
                (isinstance(sub.func, ast.Name) and sub.func.id in _HIDDEN_LOOPS)
                or (isinstance(sub.func, ast.Attribute) and sub.func.attr in _HIDDEN_LOOPS))
            if isinstance(sub, _LOOPS) or hidden:
                kind = "a hidden loop" if hidden else ("a comprehension" if not isinstance(
                    sub, (ast.For, ast.AsyncFor, ast.While)) else f"a `{type(sub).__name__.lower()}` loop")
                raise Fail(f"`{name}` uses {kind} (line {sub.lineno}). This layer only opens to array operations.",
                           hint=why)


def _short(text, limit: int = 150) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _show(value) -> str:
    if isinstance(value, np.ndarray):
        body = np.array2string(value, precision=3, threshold=10, edgeitems=2, separator=", ",
                               suppress_small=True)
        return _short(f"{' '.join(body.split())} (shape {value.shape})", 140)
    return _short(repr(value), 140)


def _scalar(v) -> str:
    v = np.asarray(v)
    if v.dtype.kind == "b":
        return str(bool(v))
    if v.dtype.kind in "iu":
        return str(int(v))
    if v.dtype.kind == "f":
        return f"{float(v):.6g}"
    return _short(repr(v.item()))


def _crash_hint(exc: BaseException) -> str:
    msg = str(exc)
    if "truth value of an array" in msg:
        return ("`and`/`or`/`if` want ONE True/False, but you gave numpy a whole array. "
                "Combine masks with & | ~ and wrap each condition: (y != -1) & (conf >= min_conf).")
    if isinstance(exc, IndexError) and "boolean index did not match" in msg:
        return "A boolean mask must have one entry per row of the array it filters. Build it from the same rows."
    if isinstance(exc, IndexError):
        return "An index is out of range for that axis. Print a.shape and the index you used."
    if "could not be broadcast" in msg:
        return "Two arrays with incompatible shapes met. Print both shapes just before that line."
    if isinstance(exc, (AttributeError, TypeError)) and "NoneType" in msg:
        return "Something is None: a function with no `return` gives back None."
    return "Call the function yourself at the bottom of your file with a small array and print the result."


def _call(fn, label: str, *args):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return fn(*args)
    except Fail:
        raise
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {_short(exc)}", hint=_crash_hint(exc))


def _array(got, label: str):
    if got is None:
        raise Fail(f"`{label}` returned None.",
                   hint="A function without a `return` line gives back None. Return the array you built.")
    if not isinstance(got, np.ndarray):
        raise Fail(f"`{label}` returned a {type(got).__name__}, not a numpy array.",
                   hint="Stay in numpy end to end: slicing and masking an array gives back an array.")
    return got


def _pair(got, label: str):
    if not isinstance(got, (tuple, list)) or len(got) != 2:
        raise Fail(f"`{label}` returned {_short(repr(got), 80)}; expected a pair (X, y).",
                   hint="End with  return X, y  (a tuple of two arrays).")
    return _array(got[0], label + "[0]"), _array(got[1], label + "[1]")


def _mismatch(got, want, label: str, hint: str = "", tol: float = 1e-9) -> None:
    bad = ~np.isclose(got.astype(np.float64), want.astype(np.float64), rtol=tol, atol=tol, equal_nan=True)
    if bad.any():
        idx = tuple(int(i) for i in np.argwhere(bad)[0])
        raise Fail(f"`{label}` is wrong at index {idx}: got {_scalar(got[idx])}, expected {_scalar(want[idx])}.",
                   hint=hint)


# ── references ──────────────────────────────────────────────────────────────────

def _ref_drop(X, y):
    keep = ~np.isnan(X).any(axis=1)
    return X[keep], y[keep]


def _ref_trusted(X, y, conf, min_conf):
    keep = (y != -1) & (conf >= min_conf)
    return X[keep], y[keep]


def _ref_one_hot(y, n_classes):
    out = np.zeros((len(y), n_classes))
    out[np.arange(len(y)), y] = 1.0
    return out


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Cut the slate — `split_xy` separates features from labels")
def _split(ctx):
    split_xy = _fn(ctx, "split_xy")
    rng = np.random.default_rng(1201)
    n, d = int(rng.integers(5, 10)), int(rng.integers(3, 7))
    table = np.round(rng.normal(0, 3, size=(n, d)), 2)
    table[:, -1] = rng.integers(0, 3, size=n)
    cases = [table, table[2:3].copy(), np.round(rng.normal(0, 1, size=(4, 2)), 2)]
    for data in cases:
        label = f"split_xy(table of shape {data.shape})"
        original = data.copy()
        X, y = _pair(_call(split_xy, label, data), label)
        n_rows = original.shape[0]
        if y.shape == (n_rows, 1):
            raise Fail(f"`{label}` returned y with shape {y.shape}; expected ({n_rows},).",
                       hint="data[:, -1:] is a slice, so it keeps a column axis of width 1. "
                            "A single index, data[:, -1], drops that axis.")
        if y.shape != (n_rows,):
            raise Fail(f"`{label}` returned y with shape {y.shape}; expected ({n_rows},).",
                       hint="y is the last column: one label per row.")
        if X.shape != (n_rows, original.shape[1] - 1):
            hint = "X is every column except the last: data[:, :-1]."
            if X.shape == original.shape:
                hint = "X still contains the label column. A model given its own answer learns nothing. Use data[:, :-1]."
            raise Fail(f"`{label}` returned X with shape {X.shape}; expected {(n_rows, original.shape[1] - 1)}.",
                       hint=hint)
        _mismatch(X, original[:, :-1], label + "[0]", hint="X should be the first d-1 columns, in order.")
        _mismatch(y, original[:, -1], label + "[1]", hint="y should be the LAST column (index -1).")


@MISSION.check("Burned rows — `drop_burned` removes every row containing NaN")
def _drop(ctx):
    drop_burned = _fn(ctx, "drop_burned")
    rng = np.random.default_rng(1202)
    n, d = int(rng.integers(8, 13)), int(rng.integers(3, 6))
    X = np.round(rng.normal(0, 5, size=(n, d)), 2)
    burned = rng.choice(n, size=n // 3, replace=False)
    X[burned, rng.integers(0, d, size=len(burned))] = np.nan
    X[burned[0], :] = np.nan                       # one row burned completely
    y = rng.integers(0, 4, size=n)
    clean = np.round(rng.normal(0, 1, size=(4, d)), 2)
    ash = np.full((3, d), np.nan)
    ash[0, 0] = 1.0                                 # partly burned still counts as burned
    cases = [(X, y), (clean, np.arange(4)), (ash, np.array([7, 8, 9]))]
    for Xc, yc in cases:
        label = f"drop_burned(X of shape {Xc.shape} with {int(np.isnan(Xc).any(axis=1).sum())} burned rows, y)"
        gX, gy = _pair(_call(drop_burned, label, Xc.copy(), yc.copy()), label)
        wX, wy = _ref_drop(Xc, yc)
        if gX.ndim == 1 and Xc.ndim == 2:
            raise Fail(f"`{label}` returned a 1-D X of shape {gX.shape}: the table lost its rows.",
                       hint="X[~np.isnan(X)] keeps CELLS. To keep ROWS, reduce the mask per row first: "
                            "np.isnan(X).any(axis=1).")
        if gX.shape != wX.shape:
            hint = "A row is burned if ANY of its cells is NaN."
            if gX.shape[0] == len(Xc) and len(wX) < len(Xc):
                hint = "Nothing was dropped. `x == np.nan` is always False (NaN equals nothing). Use np.isnan(X)."
            elif gX.shape[0] == int((~np.isnan(Xc).all(axis=1)).sum()):
                hint = "You dropped only rows where ALL cells are NaN. One NaN is enough: use .any(axis=1)."
            raise Fail(f"`{label}` kept X of shape {gX.shape}; expected {wX.shape}.", hint=hint)
        if gy.shape != wy.shape:
            raise Fail(f"`{label}` kept {len(gX)} rows of X but {gy.shape[0] if gy.ndim else gy.size} labels.",
                       hint="Filter y with the SAME mask as X, or every label after the first gap belongs to the wrong row.")
        _mismatch(gX, wX, label + "[0]", hint="Keep the clean rows in their original order.")
        _mismatch(gy, wy, label + "[1]", hint="Each label must stay with its row: y[mask].")


@MISSION.check("Trust filter — `trusted` combines two masks")
def _trusted(ctx):
    trusted = _fn(ctx, "trusted")
    rng = np.random.default_rng(1203)
    n = int(rng.integers(12, 18))
    X = np.round(rng.normal(0, 2, size=(n, 3)), 2)
    y = rng.integers(-1, 3, size=n)
    conf = np.round(rng.random(n), 2)
    labelled = np.sort(conf[y != -1])
    min_conf = float(labelled[len(labelled) // 2])   # one labelled row sits exactly on the line
    cases = [(X, y, conf, min_conf), (X[:4], np.full(4, -1), conf[:4], 0.0)]
    for args in cases:
        Xc, yc, cc, t = args
        label = f"trusted(X of shape {Xc.shape}, y={_show(yc)}, conf, min_conf={t:g})"
        gX, gy = _pair(_call(trusted, label, Xc.copy(), yc.copy(), cc.copy(), t), label)
        wX, wy = _ref_trusted(Xc, yc, cc, t)
        if gX.shape != wX.shape or gy.shape != wy.shape:
            hint = "Keep rows where (y != -1) & (conf >= min_conf). Both conditions, both arrays."
            if len(gy) == int(((yc != -1) & (cc > t)).sum()):
                hint = "A confidence EQUAL to min_conf counts as trusted: >= , not >."
            elif len(gy) == int((yc != -1).sum()):
                hint = "You kept every labelled row. The confidence condition is missing."
            elif len(gy) == int((cc >= t).sum()):
                hint = "You kept unlabelled rows (y == -1). Add the label condition with &."
            elif len(gy) == int(((yc != -1) | (cc >= t)).sum()):
                hint = "| keeps a row if EITHER condition holds. Trusted rows need both: &."
            raise Fail(f"`{label}` kept {len(gX)} rows; expected {len(wX)}.", hint=hint)
        _mismatch(gX, wX, label + "[0]", hint="Apply one mask to X and y, keeping row order.")
        _mismatch(gy, wy, label + "[1]", hint="Apply the same mask to y.")


@MISSION.check("CORRUPTED CODE — `sensor_window` must not write through a view")
def _window(ctx):
    sensor_window = _fn(ctx, "sensor_window")
    rng = np.random.default_rng(1204)
    n, d = int(rng.integers(8, 12)), int(rng.integers(3, 5))
    X = np.round(rng.normal(0, 4, size=(n, d)), 2)
    start, stop = int(rng.integers(1, 3)), int(rng.integers(5, n))
    X[start, 0] = -abs(X[start, 0]) - 1.0          # make sure the window holds a negative
    for s, e in ((start, stop), (0, n), (3, 3)):
        label = f"sensor_window(X of shape {X.shape}, {s}, {e})"
        caller = X.copy()
        got = _array(_call(sensor_window, label, caller, s, e), label)
        if not np.array_equal(caller, X):
            row = int(np.argwhere(caller != X)[0][0])
            raise Fail(f"`{label}` changed the caller's X: row {row} was {_show(X[row])}, now {_show(caller[row])}.",
                       hint="X[start:stop] is a VIEW: it shares memory with X, so writing into it rewrites X. "
                            "Take a copy first: X[start:stop].copy().")
        want = np.where(X[s:e] < 0, 0.0, X[s:e])
        if got.shape != want.shape:
            raise Fail(f"`{label}` returned shape {got.shape}; expected {want.shape}.",
                       hint="Rows start up to (not including) stop: X[start:stop].")
        _mismatch(got, want, label, hint="Every negative reading becomes 0; everything else is unchanged.")
        if got.size and np.shares_memory(got, caller):
            raise Fail(f"`{label}` returns an array that still shares memory with X.",
                       hint="The next person to edit your result would edit the census. Return a copy.")


@MISSION.check("Fancy indexing — `one_hot` lights one cell per row")
def _one_hot(ctx):
    one_hot = _fn(ctx, "one_hot")
    _no_loops(ctx, "one_hot", "Index with two arrays at once: out[np.arange(len(y)), y] = 1. Or np.eye(n_classes)[y].")
    rng = np.random.default_rng(1205)
    k = int(rng.integers(4, 7))
    y = rng.integers(0, k - 1, size=int(rng.integers(6, 10)))    # the last class never appears
    cases = [(y, k), (np.array([k - 1, 0, k - 1]), k), (np.array([], dtype=np.int64), k)]
    for yc, kc in cases:
        label = f"one_hot({_show(yc)}, {kc})"
        got = _array(_call(one_hot, label, yc.copy(), kc), label)
        want = _ref_one_hot(yc, kc)
        if got.shape != want.shape:
            hint = "One row per label, n_classes columns: np.zeros((len(y), n_classes))."
            if got.shape == (len(yc), int(yc.max()) + 1 if len(yc) else 0):
                hint = "The width is n_classes, not the largest label seen: a class can be missing from this batch."
            raise Fail(f"`{label}` returned shape {got.shape}; expected {want.shape}.", hint=hint)
        if got.dtype.kind != "f":
            raise Fail(f"`{label}` returned dtype {got.dtype}; expected floats.",
                       hint="Losses multiply one-hot rows with probabilities: build with np.zeros(...) (float64).")
        columns = np.zeros_like(want)
        columns[:, yc] = 1.0
        if len(yc) > 1 and not np.array_equal(columns, want) and np.array_equal(got, columns):
            raise Fail(f"`{label}` lit whole columns: {_show(got)}.",
                       hint="out[:, y] = 1 selects entire columns. Pair a row index with each label: "
                            "out[np.arange(len(y)), y] = 1.")
        _mismatch(got, want, label, hint="Row i has a single 1.0, in column y[i]; everything else is 0.")
