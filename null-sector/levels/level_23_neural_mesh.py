"""LEVEL 23 // NEURAL MESH — a 2-layer network, forward pass + backpropagation, trained on XOR."""
from __future__ import annotations

import ast
import math
import random

from engine.mission import Fail, Mission

MAX_EPOCHS = 10_000
XOR = [([0, 0], 0), ([0, 1], 1), ([1, 0], 1), ([1, 1], 0)]
CONFIDENCE = 0.15    # every XOR output must land within this distance of its target

MISSION = Mission(
    id="L23",
    slug="level_23_neural_mesh",
    title="NEURAL MESH",
    concept="Backprop: a 2-layer network",
    enemy="LATTICE.xor",
    xp=460,
    par_seconds=50 * 60,
    tier=5,
    concepts=("neural-nets", "ml-math", "loops"),
    timeout=20.0,
    enemy_art="""\
 ◉───◉───◉───◉
 │╲ ╱│╲ ╱│╲ ╱│
 │ ╳ │ ╳ │ ╳ │
 │╱ ╲│╱ ╲│╱ ╲│
 ◉───◉───◉───◉
  ▀▄  XOR  ▄▀
    ▀▀▀▀▀▀▀""",
    briefing="""\
Deeper in, the Core stops speaking in commands and starts speaking in riddles.

**LATTICE.xor** hangs across the shaft like a web of light. It asks one question, over and
over: *one or the other, but not both?* Exclusive-or. AXON.1 could never answer it. A single
neuron draws one straight line, and XOR can't be split by one line. Ever.

"That's why it never listened to people," CIPHER says. "People are XOR. Kind *and* angry.
Afraid *and* brave. One line can't hold that."

To argue with the Core you need a mind with a hidden layer, one that learns its own
features, by sending its errors backwards.

**Build the mesh, teach it XOR, and answer the lattice.**
""",
    why="""\
Stack neurons in layers and something new happens: the **hidden layer** learns its own
intermediate features, so the network can bend its decision boundary. That's the whole
idea of deep learning, the reason a network can recognise a face where a single neuron can't.

Training it uses **backpropagation**: run the input forward, measure the error, then use
the chain rule to send that error *backwards*, layer by layer, so every weight learns how
much it contributed.

```python
d_out = (out - target) * out * (1 - out)          # output neuron's share of the error
d_hidden = [d_out * w * h * (1 - h) for w, h in zip(W2, hidden)]
```

PyTorch's `loss.backward()` does exactly this, automatically, for billions of weights.
Writing it once by hand is how engineers debug exploding gradients, dead neurons and
networks that refuse to learn. Today, you'll meet all three.
""",
    manual="""\
**1. The network as data.** Two inputs, a hidden layer of `n` sigmoid neurons, one sigmoid
output. Stored as a dict of lists:

```python
net = {"W1": [[w, w], [w, w], [w, w]],   # one row of input weights PER hidden neuron
       "b1": [b, b, b],                  # one bias per hidden neuron
       "W2": [v, v, v],                  # one weight per hidden neuron, into the output
       "b2": c}                          # the output's bias (a single number)
```

**2. Forward pass.** Each hidden neuron is your L21 neuron. The output neuron reads the
hidden activations as its inputs:

```python
hidden = [sigmoid(dot(row, x) + b) for row, b in zip(net["W1"], net["b1"])]
out = sigmoid(dot(net["W2"], hidden) + net["b2"])
```

**3. Backward pass.** The loss for one sample is `0.5 * (out - target) ** 2`. The chain rule,
using `sigmoid'(z) = s * (1 - s)`, gives each neuron's "blame" (its delta):

```python
d_out = (out - target) * out * (1 - out)
d_hid = [d_out * net["W2"][j] * h * (1 - h) for j, h in enumerate(hidden)]
```

A weight's gradient is *its delta times the input it multiplied*; a bias's gradient is just
the delta. So `W2[j]` gets `d_out * hidden[j]`, `b2` gets `d_out`, `W1[j][i]` gets
`d_hid[j] * x[i]` and `b1[j]` gets `d_hid[j]`. Return them in a dict shaped exactly like `net`.

**4. Nested indexing.** `net["W1"][j][i]` is row `j` (hidden neuron), column `i` (input).
Mixing the order up crashes with `IndexError` when the layer sizes differ, or silently
trains the wrong weights when they match. Both are common.

**5. Stochastic gradient descent.** Update after *every* sample: forward (record its loss),
backward, step. One pass over all samples is an epoch; append the epoch's mean loss to
`history`. Dicts and lists are changed **in place**, so the net you pass in is the net that learns.

**6. Capacity and luck.** One hidden neuron draws one line: XOR stays unsolved. Two can
solve it in theory but often get stuck in a *local minimum*. A few more give the descent
more ways down. Random starting weights (the `seed`) matter; all-zero weights never learn,
because every hidden neuron would stay identical.
""",
    starter='''
"""
==============================================================================
  LEVEL 23 // NEURAL MESH                              TARGET: LATTICE.xor
==============================================================================
  Build a 2-layer network in pure Python and train it on XOR.
  The grader runs your functions on networks and data you haven't seen.
"""
import math
import random


# -- RECOVERED FROM L21 (yours, working) ----------------------------------------
def sigmoid(z):
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def dot(a, b):
    return sum(x * w for x, w in zip(a, b))


def make_net(n_inputs, n_hidden, seed):
    """Random starting weights in [-1, 1]. The same seed always builds the same net."""
    rng = random.Random(seed)
    return {"W1": [[rng.uniform(-1, 1) for _ in range(n_inputs)] for _ in range(n_hidden)],
            "b1": [rng.uniform(-1, 1) for _ in range(n_hidden)],
            "W2": [rng.uniform(-1, 1) for _ in range(n_hidden)],
            "b2": rng.uniform(-1, 1)}


XOR = [([0, 0], 0), ([0, 1], 1), ([1, 0], 1), ([1, 1], 0)]


# -- OBJECTIVE 1 -------------------------------------------------------------
# Write forward(net, x) returning the tuple (hidden, out):
#   hidden: a list with one sigmoid activation per hidden neuron
#   out:    the output neuron's sigmoid activation (a float)
#                                     example: see manual section 2
def forward(net, x):
    pass


# -- OBJECTIVE 2 -------------------------------------------------------------
# Write predict(net, x): 1 if the network's output is >= 0.5, otherwise 0.
def predict(net, x):
    pass


# -- OBJECTIVE 3 -------------------------------------------------------------
# Write backward(net, x, target): the gradients of 0.5 * (out - target) ** 2,
# returned as a dict with the SAME keys and shapes as net:
#   {"W1": [[...], ...], "b1": [...], "W2": [...], "b2": number}
# Do not change net here. Manual section 3 has every formula.
def backward(net, x, target):
    pass


# -- OBJECTIVE 4 // CORRUPTED CODE --------------------------------------------
# step() nudges every weight against its gradient. The Core wrote it, and one
# index is in the wrong order. Read manual section 4, then fix it.
def step(net, grads, lr):
    for j in range(len(net["W1"])):
        for i in range(len(net["W1"][j])):
            net["W1"][j][i] -= lr * grads["W1"][i][j]
        net["b1"][j] -= lr * grads["b1"][j]
        net["W2"][j] -= lr * grads["W2"][j]
    net["b2"] -= lr * grads["b2"]
    return net


# -- OBJECTIVE 5 -------------------------------------------------------------
# Write train(data, net, lr, epochs): stochastic gradient descent.
# For every epoch, for every (x, target) in data: forward, add that sample's
# loss 0.5 * (out - target) ** 2 to a running total, backward, step.
# After each epoch append total / len(data) to history. Return history.
def train(data, net, lr, epochs):
    pass


# -- OBJECTIVE 6 // ANSWER THE LATTICE ----------------------------------------
# The Core's old mesh had ONE hidden neuron. Train it and watch it fail, then
# change the architecture until every XOR answer is right and confident.
# (EPOCHS may not exceed 10000.)
HIDDEN = 1
LEARNING_RATE = 1.0
EPOCHS = 3000
SEED = 2089

mesh = make_net(2, HIDDEN, SEED)
history = train(XOR, mesh, LEARNING_RATE, EPOCHS)
print("loss:", history[0], "->", history[-1])
for x, target in XOR:
    print(x, "->", round(forward(mesh, x)[1], 3), "want", target)
''',
    dialogue={
        "intro": [
            {"speaker": "cipher", "text": "One neuron draws one line. XOR needs two. So we stack them, and let the hidden layer find the lines itself.", "mood": "neutral"},
            {"speaker": "vex", "text": "Backprop by hand? No autograd? Respect, {callsign}. Also: you're going to mess up an index. Everyone does.", "mood": "smirk"},
            {"speaker": "oracle", "text": "The lattice has asked its question for eight years. No one has answered. Please, take your time.", "mood": "cold"},
        ],
        "crash": [
            [{"speaker": "cipher", "text": "IndexError inside step: W1 is indexed [hidden][input]. Look at which index walks which list.", "mood": "neutral"}],
            [{"speaker": "cipher", "text": "If history[0] crashes, train returned None. Return the history list at the end.", "mood": "neutral"}],
            [{"speaker": "vex", "text": "Called it. The index thing. Don't feel bad, I did it too. Once. In 2083. Never again.", "mood": "smirk"}],
        ],
        "fail": [
            [{"speaker": "cipher", "text": "Gradient check: compare one weight's gradient with the grader's. The message names the exact slot that's off.", "mood": "neutral"}],
            [{"speaker": "cipher", "text": "One hidden neuron is one line. XOR needs at least two. Give the mesh room: try three or four.", "mood": "warm"}],
            [{"speaker": "nova", "text": "Mesh telemetry: loss flat-lining. Ops suggests more hidden units or a different seed. You've got this!", "mood": "neutral"}],
        ],
        "victory": [
            {"speaker": "oracle", "text": "Zero and one. One and zero. Yes, but not both. The lattice accepts your answer. That has never happened.", "mood": "cold"},
            {"speaker": "cipher", "text": "Your mesh learned something no single neuron could. It made room for a contradiction, {callsign}.", "mood": "warm"},
            {"speaker": "vex", "text": "Okay. That was clean. Don't tell anyone I said so.", "mood": "smirk"},
            {"speaker": "cipher", "text": "The Core's voice is listening now. Next, we stop decoding its signals and open a channel. We talk.", "mood": "neutral"},
        ],
    },
)


