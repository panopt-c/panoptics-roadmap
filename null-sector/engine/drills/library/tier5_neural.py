"""Tier-5 drills: the numerical heart of training.

* t5-softmax-heat     softmax with temperature, numerically stable
* t5-cross-entropy    cross-entropy from probabilities and from logits (log-sum-exp)
* t5-activations      sigmoid / ReLU and their derivatives
* t5-gradient-step    MSE and one gradient-descent step for linear regression, then a training run
"""
from __future__ import annotations

import math

from engine.drills import Drill, register
from engine.drills.library.tier5_common import (
    build, dot, expect, expect_raises, function, invoke, line, matrix, near, num, overflow_errors, r,
    rounded, show, stable_softmax, vector,
)
from engine.mission import Fail


def _sums_off(got):
    """(message, hint) if `got` is a list of numbers that doesn't sum to 1, else None."""
    if isinstance(got, list) and got and all(isinstance(v, (int, float)) for v in got):
        total = sum(got)
        if abs(total - 1.0) > 1e-6:
            return (f"Those add up to {r(total, 4)}; probabilities must add up to 1.",
                    "Divide every exp() by the total of all the exp() values.")
    return None


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-softmax-heat — HEAT SINK
# ══════════════════════════════════════════════════════════════════════════════════════

def _ref_softmax(logits, temperature=1.0):
    if temperature <= 0:
        raise ValueError("temperature must be > 0")
    return stable_softmax([x / temperature for x in logits])


def _softmax_spot(got, args, kwargs):
    logits = args[0] if args else kwargs["logits"]
    temperature = kwargs.get("temperature", args[1] if len(args) > 1 else 1.0)
    total = sum(logits)
    if logits and total and near(got, [x / total for x in logits]):
        return ("You divided the raw logits by their sum. Softmax exponentiates FIRST: exp(x) / sum of exp(...).",
                "Logits can be negative; exp() makes everything positive before you normalise.")
    if temperature != 1.0 and near(got, stable_softmax([x * temperature for x in logits])):
        return ("You MULTIPLIED by the temperature. Divide the logits by it: small T sharpens, big T flattens.", "")
    if temperature != 1.0 and near(got, stable_softmax(list(logits))):
        return ("The temperature had no effect. Divide every logit by it before the softmax.", "")
    return _sums_off(got)


_SOFTMAX_MANUAL = """\
**Softmax turns raw scores (logits) into probabilities.** Exponentiate each one so they're all
positive, then divide by the total so they add up to 1:

```python
exps = [math.exp(x) for x in logits]
total = sum(exps)
probs = [e / total for e in exps]
```

**Why that crashes.** `math.exp(710)` is too big for a float: `OverflowError`. And
`math.exp(-800)` rounds to `0.0`, so a list of very negative logits divides by zero.

**The fix is free.** Softmax doesn't change if you subtract the same number from every logit
(the factor `exp(-c)` cancels top and bottom). Subtract the **maximum**: the biggest exponent
becomes `exp(0) = 1`, nothing overflows, and the total is at least 1.

```python
top = max(logits)
shifted = [x - top for x in logits]     # largest is now 0.0
```

**Temperature** is the knob on every LLM API. Divide the logits by `T` before the softmax:
`T < 1` sharpens (the model gets confident), `T > 1` flattens (it gets creative). `T` must be
positive; `T = 0` would divide by zero.
"""


