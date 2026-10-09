"""LEVEL 03 // SCRAP INVENTORY — lists, indexing, slices and independent copies."""
from engine.mission import Fail, Mission


SCAN = ["wire", "battery", "cracked optic", "relay"]
PACKED = ["wire", "battery", "lens", "relay", "fuse"]

MISSION = Mission(
    id="L03", slug="level_03_scrap_inventory", title="SCRAP INVENTORY",
    concept="Lists, indexing & slicing", enemy="SORTER.daemon", xp=140,
    par_seconds=20 * 60, tier=1, concepts=("lists",),
    enemy_art="""\
  ▄▄▄▄▄▄▄▄▄▄▄
  █ ▣ ▣ ▣ ▣ █
  █▄▄▄▄▄▄▄▄▄█
   ▀█▀   ▀█▀""",
    briefing="""\
You follow the cleaned signal through a scrapyard of dead courier drones. A man under a
patched welding hood steps between you and the exit.

"RUST. I trade parts for working code. Yours work?"

His sorting machine has confused its inventory with its scanner record. Repair one part
and the evidence changes too. Behind it, a crusher starts its next cycle.

RUST offers you a replacement optic, a fuse, and the location of a LOCKSMITH access cache.
First you owe him a manifest that keeps the original scan intact.

**Repair the inventory, pack the field kit, and earn your way out of the yard.**
""",
    why="""\
A list keeps related values in order. AI programs use lists for documents, tokens,
feature names and batches of examples:

```python
features = ["temperature", "pressure", "humidity"]
first_feature = features[0]
small_batch = features[:2]
```

An index selects one item; a slice selects a group. These operations appear everywhere
in data preparation. Copies matter too: changing a working batch should not silently
rewrite your original dataset. Today the dataset is RUST's salvage manifest.
""",
    manual="""\
**1 · Lists preserve order.** Square brackets hold items separated by commas. Counting
starts at **zero**, and `-1` means the last item:

```python
tools = ["wrench", "torch", "scanner"]
first = tools[0]      # "wrench"
last = tools[-1]      # "scanner"
```

**2 · Replace one item; append a new one.** Assign through an index to replace an item.
`.append(...)` changes the list and returns `None`, so do not assign its result:

```python
tools[1] = "cutter"   # replace the torch
tools.append("cable") # add a fourth item
```

**3 · A slice makes a smaller list.** `[start:stop]` includes `start` but stops BEFORE
`stop`. Leave an end blank to go all the way to that end:

```python
middle = tools[1:3]   # items at indexes 1 and 2
first_two = tools[:2]
```

**4 · A second name is not a copy.** `working = tools` points both names at one list.
Changing either changes that same list. `tools[:]` makes a separate list:

```python
working = tools[:]
working.append("gloves")  # tools stays unchanged
```

**5 · Count and report.** `len(...)` counts items, even when the list grows. An f-string
can include the selected items and their count:

```python
tool_count = len(tools)
print(f"Packed {tool_count} tools; first: {first}")
```
""",
    starter='''
"""LEVEL 03 // SCRAP INVENTORY                         TARGET: SORTER.daemon
Complete the objectives in order. Keep the scanner data unchanged.
"""

# -- OBJECTIVE 1 // CORRUPTED CODE --------------------------------------------
# This is the scanner's original record. Do not edit or mutate it.
scanned_parts = ["wire", "battery", "cracked optic", "relay"]
# BUG: both names below point at the SAME list. Repair the assignment so
# inventory is an independent copy. Example: working = tools[:]
inventory = scanned_parts

# -- OBJECTIVE 2 -------------------------------------------------------------
# Replace "cracked optic" in inventory with "lens" by assigning at its index.
# Counting starts at zero. Example: tools[1] = "cutter"


# -- OBJECTIVE 3 -------------------------------------------------------------
# Append "fuse" to inventory. Do not assign the return value of append().
# Example: tools.append("cable")


# -- OBJECTIVE 4 -------------------------------------------------------------
# AFTER the repairs, read the first and last inventory items into
# first_part and last_part. Example: first = tools[0]; last = tools[-1]


# -- OBJECTIVE 5 -------------------------------------------------------------
# Slice inventory to create field_kit containing the battery, lens and relay.
# Include indexes 1 through 3. A slice stops BEFORE its second index.
# Example: middle = tools[1:3]


# -- OBJECTIVE 6 -------------------------------------------------------------
# Make reserve an independent copy of the completed inventory, then append
# "spare wire" to reserve only. inventory must remain unchanged.
# Example: working = tools[:]; working.append("gloves")


# -- OBJECTIVE 7 -------------------------------------------------------------
# Compute part_count from the length of inventory; do not type the answer.
# Example: tool_count = len(tools)


# -- OBJECTIVE 8 -------------------------------------------------------------
# Print an f-string using first_part, last_part and part_count so RUST can
# read all three. Example: print(f"Packed {tool_count}; first: {first}")

''',
    dialogue={
        "intro": [
            {"speaker": "rust", "mood": "smirk",
             "text": "You followed a distress signal into my scrapyard. Brave. Or bad at directions."},
            {"speaker": "rust", "mood": "neutral",
             "text": "Fix the sorter and you get parts. Fix it without eating my scanner record and you get a way forward."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "An ordered list. One item per slot. Start counting at zero, {callsign}."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Sorter stopped. Read the line in the COMBAT LOG: an index outside the list has no item to return."}],
            [{"speaker": "rust", "mood": "neutral",
              "text": "If your inventory turned into None, you stored append's receipt instead of keeping the list."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Two labels can point at one list. A full slice gives you a separate working copy."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "A slice stops before the second number. Leave my relay in the kit, not on the floor."}],
        ],
        "victory": [
            {"speaker": "rust", "mood": "warm",
             "text": "Original scan intact. Parts counted. You might be worth more than your scrap value."},
            {"speaker": "rust", "mood": "neutral",
             "text": "LOCKSMITH keeps gate keys in a cache beyond that wall. Take the fuse. You'll need the door open."},
            {"speaker": "cipher", "mood": "warm",
             "text": "The sanctuary is closer. Now we need a name for each key, not just a place in a list."},
        ],
    },
)


def _list(ctx, name):
    value = ctx.get(name)
    ctx.expect_type(name, value, list)
    return value


@MISSION.check("Preserve the scanner record — independent inventory")
def _scan(ctx):
    original = _list(ctx, "scanned_parts")
    inventory = _list(ctx, "inventory")
    if original != SCAN:
        raise Fail("The scanner record changed. Repairs belong in inventory, not scanned_parts.",
                   hint="A plain assignment shares one list. Copy all of its items with a full slice.")
    if inventory is original:
        raise Fail("inventory and scanned_parts still name the same list.",
                   hint="Use [:] on the source list to make an independent copy.")
    if not ctx.derived_from("inventory", "scanned_parts"):
        raise Fail("Build inventory from scanned_parts instead of retyping the scan.")


@MISSION.check("Repair the cracked optic — indexed replacement")
def _repair(ctx):
    inventory = _list(ctx, "inventory")
    if inventory[:4] != PACKED[:4]:
        raise Fail(f"The first four inventory items are {inventory[:4]!r}; keep wire, battery and relay, and replace only the cracked optic with lens.",
                   hint="The third item is index 2. Assignment through an index replaces that item.")


@MISSION.check("Collect the fuse — append once")
def _fuse(ctx):
    inventory = _list(ctx, "inventory")
    if len(inventory) != 5 or inventory[-1] != "fuse":
        raise Fail(f"inventory should have five items with fuse last; found {inventory!r}.",
                   hint="Append one fuse after repairing the optic. Do not assign append's result.")


@MISSION.check("Read both ends — first_part and last_part")
def _ends(ctx):
    for name, expected in (("first_part", "wire"), ("last_part", "fuse")):
        value = ctx.get(name)
        ctx.expect_type(name, value, str)
        if value != expected:
            raise Fail(f"{name} is {value!r}; expected {expected!r} after the fuse is added.",
                       hint="Index 0 reads the first item; index -1 reads the last.")
        if not ctx.derived_from(name, "inventory"):
            raise Fail(f"Read {name} from inventory instead of typing its text.")


@MISSION.check("Pack the middle three — field_kit")
def _kit(ctx):
    kit = _list(ctx, "field_kit")
    if kit != ["battery", "lens", "relay"]:
        raise Fail(f"field_kit is {kit!r}; it needs battery, lens and relay, in that order.",
                   hint="Start at index 1. Include index 3 by stopping at the following index.")
    if not ctx.derived_from("field_kit", "inventory"):
        raise Fail("Take field_kit from inventory instead of writing a new literal list.",
                   hint="A slice extracts a range of existing items.")


@MISSION.check("Keep the spare separate — reserve")
def _reserve(ctx):
    reserve = _list(ctx, "reserve")
    inventory = _list(ctx, "inventory")
    if reserve is inventory or inventory != PACKED:
        raise Fail("Adding the spare changed the main inventory.",
                   hint="Copy inventory before appending to reserve. A second variable name alone does not copy.")
    if reserve != PACKED + ["spare wire"]:
        raise Fail(f"reserve is {reserve!r}; it needs the five inventory items followed by spare wire.")
    if not ctx.derived_from("reserve", "inventory"):
        raise Fail("Make reserve from inventory so it carries the repaired parts.")


@MISSION.check("Count the shipment — part_count")
def _count(ctx):
    value = ctx.get("part_count")
    ctx.expect_type("part_count", value, int)
    if value != 5:
        raise Fail(f"part_count is {value}; the main inventory has five parts, excluding the spare.")
    if not ctx.derived_from("part_count", "inventory"):
        raise Fail("Compute part_count from inventory rather than typing 5.",
                   hint="len(a_list) returns its current number of items.")


@MISSION.check("Deliver RUST's manifest — print()")
def _broadcast(ctx):
    for name, text in (("first_part", "wire"), ("last_part", "fuse"), ("part_count", "5")):
        if not ctx.call_uses("print", name):
            raise Fail(f"The manifest must print the {name} variable.",
                       hint="Put all three variables into the braces of an f-string passed to print().")
        if text not in ctx.stdout:
            raise Fail(f"The printed manifest is missing {text!r}.")
