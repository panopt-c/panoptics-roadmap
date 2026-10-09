/**
 * HubScreen — the operative's command hub (docs/ARCHITECTURE.md §4.2).
 *
 *   ┌ topbar: logo · target sector · Higgsfield feed chip · settings ─────────────┐
 *   │ OPERATIVE card      │ SECTOR MAP (5 sectors × 5 levels)    │ MEMORY        │
 *   │ portrait, callsign, │ a PCB-style circuit winding upward   │ FRAGMENTS     │
 *   │ rank, XP, breaches  │ from S0 to the Core                  │ (gallery)     │
 *   │ [ DEPLOY ▸ L0x ]    │                                      │               │
 *   └─────────────────────┴──────────────────────────────────────┴───────────────┘
 *
 * Sector map. Nodes are real <button>s (focusable, keyboard and screen-reader friendly);
 * the circuit underneath is one SVG whose geometry is computed in CSS pixels from the map's
 * size (ResizeObserver), so traces stay crisp and 45°-true at every aspect ratio. Sector 0
 * is the bottom row and rows alternate direction (boustrophedon); the row-to-row connector
 * jogs outward with chamfered corners like a circuit-board trace. Trace state follows the
 * level it leads to: cleared (sector colour + flowing pulses), active (dashes flowing toward
 * the next target) or locked (dim dotted).
 *
 * Arrival choreography: panels rise in with a stagger, traces draw along the path, nodes pop
 * in path order. `params.unlocked` holds the new node "sealed" until the map has settled,
 * then breaks it open (ring burst, `ui:unlock`, sparks) and draws its incoming trace.
 *
 * Live data: `state:changed` patches the view in place (XP counts up, nodes re-class, the
 * gallery re-renders only when its contents change). Cutscene renders in progress
 * (`server:cutscene`) show as "decoding" cards in the gallery.
 *
 * Memory fragments: rendered media (State.gallery) first, then one "in-engine transmission"
 * card per cleared mission that has a cutscene but no rendered media, so a breach without a
 * Higgsfield key still leaves something to re-watch. Candidates are the cleared levels that can
 * carry a cutscene (the first level and the bosses, GAME_DESIGN §9); each one's Mission payload
 * is fetched once per app session to confirm it has a cutscene, and opens the cutscene screen.
 *
 * Keys: Enter deploys the current target; O opens the command center (study & fitness);
 * arrows walk the map; Esc closes the fragment viewer (otherwise it falls through to the
 * settings menu).
 */
import { h, countUp } from '../dom.js';
import { settings } from '../../core/settings.js';
import { clamp, hexToRgb } from '../../core/math.js';
import { localDay, snapshotDay, isEarlierDay } from '../api.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const UNLOCK_DELAY_MS = 1050;
const XP_COUNT_MS = 1100;
const LEAVE_FLASH_MS = 90;
const SPARK_OPTS = { color: [0, 0.94, 1], count: 46 };
const AMBER = '#ffb000';
const PACKET_SPEED = 64; // px/s along cleared traces
const COMPACT_DY = 96;
const ACTIVE_SPEED = 46; // px/s into the current target

const STATUS_TEXT = {
  cleared: 'CLEARED',
  current: 'NEXT TARGET',
  encrypted: 'ENCRYPTED',
  locked: 'LOCKED',
};
const STATUS_CHIP = { cleared: 'chip--ok', current: '', encrypted: 'chip--warn', locked: 'chip--bad' };

const ICON_GEAR =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10.3 2h3.4l.5 2.6 1.7.8 2.3-1.4 2.4 2.4-1.4 2.3.8 1.7 2.6.5v3.4l-2.6.5-.8 1.7 1.4 2.3-2.4 2.4-2.3-1.4-1.7.8-.5 2.6h-3.4l-.5-2.6-1.7-.8-2.3 1.4-2.4-2.4 1.4-2.3-.8-1.7L2 13.7v-3.4l2.6-.5.8-1.7-1.4-2.3 2.4-2.4 2.3 1.4 1.7-.8z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
const ICON_LOCK =
  '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 7V5a3.5 3.5 0 0 1 7 0v2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M3 7h10v7H3z" fill="currentColor"/><path d="M8 9.5v2" stroke="var(--void)" stroke-width="1.6"/></svg>';
const ICON_CLOSE = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 3.5l9 9m0-9l-9 9" stroke="currentColor" stroke-width="1.6"/></svg>';
const ICON_TRANSMISSION =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8.5 6.8v10.4l8.6-5.2z" fill="currentColor"/></svg>';
const ICON_FRAGMENT =
  '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M8 12h20l-4 6h16v18H20l4-6H8z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M14 30l6-7 5 5 4-4 5 6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
const PORTRAIT_PLACEHOLDER =
  '<svg viewBox="0 0 120 120" aria-hidden="true"><defs><linearGradient id="hub-pp" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="currentColor" stop-opacity=".55"/><stop offset="1" stop-color="currentColor" stop-opacity=".05"/></linearGradient></defs><path d="M60 22c13 0 21 10 21 24 0 9-4 17-9 21v5c14 4 27 12 31 26H17c4-14 17-22 31-26v-5c-5-4-9-12-9-21 0-14 8-24 21-24z" fill="url(#hub-pp)"/><path d="M38 47h44" stroke="currentColor" stroke-opacity=".7" stroke-width="2"/></svg>';

