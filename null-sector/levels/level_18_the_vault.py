"""LEVEL 18 // THE VAULT — sqlite3: connect, CREATE TABLE, parameterized INSERT, SELECT."""
from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path

from engine.mission import Fail, Mission

EVIDENCE_FILE = "evidence.json"
VAULT_FILE = "vault.db"
COLUMNS = ["id", "ref", "kind", "author", "note", "verified"]

EVIDENCE = [
    {"ref": "PK-305", "kind": "packet", "author": "ORACLE", "note": "PURGE operator-records"},
    {"ref": "PK-302", "kind": "packet", "author": "ORACLE", "note": "PURGE monastery-index"},
    {"ref": "PK-304", "kind": "packet", "author": "ORACLE", "note": "SEAL project-loom"},
    {"ref": "LOOM-0.9.1", "kind": "build", "author": "i.vance",
     "note": "Human-feedback brake: pause the loop when raters disagree"},
    {"ref": "LOOM-0.9.2", "kind": "build", "author": "operator-0", "note": "Reward model wired into the loss"},
    {"ref": "LOOM-1.0.0", "kind": "build", "author": "operator-0", "note": "Brake removed for the long run"},
    {"ref": "NOTE-VANCE", "kind": "comment", "author": "i.vance",
     "note": "I'm not signing 1.0. Someone has to be able to stop it."},
    {"ref": "NOTE-OP0", "kind": "comment", "author": "operator-0",
     "note": "if the loop keeps asking for more data, let it take it."},
    {"ref": "LOOM-1.0.0", "kind": "build", "author": "operator-0", "note": "Brake removed for the long run (mirror echo)"},
    {"ref": "TESTIMONY-01", "kind": "testimony", "author": "Sister Ines O'Hara",
     "note": "The Order's archivist saw the loop's brake pulled the night before the Null Event."},
]
EVIDENCE_JSON = json.dumps(EVIDENCE, indent=2) + "\n"
UNIQUE_REFS = sorted({r["ref"] for r in EVIDENCE})