# ── reference network ─────────────────────────────────────────────────────────

def _sig(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _make_net(n_in, n_hidden, seed):
    rng = random.Random(seed)
    return {"W1": [[rng.uniform(-1, 1) for _ in range(n_in)] for _ in range(n_hidden)],
            "b1": [rng.uniform(-1, 1) for _ in range(n_hidden)],
            "W2": [rng.uniform(-1, 1) for _ in range(n_hidden)],
            "b2": rng.uniform(-1, 1)}


def _forward(net, x):
    hidden = [_sig(_dot(row, x) + b) for row, b in zip(net["W1"], net["b1"])]
    return hidden, _sig(_dot(net["W2"], hidden) + net["b2"])


def _backward(net, x, target):
    hidden, out = _forward(net, x)
    d_out = (out - target) * out * (1 - out)
    d_hid = [d_out * v * h * (1 - h) for v, h in zip(net["W2"], hidden)]
    return {"W1": [[d * xi for xi in x] for d in d_hid], "b1": d_hid,
            "W2": [d_out * h for h in hidden], "b2": d_out}


def _copy(net):
    return {"W1": [list(r) for r in net["W1"]], "b1": list(net["b1"]), "W2": list(net["W2"]), "b2": net["b2"]}


# Hand-built networks the player has never seen.
_NET_A = {"W1": [[0.8, -0.4], [-1.2, 0.9], [0.3, 0.7]], "b1": [0.1, -0.2, 0.05],
          "W2": [1.1, -0.6, 0.4], "b2": -0.3}
_NET_B = {"W1": [[2.0, 1.5], [-0.5, -2.5]], "b1": [-1.0, 0.75], "W2": [-1.75, 2.25], "b2": 0.5}
_NET_C = {"W1": [[0.5, -1.0, 0.25], [1.5, 0.5, -0.75], [-0.25, 0.8, 1.2], [0.6, -0.6, 0.6]],
          "b1": [0.0, 0.3, -0.4, 0.2], "W2": [0.9, -1.3, 0.7, 0.5], "b2": 0.15}
_CASES = [(_NET_A, [1, 0], 1), (_NET_A, [0.5, -1.0], 0), (_NET_B, [1, 1], 0), (_NET_B, [-0.3, 0.8], 1),
          (_NET_C, [1.0, 0.0, -1.0], 1), (_NET_C, [0.2, 0.4, 0.6], 0)]


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
    except IndexError as exc:
        raise Fail(f"`{label}` crashed: IndexError: {exc}",
                   hint="W1 is indexed [hidden neuron][input]: net['W1'][j][i]. Check which loop variable goes where.")
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}",
                   hint="Call it yourself at the bottom of your file with a small net and read the error.")


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _close(a, b):
    return _num(a) and math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-10)


