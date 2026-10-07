/**
 * CodeEditor — the in-game Python editor (docs/ARCHITECTURE.md §4.4).
 *
 * The player spends most of the game here, so it is built like a small IDE, not a styled
 * <textarea>.
 *
 * Layering
 *   One native <textarea> does all the editing (caret, selection, IME, clipboard, native
 *   undo/redo) with transparent glyphs. Under it sits a highlighted copy of the text, one
 *   <div> per line, sharing every font metric, padding, tab-size and `white-space: pre`, so
 *   each glyph lands exactly under the caret.
 *
 *     .ce-scroller          the ONLY scroll container (native, compositor-threaded)
 *       .ce-content         width: max-content — grows with the longest line
 *         .ce-gutter        position: sticky; left: 0 — line numbers + error markers
 *         .ce-area          position: relative
 *           .ce-under       current-line band, error glow, bracket-match boxes
 *           .ce-code        highlighted lines (in flow: they size the area)
 *           textarea        fills the area, so it is always as large as its content
 *                           and never scrolls itself
 *           .ce-widgets     inline error messages (pointer-events: none)
 *
 *   Because the textarea never scrolls and the shared parent does, text, caret, gutter and
 *   every decoration move together on the compositor: there is no scroll event to mirror and
 *   nothing can trail by a frame (an overlay chasing a self-scrolling textarea always does).
 *
 * Highlighting
 *   A line-oriented Python lexer. Its only cross-line state — an open triple-quoted or
 *   backslash-continued string plus its prefix flags — packs into a small integer. Input is
 *   batched to one rAF; the flush diffs old/new lines (common prefix and suffix), re-lexes the
 *   changed lines, then keeps going down the file only while the carried state differs from
 *   what was there before. Typing inside a line touches one <div>; opening a `"""` re-colours
 *   exactly the lines it swallows.
 *
 * Editing
 *   Tab / Shift+Tab, Enter auto-indent, Backspace to the previous tab stop, Ctrl+/ comments,
 *   bracket auto-close with type-over, smart Home. Every programmatic edit goes through
 *   document.execCommand('insertText') so the browser's own undo stack keeps working.
 *
 * Decorations
 *   Positioned with CSS custom properties (`--line`, `--col`) in line-height and `ch` units:
 *   no layout reads, and they stay exact when the web font finishes loading. Error marks
 *   follow their code when lines are inserted or removed above them, and go "stale" (stop
 *   pulsing) once the marked line itself is edited.
 */
import { bus as globalBus } from '../core/bus.js';
import { settings } from '../core/settings.js';
import { h, inlineCode } from './dom.js';

const INDENT = 4;
const TAB = '    ';
const TYPE_INTERVAL_MS = 35; // ui:type throttle
const EMPTY = Object.freeze({});
const BULK_LINES = 400; // a flush touching more lines than this rebuilds with one innerHTML
const CHUNK = 64;
const NUM_BLOCK = 256; // line numbers per gutter text block // lines per layout chunk: an edit relayouts one chunk, not every sibling line
const CASCADE_SYNC_LINES = 160; // state-cascade lines re-lexed in the same frame (past the viewport)
const CASCADE_SLICE_MS = 6; // budget per idle slice for the rest of a cascade
const MATCH_SCAN_LINES = 3000; // bracket-match search horizon
const HEAT_KEYFRAMES = [{ opacity: 1 }, { opacity: 0 }];
const HEAT_TIMING = { duration: 340, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' };
const WIDGET_GAP_TOP = 6; // px between the marked line and its message widget (matches editor.css)
const WIDGET_GAP_BOTTOM = 3;
const CLOSER = { '(': ')', '[': ']', '{': '}' };
const OPENER = { ')': '(', ']': '[', '}': '{' };

// ═════════════════════════════════════════════════════════════════════════════════════════
// Python lexer
// ═════════════════════════════════════════════════════════════════════════════════════════

// Cross-line state: low 3 bits = string kind, higher bits = prefix flags.
const K_MASK = 7;
const K_TDQ = 1; // inside """…
const K_TSQ = 2; // inside '''…
const K_DQ = 3; // "… continued by a trailing backslash
const K_SQ = 4; // '… continued by a trailing backslash
const F_FMT = 8;
const F_RAW = 16;
const F_BYTES = 32;
const F_DOC = 64;
const F_U = 128; // only used while validating prefixes

const KEYWORDS = new Set(
  ('and as assert async await break class continue def del elif else except finally for from ' +
    'global if import in is lambda nonlocal not or pass raise return try while with yield').split(' '),
);
const BUILTINS = new Set(
  ('abs aiter all anext any ascii bin bool breakpoint bytearray bytes callable chr classmethod ' +
    'compile complex delattr dict dir divmod enumerate eval exec filter float format frozenset ' +
    'getattr globals hasattr hash help hex id input int isinstance issubclass iter len list locals ' +
    'map max memoryview min next object oct open ord pow print property range repr reversed round ' +
    'set setattr slice sorted staticmethod str sum super tuple type vars zip __import__ __name__ ' +
    '__file__ __doc__ NotImplemented Ellipsis').split(' '),
);
const SOFT_KEYWORDS = new Set(['match', 'case']);

// ASCII character classes
const C_ID = 1;
const C_DIGIT = 2;
const C_HEX = 4;
const C_OP = 8;
const CC = new Uint8Array(128);
for (let c = 0; c < 128; c++) {
  if ((c >= 65 && c <= 90) || (c >= 97 && c <= 122) || c === 95) CC[c] |= C_ID;
  if (c >= 48 && c <= 57) CC[c] |= C_DIGIT | C_HEX;
  if ((c >= 65 && c <= 70) || (c >= 97 && c <= 102)) CC[c] |= C_HEX;
}
for (const ch of '+-*/%=<>!&|^~@:') CC[ch.charCodeAt(0)] |= C_OP;

// charCodeAt past the end is NaN: every test below is false for it.
const isIdStart = (c) => (c < 128 ? (CC[c] & C_ID) !== 0 : c > 160);
const isIdPart = (c) => (c < 128 ? (CC[c] & (C_ID | C_DIGIT)) !== 0 : c > 160);
const isDigit = (c) => c >= 48 && c <= 57;
const isNumPart = (c) => (c >= 48 && c <= 57) || c === 95;
const isHexPart = (c) => (c < 128 && (CC[c] & C_HEX) !== 0) || c === 95;
const isOp = (c) => c < 128 && (CC[c] & C_OP) !== 0;

// `# -- OBJECTIVE 1 ----`, `# == Part two ==`, `# OBJECTIVE: …` read as section headers.
const HEADER_RE = /^#\s*(?:[-=#*~/]{2,}\s*[A-Za-z0-9]|(?:OBJECTIVE|SECTION|STEP|TASK|PART|MISSION)\b)/;
const COMMENT_MARK_RE = /`[^`\n]+`|\b(?:TODO|FIXME|XXX|HACK|NOTE|BUG)\b/g;
const COMMENT_MARK_TEST = /`|TODO|FIXME|XXX|HACK|NOTE|BUG/;
const ESC_RE = /[&<>]/g;
const ESC_TEST = /[&<>]/;
const ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;' };
const escChar = (ch) => ESC_MAP[ch];
const esc = (s) => (ESC_TEST.test(s) ? s.replace(ESC_RE, escChar) : s);
const commentMark = (m) =>
  m.charCodeAt(0) === 96 ? `<span class="c-cc">${m}</span>` : `<span class="c-td">${m}</span>`;

const OPEN_HTML = ['<span class="c-br">(</span>', '<span class="c-br">[</span>', '<span class="c-br">{</span>'];
const CLOSE_HTML = ['<span class="c-br">)</span>', '<span class="c-br">]</span>', '<span class="c-br">}</span>'];

// Lexer output for the line just highlighted (module scope: no per-line result objects).
let H = ''; // HTML
let END = 0; // state carried into the next line
let HEAD = false; // the line is a section-header comment
let IG = 0; // indent-guide levels
let BR = null; // code brackets: [col * 8 + kind, …] — kind 0/1 ( ) 2/3 [ ] 4/5 { }
let STMT = true; // nothing but whitespace seen yet on this line (decorators, docstrings)

const span = (cls, html) => {
  H += '<span class="' + cls + '">' + html + '</span>';
};
const bracket = (col, kind) => {
  (BR || (BR = [])).push(col * 8 + kind);
};

/**
 * Highlight one line of Python that starts in lexer `state`.
 * Returns the state at the end of the line; the HTML is left in `H` (plus HEAD / IG / BR).
 */
function highlight(s, state) {
  H = '';
  END = 0;
  HEAD = false;
  IG = 0;
  BR = null;
  STMT = true;
  const n = s.length;
  let i = 0;
  IG = indentLevel(s);
  if (state & K_MASK) {
    i = lexString(s, 0, 0, state & K_MASK, state & ~K_MASK);
    STMT = false;
    if (i >= n) return END;
  } else {
    i = leadingWs(s);
    if (i) H = s.slice(0, i);
  }
  lexCode(s, i, false, 0);
  return END;
}

/**
 * Code until end of line. In an f-string replacement field (`fexpr`) it returns at the `}`,
 * `!conversion` or `:format` that closes the field, or at the enclosing quote `q`.
 */
