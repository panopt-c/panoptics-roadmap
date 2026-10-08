"""Tier-3 drills: classes and objects (the Foundry).

* t3-mag-lock        MAG LOCK        a class with state, methods that call methods, __repr__
* t3-squad-roster    SQUAD ROSTER    a container class: __len__, __contains__, ranking with sort keys
* t3-cred-wallet     CRED WALLET     validation inside methods, a custom exception, all-or-nothing transfers
* t3-packet-frames   PACKET FRAMES   @dataclass, default_factory, pure functions over objects
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from engine.drills import Drill, register
from engine.drills.library.tier3_common import (
    CALLSIGNS, Replay, build, call_text, exception_class, invoke, klass, line, method, sample, show,
)
from engine.mission import Fail


# ══════════════════════════════════════════════════════════════════════════════════════
#  t3-mag-lock — MAG LOCK
# ══════════════════════════════════════════════════════════════════════════════════════

class _Magazine:
    def __init__(self, capacity):
        self.capacity = capacity
        self.rounds = 0

    def load(self, n):
        loaded = min(n, self.capacity - self.rounds)
        self.rounds += loaded
        return loaded

    def fire(self):
        if self.rounds > 0:
            self.rounds -= 1
            return True
        return False

    def fire_burst(self, k):
        fired = 0
        for _ in range(k):
            if not self.fire():
                break
            fired += 1
        return fired

    def is_empty(self):
        return self.rounds == 0

    def __repr__(self):
        return f"Magazine({self.rounds}/{self.capacity})"


_MAG_MANUAL = """\
**A class bundles data with the code that changes it.** `__init__` runs when you build an
object; `self.name = value` gives that object its own attribute:

```python
class Battery:
    def __init__(self, size):
        self.size = size       # remembered by THIS battery
        self.charge = 0        # every new battery starts empty
```

**Methods read and change `self`.** They can return a value too, and that return value is part
of the contract, separate from the state change:

```python
    def charge_up(self, amount):
        added = min(amount, self.size - self.charge)   # never past full
        self.charge += added
        return added                                   # how much actually went in
```

**Methods can call other methods** through `self`, so a rule lives in one place:

```python
    def drain(self, times):
        used = 0
        for _ in range(times):
            if not self.use_one():     # reuse the single-step rule
                break
            used += 1
        return used
```

**`__repr__` is what you see when you print the object** (or look at it in a shell). It must
return a string: `return f"Battery({self.charge}/{self.size})"`.
"""


def _build_mag(rng):
    cap = rng.randint(8, 30)
    other_cap = rng.randint(5, 30)
    first = rng.randint(2, cap - 3)
    loads = [first, rng.randint(cap, cap + 15), rng.randint(1, 4), 0]
    fire_plan = rng.randint(2, 5)
    burst = rng.randint(3, 6)
    cap2 = rng.randint(4, 9)
    example_cap = rng.choice([c for c in range(10, 25) if c != cap])
    ex_load = rng.randint(3, example_cap - 2)

    prompt = f"""\
RUST slides a smart magazine across the counter of his undercroft stall. "Firmware got wiped
in the Null Event. It still counts rounds, it just doesn't know it's supposed to. Write me a
new one and you keep the gun."

**Write a class `Magazine`:**

- `Magazine(capacity)` stores `capacity` and starts with `rounds = 0` (both attributes).
- `load(n)` adds up to `n` rounds but never past `capacity`. It **returns how many rounds
  actually went in** (not the new total).
- `fire()` uses one round and returns `True`; if the magazine is empty it returns `False` and
  nothing changes.
- `fire_burst(k)` fires up to `k` rounds by calling `self.fire()`, and returns how many fired.
- `is_empty()` returns `True` when there are no rounds left.
- `repr(m)` looks like `Magazine(7/12)`: rounds, a slash, capacity.

Every magazine keeps its own count.

**Bench test from RUST (this contract):**

