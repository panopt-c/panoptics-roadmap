"""Act IV // THE ARCHIVE (L16-L20), graded through the REAL subprocess grader.

For every level: the untouched starter must not win; a correct reference solution must
clear every firewall layer; realistic wrong solutions must fail on the right layer with a
message and a hint that teach. Each grade runs `python -m engine.harness <slug> <file> <report>`
from the code root, with the mission's assets written beside the player's file, exactly as
the game does. Nothing is written outside a temporary mission folder.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from engine.drills import CONCEPTS
from levels import load_mission

ROOT = Path(__file__).resolve().parents[1]
ACT4 = ("level_16_data_streams", "level_17_ghost_signals", "level_18_the_vault",
        "level_19_query_engine", "level_20_the_librarian")


# ── reference solutions (what a strong player would write) ──────────────────────

L16_SOLUTION = r'''
import json
from pathlib import Path

raw = Path("oracle_stream.json").read_text(encoding="utf-8")
stream = json.loads(raw)
origin = stream["header"]["origin"]
relay = stream["header"]["relay"]
operator = stream["header"]["operator"]


def flatten(packet):
    body = packet["body"]
    return {
        "id": packet["id"], "ts": packet["ts"], "priority": packet["priority"],
        "cmd": body["cmd"], "target": body.get("target"),
        "dst": packet.get("route", {}).get("to"), "tags": packet.get("tags", []),
    }


def select(records, field, value):
    return [r for r in records if r[field] == value]


def rank(records):
    return sorted(records, key=lambda r: (-r["priority"], r["ts"]))


def tally(records, field):
    counts = {}
    for r in records:
        counts[r[field]] = counts.get(r[field], 0) + 1
    return counts


records = [flatten(p) for p in stream["packets"]]
purges = rank(select(records, "cmd", "PURGE"))
report = {
    "origin": origin, "relay": relay, "packets": len(records),
    "commands": tally(records, "cmd"),
    "purge_order": [r["target"] for r in purges],
}
wire = json.dumps(report)
print(wire)
Path("intercept_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
'''

L17_SOLUTION = r'''
from html.parser import HTMLParser
from pathlib import Path

page = Path("ghost_loom.html").read_text(encoding="utf-8")


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href is not None:
                self.links.append(href)


def extract_links(html):
    parser = LinkParser()
    parser.feed(html)
    return parser.links


class TitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.text += data


def page_title(html):
    parser = TitleParser()
    parser.feed(html)
    return parser.text.strip()


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr":
            self.rows.append(self.row)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def extract_table(html):
    parser = TableParser()
    parser.feed(html)
    if not parser.rows:
        return []
    header, *body = parser.rows
    return [dict(zip(header, row)) for row in body]


class CommentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.notes = []

    def handle_comment(self, data):
        self.notes.append(data.strip())


def extract_comments(html):
    parser = CommentParser()
    parser.feed(html)
    return parser.notes


title = page_title(page)
links = extract_links(page)
builds = extract_table(page)
comments = extract_comments(page)

authors = {}
for build in builds:
    authors[build["Author"]] = authors.get(build["Author"], 0) + 1

dossier = {
    "title": title,
    "mirror_links": [link for link in links if link.startswith("/archive/")],
    "builds": len(builds),
    "authors": authors,
    "top_author": max(authors, key=authors.get),
    "ghost_notes": comments,
}
print(dossier)
'''

L18_SOLUTION = r'''
import json
import sqlite3
from pathlib import Path


def create_vault(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS evidence ("
        " id INTEGER PRIMARY KEY,"
        " ref TEXT NOT NULL UNIQUE,"
        " kind TEXT NOT NULL,"
        " author TEXT,"
        " note TEXT,"
        " verified INTEGER NOT NULL DEFAULT 0)"
    )


def store(conn, record):
    cursor = conn.execute(
        "INSERT INTO evidence (ref, kind, author, note, verified) VALUES (?, ?, ?, ?, 0)",
        (record["ref"], record["kind"], record["author"], record["note"]),
    )
    return cursor.lastrowid


def store_all(conn, records):
    count = 0
    for record in records:
        try:
            store(conn, record)
            count += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    return count


def fetch(conn, ref):
    row = conn.execute("SELECT ref, kind, author, note, verified FROM evidence WHERE ref = ?", (ref,)).fetchone()
    if row is None:
        return None
    return {"ref": row[0], "kind": row[1], "author": row[2], "note": row[3], "verified": row[4]}


def all_refs(conn):
    return sorted(row[0] for row in conn.execute("SELECT ref FROM evidence").fetchall())


conn = sqlite3.connect("vault.db")
conn.execute("DROP TABLE IF EXISTS evidence")
create_vault(conn)
records = json.loads(Path("evidence.json").read_text(encoding="utf-8"))
stored = store_all(conn, records)
print(f"VAULT SEALED: {stored} records")
'''

L19_SOLUTION = r'''
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


def sector_log(conn, sector):
    rows = conn.execute("SELECT command FROM commands WHERE sector = ? ORDER BY ts", (sector,)).fetchall()
    return [row[0] for row in rows]


def failures(conn, since):
    rows = conn.execute(
        "SELECT id FROM commands WHERE status = 'FAILED' AND ts >= ? ORDER BY ts DESC", (since,)
    ).fetchall()
    return [row[0] for row in rows]


def status_counts(conn):
    rows = conn.execute("SELECT status, COUNT(*) FROM commands GROUP BY status").fetchall()
    return dict(rows)


def top_signers(conn, limit):
    return conn.execute(
        "SELECT key_id, COUNT(*) AS n FROM commands GROUP BY key_id ORDER BY n DESC, key_id ASC LIMIT ?",
        (limit,),
    ).fetchall()


def signers_of(conn, command):
    return conn.execute(
        "SELECT o.handle, o.key_id FROM commands AS c "
        "JOIN operators AS o ON o.key_id = c.key_id "
        "WHERE c.command = ? ORDER BY c.ts",
        (command,),
    ).fetchall()


def ledger_span(conn):
    count, first, last = conn.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM commands").fetchone()
    return {"commands": count, "first_ts": first, "last_ts": last}


conn = sqlite3.connect(":memory:")
ledger = json.loads(Path("archive_ledger.json").read_text(encoding="utf-8"))
build_archive(conn, ledger)
null_signers = signers_of(conn, "EXECUTE NULL_EVENT")
culprit_key = null_signers[0][1]
print(f"NULL EVENT SIGNED BY: {culprit_key}")
'''

L20_SOLUTION = r'''
import json
import sqlite3
from html.parser import HTMLParser
from pathlib import Path


def run_id(text):
    """Normalize a run id so both sources agree: " LOOM-01 " -> "loom-01"."""
    return text.strip().lower()


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr":
            self.rows.append(self.row)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def extract_catalog(html):
    parser = TableParser()
    parser.feed(html)
    if not parser.rows:
        return []
    header, *body = parser.rows
    return [dict(zip(header, row)) for row in body]


def extract_manifests(text):
    data = json.loads(text)
    out = []
    for entry in data["manifests"]:
        out.append({
            "run": run_id(entry["run"]),
            "key": entry["signing"]["key"],
            "objective": entry["objective"]["name"],
            "feedback": entry["objective"].get("human_feedback"),
        })
    return out


def to_float(text):
    try:
        return float(text)
    except ValueError:
        return None


def clean_runs(rows):
    clean = []
    seen = set()
    for row in rows:
        run = run_id(row["Run"])
        if run == "" or run in seen:
            continue
        seen.add(run)
        clean.append({
            "run": run,
            "operator": row["Operator"].strip(),
            "epochs": int(row["Epochs"].replace(",", "")),
            "loss": to_float(row["Final loss"]),
        })
    return clean


def load(conn, runs, manifests):
    conn.execute("CREATE TABLE runs (run TEXT PRIMARY KEY, operator TEXT, epochs INTEGER, loss REAL)")
    conn.execute("CREATE TABLE manifests (run TEXT PRIMARY KEY, key TEXT, objective TEXT, feedback REAL)")
    for r in runs:
        conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?)", (r["run"], r["operator"], r["epochs"], r["loss"]))
    for m in manifests:
        conn.execute("INSERT INTO manifests VALUES (?, ?, ?, ?)", (m["run"], m["key"], m["objective"], m["feedback"]))
    conn.commit()


def build_report(conn):
    row = conn.execute("SELECT run FROM runs WHERE loss IS NOT NULL ORDER BY loss LIMIT 1").fetchone()
    best_run = row[0] if row else None
    count, total = conn.execute("SELECT COUNT(*), SUM(epochs) FROM runs").fetchone()
    by_key = conn.execute(
        "SELECT m.key, COUNT(*) FROM runs AS r JOIN manifests AS m ON m.run = r.run GROUP BY m.key"
    ).fetchall()
    unbraked = conn.execute(
        "SELECT r.run FROM runs AS r JOIN manifests AS m ON m.run = r.run WHERE m.feedback = 0 ORDER BY r.run"
    ).fetchall()
    return {"runs": count, "total_epochs": total, "best_run": best_run,
            "runs_by_key": dict(by_key), "unbraked": [r[0] for r in unbraked]}


def run_pipeline(html, manifest_text, conn):
    runs = clean_runs(extract_catalog(html))
    manifests = extract_manifests(manifest_text)
    load(conn, runs, manifests)
    return build_report(conn)


conn = sqlite3.connect(":memory:")
html_text = Path("stacks_catalog.html").read_text(encoding="utf-8")
manifest_text = Path("run_manifests.json").read_text(encoding="utf-8")
report = run_pipeline(html_text, manifest_text, conn)
Path("librarian_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(report["best_run"], report["runs_by_key"])
'''


# ── grading through the real harness ─────────────────────────────────────────────

def grade(slug: str, source: str) -> dict:
    """Write the player's file + assets to a fresh folder and run the sandboxed grader on it."""
    mission = load_mission(slug)
    with tempfile.TemporaryDirectory(prefix="ns-act4-") as tmp:
        folder = Path(tmp)
        player = folder / mission.filename
        player.write_bytes(source.lstrip("\n").encode("utf-8"))
        for name, text in mission.assets.items():
            (folder / name).write_bytes(text.encode("utf-8"))
        out = folder / "report.json"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        started = time.monotonic()
        proc = subprocess.run([sys.executable, "-m", "engine.harness", slug, str(player), str(out)],
                              cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=mission.timeout + 20)
        elapsed = time.monotonic() - started
        if not out.exists():
            raise AssertionError(f"grader produced no report:\n{proc.stderr.decode(errors='replace')[-1500:]}")
        report = json.loads(out.read_text(encoding="utf-8"))
        report["elapsed"] = elapsed
        report["folder"] = sorted(p.name for p in folder.iterdir())
        report["files"] = {p.name: p.read_text(encoding="utf-8") for p in folder.iterdir()
                           if p.is_file() and p.suffix == ".json" and p.name != "report.json"}
        db = folder / "vault.db"
        if db.exists():
            conn = sqlite3.connect(db)
            try:
                report["vault"] = conn.execute("SELECT ref, author, note, verified FROM evidence ORDER BY id").fetchall()
            except sqlite3.OperationalError:     # e.g. the starter: vault.db exists, the table doesn't
                report["vault"] = None
            finally:
                conn.close()
    return report


