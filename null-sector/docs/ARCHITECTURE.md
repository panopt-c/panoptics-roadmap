# NULL//SECTOR — Architecture & Contracts

This document is the single source of truth for how the game is put together.
Every module implements exactly the interface written here. If code and this
document disagree, the code is wrong.

---

## 1. Overview

```
┌─────────────────────────── Python (headless core) ───────────────────────────┐
│ levels/*.py ─► engine/mission.py      engine/state.py (config.json, save.json)│
│ engine/runner.py ─► engine/harness.py  (player code runs in a subprocess)     │
│ engine/session.py  GameSession: the ONLY place game rules live                 │
│      ▲                       ▲                                                │
│ engine/server.py (web)   engine/tui.py (Rich terminal, `python game.py tui`)  │
└──────┼───────────────────────────────────────────────────────────────────────┘
       │ HTTP JSON API + Server-Sent Events (127.0.0.1 only, token-protected)
┌──────┴──────────────────────── Browser client (client/) ─────────────────────┐
│ main.js ─ Loop (fixed 120 Hz sim + interpolated render)                       │
│   ├─ Renderer (WebGL2): World pass → HDR target → Particles → Post (bloom,    │
│   │                      tonemap, CA, grain, scanlines) → screen               │
│   ├─ Camera  (trauma shake, parallax springs) ── transforms #ui + GL composite│
│   ├─ AudioEngine (procedural Web Audio: buses, ambient bed, SFX voices)       │
│   ├─ FeedbackDirector: semantic events ─► shake / particles / audio / light   │
│   └─ ScreenManager: boot → hub → mission → victory → cutscene → hub           │
└──────────────────────────────────────────────────────────────────────────────┘
```

Design rules:

* **Rules live in one place.** XP, ranks, unlocks and grading happen in Python
  (`GameSession`). The client never computes a reward; it renders the server's verdict.
* **Gameplay emits meaning, not effects.** Screens emit `hack:layer`, never
  "shake 0.3". `fx/feedback.js` maps meaning to juice, so feel is tuned in one table.
* **Zero allocations in the frame loop.** Particles use a fixed struct-of-arrays
  pool; the frame-state object is reused; no closures are created per frame.
* **Degrade, never break.** No WebGL2 → CSS fallback background, game still playable.
  No audio → silent. No Higgsfield key → in-engine cutscene. Server down → reconnecting toast.

---

## 2. Directory layout

```
null-sector/
  game.py                    CLI entry: web (default) | tui | hack | watch | reset
  engine/
    session.py               GameSession — headless game core
    content.py               mission markdown → HTML (markdown-it-py + Pygments)
    server.py                ThreadingHTTPServer: static client, JSON API, SSE
    cinematics.py            CutsceneRenderer (headless Higgsfield) + Director (TUI)
    tui.py                   Rich terminal front end
    ui.py                    Rich widgets used by tui.py
    state.py mission.py harness.py runner.py errors.py
  levels/                    campaign + one module per level
  missions/                  the player's .py files
  cutscenes/                 generated media (git-ignored)
  client/
    index.html
    css/  tokens.css app.css editor.css mission.css victory.css cutscene.css
    js/
      main.js
      core/   bus.js loop.js math.js settings.js
      render/ gl.js renderer.js world.js particles.js post.js
      fx/     camera.js feedback.js
      audio/  audio.js
      ui/     api.js dom.js editor.js
      ui/screens/ boot.js hub.js mission.js victory.js cutscene.js settings.js
  tests/                     python -m unittest discover tests
```

All client JS is native ES modules (`<script type="module">`), no bundler, no
npm, no CDN scripts. The only external request is Google Fonts, with system fallbacks.

---

## 3. Backend

### 3.1 GameSession (`engine/session.py`)

Thread-safe (one `threading.RLock` around every public method). Owns `config`
(dict), `save` (`Save`), and mission lookup.

