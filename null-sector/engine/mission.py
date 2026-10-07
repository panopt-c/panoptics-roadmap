"""The building blocks every level is made of.

A level file in levels/ creates one `Mission` and registers checks on it:

    MISSION = Mission(id="L01", ...)

    @MISSION.check("Identity string")
    def _(ctx):
        value = ctx.get("callsign")
        ctx.expect_type("callsign", value, str)

Each check is one firewall layer. A check passes if it returns normally and
fails by raising `Fail`. Checks run inside engine/harness.py, in a separate
process from the game, after the player's file has executed.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Callable

TYPE_NAMES = {
    str: "a str (text)",
    int: "an int (whole number)",
    float: "a float (decimal)",
    bool: "a bool (True/False)",
    list: "a list",
    dict: "a dict",
    type(None): "None (empty)",
}


def type_name(t: type) -> str:
    return TYPE_NAMES.get(t, f"a {t.__name__}")


class Fail(Exception):
    """Raise inside a check to fail that layer with a human-readable reason."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.message = message
        self.hint = hint


@dataclass
class Check:
    name: str
    fn: Callable[["Context"], None]


@dataclass
class Cutscene:
    title: str
    narration: list[str]       # typed out in the terminal
    shot: str                  # what the camera sees (Higgsfield image prompt)
    camera: str = ""           # camera move for the video version
    anchor: bool = False       # True: this frame becomes your avatar reference


@dataclass
class Mission:
    id: str
    slug: str                  # file name, without .py, in missions/
    title: str
    concept: str
    enemy: str
    xp: int
    par_seconds: int           # beat this time for a speed bonus
    briefing: str              # story (markdown)
    why: str                   # the real-world AI-engineering reason (markdown)
    manual: str                # the mini-tutorial (markdown)
    starter: str               # the file the player edits
    enemy_art: str = ""
    cutscene: Cutscene | None = None
    timeout: float = 10.0      # seconds before the code is treated as an infinite loop
    run_as_main: bool = True   # whether `if __name__ == "__main__":` blocks run
    checks: list[Check] = field(default_factory=list)

    def check(self, name: str):
        def register(fn):
            self.checks.append(Check(name, fn))
            return fn
        return register

    @property
    def filename(self) -> str:
        return f"{self.slug}.py"


class Context:
    """What a check can see: the player's variables, printed output, and source code."""

    def __init__(self, ns: dict, stdout: str, source: str, tree: ast.AST, crashed: bool):
        self.ns = ns
        self.stdout = stdout
        self.source = source
        self.tree = tree
        self.crashed = crashed
        self.exports: dict = {}

    # ── reading the player's variables ──────────────────────
    def get(self, name: str):
        if name not in self.ns:
            if self.crashed and self.assignments(name):
                raise Fail(f"`{name}` doesn't exist — your script crashed before creating it. "
                           "Fix the crash in the COMBAT LOG first.")
            raise Fail(f"No variable named `{name}` found.",
                       hint=f"Create it with  {name} = ...  (spelling and capitals must match exactly)")
        return self.ns[name]

    def expect_type(self, name: str, value, expected: type) -> None:
        actual = type(value)
        if actual is expected:
            return
        hint = ""
        if actual is str and expected in (int, float, bool):
            hint = f"Remove the quotes: {value!r} is text, {value} without quotes is the real value."
        elif expected is str:
            hint = 'Text must be wrapped in quotes, like "this".'
        elif actual is float and expected is int:
            hint = "Drop the decimal point — whole numbers are written without .0"
        elif actual is int and expected is float:
            hint = "Write it with a decimal point, e.g. 0.5 instead of 1/2 or 50."
        raise Fail(f"`{name}` is {type_name(actual)}, but it needs to be {type_name(expected)}.", hint)

    # ── reading the player's code ───────────────────────────
    def assignments(self, name: str) -> list[ast.AST]:
        """Every right-hand side assigned to `name`, e.g. the `1.0 - battery` in `x = 1.0 - battery`."""
        values = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                    values.append(node.value)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                if isinstance(node.target, ast.Name) and node.target.id == name and node.value:
                    values.append(node.value)
        return values

    def derived_from(self, name: str, source_var: str) -> bool:
        """True if `name` is computed using `source_var` instead of being typed in by hand."""
        return any(
            isinstance(n, ast.Name) and n.id == source_var
            for value in self.assignments(name)
            for n in ast.walk(value)
        )

    def call_uses(self, func: str, var: str) -> bool:
        """True if some call to `func(...)` mentions the variable `var` in its arguments."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == func:
                if any(isinstance(n, ast.Name) and n.id == var for n in ast.walk(node)):
                    return True
        return False

    # ── feeding values back into the game ───────────────────
    def export(self, key: str, value) -> None:
        """Send a value from the player's code into the game world (e.g. their callsign)."""
        self.exports[key] = value
