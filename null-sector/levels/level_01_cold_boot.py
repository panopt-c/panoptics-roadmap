"""LEVEL 01 // COLD BOOT — variables & the four core data types."""
import math

from engine.mission import Cutscene, Fail, Mission

MISSION = Mission(
    id="L01",
    slug="level_01_cold_boot",
    title="COLD BOOT",
    concept="Variables & data types",
    enemy="WATCHDOG.exe",
    xp=100,
    par_seconds=15 * 60,
    enemy_art="""\
   ▄██████▄
 ▄██▀    ▀██▄
███  ▄██▄  ███
 ▀██▄ ▀▀ ▄██▀
   ▀██████▀""",
    briefing="""\
You come online in the dark.

Server racks hum around you, half of them bleeding red error light. Somewhere above,
a process called **WATCHDOG.exe** is sweeping the sector, deleting anything it can't identify.

Your neural suit is blank. No name. No vitals. To WATCHDOG you don't exist — and things
that don't exist get deleted.

**Write yourself into existence before the sweep reaches you.**
""",
    why="""\
Every AI system starts as a handful of named values. Open almost any model-training
script and the first lines look like this:

```python
model_name = "resnet50"
learning_rate = 0.001
batch_size = 32
use_gpu = True
```

That's four variables, one of each core type: **str, float, int, bool**. The same four you'll use today.

Types matter more than they look. Data from files, APIs and the web usually arrives as
**text**. A model can't learn from `"12"`, only from `12`. Converting it is a daily part
of an ML engineer's job, called *data cleaning*.
""",
    manual="""\
**A variable is a label stuck on a value.** `=` means *store*, not *equals*:

```python
weapon = "plasma cutter"   # str   — text, always inside quotes
ammo = 12                  # int   — a whole number
shield = 0.8               # float — a decimal
is_cloaked = False         # bool  — True or False (capital letter, no quotes)
```

**Compute new values from old ones** so they stay correct when the inputs change:

```python
ammo_missing = 30 - ammo   # 18
```

**Text and numbers don't mix.** `"12"` is text; `12` is a number:

```python
"12" + 8          # crash: TypeError
int("12") + 8     # 20 — convert the text to a number first
```

**Print with an f-string.** The `f` lets you drop variables inside `{}`:

```python
print(f"Weapon ready: {weapon}")    # Weapon ready: plasma cutter
```
""",
    starter='''
"""
==============================================================================
  LEVEL 01 // COLD BOOT                              TARGET: WATCHDOG.exe
==============================================================================
  Complete each objective, save, then HACK from the game.
  Fastest loop:  python game.py watch   (every save auto-attacks)
"""

# -- OBJECTIVE 1 -------------------------------------------------------------
# Create a variable named `callsign` holding your hacker name as TEXT (a str).
# Text always goes inside quotes.          example:  weapon = "plasma cutter"



# -- OBJECTIVE 2 -------------------------------------------------------------
# Your suit's frame is undamaged. Create `integrity` and set it to the
# WHOLE number 100 (an int, no quotes).



# -- OBJECTIVE 3 -------------------------------------------------------------
# Your battery is at 35%. Store it as a DECIMAL between 0 and 1 (a float):
# create `battery` and set it to 0.35



# -- OBJECTIVE 4 -------------------------------------------------------------
# Is your suit online? Yes. Create `is_online` holding the boolean True.
# Booleans are exactly True or False: capital letter, no quotes.



# -- OBJECTIVE 5 -------------------------------------------------------------
# How much charge do you still need to reach full (1.0)?
# Create `power_needed` by DOING MATH with your `battery` variable.
# Don't type the answer yourself, calculate it.   example:  missing = 30 - ammo



# -- OBJECTIVE 6 // CORRUPTED CODE --------------------------------------------
# You found a supply crate. Its label was scanned as TEXT, not a number,
# and the second line below crashes. Hack once, read the COMBAT LOG, then fix it.
# Rule: don't change the crate data itself. Fix the line that uses it.
scrap_from_crate = "12"
scrap_total = scrap_from_crate + 8



# -- OBJECTIVE 7 -------------------------------------------------------------
# Broadcast your identity so the network registers you:
# print() an f-string that includes your `callsign` variable.
#                                  example:  print(f"Weapon ready: {weapon}")

''',
    cutscene=Cutscene(
        title="IDENTITY ACCEPTED",
        narration=[
            "WATCHDOG.exe hesitates... then turns away. You're on the registry now.",
            "Your visor flickers on. In a cracked server panel, you see your own reflection for the first time.",
            "Battery at 35%. The Dead Zone stretches out in every direction.",
            "Somewhere past it, the Core is still running. Whatever broke this world is in there.",
        ],
        shot=("waist-up portrait of the hero standing in the ruins of a flooded data center, "
              "face lit from below by a visor powering on, their reflection visible in a cracked server panel, "
              "looking straight into the lens"),
        camera="slow dolly-in toward the face as the visor flickers on",
        anchor=True,
    ),
    tier=1,
    concepts=("variables", "types"),
    dialogue={
        "intro": [
            {"speaker": "cipher", "text": "You're awake. Good. I'm CIPHER, the only thing still running in your visor.", "mood": "neutral"},
            {"speaker": "cipher", "text": "WATCHDOG deletes anything without an identity. Give it one: a name, some numbers, a status. In code.", "mood": "alarm"},
            {"speaker": "cipher", "text": "Every value you store is a variable. Start there. I'll read the errors with you.", "mood": "warm"},
        ],
        "crash": [
            [{"speaker": "cipher", "text": "Crash. Not fatal. Read the last line of the error first: Python tells you what it couldn't do.", "mood": "neutral"}],
            [{"speaker": "cipher", "text": "The line number in the combat log is where it broke. Start reading there, then look one line up.", "mood": "neutral"}],
        ],
        "fail": [
            [{"speaker": "cipher", "text": "The script ran, but WATCHDOG isn't convinced. Check the first red layer. Types matter: 12 and \"12\" are different.", "mood": "neutral"}],
            [{"speaker": "cipher", "text": "Close. Compare what the hint asks for with what you stored. Exact names, exact types.", "mood": "warm"}],
        ],
        "victory": [
            {"speaker": "cipher", "text": "Identity registered, {callsign}. WATCHDOG has moved on.", "mood": "warm"},
            {"speaker": "cipher", "text": "There's a signal on the wire. Someone out there is still broadcasting. Let's find out who.", "mood": "neutral"},
        ],
    },
)