def _build_softmax(rng):
    plain = [vector(rng, n, -4, 4) for n in (3, 4, rng.randint(5, 6))]
    plain_cases = [(v,) for v in plain] + [([num(rng, -2, 2)],), ([], ), ([1.5, 1.5, 1.5],)]
    temp_base = vector(rng, 4, -3, 3)
    temp_cases = [(temp_base, 0.5), (temp_base, 2.0), ({"logits": vector(rng, 3, -3, 3), "temperature": 0.25}),
                  ({"logits": vector(rng, 5, -3, 3), "temperature": 5.0})]
    hot_cases = [([1000.0, 999.0, 998.5],), ([-1200.0, -1201.0, -1203.0],), ([800.0, -800.0, 0.0],),
                 ({"logits": [12.0, 9.5, 3.0], "temperature": 0.01})]
    hot_cases.append(([round(rng.uniform(710, 900), 1) for _ in range(3)],))

    example = plain[0]
    prompt = f"""\
The reactor under the Monastery runs on a neural regulator, and the regulator just cooked
itself. Its logits spiked past 1000 and every `math.exp` in the firmware overflowed. NOVA has
the coolant team on standby. They need a softmax that can take the heat.

**Write** `softmax(logits, temperature=1.0)`:

- Return a new list of probabilities: `exp(x / T)` for each logit, divided by the total.
- The result always sums to 1. `[]` gives `[]`; a single logit gives `[1.0]`.
- It must survive logits like `[1000.0, 999.0]` and `[-1200.0, -1201.0]` without
  `OverflowError` or `ZeroDivisionError`.
- `temperature` must be positive: raise `ValueError` if it's `0` or negative.
- Don't change the list you're given.

**Regulator readout (this contract):**

```python
softmax({show(example)})
# ≈ {[r(p, 4) for p in _ref_softmax(example)]}
```
"""
    starter = '''
import math


def softmax(logits, temperature=1.0):
    """exp(x / temperature) for each logit, normalised to sum to 1. Numerically stable.

    Raise ValueError if temperature <= 0.
    """
    # your code
    pass


if __name__ == "__main__":
    print(softmax([2.0, 1.0, 0.1]))                 # ≈ [0.659, 0.2424, 0.0986]
    print(softmax([2.0, 1.0, 0.1], temperature=0.5))  # sharper
    print(softmax([1000.0, 999.0]))                 # must not crash
'''
    mission = build(
        title="HEAT SINK", enemy="REGULATOR.core", prompt=prompt, manual=_SOFTMAX_MANUAL, starter=starter,
        concepts=("ml-math", "numeric"),
        intro=[line("nova", "Reactor regulator's logits are past a thousand and climbing. Need a softmax that won't melt, {callsign}. Go!", "alarm"),
               line("cipher", "Shift before you exponentiate. The answer doesn't change; the overflow does.", "neutral")],
        victory=[line("nova", "Regulator's holding at a cool one-point-oh total. Coolant team says thanks. Contract closed!", "warm")],
    )

    @mission.check("softmax — logits to probabilities")
    def _plain_layer(ctx):
        expect(ctx, "softmax", plain_cases, _ref_softmax, spot=_softmax_spot, pure=True,
               hint="exp() each logit, add them up, divide each exp() by that total.")

    @mission.check("temperature — sharpen and flatten")
    def _temp_layer(ctx):
        expect(ctx, "softmax", temp_cases, _ref_softmax, spot=_softmax_spot,
               hint="Divide every logit by the temperature first, then softmax as usual.")
        for bad in (0, -1.0):
            expect_raises(ctx, "softmax", ([1.0, 2.0], bad), why="temperature must be positive",
                          hint="Check the temperature at the top:  if temperature <= 0: raise ValueError(...)")

    @mission.check("overheated logits — numerical stability")
    def _hot_layer(ctx):
        expect(ctx, "softmax", hot_cases, _ref_softmax, spot=_softmax_spot, errors=overflow_errors,
               hint="Subtract max(logits) from every logit before calling math.exp().")

    return mission


register(Drill("t5-softmax-heat", "HEAT SINK", 5, ("ml-math", "numeric"), 900, _build_softmax))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-cross-entropy — LOSS SIGNAL
# ══════════════════════════════════════════════════════════════════════════════════════

EPS = 1e-12


def _check_target(n, target):
    if not 0 <= target < n:
        raise ValueError("target out of range")


def _ref_ce(probs, target):
    _check_target(len(probs), target)
    return -math.log(max(probs[target], EPS))


def _logsumexp(xs):
    top = max(xs)
    return top + math.log(sum(math.exp(x - top) for x in xs))


def _ref_ce_logits(logits, target):
    _check_target(len(logits), target)
    return _logsumexp(logits) - logits[target]


def _ref_batch(batch, targets):
    if not batch or len(batch) != len(targets):
        raise ValueError("batch and targets must be non-empty and the same length")
    return sum(_ref_ce_logits(row, t) for row, t in zip(batch, targets)) / len(batch)


def _ce_spot(got, args, _kwargs):
    probs, target = args
    expected = _ref_ce(probs, target)
    if expected > 1e-9 and near(got, -expected):
        return ("Your loss is negative: you forgot the minus sign. log(p) is ≤ 0 for p ≤ 1, so the loss is -log(p).", "")
    p = max(probs[target], EPS)
    if near(got, -math.log10(p)):
        return ("That's log base 10. Cross-entropy uses the natural log: math.log(p) with no base.", "")
    if near(got, 1 - probs[target]):
        return ("That's 1 - p, not the cross-entropy. The loss is -log(p) for the true class.", "")
    return None