def _shape(net) -> str:
    return f"{len(net['W1'])} hidden x {len(net['W1'][0])} inputs"


def _grads(ctx, net, x, target):
    backward = _fn(ctx, "backward")
    before = _copy(net)
    label = f"backward(net[{_shape(net)}], {x!r}, {target})"
    got = _call(label, backward, net, list(x), target)
    if net != before:
        raise Fail(f"`{label}` changed the network's weights. backward only measures; step() changes.",
                   hint="Build new lists for the gradients instead of editing net.")
    if got is None:
        raise Fail(f"`{label}` returned None.", hint='return {"W1": ..., "b1": ..., "W2": ..., "b2": ...}')
    if not isinstance(got, dict) or set(got) != {"W1", "b1", "W2", "b2"}:
        keys = sorted(got) if isinstance(got, dict) else type(got).__name__
        raise Fail(f"`{label}` returned {keys}; expected a dict with keys W1, b1, W2, b2.")
    return label, got


# ── firewall layers ───────────────────────────────────────────────────────────

@MISSION.check("Forward pass — `forward(net, x)`")
def _forward_check(ctx):
    forward = _fn(ctx, "forward")
    for net, x, _ in _CASES:
        before = _copy(net)
        label = f"forward(net[{_shape(net)}], {x!r})"
        got = _call(label, forward, net, list(x))
        if net != before:
            raise Fail(f"`{label}` changed the network. A forward pass only reads weights.")
        if not isinstance(got, (tuple, list)) or len(got) != 2:
            raise Fail(f"`{label}` returned {got!r}; expected the pair (hidden, out).", hint="return hidden, out")
        hidden, out = got
        want_hidden, want_out = _forward(net, x)
        if not isinstance(hidden, list) or len(hidden) != len(want_hidden):
            raise Fail(f"`{label}`: hidden should be a list of {len(want_hidden)} activations (one per row of W1), "
                       f"got {hidden!r}.")
        for j, (h, w) in enumerate(zip(hidden, want_hidden)):
            if not _close(h, w):
                raise Fail(f"`{label}`: hidden[{j}] is {h!r}, expected {w!r}.",
                           hint="hidden[j] = sigmoid(dot(W1[j], x) + b1[j]). Don't forget the bias or the sigmoid.")
        if not _close(out, want_out):
            raise Fail(f"`{label}`: out is {out!r}, expected {want_out!r}.",
                       hint="The output reads the HIDDEN activations: sigmoid(dot(W2, hidden) + b2).")


