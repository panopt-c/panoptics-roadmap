/**
 * Post — the cinematic camera: HDR scene in, display-ready image out.
 *
 * Bloom (Jimenez, "Next Generation Post Processing in Call of Duty: Advanced Warfare", 2014)
 *   1. Prefilter: 13-tap downsample of the HDR target into mip 0 (½ res). The 13 taps are
 *      grouped into five overlapping 2x2 boxes, each weighted by 1/(1+luma) — the Karis
 *      average — which stops single sub-pixel highlights ("fireflies") from strobing as they
 *      move. A soft-knee threshold then keeps only energy above ~1.0 with a quadratic
 *      toe, so lights ease into bloom instead of popping.
 *   2. Downsample: the same 13-tap filter (no Karis) down a 5-level chain to 1/32 res.
 *   3. Upsample: a 3x3 tent filter walks back up, blended additively into each larger mip,
 *      so every level contributes a progressively wider lobe — a smooth, physically
 *      plausible falloff with no blockiness at any resolution.
 *   An anamorphic streak (horizontal, cool-tinted, very high threshold) is grown from the
 *   ¼-res mip in three widening passes: a subtle 35 mm-lens signature on the hottest neon.
 *
 * Composite (one fullscreen pass to the default framebuffer)
 *   lens barrel (crt > .5) → camera shake/roll (the exact inverse of the #ui transform, so
 *   GL particles stay glued to DOM elements) → radial chromatic aberration → + bloom/streak
 *   → + flash → natural cos⁴ vignette (+ alarm edge glow) → exposure → ACES (Narkowicz fit)
 *   → scanlines on device-pixel rows → exact sRGB encode → luminance-weighted film grain
 *   → TPDF dither (no banding in the dark gradients this game lives in).
 *
 * Everything per-frame is uniforms on cached locations; no allocations, no GL queries.
 * The public knobs below are for art direction and can be tweaked live from the console.
 */
import { createProgram, createTarget, resizeTarget, deleteTarget, drawFullscreen, uniforms, FULLSCREEN_VS } from './gl.js';

const LEVELS = 5;
const TAU = Math.PI * 2;

const HEADER = `#version 300 es
precision highp float;
precision highp int;
in vec2 vUv;
out vec4 outColor;
`;

// 13 taps around vUv in source texels (Jimenez). Shared by prefilter and downsample.
const TAPS = `
uniform sampler2D uSrc;
uniform vec2 uTexel;
uniform float uClamp;
vec3 tap(float x, float y) {
  // Clamp also scrubs Inf/negative values so one bad pixel can't poison the chain.
  return clamp(texture(uSrc, vUv + vec2(x, y) * uTexel).rgb, 0.0, uClamp);
}
#define TAPS13 \\
  vec3 a = tap(-2.0, 2.0), b = tap(0.0, 2.0), c = tap(2.0, 2.0); \\
  vec3 d = tap(-2.0, 0.0), e = tap(0.0, 0.0), f = tap(2.0, 0.0); \\
  vec3 g = tap(-2.0, -2.0), h = tap(0.0, -2.0), i = tap(2.0, -2.0); \\
  vec3 j = tap(-1.0, 1.0), k = tap(1.0, 1.0), l = tap(-1.0, -1.0), m = tap(1.0, -1.0);
`;

const PREFILTER_FS = `${HEADER}${TAPS}
uniform vec4 uCurve; // threshold, threshold - knee, 2 * knee, 0.25 / knee

float karis(vec3 c) { return 1.0 / (1.0 + dot(c, vec3(0.2126, 0.7152, 0.0722))); }

void main() {
  TAPS13
  vec3 b0 = (j + k + l + m) * 0.25;
  vec3 b1 = (a + b + d + e) * 0.25;
  vec3 b2 = (b + c + e + f) * 0.25;
  vec3 b3 = (d + e + g + h) * 0.25;
  vec3 b4 = (e + f + h + i) * 0.25;
  float w0 = 0.5 * karis(b0);
  float w1 = 0.125 * karis(b1);
  float w2 = 0.125 * karis(b2);
  float w3 = 0.125 * karis(b3);
  float w4 = 0.125 * karis(b4);
  vec3 col = (b0 * w0 + b1 * w1 + b2 * w2 + b3 * w3 + b4 * w4) / (w0 + w1 + w2 + w3 + w4);

  // Soft-knee threshold on the brightest channel (keeps saturated neon saturated).
  float br = max(col.r, max(col.g, col.b));
  float rq = clamp(br - uCurve.y, 0.0, uCurve.z);
  rq = uCurve.w * rq * rq;
  col *= max(rq, br - uCurve.x) / max(br, 1e-4);
  outColor = vec4(col, 1.0);
}
`;