| method | returns |
|---|---|
| `snapshot()` | `State` payload (3.3) |
| `mission(id)` | `Mission` payload (3.3), read-only |
| `deploy(id)` | starts the par timer (first time only), writes starter file if missing, returns `Mission` payload |
| `write_source(id, text)` | `{"ok": true, "saved_at": float}` |
| `attack(id)` | `HackResult` payload (3.3); records attempt, grades, applies rewards on first clear |
| `reset(id)` | `{"source": str}` |
| `playable(id)` | bool — cleared levels and the current level are playable; nothing else |

Raises `SessionError(status: int, message: str)` for unknown/locked/encrypted missions (404/403),
and 503 when save.json is busy in another process for too long or cannot be written.
Replaying a cleared mission is allowed and grants no XP (`reward.replay = true`).

**Shared save (cross-process safety).** save.json is shared by every NULL//SECTOR process
(the web server, `game.py tui`, `hack`, `watch`). `Save` (`engine/state.py`) treats it like a
tiny database:

* Every public `GameSession` method first adopts changes another process wrote
  (`Save.refresh()`: a `stat` when nothing changed; a re-read *in place* otherwise, because the
  cutscene renderer and the TUI hold references to the same `Save`).
* Every mutation is a locked read-modify-write (`Save.transaction()`): an OS lock on the
  sidecar `save.json.lock` (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows), re-read,
  change, write. A clear made in the terminal is never overwritten by a stale web session,
  and "first clear" is decided against the file on disk, so two windows can never both pay out.
* The lock is held for milliseconds; it is never held while player code is graded.
* Writes are durable: temp file, `fsync`, `os.replace`, `fsync` of the folder.
* Top-level keys this version does not know are preserved on write.
* A damaged save.json (empty, not JSON, not an object) never stops a launch: it is moved aside
  as `save.json.corrupt-<YYYYmmdd-HHMMSS>` and the game starts fresh with a notice (printed by
  the TUI and the server). Damage found mid-session is repaired by writing back the progress
  held in memory. Fields with the wrong shape are reset individually, keeping the rest.
* The productivity tracker's SQLite work never runs under the session lock: it gets a copy of
  the campaign values it needs (`cleared`, `callsign`, `xp`).

### 3.2 Server (`engine/server.py`)

`serve(session, host="127.0.0.1", port=7777, open_browser=True)`. Stdlib
`ThreadingHTTPServer`; if the port is taken, try the next 20 ports.

Security model (the server can execute code, so this is not optional):

1. Binds `127.0.0.1` only.
2. Rejects any request whose `Host` header is not `127.0.0.1:<port>` or `localhost:<port>`
   (blocks DNS-rebinding).
3. A random per-launch token (`secrets.token_urlsafe(24)`) is injected into
   `index.html` as `<meta name="ns-token" content="...">` (replacing `{{NS_TOKEN}}`).
   Every `/api/*` request must carry it: header `X-NS-Token` (fetch) or query
   `?token=` (EventSource only). Custom headers force a CORS preflight that the
   server never approves, so other websites cannot forge requests.
4. Static files are resolved and must stay inside their root (no `..` traversal).
5. Request bodies are capped at 1 MB.
6. A body that is not valid JSON (bad UTF-8, malformed, integers too long to convert,
   absurd nesting) is a 400 `{"error": "body is not valid JSON"}`; no request input can
   produce a traceback or leak Python call signatures. Responses are encoded so that they
   can never fail (text that is not valid UTF-8 falls back to ASCII `\u` escapes).

### 3.3 HTTP API

All JSON. Errors: `{"error": "message"}` with a 4xx/5xx status.

| method & path | body | response |
|---|---|---|
| `GET /` | | `client/index.html` with the token injected |
| `GET /css/*`, `/js/*` | | static client files |
| `GET /cutscenes/<file>` | | generated media |
| `GET /api/state` | | `State` |
| `GET /api/missions/:id` | | `Mission` |
| `POST /api/missions/:id/deploy` | | `Mission` |
| `PUT /api/missions/:id/source` | `{"source": str}` | `{"ok": true, "saved_at": float}` |
| `POST /api/missions/:id/hack` | | `HackResult` |
| `POST /api/missions/:id/reset` | | `{"source": str}` |
| `POST /api/missions/:id/cutscene` | | `{"mission": id, "state": "queued"\|"done"\|"offline", "url"?: str, "reason"?: str}` |
| `GET /api/events?token=` | | SSE stream (3.4) |

