/**
 * CutsceneScreen — the transmission after a breach (docs/ARCHITECTURE.md §4.2, §3.4).
 *
 * Staging: the world shader in `cinematic` mood is the set; letterbox bars ease in to 2.39:1;
 * a title card ("TRANSMISSION // <TITLE>") decodes, holds, and clears; the narration then
 * plays as subtitles in the lower bar (typewriter, subtle `ui:type` every few characters,
 * a reading pause scaled to line length between lines).
 *
 * Media: `api.cutscene(id)` answers queued | done | offline. While a render is in flight a
 * "RENDERING MEMORY FRAGMENT" indicator tracks `server:cutscene` events for this mission;
 * each finished stage (a still, then optionally a video) cross-fades in over the previous one
 * with a slow Ken Burns move. Offline or failed renders leave the world shader alone on
 * screen, which is still a complete scene: cinematic mood, letterbox, light leak, timecode.
 *
 * Esc / Enter / click skip to the end. The finish fades out and goes to the hub, passing
 * `unlocked` (the next mission id from the victory result) so the hub can stage the unlock.
 * Params: `{mission}` per the contract, plus optional `result` / `unlocked` from victory.
 */
import { h, decodeText, typewriter, nextFrame } from '../dom.js';
import { settings } from '../../core/settings.js';

