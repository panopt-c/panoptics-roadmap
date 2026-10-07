/**
 * RunResultScreen — placeholder until the v2 build lands (docs/GAME_DESIGN.md §8). Shows an "offline"
 * panel with a way back, so the shell never fails to load this module.
 */
import { h } from '../dom.js';

export class RunResultScreen {
  #ctx;

  constructor(ctx) {
    this.#ctx = ctx;
  }

  async enter() {
    this.el = h(
      'section',
      { class: 'screen screen--run-result screen--placeholder', 'aria-label': 'Run result' },
      h(
        'div',
        { class: 'placeholder' },
        h(
          'section',
          { class: 'panel placeholder__panel' },
          h('div', { class: 'panel__head' }, h('h2', { class: 'panel__title' }, 'Run result')),
          h(
            'div',
            { class: 'panel__body' },
            h('p', { class: 'placeholder__msg' }, 'This module is still coming online.'),
            h('button', { class: 'btn btn--primary', type: 'button', onclick: () => this.#ctx.screens.go('hub') }, 'Back to hub'),
          ),
        ),
      ),
    );
  }

  async exit() {}

  onKey(e) {
    if (e.key === 'h' || e.key === 'H') {
      this.#ctx.screens.go('hub');
      return true;
    }
    return false;
  }
}
