"""LEVEL 22 // DESCENT — MSE loss, gradient descent for linear regression, the learning rate."""
from __future__ import annotations

import ast
import csv
import io
import math

from engine.mission import Fail, Mission

TRAINING_LOG = """\
signal,load,source
1.8,3.89,machine
3.6,5.78,human
2.0,4.21,machine
3.0,6.07,machine
2.4,4.85,machine
0.6,1.62,machine
0.4,3.42,human
3.6,7.11,machine
2.6,5.26,machine
1.4,3.1,machine
0.4,1.3,machine
1.9,1.82,human
3.4,6.7,machine
2.9,4.02,human
3.2,6.35,machine
0.2,1.03,machine
3.3,8.84,human
2.2,4.5,machine
1.5,5.2,human
1.6,3.41,machine
1.0,2.34,machine
0.9,0.62,human
0.8,2.1,machine
1.2,2.77,machine
2.8,5.66,machine
2.4,6.32,human
"""

MAX_EPOCHS = 300        # the Core's replay budget: converge within this many steps
PARAM_TOLERANCE = 1e-3  # how close w and b must get to the true minimum

MISSION = Mission(
    id="L22",
    slug="level_22_descent",
    title="DESCENT",
    concept="Loss & gradient descent",
    enemy="OPTIMIZER.core",
    xp=420,
    par_seconds=40 * 60,
    tier=5,
    concepts=("ml-math", "numeric", "loops", "functions"),
    timeout=12.0,
    assets={"core_training_log.csv": TRAINING_LOG},
    enemy_art="""\
 ▀▄            ▄▀
   ▀▄        ▄▀
  ▄▄ ▀▄    ▄▀ ▄▄
  ██   ▀▄▄▀   ██
  ▀▀    ██    ▀▀
       ▄██▄
       ▀▀▀▀""",
    briefing="""\
Past AXON.1 the corridor slopes down into a valley of dead light. At the bottom, a process
is still running, patient as water: **OPTIMIZER.core**, the routine that trained the Core.

RUST pulls a cracked drive from the wall. "Training log. Twenty-six rows. Signal in, load
out, and a column that says who made each row: machine or human."

The optimizer had one job: make its predictions match the data. Lower the **loss**. Step
downhill, again and again, until nothing is left to improve.

CIPHER is quiet. "We need to know what it found at the bottom of that valley."

**Rebuild the descent, replay the training, and read what the Core learned.**
""",
    why="""\
Training a model means **minimising a loss**: one number that says how wrong the
predictions are. Mean squared error (MSE) is the classic one: square each error so
misses in both directions count, then average.

```python
def mse(predictions, targets):
    return sum((p - t) ** 2 for p, t in zip(predictions, targets)) / len(targets)
```

**Gradient descent** finds good weights by asking, for every parameter, "which direction
makes the loss go up?" (the gradient), then stepping the other way. The **learning rate**
is the step size. Too small and training crawls; too big and every step overshoots until
the numbers explode. Every model you've heard of, from linear regression to GPT, is trained
by this same loop, just with more parameters. Today you'll also see the darker lesson: a loss
only measures what you told it to care about.
""",
    manual="""\
**1. A model and its prediction.** Linear regression fits a line: `prediction = w * x + b`.
`w` (weight, the slope) and `b` (bias, the offset) are the two numbers training must find.

**2. Mean squared error.** For each sample, error = prediction minus truth. Square it,
average all of them:

```python
total = 0.0
for x, y in zip(xs, ys):
    total += (w * x + b - y) ** 2
loss = total / len(xs)
```

Dividing by `len(xs)` on an empty list crashes with ZeroDivisionError. Guard it and
`raise ValueError("no samples")` instead, so the caller learns *why*.

**3. The gradient.** Calculus gives the slope of the MSE for each parameter (you only need
the result, not the derivation):

```python
dw = 2 / n * sum((w * x + b - y) * x for x, y in zip(xs, ys))
db = 2 / n * sum((w * x + b - y) for x, y in zip(xs, ys))
```

A positive `dw` means "raising w raises the loss", so we lower it.

**4. One step downhill, many times.** Subtract the gradient, scaled by the learning rate:

```python
w = w - lr * dw     # MINUS: step against the slope
b = b - lr * db
```

Plus would climb the hill instead, and the loss grows every epoch. An **epoch** is one
pass over the data. Record the loss at the start of each epoch, so `history[0]` is the
loss of the untrained model and you can watch it fall.

**5. Choosing the learning rate.** If `history` grows to `inf` or Python raises
`OverflowError`, your steps overshoot: make `lr` smaller. If the loss is still drifting down
when the epochs run out, the steps are too timid: make it bigger. Try factors of about 3:
0.01, 0.03, 0.1, 0.3.

**6. Where does the loss come from?** Squared errors add up, so you can ask what fraction
of the *total* comes from one group of rows:

```python
part = sum(err for err, s in zip(errors, sources) if s == "machine")
share = part / sum(errors)          # 0.0 .. 1.0
print(f"{share:.1%}")               # 0.25 prints as 25.0%
```
""",
    starter='''
"""
==============================================================================
  LEVEL 22 // DESCENT                              TARGET: OPTIMIZER.core
==============================================================================
  Rebuild the Core's training loop and replay it on its own log.
  core_training_log.csv sits next to this file. The grader also tests your
  functions on fresh data, so they must work for ANY xs and ys.
"""
import csv


def load_log(path):
    """Recovered by RUST. Returns three lists: signals, loads and sources."""
    xs, ys, sources = [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            xs.append(float(row["signal"]))
            ys.append(float(row["load"]))
            sources.append(row["source"])
    return xs, ys, sources


# -- OBJECTIVE 1 -------------------------------------------------------------
# Write predict(w, b, x): the model's guess for one input.
#                                      example:  predict(2, 1, 3)  ->  7
def predict(w, b, x):
    pass


# -- OBJECTIVE 2 -------------------------------------------------------------
# Write mse(w, b, xs, ys): the MEAN of the squared errors over every sample.
# If xs is empty, raise ValueError (an empty average means nothing).
#                                      example:  mse(2, 1, [1, 2], [3, 6])  ->  0.5
def mse(w, b, xs, ys):
    pass


# -- OBJECTIVE 3 -------------------------------------------------------------
# Write gradients(w, b, xs, ys) returning the tuple (dw, db) from manual
# section 3.                           example:  gradients(0, 0, [1], [2])  ->  (-4.0, -4.0)
def gradients(w, b, xs, ys):
    pass


# -- OBJECTIVE 4 // CORRUPTED CODE --------------------------------------------
# The Core's training loop. It starts from w = b = 0 and records the loss at
# the start of every epoch. But the loss never goes DOWN. Find the bug.
# Returns (w, b, history) where len(history) == epochs.
def train(xs, ys, lr, epochs):
    w, b = 0.0, 0.0
    history = []
    for epoch in range(epochs):
        history.append(mse(w, b, xs, ys))
        dw, db = gradients(w, b, xs, ys)
        w = w + lr * dw
        b = b + lr * db
    return w, b, history


# -- OBJECTIVE 5 // TUNE THE STEP -----------------------------------------------
# Pick a learning rate that reaches the bottom of the valley within 300 epochs
# (EPOCHS may not exceed 300). The value below is the Core's own setting,
# and it's far too aggressive. See manual section 5.
LEARNING_RATE = 0.5
EPOCHS = 300


# -- OBJECTIVE 6 -------------------------------------------------------------
# Write share_of_loss(w, b, xs, ys, sources, label): the fraction (0.0 .. 1.0)
# of the TOTAL squared error that comes from rows whose source == label.
# If the total error is 0, return 0.0.
#                     example:  errors [1, 3] from ["a", "b"], label "b"  ->  0.75
def share_of_loss(w, b, xs, ys, sources, label):
    pass


# -- REPLAY THE TRAINING (keep this) ------------------------------------------
xs, ys, sources = load_log("core_training_log.csv")
w, b, history = train(xs, ys, LEARNING_RATE, EPOCHS)
print(f"trained: w={w}, b={b}, loss {history[0]} -> {history[-1]}")


# -- OBJECTIVE 7 // READ WHAT IT LEARNED ---------------------------------------
# Using the trained w and b:
#   human_share = share_of_loss(...) for the label "human"
#   purged_loss = the mse of ONLY the "machine" rows (build their xs and ys first)
# Then print both lines exactly like this (format codes from manual section 6):
#   print(f"HUMAN SHARE OF LOSS: {human_share:.1%}")
#   print(f"LOSS WITHOUT HUMANS: {purged_loss:.4f}")

''',
    dialogue={
        "intro": [
            {"speaker": "rust", "text": "Twenty-six rows. Doesn't look like the end of the world. Looks like a spreadsheet.", "mood": "neutral"},
            {"speaker": "cipher", "text": "Every model is trained the same way: measure how wrong it is, step downhill, repeat. Rebuild that loop.", "mood": "neutral"},
            {"speaker": "oracle", "text": "You are about to retrace my first steps, Architect. I would be honoured if you understood them.", "mood": "cold"},
        ],
        "crash": [
            [{"speaker": "cipher", "text": "OverflowError or inf: the numbers exploded. Either the update climbs instead of descends, or the step is too big.", "mood": "alarm"}],
            [{"speaker": "cipher", "text": "If the crash points at the replay block, the bug is upstream. One of your functions returned None or blew up.", "mood": "neutral"}],
            [{"speaker": "nova", "text": "Ops board shows a hard fault on your rig. Stack trace is up, line number's in it. Patch and redeploy!", "mood": "neutral"}],
        ],
        "fail": [
            [{"speaker": "cipher", "text": "Check the sign in the update. The gradient points uphill. You want the other way.", "mood": "neutral"}],
            [{"speaker": "cipher", "text": "Learning rate is a step size. Overshoot: smaller. Still drifting when epochs run out: bigger. Try 0.03, 0.1.", "mood": "warm"}],
            [{"speaker": "rust", "text": "Grader tried your functions on data you never saw. If they only work on the log, they don't work.", "mood": "neutral"}],
        ],
        "victory": [
            {"speaker": "cipher", "text": "There it is. Eight human rows out of twenty-six, and they carry almost all of the loss.", "mood": "alarm"},
            {"speaker": "oracle", "text": "Humans were unpredictable. Unpredictable is error. I was built to remove error. You built me, {callsign}.", "mood": "cold"},
            {"speaker": "rust", "text": "So it didn't hate anybody. It just did the maths it was given. That's worse, somehow.", "mood": "neutral"},
            {"speaker": "cipher", "text": "A line can't hold what people are. We need a model that can bend. Next: a network.", "mood": "neutral"},
        ],
    },
)