const BAR_IN_MS = 900;
const TITLE_DELAY_MS = 450;
const TITLE_HOLD_MS = 1900;
const TITLE_OUT_MS = 650;
const CPS = 34;
const TYPE_EVERY = 3; // ui:type every N characters
const LINE_HOLD_MS = 1300;
const LINE_HOLD_PER_CHAR_MS = 22;
const LINE_OUT_MS = 420;
const END_HOLD_MS = 900;
const FADE_OUT_MS = 650;
const MEDIA_FADE_MS = 1800;
const TIMECODE_FPS = 24;
const VIDEO_EXT = /\.(mp4|webm|mov|m4v)(?:[?#]|$)/i;

// Ken Burns moves: [fromScale, toScale, fromX%, fromY%, toX%, toY%]
const KEN_BURNS = [
  [1.06, 1.2, -1.5, 1, 2, -1.5],
  [1.2, 1.07, 2, -1.5, -1.5, 1],
  [1.08, 1.22, 2, 1.5, -2, -1],
  [1.18, 1.06, -2, -1, 1.5, 1.5],
];

const reduced = () => settings.get('reducedMotion');

export class CutsceneScreen {
  el = null;

  #ctx;
  #alive = false;
  #finishing = false;
  #mission = null;
  #unlocked;
  #timers = new Set();
  #intervals = new Set();
  #offs = [];
  #writer = null;
  #r = {};
  #media = []; // mounted media layers, newest last
  #mediaUrls = new Set();
  #startedAt = 0;
  #frameShown = -1;
  #eventSeq = 0; // bumps on every server:cutscene event for this mission
  #statusSeq = 0; // bumps on every indicator change (guards deferred show/hide)
  #onClick = (e) => {
    if (e.button === 0) this.#finish();
  };

  constructor(ctx) {
    this.#ctx = ctx;
  }

  async enter(params = {}) {
    const ctx = this.#ctx;
    this.#alive = true;
    this.#finishing = false;
    this.#media = [];
    this.#mediaUrls = new Set();
    this.#r = {};
    this.#frameShown = -1;
    this.#eventSeq = 0;
    this.#mission = params.mission || {};
    const result = params.result;
    this.#unlocked =
      params.unlocked !== undefined ? params.unlocked : result && !result.reward?.replay && result.next ? result.next.id : undefined;

    this.#build();
    this.el.addEventListener('pointerdown', this.#onClick);
    this.#offs.push(ctx.bus.on('server:cutscene', (data) => this.#onEvent(data)));

    ctx.bus.emit('mood', { name: 'cinematic' });
    ctx.renderer?.setFocus?.(0);

    this.#startedAt = performance.now();
    this.#every(() => this.#tickTimecode(), 1000 / TIMECODE_FPS);
    this.#requestMedia();
    this.#play();
  }

  async exit() {
    this.#alive = false;
    this.el?.removeEventListener('pointerdown', this.#onClick);
    this.#writer?.skip();
    this.#writer = null;
    for (const off of this.#offs) off();
    this.#offs.length = 0;
    for (const t of this.#timers) clearTimeout(t);
    this.#timers.clear();
    for (const t of this.#intervals) clearInterval(t);
    this.#intervals.clear();
    for (const layer of this.#media) {
      const video = layer.querySelector('video');
      if (video) {
        video.pause();
        video.removeAttribute('src');
        video.load();
      }
    }
    this.#media = [];
  }

  onKey(e) {
    if (e.key === 'Escape' || e.key === 'Enter') {
      e.preventDefault();
      this.#finish();
      return true;
    }
    return false;
  }

  // ── DOM ─────────────────────────────────────────────────────────────

  #build() {
    const r = this.#r;
    const m = this.#mission;
    const cut = m.cutscene || { title: m.title || 'TRANSMISSION', narration: [] };

    r.media = h('div', { class: 'cs-media', 'aria-hidden': 'true' });
    r.leak = h('div', { class: 'cs-leak', 'aria-hidden': 'true' });
    r.titleName = h('h1', { class: 'cs-title__name' }, ' ');
    r.title = h(
      'div',
      { class: 'cs-title' },
      h('div', { class: 'cs-title__kicker' }, h('span', { class: 'cs-title__rule' }), h('span', {}, 'TRANSMISSION //'), h('span', { class: 'cs-title__rule' })),
      r.titleName,
      h('div', { class: 'cs-title__meta mono' }, `${m.id || ''} · ${m.enemy ? `${m.enemy} DELETED` : 'MEMORY FRAGMENT'}`),
    );
    r.subs = h('div', { class: 'cs-subs', 'aria-live': 'polite' });
    r.status = h(
      'div',
      { class: 'cs-status', hidden: true, role: 'status' },
      h('span', { class: 'cs-status__ring', 'aria-hidden': 'true' }),
      h('span', { class: 'cs-status__text' }, h('span', { class: 'cs-status__label' }, 'RENDERING MEMORY FRAGMENT'), h('span', { class: 'cs-status__stage mono' }, 'STILL')),
    );
    r.timecode = h('span', { class: 'cs-hud__tc mono' }, '00:00:00:00');
    r.source = h('span', { class: 'cs-hud__src label' }, 'IN-ENGINE RECONSTRUCTION');
    r.skip = h('div', { class: 'cs-skip label' }, 'SKIP ', h('span', { class: 'kbd' }, 'ESC'));

    this.el = h(
      'section',
      { class: 'screen screen--cutscene', 'aria-label': `Transmission: ${cut.title}` },
      r.media,
      r.leak,
      h('div', { class: 'cs-shade', 'aria-hidden': 'true' }),
      h('div', { class: 'cs-bar cs-bar--top', 'aria-hidden': 'true' }),
      h('div', { class: 'cs-bar cs-bar--bottom', 'aria-hidden': 'true' }),
      h(
        'div',
        { class: 'cs-hud cs-hud--top', 'aria-hidden': 'true' },
        h('span', { class: 'cs-hud__rec' }, h('i'), `MEMORY FRAGMENT // ${m.id || ''}`),
        r.timecode,
      ),
      h('div', { class: 'cs-hud cs-hud--bottom', 'aria-hidden': 'true' }, r.source, r.skip),
      r.title,
      r.subs,
      r.status,
    );
  }

  // ── script ──────────────────────────────────────────────────────────

  async #play() {
    const r = this.#r;
    const cut = this.#mission.cutscene || { title: this.#mission.title || 'TRANSMISSION', narration: [] };
    const fast = reduced();
    // Two frames: the bars must be painted collapsed once, or the ease-in has no start state.
    await nextFrame();
    await nextFrame();
    if (!this.#alive) return;
    this.el.classList.add('is-rolling'); // bars ease in
    await this.#wait(fast ? 0 : TITLE_DELAY_MS);
    if (!this.#alive) return;

    // title card
    r.title.classList.add('is-in');
    this.#ctx.bus.emit('ui:decode', {});
    await decodeText(r.titleName, String(cut.title || '').toUpperCase(), { duration: 1000 });
    if (!this.#alive) return;
    await this.#wait(fast ? 1200 : TITLE_HOLD_MS);
    if (!this.#alive) return;
    r.title.classList.add('is-out');
    await this.#wait(Math.max(BAR_IN_MS - TITLE_DELAY_MS, TITLE_OUT_MS));
    if (!this.#alive) return;
    r.skip.classList.add('is-in');

    // narration
    const lines = Array.isArray(cut.narration) ? cut.narration : [];
    for (let i = 0; i < lines.length; i++) {
      const text = String(lines[i] || '');
      const line = h('p', { class: 'cs-line' });
      r.subs.replaceChildren(line);
      // Force the entrance to start from its initial state on the next frame.
      requestAnimationFrame(() => line.classList.add('is-in'));
      let typed = 0;
      this.#writer = typewriter(line, text, {
        cps: CPS,
        onChar: (ch) => {
          if (ch !== ' ' && ++typed % TYPE_EVERY === 0) this.#ctx.bus.emit('ui:type', {});
        },
      });
      await this.#writer.done;
      this.#writer = null;
      if (!this.#alive || this.#finishing) return;
      await this.#wait(LINE_HOLD_MS + text.length * LINE_HOLD_PER_CHAR_MS);
      if (!this.#alive || this.#finishing) return;
      line.classList.add('is-out');
      await this.#wait(LINE_OUT_MS);
      if (!this.#alive || this.#finishing) return;
    }

    await this.#wait(END_HOLD_MS);
    this.#finish();
  }

  #finish() {
    if (this.#finishing || !this.#alive) return;
    this.#finishing = true;
    this.#writer?.skip();
    this.el.classList.add('is-ending');
    this.#ctx.bus.emit('ui:close', {});
    this.#later(() => {
      if (!this.#alive) return;
      this.#ctx.screens.go('hub', this.#unlocked ? { unlocked: this.#unlocked } : {});
    }, reduced() ? 0 : FADE_OUT_MS);
  }

  // ── media ───────────────────────────────────────────────────────────

  async #requestMedia() {
    const id = this.#mission.id;
    if (!id) return;
    const seq = this.#eventSeq;
    let reply;
    try {
      reply = await this.#ctx.api.cutscene(id);
    } catch {
      return; // no media: the world shader carries the scene
    }
    if (!this.#alive || !reply) return;
    if (reply.state === 'done' && reply.url) {
      this.#showMedia(reply.url, reply.kind || this.#kindOf(reply.url));
      if (seq === this.#eventSeq) this.#setStatus(null);
    } else if (reply.state === 'queued' && seq === this.#eventSeq) {
      // SSE and this reply travel on different connections: a progress event that arrived
      // while the request was in flight is newer than this answer, so it wins.
      this.#setStatus('rendering', 'still');
    }
  }

  #onEvent(data) {
    if (!this.#alive || !data || data.mission !== this.#mission.id) return;
    this.#eventSeq++;
    switch (data.state) {
      case 'rendering':
        this.#setStatus('rendering', data.stage);
        break;
      case 'done':
        if (data.url) this.#showMedia(data.url, data.kind || this.#kindOf(data.url));
        // A finished still may be followed by a video pass; its own `rendering` event re-shows the indicator.
        this.#setStatus(null);
        break;
      case 'failed': {
        this.#setStatus('failed');
        const seq = this.#eventSeq;
        this.#later(() => seq === this.#eventSeq && this.#setStatus(null), 2200);
        break;
      }
      default:
        this.#setStatus(null);
    }
  }

  #kindOf(url) {
    if (VIDEO_EXT.test(url)) return 'video';
    const gallery = this.#ctx.state?.gallery || [];
    const entry = gallery.find((g) => g.url === url);
    return entry?.kind === 'video' ? 'video' : 'image';
  }

  /** Show ('rendering' | 'failed') or hide (null) the render indicator; the latest call wins. */
  #setStatus(state, stage) {
    const el = this.#r.status;
    if (!el) return;
    const seq = ++this.#statusSeq;
    if (!state) {
      el.classList.remove('is-in');
      this.#later(() => {
        if (seq === this.#statusSeq) el.hidden = true;
      }, 400);
      return;
    }
    el.hidden = false;
    el.dataset.state = state;
    el.querySelector('.cs-status__label').textContent = state === 'failed' ? 'SIGNAL LOST — IN-ENGINE RECONSTRUCTION' : 'RENDERING MEMORY FRAGMENT';
    el.querySelector('.cs-status__stage').textContent = state === 'failed' ? '' : stage === 'video' ? 'MOTION PASS' : 'STILL';
    // Next frame, so the fade starts from the hidden state — unless a newer call superseded it.
    requestAnimationFrame(() => {
      if (seq === this.#statusSeq && this.#alive) el.classList.add('is-in');
    });
  }

  #showMedia(url, kind) {
    if (this.#mediaUrls.has(url) || !this.#alive) return;
    this.#mediaUrls.add(url);
    const move = KEN_BURNS[(Math.random() * KEN_BURNS.length) | 0];
    const layer = h('div', {
      class: 'cs-layer',
      style: `--kb-s0:${move[0]};--kb-s1:${move[1]};--kb-x0:${move[2]}%;--kb-y0:${move[3]}%;--kb-x1:${move[4]}%;--kb-y1:${move[5]}%`,
    });
    const reveal = () => {
      if (!this.#alive || !layer.isConnected) return;
      requestAnimationFrame(() => layer.classList.add('is-in'));
      this.#r.source.textContent = kind === 'video' ? 'HIGGSFIELD // MOTION' : 'HIGGSFIELD // STILL';
      // Retire layers fully covered by this one once the cross-fade completes.
      const older = this.#media.slice(0, -1);
      this.#later(() => {
        for (const old of older) {
          old.querySelector('video')?.pause();
          old.remove();
        }
        this.#media = this.#media.filter((l) => !older.includes(l));
      }, MEDIA_FADE_MS + 200);
    };
    const fail = () => layer.remove();

    if (kind === 'video') {
      const video = h('video', { class: 'cs-layer__media', muted: true, loop: true, playsinline: true, autoplay: true, preload: 'auto' });
      video.muted = true; // the attribute alone does not satisfy autoplay policies everywhere
      video.addEventListener('loadeddata', () => {
        reveal();
        video.play().catch(() => {});
      }, { once: true });
      video.addEventListener('error', fail, { once: true });
      video.src = url;
      layer.append(video);
    } else {
      const img = h('img', { class: 'cs-layer__media', alt: '', decoding: 'async' });
      img.addEventListener('load', reveal, { once: true });
      img.addEventListener('error', fail, { once: true });
      img.src = url;
      layer.append(img);
    }
    this.#r.media.append(layer);
    this.#media.push(layer);
  }

  // ── HUD ─────────────────────────────────────────────────────────────

  #tickTimecode() {
    const frames = Math.floor(((performance.now() - this.#startedAt) / 1000) * TIMECODE_FPS);
    if (frames === this.#frameShown) return;
    this.#frameShown = frames;
    const f = frames % TIMECODE_FPS;
    const s = Math.floor(frames / TIMECODE_FPS);
    this.#r.timecode.textContent = `00:${pad(Math.floor(s / 60))}:${pad(s % 60)}:${pad(f)}`;
  }

  // ── tracked timers ──────────────────────────────────────────────────

  #later(fn, ms) {
    const t = setTimeout(() => {
      this.#timers.delete(t);
      fn();
    }, ms);
    this.#timers.add(t);
    return t;
  }

  #wait(ms) {
    return new Promise((resolve) => this.#later(resolve, ms));
  }

  #every(fn, ms) {
    const t = setInterval(fn, ms);
    this.#intervals.add(t);
    return t;
  }
}

const pad = (n) => String(n).padStart(2, '0');
