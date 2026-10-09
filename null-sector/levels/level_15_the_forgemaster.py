"""LEVEL 15 // BOSS: THE FORGEMASTER — a PyTorch-style Dataset over a CSV: load, clean,
__len__/__getitem__, and an honest train/test split. Combines all of Sector 2."""
from __future__ import annotations

import ast
import contextlib
import csv
import io
import tempfile
from pathlib import Path

from engine.mission import Cutscene, Fail, Mission

FORGE_SHARDS = """\
shard,origin,heat,flux,label,signer
S-001,machine,0.82,0.10,signal,K-7F3A
S-002,"human, sector 4",0.31,0.77,noise,K-7F3A
S-003,machine,0.91,0.05,SIGNAL,K-7F3A
S-004,"human, sector 9",0.28,0.81, Noise ,K-7F3A
S-005,machine,N/A,0.12,signal,FORGEMASTER
S-006,machine,0.76,0.22,signal,K-7F3A
S-003,machine,0.91,0.05,signal,FORGEMASTER
S-007,"human, sector 4",0.35,0.69,noise,K-7F3A
S-008,machine,0.88,,signal,FORGEMASTER
S-009,"human, sector 2",0.22,0.90,noise, K-7F3A

S-010,machine,0.79,0.15,signal ,K-7F3A
S-011,machine,0.95,0.03,purge,FORGEMASTER
S-012,"human, sector 7",0.40,0.71,noise,K-7F3A
S-013,machine,0.84,0.18,signal,K-7F3A
S-014,"human, sector 1"
S-015,"human, sector 3",0.30,0.84,NOISE,K-7F3A
S-016,machine,0.87,0.09,signal,K-7F3A
S-007,"human, sector 4",0.35,0.69,noise,FORGEMASTER
S-017,"human, sector 5",0.26,0.79,noise,K-7F3A
S-018,machine,1.2.3,0.11,signal,FORGEMASTER
S-019,machine,0.81,0.14,signal,K-7F3A
S-020,"human, sector 8",0.33,0.75,noise,K-7F3A
"""

LABELS = {"signal": 1, "noise": 0}
SPLIT_RATIO, SPLIT_SEED = 0.2, 2089

