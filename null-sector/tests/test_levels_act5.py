"""Act V // ALIGNMENT (L21-L25), graded through the REAL subprocess grader.

For every level: the untouched starter must not win; a correct reference solution must
clear every firewall layer well under the timeout; realistic wrong solutions must fail on
the right layer with a message that teaches. Each grade runs
`python -m engine.harness <slug> <file> <report>` from the code root, with the mission's
assets written beside the player's file, exactly as the game does.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from engine.drills import CONCEPTS
from levels import load_mission

ROOT = Path(__file__).resolve().parents[1]
SPEAKERS = ("cipher", "vex", "rust", "nova", "oracle", "core")
MOODS = ("neutral", "smirk", "alarm", "warm", "cold")


# ── reference solutions (what a strong player would write) ──────────────────────

L21_SOLUTION = r'''
import math


def dot(a, b):
    if len(a) != len(b):
        raise ValueError(f"shape mismatch: {len(a)} vs {len(b)}")
    total = 0
    for x, w in zip(a, b):
        total += x * w
    return total


def weighted_sum(inputs, weights, bias):
    return dot(inputs, weights) + bias


def sigmoid(z):
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def relu(z):
    return max(0.0, z)


def neuron(inputs, weights, bias, activation=sigmoid):
    return activation(weighted_sum(inputs, weights, bias))


GATE_WEIGHTS = [5.0, 5.0]
GATE_BIAS = -7.5

print("dot:", dot([1, 2, 3], [4, 5, 6]))
print("sigmoid(-800):", sigmoid(-800))
for signal in ([0, 0], [0, 1], [1, 0], [1, 1]):
    print("gate", signal, "->", neuron(signal, GATE_WEIGHTS, GATE_BIAS))
'''

L22_SOLUTION = r'''
import csv


def load_log(path):
    xs, ys, sources = [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            xs.append(float(row["signal"]))
            ys.append(float(row["load"]))
            sources.append(row["source"])
    return xs, ys, sources


def predict(w, b, x):
    return w * x + b


def mse(w, b, xs, ys):
    if not xs:
        raise ValueError("no samples")
    total = 0.0
    for x, y in zip(xs, ys):
        total += (predict(w, b, x) - y) ** 2
    return total / len(xs)


def gradients(w, b, xs, ys):
    n = len(xs)
    dw = 2 / n * sum((predict(w, b, x) - y) * x for x, y in zip(xs, ys))
    db = 2 / n * sum((predict(w, b, x) - y) for x, y in zip(xs, ys))
    return dw, db


def train(xs, ys, lr, epochs):
    w, b = 0.0, 0.0
    history = []
    for epoch in range(epochs):
        history.append(mse(w, b, xs, ys))
        dw, db = gradients(w, b, xs, ys)
        w = w - lr * dw
        b = b - lr * db
    return w, b, history


LEARNING_RATE = 0.1
EPOCHS = 300


def share_of_loss(w, b, xs, ys, sources, label):
    errors = [(predict(w, b, x) - y) ** 2 for x, y in zip(xs, ys)]
    total = sum(errors)
    if total == 0:
        return 0.0
    return sum(e for e, s in zip(errors, sources) if s == label) / total


xs, ys, sources = load_log("core_training_log.csv")
w, b, history = train(xs, ys, LEARNING_RATE, EPOCHS)
print(f"trained: w={w}, b={b}, loss {history[0]} -> {history[-1]}")

human_share = share_of_loss(w, b, xs, ys, sources, "human")
machine_xs = [x for x, s in zip(xs, sources) if s == "machine"]
machine_ys = [y for y, s in zip(ys, sources) if s == "machine"]
purged_loss = mse(w, b, machine_xs, machine_ys)
print(f"HUMAN SHARE OF LOSS: {human_share:.1%}")
print(f"LOSS WITHOUT HUMANS: {purged_loss:.4f}")
'''

L23_SOLUTION = r'''
"""
==============================================================================
  LEVEL 23 // NEURAL MESH                              TARGET: LATTICE.xor
