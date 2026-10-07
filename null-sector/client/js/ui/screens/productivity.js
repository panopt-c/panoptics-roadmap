/**
 * ProductivityScreen — the COMMAND CENTER: real-world study and training, logged inside the game.
 *
 *   ┌ topbar: back · COMMAND CENTER / date · XP ledger (campaign · productivity · total) · ⚙ ┐
 *   │ NEURAL TRAINING (math)   │ CHASSIS (fitness)         │ LOG ENTRY  [study|workout|weight] │
 *   │ 360-min ring, streaks,   │ workout today, weight vs  │ form + transmission status       │
 *   │ course breakdown         │ 170 lb target, history    │                                  │
 *   │ ARMORY (inventory · milestones · protocols)          │ ACTIVITY FEED · reward renders   │
 *   └──────────────────────────────────────────────────────────────────────────────────────────┘
 *
 * Data: GET /api/productivity gives the whole snapshot; every successful log POST returns
 * {activity, snapshot}; the server also pushes the snapshot as the SSE `productivity` event
 * (main.js re-emits it as bus `server:productivity` and caches it on ctx.productivity). Every
 * path funnels into #render(snapshot), which is idempotent, so the three sources never fight.
 * The server owns all numbers (XP, streaks, progress); this screen never computes a reward.
 *
 * Retry safety: each log carries a `request_id`. SubmissionLedger reuses the pending id while
 * the payload is unchanged and issues a new one as soon as it changes. Only *uncertain*
 * failures (unreachable, timeout, 5xx: the server may have recorded it) are retried
 * automatically, with the same id and payload; a definite 4xx answer settles the id.
 *
 * States: loading (skeleton shimmer), fault (first load failed: message + retry), empty copy
 * for every list, inline field errors, an aria-live status line per form.
 *
 * Keys (outside text fields): 1 / 2 / 3 pick the log form, R refreshes, H returns to the hub.
 * Anywhere: Ctrl/Cmd+Enter submits the visible form. Tabs follow the ARIA tablist pattern.
 */
import { h, sleep, countUp, rectCenter } from '../dom.js';
import { settings } from '../../core/settings.js';
import { ApiError } from '../api.js';

export const COURSES = Object.freeze([
  'Algebra 2', 'Trigonometry', 'Precalculus', 'Calculus 1', 'Calculus 2', 'Calculus 3', 'Linear Algebra',
]);
const STUDY_GOAL_FALLBACK = 360;
const TARGET_WEIGHT_FALLBACK = 170;
const QUICK_MINUTES = [15, 30, 45, 60, 90];
const WORKOUT_PRESETS = ['Strength', 'Run', 'Walk', 'Cycling', 'HIIT', 'Mobility', 'Swim', 'Sports'];
const RETRY_DELAYS_MS = [700, 2000]; // automatic retries after an uncertain failure
const FEED_LIMIT = 12;
const RING_R = 52;
const RING_C = 2 * Math.PI * RING_R;

const FORMS = [
  { kind: 'study', label: 'Study', key: '1' },
  { kind: 'workout', label: 'Workout', key: '2' },
  { kind: 'weight', label: 'Weight', key: '3' },
];

const ICON_BACK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>';
const ICON_GEAR = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="12" cy="12" r="3.2"/><path d="M12 2.8v2.6M12 18.6v2.6M21.2 12h-2.6M5.4 12H2.8M18.5 5.5l-1.8 1.8M7.3 16.7l-1.8 1.8M18.5 18.5l-1.8-1.8M7.3 7.3L5.5 5.5"/></svg>';

// ── pure helpers (exported for tests) ───────────────────────────────────────────────────

const num = (value, fallback = 0) => {
  const n = typeof value === 'string' && value.trim() === '' ? NaN : Number(value);
  return Number.isFinite(n) ? n : fallback;
};
const clamp01 = (x) => Math.min(1, Math.max(0, num(x)));

/** 135 → "2h 15m", 45 → "45m", 120 → "2h". */
export function formatMinutes(minutes) {
  const m = Math.max(0, Math.round(num(minutes)));
  if (m < 60) return `${m}m`;
  const hours = Math.floor(m / 60);
  const rest = m % 60;
  return rest ? `${hours}h ${String(rest).padStart(2, '0')}m` : `${hours}h`;
}

const formatLbs = (lbs) => (lbs === null || lbs === undefined || !Number.isFinite(Number(lbs)) ? '—' : Number(lbs).toFixed(1));

/** JSON with sorted keys, so equal payloads always produce the same key. */
function stableKey(payload) {
  const sorted = {};
  for (const key of Object.keys(payload).sort()) if (key !== 'request_id') sorted[key] = payload[key];
  return JSON.stringify(sorted);
}

function newRequestId() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/**
 * Hands out request ids per form. The same payload keeps its id until the server gives a
 * definite answer; a changed payload gets a fresh id (the server would rightly reject reusing
 * an id for different data).
 */
export class SubmissionLedger {
  #pending = new Map(); // kind → {key, id}

  idFor(kind, payload) {
    const key = stableKey(payload);
    const pending = this.#pending.get(kind);
    if (pending && pending.key === key) return pending.id;
    const id = newRequestId();
    this.#pending.set(kind, { key, id });
    return id;
  }

  pending(kind) {
    return this.#pending.get(kind)?.id ?? null;
  }

  settle(kind) {
    this.#pending.delete(kind);
  }
}

/** Could the server have recorded the request even though we saw a failure? */
export function isUncertain(err) {
  if (!(err instanceof ApiError)) return true;
  return err.status === 0 || err.status === 408 || err.status >= 500;
}

const toList = (value) => {
  if (Array.isArray(value)) return value;
  if (value && typeof value === 'object') {
    return Object.entries(value).map(([name, v]) => (v && typeof v === 'object' ? { name, ...v } : { name, value: v }));
  }
  return [];
};

const parseDetails = (details) => {
  if (typeof details === 'string') {
    try {
      return JSON.parse(details) || {};
    } catch {
      return { note: details };
    }
  }
  return details && typeof details === 'object' ? details : {};
};

/** Minutes per course, always listing the whole curriculum in order. */
export function courseRows(study) {
  const raw = study?.course_minutes;
  const minutes = new Map();
  for (const row of toList(raw)) {
    const course = row.course ?? row.name;
    if (course) minutes.set(String(course), num(row.minutes ?? row.total_minutes ?? row.value));
  }
  const rows = COURSES.map((course) => ({ course, minutes: minutes.get(course) ?? 0 }));
  for (const [course, value] of minutes) if (!COURSES.includes(course)) rows.push({ course, minutes: value });
  return rows;
}

