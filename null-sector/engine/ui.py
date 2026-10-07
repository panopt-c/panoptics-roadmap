"""Everything you see. Built on Rich: panels, live-updating HP bars, typed transmissions."""
from __future__ import annotations

import random
import time

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from engine import errors
from engine.mission import Cutscene, Mission
from engine.runner import HackReport
from engine.state import Save
from levels import ALL_LEVELS, CAMPAIGN, next_level

CYAN, PINK, ACID, AMBER, BLOOD, STEEL, DIM = (
    "#00f0ff", "#ff2bd6", "#39ff14", "#ffb000", "#ff3355", "#8892a6", "#4a5160")

THEME = Theme({
    "accent": f"bold {CYAN}", "pink": PINK, "ok": f"bold {ACID}", "bad": f"bold {BLOOD}",
    "warn": f"bold {AMBER}", "steel": STEEL, "muted": DIM, "key": f"bold black on {CYAN}",
})

LOGO = """\
███╗   ██╗██╗   ██╗██╗     ██╗         ██╗ ██╗███████╗███████╗ ██████╗████████╗ ██████╗ ██████╗
████╗  ██║██║   ██║██║     ██║        ██╔╝██╔╝██╔════╝██╔════╝██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗
██╔██╗ ██║██║   ██║██║     ██║       ██╔╝██╔╝ ███████╗█████╗  ██║        ██║   ██║   ██║██████╔╝
██║╚██╗██║██║   ██║██║     ██║      ██╔╝██╔╝  ╚════██║██╔══╝  ██║        ██║   ██║   ██║██╔══██╗
██║ ╚████║╚██████╔╝███████╗███████╗██╔╝██╔╝   ███████║███████╗╚██████╗   ██║   ╚██████╔╝██║  ██║
╚═╝  ╚═══╝ ╚═════╝ ╚══════╝╚══════╝╚═╝ ╚═╝    ╚══════╝╚══════╝ ╚═════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝"""

LOGO_SMALL = r"""
 _  _ _   _ _    _      _______ ___ ___ _____ ___  ___
| \| | | | | |  | |    / / / __| __/ __|_   _/ _ \| _ \
| .` | |_| | |__| |__ / / /\__ \ _| (__  | || (_) |   /
|_|\_|\___/|____|____/_/_/ |___/___\___| |_| \___/|_|_\
"""[1:-1]

ACCESS_GRANTED = r"""
   _   ___ ___ ___ ___ ___    ___ ___    _   _  _ _____ ___ ___
  /_\ / __/ __| __/ __/ __|  / __| _ \  /_\ | \| |_   _| __|   \
 / _ \ (_| (__| _|\__ \__ \ | (_ |   / / _ \| .` | | | | _|| |) |
/_/ \_\___\___|___|___/___/  \___|_|_\/_/ \_\_|\_| |_| |___|___/
"""[1:-1]

GLITCH = "▓▒░█▚▞#@%&$"


def make_console() -> Console:
    return Console(theme=THEME, highlight=False)


# ── helpers ─────────────────────────────────────────────────
def _mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def gradient(art: str, start: str = CYAN, end: str = PINK, glitch: float = 0.0) -> Text:
    """Paint ASCII art with a left-to-right neon gradient, optionally corrupted by glitch noise."""
    lines = art.splitlines()
    width = max(len(line) for line in lines)
    text = Text(no_wrap=True)
    for row, line in enumerate(lines):
        for col, ch in enumerate(line):
            if ch != " " and glitch and random.random() < glitch:
                text.append(random.choice(GLITCH), style=f"bold {random.choice([PINK, ACID, '#ffffff'])}")
            else:
                text.append(ch, style=f"bold {_mix(start, end, col / max(width - 1, 1))}")
        if row < len(lines) - 1:
            text.append("\n")
    return text


def logo(console: Console, glitch: float = 0.0) -> Text:
    art = LOGO if console.width >= 100 else LOGO_SMALL
    return gradient(art, glitch=glitch)


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    return f"{h}:{rem // 60:02d}:{rem % 60:02d}" if h else f"{rem // 60:02d}:{rem % 60:02d}"


def ask_key(console: Console, keys: str, default: str = "") -> str:
    """Read one command letter. Enter picks the default."""
    while True:
        raw = console.input("[accent]  ▸ [/]").strip().lower()
        if not raw and default:
            return default
        if raw[:1] and raw[0] in keys:
            return raw[0]
        console.print(f"  [muted]Unknown command. Options: {' '.join(keys.upper())}[/]")