def mutate(source: str, old: str, new: str) -> str:
    assert old in source, f"mutation anchor not found: {old!r}"
    return source.replace(old, new, 1)


class ActIVMixin:
    """Shared checks; each level's TestCase mixes this in."""
    slug = ""
    solution = ""

    @classmethod
    def setUpClass(cls):
        cls.mission = load_mission(cls.slug)

    def describe(self, report) -> str:
        lines = [f"status={report['status']} error={report['error']}"]
        lines += [f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['name']}: {c['message']} | {c['hint']}"
                  for c in report["checks"]]
        return "\n".join(lines)

    def assert_victory(self, report):
        self.assertEqual(report["status"], "ok", self.describe(report))
        self.assertEqual(len(report["checks"]), len(self.mission.checks))
        self.assertTrue(all(c["passed"] for c in report["checks"]), self.describe(report))
        self.assertLess(report["elapsed"], self.mission.timeout / 2, "grading must finish well under the timeout")
        return report

    def assert_fails_on(self, report, layer: str, *teaches: str, first: bool = True):
        """`layer` failed (and, by default, is the first red layer); its text contains every fragment."""
        self.assertNotEqual(report["status"], "harness_error", self.describe(report))
        failed = [c for c in report["checks"] if not c["passed"]]
        self.assertTrue(failed, "expected a failing layer:\n" + self.describe(report))
        target = next((c for c in failed if layer in c["name"]), None)
        self.assertIsNotNone(target, f"layer {layer!r} should fail:\n" + self.describe(report))
        if first:
            self.assertIs(target, failed[0], f"{layer!r} should be the first red layer:\n" + self.describe(report))
        self.assertTrue(target["message"].strip(), "failure needs a message")
        self.assertTrue(target["hint"].strip(), "failure needs a teaching hint")
        text = target["message"] + " " + target["hint"]
        for fragment in teaches:
            self.assertIn(fragment, text, self.describe(report))
        return target

    # every Act IV level gets these three for free
    def test_starter_is_not_a_victory(self):
        report = grade(self.slug, self.mission.starter)
        self.assertNotIn(report["status"], ("harness_error", "timeout"), self.describe(report))
        self.assertFalse(report["status"] == "ok" and all(c["passed"] for c in report["checks"]),
                         "the untouched starter must not clear the level")
        self.assertTrue(any(not c["passed"] and c["message"] for c in report["checks"]))

    def test_reference_solution_clears_every_layer(self):
        self.assert_victory(grade(self.slug, self.solution))

    def test_mission_contract(self):
        m = self.mission
        self.assertEqual(m.slug, self.slug)
        self.assertEqual(m.tier, 4)                          # S3 DATA = Intermediate+
        self.assertTrue(m.concepts and set(m.concepts) <= set(CONCEPTS), m.concepts)
        self.assertTrue(5 <= len(m.checks) <= 9)
        self.assertLessEqual(len(re.sub(r"```.*?```", "", m.briefing, flags=re.S).split()), 130)
        self.assertLessEqual(len(re.sub(r"```.*?```", "", m.why, flags=re.S).split()), 160)
        self.assertIn("**", m.briefing.strip().splitlines()[-1], "briefing ends with a bold call to action")
        self.assertGreaterEqual(m.manual.count("```python"), 3, "manual sections each carry a code example")
        art = m.enemy_art.splitlines()
        self.assertTrue(len(art) <= 7 and max(map(len, art)) <= 20)
        self.assertIn("OBJECTIVE 1", m.starter)
        self.assertIn("CORRUPTED CODE", m.starter)
        self.assertIn("def ", m.starter, "tier 3+ players write functions the grader calls on fresh inputs")
        low, high = (450, 570) if m.boss else (300, 380)
        self.assertTrue(low <= m.xp <= high, m.xp)
        self.assertLessEqual(m.timeout, 20)
        self.assertEqual(set(m.dialogue), {"intro", "crash", "fail", "victory"})
        lines = list(m.dialogue["intro"]) + list(m.dialogue["victory"])
        for pool in ("crash", "fail"):
            self.assertTrue(m.dialogue[pool])
            for sequence in m.dialogue[pool]:
                self.assertTrue(1 <= len(sequence) <= 2)
                lines += sequence
        for line in lines:
            self.assertLessEqual(len(line["text"]), 160, line["text"])
            self.assertIn(line["mood"], ("neutral", "smirk", "alarm", "warm", "cold"))
            self.assertIn(line["speaker"], ("cipher", "vex", "rust", "nova", "oracle", "librarian"))
        # the story lead's Act IV opening (levels/story.py) names the player's key K-7F3A
        story = " ".join(line["text"] for line in lines) + m.briefing
        self.assertNotIn("M-17", story, "the Archive's key is K-7F3A, not RUST's L04 gate pass")


