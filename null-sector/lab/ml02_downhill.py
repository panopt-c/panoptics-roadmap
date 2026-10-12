"""LAB ML02 // DOWNHILL — gradient descent, loss curves and the learning rate."""
from __future__ import annotations

import math

from engine.mission import Fail, Mission
from lab.ml01_the_line import _array, _call, _fn, _numpy, _scalar, _sealed, _show

try:
    import numpy as np
except ImportError:  # the Lab shows `pip install numpy`; the briefing must still load without it
    np = None

MISSION = Mission(
    id="ML02",
    slug="ml02_downhill",
    title="DOWNHILL",
    concept="Gradient descent & loss curves",
    enemy="OVERSHOOT.daemon",
    xp=260,
    par_seconds=40 * 60,
    tier=4,
    concepts=("numpy", "ml-math", "loops"),
    requires=("numpy",),
    timeout=15,
    run_as_main=False,
    enemy_art="""\
   ▲          ▲
  ▲ ▲   ▄▄   ▲ ▲
 ▲   ▲ █▀▀█ ▲   ▲
      ▀█▓▓█▀
  ◄═══ ▀██▀ ═══►
   ·   ·  ·   ·""",
    briefing="""\
Page two of the canon is a contour map: rings inside rings, and an arrow walking down toward the
middle. Ada has re-inked the arrow three times. "The normal equation needs every row at once," she
says. "The Core had billions. So it walked."

Down in the pump hall, **OVERSHOOT.daemon** tunes the cistern valves. Every correction is bigger
than the last one. The pressure gauge swings wider each hour, and the old pipes knock like
someone asking to be let in.

"Same valley as yesterday," Ada says. "Small steps. Watch the loss fall, and know why it falls."

**Build gradient descent, prove your gradient, and find the learning rate that won't blow up.**
""",
    why="""\
Every neural network you will ever train is fitted by some version of this loop: `loss.backward()`
computes the gradient, `optimizer.step()` takes a step of size `lr`. The **learning rate** is the
first hyperparameter every ML engineer tunes, and the **loss curve** is the first plot they read:
falling is good, flat means the step is too small, climbing or `nan` means it's too big.

```python
for epoch in range(epochs):            # PyTorch, same loop
    loss = loss_fn(model(X), y)
    optimizer.zero_grad()
    loss.backward()                    # the gradient you derive by hand here
    optimizer.step()                   # w <- w - lr * grad
    history.append(loss.item())
```

Engineers also **check gradients numerically** before trusting them: nudge one weight, watch the
loss, compare. That habit catches the bugs a loss curve hides.
""",
    manual="""\
**1. The loss is one number.** Mean squared error (MSE) averages the squared misses:

```python
import numpy as np
def mse(y_true, y_pred):
    return np.mean((y_pred - y_true) ** 2)
mse(np.array([1.0, 2.0]), np.array([1.0, 4.0]))   # (0² + 2²) / 2 = 2.0
```

**2. The gradient points uphill.** With the bias column already in `Xb` (shape `(n, d+1)`) and
the error `e = Xb @ w - y`, calculus gives the slope of the MSE in every weight direction:

```python
grad = (2 / n) * Xb.T @ e          # shape (d+1,): one number per weight
```

The `2` comes from the square, the `/ n` from the mean. Step **against** it to go downhill:
`w = w - lr * grad`.

**3. Check your gradient with finite differences.** Nudge one weight by a tiny `h` both ways:

```python
h = 1e-6
w_plus, w_minus = w.copy(), w.copy()
w_plus[0] += h; w_minus[0] -= h
slope0 = (mse(y, Xb @ w_plus) - mse(y, Xb @ w_minus)) / (2 * h)   # ≈ grad[0]
```

If your formula and the nudge disagree, the formula is wrong. The grader does exactly this.

**4. The loop and its history.** Start at `w = 0`, record the loss before the first step and after
every step, so `len(history) == epochs + 1`. A healthy curve only goes down.

**5. The learning rate.** Too small: the curve barely moves. Too big: each step overshoots the
valley floor, lands higher on the other side, and the loss explodes to `inf`, then `nan`. Pick it
with a **sweep**: train with several rates, keep the lowest finite final loss.

**6. The common mistake: comparing with `nan`.** Every comparison with `nan` is `False`:
`nan < 3.0` and `3.0 < nan` are both `False`. If a diverged run's `nan` becomes your "best so far",
nothing can ever beat it. Test with `np.isfinite(loss)` first.

**7. The library versions.** PyTorch: `torch.optim.SGD(model.parameters(), lr=0.1)`.
scikit-learn: `SGDRegressor(learning_rate="constant", eta0=0.1)`. Both run this exact loop. Here
`lstsq`, `solve`, `inv` and `pinv` are sealed: you walk, you don't teleport.
""",
    starter='''
"""
==============================================================================
  LAB ML02 // DOWNHILL                              TARGET: OVERSHOOT.daemon
==============================================================================
  Gradient descent for linear regression, numpy only. The closed-form
  solvers (np.linalg.lstsq, solve, inv, pinv) are sealed: you WALK to the
  answer. The grader checks your gradient against finite differences and
  your final weights against np.linalg.lstsq. Save, then HACK from the game.
"""
import numpy as np


def add_bias(X):
    """Given (from ML01): X (n, d) -> (n, d + 1) with a column of ones in front."""
    return np.hstack([np.ones((X.shape[0], 1)), X])


# -- OBJECTIVE 1 -------------------------------------------------------------
def mse(y_true, y_pred):
    """Mean squared error, a single float.
        mse(np.array([1.0, 2.0]), np.array([1.0, 4.0]))  -> 2.0
    """
    # TODO
    raise NotImplementedError("OBJECTIVE 1: mse")


# -- OBJECTIVE 2 -------------------------------------------------------------
def mse_gradient(Xb, y, w):
    """Gradient of mse(y, Xb @ w) with respect to w. Shape (d + 1,).

    Xb ALREADY has the bias column. Formula: (2 / n) * Xbᵀ (Xb @ w - y).
    """
    # TODO
    raise NotImplementedError("OBJECTIVE 2: mse_gradient")


# -- OBJECTIVE 3 -------------------------------------------------------------
def gradient_descent(X, y, lr, epochs):
    """Fit linear regression by gradient descent. X has NO bias column.

    Start from w = zeros(d + 1). Repeat `epochs` times: w = w - lr * gradient.
    Return (w, history) where history is a list of floats:
        history[0]  = MSE at the starting w (all zeros)
        history[i]  = MSE after update i          -> len(history) == epochs + 1
    """
    # TODO
    raise NotImplementedError("OBJECTIVE 3: gradient_descent")


# -- OBJECTIVE 4 // CORRUPTED CODE -------------------------------------------
# OVERSHOOT.daemon picks its learning rate with this sweep. When its first
# candidate rate blows up to nan, it gets stuck on that rate forever.
# Read the manual, section 6, and fix it. If EVERY rate diverges, return None.
def best_learning_rate(X, y, rates, epochs=100):
    """Return the rate in `rates` whose final training loss is lowest."""
    best_rate, best_loss = None, None
    for rate in rates:
        _, history = gradient_descent(X, y, rate, epochs)
        final = history[-1]
        if best_loss is None or final < best_loss:
            best_rate, best_loss = rate, final
    return best_rate
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Yesterday you solved for the bottom of the valley. Today pretend you can't see it. Which way do you step, {callsign}?"},
            {"speaker": "ada", "mood": "smirk",
             "text": "Downhill, yes. The gradient tells you which way is up. The learning rate decides how big a fool you are about it."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Grader nudges every weight by a millionth and watches the loss. If your gradient disagrees with the nudge, it fails."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Shapes first. Xb is (n, d+1), w is (d+1,), the error is (n,). Xb.T @ error comes back (d+1,). Print them."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Overflow warnings mean the loss is exploding. That's the learning rate talking, not a bug in Python."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "The traceback is a map. Find your own line in it, then read the last line twice."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Where did the 2 in the gradient come from? Where did the n go? Derive it once on paper and you'll never forget it."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "history wants the starting loss too. Fifty steps make fifty-one numbers: one before you move."}],
            [{"speaker": "ada", "mood": "smirk",
              "text": "nan is not a small number, it's no number. Ask np.isfinite before you ask 'less than'."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Your walk ends where yesterday's equation did. Two roads, one valley. That's how you know both are right."},
            {"speaker": "rust", "mood": "smirk",
             "text": "Pump hall's quiet. Pressure's flat. Whatever you did to that daemon, I'd like it in a crate."},
            {"speaker": "ada", "mood": "neutral",
             "text": "Next page. A line can forecast water. Tomorrow we teach one to say yes or no."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

SEALED_MODULES = {"sklearn", "scipy", "statsmodels", "torch"}
SEALED_NAMES = {"lstsq", "pinv", "solve", "inv", "polyfit", "Polynomial"}


def _bias(X):
    return np.hstack([np.ones((X.shape[0], 1)), X])


def _mse_ref(y_true, y_pred) -> float:
    return float(np.mean((y_pred - y_true) ** 2))


def _grad_ref(Xb, y, w):
    return (2.0 / len(y)) * Xb.T @ (Xb @ w - y)


def _gd_ref(X, y, lr, epochs):
    Xb = _bias(X)
    w = np.zeros(Xb.shape[1])
    history = [_mse_ref(y, Xb @ w)]
    with np.errstate(all="ignore"):
        for _ in range(epochs):
            w = w - lr * _grad_ref(Xb, y, w)
            history.append(_mse_ref(y, Xb @ w))
    return w, history


def _best_rate_ref(X, y, rates, epochs):
    best_rate, best_loss = None, math.inf
    for rate in rates:
        final = _gd_ref(X, y, rate, epochs)[1][-1]
        if math.isfinite(final) and final < best_loss:
            best_rate, best_loss = rate, final
    return best_rate


def _data(seed: int, n: int, d: int, noise: float = 0.4):
    """Standardized features (mean 0, std 1) so a learning rate near 0.1 is safe."""
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, d))
    X = (X - X.mean(axis=0)) / X.std(axis=0)
    w_true = np.round(rng.uniform(-3, 3, size=d + 1), 2)
    y = w_true[0] + X @ w_true[1:] + rng.normal(scale=noise, size=n)
    return X, y


def _crash_hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, NotImplementedError):
        return "That's still the starter stub. Replace the `raise NotImplementedError(...)` line with your code."
    if isinstance(exc, ValueError) and ("align" in msg or "matmul" in msg or "broadcast" in msg):
        return "Shape mismatch. Xb is (n, d+1), w is (d+1,), error = Xb @ w - y is (n,), Xb.T @ error is (d+1,)."
    if isinstance(exc, (TypeError, ValueError)) and "unpack" in msg:
        return "gradient_descent must return a pair: `return w, history`."
    return "Call the function yourself on a tiny input and read the full error."


def _run_gd(fn, X, y, lr, epochs):
    label = f"gradient_descent(X {X.shape}, y {y.shape}, lr={lr}, epochs={epochs})"
    out = _call(label, fn, X, y, lr, epochs, crash_hint=_crash_hint)
    if not isinstance(out, (tuple, list)) or len(out) != 2:
        raise Fail(f"{label} returned {_show(out, 80)}; expected a pair (w, history).",
                   hint="End the function with  return w, history")
    w_raw, hist_raw = out
    d = X.shape[1]
    w = _array(w_raw, f"{label}[0] (w)", (d + 1,), "weight vector")
    try:
        history = np.asarray(hist_raw, dtype=float)
    except (TypeError, ValueError):
        raise Fail(f"{label}: history is {_show(hist_raw, 80)}, not a list of numbers.",
                   hint="Append float(loss) to a list once before the loop and once per update.")
    if history.ndim != 1:
        raise Fail(f"{label}: history has shape {history.shape}; expected a flat list of losses.",
                   hint="Each entry is one number: the MSE at that moment, not an array of errors.")
    return label, w, history


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Loss — `mse` is the mean of the squared errors")
def _mse(ctx):
    _numpy()
    fn = _fn(ctx, "mse")
    rng = np.random.default_rng(2101)
    cases = [(np.array([1.0, 2.0]), np.array([1.0, 4.0])),
             (rng.normal(size=12).round(2), rng.normal(size=12).round(2)),
             (np.array([3.0]), np.array([-1.0])),
             (rng.integers(-5, 5, size=7), rng.integers(-5, 5, size=7))]
    for y_true, y_pred in cases:
        label = f"mse({_show(y_true, 60)}, {_show(y_pred, 60)})"
        got = _scalar(_call(label, fn, y_true, y_pred, crash_hint=_crash_hint), label)
        expected = _mse_ref(y_true, y_pred)
        if not np.isclose(got, expected, rtol=1e-9, atol=1e-12):
            hint = "Square each miss, then take the MEAN: np.mean((y_pred - y_true) ** 2)."
            if np.isclose(got, expected * len(y_true)):
                hint = "That's the SUM of squared errors. Divide by n (use np.mean) so the loss doesn't grow with the data."
            elif np.isclose(got, float(np.mean(np.abs(y_pred - y_true)))):
                hint = "That's the mean ABSOLUTE error. MSE squares each miss: (y_pred - y_true) ** 2."
            raise Fail(f"{label} returned {got!r}; expected {expected!r}.", hint=hint)


@MISSION.check("Gradient check — `mse_gradient` agrees with finite differences")
def _gradient(ctx):
    _numpy()
    fn = _fn(ctx, "mse_gradient")
    for seed, n, d in ((2201, 20, 2), (2202, 9, 4), (2203, 1, 1)):
        X, y = _data(seed, max(n, 2), d)
        X, y = X[:n], y[:n]
        Xb = _bias(X)
        w = np.random.default_rng(seed + 50).normal(size=d + 1).round(2)
        label = f"mse_gradient(Xb {Xb.shape}, y {y.shape}, w={_show(w)})"
        got = _array(_call(label, fn, Xb, y, w, crash_hint=_crash_hint), label, (d + 1,), "gradient")
        expected = _grad_ref(Xb, y, w)
        h = 1e-6
        numeric = np.array([(_mse_ref(y, Xb @ (w + h * e)) - _mse_ref(y, Xb @ (w - h * e))) / (2 * h)
                            for e in np.eye(d + 1)])
        if not np.allclose(got, expected, rtol=1e-6, atol=1e-8):
            hint = "Error first: e = Xb @ w - y. Then (2 / n) * Xb.T @ e."
            if np.allclose(got, expected / 2, rtol=1e-6, atol=1e-8):
                hint = "Exactly half the slope: you dropped the 2. d/dw of (stuff)² is 2·(stuff)·d(stuff)/dw."
            elif np.allclose(got, -expected, rtol=1e-6, atol=1e-8):
                hint = "Right size, wrong direction: use Xb @ w - y (prediction minus truth), not y - Xb @ w."
            elif np.allclose(got, expected * n, rtol=1e-6, atol=1e-8):
                hint = "n times too big: the loss is a MEAN, so the gradient divides by n too."
            raise Fail(f"{label} returned {_show(got)}\nfinite differences say {_show(numeric)}", hint=hint)


@MISSION.check("First step — history starts at the loss of w = 0")
def _history_shape(ctx):
    _numpy()
    fn = _fn(ctx, "gradient_descent")
    X, y = _data(2301, 30, 2)
    for epochs in (10, 1, 0):
        label, w, history = _run_gd(fn, X, y, 0.1, epochs)
        if len(history) != epochs + 1:
            hint = "Record the loss once BEFORE the loop (at w = 0), then once after every update."
            if len(history) == epochs:
                hint = "One short: history[0] must be the loss at the starting w = zeros, before any update."
            raise Fail(f"{label}: history has {len(history)} entries; expected {epochs + 1}.", hint=hint)
        start = _mse_ref(y, np.zeros_like(y))
        if not np.isclose(history[0], start, rtol=1e-9):
            raise Fail(f"{label}: history[0] is {history[0]:.6g}; the loss at w = 0 is {start:.6g}.",
                       hint="Start from w = np.zeros(d + 1). With every weight at 0 every prediction is 0, "
                            "so the first loss is mean(y ** 2).")
        if epochs == 0 and not np.allclose(w, 0):
            raise Fail(f"{label} returned w = {_show(w)}; with zero epochs w must stay all zeros.",
                       hint="The loop runs `epochs` times. Zero epochs, zero steps.")


@MISSION.check("Downhill — the loss curve never climbs at a sane learning rate")
def _monotone(ctx):
    _numpy()
    fn = _fn(ctx, "gradient_descent")
    for seed, lr in ((2401, 0.05), (2402, 0.2)):
        X, y = _data(seed, 60, 3)
        label, _, history = _run_gd(fn, X, y, lr, 60)
        if not np.all(np.isfinite(history)):
            raise Fail(f"{label}: the loss went non-finite: {_show(history)}.",
                       hint="At this small learning rate the loss must fall. Check the sign of your update: w - lr * grad.")
        rises = np.flatnonzero(np.diff(history) > 1e-9 * max(1.0, history[0]))
        if rises.size:
            i = int(rises[0])
            raise Fail(f"{label}: the loss went UP at step {i + 1}: {history[i]:.6g} -> {history[i + 1]:.6g}.\n"
                       f"curve: {_show(history)}",
                       hint="Gradient descent steps AGAINST the gradient: w = w - lr * grad. "
                            "Recompute the gradient from the current w every epoch.")
        if not history[-1] < 0.5 * history[0]:
            raise Fail(f"{label}: the loss barely moved: {history[0]:.4g} -> {history[-1]:.4g}.",
                       hint="Are you updating w inside the loop and computing each loss from the NEW w?")


@MISSION.check("Same walk — your trajectory matches the reference step for step")
def _trajectory(ctx):
    _numpy()
    fn = _fn(ctx, "gradient_descent")
    for seed, n, d, lr, epochs in ((2501, 50, 2, 0.1, 40), (2502, 35, 4, 0.03, 25)):
        X, y = _data(seed, n, d)
        label, w, history = _run_gd(fn, X, y, lr, epochs)
        w_ref, hist_ref = _gd_ref(X, y, lr, epochs)
        if len(history) == len(hist_ref) and not np.allclose(history, hist_ref, rtol=1e-6, atol=1e-10):
            i = int(np.flatnonzero(~np.isclose(history, hist_ref, rtol=1e-6, atol=1e-10))[0])
            raise Fail(f"{label}: history[{i}] is {history[i]:.8g}; the reference walk has {hist_ref[i]:.8g}.\n"
                       f"yours: {_show(history[:5])}\nref:   {_show(np.array(hist_ref[:5]))}",
                       hint="One update per epoch: grad = mse_gradient(Xb, y, w); w = w - lr * grad; "
                            "then append mse(y, Xb @ w). Use your own add_bias, mse and mse_gradient.")
        if not np.allclose(w, w_ref, rtol=1e-6, atol=1e-8):
            raise Fail(f"{label} returned w = {_show(w)}; after {epochs} steps the reference is at {_show(w_ref)}.",
                       hint="Return the weights after the LAST update, not the best or the first.")


@MISSION.check("Arrival — enough small steps land on the np.linalg.lstsq answer")
def _arrival(ctx):
    _numpy()
    fn = _fn(ctx, "gradient_descent")
    X, y = _data(2601, 120, 3)
    label, w, history = _run_gd(fn, X, y, 0.1, 400)
    exact = np.linalg.lstsq(_bias(X), y, rcond=None)[0]
    if not np.allclose(w, exact, atol=1e-5):
        raise Fail(f"{label} ended at {_show(w)}\nnp.linalg.lstsq (the bottom of the valley): {_show(exact)}",
                   hint="With standardized features and lr = 0.1, 400 steps reach the exact answer. "
                        "Check the gradient formula and that every epoch takes one step.")


@MISSION.check("Learning-rate sweep — `best_learning_rate` survives nan (corrupted code repaired)")
def _sweep(ctx):
    _numpy()
    fn = _fn(ctx, "best_learning_rate")
    X, y = _data(2701, 40, 2)
    cases = [((1000.0, 0.001, 0.02, 0.3), "the FIRST rate diverges to nan"),
             ((0.001, 0.3, 4.0, 0.02), "a rate in the middle explodes"),
             ((1.2, 0.01), "1.2 overshoots: big but finite losses"),
             ((60.0, 1000.0), "every rate diverges (return None)")]
    for rates, story in cases:
        expected = _best_rate_ref(X, y, rates, 100)
        label = f"best_learning_rate(X, y, rates={list(rates)}, epochs=100)"
        with np.errstate(all="ignore"):
            got = _call(label, fn, X, y, list(rates), 100, crash_hint=_crash_hint)
        same = (got is None and expected is None) or (
            got is not None and expected is not None and isinstance(got, (int, float, np.number))
            and not isinstance(got, bool) and np.isclose(float(got), expected))
        if not same:
            finals = {r: _gd_ref(X, y, r, 100)[1][-1] for r in rates}
            shown = ", ".join(f"{r}: {v:.3g}" for r, v in finals.items())
            hint = ("nan < x is False for every x, so once nan is 'best' nothing replaces it. "
                    "Skip any final loss where np.isfinite(final) is False.")
            if expected is None:
                hint = "No rate finished with a finite loss, so there is no best rate: return None."
            raise Fail(f"{label} — {story}: returned {got!r}, expected {expected!r}.\nfinal losses: {shown}",
                       hint=hint)


@MISSION.check("Sealed shortcuts — walk, don't teleport")
def _no_shortcuts(ctx):
    found = _sealed(ctx, SEALED_MODULES, SEALED_NAMES)
    if found:
        line, name = found
        raise Fail(f"Line {line} uses `{name}`. Closed-form solvers are sealed in this mission.",
                   hint="Reach the answer with gradient steps only. The grader already compares you with lstsq.")