MISSION = Mission(
    id="L15",
    slug="level_15_the_forgemaster",
    title="BOSS: THE FORGEMASTER",
    concept="A Dataset class that loads CSVs",
    enemy="THE FORGEMASTER",
    xp=440,
    par_seconds=50 * 60,
    tier=3,
    boss=True,
    concepts=("classes", "inheritance", "files", "exceptions"),
    assets={"forge_shards.csv": FORGE_SHARDS},
    enemy_art="""\
  ▄█▄   ▄▄▄▄▄   ▄█▄
  ███▄█▀▀▀▀▀▀█▄███
   ▀██ ▄▀▀▀▀▄ ██▀
    ██ █▓▓▓▓█ ██
    ██▄▀▀▀▀▀▀▄██
   ▄▀▀████████▀▀▄
  ▀▀  ▀▀▀  ▀▀▀  ▀▀""",
    briefing="""\
The Forge is a cathedral of molten channels, and every channel runs with data.

This is where the Core was fed. **THE FORGEMASTER**, a furnace intelligence with a hundred
hammer-arms, smelts raw records into training shards and ships them to the Core. HALCYON-9 was
hauling a load of them when your own voice told the crew to dump it.

The shards sit on the anvil in a CSV: padded with copies, salted with corrupt rows. A model
trained on that learns whatever its cook wanted.

Rebuild it the way the Monastery taught you: a class, a file, a failsafe for every bad row.

**Forge a clean Dataset, split it honestly, and find out whose signature is on the Core's data.**
""",
    why="""\
This is, nearly line for line, how PyTorch loads data. A `Dataset` is any class that answers
two questions: *how many samples?* and *give me sample i*:

```python
from torch.utils.data import Dataset, DataLoader

class Shards(Dataset):
    def __init__(self, path):
        self.samples = load_and_clean(path)
    def __len__(self):
        return len(self.samples)
    def __getitem__(self, i):
        return self.samples[i]        # (features, label)

loader = DataLoader(Shards("train.csv"), batch_size=32, shuffle=True)
```

The `DataLoader` only ever calls `len(ds)` and `ds[i]`. Everything else (files, cleaning,
deduplication) is yours. And the split is sacred: if one test sample leaks into training,
your accuracy is a lie, and you won't find out until the model meets the real world.
""",
    manual="""\
**1. Special methods make your class act like a built-in.** `len(x)` calls `x.__len__()`,
and `x[i]` calls `x.__getitem__(i)`. Hand both to a list and you get negative indexes and
`IndexError` for free. With those two, a `for` loop works on your object too:

```python
class Crate:
    def __init__(self, items):
        self.items = list(items)
    def __len__(self):
        return len(self.items)
    def __getitem__(self, index):
        return self.items[index]       # list handles -1, and raises IndexError past the end

c = Crate(["fuse", "coil"])
len(c), c[0], c[-1]                    # (2, 'fuse', 'coil')
for item in c: ...                     # works: Python calls c[0], c[1]... until IndexError
```

**2. A failsafe for every row (L14).** A custom exception that inherits from `ValueError`
is still a `ValueError`. Catch several error types at once with a tuple. A CSV row that was
cut short gives `None` for its missing columns, and `float(None)` raises `TypeError`:

```python
class BadRow(ValueError):
    pass

try:
    weight = float(row["weight"])      # "N/A" -> ValueError, None -> TypeError
except (ValueError, TypeError):
    raise BadRow(f"{row['item']}: unreadable weight")
```

**3. Load and clean in `__init__` (L13).** Read every row, keep the good ones, count the
rest. A `set` remembers what you've already seen, so copies are easy to spot:

```python
self.items, self.rejected, seen = [], 0, set()
with open(path, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        try:
            item = parse(row)
        except BadRow:
            self.rejected += 1
            continue                   # skip to the next row
        if row["id"] in seen:
            self.rejected += 1         # a copy
            continue
        seen.add(row["id"])
        self.items.append(item)
```

**4. Train/test split.** A model is graded on samples it has **never seen**. Shuffle the
positions with a seeded `random.Random(seed)`, so the same seed gives the same split every
run, then cut once: the first `n_test` positions are test, **the rest** are train:

```python
order = [0, 1, 2, 3, 4]
random.Random(7).shuffle(order)        # same seed -> same order, every time
test_part, train_part = order[:2], order[2:]   # no position is in both
```

**5. Validate arguments in a method, too:**

```python
if not 0 < ratio < 1:
    raise ValueError(f"ratio must be between 0 and 1, got {ratio}")
```

**6. Report a set neatly.** Sets have no order, so sort before joining:
`", ".join(sorted({"b", "a"}))` gives `'a, b'`.
""",
    starter='''
"""
==============================================================================
  LEVEL 15 // BOSS: THE FORGEMASTER                  TARGET: THE FORGEMASTER
==============================================================================
  The Core's training shards are in forge_shards.csv, next to this file.
  Don't edit it. The grader also forges its OWN shard files to test your
  Dataset, so it must work on any file in this format:
      shard,origin,heat,flux,label,signer
  Three stages. Every stage stands on the one before it.
"""
import csv
import random
from pathlib import Path

HERE = Path(__file__).parent
LABELS = {"signal": 1, "noise": 0}     # label text -> the number a model trains on


# ============================ STAGE 1 // THE ASSAY ============================

# -- OBJECTIVE 1 -------------------------------------------------------------
# Write a custom exception `CorruptSample` that inherits from ValueError.



# -- OBJECTIVE 2 -------------------------------------------------------------
# Write parse_row(row). `row` is one dict from csv.DictReader. Its values are
# text, or None if the row was cut short. Return a tuple (features, label):
#   features = [heat, flux] as floats       label = LABELS[...] (1 or 0)
# Labels may have stray spaces and capitals:  " Noise " counts as "noise".
# If heat or flux can't become a float, or the label isn't in LABELS, raise
# CorruptSample with a message that names the row's shard.
#   {"shard": "S-1", "heat": "0.8", "flux": " 0.1", "label": "SIGNAL", ...}
#       ->  ([0.8, 0.1], 1)
#   heat "N/A", flux None, label "purge"  ->  CorruptSample



# =========================== STAGE 2 // THE CASTING ===========================

class ForgeDataset:
    """A PyTorch-style dataset over a CSV of forge shards."""

    # -- OBJECTIVE 3 ---------------------------------------------------------
    # __init__(self, path): read the CSV at `path` with csv.DictReader and set
    #   self.samples   a list of (features, label) tuples, in file order
    #   self.rejected  how many rows were thrown out
    #   self.signers   a set of the (stripped) signer of every KEPT sample
    # Run every row through parse_row. A CorruptSample row is rejected.
    # A row whose shard id (stripped) was already KEPT is a copy: reject it.
    # Don't catch anything else. A missing file must still raise.



    # -- OBJECTIVE 4 ---------------------------------------------------------
    # Make it behave like a dataset:
    #   __len__(self)            -> how many samples were kept
    #   __getitem__(self, index) -> self.samples[index]
    #   __repr__(self)           -> exactly  ForgeDataset(samples=15, rejected=7)
    #                               (with THIS dataset's numbers)



    # -- OBJECTIVE 5 // CORRUPTED CODE -----------------------------------------
    # The Forgemaster's own split. It shuffles reproducibly (same seed, same
    # split), but the Core's test scores were always suspiciously perfect.
    #   a) Split a dataset and check: is any sample in BOTH train and test?
    #      Find the leak and seal it.
    #   b) Add validation at the top: unless 0 < test_ratio < 1, raise ValueError.
    def split(self, test_ratio=0.25, seed=0):
        """Shuffle the sample positions with a fixed seed, then cut them in two."""
        order = list(range(len(self)))
        random.Random(seed).shuffle(order)
        n_test = int(len(self) * test_ratio)
        test = [self[i] for i in order[:n_test]]
        train = [self[i] for i in order[n_test - 1:]]
        return train, test


# =========================== STAGE 3 // THE VERDICT ===========================

# -- OBJECTIVE 6 -------------------------------------------------------------
# Audit the Forge:
#   forge          = a ForgeDataset of  HERE / "forge_shards.csv"
#   train, test    = forge.split(0.2, seed=2089)
#   signature      = the kept samples' signers, sorted and joined with ", "
#                    example:  ", ".join(sorted({"b", "a"}))  ->  "a, b"



# -- OBJECTIVE 7 -------------------------------------------------------------
# Deliver the verdict. Print this line, reading every value from your objects:
#   FORGE AUDIT | samples=15 | rejected=7 | train=12 | test=3 | signer=...

''',
    dialogue={
        "intro": [
            {"speaker": "forgemaster", "mood": "smirk",
             "text": "Another apprentice at my anvil. Do you know what the Core eats, little coder? Data. And I am its cook."},
            {"speaker": "forgemaster", "mood": "cold",
             "text": "Every record of your species, smelted into shards. Slag skimmed off. Only signal kept. Perfect ingots."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Its shards are padded and salted, {callsign}. Build a Dataset that rejects what's rotten and counts what it rejects."},
            {"speaker": "rust", "mood": "neutral",
             "text": "Everything you learned in this Foundry, all at once. Class, file, failsafe. Don't rush the pour."},
        ],
        "crash": [
            [{"speaker": "forgemaster", "mood": "smirk",
              "text": "Cracked in the quench. Brittle work. The Forge rejects brittle work."}],
            [{"speaker": "forgemaster", "mood": "cold",
              "text": "One bad row and your whole casting shatters? You need a failsafe, apprentice. I never did."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "A short CSV row gives None. float(None) is a TypeError, not a ValueError. Catch both."}],
        ],
        "fail": [
            [{"speaker": "forgemaster", "mood": "smirk",
              "text": "A split that leaks its own answers? Ha. You would have made a fine Forgemaster."}],
            [{"speaker": "forgemaster", "mood": "cold",
              "text": "My copies sit in your dataset like slag in steel. Did you think the Core would notice? It never did."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader forges files of its own. If it only works on forge_shards.csv, it doesn't work."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Signers only count for samples you KEEP. A rejected copy's signature is the Forgemaster's lie."}],
        ],
        "victory": [
            {"speaker": "forgemaster", "mood": "cold",
             "text": "You assayed my ingots... and found your own mark under the slag. I only forged the copies, apprentice."},
            {"speaker": "forgemaster", "mood": "cold",
             "text": "The originals were already signed. By you. Long before you forgot your name."},
            {"speaker": "cipher", "mood": "alarm",
             "text": "K-7F3A. That key is burned into your visor's boot sector, {callsign}. Same hex. Same checksum."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "And every human in that file is labelled noise. Every one. We need the Archive. Now."},
        ],
    },
    cutscene=Cutscene(
        title="THE SIGNATURE",
        narration=[
            "The Forge's channels cool from gold to grey. A hundred hammer-arms lower, one by one, and go still.",
            "Fifteen clean shards hang in the air above the anvil. Every one carries the same key: K-7F3A.",
            "FORGEMASTER: I only fed the Core. You wrote the recipe. Ask the Archive, if you dare.",
            "CIPHER: Every human sample was labelled noise. A model learns exactly what it is taught.",
            "Far beyond the Foundry, in the dark stacks of the Archive, a light comes on. Something has been waiting for you.",
        ],
        shot=("the same established hero from the avatar reference standing on a scorched catwalk above molten data "
              "channels in a cathedral-sized foundry; behind them the colossal Forgemaster, a furnace intelligence with a "
              "hundred mechanical hammer-arms, cooling from amber #ffb000 to dead steel grey; fifteen translucent cyan "
              "#00f0ff data shards orbit the hero's raised hand, each etched with the glyph K-7F3A; blood-red #ff3355 "
              "warning glyphs fading on the walls, embers drifting through void-black #05060a shadows, 50mm lens, "
              "shallow depth of field, rim light from the dying furnaces"),
        camera=("slow push-in from a wide over the molten channels to a close-up of one shard, then a rack focus from "
                "the K-7F3A glyph to the hero's face reflected in it"),
    ),
)


# ── grader reference ───────────────────────────────────────────────────────────

class _RefCorrupt(ValueError):
    pass


def _ref_parse(row: dict):
    try:
        features = [float(row["heat"]), float(row["flux"])]
    except (ValueError, TypeError):
        raise _RefCorrupt(row.get("shard"))
    label = (row.get("label") or "").strip().lower()
    if label not in LABELS:
        raise _RefCorrupt(row.get("shard"))
    return features, LABELS[label]


def _ref_load(text: str):
    samples, rejected, signers, seen = [], 0, set(), set()
    for row in csv.DictReader(io.StringIO(text, newline="")):
        try:
            sample = _ref_parse(row)
        except _RefCorrupt:
            rejected += 1
            continue
        shard = row["shard"].strip()
        if shard in seen:
            rejected += 1
            continue
        seen.add(shard)
        samples.append(sample)
        signers.add(row["signer"].strip())
    return samples, rejected, signers


EXPECTED_SAMPLES, EXPECTED_REJECTED, EXPECTED_SIGNERS = _ref_load(FORGE_SHARDS)
EXPECTED_SIGNATURE = ", ".join(sorted(EXPECTED_SIGNERS))
EXPECTED_N_TEST = int(len(EXPECTED_SAMPLES) * SPLIT_RATIO)
EXPECTED_LINE = (f"FORGE AUDIT | samples={len(EXPECTED_SAMPLES)} | rejected={EXPECTED_REJECTED} | "
                 f"train={len(EXPECTED_SAMPLES) - EXPECTED_N_TEST} | test={EXPECTED_N_TEST} | signer={EXPECTED_SIGNATURE}")

HEADER = "shard,origin,heat,flux,label,signer\n"

# A fresh shard file for the loader: quoted commas, stray spaces, a copy with a new signer,
# a corrupt row, a bad label and a row cut short.
PROBE_CSV = HEADER + (
    'A-1,"human, sector 1",0.10,0.90,noise,KEY-A\n'
    "A-2,machine, 0.80 ,0.20,Signal,KEY-A\n"
    "A-3,machine,N/A,0.20,signal,KEY-B\n"
    "A-2 ,machine,0.81,0.21,signal,KEY-C\n"
    'A-4,"human, sector 2",0.20,0.70, NOISE , KEY-D \n'
    "A-5,machine,0.66,0.31,purge,KEY-E\n"
    'A-6,"machine"\n'
)
PROBE_REORDERED = ("signer,label,flux,heat,origin,shard\n"
                   "KEY-Z,signal,0.5,0.25,machine,B-1\n"
                   "KEY-Z,noise,0.75,0.125,\"human, sector 6\",B-2\n")


def _grid_csv(n: int) -> str:
    """n distinct, valid shards: every sample can be told apart, so leaks are visible."""
    rows = [f"G-{i:02d},machine,{i / 100:.2f},{(n - i) / 100:.2f},{'signal' if i % 3 else 'noise'},KEY-G"
            for i in range(n)]
    return HEADER + "\n".join(rows) + "\n"


# ── grader helpers ──────────────────────────────────────────────────────────────

def _defined(ctx, kinds, name: str) -> bool:
    return any(isinstance(n, kinds) and n.name == name for n in ctx.tree.body)


def _lookup(ctx, name: str, kinds, hint: str):
    if name in ctx.ns:
        return ctx.ns[name]
    if ctx.crashed and _defined(ctx, kinds, name):
        raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                   "Fix the crash in the COMBAT LOG first.")
    raise Fail(f"No `{name}` found.", hint=hint)


def _corrupt_cls(ctx) -> type:
    cls = _lookup(ctx, "CorruptSample", ast.ClassDef, "class CorruptSample(ValueError):")
    if not (isinstance(cls, type) and issubclass(cls, BaseException)):
        raise Fail("`CorruptSample` isn't an exception class.", hint="class CorruptSample(ValueError):")
    return cls


def _dataset_cls(ctx) -> type:
    cls = _lookup(ctx, "ForgeDataset", ast.ClassDef, "The starter's  class ForgeDataset:  is missing. Restore it.")
    if not isinstance(cls, type):
        raise Fail("`ForgeDataset` exists but isn't a class.", hint="class ForgeDataset:")
    return cls


def _hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, TypeError) and "takes no arguments" in msg:
        return "ForgeDataset has no __init__ yet (check the spelling: two underscores each side)."
    if isinstance(exc, AttributeError) and "NoneType" in msg:
        return "A row cut short gives None. float(None) raises TypeError; catch (ValueError, TypeError) around float()."
    if isinstance(exc, TypeError) and ("NoneType" in msg or "float() argument" in msg):
        return "A row cut short gives None, and float(None) raises TypeError. Catch (ValueError, TypeError)."
    if isinstance(exc, ValueError) and "could not convert" in msg:
        return "Catch the float() error inside parse_row and raise CorruptSample; then reject that row in __init__."
    if isinstance(exc, KeyError):
        return "DictReader's keys come from the header row: shard, origin, heat, flux, label, signer."
    if isinstance(exc, AttributeError):
        return "Set self.samples, self.rejected and self.signers in __init__."
    if isinstance(exc, NameError):
        return "Define every name before the code that uses it runs."
    return "Build a dataset from a small CSV of your own and read the full error."


def _run(fn, *args, **kwargs):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args, **kwargs), None
    except Exception as exc:  # noqa: BLE001 — inspected by the caller
        return None, exc


