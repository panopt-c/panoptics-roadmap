/**
 * AudioEngine — NULL//SECTOR's procedural sound. No audio files ship with the game:
 * every sound is synthesized with Web Audio at runtime.
 *
 * Signal flow
 *
 *   voice ─► cue strip ─┬─ sfx dry ────────────────────────────────┐
 *                       ├─ sfx reverb send ─► reverb ──────────────┤
 *                       └─ sfx echo send ──► ping-pong delay ──────┤
 *   ambient layers ─────┬─ music dry ─► duck ──────────────────────┤
 *   (+ thunder, pings)  ├─ music reverb send ─► duck ─► reverb ────┤
 *                       └─ music echo send ─► duck ─► delay ───────┤
 *                                                                  ▼
 *               master (masterVolume) ─► fade ─► compressor ─► safety clip ─► speakers
 *
 *   The reverb is one shared ConvolverNode fed by a generated stereo impulse (2.2 s of
 *   decorrelated noise whose high end decays faster than its low end, like a real hall).
 *   The echo is a filtered stereo ping-pong for UI sparkle. Bus volumes are applied post-fader
 *   on every send, so turning SFX down also turns down the SFX reverb; settings changes glide
 *   with setTargetAtTime (no zipper noise, no clicks). Big moments duck the ambient bed.
 *
 * Bake, then play
 *   Every cue is a synthesis recipe (oscillators, FM, filtered noise, waveshaping, envelopes,
 *   sweeps; `SYNTHS` below). After unlock() the recipes are rendered once with
 *   OfflineAudioContexts — several seeded takes per cue for round-robin variation, rendered
 *   concurrently off the main thread — then sliced, DC-blocked, peak-normalized to the cue's
 *   mix level and trimmed. play() therefore only creates a buffer source, a gain and (when
 *   panned) a panner — the cost of three nodes, sample-accurate, with a consistent mix whatever
 *   the recipe does; rejected spam costs well under a microsecond. UI cues bake first (ready
 *   within a few frames); until a cue is baked, and for cues marked `live` (thunder, unique per
 *   strike), the same recipe runs directly on the live context. Without OfflineAudioContext
 *   everything runs live.
 *
 * Voices
 *   Per-cue voice limits (the oldest voice is stolen with a 6 ms fade), a minimum retrigger
 *   interval per cue (spam never stacks into clipping), a global budget with priorities, and
 *   per-play pitch/gain/pan jitter so repeats never machine-gun. Every source node clears
 *   itself on `ended` and disconnects its whole voice; Voice records are pooled.
 *
 * Ambient bed (per mood, 2 s crossfades)
 *   drone (detuned saws in A through LFO-swept lowpasses, sub, hum, wind) and rain (a
 *   generated, seamlessly looping field of droplets over hiss) run forever; mood layers — the
 *   combat heartbeat/bass loop, the alarm tension cluster and its faster pulse, the victory
 *   lift, the cinematic pad — are built when a mood needs them and torn down once silent.
 *   Distant metallic pings are scheduled at random. `world:lightning` on the bus schedules
 *   thunder 0.25–1.1 s later on the audio clock; the delay sets distance (gain, brightness).
 *
 * Lifecycle
 *   The AudioContext is created lazily inside the first user gesture (no autoplay warnings);
 *   unlock() is idempotent and also armed on the first pointer/key gesture. A fresh
 *   compressor over-attenuates its first ~150 ms, so output starts on a time-aligned bypass
 *   and crossfades in (the unlocking click is never swallowed). Hidden tabs fade out and
 *   suspend the context. No Web Audio → every method is a silent no-op.
 *
 * Contract (docs/ARCHITECTURE.md §4.4) plus backward-compatible extras:
 *   play() also takes `delay` (s, on the audio clock) and `distance` (thunder), and returns
 *   whether a voice started; constructor options `context` (inject e.g. an
 *   OfflineAudioContext) and `ambient: false` (cues only); `whenBaked()`, `mood`, `context`,
 *   `stats` (debug counters) and `dispose()`.
 */
import { settings as defaultSettings } from '../core/settings.js';
import { bus as defaultBus } from '../core/bus.js';

// ── tuning ──────────────────────────────────────────────────────────────────

const MAX_VOICES = 40; // global budget across all cues
const MOOD_TAU = 0.5; // setTargetAtTime constant: a mood crossfade is ~98 % done in 2 s
const BOOT_TAU = 1.1; // first fade-in of the ambient bed after unlock
const LAYER_RETIRE = 5.5; // s after a layer starts fading out before its nodes are torn down
const BUS_TAU = 0.05; // settings changes
const STEAL_TAU = 0.006; // fade of a stolen voice
const COMP_MAKEUP = 1.445; // the compressor's automatic makeup gain (+3.2 dB) at the settings below
const COMP_LOOKAHEAD = 0.006; // its fixed look-ahead delay
const COMP_WARMUP = 0.25; // s on the bypass path after the context starts
const REVERB_SECONDS = 2.2;
const REVERB_RETURN = 0.42;
const ECHO_TIME = 0.135;
const ECHO_FEEDBACK = 0.36;
const ECHO_RETURN = 0.5;
const PING_MIN = 5; // s between distant pings
const PING_MAX = 14;
const NO_OPTS = Object.freeze({});
const GESTURES = ['pointerdown', 'keydown', 'touchend', 'click'];

/*
 * Cue table — the mix lives here.
 *  variants  seeded takes baked per cue (round-robin, never the same take twice in a row)
 *  stereo    bake two channels (otherwise mono, panned at play time)
 *  dur       render length in s (trailing silence is trimmed after baking)
 *  peak      peak level in dBFS after baking (before bus volumes)
 *  voices    max simultaneous voices; gap: min s between triggers
 *  prio      0..3 — when the global budget is full, the lowest-priority oldest voice yields
 *  jitter    random ± pitch per play (fraction); spread: random ± pan
 *  reverb, echo  send levels; bus: 'music' routes through the ambient bus
 *  duck      [depth, hold s]: dips the ambient bed under big moments
 *  live      synthesized per play, never baked
 */
const CUES = {
  hover: { variants: 4, stereo: 0, dur: 0.12, peak: -18, voices: 3, gap: 0.04, prio: 0, jitter: 0.02, spread: 0.12, reverb: 0.05, echo: 0.2 },
  click: { variants: 3, stereo: 0, dur: 0.16, peak: -14, voices: 3, gap: 0.03, prio: 1, jitter: 0.015, spread: 0.05, reverb: 0.06, echo: 0.14 },
  open: { variants: 2, stereo: 1, dur: 0.6, peak: -15, voices: 2, gap: 0.08, prio: 1, jitter: 0.02, reverb: 0.18, echo: 0.22 },
  close: { variants: 2, stereo: 1, dur: 0.5, peak: -14, voices: 2, gap: 0.08, prio: 1, jitter: 0.02, reverb: 0.15, echo: 0.12 },
  type: { variants: 8, stereo: 0, dur: 0.08, peak: -13, voices: 4, gap: 0.035, prio: 0, jitter: 0.03, spread: 0.2, reverb: 0.02 },
  save: { variants: 1, stereo: 1, dur: 0.85, peak: -21, voices: 2, gap: 0.12, prio: 1, reverb: 0.2, echo: 0.3 },
  charge: { variants: 2, stereo: 1, dur: 0.56, peak: -10, voices: 2, gap: 0.15, prio: 2, jitter: 0.01, reverb: 0.12 },
  breach: { variants: 3, stereo: 1, dur: 0.9, peak: -4, voices: 4, gap: 0.03, prio: 2, jitter: 0.01, reverb: 0.22, echo: 0.06, duck: [0.2, 0.06] },
  blocked: { variants: 2, stereo: 0, dur: 0.5, peak: -1, voices: 3, gap: 0.04, prio: 2, jitter: 0.02, spread: 0.1, reverb: 0.15 },
  crash: { variants: 2, stereo: 1, dur: 0.95, peak: -5, voices: 2, gap: 0.2, prio: 3, reverb: 0.25, duck: [0.35, 0.4] },
  alarm: { variants: 1, stereo: 1, dur: 1.05, peak: -12, voices: 1, gap: 0.5, prio: 2, reverb: 0.3, duck: [0.3, 0.7] },
  death: { variants: 1, stereo: 1, dur: 3.4, peak: -1.5, voices: 1, gap: 0.5, prio: 3, reverb: 0.35, duck: [0.6, 1.3] },
  victory: { variants: 1, stereo: 1, dur: 3.0, peak: -5, voices: 1, gap: 0.5, prio: 3, reverb: 0.3, echo: 0.22, duck: [0.55, 1.6] },
  xp: { variants: 3, stereo: 0, dur: 0.16, peak: -20, voices: 3, gap: 0.045, prio: 1, jitter: 0.01, spread: 0.1, reverb: 0.08, echo: 0.15 },
  rankup: { variants: 1, stereo: 1, dur: 2.8, peak: -2, voices: 1, gap: 0.5, prio: 3, reverb: 0.3, echo: 0.2, duck: [0.5, 1.4] },
  decode: { variants: 2, stereo: 1, dur: 0.8, peak: -23, voices: 2, gap: 0.06, prio: 0, jitter: 0.03, reverb: 0.08, echo: 0.15 },
  glitch: { variants: 3, stereo: 1, dur: 0.4, peak: -16, voices: 3, gap: 0.05, prio: 1, jitter: 0.06, reverb: 0.1 },
  thunder: { live: true, stereo: 1, dur: 6.5, peak: -3, voices: 2, gap: 1.2, prio: 1, reverb: 0.55, bus: 'music' },
  unlock: { variants: 1, stereo: 1, dur: 3.6, peak: -4, voices: 1, gap: 0.5, prio: 3, reverb: 0.35, echo: 0.15, duck: [0.45, 1.6] },
  error: { variants: 1, stereo: 0, dur: 0.3, peak: -17, voices: 2, gap: 0.09, prio: 1, jitter: 0.01, reverb: 0.06 },
  whoosh: { variants: 2, stereo: 1, dur: 0.72, peak: -15, voices: 2, gap: 0.08, prio: 1, jitter: 0.04, reverb: 0.15 },
  ping: { variants: 1, stereo: 1, dur: 3.0, peak: -23, voices: 3, gap: 0.3, prio: 0, reverb: 0.9, echo: 0.25, bus: 'music' },
};

// Bake order, in batches that each cost the main thread a single wait (see #bakeBatch):
// UI first — that is what the player hears in the first second — then combat, then big moments.
const BAKE_BATCHES = [
  ['click', 'hover', 'whoosh', 'open', 'close', 'type', 'error', 'glitch', 'decode', 'save', 'xp'],
  ['charge', 'breach', 'blocked', 'crash', 'alarm'],
  ['unlock', 'victory', 'rankup', 'death', 'ping'],
];
const BAKE_GAP = 0.1; // s of silence between takes rendered end to end
const LOOP_TAIL = 0.5; // s rendered past a loop's end and folded back over its start

const CUE_NAMES = Object.keys(CUES);
const CUE_LIST = CUE_NAMES.map((name) => ({ name, variants: 1, stereo: 0, jitter: 0, spread: 0, reverb: 0, echo: 0, duck: null, live: false, bus: 'sfx', ...CUES[name] }));
const CUE_INDEX = new Map(CUE_NAMES.map((name, i) => [name, i]));
const TYPE_CUE = CUE_INDEX.get('type');

/*
 * Mood → ambient layer levels (0..1, scaled by LAYERS[key].level) and drone filter cutoff.
 * Same names as Renderer.setMood.
 */
const MOODS = {
  calm: { drone: 1, cutoff: 300, rain: 1, pulse: 0, alarm: 0, lift: 0, pad: 0, pings: 1 },
  mission: { drone: 0.9, cutoff: 430, rain: 0.72, pulse: 0, alarm: 0, lift: 0, pad: 0, pings: 0.75 },
  combat: { drone: 0.95, cutoff: 980, rain: 0.55, pulse: 1, alarm: 0, lift: 0, pad: 0, pings: 0.25 },
  alarm: { drone: 0.8, cutoff: 720, rain: 0.45, pulse: 0, alarm: 1, lift: 0, pad: 0, pings: 0 },
  victory: { drone: 0.55, cutoff: 1600, rain: 0.5, pulse: 0, alarm: 0, lift: 1, pad: 0, pings: 0.6 },
  cinematic: { drone: 0.6, cutoff: 520, rain: 0.35, pulse: 0, alarm: 0, lift: 0, pad: 1, pings: 0.5 },
};
const LAYERS = {
  drone: { level: 0.5, send: 0.3, permanent: true },
  rain: { level: 0.15, send: 0.12, permanent: true },
  pulse: { level: 1.4, send: 0.08 },
  alarm: { level: 0.7, send: 0.3 },
  lift: { level: 0.7, send: 0.55 },
  pad: { level: 0.8, send: 0.8 },
};
const LAYER_KEYS = Object.keys(LAYERS);

