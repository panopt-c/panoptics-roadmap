"""LAB ML03 // YES OR NO — logistic regression: sigmoid, binary cross-entropy and its gradient."""
from __future__ import annotations

from engine.mission import Fail, Mission
from lab.ml01_the_line import _array, _call, _fn, _numpy, _scalar, _sealed, _show

try:
    import numpy as np
except ImportError:  # the Lab shows `pip install numpy`; the briefing must still load without it
    np = None

MISSION = Mission(
    id="ML03",
    slug="ml03_yes_or_no",
    title="YES OR NO",
    concept="Logistic regression",
    enemy="COINFLIP.sentry",
    xp=260,
    par_seconds=45 * 60,
    tier=4,
    concepts=("numpy", "ml-math", "evaluation"),
    requires=("numpy",),
    timeout=15,
    run_as_main=False,
    enemy_art="""\
    ▄▄████▄▄
  ▄█▀ ▄▄▄▄ ▀█▄
  █  █ ?? █  █
  █  █ !! █  █
  ▀█▄ ▀▀▀▀ ▄█▀
    ▀▀████▀▀""",
    briefing="""\
Night shift at the Monastery gate. Signals knock on the outer relay: scavengers, lost drones,
sometimes a Core probe. **COINFLIP.sentry** decides who gets in. It has no model. It flips a
weighted coin and logs the result as certainty.

Ada brings the third page of the canon to the gatehouse. Under the ash: an S-shaped curve, and
a margin note in her own young handwriting. *A probability is a promise. Keep it.*

"A line can say how much," she says. "A gate needs yes or no, and how sure. Squash the line."

**Build logistic regression from scratch: a stable sigmoid, the cross-entropy loss, its gradient,
and a trained gate.**
""",
    why="""\
Logistic regression is the default first classifier for anything yes/no: fraud, churn, spam,
"will this part fail". It's also exactly the **last layer** of a binary neural network: a linear
layer, a sigmoid, and binary cross-entropy. PyTorch's `BCEWithLogitsLoss` fuses the sigmoid into
the loss for the same numerical-stability reason you'll meet here.

```python
logits = X @ w + b
p = torch.sigmoid(logits)                          # probability of class 1
loss = F.binary_cross_entropy_with_logits(logits, y)
```

Because the output is a **calibrated probability**, a team can move the threshold: flag at 0.2
for a cancer screen (catch everything), 0.9 for a ban hammer (be sure). The gradient you derive
here, `Xᵀ(p − y) / n`, is the same one every framework computes.
""",
    manual="""\
**1. The sigmoid squashes any real number into (0, 1).**

```python
import numpy as np
def sigmoid_naive(z):
    return 1 / (1 + np.exp(-z))
sigmoid_naive(np.array([-2.0, 0.0, 2.0]))     # [0.119, 0.5, 0.881]
```

The input `z = Xb @ w` is called the **logit**; the output is the probability of class 1.

**2. Make it stable.** `np.exp(-z)` for `z = -1000` is `exp(1000)`: **overflow**. Never feed `exp`
a large positive number. Use `e = np.exp(-np.abs(z))`, which is always in (0, 1]:

```python
e = np.exp(-np.abs(z))
p = np.where(z >= 0, 1 / (1 + e), e / (1 + e))   # both branches are the true sigmoid
```

**3. The loss: binary cross-entropy (BCE).** It measures surprise: predicting 0.99 for something
that turned out 0 costs a lot.

```python
p = np.clip(p, eps, 1 - eps)                      # log(0) is -inf: never take it
loss = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
```

The minus sign matters: `log` of a probability is negative, and a loss should be positive.

**4. The gradient is beautifully simple.** With `p = sigmoid(Xb @ w)`:

```python
grad = Xb.T @ (p - y) / len(y)      # same shape as w
```

Same shape as linear regression's gradient, with `p` in place of the prediction (and no 2).
Train exactly like ML02: start at zeros, `w = w - lr * grad`, repeat.

**5. Decide.** `predict_proba` returns probabilities; `predict` turns them into 0/1 with a
threshold. Follow scikit-learn: class 1 only when `p > threshold`, so an exact tie goes to 0.
Return integers: `(p > threshold).astype(int)`.

**6. The common mistake: the naive sigmoid "works".** On ordinary inputs it gives right answers,
then a single extreme logit fills your log with overflow warnings or turns your loss into
`nan`. Stable code is the same on easy inputs and still right on hard ones.

**7. The library versions.** scikit-learn: `LogisticRegression()` (adds L2 by default).
SciPy: `scipy.special.expit` is a stable sigmoid. Both are sealed here; the grader compares you
with its own reference on fresh data.
""",
    starter='''
"""
==============================================================================
  LAB ML03 // YES OR NO                              TARGET: COINFLIP.sentry
==============================================================================
  Logistic regression from scratch, numpy only (scikit-learn and
  scipy.special.expit are sealed). The grader feeds your sigmoid extreme
  logits with overflow turned into an error, checks your gradient against
  finite differences, and trains your model on fresh data.
"""
import numpy as np


def add_bias(X):
    """Given (from ML01): X (n, d) -> (n, d + 1) with a column of ones in front."""
    return np.hstack([np.ones((X.shape[0], 1)), X])


# -- OBJECTIVE 1 -------------------------------------------------------------
def sigmoid(z):
    """1 / (1 + e^-z), element-wise, for a number or an array of any shape.

    Must not overflow for z = -1000 or z = 1000 (see the manual, section 2).
        sigmoid(0.0) -> 0.5      sigmoid(np.array([-1000.0, 1000.0])) -> [0., 1.]
    """
    # TODO
    raise NotImplementedError("OBJECTIVE 1: sigmoid")


# -- OBJECTIVE 2 // CORRUPTED CODE -------------------------------------------
# COINFLIP.sentry grades itself with this. Its loss is negative (it thinks
# it is better than perfect) and turns into nan whenever it is 100% sure.
def bce_loss(y_true, p, eps=1e-12):
    """Mean binary cross-entropy. Clip p into [eps, 1 - eps] first."""
    return np.mean(y_true * np.log(p) + (1 - y_true) * np.log(1 - p))


# -- OBJECTIVE 3 -------------------------------------------------------------
def bce_gradient(Xb, y, w):
    """Gradient of bce_loss(y, sigmoid(Xb @ w)) with respect to w.

    Xb ALREADY has the bias column. Formula: Xbᵀ (sigmoid(Xb @ w) - y) / n.
    """
    # TODO
    raise NotImplementedError("OBJECTIVE 3: bce_gradient")


# -- OBJECTIVE 4 -------------------------------------------------------------
def fit_logistic(X, y, lr=0.5, epochs=300):
    """Train by gradient descent. X has NO bias column; y holds 0s and 1s.
    Start at w = zeros(d + 1); each epoch: w = w - lr * bce_gradient(...).
    Return w (shape (d + 1,)): w[0] is the bias."""
    # TODO
    raise NotImplementedError("OBJECTIVE 4: fit_logistic")


# -- OBJECTIVE 5 -------------------------------------------------------------
def predict_proba(X, w):
    """P(class 1) for every row of X (no bias column). Shape (n,)."""
    # TODO
    raise NotImplementedError("OBJECTIVE 5: predict_proba")


def predict(X, w, threshold=0.5):
    """0/1 integer labels: 1 only where predict_proba > threshold (a tie is 0)."""
    # TODO
    raise NotImplementedError("OBJECTIVE 5: predict")
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "A line answers 'how much'. The gate asks 'should I open'. What do you do with a number that can be minus forty?"},
            {"speaker": "ada", "mood": "smirk",
             "text": "You squash it. Zero to one. Then you punish confident mistakes harder than timid ones. That's the whole trick."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Heads-up, {callsign}: the grader turns numpy overflow warnings into errors when it tests your sigmoid."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "alarm",
              "text": "FloatingPointError: overflow. Something fed exp a huge positive number. Read the manual, section 2."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "Xb.T @ (p - y): Xb is (n, d+1), p and y are (n,). If those don't line up, print every shape."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "math.exp takes one number. np.exp takes a whole array. The grader sends arrays."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "A loss below zero means you forgot that log of a probability is negative. Where does the minus sign go?"}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "log(0) is minus infinity. Clip the probabilities before you take the log."}],
            [{"speaker": "ada", "mood": "smirk",
              "text": "Exactly one half is not a yes. Ties go to zero, same as scikit-learn."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Listen to the gate. It used to say 'yes' and 'no'. Now it says 'ninety-one percent'. That's honesty, {callsign}."},
            {"speaker": "vex", "mood": "smirk",
             "text": "A coin-flip bot, beaten by algebra. Cute. Let me know when your gate can tell a ghost from a friend."},
            {"speaker": "ada", "mood": "neutral",
             "text": "It can. Whether it's any GOOD at it is a separate question, and the old world never asked it. Next page."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

SEALED_MODULES = {"sklearn", "scipy", "statsmodels", "torch"}
SEALED_NAMES = {"expit", "LogisticRegression", "log_loss"}


def _bias(X):
    return np.hstack([np.ones((X.shape[0], 1)), X])


def _sigmoid_ref(z):
    z = np.asarray(z, dtype=float)
    e = np.exp(-np.abs(z))
    return np.where(z >= 0, 1 / (1 + e), e / (1 + e))


def _bce_ref(y, p, eps=1e-12):
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _grad_ref(Xb, y, w):
    return Xb.T @ (_sigmoid_ref(Xb @ w) - y) / len(y)


def _fit_ref(X, y, lr, epochs):
    Xb = _bias(X)
    w = np.zeros(Xb.shape[1])
    for _ in range(epochs):
        w = w - lr * _grad_ref(Xb, y, w)
    return w


def _data(seed: int, n: int, d: int):
    """Standardized features, labels drawn from a true logistic model."""
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, d))
    X = (X - X.mean(axis=0)) / X.std(axis=0)
    w_true = np.round(rng.uniform(-3, 3, size=d + 1), 2)
    y = (rng.random(n) < _sigmoid_ref(_bias(X) @ w_true)).astype(float)
    return X, y


def _crash_hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, NotImplementedError):
        return "That's still the starter stub. Replace the `raise NotImplementedError(...)` line with your code."
    if isinstance(exc, FloatingPointError):
        return "exp overflowed. Only ever exponentiate a non-positive number: e = np.exp(-np.abs(z))."
    if isinstance(exc, TypeError) and ("only" in msg or "convert" in msg or "length-1" in msg):
        return "math.exp works on single numbers. Use np.exp so the function works on whole arrays."
    if isinstance(exc, ValueError) and ("align" in msg or "matmul" in msg or "broadcast" in msg):
        return "Shape mismatch. Xb is (n, d+1), w is (d+1,), p and y are (n,), Xb.T @ (p - y) is (d+1,)."
    return "Call the function yourself on a tiny input and read the full error."


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Squash — `sigmoid` maps every real number into (0, 1)")
def _squash(ctx):
    _numpy()
    fn = _fn(ctx, "sigmoid")
    got = _scalar(_call("sigmoid(0.0)", fn, 0.0, crash_hint=_crash_hint), "sigmoid(0.0)")
    if not np.isclose(got, 0.5):
        raise Fail(f"sigmoid(0.0) returned {got!r}; expected 0.5.", hint="1 / (1 + e^0) = 1 / 2.")
    rng = np.random.default_rng(3101)
    for z in (rng.normal(0, 3, size=9).round(3), rng.normal(0, 2, size=(3, 4)).round(3)):
        label = f"sigmoid({_show(z, 70)})"
        with np.errstate(all="ignore"):
            out = _array(_call(label, fn, z, crash_hint=_crash_hint), label, z.shape)
        expected = _sigmoid_ref(z)
        if not np.allclose(out, expected, rtol=1e-9, atol=1e-12):
            hint = "sigmoid(z) = 1 / (1 + np.exp(-z)), element-wise."
            if np.allclose(out, 1 - expected, rtol=1e-9):
                hint = "Mirror image: you computed sigmoid(-z). The exponent is -z for the plain formula."
            raise Fail(f"{label} returned {_show(out)}\nexpected {_show(expected)}", hint=hint)


@MISSION.check("Stable — no overflow at z = ±1000")
def _stable(ctx):
    _numpy()
    fn = _fn(ctx, "sigmoid")
    z = np.array([-1000.0, -745.0, -30.0, 0.0, 30.0, 745.0, 1000.0])
    label = f"sigmoid({_show(z)})"
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            raw = fn(z.copy())
    except FloatingPointError as exc:
        raise Fail(f"{label} overflowed: {exc}.",
                   hint="np.exp(-z) with z = -1000 is e^1000. Use e = np.exp(-np.abs(z)) and pick "
                        "1/(1+e) where z >= 0, e/(1+e) where z < 0. Both branches are the exact sigmoid.")
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"`{label}` raised {type(exc).__name__}: {exc}", hint=_crash_hint(exc))
    out = _array(raw, label, z.shape)
    expected = _sigmoid_ref(z)
    if not np.allclose(out, expected, rtol=1e-9, atol=1e-15):
        raise Fail(f"{label} returned {_show(out)}\nexpected {_show(expected)}",
                   hint="Very negative logits give probabilities near 0, very positive ones near 1, never nan.")


@MISSION.check("Surprise — `bce_loss` is positive, clipped and exact (corrupted code repaired)")
def _bce(ctx):
    _numpy()
    fn = _fn(ctx, "bce_loss")
    rng = np.random.default_rng(3201)
    y = (rng.random(12) < 0.5).astype(float)
    cases = [(y, rng.uniform(0.05, 0.95, size=12).round(3), "ordinary probabilities"),
             (np.array([1.0, 0.0]), np.array([0.9, 0.1]), "two confident right answers"),
             (np.array([1.0, 0.0, 1.0]), np.array([1.0, 0.0, 0.0]), "p of exactly 1 and 0 (needs clipping)"),
             (np.ones(4), np.full(4, 0.5), "a coin flip on four 1s: log 2 ≈ 0.693")]
    for y_true, p, story in cases:
        label = f"bce_loss({_show(y_true, 50)}, {_show(p, 60)})"
        with np.errstate(all="ignore"):
            got = _scalar(_call(label, fn, y_true, p, crash_hint=_crash_hint), label)
        expected = _bce_ref(y_true, p)
        if not np.isfinite(got) or not np.isclose(got, expected, rtol=1e-7, atol=1e-10):
            hint = "loss = -mean(y·log(p) + (1-y)·log(1-p)) after p = np.clip(p, eps, 1 - eps)."
            if np.isfinite(got) and np.isclose(got, -expected, rtol=1e-7):
                hint = "Same size, wrong sign: log of a probability is negative, so BCE has a minus in front."
            elif not np.isfinite(got):
                hint = "log(0) is -inf. Clip first: p = np.clip(p, eps, 1 - eps)."
            elif np.isclose(got, expected * len(y_true), rtol=1e-7):
                hint = "That's the sum. Average over samples with np.mean."
            raise Fail(f"{label} — {story}: returned {got!r}, expected {expected!r}.", hint=hint)


@MISSION.check("Gradient check — `bce_gradient` agrees with finite differences")
def _gradient(ctx):
    _numpy()
    fn = _fn(ctx, "bce_gradient")
    for seed, n, d in ((3301, 25, 2), (3302, 8, 3)):
        X, y = _data(seed, n, d)
        Xb = _bias(X)
        w = np.random.default_rng(seed + 9).normal(size=d + 1).round(2)
        label = f"bce_gradient(Xb {Xb.shape}, y {y.shape}, w={_show(w)})"
        got = _array(_call(label, fn, Xb, y, w, crash_hint=_crash_hint), label, (d + 1,), "gradient")
        expected = _grad_ref(Xb, y, w)
        h = 1e-6
        numeric = np.array([(_bce_ref(y, _sigmoid_ref(Xb @ (w + h * e))) - _bce_ref(y, _sigmoid_ref(Xb @ (w - h * e))))
                            / (2 * h) for e in np.eye(d + 1)])
        if not np.allclose(got, expected, rtol=1e-6, atol=1e-9):
            hint = "p = sigmoid(Xb @ w), then Xb.T @ (p - y) / n."
            if np.allclose(got, -expected, rtol=1e-6):
                hint = "Right size, wrong direction: it's (p - y), prediction minus truth."
            elif np.allclose(got, expected * n, rtol=1e-6):
                hint = "n times too big: the loss is a mean, so divide the gradient by n."
            elif np.allclose(got, Xb.T @ (Xb @ w - y) / n, rtol=1e-6):
                hint = "You used the raw logit Xb @ w. Squash it first: p = sigmoid(Xb @ w)."
            raise Fail(f"{label} returned {_show(got)}\nfinite differences say {_show(numeric)}", hint=hint)


@MISSION.check("Training — `fit_logistic` walks downhill from w = 0")
def _training(ctx):
    _numpy()
    fn = _fn(ctx, "fit_logistic")
    for seed, n, d, lr, epochs in ((3401, 80, 2, 0.5, 200), (3402, 50, 3, 0.1, 60)):
        X, y = _data(seed, n, d)
        label = f"fit_logistic(X {X.shape}, y {y.shape}, lr={lr}, epochs={epochs})"
        with np.errstate(all="ignore"):
            raw = _call(label, fn, X, y, lr, epochs, crash_hint=_crash_hint)
        got = _array(raw, label, (d + 1,), "weight vector")
        expected = _fit_ref(X, y, lr, epochs)
        if not np.allclose(got, expected, rtol=1e-6, atol=1e-8):
            start, mine = _bce_ref(y, np.full(n, 0.5)), _bce_ref(y, _sigmoid_ref(_bias(X) @ got))
            hint = ("Start at np.zeros(d + 1), add the bias column once, then exactly `epochs` updates "
                    "of w = w - lr * bce_gradient(Xb, y, w). Use the lr and epochs you were given.")
            if mine > start:
                hint = "Your loss went UP from w = 0. Step AGAINST the gradient: w = w - lr * grad."
            raise Fail(f"{label} returned {_show(got)}\nreference after {epochs} steps: {_show(expected)}\n"
                       f"loss at w = 0: {start:.4f}, at your w: {mine:.4f}", hint=hint)
    # the trained gate must actually work on fresh signals from the same source
    X, y = _data(3403, 400, 2)
    with np.errstate(all="ignore"):
        w = _array(_call("fit_logistic(gate signals)", fn, X[:300], y[:300], 0.5, 300, crash_hint=_crash_hint),
                   "fit_logistic", (3,), "weight vector")
    accuracy = float(np.mean((_sigmoid_ref(_bias(X[300:]) @ w) > 0.5) == (y[300:] == 1)))
    if accuracy < 0.8:
        raise Fail(f"Trained on 300 gate signals, your model is right on only {accuracy:.0%} of 100 new ones.",
                   hint="A correct logistic regression reaches about 90% here. Check the update direction.")


@MISSION.check("Decision — `predict_proba` and `predict` (ties go to 0)")
def _decision(ctx):
    _numpy()
    proba, pred = _fn(ctx, "predict_proba"), _fn(ctx, "predict")
    rng = np.random.default_rng(3501)
    X = rng.normal(size=(7, 2)).round(2)
    w = np.array([0.3, -1.2, 2.0])
    label = f"predict_proba(X {X.shape}, w={_show(w)})"
    with np.errstate(all="ignore"):
        p = _array(_call(label, proba, X, w, crash_hint=_crash_hint), label, (7,), "probability vector")
    expected = _sigmoid_ref(_bias(X) @ w)
    if not np.allclose(p, expected, rtol=1e-9):
        raise Fail(f"{label} returned {_show(p)}\nexpected {_show(expected)}",
                   hint="Add the bias column, take the logits add_bias(X) @ w, then sigmoid them.")
    cases = [(X, w, 0.5, "threshold 0.5"), (X, w, 0.8, "a strict threshold of 0.8"),
             (X, np.zeros(3), 0.5, "an untrained model: every p is exactly 0.5")]
    for Xc, wc, t, story in cases:
        label = f"predict(X {Xc.shape}, w={_show(wc)}, threshold={t})"
        with np.errstate(all="ignore"):
            raw = _call(label, pred, Xc, wc, t, crash_hint=_crash_hint)
        got = _array(raw, label, (len(Xc),), "label vector")
        want = (_sigmoid_ref(_bias(Xc) @ wc) > t).astype(int)
        if not np.array_equal(got, want):
            hint = "1 where predict_proba(X, w) > threshold, else 0. Use the threshold argument."
            if story.startswith("an untrained"):
                hint = "At p == threshold exactly, predict 0 (scikit-learn's rule): use >, not >=."
            raise Fail(f"{label} — {story}: returned {_show(got)}, expected {_show(want)}.", hint=hint)
        if np.asarray(raw).dtype.kind not in "iu":
            raise Fail(f"{label} returned {_show(np.asarray(raw))} with dtype {np.asarray(raw).dtype}; "
                       "labels must be integers.", hint="Convert the boolean mask: (p > threshold).astype(int).")


@MISSION.check("Sealed shortcuts — no borrowed classifier")
def _no_shortcuts(ctx):
    found = _sealed(ctx, SEALED_MODULES, SEALED_NAMES)
    if found:
        line, name = found
        raise Fail(f"Line {line} uses `{name}`. This mission is about building it yourself.",
                   hint="numpy only. The grader already compares you with a reference implementation.")
