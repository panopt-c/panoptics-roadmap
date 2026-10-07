/**
 * World — "The Dead Zone", the backdrop behind every screen (ARCHITECTURE §4.4, art bible §6).
 *
 * One full-screen fragment pass, fully analytic: no textures, no geometry, no loops over
 * 5 iterations. Back to front:
 *
 *   sky       perspective cloud deck (5-octave value fbm, domain-warped) lit from below by
 *             the city haze, with a second density tap toward the Core for relief shading
 *   Core      the monolith on the horizon, right of centre. Its light *is* the mood colour:
 *             halo, climbing energy bands, a crown point and a beam that punches into the
 *             cloud deck (and glows through its gaps above it), plus soft angular god rays
 *   towers    two parallax layers of ruined server towers, two interleaved cell grids each
 *             (per-cell height, setback tiers, slanted/jagged broken tops, antennas with
 *             beacons), sparse windows on a slow random schedule, a few failing tubes,
 *             a rim of Core light on the facing edges, fog thickening toward the waterline
 *   water     a perspective plane: rain-ripple rings + a slow swell perturb the reflection
 *             lookup; every layer mirrors about its *own* waterline and blurs with distance
 *             from it; Fresnel; submerged data-lines converge on the Core with packets
 *             flowing toward the horizon
 *   rain      three depths of slanted streaks (the far one sits behind the near towers)
 *
 * Mood drives everything: the colour tints Core, haze, windows and data-lines; intensity
 * scales emission; corruption adds glitch bands, block displacement and an RGB split
 * inside the bands (the split re-evaluates the scene in a dynamic loop, so only band rows
 * pay for it and the scene code is emitted once); alarm pulses red through haze and Core;
 * victory lights the city back up in a wave from the Core; cinematic dollies in toward the
 * Core and raises contrast. Output is linear HDR: only the Core, the beam, lightning and a
 * few packets exceed 1.0, so bloom has something to catch and the rest stays dark.
 *
 * Anti-aliasing: the pixel footprint comes from the (affine) uv derivatives, taken at the
 * top of main() before any branch. Every warped domain (cloud deck, water plane) gets its
 * footprint analytically, so the scene function has no derivative instructions and is safe
 * to call from the glitch loop. Edges are box-filtered against that footprint; thin lights
 * widen while conserving energy; noise octaves, windows and ripples fade to their mean once
 * they shrink below a pixel — the image holds still at 0.35x and upscaled.
 *
 * Time: `frame.time` is sim time (freezes with hit-stop, slows with timeScale). It reaches
 * the shader wrapped at TIME_WRAP seconds; every periodic rate in the shader is a multiple
 * of 1/TIME_WRAP Hz so the wrap is seamless. Unbounded drifts (clouds, swell, mist) are
 * closed-form functions of time evaluated here in double precision and passed as offsets.
 *
 * Lightning: own scheduler in update(dt) — strikes every 7–20 s, each a double or triple
 * flicker (fast attack, exponential decay) plus a short afterglow inside the clouds; ~40%
 * also show a forked bolt to the horizon. Strikes favour the edges, away from the calm
 * centre-left where UI lives.
 *
 * Accessibility (`settings.reducedMotion`): a strike becomes a single soft swell with no bolt
 * (no rapid flicker), the alarm pulse is shallower, glitches fire less often and the idle
 * camera sway stops.
 *
 * Per frame: uniforms only, on cached locations; no allocations, no GL queries.
 */
import { createProgram, uniforms, drawFullscreen, FULLSCREEN_VS } from './gl.js';
import { settings } from '../core/settings.js';
import { damp, rand } from '../core/math.js';

const TIME_WRAP = 1000;
const STRIKE_MIN = 7;
const STRIKE_MAX = 20;
const MAX_FLASHES = 3;
const GUST_A_MINUS_B = 0.031 - 0.017;
const GUST_A_PLUS_B = 0.031 + 0.017;
const GUST_C = 1.3;

