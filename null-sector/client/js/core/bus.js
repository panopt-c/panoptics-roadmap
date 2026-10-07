/**
 * Global event bus.
 *
 * Gameplay code emits *semantic* events ("a firewall layer was breached");
 * feedback systems (camera, particles, audio, lighting) subscribe and decide how
 * that should feel. See docs/ARCHITECTURE.md §5 for the event catalogue.
 */
export class Bus {
  #handlers = new Map();

  /** Subscribe. Returns an unsubscribe function. */
  on(type, fn) {
    let set = this.#handlers.get(type);
    if (!set) this.#handlers.set(type, (set = new Set()));
    set.add(fn);
    return () => set.delete(fn);
  }

  once(type, fn) {
    const off = this.on(type, (payload) => {
      off();
      fn(payload);
    });
    return off;
  }

  emit(type, payload) {
    const set = this.#handlers.get(type);
    if (!set || set.size === 0) return;
    // Copy so handlers may unsubscribe while we iterate.
    for (const fn of Array.from(set)) {
      try {
        fn(payload);
      } catch (err) {
        console.error(`[bus] handler for "${type}" threw`, err);
      }
    }
  }
}

export const bus = new Bus();
