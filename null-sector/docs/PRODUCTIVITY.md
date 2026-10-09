# Productivity command center

The SQLite backend is integrated into the existing NULL//SECTOR game. The source
checkout was obtained from `panopt-c/panoptics-roadmap`, branch
`claude/keen-mayer-xso05z`, at `0134663`. Integration changes are local to this
checkout; they have not been pushed to Claude's cloud environment. Claude's
browser command center commit `5f9e7cc` has been merged locally and tested against
this backend.

## Launch

From `null-sector` in PowerShell on this computer:

```powershell
.\run.ps1
```

In the browser hub, choose **Command center** or press **O**. Study, workout and
weight forms save to SQLite, and the dashboard updates through the local event
stream. The six-hour math target and 170 lb weight target work in both frontends.

For the terminal command center:

```powershell
.\run.ps1 productivity
```

Or use `python game.py tui` and select **P — PRODUCTIVITY** from the existing
Rich terminal menu. With dependencies installed, `python game.py productivity`
opens the command center directly. The PowerShell launcher uses the local project
virtual environment if present, then the workspace virtual environment prepared
during integration, then Python on PATH.

The tracker itself uses only the standard library. The existing game uses Rich,
markdown-it-py and Pygments. Higgsfield is optional; no credentials or external
generation requests were used to build or test this integration.

For JSON output or detailed exercise metrics:

```powershell
python productivity.py dashboard
python productivity.py study --course "Algebra 2" --minutes 90 --topic "Quadratics" --request-id block-001
python productivity.py workout --activity Squats --minutes 45 --sets 3 --reps 8 --load-lbs 95 --request-id workout-001
python productivity.py weight --lbs 190 --request-id weigh-in-001
python productivity.py rewards
```

These are manual logs of completed activities. No timer or background monitor is
running. The daily math objective is 360 minutes, covering Algebra 2,
Trigonometry, Precalculus, Calculus 1–3 and Linear Algebra. The default weight
target is 170 lbs; a first measurement establishes progress direction.

## State and XP

`data/productivity.sqlite3` holds the tracker player, XP ledger, inventory,
activity history, study sessions, workout/weight logs, habits, milestones and
cinematic jobs. The schema version is recorded with `PRAGMA user_version`.
Foreign keys and transactional writes protect logs and XP; WAL and a busy timeout
allow multiple local connections. The database and generated data are Git-ignored.

The existing `save.json` remains authoritative for campaign XP, mission clears,
attempts and rank. SQLite is authoritative for productivity XP. The command center
reports `game.campaign_xp`, `game.productivity_xp` and their derived `game.total_xp`.
Productivity XP does not unlock coding missions or change the campaign rank.
The game's existing `/api/state` response stays compatible with its browser UI.
Neither XP amount is copied into the other store. CLI `--player` can select extra
tracker profiles; the game uses the stable default `Netrunner` tracker profile.

Study awards 1 XP/minute plus 100 XP once per completed daily goal. Workouts award
2 XP/minute, plus 50 XP for the first workout. Crossing the weight target from the
baseline direction awards 250 XP once. Weight measurements otherwise award no XP.
These are game rules. Missing measurements remain unknown, and no real user logs
are seeded by tests.

Weight goal direction is fixed by the first measurement ever logged (insertion
order) compared with the target: above it means *lose*, below it means *gain*.
Backfilling older weigh-ins never flips it. The baseline is the earliest-dated
measurement on the starting side of the target, and only measurements dated on or
after the baseline can reach the goal, so logging old history can never award the
goal by itself. `weight_history` is chronological (date, then insertion).

Armory: milestones drop items. A completed daily math objective drops a Focus Chip,
3/7/30-day study streaks drop an Overclock Module, Neural Lattice and Core Key, the
first workout drops Training Wraps, the weight goal drops a Target Lock, and every
cleared coding mission drops a Breach Shard. Each milestone drops exactly once
(recorded in `item_grants`, schema version 2), including milestones from before
items existed. Inventory rows carry `metadata` with `name`, `rarity`, `icon` and
`description`. Activity writes report new drops in `items_granted`.