# ── L16 · DATA STREAMS ───────────────────────────────────────────────────────────

class Level16DataStreamsTests(ActIVMixin, unittest.TestCase):
    slug = "level_16_data_streams"
    solution = L16_SOLUTION

    def test_victory_archives_pretty_json_and_broadcasts_it(self):
        report = self.assert_victory(grade(self.slug, self.solution))
        saved = report["files"]["intercept_report.json"]
        self.assertGreater(saved.count("\n"), 5)
        data = json.loads(saved)
        self.assertEqual(data["purge_order"], ["operator-records", "monastery-index", "ghost-mirrors"])
        self.assertIn('"purge_order"', report["stdout"])

    def test_sort_without_tie_break(self):
        source = mutate(self.solution, 'key=lambda r: (-r["priority"], r["ts"])',
                        'key=lambda r: r["priority"], reverse=True')
        self.assert_fails_on(grade(self.slug, source), "Rank the orders", "tuple", "expected")

    def test_in_place_sort_returns_none(self):
        source = mutate(self.solution, 'return sorted(records, key=lambda r: (-r["priority"], r["ts"]))',
                        'records.sort(key=lambda r: (-r["priority"], r["ts"]))\n    return records')
        self.assert_fails_on(grade(self.slug, source), "Rank the orders", "original order", "sorted(")

    def test_required_route_crashes_on_packets_without_one(self):
        source = mutate(self.solution, 'packet.get("route", {}).get("to")', 'packet["route"]["to"]')
        report = grade(self.slug, source)
        self.assertEqual(report["status"], "crash")
        self.assert_fails_on(report, "Flatten packets", "KeyError", '.get("route", {})')

    def test_flatten_that_mutates_its_packet(self):
        source = mutate(self.solution, '    body = packet["body"]\n',
                        '    body = packet.pop("body")\n')
        report = grade(self.slug, source)
        # popping from the real packets corrupts `stream` itself, so the decode layer points at flatten first
        self.assert_fails_on(report, "Decode the burst", "changed it", "flatten")
        self.assert_fails_on(report, "Flatten packets", "changed", "NEW dict", first=False)

    def test_unrepaired_str_encoder(self):
        report = grade(self.slug, mutate(self.solution, "wire = json.dumps(report)", "wire = str(report)"))
        self.assert_fails_on(report, "Repair the encoder", "str(report)", "json.dumps")

    def test_hand_typed_report_is_rejected(self):
        source = mutate(self.solution, '''report = {
    "origin": origin, "relay": relay, "packets": len(records),
    "commands": tally(records, "cmd"),
    "purge_order": [r["target"] for r in purges],
}''', '''report = {"origin": "ORACLE", "relay": "HYDRA-7", "packets": 8,
          "commands": {"INDEX": 4, "PURGE": 3, "SEAL": 1, "HEARTBEAT": 1},
          "purge_order": ["operator-records", "monastery-index", "ghost-mirrors"]}''')
        self.assert_fails_on(grade(self.slug, source), "Assemble the intercept", "typed in by hand")

    def test_one_line_archive(self):
        source = mutate(self.solution, "json.dumps(report, indent=2)", "json.dumps(report)")
        self.assert_fails_on(grade(self.slug, source), "Archive the intercept", "one line", "indent=2")


