"""Launches the grader in a sandboxed subprocess and turns its JSON into a HackReport."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from engine.mission import Mission
from engine.state import GAME_DIR, MISSIONS_DIR


@dataclass
class HackReport:
    status: str            # ok | crash | syntax_error | timeout | harness_error
    checks: list[dict]
    stdout: str
    error: dict | None
    exports: dict

    @property
    def passed(self) -> int:
        return sum(c["passed"] for c in self.checks)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def victory(self) -> bool:
        return self.status == "ok" and self.total > 0 and self.passed == self.total

    @property
    def first_failure(self) -> dict | None:
        return next((c for c in self.checks if not c["passed"]), None)


def mission_path(mission: Mission, missions_dir: Path | None = None) -> Path:
    return (missions_dir or MISSIONS_DIR) / mission.filename


def ensure_mission_file(mission: Mission, reset: bool = False, missions_dir: Path | None = None) -> Path:
    """Drop the starter file into missions/ — never overwriting your work unless asked."""
    path = mission_path(mission, missions_dir)
    if reset or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(mission.starter.lstrip("\n"), encoding="utf-8")
    return path


def hack(mission: Mission, missions_dir: Path | None = None) -> HackReport:
    path = ensure_mission_file(mission, missions_dir=missions_dir)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "report.json"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            # cwd is the code root (where `engine` and `levels` live), wherever the player's files are.
            proc = subprocess.run(
                [sys.executable, "-m", "engine.harness", mission.slug, str(path), str(out)],
                cwd=GAME_DIR, env=env, stdin=subprocess.DEVNULL,
                capture_output=True, timeout=mission.timeout,
            )
        except subprocess.TimeoutExpired:
            return HackReport(
                status="timeout", stdout="", exports={},
                error={"type": "Timeout", "message": f"Your code ran for over {mission.timeout:g}s.",
                       "line": None, "code": "", "traceback": ""},
                checks=[{"name": c.name, "passed": False, "hint": "",
                         "message": "Never finished — the script was still running."} for c in mission.checks],
            )
        if not out.exists():
            return HackReport("harness_error", [], "", {"type": "HarnessError", "line": None, "code": "",
                              "message": "The grader crashed before reporting:\n" + proc.stderr.decode(errors="replace")[-1500:],
                              "traceback": ""}, {})
        data = json.loads(out.read_text(encoding="utf-8"))
    return HackReport(data["status"], data["checks"], data["stdout"], data["error"], data["exports"])
