"""The campaign: 5 sectors, Zero to Hero. Each sector ends with a boss and a cutscene.

A level with slug=None is still encrypted (not built yet) and shows on the map as locked.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass

from engine.mission import Mission


@dataclass(frozen=True)
class LevelEntry:
    id: str
    title: str
    concept: str
    slug: str | None = None    # module in levels/ once built


@dataclass(frozen=True)
class Sector:
    tier: int
    name: str
    zone: str
    color: str
    levels: tuple[LevelEntry, ...]


CAMPAIGN = (
    Sector(0, "ZERO", "The Dead Zone", "#39ff14", (
        LevelEntry("L01", "COLD BOOT", "Variables & data types", "level_01_cold_boot"),
        LevelEntry("L02", "SIGNAL NOISE", "Strings & cleaning text"),
        LevelEntry("L03", "SCRAP INVENTORY", "Lists, indexing & slicing"),
        LevelEntry("L04", "CACHE RAID", "List methods & basic stats"),
        LevelEntry("L05", "BOSS: THE WARDEN", "Everything in Sector 0"),
    )),
    Sector(1, "LOGIC", "The Grid", "#00f0ff", (
        LevelEntry("L06", "TRIPWIRE", "if / elif / else"),
        LevelEntry("L07", "PATROL ROUTES", "for loops & range"),
        LevelEntry("L08", "OVERCLOCK", "while loops & break"),
        LevelEntry("L09", "SUBROUTINES", "Functions, params & return"),
        LevelEntry("L10", "BOSS: THE ARBITER", "A rule-based classifier"),
    )),
    Sector(2, "ARCHITECT", "The Foundry", "#ffb000", (
        LevelEntry("L11", "BLUEPRINTS", "Classes & objects"),
        LevelEntry("L12", "BLOODLINES", "Inheritance"),
        LevelEntry("L13", "BLACK BOX", "Reading & writing files"),
        LevelEntry("L14", "FAILSAFE", "Exceptions & context managers"),
        LevelEntry("L15", "BOSS: THE FORGEMASTER", "A Dataset class that loads CSVs"),
    )),
    Sector(3, "DATA", "The Archive", "#b388ff", (
        LevelEntry("L16", "DATA STREAMS", "JSON & dictionaries"),
        LevelEntry("L17", "GHOST SIGNALS", "Web scraping"),
        LevelEntry("L18", "THE VAULT", "SQLite: tables & inserts"),
        LevelEntry("L19", "QUERY ENGINE", "SQL queries & aggregates"),
        LevelEntry("L20", "BOSS: THE LIBRARIAN", "A scrape -> clean -> store pipeline"),
    )),
    Sector(4, "HERO", "The Core", "#ff2bd6", (
        LevelEntry("L21", "SYNAPSE", "A single neuron from scratch"),
        LevelEntry("L22", "DESCENT", "Loss & gradient descent"),
        LevelEntry("L23", "NEURAL MESH", "A 2-layer network in NumPy"),
        LevelEntry("L24", "OPEN CHANNEL", "Calling an LLM API"),
        LevelEntry("L25", "BOSS: THE CORE", "An AI agent that uses tools"),
    )),
)

ALL_LEVELS = [lvl for sector in CAMPAIGN for lvl in sector.levels]


def sector_of(level_id: str) -> Sector:
    return next(s for s in CAMPAIGN if any(l.id == level_id for l in s.levels))


def load_mission(slug: str) -> Mission:
    return importlib.import_module(f"levels.{slug}").MISSION


def next_level(cleared: dict) -> LevelEntry | None:
    """The first level you haven't cleared yet (it may still be encrypted)."""
    return next((lvl for lvl in ALL_LEVELS if lvl.id not in cleared), None)
