# Local validation — 2026-10-07

Environment: Windows, Python 3.12.14, workspace virtual environment.
Base game revision: `0134663`, branch `claude/keen-mayer-xso05z`.
Browser command center: Claude commit `5f9e7cc`, merged locally, followed by
local corrections for actual backend field names and weight-gain progress.

Full integrated suite:

```text
python -m unittest discover -s tests -v
Ran 116 tests in 100.557s
OK (skipped=2)
```

114 passed. The two skipped checks require POSIX subprocess SIGINT delivery or
Windows symlink-creation privileges. Other shutdown and path-traversal checks
ran and passed. The new tracker/API/TUI cases were not skipped.

Coverage includes 26 SQLite/tracker/cinematic tests, 7 integration tests,
10 adversarial and recovery tests, and
the original game suite with a separate symlink traversal test. The integration
tests exercise authenticated local HTTP writes, event delivery, persistent
restart state, retry deduplication, preserving the campaign save and the actual
Rich command center input/render loop. Edge cases include oversized JSON numbers,
the earliest supported calendar date, backdated weight-goal crossings, conflicting
retry IDs and recovery after a cinematic queue interruption.

Additional checks: all new Python modules compiled, `git diff --check` passed,
the PowerShell launcher displayed game help, and the integrated tracker CLI
printed a fresh in-memory dashboard without external dependencies.

All activity samples were synthetic and stored in memory or temporary test
directories. No real study/fitness logs were inserted, no mission save was
migrated, and no paid media generation requests were sent.

The real browser Level 1 flow was also exercised using an isolated save: boot,
mission deployment, editor submission, successful evaluation, 150 campaign XP,
rank-up, the in-engine transmission and return to the hub. The existing Level 2
entry is still encrypted/unimplemented; this is not a full-campaign validation.

Real-server browser integration checks passed using a separate synthetic profile:

- Study: 360 minutes saved, goal completed, 460 productivity XP.
- Workout: 45 minutes, 3 sets, 8 reps, 95 lb load saved, 140 productivity XP.
- Weight: 150 to 160 lb showed 50% progress and 10 lb remaining; reaching 170 lb
  awarded 250 XP and created one persistent reward payload.
- Campaign XP stayed at 150; final productivity XP was 850, combined XP 1,000.
- Reload preserved logs; the hub summary matched the dashboard.
- A separate authenticated HTTP habit write appeared in the open dashboard
  through SSE without a reload. No browser console warnings or errors appeared.
- Layout inspected at actual viewport sizes 1056x900 and 390x844; narrow-screen
  document width matched the viewport, and the weight form was usable.

Claude reported 13 mocked browser tests passing on his Chromium environment.
Those optional Playwright tests were not rerun on this Windows environment;
the checks above used the actual local server through the available browser tool.

The original hidden LINK LOST banner remained in the accessibility tree because
it used opacity alone. Claude's merged visibility/aria-hidden fix removed that
false warning; actual event delivery was verified as described above.
