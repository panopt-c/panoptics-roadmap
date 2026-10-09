"""Persistent game state: config.json (settings + API keys) and save.json (your progress).

Every filesystem location lives in one `Paths` value. The defaults are the real
game folders; tests and tools pass `Paths.rooted(tmp)` so they never touch your
actual save, config or mission files.

save.json is shared by every NULL//SECTOR process on this machine (the web
server, `python game.py tui`, `hack` and `watch`), so it is handled like a tiny
database:

  * Writes are atomic and durable: temp file, fsync, rename, fsync of the folder.
  * Every change is a locked read-modify-write (`Save.transaction()`): an OS lock
    on the sidecar file `save.json.lock` (fcntl on POSIX, msvcrt on Windows), a
    re-read of save.json, the change, the write. A clear made in the terminal is
    never overwritten by a stale copy held by the web server, or vice versa.
  * `Save.refresh()` adopts changes another process wrote. It updates the object
    *in place*, because the cutscene renderer and the TUI hold references to it.
  * The lock is held for milliseconds only (never while player code is graded).
  * A damaged save.json never stops the game: it is moved aside as
    `save.json.corrupt-<time>` and the game carries on (fresh at launch, or with the
    last good progress mid-session), with a notice explaining what happened.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

if os.name == "nt":  # pragma: no cover - exercised on Windows only
    import msvcrt
else:
    import fcntl

GAME_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = GAME_DIR / "config.json"
CONFIG_TEMPLATE = GAME_DIR / "config.example.json"
SAVE_PATH = GAME_DIR / "save.json"
MISSIONS_DIR = GAME_DIR / "missions"
CUTSCENE_DIR = GAME_DIR / "cutscenes"

LOCK_TIMEOUT = 20.0          # seconds to wait for another process's save.json write (normally milliseconds)

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


# ── durable files ───────────────────────────────────────────
def _fsync_dir(directory: Path) -> None:
    """Make a rename durable. Windows cannot open folders; NTFS journals the rename itself."""
    if os.name == "nt":  # pragma: no cover
        return
    try:
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _replace(src: str, dst: Path) -> None:
    """os.replace, retried briefly on Windows where a scanner or reader can hold the target open."""
    for attempt in range(20):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 19:
                raise
            time.sleep(0.05)


def atomic_write_text(path: Path, text: str, *, durable: bool = True) -> None:
    """Write via a temp file + fsync + rename (+ fsync of the folder).

    A crash, a power cut or a concurrent reader never sees half a file: readers get
    the old content or the new content, and after a power cut the new content is
    on disk once this returns.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        mode = 0o644
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            if durable:
                os.fsync(handle.fileno())
        os.chmod(tmp, mode)   # mkstemp creates 0600; keep the file's normal permissions
        _replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    if durable:
        _fsync_dir(path.parent)


# ── the cross-process lock ──────────────────────────────────
class SaveLockTimeout(TimeoutError):
    """Another process held save.json's lock for far longer than any write takes."""


class _ProcessLock:
    """One per lock file per process: re-entrant for a thread, exclusive across threads and processes."""

    def __init__(self, path: Path):
        self.path = path
        self.mutex = threading.RLock()
        self.depth = 0
        self.handle = None

    def acquire(self, timeout: float) -> None:
        if not self.mutex.acquire(timeout=timeout):
            raise SaveLockTimeout(f"{self.path.name} is busy in this process")
        if self.depth == 0:
            try:
                self.handle = self._lock_file(timeout)
            except BaseException:
                self.mutex.release()
                raise
        self.depth += 1

    def release(self) -> None:
        self.depth -= 1
        if self.depth == 0 and self.handle is not None:
            handle, self.handle = self.handle, None
            try:
                if os.name == "nt":  # pragma: no cover
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            finally:
                handle.close()
        self.mutex.release()

    def _lock_file(self, timeout: float):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(self.path, "a+b")
        except OSError:
            return None        # read-only install: nothing can write, so there is nothing to coordinate
        deadline = time.monotonic() + timeout
        delay = 0.002
        while True:
            try:
                if os.name == "nt":  # pragma: no cover
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return handle
            except OSError:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise SaveLockTimeout(f"another NULL//SECTOR process is holding {self.path.name}") from None
                time.sleep(delay)
                delay = min(delay * 2, 0.05)


_LOCKS: dict[str, _ProcessLock] = {}
_LOCKS_GUARD = threading.Lock()


