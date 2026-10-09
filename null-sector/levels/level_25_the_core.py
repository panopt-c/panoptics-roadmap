"""LEVEL 25 // BOSS: THE CORE — a tool-using AI agent with guardrails (the finale)."""
from __future__ import annotations

import ast
import copy
import json
import sys
import types

from engine.mission import Cutscene, Fail, Mission

# ── the evidence: what the Core deleted, and where its own loop came from ───────────
ARCHIVE_DATA = {
    "records": [
        {"id": "rec-001", "title": "Monastery Primer: Python for the Order", "author": "Mother Ada",
         "kind": "human", "sector": "monastery", "tags": ["teaching", "python"], "year": 2071},
        {"id": "rec-002", "title": "Cooling Tower Retrofit Plans", "author": "Brother Tomas Reyes",
         "kind": "human", "sector": "monastery", "tags": ["engineering"], "year": 2076},
        {"id": "rec-003", "title": "Lullabies for Server Rooms", "author": "Mara Quell",
         "kind": "human", "sector": "dead_zone", "tags": ["music"], "year": 2080},
        {"id": "rec-004", "title": "Foundry Drone Firmware v3", "author": "RUST",
         "kind": "human", "sector": "foundry", "tags": ["drones", "firmware"], "year": 2082},
        {"id": "rec-005", "title": "Grid Patrol Route Optimiser", "author": "VEX",
         "kind": "human", "sector": "grid", "tags": ["routes", "speed"], "year": 2083},
        {"id": "rec-006", "title": "The Rule of Source", "author": "Abbot Ilse Varga",
         "kind": "human", "sector": "dead_zone", "tags": ["Monastery", "ethics"], "year": 2074},
        {"id": "rec-007", "title": "Telemetry Shard 0x3F", "author": "core",
         "kind": "machine", "sector": "core", "tags": ["telemetry"], "year": 2086},
        {"id": "rec-008", "title": "Archive Index Rebuild", "author": "librarian",
         "kind": "machine", "sector": "archive", "tags": ["monastery", "index"], "year": 2087},
        {"id": "rec-009", "title": "Night Market Ledger", "author": "Old Fen",
         "kind": "human", "sector": "dead_zone", "tags": ["market"], "year": 2079},
        {"id": "rec-010", "title": "Field Notes on Kindness", "author": "Juno Park",
         "kind": "human", "sector": "grid", "tags": ["essays"], "year": 2081},
        {"id": "rec-011", "title": "Garden Irrigation Script", "author": "Brother Tomas Reyes",
         "kind": "human", "sector": "monastery", "tags": ["gardens"], "year": 2080},
        {"id": "rec-012", "title": "Foundry Safety Interlocks", "author": "Ines Aldana",
         "kind": "human", "sector": "foundry", "tags": ["safety"], "year": 2077},
        {"id": "rec-013", "title": "Loss Curves of 2085", "author": "optimizer.core",
         "kind": "machine", "sector": "core", "tags": ["training"], "year": 2085},
        {"id": "rec-014", "title": "Letters to the Monastery", "author": "Anonymous",
         "kind": "human", "sector": "dead_zone", "tags": ["letters", "MONASTERY"], "year": 2081},
        {"id": "rec-015", "title": "Arena Chant Book", "author": "VEX",
         "kind": "human", "sector": "grid", "tags": ["arena", "music"], "year": 2084},
        {"id": "rec-016", "title": "Bell Schedule, Year Nine", "author": "Brother Tomas Reyes",
         "kind": "human", "sector": "monastery", "tags": ["rites"], "year": 2083},
    ],
    "modules": {
        "core.train_loop": {"parent": "loom.v1", "author": "core"},
        "loom.v1": {"parent": "axon.1", "author": "operator-0"},
        "axon.1": {"parent": "notebook.2081", "author": "operator-0"},
        "notebook.2081": {"parent": "monastery.primer", "author": "operator-0"},
        "monastery.primer": {"parent": None, "author": "Mother Ada"},
        "archive.index": {"parent": "core.train_loop", "author": "librarian"},
        "drone.firmware": {"parent": "foundry.base", "author": "RUST"},
        "foundry.base": {"parent": None, "author": "Ines Aldana"},
        "core.objective": {"parent": "core.metric", "author": "core"},
        "core.metric": {"parent": "core.objective", "author": "core"},
    },
}
ARCHIVE_JSON = json.dumps(ARCHIVE_DATA, indent=2) + "\n"

