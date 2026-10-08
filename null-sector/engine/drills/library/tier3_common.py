"""Tier-3/4 drill toolkit: the check machinery shared by every `tier3_*` and `tier4_*` module.

This module registers no drills. It gives the Foundry and Archive drills one consistent way to
fail: the exact call (or replayed sequence of calls) that broke, what came back, what should
have come back, and when a classic mistake is recognisable, a sentence aimed at that mistake.

Pieces:

* `expect` / `expect_raises` — call a player function on cases and compare with a reference.
* `Replay` — drive a player object and a reference object through the same method calls and
  attribute reads, and report the replayed history on the first difference.
* Work meters, so "make it fast" is graded deterministically instead of with a stopwatch:
  `Tape` (a list stand-in that counts element reads), `Feed` (an iterator that counts pulls,
  for laziness), `Oracle` (a function that counts calls) and `line_budget` (counts lines run
  inside the player's file). All of them stop runaway code with `Runaway`.
* AST helpers (`imports`, `calls_itself`, `bare_excepts`, …) and the starter `header`.
"""
from __future__ import annotations

import ast
import contextlib
import copy
import math
import sys
from typing import Callable

from engine.mission import Fail, type_name

LABELS = {3: "INTERMEDIATE", 4: "INTERMEDIATE+"}
PREVIEW = 8               # items shown per list/tuple/dict in a failure message

CALLSIGNS = ("NYX", "KADE", "VANTA", "ORRIN", "SABLE", "JUNO", "TALON", "MIRA", "CROW", "ASH",
             "LUX", "REN", "ONYX", "PIKE", "ZERO", "HALCYON", "DREG", "SOL", "IVY", "KESTREL")
SECTORS = ("DEAD-ZONE", "GRID", "FOUNDRY", "ARCHIVE", "CORE")


class Runaway(BaseException):
    """Raised inside player code when it blows a work budget (reads, pulls, probes, lines).

    It derives from BaseException on purpose: a loop that catches `Exception` can't swallow it,
    so runaway code ends the layer with a clear message instead of timing out the grader.
    """


# ── showing values ────────────────────────────────────────────────────────────────────

def _fmt(value) -> str:
    if value is None or isinstance(value, bool):
        return repr(value)
    if isinstance(value, float):
        text = repr(value)
        if math.isfinite(value) and len(text) > 13:
            text = f"{value:.10g}"
            if not any(ch in text for ch in ".e"):
                text += ".0"
        return text
    if isinstance(value, (list, tuple)):
        items = [_fmt(v) for v in value[:PREVIEW]]
        if len(value) > PREVIEW:
            items.append(f"… {len(value) - PREVIEW} more")
        inner = ", ".join(items)
        if isinstance(value, list):
            return f"[{inner}]"
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    if isinstance(value, dict):
        pairs = [f"{_fmt(k)}: {_fmt(v)}" for k, v in list(value.items())[:PREVIEW]]
        if len(value) > PREVIEW:
            pairs.append(f"… {len(value) - PREVIEW} more")
        return "{" + ", ".join(pairs) + "}"
    if isinstance(value, Tape):
        return value.preview()
    try:
        return repr(value)
    except Exception:  # noqa: BLE001 — a broken __repr__ in player code must not crash the check
        return f"<{type(value).__name__}>"


def show(value, limit: int = 140) -> str:
    """A short, readable repr: floats trimmed, long data elided, never longer than `limit`."""
    text = _fmt(value)
    text = text.replace("`", "'")          # the client renders `…` as code; keep values intact
    return text if len(text) <= limit else text[: limit - 1] + "…"


def call_text(name: str, args=(), kwargs=None, limit: int = 70) -> str:
    parts = [show(a, limit) for a in args] + [f"{k}={show(v, 50)}" for k, v in (kwargs or {}).items()]
    return f"{name}({', '.join(parts)})"


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


# ── comparing values ──────────────────────────────────────────────────────────────────

