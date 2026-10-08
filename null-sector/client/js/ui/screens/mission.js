/**
 * MissionScreen — the combat arena (docs/ARCHITECTURE.md §4.2, §4.4, §5).
 *
 * Layout: a topbar (back · level title · live breach timer vs par · attempt counter · settings)
 * over a three-column grid:
 *   left    briefing tabs (TRANSMISSION / WHY IT MATTERS / FIELD MANUAL) + OBJECTIVES
 *   centre  CodeEditor (file path + save-status chip) + COMBAT LOG / OUTPUT footer
 *   right   TARGET: enemy ASCII art, FIREWALL HP segments, one row per layer, HACK
 *
 * The HACK choreography is a small async script (`#hack` → `#resolve` → `#victory`). Each beat
 * mutates the DOM, then emits a *semantic* bus event with viewport coordinates; the
 * FeedbackDirector turns those into shake, particles, light and sound. Rects are read before
 * classes are written in every beat, so a beat costs at most one layout.
 *
 * Saving: edits autosave 700 ms after the last keystroke; saves are serialised through one
 * promise chain so an old response can never mark newer text as clean. External edits arrive
 * as `server:file`: a clean editor adopts them in place (scroll kept), a dirty one raises a
 * conflict bar (LOAD DISK / KEEP MINE) and autosave holds until the player decides.
 *
 * Restore: RESTORE in the code panel head (or Alt+R, which works from inside the editor, where
 * Tab indents) opens an in-page confirm bar: Cancel is focused, Esc closes it. Confirming runs
 * `api.reset(id)` through the same save chain — so an in-flight autosave can never land on top
 * of the fresh starter — then loads the starter into the editor. The watcher's `server:file`
 * echo of the reset is held while the request flies and dropped once the starter is loaded.
 *
 * Victory: the profile *before* the hack is captured when HACK is pressed, before the request
 * leaves. The server pushes the post-victory profile over SSE (`state`) as soon as it answers,
 * which main.js adopts into ctx.state immediately; reading ctx.state any later would hand the
 * victory screen the new profile as "before" (no XP roll, no IDENTITY REGISTERED).
 *
 * Lifecycle: every listener, interval, timeout and observer is registered through helpers that
 * `exit()` tears down. Pending choreography awaits use tracked timers, so leaving mid-hack
 * simply abandons the script (the `#alive` guard covers the in-flight request).
 */
import { h, inlineCode, escapeHtml, formatTime, rectCenter, nextFrame } from '../dom.js';
import { CodeEditor } from '../editor.js';
import { settings } from '../../core/settings.js';

// ── tuning ──────────────────────────────────────────────────────────────
const AUTOSAVE_MS = 700;
const CHARGE_MS = 460; // minimum charge-up; the request runs concurrently
const LAYER_GAP_MS = 140; // first beat …
const LAYER_GAP_MIN_MS = 110; // … accelerating with the combo down to this
const LAYER_ACCEL_MS = 7;
const INTEL_DELAY_MS = 160;
const VICTORY_BEAT_MS = 380;
const VICTORY_EXIT_MS = 1100;
const DISK_FLASH_MS = 2200;
const LOG_LIMIT = 160;
const CRASH_STATUSES = new Set(['crash', 'syntax_error', 'timeout']);
const ART_ADVANCE = 0.6; // monospace advance / font-size (JetBrains Mono, most fallbacks)
const ART_LINE = 1.08; // must match .enemy__art line-height
const ART_MAX_PX = 34;

const STATUS_LABEL = {
  crash: 'CRASH',
  syntax_error: 'SYNTAX ERROR',
  timeout: 'TIMEOUT',
  harness_error: 'GRADER FAULT',
};

const GRADER_FAULT = 'The grader itself faulted — that is a bug in this level, not in your code. Hack again; if it keeps happening, report it.';

const EMPTY_OUTPUT = {
  none: 'No output yet. Anything your code print()s shows up here.',
  ok: 'Your code ran but printed nothing.',
  crash: 'Your code crashed before printing anything.',
  syntax_error: "Nothing ran — Python couldn't read the file.",
  timeout: 'Nothing came back — the script never finished.',
  harness_error: 'The grader faulted before collecting output.',
};

const SYNC = {
  synced: ['SYNCED', 'chip--ok'],
  dirty: ['UNSAVED', 'chip--warn'],
  saving: ['SAVING…', ''],
  disk: ['SYNCED FROM DISK', 'chip--ok'],
  error: ['SAVE FAILED', 'chip--bad'],
  conflict: ['CONFLICT', 'chip--bad'],
};

// One-shot animations (Web Animations API) — keyframes allocated once.
const EASE_OUT = 'cubic-bezier(0.16, 1, 0.3, 1)';
const SHARD_FRAMES = [
  [
    { transform: 'translate(0,0) rotate(0deg)', opacity: 1 },
    { transform: 'translate(-16px,-22px) rotate(-42deg)', opacity: 0 },
  ],
  [
    { transform: 'translate(0,0) rotate(0deg)', opacity: 1 },
    { transform: 'translate(3px,-30px) rotate(24deg)', opacity: 0 },
  ],
  [
    { transform: 'translate(0,0) rotate(0deg)', opacity: 1 },
    { transform: 'translate(18px,-16px) rotate(52deg)', opacity: 0 },
  ],
];
// `scale` (not `transform`) so it composes with the segment's CSS skew.
const SEG_FLASH = [
  { filter: 'brightness(3.2) saturate(0.4)', scale: '1 1.35' },
  { filter: 'brightness(1)', scale: '1 1' },
];
const SEG_REARM = [
  { opacity: 0, scale: '1 0.2', filter: 'brightness(3)' },
  { opacity: 1, scale: '1 1', filter: 'brightness(1)' },
];
const ROW_BREACH = [
  { backgroundColor: 'rgba(57, 255, 20, 0.22)', transform: 'translateX(6px)' },
  { backgroundColor: 'rgba(57, 255, 20, 0)', transform: 'translateX(0)' },
];
const ROW_BLOCK = [
  { backgroundColor: 'rgba(255, 51, 85, 0.34)', transform: 'translateX(0)' },
  { transform: 'translateX(-5px)', offset: 0.18 },
  { transform: 'translateX(4px)', offset: 0.36 },
  { transform: 'translateX(-2px)', offset: 0.56 },
  { backgroundColor: 'rgba(255, 51, 85, 0)', transform: 'translateX(0)' },
];
const ICON_POP = [
  { transform: 'rotate(45deg) scale(2.1)', filter: 'brightness(2.4)' },
  { transform: 'rotate(45deg) scale(1)', filter: 'brightness(1)' },
];
const ENEMY_HIT = [
  { transform: 'translate(0,0) scale(1)', filter: 'brightness(1)' },
  { transform: 'translate(7px,-3px) scale(1.05)', filter: 'brightness(2.6) saturate(0.6)', offset: 0.14 },
  { transform: 'translate(-4px,2px) scale(0.985)', filter: 'brightness(1.2)', offset: 0.42 },
  { transform: 'translate(0,0) scale(1)', filter: 'brightness(1)' },
];
const ENEMY_GLOAT = [
  { transform: 'scale(1)', filter: 'brightness(1)' },
  { transform: 'scale(1.035)', filter: 'brightness(1.7)', offset: 0.3 },
  { transform: 'scale(1)', filter: 'brightness(1)' },
];
const COMBO_POP = [
  { opacity: 0, transform: 'translate(-50%, 0) scale(1.9)' },
  { opacity: 1, transform: 'translate(-50%, 0) scale(1)', offset: 0.18 },
  { opacity: 1, transform: 'translate(-50%, 0) scale(1)', offset: 0.72 },
  { opacity: 0, transform: 'translate(-50%, -10px) scale(0.96)' },
];
const BRIEF_IN = [{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }];
const PULSE = [{ transform: 'scale(1.18)', filter: 'brightness(2)' }, { transform: 'scale(1)', filter: 'brightness(1)' }];

