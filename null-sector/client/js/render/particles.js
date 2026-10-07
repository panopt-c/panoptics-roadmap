/**
 * particles.js — the GPU particle system behind every burst of juice in NULL//SECTOR.
 *
 * Simulation (CPU, fixed step)
 *   A struct-of-arrays pool of typed arrays, sized once (default capacity 12 000). Live
 *   particles occupy [0, count); a death swap-removes the last live particle into the
 *   hole, so the live range stays dense and nothing ever iterates dead slots. Integration
 *   is semi-implicit Euler with implicit drag (v /= 1 + drag·dt: stable at any dt), and
 *   the previous position is kept so the vertex shader can interpolate by frame.alpha.
 *   Behaviours: gravity, drag, spin; homing (a short ballistic launch, then steering and
 *   cruise speed ease in so bits swing round and strike the target, dying on arrival);
 *   flutter (a paper-like sway driven by a per-particle phasor, so the hot loop does no
 *   trig; confetti also falls slower while it lies flat to the viewer); hold (a particle
 *   hangs in place, shimmering, until released — glyph disintegration).
 *
 * Rendering (GPU, one instanced draw call, additive into the bound HDR target)
 *   A unit quad (triangle strip) instanced over one interleaved instance buffer of 52 bytes
 *   per particle. Only the live range is uploaded, with bufferSubData, into a ring of three
 *   buffers (one VAO each) so the CPU never overwrites a buffer an in-flight frame may
 *   still read; when nothing changed since the last upload (hit-stop, paused sim) the upload
 *   is skipped. The vertex shader interpolates prev→cur by alpha (and rotation by spin),
 *   orients and sizes the quad per shape, applies the life envelope and colour-over-life,
 *   and converts CSS px to clip space. The fragment shader draws each shape analytically
 *   in linear HDR (SDFs, fwidth AA), so it is crisp at any DPR:
 *     streak   — velocity-stretched capsule, white-hot core, tapered tail (spark/stream)
 *     disc     — soft glow around a hot core, optional twinkle (embers/dust/flash)
 *     shard    — tumbling SDF triangle, hot rim, glints as its face turns to camera (shatter)
 *     confetti — two-sided fluttering rectangle with a specular sheen (rank-up)
 *     bit      — crisp glowing data pixel (glyph disintegration)
 *   Particles thinner than a device pixel are widened and dimmed by the same ratio, so tiny
 *   sparks keep their energy without shimmering.
 *
 * Colours are given like CSS: sRGB-encoded [r, g, b] in 0..1 (e.g. math.js hexToRgb('#ff3355'))
 * and linearised on emit, so a particle at intensity ~1 lands on its hex after ACES. Brightness
 * above 1 comes from the per-particle intensity, which is what lets bloom catch the hot ones;
 * a colour with components > 1 is normalised and the excess folded into intensity.
 *
 * Zero allocations after construction: presets are static tables, spawning writes straight
 * into the pool (emit parameters live in one reused object), `opts` objects are only read,
 * uniform locations are cached. Measured: ~0.6 ms CPU per 60 Hz frame at 12 000 live
 * particles (two sim steps + pack), and no JS heap allocation in update/render.
 *
 * Integration extra (optional, backward compatible): set `particles.camera = camera` (or pass
 * `{camera}` to the constructor). Emit coordinates measured with getBoundingClientRect()
 * already include the #ui shake transform, and the post pass shakes the GL composite again;
 * with a camera attached, emit positions and targets are mapped back through the inverse
 * shake so effects stay glued to their DOM anchors even when emitted mid-shake.
 */
import { createProgram, uniforms } from './gl.js';

const TAU = Math.PI * 2;

/** Shape ids shared by the CPU (flags) and the shaders. */
export const SHAPE = Object.freeze({ STREAK: 0, DISC: 1, SHARD: 2, CONFETTI: 3, BIT: 4 });

const STRIDE = 13; // 4-byte words per instance
const BYTES = STRIDE * 4;
const RING = 3; // instance buffers in flight
const SPIN_RANGE = 64; // rad/s represented by snorm16 ±1
const FLIP_RATE = 1.618; // tumble phase per radian of rotation (must match the shaders)
const SEED_PHASE = TAU / 256; // seed byte → phase (must match the shaders)
const FLAG_LIFT = 1; // flat-to-viewer confetti catches air
const FLUTTER_RATE = 6.5; // sway angular frequency, rad/s
const HOMING_DELAY = 0.04; // s of free flight before homing engages
const HOMING_RAMP = 0.14; // s for homing to reach full strength
const EMPTY = Object.freeze({});

const LITTLE_ENDIAN = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;
const packBytes = (a, b, c, d) =>
  LITTLE_ENDIAN ? (a | (b << 8) | (c << 16) | (d << 24)) >>> 0 : ((a << 24) | (b << 16) | (c << 8) | d) >>> 0;
const packShorts = (s0, s1) =>
  LITTLE_ENDIAN ? ((s0 & 0xffff) | ((s1 & 0xffff) << 16)) >>> 0 : (((s0 & 0xffff) << 16) | (s1 & 0xffff)) >>> 0;
const unorm8 = (v) => (v <= 0 ? 0 : v >= 1 ? 255 : (v * 255 + 0.5) | 0);
const snorm16 = (v) => (v <= -1 ? -32767 : v >= 1 ? 32767 : Math.round(v * 32767));
const rnd = (a, b) => a + Math.random() * (b - a);

// sin/cos of each seed's phase, so spawning does no trig per particle.
const SEED_SIN = new Float32Array(256);
const SEED_COS = new Float32Array(256);
for (let k = 0; k < 256; k++) {
  SEED_SIN[k] = Math.sin(k * SEED_PHASE);
  SEED_COS[k] = Math.cos(k * SEED_PHASE);
}

/** Fast sine: parabola + one refinement, |error| < 0.0011. Only drives an aesthetic effect. */
function fastSin(x) {
  let t = x * (1 / TAU);
  t -= Math.floor(t + 0.5); // wrap to [-0.5, 0.5) turns
  const y = 8 * t - 16 * t * (t < 0 ? -t : t);
  return 0.225 * (y * (y < 0 ? -y : y) - y) + y;
}

// ── palette (art bible §6) ───────────────────────────────────────────────────
const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
/** '#rrggbb' → sRGB [r, g, b] 0..1 (the form callers pass in `opts.color`). */
const srgb = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
};
/** '#rrggbb' → linear [r, g, b] (for per-particle palette picks and tints, mixed in light). */
const lin = (hex) => srgb(hex).map(toLinear);

const CYAN = srgb('#00f0ff');
const MAGENTA = srgb('#ff2bd6');
const AMBER = srgb('#ffb000');
const BLOOD = srgb('#ff3355');
const ICE = srgb('#a8d4ff'); // cold mote light
const AMBER_LIN = lin('#ffb000');
const CONFETTI_PALETTE = ['#00f0ff', '#ff2bd6', '#39ff14', '#ffb000', '#ffe55c', '#9c5cff'].map(lin);