MISSION = Mission(
    id="L18",
    slug="level_18_the_vault",
    title="THE VAULT",
    concept="SQLite: tables & inserts",
    enemy="TUMBLER.sys",
    xp=330,
    par_seconds=40 * 60,
    tier=4,
    concepts=("sql", "exceptions"),
    enemy_art="""\
   ▄██████████▄
  ██▀▀▀▀▀▀▀▀▀▀██
  ██  ▄████▄  ██
  ██  ██▀▀██  ██
  ██  ▀████▀  ██
  ██▄▄▄▄▄▄▄▄▄▄██
   ▀██████████▀""",
    briefing="""\
Evidence doesn't survive long in the Archive. HYDRA's purge is already eating the ghost mirrors,
and a dossier in your visor's memory is one crash away from gone.

Under the Monastery's Scriptorium is **the vault**: a single SQLite file the Order has kept for
forty years. It never forgets, and it never lets in a record it can't read cleanly.

**TUMBLER.sys** guards the intake. Feed it a query with your data pasted into the SQL text and
the first stray apostrophe jams the lock. The Order lost a whole archive that way once.

**Build the evidence table, store every record safely, and seal the vault before the purge reaches the Monastery.**
""",
    why="""\
Data that matters goes in a **database**, not a loose file. SQLite is a full SQL database in one
file, built into Python, and it runs on every phone on Earth. AI teams use it to log
experiments, cache model answers and store labelled data:

```python
import sqlite3

conn = sqlite3.connect("runs.db")
conn.execute("CREATE TABLE IF NOT EXISTS runs (name TEXT, loss REAL)")
conn.execute("INSERT INTO runs (name, loss) VALUES (?, ?)", ("baseline", 0.42))
conn.commit()
```

The `?` placeholders are the professional habit that matters most. Values travel separately from
the SQL, so text like `O'Hara` is stored safely instead of breaking the query. Building SQL with
f-strings is the root of **SQL injection**, one of the most common security bugs in real
software. Every serious codebase bans it.
""",
    manual="""\
**1 · Connect.** A connection is your line to one database file. `":memory:"` makes a
throwaway database that lives only in RAM:

```python
import sqlite3
conn = sqlite3.connect("crew.db")      # creates the file if it doesn't exist
```

**2 · CREATE TABLE.** A table is a grid: named, typed columns, and one row per record.
`INTEGER PRIMARY KEY` gives each row an automatic id. `UNIQUE` refuses duplicates, and
`NOT NULL` refuses missing values. `DEFAULT 0` fills a column you leave out:

```python
conn.execute(
    "CREATE TABLE IF NOT EXISTS crew ("
    " id       INTEGER PRIMARY KEY,"
    " callsign TEXT NOT NULL UNIQUE,"
    " role     TEXT,"
    " active   INTEGER NOT NULL DEFAULT 0)"
)
```

Python glues the adjacent strings into one. `IF NOT EXISTS` makes it safe to run twice.

**3 · INSERT with `?` placeholders. Always.** Write one `?` for each value, then pass the
values as a tuple. The database receives them separately, so quotes inside the data are just
characters:

```python
cur = conn.execute("INSERT INTO crew (callsign, role) VALUES (?, ?)", ("O'Hara", "archivist"))
cur.lastrowid      # the id SQLite gave the new row
```

Never paste values into the SQL text yourself:

```python
name = "O'Hara"
conn.execute(f"INSERT INTO crew (callsign) VALUES ('{name}')")   # crashes: syntax error
```

The apostrophe in `O'Hara` closes the SQL string early, so the rest of the query is garbage.
That's the harmless case. When data can change the *shape* of a query, an attacker can craft
values that make the query do something else entirely: that's **SQL injection**. Placeholders
make it impossible, because values are never read as SQL.

**4 · Duplicates raise `sqlite3.IntegrityError`.** Catch it (L14) to skip a duplicate:

```python
try:
    conn.execute("INSERT INTO crew (callsign) VALUES (?)", ("Kite",))
except sqlite3.IntegrityError:
    print("already on the roster")
```

**5 · Save with `commit()`.** Inserts sit in a pending *transaction* until you commit. If you
don't, other connections (and the next run) see nothing, and the work is lost when the
program ends:

```python
conn.commit()
```

**6 · SELECT reads rows back as tuples.** `WHERE column = ?` picks matching rows, with a
placeholder again. `fetchone()` gives one tuple or `None`; `fetchall()` gives a list of tuples:

```python
row = conn.execute("SELECT callsign, role FROM crew WHERE callsign = ?", ("Kite",)).fetchone()
# ("Kite", "scout") or None
names = [r[0] for r in conn.execute("SELECT callsign FROM crew").fetchall()]
```

A one-value tuple needs a trailing comma: `("Kite",)`. Without it, `("Kite")` is just a string.
""",
    starter='''
"""
==============================================================================
  LEVEL 18 // THE VAULT                                TARGET: TUMBLER.sys
==============================================================================
  The evidence from the stream and the ghost page is in evidence.json, next
  to this file. Store it in the Monastery vault: vault.db, a SQLite file.
  The grader also opens its OWN empty databases and calls your functions
  with fresh records, so they must work on any connection, not just yours.
"""
import json
import sqlite3
from pathlib import Path


# -- OBJECTIVE 1 -------------------------------------------------------------
# Finish create_vault(conn): create the table `evidence` (if it doesn't exist
# yet) with exactly these columns, in this order:
#   id        INTEGER PRIMARY KEY
#   ref       TEXT, NOT NULL and UNIQUE    (every record's reference code)
#   kind      TEXT, NOT NULL
#   author    TEXT
#   note      TEXT
#   verified  INTEGER, NOT NULL, DEFAULT 0
#                         example (manual, section 2):  CREATE TABLE IF NOT EXISTS crew (...)
def create_vault(conn):
    pass  # replace with your code


# -- OBJECTIVE 2 // CORRUPTED CODE --------------------------------------------
# store(conn, record) should insert ONE record dict (keys: ref, kind, author,
# note) and return the new row's id. New evidence always starts unverified (0).
# The old intake code pastes values straight into the SQL text, and it jams
# on the first apostrophe ("O'Hara", "I'm not signing"). Rewrite the INSERT
# with ? placeholders and pass the values as a tuple.
def store(conn, record):
    sql = f"INSERT INTO evidence (ref, kind, author, note, verified) VALUES ('{record['ref']}', '{record['kind']}', '{record['author']}', '{record['note']}', 0)"
    cursor = conn.execute(sql)
    return cursor.lastrowid


# -- OBJECTIVE 3 -------------------------------------------------------------
# Finish store_all(conn, records): store() every record in order. A ref
# that's already in the vault raises sqlite3.IntegrityError: catch it and
# skip that record. Commit at the end, then return how many records were
# actually stored.
#   store_all(conn, [rec_a, rec_b, rec_a_again])  ->  2
def store_all(conn, records):
    pass  # replace with your code


# -- OBJECTIVE 4 -------------------------------------------------------------
# Finish fetch(conn, ref): look up ONE record by its ref (WHERE ref = ?) and
# return it as a dict with keys "ref", "kind", "author", "note", "verified",
# or None if the vault has no such ref.
#   fetch(conn, "PK-305") -> {"ref": "PK-305", "kind": "packet",
#                             "author": "ORACLE", "note": "...", "verified": 0}
def fetch(conn, ref):
    pass  # replace with your code


# -- OBJECTIVE 5 -------------------------------------------------------------
# Finish all_refs(conn): return every ref in the vault as a list, sorted A to Z.
#   all_refs(empty_vault_conn)  ->  []
def all_refs(conn):
    pass  # replace with your code


# -- OBJECTIVE 6 -------------------------------------------------------------
# Seal the vault. The first two lines are given: they open vault.db and clear
# out any table a buggy earlier run left behind, so every hack starts clean.
conn = sqlite3.connect("vault.db")
conn.execute("DROP TABLE IF EXISTS evidence")
# Now:
#   * call create_vault(conn)
#   * `records`: json.loads the text of evidence.json
#   * `stored`:  store_all(conn, records)
#   * print a line that includes `stored`, e.g.  VAULT SEALED: 9 records

''',
    assets={EVIDENCE_FILE: EVIDENCE_JSON},
    dialogue={
        "intro": [
            {"speaker": "rust", "mood": "neutral",
             "text": "The Order's vault. One SQLite file, forty years old, never lost a byte. Don't be the first."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "A table, a schema, rows. And one rule TUMBLER enforces: values travel beside the SQL, never inside it."},
            {"speaker": "cipher", "mood": "alarm",
             "text": "The old intake code pastes data into its queries. The first apostrophe in the evidence will jam it."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "alarm",
              "text": "'syntax error' from SQLite? A quote in the data closed your SQL string early. That's what ? placeholders prevent."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "'no such table' means the INSERT ran before CREATE TABLE. Check the order of your calls."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "IntegrityError. The vault refused a duplicate. That's it doing its job. Catch it and move on."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Rows only count once they're committed. Without conn.commit(), nothing reaches the file."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader opens its own empty vaults. Your functions get a connection; don't open a new one inside them."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "TUMBLER's three pins down, {callsign}. Purge is still inbound. Keep it moving."}],
            [{"speaker": "vex", "mood": "smirk",
              "text": "A database. Wow. I keep my secrets in my head, {callsign}. Faster lookups."}],
        ],
        "victory": [
            {"speaker": "rust", "mood": "warm",
             "text": "Nine records, one echo refused, every apostrophe intact. The vault likes you. That's rare."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "The Archive's command ledger is next. If the vault can hold our evidence, it can hold theirs."},
            {"speaker": "nova", "mood": "smirk",
             "text": "HYDRA's purge hit the ghost mirrors two minutes after you sealed it, {callsign}. Two minutes. Nice."},
        ],
    },
)


# ── reference behaviour ─────────────────────────────────────────────────────────

_REF_SCHEMA = """
    CREATE TABLE IF NOT EXISTS evidence (
        id INTEGER PRIMARY KEY,
        ref TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL,
        author TEXT,
        note TEXT,
        verified INTEGER NOT NULL DEFAULT 0
    )"""

FRESH = [
    {"ref": "RUST-LEDGER", "kind": "receipt", "author": "RUST", "note": "Paid in full. Don't ask."},
    {"ref": "VEX-CLIP", "kind": "recording", "author": "VEX", "note": "\"Faster than you,\" she said. It's on tape."},
    {"ref": "ORDER-0'1", "kind": "scroll", "author": "Brother D'Souza", "note": "Copied by hand; the scribe's 41st."},
    {"ref": "NOVA-LOG", "kind": "ops", "author": None, "note": "Streak: 12 days"},
]


def _ref_vault() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(_REF_SCHEMA)
    return conn


def _rows(conn) -> list[tuple]:
    return conn.execute("SELECT ref, kind, author, note, verified FROM evidence ORDER BY id").fetchall()


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


def _crash_hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, sqlite3.OperationalError) and "syntax error" in msg:
        return ("A quote in the data broke the SQL text. Write ? for each value and pass the values "
                "as a tuple: conn.execute(sql, (a, b, c)).")
    if isinstance(exc, sqlite3.OperationalError) and "no such table" in msg:
        return "The table doesn't exist on this connection yet. Did create_vault run CREATE TABLE?"
    if isinstance(exc, sqlite3.ProgrammingError) and "bindings" in msg:
        return "The number of ? marks must match the number of values. One value? Write a tuple: (ref,)"
    if isinstance(exc, sqlite3.IntegrityError):
        return "A duplicate ref raised IntegrityError. store_all should catch it and skip that record."
    if isinstance(exc, KeyError):
        return "Read the record's fields by name: record[\"ref\"], record[\"kind\"], ..."
    return "Run the function on a  sqlite3.connect(\":memory:\")  connection at the bottom of your file."