@contextlib.contextmanager
def interprocess_lock(path: Path, timeout: float = LOCK_TIMEOUT):
    """Exclusive lock on `path` (a sidecar file) across threads and processes; re-entrant per thread."""
    key = os.path.abspath(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = _LOCKS[key] = _ProcessLock(Path(key))
    lock.acquire(timeout)
    try:
        yield
    finally:
        lock.release()


def _signature(path: Path) -> tuple[int, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_ino, st.st_mtime_ns, st.st_size


def quarantine(path: Path, *, copy_only: bool = False) -> Path | None:
    """Move (or copy) a damaged file aside as `<name>.corrupt-<YYYYmmdd-HHMMSS>[-n]`. Never overwrites."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for n in range(100):
        target = path.with_name(f"{path.name}.corrupt-{stamp}" + (f"-{n}" if n else ""))
        if target.exists():
            continue
        try:
            if copy_only:
                target.write_bytes(path.read_bytes())
            else:
                os.replace(path, target)
            return target
        except OSError:
            return None
    return None


# ── config.json ─────────────────────────────────────────────
def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(paths: Paths | None = None, notices: list | None = None) -> dict:
    """Read config.json, creating it from the template on first run.

    Keys missing from your config fall back to the template, so a new game
    version never crashes on an old config. A config.json that is not valid JSON
    is left untouched (it holds your API keys) and the defaults are used, with a
    notice appended to `notices`.
    """
    paths = paths or Paths()
    if not paths.config_path.exists():
        paths.config_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(paths.config_path, paths.config_template.read_text(encoding="utf-8"))
    defaults = json.loads(paths.config_template.read_text(encoding="utf-8"))
    try:
        user = json.loads(paths.config_path.read_text(encoding="utf-8"))
        if not isinstance(user, dict):
            raise ValueError("it must hold a JSON object")
    except (OSError, ValueError, RecursionError) as exc:
        if notices is not None:
            notices.append(f"{paths.config_path.name} could not be read ({_reason(exc)}); using the default "
                           f"settings. Fix the file or delete it to regenerate it.")
        return defaults
    return _deep_merge(defaults, user)


def _reason(exc: BaseException) -> str:
    if isinstance(exc, json.JSONDecodeError):
        return f"invalid JSON at line {exc.lineno}, column {exc.colno}"
    if isinstance(exc, UnicodeDecodeError):
        return "it is not UTF-8 text"
    if isinstance(exc, RecursionError):
        return "it is nested too deeply"
    return str(exc) or type(exc).__name__


# ── save.json ───────────────────────────────────────────────
def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# field -> (container check, per-item check or None)
_SAVE_SCHEMA = {
    "callsign": (lambda v: isinstance(v, str), None),
    "xp": (lambda v: _is_int(v) and v >= 0, None),
    "cleared": (lambda v: isinstance(v, dict), lambda k, v: isinstance(k, str) and isinstance(v, dict)),
    "attempts": (lambda v: isinstance(v, dict), lambda k, v: isinstance(k, str) and _is_int(v) and v >= 0),
    "started_at": (lambda v: isinstance(v, dict), lambda k, v: isinstance(k, str) and _is_number(v)),
    "avatar_url": (lambda v: isinstance(v, str), None),
    "gallery": (lambda v: isinstance(v, list), lambda _i, v: isinstance(v, dict)),
}
def parse_save(text: str) -> tuple[dict, list[str]]:
    """save.json text → (Save field values, problems found). Raises ValueError when it is not a save at all.

    Fields with the wrong shape fall back to their defaults (and are reported), so
    one bad value never takes the rest of your progress with it.
    """
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("it must hold a JSON object")
    values, problems = {}, []
    for name, (valid, item_ok) in _SAVE_SCHEMA.items():
        if name not in data:
            continue
        value = data[name]
        if not valid(value):
            problems.append(name)
            continue
        if item_ok is not None:
            items = value.items() if isinstance(value, dict) else enumerate(value)
            kept = [(k, v) for k, v in items if item_ok(k, v)]
            if len(kept) != len(value):
                problems.append(name)
            value = dict(kept) if isinstance(value, dict) else [v for _k, v in kept]
        values[name] = value
    return values, problems


def _unknown_keys(text: str) -> dict:
    """Top-level save.json keys that `Save` has no field for (written by another game version)."""
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return {}
    if not isinstance(data, dict):
        return {}
    known = {f.name for f in fields(Save)}
    return {k: v for k, v in data.items() if isinstance(k, str) and k not in known}


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
        # Plain attributes, not fields: never serialized.
        self._path = SAVE_PATH
        self._sig = None          # (inode, mtime_ns, size) of the save.json this object mirrors
        self._raw = None          # that file's text, to tell real changes from a touch
        self._notices: list[str] = []
        self._extra: dict = {}    # top-level keys this version does not know (kept, never dropped)
        self.reloads = 0          # how many times changes written by another process were adopted

    @classmethod
    def load(cls, path: Path | None = None) -> "Save":
        """Read save.json (missing → a fresh save). A damaged file is moved aside and the game starts fresh."""
        save = cls()
        save._path = Path(path) if path else SAVE_PATH
        with interprocess_lock(save.lock_path):
            save._reload_locked(startup=True)
        save.reloads = 0
        return save

    @property
    def path(self) -> Path:
        return self._path

    @property
    def lock_path(self) -> Path:
        return self._path.with_name(self._path.name + ".lock")

    def take_notices(self) -> list[str]:
        """Messages about damaged files found while loading or refreshing (each returned once)."""
        notices, self._notices = self._notices, []
        return notices

    # ── cross-process sync ──────────────────────────────────
    def refresh(self) -> bool:
        """Adopt changes another process wrote to save.json. True when the progress changed."""
        if _signature(self._path) == self._sig:
            return False
        with interprocess_lock(self.lock_path):
            return self._reload_locked()

    @contextlib.contextmanager
    def transaction(self):
        """Locked read-modify-write: re-read save.json, let the caller change this object, write it back.

        If the body raises, nothing is written and the in-memory object is rolled back,
        so a half-applied change can never leak into a later write.
        """
        with interprocess_lock(self.lock_path):
            self._reload_locked()
            before = asdict(self)
            try:
                yield self
            except BaseException:
                for name, value in before.items():
                    setattr(self, name, value)
                raise
            if asdict(self) != before or self._sig is None:
                self._write_locked()

    def write(self) -> None:
        """Write this object as it is (under the lock). Prefer transaction() for changes."""
        with interprocess_lock(self.lock_path):
            self._write_locked()

    def _write_locked(self) -> None:
        data = {**self._extra, **asdict(self)}
        text = json.dumps(data, indent=2)
        atomic_write_text(self._path, text)
        self._sig, self._raw = _signature(self._path), text

    def _reload_locked(self, startup: bool = False) -> bool:
        """Re-read save.json into this object (call with the lock held). True when the progress changed.

        A missing file keeps what is in memory (the next write recreates it). A damaged
        file is moved aside; mid-session the last good progress in memory is written
        back at once, so other processes never see a hole.
        """
        sig = _signature(self._path)
        if sig is None:
            self._sig = self._raw = None
            return False
        try:
            text = self._path.read_bytes().decode("utf-8")
            if text == self._raw:
                self._sig = sig
                return False
            values, problems = parse_save(text)
        except OSError:
            return False                       # unreadable for a moment (Windows sharing): try again later
        except (ValueError, RecursionError) as exc:   # JSONDecodeError and UnicodeDecodeError are ValueErrors
            kept = quarantine(self._path)
            where = f" It was kept as {kept.name}." if kept else ""
            if startup:
                self._notices.append(f"save.json could not be read ({_reason(exc)}).{where} "
                                     "Starting a fresh save.")
                self._sig = self._raw = None
            else:
                self._notices.append(f"save.json was damaged on disk ({_reason(exc)}).{where} "
                                     "Your progress from this session was written back.")
                self._write_locked()
            return False
        fresh = type(self)(**values)
        self._extra = _unknown_keys(text)
        changed = any(getattr(self, f.name) != getattr(fresh, f.name) for f in fields(self))
        for f in fields(self):
            setattr(self, f.name, getattr(fresh, f.name))
        self._sig, self._raw = sig, text
        if problems:
            kept = quarantine(self._path, copy_only=True)
            where = f" The original was kept as {kept.name}." if kept else ""
            self._notices.append(f"save.json had invalid values for {', '.join(problems)}; "
                                 f"those were reset.{where}")
            self._write_locked()
        if changed:
            self.reloads += 1
        return changed

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
        if mission_id in self.started_at and self._sig == _signature(self._path):
            return                                  # nothing to do, and nothing changed on disk
        with self.transaction():
            self.started_at.setdefault(mission_id, time.time())

    def record_attempt(self, mission_id: str) -> int:
        with self.transaction():
            self.attempts[mission_id] = self.attempts.get(mission_id, 0) + 1
            return self.attempts[mission_id]

    def elapsed(self, mission_id: str) -> float:
        return time.time() - self.started_at.get(mission_id, time.time())