Field limits (one table, `tracker.LIMITS`, also sent as `snapshot.limits`):
`minutes` 1–1440 (and at most 1440 per kind per day), `sets` 1–1000, `reps`
1–10000, `load_lbs` 0–2000, `distance_miles` 0–500, `weight_lbs` 50–800. Optional
fields are omitted or `null` when not measured; **0 sets or reps is rejected**
(400 "… leave it empty if you did not count it"), so forms send nothing instead.
Free text (`activity`, `topic`, `note`, `habit_key`, `request_id`) that holds a lone
UTF-16 surrogate is rejected with a 400; the CLI repairs non-UTF-8 argv bytes to
U+FFFD. Version-1 databases holding such text are repaired on open.

Reuse the same nonempty `request_id`, date and payload when retrying a submission.
It returns the original activity without another award. Reusing an ID with a
different payload is an error. When no ID is supplied, the call creates a new log.
A retry that omits `on_date` matches the day the original was filed under, so a
retry that lands after midnight still returns the original (clients should still
send `on_date`, resolved once at first submit).
Historical `on_date` values use `YYYY-MM-DD`. Defaults use the computer's local
calendar date, and audit timestamps use UTC. Today is always accepted; future
dates are rejected. Split cross-midnight blocks by day.
Current streaks count yesterday until today's objective is met.

## API and direct integration

All routes retain the existing loopback binding, Host check, request size limit
and `X-NS-Token` authentication. No token may be supplied in the query string for
these routes.

| Route | Result |
| --- | --- |
| `GET /api/productivity` | Today's tracker snapshot plus XP breakdown (recent milestones and reward payloads only) |
| `POST /api/productivity/study` | `course`, `minutes`, optional `topic`, `on_date`, `request_id` |
| `POST /api/productivity/workout` | `activity`, `minutes`, optional `sets`, `reps`, `load_lbs`, `distance_miles`, `note`, `on_date`, `request_id` |
| `POST /api/productivity/weight` | `weight_lbs`, optional `on_date`, `request_id` |
| `POST /api/productivity/habit` | `habit_key`, `value`, optional `note`, `on_date` |
| `GET /api/productivity/rewards` | Every persistent cinematic JSON payload, oldest first |

Activity writes return `{activity, snapshot, items_granted}` and publish a
`productivity` event on the existing event stream. The returned snapshot is always
for **today** (the real local date): `on_date` only chooses which day an entry is
filed under, never which day the dashboard shows. Habit writes replace a daily
value and return a null activity (a `request_id` is accepted and ignored).

Snapshots stay small: `milestones` holds the newest 20 (newest first) and
`milestone_counts` the totals per category (`study`, `fitness`, `coding`, `total`);
`cinematic_jobs` holds the newest 20 payloads (newest first) and
`cinematic_job_count` the total. The full history is `GET /api/productivity/rewards`.

Invalid payloads return HTTP 400 with a plain message: unknown fields
(`unknown field for study: extra`), missing fields (`missing required field for
study: minutes`), out-of-range values, or a body that is not valid JSON. A busy or
unreadable database returns 503 (retryable); the campaign API stays responsive
meanwhile because SQLite work never holds the game session's lock. The direct Python API is
`GameSession.productivity_snapshot()` and `GameSession.log_productivity(command,
payload)`. Both HTTP and Rich TUI handlers call these same methods.

The integrated browser and Rich terminal command centers both consume this
contract. Browser inventory reads `item_key` and optional metadata; protocols
show stored numeric habit values; reward cards label local payloads as ready for
export. Weight progress handles both gain and loss from the logged baseline.

## Cinematic payloads

The router durably queues one `neon.cinematic.v1` JSON envelope per milestone.
Opening the game's command center or reading its rewards reconciles coding
milestones from saved mission clears, without awarding campaign XP again.
This also recovers pending coding rewards after a process restart.

The envelopes contain a request ID, milestone category and cinematic generation
parameters. They omit private notes and weight measurements. They are an internal
provider-neutral format, not a claimed Higgsfield API schema. They are not sent
automatically. The game's existing Higgsfield mission renderer remains intact;
delivery of new productivity rewards needs a configured provider adapter.

## Validation

```powershell
python -m unittest discover -s tests -v
```

Tests use temporary directories, not player saves. New tests cover rollback,
restarts, concurrent retries, input validation, six-hour completion, study streaks,
fitness metrics, inventory, cinematic deduplication, authenticated HTTP routes,
event delivery and interaction with the existing Rich TUI.

The original HTTP test fixtures now preserve LF bytes on Windows. Path traversal
checks always run; a separate symlink check skips only if Windows denies symlink
creation. The POSIX subprocess SIGINT test skips on Windows, where Python does
not support that delivery method; the server-close tests still run.
