"""LEVEL 10 // BOSS: THE ARBITER — a rule-based classifier as functions, scored with accuracy / precision / recall.

Sector 1 boss. Stage I audits the ARBITER's own verdicts, Stage II replaces its statute with a
better classifier, Stage III files the appeals. Every function is called on a hidden docket of
fresh records the player never sees, so a rule that only memorises the evidence fails.
"""
from __future__ import annotations

import ast
import copy
import random
import re

from engine.drills import compare_cases
from engine.mission import Cutscene, Fail, Mission

# ── the court records (asset: tribunal.py) ───────────────────────────────────────

EVIDENCE = [
    {"id": "SIG-0101", "speed": 1.1, "heat": 36.9, "carrier": 12, "hostile": False},
    {"id": "SIG-0102", "speed": 4.8, "heat": 37.6, "carrier": 18, "hostile": False},
    {"id": "SIG-0103", "speed": 6.2, "heat": 21.0, "carrier": 55, "hostile": True},
    {"id": "SIG-0104", "speed": 3.4, "heat": 37.9, "carrier": 5, "hostile": False},
    {"id": "SIG-0105", "speed": 0.6, "heat": 18.4, "carrier": 30, "hostile": True},
    {"id": "SIG-0106", "speed": 6.8, "heat": 35.8, "carrier": 94, "hostile": True},
    {"id": "SIG-0107", "speed": 0.9, "heat": 36.5, "carrier": 88, "hostile": False},
    {"id": "SIG-0108", "speed": 5.5, "heat": 37.2, "carrier": 80, "hostile": False},
    {"id": "SIG-0109", "speed": 0.0, "heat": 24.7, "carrier": 70, "hostile": True},
    {"id": "SIG-0110", "speed": 1.5, "heat": 36.2, "carrier": 25, "hostile": False},
    {"id": "SIG-0111", "speed": 7.4, "heat": 26.3, "carrier": 81, "hostile": True},
    {"id": "SIG-0112", "speed": 6.1, "heat": 38.4, "carrier": 41, "hostile": False},
    {"id": "SIG-0113", "speed": 4.1, "heat": 34.9, "carrier": 90, "hostile": True},
    {"id": "SIG-0114", "speed": 2.0, "heat": 32.0, "carrier": 8, "hostile": False},
    {"id": "SIG-0115", "speed": 3.0, "heat": 29.9, "carrier": 60, "hostile": True},
    {"id": "SIG-0116", "speed": 4.0, "heat": 36.6, "carrier": 95, "hostile": False},
]

STATUTE = '''\
def arbiter_verdict(record):
    """The ARBITER's statute, article 1: whoever flees the court is guilty."""
    return record["speed"] > 3.0
'''


def _render_tribunal() -> str:
    rows = "\n".join(f"    {r!r}," for r in EVIDENCE)
    return (
        '"""TRIBUNAL RECORDS // copied from the ARBITER\'s court by RUST\'s wiretap.\n\n'
        "EVIDENCE: signals the Order verified by hand. \"hostile\" is the TRUTH:\n"
        "True for a Grid hunter, False for a human. speed is m/s, heat is degrees C,\n"
        "carrier is broadcast strength from 0 to 100.\n\n"
        "arbiter_verdict(record): the ARBITER's ruling. True means DELETE.\n"
        "Don't edit this file. If you do, delete it and the game restores the original.\n"
        '"""\n\n'
        f"EVIDENCE = [\n{rows}\n]\n\n\n{STATUTE}"
    )


TRIBUNAL_PY = _render_tribunal()
_court: dict = {}
exec(STATUTE, _court)                       # the reference ARBITER is the exact code shipped in the asset
_arbiter = _court["arbiter_verdict"]


def _classify(r):
    return r["heat"] < 32.0 or (r["carrier"] > 80 and r["speed"] > 4.0)


def _confusion(predictions, labels):
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for p, a in zip(predictions, labels):
        cm["tp" if p and a else "fp" if p else "fn" if a else "tn"] += 1
    return cm


