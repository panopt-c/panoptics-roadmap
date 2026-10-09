"""LEVEL 16 // DATA STREAMS — json loads/dumps, nested data, list-of-dicts transforms, sort by key."""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

from engine.mission import Fail, Mission

STREAM_FILE = "oracle_stream.json"
REPORT_FILE = "intercept_report.json"

# The intercepted burst. Packet order is deliberate: two PURGE orders share priority 5 and the
# later timestamp comes FIRST in the file, so a sort without a tie-break gives the wrong order.
STREAM_JSON = """\
{
  "header": {"origin": "ORACLE", "relay": "HYDRA-7", "sector": "ARCHIVE",
             "seq": 4471, "encrypted": false, "operator": null},
  "packets": [
    {"id": "PK-301", "ts": 1006, "priority": 2,
     "route": {"from": "ARCHIVE-3", "to": "CORE"},
     "body": {"cmd": "INDEX", "target": "stack-12"}, "tags": ["routine"]},
    {"id": "PK-302", "ts": 1008, "priority": 5,
     "route": {"from": "CORE", "to": "ARCHIVE-1"},
     "body": {"cmd": "PURGE", "target": "monastery-index"}, "tags": ["deletion", "priority"]},
    {"id": "PK-303", "ts": 1002, "priority": 3,
     "route": {"from": "ARCHIVE-1", "to": "CORE"},
     "body": {"cmd": "INDEX"}, "tags": []},
    {"id": "PK-304", "ts": 1007, "priority": 4,
     "route": {"from": "CORE", "to": "ARCHIVE-3"},
     "body": {"cmd": "SEAL", "target": "project-loom"}, "tags": ["sealed"]},
    {"id": "PK-305", "ts": 1004, "priority": 5,
     "route": {"from": "CORE", "to": "ARCHIVE-9"},
     "body": {"cmd": "PURGE", "target": "operator-records"}, "tags": ["deletion", "sealed"]},
    {"id": "PK-306", "ts": 1003, "priority": 1,
     "route": {"from": "ARCHIVE-9", "to": "CORE"},
     "body": {"cmd": "HEARTBEAT"}},
    {"id": "PK-307", "ts": 1001, "priority": 4,
     "route": {"from": "CORE", "to": "ARCHIVE-9"},
     "body": {"cmd": "PURGE", "target": "ghost-mirrors"}, "tags": ["deletion"]},
    {"id": "PK-308", "ts": 1009, "priority": 2,
     "route": {"from": "ARCHIVE-3"},
     "body": {"cmd": "INDEX", "target": "stack-40"}, "tags": ["routine"]}
  ]
}
"""
PAYLOAD = json.loads(STREAM_JSON)