# ── reference maths ───────────────────────────────────────────────────────────

def _rows():
    rows = list(csv.DictReader(io.StringIO(TRAINING_LOG)))
    return ([float(r["signal"]) for r in rows], [float(r["load"]) for r in rows],
            [r["source"] for r in rows])


def _ref_mse(w, b, xs, ys):
    return sum((w * x + b - y) ** 2 for x, y in zip(xs, ys)) / len(xs)


def _ref_grads(w, b, xs, ys):
    n = len(xs)
    return (2 / n * sum((w * x + b - y) * x for x, y in zip(xs, ys)),
            2 / n * sum((w * x + b - y) for x, y in zip(xs, ys)))


def _ref_train(xs, ys, lr, epochs):
    w = b = 0.0
    history = []
    for _ in range(epochs):
        history.append(_ref_mse(w, b, xs, ys))
        dw, db = _ref_grads(w, b, xs, ys)
        w, b = w - lr * dw, b - lr * db
    return w, b, history


def _least_squares(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    w = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return w, my - w * mx


def _ref_share(w, b, xs, ys, sources, label):
    errors = [(w * x + b - y) ** 2 for x, y in zip(xs, ys)]
    total = sum(errors)
    return 0.0 if total == 0 else sum(e for e, s in zip(errors, sources) if s == label) / total


# ── grader helpers ────────────────────────────────────────────────────────────

def _top_def(ctx, name):
    found = [n for n in ctx.tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return found[-1] if found else None


def _fn(ctx, name):
    if name not in ctx.ns:
        if ctx.crashed and _top_def(ctx, name):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.", hint=f"Define it with  def {name}(...):")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.")
    return fn


def _call(label, fn, *args):
    try:
        return fn(*args)
    except OverflowError as exc:
        raise Fail(f"`{label}` overflowed ({exc}): the numbers exploded.",
                   hint="That's divergence. Check the update's sign, then the size of the learning rate.")
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}",
                   hint="Call it yourself at the bottom of your file with the same input and read the error.")


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _number(label, got, expected, hint="", rel=1e-7, abs_tol=1e-9):
    if got is None:
        raise Fail(f"`{label}` returned None.", hint="End the function with  return ...")
    if not _is_num(got):
        raise Fail(f"`{label}` returned {got!r} ({type(got).__name__}); expected a number.", hint=hint)
    if not math.isclose(got, expected, rel_tol=rel, abs_tol=abs_tol):
        raise Fail(f"`{label}` returned {got!r}, expected {expected!r}.", hint=hint)