`State`:
```json
{
  "profile": {"callsign": "Nyx", "xp": 150, "rank": "SCRIPT KIDDIE", "rank_floor": 100,
              "rank_next": 400, "breaches": 1, "total_levels": 25},
  "campaign": [{"tier": 0, "name": "ZERO", "zone": "The Dead Zone", "color": "#39ff14",
                "levels": [{"id": "L01", "title": "COLD BOOT", "concept": "Variables & data types",
                            "status": "cleared|current|encrypted|locked", "boss": false}]}],
  "current": "L02",
  "higgsfield": {"online": false, "reason": "no API key in config.json"},
  "gallery": [{"mission": "L01", "title": "IDENTITY ACCEPTED", "url": "/cutscenes/L01_still.png", "kind": "image|video"}]
}
```
`status`: `cleared` (beaten) · `current` (the next level, built) · `encrypted` (the next level, not built yet) · `locked` (later).
`rank_next` is `null` at max rank. `callsign` is `""` until Level 1 registers it.

`Mission`:
```json
{
  "id": "L01", "title": "COLD BOOT", "concept": "Variables & data types",
  "tier": 0, "sector": {"name": "ZERO", "zone": "The Dead Zone", "color": "#39ff14"},
  "enemy": "WATCHDOG.exe", "enemy_art": "multi-line string", "xp": 100, "par_seconds": 900,
  "briefing_html": "<p>…</p>", "why_html": "…", "manual_html": "…",
  "objectives": ["Register identity — `callsign`", "…"],
  "file": "missions/level_01_cold_boot.py", "source": "…file text…",
  "attempts": 0, "elapsed": 12.4, "cleared": false,
  "cutscene": {"title": "IDENTITY ACCEPTED", "narration": ["…"]}
}
```
Markdown HTML: inline code → `<code>`; fenced python → `<pre class="code"><code>` with
Pygments spans using class prefix `tk-` (e.g. `tk-k` keyword, `tk-s2` string, `tk-c1` comment,
`tk-mi` int, `tk-mf` float, `tk-nb` builtin, `tk-o` operator). Raw HTML in markdown is escaped.
Objective names keep their backticks; the client renders `` `x` `` as `<code>x</code>`.

`HackResult`:
```json
{
  "report": {
    "status": "ok|crash|syntax_error|timeout|harness_error",
    "checks": [{"name": "…", "passed": true, "message": "", "hint": ""}],
    "stdout": "…",
    "error": {"type": "TypeError", "message": "…", "line": 45, "code": "…",
              "traceback": "…", "decoded": "plain-English explanation"}
  },
  "attempt": 3,
  "victory": true,
  "reward": {"lines": [{"label": "BASE XP", "amount": 100}, {"label": "SPEED BONUS", "amount": 50}],
             "gained": 150, "rank_before": "GHOST PROCESS", "rank_after": "SCRIPT KIDDIE",
             "rank_up": true, "breach_seconds": 402, "attempts": 3, "callsign": "Nyx", "replay": false},
  "next": {"id": "L02", "title": "SIGNAL NOISE", "concept": "…", "status": "encrypted"},
  "state": { "…": "State" }
}
```
`reward` and `next` are `null` unless `victory`. `error` is `null` when the code ran clean.
On victory with Higgsfield online, the server immediately queues the cutscene render
(latency hiding: it renders while the player reads the reward screen).

### 3.4 Server-Sent Events (`GET /api/events?token=…`)

| event | data |
|---|---|
| `hello` | `{"server_time": float}` |
| `file` | `{"mission": "L01", "source": str, "mtime": float}` — mission file changed on disk by something other than the client's own `PUT` |
| `cutscene` | `{"mission": "L01", "state": "rendering\|done\|failed\|offline", "stage": "still\|video", "url"?: str, "kind"?: "image\|video", "error"?: str}` |
| `state` | `State` — profile changed (after a hack through the API, or when another process — `game.py tui`, `hack`, `watch` — saved progress to save.json) |
| `productivity` | Command center snapshot — an activity was logged (docs/PRODUCTIVITY.md) |

