"""THE LAB // AI01 SHARDS OF SPEECH — character tokenization, BPE merges, encode/decode round trip."""
from __future__ import annotations

import ast
import copy
import random

from engine.mission import Fail, Mission

FORBIDDEN = {"tiktoken", "tokenizers", "sentencepiece", "transformers"}

MISSION = Mission(
    id="AI01",
    slug="ai01_shards_of_speech",
    title="SHARDS OF SPEECH",
    concept="Tokenization & BPE merges",
    enemy="SHATTERGLYPH.tok",
    xp=380,
    par_seconds=50 * 60,
    tier=5,
    concepts=("nlp", "dicts", "loops", "functions"),
    requires=(),
    timeout=10,
    run_as_main=False,
    enemy_art="""\
  ▄▀▄  ▄▀▀▄ ▄▀▄
 █ ▓ ▀█ ▓▓ █▀ ▓ █
  ▀▄ ▄▀▀▄▄▀▀▄ ▄▀
 ▓ ▀█ ▓  ▐▌  ▓ █▀ ▓
  ▄▀ ▀▄▄▀▀▄▄▀ ▀▄
 █ ▓ ▄█ ▓▓ █▄ ▓ █
  ▀▄▀  ▀▄▄▀ ▀▄▀""",
    briefing="""\
The Scriptorium Lab smells of solder and old paper. MOTHER ADA sets a scorched drive on the bench:
the Order's language canon, or what the Null Event left of it.

"The old machines never read words," she says. "They read shards. Before you ask a machine to
speak, learn how a sentence breaks."

Inside the drive, **SHATTERGLYPH.tok** has smashed every sentence into loose characters and
forgotten how to put them back. The archive is a floor of broken glass.

**Build a tokenizer that learns its own shards with byte-pair encoding, and prove every sentence
survives the round trip.**
""",
    why="""\
Every language model starts here. Before a model sees your prompt, a **tokenizer** turns the text
into integer ids, and the model only ever predicts the next id. GPT-2 and Llama use byte-level
**BPE**; most modern LLMs use a close relative. Tokens are also your budget: context windows and
API bills are counted in them, so you measure before you send:

```python
import anthropic

client = anthropic.Anthropic()
count = client.messages.count_tokens(
    model="claude-opus-5-5",
    messages=[{"role": "user", "content": prompt}],
)
print(count.input_tokens)
```

Tokenization explains strange model behaviour: why a model miscounts the letters in a word (it
sees shards, not letters), why numbers split oddly, why some languages cost more tokens per
sentence. And a tokenizer whose `decode(encode(text))` isn't exactly `text` silently corrupts
every training example that passes through it.
""",
    manual="""\
**1. Characters become ids.** A vocabulary is a dict from symbol to integer. Sort the unique
characters so the same corpus always gives the same ids:

```python
corpus = "abba cab"
vocab = {ch: i for i, ch in enumerate(sorted(set(corpus)))}
# {' ': 0, 'a': 1, 'b': 2, 'c': 3}
ids = [vocab[ch] for ch in "cab"]            # [3, 1, 2]
inverse = {i: ch for ch, i in vocab.items()}
"".join(inverse[i] for i in ids)             # 'cab'
```

**2. Count neighbours.** BPE looks at every adjacent pair. `zip(ids, ids[1:])` walks them:

```python
ids = [1, 2, 1, 2, 3]
counts = {}
for pair in zip(ids, ids[1:]):               # (1,2) (2,1) (1,2) (2,3)
    counts[pair] = counts.get(pair, 0) + 1
# {(1, 2): 2, (2, 1): 1, (2, 3): 1}
```

**3. Pick the most frequent pair.** `max(d, key=d.get)` returns the key with the largest value.
Dicts remember insertion order and `max` keeps the FIRST maximum it meets, so ties go to the pair
seen earliest in the sequence. That rule makes training deterministic:

```python
best = max(counts, key=counts.get)           # (1, 2)
```

**4. Merge it everywhere.** Walk left to right. When the pair starts at position `i`, emit the
new id and jump **two** places; otherwise copy one id and step one place:

```python
def merge(ids, pair, new_id):
    out, i = [], 0
    while i < len(ids):
        if i + 1 < len(ids) and (ids[i], ids[i + 1]) == pair:
            out.append(new_id)
            i += 2
        else:
            out.append(ids[i])
            i += 1
    return out

merge([5, 6, 5, 6, 7], (5, 6), 9)            # [9, 9, 7]
```

*The common mistake:* stepping one place after a match. On `[1, 1, 1]` with pair `(1, 1)` the
correct answer is `[N, 1]`: the middle `1` is used once, never twice. Also guard `i + 1`: the
last position has no right neighbour.

**5. Training is that loop, repeated.** Each round: count pairs, pick the best, give it the next
free id (`len(vocab)`, then `len(vocab) + 1`, ...), merge, and record `merges[pair] = new_id`.
Stop early when fewer than two ids remain. A new id can pair with an old one, so shards grow into
syllables and syllables into words:

```python
merges = {}
for step in range(num_merges):
    counts = pair_counts(ids)
    if not counts:
        break
    pair = most_frequent_pair(ids)
    new_id = len(vocab) + step
    ids = merge(ids, pair, new_id)
    merges[pair] = new_id
```

**6. Encode new text, then decode it back.** Encode characters, then replay the learned merges
**in the order they were learned** (dicts keep that order). To decode, build a table from id to
text: characters first, then each merge in order, `table[new] = table[a] + table[b]`:

```python
table = {i: ch for ch, i in vocab.items()}
for (a, b), new_id in merges.items():
    table[new_id] = table[a] + table[b]
"".join(table[i] for i in ids)
```

**In the real world** you rarely train a tokenizer by hand, but you will debug one. Hugging Face
`tokenizers` does exactly this, fast and byte-level (256 base bytes, so no character is ever
unknown):

```python
from tokenizers import Tokenizer, models, pre_tokenizers, trainers

tok = Tokenizer(models.BPE(unk_token="[UNK]"))
tok.pre_tokenizer = pre_tokenizers.Whitespace()
tok.train_from_iterator(lines, trainer=trainers.BpeTrainer(vocab_size=500, special_tokens=["[UNK]"]))
ids = tok.encode("the order remembers").ids
assert tok.decode(ids).replace(" ", "") == "theorderremembers"
```

Here you build it yourself, so tokenizer libraries are sealed.
""",
    starter='''
"""
==============================================================================
  LAB // AI01 SHARDS OF SPEECH                     TARGET: SHATTERGLYPH.tok
==============================================================================
  Teach the canon to break into shards and come back whole.
  The grader calls your functions on FRESH text it generates, and checks
  them against MOTHER ADA's reference tokenizer. Plain Python only:
  tokenizer libraries (tiktoken, tokenizers, sentencepiece) are sealed.
"""


# -- OBJECTIVE 1: The alphabet ------------------------------------------------
# Return a dict mapping every distinct character of `corpus` to an id:
# the characters SORTED, numbered 0, 1, 2, ...
#   char_vocab("abba cab")  ->  {' ': 0, 'a': 1, 'b': 2, 'c': 3}
#   char_vocab("")          ->  {}
def char_vocab(corpus):
    """Sorted unique characters of corpus -> consecutive integer ids."""
    # TODO
    return None


# -- OBJECTIVE 2: Characters to ids and back ----------------------------------
# encode: each character of `text` -> its id.   decode: ids -> the text.
#   vocab = char_vocab("abba cab")
#   encode("cab", vocab)        ->  [3, 1, 2]
#   decode([3, 1, 2], vocab)    ->  "cab"
# Example of inverting a dict:  inverse = {i: ch for ch, i in vocab.items()}
def encode(text, vocab):
    """Text -> list of character ids."""
    # TODO
    return None


def decode(ids, vocab):
    """List of character ids -> text."""
    # TODO
    return None


# -- OBJECTIVE 3: Count neighbouring pairs -----------------------------------
# Count every ADJACENT pair of ids (pairs overlap: [7, 7, 7] has (7, 7) twice).
#   pair_counts([1, 2, 1, 2, 3])  ->  {(1, 2): 2, (2, 1): 1, (2, 3): 1}
#   pair_counts([4])              ->  {}
# Example:  for pair in zip(ids, ids[1:]): ...
def pair_counts(ids):
    """Dict of (left, right) -> how many times that pair appears side by side."""
    # TODO
    return None


# -- OBJECTIVE 4: Choose the merge -------------------------------------------
# Return the most frequent adjacent pair. On a tie, the pair that appears
# FIRST in the sequence wins. Fewer than two ids -> None.
#   most_frequent_pair([8, 9, 0, 1, 8, 9, 0, 1])  ->  (8, 9)
# Example:  best = max(counts, key=counts.get)   # keeps the first maximum
def most_frequent_pair(ids):
    """The pair BPE merges next (ties: earliest first), or None."""
    # TODO
    return None


# -- OBJECTIVE 5: CORRUPTED CODE ----------------------------------------------
# SHATTERGLYPH rewrote the merge. It should replace every non-overlapping
# occurrence of `pair`, left to right, with `new_id`, and return a NEW list.
#   merge([5, 6, 5, 6, 7], (5, 6), 9)  ->  [9, 9, 7]
#   merge([1, 1, 1], (1, 1), 4)        ->  [4, 1]     (not [4, 4]!)
# It crashes on some inputs and double-counts on others. Find both bugs.
def merge(ids, pair, new_id):
    """Replace each occurrence of pair in ids with new_id."""
    out = []
    i = 0
    while i < len(ids):
        if ids[i] == pair[0] and ids[i + 1] == pair[1]:
            out.append(new_id)
            i += 1
        else:
            out.append(ids[i])
            i += 1
    return out


# -- OBJECTIVE 6: Learn the shards --------------------------------------------
# Train BPE on `text` with `num_merges` rounds. Start from encode(text, vocab).
# Round k (0, 1, 2, ...): find the most frequent pair, give it the id
# len(vocab) + k, merge it, record merges[pair] = new_id.
# Stop early if there are no pairs left. Return the merges dict.
#   vocab = char_vocab("abab")         # {'a': 0, 'b': 1}
#   train_bpe("abab", vocab, 5)  ->  {(0, 1): 2, (2, 2): 3}
def train_bpe(text, vocab, num_merges):
    """Learn up to num_merges BPE merges; returns {pair: new_id} in learning order."""
    # TODO
    return None


# -- OBJECTIVE 7: Speak in shards ---------------------------------------------
# bpe_encode: encode the characters, then apply every learned merge IN THE
# ORDER IT WAS LEARNED.  bpe_decode: turn those ids back into the exact text.
#   merges = train_bpe("abab", vocab, 5)
#   bpe_encode("ababa", vocab, merges)   ->  [3, 0]
#   bpe_decode([3, 0], vocab, merges)    ->  "ababa"
# Example: table = {i: ch for ch, i in vocab.items()}
#          for (a, b), new_id in merges.items(): table[new_id] = table[a] + table[b]
def bpe_encode(text, vocab, merges):
    """Text -> BPE token ids."""
    # TODO
    return None


def bpe_decode(ids, vocab, merges):
    """BPE token ids -> the original text."""
    # TODO
    return None
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Before the Null Event I fed text to machines for a living. Not one of them ever saw a word."},
            {"speaker": "ada", "mood": "neutral",
             "text": "They saw shards. Ids. So tell me, {callsign}: why would a machine learn its own alphabet instead of using ours?"},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Hint from the visor: frequent pairs become new symbols. Shorter sequences, same meaning."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "An IndexError at the end of a list usually means you asked for a right neighbour that isn't there."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Your tokenizer cracked mid-sentence. The COMBAT LOG has the input that broke it."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "Shattered glass, shattered code. At least the glass doesn't throw tracebacks."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Run the failing input by hand on paper. Three ones, one pair. How many times can the middle one be used?"}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "Order matters. Merges are replayed in the order they were learned, or the shards don't fit."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader writes fresh sentences each time. Only a real tokenizer survives that."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Every sentence back, byte for byte. SHATTERGLYPH has nothing left to break."},
            {"speaker": "ada", "mood": "neutral",
             "text": "First page of the canon restored: a model's world is made of shards. Next, we give the shards meaning."},
            {"speaker": "cipher", "mood": "warm",
             "text": "Logged: tokenizer online. Compression ratio looking healthy, {callsign}."},
        ],
    },
)


# ── reference tokenizer (MOTHER ADA's) ────────────────────────────────────────────

def _ref_vocab(corpus):
    return {ch: i for i, ch in enumerate(sorted(set(corpus)))}


def _ref_encode(text, vocab):
    return [vocab[ch] for ch in text]


def _ref_decode(ids, vocab):
    inverse = {i: ch for ch, i in vocab.items()}
    return "".join(inverse[i] for i in ids)


def _ref_pairs(ids):
    counts = {}
    for pair in zip(ids, ids[1:]):
        counts[pair] = counts.get(pair, 0) + 1
    return counts


def _ref_best(ids):
    counts = _ref_pairs(ids)
    return max(counts, key=counts.get) if counts else None


def _ref_merge(ids, pair, new_id):
    out, i = [], 0
    while i < len(ids):
        if i + 1 < len(ids) and ids[i] == pair[0] and ids[i + 1] == pair[1]:
            out.append(new_id)
            i += 2
        else:
            out.append(ids[i])
            i += 1
    return out


def _ref_train(text, vocab, num_merges):
    ids = _ref_encode(text, vocab)
    merges = {}
    for step in range(num_merges):
        pair = _ref_best(ids)
        if pair is None:
            break
        new_id = len(vocab) + step
        ids = _ref_merge(ids, pair, new_id)
        merges[pair] = new_id
    return merges


def _ref_bpe_encode(text, vocab, merges):
    ids = _ref_encode(text, vocab)
    for pair, new_id in merges.items():
        ids = _ref_merge(ids, pair, new_id)
    return ids


def _ref_bpe_decode(ids, vocab, merges):
    table = {i: ch for ch, i in vocab.items()}
    for (a, b), new_id in merges.items():
        table[new_id] = table[a] + table[b]
    return "".join(table[i] for i in ids)


# ── fresh text from the burned canon ────────────────────────────────────────────

_SYLLABLES = ("the ", "or", "der ", "an", "ka", "ra", "th", "en", "in", "on", "e", "s", "t", " ", "lo", "st ")


def _text(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(_SYLLABLES) for _ in range(n)).strip() or "order"


# ── grader helpers ────────────────────────────────────────────────────────────────

def _short(value, limit: int = 110) -> str:
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
            if name.split(".")[0] in FORBIDDEN:
                raise Fail(f"`import {name}` found. Tokenizer libraries are sealed in this mission.",
                           hint="Build it from dicts, lists and loops: that's the lesson. The manual shows the library version.")


def _fn(ctx, name: str):
    _sealed(ctx)
    if name not in ctx.ns:
        if ctx.crashed:
            raise Fail(f"`{name}` doesn't exist: your file crashed before defining it. Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.",
                   hint=f"Keep the starter's  def {name}(...):  line. Spelling and underscores must match.")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return fn


def _call(fn, label: str, *args, hint: str = ""):
    try:
        result = fn(*copy.deepcopy(args))
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        if isinstance(exc, IndexError):
            hint = hint or "Something read past the end of a list. Guard the last position: it has no right neighbour."
        raise Fail(f"`{label}` raised {type(exc).__name__}: {exc}",
                   hint=hint or "Call it yourself on this exact input and read the traceback.")
    if result is None:
        raise Fail(f"`{label}` returned None: the TODO is still open.",
                   hint="Every path through the function must end in a `return` with the answer.")
    return result


def _expect(label: str, got, expected, hint: str = "") -> None:
    if got != expected or type(got) is not type(expected):
        shown = _short(got)
        if type(got) is not type(expected):
            shown += f" (a {type(got).__name__}, expected a {type(expected).__name__})"
        raise Fail(f"`{label}` returned {shown}, expected {_short(expected)}.", hint=hint)


# ── firewall layers ──────────────────────────────────────────────────────────────

@MISSION.check("Alphabet — `char_vocab` numbers every character")
def _vocab(ctx):
    fn = _fn(ctx, "char_vocab")
    rng = random.Random("AI01:vocab")
    cases = ["abba cab", "", "zzz", _text(rng, 14), _text(rng, 30) + "!?"]
    for corpus in cases:
        got = _call(fn, f"char_vocab({corpus!r})", corpus)
        _expect(f"char_vocab({_short(corpus, 50)})", got, _ref_vocab(corpus),
                hint="Sort the unique characters (sorted(set(corpus))), then number them with enumerate from 0. "
                     "Same corpus, same ids, every time.")


@MISSION.check("Round trip — `encode` / `decode` characters")
def _chars(ctx):
    enc, dec = _fn(ctx, "encode"), _fn(ctx, "decode")
    rng = random.Random("AI01:chars")
    for n in (6, 18, 1):
        corpus = _text(rng, 40)
        vocab = _ref_vocab(corpus)
        text = corpus[: max(1, n * 2)]
        ids = _call(enc, f"encode({text!r}, vocab)", text, vocab)
        _expect(f"encode({_short(text, 50)}, vocab)", ids, _ref_encode(text, vocab),
                hint="One id per character, in order: [vocab[ch] for ch in text].")
        back = _call(dec, f"decode({_short(ids, 50)}, vocab)", ids, vocab)
        _expect(f"decode({_short(ids, 50)}, vocab)", back, text,
                hint="Invert the vocab ({i: ch for ch, i in vocab.items()}) and join the characters with \"\".join(...).")
    vocab = _ref_vocab("abc")
    _expect("encode('', vocab)", _call(enc, "encode('', vocab)", "", vocab), [],
            hint="Empty text has no characters, so no ids: return [].")


@MISSION.check("Pair census — `pair_counts`")
def _pairs(ctx):
    fn = _fn(ctx, "pair_counts")
    rng = random.Random("AI01:pairs")
    cases = [[1, 2, 1, 2, 3], [7, 7, 7], [4], []]
    cases += [[rng.randrange(5) for _ in range(rng.randrange(8, 30))] for _ in range(4)]
    for ids in cases:
        got = _call(fn, f"pair_counts({_short(ids, 60)})", ids,
                    hint="Fewer than two ids means no pairs at all: the answer is an empty dict.")
        hint = "Pairs overlap: zip(ids, ids[1:]) yields every neighbouring pair, and each one adds 1."
        if len(ids) < 2:
            hint = "Fewer than two ids means no pairs at all: return an empty dict."
        if ids == [7, 7, 7] and got != {(7, 7): 2}:
            hint = "[7, 7, 7] has two neighbouring pairs: positions 0-1 and 1-2. Counting overlaps is right HERE (merging is different)."
        if isinstance(got, dict) and got and not all(isinstance(k, tuple) for k in got):
            hint = "Keys must be tuples like (1, 2), so they can be used as dict keys and compared with pairs later."
        _expect(f"pair_counts({_short(ids, 60)})", got, _ref_pairs(ids), hint=hint)


@MISSION.check("The chosen pair — `most_frequent_pair` (ties: first seen)")
def _best(ctx):
    fn = _fn(ctx, "most_frequent_pair")
    rng = random.Random("AI01:best")
    cases = [[8, 9, 0, 1, 8, 9, 0, 1], [3, 3, 3, 1, 2, 1, 2, 1, 2]]
    cases += [[rng.randrange(4) for _ in range(rng.randrange(10, 24))] for _ in range(5)]
    for ids in cases:
        got = _call(fn, f"most_frequent_pair({_short(ids, 60)})", ids)
        expected = _ref_best(ids)
        if got != expected:
            counts = _ref_pairs(ids)
            top = max(counts.values())
            tied = [p for p in counts if counts[p] == top]
            hint = "Count the pairs, then take the largest count."
            if got in tied:
                hint = (f"{_short(got)} is tied at {top}, but {_short(expected)} appears earlier in the sequence. "
                        "Ties go to the pair seen first: max(counts, key=counts.get) does exactly that.")
            raise Fail(f"`most_frequent_pair({_short(ids, 60)})` returned {_short(got)}, expected {_short(expected)}.",
                       hint=hint)
    for ids in ([5], []):
        try:
            got = fn(list(ids))
        except Exception as exc:  # noqa: BLE001
            raise Fail(f"`most_frequent_pair({ids!r})` raised {type(exc).__name__}: {exc}",
                       hint="With fewer than two ids there is nothing to merge: return None before calling max().")
        if got is not None:
            raise Fail(f"`most_frequent_pair({ids!r})` returned {_short(got)}, expected None.",
                       hint="With fewer than two ids there is nothing to merge: return None.")


@MISSION.check("CORRUPTED `merge` repaired — non-overlapping, left to right")
def _merge(ctx):
    fn = _fn(ctx, "merge")
    rng = random.Random("AI01:merge")
    cases = [([5, 6, 5, 6, 7], (5, 6), 9), ([1, 1, 1], (1, 1), 4), ([1, 1, 1, 1], (1, 1), 4),
             ([2, 3, 1, 2], (1, 2), 8), ([2, 3, 2], (2, 9), 7), ([], (1, 2), 3)]
    for _ in range(4):
        ids = [rng.randrange(4) for _ in range(rng.randrange(10, 25))]
        cases.append((ids, _ref_best(ids), 10 + rng.randrange(5)))
    for ids, pair, new_id in cases:
        original = list(ids)
        label = f"merge({_short(ids, 60)}, {pair}, {new_id})"
        got = _call(fn, label, ids, pair, new_id,
                    hint="The last position has no right neighbour: check i + 1 < len(ids) before reading ids[i + 1].")
        expected = _ref_merge(ids, pair, new_id)
        hint = "After a match, the pair's second id is used up: jump i forward by 2, not 1."
        _expect(label, got, expected, hint=hint)
        if ids != original:
            raise Fail(f"`merge` changed the list it was given: {original!r} became {ids!r}.",
                       hint="Build and return a new list; the caller may still need the old ids.")
    probe = [1, 2, 1, 2]
    try:
        fn(probe, (1, 2), 5)
    except Exception:  # noqa: BLE001 — already reported above
        pass
    if probe != [1, 2, 1, 2]:
        raise Fail(f"`merge` modified its input list in place: [1, 2, 1, 2] became {probe!r}.",
                   hint="Append to a fresh `out` list and return it; leave `ids` untouched.")


@MISSION.check("Learning — `train_bpe` merges in order")
def _train(ctx):
    fn = _fn(ctx, "train_bpe")
    rng = random.Random("AI01:train")
    cases = [("abab", 5), ("x", 3), ("hello", 0)]
    for _ in range(3):
        cases.append((_text(rng, rng.randrange(25, 45)), rng.randrange(6, 14)))
    for text, k in cases:
        vocab = _ref_vocab(text + "q")
        label = f"train_bpe({_short(text, 50)}, vocab, {k})"
        got = _call(fn, label, text, vocab, k)
        expected = _ref_train(text, vocab, k)
        if not isinstance(got, dict):
            raise Fail(f"`{label}` returned {_short(got)}, expected a dict like {_short(expected)}.",
                       hint="Collect merges[pair] = new_id each round and return the dict.")
        if list(got.items()) != list(expected.items()):
            hint = "Each round: most frequent pair -> id len(vocab) + round -> merge the ids -> record it."
            if got.keys() == expected.keys():
                hint = "Right pairs, wrong ids or order. Round k's new id is len(vocab) + k, and merges are recorded in learning order."
            elif len(got) > len(expected):
                hint = "You kept merging after the sequence ran out of pairs. Stop when there are no pairs left."
            elif len(got) < len(expected):
                hint = ("You stopped early. Keep the merged ids from round to round (ids = merge(...)), "
                        "so later rounds can merge new ids with old ones.")
            raise Fail(f"`{label}` returned {_short(got)}, expected {_short(expected)}.", hint=hint)


@MISSION.check("Shards to speech — `bpe_encode` / `bpe_decode` round trip")
def _roundtrip(ctx):
    enc, dec = _fn(ctx, "bpe_encode"), _fn(ctx, "bpe_decode")
    rng = random.Random("AI01:bpe")
    corpus = _text(rng, 120)
    vocab = _ref_vocab("".join(_SYLLABLES) + corpus)
    merges = _ref_train(corpus, vocab, 24)
    texts = [_text(rng, rng.randrange(4, 16)) for _ in range(5)] + ["", "e"]
    for text in texts:
        label = f"bpe_encode({_short(text, 50)}, vocab, merges)"
        ids = _call(enc, label, text, vocab, merges)
        expected = _ref_bpe_encode(text, vocab, merges)
        hint = "Encode the characters, then apply each merge in the order it was learned: for pair, new_id in merges.items()."
        if isinstance(ids, list) and len(ids) == len(text) and len(expected) < len(text):
            hint = "No merge was applied: the ids are still one per character. Replay every learned merge over the ids."
        _expect(label, ids, expected, hint=hint)
        back = _call(dec, f"bpe_decode({_short(expected, 50)}, vocab, merges)", expected, vocab, merges)
        if back != text:
            raise Fail(f"`bpe_decode({_short(expected, 50)}, vocab, merges)` returned {_short(back)}, expected {text!r}.",
                       hint="Build an id -> text table: characters first, then table[new] = table[a] + table[b] for each merge in order.")
    plain = [vocab[c] for c in "the order"]
    if _call(dec, f"bpe_decode({_short(plain, 40)}, vocab, merges)", plain, vocab, merges) != "the order":
        raise Fail("`bpe_decode` can't decode plain character ids (no merges in them).",
                   hint="The table must start with every character id from the vocab, not just the merged ones.")