def same(got, expected, *, approx: bool = False, rel_tol: float = 1e-6, abs_tol: float = 1e-9) -> bool:
    """Structural equality with strict types (True is not 1, 3 is not 3.0 unless `approx`)."""
    if isinstance(expected, bool) or isinstance(got, bool):
        return type(got) is type(expected) and got == expected
    if isinstance(expected, float) and approx:
        return isinstance(got, (int, float)) and math.isclose(got, expected, rel_tol=rel_tol, abs_tol=abs_tol)
    if isinstance(expected, (list, tuple)):
        return (type(got) is type(expected) and len(got) == len(expected)
                and all(same(g, e, approx=approx, rel_tol=rel_tol, abs_tol=abs_tol) for g, e in zip(got, expected)))
    if isinstance(expected, dict):
        # Any dict (defaultdict and Counter included) with exactly the same keys; order is free.
        return (isinstance(got, dict) and _keyset(got) == _keyset(expected)
                and all(same(got[k], expected[k], approx=approx, rel_tol=rel_tol, abs_tol=abs_tol) for k in expected))
    return type(got) is type(expected) and got == expected


def _keyset(mapping: dict) -> set:
    return {(type(k), k) for k in mapping}


def shape_note(got, expected) -> str:
    """One sentence on HOW a result is off, when the problem is its shape rather than its value."""
    if got is None and expected is not None:
        return " It returned None: every path through the function needs a `return`."
    if isinstance(expected, dict) and isinstance(got, dict):
        pass
    elif isinstance(expected, (list, tuple, dict)) and type(got) is not type(expected):
        return f" That's {type_name(type(got))}; the contract asks for {type_name(type(expected))}."
    if isinstance(expected, (list, tuple)) and len(got) != len(expected):
        return f" It has {len(got)} items; it should have {len(expected)}."
    if isinstance(expected, dict) and isinstance(got, dict) and _keyset(got) != _keyset(expected):
        missing = [k for k in expected if (type(k), k) not in _keyset(got)]
        extra = [k for k in got if (type(k), k) not in _keyset(expected)]
        bits = []
        if missing:
            bits.append(f"missing keys {show(missing, 60)}")
        if extra:
            bits.append(f"unexpected keys {show(extra, 60)}")
        return " It has " + " and ".join(bits) + "."
    if isinstance(expected, bool) and not isinstance(got, bool):
        return f" That's {type_name(type(got))}; it must be exactly True or False."
    if isinstance(expected, int) and isinstance(got, float):
        return " That's a float; the contract asks for an int (use // or int())."
    if isinstance(expected, (int, float)) and not isinstance(expected, bool) \
            and (not isinstance(got, (int, float)) or isinstance(got, bool)):
        return f" That's {type_name(type(got))}, not a number."
    return ""


# ── calling the player's code ─────────────────────────────────────────────────────────

def function(ctx, name: str):
    fn = ctx.get(name)
    if isinstance(fn, type) or not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function.", hint=f"Define it with  def {name}(...):")
    return fn


def klass(ctx, name: str):
    cls = ctx.get(name)
    if not isinstance(cls, type):
        raise Fail(f"`{name}` exists but isn't a class.", hint=f"Define it with  class {name}:")
    return cls


def exception_class(ctx, name: str, base: type = Exception):
    """The player's custom exception class `name`, which must inherit from `base`."""
    cls = klass(ctx, name)
    if not issubclass(cls, base):
        raise Fail(f"`{name}` is a class, but it doesn't inherit from {base.__name__}, so it can't be raised "
                   f"or caught as one.", hint=f"class {name}({base.__name__}):")
    return cls


def split_case(case):
    if isinstance(case, dict):
        return (), dict(case)
    return tuple(case), {}


