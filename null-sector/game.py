#!/usr/bin/env python3
"""NULL//SECTOR — a Python survival RPG. From zero to AI engineer.

    python game.py            play in your browser (starts a local server, opens a tab)
    python game.py tui        play in the terminal
    python game.py watch      auto-hack your current mission every time you save it
    python game.py hack       hack your current mission once
    python game.py reset      restore your current mission file to its starter code

    --port N        web client port (default 7777; the next free one is used if it's taken)
    --no-browser    don't open a browser tab
    --fast          skip terminal animations
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import markdown_it  # noqa: F401 — imported by the web server; ships with rich
    import pygments  # noqa: F401
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:
    sys.exit("Missing libraries. Run:  pip install -r requirements.txt")

TERMINAL_COMMANDS = ("tui", "hack", "watch", "reset", "productivity")


def play_web(port: int, open_browser: bool) -> None:
    from engine import ui
    from engine.server import CLIENT_DIR, serve
    from engine.session import GameSession

    console = ui.make_console()
    session = GameSession()

    def banner(url: str) -> None:
        profile = session.snapshot()["profile"]
        current = session.current_level()
        grid = Table.grid(padding=(0, 3))
        grid.add_column(style="muted", no_wrap=True)
        grid.add_column(no_wrap=True)
        grid.add_row("LINK", Text(url, style=f"bold {ui.CYAN} link {url}"))
        operative = (Text(profile["callsign"], style="accent") if profile["callsign"]
                     else Text("UNREGISTERED", style="bad"))
        operative.append(f"  ·  {profile['rank']}  ·  {profile['xp']} XP", style="steel")
        grid.add_row("OPERATIVE", operative)
        if current:
            grid.add_row("TARGET", Text(f"{current.id} {current.title}", style="steel"))
        if not (CLIENT_DIR / "index.html").exists():
            grid.add_row("WARNING", Text("web client files missing — try: python game.py tui", style="warn"))
        grid.add_row("JACK OUT", Text("ctrl+c   ·   terminal mode: python game.py tui", style="muted"))
        console.print()
        console.print(Panel(grid, title=ui.gradient("NULL//SECTOR"), title_align="left",
                            subtitle="[muted]neural link established[/]", subtitle_align="right",
                            border_style=ui.DIM, padding=(1, 2), expand=False))

    try:
        serve(session, port=port, open_browser=open_browser, on_ready=banner)
    except OSError as exc:
        console.print(f"\n  [bad]Couldn't start the local server:[/] [steel]{exc}[/]")
        console.print("  [muted]Try another port with --port, or play in the terminal: python game.py tui[/]\n")
        sys.exit(1)
    console.print("\n  [pink]Jacking out. Progress saved.[/]\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="NULL//SECTOR — a Python survival RPG")
    parser.add_argument("command", nargs="?", choices=["play", *TERMINAL_COMMANDS], default="play",
                        help="play (web client, default) | tui | hack | watch | reset | productivity")
    parser.add_argument("--port", type=int, default=7777, help="web client port (default 7777)")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    parser.add_argument("--fast", action="store_true", help="skip terminal animations")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")

    if args.command == "play":
        play_web(args.port, open_browser=not args.no_browser)
    else:
        from engine.tui import run
        run(args.command, fast=args.fast)


if __name__ == "__main__":
    main()