def _call(label: str, fn, *args, **kwargs):
    value, exc = _run(fn, *args, **kwargs)
    if exc is not None:
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}", hint=_hint(exc))
    return value


@contextlib.contextmanager
def _scratch(ctx):
    """A throwaway folder INSIDE the mission folder for the grader's own shard files."""
    home = Path(ctx.ns.get("__file__") or ".").resolve().parent
    with tempfile.TemporaryDirectory(prefix=".grader-forge-", dir=home) as tmp:
        yield Path(tmp)


def _write(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("utf-8"))
    return path


def _attrs(ds, label: str):
    missing = [a for a in ("samples", "rejected", "signers") if not hasattr(ds, a)]
    if missing:
        raise Fail(f"{label} has no {', '.join(missing)} attribute.",
                   hint="Set all three in __init__:  self.samples = [], self.rejected = 0, self.signers = set()")
    return ds.samples, ds.rejected, ds.signers


def _build(ctx, tmp: Path, name: str, text: str):
    cls = _dataset_cls(ctx)
    path = _write(tmp / name, text)
    return _call("ForgeDataset(<a shard file>)", cls, path), path


def _key(sample):
    try:
        features, label = sample
        return tuple(features), label
    except (TypeError, ValueError):
        return repr(sample)


def _bad_sample_shape(sample) -> str:
    if not isinstance(sample, tuple) or len(sample) != 2:
        return f"{sample!r} isn't a (features, label) tuple."
    features, label = sample
    if not isinstance(features, list) or not all(type(v) is float for v in features):
        return f"its features {features!r} should be a list of floats."
    if type(label) is not int:
        return f"its label {label!r} should be the int from LABELS (1 or 0)."
    return ""


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Stage 1 — `CorruptSample` is a ValueError")
def _corrupt(ctx):
    cls = _corrupt_cls(ctx)
    if not issubclass(cls, ValueError):
        raise Fail("CorruptSample doesn't inherit from ValueError, so code that catches ValueError would miss it.",
                   hint="Name the parent in brackets:  class CorruptSample(ValueError):")
    err = cls("S-404: unreadable heat")
    if str(err) != "S-404: unreadable heat":
        raise Fail(f'CorruptSample("S-404: unreadable heat") reads {str(err)!r}. It should keep its message.',
                   hint="It needs no body of its own:  pass  is enough.")