const DOWN_FS = `${HEADER}${TAPS}
void main() {
  TAPS13
  vec3 col = e * 0.125 + (a + c + g + i) * 0.03125 + (b + d + f + h) * 0.0625 + (j + k + l + m) * 0.125;
  outColor = vec4(col, 1.0);
}
`;

const UP_FS = `${HEADER}
uniform sampler2D uSrc;
uniform vec2 uTexel;  // source (smaller) mip texel
uniform float uWeight;
void main() {
  vec2 o = uTexel;
  vec3 s = texture(uSrc, vUv).rgb * 4.0;
  s += (texture(uSrc, vUv + vec2(-o.x, 0.0)).rgb + texture(uSrc, vUv + vec2(o.x, 0.0)).rgb +
        texture(uSrc, vUv + vec2(0.0, -o.y)).rgb + texture(uSrc, vUv + vec2(0.0, o.y)).rgb) * 2.0;
  s += texture(uSrc, vUv - o).rgb + texture(uSrc, vUv + o).rgb +
       texture(uSrc, vUv + vec2(o.x, -o.y)).rgb + texture(uSrc, vUv + vec2(-o.x, o.y)).rgb;
  outColor = vec4(s * (uWeight / 16.0), 1.0);
}
`;

// Horizontal 7-tap exponential blur; chained with growing spacing it builds a long streak.
const STREAK_FS = `${HEADER}
uniform sampler2D uSrc;
uniform vec2 uTexel;
uniform float uSpacing;
uniform float uThreshold; // > 0 only on the first pass
void main() {
  vec3 acc = vec3(0.0);
  float wsum = 0.0;
  for (int n = -3; n <= 3; n++) {
    float fn = float(n);
    float w = exp2(-abs(fn) * 0.85);
    vec3 c = texture(uSrc, vUv + vec2(fn * uSpacing * uTexel.x, 0.0)).rgb;
    if (uThreshold > 0.0) {
      float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
      c *= max(l - uThreshold, 0.0) / max(l, 1e-4);
    }
    acc += c * w;
    wsum += w;
  }
  outColor = vec4(acc / wsum, 1.0);
}
`;

