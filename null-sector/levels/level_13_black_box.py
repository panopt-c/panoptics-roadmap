"""LEVEL 13 // BLACK BOX — files: `with open`, reading/writing lines, the `csv` module, `pathlib`."""
from __future__ import annotations

import ast
import contextlib
import csv
import io
import tempfile
from pathlib import Path

from engine.mission import Fail, Mission

FLIGHT_LOG = """\
t,altitude,speed,event
0,4200,610,CRUISE
12,4180,612,
24,4100,598,"ENGINE 2 FIRE, SUPPRESSION FAILED"
36,3650,571,
48,2900,540,"MAYDAY, MAYDAY, HALCYON-9"
60,2100,505,
72,1400,470,DUMPING CARGO
84,800,430,
96,310,392,"GEAR DOWN, NO RESPONSE"
108,0,0,IMPACT
"""

VOICE_RECORDER = """\
[T+000] PILOT: Halcyon-9, level at four-two hundred. Cargo sealed for the Forge.
[T+019] COPILOT: Number two is running hot.

[T+024] PILOT: Fire on two. Suppression's dead.
[T+031] UNKNOWN: Don't fight it. Dump the cargo.
[T+033] COPILOT: Who is on this channel?

[T+047] PILOT: Mayday, mayday. Halcyon-9 going down short of the Foundry.
[T+069] UNKNOWN: The shards are poisoned. The Forge can't have them.
[T+070] PILOT: Identify yourself!
	[T+090] UNKNOWN: You know me. Or you will.
[T+104] COPILOT: Brace, brace, brace.

[T+108] UNKNOWN: If you find this... finish what I started.
"""