function lexCode(s, i, fexpr, q) {
  const n = s.length;
  let depth = 0;
  let afterDot = false;
  let expect = 0; // 1: a def name follows, 2: a class name follows
  while (i < n) {
    const c = s.charCodeAt(i);

    if (c === 32 || c === 9) {
      let j = i + 1;
      while (j < n && (s.charCodeAt(j) === 32 || s.charCodeAt(j) === 9)) j++;
      H += s.slice(i, j);
      i = j;
      continue;
    }

    if (fexpr) {
      if (c === q) return i;
      if (depth === 0 && (c === 125 || ((c === 33 || c === 58) && s.charCodeAt(i + 1) !== 61))) return i;
    }

    if (c === 35 && !fexpr) {
      comment(s, i);
      return n;
    }

    if (isIdStart(c)) {
      let j = i + 1;
      while (j < n && isIdPart(s.charCodeAt(j))) j++;
      const next = s.charCodeAt(j);
      if ((next === 34 || next === 39) && j - i <= 2) {
        const flags = prefixFlags(s, i, j);
        if (flags >= 0) {
          span('c-sp', s.slice(i, j));
          i = openString(s, j, flags, fexpr);
          afterDot = false;
          continue;
        }
      }
      const w = s.slice(i, j);
      let cls = '';
      if (expect) {
        cls = expect === 1 ? 'c-fn' : 'c-cl';
        expect = 0;
      } else if (afterDot) {
        cls = next === 40 ? 'c-fc' : '';
      } else if (KEYWORDS.has(w)) {
        cls = 'c-k';
        if (w === 'def') expect = 1;
        else if (w === 'class') expect = 2;
      } else if (w === 'True' || w === 'False' || w === 'None') {
        cls = 'c-c';
      } else if (w === 'self' || w === 'cls') {
        cls = 'c-sf';
      } else if (BUILTINS.has(w)) {
        cls = 'c-b';
      } else if (STMT && !fexpr && SOFT_KEYWORDS.has(w) && /^\s+[^\s=.,)(\]:][^#]*:\s*(#.*)?$/.test(s.slice(j))) {
        cls = 'c-k';
      } else {
        const c0 = w.charCodeAt(0);
        if (c0 >= 65 && c0 <= 90) cls = w.length > 1 && w === w.toUpperCase() ? 'c-cn' : 'c-cl';
        else if (next === 40) cls = 'c-fc';
      }
      if (cls) span(cls, w);
      else H += w;
      STMT = false;
      afterDot = false;
      i = j;
      continue;
    }

    if (isDigit(c) || (c === 46 && isDigit(s.charCodeAt(i + 1)))) {
      const j = scanNumber(s, i);
      span('c-n', s.slice(i, j));
      STMT = false;
      afterDot = false;
      i = j;
      continue;
    }

    if (c === 34 || c === 39) {
      i = openString(s, i, 0, fexpr);
      afterDot = false;
      continue;
    }

    if (c === 40 || c === 91 || c === 123) {
      const k = c === 40 ? 0 : c === 91 ? 1 : 2;
      bracket(i, k * 2);
      H += OPEN_HTML[k];
      depth++;
      STMT = false;
      afterDot = false;
      i++;
      continue;
    }
    if (c === 41 || c === 93 || c === 125) {
      const k = c === 41 ? 0 : c === 93 ? 1 : 2;
      bracket(i, k * 2 + 1);
      H += CLOSE_HTML[k];
      if (depth > 0) depth--;
      STMT = false;
      afterDot = false;
      i++;
      continue;
    }

    if (c === 64 && STMT && !fexpr) {
      let j = i + 1;
      while (j < n && (isIdPart(s.charCodeAt(j)) || s.charCodeAt(j) === 46)) j++;
      span('c-dc', s.slice(i, j));
      STMT = false;
      i = j;
      continue;
    }

    if (c === 46) {
      if (s.charCodeAt(i + 1) === 46 && s.charCodeAt(i + 2) === 46) {
        span('c-c', '...');
        i += 3;
        afterDot = false;
      } else {
        span('c-p', '.');
        i++;
        afterDot = true;
      }
      STMT = false;
      continue;
    }
    if (c === 44 || c === 59) {
      span('c-p', c === 44 ? ',' : ';');
      STMT = false;
      afterDot = false;
      i++;
      continue;
    }

    if (isOp(c)) {
      let j = i + 1;
      while (j < n && j - i < 3 && isOp(s.charCodeAt(j))) {
        // inside a replacement field, `:` / `!` end the expression unless they start `:=` / `!=`
        const d = s.charCodeAt(j);
        if (fexpr && depth === 0 && (d === 58 || d === 33) && s.charCodeAt(j + 1) !== 61) break;
        j++;
      }
      span('c-o', esc(s.slice(i, j)));
      STMT = false;
      afterDot = false;
      i = j;
      continue;
    }

    H += esc(s.charAt(i));
    i++;
  }
  return n;
}

function comment(s, i) {
  const text = s.slice(i);
  const head = HEADER_RE.test(text);
  let html = esc(text);
  if (COMMENT_MARK_TEST.test(html)) html = html.replace(COMMENT_MARK_RE, commentMark);
  if (head) HEAD = true;
  span(head ? 'c-ch' : 'c-cm', html);
}

/** String prefix flags for s[i, j) (r, b, f, t, u and legal combinations), or -1. */
function prefixFlags(s, i, j) {
  let f = 0;
  for (let k = i; k < j; k++) {
    const c = s.charCodeAt(k) | 32;
    const bit = c === 114 ? F_RAW : c === 98 ? F_BYTES : c === 102 || c === 116 ? F_FMT : c === 117 ? F_U : 0;
    if (!bit || f & bit) return -1;
    f |= bit;
  }
  if ((f & F_U && j - i > 1) || (f & F_BYTES && f & F_FMT)) return -1;
  return f & ~F_U;
}

/** At an opening quote: lex the string (to its end or end of line). */
function openString(s, i, flags, fexpr) {
  const q = s.charCodeAt(i);
  const triple = s.charCodeAt(i + 1) === q && s.charCodeAt(i + 2) === q;
  if (triple && STMT && !fexpr && !(flags & F_FMT)) flags |= F_DOC;
  STMT = false;
  const kind = triple ? (q === 34 ? K_TDQ : K_TSQ) : q === 34 ? K_DQ : K_SQ;
  return lexString(s, i, triple ? 3 : 1, kind, flags);
}

/**
 * String body from `start` (its opening quotes are `qlen` chars there; 0 on a continuation
 * line). Returns the index after the closing quote, or the line length with END set when the
 * string carries on to the next line.
 */
function lexString(s, start, qlen, kind, flags) {
  const n = s.length;
  const triple = kind === K_TDQ || kind === K_TSQ;
  const q = kind === K_TDQ || kind === K_DQ ? 34 : 39;
  const raw = (flags & F_RAW) !== 0;
  const fmt = (flags & F_FMT) !== 0;
  const cls = flags & F_DOC ? 'c-ds' : 'c-s';
  let seg = start;
  let i = start + qlen;
  let continued = false;
  while (i < n) {
    const c = s.charCodeAt(i);
    if (c === 92) {
      if (i + 1 >= n) {
        continued = true;
        break;
      }
      if (raw) {
        i += 2;
        continue;
      }
      if (i > seg) span(cls, esc(s.slice(seg, i)));
      const e = escapeEnd(s, i);
      span('c-se', esc(s.slice(i, e)));
      i = seg = e;
      continue;
    }
    if (c === q) {
      if (!triple) {
        i++;
        span(cls, esc(s.slice(seg, i)));
        END = 0;
        return i;
      }
      if (s.charCodeAt(i + 1) === q && s.charCodeAt(i + 2) === q) {
        i += 3;
        span(cls, esc(s.slice(seg, i)));
        END = 0;
        return i;
      }
      i++;
      continue;
    }
    if (fmt && c === 123) {
      if (s.charCodeAt(i + 1) === 123) {
        i += 2; // {{ is a literal brace
        continue;
      }
      if (i > seg) span(cls, esc(s.slice(seg, i)));
      i = seg = lexField(s, i, q);
      continue;
    }
    i++;
  }
  if (n > seg) span(cls, esc(s.slice(seg, n)));
  END = triple || continued ? kind | flags : 0;
  return n;
}

/** f-string replacement field at `{`: expression, !conversion, :format spec, `}`. */
function lexField(s, i, q) {
  const n = s.length;
  bracket(i, 4);
  span('c-si', '{');
  i = lexCode(s, i + 1, true, q);
  let c = s.charCodeAt(i);
  if (c === 33) {
    const j = isIdStart(s.charCodeAt(i + 1)) ? i + 2 : i + 1;
    span('c-si', esc(s.slice(i, j)));
    i = j;
    c = s.charCodeAt(i);
  }
  if (c === 58) {
    span('c-si', ':');
    let seg = ++i;
    while (i < n) {
      const d = s.charCodeAt(i);
      if (d === 125 || d === q) break;
      if (d === 123) {
        if (i > seg) span('c-fs', esc(s.slice(seg, i)));
        i = seg = lexField(s, i, q);
        continue;
      }
      i++;
    }
    if (i > seg) span('c-fs', esc(s.slice(seg, i)));
    c = s.charCodeAt(i);
  }
  if (c === 125) {
    bracket(i, 5);
    span('c-si', '}');
    return i + 1;
  }
  return i; // unterminated field: the string lexer takes over at the quote / end of line
}

