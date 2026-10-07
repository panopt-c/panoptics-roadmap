/** Small, allocation-free math kit for animation and game feel. */

export const clamp = (x, lo = 0, hi = 1) => (x < lo ? lo : x > hi ? hi : x);
export const lerp = (a, b, t) => a + (b - a) * t;
export const invLerp = (a, b, x) => (b === a ? 0 : (x - a) / (b - a));
export const smoothstep = (a, b, x) => {
  const t = clamp(invLerp(a, b, x));
  return t * t * (3 - 2 * t);
};

/**
 * Frame-rate independent exponential smoothing toward a target.
 * `lambda` is the decay rate (higher = snappier); identical feel at 30 or 240 fps.
 */
export const damp = (current, target, lambda, dt) => lerp(current, target, 1 - Math.exp(-lambda * dt));

// ── easings (t in 0..1) ──────────────────────────────────────
export const easeOutCubic = (t) => 1 - (1 - t) ** 3;
export const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
export const easeOutExpo = (t) => (t >= 1 ? 1 : 1 - 2 ** (-10 * t));
export const easeOutBack = (t, s = 1.70158) => 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2;
export const easeOutElastic = (t) => {
  if (t === 0 || t === 1) return t;
  return 2 ** (-10 * t) * Math.sin((t * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1;
};

/**
 * Critically damped spring, integrated analytically (exact at any dt, never overshoots,
 * never explodes on a frame hitch). `omega` is the angular frequency: higher = tighter.
 */
export class Spring {
  constructor(value = 0, omega = 10) {
    this.value = value;
    this.target = value;
    this.velocity = 0;
    this.omega = omega;
  }

  update(dt) {
    const w = this.omega;
    const x = this.value - this.target;
    const decay = Math.exp(-w * dt);
    const c = (this.velocity + w * x) * dt;
    this.value = this.target + (x + c) * decay;
    this.velocity = (this.velocity - w * c) * decay;
    return this.value;
  }

  snap(value) {
    this.value = this.target = value;
    this.velocity = 0;
  }
}

// ── deterministic 1-D gradient noise ─────────────────────────
const GRADIENTS = new Float32Array(256);
{
  let seed = 1337;
  for (let i = 0; i < 256; i++) {
    seed = (seed * 16807) % 2147483647;
    GRADIENTS[i] = (seed / 2147483647) * 2 - 1;
  }
}

/** Smooth 1-D gradient noise, roughly in [-1, 1]. Ideal for camera shake. */
export function noise1(x) {
  const i = Math.floor(x);
  const f = x - i;
  const u = f * f * f * (f * (f * 6 - 15) + 10); // quintic fade
  const a = GRADIENTS[i & 255] * f;
  const b = GRADIENTS[(i + 1) & 255] * (f - 1);
  return (a + (b - a) * u) * 2;
}

export const rand = (a = 0, b = 1) => a + Math.random() * (b - a);
export const randInt = (a, b) => Math.floor(rand(a, b + 1));

/** '#rrggbb' → [r, g, b] in 0..1 */
export function hexToRgb(hex) {
  const n = parseInt(hex.replace('#', ''), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}