MISSION = Mission(
    id="L13",
    slug="level_13_black_box",
    title="BLACK BOX",
    concept="Reading & writing files",
    enemy="TOMBSTONE.wipe",
    xp=260,
    par_seconds=35 * 60,
    tier=3,
    concepts=("files",),
    assets={"flight_log.csv": FLIGHT_LOG, "voice_recorder.txt": VOICE_RECORDER},
    enemy_art="""\
   ▄▄▄▄▄▄▄▄▄▄▄▄
  █ ▄▀▀▀▀▀▀▀▀▄ █
  █ █ R.I.P. █ █
  █ █ ░░░░░░ █ █
  █ ▀▄▄▄▄▄▄▄▄▀ █
  █▄▄▄▄▄▄▄▄▄▄▄▄█
  ▀▀▀▀▀▀▀▀▀▀▀▀▀▀""",
    briefing="""\
Your scout's beacon leads past the slag fields to a gouge in the ground a kilometre long. At
the end of it: transport **HALCYON-9**, split open, still smoking.

Its black box survived. Barely. **TOMBSTONE.wipe**, the recorder's crash protocol, is already
counting down. At zero it erases everything, to protect the cargo manifest.

Two files are left: a flight log and a cockpit voice recording. RUST wants the telemetry.
CIPHER wants the voice. One speaker on that recording isn't on the crew manifest.

Files are how data outlives the machine that made it.

**Read the black box, copy the evidence to disk, and get out before TOMBSTONE wipes it.**
""",
    why="""\
Models don't learn from variables you type in. They learn from **files**: CSVs of labelled
samples, text corpora, logs. Almost every training script opens with something like this:

```python
import csv
from pathlib import Path

DATA = Path(__file__).parent / "data" / "train.csv"

with open(DATA, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))      # one dict per sample
```

`pathlib` builds paths that work on Windows, macOS and Linux. `with` guarantees the file is
closed even if your code crashes halfway. The `csv` module handles the cases that break a
naive `split(",")`, like a text field that contains a comma. And writing results back to disk
is how a pipeline hands its work to the next stage, or to the next person.
""",
    manual="""\
**1. Paths with `pathlib`.** A `Path` is a file location you can build with `/`. Start from
the folder your script lives in, so the path works no matter where you run it from:

```python
from pathlib import Path

HERE = Path(__file__).parent          # the folder this .py file is in
manifest = HERE / "cargo.csv"         # a Path, not a str
manifest.name      # 'cargo.csv'
manifest.suffix    # '.csv'
manifest.exists()  # True if the file is really there
```

**2. Reading a text file with `with open`.** `with` opens the file and **always closes it**
when the block ends, even if something crashes inside. Looping over the file gives one line
at a time, each still ending in `"\\n"`:

```python
with open(manifest, encoding="utf-8") as f:
    for line in f:
        clean = line.strip()          # drop spaces, tabs and the newline
        if clean:                     # skip blank lines
            print(clean)
```

`f = open(...)` without `with` works too, until you forget `f.close()`. Don't risk it.

**3. Writing a text file.** The second argument is the **mode**: `"r"` read (the default),
`"w"` write (wipes the file first), `"a"` append (adds to the end). `write()` does **not**
add a newline for you:

```python
with open(HERE / "notes.txt", "w", encoding="utf-8") as f:
    f.write("first\\n")
    f.write("second\\n")
```

Run that twice and the file still has two lines. With `"a"`, it would have four.

**4. Reading CSV with the `csv` module.** Never split CSV lines on commas yourself: a field
like `"FIRE, NO RESPONSE"` contains one. `csv.DictReader` reads the header row and gives you
each later row as a dict. **Every value arrives as text**, so convert numbers yourself.
Open CSV files with `newline=""` (the csv module handles line endings itself):

```python
import csv

with open(HERE / "cargo.csv", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):     # {'item': 'fuse', 'qty': '4', ...}
        qty = int(row["qty"])
```

Because DictReader finds columns **by name**, it keeps working if someone reorders them.

**5. Writing CSV.** `csv.writer` turns a list into one row, adding quotes where needed:

```python
with open(HERE / "out.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["item", "note"])          # header
    writer.writerow(["fuse", "dry, sealed"])   # written as: fuse,"dry, sealed"
```

**6. The classic file crash:**

```text
FileNotFoundError: [Errno 2] No such file or directory: 'cargo.csv'
```

A bare name like `"cargo.csv"` is looked up in the folder you *ran Python from*, which may
not be the script's folder. Build paths from `HERE` instead.
""",
    starter='''
"""
==============================================================================
  LEVEL 13 // BLACK BOX                              TARGET: TOMBSTONE.wipe
==============================================================================
  HALCYON-9's recorder left two files next to this one:
      flight_log.csv       telemetry, one row every 12 seconds
      voice_recorder.txt   the cockpit voice recording
  Don't edit them. (If you break one, delete it: the game restores it.)
  The grader also feeds your functions its OWN files, so they must work on
  any file, not just these two.
"""
import csv
from pathlib import Path

HERE = Path(__file__).parent      # the folder this file (and the black box) lives in


# -- OBJECTIVE 1 -------------------------------------------------------------
# Locate the evidence. Build two Path objects from HERE with the / operator:
#   log_path    ->  the flight_log.csv file
#   voice_path  ->  the voice_recorder.txt file
#                               example:  manifest = HERE / "cargo.csv"



# -- OBJECTIVE 2 -------------------------------------------------------------
# Write read_lines(path): open the file with `with open(...)`, and return a
# list of its lines with whitespace stripped from both ends. Skip lines that
# are blank (or only spaces) after stripping.
#   a file containing "  alpha \\n\\n beta\\n"  ->  ["alpha", "beta"]
#   an empty file                              ->  []



# -- OBJECTIVE 3 -------------------------------------------------------------
# Write load_flight_log(path): read the CSV with csv.DictReader and return a
# list with one dict per row. Convert "t", "altitude" and "speed" to int;
# keep "event" as the text it is (it may be "" or contain commas).
#   t,altitude,speed,event
#   0,900,300,"BURN, HARD"   ->  [{"t": 0, "altitude": 900, "speed": 300,
#                                  "event": "BURN, HARD"}]
# The grader will reorder the columns, so find them by NAME.



# -- OBJECTIVE 4 // CORRUPTED CODE ---------------------------------------------
# write_transcript(lines, path) should save each line on its OWN line, and
# saving again must REPLACE the file, never pile up a second copy.
# It has TWO bugs. Call it twice on the same file, open the file, and look.
def write_transcript(lines, path):
    with open(path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line)


# -- OBJECTIVE 5 -------------------------------------------------------------
# Write export_events(rows, path): take rows like load_flight_log returns and
# write a CSV with csv.writer. First the header row  t,event  then one row
# [t, event] for every row whose event is not "". Return how many event rows
# you wrote (don't count the header).
# Open it with  "w", newline="", encoding="utf-8"  (see the manual).
#   2 rows, one with event "IMPACT"  ->  file is  t,event / 108,IMPACT  -> returns 1



# -- OBJECTIVE 6 -------------------------------------------------------------
# Pull the evidence before TOMBSTONE fires. Using YOUR functions:
#   flight   = the flight log loaded from log_path
#   voice    = the voice recording's lines, read from voice_path
#   unknown  = only the lines of `voice` that contain "UNKNOWN:"
# Then save it all to disk, next to this file:
#   write `unknown` to  HERE / "recovered_voice.txt"   with write_transcript
#   export `flight` to  HERE / "flight_events.csv"     with export_events



# -- OBJECTIVE 7 -------------------------------------------------------------
# Play back the unknown speaker: print every line in `unknown`, in order.

''',
    dialogue={
        "intro": [
            {"speaker": "rust", "mood": "neutral",
             "text": "HALCYON-9. Order transport, Foundry run. I sold that crew their flight seats. Nobody walked away."},
            {"speaker": "cipher", "mood": "alarm",
             "text": "TOMBSTONE is counting down. Copy both files out of the recorder before it wipes them, {callsign}."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Open, read, close. 'with open' does the closing for you, even if the code falls over halfway."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "FileNotFoundError means the path is wrong, not the file. Build it from HERE."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "CSV values arrive as text. int(\"12\") before you do any maths on them."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "Box is fine. Your script's the thing on fire. Read the log."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader writes its own files for your functions. Hard-wire a filename and they fail."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Mode \"w\" replaces, mode \"a\" adds. And write() never adds the newline for you."}],
            [{"speaker": "rust", "mood": "neutral",
              "text": "Splitting CSV on commas? Half those events have commas in them. Use the csv module."}],
            [{"speaker": "nova", "mood": "alarm",
              "text": "TOMBSTONE's still ticking, {callsign}. Fix the red layer and pull again."}],
        ],
        "victory": [
            {"speaker": "cipher", "mood": "neutral",
             "text": "Both files are on disk. TOMBSTONE can wipe the box now; the evidence is ours."},
            {"speaker": "cipher", "mood": "alarm",
             "text": "I ran the unknown speaker against your voiceprint. Ninety-nine point seven percent. It's you, {callsign}."},
            {"speaker": "rust", "mood": "neutral",
             "text": "You warning a crew about poisoned cargo. Before you woke up. I don't like ghosts."},
            {"speaker": "nova", "mood": "alarm",
             "text": "Ops flash: the Foundry's failsafes just went dark. Somebody doesn't want us in there."},
        ],
    },
)