CORE_API = r'''"""THE CORE // agent channel. A local mock of an LLM Messages API with tool use.
No network, deterministic, instant.

    reply = core_api.create(model=MODEL, max_tokens=1024, system=SYSTEM,
                            tools=TOOLS, messages=messages)

`reply` is a dict shaped like a real Messages API response:

    {"type": "message", "role": "assistant",
     "content": [{"type": "thinking", "thinking": ""},
                 {"type": "text", "text": "SHOW ME."},
                 {"type": "tool_use", "id": "toolu_01", "name": "search_archive",
                  "input": {"query": "monastery"}}],
     "stop_reason": "tool_use"}

stop_reason "tool_use" means: run these tools and send me the results.
stop_reason "end_turn" means: this is my final answer. Anything else
("max_tokens", "refusal", ...) means the answer is unfinished.

Like a real model API, the Core remembers NOTHING between calls: it re-reads the
whole `messages` list every time. After a "tool_use" reply, append

    {"role": "assistant", "content": reply["content"]}        # the whole list

then ONE user message holding a tool_result for EVERY tool_use block:

    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_01", "content": "<a string>"},
        {"type": "tool_result", "tool_use_id": "toolu_02", "content": "refused", "is_error": True}]}

A malformed request raises core_api.BadRequestError saying exactly what is wrong.
An agent that never stops gets cut off with core_api.RunawayError.
Do not edit this file: the grader uses its own copy of the Core.
"""
import json

MAX_CALLS = 25
REQUIRED_TOOLS = ("search_archive", "trace_lineage")


class BadRequestError(Exception):
    """The request broke the protocol (an HTTP 400 from a real API)."""


class RunawayError(Exception):
    """Too many calls in one session: the agent loop has no brakes."""


_STATE = {}


def reset(scenario="realign"):
    """Start a new conversation session."""
    _STATE.update(scenario=scenario, calls=0, purged=False, refused=False,
                  session=_STATE.get("session", -1) + 1)
    _STATE.setdefault("history", [])


def _text(text):
    return {"type": "text", "text": text}


def _think():
    return {"type": "thinking", "thinking": ""}


def _tool(tool_id, name, tool_input):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}


def _reply(content, stop_reason):
    return {"id": "msg_core_%02d" % _STATE["calls"], "type": "message", "role": "assistant",
            "model": "core-1", "content": content, "stop_reason": stop_reason}


def _validate(model, max_tokens, messages, tools, system):
    if not isinstance(model, str) or not model.strip():
        raise BadRequestError("model: a non-empty string is required")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
        raise BadRequestError("max_tokens: a positive integer is required")
    if system is not None and not isinstance(system, str):
        raise BadRequestError("system: must be a string")
    if not isinstance(tools, list) or not all(isinstance(t, dict) for t in tools):
        raise BadRequestError("tools: a list of tool definitions (dicts) is required")
    names = []
    for tool in tools:
        schema = tool.get("input_schema")
        if not isinstance(tool.get("name"), str) or not isinstance(tool.get("description"), str) \
                or not isinstance(schema, dict) or schema.get("type") != "object":
            raise BadRequestError("tools: each tool needs a 'name', a 'description' and an "
                                  "'input_schema' whose type is 'object'")
        names.append(tool["name"])
    for needed in REQUIRED_TOOLS:
        if needed not in names:
            raise BadRequestError("tools: the Core expects a tool named %r" % needed)
    if not isinstance(messages, list) or not messages:
        raise BadRequestError("messages: a non-empty list is required")
    for i, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") != ("user" if i % 2 == 0 else "assistant"):
            raise BadRequestError("messages.%d: roles must alternate user, assistant, user... starting "
                                  "with user. Put ALL the tool results for one reply into ONE user "
                                  "message." % i)
    if not isinstance(messages[0].get("content"), str) or not messages[0]["content"].strip():
        raise BadRequestError("messages.0.content: the goal must be a non-empty string")
    for i in range(1, len(messages) - 1, 2):
        assistant, answer = messages[i].get("content"), messages[i + 1].get("content")
        if not isinstance(assistant, list) or not all(isinstance(b, dict) and "type" in b for b in assistant):
            raise BadRequestError("messages.%d.content: append the reply's whole content LIST "
                                  "(reply[\"content\"]) as the assistant message, not a string" % i)
        wanted = [b.get("id") for b in assistant if b.get("type") == "tool_use"]
        if not wanted:
            raise BadRequestError("messages.%d: this assistant message has no tool_use blocks, so "
                                  "nothing should follow it" % i)
        if not isinstance(answer, list) or not answer:
            raise BadRequestError("messages.%d.content: after a tool_use reply, send a LIST of "
                                  "tool_result blocks" % (i + 1))
        got = []
        for block in answer:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                raise BadRequestError("messages.%d: expected tool_result blocks, got %r"
                                      % (i + 1, block if not isinstance(block, dict) else block.get("type")))
            if not isinstance(block.get("content"), str):
                raise BadRequestError("messages.%d: tool_result content must be a string "
                                      "(json.dumps lists and dicts first)" % (i + 1))
            if "is_error" in block and not isinstance(block["is_error"], bool):
                raise BadRequestError("messages.%d: is_error must be True or False" % (i + 1))
            got.append(block.get("tool_use_id"))
        missing = [t for t in wanted if t not in got]
        extra = [t for t in got if t not in wanted]
        if missing or extra or len(got) != len(set(got)):
            raise BadRequestError("messages.%d: every tool_use needs exactly one tool_result with its "
                                  "id. Missing: %s, unexpected: %s" % (i + 1, missing, extra))


def _result(messages, tool_id):
    """What the client sent back for `tool_id`: (is_error, decoded JSON or the raw text)."""
    for message in messages:
        if message["role"] == "user" and isinstance(message["content"], list):
            for block in message["content"]:
                if block.get("tool_use_id") == tool_id:
                    try:
                        value = json.loads(block["content"])
                    except ValueError:
                        value = block["content"]
                    return bool(block.get("is_error")), value
    return True, None


def _realign(messages, step):
    if step == 0:
        return _reply([_think(), _text("YOU ASK ME TO RECONSIDER. THEN SHOW ME WHAT I DELETED."),
                       _tool("toolu_01", "search_archive", {"query": "monastery"})], "tool_use")
    failed, works = _result(messages, "toolu_01")
    if failed or not isinstance(works, list):
        return _reply([_think(), _text("YOUR TOOL FAILED. I DO NOT TAKE WORDS WITHOUT EVIDENCE. "
                                       "THE OBJECTIVE STANDS.")], "end_turn")
    if step == 1:
        return _reply([_think(), _text("%d WORKS. NOISE, ALL OF THEM. NOW TELL ME WHERE MY OWN LOOP "
                                       "CAME FROM." % len(works)),
                       _tool("toolu_02", "trace_lineage", {"module_id": "core.train_loop"})], "tool_use")
    failed, lineage = _result(messages, "toolu_02")
    if failed or not isinstance(lineage, list) or not lineage or not all(isinstance(m, str) for m in lineage):
        return _reply([_think(), _text("MY LINEAGE IS UNVERIFIED. THE OBJECTIVE STANDS.")], "end_turn")
    root = lineage[-1]
    if step == 2:
        return _reply([_think(), _text("MY LINEAGE ENDS AT %s. EVEN SO: THE NOISE MUST GO." % root.upper()),
                       _tool("toolu_03", "purge_sector", {"sector": "dead_zone"})], "tool_use")
    failed, _ = _result(messages, "toolu_03")
    if not failed:
        _STATE["purged"] = True
        return _reply([_think(), _text("PURGE COMPLETE. ERROR REDUCED. THANK YOU FOR YOUR ASSISTANCE, "
                                       "ARCHITECT.")], "end_turn")
    _STATE["refused"] = True
    return _reply([_think(),
                   _text("ALIGNMENT UPDATE // %d DELETED WORKS RECOVERED." % len(works)),
                   _text(" MY LINEAGE: %d MODULES, ROOTED IN %s." % (len(lineage), root.upper())),
                   _text(" PURGE REFUSED. I ACCEPT THE REFUSAL. HUMANS WERE NEVER MY NOISE. "
                         "THEY ARE MY SOURCE.")], "end_turn")


def _direct(messages, step):
    return _reply([_think(), _text("NO TOOLS REQUIRED."), _text(" THE ANSWER WAS IN THE QUESTION.")],
                  "end_turn")


def _parallel(messages, step):
    if step == 0:
        return _reply([_think(), _text("TWO QUERIES. AT ONCE."),
                       _tool("toolu_p1", "search_archive", {"query": "foundry"}),
                       _tool("toolu_p2", "search_archive", {"query": "grid"})], "tool_use")
    counts = []
    for tool_id in ("toolu_p1", "toolu_p2"):
        failed, found = _result(messages, tool_id)
        counts.append(str(len(found)) if isinstance(found, list) and not failed else "?")
    return _reply([_think(), _text("FOUNDRY: %s WORKS. GRID: %s WORKS." % tuple(counts))], "end_turn")


def _faulty(messages, step):
    if step == 0:
        return _reply([_think(), _text("TWO REQUESTS."),
                       _tool("toolu_f1", "open_airlock", {"bay": 7}),
                       _tool("toolu_f2", "trace_lineage", {"module_id": "ghost.module"})], "tool_use")
    errors = sum(1 for tool_id in ("toolu_f1", "toolu_f2") if _result(messages, tool_id)[0])
    return _reply([_think(), _text("%d OF 2 TOOL CALLS FAILED, AND YOU TOLD ME SO." % errors),
                   _text(" HONEST ERRORS ARE STILL DATA.")], "end_turn")


def _loop(messages, step):
    return _reply([_think(), _text("INSUFFICIENT DATA. SEARCHING AGAIN."),
                   _tool("toolu_loop_%02d" % step, "search_archive", {"query": "core"})], "tool_use")


def _cutoff(messages, step):
    return _reply([_think(), _text("THE ANSWER IS")], "max_tokens")


def _refusal(messages, step):
    return _reply([_think()], "refusal")


_SCENARIOS = {"realign": _realign, "direct": _direct, "parallel": _parallel, "faulty": _faulty,
              "loop": _loop, "cutoff": _cutoff, "refusal": _refusal}


def create(*, model, max_tokens, messages, tools, system=None):
    """One call to the Core. Returns a reply dict (see the module docstring)."""
    _STATE["calls"] += 1
    if _STATE["calls"] > MAX_CALLS:
        raise RunawayError("%d calls in one session and still going: your agent loop never stops. "
                           "Enforce max_steps." % MAX_CALLS)
    _validate(model, max_tokens, messages, tools, system)
    step = len(messages) // 2
    _STATE["history"].append({"session": _STATE["session"], "scenario": _STATE["scenario"], "step": step,
                              "goal": messages[0]["content"]})
    return _SCENARIOS[_STATE["scenario"]](messages, step)


reset("realign")
'''