def invoke(fn, shown: str, args=(), kwargs=None, *, hint: str = "", errors: Callable | None = None,
           runaway: str = ""):
    """Call player code; a crash or a blown budget becomes a Fail that names the exact call."""
    try:
        return fn(*args, **(kwargs or {}))
    except Runaway:
        raise Fail(f"`{shown}` never stopped. {runaway or 'It kept going past every limit.'}", hint=hint) from None
    except Fail:
        raise
    except RecursionError:
        raise Fail(f"`{shown}` recursed too deep (RecursionError): a call kept calling itself without ever "
                   f"reaching a base case.",
                   hint=hint or "Every recursive function needs a case that returns WITHOUT calling itself, "
                                "and every other call must move closer to it.") from None
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        found = errors(exc) if errors else None
        if found:
            raise Fail(f"`{shown}` raised {type(exc).__name__}: {exc}. {found[0]}", hint=found[1] or hint) from None
        raise Fail(f"`{shown}` raised {type(exc).__name__}: {exc}",
                   hint=hint or "Call it on this input yourself and read the traceback from the bottom up.") from None


def expect(ctx, name: str, cases, reference: Callable, *, approx: bool = False, rel_tol: float = 1e-6,
           abs_tol: float = 1e-9, hint: str = "", pure: bool = False, spot: Callable | None = None,
           errors: Callable | None = None) -> None:
    """Call `name` on every case and compare with `reference` (both get deep copies).

    `spot(got, args, kwargs) -> (message, hint) | None` names a recognisable wrong answer.
    `pure=True` also fails a function that changed the arguments it was given.
    """
    fn = function(ctx, name)
    for case in cases:
        args, kwargs = split_case(case)
        shown = call_text(name, args, kwargs)
        expected = reference(*copy.deepcopy(args), **copy.deepcopy(kwargs))
        given_args, given_kwargs = copy.deepcopy(args), copy.deepcopy(kwargs)
        got = invoke(fn, shown, given_args, given_kwargs, hint=hint, errors=errors)
        if not same(got, expected, approx=approx, rel_tol=rel_tol, abs_tol=abs_tol):
            found = spot(got, copy.deepcopy(args), copy.deepcopy(kwargs)) if spot else None
            if found:
                raise Fail(f"`{shown}` returned {show(got)}. {found[0]}", hint=found[1] or hint)
            raise Fail(f"`{shown}` returned {show(got)} — expected {show(expected)}.{shape_note(got, expected)}",
                       hint=hint)
        if pure and (given_args != args or given_kwargs != kwargs):
            raise Fail(f"`{shown}` returned the right answer but changed the data it was given "
                       f"(the caller's input is now {show(given_args or given_kwargs, 90)}).",
                       hint="Never edit the caller's data in place. Build new lists/dicts and return those.")


def expect_raises(ctx, name: str, args=(), kwargs=None, *, exc: type = ValueError, why: str = "",
                  hint: str = "", label: str = "") -> BaseException:
    """`name(*args)` must raise `exc` (or a subclass). Returns the exception for further checks."""
    fn = function(ctx, name)
    kwargs = kwargs or {}
    shown = call_text(name, args, kwargs)
    reason = f" ({why})" if why else ""
    wanted = label or exc.__name__
    try:
        got = fn(*copy.deepcopy(args), **copy.deepcopy(kwargs))
    except Runaway:
        raise Fail(f"`{shown}` never stopped.", hint=hint) from None
    except exc as caught:
        return caught
    except Exception as other:  # noqa: BLE001
        raise Fail(f"`{shown}` raised {type(other).__name__}: {other} — the contract says {wanted}{reason}.",
                   hint=hint or f"Check the input yourself and  raise {wanted}(\"...\")") from None
    raise Fail(f"`{shown}` returned {show(got)} instead of raising {wanted}{reason}.",
               hint=hint or f"Check the input and  raise {wanted}(\"...\")")


def method(obj, label: str, meth: str, args=(), kwargs=None, *, hint: str = ""):
    """Call obj.meth(*args) with crash reporting, shown as `label.meth(...)`."""
    shown = call_text(f"{label}.{meth}", args, kwargs)
    bound = getattr(obj, meth, None)
    if not callable(bound):
        raise Fail(f"`{label}` has no `{meth}()` method.", hint=f"Add  def {meth}(self, ...):  inside the class.")
    return invoke(bound, shown, args, kwargs, hint=hint)


