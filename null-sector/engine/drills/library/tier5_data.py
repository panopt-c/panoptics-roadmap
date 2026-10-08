"""Tier-5 drills: classic machine learning, by hand.

* t5-standardize       z-scores, min-max scaling, and a scaler fitted on training data only
* t5-cosine-recall     cosine similarity and top-k retrieval (the R in RAG)
* t5-knn-classify      k-nearest-neighbours with exact tie-breaking, and accuracy
* t5-kmeans-step       one k-means assignment + update, then iterate to convergence
* t5-split-seed        a reproducible train/test split and k-fold cross-validation
* t5-confusion-metrics confusion matrix, precision / recall / F1, macro-F1
"""
from __future__ import annotations

import copy
import math
import random

from engine.drills import Drill, register
from engine.drills.library.tier5_common import (
    build, call_text, expect, expect_raises, function, invoke, line, near, num, r, rounded, show, spotter,
    vector,
)
from engine.mission import Fail


def _mean(xs):
    return sum(xs) / len(xs)


def _pstd(xs):
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def _sstd(xs):
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _zero_div(why: str, fix: str):
    """An `errors` diagnoser for ZeroDivisionError with a drill-specific explanation."""
    def diagnose(exc):
        if isinstance(exc, ZeroDivisionError):
            return why, fix
        if type(exc).__name__ == "StatisticsError":
            return ("The statistics module refuses this input.", fix)
        return None
    return diagnose


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-standardize — CALIBRATION ARRAY
# ══════════════════════════════════════════════════════════════════════════════════════

def _ref_standardize(values):
    if not values:
        return []
    m, s = _mean(values), _pstd(values)
    if s == 0:
        return [0.0] * len(values)
    return [(v - m) / s for v in values]


def _ref_min_max(values, lo=0.0, hi=1.0):
    if lo >= hi:
        raise ValueError("lo must be below hi")
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [float(lo)] * len(values)
    return [lo + (v - low) * (hi - lo) / (high - low) for v in values]


def _ref_fit(rows):
    if not rows:
        raise ValueError("no rows to fit")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("rows have different lengths")
    cols = [list(c) for c in zip(*rows)]
    return ([_mean(c) for c in cols], [_pstd(c) for c in cols])


def _ref_transform(rows, means, stds):
    if len(means) != len(stds):
        raise ValueError("means and stds differ in length")
    out = []
    for row in rows:
        if len(row) != len(means):
            raise ValueError("row width doesn't match the scaler")
        out.append([0.0 if s == 0 else (x - m) / s for x, m, s in zip(row, means, stds)])
    return out


@spotter
def _standardize_spot(got, args, _kwargs):
    values = args[0]
    m, s = _mean(values), _pstd(values)
    if len(values) > 1 and near(got, [(v - m) / _sstd(values) for v in values]):
        return ("You divided by n - 1 (the SAMPLE std, statistics.stdev). This contract uses the population "
                "std: divide by n (statistics.pstdev).", "")
    if s and near(got, [(v - m) / (s * s) for v in values]):
        return ("You divided by the variance. Divide by its square root, the standard deviation.", "")
    if s and near(got, [v / s for v in values]):
        return ("You scaled but never centred: subtract the mean before dividing by the std.", "")
    if near(got, [v - m for v in values]):
        return ("Centred but not scaled: divide each (v - mean) by the std too.", "")
    return None


@spotter
def _min_max_spot(got, args, kwargs):
    values = kwargs.get("values", args[0] if args else [])
    lo = kwargs.get("lo", args[1] if len(args) > 1 else 0.0)
    hi = kwargs.get("hi", args[2] if len(args) > 2 else 1.0)
    if (lo, hi) != (0.0, 1.0) and near(got, _ref_min_max(values)):
        return (f"You scaled to 0..1, but this call asked for {lo}..{hi}.",
                "Scale to 0..1 first (t), then stretch: lo + t * (hi - lo).")
    top = max(values)
    if top and near(got, [v / top for v in values]):
        return ("You divided by the max. Subtract the min first, then divide by the range (max - min).", "")
    return None


@spotter
def _fit_spot(got, args, _kwargs):
    rows = args[0]
    if near(got, ([_mean(row) for row in rows], [_pstd(row) for row in rows])):
        return ("Those are stats for each ROW (sample). A scaler works per COLUMN: one mean and one std "
                "per feature.", "zip(*rows) hands you the columns.")
    cols = [list(c) for c in zip(*rows)]
    if len(rows) > 1 and near(got, ([_mean(c) for c in cols], [_sstd(c) for c in cols])):
        return ("Your stds divide by n - 1 (sample std). This contract uses the population std: divide by n.", "")
    return None


@spotter
def _transform_spot(got, args, _kwargs):
    rows, means, stds = args
    if near(got, _ref_transform(rows, *_ref_fit(rows))):
        return ("You re-fitted the scaler on the rows you were given. That's data leakage: new data must be "
                "scaled with the TRAINING means and stds, exactly as passed in.",
                "Never compute fresh stats here. Use means[j] and stds[j] for column j.")
    return None


_SCALE_MANUAL = """\
**Why scale at all?** Gradient descent takes one learning rate for every weight. If one
feature is in kelvin (≈ 300) and another in volts (≈ 0.5), the kelvin weight gets gradients
hundreds of times larger: training zig-zags or explodes. Put features on one scale first.

**Standardize (z-score):** subtract the mean, divide by the standard deviation. The result has
mean 0 and std 1. We use the *population* std (divide by `n`), like NumPy's default:

```python
m = sum(xs) / len(xs)
std = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
z = [(x - m) / std for x in xs]
```

**A constant feature has std 0.** Dividing would crash, and the feature carries no information
anyway, so map every value to `0.0`.

**Min-max scaling** squeezes values into a range, `[0, 1]` by default:

```python
t = (x - low) / (high - low)          # 0 at the min, 1 at the max
scaled = lo + t * (hi - lo)           # stretch to any [lo, hi]
```

**Fit on train, apply everywhere.** The means and stds are learned from the *training* rows
only, then reused, unchanged, on validation, test and live data. Re-fitting on test data lets
it leak into your model, and your scores lie. `zip(*rows)` turns rows into columns:

```python
list(zip(*[[1, 10], [2, 20]]))        # [(1, 2), (10, 20)]
```
"""


def _distinct(rng, make):
    """Call make() until it gives a list with at least two different values."""
    while True:
        values = make()
        if len(set(values)) > 1:
            return values


