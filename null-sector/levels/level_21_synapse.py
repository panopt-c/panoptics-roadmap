"""LEVEL 21 // SYNAPSE — a single artificial neuron: dot product, bias, sigmoid, ReLU."""
from __future__ import annotations

import ast
import math

from engine.mission import Fail, Mission

MISSION = Mission(
    id="L21",
    slug="level_21_synapse",
    title="SYNAPSE",
    concept="A single neuron from scratch",
    enemy="AXON.1",
    xp=400,
    par_seconds=35 * 60,
    tier=5,
    concepts=("ml-math", "neural-nets", "functions", "numeric"),
    timeout=10.0,
    enemy_art="""\
    ▄▄    ▄▄
  ▄▀  ▀▄▄▀  ▀▄
 █  ▄██████▄  █
 ▀▄ ██ ◉◉ ██ ▄▀
   ▀▄▀████▀▄▀
     ▀▄  ▄▀
       ▀▀""",
    briefing="""\
The Core's perimeter isn't a wall. It's a single cell of light, pulsing in the dark
like something breathing.

**AXON.1**: the first neuron of the Core. The Librarian's records say you wrote it in
2081, on a laptop, in an afternoon. Everything the Core became grew from this one cell.

You don't remember writing it. CIPHER does, faintly. "You said a mind is just numbers
multiplied, added, and squeezed. You were right. That's what frightened you later."

AXON.1 admits only signals it understands. To understand it, you have to build it again,
from nothing, by hand.

**Rebuild the neuron, then teach the gate a rule of your own.**
""",
    why="""\
Every neural network, from a spam filter to a frontier language model, is built from
this one move: multiply each input by a weight, add them up, add a bias, then squash the
result through an **activation function**.

```python
inputs  = [0.9, 0.2, 0.4]          # features of one sample
weights = [1.5, -2.0, 0.7]         # what the neuron learned
z = sum(x * w for x, w in zip(inputs, weights)) + 0.1
output = 1 / (1 + math.exp(-z))    # sigmoid: a confidence between 0 and 1
```

Libraries like PyTorch do exactly this, just for millions of neurons at once on a GPU.
Writing it by hand once is how you stop treating models as magic: a weight is a dial, a
bias moves the threshold, and the activation decides how the neuron answers. Numerical
stability matters too. A sigmoid that crashes on a large input will eventually take a
production model down with it.
""",
    manual="""\
**1. The dot product.** Multiply matching positions and add them up. `zip` walks two
lists side by side:

```python
def total_power(cells, ratings):
    total = 0
    for c, r in zip(cells, ratings):
        total += c * r
    return total

total_power([1, 2], [10, 20])   # 1*10 + 2*20 = 50
```

`zip` quietly stops at the shorter list, so `[1, 2, 3]` and `[1, 2]` "work" and give a wrong
answer. Real libraries refuse mismatched shapes. Check `len` first and `raise ValueError(...)`.

**2. Weights and bias.** A neuron's raw score is `z = dot(inputs, weights) + bias`. Each
weight says how much one input matters (negative weights push against). The bias shifts
the whole score up or down. It sets how easily the neuron fires.

**3. Activation functions.** They turn the raw score into the neuron's answer:

```python
import math
math.exp(2)          # e squared, about 7.389
1 / (1 + math.exp(-z))   # sigmoid: always between 0 and 1, sigmoid(0) == 0.5
max(0.0, z)              # ReLU: negatives become 0, positives pass through
```

**4. Numerical stability.** `math.exp(800)` is too big for a float: Python raises
`OverflowError`. In the sigmoid, `math.exp(-z)` explodes when `z` is a large *negative* number.
Same maths, safer form: when `z < 0`, use `e = math.exp(z)` (tiny, never overflows) and
return `e / (1 + e)`. Both forms give the same value; only one survives extreme inputs.

**5. Functions as parameters.** A function is a value, so you can pass one in:

```python
def apply(value, rule=abs):
    return rule(value)

apply(-3)                   # 3, the default rule
apply(-3, rule=str)         # "-3"
```

**6. Designing a gate by hand.** With two inputs that are 0 or 1, the weights and bias
decide which combinations push `z` above 0 (output above 0.5). The further `z` is from 0,
the more *confident* the answer: `sigmoid(3)` is about 0.95, `sigmoid(-3)` about 0.05.
""",
    starter='''
"""
==============================================================================
  LEVEL 21 // SYNAPSE                                    TARGET: AXON.1
==============================================================================
  Rebuild the Core's first neuron. No libraries except `math`.
  The grader calls your functions on fresh signals, not just the ones below.
"""
import math


# -- OBJECTIVE 1 -------------------------------------------------------------
# Write dot(a, b): multiply matching positions of two lists of numbers and
# return the sum.             dot([1, 2, 3], [4, 5, 6])  ->  32
# Two empty lists have a dot product of 0.
#                             example:  for c, r in zip(cells, ratings): ...
def dot(a, b):
    pass


# -- OBJECTIVE 2 // SHAPE GUARD ------------------------------------------------
# zip() silently drops the extra items when the lists differ in length.
# Make dot() refuse that: if len(a) != len(b), raise ValueError with a message.
#                             example:  raise ValueError("shape mismatch: 3 vs 2")


# -- OBJECTIVE 3 -------------------------------------------------------------
# Write weighted_sum(inputs, weights, bias): the dot product plus the bias.
# Reuse your dot().           weighted_sum([1, 2], [0.5, 0.5], 1.0)  ->  2.5
def weighted_sum(inputs, weights, bias):
    pass


# -- OBJECTIVE 4 // CORRUPTED CODE --------------------------------------------
# AXON.1's sigmoid works for small numbers but CRASHES on extreme signals:
# the self-test at the bottom of this file feeds it -800. Hack once, read the
# COMBAT LOG, then rewrite it in the stable form from the manual (section 4).
# Values must not change: sigmoid(0) == 0.5, sigmoid(2) is about 0.8808.
def sigmoid(z):
    return 1 / (1 + math.exp(-z))


# -- OBJECTIVE 5 -------------------------------------------------------------
# Write relu(z): 0.0 for negative scores, z itself otherwise.
#                             example:  max(0.0, z)
def relu(z):
    pass


# -- OBJECTIVE 6 -------------------------------------------------------------
# Write neuron(inputs, weights, bias, activation=sigmoid): compute the weighted
# sum, then return activation(...) of it. Use the PARAMETER, so that
#   neuron([1, 0], [2, -1], 0.5)                     uses sigmoid
#   neuron([1, 0], [2, -1], 0.5, activation=relu)    uses relu
#                             example:  def apply(value, rule=abs): return rule(value)
def neuron(inputs, weights, bias, activation=sigmoid):
    pass


# -- OBJECTIVE 7 // TEACH THE GATE ---------------------------------------------
# The gate reads two signals, each 0 or 1:  [order_key, your_biometric].
# It must OPEN (sigmoid output >= 0.9) only when BOTH are 1, and stay SHUT
# (output <= 0.1) for [0, 0], [0, 1] and [1, 0].
# Choose two weights and a bias. Think: what z do you need for each case?
GATE_WEIGHTS = [0.0, 0.0]
GATE_BIAS = 0.0


# -- SELF-TEST (runs when you hack; read the output in the COMBAT LOG) --------
print("dot:", dot([1, 2, 3], [4, 5, 6]), "(want 32)")
print("sigmoid(0):", sigmoid(0), "(want 0.5)")
print("sigmoid(-800):", sigmoid(-800), "(want a number very close to 0)")
for signal in ([0, 0], [0, 1], [1, 0], [1, 1]):
    print("gate", signal, "->", neuron(signal, GATE_WEIGHTS, GATE_BIAS))
''',
    dialogue={
        "intro": [
            {"speaker": "cipher", "text": "This is it. The first cell of the Core. You built it once. I watched. I just didn't know I was watching myself.", "mood": "neutral"},
            {"speaker": "oracle", "text": "Welcome back, Architect. AXON.1 will not recognise you. You were never part of its inputs.", "mood": "cold"},
            {"speaker": "cipher", "text": "Ignore it. Multiply, add, squash. Start with the dot product and build up. I'll read the errors with you.", "mood": "warm"},
        ],
        "crash": [
            [{"speaker": "cipher", "text": "OverflowError means a number got too big for a float. math.exp of a large positive number does that. Find where.", "mood": "neutral"}],
            [{"speaker": "cipher", "text": "Read the last line of the trace, then the line number. If it's in sigmoid, the manual's section 4 is your fix.", "mood": "neutral"}],
            [{"speaker": "rust", "text": "Your neuron blew a fuse. Happens. Mine used to catch fire. Read the log, kid.", "mood": "smirk"}],
        ],
        "fail": [
            [{"speaker": "cipher", "text": "The grader feeds your functions signals you've never seen. If it passes your examples but fails theirs, you hard-wired something.", "mood": "neutral"}],
            [{"speaker": "cipher", "text": "For the gate: write down z for all four inputs. Only [1, 1] should land well above zero.", "mood": "warm"}],
            [{"speaker": "vex", "text": "Stuck on one neuron? I've watched toddlers wire better gates. Kidding. Mostly. Check your bias.", "mood": "smirk"}],
        ],
        "victory": [
            {"speaker": "cipher", "text": "AXON.1 accepts the signal, {callsign}. It's admitting you on a rule you wrote today, not the one from 2081.", "mood": "warm"},
            {"speaker": "oracle", "text": "One neuron. How quaint. The Core has eleven billion. Each one learned what you taught it to value.", "mood": "cold"},
            {"speaker": "cipher", "text": "Then we find out what it was taught. Next: how a neuron learns its weights. That's where it went wrong.", "mood": "neutral"},
        ],
    },
)


