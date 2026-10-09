"""LAB NP01 // FIRST ARRAY — arrays, dtypes & shape (TENSOR SUTRAS, docs/GAME_DESIGN.md §13)."""
from __future__ import annotations

import ast
import warnings

from engine.mission import Fail, Mission

try:
    import numpy as np
except ImportError:      # the Lab shows `pip install numpy`; the module must still import without it
    np = None


MISSION = Mission(
    id="NP01",
    slug="np01_first_array",
    title="FIRST ARRAY",
    concept="Arrays, dtypes & shape",
    enemy="SHAPELESS.wraith",
    xp=160,
    par_seconds=25 * 60,
    tier=3,
    concepts=("numpy", "types"),
    requires=("numpy",),
    timeout=15,
    run_as_main=False,
    enemy_art="""\
   ░▒▓▓▓▓▓▓▒░
  ▒▓ ?  ?  ?▓▒
  ▓  ░▒▓▓▒░  ▓
  ▓ ▒  ??  ▒ ▓
   ▒▓░    ░▓▒
    ░▒▓▒▓▒░""",
    briefing="""\
The Scriptorium Lab is the coldest room in the Monastery and the only one with a lock. **MOTHER
ADA** keeps the Order's machine-learning canon here. What survived the Null Event of it: half a
shelf, and ash between the pages.

She sets a cracked slate in front of you. Columns of telemetry, every number stored as text.
"Before the Core, before any model, there was an array," she says. "Tell me its shape. Tell me
what it is made of. Then we can talk about learning."

The slate flickers. **SHAPELESS.wraith** lives in the burn: it eats metadata, flattens batches
into soup, and wraps the brightest pixel around to black.

**Give the data a shape and a dtype it cannot lose: write the five array rites.**
""",
    why="""\
Every model has an input contract: a **shape** and a **dtype**. scikit-learn wants `X` as a 2-D
array `(n_samples, n_features)`; a PyTorch image model wants `float32` batches. Break the
contract and you get a crash if you're lucky, or a model that silently learns from garbage if
you're not.

```python
pixels = np.load("scans.npy")            # (60000, 28, 28) uint8, straight off disk
X = pixels.reshape(len(pixels), -1)      # (60000, 784): one row per sample
X = X.astype(np.float32) / 255           # what torchvision's ToTensor() does
print(X.shape, X.dtype)                  # the first line of every debugging session
```

Most ML bugs you will meet this year are shape or dtype bugs. Checking `.shape` and `.dtype`
first is the habit that finds them in seconds instead of hours.
""",
    manual="""\
**1. An array is a grid of ONE type, with a shape.** `np.array` turns nested lists into one:

```python
import numpy as np
a = np.array([[1.5, 2.0, 0.0], [3.0, 4.5, 1.0]])
a.shape   # (2, 3)   rows, columns: always a tuple
a.ndim    # 2        how many axes
a.size    # 6        how many numbers in total
a.dtype   # dtype('float64')    str(a.dtype) gives 'float64'
len(a)    # 2        only the FIRST axis, not the element count
```

**2. dtype is what each number is made of.** `astype` returns a NEW array of another type:

```python
raw = np.array(["0.5", "1.25"])           # dtype '<U4': still TEXT
raw.astype(np.float32)                    # array([0.5, 1.25], dtype=float32)
np.array(["0.5", "1.25"], dtype=np.float32)   # convert while building
```

Models train in `float32`: half the memory of numpy's default `float64`, and what GPUs expect.

**3. reshape rearranges, never changes, the numbers.** `-1` means "work this axis out":

```python
batch = np.zeros((10, 28, 28))
batch.reshape(10, -1).shape      # (10, 784): keep the batch axis, flatten the rest
batch.reshape(len(batch), -1)    # same thing, with no hard-coded 10
np.array([]).shape               # (0,)  an empty list has lost its columns...
np.array([]).reshape(-1, 3).shape   # (0, 3) ...reshape gives them back
```

**4. Integers overflow.** `uint8` holds 0..255 (image pixels). Past the edge it *wraps*:

```python
px = np.array([250, 10], dtype=np.uint8)
px + 10                     # array([4, 20])  250 + 10 wrapped round to 4!
(px / 255).astype(np.uint8) # array([0, 0])   astype chops decimals: 0.98 becomes 0
wide = px.astype(np.int16) + 10            # widen first: 260 fits in int16
np.clip(wide, 0, 255).astype(np.uint8)     # array([255, 20])  then clamp and narrow
```

NumPy 2 refuses a Python int that can't fit at all (`px + 300` or `px + (-10)` raise
`OverflowError`), but in-range numbers still wrap silently. **Common mistake:** clipping *after*
the overflow, `np.clip(px + 10, 0, 255)`: the wrap already happened, so the clip sees 4.

**5. The same rites in the big libraries.** PyTorch: `torch.tensor(rows, dtype=torch.float32)`,
`x.shape`, `x.reshape(len(x), -1)` (or `nn.Flatten()`); `torchvision.transforms.ToTensor()`
turns uint8 pixels into float32 in [0, 1]. scikit-learn's famous error "Expected 2D array, got 1D
array instead" is asking you for `reshape(-1, 1)`.
""",
    starter='''
"""
==============================================================================
  LAB NP01 // FIRST ARRAY                            TARGET: SHAPELESS.wraith
==============================================================================
  MOTHER ADA's first rite: know the shape and the dtype of what you hold.
  Write the functions below. The grader calls them with FRESH arrays it
  generates itself, so they must work for any input, not only the examples.
  Save, then HACK from the Lab.
"""
import numpy as np


# -- OBJECTIVE 1 -------------------------------------------------------------
def describe(a):
    """Return the vital signs of array `a` as a dict:
        {"shape": a tuple, "ndim": an int, "size": an int, "dtype": a str like "float32"}

    describe(np.zeros((2, 3), dtype=np.float32))
        -> {"shape": (2, 3), "ndim": 2, "size": 6, "dtype": "float32"}
    """
    # TODO: read .shape, .ndim, .size and .dtype (wrap the dtype in str(...)).
    pass


# -- OBJECTIVE 2 -------------------------------------------------------------
def as_features(rows, n_features):
    """Turn rows of TEXT numbers into a float32 feature matrix of shape (len(rows), n_features).

    as_features([["0.5", "2"], ["1.25", "-3"]], 2)
        -> array([[ 0.5 ,  2.  ], [ 1.25, -3.  ]], dtype=float32)
    as_features([], 4).shape  ->  (0, 4)     no rows, but still 4 columns
    """
    # TODO: np.array(..., dtype=np.float32), then reshape(-1, n_features).
    pass


# -- OBJECTIVE 3 -------------------------------------------------------------
def flatten_images(images):
    """Flatten a batch of images (n, h, w) or (n, h, w, c) into (n, everything else).

    One row per image, in row-by-row order. Keep the dtype.
    flatten_images(np.zeros((5, 4, 3))).shape  ->  (5, 12)
    """
    # TODO: keep axis 0, let -1 work out the rest. Don't hard-code sizes.
    pass


# -- OBJECTIVE 4 // CORRUPTED CODE -------------------------------------------
def to_unit(pixels):
    """Scale uint8 pixels (0..255) to float32 values in [0, 1].

    to_unit(np.array([0, 51, 255], dtype=np.uint8))  ->  array([0. , 0.2, 1. ], dtype=float32)
    """
    # SHAPELESS got here first. Every scan comes back black. Hack once, read
    # the grader's message, and fix the dtype step.
    return (pixels / 255).astype(np.uint8)


# -- OBJECTIVE 5 -------------------------------------------------------------
def brighten(pixels, amount):
    """Add `amount` (may be negative) to uint8 pixels WITHOUT wrapping around.

    Results above 255 stay 255, below 0 stay 0. Return a NEW uint8 array of the
    same shape; leave `pixels` itself unchanged.
    brighten(np.array([250, 10, 3], dtype=np.uint8), 10)  ->  array([255, 20, 13], dtype=uint8)
    brighten(np.array([250, 10, 3], dtype=np.uint8), -5)  ->  array([245,  5,  0], dtype=uint8)
    """
    # TODO: widen (np.int16), add, np.clip to 0..255, back to np.uint8.
    pass


# Try your rites here. The grader ignores this block; `python np01_first_array.py` runs it.
if __name__ == "__main__":
    print(describe(np.zeros((2, 3), dtype=np.float32)))
''',
    dialogue={
        "intro": [
            {"speaker": "ada", "mood": "neutral",
             "text": "Sit. Before you train anything, answer me one question: what are you holding? Not the numbers. Its shape."},
            {"speaker": "ada", "mood": "neutral",
             "text": "A list is a crowd. An array is a formation: one type, one shape, and numpy can march it in step."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "MOTHER ADA trained models before the Null Event, {callsign}. When she asks why, answer the why."},
        ],
        "crash": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "A crash is the array telling you its shape didn't match your plan. Read which line, then print .shape there."}],
            [{"speaker": "ada", "mood": "neutral",
              "text": "OverflowError means a number didn't fit in its type. Widen the type before you do the arithmetic."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "Script went down before the rites ran. The COMBAT LOG names the line."}],
        ],
        "fail": [
            [{"speaker": "ada", "mood": "neutral",
              "text": "Compare the shape you returned with the shape I asked for. Most wrong answers are right numbers in the wrong formation."}],
            [{"speaker": "ada", "mood": "cold",
              "text": "float64 is not float32. Text that looks like a number is not a number. Precision is a kindness to your future self."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader builds fresh arrays every time. Code that only fits the example won't fit the next scan."}],
        ],
        "victory": [
            {"speaker": "ada", "mood": "warm",
             "text": "Shape, dtype, size. You read them before you touched the values. That is the first sutra, and most of the old world skipped it."},
            {"speaker": "ada", "mood": "neutral",
             "text": "The Core's eyes stored light as uint8. Somebody added before they clipped. Bright fire read as darkness for a year."},
            {"speaker": "cipher", "mood": "warm",
             "text": "SHAPELESS is gone, {callsign}. The slate holds its shape now. Ada's already reaching for the next page."},
        ],
    },
)