// ── presets ──────────────────────────────────────────────────────────────────
// A preset is a list of layers; each layer is a homogeneous population. All ranges are
// [min, max]. Units: px, s, px/s, px/s², rad, rad/s. `bias` > 1 skews speed toward min
// (most debris slow, a few fast — reads as energetic without looking uniform).

function layer(o) {
  const spread = o.spread ?? TAU;
  return {
    shape: SHAPE.STREAK,
    count: 10,
    speed: [100, 300],
    bias: 1,
    angle: 0, // centre direction when the caller gives none (0 → right, −π/2 → up)
    spread, // full cone width
    dirSpread: spread >= TAU ? 1.25 : spread, // cone used when the caller passes `angle`
    ring: false, // evenly spaced angles (shockwave)
    arc: null, // [min, max] launch offset from the target direction (homing arcs)
    radius: 0, // spawn jitter radius
    life: [0.5, 1],
    size: [2, 3],
    sizeEnd: 0.4, // end size as a fraction of start (ease-out over life)
    intensity: [1, 2],
    heat: 0, // white-hot at birth, cooling to colour over the first ~40% of life
    drag: 0,
    gravity: 0,
    lift: 0, // added to initial vy (negative pops debris upward)
    spin: [0, 0], // magnitude range, random sign
    randomRot: false,
    stretch: 0, // streak length = speed × stretch (s), grown from 0 since birth
    homing: 0, // steering rate toward (tx, ty) once locked on, 1/s
    cruise: [0, 0], // homing speed
    flutter: 0, // sway acceleration amplitude, px/s²
    fadeIn: 0, // fraction of life
    fadeOut: 0.5, // fade-out starts at this fraction of life
    flicker: 0, // disc twinkle depth 0..1
    fixed: false, // spawn exactly `count` regardless of opts.count / density (punctuation)
    tint: null, // mix the (linear) emit colour toward this…
    tintMix: 0, // …by this much
    palette: null, // per-particle random colour from this list…
    paletteMix: 1, // …for this fraction of particles (the rest use the emit colour)
    jitter: 0.06, // per-channel colour variation
    ...o,
    spread,
  };
}

function preset(color, layers) {
  let total = 0;
  let maxSpeed = 0;
  for (const l of layers) {
    if (!l.fixed) total += l.count;
    maxSpeed = Math.max(maxSpeed, l.speed[1]);
  }
  return { color, layers, total, maxSpeed };
}

const PRESETS = {
  // Hot streaks that pop out fast, bleed speed to heavy drag and arc down; a white impact pop.
  spark: preset(CYAN, [
    layer({ count: 24, speed: [320, 1250], bias: 1.6, life: [0.22, 0.5], size: [2.6, 3.8], sizeEnd: 0.35,
      intensity: [5, 9], heat: 1, drag: 5.5, gravity: 1400, stretch: 0.032, radius: 3, fadeOut: 0.3 }),
    layer({ shape: SHAPE.DISC, count: 5, speed: [60, 320], life: [0.12, 0.22], size: [3, 5], sizeEnd: 0.3,
      intensity: [4, 6], heat: 1, drag: 8, fadeOut: 0.15 }),
    layer({ shape: SHAPE.DISC, count: 1, fixed: true, speed: [0, 0], life: [0.08, 0.11], size: [14, 18],
      sizeEnd: 1.6, intensity: [5, 6], heat: 1, fadeOut: 0, jitter: 0 }),
  ]),

  // Chunky tumbling shards with weight and a fizz of fine sparks.
  shatter: preset(CYAN, [
    layer({ shape: SHAPE.SHARD, count: 12, speed: [160, 540], bias: 1.3, life: [0.8, 1.35], size: [11, 22],
      sizeEnd: 0.7, intensity: [1.6, 2.4], heat: 0.3, drag: 1.1, gravity: 1700, lift: -280,
      spin: [4, 14], randomRot: true, radius: 6, fadeOut: 0.7 }),
    layer({ count: 14, speed: [300, 1100], bias: 1.4, life: [0.2, 0.42], size: [2, 3], sizeEnd: 0.3,
      intensity: [5, 8], heat: 1, drag: 5, gravity: 1100, stretch: 0.03, radius: 4, fadeOut: 0.3 }),
    layer({ shape: SHAPE.DISC, count: 1, fixed: true, speed: [0, 0], life: [0.08, 0.1], size: [18, 22],
      sizeEnd: 1.5, intensity: [3.5, 4.5], heat: 1, fadeOut: 0, jitter: 0 }),
  ]),

  // Data bits that fan out sideways, lock on and strike (tx, ty).
  stream: preset(CYAN, [
    layer({ count: 22, speed: [420, 1100], arc: [0.55, 1.6], life: [0.7, 1.0], size: [2.4, 3.4], sizeEnd: 0.7,
      intensity: [4.5, 7], heat: 0.6, homing: 17, cruise: [2300, 3400], stretch: 0.024, radius: 7,
      fadeOut: 0.8 }),
    layer({ shape: SHAPE.DISC, count: 6, speed: [240, 600], arc: [0.3, 1.2], life: [0.7, 1.0], size: [3.2, 4.6],
      sizeEnd: 0.6, intensity: [3.5, 5], heat: 0.5, homing: 15, cruise: [1800, 2400], radius: 5, fadeOut: 0.8 }),
  ]),

  // A boss dies: a brief white-hot core, a shockwave ring, radial streaks, shards, rising embers.
  explosion: preset(BLOOD, [
    layer({ shape: SHAPE.DISC, count: 2, fixed: true, speed: [0, 20], life: [0.13, 0.2], size: [44, 60],
      sizeEnd: 2.2, intensity: [3, 4], heat: 1, fadeOut: 0, jitter: 0 }),
    layer({ count: 44, ring: true, speed: [1300, 1450], life: [0.3, 0.42], size: [3.2, 4.2], sizeEnd: 0.4,
      intensity: [6, 9], heat: 1, drag: 3, stretch: 0.034, radius: 4, fadeOut: 0.2 }),
    layer({ count: 100, speed: [260, 1700], bias: 1.8, life: [0.4, 0.95], size: [2.4, 3.6], sizeEnd: 0.3,
      intensity: [5, 8], heat: 1, drag: 3.6, gravity: 900, stretch: 0.03, radius: 8, fadeOut: 0.3 }),
    layer({ shape: SHAPE.SHARD, count: 16, speed: [220, 820], bias: 1.3, life: [0.85, 1.4], size: [10, 20],
      sizeEnd: 0.7, intensity: [1.6, 2.4], heat: 0.4, drag: 1.2, gravity: 1400, lift: -220, spin: [5, 15],
      randomRot: true, radius: 10, fadeOut: 0.7 }),
    layer({ shape: SHAPE.DISC, count: 56, speed: [40, 480], bias: 1.5, life: [1.1, 1.6], size: [3, 5],
      sizeEnd: 0.35, intensity: [3, 5], heat: 0.7, drag: 1.8, gravity: -170, flutter: 620, flicker: 0.6,
      radius: 16, fadeOut: 0.5, tint: AMBER_LIN, tintMix: 0.45 }),
  ]),

  // Rank-up: a burst of two-sided fluttering paper, twinkling glitter and a sparkle of streaks.
  confetti: preset(MAGENTA, [
    layer({ shape: SHAPE.CONFETTI, count: 130, angle: -Math.PI / 2, spread: 2.5, speed: [800, 2100], bias: 1.3,
      life: [1.3, 1.6], size: [11, 16], sizeEnd: 0.9, intensity: [0.9, 1.35], drag: 3.4, gravity: 1100,
      spin: [5, 13], randomRot: true, flutter: 1700, radius: 12, fadeOut: 0.8,
      palette: CONFETTI_PALETTE, paletteMix: 0.7, jitter: 0.04 }),
    layer({ shape: SHAPE.DISC, count: 28, angle: -Math.PI / 2, spread: 2.6, speed: [200, 1300], life: [0.9, 1.6],
      size: [1.8, 2.8], sizeEnd: 0.4, intensity: [4, 7], heat: 0.6, drag: 3, gravity: 380, flicker: 0.9,
      radius: 12, fadeOut: 0.55, palette: CONFETTI_PALETTE, paletteMix: 0.5 }),
    layer({ count: 20, angle: -Math.PI / 2, spread: 2.6, speed: [600, 1500], life: [0.3, 0.55], size: [2.4, 3.2],
      sizeEnd: 0.3, intensity: [5, 8], heat: 1, drag: 4.5, gravity: 1000, stretch: 0.03, radius: 8, fadeOut: 0.3 }),
  ]),

  // Slow rising cinders that sway and twinkle.
  embers: preset(AMBER, [
    layer({ shape: SHAPE.DISC, count: 16, angle: -Math.PI / 2, spread: 2.4, speed: [20, 120], life: [1.0, 1.6],
      size: [2, 3.8], sizeEnd: 0.2, intensity: [2, 3.6], heat: 0.5, drag: 0.9, gravity: -110, flutter: 340,
      flicker: 0.7, radius: 18, fadeIn: 0.08, fadeOut: 0.4 }),
  ]),

  // Ambient motes: dim, slow, long fade in/out. `opts.count` per call.
  dust: preset(ICE, [
    layer({ shape: SHAPE.DISC, count: 6, speed: [4, 26], life: [1.3, 1.6], size: [1.2, 2.6], sizeEnd: 1,
      intensity: [0.35, 0.9], drag: 0.3, gravity: 8, flutter: 40, flicker: 0.3, radius: 80,
      fadeIn: 0.35, fadeOut: 0.55, jitter: 0.1 }),
  ]),
};