function escapeEnd(s, i) {
  const c = s.charCodeAt(i + 1);
  let max = 0;
  if (c === 120) max = 2; // \xhh
  else if (c === 117) max = 4; // \uhhhh
  else if (c === 85) max = 8; // \Uhhhhhhhh
  else if (c === 78 && s.charCodeAt(i + 2) === 123) {
    const close = s.indexOf('}', i + 3); // \N{NAME}
    return close < 0 ? i + 2 : close + 1;
  } else if (c >= 48 && c <= 55) {
    let j = i + 2;
    while (j < i + 4 && s.charCodeAt(j) >= 48 && s.charCodeAt(j) <= 55) j++;
    return j;
  }
  let j = i + 2;
  while (max > 0 && isHexPart(s.charCodeAt(j)) && s.charCodeAt(j) !== 95) {
    j++;
    max--;
  }
  return j;
}

function scanNumber(s, i) {
  const n = s.length;
  let j = i;
  if (s.charCodeAt(i) === 48) {
    const p = s.charCodeAt(i + 1) | 32;
    if (p === 120 || p === 111 || p === 98) {
      j = i + 2; // 0x… 0o… 0b…
      while (j < n && isHexPart(s.charCodeAt(j))) j++;
      return j;
    }
  }
  while (j < n && isNumPart(s.charCodeAt(j))) j++;
  if (s.charCodeAt(j) === 46) {
    j++;
    while (j < n && isNumPart(s.charCodeAt(j))) j++;
  }
  if ((s.charCodeAt(j) | 32) === 101) {
    let k = j + 1;
    const sign = s.charCodeAt(k);
    if (sign === 43 || sign === 45) k++;
    if (isDigit(s.charCodeAt(k))) {
      j = k;
      while (j < n && isNumPart(s.charCodeAt(j))) j++;
    }
  }
  if ((s.charCodeAt(j) | 32) === 106) j++; // complex: 3j
  return j;
}

/**
 * Highlight Python source to HTML (one `<div class="ce-ln">` per line). Exposed for tests
 * and for read-only code views that want the editor's exact colours.
 */
export function highlightPython(text) {
  const lines = String(text).split('\n');
  let state = 0;
  let html = '';
  for (const line of lines) {
    state = highlight(line, state);
    html += lineOpenTag() + H + '</div>';
  }
  return html;
}

function lineClass() {
  return HEAD ? (IG ? 'ce-ln is-hd ig' : 'ce-ln is-hd') : IG ? 'ce-ln ig' : 'ce-ln';
}
function lineOpenTag() {
  return IG ? `<div class="${lineClass()}" style="--ig:${IG}">` : `<div class="${lineClass()}">`;
}

// ═════════════════════════════════════════════════════════════════════════════════════════
// Text helpers (pure)
// ═════════════════════════════════════════════════════════════════════════════════════════

/** Visual column of code-unit index `col` in `line` (tabs expand to the next multiple of 4). */
function visualCol(line, col) {
  let v = 0;
  for (let i = 0; i < col; i++) v = line.charCodeAt(i) === 9 ? v + INDENT - (v % INDENT) : v + 1;
  return v;
}

function leadingWs(line) {
  let i = 0;
  while (i < line.length && (line.charCodeAt(i) === 32 || line.charCodeAt(i) === 9)) i++;
  return i;
}

const isBlank = (line) => leadingWs(line) === line.length;

/** Indentation in levels (4 columns each) of a line's leading whitespace. */
function indentLevel(line) {
  let col = 0;
  for (let i = 0; i < line.length; i++) {
    const c = line.charCodeAt(i);
    if (c === 32) col++;
    else if (c === 9) col += INDENT - (col % INDENT);
    else break;
  }
  return (col / INDENT) | 0;
}

/** The line's code (ignoring a trailing comment) ends with `:` — it opens a block. */
function opensBlock(line) {
  let end = codeEnd(line);
  while (end > 0 && (line.charCodeAt(end - 1) === 32 || line.charCodeAt(end - 1) === 9)) end--;
  return end > 0 && line.charCodeAt(end - 1) === 58;
}

/** Index where a trailing `#` comment starts (quote-aware, single line), or the line length. */
function codeEnd(line) {
  let q = 0;
  for (let i = 0; i < line.length; i++) {
    const c = line.charCodeAt(i);
    if (q) {
      if (c === 92) i++;
      else if (c === q) q = 0;
    } else if (c === 34 || c === 39) q = c;
    else if (c === 35) return i;
  }
  return line.length;
}

/** Expand tabs in leading whitespace of every line to spaces (pasted code), normalise CRLF. */
function normalizePaste(text) {
  return text.replace(/\r\n?/g, '\n').replace(/^[ \t]+/gm, (ws) => {
    let out = '';
    for (let i = 0; i < ws.length; i++) out += ws.charCodeAt(i) === 9 ? ' '.repeat(INDENT - (out.length % INDENT)) : ' ';
    return out;
  });
}

function newChunk() {
  const chunk = document.createElement('div');
  chunk.className = 'ce-chunk';
  return chunk;
}

/** Split an over-full chunk into CHUNK-line pieces (moves nodes; line identity is preserved). */
function splitChunk(chunk) {
  while (chunk.childNodes.length > CHUNK * 2) {
    // Peel CHUNK lines off the end; each piece holds earlier lines than the previous one,
    // so it goes directly after the source chunk.
    const piece = newChunk();
    for (let k = 0; k < CHUNK; k++) piece.insertBefore(chunk.lastChild, piece.firstChild);
    chunk.after(piece);
  }
}

const idle = (fn) =>
  typeof requestIdleCallback === 'function' ? requestIdleCallback(fn, { timeout: 120 }) : setTimeout(fn, 24);
const cancelIdle = (id) => (typeof cancelIdleCallback === 'function' ? cancelIdleCallback(id) : clearTimeout(id));

/** "a\na+1\n…\nb", with a leading newline when appending to a non-empty block. */
function numberRun(a, b, lead) {
  let s = lead ? '\n' + a : String(a);
  for (let i = a + 1; i <= b; i++) s += '\n' + i;
  return s;
}

/** In-place splice without spreading (safe for any length). */
function splice(arr, start, del, items) {
  const add = items.length;
  const delta = add - del;
  const len = arr.length;
  if (delta > 0) {
    for (let k = 0; k < delta; k++) arr.push(arr[0]);
    for (let i = len - 1; i >= start + del; i--) arr[i + delta] = arr[i];
  } else if (delta < 0) {
    for (let i = start + del; i < len; i++) arr[i + delta] = arr[i];
    arr.length = len + delta;
  }
  for (let i = 0; i < add; i++) arr[start + i] = items[i];
}

/** `TypeError: msg` → {tag, body}; anything else is a generic fault. */
function parseMessage(message) {
  const text = String(message ?? '').trim();
  const m = /^([A-Z][A-Za-z]*(?:Error|Exception|Warning|Exit|Interrupt)|Timeout)\s*:\s*([\s\S]+)$/.exec(text);
  if (m) return { tag: m[1], body: m[2] };
  return { tag: 'FAULT', body: text || 'Execution stopped on this line.' };
}

/**
 * Apply sorted, non-overlapping edits [{at, del, ins}] to text[from, to).
 * mapPos maps an offset through them; with `stayBefore`, an insertion exactly at p lands after
 * p (a selection that starts at a line start keeps covering that line's new indentation).
 */
function applyEdits(text, from, to, edits) {
  let out = '';
  let pos = from;
  for (const e of edits) {
    out += text.slice(pos, e.at) + e.ins;
    pos = e.at + e.del;
  }
  return out + text.slice(pos, to);
}
function mapPos(p, edits, stayBefore) {
  let delta = 0;
  for (const e of edits) {
    if (e.at > p || (e.at === p && e.del === 0 && stayBefore)) break;
    if (p < e.at + e.del) return e.at + delta;
    delta += e.ins.length - e.del;
  }
  return p + delta;
}

// ═════════════════════════════════════════════════════════════════════════════════════════
// CodeEditor
// ═════════════════════════════════════════════════════════════════════════════════════════

export class CodeEditor {
  /** Root element (`.ce`), appended to the container. */
  el;

  #bus;
  #onChange;
  #onSubmit;
  #onSave;
  #ac = new AbortController();
  #ro = null;
  #offSettings = null;
  #dead = false;

  // DOM
  #scroller;
  #gutter;
  #nums;
  #numBlocks = [];
  #numCount = 0;
  #gcur;
  #gcurText;
  #area;
  #under;
  #band;
  #matchA;
  #matchB;
  #aguide;
  #aguideKey = -1;
  #heat;
  #heatAnim = null;
  #code;
  #ta;
  #widgets;
  #ruler;
  #probe;
  #live;

  // document model (index = line)
  #text = '';
  #lines = [''];
  #els = [];
  #states = [0, 0]; // lexer state at the start of each line, plus one past the end
  #brk = [null];
  #starts = new Int32Array(256); // offset of each line's first char
  #clean = '';
  #dirty = false;

  // flush scheduling
  #raf = 0;
  #silent = false;
  #navigated = false; // the last selection change came from the keyboard → keep the caret in view

  // selection cache
  #selS = -1;
  #selE = -1;
  #selHead = -1;
  #curLine = -1;
  #hasSel = false;

  // metrics (CSS px)
  #lh = 22; // fallbacks until editor.css has been measured
  #padT = 14;
  #padL = 18;
  #chW = 8.4;
  #metricsValid = false;
  #viewH = 0;
  #viewW = 0;