def command_bar(*options: tuple[str, str]) -> Text:
    bar = Text("  ")
    for key, label in options:
        bar.append(f" {key} ", style="key")
        bar.append(f" {label}   ", style="steel")
    return bar


# ── boot ────────────────────────────────────────────────────
def boot_sequence(console: Console, animate: bool) -> None:
    console.clear()
    if not animate:
        return
    with Live(Align.center(logo(console, glitch=0.6)), console=console, transient=True,
              refresh_per_second=30) as live:
        for level in (0.5, 0.35, 0.2, 0.1, 0.25, 0.05, 0.0):
            live.update(Align.center(logo(console, glitch=level)))
            time.sleep(0.07)
    lines = [
        ("re-establishing neural link", "OK", "ok"),
        ("mounting /dev/consciousness", "OK", "ok"),
        ("scanning sector", "HOSTILE PROCESSES DETECTED", "bad"),
    ]
    for label, result, style in lines:
        console.print(f"  [muted]>[/] [steel]{label}[/]", end="")
        for _ in range(36 - len(label)):
            console.print("[muted].[/]", end="")
            time.sleep(0.006)
        console.print(f" [{style}]{result}[/]")
    time.sleep(0.35)


# ── main HUD ────────────────────────────────────────────────
def operative_panel(save: Save) -> Panel:
    title, floor, nxt = save.rank()
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted", no_wrap=True, min_width=8)
    grid.add_column(no_wrap=True)
    callsign = Text(save.callsign, style="accent") if save.callsign else Text("▒▒▒▒▒ UNREGISTERED", style="bad")
    grid.add_row("CALLSIGN", callsign)
    grid.add_row("RANK", Text(title, style=f"bold {PINK}"))
    if nxt:
        filled = round(12 * (save.xp - floor) / (nxt - floor))
        grid.add_row("XP", Text.assemble(("█" * filled, CYAN), ("░" * (12 - filled), DIM),
                                         (f" {save.xp}/{nxt}", "steel")))
    else:
        grid.add_row("XP", Text(f"{save.xp}  MAX RANK", style="ok"))
    grid.add_row("BREACHES", Text(f"{len(save.cleared)} / {len(ALL_LEVELS)}", style="steel"))
    return Panel(grid, title="[accent]OPERATIVE[/]", border_style=CYAN, padding=(1, 2))


def sector_map(save: Save) -> Panel:
    current = next_level(save.cleared)
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    for sector in CAMPAIGN:
        chips = Text()
        for lvl in sector.levels:
            if lvl.id in save.cleared:
                chips.append("■ ", style=f"bold {sector.color}")
            elif current and lvl.id == current.id:
                chips.append("▶ ", style="bold blink #ffffff")
            else:
                chips.append("□ ", style=DIM)
        unlocked = any(l.id in save.cleared for l in sector.levels) or (current in sector.levels)
        name_style = f"bold {sector.color}" if unlocked else DIM
        table.add_row(Text(f"S{sector.tier} {sector.name}", style=name_style),
                      Text(sector.zone, style="steel" if unlocked else DIM), chips)
    body = [table, Text()]
    if current:
        body.append(Text.assemble(("NEXT ▶ ", "accent"), (f"{current.id} {current.title}", "bold"),
                                  (f"  {current.concept}", "steel")))
    else:
        body.append(Text("ALL SECTORS RESTORED. The Core is yours.", style="ok"))
    return Panel(Group(*body), title="[pink]SECTOR MAP[/]", border_style=PINK, padding=(1, 2))


def hud(console: Console, save: Save) -> None:
    console.clear()
    console.print(Panel(Align.center(logo(console)), border_style=DIM,
                        subtitle="[muted]a python survival rpg · zero → hero[/]"))
    row = Table.grid(expand=True, padding=(0, 1))
    row.add_column(ratio=2)
    row.add_column(ratio=3)
    row.add_row(operative_panel(save), sector_map(save))
    console.print(row)


