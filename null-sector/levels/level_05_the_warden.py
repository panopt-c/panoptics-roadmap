"""LEVEL 05 // THE WARDEN — a first-sector log-analysis boss."""
import math

from engine.mission import Cutscene, Fail, Mission


RAW_LOG = "  OPEN,ERROR,OPEN,OPEN|12,20,17,24  "

MISSION = Mission(
    id="L05", slug="level_05_the_warden", title="BOSS: THE WARDEN",
    concept="Strings, lists, dictionaries & basic statistics", enemy="WARDEN.gate",
    xp=225, par_seconds=30 * 60, tier=1, boss=True,
    concepts=("strings", "lists", "dicts", "numeric"),
    enemy_art="""\
   ▄████████▄
  ██ ▄█  █▄ ██
  ██  ▀██▀  ██
  ████████████
   ██ ▄▄▄▄ ██
   ▀████████▀""",
    briefing="""\
You reach the cooling tower from the distress signal. Warm light escapes through
the sealed gate. Behind it, the last engineers are still alive.

**WARDEN**, the Monastery's gate AI, lowers a wall of red scan lines.
"Four access events. Four failures. No survivors admitted."

CIPHER catches the lie: the raw log contains successful openings. Corruption has
replaced WARDEN's audit with a verdict. Your stolen access key gets you one chance
to rebuild that audit from the original data.

**Parse the gate log, count what really happened, and prove the Monastery can open.**
""",
    why="""\
Before trusting a model, an engineer inspects its inputs and measurements. Text
logs become lists, event names become dictionary counts, and timing samples become
basic statistics:

```python
times = [14, 22, 18]
metrics = {"samples": len(times), "mean_ms": sum(times) / len(times)}
print(f"Mean inference time: {metrics['mean_ms']} ms")
```

The **mean** is the total divided by the number of samples. The minimum and
maximum expose variation that a single average hides. A correct calculation on
uncleaned text is still a broken pipeline. This boss connects each stage using
the variables you have already learned; no loops or functions are required.
""",
    manual="""\
**1. Clean, then split the record.** String methods return new strings; save the
result. `split(separator)` returns a list. Here `|` separates two sections and
commas separate values inside a section:

```python
raw = "  OK,BLOCKED|8,14  "
clean = raw.strip().lower()
parts = clean.split("|")
labels = parts[0].split(",")     # ["ok", "blocked"]
text_times = parts[1].split(",") # ["8", "14"]
```

**2. Convert text samples into integers.** List positions start at zero. A small,
fixed record can be converted one position at a time. Keep the scanner's raw
text unchanged and repair the calculation that consumes it:

```python
times = [int(text_times[0]), int(text_times[1])]
# "8" + "14" gives "814"; 8 + 14 gives 22.
```

**3. Count events into a dictionary.** `some_list.count(value)` returns how many
times that value appears, including zero if it is absent. Store each result under
a descriptive key. Count the list, not the raw text:

```python
counts = {"ok": labels.count("ok"), "blocked": labels.count("blocked")}
print(counts["ok"])
```

**4. Summarize a numeric list.** `sum` adds every value; `min` finds the smallest;
`max` finds the largest; `len` counts samples. Divide the total by that count for
the mean. Use `/`, which keeps the fractional part, rather than `//`, which floors
the result. This mission always supplies four samples, so the list is not empty:

```python
total = sum(times)
fastest = min(times)
slowest = max(times)
average = total / len(times)
```

**5. Build and broadcast a report.** A dictionary can contain another dictionary.
Read nested keys one at a time. Put variables inside an f-string, then print it:

```python
report = {"counts": counts, "mean_ms": average}
print(f"AUDIT | ok={report['counts']['ok']} | mean_ms={report['mean_ms']}")
```

For WARDEN, the report keys must be `events`, `counts`, `total_ms`, `min_ms`,
`max_ms`, and `mean_ms`. The exact final line is shown in objective 8. Every stage
must use the previous variables; typing the final numbers bypasses the audit.
""",
    starter='''
"""L05 // BOSS: THE WARDEN — restore the Monastery gate audit."""

# -- OBJECTIVE 1: Recover the original record -------------------------------
# Preserve raw_log. Create clean_log by stripping outer whitespace and
# lowercasing raw_log. Example: clean = raw.strip().lower()
raw_log = "  OPEN,ERROR,OPEN,OPEN|12,20,17,24  "


# -- OBJECTIVE 2: Split the evidence ---------------------------------------
# Create sections by splitting clean_log on "|".
# Create events from sections[0], split on commas.
# Create samples from sections[1], split on commas.
# Example: parts = record.split("|"); labels = parts[0].split(",")


# -- OBJECTIVE 3: CORRUPTED CODE -------------------------------------------
# Repair the line below to create latencies: a list of FOUR integers converted
# from samples[0], samples[1], samples[2], samples[3]. Do not retype the values.
# Example: times = [int(text_times[0]), int(text_times[1])]
# The damaged firmware adds text instead of building a numeric list.
latencies = samples[0] + samples[1] + samples[2] + samples[3]


# -- OBJECTIVE 4: Count actual events -------------------------------------
# Create counts with keys "open" and "error", using events.count(...).
# Example: counts = {"ok": labels.count("ok")}


# -- OBJECTIVE 5: Total latency -------------------------------------------
# Create total_latency using sum on latencies.
# Example: total = sum(times)


# -- OBJECTIVE 6: Find the bounds -----------------------------------------
# Create fastest and slowest using min and max on latencies.
# Example: smallest = min(times); largest = max(times)


# -- OBJECTIVE 7: Compute the mean ----------------------------------------
# Create mean_latency from total_latency divided by len(latencies).
# Example: average = total / len(times)  # / keeps the fractional part


# -- OBJECTIVE 8: Submit the audit ----------------------------------------
# Create report with these keys and values:
# "events": len(events), "counts": counts, "total_ms": total_latency,
# "min_ms": fastest, "max_ms": slowest, "mean_ms": mean_latency.
# Example: report = {"counts": counts, "mean_ms": average}
# Print this line using values read from report (spacing and labels matter):
# WARDEN AUDIT | events=4 | open=3 | error=1 | mean_ms=18.25
# Example: print(f"AUDIT | ok={report['counts']['ok']}")
''',
    dialogue={
        "intro": [
            {"speaker": "warden", "text": "MONASTERY GATE: SEALED. My audit records no successful access. Your key changes nothing.", "mood": "cold"},
            {"speaker": "cipher", "text": "Its verdict contradicts the evidence. Rebuild the audit from the raw log, one stage at a time.", "mood": "neutral"},
        ],
        "crash": [[
            {"speaker": "warden", "text": "AUDIT INTERRUPTED. Evidence must survive execution before it can overturn a verdict.", "mood": "cold"},
            {"speaker": "cipher", "text": "Read the first broken line. After splitting, the samples are still text; convert each one before doing math.", "mood": "neutral"},
        ]],
        "fail": [[
            {"speaker": "warden", "text": "EVIDENCE INCOMPLETE. A copied answer is not an audit. Show how each value follows from the record.", "mood": "cold"},
        ], [
            {"speaker": "warden", "text": "VERDICT PENDING. Count the events. Measure the delay. Do not discard the fractional evidence.", "mood": "neutral"},
        ]],
        "victory": [
            {"speaker": "warden", "text": "Three successful openings. One error. My verdict was corrupted. Gate restrictions revoked.", "mood": "warm"},
            {"speaker": "cipher", "text": "You repaired the guardian, {callsign}. The Monastery is open. Let's meet the people inside.", "mood": "warm"},
        ],
    },
    cutscene=Cutscene(
        title="THE MONASTERY OPENS",
        narration=[
            "WARDEN's red scan lines turn cyan. The corrupted verdict dissolves into the audit you rebuilt.",
            "The cooling tower's gate opens. Warm lamps reveal engineers working among cables, stone steps, and hanging gardens.",
            "WARDEN: Admission restored. Welcome to the Monastery, keeper of the Source.",
            "CIPHER: Out there, you learned to survive. In here, you'll learn what your code can change.",
        ],
        shot=("the same established hero from the avatar reference, seen in three-quarter profile at a massive "
              "cooling-tower gate opening into the Monastery; WARDEN's red hologram resolves to cyan above "
              "the doorway, amber workshop lamps illuminate robed engineers and hanging gardens beyond; "
              "rain on the hero's neural suit, cinematic 35mm lens, deep cyan shadows, warm sanctuary light"),
        camera="slow tracking shot behind the hero through the opening gate, rising to reveal the sanctuary",
        anchor=False,
    ),
)