const COMPOSITE_FS = `${HEADER}
uniform sampler2D uScene;
uniform sampler2D uBloom;
uniform sampler2D uStreak;
uniform vec4 uView;        // css width, css height, aspect, unused
uniform vec4 uShake;       // shake x, y (CSS px, +y down), cos(roll), sin(roll)
uniform float uBarrel;
uniform float uCA;
uniform float uBloomStrength;
uniform float uStreakStrength;
uniform vec3 uStreakTint;
uniform vec3 uFlash;       // linear HDR, already scaled by amount
uniform float uVignetteK;  // natural vignette: 1 / (1 + k r^2)^2
uniform vec3 uEdgeGlow;    // additive tint in the vignette zone (alarm pulse)
uniform float uExposure;
uniform vec2 uScan;        // strength, period in device px
uniform float uGrain;
uniform float uGrainCell;  // grain cell size in device px (≈ one CSS px)
uniform uint uSeed;

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);

vec3 aces(vec3 x) {
  // Narkowicz 2015, "ACES Filmic Tone Mapping Curve".
  return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

vec3 encodeSrgb(vec3 c) {
  c = clamp(c, 0.0, 1.0);
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), c));
}

uvec3 pcg3d(uvec3 v) {
  v = v * 1664525u + 1013904223u;
  v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y;
  v ^= v >> 16u;
  v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y;
  return v;
}

void main() {
  vec2 c = vUv - 0.5;

  // Lens: subtle barrel (zero at centre, so DOM-anchored effects stay put where it matters).
  vec2 uv = 0.5 + c * (1.0 + uBarrel * dot(c, c));

  // Camera: inverse of translate(shake) rotate(roll) about the screen centre, in CSS px.
  vec2 p = (uv - 0.5) * uView.xy;
  p.y = -p.y;
  p -= uShake.xy;
  p = vec2(uShake.z * p.x + uShake.w * p.y, -uShake.w * p.x + uShake.z * p.y);
  p.y = -p.y;
  uv = p / uView.xy + 0.5;

  // Radial chromatic aberration, growing with r^2 (clean centre, fringed periphery).
  vec3 hdr;
  vec2 d = uv - 0.5;
  if (uCA > 0.0) {
    vec2 off = d * (dot(d, d) * 2.0 * uCA);
    hdr = vec3(texture(uScene, uv + off).r, texture(uScene, uv).g, texture(uScene, uv - off).b);
  } else {
    hdr = texture(uScene, uv).rgb;
  }

  if (uBloomStrength > 0.0) {
    hdr += texture(uBloom, uv).rgb * uBloomStrength;
    vec3 s = texture(uStreak, uv).rgb;
    hdr += mix(s, vec3(dot(s, LUMA)) * uStreakTint, 0.65) * uStreakStrength;
  }

  hdr += uFlash;

  // Natural (cos^4-like) vignette in aspect-correct space, normalised to the half-diagonal.
  vec2 vc = c * vec2(uView.z, 1.0);
  float r2 = dot(vc, vc) / dot(vec2(uView.z, 1.0) * 0.5, vec2(uView.z, 1.0) * 0.5);
  float fall = 1.0 / (1.0 + uVignetteK * r2);
  fall *= fall;
  hdr = hdr * fall + uEdgeGlow * (1.0 - fall);

  vec3 col = aces(max(hdr, 0.0) * uExposure);

  // Scanlines locked to device-pixel rows; zero-mean so overall brightness is unchanged.
  float phase = mod(floor(gl_FragCoord.y), uScan.y) / uScan.y;
  col *= 1.0 + uScan.x * cos(6.2831853 * phase);

  vec3 srgb = encodeSrgb(col);

  // Film grain: mono, triangular, strongest in the mid-tones (where film shows it).
  uvec3 h = pcg3d(uvec3(uvec2(gl_FragCoord.xy / uGrainCell), uSeed));
  vec2 n = vec2(h.xy) * (1.0 / 4294967295.0);
  float l = dot(srgb, LUMA);
  srgb += (n.x + n.y - 1.0) * uGrain * (0.3 + 2.8 * l * (1.0 - l));

  // TPDF dither, one 8-bit LSB, so smooth gradients never band.
  float dither = (float(h.z & 0xFFFFu) + float(h.z >> 16u)) * (1.0 / 65535.0) - 1.0;
  outColor = vec4(srgb + dither * (1.0 / 255.0), 1.0);
}
`;

const smooth01 = (a, b, x) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

export class Post {
  // ── art-direction knobs ───────────────────────────────────────────────
  /** Linear exposure applied before ACES. 1.0 → a linear 1.0 lands at ~80% display. */
  exposure = 1.0;
  /** Bloom energy added back to the scene (sum of all five lobes). */
  bloomStrength = 0.28;
  /** Brightest-channel threshold (linear) and knee width of the soft prefilter. */
  threshold = 1.0;
  knee = 0.7;
  /** Per-level weight of the upsample accumulation (1 = pure additive, <1 tighter glow). */
  scatter = 0.85;
  /** Anamorphic streak: amount, extra luminance threshold, tint (linear). */
  streakStrength = 0.09;
  streakThreshold = 1.4;
  streakTint = [0.35, 0.6, 1.0];
  /** Peak CRT looks at settings.crt = 1. */
  vignette = 0.42;
  scanlines = 0.045;
  grain = 0.032;
  aberration = 0.0045;
  barrel = 0.055;

  #gl;
  #mips = [];
  #streakA = null;
  #streakB = null;
  #prefilter;
  #down;
  #up;
  #streak;
  #composite;
  #u = {};
  #w = 1;
  #h = 1;
  #seed = 1;
  #bloomValid = false;

