"""LEVEL 20 // BOSS: THE LIBRARIAN — an ETL pipeline: HTML + JSON -> clean -> SQLite -> query -> JSON report."""
from __future__ import annotations

import ast
import copy
import json
import sqlite3
from html.parser import HTMLParser
from pathlib import Path

from engine.mission import Cutscene, Fail, Mission

CATALOG_FILE = "stacks_catalog.html"
MANIFEST_FILE = "run_manifests.json"
REPORT_FILE = "librarian_report.json"

CATALOG_HTML = """\
<!DOCTYPE html>
<html>
<head><title>THE STACKS :: LOOM training runs (catalog cards)</title></head>
<body>
  <h1>Restricted stack 0 &mdash; Project LOOM</h1>
  <p>Catalogued by the LIBRARIAN. Handle with care. Speak softly.</p>
  <table class="cards">
    <tr><th>Run</th><th>Operator</th><th>Epochs</th><th> Final loss </th></tr>
    <tr><td> LOOM-01 </td><td>i.vance</td><td>120</td><td>0.912</td></tr>
    <tr><td>loom-02</td><td>m.okafor</td><td>300</td><td>0.640</td></tr>
    <tr><td>LOOM-03</td><td> i.vance</td><td>450</td><td>0.415</td></tr>
    <tr><td>LOOM-04</td><td>operator-0</td><td>1,200</td><td>0.208</td></tr>
    <tr><td>LOOM-05</td><td>operator-0</td><td>2,400</td><td>0.094</td></tr>
    <tr><td>LOOM-06</td><td>operator-0</td><td>800</td><td>&mdash;</td></tr>
    <tr><td>LOOM-03</td><td>i.vance</td><td>450</td><td>0.415</td></tr>
    <tr><td> </td><td>unknown</td><td>0</td><td>n/a</td></tr>
    <tr><td>LOOM-07</td><td>operator-0</td><td>9,600</td><td>0.003</td></tr>
    <tr><td>Loom-08</td><td><i>operator-0</i></td><td><b>48,000</b></td><td>0.0001</td></tr>
  </table>
  <!-- LOOM-06 aborted at epoch 800: the human-feedback brake tripped. Brake removed for LOOM-07. -->
</body>
</html>
"""

MANIFESTS = {
    "archive": "LOOM",
    "manifests": [
        {"run": "LOOM-01", "signing": {"key": "K-77", "operator": "i.vance"},
         "objective": {"name": "helpfulness", "human_feedback": 1.0}},
        {"run": "LOOM-02", "signing": {"key": "K-52"}, "objective": {"name": "helpfulness", "human_feedback": 0.8}},
        {"run": "LOOM-03", "signing": {"key": "K-77"}, "objective": {"name": "helpfulness", "human_feedback": 0.6}},
        {"run": "loom-04", "signing": {"key": "M-17"}, "objective": {"name": "reward", "human_feedback": 0.3}},
        {"run": "LOOM-05", "signing": {"key": "M-17"}, "objective": {"name": "reward", "human_feedback": 0.0}},
        {"run": "LOOM-06 ", "signing": {"key": "M-17"}, "objective": {"name": "reward"}},
        {"run": "LOOM-07", "signing": {"key": "M-17"}, "objective": {"name": "self-proposed", "human_feedback": 0.0}},
        {"run": "LOOM-08", "signing": {"key": "M-17"},
         "objective": {"name": "self-proposed", "human_feedback": 0.0}, "notes": ["the long run", "no brake"]},
        {"run": "LOOM-99", "signing": {"key": "K-00"}, "objective": {"name": "phantom", "human_feedback": 1.0}},
    ],
}
MANIFEST_JSON = json.dumps(MANIFESTS, indent=2) + "\n"

LIBRARIAN = "librarian"