# ── L17 · GHOST SIGNALS ──────────────────────────────────────────────────────────

class Level17GhostSignalsTests(ActIVMixin, unittest.TestCase):
    slug = "level_17_ghost_signals"
    solution = L17_SOLUTION

    def test_victory_prints_the_dossier(self):
        report = self.assert_victory(grade(self.slug, self.solution))
        self.assertIn("operator-0", report["stdout"])
        self.assertIn("Someone has to be able to stop it.", report["stdout"])

    def test_unrepaired_link_parser(self):
        source = mutate(self.solution, 'href = dict(attrs).get("href")\n            if href is not None:\n                self.links.append(href)',
                        'href = attrs["href"]\n            self.links.append(href)')
        report = grade(self.slug, source)
        self.assertEqual(report["status"], "crash")
        self.assert_fails_on(report, "Repair the link parser", "list indices", "dict(attrs)")

    def test_bare_anchor_appends_none(self):
        source = mutate(self.solution, "            if href is not None:\n                self.links.append(href)",
                        "            self.links.append(href)")
        self.assert_fails_on(grade(self.slug, source), "Repair the link parser", "no href")

    def test_class_level_list_is_shared(self):
        source = mutate(self.solution, "    def __init__(self):\n        super().__init__()\n        self.links = []\n",
                        "    links = []\n")
        self.assert_fails_on(grade(self.slug, source), "Repair the link parser", "self.links")

    def test_shared_parser_leaks_links_between_pages(self):
        source = mutate(self.solution, "def extract_links(html):\n    parser = LinkParser()\n",
                        "SHARED = LinkParser()\n\n\ndef extract_links(html):\n    parser = SHARED\n")
        self.assert_fails_on(grade(self.slug, source), "Pull the links", "fresh LinkParser")

    def test_last_text_piece_only(self):
        source = mutate(self.solution, 'self.row.append("".join(self.cell).strip())',
                        "self.row.append(self.cell[-1].strip())")
        self.assert_fails_on(grade(self.slug, source), "Lift the table", "join")

    def test_string_search_title_breaks_on_real_html(self):
        source = mutate(self.solution, "    parser = TitleParser()\n    parser.feed(html)\n    return parser.text.strip()",
                        '    start = html.find("<title>")\n    end = html.find("</title>")\n'
                        '    if start == -1:\n        return ""\n    return html[start + 7:end].strip()')
        self.assert_fails_on(grade(self.slug, source), "Read the title", "Ash & Ember")

    def test_dossier_must_be_printed(self):
        self.assert_fails_on(grade(self.slug, mutate(self.solution, "print(dossier)", "")),
                             "Compile the dossier", "print(dossier)")


