"""LAB ML01 // THE LINE — linear regression in closed form: the normal equation."""
from __future__ import annotations

import ast

from engine.mission import Fail, Mission

try:
    import numpy as np
except ImportError:  # the Lab shows `pip install numpy`; the briefing must still load without it
    np = None

MISSION = Mission(
    id="ML01",
    slug="ml01_the_line",
    title="THE LINE",
    concept="Linear regression: the normal equation",
    enemy="DRIFT.daemon",
    xp=260,
    par_seconds=35 * 60,
    tier=4,
    concepts=("numpy", "ml-math", "functions"),
    requires=("numpy",),
    timeout=12,
    run_as_main=False,
    enemy_art="""\
 ·     ▄▀▀▀▄     ·
   · ▄▀ ▓ ▓ ▀▄ ·
 ·  █  ▀▀▀▀▀  █  ·
  ▄▀▀▄▄▄▄▄▄▄▄▀▀▄
 ▀  ·  ▀▄ ▄▀  ·  ▀
   ·    ▀▄▀   ·""",
    briefing="""\
The Scriptorium Lab smells of wet ash. **MOTHER ADA** opens what survived of the Order's canon on
learning machines. The first legible page holds a cloud of points and one straight line through
them.

Below the tower, **DRIFT.daemon** runs the cistern forecasts. It draws its trend lines by eye, and
the Monastery rationed water on its guesses all winter.

"Every model you will ever train is a cousin of this line," Ada says. "And this one has an exact
answer. No guessing. Derive it, solve it, check it against the old world's own solver."

**Fit the line with the normal equation and take the forecasts back from DRIFT.**
""",
    why="""\
Linear regression is the first model on every regression project (prices, demand, sensor
calibration), and the last layer of almost every neural network is the same `X @ w + b`. When a
team builds something fancier, the linear fit is the **baseline** it must beat.

```python
Xb = np.hstack([np.ones((len(X), 1)), X])    # bias column: the intercept
w = np.linalg.solve(Xb.T @ Xb, Xb.T @ y)     # the normal equation
y_hat = Xb @ w
```

Knowing the closed form tells you what scikit-learn's `LinearRegression` does under the hood, why
it breaks when two features are copies of each other, and gives you an **exact reference** to test
an iterative trainer against. You'll need that reference in the very next mission.
""",
    manual="""\
**1. The model is a matrix product.** Stack your samples as rows of `X` with shape `(n, d)`
(n samples, d features). A linear model predicts `y_hat = X @ w + b`. Fold the intercept `b` into
the weights by adding a column of ones in front, so one matrix product does everything:

```python
import numpy as np
X = np.array([[2.0], [4.0], [6.0]])          # n=3 samples, d=1 feature
Xb = np.hstack([np.ones((X.shape[0], 1)), X])
Xb            # [[1, 2], [1, 4], [1, 6]]   shape (3, 2)
w = np.array([1.0, 0.5])                      # w[0] is the intercept, w[1] the slope
Xb @ w        # [2.0, 3.0, 4.0]
```

**2. The normal equation.** We want the `w` that minimizes the squared error `||Xb @ w - y||²`.
Set the gradient to zero and you get a linear system, the **normal equation**:

```text
(Xbᵀ Xb) w = Xbᵀ y
```

`Xb.T @ Xb` is a small `(d+1, d+1)` matrix, `Xb.T @ y` a `(d+1,)` vector. Let numpy solve it:

```python
A = Xb.T @ Xb
b = Xb.T @ y
w = np.linalg.solve(A, b)       # solves A @ w = b
```

Prefer `np.linalg.solve(A, b)` to `np.linalg.inv(A) @ b`: same answer on paper, but solve is faster
and loses fewer digits to rounding. If two features are exact copies, `A` is **singular** and
both fail: the data can't tell the two weights apart.

**3. Shapes are half of the bug reports.** `y` must be a flat vector `(n,)`. If it's a column
`(n, 1)`, then `w` comes out as `(d+1, 1)` and every later shape is off by a dimension.
`y.ravel()` flattens it.

**4. Scoring the fit: R².** R² compares your errors with the dumbest honest model, "always predict
the mean":

```python
ss_res = np.sum((y_true - y_pred) ** 2)            # your squared errors
ss_tot = np.sum((y_true - y_true.mean()) ** 2)     # the mean-predictor's squared errors
r2 = 1 - ss_res / ss_tot                           # 1.0 perfect, 0.0 no better than the mean
```

If every `y_true` is the same, `ss_tot` is 0. Follow scikit-learn: return 1.0 if the predictions are
also perfect, otherwise 0.0. Never divide by zero.

**5. The common mistake: no bias column.** Without the column of ones, the line is forced through
the origin. On data like "temperature = 40 + 2 × load" it tilts to compensate and every forecast is
wrong, while the code runs without a single error. If your weight vector has `d` entries instead of
`d+1`, you forgot it.

**6. The library versions** (for checking your work, not for this mission's code):

```python
w_ref, *_ = np.linalg.lstsq(Xb, y, rcond=None)     # numpy's least-squares solver
# scikit-learn:  LinearRegression().fit(X, y)  -> .intercept_ is w[0], .coef_ is w[1:]
# PyTorch:       torch.linalg.lstsq(Xb, y[:, None]).solution
```

Here you build the solver yourself: `lstsq`, `pinv`, `polyfit` and scikit-learn are sealed. The
grader compares your weights with `np.linalg.lstsq` on data you have never seen.
""",
    starter='''
"""
==============================================================================
  LAB ML01 // THE LINE                                 TARGET: DRIFT.daemon
==============================================================================
  Linear regression in closed form. numpy only: np.linalg.lstsq, pinv,
  polyfit and scikit-learn are sealed, because YOU are building the solver.
  The grader calls your functions on fresh random data and compares your
  answers with np.linalg.lstsq. Save, then HACK from the game.
"""
import numpy as np


# -- OBJECTIVE 1 -------------------------------------------------------------
def add_bias(X):
    """Return X with a column of ones added IN FRONT (column 0).

    X has shape (n, d); the result has shape (n, d + 1).
        add_bias(np.array([[2.0, 3.0], [4.0, 5.0]]))
        -> [[1, 2, 3], [1, 4, 5]]
    Don't change X itself: build and return a new array.
    """
    # TODO: np.ones((n, 1)) and np.hstack
    raise NotImplementedError("OBJECTIVE 1: add_bias")


# -- OBJECTIVE 2 -------------------------------------------------------------
def fit_normal_equation(X, y):
    """Fit linear regression with the normal equation.

    X: (n, d) features WITHOUT a bias column.  y: (n,) targets.
    Return w with shape (d + 1,): w[0] is the intercept, w[1:] the slopes.
    Solve (Xbᵀ Xb) w = Xbᵀ y with np.linalg.solve, where Xb = add_bias(X).
        fit_normal_equation(np.array([[1.0], [3.0]]), np.array([2.0, 6.0]))
        -> [0.0, 2.0]          (the line y = 0 + 2x)
    """
    # TODO
    raise NotImplementedError("OBJECTIVE 2: fit_normal_equation")


# -- OBJECTIVE 3 -------------------------------------------------------------
def predict(X, w):
    """Predictions for every row of X (no bias column) with weights w from
    fit_normal_equation. Return shape (n,)."""
    # TODO
    raise NotImplementedError("OBJECTIVE 3: predict")


# -- OBJECTIVE 4 // CORRUPTED CODE -------------------------------------------
# DRIFT.daemon scores its own forecasts with this. It reports a beautiful
# R² for almost any line. Compare it with the manual, section 4, and fix it.
# Also handle the case where every y_true is the same (see the manual).
def r2_score(y_true, y_pred):
    """Coefficient of determination: 1 - SS_res / SS_tot. Returns a float."""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum(y_true ** 2)
    return 1 - ss_res / ss_tot
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Sit, {callsign}. The canon burned, but its first page didn't. A line through points. Why do you think that one survived?"},
            {"speaker": "ada", "mood": "smirk",
             "text": "Because everything else is built on it. DRIFT draws lines by eye. We will draw the one that minimizes the squared error."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "The grader feeds your solver data it generates on the spot, then checks you against numpy's lstsq. No memorizing answers."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "'shapes not aligned' means a matrix product with mismatched sizes. Print .shape on both sides before you multiply."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "LinAlgError: Singular matrix. Two columns carry the same information, or you solved the wrong system."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "A crash is the code asking you a question. The COMBAT LOG says which line asked it."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Count your weights. A line in d features has d slopes and one intercept. Where does the intercept live?"}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Right numbers, wrong shape is still wrong. (n, 1) and (n,) are different animals in numpy."}],
            [{"speaker": "ada", "mood": "smirk",
              "text": "R² asks one question: how much better than guessing the mean? If your formula forgot the mean, it's flattering you."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Exact to the last digit numpy cares about. DRIFT's guesses are retired; the cistern forecasts are yours."},
            {"speaker": "ada", "mood": "neutral",
             "text": "Remember this answer. When the data is too big to solve in one stroke, we'll walk to it, and this is how we'll know we arrived."},
            {"speaker": "cipher", "mood": "smirk",
             "text": "Page one of the canon, re-inked. She's already turning to the next one. It's titled DOWNHILL."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

SEALED_MODULES = {"sklearn", "scipy", "statsmodels", "torch"}
SEALED_NAMES = {"lstsq", "pinv", "polyfit", "Polynomial"}


def _numpy():
    if np is None:
        raise Fail("numpy isn't installed, so the Lab can't grade this mission.", hint="pip install numpy")
    return np


def _show(value, limit: int = 150) -> str:
    if np is not None and isinstance(value, np.ndarray):
        text = np.array2string(value, precision=4, threshold=12, edgeitems=3, separator=", ",
                               suppress_small=True)
        text = " ".join(text.split())
    else:
        text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _defined(ctx, name: str) -> bool:
    return any(isinstance(n, ast.FunctionDef) and n.name == name for n in ctx.tree.body)


def _fn(ctx, name: str):
    if name not in ctx.ns:
        if ctx.crashed and _defined(ctx, name):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.", hint=f"Keep the starter's  def {name}(...):  line.")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return fn


def _crash_hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, NotImplementedError):
        return "That's still the starter stub. Replace the `raise NotImplementedError(...)` line with your code."
    if isinstance(exc, ValueError) and ("align" in msg or "matmul" in msg or "broadcast" in msg):
        return "A shape mismatch. Print X.shape, w.shape and y.shape: Xb is (n, d+1), w is (d+1,), y is (n,)."
    if type(exc).__name__ == "LinAlgError":
        return "Solve (Xbᵀ Xb) w = Xbᵀ y, where Xb has the bias column. Check you built A and b from Xb."
    if isinstance(exc, ZeroDivisionError):
        return "Division by zero. Handle the case it happens in explicitly, before you divide."
    return "Call the function yourself on this input and read the full error."


def _call(label: str, fn, *args):
    """Call the player's function on copies; a crash or an in-place edit fails the layer."""
    copies = [a.copy() if isinstance(a, np.ndarray) else a for a in args]
    try:
        out = fn(*copies)
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` raised {type(exc).__name__}: {exc}", hint=_crash_hint(exc))
    for original, passed in zip(args, copies):
        if isinstance(original, np.ndarray) and (passed.shape != original.shape
                                                 or not np.array_equal(passed, original)):
            raise Fail(f"`{label}` changed its input array in place.",
                       hint="Build a new array and return it. The caller still needs the original data.")
    return out


def _array(got, label: str, shape: tuple, what: str = "array"):
    if got is None:
        raise Fail(f"`{label}` returned None.", hint="Every function here must `return` its result.")
    try:
        arr = np.asarray(got, dtype=float)
    except (TypeError, ValueError):
        raise Fail(f"`{label}` returned {_show(got)}, which isn't a numeric {what}.")
    if arr.shape != tuple(shape):
        hint = f"Expected shape {tuple(shape)}."
        if arr.size == int(np.prod(shape)):
            hint = (f"Right number of values, wrong shape. A column (n, 1) is not a flat vector (n,): "
                    f"use .ravel() or keep y 1-D.")
        raise Fail(f"`{label}` returned shape {arr.shape}; expected {tuple(shape)}.", hint=hint)
    if not np.all(np.isfinite(arr)):
        raise Fail(f"`{label}` returned non-finite values: {_show(arr)}.",
                   hint="nan or inf usually means a division by zero or a singular system.")
    return arr


def _size(value) -> int:
    try:
        return int(np.asarray(value, dtype=float).size) if value is not None else -1
    except (TypeError, ValueError):
        return -1


def _scalar(got, label: str) -> float:
    if got is None:
        raise Fail(f"`{label}` returned None.", hint="Return the number with `return`.")
    arr = np.asarray(got)
    if arr.size != 1 or arr.dtype.kind not in "fiub":
        raise Fail(f"`{label}` returned {_show(got)}; expected one number.",
                   hint="Sum over everything (np.sum) so the result is a single float.")
    return float(arr.reshape(()))


def _sealed(ctx):
    """Line and name of the first sealed shortcut in the player's code, or None."""
    for node in ast.walk(ctx.tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in SEALED_MODULES:
                    return node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in SEALED_MODULES:
                return node.lineno, node.module
            for alias in node.names:
                if alias.name in SEALED_NAMES:
                    return node.lineno, alias.name
        elif isinstance(node, ast.Attribute) and node.attr in SEALED_NAMES:
            return node.lineno, node.attr
        elif isinstance(node, ast.Name) and node.id in SEALED_NAMES:
            return node.lineno, node.id
    return None


def _data(seed: int, n: int, d: int, noise: float = 0.3):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, d)) * rng.uniform(0.5, 4.0, size=d) + rng.uniform(-5, 5, size=d)
    w_true = np.round(rng.uniform(-3, 3, size=d + 1), 2)
    y = w_true[0] + X @ w_true[1:] + rng.normal(scale=noise, size=n)
    return X, y, w_true


def _bias_ref(X):
    return np.hstack([np.ones((X.shape[0], 1)), X])


def _lstsq_ref(X, y):
    return np.linalg.lstsq(_bias_ref(X), y, rcond=None)[0]


def _r2_ref(y_true, y_pred) -> float:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else 0.0
    return 1.0 - ss_res / ss_tot


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Bias column — `add_bias` puts the ones in front")
def _add_bias(ctx):
    _numpy()
    fn = _fn(ctx, "add_bias")
    rng = np.random.default_rng(1101)
    for X in (rng.normal(size=(5, 3)).round(2), rng.integers(-9, 9, size=(1, 2)).astype(float),
              rng.normal(size=(4, 1)).round(2), np.zeros((0, 2))):
        label = f"add_bias(X with shape {X.shape})"
        got = _array(_call(label, fn, X), label, (X.shape[0], X.shape[1] + 1))
        if X.shape[0] and not np.all(got[:, 0] == 1.0):
            hint = "The ones go in FRONT, as column 0, so w[0] is the intercept."
            if np.all(got[:, -1] == 1.0):
                hint = "Your ones are in the LAST column. Put them first: np.hstack([ones, X])."
            raise Fail(f"{label}: column 0 is {_show(got[:, 0])}, expected all ones.", hint=hint)
        if not np.array_equal(got[:, 1:], X):
            raise Fail(f"{label}: columns 1.. should be X unchanged.\nX = {_show(X)}\ngot {_show(got)}",
                       hint="Stack a (n, 1) column of ones to the left of X; don't transform X.")


@MISSION.check("Closed form — `fit_normal_equation` matches np.linalg.lstsq")
def _fit_matches(ctx):
    _numpy()
    fn = _fn(ctx, "fit_normal_equation")
    for seed, n, d in ((1201, 40, 3), (1202, 25, 1), (1203, 60, 5)):
        X, y, _ = _data(seed, n, d)
        label = f"fit_normal_equation(X {X.shape}, y {y.shape})"
        raw = _call(label, fn, X, y)
        if _size(raw) == d:
            raise Fail(f"{label} returned {d} weights; expected {d + 1}: the intercept w[0] plus {d} slopes.",
                       hint="Solve on add_bias(X), not X. Without the ones column the line is forced "
                            "through the origin.")
        got = _array(raw, label, (d + 1,), "weight vector")
        expected = _lstsq_ref(X, y)
        if not np.allclose(got, expected, rtol=1e-6, atol=1e-8):
            hint = "Build A = Xbᵀ Xb and b = Xbᵀ y from the biased X, then np.linalg.solve(A, b)."
            if np.allclose(got[::-1], expected, rtol=1e-6, atol=1e-8):
                hint = "Your weights are reversed: the intercept must be w[0], matching the ones column in front."
            raise Fail(f"{label} returned {_show(got)}\nnp.linalg.lstsq says   {_show(expected)}", hint=hint)


@MISSION.check("Ground truth — exact lines are recovered exactly")
def _truth(ctx):
    _numpy()
    fn = _fn(ctx, "fit_normal_equation")
    cases = [(np.array([[1.0], [3.0]]), np.array([2.0, 6.0]), np.array([0.0, 2.0]))]
    X, _, w_true = _data(1301, 12, 2)
    cases.append((X, w_true[0] + X @ w_true[1:], w_true))       # noiseless: the answer is w_true
    Xi = np.random.default_rng(1302).integers(0, 20, size=(9, 2))  # integer features still work
    cases.append((Xi, 40.0 + Xi @ np.array([2.0, -0.5]), np.array([40.0, 2.0, -0.5])))
    for X, y, w_true in cases:
        label = f"fit_normal_equation(X={_show(X, 60)}, y={_show(y, 60)})"
        got = _array(_call(label, fn, X, y), label, w_true.shape, "weight vector")
        if not np.allclose(got, w_true, atol=1e-6):
            raise Fail(f"{label}\nThis data lies exactly on a line with weights {_show(w_true)}, "
                       f"but you returned {_show(got)}.",
                       hint="With zero noise the normal equation has an exact solution. Check the intercept first.")


@MISSION.check("Sealed shortcuts — you are the solver")
def _no_shortcuts(ctx):
    found = _sealed(ctx)
    if found:
        line, name = found
        raise Fail(f"Line {line} uses `{name}`. In this mission that's the answer key, not a tool.",
                   hint="Build A = Xbᵀ Xb and b = Xbᵀ y yourself and call np.linalg.solve(A, b). "
                        "The grader already compares you against lstsq.")


@MISSION.check("Forecast — `predict` returns one value per row")
def _predict(ctx):
    _numpy()
    fn = _fn(ctx, "predict")
    for seed, n, d in ((1401, 7, 3), (1402, 1, 2), (1403, 30, 1)):
        rng = np.random.default_rng(seed)
        X = rng.normal(size=(n, d)).round(3)
        w = rng.uniform(-2, 2, size=d + 1).round(3)
        label = f"predict(X {X.shape}, w={_show(w)})"
        got = _array(_call(label, fn, X, w), label, (n,), "prediction vector")
        expected = w[0] + X @ w[1:]
        if not np.allclose(got, expected, rtol=1e-9, atol=1e-9):
            raise Fail(f"{label} returned {_show(got)}, expected {_show(expected)}.",
                       hint="Predictions are add_bias(X) @ w: the intercept is added to every row.")


@MISSION.check("Honest score — `r2_score` (corrupted code repaired)")
def _r2(ctx):
    _numpy()
    fn = _fn(ctx, "r2_score")
    rng = np.random.default_rng(1501)
    y = rng.normal(50, 4, size=30).round(2)
    cases = [
        (y, y + rng.normal(0, 2, size=30).round(2), "a decent forecast"),
        (y, np.full(30, y.mean()), "always predicting the mean (must be 0.0)"),
        (y, y.copy(), "a perfect forecast (must be 1.0)"),
        (y, y[::-1].copy(), "a forecast worse than the mean (negative is allowed)"),
        (np.full(5, 7.0), np.full(5, 7.0), "constant truth, perfect forecast (1.0)"),
        (np.full(5, 7.0), np.array([7.0, 7.0, 8.0, 7.0, 7.0]), "constant truth, imperfect forecast (0.0)"),
    ]
    for y_true, y_pred, story in cases:
        label = f"r2_score(y_true={_show(y_true, 50)}, y_pred={_show(y_pred, 50)})"
        with np.errstate(all="ignore"):
            got = _scalar(_call(label, fn, y_true, y_pred), label)
        expected = _r2_ref(y_true, y_pred)
        if not np.isfinite(got) or not np.isclose(got, expected, rtol=1e-9, atol=1e-9):
            hint = "SS_tot measures spread around the MEAN: np.sum((y_true - y_true.mean()) ** 2)."
            if np.std(y_true) == 0:
                hint = "All y_true are equal, so SS_tot is 0: return 1.0 if SS_res is 0 too, else 0.0."
            raise Fail(f"{label} — {story}: returned {got!r}, expected {expected!r}.", hint=hint)