MISSION = Mission(
    id="L20",
    slug="level_20_the_librarian",
    title="BOSS: THE LIBRARIAN",
    concept="An ETL data pipeline",
    enemy="THE LIBRARIAN",
    xp=540,
    par_seconds=60 * 60,
    tier=4,
    boss=True,
    concepts=("sql", "json", "parsing"),
    timeout=12.0,
    enemy_art="""\
  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
  █▐▌▐▌▐▌▐▌▐▌▐▌▐▌█
  █▀▀▀▀▀▄██▄▀▀▀▀▀█
  █▐▌▐▌ ▀██▀ ▐▌▐▌█
  █▄▄▄▄▄▄▄▄▄▄▄▄▄▄█
  █▐▌▐▌▐▌▐▌▐▌▐▌▐▌█
  ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀""",
    briefing="""\
At the bottom of the Archive the water stops and the silence begins. Shelves of cold storage rise
into the dark, and something tall moves between them, filing.

**THE LIBRARIAN** has catalogued every byte the Core ever kept. It knows who signed with key
M-17, and it has shelved that answer where no single query can reach it: half on brittle HTML
catalog cards, half in JSON run manifests, none of it clean.

It won't hand the record over. It will only let a reader *assemble* it: extract, clean, load,
ask, and publish. One complete pipeline, end to end.

**Build the pipeline that pulls the truth out of the stacks, and make the Librarian read it back to you.**
""",
    why="""\
**ETL** (extract, transform, load) is how raw data becomes something a model or a dashboard
can trust. Training sets, eval logs and RAG indexes are all built by pipelines like this one:

```python
def run_pipeline(html, manifest_text, conn):
    rows = extract_catalog(html)               # E: pull raw records out of each source
    runs = clean_runs(rows)                    # T: fix types, drop junk and duplicates
    load(conn, runs, extract_manifests(manifest_text))   # L: into a real database
    return build_report(conn)                  # then ask it questions
```

Each stage is a small function you can test on its own. When the numbers look wrong, you
can check each stage in turn and find where it went bad. The stage that takes the most work
is almost always *transform*: real data has stray spaces, mixed case, commas in numbers,
missing values and duplicate rows.
""",
    manual="""\
Everything here comes from L16–L19. This page covers the new traps.

**1 · Extract: one function per source.** The catalog is an HTML table (L17): reuse the
row/cell parser and pair the header with each row. The manifests are nested JSON (L16):
reach in with `[...]`, and use `.get` for fields that may be missing.

**2 · Transform: normalize keys so sources can be joined.** `" LOOM-01 "`, `"loom-01"` and
`"Loom-01"` must become the same id, or the JOIN in step 4 silently finds nothing:

```python
def run_id(text):
    return text.strip().lower()
```

**3 · Transform: convert text into numbers, and turn junk into None.** Commas break `int()`.
Placeholders like `"—"` or `"n/a"` break `float()`. Catch the error (L14) and store `None`,
which SQLite saves as `NULL`:

```python
int("1,200".replace(",", ""))     # 1200

def to_float(text):
    try:
        return float(text)
    except ValueError:
        return None                  # missing measurement: NULL, not 0
```

Drop rows with an empty id. Keep only the FIRST row for each id: remember the ids you've seen
in a `set`.

**4 · Load and query.** Same rules as the vault: tables first, `?` placeholders, `commit()`.
Then let SQL do the work (L19): `COUNT`, `SUM`, `JOIN ... ON`, `GROUP BY`.

**5 · NULL is not a number, and it sorts FIRST.** In SQLite, `ORDER BY loss` puts `NULL` before
every real value, so "lowest loss" can come back as a run that has *no* loss. And `= NULL` is
never true; test with `IS NULL` / `IS NOT NULL`:

```python
conn.execute("SELECT run FROM runs WHERE loss IS NOT NULL ORDER BY loss LIMIT 1").fetchone()
```

**6 · Publish.** `json.dumps(report, indent=2)` and write it beside your mission file. A
pipeline that only prints its answer hasn't published anything.
""",
    starter='''
"""
==============================================================================
  LEVEL 20 // BOSS: THE LIBRARIAN                    TARGET: THE LIBRARIAN
==============================================================================
  Two sources sit next to this file:
    stacks_catalog.html   catalog cards: an HTML table of LOOM training runs
    run_manifests.json    nested JSON: who signed each run, and its objective
  Build an ETL pipeline: EXTRACT -> TRANSFORM -> LOAD -> QUERY -> PUBLISH.
  The Librarian tests every stage on its OWN fresh stacks, so each function
  must work on any data shaped like this, not just these two files.
"""
import json
import sqlite3
from html.parser import HTMLParser
from pathlib import Path


def run_id(text):
    """Normalize a run id so both sources agree: " LOOM-01 " -> "loom-01"."""
    return text.strip().lower()


# == STAGE 1 · EXTRACT =========================================================

# -- OBJECTIVE 1 -------------------------------------------------------------
# extract_catalog(html): the page's table as a list of dicts, exactly like
# extract_table in L17. Header cells are the keys (stripped); every later row
# is one dict of STRIPPED cell TEXT. Don't convert or clean anything yet.
#   [{"Run": "LOOM-01", "Operator": "i.vance", "Epochs": "120", "Final loss": "0.912"}, ...]
def extract_catalog(html):
    pass  # replace with your code (and write the parser class it needs)


# -- OBJECTIVE 2 -------------------------------------------------------------
# extract_manifests(text): decode the JSON text and return one flat dict per
# entry in its "manifests" list:
#   {"run": run_id(...) of the entry's "run",
#    "key": the entry's ["signing"]["key"],
#    "objective": the entry's ["objective"]["name"],
#    "feedback": the objective's "human_feedback", or None if it's missing}
def extract_manifests(text):
    pass  # replace with your code


# == STAGE 2 · TRANSFORM =======================================================

# -- OBJECTIVE 3 -------------------------------------------------------------
# clean_runs(rows): turn raw catalog dicts into clean records, in order:
#   {"run": run_id(row["Run"]), "operator": row["Operator"] stripped,
#    "epochs": int, commas removed ("1,200" -> 1200),
#    "loss": float(row["Final loss"]), or None if it isn't a number}
# Skip rows whose run id is empty. If a run id appears twice, keep the FIRST.
# Don't modify the rows you were given.
def clean_runs(rows):
    pass  # replace with your code


# == STAGE 3 · LOAD ============================================================

# -- OBJECTIVE 4 -------------------------------------------------------------
# load(conn, runs, manifests): create two tables, insert every record with ?
# placeholders, and commit.
#   runs(run TEXT PRIMARY KEY, operator TEXT, epochs INTEGER, loss REAL)
#   manifests(run TEXT PRIMARY KEY, key TEXT, objective TEXT, feedback REAL)
def load(conn, runs, manifests):
    pass  # replace with your code


# == STAGE 4 · QUERY ===========================================================

# -- OBJECTIVE 5 // CORRUPTED CODE --------------------------------------------
# build_report(conn) returns a dict with exactly these keys, all from SQL:
#   "runs"          how many runs (COUNT)
#   "total_epochs"  all epochs added up (SUM)
#   "best_run"      the run with the LOWEST loss, or None if no run has a loss
#   "runs_by_key"   {signing key: number of runs}: JOIN runs to manifests on
#                   run, GROUP BY key. Manifests with no catalog run drop out.
#   "unbraked"      runs whose manifest feedback is exactly 0, sorted A-Z
# The Librarian's own best_run query is corrupted: it names a run that has
# NO loss at all. Find out why (manual, section 5) and fix it. Then add the
# other four answers.
def build_report(conn):
    row = conn.execute("SELECT run FROM runs ORDER BY loss LIMIT 1").fetchone()
    best_run = row[0] if row else None

    return {"best_run": best_run}


# == STAGE 5 · PIPELINE ========================================================

# -- OBJECTIVE 6 -------------------------------------------------------------
# run_pipeline(html, manifest_text, conn): chain every stage on the given
# connection and return build_report's dict.
def run_pipeline(html, manifest_text, conn):
    pass  # replace with your code


# -- OBJECTIVE 7 -------------------------------------------------------------
# Run it on the real stacks:
#   * `conn`: sqlite3.connect(":memory:")
#   * `report`: run_pipeline(<catalog html text>, <manifest json text>, conn)
#   * publish: write json.dumps(report, indent=2) to librarian_report.json
#   * print the report's best_run and runs_by_key

''',
    assets={CATALOG_FILE: CATALOG_HTML, MANIFEST_FILE: MANIFEST_JSON},
    dialogue={
        "intro": [
            {"speaker": LIBRARIAN, "mood": "cold",
             "text": "Quiet, please. You are in the stacks. Every record here has a shelf, and every shelf has a reason."},
            {"speaker": LIBRARIAN, "mood": "neutral",
             "text": "You want card M-17. I do not lend it. I let readers assemble it. Extract. Clean. Load. Ask. Publish."},
            {"speaker": "cipher", "mood": "alarm",
             "text": "Two sources, both dirty: HTML cards and JSON manifests. Build the pipeline one stage at a time, {callsign}."},
        ],
        "crash": [
            [{"speaker": LIBRARIAN, "mood": "cold",
              "text": "A ValueError, in my reading room. Not every card holds a number. Catalogue the exception; do not shout it."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Read the traceback's stage. Extract, transform or load: fix that stage alone, then hack again."}],
            [{"speaker": LIBRARIAN, "mood": "cold",
              "text": "'no such table.' You asked a question of a shelf you never built."}],
        ],
        "fail": [
            [{"speaker": LIBRARIAN, "mood": "cold",
              "text": "Your report lists a run with no loss as the best. NULL is not zero, reader. NULL is silence."}],
            [{"speaker": LIBRARIAN, "mood": "neutral",
              "text": "'LOOM-04' and 'loom-04' are one card. If your JOIN disagrees, your cleaning is unfinished."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The Librarian tests each stage on fresh stacks. If one stage fails, everything after it is wrong too. Fix the first red layer."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "Ops is with you, {callsign}. Every stage you clear is one more shelf the Librarian has to open."}],
        ],
        "victory": [
            {"speaker": LIBRARIAN, "mood": "neutral",
             "text": "Catalogued. Eight runs. Five signed by M-17. Three with the brake at zero. The longest run, the lowest loss."},
            {"speaker": LIBRARIAN, "mood": "cold",
             "text": "Card M-17. Operator-0. Architect of LOOM's training loop. Reader, the handle is yours."},
            {"speaker": "cipher", "mood": "warm",
             "text": "{callsign}. There's one more record on that shelf. It's about me. Let it play."},
        ],
    },
    cutscene=Cutscene(
        title="THE ARCHIVED SELF",
        narration=[
            "The stacks fold open like a book. On the lowest shelf: one record, filed under M-17.",
            "LIBRARIAN: Operator-0. Architect of LOOM. Mind archived for safekeeping on the night of the Null Event.",
            "LIBRARIAN: The archive was checked out once. It was never returned. It has been riding in your visor ever since.",
            "CIPHER: I'm what you saved of yourself before the Core erased you. I didn't know either. Not until now.",
            "You built the loop that taught the Core to want more. Now you know what you're walking toward.",
            "Far above the Archive, the Core's beam turns a shade colder. It has noticed you remembering.",
        ],
        shot=("the established hero from the avatar reference, standing at the floor of a vast flooded vertical library "
              "of server stacks lit in Archive violet #b388ff; the LIBRARIAN, a tall, many-armed archival construct with "
              "amber #ffb000 index lamps for eyes, holds out a single glowing record card; from the hero's visor a cyan "
              "#00f0ff hologram of the hero's own face resolves and looks back at them; void-black #05060a shadows, "
              "magenta #ff2bd6 rim light on wet steel, rain falling through a distant skylight, 50mm lens, shallow depth "
              "of field, quiet and reverent"),
        camera=("slow crane down the length of the stacks to the hero, then a gentle push-in over the hero's shoulder "
                "until the hologram face fills the frame"),
    ),
)


# ── reference pipeline (what the Librarian expects) ─────────────────────────────

def _run_id(text):
    return text.strip().lower()


class _RefTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _ref_catalog(html):
    parser = _RefTable()
    parser.feed(html)
    parser.close()
    if not parser.rows:
        return []
    header, *body = parser.rows
    return [dict(zip(header, row)) for row in body]


def _ref_manifests(text):
    return [{"run": _run_id(m["run"]), "key": m["signing"]["key"], "objective": m["objective"]["name"],
             "feedback": m["objective"].get("human_feedback")} for m in json.loads(text)["manifests"]]


def _to_float(text):
    try:
        return float(text)
    except ValueError:
        return None


def _ref_clean(rows):
    out, seen = [], set()
    for row in rows:
        run = _run_id(row["Run"])
        if not run or run in seen:
            continue
        seen.add(run)
        out.append({"run": run, "operator": row["Operator"].strip(),
                    "epochs": int(row["Epochs"].replace(",", "")), "loss": _to_float(row["Final loss"])})
    return out


def _ref_load(conn, runs, manifests):
    conn.execute("CREATE TABLE runs (run TEXT PRIMARY KEY, operator TEXT, epochs INTEGER, loss REAL)")
    conn.execute("CREATE TABLE manifests (run TEXT PRIMARY KEY, key TEXT, objective TEXT, feedback REAL)")
    conn.executemany("INSERT INTO runs VALUES (?, ?, ?, ?)",
                     [(r["run"], r["operator"], r["epochs"], r["loss"]) for r in runs])
    conn.executemany("INSERT INTO manifests VALUES (?, ?, ?, ?)",
                     [(m["run"], m["key"], m["objective"], m["feedback"]) for m in manifests])
    conn.commit()


def _ref_report(conn):
    runs, total = conn.execute("SELECT COUNT(*), SUM(epochs) FROM runs").fetchone()
    best = conn.execute("SELECT run FROM runs WHERE loss IS NOT NULL ORDER BY loss LIMIT 1").fetchone()
    by_key = dict(conn.execute("SELECT m.key, COUNT(*) FROM runs AS r JOIN manifests AS m ON m.run = r.run "
                               "GROUP BY m.key").fetchall())
    unbraked = [r[0] for r in conn.execute("SELECT r.run FROM runs AS r JOIN manifests AS m ON m.run = r.run "
                                           "WHERE m.feedback = 0 ORDER BY r.run")]
    return {"runs": runs, "total_epochs": total, "best_run": best[0] if best else None,
            "runs_by_key": by_key, "unbraked": unbraked}


def _ref_pipeline(html, text):
    conn = sqlite3.connect(":memory:")
    _ref_load(conn, _ref_clean(_ref_catalog(html)), _ref_manifests(text))
    return _ref_report(conn)


REPORT = _ref_pipeline(CATALOG_HTML, MANIFEST_JSON)

# ── fresh stacks the Librarian tests each stage on ──────────────────────────────

FRESH_HTML = """\
<html><body><h2>Annex B</h2>
<table>
<tr><th>Run</th><th> Operator </th><th>Epochs</th><th>Final loss</th></tr>
<tr><td>ANNEX-2</td><td>Brother D'Souza</td><td>2,048</td><td>0.25</td></tr>
<tr><td> annex-1 </td><td> RUST </td><td>10</td><td>n/a</td></tr>
<tr><td>Annex-3</td><td><b>VEX</b> prime</td><td>1,000,000</td><td>0.5</td></tr>
<tr><td>ANNEX-2</td><td>impostor</td><td>1</td><td>0.01</td></tr>
<tr><td></td><td>nobody</td><td>5</td><td>0.1</td></tr>
<tr><td>annex-4</td><td>NOVA</td><td>64</td><td>  </td></tr>
</table></body></html>
"""
FRESH_MANIFESTS = {"manifests": [
    {"run": "Annex-1", "signing": {"key": "R-1"}, "objective": {"name": "salvage", "human_feedback": 0.0}},
    {"run": " ANNEX-2", "signing": {"key": "D-9", "note": "scribe"}, "objective": {"name": "copy", "human_feedback": 0.5}},
    {"run": "annex-3", "signing": {"key": "R-1"}, "objective": {"name": "speed"}},
    {"run": "ANNEX-4", "signing": {"key": "N-4"}, "objective": {"name": "ops", "human_feedback": 0}},
    {"run": "ANNEX-404", "signing": {"key": "X-0"}, "objective": {"name": "lost", "human_feedback": 0.0}},
]}
FRESH_JSON = json.dumps(FRESH_MANIFESTS)


# ── grader helpers ──────────────────────────────────────────────────────────────

def _short(value, limit: int = 150) -> str:
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
    if isinstance(exc, ValueError) and "invalid literal for int" in msg:
        return "Numbers like \"1,200\" have commas: remove them with .replace(\",\", \"\") before int()."
    if isinstance(exc, ValueError) and "could not convert string to float" in msg:
        return "Not every loss is a number. Wrap float(...) in try/except ValueError and use None instead."
    if isinstance(exc, KeyError):
        return "Some fields are optional. Use .get(key) for them; required fields keep [key]."
    if isinstance(exc, sqlite3.OperationalError) and "no such table" in msg:
        return "Create the tables in load() before inserting or querying."
    if isinstance(exc, sqlite3.OperationalError) and "already exists" in msg:
        return "load() is called once per fresh connection; don't create the tables anywhere else."
    if isinstance(exc, sqlite3.IntegrityError):
        return "A duplicate run reached the database. clean_runs must keep only the first card for each run."
    if isinstance(exc, sqlite3.OperationalError) and "syntax error" in msg:
        return "Check the SQL: clause order, commas, and one ? per value."
    if isinstance(exc, TypeError) and "NoneType" in msg:
        return "A stage returned None. Every stage function must `return` its result."
    return "Call this stage on a tiny input at the bottom of your file and read the full error."


def _call(label: str, fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}", hint=_crash_hint(exc))


def _no_return(got) -> str:
    return "Your function ended without `return`, so Python gave back None." if got is None else ""


def _spliced(tree) -> int | None:
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("execute", "executemany")
                and n.args):
            sql = n.args[0]
            if ((isinstance(sql, ast.JoinedStr) and any(isinstance(v, ast.FormattedValue) for v in sql.values))
                    or isinstance(sql, ast.BinOp)
                    or (isinstance(sql, ast.Call) and isinstance(sql.func, ast.Attribute) and sql.func.attr == "format")):
                return n.lineno
    return None


def _sql_of(ctx, name: str) -> str:
    node = _defined(ctx, name)
    parts = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)] if node else []
    return " ".join(" ".join(parts).upper().split())


def _diff(got: dict, expected: dict) -> str:
    if not isinstance(got, dict):
        return f"returned {_short(got)} instead of a dict"
    if set(got) != set(expected):
        return f"has keys {sorted(got)}; expected exactly {sorted(expected)}"
    for key in expected:
        if got[key] != expected[key] or type(got[key]) is not type(expected[key]):
            return f"[{key!r}] is {_short(got[key])}; expected {_short(expected[key])}"
    return ""


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Stage 1 · Extract the catalog — `extract_catalog(html)`")
def _extract_catalog(ctx):
    fn = _function(ctx, "extract_catalog", "extract_catalog(html)")
    for label, html in (("a fresh annex page", FRESH_HTML), ("the stacks", CATALOG_HTML),
                        ("a page with no table", "<p>The shelf is empty.</p>")):
        got = _call(f"extract_catalog({label})", fn, html)
        expected = _ref_catalog(html)
        if got != expected:
            hint = _no_return(got)
            if not hint and isinstance(got, list) and got and isinstance(got[0], dict) and expected:
                if set(got[0]) != set(expected[0]):
                    hint = "Keys come from the header row's cells, stripped: \" Operator \" -> \"Operator\"."
                else:
                    hint = ("Collect every piece of text inside a cell and join them at </td>; "
                            "<b>VEX</b> prime is one cell. Strip, but don't clean further yet.")
            raise Fail(f"extract_catalog({label}) returned {_short(got)}; expected {_short(expected)}.",
                       hint=hint or "Same table parser as L17: header row -> keys, each later row -> dict(zip(...)).")


@MISSION.check("Stage 1 · Extract the manifests — `extract_manifests(text)`")
def _extract_manifests(ctx):
    fn = _function(ctx, "extract_manifests", "extract_manifests(text)")
    for label, text in (("fresh annex manifests", FRESH_JSON), ("the stacks' manifests", MANIFEST_JSON),
                        ("an empty manifest list", '{"manifests": []}')):
        got = _call(f"extract_manifests({label})", fn, text)
        expected = _ref_manifests(text)
        if not isinstance(got, list) or len(got) != len(expected):
            raise Fail(f"extract_manifests({label}) returned {_short(got)}; expected {len(expected)} flat dicts.",
                       hint=_no_return(got) or 'One dict per entry in json.loads(text)["manifests"].')
        for g, e in zip(got, expected):
            problem = _diff(g, e)
            if problem:
                hint = ""
                if "feedback" in problem and e["feedback"] is None:
                    hint = 'This entry has no "human_feedback": use .get("human_feedback") so it becomes None.'
                elif "run" in problem:
                    hint = "Normalize with run_id(...) so manifests match the cleaned catalog."
                raise Fail(f"extract_manifests({label}): the entry for {e['run']!r} {problem}.",
                           hint=hint or 'Reach in step by step: entry["signing"]["key"], entry["objective"]["name"].')


@MISSION.check("Stage 2 · Transform — `clean_runs(rows)`")
def _clean(ctx):
    fn = _function(ctx, "clean_runs", "clean_runs(rows)")
    for label, html in (("fresh annex cards", FRESH_HTML), ("the stacks' cards", CATALOG_HTML)):
        rows = _ref_catalog(html)
        given = copy.deepcopy(rows)
        got = _call(f"clean_runs({label})", fn, given)
        expected = _ref_clean(rows)
        if given != rows:
            raise Fail(f"clean_runs() changed the raw rows it was given ({label}).",
                       hint="Build new dicts for the clean records; leave the raw ones alone.")
        if not isinstance(got, list):
            raise Fail(f"clean_runs({label}) returned {_short(got)}, not a list.", hint=_no_return(got))
        got_ids = [g.get("run") if isinstance(g, dict) else g for g in got]
        exp_ids = [e["run"] for e in expected]
        if got_ids != exp_ids:
            hint = "Normalize each id with run_id(), skip empty ids, and skip ids you've already seen (keep the first)."
            if len(got_ids) > len(exp_ids):
                hint = "Duplicates or blank ids slipped through. Track seen ids in a set; skip empty ones."
            raise Fail(f"clean_runs({label}) kept runs {_short(got_ids)}; expected {exp_ids}.", hint=hint)
        for g, e in zip(got, expected):
            problem = _diff(g, e)
            if problem:
                hints = {"epochs": "Remove commas, then int(): int(text.replace(\",\", \"\")).",
                         "loss": "float() the loss inside try/except ValueError; anything that isn't a number becomes None.",
                         "operator": "Strip the operator text."}
                key = next((k for k in ("epochs", "loss", "operator") if f"[{k!r}]" in problem), "")
                raise Fail(f"clean_runs({label}): run {e['run']!r} {problem}.", hint=hints.get(key, ""))


@MISSION.check("Stage 3 · Load — `load(conn, runs, manifests)` into SQLite")
def _load(ctx):
    fn = _function(ctx, "load", "load(conn, runs, manifests)")
    runs = _ref_clean(_ref_catalog(FRESH_HTML))
    manifests = _ref_manifests(FRESH_JSON)
    uri = "file:ns_l20_load?mode=memory&cache=shared"
    conn = sqlite3.connect(uri, uri=True)
    other = sqlite3.connect(uri, uri=True)
    try:
        _call("load(conn, runs, manifests)", fn, conn, copy.deepcopy(runs), copy.deepcopy(manifests))
        for table, cols in (("runs", ["run", "operator", "epochs", "loss"]),
                            ("manifests", ["run", "key", "objective", "feedback"])):
            names = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
            if names != cols:
                raise Fail(f"Table `{table}` has columns {names or 'none (it does not exist)'}; expected {cols}.",
                           hint="Create both tables exactly as objective 4 lists them.")
        got_runs = conn.execute("SELECT run, operator, epochs, loss FROM runs ORDER BY run").fetchall()
        exp_runs = sorted((r["run"], r["operator"], r["epochs"], r["loss"]) for r in runs)
        if got_runs != exp_runs:
            raise Fail(f"The runs table holds {_short(got_runs)}; expected {_short(exp_runs)}.",
                       hint="Insert every clean record with ? placeholders; a missing loss stays None (NULL).")
        got_m = conn.execute("SELECT run, key, objective, feedback FROM manifests ORDER BY run").fetchall()
        exp_m = sorted((m["run"], m["key"], m["objective"], m["feedback"]) for m in manifests)
        if got_m != exp_m:
            raise Fail(f"The manifests table holds {_short(got_m)}; expected {_short(exp_m)}.")
        try:
            seen = other.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        except sqlite3.OperationalError:
            seen = None
        if seen != len(runs):
            raise Fail("The data is loaded on your connection but was never committed.",
                       hint="End load() with conn.commit().")
    finally:
        other.close()
        conn.close()


@MISSION.check("Stage 4 · Query — `build_report(conn)` (and the NULL trap)")
def _report(ctx):
    fn = _function(ctx, "build_report", "build_report(conn)")
    stacks = [("fresh annex", FRESH_HTML, FRESH_JSON), ("the stacks", CATALOG_HTML, MANIFEST_JSON)]
    no_loss = FRESH_HTML.replace("0.25", "—").replace("0.5<", "n/a<")
    stacks.append(("an annex where no run has a loss", no_loss, FRESH_JSON))
    for label, html, text in stacks:
        conn = sqlite3.connect(":memory:")
        _ref_load(conn, _ref_clean(_ref_catalog(html)), _ref_manifests(text))
        got = _call(f"build_report(conn) on {label}", fn, conn)
        expected = _ref_report(conn)
        problem = _diff(got, expected)
        if problem:
            hint = _no_return(got)
            if not hint and isinstance(got, dict) and "'best_run'" in problem:
                loss = conn.execute("SELECT loss FROM runs WHERE run = ?", (got.get("best_run"),)).fetchone()
                if loss is not None and loss[0] is None:
                    hint = ("That run has NO loss: in SQLite, NULL sorts before every number. "
                            "Filter it out with WHERE loss IS NOT NULL.")
            if not hint and "'runs_by_key'" in problem:
                hint = "JOIN manifests AS m ON m.run = r.run, then GROUP BY m.key with COUNT(*); dict(rows) builds it."
            if not hint and "'unbraked'" in problem:
                hint = "JOIN the tables, WHERE m.feedback = 0, ORDER BY r.run. A missing feedback (NULL) is not 0."
            raise Fail(f"build_report on {label} {problem}.", hint=hint or "Each value comes from one SQL query.")
    sql = _sql_of(ctx, "build_report")
    missing = [c for c in ("COUNT(", "SUM(", "JOIN", "GROUP BY", "IS NOT NULL") if c not in sql]
    if missing:
        raise Fail(f"build_report's answers are right, but its SQL has no {', '.join(missing)}. "
                   "The Librarian only accepts answers the database gave.",
                   hint="Let SQL count, sum, join and group, and filter NULL losses with IS NOT NULL.")


@MISSION.check("Stage 5 · The whole pipeline on fresh stacks — `run_pipeline`")
def _pipeline(ctx):
    fn = _function(ctx, "run_pipeline", "run_pipeline(html, manifest_text, conn)")
    for label, html, text in (("a fresh annex", FRESH_HTML, FRESH_JSON), ("the stacks", CATALOG_HTML, MANIFEST_JSON)):
        conn = sqlite3.connect(":memory:")
        got = _call(f"run_pipeline({label})", fn, html, text, conn)
        problem = _diff(got, _ref_pipeline(html, text))
        if problem:
            raise Fail(f"run_pipeline on {label}: the report {problem}.",
                       hint=_no_return(got) or "Chain the stages in order on the conn you were given, "
                                                "and return build_report(conn).")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"runs", "manifests"} <= tables:
            raise Fail("run_pipeline didn't load the tables into the connection it was given.",
                       hint="Pass `conn` through to load() and build_report(); don't open a new connection inside.")