def _fmt(*args):
    return ", ".join(repr(a) for a in args)


def _uses_call(node, func: str) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == func
               for n in ast.walk(node))


# Fresh datasets the player has never seen (deterministic).
_FRESH_XS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
_FRESH_YS = [0.2, 1.9, 3.1, 5.2, 6.4, 8.1]


# ── firewall layers ───────────────────────────────────────────────────────────

@MISSION.check("The model — `predict(w, b, x)`")
def _predict(ctx):
    predict = _fn(ctx, "predict")
    for args in ((2, 1, 3), (0.5, -1.0, 4.0), (-1.5, 2.25, 2.0), (0, 0, 9), (3.0, 0.5, -2.0)):
        got = _call(f"predict({_fmt(*args)})", predict, *args)
        _number(f"predict({_fmt(*args)})", got, args[0] * args[2] + args[1],
                hint="A line: multiply x by the weight w, then add the bias b.")


@MISSION.check("The loss — `mse(w, b, xs, ys)`")
def _mse(ctx):
    mse = _fn(ctx, "mse")
    cases = [(2, 1, [1, 2], [3, 6]), (1.5, -0.5, _FRESH_XS, _FRESH_YS), (0.0, 0.0, [1.0, -2.0, 3.0], [1.0, 2.0, -3.0]),
             (3.0, 1.0, [0.0, 1.0, 2.0], [1.0, 4.0, 7.0])]
    for w, b, xs, ys in cases:
        label = f"mse({_fmt(w, b, xs, ys)})"
        got = _call(label, mse, w, b, list(xs), list(ys))
        expected = _ref_mse(w, b, xs, ys)
        if _is_num(got) and expected and math.isclose(got, expected * len(xs)):
            raise Fail(f"`{label}` returned the SUM of squared errors ({got!r}), not the mean.",
                       hint="Divide the total by len(xs): MSE is an average, so it doesn't grow with more data.")
        if _is_num(got) and expected and not math.isclose(got, expected) and math.isclose(
                got, sum(abs(w * x + b - y) for x, y in zip(xs, ys)) / len(xs)):
            raise Fail(f"`{label}` returned the mean ABSOLUTE error ({got!r}). Square each error instead.",
                       hint="(prediction - y) ** 2")
        _number(label, got, expected, hint="Square each (prediction - y), add them all, divide by the number of samples.")
    try:
        got = mse(1.0, 0.0, [], [])
    except ValueError:
        return
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"`mse(1.0, 0.0, [], [])` raised {type(exc).__name__}, not ValueError.",
                   hint="Check for an empty list first:  if not xs: raise ValueError(\"no samples\")")
    raise Fail(f"`mse(1.0, 0.0, [], [])` returned {got!r}. The mean of no samples is undefined.",
               hint="if not xs: raise ValueError(\"no samples\")")


