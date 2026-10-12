"""THE LAB // AI02 MEANING SPACE — embedding lookup, mean pooling, cosine similarity, nearest neighbours."""
from __future__ import annotations

import ast
import json

from engine.mission import Fail, Mission

try:
    import numpy as np
except ImportError:  # the Lab shows `pip install numpy`; the briefing must still load without it
    np = None

SEALED = {"sklearn", "scipy", "torch", "tensorflow", "gensim", "sentence_transformers", "faiss"}

LEXICON = {
    "reactor": [0.88, -0.04, 0.32, 0.15, 0.10, -0.02], "core": [0.90, 0.00, 0.04, -0.01, 0.25, 0.15],
    "coolant": [0.69, 0.04, -0.05, 0.77, 0.02, 0.05], "turbine": [0.86, -0.01, 0.06, 0.35, 0.04, -0.03],
    "garden": [-0.04, 0.85, 0.28, 0.34, -0.04, 0.01], "seed": [0.02, 0.93, 0.01, 0.05, -0.05, 0.06],
    "moss": [0.02, 0.84, -0.02, 0.41, -0.01, -0.02], "rain": [0.04, 0.32, -0.03, 0.96, 0.00, 0.05],
    "river": [0.03, 0.17, 0.16, 0.85, -0.01, 0.03], "flood": [-0.04, 0.00, -0.06, 0.92, 0.43, 0.01],
    "lamp": [0.35, -0.02, 0.92, 0.01, 0.01, 0.09], "dawn": [0.04, 0.25, 0.95, 0.02, -0.05, 0.12],
    "ember": [0.02, 0.06, 0.84, -0.03, 0.29, 0.02], "blade": [0.24, 0.00, 0.06, -0.05, 0.90, 0.03],
    "rifle": [0.46, -0.03, -0.01, 0.04, 0.85, -0.01], "siege": [0.11, 0.05, 0.04, 0.04, 0.92, 0.09],
    "scroll": [-0.02, 0.05, 0.05, -0.04, -0.04, 0.92], "canon": [-0.03, 0.00, 0.11, -0.03, -0.06, 0.89],
    "lesson": [-0.02, 0.11, 0.15, 0.02, 0.00, 0.91], "archive": [0.32, -0.05, 0.05, 0.03, 0.04, 0.89],
}
LEXICON_JSON = "{\n" + ",\n".join(f'  "{w}": {json.dumps(v)}' for w, v in LEXICON.items()) + "\n}\n"

