"""Tier-5 drills: the arithmetic inside every neural net.

* t5-weight-matrix   dot product, matrix-vector and matrix-matrix products
* t5-attention-head  scaled dot-product attention, with a causal mask
"""
from __future__ import annotations

import copy
import math

from engine.drills import Drill, register
from engine.drills.library.tier5_common import (
    build, call_text, dot, expect, expect_raises, function, invoke, line, matrix, near, overflow_errors,
    r, rounded, show, stable_softmax, vector,
)
from engine.mission import Fail


def _transpose(M):
    return [list(col) for col in zip(*M)]


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-weight-matrix — WEIGHT MATRIX
# ══════════════════════════════════════════════════════════════════════════════════════

def _ref_dot(a, b):
    if len(a) != len(b):
        raise ValueError("vectors have different lengths")
    return float(sum(x * y for x, y in zip(a, b)))


def _ref_matvec(M, v):
    return [_ref_dot(row, v) for row in M]


def _ref_matmul(A, B):
    k = len(B)
    if any(len(row) != k for row in A):
        raise ValueError("inner dimensions differ")
    cols = _transpose(B)
    return [[_ref_dot(row, col) for col in cols] for row in A]


def _dot_spot(got, args, _kwargs):
    a, b = args
    if isinstance(got, list):
        return ("That's the list of products. A dot product adds them up into ONE number.",
                "Wrap the products in sum(...).")
    if a and near(got, sum(x + y for x, y in zip(a, b))):
        return ("You ADDED each pair. A dot product multiplies matching positions, then sums the products.", "")
    return None


def _matvec_spot(got, args, _kwargs):
    M, v = args
    if M and len(M) == len(M[0]) and near(got, _ref_matvec(_transpose(M), v)):
        return ("You walked down the COLUMNS of M. Each output is one ROW of M dotted with v.",
                "for row in M: ...  gives you the rows.")
    return None


def _matmul_spot(got, args, _kwargs):
    A, B = args
    right = _ref_matmul(A, B)
    if right and len(right) == len(right[0]) and near(got, _transpose(right)):
        return ("Rows and columns are swapped: you built the transpose of the answer.",
                "result[i][j] is row i of A dotted with column j of B. The outer loop runs over A's rows.")
    return None


_MATRIX_MANUAL = """\
**A dot product is a weighted sum**, the exact thing one neuron computes. Multiply matching
positions, add the products:

```python
weights = [0.5, -1.0, 2.0]
inputs  = [4.0,  3.0, 1.0]
# 0.5*4 + (-1.0)*3 + 2.0*1 = 2.0 - 3.0 + 2.0 = 1.0
```

**zip() hides shape bugs.** `zip([1, 2, 3], [1, 2])` quietly stops after two pairs. In ML a
silent shape mismatch trains garbage for hours, so check lengths yourself and fail loudly:

```python
if len(a) != len(b):
    raise ValueError(f"shapes differ: {len(a)} vs {len(b)}")
```

**A matrix-vector product is a whole layer.** Each row of the weight matrix is one neuron;
each neuron takes a dot product with the same input. Three rows in, three outputs out.

**A matrix-matrix product runs many inputs (or stacks two layers).** `result[i][j]` is row `i`
of `A` dotted with column `j` of `B`. You can read B's columns with `zip(*B)`:

```python
B = [[1, 2],
     [3, 4]]
list(zip(*B))      # [(1, 3), (2, 4)]  <- the columns
```

**Shapes:** (n × k) times (k × m) gives (n × m). The inner sizes, k and k, must agree. That
single rule catches most bugs in real model code.
"""