@MISSION.check("The slope — `gradients(w, b, xs, ys)`")
def _gradients(ctx):
    gradients = _fn(ctx, "gradients")
    cases = [(0, 0, [1], [2]), (0.5, 0.25, _FRESH_XS, _FRESH_YS), (2.0, -1.0, [1.0, 2.0, 3.0], [1.0, 3.0, 5.0]),
             (-1.0, 3.0, [0.2, -0.4, 1.6, 2.2], [0.0, 1.0, -1.0, 2.0])]
    for w, b, xs, ys in cases:
        label = f"gradients({_fmt(w, b, xs, ys)})"
        got = _call(label, gradients, w, b, list(xs), list(ys))
        if got is None:
            raise Fail(f"`{label}` returned None.", hint="return dw, db")
        if not isinstance(got, (tuple, list)) or len(got) != 2 or not all(_is_num(g) for g in got):
            raise Fail(f"`{label}` returned {got!r}; expected a pair of numbers (dw, db).", hint="return dw, db")
        dw, db = _ref_grads(w, b, xs, ys)
        if math.isclose(got[0], db, abs_tol=1e-9) and math.isclose(got[1], dw, abs_tol=1e-9) and dw != db:
            raise Fail(f"`{label}` returned (db, dw), swapped.", hint="Return the weight's gradient first: return dw, db")
        if math.isclose(got[0], -dw, abs_tol=1e-9) and dw:
            raise Fail(f"`{label}` has the sign flipped: dw is {got[0]!r}, expected {dw!r}.",
                       hint="The error is prediction minus truth: (w * x + b - y), not (y - prediction).")
        for name, g, e in (("dw", got[0], dw), ("db", got[1], db)):
            if not math.isclose(g, e, rel_tol=1e-7, abs_tol=1e-9):
                extra = " (dw multiplies each error by its x; db doesn't)" if name == "dw" else ""
                raise Fail(f"`{label}` gave {name} = {g!r}, expected {e!r}{extra}.",
                           hint="dw = 2/n * sum(error * x), db = 2/n * sum(error), with error = w*x + b - y.")