  #cascadeAt = -1; // first line whose lexer state is still being re-derived (-1: none)
  #cascadeState = 0;
  #cascadeJob = 0;
  #scrollTop = 0;

  #marks = [];
  #marksMoved = false;
  #matchLine = -1;
  #matchCol = -1;
  #digits = 0;
  #lastType = -Infinity;

  constructor(container, { bus, onChange, onSubmit, onSave } = {}) {
    this.#bus = bus || globalBus;
    this.#onChange = onChange;
    this.#onSubmit = onSubmit;
    this.#onSave = onSave;
    this.#build();
    container.append(this.el);
    this.#listen();
    this.#renderAll(this.#lines);
    this.#setLineCount(1);
    this.#syncSelection();
  }

  // ── public API ────────────────────────────────────────────────────────────────────────

  get value() {
    return this.#ta.value;
  }

  /**
   * Replace the whole text, keeping scroll and caret where they were when possible.
   * `silent`: no onChange, and the text becomes the clean baseline (it came from disk).
   */
  setValue(text, { silent = false } = {}) {
    if (this.#dead) return;
    const next = String(text ?? '').replace(/\r\n?/g, '\n');
    const ta = this.#ta;
    const prev = ta.value;
    if (silent) this.#clean = next;
    if (next === prev) {
      this.#flush();
      this.#updateDirty();
      return;
    }
    const top = this.#scroller.scrollTop;
    const left = this.#scroller.scrollLeft;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    const dir = ta.selectionDirection;

    // Map the caret through the change: unchanged prefix → same offset, unchanged suffix →
    // same distance from the end, inside the rewritten region → clamped.
    const min = Math.min(prev.length, next.length);
    let pre = 0;
    while (pre < min && prev.charCodeAt(pre) === next.charCodeAt(pre)) pre++;
    let suf = 0;
    while (suf < min - pre && prev.charCodeAt(prev.length - 1 - suf) === next.charCodeAt(next.length - 1 - suf)) suf++;
    const map = (p) => (p <= pre ? p : p >= prev.length - suf ? p + next.length - prev.length : Math.min(p, next.length - suf));

    ta.value = next;
    ta.setSelectionRange(map(s), map(e), dir);
    this.#silent = silent;
    this.#navigated = false;
    this.#flush();
    this.#scroller.scrollTop = top;
    this.#scroller.scrollLeft = left;
  }

  get dirty() {
    return this.#ta.value !== this.#clean;
  }

  markClean() {
    this.#clean = this.#ta.value;
    this.#updateDirty();
  }

  get readOnly() {
    return this.#ta.readOnly;
  }

  set readOnly(v) {
    this.#ta.readOnly = !!v;
    this.el.classList.toggle('is-readonly', !!v);
  }

  get lineCount() {
    return this.#lines.length;
  }

  /** Gutter marker + pulsing line glow + inline message under the line (1-based). */
  markError(line, message = '') {
    if (this.#dead) return;
    this.#flush();
    const ln = this.#clampLine(line);
    const previous = this.#marks.find((m) => m.line === ln);
    if (previous) this.#dropMark(previous, true);

    const text = this.#lines[ln];
    const ws = leadingWs(text);
    const col = ws < text.length ? visualCol(text, ws) : 0;
    const { tag, body } = parseMessage(message);

    const glow = h('div', { class: 'ce-errline' });
    const num = document.createTextNode(String(ln + 1));
    const gmark = h('div', { class: 'ce-gmark' }, h('i', { class: 'ce-gmark__pip' }), h('span', { class: 'ce-gmark__num' }, num));
    const lnLabel = document.createTextNode(`LN ${ln + 1}`);
    const widget = h(
      'div',
      { class: 'ce-widget' },
      h(
        'div',
        { class: 'ce-widget__box' },
        h(
          'div',
          { class: 'ce-widget__head' },
          h('span', { class: tag === 'FAULT' ? 'ce-widget__tag' : 'ce-widget__tag is-type' }, tag),
          h('span', { class: 'ce-widget__ln' }, lnLabel),
        ),
        h('div', { class: 'ce-widget__msg', html: inlineCode(body) }),
      ),
    );
    const rmark = h('div', { class: 'ce-rmark' });
    widget.style.setProperty('--col', col);
    const mark = { line: ln, stale: false, cover: 0, glow, gmark, widget, rmark, num, lnLabel };
    this.#under.append(glow);
    this.#gutter.append(gmark);
    this.#widgets.append(widget);
    this.#ruler.append(rmark);
    this.#marks.push(mark);
    this.#placeMark(mark);

    this.#live.textContent = `Error on line ${ln + 1}: ${body}`;
    this.#publishViewWidth();
    this.#snapWidget(mark);
    this.#revealLine(ln);
    this.#layoutMarks();
    this.#updateOcclusion();
  }

  clearMarks() {
    for (const m of this.#marks) this.#dropMark(m, false);
    this.#marks.length = 0;
    this.#live.textContent = '';
  }

  /**
   * Viewport rect (CSS px) of a line's text — from its first non-blank character to its last,
   * clamped to the visible code region horizontally. Blank lines give a 2-character rect.
   */
  lineRect(line) {
    if (this.#dead) return new DOMRect();
    this.#flush();
    this.#measure();
    const ln = this.#clampLine(line);
    const text = this.#lines[ln];
    const ws = leadingWs(text);
    let end = text.length;
    while (end > ws && (text.charCodeAt(end - 1) === 32 || text.charCodeAt(end - 1) === 9)) end--;
    const area = this.#area.getBoundingClientRect();
    const view = this.#scroller.getBoundingClientRect();
    const x = area.left + this.#padL;
    let x0 = x + visualCol(text, ws) * this.#chW;
    let x1 = end > ws ? x + visualCol(text, end) * this.#chW : x0 + 2 * this.#chW;
    const minX = view.left + this.#gutter.offsetWidth;
    const maxX = view.left + this.#scroller.clientWidth;
    x0 = Math.min(Math.max(x0, minX), maxX);
    x1 = Math.min(Math.max(x1, x0 + 1), maxX);
    if (x1 <= x0) x0 = Math.max(minX, x1 - 1);
    return new DOMRect(x0, area.top + this.#padT + ln * this.#lh, x1 - x0, this.#lh);
  }

  focus() {
    if (!this.#dead) this.#ta.focus({ preventScroll: true });
  }

  destroy() {
    if (this.#dead) return;
    this.#dead = true;
    this.#ac.abort();
    if (this.#raf) cancelAnimationFrame(this.#raf);
    this.#raf = 0;
    this.#cancelCascade();
    this.#ro?.disconnect();
    this.#ro = null;
    this.#offSettings?.();
    this.#offSettings = null;
    this.#marks.length = 0;
    this.el.remove();
    this.#els = [];
    this.#brk = [];
    this.#onChange = this.#onSubmit = this.#onSave = null;
  }

  // ── construction ──────────────────────────────────────────────────────────────────────

  #build() {
    this.#gcurText = document.createTextNode('1');
    this.#nums = h('div', { class: 'ce-nums' });
    this.#gutter = h(
      'div',
      { class: 'ce-gutter', 'aria-hidden': 'true' },
      this.#nums,
      (this.#gcur = h('div', { class: 'ce-gcur' }, this.#gcurText)),
    );
    this.#band = h('div', { class: 'ce-curline' });
    this.#matchA = h('div', { class: 'ce-match' });
    this.#matchB = h('div', { class: 'ce-match' });
    this.#aguide = h('div', { class: 'ce-aguide' });
    this.#heat = h('div', { class: 'ce-heat' });
    this.#under = h('div', { class: 'ce-under', 'aria-hidden': 'true' }, this.#band, this.#aguide, this.#heat, this.#matchA, this.#matchB);
    this.#code = h('div', { class: 'ce-code', 'aria-hidden': 'true', translate: 'no' });
    this.#ta = h('textarea', {
      class: 'ce-input',
      wrap: 'off',
      spellcheck: 'false',
      autocomplete: 'off',
      autocorrect: 'off',
      autocapitalize: 'off',
      translate: 'no',
      'aria-label': 'Mission code editor (Python)',
      'aria-multiline': 'true',
      'data-gramm': 'false',
      'data-enable-grammarly': 'false',
    });
    this.#widgets = h('div', { class: 'ce-widgets', 'aria-hidden': 'true' });
    this.#probe = h('span', { class: 'ce-probe', 'aria-hidden': 'true' }, '0'.repeat(64));
    this.#area = h('div', { class: 'ce-area' }, this.#under, this.#code, this.#ta, this.#widgets, this.#probe);
    this.#scroller = h('div', { class: 'ce-scroller' }, h('div', { class: 'ce-content' }, this.#gutter, this.#area));
    this.#ruler = h('div', { class: 'ce-ruler', 'aria-hidden': 'true' });
    this.#live = h('div', { class: 'ce-live', role: 'status', 'aria-live': 'polite' });
    this.el = h('div', { class: 'ce' }, this.#scroller, this.#ruler, this.#live);
    this.el.classList.toggle('ce--still', !!settings.get('reducedMotion'));
  }

  #listen() {
    const opts = { signal: this.#ac.signal };
    const ta = this.#ta;
    const sel = () => this.#schedule();
    ta.addEventListener('keydown', (e) => this.#onKeyDown(e), opts);
    ta.addEventListener('input', () => this.#onInput(), opts);
    ta.addEventListener('paste', (e) => this.#onPaste(e), opts);
    ta.addEventListener('select', sel, opts);
    ta.addEventListener('selectionchange', sel, opts);
    ta.addEventListener('keyup', sel, opts);
    ta.addEventListener('focus', sel, opts);
    ta.addEventListener('pointerdown', () => (this.#navigated = false), opts);
    ta.addEventListener('pointerup', sel, opts);
    // The textarea is sized to its content, so it should never scroll; if the browser scrolls it
    // anyway (one frame before the overlay grows), hand the offset to the real scroller.
    ta.addEventListener(
      'scroll',
      () => {
        if (ta.scrollTop || ta.scrollLeft) {
          this.#scroller.scrollTop += ta.scrollTop;
          this.#scroller.scrollLeft += ta.scrollLeft;
          ta.scrollTop = 0;
          ta.scrollLeft = 0;
        }
      },
      opts,
    );
    this.#scroller.addEventListener('scroll', () => (this.#scrollTop = this.#scroller.scrollTop), { passive: true, signal: this.#ac.signal });
    document.addEventListener(
      'selectionchange',
      () => {
        if (document.activeElement === ta) this.#schedule();
      },
      opts,
    );

    if (typeof ResizeObserver === 'function') {
      this.#ro = new ResizeObserver((entries) => {
        for (const entry of entries) {
          if (entry.target === this.#probe) {
            const w = entry.contentRect.width;
            if (w > 0) this.#chW = w / 64;
          } else {
            this.#viewH = entry.borderBoxSize?.[0]?.blockSize ?? entry.contentRect.height;
          }
        }
        this.#metricsValid = false;
        this.#measure();
        this.#publishViewWidth();
        for (const m of this.#marks) this.#snapWidget(m);
        this.#layoutMarks();
      });
      this.#ro.observe(this.#scroller, { box: 'border-box' });
      this.#ro.observe(this.#probe);
    }

    this.#offSettings = settings.onChange((key, value) => {
      if (key === 'reducedMotion') this.el.classList.toggle('ce--still', !!value);
    });
  }

  // ── metrics ───────────────────────────────────────────────────────────────────────────

  #measure() {
    if (this.#metricsValid || !this.el.isConnected) return;
    const cs = getComputedStyle(this.el);
    this.#lh = parseFloat(cs.getPropertyValue('--ce-lh')) || 22;
    this.#padT = parseFloat(cs.getPropertyValue('--ce-pad-t')) || 0;
    this.#padL = parseFloat(cs.getPropertyValue('--ce-pad-l')) || 0;
    if (!this.#ro) this.#chW = this.#probe.offsetWidth / 64 || this.#chW;
    if (!this.#viewH) this.#viewH = this.#scroller.clientHeight;
    // "Scroll past end": the last line can rise to just above the middle of the view.
    const over = Math.max(this.#lh * 3, Math.round(this.#viewH * 0.45));
    this.#code.style.paddingBottom = `${over}px`;
    this.#metricsValid = true;
  }

  /** Inline widgets size themselves to the visible code width, not the scrolled content. */
  #publishViewWidth() {
    const w = this.#scroller.clientWidth - this.#gutter.offsetWidth;
    if (w > 0 && w !== this.#viewW) {
      this.#viewW = w;
      this.#widgets.style.setProperty('--ce-view-w', `${w}px`);
    }
  }

  // ── input & flush ─────────────────────────────────────────────────────────────────────

  #schedule() {
    if (!this.#raf && !this.#dead) this.#raf = requestAnimationFrame(this.#frame);
  }

  #frame = () => {
    this.#raf = 0;
    this.#flush();
  };

  #flush() {
    if (this.#raf) {
      cancelAnimationFrame(this.#raf);
      this.#raf = 0;
    }
    if (this.#dead) return;
    this.#measure();
    const changed = this.#syncText();
    this.#syncSelection(changed);
    // Layout reads happen only here, after every DOM write of the flush.
    if (this.#navigated) {
      this.#navigated = false;
      this.#keepCaretVisible(this.#curLine, this.#selHead);
    }
    if (this.#marksMoved) {
      this.#marksMoved = false;
      this.#layoutMarks();
    }
  }

  #onInput() {
    this.#schedule();
    const now = performance.now();
    if (now - this.#lastType >= TYPE_INTERVAL_MS) {
      this.#lastType = now;
      this.#bus.emit('ui:type', EMPTY);
      this.#flare();
    }
  }

  /** A soft bloom where the keystroke landed, in step with the typing sound. One reused Animation. */
  #flare() {
    if (this.el.classList.contains('ce--still')) return;
    const anim = this.#heatAnim;
    if (anim) {
      anim.currentTime = 0;
      anim.play();
    } else if (typeof this.#heat.animate === 'function') {
      this.#heatAnim = this.#heat.animate(HEAT_KEYFRAMES, HEAT_TIMING);
    }
  }

  /** Bring the model and the highlighted layer up to date with the textarea. */
  #syncText() {
    const text = this.#ta.value;
    if (text === this.#text) return false;
    const oldLines = this.#lines;
    const lines = text.split('\n');
    const oldN = oldLines.length;
    const n = lines.length;
    const min = oldN < n ? oldN : n;
    let top = 0;
    while (top < min && oldLines[top] === lines[top]) top++;
    let bot = 0;
    while (bot < min - top && oldLines[oldN - 1 - bot] === lines[n - 1 - bot]) bot++;
    const oldEnd = oldN - bot;
    const newEnd = n - bot;

    // Reconcile a pending cascade break with this edit (see #runCascade):
    //  break at/above the edit  → catch up to the edit only; its state seeds the edited lines
    //  break inside the edit    → superseded by the new cascade
    //  break below the edit     → survives unless the new cascade reaches it first
    let seed = -1;
    let keep = -1;
    let keepState = 0;
    const brkAt = this.#cascadeAt;
    if (brkAt >= 0) {
      if (brkAt <= top) {
        this.#runCascade(top, Infinity);
        this.#fixBlankGuides(brkAt, top);
        if (this.#cascadeAt >= 0) seed = this.#cascadeState;
      } else if (brkAt > oldEnd) {
        keep = brkAt + n - oldN;
        keepState = this.#cascadeState;
      }
      this.#cancelCascade();
    }

    if (newEnd - top > BULK_LINES) {
      this.#renderAll(lines);
    } else {
      const els = this.#els;
      const states = this.#states;
      const brk = this.#brk;
      const count = newEnd - top;
      const newEls = new Array(count);
      const newStates = new Array(count);
      const newBrk = new Array(count);
      let st = seed >= 0 ? seed : states[top];
      let frag = null;
      for (let k = 0; k < count; k++) {
        const el = document.createElement('div');
        newStates[k] = st;
        st = this.#paint(el, lines[top + k], st);
        newBrk[k] = BR;
        newEls[k] = el;
        (frag || (frag = document.createDocumentFragment())).appendChild(el);
      }
      const ref = oldEnd < oldN ? els[oldEnd] : null;
      const prev = top > 0 ? els[top - 1] : null;
      for (let i = top; i < oldEnd; i++) {
        const chunk = els[i].parentNode;
        els[i].remove();
        if (!chunk.firstChild) chunk.remove();
      }
      if (frag) {
        // New lines join the chunk of their neighbour; an over-full chunk is split.
        const chunk = ref ? ref.parentNode : prev ? prev.parentNode : this.#code.lastChild || this.#code.appendChild(newChunk());
        chunk.insertBefore(frag, ref);
        if (chunk.childNodes.length > CHUNK * 2) splitChunk(chunk);
      }
      splice(els, top, oldEnd - top, newEls);
      splice(states, top, oldEnd - top, newStates);
      splice(brk, top, oldEnd - top, newBrk);
      this.#lines = lines;
      // Carry the new end-of-region state down until it agrees with what was there: through the
      // visible lines (and up to a surviving break) now, the rest in idle slices.
      this.#cascadeAt = newEnd;
      this.#cascadeState = st;
      const end = this.#runCascade(Math.max(newEnd + CASCADE_SYNC_LINES, this.#lastVisibleLine() + 1, keep), Infinity);
      if (keep >= 0 && this.#cascadeAt < 0 && end < keep) {
        this.#cascadeAt = keep; // converged above the old break: it still stands
        this.#cascadeState = keepState;
      }
      this.#fixBlankGuides(top, Math.max(newEnd, end));
      this.#scheduleCascade();
    }

    this.#text = text;
    this.#lines = lines;
    this.#indexLines();
    if (n !== oldN) this.#setLineCount(n);
    if (this.#marks.length) this.#shiftMarks(top, oldEnd, newEnd, n - oldN);
    this.#updateDirty();

    const silent = this.#silent;
    this.#silent = false;
    if (!silent && this.#onChange) {
      try {
        this.#onChange(text);
      } catch (err) {
        console.error('[editor] onChange handler threw', err);
      }
    }
    return true;
  }

  /**
   * Lexer-state cascade. #states is a per-line chain (states[i + 1] = lex(lines[i], states[i]))
   * with at most one break: at #cascadeAt the correct state is #cascadeState, not the stored one.
   * Lines past the break still form a self-consistent chain, so the cascade may stop as soon as
   * the carried state equals the stored one. Re-lexes from the break until it converges, reaches
   * line `until`, or spends `budget` ms; leaves the remaining break in #cascadeAt (-1: none).
   * Returns the first line not re-lexed.
   */
  #runCascade(until, budget) {
    let i = this.#cascadeAt;
    if (i < 0) return 0;
    const states = this.#states;
    const lines = this.#lines;
    const els = this.#els;
    const brk = this.#brk;
    const n = lines.length;
    const t0 = budget < Infinity ? performance.now() : 0;
    let st = this.#cascadeState;
    while (i < n && states[i] !== st) {
      if (i >= until || (t0 && (i & 15) === 0 && performance.now() - t0 > budget)) {
        this.#cascadeAt = i;
        this.#cascadeState = st;
        return i;
      }
      states[i] = st;
      st = this.#paint(els[i], lines[i], st);
      brk[i] = BR;
      i++;
    }
    if (i === n) states[n] = st;
    this.#cascadeAt = -1;
    return i;
  }

  #scheduleCascade() {
    if (this.#cascadeAt >= 0 && !this.#cascadeJob && !this.#dead) this.#cascadeJob = idle(this.#idleCascade);
  }

  #idleCascade = () => {
    this.#cascadeJob = 0;
    if (this.#dead || this.#cascadeAt < 0) return;
    const from = this.#cascadeAt;
    const end = this.#runCascade(Infinity, CASCADE_SLICE_MS);
    this.#fixBlankGuides(from, end);
    this.#scheduleCascade();
  };

  #cancelCascade() {
    if (this.#cascadeJob) cancelIdle(this.#cascadeJob);
    this.#cascadeJob = 0;
    this.#cascadeAt = -1;
  }

  #lastVisibleLine() {
    return Math.ceil((this.#scrollTop + (this.#viewH || 2000)) / this.#lh);
  }

  #paint(el, line, state) {
    const end = highlight(line, state);
    el.className = lineClass();
    if (IG) el.style.setProperty('--ig', IG);
    else if (el.hasAttribute('style')) el.removeAttribute('style');
    el.innerHTML = H;
    return end;
  }

  #renderAll(lines) {
    const n = lines.length;
    const states = new Array(n + 1);
    const brk = new Array(n);
    let st = 0;
    let html = '';
    for (let i = 0; i < n; i++) {
      if (i % CHUNK === 0) html += i ? '</div><div class="ce-chunk">' : '<div class="ce-chunk">';
      states[i] = st;
      st = highlight(lines[i], st);
      brk[i] = BR;
      html += lineOpenTag() + H + '</div>';
    }
    states[n] = st;
    this.#cancelCascade();
    this.#code.innerHTML = html + '</div>';
    this.#els = Array.from(this.#code.getElementsByClassName('ce-ln'));
    this.#states = states;
    this.#brk = brk;
    this.#lines = lines;
    this.#fixBlankGuides(0, n);
  }

  /**
   * Blank lines carry the indent guides of the block around them, so guides run unbroken
   * through a function body's empty lines. Recomputes every blank run touching [from, to).
   */
  #fixBlankGuides(from, to) {
    const lines = this.#lines;
    const n = lines.length;
    let i = Math.min(from, n);
    while (i > 0 && isBlank(lines[i - 1])) i--;
    let end = Math.min(Math.max(to, from + 1), n);
    while (end < n && isBlank(lines[end])) end++;
    while (i < end) {
      if (!isBlank(lines[i])) {
        i++;
        continue;
      }
      let j = i;
      while (j < n && isBlank(lines[j])) j++;
      const level = this.#blankRunLevel(i, j);
      for (let k = i; k < j; k++) {
        const g = Math.max(level, indentLevel(lines[k]));
        const el = this.#els[k];
        if (g) {
          el.classList.add('ig');
          el.style.setProperty('--ig', g);
        } else if (el.classList.contains('ig')) {
          el.classList.remove('ig');
          el.style.removeProperty('--ig');
        }
      }
      i = j;
    }
  }

  /** Guide level for the blank run [i, j): the enclosing block's depth. */
  #blankRunLevel(i, j) {
    const lines = this.#lines;
    const above = i > 0 ? lines[i - 1] : '';
    const below = j < lines.length ? indentLevel(lines[j]) : 0;
    if (i > 0 && opensBlock(above)) return below;
    return Math.min(i > 0 ? indentLevel(above) : 0, below);
  }

  /**
   * The guide of the innermost block around the caret lights up. On a line that opens a block
   * (`def f():`), it is the block being opened.
   */
  #updateActiveGuide() {
    const lines = this.#lines;
    const n = lines.length;
    const c = this.#curLine;
    const line = lines[c];
    let level = 0;
    let start = 0;
    if (!isBlank(line) && opensBlock(line)) {
      let j = c + 1;
      while (j < n && isBlank(lines[j])) j++;
      const own = indentLevel(line);
      if (j < n && indentLevel(lines[j]) > own) {
        level = own + 1;
        start = c + 1;
      }
    }
    if (!level) {
      if (isBlank(line)) {
        let i = c;
        while (i > 0 && isBlank(lines[i - 1])) i--;
        let j = c + 1;
        while (j < n && isBlank(lines[j])) j++;
        level = this.#blankRunLevel(i, j);
      } else level = indentLevel(line);
      let k = c - 1;
      const stop = Math.max(-1, c - MATCH_SCAN_LINES);
      while (k > stop && (isBlank(lines[k]) || indentLevel(lines[k]) >= level)) k--;
      start = k + 1;
    }
    let last = start - 1;
    if (level) {
      const stop = Math.min(n, start + MATCH_SCAN_LINES);
      for (let k = start; k < stop; k++) {
        if (isBlank(lines[k])) continue;
        if (indentLevel(lines[k]) < level) break;
        last = k;
      }
    }
    const el = this.#aguide;
    if (!level || last < start) {
      if (this.#aguideKey !== -1) {
        this.#aguideKey = -1;
        el.classList.remove('is-on');
      }
      return;
    }
    const key = (start * 4096 + (last - start)) * 64 + level;
    if (key === this.#aguideKey) return;
    this.#aguideKey = key;
    el.style.setProperty('--line', start);
    el.style.setProperty('--len', last - start + 1);
    el.style.setProperty('--col', (level - 1) * INDENT);
    el.classList.add('is-on');
  }

  #indexLines() {
    const lines = this.#lines;
    const n = lines.length;
    if (this.#starts.length < n) this.#starts = new Int32Array(Math.max(n, this.#starts.length * 2));
    const starts = this.#starts;
    let off = 0;
    for (let i = 0; i < n; i++) {
      starts[i] = off;
      off += lines[i].length + 1;
    }
  }

  #lineAt(offset) {
    const starts = this.#starts;
    let lo = 0;
    let hi = this.#lines.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (starts[mid] <= offset) lo = mid;
      else hi = mid - 1;
    }
    return lo;
  }

  /** Line numbers live in fixed 256-number blocks; growing or shrinking edits only the tail. */
  #setLineCount(n) {
    const blocks = this.#numBlocks;
    let count = this.#numCount;
    while (count < n) {
      const b = (count / NUM_BLOCK) | 0;
      if (b === blocks.length) {
        const node = document.createTextNode('');
        this.#nums.appendChild(h('div', null, node));
        blocks.push(node);
      }
      const end = Math.min(n, (b + 1) * NUM_BLOCK);
      blocks[b].appendData(numberRun(count + 1, end, count > b * NUM_BLOCK));
      count = end;
    }
    while (count > n) {
      const b = ((count - 1) / NUM_BLOCK) | 0;
      const first = b * NUM_BLOCK;
      if (n <= first) {
        blocks.pop().parentNode.remove();
        count = first;
      } else {
        blocks[b].data = numberRun(first + 1, n, false);
        count = n;
      }
    }
    this.#numCount = count;
    const digits = Math.max(2, String(n).length);
    if (digits !== this.#digits) {
      this.#digits = digits;
      this.el.style.setProperty('--ce-digits', digits);
    }
  }

  #updateDirty() {
    const dirty = this.#ta.value !== this.#clean;
    if (dirty !== this.#dirty) {
      this.#dirty = dirty;
      this.el.classList.toggle('is-dirty', dirty);
    }
  }

  #clampLine(line) {
    const n = this.#lines.length;
    const v = Math.round(Number(line));
    return (Number.isFinite(v) ? Math.min(Math.max(v, 1), n) : 1) - 1;
  }

  // ── selection-driven decorations ──────────────────────────────────────────────────────

  #syncSelection(force = false) {
    const ta = this.#ta;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    const head = ta.selectionDirection === 'backward' ? s : e;
    if (!force && s === this.#selS && e === this.#selE && head === this.#selHead) return;
    this.#selS = s;
    this.#selE = e;
    this.#selHead = head;

    const line = this.#lineAt(head);
    const lineChanged = line !== this.#curLine;
    if (lineChanged) {
      this.#curLine = line;
      this.#band.style.setProperty('--line', line);
      this.#gcur.style.setProperty('--line', line);
      this.#gcurText.data = String(line + 1);
      if (this.#marks.length) this.#updateOcclusion();
    }
    if (force || lineChanged) this.#updateActiveGuide();
    if (force) {
      this.#heat.style.setProperty('--line', line);
      this.#heat.style.setProperty('--col', visualCol(this.#lines[line], head - this.#starts[line]));
    }
    const hasSel = s !== e;
    if (hasSel !== this.#hasSel) {
      this.#hasSel = hasSel;
      this.el.classList.toggle('has-selection', hasSel);
    }
    this.#matchBrackets(hasSel ? -1 : head, line);
  }

  /** Keyboard navigation keeps a little context around the caret and clear of the gutter. */
  #keepCaretVisible(line, head) {
    const sc = this.#scroller;
    const lh = this.#lh;
    const view = sc.clientHeight;
    const top = sc.scrollTop;
    const y = this.#padT + line * lh;
    const margin = Math.min(lh * 2, Math.max(0, (view - lh) / 2));
    if (y - margin < top) sc.scrollTop = Math.max(0, y - margin);
    else if (y + lh + margin > top + view) sc.scrollTop = y + lh + margin - view;

    const text = this.#lines[line];
    const x = this.#padL + visualCol(text, head - this.#starts[line]) * this.#chW;
    const left = sc.scrollLeft;
    const visible = sc.clientWidth - this.#gutter.offsetWidth;
    if (x < left + this.#chW) sc.scrollLeft = Math.max(0, x - this.#chW * 6);
    else if (x > left + visible - this.#chW * 2) sc.scrollLeft = x - visible + this.#chW * 6;
  }

  #matchBrackets(head, line) {
    let a = -1;
    let b = -1;
    let bLine = -1;
    let bad = false;
    const list = head >= 0 ? this.#brk[line] : null;
    if (list) {
      const col = head - this.#starts[line];
      let hit = -1;
      for (let k = 0; k < list.length; k++) {
        if (list[k] >> 3 === col - 1) {
          hit = k;
          break;
        }
      }
      if (hit < 0) {
        for (let k = 0; k < list.length; k++) {
          if (list[k] >> 3 === col) {
            hit = k;
            break;
          }
        }
      }
      if (hit >= 0) {
        a = list[hit] >> 3;
        if (this.#findMatch(line, hit)) {
          bLine = this.#matchLine;
          b = this.#matchCol;
        } else bad = true;
      }
    }
    this.#placeMatch(this.#matchA, line, a, bad);
    this.#placeMatch(this.#matchB, bLine, b, false);
  }

  /** Same-type depth scan from bracket `idx` on `line`; the partner lands in #matchLine/#matchCol. */
  #findMatch(line, idx) {
    const brk = this.#brk;
    const kind = brk[line][idx] & 7;
    const type = kind >> 1;
    const opening = (kind & 1) === 0;
    let depth = 0;
    const last = opening ? Math.min(brk.length - 1, line + MATCH_SCAN_LINES) : Math.max(0, line - MATCH_SCAN_LINES);
    for (let ln = line; opening ? ln <= last : ln >= last; ln += opening ? 1 : -1) {
      const list = brk[ln];
      if (!list) continue;
      let k = ln === line ? idx + (opening ? 1 : -1) : opening ? 0 : list.length - 1;
      for (; k >= 0 && k < list.length; k += opening ? 1 : -1) {
        const kk = list[k] & 7;
        if (kk >> 1 !== type) continue;
        if ((kk & 1) === (kind & 1)) depth++;
        else if (depth === 0) {
          this.#matchLine = ln;
          this.#matchCol = list[k] >> 3;
          return true;
        } else depth--;
      }
    }
    return false;
  }

  #placeMatch(el, line, col, bad) {
    if (col < 0) {
      if (el.classList.contains('is-on')) el.classList.remove('is-on', 'is-bad');
      return;
    }
    el.style.setProperty('--line', line);
    el.style.setProperty('--col', visualCol(this.#lines[line], col));
    el.classList.add('is-on');
    el.classList.toggle('is-bad', bad);
  }

  // ── error marks ───────────────────────────────────────────────────────────────────────

  #placeMark(m) {
    m.glow.style.setProperty('--line', m.line);
    m.gmark.style.setProperty('--line', m.line);
    m.widget.style.setProperty('--line', m.line);
    m.num.data = String(m.line + 1);
    m.lnLabel.data = `LN ${m.line + 1}`;
    const stale = m.stale;
    m.glow.classList.toggle('is-stale', stale);
    m.gmark.classList.toggle('is-stale', stale);
    m.widget.classList.toggle('is-stale', stale);
    m.rmark.classList.toggle('is-stale', stale);
  }

  #shiftMarks(top, oldEnd, newEnd, delta) {
    const last = this.#lines.length - 1;
    for (const m of this.#marks) {
      let ln = m.line;
      let stale = m.stale;
      if (ln >= oldEnd) ln += delta;
      else if (ln >= top) {
        stale = true;
        ln = Math.max(top, Math.min(ln, newEnd - 1));
      } else continue;
      ln = Math.min(Math.max(ln, 0), last);
      if (ln !== m.line || stale !== m.stale) {
        m.line = ln;
        m.stale = stale;
        this.#placeMark(m);
      }
    }
    this.#marksMoved = true;
  }