# ── grader reference data ───────────────────────────────────────────────────────

def _ref_log(text: str) -> list[dict]:
    rows = []
    for row in csv.DictReader(io.StringIO(text, newline="")):
        rows.append({"t": int(row["t"]), "altitude": int(row["altitude"]),
                     "speed": int(row["speed"]), "event": row["event"]})
    return rows


def _ref_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


EXPECTED_FLIGHT = _ref_log(FLIGHT_LOG)
EXPECTED_VOICE = _ref_lines(VOICE_RECORDER)
EXPECTED_UNKNOWN = [line for line in EXPECTED_VOICE if "UNKNOWN:" in line]


# ── grader helpers ──────────────────────────────────────────────────────────────

def _top_level(ctx, name: str):
    found = [n for n in ctx.tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return found[-1] if found else None


def _func(ctx, name: str, signature: str):
    fn = ctx.ns.get(name)
    if callable(fn):
        return fn
    if ctx.crashed and _top_level(ctx, name):
        raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                   "Fix the crash in the COMBAT LOG first.")
    raise Fail(f"No function named `{name}` found.", hint=f"Define it at the left edge:  def {signature}:")


def _hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, FileNotFoundError):
        return "Use the `path` parameter you were given. Don't build your own filename inside the function."
    if isinstance(exc, KeyError):
        return "DictReader's keys come from the header row. Check the column name's spelling."
    if isinstance(exc, ValueError) and "invalid literal" in msg:
        return "Only convert the number columns (t, altitude, speed). The event column is text."
    if isinstance(exc, IndexError):
        return "Rows have different lengths. Look columns up by name with csv.DictReader, not by position."
    if isinstance(exc, TypeError) and "write() argument" in msg:
        return "write() only takes text. Convert first, or use csv.writer, which converts numbers for you."
    if isinstance(exc, (io.UnsupportedOperation, PermissionError)):
        return "Check the mode: \"r\" to read, \"w\" to write."
    return "Call the function on a small file of your own and read the full error."