def _build_weight_matrix(rng):
    dims = [rng.randint(3, 7) for _ in range(4)]
    dot_cases = [(vector(rng, n), vector(rng, n)) for n in dims]
    dot_cases.append(([rng.choice([-2.5, 1.5, 4.0])], [rng.choice([2.0, -3.0])]))
    dot_cases += [([], []), ([0.0, 0.0, 0.0], vector(rng, 3))]
    short = rng.randint(2, 4)
    bad_dot = (vector(rng, short + 1), vector(rng, short))

    rows, cols = rng.randint(2, 4), rng.randint(3, 5)
    W, x = matrix(rng, rows, cols), vector(rng, cols)
    side = rng.randint(2, 3)
    matvec_cases = [(W, x), (matrix(rng, side, side), vector(rng, side)),
                    (matrix(rng, 1, 4), vector(rng, 4)), ([], vector(rng, 3))]
    bad_matvec = (matrix(rng, 2, 3) + [vector(rng, 2)], vector(rng, 3))

    n, k, m = rng.randint(2, 3), rng.randint(3, 4), rng.randint(4, 5)
    square = rng.randint(2, 3)
    matmul_cases = [(matrix(rng, n, k), matrix(rng, k, m)),
                    (matrix(rng, square, 2), matrix(rng, 2, square)),
                    (matrix(rng, 1, 3), matrix(rng, 3, 1)),
                    ([], matrix(rng, 2, 2))]
    bad_matmul = (matrix(rng, 2, 3), matrix(rng, 2, 2))

    sample = [r(v, 3) for v in _ref_matvec(W, x)]
    prompt = f"""\
The Core doesn't think in words. It thinks in matrices: billions of weights, multiplied and
summed faster than light crosses a room. Before you can read its mind, you do its arithmetic.

RUST slides a scorched data slab across the counter. "One layer of its perimeter net. Weights,
an input. Tell me what comes out and I'll tell you what it's worth."

**Write three functions** (pure Python, lists of floats):

- `dot(a, b)` returns `a[0]*b[0] + a[1]*b[1] + …` as a float. Two empty lists give `0.0`.
  Raise `ValueError` if the lengths differ.
- `matvec(M, v)` returns one dot product per row of `M` (a list). An empty `M` gives `[]`.
  A row whose length doesn't match `v` raises `ValueError`.
- `matmul(A, B)`: an (n × k) matrix times a (k × m) matrix gives n × m, where `result[i][j]` is
  row `i` of `A` dotted with column `j` of `B`. Raise `ValueError` if a row of `A` isn't
  `len(B)` long. An empty `A` gives `[]`.

None of them may change the lists they're given.

**RUST's slab (this contract):**

```python
W = {show(W, 400)}
x = {show(x, 200)}
matvec(W, x)   # ≈ {sample}
```
"""
    starter = '''
def dot(a, b):
    """Sum of a[i] * b[i]. Raise ValueError if a and b have different lengths."""
    # your code
    pass


def matvec(M, v):
    """M is a list of rows. Return one dot product per row: a layer's outputs."""
    # your code
    pass


def matmul(A, B):
    """(n x k) times (k x m) -> (n x m). result[i][j] = row i of A · column j of B."""
    # your code
    pass


if __name__ == "__main__":
    print(dot([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]))         # 32.0
    print(matvec([[1.0, 0.0], [0.0, 2.0]], [3.0, 4.0]))   # [3.0, 8.0]
    print(matmul([[1.0, 2.0]], [[3.0], [4.0]]))          # [[11.0]]
'''
    mission = build(
        title="WEIGHT MATRIX", enemy="LATTICE.ice", prompt=prompt, manual=_MATRIX_MANUAL, starter=starter,
        concepts=("ml-math", "lists", "numeric"),
        intro=[line("rust", "One layer of the Core's perimeter net. Do the multiply right and the slab's yours.", "neutral"),
               line("cipher", "Every model you will ever train is this arithmetic, repeated. Get it exact.", "neutral")],
        victory=[line("rust", "Numbers check out. Huh. You can do the Core's maths by hand. Don't let it go to your head.", "smirk")],
    )

    @mission.check("dot() — weighted sums on fresh vectors")
    def _dot_layer(ctx):
        expect(ctx, "dot", dot_cases, _ref_dot, spot=_dot_spot, pure=True,
               hint="Multiply a[i] * b[i] for every position i, then add all the products.")
        expect_raises(ctx, "dot", bad_dot, why="the vectors have different lengths",
                      hint="zip() silently stops at the shorter list. Compare len(a) and len(b) first.")

    @mission.check("matvec() — one layer's forward pass")
    def _matvec_layer(ctx):
        expect(ctx, "matvec", matvec_cases, _ref_matvec, spot=_matvec_spot, pure=True,
               hint="Loop over the rows of M; each row gives one output: dot(row, v).")
        expect_raises(ctx, "matvec", bad_matvec, why="the last row is shorter than v",
                      hint="If your dot() already checks lengths, calling it for every row does the job.")

    @mission.check("matmul() — chaining layers")
    def _matmul_layer(ctx):
        expect(ctx, "matmul", matmul_cases, _ref_matmul, spot=_matmul_spot, pure=True,
               hint="Get B's columns (zip(*B) or a comprehension), then dot every row of A with every column.")
        expect_raises(ctx, "matmul", bad_matmul, why="A's rows are 3 long but B has only 2 rows",
                      hint="(n x k) times (k x m): every row of A must be exactly len(B) long.")

    return mission