# ── L18 · THE VAULT ──────────────────────────────────────────────────────────────

class Level18VaultTests(ActIVMixin, unittest.TestCase):
    slug = "level_18_the_vault"
    solution = L18_SOLUTION

    def test_victory_seals_the_vault_on_disk(self):
        report = self.assert_victory(grade(self.slug, self.solution))
        self.assertIn("VAULT SEALED: 9 records", report["stdout"])
        vault = report["vault"]
        self.assertEqual(len(vault), 9)
        self.assertIn(("TESTIMONY-01", "Sister Ines O'Hara",
                       "The Order's archivist saw the loop's brake pulled the night before the Null Event.", 0), vault)

    def test_unrepaired_spliced_insert(self):
        source = mutate(self.solution, '''    cursor = conn.execute(
        "INSERT INTO evidence (ref, kind, author, note, verified) VALUES (?, ?, ?, ?, 0)",
        (record["ref"], record["kind"], record["author"], record["note"]),
    )''', '''    sql = f"INSERT INTO evidence (ref, kind, author, note, verified) VALUES ('{record['ref']}', '{record['kind']}', '{record['author']}', '{record['note']}', 0)"
    cursor = conn.execute(sql)''')
        report = grade(self.slug, source)
        self.assertEqual(report["status"], "crash")
        self.assert_fails_on(report, "Repair the intake", "syntax error", "?")

    def test_spliced_lookup_breaks_on_apostrophes(self):
        source = mutate(self.solution, '"SELECT ref, kind, author, note, verified FROM evidence WHERE ref = ?", (ref,)',
                        'f"SELECT ref, kind, author, note, verified FROM evidence WHERE ref = \'{ref}\'"')
        self.assert_fails_on(grade(self.slug, source), "Look it up", "ORDER-0'1", "?")

    def test_forgotten_commit(self):
        source = mutate(self.solution, "    conn.commit()\n    return count", "    return count")
        self.assert_fails_on(grade(self.slug, source), "Refuse the echoes", "committed", "conn.commit()")

    def test_duplicates_not_caught(self):
        source = mutate(self.solution, '''        try:
            store(conn, record)
            count += 1
        except sqlite3.IntegrityError:
            pass''', '''        store(conn, record)
        count += 1''')
        report = grade(self.slug, source)
        self.assertEqual(report["status"], "crash")
        self.assert_fails_on(report, "Refuse the echoes", "IntegrityError", "catch")

    def test_schema_without_unique(self):
        source = mutate(self.solution, '" ref TEXT NOT NULL UNIQUE,"', '" ref TEXT NOT NULL,"')
        self.assert_fails_on(grade(self.slug, source), "Build the vault", "same ref", "UNIQUE")

    def test_fetch_returns_raw_tuple(self):
        source = mutate(self.solution, '''    if row is None:
        return None
    return {"ref": row[0], "kind": row[1], "author": row[2], "note": row[3], "verified": row[4]}''',
                        "    return row")
        self.assert_fails_on(grade(self.slug, source), "Look it up", "tuple", "dict")

    def test_hand_counted_report(self):
        source = mutate(self.solution, "stored = store_all(conn, records)", "store_all(conn, records)\nstored = 9")
        self.assert_fails_on(grade(self.slug, source), "Report to the Order", "store_all")