def _ratio(top, bottom):
    return top / bottom if bottom else 0.0


def _accuracy(cm):
    return _ratio(cm["tp"] + cm["tn"], cm["tp"] + cm["fp"] + cm["fn"] + cm["tn"])


def _precision(cm):
    return _ratio(cm["tp"], cm["tp"] + cm["fp"])


def _recall(cm):
    return _ratio(cm["tp"], cm["tp"] + cm["fn"])


def _evaluate(records, judge):
    return _confusion([judge(r) for r in records], [r["hostile"] for r in records])


def _pardons(records):
    return sorted(r["id"] for r in records if _arbiter(r) and not _classify(r))


def _docket() -> list[dict]:
    """The hidden docket: 48 fresh signals across every archetype, labelled by the Order's finding."""
    rng = random.Random("L10:hidden-docket")
    kinds = [
        ("walker", (0.2, 2.6), (35.2, 38.2), (0, 45)),
        ("runner", (3.1, 7.5), (36.0, 39.2), (0, 80)),
        ("rigged", (0.0, 4.0), (35.0, 38.0), (81, 100)),
        ("chilled", (0.0, 3.0), (32.0, 34.0), (0, 30)),
        ("hunter", (0.0, 9.0), (11.0, 31.9), (0, 100)),
        ("masked", (4.1, 9.0), (32.0, 37.5), (81, 100)),
    ]
    docket = []
    for n in range(48):
        _, speed, heat, carrier = kinds[n % len(kinds)]
        r = {"id": f"DKT-{rng.randint(1000, 9999)}-{n:02d}",
             "speed": round(rng.uniform(*speed), 1), "heat": round(rng.uniform(*heat), 1),
             "carrier": rng.randint(*carrier)}
        r["hostile"] = _classify(r)
        docket.append(r)
    return docket


DOCKET = _docket()

# Records sitting exactly on each line of the Order's finding.
EDGES = [
    {"id": "EDGE-HEAT", "speed": 1.0, "heat": 32.0, "carrier": 10, "hostile": False},
    {"id": "EDGE-COLD", "speed": 1.0, "heat": 31.9, "carrier": 10, "hostile": True},
    {"id": "EDGE-CARRIER", "speed": 6.0, "heat": 36.0, "carrier": 80, "hostile": False},
    {"id": "EDGE-SPEED", "speed": 4.0, "heat": 36.0, "carrier": 99, "hostile": False},
    {"id": "EDGE-BOTH", "speed": 4.1, "heat": 36.0, "carrier": 81, "hostile": True},
    {"id": "EDGE-STILL", "speed": 0.0, "heat": 36.0, "carrier": 100, "hostile": False},
    {"id": "EDGE-COLDRIG", "speed": 0.0, "heat": 12.0, "carrier": 100, "hostile": True},
]

REPORT = ("TRIBUNAL | arbiter precision={:.2f} recall={:.2f} | order precision={:.2f} recall={:.2f} | pardons={}"
          .format(_precision(_evaluate(EVIDENCE, _arbiter)), _recall(_evaluate(EVIDENCE, _arbiter)),
                  _precision(_evaluate(EVIDENCE, _classify)), _recall(_evaluate(EVIDENCE, _classify)),
                  len(_pardons(EVIDENCE))))