// ── icons (trusted markup) ──────────────────────────────────────────────
const ICON_BACK =
  '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="square" aria-hidden="true"><path d="M14 5.5 7.5 12 14 18.5"/><path d="M8.5 12H19" opacity=".55"/></svg>';
const ICON_GEAR =
  '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M12 2.6 20.2 7.3v9.4L12 21.4 3.8 16.7V7.3Z"/><circle cx="12" cy="12" r="3.1"/></svg>';
const ICON_FILE =
  '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><path d="M3.5 1.5h5.8l3.2 3.2v9.8h-9Z"/><path d="M9.2 1.6v3.2h3.2"/></svg>';
const ICON_RESTORE =
  '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="square" aria-hidden="true"><path d="M3.2 6.2A5.2 5.2 0 1 1 3 9.6"/><path d="M2.6 2.8v3.6h3.6"/></svg>';

const reduced = () => settings.get('reducedMotion');
const pad2 = (n) => String(Math.max(0, n | 0)).padStart(2, '0');
const levelNumber = (id) => pad2(parseInt(String(id).replace(/\D+/g, ''), 10) || 0);
const isMod = (e) => e.ctrlKey || e.metaKey;

export class MissionScreen {
  el = null;

  #ctx;
  #alive = false;
  #id = '';
  #mission = null;
  #editor = null;

  // lifecycle bookkeeping
  #offs = [];
  #timers = new Set();
  #intervals = new Set();
  #observer = null;

  // save state
  #saveTimer = 0;
  #saveChain = Promise.resolve(true);
  #diskText = '';
  #conflictText = null;
  #syncTimer = 0;
  #lastExplicitSave = 0;

  // combat state
  #busy = false;
  #leaving = false;
  #restoring = false;
  #restoreEcho = null; // a `server:file` that arrived while a restore was in flight
  #attempts = 0;
  #rows = []; // {el, icon, state, intelMsg, intelHint, seg, shards, objective}
  #artLines = [];
  #artCols = 0;
  #animations = new Set();

  // timer state
  #elapsedBase = 0;
  #clockStart = 0;
  #clockRunning = false;
  #shownSecond = -1;
  #timerPhase = '';

  // element refs
  #r = {};

  constructor(ctx) {
    this.#ctx = ctx;
  }

  // ── lifecycle ───────────────────────────────────────────────────────

  async enter(params = {}) {
    const ctx = this.#ctx;
    this.#alive = true;
    this.#leaving = false;
    this.#busy = false;
    this.#id = params.id;
    this.#r = {};
    this.#rows = [];
    this.#briefIndex = -1;
    this.#timerPhase = '';
    this.#conflictText = null;
    this.#restoring = false;
    this.#restoreEcho = null;
    this.#saveChain = Promise.resolve(true);
    // screen--staged: the glass panels fade themselves (.rise) so backdrop blur never drops out.
    this.el = h('section', { class: 'screen screen--mission screen--staged', 'aria-label': 'Mission' });

    let mission;
    try {
      mission = await ctx.api.deploy(this.#id);
    } catch (err) {
      if (!this.#alive) return;
      ctx.toast?.(`DEPLOY FAILED — ${err?.message || 'link lost'}`, { kind: 'error' });
      ctx.bus.emit('ui:error', {});
      this.#later(() => this.#alive && ctx.screens.go('hub'), 60);
      return;
    }
    if (!this.#alive) return;
    this.#mission = mission;
    this.#attempts = mission.attempts || 0;
    this.#diskText = mission.source ?? '';

    this.#build(mission);

    this.#editor = new CodeEditor(this.#r.editorHost, {
      bus: ctx.bus,
      onChange: () => this.#onEdit(),
      onSubmit: () => this.#hack(),
      onSave: () => this.#saveNow(),
    });
    this.#editor.setValue(this.#diskText, { silent: true });
    this.#editor.markClean();
    this.#setSync('synced');

    this.#startClock(mission);
    this.#offs.push(ctx.bus.on('server:file', (data) => this.#onDiskFile(data)));

    if (typeof ResizeObserver === 'function') {
      this.#observer = new ResizeObserver((entries) => {
        const box = entries[entries.length - 1].contentRect;
        this.#fitArt(box.width, box.height);
      });
      this.#observer.observe(this.#r.stage);
    }

    ctx.bus.emit('mood', { name: 'mission' });
    ctx.renderer?.setFocus?.(0.6);

    // Focus the editor once the screen is in the document and visible.
    nextFrame().then(() => {
      if (this.#alive && this.el.isConnected && !this.#busy) this.#editor?.focus();
    });
  }