```python
m = Magazine({example_cap})
m.load({ex_load})        # {ex_load}
m.load(100)      # {example_cap - ex_load}: only that many fit
m.fire()         # True
m                # Magazine({example_cap - 1}/{example_cap})
```
"""
    starter = '''
class Magazine:
    """A smart magazine: counts its rounds and never overfills."""

    def __init__(self, capacity):
        # store capacity; start with 0 rounds
        pass

    def load(self, n):
        """Add up to n rounds without passing capacity. Return how many went in."""
        pass

    def fire(self):
        """Use one round. True if a round was fired, False if the magazine was empty."""
        pass

    def fire_burst(self, k):
        """Fire up to k rounds by calling self.fire(). Return how many fired."""
        pass

    def is_empty(self):
        pass

    def __repr__(self):
        """Magazine(rounds/capacity), e.g. Magazine(7/12)"""
        pass


if __name__ == "__main__":
    m = Magazine(12)
    print(m.load(5), m.load(20), m.fire(), m)      # 5 7 True Magazine(11/12)
'''
    mission = build(
        title="MAG LOCK", tier=3, enemy="FIRMWARE.void", prompt=prompt, manual=_MAG_MANUAL, starter=starter,
        concepts=("classes",), brief=("Write the Magazine class below.",),
        intro=[line("rust", "Smart mag, wiped clean. Teach it to count again and it's yours. Overfill it and it's scrap.", "neutral"),
               line("cipher", "State lives on self. Each method changes it a little, and says what it did.", "neutral")],
        victory=[line("rust", "Counts true, stops at full, clicks when empty. Fine. Take the gun before I change my mind.", "smirk")],
    )

    def loaded_spot(before, n, cap):
        def spot(got, expected):
            if got == min(before + n, cap) and got != expected:
                return ("That's the new total. load() returns how many rounds went IN on this call.",
                        "Work out the room left (capacity - rounds), load min(n, room), return that amount.")
            return None
        return spot

    @mission.check("Magazine(capacity) — a fresh, empty mag")
    def _fresh(ctx):
        a = Replay(ctx, "Magazine", _Magazine, (cap,), var="a",
                   hint="In __init__:  self.capacity = capacity  and  self.rounds = 0")
        a.attr("capacity")
        a.attr("rounds")
        b = Replay(ctx, "Magazine", _Magazine, (other_cap,), var="b",
                   hint="Set self.rounds inside __init__ so every magazine gets its own count.")
        a.call("load", 3, record=True)
        b.steps.append(f"a.load(3)")
        b.attr("rounds")

    @mission.check("load(n) — fill to capacity, never past it")
    def _load(ctx):
        m = Replay(ctx, "Magazine", _Magazine, (cap,), var="m",
                   hint="room = self.capacity - self.rounds; loaded = min(n, room)")
        for n in loads:
            m.call("load", n, spot=loaded_spot(m.ref.rounds, n, cap))
            m.attr("rounds")
        m.attr("capacity")

    @mission.check("fire() and fire_burst(k) — trigger discipline")
    def _fire(ctx):
        m = Replay(ctx, "Magazine", _Magazine, (cap2,), var="m",
                   hint="fire(): if there's a round, take one and return True; otherwise return False.")
        m.call("load", fire_plan)
        for _ in range(fire_plan + 2):
            m.call("fire")
            m.attr("rounds")
        m.call("load", cap2)
        m.call("fire_burst", burst)
        m.attr("rounds")
        m.call("fire_burst", cap2 + 5)
        m.attr("rounds")
        m.call("fire_burst", 2)

    @mission.check("is_empty() and repr — the status readout")
    def _status(ctx):
        m = Replay(ctx, "Magazine", _Magazine, (cap,), var="m")
        m.call("is_empty")
        m.value("repr(m)", repr, repr, hint='return f"Magazine({self.rounds}/{self.capacity})"')
        m.call("load", first)
        m.call("is_empty")
        m.value("repr(m)", repr, repr, hint='return f"Magazine({self.rounds}/{self.capacity})"')
        m.call("fire_burst", first)
        m.call("is_empty")
        m.value("repr(m)", repr, repr)

    return mission


register(Drill("t3-mag-lock", "MAG LOCK", 3, ("classes",), 600, _build_mag))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t3-squad-roster — SQUAD ROSTER
# ══════════════════════════════════════════════════════════════════════════════════════

class _Squad:
    def __init__(self, name):
        self.name = name
        self.drones = {}

    def enlist(self, callsign, power):
        self.drones[callsign] = power

    def discharge(self, callsign):
        if callsign in self.drones:
            del self.drones[callsign]
            return True
        return False

    def total_power(self):
        return sum(self.drones.values())

    def ranked(self):
        return sorted(self.drones, key=lambda c: (-self.drones[c], c))

    def strongest(self):
        order = self.ranked()
        return order[0] if order else None

    def __len__(self):
        return len(self.drones)

    def __contains__(self, callsign):
        return callsign in self.drones

    def __repr__(self):
        return f"Squad({self.name}, size={len(self.drones)})"


_SQUAD_MANUAL = """\
**An object can hold a collection.** Keep it in an attribute, usually a dict when every item has
a unique key:

```python
class Crew:
    def __init__(self, ship):
        self.ship = ship
        self.members = {}              # name -> skill

    def hire(self, name, skill):
        self.members[name] = skill     # same name again just updates the skill
```

**Special methods plug your class into Python's built-ins.** Python calls them for you:

```python
    def __len__(self):                 # len(crew)
        return len(self.members)

    def __contains__(self, name):      # "Kade" in crew
        return name in self.members
```