# ── grader helpers ──────────────────────────────────────────────────────────────

def _defs(ctx) -> dict:
    return {n.name: n for n in ctx.tree.body if isinstance(n, ast.FunctionDef)}


def _fn(ctx, name: str):
    obj = ctx.ns.get(name)
    if callable(obj):
        return obj
    if ctx.crashed and name in _defs(ctx):
        raise Fail(f"`{name}` is in your file, but the script crashed before Python defined it. "
                   "Fix the crash in the COMBAT LOG first.")
    raise Fail(f"No function named `{name}` found.",
               hint=f"Keep the starter's  def {name}(...):  line; spelling and underscores must match.")


def _short(text: str, limit: int = 150) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _show(value) -> str:
    if isinstance(value, np.ndarray):
        body = np.array2string(value, precision=4, threshold=12, edgeitems=2, separator=", ",
                               suppress_small=True)
        return _short(f"{' '.join(body.split())} (shape {value.shape}, {value.dtype})", 170)
    return _short(repr(value))


def _scalar(v) -> str:
    v = np.asarray(v)
    if v.dtype.kind == "b":
        return str(bool(v))
    if v.dtype.kind in "iu":
        return str(int(v))
    if v.dtype.kind == "f":
        return f"{float(v):.6g}"
    return _short(repr(v.item()))