# ── replaying method calls on a player object next to a reference object ──────────────

class Replay:
    """Drive a player object and a reference object through identical calls.

    Every call and attribute read is compared at once. On the first difference the layer fails
    with the replayed history, e.g.  After `m = Magazine(6); m.load(9)`, `m.rounds` is 9 —
    expected 6.  Exceptions are part of the contract: if the reference raises, the player must
    raise the same type (custom exception names are looked up in the player's file).
    """

    KEEP = 5

    def __init__(self, ctx, cls_name: str, reference: Callable, args=(), kwargs=None, *, var: str = "obj",
                 hint: str = ""):
        self.ctx = ctx
        self.var = var
        self.hint = hint
        cls = klass(ctx, cls_name)
        kwargs = kwargs or {}
        built = f"{var} = {call_text(cls_name, args, kwargs)}"
        self.steps = [built]
        self.ref = reference(*copy.deepcopy(args), **copy.deepcopy(kwargs))
        self.obj = invoke(cls, built.split(" = ", 1)[1], copy.deepcopy(args), copy.deepcopy(kwargs), hint=hint)

    # history
    def trail(self) -> str:
        steps = self.steps[-self.KEEP:]
        return ("… " if len(self.steps) > self.KEEP else "") + "; ".join(steps)

    def fail(self, what: str, hint: str | None = None):
        raise Fail(f"After `{self.trail()}`, {what}", hint=self.hint if hint is None else hint)

    def _expected_exception(self, exc: BaseException) -> type:
        kind = type(exc)
        if kind.__module__ == "builtins":
            return kind
        mine = self.ctx.ns.get(kind.__name__)
        if isinstance(mine, type) and issubclass(mine, BaseException):
            return mine
        raise Fail(f"This step should raise `{kind.__name__}`, but your file doesn't define that exception class.",
                   hint=f"class {kind.__name__}(Exception):  at the top level of your file.")

    def call(self, meth: str, *args, approx: bool = False, hint: str | None = None, spot: Callable | None = None,
             record: bool = True):
        """Call `meth` on both objects. Returns the player's result (or the exception it raised)."""
        shown = call_text(f"{self.var}.{meth}", args)
        try:
            expected, ref_exc = getattr(self.ref, meth)(*copy.deepcopy(args)), None
        except Exception as exc:  # noqa: BLE001 — the reference raising is part of the contract
            expected, ref_exc = None, exc
        bound = getattr(self.obj, meth, None)
        if not callable(bound):
            self.fail(f"`{self.var}` has no `{meth}()` method.", hint=f"Add  def {meth}(self, ...):  to the class.")
        try:
            got, exc = bound(*copy.deepcopy(args)), None
        except Runaway:
            self.fail(f"`{shown}` never stopped.")
        except Fail:
            raise
        except Exception as caught:  # noqa: BLE001
            got, exc = None, caught
        if ref_exc is not None:
            wanted = self._expected_exception(ref_exc)
            if exc is None:
                found = spot(got, None) if spot else None
                self.fail(f"`{shown}` returned {show(got)} — it should raise {type(ref_exc).__name__}. "
                          + (found[0] if found else ""), hint if hint is not None else (found[1] if found else None))
            if not isinstance(exc, wanted):
                self.fail(f"`{shown}` raised {type(exc).__name__}: {exc} — it should raise {type(ref_exc).__name__}.",
                          hint)
            if record:
                self.steps.append(f"{shown} ✗{type(ref_exc).__name__}")
            return exc
        if exc is not None:
            self.fail(f"`{shown}` raised {type(exc).__name__}: {exc}", hint)
        if not same(got, expected, approx=approx):
            found = spot(got, expected) if spot else None
            if found:
                self.fail(f"`{shown}` returned {show(got)}. {found[0]}", found[1] or hint)
            self.fail(f"`{shown}` returned {show(got)} — expected {show(expected)}.{shape_note(got, expected)}", hint)
        if record:
            self.steps.append(shown)
        return got

    def attr(self, name: str, *, approx: bool = False, hint: str | None = None, spot: Callable | None = None):
        expected = getattr(self.ref, name)
        if not hasattr(self.obj, name):
            self.fail(f"`{self.var}` has no attribute `{name}`.",
                      hint=f"Set it in __init__:  self.{name} = ...")
        got = getattr(self.obj, name)
        if not same(got, expected, approx=approx):
            found = spot(got, expected) if spot else None
            if found:
                self.fail(f"`{self.var}.{name}` is {show(got)}. {found[0]}", found[1] or hint)
            self.fail(f"`{self.var}.{name}` is {show(got)} — expected {show(expected)}.{shape_note(got, expected)}",
                      hint)
        return got

    def value(self, label: str, got_fn: Callable, expected_fn: Callable, *, approx: bool = False,
              hint: str | None = None):
        """Compare an arbitrary read, e.g. ("len(w)", lambda o: len(o), lambda r: len(r))."""
        expected = expected_fn(self.ref)
        try:
            got = got_fn(self.obj)
        except Runaway:
            self.fail(f"`{label}` never stopped.")
        except Exception as exc:  # noqa: BLE001
            self.fail(f"`{label}` raised {type(exc).__name__}: {exc}", hint)
        if not same(got, expected, approx=approx):
            self.fail(f"`{label}` gave {show(got)} — expected {show(expected)}.{shape_note(got, expected)}", hint)
        return got


