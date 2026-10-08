"""Mastery: how well you know each of the 28 Python concepts (docs/GAME_DESIGN.md §3.3).

Every time you write code that passes real tests, the concepts that code exercised earn
mastery points. Points turn into a level from 0 to 5 (MAX), shown in the hub as a skill
matrix. There is no way to earn points except by clearing challenges:

    =====================  ==========================================
    what you cleared       points, for EACH concept the challenge uses
    =====================  ==========================================
    a campaign level       +40 (first clear only: replays give nothing)
    a drill                +10 x tier (only the first clear of a seed)
    an arena match (win)   +5 x tier
    =====================  ==========================================

This module is *pure*: it never reads files, the network or the clock. Every function
takes a "save" (any object with a ``mastery`` attribute, normally ``engine.state.Save``)
and either reads it or updates ``save.mastery`` in place. Old saves that have no
``mastery`` field, or a broken one, are treated as "no points yet" and never crash.

Example::

    >>> from types import SimpleNamespace
    >>> save = SimpleNamespace(mastery={})
    >>> award(save, ["strings"], 60)
    [{'concept': 'strings', 'before': 0, 'after': 60, 'level_before': 0, 'level_after': 1}]
    >>> level_for(55)
    1
"""
from __future__ import annotations

from typing import Iterable

from engine.drills import CONCEPTS

# Points needed to *reach* each level. Index = level, so THRESHOLDS[1] == 50 means
# "level 1 starts at 50 points". The last entry is level 5, which the UI shows as MAX.
THRESHOLDS: tuple[int, ...] = (0, 50, 150, 350, 700, 1200)
MAX_LEVEL = len(THRESHOLDS) - 1

CAMPAIGN_POINTS = 40          # per concept, on a level's first clear
DRILL_POINTS_PER_TIER = 10    # per concept x tier, first clear of a seed only
ARENA_POINTS_PER_TIER = 5     # per concept x tier, arena wins only

LEVEL_NAMES = ("UNTRAINED", "INITIATE", "ADEPT", "PRACTITIONER", "EXPERT", "MAX")


# ── reading the save safely ──────────────────────────────────────────────────────────

def _points_table(save) -> dict:
    """The save's concept -> points dict, or an empty dict if it is missing or malformed.

    Read-only callers use this so that looking at an old save never changes it.
    """
    table = getattr(save, "mastery", None)
    return table if isinstance(table, dict) else {}


