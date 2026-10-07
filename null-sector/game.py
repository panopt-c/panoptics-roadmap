#!/usr/bin/env python3
"""NULL//SECTOR — a Python survival RPG. From zero to AI engineer.

    python game.py            play
    python game.py watch      auto-hack your current mission every time you save it
    python game.py hack       hack your current mission once
    python game.py reset      restore your current mission file to its starter code
    add --fast to skip animations
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from rich.panel import Panel
except ImportError:
    sys.exit("Missing libraries. Run:  pip install -r requirements.txt")

from engine import ui
from engine.cinematics import Director
from engine.mission import Mission
from engine.runner import ensure_mission_file, hack, mission_path
from engine.state import GAME_DIR, Save, load_config
from levels import load_mission, next_level

# Values your mission code is allowed to write into your profile.
PROFILE_EXPORTS = {"callsign"}


class Game:
    def __init__(self, fast: bool = False):
        self.config = load_config()
        if fast:
            self.config["ui"]["animations"] = False
        self.animate = self.config["ui"]["animations"]
        self.console = ui.make_console()
        self.save = Save.load()
        self.director = Director(self.console, self.config, self.save)

    # ── menus ───────────────────────────────────────────────
    def main_menu(self) -> None:
        ui.boot_sequence(self.console, self.animate)
        while True:
            ui.hud(self.console, self.save)
            online, reason = self.director.status()
            feed = "[ok]● ONLINE[/]" if online else f"[muted]○ OFFLINE · {reason}[/]"
            self.console.print(f"  [muted]HIGGSFIELD FEED[/]  {feed}\n")
            self.console.print(ui.command_bar(("D", "DEPLOY"), ("G", "GALLERY"), ("Q", "JACK OUT")))
            key = ui.ask_key(self.console, "dgq", default="d")
            if key == "q":
                self.console.print("\n  [pink]Jacking out. Progress saved.[/]\n")
                return
            if key == "g":
                ui.gallery(self.console, self.save)
                self.pause()
            if key == "d":
                mission = self.current_mission()
                if mission:
                    self.mission_menu(mission)
                else:
                    self.pause()

    def mission_menu(self, mission: Mission) -> None:
        path = ensure_mission_file(mission)
        self.save.deploy(mission.id)
        show_briefing = True
        while True:
            if show_briefing:
                ui.briefing(self.console, mission, self.display_path(path), path.as_uri())
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
        attempt = self.save.record_attempt(mission.id)
        with self.console.status("[accent]Injecting payload…[/]", spinner="dots12"):
            report = hack(mission)
        ui.play_hack(self.console, mission, report, attempt, self.animate)
        if report.victory:
            self.reward(mission, report.exports)
            return True
        return False

    def watch(self, mission: Mission) -> bool:
        """Re-attack every time the mission file is saved. The fastest learning loop there is."""
        path = mission_path(mission)
        last_seen = None
        try:
            while True:
                mtime = path.stat().st_mtime if path.exists() else None
                if mtime != last_seen:
                    time.sleep(0.15)  # let the editor finish writing
                    last_seen = path.stat().st_mtime if path.exists() else None
                    self.console.clear()
                    self.console.print(Panel(
                        f"[accent]WATCH MODE[/]  [steel]save[/] [bold]{self.display_path(path)}[/] "
                        f"[steel]to attack · ctrl+c to stop[/]", border_style=ui.CYAN))
                    if self.attack(mission):
                        return True
                    self.console.print("\n  [muted]◌ watching… save your file to attack again[/]")
                time.sleep(0.4)
        except KeyboardInterrupt:
            self.console.print("\n  [muted]watch mode off[/]")
            return False

    def reward(self, mission: Mission, exports: dict) -> None:
        seconds = self.save.elapsed(mission.id)
        lines = [("BASE XP", mission.xp)]
        if seconds <= mission.par_seconds:
            lines.append((f"SPEED BONUS  {ui.fmt_time(seconds)} under par {ui.fmt_time(mission.par_seconds)}",
                          mission.xp // 2))
        gained = sum(amount for _, amount in lines)

        old_rank = self.save.rank()[0]
        self.save.xp += gained
        for key, value in exports.items():
            if key in PROFILE_EXPORTS:
                setattr(self.save, key, value)
        self.save.cleared[mission.id] = {"xp": gained, "attempts": self.save.attempts.get(mission.id, 0),
                                         "seconds": int(seconds)}
        self.save.write()
        new_rank = self.save.rank()[0]

        ui.victory(self.console, mission, lines, new_rank if new_rank != old_rank else None, self.animate)
        self.console.print(f"  [muted]BREACH TIME[/] [steel]{ui.fmt_time(seconds)}[/]    "
                           f"[muted]ATTEMPTS[/] [steel]{self.save.attempts.get(mission.id, 0)}[/]\n")
        if mission.cutscene:
            self.pause("play transmission")
            self.director.play(mission.cutscene, mission.id)
        upcoming = next_level(self.save.cleared)
        if upcoming:
            label = "UNLOCKED ▶" if upcoming.slug else "NEXT TARGET ▶"
            status = "" if upcoming.slug else "  [warn][encrypted — ask Claude to build it][/]"
            self.console.print(f"  [accent]{label}[/] [bold]{upcoming.id} {upcoming.title}[/] "
                               f"[steel]{upcoming.concept}[/]{status}")
        self.pause()

    # ── helpers ─────────────────────────────────────────────
    def current_mission(self) -> Mission | None:
        upcoming = next_level(self.save.cleared)
        if upcoming is None:
            self.console.print("\n  [ok]Every sector is restored. You are the Architect of the Core.[/]")
            return None
        if upcoming.slug is None:
            self.console.print(f"\n  [warn]{upcoming.id} {upcoming.title} is still encrypted.[/] "
                               "[steel]Ask Claude to build the next level.[/]")
            return None
        return load_mission(upcoming.slug)

    def reset(self, mission: Mission) -> None:
        self.console.print("  [warn]Wipe your mission file back to the starter code?[/] [muted](y/n)[/]")
        if ui.ask_key(self.console, "yn", default="n") == "y":
            ensure_mission_file(mission, reset=True)
            self.console.print("  [ok]File restored.[/]")

    def open_in_editor(self, path: Path) -> None:
        editor = (self.config.get("editor") or os.getenv("VISUAL") or os.getenv("EDITOR")
                  or ("code" if shutil.which("code") else ""))
        if not editor:
            self.console.print(f"  [steel]Open this file in your editor:[/] [bold]{path}[/]\n"
                               "  [muted](set \"editor\" in config.json, e.g. \"code\", to open it automatically)[/]")
            return
        subprocess.call([*shlex.split(editor), str(path)])

    def display_path(self, path: Path) -> str:
        return str(path.relative_to(GAME_DIR))

    def pause(self, action: str = "continue") -> None:
        self.console.input(f"\n  [muted]press enter to {action} ▸[/] ")


def main() -> None:
    parser = argparse.ArgumentParser(description="NULL//SECTOR — a Python survival RPG")
    parser.add_argument("command", nargs="?", choices=["play", "hack", "watch", "reset"], default="play")
    parser.add_argument("--fast", action="store_true", help="skip animations")
    args = parser.parse_args()

    game = Game(fast=args.fast)
    try:
        if args.command == "play":
            game.main_menu()
            return
        mission = game.current_mission()
        if mission is None:
            return
        ensure_mission_file(mission)
        game.save.deploy(mission.id)
        if args.command == "hack":
            game.attack(mission)
        elif args.command == "watch":
            game.watch(mission)
        elif args.command == "reset":
            game.reset(mission)
    except (KeyboardInterrupt, EOFError):
        game.console.print("\n  [pink]Jacking out. Progress saved.[/]\n")


if __name__ == "__main__":
    main()
