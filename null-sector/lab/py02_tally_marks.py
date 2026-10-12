"""LAB PY02 // TALLY MARKS — Counter, defaultdict and frequencies: the first statistics of any dataset."""
from __future__ import annotations

import ast
import copy
import random
from collections import Counter

from engine.mission import Fail, Mission

MISSION = Mission(
    id="PY02",
    slug="py02_tally_marks",
    title="TALLY MARKS",
    concept="Counter, defaultdict & frequencies",
    enemy="TALLYWORM.exe",
    xp=120,
    par_seconds=25 * 60,
    tier=2,
    concepts=("dicts", "statistics", "nlp"),
    requires=(),
    timeout=10,
    run_as_main=False,
    enemy_art="""\
  ▄▀▄ ▄▀▄ ▄▀▄ ▄▀▄
 █ ▓ █ ▓ █ ▓ █ ▓ █▄
 ▀▄▀ ▀▄▀ ▀▄▀ ▀▄▀ ▀█
  ||| |||| || |   ▀
  ▀▀▀ ▀▀▀▀ ▀▀ ▀""",
    briefing="""\
Ada spreads the scorched pages of the canon across the Lab table. Half the words are ash. "Before
we rebuild a book," she says, "we learn which words it leaned on. Frequencies first. Meaning later."

**TALLYWORM.exe** lives in the Monastery's counters. It drops words, merges tallies by overwriting
them, and swears every class in the training pile is equally common. The old world believed numbers
like that and trained on them.

Counting is the first statistic of any dataset, and Python has two tools built for it.

**Rebuild the tallies with `Counter` and `defaultdict`, then turn the canon's words into a vocabulary.**
""",
    why="""\
Before training, you count. **Class balance** tells you whether 95% accuracy means anything (it
doesn't if 95% of labels are "no"). A **vocabulary** is a frequency table with a cut-off: every
tokenizer, from word-level to BPE, starts by counting.

```python
from collections import Counter
balance = Counter(y_train)              # Counter({'ok': 912, 'fraud': 88})
vocab = [w for w, n in Counter(tokens).most_common() if n >= 5]
by_user = defaultdict(list)             # group samples before a grouped split
```

Grouping with `defaultdict(list)` is how you keep all of one patient's scans in the same split, so
the model can't cheat by seeing that patient twice. `torchtext`, Hugging Face `tokenizers` and
scikit-learn's `CountVectorizer` all do this counting underneath.
""",
    manual="""\
**1. `Counter` counts anything iterable.** It's a dict whose values are counts, and a missing key
reads as 0 instead of crashing:

```python
from collections import Counter
c = Counter("the cat the hat".split())   # Counter({'the': 2, 'cat': 1, 'hat': 1})
c["the"]          # 2
c["dog"]          # 0   (no KeyError)
c.most_common(2)  # [('the', 2), ('cat', 1)]   ties keep first-seen order
sum(c.values())   # 4   total items counted
```

**2. Counters add.** `.update()` ADDS counts; `+` merges two counters:

```python
c.update(["cat", "cat"])          # c["cat"] is now 3
Counter(a=2) + Counter(a=1, b=5)  # Counter({'b': 5, 'a': 3})
```

**3. `defaultdict` makes missing keys for you.** Give it a *factory*: `list`, `int`, `set`:

```python
from collections import defaultdict
groups = defaultdict(list)
for name, sector in [("Ines", "grid"), ("Ren", "grid"), ("Okoye", "archive")]:
    groups[sector].append(name)   # no "if sector not in groups" needed
dict(groups)    # {'grid': ['Ines', 'Ren'], 'archive': ['Okoye']}
```

Pass the factory itself, `defaultdict(list)`, not `defaultdict(list())`.

**4. Frequencies are counts divided by the total.**

```python
labels = ["ok", "ok", "ok", "fraud"]
n = len(labels)
{k: v / n for k, v in Counter(labels).items()}   # {'ok': 0.75, 'fraud': 0.25}
```

**5. A vocabulary maps each kept word to an id.** Unknown words get a reserved id (here 0):

```python
vocab = {"<unk>": 0, "the": 1, "cat": 2}
[vocab.get(w, 0) for w in "the dog".split()]   # [1, 0]
```

**The common mistake: `dict.update` is not `Counter.update`.** On a plain dict, `update`
*replaces* values: `{"a": 2}.update({"a": 1})` leaves `{"a": 1}`. Your tally just lost two marks
without a single error. On a `Counter`, the same call gives 3.

**Also:** `text.split(" ")` splits on single spaces only, so double spaces produce empty-string
"words". `text.split()` with no argument splits on any run of whitespace.

**The library version:** `sklearn.feature_extraction.text.CountVectorizer(min_df=...)` builds a
vocabulary with a cut-off; `pandas.Series.value_counts(normalize=True)` is `class_balance`.
""",
    starter='''
"""
==============================================================================
  LAB PY02 // TALLY MARKS                            TARGET: TALLYWORM.exe
==============================================================================
  Counter and defaultdict live in the collections module (imported below).
  The grader calls every function with FRESH data. Save, then HACK.
"""
from collections import Counter, defaultdict

FRAGMENTS = [
    "the model learns what the data says",
    "the data says what the world did",
    "nobody read the data",
]


# -- OBJECTIVE 1 -------------------------------------------------------------
# word_counts(text) -> a Counter of the LOWERCASED words in text.
# Words are separated by any whitespace (spaces, tabs, newlines, doubles).
#   word_counts("The data the DATA")  ->  Counter({'the': 2, 'data': 2})
#   word_counts("")                   ->  Counter()
def word_counts(text):
    pass  # TODO


# -- OBJECTIVE 2 -------------------------------------------------------------
# class_balance(labels) -> {label: share of all labels}  (shares sum to 1.0)
#   class_balance(["ok", "ok", "ok", "fraud"])  ->  {'ok': 0.75, 'fraud': 0.25}
#   class_balance([])                           ->  {}
def class_balance(labels):
    pass  # TODO


# -- OBJECTIVE 3 -------------------------------------------------------------
# group_names(records, key) -> {value of record[key]: [names, in input order]}
#   recs = [{"name": "Ines", "sector": "grid"}, {"name": "Ren", "sector": "grid"},
#           {"name": "Okoye", "sector": "archive"}]
#   group_names(recs, "sector")  ->  {'grid': ['Ines', 'Ren'], 'archive': ['Okoye']}
# Tip: defaultdict(list). Returning the defaultdict itself is fine.
def group_names(records, key):
    pass  # TODO


# -- OBJECTIVE 4 -------------------------------------------------------------
# build_vocab(texts, min_count=2) -> {"<unk>": 0, word: id, ...}
#   * count the lowercased words of ALL texts together
#   * keep words seen at least min_count times
#   * ids 1, 2, 3... go to kept words from most to least frequent;
#     ties keep first-seen order (exactly what Counter.most_common() gives)
#   build_vocab(FRAGMENTS)  ->  {'<unk>': 0, 'the': 1, 'data': 2, 'what': 3, 'says': 4}
#   ('what' and 'says' both appear twice; 'what' was seen first, so it gets 3)
def build_vocab(texts, min_count=2):
    pass  # TODO


# -- OBJECTIVE 5 -------------------------------------------------------------
# encode(text, vocab) -> list of ids for the lowercased words of text.
# Words missing from vocab become 0 (the "<unk>" id). Never crash on them.
#   encode("The data LIED", build_vocab(FRAGMENTS))  ->  [1, 2, 0]
def encode(text, vocab):
    pass  # TODO


# -- OBJECTIVE 6 // CORRUPTED CODE -------------------------------------------
# merge_tallies(a, b) should return a NEW Counter where each key's count is
# a[key] + b[key], and leave a and b untouched.
# TALLYWORM rewrote it. It runs. Two scribes' tallies go in; marks vanish.
def merge_tallies(a, b):
    total = dict(a)
    total.update(b)
    return total
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Here is what's left of the canon. Before we read a word of it, tell me which words it used most."},
            {"speaker": "ada", "mood": "smirk",
             "text": "Why count first? Because a model learns frequencies long before it learns meaning. So should you."},
            {"speaker": "rust", "mood": "neutral",
             "text": "TALLYWORM's been in my trade books too. Keeps 'merging' my stock into less stock. Squash it, I'll owe you."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "KeyError on a plain dict means you read a key before it existed. Counter and defaultdict exist for that."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "TypeError: 'list' object is not callable? You wrote defaultdict(list()). Pass the factory, not a list."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "ZeroDivisionError means an empty input reached a division. Decide what an empty tally should return."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Compare your counts to the input by hand. Which word did you miss, and which did you invent?"}],
            [{"speaker": "cipher", "mood": "smirk",
              "text": "If an empty string shows up in your Counter, you split on ' '. split() with no argument handles any whitespace."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "My ledger rule: tallies only go up when you add. If yours went down, something overwrote it."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "The canon leaned on 'data' and 'the'. Honest words. Now we know what this book was made of."},
            {"speaker": "ada", "mood": "neutral",
             "text": "The old world never checked its class balance. It reported accuracy on piles that were mostly one answer."},
            {"speaker": "rust", "mood": "smirk",
             "text": "Stock's back where it should be. Undercroft's open to you, {callsign}. Don't make me count twice."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

WORDS = ("the", "data", "model", "learns", "world", "signal", "noise", "core", "order", "ash",
         "light", "code", "ledger", "truth", "says", "what", "nobody", "read", "loss", "rain")
NAMES = ("Ines", "Tomo", "Okoye", "Ren", "Mira", "Kael", "Sora", "Bex", "Juno", "Ash", "Pell",
         "Vik", "Ola", "Dov", "Yara", "Tam")
SECTORS = ("foundry", "grid", "archive", "dead-zone", "undercroft")


def _short(value, limit: int = 140) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _func(ctx, name: str):
    if name not in ctx.ns:
        if ctx.crashed and any(isinstance(n, ast.FunctionDef) and n.name == name for n in ctx.tree.body):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.", hint=f"Keep the starter's  def {name}(...):  line.")
    if not callable(ctx.ns[name]):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return ctx.ns[name]


def _call(ctx, name: str, *args, **kwargs):
    """Call the player's function on deep copies; a crash becomes a failed layer that shows the input."""
    fn = _func(ctx, name)
    shown = ", ".join([_short(a, 80) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()])
    try:
        result = fn(*copy.deepcopy(args), **copy.deepcopy(kwargs))
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        hint = "Call it yourself on this input and read the error."
        if isinstance(exc, KeyError):
            hint = ("A plain dict raised KeyError for a key it hasn't seen yet. Use Counter, defaultdict, "
                    "or dict.get(key, default).")
        elif isinstance(exc, ZeroDivisionError):
            hint = "An empty input reached a division. Return the empty result before dividing."
        elif isinstance(exc, TypeError) and "not callable" in str(exc):
            hint = "defaultdict wants the factory itself: defaultdict(list), not defaultdict(list())."
        raise Fail(f"`{name}({shown})` crashed: {type(exc).__name__}: {exc}", hint=hint)
    if result is None:
        raise Fail(f"`{name}({shown})` returned None.", hint="Finish the TODO: the function needs a return.")
    return result, shown


def _text(rng: random.Random, n: int) -> str:
    seps = (" ", " ", " ", "  ", "\t", "\n")
    words = [rng.choice(WORDS) for _ in range(n)]
    words = [w.upper() if rng.random() < 0.2 else w.capitalize() if rng.random() < 0.2 else w for w in words]
    out = ""
    for w in words:
        out += w + rng.choice(seps)
    return rng.choice(("", " ", "\n")) + out


def _ref_counts(text: str) -> Counter:
    return Counter(text.lower().split())


def _ref_vocab(texts, min_count=2) -> dict:
    counts = Counter()
    for t in texts:
        counts.update(t.lower().split())
    kept = [w for w, n in counts.most_common() if n >= min_count]
    return {"<unk>": 0, **{w: i for i, w in enumerate(kept, start=1)}}


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Tally — `word_counts` returns a Counter of lowercase words")
def _tally(ctx):
    rng = random.Random("PY02:tally")
    for text in (_text(rng, 18), "The data the DATA", "solo", "", "  \t \n "):
        got, shown = _call(ctx, "word_counts", text)
        expected = _ref_counts(text)
        if not isinstance(got, Counter):
            raise Fail(f"`word_counts({shown})` returned {type(got).__name__}; it should return a Counter.",
                       hint="from collections import Counter  ->  return Counter(<the words>)")
        if got != expected:
            hint = "Lowercase the whole text, then split on whitespace:  text.lower().split()"
            if "" in got:
                hint = ("Your Counter has an empty-string word: split(' ') splits on single spaces only. "
                        "Use split() with no argument.")
            elif any(w != w.lower() for w in got):
                hint = "'The' and 'the' are the same word here. Lowercase before counting."
            raise Fail(f"`word_counts({shown})` returned {_short(got)}, expected {_short(expected)}.", hint=hint)


@MISSION.check("Balance — `class_balance` gives each label's share")
def _balance(ctx):
    rng = random.Random("PY02:balance")
    skewed = ["ok"] * rng.randint(12, 20) + ["fraud"] * rng.randint(1, 3)
    rng.shuffle(skewed)
    cases = (skewed, [rng.choice(("cat", "dog", "bird")) for _ in range(13)], ["only"], [3, 1, 3, 3, 2, 1], [])
    for labels in cases:
        got, shown = _call(ctx, "class_balance", labels)
        n = len(labels)
        expected = {k: v / n for k, v in Counter(labels).items()}
        if not isinstance(got, dict):
            raise Fail(f"`class_balance({shown})` returned {type(got).__name__}; it should return a dict.",
                       hint="Build {label: count / total} from a Counter of the labels.")
        if set(got) != set(expected):
            raise Fail(f"`class_balance({shown})` has keys {_short(sorted(got, key=str))}, expected "
                       f"{_short(sorted(expected, key=str))}.", hint="One key per distinct label, nothing else.")
        bad = [k for k in expected if not isinstance(got[k], (int, float)) or abs(got[k] - expected[k]) > 1e-9]
        if bad:
            k = bad[0]
            hint = "A share is count / TOTAL number of labels:  {k: v / len(labels) for k, v in counts.items()}"
            if isinstance(got[k], int) and got[k] == Counter(labels)[k]:
                hint = "Those are raw counts. Divide each by the total number of labels to get a share."
            raise Fail(f"`class_balance({shown})`[{k!r}] is {got[k]!r}, expected {expected[k]:.6g}.", hint=hint)


@MISSION.check("Muster — `group_names` groups records under any key")
def _muster(ctx):
    rng = random.Random("PY02:muster")

    def records(n):
        return [{"name": name, "sector": rng.choice(SECTORS), "shift": rng.choice(("dawn", "dusk", "night"))}
                for name in rng.sample(NAMES, n)]

    for recs, key in ((records(11), "sector"), (records(9), "shift"), (records(1), "sector"), ([], "sector")):
        got, shown = _call(ctx, "group_names", recs, key)
        expected: dict = {}
        for r in recs:
            expected.setdefault(r[key], []).append(r["name"])
        if not isinstance(got, dict):
            raise Fail(f"`group_names({shown})` returned {type(got).__name__}; it should return a dict.",
                       hint="groups = defaultdict(list), then groups[r[key]].append(r['name']) for each record.")
        if dict(got) != expected:
            hint = "One list per distinct value of record[key], holding the names in input order."
            if any(isinstance(v, str) for v in got.values()):
                hint = ("Each value must be a LIST of every matching name. Assigning groups[k] = name keeps only "
                        "the last one; append to a list instead.")
            elif key != "sector" and set(got) <= set(SECTORS):
                hint = "Group by the `key` parameter, not by a hard-coded field."
            raise Fail(f"`group_names(..., {key!r})` returned {_short(dict(got))}, expected {_short(expected)}.",
                       hint=hint)


@MISSION.check("Lexicon — `build_vocab` keeps words seen min_count times")
def _lexicon(ctx):
    rng = random.Random("PY02:lexicon")
    fragments = [_text(rng, rng.randint(4, 12)) for _ in range(6)]
    cases = ((fragments, {}), (fragments, {"min_count": 4}), (fragments, {"min_count": 1}),
             (["Ash ash ASH", "rain"], {}), ([], {}))
    for texts, kwargs in cases:
        got, shown = _call(ctx, "build_vocab", texts, **kwargs)
        expected = _ref_vocab(texts, **kwargs)
        if not isinstance(got, dict):
            raise Fail(f"`build_vocab` returned {type(got).__name__}; it should return a dict.",
                       hint="Start from {'<unk>': 0} and give each kept word the next id.")
        if got.get("<unk>") != 0:
            raise Fail(f"`build_vocab({shown})` has no '<unk>': 0 entry.",
                       hint="Id 0 is reserved for unknown words, even when no word is kept.")
        if got != expected:
            hint = ("Count with ONE Counter across all texts, keep words with count >= min_count, and number them "
                    "1, 2, 3... in most_common() order.")
            missing = [w for w in expected if w not in got]
            extra = [w for w in got if w not in expected]
            if extra and not missing:
                hint = f"{extra[0]!r} appears fewer than min_count times. Use the min_count parameter, with >=."
            elif missing and not extra:
                hint = f"{missing[0]!r} appears min_count times or more (>= keeps the edge), so it belongs in."
            elif set(got) == set(expected):
                hint = "Right words, wrong ids. Ids follow Counter.most_common() order, starting at 1."
            raise Fail(f"`build_vocab(..., {kwargs or 'min_count=2'})` returned {_short(got)}, "
                       f"expected {_short(expected)}.", hint=hint)


@MISSION.check("Encoding — `encode` sends unknown words to <unk>")
def _encoding(ctx):
    rng = random.Random("PY02:encode")
    vocab = _ref_vocab([_text(rng, 30)], min_count=2)
    for text in (_text(rng, 9), "zzyzx QUILL the", "", "THE " * 3):
        got, shown = _call(ctx, "encode", text, vocab)
        expected = [vocab.get(w, 0) for w in text.lower().split()]
        if got != expected:
            raise Fail(f"`encode({_short(text, 60)}, vocab)` returned {_short(got)}, expected {_short(expected)}.",
                       hint="One id per lowercased word; vocab.get(word, 0) turns unknown words into 0.")


@MISSION.check("Purge the worm — corrupted `merge_tallies` repaired")
def _merge(ctx):
    rng = random.Random("PY02:merge")
    for _ in range(3):
        a = Counter({w: rng.randint(1, 9) for w in rng.sample(WORDS, 6)})
        b = Counter({w: rng.randint(1, 9) for w in rng.sample(WORDS, 6)})
        a_before, b_before = Counter(a), Counter(b)
        fn = _func(ctx, "merge_tallies")
        shown = f"{_short(dict(a), 60)}, {_short(dict(b), 60)}"
        try:
            got = fn(a, b)
        except Exception as exc:  # noqa: BLE001
            raise Fail(f"`merge_tallies({shown})` crashed: {type(exc).__name__}: {exc}",
                       hint="Call it yourself on two Counters and read the error.")
        expected = a_before + b_before
        if not isinstance(got, dict) or dict(got) != dict(expected):
            shared = next((k for k in a_before if k in b_before), None)
            hint = "dict.update REPLACES values. Start from Counter(a) and use Counter's update, or Counter(a) + b."
            if shared and isinstance(got, dict) and got.get(shared) == b_before[shared]:
                hint = (f"{shared!r} came back as {b_before[shared]} (b's count) instead of "
                        f"{a_before[shared]} + {b_before[shared]}. dict.update replaced it. Counter.update adds.")
            raise Fail(f"`merge_tallies` returned {_short(dict(got) if isinstance(got, dict) else got)}, "
                       f"expected {_short(dict(expected))}.", hint=hint)
        if a != a_before or b != b_before:
            raise Fail("`merge_tallies` changed the tallies it was given. It must return a NEW Counter.",
                       hint="a.update(b) edits a in place. Copy first:  total = Counter(a); total.update(b)")
