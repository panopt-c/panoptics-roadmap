"""Zero-dependency command line access to the productivity backend."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from .backend import CommandCenter
from .db import DEFAULT_DB_PATH, scrub_surrogates
from .tracker import COURSES


def _argv_text(value):
    """Undo argv's surrogateescape: bytes that were not UTF-8 become U+FFFD instead of invalid text."""
    if not isinstance(value, str):
        return value
    try:
        return value.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    except UnicodeEncodeError:       # a real lone surrogate, not an escaped byte
        return scrub_surrogates(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Neon Command: RPG productivity backend")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite file (default: game data/productivity.sqlite3)")
    parser.add_argument("--player", default="Netrunner")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize the schema and player")
    dashboard = commands.add_parser("dashboard", help="Print a JSON dashboard")
    dashboard.add_argument("--date", dest="on_date")
    commands.add_parser("rewards", help="Print queued cinematic JSON payloads")
    study = commands.add_parser("study", help="Log a completed math study block")
    study.add_argument("--course", choices=COURSES, required=True)
    study.add_argument("--minutes", type=int, required=True)
    study.add_argument("--topic", default="")
    workout = commands.add_parser("workout", help="Log a completed workout")
    workout.add_argument("--activity", required=True)
    workout.add_argument("--minutes", type=int, required=True)
    workout.add_argument("--sets", type=int)
    workout.add_argument("--reps", type=int)
    workout.add_argument("--load-lbs", type=float)
    workout.add_argument("--distance-miles", type=float)
    workout.add_argument("--note", default="")
    weight = commands.add_parser("weight", help="Log a weight measurement in pounds")
    weight.add_argument("--lbs", dest="weight_lbs", type=float, required=True)
    habit = commands.add_parser("habit", help="Set a daily custom habit value")
    habit.add_argument("--key", dest="habit_key", required=True)
    habit.add_argument("--value", type=float, required=True)
    habit.add_argument("--note", default="")
    for command in (study, workout, weight, habit):
        command.add_argument("--date", dest="on_date", help="YYYY-MM-DD (default: local calendar date)")
        if command is not habit:
            command.add_argument("--request-id", help="Reuse for retries of the same submission")
    args = {key: _argv_text(value) for key, value in vars(parser.parse_args(argv)).items()}
    path, player, command = args.pop("db"), args.pop("player"), args.pop("command")
    try:
        with CommandCenter(path, player_name=player) as app:
            if command == "init":
                result = app.player
            elif command == "dashboard":
                result = app.snapshot(**args)
            elif command == "rewards":
                app.reconcile()
                result = app.cinematics.jobs()
            else:
                result = app.execute(command, **args)
            print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
        return 0
    except (ValueError, LookupError, RuntimeError, sqlite3.Error, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