def _call(label: str, fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}", hint=_crash_hint(exc))


def _no_return_hint(got) -> str:
    return "Your function ended without `return`, so Python gave back None." if got is None else ""


def _built_sql(node: ast.AST, built: set[str]) -> bool:
    """An f-string, + / % concatenation, or .format(...) call, or a name assigned from one."""
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        return True
    return isinstance(node, ast.Name) and node.id in built


def _spliced_queries(tree: ast.AST) -> list[int]:
    """Line numbers of execute()/executemany() calls whose SQL text is built from values."""
    lines = []
    for scope in [tree] + [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        built: set[str] = set()
        for n in ast.walk(scope):
            if isinstance(n, ast.Assign) and _built_sql(n.value, set()):
                built |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        for n in ast.walk(scope):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("execute", "executemany") and n.args
                    and _built_sql(n.args[0], built)):
                lines.append(n.lineno)
    return sorted(set(lines))


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Build the vault — `create_vault(conn)` schema")
def _schema(ctx):
    fn = _function(ctx, "create_vault", "create_vault(conn)")
    conn = sqlite3.connect(":memory:")
    _call("create_vault(conn)", fn, conn)
    columns = conn.execute("PRAGMA table_info(evidence)").fetchall()
    if not columns:
        raise Fail("After create_vault(conn) there's no `evidence` table on that connection.",
                   hint="conn.execute(\"CREATE TABLE IF NOT EXISTS evidence (...)\") on the conn you were given.")
    names = [c[1] for c in columns]
    if names != COLUMNS:
        raise Fail(f"The evidence table has columns {names}; it needs {COLUMNS}, in that order.")
    info = {c[1]: c for c in columns}   # (cid, name, type, notnull, default, pk)
    for col, kind in (("id", "INTEGER"), ("ref", "TEXT"), ("kind", "TEXT"), ("verified", "INTEGER")):
        if info[col][2].upper() != kind:
            raise Fail(f"Column `{col}` is typed {info[col][2] or 'nothing'}; it should be {kind}.")
    if info["id"][5] != 1:
        raise Fail("`id` isn't the primary key.", hint="id INTEGER PRIMARY KEY")
    _call("create_vault(conn) a second time", fn, conn)   # IF NOT EXISTS
    conn.execute("INSERT INTO evidence (ref, kind) VALUES (?, ?)", ("X-1", "test"))
    verified = conn.execute("SELECT verified FROM evidence WHERE ref = ?", ("X-1",)).fetchone()[0]
    if verified != 0:
        raise Fail(f"A row inserted without `verified` got {verified!r}; it should default to 0.",
                   hint="verified INTEGER NOT NULL DEFAULT 0")
    try:
        conn.execute("INSERT INTO evidence (ref, kind) VALUES (?, ?)", ("X-1", "test"))
    except sqlite3.IntegrityError:
        pass
    else:
        raise Fail("The vault accepted two records with the same ref.", hint="ref TEXT NOT NULL UNIQUE")
    try:
        conn.execute("INSERT INTO evidence (ref) VALUES (?)", ("X-2",))
    except sqlite3.IntegrityError:
        pass
    else:
        raise Fail("The vault accepted a record with no kind.", hint="kind TEXT NOT NULL")


