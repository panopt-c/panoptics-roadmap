"""Grades one mission file. Runs in its own process, launched by engine/runner.py.

Why a separate process? Your code might crash, loop forever, or call exit().
Isolating it means none of that can take down the game — the same reason
real ML platforms run each training job in its own container.

Usage:  python -m engine.harness <level_slug> <player_file> <report.json>
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import sys
import traceback
from pathlib import Path

from engine.mission import Context, Fail
from levels import load_mission


def describe_exception(exc: BaseException, player_file: Path, source_lines: list[str]) -> dict:
    """Pull out the line of *the player's* code that blew up, ignoring engine internals."""
    frames = [f for f in traceback.extract_tb(exc.__traceback__)
              if Path(f.filename).resolve() == player_file]
    line = frames[-1].lineno if frames else None
    code = source_lines[line - 1].rstrip() if line and line <= len(source_lines) else ""
    trace = "".join(traceback.format_list(frames)) + "".join(traceback.format_exception_only(exc))
    return {"type": type(exc).__name__, "message": str(exc), "line": line, "code": code,
            "traceback": trace.replace(str(player_file), player_file.name)}


def json_safe(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return repr(value)


def load_for_grading(key: str):
    """A campaign slug, `lab:<slug>` for a Lab mission, or `drill:<drill_id>:<seed>` for a drill instance."""
    if key.startswith("lab:"):
        from lab import load_mission as load_lab
        return load_lab(key[4:])
    if key.startswith("drill:"):
        from engine.drills import instance
        _, drill_id, seed = key.split(":", 2)
        return instance(drill_id, int(seed))
    return load_mission(key)


def grade(slug: str, player_file: Path) -> dict:
    mission = load_for_grading(slug)
    report = {"status": "ok", "stdout": "", "error": None, "checks": [], "exports": {}}

    source = player_file.read_text(encoding="utf-8")
    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(player_file))
        code = compile(tree, str(player_file), "exec")
    except SyntaxError as exc:
        report["status"] = "syntax_error"
        report["error"] = {"type": type(exc).__name__, "message": exc.msg, "line": exc.lineno,
                           "code": (exc.text or "").rstrip(), "traceback": ""}
        report["checks"] = [{"name": c.name, "passed": False,
                             "message": "Python couldn't read your file, so nothing ran.", "hint": ""}
                            for c in mission.checks]
        return report

    # Run the player's file like `python their_file.py`, but capture what it prints.
    namespace = {"__name__": "__main__" if mission.run_as_main else slug,
                 "__file__": str(player_file), "__builtins__": __builtins__}
    printed = io.StringIO()
    os.chdir(player_file.parent)
    sys.path.insert(0, str(player_file.parent))
    try:
        with contextlib.redirect_stdout(printed):
            exec(code, namespace)
    except SystemExit as exc:
        if exc.code not in (None, 0):
            report["status"] = "crash"
            report["error"] = describe_exception(exc, player_file, lines)
    except BaseException as exc:  # noqa: BLE001 — any crash in player code is a game event
        report["status"] = "crash"
        report["error"] = describe_exception(exc, player_file, lines)
    report["stdout"] = printed.getvalue()

    ctx = Context(namespace, report["stdout"], source, tree, crashed=report["status"] == "crash")
    for check in mission.checks:
        entry = {"name": check.name, "passed": True, "message": "", "hint": ""}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                check.fn(ctx)
        except Fail as fail:
            entry.update(passed=False, message=fail.message, hint=fail.hint)
        except Exception as exc:  # noqa: BLE001
            entry.update(passed=False, message=f"{type(exc).__name__}: {exc}")
        report["checks"].append(entry)
    report["exports"] = {k: json_safe(v) for k, v in ctx.exports.items()}
    return report


def main() -> None:
    slug, player_path, out_path = sys.argv[1:4]
    out = Path(out_path).resolve()
    try:
        report = grade(slug, Path(player_path).resolve())
    except Exception:  # noqa: BLE001 — a bug in the level itself, not the player's code
        report = {"status": "harness_error", "stdout": "", "checks": [], "exports": {},
                  "error": {"type": "HarnessError", "message": traceback.format_exc(),
                            "line": None, "code": "", "traceback": ""}}
    out.write_text(json.dumps(report), encoding="utf-8")


if __name__ == "__main__":
    main()
