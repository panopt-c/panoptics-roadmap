"""LAB ML04 // THE JUDGE'S LEDGER — confusion matrix, precision, recall, F1 (and the zero-division rules)."""
from __future__ import annotations

from engine.mission import Fail, Mission
from lab.ml01_the_line import _call, _fn, _numpy, _scalar, _sealed, _show

try:
    import numpy as np
except ImportError:  # the Lab shows `pip install numpy`; the briefing must still load without it
    np = None

MISSION = Mission(
    id="ML04",
    slug="ml04_judges_ledger",
    title="THE JUDGE'S LEDGER",
    concept="Confusion matrix, precision, recall, F1",
    enemy="ACCURACY.cult",
    xp=260,
    par_seconds=35 * 60,
    tier=4,
    concepts=("numpy", "evaluation", "statistics"),
    requires=("numpy",),
    timeout=12,
    run_as_main=False,
    enemy_art="""\
     ╔══════╗
     ║ 97 % ║
   ▄▄╚══╤═══╝▄▄
  █  ▀▀▀█▀▀▀  █
  █ ▓▓  █  ▓▓ █
   ▀▀▀▀▀▀▀▀▀▀▀""",
    briefing="""\
The perimeter alarm has a plaque: **97% ACCURATE**. **ACCURACY.cult** etched it there and sings
it every night. Raiders come on three nights in a hundred. The alarm has never fired. Not once.
That's how it got its 97.

Ada lays the fourth page of the canon on the floor: a two-by-two grid, its corners labelled in
faded ink. "The old world loved one number," she says. "One number can't tell you *which* way a
judge is wrong. Four can."

**Build the judge's ledger: a confusion matrix, then precision, recall and F1, with zero-division
handled the way the real libraries handle it.**
""",
    why="""\
Accuracy lies whenever classes are imbalanced, and in real ML they almost always are: fraud is
0.1% of transactions, a disease 2% of scans, a bad deploy one in a hundred. Every classification
report you'll ever read is built from the confusion matrix:

```python
from sklearn.metrics import confusion_matrix, classification_report
print(confusion_matrix(y_test, y_pred))          # rows = truth, columns = prediction
print(classification_report(y_test, y_pred))     # precision / recall / F1 per class
```

**Precision** answers "when it fires, is it right?" (spam filters, ban systems). **Recall**
answers "of the real cases, how many did it catch?" (cancer screens, intrusion alarms). **F1**
balances them; **macro F1** gives each class an equal vote, so a rare class can't be ignored.
Picking which to optimize is a product decision you'll make on every project.
""",
    manual="""\
**1. The confusion matrix.** Count every (truth, prediction) pair. Row = what it really was,
column = what the judge said. That is scikit-learn's convention, and the ledger's.

```python
import numpy as np
y_true = np.array([0, 1, 1, 0, 1])
y_pred = np.array([0, 1, 0, 0, 1])
cm = np.zeros((2, 2), dtype=int)
for t, p in zip(y_true, y_pred):
    cm[t, p] += 1
cm        # [[2, 0],      2 true 0s said 0,  0 true 0s said 1 (false positive)
          #  [1, 2]]      1 true 1 said 0 (false negative), 2 true 1s said 1
```

The loop is fine to start with. The vectorized version is one line:
`np.add.at(cm, (y_true, y_pred), 1)`.

**2. The four counts for one positive class.**

```python
tp = np.sum((y_pred == pos) & (y_true == pos))   # fired, and it was real
fp = np.sum((y_pred == pos) & (y_true != pos))   # fired, false alarm
fn = np.sum((y_pred != pos) & (y_true == pos))   # stayed quiet, missed it
precision = tp / (tp + fp)       # of the alarms, how many were real
recall    = tp / (tp + fn)       # of the real raids, how many we caught
```

With more than two classes, "positive" is one class against all the others (one-vs-rest).

**3. Zero-division rules.** An alarm that never fires has `tp + fp == 0`: precision is 0/0.
scikit-learn (`zero_division=0`) reports **0.0** there; do the same for recall when there are no
real positives, and for F1 when precision + recall is 0. Never crash, never return `nan`.

**4. F1 is the harmonic mean** `2·p·r / (p + r)`, not the average. A judge with precision 1.0 and
recall 0.1 averages 0.55 (sounds fine) but its F1 is 0.18 (it is not fine). The harmonic mean is
dragged down by the worse of the two.

**5. Macro F1.** Compute F1 for each class `0 … k-1` one-vs-rest, then take the plain mean. Each
class gets an equal vote however rare it is. (A class that never appears anywhere scores 0.0.)

**6. The common mistake: the transposed ledger.** `cm[pred, true]` instead of `cm[true, pred]`
swaps false positives with false negatives, which swaps precision with recall. Your report
will look plausible and be exactly backwards.

**7. The library versions.** `sklearn.metrics.confusion_matrix`, `precision_recall_fscore_support`,
`f1_score(average="macro")`; `torchmetrics` has the same names. Sealed here: you are the ledger.
""",
    starter='''
"""
==============================================================================
  LAB ML04 // THE JUDGE'S LEDGER                       TARGET: ACCURACY.cult
==============================================================================
  Classification metrics from scratch, numpy only (sklearn.metrics is
  sealed). Labels are integers 0 .. k-1. The grader compares you with a
  reference on fresh random predictions, imbalanced classes and empty input.
"""
import numpy as np


# -- OBJECTIVE 1 -------------------------------------------------------------
def confusion_matrix(y_true, y_pred, n_classes=None):
    """(k, k) integer matrix: cm[t, p] counts samples with truth t predicted p.

    k = n_classes if given, else max(max(y_true), max(y_pred)) + 1.
        confusion_matrix([0, 1, 1], [0, 0, 1]) -> [[1, 0], [1, 1]]
    Empty input with n_classes=2 -> [[0, 0], [0, 0]].
    """
    # TODO
    raise NotImplementedError("OBJECTIVE 1: confusion_matrix")


# -- OBJECTIVE 2 -------------------------------------------------------------
def accuracy(y_true, y_pred):
    """Share of predictions that are right, a float in [0, 1]."""
    # TODO
    raise NotImplementedError("OBJECTIVE 2: accuracy")


# -- OBJECTIVE 3 // CORRUPTED CODE -------------------------------------------
# ACCURACY.cult's F1. It flatters lopsided judges, and it divides by zero
# when both numbers are 0. F1 must be 0.0 in that case.
def f1_from(precision, recall):
    """Harmonic mean of precision and recall."""
    return (precision + recall) / 2


# -- OBJECTIVE 4 -------------------------------------------------------------
def precision_recall_f1(y_true, y_pred, positive=1):
    """(precision, recall, f1) as floats, for class `positive` vs the rest.

    Zero-division rule (scikit-learn's zero_division=0): any 0/0 is 0.0.
    Use f1_from for the F1.
    """
    # TODO
    raise NotImplementedError("OBJECTIVE 4: precision_recall_f1")


# -- OBJECTIVE 5 -------------------------------------------------------------
def macro_f1(y_true, y_pred, n_classes):
    """Mean F1 over classes 0 .. n_classes-1, each one-vs-rest."""
    # TODO
    raise NotImplementedError("OBJECTIVE 5: macro_f1")
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "An alarm that never rings is right ninety-seven nights in a hundred. Is it a good alarm, {callsign}?"},
            {"speaker": "ada", "mood": "cold",
             "text": "The old world shipped that alarm. Many times. Because the dashboard showed one number, and the number was high."},
            {"speaker": "nova", "mood": "neutral",
             "text": "Perimeter logs are queued for you. Ninety-seven quiet nights, three raids. Let's see what the cult really caught."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "alarm",
              "text": "ZeroDivisionError, or a nan in the output. Some count was zero. The rule is: 0/0 reports 0.0."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "IndexError on the matrix means a label is bigger than k-1. How big did you make it, and why?"}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "Empty input is still input. max() of nothing fails; n_classes was given for exactly that case."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Rows are truth, columns are the verdict. Swap them and precision becomes recall. Which did you swap?"}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Precision divides by what the judge flagged. Recall divides by what was really there. Different denominators."}],
            [{"speaker": "ada", "mood": "smirk",
              "text": "If F1 sits halfway between a perfect score and a terrible one, it's an average. Harmonic means are harsher."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Recall zero. Read it aloud, {callsign}. Every raid, missed. The plaque comes down tonight."},
            {"speaker": "nova", "mood": "smirk",
             "text": "Logging it: alarm precision and recall on the board, by class, every shift. The cult's gone quiet."},
            {"speaker": "ada", "mood": "neutral",
             "text": "Now you can say how a judge is wrong. Next: how to know you didn't just get lucky with one test."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

SEALED_MODULES = {"sklearn", "scipy", "statsmodels", "torch", "torchmetrics"}
SEALED_NAMES = {"precision_score", "recall_score", "f1_score", "precision_recall_fscore_support",
                "classification_report"}


def _cm_ref(y_true, y_pred, k=None):
    y_true, y_pred = np.asarray(y_true, dtype=int), np.asarray(y_pred, dtype=int)
    if k is None:
        k = int(max(y_true.max(), y_pred.max())) + 1
    cm = np.zeros((k, k), dtype=int)
    np.add.at(cm, (y_true, y_pred), 1)
    return cm


def _prf_ref(y_true, y_pred, pos):
    tp = int(np.sum((y_pred == pos) & (y_true == pos)))
    fp = int(np.sum((y_pred == pos) & (y_true != pos)))
    fn = int(np.sum((y_pred != pos) & (y_true == pos)))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def _macro_ref(y_true, y_pred, k):
    return float(np.mean([_prf_ref(y_true, y_pred, c)[2] for c in range(k)]))


def _labels(seed, n, k, skill=0.6, weights=None):
    rng = np.random.default_rng(seed)
    y_true = rng.choice(k, size=n, p=weights)
    noise = rng.choice(k, size=n)
    y_pred = np.where(rng.random(n) < skill, y_true, noise)
    return y_true, y_pred


def _crash_hint(exc: BaseException) -> str:
    if isinstance(exc, NotImplementedError):
        return "That's still the starter stub. Replace the `raise NotImplementedError(...)` line with your code."
    if isinstance(exc, ZeroDivisionError):
        return "Some count was zero. The rule: a 0/0 precision, recall or F1 is reported as 0.0. Check before dividing."
    if isinstance(exc, IndexError):
        return "A label is outside the matrix. Size it k × k with k = n_classes or the largest label + 1."
    if isinstance(exc, ValueError) and "empty" in str(exc):
        return "max() of an empty array fails. When n_classes is given, use it and don't look at the labels."
    return "Call the function yourself on a tiny input and read the full error."


def _matrix(got, label, k):
    if got is None:
        raise Fail(f"`{label}` returned None.", hint="End with `return cm`.")
    try:
        cm = np.asarray(got)
    except Exception:  # noqa: BLE001
        raise Fail(f"`{label}` returned {_show(got)}, not a matrix.")
    if cm.shape != (k, k):
        raise Fail(f"`{label}` returned shape {cm.shape}; expected ({k}, {k}).",
                   hint="One row and one column per class 0 .. k-1, even for classes that never appear.")
    if cm.dtype.kind not in "iu":
        if cm.dtype.kind == "f" and np.all(cm == np.round(cm)):
            raise Fail(f"`{label}` returned dtype {cm.dtype}; counts are integers.",
                       hint="Create it with np.zeros((k, k), dtype=int).")
        raise Fail(f"`{label}` returned dtype {cm.dtype}; expected integer counts.")
    return cm


def _triple(got, label):
    if not isinstance(got, (tuple, list)) or len(got) != 3:
        raise Fail(f"`{label}` returned {_show(got, 80)}; expected (precision, recall, f1).",
                   hint="return precision, recall, f1")
    return tuple(_scalar(v, f"{label}[{i}]") for i, v in enumerate(got))


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Ledger — `confusion_matrix`: rows are truth, columns are verdicts")
def _ledger(ctx):
    _numpy()
    fn = _fn(ctx, "confusion_matrix")
    cases = [(np.array([0, 1, 1]), np.array([0, 0, 1]), None)]
    cases += [(*_labels(4101, 40, 3), None), (*_labels(4102, 25, 2), 2), (*_labels(4103, 60, 5, 0.4), 5)]
    for y_true, y_pred, k in cases:
        args = (y_true, y_pred) if k is None else (y_true, y_pred, k)
        label = f"confusion_matrix({_show(y_true, 40)}, {_show(y_pred, 40)}" + (f", n_classes={k})" if k else ")")
        expected = _cm_ref(y_true, y_pred, k)
        cm = _matrix(_call(label, fn, *args, crash_hint=_crash_hint), label, expected.shape[0])
        if not np.array_equal(cm, expected):
            hint = "Count each pair once: cm[t, p] += 1 for every (truth t, prediction p)."
            if np.array_equal(cm, expected.T):
                hint = "Transposed: you filled cm[pred, true]. Rows are TRUTH, columns are the PREDICTION."
            elif cm.sum() != len(y_true):
                hint = f"Your counts add up to {cm.sum()}, but there are {len(y_true)} samples: each one lands in exactly one cell."
            raise Fail(f"{label} returned\n{_show(cm)}\nexpected\n{_show(expected)}", hint=hint)


@MISSION.check("Edge rows — empty input, silent classes, explicit n_classes")
def _edges(ctx):
    _numpy()
    fn = _fn(ctx, "confusion_matrix")
    empty = np.array([], dtype=int)
    cases = [((empty, empty, 2), "no samples at all"),
             ((np.array([0, 1, 0]), np.array([0, 1, 1]), 4), "classes 2 and 3 never appear"),
             ((np.array([0, 0, 1]), np.array([0, 2, 1]), None), "a class only the judge predicted"),
             ((np.array([2, 2]), np.array([2, 2]), None), "only the highest class appears")]
    for args, story in cases:
        k = args[2]
        call = args if k is not None else args[:2]
        label = f"confusion_matrix({_show(args[0])}, {_show(args[1])}" + (f", n_classes={k})" if k else ")")
        expected = _cm_ref(*args)
        cm = _matrix(_call(label, fn, *call, crash_hint=_crash_hint), label, expected.shape[0])
        if not np.array_equal(cm, expected):
            raise Fail(f"{label} — {story}: returned\n{_show(cm)}\nexpected\n{_show(expected)}",
                       hint="Size first (n_classes, or the largest label in EITHER array + 1), then count.")


@MISSION.check("The cult exposed — 97% accuracy, zero recall, no crash")
def _cult(ctx):
    _numpy()
    acc_fn, prf_fn = _fn(ctx, "accuracy"), _fn(ctx, "precision_recall_f1")
    rng = np.random.default_rng(4301)
    y_true = np.zeros(100, dtype=int)
    y_true[rng.choice(100, size=3, replace=False)] = 1
    silent = np.zeros(100, dtype=int)
    label = "accuracy(perimeter_truth, alarm_never_fires)"
    got = _scalar(_call(label, acc_fn, y_true, silent, crash_hint=_crash_hint), label)
    if not np.isclose(got, 0.97):
        raise Fail(f"{label} returned {got!r}; expected 0.97 (97 quiet nights called correctly).",
                   hint="np.mean(y_true == y_pred): the share of matches.")
    y2, p2 = _labels(4302, 30, 3)
    label2 = f"accuracy({_show(y2, 40)}, {_show(p2, 40)})"
    got = _scalar(_call(label2, acc_fn, y2, p2, crash_hint=_crash_hint), label2)
    if not np.isclose(got, np.mean(y2 == p2)):
        raise Fail(f"{label2} returned {got!r}; expected {np.mean(y2 == p2)!r}.",
                   hint="Accuracy works for any number of classes: the share of predictions equal to the truth.")
    label = "precision_recall_f1(perimeter_truth, alarm_never_fires, positive=1)"
    with np.errstate(all="ignore"):
        prf = _triple(_call(label, prf_fn, y_true, silent, 1, crash_hint=_crash_hint), label)
    if not np.all(np.isfinite(prf)) or not np.allclose(prf, (0.0, 0.0, 0.0)):
        raise Fail(f"{label} returned {prf}; expected (0.0, 0.0, 0.0).",
                   hint="The alarm never fired: tp + fp = 0, so precision is 0/0 → 0.0. It caught 0 of 3 raids: "
                        "recall 0.0. And F1 with p + r = 0 is 0.0, not nan.")


@MISSION.check("Precision & recall — counted for the positive class")
def _precision_recall(ctx):
    _numpy()
    fn = _fn(ctx, "precision_recall_f1")
    cases = [(*_labels(4401, 50, 2, 0.5, [0.7, 0.3]), 1), (*_labels(4402, 50, 2, 0.5, [0.7, 0.3]), 0),
             (*_labels(4403, 80, 4, 0.5), 2),
             (np.array([1, 1, 0, 0]), np.array([1, 1, 1, 1]), 1),
             (np.array([0, 0, 0]), np.array([0, 1, 0]), 1)]
    for y_true, y_pred, pos in cases:
        label = f"precision_recall_f1({_show(y_true, 40)}, {_show(y_pred, 40)}, positive={pos})"
        with np.errstate(all="ignore"):
            got = _triple(_call(label, fn, y_true, y_pred, pos, crash_hint=_crash_hint), label)
        want = _prf_ref(y_true, y_pred, pos)
        if not np.allclose(got[:2], want[:2], atol=1e-12):
            hint = "precision = tp / (tp + fp), recall = tp / (tp + fn), counted for class `positive` only."
            if np.allclose(got[:2], want[1::-1], atol=1e-12):
                hint = "Precision and recall are swapped. Precision divides by what was PREDICTED positive."
            elif pos != 1:
                hint = "Use the `positive` argument: the class being judged isn't always 1."
            raise Fail(f"{label} returned precision={got[0]:.4f}, recall={got[1]:.4f}; "
                       f"expected {want[0]:.4f}, {want[1]:.4f}.", hint=hint)


@MISSION.check("Harmonic — F1 punishes a lopsided judge (corrupted code repaired)")
def _harmonic(ctx):
    _numpy()
    f1_fn, prf_fn = _fn(ctx, "f1_from"), _fn(ctx, "precision_recall_f1")
    for p, r in ((1.0, 0.1), (0.5, 0.5), (0.8, 0.4), (0.0, 0.0), (0.0, 1.0)):
        label = f"f1_from({p}, {r})"
        with np.errstate(all="ignore"):
            got = _scalar(_call(label, f1_fn, p, r, crash_hint=_crash_hint), label)
        want = 2 * p * r / (p + r) if p + r else 0.0
        if not np.isfinite(got) or not np.isclose(got, want, atol=1e-12):
            hint = "F1 = 2·p·r / (p + r), the harmonic mean."
            if np.isclose(got, (p + r) / 2):
                hint = "That's the arithmetic mean. F1 is the HARMONIC mean, 2·p·r / (p + r): the weak side drags it down."
            elif p + r == 0:
                hint = "Both are 0, so p + r is 0: return 0.0 before dividing."
            raise Fail(f"{label} returned {got!r}; expected {want!r}.", hint=hint)
    y_true, y_pred = _labels(4501, 60, 2, 0.6, [0.6, 0.4])
    label = f"precision_recall_f1({_show(y_true, 40)}, {_show(y_pred, 40)}, positive=1)"
    got = _triple(_call(label, prf_fn, y_true, y_pred, 1, crash_hint=_crash_hint), label)
    want = _prf_ref(y_true, y_pred, 1)
    if not np.isclose(got[2], want[2], atol=1e-12):
        raise Fail(f"{label}: f1 is {got[2]:.4f}; expected {want[2]:.4f}.",
                   hint="Return f1_from(precision, recall) as the third value.")


@MISSION.check("Macro F1 — every class gets an equal vote")
def _macro(ctx):
    _numpy()
    fn = _fn(ctx, "macro_f1")
    cases = [(*_labels(4601, 90, 3, 0.6, [0.8, 0.15, 0.05]), 3), (*_labels(4602, 40, 4, 0.5), 4),
             (np.array([0, 0, 1, 1]), np.array([0, 0, 1, 1]), 3),
             (np.array([0, 0, 0, 1]), np.array([0, 0, 0, 0]), 2)]
    for y_true, y_pred, k in cases:
        label = f"macro_f1({_show(y_true, 40)}, {_show(y_pred, 40)}, n_classes={k})"
        with np.errstate(all="ignore"):
            got = _scalar(_call(label, fn, y_true, y_pred, k, crash_hint=_crash_hint), label)
        want = _macro_ref(y_true, y_pred, k)
        if not np.isfinite(got) or not np.isclose(got, want, atol=1e-12):
            hint = "For each class c in range(n_classes): F1 of c vs the rest. Then the plain mean of those k numbers."
            if np.isclose(got, np.mean(y_true == y_pred)):
                hint = "That's accuracy. Macro F1 averages the per-class F1 scores."
            elif np.isclose(got, float(np.mean([_prf_ref(y_true, y_pred, c)[2] for c in np.unique(y_true)]))):
                hint = "Average over ALL classes 0 .. n_classes-1, not only the ones in y_true. A silent class scores 0.0."
            raise Fail(f"{label} returned {got!r}; expected {want!r}.", hint=hint)


@MISSION.check("Sealed shortcuts — you are the ledger")
def _no_shortcuts(ctx):
    found = _sealed(ctx, SEALED_MODULES, SEALED_NAMES)
    if found:
        line, name = found
        raise Fail(f"Line {line} uses `{name}`. The metrics library is sealed in this mission.",
                   hint="Count tp, fp and fn yourself with boolean masks. The grader compares you with a reference.")
