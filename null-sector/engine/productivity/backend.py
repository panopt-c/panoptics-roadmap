"""UI-facing composition root: persistent state, activity commands, reward jobs."""
from __future__ import annotations

from pathlib import Path

from .cinematics import CinematicRouter
from .db import DEFAULT_DB_PATH, Database
from .tracker import Tracker


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

    def snapshot(self, on_date=None) -> dict:
        self.cinematics.queue_rewards()
        snapshot = self.tracker.dashboard(on_date)
        snapshot["cinematic_jobs"] = self.cinematics.jobs()
        return snapshot

    def execute(self, command: str, **payload) -> dict:
        """Allowlisted dispatch suitable for TUI handlers or a local API adapter."""
        handlers = {"study": self.tracker.log_study, "workout": self.tracker.log_workout,
                    "weight": self.tracker.log_weight, "habit": self.tracker.set_habit}
        if command not in handlers:
            raise ValueError(f"Unknown activity command: {command}")
        result = handlers[command](**payload)
        self.cinematics.queue_rewards()
        return {"activity": result, "snapshot": self.snapshot(payload.get("on_date"))}

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> CommandCenter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