def _derived(ctx, name, *sources):
    for source in sources:
        if not ctx.derived_from(name, source):
            raise Fail(f"`{name}` must be calculated using `{source}`, not typed in as a finished answer.",
                       hint=f"Keep the pipeline connected: use `{source}` on the right side of `{name} = ...`.")


@MISSION.check("Recover the raw gate record")
def _clean(ctx):
    if ctx.get("raw_log") != RAW_LOG:
        raise Fail("The scanner record was changed. Preserve the original evidence.",
                   hint="Restore raw_log from the starter; clean it into a new variable.")
    value = ctx.get("clean_log")
    ctx.expect_type("clean_log", value, str)
    _derived(ctx, "clean_log", "raw_log")
    if value != RAW_LOG.strip().lower():
        raise Fail("`clean_log` must be lowercase with no surrounding whitespace.",
                   hint="Chain .strip() and .lower() on raw_log, then save the returned string.")


@MISSION.check("Separate event labels and sample text")
def _split(ctx):
    expected = {"sections": ("clean_log", ["open,error,open,open", "12,20,17,24"]),
                "events": ("sections", ["open", "error", "open", "open"]),
                "samples": ("sections", ["12", "20", "17", "24"])}
    for name, (source, values) in expected.items():
        actual = ctx.get(name)
        ctx.expect_type(name, actual, list)
        _derived(ctx, name, source)
        if actual != values:
            raise Fail(f"`{name}` has the wrong pieces: {actual!r}.",
                       hint="Split clean_log on '|', then split section 0 and section 1 on commas. Positions start at zero.")