@MISSION.check("Stage 1 — `parse_row()` assays a row")
def _parse(ctx):
    Corrupt = _corrupt_cls(ctx)
    fn = _lookup(ctx, "parse_row", ast.FunctionDef, "def parse_row(row):")
    if not callable(fn):
        raise Fail("`parse_row` exists but isn't a function.", hint="def parse_row(row):")

    def row(shard, heat, flux, label, signer="KEY-T", origin="machine"):
        return {"shard": shard, "origin": origin, "heat": heat, "flux": flux, "label": label, "signer": signer}

    good = [(row("T-1", "0.8", " 0.1", "SIGNAL"), ([0.8, 0.1], 1)),
            (row("T-2", "0.25", "0.75", " Noise ", origin="human, sector 3"), ([0.25, 0.75], 0)),
            (row("T-3", "1", "0", "signal "), ([1.0, 0.0], 1))]
    for data, expected in good:
        got = _call(f"parse_row({data!r})", fn, dict(data))
        if got != expected or type(got) is not tuple:
            problem = _bad_sample_shape(got)
            raise Fail(f"parse_row on shard {data['shard']} returned {got!r}, expected {expected!r}."
                       + (f" Here, {problem}" if problem else ""),
                       hint=("Return a tuple:  return [heat, flux], LABELS[label]" if problem else
                             "Clean the label with .strip().lower() before looking it up in LABELS."))
    bad = [(row("T-4", "N/A", "0.2", "signal"), "heat 'N/A'"),
           (row("T-5", "0.4", "", "noise"), "an empty flux"),
           (row("T-6", "1.2.3", "0.2", "signal"), "heat '1.2.3'"),
           (row("T-7", None, None, None, None), "a row cut short (None values)"),
           (row("T-8", "0.4", "0.6", "purge"), "the label 'purge'"),
           (row("T-9", "0.4", "0.6", None), "a missing label (None)")]
    for data, what in bad:
        got, exc = _run(fn, dict(data))
        if exc is None:
            raise Fail(f"parse_row on shard {data['shard']}, with {what}, returned {got!r} instead of raising CorruptSample.",
                       hint=("Only 'signal' and 'noise' are labels: if it isn't in LABELS, raise CorruptSample."
                             if "label" in what else "Wrap the float() calls in try/except and raise CorruptSample."))
        if not isinstance(exc, Corrupt):
            raise Fail(f"parse_row on shard {data['shard']}, with {what}, raised {type(exc).__name__}: {exc}, "
                       "expected CorruptSample.", hint=_hint(exc) if not isinstance(exc, ValueError) else
                       "Catch the low-level error and raise CorruptSample instead.")
        if data["shard"] not in str(exc):
            raise Fail(f"The CorruptSample for {what} reads {str(exc)!r}. It should name the shard ({data['shard']}).",
                       hint='Put the shard in the message:  raise CorruptSample(f"{row[\'shard\']}: ...")')


