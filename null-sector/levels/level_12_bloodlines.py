"""LEVEL 12 // BLOODLINES — inheritance, super(), overriding, polymorphism, @dataclass."""
from __future__ import annotations

import ast
import dataclasses
from contextlib import contextmanager

from engine.mission import Fail, Mission

MISSION = Mission(
    id="L12",
    slug="level_12_bloodlines",
    title="BLOODLINES",
    concept="Inheritance & dataclasses",
    enemy="BLOODHOUND.exe",
    xp=250,
    par_seconds=35 * 60,
    tier=3,
    concepts=("inheritance", "classes"),
    enemy_art="""\
 ▄▀▀▄          ▄▀▀▄
 █  ▀▄▄▄▄▄▄▄▄▄▄▀  █
 ▀▄  ▄██▄  ▄██▄  ▄▀
  █   ▀▀    ▀▀   █
  ▀▄   ▄▄▄▄▄▄   ▄▀
    ▀▄ ▀▄▀▄▀▄ ▄▀
      ▀▀▀▀▀▀▀▀""",
    briefing="""\
The drones you rebuilt are flying again. That's the problem.

**BLOODHOUND.exe** has their scent: the Foundry's lineage tracker, built to cull any machine
whose bloodline it can't trace to a registered chassis. Your squadron is one blueprint, cloned
fifty times. To the hound, clones are counterfeits.

The Order never built just one kind of drone. It bred **bloodlines** from a single base chassis:
scouts that fly light, haulers that burn harder under load, medics that patch the rest. Each
line inherited everything and changed only what made it different.

In Python, that's **inheritance**.

**Breed the bloodlines, file their pedigrees, and get your squadron past the hound.**
""",
    why="""\
Every PyTorch model is a subclass. You inherit from `nn.Module`, call `super().__init__()`, and
override `forward()`. The run's settings usually live in a `@dataclass`:

```python
@dataclass
class Config:                  # __init__ and __repr__ written for you
    n_in: int = 4
    n_out: int = 2

class TinyNet(nn.Module):      # inherits saving, GPU moves, train/eval modes...
    def __init__(self, cfg):
        super().__init__()     # skip this line and PyTorch refuses to build the model
        self.layer = nn.Linear(cfg.n_in, cfg.n_out)

    def forward(self, x):      # override: this model's own behaviour
        return self.layer(x)
```

The parent brings the machinery, and you write only what's different. That's also why one
training loop can drive a thousand different models: it calls `model(x)`, and each model answers
in its own way. That idea is called **polymorphism**, and it's how every deep-learning
framework stacks layers into networks.
""",
    manual="""\
**Inheritance: a new class built on an old one.** Put the parent in brackets. The child gets
every attribute and method of the parent for free:

```python
class Crate:
    def __init__(self, label, weight=10):
        self.label = label
        self.weight = weight

    def describe(self):
        return f"{self.label}: {self.weight} kg"

class AmmoCrate(Crate):            # an AmmoCrate IS a Crate
    pass

AmmoCrate("rounds", 25).describe()   # 'rounds: 25 kg', inherited
```

**`super().__init__()`: extend the setup, don't replace it.** If the child writes its own
`__init__`, Python runs only the child's. Hand the shared values up to the parent first, then add
what's new:

```python
class AmmoCrate(Crate):
    def __init__(self, label, weight=10, rounds=100):
        super().__init__(label, weight)   # the parent sets label and weight
        self.rounds = rounds              # then the child adds its own
```

Forget that line and you meet: `AttributeError: 'AmmoCrate' object has no attribute 'weight'`.

**Overriding: same name, new behaviour.** Python looks for a method on the object's own class
first, then on its parent. Inside an override, `super().method()` runs the parent's version, so
you can build on it instead of copying it:

```python
class FragileCrate(Crate):
    def describe(self):
        return super().describe() + " (FRAGILE)"   # 'glass: 10 kg (FRAGILE)'
```

**Polymorphism: ask the object, don't check its type.** When a parent's method calls
`self.something()`, Python uses the child's version if the child has one:

```python
class Crate:
    def fee(self):
        return 5

    def cost(self, km):
        return km * self.fee()        # asks THIS crate for its fee

class Hazmat(Crate):
    def fee(self):
        return 20

for crate in [Crate(), Hazmat()]:
    print(crate.cost(3))              # 15, then 60
```

That loop never needs `if isinstance(crate, Hazmat)`, and a crate type invented next year works in
it unchanged. (`isinstance(x, Crate)` is True for a Hazmat too: children count as their parents.)

**`@dataclass`: classes that are mostly data.** List the fields with their types and Python writes
`__init__`, `__repr__` and `==` for you:

```python
from dataclasses import dataclass

@dataclass
class Manifest:
    item: str
    qty: int = 1                # a default; fields with defaults go last

m = Manifest("fuse")
m                               # Manifest(item='fuse', qty=1)
m == Manifest("fuse", 1)        # True: compares field by field
```
""",
    starter='''
"""
==============================================================================
  LEVEL 12 // BLOODLINES                             TARGET: BLOODHOUND.exe
==============================================================================
  One base chassis, many bloodlines. Breed them with inheritance.
  The grader breeds its OWN drones from your classes, including bloodlines
  you've never seen, so ask each drone instead of guessing its type.
"""
from dataclasses import dataclass      # you'll need this for OBJECTIVE 6


# == THE BASE CHASSIS (given: don't edit it) ==================================
class Drone:
    """Every Order drone descends from this chassis."""

    def __init__(self, name, battery=100):
        self.name = name
        self.battery = battery
        self.cargo = []

    def role(self):
        return "drone"

    def burn_rate(self):
        """Battery burned per km of flight."""
        return 2

    def fly(self, distance):
        cost = distance * self.burn_rate()      # asks THIS drone for its burn rate
        if cost > self.battery:
            return False
        self.battery -= cost
        return True

    def load(self, item):
        self.cargo.append(item)
        return len(self.cargo)

    def status(self):
        return f"{self.name} [{self.role()}] {self.battery}%"

    def __repr__(self):
        # type(self).__name__ is the name of the object's real class (Drone, Scout...)
        return f"{type(self).__name__}(name='{self.name}', battery={self.battery})"


# -- OBJECTIVE 1 -------------------------------------------------------------
# Breed the SCOUT line: write `class Scout(Drone):` with
#   __init__(self, name, battery=100, sensor_range=50)
# Hand `name` and `battery` up to the chassis with super().__init__(...),
# then store self.sensor_range.
#        example:  super().__init__(label, weight)
#                  self.rounds = rounds
#
# -- OBJECTIVE 2 -------------------------------------------------------------
# Scouts fly light. Inside Scout, override two methods:
#   role(self)       -> return "scout"
#   burn_rate(self)  -> return 1
# Don't rewrite fly(): the chassis's fly() already asks self.burn_rate().
#   Scout("Kite", 30).fly(20)  ->  True, battery is now 10



# -- OBJECTIVE 3 -------------------------------------------------------------
# Breed the HAULER line: `class Hauler(Drone):`. It needs no __init__ of its
# own (it inherits the chassis's). Override:
#   role(self)       -> return "hauler"
#   burn_rate(self)  -> the CHASSIS's burn rate plus 1 for every item in cargo.
# Build on the parent's number with super().burn_rate(); don't retype the 2.
#   empty hauler -> 2      hauler carrying 2 items -> 4
#        example:  return super().describe() + " (FRAGILE)"



# -- OBJECTIVE 4 // CORRUPTED CODE ---------------------------------------------
# The MEDIC line came out of the vat broken: a medic has no battery, no
# name, no cargo. Its __init__ replaced the chassis's instead of extending it.
# Build Medic("Sal", 60) at the bottom of the file, print it, read the crash.
# Fix __init__ so the chassis sets up name and battery first.
class Medic(Drone):
    def __init__(self, name, battery=100, kits=2):
        self.kits = kits

    def role(self):
        return "medic"

    def heal(self, other):
        """Spend one repair kit: another drone gains 30 battery (max 100)."""
        if self.kits == 0:
            return False
        self.kits -= 1
        other.battery = min(100, other.battery + 30)
        return True


# -- OBJECTIVE 5 -------------------------------------------------------------
# Write in_range(drones, distance): return a list of the NAMES of the drones
# that have enough battery to fly `distance` km (cost = distance * burn rate).
# Don't actually fly them, and don't check their types: ask each drone for its
# own burn_rate(). The grader will slip in bloodlines you've never heard of.
#   in_range([Scout("A", 30), Drone("B", 30)], 20)  ->  ["A"]



# -- OBJECTIVE 6 -------------------------------------------------------------
# BLOODHOUND wants paperwork. Write a dataclass `Pedigree` with three fields,
# in this order:   name: str    line: str    generation: int = 1
#   Pedigree("Kite", "scout")  ->  Pedigree(name='Kite', line='scout', generation=1)
#        example:  @dataclass
#                  class Manifest:
#                      item: str
#                      qty: int = 1



# -- OBJECTIVE 7 -------------------------------------------------------------
# Assemble `squad`, a list of three drones, in this order:
#   a Scout named "Kite" with 80 battery
#   a Hauler named "Mule" with the default battery
#   a Medic named "Sal" with 60 battery
# Then build `registry`: one Pedigree per drone in squad, made from the drone's
# own name and role() (generation stays 1). Read them off the drones; don't
# type the names again.



# -- OBJECTIVE 8 -------------------------------------------------------------
# Roll call: loop over the squad and print each drone's status().
#   Kite [scout] 80%

''',
    dialogue={
        "intro": [
            {"speaker": "nova", "mood": "alarm",
             "text": "Ops alert, {callsign}: BLOODHOUND.exe is sweeping the Foundry floor. No pedigree, no mercy."},
            {"speaker": "rust", "mood": "neutral",
             "text": "Your drones all smell the same to it. One blueprint, fifty copies. Counterfeits."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "Then we breed bloodlines. One chassis, many descendants. Each changes only what makes it different."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Crash on the breeding line. 'has no attribute' often means a child skipped super().__init__()."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "That one came out of the vat inside-out. Read the log before you breed another."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The traceback names the class and the piece it's missing. Start there."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader breeds lines you've never seen. If your code checks types, it misses them. Ask the drone."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "Hound's still on the scent. One layer at a time, {callsign}. You've got this."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Override only what's different. Everything else, the parent already does."}],
            [{"speaker": "vex", "mood": "smirk",
              "text": "Still breeding drones? My bloodline's called winning, {callsign}. Look it up."}],
        ],
        "victory": [
            {"speaker": "cipher", "mood": "warm",
             "text": "BLOODHOUND traced every line back to the base chassis and lost interest. Clean pedigrees."},
            {"speaker": "nova", "mood": "smirk",
             "text": "Scout, hauler, medic, all on the registry. Squadron's on the board, {callsign}."},
            {"speaker": "rust", "mood": "neutral",
             "text": "Your scout caught a beacon past the slag fields. A transport went down hard. Black box still pinging."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

_MISSING = object()


def _top_level(ctx, kinds, name: str):
    """The last top-level definition called `name` (the one Python actually kept)."""
    found = [n for n in ctx.tree.body if isinstance(n, kinds) and n.name == name]
    return found[-1] if found else None


def _hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, AttributeError) and "has no attribute" in msg:
        return ("If this class writes its own __init__, its first line should hand the shared values "
                "to the parent:  super().__init__(name, battery)")
    if isinstance(exc, TypeError) and "positional argument" in msg:
        return "Check the def line: every method starts with self, then the parameters in the order asked."
    if isinstance(exc, TypeError) and "missing" in msg and "required" in msg:
        return "A parameter has no value. Defaults go in the def line, like  sensor_range=50"
    if isinstance(exc, RecursionError):
        return "A method calls itself forever. To reach the parent's version, use super().method()."
    return "Build one at the bottom of your file and call the same thing to see the full error."


def _cls(ctx, name: str, hint: str) -> type:
    if name not in ctx.ns:
        if ctx.crashed and _top_level(ctx, ast.ClassDef, name):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python built it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No class named `{name}` found.", hint=hint)
    value = ctx.ns[name]
    if not isinstance(value, type):
        raise Fail(f"`{name}` exists but isn't a class.", hint=hint)
    return value


def _chassis(ctx) -> type:
    return _cls(ctx, "Drone", "The base chassis `class Drone:` is given in the starter. Restore it.")


def _child(ctx, name: str) -> tuple[type, type]:
    Drone = _chassis(ctx)
    cls = _cls(ctx, name, f"Start the bloodline with  class {name}(Drone):")
    if not issubclass(cls, Drone):
        raise Fail(f"`{name}` isn't descended from Drone, so it has none of the chassis's methods.",
                   hint=f"Name the parent in brackets:  class {name}(Drone):")
    return Drone, cls


def _call(label: str, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Fail:
        raise
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}", hint=_hint(exc))


def _attr(obj, attr: str, label: str):
    if not hasattr(obj, attr):
        raise Fail(f"{label} has no `{attr}` attribute.",
                   hint="If the class has its own __init__, it must call super().__init__(name, battery) "
                        "so the chassis can set name, battery and cargo.")
    return getattr(obj, attr)


@contextmanager
def _patched(cls: type, attr: str, value):
    """Temporarily swap one attribute on a class (the grader re-tunes the chassis to test super())."""
    original = cls.__dict__.get(attr, _MISSING)
    setattr(cls, attr, value)
    try:
        yield
    finally:
        if original is _MISSING:
            delattr(cls, attr)
        else:
            setattr(cls, attr, original)


@contextmanager
def _traced_chassis(Drone: type):
    """Marks every object whose construction actually ran Drone.__init__."""
    original = Drone.__init__

    def traced(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.__dict__["_ns_chassis_ran"] = True

    with _patched(Drone, "__init__", traced):
        yield


def _built_through_chassis(ctx, Drone: type, cls: type, label: str, *args):
    with _traced_chassis(Drone):
        obj = _call(label, cls, *args)
    ran = obj.__dict__.pop("_ns_chassis_ran", False) if hasattr(obj, "__dict__") else False
    return obj, ran


def _check_chassis_attrs(obj, label: str, name: str, battery) -> None:
    got_name = _attr(obj, "name", label)
    got_battery = _attr(obj, "battery", label)
    cargo = _attr(obj, "cargo", label)
    if got_name != name:
        raise Fail(f"{label}.name is {got_name!r}, expected {name!r}.",
                   hint="Pass the name you were given up to the parent: super().__init__(name, battery)")
    if got_battery != battery:
        raise Fail(f"{label}.battery is {got_battery!r}, expected {battery!r}.",
                   hint="Pass the battery you were given, not a fixed number: super().__init__(name, battery)")
    if cargo != []:
        raise Fail(f"{label} starts with cargo {cargo!r}. A new drone's hold is empty.")


def _make_line(Drone: type, cls_name: str, rate, role: str) -> type:
    """A bloodline the player has never seen, bred by the grader from their chassis."""
    return type(cls_name, (Drone,), {"burn_rate": lambda self: rate, "role": lambda self: role})


def _literal_first_arg_calls(tree: ast.AST, func: str) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == func
               and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
               for n in ast.walk(tree))


def _method_called(tree: ast.AST, method: str) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == method
               for n in ast.walk(tree))


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Scout line — `Scout(Drone)` extends `__init__` with super()")
def _scout_init(ctx):
    Drone, Scout = _child(ctx, "Scout")
    rook, ran = _built_through_chassis(ctx, Drone, Scout, 'Scout("Rook", 45, 70)', "Rook", 45, 70)
    if not ran:
        raise Fail("Scout's __init__ never ran the chassis's __init__.",
                   hint="Its first line should hand the shared values up:  super().__init__(name, battery). "
                        "Copying the chassis's lines by hand doesn't count: the hound checks the bloodline.")
    _check_chassis_attrs(rook, 'Scout("Rook", 45, 70)', "Rook", 45)
    sensor = _attr(rook, "sensor_range", 'Scout("Rook", 45, 70)')
    if sensor != 70:
        raise Fail(f'Scout("Rook", 45, 70).sensor_range is {sensor!r}, expected 70.',
                   hint="After super().__init__(...), store the new value:  self.sensor_range = sensor_range")
    lark = _call('Scout("Lark")', Scout, "Lark")
    if getattr(lark, "battery", None) != 100 or getattr(lark, "sensor_range", None) != 50:
        raise Fail(f'Scout("Lark") has battery {getattr(lark, "battery", None)!r} and sensor_range '
                   f'{getattr(lark, "sensor_range", None)!r}. The defaults should be 100 and 50.',
                   hint="def __init__(self, name, battery=100, sensor_range=50):")
    if _attr(lark, "cargo", 'Scout("Lark")') is rook.cargo:
        raise Fail("Two scouts share one cargo list.", hint="Let the chassis create each drone's list.")


@MISSION.check("Scout tuning — overrides `role()` and `burn_rate()`")
def _scout_tuning(ctx):
    Drone, Scout = _child(ctx, "Scout")
    base = _call('Drone("Base")', Drone, "Base")
    if _call("Drone.role()", base.role) != "drone" or _call("Drone.burn_rate()", base.burn_rate) != 2:
        raise Fail("The base chassis changed: a plain Drone should still have role 'drone' and burn 2 per km.",
                   hint="Leave `class Drone` as the starter gave it. Change behaviour in the children instead.")
    kite = _call('Scout("Kite", 30)', Scout, "Kite", 30)
    role = _call('Scout("Kite", 30).role()', kite.role)
    if role != "scout":
        raise Fail(f"A scout's role() returned {role!r}, expected 'scout'.",
                   hint="Inside class Scout:  def role(self):  returning the text \"scout\".")
    rate = _call('Scout("Kite", 30).burn_rate()', kite.burn_rate)
    if rate != 1:
        raise Fail(f"A scout's burn_rate() returned {rate!r}, expected 1. Scouts fly light.",
                   hint="Override it inside class Scout:  def burn_rate(self):  return 1")
    flew = _call('Scout("Kite", 30).fly(20)', kite.fly, 20)
    if flew is not True or kite.battery != 10:
        raise Fail(f'Scout("Kite", 30).fly(20) returned {flew!r} and left {kite.battery!r} battery. '
                   "At 1 per km, 20 km costs 20: expected True and 10 left.",
                   hint="You don't need to rewrite fly(): the chassis's fly() calls self.burn_rate().")
    if _call('Drone("Base", 30).fly(20)', Drone("Base", 30).fly, 20) is not False:
        raise Fail("A plain Drone with 30 battery flew 20 km. The chassis should still burn 2 per km.")


@MISSION.check("Hauler line — `burn_rate()` builds on super()")
def _hauler(ctx):
    Drone, Hauler = _child(ctx, "Hauler")
    ox = _call('Hauler("Ox")', Hauler, "Ox")
    _check_chassis_attrs(ox, 'Hauler("Ox")', "Ox", 100)
    role = _call('Hauler("Ox").role()', ox.role)
    if role != "hauler":
        raise Fail(f"A hauler's role() returned {role!r}, expected 'hauler'.")
    empty = _call("burn_rate() with an empty hold", ox.burn_rate)
    if empty != 2:
        raise Fail(f"An empty hauler burns {empty!r} per km, expected 2 (the chassis's rate, plus 0 items).")
    _call('load("ore")', ox.load, "ore")
    _call('load("ore")', ox.load, "ore")
    loaded = _call("burn_rate() carrying 2 items", ox.burn_rate)
    if loaded != 4:
        raise Fail(f"A hauler carrying 2 items burns {loaded!r} per km, expected 4 (2, plus 1 per item).",
                   hint="len(self.cargo) counts the items in the hold.")
    flew = _call("fly(10) carrying 2 items", ox.fly, 10)
    if flew is not True or ox.battery != 60:
        raise Fail(f"A loaded hauler (4 per km) flying 10 km returned {flew!r} with {ox.battery!r} battery left. "
                   "Expected True and 60.")
    yak = _call('Hauler("Yak")', Hauler, "Yak")
    _call('load("coil")', yak.load, "coil")
    with _patched(Drone, "burn_rate", lambda self: 3):
        retuned = _call("burn_rate() after the chassis was re-tuned", yak.burn_rate)
    if retuned != 4:
        raise Fail(f"The grader re-tuned the chassis to burn 3 per km. A hauler with 1 item should then burn 4, "
                   f"but yours burned {retuned!r}. It retyped the parent's number instead of asking for it.",
                   hint="Build on the parent's rate: super().burn_rate() plus the number of items in the hold.")


@MISSION.check("Medic line — corrupted `__init__` repaired")
def _medic(ctx):
    Drone, Medic = _child(ctx, "Medic")
    sal, ran = _built_through_chassis(ctx, Drone, Medic, 'Medic("Sal", 60, 3)', "Sal", 60, 3)
    if not ran:
        missing = [a for a in ("name", "battery", "cargo") if not hasattr(sal, a)]
        what = f"has no {', '.join(missing)}" if missing else "never ran the chassis's __init__"
        raise Fail(f'Medic("Sal", 60, 3) {what}. Its __init__ replaced the chassis\'s instead of extending it.',
                   hint="Make the first line of Medic.__init__ hand name and battery up to the parent with "
                        "super().__init__(...), then keep  self.kits = kits.")
    _check_chassis_attrs(sal, 'Medic("Sal", 60, 3)', "Sal", 60)
    if getattr(sal, "kits", None) != 3:
        raise Fail(f'Medic("Sal", 60, 3).kits is {getattr(sal, "kits", None)!r}, expected 3. Keep self.kits = kits.')
    doc = _call('Medic("Doc")', Medic, "Doc")
    if getattr(doc, "battery", None) != 100 or getattr(doc, "kits", None) != 2:
        raise Fail(f'Medic("Doc") has battery {getattr(doc, "battery", None)!r} and kits '
                   f'{getattr(doc, "kits", None)!r}. The defaults are 100 and 2.')
    status = _call('Medic("Sal", 60, 3).status()', sal.status)
    if status != "Sal [medic] 60%":
        raise Fail(f"The medic's status() reads {status!r}, expected 'Sal [medic] 60%'.")
    patient = Drone("Hurt", 50)
    healed = _call("heal() on a drone with 50 battery", sal.heal, patient)
    if healed is not True or patient.battery != 80 or sal.kits != 2:
        raise Fail(f"After heal(), the patient has {patient.battery!r} battery and the medic {sal.kits!r} kits. "
                   "Expected 80 and 2. (heal() was given in the starter; restore it if you changed it.)")


@MISSION.check("Polymorphism — `in_range()` asks every drone")
def _in_range(ctx):
    Drone = _chassis(ctx)
    fn = ctx.ns.get("in_range")
    if not callable(fn):
        if ctx.crashed and _top_level(ctx, ast.FunctionDef, "in_range"):
            raise Fail("`in_range` is in your file, but the script crashed before Python reached it.")
        raise Fail("No function named `in_range` found.", hint="def in_range(drones, distance):")
    Glider = _make_line(Drone, "Glider", 0.5, "glider")
    Bruiser = _make_line(Drone, "Bruiser", 3, "bruiser")
    cases = [
        (lambda: [Drone("Bastion", 30), Glider("Wisp", 10), Bruiser("Anvil", 44), Drone("Dregs", 29)], 15,
         ["Bastion", "Wisp"]),
        (lambda: [Bruiser("Anvil", 90), Glider("Moth", 4), Drone("Pike", 100)], 30, ["Anvil", "Pike"]),
        (lambda: [Glider("Ash", 5), Drone("Cole", 0)], 0, ["Ash", "Cole"]),
        (lambda: [], 12, []),
    ]
    for build, distance, expected in cases:
        fleet = build()
        before = [d.battery for d in fleet]
        shown = "[" + ", ".join(f'{type(d).__name__}("{d.name}", {d.battery})' for d in fleet) + "]"
        got = _call(f"in_range({shown}, {distance})", fn, fleet, distance)
        if [d.battery for d in fleet] != before:
            raise Fail("in_range() actually flew the drones: their batteries changed.",
                       hint="Only compare: distance * d.burn_rate() against d.battery. Don't call fly().")
        if not isinstance(got, list):
            raise Fail(f"in_range() returned {type(got).__name__}, expected a list of names.")
        if got != expected:
            exotic = any(type(d).__name__ in ("Glider", "Bruiser") for d in fleet)
            hint = ("The grader slipped in bloodlines you've never seen (a Glider burns 0.5 per km, a Bruiser 3). "
                    "Don't check types or assume 2: ask each drone, d.burn_rate()." if exotic else
                    "Having exactly enough battery is enough: compare with <=.")
            raise Fail(f"in_range({shown}, {distance}) returned {got!r}, expected {expected!r}.", hint=hint)


@MISSION.check("Paperwork — `Pedigree` is a @dataclass")
def _pedigree(ctx):
    Pedigree = _cls(ctx, "Pedigree", "Write  @dataclass  on the line above  class Pedigree:")
    if not dataclasses.is_dataclass(Pedigree):
        raise Fail("`Pedigree` is a plain class, not a dataclass.",
                   hint="Put @dataclass on the line right above class Pedigree:, and list the fields with types.")
    names = [f.name for f in dataclasses.fields(Pedigree)]
    if names != ["name", "line", "generation"]:
        raise Fail(f"Pedigree's fields are {names}, expected ['name', 'line', 'generation'] in that order.",
                   hint="One field per line inside the class, like  name: str")
    kite = _call('Pedigree("Kite", "scout")', Pedigree, "Kite", "scout")
    if kite.generation != 1:
        raise Fail(f'Pedigree("Kite", "scout").generation is {kite.generation!r}. It should default to 1.',
                   hint="generation: int = 1")
    text = repr(kite)
    if text != "Pedigree(name='Kite', line='scout', generation=1)":
        raise Fail(f"A pedigree reads {text!r}, expected \"Pedigree(name='Kite', line='scout', generation=1)\".",
                   hint="Let the dataclass write __repr__ for you: remove any __repr__ you wrote by hand.")
    rook = _call('Pedigree("Rook", "hauler", 3)', Pedigree, "Rook", "hauler", 3)
    if rook != Pedigree("Rook", "hauler", 3) or rook == Pedigree("Rook", "hauler", 4):
        raise Fail("Two pedigrees with the same fields should be equal (==), and different ones shouldn't.",
                   hint="A dataclass writes == for you. Remove any __eq__ you wrote by hand.")


@MISSION.check("Squadron — `squad` and its `registry`")
def _squad(ctx):
    classes = {name: _cls(ctx, name, f"class {name}(Drone):") for name in ("Scout", "Hauler", "Medic")}
    squad = ctx.get("squad")
    if not isinstance(squad, list) or len(squad) != 3:
        raise Fail(f"`squad` should be a list of 3 drones, but it's {squad!r}.")
    for i, (cls_name, name, battery) in enumerate((("Scout", "Kite", 80), ("Hauler", "Mule", 100),
                                                   ("Medic", "Sal", 60))):
        drone = squad[i]
        if type(drone) is not classes[cls_name]:
            raise Fail(f"squad[{i}] is a {type(drone).__name__}, expected a {cls_name}.",
                       hint=f'Build it from the bloodline:  {cls_name}("{name}", ...)')
        if getattr(drone, "name", None) != name or getattr(drone, "battery", None) != battery:
            raise Fail(f"squad[{i}] is {drone!r}, expected a {cls_name} named {name!r} with {battery} battery.")
    Pedigree = _cls(ctx, "Pedigree", "class Pedigree:")
    registry = ctx.get("registry")
    expected = [Pedigree(d.name, d.role()) for d in squad]
    if not isinstance(registry, list) or registry != expected:
        raise Fail(f"`registry` is {registry!r}, expected one Pedigree per drone: {expected!r}.",
                   hint="Loop over squad and build Pedigree(drone.name, drone.role()) for each one.")
    if _literal_first_arg_calls(ctx.tree, "Pedigree") and not ctx.derived_from("registry", "squad"):
        raise Fail("You typed the names into the pedigrees by hand. BLOODHOUND checks the papers against the drones.",
                   hint="Build each one from a drone in squad: drone.name and drone.role().")


@MISSION.check("Roll call — print every drone's `status()`")
def _roll_call(ctx):
    if not ctx.stdout.strip():
        if ctx.crashed:
            raise Fail("Nothing was printed. Your script crashed before the roll call.")
        raise Fail("Nothing was printed.", hint="for drone in squad:  print(drone.status())")
    if not _method_called(ctx.tree, "status"):
        raise Fail("Your roll call doesn't call status(). Let each drone report itself.",
                   hint="for drone in squad:  print(drone.status())")
    lines = [line.strip() for line in ctx.stdout.splitlines()]
    for wanted in ("Kite [scout] 80%", "Mule [hauler] 100%", "Sal [medic] 60%"):
        if wanted not in lines:
            raise Fail(f"The roll call is missing the line {wanted!r}.",
                       hint=f"Your output was: {ctx.stdout.strip()[:140]!r}")
