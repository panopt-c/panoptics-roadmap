"""Translates Python errors into plain English.

Reading tracebacks is the #1 skill that separates people who get stuck from
people who ship. Every decoded error still shows the raw Python message too,
so you learn to read the real thing.
"""
from __future__ import annotations

import re

DECODER = [
    ("SyntaxError", r"unterminated string",
     "A quote was opened but never closed. Every \" needs a partner \"."),
    ("SyntaxError", r"was never closed",
     "A bracket ( [ { was opened but never closed."),
    ("SyntaxError", r"invalid syntax",
     "Python couldn't understand this line. Check for missing quotes, a stray character, "
     "or a missing = sign."),
    ("SyntaxError", r"",
     "Python couldn't read this line, so none of your file ran."),
    ("IndentationError", r"",
     "A line starts with unexpected spaces. Outside of blocks (if/for/def), lines start at "
     "the left edge."),
    ("NameError", r"name '(true|false|none)' is not defined",
     "Python is case-sensitive: write True, False and None with a capital letter."),
    ("NameError", r"",
     "Python doesn't know that name. Either it's misspelled, used before it was created, "
     "or it's text that needs quotes."),
    ("TypeError", r"can only concatenate str|unsupported operand type.*'str'|must be str, not",
     "You mixed text and numbers in math. Convert first: int(\"12\") -> 12, str(12) -> \"12\"."),
    ("TypeError", r"not callable",
     "You put ( ) after something that isn't a function — often a variable named like a function."),
    ("TypeError", r"",
     "An operation got a value of the wrong type."),
    ("ValueError", r"invalid literal for int",
     "int() can only convert text that looks like a whole number, e.g. int(\"42\")."),
    ("ValueError", r"", "The type was right but the value wasn't usable."),
    ("ZeroDivisionError", r"", "You divided by zero."),
    ("IndexError", r"", "You asked for a position that doesn't exist. Lists start at 0, and the last "
                         "position is len(list) - 1."),
    ("KeyError", r"", "That key isn't in the dictionary. Check spelling, or use .get(key)."),
    ("AttributeError", r"", "That object doesn't have the method or property you asked for."),
    ("ModuleNotFoundError", r"", "That library isn't installed. Try: pip install <name>."),
    ("EOFError", r"", "Your code called input(). Missions are graded automatically, so nobody can "
                       "type an answer — use variables instead."),
    ("RecursionError", r"", "A function kept calling itself forever."),
    ("Timeout", r"", "Your code never finished — probably a loop that never ends."),
]


def decode(error: dict | None) -> str:
    if not error:
        return ""
    etype, message = error.get("type", ""), error.get("message", "")
    for name, pattern, explanation in DECODER:
        if etype == name and re.search(pattern, message, re.IGNORECASE):
            return explanation
    return "Read the last line of the traceback — it names the problem."