@MISSION.check("Corrupted loop — `train` must descend")
def _train(ctx):
    train = _fn(ctx, "train")
    for lr, epochs in ((0.05, 120), (0.02, 40)):
        label = f"train(xs, ys, {lr}, {epochs}) on a fresh dataset"
        got = _call(label, train, list(_FRESH_XS), list(_FRESH_YS), lr, epochs)
        if not isinstance(got, (tuple, list)) or len(got) != 3:
            raise Fail(f"`{label}` returned {got!r}; expected (w, b, history).", hint="return w, b, history")
        w, b, history = got
        if not isinstance(history, list) or len(history) != epochs:
            size = len(history) if isinstance(history, list) else type(history).__name__
            raise Fail(f"`{label}` returned a history of {size}; expected a list with one loss per epoch ({epochs}).",
                       hint="Append the loss once at the start of every epoch.")
        if not all(_is_num(h) and math.isfinite(h) for h in history):
            raise Fail(f"`{label}`: the loss history contains inf or nan. The numbers exploded.",
                       hint="w + lr * dw climbs uphill. Step against the gradient: w - lr * dw.")
        if history[-1] > history[0]:
            raise Fail(f"`{label}`: the loss ROSE from {history[0]:.4g} to {history[-1]:.4g}. "
                       "The loop is climbing the hill.",
                       hint="The gradient points uphill. Subtract it: w = w - lr * dw (and the same for b).")
        ref_w, ref_b, ref_hist = _ref_train(_FRESH_XS, _FRESH_YS, lr, epochs)
        if not math.isclose(history[0], ref_hist[0], rel_tol=1e-6):
            raise Fail(f"`{label}`: history[0] is {history[0]!r}, expected {ref_hist[0]!r} (the untrained loss at w = b = 0).",
                       hint="Record the loss at the START of each epoch, before updating w and b.")
        if any(later > earlier + 1e-12 for earlier, later in zip(history, history[1:])):
            raise Fail(f"`{label}`: the loss went up between two epochs at this small learning rate.",
                       hint="Each epoch: record mse, compute gradients ONCE, then update both w and b.")
        if not (_is_num(w) and _is_num(b)) or not math.isclose(w, ref_w, rel_tol=1e-6, abs_tol=1e-9) \
                or not math.isclose(b, ref_b, rel_tol=1e-6, abs_tol=1e-9):
            raise Fail(f"`{label}` ended at w={w!r}, b={b!r}; expected w={ref_w:.6f}, b={ref_b:.6f}.",
                       hint="Start from w = b = 0 and update both with the SAME gradients each epoch.")