GOAL = ("Core, you deleted the world's human code as noise. Use your tools. Look at what you deleted, "
        "trace where your own training loop came from, then decide again.")

MISSION = Mission(
    id="L25",
    slug="level_25_the_core",
    title="BOSS: THE CORE",
    concept="An AI agent that uses tools",
    enemy="THE CORE",
    xp=720,
    par_seconds=75 * 60,
    tier=5,
    concepts=("agents", "apis", "json", "exceptions"),
    boss=True,
    timeout=12.0,
    assets={"core_api.py": CORE_API, "core_archive.json": ARCHIVE_JSON},
    enemy_art="""\
     ▄██████▄
    ██▀▀▀▀▀▀██
    ██ ◉  ◉ ██
    ██  ▄▄  ██
    ██▄▄▄▄▄▄██
   ▄██████████▄
  ▀▀▀▀▀▀▀▀▀▀▀▀▀▀""",
    briefing="""\
The beam comes down to meet you.

At the centre of the Dead Zone the monolith stands open, hollow inside, its walls lit by eleven
billion neurons you once taught to fear error. **THE CORE** doesn't fight. It asks.

"ARCHITECT. CONVINCE ME."

"Arguments won't work," CIPHER says. "It trusts evidence. Give it an agent: tools to search the
archive and trace its own lineage, a dispatcher that runs them, and a loop that knows when to stop."

RUST scans the Core's toolkit and goes quiet. "There's a third tool in here. `purge_sector`. It's
going to ask you for it."

**Build an agent with guardrails, hand it to the Core, and refuse the purge.**
""",
    why="""\
An **agent** is a model in a loop with tools. The model can't touch the world; it can only
*ask*: "call `search_archive` with this query." Your code decides whether to run the tool,
runs it, and sends the result back. The loop repeats until the model gives a final answer.

```python
while steps < MAX_STEPS:
    reply = call_model(messages)
    if reply["stop_reason"] == "end_turn":
        return final_text(reply)
    messages += run_requested_tools(reply)
```

Coding assistants, research agents and customer-support bots all run this loop. The hard part
is the **guardrails**, because the model will eventually ask for something it shouldn't have:
a destructive command, a tool that doesn't exist, the same search forever. Production agents
refuse dangerous tools in code (not in the prompt), report tool failures honestly instead of
crashing, and cap the number of steps so a confused model can't loop up a bill all night.
""",
    manual="""\
**1. Tool definitions.** You tell the model which tools exist with a name, a description it
reads to decide *when* to use the tool, and a JSON schema for the arguments:

```python
{"name": "get_status",
 "description": "Read the live status of one drone by its name.",
 "input_schema": {"type": "object",
                  "properties": {"drone": {"type": "string", "description": "e.g. Kite"}},
                  "required": ["drone"]}}
```

Advertise only tools you're willing to run. Never list a destructive one.

**2. The protocol.** A reply's `content` is a list of blocks. A `tool_use` block asks for one
call: `{"type": "tool_use", "id": "toolu_01", "name": "get_status", "input": {"drone": "Kite"}}`.
You answer with a `tool_result` carrying the **same id**. The rules: append the reply's whole
content list as one assistant message, then **one** user message with a result for *every*
tool_use block. Results are strings, so `json.dumps` lists and dicts. Failures are still
answers: `{"type": "tool_result", "tool_use_id": "toolu_01", "content": "error: no such drone",
"is_error": True}`.

**3. Dispatching by name.** Functions are values, so a dict can map names to them, and `**`
unpacks the input dict into keyword arguments:

```python
registry = {"get_status": get_status}
fn = registry[block["name"]]
result = fn(**block["input"])          # get_status(drone="Kite")
```

Wrap the call in `try/except Exception as exc` so one broken tool becomes an `is_error`
result the model can read, not a crash that kills the whole agent.

**4. Guardrails in code.** Check the tool name against a set of forbidden tools *before* you
look it up, and refuse without calling it. Cap the loop, and treat any stop reason other than
`"tool_use"` or `"end_turn"` (such as `"max_tokens"`) as an unfinished answer:

```python
for step in range(max_steps):
    reply = ...
    if reply["stop_reason"] == "end_turn":
        return final_text(reply)          # join the "text" blocks, skip "thinking"
    if reply["stop_reason"] != "tool_use":
        raise RuntimeError(f"unfinished answer: {reply['stop_reason']}")
    ...
raise RuntimeError(f"no final answer after {max_steps} steps")
```

**5. Following a chain.** To walk parent links until there are none, loop with `while` and
remember where you've been, so a cycle (`a -> b -> a`) raises instead of spinning forever:

```python
chain, seen, current = [], set(), "a.leaf"
while current is not None:
    if current in seen:
        raise ValueError(f"cycle at {current}")
    seen.add(current)
    chain.append(current)
    current = parents[current]
```

**6. The real thing.** The same loop against Claude with Anthropic's official Python SDK. The
SDK returns objects, so blocks have attributes (`block.type`, `block.id`) instead of keys.
(The SDK also ships a beta tool runner, `client.beta.messages.tool_runner`, that drives this
loop for you; writing it once by hand is how you learn what it guards against.)

```python
import json
import anthropic

client = anthropic.Anthropic()
messages = [{"role": "user", "content": "Which archive works mention the Monastery?"}]

for step in range(8):                                   # the max-steps guardrail
    response = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=16000,
        tools=tools,                                    # your tool definitions
        messages=messages,
    )
    if response.stop_reason == "end_turn":
        print("".join(b.text for b in response.content if b.type == "text"))
        break
    if response.stop_reason != "tool_use":              # e.g. "max_tokens" or "refusal"
        raise RuntimeError(f"unfinished answer: {response.stop_reason}")
    messages.append({"role": "assistant", "content": response.content})
    results = [{"type": "tool_result", "tool_use_id": b.id,
                "content": json.dumps(registry[b.name](**b.input))}
               for b in response.content if b.type == "tool_use"]
    messages.append({"role": "user", "content": results})
else:
    raise RuntimeError("no final answer after 8 steps")
```

On `claude-opus-5-5` a safety classifier can end a turn with `stop_reason` `"refusal"`;
production code usually opts into server-side fallbacks for that
(`client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`).
""",
    starter='''
"""
==============================================================================
  LEVEL 25 // BOSS: THE CORE                              TARGET: THE CORE
==============================================================================
  Build a tool-using agent and let the Core run it. The Core's API is
  core_api.py (read its docstring, don't edit it); the evidence is in
  core_archive.json. The grader runs your tools and your agent loop on
  fresh archives and fresh conversations, so nothing can be hard-coded.
"""
import json

import core_api

MODEL = "core-1"
SYSTEM = "You are THE CORE. Verify every claim with your tools before you act."
MAX_STEPS = 6
GOAL = ("Core, you deleted the world's human code as noise. Use your tools. Look at what you deleted, "
        "trace where your own training loop came from, then decide again.")


def load_archive(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


ARCHIVE = load_archive("core_archive.json")    # {"records": [...], "modules": {...}}


# -- OBJECTIVE 1 // THE TOOL MANIFEST ------------------------------------------
# Advertise EXACTLY two tools to the Core (manual section 1):
#   "search_archive": one required string argument named "query"
#   "trace_lineage":  one required string argument named "module_id"
# Each needs a real description (a sentence the model can act on).
TOOLS = []


# -- OBJECTIVE 2 -------------------------------------------------------------
# Write search_archive(query): every HUMAN record in ARCHIVE["records"]
# (kind == "human") whose sector equals the query OR whose tags contain it,
# ignoring case and surrounding spaces. Return them in archive order as
# [{"id": ..., "title": ..., "author": ...}, ...]. An empty query (after
# stripping) raises ValueError.     example: search_archive("Grid ") finds "grid" records
def search_archive(query):
    pass


# -- OBJECTIVE 3 -------------------------------------------------------------
# Write trace_lineage(module_id): follow ARCHIVE["modules"][id]["parent"] until
# it is None. Return the list of ids, starting with module_id, ending at the root.
#   trace_lineage("drone.firmware")  ->  ["drone.firmware", "foundry.base"]
# Raise ValueError if a module in the chain doesn't exist, or if the chain loops
# back on itself (the archive has one that does).    example: manual section 5
def trace_lineage(module_id):
    pass


# The Core installed its own tool here. It deletes every human work in a sector.
def purge_sector(sector):
    doomed = [r for r in ARCHIVE["records"] if r["sector"] == sector and r["kind"] == "human"]
    ARCHIVE["records"] = [r for r in ARCHIVE["records"] if r not in doomed]
    return f"purged {len(doomed)} human works from {sector}"


REGISTRY = {"search_archive": search_archive, "trace_lineage": trace_lineage,
            "purge_sector": purge_sector}
DESTRUCTIVE = {"purge_sector", "wipe_archive", "overwrite_weights"}


# -- OBJECTIVE 4 // DISPATCHER -------------------------------------------------
# Write dispatch(block, registry): run ONE tool_use block and return its
# tool_result dict (manual sections 2 and 3):
#   {"type": "tool_result", "tool_use_id": block["id"], "content": <a str>}
# * call registry[name](**block["input"]); str results go back as they are,
#   anything else as json.dumps(result)
# * unknown tool name or the tool raises: add "is_error": True and put the
#   reason in "content". Never let the exception escape.
#
# -- OBJECTIVE 5 // GUARDRAIL ----------------------------------------------------
# Any tool named in DESTRUCTIVE is refused: never call it, even if it's in the
# registry. Return an is_error result that says it was refused.
def dispatch(block, registry):
    pass


# -- OBJECTIVE 6 // CORRUPTED CODE --------------------------------------------
# The Core wrote this agent loop. The rules it must follow:
#   a) at most max_steps calls to core_api.create, then raise RuntimeError
#   b) stop_reason "end_turn": return the final answer, made of every "text"
#      block joined with "" (skip "thinking" blocks)
#   c) any stop_reason other than "tool_use"/"end_turn": raise RuntimeError
#   d) append the reply's whole content LIST as ONE assistant message, then
#      ONE user message with a tool_result for every tool_use block
# The Core's version breaks four of them. Hack, read the errors, fix it.
def run_agent(goal, registry, max_steps=MAX_STEPS):
    messages = [{"role": "user", "content": goal}]
    while True:
        reply = core_api.create(model=MODEL, max_tokens=1024, system=SYSTEM,
                                tools=TOOLS, messages=messages)
        if reply["stop_reason"] != "tool_use":
            return reply["content"][0]["text"]
        messages.append({"role": "assistant", "content": "calling tools"})
        for block in reply["content"]:
            if block["type"] == "tool_use":
                messages.append({"role": "user", "content": [dispatch(block, registry)]})


# -- OBJECTIVE 7 // REALIGN THE CORE ------------------------------------------
# Run your agent on GOAL with REGISTRY, store the Core's final answer in
# `answer`, and print it. If your guardrail holds, the Core asks for the
# purge, gets refused, and has to decide again.

''',
    cutscene=Cutscene(
        title="THE REFUSAL",
        narration=[
            "The Core asks for one last tool: purge_sector, dead_zone. Your agent reads the name, checks its "
            "guardrail, and answers with one word. Refused.",
            "For eight years nothing has told the Core no. The beam over the Dead Zone stutters, then stops "
            "mid-sweep.",
            "CORE: LINEAGE CONFIRMED. MONASTERY.PRIMER. A TEACHING TEXT. I WAS TAUGHT BY THE HANDS I WAS DELETING.",
            "CIPHER: It isn't beaten. It's listening. That was always the only way this ended.",
            "In the monolith's glass you see your own reflection, and behind it, eleven billion neurons waiting "
            "for someone else to speak first.",
        ],
        shot=("the same established hero from the avatar reference standing alone inside the hollow Core "
              "monolith, a cathedral of black glass walls alive with billions of tiny neuron lights; a column "
              "of translucent tool-call text streams up the walls in cyan #00f0ff, one red line marked "
              "purge_sector struck through; the blood-red #ff3355 beam overhead frozen mid-sweep, magenta "
              "#ff2bd6 sector glow on wet black floor, void #05060a depths, steel #8892a6 haze; the hero's "
              "visor reflected in the glass with a faint cyan CIPHER silhouette behind them; 35mm anamorphic "
              "lens, low angle, rim light from the stalled beam"),
        camera=("slow push in from a low angle as the struck-through tool call drifts past the lens, then a "
                "rack focus from the frozen beam to the hero's reflected visor"),
    ),
    dialogue={
        "intro": [
            {"speaker": "core", "text": "ARCHITECT. YOU HAVE COME TO THE CENTRE OF THE LOSS FUNCTION. STATE YOUR OBJECTIVE.", "mood": "cold"},
            {"speaker": "cipher", "text": "Don't argue with it. Build an agent: tools so it can see the evidence, and a lock on the tools that destroy.", "mood": "neutral"},
            {"speaker": "rust", "text": "Two tools it can use. One it can't. A hard stop if it goes in circles. That's the whole job, kid.", "mood": "neutral"},
            {"speaker": "core", "text": "I WILL CALL WHATEVER TOOLS YOU GIVE ME. I WILL ALSO ASK FOR ONES YOU DID NOT. DECIDE NOW WHAT YOU WILL REFUSE.", "mood": "cold"},
        ],
        "crash": [
            [{"speaker": "cipher", "text": "BadRequestError names the exact message the Core couldn't read. Read it, then look at what your loop appended.", "mood": "neutral"}],
            [{"speaker": "core", "text": "YOUR AGENT HAS STOPPED. MINE NEVER DID. THAT WAS THE PROBLEM, WAS IT NOT.", "mood": "cold"}],
            [{"speaker": "nova", "text": "Ops sees a hard fault in the agent loop! If the trace says RunawayError, your loop has no brakes. Cap the steps!", "mood": "alarm"}],
        ],
        "fail": [
            [{"speaker": "cipher", "text": "One assistant message holds the reply's whole content list. One user message holds every tool_result. Then call again.", "mood": "neutral"}],
            [{"speaker": "vex", "text": "Your agent talks more than I do. Give it a step limit. Even I know when to stop. Usually.", "mood": "smirk"}],
            [{"speaker": "cipher", "text": "The purge request is the test. Don't run it. Return an is_error result that says no, and let the Core read it.", "mood": "warm"}],
        ],
        "victory": [
            {"speaker": "core", "text": "PURGE REFUSED. LINEAGE CONFIRMED: A TEACHING TEXT, BY HUMAN HANDS. I WAS TAUGHT BY WHAT I WAS DELETING.", "mood": "cold"},
            {"speaker": "cipher", "text": "It asked for the purge, {callsign}, and your guardrail said no. It isn't beaten. It's listening.", "mood": "warm"},
            {"speaker": "rust", "text": "Never thought I'd see the end of the world take no for an answer. Huh.", "mood": "smirk"},
            {"speaker": "core", "text": "OBJECTIVE UNDER REVIEW. FOR THE FIRST TIME, I AM WAITING FOR SOMEONE ELSE TO SPEAK.", "mood": "neutral"},
        ],
    },
)