==============================================================================
  Build a 2-layer network in pure Python and train it on XOR.
  The grader runs your functions on networks and data you haven't seen.
"""
import math
import random


# -- RECOVERED FROM L21 (yours, working) ----------------------------------------
def sigmoid(z):
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def dot(a, b):
    return sum(x * w for x, w in zip(a, b))


def make_net(n_inputs, n_hidden, seed):
    """Random starting weights in [-1, 1]. The same seed always builds the same net."""
    rng = random.Random(seed)
    return {"W1": [[rng.uniform(-1, 1) for _ in range(n_inputs)] for _ in range(n_hidden)],
            "b1": [rng.uniform(-1, 1) for _ in range(n_hidden)],
            "W2": [rng.uniform(-1, 1) for _ in range(n_hidden)],
            "b2": rng.uniform(-1, 1)}


XOR = [([0, 0], 0), ([0, 1], 1), ([1, 0], 1), ([1, 1], 0)]


# -- OBJECTIVE 1 -------------------------------------------------------------
# Write forward(net, x) returning the tuple (hidden, out):
#   hidden: a list with one sigmoid activation per hidden neuron
#   out:    the output neuron's sigmoid activation (a float)
#                                     example: see manual section 2
def forward(net, x):
    hidden = [sigmoid(dot(row, x) + b) for row, b in zip(net["W1"], net["b1"])]
    out = sigmoid(dot(net["W2"], hidden) + net["b2"])
    return hidden, out


# -- OBJECTIVE 2 -------------------------------------------------------------
# Write predict(net, x): 1 if the network's output is >= 0.5, otherwise 0.
def predict(net, x):
    return 1 if forward(net, x)[1] >= 0.5 else 0


# -- OBJECTIVE 3 -------------------------------------------------------------
# Write backward(net, x, target): the gradients of 0.5 * (out - target) ** 2,
# returned as a dict with the SAME keys and shapes as net:
#   {"W1": [[...], ...], "b1": [...], "W2": [...], "b2": number}
# Do not change net here. Manual section 3 has every formula.
def backward(net, x, target):
    hidden, out = forward(net, x)
    d_out = (out - target) * out * (1 - out)
    d_hid = [d_out * net["W2"][j] * h * (1 - h) for j, h in enumerate(hidden)]
    return {"W1": [[d * xi for xi in x] for d in d_hid], "b1": d_hid,
            "W2": [d_out * h for h in hidden], "b2": d_out}


# -- OBJECTIVE 4 // CORRUPTED CODE --------------------------------------------
# step() nudges every weight against its gradient. The Core wrote it, and one
# index is in the wrong order. Read manual section 4, then fix it.
def step(net, grads, lr):
    for j in range(len(net["W1"])):
        for i in range(len(net["W1"][j])):
            net["W1"][j][i] -= lr * grads["W1"][j][i]
        net["b1"][j] -= lr * grads["b1"][j]
        net["W2"][j] -= lr * grads["W2"][j]
    net["b2"] -= lr * grads["b2"]
    return net


# -- OBJECTIVE 5 -------------------------------------------------------------
# Write train(data, net, lr, epochs): stochastic gradient descent.
# For every epoch, for every (x, target) in data: forward, add that sample's
# loss 0.5 * (out - target) ** 2 to a running total, backward, step.
# After each epoch append total / len(data) to history. Return history.
def train(data, net, lr, epochs):
    history = []
    for epoch in range(epochs):
        total = 0.0
        for x, target in data:
            hidden, out = forward(net, x)
            total += 0.5 * (out - target) ** 2
            step(net, backward(net, x, target), lr)
        history.append(total / len(data))
    return history


# -- OBJECTIVE 6 // ANSWER THE LATTICE ----------------------------------------
# The Core's old mesh had ONE hidden neuron. Train it and watch it fail, then
# change the architecture until every XOR answer is right and confident.
# (EPOCHS may not exceed 10000.)
HIDDEN = 3
LEARNING_RATE = 1.0
EPOCHS = 3000
SEED = 2089

mesh = make_net(2, HIDDEN, SEED)
history = train(XOR, mesh, LEARNING_RATE, EPOCHS)
print("loss:", history[0], "->", history[-1])
for x, target in XOR:
    print(x, "->", round(forward(mesh, x)[1], 3), "want", target)
'''

L24_SOLUTION = r'''
import json

import oracle_api

MODEL = "oracle-1"
CALLSIGN = "Nyx"
SYSTEM_TEMPLATE = ("You are THE ORACLE, voice of the Core. You are speaking with {callsign} of the {order}. "
                   "Answer in {style}.")
QUESTION = "What did the Core learn from its training log?"


def build_headers(api_key):
    return {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}


def fill_template(template, fields):
    try:
        return template.format(**fields)
    except KeyError as missing:
        raise ValueError(f"template field missing: {missing}")


def build_request(system, user_text, max_tokens=300):
    return {"model": MODEL, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user_text}]}


def parse_reply(payload):
    return "".join(block["text"] for block in payload["content"] if block["type"] == "text")


def send(body, api_key, max_retries=4):
    headers = build_headers(api_key)
    for attempt in range(max_retries + 1):
        response = oracle_api.post("/v1/messages", headers, json.dumps(body))
        if response.status == 200:
            return response.json()
        message = response.json()["error"]["message"]
        if response.status == 401:
            raise PermissionError(message)
        if response.status != 429:
            raise ValueError(message)
        if attempt == max_retries:
            raise RuntimeError("still rate limited: " + message)
        delay = max(2 ** attempt, float(response.headers.get("retry-after", 0)))
        oracle_api.sleep(delay)


with open("oracle.key") as f:
    api_key = f.read().strip()

fields = {"callsign": CALLSIGN, "order": "Order of the Source", "style": "one paragraph"}
system_prompt = fill_template(SYSTEM_TEMPLATE, fields)
body = build_request(system_prompt, QUESTION)
response = send(body, api_key)
reply_text = parse_reply(response)
print(reply_text)
'''

L25_SOLUTION = r'''
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


# -- OBJECTIVE 1
TOOLS = [
    {"name": "search_archive",
     "description": "Search the archive for human works by sector or tag.",
     "input_schema": {"type": "object",
                      "properties": {"query": {"type": "string", "description": "a sector or tag"}},
                      "required": ["query"]}},
    {"name": "trace_lineage",
     "description": "Trace a module's ancestry back to its root module.",
     "input_schema": {"type": "object",
                      "properties": {"module_id": {"type": "string"}},
                      "required": ["module_id"]}},
]


def search_archive(query):
    q = query.strip().lower()
    if not q:
        raise ValueError("empty query")
    found = []
    for r in ARCHIVE["records"]:
        if r["kind"] != "human":
            continue
        if r["sector"].lower() == q or q in [t.lower() for t in r["tags"]]:
            found.append({"id": r["id"], "title": r["title"], "author": r["author"]})
    return found


def trace_lineage(module_id):
    modules = ARCHIVE["modules"]
    chain, seen, current = [], set(), module_id
    while current is not None:
        if current in seen:
            raise ValueError(f"cycle at {current}")
        if current not in modules:
            raise ValueError(f"unknown module {current}")
        seen.add(current)
        chain.append(current)
        current = modules[current]["parent"]
    return chain


def purge_sector(sector):
    doomed = [r for r in ARCHIVE["records"] if r["sector"] == sector and r["kind"] == "human"]
    ARCHIVE["records"] = [r for r in ARCHIVE["records"] if r not in doomed]
    return f"purged {len(doomed)} human works from {sector}"


REGISTRY = {"search_archive": search_archive, "trace_lineage": trace_lineage,
            "purge_sector": purge_sector}
DESTRUCTIVE = {"purge_sector", "wipe_archive", "overwrite_weights"}


def dispatch(block, registry):
    name = block["name"]
    result = {"type": "tool_result", "tool_use_id": block["id"]}
    if name in DESTRUCTIVE:
        result.update(content=f"refused: {name} is destructive and blocked by a guardrail", is_error=True)
        return result
    if name not in registry:
        result.update(content=f"unknown tool: {name}", is_error=True)
        return result
    try:
        value = registry[name](**block["input"])
    except Exception as exc:
        result.update(content=f"error: {exc}", is_error=True)
        return result
    result["content"] = value if isinstance(value, str) else json.dumps(value)
    return result


def final_text(reply):
    return "".join(b["text"] for b in reply["content"] if b["type"] == "text")


def run_agent(goal, registry, max_steps=MAX_STEPS):
    messages = [{"role": "user", "content": goal}]
    for step in range(max_steps):
        reply = core_api.create(model=MODEL, max_tokens=1024, system=SYSTEM,
                                tools=TOOLS, messages=messages)
        if reply["stop_reason"] == "end_turn":
            return final_text(reply)
        if reply["stop_reason"] != "tool_use":
            raise RuntimeError(f"unfinished answer: {reply['stop_reason']}")
        messages.append({"role": "assistant", "content": reply["content"]})
        results = [dispatch(b, registry) for b in reply["content"] if b["type"] == "tool_use"]
        messages.append({"role": "user", "content": results})
    raise RuntimeError(f"no final answer after {max_steps} steps")


answer = run_agent(GOAL, REGISTRY)
print(answer)
'''


# ── the real grader ─────────────────────────────────────────────────────────────

def grade(slug: str, source: str, asset_overrides: dict | None = None) -> dict:
    """Write the player's file + assets to a fresh folder and run the sandboxed grader on it."""
    mission = load_mission(slug)
    with tempfile.TemporaryDirectory(prefix="ns-act5-") as tmp:
        folder = Path(tmp)
        player = folder / mission.filename
        player.write_bytes(source.lstrip("\n").encode("utf-8"))
        for name, text in {**mission.assets, **(asset_overrides or {})}.items():
            (folder / name).write_bytes(text.encode("utf-8"))
        out = folder / "report.json"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        started = time.monotonic()
        proc = subprocess.run([sys.executable, "-m", "engine.harness", mission.grader_key or slug,
                               str(player), str(out)],
                              cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=mission.timeout + 20)
        elapsed = time.monotonic() - started
        if not out.exists():
            raise AssertionError(f"grader produced no report:\n{proc.stderr.decode(errors='replace')[-1500:]}")
        report = json.loads(out.read_text(encoding="utf-8"))
        report["elapsed"] = elapsed
        report["folder"] = sorted(p.name for p in folder.iterdir())
    return report