/** One-line summary of an activity row for the feed. */
export function describeActivity(activity) {
  const d = parseDetails(activity?.details);
  const minutes = d.minutes !== undefined ? formatMinutes(d.minutes) : null;
  switch (activity?.kind) {
    case 'study':
      return { glyph: '∑', title: d.course || 'Study session', sub: [minutes, d.topic].filter(Boolean).join(' · ') };
    case 'workout': {
      const sets = d.sets && d.reps ? `${d.sets}×${d.reps}` : d.sets ? `${d.sets} sets` : d.reps ? `${d.reps} reps` : null;
      const load = d.load_lbs ? `${num(d.load_lbs)} lb` : null;
      const dist = d.distance_miles ? `${num(d.distance_miles)} mi` : null;
      return { glyph: '⚡', title: d.activity || 'Workout', sub: [minutes, sets, load, dist, d.note].filter(Boolean).join(' · ') };
    }
    case 'weight':
      return { glyph: '⚖', title: 'Weigh-in', sub: d.weight_lbs !== undefined ? `${formatLbs(d.weight_lbs)} lb` : '' };
    default:
      return { glyph: '◆', title: String(activity?.kind || 'Activity'), sub: d.note || '' };
  }
}

const itemName = (item) => String(item?.name ?? item?.title ?? item?.metadata?.name ?? item?.item_key ?? item?.item ?? item?.id ?? 'Unknown item').replaceAll('_', ' ');
const itemQty = (item) => num(item?.quantity ?? item?.qty ?? item?.count, 1);
const milestoneDone = (m) => Boolean(m?.achieved ?? m?.unlocked ?? m?.completed ?? m?.earned ?? m?.achieved_at ?? m?.unlocked_at);
const safeRarity = (r) => (/^[a-z_-]{1,24}$/i.test(String(r ?? '')) ? String(r).toLowerCase() : 'common');

// ── the screen ──────────────────────────────────────────────────────────────────────────

export class ProductivityScreen {
  #ctx;
  #alive = false;
  #offs = [];
  #r = {};
  #snap = null;
  #shown = { campaign: null, productivity: null, total: null };
  #tab = 'study';
  #ledger = new SubmissionLedger();
  #busy = new Set(); // kinds with a submission in flight
  #loadSeq = 0;

  constructor(ctx) {
    this.#ctx = ctx;
  }

  // ── lifecycle ─────────────────────────────────────────────────────────

  async enter() {
    const ctx = this.#ctx;
    this.#alive = true;
    this.#r = {};
    this.#snap = null;
    this.#shown = { campaign: null, productivity: null, total: null };
    this.el = h('section', { class: 'screen screen--productivity', 'aria-label': 'Command center' });
    this.el.append(this.#buildTopbar(), this.#buildGrid(), this.#buildFault());
    this.#selectTab(this.#tab, { focus: false });

    ctx.bus.emit('mood', { name: 'mission' });
    ctx.renderer?.setFocus?.(0.55);
    this.#offs.push(ctx.bus.on('server:productivity', (snap) => this.#adopt(snap)));

    if (ctx.productivity) this.#adopt(ctx.productivity);
    else this.#setLoading(true);
    void this.#load(); // always refresh: a cached snapshot may be stale
  }

  async exit() {
    this.#alive = false;
    for (const off of this.#offs) off();
    this.#offs.length = 0;
  }

  onKey(e) {
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key === 'Enter') {
      e.preventDefault();
      this.#submit(this.#tab);
      return true;
    }
    if (mod || e.altKey) return false;
    const target = e.target;
    if (target instanceof Element && target.closest('input, select, textarea, [contenteditable="true"]')) return false;
    const form = FORMS.find((f) => f.key === e.key);
    if (form) {
      e.preventDefault();
      this.#selectTab(form.kind, { focus: true });
      return true;
    }
    if (e.key === 'r' || e.key === 'R') {
      e.preventDefault();
      void this.#load({ announce: true });
      return true;
    }
    if (e.key === 'h' || e.key === 'H') {
      e.preventDefault();
      this.#ctx.screens.go('hub');
      return true;
    }
    return false;
  }

  // ── data ──────────────────────────────────────────────────────────────

  async #load({ announce = false } = {}) {
    const seq = ++this.#loadSeq;
    try {
      const snap = await this.#ctx.api.productivity();
      if (!this.#alive || seq !== this.#loadSeq) return;
      this.#adopt(snap);
      if (announce) this.#ctx.toast('Command center synced.', { kind: 'ok', ms: 1600 });
    } catch (err) {
      if (!this.#alive || seq !== this.#loadSeq) return;
      if (this.#snap) {
        if (announce) this.#ctx.toast(`Sync failed — ${err?.message || 'unknown fault'}`, { kind: 'warn' });
        return;
      }
      this.#showFault(err);
    }
  }

  #adopt(snap) {
    if (!snap || typeof snap !== 'object' || !this.#alive) return;
    this.#ctx.productivity = snap;
    this.#snap = snap;
    this.#setLoading(false);
    this.#hideFault();
    this.#render(snap);
  }

  #setLoading(on) {
    this.el?.classList.toggle('is-loading', on);
    this.#r.grid?.setAttribute('aria-busy', on ? 'true' : 'false');
  }

  // ── build ─────────────────────────────────────────────────────────────

  #buildTopbar() {
    const r = this.#r;
    r.date = h('span', { class: 'label ops-topbar__date' }, 'Syncing…');
    r.xpCampaign = h('span', { class: 'ops-xp__value mono' }, '—');
    r.xpProductivity = h('span', { class: 'ops-xp__value mono' }, '—');
    r.xpTotal = h('span', { class: 'ops-xp__value mono' }, '—');
    const xpChip = (cls, label, value, title) =>
      h('div', { class: `ops-xp__chip ${cls}`, title }, h('span', { class: 'ops-xp__label' }, label), value);
    return h(
      'header',
      { class: 'topbar ops-topbar rise', style: '--i: 0' },
      h(
        'div',
        { class: 'topbar__left' },
        h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Back to hub (H)', title: 'Back to hub · H', html: ICON_BACK, onclick: () => this.#ctx.screens.go('hub') }),
        h('div', { class: 'ops-topbar__title' }, h('span', { class: 'ops-topbar__name' }, 'Command center'), r.date),
      ),
      h(
        'div',
        { class: 'topbar__center ops-xp', role: 'group', 'aria-label': 'Experience points' },
        xpChip('ops-xp__chip--campaign', 'Campaign', r.xpCampaign, 'XP from hacking missions (save.json)'),
        h('span', { class: 'ops-xp__op', 'aria-hidden': 'true' }, '+'),
        xpChip('ops-xp__chip--productivity', 'Productivity', r.xpProductivity, 'XP from study and training logs'),
        h('span', { class: 'ops-xp__op', 'aria-hidden': 'true' }, '='),
        xpChip('ops-xp__chip--total', 'Total', r.xpTotal, 'Combined XP'),
      ),
      h(
        'div',
        { class: 'topbar__right' },
        h('button', { class: 'icon-btn icon-btn--gear', type: 'button', 'data-action': 'settings', 'aria-label': 'Settings (Esc)', title: 'Settings · Esc', html: ICON_GEAR }),
      ),
    );
  }