def _points(table: dict, concept: str) -> int:
    """Points for one concept. Anything that isn't a non-negative whole number counts as 0."""
    value = table.get(concept, 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


# ── levels ───────────────────────────────────────────────────────────────────────────

def level_for(points: int) -> int:
    """The mastery level (0..5) that `points` reaches.

    We walk the thresholds from the top down and return the first one we have passed:

        >>> [level_for(p) for p in (0, 49, 50, 149, 150, 1199, 1200, 99999)]
        [0, 0, 1, 1, 2, 4, 5, 5]
    """
    for level in range(MAX_LEVEL, -1, -1):
        if points >= THRESHOLDS[level]:
            return level
    return 0   # negative points can't happen, but never crash on them


def next_at(points: int) -> int | None:
    """Points needed for the next level, or None once the concept is at MAX."""
    level = level_for(points)
    return THRESHOLDS[level + 1] if level < MAX_LEVEL else None


def level_of(save, concept: str) -> int:
    """The current level of one concept in this save (0 for unknown concepts)."""
    return level_for(_points(_points_table(save), concept))


def rows(save) -> list[dict]:
    """The skill matrix: one row per concept, always all 28, in the fixed CONCEPTS order.

    Each row is ``{concept, points, level, next_at}`` exactly as ``Training.mastery``
    (§7) expects. ``next_at`` is None at MAX.
    """
    table = _points_table(save)
    out = []
    for concept in CONCEPTS:
        points = _points(table, concept)
        out.append({"concept": concept, "points": points, "level": level_for(points),
                    "next_at": next_at(points)})
    return out


def average_level(save) -> float:
    """The mean level over all 28 concepts, rounded to 2 decimals (the hub's MASTERY tile)."""
    table = _points_table(save)
    total = sum(level_for(_points(table, c)) for c in CONCEPTS)
    return round(total / len(CONCEPTS), 2)


def maxed_concepts(save) -> list[str]:
    """Concepts at level 5, in CONCEPTS order (used for the earned mastery titles)."""
    table = _points_table(save)
    return [c for c in CONCEPTS if level_for(_points(table, c)) == MAX_LEVEL]


def highest_level(save) -> int:
    """The best level of any single concept (augment ZERO-DAY unlocks at 4)."""
    table = _points_table(save)
    return max((level_for(_points(table, c)) for c in CONCEPTS), default=0)


# ── awarding ─────────────────────────────────────────────────────────────────────────

def _clean_concepts(concepts: Iterable[str] | str | None) -> list[str]:
    """Known concept tags, each once, in the order given.

    A single string counts as one tag (a classic Python trap: iterating "loops" would
    give the letters l, o, o, p, s). Unknown tags are ignored rather than raising, so
    a typo in content can never block a reward.
    """
    if concepts is None:
        return []
    if isinstance(concepts, str):
        concepts = [concepts]
    seen: list[str] = []
    for concept in concepts:
        if concept in CONCEPTS and concept not in seen:
            seen.append(concept)
    return seen


def award(save, concepts: Iterable[str] | str | None, points: int) -> list[dict]:
    """Add `points` to every concept in `concepts` and report what changed.

    Returns one entry per concept actually awarded::

        {"concept", "before", "after", "level_before", "level_after"}

    which is exactly the ``RunResult.outcome.mastery`` list (§7). Zero or negative
    points award nothing and return ``[]``; unknown concepts are skipped. If the save
    has no usable ``mastery`` dict yet, one is created.
    """
    points = int(points) if isinstance(points, (int, float)) and not isinstance(points, bool) else 0
    tags = _clean_concepts(concepts)
    if points <= 0 or not tags:
        return []
    table = getattr(save, "mastery", None)
    if not isinstance(table, dict):
        table = {}
        save.mastery = table
    changes = []
    for concept in tags:
        before = _points(table, concept)
        after = before + points
        table[concept] = after
        changes.append({"concept": concept, "before": before, "after": after,
                        "level_before": level_for(before), "level_after": level_for(after)})
    return changes


def campaign_points() -> int:
    """Points per concept for a campaign level's first clear."""
    return CAMPAIGN_POINTS


def drill_points(tier: int, first_seed_clear: bool = True) -> int:
    """Points per concept for a drill clear: 10 x tier, but only the first clear of a seed.

    Re-solving a seed you already beat is still good practice, it just isn't *new*
    evidence of skill, so it pays 0.
    """
    return DRILL_POINTS_PER_TIER * _tier(tier) if first_seed_clear else 0


def arena_points(tier: int, won: bool = True) -> int:
    """Points per concept for an arena match: 5 x tier on a win, 0 on a loss."""
    return ARENA_POINTS_PER_TIER * _tier(tier) if won else 0


def award_campaign(save, concepts) -> list[dict]:
    """Shortcut: award a campaign level's first clear."""
    return award(save, concepts, campaign_points())


def award_drill(save, concepts, tier: int, first_seed_clear: bool) -> list[dict]:
    """Shortcut: award a drill clear (practice, contract or ghost)."""
    return award(save, concepts, drill_points(tier, first_seed_clear))


def award_arena(save, concepts, tier: int, won: bool) -> list[dict]:
    """Shortcut: award an arena result."""
    return award(save, concepts, arena_points(tier, won))


def _tier(tier) -> int:
    """Clamp a tier into 1..5 (bad input becomes 1, never an exception)."""
    try:
        return max(1, min(5, int(tier)))
    except (TypeError, ValueError):
        return 1