@MISSION.check("Register identity — `callsign`")
def _callsign(ctx):
    value = ctx.get("callsign")
    ctx.expect_type("callsign", value, str)
    if not value.strip():
        raise Fail("`callsign` is an empty string.", hint='Put your name between the quotes: callsign = "Nyx"')
    ctx.export("callsign", value.strip()[:24])


@MISSION.check("Frame integrity — `integrity`")
def _integrity(ctx):
    value = ctx.get("integrity")
    ctx.expect_type("integrity", value, int)
    if value != 100:
        raise Fail(f"`integrity` is {value}. Your frame is undamaged, so it should be 100.")


@MISSION.check("Battery reading — `battery`")
def _battery(ctx):
    value = ctx.get("battery")
    if type(value) is int and value == 35:
        raise Fail("`battery` is 35, but it needs to be a fraction between 0 and 1.",
                   hint="35% as a decimal is 0.35")
    ctx.expect_type("battery", value, float)
    if not math.isclose(value, 0.35):
        raise Fail(f"`battery` is {value}. The reading says 35%, which is 0.35.")


@MISSION.check("Suit status — `is_online`")
def _online(ctx):
    value = ctx.get("is_online")
    ctx.expect_type("is_online", value, bool)
    if value is not True:
        raise Fail("`is_online` is False. Your suit IS online.")


@MISSION.check("Power calculation — `power_needed`")
def _power(ctx):
    value = ctx.get("power_needed")
    if not ctx.derived_from("power_needed", "battery"):
        raise Fail("You typed the number in yourself. WATCHDOG flags hard-coded values as tampering.",
                   hint="Calculate it from the `battery` variable: full charge (1.0) minus battery.")
    if type(value) not in (int, float):
        ctx.expect_type("power_needed", value, float)
    if not math.isclose(value, 0.65):
        raise Fail(f"`power_needed` came out as {value}, but full (1.0) minus 35% should be 0.65.")


@MISSION.check("Repair corrupted crate scan — `scrap_total`")
def _scrap(ctx):
    crate = ctx.get("scrap_from_crate")
    if crate != "12":
        raise Fail("You changed the crate data. In the real world you can't edit what the scanner gives you.",
                   hint='Keep  scrap_from_crate = "12"  and convert it on the line below.')
    value = ctx.get("scrap_total")
    if value == "128":
        raise Fail('`scrap_total` is "128". Python glued two pieces of text together instead of adding numbers.',
                   hint='int("12") turns the text "12" into the number 12.')
    ctx.expect_type("scrap_total", value, int)
    if value != 20:
        raise Fail(f"`scrap_total` is {value}. 12 scrap from the crate plus 8 should be 20.")


@MISSION.check("Broadcast to the network — print()")
def _broadcast(ctx):
    if not ctx.stdout.strip():
        if ctx.crashed:
            raise Fail("Nothing was broadcast. Your script crashed before it reached the print().")
        raise Fail("Nothing was printed.", hint='print(f"... {callsign} ...")')
    if not ctx.call_uses("print", "callsign"):
        raise Fail("Your print() doesn't use the `callsign` variable. Don't retype your name; reference the variable.",
                   hint='Put it in an f-string: print(f"{callsign} online")')
    callsign = ctx.ns.get("callsign")
    if isinstance(callsign, str) and callsign.strip() and callsign.strip() not in ctx.stdout:
        raise Fail("Your callsign didn't show up in the printed output.")
