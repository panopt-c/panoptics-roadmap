"""THE LAB // AI03 THE GAZE — stable softmax, scaled dot-product attention and the causal mask."""
from __future__ import annotations

import ast
import warnings

from engine.mission import Fail, Mission

try:
    import numpy as np
except ImportError:  # the Lab shows `pip install numpy`; the briefing must still load without it
    np = None

SEALED = {"torch", "scipy", "tensorflow", "jax", "keras", "transformers"}

MISSION = Mission(
    id="AI03",
    slug="ai03_the_gaze",
    title="THE GAZE",
    concept="Scaled dot-product attention & causal masks",
    enemy="FORESIGHT.daemon",
    xp=380,
    par_seconds=55 * 60,
    tier=5,
    concepts=("numpy", "nlp", "neural-nets", "ml-math"),
    requires=("numpy",),
    timeout=12,
    run_as_main=False,
    enemy_art="""\
    ▄▄▀▀▀▀▀▀▄▄
  ▄▀  ▄▄▄▄▄▄  ▀▄
 █  ▄▀ ▄██▄ ▀▄  █
 █  ▀▄ ▀██▀ ▄▀  █
  ▀▄  ▀▀▀▀▀▀  ▄▀
 ═══▀▀▄▄▄▄▄▄▀▀═══
  » » » » » » » »""",
    briefing="""\
A word means little alone. *Bank* is a river or a vault, depending on who it looks at. The old
models learned to let every token **look at** the others and borrow their meaning, weighted by
how relevant each one seemed. They called it attention.

**FORESIGHT.daemon** learned it wrong. It peeks at tokens that haven't been written yet, so its
predictions are perfect in training and worthless in the field. MOTHER ADA calls it the oldest
lie in machine learning: a model that has seen the answer.

**Build scaled dot-product attention with a causal mask, and blind FORESIGHT to the future.**
""",
    why="""\
Attention is the core operation of every Transformer: GPT, Claude, BERT, ViT. Each token makes a
**query**, every token offers a **key** and a **value**; the softmax of query-key scores decides
how much of each value flows into the output:

```python
scores = Q @ K.swapaxes(-1, -2) / np.sqrt(d_k)   # (..., n_q, n_k)
scores = np.where(mask, scores, -np.inf)         # causal: no peeking ahead
weights = softmax(scores, axis=-1)               # each row sums to 1
out = weights @ V                                # (..., n_q, d_v)
```

In a decoder (a chatbot, a code model) the **causal mask** is what makes next-token training
honest: position t may only use positions ≤ t. Forget it and validation loss looks miraculous
while generation collapses. Reading this shape-by-shape is also how you debug real model code,
where most bugs are a wrong axis or a wrong transpose.
""",
    manual="""\
**1. Softmax, the stable way.** Softmax turns scores into probabilities: `exp(x) / sum(exp(x))`.
`np.exp(1000)` overflows to `inf`, and `inf / inf` is `nan`. Subtracting the row maximum changes
nothing mathematically (it cancels in the fraction) but keeps every exponent ≤ 0:

```python
def softmax(x, axis=-1):
    z = x - x.max(axis=axis, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=axis, keepdims=True)

softmax(np.array([1000.0, 1001.0]))   # [0.269, 0.731], not [nan, nan]
```

`keepdims=True` keeps the reduced axis as size 1, so a `(4, 5)` array divides by a `(4, 1)`
column: each row by its own total. Without it the shapes don't line up, or worse, broadcast the
wrong way.

**2. Scores: how well each query matches each key.** `Q` is `(n_q, d_k)`, `K` is `(n_k, d_k)`.
`Q @ K.T` is `(n_q, n_k)`: row i holds query i against every key. Divide by `sqrt(d_k)` so the
scores don't grow with the dimension (big scores make softmax nearly one-hot and gradients vanish).

For batches `(B, n, d)`, `.T` reverses ALL axes. Use `K.swapaxes(-1, -2)`, which swaps only the
last two, and `@` multiplies batch by batch.

**3. Weights and output.** Softmax over the **last** axis (over the keys), then mix the values:

```python
weights = softmax(Q @ K.swapaxes(-1, -2) / np.sqrt(Q.shape[-1]), axis=-1)
out = weights @ V          # (n_q, n_k) @ (n_k, d_v) -> (n_q, d_v)
```

**4. The causal mask.** For a sequence of n tokens, position i may look at j only when j ≤ i:
the lower triangle. Here `True` means *allowed* (PyTorch's `scaled_dot_product_attention` uses
the same convention):

```python
mask = np.tril(np.ones((4, 4), dtype=bool))
scores = np.where(mask, scores, -np.inf)    # BEFORE softmax: exp(-inf) = 0
```

*The common mistake:* zeroing the weights **after** the softmax. The surviving weights no longer
sum to 1, so the output shrinks. Masking with `-inf` before the softmax renormalizes for free.
Masking with `0` is also wrong: a score of 0 is an ordinary score and still gets weight.

**5. Self-attention.** One sequence `X` `(n, d)` makes its own queries, keys and values through
three weight matrices: `Q = X @ Wq`, `K = X @ Wk`, `V = X @ Wv`. With the causal mask, the output
at position t must not change if you rewrite any token after t. That's exactly what the grader
will try.

**In the real world:** PyTorch's `F.scaled_dot_product_attention(q, k, v, is_causal=True)` is
this mission in one fused kernel, and `nn.MultiheadAttention` runs several of them side by side.
Here torch and scipy are sealed; you build the kernel.
""",
    starter='''
"""
==============================================================================
  LAB // AI03 THE GAZE                             TARGET: FORESIGHT.daemon
==============================================================================
  The grader calls your functions on FRESH random matrices, compares with
  MOTHER ADA's reference, and tries to make your model see the future.
  NumPy only: torch and scipy are sealed.
"""
import numpy as np


# -- OBJECTIVE 1: CORRUPTED CODE ----------------------------------------------
# FORESIGHT poisoned the softmax. It must:
#   * work along `axis` (default: the last axis) for arrays of any shape
#   * survive huge scores: softmax(np.array([1000., 1001.])) -> [0.269, 0.731]
#   * treat -inf as "no weight": softmax(np.array([0., -np.inf])) -> [1., 0.]
# Example: z = x - x.max(axis=axis, keepdims=True)
def softmax(x, axis=-1):
    """exp(x) normalized along `axis` so the values sum to 1."""
    e = np.exp(x)
    return e / e.sum()


# -- OBJECTIVE 2: The causal mask --------------------------------------------------
# Return an (n, n) BOOL array: True where query i may look at key j (j <= i).
#   causal_mask(3) -> [[ True, False, False],
#                      [ True,  True, False],
#                      [ True,  True,  True]]
def causal_mask(n):
    """Lower-triangular boolean mask: True = allowed to attend."""
    # TODO
    return None


# -- OBJECTIVE 3: Scores ------------------------------------------------------------
# Q: (..., n_q, d_k)   K: (..., n_k, d_k)   ->   (..., n_q, n_k)
# score[i, j] = (Q[i] . K[j]) / sqrt(d_k). Must also work with a leading
# batch axis: use K.swapaxes(-1, -2), not K.T.
def attention_scores(Q, K):
    """Scaled dot products between every query and every key."""
    # TODO
    return None


# -- OBJECTIVE 4: Attention -------------------------------------------------------
# Return (output, weights):
#   weights = softmax of the scores over the KEYS (last axis)   (..., n_q, n_k)
#   output  = weights @ V                                       (..., n_q, d_v)
# mask (optional, bool, broadcastable to the scores): False positions must
# get exactly zero weight. Set their scores to -np.inf BEFORE the softmax.
def attention(Q, K, V, mask=None):
    """Scaled dot-product attention. Returns (output, weights)."""
    # TODO
    return None, None


# -- OBJECTIVE 5: Self-attention that cannot see the future -------------------------
# X: (n, d). Project Q = X @ Wq, K = X @ Wk, V = X @ Wv, then attend with
# the causal mask when causal=True. Return only the output (n, d_v).
def self_attention(X, Wq, Wk, Wv, causal=True):
    """One causal self-attention head."""
    # TODO
    return None


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    X = rng.normal(size=(4, 8))
    W = [rng.normal(size=(8, 8)) for _ in range(3)]
    out = self_attention(X, *W)
    print("output shape:", None if out is None else out.shape)
    print(causal_mask(4))
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "In the river bank, which word tells you what bank means? How would a machine know where to look?"},
            {"speaker": "ada", "mood": "neutral",
             "text": "It asks every word a question and weighs the answers. Today you build that gaze, and you blindfold it."},
            {"speaker": "cipher", "mood": "alarm",
             "text": "FORESIGHT.daemon reads tokens before they exist. Its scores are perfect. That should frighten you."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "matmul refused your shapes. Write each one down: (n_q, d_k) @ (d_k, n_k). Which transpose is missing?"}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Crash in the attention bay. The COMBAT LOG has the shapes that collided."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "exp of a thousand. Even my ledger doesn't have numbers that big, kid."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Every row of weights must sum to one. Sum them yourself. Which axis did your softmax walk along?"}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "Zeroing weights after the softmax leaves a distribution that no longer sums to one. Mask before."}],
            [{"speaker": "vex", "mood": "smirk",
              "text": "Your model aced the past by reading the future? Cute. I call that cheating in the Arena too."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Rewrite the future and the past stays still. FORESIGHT is blind, and your model is honest."},
            {"speaker": "ada", "mood": "neutral",
             "text": "Third page restored: a model may only learn from what it could have known. The Core forgot that."},
            {"speaker": "cipher", "mood": "warm",
             "text": "Attention head online, {callsign}. Causality verified. No leaks."},
        ],
    },
)


# ── reference (MOTHER ADA's) ─────────────────────────────────────────────────────

def _ref_softmax(x, axis=-1):
    z = x - np.max(x, axis=axis, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=axis, keepdims=True)


def _ref_mask(n):
    return np.tril(np.ones((n, n), dtype=bool))


def _ref_scores(Q, K):
    return Q @ np.swapaxes(K, -1, -2) / np.sqrt(Q.shape[-1])


def _ref_attention(Q, K, V, mask=None):
    s = _ref_scores(Q, K)
    if mask is not None:
        s = np.where(mask, s, -np.inf)
    w = _ref_softmax(s, axis=-1)
    return w @ V, w


def _ref_self(X, Wq, Wk, Wv, causal=True):
    n = X.shape[0]
    return _ref_attention(X @ Wq, X @ Wk, X @ Wv, _ref_mask(n) if causal else None)[0]


# ── grader helpers ────────────────────────────────────────────────────────────────

def _show(value, limit: int = 140) -> str:
    if np is not None and isinstance(value, np.ndarray):
        text = " ".join(np.array2string(value, precision=3, threshold=10, edgeitems=2,
                                        separator=", ", suppress_small=True).split())
        text = f"{text} (shape {value.shape})"
    else:
        text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _sealed(ctx) -> None:
    for node in ast.walk(ctx.tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if name.split(".")[0] in SEALED:
                raise Fail(f"`import {name}` found (line {node.lineno}). Deep-learning libraries are sealed here.",
                           hint="Build attention from NumPy matmuls and your own softmax; the manual shows the PyTorch call.")


def _fn(ctx, name: str):
    if np is None:
        raise Fail("numpy isn't installed, so the Lab can't grade this mission.", hint="pip install numpy")
    _sealed(ctx)
    if name not in ctx.ns:
        if ctx.crashed:
            raise Fail(f"`{name}` doesn't exist: your file crashed before defining it. Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.", hint=f"Keep the starter's  def {name}(...):  line.")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return fn


def _call(fn, label: str, *args, hint: str = "", **kwargs):
    copies = [a.copy() if isinstance(a, np.ndarray) else a for a in args]
    try:
        with warnings.catch_warnings(), np.errstate(all="ignore"):
            warnings.simplefilter("ignore")
            out = fn(*copies, **kwargs)
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        msg = str(exc)
        if not hint and isinstance(exc, ValueError) and ("matmul" in msg or "shape" in msg or "broadcast" in msg):
            hint = ("A shape mismatch. Q @ K needs K transposed on its last two axes: K.swapaxes(-1, -2). "
                    "With a batch axis, .T also flips the batch.")
        raise Fail(f"`{label}` raised {type(exc).__name__}: {exc}",
                   hint=hint or "Call it yourself on this input and read the traceback.")
    for original, passed in zip(args, copies):
        if isinstance(original, np.ndarray) and not np.array_equal(original, passed, equal_nan=original.dtype.kind == "f"):
            raise Fail(f"`{label}` changed its input array in place.",
                       hint="Use np.where(...) or x - max(...) to build new arrays; leave the inputs untouched.")
    return out


def _array(got, label: str, shape: tuple, hint: str = ""):
    if got is None:
        raise Fail(f"`{label}` returned None: the TODO is still open.", hint="End the function with `return ...`.")
    if not isinstance(got, np.ndarray):
        raise Fail(f"`{label}` returned a {type(got).__name__}, expected a NumPy array of shape {shape}.",
                   hint=hint or "Return the NumPy array itself.")
    if got.shape != tuple(shape):
        raise Fail(f"`{label}` returned shape {got.shape}, expected {tuple(shape)}.", hint=hint)
    if got.dtype.kind in "fc" and not np.all(np.isfinite(got)):
        raise Fail(f"`{label}` returned nan/inf: {_show(got)}.",
                   hint="exp of a big score overflows to inf, and inf/inf is nan. Subtract the max along the axis first.")
    return got


def _close(label: str, got, want, hint: str = "", tol: float = 1e-8) -> None:
    if not np.allclose(got, want, atol=tol, rtol=1e-6):
        raise Fail(f"`{label}` returned {_show(got)}, expected {_show(want)}.", hint=hint)


def _pair(got, label: str):
    if not (isinstance(got, tuple) and len(got) == 2):
        raise Fail(f"`{label}` returned {_show(got, 80)}, expected a tuple (output, weights).",
                   hint="End with  return out, weights  (in that order).")
    if got[0] is None or got[1] is None:
        raise Fail(f"`{label}` returned (None, None): the TODO is still open.",
                   hint="Compute the weights with softmax over the scores, then out = weights @ V.")
    return got


# ── firewall layers ──────────────────────────────────────────────────────────────

@MISSION.check("CORRUPTED `softmax` repaired — stable, along the right axis")
def _softmax(ctx):
    fn = _fn(ctx, "softmax")
    rng = np.random.default_rng(31)
    cases = [(np.array([1.0, 2.0, 3.0]), -1), (np.array([1000.0, 1001.0, 1002.0]), -1),
             (np.array([0.0, -np.inf, 2.0]), -1), (rng.normal(size=(4, 5)) * 3, -1),
             (rng.normal(size=(3, 6)) * 50 + 700, -1), (rng.normal(size=(4, 3)), 0),
             (rng.normal(size=(2, 3, 4)) * 5, -1), (rng.normal(size=(2, 3, 4)), 1)]
    for x, axis in cases:
        label = f"softmax({_show(x, 70)}, axis={axis})"
        got = _array(_call(fn, label, x, axis=axis), label, x.shape,
                     hint="Same shape out as in: normalize along `axis` with keepdims=True.")
        want = _ref_softmax(x, axis)
        if not np.allclose(got, want, atol=1e-9):
            hint = "Sum along `axis` with keepdims=True, so each slice is divided by its OWN total."
            if np.isclose(got.sum(), 1.0) and x.ndim > 1:
                hint = "Your whole array sums to 1. Each slice along `axis` must: e.sum(axis=axis, keepdims=True)."
            elif x.ndim > 1 and np.allclose(got, _ref_softmax(x, 0 if axis != 0 else -1), atol=1e-9):
                hint = "You normalized along the other axis. Use the `axis` argument you were given."
            raise Fail(f"`{label}` returned {_show(got)}, expected {_show(want)}.", hint=hint)


@MISSION.check("Blindfold — `causal_mask` is lower-triangular and boolean")
def _mask(ctx):
    fn = _fn(ctx, "causal_mask")
    for n in (3, 1, 6):
        label = f"causal_mask({n})"
        got = _array(_call(fn, label, n), label, (n, n), hint="An (n, n) array: one row per query, one column per key.")
        if got.dtype != bool:
            raise Fail(f"`{label}` has dtype {got.dtype}, expected bool.",
                       hint="np.tril(np.ones((n, n), dtype=bool)): True/False values, so np.where can use it as a mask.")
        want = _ref_mask(n)
        if not np.array_equal(got, want):
            hint = "Query i may see keys 0..i (itself included): the LOWER triangle, diagonal included."
            if np.array_equal(got, ~want) or np.array_equal(got, np.triu(np.ones((n, n), dtype=bool), 1)):
                hint = "That's inverted: True must mean ALLOWED (j <= i), the lower triangle."
            elif np.array_equal(got, np.tril(np.ones((n, n), dtype=bool), -1)):
                hint = "You blocked the diagonal. A token may look at itself: keep j == i."
            raise Fail(f"`{label}` returned {_show(got)}, expected {_show(want)}.", hint=hint)


@MISSION.check("Relevance — `attention_scores` = Q·Kᵀ / √d_k, batches too")
def _scores(ctx):
    fn = _fn(ctx, "attention_scores")
    rng = np.random.default_rng(32)
    for qshape, kshape in (((3, 4), (5, 4)), ((6, 16), (6, 16)), ((2, 3, 8), (2, 7, 8)), ((4, 5, 2), (4, 5, 2))):
        Q, K = rng.normal(size=qshape), rng.normal(size=kshape)
        label = f"attention_scores(Q{Q.shape}, K{K.shape})"
        shape = qshape[:-1] + (kshape[-2],)
        got = _array(_call(fn, label, Q, K), label, shape,
                     hint="Scores are (..., n_q, n_k). Use K.swapaxes(-1, -2): with a batch axis, .T also flips the batch.")
        want = _ref_scores(Q, K)
        if not np.allclose(got, want, atol=1e-9):
            d = qshape[-1]
            raw = Q @ np.swapaxes(K, -1, -2)
            hint = "Divide the raw dot products by np.sqrt(d_k), where d_k = Q.shape[-1]."
            if np.allclose(got, raw, atol=1e-9):
                hint = "Unscaled. Divide by sqrt(d_k): large dot products would push softmax to one-hot."
            elif np.allclose(got, raw / d, atol=1e-9):
                hint = f"You divided by d_k ({d}). The scale is its SQUARE ROOT: np.sqrt(d_k)."
            raise Fail(f"`{label}` returned {_show(got)}, expected {_show(want)}.", hint=hint)


@MISSION.check("The gaze — `attention` returns (output, weights), rows sum to 1")
def _attend(ctx):
    fn = _fn(ctx, "attention")
    rng = np.random.default_rng(33)
    for nq, nk, dk, dv in ((3, 5, 4, 2), (6, 6, 8, 8), (1, 4, 3, 5)):
        Q, K, V = rng.normal(size=(nq, dk)) * 2, rng.normal(size=(nk, dk)) * 2, rng.normal(size=(nk, dv))
        label = f"attention(Q{Q.shape}, K{K.shape}, V{V.shape})"
        out, w = _pair(_call(fn, label, Q, K, V), label)
        w = _array(w, label + " weights", (nq, nk), hint="Weights are (n_q, n_k): one distribution over keys per query.")
        want_out, want_w = _ref_attention(Q, K, V)
        if not np.allclose(w, want_w, atol=1e-9):
            hint = "softmax(attention_scores(Q, K), axis=-1): normalize over the KEYS so each row sums to 1."
            if np.allclose(w, _ref_softmax(_ref_scores(Q, K), axis=0), atol=1e-9):
                hint = "Your COLUMNS sum to 1. Softmax over the last axis (keys): each query's row must sum to 1."
            raise Fail(f"`{label}` weights {_show(w)}, expected {_show(want_w)}.", hint=hint)
        out = _array(out, label + " output", (nq, dv), hint="Output = weights @ V, shape (n_q, d_v).")
        _close(label + " output", out, want_out, hint="Mix the values with the weights: out = weights @ V.")


@MISSION.check("Masked gaze — masked positions get exactly zero weight")
def _masked(ctx):
    fn = _fn(ctx, "attention")
    rng = np.random.default_rng(34)
    for n, dk, dv in ((4, 4, 3), (7, 8, 2)):
        Q, K, V = rng.normal(size=(n, dk)) * 2, rng.normal(size=(n, dk)) * 2, rng.normal(size=(n, dv))
        mask = _ref_mask(n)
        label = f"attention(Q{Q.shape}, K, V, mask=causal_mask({n}))"
        out, w = _pair(_call(fn, label, Q, K, V, mask=mask), label)
        w = _array(w, label + " weights", (n, n))
        out = _array(out, label + " output", (n, dv))
        want_out, want_w = _ref_attention(Q, K, V, mask)
        leak = np.abs(w[~mask]).max()
        if leak > 1e-12:
            hint = "Set masked scores to -np.inf BEFORE the softmax: np.where(mask, scores, -np.inf). exp(-inf) is 0."
            raise Fail(f"`{label}` gives weight {leak:.3g} to a future (masked) position.", hint=hint)
        if not np.allclose(w, want_w, atol=1e-9):
            hint = "Mask with -inf BEFORE the softmax, so the allowed weights renormalize to sum to 1."
            sums = w.sum(axis=-1)
            if not np.allclose(sums, 1.0):
                hint = (f"Row sums are {_show(sums.round(3), 60)}, not 1: you zeroed weights AFTER the softmax. "
                        "Mask the scores with -inf before it.")
            raise Fail(f"`{label}` weights {_show(w)}, expected {_show(want_w)}.", hint=hint)
        _close(label + " output", out, want_out, hint="With the right weights, out = weights @ V.")
    # a mask that also blocks some past positions (padding): any False must be respected
    Q, K, V = rng.normal(size=(3, 4)), rng.normal(size=(5, 4)), rng.normal(size=(5, 2))
    mask = np.array([[1, 1, 0, 1, 0], [1, 0, 0, 1, 1], [0, 1, 1, 1, 0]], dtype=bool)
    label = "attention(Q(3, 4), K(5, 4), V(5, 2), mask=padding_mask)"
    out, w = _pair(_call(fn, label, Q, K, V, mask=mask), label)
    _close(label + " weights", _array(w, label, (3, 5)), _ref_attention(Q, K, V, mask)[1],
           hint="Any mask works the same way: False positions get -inf scores, whatever their place.")


@MISSION.check("Many heads — batched attention with a broadcast causal mask")
def _batched(ctx):
    fn = _fn(ctx, "attention")
    rng = np.random.default_rng(35)
    B, n, dk, dv = 3, 5, 4, 6
    Q, K, V = rng.normal(size=(B, n, dk)), rng.normal(size=(B, n, dk)), rng.normal(size=(B, n, dv))
    mask = _ref_mask(n)
    label = f"attention(Q{Q.shape}, K{K.shape}, V{V.shape}, mask=causal_mask({n}))"
    out, w = _pair(_call(fn, label, Q, K, V, mask=mask), label)
    w = _array(w, label + " weights", (B, n, n),
               hint="With a batch axis the weights are (B, n_q, n_k). Use K.swapaxes(-1, -2), never K.T.")
    out = _array(out, label + " output", (B, n, dv))
    want_out, want_w = _ref_attention(Q, K, V, mask)
    _close(label + " weights", w, want_w,
           hint="Each batch item attends only within itself: K.swapaxes(-1, -2), softmax over axis=-1.")
    _close(label + " output", out, want_out, hint="out = weights @ V; @ multiplies batch by batch.")


@MISSION.check("No foresight — `self_attention` ignores every future token")
def _causal(ctx):
    fn = _fn(ctx, "self_attention")
    rng = np.random.default_rng(36)
    n, d, dv = 6, 8, 5
    X = rng.normal(size=(n, d))
    Wq, Wk, Wv = rng.normal(size=(d, d)) / 2, rng.normal(size=(d, d)) / 2, rng.normal(size=(d, dv))
    label = f"self_attention(X{X.shape}, Wq, Wk, Wv)"
    out = _array(_call(fn, label, X, Wq, Wk, Wv), label, (n, dv),
                 hint="Q = X @ Wq, K = X @ Wk, V = X @ Wv; the output has one row per token, d_v columns.")
    _close(label, out, _ref_self(X, Wq, Wk, Wv),
           hint="Project with Wq, Wk, Wv, then call your attention with mask=causal_mask(len(X)).")
    for t in (0, 2, 4):
        future = X.copy()
        future[t + 1:] = rng.normal(size=(n - t - 1, d)) * 5
        again = _array(_call(fn, label, future, Wq, Wk, Wv), label, (n, dv))
        if not np.allclose(again[: t + 1], out[: t + 1], atol=1e-9):
            raise Fail(f"Rewriting tokens after position {t} changed your output at positions 0..{t}: the model sees the future.",
                       hint="Pass mask=causal_mask(n) to attention when causal=True. Position t may only attend to j <= t.")
    open_out = _array(_call(fn, label + " causal=False", X, Wq, Wk, Wv, causal=False), label, (n, dv))
    _close(f"self_attention(X{X.shape}, Wq, Wk, Wv, causal=False)", open_out, _ref_self(X, Wq, Wk, Wv, causal=False),
           hint="causal=False means no mask at all: every token sees every token (that's an encoder, like BERT).")