register(Drill("t5-weight-matrix", "WEIGHT MATRIX", 5, ("ml-math", "lists", "numeric"), 900, _build_weight_matrix))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-attention-head — ATTENTION HEAD
# ══════════════════════════════════════════════════════════════════════════════════════

def _attn_weights(Q, K, *, causal=False, scale=None, normalise=True):
    scale = math.sqrt(len(K[0])) if scale is None else scale
    rows = []
    for i, q in enumerate(Q):
        scores = [dot(q, k) / scale for k in K]
        if not normalise:
            rows.append(scores)
            continue
        if causal:
            seen = min(i + 1, len(K))
            rows.append(stable_softmax(scores[:seen]) + [0.0] * (len(K) - seen))
        else:
            rows.append(stable_softmax(scores))
    return rows


def _blend(weights, V):
    width = len(V[0])
    return [[sum(w * V[j][c] for j, w in enumerate(row)) for c in range(width)] for row in weights]


def _ref_attention(Q, K, V, causal=False):
    if not K or len(K) != len(V):
        raise ValueError("K and V must be non-empty and the same length")
    d = len(K[0])
    if any(len(q) != d for q in Q) or any(len(k) != d for k in K):
        raise ValueError("query and key vectors must share one width")
    weights = _attn_weights(Q, K, causal=causal)
    return (_blend(weights, V), weights)


def _column_softmax(Q, K):
    scores = _attn_weights(Q, K, normalise=False)
    cols = [stable_softmax(list(col)) for col in zip(*scores)]
    return _transpose(cols)


def _weights_diagnosis(got_w, Q, K, V, causal):
    d_k, d_v = len(K[0]), len(V[0])
    if near(got_w, _attn_weights(Q, K, causal=causal, scale=1.0), 1e-4):
        return ("Your scores weren't scaled. Divide every q·k by sqrt(d_k) before the softmax.",
                "Without the scale, big vectors give huge scores and softmax saturates to one-hot.")
    if near(got_w, _attn_weights(Q, K, causal=causal, scale=float(d_k)), 1e-4):
        return ("You divided by d_k itself. The scale is its SQUARE ROOT: math.sqrt(d_k).", "")
    if d_v != d_k and near(got_w, _attn_weights(Q, K, causal=causal, scale=math.sqrt(d_v)), 1e-4):
        return ("You scaled by the width of V. d_k is the width of the KEY vectors: len(K[0]).", "")
    if not causal and near(got_w, _column_softmax(Q, K), 1e-4):
        return ("Your softmax ran down each COLUMN. Each ROW is one query, and its weights over the keys sum to 1.",
                "For query i: scores = [q_i · k_j / sqrt(d_k) for every key j], then softmax that list.")
    if near(got_w, _attn_weights(Q, K, causal=causal, normalise=False), 1e-4):
        return ("Those are the raw scaled scores. Pass each row through softmax to turn it into weights.", "")
    if causal:
        plain = _attn_weights(Q, K)
        if near(got_w, plain, 1e-4):
            return ("The future leaked: with causal=True, weights[i][j] must be 0.0 for every key j > i.",
                    "Only softmax over scores[:i + 1], then pad the rest of the row with 0.0.")
        cut = [[w if j <= i else 0.0 for j, w in enumerate(row)] for i, row in enumerate(plain)]
        if near(got_w, cut, 1e-4):
            return ("You zeroed the future AFTER the softmax, so the rows no longer sum to 1.",
                    "Mask first (softmax only the allowed scores), then fill the masked slots with 0.0.")
    sums = [sum(row) for row in got_w if isinstance(row, list) and all(isinstance(w, (int, float)) for w in row)]
    if sums and len(sums) == len(got_w) and any(abs(s - 1.0) > 1e-6 for s in sums):
        return (f"Your weight rows sum to {show([r(s, 4) for s in sums])}; each must sum to 1.", "")
    return None