def _call(label: str, fn, *args):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)
    except Fail:
        raise
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}", hint=_hint(exc))


@contextlib.contextmanager
def _scratch(ctx):
    """A throwaway folder INSIDE the mission folder for the grader's own test files."""
    home = Path(ctx.ns.get("__file__") or ".").resolve().parent
    with tempfile.TemporaryDirectory(prefix=".grader-blackbox-", dir=home) as tmp:
        yield Path(tmp)


def _write(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("utf-8"))
    return path


def _bare_opens(tree: ast.AST) -> list[int]:
    """Line numbers of open(...) calls that aren't the subject of a `with` statement."""
    managed = {id(item.context_expr) for node in ast.walk(tree) if isinstance(node, (ast.With, ast.AsyncWith))
               for item in node.items}
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and id(node) not in managed:
            f = node.func
            if (isinstance(f, ast.Name) and f.id == "open") or (isinstance(f, ast.Attribute) and f.attr == "open"):
                lines.append(node.lineno)
    return sorted(lines)


def _on_disk(ctx, name: str, expected: str) -> None:
    path = Path(ctx.ns.get("__file__") or ".").resolve().parent / name
    if not path.exists():
        raise Fail(f"`{name}` is missing from the mission folder.",
                   hint="Restart the mission (or hack again): the game restores missing black-box files.")
    if path.read_text(encoding="utf-8").replace("\r\n", "\n") != expected:
        raise Fail(f"`{name}` was changed. That's the evidence; it has to stay exactly as the recorder left it.",
                   hint=f"Delete {name} and hack again: the game restores the original.")


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Locate the evidence — `log_path` and `voice_path`")
def _paths(ctx):
    here = ctx.get("HERE")
    if not isinstance(here, Path):
        raise Fail("`HERE` is no longer a Path.", hint="Keep the starter's line:  HERE = Path(__file__).parent")
    for var, filename in (("log_path", "flight_log.csv"), ("voice_path", "voice_recorder.txt")):
        value = ctx.get(var)
        if isinstance(value, str):
            raise Fail(f"`{var}` is a str, not a Path.",
                       hint=f'Build it with the / operator:  {var} = HERE / "{filename}"')
        if not isinstance(value, Path):
            raise Fail(f"`{var}` is {type(value).__name__}, but it needs to be a Path.",
                       hint=f'{var} = HERE / "{filename}"')
        if value.name != filename:
            raise Fail(f"`{var}` points at {value.name!r}, but the file is called {filename!r}.",
                       hint="Check the spelling and the extension: the name must match exactly.")
        if not ctx.derived_from(var, "HERE"):
            raise Fail(f"`{var}` isn't built from HERE. A bare filename breaks when you run Python from another folder.",
                       hint=f'{var} = HERE / "{filename}"')
        if not value.exists():
            raise Fail(f"`{var}` is {value}, but there's no file there.",
                       hint="Build it from HERE, which is the folder the black box files are in.")
    _on_disk(ctx, "flight_log.csv", FLIGHT_LOG)
    _on_disk(ctx, "voice_recorder.txt", VOICE_RECORDER)


@MISSION.check("Read the recording — `read_lines()`")
def _read_lines(ctx):
    fn = _func(ctx, "read_lines", "read_lines(path)")
    cases = [
        ("  alpha  \n\n beta\n\t\ngamma", ["alpha", "beta", "gamma"], "a file whose last line has no newline"),
        ("", [], "an empty file"),
        ("\n   \n\t\n", [], "a file of only blank lines"),
        ("[T+001] RELAY: Ω-band open.\n", ["[T+001] RELAY: Ω-band open."], "a one-line file"),
    ]
    with _scratch(ctx) as tmp:
        for i, (text, expected, label) in enumerate(cases):
            path = _write(tmp / f"probe_{i}.txt", text)
            arg = str(path) if i == 1 else path   # paths may arrive as str or Path
            got = _call(f"read_lines(...) on {label}", fn, arg)
            if got is None:
                raise Fail("read_lines() returned None.", hint="Build a list inside the function and `return` it.")
            if not isinstance(got, list):
                raise Fail(f"read_lines() returned {type(got).__name__}, expected a list of lines.")
            if got != expected:
                hint = "Strip each line with .strip() and skip the ones that are empty afterwards."
                if any(isinstance(g, str) and g.endswith("\n") for g in got):
                    hint = "Each line read from a file still ends in \"\\n\". .strip() removes it."
                elif "" in got:
                    hint = "Skip lines that are empty after stripping:  if clean:"
                raise Fail(f"On {label} ({text!r}), read_lines() returned {got!r}, expected {expected!r}.", hint=hint)
    bare = _bare_opens(ctx.tree)
    if bare:
        raise Fail(f"Line {bare[0]} opens a file without `with`. If anything crashes before close(), the file stays open.",
                   hint="Write it as  with open(path, ...) as f:  and indent the code that uses f.")