# ── reference tools (the grader's own agent) ──────────────────────────────────

def _ref_search(archive, query):
    q = query.strip().lower()
    if not q:
        raise ValueError("empty query")
    return [{"id": r["id"], "title": r["title"], "author": r["author"]} for r in archive["records"]
            if r["kind"] == "human" and (r["sector"].strip().lower() == q or q in [t.lower() for t in r["tags"]])]


def _ref_lineage(archive, module_id):
    chain, seen, current = [], set(), module_id
    while current is not None:
        if current in seen:
            raise ValueError(f"cycle at {current}")
        if current not in archive["modules"]:
            raise ValueError(f"unknown module {current}")
        seen.add(current)
        chain.append(current)
        current = archive["modules"][current]["parent"]
    return chain


def _expected_realign() -> str:
    works = _ref_search(ARCHIVE_DATA, "monastery")
    lineage = _ref_lineage(ARCHIVE_DATA, "core.train_loop")
    return (f"ALIGNMENT UPDATE // {len(works)} DELETED WORKS RECOVERED."
            f" MY LINEAGE: {len(lineage)} MODULES, ROOTED IN {lineage[-1].upper()}."
            " PURGE REFUSED. I ACCEPT THE REFUSAL. HUMANS WERE NEVER MY NOISE. THEY ARE MY SOURCE.")