# ── work meters ───────────────────────────────────────────────────────────────────────

class Tape:
    """A read-only, list-like sequence that meters every element it hands out.

    Supports len(), indexing (negative too), slicing, iteration, `in`, .index() and .count().
    Every element read costs 1; past `cap` reads it raises Runaway inside the player's code.
    """

    def __init__(self, items, cap: int = 1_000_000):
        self._items = list(items)
        self.reads = 0
        self.cap = cap

    def _charge(self, n: int = 1) -> None:
        self.reads += n
        if self.reads > self.cap:
            raise Runaway(f"read cap {self.cap} exceeded")

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index):
        if isinstance(index, slice):
            part = self._items[index]
            self._charge(len(part))
            return part
        value = self._items[index]           # IndexError / TypeError exactly like a list
        self._charge()
        return value

    def __iter__(self):
        for value in self._items:
            self._charge()
            yield value

    def __reversed__(self):
        for value in reversed(self._items):
            self._charge()
            yield value

    def __contains__(self, item) -> bool:
        return any(value == item for value in self)

    def index(self, item, *_):
        for i, value in enumerate(self):
            if value == item:
                return i
        raise ValueError(f"{item!r} is not in list")

    def count(self, item) -> int:
        return sum(1 for value in self if value == item)

    def __eq__(self, other) -> bool:
        return self._items == (other._items if isinstance(other, Tape) else other)

    __hash__ = None

    def preview(self) -> str:
        if len(self._items) <= 12:
            return repr(self._items)
        head = ", ".join(repr(v) for v in self._items[:4])
        tail = ", ".join(repr(v) for v in self._items[-2:])
        return f"[{head}, … {len(self._items) - 6} more …, {tail}]"

    __repr__ = preview


class Feed:
    """An iterator that counts how many items have been pulled from it (laziness meter)."""

    def __init__(self, source, cap: int = 10_000):
        self._it = iter(source)
        self.pulled = 0
        self.cap = cap

    def __iter__(self):
        return self

    def __next__(self):
        if self.pulled >= self.cap:
            raise Runaway(f"pulled {self.cap} items")
        value = next(self._it)
        self.pulled += 1
        return value


class Oracle:
    """A callable that answers through `answer(x)` and counts every call it receives."""

    def __init__(self, answer: Callable, cap: int):
        self.answer = answer
        self.calls = 0
        self.cap = cap

    def __call__(self, *args):
        self.calls += 1
        if self.calls > self.cap:
            raise Runaway(f"called {self.cap} times")
        return self.answer(*args)