const isMod = (e) => e.ctrlKey || e.metaKey || e.altKey;
const pad2 = (n) => String(n).padStart(2, '0');
const levelNumber = (id) => String(id).replace(/^\D+/, '');
const shortTitle = (title) => String(title).replace(/^BOSS:\s*/i, '');
const safeColor = (c) => (/^#[0-9a-f]{6}$/i.test(c || '') ? c : '#00f0ff');
const rgbTriplet = (hex) =>
  hexToRgb(hex)
    .map((v) => Math.round(v * 255))
    .join(', ');

export class HubScreen {
  #ctx;
  #alive = false;
  #leaving = false;
  #offs = [];
  #timers = new Set();
  #observer = null;
  #r = {};
  #levels = []; // flattened campaign in path order: {id, title, concept, status, boss, sector, color, rgb, row, col, index, el}
  #byId = new Map();
  #size = { w: 0, h: 0 };
  #sealed = null; // id held back for the unlock reveal
  #tipNode = null;
  #shown = null; // {xp, floor, value} last values the operative card displayed
  #renders = new Map(); // mission → stage, for cutscenes rendering right now
  #galleryKey = '';
  #lightbox = null;
  #opener = null; // element focused before the lightbox opened
  #geo = null; // last map geometry (see #geometry)
  #rows = 0;
  #unlockedNow = null; // id whose incoming trace draws during the unlock reveal
  // Cleared missions' cutscenes, for the in-engine transmission cards. Kept for the app's
  // lifetime (screens are singletons; cutscene content never changes): id → Mission | null.
  #transmissions = new Map();
  #transmissionsLoading = new Set();
  #transmissionsFailed = new Set(); // retried on the next visit
  #opsSnap = null; // the productivity snapshot the Daily ops card shows

  constructor(ctx) {
    this.#ctx = ctx;
    // Lives as long as the app (screens are singletons): tracks renders even while we're hidden.
    ctx.bus.on('server:cutscene', (e) => this.#onCutscene(e));
  }

  // ── lifecycle ─────────────────────────────────────────────────────────

  async enter(params = {}) {
    const ctx = this.#ctx;
    this.#alive = true;
    this.#leaving = false;
    this.#r = {};
    this.#levels = [];
    this.#byId.clear();
    this.#galleryKey = '';
    this.#tipNode = null;
    this.#lightbox = null;
    this.#size = { w: 0, h: 0 };
    this.#geo = null;
    this.#transmissionsFailed.clear();
    this.el = h('section', { class: 'screen screen--hub screen--staged', 'aria-label': 'Command hub' });

    ctx.bus.emit('mood', { name: 'calm' });
    ctx.renderer?.setFocus?.(0);

    let state = ctx.state;
    if (!state) {
      try {
        state = await ctx.refreshState();
      } catch (err) {
        if (this.#alive) this.#buildOffline(err);
        return;
      }
    }
    if (!this.#alive) return;

    const unlocked = typeof params.unlocked === 'string' ? params.unlocked : params.unlocked?.id;
    this.#build(state, unlocked);
    this.#offs.push(ctx.bus.on('state:changed', (s) => this.#update(s)));
    this.#offs.push(ctx.bus.on('server:productivity', (snap) => this.#onOpsPush(snap)));
    this.#loadOps();
  }

  async exit() {
    this.#alive = false;
    for (const off of this.#offs) off();
    this.#offs.length = 0;
    for (const t of this.#timers) clearTimeout(t);
    this.#timers.clear();
    this.#observer?.disconnect();
    this.#observer = null;
    for (const video of this.el?.querySelectorAll('video') ?? []) video.pause();
  }

  onKey(e) {
    if (this.#lightbox) {
      if (e.key !== 'Escape') return false;
      e.preventDefault();
      this.#closeLightbox();
      return true;
    }
    if (!this.#r.map || isMod(e)) return false;
    if (e.key === 'Enter' && !e.repeat) {
      const focused = document.activeElement;
      if (focused && focused !== document.body && this.el.contains(focused) && focused.matches('button, a, input, [tabindex]')) return false;
      e.preventDefault();
      this.#ctx.bus.emit('ui:click', {});
      this.#deployCurrent();
      return true;
    }
    if ((e.key === 'o' || e.key === 'O') && !e.repeat) {
      e.preventDefault();
      this.#openOps();
      return true;
    }
    const step = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [1, 0], ArrowDown: [-1, 0] }[e.key];
    if (step) {
      e.preventDefault();
      this.#walk(step[0], step[1]);
      return true;
    }
    return false;
  }

  // ── build ─────────────────────────────────────────────────────────────

  #build(state, unlocked) {
    const r = this.#r;
    this.#indexCampaign(state);
    const target = this.#byId.get(state.current);
    // Hold a freshly unlocked target back ("sealed") so it can be broken open once the map settles.
    const status = this.#byId.get(unlocked)?.status;
    this.#sealed = (status === 'current' || status === 'encrypted') && !settings.get('reducedMotion') ? unlocked : null;

    r.tip = this.#buildTip();
    this.el.append(
      this.#buildTopbar(state, target),
      h(
        'div',
        { class: 'hub' },
        h('div', { class: 'hub__left' }, this.#buildOperative(), this.#buildDeploy(), this.#buildOps()),
        this.#buildMap(state),
        this.#buildGallery(state),
      ),
      r.tip,
    );
    this.#renderOperative(state, true);
    this.#renderDeploy(state);

    this.#observer = new ResizeObserver((entries) => {
      const box = entries[entries.length - 1].contentRect;
      this.#layout(box.width, box.height);
    });
    this.#observer.observe(r.map);

    if (this.#sealed) this.#later(() => this.#unseal(), UNLOCK_DELAY_MS);
  }

  #indexCampaign(state) {
    const levels = [];
    for (const [row, sector] of (state.campaign || []).entries()) {
      const color = safeColor(sector.color);
      for (const [j, level] of (sector.levels || []).entries()) {
        levels.push({
          ...level,
          sector,
          row,
          col: row % 2 === 0 ? j : (sector.levels.length - 1) - j,
          index: levels.length,
          color,
          rgb: rgbTriplet(color),
          el: null,
        });
      }
    }
    this.#levels = levels;
    this.#byId = new Map(levels.map((l) => [l.id, l]));
    this.#rows = Math.max(1, (state.campaign || []).length);
  }

  #buildTopbar(state, target) {
    const r = this.#r;
    r.sectorChip = h('div', { class: 'hub-sector' });
    r.feed = h('span', { class: 'chip hub-feed' });
    this.#renderTopbar(state, target);
    return h(
      'header',
      { class: 'topbar hub-topbar rise', style: '--i: 0' },
      h(
        'div',
        { class: 'topbar__left' },
        h('span', { class: 'ns-logo ns-logo--sm', 'data-text': 'NULL//SECTOR' }, 'NULL//SECTOR'),
        h('span', { class: 'hub-topbar__rule', 'aria-hidden': 'true' }),
        h('span', { class: 'label' }, 'Command hub'),
      ),
      h('div', { class: 'topbar__center' }, r.sectorChip),
      h(
        'div',
        { class: 'topbar__right' },
        r.feed,
        h('button', { class: 'icon-btn icon-btn--gear', type: 'button', 'data-action': 'settings', 'aria-label': 'Settings (Esc)', title: 'Settings · Esc', html: ICON_GEAR }),
      ),
    );
  }

  #renderTopbar(state, target) {
    const r = this.#r;
    if (target) {
      const s = target.sector;
      r.sectorChip.style.cssText = `--accent: ${target.color}; --accent-rgb: ${target.rgb}`;
      r.sectorChip.replaceChildren(
        h('span', { class: 'hub-sector__index mono' }, `S${s.tier ?? target.row}`),
        h('span', { class: 'hub-sector__name' }, s.name),
        h('span', { class: 'hub-sector__zone label' }, s.zone),
      );
    } else {
      r.sectorChip.style.cssText = '--accent: var(--acid); --accent-rgb: 57, 255, 20';
      r.sectorChip.replaceChildren(h('span', { class: 'hub-sector__name' }, 'All sectors restored'));
    }
    const hf = state.higgsfield || {};
    r.feed.className = `chip hub-feed ${hf.online ? 'chip--ok chip--live' : 'hub-feed--off'}`;
    r.feed.textContent = hf.online ? 'Higgsfield feed · live' : 'Higgsfield feed · offline';
    r.feed.title = hf.online ? 'Cutscenes render with Higgsfield' : `In-engine cutscenes — ${hf.reason || 'no API key'}`;
  }

  #buildOperative() {
    const r = this.#r;
    r.portrait = h('div', { class: 'operative__portrait' });
    r.opId = h('span', { class: 'label mono operative__id' });
    r.callsign = h('div', { class: 'operative__callsign' });
    r.rank = h('div', { class: 'operative__rank' });
    r.xp = h('span', { class: 'mono operative__xp-now' }, '0');
    r.xpNext = h('span', { class: 'mono operative__xp-next' });
    r.meterFill = h('div', { class: 'meter__fill' });
    r.meter = h('div', { class: 'meter meter--ticks operative__meter', role: 'progressbar', 'aria-label': 'Experience to next rank', 'aria-valuemin': 0, 'aria-valuemax': 100 }, r.meterFill);
    r.xpNote = h('span', { class: 'label operative__xp-note' });
    r.breaches = h('span', { class: 'mono operative__breach-count' });
    r.strip = h('div', { class: 'breach-strip', 'aria-hidden': 'true' });

    return h(
      'section',
      { class: 'panel operative rise', style: '--i: 1', 'aria-label': 'Operative' },
      h('div', { class: 'panel__head' }, h('span', { class: 'panel__title' }, 'Operative'), r.opId),
      h(
        'div',
        { class: 'panel__body operative__body' },
        r.portrait,
        h('div', { class: 'operative__ident' }, h('span', { class: 'label' }, 'Callsign'), r.callsign),
        h('div', { class: 'operative__row' }, h('span', { class: 'label' }, 'Rank'), r.rank),
        h(
          'div',
          { class: 'operative__xp' },
          h('div', { class: 'operative__row' }, h('span', { class: 'label' }, 'XP'), h('span', { class: 'operative__xp-nums' }, r.xp, r.xpNext)),
          r.meter,
          r.xpNote,
        ),
        h('div', { class: 'operative__breach' }, h('div', { class: 'operative__row' }, h('span', { class: 'label' }, 'Breaches'), r.breaches), r.strip),
      ),
    );
  }

  #renderOperative(state, first) {
    const r = this.#r;
    const p = state.profile || {};
    const callsign = String(p.callsign || '').trim();

    r.opId.textContent = callsign ? `NS-${operativeHash(callsign)}` : 'NS-????';
    r.callsign.className = `operative__callsign${callsign ? '' : ' is-unregistered'}`;
    r.callsign.textContent = callsign ? callsign.toUpperCase() : 'UNREGISTERED';
    r.callsign.dataset.text = r.callsign.textContent;
    r.callsign.title = callsign ? '' : 'Clear L01 COLD BOOT to register your identity';
    r.rank.textContent = p.rank || '—';

    const portrait = (state.gallery || []).find((g) => g.mission === 'L01' && g.kind !== 'video' && g.url);
    const key = portrait ? portrait.url : '';
    if (r.portrait.dataset.key !== key || first) {
      r.portrait.dataset.key = key;
      r.portrait.classList.toggle('has-image', !!portrait);
      r.portrait.replaceChildren(
        portrait
          ? h('img', { src: portrait.url, alt: `${callsign || 'Operative'} — anchor avatar`, decoding: 'async' })
          : h('div', { class: 'operative__placeholder', html: PORTRAIT_PLACEHOLDER }),
        h('span', { class: 'operative__portrait-tag label' }, portrait ? 'ANCHOR AVATAR' : 'NO VISUAL'),
        h('span', { class: 'operative__scan', 'aria-hidden': 'true' }),
      );
    }

    // XP: count from what the card showed last (0 on first visit) to the server's verdict.
    const xp = Math.max(0, p.xp | 0);
    const floor = p.rank_floor | 0;
    const next = p.rank_next;
    const value = next ? clamp((xp - floor) / Math.max(1, next - floor)) : 1;
    const prev = this.#shown;
    const from = prev && prev.floor === floor ? prev.xp : first && !prev ? 0 : floor;
    this.#shown = { xp, floor, value };
    r.xpNext.textContent = next ? ` / ${next}` : '';
    countUp(r.xp, from, xp, { duration: XP_COUNT_MS });
    r.xpNote.textContent = next ? `${Math.max(0, next - xp)} XP to next rank` : 'Max rank reached';
    r.meter.classList.toggle('is-max', !next);
    r.meter.setAttribute('aria-valuenow', String(Math.round(value * 100)));
    const startValue = prev && prev.floor === floor ? prev.value : 0;
    r.meter.style.setProperty('--value', String(startValue));
    // The fill transitions from the start value once the screen is live.
    this.#later(() => r.meter.style.setProperty('--value', String(value)), first ? 420 : 60);

    r.breaches.textContent = `${pad2(p.breaches | 0)} / ${p.total_levels || this.#levels.length || 25}`;
    // Cells are created once and re-classed afterwards, so live updates never replay the entrance.
    if (r.strip.childElementCount !== this.#levels.length) {
      r.strip.replaceChildren(...this.#levels.map((l) => h('i', { style: `--c: ${l.color}; --c-rgb: ${l.rgb}; --n: ${l.index}` })));
    }
    for (const l of this.#levels) r.strip.children[l.index].className = `breach-strip__cell is-${l.status}`;
  }

  // ── command center entry (productivity) ───────────────────────────────

  #buildOps() {
    const r = this.#r;
    r.opsTitle = h('span', { class: 'hub-ops__title' }, 'Daily ops');
    r.opsSub = h('span', { class: 'hub-ops__sub' }, 'Syncing daily ops…');
    r.opsMeter = h('span', { class: 'meter meter--ticks hub-ops__meter', 'aria-hidden': 'true' }, h('span', { class: 'meter__fill' }));
    r.ops = h(
      'button',
      { class: 'btn btn--ghost hub-ops rise', style: '--i: 3', type: 'button', 'aria-keyshortcuts': 'O', onclick: () => this.#openOps() },
      h('span', { class: 'hub-ops__text' }, h('span', { class: 'hub-ops__kicker' }, 'Command center ▸'), r.opsTitle, r.opsSub),
      h('span', { class: 'kbd' }, 'O'),
      r.opsMeter,
    );
    // A cached snapshot of an earlier day is not today's: leave "Syncing…" until the GET lands.
    this.#opsSnap = null;
    const cached = this.#ctx.productivity;
    const day = snapshotDay(cached);
    if (cached && !(day && day < localDay())) this.#renderOps(cached);
    return r.ops;
  }

  /**
   * SSE `productivity`. A push for an earlier day than the card shows is a backfill's view of
   * that day (older servers broadcast it): keep today's numbers and re-fetch them instead.
   */
  #onOpsPush(snap) {
    if (!this.#alive || !snap || typeof snap !== 'object') return;
    if (this.#opsSnap && isEarlierDay(snap, this.#opsSnap)) {
      this.#ctx.productivity = this.#opsSnap;
      this.#loadOps();
      return;
    }
    this.#renderOps(snap);
  }

  #loadOps() {
    const ctx = this.#ctx;
    ctx.api
      .productivity()
      .then((snap) => {
        ctx.productivity = snap;
        if (this.#alive) this.#renderOps(snap);
      })
      .catch(() => {
        if (!this.#alive || ctx.productivity || !this.#r.ops) return;
        this.#r.ops.classList.add('is-offline');
        this.#r.opsSub.textContent = 'Offline — open to retry';
      });
  }

  #renderOps(snap) {
    const r = this.#r;
    if (!r.ops || !snap || typeof snap !== 'object') return;
    this.#opsSnap = snap;
    const study = snap.study || {};
    const goal = Number(study.goal_minutes) || 360;
    const today = Math.max(0, Number(study.today_minutes) || 0);
    const progress = Number.isFinite(Number(study.progress)) ? clamp(Number(study.progress), 0, 1) : clamp(today / goal, 0, 1);
    const fit = snap.fitness || {};
    const parts = [`Training ${Math.max(0, Number(fit.today_workout_minutes) || 0)} min`];
    if (fit.latest_weight_lbs !== null && fit.latest_weight_lbs !== undefined && Number.isFinite(Number(fit.latest_weight_lbs))) {
      parts.push(`${Number(fit.latest_weight_lbs).toFixed(1)} → ${Number(fit.target_weight_lbs) || 170} lb`);
    }
    r.ops.classList.remove('is-offline');
    r.ops.classList.toggle('is-complete', progress >= 1);
    r.opsTitle.textContent = `Study ${today} / ${goal} min`;
    r.opsSub.textContent = parts.join(' · ');
    r.opsMeter.style.setProperty('--value', String(progress));
    r.ops.setAttribute('aria-label', `Command center: study ${today} of ${goal} minutes today. ${parts.join(', ')}. Shortcut O.`);
  }

  #openOps() {
    if (this.#leaving) return;
    this.#ctx.bus.emit('ui:click', {});
    this.#ctx.screens.go('productivity');
  }

  #buildDeploy() {
    const r = this.#r;
    r.deployKicker = h('span', { class: 'deploy__kicker' });
    r.deployTitle = h('span', { class: 'deploy__title' });
    r.deployConcept = h('span', { class: 'deploy__concept' });
    r.deployKey = h('span', { class: 'kbd deploy__kbd' }, 'ENTER');
    r.deploy = h(
      'button',
      { class: 'btn btn--primary btn--lg deploy rise', style: '--i: 2', type: 'button', onclick: () => this.#deployCurrent() },
      h('span', { class: 'deploy__text' }, r.deployKicker, r.deployTitle, r.deployConcept),
      r.deployKey,
    );
    return r.deploy;
  }

  #renderDeploy(state) {
    const r = this.#r;
    const target = this.#byId.get(state.current);
    const btn = r.deploy;
    btn.classList.remove('is-encrypted', 'is-complete');
    btn.classList.toggle('btn--primary', !!target && target.status === 'current');
    if (!target) {
      btn.classList.add('is-complete');
      r.deployKicker.textContent = 'Campaign complete';
      r.deployTitle.textContent = 'ALL SECTORS RESTORED';
      r.deployConcept.textContent = 'The Core is yours. Replay any level from the map.';
      r.deployKey.hidden = true;
      btn.setAttribute('aria-label', 'Campaign complete');
      return;
    }
    r.deployKey.hidden = false;
    r.deployTitle.textContent = `${target.id} · ${target.title}`;
    if (target.status === 'encrypted') {
      btn.classList.add('is-encrypted');
      r.deployKicker.replaceChildren(h('span', { class: 'deploy__lock', html: ICON_LOCK }), 'Encrypted');
      r.deployConcept.textContent = 'Ask Claude to build the next level';
      btn.setAttribute('aria-label', `${target.id} ${target.title} is encrypted. Ask Claude to build the next level.`);
    } else {
      r.deployKicker.replaceChildren('Deploy', h('span', { class: 'deploy__chev', 'aria-hidden': 'true' }, '▸'));
      r.deployConcept.textContent = target.concept;
      btn.setAttribute('aria-label', `Deploy to ${target.id} ${target.title}`);
    }
  }

  #buildMap(state) {
    const r = this.#r;
    r.svg = document.createElementNS(SVG_NS, 'svg');
    r.svg.setAttribute('class', 'map__traces');
    r.svg.setAttribute('aria-hidden', 'true');
    r.bands = h('div', { class: 'map__bands', 'aria-hidden': 'true' });
    r.nodes = h('div', { class: 'map__nodes', role: 'group', 'aria-label': 'Levels' });
    r.packets = h('div', { class: 'map__packets', 'aria-hidden': 'true' });
    r.map = h('div', { class: 'map' }, r.bands, r.svg, r.packets, r.nodes);

    for (const level of this.#levels) {
      level.el = this.#buildNode(level);
      r.nodes.append(level.el);
    }
    const sectors = state.campaign || [];
    r.bandEls = sectors.map((sector, row) => {
      const color = safeColor(sector.color);
      const progress = h('span', { class: 'map__sector-progress mono' });
      const el = h(
        'div',
        { class: 'map__band', style: `--c: ${color}; --c-rgb: ${rgbTriplet(color)}; --n: ${row}` },
        h(
          'div',
          { class: 'map__sector' },
          h('span', { class: 'map__sector-index mono' }, `S${sector.tier ?? row}`),
          h('span', { class: 'map__sector-name' }, sector.name),
          h('span', { class: 'map__sector-zone' }, sector.zone),
          progress,
        ),
      );
      r.bands.append(el);
      return { el, progress, row };
    });
    this.#renderBands();

    const legend = h(
      'div',
      { class: 'map-legend', 'aria-hidden': 'true' },
      ...['cleared', 'current', 'encrypted', 'locked'].map((s) => h('span', { class: `map-legend__item is-${s}` }, h('i'), s === 'current' ? 'Target' : s)),
    );

    return h(
      'section',
      { class: 'panel hub-map rise', style: '--i: 3', 'aria-label': 'Sector map' },
      h('div', { class: 'panel__head' }, h('span', { class: 'panel__title' }, 'Sector map'), legend),
      h('div', { class: 'panel__body hub-map__body' }, r.map),
    );
  }

  #buildNode(level) {
    const node = h(
      'button',
      {
        class: 'map-node',
        type: 'button',
        'data-id': level.id,
        style: `--c: ${level.color}; --c-rgb: ${level.rgb}; --n: ${level.index}`,
        onclick: () => this.#activate(level),
        onpointerenter: () => this.#showTip(level, true),
        onpointerleave: () => this.#hideTip(level),
        onfocus: () => this.#showTip(level, false),
        onblur: () => this.#hideTip(level),
      },
      h('span', { class: 'map-node__ring', 'aria-hidden': 'true' }),
      h('span', { class: 'map-node__burst', 'aria-hidden': 'true' }),
      h('span', { class: 'map-node__hex', 'aria-hidden': 'true' }, h('span', { class: 'map-node__core' }, h('span', { class: 'map-node__glyph' }))),
      h('span', { class: 'map-node__tag', 'aria-hidden': 'true' }),
      h('span', { class: 'map-node__title', 'aria-hidden': 'true' }, shortTitle(level.title)),
    );
    this.#renderNode(level, node);
    return node;
  }

  #renderNode(level, node = level.el) {
    const sealed = this.#sealed === level.id;
    const status = sealed ? 'locked' : level.status;
    node.className = `map-node is-${status}${level.boss ? ' is-boss' : ''}${sealed ? ' is-sealed' : ''}`;
    node.setAttribute('aria-label', `${level.id} ${level.title} — ${STATUS_TEXT[level.status] || level.status}. ${level.concept}`);
    node.setAttribute('aria-disabled', String(!(status === 'cleared' || status === 'current')));
    const glyph = node.querySelector('.map-node__glyph');
    if (status === 'encrypted') glyph.innerHTML = ICON_LOCK;
    else glyph.textContent = levelNumber(level.id);
    const tag = node.querySelector('.map-node__tag');
    tag.textContent = status === 'current' ? 'Target' : status === 'encrypted' ? 'Encrypted' : level.boss ? 'Boss' : '';
  }

  #renderBands() {
    for (const band of this.#r.bandEls || []) {
      const levels = this.#levels.filter((l) => l.row === band.row);
      const cleared = levels.filter((l) => l.status === 'cleared').length;
      const live = levels.some((l) => l.status !== 'locked' && this.#sealed !== l.id);
      const current = levels.some((l) => l.status === 'current' || l.status === 'encrypted');
      band.el.classList.toggle('is-live', live);
      band.el.classList.toggle('is-current', current);
      band.el.classList.toggle('is-complete', cleared === levels.length && levels.length > 0);
      band.progress.textContent = live ? `${cleared}/${levels.length}` : 'LOCKED';
    }
  }

  // ── map geometry ──────────────────────────────────────────────────────

  /** Positions nodes, bands and every trace for a map of w × h CSS px. */
  #layout(w, hgt) {
    if (w < 10 || hgt < 10) return;
    const first = this.#size.w === 0;
    this.#size = { w, h: hgt };
    const g = (this.#geo = this.#geometry(w, hgt));
    const map = this.#r.map;
    map.style.setProperty('--dx', `${g.dx.toFixed(1)}px`);
    map.style.setProperty('--dy', `${g.dy.toFixed(1)}px`);
    map.style.setProperty('--lab', `${g.lab.toFixed(1)}px`);
    map.classList.toggle('is-compact', g.dy < COMPACT_DY); // short rows: locked labels yield to the tooltip
    for (const level of this.#levels) {
      const p = g.pos(level);
      level.x = p.x;
      level.y = p.y;
      level.el.style.left = `${p.x.toFixed(1)}px`;
      level.el.style.top = `${p.y.toFixed(1)}px`;
    }
    for (const band of this.#r.bandEls || []) {
      const y = g.rowY(band.row);
      band.el.style.top = `${(y - g.dy / 2).toFixed(1)}px`;
      band.el.style.height = `${g.dy.toFixed(1)}px`;
    }
    this.#drawTraces(first);
  }

  #geometry(w, hgt) {
    const rows = this.#rows;
    const cols = 5;
    const lab = clamp(w * 0.19, 104, 168);
    const x0 = lab + 62;
    const x1 = w - 60;
    const top = 46;
    const bottom = hgt - 56;
    const dx = (x1 - x0) / (cols - 1);
    const dy = rows > 1 ? (bottom - top) / (rows - 1) : 0;
    const rowY = (row) => bottom - row * dy;
    return { lab, x0, x1, dx, dy, rowY, pos: (l) => ({ x: x0 + l.col * dx, y: rowY(l.row) }) };
  }

  /** (Re)builds the SVG circuit. Traces are classed by the state of the level they lead to. */
  #drawTraces(animate) {
    const { w, h: hgt } = this.#size;
    if (!w || !this.#geo) return;
    const svg = this.#r.svg;
    svg.setAttribute('viewBox', `0 0 ${w.toFixed(1)} ${hgt.toFixed(1)}`);
    svg.setAttribute('width', w.toFixed(1));
    svg.setAttribute('height', hgt.toFixed(1));
    const defs = svgEl('defs');
    const glow = svgEl('g', { class: 'traces__glow' });
    const base = svgEl('g', { class: 'traces__base' });
    const flow = svgEl('g', { class: 'traces__flow' });
    const packets = [];
    const jog = 20;
    const bevel = Math.min(14, (this.#geo?.dy ?? 80) / 4);

    for (let i = 1; i < this.#levels.length; i++) {
      const a = this.#levels[i - 1];
      const b = this.#levels[i];
      let d;
      let stroke = b.color;
      let length;
      if (a.row === b.row) {
        d = `M${a.x.toFixed(1)} ${a.y.toFixed(1)}H${b.x.toFixed(1)}`;
        length = Math.abs(b.x - a.x);
      } else {
        length = 2 * jog + 2 * bevel * Math.SQRT2 + (a.y - b.y - 2 * bevel);
        const s = a.x > w / 2 ? 1 : -1;
        const xo = a.x + s * jog;
        const xb = a.x + s * (jog + bevel);
        d = `M${a.x.toFixed(1)} ${a.y.toFixed(1)}H${xo.toFixed(1)}L${xb.toFixed(1)} ${(a.y - bevel).toFixed(1)}V${(b.y + bevel).toFixed(1)}L${xo.toFixed(1)} ${b.y.toFixed(1)}H${b.x.toFixed(1)}`;
        const id = `hub-trace-${i}`;
        defs.append(
          svgEl(
            'linearGradient',
            { id, gradientUnits: 'userSpaceOnUse', x1: 0, y1: a.y.toFixed(1), x2: 0, y2: b.y.toFixed(1) },
            svgEl('stop', { offset: 0, 'stop-color': a.color }),
            svgEl('stop', { offset: 1, 'stop-color': b.color }),
          ),
        );
        stroke = `url(#${id})`;
      }
      const state = this.#traceState(a, b);
      // Only solid traces can draw in: pathLength=1 would rescale a dashed trace's pattern.
      const drawn = state === 'cleared' && animate;
      const attrs = { d, class: `trace trace--${state}${drawn ? ' is-drawing' : ''}`, style: `--n: ${i}` };
      if (drawn) attrs.pathLength = 1;
      const color = state === 'active' && b.status === 'encrypted' ? AMBER : b.color;
      if (state === 'cleared') {
        glow.append(svgEl('path', { d, class: 'trace-glow', stroke, style: `--n: ${i}` }));
        packets.push(this.#packet(d, length, b.color, PACKET_SPEED, i * 0.37));
      } else if (state === 'active') {
        const dur = length / ACTIVE_SPEED;
        packets.push(this.#packet(d, length, color, ACTIVE_SPEED, 0), this.#packet(d, length, color, ACTIVE_SPEED, dur / 2));
      }
      const path = svgEl('path', attrs);
      if (state === 'active') path.setAttribute('stroke', color);
      else if (state === 'cleared') path.setAttribute('stroke', stroke);
      base.append(path);
      if (this.#unlockedNow === b.id) flow.append(svgEl('path', { d, class: 'trace-reveal', pathLength: 1 }));
    }
    svg.replaceChildren(defs, glow, base, flow);
    this.#r.packets.replaceChildren(...packets);
  }

  /**
   * A "data packet": a short comet riding the trace on a CSS motion path. Moving packets are
   * composited layers, so the glass panel underneath never repaints (scrolling SVG dashes did,
   * every frame). Duration follows path length so every packet travels at the same speed.
   */
  #packet(d, length, color, speed, offset) {
    const dur = Math.max(0.8, length / speed);
    return h('i', {
      class: 'trace-packet',
      style: `offset-path: path('${d}'); --c-rgb: ${rgbTriplet(color)}; --dur: ${dur.toFixed(2)}s; --delay: ${(-(offset % dur)).toFixed(2)}s`,
    });
  }

  #traceState(a, b) {
    const sealedB = this.#sealed === b.id;
    if (a.status === 'cleared' && b.status === 'cleared') return 'cleared';
    if (a.status === 'cleared' && (b.status === 'current' || b.status === 'encrypted') && !sealedB) return 'active';
    return 'locked';
  }

  // ── unlock reveal ─────────────────────────────────────────────────────

  #unseal() {
    if (!this.#geo) {
      this.#later(() => this.#unseal(), 120); // the map hasn't been laid out yet (slow first frames)
      return;
    }
    const id = this.#sealed;
    const level = id && this.#byId.get(id);
    this.#sealed = null;
    if (!level || !this.#alive) return;
    const ctx = this.#ctx;
    this.#unlockedNow = id;
    this.#renderNode(level);
    this.#renderBands();
    this.#drawTraces(false);
    this.#unlockedNow = null;
    level.el.classList.add('is-unlocking');
    this.#later(() => level.el.classList.remove('is-unlocking'), 1400);

    const banner = h(
      'div',
      { class: `map-unlock${level.y < 110 ? ' is-below' : ''}`, style: `--c: ${level.color}; --c-rgb: ${level.rgb}; left: ${level.x}px; top: ${level.y}px` },
      h('span', { class: 'map-unlock__label' }, level.status === 'encrypted' ? 'Signal found · encrypted' : 'New target unlocked'),
      h('span', { class: 'map-unlock__title' }, `${level.id} · ${level.title}`),
    );
    this.#r.map.append(banner);
    this.#later(() => banner.remove(), 3200);

    ctx.bus.emit('ui:unlock', {});
    // No catalogue event covers a map unlock (§5); a light direct kick, tuned well below combat.
    ctx.camera?.addTrauma?.(0.14);
    const rect = level.el.getBoundingClientRect();
    if (rect.width) {
      SPARK_OPTS.color = hexToRgb(level.color);
      ctx.renderer?.particles?.emit?.('spark', rect.left + rect.width / 2, rect.top + rect.height / 2, SPARK_OPTS);
    }
    this.#r.deploy?.classList.add('is-fresh');
  }

  // ── tooltip ───────────────────────────────────────────────────────────

  #buildTip() {
    const r = this.#r;
    r.tipId = h('span', { class: 'map-tip__id mono' });
    r.tipStatus = h('span', { class: 'chip map-tip__status' });
    r.tipTitle = h('div', { class: 'map-tip__title' });
    r.tipConcept = h('div', { class: 'map-tip__concept' });
    r.tipSector = h('div', { class: 'map-tip__sector label' });
    r.tipHint = h('div', { class: 'map-tip__hint' });
    return h(
      'div',
      { class: 'map-tip', role: 'tooltip', 'aria-hidden': 'true' },
      h('div', { class: 'map-tip__head' }, h('div', { class: 'map-tip__where' }, r.tipId, r.tipSector), r.tipStatus),
      r.tipTitle,
      r.tipConcept,
      r.tipHint,
    );
  }

  #showTip(level, pointer) {
    const r = this.#r;
    if (!r.tip || !this.#alive) return;
    if (this.#tipNode === level) return;
    const status = this.#sealed === level.id ? 'locked' : level.status;
    this.#tipNode = level;
    r.tip.style.setProperty('--accent', status === 'encrypted' ? 'var(--amber)' : level.color);
    r.tip.style.setProperty('--accent-rgb', status === 'encrypted' ? '255, 176, 0' : level.rgb);
    r.tipId.textContent = level.id;
    r.tipStatus.className = `chip map-tip__status ${STATUS_CHIP[status] || ''}`;
    r.tipStatus.textContent = STATUS_TEXT[status];
    r.tipTitle.textContent = level.title;
    r.tipConcept.textContent = level.concept;
    r.tipSector.textContent = `S${level.sector.tier ?? level.row} · ${level.sector.zone}`;
    r.tipHint.textContent = this.#hint(level, status);
    r.tip.classList.toggle('is-playable', status === 'cleared' || status === 'current');

    // One layout read for the node and the screen, then a single transform write.
    const node = level.el.getBoundingClientRect();
    const host = this.el.getBoundingClientRect();
    const tipW = r.tip.offsetWidth || 260;
    const tipH = r.tip.offsetHeight || 120;
    let x = node.left - host.left + node.width / 2 - tipW / 2;
    let y = node.top - host.top - tipH - 26; // clears the node's tag
    const below = y < 64;
    if (below) y = node.bottom - host.top + 30; // and its title
    x = clamp(x, 12, host.width - tipW - 12);
    r.tip.style.transform = `translate3d(${x.toFixed(0)}px, ${y.toFixed(0)}px, 0)`;
    r.tip.classList.toggle('is-below', below);
    r.tip.classList.add('is-shown');
    if (pointer) this.#ctx.bus.emit('ui:hover', {});
  }

  #hideTip(level) {
    if (this.#tipNode !== level) return;
    this.#tipNode = null;
    this.#r.tip?.classList.remove('is-shown');
  }

  #hint(level, status) {
    if (status === 'cleared') return 'Replay · no XP';
    if (status === 'current') return 'Click to deploy';
    if (status === 'encrypted') return 'Ask Claude to build this level';
    const before = this.#levels[level.index - 1];
    return before ? `Clear ${before.id} first` : 'Locked';
  }

  // ── actions ───────────────────────────────────────────────────────────

  #activate(level) {
    const status = this.#sealed === level.id ? 'locked' : level.status;
    if (status === 'cleared' || status === 'current') return this.#deploy(level.id);
    this.#deny(level.el);
    if (status === 'encrypted') {
      this.#ctx.toast(`${level.id} ${level.title} is still encrypted. Ask Claude to build the next level.`, { kind: 'warn', title: 'ENCRYPTED' });
    }
  }

  #deployCurrent() {
    const state = this.#ctx.state;
    const target = state && this.#byId.get(state.current);
    if (!target) {
      this.#deny(this.#r.deploy);
      return;
    }
    if (target.status === 'current' && this.#sealed !== target.id) return this.#deploy(target.id);
    this.#deny(this.#r.deploy);
    if (target.status === 'encrypted') {
      this.#ctx.toast(`${target.id} ${target.title} is still encrypted. Ask Claude to build the next level.`, { kind: 'warn', title: 'ENCRYPTED' });
    }
  }

  #deploy(id) {
    if (this.#leaving || !this.#alive) return;
    this.#leaving = true;
    const level = this.#byId.get(id);
    level?.el.classList.add('is-launching');
    if (this.#ctx.state?.current === id) this.#r.deploy?.classList.add('is-launching');
    this.#hideTip(this.#tipNode);
    this.#later(() => this.#ctx.screens.go('mission', { id }), LEAVE_FLASH_MS);
  }

  #deny(el) {
    if (!el) return;
    this.#ctx.bus.emit('ui:error', {});
    el.classList.remove('is-denied');
    void el.offsetWidth; // restart the shake
    el.classList.add('is-denied');
    this.#later(() => el.classList.remove('is-denied'), 420);
  }

  /** Arrow-key navigation: drow = rows up/down (sector), dcol = columns left/right. */
  #walk(drow, dcol) {
    const focused = this.#levels.find((l) => l.el === document.activeElement);
    const from = focused || this.#byId.get(this.#ctx.state?.current) || this.#levels[0];
    if (!from) return;
    if (!focused) return from.el.focus();
    const to = this.#levels.find((l) => l.row === from.row + drow && l.col === from.col + dcol);
    to?.el.focus();
  }

  // ── gallery ───────────────────────────────────────────────────────────

  #buildGallery(state) {
    const r = this.#r;
    r.galleryCount = h('span', { class: 'chip hub-gallery__count mono' });
    r.galleryList = h('div', { class: 'hub-gallery__list' });
    this.#renderGallery(state);
    return h(
      'section',
      { class: 'panel hub-gallery rise', style: '--i: 4', 'aria-label': 'Memory fragments' },
      h('div', { class: 'panel__head' }, h('span', { class: 'panel__title' }, 'Memory fragments'), r.galleryCount),
      h('div', { class: 'panel__body hub-gallery__body scroll' }, r.galleryList),
    );
  }

  #renderGallery(state) {
    const r = this.#r;
    const items = (state.gallery || []).filter((g) => g && g.url);
    const renders = [...this.#renders.entries()];
    const transmissions = this.#transmissionCards(state, items);
    const breaches = Math.max(0, state.profile?.breaches | 0);
    const online = !!state.higgsfield?.online;
    const key = JSON.stringify([items.map((g) => g.url), renders, transmissions.map((m) => m.id), breaches > 0, online]);
    if (key === this.#galleryKey) return;
    this.#galleryKey = key;
    r.galleryCount.textContent = pad2(items.length + transmissions.length);

    const cards = renders.map(([mission, stage]) =>
      h(
        'div',
        { class: 'frag frag--rendering', role: 'status' },
        h('div', { class: 'frag__media' }, h('span', { class: 'frag__shimmer' })),
        h('div', { class: 'frag__meta' }, h('span', { class: 'frag__id mono' }, mission), h('span', { class: 'frag__title' }, `Decoding memory · ${stage === 'video' ? 'motion' : 'still'}`)),
      ),
    );
    items.forEach((item, i) => cards.push(this.#fragCard(item, i)));
    transmissions.forEach((mission, i) => cards.push(this.#transmissionCard(mission, items.length + i)));

    r.galleryList.classList.toggle('is-empty', !cards.length);
    if (!cards.length) {
      // Before the first clear there is nothing to recover yet; after it, say where it went.
      const [title, text] =
        breaches === 0
          ? ['No fragments recovered', 'Every breach restores a piece of who you were. Clear your first level to recover a memory.']
          : online
            ? ['Fragments decoding', 'Your breaches are logged. Memory fragments appear here as the feed renders their transmissions.']
            : ['Transmissions in-engine', 'Your breaches are logged. Transmissions play in-engine; rendered memory fragments collect here.'];
      r.galleryList.replaceChildren(
        h(
          'div',
          { class: 'hub-gallery__empty' },
          h('span', { class: 'hub-gallery__empty-icon', html: ICON_FRAGMENT }),
          h('p', { class: 'hub-gallery__empty-title' }, title),
          h('p', { class: 'hub-gallery__empty-text' }, text),
          online ? null : h('p', { class: 'hub-gallery__empty-note' }, 'Feed offline — add a Higgsfield key to config.json to render transmissions as fragments.'),
        ),
      );
      return;
    }
    if (transmissions.length && !online) {
      cards.push(h('p', { class: 'hub-gallery__note' }, 'Feed offline — transmissions replay in-engine. Add a Higgsfield key to config.json to keep rendered fragments.'));
    }
    r.galleryList.replaceChildren(...cards);
  }

  /**
   * Cleared missions with a cutscene and no rendered media yet, in campaign order. Unknown
   * candidates are fetched in the background; the gallery re-renders when they resolve.
   */
  #transmissionCards(state, items) {
    const media = new Set(items.map((g) => g.mission));
    const out = [];
    this.#levels.forEach((level, i) => {
      if (level.status !== 'cleared' || media.has(level.id) || this.#renders.has(level.id)) return;
      if (!(i === 0 || level.boss)) return; // only the first level and bosses carry cutscenes
      if (!this.#transmissions.has(level.id)) {
        this.#loadTransmission(level.id);
        return;
      }
      const mission = this.#transmissions.get(level.id);
      if (mission) out.push(mission);
    });
    return out;
  }

  #loadTransmission(id) {
    if (this.#transmissionsLoading.has(id) || this.#transmissionsFailed.has(id)) return;
    this.#transmissionsLoading.add(id);
    this.#ctx.api
      .mission(id)
      .then(
        (mission) => {
          const cut = mission?.cutscene;
          const ok = cut && typeof cut === 'object' && (cut.title || (Array.isArray(cut.narration) && cut.narration.length));
          this.#transmissions.set(id, ok ? mission : null);
        },
        () => this.#transmissionsFailed.add(id),
      )
      .finally(() => {
        this.#transmissionsLoading.delete(id);
        if (this.#alive && this.#r.galleryList && this.#ctx.state) this.#renderGallery(this.#ctx.state);
      });
  }

  #transmissionCard(mission, i) {
    const level = this.#byId.get(mission.id);
    const color = level?.color || safeColor(mission.sector?.color);
    const title = mission.cutscene?.title || mission.title || 'Transmission';
    return h(
      'button',
      {
        class: 'frag frag--transmission',
        type: 'button',
        style: `--n: ${i}; --c-rgb: ${level?.rgb || rgbTriplet(color)}`,
        'aria-label': `Replay transmission ${mission.id} — ${title} (in-engine)`,
        onclick: () => this.#playTransmission(mission),
      },
      h(
        'span',
        { class: 'frag__media frag__media--signal', 'aria-hidden': 'true' },
        h('span', { class: 'frag__signal-grid' }),
        h('span', { class: 'frag__play', html: ICON_TRANSMISSION }),
      ),
      h('span', { class: 'frag__meta' }, h('span', { class: 'frag__id mono' }, mission.id), h('span', { class: 'frag__title' }, title)),
      h('span', { class: 'frag__kind is-engine' }, 'In-engine'),
    );
  }

  #playTransmission(mission) {
    if (this.#leaving || !this.#alive) return;
    this.#leaving = true;
    this.#hideTip(this.#tipNode);
    this.#ctx.screens.go('cutscene', { mission });
  }

  #fragCard(item, i) {
    const video = item.kind === 'video';
    const media = video
      ? h('video', { src: `${item.url}#t=0.1`, muted: true, loop: true, playsinline: true, preload: 'metadata', 'aria-hidden': 'true' })
      : h('img', { src: item.url, alt: '', loading: 'lazy', decoding: 'async' });
    if (video) media.muted = true;
    media.addEventListener('error', () => card.classList.add('is-broken'), { once: true });
    const card = h(
      'button',
      {
        class: 'frag',
        type: 'button',
        style: `--n: ${i}`,
        'aria-label': `View memory fragment ${item.mission} — ${item.title}`,
        onclick: () => this.#openLightbox(item),
        onpointerenter: video ? () => media.play().catch(() => {}) : null,
        onpointerleave: video ? () => media.pause() : null,
      },
      h('span', { class: 'frag__media' }, media, h('span', { class: 'frag__broken label' }, 'Signal corrupted')),
      h('span', { class: 'frag__meta' }, h('span', { class: 'frag__id mono' }, item.mission), h('span', { class: 'frag__title' }, item.title || 'Untitled')),
      h('span', { class: `frag__kind${video ? ' is-video' : ''}` }, video ? 'Motion' : 'Still'),
    );
    return card;
  }

  #openLightbox(item) {
    if (this.#lightbox || !this.#alive) return;
    const video = item.kind === 'video';
    const media = video
      ? h('video', { src: item.url, autoplay: true, loop: true, playsinline: true, controls: true, class: 'lightbox__media' })
      : h('img', { src: item.url, alt: item.title || '', class: 'lightbox__media' });
    const close = h('button', { class: 'icon-btn lightbox__close', type: 'button', 'aria-label': 'Close (Esc)', html: ICON_CLOSE, onclick: () => this.#closeLightbox() });
    const box = h(
      'div',
      { class: 'lightbox', role: 'dialog', 'aria-modal': 'true', 'aria-label': `Memory fragment ${item.mission}`, onclick: (e) => e.target === box && this.#closeLightbox() },
      h(
        'figure',
        { class: 'lightbox__frame' },
        media,
        h('figcaption', { class: 'lightbox__caption' }, h('span', { class: 'mono' }, item.mission), h('span', { class: 'lightbox__title' }, item.title || ''), h('span', { class: 'kbd' }, 'ESC')),
        close,
      ),
    );
    this.#lightbox = box;
    this.#opener = document.activeElement;
    this.el.append(box);
    this.#ctx.bus.emit('ui:open', {});
    requestAnimationFrame(() => box.classList.add('is-open'));
    close.focus({ preventScroll: true });
  }

  #closeLightbox() {
    const box = this.#lightbox;
    if (!box) return;
    this.#lightbox = null;
    box.querySelector('video')?.pause();
    box.classList.remove('is-open');
    this.#ctx.bus.emit('ui:close', {});
    this.#later(() => box.remove(), 260);
    if (!this.#alive) box.remove();
    if (this.#opener?.isConnected) this.#opener.focus({ preventScroll: true });
    this.#opener = null;
  }

  #onCutscene(e) {
    if (!e || !e.mission) return;
    if (e.state === 'rendering') this.#renders.set(e.mission, e.stage || 'still');
    else this.#renders.delete(e.mission);
    if (this.#alive && this.#r.galleryList && this.#ctx.state) this.#renderGallery(this.#ctx.state);
  }

  // ── live updates ──────────────────────────────────────────────────────

  #update(state) {
    if (!this.#alive || !this.#r.map || !state?.campaign) return;
    const byId = new Map();
    for (const sector of state.campaign) for (const l of sector.levels || []) byId.set(l.id, l);
    for (const level of this.#levels) {
      const next = byId.get(level.id);
      if (!next || next.status === level.status) continue;
      level.status = next.status;
      this.#renderNode(level);
    }
    const target = this.#byId.get(state.current);
    this.#renderTopbar(state, target);
    this.#renderOperative(state, false);
    this.#renderDeploy(state);
    this.#renderBands();
    this.#drawTraces(false);
    this.#renderGallery(state);
  }

  #buildOffline(err) {
    const retry = h(
      'button',
      {
        class: 'btn btn--primary',
        type: 'button',
        onclick: async () => {
          retry.disabled = true;
          try {
            const state = await this.#ctx.refreshState();
            if (!this.#alive) return;
            this.el.replaceChildren();
            this.#build(state, null);
            this.#offs.push(this.#ctx.bus.on('state:changed', (s) => this.#update(s)));
          } catch {
            retry.disabled = false;
            this.#deny(retry);
          }
        },
      },
      'Retry link',
    );
    this.el.append(
      h(
        'div',
        { class: 'hub-offline panel rise', style: '--accent: var(--amber); --accent-rgb: 255, 176, 0' },
        h('div', { class: 'panel__head' }, h('span', { class: 'panel__title' }, 'No signal')),
        h(
          'div',
          { class: 'panel__body' },
          h('p', { class: 'hub-offline__code mono' }, `ERR::${err?.status ?? 0} — ${err?.message || 'no response'}`),
          h('p', null, 'The game server did not answer. Make sure ', h('code', null, 'python game.py'), ' is running, then retry.'),
          retry,
        ),
      ),
    );
  }

  #later(fn, ms) {
    const t = setTimeout(() => {
      this.#timers.delete(t);
      if (this.#alive) fn();
    }, ms);
    this.#timers.add(t);
    return t;
  }
}

function svgEl(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) el.setAttribute(k, String(v));
  el.append(...children);
  return el;
}

/** A stable four-hex "operative ID" derived from the callsign (cosmetic). */
function operativeHash(text) {
  let x = 0x811c9dc5;
  for (const ch of text) x = Math.imul(x ^ ch.codePointAt(0), 0x01000193);
  return ((x >>> 0) & 0xffff).toString(16).toUpperCase().padStart(4, '0');
}
