/**
 * Renderer — owns the WebGL2 context and runs the frame pipeline (ARCHITECTURE §4.4).
 *
 *   world.render ─► worldRT (renderScale × worldScale, HDR)
 *        │  focus: dual-filter blur ½ → ¼ → ½ (only while focused)
 *        ▼
 *   blit (bilinear upscale; focus darken / desaturate / blur) ─► hdrRT (renderScale, RGBA16F)
 *   particles.render (additive) ─► hdrRT
 *   post.render (bloom, tonemap, lens, film) ─► canvas
 *
 * Focus is applied to the world in the blit, *before* particles are added, so the backdrop
 * recedes behind dense UI while sparks and data streams stay vivid on top of it.
 *
 * Frame state: one object, allocated once, mutated every frame and handed to every pass.
 * `width`/`height` are the pixel size of the target the current pass draws into and `dpr`
 * is pixels per CSS pixel *of that target* — so a pass sizes things correctly whether it
 * runs in the scaled world target, the HDR target or on the canvas. `renderScale` is the
 * HDR/canvas ratio; `cssWidth`/`cssHeight` never change between passes.
 *
 * Presentation state animates on real time (it keeps living through hit-stop and slow-mo):
 *  - mood: eased blend between six presets. Colours travel through OKLCH along the shortest
 *    hue arc, so every in-between is a saturated neon instead of a grey midpoint. Short
 *    blends (reactions) ease out; long ones (ambience) ease in and out.
 *  - flash: additive, quadratic decay over 0.25 s; overlapping flashes merge colour by
 *    energy and stack slightly brighter (bounded).
 *  - focus: critically damped spring.
 * `frame.time` is *sim* time interpolated by alpha, so the world freezes with hit-stop.
 *
 * Quality: 'high' | 'medium' | 'low' are fixed presets; 'auto' is a dynamic-resolution
 * governor on a hitch-robust EMA of the frame interval: > 18.5 ms for 0.5 s steps
 * renderScale down (two rungs when far over), < 12 ms for 2 s steps up. Because a 60 Hz
 * display never shows < 12 ms, the governor also probes upward after a period of frames
 * locked at the display's refresh rate; a probe that fails doubles the next probe delay.
 *
 * Robustness: no WebGL2 (or a failed core build) → `body.no-webgl`, `ok = false`, every
 * method a no-op and `particles` a no-op stub. Context loss stops drawing (preventDefault so
 * the browser may restore); restore rebuilds every GL object and sub-system. A sub-system
 * that throws is logged once and skipped; the rest of the frame still presents.
 *
 * Per frame: no allocations, no layout reads (sizes come from a ResizeObserver, applied at
 * the start of the next frame), uniform locations cached, GL state reset only where needed.
 */
import { bus as defaultBus } from '../core/bus.js';
import { settings as defaultSettings } from '../core/settings.js';
import { Spring, easeOutCubic, easeInOutCubic } from '../core/math.js';
import { createProgram, createTarget, resizeTarget, deleteTarget, drawFullscreen, uniforms, FULLSCREEN_VS } from './gl.js';
import { World } from './world.js';
import { Particles } from './particles.js';
import { Post } from './post.js';

const MAX_DPR = 2;
const FLASH_SECONDS = 0.25;
const LIGHTNING_EVENT = Object.freeze({});

/** Dynamic-resolution ladder for quality 'auto' (renderScale, top = best). */
const LADDER = [1, 0.85, 0.72, 0.6, 0.5];

const QUALITY = {
  auto: { scale: 1, worldScale: 0.6 },
  high: { scale: 1, worldScale: 0.6 },
  medium: { scale: 0.85, worldScale: 0.5 },
  low: { scale: 0.7, worldScale: 0.35 },
};

/** Mood presets (§4.4). Unlisted fields are 0; intensities not given by the contract are art calls. */
const MOODS = {
  calm: { color: [0.0, 0.85, 1.0], intensity: 0.8, corruption: 0.08 },
  mission: { color: [0.15, 0.6, 1.0], intensity: 0.85, corruption: 0.12 },
  combat: { color: [1.0, 0.17, 0.84], intensity: 1.0, corruption: 0.22 },
  alarm: { color: [1.0, 0.18, 0.25], intensity: 1.05, alarm: 1, corruption: 0.55 },
  victory: { color: [0.25, 1.0, 0.12], intensity: 1.35, victory: 1, corruption: 0.02 },
  cinematic: { color: [0.55, 0.3, 1.0], intensity: 0.9, cinematic: 1, corruption: 0.05 },
};

// Mood vector layout: OKLCH colour + the scalar channels.
const M_L = 0, M_C = 1, M_H = 2, M_INTENSITY = 3, M_ALARM = 4, M_CORRUPTION = 5, M_CINEMATIC = 6, M_VICTORY = 7;
const M_SIZE = 8;