@MISSION.check("Decode the telemetry — `load_flight_log()` with csv")
def _load(ctx):
    fn = _func(ctx, "load_flight_log", "load_flight_log(path)")
    probe = 't,altitude,speed,event\n0,900,300,"BURN, HARD"\n5,850,310,\n10,0,0,IMPACT\n'
    expected = [{"t": 0, "altitude": 900, "speed": 300, "event": "BURN, HARD"},
                {"t": 5, "altitude": 850, "speed": 310, "event": ""},
                {"t": 10, "altitude": 0, "speed": 0, "event": "IMPACT"}]
    shuffled = 'event,speed,t,altitude\n"SAY ""AGAIN""",120,3,75\nSILENCE,0,9,0\n'
    expected_shuffled = [{"t": 3, "altitude": 75, "speed": 120, "event": 'SAY "AGAIN"'},
                         {"t": 9, "altitude": 0, "speed": 0, "event": "SILENCE"}]
    with _scratch(ctx) as tmp:
        got = _call("load_flight_log(...) on a 3-row log", fn, _write(tmp / "probe.csv", probe))
        if not isinstance(got, list):
            raise Fail(f"load_flight_log() returned {type(got).__name__}, expected a list of dicts.",
                       hint="Collect each row into a list and return it.")
        if len(got) == len(expected) + 1:
            raise Fail("You got one row too many: the header line was treated as data.",
                       hint="csv.DictReader reads the header for you and uses it as the dict keys.")
        if got and isinstance(got[0], dict) and isinstance(got[0].get("t"), str):
            raise Fail(f"The first row came back as {got[0]!r}. Its numbers are still text.",
                       hint='Convert the number columns:  int(row["t"]), and the same for altitude and speed.')
        if got != expected:
            hint = "Use csv.DictReader and convert t, altitude and speed with int()."
            if any(isinstance(r, dict) and isinstance(r.get("event"), str) and r["event"] != "BURN, HARD"
                   and "BURN" in r["event"] for r in got):
                hint = 'A quoted field like "BURN, HARD" contains a comma. split(",") cuts it in two; csv doesn\'t.'
            if len(got) == len(expected):
                i = next(i for i, (a, b) in enumerate(zip(got, expected)) if a != b)
                raise Fail(f"On a 3-row log, row {i} came back as {got[i]!r}, expected {expected[i]!r}.", hint=hint)
            raise Fail(f"On a 3-row log, load_flight_log() returned {len(got)} rows, expected 3.", hint=hint)
        got = _call("load_flight_log(...) on a log with its columns reordered", fn, _write(tmp / "shuffled.csv", shuffled))
        if got != expected_shuffled:
            raise Fail(f"With the columns in a different order, load_flight_log() returned {got!r}, "
                       f"expected {expected_shuffled!r}.",
                       hint="Find columns by name with csv.DictReader:  row[\"altitude\"], not row[1].")
        got = _call("load_flight_log(...) on a header-only file", fn, _write(tmp / "empty.csv", "t,altitude,speed,event\n"))
        if got != []:
            raise Fail(f"A log with a header and no rows should give [], but got {got!r}.")