MISSION = Mission(
    id="L16",
    slug="level_16_data_streams",
    title="DATA STREAMS",
    concept="JSON & nested data",
    enemy="HYDRA.relay",
    xp=310,
    par_seconds=35 * 60,
    tier=4,
    concepts=("json", "dicts", "sorting"),
    enemy_art="""\
 ▄█▄    ▄█▄    ▄█▄
 ▀█▀▄  ▄▀█▀▄  ▄▀█▀
   ▀█▄█▀ ▀█▄█▀
     ▀██▄▄▄██▀
   ▄▄▄███████▄▄▄
  ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀""",
    briefing="""\
The Forgemaster's dataset carried your signature. The Order wants to know why, and there is
only one place that remembers: **the Archive**, the Core's drowned library, stacked kilometres
deep under the Dead Zone.

The ORACLE talks to its Archive in streams of JSON: text shaped like dictionaries, nested
inside lists, inside dictionaries. **HYDRA.relay** carries the traffic. Cut one head and two
more rotate in, re-keying every few seconds.

CIPHER has tapped a single burst and saved it to `oracle_stream.json`. Somewhere in those
packets is a list of what the ORACLE plans to delete next.

**Decode the burst, rank the purge orders, and send the Monastery a clean report before HYDRA re-keys.**
""",
    why="""\
Almost every API an AI engineer touches speaks JSON. Ask an LLM a question over HTTP and the
answer comes back as text that you turn into nested dicts and lists:

```python
import json

body = '{"choices": [{"message": {"content": "Hello"}}], "usage": {"total_tokens": 12}}'
reply = json.loads(body)
text = reply["choices"][0]["message"]["content"]   # "Hello"
tokens = reply["usage"]["total_tokens"]            # 12
```

Then you flatten those records, filter them, sort them and count them. That's what you do when
you log thousands of model calls or rank search results. Finally, `json.dumps` turns your
Python data back into text for the next service. You'll use these steps in nearly every AI
pipeline you build: *decode, reshape, encode*.
""",
    manual="""\
**1 · JSON is text. `json.loads` turns it into Python.** (`loads` = *load string*.)

```python
import json
raw = '{"name": "HYDRA", "heads": 7, "active": true, "owner": null, "tags": ["relay"]}'
data = json.loads(raw)
data["heads"] + 1        # 8, a real int now
```

| JSON | Python |
|---|---|
| `{...}` object | `dict` |
| `[...]` array | `list` |
| `"text"` | `str` |
| `7`, `0.5` | `int`, `float` |
| `true` / `false` | `True` / `False` |
| `null` | `None` |

**2 · Walk nested data one key at a time.** Each `[...]` steps one level deeper. Use
`.get(key, default)` when a field is optional. To reach into an optional *dictionary*, give
`.get` an empty dict as its default, so the second `.get` still works:

```python
drone = {"id": "D-1", "gps": {"lat": 51.2}, "crew": ["Ines"]}
drone["gps"]["lat"]                       # 51.2
drone["crew"][0]                          # "Ines"
drone.get("cargo", [])                    # [] (the key is missing)
drone.get("gps", {}).get("alt")           # None (inner key missing)
drone.get("radio", {}).get("band")        # None (outer key missing too)
```

**3 · Reshape a list of dicts with a loop or a comprehension.** Return *new* dicts and lists.
Don't edit the ones you were given:

```python
crews = [{"id": "D-1", "size": 3}, {"id": "D-2", "size": 1}, {"id": "D-3", "size": 3}]
big = [c for c in crews if c["size"] == 3]          # filter
ids = [c["id"] for c in big]                        # ["D-1", "D-3"]
field = "size"
same = [c for c in crews if c[field] == 1]          # the key can be a variable
```

**4 · Sort by a key.** `sorted()` returns a NEW list and leaves the original alone, while
`list.sort()` reorders the list in place and returns `None`. `key=` says what to sort by.
To sort by two things, return a tuple. Negate a number to flip that part to high-to-low:

```python
by_size = sorted(crews, key=lambda c: c["size"])               # low to high
biggest = sorted(crews, key=lambda c: c["size"], reverse=True) # high to low
ranked = sorted(crews, key=lambda c: (-c["size"], c["id"]))    # size high→low, then id A→Z
```

**5 · Count by a field.** Start an empty dict and add one per record:

```python
counts = {}
for c in crews:
    counts[c["size"]] = counts.get(c["size"], 0) + 1     # {3: 2, 1: 1}
```

**6 · Back to text with `json.dumps`.** (`dumps` = *dump string*.) `str()` is NOT JSON:
it writes Python's own notation, with single quotes and `None`, which other programs reject.

```python
str({"ok": True, "x": None})          # "{'ok': True, 'x': None}"  (not JSON)
json.dumps({"ok": True, "x": None})   # '{"ok": true, "x": null}'  (JSON)
json.dumps(data, indent=2)            # pretty, one field per line

from pathlib import Path
Path("out.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
```
""",
    starter='''
"""
==============================================================================
  LEVEL 16 // DATA STREAMS                             TARGET: HYDRA.relay
==============================================================================
  CIPHER tapped one burst of ORACLE traffic into oracle_stream.json (it sits
  next to this file). Decode it, reshape it, rank it, and re-encode it.
  The grader also feeds your functions FRESH packets it intercepts itself,
  so they have to work for any packet, not just these eight.
"""
import json
from pathlib import Path

raw = Path("oracle_stream.json").read_text(encoding="utf-8")   # the burst, as TEXT


# -- OBJECTIVE 1 -------------------------------------------------------------
# `raw` is one long string. Create `stream` by decoding it with json.loads,
# so it becomes real Python dicts and lists.
#                                 example:  data = json.loads(text)



# -- OBJECTIVE 2 -------------------------------------------------------------
# Read three fields from the burst's "header" dict into variables:
#   `origin`    the header's "origin"
#   `relay`     the header's "relay"
#   `operator`  the header's "operator"  (look at what JSON's null becomes)
#                                 example:  lat = drone["gps"]["lat"]



# -- OBJECTIVE 3 -------------------------------------------------------------
# Finish flatten(packet): turn ONE nested packet into a flat dict with
# exactly these 7 keys:
#   "id", "ts", "priority"   copied from the packet
#   "cmd"                    packet["body"]["cmd"]
#   "target"                 the body's "target", or None if it has none
#   "dst"                    the route's "to", or None. Some packets have no
#                            route at all.
#   "tags"                   the packet's "tags" list, or [] if it has none
# Don't change the packet you were given; build a new dict.
#   flatten({"id": "PK-1", "ts": 5, "priority": 2, "route": {"from": "CORE"},
#            "body": {"cmd": "INDEX"}})
#   -> {"id": "PK-1", "ts": 5, "priority": 2, "cmd": "INDEX",
#       "target": None, "dst": None, "tags": []}
def flatten(packet):
    pass  # replace with your code


# -- OBJECTIVE 4 -------------------------------------------------------------
# Finish select(records, field, value): return a NEW list of the records
# whose `field` equals `value`, in their original order.
#   select(records, "cmd", "PURGE")  -> only the PURGE records
#   select(records, "dst", None)     -> records with no destination
def select(records, field, value):
    pass  # replace with your code


# -- OBJECTIVE 5 -------------------------------------------------------------
# Finish rank(records): return a NEW list sorted by "priority" from HIGH
# to LOW. When two records share a priority, the EARLIER "ts" goes first.
# Leave the list you were given in its original order.
#   priorities/ts  (5, 9) (2, 1) (5, 3)  ->  (5, 3) (5, 9) (2, 1)
def rank(records):
    pass  # replace with your code


# -- OBJECTIVE 6 -------------------------------------------------------------
# Finish tally(records, field): return a dict counting how many records
# have each value of `field`.
#   tally(records, "cmd")  ->  {"INDEX": 3, "PURGE": 3, ...}
#   tally([], "cmd")       ->  {}
def tally(records, field):
    pass  # replace with your code


# -- OBJECTIVE 7 -------------------------------------------------------------
# Use your functions on the real burst:
#   `records`  flatten() every packet in stream["packets"] (a list of 8)
#   `purges`   the "PURGE" records, ranked with rank()
#   `report`   a dict with exactly these keys:
#       "origin"       origin
#       "relay"        relay
#       "packets"      how many records there are
#       "commands"     tally of records by "cmd"
#       "purge_order"  the "target" of each record in purges, in ranked order



# -- OBJECTIVE 8 // CORRUPTED CODE --------------------------------------------
# The Monastery's receiver only accepts JSON. This line "encodes" the report
# with str(), and the receiver keeps rejecting it. Fix it so `wire` holds
# real JSON text made from `report`. Then broadcast it with print(wire).
wire = str(report)



# -- OBJECTIVE 9 -------------------------------------------------------------
# Archive the intercept for the Order: write `report` to the file
# intercept_report.json as PRETTY JSON (indent=2), next to this file.
#    example:  Path("out.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

''',
    assets={STREAM_FILE: STREAM_JSON},
    dialogue={
        "intro": [
            {"speaker": "nova", "mood": "neutral",
             "text": "Ops update, {callsign}: Sector 3 is live. The Archive. Every byte the Core ever kept, stacked in the dark."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "The Forgemaster's data had your signature on it. If anything remembers why, it's down here."},
            {"speaker": "cipher", "mood": "alarm",
             "text": "I caught one burst from HYDRA before it re-keyed. It's JSON: text pretending to be a dictionary. Decode it."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "KeyError on a packet? Not every packet has every field. Optional keys need .get() with a default."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "JSONDecodeError means the text isn't valid JSON. json.loads wants the file's TEXT, not its name."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "TypeError: 'NoneType'... One of your functions isn't returning anything. Shocking. Read the line number."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader intercepts its own packets: some with no route, no tags, no target. Your code has to survive all of them."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "HYDRA's lost a head, {callsign}. Seven to go. Check the first red layer and keep the tempo."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Two orders with the same priority? The earlier timestamp wins. Your sort needs a tie-break."}],
            [{"speaker": "vex", "mood": "smirk",
              "text": "Still decoding? I'd have parsed that burst before HYDRA finished saying hello."}],
        ],
        "victory": [
            {"speaker": "cipher", "mood": "alarm",
             "text": "Purge order, top priority first: operator records. Then the Monastery's index. Then the ghost mirrors."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "And one SEAL: project-loom. The ORACLE is hiding something, and it's erasing everyone who'd remember it."},
            {"speaker": "nova", "mood": "warm",
             "text": "Report's in the Monastery feed, {callsign}. Clean JSON, zero rejects. Ops is impressed. I'm impressed."},
            {"speaker": "rust", "mood": "neutral",
             "text": "Ghost mirrors are old-net caches. If the ORACLE wants them gone, they're worth scraping. Fast."},
        ],
    },
)


# ── reference behaviour (what the grader expects) ───────────────────────────────

def _ref_flatten(packet: dict) -> dict:
    return {
        "id": packet["id"], "ts": packet["ts"], "priority": packet["priority"],
        "cmd": packet["body"]["cmd"], "target": packet["body"].get("target"),
        "dst": packet.get("route", {}).get("to"), "tags": list(packet.get("tags", [])),
    }


def _ref_select(records, field, value):
    return [r for r in records if r.get(field) == value]


def _ref_rank(records):
    return sorted(records, key=lambda r: (-r["priority"], r["ts"]))


def _ref_tally(records, field):
    counts: dict = {}
    for r in records:
        counts[r[field]] = counts.get(r[field], 0) + 1
    return counts


RECORDS = [_ref_flatten(p) for p in PAYLOAD["packets"]]
PURGES = _ref_rank(_ref_select(RECORDS, "cmd", "PURGE"))
REPORT = {
    "origin": PAYLOAD["header"]["origin"],
    "relay": PAYLOAD["header"]["relay"],
    "packets": len(RECORDS),
    "commands": _ref_tally(RECORDS, "cmd"),
    "purge_order": [r["target"] for r in PURGES],
}

# Fresh traffic the grader intercepts itself (never in the player's file).
FRESH_PACKETS = [
    {"id": "PK-900", "ts": 77, "priority": 4, "route": {"from": "CORE", "to": "STACK-2"},
     "body": {"cmd": "SEAL", "target": "vault-9"}, "tags": ["sealed", "audit"]},
    {"id": "PK-901", "ts": 3, "priority": 1, "route": {"from": "STACK-2"}, "body": {"cmd": "HEARTBEAT"}},
    {"id": "PK-902", "ts": 5, "priority": 2, "body": {"cmd": "INDEX", "target": "stack-1"}, "tags": []},
    {"id": "PK-903", "ts": 12, "priority": 5, "route": {"from": "ARCHIVE-2", "to": "CORE"},
     "body": {"cmd": "PURGE", "target": "lexicon", "reason": "redundant"}, "tags": ["deletion"],
     "checksum": "f00d"},
]


# ── grader helpers ──────────────────────────────────────────────────────────────

def _short(value, limit: int = 150) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _defined(ctx, name: str) -> bool:
    return any(isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name for n in ctx.tree.body)


def _function(ctx, name: str, signature: str):
    if name not in ctx.ns:
        if ctx.crashed and (_defined(ctx, name) or ctx.assignments(name)):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.", hint=f"Keep the starter's  def {signature}:  line.")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function anymore. Did a variable reuse its name?",
                   hint=f"Keep  def {signature}:  and pick a different name for the variable.")
    return fn