# ── mission briefing ────────────────────────────────────────
def briefing(console: Console, mission: Mission, mission_file_display: str, file_uri: str) -> None:
    console.clear()
    console.print(Rule(f"[accent]LEVEL {mission.id[1:]} // {mission.title}[/]  [steel]{mission.concept}[/]",
                       style=CYAN))
    story = Table.grid(expand=True, padding=(0, 3))
    story.add_column(ratio=1)
    story.add_column(no_wrap=True)
    enemy = Group(Text(mission.enemy_art, style=BLOOD), Text(),
                  Align.center(Text(mission.enemy, style="bad")))
    story.add_row(Markdown(mission.briefing), enemy)
    console.print(Panel(story, title="[pink]◉ INCOMING TRANSMISSION[/]", border_style=PINK, padding=(1, 2)))
    console.print(Panel(Markdown(mission.why, code_theme="monokai"),
                        title="[accent]WHY THIS MATTERS IN AI ENGINEERING[/]", border_style=CYAN,
                        padding=(1, 2)))
    console.print(Panel(Markdown(mission.manual, code_theme="monokai"), title="[ok]FIELD MANUAL[/]",
                        border_style=ACID, padding=(1, 2)))
    objectives = Text()
    for i, check in enumerate(mission.checks, 1):
        objectives.append(f"  LAYER {i}  ", style="muted")
        objectives.append(f"{check.name}\n", style="steel")
    objectives.append("\n  MISSION FILE ▶ ", style="accent")
    objectives.append(mission_file_display, style=f"bold underline link {file_uri}")
    console.print(Panel(objectives, title=f"[warn]OBJECTIVES — {len(mission.checks)} FIREWALL LAYERS[/]",
                        border_style=AMBER, padding=(1, 1)))


# ── combat ──────────────────────────────────────────────────
def _hp_bar(total: int, remaining: int) -> Text:
    bar = Text()
    for i in range(total):
        bar.append("███ " if i < remaining else "░░░ ", style=BLOOD if i < remaining else DIM)
    return bar


def battle_view(mission: Mission, report: HackReport, revealed: int, attempt: int) -> Group:
    shown = report.checks[:revealed]
    remaining = report.total - sum(c["passed"] for c in shown)
    status = Table.grid(padding=(0, 2))
    status.add_column(style="muted", no_wrap=True)
    status.add_column(no_wrap=True)
    status.add_row("FIREWALL", _hp_bar(report.total, remaining))
    status.add_row("LAYERS", Text(f"{report.total - remaining} / {report.total} breached", style="steel"))
    status.add_row("ATTEMPT", Text(f"#{attempt}", style="steel"))
    header = Table.grid(padding=(0, 4))
    header.add_column(no_wrap=True)
    header.add_column()
    header.add_row(Text(mission.enemy_art, style=BLOOD), status)
    enemy_panel = Panel(header, title=f"[bad]⚠ TARGET LOCKED // {mission.enemy}[/]", border_style=BLOOD,
                        padding=(1, 2))

    layers = Table.grid(padding=(0, 2))
    layers.add_column(no_wrap=True)
    layers.add_column(no_wrap=True)
    layers.add_column()
    for i, check in enumerate(report.checks):
        tag = Text(f"LAYER {i + 1}", style="muted")
        if i < revealed:
            ok = check["passed"]
            layers.add_row(tag, Text("✔ BREACHED" if ok else "✖ BLOCKED ", style="ok" if ok else "bad"),
                           Text(check["name"], style="steel" if ok else "bold"))
        elif i == revealed:
            layers.add_row(tag, Text("▒ INJECTING", style="warn"), Text(check["name"], style="muted"))
        else:
            layers.add_row(tag, Text("░ QUEUED   ", style=DIM), Text(check["name"], style=DIM))
    return Group(enemy_panel, layers, Text())


def combat_log(report: HackReport) -> Panel | None:
    err = report.error
    if report.status == "ok" or not err:
        return None
    titles = {"syntax_error": "SYNTAX FAULT", "crash": "SYSTEM CRASH", "timeout": "INFINITE LOOP",
              "harness_error": "GRADER FAULT"}
    parts = []
    where = f" at line {err['line']}" if err.get("line") else ""
    parts.append(Text(f"{err['type']}{where}", style="bad"))
    if err.get("code") and err.get("line"):
        parts.append(Syntax(err["code"], "python", line_numbers=True, start_line=err["line"],
                            theme="monokai", background_color="default"))
    parts.append(Text.assemble(("RAW      ", "muted"), (err["message"], "steel")))
    parts.append(Text.assemble(("DECODED  ", "muted"), (errors.decode(err), "bold")))
    return Panel(Group(*parts), title=f"[bad]COMBAT LOG // {titles.get(report.status, 'ERROR')}[/]",
                 border_style=BLOOD, padding=(1, 2))