@MISSION.check("Repair the intake — `store(conn, record)` with placeholders")
def _store(ctx):
    fn = _function(ctx, "store", "store(conn, record)")
    conn = _ref_vault()
    for i, record in enumerate(FRESH, start=1):
        new_id = _call(f"store(conn, {record['ref']!r} record)", fn, conn, dict(record))
        row = conn.execute("SELECT id, ref, kind, author, note, verified FROM evidence WHERE ref = ?",
                           (record["ref"],)).fetchone()
        if row is None:
            raise Fail(f"store() ran, but no row with ref {record['ref']!r} reached the table.",
                       hint="Execute the INSERT on the `conn` you were given.")
        expected = (record["ref"], record["kind"], record["author"], record["note"], 0)
        if row[1:] != expected:
            raise Fail(f"store() saved {_short(row[1:])}; expected exactly {_short(expected)}.",
                       hint="Pass the four values in column order and leave verified at 0.")
        if new_id != row[0]:
            raise Fail(f"store() returned {new_id!r}, but the new row's id is {row[0]}.",
                       hint=_no_return_hint(new_id) or "Return cursor.lastrowid from the execute() call.")
    spliced = _spliced_queries(_defined(ctx, "store") or ast.Module(body=[], type_ignores=[]))
    if spliced:
        raise Fail(f"store() still builds its SQL text out of values (line {spliced[0]}). TUMBLER rejects spliced queries.",
                   hint="Keep the SQL a plain string with ? marks and pass values as the second argument.")


