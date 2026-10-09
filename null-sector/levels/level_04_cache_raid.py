"""LEVEL 04 // CACHE RAID — dictionaries, safe lookups and record updates."""
from engine.mission import Fail, Mission


CACHE = {"gate": "M-17", "district": "dead zone", "charge": "4", "owner": "LOCKSMITH"}

MISSION = Mission(
    id="L04", slug="level_04_cache_raid", title="CACHE RAID",
    concept="Dictionaries & lookups", enemy="LOCKSMITH.exe", xp=160,
    par_seconds=20 * 60, tier=1, concepts=("dicts", "types"),
    enemy_art="""\
     ▄████▄
    ██    ██
   ▄████████▄
   █   ▣    █
   ▀████████▀""",
    briefing="""\
RUST's fuse burns a narrow path through the scrapyard wall. Beyond it stands a cache kiosk,
still demanding payment from a city that no longer exists.

**LOCKSMITH.exe** keeps every access credential filed by name. Position means nothing here.
Ask for the wrong key and the kiosk kills the connection.

You find a gate code, an old charge reading and an owner field. RUST can sponsor a
temporary pass, but the original cache must remain untouched: LOCKSMITH checks its seal.

Above the kiosk, a camera turns toward the Monastery's closed gate.

**Read the cache, prepare a verified pass, and leave before the gate's WARDEN notices.**
""",
    why="""\
A dictionary connects a **key** to a **value**. API responses, model settings and dataset
records often arrive in this form:

```python
config = {"model": "small-net", "batch_size": 32}
model = config["model"]
retries = config.get("retries", 3)
```

Unlike a list index, a key tells you what a value means. Required fields use a direct
lookup. Optional fields need a sensible default. Copying a record before changing it
preserves the evidence you received from another system.
""",
    manual="""\
**1 · Dictionaries give values names.** Curly braces contain `key: value` pairs. Keys
are unique; a later assignment to the same key replaces its value:

```python
crate = {"label": "supplies", "units": "7"}
label = crate["label"]    # "supplies"
```

**2 · Lookups return the stored type.** A number scanned as text stays text until you
convert it. The conversion from COLD BOOT still applies:

```python
total_units = int(crate["units"]) + 2   # 9, an int
```

**3 · Optional keys need a fallback.** `crate["alarm"]` raises `KeyError` when that key
is absent. `.get(key, default)` returns the default without adding a key:

```python
alarm = crate.get("alarm", "quiet")    # "quiet"
```

**4 · Copy before editing.** `.copy()` makes a separate dictionary. These records hold
only text and numbers, so this copy is enough to keep changes separate:

```python
shipping = crate.copy()
shipping["label"] = "outbound"   # replace an existing value
shipping["sealed"] = True       # add a new key and a bool
```

**5 · Count and report.** `len(a_dict)` counts its keys. F-strings can use dictionary
lookups; use single quotes for keys inside a double-quoted f-string:

```python
field_count = len(shipping)
print(f"{shipping['label']}: {field_count} fields")
```
""",
    starter='''
"""LEVEL 04 // CACHE RAID                              TARGET: LOCKSMITH.exe
Read the sealed cache, then edit a separate working pass.
"""

# -- OBJECTIVE 1 -------------------------------------------------------------
# Keep this sealed cache unchanged, including its text charge reading.
cache = {"gate": "M-17", "district": "dead zone", "charge": "4", "owner": "LOCKSMITH"}
# Read its gate value into access_key. Do not type the code yourself.
# Example: label = crate["label"]


# -- OBJECTIVE 2 -------------------------------------------------------------
# Compute charge_total from the cache's text charge plus 6 fresh units.
# The result must be an int. Example: total_units = int(crate["units"]) + 2


# -- OBJECTIVE 3 // CORRUPTED CODE --------------------------------------------
# The optional alarm field is absent. This lookup crashes. Repair it using
# .get() with "silent" as the fallback; do NOT add an alarm key to cache.
# Example: alarm = crate.get("alarm", "quiet")
alarm = cache["alarm"]


# -- OBJECTIVE 4 -------------------------------------------------------------
# Copy cache into route. Set route's owner to "RUST" and its charge to
# your charge_total. The sealed cache must still name LOCKSMITH and store "4".
# Example: shipping = crate.copy(); shipping["label"] = "outbound"


# -- OBJECTIVE 5 -------------------------------------------------------------
# Add a verified key to route, holding the boolean True, not the text "True".
# Example: shipping["sealed"] = True


# -- OBJECTIVE 6 -------------------------------------------------------------
# Compute field_count from the number of keys in route; do not type the answer.
# Example: field_count = len(shipping)


# -- OBJECTIVE 7 -------------------------------------------------------------
# Print an f-string containing access_key, route's owner and field_count.
# Example: print(f"{shipping['label']}: {field_count} fields")

''',
    dialogue={
        "intro": [
            {"speaker": "rust", "mood": "neutral",
             "text": "LOCKSMITH doesn't count shelves. It names them. Gate. Charge. Owner. Ask for exactly what you need."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "A dictionary. Named keys lead to values. Leave the sealed record untouched and work on a copy."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "alarm",
              "text": "KeyError means the name you asked for is absent. Optional fields need a fallback."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "The kiosk gave you text on that charge label. Convert it before adding the six units I paid for."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Check the original cache. If it names RUST now, your pass and the sealed record are the same dictionary."}],
            [{"speaker": "rust", "mood": "neutral",
              "text": "Verified means True. The word in quotes is just ink on a forged pass."}],
        ],
        "victory": [
            {"speaker": "rust", "mood": "warm",
             "text": "M-17. My name on the pass, enough charge to reach it. Debt paid, {callsign}."},
            {"speaker": "cipher", "mood": "alarm",
             "text": "The outer lock accepted it. The gate's WARDEN is answering now. Its registry is corrupted."},
            {"speaker": "rust", "mood": "neutral",
             "text": "That's the Monastery behind those doors. People still learning to build things. Get them open."},
        ],
    },
)


def _dict(ctx, name):
    value = ctx.get(name)
    ctx.expect_type(name, value, dict)
    return value


@MISSION.check("Keep LOCKSMITH's seal — original cache")
def _cache(ctx):
    cache = _dict(ctx, "cache")
    if cache != CACHE:
        raise Fail("The sealed cache changed. Keep its four original fields, including owner LOCKSMITH and charge as text '4'.",
                   hint="Edit a dictionary copy. A missing optional field does not need to be inserted into the source.")


@MISSION.check("Read the named gate key — access_key")
def _key(ctx):
    value = ctx.get("access_key")
    ctx.expect_type("access_key", value, str)
    if value != "M-17":
        raise Fail(f"access_key is {value!r}; read the cache's gate field.",
                   hint="Dictionary square brackets take a key name, not a numeric position.")
    if not ctx.derived_from("access_key", "cache"):
        raise Fail("Read access_key from cache instead of retyping M-17.")


@MISSION.check("Recharge the pass — charge_total")
def _charge(ctx):
    value = ctx.get("charge_total")
    ctx.expect_type("charge_total", value, int)
    if value != 10:
        raise Fail(f"charge_total is {value}; the scanned 4 plus 6 fresh units makes 10.",
                   hint="Use int() on the text returned by the charge lookup before adding.")
    if not ctx.derived_from("charge_total", "cache"):
        raise Fail("Compute charge_total from the cache's charge reading instead of typing 10.")


@MISSION.check("Handle an absent field — alarm fallback")
def _alarm(ctx):
    value = ctx.get("alarm")
    ctx.expect_type("alarm", value, str)
    if value != "silent":
        raise Fail(f"alarm is {value!r}; absent alarm data must fall back to 'silent'.",
                   hint=".get() accepts the key name first and its fallback second.")
    if not ctx.derived_from("alarm", "cache"):
        raise Fail("Use a safe cache lookup for alarm instead of typing the fallback by itself.")


@MISSION.check("Prepare RUST's working copy — route")
def _route(ctx):
    route = _dict(ctx, "route")
    cache = _dict(ctx, "cache")
    if route is cache:
        raise Fail("route and cache are the same dictionary.", hint="Use the dictionary's .copy() method.")
    if not ctx.derived_from("route", "cache"):
        raise Fail("Build route from the cache rather than retyping all of its fields.")
    expected = {"gate": "M-17", "district": "dead zone", "charge": 10, "owner": "RUST"}
    for key, value in expected.items():
        if key not in route or type(route[key]) is not type(value) or route[key] != value:
            raise Fail(f"route[{key!r}] must be {value!r}; found {route.get(key)!r}.",
                       hint="Keep the gate and district, update the owner, and store the integer charge_total.")


@MISSION.check("Verify the pass — a boolean field")
def _verified(ctx):
    route = _dict(ctx, "route")
    if route.get("verified") is not True:
        raise Fail(f"route's verified value is {route.get('verified')!r}; it must be the boolean True.",
                   hint="Use capital-T True without quotation marks.")
    if set(route) != set(CACHE) | {"verified"}:
        raise Fail("route should contain the four cache keys plus verified, with no extra fields.")


@MISSION.check("Count the named fields — field_count")
def _count(ctx):
    value = ctx.get("field_count")
    ctx.expect_type("field_count", value, int)
    if value != 5:
        raise Fail(f"field_count is {value}; the pass has four original keys and one verification key.")
    if not ctx.derived_from("field_count", "route"):
        raise Fail("Compute field_count from route instead of typing 5.",
                   hint="len(a_dictionary) counts its keys.")


@MISSION.check("Present the gate pass — print()")
def _broadcast(ctx):
    for name in ("access_key", "route", "field_count"):
        if not ctx.call_uses("print", name):
            raise Fail(f"The printed pass must use {name}.",
                       hint="Print an f-string with access_key, route's owner lookup and field_count.")
    for value in ("M-17", "RUST", "5"):
        if value not in ctx.stdout:
            raise Fail(f"The printed pass is missing {value!r}.")
