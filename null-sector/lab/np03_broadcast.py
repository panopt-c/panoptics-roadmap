"""LAB NP03 // BROADCAST — the broadcasting rules, and the shape bugs they hide (TENSOR SUTRAS, §13)."""
from __future__ import annotations

import ast
import warnings

from engine.mission import Fail, Mission

try:
    import numpy as np
except ImportError:      # the Lab shows `pip install numpy`; the module must still import without it
    np = None


MISSION = Mission(
    id="NP03",
    slug="np03_broadcast",
    title="BROADCAST",
    concept="Broadcasting rules",
    enemy="ECHO.choir",
    xp=160,
    par_seconds=35 * 60,
    tier=3,
    concepts=("numpy", "ml-math"),
    requires=("numpy",),
    timeout=15,
    run_as_main=False,
    enemy_art="""\
 ▄▀▄   ▄▀▄   ▄▀▄
 █○█ ▄ █○█ ▄ █○█
 ▀▄▀ █ ▀▄▀ █ ▀▄▀
  ║  ▀  ║  ▀  ║
 ≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈
  ))) ))) ))) )))""",
    briefing="""\
The Monastery's relay mast hums all night. **ECHO.choir** has nested in it: a daemon that takes one
voice and repeats it down every channel, until a single reading becomes a whole wall of false
agreement.

**MOTHER ADA** listens with her eyes closed. "Broadcasting," she says. "Numpy's mercy and its trap.
It stretches small arrays to fit big ones, so you never write the loop. But when shapes *almost*
fit, it stretches the wrong way and says nothing at all."

She chalks two shapes on the slate, `(8, 1)` and `(8,)`, and waits for you to say what they make.

**Learn the rule by hand, then make every stretch in the relay deliberate.**
""",
    why="""\
Broadcasting is how every feature-scaling step, bias add and distance matrix in ML is written:

```python
X_scaled = (X - X.mean(axis=0)) / X.std(axis=0)   # (n, d) with (d,): one rule per column
logits = X @ W + b                                # (n, k) plus (k,): bias on every row
D = ((A[:, None, :] - B[None, :, :]) ** 2).sum(-1)   # (m, n): all pairwise distances
```

It also causes the most expensive silent bug in the field. A regression model outputs predictions of
shape `(n, 1)`; the targets are `(n,)`. Subtract them and you get an `(n, n)` matrix, every
prediction minus every target. The loss is a number, training runs, and the model learns to predict
the mean. PyTorch prints a warning for exactly this (`Using a target size that is different to the
input size`) because it bit so many people. Knowing the rule lets you see it coming.
""",
    manual="""\
**1. The rule. Line the shapes up from the RIGHT and compare axis by axis.** Two sizes fit if they
are equal, or one of them is 1 (that axis is stretched). A missing axis on the left counts as 1.

```text
X      (5, 3)          A   (8, 1)          P   (4, 3)
mean      (3,)         B      (8,)         Q   (4,)       <- 3 vs 4: neither is 1
-----------------      -----------         -----------
result (5, 3)  ok      AB  (8, 8)  !!      ValueError: could not be broadcast
```

```python
import numpy as np
np.broadcast_shapes((5, 3), (3,))     # (5, 3)
np.broadcast_shapes((8, 1), (8,))     # (8, 8)   legal, and usually a bug
```

**2. Per-column statistics broadcast along rows for free.**

```python
X = np.array([[1.0, 200.0], [3.0, 400.0]])
mu = X.mean(axis=0)              # shape (2,): one mean per column
sd = X.std(axis=0)               # shape (2,)
(X - mu) / sd                    # (2, 2) with (2,) -> every row uses the same mu, sd
```

A constant column has `sd == 0`. scikit-learn's `StandardScaler` treats that as a scale of 1 so the
column becomes all zeros instead of NaN: `sd = np.where(sd == 0, 1.0, sd)`.

**3. Per-ROW statistics need the axis kept.** `X.sum(axis=1)` has shape `(n,)`, which lines up
with the COLUMNS of `(n, d)`. Keep it as a column instead:

```python
norms = np.linalg.norm(X, axis=1, keepdims=True)   # (n, 1)
X / norms                                          # (n, d) / (n, 1): each row by its own norm
X / np.linalg.norm(X, axis=1)    # (n, d) / (n,): crashes if n != d... and if n == d,
                                 # it silently divides COLUMN j by row j's norm
```

**4. Add an axis on purpose with `None` (alias `np.newaxis`).** That turns two 1-D arrays into a
table of every pair:

```python
a = np.array([1, 5, 9]); b = np.array([2, 3])
a[:, None]                 # shape (3, 1)
a[:, None] - b[None, :]    # shape (3, 2): a[i] - b[j] for every i, j
a - np.array([2, 3, 4])    # shape (3,): equal lengths pair up ONE-to-one instead
```

**5. Common mistake: the `(n, 1)` vs `(n,)` loss.**

```python
y_true = np.array([1.0, 2.0, 3.0])          # (3,)
y_pred = np.array([[1.1], [1.9], [3.2]])    # (3, 1): what X @ w gives when w is (d, 1)
((y_true - y_pred) ** 2).mean()             # 1.6366... nonsense from a (3, 3) matrix
((y_true - y_pred.ravel()) ** 2).mean()     # 0.02  the real error
```

Flatten both sides with `.ravel()` (or `.reshape(-1)`) and check the sizes match first.

**6. Elsewhere.** PyTorch broadcasts with exactly the same rule (`x.unsqueeze(1)` is `x[:, None]`;
`keepdim=True` is `keepdims=True`). `torch.nn.functional.normalize(x, dim=1)` and scikit-learn's
`preprocessing.normalize` do the row scaling of section 3, leaving all-zero rows at zero.
""",
    starter='''
"""
==============================================================================
  LAB NP03 // BROADCAST                                    TARGET: ECHO.choir
==============================================================================
  Make every stretch deliberate. The grader calls your functions with FRESH
  arrays, including square ones, where a wrong-axis stretch hides best.
  Save, then HACK from the Lab.
"""
import numpy as np


# -- OBJECTIVE 1 -------------------------------------------------------------
def broadcast_shape(a, b):
    """Apply the broadcasting rule BY HAND to two shape tuples.

    Return the result shape as a tuple of ints, or raise ValueError if the
    shapes can't broadcast. Plain Python only: no numpy in here.
    broadcast_shape((5, 3), (3,))   -> (5, 3)
    broadcast_shape((8, 1), (8,))   -> (8, 8)
    broadcast_shape((4, 3), (4,))   -> raises ValueError
    """
    # TODO: pad the shorter shape with 1s on the LEFT, then compare axis by axis.
    pass


# -- OBJECTIVE 2 -------------------------------------------------------------
def standardize(X):
    """Scale each COLUMN of X (n, d) to mean 0 and standard deviation 1.

    Use the population std (numpy's default, ddof=0). A constant column has
    std 0: treat its std as 1 so it becomes all zeros, never NaN.
    """
    # TODO: mean and std over axis 0, broadcast against X. No loops.
    pass


# -- OBJECTIVE 3 -------------------------------------------------------------
def abs_diff_table(a, b):
    """Every pairwise distance between two 1-D arrays: out[i, j] = |a[i] - b[j]|.

    abs_diff_table(np.array([1, 5]), np.array([2, 3, 9]))
        -> [[1, 2, 8], [3, 2, 4]]          shape (len(a), len(b))
    """
    # TODO: give a and b their own axes with None. No loops.
    pass


# -- OBJECTIVE 4 // CORRUPTED CODE -------------------------------------------
def unit_rows(X):
    """Scale each ROW of X to length 1 (L2 norm). All-zero rows stay zero."""
    # ECHO.choir tuned this. It crashes on some inputs and lies on others.
    return X / np.linalg.norm(X, axis=1)


# -- OBJECTIVE 5 -------------------------------------------------------------
def safe_mse(y_true, y_pred):
    """Mean squared error that can't be fooled by (n,) vs (n, 1) shapes.

    Either argument may arrive as shape (n,) or (n, 1). Flatten both. If they
    hold a different number of values, raise ValueError. Return a float.
    safe_mse(np.array([1., 2.]), np.array([[1.], [4.]]))  ->  2.0
    """
    # TODO: ravel both, check sizes, then the mean of squared differences.
    pass


# Try your rites here. The grader ignores this block; `python np03_broadcast.py` runs it.
if __name__ == "__main__":
    print(broadcast_shape((8, 1), (8,)))
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Two shapes walk into an operation. Line them up from the right. Equal, or one of them is 1. That is the entire law."},
            {"speaker": "ada", "mood": "neutral",
             "text": "The law is simple. Breaking it quietly is easy. Today you learn to hear when it's broken."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "ECHO.choir repeats whatever it hears, {callsign}. Feed it the wrong axis and it'll sing it back to every row."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "'Could not be broadcast.' Good. Numpy refused instead of guessing. Print both shapes and line them up from the right."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "A crash on one input and a pass on another often means a wrong axis that only fits square arrays."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Relay's down before the checks ran. The COMBAT LOG names the line."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "cold",
              "text": "A square matrix is a liar's favourite input. It fits every wrong axis. Test your code on one before you trust it."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "(n,) is not (n, 1). One is a list of numbers. The other is a column. Broadcasting treats them very differently."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Check the SHAPE of what you returned before the values. Most of these failures start there."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Every stretch deliberate. That's the third sutra: shapes agree from the right, or they don't agree at all."},
            {"speaker": "ada", "mood": "neutral",
             "text": "The Core's first loss function compared every prediction with every target. It trained for a month. It learned the average."},
            {"speaker": "cipher", "mood": "warm",
             "text": "The relay carries one voice per channel again, {callsign}. ECHO's gone quiet."},
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
    if v.dtype.kind in "iu":
        return str(int(v))
    if v.dtype.kind == "f":
        return f"{float(v):.6g}"
    return _short(repr(v.item()))


def _crash_hint(exc: BaseException) -> str:
    msg = str(exc)
    if "could not be broadcast" in msg:
        return ("Two shapes didn't fit. Line them up from the RIGHT: equal, or one is 1. "
                "For per-row values, keep the axis: keepdims=True gives (n, 1).")
    if isinstance(exc, (AttributeError, TypeError)) and "NoneType" in msg:
        return "Something is None: a function with no `return` gives back None."
    if isinstance(exc, IndexError):
        return "An index ran past the end of a shape. Pad the shorter shape with 1s on the left first."
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
                   hint="Array in, array out: arithmetic on numpy arrays already returns arrays.")
    return got


def _mismatch(got, want, label: str, hint: str = "", tol: float = 1e-7) -> None:
    bad = ~np.isclose(got.astype(np.float64), want.astype(np.float64), rtol=tol, atol=tol, equal_nan=False)
    if bad.any():
        idx = tuple(int(i) for i in np.argwhere(bad)[0])
        raise Fail(f"`{label}` is wrong at index {idx}: got {_scalar(got[idx])}, expected {_scalar(want[idx])}.",
                   hint=hint)


# ── references ──────────────────────────────────────────────────────────────────

def _ref_shape(a, b):
    try:
        return tuple(int(n) for n in np.broadcast_shapes(tuple(a), tuple(b)))
    except ValueError:
        return None


def _ref_standardize(X):
    sd = X.std(axis=0)
    return (X - X.mean(axis=0)) / np.where(sd == 0, 1.0, sd)


def _ref_unit_rows(X):
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    return X / np.where(norms == 0, 1.0, norms)


def _ref_mse(y_true, y_pred):
    return float(np.mean((np.ravel(y_true) - np.ravel(y_pred)) ** 2))


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("The law by hand — `broadcast_shape` matches numpy's rule")
def _rule(ctx):
    broadcast_shape = _fn(ctx, "broadcast_shape")
    for node in _reach(ctx, "broadcast_shape"):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in ("np", "numpy"):
                raise Fail(f"`broadcast_shape` uses numpy (line {sub.lineno}). This rite is the rule itself, by hand.",
                           hint="Plain Python: pad the shorter tuple with 1s on the left, then walk both from the right.")
    rng = np.random.default_rng(1301)
    cases = [((5, 3), (3,)), ((8, 1), (8,)), ((4, 3), (4,)), ((), (2, 3)), ((0,), (1,)), ((0,), (3,)),
             ((5, 1, 4), (3, 1)), ((2, 1), (1, 6))]
    for _ in range(6):                                   # fresh shapes every layer
        ndim = int(rng.integers(1, 5))
        full = [int(n) for n in rng.integers(2, 6, size=ndim)]
        a = [1 if rng.random() < 0.3 else n for n in full]
        b = [1 if rng.random() < 0.3 else n for n in full][int(rng.integers(0, ndim)):]
        if rng.random() < 0.3 and b:
            b[-1] = full[-1] + 1 if a[-1] != 1 else b[-1]          # sometimes a genuine clash
        cases.append((tuple(a), tuple(b)))
    for a, b in cases:
        label = f"broadcast_shape({a}, {b})"
        want = _ref_shape(a, b)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                got = broadcast_shape(a, b)
        except ValueError:
            if want is None:
                continue
            raise Fail(f"`{label}` raised ValueError, but these shapes DO broadcast to {want}.",
                       hint="Sizes fit when they are equal OR either one is 1. A missing axis on the left counts as 1.")
        except Exception as exc:  # noqa: BLE001
            raise Fail(f"`{label}` crashed: {type(exc).__name__}: {_short(exc)}", hint=_crash_hint(exc))
        if want is None:
            raise Fail(f"`{label}` returned {_short(repr(got), 60)}, but these shapes can't broadcast.",
                       hint="When two sizes differ and neither is 1, raise ValueError(...) like numpy does.")
        if not isinstance(got, tuple):
            raise Fail(f"`{label}` returned a {type(got).__name__}; shapes are tuples.",
                       hint="Build a list while you work, then return tuple(result).")
        if got != want:
            hint = "Compare from the RIGHT: the last axes line up first; pad the shorter shape with 1s on the left."
            if len(got) == len(want) and tuple(got) == tuple(max(x, y) for x, y in zip(a, b)) and len(a) != len(b):
                hint = "zip() pairs shapes from the LEFT and stops at the shorter one. Pad on the left first."
            if want and 0 in want:
                hint = "A size-0 axis is a real size: 0 against 1 gives 0 (an empty stretch), 0 against 3 is an error."
            raise Fail(f"`{label}` returned {got}; expected {want}.", hint=hint)


@MISSION.check("Tune the columns — `standardize` scales every feature")
def _standardize(ctx):
    standardize = _fn(ctx, "standardize")
    _no_loops(ctx, "standardize", "X.mean(axis=0) is one number per column; (X - mean) broadcasts it down every row.")
    rng = np.random.default_rng(1302)
    n, d = int(rng.integers(6, 10)), int(rng.integers(3, 5))
    X = rng.normal(0, 1, size=(n, d)) * rng.choice([1.0, 50.0, 1000.0], size=d) + rng.normal(0, 30, size=d)
    X[:, 1] = 7.0                                        # a dead sensor: constant column
    square = rng.normal(5, 3, size=(d, d))
    for Xc in (X, square, X[:1].copy()):
        label = f"standardize(X of shape {Xc.shape})"
        caller = Xc.copy()
        got = _array(_call(standardize, label, caller), label)
        want = _ref_standardize(Xc)
        if got.shape != want.shape:
            raise Fail(f"`{label}` returned shape {got.shape}; expected {want.shape}.",
                       hint="Scaling keeps the table's shape: (n, d) in, (n, d) out.")
        if np.isnan(got).any():
            raise Fail(f"`{label}` produced NaN at {tuple(int(i) for i in np.argwhere(np.isnan(got))[0])}.",
                       hint="0 / 0 is NaN. A constant column has std 0; replace that std with 1: np.where(sd == 0, 1.0, sd).")
        if np.allclose(got, (Xc - Xc.mean()) / (Xc.std() or 1.0)):
            raise Fail(f"`{label}` used ONE mean and std for the whole table.",
                       hint="Each feature has its own scale: X.mean(axis=0) and X.std(axis=0).")
        if Xc.shape[0] > 1:
            sd1 = Xc.std(axis=0, ddof=1)
            if np.allclose(got, (Xc - Xc.mean(axis=0)) / np.where(sd1 == 0, 1.0, sd1)):
                raise Fail(f"`{label}` divided by the sample std (ddof=1).",
                           hint="StandardScaler uses the population std, numpy's default: X.std(axis=0) with ddof=0.")
        _mismatch(got, want, label, hint="Per COLUMN: (X - X.mean(axis=0)) / X.std(axis=0). axis=1 would scale rows.")


@MISSION.check("Every pair — `abs_diff_table` builds a (len(a), len(b)) table")
def _table(ctx):
    abs_diff_table = _fn(ctx, "abs_diff_table")
    _no_loops(ctx, "abs_diff_table", "Give each array its own axis: a[:, None] - b[None, :] is a (len(a), len(b)) table.")
    rng = np.random.default_rng(1303)
    m = int(rng.integers(3, 6))
    a = np.round(rng.normal(0, 10, size=m), 1)
    cases = [(a, np.round(rng.normal(0, 10, size=m + 2), 1)),
             (a, np.round(rng.normal(0, 10, size=m), 1)),           # equal lengths: the silent pairing
             (np.array([]), np.array([1.0, 2.0]))]
    for ac, bc in cases:
        label = f"abs_diff_table({_show(ac)}, {_show(bc)})"
        got = _array(_call(abs_diff_table, label, ac.copy(), bc.copy()), label)
        want = np.abs(ac[:, None] - bc[None, :])
        if got.shape != want.shape:
            hint = "Turn a into a column (len(a), 1) and b into a row (1, len(b)); broadcasting fills the table."
            if got.shape == (len(ac),) and len(ac) == len(bc):
                hint = ("Equal lengths pair up one-to-one: a - b is a[i] - b[i] only. "
                        "For EVERY pair, add axes: a[:, None] - b[None, :].")
            elif got.shape == (len(bc), len(ac)):
                hint = "Rows belong to a, columns to b: a[:, None] - b[None, :], not the other way round."
            raise Fail(f"`{label}` returned shape {got.shape}; expected {want.shape}.", hint=hint)
        if (got < 0).any():
            raise Fail(f"`{label}` has negative entries: distances can't be negative.",
                       hint="Take the absolute value: np.abs(...).")
        _mismatch(got, want, label, hint="out[i, j] is |a[i] - b[j]|.")


@MISSION.check("CORRUPTED CODE — `unit_rows` divides each row by its own norm")
def _unit_rows(ctx):
    unit_rows = _fn(ctx, "unit_rows")
    _no_loops(ctx, "unit_rows", "np.linalg.norm(X, axis=1, keepdims=True) gives an (n, 1) column that divides each row.")
    rng = np.random.default_rng(1304)
    d = int(rng.integers(3, 6))
    square = np.round(rng.normal(0, 3, size=(d, d)), 2)                 # fits the wrong axis silently
    tall = np.round(rng.normal(0, 3, size=(d + 3, d)), 2)
    tall[1] = 0.0                                                       # an all-zero row
    for Xc in (square, tall):
        label = f"unit_rows(X of shape {Xc.shape})"
        got = _array(_call(unit_rows, label, Xc.copy()), label)
        want = _ref_unit_rows(Xc)
        if got.shape != want.shape:
            raise Fail(f"`{label}` returned shape {got.shape}; expected {want.shape}.",
                       hint="Row scaling keeps the shape of X.")
        echo = Xc / np.linalg.norm(Xc, axis=1)
        if Xc.shape[0] == Xc.shape[1] and np.allclose(got, echo):
            row_norms = np.linalg.norm(got, axis=1)
            raise Fail(f"`{label}` on a SQUARE matrix: rows came out with lengths {_show(np.round(row_norms, 3))}, "
                       "not 1. Column j was divided by row j's norm.",
                       hint="norm(X, axis=1) has shape (n,), which lines up with the COLUMNS of (n, d). "
                            "Keep it as a column: keepdims=True gives (n, 1).")
        if np.isnan(got).any():
            raise Fail(f"`{label}` produced NaN: an all-zero row has norm 0, and 0 / 0 is NaN.",
                       hint="Divide zero rows by 1 instead: np.where(norms == 0, 1.0, norms).")
        _mismatch(got, want, label, hint="Each row divided by ITS OWN L2 norm; all-zero rows stay zero.")


@MISSION.check("The classic shape bug — `safe_mse` flattens before it subtracts")
def _mse(ctx):
    safe_mse = _fn(ctx, "safe_mse")
    rng = np.random.default_rng(1305)
    n = int(rng.integers(6, 10))
    y = np.round(rng.normal(3, 2, size=n), 2)
    pred = np.round(y + rng.normal(0, 0.5, size=n), 2)
    cases = [(y, pred.reshape(-1, 1)), (y.reshape(-1, 1), pred), (y, pred), (y[:1], pred[:1].reshape(1, 1))]
    for yt, yp in cases:
        label = f"safe_mse(y_true of shape {yt.shape}, y_pred of shape {yp.shape})"
        got = _call(safe_mse, label, yt.copy(), yp.copy())
        want = _ref_mse(yt, yp)
        if got is None:
            raise Fail(f"`{label}` returned None.", hint="End with  return float(...).")
        try:
            value = float(got)
        except (TypeError, ValueError):
            raise Fail(f"`{label}` returned {_short(repr(got), 80)}; expected one float.",
                       hint="A loss is ONE number: take the mean of the squared differences.") from None
        if not np.isclose(value, want, rtol=1e-9, atol=1e-12):
            hint = "Flatten both sides with np.ravel(...) so they're both (n,), then mean((a - b) ** 2)."
            if yt.ndim != yp.ndim and np.isclose(value, float(np.mean((yt - yp) ** 2))):
                hint = ("(n,) minus (n, 1) broadcasts to an (n, n) matrix: every prediction minus every target. "
                        "The mean of that is a number, and it is meaningless. Ravel both first.")
            raise Fail(f"`{label}` returned {value:.6g}; expected {want:.6g}.", hint=hint)
    label = f"safe_mse(y_true of shape ({n},), y_pred of shape ({n - 1},))"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            got = safe_mse(y.copy(), pred[:-1].copy())
    except ValueError:
        return
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"`{label}` raised {type(exc).__name__}; expected ValueError.",
                   hint="Check the sizes yourself first: if a.size != b.size: raise ValueError(...)") from None
    raise Fail(f"`{label}` returned {_short(repr(got), 60)} for mismatched lengths.",
               hint="Different sizes means the data is misaligned. Refuse loudly: raise ValueError(...).")