def _ce_logits_spot(got, args, _kwargs):
    logits, target = args
    expected = _ref_ce_logits(logits, target)
    if expected > 1e-9 and near(got, -expected):
        return ("Wrong sign. The loss is logsumexp(logits) - logits[target], which is never negative.", "")
    if near(got, -logits[target]):
        return ("You left out the log-sum-exp term. The loss is log(sum(exp(z))) - z[target].", "")
    return None


def _batch_spot(got, args, _kwargs):
    batch, targets = args
    if len(batch) > 1 and near(got, _ref_batch(batch, targets) * len(batch)):
        return ("You returned the SUM of the losses. Average them, so the loss doesn't grow with the batch size.",
                "Divide by len(batch).")
    return None


_CE_MANUAL = """\
**Cross-entropy measures surprise.** The model says "class 2 has probability `p`". If class 2
is the truth, the loss is `-log(p)`: near 0 when the model was confident and right, huge
when it was confident and wrong.

```python
-math.log(0.9)    # 0.105  good guess, small loss
-math.log(0.01)   # 4.605  bad guess, big loss
```

**log(0) is a crash.** A probability that rounds to `0.0` makes `math.log` raise `math domain
error`. Clip first: `max(p, 1e-12)`. Every ML library does this quietly.

**Better: never make the probability at all.** Models output logits `z`. Since
`p = exp(z_t) / sum(exp(z))`, the loss simplifies to

```python
loss = log(sum(exp(z))) - z[target]       # "log-sum-exp" minus the true logit
```

and log-sum-exp has its own stable form: `m + log(sum(exp(z_i - m)))` with `m = max(z)`.
That's how PyTorch's `CrossEntropyLoss` works.

**Negative indexes are a trap.** `probs[-1]` quietly reads the last class. A label of `-1`
usually means bad data, so check `0 <= target < len(probs)` and raise `ValueError`.

**Batches average.** The loss for a batch is the mean over its rows, so changing the batch size
doesn't change the scale of your gradients.
"""


def _prob_row(rng, n):
    raw = [rng.uniform(0.05, 1.0) for _ in range(n)]
    total = sum(raw)
    return [round(v / total, 4) for v in raw]