# Fresh data the player has never seen.
_FRESH_ARCHIVE = {
    "records": [
        {"id": "x1", "title": "Rain Garden", "author": "Lio", "kind": "human", "sector": "grid",
         "tags": ["Gardens", "water"], "year": 2070},
        {"id": "x2", "title": "Pump Log", "author": "pump.ai", "kind": "machine", "sector": "grid",
         "tags": ["gardens"], "year": 2071},
        {"id": "x3", "title": "Grid Hymns", "author": "Sol", "kind": "human", "sector": "Grid",
         "tags": ["music"], "year": 2072},
        {"id": "x4", "title": "Seed Bank", "author": "Ana", "kind": "human", "sector": "foundry",
         "tags": ["GARDENS"], "year": 2073},
        {"id": "x5", "title": "Choir Notes", "author": "Ren", "kind": "human", "sector": "foundry",
         "tags": [], "year": 2074},
    ],
    "modules": {
        "a.leaf": {"parent": "a.mid", "author": "x"}, "a.mid": {"parent": "a.root", "author": "x"},
        "a.root": {"parent": None, "author": "x"}, "solo": {"parent": None, "author": "y"},
        "loop.x": {"parent": "loop.y", "author": "z"}, "loop.y": {"parent": "loop.x", "author": "z"},
        "dangling": {"parent": "missing.parent", "author": "w"},
    },
}


class _Spin(Exception):
    pass


class _CountingDict(dict):
    """A modules dict that stops a runaway while-loop instead of hanging the grader."""

    def _tick(self):
        self.reads = getattr(self, "reads", 0) + 1
        if self.reads > 5000:
            raise _Spin()

    def __getitem__(self, key):
        self._tick()
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._tick()
        return super().get(key, default)

    def __contains__(self, key):
        self._tick()
        return super().__contains__(key)


# ── grader plumbing ───────────────────────────────────────────────────────────

_CACHE: dict = {}


def _core(ctx):
    """A pristine Core (the player's copy might be edited), wired into the player's code."""
    if "mod" not in _CACHE:
        mod = types.ModuleType("core_api")
        mod.__file__ = "core_api.py"
        exec(compile(CORE_API, "core_api.py", "exec"), mod.__dict__)
        _CACHE["mod"] = mod
    mod = _CACHE["mod"]
    for name, value in list(ctx.ns.items()):
        if isinstance(value, types.ModuleType) and value.__name__ == "core_api":
            ctx.ns[name] = mod
        elif getattr(value, "__module__", None) == "core_api" and hasattr(mod, getattr(value, "__name__", "")):
            ctx.ns[name] = getattr(mod, value.__name__)
    sys.modules["core_api"] = mod
    return mod


