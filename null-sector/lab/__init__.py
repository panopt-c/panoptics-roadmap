"""THE LAB: the Order's machine-learning school (docs/GAME_DESIGN.md §13).

Six tracks take you from "Python that handles data" to building and evaluating models, then
to the pieces of modern AI: tokens, embeddings, attention, retrieval and evals. Every mission is a
normal `Mission` (same grader, same editor), loaded from `lab/<slug>.py`.

A mission is "built" once its file exists; until then it shows as sealed. Content authors only
ever add files. A track opens when ANY of its `gate` ids is cleared (a campaign level or another
track's capstone), so experienced players can go straight to the material they need. Inside an
open track every mission is playable; the capstone needs `CAPSTONE_AFTER` of the track's other
missions first.
"""
from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass, replace
from pathlib import Path

from engine.mission import Mission

CAPSTONE_AFTER = 4   # cleared missions in a track before its capstone opens


@dataclass(frozen=True)
class LabEntry:
    id: str                       # "NP03" — track code + number; also the API id
    title: str
    concept: str
    slug: str | None              # module in lab/ once built
    capstone: bool = False
    requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class Track:
    code: str
    name: str
    tagline: str
    color: str
    gate: tuple[str, ...]          # any of these cleared opens the track
    entries: tuple[LabEntry, ...]


def _e(code: str, n: int, title: str, concept: str, name: str, *, capstone: bool = False,
       requires: tuple[str, ...] = ()) -> LabEntry:
    return LabEntry(f"{code}{n:02d}", title, concept, f"{code.lower()}{n:02d}_{name}", capstone, requires)


NP = ("numpy",)
PD = ("numpy", "pandas")

_TRACKS = (
    Track("PY", "DATA RITES", "Python that handles real data", "#39ff14", ("L05",), (
        _e("PY", 1, "THE CENSUS", "Comprehensions for data", "census"),
        _e("PY", 2, "TALLY MARKS", "Counter, defaultdict & frequencies", "tally_marks"),
        _e("PY", 3, "ORDER OF RANKS", "Sorting with keys, zip & enumerate", "order_of_ranks"),
        _e("PY", 4, "SCROLLS OF THE ORDER", "The csv module & typed records", "scrolls"),
        _e("PY", 5, "THE MEASURE", "Statistics by hand: mean, median, variance", "the_measure"),
        _e("PY", 6, "CLEAN WATER", "Validating & cleaning messy records", "clean_water"),
        _e("PY", 7, "CAPSTONE: THE LEDGER", "A full dataset summary report", "the_ledger", capstone=True),
    )),
    Track("NP", "TENSOR SUTRAS", "NumPy: think in arrays", "#00f0ff", ("PY07", "L10"), (
        _e("NP", 1, "FIRST ARRAY", "Arrays, dtypes & shape", "first_array", requires=NP),
        _e("NP", 2, "MASKS", "Indexing, slicing & boolean masks", "masks", requires=NP),
        _e("NP", 3, "BROADCAST", "Broadcasting rules", "broadcast", requires=NP),
        _e("NP", 4, "NO LOOPS", "Vectorization & axis reductions", "no_loops", requires=NP),
        _e("NP", 5, "THE MATRIX RITE", "Matrix multiplication & linear algebra", "matrix_rite", requires=NP),
        _e("NP", 6, "SEEDED CHAOS", "Random generators, sampling & shuffling", "seeded_chaos", requires=NP),
        _e("NP", 7, "CAPSTONE: NEAREST KIN", "Vectorized k-nearest neighbours", "nearest_kin", capstone=True, requires=NP),
    )),
    Track("DA", "ARCHIVE OF NOISE", "Data wrangling & features with pandas", "#ffb000", ("NP03", "L15"), (
        _e("DA", 1, "THE FRAME", "DataFrames: load, inspect, select", "the_frame", requires=PD),
        _e("DA", 2, "MISSING PIECES", "Missing values & type repair", "missing_pieces", requires=PD),
        _e("DA", 3, "THE GATHERING", "groupby & aggregations", "the_gathering", requires=PD),
        _e("DA", 4, "BINDINGS", "Merges & joins", "bindings", requires=PD),
        _e("DA", 5, "FEATURE FORGE", "One-hot encoding & scaling", "feature_forge", requires=PD),
        _e("DA", 6, "NO PEEKING", "Train/validation/test splits without leakage", "no_peeking", requires=PD),
        _e("DA", 7, "CAPSTONE: THE PIPELINE", "A reusable feature pipeline", "the_pipeline", capstone=True, requires=PD),
    )),
    Track("ML", "ORACLE'S APPRENTICE", "Classic machine learning from scratch", "#b388ff", ("NP07", "L20"), (
        _e("ML", 1, "THE LINE", "Linear regression: the normal equation", "the_line", requires=NP),
        _e("ML", 2, "DOWNHILL", "Gradient descent & loss curves", "downhill", requires=NP),
        _e("ML", 3, "YES OR NO", "Logistic regression", "yes_or_no", requires=NP),
        _e("ML", 4, "THE JUDGE'S LEDGER", "Confusion matrix, precision, recall, F1", "judges_ledger", requires=NP),
        _e("ML", 5, "FOLDS", "Cross-validation", "folds", requires=NP),
        _e("ML", 6, "THE OVERFIT", "Regularization & the bias-variance trade-off", "the_overfit", requires=NP),
        _e("ML", 7, "CAPSTONE: BEAT THE BASELINE", "Build and evaluate a classifier", "beat_the_baseline", capstone=True, requires=NP),
    )),
    Track("DL", "NEURAL LITURGY", "Deep learning from first principles", "#ff2bd6", ("ML07", "L23"), (
        _e("DL", 1, "THE SPARK", "A scalar autograd engine", "the_spark"),
        _e("DL", 2, "CHAIN RULE", "Backpropagation through a graph", "chain_rule"),
        _e("DL", 3, "THE LAYER", "A neural layer & an MLP forward pass", "the_layer", requires=NP),
        _e("DL", 4, "SOFT LANDING", "Softmax & cross-entropy, numerically stable", "soft_landing", requires=NP),
        _e("DL", 5, "MOMENTUM", "Optimizers: SGD, momentum, Adam", "momentum", requires=NP),
        _e("DL", 6, "THE BATCH", "Initialization, mini-batches & a training loop", "the_batch", requires=NP),
        _e("DL", 7, "CAPSTONE: AWAKEN", "Train an MLP to a target accuracy", "awaken", capstone=True, requires=NP),
    )),
    Track("AI", "LANGUAGE OF GODS", "Tokens, embeddings, attention, retrieval & evals", "#ff3355", ("DL07", "L25"), (
        _e("AI", 1, "SHARDS OF SPEECH", "Tokenization & BPE merges", "shards_of_speech"),
        _e("AI", 2, "MEANING SPACE", "Embeddings & cosine similarity", "meaning_space", requires=NP),
        _e("AI", 3, "THE GAZE", "Scaled dot-product attention & causal masks", "the_gaze", requires=NP),
        _e("AI", 4, "THE BABBLER", "A bigram language model, sampling & temperature", "the_babbler"),
        _e("AI", 5, "THE LIBRARY OF ECHOES", "Retrieval for RAG", "library_of_echoes", requires=NP),
        _e("AI", 6, "THE TRIAL", "Evaluating model outputs", "the_trial"),
        _e("AI", 7, "CAPSTONE: THE ANSWERING MACHINE", "A tiny RAG system with an eval harness", "answering_machine", capstone=True, requires=NP),
    )),
)