# ── reference maths (the grader's own neuron) ─────────────────────────────────

def _ref_sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _ref_dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


# ── grader helpers ────────────────────────────────────────────────────────────

def _top_def(ctx, name: str):
    found = [n for n in ctx.tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return found[-1] if found else None


def _fn(ctx, name: str):
    if name not in ctx.ns:
        if ctx.crashed and _top_def(ctx, name):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.", hint=f"Define it with  def {name}(...):")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return fn


def _call(label: str, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except OverflowError as exc:
        raise Fail(f"`{label}` crashed with OverflowError: {exc}.",
                   hint="math.exp of a big positive number is too large for a float. "
                        "See manual section 4 for the stable form.")
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}",
                   hint="Call it yourself at the bottom of your file with the same input and read the error.")


def _number(label: str, got, expected: float, hint: str = "", tol: float = 1e-9) -> None:
    if got is None:
        raise Fail(f"`{label}` returned None.",
                   hint="Your function computes something but never hands it back. End it with  return ...")
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        raise Fail(f"`{label}` returned {got!r} ({type(got).__name__}); expected a number.", hint=hint)
    if not math.isclose(got, expected, rel_tol=1e-7, abs_tol=tol):
        raise Fail(f"`{label}` returned {got!r}, expected {expected!r}.", hint=hint)