  /** Overview-ruler ticks: where each mark sits along the scrollbar track. */
  #layoutMarks() {
    if (!this.#marks.length) return;
    const sc = this.#scroller;
    const total = sc.scrollHeight;
    const track = sc.clientHeight;
    const show = total > track + 1;
    this.#ruler.classList.toggle('is-on', show);
    if (!show) return;
    for (const m of this.#marks) {
      const y = ((this.#padT + (m.line + 0.5) * this.#lh) / total) * track;
      m.rmark.style.transform = `translate3d(0, ${Math.round(y - 1.5)}px, 0)`;
    }
  }

  /**
   * Snap a widget's height to whole lines so it never slices a line of code in half, and
   * remember how many lines it covers.
   */
  #snapWidget(m) {
    const box = m.widget.firstChild;
    box.style.minHeight = '';
    const lh = this.#lh;
    const inset = WIDGET_GAP_TOP + WIDGET_GAP_BOTTOM;
    m.cover = Math.max(1, Math.ceil((box.offsetHeight + inset) / lh));
    box.style.minHeight = `${m.cover * lh - inset}px`;
  }

  /** Fade an error widget while the caret works on the lines it covers. */
  #updateOcclusion() {
    const line = this.#curLine;
    for (const m of this.#marks) {
      const covering = line > m.line && line <= m.line + m.cover;
      m.widget.classList.toggle('is-faded', covering);
    }
  }

