/**
 * BootScreen — the cold start (docs/ARCHITECTURE.md §4.2).
 *
 * Timeline (first visit this browser session, ≈2.1 s to the prompt):
 *   0.00  black veil · typed BIOS log, one line at a time (label → dotted leader → result)
 *   1.15  the veil thins to reveal the world · NULL//SECTOR decodes out of glyph noise
 *   1.70  subtitle · 2.05 "PRESS ANY KEY TO JACK IN" + footer telemetry
 * On a reload in the same session (sessionStorage flag) the log is printed instantly and the
 * prompt arrives at ≈0.6 s. Reduced motion completes every beat immediately.
 *
 * Any key or click at any moment jacks in: unlock audio (this is the user gesture browsers
 * require), `ui:open`, a small camera kick and cyan flash, then `go('hub')`. Modifier and
 * function keys, Tab and Esc are ignored so browser shortcuts and the settings menu still work.
 *
 * Every pause goes through `#wait`, so `exit()` cancels the whole sequence in one sweep.
 */
import { h, decodeText, typewriter } from '../dom.js';
import { settings } from '../../core/settings.js';

const SEEN_KEY = 'nullsector.booted';
const LOGO = 'NULL//SECTOR';
const JACK_FLASH = [0.0, 0.94, 1.0];
const LOG_BUDGET_MS = 1150; // lines starting later than this print instantly
const LINE_GAP_MS = 60;
const RESULT_DELAY_MS = 70;

const IGNORED_KEYS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'Tab', 'Escape', 'ContextMenu', 'OS', 'Fn']);

export class BootScreen {
  #ctx;
  #alive = false;
  #leaving = false;
  #timers = new Set();
  #typers = new Set();
  #r = {};

  constructor(ctx) {
    this.#ctx = ctx;
  }

  async enter() {
    const ctx = this.#ctx;
    this.#alive = true;
    this.#leaving = false;
    const quick = this.#seen() || settings.get('reducedMotion');
    const r = (this.#r = {});

    r.log = h('div', { class: 'boot__log', 'aria-hidden': 'true' });
    r.logo = h('h1', { class: 'ns-logo boot__logo', 'data-text': LOGO, 'aria-label': LOGO });
    r.sub = h('p', { class: 'boot__sub' }, 'A Python survival RPG', h('i', { 'aria-hidden': 'true' }, '·'), 'Zero → AI engineer');
    r.prompt = h('p', { class: 'boot__prompt' }, h('span', { class: 'boot__prompt-text' }, 'Press any key to jack in'));
    r.meta = h(
      'div',
      { class: 'boot__meta mono', 'aria-hidden': 'true' },
      h('span', null, `CLIENT 1.0 · ${ctx.renderer?.ok ? 'WEBGL2 · HDR PIPELINE' : 'COMPATIBILITY MODE'}`),
      h('span', null, `${location.host || 'LOCALHOST'} · LINK ENCRYPTED`),
    );

    this.el = h(
      'section',
      {
        class: `screen screen--boot screen--staged${quick ? ' is-quick' : ''}`,
        'aria-label': 'NULL//SECTOR — press any key to start',
        onpointerdown: (e) => e.button === 0 && this.#jackIn(),
      },
      h('div', { class: 'boot__veil' }),
      r.log,
      h('div', { class: 'boot__center' }, r.logo, r.sub, r.prompt),
      r.meta,
    );

    ctx.bus.emit('mood', { name: 'cinematic' });
    ctx.renderer?.setFocus?.(0);
    this.#sequence(quick);
  }

  async exit() {
    this.#alive = false;
    for (const t of this.#timers) clearTimeout(t);
    this.#timers.clear();
    for (const typer of this.#typers) typer.skip();
    this.#typers.clear();
  }

  onKey(e) {
    if (IGNORED_KEYS.has(e.key) || /^F\d{1,2}$/.test(e.key) || e.ctrlKey || e.metaKey || e.altKey) return false;
    e.preventDefault();
    this.#jackIn();
    return true;
  }

  // ── sequence ──────────────────────────────────────────────────────────

  /**
   * Strictly sequential, so beats never reorder even when the first frames stall (shader
   * compilation, font decoding). Lines that would start after LOG_BUDGET_MS print instantly,
   * which keeps the prompt on time on slow machines.
   */
  async #sequence(quick) {
    const r = this.#r;
    const lines = this.#lines();
    if (quick) {
      for (const line of lines) r.log.append(this.#lineEl(line, true).el);
      await this.#wait(90);
      this.#reveal(380);
      await this.#wait(210);
      this.el.classList.add('show-sub');
      await this.#wait(260);
      this.#ready();
      return;
    }

    const start = performance.now();
    await this.#wait(120);
    for (const line of lines) {
      const late = performance.now() - start > LOG_BUDGET_MS;
      await this.#typeLine(line, late);
      if (!late) await this.#wait(LINE_GAP_MS);
    }
    this.#reveal(650);
    await this.#wait(520);
    this.el.classList.add('show-sub');
    await this.#wait(380);
    this.#ready();
  }

  /** Log content, personalised once the save has loaded (it usually has by line four). */
  #lines() {
    return [
      { label: 'NS-BIOS 4.0.1 · neural interface cold start', head: true },
      { label: 're-establishing neural link', result: 'OK' },
      { label: 'mounting /dev/consciousness', result: 'OK' },
      {
        label: 'verifying operative',
        result: () => {
          const callsign = this.#ctx.state?.profile?.callsign;
          return callsign ? [callsign.toUpperCase(), 'ok'] : ['UNREGISTERED', 'warn'];
        },
      },
      { label: 'scanning sector', result: 'HOSTILE PROCESSES DETECTED', kind: 'bad' },
    ];
  }

  #lineEl(line, complete) {
    const text = h('span', { class: 'boot__text' });
    const el = h(
      'div',
      { class: `boot__line${line.head ? ' boot__line--head' : ''}${line.kind === 'bad' ? ' boot__line--bad' : ''}` },
      h('span', { class: 'boot__caret' }, line.head ? '#' : '›'),
      text,
    );
    if (!line.head) el.append(h('span', { class: 'boot__leader' }), h('span', { class: 'boot__result' }));
    if (complete) {
      text.textContent = line.label;
      this.#finishLine(el, line, true);
    }
    return { el, text };
  }

  async #typeLine(line, instant) {
    const { el, text } = this.#lineEl(line, instant);
    this.#r.log.append(el);
    if (instant) return;
    const typer = typewriter(text, line.label, { cps: 260 });
    this.#typers.add(typer);
    await typer.done;
    this.#typers.delete(typer);
    el.classList.add('is-typed');
    await this.#wait(RESULT_DELAY_MS);
    this.#finishLine(el, line, false);
  }