// ── shaders ──────────────────────────────────────────────────────────────────

const VS = `#version 300 es
precision highp float;
precision highp int;

layout(location = 0) in vec2 aCorner;   // unit quad, -1..1
layout(location = 1) in vec4 aPos;      // previous xy, current xy (CSS px)
layout(location = 2) in vec2 aTrail;    // streak trail vector (CSS px, points along motion)
layout(location = 3) in vec4 aParam;    // size (px), rotation (rad), life t (< 0: holding, -seconds), intensity
layout(location = 4) in vec4 aColor;    // linear rgb, heat
layout(location = 5) in uvec4 aMeta;    // shape, seed, fade-in, fade-out start (bytes)
layout(location = 6) in vec2 aExt;      // spin / SPIN_RANGE, flicker

uniform vec4 uView;   // CSS width, CSS height, alpha, sim step (s)
uniform vec2 uMisc;   // device px per CSS px, time (s)

out vec2 vLocal;          // fragment position in the particle's own frame (CSS px)
flat out vec4 vBox;       // per-shape extents
flat out vec4 vTri;       // shard vertices 0 and 1
flat out vec4 vColor;     // HDR colour (rgb), heat now (a)
flat out int vShape;

const float SPIN_RANGE = ${SPIN_RANGE.toFixed(1)};
const float FLIP_RATE = ${FLIP_RATE};
const float SEED_PHASE = ${SEED_PHASE};

float hash11(float n) { return fract(sin(n * 12.9898 + 78.233) * 43758.5453); }
vec2 rotate(vec2 v, float a) { float c = cos(a), s = sin(a); return vec2(c * v.x - s * v.y, s * v.x + c * v.y); }

void main() {
  int shape = int(aMeta.x);
  float seed = float(aMeta.y);
  float alpha = uView.z;
  vec2 pos = mix(aPos.xy, aPos.zw, alpha);
  float rot = aParam.y - aExt.x * SPIN_RANGE * uView.w * (1.0 - alpha);
  float size = aParam.x;
  float onePx = 1.0 / max(uMisc.x, 0.25);  // one device pixel, in CSS px
  float rawT = aParam.z;
  float t = max(rawT, 0.0);

  // Life envelope and colour-over-life.
  float fadeIn = float(aMeta.z) * (1.0 / 255.0);
  float fadeOut = float(aMeta.w) * (1.0 / 255.0);
  float env = (fadeIn > 0.0 ? smoothstep(0.0, fadeIn, t) : 1.0) * (1.0 - smoothstep(fadeOut, 1.0, t));
  float cool = 1.0 - t;
  float heat = aColor.a * cool * cool * cool;
  if (rawT < 0.0) {
    // Holding: shimmer like unstable data, then flash hot just before release.
    float wait = -rawT;
    float pop = 1.0 - smoothstep(0.0, 0.08, wait);
    env = 0.8 + 0.2 * sin(uMisc.y * 47.0 + seed * 1.7) + 1.6 * pop;
    heat = max(aColor.a, 0.35) * pop;
  }
  float energy = aParam.w * env;

  vec2 local;
  vec2 world;
  vBox = vec4(0.0);
  vTri = vec4(0.0);

  if (shape == 0) {
    // Streak: capsule from tail to head; the head sits on the particle.
    float len = min(length(aTrail), 180.0);
    vec2 dir = len > 0.01 ? aTrail / len : vec2(1.0, 0.0);
    vec2 nrm = vec2(-dir.y, dir.x);
    float r = 0.5 * size;
    float rc = max(r, 0.6 * onePx);
    energy *= r / rc;
    energy *= mix(1.0, (2.0 * rc + 2.0) / (2.0 * rc + 2.0 + len), 0.45); // trail spreads the light
    float halfSeg = 0.5 * len;
    float pad = rc * 3.0;
    local = aCorner * vec2(halfSeg + pad, pad);
    world = pos - dir * halfSeg + dir * local.x + nrm * local.y;
    vBox = vec4(halfSeg, rc, 0.0, 0.0);
  } else if (shape == 1) {
    // Disc: soft glow, optional twinkle.
    float r = 0.5 * size;
    float rc = max(r, 0.6 * onePx);
    energy *= (r * r) / (rc * rc);
    float fl = aExt.y;
    if (fl > 0.0) energy *= 1.0 - fl * (0.5 + 0.5 * sin(uMisc.y * (7.0 + mod(seed, 9.0)) + seed));
    local = aCorner * (rc * 3.0);
    world = pos + local;
    vBox = vec4(rc, 0.0, 0.0, 0.0);
  } else if (shape == 2) {
    // Shard: an irregular triangle that tumbles (x squashes with the flip phase).
    float R = 0.5 * size;
    float flip = cos(rot * FLIP_RATE + seed * SEED_PHASE);
    float fx = max(abs(flip), 0.14);
    float a0 = (hash11(seed) - 0.5) * 0.9;
    float a1 = 2.094 + (hash11(seed + 17.0) - 0.5) * 0.9;
    float a2 = 4.189 + (hash11(seed + 41.0) - 0.5) * 0.9;
    vec2 v0 = vec2(cos(a0), sin(a0)) * R * (0.75 + 0.25 * hash11(seed + 3.0));
    vec2 v1 = vec2(cos(a1), sin(a1)) * R * (0.65 + 0.35 * hash11(seed + 5.0));
    vec2 v2 = vec2(cos(a2), sin(a2)) * R * (0.55 + 0.45 * hash11(seed + 7.0));
    float m = 3.0 + 0.25 * R;
    local = aCorner * vec2(R * fx + m, R + m);
    world = pos + rotate(local, rot);
    vBox = vec4(fx, R, v2);
    vTri = vec4(v0, v1);
    // Light catches the face as it turns toward the camera.
    float glint = pow(abs(flip), 10.0);
    energy *= 0.55 + 0.45 * abs(flip) + 1.4 * glint;
    heat = max(heat, 0.65 * glint);
  } else if (shape == 3) {
    // Confetti: a two-sided rectangle; its width follows the flip.
    float flip = cos(rot * FLIP_RATE + seed * SEED_PHASE);
    vec2 h = vec2(0.5 * size * max(abs(flip), 0.06), 0.28 * size);
    local = aCorner * (h + 1.5);
    world = pos + rotate(local, rot);
    float sheen = pow(abs(flip), 12.0);
    vBox = vec4(h, flip >= 0.0 ? 1.0 : 0.0, sheen);
  } else {
    // Bit: a crisp square data pixel.
    float hs = max(0.5 * size, 0.6 * onePx);
    float m = 1.5 + hs * 1.2;
    local = aCorner * (hs + m);
    world = pos + rotate(local, rot);
    vBox = vec4(hs, m, 0.0, 0.0);
  }

  vLocal = local;
  vShape = shape;
  vColor = vec4(aColor.rgb * energy, heat);
  vec2 clip = world / uView.xy * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
}
`;