def _build_standardize(rng):
    kelvin = _distinct(rng, lambda: [round(rng.uniform(280, 360), 1) for _ in range(rng.randint(5, 7))])
    volts = _distinct(rng, lambda: vector(rng, rng.randint(4, 6), -5, 5))
    counts = _distinct(rng, lambda: [float(rng.randint(0, 60)) for _ in range(6)])
    const = rng.choice([4.0, -1.5, 2.25, 300.0])
    std_main = [(kelvin,), (volts,), (counts,)]
    std_edge = [([const] * rng.randint(3, 5),), ([num(rng, -9, 9)],), ([],)]

    mm_main = [(_distinct(rng, lambda: vector(rng, 5, -4, 4)),),
               (_distinct(rng, lambda: [round(rng.uniform(280, 360), 1) for _ in range(4)]),),
               (_distinct(rng, lambda: vector(rng, 6, 0, 50)), -1.0, 1.0),
               {"values": _distinct(rng, lambda: vector(rng, 4, -10, 10)), "lo": 10.0, "hi": 20.0}]
    mm_edge = [([const] * 4,), ([num(rng, -5, 5)],), ([],), ([const] * 3, -1.0, 1.0)]

    def table(n):
        return [[round(rng.uniform(280, 360), 1), num(rng, -0.9, 0.9), float(rng.randint(0, 60))]
                for _ in range(n)]

    train = table(rng.randint(6, 8))
    flat_train = [[num(rng, -5, 5), const] for _ in range(4)]
    fit_cases = [(train,), (flat_train,), ([[num(rng, 0, 9), num(rng, 0, 9)]],)]
    test_rows = [[round(rng.uniform(300, 420), 1), num(rng, -2, 2), float(rng.randint(30, 99))] for _ in range(3)]
    means, stds = _ref_fit(train)
    flat_means, flat_stds = _ref_fit(flat_train)
    flat_test = [[num(rng, -5, 5), round(const + rng.choice([-1.0, 1.0, 2.0]), 2)] for _ in range(3)]
    tf_cases = [(test_rows, means, stds), (flat_test, flat_means, flat_stds), ([], means, stds)]

    sample = [r(z, 3) for z in _ref_standardize(kelvin)]
    prompt = f"""\
The rig you'll use to read the Core is only as good as its inputs, and the Monastery's sensor
array is a mess: hull temperature in kelvin, coil drift in volts, packet counts in the dozens.
Feed that raw into a model and the biggest number wins every argument. NOVA needs it calibrated.

**Write four functions** (pure Python, lists of floats, never change the lists you're given):

- `standardize(values)`: z-scores `(v - mean) / std` with the **population** std (divide by `n`).
  If the std is 0 (all values equal), return `0.0` for every value. `[]` gives `[]`.
- `min_max(values, lo=0.0, hi=1.0)`: rescale so the min maps to `lo` and the max to `hi`. If all
  values are equal, every one maps to `lo`. `[]` gives `[]`. Raise `ValueError` if `lo >= hi`.
- `fit_scaler(rows)`: a tuple `(means, stds)`, one mean and one population std **per column**.
  Raise `ValueError` if `rows` is empty or the rows have different lengths.
- `transform(rows, means, stds)`: standardize every row with the stats it was given, as new
  lists. A column whose std is 0 becomes `0.0`. Raise `ValueError` if a row's width doesn't
  match `len(means)`.

**Hull temperature feed (this contract):**

```python
standardize({show(kelvin, 200)})
# ≈ {sample}
```
"""
    starter = '''
import math


def standardize(values):
    """(v - mean) / std for each value, population std. Constant input -> all 0.0."""
    # your code
    pass


def min_max(values, lo=0.0, hi=1.0):
    """Rescale so min -> lo and max -> hi. Constant input -> all lo. ValueError if lo >= hi."""
    # your code
    pass


def fit_scaler(rows):
    """Return (means, stds): one mean and one population std per COLUMN of rows."""
    # your code
    pass


def transform(rows, means, stds):
    """Standardize each row with the given stats. std 0 -> 0.0. ValueError on a width mismatch."""
    # your code
    pass


if __name__ == "__main__":
    print(standardize([2.0, 4.0, 6.0]))           # ≈ [-1.2247, 0.0, 1.2247]
    print(min_max([5.0, 10.0, 7.5]))              # [0.0, 1.0, 0.5]
    print(min_max([5.0, 10.0], -1.0, 1.0))        # [-1.0, 1.0]
    train = [[300.0, 0.5], [320.0, 0.1], [310.0, 0.3]]
    means, stds = fit_scaler(train)
    print(means, stds)                            # [310.0, 0.3] [8.16..., 0.163...]
    print(transform([[330.0, 0.3]], means, stds))  # ≈ [[2.449, 0.0]]
'''
    mission = build(
        title="CALIBRATION ARRAY", enemy="DRIFT.sensor", prompt=prompt, manual=_SCALE_MANUAL, starter=starter,
        concepts=("ml-math", "numeric", "lists"),
        intro=[line("nova", "Calibration contract, {callsign}! Sensor feeds are screaming in five different units. Bring them to one scale.", "warm"),
               line("cipher", "Fit the stats on training data. Reuse them on everything else. That rule has sunk better engineers than you.", "neutral")],
        victory=[line("nova", "Array's calibrated. Every feed reads mean zero, spread one. Contract closed, nice and clean!", "warm"),
                 line("cipher", "No leakage. Your test scores will mean something now.", "neutral")],
    )

    @mission.check("standardize — z-scores for one feed")
    def _standardize_layer(ctx):
        expect(ctx, "standardize", std_main, _ref_standardize, spot=_standardize_spot, pure=True,
               errors=_zero_div("Something divided by zero.", "Compute the mean and std first; check them before dividing."),
               hint="mean = sum / n; std = sqrt(sum of (v - mean)**2 / n); then (v - mean) / std for each v.")
        expect(ctx, "standardize", std_edge, _ref_standardize, spot=_standardize_spot,
               errors=_zero_div("An empty list has no mean (len is 0), and equal values have std 0.",
                                "Return [] for [] and [0.0] * len(values) when the std is 0, before dividing."),
               hint="Handle the two edge cases first: an empty list, then a std of 0.")

    @mission.check("min_max — squeeze into a range")
    def _min_max_layer(ctx):
        expect(ctx, "min_max", mm_main, _ref_min_max, spot=_min_max_spot, pure=True,
               hint="t = (v - min) / (max - min), then lo + t * (hi - lo).")
        expect(ctx, "min_max", mm_edge, _ref_min_max, spot=_min_max_spot,
               errors=_zero_div("Every value was equal, so max - min was 0.",
                                "When max == min, return [lo] * len(values) (as floats) before dividing."),
               hint="Equal values map to lo. An empty list gives [].")
        expect_raises(ctx, "min_max", ([1.0, 2.0], 1.0, 1.0), why="lo == hi leaves no range to fill",
                      hint="Check at the top:  if lo >= hi: raise ValueError(...)")
        expect_raises(ctx, "min_max", ([1.0, 2.0], 5.0, -5.0), why="lo is above hi")

    @mission.check("fit_scaler — learn column stats from training data")
    def _fit_layer(ctx):
        expect(ctx, "fit_scaler", fit_cases, _ref_fit, spot=_fit_spot, pure=True,
               hint="cols = list(zip(*rows)); then a mean and a population std for each column.")
        expect_raises(ctx, "fit_scaler", ([],), why="there's nothing to learn from")
        expect_raises(ctx, "fit_scaler", ([[1.0, 2.0], [3.0]],), why="the second row is missing a feature",
                      hint="Compare every row's length with the first row's before you zip.")

    @mission.check("transform — reuse the training stats (no leakage)")
    def _transform_layer(ctx):
        expect(ctx, "transform", tf_cases, _ref_transform, spot=_transform_spot, pure=True,
               errors=_zero_div("A column that never varied in training has std 0.",
                                "Map that column to 0.0 instead of dividing."),
               hint="new[j] = (row[j] - means[j]) / stds[j], or 0.0 when stds[j] == 0.")
        expect_raises(ctx, "transform", ([[1.0, 2.0]], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]),
                      why="a 2-wide row can't use a 3-feature scaler",
                      hint="zip() would silently drop the extra feature. Compare len(row) with len(means) yourself.")

    return mission


register(Drill("t5-standardize", "CALIBRATION ARRAY", 5, ("ml-math", "numeric", "lists"), 1200, _build_standardize))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-cosine-recall — ECHO SEARCH
# ══════════════════════════════════════════════════════════════════════════════════════

def _norm(v):
    return math.sqrt(sum(x * x for x in v))


def _ref_cosine(a, b):
    if len(a) != len(b):
        raise ValueError("vectors have different lengths")
    na, nb = _norm(a), _norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _ref_top_k(query, memory, k):
    scored = [(key, _ref_cosine(query, vec)) for key, vec in memory.items()]
    scored.sort(key=lambda kv: (-kv[1], kv[0]))
    return scored[:max(k, 0)]


@spotter
def _cosine_spot(got, args, _kwargs):
    a, b = args
    d = sum(x * y for x, y in zip(a, b))
    na, nb = _norm(a), _norm(b)
    if na and nb:
        expected = d / (na * nb)
        if abs(d - expected) > 1e-6 and near(got, d):
            return ("That's the raw dot product: it grows with the vectors' length. Cosine divides by both "
                    "norms, so only direction counts.", "")
        if near(got, d / na) or near(got, d / nb):
            return ("You divided by only one norm. Divide by |a| * |b|.", "")
        if near(got, 1 - expected):
            return ("That's the cosine DISTANCE (1 - similarity). Return the similarity itself.", "")
    return None


@spotter
def _top_k_spot(got, args, _kwargs):
    query, memory, k = args
    full = _ref_top_k(query, memory, len(memory))
    expected = full[:max(k, 0)]
    if not isinstance(got, list) or len(got) != len(expected):
        return None
    ascending = sorted(full, key=lambda kv: (kv[1], kv[0]))[:max(k, 0)]
    if near(got, ascending):
        return ("You ranked the LEAST similar fragments first. Highest cosine first.",
                "sorted(..., reverse=True), or sort by -score.")
    if all(isinstance(item, tuple) and len(item) == 2 for item in got):
        for (g_key, g_score), (e_key, e_score) in zip(got, expected):
            if g_key != e_key and near(g_score, e_score, 1e-12):
                return (f"'{g_key}' and '{e_key}' tie at {r(e_score, 6)}. Ties go to the smaller id "
                        "(alphabetical), so '{e_key}' comes first.".replace("{e_key}", str(e_key)),
                        "Sort by (-score, key): a tuple key settles ties on its second item.")
    return None


