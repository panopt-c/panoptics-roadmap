/**
 * Loop — the game's clock.
 *
 * Fixed-timestep simulation with interpolated rendering (Glenn Fiedler, "Fix Your Timestep!"):
 * real time is poured into an accumulator and the simulation is advanced in constant
 * `step` slices (1/120 s), so particles, springs and timers behave identically at 30, 60
 * or 240 Hz. Once per display refresh every system's `frame(realDt, alpha)` runs, where
 * `alpha` ∈ [0, 1) says how far the present instant sits between the previous and the
 * current sim state — renderers interpolate with it, so motion is smooth at any refresh rate.
 *
 * Game-feel controls
 *  - `timeScale` scales the time fed to the accumulator. The sim dt stays exactly `step`
 *    (deterministic), slow motion simply runs fewer steps, and `alpha` keeps it fluid.
 *  - `hitStop(ms)` freezes the simulation for `ms` of *real* time; overlapping requests take
 *    the max of what remains. `frame()` keeps running with real dt, so UI, camera shake and
 *    post effects stay alive during the freeze. A hit-stop ending mid-frame hands the
 *    leftover time to the sim, so freezes are exact to the sub-frame.
 *
 * Frame pacing
 *  - rAF timestamps jitter (and are coarsened by privacy-hardened browsers), while the display
 *    really refreshes at a fixed period. An interval within 0.25 ms of 1–3 periods of a common
 *    refresh rate is snapped to it, so at 60/120/144 Hz every frame advances the sim by the
 *    same number of steps instead of alternating (e.g. 0, 2, 0, 2 at 120 Hz) — that alternation
 *    is visible judder in anything that does not interpolate. The step test has a tiny epsilon
 *    for the same reason: float error must not turn "exactly one step" into zero.
 *
 * Robustness
 *  - dt is clamped to `maxFrame` (no spiral of death after a hitch or a debugger pause),
 *    and the number of sim steps per frame is bounded.
 *  - The loop pauses while `document.hidden` and restarts its clock on resume, so returning
 *    to the tab never triggers a catch-up burst.
 *  - A system that throws is logged once and the loop keeps running every other system
 *    ("degrade, never break"). The next frame is scheduled before any system runs.
 *
 * Performance: zero allocations per tick — the rAF callback is bound once, systems live in
 * flat arrays iterated by index, removals requested mid-tick are deferred to its end. Even the
 * numbers handed to systems are free: a freshly computed double crossing a (megamorphic) call
 * is boxed into a new heap number by V8, so `dt`/`alpha`/`step` are passed from tagged fields
 * that are only reassigned when the value changes (measured: ~33 B/frame → 0).
 */
/** Refresh periods (s) that measured frame intervals snap to. */
const REFRESH = new Float64Array([60, 120, 144, 165, 240, 90, 75, 100, 50].map((hz) => 1 / hz));
const SNAP_TOLERANCE = 0.00025;

function snapInterval(dt) {
  for (let i = 0; i < REFRESH.length; i++) {
    const p = REFRESH[i];
    const n = Math.round(dt / p);
    if (n >= 1 && n <= 3 && Math.abs(dt - n * p) < SNAP_TOLERANCE) return n * p;
  }
  return dt;
}

export class Loop {
  /** Multiplies simulation time (slow motion < 1 < fast forward). 0 pauses the sim. */
  timeScale = 1;

  #step;
  #maxFrame;
  #maxSteps;

  #updaters = [];
  #framers = [];
  #pendingRemoval = [];
  #inTick = false;
  #faulted = new WeakSet();

  #running = false;
  #raf = 0;
  #last = -1; // rAF timestamp of the previous tick (ms); -1 = clock reset
  #acc = 0; // sim seconds owed
  #hitStop = 0; // real seconds of freeze remaining
  #time = 0; // total sim seconds
  #alpha = 0;

  #frameMs = 1000 / 60; // EMA of the real frame interval
  // Boxed copies of the values passed to systems (see the header: no per-call heap numbers).
  #stepArg = null;
  #dtArg = null;
  #alphaArg = null;
  #cpuMs = 0; // EMA of time spent inside tick()

  #onFrame = (t) => this.#tick(t);
  #onVisibility = () => this.#visibilityChanged();

  constructor({ step = 1 / 120, maxFrame = 0.25 } = {}) {
    this.#step = step > 0 ? step : 1 / 120;
    this.#maxFrame = maxFrame > 0 ? maxFrame : 0.25;
    // Enough steps to absorb a clamped frame at up to 4x fast-forward; beyond that the sim slips.
    this.#maxSteps = Math.ceil((this.#maxFrame * 4) / this.#step) + 1;
  }

  /**
   * Registers `{ update?(dt), frame?(realDt, alpha) }`. Systems are called in insertion
   * order. Returns a function that removes the system again.
   */
  add(system) {
    if (!system) return () => {};
    if (typeof system.update === 'function') this.#updaters.push(system);
    if (typeof system.frame === 'function') this.#framers.push(system);
    return () => this.remove(system);
  }

