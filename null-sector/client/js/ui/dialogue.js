import { h } from './dom.js';

/** Keyboard-accessible story sequences; native dialog keeps focus out of the editor. */
export class DialogueOverlay {
  #dialog = null;
  #finish = null;

  constructor(ctx, root) {
    this.ctx = ctx;
    this.root = root;
  }

  /** Resolve true when read/skipped, false when cancelled by a screen change. */
  play(lines = []) {
    this.close();
    const sequence = Array.isArray(lines) ? lines.filter((line) => line && typeof line.text === 'string') : [];
    if (!this.root || !sequence.length) return Promise.resolve(true);
    const previousFocus = document.activeElement;
    let index = 0;
    const speaker = h('h2', { id: 'story-speaker', class: 'dialogue__speaker' });
    const text = h('p', { id: 'story-text', class: 'dialogue__text', 'aria-live': 'polite' });
    const counter = h('span', { class: 'dialogue__count' });
    const next = h('button', { type: 'button', class: 'btn', onclick: () => advance() });
    const skip = h('button', { type: 'button', class: 'btn btn--ghost', onclick: () => finish(true) }, 'SKIP STORY');
    const dialog = h('dialog', {
      class: 'dialogue', 'aria-labelledby': 'story-speaker', 'aria-describedby': 'story-text',
    }, h('div', { class: 'dialogue__label' }, 'INCOMING TRANSMISSION'), speaker, text,
    h('div', { class: 'dialogue__controls' }, counter, skip, next));
    const draw = () => {
      const line = sequence[index];
      speaker.textContent = String(line.speaker || 'cipher').toUpperCase();
      const callsign = String(this.ctx.state?.profile?.callsign || 'runner');
      // Callback replacement preserves literal dollars in player names; textContent prevents markup injection.
      text.textContent = line.text.replaceAll('{callsign}', () => callsign);
      counter.textContent = `${index + 1} / ${sequence.length}`;
      next.textContent = index === sequence.length - 1 ? 'CONTINUE' : 'NEXT';
    };
    let resolve;
    const done = new Promise((settle) => { resolve = settle; });
    const finish = (completed) => {
      if (this.#dialog !== dialog) return;
      this.#dialog = null;
      this.#finish = null;
      dialog.close();
      dialog.remove();
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
      resolve(completed);
    };
    const advance = () => {
      if (++index >= sequence.length) finish(true);
      else draw();
    };
    dialog.addEventListener('cancel', (event) => { event.preventDefault(); finish(true); });
    dialog.addEventListener('keydown', (event) => {
      // Let Tab and button activation use their native behavior, but don't send shortcuts to gameplay.
      event.stopPropagation();
      if ((event.ctrlKey || event.metaKey) && ['Enter', 's', 'S'].includes(event.key)) event.preventDefault();
    });
    this.#dialog = dialog;
    this.#finish = finish;
    this.root.append(dialog);
    draw();
    dialog.showModal();
    next.focus({ preventScroll: true });
    return done;
  }

  close() {
    this.#finish?.(false);
  }

  get active() {
    return this.#dialog !== null;
  }
}
