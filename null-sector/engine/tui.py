"""The Rich terminal front end: `python game.py tui`, plus the `hack`, `watch` and `reset` commands.

Presentation only. Every rule — attempts, the par timer, XP and speed bonus,
ranks, profile exports, unlocks — comes from `GameSession`, the same headless
core the web client talks to, so both front ends always agree. The terminal may
run next to the web server (they share save.json), so every screen refreshes
the session before drawing and always shows the latest progress.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from rich.panel import Panel

from engine import ui
from engine.cinematics import Director
from engine.mission import Mission
from engine.session import GameSession
from engine.state import Save


class Game:
    def __init__(self, fast: bool = False, session: GameSession | None = None):
        self.session = session or GameSession()
        self.config = self.session.config
        if fast:
            self.config["ui"]["animations"] = False
        self.animate = self.config["ui"]["animations"]
        self.console = ui.make_console()
        self.director = Director(self.console, self.session.cinema, self.config["ui"])

    @property
    def save(self) -> Save:
        return self.session.save

    def sync(self) -> None:
        """Adopt progress saved by another window (the browser) and show any file-damage notices."""
        self.session.refresh()
        self.show_notices()

    def show_notices(self) -> None:
        for notice in self.session.take_notices():
            self.console.print(f"  [warn]! {notice}[/]")

    # ── menus ───────────────────────────────────────────────
    def main_menu(self) -> None:
        ui.boot_sequence(self.console, self.animate)
        while True:
            self.sync()
            ui.hud(self.console, self.save)
            online, reason = self.director.status()
            feed = "[ok]● ONLINE[/]" if online else f"[muted]○ OFFLINE · {reason}[/]"
            self.console.print(f"  [muted]HIGGSFIELD FEED[/]  {feed}\n")
            self.console.print(ui.command_bar(("D", "DEPLOY"), ("P", "PRODUCTIVITY"), ("G", "GALLERY"), ("Q", "JACK OUT")))
            key = ui.ask_key(self.console, "dpgq", default="d")
            if key == "p":
                from engine.productivity.tui import show_command_center
                show_command_center(self.console, self.session)
            if key == "q":
                self.console.print("\n  [pink]Jacking out. Progress saved.[/]\n")
                return
            if key == "g":
                self.sync()
                ui.gallery(self.console, self.save)
                self.pause()
            if key == "d":
                mission = self.current_mission()
                if mission:
                    self.mission_menu(mission)
                else:
                    self.pause()

    def mission_menu(self, mission: Mission) -> None:
        self.session.deploy(mission.id)
        path = self.session.mission_path(mission.id)
        show_briefing = True
        while True:
            if show_briefing:
                ui.briefing(self.console, mission, self.session.display_path(path), path.as_uri())
                show_briefing = False
            self.console.print(ui.command_bar(("H", "HACK"), ("W", "WATCH MODE"), ("O", "OPEN FILE"),
                                              ("B", "BRIEFING"), ("R", "RESET FILE"), ("X", "BACK")))
            key = ui.ask_key(self.console, "hwobrx", default="h")
            if key == "x":
                return
            if key == "b":
                show_briefing = True
            elif key == "o":
                self.open_in_editor(path)
            elif key == "r":
                self.reset(mission)
            elif key == "h" and self.attack(mission):
                return
            elif key == "w" and self.watch(mission):
                return

    # ── combat ──────────────────────────────────────────────
    def attack(self, mission: Mission) -> bool:
        with self.console.status("[accent]Injecting payload…[/]", spinner="dots12"):
            outcome = self.session.attack_detailed(mission.id)
        ui.play_hack(self.console, mission, outcome.report, outcome.attempt, self.animate)
        if outcome.victory:
            self.reward(mission, outcome.reward, outcome.payload["next"])
            return True
        return False

    def watch(self, mission: Mission) -> bool:
        """Re-attack every time the mission file is saved. The fastest learning loop there is."""
        path = self.session.mission_path(mission.id)
        last_seen = None
        try:
            while True:
                mtime = path.stat().st_mtime if path.exists() else None
                if mtime != last_seen:
                    time.sleep(0.15)  # let the editor finish writing
                    last_seen = path.stat().st_mtime if path.exists() else None
                    self.console.clear()
                    self.console.print(Panel(
                        f"[accent]WATCH MODE[/]  [steel]save[/] [bold]{self.session.display_path(path)}[/] "
                        f"[steel]to attack · ctrl+c to stop[/]", border_style=ui.CYAN))
                    if self.attack(mission):
                        return True
                    self.console.print("\n  [muted]◌ watching… save your file to attack again[/]")
                time.sleep(0.4)
        except KeyboardInterrupt:
            self.console.print("\n  [muted]watch mode off[/]")
            return False

    def reward(self, mission: Mission, reward: dict, upcoming: dict | None) -> None:
        seconds = reward["breach_seconds"]
        lines = []
        for line in reward["lines"]:
            label = line["label"]
            if label == "SPEED BONUS":
                label = f"SPEED BONUS  {ui.fmt_time(seconds)} under par {ui.fmt_time(mission.par_seconds)}"
            lines.append((label, line["amount"]))
        rank_up = reward["rank_after"] if reward["rank_up"] else None
        ui.victory(self.console, mission, lines, rank_up, self.animate)
        if reward["replay"]:
            self.console.print("  [muted]REPLAY — this sector was already restored, no XP awarded[/]")
        self.console.print(f"  [muted]BREACH TIME[/] [steel]{ui.fmt_time(seconds)}[/]    "
                           f"[muted]ATTEMPTS[/] [steel]{reward['attempts']}[/]\n")
        if mission.cutscene:
            self.pause("play transmission")
            self.director.play(mission.cutscene, mission.id)
        if upcoming:
            built = upcoming["status"] == "current"
            label = "UNLOCKED ▶" if built else "NEXT TARGET ▶"
            status = "" if built else "  [warn]\\[encrypted — ask Claude to build it][/]"
            self.console.print(f"  [accent]{label}[/] [bold]{upcoming['id']} {upcoming['title']}[/] "
                               f"[steel]{upcoming['concept']}[/]{status}")
        self.pause()

    # ── helpers ─────────────────────────────────────────────
    def current_mission(self) -> Mission | None:
        upcoming = self.session.current_level()
        if upcoming is None:
            self.console.print("\n  [ok]Every sector is restored. You are the Architect of the Core.[/]")
            return None
        if upcoming.slug is None:
            self.console.print(f"\n  [warn]{upcoming.id} {upcoming.title} is still encrypted.[/] "
                               "[steel]Ask Claude to build the next level.[/]")
            return None
        return self.session.mission_object(upcoming.id)

    def reset(self, mission: Mission) -> None:
        self.console.print("  [warn]Wipe your mission file back to the starter code?[/] [muted](y/n)[/]")
        if ui.ask_key(self.console, "yn", default="n") == "y":
            self.session.reset(mission.id)
            self.console.print("  [ok]File restored.[/]")

    def open_in_editor(self, path: Path) -> None:
        editor = (self.config.get("editor") or os.getenv("VISUAL") or os.getenv("EDITOR")
                  or ("code" if shutil.which("code") else ""))
        if not editor:
            self.console.print(f"  [steel]Open this file in your editor:[/] [bold]{path}[/]\n"
                               "  [muted](set \"editor\" in config.json, e.g. \"code\", to open it automatically)[/]")
            return
        subprocess.call([*shlex.split(editor), str(path)])

    def pause(self, action: str = "continue") -> None:
        self.console.input(f"\n  [muted]press enter to {action} ▸[/] ")


def run(command: str = "tui", fast: bool = False, session: GameSession | None = None) -> None:
    """Entry point for the terminal commands: tui | hack | watch | reset."""
    game = Game(fast=fast, session=session)
    game.show_notices()
    try:
        if command == "productivity":
            from engine.productivity.tui import show_command_center
            show_command_center(game.console, game.session)
            return
        if command in ("tui", "play"):
            game.main_menu()
            return
        mission = game.current_mission()
        if mission is None:
            return
        game.session.deploy(mission.id)
        if command == "hack":
            game.attack(mission)
        elif command == "watch":
            game.watch(mission)
        elif command == "reset":
            game.reset(mission)
    except (KeyboardInterrupt, EOFError):
        game.console.print("\n  [pink]Jacking out. Progress saved.[/]\n")