  #finishLine(el, line, instant) {
    if (line.head) return el.classList.add('is-typed', 'is-done');
    const [value, kind] = typeof line.result === 'function' ? line.result() : [line.result, line.kind || 'ok'];
    const result = el.querySelector('.boot__result');
    result.textContent = value;
    result.dataset.kind = kind;
    el.classList.add('is-typed', 'is-done');
    if (!instant && kind === 'bad') this.#ctx.bus.emit('ui:glitch', {});
  }

  #reveal(duration) {
    if (!this.#alive) return;
    this.el.classList.add('is-revealed');
    this.#ctx.bus.emit('ui:decode', {});
    decodeText(this.#r.logo, LOGO, { duration });
  }

  #ready() {
    if (!this.#alive) return;
    this.el.classList.add('is-ready');
    try {
      sessionStorage.setItem(SEEN_KEY, '1');
    } catch {
      /* storage blocked: every boot is a full boot */
    }
  }

  // ── exit ──────────────────────────────────────────────────────────────

  #jackIn() {
    if (!this.#alive || this.#leaving) return;
    this.#leaving = true;
    const ctx = this.#ctx;
    try {
      ctx.audio?.unlock?.();
    } catch {
      /* audio is optional */
    }
    try {
      sessionStorage.setItem(SEEN_KEY, '1');
    } catch {
      /* ignore */
    }
    ctx.bus.emit('ui:open', {});
    // No catalogue event covers "jack in" (§5); a direct, small kick keeps it out of the feedback table.
    ctx.camera?.addTrauma?.(0.16);
    ctx.renderer?.flash?.(JACK_FLASH, 0.28);
    this.el.classList.add('is-jacking');
    ctx.screens.go('hub');
  }

  #seen() {
    try {
      return sessionStorage.getItem(SEEN_KEY) === '1';
    } catch {
      return false;
    }
  }

  /** Resolves after `ms` while the screen is alive; never resolves once `exit()` ran. */
  #wait(ms) {
    return new Promise((resolve) => {
      const t = setTimeout(() => {
        this.#timers.delete(t);
        if (this.#alive) resolve();
      }, ms);
      this.#timers.add(t);
    });
  }
}