// ── OKLab (Björn Ottosson) on linear sRGB ────────────────────────────────

function linearToOklch(r, g, b, out) {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  out[M_L] = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  out[M_C] = Math.hypot(A, B);
  out[M_H] = Math.atan2(B, A);
}

function oklchToLinear(L, C, h, out) {
  const A = C * Math.cos(h);
  const B = C * Math.sin(h);
  const l = L + 0.3963377774 * A + 0.2158037573 * B;
  const m = L - 0.1055613458 * A - 0.0638541728 * B;
  const s = L - 0.0894841775 * A - 1.291485548 * B;
  const l3 = l * l * l, m3 = m * m * m, s3 = s * s * s;
  // Saturated hues between two in-gamut endpoints can leave sRGB slightly: clip negatives.
  const r = Math.max(0, 4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3);
  const g = Math.max(0, -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3);
  const b = Math.max(0, -0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3);
  // Presets are 0..1 colours; keep in-betweens there too, preserving hue.
  const k = Math.max(r, g, b) > 1 ? 1 / Math.max(r, g, b) : 1;
  out[0] = r * k;
  out[1] = g * k;
  out[2] = b * k;
}

const MOOD_VECTORS = {};
for (const [name, p] of Object.entries(MOODS)) {
  const v = new Float32Array(M_SIZE);
  linearToOklch(p.color[0], p.color[1], p.color[2], v);
  v[M_INTENSITY] = p.intensity ?? 1;
  v[M_ALARM] = p.alarm ?? 0;
  v[M_CORRUPTION] = p.corruption ?? 0;
  v[M_CINEMATIC] = p.cinematic ?? 0;
  v[M_VICTORY] = p.victory ?? 0;
  MOOD_VECTORS[name] = { vector: v, rgb: Float32Array.from(p.color) };
}

// ── shaders ──────────────────────────────────────────────────────────────

// Dual-filter downsample (Bjørge, SIGGRAPH 2015): 5 bilinear taps cover a 4×4 footprint.
const BLUR_DOWN_FS = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;
uniform sampler2D uSrc;
uniform vec2 uTexel; // source texel
void main() {
  vec3 s = texture(uSrc, vUv).rgb * 4.0;
  s += texture(uSrc, vUv - uTexel).rgb;
  s += texture(uSrc, vUv + uTexel).rgb;
  s += texture(uSrc, vUv + vec2(uTexel.x, -uTexel.y)).rgb;
  s += texture(uSrc, vUv + vec2(-uTexel.x, uTexel.y)).rgb;
  outColor = vec4(s * 0.125, 1.0);
}
`;

// Dual-filter upsample: 8 taps, a smooth wide tent; ¼ → ½ so the blit needs one tap.
const BLUR_UP_FS = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;
uniform sampler2D uSrc;
uniform vec2 uTexel; // source texel
void main() {
  vec2 h = uTexel * 0.5;
  vec3 s = texture(uSrc, vUv + vec2(-uTexel.x, 0.0)).rgb + texture(uSrc, vUv + vec2(uTexel.x, 0.0)).rgb +
           texture(uSrc, vUv + vec2(0.0, -uTexel.y)).rgb + texture(uSrc, vUv + vec2(0.0, uTexel.y)).rgb;
  s += (texture(uSrc, vUv + vec2(-h.x, h.y)).rgb + texture(uSrc, vUv + vec2(h.x, h.y)).rgb +
        texture(uSrc, vUv + vec2(h.x, -h.y)).rgb + texture(uSrc, vUv + vec2(-h.x, -h.y)).rgb) * 2.0;
  outColor = vec4(s * (1.0 / 12.0), 1.0);
}
`;

