"""Bridge the tracker to an existing GameSession without migrating its saves.

Campaign XP is authoritative in Save; productivity XP is authoritative in SQLite.
`save` is any object with `cleared`, `callsign` and `xp` (GameSession passes a copy
taken under its lock, so no SQLite work ever runs while the session lock is held).
The command center derives their sum without copying either award into the other
store. Mission cinematic jobs are reconciled from durable cleared-mission records.
"""
from __future__ import annotations

from .backend import CommandCenter
from .db import json_text, utc_now


def _sync_coding_rewards(backend: CommandCenter, save) -> None:
    with backend.db.transaction() as conn:
        for mission_id in save.cleared:
            conn.execute("""INSERT INTO milestones(player_id,milestone_key,title,category,details_json,achieved_at)
                VALUES (?,?,?,'coding',?,?) ON CONFLICT(player_id,milestone_key) DO NOTHING""",
                (backend.player["id"], f"coding:{mission_id}", f"Mission {mission_id} cleared",
                 json_text({"mission_id": mission_id}), utc_now()))


def _attach_game(snapshot: dict, save) -> dict:
    productivity_xp = snapshot["player"]["xp"]
    snapshot["game"] = {"callsign": save.callsign, "campaign_xp": save.xp,
                        "productivity_xp": productivity_xp, "total_xp": save.xp + productivity_xp}
    return snapshot


def _open(paths) -> CommandCenter:
    return CommandCenter(paths.game_dir / "data" / "productivity.sqlite3")


def snapshot(paths, save, on_date=None) -> dict:
    with _open(paths) as backend:
        _sync_coding_rewards(backend, save)
        return _attach_game(backend.snapshot(on_date), save)


def rewards(paths, save) -> list[dict]:
    """Every reward payload, oldest first (GET /api/productivity/rewards)."""
    with _open(paths) as backend:
        _sync_coding_rewards(backend, save)
        backend.reconcile()
        return backend.cinematics.jobs()


def execute(paths, save, command: str, payload: dict) -> dict:
    with _open(paths) as backend:
        _sync_coding_rewards(backend, save)
        result = backend.execute(command, **payload)
        result["snapshot"] = _attach_game(result["snapshot"], save)
        return result
