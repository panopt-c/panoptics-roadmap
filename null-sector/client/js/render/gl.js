/**
 * gl.js — the thin WebGL2 layer every render module builds on.
 *
 * Deliberately not an abstraction: these are the five things that are tedious and
 * error-prone to repeat (programs, uniforms, render targets, the fullscreen pass,
 * capability probing), done once and done carefully.
 *
 *  - createProgram() links first and only interrogates individual shaders when the
 *    link fails, so a healthy boot never forces a synchronous compile stall per shader.
 *    On failure it throws an Error carrying the driver log *and* the line-numbered
 *    source with the offending lines marked `>>` — the message you want at 2 a.m.
 *  - Render targets are a texture + FBO pair. HDR targets are RGBA16F when
 *    EXT_color_buffer_float is available (practically universal on WebGL2), otherwise
 *    RGBA8 — and the target's `hdr` flag reports what was actually allocated.
 *  - FULLSCREEN_VS draws one oversized triangle from gl_VertexID: no buffers, no
 *    attributes, no diagonal seam, ~10% cheaper than a quad on tiled GPUs.
 *
 * Per-context caches (extension probes, the empty VAO) are keyed by the context and
 * dropped automatically on `webglcontextlost`, so everything re-probes cleanly after a
 * restore (extensions must be re-enabled on a restored context).
 */

const capsCache = new WeakMap(); // gl → capabilities
const vaoCache = new WeakMap(); // gl → empty VAO for attribute-less draws
const tracked = new WeakSet(); // contexts whose canvas we listen to for loss

function track(gl) {
  if (tracked.has(gl)) return;
  tracked.add(gl);
  const canvas = gl.canvas;
  if (canvas && typeof canvas.addEventListener === 'function') {
    canvas.addEventListener('webglcontextlost', () => {
      capsCache.delete(gl);
      vaoCache.delete(gl);
    });
  }
}

/**
 * Probes (and enables) the extensions the pipeline cares about. Cached per context.
 * @returns {{colorBufferFloat: boolean, floatBlend: boolean, maxTextureSize: number}}
 */
export function capabilities(gl) {
  let caps = capsCache.get(gl);
  if (!caps) {
    track(gl);
    caps = {
      colorBufferFloat: !!gl.getExtension('EXT_color_buffer_float'),
      floatBlend: !!gl.getExtension('EXT_float_blend'),
      maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE) || 4096,
    };
    capsCache.set(gl, caps);
  }
  return caps;
}

// ── programs ─────────────────────────────────────────────────────────────

/** Source with 1-based line numbers; lines the driver complained about are marked `>>`. */
function annotate(source, log) {
  const bad = new Set();
  for (const m of log.matchAll(/(?:ERROR|WARNING):\s*\d+:(\d+)/g)) bad.add(Number(m[1]));
  const lines = source.split('\n');
  const width = String(lines.length).length;
  return lines
    .map((line, i) => `${bad.has(i + 1) ? '>>' : '  '} ${String(i + 1).padStart(width)} | ${line}`)
    .join('\n');
}

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  return shader;
}

function shaderFailure(gl, shader, source, kind, label) {
  if (gl.getShaderParameter(shader, gl.COMPILE_STATUS)) return null;
  const log = (gl.getShaderInfoLog(shader) || '(no info log)').trim();
  return `[gl] ${label}: ${kind} shader failed to compile\n${log}\n\n${annotate(source, log)}`;
}

/**
 * Compiles + links a program. Throws an Error with the info log and numbered source on
 * failure (or a short "context lost" error if the context died mid-build).
 */
export function createProgram(gl, vs, fs, label = 'program') {
  const vsh = compile(gl, gl.VERTEX_SHADER, vs);
  const fsh = compile(gl, gl.FRAGMENT_SHADER, fs);
  const program = gl.createProgram();
  gl.attachShader(program, vsh);
  gl.attachShader(program, fsh);
  gl.linkProgram(program);

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const message = gl.isContextLost()
      ? `[gl] ${label}: WebGL context lost while building program`
      : shaderFailure(gl, vsh, vs, 'vertex', label) ||
        shaderFailure(gl, fsh, fs, 'fragment', label) ||
        `[gl] ${label}: program failed to link\n${(gl.getProgramInfoLog(program) || '').trim()}`;
    gl.deleteProgram(program);
    gl.deleteShader(vsh);
    gl.deleteShader(fsh);
    throw new Error(message);
  }

  // The linked program keeps its own copy; free the shader objects now.
  gl.detachShader(program, vsh);
  gl.detachShader(program, fsh);
  gl.deleteShader(vsh);
  gl.deleteShader(fsh);
  return program;
}