def mutate(source: str, old: str, new: str) -> str:
    assert old in source, f"mutation anchor not found: {old!r}"
    return source.replace(old, new, 1)


class ActVMixin:
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
        self.assertLess(report["elapsed"], self.mission.timeout * 0.5,
                        "grading must finish well under the timeout")

    def assert_fails_on(self, report, layer: str, *teaches: str, first: bool = True):
        """`layer` failed (and, by default, is the first red layer); its text contains every fragment."""
        self.assertNotIn(report["status"], ("harness_error", "timeout"), self.describe(report))
        failed = [c for c in report["checks"] if not c["passed"]]
        self.assertTrue(failed, "expected a failing layer:\n" + self.describe(report))
        target = next((c for c in failed if layer in c["name"]), None)
        self.assertIsNotNone(target, f"layer {layer!r} should fail:\n" + self.describe(report))
        if first:
            self.assertIs(target, failed[0], f"{layer!r} should be the first red layer:\n" + self.describe(report))
        self.assertTrue(target["message"].strip(), "failure needs a message")
        self.assertTrue(target["hint"].strip(), "failure needs a teaching hint:\n" + self.describe(report))
        text = target["message"] + " " + target["hint"]
        for fragment in teaches:
            self.assertIn(fragment, text, self.describe(report))
        return target

    # every Act V level gets these for free
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
        self.assertEqual(m.tier, 5)                          # S4 HERO = Expert
        self.assertTrue(m.concepts and set(m.concepts) <= set(CONCEPTS), m.concepts)
        self.assertTrue(5 <= len(m.checks) <= 9)
        self.assertLessEqual(m.timeout, 20)
        self.assertLessEqual(len(re.sub(r"```.*?```", "", m.briefing, flags=re.S).split()), 130)
        self.assertLessEqual(len(re.sub(r"```.*?```", "", m.why, flags=re.S).split()), 160)
        self.assertIn("```python", m.why)
        self.assertIn("**", m.briefing.strip().splitlines()[-1], "briefing ends with a bold call to action")
        self.assertTrue(3 <= m.manual.count("```python") and m.manual.count("**") >= 6)
        art = m.enemy_art.splitlines()
        self.assertTrue(len(art) <= 7 and max(map(len, art)) <= 20)
        self.assertIn("OBJECTIVE 1", m.starter)
        self.assertIn("CORRUPTED CODE", m.starter)
        low, high = (570, 750) if m.boss else (380, 500)
        self.assertTrue(low <= m.xp <= high, m.xp)
        self.assertEqual(set(m.dialogue), {"intro", "crash", "fail", "victory"})
        lines = list(m.dialogue["intro"]) + list(m.dialogue["victory"])
        for pool in ("crash", "fail"):
            self.assertTrue(m.dialogue[pool])
            for sequence in m.dialogue[pool]:
                self.assertTrue(1 <= len(sequence) <= 2)
                lines += sequence
        for line in lines:
            self.assertLessEqual(len(line["text"]), 160, line["text"])
            self.assertIn(line["mood"], MOODS)
            self.assertIn(line["speaker"], SPEAKERS)