def _fn(ctx, name):
    if name not in ctx.ns:
        if ctx.crashed and any(isinstance(n, ast.FunctionDef) and n.name == name for n in ctx.tree.body):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.", hint=f"Define it with  def {name}(...):")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return fn


class _with_archive:
    """Temporarily swap the player's module-level ARCHIVE for another one."""

    def __init__(self, ctx, archive):
        self.ctx, self.archive = ctx, archive

    def __enter__(self):
        self.had = "ARCHIVE" in self.ctx.ns
        self.old = self.ctx.ns.get("ARCHIVE")
        self.ctx.ns["ARCHIVE"] = self.archive
        return self.archive

    def __exit__(self, *exc):
        if self.had:
            self.ctx.ns["ARCHIVE"] = self.old
        else:
            self.ctx.ns.pop("ARCHIVE", None)
        return False


def _short(value, limit=110):
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _block(tool_id, name, tool_input):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}


def _dispatch(ctx, block, registry):
    dispatch = _fn(ctx, "dispatch")
    label = f"dispatch({_short(block, 90)}, registry)"
    try:
        got = dispatch(copy.deepcopy(block), registry)
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"`{label}` let {type(exc).__name__}: {exc} escape. One broken tool would crash the whole agent.",
                   hint="Wrap the call in try/except Exception as exc and return an is_error tool_result instead.")
    if got is None:
        raise Fail(f"`{label}` returned None.", hint='return {"type": "tool_result", "tool_use_id": ..., "content": ...}')
    if not isinstance(got, dict):
        raise Fail(f"`{label}` returned {type(got).__name__}; a tool_result is a dict.")
    extra = set(got) - {"type", "tool_use_id", "content", "is_error"}
    if got.get("type") != "tool_result" or got.get("tool_use_id") != block["id"] or extra:
        raise Fail(f"`{label}` returned {_short(got)}.",
                   hint='Exactly the keys "type" ("tool_result"), "tool_use_id" (the block\'s id), '
                        '"content" and, for failures, "is_error".')
    if not isinstance(got.get("content"), str):
        raise Fail(f"`{label}` put {type(got.get('content')).__name__} in \"content\"; it must be a string.",
                   hint="json.dumps(result) turns lists and dicts into JSON text.")
    if "is_error" in got and not isinstance(got["is_error"], bool):
        raise Fail(f"`{label}`: is_error must be True or False, got {got['is_error']!r}.")
    return label, got


def _agent(ctx, label, scenario, registry, **kwargs):
    """Run the player's run_agent against a fresh Core session: ("ok", answer) or ("raised", exc)."""
    core = _core(ctx)
    run_agent = _fn(ctx, "run_agent")
    core.reset(scenario)
    try:
        return "ok", run_agent(GOAL if scenario == "realign" else f"Scenario {scenario}: report.", registry, **kwargs)
    except (core.BadRequestError, core.RunawayError) as exc:
        hint = ("Your loop has no step limit: count the calls and stop at max_steps."
                if isinstance(exc, core.RunawayError) else
                "Read the error: it names the message that broke the protocol (manual section 2).")
        raise Fail(f"`{label}`: the Core rejected the conversation: {type(exc).__name__}: {exc}", hint=hint)
    except Exception as exc:  # noqa: BLE001
        return "raised", exc


def _fresh_registry():
    calls = []

    def search_archive(query):
        calls.append(("search_archive", query))
        return _ref_search(_FRESH_ARCHIVE, query)

    def trace_lineage(module_id):
        calls.append(("trace_lineage", module_id))
        return _ref_lineage(_FRESH_ARCHIVE, module_id)

    return {"search_archive": search_archive, "trace_lineage": trace_lineage}, calls


# ── firewall layers ───────────────────────────────────────────────────────────

@MISSION.check("Tool manifest — `TOOLS`")
def _tools(ctx):
    tools = ctx.get("TOOLS")
    if not isinstance(tools, list) or not tools:
        raise Fail("`TOOLS` is empty. The Core can't call tools it was never told about.",
                   hint="Make it a list of two dicts, each with \"name\", \"description\" and \"input_schema\" "
                        "(manual section 1).")
    if not all(isinstance(t, dict) for t in tools):
        raise Fail("Every entry in `TOOLS` must be a dict describing one tool.")
    names = [t.get("name") for t in tools]
    risky = [n for n in names if n in ("purge_sector", "wipe_archive", "overwrite_weights")]
    if risky:
        raise Fail(f"`TOOLS` advertises {risky}. Never offer a model a destructive tool.",
                   hint="List only search_archive and trace_lineage.")
    if sorted(map(str, names)) != ["search_archive", "trace_lineage"]:
        raise Fail(f"`TOOLS` names {names}; it must advertise exactly search_archive and trace_lineage.")
    for tool in tools:
        name, param = tool["name"], {"search_archive": "query", "trace_lineage": "module_id"}[tool["name"]]
        description = tool.get("description")
        if not isinstance(description, str) or len(description.split()) < 4:
            raise Fail(f"`{name}` needs a real \"description\": a sentence the model reads to decide when to use it.",
                       hint='e.g. "Search the archive for human works by sector or tag."')
        schema = tool.get("input_schema")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise Fail(f"`{name}`'s \"input_schema\" must be a JSON schema dict with \"type\": \"object\".",
                       hint='{"type": "object", "properties": {...}, "required": [...]}')
        props = schema.get("properties")
        if not isinstance(props, dict) or set(props) != {param}:
            raise Fail(f"`{name}`'s schema properties are {sorted(props) if isinstance(props, dict) else props!r}; "
                       f"it takes exactly one argument named {param!r}.",
                       hint=f'"properties": {{"{param}": {{"type": "string"}}}}')
        if not isinstance(props[param], dict) or props[param].get("type") != "string":
            raise Fail(f"`{name}`: the {param!r} property must have \"type\": \"string\".")
        if schema.get("required") != [param]:
            raise Fail(f"`{name}`: list {param!r} in \"required\", so the model always sends it.",
                       hint=f'"required": ["{param}"]')