const FS = /* glsl */ `#version 300 es
precision highp float;
precision highp int;

in vec2 vUv;
out vec4 outColor;

uniform vec4 uTime;    // x: seconds (wrapped), y: alarm pulse 0..1, z: glitch activity 0..1, w: glitch step
uniform vec4 uDrift;   // cloud x, cloud y, swell, mist (unbounded offsets)
uniform vec3 uMood;    // mood colour, linear
uniform vec4 uMoodK;   // intensity, alarm, corruption, cinematic
uniform float uVictory;
uniform vec4 uLight;   // envelope, strike x, strike y (scene units), bolt amount
uniform float uBoltSeed;
uniform vec4 uCam;     // parallax x, parallax y, zoom, idle sway
uniform vec4 uSweep;   // searchlight directions: left (sin, cos), right (sin, cos) of the angle from vertical
uniform float uSweepK; // searchlight strength

// ── layout, in scene units: 1 = viewport height, x = 0 at the centre, y = 0 on the horizon ──
const float HORIZON = 0.355;          // horizon height in vUv
const float CORE_H = 0.225;           // monolith shoulder height
const float CORE_W = 0.03;            // half width at the base (tapers to 76%)
const float CORE_TAPER = 0.24;
const float CORE_ROOF = 1.1;          // crown gable slope
const float CROWN = CORE_H + CORE_W * (1.0 - CORE_TAPER) * CORE_ROOF;
const float BEAM_Y = 0.425;           // where the beam enters the cloud deck
const float CLOUD_H = 0.42;           // cloud deck height (perspective scale)
const float CLOUD_E = 0.035;          // horizon bend (keeps the deck finite at y = 0)
const float WATER_H = 0.12;           // eye height above the water
const float FAR_BASE = -0.006;        // far layer waterline
const float NEAR_BASE = -0.05;        // near layer waterline

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
const vec3 AMBER = vec3(1.0, 0.42, 0.05);
const vec3 BLOOD = vec3(1.0, 0.03, 0.07);
const vec3 BEACON = vec3(1.0, 0.06, 0.04);
const vec3 BOLT = vec3(0.72, 0.8, 1.0);
const vec3 ZENITH = vec3(0.0010, 0.0013, 0.0024);
const vec3 ACID = vec3(0.25, 1.0, 0.12);

// Tower layers: cell A, cell B, min height, max height.
const vec4 TW_SHAPE[2] = vec4[2](vec4(0.019, 0.031, 0.012, 0.082), vec4(0.052, 0.083, 0.05, 0.3));
// Window grid: spacing x, spacing y, lit probability, brightness.
const vec4 TW_WIN[2] = vec4[2](vec4(0.0042, 0.0058, 0.06, 0.6), vec4(0.0085, 0.0112, 0.045, 1.25));
const vec3 TW_BASE[2] = vec3[2](vec3(0.0030, 0.0036, 0.0052), vec3(0.0011, 0.0013, 0.0019));
// Rain: columns per unit, speed (cells/s), streak width, gain.
const vec4 RAIN[3] = vec4[3](vec4(92.0, 11.0, 0.0006, 0.55), vec4(46.0, 9.0, 0.0011, 0.8), vec4(21.0, 6.0, 0.0024, 1.0));
const vec3 RAIN_K[3] = vec3[3](vec3(0.55, 0.012, 0.11), vec3(0.32, 0.025, 0.09), vec3(0.12, 0.045, 0.07)); // density, parallax, rows per column

// ── per-pixel globals (set once in main) ──
float gT, gPx, gAspect, gI, gCoreX, gAlarm;
vec3 gMood, gFog, gCore;

// ── hashing & noise ──
// Integer PCG for the discrete decisions (towers, windows, rain, glitches): exact at any
// coordinate and identical on every GPU, so the skyline never drifts between machines.
uint pcg(uint v) {
  uint s = v * 747796405u + 2891336453u;
  uint w = ((s >> ((s >> 28u) + 4u)) ^ s) * 277803737u;
  return (w >> 22u) ^ w;
}
float u2f(uint h) { return float(h >> 8u) * (1.0 / 16777216.0); }
uvec2 lattice(vec2 p) { return uvec2(ivec2(floor(p)) + 0x40000); }
float hash11(float x) { return u2f(pcg(uint(int(floor(x)) + 0x40000))); }
float hash21(vec2 p) { uvec2 c = lattice(p); return u2f(pcg(c.y + pcg(c.x))); }
vec4 hash42(vec2 p) {
  uvec2 c = lattice(p);
  uint a = pcg(c.y + pcg(c.x));
  uint b = pcg(a);
  uint d = pcg(b);
  return vec4(u2f(a), u2f(b), u2f(d), u2f(pcg(d)));
}
// Noise runs on a float hash (Hoskins, "hash without sine"): it is the hottest code in the
// pass and integer multiplies run at quarter rate on some integrated GPUs. Lattice inputs
// stay small (< ~1e4), well inside its precision.
float hashf(float p) {
  p = fract(p * 0.1031);
  p *= p + 33.33;
  return fract((p + p) * p);
}
float hashf(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}
float noise1(float x) {
  float i = floor(x);
  float f = x - i;
  return mix(hashf(i), hashf(i + 1.0), f * f * (3.0 - 2.0 * f));
}
float vnoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = p - i;
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hashf(i), hashf(i + vec2(1.0, 0.0)), u.x), mix(hashf(i + vec2(0.0, 1.0)), hashf(i + 1.0), u.x), u.y);
}
// Band-limited fbm: an octave whose cells shrink toward a pixel fades to its mean, and once
// one is gone (or the LOD ends) the rest contribute their mean without being evaluated, so
// every LOD and distance has the same average density — and the horizon costs the least.
const mat2 OCT = mat2(0.8, 0.6, -0.6, 0.8) * 2.03;
float fbm(vec2 p, int oct, float fw) {
  float s = 0.0, a = 0.5;
  for (int i = 0; i < 5; i++) {
    float k = 1.6 - fw * 2.4;
    if (i >= oct || k <= 0.0) { s += a * (1.0 - exp2(float(i - 5))); break; }
    s += a * mix(0.5, vnoise(p), min(k, 1.0));
    p = OCT * p + vec2(13.7, 7.1);
    fw *= 2.03;
    a *= 0.5;
  }
  return s;
}

float sq(float x) { return x * x; }
// Box-filtered coverage of a line of width w at signed offset d, for a pixel of width px.
float lineCov(float d, float w, float px) {
  d = abs(d);
  return clamp((min(d + 0.5 * px, 0.5 * w) - max(d - 0.5 * px, -0.5 * w)) / px, 0.0, 1.0);
}
// Exponential glow of width w, widened to the pixel footprint while conserving energy:
// a thin light never sparkles or vanishes at low render scales.
float glow(float d, float w, float px) {
  float we = sqrt(w * w + 0.35 * px * px);
  return (w / we) * exp(-abs(d) / we);
}

// ── sky: haze, clouds, Core, beam, rays, bolt. Also evaluated mirrored for the water. ──
vec3 sky(vec2 p, bool refl, float px) {
  float y = max(p.y, 0.0);
  vec3 col = ZENITH * (1.0 + 1.5 * exp(-y / 0.25));
  col += gFog * (3.2 * exp(-y / 0.028) + 0.7 * exp(-y / 0.12));

  // Light pollution around the Core.
  vec2 dc = (p - vec2(gCoreX, CROWN * 0.62)) * vec2(0.85, 1.0);
  float rc = length(dc);
  col += gCore * (0.07 * exp(-rc / 0.08) + 0.04 * exp(-rc / 0.3) + 0.012 * exp(-rc / 0.8));
  col += gCore * 0.5 * exp(-abs(p.x - gCoreX) / 0.06 - y / 0.012);  // pooled at its foot

  // Cloud deck: a perspective plane overhead. q is the deck coordinate.
  float inv = 1.0 / (y + CLOUD_E);
  float cx = p.x + uCam.x * 0.004;
  vec2 q = vec2(cx * inv, inv) * CLOUD_H;
  float fw = px * CLOUD_H * inv * (inv * (1.0 + abs(cx)) * 2.6 + 2.1);   // deck footprint, noise units
  vec2 nq = q * vec2(2.1, 2.6) + uDrift.xy;
  float warp = fbm(nq * 0.42 + vec2(3.1, 1.7) + uDrift.xy * 0.3, refl ? 2 : 3, fw * 0.42);
  vec2 wq = nq + warp * 1.25;
  float d = fbm(wq, refl ? 3 : 5, fw);
  float cov = smoothstep(0.34, 0.66, d) * smoothstep(0.0, 0.045, y);
  float relief = 0.5;
  if (!refl) {
    // Second tap toward the Core: faces turned to the light catch it, the rest falls into shadow.
    vec2 toCore = normalize(vec2((gCoreX - cx) * 1.6, 1.0));
    float d2 = fbm(wq + toCore * 0.11, 5, fw);
    relief = clamp(0.5 + (d - d2) * 5.5, 0.0, 1.0);
  }
  vec3 under = gFog * (0.45 + 6.5 * exp(-y / 0.1));
  vec3 cl = ZENITH * 1.4 + under * (0.08 + 1.5 * relief * relief) * (0.4 + 1.2 * d);
  // The beam splashes across the underside of the deck.
  float hinv = CLOUD_H / (BEAM_Y + CLOUD_E);
  vec2 hq = vec2(gCoreX * hinv, hinv);
  vec2 dq = q - vec2(hq.x + uCam.x * 0.004 * hinv, hq.y);
  vec2 sk = dq * vec2(9.0, 15.0);
  float splash = exp(-dot(sk, sk));   // gaussian: dense cloud a little way off must not out-glow the hit
  float wash = exp(-length(dq * vec2(0.9, 2.2)));
  cl += gCore * (splash * (0.1 + 2.0 * d * relief) + wash * 0.08 * d * relief);
  // Lightning lights the deck from inside. The storm cell is centred on the strike and brings
  // its own cloud, so the flash (and the bolt leaving it) never sits in clear sky; within it
  // the thick cores glow hardest. Depth is squeezed: the upper sky spans little deck depth.
  float L = uLight.x;
  float mixCov = cov;
  if (L > 0.001) {
    float sinv = CLOUD_H / (uLight.z + CLOUD_E);
    vec2 sd = (q - vec2(uLight.y * sinv, sinv)) * vec2(4.0, 8.0);
    float cell = exp(-dot(sd, sd));
    float halo = exp(-length(sd) * 0.35);
    cl += BOLT * L * (cell * (0.35 + 9.0 * d * d * d) * 2.0 + halo * 0.035 + 0.004);
    col += BOLT * L * (0.003 + 0.05 * cell + 0.008 * halo);
    mixCov = max(cov, cell * min(L * 3.0, 1.0) * 0.85 * smoothstep(0.0, 0.08, y));
  }
  col = mix(col, cl, mixCov);
  col += gCore * splash * 0.04;   // haze around the splash, even between clouds

  // WATCHDOG's searchlights: two pale cones sweeping up from the far city, lost in the deck.
  if (uSweepK > 0.0) {
    vec3 sc = mix(vec3(0.62, 0.74, 1.0), BLOOD, gAlarm * 0.75) * uSweepK;
    for (int i = 0; i < 2; i++) {
      vec2 o = vec2((i == 0 ? -0.33 : 0.41) * gAspect - uCam.x * 0.012, 0.015);   // on the far skyline
      vec2 dir = i == 0 ? uSweep.xy : uSweep.zw;
      vec2 v = p - o;
      float along = dot(v, dir);
      if (along > 0.0) {
        float w = 0.0025 + along * 0.05;
        float perp = v.x * dir.y - v.y * dir.x;
        col += sc * exp(-sq(perp / w)) * min(1.0, 0.004 / w) * exp(-along * 1.6) * 0.07 * (1.0 - 0.75 * cov) * (1.0 - smoothstep(0.25, 0.5, y));
      }
    }
  }

  // God rays: soft angular shafts fanning out of the crown, stronger in clear air.
  vec2 dr = p - vec2(gCoreX, CROWN);
  float rr = length(dr);
  float ang = atan(dr.x, dr.y);
  float rays = noise1(ang * 4.0 + uDrift.x * 0.5) * 0.65 + noise1(ang * 9.0 - uDrift.x * 0.9) * 0.35;
  rays = smoothstep(0.5, 1.0, rays);
  col += gCore * rays * 0.035 * exp(-rr * 3.0) * smoothstep(0.02, 0.12, rr) * (1.0 - 0.6 * cov);

  // The Core: obsidian slab, tapering, gabled crown.
  vec2 c = vec2(p.x - gCoreX, p.y);
  float hw = CORE_W * (1.0 - CORE_TAPER * clamp(c.y / CORE_H, 0.0, 1.0));
  float ax = abs(c.x);
  float roof = CORE_H + (hw - ax) * CORE_ROOF;
  float din = min(hw - ax, roof - c.y);
  float ccov = clamp(din / px + 0.5, 0.0, 1.0);
  float dout = length(vec2(max(ax - hw, 0.0), max(c.y - roof, 0.0)));
  col += gCore * (0.3 * exp(-dout / 0.004) + 0.07 * exp(-dout / 0.03)) * (1.0 - ccov);
  if (ccov > 0.0) {
    float t01 = clamp(c.y / CORE_H, 0.0, 1.0);
    float climb = pow(fract(c.y * 3.2 - gT * 0.4), 7.0);               // energy rising through it
    float seam = glow(c.x, 0.0015, px) * (1.2 + 2.0 * t01 + 2.6 * climb);
    float rim = exp(-max(hw - ax, 0.0) / 0.0011) * (0.2 + 0.25 * t01);
    // Fissures: light leaking through cracks in the slab, each breathing on its own phase.
    float fis = 0.0;
    for (int f = 0; f < 2; f++) {
      float side = f == 0 ? -1.0 : 1.0;
      float fx0 = side * hw * (0.3 + 0.12 * float(f)) + 0.0018 * (noise1(c.y * 90.0 + float(f) * 17.0) - 0.5);
      float run = smoothstep(0.2, 0.6, noise1(c.y * 14.0 + float(f) * 31.0));
      fis += glow(c.x - fx0, 0.0005, px) * run * (0.35 + 0.25 * sin(6.2831853 * (gT * 0.13 + float(f) * 0.37)));
    }
    float crownEdge = exp(-max(roof - c.y, 0.0) / 0.0016) * 0.9;
    float grooves = lineCov(ax - 0.52 * hw, 0.0007, px) * (0.03 + 0.25 * climb);
    float ribs = lineCov(fract(c.y / 0.028 + 0.5) - 0.5, 0.0009 / 0.028, px / 0.028) * (0.015 + 0.3 * climb) * (1.0 - ax / hw);
    vec3 body = vec3(0.0019, 0.0021, 0.003) + gFog * 0.35 * t01;
    body += gCore * (seam + rim + crownEdge + grooves + ribs + fis);
    body += vec3(0.6) * seam * gI * 0.15;                              // white-hot centre
    body = mix(body, gFog * 1.3, 0.55 * exp(-c.y / 0.03));             // its foot is lost in haze
    col = mix(col, body, ccov);
  }
  float ra = length(vec2(c.x, c.y - CROWN));
  col += gCore * (glow(ra, 0.0025, px) * 4.0 + exp(-ra / 0.014) * 0.3) + vec3(1.0) * glow(ra, 0.001, px) * gI * 1.5;

  // The beam: clear air up to the deck, then only through its gaps.
  float by = p.y - CROWN;
  if (by > -0.004) {
    float bx = abs(p.x - gCoreX);
    float above = smoothstep(BEAM_Y - 0.05, BEAM_Y + 0.06, p.y);
    float vis = 1.0 - above + above * (1.0 - cov) * 0.12;
    float flow = 0.82 + 0.18 * sin(6.2831853 * (by * 7.0 - gT * 0.9));
    float att = exp(-by * 1.9) * smoothstep(-0.004, 0.006, by);
    col += gCore * (glow(bx, 0.0016, px) * 2.6 + exp(-bx / 0.011) * 0.22 + exp(-bx / 0.045) * 0.045) * att * flow * vis;
  }

  // Bolt: a forked channel from the strike point down to the horizon (only some strikes).
  if (uLight.w > 0.0 && L > 0.01 && y < uLight.z) {
    float k = 1.0 - y / uLight.z;
    float s = uBoltSeed;
    float xo = (noise1(y * 16.0 + s) - 0.5) * 0.08 + (noise1(y * 61.0 + s * 1.7) - 0.5) * 0.02 + (noise1(y * 190.0 + s * 2.3) - 0.5) * 0.006;
    float bx = p.x - uLight.y - xo * (0.35 + k);
    float bolt = glow(bx, 0.0006, px) * 6.0 + exp(-abs(bx) / 0.012) * 0.22;
    float fy = uLight.z * 0.58;
    if (y < fy) {
      float fk = (fy - y) / fy;
      float fx = bx - (fy - y) * 0.45 * (fract(s) > 0.5 ? 1.0 : -1.0) - (noise1(y * 45.0 + s * 3.1) - 0.5) * 0.025;
      bolt += glow(fx, 0.0005, px) * 3.5 * (1.0 - smoothstep(0.25, 0.7, fk));
    }
    col += BOLT * bolt * L * uLight.w * smoothstep(0.0, 0.15, k) * (1.0 - 0.6 * cov);
  }
  return col;
}

// ── tower layer (0 far, 1 near) at layer-space point q (q.y measured up from its waterline) ──
// Returns premultiplied radiance + coverage. Two interleaved cell grids, grid 0 in front.
vec4 towers(int layer, vec2 q, float px, float coreLX) {
  bool nearL = layer == 1;
  vec4 S = TW_SHAPE[layer];
  vec4 W = TW_WIN[layer];
  float rimFall = nearL ? 2.4 : 5.0;
  float reach = nearL ? 0.09 : 0.04;   // ruin slope + antenna + beacon glow above a roof
  vec3 acc = vec3(0.0);
  float alpha = 0.0;
  for (int g = 0; g < 2; g++) {
    float cell = g == 0 ? S.x : S.y;
    float seed = float(layer * 2 + g) * 101.0 + 7.0;
    float gx = q.x / cell + float(g) * 0.43;
    float ci = floor(gx);
    float fx = gx - ci;
    // Height envelope, sampled once per cell so roofs stay flat.
    float cx0 = (ci + 0.5 - float(g) * 0.43) * cell;
    float env;
    if (nearL) {
      env = mix(0.4, 1.0, smoothstep(0.16, 0.5, abs(cx0 / gAspect + 0.04)));   // tall wings frame the shot
      env *= 1.0 - 0.6 * exp(-sq((cx0 - coreLX) / 0.15));                     // valley that reveals the Core
    } else {
      env = 1.0 - 0.4 * exp(-sq((cx0 - coreLX) / 0.07));
    }
    float district = smoothstep(0.2, 0.85, noise1(cx0 * (nearL ? 2.2 : 4.5) + float(layer) * 9.0));
    env *= nearL ? 0.75 + 0.45 * district : 0.45 + district;   // districts
    if (q.y > S.w * env + reach) continue;   // above anything this cell can hold: no hashing
    vec4 h = hash42(vec2(ci, seed));
    vec4 k = hash42(vec2(ci, seed + 57.0));
    float a = 0.03 + 0.28 * h.x;
    float b = 0.97 - 0.28 * h.y;
    float w = (b - a) * cell;
    float u = (fx - a) * cell;
    float H = mix(S.z, S.w, nearL ? h.z * h.z : h.z * h.z * h.z) * env * (k.w < 0.1 ? 0.3 : 1.0);
    float inset = k.x > 0.45 ? (0.1 + 0.2 * k.y) * w : 0.0;
    float H1 = inset > 0.0 ? H * (0.55 + 0.3 * k.z) : H;
    float ruin = step(0.6, h.w);
    float uw = u - inset;
    float ww = w - 2.0 * inset;
    float top = H + ruin * ((k.y - 0.5) * 1.3 * (uw - 0.5 * ww) - (nearL ? 0.007 : 0.0035) * noise1(q.x * 260.0 + seed));
    float d = max(min(min(u, w - u), H1 - q.y), min(min(uw, ww - uw), top - q.y));
    float ant = step(0.58, k.w) * (1.0 - ruin);
    float ax = inset + ww * (0.3 + 0.4 * h.x);
    float aTop = top + (nearL ? 0.018 + 0.035 * h.y : 0.007 + 0.014 * h.y);
    float acov = ant * lineCov(u - ax, nearL ? 0.0011 : 0.0006, px) * clamp((aTop - q.y) / px + 0.5, 0.0, 1.0);
    float cov = max(clamp(d / px + 0.5, 0.0, 1.0), acov) * clamp(q.y / px + 0.5, 0.0, 1.0);

    float centre = (ci - float(g) * 0.43 + 0.5 * (a + b)) * cell;
    float toCore = abs(centre - coreLX);
    vec3 col = TW_BASE[layer];
    if (cov > 0.0) {
      // The flash catches the upper facades.
      col += BOLT * uLight.x * (nearL ? 0.012 : 0.02) * (0.3 + 0.7 * clamp(q.y / max(H, 1e-3), 0.0, 1.0));
      float face = centre < coreLX ? w - u : u;
      col += gCore * exp(-max(face, 0.0) / (nearL ? 0.0017 : 0.0011)) * exp(-toCore * rimFall) * (nearL ? 0.3 : 0.16);
      col += gFog * 0.45 * exp(-max(top - q.y, 0.0) / 0.0014);   // roof edges catch the haze

      // Windows: sparse, clustered on powered floors, re-rolled on a slow per-window cycle.
      vec2 wc = vec2(u, q.y) / W.xy;
      vec2 wi = floor(wc);
      vec2 wf = wc - wi;
      vec4 wh = hash42(vec2(wi.x + ci * 61.0, wi.y + seed * 3.0));
      float powered = hash21(vec2(ci * 13.0 + seed, wi.y + floor(gT * 0.01 + h.z)));
      float prob = W.z * (powered < 0.22 ? 4.0 : 0.35);
      prob += uVictory * 0.18 * smoothstep(0.0, 0.25, uVictory * 1.9 - toCore * 1.3);   // power returns from the Core outward
      float cyc = floor(gT * (0.02 + 0.02 * floor(wh.w * 2.0)) + wh.z);
      float lit = step(hash21(vec2(wh.x * 8192.0, cyc)), prob);
      float tube = wh.y < 0.2 ? 0.2 + 0.8 * step(0.28, hash21(vec2(wh.x * 977.0, floor(gT * 12.0)))) : 1.0;
      vec2 hs = nearL ? vec2(0.24, 0.12) : vec2(0.26, 0.17);
      vec2 wfw = px / W.xy;
      vec2 m2 = clamp((hs - abs(wf - 0.5)) / wfw + 0.5, 0.0, 1.0);
      float mask = mix(m2.x * m2.y, 4.0 * hs.x * hs.y, smoothstep(0.35, 0.9, max(wfw.x, wfw.y)));
      float bodyIn = clamp((min(d, q.y - 0.006) - 0.5 * W.x) / px, 0.0, 1.0);
      vec3 wcol = wh.z < 0.22 ? AMBER : mix(gMood, vec3(dot(gMood, LUMA)), 0.12);
      col += wcol * (lit * tube * mask * bodyIn * W.w * gI);

      // Dead neon: a failing vertical strip down one edge of a few near towers.
      if (nearL && k.z > 0.8) {
        float sx = w * (k.z > 0.9 ? 0.1 : 0.9);
        float y0 = H1 * (0.2 + 0.2 * h.y);
        float y1 = H1 * (0.55 + 0.3 * h.x);
        float strip = lineCov(u - sx, 0.0014, px) * clamp((q.y - y0) / px, 0.0, 1.0) * clamp((y1 - q.y) / px, 0.0, 1.0);
        float buzz = 0.15 + 0.85 * step(0.1, hash21(vec2(ci + seed, floor(gT * 9.0))));
        col += (fract(k.z * 37.0) < 0.3 ? AMBER : gMood) * strip * buzz * 0.8 * gI;
      }

      float fogK = nearL ? 0.06 + 0.6 * exp(-q.y / 0.016) : 0.48 + 0.45 * exp(-q.y / 0.028);
      col = mix(col, gFog * (nearL ? 0.75 : 1.35), fogK);
    }
    vec3 rad = col * cov;
    // Aviation beacon on intact antennas: a slow red blink that glows past the silhouette.
    if (ant > 0.0 && k.z < (nearL ? 0.6 : 0.25)) {
      float blink = pow(max(sin(6.2831853 * (gT * 0.4 + h.z)), 0.0), 20.0);
      rad += BEACON * glow(length(vec2(u - ax, q.y - aTop)), 0.0011, px) * blink * (nearL ? 2.2 : 1.1);
    }
    acc += (1.0 - alpha) * rad;
    alpha += (1.0 - alpha) * cov;
  }
  return vec4(acc, alpha);
}

// Rain-ripple rings on the water plane (plane units); returns the surface slope.
vec2 ripples(vec2 P, float fz) {
  vec2 n = vec2(0.0);
  for (int g = 0; g < 2; g++) {
    float cs = g == 0 ? 0.05 : 0.032;
    vec2 Q = P / cs + float(g) * vec2(0.37, 0.71);
    vec2 ci = floor(Q);
    float ph = gT * (g == 0 ? 0.9 : 1.3) + hash21(ci + float(g) * 91.0);
    float age = fract(ph);
    vec4 h2 = hash42(ci * 1.7 + floor(ph) + float(g) * 13.0);
    vec2 dv = Q - ci - (0.3 + 0.4 * h2.xy);
    float r = length(dv);
    float x = (r - age * 0.3) / 0.045;
    float amp = sq(1.0 - age) * step(h2.z, 0.7);
    n += dv / max(r, 1e-3) * (-2.0 * x * exp(-x * x)) * amp;
  }
  return n * (1.0 - smoothstep(0.1, 0.35, fz / 0.032));
}

vec3 rain(vec2 p, int i, float px) {
  vec4 R = RAIN[i];
  vec3 K = RAIN_K[i];
  vec2 q = p;
  q.x += uCam.x * K.y - q.y * 0.17;   // parallax + slant
  float cx = q.x * R.x;
  float ci = floor(cx);
  float ry = q.y * R.x * K.z + gT * R.y + hash21(vec2(ci, float(i) * 31.0)) * 13.0;
  float ri = floor(ry);
  vec4 g = hash42(vec2(ci * 3.0 + float(i), ri));
  if (g.x > K.x) return vec3(0.0);
  float s = (ry - ri - g.w * 0.6) / (0.18 + 0.2 * g.z);  // 0 at the head (bottom), 1 at the tail
  float along = smoothstep(0.0, 0.08, s) * (1.0 - smoothstep(0.2, 1.0, s));
  float cov = lineCov((cx - ci - 0.2 - 0.6 * g.y) / R.x, R.z, px);
  vec3 lit = gFog * 1.6 + gMood * gI * 0.012 + BOLT * uLight.x * 0.07;
  lit *= 1.0 + 2.5 * exp(-length(p - vec2(gCoreX, CROWN * 0.6)) / 0.2);
  return lit * cov * along * R.w;
}

vec3 scene(vec2 uv) {
  vec2 p = vec2((uv.x - 0.5) * gAspect, uv.y - HORIZON);
  vec2 pivot = vec2(gCoreX, CROWN * 0.55);
  p = pivot + (p - pivot) / uCam.z;           // cinematic dolly toward the Core
  // Parallax: content moves against the pointer (camera.y is +down), near layers the most.
  p.y -= uCam.y * 0.01;
  p.x += uCam.w;
  float px = gPx;
  float nearBase = NEAR_BASE + uCam.y * 0.006;
  bool water = p.y < 0.0;

  vec2 off = vec2(0.0);
  float F = 0.0;
  float rip = 0.0;
  vec2 P = vec2(0.0);
  float Z = 1.0;
  if (water) {
    float dy = max(-p.y, 1e-4);
    Z = WATER_H / dy;
    P = vec2((p.x - gCoreX) * Z, Z);
    float fz = px * WATER_H / (dy * dy);
    vec2 n = ripples(P, fz);
    rip = dot(n, n);
    float swellFade = 1.0 - smoothstep(0.02, 0.12, fz);
    float s1 = vnoise(vec2(P.x * 7.0, P.y * 1.6 + uDrift.z)) - 0.5;
    float s2 = vnoise(vec2(P.x * 17.0 + 7.0, P.y * 3.7 - uDrift.z * 1.3)) - 0.5;
    off = n * vec2(0.008, 0.014) + vec2(s1 * 0.004 + s2 * 0.002, (s1 + 0.6 * s2) * 0.016) * swellFade;
    off *= smoothstep(0.0, 0.03, dy);
    float st = dy / sqrt(dy * dy + 1.6);
    F = 0.02 + 0.98 * pow(1.0 - st, 5.0);
  }

  // Towers first — far + near direct, then far + near mirrored about their own waterlines —
  // so the sky and the water are only evaluated where something of them shows through.
  vec4 tw[4];
  for (int i = 0; i < 4; i++) {
    tw[i] = vec4(0.0);
    int layer = i & 1;
    float base = layer == 0 ? FAR_BASE : nearBase;
    float par = layer == 0 ? 0.012 : 0.032;
    float lx = p.x + uCam.x * par;
    float coreLX = gCoreX + uCam.x * par;
    if (i < 2) {
      if (p.y > base - px) tw[i] = towers(layer, vec2(lx, p.y - base), px, coreLX);
    } else if (water && p.y < base && max(tw[0].a, tw[1].a) < 1.0) {
      float depth = base - p.y;
      tw[i] = towers(layer, vec2(lx + off.x, depth + off.y), px + depth * 0.035, coreLX);
    }
  }

  vec3 col = vec3(0.0);
  if (max(tw[0].a, tw[1].a) < 1.0) {
    float reflVis = water ? (1.0 - tw[2].a) * (1.0 - tw[3].a) : 1.0;
    if (reflVis > 0.0) col = sky(water ? vec2(p.x + off.x, max(off.y - p.y, 0.0)) : p, water, water ? px * 1.5 - p.y * 0.02 : px);
    if (water) {
      vec3 refl = col;
      refl = refl * (1.0 - tw[2].a) + tw[2].rgb;
      refl = refl * (1.0 - tw[3].a) + tw[3].rgb;
      col = gFog * 0.05 + vec3(0.0004, 0.0005, 0.0008) + refl * F;

      // Submerged data-lines converging on the Core, packets flowing toward the horizon.
      float sp = 0.05;
      float lx = (P.x + off.x * Z * 0.6) / sp;
      float li = floor(lx + 0.5);
      float hl = hash11(li + 17.0);
      if (hl < 0.3) {
        float kk = inversesqrt(1.0 + sq(li * sp / WATER_H));   // horizontal → perpendicular distance
        float dS = abs(lx - li) * sp / Z * kk;
        float wS = 0.0016 / Z;
        float fade = smoothstep(px * 6.0, px * 26.0, sp / Z * kk) * smoothstep(0.25, 0.9, Z);
        float line = glow(dS, wS, px) + exp(-dS / (wS * 6.0)) * 0.06;
        float s = fract(Z * 0.2 - gT * (0.12 + 0.05 * floor(hl * 7.5)) + hl * 9.0);
        float pk = pow(s, 9.0) * (1.0 - smoothstep(0.965, 1.0, s));
        col += gMood * gI * fade * line * (0.012 + 0.55 * pk) * (1.0 + 1.4 * uVictory);
      }
      col += gFog * 0.6 * exp(p.y / 0.014);   // haze lying on the water at the horizon
      // Ripple crests catch the haze, and the Core's light along its reflection column.
      float coreCol = exp(-abs(p.x - gCoreX) / 0.09);
      col += (gFog * 3.5 + gCore * 0.35 * coreCol) * min(rip, 2.0) * 0.5;
    }
  }

  col = col * (1.0 - tw[0].a) + tw[0].rgb;
  for (int i = 0; i < 3; i++) {
    if (i == 1) {
      col = col * (1.0 - tw[1].a) + tw[1].rgb;
      float mist = 0.55 + 0.45 * vnoise(vec2(p.x * 7.0 + uDrift.w, p.y * 30.0));
      col += gFog * 0.32 * mist * exp(-sq((p.y - nearBase) / 0.014));   // mist hugging the near waterline
    }
    col += rain(p, i, px);
  }
  return col;
}

void main() {
  // Pixel footprint from the affine uv: exact at any render scale, taken before any branch.
  vec2 duv = vec2(abs(dFdx(vUv.x)), abs(dFdy(vUv.y)));
  gAspect = duv.y / max(duv.x, 1e-7);
  gPx = duv.y / uCam.z;
  gT = uTime.x;
  gI = uMoodK.x;
  gMood = uMood;
  gCoreX = 0.145 * gAspect - uCam.x * 0.006;

  float alarm = uMoodK.y * uTime.y;
  gAlarm = uMoodK.y;
  vec3 tint = mix(vec3(0.42, 0.5, 0.66), uMood / max(max(uMood.r, max(uMood.g, uMood.b)), 1e-3), 0.36);
  gFog = tint * (0.007 + 0.006 * gI) + BLOOD * alarm * 0.016 + ACID * uVictory * 0.004;
  gCore = mix(uMood, BLOOD, alarm * 0.35) * gI * (1.0 + 0.9 * alarm);

  // Corruption: glitch bands (with an RGB split) and block displacement, in bursts.
  vec2 uv = vUv;
  float split = 0.0;
  float corr = uMoodK.z;
  float st = uTime.w;
  // A glitch step (14 Hz) fires with probability ~corruption², in bursts: calm glitches every
  // few seconds, alarm almost constantly. The branch is uniform across the frame.
  if (corr > 0.002 && hash11(st + 7919.0) < clamp(corr * corr * 2.2 + corr * 0.1, 0.0, 1.0) * uTime.z) {
    float rows = 22.0 + floor(hash11(st) * 60.0);
    vec4 hb = hash42(vec2(floor(uv.y * rows), st));
    float band = step(hb.x, 0.04 + 0.2 * corr);
    uv.x += band * (hb.y - 0.5) * (0.03 + 0.1 * corr);
    split = band * (0.002 + 0.008 * hb.z) * (0.4 + corr);
    vec2 cell = floor(uv * vec2(16.0, 9.0));
    vec4 hk = hash42(cell + st * 13.0);
    float blk = step(hk.x, corr * 0.06);
    uv += blk * (floor(hk.yz * 5.0) - 2.0) * vec2(0.03125, 0.0556);
  }
  vec3 col = vec3(0.0);
  int passes = split > 0.0 ? 2 : 1;
  for (int i = 0; i < passes; i++) {
    vec3 c = scene(uv + vec2(split * float(i), 0.0));
    if (i == 0) col = c; else col.r = c.r;
  }
  if (split > 0.0) col += gMood * 0.01;

  // Cinematic grade: contrast about mid-grey (linear).
  col = max(col, 0.0);
  col = 0.18 * pow(col / 0.18, vec3(1.0 + 0.2 * uMoodK.w));
  outColor = vec4(min(col, vec3(64.0)), 1.0);
}
`;

