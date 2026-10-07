"""Mission markdown → safe, highlighted HTML for the web client.

Briefings, "why it matters" notes and field manuals are authored in markdown
inside levels/*.py. This module turns them into HTML fragments the client drops
into a `.rich` container:

* CommonMark via markdown-it-py with raw HTML **disabled**, so any `<tag>` in a
  level's text is escaped instead of executed.
* Fenced code is emitted as ``<pre class="code"><code class="language-x">…</code></pre>``.
  Languages Pygments knows (python first and foremost) get token spans with the
  ``tk-`` class prefix (``tk-k`` keyword, ``tk-s2`` string, ``tk-c1`` comment, …),
  which css/app.css colours.
* Links open in a new tab without leaking the opener or referrer.

Level text is static, so results are memoised: each fragment is rendered once
per process no matter how many times the client asks for a mission.
"""
from __future__ import annotations

from functools import lru_cache
from html import escape

from markdown_it import MarkdownIt
from pygments import highlight as _pygmentize
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

__all__ = ["render_markdown", "highlight_code"]

_FORMATTER = HtmlFormatter(nowrap=True, classprefix="tk-")
_ALIASES = {"py": "python", "python3": "python", "py3": "python", "": ""}


def _language(name: str) -> str:
    name = name.strip().lower()
    name = _ALIASES.get(name, name)
    return "".join(ch for ch in name if ch.isalnum() or ch in "+-_")


@lru_cache(maxsize=512)
def highlight_code(code: str, language: str = "python") -> str:
    """One code block as `<pre class="code"><code …>` with `tk-` token spans (escaped if unknown)."""
    lang = _language(language)
    body = None
    if lang:
        try:
            lexer = get_lexer_by_name(lang, stripnl=False, ensurenl=False)
        except ClassNotFound:
            lexer = None
        if lexer is not None:
            body = _pygmentize(code, lexer, _FORMATTER)
    if body is None:
        body = escape(code, quote=False)
    body = body.rstrip("\n")
    cls = f' class="language-{lang}"' if lang else ""
    return f'<pre class="code"><code{cls}>{body}</code></pre>'


def _fence_highlight(content: str, lang: str, _attrs: str) -> str:
    return highlight_code(content, lang)


def _build() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "highlight": _fence_highlight})
    # Indented code blocks (no language) get the same container as fences.
    md.add_render_rule("code_block", lambda self, tokens, idx, options, env:
                       highlight_code(tokens[idx].content, "") + "\n")
    default_link_open = md.renderer.rules.get("link_open")

    def link_open(self, tokens, idx, options, env):
        tokens[idx].attrSet("target", "_blank")
        tokens[idx].attrSet("rel", "noopener noreferrer")
        if default_link_open:
            return default_link_open(tokens, idx, options, env)
        return self.renderToken(tokens, idx, options, env)

    md.add_render_rule("link_open", link_open)
    return md


_MD = _build()


@lru_cache(maxsize=256)
def render_markdown(text: str) -> str:
    """Render one markdown document to an HTML fragment. Raw HTML in `text` is escaped."""
    return _MD.render(text or "").strip()
