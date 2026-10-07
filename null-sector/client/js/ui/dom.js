/** DOM helpers and text effects shared by every screen. */
import { settings } from '../core/settings.js';
import { easeOutCubic } from '../core/math.js';

const GLYPHS = '!<>-_\\/[]{}—=+*^?#░▒▓█01ABCDEFX';

/**
 * Hyperscript: h('div', {class: 'panel', onclick: fn}, 'text', childEl)
 * attrs: class, style (string or object), dataset (object), html (trusted markup only),
 * on<event> listeners, anything else → setAttribute. Falsy children are skipped.
 */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'style' && typeof value === 'object') Object.assign(el.style, value);
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key === 'html') el.innerHTML = value;
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
export const nextFrame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));

const reduced = () => settings.get('reducedMotion');

export function escapeHtml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

/** Escape text, then render `backtick` spans as <code>. Safe for innerHTML. */
export function inlineCode(text) {
  return escapeHtml(text).replace(/`([^`]+)`/g, '<code>$1</code>');
}

/**
 * Cyberpunk "decode" reveal: characters resolve left-to-right out of random glyph noise.
 * Resolves when the final text is in place.
 */
export function decodeText(el, text, { duration = 650 } = {}) {
  if (reduced() || duration <= 0) {
    el.textContent = text;
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const start = performance.now();
    const chars = Array.from(text);
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const revealed = Math.floor(easeOutCubic(t) * chars.length);
      let out = '';
      for (let i = 0; i < chars.length; i++) {
        const c = chars[i];
        if (i < revealed || c === ' ') out += c;
        else out += GLYPHS[(Math.random() * GLYPHS.length) | 0];
      }
      el.textContent = out;
      if (t < 1) requestAnimationFrame(tick);
      else {
        el.textContent = text;
        resolve();
      }
    };
    requestAnimationFrame(tick);
  });
}

/**
 * Typewriter. Returns {done: Promise, skip()}. onChar(char) fires per typed character
 * (use it for typing sounds). Appends a text node so existing children are preserved.
 */
export function typewriter(el, text, { cps = 60, onChar } = {}) {
  const node = document.createTextNode('');
  el.append(node);
  if (reduced()) {
    node.data = text;
    return { done: Promise.resolve(), skip() {} };
  }
  let index = 0;
  let timer = 0;
  let finish;
  const done = new Promise((resolve) => (finish = resolve));
  const interval = 1000 / cps;
  let last = performance.now();
  const step = (now) => {
    const due = Math.floor((now - last) / interval);
    if (due > 0) {
      last += due * interval;
      const next = Math.min(text.length, index + due);
      for (let i = index; i < next; i++) onChar?.(text[i]);
      index = next;
      node.data = text.slice(0, index);
    }
    if (index < text.length) timer = requestAnimationFrame(step);
    else finish();
  };
  timer = requestAnimationFrame(step);
  return {
    done,
    skip() {
      cancelAnimationFrame(timer);
      index = text.length;
      node.data = text;
      finish();
    },
  };
}

/** Animated number. onTick(value) fires each time the displayed integer changes. */
export function countUp(el, from, to, { duration = 900, onTick, format = (n) => String(n) } = {}) {
  if (reduced() || duration <= 0 || from === to) {
    el.textContent = format(to);
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const start = performance.now();
    let shown = from;
    el.textContent = format(from);
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const value = Math.round(from + (to - from) * easeOutCubic(t));
      if (value !== shown) {
        shown = value;
        el.textContent = format(value);
        onTick?.(value);
      }
      if (t < 1) requestAnimationFrame(tick);
      else resolve();
    };
    requestAnimationFrame(tick);
  });
}

export function formatTime(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(s / 3600);
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return hours ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** Viewport-space centre of an element in CSS px. */
export function rectCenter(el) {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}
