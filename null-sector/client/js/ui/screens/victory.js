/**
 * VictoryScreen — the reward ceremony (docs/ARCHITECTURE.md §4.2, §5).
 *
 * Renders the server's verdict, never computes one: every number comes from
 * `result.reward` / `result.state`. The reveal is a timed script of beats:
 *
 *   ACCESS GRANTED decodes in (chromatic glow) → "<ENEMY> — DELETED" stamp slams
 *   → reward rows count up one by one (BASE XP …) → SPEED BONUS stamp slams with breach
 *   time vs par → TOTAL → XP meter fills (rolling over on a rank-up) → RANK UP banner
 *   → IDENTITY REGISTERED → stats, next target and the two actions.
 *
 * Every beat awaits `#beat(ms)`; any key or click flips `#fast`, which resolves all pending
 * beats immediately, snaps running count-ups to their final values (they write through a
 * detached proxy element, so a skipped tween can never overwrite the final number) and
 * adds `.is-instant` so CSS entrances complete at once. Feedback is emitted as meaning only:
 * `reward:tick` (throttled), `reward:stamp` at the stamp's centre on impact, `reward:rankup`.
 *
 * Optional `params.before` (the profile before the hack, passed by the mission screen) lets
 * the meter start from the true previous XP; without it the start is derived from `gained`.
 */
import { h, decodeText, countUp, formatTime, rectCenter, nextFrame } from '../dom.js';
import { settings } from '../../core/settings.js';

const TICK_MS = 42; // reward:tick throttle
const STAMP_IMPACT_MS = 170; // when the slam animation hits the page (see victory.css)
const ICON_PLAY =
  '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M4 2.5v11l9-5.5z" fill="currentColor"/></svg>';

const plus = (n) => `+${n}`;
const xpCeiling = (rank) => (rank.rank_next == null ? ' · MAX RANK' : ` / ${rank.rank_next} XP`);
const reduced = () => settings.get('reducedMotion');

export class VictoryScreen {
  el = null;

  #ctx;
  #alive = false;
  #fast = false;
  #revealed = false;
  #leaving = false;
  #mission = null;
  #result = null;
  #unlocked;
  #timers = new Set();
  #pending = new Set(); // resolvers of in-flight beats
  #offs = [];
  #r = {};
  #lastTick = 0;
  #onPointer = () => this.#skip();

  constructor(ctx) {
    this.#ctx = ctx;
  }