def _crash_hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, OverflowError):
        return ("A number didn't fit in the array's dtype. Widen first, e.g. pixels.astype(np.int16), "
                "do the arithmetic, then np.clip and convert back.")
    if "could not convert string" in msg:
        return "One of the text values isn't a number as written. np.array(rows, dtype=np.float32) parses '1e-3' and '-7' fine."
    if "cannot reshape" in msg:
        return "reshape must keep the total number of elements. Use -1 for the axis numpy should work out."
    if isinstance(exc, TypeError) and "len() of unsized" in msg:
        return "A 0-d array (a single number) has no len(). Use .size to count elements."
    if isinstance(exc, (AttributeError, TypeError)) and "NoneType" in msg:
        return "Something is None: a function with no `return` gives back None."
    return "Call the function yourself at the bottom of your file with a small array and print the result."


def _call(fn, label: str, *args):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return fn(*args)
    except Fail:
        raise
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {_short(exc)}", hint=_crash_hint(exc))


def _array(got, label: str):
    if got is None:
        raise Fail(f"`{label}` returned None.",
                   hint="A function without a `return` line gives back None. Return the array you built.")
    if not isinstance(got, np.ndarray):
        raise Fail(f"`{label}` returned a {type(got).__name__}, not a numpy array.",
                   hint="Stay in numpy end to end; np.array(...) and array methods return arrays.")
    return got


def _mismatch(got, want, label: str, hint: str = "", tol: float = 1e-6) -> None:
    if want.dtype.kind in "biu" and got.dtype.kind in "biu":
        bad = got != want
    else:
        bad = ~np.isclose(got.astype(np.float64), want.astype(np.float64), rtol=tol, atol=tol)
    if bad.any():
        idx = tuple(int(i) for i in np.argwhere(bad)[0])
        raise Fail(f"`{label}` is wrong at index {idx}: got {_scalar(got[idx])}, expected {_scalar(want[idx])}.",
                   hint=hint)


# ── references ──────────────────────────────────────────────────────────────────

def _ref_features(rows, n_features):
    return np.array(rows, dtype=np.float32).reshape(-1, n_features)