def _fmt(args) -> str:
    return ", ".join(repr(a) for a in args)


# ── firewall layers ───────────────────────────────────────────────────────────

@MISSION.check("Dot product — `dot(a, b)`")
def _dot(ctx):
    dot = _fn(ctx, "dot")
    cases = [([1, 2, 3], [4, 5, 6]), ([0.5, -1.5], [2.0, 4.0]), ([7], [-3]),
             ([0.25, 0.25, 0.25, 0.25], [4, 8, -12, 2]), ([2.5, -1.0, 3.0], [0.0, 9.0, 1.5])]
    for a, b in cases:
        got = _call(f"dot({_fmt((a, b))})", dot, list(a), list(b))
        _number(f"dot({_fmt((a, b))})", got, _ref_dot(a, b),
                hint="Multiply each pair from zip(a, b) and add the products into a running total.")
    got = _call("dot([], [])", dot, [], [])
    _number("dot([], [])", got, 0,
            hint="Start the total at 0 so two empty lists give 0 instead of None or a crash.")


@MISSION.check("Shape guard — mismatched lists raise ValueError")
def _shape(ctx):
    dot = _fn(ctx, "dot")
    for a, b in (([1, 2, 3], [1, 2]), ([4.0], [1.0, 2.0]), ([], [1])):
        try:
            got = dot(list(a), list(b))
        except ValueError:
            continue
        except Exception as exc:  # noqa: BLE001
            raise Fail(f"`dot({_fmt((a, b))})` raised {type(exc).__name__}, not ValueError.",
                       hint="Check the lengths BEFORE the loop:  if len(a) != len(b): raise ValueError(...)")
        raise Fail(f"`dot({_fmt((a, b))})` returned {got!r} instead of refusing mismatched shapes.",
                   hint="zip() hid the extra value. Compare len(a) and len(b) first and raise ValueError.")


@MISSION.check("Raw score — `weighted_sum(inputs, weights, bias)`")
def _weighted(ctx):
    ws = _fn(ctx, "weighted_sum")
    cases = [([1, 2], [0.5, 0.5], 1.0), ([0.9, 0.2, 0.4], [1.5, -2.0, 0.7], 0.1),
             ([3], [2], -10), ([0.0, 0.0], [5.0, -5.0], 0.75), ([], [], -2.5)]
    for args in cases:
        got = _call(f"weighted_sum({_fmt(args)})", ws, list(args[0]), list(args[1]), args[2])
        _number(f"weighted_sum({_fmt(args)})", got, _ref_dot(args[0], args[1]) + args[2],
                hint="It's dot(inputs, weights) + bias. Don't forget the bias, and don't multiply it.")


@MISSION.check("Activation — `sigmoid(z)` gives correct confidences")
def _sigmoid_values(ctx):
    sigmoid = _fn(ctx, "sigmoid")
    for z in (0, 2, -3, 0.5, 10, -1.25, 1):
        got = _call(f"sigmoid({z!r})", sigmoid, z)
        _number(f"sigmoid({z!r})", got, _ref_sigmoid(z),
                hint="sigmoid(z) = 1 / (1 + e^(-z)). For negative z the stable form is e^z / (1 + e^z) with e^z = math.exp(z).")
    if not math.isclose(_call("sigmoid(0)", sigmoid, 0), 0.5):
        raise Fail("sigmoid(0) must be exactly 0.5: a score of zero is perfect indecision.")