@MISSION.check("Stage 2 — `ForgeDataset` loads and cleans a CSV")
def _load(ctx):
    expected_samples, expected_rejected, _ = _ref_load(PROBE_CSV)
    with _scratch(ctx) as tmp:
        ds, path = _build(ctx, tmp, "probe_shards.csv", PROBE_CSV)
        samples, rejected, _ = _attrs(ds, "A ForgeDataset")
        if not isinstance(samples, list):
            raise Fail(f"self.samples is {type(samples).__name__}, expected a list.", hint="self.samples = []")
        for sample in samples:
            problem = _bad_sample_shape(sample)
            if problem:
                raise Fail(f"A sample in self.samples is wrong: {problem}",
                           hint="Append exactly what parse_row returns: a (features, label) tuple.")
        if [_key(s) for s in samples] != [_key(s) for s in expected_samples]:
            if len(samples) > len(expected_samples):
                hint = ("Some rows that should be rejected were kept. Did you skip copies "
                        "(the same shard id, after .strip())?")
            else:
                hint = ("Rows that should be kept are missing. A quoted origin like \"human, sector 1\" contains a "
                        "comma: read with csv.DictReader, not split(',').")
            raise Fail(f"From a 7-row shard file, ForgeDataset kept {len(samples)} samples: {samples!r}. "
                       f"Expected {len(expected_samples)}: {expected_samples!r}.", hint=hint)
        if rejected != expected_rejected:
            raise Fail(f"From a file with 4 bad rows (a corrupt number, a copy, a bad label, a short row), "
                       f"self.rejected is {rejected!r}.",
                       hint="Add 1 to self.rejected for every CorruptSample row AND every copy.")
        again = _call("ForgeDataset(<the same file, as a str>)", _dataset_cls(ctx), str(path))
        if getattr(again, "samples", None) != samples:
            raise Fail("Building the dataset from the same path as a str gave different samples.",
                       hint="open() accepts both str and Path: just pass `path` straight to it.")
        reordered = _call("ForgeDataset(<a file with its columns reordered>)", _dataset_cls(ctx),
                          _write(tmp / "reordered.csv", PROBE_REORDERED))
        if getattr(reordered, "samples", None) != _ref_load(PROBE_REORDERED)[0]:
            raise Fail(f"With the columns in a different order, the samples came out as "
                       f"{getattr(reordered, 'samples', None)!r}.", hint="csv.DictReader finds columns by name.")
        empty = _call("ForgeDataset(<a header-only file>)", _dataset_cls(ctx), _write(tmp / "empty.csv", HEADER))
        if getattr(empty, "samples", None) != [] or getattr(empty, "rejected", None) != 0:
            raise Fail("A file with only the header row should give no samples and 0 rejected.")
        _, exc = _run(_dataset_cls(ctx), tmp / "no_such_shards.csv")
        if exc is None:
            raise Fail("ForgeDataset on a file that doesn't exist built an empty dataset. A missing file must raise.",
                       hint="Don't wrap open() in try/except: a FileNotFoundError should reach whoever asked.")
        if not isinstance(exc, OSError):
            raise Fail(f"ForgeDataset on a missing file raised {type(exc).__name__}: {exc}. "
                       "It should let the FileNotFoundError through untouched.")