A `: keepalive` comment is sent every 15 s. A watcher thread polls the current
mission file's mtime every 300 ms; writes made through `PUT` are suppressed by content hash.
The same thread checks save.json's signature and publishes `state` when another process
changed it (its own writes are not echoed).

`PUT /api/missions/:id/source`: CRLF/CR become LF; a lone UTF-16 surrogate (half an emoji)
becomes U+FFFD instead of failing the save.

---

## 4. Client runtime

### 4.1 Boot (`main.js`)

1. Read token from `<meta name="ns-token">`, create `Api`.
2. Create `Loop`, `Camera(root=#ui)`, `Renderer(canvas#gl)`, `AudioEngine`, `FeedbackDirector`.
3. `loop.add({ update: dt => renderer.update(dt) })`
   `loop.add({ frame: (realDt, alpha) => { camera.frame(realDt); renderer.frame(realDt, alpha); } })`
4. Fetch `State`, open SSE, re-emit SSE events on the bus as `server:<event>`.
5. `screens.go('boot')`.

`ctx` — the object every screen receives:
```js
{ bus, api, audio, renderer, camera, loop, settings,
  screens,            // ScreenManager: go(name, params)
  state,              // latest State payload (mutable reference, replaced on refresh)
  refreshState(),     // GET /api/state → ctx.state, emits 'state:changed'
  toast(msg, {kind: 'info'|'ok'|'warn'|'error', ms: 3200}),
  openSettings() }
```

### 4.2 Screens

```js
export class XScreen {
  constructor(ctx) {}
  async enter(params) {}   // build DOM: this.el = h('section', {class: 'screen screen--x'}); return when mounted
  async exit() {}          // stop timers/listeners; the manager removes this.el after the exit transition
  onKey(event) { return false; }   // return true if handled (stops global handling)
}
```
`ScreenManager.go(name, params)`: calls `exit()` on the current screen, adds
`is-exiting` (removed from DOM after 320 ms), mounts the new `el` into `#screens`,
calls `enter(params)`, then adds `is-active` on the next frame. Emits `screen:change {name}`.
Only one `go` runs at a time (calls during a transition are queued, last wins).

| screen | params | goes to |
|---|---|---|
| `boot` | – | `hub` on any key/click (this gesture calls `audio.unlock()`) |
| `hub` | `{unlocked?: id}` | `mission {id}` |
| `mission` | `{id}` | `victory {mission, result}`, `hub` |
| `victory` | `{mission, result}` | `cutscene {mission}` or `hub {unlocked}` |
| `cutscene` | `{mission}` | `hub {unlocked}` |

Settings are an overlay (`ui/screens/settings.js`, `class SettingsOverlay {open(), close(), get isOpen}`),
toggled by `Esc` when the active screen does not handle it, or by any `[data-action="settings"]` button.

### 4.3 DOM layers (`index.html`)

```html
<canvas id="gl"></canvas>          <!-- fixed, full-viewport, z-index 0 -->
<div id="fallback-bg"></div>       <!-- shown only when body.no-webgl -->
<div id="ui">                      <!-- z-index 1; Camera writes its transform -->
  <div id="screens"></div>
</div>
<div id="crt"></div>               <!-- z-index 50, pointer-events:none: scanlines + vignette + flicker -->
<div id="toasts"></div>            <!-- z-index 60 -->
<div id="settings-root"></div>     <!-- z-index 70 -->
```
Screen-space coordinates everywhere in the client are **CSS pixels relative to
the viewport** (`getBoundingClientRect()`), top-left origin. Particles use the same space;
the renderer converts to clip space. `#ui` and the GL composite share one shake offset,
so particles stay glued to DOM elements while the screen shakes.

### 4.4 Module contracts