  async exit() {
    this.#alive = false;
    // Never lose work: capture a pending autosave (unless a conflict is waiting on the player)…
    const editor = this.#editor;
    // (A confirmed restore in flight means the player chose to discard that text.)
    const unsaved =
      editor && !this.#restoring && this.#conflictText === null && (this.#saveTimer || editor.dirty) && editor.value !== this.#diskText
        ? editor.value
        : null;
    // …tear everything down synchronously…
    clearTimeout(this.#saveTimer);
    this.#saveTimer = 0;
    for (const off of this.#offs) off();
    this.#offs.length = 0;
    for (const t of this.#timers) clearTimeout(t);
    this.#timers.clear();
    for (const t of this.#intervals) clearInterval(t);
    this.#intervals.clear();
    for (const a of this.#animations) a.cancel();
    this.#animations.clear();
    this.#observer?.disconnect();
    this.#observer = null;
    this.#editor?.destroy();
    this.#editor = null;
    this.#rows = [];
    // …then flush it (the manager allows exit() a short grace period).
    if (unsaved !== null) {
      try {
        await this.#ctx.api.saveSource(this.#id, unsaved);
      } catch {
        /* the server is unreachable; main.js shows the link-lost banner */
      }
    }
  }

  onKey(e) {
    if (!this.#mission || e.defaultPrevented) return false;
    if (e.key === 'Escape' && this.#restoreOpen()) {
      e.preventDefault();
      if (!this.#restoring) this.#cancelRestore(true);
      return true;
    }
    if (isMod(e) && e.key === 'Enter') {
      e.preventDefault();
      this.#hack();
      return true;
    }
    if (isMod(e) && !e.altKey && (e.key === 's' || e.key === 'S')) {
      e.preventDefault();
      this.#saveNow();
      return true;
    }
    // Alt+R (by code: Option+R types "®" on macOS). The editor traps Tab, so this is the
    // keyboard way to the restore bar from inside it.
    if (e.altKey && !isMod(e) && !e.shiftKey && e.code === 'KeyR' && !e.repeat) {
      e.preventDefault();
      this.#askRestore();
      return true;
    }
    return false;
  }

  // ── DOM ─────────────────────────────────────────────────────────────

  #build(m) {
    const r = this.#r;
    const sector = m.sector || {};
    const sectorColor = /^#[0-9a-f]{6}$/i.test(sector.color || '') ? sector.color : '';

    // topbar
    r.timer = h('span', { class: 'mission-timer__value mono' }, formatTime(m.elapsed || 0));
    r.timerNote = h('span', { class: 'mission-timer__note label' });
    r.timerMeter = h('div', { class: 'meter mission-timer__meter' }, h('div', { class: 'meter__fill' }));
    r.attempts = h('span', { class: 'mission-attempts__value mono' }, pad2(this.#attempts));

    const topbar = h(
      'header',
      { class: 'topbar mission-topbar rise', style: '--i: 0' },
      h(
        'div',
        { class: 'topbar__left' },
        h('button', {
          class: 'icon-btn',
          type: 'button',
          title: 'Back to hub',
          'aria-label': 'Back to hub',
          html: ICON_BACK,
          onclick: () => this.#goHub(),
        }),
        h(
          'div',
          { class: 'mission-title', style: sectorColor ? `--sector: ${sectorColor}` : undefined },
          h(
            'div',
            { class: 'mission-title__main' },
            h('span', { class: 'mission-title__level' }, `LEVEL ${levelNumber(m.id)}`),
            h('span', { class: 'mission-title__sep' }, '//'),
            h('span', { class: 'mission-title__name' }, m.title),
          ),
          h(
            'div',
            { class: 'mission-title__sub' },
            h('span', { class: 'mission-title__sector' }, `SECTOR ${sector.name || ''}`),
            h('span', { class: 'mission-title__concept' }, m.concept),
          ),
        ),
      ),
      h(
        'div',
        { class: 'topbar__center' },
        h(
          'div',
          { class: 'mission-timer', role: 'timer', 'aria-label': 'Breach time' },
          h(
            'div',
            { class: 'mission-timer__row' },
            h('span', { class: 'label' }, m.cleared ? 'BREACHED IN' : 'BREACH TIME'),
            r.timer,
            h('span', { class: 'mission-timer__par mono' }, `/ ${formatTime(m.par_seconds || 0)} PAR`),
          ),
          r.timerMeter,
          r.timerNote,
        ),
      ),
      h(
        'div',
        { class: 'topbar__right' },
        h('div', { class: 'mission-attempts' }, h('span', { class: 'label' }, 'ATTEMPT'), r.attempts),
        h('button', {
          class: 'icon-btn icon-btn--gear',
          type: 'button',
          title: 'Settings (Esc)',
          'aria-label': 'Settings',
          'data-action': 'settings',
          html: ICON_GEAR,
        }),
      ),
    );

    const grid = h('div', { class: 'mission-grid' }, this.#buildBrief(m), this.#buildCode(m), this.#buildTarget(m));
    this.el.append(topbar, grid);
  }

  #buildBrief(m) {
    const r = this.#r;
    // [label, short label for narrow layouts, html]
    const tabs = [
      ['TRANSMISSION', 'COMMS', m.briefing_html],
      ['WHY IT MATTERS', 'WHY', m.why_html],
      ['FIELD MANUAL', 'MANUAL', m.manual_html],
    ];
    r.rich = h('div', { class: 'rich mission-brief__rich', role: 'tabpanel' });
    r.richScroll = h('div', { class: 'scroll mission-brief__scroll' }, r.rich);
    r.briefTabs = tabs.map(([label, short, html], i) =>
      h(
        'button',
        {
          class: 'mission-tab',
          type: 'button',
          role: 'tab',
          title: label,
          'aria-label': label,
          'aria-selected': 'false',
          'data-sfx': '',
          onclick: () => this.#selectBrief(i, html, true),
        },
        h('span', { class: 'mission-tab__full' }, label),
        h('span', { class: 'mission-tab__short', 'aria-hidden': 'true' }, short),
      ),
    );
    this.#briefHtml = tabs.map((t) => t[2] || '');
    this.#selectBrief(0, tabs[0][2], false);

    r.objCount = h('span', { class: 'mono mission-objectives__count' }, `0/${(m.objectives || []).length}`);
    r.objectives = (m.objectives || []).map((name, i) =>
      h(
        'li',
        { class: 'objective' },
        h('span', { class: 'objective__index mono' }, pad2(i + 1)),
        h('span', { class: 'objective__name', html: inlineCode(name) }),
        h('span', { class: 'objective__mark', 'aria-hidden': 'true' }),
      ),
    );

    return h(
      'aside',
      { class: 'panel mission-brief rise', style: '--i: 1' },
      h('div', { class: 'panel__head mission-brief__head', role: 'tablist' }, r.briefTabs),
      h('div', { class: 'panel__body mission-brief__body' }, r.richScroll),
      h(
        'div',
        { class: 'mission-objectives' },
        h('div', { class: 'mission-objectives__head' }, h('span', { class: 'label' }, 'OBJECTIVES'), r.objCount),
        h('ol', { class: 'mission-objectives__list scroll' }, r.objectives),
      ),
    );
  }

  #briefHtml = [];
  #briefIndex = -1;

  #selectBrief(index, html, animate) {
    const r = this.#r;
    if (index === this.#briefIndex) return;
    this.#briefIndex = index;
    r.briefTabs.forEach((tab, i) => {
      tab.classList.toggle('is-active', i === index);
      tab.setAttribute('aria-selected', String(i === index));
    });
    r.rich.innerHTML = html || this.#briefHtml[index] || '';
    r.richScroll.scrollTop = 0;
    if (animate && !reduced()) {
      this.#anim(r.rich, BRIEF_IN, { duration: 220, easing: EASE_OUT });
    }
  }

  #buildCode(m) {
    const r = this.#r;
    r.sync = h('span', { class: 'chip mission-sync', role: 'status' }, 'SYNCED');
    r.editorHost = h('div', { class: 'mission-editor' });
    r.conflict = h('div', { class: 'mission-conflict', hidden: true });
    r.restore = h(
      'button',
      {
        class: 'btn btn--ghost mission-restore',
        type: 'button',
        title: 'Restore the original starter code · Alt+R',
        'aria-label': 'Restore starter code (Alt+R)',
        'aria-keyshortcuts': 'Alt+R',
        'aria-controls': 'mission-restore-bar',
        'aria-expanded': 'false',
        onclick: () => this.#askRestore(),
      },
      h('span', { class: 'mission-restore__icon', html: ICON_RESTORE }),
      h('span', { class: 'mission-restore__label' }, 'Restore'),
    );
    r.restoreBar = this.#buildRestoreBar(m);

    r.logTabs = ['COMBAT LOG', 'OUTPUT'].map((label, i) =>
      h(
        'button',
        { class: 'mission-tab', type: 'button', role: 'tab', 'data-sfx': '', onclick: () => this.#showLog(i === 0 ? 'combat' : 'output') },
        label,
        i === 1 ? h('span', { class: 'mission-tab__badge', 'aria-hidden': 'true' }) : null,
      ),
    );
    r.log = h(
      'div',
      { class: 'mission-log__feed', role: 'log', 'aria-live': 'polite' },
      h(
        'div',
        { class: 'log-line log-line--sys' },
        h('span', { class: 'log-line__tag' }, 'SYS'),
        h('span', {
          html: `Target acquired: <b>${escapeHtml(m.enemy || 'UNKNOWN')}</b>. Write your payload, then <span class="log-line__keys"><b>HACK</b> <span class="kbd">Ctrl</span><span class="kbd">↵</span></span>`,
        }),
      ),
    );
    r.stdout = h('pre', { class: 'mission-log__stdout' });
    r.logCombat = h('div', { class: 'mission-log__pane scroll' }, r.log);
    r.logOutput = h('div', { class: 'mission-log__pane scroll', hidden: true }, r.stdout);
    this.#setOutput(null);

    const panel = h(
      'main',
      { class: 'panel mission-code rise', style: '--i: 2' },
      h(
        'div',
        { class: 'panel__head mission-code__head' },
        h('span', { class: 'mission-code__file mono', title: m.file }, h('span', { html: ICON_FILE }), m.file),
        h('div', { class: 'mission-code__tools' }, r.restore, r.sync),
      ),
      h('div', { class: 'panel__body mission-code__body' }, r.editorHost, r.conflict, r.restoreBar, h('div', { class: 'mission-code__scan', 'aria-hidden': 'true' })),
      h(
        'footer',
        { class: 'mission-log' },
        h('div', { class: 'mission-log__tabs', role: 'tablist' }, r.logTabs),
        r.logCombat,
        r.logOutput,
      ),
    );
    this.#showLog('combat');
    return panel;
  }

  #buildTarget(m) {
    const r = this.#r;
    const art = String(m.enemy_art || '').replace(/\s+$/, '');
    this.#artLines = art ? art.split('\n') : [];
    this.#artCols = this.#artLines.reduce((n, line) => Math.max(n, Array.from(line).length), 0);

    r.art = h('pre', { class: 'enemy__art', 'data-art': art, 'aria-hidden': 'true' }, art);
    r.enemyBody = h('div', { class: 'enemy__body' }, r.art);
    r.combo = h('div', { class: 'enemy__combo', 'aria-hidden': 'true' }, h('b', { class: 'mono' }, '×2'), h('span', { class: 'label' }, 'CHAIN'));
    r.stage = h(
      'div',
      { class: 'enemy' },
      h('div', { class: 'enemy__grid', 'aria-hidden': 'true' }),
      h('div', { class: 'enemy__aura', 'aria-hidden': 'true' }),
      r.enemyBody,
      h('div', { class: 'enemy__scan', 'aria-hidden': 'true' }),
      h('span', { class: 'enemy__corner enemy__corner--tl' }),
      h('span', { class: 'enemy__corner enemy__corner--tr' }),
      h('span', { class: 'enemy__corner enemy__corner--bl' }),
      h('span', { class: 'enemy__corner enemy__corner--br' }),
      h(
        'div',
        { class: 'enemy__readout mono', 'aria-hidden': 'true' },
        h('span', {}, `PID ${pidOf(m.enemy)}`),
        h('span', { class: 'enemy__readout-rule' }),
        h('span', {}, 'THREAT: HOSTILE', h('span', { class: 'enemy__readout-extra' }, ` · ${(m.objectives || []).length} LAYERS`)),
      ),
      r.combo,
    );

    const total = (m.objectives || []).length;
    r.hpCount = h('span', { class: 'mono hp__count' }, `${total}/${total}`);
    r.hpTrack = h('div', { class: 'hp__track' });
    r.layers = h('ol', { class: 'layers scroll' });

    this.#rows = (m.objectives || []).map((name, i) => {
      const shards = [h('i', { class: 'hp__shard hp__shard--0' }), h('i', { class: 'hp__shard hp__shard--1' }), h('i', { class: 'hp__shard hp__shard--2' })];
      const seg = h('span', { class: 'hp__seg' }, shards);
      r.hpTrack.append(seg);
      const icon = h('span', { class: 'layer__icon', 'aria-hidden': 'true' });
      const state = h('span', { class: 'layer__state' }, 'QUEUED');
      const intelMsg = h('p', { class: 'layer__intel-msg' });
      const intelHint = h('p', { class: 'layer__intel-hint' });
      const intel = h(
        'div',
        { class: 'layer__intel' },
        h(
          'div',
          { class: 'layer__intel-inner' },
          h('div', { class: 'layer__intel-card' }, h('span', { class: 'label layer__intel-tag' }, 'INTEL'), intelMsg, intelHint),
        ),
      );
      const el = h(
        'li',
        { class: 'layer is-queued' },
        h('div', { class: 'layer__row' }, icon, h('span', { class: 'layer__index mono' }, pad2(i + 1)), h('span', { class: 'layer__name', html: inlineCode(name) }), state),
        intel,
      );
      r.layers.append(el);
      return { el, icon, state, intelMsg, intelHint, seg, shards, objective: r.objectives[i] };
    });

    r.hackLabel = h('span', { class: 'hack-btn__label' }, 'HACK');
    r.hackSub = h('span', { class: 'hack-btn__sub label' }, 'INJECT PAYLOAD');
    r.hack = h(
      'button',
      { class: 'btn btn--primary btn--lg hack-btn', type: 'button', onclick: () => this.#hack() },
      h('span', { class: 'hack-btn__fill', 'aria-hidden': 'true' }),
      h('span', { class: 'hack-btn__text' }, r.hackLabel, r.hackSub),
      h('span', { class: 'hack-btn__keys' }, h('span', { class: 'kbd' }, 'Ctrl'), h('span', { class: 'kbd' }, '↵')),
    );

    return h(
      'aside',
      { class: 'panel mission-target rise', style: '--i: 3' },
      h(
        'div',
        { class: 'panel__head mission-target__head' },
        h('span', { class: 'label' }, 'TARGET'),
        h('span', { class: 'mission-target__live' }, h('i'), 'LIVE'),
        // panel__title is inline-flex (no text-overflow), so the name ellipsizes in its own span.
        h('span', { class: 'panel__title mission-target__name', title: m.enemy || '' }, h('span', { class: 'mission-target__name-text' }, m.enemy || 'UNKNOWN')),
      ),
      h(
        'div',
        { class: 'panel__body mission-target__body' },
        r.stage,
        h('div', { class: 'hp' }, h('div', { class: 'hp__head' }, h('span', { class: 'label' }, 'FIREWALL'), r.hpCount), r.hpTrack),
        r.layers,
      ),
      h('div', { class: 'mission-target__foot' }, r.hack),
    );
  }

  /** Scale the enemy art to fill its stage (ResizeObserver; no layout reads). */
  #fitArt(width, height) {
    if (!this.#artCols || !this.#artLines.length || width <= 0 || height <= 0) return;
    const byWidth = (width * 0.8) / (this.#artCols * ART_ADVANCE);
    const byHeight = (height * 0.72) / (this.#artLines.length * ART_LINE);
    const size = Math.max(8, Math.min(ART_MAX_PX, byWidth, byHeight));
    this.#r.art.style.setProperty('--art-size', `${size.toFixed(2)}px`);
  }

  // ── breach timer ────────────────────────────────────────────────────

  #startClock(m) {
    this.#elapsedBase = Number(m.elapsed) || 0;
    this.#clockStart = performance.now();
    this.#clockRunning = !m.cleared;
    this.#shownSecond = -1;
    this.#tickClock();
    if (this.#clockRunning) this.#every(() => this.#tickClock(), 250);
    if (m.cleared) this.#r.timer.closest('.mission-timer').classList.add('is-cleared');
  }

  #elapsed() {
    return this.#clockRunning ? this.#elapsedBase + (performance.now() - this.#clockStart) / 1000 : this.#elapsedBase;
  }

  #tickClock() {
    const m = this.#mission;
    if (!m) return;
    const seconds = Math.floor(this.#elapsed());
    if (seconds === this.#shownSecond) return;
    this.#shownSecond = seconds;
    const r = this.#r;
    r.timer.textContent = formatTime(seconds);
    const par = m.par_seconds || 0;
    const ratio = par > 0 ? seconds / par : 0;
    r.timerMeter.style.setProperty('--value', String(Math.min(1, ratio)));
    if (m.cleared) return;
    const phase = ratio >= 1 ? 'over' : ratio >= 0.75 ? 'warn' : 'ok';
    if (phase !== this.#timerPhase) {
      const box = r.timer.closest('.mission-timer');
      box.classList.toggle('is-warn', phase === 'warn');
      box.classList.toggle('is-over', phase === 'over');
      r.timerNote.textContent = phase === 'over' ? 'SPEED BONUS LOST' : phase === 'warn' ? 'PAR WINDOW CLOSING' : '';
      if (this.#timerPhase && phase === 'over') this.#ctx.bus.emit('ui:error', {});
      this.#timerPhase = phase;
    }
  }

  #stopClock() {
    this.#elapsedBase = this.#elapsed();
    this.#clockRunning = false;
  }

  // ── saving ──────────────────────────────────────────────────────────

  #onEdit() {
    if (!this.#alive) return;
    this.#setSync(this.#conflictText !== null ? 'conflict' : 'dirty');
    clearTimeout(this.#saveTimer);
    this.#saveTimer = 0;
    if (this.#conflictText !== null) return; // hold autosave until the conflict is resolved
    this.#saveTimer = this.#later(() => {
      this.#saveTimer = 0;
      this.#save();
    }, AUTOSAVE_MS);
  }

  /** Ctrl+S: save immediately with audible confirmation. */
  #saveNow() {
    const now = performance.now();
    if (now - this.#lastExplicitSave < 150) return; // editor + global handler on one keypress
    this.#lastExplicitSave = now;
    if (this.#conflictText !== null) this.#hideConflict();
    this.#ctx.bus.emit('ui:save', {});
    this.#save(true).then((ok) => {
      if (ok && this.#alive && !reduced()) this.#anim(this.#r.sync, PULSE, { duration: 360, easing: EASE_OUT });
    });
  }

  /** Queue a save of the editor's current text. Resolves true once the disk has it. */
  #save(force = false) {
    clearTimeout(this.#saveTimer);
    this.#saveTimer = 0;
    this.#saveChain = this.#saveChain.then(() => this.#doSave(force));
    return this.#saveChain;
  }

  async #doSave(force) {
    const editor = this.#editor;
    if (!editor || !this.#alive) return true;
    const text = editor.value;
    if (!force && text === this.#diskText) {
      editor.markClean();
      if (this.#conflictText === null) this.#setSync('synced');
      return true;
    }
    this.#setSync('saving');
    try {
      await this.#ctx.api.saveSource(this.#id, text);
    } catch (err) {
      if (!this.#alive) return false;
      this.#setSync('error');
      this.#ctx.toast?.(`SAVE FAILED — ${err?.message || 'link lost'}`, { kind: 'error' });
      this.#ctx.bus.emit('ui:error', {});
      return false;
    }
    this.#diskText = text;
    if (!this.#alive || !this.#editor) return true;
    if (this.#editor.value === text) {
      this.#editor.markClean();
      if (this.#conflictText === null) this.#setSync('synced');
    }
    return true;
  }

  #setSync(kind) {
    const chip = this.#r.sync;
    if (!chip) return;
    const [text, mod] = SYNC[kind] || SYNC.synced;
    chip.className = `chip mission-sync${mod ? ` ${mod}` : ''} is-${kind}`;
    chip.textContent = text;
    clearTimeout(this.#syncTimer);
    this.#syncTimer = 0;
    if (kind === 'disk') {
      this.#syncTimer = this.#later(() => {
        if (this.#editor && !this.#editor.dirty) this.#setSync('synced');
      }, DISK_FLASH_MS);
    }
  }

  #onDiskFile(data) {
    if (!this.#alive || !data || data.mission !== this.#id || typeof data.source !== 'string' || !this.#editor) return;
    if (this.#restoring) {
      // Most likely the watcher seeing our own reset: the response loads it. Kept in case the
      // restore fails, so a real external edit is still offered afterwards.
      this.#restoreEcho = data;
      return;
    }
    const disk = data.source;
    const editor = this.#editor;
    if (disk === editor.value) {
      this.#diskText = disk;
      if (this.#conflictText !== null) this.#hideConflict();
      editor.markClean();
      this.#setSync('synced');
      return;
    }
    if (!editor.dirty && !this.#saveTimer && this.#conflictText === null) {
      this.#adoptDisk(disk);
      return;
    }
    this.#showConflict(disk);
  }

  #adoptDisk(disk) {
    const editor = this.#editor;
    clearTimeout(this.#saveTimer);
    this.#saveTimer = 0;
    editor.setValue(disk, { silent: true }); // CodeEditor keeps scroll + caret across setValue
    editor.markClean();
    editor.clearMarks();
    this.#diskText = disk;
    this.#setSync('disk');
    this.#log('sys', 'SYS', 'Mission file changed on disk — editor synced.');
    if (!reduced()) this.#anim(this.#r.sync, PULSE, { duration: 420, easing: EASE_OUT });
  }

  #showConflict(disk) {
    const r = this.#r;
    const first = this.#conflictText === null;
    this.#conflictText = disk;
    clearTimeout(this.#saveTimer);
    this.#saveTimer = 0;
    this.#setSync('conflict');
    if (!first) return;
    r.conflict.replaceChildren(
      h('span', { class: 'mission-conflict__icon', 'aria-hidden': 'true' }, '!'),
      h(
        'div',
        { class: 'mission-conflict__text' },
        h('strong', {}, 'FILE CHANGED ON DISK'),
        h('span', {}, 'Your unsaved edits differ from the file on disk.'),
      ),
      h('button', { class: 'btn btn--ghost', type: 'button', onclick: () => this.#resolveConflict('disk') }, 'LOAD DISK'),
      h('button', { class: 'btn', type: 'button', onclick: () => this.#resolveConflict('mine') }, 'KEEP MINE'),
    );
    r.conflict.hidden = false;
    r.conflict.classList.remove('is-out');
    this.#ctx.bus.emit('ui:open', {});
  }

  #hideConflict() {
    const el = this.#r.conflict;
    this.#conflictText = null;
    if (!el || el.hidden) return;
    el.classList.add('is-out');
    this.#later(() => {
      if (this.#conflictText === null) el.hidden = true;
    }, 220);
  }

  #resolveConflict(choice) {
    const disk = this.#conflictText;
    if (disk === null) return;
    this.#hideConflict();
    if (choice === 'disk') this.#adoptDisk(disk);
    else this.#save(true);
  }

  // ── restore starter code ────────────────────────────────────────────

  #buildRestoreBar(m) {
    const r = this.#r;
    r.restoreGo = h(
      'button',
      { class: 'btn btn--primary btn--danger mission-restore-bar__go', type: 'button', onclick: () => this.#restore() },
      'Restore starter',
    );
    r.restoreCancel = h(
      'button',
      { class: 'btn btn--ghost mission-restore-bar__cancel', type: 'button', onclick: () => this.#cancelRestore(true) },
      'Cancel',
      h('span', { class: 'kbd' }, 'Esc'),
    );
    const file = String(m.file || '').split('/').pop() || 'this file';
    return h(
      'div',
      {
        class: 'mission-restore-bar',
        id: 'mission-restore-bar',
        role: 'alertdialog',
        'aria-modal': 'false',
        'aria-labelledby': 'mission-restore-title',
        'aria-describedby': 'mission-restore-text',
        hidden: true,
      },
      h('span', { class: 'mission-restore-bar__icon', 'aria-hidden': 'true', html: ICON_RESTORE }),
      h(
        'div',
        { class: 'mission-restore-bar__text' },
        h('strong', { id: 'mission-restore-title' }, 'RESTORE STARTER CODE?'),
        h('span', { id: 'mission-restore-text', html: `Replaces everything in <code>${escapeHtml(file)}</code> with the original starter. Your current code cannot be recovered.` }),
      ),
      h('div', { class: 'mission-restore-bar__actions' }, r.restoreGo, r.restoreCancel),
    );
  }

  #restoreOpen() {
    const bar = this.#r.restoreBar;
    return !!bar && !bar.hidden && !bar.classList.contains('is-out');
  }

  #askRestore() {
    const r = this.#r;
    if (!this.#alive || this.#busy || this.#leaving || this.#restoring || !this.#editor) return;
    if (this.#restoreOpen()) {
      r.restoreCancel.focus();
      return;
    }
    r.restoreBar.hidden = false;
    r.restoreBar.classList.remove('is-out', 'is-working');
    r.restoreGo.disabled = false;
    r.restoreCancel.disabled = false;
    r.restoreGo.textContent = 'Restore starter';
    r.restore.setAttribute('aria-expanded', 'true');
    r.restore.classList.add('is-on');
    this.#ctx.bus.emit('ui:open', {});
    r.restoreCancel.focus({ preventScroll: true }); // the safe choice is the default one
  }

  /** `refocus`: return focus to the RESTORE button (keyboard flow) instead of leaving it. */
  #cancelRestore(refocus = false) {
    const r = this.#r;
    if (!r.restoreBar || r.restoreBar.hidden) return;
    const hadFocus = r.restoreBar.contains(document.activeElement);
    this.#closeRestoreBar();
    this.#ctx.bus.emit('ui:close', {});
    if (refocus && hadFocus && this.#alive) r.restore.focus({ preventScroll: true });
  }

  #closeRestoreBar() {
    const r = this.#r;
    const bar = r.restoreBar;
    r.restore?.setAttribute('aria-expanded', 'false');
    r.restore?.classList.remove('is-on');
    if (!bar || bar.hidden) return;
    bar.classList.add('is-out');
    this.#later(() => {
      if (bar.classList.contains('is-out')) bar.hidden = true;
    }, 200);
  }

  /** Confirmed: reset the file on disk, then load the starter into the editor. */
  #restore() {
    const r = this.#r;
    if (!this.#alive || this.#busy || this.#leaving || this.#restoring || !this.#editor) return;
    this.#restoring = true;
    r.restoreGo.disabled = true;
    r.restoreCancel.disabled = true;
    r.restoreGo.textContent = 'Restoring…';
    r.restoreBar.classList.add('is-working');
    r.restore.disabled = true;
    r.hack.disabled = true;
    // Drop the pending autosave: the starter replaces that text anyway. Queue behind any save
    // already in flight, so it cannot overwrite the restored file after the reset lands.
    clearTimeout(this.#saveTimer);
    this.#saveTimer = 0;
    this.#saveChain = this.#saveChain.then(() => this.#doRestore());
    return this.#saveChain;
  }

  async #doRestore() {
    const ctx = this.#ctx;
    let source;
    try {
      const result = await ctx.api.reset(this.#id);
      if (!result || typeof result.source !== 'string') throw new Error('malformed response');
      source = result.source;
    } catch (err) {
      if (!this.#alive) return false;
      this.#restoring = false;
      this.#restoreControls();
      this.#closeRestoreBar();
      ctx.toast?.(`RESTORE FAILED — ${err?.message || 'link lost'}`, { kind: 'error' });
      ctx.bus.emit('ui:error', {});
      this.#log('bad', 'SYS', `Restore failed: ${err?.message || 'link lost'}. Your code was not changed.`);
      const echo = this.#restoreEcho;
      this.#restoreEcho = null;
      if (echo) this.#onDiskFile(echo); // the file did change on disk: treat it as an external edit
      if (this.#editor && document.activeElement === document.body) this.#editor.focus();
      return false;
    }
    if (!this.#alive || !this.#editor) return true;
    const editor = this.#editor;
    clearTimeout(this.#saveTimer); // keystrokes typed while the request flew are replaced too
    this.#saveTimer = 0;
    if (this.#conflictText !== null) this.#hideConflict();
    editor.setValue(source, { silent: true });
    editor.markClean();
    editor.clearMarks();
    this.#diskText = source;
    this.#setSync('synced');
    this.#restoring = false;
    const echo = this.#restoreEcho;
    this.#restoreEcho = null;
    if (echo && echo.source !== source) this.#onDiskFile(echo); // a later external edit still counts
    this.#restoreControls();
    this.#closeRestoreBar();
    this.#log('sys', 'SYS', 'Starter code restored — the mission file is back to its original state.');
    ctx.toast?.('Starter code restored. The mission file is back to its original state.', { kind: 'ok', title: 'RESTORED', ms: 2800 });
    ctx.bus.emit('ui:save', {});
    if (!reduced()) this.#anim(this.#r.sync, PULSE, { duration: 420, easing: EASE_OUT });
    editor.focus();
    return true;
  }

  /** Re-enable RESTORE / HACK after a restore, unless a hack started meanwhile. */
  #restoreControls() {
    const r = this.#r;
    if (!r.restore) return;
    const idle = r.hack?.dataset.state === 'idle' || !r.hack?.dataset.state;
    r.restore.disabled = !idle || this.#leaving;
    if (r.hack && idle) r.hack.disabled = false;
  }

  // ── navigation ──────────────────────────────────────────────────────

  #goHub() {
    if (this.#leaving) return;
    this.#leaving = true;
    this.#ctx.screens.go('hub');
  }

  // ── HACK choreography ───────────────────────────────────────────────

  async #hack() {
    if (this.#busy || this.#leaving || this.#restoring || !this.#alive || !this.#editor) return;
    this.#busy = true;
    const ctx = this.#ctx;
    const r = this.#r;
    // The profile as it was before this hack: captured now, before the request leaves, because
    // the server's SSE `state` push replaces ctx.state with the post-victory profile the moment
    // it answers. It lets the victory screen roll the XP meter over a rank-up and tell a newly
    // registered callsign from a known one.
    const before = ctx.state?.profile && typeof ctx.state.profile === 'object' ? { ...ctx.state.profile } : null;

    if (this.#conflictText !== null) this.#hideConflict(); // hacking means "my code"
    if (this.#restoreOpen()) this.#cancelRestore(false); // …and not the starter
    this.#setButton('saving');
    if (this.#saveTimer || this.#editor.dirty || this.#editor.value !== this.#diskText) {
      const ok = await this.#save();
      if (!this.#alive) return;
      if (!ok) {
        this.#setButton('idle');
        this.#busy = false;
        return;
      }
    }

    this.#editor.clearMarks();
    this.#resetBattle();
    this.#setButton('charging');
    this.el.classList.add('is-charging');
    this.#logAttemptHead(this.#attempts + 1);

    const from = rectCenter(r.editorHost);
    const to = rectCenter(r.art);
    ctx.bus.emit('hack:charge', { x: from.x, y: from.y, tx: to.x, ty: to.y });

    const request = ctx.api.hack(this.#id).then(
      (result) => ({ result }),
      (error) => ({ error }),
    );
    const [outcome] = await Promise.all([request, this.#wait(CHARGE_MS)]);
    if (!this.#alive) return;
    this.el.classList.remove('is-charging');

    if (outcome.error || !outcome.result || !outcome.result.report) {
      const message = outcome.error?.message || 'malformed response';
      ctx.toast?.(`HACK FAILED — ${message}`, { kind: 'error' });
      ctx.bus.emit('ui:error', {});
      ctx.bus.emit('mood', { name: 'mission' });
      this.#log('bad', 'LINK', `Uplink failed: ${message}`);
      this.#resetBattle(true);
      this.#setButton('idle');
      this.#busy = false;
      return;
    }
    await this.#resolve(outcome.result, before);
  }

  /** Rows back to their pre-hack state (scanning while the payload is in flight). */
  #resetBattle(toQueued = false) {
    const motion = !reduced();
    let rearmed = 0;
    for (const row of this.#rows) {
      row.el.className = `layer ${toQueued ? 'is-queued' : 'is-scanning'}`;
      row.state.textContent = toQueued ? 'QUEUED' : 'SCANNING';
      const wasBroken = row.seg.classList.contains('is-broken');
      row.seg.classList.remove('is-broken', 'is-blocked');
      for (const s of row.shards) s.getAnimations?.().forEach((a) => a.cancel());
      // The firewall regenerates: broken segments re-arm left to right instead of popping back.
      if (wasBroken && motion) this.#anim(row.seg, SEG_REARM, { duration: 260, delay: rearmed++ * 45, easing: EASE_OUT, fill: 'backwards' });
      row.objective?.classList.remove('is-done', 'is-failed');
    }
    const total = this.#rows.length;
    this.#r.hpCount.textContent = `${total}/${total}`;
    this.#r.objCount.textContent = `0/${total}`;
  }

  async #resolve(result, before) {
    const ctx = this.#ctx;
    const r = this.#r;
    const report = result.report;
    const checks = Array.isArray(report.checks) ? report.checks : [];
    const total = checks.length;
    const reducedMotion = reduced();

    this.#attempts = result.attempt || this.#attempts + 1;
    r.attempts.textContent = pad2(this.#attempts);
    if (!reducedMotion) this.#anim(r.attempts, PULSE, { duration: 380, easing: EASE_OUT });

    this.#setButton('resolving', { done: 0, total });
    let combo = 0;
    let passed = 0;
    let remaining = this.#rows.length;

    for (let i = 0; i < total; i++) {
      const check = checks[i];
      const row = this.#rows[i];
      const ok = !!check.passed;
      // Read rects first (one layout), then write.
      const from = row ? rectCenter(row.el.firstElementChild) : rectCenter(r.layers);
      const to = row ? rectCenter(row.seg) : rectCenter(r.art);

      const chain = ok ? combo : 0;
      if (ok) {
        passed++;
        remaining--;
      }
      if (row) this.#applyLayer(row, ok, chain, reducedMotion);
      this.#rows[i + 1]?.el.classList.add('is-next');
      r.hpCount.textContent = `${Math.max(0, remaining)}/${this.#rows.length}`;
      r.objCount.textContent = `${passed}/${this.#rows.length}`;
      this.#setButton('resolving', { done: i + 1, total });

      ctx.bus.emit('hack:layer', { index: i, total, passed: ok, combo: chain, x: from.x, y: from.y, tx: to.x, ty: to.y });
      this.#log(ok ? 'ok' : 'bad', ok ? 'BREACH' : 'BLOCK', `L${pad2(i + 1)} ${ok ? 'breached' : 'blocked'} — `, check.name);

      combo = ok ? combo + 1 : 0;
      const gap = reducedMotion ? 70 : Math.max(LAYER_GAP_MIN_MS, LAYER_GAP_MS - combo * LAYER_ACCEL_MS);
      await this.#wait(gap);
      if (!this.#alive) return;
    }

    // Layers the report did not cover (grader fault) go back to QUEUED.
    for (let i = total; i < this.#rows.length; i++) {
      this.#rows[i].el.className = 'layer is-queued';
      this.#rows[i].state.textContent = 'QUEUED';
    }

    const status = report.status;
    const error = report.error;
    if (CRASH_STATUSES.has(status)) {
      let point = rectCenter(r.editorHost);
      const line = error && Number.isInteger(error.line) ? error.line : 0;
      if (line > 0 && this.#editor) {
        // "Type: explanation" lets the editor tag its inline widget with the error type.
        this.#editor.markError(line, `${error.type || 'Error'}: ${error.decoded || error.message || STATUS_LABEL[status]}`);
        const lr = this.#editor.lineRect(line);
        const host = r.editorHost.getBoundingClientRect();
        if (lr && lr.height > 0) {
          point = {
            x: Math.min(host.right - 24, lr.left + lr.width / 2),
            y: Math.max(host.top + 8, Math.min(host.bottom - 8, lr.top + lr.height / 2)),
          };
        }
      }
      ctx.bus.emit('hack:crash', { status, x: point.x, y: point.y });
      this.#showLog('combat');
      this.#logResult(passed, total, checks);
      this.#logError(status, error);
      this.#enemyReact('gloat');
    } else if (!result.victory) {
      ctx.bus.emit('hack:fail', { passed, total });
      this.#logResult(passed, total, checks);
      if (status === 'harness_error') this.#logError(status, error);
      this.#enemyReact('gloat');
    }

    this.#setOutput(report.stdout, status);

    if (!result.victory) {
      const first = checks.findIndex((c) => !c.passed);
      if (first >= 0 && this.#rows[first]) {
        this.#later(() => this.#showIntel(first, checks[first]), INTEL_DELAY_MS);
      }
    } else {
      this.#log('ok', 'ROOT', `All ${total} layers breached. ${this.#mission.enemy || 'Target'} is defenceless.`);
    }

    if (result.state && typeof result.state === 'object') {
      ctx.state = result.state;
      ctx.bus.emit('state:changed', result.state);
    }

    if (result.victory) {
      await this.#victory(result, before);
      return;
    }
    this.#setButton('idle', { retry: true, sub: status === 'harness_error' ? 'GRADER FAULT · REINJECT' : '' });
    this.#busy = false;
  }

  #applyLayer(row, ok, chain, reducedMotion) {
    row.el.className = `layer ${ok ? 'is-breached' : 'is-blocked'}`;
    row.state.textContent = ok ? 'BREACHED' : 'BLOCKED';
    row.objective?.classList.add(ok ? 'is-done' : 'is-failed');
    if (ok) {
      row.seg.classList.add('is-broken');
    } else {
      row.seg.classList.add('is-blocked');
    }
    if (reducedMotion) return;
    const rowEl = row.el.firstElementChild;
    if (ok) {
      this.#anim(rowEl, ROW_BREACH, { duration: 420, easing: EASE_OUT });
      this.#anim(row.icon, ICON_POP, { duration: 380, easing: 'cubic-bezier(0.34, 1.56, 0.64, 1)' });
      this.#anim(row.seg, SEG_FLASH, { duration: 200, easing: EASE_OUT });
      for (let s = 0; s < row.shards.length; s++) {
        this.#anim(row.shards[s], SHARD_FRAMES[s], { duration: 560 + s * 60, easing: 'cubic-bezier(0.2, 0.7, 0.3, 1)', fill: 'both', delay: 40 });
      }
      this.#enemyReact('hit');
      if (chain >= 1) this.#comboPop(chain + 1);
    } else {
      this.#anim(rowEl, ROW_BLOCK, { duration: 460, easing: EASE_OUT });
      this.#anim(row.seg, SEG_FLASH, { duration: 240, easing: EASE_OUT });
    }
  }

  #comboPop(n) {
    const el = this.#r.combo;
    el.firstElementChild.textContent = `×${n}`;
    el.style.setProperty('--heat', String(Math.min(1, (n - 1) / 5)));
    this.#anim(el, COMBO_POP, { duration: 900, easing: EASE_OUT, fill: 'forwards' });
  }

  #enemyReact(kind) {
    if (reduced()) return;
    if (kind === 'hit') this.#anim(this.#r.enemyBody, ENEMY_HIT, { duration: 260, easing: EASE_OUT });
    else this.#anim(this.#r.enemyBody, ENEMY_GLOAT, { duration: 640, easing: 'cubic-bezier(0.65, 0, 0.35, 1)' });
  }

  #showIntel(index, check) {
    if (!this.#alive) return;
    const row = this.#rows[index];
    if (!row) return;
    row.intelMsg.innerHTML = inlineCode(check.message || 'This layer rejected your payload.');
    if (check.hint) {
      row.intelHint.innerHTML = `<span class="layer__try">▸ TRY</span> <span class="layer__hint-text">${escapeHtml(check.hint)}</span>`;
      row.intelHint.hidden = false;
    } else {
      row.intelHint.hidden = true;
    }
    row.el.classList.add('has-intel');
    this.#ctx.bus.emit('ui:open', {});
    // Bring the intel into view inside the layer list without scrolling the page.
    this.#later(() => {
      if (!this.#alive) return;
      const list = this.#r.layers;
      const lr = list.getBoundingClientRect();
      const rr = row.el.getBoundingClientRect();
      if (rr.bottom > lr.bottom || rr.top < lr.top) {
        list.scrollTo({ top: list.scrollTop + (rr.top - lr.top) - 8, behavior: reduced() ? 'auto' : 'smooth' });
      }
    }, 240);
  }

  async #victory(result, before) {
    const ctx = this.#ctx;
    const r = this.#r;
    this.#leaving = true;
    this.#stopClock();
    this.#setButton('victory');
    this.el.classList.add('is-victory');
    await this.#wait(VICTORY_BEAT_MS);
    if (!this.#alive) return;

    const points = this.#glyphPoints();
    const c = rectCenter(r.art);
    ctx.bus.emit('hack:victory', { x: c.x, y: c.y, points });
    r.stage.classList.add('is-dead');

    await this.#wait(VICTORY_EXIT_MS);
    if (!this.#alive) return;
    ctx.screens.go('victory', { mission: this.#mission, result, before });
  }

  /** One viewport point per visible glyph of the rendered art, from its measured cell grid. */
  #glyphPoints() {
    const lines = this.#artLines;
    const cols = this.#artCols;
    if (!lines.length || !cols) return new Float32Array(0);
    const rect = this.#r.art.getBoundingClientRect();
    const cw = rect.width / cols;
    const ch = rect.height / lines.length;
    let count = 0;
    for (const line of lines) for (const g of line) if (g.trim()) count++;
    const out = new Float32Array(count * 2);
    let k = 0;
    for (let row = 0; row < lines.length; row++) {
      let col = 0;
      for (const g of lines[row]) {
        if (g.trim()) {
          out[k++] = rect.left + (col + 0.5) * cw;
          out[k++] = rect.top + (row + 0.5) * ch;
        }
        col++;
      }
    }
    return out;
  }

  #setButton(state, info = {}) {
    const r = this.#r;
    const btn = r.hack;
    if (!btn) return;
    btn.dataset.state = state;
    btn.disabled = state !== 'idle' || this.#restoring;
    if (r.restore) r.restore.disabled = state !== 'idle' || this.#restoring || this.#leaving;
    btn.setAttribute('aria-busy', String(state !== 'idle' && state !== 'victory'));
    switch (state) {
      case 'saving':
        r.hackLabel.textContent = 'HACK';
        r.hackSub.textContent = 'SAVING PAYLOAD';
        break;
      case 'charging':
        r.hackLabel.textContent = 'INJECTING';
        r.hackSub.textContent = 'PAYLOAD IN FLIGHT';
        break;
      case 'resolving':
        r.hackLabel.textContent = 'BREACHING';
        r.hackSub.textContent = `LAYER ${pad2(info.done)} / ${pad2(info.total)}`;
        btn.style.setProperty('--progress', String(info.total ? info.done / info.total : 0));
        break;
      case 'victory':
        r.hackLabel.textContent = 'ROOT ACCESS';
        r.hackSub.textContent = 'TARGET DELETED';
        break;
      default:
        r.hackLabel.textContent = info.retry ? 'RETRY' : 'HACK';
        r.hackSub.textContent = info.sub || (info.retry ? 'PATCH · REINJECT' : 'INJECT PAYLOAD');
        btn.style.removeProperty('--progress');
    }
  }

  // ── combat log ──────────────────────────────────────────────────────

  #showLog(which) {
    const r = this.#r;
    const combat = which === 'combat';
    r.logTabs[0].classList.toggle('is-active', combat);
    r.logTabs[1].classList.toggle('is-active', !combat);
    r.logTabs[0].setAttribute('aria-selected', String(combat));
    r.logTabs[1].setAttribute('aria-selected', String(!combat));
    r.logCombat.hidden = !combat;
    r.logOutput.hidden = combat;
    if (!combat) r.logTabs[1].classList.remove('has-news');
    if (combat) this.#scrollLog();
  }

  #logAttemptHead(n) {
    const time = new Date().toTimeString().slice(0, 8);
    this.#append(
      h('div', { class: 'log-head' }, h('span', {}, `ATTEMPT ${pad2(n)}`), h('span', { class: 'log-head__rule' }), h('span', { class: 'mono' }, time)),
    );
  }

  /** kind: ok | bad | warn | sys. `code` (optional) is rendered with inline-code markup. */
  #log(kind, tag, text, code) {
    this.#append(
      h(
        'div',
        { class: `log-line log-line--${kind}` },
        h('span', { class: 'log-line__tag' }, tag),
        h('span', { class: 'log-line__text', html: escapeHtml(text) + (code ? inlineCode(code) : '') }),
      ),
    );
  }

  #logResult(passed, total, checks) {
    const first = checks.findIndex((c) => !c.passed);
    this.#log(
      passed ? 'warn' : 'bad',
      'RESULT',
      `Firewall holding — ${passed}/${total} layers breached.${first >= 0 ? ` INTEL on layer ${pad2(first + 1)}.` : ''}`,
    );
  }

  #logError(status, error) {
    const label = STATUS_LABEL[status] || 'ERROR';
    const type = error?.type || label;
    const line = Number.isInteger(error?.line) ? error.line : null;
    const head = h(
      'div',
      { class: 'log-error__head' },
      h('span', { class: 'chip chip--bad' }, label),
      h('span', { class: 'log-error__type mono' }, type),
      line ? h('span', { class: 'log-error__line mono' }, `LINE ${line}`) : null,
    );
    const body = [head];
    // A grader fault is a bug in the level, not the player's code: never blame them for it.
    const decoded = status === 'harness_error' ? GRADER_FAULT : error?.decoded;
    if (decoded) body.push(h('p', { class: 'log-error__decoded' }, decoded));
    if (error?.code) {
      body.push(
        h('pre', { class: 'log-error__code' }, line ? h('span', { class: 'log-error__ln' }, String(line)) : null, error.code),
      );
    }
    if (error?.message) {
      body.push(h('div', { class: 'log-error__raw' }, h('span', { class: 'label' }, 'PYTHON SAYS'), h('code', {}, `${type}: ${error.message}`)));
    }
    const card = h('div', { class: 'log-error', role: 'alert' }, body);
    this.#append(card);
    // The error is what the player must read: align its top, not the end of the feed.
    const pane = this.#r.logCombat;
    if (!pane.hidden) pane.scrollTop = Math.max(0, card.offsetTop - 6); // pane is the offsetParent
  }

  #append(node) {
    const feed = this.#r.log;
    feed.append(node);
    while (feed.childElementCount > LOG_LIMIT) feed.firstElementChild.remove();
    this.#scrollLog();
  }

  #scrollLog() {
    const pane = this.#r.logCombat;
    if (pane && !pane.hidden) pane.scrollTop = pane.scrollHeight;
  }

  #setOutput(stdout, status) {
    const r = this.#r;
    const text = typeof stdout === 'string' ? stdout.replace(/\s+$/, '') : '';
    r.stdout.classList.toggle('is-empty', !text);
    r.stdout.textContent = text || EMPTY_OUTPUT[stdout === null || stdout === undefined ? 'none' : status] || EMPTY_OUTPUT.ok;
    if (text && r.logOutput.hidden) r.logTabs[1].classList.add('has-news');
  }

  // ── tracked async helpers ───────────────────────────────────────────

  #later(fn, ms) {
    const t = setTimeout(() => {
      this.#timers.delete(t);
      fn();
    }, ms);
    this.#timers.add(t);
    return t;
  }

  /** Resolves after `ms` — or never, if the screen exits first (abandons the script). */
  #wait(ms) {
    return new Promise((resolve) => this.#later(resolve, ms));
  }

  #every(fn, ms) {
    const t = setInterval(fn, ms);
    this.#intervals.add(t);
    return t;
  }

  #anim(el, frames, options) {
    if (!el || typeof el.animate !== 'function') return null;
    const a = el.animate(frames, options);
    this.#animations.add(a);
    const forget = () => this.#animations.delete(a);
    a.onfinish = forget;
    a.oncancel = forget;
    return a;
  }
}

/** A stable fake process id for flavour text, derived from the enemy name. */
function pidOf(name = '') {
  let hash = 0x811c9dc5;
  for (let i = 0; i < name.length; i++) hash = Math.imul(hash ^ name.charCodeAt(i), 0x01000193);
  return `0x${((hash >>> 0) & 0xffff).toString(16).toUpperCase().padStart(4, '0')}`;
}