MISSION = Mission(
    id="AI02",
    slug="ai02_meaning_space",
    title="MEANING SPACE",
    concept="Embeddings & cosine similarity",
    enemy="SYNONYM.wraith",
    xp=380,
    par_seconds=45 * 60,
    tier=5,
    concepts=("numpy", "nlp", "ml-math", "functions"),
    requires=("numpy",),
    timeout=12,
    run_as_main=False,
    assets={"lexicon.json": LEXICON_JSON},
    enemy_art="""\
   ░▒▓▓▓▓▓▓▒░
  ▒▓ ◉    ◉ ▓▒
  ▓   ▄▄▄▄   ▓
  ▓  ▀    ▀  ▓
  ▒▓ ░ ░ ░ ░▓▒
   ▓░▒ ▓ ▒░▓
   ░  ▀ ▀  ░""",
    briefing="""\
The shards from your tokenizer are only numbers. Ask the archive for *flood* and it hands you
*lamp*: ids carry no meaning, and **SYNONYM.wraith** feeds on that confusion, swapping every
word for a stranger with a neighbouring id.

MOTHER ADA unrolls a stained chart: twenty words plotted as arrows in six dimensions. "The old
world gave every token a vector and let training push similar meanings together. Then it
measured the angle between them. Not the distance. The angle."

**Look up embeddings, measure cosine similarity without a single loop, and find each word's true
neighbours.**
""",
    why="""\
An **embedding** is a row of a learned matrix: token id `i` becomes `table[i]`. Every language
model starts with this lookup (PyTorch's `nn.Embedding`), and every semantic search engine ends
with a similarity between vectors. When you build retrieval for a chatbot you embed each document
chunk once, embed the question, and take the chunks with the highest **cosine similarity**:

```python
doc_unit = docs / np.linalg.norm(docs, axis=1, keepdims=True)
q_unit = q / np.linalg.norm(q)
scores = doc_unit @ q_unit                  # one cosine per document
top = np.argsort(-scores, kind="stable")[:5]
```

Cosine ignores length and compares direction, so a long document and a short note on the same
topic still match. Vector databases (FAISS, pgvector) are this exact computation made fast, and
deduplication, clustering and recommendations all run on it.
""",
    manual="""\
**1. Lookup is indexing.** An embedding table has one row per token id. Indexing with a list of
ids returns one row per id, in order, repeats included:

```python
import numpy as np
table = np.arange(12.0).reshape(4, 3)   # 4 tokens, 3 dimensions
table[[2, 0, 2]]                        # shape (3, 3): rows 2, 0, 2
table[[]]                               # shape (0, 3): no ids, no rows
```

**2. Mean pooling: one vector for a whole sentence.** Average the token rows down the *rows*
(axis 0). Watch the shape: averaging along axis 1 gives one number per token instead.

```python
rows = table[[1, 3]]          # (2, 3)
rows.mean(axis=0)             # (3,)  the sentence vector
rows.mean(axis=1)             # (2,)  wrong: one value per token
```

An empty sentence has no rows to average (NumPy warns and returns `nan`); return `np.zeros(d)`
instead, with `d = table.shape[1]`.

**3. Cosine similarity.** The dot product divided by both lengths. It is 1 for the same
direction, 0 for perpendicular, -1 for opposite, and scaling a vector doesn't change it:

```python
def cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0                     # a zero vector has no direction
    return float(a @ b / (na * nb))
```

*The common mistake:* `a @ b / na * nb`. Division and multiplication run left to right, so that
divides by `na` and then **multiplies** by `nb`. Brackets around the denominator.

**4. Normalize rows, then one matmul does everything.** Divide each row by its own length.
`keepdims=True` keeps the norms as a column `(n, 1)` so broadcasting divides row by row:

```python
norms = np.linalg.norm(M, axis=1, keepdims=True)   # (n, 1)
safe = np.where(norms == 0, 1.0, norms)            # zero rows stay zero
unit = M / safe
```

After that, `unit_A @ unit_B.T` is the `(n, m)` matrix of every cosine between a row of A and a
row of B, computed in compiled code. No Python loop.

**5. Nearest neighbours.** `np.argsort` sorts ascending, so sort the *negated* scores to get the
best first, and use `kind="stable"` so equal scores keep the lower index first:

```python
scores = np.array([0.2, 0.9, 0.9, -0.1])
order = np.argsort(-scores, kind="stable")   # [1, 2, 0, 3]
[int(i) for i in order[:2]]                  # [1, 2]
```

**In the real world:** scikit-learn has `cosine_similarity(A, B)` and PyTorch has
`F.cosine_similarity` and `nn.Embedding`; FAISS's `IndexFlatIP` on normalized vectors is exactly
step 4. Here those libraries are sealed: you build the engine they all share.
""",
    starter='''
"""
==============================================================================
  LAB // AI02 MEANING SPACE                          TARGET: SYNONYM.wraith
==============================================================================
  The grader calls your functions on FRESH random tables and checks them
  against MOTHER ADA's reference. NumPy only: sklearn, scipy and torch are
  sealed. lexicon.json (next to this file) has 20 real word vectors to play
  with: run this file to see your neighbours.
"""
import json

import numpy as np


# -- OBJECTIVE 1: Look up the embeddings --------------------------------------
# table has shape (vocab_size, d). Return the rows for `ids`, in order, as a
# NumPy array of shape (len(ids), d). Empty ids -> shape (0, d).
#   table = np.arange(12.0).reshape(4, 3)
#   lookup(table, [2, 0])  ->  array([[6., 7., 8.], [0., 1., 2.]])
def lookup(table, ids):
    """Embedding rows for each token id."""
    # TODO
    return None


# -- OBJECTIVE 2: One vector per sentence -------------------------------------
# Average the rows for `ids` into ONE vector of shape (d,).
# No ids -> np.zeros(d), never nan.
#   mean_pool(table, [1, 3])  ->  array([6., 7., 8.])
def mean_pool(table, ids):
    """Mean of the embedding rows: a sentence vector."""
    # TODO
    return None


# -- OBJECTIVE 3: CORRUPTED CODE ----------------------------------------------
# SYNONYM.wraith rewired the similarity gauge. Cosine similarity is
# a.b / (|a| * |b|), returned as a float. A zero vector has no direction:
# return 0.0 instead of dividing by zero.
#   cosine(np.array([1., 0.]), np.array([3., 0.]))   ->  1.0
#   cosine(np.array([1., 0.]), np.array([0., 2.]))   ->  0.0
def cosine(a, b):
    """Cosine similarity of two vectors."""
    return np.dot(a, b) / np.linalg.norm(a) * np.linalg.norm(b)


# -- OBJECTIVE 4: Unit rows -----------------------------------------------------
# Return a NEW array where every row of M has length 1. All-zero rows stay
# zero (no nan). Don't modify M.
#   normalize_rows(np.array([[3., 4.], [0., 0.]]))  ->  [[0.6, 0.8], [0., 0.]]
# Example: norms = np.linalg.norm(M, axis=1, keepdims=True)
def normalize_rows(M):
    """Each row divided by its own length (zero rows left as zeros)."""
    # TODO
    return None


# -- OBJECTIVE 5: Every cosine at once ------------------------------------------
# A is (n, d), B is (m, d). Return the (n, m) matrix whose [i, j] entry is
# cosine(A[i], B[j]). NO Python loops or comprehensions in this function:
# normalize, then one matrix multiplication.
def cosine_matrix(A, B):
    """All pairwise cosine similarities between rows of A and rows of B."""
    # TODO
    return None


# -- OBJECTIVE 6: True neighbours -----------------------------------------------
# Return a list of the k row indices of M most similar (cosine) to `query`,
# best first. Equal scores: lower index first. k larger than the number of
# rows -> every row.
#   nearest(np.array([1., 0.]), np.array([[0., 1.], [2., 0.1], [1., 1.]]), 2)  ->  [1, 2]
# Example: np.argsort(-scores, kind="stable")
def nearest(query, M, k):
    """Indices of the k most similar rows of M, most similar first."""
    # TODO
    return None


if __name__ == "__main__":
    with open("lexicon.json", encoding="utf-8") as fh:
        lexicon = json.load(fh)
    words = list(lexicon)
    vectors = np.array([lexicon[w] for w in words])
    for word in ("flood", "lamp", "canon"):
        idx = nearest(vectors[words.index(word)], vectors, 4)
        print(word, "->", [words[i] for i in idx] if idx is not None else "TODO")
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Token 41 and token 42 sit side by side in the vocabulary. Are they related, {callsign}?"},
            {"speaker": "ada", "mood": "neutral",
             "text": "No. Ids are names, not meanings. Meaning lives in the vectors. Today you learn to measure it."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "SYNONYM.wraith is swapping words by id distance. Show it what an angle is."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Shapes first. Print .shape on everything you touch; most crashes here are a (n,) meeting an (n, 1)."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Crash in the vector bay. The COMBAT LOG shows the exact array that broke it."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "Divide by zero, get a nan. Sell a nan, get nothing. Guard your norms, kid."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Read the expected and the returned values side by side. Is the error a scale, a sign, or a shape?"}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "argsort climbs from smallest to largest. Which end of that ladder are you standing on?"}],
            [{"speaker": "vex", "mood": "smirk",
              "text": "Still looping over rows? My grandmother's toaster vectorizes faster than that."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Flood finds rain and river. Lamp finds dawn. The wraith has nowhere left to hide."},
            {"speaker": "ada", "mood": "neutral",
             "text": "Second page of the canon: meaning is direction. Next, we teach a sequence to look at itself."},
            {"speaker": "cipher", "mood": "warm",
             "text": "Similarity engine online, {callsign}. No loops harmed in the making."},
        ],
    },
)


# ── reference (MOTHER ADA's) ─────────────────────────────────────────────────────

def _ref_lookup(table, ids):
    return table[np.asarray(ids, dtype=int)].reshape(len(ids), table.shape[1])


def _ref_pool(table, ids):
    return table[list(ids)].mean(axis=0) if len(ids) else np.zeros(table.shape[1])


def _ref_cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return 0.0 if na == 0 or nb == 0 else float(a @ b / (na * nb))


def _ref_unit(M):
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    return M / np.where(norms == 0, 1.0, norms)


def _ref_matrix(A, B):
    return _ref_unit(A) @ _ref_unit(B).T


def _ref_nearest(query, M, k):
    q = np.asarray(query, dtype=float)
    nq = np.linalg.norm(q)
    scores = _ref_unit(M) @ (q / nq if nq else q)
    return [int(i) for i in np.argsort(-scores, kind="stable")[:k]]


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
                raise Fail(f"`import {name}` found (line {node.lineno}). Similarity libraries are sealed here.",
                           hint="Build it with NumPy: norms, a division and a matmul. The manual shows the library version.")


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


def _call(fn, label: str, *args, hint: str = ""):
    copies = [a.copy() if isinstance(a, np.ndarray) else a for a in args]
    try:
        out = fn(*copies)
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        if not hint and isinstance(exc, ValueError) and ("shape" in str(exc) or "broadcast" in str(exc)):
            hint = "A shape mismatch. Print the .shape of each array; keepdims=True keeps a column (n, 1)."
        raise Fail(f"`{label}` raised {type(exc).__name__}: {exc}",
                   hint=hint or "Call it yourself on this input and read the traceback.")
    for original, passed in zip(args, copies):
        if isinstance(original, np.ndarray) and not np.array_equal(original, passed):
            raise Fail(f"`{label}` changed its input array in place.",
                       hint="Build and return a new array (M / norms creates one); the caller still needs the original.")
    if out is None:
        raise Fail(f"`{label}` returned None: the TODO is still open.", hint="End the function with `return ...`.")
    return out


def _array(got, label: str, shape: tuple, hint: str = ""):
    if not isinstance(got, np.ndarray):
        raise Fail(f"`{label}` returned a {type(got).__name__}, expected a NumPy array of shape {shape}.",
                   hint=hint or "Return the NumPy array itself (indexing and arithmetic on arrays give arrays).")
    if got.shape != tuple(shape):
        raise Fail(f"`{label}` returned shape {got.shape}, expected {tuple(shape)}.", hint=hint)
    if got.size and not np.all(np.isfinite(got)):
        raise Fail(f"`{label}` returned nan/inf: {_show(got)}.",
                   hint="That's a division by zero. A zero vector has no length: handle it before dividing.")
    return got


def _close(label: str, got, want, hint: str = "", tol: float = 1e-7) -> None:
    if not np.allclose(got, want, atol=tol, rtol=1e-6):
        raise Fail(f"`{label}` returned {_show(got)}, expected {_show(want)}.", hint=hint)


def _no_loops(ctx, name: str) -> None:
    for node in ctx.tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            for sub in ast.walk(node):
                if isinstance(sub, (ast.For, ast.While, ast.ListComp, ast.GeneratorExp, ast.DictComp, ast.SetComp)):
                    raise Fail(f"`{name}` uses a Python loop (line {sub.lineno}). This layer is about vectorizing.",
                               hint="Normalize both matrices' rows, then a single  unit_A @ unit_B.T  computes every cosine.")


# ── firewall layers ──────────────────────────────────────────────────────────────

@MISSION.check("Lookup — `lookup` returns one row per token id")
def _lookup(ctx):
    fn = _fn(ctx, "lookup")
    rng = np.random.default_rng(202)
    for vocab, d, ids in ((4, 3, [2, 0]), (12, 5, None), (30, 8, None), (6, 4, [5, 5, 5]), (7, 3, [])):
        table = rng.normal(size=(vocab, d)).round(3)
        if ids is None:
            ids = [int(i) for i in rng.integers(0, vocab, size=int(rng.integers(3, 9)))]
        label = f"lookup(table{table.shape}, {ids})"
        got = _array(_call(fn, label, table, list(ids)), label, (len(ids), d),
                     hint="One row per id: table[ids]. An empty id list still gives a (0, d) array.")
        _close(label, got, _ref_lookup(table, ids), hint="Row i of the answer is table[ids[i]], in order, repeats included.")


@MISSION.check("Sentence vector — `mean_pool` averages down the rows")
def _pool(ctx):
    fn = _fn(ctx, "mean_pool")
    rng = np.random.default_rng(303)
    for vocab, d, ids in ((4, 3, [1, 3]), (10, 6, None), (25, 4, None), (5, 7, [])):
        table = rng.normal(size=(vocab, d)).round(3)
        if ids is None:
            ids = [int(i) for i in rng.integers(0, vocab, size=int(rng.integers(2, 7)))]
        label = f"mean_pool(table{table.shape}, {ids})"
        hint = "Average over axis=0 (down the rows): the result has one value per dimension, shape (d,)."
        if not ids:
            hint = "No ids, nothing to average: return np.zeros(table.shape[1])."
        got = _array(_call(fn, label, table, list(ids)), label, (d,), hint=hint)
        _close(label, got, _ref_pool(table, ids), hint=hint)


@MISSION.check("CORRUPTED `cosine` repaired — angle, not scale")
def _cosine(ctx):
    fn = _fn(ctx, "cosine")
    rng = np.random.default_rng(404)
    a = rng.normal(size=6)
    cases = [(np.array([1.0, 0.0]), np.array([3.0, 0.0])), (np.array([1.0, 0.0]), np.array([0.0, 2.0])),
             (np.array([2.0, -1.0]), np.array([-4.0, 2.0])), (a, a * 7.5)]
    cases += [(rng.normal(size=8) * 3, rng.normal(size=8) * 0.5) for _ in range(4)]
    for x, y in cases:
        label = f"cosine({_show(x, 60)}, {_show(y, 60)})"
        got = _call(fn, label, x, y)
        want = _ref_cos(x, y)
        try:
            value = float(got)
        except (TypeError, ValueError):
            raise Fail(f"`{label}` returned {_show(got)}, expected one float like {want:.4f}.",
                       hint="a @ b is a single number; so is each norm. Return float(...) of the ratio.")
        if not np.isclose(value, want, atol=1e-9):
            hint = "Brackets: a.b / (|a| * |b|). Without them you divide by |a| and then MULTIPLY by |b|."
            if np.isclose(value, np.dot(x, y), atol=1e-9):
                hint = "That's the raw dot product. Divide by the product of both lengths."
            raise Fail(f"`{label}` returned {value:.6g}, expected {want:.6g}.", hint=hint)
    zero = np.zeros(4)
    for x, y in ((zero, np.ones(4)), (np.ones(4), zero)):
        label = f"cosine({_show(x, 40)}, {_show(y, 40)})"
        try:
            with np.errstate(all="ignore"):
                got = fn(x.copy(), y.copy())
        except Exception as exc:  # noqa: BLE001
            raise Fail(f"`{label}` raised {type(exc).__name__}: {exc}",
                       hint="Check the norms first: if either is 0, return 0.0 before dividing.")
        if got is None or not np.isfinite(float(got)) or float(got) != 0.0:
            raise Fail(f"`{label}` returned {_show(got)}, expected 0.0.",
                       hint="A zero vector has no direction. If either norm is 0, return 0.0 instead of dividing.")


@MISSION.check("Unit rows — `normalize_rows` (axis, keepdims, zero rows)")
def _normalize(ctx):
    fn = _fn(ctx, "normalize_rows")
    rng = np.random.default_rng(505)
    mats = [np.array([[3.0, 4.0], [0.0, 0.0]]), rng.normal(size=(5, 3)) * 4, rng.normal(size=(2, 6))]
    tall = rng.normal(size=(6, 6))
    tall[[1, 4]] = 0.0
    mats.append(tall)
    for M in mats:
        label = f"normalize_rows({_show(M, 70)})"
        with np.errstate(all="ignore"):
            got = _call(fn, label, M)
        got = _array(got, label, M.shape,
                     hint="Divide each row by its own norm: np.linalg.norm(M, axis=1, keepdims=True), and keep zero rows at zero.")
        want = _ref_unit(M)
        if not np.allclose(got, want, atol=1e-9):
            hint = "Each ROW must have length 1: norms along axis=1, kept as a column (n, 1) with keepdims=True."
            if np.allclose(got, M / np.linalg.norm(M, axis=0, keepdims=True), atol=1e-9):
                hint = "You normalized the columns (axis=0). Rows are axis=1."
            elif np.allclose(got, M / np.linalg.norm(M), atol=1e-9):
                hint = "You divided by the norm of the whole matrix. Each row needs its own norm: axis=1, keepdims=True."
            raise Fail(f"`{label}` returned {_show(got)}, expected {_show(want)}.", hint=hint)


@MISSION.check("Every angle at once — `cosine_matrix` (n, m), no loops")
def _matrix(ctx):
    fn = _fn(ctx, "cosine_matrix")
    _no_loops(ctx, "cosine_matrix")
    rng = np.random.default_rng(606)
    for n, m, d in ((3, 5, 4), (7, 2, 6), (1, 1, 3), (40, 25, 16)):
        A, B = rng.normal(size=(n, d)) * 2, rng.normal(size=(m, d))
        if n > 3:
            A[2] = 0.0
        label = f"cosine_matrix(A{A.shape}, B{B.shape})"
        with np.errstate(all="ignore"):
            got = _call(fn, label, A, B)
        got = _array(got, label, (n, m),
                     hint="Entry [i, j] compares A[i] with B[j]: unit_A (n, d) @ unit_B.T (d, m) is (n, m).")
        _close(label, got, _ref_matrix(A, B),
               hint="Normalize the rows of BOTH matrices first; then the matmul gives cosines, not raw dot products.")


@MISSION.check("True neighbours — `nearest` (best first, ties to the lower index)")
def _nearest(ctx):
    fn = _fn(ctx, "nearest")
    rng = np.random.default_rng(707)
    cases = [(np.array([1.0, 0.0]), np.array([[0.0, 1.0], [2.0, 0.1], [1.0, 1.0]]), 2)]
    for n, d, k in ((12, 5, 3), (30, 8, 5), (4, 3, 10)):
        cases.append((rng.normal(size=d), rng.normal(size=(n, d)), k))
    tied = rng.normal(size=(9, 4))
    tied[[2, 5, 7]] = tied[0] * np.array([[1.0], [2.0], [0.5]])   # powers of two: exact ties
    cases.append((tied[0] * 2, tied, 4))
    words = list(LEXICON)
    vectors = np.array([LEXICON[w] for w in words])
    for word in ("flood", "lamp", "canon"):
        cases.append((vectors[words.index(word)], vectors, 3))
    for query, M, k in cases:
        label = f"nearest({_show(query, 50)}, M{M.shape}, {k})"
        got = _call(fn, label, query, M, k)
        try:
            got_list = [int(i) for i in np.asarray(got).ravel()]
        except (TypeError, ValueError):
            raise Fail(f"`{label}` returned {_show(got)}, expected a list of row indices.",
                       hint="Return the indices themselves, e.g. [int(i) for i in order[:k]].")
        want = _ref_nearest(query, M, k)
        if got_list != want:
            hint = "Score every row with cosine, sort the NEGATED scores with kind='stable', take the first k."
            scores = _ref_unit(M) @ (query / np.linalg.norm(query))
            if got_list == [int(i) for i in np.argsort(scores, kind="stable")[:k]]:
                hint = "Those are the LEAST similar rows: np.argsort sorts ascending. Sort -scores instead."
            elif got_list == [int(i) for i in np.argsort(-(M @ query), kind="stable")[:k]]:
                hint = "You ranked by raw dot product, so long vectors win. Normalize first: rank by cosine."
            elif sorted(got_list) == sorted(want):
                hint = "Right rows, wrong order: equal scores keep the lower index first (kind='stable')."
            if M is vectors:
                q = words[[i for i, w in enumerate(words) if np.array_equal(vectors[i], query)][0]]
                raise Fail(f"`nearest` on lexicon word {q!r} returned {[words[i] for i in got_list if 0 <= i < len(words)]}, "
                           f"expected {[words[i] for i in want]}.", hint=hint)
            raise Fail(f"`{label}` returned {got_list}, expected {want}.", hint=hint)