_COSINE_MANUAL = """\
**An embedding is meaning as a list of numbers.** Models map text to vectors so that related
ideas point in similar directions. Search then becomes geometry: find the stored vectors that
point the same way as the query. That's the retrieval step of every RAG system.

**Cosine similarity measures direction, not length:**

```python
dot  = sum(x * y for x, y in zip(a, b))
norm = lambda v: math.sqrt(sum(x * x for x in v))
cos  = dot / (norm(a) * norm(b))     # 1.0 same way, 0.0 unrelated, -1.0 opposite
```

So `[1, 2]` and `[10, 20]` score exactly 1.0: one is just a louder version of the other.

**A zero vector has no direction.** Its norm is 0 and the division would crash. Retrieval code
treats it as "unrelated" and scores it `0.0`.

**Ranking with a tie-breaker.** Sort by a tuple: Python compares the first item, then the
second only on a tie. Negate the score to get highest-first:

```python
scored.sort(key=lambda pair: (-pair[1], pair[0]))   # best score first, ties by id A→Z
top = scored[:k]                                     # slicing past the end is safe
```
"""


def _build_cosine(rng):
    width = 4

    def unit_vector():
        while True:
            v = vector(rng, width, -3, 3)
            if _norm(v) > 0.5:
                return v

    cos_cases = []
    for _ in range(3):
        cos_cases.append((unit_vector(), unit_vector()))
    base = unit_vector()
    cos_cases.append((base, [x * rng.choice([2.0, 4.0, 0.5]) for x in base]))       # same direction -> 1.0
    cos_cases.append((base, [-x for x in base]))                                      # opposite -> -1.0
    cos_cases.append(([1.0, 0.0, 0.0], [0.0, rng.choice([2.0, 3.5]), 0.0]))          # orthogonal -> 0.0
    zero_cases = [([0.0] * width, unit_vector()), (unit_vector(), [0.0] * width), ([], [])]
    bad_cos = (unit_vector(), unit_vector()[:3])

    ids = rng.sample(range(100, 999), 9)
    names = [f"mem-{i}" for i in ids]
    memory = {name: unit_vector() for name in names[:7]}
    query = unit_vector()
    # a guaranteed tie: one fragment and a louder copy of it, the alphabetically-first one stored LAST
    twin_a, twin_b = sorted(names[7:9], reverse=True)
    tied = dict(memory)
    tied[twin_a] = unit_vector()
    tied[twin_b] = [x * 2.0 for x in tied[twin_a]]
    with_zero = dict(list(memory.items())[:4])
    with_zero["mem-000"] = [0.0] * width
    top_cases = [(query, memory, 3), (unit_vector(), memory, 1), (query, with_zero, 5)]
    edge_cases = [(query, tied, len(tied)), (query, memory, 0), (query, memory, len(memory) + 4), (query, {}, 3)]
    bad_memory = dict(list(memory.items())[:3])
    bad_memory["mem-bad"] = [1.0, 2.0]

    sample = [(k, r(s, 4)) for k, s in _ref_top_k(query, memory, 2)]
    prompt = f"""\
CIPHER isn't a program you found. It's an archive of you: every memory you had, stored as an
embedding, a list of numbers pointing in the direction of what it meant. The archive is
corrupted and unsorted. To ask it a question, you search it the way the Core searches
everything: by angle.

**Write three functions:**

- `cosine(a, b)`: `dot(a, b) / (|a| * |b|)`, where `|v| = sqrt(sum of v[i]**2)`. If either vector
  has norm 0, return `0.0`. Raise `ValueError` if the lengths differ.
- `top_k(query, memory, k)`: `memory` maps an id (str) to a vector. Return a list of `(id, score)`
  tuples for the `k` fragments with the highest cosine score against `query`, best first.
  **Ties go to the smaller id** (alphabetical). `k` larger than the memory returns everything;
  `k <= 0` or an empty memory returns `[]`. Don't change `memory`.

(You'll probably want a little `norm(v)` helper too.)

**Recall test (this contract):**

```python
query = {show(query)}
top_k(query, memory, 2)    # ≈ {sample}
```
"""
    starter = '''
import math


def cosine(a, b):
    """dot(a, b) / (|a| * |b|). 0.0 if either norm is 0. ValueError if lengths differ."""
    # your code
    pass


def top_k(query, memory, k):
    """The k (id, score) pairs most similar to query, best first, ties by id A->Z."""
    # your code
    pass


if __name__ == "__main__":
    print(cosine([1.0, 2.0], [10.0, 20.0]))     # 1.0  (same direction)
    print(cosine([1.0, 0.0], [0.0, 5.0]))       # 0.0  (unrelated)
    memory = {"mem-a": [1.0, 0.0], "mem-b": [0.6, 0.8], "mem-c": [-1.0, 0.1]}
    print(top_k([1.0, 0.1], memory, 2))         # [('mem-a', 0.995...), ('mem-b', 0.676...)]
'''
    mission = build(
        title="ECHO SEARCH", enemy="ARCHIVE.shard", prompt=prompt, manual=_COSINE_MANUAL, starter=starter,
        concepts=("ml-math", "sorting", "numeric"),
        intro=[line("cipher", "These are my fragments. Yours, technically. Search them by direction, not by size.", "neutral"),
               line("cipher", "Two memories can tie. When they do, the archive is ordered by id. Respect the order.", "neutral")],
        victory=[line("cipher", "Recall is clean. I remember a lab, {callsign}. Rain on a window. You, writing a training loop.", "warm"),
                 line("oracle", "You have begun to remember. Most who built me preferred not to.", "cold")],
    )

    @mission.check("cosine — direction, not size")
    def _cosine_layer(ctx):
        expect(ctx, "cosine", cos_cases, _ref_cosine, spot=_cosine_spot, pure=True,
               hint="dot(a, b) divided by (norm(a) * norm(b)), where norm(v) = math.sqrt(sum(x * x for x in v)).")

    @mission.check("cosine guards — zero vectors and bad shapes")
    def _guard_layer(ctx):
        expect(ctx, "cosine", zero_cases, _ref_cosine, spot=_cosine_spot,
               errors=_zero_div("A zero vector has norm 0, so the division crashed.",
                                "If either norm is 0, return 0.0 before dividing."),
               hint="Check both norms before you divide; an empty pair of vectors also has norm 0.")
        expect_raises(ctx, "cosine", bad_cos, why="a 4-wide and a 3-wide vector can't be compared",
                      hint="zip() silently drops the extra number. Compare len(a) and len(b) first.")

    @mission.check("top_k — recall the closest fragments")
    def _top_layer(ctx):
        expect(ctx, "top_k", top_cases, _ref_top_k, spot=_top_k_spot, pure=True,
               hint="Score every (id, vector) pair with cosine, sort best-first, slice the first k.")

    @mission.check("top_k edge cases — ties, k past the end, empty memory")
    def _edge_layer(ctx):
        expect(ctx, "top_k", edge_cases, _ref_top_k, spot=_top_k_spot,
               hint="Sort with key=lambda pair: (-pair[1], pair[0]). Slicing [:k] never fails, but k <= 0 must give [].")
        expect_raises(ctx, "top_k", (query, bad_memory, 2), why="'mem-bad' is 2-wide but the query is 4-wide",
                      hint="If top_k scores with your cosine(), the length check comes for free.")

    return mission


register(Drill("t5-cosine-recall", "ECHO SEARCH", 5, ("ml-math", "sorting", "numeric"), 1000, _build_cosine))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-knn-classify — NEAREST NEIGHBOURS
# ══════════════════════════════════════════════════════════════════════════════════════

def _ref_distance(a, b):
    if len(a) != len(b):
        raise ValueError("points have different dimensions")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _vote(nearest):
    counts = {}
    for label in nearest:
        counts[label] = counts.get(label, 0) + 1
    best = max(counts.values())
    return next(label for label in nearest if counts[label] == best)


def _ref_knn(train_X, train_y, x, k):
    if len(train_X) != len(train_y):
        raise ValueError("train_X and train_y differ in length")
    if not 1 <= k <= len(train_X):
        raise ValueError("k must be between 1 and len(train_X)")
    order = sorted(range(len(train_X)), key=lambda i: _ref_distance(train_X[i], x))
    return _vote([train_y[i] for i in order[:k]])


def _ref_accuracy(train_X, train_y, test_X, test_y, k):
    if not test_X or len(test_X) != len(test_y):
        raise ValueError("test set is empty or mismatched")
    hits = sum(_ref_knn(train_X, train_y, x, k) == y for x, y in zip(test_X, test_y))
    return hits / len(test_X)