**Sort with a key that breaks ties.** A key can return a tuple: Python compares the first item,
then the second if the first ties. Negate a number to sort it biggest-first:

```python
sorted(skills, key=lambda name: (-skills[name], name))   # best first, then A→Z
```

`min()` and `max()` take the same `key=`, and `del d[key]` removes an entry.
"""


def _build_squad(rng):
    name = rng.choice(("ember", "static", "ashfall", "nightshift", "rivet", "halcyon"))
    names = sample(rng, CALLSIGNS, 8)
    roster = [(c, rng.randint(10, 99)) for c in names[:6]]
    tie_power = rng.randint(40, 90)
    roster[1] = (roster[1][0], tie_power)
    roster[4] = (roster[4][0], tie_power)
    roster.append((roster[2][0], rng.randint(10, 99)))      # re-enlist: an update, not a second entry
    absent = names[6]
    gone = roster[3][0]
    late = names[7]
    late_power = max(p for _, p in roster) + rng.randint(0, 5)

    ex = sample(rng, CALLSIGNS, 3)
    prompt = f"""\
The Foundry's drone bays are filling up again, and NOVA wants squads she can actually dispatch.
Right now the roster is a sticky note on a furnace. Give her a class.

**Write a class `Squad`:**

- `Squad(name)` stores `name` and starts with no drones.
- `enlist(callsign, power)` adds a drone. Enlisting a callsign that's already there **updates**
  its power (it's still one drone).
- `discharge(callsign)` removes it and returns `True`, or returns `False` if it wasn't there.
- `total_power()` is the sum of every drone's power (`0` for an empty squad).
- `ranked()` is a list of callsigns, highest power first; equal power goes **alphabetically**.
- `strongest()` is the first callsign in that order, or `None` for an empty squad.
- `len(squad)` is the number of drones, and `"KADE" in squad` works.
- `repr(squad)` looks like `Squad(ember, size=3)`.

**Dispatch board (this contract):**

```python
s = Squad("{name}")
s.enlist("{ex[0]}", 40); s.enlist("{ex[1]}", 75); s.enlist("{ex[2]}", 75)
s.ranked()      # {sorted(ex[1:], key=lambda c: c) + [ex[0]]}
s.strongest()   # {sorted(ex[1:])[0]!r}
len(s), "{ex[0]}" in s   # (3, True)
```
"""
    starter = '''
class Squad:
    """A named squad of drones, each with a power rating."""

    def __init__(self, name):
        pass

    def enlist(self, callsign, power):
        pass

    def discharge(self, callsign):
        """Remove a drone. True if it was there, False if not."""
        pass

    def total_power(self):
        pass

    def ranked(self):
        """Callsigns, highest power first; ties alphabetical."""
        pass

    def strongest(self):
        """The top callsign, or None if the squad is empty."""
        pass

    # len(squad), "NYX" in squad, repr(squad):  add __len__, __contains__ and __repr__


if __name__ == "__main__":
    s = Squad("ember")
    s.enlist("NYX", 40)
    s.enlist("KADE", 75)
    s.enlist("ASH", 75)
    print(s.ranked(), s.strongest(), len(s), "NYX" in s, s)
    # ['ASH', 'KADE', 'NYX'] ASH 3 True Squad(ember, size=3)
'''
    mission = build(
        title="SQUAD ROSTER", tier=3, enemy="BAY-CONTROL.bak", prompt=prompt, manual=_SQUAD_MANUAL,
        starter=starter, concepts=("classes", "sorting"), brief=("Write the Squad class below.",),
        intro=[line("nova", "Drone bays are live and my roster is a sticky note on a furnace. Build me a Squad class, {callsign}!", "warm"),
               line("cipher", "A dict inside an object, and a few special methods so len() and `in` just work.", "neutral")],
        victory=[line("nova", "Roster's up, ranked and counted. First squad dispatches at dawn. Contract closed!", "warm")],
    )

    def enlist_all(s):
        for callsign, power in roster:
            s.call("enlist", callsign, power, hint="Store the power under the callsign: one entry per drone.")

    @mission.check("enlist, len() and `in` — the roster")
    def _roster(ctx):
        s = Replay(ctx, "Squad", _Squad, (name,), var="s", hint="Keep the drones in a dict: callsign -> power.")
        s.attr("name")
        s.value("len(s)", len, len, hint="Add  def __len__(self): return len(self.drones)  (or whatever you named it).")
        enlist_all(s)
        s.value("len(s)", len, len,
                hint="Enlisting an existing callsign updates it; it's still one drone. A dict does that for free.")
        for callsign in (roster[0][0], absent, roster[-1][0]):
            s.value(f"{callsign!r} in s", lambda o, c=callsign: c in o, lambda r, c=callsign: c in r,
                    hint="Add  def __contains__(self, callsign):  returning True or False.")

    @mission.check("total_power() and discharge()")
    def _discharge(ctx):
        s = Replay(ctx, "Squad", _Squad, (name,), var="s")
        s.call("total_power", hint="An empty squad has 0 power: sum() of nothing is 0.")
        enlist_all(s)
        s.call("total_power", hint="Add up the powers: sum(self.drones.values())")
        s.call("discharge", gone, hint="Remove it with  del self.drones[callsign]  and return True.")
        s.call("discharge", gone, hint="It's already gone: return False instead of crashing.")
        s.call("discharge", absent)
        s.call("total_power")
        s.value("len(s)", len, len)

    @mission.check("ranked() and strongest() — the pecking order")
    def _ranked(ctx):
        s = Replay(ctx, "Squad", _Squad, (name,), var="s")
        s.call("strongest", hint="With no drones there's no strongest: return None.")
        s.call("ranked")
        enlist_all(s)
        hint = "sorted(self.drones, key=lambda c: (-self.drones[c], c)) puts high power first and breaks ties A→Z."
        s.call("ranked", hint=hint)
        s.call("strongest", hint=hint)
        s.call("enlist", late, late_power)
        s.call("ranked", hint=hint)
        s.call("strongest", hint=hint)

    @mission.check("repr — the dispatch tag")
    def _repr(ctx):
        s = Replay(ctx, "Squad", _Squad, (name,), var="s")
        hint = 'return f"Squad({self.name}, size={len(self.drones)})"'
        s.value("repr(s)", repr, repr, hint=hint)
        enlist_all(s)
        s.value("repr(s)", repr, repr, hint=hint)

    return mission


register(Drill("t3-squad-roster", "SQUAD ROSTER", 3, ("classes", "sorting"), 900, _build_squad))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t3-cred-wallet — CRED WALLET
# ══════════════════════════════════════════════════════════════════════════════════════

class InsufficientFunds(Exception):
    """Reference copy: the player's class with the same name is what the checks expect."""


class _Wallet:
    def __init__(self, owner, balance=0):
        self.owner = owner
        self.balance = balance
        self.history = []

    @staticmethod
    def _valid(amount):
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError(f"bad amount: {amount!r}")

    def deposit(self, amount):
        self._valid(amount)
        self.balance += amount
        self.history.append(("deposit", amount))
        return self.balance

    def withdraw(self, amount):
        self._valid(amount)
        if amount > self.balance:
            raise InsufficientFunds(f"need {amount}, have {self.balance}")
        self.balance -= amount
        self.history.append(("withdraw", amount))
        return self.balance

    def transfer(self, other, amount):
        self.withdraw(amount)
        other.deposit(amount)
        return self.balance


_WALLET_MANUAL = """\
**Methods guard their own data.** Check the input first and `raise` before changing anything,
so a bad call leaves the object exactly as it was:

```python
def charge(self, amount):
    if not isinstance(amount, int) or amount <= 0:
        raise ValueError(f"bad amount: {amount!r}")
    self.level += amount            # only reached when the amount is valid
```

Check the **type** before comparing: `"100" <= 0` crashes with a `TypeError` before your
`ValueError` gets a chance.

**A custom exception is one line.** It names the problem, so callers can catch exactly it:

```python
class Overheated(Exception):
    pass

raise Overheated("core at 940 degrees")
```

**Reuse your own methods to stay all-or-nothing.** If step one raises, step two never runs:

```python
def move(self, other, amount):
    self.take(amount)     # raises? then nothing below runs, nothing changed
    other.give(amount)
```

A tuple like `("deposit", 50)` makes a tidy history entry.
"""


def _build_wallet(rng):
    owner = rng.choice(CALLSIGNS)
    start = rng.randint(50, 400)
    deposits = [rng.randint(5, 200) for _ in range(2)]
    withdraw_ok = rng.randint(10, start)
    bad_amounts = [0, -rng.randint(1, 50), round(rng.uniform(1, 9), 1) + 0.5, str(rng.randint(10, 99))]
    other_owner = rng.choice([c for c in CALLSIGNS if c != owner])
    other_start = rng.randint(0, 120)
    t_ok = rng.randint(5, 40)

    prompt = f"""\
Every runner in the Monastery gets paid in CRED, and RUST is tired of settling disputes with a
crowbar. He wants a wallet that can't be cheated: no negative deposits, no spending money you
don't have, no half-finished transfers.

**Write an exception and a class:**

- `class InsufficientFunds(Exception)`.
- `Wallet(owner, balance=0)` stores `owner`, `balance` and `history` (starts as an empty list).
- `deposit(amount)` adds to the balance, appends `("deposit", amount)` to `history`, and
  returns the new balance.
- `withdraw(amount)` subtracts, appends `("withdraw", amount)`, and returns the new balance. If
  `amount` is more than the balance, raise `InsufficientFunds`.
- `transfer(other, amount)` moves CRED from this wallet into `other` (another `Wallet`) and
  returns this wallet's new balance. Use your own `withdraw` and `deposit`.
- An amount must be a whole number (`int`) above 0. Anything else (`0`, `-5`, `2.5`, `"100"`)
  raises `ValueError`.

**A failed call changes nothing**: same balance, same history, on both wallets.

**RUST's test (this contract):**

```python
w = Wallet("{owner}", {start})
w.deposit({deposits[0]})       # {start + deposits[0]}
w.withdraw(10_000)  # InsufficientFunds, balance still {start + deposits[0]}
w.deposit(0)        # ValueError
```
"""
    starter = '''
class InsufficientFunds(Exception):
    pass


class Wallet:
    def __init__(self, owner, balance=0):
        pass

    def deposit(self, amount):
        """Add amount; record ("deposit", amount); return the new balance."""
        pass

    def withdraw(self, amount):
        """Subtract amount; record ("withdraw", amount); return the new balance.
        Raise InsufficientFunds if amount > balance."""
        pass

    def transfer(self, other, amount):
        """Move amount into the other wallet; return this wallet's new balance."""
        pass


if __name__ == "__main__":
    w = Wallet("NYX", 100)
    print(w.deposit(50))          # 150
    try:
        w.withdraw(10_000)
    except InsufficientFunds:
        print("blocked", w.balance)  # blocked 150
'''
    mission = build(
        title="CRED WALLET", tier=3, enemy="SKIM.worm", prompt=prompt, manual=_WALLET_MANUAL, starter=starter,
        concepts=("classes", "exceptions"), brief=("Write InsufficientFunds and the Wallet class below.",),
        intro=[line("rust", "Somebody deposited minus five hundred CRED last week. Make a wallet that says no.", "neutral"),
               line("cipher", "Validate first, change state second. A rejected call must leave no fingerprints.", "neutral")],
        victory=[line("rust", "No negatives, no overdrafts, no half-transfers. I can put the crowbar away. Mostly.", "smirk")],
    )

    hint_valid = "Check  isinstance(amount, int) and amount > 0  first; otherwise  raise ValueError(...)."

    def history_spot(got, expected):
        if isinstance(got, list) and got and isinstance(got[-1], list):
            return ("Each history entry should be a tuple like ('deposit', 50), not a list.",
                    'self.history.append(("deposit", amount))')
        return None

    @mission.check("InsufficientFunds — a custom exception")
    def _exc(ctx):
        exception_class(ctx, "InsufficientFunds", Exception)

    @mission.check("deposit() and withdraw() — the ledger")
    def _ledger(ctx):
        w = Replay(ctx, "Wallet", _Wallet, (owner, start), var="w",
                   hint="In __init__: self.owner, self.balance and self.history = []")
        w.attr("owner")
        w.attr("balance")
        w.attr("history")
        for amount in deposits:
            w.call("deposit", amount, hint="Add, record, then return self.balance.")
        w.call("withdraw", withdraw_ok, hint="Subtract, record, then return self.balance.")
        w.attr("balance")
        w.attr("history", spot=history_spot)
        z = Replay(ctx, "Wallet", _Wallet, (other_owner,), var="z", hint="balance defaults to 0:  def __init__(self, owner, balance=0)")
        z.attr("balance")

    @mission.check("bad amounts — rejected with ValueError")
    def _bad(ctx):
        w = Replay(ctx, "Wallet", _Wallet, (owner, start), var="w", hint=hint_valid)
        w.call("deposit", deposits[0])
        for amount in bad_amounts:
            w.call("deposit", amount, hint=hint_valid)
            w.attr("balance", hint="Validate BEFORE changing the balance.")
        for amount in (bad_amounts[1], bad_amounts[2]):
            w.call("withdraw", amount, hint=hint_valid)
        w.attr("balance")
        w.attr("history", hint="A rejected call must not be recorded.", spot=history_spot)

    @mission.check("overdraft and transfer() — all or nothing")
    def _transfer(ctx):
        w = Replay(ctx, "Wallet", _Wallet, (owner, start), var="w")
        w.call("withdraw", start + rng_extra, hint="if amount > self.balance:  raise InsufficientFunds(...)")
        w.attr("balance", hint="Raise BEFORE subtracting, so the balance is untouched.")
        w.attr("history")
        # transfers involve two of the player's objects, so drive them by hand
        cls = klass(ctx, "Wallet")
        steps = [f"a = Wallet({owner!r}, {start})", f"b = Wallet({other_owner!r}, {other_start})"]
        a = invoke(cls, call_text("Wallet", (owner, start)), (owner, start))
        b = invoke(cls, call_text("Wallet", (other_owner, other_start)), (other_owner, other_start))
        ra, rb = _Wallet(owner, start), _Wallet(other_owner, other_start)

        def compare(after: str):
            for label, mine, ref in (("a", a, ra), ("b", b, rb)):
                for attr in ("balance", "history"):
                    got = getattr(mine, attr, None)
                    want = getattr(ref, attr)
                    if got != want:
                        raise Fail(f"After `{'; '.join(steps)}`, `{label}.{attr}` is {show(got)} — expected "
                                   f"{show(want)}.{after}",
                                   hint="transfer = self.withdraw(amount) then other.deposit(amount). If the "
                                        "withdraw raises, the deposit never runs.")

        for amount, expect_exc in ((t_ok, None), (start + other_start + 999, InsufficientFunds), (-3, ValueError)):
            shown = f"a.transfer(b, {amount})"
            want_balance = None
            try:
                want_balance = ra.transfer(rb, amount)
            except (InsufficientFunds, ValueError):
                pass
            if expect_exc is None:
                got = method(a, "a", "transfer", (b, amount))
                steps.append(shown)
                if got != want_balance:
                    raise Fail(f"`{shown}` returned {show(got)} — expected {show(want_balance)} "
                               f"(a's new balance).", hint="Return self.balance at the end.")
                compare("")
                continue
            wanted = ctx.ns.get("InsufficientFunds") if expect_exc is InsufficientFunds else ValueError
            try:
                got = a.transfer(b, amount)
            except Exception as exc:  # noqa: BLE001 — the player's exception is inspected below
                if not (isinstance(wanted, type) and isinstance(exc, wanted)):
                    raise Fail(f"`{shown}` raised {type(exc).__name__}: {exc} — it should raise "
                               f"{expect_exc.__name__}.", hint="Let withdraw() do the checking.") from None
            else:
                raise Fail(f"`{shown}` returned {show(got)} — it should raise {expect_exc.__name__}.",
                           hint="Let withdraw() do the checking: it raises before anything moves.")
            steps.append(f"{shown} ✗{expect_exc.__name__}")
            compare(" A failed transfer must change nothing on either wallet.")

    rng_extra = rng.randint(1, 500)
    return mission


register(Drill("t3-cred-wallet", "CRED WALLET", 3, ("classes", "exceptions"), 900, _build_wallet))


# ══════════════════════════════════════════════════════════════════════════════════════
#  t3-packet-frames — PACKET FRAMES
# ══════════════════════════════════════════════════════════════════════════════════════

@dataclass
class _Frame:
    source: str
    size: int
    tags: list = field(default_factory=list)

    def is_jumbo(self):
        return self.size > 1500

    def tag(self, label):
        if label not in self.tags:
            self.tags.append(label)


def _ref_merge(a: _Frame, b: _Frame) -> _Frame:
    return _Frame(a.source, a.size + b.size, a.tags + [t for t in b.tags if t not in a.tags])


def _ref_largest(frames, n):
    return sorted(frames, key=lambda f: (-f.size, f.source))[:max(n, 0)]


_FRAME_MANUAL = """\
**`@dataclass` writes the boring parts of a class for you.** List the fields with type
annotations and Python generates `__init__`, `__repr__` and `__eq__`:

```python
from dataclasses import dataclass, field

@dataclass
class Reading:
    sensor: str
    value: float
    notes: list = field(default_factory=list)   # a NEW empty list for every object

    def is_hot(self):                          # normal methods still work
        return self.value > 90

r = Reading("core", 97.5)
r                                   # Reading(sensor='core', value=97.5, notes=[])
r == Reading("core", 97.5)          # True: compares field by field
```

**Never use `[]` as a default.** A plain `notes: list = []` would be one list shared by every
object, so `@dataclass` refuses it with a `ValueError`. `field(default_factory=list)` calls
`list()` fresh each time.

**Pure functions build new objects** instead of editing the ones they're given:

```python
def combine(a, b):
    return Reading(a.sensor, a.value + b.value, a.notes + b.notes)   # + makes a new list
```
"""


def _build_frames(rng):
    srcs = ["relay-" + str(rng.randint(1, 9)), "uplink-" + str(rng.randint(1, 9)),
            "node-" + str(rng.randint(10, 99)), "gate-" + str(rng.randint(1, 9)), "vault-" + str(rng.randint(1, 9))]
    rng.shuffle(srcs)
    frames = [(s, rng.choice([rng.randint(64, 1400), rng.randint(1501, 9000)])) for s in srcs]
    tie = rng.randint(400, 1400)
    frames[1] = (frames[1][0], tie)
    frames[3] = (frames[3][0], tie)
    tag_pool = ["hot", "crypt", "noise", "relay", "ghost", "core"]
    tags_a = rng.sample(tag_pool, 2)
    tags_b = [tags_a[0]] + rng.sample([t for t in tag_pool if t not in tags_a], 2)
    n_top = rng.randint(2, 4)
    probe_sizes = [1500, 1501, rng.randint(1, 1499), rng.randint(1502, 9000)]

    prompt = f"""\
The Oracle's packets come in frames, and the Archive team keeps writing the same frame class by
hand, badly. CIPHER suggests letting Python write it. Less code, fewer bugs.

**Write, using `@dataclass`:**

- `Frame` with fields `source: str`, `size: int` and `tags: list`, where `tags` defaults to a
  **new** empty list for every frame (`field(default_factory=list)`).
- A method `is_jumbo()`: `True` when `size` is over `1500`.
- A method `tag(label)`: adds `label` to `tags` unless it's already there.

**And two functions that never change the frames they're given:**

- `merge(a, b)` returns a **new** `Frame` with `a`'s source, the two sizes added, and `a`'s
  tags followed by any of `b`'s tags that `a` doesn't have.
- `largest(frames, n)` returns a list of the `n` biggest frames, biggest first; equal sizes go
  alphabetically by source. If `n` is bigger than the list, return them all.

**Intercept (this contract):**

```python
f = Frame("{frames[0][0]}", {frames[0][1]})
f                 # Frame(source='{frames[0][0]}', size={frames[0][1]}, tags=[])
f.is_jumbo()      # {frames[0][1] > 1500}
```
"""
    starter = '''
from dataclasses import dataclass, field


# Decorate with @dataclass and declare the fields:  source: str,  size: int,  tags (default: new empty list)
class Frame:
    pass

    # def is_jumbo(self): ...
    # def tag(self, label): ...


def merge(a, b):
    """A NEW Frame: a's source, a.size + b.size, a's tags + b's tags that a doesn't have."""
    pass


def largest(frames, n):
    """The n biggest frames, biggest first; ties alphabetical by source."""
    pass


if __name__ == "__main__":
    f = Frame("relay-3", 1800)
    g = Frame("node-12", 300, ["hot"])
    f.tag("crypt")
    print(f, f.is_jumbo())            # Frame(source='relay-3', size=1800, tags=['crypt']) True
    print(merge(f, g))                # Frame(source='relay-3', size=2100, tags=['crypt', 'hot'])
    print(largest([g, f], 1))         # [Frame(source='relay-3', ...)]
'''
    mission = build(
        title="PACKET FRAMES", tier=3, enemy="FRAGMENT.swarm", prompt=prompt, manual=_FRAME_MANUAL,
        starter=starter, concepts=("classes",), brief=("Write the Frame dataclass and two functions below.",),
        intro=[line("cipher", "Three engineers, three hand-written Frame classes, three bugs. Let the decorator write it.", "neutral"),
               line("vex", "Dataclasses? Cute. Watch the default list, {callsign}. Everybody trips on that one.", "smirk")],
        victory=[line("cipher", "Generated init, generated repr, no shared lists. Fewer lines, fewer places to be wrong.", "warm")],
    )

    def frame_cls(ctx):
        cls = klass(ctx, "Frame")
        if not dataclasses.is_dataclass(cls):
            raise Fail("`Frame` is a plain class. This contract wants Python to generate it with @dataclass.",
                       hint="Put  @dataclass  on the line above  class Frame:  and declare the fields with annotations.")
        return cls

    def as_tuple(frame):
        return (getattr(frame, "source", None), getattr(frame, "size", None), getattr(frame, "tags", None))

    def make(ctx, cls, source, size, tags=None):
        args = (source, size) if tags is None else (source, size, list(tags))
        return invoke(cls, call_text("Frame", args), args)

    @mission.check("Frame — a dataclass with three fields")
    def _shape(ctx):
        cls = frame_cls(ctx)
        names = [f.name for f in dataclasses.fields(cls)]
        if names != ["source", "size", "tags"]:
            raise Fail(f"Frame's fields are {names} — expected ['source', 'size', 'tags'], in that order.",
                       hint="One annotated line per field:  source: str,  size: int,  tags: list = field(...)")
        src, size = frames[0]
        f = make(ctx, cls, src, size)
        if as_tuple(f) != (src, size, []):
            raise Fail(f"`Frame({src!r}, {size})` gave {show(f)} — expected source={src!r}, size={size}, tags=[].",
                       hint="tags: list = field(default_factory=list)")
        expected = repr(_Frame(src, size))
        if repr(f) != expected:
            raise Fail(f"`repr(Frame({src!r}, {size}))` is {repr(f)!r} — expected {expected!r}.",
                       hint="Let @dataclass write __repr__ for you: delete any __repr__ you wrote.")
        if not f == make(ctx, cls, src, size):
            raise Fail(f"Two frames with the same fields aren't equal: `Frame({src!r}, {size}) == Frame({src!r}, {size})` "
                       f"is False.", hint="@dataclass generates __eq__. Don't override it.")

    @mission.check("tags — every frame gets its own list")
    def _own_list(ctx):
        cls = frame_cls(ctx)
        (sa, za), (sb, zb) = frames[0], frames[2]
        a, b = make(ctx, cls, sa, za), make(ctx, cls, sb, zb)
        method(a, "a", "tag", (tags_a[0],))
        if getattr(b, "tags", None) != []:
            raise Fail(f"After `a = Frame({sa!r}, {za}); b = Frame({sb!r}, {zb}); a.tag({tags_a[0]!r})`, `b.tags` is "
                       f"{show(b.tags)}. Both frames share one list.",
                       hint="tags: list = field(default_factory=list)  gives each frame a fresh list.")

    @mission.check("is_jumbo() and tag() — frame flags")
    def _methods(ctx):
        frame_cls(ctx)
        for size in probe_sizes:
            f = Replay(ctx, "Frame", _Frame, ("probe", size), var="f")
            f.call("is_jumbo", hint="Over 1500 means strictly greater: size > 1500.")
        f = Replay(ctx, "Frame", _Frame, (frames[1][0], frames[1][1]), var="f")
        for label in (tags_b[0], tags_b[1], tags_b[0], tags_b[2], tags_b[1]):
            f.call("tag", label, hint="Only append when the label isn't already in self.tags.")
            f.attr("tags", hint="Only append when the label isn't already in self.tags.")

    @mission.check("merge() and largest() — pure functions over frames")
    def _functions(ctx):
        cls = frame_cls(ctx)
        from engine.drills.library.tier3_common import function
        merge_fn, largest_fn = function(ctx, "merge"), function(ctx, "largest")
        for ta, tb in ((tags_a, tags_b), ([], tags_b), (tags_a, [])):
            (sa, za), (sb, zb) = frames[0], frames[4]
            a, b = make(ctx, cls, sa, za, ta), make(ctx, cls, sb, zb, tb)
            want = _ref_merge(_Frame(sa, za, list(ta)), _Frame(sb, zb, list(tb)))
            shown = f"merge(Frame({sa!r}, {za}, {ta}), Frame({sb!r}, {zb}, {tb}))"
            got = invoke(merge_fn, shown, (a, b), hint="return Frame(a.source, a.size + b.size, new_tags)")
            if not isinstance(got, cls):
                raise Fail(f"`{shown}` returned {show(got)} — expected a new Frame.",
                           hint="Build and return a Frame object, not a tuple or dict.")
            if as_tuple(got) != as_tuple(want):
                raise Fail(f"`{shown}` returned {show(got)} — expected {show(want)}.",
                           hint="Tags: everything in a.tags, then each tag of b.tags that isn't already in a.tags.")
            if as_tuple(a) != (sa, za, list(ta)) or as_tuple(b) != (sb, zb, list(tb)):
                raise Fail(f"`{shown}` returned the right frame but changed its inputs (a is now {show(a)}, "
                           f"b is now {show(b)}).", hint="Build a new tags list:  a.tags + [...]  instead of appending.")
            if got.tags is a.tags or got.tags is b.tags:
                raise Fail(f"`{shown}` gave the new frame the SAME tags list object as an input. Tag one and you "
                           f"tag both.", hint="Make a new list:  list(a.tags)  or  a.tags + [...]")
        pool = [make(ctx, cls, s, z) for s, z in frames]
        for n in (n_top, len(frames) + 3, 0):
            want = [as_tuple(f) for f in _ref_largest([_Frame(s, z) for s, z in frames], n)]
            shown = f"largest({show([f'{s}:{z}' for s, z in frames], 90)}, {n})"
            got = invoke(largest_fn, shown, (list(pool), n),
                         hint="sorted(frames, key=lambda f: (-f.size, f.source))[:n]")
            if not isinstance(got, list) or [as_tuple(f) for f in got] != want:
                shown_got = [f"{getattr(f, 'source', f)}:{getattr(f, 'size', '')}" for f in got] \
                    if isinstance(got, list) else got
                raise Fail(f"`{shown}` returned {show(shown_got)} — expected {show([f'{s}:{z}' for s, z, _ in want])}.",
                           hint="sorted(frames, key=lambda f: (-f.size, f.source))[:n]  (ties alphabetical by source)")

    return mission


register(Drill("t3-packet-frames", "PACKET FRAMES", 3, ("classes",), 900, _build_frames))