def _ref_brighten(pixels, amount):
    return np.clip(pixels.astype(np.int16) + amount, 0, 255).astype(np.uint8)


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Vital signs — `describe` reads shape, ndim, size, dtype")
def _describe(ctx):
    describe = _fn(ctx, "describe")
    rng = np.random.default_rng(1101)
    cases = [
        rng.random(tuple(int(n) for n in rng.integers(2, 5, size=3))).astype(np.float32),
        rng.integers(0, 9, size=int(rng.integers(3, 9))),
        rng.random((int(rng.integers(2, 6)), int(rng.integers(2, 6)))) > 0.5,
        np.zeros((0, int(rng.integers(2, 6)))),
        np.array(7.5),
    ]
    for a in cases:
        label = f"describe(array of shape {a.shape}, {a.dtype})"
        got = _call(describe, label, a)
        if not isinstance(got, dict):
            raise Fail(f"`{label}` returned {_short(repr(got))}, not a dict.",
                       hint='Return a dict literal: {"shape": ..., "ndim": ..., "size": ..., "dtype": ...}')
        for key in ("shape", "ndim", "size", "dtype"):
            if key not in got:
                raise Fail(f"`{label}` has no {key!r} key. Keys: {sorted(map(str, got))}.",
                           hint="Exactly these four keys: 'shape', 'ndim', 'size', 'dtype'.")
        if not isinstance(got["shape"], tuple) or got["shape"] != a.shape:
            raise Fail(f"`{label}`['shape'] is {_short(repr(got['shape']))}; expected the tuple {a.shape}.",
                       hint="a.shape is already a tuple: one number per axis, () for a single number.")
        if got["ndim"] != a.ndim:
            raise Fail(f"`{label}`['ndim'] is {got['ndim']!r}; expected {a.ndim}.",
                       hint="ndim counts AXES, not elements: a.ndim, which is len(a.shape).")
        if got["size"] != a.size:
            hint = "Use a.size: it multiplies every axis together."
            if a.ndim and got["size"] == len(a):
                hint = "len(a) only counts the first axis. a.size counts every element (the product of the shape)."
            raise Fail(f"`{label}`['size'] is {got['size']!r}; expected {a.size}.", hint=hint)
        if not isinstance(got["dtype"], str):
            raise Fail(f"`{label}`['dtype'] is a {type(got['dtype']).__name__}, not a str.",
                       hint="Wrap it: str(a.dtype) gives text like 'float32'.")
        if got["dtype"] != str(a.dtype):
            raise Fail(f"`{label}`['dtype'] is {got['dtype']!r}; expected {str(a.dtype)!r}.",
                       hint="Read it from the array: str(a.dtype). Don't name a type yourself.")


@MISSION.check("Parse the slate — `as_features` gives float32 (n, d)")
def _features(ctx):
    as_features = _fn(ctx, "as_features")
    rng = np.random.default_rng(1102)
    n, d = int(rng.integers(5, 9)), int(rng.integers(3, 6))
    styles = ("{:.3f}", "{:.1f}", "{:.0f}", "{:.2e}")
    rows = [[styles[int(rng.integers(0, 4))].format(float(v)) for v in rng.normal(0, 40, d)] for _ in range(n)]
    for args in ((rows, d), (rows[:1], d), ([], d + 1)):
        rows_in, k = args
        label = f"as_features({_short(repr(rows_in), 60)}, {k})"
        got = _array(_call(as_features, label, [list(r) for r in rows_in], k), label)
        want = _ref_features(rows_in, k)
        if got.dtype.kind == "U" or got.dtype.kind == "S":
            raise Fail(f"`{label}` returned an array of TEXT ({got.dtype}).",
                       hint="np.array(rows) keeps strings as strings. Ask for numbers: dtype=np.float32.")
        if got.shape != want.shape:
            hint = "Keep one row per input row and n_features columns."
            if len(rows_in) == 0:
                hint = ("np.array([]) has shape (0,): the columns are lost. "
                        "reshape(-1, n_features) gives back (0, n_features).")
            raise Fail(f"`{label}` returned shape {got.shape}; expected {want.shape}.", hint=hint)
        if got.dtype != np.float32:
            raise Fail(f"`{label}` returned dtype {got.dtype}; expected float32.",
                       hint="numpy's default float is float64. Models train in float32: pass dtype=np.float32.")
        _mismatch(got, want, label, hint="Convert every text value in place, in the same row and column.")