# ── L19 · QUERY ENGINE ───────────────────────────────────────────────────────────

class Level19QueryEngineTests(ActIVMixin, unittest.TestCase):
    slug = "level_19_query_engine"
    solution = L19_SOLUTION

    def test_victory_names_the_key(self):
        report = self.assert_victory(grade(self.slug, self.solution))
        self.assertIn("NULL EVENT SIGNED BY: K-7F3A", report["stdout"])

    def test_missing_order_by(self):
        source = mutate(self.solution, "WHERE sector = ? ORDER BY ts", "WHERE sector = ?")
        self.assert_fails_on(grade(self.slug, source), "WHERE + ORDER BY", "grader's own ledger", "ORDER BY ts")

    def test_unrepaired_census_without_group_by(self):
        source = mutate(self.solution, '"SELECT status, COUNT(*) FROM commands GROUP BY status"',
                        '"SELECT status, COUNT(*) FROM commands"')
        self.assert_fails_on(grade(self.slug, source), "Repair the census", "GROUP BY status")

    def test_counting_in_python_is_redacted(self):
        source = mutate(self.solution, '''    rows = conn.execute("SELECT status, COUNT(*) FROM commands GROUP BY status").fetchall()
    return dict(rows)''', '''    counts = {}
    for (status,) in conn.execute("SELECT status FROM commands"):
        counts[status] = counts.get(status, 0) + 1
    return counts''')
        self.assert_fails_on(grade(self.slug, source), "Repair the census", "not from SQL", "GROUP BY")

    def test_top_signers_without_tie_break(self):
        source = mutate(self.solution, "ORDER BY n DESC, key_id ASC LIMIT ?", "ORDER BY n DESC LIMIT ?")
        self.assert_fails_on(grade(self.slug, source), "Rank the signers", "key_id ASC")

    def test_left_join_keeps_unknown_keys(self):
        source = mutate(self.solution, '"JOIN operators AS o', '"LEFT JOIN operators AS o')
        self.assert_fails_on(grade(self.slug, source), "JOIN the keys", "drop out of a JOIN")

    def test_span_in_python_crashes_on_an_empty_ledger(self):
        source = mutate(self.solution, '''    count, first, last = conn.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM commands").fetchone()''',
                        '''    stamps = [r[0] for r in conn.execute("SELECT ts FROM commands")]
    count, first, last = len(stamps), min(stamps), max(stamps)''')
        self.assert_fails_on(grade(self.slug, source), "Measure the ledger", "empty ledger")

    def test_spliced_query_is_caught(self):
        source = mutate(self.solution, '"SELECT command FROM commands WHERE sector = ? ORDER BY ts", (sector,)',
                        'f"SELECT command FROM commands WHERE sector = \'{sector}\' ORDER BY ts"')
        self.assert_fails_on(grade(self.slug, source), "Interrogate the Archive", "builds SQL text", "?")

    def test_hand_typed_culprit(self):
        source = mutate(self.solution, "culprit_key = null_signers[0][1]", 'culprit_key = "K-7F3A"')
        self.assert_fails_on(grade(self.slug, source), "Interrogate the Archive", "typed in", "null_signers[0][1]")


