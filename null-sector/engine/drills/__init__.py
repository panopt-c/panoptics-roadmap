"""Drills: procedural, seeded coding challenges (docs/GAME_DESIGN.md §3.1).

A drill is a generator. Given a seed it builds a fresh `Mission` with randomized data;
the player implements a function, and the checks call it on generated cases and compare
against a reference implementation. The same seed always builds the same mission, in any
process, which is how the server and the sandboxed grader agree on what was asked.

Authoring a drill (in engine/drills/library/<anything>.py):

    from engine.drills import Drill, compare_cases, make_mission, register

    def _build(rng):
        words = [rng.choice(WORDS) for _ in range(6)]
        mission = make_mission(
            title="REVERSE THE STREAM", tier=1, concepts=("strings", "lists"),
            prompt="Write `reverse_words(text)` that returns the words in reverse order.",
            starter='def reverse_words(text):\n    # your code\n    pass\n',
        )

        @mission.check("reverse_words on intercepted packets")
        def _(ctx):
            cases = [(" ".join(words),), ("",), ("solo",)]
            compare_cases(ctx, "reverse_words", cases, lambda t: " ".join(t.split()[::-1]))

        return mission

    register(Drill("t1-reverse-words", "REVERSE THE STREAM", 1, ("strings", "lists"), 240, _build))
"""
from __future__ import annotations

import copy
import importlib
import math
import pkgutil
import random
import re
from dataclasses import dataclass
from typing import Callable

from engine.mission import Fail, Mission

TIER_LABELS = {1: "Beginner", 2: "Beginner+", 3: "Intermediate", 4: "Intermediate+", 5: "Expert"}

CONCEPTS = (
    "variables", "types", "strings", "lists", "dicts", "tuples-sets", "conditionals", "loops",
    "comprehensions", "functions", "sorting", "recursion", "classes", "inheritance", "files",
    "exceptions", "json", "parsing", "regex", "sql", "algorithms", "generators", "decorators",
    "numeric", "ml-math", "neural-nets", "apis", "agents",
    # THE LAB (GAME_DESIGN §13)
    "numpy", "pandas", "statistics", "evaluation", "nlp",
)

DRILL_XP = {1: 40, 2: 60, 3: 85, 4: 110, 5: 140}       # first clear of a seed
DRILL_CREDITS = {t: 8 * t for t in TIER_LABELS}          # GAME_DESIGN §3.4