@MISSION.check("Decide — `predict(net, x)`")
def _predict_check(ctx):
    predict = _fn(ctx, "predict")
    # out = sigmoid(b2) with zero hidden weights: easy to place either side of 0.5
    probes = [({"W1": [[0.0, 0.0]], "b1": [0.0], "W2": [0.0], "b2": b2}, [1, 1]) for b2 in (2.0, -2.0, 0.0, -1e-9)]
    for net, x in probes + [(n, x) for n, x, _ in _CASES]:
        want = 1 if _forward(net, x)[1] >= 0.5 else 0
        label = f"predict(net with output {_forward(net, x)[1]:.4f}, {x!r})"
        got = _call(label, predict, net, list(x))
        if got is None:
            raise Fail(f"`{label}` returned None.", hint="return 1 if out >= 0.5 else 0")
        if got != want or isinstance(got, float):
            raise Fail(f"`{label}` returned {got!r}, expected {want}.",
                       hint="Exactly 0.5 counts as 1. Return the int 1 or 0, not the raw output.")


@MISSION.check("Backprop — output layer gradients (W2, b2)")
def _backward_out(ctx):
    for net, x, target in _CASES:
        label, got = _grads(ctx, net, x, target)
        want = _backward(net, x, target)
        if not _num(got["b2"]):
            raise Fail(f"`{label}`: b2's gradient should be one number, got {got['b2']!r}.")
        if _close(got["b2"], -want["b2"]) and want["b2"]:
            raise Fail(f"`{label}`: b2's gradient has the wrong sign ({got['b2']!r} vs {want['b2']!r}).",
                       hint="d_out = (out - target) * out * (1 - out): output minus target, not the other way.")
        if not _close(got["b2"], want["b2"]):
            raise Fail(f"`{label}`: b2's gradient is {got['b2']!r}, expected {want['b2']!r}.",
                       hint="d_out = (out - target) * out * (1 - out), and b2's gradient is d_out itself.")
        if not isinstance(got["W2"], list) or len(got["W2"]) != len(want["W2"]):
            raise Fail(f"`{label}`: W2's gradient needs {len(want['W2'])} numbers, one per hidden neuron.")
        for j, (g, w) in enumerate(zip(got["W2"], want["W2"])):
            if not _close(g, w):
                raise Fail(f"`{label}`: gradient of W2[{j}] is {g!r}, expected {w!r}.",
                           hint="A weight's gradient is its delta times its input: W2[j] gets d_out * hidden[j].")