def _crash_hint(exc: BaseException) -> str:
    if isinstance(exc, KeyError):
        return ("That key is missing from this packet. Optional fields need .get(key, default); "
                "for the optional route, chain: packet.get(\"route\", {}).get(\"to\")")
    if isinstance(exc, TypeError) and "NoneType" in str(exc):
        return "Something is None. A function that ends without `return` gives back None."
    if isinstance(exc, AttributeError) and "get" in str(exc):
        return ".get() works on dicts. Check which level of the nested data you are holding."
    return "Call the function on this input at the bottom of your file and read the full error."


def _call(label: str, fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}", hint=_crash_hint(exc))


def _no_return_hint(got) -> str:
    return "Your function ended without `return`, so Python gave back None." if got is None else ""


def _calls(node: ast.AST, func: str) -> bool:
    """True if `node` contains a call to `func(...)` or `something.func(...)`."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if (isinstance(f, ast.Name) and f.id == func) or (isinstance(f, ast.Attribute) and f.attr == func):
                return True
    return False


def _assigned_with_call(ctx, name: str, func: str) -> bool:
    return any(_calls(value, func) for value in ctx.assignments(name))


def _mentions(ctx, name: str, *sources: str) -> bool:
    return any(ctx.derived_from(name, s) for s in sources)


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Decode the burst — `stream = json.loads(raw)`")
def _decode(ctx):
    value = ctx.get("stream")
    if isinstance(value, str):
        raise Fail("`stream` is still a string. Text that LOOKS like a dict is still just text.",
                   hint="json.loads(raw) reads the JSON text and builds real dicts and lists.")
    ctx.expect_type("stream", value, dict)
    if not ctx.derived_from("stream", "raw"):
        raise Fail("`stream` wasn't decoded from `raw`. Typing the data in by hand isn't decoding.",
                   hint="stream = json.loads(raw)")
    if value != PAYLOAD:
        raise Fail("`stream` doesn't match the intercepted burst. Something changed it after decoding.",
                   hint="Decode `raw` once and leave the result alone. A function that pops or assigns into a "
                        "packet (check flatten!) edits `stream` too: build NEW dicts instead.")


@MISSION.check("Read the nested header — `origin`, `relay`, `operator`")
def _header(ctx):
    header = PAYLOAD["header"]
    for name in ("origin", "relay", "operator"):
        value = ctx.get(name)
        if not ctx.derived_from(name, "stream"):
            raise Fail(f"`{name}` was typed in, not read from `stream`.",
                       hint=f'Step into the header:  {name} = stream["header"]["{name}"]')
        if value != header[name] or type(value) is not type(header[name]):
            if name == "operator" and value == "null":
                raise Fail('`operator` is the text "null". JSON\'s null becomes Python\'s None when decoded.',
                           hint="Read it from stream; json.loads already converted it for you.")
            raise Fail(f"`{name}` is {_short(value)}, but the header says {header[name]!r}.",
                       hint=f'Two steps down: stream["header"]["{name}"]')
    if ctx.ns.get("operator") is not None:
        raise Fail("`operator` should be None: JSON null decodes to Python None.")


@MISSION.check("Flatten packets — `flatten(packet)` on fresh intercepts")
def _flatten(ctx):
    fn = _function(ctx, "flatten", "flatten(packet)")
    for packet in FRESH_PACKETS:
        before = copy.deepcopy(packet)
        given = copy.deepcopy(packet)
        got = _call(f"flatten({packet['id']} packet)", fn, given)
        expected = _ref_flatten(before)
        if given != before:
            raise Fail(f"flatten() changed the {packet['id']} packet it was given.",
                       hint="Build and return a NEW dict; don't pop, delete or assign into `packet`.")
        if not isinstance(got, dict):
            raise Fail(f"flatten() returned {_short(got)} for packet {packet['id']}, not a dict.",
                       hint=_no_return_hint(got) or "Return a dict with the 7 keys from objective 3.")
        if set(got) != set(expected):
            missing = sorted(set(expected) - set(got))
            extra = sorted(set(got) - set(expected))
            raise Fail(f"flatten({packet['id']}) has the wrong keys. Missing: {missing or 'none'}; "
                       f"extra: {extra or 'none'}.", hint="Exactly: id, ts, priority, cmd, target, dst, tags.")
        for key in expected:
            if got[key] != expected[key] or type(got[key]) is not type(expected[key]):
                why = ""
                if key in ("target", "dst") and expected[key] is None:
                    why = " This packet has no such field, so the value should be None."
                elif key == "tags" and expected[key] == [] and "tags" not in packet:
                    why = " This packet has no tags at all, so use an empty list."
                raise Fail(f"flatten({packet['id']})[{key!r}] is {_short(got[key])}, expected "
                           f"{_short(expected[key])}.{why}",
                           hint='For optional fields: body.get("target"), packet.get("route", {}).get("to"), '
                                'packet.get("tags", []).')


@MISSION.check("Filter the stream — `select(records, field, value)`")
def _select(ctx):
    fn = _function(ctx, "select", "select(records, field, value)")
    records = [_ref_flatten(p) for p in FRESH_PACKETS] + [_ref_flatten(PAYLOAD["packets"][1])]
    cases = [(records, "cmd", "PURGE"), (records, "dst", None), (records, "priority", 4),
             (records, "cmd", "REBOOT"), ([], "cmd", "PURGE")]
    for recs, field, value in cases:
        given = copy.deepcopy(recs)
        got = _call(f"select(records, {field!r}, {value!r})", fn, given, field, value)
        expected = _ref_select(recs, field, value)
        if given != recs:
            raise Fail("select() changed the list it was given.", hint="Build a new list; don't remove items from `records`.")
        if got != expected or not isinstance(got, list):
            shown = [r["id"] for r in got] if isinstance(got, list) and all(isinstance(r, dict) and "id" in r for r in got) else got
            raise Fail(f"select(records, {field!r}, {value!r}) returned {_short(shown)}; expected the records "
                       f"{[r['id'] for r in expected]}.",
                       hint=_no_return_hint(got) or "Keep each record r where r[field] == value. The field name "
                                                    "is a variable, so write r[field], not r[\"field\"].")


@MISSION.check("Rank the orders — `rank(records)` by priority, then time")
def _rank(ctx):
    fn = _function(ctx, "rank", "rank(records)")
    tie = [{"id": "A", "priority": 5, "ts": 9}, {"id": "B", "priority": 2, "ts": 1},
           {"id": "C", "priority": 5, "ts": 3}, {"id": "D", "priority": 3, "ts": 2},
           {"id": "E", "priority": 2, "ts": 0}]
    fresh = [_ref_flatten(p) for p in FRESH_PACKETS]
    for recs in (tie, fresh, [], [{"id": "solo", "priority": 1, "ts": 1}]):
        given = copy.deepcopy(recs)
        got = _call("rank(records)", fn, given)
        if got is None and given != recs:
            raise Fail("rank() returned None and reordered the list it was given.",
                       hint="list.sort() sorts in place and returns None. sorted(records, key=...) returns a new list.")
        if given != recs:
            raise Fail("rank() reordered the caller's list. The original order must survive.",
                       hint="Use sorted(...), which makes a new list, instead of records.sort(...).")
        expected = _ref_rank(recs)
        if got != expected:
            got_ids = [r.get("id") for r in got] if isinstance(got, list) and all(isinstance(r, dict) for r in got) else got
            hint = _no_return_hint(got)
            if not hint and isinstance(got, list) and recs is tie:
                hint = ("Sort by a tuple: priority high→low, then ts low→high. "
                        "Negating the priority flips just that part: key=lambda r: (-r[...], r[...])")
            raise Fail(f"rank() gave the order {_short(got_ids)}; expected {[r['id'] for r in expected]}.",
                       hint=hint or "Sort by priority (high first), breaking ties with the earlier ts.")


@MISSION.check("Count the traffic — `tally(records, field)`")
def _tally(ctx):
    fn = _function(ctx, "tally", "tally(records, field)")
    fresh = [_ref_flatten(p) for p in FRESH_PACKETS] + [_ref_flatten(p) for p in PAYLOAD["packets"][:3]]
    for recs, field in ((fresh, "cmd"), (fresh, "priority"), (fresh, "dst"), ([], "cmd")):
        got = _call(f"tally(records, {field!r})", fn, copy.deepcopy(recs), field)
        expected = _ref_tally(recs, field)
        if got != expected or not isinstance(got, dict):
            raise Fail(f"tally(records, {field!r}) returned {_short(got)}; expected {_short(expected)}.",
                       hint=_no_return_hint(got) or "Start with counts = {} and add one per record: "
                                                    "counts[key] = counts.get(key, 0) + 1")


@MISSION.check("Assemble the intercept — `records`, `purges`, `report`")
def _report(ctx):
    records = ctx.get("records")
    if not _assigned_with_call(ctx, "records", "flatten") or not ctx.derived_from("records", "stream"):
        raise Fail("`records` must come from running flatten() over stream[\"packets\"].",
                   hint='records = [flatten(p) for p in stream["packets"]]')
    if records != RECORDS:
        raise Fail(f"`records` doesn't match the burst: expected 8 flat records, got {_short(records, 90)}.",
                   hint="Flatten every packet in stream[\"packets\"], in order.")
    purges = ctx.get("purges")
    if not _assigned_with_call(ctx, "purges", "rank"):
        raise Fail("`purges` must be ranked with your rank() function.",
                   hint='Select the PURGE records, then rank them: rank(select(records, "cmd", "PURGE"))')
    if purges != PURGES:
        ids = [r.get("id") for r in purges] if isinstance(purges, list) and all(isinstance(r, dict) for r in purges) else purges
        raise Fail(f"`purges` is {_short(ids)}; expected the PURGE records in ranked order {[r['id'] for r in PURGES]}.",
                   hint="Two PURGE orders share priority 5. rank() must break that tie with the earlier ts.")
    report = ctx.get("report")
    ctx.expect_type("report", report, dict)
    if not _mentions(ctx, "report", "records", "purges"):
        raise Fail("`report` was typed in by hand. HYDRA re-keys every few seconds; the report must be computed.",
                   hint="Build it from origin, relay, records and purges.")
    if set(report) != set(REPORT):
        raise Fail(f"`report` has keys {sorted(report)}; it needs exactly {sorted(REPORT)}.")
    for key, expected in REPORT.items():
        if report[key] != expected:
            raise Fail(f"report[{key!r}] is {_short(report[key])}; expected {_short(expected)}.",
                       hint="purge_order is a list of each ranked record's \"target\"." if key == "purge_order" else "")


@MISSION.check("Repair the encoder — `wire` is real JSON")
def _wire(ctx):
    wire = ctx.get("wire")
    ctx.expect_type("wire", wire, str)
    report = ctx.ns.get("report")
    if not ctx.derived_from("wire", "report"):
        raise Fail("`wire` must be encoded from `report`, not typed out.", hint="wire = json.dumps(report)")
    try:
        decoded = json.loads(wire)
    except ValueError:
        if isinstance(report, dict) and wire == str(report):
            raise Fail("`wire` is still str(report): Python notation with single quotes, not JSON. The receiver rejects it.",
                       hint="json.dumps(...) writes real JSON: double quotes, true/false, null.")
        raise Fail(f"`wire` isn't valid JSON: {_short(wire, 80)}", hint="Build it with json.dumps(report).")
    if decoded != report:
        raise Fail("`wire` decodes to something different from `report`.", hint="Encode the finished report: json.dumps(report)")
    if wire not in ctx.stdout:
        raise Fail("The JSON never went out. Broadcast it.", hint="print(wire)")


@MISSION.check("Archive the intercept — intercept_report.json")
def _archive(ctx):
    path = Path(ctx.ns.get("__file__", REPORT_FILE)).resolve().parent / REPORT_FILE
    if not path.exists():
        raise Fail(f"No {REPORT_FILE} next to your mission file yet.",
                   hint='Path("intercept_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")')
    text = path.read_text(encoding="utf-8")
    try:
        saved = json.loads(text)
    except ValueError:
        raise Fail(f"{REPORT_FILE} isn't valid JSON. Write json.dumps(...) output, not str(...).")
    if saved != ctx.ns.get("report"):
        raise Fail(f"{REPORT_FILE} doesn't contain your current `report`.",
                   hint="Write the file AFTER the report is built, from the report itself.")
    if "\n" not in text.strip():
        raise Fail(f"{REPORT_FILE} is all on one line. The Order reads these by hand.",
                   hint="json.dumps(report, indent=2) puts one field per line.")