@spotter
def _distance_spot(got, args, _kwargs):
    a, b = args
    sq = sum((x - y) ** 2 for x, y in zip(a, b))
    if sq not in (0.0, 1.0) and near(got, sq):
        return ("That's the SQUARED distance. Take math.sqrt of the sum.", "")
    if near(got, sum(abs(x - y) for x, y in zip(a, b))) and not near(got, math.sqrt(sq)):
        return ("That's the Manhattan distance (sum of |differences|). This contract is straight-line: "
                "sqrt of the sum of squared differences.", "")
    return None


@spotter
def _knn_spot(got, args, _kwargs):
    train_X, train_y, x, k = args
    expected = _ref_knn(train_X, train_y, x, k)
    order = sorted(range(len(train_X)), key=lambda i: _ref_distance(train_X[i], x))
    nearest = [train_y[i] for i in order[:k]]
    far = [train_y[i] for i in sorted(range(len(train_X)), key=lambda i: -_ref_distance(train_X[i], x))[:k]]
    counts = {lab: nearest.count(lab) for lab in nearest}
    best = max(counts.values())
    tied = sorted(lab for lab in counts if counts[lab] == best)
    if len(tied) > 1 and got in tied and got != expected:
        return (f"The vote tied between {show(tied)} ({best} each). The contract gives a tied vote to the "
                f"label whose member is CLOSEST, which is {show(expected)}.",
                "Walk the neighbours nearest-first and return the first label that has the top count. "
                "collections.Counter(nearest).most_common(1) also does this, because it keeps first-seen order on ties.")
    if k > 1 and got == train_y[order[0]] and got != expected:
        return (f"You returned the single nearest label, ignoring k = {k}. Take a vote among the {k} nearest.", "")
    if got == _vote(far) and got != expected:
        return ("You voted among the FARTHEST points. Sort by distance ascending: nearest first.", "")
    return None


_KNN_MANUAL = """\
**k-nearest-neighbours has no training step.** To label a new point, find the `k` stored
points closest to it and let them vote. It's the oldest trick in machine learning, and the
same idea powers "find similar items" at web scale.

**Distance first.** Straight-line (Euclidean) distance between two points:

```python
math.sqrt(sum((a - b) ** 2 for a, b in zip(p, q)))
```

**Sort indexes by distance.** Sorting the *indexes* keeps each point linked to its label.
Python's sort is **stable**: equal keys keep their original order, so distance ties go to the
earlier training point automatically.

```python
order = sorted(range(len(train_X)), key=lambda i: distance(train_X[i], x))
nearest = [train_y[i] for i in order[:k]]       # labels, nearest first
```

**Count the votes, break ties by closeness.** If two labels get the same number of votes,
pick the one whose member came first in `nearest` (it was closer):

```python
counts = {}
for label in nearest:
    counts[label] = counts.get(label, 0) + 1
best = max(counts.values())
for label in nearest:              # nearest-first, so the first match is the closest
    if counts[label] == best:
        return label
```

**Accuracy** is the fraction of test points whose prediction matches the true label.
"""


def _build_knn(rng):
    labels = ["ally", "drone", "hostile"]
    rng.shuffle(labels)
    centres = [(rng.uniform(-6, -2), rng.uniform(-6, -2)), (rng.uniform(2, 6), rng.uniform(-2, 2)),
               (rng.uniform(-2, 2), rng.uniform(3, 7))]
    train_X, train_y = [], []
    for _ in range(rng.randint(14, 18)):
        c = rng.randrange(3)
        cx, cy = centres[c]
        train_X.append([round(cx + rng.gauss(0, 1.3), 1), round(cy + rng.gauss(0, 1.3), 1)])
        train_y.append(labels[c])
    dist_cases = [([num(rng, -5, 5, 1) for _ in range(2)], [num(rng, -5, 5, 1) for _ in range(2)]),
                  ([num(rng, -5, 5, 1) for _ in range(4)], [num(rng, -5, 5, 1) for _ in range(4)]),
                  ([3.0, 4.0], [0.0, 0.0]), ([num(rng, -9, 9)], [num(rng, -9, 9)]), ([1.5, -2.0], [1.5, -2.0])]
    queries = [[round(cx + rng.uniform(-1, 1), 1), round(cy + rng.uniform(-1, 1), 1)] for cx, cy in centres]
    queries.append([round(rng.uniform(-3, 3), 1), round(rng.uniform(-3, 3), 1)])
    knn_cases = [(train_X, train_y, q, k) for q, k in zip(queries, (3, 5, 1, 5))]

    # exact ties (integer coordinates): two points mirror each other around the query
    qx, qy = rng.randint(-3, 3), rng.randint(-3, 3)
    dx, dy = rng.randint(1, 3), rng.randint(1, 3)
    near_a, near_b = rng.sample(labels, 2)
    tie_X = [[float(qx + dx + 4), float(qy + dy + 4)],        # far point
             [float(qx + dx), float(qy + dy)],                # tied with the next one, earlier index
             [float(qx - dx), float(qy - dy)],
             [float(qx + 6), float(qy - 6)]]
    tie_y = [near_b, near_a, near_b, near_b]
    # split vote: k = 2 with two different labels -> the closer one wins
    split_X = [[float(qx + 1), float(qy)], [float(qx + 3), float(qy)], [float(qx - 5), float(qy)]]
    split_y = [near_b, near_a, near_a]
    # 2-2 split with k = 4: the label of the nearest of the four wins
    four_X = [[float(qx), float(qy + 4)], [float(qx + 1), float(qy)], [float(qx + 2), float(qy)],
              [float(qx + 3), float(qy)], [float(qx - 3.5), float(qy)]]
    four_y = [near_a, near_b, near_a, near_a, near_b]
    q = [float(qx), float(qy)]
    tie_cases = [(tie_X, tie_y, q, 1), (split_X, split_y, q, 2), (four_X, four_y, q, 4)]

    test_X = [[round(cx + rng.gauss(0, 1.6), 1), round(cy + rng.gauss(0, 1.6), 1)] for cx, cy in centres * 2]
    test_y = [labels[i % 3] for i in range(6)]
    acc_cases = [(train_X, train_y, test_X, test_y, 3), (train_X, train_y, test_X[:2], test_y[:2], 1)]

    sample_q = queries[0]
    prompt = f"""\
Something is moving in the Core's outer ring: signatures the Monastery can't name. You have a
log of {len(train_X)} contacts, each tagged ally, drone or hostile by a scout who didn't come back.
New contacts are inbound. Label each one by the company it keeps.

**Write three functions:**

- `distance(a, b)`: straight-line distance, `sqrt(sum((a[i] - b[i]) ** 2))`. `ValueError` if the
  dimensions differ.
- `knn_predict(train_X, train_y, x, k)`: the majority label among the `k` training points
  nearest to `x`. Exact rules:
  - training points at equal distance keep their training order (earlier index first);
  - if the vote ties, the tied label whose member is **nearest** to `x` wins;
  - raise `ValueError` unless `1 <= k <= len(train_X)`, or if `train_X` and `train_y` differ in length.
- `accuracy(train_X, train_y, test_X, test_y, k)`: the fraction of test points that
  `knn_predict` labels correctly, as a float. `ValueError` if the test set is empty or mismatched.

**Inbound contact (this contract):**

```python
knn_predict(train_X, train_y, {show(sample_q)}, 3)   # -> {show(_ref_knn(train_X, train_y, sample_q, 3))}
```
"""
    starter = '''
import math


def distance(a, b):
    """Straight-line distance between two points. ValueError if dimensions differ."""
    # your code
    pass


def knn_predict(train_X, train_y, x, k):
    """Majority label of the k nearest training points; tied votes go to the nearest label."""
    # your code
    pass


def accuracy(train_X, train_y, test_X, test_y, k):
    """Fraction of test points knn_predict gets right."""
    # your code
    pass


if __name__ == "__main__":
    X = [[0.0, 0.0], [1.0, 0.0], [5.0, 5.0], [6.0, 5.0]]
    y = ["ally", "ally", "hostile", "hostile"]
    print(distance([0.0, 0.0], [3.0, 4.0]))             # 5.0
    print(knn_predict(X, y, [0.5, 0.5], 3))             # ally
    print(accuracy(X, y, [[5.5, 5.0], [0.0, 1.0]], ["hostile", "ally"], 1))   # 1.0
'''
    mission = build(
        title="NEAREST NEIGHBOURS", enemy="UNKNOWN.contact", prompt=prompt, manual=_KNN_MANUAL, starter=starter,
        concepts=("ml-math", "algorithms", "sorting"),
        intro=[line("vex", "Contacts inbound and you're still sorting lists? I'd have tagged them by now, {callsign}.", "smirk"),
               line("cipher", "No model, no training. Just distance and a fair vote. Be exact about the ties.", "neutral")],
        victory=[line("vex", "Every contact tagged, ties and all. Fine. That was clean. Don't tell anyone I said so.", "smirk")],
    )

    @mission.check("distance — straight-line gap")
    def _distance_layer(ctx):
        expect(ctx, "distance", dist_cases, _ref_distance, spot=_distance_spot, pure=True,
               hint="math.sqrt(sum((p - q) ** 2 for p, q in zip(a, b)))")
        expect_raises(ctx, "distance", ([1.0, 2.0], [1.0, 2.0, 3.0]), why="a 2-D point and a 3-D point",
                      hint="Compare len(a) and len(b) before zipping.")

    @mission.check("knn_predict — majority of the k nearest")
    def _knn_layer(ctx):
        expect(ctx, "knn_predict", knn_cases, _ref_knn, spot=_knn_spot, approx=False, pure=True,
               hint="Sort the training indexes by distance to x, take the first k labels, count the votes.")

    @mission.check("tie-breaks — equal distances and split votes")
    def _tie_layer(ctx):
        expect(ctx, "knn_predict", tie_cases, _ref_knn, spot=_knn_spot, approx=False,
               hint="Sort indexes with sorted(..., key=distance): it's stable, so equal distances keep training order. "
                    "On a split vote, the first tied label in nearest-first order wins.")

    @mission.check("guards & accuracy")
    def _acc_layer(ctx):
        for bad_k in (0, len(train_X) + 1):
            expect_raises(ctx, "knn_predict", (train_X, train_y, queries[0], bad_k),
                          why=f"k = {bad_k} is outside 1..{len(train_X)}",
                          hint="Check  1 <= k <= len(train_X)  at the top and raise ValueError otherwise.")
        expect_raises(ctx, "knn_predict", (train_X, train_y[:-1], queries[0], 3),
                      why="one training point has no label")
        expect(ctx, "accuracy", acc_cases, _ref_accuracy,
               hint="Count the test points where knn_predict(...) == the true label, then divide by len(test_X).")
        expect_raises(ctx, "accuracy", (train_X, train_y, [], [], 3), why="an empty test set has no accuracy")

    return mission