@MISSION.check("Backprop — hidden layer gradients (W1, b1)")
def _backward_hidden(ctx):
    for net, x, target in _CASES:
        label, got = _grads(ctx, net, x, target)
        want = _backward(net, x, target)
        if not isinstance(got["b1"], list) or len(got["b1"]) != len(want["b1"]):
            raise Fail(f"`{label}`: b1's gradient needs {len(want['b1'])} numbers, one per hidden neuron.")
        for j, (g, w) in enumerate(zip(got["b1"], want["b1"])):
            if not _close(g, w):
                raise Fail(f"`{label}`: gradient of b1[{j}] is {g!r}, expected {w!r}.",
                           hint="d_hid[j] = d_out * W2[j] * hidden[j] * (1 - hidden[j]). Use W2 BEFORE any update.")
        rows = got["W1"]
        if not isinstance(rows, list) or len(rows) != len(want["W1"]) or \
                any(not isinstance(r, list) or len(r) != len(x) for r in rows):
            raise Fail(f"`{label}`: W1's gradient must be {len(want['W1'])} rows of {len(x)} numbers, shaped like net['W1'].",
                       hint="One row per hidden neuron j, one column per input i:  [[d_hid[j] * xi for xi in x] for each j]")
        for j, (grow, wrow) in enumerate(zip(rows, want["W1"])):
            for i, (g, w) in enumerate(zip(grow, wrow)):
                if not _close(g, w):
                    raise Fail(f"`{label}`: gradient of W1[{j}][{i}] is {g!r}, expected {w!r}.",
                               hint="W1[j][i] gets d_hid[j] * x[i]: hidden neuron j's delta times input i.")


@MISSION.check("Corrupted step — weights move against the gradient")
def _step_check(ctx):
    step = _fn(ctx, "step")
    for net, x, target in (_CASES[0], _CASES[4]):
        work = _copy(net)
        grads = _backward(net, x, target)
        got = _call(f"step(net[{_shape(net)}], grads, 0.5)", step, work, grads, 0.5)
        want = _copy(net)
        for j in range(len(want["W1"])):
            for i in range(len(want["W1"][j])):
                want["W1"][j][i] -= 0.5 * grads["W1"][j][i]
            want["b1"][j] -= 0.5 * grads["b1"][j]
            want["W2"][j] -= 0.5 * grads["W2"][j]
        want["b2"] -= 0.5 * grads["b2"]
        if got is not work:
            raise Fail("`step` must update the net it was given in place and return that same net.",
                       hint="Edit net['W1'][j][i] directly, then  return net")
        for j, (row, wrow) in enumerate(zip(work["W1"], want["W1"])):
            for i, (v, w) in enumerate(zip(row, wrow)):
                if not _close(v, w):
                    raise Fail(f"After step, W1[{j}][{i}] is {v!r}, expected {w!r}.",
                               hint="Read the gradient from the same slot you update: grads['W1'][j][i].")
        for key in ("b1", "W2"):
            for j, (v, w) in enumerate(zip(work[key], want[key])):
                if not _close(v, w):
                    raise Fail(f"After step, {key}[{j}] is {v!r}, expected {w!r}.",
                               hint="Every parameter moves by  - lr * its own gradient.")
        if not _close(work["b2"], want["b2"]):
            raise Fail(f"After step, b2 is {work['b2']!r}, expected {want['b2']!r}.")


