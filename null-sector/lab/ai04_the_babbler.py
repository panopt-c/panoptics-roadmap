"""THE LAB // AI04 THE BABBLER — a bigram character language model: counts, smoothing, temperature, sampling, NLL."""
from __future__ import annotations

import ast
import copy
import math
import random

from engine.mission import Fail, Mission

SEALED = {"numpy", "torch", "nltk", "scipy", "transformers"}
BOUNDARY = "."

NAMES = """ada cipher nova rust vex orin selka maro tavin ilsa kade brin oska lumen tarq veya juno rhee kestrel
mira soren adel tamsin yori calix nadia ezra lior thane wren isolde corin amara dax ferro galen halle ines
jarek kaia lusk morrow nyx oriel pell quill rook sable tycho una varo wynn xan yara zeph ember ash
coil flint harrow lark moth reed sorrel tamar vesper""".split()

MISSION = Mission(
    id="AI04",
    slug="ai04_the_babbler",
    title="THE BABBLER",
    concept="A bigram language model, sampling & temperature",
    enemy="BABBLE.loop",
    xp=380,
    par_seconds=50 * 60,
    tier=5,
    concepts=("nlp", "dicts", "statistics", "functions"),
    requires=(),
    timeout=10,
    run_as_main=False,
    assets={"monastery_names.txt": "\n".join(NAMES) + "\n"},
    enemy_art="""\
  ▄▀▀▄ ▄▀▀▄ ▄▀▀▄
  █ab█ █ba█ █ab█
  ▀▄▄▀ ▀▄▄▀ ▀▄▄▀
    ▀▄  ▀▄  ▀▄
  ▄▀▀▄ ▄▀▀▄ ▄▀▀▄
  █ba█ █ab█ █ba█
  ▀▄▄▀ ▀▄▄▀ ▀▄▄▀""",
    briefing="""\
The Monastery keeps a register of everyone who reached its gate: sixty-six names, one per line.
Somewhere below, **BABBLE.loop** chants the same syllable forever. It is a language model with
no sense of chance: it always picks the likeliest next letter, so it never stops saying *ana*.

MOTHER ADA lays out a grid of tally marks. "Every model that ever wrote a sentence did one thing:
predict the next symbol, then roll dice. Count pairs. Turn counts into probabilities. Roll
honest dice. Learn how hot to run them."

**Build a bigram language model that names new members of the Order, and break the loop.**
""",
    why="""\
A large language model is a vastly better version of this exact loop: a probability for every
possible next token, a sample, repeat. Training minimizes the **negative log-likelihood** of the
real next token; serving is all about **sampling**. Temperature, top-k and seeded generators live
in every inference stack:

```python
probs = softmax(logits / temperature)    # T < 1 sharper, T > 1 flatter
next_id = rng.choices(range(len(probs)), weights=probs)[0]
```

A bigram model is the baseline Karpathy's *makemore* starts from, and the smallest model where
you can see every number. Smoothing (why a model never assigns exactly zero), temperature (why
answers vary), seeds (why a test is reproducible) and perplexity (how a language model is scored)
all transfer directly to evaluating and serving real LLMs.
""",
    manual="""\
**1. Count what follows what.** Wrap each word in a boundary symbol `.` so the model also learns
how words start and end, then count adjacent pairs:

```python
counts = {}
for word in ["ada", "ash"]:
    chars = "." + word + "."              # ".ada."
    for a, b in zip(chars, chars[1:]):    # (.,a) (a,d) (d,a) (a,.)
        counts[(a, b)] = counts.get((a, b), 0) + 1
# {('.', 'a'): 2, ('a', 'd'): 1, ('d', 'a'): 1, ('a', '.'): 1, ('a', 's'): 1, ...}
```

The alphabet is `.` first, then every letter that appears, sorted: `[".", "a", "d", "h", "s"]`.

**2. Counts to probabilities, with smoothing.** P(next = c | prev) is the count of `(prev, c)`
over the total count of pairs starting with `prev`. A pair never seen would get probability 0,
and log(0) is minus infinity: one unseen pair makes a whole word "impossible". **Add-alpha
(Laplace) smoothing** pretends every pair was seen `alpha` extra times:

```python
V = len(alphabet)
total = sum(counts.get((prev, c), 0) for c in alphabet)
p = {c: (counts.get((prev, c), 0) + alpha) / (total + alpha * V) for c in alphabet}
```

*The common mistake:* adding `alpha` to the top but not `alpha * V` to the bottom. Then the
probabilities sum to more than 1, which is not a distribution. If `total + alpha * V` is 0 (an
unseen letter with `alpha = 0`), fall back to uniform: `1 / V` each.

**3. Temperature.** Raise each probability to the power `1 / T` and renormalize. `T = 1`
changes nothing, `T < 1` sharpens toward the favourite, `T > 1` flattens toward uniform.
(That's identical to `softmax(log p / T)`.) `T = 0` is the limit: **greedy**, all the mass on
the most likely symbol (ties: the first in alphabet order). Zero stays zero at any T.

**4. Sampling you can reproduce.** Draw one number `r = rng.random()` in [0, 1), then walk the
symbols in order adding up probabilities; return the first symbol where `r < running total`:

```python
r = rng.random()
total = 0.0
for symbol, p in probs.items():
    total += p
    if r < total:
        return symbol
```

Rounding can leave the final total a hair under 1, so after the loop return the last symbol with
`p > 0`. `rng.choices(list(probs), weights=list(probs.values()))[0]` gives the same answer.
Always pass the generator in (`rng = random.Random(seed)`): never use the global `random`, or
nobody can reproduce your run.

**5. Generate, then score.** Start from `.`, sample the next symbol, stop when you sample `.` or
hit `max_len`. To score a model, average `-log P(b | a)` over every pair of every padded word: the
**average negative log-likelihood**. Lower is better; `math.exp(nll)` is the **perplexity**.

**In the real world:** in PyTorch the same model is a `(V, V)` tensor of counts and
`torch.multinomial(probs, 1, generator=g)`; nanoGPT's `generate()` divides logits by temperature
exactly as in step 3. Hosted models fix more of this server-side: current Claude models such as
`claude-opus-5-5` reject a `temperature` parameter outright, so the knob you learn here is the one
you'll use when you serve your own models. Plain Python only in this mission.
""",
    starter='''
"""
==============================================================================
  LAB // AI04 THE BABBLER                              TARGET: BABBLE.loop
==============================================================================
  A character-level bigram language model, from tally marks to new names.
  The grader calls your functions on FRESH slices of the Monastery register
  (monastery_names.txt, next to this file) with seeded random generators.
  Plain Python only.
"""
import math
import random

BOUNDARY = "."


# -- OBJECTIVE 1: The alphabet and the tally ----------------------------------
# alphabet: "." first, then every distinct character of the words, sorted.
#   alphabet(["ada", "ash"])  ->  [".", "a", "d", "h", "s"]
# bigram_counts: pad each word as "." + word + "." and count adjacent pairs.
#   bigram_counts(["ada"])  ->  {(".", "a"): 1, ("a", "d"): 1, ("d", "a"): 1, ("a", "."): 1}
def alphabet(words):
    """Boundary symbol first, then the sorted distinct characters."""
    # TODO
    return None


def bigram_counts(words):
    """{(prev, next): count} over every padded word."""
    # TODO
    return None


# -- OBJECTIVE 2: CORRUPTED CODE ----------------------------------------------
# BABBLE.loop broke the probability table. next_probs must return a dict
# {symbol: P(symbol | prev)} for EVERY symbol of `alpha_list`, in that order,
# with add-alpha smoothing, summing to 1. If there is nothing to divide by
# (unseen prev and alpha == 0), return the uniform distribution.
#   p = (count(prev, c) + alpha) / (total(prev) + alpha * V)
def next_probs(counts, alpha_list, prev, alpha=1.0):
    """Smoothed next-symbol distribution after `prev`."""
    total = sum(counts.get((prev, c), 0) for c in alpha_list)
    return {c: (counts.get((prev, c), 0) + alpha) / total for c in alpha_list}


# -- OBJECTIVE 3: Temperature --------------------------------------------------
# Return a NEW dict with the same keys: p ** (1 / temperature), renormalized.
# temperature == 0: greedy, 1.0 on the most likely key (ties: first one),
# 0.0 elsewhere. Zero probabilities stay zero.
def apply_temperature(probs, temperature):
    """Sharpen (T < 1) or flatten (T > 1) a distribution."""
    # TODO
    return None


# -- OBJECTIVE 4: Honest dice --------------------------------------------------
# Draw ONE number r = rng.random(); walk the keys in order with a running
# total; return the first key where r < total (fallback: last key with p > 0).
def sample_next(probs, rng):
    """Sample one key from {key: probability} using the generator rng."""
    # TODO
    return None


# -- OBJECTIVE 5: Speak --------------------------------------------------------
# Start from ".", repeatedly: probs = next_probs(...), apply_temperature(...),
# sample_next(...). Stop when "." is sampled or the word has max_len
# characters. Return the word without boundary symbols.
def generate(counts, alpha_list, rng, temperature=1.0, alpha=1.0, max_len=20):
    """Sample one new name."""
    # TODO
    return None


# -- OBJECTIVE 6: Judge the model ------------------------------------------------
# Average of -log P(b | a) over every bigram of every padded word
# (use next_probs with the given alpha). No bigrams at all -> 0.0.
def avg_nll(words, counts, alpha_list, alpha=1.0):
    """Average negative log-likelihood per bigram (lower is better)."""
    # TODO
    return None


if __name__ == "__main__":
    with open("monastery_names.txt", encoding="utf-8") as fh:
        names = fh.read().split()
    symbols, table = alphabet(names), bigram_counts(names)
    rng = random.Random(7)
    for temperature in (0.0, 0.7, 1.0, 1.5):
        print(temperature, [generate(table, symbols, rng, temperature) for _ in range(5)])
    print("avg nll:", avg_nll(names, table, symbols))
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Before the Null Event, I watched people argue with machines that wrote poetry. Every one was this, scaled up."},
            {"speaker": "ada", "mood": "neutral",
             "text": "Count what follows what. Turn counts into odds. Roll dice. Why dice, {callsign}? Why not the likeliest letter?"},
            {"speaker": "cipher", "mood": "neutral",
             "text": "BABBLE.loop always picks the likeliest letter. Listen to it. That's your answer."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "ZeroDivisionError. Somewhere a letter has no followers and no smoothing. What should a model say about the unseen?"}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "The model fell over mid-word. The COMBAT LOG shows the letter that broke it."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "Rolling dice and dividing by zero. You'd be a terrible bookie."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Add the probabilities yourself. A distribution sums to one. Exactly one."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "Same seed, same dice. If your words differ from mine, you rolled more times than I did, or in another order."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "Ops note: the grader replays your rolls with a fixed seed. One extra rng.random() and the whole run shifts."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "New names nobody has worn yet, and the register still sounds like us. BABBLE.loop has gone quiet."},
            {"speaker": "ada", "mood": "neutral",
             "text": "Fourth page of the canon: a model is a probability, not a parrot. The temperature is a choice someone makes."},
            {"speaker": "cipher", "mood": "warm",
             "text": "Language model online, {callsign}. Perplexity logged. The dice are honest."},
        ],
    },
)


# ── reference (MOTHER ADA's) ─────────────────────────────────────────────────────

def _ref_alphabet(words):
    return [BOUNDARY] + sorted(set("".join(words)))


def _ref_counts(words):
    counts = {}
    for word in words:
        chars = BOUNDARY + word + BOUNDARY
        for pair in zip(chars, chars[1:]):
            counts[pair] = counts.get(pair, 0) + 1
    return counts


def _ref_probs(counts, alpha_list, prev, alpha=1.0):
    total = sum(counts.get((prev, c), 0) for c in alpha_list)
    denom = total + alpha * len(alpha_list)
    if denom == 0:
        return {c: 1 / len(alpha_list) for c in alpha_list}
    return {c: (counts.get((prev, c), 0) + alpha) / denom for c in alpha_list}


def _ref_temp(probs, temperature):
    if temperature == 0:
        best = max(probs, key=probs.get)
        return {k: (1.0 if k == best else 0.0) for k in probs}
    powered = {k: (p ** (1 / temperature) if p > 0 else 0.0) for k, p in probs.items()}
    z = sum(powered.values())
    return {k: v / z for k, v in powered.items()}


def _ref_sample(probs, rng):
    r = rng.random()
    total, last = 0.0, None
    for key, p in probs.items():
        total += p
        if p > 0:
            last = key
        if r < total:
            return key
    return last


def _ref_generate(counts, alpha_list, rng, temperature=1.0, alpha=1.0, max_len=20):
    out, prev = "", BOUNDARY
    while len(out) < max_len:
        ch = _ref_sample(_ref_temp(_ref_probs(counts, alpha_list, prev, alpha), temperature), rng)
        if ch == BOUNDARY:
            break
        out += ch
        prev = ch
    return out


def _ref_nll(words, counts, alpha_list, alpha=1.0):
    total, n = 0.0, 0
    for word in words:
        chars = BOUNDARY + word + BOUNDARY
        for a, b in zip(chars, chars[1:]):
            total -= math.log(_ref_probs(counts, alpha_list, a, alpha)[b])
            n += 1
    return total / n if n else 0.0


# ── grader helpers ────────────────────────────────────────────────────────────────

def _short(value, limit: int = 120) -> str:
    if isinstance(value, dict):
        value = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in value.items()}
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
                raise Fail(f"`import {name}` found (line {node.lineno}). This model is built from dicts and loops.",
                           hint="Plain Python: dict counts, math.log and a random.Random generator. The manual shows the torch version.")


def _fn(ctx, name: str):
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
    copies = [a if isinstance(a, random.Random) else copy.deepcopy(a) for a in args]
    try:
        out = fn(*copies, **kwargs)
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        if isinstance(exc, ZeroDivisionError):
            hint = hint or "Something divided by zero. With smoothing the denominator is total + alpha * V; if that's 0, return uniform."
        raise Fail(f"`{label}` raised {type(exc).__name__}: {exc}",
                   hint=hint or "Call it yourself on this input and read the traceback.")
    for original, passed in zip(args, copies):
        if not isinstance(original, random.Random) and original != passed:
            raise Fail(f"`{label}` changed its input in place.", hint="Build a new dict and return it; leave the argument untouched.")
    if out is None:
        raise Fail(f"`{label}` returned None: the TODO is still open.", hint="End the function with `return ...`.")
    return out


def _dist(label: str, got, want, hint: str) -> None:
    if not isinstance(got, dict):
        raise Fail(f"`{label}` returned a {type(got).__name__}, expected a dict like {_short(want, 80)}.", hint=hint)
    if list(got) != list(want):
        raise Fail(f"`{label}` has keys {_short(list(got), 80)}, expected {_short(list(want), 80)} (in that order).",
                   hint="One entry for EVERY symbol, in alphabet order: build it with a loop or comprehension over the alphabet.")
    bad = [k for k in want if not isinstance(got[k], (int, float)) or not math.isclose(got[k], want[k], abs_tol=1e-9)]
    if bad:
        raise Fail(f"`{label}` returned {_short(got)}, expected {_short(want)}.", hint=hint)


def _corpus(seed: int, n: int) -> list[str]:
    rng = random.Random(f"AI04:{seed}")
    return rng.sample(NAMES, n)


# ── firewall layers ──────────────────────────────────────────────────────────────

@MISSION.check("Tally — `alphabet` and `bigram_counts` with boundaries")
def _tally(ctx):
    fa, fc = _fn(ctx, "alphabet"), _fn(ctx, "bigram_counts")
    cases = [["ada", "ash"], ["ada"], [], ["x"], _corpus(1, 12), _corpus(2, 30)]
    for words in cases:
        label = f"alphabet({_short(words, 60)})"
        got = _call(fa, label, words)
        want = _ref_alphabet(words)
        if got != want:
            hint = "'.' first, then sorted(set of every character): [\".\"] + sorted(set(\"\".join(words)))."
            raise Fail(f"`{label}` returned {_short(got)}, expected {_short(want)}.", hint=hint)
        label = f"bigram_counts({_short(words, 60)})"
        got = _call(fc, label, words)
        want = _ref_counts(words)
        if not isinstance(got, dict) or got != want:
            hint = "Pad each word as '.' + word + '.', then count every (a, b) from zip(chars, chars[1:])."
            if isinstance(got, dict) and got and all(BOUNDARY not in k for k in got):
                hint = "No boundary pairs: pad each word with '.' on BOTH sides so the model learns starts and ends."
            elif isinstance(got, dict) and got and not all(isinstance(k, tuple) for k in got):
                hint = "Keys must be tuples like ('a', 'd'), not strings."
            raise Fail(f"`{label}` returned {_short(got)}, expected {_short(want)}.", hint=hint)


@MISSION.check("CORRUPTED `next_probs` repaired — smoothed, sums to 1")
def _probs(ctx):
    fn = _fn(ctx, "next_probs")
    words = _corpus(3, 25)
    counts, letters = _ref_counts(words), _ref_alphabet(words + ["qz"])
    rng = random.Random("AI04:probs")
    cases = [(".", 1.0), ("a", 1.0), ("e", 0.5), (rng.choice(letters[1:]), 2.0), ("a", 0.0), ("q", 1.0), ("z", 0.0)]
    for prev, alpha in cases:
        label = f"next_probs(counts, alphabet, {prev!r}, alpha={alpha})"
        got = _call(fn, label, counts, letters, prev, alpha=alpha)
        want = _ref_probs(counts, letters, prev, alpha)
        hint = "(count + alpha) / (total + alpha * V), with V = len(alphabet), so the values sum to 1."
        if isinstance(got, dict) and got and all(isinstance(v, (int, float)) for v in got.values()):
            s = sum(got.values())
            if not math.isclose(s, 1.0, abs_tol=1e-9):
                hint = (f"Your probabilities sum to {s:.4f}. Smoothing adds alpha to EVERY one of the V symbols, "
                        "so the denominator needs + alpha * V.")
        _dist(label, got, want, hint)


@MISSION.check("Temperature — sharpen, flatten, greedy at zero")
def _temperature(ctx):
    fn = _fn(ctx, "apply_temperature")
    rng = random.Random("AI04:temp")
    words = _corpus(4, 30)
    counts, letters = _ref_counts(words), _ref_alphabet(words)
    base = [_ref_probs(counts, letters, prev, a) for prev, a in ((".", 1.0), ("a", 0.0), ("o", 0.3))]
    base.append({"x": 0.25, "y": 0.5, "z": 0.25})
    base.append({"x": 0.4, "y": 0.4, "z": 0.2})
    for probs in base:
        for t in (1.0, 0.5, 2.0, round(rng.uniform(0.3, 1.8), 2), 0):
            label = f"apply_temperature({_short(probs, 60)}, {t})"
            got = _call(fn, label, probs, t)
            want = _ref_temp(probs, t)
            hint = "p ** (1 / T) for each value, then divide by the new total so they sum to 1."
            if t == 0:
                hint = "T = 0 is greedy: 1.0 on the largest probability (ties: the first key), 0.0 everywhere else."
            elif isinstance(got, dict) and list(got) == list(want):
                if all(math.isclose(got[k], probs[k] ** t / sum(v ** t for v in probs.values()), abs_tol=1e-9) for k in got) and t != 1:
                    hint = "You raised to the power T. It's 1 / T: a LOW temperature must SHARPEN the distribution."
                elif any(probs[k] == 0 and got[k] != 0 for k in got):
                    hint = "A zero probability must stay zero at any temperature."
            _dist(label, got, want, hint)


@MISSION.check("Honest dice — `sample_next` replays a seeded generator")
def _sample(ctx):
    fn = _fn(ctx, "sample_next")
    dists = [{"a": 0.5, "b": 0.3, "c": 0.2}, {".": 0.1, "x": 0.0, "y": 0.9}, {"only": 1.0},
             _ref_probs(_ref_counts(_corpus(5, 20)), _ref_alphabet(_corpus(5, 20)), "a", 0.5)]
    for i, probs in enumerate(dists):
        mine, ref = random.Random(500 + i), random.Random(500 + i)
        got_seq = [_call(fn, f"sample_next({_short(probs, 60)}, rng)", probs, mine) for _ in range(40)]
        want_seq = [_ref_sample(probs, ref) for _ in range(40)]
        if got_seq != want_seq:
            j = next(k for k, (g, w) in enumerate(zip(got_seq, want_seq)) if g != w)
            hint = ("One r = rng.random() per call; walk the keys IN ORDER with a running total; return the first key "
                    "where r < total.")
            if any(probs.get(g, 0) == 0 for g in got_seq):
                hint = "You returned a key with probability 0. Compare r < running total, and skip nothing else."
            raise Fail(f"With probs {_short(probs, 70)} and random.Random({500 + i}), draw #{j + 1} was "
                       f"{got_seq[j]!r}; expected {want_seq[j]!r}.", hint=hint)
    edge = {"a": 0.3, "b": 0.3, "c": 0.3999999999}

    class _High(random.Random):
        def random(self):
            return 0.99999999999

    got = _call(fn, "sample_next(probs summing to 0.9999999999, rng drawing 0.99999999999)", edge, _High(1))
    if got != "c":
        raise Fail(f"When rounding leaves the total a hair under 1 and r lands past it, `sample_next` returned {got!r}; expected 'c'.",
                   hint="After the loop, return the last key with p > 0 instead of falling off the end (None).")


@MISSION.check("Speak — `generate` names new members, reproducibly")
def _generate(ctx):
    fn = _fn(ctx, "generate")
    words = _corpus(6, 40)
    counts, letters = _ref_counts(words), _ref_alphabet(words)
    for seed, t, alpha, max_len in ((11, 1.0, 1.0, 20), (12, 0.7, 0.5, 20), (13, 1.6, 1.0, 6), (14, 0.0, 1.0, 12)):
        mine, ref = random.Random(seed), random.Random(seed)
        label = f"generate(counts, alphabet, random.Random({seed}), temperature={t}, alpha={alpha}, max_len={max_len})"
        got = [_call(fn, label, counts, letters, mine, temperature=t, alpha=alpha, max_len=max_len) for _ in range(6)]
        want = [_ref_generate(counts, letters, ref, t, alpha, max_len) for _ in range(6)]
        if got != want:
            hint = ("Start at '.', loop: next_probs -> apply_temperature -> sample_next; stop on '.' or at max_len; "
                    "one sample per character, nothing else touching rng.")
            if any(not isinstance(g, str) for g in got):
                hint = "Return the word as a string."
            elif any(BOUNDARY in g for g in got):
                hint = "Don't include the boundary '.' in the returned word: stop when you sample it."
            elif any(len(g) > max_len for g in got):
                hint = f"Words must stop at max_len ({max_len}) characters."
            raise Fail(f"`{label}` gave {_short(got, 90)}; expected {_short(want, 90)}.", hint=hint)


@MISSION.check("Judgement — `avg_nll` scores the model (lower is better)")
def _nll(ctx):
    fn = _fn(ctx, "avg_nll")
    train = _corpus(7, 40)
    counts, letters = _ref_counts(train), _ref_alphabet(NAMES)
    held_out = [w for w in NAMES if w not in train][:10]
    cases = [(train[:10], 1.0), (held_out, 1.0), (held_out, 0.1), (["ada"], 2.0), ([], 1.0)]
    for words, alpha in cases:
        label = f"avg_nll({_short(words, 60)}, counts, alphabet, alpha={alpha})"
        got = _call(fn, label, words, counts, letters, alpha=alpha)
        want = _ref_nll(words, counts, letters, alpha)
        if not isinstance(got, (int, float)) or not math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-12):
            hint = ("For every pair (a, b) of every padded word, add -math.log(next_probs(...)[b]); divide by the "
                    "number of pairs, boundaries included.")
            if not words:
                hint = "No words means no pairs: return 0.0 instead of dividing by zero."
            elif isinstance(got, (int, float)) and want and math.isclose(got, -want, rel_tol=1e-9):
                hint = "Wrong sign: the NEGATIVE log-likelihood is positive, since log of a probability is <= 0."
            raise Fail(f"`{label}` returned {_short(got)}, expected {want:.6f}.", hint=hint)