export class World {
  /** Called at the start of every strike (the renderer forwards it as bus `world:lightning`). */
  onStrike = null;
  /** Lightning envelope 0..1 (copied into `frame.lightning` by the renderer). */
  lightning = 0;
  /**
   * The current/last strike, mutated in place: `x` in -1..1 across the screen (for panning
   * thunder), `power` 0..1. Read-only for consumers.
   */
  strikeInfo = { x: 0, power: 0 };

  #gl;
  #program = null;
  #u = null;

  // lightning scheduler (sim time)
  #next = rand(STRIKE_MIN, 12);
  #age = -1; // seconds since the current strike started; < 0 = idle
  #end = 0;
  #count = 0;
  #start = new Float32Array(MAX_FLASHES);
  #amp = new Float32Array(MAX_FLASHES);
  #decay = new Float32Array(MAX_FLASHES);
  #attack = 0.02;
  #glow = 0.12;
  #sx = 0;
  #sy = 0.3;
  #bolt = 0;
  #seed = 0;

  // presentation
  #dolly = 0;
  #sweep = 0;
  #lastTime = -1;

  constructor(gl) {
    this.#gl = gl;
    this.#program = createProgram(gl, FULLSCREEN_VS, FS, 'world');
    this.#u = uniforms(gl, this.#program);
  }