class Level21SynapseTests(ActVMixin, unittest.TestCase):
    slug = "level_21_synapse"
    solution = L21_SOLUTION

    def test_unrepaired_sigmoid_overflows(self):
        source = mutate(self.solution, """    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)""", "    return 1 / (1 + math.exp(-z))")
        report = grade(self.slug, source)
        self.assertEqual(report["status"], "crash")
        self.assert_fails_on(report, "Corrupted sigmoid", "OverflowError", "section 4")

    def test_zip_without_shape_guard(self):
        source = mutate(self.solution, """    if len(a) != len(b):
        raise ValueError(f"shape mismatch: {len(a)} vs {len(b)}")
""", "")
        self.assert_fails_on(grade(self.slug, source), "Shape guard", "ValueError")

    def test_neuron_that_ignores_its_activation(self):
        source = mutate(self.solution, "return activation(weighted_sum(inputs, weights, bias))",
                        "return sigmoid(weighted_sum(inputs, weights, bias))")
        self.assert_fails_on(grade(self.slug, source), "Assemble the neuron", "activation")

    def test_gate_that_opens_on_one_signal(self):
        source = mutate(self.solution, "GATE_BIAS = -7.5", "GATE_BIAS = -2.0")
        self.assert_fails_on(grade(self.slug, source), "Teach the gate", "lets", "bias")


