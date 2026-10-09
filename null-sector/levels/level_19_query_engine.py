"""LEVEL 19 // QUERY ENGINE — WHERE, ORDER BY, GROUP BY, aggregates and JOIN, from Python."""
from __future__ import annotations

import ast
import json
import sqlite3

from engine.mission import Fail, Mission

LEDGER_FILE = "archive_ledger.json"

LEDGER = {
    "operators": [
        {"key_id": "K-04", "handle": "ARCHIVIST", "clearance": 3},
        {"key_id": "K-11", "handle": "HYDRA-7", "clearance": 2},
        {"key_id": "K-23", "handle": "LIBRARIAN", "clearance": 6},
        {"key_id": "K-31", "handle": "WARDEN", "clearance": 1},
        {"key_id": "K-40", "handle": "FORGEMASTER", "clearance": 5},
        {"key_id": "K-7F3A", "handle": "[REDACTED]", "clearance": 9},
    ],
    "commands": [
        {"id": 1, "ts": 100, "key_id": "K-31", "command": "OPEN GATE", "sector": "MONASTERY", "status": "OK"},
        {"id": 2, "ts": 105, "key_id": "K-04", "command": "INDEX stack-12", "sector": "ARCHIVE", "status": "OK"},
        {"id": 3, "ts": 110, "key_id": "K-40", "command": "FORGE dataset-7", "sector": "FOUNDRY", "status": "OK"},
        {"id": 4, "ts": 120, "key_id": "K-11", "command": "RELAY burst-4471", "sector": "ARCHIVE", "status": "FAILED"},
        {"id": 5, "ts": 130, "key_id": "K-7F3A", "command": "DEPLOY LOOM-1.0.0", "sector": "CORE", "status": "OK"},
        {"id": 6, "ts": 140, "key_id": "K-23", "command": "SEAL project-loom", "sector": "ARCHIVE", "status": "OK"},
        {"id": 7, "ts": 150, "key_id": "K-04", "command": "INDEX stack-40", "sector": "ARCHIVE", "status": "FAILED"},
        {"id": 8, "ts": 160, "key_id": "K-40", "command": "FORGE dataset-9", "sector": "FOUNDRY", "status": "DENIED"},
        {"id": 9, "ts": 170, "key_id": "K-7F3A", "command": "EXECUTE NULL_EVENT", "sector": "CORE", "status": "OK"},
        {"id": 10, "ts": 175, "key_id": "K-11", "command": "PURGE ghost-mirrors", "sector": "ARCHIVE", "status": "OK"},
        {"id": 11, "ts": 180, "key_id": "K-31", "command": "SEAL GATE", "sector": "MONASTERY", "status": "FAILED"},
        {"id": 12, "ts": 185, "key_id": "K-11", "command": "PURGE operator-records", "sector": "ARCHIVE", "status": "OK"},
        {"id": 13, "ts": 190, "key_id": "K-99", "command": "RELAY unknown", "sector": "GRID", "status": "FAILED"},
        {"id": 14, "ts": 195, "key_id": "K-23", "command": "PURGE monastery-index", "sector": "ARCHIVE", "status": "DENIED"},
        {"id": 15, "ts": 200, "key_id": "K-04", "command": "INDEX stack-12", "sector": "ARCHIVE", "status": "OK"},
        {"id": 16, "ts": 205, "key_id": "K-11", "command": "RELAY burst-4472", "sector": "ARCHIVE", "status": "FAILED"},
    ],
}
LEDGER_JSON = json.dumps(LEDGER, indent=2) + "\n"

# Commands are stored out of time order and ids don't follow time, so a query that forgets ORDER BY shows it.
FRESH_LEDGER = {
    "operators": [
        {"key_id": "A-1", "handle": "NOVA", "clearance": 4},
        {"key_id": "B-2", "handle": "RUST", "clearance": 2},
        {"key_id": "C-3", "handle": "VEX", "clearance": 7},
    ],
    "commands": [
        {"id": 3, "ts": 50, "key_id": "B-2", "command": "SELL relay-chip", "sector": "UNDERCROFT", "status": "OK"},
        {"id": 9, "ts": 10, "key_id": "A-1", "command": "POST contract-1", "sector": "OPS", "status": "OK"},
        {"id": 4, "ts": 70, "key_id": "C-3", "command": "CHALLENGE arena", "sector": "ARENA", "status": "FAILED"},
        {"id": 8, "ts": 20, "key_id": "B-2", "command": "SELL hint-chip", "sector": "UNDERCROFT", "status": "FAILED"},
        {"id": 2, "ts": 60, "key_id": "A-1", "command": "POST contract-2", "sector": "OPS", "status": "OK"},
        {"id": 7, "ts": 30, "key_id": "C-3", "command": "CHALLENGE arena", "sector": "ARENA", "status": "OK"},
        {"id": 5, "ts": 40, "key_id": "Z-9", "command": "CHALLENGE arena", "sector": "ARENA", "status": "FAILED"},
        {"id": 10, "ts": 5, "key_id": "B-2", "command": "OPEN shop", "sector": "UNDERCROFT", "status": "OK"},
        {"id": 6, "ts": 80, "key_id": "A-1", "command": "POST contract-3", "sector": "OPS", "status": "PENDING"},
    ],
}
EMPTY_LEDGER = {"operators": [], "commands": []}