# ── L20 · BOSS: THE LIBRARIAN ────────────────────────────────────────────────────

class Level20LibrarianTests(ActIVMixin, unittest.TestCase):
    slug = "level_20_the_librarian"
    solution = L20_SOLUTION

    def test_victory_publishes_the_report(self):
        report = self.assert_victory(grade(self.slug, self.solution))
        published = json.loads(report["files"]["librarian_report.json"])
        self.assertEqual(published, {"runs": 8, "total_epochs": 62870, "best_run": "loom-08",
                                     "runs_by_key": {"K-52": 1, "K-77": 2, "K-7F3A": 5},
                                     "unbraked": ["loom-05", "loom-07", "loom-08"]})
        self.assertIn("K-7F3A", report["stdout"])

    def test_boss_staging(self):
        m = self.mission
        self.assertTrue(m.boss)
        self.assertTrue(3 <= len(m.cutscene.narration) <= 6)
        self.assertTrue(m.cutscene.shot and m.cutscene.camera)
        self.assertIn("#b388ff", m.cutscene.shot, "the Archive's violet from the art bible")
        self.assertFalse(any("{callsign}" in line for line in m.cutscene.narration),
                         "narration isn't callsign-substituted by the client")
        self.assertEqual(m.dialogue["intro"][0]["speaker"], "librarian")
        self.assertEqual(m.dialogue["victory"][0]["speaker"], "librarian")
        for stage in ("STAGE 1", "STAGE 2", "STAGE 3", "STAGE 4", "STAGE 5"):
            self.assertIn(stage, m.starter)

    def test_unrepaired_null_trap(self):
        source = mutate(self.solution, "SELECT run FROM runs WHERE loss IS NOT NULL ORDER BY loss LIMIT 1",
                        "SELECT run FROM runs ORDER BY loss LIMIT 1")
        self.assert_fails_on(grade(self.slug, source), "Stage 4", "best_run", "IS NOT NULL")

    def test_commas_in_epochs(self):
        source = mutate(self.solution, 'int(row["Epochs"].replace(",", ""))', 'int(row["Epochs"])')
        report = grade(self.slug, source)
        self.assertEqual(report["status"], "crash")
        self.assert_fails_on(report, "Stage 2", "2,048", "replace")

    def test_junk_loss_without_try(self):
        source = mutate(self.solution, '''    try:
        return float(text)
    except ValueError:
        return None''', "    return float(text)")
        self.assert_fails_on(grade(self.slug, source), "Stage 2", "could not convert", "try/except")

    def test_unnormalized_manifest_ids(self):
        source = mutate(self.solution, '"run": run_id(entry["run"]),', '"run": entry["run"],')
        self.assert_fails_on(grade(self.slug, source), "Extract the manifests", "run_id")

    def test_missing_feedback_defaulted_to_zero(self):
        source = mutate(self.solution, '.get("human_feedback")', '.get("human_feedback", 0)')
        self.assert_fails_on(grade(self.slug, source), "Extract the manifests", "None")

    def test_load_without_commit(self):
        source = mutate(self.solution, "(m[\"run\"], m[\"key\"], m[\"objective\"], m[\"feedback\"]))\n    conn.commit()",
                        "(m[\"run\"], m[\"key\"], m[\"objective\"], m[\"feedback\"]))")
        self.assert_fails_on(grade(self.slug, source), "Stage 3", "committed", "conn.commit()")

    def test_spliced_insert_breaks_on_apostrophes(self):
        source = mutate(self.solution,
                        '''conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?)", (r["run"], r["operator"], r["epochs"], r["loss"]))''',
                        '''conn.execute(f"INSERT INTO runs VALUES ('{r['run']}', '{r['operator']}', {r['epochs']}, {r['loss'] or 'NULL'})")''')
        self.assert_fails_on(grade(self.slug, source), "Stage 3", "syntax error")

    def test_counting_in_python_is_refused(self):
        source = mutate(self.solution, '''    count, total = conn.execute("SELECT COUNT(*), SUM(epochs) FROM runs").fetchone()''',
                        '''    epochs = [r[0] for r in conn.execute("SELECT epochs FROM runs")]
    count, total = len(epochs), (sum(epochs) if epochs else None)''')
        self.assert_fails_on(grade(self.slug, source), "Stage 4", "SUM(", "answers the database gave")

    def test_pipeline_that_opens_its_own_connection(self):
        source = mutate(self.solution, "def run_pipeline(html, manifest_text, conn):\n",
                        "def run_pipeline(html, manifest_text, conn):\n    conn = sqlite3.connect(':memory:')\n")
        self.assert_fails_on(grade(self.slug, source), "Stage 5", "conn")

    def test_one_line_publication(self):
        source = mutate(self.solution, "json.dumps(report, indent=2)", "json.dumps(report)")
        self.assert_fails_on(grade(self.slug, source), "Publish", "one long line", "indent=2")


class ActIVRegistryTests(unittest.TestCase):
    def test_every_act_iv_level_is_registered_and_built(self):
        from levels import CAMPAIGN
        sector = next(s for s in CAMPAIGN if s.tier == 3)
        self.assertEqual(tuple(l.slug for l in sector.levels), ACT4)
        for slug, level in zip(ACT4, sector.levels):
            self.assertEqual(load_mission(slug).id, level.id)


if __name__ == "__main__":
    unittest.main()