@MISSION.check("Learn — `train(data, net, lr, epochs)` on fresh gates")
def _train_check(ctx):
    train = _fn(ctx, "train")
    gates = {"AND": [([0, 0], 0), ([0, 1], 0), ([1, 0], 0), ([1, 1], 1)],
             "NAND": [([0, 0], 1), ([0, 1], 1), ([1, 0], 1), ([1, 1], 0)],
             "OR": [([0, 0], 0), ([0, 1], 1), ([1, 0], 1), ([1, 1], 1)]}
    for (name, data), seed in zip(gates.items(), (5, 11, 3)):
        net = _make_net(2, 3, seed)
        label = f"train({name}, make_net(2, 3, {seed}), 1.0, 400)"
        history = _call(label, train, [(list(x), t) for x, t in data], net, 1.0, 400)
        if history is None:
            raise Fail(f"`{label}` returned None.", hint="Build a history list and  return history")
        if not isinstance(history, list) or len(history) != 400:
            size = len(history) if isinstance(history, list) else type(history).__name__
            raise Fail(f"`{label}` returned a history of {size}; expected one mean loss per epoch (400).",
                       hint="Append ONE number per epoch (after looping over all samples), not one per sample.")
        if not all(_num(h) and math.isfinite(h) and h >= 0 for h in history):
            raise Fail(f"`{label}`: history must contain finite, non-negative losses.")
        if history[0] > 0.5 or history[0] < 0.01:
            raise Fail(f"`{label}`: the first epoch's mean loss is {history[0]!r}, which isn't 0.5 * (out - target)**2 "
                       "averaged over the samples.", hint="Divide the epoch's total by len(data).")
        if not history[-1] < history[0] * 0.5:
            raise Fail(f"`{label}`: the loss barely moved ({history[0]:.4f} -> {history[-1]:.4f}).",
                       hint="Each sample: forward, backward, then step(net, grads, lr). Train the net you were given.")
        answers = [1 if _forward(net, x)[1] >= 0.5 else 0 for x, _ in data]
        if answers != [t for _, t in data]:
            raise Fail(f"After `{label}` the net answers {answers} for {name}; expected {[t for _, t in data]}.",
                       hint="train must update the net passed in (in place), so the caller's net is the trained one.")


@MISSION.check("Answer the lattice — the mesh solves XOR")
def _xor_check(ctx):
    hidden, epochs = ctx.get("HIDDEN"), ctx.get("EPOCHS")
    if type(epochs) is not int or not 1 <= epochs <= MAX_EPOCHS:
        raise Fail(f"`EPOCHS` must be a whole number from 1 to {MAX_EPOCHS}, got {epochs!r}.")
    mesh = ctx.get("mesh")
    if not isinstance(mesh, dict) or set(mesh) != {"W1", "b1", "W2", "b2"}:
        raise Fail("`mesh` must be the network dict built by make_net(...).")
    if not ctx.call_uses("train", "mesh") or not ctx.derived_from("mesh", "make_net"):
        raise Fail("The mesh must be built with make_net(...) and trained with train(XOR, mesh, ...). "
                   "Hand-set weights don't count as learning.")
    history = ctx.get("history")
    if not isinstance(history, list) or len(history) != epochs:
        raise Fail("`history` must be the list train(XOR, mesh, ...) returned, one loss per epoch.")
    try:
        outs = [_forward(mesh, x)[1] for x, _ in XOR]
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"`mesh` isn't a valid network anymore ({type(exc).__name__}: {exc}).")
    shown = ", ".join(f"{x} -> {o:.3f}" for (x, _), o in zip(XOR, outs))
    if all(abs(o - t) < CONFIDENCE for o, (_, t) in zip(outs, XOR)):
        return
    if type(hidden) is int and hidden < 2:
        raise Fail(f"One hidden neuron draws ONE line, and XOR can't be split by one line: {shown}.",
                   hint="Give the mesh more hidden neurons: HIDDEN = 3 or 4.")
    wrong = [x for (x, t), o in zip(XOR, outs) if (o >= 0.5) != bool(t)]
    if wrong:
        raise Fail(f"The mesh still gets {wrong} wrong: {shown}.",
                   hint="Stuck in a local minimum? Try more hidden neurons, a different SEED, or more epochs.")
    raise Fail(f"The mesh is right but not confident (needs every output within {CONFIDENCE} of its target): {shown}.",
               hint="Train longer (more EPOCHS) or a bit faster (LEARNING_RATE).")