const FS = `#version 300 es
precision highp float;

in vec2 vLocal;
flat in vec4 vBox;
flat in vec4 vTri;
flat in vec4 vColor;
flat in int vShape;
out vec4 outColor;

float peak(vec3 c) { return max(c.r, max(c.g, c.b)); }

// Gaussian lobe that reaches exactly zero at d2 = 9 (the quad edge), so no square halos.
float lobe(float d2, float k) {
  float e = exp(-9.0 * k);
  return max(exp(-k * d2) - e, 0.0) / (1.0 - e);
}

float sdBox(vec2 p, vec2 b) {
  vec2 d = abs(p) - b;
  return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
}

// Inigo Quilez, exact signed distance to a triangle.
float sdTriangle(vec2 p, vec2 p0, vec2 p1, vec2 p2) {
  vec2 e0 = p1 - p0, e1 = p2 - p1, e2 = p0 - p2;
  vec2 v0 = p - p0, v1 = p - p1, v2 = p - p2;
  vec2 pq0 = v0 - e0 * clamp(dot(v0, e0) / dot(e0, e0), 0.0, 1.0);
  vec2 pq1 = v1 - e1 * clamp(dot(v1, e1) / dot(e1, e1), 0.0, 1.0);
  vec2 pq2 = v2 - e2 * clamp(dot(v2, e2) / dot(e2, e2), 0.0, 1.0);
  float s = sign(e0.x * e2.y - e0.y * e2.x);
  vec2 d = min(min(vec2(dot(pq0, pq0), s * (v0.x * e0.y - v0.y * e0.x)),
                   vec2(dot(pq1, pq1), s * (v1.x * e1.y - v1.y * e1.x))),
                   vec2(dot(pq2, pq2), s * (v2.x * e2.y - v2.y * e2.x)));
  return -sqrt(d.x) * sign(d.y);
}

void main() {
  vec3 c = vColor.rgb;
  float heat = vColor.a;
  vec3 white = vec3(peak(c));
  vec3 col;

  if (vShape == 0) {
    float halfSeg = vBox.x;
    float r = vBox.y;
    vec2 q = vec2(max(abs(vLocal.x) - halfSeg, 0.0), vLocal.y);
    float d2 = dot(q, q) / (r * r);
    float core = exp(-1.8 * d2);
    float halo = lobe(d2, 0.3);
    float head = halfSeg > 0.0 ? clamp(0.5 + 0.5 * vLocal.x / (halfSeg + r), 0.0, 1.0) : 1.0;
    float taper = 0.12 + 0.88 * head * head;
    col = (mix(c, white, 0.4 + 0.6 * heat) * core * 1.15 + c * halo * 0.5) * taper;
  } else if (vShape == 1) {
    float d2 = dot(vLocal, vLocal) / (vBox.x * vBox.x);
    float core = exp(-2.2 * d2);
    float halo = lobe(d2, 0.45);
    col = mix(c, white, 0.15 + 0.75 * heat) * core + c * halo * 0.5;
  } else if (vShape == 2) {
    float R = vBox.y;
    vec2 p = vec2(vLocal.x / vBox.x, vLocal.y);
    float sd = sdTriangle(p, vTri.xy, vTri.zw, vBox.zw);
    float aa = max(fwidth(sd), 1e-3);
    float fill = 1.0 - smoothstep(-aa, aa, sd);
    float rim = exp(-abs(sd) / (0.9 + 0.06 * R));
    float glow = exp(-max(sd, 0.0) / (0.9 + 0.12 * R)) * 0.18;
    float facet = 0.16 + 0.2 * clamp(-p.y / R + 0.5, 0.0, 1.0); // dim glassy body, top lit
    col = c * (fill * facet + glow) + mix(c, white, 0.08 + 0.6 * heat) * rim * 1.1;
  } else if (vShape == 3) {
    float sd = sdBox(vLocal, vBox.xy);
    float aa = max(fwidth(sd), 1e-3);
    float fill = 1.0 - smoothstep(-aa, aa, sd);
    float side = mix(0.5, 1.0, vBox.z);                 // back face is darker
    float edge = exp(-max(sd, 0.0) / 1.2) * 0.12;
    col = (c * side + white * vBox.w * 0.6) * fill + c * edge;
  } else {
    float hs = vBox.x;
    float sd = sdBox(vLocal, vec2(hs));
    float aa = max(fwidth(sd), 1e-3);
    float fill = 1.0 - smoothstep(-aa, aa, sd);
    float glow = exp(-max(sd, 0.0) / (0.6 + 0.5 * hs)) * 0.32;
    col = mix(c, white, 0.08 + 0.8 * heat) * fill + c * glow * (1.0 - fill);
  }

  outColor = vec4(col, 0.0);
}
`;