// World → HDR: bilinear upscale, plus the focus treatment of the world (never the particles).
const BLIT_FS = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;
uniform sampler2D uWorld;
uniform sampler2D uBlur; // ½-res world blur, valid while uFocus.x > 0
uniform vec3 uFocus;     // blur mix, desaturation, brightness
void main() {
  vec3 c = texture(uWorld, vUv).rgb;
  if (uFocus.x > 0.0) c = mix(c, texture(uBlur, vUv).rgb, uFocus.x);
  float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
  outColor = vec4(max(mix(c, vec3(l), uFocus.y) * uFocus.z, 0.0), 1.0);
}
`;

// ── no-op stand-ins ──────────────────────────────────────────────────────

/** Particles stand-in when there is no GL (or the real module failed to build). */
const PARTICLES_STUB = Object.freeze({
  emit() {},
  emitPoints() {},
  update() {},
  render() {},
  setDensity() {},
  dispose() {},
  get count() {
    return 0;
  },
});

export class Renderer {
  /** False when WebGL2 is unavailable (or the pipeline could not be built). */
  ok = false;
  /** @type {WebGL2RenderingContext|null} */
  gl = null;
  /** @type {World|null} */
  world = null;
  /** Live particle system, or a no-op stub (no GL, context lost, build failure). */
  particles = PARTICLES_STUB;
  /** @type {Post|null} */
  post = null;

  #canvas;
  #bus;
  #settings;
  #camera;
  #lost = false;
  #disposed = false;
  #faults = new Set();
  #offSettings = null;

  // targets + programs
  #worldRT = null;
  #hdrRT = null;
  #blurA = null;
  #blurB = null;
  #blit = null;
  #blurDown = null;
  #blurUp = null;

  // sizing
  #observer = null;
  #dprQuery = null;
  #sizeDirty = true;
  #cssW = 1;
  #cssH = 1;
  #devW = 0; // exact device-pixel size from the observer (0 = derive from css × dpr)
  #devH = 0;

  // quality
  #quality = 'auto';
  #scale = 1;
  #worldScale = 0.6;
  #rung = 0;
  #govEma = 1000 / 60;
  #refreshMs = 1000 / 60;
  #overT = 0;
  #underT = 0;
  #stableT = 0;
  #settleT = 1;
  #sinceUp = Infinity;
  #probeDelay = 4;

  // presentation state
  #moodName = 'calm';
  #moodFrom = new Float32Array(M_SIZE);
  #moodTo = new Float32Array(M_SIZE);
  #moodCur = new Float32Array(M_SIZE);
  #moodTargetRgb = MOOD_VECTORS.calm.rgb;
  #moodT = 1;
  #moodDur = 0;
  #flashPeak = 0;
  #flashT = FLASH_SECONDS;
  #focus = new Spring(0, 7);
  #warnedMoods = new Set();

  // clocks + stats
  #simTime = 0;
  #simStep = 1 / 120;
  #statMs = 1000 / 60;
  #stats = { fps: 60, ms: 1000 / 60, scale: 1, particles: 0 };
  #postSettings = { crt: 1, bloom: true, reducedMotion: false };

  #frame = {
    time: 0,
    dt: 0,
    width: 1,
    height: 1,
    cssWidth: 1,
    cssHeight: 1,
    dpr: 1,
    alpha: 0,
    camera: { x: 0, y: 0, shakeX: 0, shakeY: 0, roll: 0 },
    mood: { color: new Float32Array(3), intensity: 0, alarm: 0, corruption: 0, cinematic: 0, victory: 0 },
    flash: { color: new Float32Array(3), amount: 0 },
    focus: 0,
    lightning: 0,
    renderScale: 1,
  };

  // bound once: listeners and callbacks never allocate later
  #onLost = (e) => this.#contextLost(e);
  #onRestored = () => this.#contextRestored();
  #onResize = (entries) => this.#observed(entries);
  #onWindowResize = () => this.#requestSize(window.innerWidth, window.innerHeight, 0, 0);
  #onDprChange = () => {
    this.#sizeDirty = true;
    this.#watchDpr();
  };
  #onStrike = () => this.#bus.emit('world:lightning', LIGHTNING_EVENT);

  /**
   * @param {HTMLCanvasElement} canvas
   * @param {{bus?: object, settings?: object, camera?: {state: object}, lowLatency?: boolean}} options
   *   lowLatency — the `desynchronized` context hint. Off under automation by default: a
   *   desynchronized canvas can stall headless screenshot capture.
   */
  constructor(canvas, { bus = defaultBus, settings = defaultSettings, camera = null, lowLatency } = {}) {
    this.#canvas = canvas;
    this.#bus = bus;
    this.#settings = settings;
    this.#camera = camera;

    this.#snapMood('calm');
    this.#readSettings();
    if (settings && typeof settings.onChange === 'function') {
      this.#offSettings = settings.onChange((key) => this.#settingChanged(key));
    }

    let gl = null;
    try {
      gl = canvas && typeof canvas.getContext === 'function'
        ? canvas.getContext('webgl2', {
            alpha: false,
            antialias: false,
            depth: false,
            stencil: false,
            premultipliedAlpha: false,
            preserveDrawingBuffer: false,
            powerPreference: 'high-performance',
            desynchronized: lowLatency ?? !(typeof navigator !== 'undefined' && navigator.webdriver),
          })
        : null;
    } catch {
      gl = null;
    }
    if (!gl) {
      this.#fallback(null);
      return;
    }
    this.gl = gl;

    canvas.addEventListener('webglcontextlost', this.#onLost);
    canvas.addEventListener('webglcontextrestored', this.#onRestored);
    this.#initialSize();
    this.#watchSize();

    try {
      this.#build();
      this.ok = true;
    } catch (err) {
      this.#fallback(err);
    }
  }

  // ── public API (§4.4) ───────────────────────────────────────────────────

  /** Fixed sim step: world + particles integrate; advances the clock the world animates on. */
  update(dt) {
    if (!this.ok || this.#lost) return;
    this.#simTime += dt;
    this.#simStep = dt;
    const world = this.world;
    if (world) {
      try {
        world.update(dt);
      } catch (err) {
        this.#fault('world.update', err);
      }
    }
    try {
      this.particles.update(dt);
    } catch (err) {
      this.#fault('particles.update', err);
    }
  }

  /** Renders one presented frame. `realDt` is wall-clock seconds, `alpha` the sim interpolant. */
  frame(realDt, alpha) {
    if (!this.ok || this.#lost) return;
    const gl = this.gl;
    const dt = realDt > 0 ? realDt : 0;

    this.#measure(dt);
    if (this.#sizeDirty) this.#applySize();
    if (this.#quality === 'auto') this.#govern(dt);
    this.#animate(dt);

    const f = this.#frame;
    f.time = this.#simTime + (alpha || 0) * this.#simStep;
    f.dt = dt;
    f.alpha = alpha || 0;
    f.renderScale = this.#scale;
    this.#copyCamera(f.camera);
    const world = this.world;
    f.lightning = world ? +world.lightning || 0 : 0;

    const worldRT = this.#worldRT;
    const hdrRT = this.#hdrRT;
    const cssW = f.cssWidth;

    gl.disable(gl.BLEND);
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    gl.disable(gl.SCISSOR_TEST);

    // 1. World → worldRT.
    gl.bindFramebuffer(gl.FRAMEBUFFER, worldRT.fbo);
    gl.viewport(0, 0, worldRT.w, worldRT.h);
    f.width = worldRT.w;
    f.height = worldRT.h;
    f.dpr = worldRT.w / cssW;
    let drewWorld = false;
    if (world) {
      try {
        world.render(gl, f);
        drewWorld = true;
      } catch (err) {
        this.#fault('world.render', err);
        gl.bindFramebuffer(gl.FRAMEBUFFER, worldRT.fbo);
        gl.viewport(0, 0, worldRT.w, worldRT.h);
      }
      this.#resetState(gl);
    }
    if (!drewWorld) {
      gl.clearColor(0.0015, 0.0018, 0.003, 1); // --void, linear
      gl.clear(gl.COLOR_BUFFER_BIT);
    }

    // 2. Focus blur of the world (only while focused): ½ → ¼ down, back up into ½.
    const focus = f.focus;
    const focused = focus > 0.002;
    if (focused) {
      const down = this.#blurDown;
      gl.useProgram(down.program);
      gl.activeTexture(gl.TEXTURE0);
      this.#pass(gl, down, worldRT, this.#blurA);
      this.#pass(gl, down, this.#blurA, this.#blurB);
      const up = this.#blurUp;
      gl.useProgram(up.program);
      this.#pass(gl, up, this.#blurB, this.#blurA);
    }

    // 3. Blit world → hdrRT (bilinear upscale + focus treatment).
    const blit = this.#blit;
    const u = blit.u;
    gl.bindFramebuffer(gl.FRAMEBUFFER, hdrRT.fbo);
    gl.viewport(0, 0, hdrRT.w, hdrRT.h);
    gl.useProgram(blit.program);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.#blurA.tex); // always bound: an empty unit is a driver warning
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, worldRT.tex);
    if (focused) {
      const blur = focus * 1.8; // fully defocused by the mission screen's 0.6
      gl.uniform3f(u.uFocus, blur > 1 ? 1 : blur, 0.3 * focus, 1 - 0.5 * focus);
    } else {
      gl.uniform3f(u.uFocus, 0, 0, 1);
    }
    drawFullscreen(gl);
    gl.bindTexture(gl.TEXTURE_2D, null); // never leave a render target bound for the next pass
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, null);
    gl.activeTexture(gl.TEXTURE0);

    // 4. Particles, additive into hdrRT.
    const particles = this.particles;
    if (particles !== PARTICLES_STUB) {
      f.width = hdrRT.w;
      f.height = hdrRT.h;
      f.dpr = hdrRT.w / cssW;
      gl.enable(gl.BLEND);
      gl.blendEquation(gl.FUNC_ADD);
      gl.blendFunc(gl.ONE, gl.ONE);
      try {
        particles.render(gl, f);
      } catch (err) {
        this.#fault('particles.render', err);
      }
      this.#resetState(gl);
    }

    // 5. Post → canvas.
    const canvas = this.#canvas;
    f.width = canvas.width;
    f.height = canvas.height;
    f.dpr = canvas.width / cssW;
    this.post.render(gl, hdrRT, f, this.#postSettings);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, null);
  }

  /** Blend to a mood preset over `seconds` (0 = snap). */
  setMood(name, seconds = 1.2) {
    const preset = MOOD_VECTORS[name];
    if (!preset) {
      if (!this.#warnedMoods.has(name)) {
        this.#warnedMoods.add(name);
        console.warn(`[renderer] unknown mood "${name}"`);
      }
      return;
    }
    const secs = Number(seconds);
    if (!(secs > 0)) {
      this.#snapMood(name);
      return;
    }
    if (name === this.#moodName) return; // already there, or already on the way
    this.#moodName = name;
    this.#moodFrom.set(this.#moodCur);
    this.#moodTo.set(preset.vector);
    this.#moodTargetRgb = preset.rgb;
    this.#moodT = 0;
    this.#moodDur = secs;
  }

  /** Additive full-screen flash of `rgb` ([r,g,b] 0..1 or '#rrggbb'), decaying over ~0.25 s. */
  flash(rgb, amount = 1) {
    const a = Math.min(Math.max(Number(amount) || 0, 0), 2);
    if (a <= 0) return;
    let r = 1, g = 1, b = 1;
    if (typeof rgb === 'string' && rgb[0] === '#') {
      const n = parseInt(rgb.slice(1), 16);
      r = ((n >> 16) & 255) / 255;
      g = ((n >> 8) & 255) / 255;
      b = (n & 255) / 255;
    } else if (rgb && rgb.length >= 3) {
      r = +rgb[0] || 0;
      g = +rgb[1] || 0;
      b = +rgb[2] || 0;
    }
    const fl = this.#frame.flash;
    const cur = fl.amount;
    const c = fl.color;
    if (cur > 0.001) {
      // Merge by energy: colours blend, overlapping hits stack a little brighter (bounded).
      const w = a / (a + cur);
      c[0] += (r - c[0]) * w;
      c[1] += (g - c[1]) * w;
      c[2] += (b - c[2]) * w;
      this.#flashPeak = Math.min(1.5, Math.max(a, cur) + 0.35 * Math.min(a, cur));
    } else {
      c[0] = r;
      c[1] = g;
      c[2] = b;
      this.#flashPeak = a;
    }
    this.#flashT = 0;
    fl.amount = this.#flashPeak;
  }

  /** 0..1 — recede the world behind dense UI (darken, desaturate, blur). Springs to target. */
  setFocus(amount) {
    const v = Number(amount) || 0;
    this.#focus.target = v < 0 ? 0 : v > 1 ? 1 : v;
  }

  /** {fps, ms, scale, particles} — one object, refreshed in place each frame. */
  get stats() {
    const s = this.#stats;
    s.fps = 1000 / this.#statMs;
    s.ms = this.#statMs;
    s.scale = this.ok ? this.#scale : 0;
    s.particles = this.particles.count | 0;
    return s;
  }

  /** The live frame-state object (read-only by convention). */
  get frameState() {
    return this.#frame;
  }

  /** Name of the mood currently being blended toward. */
  get mood() {
    return this.#moodName;
  }

  /** Releases every listener and GL object. The renderer is inert afterwards. */
  dispose() {
    if (this.#disposed) return;
    this.#disposed = true;
    this.#offSettings?.();
    this.#offSettings = null;
    this.#observer?.disconnect();
    this.#observer = null;
    if (typeof window !== 'undefined') window.removeEventListener('resize', this.#onWindowResize);
    this.#dprQuery?.removeEventListener('change', this.#onDprChange);
    this.#dprQuery = null;
    const canvas = this.#canvas;
    if (canvas) {
      canvas.removeEventListener('webglcontextlost', this.#onLost);
      canvas.removeEventListener('webglcontextrestored', this.#onRestored);
    }
    if (this.gl && !this.#lost && !this.gl.isContextLost()) this.#destroyGL();
    this.ok = false;
    this.world = null;
    this.post = null;
    this.particles = PARTICLES_STUB;
  }

  // ── build / teardown ────────────────────────────────────────────────────

  #build() {
    const gl = this.gl;
    // Post and the pipeline's own passes are the core: if they fail, there is no picture.
    this.post = new Post(gl);
    this.#blit = this.#program(BLIT_FS, 'renderer.blit');
    this.#blurDown = this.#program(BLUR_DOWN_FS, 'renderer.focusDown');
    this.#blurUp = this.#program(BLUR_UP_FS, 'renderer.focusUp');
    gl.useProgram(this.#blit.program);
    gl.uniform1i(this.#blit.u.uWorld, 0);
    gl.uniform1i(this.#blit.u.uBlur, 1);
    for (const p of [this.#blurDown, this.#blurUp]) {
      gl.useProgram(p.program);
      gl.uniform1i(p.u.uSrc, 0);
    }
    gl.useProgram(null);

    this.#worldRT = createTarget(gl, 1, 1, { hdr: true });
    this.#hdrRT = createTarget(gl, 1, 1, { hdr: true });
    this.#blurA = createTarget(gl, 1, 1, { hdr: true });
    this.#blurB = createTarget(gl, 1, 1, { hdr: true });
    // Shake, roll and lens barrel sample slightly outside the frame: reflect, don't smear.
    gl.bindTexture(gl.TEXTURE_2D, this.#hdrRT.tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.MIRRORED_REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.MIRRORED_REPEAT);
    gl.bindTexture(gl.TEXTURE_2D, null);

    // World and particles are content: a failure degrades the picture, never removes it.
    try {
      this.world = new World(gl);
      this.world.onStrike = this.#onStrike;
    } catch (err) {
      this.world = null;
      this.#fault('world', err);
    }
    try {
      // `camera` (optional extra): emits measured mid-shake are mapped back to layout space.
      this.particles = new Particles(gl, { capacity: 12000, camera: this.#camera });
    } catch (err) {
      this.particles = PARTICLES_STUB;
      this.#fault('particles', err);
    }

    this.#sizeDirty = true;
    this.#settle(1);
  }

  #destroyGL() {
    const gl = this.gl;
    try {
      this.world?.dispose?.();
      this.particles?.dispose?.();
      this.post?.dispose?.();
    } catch {
      /* sub-system teardown is best effort */
    }
    for (const t of [this.#worldRT, this.#hdrRT, this.#blurA, this.#blurB]) if (t) deleteTarget(gl, t);
    for (const p of [this.#blit, this.#blurDown, this.#blurUp]) if (p) gl.deleteProgram(p.program);
    this.#worldRT = this.#hdrRT = this.#blurA = this.#blurB = null;
    this.#blit = this.#blurDown = this.#blurUp = null;
  }

  #program(fs, label) {
    const program = createProgram(this.gl, FULLSCREEN_VS, fs, label);
    return { program, u: uniforms(this.gl, program) };
  }

  #fallback(err) {
    if (err) console.error('[renderer] WebGL2 pipeline unavailable, using the CSS fallback', err);
    this.ok = false;
    this.world = null;
    this.post = null;
    this.particles = PARTICLES_STUB;
    if (typeof document !== 'undefined' && document.body) document.body.classList.add('no-webgl');
    if (this.#canvas && this.#canvas.style) this.#canvas.style.display = 'none';
    this.#observer?.disconnect();
    this.#observer = null;
  }

  #contextLost(event) {
    event.preventDefault(); // tells the browser we can restore
    if (this.#lost) return;
    this.#lost = true;
    // Every GL object is gone; drop references (deleting them now would be an error).
    this.world = null;
    this.post = null;
    this.particles = PARTICLES_STUB;
    this.#worldRT = this.#hdrRT = this.#blurA = this.#blurB = null;
    this.#blit = this.#blurDown = this.#blurUp = null;
  }

  #contextRestored() {
    if (this.#disposed || !this.ok) return;
    try {
      this.#build();
      this.#lost = false;
    } catch (err) {
      this.#fallback(err);
    }
  }

  #fault(where, err) {
    if (this.#faults.has(where)) return;
    this.#faults.add(where);
    console.error(`[renderer] ${where} failed; continuing without it`, err);
  }

  /** Restores the state the renderer's own passes assume after foreign code ran. */
  #resetState(gl) {
    gl.disable(gl.BLEND);
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    gl.disable(gl.SCISSOR_TEST);
    gl.bindVertexArray(null);
    gl.activeTexture(gl.TEXTURE0);
  }

  #pass(gl, prog, src, dst) {
    gl.bindFramebuffer(gl.FRAMEBUFFER, dst.fbo);
    gl.viewport(0, 0, dst.w, dst.h);
    gl.bindTexture(gl.TEXTURE_2D, src.tex);
    gl.uniform2f(prog.u.uTexel, 1 / src.w, 1 / src.h);
    drawFullscreen(gl);
  }

  // ── sizing ──────────────────────────────────────────────────────────────

  #initialSize() {
    const c = this.#canvas;
    const w = c.clientWidth || (typeof window !== 'undefined' ? window.innerWidth : 1);
    const h = c.clientHeight || (typeof window !== 'undefined' ? window.innerHeight : 1);
    this.#requestSize(w, h, 0, 0);
  }

  #watchSize() {
    if (typeof ResizeObserver === 'function') {
      this.#observer = new ResizeObserver(this.#onResize);
      try {
        // Exact device pixels: the canvas maps 1:1 onto the panel, so scanlines never alias.
        this.#observer.observe(this.#canvas, { box: 'device-pixel-content-box' });
      } catch {
        this.#observer.observe(this.#canvas);
      }
    } else if (typeof window !== 'undefined') {
      window.addEventListener('resize', this.#onWindowResize);
    }
    this.#watchDpr();
  }

  /** Re-arms a one-shot media query for the *current* DPR (zoom, moving between monitors). */
  #watchDpr() {
    if (typeof matchMedia !== 'function' || this.#disposed) return;
    this.#dprQuery?.removeEventListener('change', this.#onDprChange);
    this.#dprQuery = matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`);
    this.#dprQuery.addEventListener('change', this.#onDprChange);
  }

  #observed(entries) {
    const e = entries[entries.length - 1];
    const box = e.contentBoxSize && e.contentBoxSize[0];
    const cssW = box ? box.inlineSize : e.contentRect.width;
    const cssH = box ? box.blockSize : e.contentRect.height;
    const dev = e.devicePixelContentBoxSize && e.devicePixelContentBoxSize[0];
    const dpr = window.devicePixelRatio || 1;
    // Trust the exact box only when it agrees with css × dpr (DPR emulation reports it unscaled).
    const exact =
      dev && dpr <= MAX_DPR && Math.abs(dev.inlineSize - cssW * dpr) <= 2 && Math.abs(dev.blockSize - cssH * dpr) <= 2;
    this.#requestSize(cssW, cssH, exact ? dev.inlineSize : 0, exact ? dev.blockSize : 0);
  }

  #requestSize(cssW, cssH, devW, devH) {
    this.#cssW = cssW > 0 ? cssW : 1;
    this.#cssH = cssH > 0 ? cssH : 1;
    this.#devW = devW | 0;
    this.#devH = devH | 0;
    this.#sizeDirty = true;
  }

  #applySize() {
    this.#sizeDirty = false;
    const dpr = Math.min(typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1, MAX_DPR);
    const cssW = this.#cssW;
    const cssH = this.#cssH;
    const w = Math.max(1, this.#devW || Math.round(cssW * dpr));
    const h = Math.max(1, this.#devH || Math.round(cssH * dpr));
    const canvas = this.#canvas;
    if (canvas.width !== w) canvas.width = w;
    if (canvas.height !== h) canvas.height = h;
    const f = this.#frame;
    f.cssWidth = cssW;
    f.cssHeight = cssH;
    this.#resizeTargets();
  }

  #resizeTargets() {
    const gl = this.gl;
    const cw = this.#canvas.width;
    const ch = this.#canvas.height;
    const s = this.#scale;
    const ws = s * this.#worldScale;
    const hw = Math.max(1, Math.round(cw * s));
    const hh = Math.max(1, Math.round(ch * s));
    const ww = Math.max(1, Math.round(cw * ws));
    const wh = Math.max(1, Math.round(ch * ws));
    resizeTarget(gl, this.#hdrRT, hw, hh);
    resizeTarget(gl, this.#worldRT, ww, wh);
    resizeTarget(gl, this.#blurA, Math.ceil(ww / 2), Math.ceil(wh / 2));
    resizeTarget(gl, this.#blurB, Math.ceil(ww / 4), Math.ceil(wh / 4));
    this.post.resize(hw, hh);
    this.#settle(0.35);
  }

  // ── quality ─────────────────────────────────────────────────────────────

  #readSettings() {
    const s = this.#settings;
    const get = (k, d) => {
      const v = s && typeof s.get === 'function' ? s.get(k) : undefined;
      return v === undefined ? d : v;
    };
    const ps = this.#postSettings;
    ps.crt = Math.min(Math.max(Number(get('crt', 1)) || 0, 0), 1);
    ps.bloom = get('bloom', true) !== false;
    ps.reducedMotion = !!get('reducedMotion', false);
    this.#setQuality(get('quality', 'auto'));
  }

  #settingChanged(key) {
    if (key === 'crt' || key === 'bloom' || key === 'reducedMotion' || key === 'quality') this.#readSettings();
  }

  #setQuality(mode) {
    const q = QUALITY[mode] ? mode : 'auto';
    if (q === this.#quality && this.#scale === (q === 'auto' ? LADDER[this.#rung] : QUALITY[q].scale)) return;
    this.#quality = q;
    this.#worldScale = QUALITY[q].worldScale;
    if (q === 'auto') {
      this.#rung = 0;
      this.#probeDelay = 4;
      this.#scale = LADDER[0];
    } else {
      this.#scale = QUALITY[q].scale;
    }
    if (this.ok && !this.#lost) this.#resizeTargets();
  }

  #settle(seconds) {
    this.#settleT = Math.max(this.#settleT, seconds);
    this.#overT = 0;
    this.#underT = 0;
    this.#stableT = 0;
  }

  /** Frame-interval EMAs: plain for stats, hitch-robust for the governor. */
  #measure(dt) {
    if (dt <= 0) return;
    const ms = dt * 1000;
    this.#statMs += (ms - this.#statMs) * (1 - Math.exp(-dt / 0.25));
    // A single GC pause or tab hitch is clipped so it cannot trip a resolution change.
    let s = ms;
    const cap = this.#govEma * 2.5;
    if (s > cap) s = cap;
    if (s > 100) s = 100;
    this.#govEma += (s - this.#govEma) * (1 - Math.exp(-s / 250));
    // Lower envelope of the interval ≈ the display's refresh period.
    this.#refreshMs += (ms - this.#refreshMs) * (ms < this.#refreshMs ? 0.05 : 0.004);
  }

  #govern(dt) {
    this.#sinceUp += dt;
    if (this.#settleT > 0) {
      this.#settleT -= dt;
      return;
    }
    const ema = this.#govEma;
    if (ema > 18.5) {
      this.#overT += dt;
      this.#underT = 0;
      this.#stableT = 0;
    } else {
      this.#overT = 0;
      this.#underT = ema < 12 ? this.#underT + dt : 0;
      // Locked to a ≥ 12 ms refresh with no dropped frames: there may be headroom we can't see.
      const locked = this.#refreshMs >= 12 && ema < this.#refreshMs * 1.12 + 0.4;
      this.#stableT = locked ? this.#stableT + dt : 0;
    }

    const last = LADDER.length - 1;
    if (this.#overT >= 0.5 && this.#rung < last) {
      if (this.#sinceUp < 3) this.#probeDelay = Math.min(this.#probeDelay * 2, 64); // failed probe
      this.#rung = Math.min(last, this.#rung + (ema > 33 ? 2 : 1));
      this.#applyRung();
    } else if (this.#rung > 0 && (this.#underT >= 2 || this.#stableT >= this.#probeDelay)) {
      this.#rung -= 1;
      this.#sinceUp = 0;
      this.#applyRung();
    }
  }

  #applyRung() {
    this.#scale = LADDER[this.#rung];
    this.#resizeTargets();
  }

  // ── presentation state ──────────────────────────────────────────────────

  #snapMood(name) {
    const preset = MOOD_VECTORS[name];
    this.#moodName = name;
    this.#moodCur.set(preset.vector);
    this.#moodFrom.set(preset.vector);
    this.#moodTo.set(preset.vector);
    this.#moodTargetRgb = preset.rgb;
    this.#moodT = 1;
    this.#moodDur = 0;
    this.#writeMood(true);
  }

  #animate(dt) {
    // Mood.
    if (this.#moodT < 1) {
      this.#moodT = Math.min(1, this.#moodT + dt / this.#moodDur);
      const t = this.#moodT;
      const e = this.#moodDur < 0.8 ? easeOutCubic(t) : easeInOutCubic(t);
      const a = this.#moodFrom;
      const b = this.#moodTo;
      const c = this.#moodCur;
      for (let i = 0; i < M_SIZE; i++) c[i] = a[i] + (b[i] - a[i]) * e;
      // Hue along the shortest arc.
      let dh = b[M_H] - a[M_H];
      if (dh > Math.PI) dh -= 2 * Math.PI;
      else if (dh < -Math.PI) dh += 2 * Math.PI;
      c[M_H] = a[M_H] + dh * e;
      this.#writeMood(t >= 1);
    }

    // Flash: quadratic decay to zero over FLASH_SECONDS.
    const fl = this.#frame.flash;
    if (this.#flashT < FLASH_SECONDS) {
      this.#flashT += dt;
      const k = 1 - this.#flashT / FLASH_SECONDS;
      fl.amount = k > 0 ? this.#flashPeak * k * k : 0;
    } else {
      fl.amount = 0;
    }

    // Focus.
    const v = this.#focus.update(dt);
    this.#frame.focus = v < 0.0005 ? 0 : v > 1 ? 1 : v;
  }

  #writeMood(exact) {
    const c = this.#moodCur;
    const m = this.#frame.mood;
    if (exact) m.color.set(this.#moodTargetRgb);
    else oklchToLinear(c[M_L], c[M_C], c[M_H], m.color);
    m.intensity = c[M_INTENSITY];
    m.alarm = c[M_ALARM];
    m.corruption = c[M_CORRUPTION];
    m.cinematic = c[M_CINEMATIC];
    m.victory = c[M_VICTORY];
  }

  #copyCamera(out) {
    const cam = this.#camera;
    if (!cam) return;
    const s = cam.state;
    if (!s) return;
    out.x = +s.x || 0;
    out.y = +s.y || 0;
    out.shakeX = +s.shakeX || 0;
    out.shakeY = +s.shakeY || 0;
    out.roll = +s.roll || 0;
  }
}