  #dropMark(m, instant) {
    const els = [m.glow, m.gmark, m.widget, m.rmark];
    const i = this.#marks.indexOf(m);
    if (instant) {
      if (i >= 0) this.#marks.splice(i, 1);
      for (const el of els) el.remove();
      return;
    }
    if (this.el.classList.contains('ce--still') || !this.el.isConnected || typeof Element.prototype.animate !== 'function') {
      for (const el of els) el.remove();
      return;
    }
    for (const el of els) {
      el.classList.add('is-leaving');
      const anim = el.animate([{ opacity: getComputedStyle(el).opacity }, { opacity: 0 }], {
        duration: 160,
        easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
        fill: 'forwards',
      });
      anim.onfinish = () => el.remove();
      anim.oncancel = () => el.remove();
    }
  }

  /** Scroll so a line sits about a third of the way down the view, if it is not comfortably visible. */
  #revealLine(ln) {
    const sc = this.#scroller;
    const lh = this.#lh;
    const view = sc.clientHeight;
    const y = this.#padT + ln * lh;
    const top = sc.scrollTop;
    if (y < top + lh || y + lh * 4 > top + view) sc.scrollTop = Math.max(0, y - Math.round(view * 0.34));
    const text = this.#lines[ln];
    const x = this.#padL + visualCol(text, leadingWs(text)) * this.#chW;
    const visible = sc.clientWidth - this.#gutter.offsetWidth;
    if (x < sc.scrollLeft || x > sc.scrollLeft + visible - this.#chW * 8) sc.scrollLeft = Math.max(0, x - this.#chW * 4);
  }

  // ── keyboard ──────────────────────────────────────────────────────────────────────────

  #onKeyDown(e) {
    if (e.isComposing || e.keyCode === 229) return;
    this.#navigated = true;
    const mod = e.ctrlKey || e.metaKey;
    const key = e.key;
    let handled = false;

    if (mod && !e.altKey) {
      if (key === 'Enter') {
        this.#flush();
        this.#call(this.#onSubmit);
        handled = true;
      } else if (key === 's' || key === 'S') {
        this.#flush();
        this.#call(this.#onSave);
        handled = true;
      } else if (key === '/' || e.code === 'Slash') {
        handled = this.#toggleComment();
      } else if (key === ']' && !e.shiftKey) {
        handled = this.#shiftLines(1, true);
      } else if (key === '[' && !e.shiftKey) {
        handled = this.#shiftLines(-1, true);
      }
    } else if (!mod && !e.altKey) {
      switch (key) {
        case 'Tab':
          handled = e.shiftKey ? this.#shiftLines(-1, true) : this.#tab();
          break;
        case 'Enter':
          handled = this.#newline();
          break;
        case 'Backspace':
          handled = !e.shiftKey && this.#backspace();
          break;
        case 'Home':
          handled = this.#smartHome(e.shiftKey);
          break;
        case '(':
        case '[':
        case '{':
          handled = this.#openBracket(key);
          break;
        case ')':
        case ']':
        case '}':
          handled = this.#typeOver(key);
          break;
      }
    }
    if (handled) {
      e.preventDefault();
      e.stopPropagation();
    }
  }

  #call(fn) {
    if (typeof fn !== 'function') return;
    try {
      fn();
    } catch (err) {
      console.error('[editor] handler threw', err);
    }
  }

  /**
   * Replace [from, to) with `text` as one native edit (undoable), then select [selS, selE].
   * Falls back to setRangeText (no undo entry) where execCommand is unavailable.
   */
  #replace(from, to, text, selS = from + text.length, selE = selS) {
    const ta = this.#ta;
    if (ta.readOnly) return;
    if (document.activeElement !== ta) ta.focus({ preventScroll: true });
    ta.setSelectionRange(from, to);
    let ok = false;
    try {
      ok = text ? document.execCommand('insertText', false, text) : from === to || document.execCommand('delete', false);
    } catch {
      ok = false;
    }
    if (!ok) {
      ta.setRangeText(text, from, to, 'end');
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    }
    ta.setSelectionRange(Math.min(selS, ta.value.length), Math.min(selE, ta.value.length));
  }

  /** Tab: indent a selection, or insert spaces to the next tab stop. */
  #tab() {
    const ta = this.#ta;
    const s = ta.selectionStart;
    if (s !== ta.selectionEnd) return this.#shiftLines(1, false);
    const v = ta.value;
    const ls = v.lastIndexOf('\n', s - 1) + 1;
    const col = visualCol(v.slice(ls, s), s - ls);
    this.#replace(s, s, ' '.repeat(INDENT - (col % INDENT)));
    return true;
  }

  /** The [first, last) span of whole lines touched by the selection. */
  #selectedLines() {
    const ta = this.#ta;
    const v = ta.value;
    const s = ta.selectionStart;
    let e = ta.selectionEnd;
    // A selection ending at column 0 does not include that line.
    if (e > s && v.charCodeAt(e - 1) === 10) e--;
    const first = v.lastIndexOf('\n', s - 1) + 1;
    let last = v.indexOf('\n', e);
    if (last < 0) last = v.length;
    return { v, s, e: ta.selectionEnd, first, last, dir: ta.selectionDirection };
  }

  /** Indent (+1) or dedent (-1) every selected line by one level as a single undo step. */
  #shiftLines(dir, always) {
    const { v, s, e, first, last } = this.#selectedLines();
    const edits = [];
    let pos = first;
    while (pos <= last) {
      let eol = v.indexOf('\n', pos);
      if (eol < 0 || eol > last) eol = last;
      if (dir > 0) {
        if (eol > pos || (always && s === e)) edits.push({ at: pos, del: 0, ins: TAB });
      } else {
        let r = 0;
        if (v.charCodeAt(pos) === 9) r = 1;
        else while (r < INDENT && pos + r < eol && v.charCodeAt(pos + r) === 32) r++;
        if (r) edits.push({ at: pos, del: r, ins: '' });
      }
      pos = eol + 1;
    }
    if (!edits.length) return true;
    const from = edits[0].at;
    const to = edits[edits.length - 1].at + edits[edits.length - 1].del;
    const block = applyEdits(v, from, to, edits);
    const collapsed = s === e;
    const ns = mapPos(s, edits, !collapsed && s === first);
    const ne = collapsed ? ns : mapPos(e, edits, false);
    this.#replace(from, to, block, ns, ne);
    return true;
  }

  /** Ctrl+/: comment every selected line at their common indent, or uncomment if all are. */
  #toggleComment() {
    const { v, s, e, first, last } = this.#selectedLines();
    const lines = v.slice(first, last).split('\n');
    let minIndent = Infinity;
    let allCommented = true;
    let any = false;
    for (const line of lines) {
      const ws = leadingWs(line);
      if (ws === line.length) continue;
      any = true;
      minIndent = Math.min(minIndent, ws);
      if (line.charCodeAt(ws) !== 35) allCommented = false;
    }
    if (!any) return true;
    const edits = [];
    let pos = first;
    for (const line of lines) {
      const ws = leadingWs(line);
      if (ws < line.length) {
        if (allCommented) {
          const del = line.charCodeAt(ws + 1) === 32 ? 2 : 1;
          edits.push({ at: pos + ws, del, ins: '' });
        } else {
          edits.push({ at: pos + minIndent, del: 0, ins: '# ' });
        }
      }
      pos += line.length + 1;
    }
    const from = edits[0].at;
    const to = edits[edits.length - 1].at + edits[edits.length - 1].del;
    const block = applyEdits(v, from, to, edits);
    const collapsed = s === e;
    const ns = mapPos(s, edits, !collapsed);
    const ne = collapsed ? ns : mapPos(e, edits, false);
    this.#replace(from, to, block, ns, ne);
    return true;
  }

  /** Enter: keep indentation, +1 level after `:` or an open bracket, -1 after return/pass/…. */
  #newline() {
    const ta = this.#ta;
    const v = ta.value;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    const ls = v.lastIndexOf('\n', s - 1) + 1;
    const before = v.slice(ls, s);
    const ws = leadingWs(before);

    // Caret inside the indentation: push the line down without disturbing its indent.
    if (ws === before.length) {
      this.#replace(ls, e, '\n' + before);
      return true;
    }

    let indent = before.slice(0, ws);
    const code = before.slice(0, codeEnd(before)).trimEnd();
    const lastCh = code.charAt(code.length - 1);
    const stmt = code.trimStart();
    if (lastCh === ':') {
      indent += TAB;
    } else if (lastCh in CLOSER) {
      if (v.charAt(e) === CLOSER[lastCh]) {
        // Between a fresh pair: open a block and park the closer on its own line.
        const inner = '\n' + indent + TAB;
        this.#replace(s, e, inner + '\n' + indent, s + inner.length);
        return true;
      }
      indent += TAB;
    } else if (/^(?:return|raise)\b|^(?:pass|break|continue)$/.test(stmt)) {
      indent = indent.slice(0, Math.max(0, indent.length - INDENT));
    }
    this.#replace(s, e, '\n' + indent);
    return true;
  }

  /** Backspace in leading spaces → previous tab stop; between an empty bracket pair → both. */
  #backspace() {
    const ta = this.#ta;
    const s = ta.selectionStart;
    if (s !== ta.selectionEnd || s === 0) return false;
    const v = ta.value;
    const prev = v.charAt(s - 1);
    if (prev in CLOSER && v.charAt(s) === CLOSER[prev]) {
      this.#replace(s - 1, s + 1, '');
      return true;
    }
    const ls = v.lastIndexOf('\n', s - 1) + 1;
    const col = s - ls;
    if (col === 0) return false;
    for (let i = ls; i < s; i++) if (v.charCodeAt(i) !== 32) return false;
    const n = col % INDENT || INDENT;
    this.#replace(s - n, s, '');
    return true;
  }

  /** Home toggles between the first non-blank character and column 0. */
  #smartHome(extend) {
    const ta = this.#ta;
    const v = ta.value;
    const backward = ta.selectionDirection === 'backward';
    const head = backward ? ta.selectionStart : ta.selectionEnd;
    const anchor = backward ? ta.selectionEnd : ta.selectionStart;
    const ls = v.lastIndexOf('\n', head - 1) + 1;
    let le = v.indexOf('\n', ls);
    if (le < 0) le = v.length;
    const fnb = ls + leadingWs(v.slice(ls, le));
    const target = head === fnb || fnb === le ? ls : fnb;
    if (extend) {
      if (target < anchor) ta.setSelectionRange(target, anchor, 'backward');
      else ta.setSelectionRange(anchor, target, 'forward');
    } else {
      ta.setSelectionRange(target, target);
    }
    this.#schedule();
    return true;
  }

  /** Auto-close ( [ { before whitespace/closers/end of line; wrap a selection in the pair. */
  #openBracket(open) {
    const ta = this.#ta;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    const v = ta.value;
    const close = CLOSER[open];
    if (s !== e) {
      if (v.slice(s, e).includes('\n')) return false;
      this.#replace(s, e, open + v.slice(s, e) + close, s + 1, e + 1);
      return true;
    }
    const next = v.charAt(s);
    const okNext = next === '' || /[\s)\]}:,;]/.test(next) || (open === '{' && (next === '"' || next === "'"));
    if (!okNext) return false;
    const ls = v.lastIndexOf('\n', s - 1) + 1;
    const before = v.slice(ls, s);
    if (codeEnd(before) < before.length) return false; // inside a comment
    this.#replace(s, s, open + close, s + 1);
    return true;
  }

  /** Typing a closer right before the same closer steps over it when the line is balanced. */
  #typeOver(close) {
    const ta = this.#ta;
    const s = ta.selectionStart;
    if (s !== ta.selectionEnd) return false;
    const v = ta.value;
    if (v.charAt(s) !== close) return false;
    const open = OPENER[close];
    const ls = v.lastIndexOf('\n', s - 1) + 1;
    let le = v.indexOf('\n', s);
    if (le < 0) le = v.length;
    let balance = 0;
    for (let i = ls; i < le; i++) {
      const ch = v.charAt(i);
      if (ch === open) balance++;
      else if (ch === close) balance--;
    }
    if (balance > 0) return false;
    ta.setSelectionRange(s + 1, s + 1);
    this.#onInput(); // a keystroke all the same: typing sound, no text change
    return true;
  }

  #onPaste(e) {
    const text = e.clipboardData?.getData('text/plain');
    if (!text || !/\r|^[ ]*\t/m.test(text)) return;
    e.preventDefault();
    this.#navigated = true;
    const ta = this.#ta;
    this.#replace(ta.selectionStart, ta.selectionEnd, normalizePaste(text));
  }
}
