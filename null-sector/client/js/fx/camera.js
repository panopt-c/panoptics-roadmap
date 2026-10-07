/**
 * camera.js — screen shake and parallax for the whole presentation.
 *
 * Shake: the trauma model (Squirrel Eiserloh, GDC 2016, "Math for Game Programmers:
 * Juicing Your Cameras With Math"). Gameplay adds *trauma* (0..1); trauma decays
 * linearly (1.4/s) and the visible shake is trauma², so small hits stay subtle, big hits
 * are violent, and every shake eases out instead of stopping dead. Offsets come from
 * smooth 1-D gradient noise sampled at three seeds (x, y, roll) — continuous, never the
 * jittery white-noise look of Math.random() — and the noise is gained then soft-clipped
 * so peaks genuinely reach the budget (14 CSS px, 0.55°) without flat plateaus. The noise
 * phase advances faster at high trauma, so heavy impacts rattle and light ones sway.
 *
 * Parallax: pointer(nx, ny) sets a target that two critically damped springs chase (no
 * overshoot, frame-rate independent); a whisper of noise drift keeps the world breathing
 * when the pointer is still. `state.x/y` (-1..1) is for the world's parallax layers only —
 * the #ui transform carries shake and roll exclusively, because the post pass applies the
 * exact same translate+rotate to the GL composite and particles must stay glued to DOM.
 *
 * DOM writes: `translate3d(x, y, 0) rotate(r)` on `root`, quantised (0.01 px, 0.001°) and
 * written only when the quantised value changes; cleared to '' at rest — including shakes too
 * faint to see (< 0.05 px), e.g. a distant lightning strike — so #ui isn't a needless
 * compositor layer. `state` is built from the same quantised values, so the GL
 * composite and the DOM always agree exactly. Where CSS Typed OM exists, the transform is
 * a pre-built CSSTransformValue mutated in place — no string building, no CSS parsing,
 * zero allocations per frame; elsewhere it falls back to a style string (only while shaking).
 *
 * Settings are read live each frame: `shake` scales amplitude, `reducedMotion` scales it
 * by 0.25 and disables parallax (snapped, not animated, to 0).
 */
import { Spring, noise1 } from '../core/math.js';

const MAX_OFFSET = 14; // CSS px at trauma 1, settings.shake 1
const MAX_ROLL = (0.55 * Math.PI) / 180; // rad
const DECAY = 1.4; // trauma per second
const REDUCED_SCALE = 0.25;

const NOISE_GAIN = 1.6; // raw noise1 rarely exceeds ±0.8; this lets peaks use the full budget
const FREQ_BASE = 13; // noise cells per second at low trauma (a sway)…
const FREQ_TRAUMA = 15; // …plus this much at trauma 1 (a rattle)
const SEED_X = 17.31;
const SEED_Y = 91.77;
const SEED_ROLL = 163.09;
const SEED_DRIFT_X = 211.5;
const SEED_DRIFT_Y = 247.9;

const PX_Q = 100; // quantisation: 0.01 px
const DEG_Q = 1000; // quantisation: 0.001°
const REST_PX = 5; // below 0.05 px…
const REST_DEG = 2; // …and 0.002° the shake is invisible: treat as rest (no DOM write, no layer)
const MAX_DT = 0.25; // matches Loop maxFrame: decay stays real-time even at low frame rates
const RAD_TO_DEG = 180 / Math.PI;

/** noise → [-1, 1] with gain and a smooth cubic knee (slope 0 at the limit, no plateau edge). */
function shaped(x) {
  let v = noise1(x) * NOISE_GAIN;
  if (v > 1) v = 1;
  else if (v < -1) v = -1;
  return v * (1.5 - 0.5 * v * v);
}

function readSettings(settings, key, fallback) {
  if (!settings) return fallback;
  if (typeof settings.get === 'function') {
    const v = settings.get(key);
    return v === undefined ? fallback : v;
  }
  return key in settings ? settings[key] : fallback;
}

export class Camera {
  /** Parallax spring stiffness (angular frequency, rad/s). ~0.6 s to settle: floaty, never laggy. */
  parallaxOmega = 5;
  /** Idle parallax wander amplitude (fraction of the -1..1 range) and speed (noise cells / s). */
  drift = 0.05;
  driftRate = 0.11;

  #root;
  #settings;
  #trauma = 0;
  #phase = 0;
  #time = 0;
  #targetX = 0;
  #targetY = 0;
  #springX;
  #springY;
  #state = { x: 0, y: 0, shakeX: 0, shakeY: 0, roll: 0 };

  // Last values written to the DOM (quantised integers) and whether a transform is set.
  #applied = false;
  #qx = 0;
  #qy = 0;
  #qr = 0;

  // CSS Typed OM path (null → string fallback).
  #om = null;

  constructor({ root = null, settings = null } = {}) {
    this.#root = root && root.style ? root : null;
    this.#settings = settings;
    this.#springX = new Spring(0, this.parallaxOmega);
    this.#springY = new Spring(0, this.parallaxOmega);
    this.#om = this.#buildTypedOM();
  }

  /** Adds trauma (0..1 scale; the sum is clamped to 1). Negative or invalid amounts are ignored. */
  addTrauma(amount) {
    const a = +amount;
    if (!(a > 0)) return;
    const t = this.#trauma + a;
    this.#trauma = t > 1 ? 1 : t;
  }

  /** Parallax target in -1..1 (e.g. pointer position normalised to the viewport). */
  pointer(nx, ny) {
    const x = +nx;
    const y = +ny;
    this.#targetX = x > 1 ? 1 : x < -1 ? -1 : x || 0;
    this.#targetY = y > 1 ? 1 : y < -1 ? -1 : y || 0;
  }

