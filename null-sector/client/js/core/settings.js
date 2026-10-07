/**
 * Player settings, persisted per browser in localStorage.
 * Storage can be unavailable (private mode, blocked site data), so every access is guarded
 * and the game always runs on in-memory defaults.
 */
const STORAGE_KEY = 'nullsector.settings.v1';

const prefersReducedMotion =
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

export const DEFAULTS = Object.freeze({
  masterVolume: 0.8,
  musicVolume: 0.55,
  sfxVolume: 0.85,
  shake: 1.0,
  crt: 1.0,
  bloom: true,
  quality: 'auto', // 'auto' | 'high' | 'medium' | 'low'
  reducedMotion: prefersReducedMotion,
  typingSounds: true,
});

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    // Only accept known keys with the right type.
    const out = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (key in DEFAULTS && typeof value === typeof DEFAULTS[key]) out[key] = value;
    }
    return out;
  } catch {
    return {};
  }
}

class Settings {
  #values = { ...DEFAULTS, ...load() };
  #listeners = new Set();

  get(key) {
    return this.#values[key];
  }

  set(key, value) {
    if (!(key in DEFAULTS) || this.#values[key] === value) return;
    this.#values[key] = value;
    this.#persist();
    for (const fn of Array.from(this.#listeners)) fn(key, value);
  }

  all() {
    return { ...this.#values };
  }

  /** fn(key, value) on every change. Returns an unsubscribe function. */
  onChange(fn) {
    this.#listeners.add(fn);
    return () => this.#listeners.delete(fn);
  }

  reset() {
    for (const key of Object.keys(DEFAULTS)) this.set(key, DEFAULTS[key]);
  }

  #persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.#values));
    } catch {
      /* storage unavailable — settings still apply for this session */
    }
  }
}

export const settings = new Settings();
