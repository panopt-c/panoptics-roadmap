"""LEVEL 11 // BLUEPRINTS — classes, __init__, attributes, methods, __repr__."""
from __future__ import annotations

import ast

from engine.mission import Fail, Mission

MISSION = Mission(
    id="L11",
    slug="level_11_blueprints",
    title="BLUEPRINTS",
    concept="Classes & objects",
    enemy="RECLAIM.daemon",
    xp=230,
    par_seconds=30 * 60,
    tier=3,
    concepts=("classes",),
    enemy_art="""\
  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄
 █▌ ▀▀▀▀▀▀▀▀▀▀ ▐█
 █  ▓▓▓▓  ▓▓▓▓  █
 █▄▄▄▄▄▄▄▄▄▄▄▄▄▄█
  ▀█▀▀█▀▀█▀▀█▀▀█▀
   ▀  ▀  ▀  ▀  ▀""",
    briefing="""\
The Foundry never stopped working. Nobody told it the world ended.

Furnaces still breathe orange through the smog. A conveyor carries dead Order drones, hundreds
of them, toward the jaws of **RECLAIM.daemon**, a recycler that melts down any machine without
a valid blueprint.

RUST hauls one off the belt. Same chassis, same scars as the rest. "Their firmware was one
blueprint," he says. "Lose the blueprint, lose the fleet."

One design, every drone stamped from it. In Python, that's a **class**.

**Write the blueprint and bring the squadron back online before the belt reaches the smelter.**
""",
    why="""\
Every serious AI library is built from classes. A PyTorch model is a class, and each model you
create is an **object** stamped from it, carrying its own weights:

```python
class Classifier:
    def __init__(self, n_inputs):
        self.weights = [0.0] * n_inputs   # every model keeps its own
        self.trained = False

    def predict(self, x):
        return sum(w * xi for w, xi in zip(self.weights, x))

model = Classifier(3)
model.predict([1.0, 2.0, 0.5])
```

A class bundles **data** (attributes) with the **behaviour** that uses it (methods), so a
hundred models never trip over each other's numbers. And `__repr__` is why printing a model in a
notebook shows something useful instead of `<object at 0x7f3a…>`. At 3 a.m., mid-debug, that
matters.
""",
    manual="""\
**A class is a blueprint. An object is one thing built from it.** Call the class like a
function to build a new object:

```python
class Crate:
    pass

a = Crate()      # one crate
b = Crate()      # a second, completely separate crate
```

**`__init__` sets up each new object.** Python runs it automatically when you build one.
`self` is the object being built; `self.something = ...` attaches data to it (an **attribute**):

```python
class Crate:
    def __init__(self, label, weight=10):   # defaults work like in any function
        self.label = label
        self.weight = weight
        self.tags = []                      # a brand-new list for EVERY crate

ammo = Crate("ammo", 25)
ammo.label              # 'ammo'
Crate("rope").weight    # 10, the default
```

Never write `def __init__(self, tags=[])`: that single default list would be shared by every
crate ever built. Create fresh lists inside `__init__`.

**Methods are functions inside the class.** Their first parameter is always `self`. When you
call `ammo.add_tag("fragile")`, Python passes `ammo` in as `self` for you:

```python
    def add_tag(self, tag):
        self.tags.append(tag)
        return len(self.tags)

    def lighten(self, amount):
        self.weight = max(0, self.weight - amount)   # change the object's OWN data
```

Inside a method, `weight = 5` (no `self.`) makes a throwaway local variable that vanishes when
the method returns. To change the object, write to `self.weight`.

**`__repr__` is how an object describes itself.** It must *return* a string. `print()` and the
REPL use it:

```python
    def __repr__(self):
        return f"Crate(label='{self.label}', weight={self.weight})"

print(Crate("ammo", 25))     # Crate(label='ammo', weight=25)
```

Without it you get `<__main__.Crate object at 0x7f3a…>`.

**Reading the classic class crash:**

```text
TypeError: Crate.add_tag() takes 1 positional argument but 2 were given
```

You passed one argument, but Python also passes the object itself, so that's two. The method
forgot `self` as its first parameter.
""",
    starter='''
"""
==============================================================================
  LEVEL 11 // BLUEPRINTS                             TARGET: RECLAIM.daemon
==============================================================================
  Every drone in the Order's fleet is stamped from ONE blueprint: a class.
  Write it, then build the squadron. Save, then HACK from the game.
  The grader builds its OWN drones from your class with fresh names and
  numbers, so the blueprint has to work for any drone, not just yours.
"""


class Drone:
    """Blueprint for an Order drone."""

    # -- OBJECTIVE 1 ---------------------------------------------------------
    # Write __init__(self, name, battery=100). It must store three attributes:
    #   self.name     the name it was given
    #   self.battery  the battery it was given (100 if none was passed)
    #   self.cargo    a NEW empty list, so every drone has its own hold
    #
    #   example:   def __init__(self, label, weight=10):
    #                  self.label = label
    #                  self.weight = weight
    #                  self.tags = []



    # -- OBJECTIVE 2 ---------------------------------------------------------
    # Write charge(self, amount): add `amount` to self.battery, but a
    # battery can never go above 100.
    #   Drone("Kite", 70), then .charge(20)  ->  battery is 90
    #   Drone("Kite", 90), then .charge(20)  ->  battery is 100, not 110



    # -- OBJECTIVE 3 ---------------------------------------------------------
    # Write fly(self, distance): flying costs 2 battery per km.
    #   Enough battery?  subtract the cost and return True.
    #   Not enough?      change nothing and return False.
    #   Drone("Kite", 30).fly(10)  ->  True, battery is now 10
    #   Drone("Kite", 10).fly(6)   ->  False, battery stays 10 (it needs 12)



    # -- OBJECTIVE 4 ---------------------------------------------------------
    # Write __repr__(self) so a drone describes itself in exactly this format:
    #   Drone(name='Kite', battery=80)
    # It must RETURN that text, not print it.



    # -- OBJECTIVE 5 // CORRUPTED CODE ----------------------------------------
    # RUST bolted on a cargo method from an old drone. It should put `item`
    # in THIS drone's cargo and return how many items the drone now holds.
    # Calling it crashes. Hack once, read the error, and fix it.
    def load(item):
        self.cargo.append(item)
        return len(self.cargo)


# -- OBJECTIVE 6 -------------------------------------------------------------
# Build the squadron from your blueprint:
#   `scout`  : a Drone named "Kite" with 80 battery
#   `hauler` : a Drone named "Mule" that uses the DEFAULT battery
# Then load "relay chip" into the hauler with its load() method.
#                                     example:  ammo = Crate("ammo", 25)



# -- OBJECTIVE 7 -------------------------------------------------------------
# Broadcast the scout's identity: print the `scout` object itself.
# (print() asks your __repr__ for the text.)

''',
    dialogue={
        "intro": [
            {"speaker": "rust", "mood": "neutral",
             "text": "Order drones. Good chassis, dead firmware. RECLAIM wants every one of them for slag."},
            {"speaker": "rust", "mood": "smirk",
             "text": "Write me a blueprint, {callsign}. One class, and I'll stamp out a whole squadron."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "A class is the mould, an object is the casting. Get the mould right and every casting comes out right."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "alarm",
              "text": "The blueprint cracked mid-stamp. The COMBAT LOG has the exact line."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "'takes 1 positional argument but 2 were given' is Python saying a method forgot self."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "Drone's twitching. Not flying, but twitching. Read the log."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader builds its own drones from your class. If it only works for Kite, it doesn't work."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Inside a method, a name without self. is a local. It evaporates the moment the method returns."}],
            [{"speaker": "rust", "mood": "neutral",
              "text": "Belt's still moving, {callsign}. Fix the layer it's yelling about. One at a time."}],
        ],
        "victory": [
            {"speaker": "cipher", "mood": "warm",
             "text": "RECLAIM.daemon released the line. It recognises the blueprint now. So do the drones."},
            {"speaker": "rust", "mood": "smirk",
             "text": "Kite and Mule, flying again. I'll print fifty more off your class. Pleasure doing business."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Next lesson: not every drone should be the same. The Foundry kept bloodlines."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

def _hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, TypeError) and "takes no arguments" in msg:
        return "Python can't find your __init__. Check the spelling: two underscores on each side, __init__."
    if isinstance(exc, TypeError) and "positional argument" in msg and "were given" in msg:
        return "Every method needs `self` as its FIRST parameter: Python passes the drone in automatically."
    if isinstance(exc, TypeError) and "missing" in msg and "required" in msg:
        return "A parameter has no value. Defaults go in the def line, like  def __init__(self, name, battery=100):"
    if isinstance(exc, NameError) and "self" in msg:
        return "`self` only exists inside a method that lists it as its first parameter."
    if isinstance(exc, AttributeError):
        return "Attributes are created in __init__ with  self.name = ...  and read back as self.name."
    return "Build a drone at the bottom of your file and call the same thing to see the full error."


def _top_level(ctx, kinds, name: str):
    """The last top-level definition called `name` (the one Python actually kept)."""
    found = [n for n in ctx.tree.body if isinstance(n, kinds) and n.name == name]
    return found[-1] if found else None


def _drone_class(ctx) -> type:
    if "Drone" not in ctx.ns:
        if ctx.crashed and _top_level(ctx, ast.ClassDef, "Drone"):
            raise Fail("`Drone` is in your file, but the script crashed before Python built it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail("No class named `Drone` found.", hint="The blueprint starts with  class Drone:")
    cls = ctx.ns["Drone"]
    if not isinstance(cls, type):
        raise Fail("`Drone` exists but isn't a class.", hint="Define the blueprint with  class Drone:")
    return cls


def _build(cls, *args):
    shown = ", ".join(repr(a) for a in args)
    try:
        return cls(*args)
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"Building `Drone({shown})` crashed: {type(exc).__name__}: {exc}", hint=_hint(exc))


def _method(ctx, drone, name: str):
    fn = getattr(drone, name, None)
    if callable(fn):
        return fn
    if _top_level(ctx, ast.FunctionDef, name):
        raise Fail(f"`{name}()` is written OUTSIDE the class, so drones don't have it.",
                   hint="Methods belong inside the class: indent the whole def one level under  class Drone:")
    raise Fail(f"Drones don't have a `{name}()` method yet.",
               hint=f"Inside the class, indented:  def {name}(self, ...):")


def _call(label: str, fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}", hint=_hint(exc))


def _attr(drone, attr: str, label: str):
    if not hasattr(drone, attr):
        raise Fail(f"{label} has no `{attr}` attribute.", hint=f"Store it in __init__:  self.{attr} = ...")
    return getattr(drone, attr)


def _method_called(tree: ast.AST, obj: str, method: str) -> bool:
    """True if the code calls `obj.method(...)` somewhere."""
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == method
               and isinstance(n.func.value, ast.Name) and n.func.value.id == obj
               for n in ast.walk(tree))


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Blueprint — `Drone.__init__` stores name, battery, cargo")
def _init(ctx):
    Drone = _drone_class(ctx)
    wren = _build(Drone, "Wren", 55)
    name = _attr(wren, "name", 'Drone("Wren", 55)')
    battery = _attr(wren, "battery", 'Drone("Wren", 55)')
    cargo = _attr(wren, "cargo", 'Drone("Wren", 55)')
    if name != "Wren":
        raise Fail(f'Drone("Wren", 55).name is {name!r}, expected \'Wren\'.',
                   hint="Store the parameter, not a fixed value:  self.name = name")
    if battery != 55:
        raise Fail(f'Drone("Wren", 55).battery is {battery!r}, expected 55.',
                   hint="Store the parameter that was passed in:  self.battery = battery")
    if not isinstance(cargo, list):
        raise Fail(f"`cargo` should be a list, but it's {type(cargo).__name__}.", hint="self.cargo = []")
    if cargo:
        raise Fail(f"A brand-new drone already has cargo: {cargo!r}. Every drone should start empty.")
    pip = _build(Drone, "Pip")
    if getattr(pip, "battery", None) != 100:
        raise Fail(f'Drone("Pip") has battery {getattr(pip, "battery", None)!r}. Without a battery argument '
                   "it should default to 100.", hint="Give the parameter a default:  battery=100")


@MISSION.check("Separate holds — every drone gets its own `cargo`")
def _separate(ctx):
    Drone = _drone_class(ctx)
    ash, birch = _build(Drone, "Ash", 40), _build(Drone, "Birch", 60)
    a_cargo, b_cargo = _attr(ash, "cargo", "A drone"), _attr(birch, "cargo", "A drone")
    if a_cargo is b_cargo:
        raise Fail("Two different drones share ONE cargo list: load one and the other fills up too.",
                   hint="Create the list inside __init__ (self.cargo = []), not as a default parameter "
                        "or a variable written directly under `class Drone:`.")
    if getattr(ash, "name", None) == getattr(birch, "name", None):
        raise Fail("Two drones built with different names ended up with the same name.",
                   hint="self.name = name  stores whatever name each drone was given.")


@MISSION.check("Recharge — `charge()` tops up but caps at 100")
def _charge(ctx):
    Drone = _drone_class(ctx)
    volt = _build(Drone, "Volt", 40)
    charge = _method(ctx, volt, "charge")
    _call('Drone("Volt", 40).charge(25)', charge, 25)
    if volt.battery == 40:
        raise Fail("charge(25) left the battery at 40. Nothing changed on the drone.",
                   hint="`battery = ...` inside a method only makes a local variable. Write to self.battery.")
    if volt.battery != 65:
        raise Fail(f'Drone("Volt", 40).charge(25) left battery at {volt.battery!r}, expected 65.')
    _call("charge(50)", charge, 50)
    if volt.battery != 100:
        raise Fail(f"A drone at 65 charged by 50 ended at {volt.battery!r}. Batteries cap at 100.",
                   hint="min() picks the smaller of two numbers: the new total, or 100.")
    ember = _build(Drone, "Ember", 97)
    _call('Drone("Ember", 97).charge(3)', _method(ctx, ember, "charge"), 3)
    if ember.battery != 100:
        raise Fail(f"97 + 3 should be exactly 100, but the battery is {ember.battery!r}.")
    full = _build(Drone, "Spark")
    _call('Drone("Spark").charge(0)', _method(ctx, full, "charge"), 0)
    if full.battery != 100:
        raise Fail(f"Charging a full drone by 0 changed its battery to {full.battery!r}.")


@MISSION.check("Flight — `fly()` burns 2 battery per km")
def _fly(ctx):
    Drone = _drone_class(ctx)
    gale = _build(Drone, "Gale", 30)
    fly = _method(ctx, gale, "fly")
    went = _call('Drone("Gale", 30).fly(10)', fly, 10)
    if went is None:
        raise Fail("fly(10) returned None. A method that never reaches a `return` gives back None.",
                   hint="Return True when the drone flies and False when it can't.")
    if went is not True:
        raise Fail(f"Drone(\"Gale\", 30).fly(10) returned {went!r}. It has enough battery, so it should return True.")
    if gale.battery != 10:
        raise Fail(f"After flying 10 km from 30 battery, the drone has {gale.battery!r}. 10 km costs 20, so 10 should be left.",
                   hint="Subtract from self.battery: the cost is distance * 2.")
    went = _call("fly(6) with 10 battery left", fly, 6)
    if went is not False:
        raise Fail(f"With 10 battery, fly(6) (costs 12) returned {went!r}. It can't make it: return False.")
    if gale.battery != 10:
        raise Fail(f"A refused flight still changed the battery to {gale.battery!r}. If it can't fly, nothing changes.",
                   hint="Check whether the cost fits BEFORE subtracting anything.")
    went = _call("fly(5) with exactly 10 battery", fly, 5)
    if went is not True or gale.battery != 0:
        raise Fail(f"With exactly 10 battery, fly(5) costs exactly 10. Expected True and 0 left; got {went!r} "
                   f"and {gale.battery!r} left.", hint="Having exactly enough is enough: compare with <=, not <.")
    moth = _build(Drone, "Moth", 7)
    if _call('Drone("Moth", 7).fly(4)', _method(ctx, moth, "fly"), 4) is not False or moth.battery != 7:
        raise Fail(f'Drone("Moth", 7).fly(4) needs 8 battery, so it must return False and keep 7. '
                   f"Battery is now {moth.battery!r}.")


@MISSION.check("Cargo bay — corrupted `load()` repaired")
def _load(ctx):
    Drone = _drone_class(ctx)
    crane, tern = _build(Drone, "Crane", 50), _build(Drone, "Tern", 50)
    load = _method(ctx, crane, "load")
    try:
        first = load("coil")
    except TypeError as exc:
        if "positional argument" in str(exc):
            raise Fail(f"load() still crashes: {exc}.",
                       hint="You pass one argument (the item), and Python also passes the drone itself. "
                            "What must every method's first parameter be?")
        raise Fail(f"`load(\"coil\")` crashed: TypeError: {exc}", hint=_hint(exc))
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"`load(\"coil\")` crashed: {type(exc).__name__}: {exc}", hint=_hint(exc))
    second = _call('load("fuse")', load, "fuse")
    if (first, second) != (1, 2):
        raise Fail(f"Loading two items returned {first!r} then {second!r}. It should return the new count: 1, then 2.")
    if crane.cargo != ["coil", "fuse"]:
        raise Fail(f"After loading 'coil' and 'fuse', cargo is {crane.cargo!r}.")
    if tern.cargo:
        raise Fail(f"Loading one drone put {tern.cargo!r} in another drone's hold.",
                   hint="Each drone needs its own list: self.cargo = [] inside __init__.")


@MISSION.check("Identity readout — `__repr__`")
def _repr(ctx):
    Drone = _drone_class(ctx)
    kite = _build(Drone, "Kite", 80)
    try:
        text = repr(kite)
    except TypeError as exc:
        if "non-string" in str(exc):
            raise Fail("__repr__ didn't return a string.",
                       hint="__repr__ must RETURN the text. print() inside it doesn't count.")
        raise Fail(f"repr() crashed: {exc}", hint=_hint(exc))
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"repr() crashed: {type(exc).__name__}: {exc}", hint=_hint(exc))
    if text.startswith("<") and "object at" in text:
        hint = "Inside the class:  def __repr__(self):  returning an f-string."
        if type(kite).__str__ is not object.__str__:
            hint = "You wrote __str__. This layer needs __repr__ (print falls back to it, and so does every list)."
        raise Fail(f"No __repr__ yet: the drone still describes itself as {text.split(' at ')[0]} at 0x…>",
                   hint=hint)
    expected = "Drone(name='Kite', battery=80)"
    if text != expected:
        raise Fail(f"repr(Drone(\"Kite\", 80)) is {text!r}, expected {expected!r}.",
                   hint="Match it character for character: quotes around the name, no spaces around =.")
    ghost = _build(Drone, "Ghost-7", 12)
    if repr(ghost) != "Drone(name='Ghost-7', battery=12)":
        raise Fail(f"Drone(\"Ghost-7\", 12) describes itself as {repr(ghost)!r}. "
                   "The readout must use THIS drone's name and battery.",
                   hint="Build the string from self.name and self.battery.")
    _call('Drone("Ghost-7", 12).charge(5)', _method(ctx, ghost, "charge"), 5)
    if repr(ghost) != "Drone(name='Ghost-7', battery=17)":
        raise Fail("After charging, the readout didn't update. It should show the battery as it is right now.")


@MISSION.check("Squadron online — `scout` and `hauler`")
def _squadron(ctx):
    Drone = _drone_class(ctx)
    for var, name, battery in (("scout", "Kite", 80), ("hauler", "Mule", 100)):
        obj = ctx.get(var)
        if not isinstance(obj, Drone):
            raise Fail(f"`{var}` is {type(obj).__name__}, not a Drone object.",
                       hint=f'Build it from the class:  {var} = Drone("{name}", ...)')
        if getattr(obj, "name", None) != name or getattr(obj, "battery", None) != battery:
            raise Fail(f"`{var}` is {obj!r}. It should be named {name!r} with {battery} battery.")
    for call in (v for v in ctx.assignments("hauler") if isinstance(v, ast.Call)):
        if len(call.args) + len(call.keywords) > 1:
            raise Fail("You passed the hauler's battery in yourself. Let the default in __init__ do that.",
                       hint='Pass only the name:  Drone("Mule")')
    hauler = ctx.ns["hauler"]
    if hauler.cargo != ["relay chip"]:
        raise Fail(f"The hauler's cargo is {hauler.cargo!r}. It should hold exactly ['relay chip'].")
    if not _method_called(ctx.tree, "hauler", "load"):
        raise Fail("The relay chip is in the hold, but not through the load() method.",
                   hint="Use the drone's own method:  hauler.load(...)")


@MISSION.check("Broadcast — print the scout")
def _broadcast(ctx):
    if not ctx.stdout.strip():
        if ctx.crashed:
            raise Fail("Nothing was broadcast. Your script crashed before it reached the print().")
        raise Fail("Nothing was printed.", hint="print() the scout object itself.")
    if not ctx.call_uses("print", "scout"):
        raise Fail("Your print() doesn't use the `scout` object. Don't type the readout in by hand.",
                   hint="Pass the object straight to print(); it calls your __repr__.")
    scout = ctx.get("scout")
    expected = "Drone(name='Kite', battery=80)"
    if expected not in ctx.stdout:
        raise Fail(f"The scout's readout {expected!r} didn't show up in the printed output.",
                   hint=f"Your output was: {ctx.stdout.strip()[:120]!r}. Check __repr__ and that scout still "
                        f"has 80 battery (it's {getattr(scout, 'battery', '?')!r} now).")