def _build_cross_entropy(rng):
    ce_cases = []
    for n in (3, 4, rng.randint(4, 6)):
        row = _prob_row(rng, n)
        ce_cases.append((row, rng.randrange(n)))
    ce_cases += [([0.0, 1.0, 0.0], 1), ([0.7, 0.3, 0.0], 2), ([0.25, 0.25, 0.25, 0.25], rng.randrange(4))]
    logit_cases = [(vector(rng, n, -5, 5), rng.randrange(n)) for n in (3, 4, 5)]
    logit_cases += [([900.0, 100.0, -50.0], 1), ([-1000.0, -1001.0], 0), ([710.0, 710.0], 1)]
    batch = [vector(rng, 3, -4, 4) for _ in range(rng.randint(4, 6))]
    targets = [rng.randrange(3) for _ in batch]
    batch_cases = [(batch, targets), ([[800.0, -800.0, 0.0], [0.0, 0.0, 0.0]], [1, 2]), ([vector(rng, 4)], [3])]

    sample = ce_cases[0]
    prompt = f"""\
The Core minimised its loss for forty years, and nobody checked what it was measuring. To
argue with it you have to speak its language: the number it was built to drive to zero.

**Write three functions:**

- `cross_entropy(probs, target)`: `-log(probs[target])` (natural log). Clip the probability to
  at least `1e-12` first, so a `0.0` gives about `27.63` instead of a crash.
- `cross_entropy_logits(logits, target)`: the same loss straight from raw logits, computed as
  `logsumexp(logits) - logits[target]`, stable for logits in the thousands.
- `batch_loss(batch_logits, targets)`: the **mean** of `cross_entropy_logits` over the rows.
  Raise `ValueError` if the batch is empty or the lengths differ.

`cross_entropy` and `cross_entropy_logits` raise `ValueError` unless `0 <= target < len(...)`.

**Intercepted training step (this contract):**

```python
cross_entropy({show(sample[0])}, {sample[1]})   # ≈ {r(_ref_ce(*sample), 4)}
```
"""
    starter = '''
import math


def cross_entropy(probs, target):
    """-log(probs[target]), with the probability clipped to at least 1e-12."""
    # your code
    pass


def cross_entropy_logits(logits, target):
    """logsumexp(logits) - logits[target], computed stably."""
    # your code
    pass


def batch_loss(batch_logits, targets):
    """Mean of cross_entropy_logits over the batch. ValueError if empty or mismatched."""
    # your code
    pass


if __name__ == "__main__":
    print(cross_entropy([0.1, 0.7, 0.2], 1))          # ≈ 0.3567
    print(cross_entropy_logits([2.0, 1.0, 0.1], 0))   # ≈ 0.417
    print(cross_entropy_logits([900.0, 100.0], 1))    # 800.0, no crash
    print(batch_loss([[2.0, 1.0], [0.0, 3.0]], [0, 1]))
'''
    mission = build(
        title="LOSS SIGNAL", enemy="OBJECTIVE.fn", prompt=prompt, manual=_CE_MANUAL, starter=starter,
        concepts=("ml-math", "numeric", "exceptions"),
        intro=[line("cipher", "This is the number the Core was built to minimise. Learn to compute it and you learn what it wanted.", "neutral")],
        victory=[line("cipher", "Stable, clipped, averaged. You measure loss the way the Core does now. Now we can argue with it.", "warm"),
                 line("oracle", "You have found my objective. Few think to look.", "cold")],
    )

    @mission.check("cross_entropy — surprise at the truth")
    def _ce_layer(ctx):
        expect(ctx, "cross_entropy", ce_cases, _ref_ce, spot=_ce_spot, errors=overflow_errors,
               hint="loss = -math.log(p) where p = probs[target], clipped with max(p, 1e-12).")
        expect_raises(ctx, "cross_entropy", ([0.5, 0.5], 2), why="class 2 doesn't exist",
                      hint="Check  0 <= target < len(probs)  before you index.")
        expect_raises(ctx, "cross_entropy", ([0.2, 0.3, 0.5], -1), why="a label of -1 is bad data",
                      hint="probs[-1] quietly reads the last class. Reject negative targets yourself.")

    @mission.check("cross_entropy_logits — straight from the logits")
    def _logits_layer(ctx):
        expect(ctx, "cross_entropy_logits", logit_cases, _ref_ce_logits, spot=_ce_logits_spot,
               errors=overflow_errors,
               hint="m = max(logits); lse = m + log(sum(exp(z - m))); loss = lse - logits[target].")
        expect_raises(ctx, "cross_entropy_logits", ([1.0, 2.0], 5), why="class 5 doesn't exist")

    @mission.check("batch_loss — average over the batch")
    def _batch_layer(ctx):
        expect(ctx, "batch_loss", batch_cases, _ref_batch, spot=_batch_spot, errors=overflow_errors,
               hint="Loss for each row with cross_entropy_logits, then divide the total by the number of rows.")
        expect_raises(ctx, "batch_loss", ([], []), why="an empty batch has no mean")
        expect_raises(ctx, "batch_loss", ([[1.0, 2.0], [0.5, 0.5]], [0]), why="2 rows but 1 target")

    return mission


register(Drill("t5-cross-entropy", "LOSS SIGNAL", 5, ("ml-math", "numeric", "exceptions"), 1200,
               _build_cross_entropy))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-activations — NEURON FIRMWARE
# ══════════════════════════════════════════════════════════════════════════════════════