def aftermath(console: Console, report: HackReport) -> None:
    log = combat_log(report)
    if log:
        console.print(log)
    fail = report.first_failure
    if fail and report.status != "syntax_error":
        intel = [Text(fail["message"], style="bold")]
        if fail["hint"]:
            intel.append(Text.assemble(("▸ TRY  ", "accent"), (fail["hint"], "steel")))
        console.print(Panel(Group(*intel), title=f"[warn]INTEL // {fail['name']}[/]", border_style=AMBER,
                            padding=(1, 2)))
    if report.stdout.strip():
        out = report.stdout.rstrip()
        if out.count("\n") > 12:
            out = "\n".join(out.splitlines()[-12:])
        console.print(Panel(Text(out, style="steel"), title="[muted]YOUR OUTPUT[/]", border_style=DIM))


def play_hack(console: Console, mission: Mission, report: HackReport, attempt: int, animate: bool) -> None:
    if animate:
        with Live(battle_view(mission, report, 0, attempt), console=console, refresh_per_second=30) as live:
            time.sleep(0.25)
            for i in range(1, report.total + 1):
                time.sleep(0.16)
                live.update(battle_view(mission, report, i, attempt))
    else:
        console.print(battle_view(mission, report, report.total, attempt))
    aftermath(console, report)


# ── rewards ─────────────────────────────────────────────────
def victory(console: Console, mission: Mission, lines: list[tuple[str, int]], rank_up: str | None,
            animate: bool) -> None:
    console.print()
    console.print(Align.center(gradient(ACCESS_GRANTED, ACID, CYAN)))
    console.print()
    console.print(Align.center(Text(f"{mission.enemy} ........ DELETED", style="bad")))
    console.print()

    def tally(progress: float) -> Panel:
        grid = Table.grid(padding=(0, 4))
        grid.add_column(style="steel", no_wrap=True)
        grid.add_column(justify="right", no_wrap=True)
        total = 0
        for label, amount in lines:
            shown = round(amount * progress)
            total += shown
            grid.add_row(label, Text(f"+{shown}", style="accent"))
        grid.add_row(Text("TOTAL XP", style="bold"), Text(f"+{total}", style="ok"))
        return Panel(grid, border_style=ACID, title="[ok]REWARDS[/]", padding=(1, 3), expand=False)

    if animate:
        with Live(Align.center(tally(0)), console=console, refresh_per_second=30) as live:
            for step in range(1, 21):
                time.sleep(0.03)
                live.update(Align.center(tally(step / 20)))
    else:
        console.print(Align.center(tally(1)))
    if rank_up:
        console.print(Align.center(Text(f"▲ RANK UP ▲  {rank_up}", style=f"bold reverse {PINK}")))
    console.print()


def transmission(console: Console, cutscene: Cutscene, animate: bool, speed: float) -> None:
    """The in-terminal cutscene. Always plays, with or without Higgsfield."""

    def frame(text: Text) -> Panel:
        return Panel(text, title=f"[pink]◉ TRANSMISSION // {cutscene.title}[/]", border_style=PINK,
                     padding=(1, 3), subtitle="[muted]ctrl+c to skip[/]")

    full = Text()
    for i, line in enumerate(cutscene.narration):
        full.append("\n\n" if i else "")
        full.append("> ", style="pink")
        full.append(line, style="steel")
    if not animate:
        console.print(frame(full))
        return
    shown = Text()
    try:
        with Live(frame(shown), console=console, refresh_per_second=60) as live:
            for i, line in enumerate(cutscene.narration):
                shown.append("\n\n" if i else "")
                shown.append("> ", style="pink")
                for ch in line:
                    shown.append(ch, style="steel")
                    live.update(frame(shown))
                    time.sleep(speed)
                time.sleep(0.35)
    except KeyboardInterrupt:
        console.print(frame(full))


def gallery(console: Console, save: Save) -> None:
    console.clear()
    console.print(Rule("[pink]MEMORY FRAGMENTS[/]", style=PINK))
    if not save.gallery:
        console.print("\n  [muted]No cutscenes rendered yet. Clear a level with Higgsfield connected.[/]\n")
        return
    table = Table(border_style=DIM, header_style="accent")
    table.add_column("LEVEL")
    table.add_column("SCENE")
    table.add_column("FILE")
    for item in save.gallery:
        table.add_row(item["mission"], item["title"], item.get("path") or item.get("url", ""))
    console.print(table)