// ── the system ───────────────────────────────────────────────────────────────

export class Particles {
  /** Optional Camera (see header): emit coordinates are un-shaken through its state. */
  camera = null;

  #gl;
  #ok = false;
  #cap;
  #n = 0;
  #density = 1;
  #program = null;
  #u = null;
  #quad = null;
  #vbos = [];
  #vaos = [];
  #ring = 0;
  #dirty = false;
  #step = 1 / 120;
  #cssW = 0;
  #cssH = 0;
  #warned = new Set();
  #ux = 0; // #unshake() result (avoids returning a tuple)
  #uy = 0;

  // Pool (struct of arrays).
  #px; #py; #x; #y; #vx; #vy;
  #age; #life; #wait;
  #size0; #size1; #inten;
  #drag; #grav; #rot; #spin;
  #tx; #ty; #home; #cruise;
  #flutter; #phase; #stretch; #oscS; #oscC;
  #col; #meta; #ext; #flags;
  #floats; // every Float32 pool array, for swap-remove
  #uints;

  // Upload staging (one interleaved instance array, two views).
  #f32;
  #u32;

  // Spawn scratch: one reused colour + emit parameters (no allocation per emit).
  #rgb = new Float32Array(3);
  #e = { x: 0, y: 0, tx: 0, ty: 0, target: false, angle: 0, hasAngle: false, spread: 0, hasSpread: false,
    speedMul: 1, gain: 1 };

  constructor(gl, { capacity = 12000, camera = null } = {}) {
    this.#gl = gl;
    this.#cap = Math.max(1, capacity | 0);
    this.camera = camera;
    const cap = this.#cap;
    const F = () => new Float32Array(cap);
    this.#px = F(); this.#py = F(); this.#x = F(); this.#y = F(); this.#vx = F(); this.#vy = F();
    this.#age = F(); this.#life = F(); this.#wait = F();
    this.#size0 = F(); this.#size1 = F(); this.#inten = F();
    this.#drag = F(); this.#grav = F(); this.#rot = F(); this.#spin = F();
    this.#tx = F(); this.#ty = F(); this.#home = F(); this.#cruise = F();
    this.#flutter = F(); this.#phase = F(); this.#stretch = F(); this.#oscS = F(); this.#oscC = F();
    this.#col = new Uint32Array(cap);
    this.#meta = new Uint32Array(cap);
    this.#ext = new Uint32Array(cap);
    this.#flags = new Uint8Array(cap);
    this.#floats = [this.#px, this.#py, this.#x, this.#y, this.#vx, this.#vy, this.#age, this.#life, this.#wait,
      this.#size0, this.#size1, this.#inten, this.#drag, this.#grav, this.#rot, this.#spin, this.#tx, this.#ty,
      this.#home, this.#cruise, this.#flutter, this.#phase, this.#stretch, this.#oscS, this.#oscC];
    this.#uints = [this.#col, this.#meta, this.#ext];

    const staging = new ArrayBuffer(cap * BYTES);
    this.#f32 = new Float32Array(staging);
    this.#u32 = new Uint32Array(staging);

    if (gl) {
      try {
        this.#build(gl);
        this.#ok = true;
      } catch (err) {
        console.error('[particles] GPU setup failed; particles disabled', err);
        this.#release(gl);
      }
    }
  }

  /** Live particle count. */
  get count() {
    return this.#n;
  }

  get capacity() {
    return this.#cap;
  }

  /** 0..1 multiplier on spawn counts (quality scaling). */
  setDensity(m) {
    const v = +m;
    this.#density = v > 1 ? 1 : v > 0 ? v : 0;
  }

  /** Kills every particle immediately. */
  clear() {
    this.#n = 0;
    this.#dirty = true;
  }

  /**
   * Spawns a preset burst at (x, y) CSS px.
   * opts: color [r,g,b] sRGB 0..1 · count (total, before density) · tx, ty (stream target) ·
   *       angle (rad, screen space: 0 right, −π/2 up) · spread (cone width, rad) ·
   *       speed (px/s of the fastest particles, or a multiplier when ≤ 10).
   * Returns the number of particles spawned.
   */
  emit(preset, x, y, opts = EMPTY) {
    const p = PRESETS[preset];
    if (!p) {
      this.#warnOnce(`unknown preset "${preset}"`);
      return 0;
    }
    if (!this.#ok || !(this.#density > 0) || !Number.isFinite(x) || !Number.isFinite(y)) return 0;
    const o = opts || EMPTY;
    const e = this.#e;
    this.#unshake(x, y);
    e.x = this.#ux;
    e.y = this.#uy;
    e.target = Number.isFinite(o.tx) && Number.isFinite(o.ty);
    if (e.target) {
      this.#unshake(o.tx, o.ty);
      e.tx = this.#ux;
      e.ty = this.#uy;
    }
    e.hasAngle = Number.isFinite(o.angle);
    e.angle = e.hasAngle ? o.angle : 0;
    e.hasSpread = Number.isFinite(o.spread);
    e.spread = e.hasSpread ? Math.max(0, o.spread) : 0;
    const s = +o.speed;
    e.speedMul = s > 10 ? s / p.maxSpeed : s > 0 ? s : 1;
    e.gain = this.#setColor(o.color, p.color);
    const scale = (Number.isFinite(o.count) && o.count >= 0 ? o.count / p.total : 1) * this.#density;

    const before = this.#n;
    const layers = p.layers;
    for (let k = 0; k < layers.length; k++) {
      const L = layers[k];
      const n = L.fixed ? L.count : Math.floor(L.count * scale + Math.random());
      if (n > 0) this.#emitLayer(L, n);
    }
    if (this.#n !== before) this.#dirty = true;
    return this.#n - before;
  }

  /**
   * One particle per point (Float32Array [x0, y0, x1, y1, …] CSS px) — glyph disintegration.
   * The points hold in place, shimmering like unstable data, then a release front with a
   * ragged edge eats into them from the downwind edge, so freed bits blow clear of what is
   * still intact; each bit flashes hot as it lets go, is carried downwind with a little
   * outward blast and lift, and fades as it drifts. opts: color · size (px; default from the point spacing) · hold (s before the
   * front starts, default 0.1) · sweep (s for the front to cross, default 0.55) ·
   * angle (wind direction, rad; default 0 → blows to the right) · speed (multiplier).
   */
  emitPoints(points, opts = EMPTY) {
    if (!this.#ok || !points || points.length < 2 || !(this.#density > 0)) return 0;
    const o = opts || EMPTY;
    const m = points.length >> 1;
    const gain = this.#setColor(o.color, BLOOD);
    const rgb = this.#rgb;
    const wind = Number.isFinite(o.angle) ? o.angle : 0;
    const wx = Math.cos(wind);
    const wy = Math.sin(wind);

    // Centroid, extent along the wind, and grid spacing (glyph rasters arrive in rows).
    let cx = 0;
    let cy = 0;
    let valid = 0;
    let pmin = Infinity;
    let pmax = -Infinity;
    let spacing = Infinity;
    for (let k = 0; k < m; k++) {
      const px = points[2 * k];
      const py = points[2 * k + 1];
      if (!Number.isFinite(px) || !Number.isFinite(py)) continue;
      valid++;
      cx += px;
      cy += py;
      const proj = px * wx + py * wy;
      if (proj < pmin) pmin = proj;
      if (proj > pmax) pmax = proj;
      if (k > 0 && k < 256) {
        const dx = px - points[2 * k - 2];
        const dy = py - points[2 * k - 1];
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d > 0.5 && d < spacing) spacing = d;
      }
    }
    if (valid === 0) return 0;
    cx /= valid;
    cy /= valid;
    const span = pmax - pmin > 1 ? pmax - pmin : 1;

    const size = Number.isFinite(o.size) && o.size > 0
      ? o.size
      : Number.isFinite(spacing) ? Math.min(6, Math.max(1.6, spacing * 0.92)) : 2.6;
    const hold = Number.isFinite(o.hold) ? Math.max(0, o.hold) : 0.1;
    const sweep = Number.isFinite(o.sweep) ? Math.max(0, o.sweep) : 0.55;
    const speedMul = +o.speed > 0 ? +o.speed : 1;
    const col = packBytes(unorm8(rgb[0]), unorm8(rgb[1]), unorm8(rgb[2]), unorm8(0.6));
    const meta0 = packBytes(SHAPE.BIT, 0, 0, unorm8(0.3)); // seed byte is OR-ed in per particle

    const before = this.#n;
    const density = this.#density;
    let acc = 1 - density * 0.5; // error diffusion → evenly decimated, never clumped
    for (let k = 0; k < m; k++) {
      acc += density;
      if (acc < 1) continue;
      acc -= 1;
      const i = this.#n;
      if (i >= this.#cap) break;
      const sx = points[2 * k];
      const sy = points[2 * k + 1];
      if (!Number.isFinite(sx) || !Number.isFinite(sy)) continue;
      this.#unshake(sx, sy);
      const x = this.#ux;
      const y = this.#uy;
      const u = (pmax - (sx * wx + sy * wy)) / span; // 0 at the downwind edge: it lets go first
      let ox = x - cx;
      let oy = y - cy;
      const od = Math.sqrt(ox * ox + oy * oy);
      if (od > 1e-3) {
        ox /= od;
        oy /= od;
      }
      const carry = (110 + 260 * Math.random() * Math.random()) * speedMul; // a few bits streak away
      const blast = rnd(10, 70) * speedMul;
      const seed = (Math.random() * 256) | 0;

      this.#n = i + 1;
      this.#px[i] = this.#x[i] = x;
      this.#py[i] = this.#y[i] = y;
      this.#vx[i] = wx * carry + ox * blast + rnd(-25, 25);
      this.#vy[i] = wy * carry + oy * blast + rnd(-25, 25) - rnd(30, 100);
      this.#age[i] = 0;
      this.#life[i] = rnd(0.7, 1.3);
      // Ragged front: mostly ordered by position along the wind, a third noise.
      this.#wait[i] = hold + sweep * (0.7 * u + 0.3 * Math.random());
      this.#size0[i] = size;
      this.#size1[i] = size * 0.3;
      this.#inten[i] = rnd(1.15, 1.6) * gain;
      this.#drag[i] = 0.55;
      this.#grav[i] = -80;
      this.#rot[i] = 0;
      this.#spin[i] = rnd(-4, 4);
      this.#home[i] = 0;
      this.#flutter[i] = 320;
      this.#phase[i] = seed * SEED_PHASE;
      this.#oscS[i] = SEED_SIN[seed];
      this.#oscC[i] = SEED_COS[seed];
      this.#stretch[i] = 0;
      this.#col[i] = col;
      this.#meta[i] = (meta0 | packBytes(0, seed, 0, 0)) >>> 0;
      this.#ext[i] = packShorts(snorm16(this.#spin[i] / SPIN_RANGE), 0);
      this.#flags[i] = 0;
    }
    if (this.#n !== before) this.#dirty = true;
    return this.#n - before;
  }

  /** Fixed-step integration. Keeps previous positions for interpolation. */
  update(dt) {
    if (!(dt > 0)) return;
    this.#step = dt;
    let n = this.#n;
    if (n === 0) return;

    const px = this.#px, py = this.#py, X = this.#x, Y = this.#y, VX = this.#vx, VY = this.#vy;
    const age = this.#age, life = this.#life, wait = this.#wait;
    const drag = this.#drag, grav = this.#grav, rot = this.#rot, spin = this.#spin;
    const TX = this.#tx, TY = this.#ty, home = this.#home, cruise = this.#cruise;
    const flutter = this.#flutter, phase = this.#phase, flags = this.#flags, oscS = this.#oscS, oscC = this.#oscC;
    // Flutter sway: each particle carries a unit phasor (sin, cos of its sway phase) that is
    // rotated by one shared step here, instead of a Math.sin per particle per step.
    const cd = Math.cos(FLUTTER_RATE * dt);
    const sd = Math.sin(FLUTTER_RATE * dt);

    let i = 0;
    while (i < n) {
      const w = wait[i];
      if (w > 0) {
        wait[i] = w > dt ? w - dt : 0;
        px[i] = X[i];
        py[i] = Y[i];
        i++;
        continue;
      }
      const a = age[i] + dt;
      const L = life[i];
      if (a >= L) {
        n--;
        if (i !== n) this.#move(n, i);
        continue;
      }
      age[i] = a;

      const x = X[i];
      const y = Y[i];
      let vx = VX[i];
      let vy = VY[i];
      let g = grav[i];
      let k = drag[i];

      const h = home[i];
      if (h > 0) {
        const dx = TX[i] - x;
        const dy = TY[i] - y;
        const d2 = dx * dx + dy * dy;
        const cr = cruise[i];
        const reach = cr * dt + 6;
        if (d2 < reach * reach) {
          n--;
          if (i !== n) this.#move(n, i);
          continue;
        }
        // Ballistic for HOMING_DELAY, then lock on over HOMING_RAMP: steering and cruise
        // speed both ease in, so bits fan out, swing round and accelerate into the target.
        let ramp = (a - HOMING_DELAY) * (1 / HOMING_RAMP);
        ramp = ramp <= 0 ? 0 : ramp >= 1 ? 1 : ramp * ramp * (3 - 2 * ramp);
        if (ramp > 0) {
          let turn = h * ramp * dt;
          if (turn > 1) turn = 1;
          const inv = (cr * (0.45 + 0.55 * ramp)) / Math.sqrt(d2);
          vx += (dx * inv - vx) * turn;
          vy += (dy * inv - vy) * turn;
        }
      }

      const f = flutter[i];
      if (f !== 0) {
        const os = oscS[i], oc = oscC[i];
        vx += os * f * dt;
        oscS[i] = os * cd + oc * sd;
        oscC[i] = oc * cd - os * sd;
        if (flags[i] & FLAG_LIFT) {
          const fc = fastSin(rot[i] * FLIP_RATE + phase[i] + Math.PI / 2);
          const flat = fc < 0 ? -fc : fc;
          g *= 1.2 - 0.85 * flat;
          k *= 0.7 + 0.9 * flat;
        }
      }

      const damp = 1 / (1 + k * dt);
      vx *= damp;
      vy = vy * damp + g * dt;
      VX[i] = vx;
      VY[i] = vy;
      px[i] = x;
      py[i] = y;
      X[i] = x + vx * dt;
      Y[i] = y + vy * dt;
      rot[i] += spin[i] * dt;
      i++;
    }
    this.#n = n;
    this.#dirty = true;
  }

  /** One instanced, additive draw into the currently bound target. */
  render(gl, frame) {
    const cssW = frame && frame.cssWidth > 0 ? frame.cssWidth : 0;
    const cssH = frame && frame.cssHeight > 0 ? frame.cssHeight : 0;
    if (cssW > 0 && cssH > 0) {
      this.#cssW = cssW;
      this.#cssH = cssH;
    }
    const n = this.#n;
    if (!this.#ok || n === 0 || !(cssW > 0 && cssH > 0)) return;
    gl = gl || this.#gl;

    if (this.#dirty) {
      this.#pack(n);
      this.#ring = (this.#ring + 1) % RING;
      gl.bindBuffer(gl.ARRAY_BUFFER, this.#vbos[this.#ring]);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.#f32, 0, n * STRIDE);
      gl.bindBuffer(gl.ARRAY_BUFFER, null);
      this.#dirty = false;
    }

    const u = this.#u;
    const alpha = frame.alpha >= 0 && frame.alpha <= 1 ? frame.alpha : 1;
    const pxPerCss = frame.width > 0 ? frame.width / cssW : frame.dpr > 0 ? frame.dpr : 1;
    gl.useProgram(this.#program);
    gl.uniform4f(u.uView, cssW, cssH, alpha, this.#step);
    gl.uniform2f(u.uMisc, pxPerCss, frame.time || 0);
    gl.bindVertexArray(this.#vaos[this.#ring]);
    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendEquation(gl.FUNC_ADD);
    gl.blendFuncSeparate(gl.ONE, gl.ONE, gl.ZERO, gl.ONE); // additive colour, alpha untouched
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, n);
    gl.disable(gl.BLEND);
    gl.bindVertexArray(null);
  }

  /** Frees GPU objects. The instance is inert afterwards. */
  dispose() {
    if (this.#gl) this.#release(this.#gl);
    this.#ok = false;
    this.#n = 0;
  }

  // ── internals ──────────────────────────────────────────────────────────

  #build(gl) {
    this.#program = createProgram(gl, VS, FS, 'particles');
    this.#u = uniforms(gl, this.#program);

    this.#quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.#quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);

    for (let k = 0; k < RING; k++) {
      const vao = gl.createVertexArray();
      const vbo = gl.createBuffer();
      gl.bindVertexArray(vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.#quad);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 8, 0);

      gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
      gl.bufferData(gl.ARRAY_BUFFER, this.#cap * BYTES, gl.DYNAMIC_DRAW);
      const attr = (loc, size, type, normalized, offset, integer = false) => {
        gl.enableVertexAttribArray(loc);
        if (integer) gl.vertexAttribIPointer(loc, size, type, BYTES, offset);
        else gl.vertexAttribPointer(loc, size, type, normalized, BYTES, offset);
        gl.vertexAttribDivisor(loc, 1);
      };
      attr(1, 4, gl.FLOAT, false, 0); // prev xy, cur xy
      attr(2, 2, gl.FLOAT, false, 16); // trail
      attr(3, 4, gl.FLOAT, false, 24); // size, rot, t, intensity
      attr(4, 4, gl.UNSIGNED_BYTE, true, 40); // rgb, heat
      attr(5, 4, gl.UNSIGNED_BYTE, false, 44, true); // shape, seed, fade-in, fade-out
      attr(6, 2, gl.SHORT, true, 48); // spin, flicker
      this.#vaos.push(vao);
      this.#vbos.push(vbo);
    }
    gl.bindVertexArray(null);
    gl.bindBuffer(gl.ARRAY_BUFFER, null);
  }

  #release(gl) {
    if (!gl.isContextLost || !gl.isContextLost()) {
      for (const vao of this.#vaos) gl.deleteVertexArray(vao);
      for (const vbo of this.#vbos) gl.deleteBuffer(vbo);
      if (this.#quad) gl.deleteBuffer(this.#quad);
      if (this.#program) gl.deleteProgram(this.#program);
    }
    this.#vaos.length = 0;
    this.#vbos.length = 0;
    this.#quad = null;
    this.#program = null;
  }

  /** Writes the live range into the interleaved staging array. */
  #pack(n) {
    const f = this.#f32, u = this.#u32;
    const px = this.#px, py = this.#py, X = this.#x, Y = this.#y, VX = this.#vx, VY = this.#vy;
    const age = this.#age, life = this.#life, wait = this.#wait, stretch = this.#stretch;
    const s0 = this.#size0, s1 = this.#size1, rot = this.#rot, inten = this.#inten;
    const col = this.#col, meta = this.#meta, ext = this.#ext;
    for (let i = 0, o = 0; i < n; i++, o += STRIDE) {
      f[o] = px[i];
      f[o + 1] = py[i];
      f[o + 2] = X[i];
      f[o + 3] = Y[i];
      const a = age[i];
      const st = stretch[i];
      const k = st < a ? st : a; // trails grow from zero: no streak through the emitter at birth
      f[o + 4] = VX[i] * k;
      f[o + 5] = VY[i] * k;
      const w = wait[i];
      let t;
      let size = s0[i];
      if (w > 0) {
        t = -w;
      } else {
        t = a / life[i];
        const e = 1 - t;
        size += (s1[i] - size) * (1 - e * e);
      }
      f[o + 6] = size;
      f[o + 7] = rot[i];
      f[o + 8] = t;
      f[o + 9] = inten[i];
      u[o + 10] = col[i];
      u[o + 11] = meta[i];
      u[o + 12] = ext[i];
    }
  }

  /** Swap-remove: moves particle `from` into slot `to`. */
  #move(from, to) {
    const fl = this.#floats;
    for (let k = 0; k < fl.length; k++) fl[k][to] = fl[k][from];
    const ui = this.#uints;
    for (let k = 0; k < ui.length; k++) ui[k][to] = ui[k][from];
    this.#flags[to] = this.#flags[from];
  }

  /** Resolves the emit colour (sRGB) into linear #rgb and returns the intensity gain for HDR input. */
  #setColor(color, fallback) {
    const rgb = this.#rgb;
    const src = color && color.length >= 3 ? color : fallback;
    let r = +src[0] || 0;
    let g = +src[1] || 0;
    let b = +src[2] || 0;
    if (r < 0) r = 0;
    if (g < 0) g = 0;
    if (b < 0) b = 0;
    const m = Math.max(r, g, b);
    let gain = 1;
    if (m > 1) {
      gain = m;
      r /= m;
      g /= m;
      b /= m;
    }
    rgb[0] = toLinear(r);
    rgb[1] = toLinear(g);
    rgb[2] = toLinear(b);
    return gain;
  }

  /** Maps a shaken viewport point back to layout space (inverse of the #ui transform). */
  #unshake(x, y) {
    const cam = this.camera;
    const s = cam && cam.state;
    if (!s || (s.shakeX === 0 && s.shakeY === 0 && s.roll === 0)) {
      this.#ux = x;
      this.#uy = y;
      return;
    }
    const cx = (this.#cssW || (typeof innerWidth === 'number' ? innerWidth : 0)) * 0.5;
    const cy = (this.#cssH || (typeof innerHeight === 'number' ? innerHeight : 0)) * 0.5;
    const dx = x - cx - (s.shakeX || 0);
    const dy = y - cy - (s.shakeY || 0);
    const c = Math.cos(s.roll || 0);
    const sn = Math.sin(s.roll || 0);
    this.#ux = cx + c * dx + sn * dy;
    this.#uy = cy - sn * dx + c * dy;
  }

  #emitLayer(L, count) {
    const e = this.#e;
    const rgb = this.#rgb;
    const cap = this.#cap;
    const homing = e.target && L.homing > 0;
    const toTarget = e.target ? Math.atan2(e.ty - e.y, e.tx - e.x) : 0;
    const centre = e.hasAngle ? e.angle : L.angle;
    const spread = e.hasSpread ? e.spread : e.hasAngle ? L.dirSpread : L.spread;
    const fadeIn = unorm8(L.fadeIn);
    const fadeOut = unorm8(L.fadeOut);
    const flicker = snorm16(L.flicker);
    const heat = unorm8(L.heat);
    const pal = L.palette;

    for (let j = 0; j < count; j++) {
      const i = this.#n;
      if (i >= cap) return;
      this.#n = i + 1;

      let a;
      if (L.arc && e.target) a = toTarget + (Math.random() < 0.5 ? -1 : 1) * rnd(L.arc[0], L.arc[1]);
      else if (L.ring) a = centre + (spread >= TAU ? TAU : spread) * ((j + Math.random() * 0.35) / count - 0.5);
      else a = centre + (Math.random() - 0.5) * spread;
      const speed = (L.speed[0] + (L.speed[1] - L.speed[0]) * Math.pow(Math.random(), L.bias)) * e.speedMul;
      const ca = Math.cos(a);
      const sa = Math.sin(a);

      let x = e.x;
      let y = e.y;
      if (L.radius > 0) {
        const rr = L.radius * Math.sqrt(Math.random());
        const ra = Math.random() * TAU;
        x += Math.cos(ra) * rr;
        y += Math.sin(ra) * rr;
      }

      // Colour: palette pick or emit colour → tint → per-channel jitter.
      let r = rgb[0];
      let g = rgb[1];
      let b = rgb[2];
      if (pal && Math.random() < L.paletteMix) {
        const pc = pal[(Math.random() * pal.length) | 0];
        r = pc[0];
        g = pc[1];
        b = pc[2];
      }
      if (L.tint) {
        const tm = L.tintMix;
        r += (L.tint[0] - r) * tm;
        g += (L.tint[1] - g) * tm;
        b += (L.tint[2] - b) * tm;
      }
      const jt = L.jitter;
      if (jt > 0) {
        r *= 1 + jt * (Math.random() * 2 - 1);
        g *= 1 + jt * (Math.random() * 2 - 1);
        b *= 1 + jt * (Math.random() * 2 - 1);
      }

      const seed = (Math.random() * 256) | 0;
      const spinMag = L.spin[1] > 0 ? rnd(L.spin[0], L.spin[1]) * (Math.random() < 0.5 ? -1 : 1) : 0;
      const size0 = rnd(L.size[0], L.size[1]);

      this.#px[i] = this.#x[i] = x;
      this.#py[i] = this.#y[i] = y;
      this.#vx[i] = ca * speed;
      this.#vy[i] = sa * speed + L.lift;
      this.#age[i] = 0;
      this.#life[i] = rnd(L.life[0], L.life[1]);
      this.#wait[i] = 0;
      this.#size0[i] = size0;
      this.#size1[i] = size0 * L.sizeEnd;
      this.#inten[i] = rnd(L.intensity[0], L.intensity[1]) * e.gain;
      this.#drag[i] = L.drag;
      this.#grav[i] = L.gravity;
      this.#rot[i] = L.randomRot ? Math.random() * TAU : 0;
      this.#spin[i] = spinMag;
      if (homing) {
        this.#tx[i] = e.tx;
        this.#ty[i] = e.ty;
        this.#home[i] = L.homing;
        this.#cruise[i] = rnd(L.cruise[0], L.cruise[1]) * e.speedMul;
      } else {
        this.#home[i] = 0;
      }
      this.#flutter[i] = L.flutter;
      this.#phase[i] = seed * SEED_PHASE;
      this.#oscS[i] = SEED_SIN[seed];
      this.#oscC[i] = SEED_COS[seed];
      this.#stretch[i] = L.stretch;
      this.#col[i] = packBytes(unorm8(r), unorm8(g), unorm8(b), heat);
      this.#meta[i] = packBytes(L.shape, seed, fadeIn, fadeOut);
      this.#ext[i] = packShorts(snorm16(spinMag / SPIN_RANGE), flicker);
      this.#flags[i] = L.shape === SHAPE.CONFETTI ? FLAG_LIFT : 0;
    }
  }

  #warnOnce(message) {
    if (this.#warned.has(message)) return;
    this.#warned.add(message);
    console.warn(`[particles] ${message}`);
  }
}
