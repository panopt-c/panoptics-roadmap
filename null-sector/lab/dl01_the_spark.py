"""LAB DL01 // THE SPARK — a scalar autograd engine: numbers that remember how they were made."""
from __future__ import annotations

import ast
import math
import random

from engine.mission import Fail, Mission

MISSION = Mission(
    id="DL01",
    slug="dl01_the_spark",
    title="THE SPARK",
    concept="A scalar autograd engine",
    enemy="FLICKER.node",
    xp=320,
    par_seconds=45 * 60,
    tier=5,
    concepts=("classes", "neural-nets", "ml-math"),
    requires=(),
    timeout=10,
    run_as_main=False,
    enemy_art="""\
   ·   ▄▄█▄▄   ·
  · ▄▀ ░▒▓▒░ ▀▄ ·
   █ ▓ ◉   ◉ ▓ █
  · ▀▄ ░▒▓▒░ ▄▀ ·
   ·  ▀▀▄█▄▀▀  ·
    ·  ▐ ? ▌  ·""",
    briefing="""\
The last chapter of the Order's canon on learning machines is the thickest and the most burned.
Its title survived: **NEURAL LITURGY**. MOTHER ADA reads the first legible line aloud:
`loss.backward()`.

"The old world said those words a billion times a day," she says. "Like a prayer. Almost nobody
could tell you what they did. The Core was trained by people reciting."

In the cooling ducts, **FLICKER.node** throws off numbers with no history: results nobody can
trace back to a cause.

Ada lights one lamp. "A number that remembers its parents can be blamed. That's where learning
starts."

**Forge `Value`: a number that records how it was made and knows its local derivatives.**
""",
    why="""\
Every deep-learning framework is an **autograd engine** at heart. When you compute a loss in
PyTorch, each tensor quietly records the operation that produced it and its inputs;
`loss.backward()` walks that record backwards with the chain rule. You are building that
machinery one scalar at a time (Karpathy's *micrograd* is the famous version of this exercise).

```python
import torch
a = torch.tensor(2.0, requires_grad=True)
b = torch.tensor(-3.0, requires_grad=True)
c = a * b + a ** 2
c.backward()
a.grad, b.grad        # tensor(1.), tensor(2.)   dc/da = b + 2a, dc/db = a
```

Engineers who understand this can debug what others can't: a gradient that is `None` because a
tensor was detached, an in-place op that broke the graph, an exploding activation. Writing a
custom layer or loss (`torch.autograd.Function`) means writing exactly the `_backward` functions
you write today.
""",
    manual="""\
**1. A number that remembers.** A `Value` wraps a float and records where it came from:

```python
a = Value(2.0)
b = Value(-3.0)
c = a * b            # c.data == -6.0
c._prev              # {a, b}       the parents
c._op                # "*"          the operation
c.grad               # 0.0          d(final result)/dc, filled in later
```

Chained together, Values form a **computation graph**: every result points back to its inputs.

**2. Local derivatives.** Each operation knows how its output moves when an input moves a little:

```text
out = a + b      d out/d a = 1             d out/d b = 1
out = a * b      d out/d a = b             d out/d b = a
out = a ** k     d out/d a = k * a ** (k - 1)          (k is a plain number)
out = tanh(a)    d out/d a = 1 - out ** 2
out = relu(a)    d out/d a = 1 if a > 0 else 0         (0 at exactly 0, like PyTorch)
```

**3. The chain rule in one line.** If the final loss changes by `out.grad` per unit of `out`, and
`out` changes by `local` per unit of `a`, then the loss changes by `local * out.grad` per unit of
`a`. Each operation stores that rule as a small function, `out._backward`:

```python
def __mul__(self, other):
    other = other if isinstance(other, Value) else Value(other)   # allow  a * 2
    out = Value(self.data * other.data, (self, other), "*")

    def _backward():
        self.grad += other.data * out.grad      # local derivative times upstream grad
        other.grad += self.data * out.grad

    out._backward = _backward
    return out
```

The closure keeps `self`, `other` and `out` alive, so calling `out._backward()` later still works.
Try it by hand:

```python
a, b = Value(2.0), Value(-3.0)
c = a * b
c.grad = 1.0         # pretend c is the final loss
c._backward()
a.grad, b.grad       # (-3.0, 2.0)
```

**4. The common mistake: `=` instead of `+=`.** A Value can be used more than once. In `c = a * a`,
`self` and `other` are the *same* object, and both lines of `_backward` add blame to it:
`a.grad` must end up `2 * a.data * c.grad`. Write `self.grad = ...` and the second line overwrites
the first: half the gradient silently disappears. Gradients from different paths **add up**.

**5. Plain numbers and the reflected operators.** `a + 2` calls `a.__add__(2)`: wrap the 2 in a
Value. `2 + a` first tries `int.__add__`, which fails, so Python calls `a.__radd__(2)`. The starter
already builds `-a`, `a - b`, `2 * a`, `a / b` from your primitives: `a / b` is `a * b ** -1`.

**6. tanh without overflow.** `math.tanh(x)` is safe for any x. The textbook formula
`(e^2x - 1) / (e^2x + 1)` overflows at `x = 400`. The derivative is written with the *output*:
`1 - t ** 2` where `t = math.tanh(x)`.

**7. The PyTorch version** of a hand-written operation, so the skill transfers:

```python
class Square(torch.autograd.Function):
    @staticmethod
    def forward(ctx, a):
        ctx.save_for_backward(a)
        return a * a
    @staticmethod
    def backward(ctx, out_grad):
        (a,) = ctx.saved_tensors
        return 2 * a * out_grad          # local derivative times upstream grad
```

torch, jax and micrograd are sealed here. Don't define `__eq__` on Value: it makes Values
unhashable, and `_prev` is a set.
""",
    starter='''
"""
==============================================================================
  LAB DL01 // THE SPARK                                TARGET: FLICKER.node
==============================================================================
  A scalar autograd engine: the heart of PyTorch, in pure Python.
  Only `math` is needed. torch, jax and micrograd are sealed.
  The grader builds expressions from YOUR Value class with fresh random
  numbers and checks every derivative against finite differences.
"""
import math


class Value:
    """One number in a computation graph. The grader reads these exact names:

      data       the number itself, always a float
      grad       d(final output) / d(this value); starts at 0.0
      _prev      set of the Values this one was computed from
      _op        label of the operation that made it: "+", "*", "**2", "tanh", "relu"
      _backward  function that pushes out.grad into the parents' .grad
    """

    # -- OBJECTIVE 1 ---------------------------------------------------------
    def __init__(self, data, _children=(), _op=""):
        """Value(3) -> data 3.0, grad 0.0, _prev set(), _op "", _backward does nothing."""
        # TODO: self.data = float(data)        self.grad = 0.0
        #       self._backward = lambda: None
        #       self._prev = set(_children)    self._op = _op
        raise NotImplementedError("OBJECTIVE 1: Value.__init__")

    def __repr__(self):
        return f"Value(data={self.data:.4g}, grad={self.grad:.4g})"

    # -- OBJECTIVE 2 ---------------------------------------------------------
    def __add__(self, other):
        """out = self + other.   d out/d self = 1,  d out/d other = 1.

            a, b = Value(2.0), Value(-3.0)
            c = a + b                       # c.data == -1.0, c._prev == {a, b}
            c.grad = 1.0; c._backward()     # a.grad == 1.0, b.grad == 1.0
        """
        other = other if isinstance(other, Value) else Value(other)   # allow  a + 2
        # TODO: out = Value(..., (self, other), "+")
        #       def _backward(): ...        (+= into self.grad and other.grad)
        #       out._backward = _backward
        #       return out
        raise NotImplementedError("OBJECTIVE 2: __add__")

    # -- OBJECTIVE 3 ---------------------------------------------------------
    def __mul__(self, other):
        """out = self * other.   d out/d self = other.data,  d out/d other = self.data.

            c = Value(2.0) * Value(-3.0)    # c.data == -6.0
            c.grad = 1.0; c._backward()     # parents' grads: -3.0 and 2.0
        `other` may be a plain number, like in __add__.
        """
        # TODO
        raise NotImplementedError("OBJECTIVE 3: __mul__")

    # -- OBJECTIVE 4 ---------------------------------------------------------
    def __pow__(self, k):
        """out = self ** k for a plain number k (int or float).
        d out/d self = k * self.data ** (k - 1).   Label the op f"**{k}".

            c = Value(3.0) ** 2             # c.data == 9.0
            c.grad = 1.0; c._backward()     # parent's grad == 6.0
        """
        assert isinstance(k, (int, float)), "only plain-number powers are supported"
        # TODO
        raise NotImplementedError("OBJECTIVE 4: __pow__")

    # -- OBJECTIVE 5 // CORRUPTED CODE ---------------------------------------
    # FLICKER.node wrote this activation. The forward value is right; the
    # gradient is not. Check the derivative of tanh in the manual and fix it.
    def tanh(self):
        t = math.tanh(self.data)
        out = Value(t, (self,), "tanh")

        def _backward():
            self.grad += (1 - t) * out.grad

        out._backward = _backward
        return out

    # -- OBJECTIVE 6 ---------------------------------------------------------
    def relu(self):
        """max(0, x).   Gradient: 1 where x > 0, else 0 (also at exactly 0).

            Value(-2.0).relu().data == 0.0      Value(3.0).relu().data == 3.0
        """
        # TODO: label the op "relu"
        raise NotImplementedError("OBJECTIVE 6: relu")

    # -- GIVEN: built from your primitives, nothing to change ----------------
    def __neg__(self):              # -a
        return self * -1

    def __sub__(self, other):       # a - b
        return self + (-other)

    def __rsub__(self, other):      # 2 - a
        return (-self) + other

    def __radd__(self, other):      # 2 + a
        return self + other

    def __rmul__(self, other):      # 2 * a
        return self * other

    def __truediv__(self, other):   # a / b  ==  a * b ** -1
        return self * other ** -1

    def __rtruediv__(self, other):  # 2 / a
        return self ** -1 * other
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "The last chapter, {callsign}. The one the old world recited without reading. We start smaller than a neuron: one number."},
            {"speaker": "ada", "mood": "smirk",
             "text": "Why does a number need a memory? Because when the answer is wrong, you must know whom to blame, and by how much."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "The grader builds expressions out of your Value class with random numbers, then nudges each input to check your derivatives."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "'unsupported operand' means a plain number met a Value. Wrap it: other if isinstance(other, Value) else Value(other)."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "AttributeError on .data: something in _prev isn't a Value. Only Values go into the children tuple."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "The COMBAT LOG names the line that failed. Read it before you change anything."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "a * a. One object, two roles. If its gradient came out half as big as it should, ask what `=` did to the first half."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Local derivative times out.grad. Forget the out.grad factor and every gradient is right only when upstream is 1."}],
            [{"speaker": "ada", "mood": "smirk",
              "text": "tanh's slope is written with its own output: 1 - t squared. FLICKER dropped the square. Small sins compound."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Every number in that graph can now say where it came from and how much it mattered. That is the spark."},
            {"speaker": "ada", "mood": "neutral",
             "text": "You ran each _backward by hand. Next we teach the graph to run them itself, in the right order. Order is everything."},
            {"speaker": "cipher", "mood": "smirk",
             "text": "FLICKER.node is just a flicker now. First verse of the Liturgy, re-inked. The next page is titled CHAIN RULE."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

SEALED_MODULES = {"torch", "jax", "micrograd", "autograd", "tensorflow", "sympy"}
TOL = dict(rel_tol=1e-9, abs_tol=1e-12)


def _short(value, limit: int = 120) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _num(x) -> str:
    return f"{x:.6g}" if isinstance(x, (int, float)) and not isinstance(x, bool) else _short(x, 60)


def _value_class(ctx):
    if "Value" not in ctx.ns:
        defined = any(isinstance(n, ast.ClassDef) and n.name == "Value" for n in ctx.tree.body)
        if ctx.crashed and defined:
            raise Fail("`Value` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail("No class named `Value` found.", hint="Keep the starter's  class Value:  line.")
    cls = ctx.ns["Value"]
    if not isinstance(cls, type):
        raise Fail("`Value` exists but isn't a class.", hint="Define it with  class Value:")
    return cls


def _crash_hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, NotImplementedError):
        return "That's still the starter stub. Replace the `raise NotImplementedError(...)` line with your code."
    if isinstance(exc, TypeError) and "unsupported operand" in msg:
        return ("A plain number met a Value. Wrap numbers first: "
                "other = other if isinstance(other, Value) else Value(other).")
    if isinstance(exc, TypeError) and "unhashable" in msg:
        return "Values must be hashable to live in the _prev set. Don't define __eq__ on Value."
    if isinstance(exc, AttributeError):
        return "Every Value needs data, grad, _prev, _op and _backward, set in __init__."
    if isinstance(exc, OverflowError):
        return "math.tanh(x) never overflows; the exp-based formula does at large x. Use math.tanh."
    if isinstance(exc, RecursionError):
        return "Something calls itself forever. Check that _backward doesn't call out._backward()."
    return "Run the same lines in your own file and read the full error."


def _run(label: str, thunk):
    try:
        return thunk()
    except Fail:
        raise
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` raised {type(exc).__name__}: {exc}", hint=_crash_hint(exc))


def _attr(v, name: str, label: str):
    if not hasattr(v, name):
        raise Fail(f"`{label}` has no attribute `{name}`.",
                   hint="__init__ must set self.data, self.grad, self._prev, self._op and self._backward.")
    return getattr(v, name)


def _data(V, v, label: str) -> float:
    if not isinstance(v, V):
        raise Fail(f"`{label}` returned {_short(v)}, not a Value.",
                   hint="Every operation returns a new Value: out = Value(result, (self, other), op).")
    data = _attr(v, "data", label)
    if not isinstance(data, (int, float)) or isinstance(data, bool):
        raise Fail(f"`{label}`.data is {_short(data)}; expected a plain number.",
                   hint="Compute with the parents' .data: self.data * other.data, not self * other.")
    return float(data)


def _expect(label: str, what: str, got, expected: float, hint: str):
    if not isinstance(got, (int, float)) or isinstance(got, bool) or not math.isclose(got, expected, **TOL):
        raise Fail(f"{label}: {what} is {_num(got)}, expected {_num(expected)}.", hint=hint)


def _prev_ids(v, label: str) -> set:
    prev = _attr(v, "_prev", label)
    try:
        return {id(p) for p in prev}
    except TypeError:
        raise Fail(f"`{label}`._prev is {_short(prev)}; expected a set of Values.",
                   hint="self._prev = set(_children)")


def _local(V, label: str, out, upstream: float):
    """Set out.grad and run its own _backward once, like one step of the chain rule."""
    out.grad = upstream
    back = _attr(out, "_backward", label)
    if not callable(back):
        raise Fail(f"`{label}`._backward isn't a function.", hint="Assign the inner function: out._backward = _backward")
    _run(f"({label})._backward()", back)


ACCUMULATE = ("Use += in _backward. When a Value is used twice (a + a, a * a), both contributions must add up; "
              "= keeps only the last one.")


def _topo(V, root) -> list:
    """Iterative post-order DFS over _prev: the grader's own reference ordering."""
    order, seen, stack = [], set(), [(root, False)]
    while stack:
        node, done = stack.pop()
        if done:
            order.append(node)
            continue
        if id(node) in seen:
            continue
        seen.add(id(node))
        stack.append((node, True))
        for child in getattr(node, "_prev", ()):
            if isinstance(child, V) and id(child) not in seen:
                stack.append((child, False))
    return order


# ── random expressions: built once with Values, once with floats ──────────────────

def _gen(rng: random.Random, depth: int, n_leaves: int):
    if depth == 0 or rng.random() < 0.2:
        if rng.random() < 0.8:
            return ("leaf", rng.randrange(n_leaves))
        return ("const", round(rng.uniform(-2, 2), 2))
    kind = rng.choice(("add", "mul", "sub", "div", "pow", "tanh", "relu", "neg", "radd", "rmul"))
    if kind in ("add", "mul", "sub", "div"):
        return (kind, _gen(rng, depth - 1, n_leaves), _gen(rng, depth - 1, n_leaves))
    if kind == "pow":
        return (kind, _gen(rng, depth - 1, n_leaves), rng.choice((2, 3)))
    if kind in ("radd", "rmul"):
        return (kind, round(rng.uniform(-2, 2), 2), _gen(rng, depth - 1, n_leaves))
    return (kind, _gen(rng, depth - 1, n_leaves))


def _eval(e, leaves, tanh, relu, kinks=None):
    kind = e[0]
    if kind == "leaf":
        return leaves[e[1]]
    if kind == "const":
        return e[1]
    if kind in ("radd", "rmul"):
        x = _eval(e[2], leaves, tanh, relu, kinks)
        return e[1] + x if kind == "radd" else e[1] * x
    a = _eval(e[1], leaves, tanh, relu, kinks)
    if kind == "pow":
        return a ** e[2]
    if kind == "tanh":
        return tanh(a)
    if kind == "relu":
        if kinks is not None:
            kinks.append(abs(a))
        return relu(a)
    if kind == "neg":
        return -a
    b = _eval(e[2], leaves, tanh, relu, kinks)
    if kind == "add":
        return a + b
    if kind == "mul":
        return a * b
    if kind == "sub":
        return a - b
    return a / (b * b + 1.0)   # "div": a denominator that never reaches zero


def _show_expr(e) -> str:
    kind = e[0]
    if kind == "leaf":
        return "xyzw"[e[1]]
    if kind == "const":
        return f"{e[1]:g}"
    if kind == "radd":
        return f"({e[1]:g} + {_show_expr(e[2])})"
    if kind == "rmul":
        return f"({e[1]:g} * {_show_expr(e[2])})"
    if kind == "pow":
        return f"{_show_expr(e[1])}**{e[2]}"
    if kind in ("tanh", "relu"):
        return f"{_show_expr(e[1])}.{kind}()"
    if kind == "neg":
        return f"-{_show_expr(e[1])}"
    a, b = _show_expr(e[1]), _show_expr(e[2])
    if kind == "div":
        return f"({a} / ({b}*{b} + 1))"
    return f"({a} {'+' if kind == 'add' else '*' if kind == 'mul' else '-'} {b})"


def _float_f(e):
    return lambda xs: _eval(e, xs, math.tanh, lambda a: max(0.0, a))


def _central(f, xs, h=1e-6):
    grads = []
    for i in range(len(xs)):
        up, down = list(xs), list(xs)
        up[i] += h
        down[i] -= h
        grads.append((f(up) - f(down)) / (2 * h))
    return grads


def _expressions(seed: int, count: int, n_leaves: int = 3, depth: int = 4):
    """Expressions whose float value is moderate and whose ReLU inputs sit away from the kink."""
    rng = random.Random(seed)
    out = []
    while len(out) < count:
        e = _gen(rng, depth, n_leaves)
        if not any(k in repr(e) for k in ("'leaf', 0", "'leaf', 1")):
            continue
        xs = [round(rng.uniform(-1.5, 1.5), 3) for _ in range(n_leaves)]
        kinks: list = []
        value = _eval(e, xs, math.tanh, lambda a: max(0.0, a), kinks)
        if abs(value) > 1e4 or any(k < 1e-3 for k in kinks):
            continue
        out.append((e, xs))
    return out


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Spark — `Value(x)` holds a float and an empty history")
def _spark(ctx):
    V = _value_class(ctx)
    for x in (3, -1.5, 0, random.Random(11).uniform(-50, 50)):
        label = f"Value({x!r})"
        v = _run(label, lambda: V(x))
        data = _attr(v, "data", label)
        if not isinstance(data, float):
            raise Fail(f"`{label}.data` is {_short(data)} ({type(data).__name__}); expected the float {float(x)!r}.",
                       hint="Store self.data = float(data), so every Value is a float.")
        _expect(label, ".data", data, float(x), "Store the number you were given in self.data.")
        _expect(label, ".grad", _attr(v, "grad", label), 0.0,
                "Every Value starts with self.grad = 0.0: nothing has flowed back into it yet.")
        if _prev_ids(v, label):
            raise Fail(f"`{label}._prev` should be empty: a leaf has no parents.", hint="self._prev = set(_children)")
        if _attr(v, "_op", label) != "":
            raise Fail(f"`{label}._op` is {_short(v._op)}; a leaf's op is \"\".", hint="self._op = _op (default \"\").")
        back = _attr(v, "_backward", label)
        if not callable(back):
            raise Fail(f"`{label}._backward` isn't callable.", hint="self._backward = lambda: None")
        _run(f"{label}._backward()", back)
    a, b = V(1.0), V(2.0)
    c = _run("Value(3.0, (a, b), '+')", lambda: V(3.0, (a, b), "+"))
    if _prev_ids(c, "Value(3.0, (a, b), '+')") != {id(a), id(b)}:
        raise Fail("`Value(3.0, (a, b), '+')._prev` should be {a, b}.", hint="self._prev = set(_children)")
    if c._op != "+":
        raise Fail(f"`Value(3.0, (a, b), '+')._op` is {_short(c._op)}; expected '+'.", hint="self._op = _op")


def _binary(ctx, op: str, seed: int):
    V = _value_class(ctx)
    rng = random.Random(seed)
    fwd = (lambda p, q: p + q) if op == "+" else (lambda p, q: p * q)
    grads = (lambda p, q: (1.0, 1.0)) if op == "+" else (lambda p, q: (q, p))
    rule = ("d(a + b)/da = 1 and d(a + b)/db = 1, each times out.grad." if op == "+"
            else "d(a * b)/da = b.data and d(a * b)/db = a.data, each times out.grad.")
    for _ in range(4):
        x, y = round(rng.uniform(-5, 5), 3), round(rng.uniform(-5, 5), 3)
        g = round(rng.uniform(-3, 3), 3)
        a, b = V(x), V(y)
        label = f"Value({x}) {op} Value({y})"
        c = _run(label, lambda: fwd(a, b))
        _expect(label, ".data", _data(V, c, label), fwd(x, y), f"Compute the result from self.data and other.data.")
        if _prev_ids(c, label) != {id(a), id(b)}:
            raise Fail(f"`({label})._prev` should hold exactly the two parents.",
                       hint=f"Create the output as Value(result, (self, other), \"{op}\").")
        if getattr(c, "_op", None) != op:
            raise Fail(f"`({label})._op` is {_short(getattr(c, '_op', None))}; expected {op!r}.",
                       hint=f"Pass \"{op}\" as the third argument when you create the output Value.")
        _local(V, label, c, g)
        ga, gb = grads(x, y)
        _expect(f"after c = {label}; c.grad = {g}; c._backward()", "a.grad", a.grad, ga * g, rule)
        _expect(f"after c = {label}; c.grad = {g}; c._backward()", "b.grad", b.grad, gb * g, rule)
    # plain numbers on either side
    x, k, g = round(rng.uniform(-5, 5), 3), round(rng.uniform(-5, 5), 3), round(rng.uniform(-3, 3), 3)
    for label, make in ((f"Value({x}) {op} {k}", lambda a: fwd(a, k)), (f"{k} {op} Value({x})", lambda a: fwd(k, a))):
        a = V(x)
        c = _run(label, lambda: make(a))
        _expect(label, ".data", _data(V, c, label), fwd(x, k),
                "Wrap plain numbers first: other = other if isinstance(other, Value) else Value(other).")
        _local(V, label, c, g)
        _expect(f"after c = {label}; c.grad = {g}; c._backward()", "a.grad", a.grad, grads(x, k)[0] * g, rule)
    # the same Value on both sides
    x, g = round(rng.uniform(0.5, 4), 3), round(rng.uniform(0.5, 2), 3)
    a = V(x)
    label = f"a {op} a   (a = Value({x}))"
    c = _run(label, lambda: fwd(a, a))
    _local(V, label, c, g)
    want = 2 * g if op == "+" else 2 * x * g
    if math.isclose(a.grad, want / 2, rel_tol=1e-9):
        raise Fail(f"after c = {label}; c.grad = {g}; c._backward(): a.grad is {_num(a.grad)}, "
                   f"expected {_num(want)} (half of it went missing).", hint=ACCUMULATE)
    _expect(f"after c = {label}; c.grad = {g}; c._backward()", "a.grad", a.grad, want, ACCUMULATE)


@MISSION.check("Addition — `a + b` and its local gradients")
def _add(ctx):
    _binary(ctx, "+", 2101)


@MISSION.check("Multiplication — `a * b` and its local gradients")
def _mul(ctx):
    _binary(ctx, "*", 2201)


@MISSION.check("Power — `a ** k` for plain-number k")
def _pow(ctx):
    V = _value_class(ctx)
    rng = random.Random(2301)
    cases = [(round(rng.uniform(-3, 3), 3), 2), (round(rng.uniform(-3, 3), 3), 3),
             (round(rng.uniform(0.5, 4), 3), -1), (round(rng.uniform(0.5, 9), 3), 0.5),
             (round(rng.uniform(0.5, 3), 3), -2.5), (round(rng.uniform(-3, -0.5), 3), 1)]
    for x, k in cases:
        g = round(rng.uniform(-2, 2), 3) or 1.0
        a = V(x)
        label = f"Value({x}) ** {k}"
        c = _run(label, lambda: a ** k)
        _expect(label, ".data", _data(V, c, label), x ** k, "Forward value: self.data ** k.")
        if id(a) not in _prev_ids(c, label):
            raise Fail(f"`({label})._prev` doesn't contain the base Value.",
                       hint="Create the output as Value(self.data ** k, (self,), f\"**{k}\").")
        _local(V, label, c, g)
        _expect(f"after c = {label}; c.grad = {g}; c._backward()", "a.grad", a.grad, k * x ** (k - 1) * g,
                "The power rule: d(a**k)/da = k * a.data ** (k - 1), times out.grad.")


@MISSION.check("Activation — `tanh` (corrupted code repaired)")
def _tanh(ctx):
    V = _value_class(ctx)
    rng = random.Random(2401)
    for x in (round(rng.uniform(-2, 2), 3), 0.0, round(rng.uniform(0.3, 1.5), 3), 25.0, -400.0, 400.0):
        g = round(rng.uniform(0.5, 2), 3)
        a = V(x)
        label = f"Value({x}).tanh()"
        c = _run(label, lambda: a.tanh())
        t = math.tanh(x)
        _expect(label, ".data", _data(V, c, label), t, "The forward value is math.tanh(self.data).")
        _local(V, label, c, g)
        hint = "d tanh(x)/dx = 1 - tanh(x) ** 2. With t = math.tanh(x), the local derivative is 1 - t ** 2."
        _expect(f"after c = {label}; c.grad = {g}; c._backward()", "a.grad", a.grad, (1 - t * t) * g, hint)


@MISSION.check("Activation — `relu` is a gate")
def _relu(ctx):
    V = _value_class(ctx)
    rng = random.Random(2501)
    for x in (round(rng.uniform(0.1, 5), 3), round(rng.uniform(-5, -0.1), 3), 0.0, -2.0, 3.5):
        g = round(rng.uniform(0.5, 2), 3)
        a = V(x)
        label = f"Value({x}).relu()"
        c = _run(label, lambda: a.relu())
        _expect(label, ".data", _data(V, c, label), max(0.0, x),
                "relu outputs the input when it's positive, else 0.0.")
        if id(a) not in _prev_ids(c, label):
            raise Fail(f"`({label})._prev` doesn't contain its input.", hint="Value(result, (self,), \"relu\")")
        _local(V, label, c, g)
        hint = "The gate passes out.grad through where the input was > 0, and blocks it (0) everywhere else, 0 included."
        _expect(f"after c = {label}; c.grad = {g}; c._backward()", "a.grad", a.grad, g if x > 0 else 0.0, hint)


@MISSION.check("Full graph — backprop through your expressions matches finite differences")
def _graph(ctx):
    V = _value_class(ctx)
    for e, xs in _expressions(2601, 12):
        shown = _show_expr(e)
        where = ", ".join(f"{n}={x}" for n, x in zip("xyz", xs))
        leaves = [V(x) for x in xs]
        out = _run(f"{shown} with {where}", lambda: _eval(e, leaves, lambda v: v.tanh(), lambda v: v.relu()))
        f = _float_f(e)
        expected = f(xs)
        if isinstance(out, (int, float)):
            continue   # the expression never touched a leaf (all constants): nothing to differentiate
        got = _data(V, out, shown)
        if not math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-9):
            raise Fail(f"{shown} with {where}: .data is {_num(got)}, expected {_num(expected)}.",
                       hint="One of your forward values is off. The given operators (-, /, 2 * a) call yours.")
        order = _topo(V, out)
        out.grad = 1.0
        for node in reversed(order):
            back = getattr(node, "_backward", None)
            if callable(back):
                _run(f"backprop through {shown}", back)
        numeric = _central(f, xs)
        for name, leaf, want in zip("xyz", leaves, numeric):
            if not math.isclose(leaf.grad, want, rel_tol=1e-4, abs_tol=1e-5):
                raise Fail(f"d/d{name} of {shown} at {where}: your graph gives {_num(leaf.grad)}, "
                           f"finite differences say {_num(want)}.",
                           hint="The grader ran every _backward from the output down. Check which operation "
                                "the expression uses that your single-op tests didn't catch, and use +=.")


@MISSION.check("Bare hands — no torch, jax or micrograd")
def _sealed(ctx):
    for node in ast.walk(ctx.tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
            names = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        for name in names:
            if name.split(".")[0] in SEALED_MODULES:
                raise Fail(f"Line {node.lineno} imports `{name}`. In this mission that's the answer key, not a tool.",
                           hint="Build the engine with plain Python and `math`. The grader already checks you "
                                "against finite differences.")