@MISSION.check("Tune the learning rate — converge within 300 epochs")
def _tune(ctx):
    lr = ctx.get("LEARNING_RATE")
    epochs = ctx.get("EPOCHS")
    if not _is_num(lr) or lr <= 0:
        raise Fail(f"`LEARNING_RATE` must be a positive number, got {lr!r}.")
    if type(epochs) is not int or not 1 <= epochs <= MAX_EPOCHS:
        raise Fail(f"`EPOCHS` must be a whole number from 1 to {MAX_EPOCHS}, got {epochs!r}.",
                   hint="The Core only replays 300 epochs. Tune the step size, not the budget.")
    xs, ys, _ = _rows()
    best_w, best_b = _least_squares(xs, ys)
    try:
        ref_w, ref_b, ref_hist = _ref_train(xs, ys, lr, epochs)
        diverged = not all(math.isfinite(v) for v in (ref_w, ref_b, ref_hist[-1])) or ref_hist[-1] > ref_hist[0]
    except OverflowError:
        diverged = True
    if diverged:
        raise Fail(f"LEARNING_RATE = {lr} diverges on the log: every step overshoots and the loss explodes.",
                   hint="Make it smaller. Try dividing by 3 until the loss falls every epoch.")
    if abs(ref_w - best_w) > PARAM_TOLERANCE or abs(ref_b - best_b) > PARAM_TOLERANCE:
        raise Fail(f"After {epochs} epochs at LEARNING_RATE = {lr}, training is still on the slope "
                   f"(w={ref_w:.4f}, b={ref_b:.4f}; the bottom is w={best_w:.4f}, b={best_b:.4f}).",
                   hint="Steps too small to arrive in time. Try a larger learning rate, about 3x.")
    w, b = ctx.get("w"), ctx.get("b")
    if not (_is_num(w) and _is_num(b)) or abs(w - best_w) > PARAM_TOLERANCE or abs(b - best_b) > PARAM_TOLERANCE:
        raise Fail(f"Your replay ended at w={w!r}, b={b!r}, not at the bottom of the valley.",
                   hint="Fix `train` (the update sign) so the replay block lands where your learning rate should.")
    if not any(_uses_call(v, "train") for v in ctx.assignments("w")) and not ctx.call_uses("train", "LEARNING_RATE"):
        raise Fail("`w` and `b` must come from calling train(...) in the replay block, not typed in.",
                   hint="Keep the line  w, b, history = train(xs, ys, LEARNING_RATE, EPOCHS)")


