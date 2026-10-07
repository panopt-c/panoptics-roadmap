"""Persistent game state: config.json (settings + API keys) and save.json (your progress)."""
from __future__ import annotations

import copy
import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = GAME_DIR / "config.json"
CONFIG_TEMPLATE = GAME_DIR / "config.example.json"
SAVE_PATH = GAME_DIR / "save.json"
MISSIONS_DIR = GAME_DIR / "missions"
CUTSCENE_DIR = GAME_DIR / "cutscenes"

# (XP needed, title). Your rank is the last row whose XP you've reached.
RANKS = [
    (0, "GHOST PROCESS"),
    (100, "SCRIPT KIDDIE"),
    (400, "CODE RUNNER"),
    (1000, "NETRUNNER"),
    (2000, "SYSTEM ARCHITECT"),
    (3500, "DATA WRAITH"),
    (5500, "NEURAL ENGINEER"),
    (8000, "ARCHITECT OF THE CORE"),
]


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict:
    """Read config.json, creating it from the template on first run.

    Keys missing from your config fall back to the template, so a new game
    version never crashes on an old config.
    """
    if not CONFIG_PATH.exists():
        shutil.copy(CONFIG_TEMPLATE, CONFIG_PATH)
    defaults = json.loads(CONFIG_TEMPLATE.read_text(encoding="utf-8"))
    user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return _deep_merge(defaults, user)


@dataclass
class Save:
    callsign: str = ""
    xp: int = 0
    cleared: dict = field(default_factory=dict)      # mission id -> {xp, attempts, seconds}
    attempts: dict = field(default_factory=dict)     # mission id -> hack attempts so far
    started_at: dict = field(default_factory=dict)   # mission id -> unix time first deployed
    avatar_url: str = ""                             # anchor frame for character consistency
    gallery: list = field(default_factory=list)      # generated cutscenes

    @classmethod
    def load(cls) -> "Save":
        if not SAVE_PATH.exists():
            return cls()
        data = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def write(self) -> None:
        SAVE_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    # ── progression ─────────────────────────────────────────
    def rank(self) -> tuple[str, int, int | None]:
        """Return (title, xp floor of this rank, xp needed for next rank or None at max)."""
        title, floor, nxt = RANKS[0][1], 0, None
        for i, (need, name) in enumerate(RANKS):
            if self.xp >= need:
                title, floor = name, need
                nxt = RANKS[i + 1][0] if i + 1 < len(RANKS) else None
        return title, floor, nxt

    def deploy(self, mission_id: str) -> None:
        self.started_at.setdefault(mission_id, time.time())
        self.write()

    def record_attempt(self, mission_id: str) -> int:
        self.attempts[mission_id] = self.attempts.get(mission_id, 0) + 1
        self.write()
        return self.attempts[mission_id]

    def elapsed(self, mission_id: str) -> float:
        return time.time() - self.started_at.get(mission_id, time.time())
