"""Check shipped campaign/drill contracts without touching player saves.

Each content import/build runs in a fresh process with a deadline. Optional
starter grading uses a temporary mission folder and the game's real grader.
This is a developer check, not a sandbox for hostile third-party Python.
Determinism covers generated mission fields/check names and captured inputs, not function behavior;
authors must still test reference solutions and realistic wrong answers.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import random
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def asset_errors(assets: object, filename: str) -> list[str]:
    """Check paths using both Windows and POSIX rules, on either host."""
    if not isinstance(assets, dict):
        return ["assets must be a filename-to-text object"]
    errors, seen = [], {filename.casefold()}
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                *(f"lpt{i}" for i in range(1, 10))}
    for name, content in assets.items():
        if not isinstance(name, str) or not name:
            errors.append("asset filenames must be nonempty strings")
            continue
        normalized = name.replace("\\", "/")
        parts = normalized.split("/")
        unsafe = (PurePosixPath(normalized).is_absolute() or PureWindowsPath(name).drive
                  or any(p in {"", ".", ".."} or p.endswith((" ", "."))
                         or p.split(".")[0].casefold() in reserved for p in parts)
                  or any(ord(c) < 32 or c in ':*?"<>|' for c in normalized))
        if unsafe:
            errors.append(f"unsafe cross-platform asset path: {name!r}")
        folded = normalized.casefold()
        if folded in seen:
            errors.append(f"asset collides with another asset or mission source: {name!r}")
        seen.add(folded)
        if not isinstance(content, str):
            errors.append(f"asset {name!r} must contain text")
    return errors


def validate_mission(mission: object, *, campaign: bool) -> list[str]:
    from engine.mission import Mission
    if not isinstance(mission, Mission):
        return ["module/build must return a Mission"]
    errors = []
    required = ["id", "slug", "title", "briefing", "starter"]
    if campaign:
        required += ["why", "manual"]
    for name in required:
        value = getattr(mission, name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{name} must contain text")
    if not isinstance(mission.slug, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", mission.slug):
        errors.append("slug must be a portable Python module/file name")
    for name in ("xp", "par_seconds", "tier"):
        value = getattr(mission, name)
        if type(value) is not int or value <= 0:
            errors.append(f"{name} must be a positive integer")
    if type(mission.tier) is int and not 1 <= mission.tier <= 5:
        errors.append("tier must be between 1 and 5")
    if (type(mission.timeout) not in (int, float) or not math.isfinite(mission.timeout)
            or not 0 < mission.timeout <= 20):
        errors.append("timeout must be finite and between 0 and 20 seconds")
    checks = mission.checks
    if not isinstance(checks, list) or not checks:
        errors.append("mission must register at least one check")
    else:
        names = []
        for check in checks:
            name = getattr(check, "name", None)
            if not isinstance(name, str) or not name.strip() or not callable(getattr(check, "fn", None)):
                errors.append("each check needs a nonempty name and callable function")
            elif name in names:
                errors.append(f"duplicate check name: {name}")
            names.append(name)
        if campaign and not 5 <= len(checks) <= 9:
            errors.append("campaign authoring contract requires 5 to 9 checks")
    errors.extend(asset_errors(mission.assets, mission.filename))
    return errors


def mission_fingerprint(mission) -> str:
    """Compare public generated content, excluding process-specific callables."""
    def encode(value):
        if isinstance(value, random.Random):
            return {"random_state": encode(value.getstate())}
        if hasattr(value, "__dataclass_fields__"):
            return {f.name: encode(getattr(value, f.name)) for f in fields(value)
                    if f.name not in {"checks", "fn"}}
        if isinstance(value, dict):
            return {k: encode(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [encode(v) for v in value]
        return value
    payload = encode(mission)
    payload["checks"] = [check.name for check in mission.checks]
    payload["captures"] = [
        {name: encode(cell.cell_contents)
         for name, cell in zip(check.fn.__code__.co_freevars, check.fn.__closure__ or ())}
        for check in mission.checks
    ]
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def worker(mode: str, key: str, seed: int, exercise: bool) -> dict:
    if mode == "catalog":
        import levels
        result = {"campaign": [{"id": entry.id, "slug": entry.slug,
                                "present": (ROOT / "levels" / f"{entry.slug}.py").is_file()}
                               for sector in levels._CAMPAIGN for entry in sector.levels]}
        registered = {entry["slug"] for entry in result["campaign"]}
        result["orphans"] = sorted(path.name for path in (ROOT / "levels").glob("level_*.py")
                                   if path.stem not in registered)
        if key == "campaign":
            result["drills"] = []
            return result
        try:
            from engine.drills import all_drills
            result["drills"] = [{"id": d.id, "tier": d.tier} for d in all_drills()]
        except Exception as exc:
            result["drills"] = []
            result["drill_error"] = f"{type(exc).__name__}: {exc}"
        return result
    if mode == "campaign":
        from levels import load_mission
        mission = load_mission(key)
    else:
        from engine.drills import instance
        mission = instance(key, seed)
    errors = validate_mission(mission, campaign=mode == "campaign")
    result = {"id": getattr(mission, "id", None), "slug": getattr(mission, "slug", None),
              "errors": errors, "starter": "not run"}
    if errors:
        return result
    result["fingerprint"] = mission_fingerprint(mission)
    result["checks"] = len(mission.checks)
    if exercise:
        from engine.runner import hack
        with tempfile.TemporaryDirectory(prefix="ns-content-") as folder:
            report = hack(mission, missions_dir=Path(folder))
        result["starter"] = report.status
        if report.status in {"harness_error", "timeout"}:
            errors.append(f"starter grader failed: {report.status}")
        elif report.victory:
            errors.append("untouched starter passes every check")
        elif report.total != len(mission.checks):
            errors.append("grader check count differs from the generated mission")
        elif not any(not c["passed"] and c.get("message") for c in report.checks):
            errors.append("starter failure has no actionable message")
    return result


def call_worker(mode: str, key: str = "", seed: int = 0, *, exercise=False, timeout=45, hash_seed=1) -> dict:
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", mode,
               "--key", key, "--seed", str(seed)]
    if exercise:
        command.append("--exercise-starters")
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout,
                                   env={**os.environ, "PYTHONHASHSEED": str(hash_seed),
                                        "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    except subprocess.TimeoutExpired:
        return {"errors": [f"content worker exceeded {timeout}s deadline"]}
    if completed.returncode:
        return {"errors": [f"worker exited {completed.returncode}: {completed.stderr[-800:].strip()}"]}
    try:
        result = json.loads(completed.stdout)
        if not isinstance(result, dict):
            raise ValueError("worker returned a non-object")
        return result
    except (ValueError, TypeError) as exc:
        return {"errors": [f"invalid worker report: {exc}"]}


def validate_content(*, scope="all", seeds=(0, 17), exercise=False, require_complete=False) -> dict:
    catalog = call_worker("catalog", scope)
    errors = list(catalog.get("errors", []))
    missing, records, counts = [], [], {tier: 0 for tier in range(1, 6)}
    if errors:
        return {"ok": False, "errors": errors, "missing": [], "records": [], "drills_per_tier": counts}
    if scope in {"all", "campaign"}:
        errors.extend(f"level module missing from campaign registry: {name}" for name in catalog.get("orphans", []))
        for entry in catalog["campaign"]:
            if not entry["present"]:
                missing.append(entry["id"])
                continue
            record = call_worker("campaign", entry["slug"], exercise=exercise)
            record.update(content=entry["id"], kind="campaign")
            if not record.get("errors") and (record.get("id") != entry["id"] or record.get("slug") != entry["slug"]):
                record.setdefault("errors", []).append("mission identity differs from the campaign registry")
            records.append(record)
        if require_complete and missing:
            errors.append(f"missing campaign modules: {', '.join(missing)}")
    if scope in {"all", "drills"}:
        if catalog.get("drill_error"):
            errors.append(f"drill registry cannot load: {catalog['drill_error']}")
        for drill in catalog["drills"]:
            counts[drill["tier"]] = counts.get(drill["tier"], 0) + 1
            for seed in seeds:
                record = call_worker("drill", drill["id"], seed, exercise=exercise)
                record.update(content=drill["id"], kind="drill", seed=seed)
                if not record.get("errors"):
                    repeated = call_worker("drill", drill["id"], seed, hash_seed=923)
                    if repeated.get("errors"):
                        record.setdefault("errors", []).extend(repeated["errors"])
                    elif repeated.get("fingerprint") != record.get("fingerprint"):
                        record.setdefault("errors", []).append("same seed generated different content across processes")
                records.append(record)
        if require_complete:
            for tier, count in counts.items():
                if count < 12:
                    errors.append(f"tier {tier} has {count}/12 required drills")
    for record in records:
        errors.extend(f"{record['content']}: {error}" for error in record.get("errors", []))
    return {"ok": not errors, "errors": errors, "missing": missing, "records": records,
            "drills_per_tier": counts,
            "scope": "Structural contracts and generated-content determinism; not proof of solvability."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("all", "campaign", "drills"), default="all")
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 17])
    parser.add_argument("--exercise-starters", action="store_true")
    parser.add_argument("--require-complete", action="store_true", help="require all 25 levels and 12 drills per tier")
    parser.add_argument("--json", action="store_true", help="emit the complete machine-readable report")
    parser.add_argument("--worker", choices=("catalog", "campaign", "drill"), help=argparse.SUPPRESS)
    parser.add_argument("--key", default="", help=argparse.SUPPRESS)
    parser.add_argument("--seed", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            # Authors may print on import; don't let that corrupt the worker protocol.
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                result = worker(args.worker, args.key, args.seed, args.exercise_starters)
        except Exception as exc:
            result = {"errors": [f"{type(exc).__name__}: {exc}"]}
        print(json.dumps(result, allow_nan=False))
        return 0
    result = validate_content(scope=args.scope, seeds=args.seeds, exercise=args.exercise_starters,
                              require_complete=args.require_complete)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Content contracts: {'PASS' if result['ok'] else 'FAIL'} ({len(result['records'])} builds)")
        if result["missing"]:
            print("Not shipped: " + ", ".join(result["missing"]))
        for error in result["errors"]:
            print("ERROR: " + error)
        print(result.get("scope", ""))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
