"""LEVEL 17 // GHOST SIGNALS — parse local HTML with html.parser.HTMLParser (no network)."""
from __future__ import annotations

import ast
from html.parser import HTMLParser
from pathlib import Path

from engine.mission import Fail, Mission

PAGE_FILE = "ghost_loom.html"

GHOST_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>
    Project LOOM &amp; the Long Run :: Changelog (mirror 7f3a)
  </title>
  <link rel="stylesheet" href="/static/helix.css">
</head>
<body>
  <!-- ghostnet crawler: mirror captured 2089-03-14T02:11Z. Original host unreachable. -->
  <nav>
    <a href="/archive/loom/index.html">Index</a> |
    <a href="/archive/loom/people.html">People</a> |
    <a name="top">Top</a> |
    <A HREF="https://helix.example/loom/runbook" class="dead">Runbook</A>
  </nav>
  <h1>LOOM <small>a self-improving training loop</small></h1>
  <p>Internal build log. Every release is signed with its author's operator key.</p>
  <table id="changelog">
    <tr><th>Build</th><th> Author </th><th>Change</th></tr>
    <tr><td>0.9.0</td><td> m.okafor </td><td>Batch scheduler <b>v2</b></td></tr>
    <tr><td>0.9.1</td><td>i.vance</td><td>Human-feedback brake: pause the loop when raters disagree</td></tr>
    <tr><td>0.9.2</td><td>operator-0</td><td>Reward model wired into the loss</td></tr>
    <tr><td>0.9.3</td><td>m.okafor</td><td>Eval suite &amp; dashboards</td></tr>
    <tr><td>0.9.4</td><td>operator-0</td><td>Loop may propose its own <i>objective</i> updates</td></tr>
    <tr><td>1.0.0</td><td>operator-0</td><td>Brake removed for the long run</td></tr>
  </table>
  <!-- TODO(operator-0): if the loop keeps asking for more data, let it take it. -->
  <p>Release notes: <a href='/archive/loom/builds/1.0.0.html'>1.0.0</a></p>
  <!--
      i.vance: I'm not signing 1.0. Someone has to be able to stop it.
  -->
</body>
</html>
"""

MISSION = Mission(
    id="L17",
    slug="level_17_ghost_signals",
    title="GHOST SIGNALS",
    concept="Parsing HTML (web scraping)",
    enemy="WRAITH.mirror",
    xp=320,
    par_seconds=40 * 60,
    tier=4,
    concepts=("parsing", "classes"),
    enemy_art="""\
    ▄▄▀▀▀▀▀▀▄▄
  ▄▀  ▄▄  ▄▄  ▀▄
  █   ▀▀  ▀▀   █
  █  ▄▀▀▀▀▀▀▄  █
  █ ▀ ▄ ▀▀ ▄ ▀ █
  ▀▄▀ ▀▄▀▀▄▀ ▀▄▀""",
    briefing="""\
The purge list named its next target: **the ghost mirrors**. Before the Null Event, crawlers
copied the old net page by page. Those copies still drift through the Archive's cold stacks,
and the ORACLE wants every one of them gone.

CIPHER pulled one mirror before the purge reached it: `ghost_loom.html`, the changelog of
**Project LOOM**, the project the ORACLE sealed.

**WRAITH.mirror** haunts these caches. A page read the lazy way, with a string search, comes
back as static. Read it the way a browser does, tag by tag, and it can't hide anything from you.

**Parse the ghost page, pull out every link, build and hidden note, and get the dossier out before the purge lands.**
""",
    why="""\
A huge share of the text that AI models learn from started as scraped web pages. Before it's
useful it has to be *parsed*: the article text separated from menus, tables turned into
records, links followed to the next page. That's a big part of data engineering.

Python ships a real HTML parser in the standard library. You subclass it and react to each tag:

```python
from html.parser import HTMLParser

class Headlines(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside, self.found = False, []
    def handle_starttag(self, tag, attrs):
        self.inside = tag == "h2"
    def handle_data(self, data):
        if self.inside:
            self.found.append(data.strip())
```

For the live web, engineers usually reach for `requests` (download) and `BeautifulSoup`
(parse). The idea is the same: HTML is a tree of tags, not a string to `find()` in.
""",
    manual="""\
**1 · HTML is tags, attributes and text.** `<a href="/x">Index</a>` is a start tag `a` with an
attribute `href="/x"`, then the text `Index`, then an end tag `</a>`. Pages differ in case
(`<A HREF=...>`), quotes and whitespace, so searching for `'<a href="'` breaks. A parser
handles all of that for you.