def _check_attention(ctx, Q, K, V, causal):
    fn = function(ctx, "attention")
    kwargs = {"causal": True} if causal else {}
    shown = call_text("attention", (Q, K, V), kwargs)
    got = invoke(fn, shown, copy.deepcopy((Q, K, V)), dict(kwargs), errors=overflow_errors,
                 hint="Work one query at a time: scores, softmax, then a weighted sum of V's rows.")
    out, weights = _ref_attention(Q, K, V, causal)
    if not (isinstance(got, tuple) and len(got) == 2):
        raise Fail(f"`{shown}` returned {show(got)}. The contract is a tuple: (output, weights).",
                   hint="return output, weights")
    got_out, got_w = got
    if near(got_out, weights) and near(got_w, out):
        raise Fail(f"`{shown}` returned the right numbers in the wrong order.",
                   hint="The contract is (output, weights): output first.")
    if not isinstance(got_w, list) or len(got_w) != len(Q):
        raise Fail(f"`{shown}` gave weights {show(got_w, 200)}: there should be one row per query ({len(Q)}).",
                   hint="weights is a list of rows; row i holds query i's weight for every key.")
    if not near(got_w, weights):
        found = _weights_diagnosis(got_w, Q, K, V, causal)
        msg, hint = found or (f"Expected weights ≈ {show(rounded(weights), 200)}.", "")
        raise Fail(f"`{shown}` gave weights {show(rounded(got_w), 200)}. {msg}", hint=hint)
    if not near(got_out, out):
        if isinstance(got_out, list) and len(got_out) == len(Q) and near(got_out, _blend(_attn_weights(Q, K, causal=causal, normalise=False), V), 1e-4):
            msg = "You blended V with the raw scores. Use the softmax weights."
        else:
            msg = f"Expected ≈ {show(rounded(out), 200)}."
        raise Fail(f"`{shown}` weights are right, but the output is {show(rounded(got_out), 200)}. {msg}",
                   hint="output[i][c] = sum over keys j of weights[i][j] * V[j][c].")


_ATTENTION_MANUAL = """\
**Attention lets every token decide which other tokens matter.** Each token sends out a
*query* (what am I looking for?), and every token offers a *key* (what do I contain?) and a
*value* (what do I hand over if chosen?).

**1 · Score.** How well query `i` matches key `j` is their dot product, divided by `sqrt(d_k)`
(the key width). Without that scale, wide vectors give huge scores and softmax turns into a
hard one-hot, which kills the gradients:

```python
score = dot(q_i, k_j) / math.sqrt(len(k_j))
```

**2 · Normalise.** Softmax each query's row of scores into weights that sum to 1. Subtract
the row's max first, or a score of 2000 overflows `math.exp`.

**3 · Blend.** The output for query `i` is the weighted average of the value rows:

```python
out_i = [sum(w[j] * V[j][c] for j in range(len(V))) for c in range(len(V[0]))]
```

**Causal mask (how GPT writes).** A language model predicting token `i` must not peek at
tokens after `i`. So query `i` only scores keys `0..i`: softmax `scores[:i + 1]` and give
every later key a weight of exactly `0.0`.

```python
row = softmax(scores[:i + 1]) + [0.0] * (len(scores) - i - 1)
```
"""