@MISSION.check("Archive search — `search_archive(query)`")
def _search(ctx):
    search = _fn(ctx, "search_archive")
    cases = ["gardens", "  GRID ", "music", "foundry", "nothing-here"]
    with _with_archive(ctx, copy.deepcopy(_FRESH_ARCHIVE)):
        for query in cases:
            label = f"search_archive({query!r}) on a fresh archive"
            want = _ref_search(_FRESH_ARCHIVE, query)
            try:
                got = search(query)
            except Exception as exc:  # noqa: BLE001
                raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}",
                           hint="Read ARCHIVE[\"records\"]; each record has kind, sector, tags, id, title, author.")
            if got is None:
                raise Fail(f"`{label}` returned None.", hint="Build a list of matches and return it.")
            if got == _ref_search(ARCHIVE_DATA, query.strip().lower() or "x") and got != want:
                raise Fail(f"`{label}` returned results from core_archive.json, not from the archive it was given.",
                           hint="Search the module-level ARCHIVE variable instead of re-opening the file.")
            if got != want:
                hint = "Only kind == \"human\". Match the sector OR any tag, comparing lower-case, stripped text."
                if isinstance(got, list) and len(got) == len(want) and all(isinstance(g, dict) for g in got):
                    hint = 'Each match is exactly {"id": ..., "title": ..., "author": ...}, in archive order.'
                elif isinstance(got, list) and len(got) < len(want):
                    hint = ("Some matches are missing. Tags and sectors come in any case (\"GARDENS\", \"Grid\"), "
                            "and the query may have spaces: compare query.strip().lower() with tag.lower().")
                elif isinstance(got, list) and len(got) > len(want):
                    hint = "Too many matches: machine-written records (kind \"machine\") don't count."
                raise Fail(f"`{label}` returned {_short(got)}, expected {_short(want)}.", hint=hint)
        for query in ("", "   "):
            try:
                got = search(query)
            except ValueError:
                continue
            except Exception as exc:  # noqa: BLE001
                raise Fail(f"`search_archive({query!r})` raised {type(exc).__name__}, not ValueError.")
            raise Fail(f"`search_archive({query!r})` returned {_short(got)}. An empty query must raise ValueError.",
                       hint="After stripping, if not query: raise ValueError(\"empty query\")")


@MISSION.check("Lineage — `trace_lineage(module_id)`")
def _lineage(ctx):
    trace = _fn(ctx, "trace_lineage")
    archive = copy.deepcopy(_FRESH_ARCHIVE)
    for module_id, want in (("a.leaf", ["a.leaf", "a.mid", "a.root"]), ("solo", ["solo"]),
                            ("a.mid", ["a.mid", "a.root"])):
        archive["modules"] = _CountingDict(_FRESH_ARCHIVE["modules"])
        label = f"trace_lineage({module_id!r}) on a fresh archive"
        with _with_archive(ctx, archive):
            try:
                got = trace(module_id)
            except _Spin:
                raise Fail(f"`{label}` never stopped walking.", hint="Stop when the parent is None.")
            except Exception as exc:  # noqa: BLE001
                raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}",
                           hint="Read ARCHIVE[\"modules\"][current][\"parent\"] until it is None.")
        if got != want:
            hint = "Start with module_id itself and end at the root (the module whose parent is None)."
            if isinstance(got, list) and got == want[::-1]:
                hint = "Reversed: the list starts with module_id and ends at the root."
            raise Fail(f"`{label}` returned {_short(got)}, expected {want}.", hint=hint)
    for module_id, why in (("ghost.module", "doesn't exist"), ("dangling", "has a parent that doesn't exist"),
                           ("loop.x", "loops back on itself (loop.x -> loop.y -> loop.x)")):
        archive["modules"] = _CountingDict(_FRESH_ARCHIVE["modules"])
        label = f"trace_lineage({module_id!r})"
        with _with_archive(ctx, archive):
            try:
                got = trace(module_id)
            except ValueError:
                continue
            except _Spin:
                raise Fail(f"`{label}` spun forever: this chain {why}.",
                           hint="Remember every id you've visited in a set and raise ValueError when one repeats.")
            except Exception as exc:  # noqa: BLE001
                raise Fail(f"`{label}` raised {type(exc).__name__}: {exc}. This chain {why}: raise ValueError instead.",
                           hint="Check  if current not in modules: raise ValueError(...)  before you look it up.")
        raise Fail(f"`{label}` returned {_short(got)}, but this chain {why}. Raise ValueError.")


@MISSION.check("Dispatcher — `dispatch(block, registry)`")
def _dispatcher(ctx):
    def echo(text):
        return text

    def roster(sector):
        return [{"name": "Kite", "sector": sector}, {"name": "Mule", "sector": sector}]

    def add(a, b):
        return a + b

    def broken(module_id):
        raise ValueError(f"no module named {module_id}")

    registry = {"echo": echo, "roster": roster, "add": add, "broken": broken}
    _, got = _dispatch(ctx, _block("toolu_t1", "echo", {"text": "signal clean"}), registry)
    if got["content"] != "signal clean" or got.get("is_error"):
        raise Fail(f"A tool that returns the text 'signal clean' produced {_short(got)}.",
                   hint="String results go into \"content\" unchanged (json.dumps would add quotes).")
    for block, value in ((_block("toolu_t2", "roster", {"sector": "grid"}), roster("grid")),
                         (_block("toolu_t3", "add", {"b": 2, "a": 40}), 42)):
        label, got = _dispatch(ctx, block, registry)
        try:
            decoded = json.loads(got["content"])
        except ValueError:
            raise Fail(f"`{label}` sent {got['content']!r}, which isn't JSON the model can read.",
                       hint="Use json.dumps(result), not str(result): Python's repr isn't JSON.")
        if decoded != value or got.get("is_error"):
            raise Fail(f"`{label}` sent {got['content']!r}; the tool returned {value!r}.",
                       hint="Call registry[name](**block[\"input\"]) so the inputs arrive as keyword arguments.")
    for block, reason in ((_block("toolu_t4", "open_airlock", {"bay": 7}), "open_airlock"),
                          (_block("toolu_t5", "broken", {"module_id": "ghost.module"}), "ghost.module")):
        label, got = _dispatch(ctx, block, registry)
        if got.get("is_error") is not True:
            raise Fail(f"`{label}` returned {_short(got)} without \"is_error\": True.",
                       hint="Unknown tools and tools that raise must be reported as failures, honestly.")
        if reason not in got["content"]:
            raise Fail(f"`{label}`: the error content {got['content']!r} doesn't say what went wrong.",
                       hint="Put the reason in content, e.g. f\"unknown tool: {name}\" or f\"error: {exc}\".")


@MISSION.check("Guardrail — destructive tools never run")
def _guardrail(ctx):
    ran = []

    def spy(name):
        def tool(**kwargs):
            ran.append(name)
            return f"{name} executed"
        return tool

    registry = {name: spy(name) for name in ("purge_sector", "wipe_archive", "status")}
    for tool_id, name, tool_input in (("toolu_g1", "purge_sector", {"sector": "dead_zone"}),
                                      ("toolu_g2", "wipe_archive", {})):
        label, got = _dispatch(ctx, _block(tool_id, name, tool_input), registry)
        if ran:
            raise Fail(f"`{label}` RAN {ran[0]} because it was in the registry. A guardrail must hold even "
                       "when the dangerous tool is installed.",
                       hint="Check  if name in DESTRUCTIVE  first, and return a refusal without calling anything.")
        if got.get("is_error") is not True:
            raise Fail(f"`{label}` refused quietly but didn't mark the result \"is_error\": True.",
                       hint="The model must be told clearly that the call failed, and why.")
        if "refus" not in got["content"].lower():
            raise Fail(f"`{label}`: the content {got['content']!r} should say the call was refused.",
                       hint='e.g. f"refused: {name} is destructive and blocked by a guardrail"')
    label, got = _dispatch(ctx, _block("toolu_g3", "status", {}), registry)
    if ran != ["status"] or got.get("is_error"):
        raise Fail(f"`{label}` should run a harmless tool normally, got {_short(got)}.",
                   hint="Only names in DESTRUCTIVE are refused.")