**`core/bus.js`** — `export const bus` with `on(type, fn) → off`, `once`, `emit(type, payload)`.

**`core/settings.js`** — `export const settings` with `get(k)`, `set(k, v)`, `all()`,
`onChange(fn(k, v)) → off`, `reset()`. Keys & defaults:
`masterVolume 0.8, musicVolume 0.55, sfxVolume 0.85, shake 1.0, crt 1.0, bloom true,
quality 'auto' ('auto'|'high'|'medium'|'low'), reducedMotion <prefers-reduced-motion>, typingSounds true`.

**`core/math.js`** — `clamp lerp invLerp smoothstep damp(current, target, lambda, dt)`,
easings `easeOutCubic easeInOutCubic easeOutExpo easeOutBack easeOutElastic`,
`class Spring(value, omega)` (critically damped; `.target`, `.update(dt)`, `.value`, `.velocity`),
`noise1(x)` (1-D gradient noise in [-1, 1]), `rand(a, b)`, `randInt(a, b)`, `hexToRgb('#rrggbb') → [r,g,b] 0..1`.

**`core/loop.js`**
```js
export class Loop {
  constructor({ step = 1/120, maxFrame = 0.25 } = {})
  add(system)          // { update?(dt), frame?(realDt, alpha) } — called in insertion order
  start(); stop();
  timeScale            // multiplies sim dt (slow motion), default 1
  hitStop(ms)          // freeze sim updates for ms of real time (max of overlapping requests); frame() keeps running
  get fps(); get frameMs()   // exponential moving averages
}
```
Fixed-timestep accumulator ("Fix Your Timestep"): `update(step)` runs 0..N times per
rAF, `alpha = accumulator / step` is passed to `frame` for interpolation. Pauses on
`document.hidden` and resets the clock on resume (no catch-up spiral).

**`render/gl.js`** — `createProgram(gl, vs, fs, label)` (throws Error with numbered source + log),
`createTarget(gl, w, h, {hdr: bool, filter: gl.LINEAR})` → `{fbo, tex, w, h, hdr}`,
`resizeTarget(gl, target, w, h)`, `deleteTarget`, `FULLSCREEN_VS` (no attributes; uses `gl_VertexID`,
outputs `vec2 vUv`), `drawFullscreen(gl)`, `uniforms(gl, program) → {name: location}`.
HDR targets use `RGBA16F` when `EXT_color_buffer_float` exists, else `RGBA8`.

**`render/renderer.js`**
```js
export class Renderer {
  constructor(canvas, { bus, settings, camera })
  ok                     // false if WebGL2 unavailable → adds body.no-webgl; all methods become no-ops
  world; particles; post // sub-systems (particles is a no-op stub when !ok)
  update(dt)             // sim step: world.update(dt), particles.update(dt)
  frame(realDt, alpha)   // render: world → worldRT (scaled), blit to hdrRT, particles (additive), post → screen
  setMood(name, seconds = 1.2)   // 'calm'|'mission'|'combat'|'alarm'|'victory'|'cinematic' — eased blend
  flash(rgb, amount)             // additive full-screen flash, decays ~0.25 s
  setFocus(amount)               // 0..1 darkens/blurs world behind dense UI (mission screen 0.6)
  get stats()            // {fps, ms, scale, particles}
}
```
Frame state passed to `world.render` / `post.render` (one object, mutated, never reallocated):
```js
{ time, dt, width, height, cssWidth, cssHeight, dpr, alpha,
  camera: { x, y, shakeX, shakeY, roll },          // parallax -1..1, shake in CSS px, roll in radians
  mood:   { color: Float32Array(3), intensity, alarm, corruption, cinematic, victory },
  flash:  { color: Float32Array(3), amount },
  focus, lightning, renderScale }
```
Mood presets (blend targets): `calm` cyan `[0.0,0.85,1.0]` intensity .8 corruption .08;
`mission` blue-cyan `[0.15,0.6,1.0]` .85/.12; `combat` magenta `[1.0,0.17,0.84]` 1.0/.22;
`alarm` red `[1.0,0.18,0.25]` alarm 1 corruption .55; `victory` acid `[0.25,1.0,0.12]` 1.35 victory 1;
`cinematic` violet `[0.55,0.3,1.0]` cinematic 1.
Adaptive quality (`quality: 'auto'`): EMA of frame time; above 18.5 ms for 0.5 s → step
`renderScale` down (min .5); below 12 ms for 2 s → step up (max 1). World renders at
`renderScale × worldScale` (worldScale .6 auto/high, .5 medium, .35 low). Handles
`webglcontextlost` (preventDefault, stop drawing) and `webglcontextrestored` (rebuild everything).
DPR is capped at 2.

