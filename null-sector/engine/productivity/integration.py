"""Bridge the tracker to an existing GameSession without migrating its saves.

Campaign XP is authoritative in Save; productivity XP is authoritative in SQLite.
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


def snapshot(paths, save, on_date=None) -> dict:
    with CommandCenter(paths.game_dir / "data" / "productivity.sqlite3") as backend:
        _sync_coding_rewards(backend, save)
        return _attach_game(backend.snapshot(on_date), save)


def execute(paths, save, command: str, payload: dict) -> dict:
    with CommandCenter(paths.game_dir / "data" / "productivity.sqlite3") as backend:
        _sync_coding_rewards(backend, save)
        result = backend.execute(command, **payload)
        result["snapshot"] = _attach_game(result["snapshot"], save)
        return result