// Pitch ratios for the distant pings: A minor pentatonic over the baked A5.
const PING_RATIOS = [1, 1.1892, 1.3348, 1.4983, 1.7818, 0.8909];

// ── small helpers ───────────────────────────────────────────────────────────

const dbToGain = (db) => Math.pow(10, db / 20);
const clamp = (x, lo, hi) => (x < lo ? lo : x > hi ? hi : x);
/** `x` clamped to [lo, hi], or `fallback` when `x` is not a number (or NaN). */
const num = (x, fallback, lo, hi) => (typeof x === 'number' && x === x ? clamp(x, lo, hi) : fallback);
/** Slider 0..1 → gain. Squared ("audio taper"): perceptually even steps, true silence at 0. */
const taper = (v) => {
  const x = num(+v, 0, 0, 1);
  return x * x;
};
const noop = () => {};
const yieldTask = () => new Promise((resolve) => setTimeout(resolve, 0));

/** Small fast seeded PRNG (mulberry32): baked takes sound identical every session. */
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashString(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

// ── envelopes (all times absolute, in the context's clock) ─────────────────

/** Percussive: linear attack to `peak`, exponential fall to −60 dB over `decay`, then a true zero. */
function perc(param, t, attack, peak, decay) {
  if (!(peak > 0)) return;
  param.setValueAtTime(0, t);
  param.linearRampToValueAtTime(peak, t + attack);
  param.exponentialRampToValueAtTime(peak * 1e-3, t + attack + decay);
  param.linearRampToValueAtTime(0, t + attack + decay + 0.004);
}

/** Swell: exponential attack, optional hold, exponential release (whooshes, risers, pads). */
function swell(param, t, attack, peak, hold, release) {
  if (!(peak > 0)) return;
  param.setValueAtTime(peak * 1e-3, t);
  param.exponentialRampToValueAtTime(peak, t + attack);
  if (hold > 0) param.setValueAtTime(peak, t + attack + hold);
  param.exponentialRampToValueAtTime(peak * 1e-3, t + attack + hold + release);
  param.linearRampToValueAtTime(0, t + attack + hold + release + 0.004);
}

/** Exponential sweep (frequencies are perceived logarithmically). */
function sweep(param, t, from, to, dur) {
  param.setValueAtTime(from, t);
  param.exponentialRampToValueAtTime(to, t + dur);
}

/** Move a long-lived parameter toward `value` from wherever it is now, without a step. */
function glide(param, value, now, tau) {
  param.cancelScheduledValues(now);
  param.setTargetAtTime(value, now, tau);
}

// ── generated resources ─────────────────────────────────────────────────────

/** Waveshaper curves (odd length → curve(0) is exactly 0, no DC). */
function makeCurve(fn, n = 2049) {
  const c = new Float32Array(n);
  for (let i = 0; i < n; i++) c[i] = fn((i / (n - 1)) * 2 - 1);
  return c;
}
const CURVES = {
  soft: makeCurve((x) => Math.tanh(2 * x) / Math.tanh(2)),
  hard: makeCurve((x) => Math.tanh(6 * x) / Math.tanh(6)),
  crush: makeCurve((x) => (Math.sign(x) * Math.floor(Math.abs(x) * 5 + 0.5)) / 5),
  // Master safety clip: transparent below 0.75, then a tanh knee that can never pass 0.93.
  limit: makeCurve((x) => {
    const a = Math.abs(x);
    return a <= 0.75 ? x : Math.sign(x) * (0.75 + 0.22 * Math.tanh((a - 0.75) / 0.22));
  }, 4097),
};

/**
 * 2 s mono noise loops. Pink and brown are crossfaded across the seam (they have memory, so
 * a plain loop would click); every buffer is made zero-mean.
 */
function makeNoise(ctx, rate, kind, rng, seconds = 2) {
  const sr = rate;
  const n = Math.round(seconds * sr);
  if (kind === 'white') {
    const buf = ctx.createBuffer(1, n, sr);
    const d = buf.getChannelData(0);
    let mean = 0;
    for (let i = 0; i < n; i++) mean += d[i] = (rng() * 2 - 1) * 0.9;
    mean /= n;
    for (let i = 0; i < n; i++) d[i] -= mean;
    return buf;
  }
  const fade = Math.round(0.05 * sr);
  const raw = new Float32Array(n + fade);
  let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0, last = 0;
  for (let i = 0; i < raw.length; i++) {
    const w = rng() * 2 - 1;
    if (kind === 'pink') {
      // Paul Kellet's refined pink filter.
      b0 = 0.99886 * b0 + w * 0.0555179;
      b1 = 0.99332 * b1 + w * 0.0750759;
      b2 = 0.969 * b2 + w * 0.153852;
      b3 = 0.8665 * b3 + w * 0.3104856;
      b4 = 0.55 * b4 + w * 0.5329522;
      b5 = -0.7616 * b5 - w * 0.016898;
      raw[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11;
      b6 = w * 0.115926;
    } else if (kind === 'brown') {
      last = (last + 0.02 * w) / 1.02;
      raw[i] = last * 3.5;
    } else {
      // Crackle: sparse signed impulses with a short tail — embers, static, debris.
      last = w > 0.995 || w < -0.995 ? (w < 0 ? -1 : 1) * (0.3 + 0.7 * rng() * rng()) : last * 0.45;
      raw[i] = last;
    }
  }
  const buf = ctx.createBuffer(1, n, sr);
  const d = buf.getChannelData(0);
  d.set(raw.subarray(0, n));
  if (kind === 'pink' || kind === 'brown') {
    for (let i = 0; i < fade; i++) {
      const x = i / fade;
      d[i] = raw[i] * Math.sqrt(x) + raw[n + i] * Math.sqrt(1 - x);
    }
  }
  let mean = 0;
  for (let i = 0; i < n; i++) mean += d[i];
  mean /= n;
  let peak = 0;
  for (let i = 0; i < n; i++) {
    d[i] -= mean;
    const a = Math.abs(d[i]);
    if (a > peak) peak = a;
  }
  const k = peak > 0 ? 0.9 / peak : 1;
  for (let i = 0; i < n; i++) d[i] *= k;
  return buf;
}

/**
 * Stereo impulse response: 12 ms pre-delay, a few early reflections, then decorrelated noise
 * through a one-pole lowpass that darkens over time (air absorbs highs first), −60 dB at the end.
 * Exponentials run as per-sample recurrences; one channel per task.
 */
async function makeImpulse(ctx, seconds, rng, alive) {
  const sr = ctx.sampleRate;
  const n = Math.round(seconds * sr);
  const pre = Math.round(0.012 * sr);
  const build = 1 / (0.025 * sr);
  const len = n - pre;
  const decayStep = Math.exp(-6.9 / len); // amplitude: −60 dB over the tail
  const darkStep = Math.exp(-3.2 / len); // lowpass coefficient: bright onset, dark tail
  const buf = ctx.createBuffer(2, n, sr);
  for (let c = 0; c < 2; c++) {
    if (c) await yieldTask();
    if (!alive()) return null;
    const d = buf.getChannelData(c);
    let lp = 0, env = 1, dark = 1, onset = 0;
    for (let i = pre; i < n; i++) {
      lp += (0.82 * dark + 0.05) * (rng() * 2 - 1 - lp);
      d[i] = lp * env * (onset < 1 ? (onset += build) : 1);
      env *= decayStep;
      dark *= darkStep;
    }
    for (let e = 0; e < 8; e++) {
      const at = pre + Math.floor((0.003 + rng() * 0.055) * sr);
      d[at] += (rng() * 2 - 1) * 0.45 * (1 - e / 9);
    }
  }
  return buf;
}

/**
 * Rain: a seamless stereo loop of soft hiss plus thousands of droplets (damped resonators —
 * impulse-excited two-pole filters), placed circularly so the loop point is invisible.
 * Generated in chunks between yields so it never blocks a frame.
 */
async function makeRain(ctx, rate, seconds, rng, alive) {
  const sr = rate;
  const n = Math.round(seconds * sr);
  const buf = ctx.createBuffer(2, n, sr);
  for (let c = 0; c < 2; c++) {
    const d = buf.getChannelData(c);
    let b0 = 0, b1 = 0, b2 = 0;
    for (let i = 0; i < n; i++) {
      const w = rng() * 2 - 1;
      b0 = 0.99765 * b0 + w * 0.099046;
      b1 = 0.963 * b1 + w * 0.2965164;
      b2 = 0.57 * b2 + w * 1.0526913;
      d[i] = (b0 + b1 + b2 + w * 0.1848) * 0.035;
    }
    const drops = Math.round(seconds * 760);
    for (let j = 0; j < drops; j++) {
      const pos = Math.floor(rng() * n);
      const big = rng() < 0.05;
      const f = big ? 650 + rng() * 1100 : 1700 + rng() * rng() * 6500;
      const tau = (big ? 0.006 + rng() * 0.01 : 0.0007 + rng() * 0.0022) * sr;
      const amp = big ? 0.12 + rng() * 0.1 : 0.03 + 0.3 * rng() * rng() * rng();
      const w = (2 * Math.PI * f) / sr;
      const r = Math.exp(-1 / tau);
      const c1 = 2 * r * Math.cos(w);
      const r2 = r * r;
      const len = Math.min(Math.floor(tau * 4.6), 3000);
      let y1 = 0, y2 = 0, x = amp * Math.sin(w);
      for (let s = 0, idx = pos; s < len; s++, idx++) {
        if (idx >= n) idx -= n;
        const y = c1 * y1 - r2 * y2 + x;
        x = 0;
        y2 = y1;
        y1 = y;
        d[idx] += y;
      }
      if ((j & 2047) === 2047) {
        await yieldTask();
        if (!alive()) return null;
      }
    }
  }
  let peak = 0;
  for (let c = 0; c < 2; c++) {
    const d = buf.getChannelData(c);
    let mean = 0;
    for (let i = 0; i < n; i++) mean += d[i];
    mean /= n;
    for (let i = 0; i < n; i++) peak = Math.max(peak, Math.abs((d[i] -= mean)));
  }
  for (let c = 0; c < 2; c++) {
    const d = buf.getChannelData(c);
    const k = 0.9 / (peak || 1);
    for (let i = 0; i < n; i++) d[i] *= k;
  }
  return buf;
}

// ── synthesis kit ───────────────────────────────────────────────────────────

/**
 * Thin node factory bound to one render: an offline bake (owner = null, the whole context is
 * thrown away afterwards) or a live voice/layer (owner collects every node for teardown and
 * every source for `ended` bookkeeping). Recipes only ever talk to this.
 */
class Kit {
  constructor(res, adopt) {
    this.res = res; // { noise: {white, pink, brown, crackle}, curves }
    this.adopt = adopt; // (src, owner) → registers a live source
    this.ac = null;
    this.out = null;
    this.rng = Math.random;
    this.owner = null;
    this.nyq = 20000; // highest frequency worth synthesizing on this context
  }

  bind(ac, out, rng, owner) {
    this.ac = ac;
    this.out = out;
    this.rng = rng;
    this.owner = owner;
    this.nyq = ac.sampleRate * 0.45;
    return this;
  }

  r(a, b) {
    return a + (b - a) * this.rng();
  }

  pick(list) {
    return list[Math.floor(this.rng() * list.length) % list.length];
  }

  keep(node, to) {
    if (to) node.connect(to);
    if (this.owner) this.owner.nodes.push(node);
    return node;
  }

  gain(v, to) {
    const n = this.ac.createGain();
    n.gain.value = v;
    return this.keep(n, to);
  }

  filter(type, freq, q, to) {
    const n = this.ac.createBiquadFilter();
    n.type = type;
    n.frequency.value = freq;
    n.Q.value = q;
    return this.keep(n, to);
  }

  pan(v, to) {
    const n = this.ac.createStereoPanner();
    n.pan.value = v;
    return this.keep(n, to);
  }

  shaper(curve, to) {
    const n = this.ac.createWaveShaper();
    n.curve = this.res.curves[curve];
    n.oversample = '2x';
    return this.keep(n, to);
  }

  /** Oscillator started at t0; stopped at t1 (t1 = 0: runs until torn down). */
  osc(type, freq, t0, t1, to, detune = 0) {
    const o = this.ac.createOscillator();
    o.type = type;
    o.frequency.value = Math.min(freq, this.nyq);
    o.detune.value = detune;
    this.keep(o, to);
    o.start(t0);
    if (t1 > 0) o.stop(t1);
    if (this.owner) this.adopt(o, this.owner);
    return o;
  }

  /** Looping buffer source (random start offset unless given). */
  buffer(buf, t0, t1, to, rate = 1, offset = -1) {
    const s = this.ac.createBufferSource();
    s.buffer = buf;
    s.loop = true;
    s.playbackRate.value = rate;
    this.keep(s, to);
    s.start(t0, offset >= 0 ? offset : this.rng() * buf.duration);
    if (t1 > 0) s.stop(t1);
    if (this.owner) this.adopt(s, this.owner);
    return s;
  }

  noise(kind, t0, t1, to, rate = 1) {
    const bank = this.res.noise;
    return this.buffer(bank[kind] || bank.white, t0, t1, to, rate);
  }
}

// ── recipes: shared gestures ────────────────────────────────────────────────

const GLASS = [
  [1, 0.5, 0.05],
  [2.76, 0.2, 0.028],
  [4.07, 0.08, 0.016],
]; // inharmonic ratio, amplitude, decay

/** A tiny struck-glass tick: three inharmonic partials with a 4 % downward pitch settle. */
function glass(k, t, f, amp, to = k.out) {
  for (let i = 0; i < GLASS.length; i++) {
    const [ratio, a, dec] = GLASS[i];
    if (f * ratio * 1.04 > k.nyq) break; // partials above Nyquist would only alias
    const g = k.gain(0, to);
    const o = k.osc('sine', f * ratio, t, t + dec + 0.03, g);
    sweep(o.frequency, t, f * ratio * 1.04, f * ratio, 0.012);
    perc(g.gain, t, 0.0012, a * amp, dec);
  }
}

/** Filtered noise burst. */
function burst(k, t, kind, type, freq, q, amp, decay, to = k.out, attack = 0.0005) {
  const g = k.gain(0, to);
  k.noise(kind, t, t + attack + decay + 0.02, k.filter(type, freq, q, g));
  perc(g.gain, t, attack, amp, decay);
  return g;
}

/** Pitched-down sine thump (kick, impact, heartbeat), optionally saturated. */
function kick(k, t, f0, f1, sweepT, amp, decay, drive = true, to = k.out) {
  const g = k.gain(0, drive ? k.shaper('soft', to) : to);
  const o = k.osc('sine', f0, t, t + decay + 0.05, g);
  sweep(o.frequency, t, f0, f1, sweepT);
  perc(g.gain, t, 0.0015, amp, decay);
}

/** Two-operator FM bell: bright metallic onset settling into a purer tone. */
function bell(k, t, f, ratio, index, amp, decay, pan = 0, to = k.out) {
  const g = k.gain(0, pan ? k.pan(pan, to) : to);
  const end = t + decay + 0.05;
  const car = k.osc('sine', f, t, end, g);
  const mg = k.gain(0, car.frequency);
  k.osc('sine', f * ratio, t, end, mg);
  mg.gain.setValueAtTime(f * ratio * index, t);
  mg.gain.exponentialRampToValueAtTime(f * ratio * index * 0.04, t + decay * 0.6);
  perc(g.gain, t, 0.0015, amp, decay);
}

/** Saw+square pluck through a closing lowpass. */
function pluck(k, t, f, pan, amp, decay) {
  const g = k.gain(0, k.pan(pan, k.out));
  const lp = k.filter('lowpass', 8000, 2, g);
  sweep(lp.frequency, t, Math.min(f * 10, 12000), Math.max(f * 1.6, 600), decay * 0.7);
  k.osc('sawtooth', f, t, t + decay + 0.05, lp, -6);
  k.osc('square', f, t, t + decay + 0.05, k.gain(0.55, lp), 7);
  perc(g.gain, t, 0.002, amp, decay);
}

/** Brass-like stab: detuned saws, filter opens on the attack; optional delayed vibrato. */
function brass(k, t, f, pan, amp, attack, hold, release, vibrato = 0) {
  const end = t + attack + hold + release + 0.02;
  const g = k.gain(0, k.pan(pan, k.out));
  const lp = k.filter('lowpass', f * 1.2, 1.4, g);
  const a = k.osc('sawtooth', f, t, end, lp, -7);
  const b = k.osc('sawtooth', f, t, end, lp, 6);
  lp.frequency.setValueAtTime(f * 1.2, t);
  lp.frequency.exponentialRampToValueAtTime(Math.min(f * 9, 14000), t + attack + 0.03);
  lp.frequency.exponentialRampToValueAtTime(Math.min(f * 3, 9000), t + attack + hold + release);
  if (vibrato > 0) {
    const depth = k.gain(0, null);
    depth.connect(a.detune);
    depth.connect(b.detune);
    k.osc('sine', 5.6, t, end, depth);
    depth.gain.setValueAtTime(0, t + attack);
    depth.gain.linearRampToValueAtTime(vibrato, t + attack + 0.35);
  }
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(amp, t + attack);
  g.gain.setValueAtTime(amp, t + attack + hold);
  g.gain.exponentialRampToValueAtTime(amp * 1e-3, t + attack + hold + release);
  g.gain.linearRampToValueAtTime(0, t + attack + hold + release + 0.004);
}

const N = {
  A1: 55, E2: 82.41, A2: 110, Bb2: 116.54, C3: 130.81, E3: 164.81, G3: 196, A3: 220, B3: 246.94,
  Cs4: 277.18, E4: 329.63, A4: 440, Cs5: 554.37, E5: 659.26, A5: 880, B5: 987.77,
  Cs6: 1108.73, E6: 1318.51, F6: 1396.91, A6: 1760, B6: 1975.53, Cs7: 2217.46, E7: 2637.02,
};
const VICTORY_ARP = [N.A4, N.Cs5, N.E5, N.A5, N.B5, N.Cs6];
const VICTORY_CHORD = [N.A3, N.E4, N.A4, N.Cs5, N.E5];
const SPARKLE = [N.A6, N.Cs7, N.E7];
const RANK_ARP = [N.A3, N.Cs4, N.E4, N.A4, N.Cs5, N.E5, N.A5];
const RANK_CHORD = [N.A4, N.Cs5, N.E5, N.A5];
const DATA_NOTES = [1046.5, 1318.51, 1567.98, 1760, 2093, 2637.02, 3135.96];
const GLITCH_FREQS = [55, 110, 220, 330, 440, 660, 880, 1320, 1760, 2640];
const UNLOCK_CHIME = [N.E6, N.A6, N.Cs7];

// ── recipes: cues ───────────────────────────────────────────────────────────
// Signature (k, t, p, x): kit, start time, pitch multiplier, cue-specific extra.

const SYNTHS = {
  hover(k, t, p) {
    glass(k, t, k.r(2800, 3300) * p, 1);
    burst(k, t, 'white', 'highpass', 7500, 0.7, 0.16, 0.005);
  },

  click(k, t, p) {
    burst(k, t, 'white', 'bandpass', 4600 * p, 0.9, 0.5, 0.007, k.out, 0.0003);
    const cg = k.gain(0, k.out);
    const c = k.osc('sine', 1200 * p, t, t + 0.1, cg);
    sweep(c.frequency, t, 1050 * p, 1650 * p, 0.018);
    perc(cg.gain, t, 0.001, 0.42, 0.065);
    const sg = k.gain(0, k.out);
    k.osc('triangle', 3300 * p * k.r(0.98, 1.02), t + 0.004, t + 0.06, sg);
    perc(sg.gain, t + 0.004, 0.001, 0.1, 0.03);
    kick(k, t, 240 * p, 120 * p, 0.035, 0.25, 0.04, false);
  },

  open(k, t, p) {
    const rise = 0.26;
    for (let s = -1; s <= 1; s += 2) {
      const g = k.gain(0, k.pan(s * 0.5, k.out));
      const bp = k.filter('bandpass', 450, 1.4, g);
      k.noise('pink', t, t + 0.5, bp);
      sweep(bp.frequency, t, (s < 0 ? 380 : 430) * p, (s < 0 ? 5200 : 6000) * p, rise + 0.06);
      swell(g.gain, t, rise, 0.75, 0, 0.17);
    }
    const tg = k.gain(0, k.out);
    const o = k.osc('triangle', 330 * p, t, t + 0.48, tg);
    sweep(o.frequency, t, 330 * p, 990 * p, rise);
    swell(tg.gain, t, rise * 0.9, 0.12, 0, 0.14);
    glass(k, t + rise - 0.012, 2900 * p, 0.35);
  },

  close(k, t, p) {
    for (let s = -1; s <= 1; s += 2) {
      const g = k.gain(0, k.pan(s * 0.45, k.out));
      const bp = k.filter('bandpass', 4000, 1.3, g);
      k.noise('pink', t, t + 0.4, bp);
      sweep(bp.frequency, t, (s < 0 ? 4600 : 5200) * p, 360 * p, 0.24);
      perc(g.gain, t, 0.025, 0.7, 0.26);
    }
    const tg = k.gain(0, k.out);
    const o = k.osc('triangle', 880 * p, t, t + 0.3, tg);
    sweep(o.frequency, t, 880 * p, 290 * p, 0.2);
    perc(tg.gain, t, 0.01, 0.12, 0.2);
    kick(k, t + 0.16, 140 * p, 62 * p, 0.06, 0.3, 0.11, false);
  },

  type(k, t, p) {
    const tone = k.r(0.88, 1.15) * p;
    // Switch contact, keycap knock, a short bottom-out "thock", then the release rattle.
    burst(k, t, 'white', 'bandpass', 4200 * tone, 1.6, 0.5, 0.008, k.out, 0.0003);
    const bg = k.gain(0, k.out);
    k.noise('pink', t, t + 0.04, k.filter('bandpass', 1800 * tone, 2.8, bg));
    perc(bg.gain, t + 0.0005, 0.0008, 0.55, 0.022);
    kick(k, t + 0.001, 420 * tone, 260 * tone, 0.02, 0.22, 0.025, false);
    const t2 = t + k.r(0.007, 0.013);
    burst(k, t2, 'white', 'highpass', 5200, 0.7, 0.12, 0.004, k.out, 0.0003);
  },

  save(k, t, p) {
    bell(k, t, N.A5 * p, 2, 0.6, 0.5, 0.36, -0.25);
    bell(k, t + 0.09, N.E6 * p, 2, 0.6, 0.55, 0.6, 0.25);
    const og = k.gain(0, k.out);
    k.osc('sine', N.A4 * p, t + 0.09, t + 0.8, og);
    perc(og.gain, t + 0.09, 0.02, 0.14, 0.6);
    kick(k, t, 320 * p, 180 * p, 0.03, 0.25, 0.05, false);
  },

  charge(k, t, p) {
    const T = 0.45;
    for (let s = -1; s <= 1; s += 2) {
      const g = k.gain(0, k.pan(s * 0.35, k.out));
      const lp = k.filter('lowpass', 220, 9, g);
      sweep(lp.frequency, t, 220, 5200, T);
      for (let d = -1; d <= 1; d++) {
        const o = k.osc('sawtooth', 98 * p, t, t + T + 0.06, lp, d * 13 + s * 4);
        sweep(o.frequency, t, 98 * p, 196 * p, T);
      }
      g.gain.setValueAtTime(0.0005, t);
      g.gain.exponentialRampToValueAtTime(0.22, t + T);
      g.gain.linearRampToValueAtTime(0, t + T + 0.05);
    }
    // Capacitor whine with an accelerating tremolo.
    const wg = k.gain(0, k.out);
    const trem = k.gain(0.5, wg);
    const w = k.osc('sine', 900 * p, t, t + T + 0.06, trem);
    sweep(w.frequency, t, 900 * p, 3400 * p, T);
    const lfo = k.osc('sine', 10, t, t + T + 0.06, k.gain(0.5, trem.gain));
    sweep(lfo.frequency, t, 10, 34, T);
    wg.gain.setValueAtTime(0.0005, t);
    wg.gain.exponentialRampToValueAtTime(0.16, t + T);
    wg.gain.linearRampToValueAtTime(0, t + T + 0.04);
    const ng = k.gain(0, k.out);
    const bp = k.filter('bandpass', 800, 1.5, ng);
    k.noise('pink', t, t + T + 0.06, bp);
    sweep(bp.frequency, t, 800, 7000, T);
    ng.gain.setValueAtTime(0.0005, t);
    ng.gain.exponentialRampToValueAtTime(0.3, t + T);
    ng.gain.linearRampToValueAtTime(0, t + T + 0.05);
  },

  breach(k, t, p) {
    burst(k, t, 'white', 'highpass', 2400, 0.7, 0.85, 0.03, k.out, 0.0002);
    kick(k, t, 170 * p, 48 * p, 0.08, 1, 0.3);
    for (let s = -1; s <= 1; s += 2) {
      // FM body: inharmonic (√2) modulator, index collapsing → metallic clang settling to a thud.
      const g = k.gain(0, k.pan(s * 0.35, k.out));
      const lp = k.filter('lowpass', 9000, 0.9, g);
      sweep(lp.frequency, t, 9000, 1100, 0.28);
      const sh = k.shaper('soft', lp);
      const f = N.G3 * p;
      const car = k.osc('sine', f, t, t + 0.5, sh, s * 7);
      const mg = k.gain(0, car.frequency);
      k.osc('sine', f * 1.414, t, t + 0.5, mg, s * 7);
      mg.gain.setValueAtTime(f * 1.414 * 6, t);
      mg.gain.exponentialRampToValueAtTime(f * 1.414 * 0.25, t + 0.2);
      perc(g.gain, t, 0.001, 0.42, 0.36);
      // Digital sparkle tail.
      const tg = k.gain(0, k.pan(s * 0.7, k.out));
      k.noise('white', t + 0.01, t + 0.6, k.filter('bandpass', 6500 + s * 600, 4, tg));
      perc(tg.gain, t + 0.01, 0.006, 0.2, 0.4);
    }
    const zg = k.gain(0, k.out);
    const z = k.osc('square', 3200 * p, t, t + 0.05, k.filter('bandpass', 3000 * p, 1.2, zg));
    sweep(z.frequency, t, 4200 * p, 1600 * p, 0.03);
    perc(zg.gain, t, 0.0003, 0.28, 0.03);
  },

  blocked(k, t, p) {
    // A shot absorbed by the firewall: dull saturated thud, a metallic knock on the shield,
    // a band-limited grit burst and a beating "denied" buzz.
    kick(k, t, 150 * p, 52 * p, 0.12, 0.45, 0.3);
    burst(k, t, 'brown', 'lowpass', 700 * p, 1, 0.6, 0.14, k.out, 0.002);
    bell(k, t, 220 * p, 1.5, 1.2, 0.35, 0.09);
    const gg = k.gain(0, k.out);
    const sh = k.shaper('hard', k.filter('lowpass', 1600 * p, 0.9, gg));
    k.osc('square', 58 * p, t, t + 0.25, sh, 9);
    perc(gg.gain, t, 0.003, 0.4, 0.16);
    const bz = k.gain(0, k.out);
    const lp = k.filter('lowpass', 1100 * p, 1.2, bz);
    k.osc('sawtooth', 104 * p, t, t + 0.3, lp);
    k.osc('sawtooth', 111 * p, t, t + 0.3, lp);
    perc(bz.gain, t, 0.004, 0.3, 0.2);
  },

  crash(k, t, p) {
    kick(k, t, 130 * p, 38 * p, 0.12, 0.9, 0.4);
    burst(k, t, 'white', 'lowpass', 2800, 0.7, 0.7, 0.14, k.out, 0.001);
    // Stutter: one square + one noise source, gated into ragged slices that jump in pitch,
    // filter and pan — through a bit-crush staircase.
    const pn = k.pan(0, k.out);
    const gate = k.gain(0, pn);
    const bp = k.filter('bandpass', 1200, 2, gate);
    const sh = k.shaper('crush', bp);
    const sqg = k.gain(0.7, sh);
    const sq = k.osc('square', 400, t, t + 0.78, sqg);
    const nzg = k.gain(0, sh);
    k.noise('white', t, t + 0.78, nzg);
    let ts = t + 0.02;
    for (let i = 0; i < 18 && ts < t + 0.62; i++) {
      const len = k.r(0.018, 0.05);
      const amp = k.rng() < 0.78 ? k.r(0.35, 0.8) * (1 - (ts - t) / 0.9) : 0;
      const tonal = k.rng() < 0.6;
      gate.gain.setTargetAtTime(amp, ts, 0.0015);
      sq.frequency.setValueAtTime(k.pick(GLITCH_FREQS) * p * k.r(0.97, 1.03), ts);
      bp.frequency.setTargetAtTime(k.r(500, 5000), ts, 0.002);
      sqg.gain.setTargetAtTime(tonal ? 0.7 : 0.12, ts, 0.001);
      nzg.gain.setTargetAtTime(tonal ? 0.1 : 0.6, ts, 0.001);
      pn.pan.setTargetAtTime(k.r(-0.9, 0.9), ts, 0.002);
      ts += len;
    }
    gate.gain.setTargetAtTime(0, ts, 0.008);
    // Power-down: a saw diving from 900 Hz to 30 Hz through hard drive.
    const pg = k.gain(0, k.out);
    const plp = k.filter('lowpass', 4000, 3, pg);
    const ps = k.osc('sawtooth', 900 * p, t + 0.05, t + 0.92, k.shaper('hard', plp));
    sweep(ps.frequency, t + 0.05, 900 * p, 30 * p, 0.7);
    sweep(plp.frequency, t + 0.05, 4000, 160, 0.7);
    perc(pg.gain, t + 0.05, 0.01, 0.4, 0.8);
  },

  alarm(k, t, p) {
    const step = 0.21;
    const tones = [N.A5, N.E5, N.A5, N.E5];
    const vib = k.gain(14, null);
    k.osc('sine', 6.5, t, t + 1.0, vib);
    for (let s = -1; s <= 1; s += 2) {
      const g = k.gain(0, k.pan(s * 0.4, k.out));
      const lp = k.filter('lowpass', 3600, 0.8, g);
      const mix = k.gain(0.45, k.shaper('soft', lp));
      const a = k.osc('sawtooth', tones[0] * p, t, t + 1.0, mix, s * 8);
      const b = k.osc('square', (tones[0] * p) / 2, t, t + 1.0, k.gain(0.5, mix), -s * 5);
      vib.connect(a.detune);
      vib.connect(b.detune);
      g.gain.setValueAtTime(0, t);
      for (let i = 0; i < tones.length; i++) {
        const ti = t + i * step;
        a.frequency.setTargetAtTime(tones[i] * p, ti, 0.006);
        b.frequency.setTargetAtTime((tones[i] * p) / 2, ti, 0.006);
        g.gain.setTargetAtTime(0.5, ti, 0.004);
        g.gain.setTargetAtTime(0.3, ti + step - 0.018, 0.004);
      }
      g.gain.setTargetAtTime(0, t + tones.length * step - 0.01, 0.025);
    }
    const sub = k.gain(0, k.out);
    k.osc('sine', N.A3 * p, t, t + 1.0, sub);
    perc(sub.gain, t, 0.01, 0.25, 0.85);
  },

  death(k, t, p) {
    kick(k, t, 190 * p, 36 * p, 0.2, 1.2, 0.5);
    // Sub drop.
    const sg = k.gain(0, k.out);
    const s = k.osc('sine', 110 * p, t, t + 2.15, sg);
    sweep(s.frequency, t + 0.02, 110 * p, 25 * p, 1.5);
    sg.gain.setValueAtTime(0, t);
    sg.gain.linearRampToValueAtTime(0.9, t + 0.03);
    sg.gain.exponentialRampToValueAtTime(0.0009, t + 2.0);
    sg.gain.linearRampToValueAtTime(0, t + 2.05);
    for (let side = -1; side <= 1; side += 2) {
      // Noise explosion, darkening as it dissipates.
      const g = k.gain(0, k.pan(side * 0.6, k.out));
      const lp = k.filter('lowpass', 10000, 0.7, g);
      k.noise('white', t, t + 2.2, lp);
      sweep(lp.frequency, t, 10000, 160, 1.7);
      perc(g.gain, t, 0.004, 0.85, 1.8);
      // Debris crackle.
      burst(k, t + 0.03, 'crackle', 'bandpass', 2600 + side * 500, 0.8, 0.7, 1.6, k.pan(side * 0.8, k.out), 0.01);
      // Disintegration shimmer: FM falling through the floor.
      const fg = k.gain(0, k.pan(side * 0.5, k.out));
      const car = k.osc('sine', 1500 * p, t, t + 3.0, fg, side * 9);
      const mg = k.gain(0, car.frequency);
      const mod = k.osc('sine', 1500 * 2.37 * p, t, t + 3.0, mg, side * 9);
      sweep(car.frequency, t, 1500 * p, 240 * p, 2.4);
      sweep(mod.frequency, t, 1500 * 2.37 * p, 240 * 2.37 * p, 2.4);
      sweep(mg.gain, t, 1500 * 2.37 * 3 * p, 240 * 2.37 * 0.5 * p, 2.4);
      perc(fg.gain, t, 0.03, 0.16, 2.6);
    }
    // Collapse rumble.
    const rg = k.gain(0, k.out);
    k.noise('brown', t, t + 3.2, k.filter('lowpass', 140, 0.9, rg));
    swell(rg.gain, t, 0.25, 0.8, 0.2, 2.6);
  },

  victory(k, t, p) {
    for (let i = 0; i < VICTORY_ARP.length; i++) {
      pluck(k, t + i * 0.055, VICTORY_ARP[i] * p, i % 2 ? 0.45 : -0.45, 0.42, 0.55);
    }
    const tc = t + 0.34;
    for (let s = -1; s <= 1; s += 2) {
      const g = k.gain(0, k.pan(s * 0.6, k.out));
      const lp = k.filter('lowpass', 5200, 0.7, g);
      sweep(lp.frequency, tc, 5200, 1800, 1.2);
      for (let j = 0; j < VICTORY_CHORD.length; j++) {
        k.osc('sawtooth', VICTORY_CHORD[j] * p, tc, tc + 2.5, lp, s * (6 + j));
      }
      g.gain.setValueAtTime(0, tc);
      g.gain.linearRampToValueAtTime(0.16, tc + 0.03);
      g.gain.exponentialRampToValueAtTime(0.1, tc + 0.6);
      g.gain.setValueAtTime(0.1, tc + 0.8);
      g.gain.exponentialRampToValueAtTime(0.0001, tc + 2.4);
      g.gain.linearRampToValueAtTime(0, tc + 2.42);
    }
    kick(k, tc, 110 * p, 52 * p, 0.12, 0.7, 0.9, false);
    for (let i = 0; i < 9; i++) {
      const ts = tc + k.r(0, 1.1);
      bell(k, ts, k.pick(SPARKLE) * p, 1, 0.2, k.r(0.04, 0.1), 0.3, k.r(-0.8, 0.8));
    }
  },

  xp(k, t, p) {
    const g = k.gain(0, k.out);
    const lp = k.filter('lowpass', 7000, 0.7, g);
    const o = k.osc('square', N.B6 * p, t, t + 0.15, k.gain(0.3, lp));
    const s = k.osc('sine', N.B6 * p, t, t + 0.15, lp);
    o.frequency.setValueAtTime(N.E7 * p, t + 0.035);
    s.frequency.setValueAtTime(N.E7 * p, t + 0.035);
    perc(g.gain, t, 0.001, 0.5, 0.12);
    glass(k, t, 5200 * p * k.r(0.98, 1.02), 0.25);
  },

  rankup(k, t, p) {
    const rg = k.gain(0, k.out);
    const rbp = k.filter('bandpass', 500, 1.2, rg);
    k.noise('pink', t, t + 0.64, rbp);
    sweep(rbp.frequency, t, 400 * p, 7000 * p, 0.56);
    swell(rg.gain, t, 0.55, 0.35, 0, 0.06);
    for (let i = 0; i < RANK_ARP.length; i++) {
      brass(k, t + i * 0.075, RANK_ARP[i] * p, (i / (RANK_ARP.length - 1) - 0.5) * 1.1, 0.16 + i * 0.012, 0.012, 0.03, 0.32);
    }
    const tc = t + 0.56;
    for (let i = 0; i < RANK_CHORD.length; i++) {
      brass(k, tc, RANK_CHORD[i] * p, (i % 2 ? 0.5 : -0.5) * (0.4 + i * 0.2), 0.14, 0.03, 0.7, 1.1, 18);
    }
    kick(k, tc, 140 * p, 45 * p, 0.1, 0.8, 0.45);
    burst(k, tc, 'white', 'highpass', 3000, 0.7, 0.35, 0.3, k.out, 0.001);
    for (let i = 0; i < 7; i++) {
      bell(k, tc + 0.05 + i * 0.07, SPARKLE[i % 3] * p * (i > 3 ? 2 : 1), 1, 0.3, 0.07, 0.35, (i % 2 ? 0.7 : -0.7));
    }
  },

  decode(k, t, p) {
    const pn = k.pan(0, k.out);
    const g = k.gain(0, pn);
    const bp = k.filter('bandpass', 2200, 1.4, g);
    const o = k.osc('square', 1500, t, t + 0.72, bp);
    const s = k.osc('sine', 3000, t, t + 0.72, k.gain(0.5, g));
    const cg = k.gain(0, g);
    k.noise('white', t, t + 0.72, k.shaper('crush', k.filter('highpass', 4000, 0.7, cg)));
    const end = t + 0.6;
    let ts = t;
    while (ts < end) {
      const len = k.r(0.016, 0.03);
      const on = k.rng() < 0.72;
      o.frequency.setValueAtTime(k.pick(DATA_NOTES) * p, ts);
      s.frequency.setValueAtTime(k.pick(DATA_NOTES) * 2 * p, ts);
      g.gain.setTargetAtTime(on ? k.r(0.25, 0.5) : 0, ts, 0.0012);
      g.gain.setTargetAtTime(0, ts + len * 0.7, 0.002);
      cg.gain.setTargetAtTime(on && k.rng() < 0.3 ? 0.4 : 0, ts, 0.001);
      pn.pan.setTargetAtTime(k.r(-0.6, 0.6), ts, 0.003);
      ts += len;
    }
    g.gain.setTargetAtTime(0, ts, 0.004);
    glass(k, ts + 0.01, 3500 * p, 0.6);
  },

  glitch(k, t, p) {
    const pn = k.pan(0, k.out);
    const gate = k.gain(0, pn);
    const sh = k.shaper('crush', k.filter('bandpass', 1500, 1.2, gate));
    const sqg = k.gain(0.6, sh);
    const sq = k.osc('square', 220, t, t + 0.36, sqg);
    const nzg = k.gain(0, sh);
    k.noise('white', t, t + 0.36, nzg);
    let ts = t;
    const slices = Math.floor(k.r(6, 10));
    for (let i = 0; i < slices; i++) {
      const len = k.r(0.012, 0.032);
      const tonal = k.rng() < 0.55;
      gate.gain.setTargetAtTime(k.rng() < 0.85 ? k.r(0.4, 0.9) : 0, ts, 0.001);
      sq.frequency.setValueAtTime(k.pick(GLITCH_FREQS) * p, ts);
      sqg.gain.setTargetAtTime(tonal ? 0.7 : 0.1, ts, 0.001);
      nzg.gain.setTargetAtTime(tonal ? 0.1 : 0.7, ts, 0.001);
      pn.pan.setTargetAtTime(k.r(-0.85, 0.85), ts, 0.0015);
      ts += len;
    }
    gate.gain.setTargetAtTime(0, ts, 0.012);
  },

  /** Live: `x` is distance 0 (overhead) .. 1 (horizon) — gain, brightness and onset follow. */
  thunder(k, t, p, x) {
    const dist = num(x, k.r(0.3, 1), 0, 1);
    const near = 1 - dist;
    const dur = 4.4 + dist * 1.6;
    if (near > 0.35) {
      burst(k, t, 'crackle', 'bandpass', 1400, 0.6, 0.5 * near * near, 0.45, k.out, 0.004);
      burst(k, t, 'white', 'bandpass', 900, 0.8, 0.3 * near * near, 0.35, k.out, 0.006);
    }
    for (let s = -1; s <= 1; s += 2) {
      const g = k.gain(0, k.pan(s * 0.7, k.out));
      const lp = k.filter('lowpass', (220 + 700 * near) * p, 0.8, k.filter('highpass', 28, 0.7, g));
      k.noise('brown', t, t + dur, lp, k.r(0.9, 1.05));
      sweep(lp.frequency, t, (220 + 700 * near) * p, 95, dur);
      // Rolling: a quick rise, then a few random swells, then a long settle.
      const rise = 0.12 + dist * 0.35;
      g.gain.setValueAtTime(0, t);
      g.gain.setTargetAtTime(0.9, t, rise / 3);
      let tb = t + rise;
      for (let j = 0; j < 4; j++) {
        tb += k.r(0.25, 0.75);
        g.gain.setTargetAtTime(k.r(0.35, 1) * (1 - j * 0.15), tb, 0.12);
      }
      const left = t + dur - (tb + 0.3);
      g.gain.setTargetAtTime(0, tb + 0.3, Math.max(left, 0.5) / 7);
    }
  },

  unlock(k, t, p) {
    const T = 1.3;
    for (let s = -1; s <= 1; s += 2) {
      const g = k.gain(0, k.pan(s * 0.5, k.out));
      const lp = k.filter('lowpass', 120, 5, g);
      sweep(lp.frequency, t, 120, 2400, T);
      k.osc('sawtooth', N.A1 * p, t, t + 3.4, lp, s * 9);
      k.osc('sawtooth', N.A2 * p, t, t + 3.4, lp, -s * 7);
      k.osc('sawtooth', N.E3 * p, t, t + 3.4, k.gain(0.6, lp), s * 4);
      swell(g.gain, t, T, 0.3, 0.05, 1.9);
    }
    const sg = k.gain(0, k.out);
    k.osc('sine', N.A1 * p, t, t + 3.4, sg);
    swell(sg.gain, t, T, 0.5, 0.05, 1.6);
    const rg = k.gain(0, k.out);
    k.noise('pink', t, t + T + 0.1, k.filter('highpass', 2000, 0.7, rg));
    swell(rg.gain, t, T, 0.16, 0, 0.05);
    const tc = t + T;
    kick(k, tc, 80 * p, 45 * p, 0.1, 0.6, 0.4);
    for (let i = 0; i < UNLOCK_CHIME.length; i++) {
      bell(k, tc + i * 0.06, UNLOCK_CHIME[i] * p, 3.5, 2, 0.2 - i * 0.03, 1.6, (i - 1) * 0.6);
    }
  },

  error(k, t, p) {
    for (let i = 0; i < 2; i++) {
      const ts = t + i * 0.115;
      const g = k.gain(0, k.out);
      const lp = k.filter('lowpass', 1400, 2, g);
      const o = k.osc('square', 200 * p, ts, ts + 0.12, lp);
      sweep(o.frequency, ts, 200 * p, 178 * p, 0.09);
      k.osc('sawtooth', 99 * p, ts, ts + 0.12, k.gain(0.6, lp));
      g.gain.setValueAtTime(0, ts);
      g.gain.linearRampToValueAtTime(0.4, ts + 0.004);
      g.gain.setValueAtTime(0.4, ts + 0.07);
      g.gain.exponentialRampToValueAtTime(0.0004, ts + 0.1);
      g.gain.linearRampToValueAtTime(0, ts + 0.102);
    }
  },

  whoosh(k, t, p) {
    const T = 0.62;
    const peakAt = 0.3;
    const pn = k.pan(-0.75, k.out);
    pn.pan.setValueAtTime(-0.75, t);
    pn.pan.linearRampToValueAtTime(0.75, t + T);
    const g = k.gain(0, pn);
    for (let band = 1; band <= 2; band++) {
      const m = band === 1 ? 1 : 2.1;
      const bp = k.filter('bandpass', 400 * m, 1.2, k.gain(band === 1 ? 1 : 0.4, g));
      k.noise('pink', t, t + T + 0.05, bp);
      bp.frequency.setValueAtTime(380 * m * p, t);
      bp.frequency.exponentialRampToValueAtTime(2600 * m * p, t + peakAt);
      bp.frequency.exponentialRampToValueAtTime(520 * m * p, t + T);
    }
    swell(g.gain, t, peakAt, 0.8, 0, T - peakAt);
    const bg = k.gain(0, k.out);
    const b = k.osc('sine', 85 * p, t, t + T + 0.02, bg);
    sweep(b.frequency, t, 85 * p, 50 * p, T);
    swell(bg.gain, t, peakAt, 0.15, 0, T - peakAt);
  },

  /** Ambient: a distant metallic ping, mostly heard through the reverb. */
  ping(k, t, p) {
    const f = N.A5 * p;
    for (let s = -1; s <= 1; s += 2) {
      const lp = k.filter('lowpass', 4200, 0.7, k.pan(s * 0.25, k.out));
      bell(k, t, f * (1 + s * 0.0015), 2.756, 1.4, 0.4, 2.6, 0, lp);
    }
    const hg = k.gain(0, k.out);
    k.osc('sine', f * 4.07, t, t + 0.7, hg);
    perc(hg.gain, t, 0.001, 0.08, 0.6);
  },
};

// ── recipes: ambient loops (baked, seamless) ────────────────────────────────

const COMBAT_BAR = 2.4; // 100 BPM, 4 beats; 55 Hz × 2.4 s = 132 whole cycles (seamless bass)
const ALARM_BAR = 94 / 55; // ≈140 BPM, 4 beats; every source is gated, so no seam to hide

function heart(k, t, amp) {
  kick(k, t, 90, 42, 0.1, amp, 0.24);
  burst(k, t, 'brown', 'lowpass', 340, 1.2, amp * 0.6, 0.07, k.out, 0.002);
}

const LOOPS = {
  pulse(k, t) {
    const beat = COMBAT_BAR / 4;
    for (let b = 0; b < 4; b += 2) {
      heart(k, t + b * beat, 1);
      heart(k, t + b * beat + 0.27, 0.68);
    }
    // Bass pumping against the heartbeat (a sidechain shape, continuous at every beat).
    const bg = k.gain(0, k.out);
    const lp = k.filter('lowpass', 320, 2.2, bg);
    k.osc('sawtooth', N.A1, t, t + COMBAT_BAR, lp, -4);
    k.osc('sawtooth', N.A1, t, t + COMBAT_BAR, lp, 5);
    const res = 400;
    const curve = new Float32Array(Math.round(COMBAT_BAR * res) + 1);
    for (let i = 0; i < curve.length; i++) {
      const ph = ((i / res) % beat) / beat;
      const recover = 1 - Math.exp(-ph * 7);
      const close = ph > 0.94 ? 1 - (ph - 0.94) / 0.06 : 1;
      curve[i] = 0.32 * (0.12 + 0.88 * recover * close);
    }
    curve[curve.length - 1] = curve[0];
    bg.gain.setValueCurveAtTime(curve, t, COMBAT_BAR);
    for (let i = 0; i < 4; i++) burst(k, t + i * beat + beat / 2, 'white', 'highpass', 7000, 0.7, 0.08, 0.02);
  },

  alarm(k, t) {
    const beat = ALARM_BAR / 4;
    for (let b = 0; b < 4; b++) {
      const tb = t + b * beat;
      kick(k, tb, 110, 42, 0.07, 1, 0.18);
      burst(k, tb, 'white', 'highpass', 3000, 0.7, 0.25, 0.006);
      // Offbeat tritone stab.
      const sg = k.gain(0, k.out);
      const lp = k.filter('lowpass', 650, 2, sg);
      const sh = k.shaper('hard', lp);
      k.osc('sawtooth', N.A1, tb + beat / 2, tb + beat / 2 + 0.16, sh, -5);
      k.osc('sawtooth', 77.78, tb + beat / 2, tb + beat / 2 + 0.16, sh, 5);
      perc(sg.gain, tb + beat / 2, 0.004, 0.3, 0.12);
    }
    for (let s = 0; s < 16; s++) {
      burst(k, t + (s * beat) / 4, 'white', 'highpass', 7500, 0.7, s % 2 ? 0.05 : 0.1, 0.03);
    }
  },
};

// ── recipes: ambient layers (live, built on demand) ─────────────────────────
// Signature (k, t, L, engine-provided buffers). Each adds nodes under L.out; L.filters
// collects lowpasses whose base cutoff the mood steers.

const DRONE_VOICES = [
  [N.A1, 6, 1.0],
  [N.A1, -9, 0.8],
  [N.A2, 3, 0.45],
  [N.E2, -4, 0.3],
  [N.E3, 5, 0.12],
]; // frequency, detune (× side), amplitude
const LIFT_PAD = [N.A2, N.E3, N.A3, N.Cs4, N.E4];
const LIFT_SHIMMER = [N.A5, N.Cs6, N.E6];
const CINE_PAD = [N.A1, N.E2, N.C3, N.G3, N.B3, N.E4];

const LAYER_BUILDERS = {
  drone(k, t, L) {
    const lfoA = k.osc('sine', 0.047, t, 0, null);
    const lfoB = k.osc('sine', 0.0191, t, 0, null);
    const drift = k.osc('triangle', 0.07, t, 0, null);
    for (let s = -1; s <= 1; s += 2) {
      const lp = k.filter('lowpass', 300, 2.6, k.pan(s * 0.55, L.out));
      L.filters.push(lp);
      lfoA.connect(k.gain(s * 140, lp.frequency));
      lfoB.connect(k.gain(90, lp.frequency));
      const chorus = k.gain(s * 5, null);
      drift.connect(chorus);
      for (let i = 0; i < DRONE_VOICES.length; i++) {
        const [f, det, amp] = DRONE_VOICES[i];
        const o = k.osc('sawtooth', f, t, 0, k.gain(amp * 0.16, lp), s * det);
        chorus.connect(o.detune);
      }
    }
    k.osc('sine', N.A1, t, 0, k.gain(0.1, L.out));
    // Server hum with a slow flutter.
    const hum = k.gain(0.02, L.out);
    k.osc('sine', N.A2, t, 0, hum);
    k.osc('sine', N.A3, t, 0, k.gain(0.4, hum));
    k.osc('sine', 0.9, t, 0, k.gain(0.008, hum.gain));
    // Wind through the ruins: resonant band of pink noise wandering slowly.
    const bp = k.filter('bandpass', 700, 6, k.gain(0.5, L.out));
    k.noise('pink', t, 0, bp);
    k.osc('sine', 0.023, t, 0, k.gain(320, bp.frequency));
  },

  rain(k, t, L, buffers) {
    const gust = k.gain(1, L.out);
    k.osc('sine', 0.071, t, 0, k.gain(0.22, gust.gain));
    const hp = k.filter('highpass', 260, 0.6, k.filter('lowpass', 4500, 0.5, gust));
    k.buffer(buffers.rain, t, 0, hp, 1);
    // Heavier, distant downpour: the same field an octave down, darkened.
    const body = k.filter('highpass', 70, 0.6, k.filter('lowpass', 700, 0.6, k.gain(0.55, gust)));
    k.buffer(buffers.rain, t, 0, body, 0.5);
  },

  pulse(k, t, L, buffers) {
    if (buffers.pulse) {
      k.buffer(buffers.pulse, t, 0, L.out, 1, 0);
      L.looped = true;
    }
  },

  alarm(k, t, L, buffers) {
    // Dissonant cluster (A2 against B♭2) with tremolo, and an eerie beating minor second up high.
    const trem = k.gain(0.6, L.out);
    k.osc('sine', 5.3, t, 0, k.gain(0.4, trem.gain));
    const bp = k.filter('bandpass', 700, 1.6, trem);
    k.osc('sawtooth', N.A2, t, 0, k.gain(0.3, bp));
    k.osc('sawtooth', N.Bb2, t, 0, k.gain(0.3, bp));
    const vib = k.gain(15, null);
    k.osc('sine', 0.27, t, 0, vib);
    for (let s = -1; s <= 1; s += 2) {
      const o = k.osc('sine', s < 0 ? N.E6 : N.F6, t, 0, k.gain(0.035, k.pan(s * 0.5, L.out)));
      vib.connect(o.detune);
    }
    if (buffers.alarm) {
      k.buffer(buffers.alarm, t, 0, k.gain(0.9, L.out), 1, 0);
      L.looped = true;
    }
  },

  lift(k, t, L) {
    for (let s = -1; s <= 1; s += 2) {
      const lp = k.filter('lowpass', 2400, 0.7, k.pan(s * 0.6, L.out));
      for (let i = 0; i < LIFT_PAD.length; i++) {
        k.osc(i % 2 ? 'triangle' : 'sawtooth', LIFT_PAD[i], t, 0, k.gain(0.07, lp), s * (5 + i * 2));
      }
    }
    const shimmer = k.gain(0.5, L.out);
    k.osc('sine', 0.4, t, 0, k.gain(0.4, shimmer.gain));
    for (let i = 0; i < LIFT_SHIMMER.length; i++) {
      k.osc('sine', LIFT_SHIMMER[i], t, 0, k.gain(0.035, k.pan((i - 1) * 0.6, shimmer)));
    }
  },

  pad(k, t, L) {
    const lfo = k.osc('sine', 0.06, t, 0, null);
    for (let s = -1; s <= 1; s += 2) {
      const lp = k.filter('lowpass', 700, 0.8, k.pan(s * 0.8, L.out));
      lfo.connect(k.gain(s * 250, lp.frequency));
      for (let i = 0; i < CINE_PAD.length; i++) {
        k.osc('sawtooth', CINE_PAD[i], t, 0, k.gain(i ? 0.06 : 0.09, lp), s * 10 + i * 3);
      }
    }
  },
};

// ── engine ──────────────────────────────────────────────────────────────────

class Voice {
  cue = -1;
  start = 0;
  prio = 0;
  src = null; // baked voices: the buffer source
  out = null; // GainNode
  pan = null; // StereoPannerNode | null
  nodes = []; // live voices: every node the recipe made (sources included)
  pending = 0; // sources still running
  dead = false; // stolen: already out of the active list
}

export class AudioEngine {
  #settings;
  #bus;
  #injected;
  #ambient;
  #ctx = null;
  #rate = 48000; // bake / texture sample rate
  #liveOk = true; // recipes may run on the live context (sample rate ≥ 44.1 kHz)
  #offline = false;
  #failed = false;
  #disposed = false;
  #resuming = false;
  #suspendedByUs = false;
  #typing = true;
  #armed = false;

  #graph = null; // persistent nodes, see #buildGraph
  #strips = [];
  #bank = new Array(CUE_LIST.length).fill(null); // baked takes per cue
  #loopBufs = { rain: null, pulse: null, alarm: null };
  #res = { noise: {}, curves: CURVES };
  #kit;
  #last = new Float64Array(CUE_LIST.length).fill(-Infinity);
  #count = new Int16Array(CUE_LIST.length);
  #lastTake = new Int8Array(CUE_LIST.length).fill(-1);
  #active = [];
  #pool = [];
  #bySrc = new Map();
  #layers = {};
  #mood = 'calm';
  #duckUntil = 0;
  #duckDepth = 0;
  #bakeErrors = 0;
  #offs = [];
  #pingTimer = 0;
  #sweepTimer = 0;
  #suspendTimer = 0;
  #baked;
  #resolveBaked = noop;

  /**
   * @param {object} [opts]
   * @param {object} [opts.settings] settings store (core/settings.js interface)
   * @param {object} [opts.bus]      event bus (core/bus.js interface)
   * @param {BaseAudioContext} [opts.context] inject a context (e.g. OfflineAudioContext for tests)
   * @param {boolean} [opts.ambient=true] false: no ambient bed or pings (cues only)
   */
  constructor({ settings = defaultSettings, bus = defaultBus, context = null, ambient = true } = {}) {
    this.#settings = settings;
    this.#bus = bus;
    this.#injected = context;
    this.#ambient = ambient !== false;
    this.#kit = new Kit(this.#res, this.#adopt);
    this.#baked = new Promise((resolve) => (this.#resolveBaked = resolve));
    this.#typing = settings?.get?.('typingSounds') !== false;
    if (settings?.onChange) this.#offs.push(settings.onChange(this.#onSetting));
    if (bus?.on) this.#offs.push(bus.on('world:lightning', this.#onLightning));
    if (!context) this.#arm();
  }

  /** True once the context exists and is running (an injected offline context: once unlocked). */
  get ready() {
    const ctx = this.#ctx;
    return ctx !== null && !this.#disposed && (this.#offline || ctx.state === 'running');
  }

  /** Current ambient mood. */
  get mood() {
    return this.#mood;
  }

  /** The underlying context (null until unlock). */
  get context() {
    return this.#ctx;
  }

  /** Resolves when every cue is baked (immediately useful for tests and loading screens). */
  whenBaked() {
    return this.#baked;
  }

  /** Debug counters. */
  get stats() {
    let baked = 0;
    for (const b of this.#bank) if (b) baked++;
    let layers = 0;
    for (const key of LAYER_KEYS) if (this.#layers[key]) layers++;
    return {
      state: this.#ctx ? this.#ctx.state : this.#failed ? 'unavailable' : 'locked',
      voices: this.#active.length,
      sources: this.#bySrc.size,
      baked,
      cues: CUE_LIST.length,
      layers,
      mood: this.#mood,
      bakeErrors: this.#bakeErrors,
    };
  }

  /**
   * Create/resume the context (call from a user gesture) and start the ambient bed.
   * Idempotent; safe to call on every gesture.
   */
  unlock() {
    if (this.#disposed || this.#failed) return;
    if (!this.#ctx) {
      // Creating a context before any user activation only earns a console warning and a
      // suspended context; wait for the gesture listeners instead.
      const ua = typeof navigator !== 'undefined' ? navigator.userActivation : null;
      if (!this.#injected && ua && !ua.hasBeenActive) {
        this.#arm();
        return;
      }
      if (!this.#boot()) return;
    }
    const ctx = this.#ctx;
    if (!this.#offline && ctx.state !== 'running' && ctx.state !== 'closed' && !this.#resuming) {
      if (typeof document !== 'undefined' && document.hidden) return;
      this.#resuming = true;
      this.#suspendedByUs = false;
      ctx.resume().then(this.#onResumed, this.#onResumed);
    }
  }

  /**
   * Play a cue. Cheap: a buffer source + gain (+ panner). Never throws.
   * opts: pitch (playback-rate multiplier), gain (linear), pan (-1..1),
   *       delay (s, scheduled on the audio clock), distance (thunder only, 0..1).
   * Returns whether a voice started.
   */
  play(cue, opts = NO_OPTS) {
    const ctx = this.#ctx;
    if (ctx === null || this.#disposed) return false;
    if (!this.#offline && ctx.state !== 'running' && !this.#resuming) return false;
    const i = CUE_INDEX.get(cue);
    if (i === undefined) return false;
    if (i === TYPE_CUE && !this.#typing) return false;
    const def = CUE_LIST[i];
    const takes = this.#bank[i];
    if (takes === null && !def.live && !this.#liveOk) return false; // not baked yet
    const o = opts || NO_OPTS;
    const t = ctx.currentTime + num(o.delay, 0, 0, 30);
    const last = this.#last[i];
    if (t - last < def.gap && last - t < def.gap) return false;
    try {
      if (this.#count[i] >= def.voices) this.#stealOldest(i);
      else if (this.#active.length >= MAX_VOICES && !this.#stealLowest(def.prio)) return false;
      this.#last[i] = t;
      const pitch = num(o.pitch, 1, 0.25, 4) * (1 + def.jitter * (Math.random() * 2 - 1));
      const gain = num(o.gain, 1, 0, 4) * (0.9 + Math.random() * 0.1);
      const pan = clamp(num(o.pan, 0, -1, 1) + def.spread * (Math.random() * 2 - 1), -1, 1);
      if (takes !== null) this.#startBaked(i, def, takes, t, pitch, gain, pan);
      else this.#startLive(i, def, t, Math.min(pitch, 2), gain, pan, o.distance);
      if (def.duck !== null) this.#duck(def.duck[0], def.duck[1], t);
      return true;
    } catch {
      return false;
    }
  }

  /** Crossfade the ambient bed to a mood ('calm'|'mission'|'combat'|'alarm'|'victory'|'cinematic'). */
  setMood(name) {
    this.#applyMood(name, MOOD_TAU);
  }

  #applyMood(name, tau) {
    const m = MOODS[name];
    if (!m || this.#disposed) return;
    this.#mood = name;
    if (this.#graph === null || !this.#ambient) return;
    const now = this.#ctx.currentTime;
    for (const key of LAYER_KEYS) {
      const spec = LAYERS[key];
      const target = m[key] * spec.level;
      let L = this.#layers[key];
      if (target > 0) {
        if (!L) L = this.#buildLayer(key, now);
        if (!L) continue;
        L.fading = false;
        glide(L.out.gain, target, now, tau);
      } else if (L && !L.fading && !spec.permanent) {
        L.fading = true;
        L.fadeAt = now;
        glide(L.out.gain, 0, now, tau);
        this.#scheduleSweep();
      } else if (L && spec.permanent) {
        glide(L.out.gain, 0, now, tau);
      }
    }
    const drone = this.#layers.drone;
    if (drone) for (const f of drone.filters) glide(f.frequency, m.cutoff, now, tau);
    this.#sweepLayers(now);
  }

  /** Stop everything, release every node and listener, close an owned context. */
  dispose() {
    if (this.#disposed) return;
    this.#disposed = true;
    for (const off of this.#offs) off();
    this.#offs.length = 0;
    this.#disarm();
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', this.#onVisibility);
    clearTimeout(this.#pingTimer);
    clearTimeout(this.#sweepTimer);
    clearTimeout(this.#suspendTimer);
    this.#resolveBaked();
    const ctx = this.#ctx;
    if (!ctx) return;
    ctx.removeEventListener?.('statechange', this.#onState);
    const now = ctx.currentTime;
    for (let n = this.#active.length - 1; n >= 0; n--) this.#kill(this.#active[n], now, true);
    for (const v of Array.from(this.#bySrc.values())) this.#release(v);
    this.#bySrc.clear();
    for (const key of LAYER_KEYS) if (this.#layers[key]) this.#teardown(key);
    for (const n of this.#graph?.nodes || []) n.disconnect();
    this.#graph = null;
    if (!this.#injected && ctx.state !== 'closed') ctx.close().catch(noop);
  }

  // ── boot & graph ──────────────────────────────────────────────────────────

  #boot() {
    let ctx = this.#injected;
    if (!ctx) {
      const AC = globalThis.AudioContext || globalThis.webkitAudioContext;
      if (!AC) return this.#fail();
      try {
        ctx = new AC({ latencyHint: 'interactive' });
      } catch {
        try {
          ctx = new AC();
        } catch {
          return this.#fail();
        }
      }
    }
    this.#ctx = ctx;
    this.#offline = typeof ctx.startRendering === 'function';
    // Baked cues and generated textures use 44.1/48 kHz even on odd devices (a Bluetooth
    // headset in hands-free mode runs at 16 kHz): recipes never cross Nyquist, and buffer
    // sources resample on playback. Only the reverb impulse must match the context rate.
    const sr = ctx.sampleRate;
    this.#rate = sr >= 44100 && sr <= 48000 ? sr : 48000;
    this.#liveOk = sr >= 44100;
    // Just enough noise for a live-synthesized first click; the bake replaces it with the
    // seeded 2 s buffer before rendering anything.
    this.#res.noise.white = makeNoise(ctx, this.#rate, 'white', Math.random, 0.5);
    this.#buildGraph();
    if (!this.#offline) {
      ctx.addEventListener?.('statechange', this.#onState);
      if (typeof document !== 'undefined') document.addEventListener('visibilitychange', this.#onVisibility);
      if (this.#ambient) this.#schedulePing();
    }
    this.#bake().catch(() => this.#resolveBaked());
    return true;
  }

  #fail() {
    this.#failed = true;
    this.#disarm();
    this.#resolveBaked();
    return false;
  }

  #buildGraph() {
    const ctx = this.#ctx;
    const s = this.#settings;
    const nodes = [];
    const gain = (v, to) => {
      const n = ctx.createGain();
      n.gain.value = v;
      if (to) n.connect(to);
      nodes.push(n);
      return n;
    };

    // Output: master → fade (tab visibility) → gentle limiter → never-clip safety curve.
    const clip = ctx.createWaveShaper();
    clip.curve = CURVES.limit;
    clip.oversample = 'none'; // no resampling filters → the curve's bound is a hard bound
    clip.connect(ctx.destination);
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -9;
    comp.knee.value = 8;
    comp.ratio.value = 10;
    comp.attack.value = 0.002;
    comp.release.value = 0.2;
    comp.connect(clip);
    nodes.push(clip, comp);
    const fade = gain(1, null);
    const master = gain(taper(s?.get?.('masterVolume') ?? 0.8), fade);
    // A fresh DynamicsCompressor over-attenuates for its first ~150 ms (its detector starts
    // from rest), which would swallow the click that unlocked audio. Start on a bypass that
    // is time-aligned with the look-ahead and makeup-matched, then crossfade into the
    // compressor: both paths carry the same signal, so the sum stays exactly constant.
    const now = ctx.currentTime;
    const compIn = gain(0, comp);
    const align = ctx.createDelay(0.05);
    align.delayTime.value = COMP_LOOKAHEAD;
    align.connect(clip);
    nodes.push(align);
    const bypass = gain(COMP_MAKEUP, align);
    fade.connect(compIn);
    fade.connect(bypass);
    compIn.gain.setValueAtTime(0, now);
    compIn.gain.setTargetAtTime(1, now + COMP_WARMUP, 0.04);
    bypass.gain.setValueAtTime(COMP_MAKEUP, now);
    bypass.gain.setTargetAtTime(0, now + COMP_WARMUP, 0.04);
    bypass.gain.setValueAtTime(0, now + COMP_WARMUP + 0.8); // residual e^-20: snap to the zero-gain fast path

    // Shared reverb (impulse filled in by the bake, after a yield).
    const convolver = ctx.createConvolver();
    convolver.normalize = true;
    const revOut = gain(REVERB_RETURN, master);
    convolver.connect(revOut);
    const revHp = ctx.createBiquadFilter();
    revHp.type = 'highpass';
    revHp.frequency.value = 160;
    revHp.connect(convolver);
    nodes.push(convolver, revHp);
    const revIn = gain(1, revHp);

    // Ping-pong echo: L → R → L …, band-limited in the loop so repeats get darker and thinner.
    const dl = ctx.createDelay(1);
    const dr = ctx.createDelay(1);
    dl.delayTime.value = ECHO_TIME;
    dr.delayTime.value = ECHO_TIME;
    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 450;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 5500;
    const merge = ctx.createChannelMerger(2);
    nodes.push(dl, dr, hp, lp, merge);
    const echoIn = gain(1, dl);
    dl.connect(hp);
    hp.connect(lp);
    lp.connect(gain(ECHO_FEEDBACK, dr));
    dr.connect(gain(ECHO_FEEDBACK, dl));
    dl.connect(merge, 0, 0);
    dr.connect(merge, 0, 1);
    const echoOut = gain(ECHO_RETURN, master);
    merge.connect(echoOut);
    echoOut.connect(gain(0.25, revIn));

    // Buses: volume is applied on dry and on every send (post-fader sends).
    const sfxVol = taper(s?.get?.('sfxVolume') ?? 0.85);
    const musVol = taper(s?.get?.('musicVolume') ?? 0.55);
    const sfx = { dry: gain(sfxVol, master), rev: gain(sfxVol, revIn), echo: gain(sfxVol, echoIn) };
    const duck = [gain(1, master), gain(1, revIn), gain(1, echoIn)];
    const music = { dry: gain(musVol, duck[0]), rev: gain(musVol, duck[1]), echo: gain(musVol, duck[2]) };

    // One strip per cue: its level and its send amounts.
    this.#strips = CUE_LIST.map((def, i) => {
      const b = def.bus === 'music' ? music : sfx;
      const input = gain(i === TYPE_CUE && !this.#typing ? 0 : 1, b.dry);
      if (def.reverb > 0) input.connect(gain(def.reverb, b.rev));
      if (def.echo > 0) input.connect(gain(def.echo, b.echo));
      return input;
    });

    this.#graph = {
      nodes,
      master,
      fade,
      convolver,
      sfx: [sfx.dry, sfx.rev, sfx.echo],
      music: [music.dry, music.rev, music.echo],
      musicDry: music.dry,
      musicRev: music.rev,
      duck,
    };
  }

  // ── baking ────────────────────────────────────────────────────────────────

  /**
   * Everything after the gesture, in a handful of short tasks (each a few ms of plain JS) so
   * the boot transition never hitches, ordered by when the player will need it: the bed fades
   * in, UI cues, the reverb, combat cues and loops, the rain texture, then the big moments.
   */
  async #bake() {
    const ctx = this.#ctx;
    const rate = this.#rate;
    const alive = () => !this.#disposed;
    const seed = mulberry32(0xa11ce);
    const OAC = globalThis.OfflineAudioContext;
    const step = async () => {
      await yieldTask();
      return alive();
    };
    if (!(await step())) return;
    this.#applyMood(this.#mood, BOOT_TAU); // the world fades in
    if (!(await step())) return;
    this.#res.noise.white = makeNoise(ctx, rate, 'white', seed);
    this.#res.noise.pink = makeNoise(ctx, rate, 'pink', seed);
    if (OAC) await this.#bakeBatch(OAC, BAKE_BATCHES[0], false);
    if (!(await step())) return;
    this.#res.noise.brown = makeNoise(ctx, rate, 'brown', seed);
    this.#res.noise.crackle = makeNoise(ctx, rate, 'crackle', seed);
    const impulse = await makeImpulse(ctx, REVERB_SECONDS, seed, alive);
    if (!impulse) return;
    this.#graph.convolver.buffer = impulse;
    if (OAC) await this.#bakeBatch(OAC, BAKE_BATCHES[1], true);
    if (!alive()) return;
    this.#loopBufs.rain = await makeRain(ctx, rate, 6, seed, alive);
    if (!alive()) return;
    this.#startRain();
    if (OAC) await this.#bakeBatch(OAC, BAKE_BATCHES[2], false);
    if (alive()) this.#resolveBaked();
  }

  /**
   * Bake a batch: one small offline context per cue (its takes end to end, each with its own
   * DC blocker) and one per mood loop. Every graph is built in this task and all of them render
   * concurrently, so however busy the main thread is, the batch waits for it only once — while
   * each context stays short, so no node is processed for longer than its own cue. A recipe
   * that throws leaves its cue live-synthesized.
   */
  async #bakeBatch(OAC, names, loops) {
    const groups = names.map((name) => {
      const def = CUE_LIST[CUE_INDEX.get(name)];
      const jobs = [];
      let at = BAKE_GAP;
      for (let v = 0; v < def.variants; v++) {
        jobs.push({ recipe: SYNTHS[name], seed: hashString(name) + v * 7919, at, len: def.dur });
        at += def.dur + BAKE_GAP;
      }
      return { name, channels: def.stereo ? 2 : 1, jobs, length: at };
    });
    if (loops) {
      for (const [name, bar] of [['pulse', COMBAT_BAR], ['alarm', ALARM_BAR]]) {
        const len = bar + LOOP_TAIL;
        groups.push({ name, loop: bar, channels: 2, jobs: [{ recipe: LOOPS[name], seed: 0x100b, at: BAKE_GAP, len }], length: len + 2 * BAKE_GAP });
      }
    }
    const bufs = await Promise.all(groups.map((g) => this.#renderGroup(OAC, g)));
    if (this.#disposed) return;
    // Slicing a batch is a few ms of copying: one task, so the cues arrive together.
    for (let n = 0; n < groups.length; n++) {
      const g = groups[n];
      const buf = bufs[n];
      if (g.loop) {
        if (buf) this.#loopBufs[g.name] = this.#sliceLoop(buf, BAKE_GAP, g.loop, -6);
        continue;
      }
      const i = CUE_INDEX.get(g.name);
      let peak = 0;
      if (buf) for (const j of g.jobs) peak = Math.max(peak, peakOf(buf, j.at, j.len, g.channels));
      if (!(peak > 0)) {
        this.#bakeErrors++; // the cue stays live-synthesized
        continue;
      }
      const k = dbToGain(CUE_LIST[i].peak) / peak;
      this.#bank[i] = g.jobs.map((j) => this.#slice(buf, j.at, j.len, g.channels, k));
    }
    if (loops) this.#attachLoops();
  }

  /** Build one group's graph and start rendering it; resolves to its buffer, or null on failure. */
  #renderGroup(OAC, group) {
    try {
      const sr = this.#rate;
      const oac = new OAC(group.channels, Math.ceil(group.length * sr), sr);
      const kit = new Kit(this.#res, noop);
      for (const job of group.jobs) {
        const dc = oac.createBiquadFilter();
        dc.type = 'highpass';
        dc.frequency.value = 12;
        dc.Q.value = 0.5;
        dc.connect(oac.destination);
        job.recipe(kit.bind(oac, dc, mulberry32(job.seed), null), job.at, 1);
      }
      return oac.startRendering().catch(() => null);
    } catch {
      return Promise.resolve(null);
    }
  }

  /** Window of `buf` → its own buffer: scaled by `k`, trailing silence trimmed, 3 ms fade-out. */
  #slice(buf, at, len, chs, k) {
    const sr = buf.sampleRate;
    const s0 = Math.round(at * sr);
    const n = Math.min(Math.round(len * sr), buf.length - s0);
    let end = 0;
    for (let c = 0; c < chs; c++) {
      const d = buf.getChannelData(c);
      for (let j = n - 1; j > end; j--) {
        if (Math.abs(d[s0 + j] * k) > 3e-5) {
          end = j;
          break;
        }
      }
    }
    const fade = Math.round(0.003 * sr);
    const size = Math.min(n, end + fade + 1);
    const out = this.#ctx.createBuffer(chs, size, sr);
    for (let c = 0; c < chs; c++) {
      const src = buf.getChannelData(c);
      const dst = out.getChannelData(c);
      for (let j = 0; j < size; j++) dst[j] = src[s0 + j] * k;
      for (let j = 0; j < fade && j < size; j++) dst[size - 1 - j] *= j / fade;
    }
    return out;
  }

  /** Window of `buf` → a seamless loop of `length` s: the tail past the end folds over the start. */
  #sliceLoop(buf, at, length, peakDb) {
    const sr = buf.sampleRate;
    const s0 = Math.round(at * sr);
    const n = Math.round(length * sr);
    const total = Math.min(Math.round((length + LOOP_TAIL) * sr), buf.length - s0);
    const out = this.#ctx.createBuffer(2, n, sr);
    const k = dbToGain(peakDb) / (peakOf(buf, at, length + LOOP_TAIL, 2) || 1);
    for (let c = 0; c < 2; c++) {
      const src = buf.getChannelData(c);
      const dst = out.getChannelData(c);
      for (let j = 0; j < total; j++) dst[j % n] += src[s0 + j] * k;
    }
    return out;
  }

  // ── voices ────────────────────────────────────────────────────────────────

  #startBaked(i, def, takes, t, pitch, gain, pan) {
    const ctx = this.#ctx;
    let take = 0;
    if (takes.length > 1) {
      take = Math.floor(Math.random() * (takes.length - 1));
      if (take >= this.#lastTake[i]) take++;
    }
    this.#lastTake[i] = take;
    const v = this.#acquire(i, def, t);
    const src = ctx.createBufferSource();
    src.buffer = takes[take];
    src.playbackRate.value = pitch;
    const g = ctx.createGain();
    g.gain.value = gain;
    src.connect(g);
    v.src = src;
    v.out = g;
    this.#route(v, pan, i);
    this.#adopt(src, v);
    src.start(t);
  }

  #startLive(i, def, t, pitch, gain, pan, extra) {
    const ctx = this.#ctx;
    const v = this.#acquire(i, def, t);
    const g = ctx.createGain();
    g.gain.value = gain * dbToGain(def.peak);
    v.out = g;
    this.#route(v, pan, i);
    SYNTHS[def.name](this.#kit.bind(ctx, g, Math.random, v), t, pitch, extra);
    if (v.pending === 0) this.#release(v);
  }

  #route(v, pan, i) {
    let tail = v.out;
    if (pan > 0.004 || pan < -0.004) {
      const p = this.#ctx.createStereoPanner();
      p.pan.value = pan;
      tail.connect(p);
      v.pan = p;
      tail = p;
    }
    tail.connect(this.#strips[i]);
  }

  /**
   * Register a voice's source: on `ended` it disconnects, and the last one frees the voice.
   * Layer sources run until their layer is torn down, so they need no bookkeeping.
   */
  #adopt = (src, owner) => {
    if (!(owner instanceof Voice)) return;
    owner.pending++;
    this.#bySrc.set(src, owner);
    src.onended = this.#onEnded;
  };

  #onEnded = (e) => {
    const src = e.target;
    src.onended = null;
    src.disconnect();
    const v = this.#bySrc.get(src);
    if (v === undefined) return;
    this.#bySrc.delete(src);
    if (--v.pending <= 0) this.#release(v);
  };

  #acquire(i, def, t) {
    const v = this.#pool.pop() || new Voice();
    v.cue = i;
    v.start = t;
    v.prio = def.prio;
    v.dead = false;
    v.pending = 0;
    this.#active.push(v);
    this.#count[i]++;
    return v;
  }

  #release(v) {
    if (v.cue < 0) return;
    v.src?.disconnect();
    v.out?.disconnect();
    v.pan?.disconnect();
    for (const n of v.nodes) n.disconnect();
    v.nodes.length = 0;
    if (!v.dead) this.#deactivate(v);
    v.src = v.out = v.pan = null;
    v.cue = -1;
    v.pending = 0;
    this.#pool.push(v);
  }

  #deactivate(v) {
    const list = this.#active;
    const at = list.indexOf(v);
    if (at >= 0) {
      list[at] = list[list.length - 1];
      list.pop();
    }
    this.#count[v.cue]--;
    v.dead = true;
  }

  /** Fade a voice out over a few ms and stop its sources; `ended` does the cleanup. */
  #kill(v, now, immediate = false) {
    if (v.dead) return;
    this.#deactivate(v);
    const stopAt = immediate ? now : Math.max(now, v.start) + STEAL_TAU * 6;
    v.out.gain.cancelScheduledValues(now);
    v.out.gain.setTargetAtTime(0, now, STEAL_TAU);
    if (v.src !== null) {
      v.src.stop(stopAt);
      return;
    }
    for (const n of v.nodes) if (typeof n.stop === 'function') n.stop(stopAt);
  }

  #stealOldest(i) {
    let victim = null;
    for (const v of this.#active) if (v.cue === i && (victim === null || v.start < victim.start)) victim = v;
    if (victim) this.#kill(victim, this.#ctx.currentTime);
  }

  #stealLowest(prio) {
    let victim = null;
    for (const v of this.#active) {
      if (v.prio > prio) continue;
      if (victim === null || v.prio < victim.prio || (v.prio === victim.prio && v.start < victim.start)) victim = v;
    }
    if (!victim) return false;
    this.#kill(victim, this.#ctx.currentTime);
    return true;
  }

  /** Dip the ambient bed (never shallower than a duck already in progress). */
  #duck(depth, hold, t) {
    const interrupting = t < this.#duckUntil;
    if (interrupting && depth <= this.#duckDepth) return;
    this.#duckUntil = t + hold;
    this.#duckDepth = depth;
    for (const n of this.#graph.duck) {
      if (interrupting) n.gain.cancelScheduledValues(t); // drop the pending recovery
      n.gain.setTargetAtTime(1 - depth, t, 0.02);
      n.gain.setTargetAtTime(1, t + hold, 0.35);
    }
  }

  // ── ambient layers ────────────────────────────────────────────────────────

  #buildLayer(key, now) {
    if (key === 'rain' && !this.#loopBufs.rain) return null;
    const ctx = this.#ctx;
    const g = this.#graph;
    const out = ctx.createGain();
    out.gain.value = 0;
    out.connect(g.musicDry);
    const send = ctx.createGain();
    send.gain.value = LAYERS[key].send;
    out.connect(send);
    send.connect(g.musicRev);
    const L = { key, out, nodes: [send], filters: [], fading: false, fadeAt: 0, looped: false, pending: 0 };
    LAYER_BUILDERS[key](this.#kit.bind(ctx, out, Math.random, L), now, L, this.#loopBufs);
    this.#layers[key] = L;
    return L;
  }

  /** The rain texture is ready: fade its layer in at the current mood's level. */
  #startRain() {
    if (!this.#ambient || this.#layers.rain || this.#graph === null) return;
    const now = this.#ctx.currentTime;
    const L = this.#buildLayer('rain', now);
    if (L) glide(L.out.gain, MOODS[this.#mood].rain * LAYERS.rain.level, now, BOOT_TAU);
  }

  /** Loops finished baking after their layer was built: add them now. */
  #attachLoops() {
    const now = this.#ctx.currentTime;
    for (const key of ['pulse', 'alarm']) {
      const L = this.#layers[key];
      const buf = this.#loopBufs[key];
      if (!L || L.looped || !buf) continue;
      const k = this.#kit.bind(this.#ctx, L.out, Math.random, L);
      k.buffer(buf, now, 0, key === 'alarm' ? k.gain(0.9, L.out) : L.out, 1, 0);
      L.looped = true;
    }
  }

  #sweepLayers(now) {
    for (const key of LAYER_KEYS) {
      const L = this.#layers[key];
      if (L && L.fading && now - L.fadeAt >= LAYER_RETIRE) this.#teardown(key);
    }
  }

  #teardown(key) {
    const L = this.#layers[key];
    this.#layers[key] = null;
    for (const n of L.nodes) {
      if (typeof n.stop === 'function') n.stop();
      n.disconnect();
    }
    L.nodes.length = 0;
    L.out.disconnect();
  }

  #scheduleSweep(seconds = LAYER_RETIRE) {
    if (this.#offline) return; // offline tests drive sweeps through setMood
    clearTimeout(this.#sweepTimer);
    this.#sweepTimer = setTimeout(this.#onSweep, (seconds + 0.25) * 1000);
  }

  #onSweep = () => {
    if (!this.#ctx || this.#disposed) return;
    const now = this.#ctx.currentTime;
    this.#sweepLayers(now);
    // Retirement runs on the audio clock, which stops while the tab is hidden: if anything is
    // still fading, come back when the soonest one is due.
    let due = Infinity;
    for (const key of LAYER_KEYS) {
      const L = this.#layers[key];
      if (L && L.fading) due = Math.min(due, L.fadeAt + LAYER_RETIRE - now);
    }
    if (due < Infinity) this.#scheduleSweep(Math.max(due, 0.5));
  };

  // ── events ────────────────────────────────────────────────────────────────

  #onSetting = (key, value) => {
    if (key === 'typingSounds') this.#typing = value !== false;
    const g = this.#graph;
    if (g === null) return;
    const now = this.#ctx.currentTime;
    switch (key) {
      case 'masterVolume':
        glide(g.master.gain, taper(value), now, BUS_TAU);
        break;
      case 'sfxVolume':
        for (const n of g.sfx) glide(n.gain, taper(value), now, BUS_TAU);
        break;
      case 'musicVolume':
        for (const n of g.music) glide(n.gain, taper(value), now, BUS_TAU);
        break;
      case 'typingSounds':
        glide(this.#strips[TYPE_CUE].gain, this.#typing ? 1 : 0, now, BUS_TAU);
        break;
      default:
    }
  };

  #onLightning = () => {
    if (!this.ready) return;
    // Sound travels ~340 m/s: the longer the gap, the further, duller and quieter the strike.
    const delay = 0.25 + Math.random() * 0.85;
    const distance = (delay - 0.25) / 0.85;
    this.play('thunder', { delay, distance, gain: 1 - distance * 0.45, pan: (Math.random() * 2 - 1) * 0.6 });
  };

  #schedulePing() {
    clearTimeout(this.#pingTimer);
    this.#pingTimer = setTimeout(this.#onPing, (PING_MIN + Math.random() * (PING_MAX - PING_MIN)) * 1000);
  }

  #onPing = () => {
    if (this.#disposed) return;
    const m = MOODS[this.#mood];
    if (this.ready && Math.random() < m.pings) {
      const ratio = PING_RATIOS[Math.floor(Math.random() * PING_RATIOS.length)];
      const pan = (Math.random() * 2 - 1) * 0.8;
      const gain = 0.5 + Math.random() * 0.5;
      this.play('ping', { pitch: ratio, pan, gain });
      // Sometimes a fainter answer from across the city.
      if (Math.random() < 0.3) {
        this.play('ping', { pitch: ratio * PING_RATIOS[1 + Math.floor(Math.random() * 4)], pan: -pan, gain: gain * 0.45, delay: 0.35 + Math.random() * 0.5 });
      }
    }
    this.#schedulePing();
  };

  #onResumed = () => {
    this.#resuming = false;
    if (this.#ctx?.state === 'running') this.#disarm();
  };

  #onState = () => {
    const state = this.#ctx?.state;
    if (state === 'running') this.#disarm();
    else if (state !== 'closed' && !this.#suspendedByUs && !this.#disposed) this.#arm(); // e.g. iOS interruption
  };

  #onVisibility = () => {
    const ctx = this.#ctx;
    const g = this.#graph;
    if (!ctx || !g || this.#disposed || ctx.state === 'closed') return;
    clearTimeout(this.#suspendTimer);
    const now = ctx.currentTime;
    if (document.hidden) {
      glide(g.fade.gain, 0, now, 0.06);
      this.#suspendTimer = setTimeout(this.#suspendHidden, 450);
    } else {
      if (this.#suspendedByUs) {
        this.#suspendedByUs = false;
        this.#resuming = true;
        ctx.resume().then(this.#onResumed, this.#onResumed);
      }
      glide(g.fade.gain, 1, now, 0.25);
    }
  };

  #suspendHidden = () => {
    const ctx = this.#ctx;
    if (!ctx || this.#disposed || !document.hidden || ctx.state !== 'running') return;
    this.#suspendedByUs = true;
    ctx.suspend().catch(noop);
  };

  #onGesture = () => this.unlock();

  #arm() {
    if (this.#armed || this.#injected || typeof window === 'undefined') return;
    this.#armed = true;
    for (const type of GESTURES) window.addEventListener(type, this.#onGesture, { capture: true, passive: true });
  }

  #disarm() {
    if (!this.#armed) return;
    this.#armed = false;
    for (const type of GESTURES) window.removeEventListener(type, this.#onGesture, { capture: true });
  }
}

/** Peak of the first `chs` channels of `buf` within [at, at + len) seconds. */
function peakOf(buf, at, len, chs) {
  const s0 = Math.round(at * buf.sampleRate);
  const s1 = Math.min(buf.length, s0 + Math.round(len * buf.sampleRate));
  let peak = 0;
  for (let c = 0; c < chs; c++) {
    const d = buf.getChannelData(c);
    for (let j = s0; j < s1; j++) {
      const a = d[j] < 0 ? -d[j] : d[j];
      if (a > peak) peak = a;
    }
  }
  return peak;
}