register(Drill("t5-knn-classify", "NEAREST NEIGHBOURS", 5, ("ml-math", "algorithms", "sorting"), 1200, _build_knn))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-kmeans-step — SWARM CENTROIDS
# ══════════════════════════════════════════════════════════════════════════════════════

def _sq(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _ref_assign(points, centroids, *, ties_high=False):
    labels = []
    for p in points:
        best, best_d = 0, _sq(p, centroids[0])
        for j in range(1, len(centroids)):
            d = _sq(p, centroids[j])
            if d < best_d or (ties_high and d == best_d):
                best, best_d = j, d
        labels.append(best)
    return labels


def _ref_update(points, labels, centroids):
    if len(points) != len(labels):
        raise ValueError("one label per point")
    new = []
    for j, c in enumerate(centroids):
        members = [p for p, lab in zip(points, labels) if lab == j]
        if not members:
            new.append(list(c))
            continue
        new.append([sum(col) / len(members) for col in zip(*members)])
    return new


def _ref_kmeans(points, centroids, max_iters=100):
    centroids = [list(c) for c in centroids]
    for _ in range(max_iters):
        labels = _ref_assign(points, centroids)
        new = _ref_update(points, labels, centroids)
        if new == centroids:
            break
        centroids = new
    return (_ref_assign(points, centroids), centroids)


def _iterations(points, centroids):
    centroids = [list(c) for c in centroids]
    for n in range(1, 100):
        new = _ref_update(points, _ref_assign(points, centroids), centroids)
        if new == centroids:
            return n
        centroids = new
    return 100


@spotter
def _assign_spot(got, args, _kwargs):
    points, centroids = args
    if near(got, _ref_assign(points, centroids, ties_high=True)):
        return ("A point sits exactly between two centroids, and you gave it to the LATER one. Ties go to the "
                "lowest index.", "Only switch to centroid j if it is strictly closer: d < best_d.")
    if isinstance(got, list) and got and isinstance(got[0], list):
        return ("You returned centroids. assign() returns one INDEX per point (0, 1, 2…).", "")
    return None


@spotter
def _update_spot(got, args, _kwargs):
    points, labels, centroids = args
    if isinstance(got, list) and len(got) < len(centroids):
        return ("A centroid disappeared. A cluster with no points keeps its old centroid, so the count never "
                "changes.", "if not members: new.append(list(old_centroid))")
    return None


@spotter
def _kmeans_spot(got, args, kwargs):
    points, centroids = args[0], args[1]
    max_iters = kwargs.get("max_iters", args[2] if len(args) > 2 else 100)
    one = _ref_update(points, _ref_assign(points, centroids), centroids)
    if max_iters > 1 and near(got, (_ref_assign(points, one), one)):
        return ("You stopped after a single update. Keep repeating assign + update until the centroids stop "
                "moving.", "")
    if max_iters < 100 and near(got, _ref_kmeans(points, centroids)):
        return (f"You ran to convergence and ignored max_iters = {max_iters}. It's a hard cap on the number of "
                "updates.", "for _ in range(max_iters): ...  then return.")
    return None


_KMEANS_MANUAL = """\
**k-means finds groups nobody labelled.** Start with `k` guesses for the group centres
(centroids), then repeat two steps:

**1 · Assign.** Each point joins its nearest centroid. Comparing *squared* distances is enough
(the square root never changes which one is smallest) and keeps the arithmetic exact:

```python
d = sum((p - c) ** 2 for p, c in zip(point, centroid))
```

On an exact tie, keep the lower index: only switch when the new centroid is *strictly* closer.

**2 · Update.** Move each centroid to the mean of the points assigned to it, one coordinate at
a time. `zip(*members)` gives you the columns:

```python
members = [[1.0, 2.0], [3.0, 4.0]]
[sum(col) / len(members) for col in zip(*members)]     # [2.0, 3.0]
```

A centroid that attracted no points can't be averaged (that's a division by zero). Keep it
where it was.

**3 · Repeat until nothing moves.** When an update returns exactly the same centroids, the
assignments can't change either: it has converged. Real code also caps the number of rounds
(`max_iters`) so a pathological input can't loop forever.
"""


def _build_kmeans(rng):
    while True:
        centres = [(rng.uniform(-8, -3), rng.uniform(-8, -3)), (rng.uniform(3, 8), rng.uniform(-6, 0)),
                   (rng.uniform(-2, 3), rng.uniform(4, 9))]
        points = [[round(cx + rng.gauss(0, 1.4), 1), round(cy + rng.gauss(0, 1.4), 1)]
                  for cx, cy in centres for _ in range(rng.randint(4, 6))]
        rng.shuffle(points)
        start = [list(p) for p in points[:3]]          # Forgy start: three of the points themselves
        if _iterations(points, start) >= 3 and len({tuple(p) for p in start}) == 3:
            break
    far_start = start[:2] + [[40.0, 40.0]]                   # attracts nobody: an empty cluster
    labels0 = _ref_assign(points, start)
    tie_pts = [[0.0, 0.0], [2.0, 0.0], [1.0, 3.0]]
    tie_cent = [[1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]]         # (0,0) is equidistant from all three
    assign_cases = [(points, start), (points[:5], far_start), (tie_pts, tie_cent), ([], start)]
    update_cases = [(points, labels0, start),
                    (points, _ref_assign(points, far_start), far_start),
                    ([[1.0, 1.0], [3.0, 5.0]], [0, 0], [[0.0, 0.0], [9.0, 9.0]])]
    kmeans_cases = [(points, start), (points, start, 1), (points, far_start), (points[:6], points[:2])]

    shown_pts = points[:4]
    prompt = f"""\
A drone swarm has broken formation in the Core's shadow, {len(points)} contacts scattered across
the scope. They aren't random: they're regrouping around hives you can't see. Find the hives.
No labels, no training data. Just the points, and the patience to let them settle.

**Write three functions** (points and centroids are lists of `[x, y]` lists):

- `assign(points, centroids)`: for each point, the **index** of its nearest centroid (smallest
  squared distance). On an exact tie, the lowest index wins.
- `update(points, labels, centroids)`: new centroids, as new lists. Centroid `j` moves to the
  mean of the points labelled `j`; a centroid with **no** points keeps its old position.
  `ValueError` if `points` and `labels` differ in length.
- `kmeans(points, centroids, max_iters=100)`: repeat at most `max_iters` times: `assign`, then
  `update`; stop early as soon as an update leaves every centroid unchanged. Return
  `(labels, centroids)` with `labels = assign(points, final_centroids)`.

None of them may change the lists they're given.

**Scope readout (this contract):** the swarm starts with
`centroids = {show(start)}`; the first four contacts are `{show(shown_pts)}`.
"""
    starter = '''
def assign(points, centroids):
    """Index of the nearest centroid for each point (squared distance; ties -> lowest index)."""
    # your code
    pass


def update(points, labels, centroids):
    """Each centroid moves to the mean of its points; an empty cluster keeps its centroid."""
    # your code
    pass


def kmeans(points, centroids, max_iters=100):
    """assign + update until the centroids stop moving (or max_iters). Return (labels, centroids)."""
    # your code
    pass


if __name__ == "__main__":
    pts = [[0.0, 0.0], [0.0, 1.0], [9.0, 9.0], [10.0, 9.0]]
    start = [[0.0, 0.0], [0.0, 1.0]]
    labels = assign(pts, start)
    print(labels)                          # [0, 1, 1, 1]
    print(update(pts, labels, start))      # [[0.0, 0.0], [6.33.., 6.33..]]
    print(kmeans(pts, start))              # ([0, 0, 1, 1], [[0.0, 0.5], [9.5, 9.0]])
'''
    mission = build(
        title="SWARM CENTROIDS", enemy="HIVE.swarm", prompt=prompt, manual=_KMEANS_MANUAL, starter=starter,
        concepts=("ml-math", "algorithms", "lists"),
        intro=[line("rust", "Swarm's out there regrouping. Find the hives and I'll sell the coordinates. Fifty-fifty.", "neutral"),
               line("cipher", "Assign, update, repeat. Watch the empty clusters: they're where most k-means code dies.", "neutral")],
        victory=[line("rust", "Three hives, pinned. Coordinates are already on the market. Your cut's in your account. Probably.", "smirk"),
                 line("cipher", "It converged without a single label. The Core learned to see us the same way.", "neutral")],
    )

    @mission.check("assign — each contact to its nearest hive")
    def _assign_layer(ctx):
        expect(ctx, "assign", assign_cases, _ref_assign, spot=_assign_spot, approx=False, pure=True,
               hint="For each point, compute the squared distance to every centroid and keep the index of the smallest.")

    @mission.check("update — move each hive to its swarm's centre")
    def _update_layer(ctx):
        expect(ctx, "update", update_cases, _ref_update, spot=_update_spot, pure=True,
               errors=_zero_div("A cluster with no points has no mean.",
                                "If a centroid has no members, append a copy of the old centroid instead."),
               hint="For centroid j: members = the points labelled j; mean of each coordinate (zip(*members)).")
        expect_raises(ctx, "update", (points[:3], [0, 1], start), why="3 points but only 2 labels")

    @mission.check("kmeans — iterate to convergence (and respect max_iters)")
    def _kmeans_layer(ctx):
        expect(ctx, "kmeans", kmeans_cases, _ref_kmeans, spot=_kmeans_spot, pure=True,
               hint="Loop up to max_iters times: labels = assign(...); new = update(...); if new == centroids: break; "
                    "centroids = new. Then return (assign(points, centroids), centroids).")

    return mission


register(Drill("t5-kmeans-step", "SWARM CENTROIDS", 5, ("ml-math", "algorithms", "lists"), 1200, _build_kmeans))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-split-seed — CLEAN SPLIT
# ══════════════════════════════════════════════════════════════════════════════════════

def _ref_split(X, y, test_ratio, seed):
    if len(X) != len(y):
        raise ValueError("X and y differ in length")
    if not 0 < test_ratio < 1:
        raise ValueError("test_ratio must be between 0 and 1")
    n = len(X)
    n_test = round(n * test_ratio)
    if n_test == 0 or n_test == n:
        raise ValueError("one side of the split would be empty")
    order = list(range(n))
    random.Random(seed).shuffle(order)
    test_idx, train_idx = order[:n_test], order[n_test:]
    return ([X[i] for i in train_idx], [X[i] for i in test_idx],
            [y[i] for i in train_idx], [y[i] for i in test_idx])


def _ref_kfold(n, k):
    if not 2 <= k <= n:
        raise ValueError("k must be between 2 and n")
    folds, start = [], 0
    for f in range(k):
        size = n // k + (1 if f < n % k else 0)
        val = list(range(start, start + size))
        train = [i for i in range(n) if not start <= i < start + size]
        folds.append((train, val))
        start += size
    return folds


@spotter
def _split_spot(got, args, _kwargs):
    X, y, test_ratio, seed = args
    expected = _ref_split(X, y, test_ratio, seed)
    if not (isinstance(got, tuple) and len(got) == 4):
        return ("The contract is a 4-tuple: (X_train, X_test, y_train, y_test).", "return X_train, X_test, y_train, y_test")
    if near(got, (expected[1], expected[0], expected[3], expected[2])):
        return ("Train and test are swapped. The FIRST round(n * test_ratio) shuffled indexes are the test set.", "")
    pairs = {(tuple(x), lab) for x, lab in zip(X, y)}
    xs, labs = got[0] + got[1], got[2] + got[3]
    if len(xs) == len(labs) and any((tuple(x), lab) not in pairs for x, lab in zip(xs, labs)):
        return ("Some rows ended up with the wrong labels: X and y were shuffled separately. Shuffle ONE list of "
                "indexes and use it for both.", "")
    n_test = round(len(X) * test_ratio)
    if len(got[1]) == len(X) - n_test:
        return (f"Your test set has {len(got[1])} rows; test_ratio = {test_ratio} of {len(X)} rows is "
                f"{n_test}. test_ratio sizes the TEST side.", "")
    if len(got[1]) != n_test:
        return (f"Your test set has {len(got[1])} rows; it should have round({len(X)} * {test_ratio}) = {n_test}.", "")
    return ("Right sizes, wrong rows: your shuffle isn't the one in the contract.",
            "order = list(range(len(X))); random.Random(seed).shuffle(order). The first n_test indexes are the test set.")


@spotter
def _kfold_spot(got, args, _kwargs):
    n, k = args
    if isinstance(got, list) and len(got) == k and all(isinstance(f, tuple) and len(f) == 2 for f in got):
        sizes = [len(f[1]) for f in got]
        want = [len(f[1]) for f in _ref_kfold(n, k)]
        if sizes != want:
            return (f"Your validation folds have sizes {sizes}; they should be {want}. The first n % k folds get "
                    "one extra row.", "size = n // k + (1 if fold < n % k else 0)")
        if near(got, [(v, t) for t, v in _ref_kfold(n, k)]):
            return ("Each pair is (validation, train); the contract is (train, validation).", "")
    return None


_SPLIT_MANUAL = """\
**Never grade a model on data it trained on.** It would score itself on answers it memorised.
So you hold some rows back as a *test* set. Two rules make that split trustworthy:

**1 · Shuffle first, with a seed.** Datasets are often sorted (by date, by class), so the last
20% isn't a fair sample. Shuffle, but reproducibly: the same seed must give the same split
tomorrow, or no experiment can be repeated.

```python
order = list(range(len(X)))
random.Random(seed).shuffle(order)   # a private generator, seeded
```

**Use a private `random.Random(seed)`, never `random.seed()`.** The module-level generator is
shared by every library in the process; reseeding it quietly changes everyone else's "random"
numbers too.

**2 · Shuffle indexes, not the data.** One shuffled list of indexes picks rows from `X` *and*
`y`, so each row keeps its label:

```python
X_test = [X[i] for i in order[:n_test]]
y_test = [y[i] for i in order[:n_test]]
```

**k-fold cross-validation** uses every row for validation exactly once. Cut `range(n)` into `k`
consecutive folds; when `n` doesn't divide evenly, the first `n % k` folds get one extra row.
Fold `f` validates on its own indexes and trains on all the others.
"""


def _ratio_case(rng):
    while True:
        n = rng.randint(10, 20)
        ratio = rng.choice([0.2, 0.25, 0.3, 0.4])
        frac = (n * ratio) % 1
        if abs(frac - 0.5) > 0.05:
            return n, ratio


def _build_split(rng):
    def dataset(n):
        X = [[round(rng.uniform(0, 10), 1), round(rng.uniform(0, 10), 1)] for _ in range(n)]
        y = [f"s{i:02d}-{rng.choice(['ok', 'rogue'])}" for i in range(n)]
        return X, y

    split_cases = []
    for _ in range(3):
        n, ratio = _ratio_case(rng)
        X, y = dataset(n)
        split_cases.append((X, y, ratio, rng.randint(0, 9999)))
    n, ratio = _ratio_case(rng)
    X_main, y_main = dataset(n)
    seed_main = rng.randint(0, 9999)
    kfold_cases = [(rng.randint(10, 14), 3), (rng.choice([6, 8]), 2), (7, 7), (rng.randint(11, 13), 5)]

    sample = _ref_split(X_main, y_main, ratio, seed_main)
    prompt = f"""\
The Monastery is about to train its first model on the evidence from the Archive: who the Core
deleted, and why. Before anyone trains anything, the Order wants an honest exam: a test set the
model never sees, cut the same way every time so every result can be checked by someone else.

**Write two functions:**

- `train_test_split(X, y, test_ratio, seed)` returns `(X_train, X_test, y_train, y_test)`:
  1. `order = list(range(len(X)))`, shuffled with `random.Random(seed).shuffle(order)`;
  2. `n_test = round(len(X) * test_ratio)`;
  3. the first `n_test` indexes of `order` are the test rows, the rest are training rows, both
     in shuffled order. Rows keep their labels.
  - Raise `ValueError` if `len(X) != len(y)`, if `test_ratio` isn't strictly between 0 and 1,
    or if either side would be empty.
  - Don't change `X` or `y`, and don't touch the global `random` generator.
- `k_fold(n, k)` returns a list of `k` tuples `(train_idx, val_idx)` over `range(n)`, no
  shuffling: fold `f`'s validation indexes are the `f`-th consecutive block (the first `n % k`
  blocks have one extra index); its training indexes are all the others, ascending. Raise
  `ValueError` unless `2 <= k <= n`.

**The Order's split (this contract):** with `{len(X_main)}` rows, `test_ratio={ratio}`,
`seed={seed_main}`, the test labels come out as `{show(sample[3], 300)}`.
"""
    starter = '''
import random


def train_test_split(X, y, test_ratio, seed):
    """Seeded shuffle of the row indexes; the first round(n * test_ratio) are the test set.

    Return (X_train, X_test, y_train, y_test).
    """
    # your code
    pass


def k_fold(n, k):
    """k consecutive validation folds over range(n): a list of (train_idx, val_idx) tuples."""
    # your code
    pass


if __name__ == "__main__":
    X = [[float(i), float(i * i)] for i in range(10)]
    y = [f"row{i}" for i in range(10)]
    X_train, X_test, y_train, y_test = train_test_split(X, y, 0.3, seed=42)
    print(y_test)                  # 3 labels, the same ones on every run
    print(k_fold(5, 2))            # [([3, 4], [0, 1, 2]), ([0, 1, 2], [3, 4])]
'''
    mission = build(
        title="CLEAN SPLIT", enemy="LEAK.vector", prompt=prompt, manual=_SPLIT_MANUAL, starter=starter,
        concepts=("ml-math", "lists", "algorithms"),
        intro=[line("cipher", "A model that's seen its exam is a liar. Cut the test set clean, and cut it the same way every time.", "neutral"),
               line("nova", "Order's evaluation board wants reproducible splits by end of shift. Seeds on everything, {callsign}!", "warm")],
        victory=[line("cipher", "Same seed, same split, every row with its own label. Now the results can be checked by anyone.", "warm")],
    )

    @mission.check("train_test_split — the seeded shuffle")
    def _split_layer(ctx):
        expect(ctx, "train_test_split", split_cases, _ref_split, spot=_split_spot,
               hint="order = list(range(len(X))); random.Random(seed).shuffle(order); n_test = round(len(X) * test_ratio).")

    @mission.check("integrity — labels attached, inputs untouched, global RNG untouched")
    def _integrity_layer(ctx):
        fn = function(ctx, "train_test_split")
        args = (X_main, y_main, ratio, seed_main)
        shown = call_text("train_test_split", args)
        given = copy.deepcopy(args)
        state = random.getstate()
        first = invoke(fn, shown, given)
        reseeded = random.getstate() != state
        random.setstate(state)
        if reseeded:
            raise Fail(f"`{shown}` changed the GLOBAL random generator (random.seed or random.shuffle). Every "
                       "library in the process shares that one.",
                       hint="Make a private one: rng = random.Random(seed); rng.shuffle(order).")
        if given != args:
            raise Fail(f"`{shown}` shuffled the caller's lists in place. Their data is now in a different order.",
                       hint="Shuffle a fresh list of indexes and build new lists from it.")
        again = invoke(fn, shown, copy.deepcopy(args))
        if not near(first, again):
            raise Fail(f"Calling `{shown}` twice gave two different splits. Same seed must mean same split.",
                       hint="Seed a private random.Random(seed) inside the function, every call.")
        expect(ctx, "train_test_split", [args], _ref_split, spot=_split_spot)

    @mission.check("guards — reject impossible splits")
    def _guard_layer(ctx):
        X, y = X_main[:6], y_main[:6]
        expect_raises(ctx, "train_test_split", (X, y[:5], 0.3, 1), why="6 rows but 5 labels")
        for bad, why in ((0.0, "a test_ratio of 0 holds nothing back"), (1.0, "a test_ratio of 1 leaves nothing to train on"),
                         (1.5, "a ratio above 1 is meaningless")):
            expect_raises(ctx, "train_test_split", (X, y, bad, 1), why=why,
                          hint="Check  0 < test_ratio < 1  at the top.")
        expect_raises(ctx, "train_test_split", (X[:3], y[:3], 0.1, 1), why="round(3 * 0.1) = 0 test rows",
                      hint="After computing n_test, reject 0 and len(X): one side of the split would be empty.")

    @mission.check("k_fold — every row validates exactly once")
    def _kfold_layer(ctx):
        expect(ctx, "k_fold", kfold_cases, _ref_kfold, spot=_kfold_spot, approx=False,
               hint="Walk a start index forward; each fold's size is n // k, plus 1 for the first n % k folds.")
        expect_raises(ctx, "k_fold", (5, 1), why="one fold leaves nothing to train on")
        expect_raises(ctx, "k_fold", (3, 4), why="4 folds can't be cut from 3 rows")

    return mission


register(Drill("t5-split-seed", "CLEAN SPLIT", 5, ("ml-math", "lists", "algorithms"), 1000, _build_split))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t5-confusion-metrics — TRIBUNAL AUDIT
# ══════════════════════════════════════════════════════════════════════════════════════

def _ref_confusion(y_true, y_pred, labels):
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred differ in length")
    index = {label: i for i, label in enumerate(labels)}
    matrix = [[0] * len(labels) for _ in labels]
    for t, p in zip(y_true, y_pred):
        if t not in index or p not in index:
            raise ValueError("unknown label")
        matrix[index[t]][index[p]] += 1
    return matrix


def _counts(y_true, y_pred, positive):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == positive and p == positive)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != positive and p == positive)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == positive and p != positive)
    return tp, fp, fn