  #buildGrid() {
    const r = this.#r;
    r.grid = h(
      'div',
      { class: 'ops scroll', 'aria-busy': 'true' },
      this.#buildStudy(),
      this.#buildFitness(),
      this.#buildLog(),
      this.#buildArmory(),
      this.#buildFeed(),
    );
    return r.grid;
  }

  #panel(cls, title, i, ...body) {
    const head = h('div', { class: 'panel__head' }, h('h2', { class: 'panel__title' }, title));
    const panel = h('section', { class: `panel ops-panel ${cls} rise`, style: `--i: ${i}`, 'aria-label': title }, head, ...body);
    return { panel, head };
  }

  #buildStudy() {
    const r = this.#r;
    r.ringFill = h('circle', {});
    r.ringValue = h('span', { class: 'ops-ring__value mono' }, '0');
    r.ringGoal = h('span', { class: 'ops-ring__goal label' }, `of ${STUDY_GOAL_FALLBACK} min`);
    r.ring = h('div', { class: 'ops-ring', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': String(STUDY_GOAL_FALLBACK), 'aria-valuenow': '0', 'aria-label': 'Study minutes today' });
    r.ring.innerHTML =
      `<svg viewBox="0 0 120 120" aria-hidden="true"><circle class="ops-ring__track" cx="60" cy="60" r="${RING_R}"/>` +
      `<circle class="ops-ring__ticks" cx="60" cy="60" r="${RING_R}"/>` +
      `<circle class="ops-ring__fill" cx="60" cy="60" r="${RING_R}" stroke-dasharray="${RING_C.toFixed(2)}" stroke-dashoffset="${RING_C.toFixed(2)}"/></svg>`;
    r.ringFill = r.ring.querySelector('.ops-ring__fill');
    r.ring.append(h('div', { class: 'ops-ring__center' }, r.ringValue, r.ringGoal));

    r.remaining = h('span', { class: 'ops-stat__value mono' }, '—');
    r.streak = h('span', { class: 'ops-stat__value mono' }, '—');
    r.best = h('span', { class: 'ops-stat__value mono' }, '—');
    r.totalStudy = h('span', { class: 'ops-stat__value mono' }, '—');
    const stat = (label, value) => h('div', { class: 'ops-stat' }, h('span', { class: 'label' }, label), value);
    r.streakChip = h('span', { class: 'chip' }, 'Streak —');
    r.courses = h('ol', { class: 'ops-courses', 'aria-label': 'Minutes per course' });

    const { panel, head } = this.#panel(
      'ops-study',
      'Neural training · math',
      1,
      h(
        'div',
        { class: 'panel__body ops-study__body' },
        h('div', { class: 'ops-study__top' }, r.ring, h('div', { class: 'ops-stats' }, stat('Remaining today', r.remaining), stat('Current streak', r.streak), stat('Best streak', r.best), stat('All-time', r.totalStudy))),
        h('div', { class: 'ops-subhead label' }, 'Course load'),
        r.courses,
      ),
    );
    head.append(r.streakChip);
    return panel;
  }

  #buildFitness() {
    const r = this.#r;
    r.workoutToday = h('span', { class: 'ops-big mono' }, '0');
    r.latest = h('span', { class: 'ops-big mono' }, '—');
    r.target = h('span', { class: 'mono' }, String(TARGET_WEIGHT_FALLBACK));
    r.baseline = h('span', { class: 'mono' }, '—');
    r.toGo = h('span', { class: 'ops-weight__togo' }, '');
    r.weightMeter = h('div', { class: 'meter meter--ticks ops-weight__meter', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-label': 'Progress toward target weight' }, h('div', { class: 'meter__fill' }));
    r.chart = h('div', { class: 'ops-chart', role: 'img', 'aria-label': 'Weight history' });

    const { panel } = this.#panel(
      'ops-fitness',
      'Chassis · fitness',
      2,
      h(
        'div',
        { class: 'panel__body ops-fitness__body' },
        h(
          'div',
          { class: 'ops-fitness__row' },
          h('div', { class: 'ops-metric' }, h('span', { class: 'label' }, 'Training today'), h('span', { class: 'ops-metric__line' }, r.workoutToday, h('span', { class: 'ops-unit' }, 'min'))),
          h('div', { class: 'ops-metric' }, h('span', { class: 'label' }, 'Latest weight'), h('span', { class: 'ops-metric__line' }, r.latest, h('span', { class: 'ops-unit' }, 'lb'))),
        ),
        h(
          'div',
          { class: 'ops-weight' },
          h('div', { class: 'ops-weight__labels' }, h('span', { class: 'label' }, 'Baseline ', r.baseline), r.toGo, h('span', { class: 'label' }, 'Target ', r.target)),
          r.weightMeter,
        ),
        h('div', { class: 'ops-subhead label' }, 'Weight history'),
        r.chart,
      ),
    );
    return panel;
  }

  #buildLog() {
    const r = this.#r;
    r.tabs = new Map();
    r.forms = new Map();
    const tablist = h('div', { class: 'segmented ops-tabs', role: 'tablist', 'aria-label': 'Log type', style: `--count: ${FORMS.length}` });
    for (const f of FORMS) {
      const tab = h(
        'button',
        {
          class: 'segmented__opt',
          type: 'button',
          role: 'tab',
          id: `ops-tab-${f.kind}`,
          'aria-controls': `ops-form-${f.kind}`,
          'aria-selected': 'false',
          tabindex: '-1',
          title: `${f.label} · ${f.key}`,
          onclick: () => this.#selectTab(f.kind, { focus: false }),
        },
        f.label,
      );
      r.tabs.set(f.kind, tab);
      tablist.append(tab);
    }
    tablist.addEventListener('keydown', (e) => {
      const order = FORMS.map((f) => f.kind);
      const at = order.indexOf(this.#tab);
      const next = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: order.length - 1 }[e.key];
      if (next === undefined) return;
      e.preventDefault();
      e.stopPropagation();
      this.#selectTab(order[(next + order.length) % order.length], { focus: 'tab' });
    });
    r.tablist = tablist;

    r.forms.set('study', this.#buildStudyForm());
    r.forms.set('workout', this.#buildWorkoutForm());
    r.forms.set('weight', this.#buildWeightForm());

    const { panel, head } = this.#panel('ops-log', 'Log entry', 3, h('div', { class: 'panel__body ops-log__body scroll' }, ...r.forms.values()));
    head.append(tablist);
    return panel;
  }

  // field factory: label + control + inline error, wired with aria-describedby
  #field(id, label, control, { hint, cls = '' } = {}) {
    const error = h('span', { class: 'ops-field__error', id: `${id}-err`, role: 'alert' });
    control.id = id;
    control.setAttribute('aria-describedby', `${id}-err${hint ? ` ${id}-hint` : ''}`);
    return h(
      'div',
      { class: `ops-field ${cls}` },
      h('label', { class: 'ops-field__label', for: id }, label),
      control,
      hint ? h('span', { class: 'ops-field__hint', id: `${id}-hint` }, hint) : null,
      error,
    );
  }

  #input(name, attrs = {}) {
    return h('input', { class: 'ops-input', name, autocomplete: 'off', spellcheck: 'false', ...attrs });
  }

  #formShell(kind, title, fields, submitLabel) {
    const status = h('p', { class: 'ops-form__status', role: 'status', 'aria-live': 'polite' });
    const submit = h(
      'button',
      { class: 'btn btn--primary ops-form__submit', type: 'submit' },
      h('span', { class: 'ops-form__submit-label' }, submitLabel),
      h('span', { class: 'kbd' }, navigator.platform?.startsWith('Mac') ? '⌘↵' : 'Ctrl+↵'),
    );
    const form = h(
      'form',
      {
        class: 'ops-form',
        id: `ops-form-${kind}`,
        role: 'tabpanel',
        'aria-labelledby': `ops-tab-${kind}`,
        novalidate: true,
        dataset: { kind },
        onsubmit: (e) => {
          e.preventDefault();
          this.#submit(kind);
        },
        oninput: (e) => this.#clearFieldError(e.target),
      },
      h('p', { class: 'ops-form__title' }, title),
      ...fields,
      h('div', { class: 'ops-form__foot' }, status, submit),
    );
    form._status = status;
    form._submit = submit;
    return form;
  }

  #dateField(kind) {
    return this.#field(`ops-${kind}-date`, 'Date', this.#input('on_date', { type: 'date' }), { hint: 'Leave empty for today', cls: 'ops-field--date' });
  }

  #buildStudyForm() {
    const select = h('select', { class: 'ops-input ops-select', name: 'course', required: true }, ...COURSES.map((c) => h('option', { value: c }, c)));
    const minutes = this.#input('minutes', { type: 'number', inputmode: 'numeric', min: '1', max: '1440', step: '1', required: true, placeholder: 'e.g. 45' });
    const quick = h(
      'div',
      { class: 'ops-quick', role: 'group', 'aria-label': 'Quick minutes' },
      ...QUICK_MINUTES.map((m) =>
        h('button', {
          class: 'ops-quick__btn',
          type: 'button',
          onclick: () => {
            minutes.value = String(m);
            this.#clearFieldError(minutes);
            minutes.focus();
          },
        }, `${m}`),
      ),
    );
    return this.#formShell(
      'study',
      'Log a study session',
      [
        h('div', { class: 'ops-form__row ops-form__row--2' },
          this.#field('ops-study-course', 'Course', select),
          this.#field('ops-study-minutes', 'Minutes', minutes),
        ),
        quick,
        this.#field('ops-study-topic', 'Topic', this.#input('topic', { type: 'text', maxlength: '200', placeholder: 'Unit circle, chain rule…' }), { hint: 'Optional' }),
        this.#dateField('study'),
      ],
      'Log study',
    );
  }

  #buildWorkoutForm() {
    const list = h('datalist', { id: 'ops-workout-presets' }, ...WORKOUT_PRESETS.map((p) => h('option', { value: p })));
    const opt = (name, label, attrs) =>
      this.#field(`ops-workout-${name}`, label, this.#input(name, { type: 'number', inputmode: 'decimal', min: '0', ...attrs }), { hint: 'Optional' });
    return this.#formShell(
      'workout',
      'Log a workout',
      [
        list,
        h('div', { class: 'ops-form__row ops-form__row--2' },
          this.#field('ops-workout-activity', 'Activity', this.#input('activity', { type: 'text', maxlength: '80', required: true, list: 'ops-workout-presets', placeholder: 'e.g. Strength' })),
          this.#field('ops-workout-minutes', 'Minutes', this.#input('minutes', { type: 'number', inputmode: 'numeric', min: '1', max: '1440', step: '1', required: true, placeholder: 'e.g. 40' })),
        ),
        h('div', { class: 'ops-form__row ops-form__row--4' },
          opt('sets', 'Sets', { step: '1', inputmode: 'numeric' }),
          opt('reps', 'Reps', { step: '1', inputmode: 'numeric' }),
          opt('load_lbs', 'Load lb', { step: '0.5' }),
          opt('distance_miles', 'Miles', { step: '0.01' }),
        ),
        this.#field('ops-workout-note', 'Note', this.#input('note', { type: 'text', maxlength: '500', placeholder: 'How it felt' }), { hint: 'Optional' }),
        this.#dateField('workout'),
      ],
      'Log workout',
    );
  }

  #buildWeightForm() {
    return this.#formShell(
      'weight',
      'Log a weigh-in',
      [
        this.#field('ops-weight-lbs', 'Weight (lb)', this.#input('weight_lbs', { type: 'number', inputmode: 'decimal', min: '50', max: '800', step: '0.1', required: true, placeholder: '000.0' }), { cls: 'ops-field--hero' }),
        this.#dateField('weight'),
      ],
      'Log weight',
    );
  }

  #buildArmory() {
    const r = this.#r;
    r.inventory = h('ul', { class: 'ops-items', 'aria-label': 'Inventory' });
    r.milestones = h('ul', { class: 'ops-milestones', 'aria-label': 'Milestones' });
    r.habits = h('ul', { class: 'ops-habits', 'aria-label': 'Habits' });
    r.itemCount = h('span', { class: 'chip' }, '0 items');
    const { panel, head } = this.#panel(
      'ops-armory',
      'Armory',
      4,
      h(
        'div',
        { class: 'panel__body ops-armory__body' },
        h('div', { class: 'ops-armory__col' }, h('div', { class: 'ops-subhead label' }, 'Inventory'), h('div', { class: 'scroll ops-armory__scroll' }, r.inventory)),
        h('div', { class: 'ops-armory__col' }, h('div', { class: 'ops-subhead label' }, 'Milestones'), h('div', { class: 'scroll ops-armory__scroll' }, r.milestones)),
        h('div', { class: 'ops-armory__col ops-armory__col--habits' }, h('div', { class: 'ops-subhead label' }, 'Protocols'), h('div', { class: 'scroll ops-armory__scroll' }, r.habits)),
      ),
    );
    head.append(r.itemCount);
    return panel;
  }

  #buildFeed() {
    const r = this.#r;
    r.feed = h('ol', { class: 'ops-feed', 'aria-label': 'Recent activity' });
    r.jobs = h('ul', { class: 'ops-jobs', 'aria-label': 'Reward transmissions' });
    r.jobsWrap = h('div', { class: 'ops-jobs-wrap', hidden: true }, h('div', { class: 'ops-subhead label' }, 'Reward transmissions'), r.jobs);
    const { panel } = this.#panel('ops-feed-panel', 'Activity feed', 5, h('div', { class: 'panel__body ops-feed__body scroll' }, r.feed, r.jobsWrap));
    return panel;
  }

  #buildFault() {
    const r = this.#r;
    r.faultMsg = h('p', { class: 'ops-fault__msg' });
    r.faultRetry = h('button', { class: 'btn btn--primary', type: 'button', onclick: () => this.#retryLoad() }, 'Retry', h('span', { class: 'kbd' }, 'R'));
    r.fault = h(
      'div',
      { class: 'ops-fault', hidden: true },
      h(
        'section',
        { class: 'panel ops-fault__panel', role: 'alert', 'aria-label': 'Command center offline' },
        h('div', { class: 'panel__head' }, h('h2', { class: 'panel__title' }, 'Command center offline')),
        h(
          'div',
          { class: 'panel__body' },
          r.faultMsg,
          h('div', { class: 'ops-fault__actions' }, r.faultRetry, h('button', { class: 'btn btn--ghost', type: 'button', onclick: () => this.#ctx.screens.go('hub') }, 'Back to hub', h('span', { class: 'kbd' }, 'H'))),
        ),
      ),
    );
    return r.fault;
  }

  #showFault(err) {
    const r = this.#r;
    this.#setLoading(false);
    const offline = err instanceof ApiError && err.status === 404;
    r.faultMsg.textContent = offline
      ? 'The productivity service is not running on this server yet.'
      : `Could not reach the productivity service — ${err?.message || 'unknown fault'}.`;
    r.grid.hidden = true;
    r.fault.hidden = false;
    r.faultRetry.disabled = false;
    if (this.el.contains(document.activeElement) || document.activeElement === document.body) r.faultRetry.focus({ preventScroll: true });
    this.#ctx.bus.emit('ui:error', {});
  }

  #hideFault() {
    const r = this.#r;
    if (!r.fault || r.fault.hidden) return;
    r.fault.hidden = true;
    r.grid.hidden = false;
  }

  async #retryLoad() {
    this.#r.faultRetry.disabled = true;
    this.#r.fault.hidden = true;
    this.#r.grid.hidden = false;
    this.#setLoading(true);
    await this.#load();
  }

  // ── render ────────────────────────────────────────────────────────────

  #render(snap) {
    const r = this.#r;
    const study = snap.study || {};
    const fitness = snap.fitness || {};
    const game = snap.game || {};

    r.date.textContent = snap.date ? `Daily ops · ${snap.date}` : 'Daily ops';
    for (const form of r.forms.values()) {
      const date = form.querySelector('input[name="on_date"]');
      if (date && snap.date) date.max = snap.date;
    }

    this.#renderXp(game);

    // study
    const goal = num(study.goal_minutes, STUDY_GOAL_FALLBACK) || STUDY_GOAL_FALLBACK;
    const today = num(study.today_minutes);
    const progress = study.progress !== undefined && study.progress !== null ? clamp01(study.progress) : clamp01(today / goal);
    r.ringFill.style.strokeDashoffset = String((RING_C * (1 - progress)).toFixed(2));
    r.ring.classList.toggle('is-complete', progress >= 1);
    r.ring.setAttribute('aria-valuenow', String(today));
    r.ring.setAttribute('aria-valuemax', String(goal));
    r.ring.setAttribute('aria-valuetext', `${today} of ${goal} minutes`);
    r.ringValue.textContent = String(today);
    r.ringGoal.textContent = `of ${goal} min`;
    const remaining = study.remaining_minutes ?? Math.max(0, goal - today);
    r.remaining.textContent = num(remaining) > 0 ? formatMinutes(remaining) : 'Goal met';
    r.remaining.classList.toggle('is-done', num(remaining) <= 0);
    const streak = num(study.current_streak_days);
    r.streak.textContent = `${streak} ${streak === 1 ? 'day' : 'days'}`;
    const bestStreak = num(study.best_streak_days);
    r.best.textContent = `${bestStreak} ${bestStreak === 1 ? 'day' : 'days'}`;
    r.totalStudy.textContent = formatMinutes(study.total_minutes);
    r.streakChip.className = `chip ${streak > 0 ? 'chip--ok' : ''}`;
    r.streakChip.textContent = streak > 0 ? `Streak ${streak}d` : 'No streak';
    this.#renderCourses(study);

    // fitness
    r.workoutToday.textContent = String(num(fitness.today_workout_minutes));
    r.latest.textContent = formatLbs(fitness.latest_weight_lbs);
    const target = num(fitness.target_weight_lbs, TARGET_WEIGHT_FALLBACK) || TARGET_WEIGHT_FALLBACK;
    r.target.textContent = formatLbs(target);
    r.baseline.textContent = formatLbs(fitness.baseline_weight_lbs);
    const wp = fitness.weight_progress;
    const hasProgress = wp !== null && wp !== undefined && Number.isFinite(Number(wp));
    r.weightMeter.style.setProperty('--value', hasProgress ? String(clamp01(wp)) : '0');
    r.weightMeter.setAttribute('aria-valuenow', hasProgress ? String(Math.round(clamp01(wp) * 100)) : '0');
    r.weightMeter.classList.toggle('is-empty', !hasProgress);
    const latest = fitness.latest_weight_lbs;
    if (latest === null || latest === undefined) {
      r.toGo.textContent = 'Log a weigh-in to start';
      r.toGo.className = 'ops-weight__togo';
    } else {
      const gap = Math.abs(num(latest) - target);
      const reached = gap === 0 || (hasProgress && Number(wp) >= 1);
      r.toGo.textContent = reached ? 'Target reached' : `${gap.toFixed(1)} lb to go`;
      r.toGo.className = `ops-weight__togo ${reached ? 'is-done' : ''}`;
    }
    this.#renderChart(fitness.weight_history, target);

    this.#renderInventory(snap.inventory);
    this.#renderMilestones(snap.milestones);
    this.#renderHabits(snap.habits);
    this.#renderFeed(snap.recent_activity);
    this.#renderJobs(snap.cinematic_jobs, snap.milestones);
  }

  #renderXp(game) {
    const r = this.#r;
    const values = {
      campaign: num(game.campaign_xp),
      productivity: num(game.productivity_xp),
      total: num(game.total_xp, num(game.campaign_xp) + num(game.productivity_xp)),
    };
    const els = { campaign: r.xpCampaign, productivity: r.xpProductivity, total: r.xpTotal };
    for (const key of Object.keys(values)) {
      const from = this.#shown[key];
      const to = values[key];
      if (from === to) continue;
      this.#shown[key] = to;
      if (from === null) els[key].textContent = to.toLocaleString();
      else {
        els[key].parentElement.classList.remove('is-bumped');
        void els[key].offsetWidth;
        els[key].parentElement.classList.add('is-bumped');
        countUp(els[key], from, to, { duration: 700, format: (n) => n.toLocaleString() });
      }
    }
  }

  #renderCourses(study) {
    const rows = courseRows(study);
    const max = Math.max(1, ...rows.map((row) => row.minutes));
    this.#r.courses.replaceChildren(
      ...rows.map((row, i) =>
        h(
          'li',
          { class: `ops-course ${row.minutes > 0 ? '' : 'is-idle'}`, style: `--i: ${i}` },
          h('span', { class: 'ops-course__name' }, row.course),
          h('span', { class: 'meter ops-course__meter', style: `--value: ${(row.minutes / max).toFixed(4)}`, 'aria-hidden': 'true' }, h('span', { class: 'meter__fill' })),
          h('span', { class: 'ops-course__min mono' }, formatMinutes(row.minutes)),
        ),
      ),
    );
  }

  #renderChart(history, target) {
    const chart = this.#r.chart;
    const points = toList(history)
      .map((p) => ({ date: String(p.log_date ?? p.date ?? ''), lbs: Number(p.weight_lbs ?? p.value) }))
      .filter((p) => Number.isFinite(p.lbs))
      .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    if (!points.length) {
      chart.replaceChildren(h('p', { class: 'ops-empty' }, 'No weigh-ins yet. Log one to start the trend line.'));
      chart.setAttribute('aria-label', 'Weight history: no data yet');
      return;
    }
    const W = 320;
    const H = 110;
    const pad = { l: 6, r: 34, t: 10, b: 16 };
    const values = points.map((p) => p.lbs).concat(target);
    let lo = Math.min(...values);
    let hi = Math.max(...values);
    if (hi - lo < 4) {
      lo -= 2;
      hi += 2;
    }
    const span = hi - lo;
    lo -= span * 0.08;
    hi += span * 0.08;
    const x = (i) => pad.l + (points.length === 1 ? (W - pad.l - pad.r) / 2 : (i / (points.length - 1)) * (W - pad.l - pad.r));
    const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);
    const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.lbs).toFixed(1)}`).join(' ');
    const area = `${x(0).toFixed(1)},${H - pad.b} ${line} ${x(points.length - 1).toFixed(1)},${H - pad.b}`;
    const last = points[points.length - 1];
    const ty = y(target).toFixed(1);
    chart.innerHTML =
      `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">` +
      `<defs><linearGradient id="ops-area" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="currentColor" stop-opacity=".32"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>` +
      `<line class="ops-chart__target" x1="${pad.l}" x2="${W - pad.r}" y1="${ty}" y2="${ty}"/>` +
      `<text class="ops-chart__target-label" x="${W - pad.r + 4}" y="${Number(ty) + 3}">${target}</text>` +
      `<polygon class="ops-chart__area" points="${area}"/>` +
      `<polyline class="ops-chart__line" points="${line}"/>` +
      `<circle class="ops-chart__dot" cx="${x(points.length - 1).toFixed(1)}" cy="${y(last.lbs).toFixed(1)}" r="3.2"/>` +
      `</svg>` +
      `<div class="ops-chart__axis"><span class="mono">${escapeText(points[0].date)}</span><span class="mono">${escapeText(last.date)}</span></div>`;
    chart.setAttribute('aria-label', `Weight history: ${points.length} weigh-ins, latest ${formatLbs(last.lbs)} lb, target ${target} lb`);
  }

  #renderInventory(inventory) {
    const items = toList(inventory).map(item => ({ ...item.metadata, ...item }));
    const r = this.#r;
    const total = items.reduce((sum, it) => sum + itemQty(it), 0);
    r.itemCount.textContent = `${total} ${total === 1 ? 'item' : 'items'}`;
    if (!items.length) {
      r.inventory.replaceChildren(h('li', { class: 'ops-empty' }, 'No items in your inventory yet.'));
      return;
    }
    r.inventory.replaceChildren(
      ...items.map((it) => {
        const qty = itemQty(it);
        return h(
          'li',
          { class: `ops-item ops-item--${safeRarity(it.rarity)}`, title: it.description ? String(it.description) : itemName(it) },
          h('span', { class: 'ops-item__glyph', 'aria-hidden': 'true' }, String(it.icon ?? itemName(it)).trim().charAt(0).toUpperCase() || '◆'),
          h('span', { class: 'ops-item__text' }, h('span', { class: 'ops-item__name' }, itemName(it)), it.rarity ? h('span', { class: 'ops-item__rarity label' }, String(it.rarity)) : null),
          qty !== 1 ? h('span', { class: 'ops-item__qty mono' }, `×${qty}`) : null,
        );
      }),
    );
  }

  #renderMilestones(milestones) {
    const list = toList(milestones);
    const r = this.#r;
    if (!list.length) {
      r.milestones.replaceChildren(h('li', { class: 'ops-empty' }, 'No milestones yet.'));
      return;
    }
    const sorted = [...list].sort((a, b) => Number(milestoneDone(a)) - Number(milestoneDone(b)));
    r.milestones.replaceChildren(
      ...sorted.map((m) => {
        const done = milestoneDone(m);
        const progress = m.progress !== undefined && m.progress !== null ? clamp01(m.progress) : done ? 1 : null;
        return h(
          'li',
          { class: `ops-milestone ${done ? 'is-done' : ''}` },
          h('span', { class: 'ops-milestone__mark', 'aria-hidden': 'true' }, done ? '✓' : '◇'),
          h(
            'span',
            { class: 'ops-milestone__text' },
            h('span', { class: 'ops-milestone__name' }, String(m.title ?? m.name ?? m.id ?? 'Milestone')),
            m.description ? h('span', { class: 'ops-milestone__desc' }, String(m.description)) : null,
            progress !== null && !done ? h('span', { class: 'meter ops-milestone__meter', style: `--value: ${progress.toFixed(4)}` }, h('span', { class: 'meter__fill' })) : null,
          ),
          h('span', { class: 'visually-hidden' }, done ? 'achieved' : 'in progress'),
        );
      }),
    );
  }

  #renderHabits(habits) {
    const list = toList(habits);
    const r = this.#r;
    if (!list.length) {
      r.habits.replaceChildren(h('li', { class: 'ops-empty' }, 'No protocols tracked.'));
      return;
    }
    r.habits.replaceChildren(
      ...list.map((hb) => {
        const measured = typeof hb.value === 'number' && Number.isFinite(hb.value);
        const done = Boolean(hb.done_today ?? hb.completed_today ?? hb.done ?? hb.completed ?? (typeof hb.value === 'boolean' ? hb.value : false));
        const streak = hb.streak ?? hb.current_streak_days ?? hb.streak_days;
        const unit = hb.habit_key?.endsWith('_minutes') ? ' min' : hb.habit_key === 'weight_lbs' ? ' lb' : '';
        return h(
          'li',
          { class: `ops-habit ${done ? 'is-done' : ''}` },
          h('span', { class: 'ops-habit__mark', 'aria-hidden': 'true' }, measured ? '•' : done ? '■' : '□'),
          h('span', { class: 'ops-habit__name' }, String(hb.title ?? hb.name ?? hb.habit_key ?? 'Protocol').replaceAll('_', ' ')),
          measured ? h('span', { class: 'ops-habit__streak mono' }, `${hb.value}${unit}`) : null,
          streak !== undefined && streak !== null ? h('span', { class: 'ops-habit__streak mono' }, `${num(streak)}d`) : null,
          h('span', { class: 'visually-hidden' }, measured ? 'recorded today' : done ? 'done today' : 'not done today'),
        );
      }),
    );
  }

  #renderFeed(activity) {
    const list = toList(activity).slice(0, FEED_LIMIT);
    const r = this.#r;
    if (!list.length) {
      r.feed.replaceChildren(h('li', { class: 'ops-empty' }, 'No activity yet. Your first log appears here.'));
      return;
    }
    r.feed.replaceChildren(
      ...list.map((a, i) => {
        const d = describeActivity(a);
        const kind = ['study', 'workout', 'weight'].includes(a.kind) ? a.kind : 'other';
        return h(
          'li',
          { class: `ops-event ops-event--${kind}`, style: `--i: ${i}`, dataset: { id: String(a.id ?? '') } },
          h('span', { class: 'ops-event__glyph', 'aria-hidden': 'true' }, d.glyph),
          h('span', { class: 'ops-event__text' }, h('span', { class: 'ops-event__title' }, d.title), d.sub ? h('span', { class: 'ops-event__sub' }, d.sub) : null),
          h('span', { class: 'ops-event__meta' }, num(a.xp_awarded) > 0 ? h('span', { class: 'ops-event__xp mono' }, `+${num(a.xp_awarded)} XP`) : null, h('span', { class: 'ops-event__date mono' }, String(a.log_date ?? ''))),
        );
      }),
    );
  }

  #renderJobs(jobs, milestones) {
    const list = toList(jobs);
    const r = this.#r;
    r.jobsWrap.hidden = list.length === 0;
    r.jobs.replaceChildren(
      ...list.slice(0, 6).map((job) => {
        const localPayload = job.schema_version === 'neon.cinematic.v1';
        const milestone = toList(milestones).find(item => item.id === job.reward?.milestone_id);
        const state = String(job.state ?? job.status ?? (localPayload ? 'ready for export' : 'queued')).toLowerCase();
        const tone = state === 'done' || state === 'completed' ? 'chip--ok' : state === 'failed' ? 'chip--bad' : state === 'offline' ? '' : 'chip--warn';
        return h(
          'li',
          { class: 'ops-job' },
          h('span', { class: 'ops-job__name' }, String(job.title ?? milestone?.title ?? job.milestone ?? job.reward?.category ?? job.kind ?? job.id ?? 'Reward')),
          h('span', { class: `chip ${tone}` }, state),
        );
      }),
    );
  }

  // ── tabs ──────────────────────────────────────────────────────────────

  #selectTab(kind, { focus }) {
    const r = this.#r;
    if (!r.forms?.has(kind)) return;
    const changed = this.#tab !== kind;
    this.#tab = kind;
    const index = FORMS.findIndex((f) => f.kind === kind);
    r.tablist.style.setProperty('--index', String(index));
    for (const [k, tab] of r.tabs) {
      const on = k === kind;
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
      tab.tabIndex = on ? 0 : -1;
      tab.classList.toggle('is-on', on);
    }
    for (const [k, form] of r.forms) form.hidden = k !== kind;
    if (changed) this.#ctx.bus.emit('ui:click', {});
    if (focus === 'tab') r.tabs.get(kind).focus();
    else if (focus) r.forms.get(kind).querySelector('input:not([type="date"]), select')?.focus();
  }

  // ── validation ────────────────────────────────────────────────────────

  #clearFieldError(control) {
    if (!(control instanceof HTMLElement) || !control.classList.contains('ops-input')) return;
    control.removeAttribute('aria-invalid');
    const err = document.getElementById(`${control.id}-err`);
    if (err) err.textContent = '';
  }

  #fieldError(form, name, message) {
    const control = form.elements.namedItem(name);
    if (!control) return;
    control.setAttribute('aria-invalid', 'true');
    const err = document.getElementById(`${control.id}-err`);
    if (err) err.textContent = message;
  }

  /** Build the request payload from a form, or return {errors} for inline display. */
  #payload(kind, form) {
    const value = (name) => String(form.elements.namedItem(name)?.value ?? '').trim();
    const errors = [];
    const payload = {};
    const intField = (name, label, { min, max, required }) => {
      const raw = value(name);
      if (!raw) {
        if (required) errors.push([name, `${label} is required.`]);
        return;
      }
      const n = Number(raw);
      if (!Number.isInteger(n)) errors.push([name, `${label} must be a whole number.`]);
      else if (n < min || n > max) errors.push([name, `${label} must be ${min}–${max}.`]);
      else payload[name] = n;
    };
    const decField = (name, label, { min, max, required }) => {
      const raw = value(name);
      if (!raw) {
        if (required) errors.push([name, `${label} is required.`]);
        return;
      }
      const n = Number(raw);
      if (!Number.isFinite(n)) errors.push([name, `${label} must be a number.`]);
      else if (n < min || n > max) errors.push([name, `${label} must be ${min}–${max}.`]);
      else payload[name] = Math.round(n * 100) / 100;
    };
    const textField = (name, label, { max, required }) => {
      const raw = value(name);
      if (!raw) {
        if (required) errors.push([name, `${label} is required.`]);
        return;
      }
      if (raw.length > max) errors.push([name, `${label} must be at most ${max} characters.`]);
      else payload[name] = raw;
    };

    if (kind === 'study') {
      const course = value('course');
      if (!COURSES.includes(course)) errors.push(['course', 'Pick a course.']);
      else payload.course = course;
      intField('minutes', 'Minutes', { min: 1, max: 1440, required: true });
      textField('topic', 'Topic', { max: 200 });
    } else if (kind === 'workout') {
      textField('activity', 'Activity', { max: 80, required: true });
      intField('minutes', 'Minutes', { min: 1, max: 1440, required: true });
      intField('sets', 'Sets', { min: 0, max: 1000 });
      intField('reps', 'Reps', { min: 0, max: 10000 });
      decField('load_lbs', 'Load', { min: 0, max: 2000 });
      decField('distance_miles', 'Distance', { min: 0, max: 500 });
      textField('note', 'Note', { max: 500 });
    } else if (kind === 'weight') {
      decField('weight_lbs', 'Weight', { min: 50, max: 800, required: true });
    }

    const date = value('on_date');
    if (date) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) errors.push(['on_date', 'Use YYYY-MM-DD.']);
      else if (this.#snap?.date && date > this.#snap.date) errors.push(['on_date', 'Future dates cannot be logged.']);
      else payload.on_date = date;
    }
    return errors.length ? { errors } : { payload };
  }

  // ── submission ────────────────────────────────────────────────────────

  #setStatus(form, text, tone = '') {
    form._status.textContent = text;
    form._status.className = `ops-form__status ${tone ? `is-${tone}` : ''}`;
  }

  async #submit(kind) {
    const r = this.#r;
    const form = r.forms?.get(kind);
    if (!form || this.#busy.has(kind)) return;
    if (!this.#snap) {
      this.#setStatus(form, 'Waiting for the command center to sync…', 'warn');
      return;
    }
    for (const control of form.querySelectorAll('.ops-input')) this.#clearFieldError(control);
    const { payload, errors } = this.#payload(kind, form);
    if (errors) {
      for (const [name, message] of errors) this.#fieldError(form, name, message);
      form.elements.namedItem(errors[0][0])?.focus();
      this.#setStatus(form, 'Fix the highlighted fields.', 'bad');
      this.#ctx.bus.emit('ui:error', {});
      return;
    }

    const body = { ...payload, request_id: this.#ledger.idFor(kind, payload) };
    const call = { study: 'logStudy', workout: 'logWorkout', weight: 'logWeight' }[kind];
    this.#busy.add(kind);
    form.classList.add('is-sending');
    form._submit.disabled = true;
    form.setAttribute('aria-busy', 'true');
    this.#setStatus(form, 'Transmitting…');
    this.#ctx.bus.emit('ui:click', {});

    try {
      let result = null;
      for (let attempt = 0; ; attempt++) {
        try {
          result = await this.#ctx.api[call](body);
          break;
        } catch (err) {
          if (!isUncertain(err)) {
            this.#ledger.settle(kind); // definite answer: this id is spent
            throw err;
          }
          if (attempt >= RETRY_DELAYS_MS.length || !this.#alive) throw err;
          this.#setStatus(form, `Link unstable — retrying (${attempt + 2}/${RETRY_DELAYS_MS.length + 1})…`, 'warn');
          await sleep(RETRY_DELAYS_MS[attempt]);
          if (!this.#alive) throw err;
        }
      }
      this.#ledger.settle(kind);
      if (!this.#alive) return;
      this.#onLogged(kind, form, result);
    } catch (err) {
      if (!this.#alive) return;
      if (isUncertain(err)) {
        this.#setStatus(form, `Not confirmed — ${err?.message || 'link lost'}. Submit again to retry safely; it will not double-log.`, 'bad');
      } else {
        const field = this.#fieldForServerError(kind, err?.message);
        if (field) this.#fieldError(form, field, err.message);
        this.#setStatus(form, `Rejected — ${err?.message || 'invalid entry'}`, 'bad');
      }
      this.#ctx.bus.emit('ui:error', {});
    } finally {
      this.#busy.delete(kind);
      if (this.#alive) {
        form.classList.remove('is-sending');
        form._submit.disabled = false;
        form.removeAttribute('aria-busy');
      }
    }
  }

  /** Point a 400 message at the field it names, when it names one. */
  #fieldForServerError(kind, message = '') {
    const text = String(message).toLowerCase();
    const fields = {
      study: ['course', 'minutes', 'topic', 'on_date'],
      workout: ['activity', 'minutes', 'sets', 'reps', 'load_lbs', 'distance_miles', 'note', 'on_date'],
      weight: ['weight_lbs', 'on_date'],
    }[kind];
    return fields.find((f) => text.includes(f) || text.includes(f.replace('_', ' '))) || (text.includes('date') ? 'on_date' : null);
  }

  #onLogged(kind, form, result) {
    const activity = result?.activity || {};
    const xp = num(activity.xp_awarded);
    const labels = { study: 'Study session logged', workout: 'Workout logged', weight: 'Weigh-in logged' };
    this.#setStatus(form, xp > 0 ? `${labels[kind]} · +${xp} XP` : labels[kind], 'ok');
    // Keep the course (sessions often repeat it); clear everything else.
    for (const control of form.querySelectorAll('.ops-input')) {
      if (control.name !== 'course') control.value = '';
    }
    if (result?.snapshot) this.#adopt(result.snapshot);
    const at = rectCenter(form._submit);
    this.#ctx.bus.emit('ui:save', {});
    this.#ctx.bus.emit('reward:stamp', at);
    if (xp > 0) {
      this.#ctx.bus.emit('reward:tick', {});
      this.#ctx.toast(`+${xp} XP — ${labels[kind].toLowerCase()}.`, { kind: 'ok', title: 'LOGGED', ms: 2600 });
    }
    if (!settings.get('reducedMotion')) {
      const row = this.#r.feed.querySelector('.ops-event');
      row?.classList.add('is-new');
    }
    form.querySelector('input:not([type="date"]):not([name="course"]), select')?.focus({ preventScroll: true });
  }
}

function escapeText(text) {
  return String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}
