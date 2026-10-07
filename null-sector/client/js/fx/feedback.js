/**
 * FeedbackDirector — the single place where game feel is tuned.
 *
 * Gameplay code emits *meaning* on the bus ("layer 3 was breached, combo 2, from here to
 * there"); this module turns meaning into juice: camera trauma, hit-stop, particles, flashes,
 * mood blends and audio cues. The mapping is docs/ARCHITECTURE.md §5's feedback table,
 * written as one handler per event so every number lives in exactly one spot.
 *
 * Design notes
 *  - Handlers run on events, never per frame, and still avoid garbage: particle option
 *    objects are two reused scratch records (one per shape, so they stay monomorphic), colour
 *    triplets are module constants, and the glyph raster buffer only grows.
 *  - Every collaborator is optional. A renderer without WebGL2 (no-op particles), a missing
 *    or locked AudioEngine, or a missing camera all degrade to silence, never to a throw.
 *  - Mood is owned here: `mood` events and the moods implied by combat go through one
 *    `#setMood`, so the 1.6 s alarm → mission revert is cancelled by any newer mood.
 *  - Particle density follows `settings.quality` (high/auto 1, medium .6, low .35; in 'auto'
 *    also the renderer's adaptive render scale). It is applied through
 *    `particles.setDensity()` — which also decimates glyph points evenly — and re-synced
 *    lazily before each burst, so a quality change or a context restore (new Particles) is
 *    picked up without polling. Counts below are therefore pre-density.
 *  - Glyph disintegration: the mission sends one point per glyph; each is expanded into a
 *    small raster covering its cell (pitch inferred from the points), so the art dissolves
 *    as a cloud of bits that keeps its silhouette, released upward on a ragged front.
 *  - `ui:<cue>` events play the audio cue of the same name (hover, click, open, close, type,
 *    error, save, decode, …). Typing ticks respect `typingSounds`.
 *  - Flashes are halved under `reducedMotion` (photosensitivity), on top of the camera's own
 *    reduced-motion shake scaling.
 *  - `world:lightning` only adds trauma here: AudioEngine subscribes to it itself and
 *    schedules the delayed thunder (§4.4), so doing it here too would double every strike.
 */
import { bus as defaultBus } from '../core/bus.js';
import { settings as defaultSettings } from '../core/settings.js';

// Mood colours mirror the renderer's presets (§4.4) — "flash mood colour".
const MOOD_COLOR = {
  calm: [0.0, 0.85, 1.0],
  mission: [0.15, 0.6, 1.0],
  combat: [1.0, 0.17, 0.84],
  alarm: [1.0, 0.18, 0.25],
  victory: [0.25, 1.0, 0.12],
  cinematic: [0.55, 0.3, 1.0],
};

const CYAN = [0.0, 0.94, 1.0];
const ACID = [0.22, 1.0, 0.08];
const BLOOD = [1.0, 0.2, 0.33];
const RED = [1.0, 0.18, 0.25];
const MAGENTA = [1.0, 0.17, 0.84];
const AMBER = [1.0, 0.69, 0.0];

const QUALITY_DENSITY = { auto: 1, high: 1, medium: 0.6, low: 0.35 };

/** Audio cues that may be triggered directly as `ui:<cue>`. */
const UI_CUES = ['hover', 'click', 'open', 'close', 'type', 'error', 'save', 'decode', 'glitch', 'whoosh', 'unlock'];

// Timing (ms).
const ALARM_HOLD_MS = 1600;
const ALARM_AFTER_CRASH_MS = 240;
const VICTORY_AFTER_DEATH_MS = 520;
const XP_STREAK_RESET_MS = 450;

// Glyph raster: bits per cell column, and the release (rises, drifting toward screen centre).
const RASTER_X = 3;
const RASTER_MAX_Y = 6;
const RELEASE_ANGLE = -2.05;

// Reused scratch records; never allocated per emit.
const EMIT = { color: CYAN, count: 0 };
const EMIT_TO = { color: CYAN, count: 0, tx: 0, ty: 0 };
const POINTS = { color: BLOOD, angle: RELEASE_ANGLE, hold: 0.12, sweep: 0.6 };

export class FeedbackDirector {
  #bus;
  #settings;
  #camera;
  #loop;
  #renderer;
  #audio;

  #offs = [];
  #timers = new Set();
  #mood = 'calm';
  #alarmTimer = 0;
  #xpStreak = 0;
  #xpLast = 0;
  #raster = new Float32Array(0);
  #densityFor = null; // the Particles instance last given a density…
  #densityValue = -1; // …and the value it got