  /** Advances shake and parallax by real (unscaled, hit-stop-immune) time and updates the DOM. */
  frame(realDt) {
    let dt = +realDt;
    if (!(dt > 0)) dt = 0;
    else if (dt > MAX_DT) dt = MAX_DT; // a stall (debugger, tab switch) must not skip the decay curve
    this.#time += dt;

    let shakeSetting = +readSettings(this.#settings, 'shake', 1);
    if (!(shakeSetting > 0)) shakeSetting = 0;
    else if (shakeSetting > 2) shakeSetting = 2;
    const reduced = !!readSettings(this.#settings, 'reducedMotion', false);
    const amp = shakeSetting * (reduced ? REDUCED_SCALE : 1);

    // ── trauma → shake ──
    let trauma = this.#trauma;
    if (trauma > 0) {
      trauma -= DECAY * dt;
      if (trauma < 0) trauma = 0;
      this.#trauma = trauma;
    }
    this.#phase += dt * (FREQ_BASE + FREQ_TRAUMA * trauma);

    let qx = 0;
    let qy = 0;
    let qr = 0;
    const shake = trauma * trauma * amp;
    if (shake > 0) {
      const p = this.#phase;
      qx = Math.round(MAX_OFFSET * shake * shaped(p + SEED_X) * PX_Q);
      qy = Math.round(MAX_OFFSET * shake * shaped(p + SEED_Y) * PX_Q);
      // Roll on a slightly slower clock: rotation reads heavier than translation.
      qr = Math.round(MAX_ROLL * RAD_TO_DEG * shake * shaped(p * 0.8 + SEED_ROLL) * DEG_Q);
      if (qx < REST_PX && qx > -REST_PX && qy < REST_PX && qy > -REST_PX && qr < REST_DEG && qr > -REST_DEG) {
        qx = qy = qr = 0;
      }
    }

    // ── parallax ──
    const sx = this.#springX;
    const sy = this.#springY;
    if (reduced) {
      if (sx.value !== 0 || sx.velocity !== 0) sx.snap(0);
      if (sy.value !== 0 || sy.velocity !== 0) sy.snap(0);
    } else {
      const d = this.drift;
      const tt = this.#time * this.driftRate;
      sx.omega = sy.omega = this.parallaxOmega;
      sx.target = this.#targetX + (d > 0 ? d * noise1(tt + SEED_DRIFT_X) : 0);
      sy.target = this.#targetY + (d > 0 ? d * noise1(tt + SEED_DRIFT_Y) : 0);
      sx.update(dt);
      sy.update(dt);
    }

    const s = this.#state;
    const px = sx.value;
    const py = sy.value;
    s.x = px > 1 ? 1 : px < -1 ? -1 : px;
    s.y = py > 1 ? 1 : py < -1 ? -1 : py;
    s.shakeX = qx / PX_Q;
    s.shakeY = qy / PX_Q;
    s.roll = (qr / DEG_Q) / RAD_TO_DEG;

    this.#apply(qx, qy, qr);
  }

  /** Reused object (never reallocated): {x, y} parallax -1..1, {shakeX, shakeY} CSS px, roll rad. */
  get state() {
    return this.#state;
  }

  /** Current trauma, 0..1 (read-only; for debugging and tuning). */
  get trauma() {
    return this.#trauma;
  }

  /** Clears trauma and the DOM transform (e.g. before a cutscene). Parallax keeps easing. */
  reset() {
    this.#trauma = 0;
    const s = this.#state;
    s.shakeX = s.shakeY = s.roll = 0;
    this.#apply(0, 0, 0);
  }

  /** Releases the root: removes any transform this camera wrote. */
  dispose() {
    this.reset();
    this.#root = null;
    this.#om = null;
  }

  // ── internals ──────────────────────────────────────────────────────────

  #apply(qx, qy, qr) {
    const root = this.#root;
    if (!root) return;
    if (qx === 0 && qy === 0 && qr === 0) {
      if (this.#applied) {
        root.style.transform = '';
        this.#applied = false;
      }
      return;
    }
    if (this.#applied && qx === this.#qx && qy === this.#qy && qr === this.#qr) return;
    this.#qx = qx;
    this.#qy = qy;
    this.#qr = qr;
    this.#applied = true;

    const om = this.#om;
    if (om) {
      om.x.value = qx / PX_Q;
      om.y.value = qy / PX_Q;
      om.r.value = qr / DEG_Q;
      try {
        root.attributeStyleMap.set('transform', om.value);
        return;
      } catch {
        this.#om = null; // engine refused the typed value: use strings from now on
      }
    }
    root.style.transform = `translate3d(${qx / PX_Q}px, ${qy / PX_Q}px, 0px) rotate(${qr / DEG_Q}deg)`;
  }

  #buildTypedOM() {
    const root = this.#root;
    try {
      if (
        !root ||
        !root.attributeStyleMap ||
        typeof CSS === 'undefined' ||
        typeof CSS.px !== 'function' ||
        typeof CSSTransformValue !== 'function' ||
        typeof CSSTranslate !== 'function' ||
        typeof CSSRotate !== 'function'
      ) {
        return null;
      }
      const x = CSS.px(0);
      const y = CSS.px(0);
      const r = CSS.deg(0);
      const value = new CSSTransformValue([new CSSTranslate(x, y, CSS.px(0)), new CSSRotate(r)]);
      return { x, y, r, value };
    } catch {
      return null;
    }
  }
}