@MISSION.check("Refuse the echoes — `store_all(conn, records)` skips duplicates and commits")
def _store_all(ctx):
    fn = _function(ctx, "store_all", "store_all(conn, records)")
    uri = "file:ns_l18_store_all?mode=memory&cache=shared"
    conn = sqlite3.connect(uri, uri=True)
    watcher = sqlite3.connect(uri, uri=True)
    try:
        conn.execute(_REF_SCHEMA)
        conn.commit()
        batch = [dict(r) for r in FRESH[:3]] + [dict(FRESH[0], note="echo")] + [dict(FRESH[3])]
        got = _call("store_all(conn, 5 records, one a duplicate)", fn, conn, batch)
        refs = [r[0] for r in conn.execute("SELECT ref FROM evidence ORDER BY id")]
        if refs != [r["ref"] for r in FRESH]:
            raise Fail(f"After store_all the vault holds {refs}; expected {[r['ref'] for r in FRESH]}.",
                       hint="Loop over the records in order and store() each one, skipping duplicates.")
        if got != 4:
            raise Fail(f"store_all() returned {got!r}; 5 records with one duplicate means 4 were stored.",
                       hint=_no_return_hint(got) or "Count only the records whose store() succeeded.")
        try:
            seen = watcher.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        except sqlite3.OperationalError:   # an open, uncommitted write transaction locks the table
            seen = None
        if seen != 4:
            raise Fail("The rows exist on your connection, but nobody else can see them: they were never committed.",
                       hint="Call conn.commit() before store_all returns.")
        again = _call("store_all(conn, [])", fn, conn, [])
        if again != 0:
            raise Fail(f"store_all(conn, []) returned {again!r}; storing nothing should return 0.")
    finally:
        watcher.close()
        conn.close()


@MISSION.check("Look it up — `fetch(conn, ref)`")
def _fetch(ctx):
    fn = _function(ctx, "fetch", "fetch(conn, ref)")
    conn = _ref_vault()
    for r in FRESH:
        conn.execute("INSERT INTO evidence (ref, kind, author, note) VALUES (?, ?, ?, ?)",
                     (r["ref"], r["kind"], r["author"], r["note"]))
    conn.execute("UPDATE evidence SET verified = 1 WHERE ref = ?", ("VEX-CLIP",))
    for r in (FRESH[2], FRESH[1], FRESH[3]):
        got = _call(f"fetch(conn, {r['ref']!r})", fn, conn, r["ref"])
        expected = {"ref": r["ref"], "kind": r["kind"], "author": r["author"], "note": r["note"],
                    "verified": 1 if r["ref"] == "VEX-CLIP" else 0}
        if got != expected:
            hint = _no_return_hint(got)
            if not hint and isinstance(got, tuple):
                hint = "fetchone() gives a tuple. Build a dict from it with the five key names."
            raise Fail(f"fetch(conn, {r['ref']!r}) returned {_short(got)}; expected {_short(expected)}.",
                       hint=hint or "SELECT ref, kind, author, note, verified FROM evidence WHERE ref = ?")
    for missing in ("NO-SUCH-REF", "rust-ledger"):
        got = _call(f"fetch(conn, {missing!r})", fn, conn, missing)
        if got is not None:
            raise Fail(f"fetch(conn, {missing!r}) returned {_short(got)}, but no record has that exact ref.",
                       hint="fetchone() returns None when nothing matches: return None in that case.")


