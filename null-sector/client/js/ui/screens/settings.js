/**
 * SettingsOverlay — "SYSTEM CONFIG", the in-game options menu (docs/ARCHITECTURE.md §4.2).
 *
 * A modal over a blurred backdrop, mounted in #settings-root (above the camera-shaken #ui, so
 * it stays rock steady while previewing shake). Every control writes straight to `settings`;
 * the subsystems listen to `settings.onChange`, so changes apply live:
 *   volumes → a click at the new level · screen shake → a test kick · CRT → the overlay and
 *   post stack · bloom / quality → the renderer · reduced motion → body class and helpers.
 *
 * Built once on first open and reused (opening is instant); values are re-synced from
 * `settings` on every open and whenever a setting changes while it is open (e.g. reset).
 *
 * Accessibility: role=dialog + aria-modal, #ui is made `inert` while open, Tab/Shift+Tab are
 * trapped inside the panel, focus returns to whatever had it before. Esc or the close button
 * closes. Sliders are native range inputs (full keyboard support), toggles are role=switch
 * buttons and the quality picker is a radiogroup with arrow-key roving focus.
 */
import { h, $$ } from '../dom.js';
import { settings } from '../../core/settings.js';

const CLOSE_MS = 240;
const PREVIEW_GAP_MS = 110;
const SHAKE_GAP_MS = 260;
const STATS_MS = 500;

const ICON_CLOSE = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 3.5l9 9m0-9l-9 9" stroke="currentColor" stroke-width="1.6"/></svg>';
const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Control definitions, grouped. Ranges are stored 0..1 and shown as percentages. */
const GROUPS = [
  {
    title: 'Audio',
    items: [
      { key: 'masterVolume', type: 'range', label: 'Master volume', preview: 'click' },
      { key: 'musicVolume', type: 'range', label: 'Music', preview: 'click' },
      { key: 'sfxVolume', type: 'range', label: 'Effects', preview: 'click' },
      { key: 'typingSounds', type: 'toggle', label: 'Typing sounds', hint: 'Keystroke ticks in the code editor' },
    ],
  },
  {
    title: 'Visuals',
    items: [
      { key: 'quality', type: 'choice', label: 'Quality', options: [['auto', 'Auto'], ['high', 'High'], ['medium', 'Med'], ['low', 'Low']] },
      { key: 'bloom', type: 'toggle', label: 'Bloom', hint: 'Neon light bleed' },
      { key: 'crt', type: 'range', label: 'CRT / post FX', hint: 'Scanlines, grain, lens' },
      { key: 'shake', type: 'range', label: 'Screen shake', preview: 'shake' },
    ],
  },
  {
    title: 'Accessibility',
    items: [{ key: 'reducedMotion', type: 'toggle', label: 'Reduced motion', hint: 'Calmer camera, no flicker, instant text' }],
  },
];

const CONTROLS = [
  [['Enter'], 'Deploy to target'],
  [['Ctrl', '↵'], 'Hack'],
  [['Ctrl', 'S'], 'Save code'],
  [['←', '→', '↑', '↓'], 'Walk the map'],
  [['Esc'], 'Menu · back'],
];

export class SettingsOverlay {
  #ctx;
  #root;
  #el = null;
  #panel = null;
  #controls = new Map(); // key → {sync(value)}
  #stats = null;
  #open = false;
  #prevFocus = null;
  #offChange = null;
  #closeTimer = 0;
  #statsTimer = 0;
  #lastPreview = 0;
  #lastShake = 0;
  #onKeyDown = (e) => this.#keydown(e);

  /**
   * @param {object} ctx    the app ctx (bus, camera, renderer, loop, toast)
   * @param {HTMLElement} [root]  mount point, #settings-root by default
   */
  constructor(ctx, root = document.getElementById('settings-root')) {
    this.#ctx = ctx;
    this.#root = root;
  }

  get isOpen() {
    return this.#open;
  }