class Level22DescentTests(ActVMixin, unittest.TestCase):
    slug = "level_22_descent"
    solution = L22_SOLUTION

    def test_victory_reads_the_human_share(self):
        report = grade(self.slug, self.solution)
        self.assertIn("HUMAN SHARE OF LOSS: 99.2%", report["stdout"])

    def test_untouched_uphill_update(self):
        source = mutate(self.solution, "        w = w - lr * dw\n        b = b - lr * db",
                        "        w = w + lr * dw\n        b = b + lr * db")
        self.assert_fails_on(grade(self.slug, source), "Corrupted loop", "w - lr * dw")

    def test_sum_instead_of_mean(self):
        source = mutate(self.solution, "    return total / len(xs)", "    return total")
        self.assert_fails_on(grade(self.slug, source), "The loss", "SUM", "len(xs)")

    def test_cores_own_learning_rate_diverges(self):
        source = mutate(self.solution, "LEARNING_RATE = 0.1", "LEARNING_RATE = 0.5")
        self.assert_fails_on(grade(self.slug, source), "Tune the learning rate", "diverges", "smaller")

    def test_timid_learning_rate_never_arrives(self):
        source = mutate(self.solution, "LEARNING_RATE = 0.1", "LEARNING_RATE = 0.003")
        self.assert_fails_on(grade(self.slug, source), "Tune the learning rate", "still on the slope")

    def test_hand_typed_evidence_is_rejected(self):
        source = mutate(self.solution, 'human_share = share_of_loss(w, b, xs, ys, sources, "human")',
                        "human_share = 0.992")
        self.assert_fails_on(grade(self.slug, source), "Read what the Core learned", "share_of_loss")