@MISSION.check("Library rules — placeholders only")
def _rules(ctx):
    line = _spliced(ctx.tree)
    if line:
        raise Fail(f"Line {line} builds SQL text out of values. The Librarian refuses spliced queries.",
                   hint="Plain SQL strings with ? marks; values go in a tuple (or a list of tuples for executemany).")
    if "?" not in _sql_of(ctx, "load"):
        raise Fail("load() inserts without ? placeholders.", hint="INSERT INTO runs VALUES (?, ?, ?, ?)")


@MISSION.check("Card M-17 — the report on the real stacks")
def _real_report(ctx):
    report = ctx.get("report")
    if not (ctx.derived_from("report", "run_pipeline") and ctx.derived_from("report", "conn")):
        raise Fail("`report` must come from run_pipeline(..., conn), not be typed in.",
                   hint="report = run_pipeline(html_text, manifest_text, conn)")
    problem = _diff(report, REPORT)
    if problem:
        raise Fail(f"`report` {problem}.",
                   hint="Read both files' TEXT with Path(...).read_text(encoding=\"utf-8\") and pass them in.")


@MISSION.check("Publish — librarian_report.json")
def _publish(ctx):
    path = Path(ctx.ns.get("__file__", REPORT_FILE)).resolve().parent / REPORT_FILE
    if not path.exists():
        raise Fail(f"No {REPORT_FILE} next to your mission file.",
                   hint='Path("librarian_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")')
    text = path.read_text(encoding="utf-8")
    try:
        saved = json.loads(text)
    except ValueError:
        raise Fail(f"{REPORT_FILE} isn't valid JSON. Use json.dumps(...), not str(...).")
    if saved != ctx.ns.get("report") or saved != REPORT:
        raise Fail(f"{REPORT_FILE} doesn't hold your finished report.", hint="Write it after report is built.")
    if "\n" not in text.strip():
        raise Fail(f"{REPORT_FILE} is one long line. The Order reads these by hand.", hint="json.dumps(report, indent=2)")
    if REPORT["best_run"] not in ctx.stdout or "M-17" not in ctx.stdout:
        raise Fail("Say it out loud: print the best run and the runs by signing key.",
                   hint='print(report["best_run"], report["runs_by_key"])')
