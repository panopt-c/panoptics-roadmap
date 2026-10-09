"""UI-facing composition root: persistent state, activity commands, reward jobs."""
from __future__ import annotations

from pathlib import Path

from .cinematics import CinematicRouter
from .db import DEFAULT_DB_PATH, Database
from .tracker import Tracker

RECENT_JOBS = 20      # snapshots carry the newest N reward payloads; GET /api/productivity/rewards has all

# command -> (required fields, optional fields). Anything else is refused with a clean message.
FIELDS = {
    "study": (("course", "minutes"), ("topic", "on_date", "request_id")),
    "workout": (("activity", "minutes"), ("sets", "reps", "load_lbs", "distance_miles", "note", "on_date", "request_id")),
    "weight": (("weight_lbs",), ("on_date", "request_id")),
    # Habit writes are daily upserts, idempotent by nature; a request_id is accepted and ignored.
    "habit": (("habit_key", "value"), ("note", "on_date", "request_id")),
}


def validate_fields(command: str, payload: dict) -> dict:
    """Check payload keys against the command's allowlist. Returns the handler's keyword arguments."""
    if command not in FIELDS:
        raise ValueError(f"Unknown activity command: {command}")
    required, optional = FIELDS[command]
    unknown = sorted(key for key in payload if key not in required and key not in optional)
    if unknown:
        raise ValueError(f"unknown field{'s' if len(unknown) > 1 else ''} for {command}: {', '.join(map(str, unknown))}")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"missing required field{'s' if len(missing) > 1 else ''} for {command}: {', '.join(missing)}")
    kwargs = dict(payload)
    if command == "habit":
        kwargs.pop("request_id", None)
    return kwargs


class CommandCenter:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH, *, player_name: str = "Netrunner"):
        self.db = Database(path)
        try:
            self.player = self.db.create_player(player_name)
            self.tracker = Tracker(self.db, self.player["id"])
            self.cinematics = CinematicRouter(self.db, self.player["id"])
        except BaseException:
            self.db.close()
            raise

    def reconcile(self) -> list[dict]:
        """Drop pending Armory items and queue pending reward payloads. Returns the new items."""
        granted = self.tracker.grant_items()
        self.cinematics.queue_rewards()
        return granted

    def snapshot(self, on_date=None) -> dict:
        self.reconcile()
        snapshot = self.tracker.dashboard(on_date)
        snapshot["cinematic_jobs"] = self.cinematics.recent_jobs(RECENT_JOBS)
        snapshot["cinematic_job_count"] = self.cinematics.job_count()
        return snapshot

    def execute(self, command: str, /, **payload) -> dict:
        """Allowlisted dispatch suitable for TUI handlers or a local API adapter.

        The returned snapshot is always for the current day: `on_date` only chooses
        which day the entry is filed under, never which day the dashboard shows.
        """
        kwargs = validate_fields(command, payload)
        handlers = {"study": self.tracker.log_study, "workout": self.tracker.log_workout,
                    "weight": self.tracker.log_weight, "habit": self.tracker.set_habit}
        result = handlers[command](**kwargs)
        granted = self.reconcile()
        return {"activity": result, "snapshot": self.snapshot(), "items_granted": granted}

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> CommandCenter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