  open() {
    if (this.#open || !this.#root) return;
    if (!this.#el) this.#build();
    this.#open = true;
    clearTimeout(this.#closeTimer);
    this.#prevFocus = document.activeElement;
    for (const [key, control] of this.#controls) control.sync(settings.get(key));
    this.#offChange = settings.onChange((key, value) => this.#controls.get(key)?.sync(value));

    const ui = document.getElementById('ui');
    if (ui) ui.inert = true;
    document.body.classList.add('settings-open');
    this.#el.hidden = false;
    this.#el.classList.remove('is-closing');
    void this.#el.offsetWidth; // start the entry transition from the closed state
    this.#el.classList.add('is-open');
    document.addEventListener('keydown', this.#onKeyDown, true);
    this.#ctx.bus.emit('ui:open', {});

    this.#updateStats();
    this.#statsTimer = setInterval(() => this.#updateStats(), STATS_MS);
    // Start on the first control (not the close button), so arrows adjust a value immediately.
    this.#panel.querySelector(`.settings__body :is(${FOCUSABLE})`)?.focus({ preventScroll: true });
  }

  close() {
    if (!this.#open) return;
    this.#open = false;
    this.#offChange?.();
    this.#offChange = null;
    clearInterval(this.#statsTimer);
    document.removeEventListener('keydown', this.#onKeyDown, true);

    const ui = document.getElementById('ui');
    if (ui) ui.inert = false;
    document.body.classList.remove('settings-open');
    this.#el.classList.remove('is-open');
    this.#el.classList.add('is-closing');
    this.#closeTimer = setTimeout(() => {
      this.#el.classList.remove('is-closing');
      this.#el.hidden = true;
    }, settings.get('reducedMotion') ? 0 : CLOSE_MS);
    this.#ctx.bus.emit('ui:close', {});

    const prev = this.#prevFocus;
    this.#prevFocus = null;
    if (prev instanceof HTMLElement && prev.isConnected) prev.focus({ preventScroll: true });
  }

  toggle() {
    if (this.#open) this.close();
    else this.open();
  }

  // ── keyboard: Esc closes, Tab is trapped ──────────────────────────────

  #keydown(e) {
    if (!this.#open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      if (!e.repeat) this.close();
      return;
    }
    if (e.key !== 'Tab') return;
    const items = $$(FOCUSABLE, this.#panel).filter((el) => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const inside = this.#panel.contains(document.activeElement);
    if (e.shiftKey && (document.activeElement === first || !inside)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (document.activeElement === last || !inside)) {
      e.preventDefault();
      first.focus();
    }
  }

  // ── DOM ───────────────────────────────────────────────────────────────

  #build() {
    this.#stats = h('span', { class: 'settings__stats mono', 'aria-live': 'off' });
    const groups = GROUPS.map((group, gi) =>
      h(
        'section',
        { class: 'settings__group', style: `--i: ${gi}` },
        h('h3', { class: 'settings__group-title label' }, group.title),
        ...group.items.map((item) => this.#control(item)),
      ),
    );
    const controls = h(
      'section',
      { class: 'settings__group settings__group--keys', style: `--i: ${GROUPS.length}` },
      h('h3', { class: 'settings__group-title label' }, 'Controls'),
      h(
        'dl',
        { class: 'settings__keys' },
        ...CONTROLS.flatMap(([keys, what]) => [
          h('dt', null, ...keys.map((k) => h('span', { class: 'kbd' }, k))),
          h('dd', null, what),
        ]),
      ),
    );

    this.#panel = h(
      'div',
      { class: 'panel settings__panel', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'settings-title' },
      h(
        'div',
        { class: 'panel__head' },
        h('span', { class: 'panel__title', id: 'settings-title' }, 'System config'),
        h(
          'div',
          { class: 'settings__head-tools' },
          h('span', { class: 'kbd' }, 'ESC'),
          h('button', { class: 'icon-btn settings__close', type: 'button', 'aria-label': 'Close settings', html: ICON_CLOSE, onclick: () => this.close() }),
        ),
      ),
      h('div', { class: 'panel__body settings__body scroll' }, ...groups, controls),
      h(
        'div',
        { class: 'settings__foot' },
        this.#stats,
        h('button', { class: 'btn btn--ghost', type: 'button', onclick: () => this.#reset() }, 'Reset to defaults'),
        h('button', { class: 'btn btn--primary', type: 'button', onclick: () => this.close() }, 'Done'),
      ),
    );
    this.#el = h(
      'div',
      { class: 'settings', hidden: true },
      h('div', { class: 'settings__backdrop', onclick: () => this.close() }),
      this.#panel,
    );
    this.#root.append(this.#el);
  }

  #control(item) {
    if (item.type === 'range') return this.#range(item);
    if (item.type === 'toggle') return this.#toggle(item);
    return this.#choice(item);
  }

  #row(item, id, control, value) {
    return h(
      'div',
      { class: `setting setting--${item.type}` },
      h(
        'div',
        { class: 'setting__text' },
        h('label', { class: 'setting__label', for: id, id: `${id}-label` }, item.label),
        item.hint ? h('span', { class: 'setting__hint' }, item.hint) : null,
      ),
      control,
      value,
    );
  }

  #range(item) {
    const id = `setting-${item.key}`;
    const output = h('output', { class: 'setting__value mono', for: id });
    const input = h('input', { class: 'range', id, type: 'range', min: 0, max: 100, step: 1 });
    const sync = (v) => {
      const pct = Math.round(Number(v) * 100);
      input.value = String(pct);
      input.style.setProperty('--value', String(pct / 100));
      output.textContent = `${pct}%`;
      input.setAttribute('aria-valuetext', `${pct} percent`);
    };
    input.addEventListener('input', () => {
      const v = Number(input.value) / 100;
      settings.set(item.key, v);
      sync(v);
      this.#preview(item.preview, v);
    });
    this.#controls.set(item.key, { sync });
    return this.#row(item, id, h('div', { class: 'setting__control' }, input), output);
  }

  #toggle(item) {
    const id = `setting-${item.key}`;
    const state = h('span', { class: 'switch__state mono' });
    const button = h(
      'button',
      {
        class: 'switch',
        id,
        type: 'button',
        role: 'switch',
        'data-sfx': '',
        onclick: () => {
          const next = !settings.get(item.key);
          settings.set(item.key, next);
          if (item.key === 'typingSounds' && next) this.#ctx.bus.emit('ui:type', {});
        },
      },
      h('span', { class: 'switch__track' }, h('span', { class: 'switch__knob' })),
      state,
    );
    const sync = (v) => {
      button.setAttribute('aria-checked', String(!!v));
      state.textContent = v ? 'ON' : 'OFF';
    };
    this.#controls.set(item.key, { sync });
    return this.#row(item, id, h('div', { class: 'setting__control' }, button), null);
  }

  #choice(item) {
    const id = `setting-${item.key}`;
    const buttons = item.options.map(([value, text]) =>
      h('button', { class: 'segmented__opt', type: 'button', role: 'radio', 'data-value': value, 'data-sfx': '' }, text),
    );
    const group = h('div', { class: 'segmented', id, role: 'radiogroup', 'aria-labelledby': `${id}-label` }, ...buttons);
    const pick = (value, focus) => {
      settings.set(item.key, value);
      if (focus) buttons.find((b) => b.dataset.value === value)?.focus();
    };
    group.addEventListener('click', (e) => {
      const opt = e.target instanceof Element && e.target.closest('.segmented__opt');
      if (opt) pick(opt.dataset.value, false);
    });
    group.addEventListener('keydown', (e) => {
      const step = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[e.key];
      if (!step) return;
      e.preventDefault();
      const values = item.options.map(([v]) => v);
      const at = values.indexOf(settings.get(item.key));
      pick(values[(at + step + values.length) % values.length], true);
      this.#ctx.bus.emit('ui:click', {});
    });
    const sync = (v) => {
      let index = 0;
      buttons.forEach((b, i) => {
        const on = b.dataset.value === v;
        if (on) index = i;
        b.setAttribute('aria-checked', String(on));
        b.tabIndex = on ? 0 : -1;
      });
      group.style.setProperty('--index', String(index));
    };
    group.style.setProperty('--count', String(buttons.length));
    this.#controls.set(item.key, { sync });
    return this.#row(item, id, h('div', { class: 'setting__control' }, group), null);
  }

  // ── live preview ──────────────────────────────────────────────────────

  #preview(kind, value) {
    const now = performance.now();
    if (kind === 'click' && now - this.#lastPreview > PREVIEW_GAP_MS) {
      this.#lastPreview = now;
      this.#ctx.bus.emit('ui:click', {});
    } else if (kind === 'shake' && value > 0 && now - this.#lastShake > SHAKE_GAP_MS) {
      this.#lastShake = now;
      this.#ctx.camera?.addTrauma?.(0.32);
    }
  }

  #reset() {
    settings.reset();
    this.#ctx.toast?.('All settings restored to their defaults.', { kind: 'ok', title: 'DEFAULTS', ms: 2200 });
  }

  #updateStats() {
    const r = this.#ctx.renderer;
    const s = r?.stats;
    if (!r?.ok || !s) {
      this.#stats.textContent = 'CSS FALLBACK · NO WEBGL2';
      return;
    }
    const fps = Math.round(s.fps || this.#ctx.loop?.fps || 0);
    const ms = (s.ms || this.#ctx.loop?.frameMs || 0).toFixed(1);
    this.#stats.textContent = `${fps} FPS · ${ms} MS · RES ${Math.round((s.scale || 1) * 100)}%`;
  }
}

