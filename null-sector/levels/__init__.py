"""The campaign: 5 sectors, Zero to Hero. Each sector ends with a boss and a cutscene.

A level with slug=None is still encrypted (not built yet) and shows on the map as locked.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, replace
from pathlib import Path

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


# Every level has a module name; a level is "built" once levels/<slug>.py exists, otherwise its
# slug is cleared below and it shows as encrypted. Content authors only ever add files.
_CAMPAIGN = (
    Sector(0, "ZERO", "The Dead Zone", "#39ff14", (
        LevelEntry("L01", "COLD BOOT", "Variables & data types", "level_01_cold_boot"),
        LevelEntry("L02", "SIGNAL NOISE", "Strings & cleaning text", "level_02_signal_noise"),
        LevelEntry("L03", "SCRAP INVENTORY", "Lists, indexing & slicing", "level_03_scrap_inventory"),
        LevelEntry("L04", "CACHE RAID", "Dictionaries & lookups", "level_04_cache_raid"),
        LevelEntry("L05", "BOSS: THE WARDEN", "Everything in Sector 0", "level_05_the_warden"),
    )),
    Sector(1, "LOGIC", "The Grid", "#00f0ff", (
        LevelEntry("L06", "TRIPWIRE", "if / elif / else", "level_06_tripwire"),
        LevelEntry("L07", "PATROL ROUTES", "Loops & comprehensions", "level_07_patrol_routes"),
        LevelEntry("L08", "OVERCLOCK", "while loops & break", "level_08_overclock"),
        LevelEntry("L09", "SUBROUTINES", "Functions, params & return", "level_09_subroutines"),
        LevelEntry("L10", "BOSS: THE ARBITER", "A rule-based classifier", "level_10_the_arbiter"),
    )),
    Sector(2, "ARCHITECT", "The Foundry", "#ffb000", (
        LevelEntry("L11", "BLUEPRINTS", "Classes & objects", "level_11_blueprints"),
        LevelEntry("L12", "BLOODLINES", "Inheritance & dataclasses", "level_12_bloodlines"),
        LevelEntry("L13", "BLACK BOX", "Reading & writing files", "level_13_black_box"),
        LevelEntry("L14", "FAILSAFE", "Exceptions & validation", "level_14_failsafe"),
        LevelEntry("L15", "BOSS: THE FORGEMASTER", "A Dataset class that loads CSVs", "level_15_the_forgemaster"),
    )),
    Sector(3, "DATA", "The Archive", "#b388ff", (
        LevelEntry("L16", "DATA STREAMS", "JSON & nested data", "level_16_data_streams"),
        LevelEntry("L17", "GHOST SIGNALS", "Parsing HTML (web scraping)", "level_17_ghost_signals"),
        LevelEntry("L18", "THE VAULT", "SQLite: tables & inserts", "level_18_the_vault"),
        LevelEntry("L19", "QUERY ENGINE", "SQL queries & aggregates", "level_19_query_engine"),
        LevelEntry("L20", "BOSS: THE LIBRARIAN", "An ETL data pipeline", "level_20_the_librarian"),
    )),
    Sector(4, "HERO", "The Core", "#ff2bd6", (
        LevelEntry("L21", "SYNAPSE", "A single neuron from scratch", "level_21_synapse"),
        LevelEntry("L22", "DESCENT", "Loss & gradient descent", "level_22_descent"),
        LevelEntry("L23", "NEURAL MESH", "Backprop: a 2-layer network", "level_23_neural_mesh"),
        LevelEntry("L24", "OPEN CHANNEL", "Calling an LLM API", "level_24_open_channel"),
        LevelEntry("L25", "BOSS: THE CORE", "An AI agent that uses tools", "level_25_the_core"),
    )),
)

_HERE = Path(__file__).resolve().parent


def _built(entry: LevelEntry) -> LevelEntry:
    return entry if entry.slug and (_HERE / f"{entry.slug}.py").exists() else replace(entry, slug=None)


CAMPAIGN = tuple(replace(sector, levels=tuple(_built(l) for l in sector.levels)) for sector in _CAMPAIGN)

ALL_LEVELS = [lvl for sector in CAMPAIGN for lvl in sector.levels]


def sector_of(level_id: str) -> Sector:
    return next(s for s in CAMPAIGN if any(l.id == level_id for l in s.levels))


def load_mission(slug: str) -> Mission:
    return importlib.import_module(f"levels.{slug}").MISSION


def next_level(cleared: dict) -> LevelEntry | None:
    """The first level you haven't cleared yet (it may still be encrypted)."""
    return next((lvl for lvl in ALL_LEVELS if lvl.id not in cleared), None)