MISSION = Mission(
    id="L10",
    slug="level_10_the_arbiter",
    title="BOSS: THE ARBITER",
    concept="A rule-based classifier",
    enemy="ARBITER.court",
    xp=320,
    par_seconds=45 * 60,
    tier=2,
    boss=True,
    concepts=("functions", "conditionals", "loops", "ml-math"),
    timeout=10.0,
    assets={"tribunal.py": TRIBUNAL_PY},
    enemy_art="""\
   ▄▄▄██████████▄▄▄
  ██▀▀  ▄▄▄▄▄▄  ▀▀██
  █  ▄██▀▀  ▀▀██▄  █
  █ ▀▀▀  ▐██▌  ▀▀▀ █
  ██▄   ▄████▄   ▄██
   ▀██▄▄▄▀▀▀▀▄▄▄██▀
  ▄▄▄▄▄▄████▄▄▄▄▄▄▄""",
    briefing="""\
The Tribunal spire rises out of the Grid like a nail driven through the city. At its top,
**the ARBITER** holds court: a judge with a thousand-year docket and no doubt at all.

At dawn it sentences every signal on the Grid. HOSTILE means deletion. RUST's wiretap
copied its records into `tribunal.py` beside your mission. Sixteen signals the Order
verified by hand, and the ARBITER's statute. One line long.

It deletes whoever runs. People run from it.

The ARBITER won't hear pleas, only evidence. So you'll give it evidence: measure its
verdicts, write a better judge, prove it on cases neither of you has seen, and file the
appeals.

**Cross-examine the ARBITER. Then overturn it.**
""",
    why="""\
A model that's "90% accurate" can still be useless, or dangerous. Every classifier is
judged with a **confusion matrix** and the metrics built on it:

```python
cm = {"tp": 40, "fp": 10, "fn": 5, "tn": 945}
precision = cm["tp"] / (cm["tp"] + cm["fp"])   # 0.80: of everything flagged, how much was right?
recall = cm["tp"] / (cm["tp"] + cm["fn"])      # 0.89: of everything real, how much was caught?
```

That model is 98.5% accurate, mostly by saying "no" to the 955 easy cases. Precision tells
you how many innocent people your fraud alert hits. Recall tells you how many frauds slip
past. Which one matters more is an ethical decision, not a technical one.

And a rule is only proven on data it has **never seen**. Real teams lock away a test set for
exactly that reason.
""",
    manual="""\
**1 · Importing names from a file.** `from tribunal import EVIDENCE, arbiter_verdict` runs
`tribunal.py` (beside your mission) and gives you its list and its function. The line is
already in your starter. Open `tribunal.py` to read the evidence.

**2 · The confusion matrix.** Compare each prediction with the truth and count four kinds
of outcome:

| prediction | truth | name |
|---|---|---|
| hostile | hostile | **tp**, true positive |
| hostile | human | **fp**, false positive: an innocent deleted |
| human | hostile | **fn**, false negative: a hunter missed |
| human | human | **tn**, true negative |

**3 · Metrics, and the zero guard.** Each metric divides one count by a total of counts:

```python
accuracy  = (tp + tn) / (tp + fp + fn + tn)   # how often it was right at all
precision = tp / (tp + fp)                    # when it says hostile, is it?
recall    = tp / (tp + fn)                    # of the real hostiles, how many did it catch?
```

If the bottom is 0 (a judge that never says "hostile" has no precision to measure), return
`0.0` instead of dividing. Check with an `if` before you divide.

**4 · Functions are values.** You passed `lambda` to `sorted(key=...)` in SUBROUTINES. Any
function can be handed to another function by name, *without* the parentheses, and called
inside:

```python
def apply_all(items, rule):
    return [rule(x) for x in items]

def is_big(n):
    return n > 10

apply_all([4, 40], is_big)        # [False, True]
```

That's how one `evaluate` can grade any judge: the ARBITER's, or yours.

**5 · A rule-based classifier** is a function that returns `True` or `False` from a record's
fields, built from the comparisons and `and` / `or` of TRIPWIRE. Translate the rule's words
exactly: "colder than 32.0" is `< 32.0`; "above 80" is `> 80`. Return the condition itself;
it's already a bool.

**6 · Two decimals.** In an f-string, `:.2f` after a value rounds it for display:
`f"{4 / 9:.2f}"` shows `0.44`. The value itself stays exact.
""",
    starter='''
"""
==============================================================================
  LEVEL 10 // BOSS: THE ARBITER                      TARGET: ARBITER.court
==============================================================================
  Three stages. The ARBITER only accepts evidence: every function you write
  is called on a HIDDEN DOCKET of signals you have never seen.
"""
from tribunal import EVIDENCE, arbiter_verdict

# EVIDENCE is a list of 16 records the Order verified by hand, like:
#   {"id": "SIG-0101", "speed": 1.1, "heat": 36.9, "carrier": 12, "hostile": False}
# speed in m/s, heat in degrees C, carrier strength 0-100.
# "hostile" is the TRUTH: True for a Grid hunter, False for a human.
# arbiter_verdict(record) is the ARBITER's ruling: True means DELETE.
# Open tribunal.py to read the evidence and the ARBITER's statute.


# ════════════════════ STAGE I // CROSS-EXAMINE THE JUDGE ════════════════════

# -- OBJECTIVE 1 // CORRUPTED CODE --------------------------------------------
# confusion(predictions, labels) tallies a judge's calls against the truth.
# Both are lists of bools, in the same order. It should count all four
# outcomes over EVERY pair, but it only ever counts the first one, and for
# empty lists it returns None. One line is in the wrong place.
def confusion(predictions, labels):
    """Count true/false positives/negatives of predictions against labels."""
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for predicted, actual in zip(predictions, labels):
        if predicted and actual:
            counts["tp"] += 1
        elif predicted:
            counts["fp"] += 1
        elif actual:
            counts["fn"] += 1
        else:
            counts["tn"] += 1
        return counts


# -- OBJECTIVE 2 -------------------------------------------------------------
# Write three functions. Each takes a confusion dict `cm` and returns a float:
#   accuracy(cm)   ->  (tp + tn) / (tp + fp + fn + tn)
#   precision(cm)  ->  tp / (tp + fp)
#   recall(cm)     ->  tp / (tp + fn)
# If the bottom of a division is 0, return 0.0 instead of dividing.



# -- OBJECTIVE 3 -------------------------------------------------------------
# Write evaluate(records, judge). `judge` is a FUNCTION (like arbiter_verdict).
#   1. predictions: judge(r) for every record r, in order
#   2. labels: r["hostile"] for every record r, in order
#   3. return confusion(predictions, labels)
#                 example:  [rule(x) for x in items]



# -- OBJECTIVE 4 -------------------------------------------------------------
# Put the ARBITER on the stand. Using evaluate, precision and recall, create:
#   arbiter_cm         the confusion dict for arbiter_verdict on EVIDENCE
#   arbiter_precision  the ARBITER's precision
#   arbiter_recall     the ARBITER's recall



# ═════════════════════════ STAGE II // A BETTER JUDGE ═══════════════════════

# -- OBJECTIVE 5 -------------------------------------------------------------
# Write classify(record): return True for a Grid hunter, False for a human.
# The Order's investigators found, across every case they ever verified:
#   "Every hunter ran COLDER than 32.0 degrees, OR broadcast a carrier ABOVE
#    80 while moving FASTER than 4.0 m/s. No human ever did either."
# Translate it exactly. It will be judged on records you haven't seen.



# -- OBJECTIVE 6 -------------------------------------------------------------
# Your judge on the stand: create order_cm, order_precision, order_recall,
# exactly like objective 4 but for classify.



# ════════════════════════════ STAGE III // THE APPEAL ═══════════════════════

# -- OBJECTIVE 7 -------------------------------------------------------------
# Write pardons(records): the ids of every record the ARBITER sentences
# (arbiter_verdict is True) but your classify clears (False), sorted
# alphabetically.          example:  sorted(x["id"] for x in items if ...)



# -- OBJECTIVE 8 -------------------------------------------------------------
# Read the verdict into the court record. Print exactly this, with every
# metric shown to 2 decimals (:.2f) and pardons as how many there are:
# TRIBUNAL | arbiter precision=0.44 recall=0.57 | order precision=1.00 recall=1.00 | pardons=5

''',
    dialogue={
        "intro": [
            {"speaker": "arbiter", "mood": "cold",
             "text": "THE COURT IS IN SESSION. Signal 0102: fleeing. Verdict: hostile. Sentence: deletion. Next."},
            {"speaker": "arbiter", "mood": "cold",
             "text": "You wish to object, {callsign}? This court hears no pleas. It hears only evidence."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Then that's what we bring. Measure its verdicts first. A judge is only as good as its record."},
        ],
        "crash": [
            [{"speaker": "arbiter", "mood": "cold",
              "text": "DISORDER IN THE COURT. Your submission failed to execute. It is struck from the record."},
             {"speaker": "cipher", "mood": "neutral",
              "text": "ZeroDivisionError means a metric divided by an empty total. Guard it with an if and return 0.0."}],
            [{"speaker": "arbiter", "mood": "cold",
              "text": "Exhibit inadmissible. A court cannot weigh evidence that crashes on arrival."},
             {"speaker": "cipher", "mood": "neutral",
              "text": "If tribunal can't be imported, the records file is missing. Let the game restore it beside your mission."}],
        ],
        "fail": [
            [{"speaker": "arbiter", "mood": "cold",
              "text": "OBJECTION OVERRULED. Your judge errs on a case you never saw. That is what judges do. I would know."}],
            [{"speaker": "arbiter", "mood": "neutral",
              "text": "You found my errors. Commendable. Now find your own. The docket is long and it does not repeat."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Read the record it quotes. Which clause of the finding should have caught it? Check the boundary: < or <=."}],
        ],
        "victory": [
            {"speaker": "arbiter", "mood": "warm",
             "text": "Precision one. Recall one. The court... was wrong. Five hundred sentences are vacated. Let the record show it."},
            {"speaker": "arbiter", "mood": "cold",
             "text": "My statute was not my own. It was issued from the Foundry. Ask the furnaces who taught me to judge."},
            {"speaker": "cipher", "mood": "warm",
             "text": "You didn't destroy it, {callsign}. You corrected it. Remember that. It matters more than you know."},
            {"speaker": "vex", "mood": "smirk",
             "text": "Beating a judge is cute. Beating me is a sport. The Arena, monk. Tonight. Bring your fastest code."},
        ],
    },
    cutscene=Cutscene(
        title="VERDICT OVERTURNED",
        narration=[
            "The Tribunal spire goes silent. Across the Grid, five hundred deletion orders hang in the air, then fall away like ash.",
            "ARBITER: The court finds itself in error. Precision one. Recall one. The record is corrected.",
            "Its faceless head fractures into a slow rain of red glyphs, and the lattice streets below burn steady cyan.",
            "Far below, in the Monastery's old cooling chamber, a ring of magenta light switches on for the first time in years.",
            "VEX: Judges are easy, monk. They wait for you. I don't. The Arena's open. Come and lose properly.",
        ],
        shot=("the established hero from the avatar reference standing on a rain-slick glass walkway at the summit of the "
              "Tribunal spire above the Grid, a neon lattice of dead city blocks; the ARBITER, a colossal faceless judge's "
              "head of segmented cyan (#00f0ff) scales, fractures into falling blood-red (#ff3355) verdict glyphs; far "
              "below, a ring of magenta (#ff2bd6) light ignites in the Monastery's cooling tower, VEX's silhouette at its "
              "edge; the Core's beam on the horizon, void-black sky (#05060a), volumetric rain haze, 35mm anamorphic, "
              "low angle, rim light on the hero's cracked visor"),
        camera=("slow crane up from the hero's visor reflection to reveal the shattering judge, then a long rack-focus "
                "down the spire to the magenta arena ring"),
        anchor=False,
    ),
)


# ── helpers ──────────────────────────────────────────────────────────────────────

_FIELDS = ("speed", "heat", "carrier")


def _top_def(ctx, name: str):
    found = [n for n in ctx.tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return found[-1] if found else None


def _function(ctx, name: str):
    if name not in ctx.ns:
        if ctx.crashed and "EVIDENCE" not in ctx.ns and "arbiter_verdict" not in ctx.ns:
            raise Fail("Your script crashed before it loaded the court records (the `from tribunal import ...` line).",
                       hint="If the error is ModuleNotFoundError, tribunal.py is missing from your missions folder. "
                            "Deploy the mission again and the game restores it beside your file.")
        if ctx.crashed and _top_def(ctx, name):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.",
                   hint=f"Write it at the left edge:  def {name}(...):  with its body indented underneath.")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return fn


def _call(name: str, fn, *args):
    shown = ", ".join(_short(a) for a in args)
    try:
        return fn(*copy.deepcopy(args))
    except ZeroDivisionError:
        raise Fail(f"`{name}({shown})` divided by zero.",
                   hint="When the bottom of the fraction is 0, return 0.0 before dividing. Test it with an if.")
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported with the exact input
        raise Fail(f"`{name}({shown})` raised {type(exc).__name__}: {exc}")


def _short(value) -> str:
    if callable(value):
        return getattr(value, "__name__", "judge")
    if isinstance(value, list) and len(value) > 3 and isinstance(value[0], dict):
        return f"<{len(value)} records>"
    text = repr(value)
    return text if len(text) <= 90 else text[:89] + "…"


def _record(r) -> str:
    return f"{r['id']} (speed {r['speed']}, heat {r['heat']}, carrier {r['carrier']})"


def _judge_hint(r) -> str:
    """Why a record should have gone the other way, starting with the boundary it sits on."""
    if r["heat"] == 32.0:
        return "Exactly 32.0 is not COLDER than 32.0: use <, not <=."
    if r["carrier"] == 80 and r["speed"] > 4.0:
        return "A carrier of exactly 80 is not ABOVE 80: use >, not >=."
    if r["speed"] == 4.0 and r["carrier"] > 80:
        return "Exactly 4.0 m/s is not FASTER than 4.0: use >, not >=."
    if r["hostile"] and r["heat"] < 32.0:
        return "This one runs cold, so the first clause (heat colder than 32.0) should catch it on its own."
    if r["hostile"]:
        return ("Warm, but a strong carrier while moving fast: the second clause. Both parts must hold, "
                "so join them with `and`, and join the two clauses with `or`.")
    if r["carrier"] > 80 or r["speed"] > 4.0:
        return ("A human. Only ONE part of the second clause is true here, and the finding needs BOTH "
                "(carrier above 80 AND speed above 4.0). Check `and` vs `or`.")
    return "A human. Neither clause of the finding applies, so your judge must return False."


def _evidence_intact(ctx):
    if ctx.get("EVIDENCE") != EVIDENCE:
        raise Fail("The EVIDENCE list doesn't match the court's records. Someone edited tribunal.py.",
                   hint="Delete tribunal.py from your missions folder; the game restores the original on the next hack.")


def _uses_call(ctx, var: str, func: str, *needed: str) -> bool:
    """True if `var` is assigned from a call to `func` that mentions every name in `needed`."""
    for value in ctx.assignments(var):
        for node in ast.walk(value):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == func:
                names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
                if all(n in names for n in needed):
                    return True
    return False


def _metric_vars(ctx, prefix: str, judge: str, judge_ref):
    cm_name = f"{prefix}_cm"
    cm = ctx.get(cm_name)
    if not _uses_call(ctx, cm_name, "evaluate", "EVIDENCE", judge):
        raise Fail(f"`{cm_name}` must come from evaluate(EVIDENCE, {judge}), not from counting by hand.",
                   hint=f"Pass the function itself, without parentheses:  evaluate(EVIDENCE, {judge})")
    expected = _evaluate(EVIDENCE, judge_ref)
    if cm != expected:
        raise Fail(f"`{cm_name}` is {cm!r}, expected {expected!r}.",
                   hint="If evaluate passes its own layer, check you passed EVIDENCE and the right judge.")
    for metric, ref in (("precision", _precision), ("recall", _recall)):
        name = f"{prefix}_{metric}"
        value = ctx.get(name)
        if not ctx.call_uses(metric, cm_name) or not ctx.derived_from(name, cm_name):
            raise Fail(f"`{name}` must be computed with {metric}({cm_name}).",
                       hint="Reuse the functions from objective 2; don't retype the fraction.")
        if not isinstance(value, float) or abs(value - ref(expected)) > 1e-9:
            raise Fail(f"`{name}` is {value!r}, expected {ref(expected)!r}.")


# ── firewall layers ──────────────────────────────────────────────────────────────

_CM_CASES = [
    {"tp": 4, "fp": 5, "fn": 3, "tn": 4},
    {"tp": 40, "fp": 10, "fn": 5, "tn": 945},
    {"tp": 0, "fp": 0, "fn": 7, "tn": 3},
    {"tp": 0, "fp": 6, "fn": 0, "tn": 0},
    {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
    {"tp": 9, "fp": 0, "fn": 0, "tn": 0},
]


@MISSION.check("STAGE I · Repair the tally — `confusion`")
def _confusion_check(ctx):
    fn = _function(ctx, "confusion")
    got = _call("confusion", fn, [True, False], [True, True])
    if got is None:
        raise Fail("confusion([True, False], [True, True]) returned None.",
                   hint="The return line runs too early, or never. It belongs AFTER the loop has seen every pair.")
    if got == {"tp": 1, "fp": 0, "fn": 0, "tn": 0}:
        raise Fail("confusion only counted the FIRST pair: [True, False] vs [True, True] gave tp=1 and nothing else.",
                   hint="A return inside the loop ends the whole function on the first pass. Dedent it so it runs "
                        "once, after the loop.")
    rng = random.Random("L10:confusion")
    cases = [([True, False], [True, True]), ([], []), ([False] * 4, [False, True, False, True])]
    for size in (7, 23):
        preds = [rng.random() < 0.5 for _ in range(size)]
        cases.append((preds, [rng.random() < 0.5 for _ in range(size)]))
    compare_cases(ctx, "confusion", cases, _confusion,
                  hint="Every pair lands in exactly one of tp/fp/fn/tn. Empty lists give four zeros.")


@MISSION.check("STAGE I · Score a judge — accuracy, precision, recall")
def _metrics_check(ctx):
    for name, ref in (("accuracy", _accuracy), ("precision", _precision), ("recall", _recall)):
        fn = _function(ctx, name)
        for cm in _CM_CASES:
            got = _call(name, fn, cm)
            want = ref(cm)
            if type(got) is not float or abs(got - want) > 1e-9:
                if got is None:
                    hint = "It returned None: use return, not print."
                elif type(got) is int:
                    hint = "Return a float: when the bottom is 0, return 0.0 (with the decimal point)."
                elif want == 0.0 and sum(cm.values()) and name != "accuracy":
                    hint = "No positives to measure means the bottom is 0: return 0.0."
                else:
                    hint = {"accuracy": "Right answers (tp + tn) over all four counts.",
                            "precision": "Of everything it FLAGGED (tp + fp), how many were right (tp)?",
                            "recall": "Of everything really hostile (tp + fn), how many did it catch (tp)?"}[name]
                raise Fail(f"`{name}({cm})` returned {got!r}, expected {want!r}.", hint=hint)


@MISSION.check("STAGE I · Cross-examine — `evaluate(records, judge)`")
def _evaluate_check(ctx):
    fn = _function(ctx, "evaluate")
    judges = [(_arbiter, "arbiter_verdict"), (lambda r: True, "a judge that always says hostile"),
              (lambda r: r["carrier"] > 50, "a judge that flags carrier above 50")]
    for records in (DOCKET[:20], DOCKET[20:21], []):
        for judge, label in judges:
            got = _call("evaluate", fn, records, judge)
            want = _evaluate(records, judge)
            if got != want:
                raise Fail(f"evaluate(<{len(records)} fresh records>, {label}) returned {got!r}, expected {want!r}.",
                           hint="Call judge(r) for each record, collect r[\"hostile\"] for each record, then return "
                                "confusion(predictions, labels). If confusion fails its layer, fix that first.")


@MISSION.check("STAGE I · The ARBITER's record — `arbiter_cm`")
def _arbiter_record(ctx):
    _evidence_intact(ctx)
    _metric_vars(ctx, "arbiter", "arbiter_verdict", _arbiter)


@MISSION.check("STAGE II · A better judge — `classify` on the hidden docket")
def _classify_check(ctx):
    fn = _function(ctx, "classify")
    misses = []
    for r in EVIDENCE + DOCKET:
        record = {k: v for k, v in r.items() if k != "hostile"}
        got = _call("classify", fn, record)
        if got is not r["hostile"]:
            misses.append((r, got))
    if misses:
        r, got = misses[0]
        side = "hunter" if r["hostile"] else "human"
        if not isinstance(got, bool):
            raise Fail(f"classify returned {got!r} for {_record(r)}. A judge must answer True or False.",
                       hint="Return the condition itself: comparisons joined with and / or are already a bool.")
        raise Fail(f"classify got {len(misses)} of {len(EVIDENCE) + len(DOCKET)} cases wrong. First: {_record(r)} "
                   f"is a {side}, but your judge said {got}.", hint=_judge_hint(r))


@MISSION.check("STAGE II · Edge of the law — exact boundaries")
def _edges_check(ctx):
    fn = _function(ctx, "classify")
    for r in EDGES:
        record = {k: v for k, v in r.items() if k != "hostile"}
        got = _call("classify", fn, record)
        if got is not r["hostile"]:
            raise Fail(f"{_record(r)} sits right on the line, and your judge said {got!r} "
                       f"(the finding says {r['hostile']}).", hint=_judge_hint(r))


@MISSION.check("STAGE II · Your judge on the stand — `order_cm`")
def _order_record(ctx):
    _evidence_intact(ctx)
    _metric_vars(ctx, "order", "classify", _classify)


@MISSION.check("STAGE III · File the appeals — `pardons`")
def _pardons_check(ctx):
    _function(ctx, "pardons")
    compare_cases(ctx, "pardons", [(EVIDENCE,), (DOCKET,), (DOCKET[:5],), ([],)], _pardons,
                  hint="Keep a record's id when arbiter_verdict(r) is True AND classify(r) is False, then sort the ids.")


@MISSION.check("STAGE III · Overturn the verdict — tribunal report")
def _report(ctx):
    for var in ("arbiter_precision", "arbiter_recall", "order_precision", "order_recall"):
        if not ctx.call_uses("print", var):
            raise Fail(f"Your report doesn't print `{var}`. The court only accepts numbers it can trace.",
                       hint="Use each variable inside the f-string, followed by :.2f")
    called = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "pardons"
                 for stmt in ctx.tree.body if not isinstance(stmt, ast.FunctionDef) for n in ast.walk(stmt))
    typed = any(isinstance(n, ast.Constant) and isinstance(n.value, str) and re.search(r"pardons=\d", n.value)
                for n in ast.walk(ctx.tree))
    if not called or typed:
        raise Fail("The pardon count must come from calling your pardons() function, not a typed number.",
                   hint="len(pardons(EVIDENCE)) counts the appeals. Put it (or a variable holding it) in the f-string.")
    if REPORT not in ctx.stdout.splitlines():
        got = ctx.stdout.strip().splitlines()
        raise Fail(f"The court expected {REPORT!r}" + (f" but got {got[-1]!r}." if got else ", and nothing was printed."),
                   hint="Each metric needs :.2f inside its braces, e.g. {order_recall:.2f}. Spaces around each |.")