/**
 * Every active uniform → location, looked up once. Array uniforms are reachable both as
 * `name[0]` and `name`. Uniforms the compiler optimised away are simply absent (passing
 * `undefined` to gl.uniform* is a silent no-op, so callers need no guards).
 */
export function uniforms(gl, program) {
  const out = {};
  const count = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS) || 0;
  for (let i = 0; i < count; i++) {
    const info = gl.getActiveUniform(program, i);
    if (!info) continue;
    const location = gl.getUniformLocation(program, info.name);
    out[info.name] = location;
    if (info.name.endsWith('[0]')) out[info.name.slice(0, -3)] = location;
  }
  return out;
}

// ── render targets ───────────────────────────────────────────────────────

function allocate(gl, target, w, h) {
  target.w = w;
  target.h = h;
  gl.bindTexture(gl.TEXTURE_2D, target.tex);
  if (target.hdr) gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
  else gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
}

const clampSize = (gl, n) => Math.max(1, Math.min(capabilities(gl).maxTextureSize, Math.round(n) || 1));

/**
 * Colour texture + framebuffer. `filter` applies to both min and mag (no mips).
 * @returns {{fbo: WebGLFramebuffer, tex: WebGLTexture, w: number, h: number, hdr: boolean}}
 */
export function createTarget(gl, w, h, { hdr = false, filter = gl.LINEAR } = {}) {
  const target = {
    fbo: gl.createFramebuffer(),
    tex: gl.createTexture(),
    w: 0,
    h: 0,
    hdr: hdr && capabilities(gl).colorBufferFloat,
  };
  gl.bindTexture(gl.TEXTURE_2D, target.tex);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  allocate(gl, target, clampSize(gl, w), clampSize(gl, h));

  gl.bindFramebuffer(gl.FRAMEBUFFER, target.fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, target.tex, 0);
  let status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
  if (status !== gl.FRAMEBUFFER_COMPLETE && target.hdr && !gl.isContextLost()) {
    // A driver that advertises float rendering but rejects this format: degrade to LDR.
    target.hdr = false;
    allocate(gl, target, target.w, target.h);
    status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
  }
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.bindTexture(gl.TEXTURE_2D, null);
  if (status !== gl.FRAMEBUFFER_COMPLETE && !gl.isContextLost()) {
    deleteTarget(gl, target);
    throw new Error(`[gl] render target ${w}x${h} incomplete (status 0x${status.toString(16)})`);
  }
  return target;
}

/** Reallocates storage if the size changed. Returns true when it did. Contents are undefined after. */
export function resizeTarget(gl, target, w, h) {
  w = clampSize(gl, w);
  h = clampSize(gl, h);
  if (target.w === w && target.h === h) return false;
  allocate(gl, target, w, h);
  gl.bindTexture(gl.TEXTURE_2D, null);
  return true;
}

export function deleteTarget(gl, target) {
  if (!target) return;
  gl.deleteFramebuffer(target.fbo);
  gl.deleteTexture(target.tex);
  target.fbo = null;
  target.tex = null;
}

// ── fullscreen pass ──────────────────────────────────────────────────────

/**
 * Attribute-less fullscreen vertex shader: one triangle covering the viewport,
 * outputs `vUv` (0..1 across the viewport). Draw with drawFullscreen(gl).
 */
export const FULLSCREEN_VS = `#version 300 es
out vec2 vUv;
void main() {
  // gl_VertexID 0,1,2 -> uv (0,0) (2,0) (0,2): a triangle whose inner corner is the viewport.
  vec2 p = vec2(float((gl_VertexID & 1) << 1), float(gl_VertexID & 2));
  vUv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
`;

/**
 * Draws FULLSCREEN_VS with the currently bound program. Binds an empty VAO for the draw
 * and restores the default VAO afterwards, so it never disturbs another module's
 * attribute state.
 */
export function drawFullscreen(gl) {
  let vao = vaoCache.get(gl);
  if (!vao) {
    track(gl);
    vao = gl.createVertexArray();
    vaoCache.set(gl, vao);
  }
  gl.bindVertexArray(vao);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  gl.bindVertexArray(null);
}
