"""Persistent game state: config.json (settings + API keys) and save.json (your progress).

Every filesystem location lives in one `Paths` value. The defaults are the real
game folders; tests and tools pass `Paths.rooted(tmp)` so they never touch your
actual save, config or mission files.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
import shutil
import tempfile
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


@dataclass(frozen=True)
class Paths:
    """Where the game reads and writes. `game_dir` is the root that mission paths are shown relative to."""

    game_dir: Path = GAME_DIR
    missions_dir: Path = MISSIONS_DIR
    save_path: Path = SAVE_PATH
    config_path: Path = CONFIG_PATH
    config_template: Path = CONFIG_TEMPLATE
    cutscene_dir: Path = CUTSCENE_DIR

    @classmethod
    def rooted(cls, root: Path | str) -> "Paths":
        """Every writable location inside `root` (the config template is still read from the game)."""
        root = Path(root)
        return cls(game_dir=root, missions_dir=root / "missions", save_path=root / "save.json",
                   config_path=root / "config.json", config_template=CONFIG_TEMPLATE,
                   cutscene_dir=root / "cutscenes")


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file + rename, so a crash or a concurrent reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        mode = 0o644
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.chmod(tmp, mode)   # mkstemp creates 0600; keep the file's normal permissions
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(paths: Paths | None = None) -> dict:
    """Read config.json, creating it from the template on first run.

    Keys missing from your config fall back to the template, so a new game
    version never crashes on an old config.
    """
    paths = paths or Paths()
    if not paths.config_path.exists():
        paths.config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(paths.config_template, paths.config_path)
    defaults = json.loads(paths.config_template.read_text(encoding="utf-8"))
    user = json.loads(paths.config_path.read_text(encoding="utf-8"))
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

    def __post_init__(self) -> None:
        self._path = SAVE_PATH   # plain attribute, not a field: never serialized

    @classmethod
    def load(cls, path: Path | None = None) -> "Save":
        path = Path(path) if path else SAVE_PATH
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            save = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        else:
            save = cls()
        save._path = path
        return save

    @property
    def path(self) -> Path:
        return self._path

    def write(self) -> None:
        atomic_write_text(self._path, json.dumps(asdict(self), indent=2))

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
        if mission_id not in self.started_at:
            self.started_at[mission_id] = time.time()
            self.write()

    def record_attempt(self, mission_id: str) -> int:
        self.attempts[mission_id] = self.attempts.get(mission_id, 0) + 1
        self.write()
        return self.attempts[mission_id]

    def elapsed(self, mission_id: str) -> float:
        return time.time() - self.started_at.get(mission_id, time.time())