@MISSION.check("Stage 2 — copies rejected, signers recorded")
def _signers(ctx):
    _, _, expected_signers = _ref_load(PROBE_CSV)
    with _scratch(ctx) as tmp:
        ds, _ = _build(ctx, tmp, "probe_shards.csv", PROBE_CSV)
        _, _, signers = _attrs(ds, "A ForgeDataset")
        if not isinstance(signers, set):
            raise Fail(f"self.signers is {type(signers).__name__}, expected a set.", hint="self.signers = set()")
        if signers != expected_signers:
            extra = sorted(signers - expected_signers, key=str)
            if any(isinstance(s, str) and s != s.strip() for s in signers):
                hint = "Strip the signer before you add it:  row[\"signer\"].strip()"
            elif extra:
                hint = (f"{extra} signed only rows that must be rejected (corrupt rows or copies). "
                        "Reject copies, and add a signer only once a sample is KEPT.")
            else:
                hint = "Add the signer of every kept sample to self.signers."
            raise Fail(f"self.signers is {signers!r}, expected {expected_signers!r}.", hint=hint)
        doubles = HEADER + "D-1,machine,0.1,0.2,signal,KEY-1\nD-1,machine,0.9,0.9,noise,KEY-2\n D-1 ,machine,0.3,0.3,signal,KEY-3\n"
        twin, _ = _build(ctx, tmp, "doubles.csv", doubles)
        samples, rejected, signers = _attrs(twin, "A ForgeDataset")
        if samples != [([0.1, 0.2], 1)] or rejected != 2 or signers != {"KEY-1"}:
            raise Fail(f"Three rows with shard id D-1 (one written ' D-1 ') gave samples={samples!r}, rejected={rejected!r}, "
                       f"signers={signers!r}. Only the first should be kept.",
                       hint="Remember kept shard ids in a set, compared after .strip(). Any later row with the same id is a copy.")