@MISSION.check("Repair numeric latency samples")
def _numbers(ctx):
    value = ctx.get("latencies")
    if type(value) is not list or any(type(item) is not int for item in value):
        raise Fail("`latencies` must be a list of four integers, not text joined by +.",
                   hint="Use square brackets and commas; wrap each samples[index] in int(...).")
    _derived(ctx, "latencies", "samples")
    if not ctx.call_uses("int", "samples") or value != [12, 20, 17, 24]:
        raise Fail("The four latency integers must come from converting the sample text in order.",
                   hint="Convert all four samples with int; keep their order and do not retype the numeric answers.")


@MISSION.check("Count openings and errors")
def _counts(ctx):
    value = ctx.get("counts")
    ctx.expect_type("counts", value, dict)
    _derived(ctx, "counts", "events")
    if value != {"open": 3, "error": 1} or any(type(v) is not int for v in value.values()):
        raise Fail(f"`counts` must account for three openings and one error; received {value!r}.",
                   hint="Use events.count('open') and events.count('error') under matching dictionary keys.")


@MISSION.check("Sum every latency sample")
def _total(ctx):
    value = ctx.get("total_latency")
    ctx.expect_type("total_latency", value, int)
    _derived(ctx, "total_latency", "latencies")
    if value != 73 or not ctx.call_uses("sum", "latencies"):
        raise Fail("`total_latency` must sum all four measurements, for a total of 73 ms.",
                   hint="sum(latencies) adds the list's numbers; len(latencies) only counts them.")


@MISSION.check("Find the fastest and slowest samples")
def _bounds(ctx):
    for name, function, expected in (("fastest", "min", 12), ("slowest", "max", 24)):
        value = ctx.get(name)
        ctx.expect_type(name, value, int)
        _derived(ctx, name, "latencies")
        if value != expected or not ctx.call_uses(function, "latencies"):
            raise Fail(f"`{name}` must use {function} on latencies and produce {expected} ms.",
                       hint=f"{function}(latencies) examines every sample, regardless of its position.")


@MISSION.check("Retain the fractional mean")
def _mean(ctx):
    value = ctx.get("mean_latency")
    _derived(ctx, "mean_latency", "total_latency", "latencies")
    if type(value) not in (int, float) or not math.isclose(value, 18.25):
        raise Fail("`mean_latency` must be 18.25 ms; rounding or floor division loses evidence.",
                   hint="Divide total_latency by len(latencies) using /, which keeps the fractional part.")
    if not ctx.call_uses("len", "latencies"):
        raise Fail("Calculate the sample count from the list rather than typing 4.",
                   hint="len(latencies) counts the measurements used by the mean.")


@MISSION.check("Broadcast the evidence report")
def _report(ctx):
    value = ctx.get("report")
    ctx.expect_type("report", value, dict)
    for source in ("events", "counts", "total_latency", "fastest", "slowest", "mean_latency"):
        _derived(ctx, "report", source)
    expected = {"events": 4, "counts": {"open": 3, "error": 1}, "total_ms": 73,
                "min_ms": 12, "max_ms": 24, "mean_ms": 18.25}
    if value != expected:
        raise Fail("`report` is missing an audit field or contains a mismatched value.",
                   hint="Use the six keys in objective 8, reading their values from the earlier variables.")
    line = "WARDEN AUDIT | events=4 | open=3 | error=1 | mean_ms=18.25"
    if not ctx.call_uses("print", "report") or line not in ctx.stdout.splitlines():
        raise Fail("WARDEN did not receive the expected audit line from `report`.",
                   hint="Print the objective 8 format using an f-string; read counts through report['counts']['open'] and ['error'].")