  async enter(params = {}) {
    const ctx = this.#ctx;
    this.#alive = true;
    this.#fast = reduced();
    this.#revealed = false;
    this.#leaving = false;
    this.#r = {};
    this.#mission = params.mission || {};
    this.#result = params.result || {};
    const result = this.#result;
    const reward = result.reward || null;
    this.#unlocked = reward && !reward.replay && result.next ? result.next.id : undefined;

    // screen--staged: every element reveals itself (`.is-in`), so the glass panel keeps its blur.
    this.el = h('section', { class: 'screen screen--victory screen--staged', 'aria-label': 'Access granted' });
    this.#build(params.before || null);
    this.el.addEventListener('pointerdown', this.#onPointer);

    this.#offs.push(ctx.bus.on('server:cutscene', (data) => this.#onCutscene(data)));

    ctx.bus.emit('mood', { name: 'victory' });
    ctx.renderer?.setFocus?.(0.32);

    this.#run();
  }

  async exit() {
    this.#alive = false;
    this.el?.removeEventListener('pointerdown', this.#onPointer);
    for (const off of this.#offs) off();
    this.#offs.length = 0;
    for (const t of this.#timers) clearTimeout(t);
    this.#timers.clear();
    this.#pending.clear();
  }

  onKey(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    if (!this.#revealed) {
      if (e.key === 'Escape' || e.key === 'Shift' || e.key === 'Tab') return false;
      e.preventDefault();
      this.#skip();
      return true;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (this.#mission.cutscene) this.#play(true);
      else this.#hub(true);
      return true;
    }
    if (e.key === 'h' || e.key === 'H') {
      this.#hub(true);
      return true;
    }
    return false;
  }

  // ── DOM ─────────────────────────────────────────────────────────────

  #build(before) {
    const r = this.#r;
    const m = this.#mission;
    const result = this.#result;
    const reward = result.reward || { lines: [], gained: 0, replay: true };
    const profile = result.state?.profile || {};

    r.title = h('h1', { class: 'victory__title', 'data-text': 'ACCESS GRANTED' }, ' ');
    r.deleted = h(
      'div',
      { class: 'victory__deleted stamp' },
      h('span', { class: 'victory__enemy' }, m.enemy || 'TARGET'),
      h('span', { class: 'victory__dash' }, '—'),
      h('span', {}, 'DELETED'),
    );

    // reward rows
    r.lines = [];
    const rows = [];
    for (const line of reward.lines || []) {
      const bonus = line.label === 'SPEED BONUS';
      const value = h('span', { class: 'reward__value mono' }, '+0');
      const el = h(
        'li',
        { class: `reward${bonus ? ' reward--bonus' : ''}` },
        bonus
          ? h(
              'span',
              { class: 'reward__label' },
              h('span', { class: 'stamp stamp--bonus' }, 'SPEED BONUS'),
              h(
                'span',
                { class: 'reward__detail mono' },
                `${formatTime(reward.breach_seconds || 0)} `,
                h('span', { class: 'dim' }, `/ PAR ${formatTime(m.par_seconds || 0)}`),
              ),
            )
          : h('span', { class: 'reward__label' }, line.label),
        h('span', { class: 'reward__leader', 'aria-hidden': 'true' }),
        value,
      );
      rows.push(el);
      r.lines.push({ el, value, amount: Number(line.amount) || 0, bonus, stamp: bonus ? el.querySelector('.stamp') : null });
    }
    const speedMissed = !reward.replay && !(reward.lines || []).some((l) => l.label === 'SPEED BONUS');
    if (speedMissed) {
      rows.push(
        h(
          'li',
          { class: 'reward reward--missed' },
          h(
            'span',
            { class: 'reward__label' },
            'SPEED BONUS',
            h('span', { class: 'reward__detail mono' }, `${formatTime(reward.breach_seconds || 0)} / PAR ${formatTime(m.par_seconds || 0)}`),
          ),
          h('span', { class: 'reward__leader', 'aria-hidden': 'true' }),
          h('span', { class: 'reward__value mono' }, 'MISSED'),
        ),
      );
    }
    r.missed = rows.find((el) => el.classList.contains('reward--missed')) || null;

    r.total = h('span', { class: 'reward__value mono' }, '+0');
    r.totalRow = h('div', { class: 'reward reward--total' }, h('span', { class: 'reward__label' }, 'TOTAL XP'), h('span', { class: 'reward__leader' }), r.total);

    r.replay = reward.replay
      ? h('div', { class: 'victory__replay' }, h('span', { class: 'stamp stamp--replay' }, 'REPLAY — NO XP'), h('p', {}, 'This sector was already restored. Your record stands.'))
      : null;

    // XP meter
    const xpAfter = Number(profile.xp) || 0;
    const xpBefore = before && Number.isFinite(Number(before.xp)) ? Number(before.xp) : Math.max(0, xpAfter - (Number(reward.gained) || 0));
    // On a rank-up the meter starts inside the old rank, whose ceiling is the new rank's floor.
    const startRank = reward.rank_up
      ? { rank_floor: Number(before?.rank_floor) || 0, rank_next: Number(profile.rank_floor) || 0 }
      : profile;
    r.meterFill = h('div', { class: 'meter__fill' });
    r.meter = h('div', { class: 'meter victory__meter' }, r.meterFill);
    r.rankName = h('span', { class: 'victory__rank' }, (reward.rank_up ? reward.rank_before : profile.rank || reward.rank_after) || '');
    r.xpNow = h('span', { class: 'mono' }, String(xpBefore));
    r.xpNext = h('span', { class: 'mono dim' }, xpCeiling(startRank));
    r.xpBlock = h(
      'div',
      { class: 'victory__xp' },
      h('div', { class: 'victory__xp-head' }, h('span', { class: 'label' }, 'RANK'), r.rankName, h('span', { class: 'victory__xp-num' }, r.xpNow, r.xpNext)),
      r.meter,
    );
    this.#meter = { startRank, xpBefore, xpAfter, profile, reward };
    r.meter.style.setProperty('--value', String(this.#fraction(xpBefore, startRank)));

    r.rankup = reward.rank_up
      ? h(
          'div',
          { class: 'victory__rankup', role: 'status' },
          h('span', { class: 'victory__rankup-tag' }, '▲ RANK UP ▲'),
          h('span', { class: 'victory__rankup-name' }, reward.rank_after || profile.rank || ''),
        )
      : null;

    const callsign = reward.callsign || profile.callsign || '';
    const registered = this.#registered(before, callsign, reward);
    r.identity = registered
      ? h(
          'div',
          { class: 'victory__identity' },
          h('span', { class: 'label' }, registered === 'new' ? 'IDENTITY REGISTERED' : 'IDENTITY UPDATED'),
          h('span', { class: 'victory__callsign' }, callsign.toUpperCase()),
        )
      : null;

    // stats + next target
    const next = result.next;
    r.stats = h(
      'div',
      { class: 'victory__stats' },
      h('div', { class: 'victory__stat' }, h('span', { class: 'label' }, 'BREACH TIME'), h('span', { class: 'mono' }, formatTime(reward.breach_seconds || 0))),
      h('div', { class: 'victory__stat' }, h('span', { class: 'label' }, 'ATTEMPTS'), h('span', { class: 'mono' }, String(reward.attempts ?? result.attempt ?? '—'))),
      next
        ? h(
            'div',
            { class: 'victory__stat victory__stat--next' },
            h('span', { class: 'label' }, 'NEXT TARGET'),
            h('span', { class: 'victory__next' }, h('span', { class: 'mono' }, next.id), ` ${next.title}`),
            h('span', { class: `chip ${next.status === 'current' ? 'chip--ok' : 'chip--warn'}` }, next.status === 'current' ? 'UNLOCKED' : 'ENCRYPTED'),
          )
        : null,
    );

    // actions
    r.castStatus = h('span', { class: 'victory__cast label' });
    const play = m.cutscene
      ? h(
          'button',
          { class: 'btn btn--primary btn--lg victory__play', type: 'button', onclick: () => this.#play() },
          h('span', { class: 'victory__play-icon', html: ICON_PLAY }),
          h('span', { class: 'victory__btn-text' }, h('span', {}, 'PLAY TRANSMISSION'), r.castStatus),
          h('span', { class: 'kbd' }, '↵'),
        )
      : null;
    const hub = h(
      'button',
      { class: `btn btn--lg${play ? ' btn--ghost' : ' btn--primary'} victory__hub`, type: 'button', onclick: () => this.#hub() },
      h('span', { class: 'victory__btn-text' }, h('span', {}, 'RETURN TO HUB')),
      h('span', { class: 'kbd' }, play ? 'H' : '↵'),
    );
    r.primary = play || hub;
    r.actions = h('div', { class: 'victory__actions' }, play, hub);
    this.#setCastStatus(this.#ctx.state?.higgsfield?.online ? 'rendering' : 'offline');

    r.skip = h('div', { class: 'victory__skip label' }, 'ANY KEY — SKIP');

    r.panel = h(
      'div',
      { class: 'panel victory__panel' },
      h('div', { class: 'panel__head' }, h('span', { class: 'panel__title' }, 'REWARDS'), h('span', { class: 'label' }, `${m.id || ''} // ${m.title || ''}`)),
      h(
        'div',
        { class: 'panel__body' },
        r.replay,
        rows.length ? h('ul', { class: 'victory__lines' }, rows) : null,
        reward.replay ? null : r.totalRow,
        r.xpBlock,
      ),
    );

    this.el.append(
      h('div', { class: 'victory__glow', 'aria-hidden': 'true' }),
      h(
        'div',
        { class: 'victory scroll' },
        h(
          'header',
          { class: 'victory__head' },
          h('div', { class: 'victory__kicker label' }, h('span', {}, 'BREACH CONFIRMED'), h('span', { class: 'victory__kicker-rule' }), h('span', { class: 'mono' }, m.id || '')),
          r.title,
          r.deleted,
        ),
        r.panel,
        r.rankup,
        r.identity,
        r.stats,
        r.actions,
      ),
      r.skip,
    );
  }

  #meter = null;

  #fraction(xp, profile) {
    const floor = Number(profile?.rank_floor) || 0;
    const next = profile?.rank_next;
    if (next == null) return 1;
    const span = Number(next) - floor;
    return span > 0 ? Math.max(0, Math.min(1, (xp - floor) / span)) : 1;
  }

  /** 'new' | 'updated' | '' — whether this victory wrote a callsign into the profile. */
  #registered(before, callsign, reward) {
    if (!callsign) return '';
    if (before) {
      if (!before.callsign) return 'new';
      return before.callsign !== callsign ? 'updated' : '';
    }
    // Without the previous profile: only a first clear of a mission that registers the callsign.
    const registers = (this.#mission.objectives || []).some((o) => String(o).includes('`callsign`'));
    return registers && !reward.replay ? 'new' : '';
  }

  // ── the reveal ──────────────────────────────────────────────────────

  async #run() {
    const r = this.#r;
    const bus = this.#ctx.bus;
    const reward = this.#result.reward || { lines: [], replay: true };
    await nextFrame();
    if (!this.#alive) return;
    this.el.classList.add('is-revealing');

    // ACCESS GRANTED
    this.#show(r.title);
    bus.emit('ui:decode', {});
    await this.#decode(r.title, 'ACCESS GRANTED', 820);
    if (!this.#alive) return;

    // <ENEMY> — DELETED
    await this.#beat(120);
    await this.#stamp(r.deleted);

    await this.#beat(260);
    this.#show(r.panel);
    await this.#beat(240);

    // reward rows, one by one
    let total = 0;
    for (const line of r.lines) {
      this.#show(line.el);
      if (line.bonus) {
        await this.#beat(90);
        await this.#stamp(line.stamp);
      } else {
        await this.#beat(140);
      }
      await this.#count(line.value, 0, line.amount, line.bonus ? 520 : 720);
      total += line.amount;
      await this.#beat(200);
    }
    if (r.missed) {
      this.#show(r.missed);
      await this.#beat(320);
    }
    if (r.replay) {
      this.#show(r.replay);
      await this.#stamp(r.replay.firstElementChild);
      await this.#beat(260);
    } else {
      this.#show(r.totalRow);
      await this.#count(r.total, 0, Number(reward.gained) || total, 560);
      if (!this.#fast) r.totalRow.classList.add('is-hot');
      await this.#beat(220);
    }

    // XP meter (+ rank-up rollover)
    this.#show(r.xpBlock);
    await this.#fillMeter();

    if (r.rankup) {
      this.#show(r.rankup);
      await this.#beat(this.#fast ? 0 : 140);
      if (this.#alive) {
        const c = rectCenter(r.rankup);
        bus.emit('reward:rankup', { rank: reward.rank_after, x: c.x, y: c.y });
      }
      await this.#beat(520);
    }

    if (r.identity) {
      this.#show(r.identity);
      const name = r.identity.querySelector('.victory__callsign');
      bus.emit('ui:decode', {});
      await this.#decode(name, name.textContent, 600);
      await this.#beat(240);
    }

    this.#show(r.stats);
    await this.#beat(160);
    this.#show(r.actions);
    this.#finishReveal();
  }

  async #fillMeter() {
    const { startRank, xpBefore, xpAfter, profile, reward } = this.#meter;
    const r = this.#r;
    const fmt = (n) => String(n);
    if (reward.replay || xpAfter === xpBefore) {
      r.xpNow.textContent = String(xpAfter);
      r.meter.style.setProperty('--value', String(this.#fraction(xpAfter, profile)));
      return;
    }
    if (reward.rank_up) {
      // Fill out the old rank, then roll over into the new one.
      const ceiling = startRank.rank_next;
      r.meter.classList.add('is-filling');
      r.meter.style.setProperty('--value', '1');
      await this.#count(r.xpNow, xpBefore, ceiling, 520, fmt);
      if (!this.#alive) return;
      r.meter.classList.remove('is-filling');
      r.meter.classList.add('is-rollover');
      r.rankName.textContent = reward.rank_after || profile.rank || '';
      r.xpNext.textContent = xpCeiling(profile);
      r.meter.style.setProperty('--value', '0');
      await nextFrame();
      await nextFrame();
      if (!this.#alive) return;
      r.meter.classList.remove('is-rollover');
      r.meter.classList.add('is-filling');
      r.meter.style.setProperty('--value', String(this.#fraction(xpAfter, profile)));
      await this.#count(r.xpNow, ceiling, xpAfter, 640, fmt);
    } else {
      r.meter.classList.add('is-filling');
      r.meter.style.setProperty('--value', String(this.#fraction(xpAfter, profile)));
      await this.#count(r.xpNow, xpBefore, xpAfter, 820, fmt);
    }
    r.meter.classList.remove('is-filling');
  }

  #finishReveal() {
    if (!this.#alive || this.#revealed) return;
    this.#revealed = true;
    const r = this.#r;
    this.el.classList.remove('is-revealing');
    this.el.classList.add('is-revealed');
    r.skip.classList.add('is-hidden');
    r.primary?.focus({ preventScroll: true });
  }

  // ── beats & skipping ────────────────────────────────────────────────

  #show(el) {
    if (el) el.classList.add('is-in');
  }

  /** Slam a stamp in; emits reward:stamp at its centre on impact. */
  async #stamp(el) {
    if (!el) return;
    el.classList.add('is-in', 'is-slam');
    if (this.#fast) return;
    await this.#beat(STAMP_IMPACT_MS);
    if (!this.#alive || this.#fast) return;
    const c = rectCenter(el);
    this.#ctx.bus.emit('reward:stamp', { x: c.x, y: c.y });
    await this.#beat(200);
  }

  /**
   * decodeText into a child span; a skip swaps in the final text, leaving the running tween
   * writing into a detached node (it cannot be cancelled, and must never overwrite the result).
   */
  #decode(el, text, duration) {
    if (this.#fast) {
      el.textContent = text;
      return Promise.resolve();
    }
    const span = document.createElement('span');
    el.replaceChildren(span);
    return Promise.race([decodeText(span, text, { duration }), this.#skipped()]).then(() => {
      el.textContent = text;
    });
  }

  /** countUp through a detached proxy so skipping can snap the visible value safely. */
  #count(el, from, to, duration, format = plus) {
    if (this.#fast || from === to) {
      el.textContent = format(to);
      return Promise.resolve();
    }
    el.textContent = format(from);
    const proxy = document.createElement('span');
    const run = countUp(proxy, from, to, {
      duration,
      format,
      onTick: (value) => {
        if (this.#fast || !this.#alive) return;
        el.textContent = format(value);
        const now = performance.now();
        if (now - this.#lastTick >= TICK_MS) {
          this.#lastTick = now;
          this.#ctx.bus.emit('reward:tick', {});
        }
      },
    });
    return Promise.race([run, this.#skipped()]).then(() => {
      el.textContent = format(to);
    });
  }

  /** Wait `ms` — resolves at once when skipping (or already skipped). */
  #beat(ms) {
    if (this.#fast || ms <= 0 || !this.#alive) return Promise.resolve();
    return new Promise((resolve) => {
      const done = () => {
        clearTimeout(t);
        this.#timers.delete(t);
        this.#pending.delete(done);
        resolve();
      };
      const t = setTimeout(done, ms);
      this.#timers.add(t);
      this.#pending.add(done);
    });
  }

  /** A promise that resolves when (or if already) the reveal is skipped. */
  #skipped() {
    if (this.#fast) return Promise.resolve();
    return new Promise((resolve) => this.#pending.add(resolve));
  }

  #skip() {
    if (this.#revealed || this.#fast) return;
    this.#fast = true;
    this.el.classList.add('is-instant');
    for (const resolve of Array.from(this.#pending)) resolve();
    this.#pending.clear();
  }

  // ── actions ─────────────────────────────────────────────────────────

  #onCutscene(data) {
    if (!data || data.mission !== this.#mission.id) return;
    this.#setCastStatus(data.state);
  }

  #setCastStatus(state) {
    const el = this.#r.castStatus;
    if (!el) return;
    const text = state === 'rendering' || state === 'queued' ? 'RENDERING MEMORY FRAGMENT…' : state === 'done' ? 'MEMORY FRAGMENT READY' : 'IN-ENGINE';
    el.textContent = text;
    el.dataset.state = state;
  }

  /** `viaKey`: buttons get their click sound from main.js's delegation; keys need their own. */
  #play(viaKey = false) {
    if (this.#leaving || !this.#mission.cutscene) return;
    this.#leaving = true;
    if (viaKey) this.#ctx.bus.emit('ui:click', {});
    this.#ctx.screens.go('cutscene', { mission: this.#mission, result: this.#result, unlocked: this.#unlocked });
  }

  #hub(viaKey = false) {
    if (this.#leaving) return;
    this.#leaving = true;
    if (viaKey) this.#ctx.bus.emit('ui:click', {});
    this.#ctx.screens.go('hub', this.#unlocked ? { unlocked: this.#unlocked } : {});
  }
}