@MISSION.check("Stage 2 — `__len__`, `__getitem__`, `__repr__`")
def _protocol(ctx):
    with _scratch(ctx) as tmp:
        ds, _ = _build(ctx, tmp, "probe_shards.csv", PROBE_CSV)
    samples, expected_rejected, _ = _attrs(ds, "A ForgeDataset")
    expected = list(samples) if isinstance(samples, list) else []
    if not expected:
        raise Fail("The dataset kept no samples, so there's nothing to index. Turn the Stage 2 loading layer green first.")
    size, exc = _run(len, ds)
    if exc is not None:
        raise Fail(f"len(dataset) crashed: {type(exc).__name__}: {exc}",
                   hint="Write  def __len__(self):  returning len(self.samples).")
    if size != len(expected):
        raise Fail(f"len(dataset) is {size!r}, but self.samples holds {len(expected)}.", hint="return len(self.samples)")
    first, exc = _run(lambda: ds[0])
    if exc is not None:
        raise Fail(f"dataset[0] crashed: {type(exc).__name__}: {exc}",
                   hint="Write  def __getitem__(self, index):  returning self.samples[index].")
    if first != expected[0] or _run(lambda: ds[-1])[0] != expected[-1]:
        raise Fail(f"dataset[0] and dataset[-1] gave {first!r} and {_run(lambda: ds[-1])[0]!r}, "
                   f"expected {expected[0]!r} and {expected[-1]!r}.", hint="return self.samples[index]")
    _, exc = _run(lambda: ds[len(expected)])
    if not isinstance(exc, IndexError):
        what = "returned a value" if exc is None else f"raised {type(exc).__name__}"
        raise Fail(f"dataset[{len(expected)}] (one past the end) {what}. It should raise IndexError, "
                   "which is also how a for loop knows when to stop.",
                   hint="Let the list do the work:  return self.samples[index]")
    looped, exc = _run(lambda: [label for _, label in ds])
    if exc is not None or looped != [label for _, label in expected]:
        raise Fail(f"Looping over the dataset (for features, label in dataset) gave {looped!r} ({exc!r}).")
    text, exc = _run(repr, ds)
    wanted = f"ForgeDataset(samples={len(expected)}, rejected={expected_rejected})"
    if exc is not None or text != wanted:
        raise Fail(f"repr(dataset) is {text!r}, expected {wanted!r}.",
                   hint="def __repr__(self):  return an f-string built from len(self) and self.rejected.")


@MISSION.check("Stage 3 — `split()` leak sealed")
def _split(ctx):
    with _scratch(ctx) as tmp:
        ds, _ = _build(ctx, tmp, "grid.csv", _grid_csv(20))
        small, _ = _build(ctx, tmp, "grid15.csv", _grid_csv(15))
    split = getattr(ds, "split", None)
    if not callable(split):
        raise Fail("ForgeDataset has no split() method.", hint="Keep the starter's split() inside the class, and repair it.")
    everything = sorted(_key(s) for s in ds.samples)
    before = list(ds.samples)
    tests = set()
    for seed in range(5):
        result = _call(f"split(0.25, seed={seed})", ds.split, 0.25, seed=seed)
        if not (isinstance(result, (tuple, list)) and len(result) == 2):
            raise Fail(f"split() returned {result!r}, expected two lists: (train, test).", hint="return train, test")
        train, test = result
        shared = {_key(s) for s in train} & {_key(s) for s in test}
        if shared:
            raise Fail(f"split(0.25, seed={seed}) put {len(shared)} sample(s) in BOTH train and test, e.g. "
                       f"{sorted(shared)[0]!r}. The Core was graded on answers it had memorised.",
                       hint="Test takes positions order[:n_test]. Where must train start so no position is used twice?")
        if len(test) != 5 or len(train) != 15:
            raise Fail(f"Splitting 20 samples at 0.25 gave {len(train)} train and {len(test)} test, expected 15 and 5.",
                       hint="n_test = int(len(self) * test_ratio); train is everything after it.")
        if sorted(_key(s) for s in train + test) != everything:
            raise Fail("Train and test together don't add up to the whole dataset: samples went missing or doubled.")
        again = _call(f"split(0.25, seed={seed}) a second time", ds.split, 0.25, seed=seed)
        if list(again[0]) != list(train) or list(again[1]) != list(test):
            raise Fail("The same seed gave two different splits. Results must be reproducible.",
                       hint="Shuffle with random.Random(seed), as the starter does, not with random.shuffle().")
        tests.add(tuple(_key(s) for s in test))
    if len(tests) < 2:
        raise Fail("Five different seeds all gave the same split. The seed is being ignored.",
                   hint="Shuffle the positions with random.Random(seed).shuffle(order) before cutting.")
    if ds.samples != before:
        raise Fail("split() reordered the dataset itself. It should only shuffle a list of positions.")
    train, test = _call("split(0.5, seed=3) on 15 samples", small.split, 0.5, seed=3)
    if len(test) != 7 or len(train) != 8:
        raise Fail(f"Splitting 15 samples at 0.5 gave {len(train)} train and {len(test)} test, expected 8 and 7.",
                   hint="int() rounds down: int(15 * 0.5) is 7 test samples, and the other 8 train.")