  /** @param {object} ctx  { bus, settings, camera, loop, renderer, audio } — the app ctx. */
  constructor(ctx = {}) {
    this.#bus = ctx.bus || defaultBus;
    this.#settings = ctx.settings || defaultSettings;
    this.#camera = ctx.camera || null;
    this.#loop = ctx.loop || null;
    this.#renderer = ctx.renderer || null;
    this.#audio = ctx.audio || null;

    const on = (type, fn) => this.#offs.push(this.#bus.on(type, fn));
    on('hack:charge', (e) => this.#onCharge(e));
    on('hack:layer', (e) => this.#onLayer(e));
    on('hack:crash', (e) => this.#onCrash(e));
    on('hack:fail', () => this.#setMood('mission'));
    on('hack:victory', (e) => this.#onVictory(e));
    on('reward:tick', () => this.#onRewardTick());
    on('reward:stamp', (e) => this.#onStamp(e));
    on('reward:rankup', (e) => this.#onRankUp(e));
    on('world:lightning', () => this.#trauma(0.04));
    on('mood', (e) => e && e.name && this.#setMood(e.name, e.seconds));
    for (const cue of UI_CUES) on(`ui:${cue}`, () => this.#onUi(cue));
    if (typeof this.#settings.onChange === 'function') {
      this.#offs.push(this.#settings.onChange((key) => key === 'quality' && this.#syncDensity()));
    }
    this.#syncDensity();
  }

  /** The mood most recently requested (renderer + audio follow it). */
  get mood() {
    return this.#mood;
  }

  /** Unsubscribe everything and cancel pending delayed cues. */
  destroy() {
    for (const off of this.#offs) off();
    this.#offs.length = 0;
    for (const t of this.#timers) clearTimeout(t);
    this.#timers.clear();
    this.#alarmTimer = 0;
  }

  // ── §5 feedback table ─────────────────────────────────────────────────

  #onCharge(e) {
    if (!e) return;
    this.#trauma(0.08);
    this.#emit('stream', e.x, e.y, CYAN, 64, e);
    this.#play('charge');
    this.#setMood('combat', 0.35);
  }

  #onLayer(e) {
    if (!e) return;
    if (e.passed) {
      this.#trauma(0.22);
      this.#loop?.hitStop?.(45);
      this.#emit('spark', e.x, e.y, ACID, 24);
      this.#emit('stream', e.x, e.y, CYAN, 28, e);
      this.#emit('shatter', e.tx, e.ty, BLOOD, 20);
      this.#play('breach', 1 + (e.combo || 0) * 0.09);
      this.#flash(MOOD_COLOR[this.#mood] || MOOD_COLOR.combat, 0.12);
    } else {
      this.#trauma(0.3);
      this.#emit('spark', e.x, e.y, RED, 30);
      this.#play('blocked');
      this.#flash(RED, 0.15);
    }
  }

  #onCrash(e) {
    if (!e) return;
    this.#trauma(0.55);
    this.#emit('spark', e.x, e.y, RED, 60);
    this.#play('crash');
    this.#later(() => this.#play('alarm'), ALARM_AFTER_CRASH_MS);
    this.#setMood('alarm', 0.15);
  }

  #onVictory(e) {
    if (!e) return;
    this.#trauma(0.9);
    this.#loop?.hitStop?.(140);
    this.#emit('explosion', e.x, e.y, BLOOD, 220);
    if (e.points && e.points.length >= 2) this.#disintegrate(e.points);
    this.#play('death');
    this.#later(() => this.#play('victory'), VICTORY_AFTER_DEATH_MS);
    this.#flash(ACID, 0.85);
    this.#setMood('victory', 0.5);
  }

  #onRewardTick() {
    // Consecutive ticks climb in pitch like a coin counter; a pause resets the climb.
    const now = performance.now();
    this.#xpStreak = now - this.#xpLast > XP_STREAK_RESET_MS ? 0 : Math.min(this.#xpStreak + 1, 24);
    this.#xpLast = now;
    this.#play('xp', 1 + this.#xpStreak * 0.018, 0.85);
  }

  #onStamp(e) {
    if (!e) return;
    this.#trauma(0.35);
    this.#emit('spark', e.x, e.y, AMBER, 36);
    this.#play('blocked', 0.6);
  }

  #onRankUp(e) {
    if (!e) return;
    this.#trauma(0.3);
    this.#emit('confetti', e.x, e.y, MAGENTA, 178);
    this.#play('rankup');
    this.#flash(MAGENTA, 0.4);
  }

  #onUi(cue) {
    if (cue === 'type') {
      if (!this.#settings.get('typingSounds')) return;
      this.#play('type', 0.94 + Math.random() * 0.12, 0.7);
      return;
    }
    this.#play(cue);
  }

  // ── mood ──────────────────────────────────────────────────────────────

  #setMood(name, seconds) {
    if (!MOOD_COLOR[name]) return;
    if (this.#alarmTimer) {
      clearTimeout(this.#alarmTimer);
      this.#timers.delete(this.#alarmTimer);
      this.#alarmTimer = 0;
    }
    this.#mood = name;
    const r = this.#renderer;
    if (r && typeof r.setMood === 'function') {
      if (seconds === undefined) r.setMood(name);
      else r.setMood(name, seconds);
    }
    this.#audio?.setMood?.(name);
    if (name === 'alarm') {
      this.#alarmTimer = this.#later(() => {
        this.#alarmTimer = 0;
        if (this.#mood === 'alarm') this.#setMood('mission', 1.4);
      }, ALARM_HOLD_MS);
    }
  }

  // ── primitives ────────────────────────────────────────────────────────

  #trauma(amount) {
    this.#camera?.addTrauma?.(amount);
  }

  #play(cue, pitch = 1, gain = 1) {
    const a = this.#audio;
    if (a && typeof a.play === 'function') a.play(cue, { pitch, gain });
  }

  #flash(rgb, amount) {
    const r = this.#renderer;
    if (r && typeof r.flash === 'function') r.flash(rgb, this.#settings.get('reducedMotion') ? amount * 0.5 : amount);
  }

  /** The live particle system (the renderer swaps it on context restore), density synced. */
  #particles() {
    const p = this.#renderer?.particles;
    if (!p || typeof p.emit !== 'function') return null;
    this.#syncDensity(p);
    return p;
  }

  #syncDensity(p = this.#renderer?.particles) {
    if (!p || typeof p.setDensity !== 'function') return;
    const q = this.#settings.get('quality');
    let d = QUALITY_DENSITY[q] ?? 1;
    if (q === 'auto') {
      const scale = this.#renderer?.stats?.scale;
      if (typeof scale === 'number' && scale > 0 && scale < 1) d *= 0.45 + 0.55 * scale;
    }
    d = Math.round(d * 20) / 20; // quantised: no churn from tiny scale changes
    if (p === this.#densityFor && d === this.#densityValue) return;
    this.#densityFor = p;
    this.#densityValue = d;
    p.setDensity(d);
  }

  #emit(preset, x, y, color, count, target) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    const p = this.#particles();
    if (!p) return;
    if (target && Number.isFinite(target.tx) && Number.isFinite(target.ty)) {
      EMIT_TO.color = color;
      EMIT_TO.count = count;
      EMIT_TO.tx = target.tx;
      EMIT_TO.ty = target.ty;
      p.emit(preset, x, y, EMIT_TO);
    } else {
      EMIT.color = color;
      EMIT.count = count;
      p.emit(preset, x, y, EMIT);
    }
  }

  /** Expand one point per glyph into a raster over each glyph cell, then release it. */
  #disintegrate(points) {
    const p = this.#particles();
    if (!p || typeof p.emitPoints !== 'function') return;
    const glyphs = points.length >> 1;

    // Cell pitch from the points themselves: nearest same-row neighbour (x), nearest row (y).
    let cw = Infinity;
    let ch = Infinity;
    for (let i = 1; i < glyphs; i++) {
      const dx = Math.abs(points[i * 2] - points[i * 2 - 2]);
      const dy = Math.abs(points[i * 2 + 1] - points[i * 2 - 1]);
      if (dy < 0.5) {
        if (dx > 0.5 && dx < cw) cw = dx;
      } else if (dy < ch) {
        ch = dy;
      }
    }
    if (!Number.isFinite(cw)) cw = Number.isFinite(ch) ? ch * 0.55 : 12;
    if (!Number.isFinite(ch)) ch = cw * 1.8;

    const nx = RASTER_X;
    const ny = Math.max(2, Math.min(RASTER_MAX_Y, Math.round((nx * ch) / cw)));
    const total = glyphs * nx * ny;
    if (this.#raster.length < total * 2) this.#raster = new Float32Array(total * 2);
    const out = this.#raster;
    const sx = (cw * 0.92) / nx;
    const sy = (ch * 0.92) / ny;
    let k = 0;
    for (let i = 0; i < glyphs; i++) {
      const x0 = points[i * 2] - (cw * 0.92) / 2 + sx / 2;
      const y0 = points[i * 2 + 1] - (ch * 0.92) / 2 + sy / 2;
      for (let row = 0; row < ny; row++) {
        for (let col = 0; col < nx; col++) {
          out[k++] = x0 + col * sx;
          out[k++] = y0 + row * sy;
        }
      }
    }
    p.emitPoints(out.subarray(0, k), POINTS);
  }

  #later(fn, ms) {
    const t = setTimeout(() => {
      this.#timers.delete(t);
      fn();
    }, ms);
    this.#timers.add(t);
    return t;
  }
}