**`render/world.js`** — `export class World { constructor(gl); update(dt); render(gl, frame); onStrike = null; }`.
Draws one full-screen pass into the bound target (viewport already set). Outputs linear HDR
color (bright lights > 1.0 so bloom catches them). Owns its lightning scheduler: exposes
`this.lightning` (0..1 envelope, copied into `frame.lightning` by the renderer) and calls
`this.onStrike?.()` when a strike starts (renderer forwards it as bus `world:lightning`).
See the art bible (§6).

**`render/particles.js`**
```js
export class Particles {
  constructor(gl, { capacity = 12000 } = {})
  emit(preset, x, y, opts = {})   // x,y CSS px; opts: {tx, ty, color:[r,g,b], count, speed, spread, angle}
  emitPoints(points, opts = {})   // points: Float32Array [x0,y0,x1,y1,…] CSS px — one particle each (glyph disintegration)
  update(dt)                      // fixed-step integration; keeps previous positions for interpolation
  render(gl, frame)               // additive, instanced, one draw call; interpolates prev→cur by frame.alpha
  setDensity(m)                   // 0..1 quality multiplier on counts
  get count()
}
```
Presets: `spark` (fast streaks, drag, gravity), `shatter` (chunky shards, spin, gravity),
`stream` (bits that home toward `tx,ty`), `explosion` (big radial burst + embers),
`confetti` (rank-up), `embers` (slow rising), `dust` (ambient motes; `opts.count` per call).
Struct-of-arrays `Float32Array` pool, swap-remove on death, no allocation after construction.

**`render/post.js`** — `export class Post { constructor(gl); resize(w, h); render(gl, hdrTarget, frame, settings) }`:
bloom (soft-knee prefilter → 5-level downsample → tent upsample, additive) then a final
composite to the default framebuffer: ACES tonemap, bloom, chromatic aberration
(radial, scales with `settings.crt`, shake and `mood.alarm`), vignette, scanlines and grain
(scale with `settings.crt`), flash, `focus` darkening, shake offset in UV, subtle barrel
distortion at `crt > 0.5`. `settings.bloom === false` skips bloom.

