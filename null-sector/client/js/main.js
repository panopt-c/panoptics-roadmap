/**
 * main.js — bootstrap and application shell (docs/ARCHITECTURE.md §4.1–4.3).
 *
 * Boot order (§4.1): token → Api; Loop, Camera(#ui), Renderer(#gl), AudioEngine,
 * FeedbackDirector; loop systems; State + SSE; `screens.go('boot')`. The first State request
 * is fired before the subsystem modules are even fetched, so the network round trip overlaps
 * module loading instead of following it.
 *
 * Degrade, never break: everything except the core kit is loaded with dynamic `import()`. A
 * subsystem that fails to load or construct is replaced by a null object (no WebGL → CSS
 * skyline, no audio → silence), a screen that fails becomes an "offline" screen with a way
 * back to the hub, and the failure is logged once. The UI never hard-crashes into a blank page.
 *
 * ScreenManager (§4.2): one transition at a time; calls made during a transition are queued
 * and only the most recent survives ("last wins"). A transition calls `exit()` and starts the
 * outgoing screen's exit animation at once (the DOM node is removed 320 ms later), waits
 * briefly for `exit()` to settle, then runs `enter()`. A screen that builds `this.el`
 * synchronously is mounted immediately (so it can measure itself while it loads data); one
 * that builds it later is mounted when `enter()` resolves. `is-active` is added on the next
 * frame after a forced style resolve, so CSS transitions always start from the initial state.
 *
 * Shell services: ctx (§4.1), toasts, the "link lost" banner (SSE drop, server restart),
 * global keys (Esc → active screen first, else settings), pointer parallax, first-gesture
 * audio unlock, delegated hover/click sounds, settings → body classes, and global error
 * reporting. All input listeners are passive or delegated: one listener per event type.
 */
import { bus } from './core/bus.js';
import { settings } from './core/settings.js';
import { h, $, nextFrame, sleep, inlineCode } from './ui/dom.js';
import { Api, ApiError } from './ui/api.js';

const EXIT_MS = 320; // §4.2: the outgoing screen is removed this long after `is-exiting`
const EXIT_GRACE_MS = 260; // how long a slow `exit()` may hold up the next `enter()`
const SWEEP_MS = 520;
const HOVER_SFX_GAP_MS = 45;
const FAULT_TOAST_GAP_MS = 4000;
const BANNER_DELAY_MS = 1200; // a drop that heals faster than this never shows the banner
const MAX_TOASTS = 4;
const SFX_SELECTOR = '.btn, .icon-btn, [data-sfx]';
const EMPTY = Object.freeze({});

// ── null objects: what a subsystem becomes when its module is missing or throws ──────────
const NULL_PARTICLES = { emit() {}, emitPoints() {}, update() {}, render() {}, setDensity() {}, count: 0 };
const NULL_RENDERER = {
  ok: false,
  world: null,
  particles: NULL_PARTICLES,
  post: null,
  update() {},
  frame() {},
  setMood() {},
  flash() {},
  setFocus() {},
  stats: { fps: 0, ms: 0, scale: 0, particles: 0 },
};
const NULL_CAMERA = { addTrauma() {}, pointer() {}, frame() {}, state: { x: 0, y: 0, shakeX: 0, shakeY: 0, roll: 0 } };
const NULL_AUDIO = { unlock() {}, play() {}, setMood() {}, ready: false };
const NULL_LOOP = { timeScale: 1, fps: 0, frameMs: 0, add: () => () => {}, remove() {}, start() {}, stop() {}, hitStop() {} };

async function load(path, name) {
  try {
    const mod = await import(path);
    if (typeof mod[name] !== 'function') throw new Error(`no export named "${name}"`);
    return mod[name];
  } catch (err) {
    console.error(`[null-sector] ${path} failed to load — continuing without ${name}.`, err);
    return null;
  }
}

function construct(Cls, args, fallback, label) {
  if (!Cls) return fallback;
  try {
    return new Cls(...args);
  } catch (err) {
    console.error(`[null-sector] ${label} failed to start — continuing without it.`, err);
    return fallback;
  }
}

// ── 1. token + API; the first State request flies while modules load ──────────────────
const token = $('meta[name="ns-token"]')?.content ?? '';
const tokenMissing = !token || token.includes('{{');
const api = new Api(token);