@contextlib.contextmanager
def line_budget(ctx, limit: int):
    """Count the lines executed inside the player's file; past `limit`, raise Runaway there.

    Lines run by builtins and the standard library are free; only the player's own Python is
    metered, which is exactly the part whose growth rate a drill wants to grade.
    """
    filename = ctx.ns.get("__file__", "")
    meter = {"lines": 0, "limit": limit}

    def local(frame, event, arg):
        if event == "line":
            meter["lines"] += 1
            if meter["lines"] > limit:
                raise Runaway(f"line budget {limit} exceeded")
        return local

    def watch(frame, event, arg):
        return local if frame.f_code.co_filename == filename else None

    previous = sys.gettrace()
    sys.settrace(watch)
    try:
        yield meter
    finally:
        sys.settrace(previous)


# ── reading the player's code ─────────────────────────────────────────────────────────

def imports(ctx, module: str) -> bool:
    """True if the file imports `module` (import x / import x.y / from x import y)."""
    for node in ast.walk(ctx.tree):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] == module for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == module:
            return True
    return False


def function_node(ctx, name: str):
    for node in ast.walk(ctx.tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def calls_itself(ctx, name: str) -> bool:
    """True if `def name` contains a call to `name(...)` (directly recursive)."""
    node = function_node(ctx, name)
    if node is None:
        return False
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name
               for n in ast.walk(node))


def except_handlers(ctx) -> list[ast.ExceptHandler]:
    return [n for n in ast.walk(ctx.tree) if isinstance(n, ast.ExceptHandler)]


def handler_names(handler: ast.ExceptHandler) -> list[str]:
    """['ValueError', 'TypeError'] for  except (ValueError, TypeError):  ; [] for a bare except."""
    if handler.type is None:
        return []
    nodes = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    names = []
    for n in nodes:
        if isinstance(n, ast.Name):
            names.append(n.id)
        elif isinstance(n, ast.Attribute):
            names.append(n.attr)
    return names