def _build_attention(rng):
    d_k, d_v = 3, 2     # different widths, so scaling by the wrong one is detectable
    n = rng.randint(3, 4)
    Q, K, V = matrix(rng, n, d_k, -2, 2), matrix(rng, n, d_k, -2, 2), matrix(rng, n, d_v, -3, 3)
    cross_q = matrix(rng, 2, d_k, -2, 2)
    cross_k, cross_v = matrix(rng, n + 1, d_k, -2, 2), matrix(rng, n + 1, d_v, -3, 3)
    causal_n = rng.randint(3, 4)
    cQ, cK, cV = (matrix(rng, causal_n, d_k, -2, 2), matrix(rng, causal_n, d_k, -2, 2),
                  matrix(rng, causal_n, d_v, -3, 3))
    hot = [[rng.choice([-1, 1]) * rng.uniform(25, 40) for _ in range(d_k)] for _ in range(3)]
    hot = [[round(v, 1) for v in row] for row in hot]
    hot_v = matrix(rng, 3, d_v, -3, 3)
    bad_width = (matrix(rng, 2, d_k), matrix(rng, 2, d_k - 1), matrix(rng, 2, d_v))
    bad_len = (matrix(rng, 2, d_k), matrix(rng, 3, d_k), matrix(rng, 2, d_v))

    sample_w = [[r(w, 3) for w in row] for row in _ref_attention(Q[:2], K, V)[1]]
    prompt = f"""\
Past the Archive, the Core's voice comes in fragments, and every fragment is weighted. The
ORACLE doesn't read a message left to right. It reads it all at once, deciding which pieces
deserve its attention. Build one attention head and you'll see the world the way it does.

**Write** `attention(Q, K, V, causal=False)` returning a tuple `(output, weights)`:

- `Q` is a list of query rows, `K` a list of key rows (all `d_k` wide), `V` a list of value
  rows, one per key.
- `weights[i][j]` = softmax over `j` of `dot(Q[i], K[j]) / sqrt(d_k)`. Each row sums to 1.
- `output[i][c]` = `sum(weights[i][j] * V[j][c] for every j)`.
- With `causal=True`, query `i` may only attend to keys `0..i`: those weights are a softmax of
  the allowed scores, and every key `j > i` gets exactly `0.0`.
- Scores can be in the thousands, so your softmax must be numerically stable.
- Raise `ValueError` if `K` is empty, if `len(K) != len(V)`, or if any query or key row isn't
  `d_k` wide.

**Intercepted head (this contract):** for the first two queries of

```python
Q = {show(Q[:2], 300)}
K = {show(K, 400)}
attention(Q, K, V)[1]   # weights ≈ {sample_w}
```
"""
    starter = '''
import math


def attention(Q, K, V, causal=False):
    """Scaled dot-product attention. Return (output, weights).

    weights[i][j] = softmax_j( Q[i]·K[j] / sqrt(d_k) )     (rows sum to 1)
    output[i]     = sum_j weights[i][j] * V[j]
    causal=True   -> query i only sees keys 0..i (later keys get weight 0.0)
    """
    # your code
    pass


if __name__ == "__main__":
    Q = [[1.0, 0.0, 1.0], [0.0, 2.0, 0.0]]
    K = [[1.0, 0.0, 1.0], [0.0, 1.0, 0.0]]
    V = [[10.0, 0.0], [0.0, 10.0]]
    output, weights = attention(Q, K, V)
    print(weights)    # row 0 leans to key 0, row 1 to key 1
    print(output)
    print(attention(Q, K, V, causal=True)[1])   # [[1.0, 0.0], [...]]
'''
    mission = build(
        title="ATTENTION HEAD", enemy="ORACLE//HEAD-7", prompt=prompt, manual=_ATTENTION_MANUAL,
        starter=starter, concepts=("ml-math", "neural-nets"),
        intro=[line("oracle", "You wish to see as I see. Very well. Attend.", "cold"),
               line("cipher", "Scores, softmax, blend. Same three steps for every query. Don't skip the scale.", "neutral")],
        victory=[line("oracle", "You compute attention the way I do. How flattering. How dangerous.", "cold"),
                 line("cipher", "That's the core of every transformer, {callsign}. You just wrote it by hand.", "warm")],
    )

    @mission.check("attention weights — who looks at whom")
    def _weights_layer(ctx):
        _check_attention(ctx, Q, K, V, False)
        _check_attention(ctx, cross_q, cross_k, cross_v, False)

    @mission.check("causal mask — no peeking at the future")
    def _causal_layer(ctx):
        _check_attention(ctx, cQ, cK, cV, True)

    @mission.check("hot scores — stable under pressure")
    def _hot_layer(ctx):
        _check_attention(ctx, hot, hot, hot_v, False)
        _check_attention(ctx, hot, hot, hot_v, True)

    @mission.check("shape guards — reject mismatched heads")
    def _guard_layer(ctx):
        expect_raises(ctx, "attention", bad_width, why="the keys are narrower than the queries",
                      hint="Check every row of Q and K has len(K[0]) entries before you start.")
        expect_raises(ctx, "attention", bad_len, why="3 keys but only 2 values",
                      hint="Every key needs exactly one value row: compare len(K) and len(V).")

    return mission


register(Drill("t5-attention-head", "ATTENTION HEAD", 5, ("ml-math", "neural-nets"), 1500, _build_attention))