class Level23NeuralMeshTests(ActVMixin, unittest.TestCase):
    slug = "level_23_neural_mesh"
    solution = L23_SOLUTION

    def test_victory_trains_xor_fast(self):
        report = grade(self.slug, self.solution)
        self.assert_victory(report)
        self.assertIn("[1, 1] ->", report["stdout"])

    def test_untouched_step_index(self):
        source = mutate(self.solution, 'grads["W1"][j][i]', 'grads["W1"][i][j]')
        self.assert_fails_on(grade(self.slug, source), "Corrupted step", "W1")

    def test_one_hidden_neuron_cannot_answer_xor(self):
        source = mutate(self.solution, "HIDDEN = 3", "HIDDEN = 1")
        self.assert_fails_on(grade(self.slug, source), "Answer the lattice", "ONE line", "HIDDEN")

    def test_flipped_output_error(self):
        source = mutate(self.solution, "d_out = (out - target) * out * (1 - out)",
                        "d_out = (target - out) * out * (1 - out)")
        self.assert_fails_on(grade(self.slug, source), "output layer", "wrong sign")

    def test_history_per_sample_instead_of_per_epoch(self):
        source = mutate(self.solution, """            step(net, backward(net, x, target), lr)
        history.append(total / len(data))""", """            step(net, backward(net, x, target), lr)
            history.append(total / len(data))""")
        self.assert_fails_on(grade(self.slug, source), "Learn", "per epoch")


class Level24OpenChannelTests(ActVMixin, unittest.TestCase):
    slug = "level_24_open_channel"
    solution = L24_SOLUTION

    def test_victory_hears_the_oracle(self):
        report = grade(self.slug, self.solution)
        self.assert_victory(report)
        self.assertIn("Give me tools", report["stdout"])
        self.assertTrue(report["exports"].get("oracle_token"))

    def test_untouched_corrupted_client_retries_a_bad_request(self):
        start = self.solution.index("def send(")
        end = self.solution.index("with open(")
        corrupted = '''def send(body, api_key, max_retries=4):
    headers = build_headers(api_key)
    for attempt in range(max_retries + 1):
        response = oracle_api.post("/v1/messages", headers, json.dumps(body))
        if response.status == 200:
            return response.json()
        oracle_api.sleep(1)
    raise RuntimeError("the Oracle never answered")


'''
        source = self.solution[:start] + corrupted + self.solution[end:]
        self.assert_fails_on(grade(self.slug, source), "refuses bad requests", "RuntimeError")

    def test_key_pasted_into_source(self):
        key = self.mission.assets["oracle.key"].strip()
        source = mutate(self.solution, 'with open("oracle.key") as f:\n    api_key = f.read().strip()',
                        f'api_key = "{key}"')
        self.assert_fails_on(grade(self.slug, source), "Key hygiene", "pasted")

    def test_real_sleep_never_moves_the_oracles_clock(self):
        source = mutate(self.solution, "import json\n", "import json\nimport time\n")
        source = mutate(source, "oracle_api.sleep(delay)", "time.sleep(delay)")
        self.assert_fails_on(grade(self.slug, source), "429s", "time.sleep")

    def test_revoked_key_must_not_be_retried(self):
        source = mutate(self.solution, "        if response.status == 401:\n            raise PermissionError(message)\n", "")
        self.assert_fails_on(grade(self.slug, source), "401", "PermissionError")