_ID = re.compile(r"^t[1-5]-[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Drill:
    id: str                       # "t1-reverse-words": tier prefix + kebab name
    title: str                    # shown in the catalog, uppercase
    tier: int                     # 1..5
    concepts: tuple[str, ...]     # mastery tags from CONCEPTS
    par_seconds: int              # an engaged player at this tier should finish in this time
    build: Callable[[random.Random], Mission]


_REGISTRY: dict[str, Drill] = {}
_loaded = False


def register(drill: Drill) -> Drill:
    if not _ID.match(drill.id) or int(drill.id[1]) != drill.tier:
        raise ValueError(f"drill id {drill.id!r} must look like 't{drill.tier}-kebab-name'")
    unknown = set(drill.concepts) - set(CONCEPTS)
    if unknown or not drill.concepts:
        raise ValueError(f"drill {drill.id}: unknown or missing concepts {sorted(unknown)}")
    if drill.id in _REGISTRY and _REGISTRY[drill.id] is not drill:
        raise ValueError(f"duplicate drill id {drill.id}")
    _REGISTRY[drill.id] = drill
    return drill


def _load_library() -> None:
    global _loaded
    if _loaded:
        return
    from engine.drills import library
    for info in sorted(pkgutil.iter_modules(library.__path__), key=lambda m: m.name):
        importlib.import_module(f"{library.__name__}.{info.name}")
    _loaded = True


def all_drills() -> list[Drill]:
    _load_library()
    return sorted(_REGISTRY.values(), key=lambda d: (d.tier, d.id))


def get(drill_id: str) -> Drill:
    _load_library()
    return _REGISTRY[drill_id]


def instance(drill_id: str, seed: int) -> Mission:
    """Build the Mission for (drill, seed). Deterministic across processes."""
    drill = get(drill_id)
    rng = random.Random(f"{drill_id}:{int(seed)}")   # str seeds hash with SHA-512: stable everywhere
    mission = drill.build(rng)
    mission.id = f"D:{drill_id}:{int(seed)}"
    mission.slug = drill_id.replace("-", "_")
    mission.grader_key = f"drill:{drill_id}:{int(seed)}"
    mission.tier = drill.tier
    mission.concepts = tuple(drill.concepts)
    mission.par_seconds = drill.par_seconds
    if not mission.xp:
        mission.xp = DRILL_XP[drill.tier]
    return mission


def daily_contracts(date: str, player_tier: int) -> list[str]:
    """Three distinct drills for a local date (YYYY-MM-DD): one at the player's tier, plus neighbours."""
    tier = max(1, min(5, int(player_tier)))
    pool = all_drills()
    rng = random.Random(f"contracts:{date}:{tier}")
    picks: list[str] = []
    for want in (tier, max(1, tier - 1), min(5, tier + 1)):
        options = [d.id for d in pool if d.tier == want and d.id not in picks] or \
                  [d.id for d in pool if d.id not in picks]
        if options:
            picks.append(rng.choice(sorted(options)))
    return picks


# ── authoring helpers ─────────────────────────────────────────────────────────────────

def make_mission(*, title: str, prompt: str, starter: str, tier: int, concepts: tuple[str, ...],
                 manual: str = "", enemy: str = "SPARRING ICE", xp: int = 0, timeout: float = 10.0) -> Mission:
    """A drill mission: `prompt` is the brief (markdown), `manual` an optional refresher."""
    return Mission(
        id="", slug="", title=title, concept=", ".join(concepts), enemy=enemy, xp=xp, par_seconds=0,
        briefing=prompt, why="", manual=manual, starter=starter, timeout=timeout,
        run_as_main=False, tier=tier, concepts=tuple(concepts),
    )


def _short(value, limit: int = 140) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _close(a, b, rel_tol: float, abs_tol: float) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(_close(x, y, rel_tol, abs_tol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k], rel_tol, abs_tol) for k in a)
    return a == b


def compare_cases(ctx, func_name: str, cases, reference: Callable, *, approx: bool = False,
                  rel_tol: float = 1e-6, abs_tol: float = 1e-9, hint: str = "") -> None:
    """Call the player's `func_name` on each case and compare with `reference`.

    `cases` is a list of argument tuples (or dicts of keyword arguments). Arguments are
    deep-copied for both calls, so a function that mutates its input can't poison the
    comparison. The first mismatch fails with the exact input, expected and actual value.
    """
    fn = ctx.get(func_name)
    if not callable(fn):
        raise Fail(f"`{func_name}` exists but isn't a function.", hint=f"Define it with  def {func_name}(...):")
    for case in cases:
        args, kwargs = ((), dict(case)) if isinstance(case, dict) else (tuple(case), {})
        shown = ", ".join([_short(a, 60) for a in args] + [f"{k}={_short(v, 60)}" for k, v in kwargs.items()])
        expected = reference(*copy.deepcopy(args), **copy.deepcopy(kwargs))
        try:
            got = fn(*copy.deepcopy(args), **copy.deepcopy(kwargs))
        except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
            raise Fail(f"`{func_name}({shown})` raised {type(exc).__name__}: {exc}",
                       hint=hint or "Run your function on this input yourself and read the error.")
        same = _close(got, expected, rel_tol, abs_tol) if approx else (got == expected and type(got) is type(expected))
        if not same:
            raise Fail(f"`{func_name}({shown})` returned {_short(got)} — expected {_short(expected)}.",
                       hint=hint)