_HERE = Path(__file__).resolve().parent


def _built(entry: LabEntry) -> LabEntry:
    return entry if entry.slug and (_HERE / f"{entry.slug}.py").exists() else replace(entry, slug=None)


TRACKS = tuple(replace(t, entries=tuple(_built(e) for e in t.entries)) for t in _TRACKS)
ALL_ENTRIES = [e for t in TRACKS for e in t.entries]


def find(mission_id: str) -> tuple[Track, LabEntry] | None:
    for track in TRACKS:
        for entry in track.entries:
            if entry.id == mission_id:
                return track, entry
    return None


def is_lab_id(mission_id: str) -> bool:
    return find(mission_id) is not None


def track_open(track: Track, cleared: dict) -> bool:
    return any(gate in cleared for gate in track.gate)


def playable(mission_id: str, cleared: dict) -> bool:
    """Built, its track is open, and (for a capstone) enough of the track is cleared."""
    found = find(mission_id)
    if not found:
        return False
    track, entry = found
    if not entry.slug or not track_open(track, cleared):
        return False
    if entry.capstone:
        done = sum(1 for e in track.entries if not e.capstone and e.id in cleared)
        return done >= min(CAPSTONE_AFTER, sum(1 for e in track.entries if not e.capstone))
    return True


def missing_requirements(entry: LabEntry) -> list[str]:
    """Third-party modules this mission needs that aren't installed (shown as `pip install ...`)."""
    return [name for name in entry.requires if importlib.util.find_spec(name) is None]


def load_mission(slug: str) -> Mission:
    mission = importlib.import_module(f"lab.{slug}").MISSION
    mission.grader_key = f"lab:{slug}"
    return mission
