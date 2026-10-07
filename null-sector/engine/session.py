"""GameSession — the headless game core and the ONLY place game rules live.

Both front ends (the web server and the Rich TUI) drive the game exclusively
through this class, so XP, ranks, unlocks, the par timer and grading behave
identically everywhere. Public methods return the JSON payloads documented in
docs/ARCHITECTURE.md §3.3 (`State`, `Mission`, `HackResult`).

Rules
  * Playable = cleared or current. Unknown ids → SessionError(404); locked or
    encrypted (not built yet) levels → SessionError(403).
  * The par timer starts the first time a mission is deployed (or attacked).
  * First clear: XP = base, plus a speed bonus of xp // 2 when the breach time
    is within par. Values in PROFILE_EXPORTS (the callsign) flow from the
    player's code into the profile on every victory.
  * Replaying a cleared mission grades normally but grants no XP (reward.replay).

Concurrency
  One RLock guards every read and write of config/save state. Grading runs the
  player's code in a subprocess for up to `mission.timeout` seconds, so it runs
  *outside* that lock (serialised by its own lock) and the reward is applied
  under the lock afterwards, re-checking "first clear" so two racing hacks can
  never pay out twice. The API stays responsive while a slow mission grades.

Filesystem locations come from an injectable `Paths`; tests run in a temp dir.
"""
from __future__ import annotations

import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from engine import errors
from engine.cinematics import CutsceneRenderer, entry_kind
from engine.content import render_markdown
from engine.mission import Cutscene, Mission
from engine.runner import HackReport, ensure_mission_file, hack, mission_path
from engine.state import Paths, Save, atomic_write_text, load_config
from levels import ALL_LEVELS, CAMPAIGN, LevelEntry, load_mission, next_level, sector_of

# Values your mission code is allowed to write into your profile.
PROFILE_EXPORTS = {"callsign"}
CALLSIGN_MAX = 24
STDOUT_LIMIT = 64 * 1024          # characters of program output returned to the client
_LEVELS = {lvl.id: lvl for lvl in ALL_LEVELS}