  constructor(gl) {
    this.#gl = gl;
    this.#prefilter = this.#program(PREFILTER_FS, 'post.prefilter');
    this.#down = this.#program(DOWN_FS, 'post.downsample');
    this.#up = this.#program(UP_FS, 'post.upsample');
    this.#streak = this.#program(STREAK_FS, 'post.streak');
    this.#composite = this.#program(COMPOSITE_FS, 'post.composite');

    gl.useProgram(this.#composite.program);
    gl.uniform1i(this.#composite.u.uScene, 0);
    gl.uniform1i(this.#composite.u.uBloom, 1);
    gl.uniform1i(this.#composite.u.uStreak, 2);
    for (const p of [this.#prefilter, this.#down, this.#up, this.#streak]) {
      gl.useProgram(p.program);
      gl.uniform1i(p.u.uSrc, 0);
    }
    gl.useProgram(null);

    for (let i = 0; i < LEVELS; i++) this.#mips.push(createTarget(gl, 1, 1, { hdr: true }));
    this.#streakA = createTarget(gl, 1, 1, { hdr: true });
    this.#streakB = createTarget(gl, 1, 1, { hdr: true });
  }

  /** True when the bloom chain is floating point (false → LDR fallback, lower threshold). */
  get hdr() {
    return this.#mips[0].hdr;
  }

  /** Size of the HDR scene target that will be passed to render(). */
  resize(w, h) {
    w = Math.max(1, Math.round(w));
    h = Math.max(1, Math.round(h));
    if (w === this.#w && h === this.#h) return;
    this.#w = w;
    this.#h = h;
    const gl = this.#gl;
    let mw = w;
    let mh = h;
    for (let i = 0; i < LEVELS; i++) {
      mw = Math.max(1, Math.ceil(mw / 2));
      mh = Math.max(1, Math.ceil(mh / 2));
      resizeTarget(gl, this.#mips[i], mw, mh);
    }
    // Streak buffer: ⅛ width (it is blurred hundreds of px anyway), ¼ height (stays thin).
    resizeTarget(gl, this.#streakA, this.#mips[2].w, this.#mips[1].h);
    resizeTarget(gl, this.#streakB, this.#mips[2].w, this.#mips[1].h);
    this.#bloomValid = false;
  }

  /**
   * @param {WebGL2RenderingContext} gl
   * @param {{fbo, tex, w, h}} hdrTarget  linear HDR scene
   * @param {object} frame  renderer frame state (ARCHITECTURE §4.4)
   * @param {{crt?: number, bloom?: boolean, reducedMotion?: boolean}} settings
   */
  render(gl, hdrTarget, frame, settings) {
    const crt = settings && typeof settings.crt === 'number' ? Math.min(Math.max(settings.crt, 0), 1) : 1;
    const bloomOn = !settings || settings.bloom !== false;
    const reduced = !!(settings && settings.reducedMotion);

    if (hdrTarget.w !== this.#w || hdrTarget.h !== this.#h) this.resize(hdrTarget.w, hdrTarget.h);

    gl.disable(gl.BLEND);
    gl.disable(gl.DEPTH_TEST);
    gl.activeTexture(gl.TEXTURE0);
    if (bloomOn) this.#bloom(gl, hdrTarget);

    // ── composite ──
    const mood = frame.mood;
    const cam = frame.camera;
    const flash = frame.flash;
    const p = this.#composite;
    const u = p.u;

    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, frame.width, frame.height);
    gl.useProgram(p.program);

    gl.activeTexture(gl.TEXTURE2);
    gl.bindTexture(gl.TEXTURE_2D, this.#streakA.tex);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.#mips[0].tex);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, hdrTarget.tex);

    const cssW = frame.cssWidth > 0 ? frame.cssWidth : frame.width;
    const cssH = frame.cssHeight > 0 ? frame.cssHeight : frame.height;
    gl.uniform4f(u.uView, cssW, cssH, cssW / cssH, 0);

    const roll = cam.roll || 0;
    gl.uniform4f(u.uShake, cam.shakeX || 0, cam.shakeY || 0, Math.cos(roll), Math.sin(roll));
    gl.uniform1f(u.uBarrel, this.barrel * smooth01(0.5, 1.0, crt));

    // CA: a lens baseline from the CRT setting, plus impact energy from shake and the alarm.
    const shake = Math.min(1, Math.hypot(cam.shakeX || 0, cam.shakeY || 0) / 14);
    const alarm = mood.alarm;
    gl.uniform1f(u.uCA, crt * (this.aberration * (1 + 0.6 * mood.corruption) + 0.014 * shake + 0.006 * alarm));

    const intensity = mood.intensity;
    const bloomGain = bloomOn && this.#bloomValid ? this.bloomStrength * (0.55 + 0.45 * intensity) : 0;
    gl.uniform1f(u.uBloomStrength, bloomGain);
    gl.uniform1f(u.uStreakStrength, bloomGain > 0 ? this.streakStrength * (0.6 + 0.4 * intensity) : 0);
    const tint = this.streakTint;
    gl.uniform3f(u.uStreakTint, tint[0], tint[1], tint[2]);

    // Flash: additive HDR light with a whiter core at high amounts (reads as a bright burst).
    const fa = flash.amount;
    const fc = flash.color;
    const core = fa * fa * 0.35;
    gl.uniform3f(u.uFlash, fc[0] * fa * 1.6 + core, fc[1] * fa * 1.6 + core, fc[2] * fa * 1.6 + core);

    const vig = Math.min(0.9, this.vignette * (0.55 + 0.45 * crt) + 0.12 * frame.focus + 0.1 * mood.cinematic);
    gl.uniform1f(u.uVignetteK, 1 / Math.sqrt(1 - vig) - 1);

    // Alarm: the frame edges breathe in the mood colour (~0.9 Hz), subtle by design.
    const pulse = alarm > 0 ? alarm * (0.55 + 0.45 * Math.sin(frame.time * TAU * 0.9)) * 0.07 : 0;
    const mc = mood.color;
    gl.uniform3f(u.uEdgeGlow, mc[0] * pulse, mc[1] * pulse, mc[2] * pulse);

    gl.uniform1f(u.uExposure, this.exposure * (1 + 0.1 * (frame.lightning || 0)));

    const dpr = frame.dpr > 0 ? frame.dpr : 1;
    gl.uniform2f(u.uScan, this.scanlines * crt, Math.max(2, Math.round(2 * dpr)));
    gl.uniform1f(u.uGrain, this.grain * crt * (1 + 0.25 * mood.cinematic));
    gl.uniform1f(u.uGrainCell, Math.max(1, Math.round(dpr)));
    if (!reduced) this.#seed = (this.#seed + 1) >>> 0 || 1;
    gl.uniform1ui(u.uSeed, this.#seed);

    drawFullscreen(gl);
  }

  dispose() {
    const gl = this.#gl;
    for (const t of this.#mips) deleteTarget(gl, t);
    deleteTarget(gl, this.#streakA);
    deleteTarget(gl, this.#streakB);
    for (const p of [this.#prefilter, this.#down, this.#up, this.#streak, this.#composite]) gl.deleteProgram(p.program);
    this.#mips.length = 0;
  }

  // ── internals ─────────────────────────────────────────────────────────

  #program(fs, label) {
    const program = createProgram(this.#gl, FULLSCREEN_VS, fs, label);
    return { program, u: uniforms(this.#gl, program) };
  }

  #pass(gl, prog, src, dst) {
    gl.bindFramebuffer(gl.FRAMEBUFFER, dst.fbo);
    gl.viewport(0, 0, dst.w, dst.h);
    gl.bindTexture(gl.TEXTURE_2D, src.tex);
    gl.uniform2f(prog.u.uTexel, 1 / src.w, 1 / src.h);
    drawFullscreen(gl);
  }

  #bloom(gl, hdrTarget) {
    const mips = this.#mips;
    const hdr = mips[0].hdr;

    // 1. Prefilter: Karis-averaged 13-tap + soft knee, scene → mip 0.
    const pre = this.#prefilter;
    gl.useProgram(pre.program);
    // LDR fallback: the scene tops out at 1.0, so bloom must start lower to exist at all.
    const t = hdr ? this.threshold : 0.62;
    const k = Math.max(1e-4, (hdr ? this.knee : 0.35) * t);
    gl.uniform4f(pre.u.uCurve, t, t - k, 2 * k, 0.25 / k);
    gl.uniform1f(pre.u.uClamp, hdr ? 64 : 1);
    this.#pass(gl, pre, hdrTarget, mips[0]);

    // 2. Downsample chain.
    const down = this.#down;
    gl.useProgram(down.program);
    gl.uniform1f(down.u.uClamp, 65000);
    for (let i = 1; i < LEVELS; i++) this.#pass(gl, down, mips[i - 1], mips[i]);

    // 3. Anamorphic streak from the ¼-res mip, before the upsample adds into it.
    const st = this.#streak;
    gl.useProgram(st.program);
    gl.uniform1f(st.u.uThreshold, hdr ? this.streakThreshold : 0.4);
    gl.uniform1f(st.u.uSpacing, 1);
    this.#pass(gl, st, mips[1], this.#streakA);
    gl.uniform1f(st.u.uThreshold, 0);
    gl.uniform1f(st.u.uSpacing, 4);
    this.#pass(gl, st, this.#streakA, this.#streakB);
    gl.uniform1f(st.u.uSpacing, 16);
    this.#pass(gl, st, this.#streakB, this.#streakA);

    // 4. Tent upsample, accumulated additively into each larger mip.
    const up = this.#up;
    gl.useProgram(up.program);
    gl.uniform1f(up.u.uWeight, this.scatter);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    for (let i = LEVELS - 1; i > 0; i--) this.#pass(gl, up, mips[i], mips[i - 1]);
    gl.disable(gl.BLEND);
    this.#bloomValid = true;
  }
}