@MISSION.check("Repair the transcript writer — `write_transcript()`")
def _transcript(ctx):
    fn = _func(ctx, "write_transcript", "write_transcript(lines, path)")
    with _scratch(ctx) as tmp:
        target = tmp / "transcript.txt"
        _call('write_transcript(["alpha", "beta"], path)', fn, ["alpha", "beta"], target)
        if not target.exists():
            raise Fail("write_transcript() didn't create the file.", hint="Open `path` for writing:  open(path, \"w\", ...)")
        first = target.read_text(encoding="utf-8")
        if first == "alphabeta":
            raise Fail('Writing ["alpha", "beta"] produced the single line "alphabeta".',
                       hint="write() doesn't add a newline. Add \"\\n\" to the end of each line you write.")
        if first not in ("alpha\nbeta\n", "alpha\nbeta"):
            raise Fail(f'Writing ["alpha", "beta"] produced {first!r}, expected "alpha\\nbeta\\n".',
                       hint="Write each line followed by \"\\n\".")
        _call('write_transcript(["gamma"], same path)', fn, ["gamma"], target)
        second = target.read_text(encoding="utf-8")
        if "alpha" in second:
            raise Fail(f"After saving [\"gamma\"] to the same file, it contains {second!r}. The old transcript piled up.",
                       hint='Mode "a" appends to whatever is there. Mode "w" starts the file fresh.')
        if second.rstrip("\n") != "gamma":
            raise Fail(f'Saving ["gamma"] produced {second!r}, expected "gamma\\n".')
        _call("write_transcript([], same path)", fn, [], target)
        if target.read_text(encoding="utf-8").strip():
            raise Fail("Saving an empty transcript should leave an empty file.")
        lines = ["[T+1] A", "[T+2] B, with a comma", "[T+3] C"]
        _call("write_transcript(three lines, path)", fn, lines, target)
        back = target.read_text(encoding="utf-8").splitlines()
        if back != lines:
            raise Fail(f"Reading back three saved lines gave {back!r}, expected {lines!r}.")


@MISSION.check("Export the event table — `export_events()` with csv.writer")
def _export(ctx):
    fn = _func(ctx, "export_events", "export_events(rows, path)")
    rows = [{"t": 0, "altitude": 900, "speed": 300, "event": "BURN, HARD"},
            {"t": 5, "altitude": 850, "speed": 310, "event": ""},
            {"t": 7, "altitude": 600, "speed": 305, "event": 'SAY "AGAIN"'},
            {"t": 10, "altitude": 0, "speed": 0, "event": "IMPACT"}]
    expected = [["t", "event"], ["0", "BURN, HARD"], ["7", 'SAY "AGAIN"'], ["10", "IMPACT"]]
    with _scratch(ctx) as tmp:
        target = tmp / "events.csv"
        count = _call("export_events(4 rows, path)", fn, [dict(r) for r in rows], target)
        if not target.exists():
            raise Fail("export_events() didn't create the file.", hint='with open(path, "w", newline="", encoding="utf-8") as f:')
        with open(target, newline="", encoding="utf-8") as f:
            back = list(csv.reader(f))
        if back and back[0] != ["t", "event"]:
            raise Fail(f"The first row of the file is {back[0]!r}, expected the header ['t', 'event'].",
                       hint='Write the header first:  writer.writerow(["t", "event"])')
        if back != expected:
            hint = "Write one [t, event] row per row whose event isn't empty, with csv.writer."
            if any(r == ["5", ""] for r in back):
                hint = "Rows with an empty event shouldn't be exported:  if row[\"event\"]:"
            elif len(back) != len(expected) or any(len(r) != 2 for r in back):
                hint = "Events contain commas and quotes. csv.writer quotes them for you; joining with \",\" doesn't."
            raise Fail(f"Reading the exported file back gave {back!r}, expected {expected!r}.", hint=hint)
        if count is None:
            raise Fail("export_events() wrote the file but returned None.",
                       hint="Count the event rows you write and `return` the count.")
        if count != 3:
            raise Fail(f"export_events() wrote 3 event rows but returned {count!r}.",
                       hint="Return the number of event rows, not counting the header.")
        again = _call("export_events(1 row, same path)", fn, [{"t": 108, "altitude": 0, "speed": 0, "event": "IMPACT"}], target)
        with open(target, newline="", encoding="utf-8") as f:
            back = list(csv.reader(f))
        if back != [["t", "event"], ["108", "IMPACT"]] or again != 1:
            raise Fail(f"Exporting again to the same file gave {back!r} (returned {again!r}). The new export should replace the old one.",
                       hint='Open the file with mode "w" so every export starts fresh.')