def _ref_metrics(y_true, y_pred, positive):
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred differ in length")
    tp, fp, fn = _counts(y_true, y_pred, positive)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return (precision, recall, f1)


def _ref_macro(y_true, y_pred, labels):
    if not labels:
        raise ValueError("no labels")
    return sum(_ref_metrics(y_true, y_pred, label)[2] for label in labels) / len(labels)


@spotter
def _confusion_spot(got, args, _kwargs):
    y_true, y_pred, labels = args
    if near(got, [list(col) for col in zip(*_ref_confusion(y_true, y_pred, labels))]):
        return ("Rows and columns are swapped. Rows are the TRUE label, columns the PREDICTED one: "
                "matrix[true][pred].", "")
    return None


@spotter
def _metrics_spot(got, args, _kwargs):
    p, rc, f1 = _ref_metrics(*args)
    if not (isinstance(got, tuple) and len(got) == 3):
        return ("The contract is a tuple of three floats: (precision, recall, f1).", "return precision, recall, f1")
    if p != rc and near(got[:2], (rc, p)):
        return ("Precision and recall are swapped. Precision = tp / (tp + fp): of everything you FLAGGED, how much "
                "was right. Recall = tp / (tp + fn): of everything REAL, how much you caught.", "")
    if near(got[:2], (p, rc)) and near(got[2], (p + rc) / 2):
        return ("Your F1 is the plain average of precision and recall. F1 is their HARMONIC mean: "
                "2 * p * r / (p + r).", "It punishes a lopsided classifier; the plain average doesn't.")
    return None


