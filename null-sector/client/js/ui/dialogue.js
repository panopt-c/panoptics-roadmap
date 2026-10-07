/**
 * DialogueOverlay — placeholder until the v2 build lands (docs/GAME_DESIGN.md §5.2, §8, §12).
 * `play(lines)` resolves at once, so callers can depend on the API today.
 */
export class DialogueOverlay {
  constructor(ctx, root) {
    this.ctx = ctx;
    this.root = root;
  }

  /** @returns {Promise<void>} */
  play() {
    return Promise.resolve();
  }

  get active() {
    return false;
  }
}