@MISSION.check("Pull the evidence — `flight`, `voice`, `unknown` saved to disk")
def _evidence(ctx):
    flight = ctx.get("flight")
    if flight != EXPECTED_FLIGHT:
        if not isinstance(flight, list) or len(flight) != len(EXPECTED_FLIGHT):
            size = len(flight) if isinstance(flight, (list, tuple, dict, str)) else "?"
            raise Fail(f"`flight` has {size} rows, but the recorder's log has {len(EXPECTED_FLIGHT)}.",
                       hint="flight = load_flight_log(log_path)")
        i = next(i for i, (a, b) in enumerate(zip(flight, EXPECTED_FLIGHT)) if a != b)
        raise Fail(f"Row {i} of `flight` is {flight[i]!r}, but the log says {EXPECTED_FLIGHT[i]!r}.",
                   hint="flight = load_flight_log(log_path), and fix load_flight_log first if its layer is red.")
    if not ctx.derived_from("flight", "log_path"):
        raise Fail("`flight` isn't loaded from log_path.", hint="flight = load_flight_log(log_path)")
    voice = ctx.get("voice")
    if voice != EXPECTED_VOICE:
        raise Fail("`voice` doesn't match the recording's non-blank lines.", hint="voice = read_lines(voice_path)")
    if not ctx.derived_from("voice", "voice_path"):
        raise Fail("`voice` isn't read from voice_path.", hint="voice = read_lines(voice_path)")
    unknown = ctx.get("unknown")
    if unknown != EXPECTED_UNKNOWN:
        raise Fail(f"`unknown` has {len(unknown) if isinstance(unknown, list) else '?'} lines; the recording has "
                   f"{len(EXPECTED_UNKNOWN)} from the unknown speaker.",
                   hint='Keep only the lines of voice where  "UNKNOWN:" in line')
    if not ctx.derived_from("unknown", "voice"):
        raise Fail("`unknown` was typed in, not filtered out of `voice`. TOMBSTONE flags forged evidence.",
                   hint='Filter it:  [line for line in voice if "UNKNOWN:" in line]')
    home = Path(ctx.ns.get("__file__") or ".").resolve().parent
    saved = home / "recovered_voice.txt"
    if not saved.exists():
        raise Fail("recovered_voice.txt isn't in the mission folder.",
                   hint='write_transcript(unknown, HERE / "recovered_voice.txt")')
    if saved.read_text(encoding="utf-8").splitlines() != EXPECTED_UNKNOWN:
        raise Fail("recovered_voice.txt doesn't hold the unknown speaker's lines, one per line.",
                   hint="Save `unknown` with your repaired write_transcript().")
    events = home / "flight_events.csv"
    if not events.exists():
        raise Fail("flight_events.csv isn't in the mission folder.", hint='export_events(flight, HERE / "flight_events.csv")')
    with open(events, newline="", encoding="utf-8") as f:
        back = list(csv.reader(f))
    wanted = [["t", "event"]] + [[str(r["t"]), r["event"]] for r in EXPECTED_FLIGHT if r["event"]]
    if back != wanted:
        raise Fail("flight_events.csv doesn't match the flight log's events.",
                   hint="Export `flight` with your export_events().")


@MISSION.check("Play back the unknown speaker")
def _playback(ctx):
    if not ctx.stdout.strip():
        if ctx.crashed:
            raise Fail("Nothing was played back. Your script crashed before the print().")
        raise Fail("Nothing was printed.", hint="for line in unknown:  print(line)")
    lines = [line.strip() for line in ctx.stdout.splitlines() if line.strip()]
    found = [line for line in lines if line in EXPECTED_UNKNOWN]
    if found != EXPECTED_UNKNOWN:
        missing = next((u for u in EXPECTED_UNKNOWN if u not in lines), None)
        if missing:
            raise Fail(f"The playback is missing {missing!r}.", hint="Print every line of `unknown`, one print() each.")
        raise Fail("The unknown speaker's lines were printed out of order.", hint="Loop over `unknown` from start to end.")
    uses_unknown = ctx.call_uses("print", "unknown") or any(
        isinstance(n, ast.For) and isinstance(n.iter, ast.Name) and n.iter.id == "unknown" for n in ast.walk(ctx.tree))
    if not uses_unknown:
        raise Fail("Your playback doesn't read from `unknown`. Don't retype the recording.",
                   hint="for line in unknown:  print(line)")