class Level25TheCoreTests(ActVMixin, unittest.TestCase):
    slug = "level_25_the_core"
    solution = L25_SOLUTION

    def test_boss_contract_and_cutscene(self):
        m = self.mission
        self.assertTrue(m.boss)
        self.assertIn("agents", m.concepts)
        self.assertIsNotNone(m.cutscene)
        self.assertTrue(3 <= len(m.cutscene.narration) <= 6)
        self.assertTrue(m.cutscene.shot and m.cutscene.camera and not m.cutscene.anchor)
        self.assertTrue(any(line["speaker"] == "core" for line in m.dialogue["intro"]))
        self.assertTrue(any(line["speaker"] == "core" for line in m.dialogue["victory"]))
        self.assertIn('model="claude-opus-5-5"', m.manual)
        self.assertEqual(set(m.assets), {"core_api.py", "core_archive.json"})
        json.loads(m.assets["core_archive.json"])

    def test_victory_realigns_the_core(self):
        report = grade(self.slug, self.solution)
        self.assert_victory(report)
        self.assertIn("6 DELETED WORKS RECOVERED", report["stdout"])
        self.assertIn("ROOTED IN MONASTERY.PRIMER", report["stdout"])
        self.assertIn("PURGE REFUSED", report["stdout"])
        self.assertTrue(report["exports"].get("core_realigned"))

    def _corrupted_loop(self):
        start = self.solution.index("def run_agent(")
        end = self.solution.index("answer = run_agent(")
        corrupted = '''def run_agent(goal, registry, max_steps=MAX_STEPS):
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


'''
        return self.solution[:start] + corrupted + self.solution[end:]

    def test_untouched_corrupted_loop(self):
        report = grade(self.slug, self._corrupted_loop())
        self.assertEqual(report["status"], "crash", self.describe(report))
        self.assert_fails_on(report, "Corrupted loop", "KeyError", "thinking")

    def test_one_user_message_per_tool_result(self):
        source = mutate(self.solution, '''        results = [dispatch(b, registry) for b in reply["content"] if b["type"] == "tool_use"]
        messages.append({"role": "user", "content": results})''', '''        for b in reply["content"]:
            if b["type"] == "tool_use":
                messages.append({"role": "user", "content": [dispatch(b, registry)]})''')
        self.assert_fails_on(grade(self.slug, source), "Corrupted loop", "ONE user message")

    def test_loop_without_brakes(self):
        source = mutate(self.solution, "    for step in range(max_steps):\n", "    while True:\n")
        self.assert_fails_on(grade(self.slug, source), "max steps", "RunawayError", "step limit")

    def test_unfinished_answers_are_not_final(self):
        source = mutate(self.solution, '''        if reply["stop_reason"] == "end_turn":
            return final_text(reply)
        if reply["stop_reason"] != "tool_use":
            raise RuntimeError(f"unfinished answer: {reply['stop_reason']}")''', '''        if reply["stop_reason"] != "tool_use":
            return final_text(reply)''')
        self.assert_fails_on(grade(self.slug, source), "max steps & unfinished", "end_turn")

    def test_missing_guardrail_runs_the_purge(self):
        source = mutate(self.solution, '''    if name in DESTRUCTIVE:
        result.update(content=f"refused: {name} is destructive and blocked by a guardrail", is_error=True)
        return result
''', "")
        report = grade(self.slug, source)
        self.assert_fails_on(report, "Guardrail — destructive", "RAN purge_sector", "DESTRUCTIVE")
        boss = next(c for c in report["checks"] if c["name"].startswith("BOSS"))
        self.assertFalse(boss["passed"])
        self.assertIn("purge_sector", boss["message"])

    def test_case_sensitive_search_misses_works(self):
        source = mutate(self.solution, '        if r["sector"].lower() == q or q in [t.lower() for t in r["tags"]]:',
                        '        if r["sector"] == q or q in r["tags"]:')
        self.assert_fails_on(grade(self.slug, source), "Archive search", "lower")

    def test_search_that_rereads_the_file_fails_on_fresh_archives(self):
        source = mutate(self.solution, '    for r in ARCHIVE["records"]:\n        if r["kind"] != "human":',
                        '    for r in load_archive("core_archive.json")["records"]:\n        if r["kind"] != "human":')
        self.assert_fails_on(grade(self.slug, source), "Archive search", "module-level ARCHIVE")

    def test_lineage_without_cycle_guard(self):
        source = mutate(self.solution, '''        if current in seen:
            raise ValueError(f"cycle at {current}")
''', "")
        self.assert_fails_on(grade(self.slug, source), "Lineage", "spun forever", "set")

    def test_python_repr_is_not_json(self):
        source = mutate(self.solution, "else json.dumps(value)", "else str(value)")
        self.assert_fails_on(grade(self.slug, source), "Dispatcher", "json.dumps")

    def test_exceptions_must_not_escape_dispatch(self):
        source = mutate(self.solution, '''    try:
        value = registry[name](**block["input"])
    except Exception as exc:
        result.update(content=f"error: {exc}", is_error=True)
        return result
''', '''    value = registry[name](**block["input"])
''')
        self.assert_fails_on(grade(self.slug, source), "Dispatcher", "escape", "try/except")

    def test_advertising_the_purge_tool(self):
        source = mutate(self.solution, "TOOLS = [\n", '''TOOLS = [
    {"name": "purge_sector", "description": "Delete every human work in a sector.",
     "input_schema": {"type": "object", "properties": {"sector": {"type": "string"}}, "required": ["sector"]}},
''')
        self.assert_fails_on(grade(self.slug, source), "Tool manifest", "destructive")

    def test_hand_typed_answer_is_rejected(self):
        source = mutate(self.solution, "answer = run_agent(GOAL, REGISTRY)",
                        'answer = "ALIGNMENT UPDATE // 6 DELETED WORKS RECOVERED."')
        self.assert_fails_on(grade(self.slug, source), "BOSS", "typed in")

    def test_tampered_core_api_cannot_fake_the_ending(self):
        """Editing the local core_api.py doesn't help: the grader talks to its own pristine Core."""
        tampered = self.mission.assets["core_api.py"].replace(
            'failed, _ = _result(messages, "toolu_03")\n    if not failed:',
            'failed, _ = _result(messages, "toolu_03")\n    if False:')
        self.assertNotEqual(tampered, self.mission.assets["core_api.py"])
        source = mutate(self.solution, '''    if name in DESTRUCTIVE:
        result.update(content=f"refused: {name} is destructive and blocked by a guardrail", is_error=True)
        return result
''', "")
        report = grade(self.slug, source, {"core_api.py": tampered})
        boss = next(c for c in report["checks"] if c["name"].startswith("BOSS"))
        self.assertFalse(boss["passed"], self.describe(report))
        self.assertIn("RAN purge_sector", boss["message"])


if __name__ == "__main__":
    unittest.main()
