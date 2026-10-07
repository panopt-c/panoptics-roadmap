"""Command center panel embedded in the existing Rich terminal frontend."""
from __future__ import annotations

from uuid import uuid4

from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from engine.session import SessionError
from .tracker import COURSES


def render_dashboard(state: dict) -> Panel:
    study, fitness, game = state["study"], state["fitness"], state["game"]
    study_table = Table.grid(padding=(0, 2))
    study_table.add_column(style="cyan")
    study_table.add_column()
    study_table.add_row("TODAY", f"{study['today_minutes']} / {study['goal_minutes']} min")
    filled = round(study["progress"] * 20)
    study_table.add_row("PROGRESS", Text("#" * filled + "-" * (20 - filled), style="cyan"))
    study_table.add_row("REMAINING", f"{study['remaining_minutes']} min")
    study_table.add_row("STREAK", f"{study['current_streak_days']} days / best {study['best_streak_days']}")
    for course, minutes in study["course_minutes"].items():
        study_table.add_row(course, f"{minutes / 60:.1f} h total")
    fitness_table = Table.grid(padding=(0, 2))
    fitness_table.add_column(style="magenta")
    fitness_table.add_column()
    fitness_table.add_row("TRAINING TODAY", f"{fitness['today_workout_minutes']} min")
    latest = fitness["latest_weight_lbs"]
    fitness_table.add_row("LATEST WEIGHT", "No measurement" if latest is None else f"{latest:g} lbs")
    fitness_table.add_row("TARGET", f"{fitness['target_weight_lbs']:g} lbs")
    fitness_table.add_row("CAMPAIGN XP", str(game["campaign_xp"]))
    fitness_table.add_row("PRODUCTIVITY XP", str(game["productivity_xp"]))
    fitness_table.add_row("COMBINED XP", str(game["total_xp"]))
    fitness_table.add_row("REWARD PAYLOADS", str(len(state["cinematic_jobs"])))
    return Panel(Columns([Panel(study_table, title="MATH PROTOCOL", border_style="cyan"),
                          Panel(fitness_table, title="PHYSICAL TRAINING", border_style="magenta")], expand=True),
                 title="NULL//SECTOR COMMAND CENTER", subtitle=state["date"], border_style="cyan")


def show_command_center(console, session) -> None:
    while True:
        console.print(render_dashboard(session.productivity_snapshot()))
        key = console.input("[cyan]S[/] Study  [magenta]T[/] Training  W Weight  R Refresh  B Back > ").strip().lower()
        if key in {"b", ""}:
            return
        if key == "r":
            continue
        try:
            payload = {"request_id": str(uuid4())}
            if key == "s":
                for number, course in enumerate(COURSES, 1):
                    console.print(f"  {number}. {course}")
                index = int(console.input("Course number > "))
                if not 1 <= index <= len(COURSES):
                    raise ValueError("Choose a course from the list")
                payload.update(course=COURSES[index - 1], minutes=int(console.input("Completed minutes > ")),
                               topic=console.input("Topic (optional) > "))
                command = "study"
            elif key == "t":
                payload.update(activity=console.input("Activity > "), minutes=int(console.input("Completed minutes > ")))
                command = "workout"
            elif key == "w":
                payload["weight_lbs"] = float(console.input("Measured weight in lbs > "))
                command = "weight"
            else:
                console.print("Choose S, T, W, R or B.")
                continue
            result = session.log_productivity(command, payload)
            console.print(Text(f"Saved. +{result['activity']['xp_awarded']} productivity XP", style="green"))
        except (ValueError, SessionError) as exc:
            console.print(Text(str(exc), style="red"))