@spotter
def _macro_spot(got, args, _kwargs):
    y_true, y_pred, labels = args
    acc = sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)
    if near(got, acc) and not near(got, _ref_macro(*args)):
        return ("That's accuracy (the micro average). Macro-F1 computes F1 for EACH label, then averages "
                "those, so a rare class counts as much as a common one.", "")
    support = {lab: y_true.count(lab) for lab in labels}
    weighted = sum(_ref_metrics(y_true, y_pred, lab)[2] * support[lab] for lab in labels) / len(y_true)
    if near(got, weighted):
        return ("You weighted each label's F1 by how often it occurs. Macro-F1 is a plain average over the labels.", "")
    return None


_METRICS_MANUAL = """\
**Accuracy hides who you fail.** If 90% of contacts are civilians, a model that calls everyone
a civilian is 90% accurate and catches zero rogues. So we score each class separately.

**The confusion matrix** counts every (true, predicted) pair. Row = what it really was,
column = what the model said. The diagonal is the hits:

```python
index = {label: i for i, label in enumerate(labels)}
matrix[index[true]][index[pred]] += 1
```

**One class at a time** ("positive" = the class you're scoring):

* `tp` true positives: really positive, predicted positive
* `fp` false positives: predicted positive, but it wasn't
* `fn` false negatives: really positive, but missed

```python
precision = tp / (tp + fp)   # of everything I flagged, how much was right?
recall    = tp / (tp + fn)   # of everything real, how much did I catch?
f1 = 2 * precision * recall / (precision + recall)   # harmonic mean
```

**Zero denominators are normal.** A class the model never predicts has `tp + fp == 0`. The
convention (scikit-learn's too) is to report `0.0` instead of crashing.

**Macro-F1** averages the per-class F1 scores, so a rare class counts as much as a common one.
"""