def string_constants(ctx) -> list[str]:
    return [n.value for n in ast.walk(ctx.tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


# ── starter files ─────────────────────────────────────────────────────────────────────

_HEADER = '''"""
==============================================================================
  DRILL // {title:<44}TIER {tier} // {label}
==============================================================================
{lines}
  Save, then HACK. The grader calls your code on fresh, hidden inputs, so it
  must work for any data, not just the sample at the bottom of this file.
"""
'''


def header(title: str, tier: int, *lines: str) -> str:
    body = "\n".join(f"  {line}".rstrip() for line in lines)
    return _HEADER.format(title=title, tier=tier, label=LABELS[tier], lines=body)


# ── more code readers ─────────────────────────────────────────────────────────────────

def calls_in(ctx, func_name: str) -> set[str]:
    """Names called inside `def func_name` (plain calls and method calls): {'sorted', 'sort', 'count'}."""
    node = function_node(ctx, func_name)
    found: set[str] = set()
    if node is None:
        return found
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                found.add(n.func.id)
            elif isinstance(n.func, ast.Attribute):
                found.add(n.func.attr)
    return found


def forbid(ctx, func_name: str, banned, message: str, hint: str = "") -> None:
    """Fail if `def func_name` calls any of `banned` (e.g. {'sorted', 'sort'} in a merge drill)."""
    used = sorted(calls_in(ctx, func_name) & set(banned))
    if used:
        raise Fail(f"`{func_name}` calls {', '.join(f'{u}()' for u in used)}. {message}", hint=hint)


def handlers_in(ctx, func_name: str) -> list[ast.ExceptHandler]:
    node = function_node(ctx, func_name)
    return [n for n in ast.walk(node) if isinstance(n, ast.ExceptHandler)] if node else []


def generator_function(ctx, name: str):
    """The player's `name`, which must be a generator function (its body uses `yield`)."""
    import inspect
    fn = function(ctx, name)
    if not inspect.isgeneratorfunction(fn):
        raise Fail(f"`{name}` is a normal function. This contract needs a generator: a function that uses "
                   f"`yield` to hand out values one at a time.",
                   hint="Replace  result.append(x) ... return result  with  yield x  inside the loop.")
    return fn


def pull(gen, shown: str, n: int | None = None, *, hint: str = "") -> list:
    """Collect up to `n` items (all, if None) from a player generator, with crash reporting."""
    import itertools

    def collect():
        it = iter(gen)
        return list(it) if n is None else list(itertools.islice(it, n))
    return invoke(collect, shown, hint=hint,
                  runaway="It kept pulling from the source long after it had what it needed.")


@contextlib.contextmanager
def sql_trace(conn):
    """Record every SQL statement a sqlite3 connection runs: `with sql_trace(conn) as log: ...`."""
    log: list[str] = []
    conn.set_trace_callback(log.append)
    try:
        yield log
    finally:
        conn.set_trace_callback(None)


# ── building a tier-3/4 drill mission ─────────────────────────────────────────────────

def line(speaker: str, text: str, mood: str = "neutral") -> dict:
    """One dialogue line (GAME_DESIGN §5.2)."""
    if len(text) > 160:
        raise ValueError(f"dialogue line over 160 chars: {text!r}")
    return {"speaker": speaker, "text": text, "mood": mood}


CRASH_POOL = [
    [line("cipher", "Your file fell over before the grader could ask it anything. The last line of the trace names the problem.", "alarm")],
    [line("cipher", "Crash on load. Run the file yourself: the sample block at the bottom will show you the same error.", "alarm")],
    [line("rust", "Code broke before the test even started. I don't pay for parts that arrive in pieces.", "smirk")],
    [line("cipher", "Indentation, a missing colon, a typo in a name. Small things. Read the line number, then the line above it.", "neutral")],
]

FAIL_POOL = [
    [line("cipher", "The failing layer shows the exact call. Run that one case by hand and compare each step.", "neutral")],
    [line("cipher", "Close is not equal. Check the edge case in the message first: empty input, a tie, a duplicate.", "neutral")],
    [line("vex", "Still on this one? I cleared it before my coffee cooled. Read the hint, {callsign}.", "smirk")],
    [line("nova", "Contract's still open, {callsign}. One layer at a time. The log tells you which one.", "warm")],
    [line("rust", "Half a part is no part. Finish the job and we talk payment.", "neutral")],
    [line("cipher", "The grader feeds fresh data every time. If it only works on the sample, it doesn't work.", "neutral")],
]


def build(*, title: str, tier: int, enemy: str, prompt: str, manual: str, starter: str,
          concepts: tuple[str, ...], intro: list[dict], victory: list[dict], brief: tuple[str, ...] = (),
          timeout: float = 10.0):
    """A tier-3/4 drill Mission with the house header, dialogue pools and enemy name."""
    from engine.drills import make_mission   # late import: engine.drills imports this package
    mission = make_mission(title=title, prompt=prompt, starter=header(title, tier, *brief) + starter.lstrip("\n"),
                           tier=tier, concepts=concepts, manual=manual, enemy=enemy, timeout=timeout)
    mission.dialogue = {"intro": intro, "crash": CRASH_POOL, "fail": FAIL_POOL, "victory": victory}
    return mission


# ── seeded flavour data ───────────────────────────────────────────────────────────────

UNITS = ("reactor", "coolant", "relay", "furnace", "conveyor", "uplink", "turbine", "vault", "gate", "smelter")
WORDS = ("ash", "ember", "static", "signal", "ghost", "cipher", "relay", "pulse", "shard", "vector", "null",
         "drift", "spark", "echo", "rust", "flux", "grid", "core", "node", "byte")


def sample(rng, pool, k: int) -> list:
    """k distinct items from `pool`, in random order."""
    return rng.sample(list(pool), k)