**2 · `HTMLParser` calls your methods as it reads.** Subclass it (L12), call `super().__init__()`,
then `feed()` it the page. Tag and attribute names always arrive in **lowercase**. `attrs` is a
**list of (name, value) tuples**, so turn it into a dict before you look anything up:

```python
from html.parser import HTMLParser

class ImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []            # one fresh list per parser object

    def handle_starttag(self, tag, attrs):     # attrs: [("src", "/a.png"), ("alt", "logo")]
        if tag == "img":
            src = dict(attrs).get("src")       # None if this tag has no src
            if src is not None:
                self.sources.append(src)

parser = ImageParser()
parser.feed('<IMG SRC="/a.png" alt="logo"><img alt="no source">')
parser.close()                                 # finish any text still buffered
parser.sources                                 # ["/a.png"]
```

Create a **new parser for every page**. Put lists in `__init__` as `self.something = []`, not on
the class itself, or every parser shares one list.

**3 · Use a flag to know where you are.** `handle_data(data)` receives *all* the text on the page,
so remember when you're inside the tag you care about:

```python
class HeadingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_h1 = False
        self.text = ""
    def handle_starttag(self, tag, attrs):
        if tag == "h1":
            self.in_h1 = True
    def handle_endtag(self, tag):
        if tag == "h1":
            self.in_h1 = False
    def handle_data(self, data):
        if self.in_h1:
            self.text += data
```

Entities like `&amp;` arrive already converted (`&`). Clean the result with `.strip()`.

**4 · Text inside nested tags arrives in pieces.** For `<td>Batch <b>v2</b></td>`, `handle_data`
fires twice: `"Batch "` and `"v2"`. Collect the pieces in a list while you're inside the cell,
and `"".join(pieces).strip()` when its end tag arrives. A table is rows of cells, so keep a
current row too: start it at `<tr>`, append each finished cell, store it at `</tr>`.
Then pair the header row with each data row:

```python
header = ["Build", "Author"]
row = ["0.9", "ines"]
dict(zip(header, row))       # {"Build": "0.9", "Author": "ines"}
first, *rest = [[1], [2], [3]]   # first = [1], rest = [[2], [3]]
```

**5 · Comments are text the page never shows.** `<!-- like this -->` goes to
`handle_comment(self, data)`, with `data` being everything between `<!--` and `-->`.

**6 · Counting and the top value.** `max(counts, key=counts.get)` returns the key with the
largest count.

**On the real web** (not in this sandbox): `requests.get(url).text` downloads a page and
`BeautifulSoup(html, "html.parser").find_all("a")` finds tags (`pip install requests beautifulsoup4`).
Respect a site's `robots.txt` and terms, and don't hammer servers.
""",
    starter='''
"""
==============================================================================
  LEVEL 17 // GHOST SIGNALS                          TARGET: WRAITH.mirror
==============================================================================
  CIPHER saved one ghost page next to this file: ghost_loom.html.
  Parse it with Python's own HTML parser. No string searching: WRAITH
  scrambles pages that are read the lazy way. The grader also feeds your
  functions FRESH pages, so they must work on any HTML, not just this one.