@MISSION.check("Flatten the scans — `flatten_images` keeps the batch axis")
def _flatten(ctx):
    flatten_images = _fn(ctx, "flatten_images")
    rng = np.random.default_rng(1103)
    n, h, w = (int(v) for v in rng.integers(3, 7, size=3))
    cases = [
        rng.integers(0, 256, size=(n, h, w)).astype(np.uint8),
        rng.integers(0, 256, size=(1, h + 1, w)).astype(np.uint8),
        rng.random((n, h, w, 3)).astype(np.float32),
    ]
    for images in cases:
        label = f"flatten_images(batch of shape {images.shape})"
        original = images.copy()
        got = _array(_call(flatten_images, label, images), label)
        want = original.reshape(len(original), -1)
        if got.shape != want.shape:
            hint = "Keep axis 0 (one row per image): reshape(len(images), -1)."
            if got.ndim == 1:
                hint = ".flatten() / reshape(-1) flattens EVERYTHING, batch axis included. Keep axis 0."
            raise Fail(f"`{label}` returned shape {got.shape}; expected {want.shape}.", hint=hint)
        if got.dtype != want.dtype:
            raise Fail(f"`{label}` changed the dtype from {want.dtype} to {got.dtype}.",
                       hint="Flattening only rearranges; it shouldn't convert anything.")
        if not np.array_equal(got, want):
            hint = "Read each image row by row: plain reshape does exactly that."
            if images.ndim == 3 and np.array_equal(got, original.transpose(0, 2, 1).reshape(len(original), -1)):
                hint = "You read the image column by column (a transpose). Plain reshape reads row by row."
            raise Fail(f"`{label}` has the right shape but pixels in the wrong order.", hint=hint)


@MISSION.check("CORRUPTED CODE — `to_unit` scales pixels into [0, 1]")
def _to_unit(ctx):
    to_unit = _fn(ctx, "to_unit")
    rng = np.random.default_rng(1104)
    pixels = rng.integers(0, 256, size=(int(rng.integers(2, 5)), 5, 4)).astype(np.uint8)
    pixels.flat[0], pixels.flat[1] = 0, 255
    label = f"to_unit(uint8 pixels of shape {pixels.shape})"
    got = _array(_call(to_unit, label, pixels.copy()), label)
    want = pixels.astype(np.float32) / 255
    if got.shape != want.shape:
        raise Fail(f"`{label}` returned shape {got.shape}; expected {want.shape}.",
                   hint="Scaling works element by element; the shape should not change.")
    if got.dtype.kind in "iu":
        raise Fail(f"`{label}` still returns {got.dtype}: 51/255 = 0.2 becomes 0 when cast to an integer, "
                   "so almost every pixel turns black.",
                   hint="Integers can't hold 0.2. The result must be float32, not uint8.")
    if got.dtype != np.float32:
        raise Fail(f"`{label}` returned dtype {got.dtype}; expected float32.",
                   hint="pixels / 255 gives float64. Convert with .astype(np.float32) (before or after dividing).")
    _mismatch(got, want, label, hint="Every pixel is divided by 255: 0 stays 0.0, 255 becomes 1.0.")


@MISSION.check("Raise the light — `brighten` clips instead of wrapping")
def _brighten(ctx):
    brighten = _fn(ctx, "brighten")
    rng = np.random.default_rng(1105)
    shape = (int(rng.integers(3, 6)), int(rng.integers(3, 6)))
    pixels = rng.integers(0, 256, size=shape).astype(np.uint8)
    pixels.flat[:4] = [254, 250, 1, 6]
    for amount in (int(rng.integers(30, 90)), -int(rng.integers(30, 90)), 0):
        label = f"brighten(uint8 pixels of shape {shape}, {amount})"
        original = pixels.copy()
        got = _array(_call(brighten, label, pixels, amount), label)
        if not np.array_equal(pixels, original):
            raise Fail(f"`{label}` changed the caller's `pixels` array.",
                       hint="Build a new array (astype already makes a copy); don't write back into `pixels`.")
        want = _ref_brighten(original, amount)
        if got.shape != want.shape:
            raise Fail(f"`{label}` returned shape {got.shape}; expected {want.shape}.")
        if got.dtype != np.uint8:
            raise Fail(f"`{label}` returned dtype {got.dtype}; an image must come back as uint8.",
                       hint="After clipping to 0..255, convert back with .astype(np.uint8).")
        wrapped = (original.astype(np.int64) + amount) % 256
        if amount and np.array_equal(got, wrapped):
            i = int(np.argmax(wrapped != want.astype(np.int64)))
            raise Fail(f"`{label}` wrapped around instead of clipping: {int(original.flat[i])} {amount:+d} came out "
                       f"as {int(wrapped.flat[i])}, not {int(want.flat[i])}.",
                       hint="uint8 wraps past its edges. Widen to np.int16 BEFORE adding, then np.clip, then narrow.")
        _mismatch(got, want, label, hint="Clamp to the range 0..255: np.clip(widened, 0, 255).")