class SessionError(Exception):
    """A request the rules refuse. `status` is the HTTP status the server should answer with."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class AttackOutcome:
    """Everything one hack produced: the raw report (for the TUI's animations) and the API payload."""

    mission: Mission
    report: HackReport
    attempt: int
    payload: dict

    @property
    def victory(self) -> bool:
        return self.payload["victory"]

    @property
    def reward(self) -> dict | None:
        return self.payload["reward"]


class GameSession:
    def __init__(self, paths: Paths | None = None, config: dict | None = None):
        self.paths = paths or Paths()
        self.config = config if config is not None else load_config(self.paths)
        self.save = Save.load(self.paths.save_path)
        self._lock = threading.RLock()
        self._grading = threading.Lock()
        self._cutscene_root = self.paths.cutscene_dir.resolve()
        self.cinema = CutsceneRenderer(self.config, self.save, self.paths.cutscene_dir, lock=self._lock)

    # ── public API (docs/ARCHITECTURE.md §3.1) ──────────────
    def snapshot(self) -> dict:
        """The `State` payload: profile, campaign map, Higgsfield status, gallery."""
        with self._lock:
            title, floor, nxt = self.save.rank()
            current = next_level(self.save.cleared)
            online, reason = self.cinema.status()
            return {
                "profile": {
                    "callsign": self.save.callsign, "xp": self.save.xp, "rank": title,
                    "rank_floor": floor, "rank_next": nxt, "breaches": len(self.save.cleared),
                    "total_levels": len(ALL_LEVELS),
                },
                "campaign": [{
                    "tier": sector.tier, "name": sector.name, "zone": sector.zone, "color": sector.color,
                    "levels": [{"id": lvl.id, "title": lvl.title, "concept": lvl.concept,
                                "status": self._status(lvl, current), "boss": lvl.title.startswith("BOSS")}
                               for lvl in sector.levels],
                } for sector in CAMPAIGN],
                "current": current.id if current else None,
                "higgsfield": {"online": online, "reason": reason},
                "gallery": [{"mission": e.get("mission", ""), "title": e.get("title", ""),
                             "url": self.media_url(e), "kind": kind}
                            for e, kind in ((e, entry_kind(e)) for e in self.save.gallery)],
            }

    def mission(self, mission_id: str) -> dict:
        """The `Mission` payload. Read-only: never creates files or starts the timer."""
        with self._lock:
            return self._mission_payload(self._playable_mission(mission_id))

    def deploy(self, mission_id: str) -> dict:
        """Start the par timer (first time only), drop the starter file if missing, return `Mission`."""
        with self._lock:
            mission = self._playable_mission(mission_id)
            ensure_mission_file(mission, missions_dir=self.paths.missions_dir)
            self.save.deploy(mission.id)
            return self._mission_payload(mission)

    def write_source(self, mission_id: str, text: str) -> dict:
        """Save the player's code (atomically, LF newlines). Returns {"ok": true, "saved_at": mtime}."""
        if not isinstance(text, str):
            raise SessionError(400, "source must be a string")
        text = normalize_source(text)
        with self._lock:
            path = mission_path(self._playable_mission(mission_id), self.paths.missions_dir)
            try:
                atomic_write_text(path, text)
            except PermissionError:   # Windows: target briefly locked by a reader; write in place
                path.write_text(text, encoding="utf-8", newline="")
            return {"ok": True, "saved_at": path.stat().st_mtime}

    def attack(self, mission_id: str) -> dict:
        """Grade the mission file. Returns the `HackResult` payload."""
        return self.attack_detailed(mission_id).payload

    def attack_detailed(self, mission_id: str) -> AttackOutcome:
        with self._grading:
            with self._lock:
                mission = self._playable_mission(mission_id)
                ensure_mission_file(mission, missions_dir=self.paths.missions_dir)
                self.save.deploy(mission.id)          # hacking without deploying still starts the clock
                attempt = self.save.record_attempt(mission.id)
            report = hack(mission, self.paths.missions_dir)
            with self._lock:
                victory = report.victory
                reward = self._apply_victory(mission, report) if victory else None
                payload = {
                    "report": report_payload(report),
                    "attempt": attempt,
                    "victory": victory,
                    "reward": reward,
                    "next": self._next_payload() if victory else None,
                    "state": self.snapshot(),
                }
        return AttackOutcome(mission, report, attempt, payload)

    def reset(self, mission_id: str) -> dict:
        """Restore the starter code. Returns {"source": str}."""
        with self._lock:
            mission = self._playable_mission(mission_id)
            ensure_mission_file(mission, reset=True, missions_dir=self.paths.missions_dir)
            return {"source": mission.starter.lstrip("\n")}

    def playable(self, mission_id: str) -> bool:
        """Cleared levels and the current (built) level are playable; nothing else."""
        with self._lock:
            entry = _LEVELS.get(mission_id)
            return entry is not None and self._status(entry, next_level(self.save.cleared)) in ("cleared", "current")

    # ── helpers for the front ends ──────────────────────────
    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def current_level(self) -> LevelEntry | None:
        """The first level not yet cleared (it may still be encrypted); None when the campaign is done."""
        with self._lock:
            return next_level(self.save.cleared)

    def current_playable_id(self) -> str | None:
        current = self.current_level()
        return current.id if current and current.slug else None

    def mission_object(self, mission_id: str) -> Mission:
        with self._lock:
            return self._playable_mission(mission_id)

    def mission_path(self, mission_id: str) -> Path:
        """Where a built mission's file lives (no playability check; used by the file watcher)."""
        entry = self._entry(mission_id)
        if not entry.slug:
            raise SessionError(403, f"{entry.id} {entry.title} is still encrypted")
        return mission_path(load_mission(entry.slug), self.paths.missions_dir)

    def display_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.paths.game_dir.resolve()).as_posix()
        except ValueError:
            return str(path)

    def cutscene(self, mission_id: str) -> Cutscene | None:
        """A cleared mission's cutscene (None if it has none). Uncleared missions → 403."""
        with self._lock:
            mission = self._playable_mission(mission_id)
            if mission.id not in self.save.cleared:
                raise SessionError(403, f"clear {mission.id} to unlock its transmission")
            return mission.cutscene

    def media_url(self, entry: dict) -> str:
        """`/cutscenes/<file>` when the media was downloaded, else the remote URL."""
        path = entry.get("path")
        if path:
            local = Path(path)
            try:
                if local.parent.resolve() == self._cutscene_root and local.is_file():
                    return "/cutscenes/" + quote(local.name)
            except OSError:
                pass
        return entry.get("url") or ""

    # ── internals ───────────────────────────────────────────
    def _entry(self, mission_id: str) -> LevelEntry:
        entry = _LEVELS.get(mission_id) if isinstance(mission_id, str) else None
        if entry is None:
            raise SessionError(404, f"unknown mission '{mission_id}'")
        return entry

    def _status(self, entry: LevelEntry, current: LevelEntry | None) -> str:
        if entry.id in self.save.cleared:
            return "cleared"
        if current is not None and entry.id == current.id:
            return "current" if entry.slug else "encrypted"
        return "locked"

    def _playable_mission(self, mission_id: str) -> Mission:
        entry = self._entry(mission_id)
        status = self._status(entry, next_level(self.save.cleared))
        if status == "locked":
            raise SessionError(403, f"{entry.id} {entry.title} is locked — clear the levels before it first")
        if status == "encrypted" or not entry.slug:
            raise SessionError(403, f"{entry.id} {entry.title} is still encrypted")
        return load_mission(entry.slug)

    def _mission_payload(self, mission: Mission) -> dict:
        sector = sector_of(mission.id)
        path = mission_path(mission, self.paths.missions_dir)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            source = mission.starter.lstrip("\n")
        record = self.save.cleared.get(mission.id)
        if record is not None:
            elapsed = float(record.get("seconds", 0))     # the par clock freezes at the breach
        elif mission.id in self.save.started_at:
            elapsed = self.save.elapsed(mission.id)
        else:
            elapsed = 0.0
        cutscene = mission.cutscene
        return {
            "id": mission.id, "title": mission.title, "concept": mission.concept,
            "tier": sector.tier, "sector": {"name": sector.name, "zone": sector.zone, "color": sector.color},
            "enemy": mission.enemy, "enemy_art": mission.enemy_art, "xp": mission.xp,
            "par_seconds": mission.par_seconds,
            "briefing_html": render_markdown(mission.briefing),
            "why_html": render_markdown(mission.why),
            "manual_html": render_markdown(mission.manual),
            "objectives": [check.name for check in mission.checks],
            "file": self.display_path(path), "source": source,
            "attempts": self.save.attempts.get(mission.id, 0),
            "elapsed": round(max(elapsed, 0.0), 1),
            "cleared": record is not None,
            "cutscene": {"title": cutscene.title, "narration": list(cutscene.narration)} if cutscene else None,
        }

    def _apply_victory(self, mission: Mission, report: HackReport) -> dict:
        save = self.save
        first_clear = mission.id not in save.cleared
        rank_before = save.rank()[0]
        self._apply_exports(report.exports)
        if first_clear:
            seconds = save.elapsed(mission.id)
            lines = [{"label": "BASE XP", "amount": mission.xp}]
            if seconds <= mission.par_seconds:
                lines.append({"label": "SPEED BONUS", "amount": mission.xp // 2})
            gained = sum(line["amount"] for line in lines)
            save.xp += gained
            save.cleared[mission.id] = {"xp": gained, "attempts": save.attempts.get(mission.id, 0),
                                        "seconds": int(seconds)}
        else:
            seconds, lines, gained = save.cleared[mission.id].get("seconds", 0), [], 0
        save.write()
        rank_after = save.rank()[0]
        return {
            "lines": lines, "gained": gained,
            "rank_before": rank_before, "rank_after": rank_after, "rank_up": rank_after != rank_before,
            "breach_seconds": int(seconds), "attempts": save.attempts.get(mission.id, 0),
            "callsign": save.callsign, "replay": not first_clear,
        }

    def _apply_exports(self, exports: dict) -> None:
        for key, value in (exports or {}).items():
            if key not in PROFILE_EXPORTS:
                continue
            if key == "callsign":
                value = clean_callsign(value)
                if not value:
                    continue
            setattr(self.save, key, value)

    def _next_payload(self) -> dict | None:
        upcoming = next_level(self.save.cleared)
        if upcoming is None:
            return None
        return {"id": upcoming.id, "title": upcoming.title, "concept": upcoming.concept,
                "status": "current" if upcoming.slug else "encrypted"}


# ── pure helpers ────────────────────────────────────────────
def normalize_source(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def clean_callsign(value) -> str:
    """Strip control characters and whitespace; cap the length. Non-strings are rejected."""
    if not isinstance(value, str):
        return ""
    text = "".join(ch for ch in value if unicodedata.category(ch)[0] != "C")
    return " ".join(text.split())[:CALLSIGN_MAX]


def report_payload(report: HackReport) -> dict:
    """`HackResult.report`: grader output plus a plain-English `decoded` explanation of any error."""
    error = None
    if report.error:
        raw = report.error
        error = {"type": raw.get("type") or "Error", "message": raw.get("message") or "",
                 "line": raw.get("line"), "code": raw.get("code") or "", "traceback": raw.get("traceback") or "",
                 "decoded": errors.decode(raw)}
    stdout = report.stdout or ""
    if len(stdout) > STDOUT_LIMIT:
        dropped = len(stdout) - STDOUT_LIMIT
        stdout = f"[… {dropped:,} earlier characters of output truncated …]\n" + stdout[-STDOUT_LIMIT:]
    checks = [{"name": c.get("name", ""), "passed": bool(c.get("passed")), "message": c.get("message") or "",
               "hint": c.get("hint") or ""} for c in report.checks]
    return {"status": report.status, "checks": checks, "stdout": stdout, "error": error}


__all__ = ["GameSession", "SessionError", "AttackOutcome", "PROFILE_EXPORTS", "report_payload",
           "normalize_source", "clean_callsign"]