const ctx = {
  bus,
  api,
  audio: NULL_AUDIO,
  renderer: NULL_RENDERER,
  camera: NULL_CAMERA,
  loop: NULL_LOOP,
  settings,
  screens: null,
  state: null,
  refreshState,
  toast,
  openSettings: () => overlay?.open(),
};

let refreshing = null;
/** GET /api/state → ctx.state, emits 'state:changed'. Concurrent calls share one request. */
function refreshState() {
  refreshing ??= api
    .state()
    .then((state) => {
      adoptState(state);
      return state;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

function adoptState(state) {
  if (!state || typeof state !== 'object' || !state.profile) return;
  ctx.state = state;
  bus.emit('state:changed', state);
}

// A screen may emit 'state:changed' with a fresh payload (e.g. a HackResult's state) without
// assigning ctx.state itself; keep ctx.state authoritative either way.
bus.on('state:changed', (state) => {
  if (state && state !== ctx.state && typeof state === 'object' && state.profile) ctx.state = state;
});

const firstState = refreshState().catch((err) => {
  console.warn('[null-sector] initial state request failed:', err?.message || err);
  return null;
});

// ── 2. subsystems ──────────────────────────────────────────────────────────────────────
const [Loop, Camera, Renderer, AudioEngine, FeedbackDirector, BootScreen, HubScreen, SettingsOverlay, MissionScreen, VictoryScreen, CutsceneScreen] =
  await Promise.all([
    load('./core/loop.js', 'Loop'),
    load('./fx/camera.js', 'Camera'),
    load('./render/renderer.js', 'Renderer'),
    load('./audio/audio.js', 'AudioEngine'),
    load('./fx/feedback.js', 'FeedbackDirector'),
    load('./ui/screens/boot.js', 'BootScreen'),
    load('./ui/screens/hub.js', 'HubScreen'),
    load('./ui/screens/settings.js', 'SettingsOverlay'),
    load('./ui/screens/mission.js', 'MissionScreen'),
    load('./ui/screens/victory.js', 'VictoryScreen'),
    load('./ui/screens/cutscene.js', 'CutsceneScreen'),
  ]);

const uiRoot = $('#ui');
const canvas = $('#gl');
ctx.loop = construct(Loop, [], NULL_LOOP, 'Loop');
ctx.camera = construct(Camera, [{ root: uiRoot, settings }], NULL_CAMERA, 'Camera');
ctx.renderer = construct(Renderer, [canvas, { bus, settings, camera: ctx.camera }], NULL_RENDERER, 'Renderer');
if (!ctx.renderer.ok) document.body.classList.add('no-webgl');
ctx.audio = construct(AudioEngine, [{ settings, bus }], NULL_AUDIO, 'AudioEngine');
if (!construct(FeedbackDirector, [ctx], null, 'FeedbackDirector')) wireMinimalFeedback();

// ── 3. the clock ───────────────────────────────────────────────────────────────────────
{
  const { renderer, camera, loop } = ctx;
  loop.add({ update: (dt) => renderer.update(dt) });
  loop.add({
    frame: (realDt, alpha) => {
      camera.frame(realDt);
      renderer.frame(realDt, alpha);
    },
  });
  loop.start();
}

/** Without the FeedbackDirector, keep the UI audible and moods flowing (no juice). */
function wireMinimalFeedback() {
  for (const cue of ['hover', 'click', 'open', 'close', 'error', 'save', 'decode', 'glitch', 'whoosh', 'unlock']) {
    bus.on(`ui:${cue}`, () => ctx.audio.play(cue));
  }
  bus.on('mood', (e) => {
    if (!e?.name) return;
    ctx.renderer.setMood(e.name);
    ctx.audio.setMood(e.name);
  });
}

// ── screens ────────────────────────────────────────────────────────────────────────────
/** Stand-in for a screen whose module failed: says so and offers the way home. */
class OfflineScreen {
  constructor(context, name) {
    this.ctx = context;
    this.name = name;
  }

  async enter() {
    const back = () => this.ctx.screens.go('hub');
    this.el = h(
      'section',
      { class: 'screen screen--offline screen--staged', 'aria-label': 'Module offline' },
      h(
        'div',
        { class: 'panel offline rise', style: '--accent: var(--amber); --accent-rgb: 255, 176, 0' },
        h('div', { class: 'panel__head' }, h('span', { class: 'panel__title' }, 'MODULE OFFLINE')),
        h(
          'div',
          { class: 'panel__body offline__body' },
          h('p', { class: 'offline__code mono' }, `ERR::${this.name.toUpperCase()}_UNAVAILABLE`),
          h('p', { class: 'offline__text' }, `The ${this.name} module failed to load. Details are in the browser console.`),
          h('button', { class: 'btn btn--primary', type: 'button', onclick: back }, 'BACK TO HUB', h('span', { class: 'kbd' }, 'ESC')),
        ),
      ),
    );
  }

  async exit() {}

  onKey(e) {
    if (e.key !== 'Escape' && e.key !== 'Enter') return false;
    e.preventDefault();
    this.ctx.screens.go('hub');
    return true;
  }
}

class ScreenManager {
  #ctx;
  #root;
  #registry;
  #instances = new Map();
  #current = null;
  #name = '';
  #busy = false;
  #pending = null;
  #waiters = [];
  #sweepTimer = 0;

  /**
   * @param {object} context  the app ctx handed to every screen
   * @param {HTMLElement} root  #screens
   * @param {Record<string, Function|null>} registry  name → Screen class (null = failed to load)
   */
  constructor(context, root, registry) {
    this.#ctx = context;
    this.#root = root;
    this.#registry = registry;
  }

  /** The active screen once its transition has finished; null while switching. */
  get active() {
    return this.#busy ? null : this.#current;
  }

  get name() {
    return this.#name;
  }

  get busy() {
    return this.#busy;
  }

  /** Switch screens. Resolves when the manager is idle again (this or a later request done). */
  go(name, params = {}) {
    this.#pending = { name, params: params || {} };
    const idle = new Promise((resolve) => this.#waiters.push(resolve));
    if (!this.#busy) this.#drain();
    return idle;
  }

  async #drain() {
    this.#busy = true;
    while (this.#pending) {
      const { name, params } = this.#pending;
      this.#pending = null;
      try {
        await this.#transition(name, params);
      } catch (err) {
        console.error(`[screens] transition to "${name}" failed`, err);
      }
    }
    this.#busy = false;
    const waiters = this.#waiters;
    this.#waiters = [];
    for (const resolve of waiters) resolve();
  }

  async #transition(name, params) {
    const screen = this.#instance(name);
    const prev = this.#current;
    if (prev) await this.#leave(prev);

    this.#current = screen;
    this.#name = name;
    this.#ctx.bus.emit('screen:change', { name });
    if (prev) {
      this.#ctx.bus.emit('ui:whoosh', EMPTY);
      this.#sweep();
    }

    try {
      const entering = screen.enter(params);
      this.#mount(screen); // mounts now if enter() built `el` synchronously
      await entering;
    } catch (err) {
      console.error(`[screens] ${name}.enter() failed`, err);
      this.#discard(screen);
      this.#current = null;
      this.#ctx.toast(`${name.toUpperCase()} FAILED TO OPEN — ${err?.message || 'unknown fault'}`, { kind: 'error' });
      if (name !== 'hub' && !this.#pending) this.#pending = { name: 'hub', params: {} };
      return;
    }

    // A newer request arrived while this screen loaded: skip straight to it.
    if (this.#pending || this.#current !== screen) return;
    this.#mount(screen);
    await nextFrame();
    const el = screen.el;
    if (el && this.#current === screen) {
      void getComputedStyle(el).opacity; // resolve the initial style so transitions run
      el.classList.add('is-active');
    }
  }

  #instance(name) {
    if (this.#instances.has(name)) return this.#instances.get(name);
    const Cls = this.#registry[name];
    let screen = null;
    if (Cls) {
      try {
        screen = new Cls(this.#ctx);
      } catch (err) {
        console.error(`[screens] constructing "${name}" failed`, err);
      }
    } else if (!(name in this.#registry)) {
      console.error(`[screens] unknown screen "${name}"`);
    }
    screen ??= new OfflineScreen(this.#ctx, name);
    this.#instances.set(name, screen);
    return screen;
  }

  #mount(screen) {
    const el = screen.el;
    if (el instanceof Element && !el.isConnected) this.#root.append(el);
  }

  async #leave(screen) {
    const el = screen.el;
    let exiting;
    try {
      exiting = Promise.resolve(screen.exit());
    } catch (err) {
      exiting = Promise.reject(err);
    }
    exiting = exiting.catch((err) => console.error('[screens] exit() failed', err));
    if (el instanceof Element) {
      if (el.classList.contains('is-active')) {
        el.classList.remove('is-active');
        el.classList.add('is-exiting');
        el.inert = true;
        setTimeout(() => el.remove(), EXIT_MS);
      } else {
        el.remove(); // never shown: nothing to animate
      }
    }
    await Promise.race([exiting, sleep(EXIT_GRACE_MS)]);
  }

  #discard(screen) {
    try {
      Promise.resolve(screen.exit()).catch(() => {});
    } catch {
      /* already failing; the error was reported by enter() */
    }
    screen.el?.remove?.();
  }

  /** One scan-line sweep across the viewport per screen change (#screens::after). */
  #sweep() {
    const root = this.#root;
    root.classList.remove('is-switching');
    clearTimeout(this.#sweepTimer);
    void root.offsetWidth; // restart the CSS animation
    root.classList.add('is-switching');
    this.#sweepTimer = setTimeout(() => root.classList.remove('is-switching'), SWEEP_MS);
  }
}

const screens = new ScreenManager(ctx, $('#screens'), {
  boot: BootScreen,
  hub: HubScreen,
  mission: MissionScreen,
  victory: VictoryScreen,
  cutscene: CutsceneScreen,
});
ctx.screens = screens;

const overlay = construct(SettingsOverlay, [ctx, $('#settings-root')], null, 'SettingsOverlay');

// ── toasts ─────────────────────────────────────────────────────────────────────────────
const TOAST_META = {
  info: { title: 'SYSTEM', icon: '›', accent: '0, 240, 255' },
  ok: { title: 'CONFIRMED', icon: '✓', accent: '57, 255, 20' },
  warn: { title: 'WARNING', icon: '!', accent: '255, 176, 0' },
  error: { title: 'FAULT', icon: '×', accent: '255, 51, 85' },
};
const toastRoot = $('#toasts');
const liveToasts = [];

/**
 * Show a toast. `message` may contain `backtick` spans (rendered as code). Identical toasts
 * merge into one with a ×N counter. Hovering pauses the countdown; clicking dismisses.
 * @returns {{close(): void}}
 */
function toast(message, { kind = 'info', ms = 3200, title } = {}) {
  const meta = TOAST_META[kind] || TOAST_META.info;
  const text = String(message ?? '');
  const twin = liveToasts.find((t) => t.text === text && t.kind === kind && !t.leaving);
  if (twin) {
    twin.count += 1;
    twin.counter.textContent = `×${twin.count}`;
    twin.el.classList.add('has-count');
    twin.restart(ms);
    return twin.handle;
  }

  const bar = h('i', { class: 'toast__bar' });
  const counter = h('span', { class: 'toast__count mono' });
  const el = h(
    'div',
    {
      class: `toast toast--${kind in TOAST_META ? kind : 'info'}`,
      role: kind === 'error' ? 'alert' : 'status',
      style: `--accent-rgb: ${meta.accent}; --accent: rgb(${meta.accent}); --ms: ${Math.max(800, ms)}ms`,
    },
    h('span', { class: 'toast__icon mono', 'aria-hidden': 'true' }, meta.icon),
    h('div', { class: 'toast__text' }, h('span', { class: 'toast__title' }, title || meta.title, counter), h('span', { class: 'toast__msg', html: inlineCode(text) })),
    bar,
  );

  const record = { el, text, kind, count: 1, counter, leaving: false, restart: null, handle: null };
  const leave = () => {
    if (record.leaving) return;
    record.leaving = true;
    liveToasts.splice(liveToasts.indexOf(record), 1);
    el.classList.add('is-leaving');
    // animationend never fires when animations are off; the timer is the backstop.
    const done = () => el.remove();
    el.addEventListener('animationend', (e) => e.target === el && done(), { once: false });
    setTimeout(done, 420);
  };
  record.restart = (nextMs) => {
    el.style.setProperty('--ms', `${Math.max(800, nextMs)}ms`);
    bar.style.animation = 'none';
    void bar.offsetWidth;
    bar.style.animation = '';
  };
  record.handle = { close: leave };
  bar.addEventListener('animationend', leave);
  el.addEventListener('click', leave);

  liveToasts.push(record);
  toastRoot.append(el);
  while (liveToasts.length > MAX_TOASTS) liveToasts.find((t) => !t.leaving)?.handle.close();
  return record.handle;
}

// ── link banner: SSE dropped / server restarted ───────────────────────────────────────
const banner = (() => {
  const detail = h('span', { class: 'link-banner__detail' });
  const title = h('span', { class: 'link-banner__title' }, 'LINK LOST');
  const action = h('button', { class: 'btn btn--ghost link-banner__action', type: 'button', hidden: true, onclick: () => location.reload() }, 'RELOAD');
  const el = h(
    'div',
    { class: 'link-banner', role: 'alert', 'aria-live': 'assertive' },
    h('span', { class: 'link-banner__pulse', 'aria-hidden': 'true' }),
    h('div', { class: 'link-banner__text' }, title, detail),
    action,
  );
  document.body.append(el);
  let shown = false;
  return {
    get shown() {
      return shown;
    },
    show(heading, text, { reload = false } = {}) {
      title.textContent = heading;
      detail.innerHTML = inlineCode(text);
      action.hidden = !reload;
      el.classList.toggle('is-fatal', reload);
      if (!shown) el.classList.add('is-shown');
      shown = true;
    },
    hide() {
      shown = false;
      el.classList.remove('is-shown');
    },
  };
})();

let linkDown = false;
let sessionExpired = false;
let bannerTimer = 0;
let probing = false;

function onServerEvent(name, data) {
  if (name === 'state' && data && typeof data === 'object' && data.profile) ctx.state = data;
  bus.emit(`server:${name}`, data);
  if (name === 'state' && data?.profile) bus.emit('state:changed', data);
}

function onLinkStatus(status, info) {
  if (status === 'open') {
    clearTimeout(bannerTimer);
    if (!linkDown) return;
    linkDown = false;
    if (banner.shown) {
      banner.hide();
      toast('Link to the game server restored.', { kind: 'ok', title: 'LINK RESTORED', ms: 2400 });
    }
    refreshState().catch(() => {}); // events may have been missed while the link was down
    return;
  }
  if (sessionExpired) return;
  const retry = `retrying in ${Math.max(1, Math.round(info.delay / 1000))} s`;
  if (!linkDown) {
    linkDown = true;
    clearTimeout(bannerTimer);
    bannerTimer = setTimeout(() => {
      if (linkDown && !sessionExpired) banner.show('LINK LOST', `Reconnecting to the local game server — ${retry}.`);
    }, BANNER_DELAY_MS);
  } else if (banner.shown) {
    banner.show('LINK LOST', `Is \`python game.py\` still running? Attempt ${info.attempt} — ${retry}.`);
  }
  if (info.attempt >= 2) probeSession();
}

/** After repeated drops, ask the API directly: a 401/403 means the server restarted with a new token. */
async function probeSession() {
  if (probing || sessionExpired) return;
  probing = true;
  try {
    await api.state();
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
      sessionExpired = true;
      closeEvents();
      clearTimeout(bannerTimer);
      banner.show('SESSION EXPIRED', 'The game server restarted with a new key. Reload to re-link — your progress is saved.', { reload: true });
    }
  } finally {
    probing = false;
  }
}

const closeEvents = tokenMissing ? () => {} : api.events(onServerEvent, { onStatus: onLinkStatus });
addEventListener('pagehide', () => closeEvents());

// ── settings → document ───────────────────────────────────────────────────────────────
function applySettings() {
  const body = document.body.classList;
  const crt = Number(settings.get('crt')) || 0;
  body.toggle('reduce-motion', !!settings.get('reducedMotion'));
  body.toggle('crt-off', crt <= 0.001);
  body.toggle('quality-low', settings.get('quality') === 'low');
  document.documentElement.style.setProperty('--crt', crt.toFixed(3));
}
applySettings();
settings.onChange(applySettings);

// ── input ──────────────────────────────────────────────────────────────────────────────
function unlockAudio() {
  if (ctx.audio.ready) return;
  try {
    ctx.audio.unlock();
  } catch (err) {
    console.warn('[null-sector] audio unlock failed', err);
  }
}

addEventListener('pointerdown', unlockAudio, { capture: true, passive: true });

addEventListener('keydown', (e) => {
  unlockAudio();
  if (overlay?.isOpen) return; // the overlay owns the keyboard while it is open
  const screen = screens.active;
  if (!screen) return; // mid-transition: drop input rather than deliver it to a leaving screen
  let handled = false;
  try {
    handled = !!screen.onKey?.(e);
  } catch (err) {
    console.error('[screens] onKey failed', err);
  }
  if (handled || e.defaultPrevented) return;
  if (e.key === 'Escape' && !e.repeat && overlay) {
    e.preventDefault();
    overlay.open();
  }
});

let viewW = innerWidth;
let viewH = innerHeight;
addEventListener('resize', () => {
  viewW = innerWidth;
  viewH = innerHeight;
});
addEventListener('pointermove', (e) => ctx.camera.pointer((e.clientX / viewW) * 2 - 1, (e.clientY / viewH) * 2 - 1), { passive: true });
document.documentElement.addEventListener('pointerleave', () => ctx.camera.pointer(0, 0));

// Delegated UI sounds: one listener each for hover and click, for every button in the game.
const sfxEnabled = (el) => !el.disabled && el.getAttribute('aria-disabled') !== 'true' && el.dataset.sfx !== 'off';
let hovered = null;
let lastHoverAt = 0;
document.addEventListener('pointerover', (e) => {
  const el = e.target instanceof Element ? e.target.closest(SFX_SELECTOR) : null;
  if (el === hovered) return;
  hovered = el;
  if (!el || e.pointerType === 'touch' || !sfxEnabled(el)) return;
  const now = performance.now();
  if (now - lastHoverAt < HOVER_SFX_GAP_MS) return;
  lastHoverAt = now;
  bus.emit('ui:hover', EMPTY);
});
document.addEventListener('click', (e) => {
  if (!(e.target instanceof Element)) return;
  const el = e.target.closest(SFX_SELECTOR);
  if (el && sfxEnabled(el)) bus.emit('ui:click', EMPTY);
  if (e.target.closest('[data-action="settings"]') && overlay && !overlay.isOpen) overlay.open();
});

// ── global error reporting ────────────────────────────────────────────────────────────
let lastFaultAt = 0;
function reportFault(err, kind) {
  console.error(`[null-sector] ${kind}:`, err);
  const now = performance.now();
  if (now - lastFaultAt < FAULT_TOAST_GAP_MS) return;
  lastFaultAt = now;
  if (err instanceof ApiError && err.offline) {
    toast('The game server is unreachable.', { kind: 'error', title: 'LINK LOST', ms: 5000 });
  } else {
    const message = err instanceof Error ? err.message : String(err ?? 'unknown fault');
    toast(message.slice(0, 160) || 'unknown fault', { kind: 'error', title: 'SYSTEM FAULT', ms: 5200 });
  }
  bus.emit('ui:error', EMPTY);
}
addEventListener('error', (e) => {
  if (!e.error && /^ResizeObserver loop/.test(e.message || '')) return; // benign browser notice
  if (!e.error && !e.message) return; // resource load errors are reported by the browser itself
  e.preventDefault();
  reportFault(e.error || e.message, 'uncaught error');
});
addEventListener('unhandledrejection', (e) => {
  e.preventDefault();
  reportFault(e.reason, 'unhandled rejection');
});

// ── go ─────────────────────────────────────────────────────────────────────────────────
window.__NS__ = ctx; // debugging / automated-test hook (same-origin only)

await screens.go('boot');
window.__nsBooted = true;
const preboot = $('#preboot');
if (preboot) {
  preboot.classList.add('is-done');
  setTimeout(() => preboot.remove(), 600);
}
if (tokenMissing) {
  toast('No session token — open the game through `python game.py`, not as a file.', { kind: 'warn', title: 'OFFLINE', ms: 8000 });
}
firstState.then((state) => {
  if (!state && !tokenMissing) toast('Could not read your save from the game server yet.', { kind: 'warn', title: 'NO SIGNAL', ms: 5000 });
});
