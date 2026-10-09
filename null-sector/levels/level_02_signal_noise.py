"""Act I: decode the distress signal that leads to the Monastery."""
from engine.mission import Fail, Mission

RAW_SIGNAL = "  SOS::MONASTERY::SECTOR-0::GATE-7  "

MISSION = Mission(
    id="L02", slug="level_02_signal_noise", title="SIGNAL NOISE",
    concept="Strings & cleaning text", enemy="STATIC LEECH", xp=120,
    par_seconds=20 * 60, tier=1, concepts=("strings", "lists"),
    enemy_art="   .: /\\ :.\n  -- STATIC --\n   ': \\/ :'",
    briefing="""WATCHDOG's sweep fades behind you. A distress call claws through your visor:
too loud, badly padded, its separators doubled by interference.

CIPHER recognizes one word: **Monastery**. A sanctuary, if its gate still opens.
The STATIC LEECH feeds on malformed transmissions. Feed it clean text and it has
nothing left to eat. Recover the address before the signal disappears.

**Clean the signal, recover the coordinates, and broadcast your route.**""",
    why="""Search engines and language models ingest messy text. Spaces, casing, and
inconsistent separators can make two identical records look different. Cleaning
text and splitting it into useful pieces is a first step in a data pipeline.
Today your pipeline turns one noisy message into a usable destination.""",
    manual="""### 1. Clean without destroying the evidence
Strings cannot be changed in place. Methods return new text, so assign the result:
```python
raw = "  ALERT::DOCK  "
clean = raw.strip().lower().replace("::", "|")
# clean is "alert|dock"; raw still contains the original message
```
`strip()` trims the ends; `lower()` normalizes case; `upper()` does the opposite.

### 2. Split into fields, then index
`split(separator)` returns a list of text fields. Positions start at zero:
```python
fields = "alert|dock|east".split("|")
first = fields[0]    # "alert"
last = fields[-1]    # "east"
```

### 3. Slice and join
`items[start:stop]` includes start and excludes stop. Omit stop to keep the rest.
Strings and lists both support slicing. `separator.join(fields)` combines strings:
```python
route = "/".join(fields[1:])  # "dock/east"
area = route[:4]              # "dock"
```

### 4. Measure and search
`len(text)` counts characters, including separators. `in` produces a boolean:
```python
size = len(route)
has_dock = "dock" in route
```

### 5. Broadcast your computed values
An f-string inserts variables into text. Keep the address computed, not retyped:
```python
print(f"ROUTE {route}")
```
For this mission print exactly `ROUTE ` followed by your coordinates.""",
    starter='''"""L02 // SIGNAL NOISE — repair the transmission pipeline."""
# Scanner input: preserve this original evidence unchanged.
raw_signal = "  SOS::MONASTERY::SECTOR-0::GATE-7  "

# OBJECTIVE 1: Repair this corrupted cleanup. Strip padding, lowercase the text,
# and replace every double colon with |. Store the result in clean_signal.
clean_signal = raw_signal.strip()

# OBJECTIVE 2: Split clean_signal on | into a list named fields.
fields = []

# OBJECTIVE 3: Read destination from field index 1 (the sanctuary name).
destination = ""

# OBJECTIVE 4: Join the fields from index 2 onward with / into coordinates.
# Use a slice so the prefix fields are excluded.
coordinates = ""

# OBJECTIVE 5: Slice the first eight characters of coordinates into sector.
sector = ""

# OBJECTIVE 6: Use len(coordinates) to set coordinate_length.
coordinate_length = 0

# OBJECTIVE 7: Use `in` to test whether clean_signal contains "monastery".
has_sanctuary = False

# OBJECTIVE 8: Print ROUTE followed by a space and your computed coordinates.
print("ROUTE unknown")
''',
    dialogue={
        "intro": [
            {"speaker": "cipher", "text": "That signal is asking for help. Or baiting a trap. First, let's make it readable.", "mood": "neutral"},
            {"speaker": "cipher", "text": "The Monastery sheltered runners before the blackout. Its coordinates could get us off this street.", "mood": "warm"},
        ],
        "crash": [[{"speaker": "cipher", "text": "The signal survived. Your pipeline stopped. Read the error, then inspect the value on that line.", "mood": "neutral"}]],
        "fail": [[{"speaker": "cipher", "text": "Some noise remains. Check the first red layer; spaces and separators count as characters too.", "mood": "neutral"}]],
        "victory": [
            {"speaker": "cipher", "text": "Sector zero. Gate seven. A real address, buried under all that static.", "mood": "warm"},
            {"speaker": "rust", "text": "You decoded my beacon? Good. Gate's dead. Bring a working scrap kit and we'll discuss the keys.", "mood": "smirk"},
        ],
    },
)


def _value(ctx, name, expected, source, hint):
    value = ctx.get(name)
    ctx.expect_type(name, value, type(expected))
    if value != expected:
        raise Fail(f"`{name}` has the wrong value: {value!r}.", hint=hint)
    if not ctx.derived_from(name, source):
        raise Fail(f"Compute `{name}` from `{source}` so the pipeline follows its input.", hint=hint)


@MISSION.check("Clean the preserved signal")
def _clean(ctx):
    if ctx.get("raw_signal") != RAW_SIGNAL:
        raise Fail("The scanner input was changed.", hint="Restore raw_signal from the starter; clean a new string instead.")
    _value(ctx, "clean_signal", "sos|monastery|sector-0|gate-7", "raw_signal",
           "Chain strip(), lower(), and replace() on the original signal, assigning the returned string.")


@MISSION.check("Split the transmission into fields")
def _fields(ctx):
    _value(ctx, "fields", ["sos", "monastery", "sector-0", "gate-7"], "clean_signal",
           "Split clean_signal at each | separator; split returns a list.")


@MISSION.check("Identify the sanctuary")
def _destination(ctx):
    _value(ctx, "destination", "monastery", "fields", "Index the second field; the first index is zero.")


@MISSION.check("Rebuild the coordinates")
def _coordinates(ctx):
    _value(ctx, "coordinates", "sector-0/gate-7", "fields",
           "Slice fields from index 2 onward and join those strings with /.")


@MISSION.check("Extract the sector")
def _sector(ctx):
    _value(ctx, "sector", "sector-0", "coordinates", "Take the first eight characters of coordinates; the stop index is excluded.")


@MISSION.check("Measure the address")
def _length(ctx):
    _value(ctx, "coordinate_length", 15, "coordinates", "Use len() on coordinates, including the slash and hyphens.")
    if not ctx.call_uses("len", "coordinates"):
        raise Fail("Measure coordinates with len().", hint="Counting characters by hand breaks when the address changes.")


@MISSION.check("Confirm the sanctuary signal")
def _sanctuary(ctx):
    _value(ctx, "has_sanctuary", True, "clean_signal", 'Use "monastery" in clean_signal to obtain a bool.')


@MISSION.check("Broadcast the route")
def _broadcast(ctx):
    if ctx.stdout.strip() != "ROUTE sector-0/gate-7" or not ctx.call_uses("print", "coordinates"):
        raise Fail("The route broadcast is missing or malformed.", hint="Print ROUTE, a space, then the coordinates variable using an f-string.")