**`fx/camera.js`**
```js
export class Camera {
  constructor({ root, settings })   // root = #ui element
  addTrauma(amount)                 // trauma += amount, clamped to 1
  pointer(nx, ny)                   // parallax target, -1..1
  frame(realDt)                     // trauma decays 1.4/s; shake = trauma²·Perlin; springs → writes root.style.transform
  get state()                       // {x, y, shakeX, shakeY, roll}
}
```
Max shake 14 CSS px and 0.55°, scaled by `settings.shake`; `reducedMotion` → ×0.25 and no parallax.
Writes `transform` only when it changes (and clears it to `''` at rest so `#ui` isn't a permanent layer).

**`audio/audio.js`**
```js
export class AudioEngine {
  constructor({ settings, bus })
  unlock()                        // resume AudioContext on first gesture; starts the ambient bed; idempotent
  play(cue, { pitch = 1, gain = 1, pan = 0 } = {})
  setMood(name)                   // crossfade ambient layers (same mood names as the renderer)
  get ready()
}
```
Cues: `hover click open close type save charge breach blocked crash alarm death victory xp
rankup decode glitch thunder unlock error whoosh`. Master → compressor → destination;
`music` and `sfx` buses follow settings live. Per-cue voice limits; every node is
disconnected when it ends. Listens to bus `world:lightning` → delayed `thunder`.

**`fx/feedback.js`** — `export class FeedbackDirector { constructor(ctx) }`. Subscribes to the
semantic events (§5) and drives camera, particles, renderer and audio. The one place juice is tuned.

**`ui/api.js`**
```js
export class Api {
  constructor(token)
  state(); mission(id); deploy(id); saveSource(id, source); hack(id); reset(id); cutscene(id)
  events(onEvent)   // EventSource with exponential-backoff reconnect; onEvent(name, data); returns close()
}
```
Throws `ApiError {status, message}` on non-2xx. 15 s timeout (60 s for `hack`).

**`ui/dom.js`** — `h(tag, attrs, ...children)`, `$`, `$$`, `sleep`, `nextFrame`, `escapeHtml`,
`inlineCode(text)` (escape, then `` `x` `` → `<code>x</code>`),
`decodeText(el, text, {duration})`, `typewriter(el, text, {cps, onChar}) → {done, skip}`,
`countUp(el, from, to, {duration, onTick, format})`, `formatTime(seconds)`, `rectCenter(el) → {x, y}`.
Every animation helper completes instantly when `settings.reducedMotion` is on.

**`ui/editor.js`**
```js
export class CodeEditor {
  constructor(container, { bus, onChange, onSubmit, onSave })  // Ctrl/Cmd+Enter → onSubmit, Ctrl/Cmd+S → onSave
  get value(); setValue(text, { silent = false } = {})
  get dirty(); markClean()
  markError(line, message)        // gutter + line glow + inline message widget
  clearMarks()
  lineRect(line) → DOMRect        // for particle origins
  focus(); destroy()
}
```
Textarea + highlighted overlay; Python tokenizer; line numbers; current-line highlight;
Tab/Shift-Tab indent (4 spaces), Enter keeps indent (+4 after `:`), Ctrl+/ toggles comments.
Emits `ui:type` (throttled to 1 per 35 ms) on keystrokes.

### 4.5 Shared CSS components (`css/app.css`)

Defined once in `app.css`; screen stylesheets compose them and never redefine them.

| class | purpose |
|---|---|
| `.screen`, `.screen--<name>` | screen root; `.is-active` fades/slides in, `.is-exiting` fades out (320 ms) |
| `.panel` `.panel__head` `.panel__title` `.panel__body` | glass panel, chamfered corners, neon hairline in `--accent`, corner brackets |
| `.btn` `.btn--primary` `.btn--danger` `.btn--ghost` `.btn--lg` | buttons; press = scale .97 + glow; `.btn .kbd` shows a shortcut |
| `.icon-btn` | square icon button (settings gear, back) |
| `.kbd` | keyboard hint chip |
| `.chip` `.chip--ok` `.chip--warn` `.chip--bad` | small status pill |
| `.label` | tiny uppercase tracked label (`--steel`) |
| `.mono` `.glow` `.dim` | utilities |
| `.topbar` | 56 px top bar: left / centre / right slots |
| `.scroll` | themed scroll container |
| `.meter` + `.meter__fill` | horizontal bar; fill width via `--value` (0..1), animated |
| `.rich` | rendered markdown (briefings): `p`, `strong`, `em`, `code`, `pre.code` + `tk-*` token colours |

Any element may set `--accent` / `--accent-rgb` to recolour these components.

---

## 5. Event catalogue (bus)

Payload coordinates are viewport CSS px.

| event | payload | emitted by |
|---|---|---|
| `ui:hover` `ui:click` `ui:open` `ui:close` `ui:error` `ui:type` | `{}` | UI |
| `screen:change` | `{name}` | ScreenManager |
| `state:changed` | `State` | ctx.refreshState / mission screen |
| `server:hello` `server:file` `server:cutscene` `server:state` | SSE data | main.js |
| `hack:charge` | `{x, y, tx, ty}` editor → enemy | mission |
| `hack:layer` | `{index, total, passed, combo, x, y, tx, ty}` row → enemy HP segment | mission |
| `hack:crash` | `{status, x, y}` at the error line | mission |
| `hack:fail` | `{passed, total}` | mission |
| `hack:victory` | `{x, y, points: Float32Array}` enemy center + glyph points | mission |
| `reward:tick` | `{}` | victory |
| `reward:stamp` | `{x, y}` | victory |
| `reward:rankup` | `{rank, x, y}` | victory |
| `world:lightning` | `{}` | renderer |
| `mood` | `{name}` | screens → feedback (renderer + audio) |

Feedback table (implemented in `fx/feedback.js`):

| event | camera | particles | audio | renderer |
|---|---|---|---|---|
| `hack:charge` | trauma .08 | `stream` editor→enemy | `charge` | mood `combat` |
| `hack:layer` passed | trauma .22, hit-stop 45 ms | `spark` at row, `stream` row→enemy, `shatter` at segment | `breach` pitch `1 + combo·0.09` | flash mood colour .12 |
| `hack:layer` blocked | trauma .3 | `spark` red at row | `blocked` | flash red .15 |
| `hack:crash` | trauma .55 | `spark` red at line | `crash` then `alarm` | mood `alarm` 1.6 s, then `mission` |
| `hack:fail` | – | – | – | mood `mission` |
| `hack:victory` | trauma .9, hit-stop 140 ms | `explosion` + `emitPoints` | `death`, then `victory` | flash acid .85, mood `victory` |
| `reward:tick` | – | – | `xp` | – |
| `reward:stamp` | trauma .35 | `spark` | `blocked` pitch .6 | – |
| `reward:rankup` | trauma .3 | `confetti` | `rankup` | flash magenta .4 |
| `world:lightning` | trauma .04 | – | `thunder` (0.25–1.1 s later) | – |
| `ui:*` | – | – | matching cue | – |
| `mood` | – | – | `setMood` | `setMood` |

---

## 6. Art bible

**Fantasy:** the last engineer awake inside a dead, flooded server-world. Neon is
scarce and precious. Darkness is the default; light means information.

**Palette** (`css/tokens.css`): void `#05060a`, deep `#0a0d14`, panel `rgba(10,14,22,.62)`,
cyan `#00f0ff` (system/primary), magenta `#ff2bd6` (narrative/danger-adjacent),
acid `#39ff14` (success), amber `#ffb000` (warning/intel), blood `#ff3355` (enemy/failure),
steel `#8892a6` (body text), dim `#4a5160`. Sector accents come from the campaign colors.

**Type:** display `Chakra Petch` (600/700, uppercase, +0.12em tracking), mono
`JetBrains Mono` for code and data. Fallbacks: `ui-monospace, "Cascadia Code", Consolas, monospace`.

**UI language:** glass panels (backdrop blur 14 px, 1 px neon hairline at 35% alpha),
chamfered corners via `clip-path`, corner brackets, tiny uppercase labels with wide
tracking, numbers in mono. Glow is earned: only interactive or live elements glow.
Motion: 140–220 ms ease-out for UI, springs for anything physical. Nothing linear.

**World ("The Dead Zone"):** night sky of slow fbm clouds lit from below; on the horizon the
**Core**, a colossal monolith whose light colour *is* the mood colour, throwing a beam
into the clouds; two parallax layers of ruined server towers with sparse flickering
windows and atmospheric fog; a flooded ground plane mirroring the skyline with rain
ripples and faint perspective data-lines flowing to the horizon; three depths of slanted
rain streaks. Lightning lights the clouds from inside. `corruption` adds horizontal
glitch bands; `alarm` pulses red through fog and Core; `cinematic` slowly dollies in.

**Performance budget:** world ≤ 3 ms at 960×540 on an integrated GPU; no loop over 48
iterations; the whole frame ≤ 8 ms on a mid laptop at 1080p.

---

## 7. Testing

* `python -m unittest discover -s tests` — session rules, grading, server security.
* Client: headless Chromium (Playwright) loads the real server, asserts no console
  errors, compiles every shader, and drives a full Level 1 clear.