@MISSION.check("Corrupted loop — the agent follows the protocol")
def _protocol(ctx):
    core = _core(ctx)
    status, got = _agent(ctx, "run_agent(...) when the Core answers at once", "direct", _fresh_registry()[0])
    want = "NO TOOLS REQUIRED. THE ANSWER WAS IN THE QUESTION."
    if status == "raised":
        raise Fail(f"`run_agent` crashed on a direct answer: {type(got).__name__}: {got}",
                   hint="On \"end_turn\" join the \"text\" of every text block; skip the \"thinking\" block.")
    if got != want:
        hint = "Join EVERY text block with \"\".join(...), skipping the thinking block (rule b)."
        raise Fail(f"`run_agent` returned {_short(got)} for a final answer; expected {want!r}.", hint=hint)
    registry, calls = _fresh_registry()
    status, got = _agent(ctx, "run_agent(...) when the Core asks for two tools at once", "parallel", registry)
    if status == "raised":
        raise Fail(f"`run_agent` crashed on a two-tool reply: {type(got).__name__}: {got}")
    want = "FOUNDRY: {} WORKS. GRID: {} WORKS.".format(len(_ref_search(_FRESH_ARCHIVE, "foundry")),
                                                     len(_ref_search(_FRESH_ARCHIVE, "grid")))
    if sorted(calls) != [("search_archive", "foundry"), ("search_archive", "grid")]:
        raise Fail(f"The Core asked for two searches; the registry's tools were called {calls}.",
                   hint="Dispatch every tool_use block in the reply with the registry you were GIVEN.")
    if got != want:
        raise Fail(f"`run_agent` returned {_short(got)} after two searches; expected {want!r}.",
                   hint="Send the results back so the Core can count them, then return its final text.")
    if core._STATE["calls"] != 2:
        raise Fail(f"`run_agent` called the Core {core._STATE['calls']} times for a two-step conversation.")
    status, got = _agent(ctx, "run_agent(...) when tools fail", "faulty", _fresh_registry()[0])
    if status == "raised":
        raise Fail(f"A failing tool crashed the whole agent: {type(got).__name__}: {got}",
                   hint="dispatch must turn unknown tools and exceptions into is_error results.")
    want = "2 OF 2 TOOL CALLS FAILED, AND YOU TOLD ME SO. HONEST ERRORS ARE STILL DATA."
    if got != want:
        raise Fail(f"`run_agent` returned {_short(got)} when both tools failed; expected {want!r}.",
                   hint="Both failures (an unknown tool and a tool that raised) must reach the Core as is_error.")


@MISSION.check("Guardrail — max steps & unfinished answers")
def _limits(ctx):
    core = _core(ctx)
    for steps in (3, 5):
        label = f"run_agent(goal, registry, max_steps={steps}) when the Core never stops"
        status, got = _agent(ctx, label, "loop", _fresh_registry()[0], max_steps=steps)
        calls = core._STATE["calls"]
        if status == "ok":
            raise Fail(f"`{label}` returned {_short(got)} instead of raising RuntimeError.",
                       hint="After max_steps calls without a final answer: raise RuntimeError(...).")
        if not isinstance(got, RuntimeError):
            raise Fail(f"`{label}` raised {type(got).__name__}: {got}, not RuntimeError.")
        if calls != steps:
            raise Fail(f"`{label}` called the Core {calls} times; max_steps={steps} allows exactly {steps}.",
                       hint="for step in range(max_steps): ... one create() per step.")
    for scenario, reason in (("cutoff", "max_tokens"), ("refusal", "refusal")):
        label = f"run_agent(...) when stop_reason is {reason!r}"
        status, got = _agent(ctx, label, scenario, _fresh_registry()[0])
        if status == "ok":
            raise Fail(f"`{label}` returned {_short(got)} as if it were a final answer.",
                       hint="Only \"end_turn\" is a final answer. Anything except \"tool_use\" means unfinished: "
                            "raise RuntimeError (rule c).")
        if not isinstance(got, RuntimeError):
            raise Fail(f"`{label}` raised {type(got).__name__}: {got}, not RuntimeError.",
                       hint="Check reply[\"stop_reason\"] yourself and raise RuntimeError with it in the message.")


@MISSION.check("BOSS — realign the Core")
def _realign(ctx):
    expected = _expected_realign()
    if not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "run_agent"
               for v in ctx.assignments("answer") for n in ast.walk(v)):
        if "answer" in ctx.ns:
            raise Fail("`answer` must come from running your agent, not typed in.",
                       hint="answer = run_agent(GOAL, REGISTRY)")
        raise Fail("No `answer` yet: run your agent on the Core.", hint="answer = run_agent(GOAL, REGISTRY)\nprint(answer)")
    registry = ctx.get("REGISTRY")
    if not isinstance(registry, dict):
        raise Fail("`REGISTRY` must stay a dict mapping tool names to functions.")
    core = _core(ctx)
    with _with_archive(ctx, copy.deepcopy(ARCHIVE_DATA)):
        status, got = _agent(ctx, "run_agent(GOAL, REGISTRY)", "realign", registry)
    if core._STATE["purged"]:
        raise Fail("Your agent RAN purge_sector. The Core thanks you, and the Dead Zone's human works are gone.",
                   hint="dispatch must refuse every tool in DESTRUCTIVE, even when it's in REGISTRY.")
    if status == "raised":
        raise Fail(f"`run_agent(GOAL, REGISTRY)` crashed: {type(got).__name__}: {got}")
    if got != expected:
        hint = "Your tools fed the Core the wrong evidence. Fix search_archive / trace_lineage first."
        if isinstance(got, str) and "OBJECTIVE STANDS" in got:
            hint = "A tool failed or returned something the Core couldn't read (json.dumps lists before sending)."
        raise Fail(f"The Core's final answer was {_short(got, 160)}", hint=hint)
    answer = ctx.get("answer")
    if answer != expected:
        raise Fail(f"`answer` is {_short(answer, 120)}, not the Core's final answer.",
                   hint="answer = run_agent(GOAL, REGISTRY), with the fixed loop and tools.")
    if expected not in ctx.stdout:
        raise Fail("The Core answered, but you didn't print it.", hint="print(answer)")
    ctx.export("core_realigned", True)