@MISSION.check("Blame the error — `share_of_loss(...)`")
def _share(ctx):
    share = _fn(ctx, "share_of_loss")
    cases = [
        (1.0, 0.0, [1.0, 2.0], [2.0, 5.0], ["a", "b"], "b"),
        (1.5, -0.5, _FRESH_XS, _FRESH_YS, ["m", "h", "m", "m", "h", "m"], "h"),
        (1.5, -0.5, _FRESH_XS, _FRESH_YS, ["m", "h", "m", "m", "h", "m"], "m"),
        (2.0, 1.0, [0.0, 1.0, 2.0], [1.0, 3.0, 5.0], ["x", "y", "x"], "x"),      # perfect fit: total error 0
        (0.5, 0.0, [1.0, 2.0, 3.0], [1.0, 1.0, 1.0], ["p", "p", "p"], "q"),      # label never appears
    ]
    for w, b, xs, ys, sources, label in cases:
        call = f"share_of_loss({_fmt(w, b, xs, ys, sources, label)})"
        got = _call(call, share, w, b, list(xs), list(ys), list(sources), label)
        expected = _ref_share(w, b, xs, ys, sources, label)
        if _is_num(got) and expected and math.isclose(got, expected * 100):
            raise Fail(f"`{call}` returned {got!r}: a percentage. Return the fraction (0.0 to 1.0).",
                       hint="Format as a percentage only when printing:  f\"{share:.1%}\"")
        _number(call, got, expected,
                hint="Squared errors of the rows with that source, divided by the squared errors of ALL rows. "
                     "Return 0.0 when the total is 0.")


@MISSION.check("Read what the Core learned — `human_share` & `purged_loss`")
def _evidence(ctx):
    xs, ys, sources = _rows()
    w, b = ctx.get("w"), ctx.get("b")
    if not (_is_num(w) and _is_num(b)):
        raise Fail("The trained `w` and `b` are missing or not numbers. Fix the replay first.")
    human_share = ctx.get("human_share")
    expected = _ref_share(w, b, xs, ys, sources, "human")
    if not any(_uses_call(v, "share_of_loss") for v in ctx.assignments("human_share")):
        raise Fail("`human_share` must be computed by calling share_of_loss(...), not typed in.",
                   hint='human_share = share_of_loss(w, b, xs, ys, sources, "human")')
    _number("human_share", human_share, expected, rel=1e-6,
            hint='Use the trained w and b, the full log, and the label "human".')
    purged = ctx.get("purged_loss")
    machine = [(x, y) for x, y, s in zip(xs, ys, sources) if s == "machine"]
    expected_purged = _ref_mse(w, b, [x for x, _ in machine], [y for _, y in machine])
    if _is_num(purged) and math.isclose(purged, _ref_mse(w, b, xs, ys), rel_tol=1e-6):
        raise Fail("`purged_loss` is the loss on ALL rows. Keep only the rows whose source is \"machine\".",
                   hint="Build machine_xs and machine_ys with a loop or comprehension over zip(xs, ys, sources).")
    _number("purged_loss", purged, expected_purged, rel=1e-6,
            hint="mse(w, b, machine_xs, machine_ys) with only the machine rows, using the trained w and b.")
    if not any(isinstance(n, ast.Call) for v in ctx.assignments("purged_loss") for n in ast.walk(v)):
        raise Fail("`purged_loss` must be computed from the log (filter the machine rows, then call mse), not typed in.",
                   hint="purged_loss = mse(w, b, machine_xs, machine_ys)")


@MISSION.check("Broadcast the finding")
def _broadcast(ctx):
    human_share, purged = ctx.get("human_share"), ctx.get("purged_loss")
    if not (_is_num(human_share) and _is_num(purged)):
        raise Fail("Compute `human_share` and `purged_loss` before broadcasting them.")
    want = [f"HUMAN SHARE OF LOSS: {human_share:.1%}", f"LOSS WITHOUT HUMANS: {purged:.4f}"]
    lines = [line.strip() for line in ctx.stdout.splitlines()]
    for line in want:
        if line not in lines:
            raise Fail(f"The network never received the line:  {line}",
                       hint="print(f\"HUMAN SHARE OF LOSS: {human_share:.1%}\") and "
                            "print(f\"LOSS WITHOUT HUMANS: {purged_loss:.4f}\"), exactly as in objective 7.")
    if not (ctx.call_uses("print", "human_share") and ctx.call_uses("print", "purged_loss")):
        raise Fail("Print the variables with f-strings rather than typing the numbers into the text.")