def _ref_sigmoid(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _ref_sigmoid_grad(x):
    s = _ref_sigmoid(x)
    return s * (1.0 - s)


def _ref_relu(x):
    return float(x) if x > 0 else 0.0


def _ref_relu_grad(x):
    return 1.0 if x > 0 else 0.0


def _sigmoid_spot(got, args, _kwargs):
    (x,) = args
    if isinstance(got, (int, float)) and not 0.0 <= got <= 1.0:
        return (f"Sigmoid always lands between 0 and 1, but you returned {show(got)}.",
                "sigmoid(x) = 1 / (1 + exp(-x)). Check the sign inside exp().")
    if x != 0 and near(got, _ref_sigmoid(-x)):
        return ("You returned sigmoid(-x): the sign inside exp() is flipped. Big positive x should give nearly 1.", "")
    return None


def _sigmoid_grad_spot(got, args, _kwargs):
    (x,) = args
    if near(got, _ref_sigmoid(x)):
        return ("That's sigmoid(x) itself, not its slope.",
                "The derivative is s * (1 - s), where s = sigmoid(x).")
    if near(got, x * (1 - x)):
        return ("You computed x * (1 - x). The formula is s * (1 - s), where s = sigmoid(x), not x.", "")
    return None


def _relu_spot(got, args, _kwargs):
    (x,) = args
    if isinstance(got, (int, float)) and got < 0:
        return ("ReLU never outputs a negative number: anything below 0 becomes 0.0.", "max(0.0, x)")
    return None


def _relu_grad_spot(got, args, _kwargs):
    (x,) = args
    if x == 0 and near(got, 1.0):
        return ("At exactly 0 this contract says the gradient is 0.0: use x > 0, not x >= 0.",
                "ReLU has a kink at 0. Frameworks pick 0 there, and so do we.")
    if x < 0 and near(got, x):
        return ("You returned x. The slope of ReLU is a constant: 1.0 when x > 0, otherwise 0.0.", "")
    return None


_ACT_MANUAL = """\
**An activation bends a neuron's output.** Without one, stacking layers is pointless: a chain
of weighted sums is still one weighted sum. Two classics:

```python
sigmoid(x) = 1 / (1 + exp(-x))     # squashes anything into (0, 1)
relu(x)    = max(0.0, x)           # passes positives, blocks negatives
```

**Training needs their slopes (derivatives).** Backprop multiplies by them at every layer:

```python
s = sigmoid(x)
slope = s * (1 - s)                # sigmoid's derivative, at most 0.25 (at x = 0)
relu_slope = 1.0 if x > 0 else 0.0 # ReLU's derivative; we pick 0.0 at exactly 0
```

**The overflow trap.** For `x = -1000`, `exp(-x)` is `exp(1000)`: `OverflowError`. Rewrite the
formula so `exp` only ever sees a value ≤ 0:

```python
if x >= 0:
    return 1 / (1 + math.exp(-x))   # -x <= 0, safe
e = math.exp(x)                     # x < 0, safe
return e / (1 + e)                  # same value, multiplied top and bottom by exp(x)
```

**Why sigmoid fell out of fashion:** for big |x| its slope is almost 0, so deep networks stop
learning (vanishing gradients). ReLU's slope is a clean 1.0 for every positive input.
"""


def _build_activations(rng):
    mids = [(num(rng, -6, 6),) for _ in range(4)]
    sig_cases = [(0.0,)] + mids + [(35.0,), (-35.0,), (750.0,), (-750.0,), (-1000.0,)]
    grad_cases = [(0.0,)] + [(num(rng, -5, 5),) for _ in range(4)] + [(800.0,), (-800.0,)]
    relu_cases = [(num(rng, -9, -0.5),), (num(rng, 0.5, 9),), (0.0,), (num(rng, -3, 3),), (-0.01,)]
    relu_grad_cases = [(num(rng, 0.5, 9),), (num(rng, -9, -0.5),), (0.0,), (1e-9,), (-1e-9,)]

    x = mids[0][0]
    prompt = f"""\
The Order's drones are coming back online one neuron at a time, but their firmware lost its
activation tables. Every neuron needs a curve to bend its output and a slope to learn from.
CIPHER found the spec in your old notes. Your handwriting. Of course it was.

**Write four functions** (each takes one float, returns one float):

- `sigmoid(x)` = `1 / (1 + exp(-x))`. Must not crash for `x = -1000` or `x = 1000`.
- `sigmoid_grad(x)` = `s * (1 - s)` where `s = sigmoid(x)`.
- `relu(x)` = `x` if `x > 0`, otherwise `0.0`.
- `relu_grad(x)` = `1.0` if `x > 0`, otherwise `0.0` (including at exactly 0).

**Drone neuron readout (this contract):**

```python
sigmoid({x})        # ≈ {r(_ref_sigmoid(x), 6)}
sigmoid_grad({x})   # ≈ {r(_ref_sigmoid_grad(x), 6)}
```
"""
    starter = '''
import math


def sigmoid(x):
    """1 / (1 + exp(-x)), without overflowing for large |x|."""
    # your code
    pass


def sigmoid_grad(x):
    """The slope of sigmoid at x: s * (1 - s), where s = sigmoid(x)."""
    # your code
    pass


def relu(x):
    """x if x > 0, else 0.0."""
    # your code
    pass


def relu_grad(x):
    """1.0 if x > 0, else 0.0."""
    # your code
    pass


if __name__ == "__main__":
    print(sigmoid(0.0), sigmoid_grad(0.0))   # 0.5 0.25
    print(sigmoid(-1000.0))                  # ≈ 0.0, no crash
    print(relu(-2.0), relu(3.5))             # 0.0 3.5
    print(relu_grad(0.0), relu_grad(2.0))    # 0.0 1.0
'''
    mission = build(
        title="NEURON FIRMWARE", enemy="DEADFIRM.bin", prompt=prompt, manual=_ACT_MANUAL, starter=starter,
        concepts=("neural-nets", "ml-math", "numeric"),
        intro=[line("cipher", "Your notes, {callsign}. Four curves, four slopes. You wrote these once. Write them again.", "neutral")],
        victory=[line("cipher", "Drone neurons are firing. Every one of them bends its signal with your curves now.", "warm"),
                 line("rust", "Drones back online and I didn't pay for firmware. Best day this month.", "smirk")],
    )

    @mission.check("sigmoid — squash to (0, 1), even at ±1000")
    def _sigmoid_layer(ctx):
        expect(ctx, "sigmoid", sig_cases, _ref_sigmoid, spot=_sigmoid_spot, errors=overflow_errors,
               hint="Branch on the sign of x so math.exp() is only ever given a value ≤ 0.")

    @mission.check("sigmoid_grad — the slope backprop needs")
    def _grad_layer(ctx):
        expect(ctx, "sigmoid_grad", grad_cases, _ref_sigmoid_grad, spot=_sigmoid_grad_spot,
               errors=overflow_errors, hint="Call your own sigmoid(x) once, keep it as s, return s * (1 - s).")

    @mission.check("relu & relu_grad — the gate and its slope")
    def _relu_layer(ctx):
        expect(ctx, "relu", relu_cases, _ref_relu, spot=_relu_spot, hint="max(0.0, x) does it in one line.")
        expect(ctx, "relu_grad", relu_grad_cases, _ref_relu_grad, spot=_relu_grad_spot,
               hint="1.0 when x > 0, else 0.0. Strictly greater than.")

    return mission


register(Drill("t5-activations", "NEURON FIRMWARE", 5, ("neural-nets", "ml-math", "numeric"), 720,
               _build_activations))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-gradient-step — DESCENT VECTOR
# ══════════════════════════════════════════════════════════════════════════════════════

def _ref_predict(weights, bias, x):
    if len(weights) != len(x):
        raise ValueError("weights and features differ in length")
    return dot(weights, x) + bias


def _ref_mse(weights, bias, X, y):
    if not X or len(X) != len(y):
        raise ValueError("X and y must be non-empty and the same length")
    return sum((_ref_predict(weights, bias, x) - t) ** 2 for x, t in zip(X, y)) / len(X)


def _grads(weights, bias, X, y, *, factor=2.0, mean=True):
    n = len(X)
    errors = [_ref_predict(weights, bias, x) - t for x, t in zip(X, y)]
    scale = factor / n if mean else factor
    gw = [scale * sum(e * x[j] for e, x in zip(errors, X)) for j in range(len(weights))]
    gb = scale * sum(errors)
    return gw, gb


def _ref_step(weights, bias, X, y, lr):
    if not X or len(X) != len(y):
        raise ValueError("X and y must be non-empty and the same length")
    gw, gb = _grads(weights, bias, X, y)
    return ([w - lr * g for w, g in zip(weights, gw)], bias - lr * gb)


def _mse_spot(got, args, _kwargs):
    weights, bias, X, y = args
    errs = [_ref_predict(weights, bias, x) - t for x, t in zip(X, y)]
    if len(X) > 1 and near(got, sum(e * e for e in errs)):
        return ("That's the SUM of squared errors. MSE is the mean: divide by the number of samples.", "")
    if near(got, math.sqrt(sum(e * e for e in errs) / len(errs))):
        return ("You took the square root (that's RMSE). MSE stays squared.", "")
    if near(got, sum(abs(e) for e in errs) / len(errs)):
        return ("That's the mean ABSOLUTE error. Square each error instead: (prediction - target) ** 2.", "")
    return None


def _step_spot(got, args, _kwargs):
    weights, bias, X, y, lr = args
    gw, gb = _grads(weights, bias, X, y)
    if near(got, ([w + lr * g for w, g in zip(weights, gw)], bias + lr * gb)):
        return ("You stepped UPHILL: the loss gets worse. Gradient descent subtracts: w - lr * gradient.", "")
    gw1, gb1 = _grads(weights, bias, X, y, factor=1.0)
    if near(got, ([w - lr * g for w, g in zip(weights, gw1)], bias - lr * gb1)):
        return ("Your step is exactly half the size it should be: you dropped the 2.",
                "The derivative of (error)² is 2 · error · (d error). The 2 stays in.")
    gws, gbs = _grads(weights, bias, X, y, mean=False)
    if len(X) > 1 and near(got, ([w - lr * g for w, g in zip(weights, gws)], bias - lr * gbs)):
        return ("You summed the gradients without dividing by n, so the step grows with the dataset.",
                "MSE is a mean, so its gradient is a mean too: (2 / n) · Σ ...")
    if isinstance(got, tuple) and len(got) == 2 and near(got[0], [w - lr * g for w, g in zip(weights, gw)]):
        return ("Your weights are right but the bias is off. Its gradient is (2 / n) · Σ error (feature = 1).", "")
    return None


_GD_MANUAL = """\
**A linear model** predicts with a weighted sum plus a bias:

```python
prediction = w[0]*x[0] + w[1]*x[1] + ... + bias
```

**MSE (mean squared error)** scores the whole dataset: square each miss, then average.
Squaring makes every miss positive and punishes big misses hardest.

**The gradient says which way is uphill.** For MSE, with `error_i = prediction_i - y_i`:

```python
d_loss / d_w[j] = (2 / n) * sum(error_i * x_i[j]   for every sample i)
d_loss / d_bias = (2 / n) * sum(error_i            for every sample i)
```

The 2 comes from the square; the `x_i[j]` is how much `w[j]` moved that prediction.

**One step of gradient descent** walks a little way *downhill*:

```python
w_new = w - lr * gradient          # minus: we want the loss to go DOWN
```

`lr` (the learning rate) is the step size. Too big and you overshoot; too small and training
takes forever.

**Compute every gradient from the OLD weights**, then update. Updating `w[0]` before you
compute `w[1]`'s gradient mixes two different models. Return new lists; leave the caller's
alone.
"""


def _build_gradient_step(rng):
    d = rng.randint(2, 3)
    pred_cases = [(vector(rng, d), num(rng), vector(rng, d)) for _ in range(3)]
    pred_cases.append(([0.0] * d, 1.5, vector(rng, d)))

    def dataset(n, d):
        X = matrix(rng, n, d, -2, 2)
        y = [num(rng, -4, 4) for _ in range(n)]
        return X, y

    mse_cases = []
    for n in (4, 6):
        X, y = dataset(n, d)
        mse_cases.append((vector(rng, d, -1, 1), num(rng, -1, 1), X, y))
    X1, y1 = dataset(1, d)
    mse_cases.append((vector(rng, d), num(rng), X1, y1))

    step_cases = []
    for n, lr in ((5, 0.1), (8, 0.05), (3, 0.3)):
        X, y = dataset(n, d)
        step_cases.append((vector(rng, d, -1, 1), num(rng, -1, 1), X, y, lr))

    true_w = vector(rng, d, -3, 3, 1)
    true_b = num(rng, -2, 2, 1)
    train_X = matrix(rng, 24, d, -1, 1)
    train_y = [_ref_predict(true_w, true_b, x) for x in train_X]
    steps, lr = 400, 0.3

    prompt = f"""\
The Core didn't hate anyone. It minimised a loss function, and humans were the noise. To
understand that, you train a model yourself, one step downhill at a time.

**Write three functions** for a linear model `prediction = dot(weights, x) + bias`:

- `predict(weights, bias, x)`: one prediction. `ValueError` if `len(weights) != len(x)`.
- `mse(weights, bias, X, y)`: mean squared error over the rows of `X` and targets `y`.
- `gd_step(weights, bias, X, y, lr)`: one step of gradient descent on the MSE. Return a tuple
  `(new_weights, new_bias)`, with `new_weights` a **new** list:
  - `grad_w[j] = (2 / n) * sum((prediction_i - y_i) * X[i][j])`
  - `grad_b    = (2 / n) * sum(prediction_i - y_i)`
  - `new = old - lr * grad`

`mse` and `gd_step` raise `ValueError` if `X` is empty or `len(X) != len(y)`.

The final layer trains your model for {steps} steps (lr = {lr}) on data from a hidden rule.
If your step is right, you'll recover that rule to three decimal places.
"""
    starter = '''
def predict(weights, bias, x):
    """dot(weights, x) + bias. ValueError if the lengths differ."""
    # your code
    pass


def mse(weights, bias, X, y):
    """Mean of (predict(...) - target) ** 2 over every row. ValueError if empty or mismatched."""
    # your code
    pass


def gd_step(weights, bias, X, y, lr):
    """One gradient-descent step on the MSE. Return (new_weights, new_bias)."""
    # your code
    pass


if __name__ == "__main__":
    X = [[1.0, 2.0], [2.0, 0.0], [0.0, 1.0]]
    y = [5.0, 2.0, 2.0]                      # hidden rule: y = 1*x0 + 2*x1 + 0
    w, b = [0.0, 0.0], 0.0
    for step in range(200):
        w, b = gd_step(w, b, X, y, 0.1)
    print(w, b, mse(w, b, X, y))             # close to [1.0, 2.0] 0.0  and a loss near 0
'''
    mission = build(
        title="DESCENT VECTOR", enemy="MINIMA.daemon", prompt=prompt, manual=_GD_MANUAL, starter=starter,
        concepts=("ml-math", "neural-nets", "numeric"),
        intro=[line("cipher", "The Core minimised loss and called it purpose. Let's see what minimising feels like from the inside.", "neutral")],
        victory=[line("cipher", "Your model found the hidden rule on its own. That's all training is. That's all it ever was.", "warm"),
                 line("oracle", "Downhill. Always downhill. You understand me better now.", "cold")],
    )

    @mission.check("predict & mse — measure the miss")
    def _mse_layer(ctx):
        expect(ctx, "predict", pred_cases, _ref_predict, hint="sum(w * x for w, x in zip(weights, x)) + bias")
        expect_raises(ctx, "predict", ([1.0, 2.0], 0.0, [1.0, 2.0, 3.0]), why="3 features but 2 weights")
        expect(ctx, "mse", mse_cases, _ref_mse, spot=_mse_spot,
               hint="For each row: error = predict(...) - target; square it; average the squares.")
        expect_raises(ctx, "mse", ([1.0], 0.0, [], []), why="there are no samples to average")

    @mission.check("gd_step — one step downhill")
    def _step_layer(ctx):
        expect(ctx, "gd_step", step_cases, _ref_step, spot=_step_spot, pure=True,
               hint="Compute every error with the OLD weights, then both gradients, then subtract lr * gradient.")
        expect_raises(ctx, "gd_step", ([1.0], 0.0, [[1.0], [2.0]], [1.0], 0.1), why="2 rows but 1 target")

    @mission.check(f"training run — recover the hidden rule in {steps} steps")
    def _train_layer(ctx):
        fn = function(ctx, "gd_step")
        w, b = [0.0] * d, 0.0
        rw, rb = [0.0] * d, 0.0
        for step in range(steps):
            got = invoke(fn, f"gd_step(..., step {step + 1})", ([*w], b, train_X, train_y, lr))
            if not (isinstance(got, tuple) and len(got) == 2 and isinstance(got[0], list)):
                raise Fail(f"Step {step + 1} returned {show(got)}; expected a tuple (new_weights, new_bias).")
            w, b = got
            rw, rb = _ref_step(rw, rb, train_X, train_y, lr)
        if not near((w, b), (rw, rb), 1e-6):
            raise Fail(f"After {steps} steps your model sits at weights {show(rounded(w, 5))}, bias {show(round(b, 5))}; "
                       f"a correct step lands on {show(rounded(rw, 5))}, {show(round(rb, 5))}.",
                       hint="Each step must use only the weights it was given, never values left over from earlier calls.")
        if not near((w, b), (true_w, true_b), 1e-3):
            raise Fail(f"Training ended at {show(rounded(w, 4))}, {round(b, 4)}, short of the hidden rule.")

    return mission


register(Drill("t5-gradient-step", "DESCENT VECTOR", 5, ("ml-math", "neural-nets", "numeric"), 1200,
               _build_gradient_step))
