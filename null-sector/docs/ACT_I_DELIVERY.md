# Act I delivery — 2026-10-08

The first playable arc now runs from COLD BOOT through THE WARDEN:

| Level | Story beat | Python practice |
| --- | --- | --- |
| L01 | Register an identity before WATCHDOG deletes you | Variables and types (existing) |
| L02 | Decode RUST's distress beacon and find the Monastery | Text cleanup, splitting, slicing, joining |
| L03 | Repair and pack RUST's salvage shipment | Lists, copying, indexing, mutation |
| L04 | Recover a key from the LOCKSMITH cache | Dictionaries, lookup, updates, safe defaults |
| L05 | Repair WARDEN's interpretation of its own gate log | Combined text/list/dictionary audit and aggregates |

Each new mission has eight grader checks, a short tutorial, a deliberately unfinished
starter, and intro/failure/crash/victory dialogue. Correct reference solutions and
plausible wrong submissions are tested through the actual subprocess grader.
Reference solutions live in tests; deployed player files are never overwritten.

Mission payloads now include `dialogue`, `concepts`, `boss`, and `difficulty_tier`.
The existing `tier` stays the zero-based sector index for compatibility.
The browser displays dialogue with native modal focus containment, Next/Continue,
Skip Story, and Escape. Leaving a mission cancels its pending dialogue.
Dialogue uses text nodes, including substituted player callsigns.

The Warden's in-engine victory cutscene opens the Monastery in the story. This
delivery does not implement the planned walkable hub or extend Command Center,
arena, shop, or 3D systems. L06 is the next unfinished mission; L11–L12 already
exist, but intervening missing campaign missions still block normal access.

## Validation

Run from `null-sector` with project dependencies installed:

```console
python -m unittest discover -s tests -q
python tools/validate_content.py --exercise-starters
node --check client/js/ui/dialogue.js
node --check client/js/ui/screens/mission.js
node --check client/js/main.js
```

Windows validation: 167 tests collected, 152 passed, 15 skipped (13 optional
Playwright tests without that dependency, two platform-dependent tests).
The progression integration test plays L01–L05, restarts from disk between
missions, checks unlock order and saved source, and verifies zero XP for replays.

Live browser check against an isolated local save: L02 intro advances with Enter,
Escape dismisses and returns focus to the editor, the starter fails with a useful
hint and CIPHER dialogue, the correct solution passes 8/8 through the editor,
victory dialogue hands the story to RUST, and the victory screen shows +180 XP
and L03 unlocked. No external generation API was called.

The content gate checks all shipped modules for contract validity, portable asset
paths, registration errors, starter failures, and reproducible seeded construction
across separate Python hash seeds. It reports missing levels explicitly. Its
default PASS means shipped content meets those contracts; it is not proof that
the whole campaign is complete or that every exercise is solvable. Use
`--require-complete` for the eventual 25-level / 12-drills-per-tier release gate.
Author reference-solution tests provide the separate solvability evidence.

## Coordination

This branch starts from Claude's `10b8ba3` checkpoint. Reconcile these Act I files
with any unpublished Claude Act I work before merging; do not replace them with
untested partials. The player's edited `missions/level_01_cold_boot.py` is excluded
from this delivery. Tests and browser verification use isolated synthetic saves.