  /** Fixed sim step: drives the lightning scheduler. */
  update(dt) {
    if (!(dt > 0)) return;
    this.#next -= dt;
    if (this.#next <= 0) this.strike();
    if (this.#age < 0) return;

    const age = (this.#age += dt);
    if (age > this.#end) {
      this.#age = -1;
      this.lightning = 0;
      return;
    }
    let v = 0;
    for (let i = 0; i < this.#count; i++) {
      const t = age - this.#start[i];
      if (t <= 0) continue;
      const a = this.#attack;
      const e = t < a ? 1 - (1 - t / a) * (1 - t / a) : Math.exp(-(t - a) / this.#decay[i]);
      const f = this.#amp[i] * e;
      if (f > v) v = f;
    }
    // Afterglow: the deck keeps a dull glow for a moment after the last flicker.
    const tail = this.#glow * Math.exp(-age / 0.7) * (age < 0.03 ? age / 0.03 : 1);
    this.lightning = v > tail ? v : tail;
  }

  /**
   * Starts a strike now (the scheduler calls this; screens may force one for drama).
   * @param {number} power 0..1
   */
  strike(power = 1) {
    const reduced = !!settings.get('reducedMotion');
    power = Math.min(Math.max(+power || 0, 0), 1);
    this.#next = rand(STRIKE_MIN, STRIKE_MAX);
    this.#age = 0;
    if (reduced) {
      // One slow swell: no rapid flicker, no bolt.
      this.#count = 1;
      this.#start[0] = 0;
      this.#amp[0] = 0.45 * power;
      this.#decay[0] = 0.8;
      this.#attack = 0.25;
      this.#glow = 0;
      this.#bolt = 0;
      this.#end = 4;
    } else {
      const n = Math.random() < 0.55 ? 2 : 3;
      let t = 0;
      for (let i = 0; i < n; i++) {
        this.#start[i] = t;
        this.#amp[i] = power * (i === 0 ? rand(0.7, 1) : rand(0.45, 1));
        this.#decay[i] = rand(0.05, 0.12);
        t += rand(0.06, 0.16) + this.#decay[i];
      }
      this.#count = n;
      this.#attack = 0.02;
      this.#glow = 0.14 * power;
      this.#bolt = Math.random() < 0.4 ? 1 : 0;
      this.#end = t + 3;
    }
    // x normalised across the screen (converted to scene units at render), y in scene units
    // above the horizon (inside the cloud deck).
    this.#sx = Math.random() < 0.3 ? rand(0.04, 0.26) : rand(0.52, 0.96);
    this.#sy = rand(0.27, 0.5);
    this.#seed = rand(0, 512);
    this.strikeInfo.x = this.#sx * 2 - 1;
    this.strikeInfo.power = power;
    this.onStrike?.();
  }

  /** Draws the world into the bound target (viewport already set). No allocations. */
  render(gl, frame) {
    const program = this.#program;
    if (!program) return;
    const u = this.#u;
    const mood = frame.mood;
    const cam = frame.camera;
    const time = +frame.time || 0;

    // Unbounded drifts, closed-form in sim time (double precision until the uniform upload):
    // wind speed 0.75 + 0.5·sin(at)·sin(bt + c), integrated analytically, so gusts are smooth,
    // deterministic and immune to hitches.
    const wind = 0.75 * time + 0.25 * (Math.sin(GUST_A_MINUS_B * time - GUST_C) / GUST_A_MINUS_B - Math.sin(GUST_A_PLUS_B * time + GUST_C) / GUST_A_PLUS_B);

    // Cinematic dolly: eases in for as long as the mood holds, eases back out after.
    const rdt = frame.dt > 0 ? Math.min(frame.dt, 0.1) : 0;
    const cin = mood.cinematic;
    if (cin > 0.001) this.#dolly += rdt * cin;
    else this.#dolly = damp(this.#dolly, 0, 0.6, rdt);
    const zoom = 1 + 0.16 * cin * (1 - Math.exp(-this.#dolly / 12));
    const reduced = settings.get('reducedMotion');
    const sway = reduced ? 0 : 0.0035 * Math.sin(time * 0.11) + 0.002 * Math.sin(time * 0.047 + 2);

    // WATCHDOG's searchlights: the sweep phase integrates sim time, so the alarm can speed
    // it up without a jump; they go dark on victory.
    let sdt = this.#lastTime < 0 ? 0 : time - this.#lastTime;
    if (!(sdt > 0) || sdt > 0.25) sdt = 0;
    this.#lastTime = time;
    this.#sweep += sdt * 0.13 * (1 + 2.4 * mood.alarm);
    const sweep = this.#sweep;

    // Glitch bursts: corruption comes and goes instead of buzzing constantly. Reduced motion
    // keeps the look but glitches less often and pulses the alarm shallower.
    const burst = (0.35 + 0.65 * Math.min(1, Math.max(0, Math.sin(time * 0.53) * Math.sin(time * 0.29 + 0.7) * 1.6))) * (reduced ? 0.4 : 1);
    const tw = time % TIME_WRAP;
    const pulse = Math.pow(0.5 + 0.5 * Math.sin(tw * Math.PI * 2 * 1.6), 3) * (reduced ? 0.35 : 1);

    gl.useProgram(program);
    gl.uniform4f(u.uTime, tw, pulse, burst, Math.floor(tw * 14));
    gl.uniform4f(u.uDrift, wind * 0.016, -wind * 0.006, time * 0.32, time * 0.05);
    const c = mood.color;
    gl.uniform3f(u.uMood, c[0], c[1], c[2]);
    gl.uniform4f(u.uMoodK, mood.intensity, mood.alarm, mood.corruption, cin);
    gl.uniform1f(u.uVictory, mood.victory);

    const aspect = frame.width > 0 && frame.height > 0 ? frame.width / frame.height : 16 / 9;
    const light = frame.lightning ?? this.lightning;
    gl.uniform4f(u.uLight, +light || 0, (this.#sx - 0.5) * aspect, this.#sy, this.#bolt);
    gl.uniform1f(u.uBoltSeed, this.#seed);
    gl.uniform4f(u.uCam, cam.x || 0, cam.y || 0, zoom, sway);
    const aL = 0.32 + 0.4 * Math.sin(sweep);
    const aR = -0.34 + 0.4 * Math.sin(sweep * 0.83 + 2.4);
    gl.uniform4f(u.uSweep, Math.sin(aL), Math.cos(aL), Math.sin(aR), Math.cos(aR));
    gl.uniform1f(u.uSweepK, (0.7 + 0.9 * mood.alarm) * (1 - mood.victory));

    drawFullscreen(gl);
  }

  dispose() {
    if (this.#program) this.#gl.deleteProgram(this.#program);
    this.#program = null;
    this.#u = null;
    this.onStrike = null;
  }
}