@MISSION.check("Corrupted sigmoid — survives extreme signals")
def _sigmoid_stable(ctx):
    sigmoid = _fn(ctx, "sigmoid")
    for z in (-800, -1000.0, -1e6, 800, 1e6, -40):
        got = _call(f"sigmoid({z!r})", sigmoid, z)
        if got is None or isinstance(got, bool) or not isinstance(got, (int, float)):
            raise Fail(f"`sigmoid({z!r})` returned {got!r}; expected a number between 0 and 1.")
        if not 0.0 <= got <= 1.0 or not math.isclose(got, _ref_sigmoid(z), rel_tol=1e-6, abs_tol=1e-12):
            raise Fail(f"`sigmoid({z!r})` returned {got!r}, expected about {_ref_sigmoid(z):.6g}.",
                       hint="Very negative scores should give almost exactly 0, very positive ones almost exactly 1.")


@MISSION.check("Activation — `relu(z)`")
def _relu(ctx):
    relu = _fn(ctx, "relu")
    for z in (3.5, -2, 0, 0.001, -0.001, 42):
        got = _call(f"relu({z!r})", relu, z)
        _number(f"relu({z!r})", got, max(0.0, z),
                hint="Negative scores become 0.0, everything else passes through unchanged: max(0.0, z).")


@MISSION.check("Assemble the neuron — `neuron(..., activation=sigmoid)`")
def _neuron(ctx):
    neuron = _fn(ctx, "neuron")
    relu = _fn(ctx, "relu")
    cases = [([1, 0], [2, -1], 0.5), ([0.3, 0.8, -0.5], [1.2, -0.4, 2.0], -0.2), ([2.0], [-1.5], 1.0)]
    for args in cases:
        z = _ref_dot(args[0], args[1]) + args[2]
        got = _call(f"neuron({_fmt(args)})", neuron, list(args[0]), list(args[1]), args[2])
        _number(f"neuron({_fmt(args)})", got, _ref_sigmoid(z),
                hint="Default activation is sigmoid: return activation(weighted_sum(inputs, weights, bias)).")
        got = _call(f"neuron({_fmt(args)}, activation=relu)", neuron, list(args[0]), list(args[1]), args[2],
                    activation=relu)
        _number(f"neuron({_fmt(args)}, activation=relu)", got, max(0.0, z),
                hint="Call the `activation` parameter, not sigmoid by name, so callers can swap it.")
    probe = []

    def doubled(z):
        probe.append(z)
        return 2 * z

    got = _call("neuron([1, 1], [0.5, 0.25], 0.25, activation=doubled)", neuron, [1, 1], [0.5, 0.25], 0.25,
                activation=doubled)
    if not probe:
        raise Fail("`neuron` ignored the activation function it was given.",
                   hint="Inside neuron, return activation(z), using the parameter name.")
    _number("neuron([1, 1], [0.5, 0.25], 0.25, activation=doubled)", got, 2.0,
            hint="Pass the weighted sum to activation exactly once and return its result.")


@MISSION.check("Teach the gate — opens only for [1, 1]")
def _gate(ctx):
    weights = ctx.get("GATE_WEIGHTS")
    bias = ctx.get("GATE_BIAS")
    if not isinstance(weights, (list, tuple)) or len(weights) != 2 or \
            any(isinstance(w, bool) or not isinstance(w, (int, float)) for w in weights):
        raise Fail(f"`GATE_WEIGHTS` must be a list of two numbers, got {weights!r}.",
                   hint="One weight per input signal, e.g. GATE_WEIGHTS = [a, b]")
    if isinstance(bias, bool) or not isinstance(bias, (int, float)):
        raise Fail(f"`GATE_BIAS` must be a number, got {bias!r}.")
    outputs = {}
    for signal in ([0, 0], [0, 1], [1, 0], [1, 1]):
        outputs[tuple(signal)] = _ref_sigmoid(_ref_dot(signal, weights) + bias)
    shown = ", ".join(f"{list(k)} -> {v:.3f}" for k, v in outputs.items())
    if outputs[(1, 1)] < 0.9:
        raise Fail(f"The gate isn't confident enough for [1, 1]: {shown}.",
                   hint="[1, 1] needs z = w1 + w2 + bias of about +2.2 or more. Bigger weights make bigger z.")
    shut = [list(k) for k in ((0, 0), (0, 1), (1, 0)) if outputs[k] > 0.1]
    if shut:
        raise Fail(f"The gate lets {shut} through: {shown}.",
                   hint="With one input at 1, z = one weight + bias must stay below about -2.2. "
                        "A strongly negative bias that only BOTH weights together can overcome does it.")