  remove(system) {
    if (this.#inTick) {
      this.#pendingRemoval.push(system);
      return;
    }
    let i = this.#updaters.indexOf(system);
    if (i >= 0) this.#updaters.splice(i, 1);
    i = this.#framers.indexOf(system);
    if (i >= 0) this.#framers.splice(i, 1);
  }

  start() {
    if (this.#running) return;
    this.#running = true;
    this.#resetClock();
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', this.#onVisibility);
      if (document.hidden) return;
    }
    this.#raf = requestAnimationFrame(this.#onFrame);
  }

  stop() {
    if (!this.#running) return;
    this.#running = false;
    if (this.#raf) cancelAnimationFrame(this.#raf);
    this.#raf = 0;
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', this.#onVisibility);
  }

  /** Freeze simulation updates for `ms` of real time. Overlapping requests take the max. */
  hitStop(ms) {
    const seconds = (Number(ms) || 0) / 1000;
    if (seconds > this.#hitStop) this.#hitStop = Math.min(seconds, 2);
  }

  /** Frames per second (exponential moving average). */
  get fps() {
    return 1000 / this.#frameMs;
  }

  /** Real frame interval in ms (exponential moving average). */
  get frameMs() {
    return this.#frameMs;
  }

  /** Main-thread ms spent inside the loop's systems per frame (EMA). */
  get cpuMs() {
    return this.#cpuMs;
  }

  /** Total simulated seconds (affected by timeScale and hit-stop). */
  get time() {
    return this.#time;
  }

  get alpha() {
    return this.#alpha;
  }

  get step() {
    return this.#step;
  }

  get running() {
    return this.#running;
  }

  /** True while a hit-stop is freezing the simulation. */
  get frozen() {
    return this.#hitStop > 0;
  }

  // ── internals ──────────────────────────────────────────────────────────

  #resetClock() {
    this.#last = -1;
    this.#acc = 0;
    this.#hitStop = 0;
  }

  #visibilityChanged() {
    if (!this.#running) return;
    if (document.hidden) {
      if (this.#raf) cancelAnimationFrame(this.#raf);
      this.#raf = 0;
    } else if (!this.#raf) {
      this.#resetClock();
      this.#raf = requestAnimationFrame(this.#onFrame);
    }
  }

  #tick(t) {
    // Schedule first: a throwing system must never stop the clock.
    this.#raf = requestAnimationFrame(this.#onFrame);
    const begin = performance.now();

    let dt = this.#last < 0 ? 0 : (t - this.#last) / 1000;
    this.#last = t;
    if (dt > 0) {
      // Time-constant EMA (~0.25 s) of the raw interval, so the stat means the same thing at
      // any refresh rate.
      const k = 1 - Math.exp(-Math.min(dt, 1) / 0.25);
      this.#frameMs += (Math.min(dt, 1) * 1000 - this.#frameMs) * k;
      dt = snapInterval(dt);
    } else {
      dt = 0;
    }
    if (dt > this.#maxFrame) dt = this.#maxFrame;

    // Hit-stop consumes real time before the sim sees any of it.
    let simDt = dt;
    if (this.#hitStop > 0) {
      if (simDt >= this.#hitStop) {
        simDt -= this.#hitStop;
        this.#hitStop = 0;
      } else {
        this.#hitStop -= simDt;
        simDt = 0;
      }
    }

    const scale = this.timeScale > 0 ? this.timeScale : 0;
    this.#acc += simDt * scale;

    const step = this.#step;
    if (this.#stepArg !== step) this.#stepArg = step;
    const stepArg = this.#stepArg;
    const updaters = this.#updaters;
    const framers = this.#framers;
    this.#inTick = true;

    let steps = 0;
    const threshold = step * (1 - 1e-6);
    while (this.#acc >= threshold) {
      this.#acc -= step;
      this.#time += step;
      for (let i = 0; i < updaters.length; i++) {
        const system = updaters[i];
        try {
          system.update(stepArg);
        } catch (err) {
          this.#fault(system, 'update', err);
        }
      }
      if (++steps >= this.#maxSteps) {
        this.#acc %= step; // drop the debt rather than spiral
        break;
      }
    }

    if (this.#acc < 0) this.#acc = 0; // absorbed epsilon
    const alpha = this.#acc / step;
    this.#alpha = alpha;
    if (this.#dtArg !== dt) this.#dtArg = dt;
    if (this.#alphaArg !== alpha) this.#alphaArg = alpha;
    const dtArg = this.#dtArg;
    const alphaArg = this.#alphaArg;
    for (let i = 0; i < framers.length; i++) {
      const system = framers[i];
      try {
        system.frame(dtArg, alphaArg);
      } catch (err) {
        this.#fault(system, 'frame', err);
      }
    }

    this.#inTick = false;
    if (this.#pendingRemoval.length) {
      for (let i = 0; i < this.#pendingRemoval.length; i++) this.remove(this.#pendingRemoval[i]);
      this.#pendingRemoval.length = 0;
    }

    const spent = performance.now() - begin;
    this.#cpuMs += (spent - this.#cpuMs) * 0.1;
  }

  #fault(system, phase, err) {
    if (this.#faulted.has(system)) return;
    this.#faulted.add(system);
    console.error(`[loop] a system threw in ${phase}(); it keeps running, further errors are suppressed`, err);
  }
}