def _build_metrics(rng):
    labels = ["civilian", "drone", "rogue"]
    weights = [0.55, 0.3, 0.15]

    def predictions(n, skill):
        y_true = rng.choices(labels, weights=weights, k=n)
        y_pred = [t if rng.random() < skill else rng.choice(labels) for t in y_true]
        return y_true, y_pred

    y_true, y_pred = predictions(rng.randint(18, 24), 0.7)
    t2, p2 = predictions(rng.randint(10, 14), 0.5)
    order2 = labels[:]
    rng.shuffle(order2)
    conf_cases = [(y_true, y_pred, labels), (t2, p2, order2), ([], [], labels)]
    metric_cases = [(y_true, y_pred, lab) for lab in labels] + [(t2, p2, rng.choice(labels))]
    # zero-division cases: a class nobody predicted, a class that never occurs, and a ghost label
    missed = rng.choice(labels)
    t3 = [missed, missed] + [lab for lab in rng.choices(labels, k=6) if lab != missed]
    p3 = [lab if lab != missed else rng.choice([x for x in labels if x != missed]) for lab in t3]
    unseen = rng.choice(labels)
    t4 = [rng.choice([x for x in labels if x != unseen]) for _ in range(6)]
    p4 = t4[:-1] + [unseen]
    zero_cases = [(t3, p3, missed), (t4, p4, unseen), (y_true, y_pred, "ghost")]
    macro_cases = [(y_true, y_pred, labels), (t2, p2, labels), (t3, p3, labels), (y_true, y_pred, labels + ["ghost"])]

    p, rc, f1 = _ref_metrics(y_true, y_pred, "rogue")
    prompt = f"""\
Before the Arbiter fell, it decided who the Core deleted. Its successor is still running in the
outer ring, flagging contacts as civilian, drone or rogue, and the Order is about to trust it
with the Monastery's gate. Audit it first. Not its accuracy: its mistakes.

**Write three functions** (`y_true` and `y_pred` are equal-length lists of labels):

- `confusion_matrix(y_true, y_pred, labels)`: a list of lists where `matrix[i][j]` counts the
  samples whose true label is `labels[i]` and predicted label is `labels[j]`. Raise
  `ValueError` if the lists differ in length or a label isn't in `labels`.
- `class_metrics(y_true, y_pred, positive)`: a tuple `(precision, recall, f1)` of floats for
  one class. Any metric whose denominator is 0 is `0.0`.
- `macro_f1(y_true, y_pred, labels)`: the mean of `class_metrics(...)[2]` over `labels`.

**Gate classifier log (this contract):** {len(y_true)} contacts. For `"rogue"` the auditors
expect precision ≈ {r(p, 4)}, recall ≈ {r(rc, 4)}, F1 ≈ {r(f1, 4)}.
"""
    starter = '''
def confusion_matrix(y_true, y_pred, labels):
    """matrix[i][j] = how many samples were really labels[i] and predicted labels[j]."""
    # your code
    pass


def class_metrics(y_true, y_pred, positive):
    """(precision, recall, f1) for one class. A zero denominator gives 0.0."""
    # your code
    pass


def macro_f1(y_true, y_pred, labels):
    """Average of the per-label F1 scores."""
    # your code
    pass


if __name__ == "__main__":
    y_true = ["rogue", "civilian", "rogue", "drone", "civilian"]
    y_pred = ["rogue", "rogue", "civilian", "drone", "civilian"]
    labels = ["civilian", "drone", "rogue"]
    print(confusion_matrix(y_true, y_pred, labels))   # [[1, 0, 1], [0, 1, 0], [1, 0, 1]]
    print(class_metrics(y_true, y_pred, "rogue"))     # (0.5, 0.5, 0.5)
    print(macro_f1(y_true, y_pred, labels))           # ≈ 0.6667
'''
    mission = build(
        title="TRIBUNAL AUDIT", enemy="ARBITER.ghost", prompt=prompt, manual=_METRICS_MANUAL, starter=starter,
        concepts=("ml-math", "dicts", "algorithms"),
        intro=[line("cipher", "Accuracy is how the Arbiter justified itself. Look at who it got wrong instead.", "cold"),
               line("vex", "Rogue class is tiny. Bet you a hundred CRED its recall is garbage.", "smirk")],
        victory=[line("cipher", "Per-class numbers, zero-safe, macro-averaged. Now the Order can see exactly who this model fails.", "warm"),
                 line("vex", "Told you the rogue recall was garbage. Keep the CRED. I just like being right.", "smirk")],
    )

    @mission.check("confusion_matrix — who got mistaken for whom")
    def _confusion_layer(ctx):
        expect(ctx, "confusion_matrix", conf_cases, _ref_confusion, spot=_confusion_spot, approx=False, pure=True,
               hint="Map each label to its position with a dict, start from a k x k grid of zeros, add 1 at [true][pred].")
        expect_raises(ctx, "confusion_matrix", (["drone"], ["drone", "rogue"], labels), why="1 truth but 2 predictions")
        expect_raises(ctx, "confusion_matrix", (["drone", "angel"], ["drone", "drone"], labels),
                      why="'angel' isn't one of the labels", hint="Check each label is in your index dict before counting.")

    @mission.check("class_metrics — precision, recall, F1")
    def _metrics_layer(ctx):
        expect(ctx, "class_metrics", metric_cases, _ref_metrics, spot=_metrics_spot,
               hint="Count tp, fp and fn for the positive class, then precision = tp / (tp + fp), recall = tp / (tp + fn).")

    @mission.check("zero division — a class nobody predicted")
    def _zero_layer(ctx):
        expect(ctx, "class_metrics", zero_cases, _ref_metrics, spot=_metrics_spot,
               errors=_zero_div("A denominator was 0: this class was never predicted (tp + fp = 0) or never occurs (tp + fn = 0).",
                                "Return 0.0 for any metric whose denominator is 0. F1 too, when precision + recall is 0."),
               hint="precision = tp / (tp + fp) if tp + fp else 0.0, and the same pattern for recall and F1.")

    @mission.check("macro_f1 — every class counts the same")
    def _macro_layer(ctx):
        expect(ctx, "macro_f1", macro_cases, _ref_macro, spot=_macro_spot,
               errors=_zero_div("A denominator was 0 inside your F1.", "Reuse class_metrics: it already handles 0."),
               hint="sum(class_metrics(y_true, y_pred, lab)[2] for lab in labels) / len(labels)")

    return mission


register(Drill("t5-confusion-metrics", "TRIBUNAL AUDIT", 5, ("ml-math", "dicts", "algorithms"), 1200, _build_metrics))