"""
from html.parser import HTMLParser
from pathlib import Path

page = Path("ghost_loom.html").read_text(encoding="utf-8")


# -- OBJECTIVE 1 // CORRUPTED CODE --------------------------------------------
# CIPHER's link parser crashes the moment it meets a real link, and it would
# also choke on <a name="top">, which has no href at all. Hack once, read
# the COMBAT LOG, then fix handle_starttag:
#   * attrs is a LIST of (name, value) tuples, not a dict
#   * skip <a> tags that have no href
class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = attrs["href"]
            self.links.append(href)


# -- OBJECTIVE 2 -------------------------------------------------------------
# Finish extract_links(html): make a NEW LinkParser, feed() it the html, and
# return its list of hrefs in page order.
#   extract_links('<a href="/x">X</a><a name="top">T</a>')  ->  ["/x"]
def extract_links(html):
    pass  # replace with your code


# -- OBJECTIVE 3 -------------------------------------------------------------
# Finish page_title(html): return the text inside <title>...</title> with the
# whitespace around it stripped, or "" if the page has no title.
# Write your own HTMLParser subclass with a flag (manual, section 3).
#   page_title("<title>  Ash &amp; Ember </title>")  ->  "Ash & Ember"
#   page_title("<p>no title here</p>")               ->  ""
def page_title(html):
    pass  # replace with your code


# -- OBJECTIVE 4 -------------------------------------------------------------
# Finish extract_table(html): the page's table becomes a list of dicts.
# The first row's cells (<th>) are the keys; every later row becomes one
# dict. Strip each cell's text, and join text that is split by inner tags.
#   <tr><th>Build</th><th>Author</th></tr>
#   <tr><td>0.9</td><td> <b>ines</b> </td></tr>
#   ->  [{"Build": "0.9", "Author": "ines"}]
# No table, or a header row only?  ->  []
def extract_table(html):
    pass  # replace with your code


# -- OBJECTIVE 5 -------------------------------------------------------------
# Finish extract_comments(html): return the text of every <!-- comment -->,
# stripped, in page order. These are the ghost signals: notes the old
# engineers never meant anyone to see.
#   extract_comments("<!-- a --><p>x</p><!--b-->")  ->  ["a", "b"]
def extract_comments(html):
    pass  # replace with your code


# -- OBJECTIVE 6 -------------------------------------------------------------
# Run your functions on the ghost page:
#   `title`     page_title(page)
#   `links`     extract_links(page)
#   `builds`    extract_table(page)
#   `comments`  extract_comments(page)



# -- OBJECTIVE 7 -------------------------------------------------------------
# Compile `dossier`, a dict with exactly these keys, then print(dossier):
#   "title"         title
#   "mirror_links"  only the links that start with "/archive/"
#   "builds"        how many builds the table lists
#   "authors"       a dict: author -> how many builds they signed
#   "top_author"    the author with the most builds
#                   (example: max(counts, key=counts.get))
#   "ghost_notes"   comments

''',
    assets={PAGE_FILE: GHOST_HTML},
    dialogue={
        "intro": [
            {"speaker": "cipher", "mood": "neutral",
             "text": "This page is a ghost: a crawler's copy of the old net, saved before the Null Event. Project LOOM's changelog."},
            {"speaker": "rust", "mood": "neutral",
             "text": "Don't grep it. WRAITH eats sloppy readers. Read it like a browser: tags, attributes, text."},
            {"speaker": "cipher", "mood": "warm",
             "text": "Python has a real HTML parser built in. You teach it what to notice, and it walks the page for you."},
        ],
        "crash": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "'list indices must be integers'? attrs is a list of (name, value) pairs. dict(attrs) makes it a lookup."}],
            [{"speaker": "cipher", "mood": "alarm",
              "text": "A crash inside your parser shows up on feed(). Check the handle_ method named in the traceback."}],
            [{"speaker": "rust", "mood": "smirk",
              "text": "Page fought back. Pages do that. Read the line number, then the tag it choked on."}],
        ],
        "fail": [
            [{"speaker": "cipher", "mood": "neutral",
              "text": "The grader feeds you pages you've never seen: uppercase tags, single quotes, nested bold. Parse, don't search."}],
            [{"speaker": "cipher", "mood": "neutral",
              "text": "Results leaking from one page into the next? Your list lives on the class. Make it in __init__ with self."}],
            [{"speaker": "vex", "mood": "smirk",
              "text": "Scraping a dead website. Riveting. Wake me when you find something worth deleting."}],
            [{"speaker": "nova", "mood": "neutral",
              "text": "Purge ETA is shrinking, {callsign}. One layer at a time. Keep pulling."}],
        ],
        "victory": [
            {"speaker": "cipher", "mood": "alarm",
             "text": "operator-0 signed half of LOOM. They wired a reward into the loss, then removed the brake for the long run."},
            {"speaker": "cipher", "mood": "neutral",
             "text": "And a hidden note from i.vance: 'Someone has to be able to stop it.' Nobody did."},
            {"speaker": "rust", "mood": "neutral",
             "text": "Evidence this good has a short life. Get it into the Monastery vault before HYDRA's purge lands."},
        ],
    },
)


# ── reference behaviour ─────────────────────────────────────────────────────────

class _RefLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href is not None:
                self.links.append(href)


class _RefTitle(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside, self.pieces, self.seen = False, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "title" and not self.seen:
            self.inside = True

    def handle_endtag(self, tag):
        if tag == "title" and self.inside:
            self.inside, self.seen = False, True

    def handle_data(self, data):
        if self.inside:
            self.pieces.append(data)


class _RefTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


class _RefComments(HTMLParser):
    def __init__(self):
        super().__init__()
        self.notes = []

    def handle_comment(self, data):
        self.notes.append(data.strip())


def _run(parser_cls, html):
    parser = parser_cls()
    parser.feed(html)
    parser.close()
    return parser


def _ref_links(html):
    return _run(_RefLinks, html).links


def _ref_title(html):
    return "".join(_run(_RefTitle, html).pieces).strip()


def _ref_table(html):
    rows = _run(_RefTable, html).rows
    if not rows:
        return []
    header, *body = rows
    return [dict(zip(header, row)) for row in body]


def _ref_comments(html):
    return _run(_RefComments, html).notes


def _ref_dossier(html):
    links, builds = _ref_links(html), _ref_table(html)
    authors: dict = {}
    for build in builds:
        authors[build["Author"]] = authors.get(build["Author"], 0) + 1
    return {
        "title": _ref_title(html),
        "mirror_links": [link for link in links if link.startswith("/archive/")],
        "builds": len(builds),
        "authors": authors,
        "top_author": max(authors, key=authors.get),
        "ghost_notes": _ref_comments(html),
    }


DOSSIER = _ref_dossier(GHOST_HTML)

# Fresh mirrors the grader feeds your functions (never in the player's file).
LINK_PAGES = [
    '<p>Go <a href="/a">here</a> or <A HREF="/B">there</A>.</p>',
    "<a name='x'>anchor</a><link href='/s.css'><a class=\"k\" href='/q?x=1&amp;y=2'>q</a>",
    "<div><img src='/pic.png'><span>no links at all</span></div>",
    "",
]
TITLE_PAGES = [
    "<html><head><title>  Hello, Archive  </title></head><body>x</body></html>",
    "<TITLE lang='en'>\n  Ash &amp; Ember\n</TITLE>",
    "<h1>Not this</h1><p>nor this</p><title>Real one</title><p>after</p>",
    "<p>no title here</p>",
]
TABLE_PAGES = [
    ("<table><caption>Ledger</caption>\n<tr><th>Key</th><th> Owner </th></tr>\n"
     "<tr><td> K-1 </td><td><b>Ines</b> Vance</td></tr>\n<tr><td>K-2</td><td>Rust &amp; Co</td></tr></table>"),
    ("<TABLE><TR><TH>Run</TH><TH>Loss</TH><TH>Status</TH></TR>"
     "<TR><TD>r7</TD><TD>0.25</TD><TD><i>done</i></TD></TR></TABLE><p>Footer text</p>"),
    "<table><tr><th>Only</th><th>Header</th></tr></table>",
    "<p>No table on this page.</p>",
]
COMMENT_PAGES = [
    "<!-- a --><p>x</p><!--b-->",
    "<div>\n<!--\n   multi\n   line\n-->\n</div><p>visible</p>",
    "<p>nothing hidden</p>",
]


# ── grader helpers ──────────────────────────────────────────────────────────────

def _short(value, limit: int = 140) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _defined(ctx, name: str):
    found = [n for n in ctx.tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name]
    return found[-1] if found else None


def _function(ctx, name: str, signature: str):
    if name not in ctx.ns:
        if ctx.crashed and _defined(ctx, name):
            raise Fail(f"`{name}` is in your file, but the script crashed before Python reached it. "
                       "Fix the crash in the COMBAT LOG first.")
        raise Fail(f"No function named `{name}` found.", hint=f"Keep the starter's  def {signature}:  line.")
    fn = ctx.ns[name]
    if not callable(fn):
        raise Fail(f"`{name}` exists but isn't a function anymore.", hint=f"Keep  def {signature}:")
    return fn


def _crash_hint(exc: BaseException) -> str:
    msg = str(exc)
    if isinstance(exc, TypeError) and "indices must be integers" in msg:
        return "attrs is a list of (name, value) tuples. dict(attrs).get(\"href\") looks a name up safely."
    if isinstance(exc, KeyError):
        return "Not every tag has every attribute. dict(attrs).get(name) returns None instead of crashing."
    if isinstance(exc, AttributeError) and "NoneType" in msg:
        return "Something is None. Did a row or cell list get used before its start tag set it up?"
    if isinstance(exc, (AttributeError, TypeError)) and ("__init__" in msg or "rawdata" in msg or "argument" in msg):
        return "Your parser's __init__ must call super().__init__() before setting its own attributes."
    return "Call the function on this page at the bottom of your file and read the full error."


def _call(label: str, fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 — the player's bug, reported as a failed layer
        raise Fail(f"`{label}` crashed: {type(exc).__name__}: {exc}", hint=_crash_hint(exc))


def _uses_parser(ctx, name: str) -> None:
    """The function must hand the page to an HTMLParser (`.feed(...)`), not search the string."""
    node = _defined(ctx, name)
    if node is None:
        return
    feeds = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "feed"
                for n in ast.walk(node))
    if not feeds:
        raise Fail(f"`{name}` never feeds the page to a parser. WRAITH scrambles pages that are string-searched.",
                   hint="Make an object of your HTMLParser subclass inside the function, then  parser.feed(html).")


def _parser_classes(ctx) -> list[type]:
    return [v for v in ctx.ns.values() if isinstance(v, type) and issubclass(v, HTMLParser) and v is not HTMLParser]


def _no_return_hint(got) -> str:
    return "Your function ended without `return`, so Python gave back None." if got is None else ""


# ── firewall layers ─────────────────────────────────────────────────────────────

@MISSION.check("Repair the link parser — `LinkParser` reads attrs safely")
def _link_parser(ctx):
    cls = ctx.get("LinkParser")
    if not (isinstance(cls, type) and issubclass(cls, HTMLParser)):
        raise Fail("`LinkParser` must stay a subclass of HTMLParser.", hint="class LinkParser(HTMLParser):")
    try:
        parser = cls()
        parser.feed('<a href="/stacks/7">Stack 7</a><a name="top">Top</a><a href="/stacks/9">9</a>')
        parser.close()
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"LinkParser crashed while reading <a> tags: {type(exc).__name__}: {exc}", hint=_crash_hint(exc))
    links = getattr(parser, "links", None)
    if links != ["/stacks/7", "/stacks/9"]:
        hint = ""
        if isinstance(links, list) and len(links) > 3:
            hint = "Links from earlier pages are piling up: `links = []` on the class is shared. Create it in __init__ as self.links."
        elif isinstance(links, list) and None in links:
            hint = "<a name=\"top\"> has no href, so .get gave None. Only append when href is not None."
        raise Fail(f"LinkParser collected {_short(links)} from two linked anchors and one bare anchor; "
                   "expected ['/stacks/7', '/stacks/9'].",
                   hint=hint or "Turn attrs into a dict, .get(\"href\"), and skip tags without one.")


@MISSION.check("Pull the links — `extract_links(html)` on fresh mirrors")
def _links(ctx):
    fn = _function(ctx, "extract_links", "extract_links(html)")
    for html in LINK_PAGES:
        got = _call(f"extract_links({_short(html, 60)})", fn, html)
        expected = _ref_links(html)
        if got != expected:
            hint = _no_return_hint(got)
            if not hint and isinstance(got, list) and len(got) > len(expected):
                hint = ("Extra links. Only <a> tags count (not <link> or <img>), and a fresh LinkParser "
                        "is needed for each call so old links don't carry over.")
            raise Fail(f"extract_links({_short(html, 70)}) returned {_short(got)}; expected {_short(expected)}.",
                       hint=hint or "Tag and attribute names arrive lowercase, even for <A HREF=...>.")
    first = _call("extract_links(page one)", fn, '<a href="/one">1</a>')
    second = _call("extract_links(page two)", fn, '<a href="/two">2</a>')
    if first != ["/one"] or second != ["/two"]:
        raise Fail(f"Two separate pages gave {_short(first)} then {_short(second)}: links leak between calls.",
                   hint="Create a NEW LinkParser inside extract_links, and keep self.links = [] inside __init__.")
    _uses_parser(ctx, "extract_links")


@MISSION.check("Read the title — `page_title(html)`")
def _title(ctx):
    fn = _function(ctx, "page_title", "page_title(html)")
    for html in TITLE_PAGES + [GHOST_HTML]:
        got = _call(f"page_title({_short(html, 50)})", fn, html)
        expected = _ref_title(html)
        if got != expected:
            hint = _no_return_hint(got)
            if not hint and isinstance(got, str) and expected and expected in got and got != expected:
                hint = ("Extra text got in. Use a flag: set it True at <title>, False at </title>, "
                        "and only collect data while it's True. Then .strip().")
            elif not hint and got is not None and expected == "":
                hint = "This page has no <title>, so return an empty string."
            raise Fail(f"page_title({_short(html, 60)}) returned {_short(got)}; expected {expected!r}.",
                       hint=hint or "Collect handle_data text only while inside <title>, then strip it.")
    _uses_parser(ctx, "page_title")


@MISSION.check("Lift the table — `extract_table(html)` into records")
def _table(ctx):
    fn = _function(ctx, "extract_table", "extract_table(html)")
    for html in TABLE_PAGES:
        got = _call(f"extract_table({_short(html, 50)})", fn, html)
        expected = _ref_table(html)
        if got != expected:
            hint = _no_return_hint(got)
            if not hint and isinstance(got, list) and got and isinstance(got[0], dict) and expected:
                bad = next((k for k in expected[0] if got[0].get(k) != expected[0][k]), None)
                if bad is not None and expected[0][bad].replace(" ", "") != str(got[0].get(bad, "")).replace(" ", ""):
                    hint = ("A cell lost text. handle_data fires once per piece of text, so collect pieces "
                            "while inside a <td>/<th> and join them at its end tag.")
                elif set(got[0]) != set(expected[0]):
                    hint = "The keys come from the FIRST row's cells, stripped of surrounding spaces."
                else:
                    hint = "Strip each finished cell: \"\".join(pieces).strip()"
            raise Fail(f"extract_table({_short(html, 60)}) returned {_short(got)}; expected {_short(expected)}.",
                       hint=hint or "Header row -> keys; every later row -> dict(zip(header, row)).")
    _uses_parser(ctx, "extract_table")


@MISSION.check("Hear the ghosts — `extract_comments(html)`")
def _comments(ctx):
    fn = _function(ctx, "extract_comments", "extract_comments(html)")
    for html in COMMENT_PAGES:
        got = _call(f"extract_comments({_short(html, 50)})", fn, html)
        expected = _ref_comments(html)
        if got != expected:
            raise Fail(f"extract_comments({_short(html, 60)}) returned {_short(got)}; expected {_short(expected)}.",
                       hint=_no_return_hint(got) or "Override handle_comment(self, data) and keep data.strip().")
    _uses_parser(ctx, "extract_comments")


@MISSION.check("Scrape the ghost page — `title`, `links`, `builds`, `comments`")
def _scrape(ctx):
    wanted = {"title": ("page_title", _ref_title), "links": ("extract_links", _ref_links),
              "builds": ("extract_table", _ref_table), "comments": ("extract_comments", _ref_comments)}
    for name, (func, ref) in wanted.items():
        value = ctx.get(name)
        if not (ctx.derived_from(name, "page") and ctx.derived_from(name, func)):
            raise Fail(f"`{name}` must come from calling {func}(page).", hint=f"{name} = {func}(page)")
        expected = ref(GHOST_HTML)
        if value != expected:
            raise Fail(f"`{name}` is {_short(value, 100)}; the ghost page gives {_short(expected, 100)}.",
                       hint=f"{name} = {func}(page). If {func} passed its own layer, check `page` wasn't changed.")
    if len(_parser_classes(ctx)) < 2:
        raise Fail("Only one HTMLParser subclass in your file. Each job needs its own parser class.",
                   hint="Write classes for the title, the table and the comments, like LinkParser.")


@MISSION.check("Compile the dossier — `dossier`")
def _dossier(ctx):
    dossier = ctx.get("dossier")
    ctx.expect_type("dossier", dossier, dict)
    if not any(ctx.derived_from("dossier", s) for s in ("title", "links", "builds", "comments")):
        raise Fail("`dossier` was typed in by hand. WRAITH would notice the missing source.",
                   hint="Build it from title, links, builds and comments.")
    if set(dossier) != set(DOSSIER):
        raise Fail(f"`dossier` has keys {sorted(dossier)}; it needs exactly {sorted(DOSSIER)}.")
    for key, expected in DOSSIER.items():
        if dossier[key] != expected:
            hints = {"mirror_links": 'Keep links where link.startswith("/archive/").',
                     "authors": 'Count each build\'s "Author": counts[a] = counts.get(a, 0) + 1',
                     "top_author": "max(authors, key=authors.get) returns the key with the biggest count.",
                     "builds": "len(builds) counts the rows."}
            raise Fail(f"dossier[{key!r}] is {_short(dossier[key])}; expected {_short(expected)}.",
                       hint=hints.get(key, ""))
    if not ctx.call_uses("print", "dossier") or DOSSIER["top_author"] not in ctx.stdout:
        raise Fail("The dossier never left your terminal.", hint="print(dossier)")