MISSION = Mission(
    id="L19",
    slug="level_19_query_engine",
    title="QUERY ENGINE",
    concept="SQL queries & aggregates",
    enemy="CENSOR.ice",
    xp=350,
    par_seconds=45 * 60,
    tier=4,
    concepts=("sql", "dicts"),
    enemy_art="""\
 ██████████████████
 █▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓█
 █ ▀▀▀▀ ▓▓▓▓ ▀▀▀▀ █
 █▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓█
 █ ▀▀ ▓▓▓▓▓▓▓ ▀▀▀ █
 ██████████████████""",
    briefing="""\
While HYDRA purged the mirrors, CIPHER copied something bigger: the Archive's **command
ledger**. Every order ever signed in the sector, with the key that signed it. It's in
`archive_ledger.json`, and the vault is ready to hold it.

Sixteen commands. Six operator keys. One of them gave the order that ended the world.

**CENSOR.ice** sits on the ledger and blacks out anything you scroll through by hand. It
can't redact a question, though. Ask the database exactly what you want, and SQL answers
before CENSOR can react.

**Interrogate the ledger: filter it, sort it, group it, join it, and find out whose key signed the Null Event.**
""",
    why="""\
Most of a data scientist's day is asking questions of tables. Which runs failed? How many
samples per label? Which prompts cost the most? SQL answers them inside the database, on
millions of rows, faster than any Python loop:

```python
rows = conn.execute('''
    SELECT model, COUNT(*), AVG(latency_ms)
    FROM calls
    WHERE status = ?
    GROUP BY model
    ORDER BY AVG(latency_ms) DESC
''', ("ok",)).fetchall()
```

`WHERE` filters, `GROUP BY` buckets, aggregates summarize, `ORDER BY` ranks, and `JOIN`
connects tables that share a key. Feature stores, eval dashboards and RAG metadata filters
are all built from these few clauses.
""",
    manual="""\
**1 · WHERE filters rows; AND / OR combine conditions.** Values still go in as `?`:

```python
conn.execute(
    "SELECT name FROM runs WHERE status = ? AND loss < ?", ("done", 0.5)
).fetchall()                         # [("r7",), ("r9",)]
```

Comparisons work as in Python: `=`, `!=`, `<`, `<=`, `>`, `>=` (SQL uses one `=`).

**2 · ORDER BY sorts; LIMIT keeps the first few.** `ASC` is low to high (the default),
`DESC` high to low. List several columns to break ties:

```python
"SELECT name, loss FROM runs ORDER BY loss ASC LIMIT 3"
"SELECT name FROM runs ORDER BY epochs DESC, name ASC"
```

Without `ORDER BY`, SQL promises *no* order at all. If order matters, ask for it.

**3 · Aggregates squash many rows into one value.** `COUNT(*)`, `SUM(col)`, `AVG(col)`,
`MIN(col)`, `MAX(col)`. On an empty table, `COUNT(*)` is 0 and the others are `NULL`, which
arrives in Python as `None`:

```python
total, best = conn.execute("SELECT COUNT(*), MIN(loss) FROM runs").fetchone()
```

**4 · GROUP BY runs the aggregate once per group.** Without it, `COUNT(*)` counts the whole
table and you get ONE row back. With it, you get one row per distinct value:

```python
conn.execute("SELECT status, COUNT(*) FROM runs GROUP BY status").fetchall()
# [("done", 4), ("failed", 2)]
dict(rows)        # a list of (key, value) pairs turns straight into a dict
```

You can sort by the aggregate too: give it a name with `AS` and use the name:
`SELECT owner, COUNT(*) AS n FROM runs GROUP BY owner ORDER BY n DESC`.

**5 · JOIN connects two tables through a shared key.** Each command stores a `key_id`; the
operators table maps `key_id` to a handle. `JOIN ... ON` pairs up the rows where they match.
Short aliases (`c`, `o`) keep it readable:

```python
conn.execute('''
    SELECT o.handle, c.command
    FROM commands AS c
    JOIN operators AS o ON o.key_id = c.key_id
    WHERE c.sector = ?
    ORDER BY c.ts
''', ("ARCHIVE",)).fetchall()
```

A plain `JOIN` keeps only rows that match on both sides: a command signed by a key that isn't
in `operators` simply doesn't appear.

**6 · Rows come back as tuples.** `fetchall()` is a list of tuples, `fetchone()` a single
tuple or `None`. A one-column result still gives tuples: `[("a",), ("b",)]`, so take `row[0]`.
""",
    starter='''
"""
==============================================================================
  LEVEL 19 // QUERY ENGINE                              TARGET: CENSOR.ice
==============================================================================
  The Archive's command ledger is in archive_ledger.json. build_archive()
  loads it into two tables (already written; read it, it's L18 in action):

    operators(key_id TEXT PRIMARY KEY, handle TEXT, clearance INTEGER)
    commands(id INTEGER PRIMARY KEY, ts INTEGER, key_id TEXT,
             command TEXT, sector TEXT, status TEXT)

  Answer every question with SQL. The grader runs your queries on OTHER
  ledgers it builds itself, so they must work on any data.
"""
import json
import sqlite3
from pathlib import Path


def build_archive(conn, ledger):
    conn.execute("CREATE TABLE operators (key_id TEXT PRIMARY KEY, handle TEXT, clearance INTEGER)")
    conn.execute("CREATE TABLE commands (id INTEGER PRIMARY KEY, ts INTEGER, key_id TEXT, "
                 "command TEXT, sector TEXT, status TEXT)")
    conn.executemany("INSERT INTO operators VALUES (?, ?, ?)",
                     [(o["key_id"], o["handle"], o["clearance"]) for o in ledger["operators"]])
    conn.executemany("INSERT INTO commands VALUES (?, ?, ?, ?, ?, ?)",
                     [(c["id"], c["ts"], c["key_id"], c["command"], c["sector"], c["status"])
                      for c in ledger["commands"]])
    conn.commit()


# -- OBJECTIVE 1 // WHERE + ORDER BY ------------------------------------------
# sector_log(conn, sector): the `command` text of every command in that
# sector, oldest first (by ts), as a list of strings.
#   sector_log(conn, "CORE")  ->  ["DEPLOY LOOM-1.0.0", "EXECUTE NULL_EVENT"]
def sector_log(conn, sector):
    pass  # replace with your code


# -- OBJECTIVE 2 // AND + DESC ------------------------------------------------
# failures(conn, since): the `id` of every command whose status is "FAILED"
# AND whose ts is at least `since`, newest first, as a list of ints.
#   failures(conn, 180)  ->  [16, 13, 11]
def failures(conn, since):
    pass  # replace with your code


# -- OBJECTIVE 3 // CORRUPTED CODE --------------------------------------------
# status_counts(conn) should return {status: number of commands}, like
#   {"OK": 9, "FAILED": 5, "DENIED": 2}
# CENSOR got to this query: it only ever returns ONE status. Fix the SQL.
def status_counts(conn):
    rows = conn.execute("SELECT status, COUNT(*) FROM commands").fetchall()
    return dict(rows)


# -- OBJECTIVE 4 // GROUP BY + ORDER BY + LIMIT --------------------------------
# top_signers(conn, limit): the `limit` keys that signed the most commands,
# as a list of (key_id, count) tuples: most commands first, and keys with
# the same count in A-Z order. Pass `limit` with a ? placeholder.
#   top_signers(conn, 3)  ->  [("K-11", 4), ("K-04", 3), ("K-23", 2)]
def top_signers(conn, limit):
    pass  # replace with your code


# -- OBJECTIVE 5 // JOIN ------------------------------------------------------
# signers_of(conn, command): who issued this exact command? Return a list of
# (handle, key_id) tuples, oldest first. JOIN commands to operators on key_id.
#   signers_of(conn, "SEAL project-loom")  ->  [("LIBRARIAN", "K-23")]
def signers_of(conn, command):
    pass  # replace with your code


# -- OBJECTIVE 6 // AGGREGATES ------------------------------------------------
# ledger_span(conn): ONE query with COUNT, MIN and MAX. Return
#   {"commands": how many, "first_ts": smallest ts, "last_ts": largest ts}
# An empty ledger gives {"commands": 0, "first_ts": None, "last_ts": None}.
def ledger_span(conn):
    pass  # replace with your code


# -- OBJECTIVE 7 -------------------------------------------------------------
# Interrogate the real ledger:
#   * `conn`: an in-memory database, sqlite3.connect(":memory:")
#   * `ledger`: json.loads the text of archive_ledger.json
#   * build_archive(conn, ledger)
#   * `null_signers`: signers_of(conn, "EXECUTE NULL_EVENT")
#   * `culprit_key`: the key_id from the first entry of null_signers
#   * print a line that includes culprit_key

''',
    assets={LEDGER_FILE: LEDGER_JSON},
    dialogue={
        "intro": [
            {"speaker": "cipher", "mood": "neutral",
             "text": "Sixteen commands, six keys. Scroll through it by hand and CENSOR blacks out every line you touch."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "So don't scroll. Ask. WHERE to filter, GROUP BY to count, JOIN to put names to keys."},
            {"speaker": "rust", "mood": "neutral",
             "text": "Somebody signed the Null Event. Keys don't lie. Find out whose."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "'no such column'? Check the spelling against the schema at the top of the file. SQL is picky too."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "'Incorrect number of bindings' means your ? marks and your values don't line up. One value needs (value,)."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "SQL threw a syntax error. Clauses go in order: SELECT, FROM, JOIN, WHERE, GROUP BY, ORDER BY, LIMIT."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader asks your queries about a different ledger, stored out of order. Without ORDER BY, the order is luck."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "One row back from a COUNT? Without GROUP BY, the whole table is one group."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "CENSOR's down to its last redaction layers, {callsign}. Keep the queries coming."}],
            [{"speaker": "vex", "mood": "smirk",
              "text": "GROUP BY, ORDER BY, give up by. You're close, {callsign}. Don't make me watch you lose to a spreadsheet."}],
        ],
        "victory": [
            {"speaker": "cipher", "mood": "alarm",
             "text": "EXECUTE NULL_EVENT. Status OK. Signed with key K-7F3A. Handle redacted. Clearance nine."},
            {"speaker": "rust", "mood": "cold",
             "text": "K-7F3A. Same hex the Forgemaster stamped on every shard. Same hex in your visor's boot sector. I can count, {callsign}."},
            {"speaker": "vex", "mood": "neutral",
             "text": "...Huh. No joke this time. Whoever signed that, the Arena would've named a division after them."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Someone redacted the handle but kept the key. The Librarian holds every card at the Archive's floor. It knows. I think I do too."},
        ],
    },
)


# ── reference behaviour ─────────────────────────────────────────────────────────

def _ref_build(ledger) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE operators (key_id TEXT PRIMARY KEY, handle TEXT, clearance INTEGER)")
    conn.execute("CREATE TABLE commands (id INTEGER PRIMARY KEY, ts INTEGER, key_id TEXT, "
                 "command TEXT, sector TEXT, status TEXT)")
    conn.executemany("INSERT INTO operators VALUES (?, ?, ?)",
                     [(o["key_id"], o["handle"], o["clearance"]) for o in ledger["operators"]])
    conn.executemany("INSERT INTO commands VALUES (?, ?, ?, ?, ?, ?)",
                     [(c["id"], c["ts"], c["key_id"], c["command"], c["sector"], c["status"])
                      for c in ledger["commands"]])
    return conn


def _ref_sector_log(conn, sector):
    return [r[0] for r in conn.execute("SELECT command FROM commands WHERE sector = ? ORDER BY ts", (sector,))]


def _ref_failures(conn, since):
    return [r[0] for r in conn.execute(
        "SELECT id FROM commands WHERE status = 'FAILED' AND ts >= ? ORDER BY ts DESC", (since,))]


def _ref_status_counts(conn):
    return dict(conn.execute("SELECT status, COUNT(*) FROM commands GROUP BY status").fetchall())


def _ref_top_signers(conn, limit):
    return conn.execute("SELECT key_id, COUNT(*) AS n FROM commands GROUP BY key_id "
                        "ORDER BY n DESC, key_id ASC LIMIT ?", (limit,)).fetchall()


def _ref_signers_of(conn, command):
    return conn.execute("SELECT o.handle, o.key_id FROM commands AS c JOIN operators AS o "
                        "ON o.key_id = c.key_id WHERE c.command = ? ORDER BY c.ts", (command,)).fetchall()


def _ref_span(conn):
    n, first, last = conn.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM commands").fetchone()
    return {"commands": n, "first_ts": first, "last_ts": last}


NULL_SIGNERS = _ref_signers_of(_ref_build(LEDGER), "EXECUTE NULL_EVENT")


# ── grader helpers ──────────────────────────────────────────────────────────────

def _short(value, limit: int = 140) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _defined(ctx, name: str):
    found = [n for n in ctx.tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return found[-1] if found else None


def _function(ctx, name: str, signature: str):
    if name not in ctx.ns:
        if ctx.crashed and _defined(ctx, name):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.", hint=f"Keep the starter's  def {signature}:  line.")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function anymore.", hint=f"Keep  def {signature}:")
    return fn


def _sql_of(ctx, name: str) -> str:
    """All the string literals inside the player's function, uppercased: its SQL."""
    node = _defined(ctx, name)
    if node is None:
        return ""
    parts = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return " ".join(" ".join(parts).upper().split())


def _require_sql(ctx, name: str, clauses: tuple[str, ...], why: str) -> None:
    sql = _sql_of(ctx, name)
    missing = [c for c in clauses if c not in sql]
    if missing:
        raise Fail(f"{name}() gets the right answer here, but not from SQL: no {', '.join(missing)} in its query. "
                   "CENSOR redacts answers computed in Python.", hint=why)


def _spliced(ctx) -> int | None:
    for n in ast.walk(ctx.tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("execute", "executemany")
                and n.args and (isinstance(n.args[0], ast.JoinedStr) and any(isinstance(v, ast.FormattedValue) for v in n.args[0].values)
                                or isinstance(n.args[0], ast.BinOp)
                                or isinstance(n.args[0], ast.Call) and isinstance(n.args[0].func, ast.Attribute)
                                and n.args[0].func.attr == "format")):
            return n.lineno
    return None


def _crash_hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, sqlite3.OperationalError) and "no such column" in msg:
        return "Check the column names against the schema in the starter's header comment."
    if isinstance(exc, sqlite3.OperationalError) and "syntax error" in msg:
        return "Clause order: SELECT … FROM … JOIN … ON … WHERE … GROUP BY … ORDER BY … LIMIT …"
    if isinstance(exc, sqlite3.ProgrammingError) and "bindings" in msg:
        return "One ? per value, and values in a tuple. A single value needs a comma: (sector,)"
    if isinstance(exc, (TypeError, IndexError)) and "NoneType" in msg:
        return "fetchone() returned None, or a function returned nothing. Print the rows to see what came back."
    return "Run the function on a small in-memory ledger at the bottom of your file and read the full error."


def _ask(ctx, name: str, signature: str, args: tuple, ledgers, reference, hint: str):
    fn = _function(ctx, name, signature)
    for label, ledger in ledgers:
        conn = _ref_build(ledger)
        shown = "".join(", " + repr(a) for a in args)
        try:
            got = fn(conn, *args)
        except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
            raise Fail(f"`{name}(conn{shown})` on the {label} crashed: {type(exc).__name__}: {exc}",
                       hint=_crash_hint(exc))
        expected = reference(conn, *args)
        if got != expected or type(got) is not type(expected):
            more = "Your function ended without `return`, so Python gave back None." if got is None else hint
            raise Fail(f"`{name}(conn{shown})` on the {label} returned {_short(got)}; expected {_short(expected)}.",
                       hint=more)


# ── firewall layers ─────────────────────────────────────────────────────────────

GRID = [("grader's own ledger", FRESH_LEDGER), ("Archive ledger", LEDGER)]


@MISSION.check("WHERE + ORDER BY — `sector_log(conn, sector)`")
def _sector_log(ctx):
    for sector in ("UNDERCROFT", "OPS", "ARCHIVE", "NOWHERE"):
        _ask(ctx, "sector_log", "sector_log(conn, sector)", (sector,), GRID, _ref_sector_log,
             "SELECT command … WHERE sector = ? ORDER BY ts, then take row[0] from each row.")
    _require_sql(ctx, "sector_log", ("WHERE", "ORDER BY"), "Let SQL filter and sort: WHERE sector = ? ORDER BY ts")


@MISSION.check("AND + DESC — `failures(conn, since)`")
def _failures(ctx):
    for since in (0, 40, 180, 999):
        _ask(ctx, "failures", "failures(conn, since)", (since,), GRID, _ref_failures,
             "Two conditions joined with AND (status and ts >= ?), newest first with ORDER BY ts DESC.")
    _require_sql(ctx, "failures", ("WHERE", "AND", "DESC"), "WHERE status = 'FAILED' AND ts >= ? ORDER BY ts DESC")


@MISSION.check("Repair the census — `status_counts(conn)` with GROUP BY")
def _status_counts(ctx):
    _ask(ctx, "status_counts", "status_counts(conn)", (), GRID + [("empty ledger", EMPTY_LEDGER)],
         _ref_status_counts,
         "Without GROUP BY, COUNT(*) treats the whole table as one group. Add GROUP BY status.")
    _require_sql(ctx, "status_counts", ("GROUP BY",), "SELECT status, COUNT(*) FROM commands GROUP BY status")


@MISSION.check("Rank the signers — `top_signers(conn, limit)`")
def _top_signers(ctx):
    for limit in (1, 2, 3, 10):
        _ask(ctx, "top_signers", "top_signers(conn, limit)", (limit,), GRID, _ref_top_signers,
             "GROUP BY key_id, name the count (COUNT(*) AS n), ORDER BY n DESC, key_id ASC, then LIMIT ?.")
    _require_sql(ctx, "top_signers", ("GROUP BY", "ORDER BY", "LIMIT"),
                 "One query: GROUP BY key_id … ORDER BY … LIMIT ?")


@MISSION.check("JOIN the keys — `signers_of(conn, command)`")
def _signers_of(ctx):
    for command in ("CHALLENGE arena", "POST contract-2", "SEAL project-loom", "RELAY unknown", "NO SUCH ORDER"):
        _ask(ctx, "signers_of", "signers_of(conn, command)", (command,), GRID, _ref_signers_of,
             "JOIN operators AS o ON o.key_id = c.key_id, select o.handle and o.key_id, WHERE c.command = ?, "
             "ORDER BY c.ts. Keys missing from operators drop out of a JOIN.")
    _require_sql(ctx, "signers_of", ("JOIN", " ON "), "commands JOIN operators ON the shared key_id column")


@MISSION.check("Measure the ledger — `ledger_span(conn)` aggregates")
def _span(ctx):
    _ask(ctx, "ledger_span", "ledger_span(conn)", (), GRID + [("empty ledger", EMPTY_LEDGER)], _ref_span,
         "SELECT COUNT(*), MIN(ts), MAX(ts) FROM commands, then fetchone() and build the dict. "
         "On an empty table MIN and MAX are NULL, which Python gets as None.")
    _require_sql(ctx, "ledger_span", ("COUNT(", "MIN(", "MAX("), "One SELECT with COUNT(*), MIN(ts) and MAX(ts).")


@MISSION.check("Interrogate the Archive — who signed the Null Event?")
def _null_event(ctx):
    line = _spliced(ctx)
    if line:
        raise Fail(f"Line {line} builds SQL text from values. CENSOR can rewrite a spliced query.",
                   hint="Keep SQL as plain strings with ? marks; pass values as a tuple.")
    ledger = ctx.get("ledger")
    if ledger != LEDGER or not ctx.derived_from("ledger", "json"):
        raise Fail("`ledger` must be json.loads of archive_ledger.json.",
                   hint='ledger = json.loads(Path("archive_ledger.json").read_text(encoding="utf-8"))')
    signers = ctx.get("null_signers")
    if not (ctx.derived_from("null_signers", "signers_of") and ctx.derived_from("null_signers", "conn")):
        raise Fail("`null_signers` must come from asking the database: signers_of(conn, ...).",
                   hint='null_signers = signers_of(conn, "EXECUTE NULL_EVENT")')
    if signers != NULL_SIGNERS:
        raise Fail(f"`null_signers` is {_short(signers)}. Ask for the exact command text \"EXECUTE NULL_EVENT\".")
    culprit = ctx.get("culprit_key")
    if not ctx.derived_from("culprit_key", "null_signers"):
        raise Fail("`culprit_key` was typed in. Read it out of null_signers.",
                   hint="The first entry is a (handle, key_id) tuple: null_signers[0][1]")
    if culprit != NULL_SIGNERS[0][1]:
        raise Fail(f"`culprit_key` is {_short(culprit)}; take the key_id, the second item of the first tuple.")
    if not ctx.call_uses("print", "culprit_key") or culprit not in ctx.stdout:
        raise Fail("You found it. Now say it out loud.", hint='print(f"NULL EVENT SIGNED BY: {culprit_key}")')