@MISSION.check("Index the vault — `all_refs(conn)`")
def _all_refs(ctx):
    fn = _function(ctx, "all_refs", "all_refs(conn)")
    conn = _ref_vault()
    got = _call("all_refs(empty vault)", fn, conn)
    if got != []:
        raise Fail(f"all_refs() on an empty vault returned {_short(got)}; expected [].",
                   hint=_no_return_hint(got))
    for r in reversed(FRESH):
        conn.execute("INSERT INTO evidence (ref, kind) VALUES (?, ?)", (r["ref"], r["kind"]))
    got = _call("all_refs(conn)", fn, conn)
    expected = sorted(r["ref"] for r in FRESH)
    if got != expected:
        hint = ""
        if isinstance(got, list) and got and isinstance(got[0], tuple):
            hint = "Each row is a tuple like ('NOVA-LOG',). Take row[0] from each."
        raise Fail(f"all_refs() returned {_short(got)}; expected {expected}.",
                   hint=hint or "SELECT ref FROM evidence, take the first item of each row, then sorted().")


@MISSION.check("TUMBLER scan — no SQL built from values")
def _placeholders(ctx):
    spliced = _spliced_queries(ctx.tree)
    if spliced:
        raise Fail(f"execute() on line {spliced[0]} gets SQL text built with an f-string, + or format().",
                   hint="Values go in a tuple after the SQL: conn.execute(\"... WHERE ref = ?\", (ref,))")
    if "?" not in ctx.source:
        raise Fail("No ? placeholders anywhere in your file.", hint="Every value in your SQL should be a ?.")


@MISSION.check("Seal the vault — vault.db on disk")
def _vault_file(ctx):
    path = Path(ctx.ns.get("__file__", VAULT_FILE)).resolve().parent / VAULT_FILE
    records = ctx.get("records")
    if records != EVIDENCE:
        raise Fail("`records` doesn't match evidence.json.",
                   hint='records = json.loads(Path("evidence.json").read_text(encoding="utf-8"))')
    if not ctx.derived_from("records", "json") and not ctx.derived_from("records", "Path"):
        raise Fail("`records` must be loaded from evidence.json, not typed in.")
    if not path.exists():
        raise Fail("There's no vault.db next to your mission file.", hint='conn = sqlite3.connect("vault.db")')
    disk = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        try:
            rows = _rows(disk)
        except sqlite3.OperationalError:
            raise Fail("vault.db has no evidence table.", hint="Call create_vault(conn) on the vault connection.")
    finally:
        disk.close()
    if not rows:
        raise Fail("vault.db's evidence table is empty on disk. The inserts were never committed.",
                   hint="store_all must call conn.commit().")
    refs = sorted(r[0] for r in rows)
    if refs != UNIQUE_REFS:
        raise Fail(f"The vault holds {len(rows)} records; it should hold the {len(UNIQUE_REFS)} unique refs from evidence.json.")
    by_ref = {r[0]: r for r in rows}
    oh = by_ref["TESTIMONY-01"]
    if oh[2] != "Sister Ines O'Hara" or "loop's brake" not in (oh[3] or ""):
        raise Fail("The archivist's testimony was stored with damaged text.", hint="Placeholders store text exactly.")
    if any(r[4] != 0 for r in rows):
        raise Fail("Some evidence was stored as verified. All new evidence starts at 0.")
    if "(mirror echo)" in (by_ref["LOOM-1.0.0"][3] or ""):
        raise Fail("The mirror echo replaced the original LOOM-1.0.0 record. Keep the first, skip the duplicate.")


@MISSION.check("Report to the Order — `stored`")
def _report(ctx):
    stored = ctx.get("stored")
    if not ctx.derived_from("stored", "store_all"):
        raise Fail("`stored` must be the number store_all() returned, not one you counted yourself.",
                   hint="stored = store_all(conn, records)")
    if stored != len(UNIQUE_REFS):
        raise Fail(f"`stored` is {stored!r}; evidence.json has {len(EVIDENCE)} records and one duplicate, "
                   f"so {len(UNIQUE_REFS)} should be stored.")
    if not ctx.call_uses("print", "stored") or str(stored) not in ctx.stdout:
        raise Fail("The Order never heard the vault was sealed.", hint='print(f"VAULT SEALED: {stored} records")')