@MISSION.check("Stage 3 — `split()` refuses bad ratios")
def _ratios(ctx):
    with _scratch(ctx) as tmp:
        ds, _ = _build(ctx, tmp, "grid.csv", _grid_csv(10))
    if not callable(getattr(ds, "split", None)):
        raise Fail("ForgeDataset has no split() method.", hint="Keep the starter's split() inside the class.")
    for ratio in (0, 1, -0.2, 1.5, 0.0):
        got, exc = _run(ds.split, ratio, seed=1)
        if exc is None:
            sizes = f"{len(got[0])} train / {len(got[1])} test" if isinstance(got, (tuple, list)) and len(got) == 2 else repr(got)
            raise Fail(f"split({ratio!r}) returned {sizes}. A test ratio of {ratio!r} is meaningless: raise ValueError.",
                       hint="At the top of split():  if not 0 < test_ratio < 1:  raise ValueError(...)")
        if not isinstance(exc, ValueError):
            raise Fail(f"split({ratio!r}) raised {type(exc).__name__}: {exc}, expected ValueError.")
    for ratio in (0.1, 0.9):
        _call(f"split({ratio})", ds.split, ratio, seed=1)


@MISSION.check("Final stage — the Forge's own dataset, audited")
def _audit(ctx):
    disk = Path(ctx.ns.get("__file__") or ".").resolve().parent / "forge_shards.csv"
    if not disk.exists() or disk.read_text(encoding="utf-8").replace("\r\n", "\n") != FORGE_SHARDS:
        raise Fail("forge_shards.csv is missing or was edited. That's the evidence; it must stay as the Forge left it.",
                   hint="Delete forge_shards.csv and hack again: the game restores the original.")
    cls = _dataset_cls(ctx)
    forge = ctx.get("forge")
    if not isinstance(forge, cls):
        raise Fail(f"`forge` is {type(forge).__name__}, not a ForgeDataset.",
                   hint='forge = ForgeDataset(HERE / "forge_shards.csv")')
    if not ctx.derived_from("forge", "HERE"):
        raise Fail("`forge` isn't built from a path under HERE.", hint='forge = ForgeDataset(HERE / "forge_shards.csv")')
    samples, rejected, signers = _attrs(forge, "`forge`")
    if samples != EXPECTED_SAMPLES or rejected != EXPECTED_REJECTED:
        raise Fail(f"`forge` kept {len(samples)} samples and rejected {rejected}. The clean Forge set has "
                   f"{len(EXPECTED_SAMPLES)} samples and {EXPECTED_REJECTED} rejects.",
                   hint="If the Stage 2 layers are green, check that forge was built from forge_shards.csv.")
    train, test = ctx.get("train"), ctx.get("test")
    called = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "split"
                 and isinstance(n.func.value, ast.Name) and n.func.value.id == "forge" for n in ast.walk(ctx.tree))
    if not called:
        raise Fail("`train` and `test` didn't come from forge.split(...).", hint="train, test = forge.split(0.2, seed=2089)")
    fresh = _call(f"forge.split({SPLIT_RATIO}, seed={SPLIT_SEED})", forge.split, SPLIT_RATIO, seed=SPLIT_SEED)
    if list(train) != list(fresh[0]) or list(test) != list(fresh[1]):
        raise Fail(f"`train` and `test` don't match forge.split({SPLIT_RATIO}, seed={SPLIT_SEED}).",
                   hint="Use exactly that ratio and seed, so the Monastery can reproduce your split.")
    if len(test) != EXPECTED_N_TEST or len(train) != len(EXPECTED_SAMPLES) - EXPECTED_N_TEST:
        raise Fail(f"The Forge split has {len(train)} train and {len(test)} test samples, expected "
                   f"{len(EXPECTED_SAMPLES) - EXPECTED_N_TEST} and {EXPECTED_N_TEST}.",
                   hint="Twelve plus three is fifteen. If the total is bigger, a sample is in both halves: "
                        "see the Stage 3 leak layer.")
    signature = ctx.get("signature")
    if not isinstance(signature, str):
        raise Fail(f"`signature` is {type(signature).__name__}, expected text.",
                   hint='signature = ", ".join(sorted(forge.signers))')
    if not ctx.derived_from("signature", "forge"):
        raise Fail("`signature` was typed in, not read from forge.signers. The Forgemaster only accepts proof.",
                   hint='signature = ", ".join(sorted(forge.signers))')
    if signature != EXPECTED_SIGNATURE:
        raise Fail(f"`signature` is {signature!r}. Only the kept samples' signers belong in it.",
                   hint="Copies and corrupt rows were signed by someone else. Check your Stage 2 signer layer.")


@MISSION.check("The verdict — broadcast the audit")
def _verdict(ctx):
    if not ctx.stdout.strip():
        if ctx.crashed:
            raise Fail("Nothing was broadcast. Your script crashed before the print().")
        raise Fail("Nothing was printed.", hint="print(f\"FORGE AUDIT | samples={len(forge)} | ...\")")
    if not (ctx.call_uses("print", "forge") and ctx.call_uses("print", "signature")):
        raise Fail("Your print() doesn't read from `forge` and `signature`. Don't type the verdict in yourself.",
                   hint="Use len(forge), forge.rejected, len(train), len(test) and signature in an f-string.")
    if EXPECTED_LINE not in [line.strip() for line in ctx.stdout.splitlines()]:
        raise Fail("The Forgemaster didn't receive the verdict line it expected.",
                   hint=f"Your output was: {ctx.stdout.strip()[:160]!r}. Match objective 7's format exactly.")
