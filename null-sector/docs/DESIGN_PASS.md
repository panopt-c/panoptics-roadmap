# NULL//SECTOR: design pass (taste skills applied)

Status: implemented (P0 793cc6f, P1 657220d, P2 in the commit that follows them); see §8 for
what changed from the spec while executing it. Written against `HEAD` 1356694 (branch
`claude/keen-mayer-xso05z`). Audience: the engineer who executes it.

Inputs: `.agents/skills/redesign-existing-projects` (method: audit first, keep what works,
upgrade without breaking behaviour), `design-taste-frontend` (anti-slop rules, pre-flight),
`industrial-brutalist-ui` (tactical-telemetry / CRT terminal direction), `high-end-visual-design`
(spacing, type, depth, motion), and the art bible in `docs/ARCHITECTURE.md` §6. The skills'
stack instructions (React, Tailwind, GSAP, npm installs, image generation, picsum photos) are
ignored on purpose: the client stays plain ES modules + hand-written CSS with no build step.

Contents

0. How the pass was run
1. The keep list (identity that must survive)
2. Systemic findings (cross-screen)
3. Per-screen audit
4. Refined design system (tokens)
5. Prioritised change list, per file
6. Test contract: selectors, text and keys that must not change
7. Verification checklist

---

## 0. How the pass was run

**Design read** (design-taste-frontend §0.B): *reading this as a redesign-preserve of a
dark-mode, keyboard-first game HUD for people learning Python, with a tactical-telemetry / CRT
language (industrial-brutalist §2.2), leaning toward the existing hand-written token system,
Chakra Petch + JetBrains Mono, and event-driven juice.*

**Dials.** Measured on the current build, then the target:

| Dial | Now | Target | Why |
|---|---|---|---|
| DESIGN_VARIANCE | 4 (rigid 3-column HUD grids) | 4 | A cockpit should be predictable; variance goes into the moments (victory, cutscene), not the layout. |
| MOTION_INTENSITY | 8 at rest (48 `infinite` animation declarations across the CSS) | 6 at rest, 8 on events | Keep every event reaction (hack, stamps, unlock, deletion); cut idle loops that compete with the one live thing on screen. |
| VISUAL_DENSITY | 7 (cockpit) | 7 | Right for the mission screen; what is missing is hierarchy inside the density, not air. |

**Which skill rules apply to a game and which do not.** Applied with judgement:

- Applied: WCAG AA contrast for all text (the biggest finding), shape-consistency lock (one
  documented corner-cut grammar), button/CTA wrap ban, "motion must be motivated", reduced
  motion, mobile collapse declared per layout, `min-height: 100dvh` thinking, tabular numbers,
  one focus style, glow only where it carries meaning, z-index scale, no duplicated intent.
- Deliberately not applied: "max one accent colour" (the bible's colours are *semantic roles*:
  cyan system, magenta narrative, acid success, amber warning/intel, blood enemy/failure, plus
  per-sector colours; they stay, but each gets a job and a budget); "no neon glows" (glow is the
  bible's information channel; it gets a budget instead of a ban); the eyebrow cap and the
  uppercase-label ban (tiny tracked uppercase labels *are* the telemetry language,
  industrial-brutalist §3.2; the fix is fewer sizes and enough contrast, not sentence case);
  "real photography / hero image"; the Inter/Roboto ban (not used); landing-page hero rules.
- The gradient wordmark (cyan to violet to magenta) is the one "AI gradient" fingerprint in the
  build. It is the brand mark (logo + favicon), so it stays (design-taste §11.F: never change
  the logo silently) but it must not spread to any other element.

**Capture method.** `git archive HEAD null-sector` into a scratch folder, seeded saves (fresh,
L01 ready, L01 cleared, mid-campaign L08, bosses L05/L10, campaign complete, story flags set
per state), `python3 game.py --no-browser --port <p>` per run, headless Chromium (software
WebGL2 via SwiftShader, about 4 fps, so screenshots were taken after 1.2 to 2.6 s settles; a
few animated states were caught mid-transition and are labelled where cited).
Viewports 1440x900, 1280x720, 390x844.

Screenshots: `/tmp/claude-0/-home-user-panoptics-roadmap/5e27923e-bb40-5368-9f28-c27197b4879d/scratchpad/design/before/`
(cited below as `before/<name>--<width>.png`). Capture scripts sit next to it in `scripts/`.

**Contrast method.** WCAG 2.x relative luminance. Text is measured against its *real*
background: the glass panel composite `rgba(10,14,22,.62)` over the dark world, which computes
to `#0a0c14` and matches pixels sampled from the screenshots (`rgb(6,10,15)` to `rgb(6,22,30)`
inside panels; `rgb(4,8,12)` in the editor). Alpha-faded text is composited first. Script:
`scripts/contrast.py`.

---

## 1. The keep list (identity that must survive)

These already work and every change below is designed around them:

1. **The world as the set.** The WebGL Dead Zone (Core beam, flooded skyline, rain) behind
   every screen, recoloured by mood (green on victory, violet in story). No UI
   change may cover it with opaque surfaces at rest.
2. **Glass panels with chamfered corners, a hairline frame whose chamfer diagonals glow, and
   two corner brackets** (`.panel`, `.panel::before`, `.panel::after`). This is the signature
   component; the fix is to make the rest of the UI (dialogue, alerts) speak the same grammar.
3. **The type pair**: Chakra Petch (display, uppercase, tracked) + JetBrains Mono (code, data,
   numbers, machine voice). Ligatures off for code (players learn what to type). Keep.
4. **Semantic colour roles** from the bible (above). Sector colours on the map and in the
   breach strip.
5. **The hack choreography**: charge sweep over the editor, firewall shards breaking left to
   right, layer rows flipping BREACHED/BLOCKED, INTEL cards unfolding, enemy deletion glitch,
   combo counter, particles. `before/15-hack-progress--1440.png`, `before/31-hack-progress-boss5--1440.png`.
6. **The victory ceremony** beats (decode title, DELETED stamp slam, count-ups, SPEED BONUS
   stamp, XP meter roll-over, RANK UP unfurl, IDENTITY line, actions) and skip-on-any-key.
   `before/21b-victory-focus--1280.png`.
7. **The cutscene film language**: 2.39:1 letterbox, REC + timecode HUD in the bars, title card
   with breathing tracking, typed subtitles with a magenta caret. Settled title card is the
   strongest frame in the game: `before/33-cutscene-boss5-title--1440.png`.
8. **The sector map**: bottom-up serpentine circuit, hex nodes, 45-degree traces, data packets,
   unlock burst, boss labels. `before/35-hub-complete--1440.png`.
9. **The boot BIOS log** and "PRESS ANY KEY TO JACK IN". `before/01-boot--1440.png`.
10. **Accessibility already done right**: reduced motion (OS + in-game, global collapse in
    `app.css` "modes"), native `<dialog>` for story lines (focus trapped, focus restored),
    restore confirm with Cancel focused by default and Esc closing, `aria-*` on tabs, ring,
    chart, map nodes as buttons, `quality-low` / `no-webgl` fallbacks that drop blur and make
    glass opaque so contrast holds.
11. **The Command Center's responsive rules** (`productivity.css` 1280/900/560 breakpoints):
    it is the only primary screen that already works at 390 px (`before/07-command-center--390.png`)
    and is the model for hub and mission.

---

## 2. Systemic findings (cross-screen)

Numbers come from the stylesheets at `HEAD` (`app.css`, `mission.css`, `victory.css`,
`cutscene.css`, `story.css`, `dialogue.css`, `editor.css`).

### 2.1 Typography

- **34 distinct font sizes** (8.5, 9, 9.5, 10, 10.5, 11, 11.5, 12, 12.5, 12.75, 13, 13.5, 14,
  14.5, 15, 16, 17, 18, 19, 20, 21, 22, 24, 25, 26, 32, 34, 38, 40, 46, 72, 84, 108, 116 px).
  Half-pixel steps (10 vs 10.5, 12 vs 12.5) are not distinguishable as hierarchy; they read as
  noise. Target: 9 steps (§4.1).
- **Text below 10 px** in 18 rules: `.map-node__title` 8.5, `.map-node__tag` 8.5,
  `.frag__kind` 8.5, `.enemy__readout` 8.5, `.map-legend__item` 9, `.map__sector-zone` 9,
  `.map-tip__sector` 9, `.map-unlock__label` 9, `.layer__state` 9, `.mission-target__live` 9,
  `.mission-timer__note` 9, `.operative__portrait-tag` 9, `.victory__cast` 9,
  `.operative__xp-note` 9.5, `.log-line__tag` 9.5, `.log-head` 9.5, `.mission-title__sector` 9.5,
  `.cs-status__stage` 9.5. Uppercase + 0.12 to 0.2 em tracking at 8.5 px is below legibility
  at 1x DPR. Floor: 10 px.
- **About two dozen distinct letter-spacing values** (0.02 to 0.5 em). Target: 4 tracking tokens + one
  "kicker" value used once per screen.
- **Mono vs display is mostly right**: numbers are mono with tabular figures (timer, XP, counts),
  code is mono, UI is display. The dialogue body is mono (CIPHER speaking through a terminal)
  while cutscene subtitles are display (narrator). That is a coherent rule, so it is written
  down (§4.3) rather than changed.
- **Display weights**: only 500/600/700 are loaded; hierarchy uses 600 vs 700 plus colour. Fine.
- **Line length**: briefing text runs about 40 ch in the 300 to 345 px left column, dialogue about
  62 ch, settings hints short. No long-measure problem.

### 2.2 Spacing

No scale. Gaps and paddings use 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 22, 24 px.
Visible symptoms: hub left column stacks at 14 px while the grid gutter is 23 px at 1440
(`before/04-hub-fresh--1440.png`: the DEPLOY card sits closer to OPERATIVE than any panel sits
to its neighbour); `.operative__body` gap 13 px; `.operative__xp` 7 px. Target: 4 px grid (§4.4).

### 2.3 Colour and contrast (measured)

The palette values are fine; the failure is one token used for text. `--dim #4a5160` measures
**2.45:1** on the glass and is used as a text colour in **35 rules** (13 in `app.css`, 7 in
`mission.css`, 3 in `victory.css`, 2 in `story.css`, 10 in `productivity.css`). Faded steel
(`rgba(136,146,166,.42 to .6)`) and faded dim are used for the map's labels.

| Text (selector) | Size | Ratio | AA (4.5) |
|---|---|---|---|
| `--text` on glass | any | 14.32 | pass |
| `--steel` on glass (`.label`, `.rich`, ghost buttons) | 10.5 to 14 | 6.24 | pass |
| `--cyan` / `--acid` / `--amber` on glass | any | 13.86 / 14.40 / 10.66 | pass |
| `--magenta` / `--blood` on glass | any | 6.11 / 5.45 | pass |
| `--dim` on glass (`.setting__hint`, `.objective__index`, `.layer__state` QUEUED, `.operative__xp-note`, `.map-legend__item`, `.mission-timer__par`, `.hub-gallery__empty-note`, ...) | 9 to 11.5 | 2.25 to 2.51 | **fail** |
| `--dim` on void (`.boot__meta`) | 10.5 | 2.54 | **fail** |
| `.map__sector-name` (steel @ 55%) | 12 | 2.65 | **fail** |
| `.map__sector-zone`, `.map__sector-progress` (dim @ 95%) | 9 / 10 | 2.34 | **fail** |
| `.map-node__title` (steel @ 42%) | 8.5 | 2.01 | **fail** |
| `.map-node__tag` BOSS (steel @ 50%) | 8.5 | 2.38 | **fail** |
| `.map__sector-index` locked (dim @ 90%) | 18 | 2.20 | **fail** (even as large text) |
| `.enemy__readout` (blood @ 60%) | 8.5 | 2.54 | **fail** |
| **`--syn-comment #66758b`** in the editor (the objective instructions live in comments) | 14 | **4.30** | **fail** |
| `.ce-num #343c4b` line numbers on `#060910` | 14 | 1.80 | fail (supplementary, target 3:1) |
| `.ce-gcur #5d6b80` (current line number, editor blurred) | 14 | 3.68 | ok as UI |
| `.boot__sub` steel where it crosses the Core beam (sampled `rgb(130,126,132)`) | 13 | **about 1.2** | **fail** (`before/01-boot--1440.png`, "EN GINEER") |
| `.cs-hud__src` IN-ENGINE RECONSTRUCTION (steel @ 70% on black) | 10.5 | 3.64 | fail |
| `.cs-skip` SKIP (steel x .75 opacity on black) | 10.5 | about 4.1 | fail |
| `.victory__skip` ANY KEY SKIP (steel x .55 opacity) | 10.5 | 2.62 | fail |
| `.reward--missed` (dim) on the victory backdrop | 13 | 2.33 | fail |
| `.btn--primary` void on cyan @ 86% | 12.5 | 10.68 | pass |
| `.victory__play` void on magenta @ 86% | 14.5 | 4.90 | pass (keep the fill at least 86%) |
| `.dialogue__label` `#8299a9` on `#0a1420` | 11 | 6.24 | pass |
| Ghost button ring (cyan @ 28%) | UI | 2.02 | below 3:1; the label carries the affordance, still worth raising |

Proposed values (measured on the same composite): `--meta #7c879b` 5.39:1 (5.18 on a magenta
panel head, 5.13 on the victory backdrop, 5.68 on boot void, 5.80 on cutscene bars, 5.50 on the
editor gutter); `--text-2 #a3acbe` 8.56:1; `--muted #5f6a7d` 3.57:1 (locked/disabled only);
`--syn-comment #7a879c` 5.54:1; `--ce-num #5b667a` 3.44:1; ring alpha .55 on cyan 4.66:1.

**Neon overuse.** A fresh hub shows five accents at once (cyan panels and DEPLOY, acid S0 band
and target node, magenta gallery frame + rank + STORY button, blood UNREGISTERED, amber legend),
`before/04-hub-fresh--1440.png`. That is semantic, so it stays, but two of them are louder
than their job: the **memory-fragments panel frame** is full magenta at the same intensity as
the map, and **LOCKED chips are blood red** (`STATUS_CHIP.locked = 'chip--bad'` in `hub.js`, also
in the story archive, `before/26-story-archive--390.png`): locked is not failure.

**Latent bug.** `tokens.css` defines `--glow-sm`, `--glow-md` and `--text-glow` on `:root` with
`rgba(var(--accent-rgb), …)`. A custom property's `var()` resolves where it is declared, so
these are always **cyan**, whatever `--accent-rgb` a component sets. `productivity.css` uses
`--text-glow` on `.ops-big` inside the magenta fitness panel and gets a cyan halo. Any new
accent-relative token must be an *alpha* token (`--a-line: .35`) combined at the use site.
Also: the rgb triplets (`255, 43, 214` etc.) are re-declared locally in `mission.css`,
`victory.css`, `cutscene.css` and typed as literals in about 30 rules.

### 2.4 Borders, corners, glows

- **Eight chamfer sizes** (`--c` 5, 6, 7, 8, 9, 10, 12, 14 px) plus `border-radius` 2 to 3 px
  (`.kbd`, `.rich code`) and circles (live dots, `.frag__play`, `.cs-status__ring`).
- **Three corner-cut grammars**: structural (top-left + bottom-right: panels, buttons, chips),
  alert (top-right + bottom-left: `.mission-conflict`, `.mission-restore-bar`, `.cs-status`),
  toast (top-right only). Plus **none**: `.dialogue` is a plain rectangle with a 100% speaker
  border and a 44 px glow (`before/10-dialogue-intro--1440.png`), the only overlay that does not
  speak the panel language. Shape-consistency lock: two grammars with a written rule are fine
  (structural vs alert); the dialogue and the toast are the outliers.
- **32 `text-shadow` declarations** in the five core stylesheets. The bible says "glow is
  earned: only interactive or live elements glow", but static text glows: `.operative__callsign`,
  `.operative__rank`, `.hub-sector__index`, `.map__band.is-live .map__sector-index`,
  `.story-chapter__index`, `.mission-target__name`, `.victory__callsign`, every `.reward__value`;
  every `.panel__title::before` diamond has a `box-shadow`; every cleared map node has a
  `drop-shadow`. On the complete map that is 25 glowing hexes + 25 traces + packets
  (`before/35-hub-complete--1440.png`): the circuit reads as one smear and the current target,
  when there is one, has nothing left to win attention with.

### 2.5 Motion and juice

Event motion is excellent and consistent (`--ease-out` 140/220/420 ms, springs on `--ease-back`).
Idle motion is not budgeted. At rest the fresh hub runs: logo glitch, portrait scan (5.5 s),
UNREGISTERED glitch (3.4 s), breach-strip `cell-blink`, `deploy__chev` nudge, current-node
`node-pulse`, current-node `tag-bob`, encrypted `lock-glitch`, trace packets, CRT flicker. Three
of those say the same thing ("this is your next target": pulse, tag bob, cell blink) and one
competes with the CTA it decorates (chevron nudge). Hard-coded durations: 260, 320, 460, 480,
520, 560, 600, 620, 640, 700, 760, 900, 1000, 1100, 1300, 1800 ms outside the tokens.

### 2.6 Hierarchy and density

- **Hub**: focal pair should be DEPLOY + current node. DEPLOY wins (only filled surface), but
  the magenta gallery column competes at equal weight, and on a fresh save the gallery spends a
  full column on an empty state (`before/04-hub-fresh--1440.png`).
- **Mission**: the editor is the focal point of a coding game, yet it is the column that gets
  squeezed. At 1440 the centre column is 650 px, about **64 columns** of 14 px mono after the
  gutter; mission starters are up to **81 columns** wide (L01: 16 lines over 72). The header
  rule and "TARGET: WATCHDOG" are cut at the right edge in every mission shot
  (`before/11-mission-brief--1440.png`, `before/11-mission-brief--1280.png`: about 56 columns).
- **Objectives are shown twice**: the left OBJECTIVES list and the right layer list carry the
  same seven names (`before/11-mission-brief--1440.png`).
- **Victory**: correct top-down order, one focal number (TOTAL XP), but five accents stacked in
  600 px (acid panel, red stamp, amber stamp, magenta rank band, cyan identity line).

### 2.7 Mobile and narrow windows (390 px)

The realistic narrow case is not a phone; it is a browser docked beside the IDE, because the
documented loop is `python game.py watch` (every save auto-attacks). Today:

- **Mission < 1100 px has no layout**: the three fixed-minimum columns (256 + 272 px +
  gutters) exceed 390 px, the editor column collapses to **0 px** and the grid scrolls
  sideways (`before/11-mission-brief--390.png`, `before/16-hack-failed--390.png`). The game is
  not playable below about 800 px.
- **Hub < 768 px**: the 2-column fallback keeps a 252 px left column, the map gets about 100 px
  and is cut, topbar items overlap the logo (`before/24-hub-l01-cleared--390.png`).
- **Victory** title `ACCESS GRANTED` is `white-space: nowrap` with a 40 px minimum: clipped at
  both edges at 390 (`before/21-victory-l01-full--390.png`).
- **Settings**: fixed `230px 50px` control columns overlap the labels ("MASTER VOLUME" under
  its slider, `before/06-settings--390.png`); the footer stats wrap to four lines.
- **Cutscene**: the letterbox formula gives 340 px bars on a 844 px tall screen, leaving a
  163 px picture strip (`before/03-prologue-narration--390.png`).
- **Boot**: BIOS lines overflow the right edge ("UNREGISTE"), the subtitle breaks into a 2x2
  block (`before/01-boot--390.png`).
- Works: story archive (`before/26-story-archive--390.png`), command center, dialogue.

### 2.8 Keyboard focus

Five different focus styles: default `1px dashed accent @ 90%`, offset 3 px (square rectangle
around chamfered shapes, `before/05-hub-focus--1440.png`, `before/18-mission-focus--1440.png`,
`before/21b-victory-focus--1280.png`); `.mission-tab` 1 px solid inset; `.dialogue button`
**2 px solid amber** (amber means warning/intel, `before/10-dialogue-intro--1440.png`);
`.map-node` 1 px dashed in sector colour, offset 6 px; `.frag`, `.story-chapter` use an inner
`box-shadow` (good). All are visible; none is consistent, and 1 px dashed is the weakest
possible ring on a busy WebGL backdrop.

---

## 3. Per-screen audit

Format per screen: **Keep** (works, do not touch), **Fix** (what fails and why), **390** (narrow).

### 3.1 Boot / callsign

`before/01-boot--1440.png`, `before/01-boot--1280.png`, `before/01-boot--390.png`

- **Keep**: BIOS log typing with dotted leaders and coloured results; gradient wordmark with RGB
  glitch slices; veil lifting to reveal the skyline; one blinking prompt. Asymmetric composition
  (log top-left, wordmark centre) already avoids the centred-everything tell.
- **Fix**: the subtitle `.boot__sub` crosses the Core beam: 1.2:1 where it overlaps
  ("EN GINEER"). `.boot__meta` (CLIENT 1.0 · WEBGL2 · HDR PIPELINE / 127.0.0.1:8501 · LINK
  ENCRYPTED) is 2.54:1. The meta strip is diegetic BIOS text, so it stays (the version-footer
  ban targets marketing pages), it just needs `--meta`. The subtitle's 0.5 em tracking and the
  prompt's 0.42 em are the "kicker" exception; keep one of them at kicker width, bring the other
  to `--tracking-label`.
- **390**: log lines are `white-space: nowrap` in a `min(540px, 100vw - 48px)` box: overflow.
  Subtitle wraps into four fragments around the magenta dot. Meta wraps to two lines each.

### 3.2 Story cutscenes (prologue, act openings) and level transmissions

`before/02-prologue-title--1440.png` (the world between title card and first line; at 4 fps the
title card itself was only caught on the level transmission), `before/03-prologue-narration--1440.png`,
`before/08-act-intro-title--1440.png`, `before/09-act-intro-narration--1440.png`,
`before/33-cutscene-boss5-title--1440.png`, `before/34-cutscene-boss5-sub--1440.png`,
`before/03-prologue-narration--390.png`

- **Keep**: everything structural. Title card (kicker with rules, 84 px name with breathing
  tracking, mono meta), typed subtitles centred in the lower bar at 21 px display with a hard
  text shadow (readable on any frame), REC + timecode, skip hint. This is the most "premium"
  screen in the game.
- **Fix**: bar HUD text is under AA: `.cs-hud__src` 3.64:1, `.cs-skip` about 4.1:1,
  `.cs-hud__tc` 4.87 (ok). The REC dot blinks with `steps(2)` forever: that one is semantic
  (recording), keep. The magenta caret glows (fine, it is the live element).
- **390**: bars are 340 px each; cap them.

### 3.3 Hub: sector map, operative, deploy, gallery, topbar

`before/04-hub-fresh--1440.png`, `before/04-hub-fresh--1280.png`, `before/05-hub-focus--1440.png`,
`before/24-hub-l01-cleared--1440.png`, `before/25-hub-map-tip--1440.png`, `before/28-hub-mid--1440.png`,
`before/35-hub-complete--1440.png`, `before/24-hub-l01-cleared--390.png`

- **Keep**: the map (see keep list), the operative card's ident block (callsign in display 25 px,
  rank right-aligned, segmented XP meter, 25-cell breach strip in sector colours), DEPLOY as the
  only filled surface, ENTER kbd hints, the topbar with sector chip in the centre.
- **Fix, hierarchy**: the gallery panel frame (`.hub-gallery` sets `--accent: magenta` for the
  whole panel, so frame, chamfer glow, brackets and head gradient are magenta) is as loud as the
  map. Narrative magenta should mark the *title and cards*, not the chrome.
- **Fix, CTA wrap**: DEPLOY's title wraps to two lines for longer names ("L02 · SIGNAL NOISE",
  `before/24-hub-l01-cleared--1440.png`) because the ENTER kbd takes a column next to it. This is
  the hub's primary CTA; the taste pre-flight treats a wrapped CTA as broken.
- **Fix, contrast**: map sector labels, node titles, BOSS tags, legend, `/ 100`, `250 XP TO NEXT
  RANK`, `NS-????`, the gallery note: all 2.0 to 2.65:1 (table in §2.3). Node titles are 8.5 px.
- **Fix, glow and idle loops**: see §2.4/§2.5. Cleared nodes glow; the current node has pulse +
  bob + strip blink; the DEPLOY chevron nudges forever.
- **Fix, semantics**: map tooltip status `LOCKED` and story-archive `LOCKED` use `chip--bad`
  (blood).
- **Fix, tooltip**: `.map-tip` is 252 px; the head row (`L02 S0 · THE DEAD ZONE` + status chip)
  truncates the sector name (`before/25-hub-map-tip--1440.png`).
- **Generic patterns**: the "NO VISUAL" silhouette is a generic avatar egg, but it is diegetic
  (no identity yet) and is replaced by the L01 render when the feed is online, so it stays; it
  should not take 200 px of a 296 px column, though. "IN-ENGINE" is printed on every fragment card
  (`before/35-hub-complete--1440.png`): a repeated label carries no information once every
  card has it.
- **390**: unusable (map clipped, topbar overlap). See P1 hub narrow layout.

### 3.4 Story archive and fragment viewer

`before/26-story-archive--1440.png`, `before/26b-story-archive-focus--1440.png`, `before/26-story-archive--390.png`,
`before/27-fragment-viewer--1440.png` (in-engine replay opening)

- **Keep**: list of chapter rows as chamfered cards with an inset left rule in the chapter's
  colour, SEEN/LOCKED chips, arrow-key navigation, Esc to close; the narrow layout already works.
- **Fix**: LOCKED chips in blood (above); locked rows use `--dim` text (2.45:1; these are
  inactive so WCAG exempts them, but "ENCRYPTED / REACH ACT II TO UNLOCK" is information, use
  `--muted` at least). `story.css` is being edited by another engineer: coordinate.

### 3.5 Mission

`before/11-mission-brief--1440.png`, `before/12-mission-why--1440.png`, `before/13-mission-manual--1440.png`,
`before/14-restore-confirm--1440.png`, `before/15-hack-progress--1440.png`, `before/16-hack-failed--1440.png`,
`before/17-mission-output--1440.png`, `before/18-mission-focus--1440.png`, `before/18b-mission-focus-hack--1440.png`,
`before/11-mission-brief--1280.png`, `before/14-restore-confirm--1280.png`, `before/29-mission-l08--1440.png`,
`before/30-mission-boss5--1440.png`, `before/31-hack-progress-boss5--1440.png`, `before/11-mission-brief--390.png`

**Topbar.** Keep: back, LEVEL 01 // COLD BOOT with sector chip and concept, breach timer in mono
with a 2 px par meter that turns amber at 75% and blood over par, attempt counter. Fix: `/ 15:00
PAR` is `--dim` (2.51:1).

**Briefing tabs (TRANSMISSION / WHY IT MATTERS / FIELD MANUAL).** Keep: underline indicator that
scales in, short labels below 1180 px, `role=tab`. Fix: tabs are 10 px with a 34 px hit height:
make the hit area the full 42 px head. Field Manual code samples overflow the 345 px column and
get cut mid-comment (`before/13-mission-manual--1440.png`), which is acceptable inside a scroll
box, but the cut sits under the panel bracket with no fade: add an edge fade on `.rich pre.code`.

**Objectives.** Keep: index, inline `code` chips, diamond mark that fills acid. Fix: the list
duplicates the layer list; at 1280x720 it is cut at item 07 (`before/11-mission-brief--1280.png`).
`.objective__index` is `--dim`.

**Editor.** Keep: gutter with active line number, heat/error lines, inline error widget, bracket
match, current line, file path + SYNCED chip. Fix (P0): **comment colour 4.30:1** while the
objectives are written as comments; line numbers 1.80:1; editor width (64 columns at 1440, 56 at
1280, starters up to 81). `editor.css` documents `--ce-font-size`, `--ce-lh`, `--ce-pad-*` as
tunables and re-measures the glyph probe, so width can be won safely.

**Combat log / output.** Keep: tag column, attempt head with timestamp, decoded error card with
the offending line and the raw Python message. Fix: default `.log-line__tag` and
`.log-head .mono` are `--dim`; the error card duplicates the editor's inline widget (that is
intentional: one is at the line, one is in the log; keep both).

**Target (enemy, firewall, layers, intel).** Keep: ASCII enemy with breathing aura, scan, glitch
ghosts; skewed HP shards; layer rows with QUEUED / SCANNING / BREACHED / BLOCKED; amber INTEL
card unfolding with grid-rows; HACK button with fill, sub-label and keys; RETRY / ROOT ACCESS
states. Fix: `QUEUED` and indices are `--dim` 9 to 10 px; `.enemy__readout` 8.5 px at 2.54:1;
150 px of dead space between the layer list and HACK at 1440 (fine, it is where INTEL expands).

**Restore confirm.** `before/14-restore-confirm--1440.png`. Keep as is: danger-toned bar over
the editor, Cancel focused, Esc closes, RESTORE button turns red while open. It uses the alert
grammar (top-right + bottom-left cut), which becomes the documented rule.

**Failed hack.** `before/16a-dialogue-fail--1440.png`, `before/16-hack-failed--1440.png`. Keep:
INTEL on the first blocked layer, RETRY / PATCH · REINJECT. Fix: while the fail dialogue is up the
HACK button still reads BREACHING 07/07 (`before/16a-dialogue-fail--1440.png`): the button
should settle to RETRY before the dialogue opens (`mission.js` order of beats; behaviour, P2).

**Focus.** `before/18-mission-focus--1440.png`, `before/18b-mission-focus-hack--1440.png`:
visible, but a 1 px dashed square around chamfered shapes.

**390.** Not playable (editor 0 px). P0.

### 3.6 Dialogue overlay (INCOMING TRANSMISSION)

`before/10-dialogue-intro--1440.png`, `before/10b-dialogue-focus--1440.png`, `before/16a-dialogue-fail--1440.png`,
`before/19-dialogue-victory--390.png`

- **Keep**: native modal `<dialog>`, speaker colour per cast member, mono body (machine voice),
  counter, SKIP STORY + NEXT/CONTINUE, focus restore, `{callsign}` substitution.
- **Fix**: shape language (plain rectangle, 100% border, 44 px glow; no chamfer, no brackets);
  it sits dead centre and covers exactly the code the line talks about; the label "INCOMING
  TRANSMISSION" is a 11 px label above a 26 px name above 16 px text: three sizes, fine, but
  the speaker name is in display 700 at 26 px while panel titles elsewhere are 12 px, so the
  overlay feels like another product. Focus ring is amber.
- **390**: works (`before/19-dialogue-victory--390.png`).

### 3.7 Victory

`before/20-victory-mid-reveal--1280.png`, `before/21-victory-l01--1280.png`, `before/21b-victory-focus--1280.png`,
`before/21b-victory-focus--1440.png` (speed bonus MISSED row), `before/32-victory-boss5--1440.png`,
`before/21-victory-l01-full--390.png`, `before/22-cutscene-title--1440.png`, `before/23-cutscene-subtitle--1440.png`

- **Keep**: the beats, the reward panel with dotted leaders and right-aligned mono values, TOTAL
  as the focal number, the RANK UP band, the two actions (PLAY TRANSMISSION primary in narrative
  magenta, RETURN TO HUB ghost), "any key skips". Centred composition is right here: it is a
  ceremony, the "manifesto" exception in design-taste §4.3.
- **Fix**: `ANY KEY — SKIP` 2.62:1; `.reward--missed` 2.33:1 (the MISSED speed-bonus row is
  barely visible in `before/21b-victory-focus--1440.png`); the DELETED stamp is red text with
  a line-through, rotated, on a green field (4.97:1, and the strike halves legibility at 13 px):
  strike the enemy name only (already the case) and lighten the stamp ink. Static glows on every
  reward value and on the callsign; the focal TOTAL loses its edge. Focus ring is the dashed
  square (`before/21b-victory-focus--1280.png`). Particles overlap the RANK UP label for a
  moment (`before/21-victory-l01--1280.png`): acceptable juice.
- **390**: title clipped both sides.

### 3.8 Settings (SYSTEM CONFIG)

`before/06-settings--1440.png`, `before/06-settings--390.png`

- **Keep**: grouped settings, segmented quality control with the sliding plate, chamfered
  switch, tick-marked range, controls reference with kbd, Esc closes, DONE primary.
- **Fix**: hints and footer stats are `--dim`. The range focus ring is the dashed rectangle
  around the whole slider (`before/06-settings--1440.png`).
- **390**: label/slider overlap; stats wrap to four lines.

### 3.9 Command Center

`before/07-command-center--1440.png`, `before/07-command-center--390.png`

- **Keep**: everything structural; it is responsive. Not core loop: P2 only.
- **Fix**: ten `--dim` text rules (`.ops-empty`, `.ops-field__hint`, `.ops-input::placeholder`,
  `.ops-event__date`, ...); the cyan `--text-glow` bug on `.ops-big` in the magenta panel.

---

## 4. Refined design system (tokens)

Everything below **extends `client/css/tokens.css`**; no parallel system, no renamed existing
tokens (every current name keeps working). Values that depend on the local accent are expressed
as **alpha tokens** combined at the use site (see the latent bug in §2.3).

### 4.1 The token block

```css
/* tokens.css additions: keep every existing token; values below are measured (§2.3) */
:root {
  /* rgb triplets, declared once (delete the local copies in mission.css, victory.css, cutscene.css) */
  --cyan-rgb: 0, 240, 255;
  --magenta-rgb: 255, 43, 214;
  --acid-rgb: 57, 255, 20;
  --amber-rgb: 255, 176, 0;
  --blood-rgb: 255, 51, 85;
  --steel-rgb: 136, 146, 166;
  --violet: #8c4dff;
  --violet-rgb: 140, 77, 255;

  /* ink: text roles, contrast on the glass composite #0a0c14 */
  /* --text   #d7dde8  14.3:1  primary text, values            (existing) */
  --text-2: #a3acbe;   /*  8.6:1  secondary values, active labels in dense rows */
  /* --steel  #8892a6   6.2:1  body copy, labels, ghost buttons (existing) */
  --meta: #7c879b;     /*  5.4:1  hints, indices, units, timestamps, "/ 100", par: replaces --dim as text */
  --muted: #5f6a7d;    /*  3.6:1  locked / disabled text only (inactive UI) and numerals >= 18 px */
  /* --dim    #4a5160   2.4:1  strokes, sockets, empty cells, carets. Never text. (existing) */

  /* surfaces (elevation e0..e3) */
  --surface-inset: rgba(3, 5, 10, 0.72);    /* e0 wells: editor, code blocks, portrait, fragment media */
  /* --panel  rgba(10,14,22,.62) + blur 14   e1 glass panels (existing) */
  --surface-pop: rgba(6, 9, 15, 0.92);      /* e2 popovers: map tip, toast, conflict / restore bars */
  --surface-modal: rgba(9, 13, 21, 0.96);   /* e3 modal frames over motion: dialogue, archive, lightbox */
  --scrim: rgba(3, 4, 8, 0.74);             /* behind e3 */

  /* strokes: alpha steps for rgba(var(--accent-rgb), var(--a-*)) */
  --a-wash: 0.055;   /* panel top wash */
  --a-faint: 0.13;   /* dividers inside a panel */
  --a-line: 0.35;    /* panel hairline (= --hairline) */
  --a-ui: 0.55;      /* resting ring of an interactive control: 4.7:1 on cyan */
  --a-hot: 0.95;     /* hover / active / chamfer diagonals */

  /* corner cuts: one structural grammar (top-left + bottom-right), one alert grammar (top-right + bottom-left) */
  --cut-xs: 5px;     /* chips, kbd-sized controls, switch, stamps */
  --cut-sm: 8px;     /* buttons, rows, cards (= --chamfer-sm) */
  --cut-md: 10px;    /* popovers, toasts, fragment cards, large buttons */
  --cut-lg: 14px;    /* panels and modal frames (= --chamfer) */

  /* type scale (Chakra Petch unless noted). Floor: 10 px. */
  --fs-micro: 10px;  /* uppercase telemetry labels, tags, legend, node titles */
  --fs-label: 11px;  /* .label, chips, panel sub-labels, table heads */
  --fs-meta: 12px;   /* panel titles, log text (mono), meta lines */
  --fs-ui: 13px;     /* list rows, objectives, layer rows, controls */
  --fs-body: 14px;   /* body copy (.rich), settings labels, editor (mono) */
  --fs-lead: 16px;   /* dialogue text (mono), mission title */
  --fs-h3: 20px;     /* deploy title, HACK label, reward values */
  --fs-h2: 24px;     /* callsign, dialogue speaker, rank-up name */
  --fs-h1: 32px;     /* TOTAL XP */
  /* display stays fluid per component: .ns-logo, .victory__title, .cs-title__name */
  --lh-tight: 1.05;
  --lh-snug: 1.25;
  --lh-body: 1.6;
  --tracking-display-xl: 0.06em; /* >= 40 px uppercase */
  /* --tracking-display 0.12em     13 to 26 px uppercase headings (existing) */
  --tracking-label: 0.16em;      /* was 0.18em; 10 to 12 px labels */
  --tracking-kicker: 0.32em;     /* one kicker per screen: boot prompt, deploy kicker, cutscene kicker */
  --tracking-mono: 0.04em;       /* mono numerals and kbd */

  /* space: 4 px grid */
  --sp-1: 4px;
  --sp-2: 8px;
  --sp-3: 12px;
  --sp-4: 16px;
  --sp-5: 20px;
  --sp-6: 24px;
  --sp-8: 32px;
  --sp-12: 48px;
  /* --gutter clamp(12px, 1.6vw, 24px) stays the between-panel gap (existing) */

  /* motion */
  --t-instant: 60ms;   /* press feedback */
  /* --t-fast 140ms hover colour, --t-med 220ms state change, --t-slow 420ms overlay enter (existing) */
  --t-scene: 640ms;    /* staged entrances (.rise, band-in) */
  --t-cine: 900ms;     /* letterbox, title card */
  --stagger: 75ms;     /* per-item delay in staged entrances */
  --loop-pulse: 1.9s;  /* the one "you are here" pulse */
  --loop-breathe: 3.6s;/* live subject idle (enemy aura) */

  /* focus: one ring for everything (§4.7) */
  --focus-w: 2px;
  --focus-offset: 3px;

  /* layers */
  --z-overlay: 40;   /* in-screen overlays: lightbox, story archive, map tip */
  --z-crt: 50;
  --z-toast: 60;
  --z-banner: 65;
  --z-settings: 70;
  --z-preboot: 90;
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --t-instant: 0ms;
    --t-scene: 0ms;
    --t-cine: 0ms;
  }
}
```

Fix the existing glow tokens in the same file: they cannot follow the local accent from
`:root`. Either delete them (only `.glow` and three `productivity.css` rules use `--text-glow`)
or redefine them as cyan-only on purpose and give the three productivity rules a local
`text-shadow: 0 0 8px rgba(var(--accent-rgb), .65), 0 0 22px rgba(var(--accent-rgb), .25)`.

### 4.2 Colour roles and where each may appear

| Role | Token | Used for | Never for |
|---|---|---|---|
| System / primary | `--cyan` | panels' default accent, primary buttons, caret, focus default, links | success, locked |
| Narrative | `--magenta`, `--violet` | story, cutscene, rank-up, fragment cards, PLAY TRANSMISSION | panel chrome at rest (gallery frame) |
| Success | `--acid` | breached, cleared, victory screen, SYNCED | decoration |
| Warning / intel | `--amber` | INTEL, timer at 75%, encrypted nodes, conflict bar, speed bonus | focus rings |
| Enemy / failure | `--blood` | target panel, BLOCKED, crash, restore danger, over-par timer | locked, disabled |
| Neutral | `--text`, `--text-2`, `--steel`, `--meta`, `--muted`, `--dim` | per the ink table | `--dim` as text |
| Sector | `--c` / `--c-rgb` (set inline from the campaign) | map bands, nodes, breach strip, mission sector chip | anything outside its sector |

### 4.3 Typography rules

- Sizes only from the scale; 10 px floor. Tracking only from the four tokens plus the kicker.
- Mono = machine voice: code, logs, numbers, timecodes, kbd, CIPHER's dialogue lines.
  Display = interface and narrator: labels, titles, buttons, cutscene subtitles, rich text.
- Uppercase + tracking for labels and titles; sentence case for anything a player reads as
  prose (brief, hints, intel, dialogue, subtitles). This is the current practice; make it the rule.
- Numbers: `.mono` (tabular). Big numerals (TOTAL XP, timer, callsign) may glow only when live.
- `text-wrap: balance` on multi-line headings (deploy title, cutscene title at 390, victory
  title at 390); `text-wrap: pretty` on `.rich p`, `.dialogue__text`, `.cs-line`.

### 4.4 Spacing rules

4 px grid (`--sp-*`). Panel head height 42 px; panel body padding `--sp-4`; row padding
`--sp-2` vertical; stacked cards in one column use `--gutter` like the grid (one rhythm for the
whole screen). Map odd values to the scale when a rule is touched: 13 to 12, 7 to 8, 9 to 8,
11 to 12, 14 to 16, 18 to 20, 22 to 24.

### 4.5 Surfaces, elevation, strokes, corner cuts

- e0 inset wells, e1 glass panels, e2 popovers, e3 modal frames (tokens above). Only e1 and the
  topbar blur the world (`backdrop-filter` on fixed/large surfaces only; high-end-visual §6).
- Stroke alpha steps: faint dividers `.13`, hairline `.35`, interactive resting ring `.55`, hot `.95`.
- **Corner-cut rule** (shape-consistency lock, documented):
  - Structural cut, top-left + bottom-right: panels, buttons, chips, cards, rows, modal frames
    (including the dialogue after P1-D1), switches, segmented control.
  - Alert cut, top-right + bottom-left: transient alerts that interrupt (toast, conflict bar,
    restore bar, link banner, cutscene render status). The toast's single cut becomes the pair.
  - Round: only live-signal dots (REC, LIVE, link pulse, feed live chip) and spinners.
    `.frag__play` becomes a cut square.
  - Radius 2 px only on inline `code` chips and `.kbd` (keycaps), nowhere else.
  - Sizes from `--cut-*`: 5 (chip, switch, stamp, restore button), 8 (buttons, rows, cards,
    icon buttons: was 7), 10 (toast, map tip, fragment card, portrait, large button: was 12 on
    `.btn--lg`, 9 on `.map-unlock`), 14 (panels, modal frames).

### 4.6 Glow budget

At rest, at most **three** glowing things per screen, each with a reason:

| Screen | 1. Focal action | 2. Live subject | 3. Live status |
|---|---|---|---|
| Boot | prompt | wordmark | none |
| Hub | DEPLOY (`--btn-glow` on hover only; its fill already wins) | current node (pulse) | feed LIVE chip when online |
| Mission | HACK | enemy art + aura | timer when warn/over; caret |
| Victory | primary action | title (decays after the chroma beat) | TOTAL value |
| Cutscene | none | title card | REC dot, caret |

Everything else is flat colour. Hover and focus may glow (feedback). Cleared map nodes: fill,
no halo. Panel title diamonds: no `box-shadow`.

### 4.7 Motion

Event durations from tokens (`--t-instant/fast/med/slow/scene/cine`), easing `--ease-out` for
UI, `--ease-back` for physical overshoot (stamps, switch knob, segmented plate), `linear` only
for continuous flows (packets, rain, toast countdown, spinners). Idle loops: one "you are here"
pulse per screen (`--loop-pulse`), one live-subject breath (`--loop-breathe`), rare glitches
(logo, encrypted lock) at 6 s or longer. Every loop is already killed by `body.reduce-motion`;
keep that.

### 4.8 Focus ring

```css
:focus-visible {
  outline: var(--focus-w) solid rgb(var(--accent-rgb));
  outline-offset: var(--focus-offset);
}
```

One ring, solid 2 px in the local accent (cyan by default, speaker colour in the dialogue,
sector colour on map nodes, blood inside the restore bar), offset 3 px so it clears chamfers
and fills. Components that clip (`clip-path`) and therefore cannot show an outline keep their
inner-ring technique (`.frag`, `.story-chapter`, `.ce`) but use the same 2 px width and the hot
alpha. Measured: cyan ring 11.2:1 against the glass, blood 5.4:1, amber 10.7:1 (all over the
3:1 non-text minimum).

---

## 5. Prioritised change list, per file

Priorities: **P0** breaks play, readability (AA) or the primary CTA; **P1** makes the core loop
read as one system; **P2** polish and secondary screens. IDs are referenced in commits.
Ownership: `hub.js`, `victory.js`, `cutscene.js`, `boot.js`, `index.html`, `story.js`,
`story.css` and `engine/` are being edited by another engineer right now. Every change below is
CSS-only unless marked **[JS]**; the few JS items name the file and must be coordinated.

### 5.1 `client/css/tokens.css`

| ID | P | Change | Result |
|---|---|---|---|
| T1 | P0 | Add the token block from §4.1 (rgb triplets, `--text-2`, `--meta`, `--muted`, surfaces, `--a-*`, `--cut-*`, `--fs-*`, `--lh-*`, tracking tokens, `--sp-*`, motion additions, focus, z-index) and the reduced-motion additions. | No visual change by itself; every later item consumes it. |
| T2 | P0 | Set `--chamfer: var(--cut-lg)` and `--chamfer-sm: var(--cut-sm)` (values unchanged: 14 / 8). Change `--tracking-label` 0.18em to 0.16em. | Labels tighten slightly (13 rules use the token). |
| T3 | P1 | Fix or delete `--glow-sm`, `--glow-md`, `--text-glow` (§4.1 last paragraph). | Productivity numerals glow in their own panel colour. |

### 5.2 `client/css/app.css`

| ID | P | Selector(s) | Property change | Expected result |
|---|---|---|---|---|
| A1 | P0 | `.dim`, `.boot__meta`, `.operative__id`, `.operative__xp-next`, `.operative__xp-note`, `.map-legend__item`, `.map-tip__hint`, `.hub-gallery__note`, `.hub-gallery__empty-note`, `.setting__hint`, `.switch__state`, `.settings__stats` | `color: var(--dim)` to `color: var(--meta)`. Keep `.boot__caret` on `--dim` (decoration). | All meta text 5.4:1 (was 2.25 to 2.54). Hierarchy is kept because `--meta` is still the darkest text step. |
| A2 | P0 | `.map__sector-index` (`rgba(74,81,96,.9)`), `.map__sector-name` (`rgba(136,146,166,.55)`), `.map__sector-zone`, `.map__sector-progress` (`rgba(74,81,96,.95)`), `.map-node__glyph` (`rgba(136,146,166,.6)`), `.map-node__title` (`.42`), `.map-node__tag` (`.5`) | Locked/default state: index, zone, progress, glyph, title, tag to `var(--muted)`; `.map__sector-name` to `var(--meta)`. Live overrides (`.map__band.is-live …`, `.map-node.is-cleared …`, `.is-current`) unchanged. | Locked sectors read as a dim preview at 3.6:1 instead of a smear at 2.0:1; the live band still dominates. |
| A3 | P0 | `.map-node__title`, `.map-node__tag`, `.map-legend__item`, `.map__sector-zone`, `.map-tip__sector`, `.map-unlock__label`, `.frag__kind`, `.operative__portrait-tag`, `.operative__xp-note` | Font size to `var(--fs-micro)` (10 px). `.map-node__title` keeps `-webkit-line-clamp: 2` and `width: calc(var(--dx) - 12px)`; check the compact rule (`.map.is-compact`) still hides locked titles. | No text under 10 px in the hub. |
| A4 | P0 | `:focus-visible` (line 116) | Replace `outline: 1px dashed rgba(var(--accent-rgb), .9); outline-offset: 3px` with the §4.8 rule. `.btn:focus-visible, .icon-btn:focus-visible` keep `--btn-line: rgba(var(--accent-rgb), 1)` and set `outline-offset: var(--focus-offset)`. `.map-node:focus-visible .map-node__hex`: `outline: var(--focus-w) solid var(--c); outline-offset: 5px`. `.segmented__opt:focus-visible`: keep `outline-offset: -1px` but 2 px solid. `.frag:focus-visible::after`, `.story-chapter:focus-visible::after`: inner ring 2 px at hot alpha. | One solid 2 px ring in the local colour everywhere (`before/05-hub-focus--1440.png` dashed square becomes a clean ring). |
| A5 | P0 | `.deploy`, `.deploy__text`, `.deploy__kbd`, `.deploy__title` | `.deploy { position: relative; }` (it already has it via `.btn`), `.deploy__kbd { position: absolute; top: 14px; right: 18px; }`, `.deploy__title { font-size: 18px; letter-spacing: 0.05em; text-wrap: balance; }`, `.deploy__text { padding-right: 0; }` and give `.deploy__kicker` `padding-right: 64px` so it never runs under the kbd. Keep `.deploy.is-encrypted .deploy__kbd, .deploy.is-complete .deploy__kbd { display: none }`. | "L02 · SIGNAL NOISE" and "L08 · OVERCLOCK" fit on one line at 1280 and 1440; ENTER sits top-right as a key legend. |
| A6 | P0 | `@media (max-width: 767px)` hub block (new) | `.hub { grid-template-columns: minmax(0, 1fr); grid-template-rows: none; grid-auto-rows: auto; grid-template-areas: 'left' 'map' 'gallery'; overflow-y: auto; }`, `.hub__left { gap: var(--gutter); }`, `.operative__portrait { display: none; }` (the ident block carries the card on a phone), `.hub-map { min-height: 520px; }`, `.hub-map__body { overflow-x: auto; }`, `.map { min-width: 600px; }` (the map's ResizeObserver lays out from its own box, so traces stay 45-degree true), `.hub-gallery { height: 160px; }` with the existing 1279 px horizontal-strip rules, `.hub-topbar .label, .hub-topbar__rule, .hub-feed, .hub-sector { display: none; }`, `.ns-logo--sm { font-size: 15px; }`. | Hub is a vertical scroll: ident + DEPLOY, then a horizontally scrollable map, then fragments. No overlap in the topbar. Upgrade to P0 because the hub is the router into every mission. |
| A7 | P1 | `.panel__title::before` | Remove `box-shadow`. | Diamonds stay as markers, stop glowing (glow budget). |
| A8 | P1 | `.operative__callsign` (cyan state), `.operative__rank`, `.hub-sector__index`, `.map__band.is-live .map__sector-index`, `.map-node.is-cleared .map-node__hex` | Remove `text-shadow` / `drop-shadow` at rest. Keep `.operative__callsign.is-unregistered` glow (story beat), `.map-node.is-current` and `.is-encrypted` halos. | Complete map (`before/35-hub-complete--1440.png`) reads as a circuit, not a smear; the current node is the only halo on the map. |
| A9 | P1 | `.map-node.is-current .map-node__tag` and `.screen.is-active .map-node.is-current .map-node__tag` | Drop `tag-bob` from both animation lists (keep `fade-in`). | One "you are here" signal (the ring pulse). |
| A10 | P1 | `.deploy__chev` | Remove `animation: chev-nudge`; on `.deploy:hover .deploy__chev, .deploy:focus-visible .deploy__chev` apply `translate: 4px 0; transition: translate var(--t-med) var(--ease-out)`. | Motion becomes feedback, not idle noise. |
| A11 | P1 | `.breach-strip__cell.is-current` | Remove `cell-blink`; keep the inset ring. | The map node owns the pulse. |
| A12 | P1 | `.operative__scan` | `animation-duration: 9s` and `animation-iteration-count: 3` (scan on arrival, then rest). | Portrait stops competing after the first 27 s. |
| A13 | P1 | `.hub-gallery` | Keep `--accent: var(--magenta)` for the title and cards, but set `--hairline-c: rgba(136,146,166,.22)` on `.hub-gallery` (the `.panel::before` hook already exists) and override `.hub-gallery::after { opacity: .45; }` (brackets) and `.hub-gallery .panel__head { background: linear-gradient(90deg, rgba(var(--magenta-rgb), .06), transparent 65%); }`. | Gallery frame recedes to neutral; magenta stays on title, count chip and cards. Map + DEPLOY become the focal pair. |
| A14 | P1 | `.map-tip` | `width: 280px`; `.map-tip__head { flex-wrap: wrap; row-gap: 4px; }`. | Sector name no longer truncated next to the status chip. |
| A15 | P1 | `.map-tip__status.chip--bad` (new rule, CSS only) | `--accent: var(--meta); --accent-rgb: 124, 135, 155;` | LOCKED stops reading as an error in the tooltip without touching `hub.js` (`STATUS_CHIP.locked` stays `chip--bad`). |
| A16 | P1 | `.boot__center` | Add a scrim behind the wordmark block: `.boot__center::before { content: ''; position: absolute; inset: -6vh -8vw; z-index: -1; background: radial-gradient(closest-side, rgba(3,4,8,.72), rgba(3,4,8,0)); pointer-events: none; }`. `.boot__sub { color: var(--text-2); letter-spacing: var(--tracking-label); padding-left: var(--tracking-label); }` (keep the kicker width on `.boot__prompt` only). | Subtitle readable where it crosses the beam (target 4.5:1 or better on the sampled beam colour); beam still visible above and below. |
| A17 | P1 | `@media (max-width: 560px)` boot block (new) | `.boot__log { font-size: 11px; } .boot__line { white-space: normal; grid-template-columns: 16px minmax(0, 1fr) auto; } .boot__leader { display: none; }`, `.boot__sub { flex-wrap: wrap; justify-content: center; row-gap: 8px; letter-spacing: 0.24em; }`, `.boot__meta { flex-direction: column; align-items: center; gap: 4px; }`. | No overflow at 390; subtitle wraps as two clean lines. |
| A18 | P1 | `.settings__body .setting` under `@media (max-width: 560px)` (new) | `.setting { grid-template-columns: minmax(0, 1fr) auto; row-gap: 6px; } .setting__text { grid-area: 1 / 1; } .setting__value { grid-area: 1 / 2; } .setting__control { grid-area: 2 / 1 / 3 / 3; justify-content: stretch; } .setting--toggle .setting__control, .setting--choice .setting__control { grid-area: 1 / 2; }`, `.segmented { width: 100%; }`, `.settings__stats { display: none; }`. | Labels above full-width sliders at 390; no overlap. |
| A19 | P1 | `.toast` | Clip to the alert pair: `clip-path: polygon(0 0, calc(100% - var(--c)) 0, 100% var(--c), 100% 100%, var(--c) 100%, 0 calc(100% - var(--c)));` | Toasts match the conflict/restore bars (alert grammar). |
| A20 | P1 | `.btn--ghost` | `--btn-line: rgba(var(--accent-rgb), var(--a-ui))` (was .28). | Ghost buttons show a 4.7:1 boundary (SKIP STORY, RETURN TO HUB, RESET TO DEFAULTS). |
| A21 | P1 | `.btn--lg` | `--c: var(--cut-md)` (was 12). `.icon-btn` `--c: var(--cut-sm)` (was 7). `.map-unlock` `--c: var(--cut-md)` (was 9). | Corner sizes come from the 4-step scale. |
| A22 | P1 | `.rich pre.code` | Add a right-edge fade when scrollable: `mask-image: linear-gradient(90deg, #000 calc(100% - 24px), transparent);` and remove it on `:hover, :focus-within`. `.rich p { text-wrap: pretty; }` | Cut-off manual code reads as "scrolls", not as a rendering bug. |
| A23 | P2 | `.hub__left` | `gap: var(--gutter)` (was 14 px). `.operative__body` gap 12, `.operative__xp` gap 8. | One vertical rhythm in the hub. |
| A24 | P2 | `.operative__portrait` | `max-height: 160px` (was 200) at heights over 760; keep. | Ident block and DEPLOY move up; less silhouette. |
| A25 | P2 | `.frag__kind.is-engine` | Hide when every card is in-engine: `.hub-gallery__list:not(:has(.frag__kind:not(.is-engine))) .frag__kind.is-engine { display: none; }`. | No repeated IN-ENGINE label (`before/35-hub-complete--1440.png`). |
| A26 | P2 | `.frag__play` | Replace the circle with a cut square: `border-radius: 0; clip-path: polygon(6px 0,100% 0,100% calc(100% - 6px),calc(100% - 6px) 100%,0 100%,0 6px); border: 0; box-shadow: inset 0 0 0 1px rgba(var(--c-rgb, var(--cyan-rgb)), .6);` | Shape lock: round only for live dots. |
| A27 | P2 | Hard-coded rgb literals | Replace `255, 43, 214`, `0, 240, 255`, `57, 255, 20`, `255, 176, 0`, `255, 51, 85`, `136, 146, 166` literals with the T1 triplets as rules are touched. | One source of truth. |
| A28 | P2 | Durations | `:where(.screen) > *` 260 ms to `var(--t-med)`; `.screen.is-active .rise` 640 ms to `var(--t-scene)` with `calc(70ms + var(--i, 0) * var(--stagger))`; `.settings__panel` 460 ms to `var(--t-slow)`. | Motion durations come from tokens. |

### 5.3 `client/css/mission.css`

| ID | P | Selector(s) | Property change | Expected result |
|---|---|---|---|---|
| M1 | P0 | `.mission-grid` | `grid-template-columns: clamp(248px, 21vw, 340px) minmax(0, 1fr) clamp(256px, 19vw, 320px);` (was `clamp(256px, 24vw, 360px) … clamp(272px, 24.5vw, 372px)`). | Centre column 650 to 772 px at 1440: about 80 columns of 14 px mono (with M2). Target panel 274 px: layer names ellipsize earlier, which is acceptable because the left list shows them in full. |
| M2 | P0 | `.mission-editor .ce` (new) | `--ce-pad-r: 20px;` and under `@media (max-width: 1366px)` `--ce-font-size: 13px; --ce-lh: 21px;`. `editor.css` documents these tunables and `editor.js` re-measures the glyph probe on resize. | 1440: about 80 columns (starters up to 81). 1280: about 74 columns (was 56). |
| M3 | P0 | `.mission-timer__par`, `.objective__index`, `.log-line__tag`, `.log-head .mono`, `.mission-log__stdout.is-empty`, `.layer__index`, `.layer__state` | `color: var(--dim)` to `var(--meta)`. | QUEUED, indices, par and timestamps at 5.4:1. |
| M4 | P0 | `.layer__state`, `.mission-target__live`, `.mission-timer__note`, `.log-line__tag`, `.log-head`, `.mission-title__sector` | Font size to `var(--fs-micro)` (10 px). `.enemy__readout`: 10 px and `color: rgba(var(--blood-rgb), .8)` (was 8.5 px at .6). | No mission text under 10 px; readout 4.0:1+. |
| M5 | P0 | Narrow mission, `@media (max-width: 1100px) and (min-width: 768px)`: replaces the `.mission-grid` columns in the existing `@media (max-width: 1100px)` block (236 / 262 px, about 45 editor columns at 1024); keep that block's other declarations | `.mission-grid { grid-template-columns: minmax(0, 1fr) clamp(256px, 32vw, 320px); grid-template-rows: minmax(0, 34%) minmax(0, 1fr); grid-template-areas: 'brief target' 'code target'; } .mission-brief { grid-area: brief; } .mission-code { grid-area: code; } .mission-target { grid-area: target; }` and `.mission-objectives { display: none; }` (the layer list carries them). | Editor gets the full left column under the brief; DOM order (brief, code, target) equals reading order, so tab order stays meaningful. |
| M6 | P0 | Phone mission, `@media (max-width: 767px)` (new, after M5) | `.mission-grid { grid-template-columns: minmax(0, 1fr); grid-template-rows: none; grid-auto-rows: auto; overflow-y: auto; } .mission-brief { max-height: 46dvh; } .mission-code { height: 64dvh; } .mission-objectives { display: none; } .enemy { height: 132px; } .mission-log { flex-basis: 34%; }`. Topbar: `.mission-topbar { grid-template-columns: auto minmax(0, 1fr) auto; } .mission-timer { min-width: 0; } .mission-timer__par, .mission-title__sub, .mission-attempts .label { display: none; } .mission-title__main { font-size: 14px; }`. | Playable column: brief, editor (visible, 64 dvh), target with HACK. Fixes `before/11-mission-brief--390.png` (editor 0 px). |
| M7 | P1 | `.mission-tab` | `min-height: 42px` (match `.panel__head`), `font-size: var(--fs-micro)`; `.mission-tab:focus-visible { outline: var(--focus-w) solid rgb(var(--accent-rgb)); outline-offset: -4px; }`. | Larger hit area; same ring as everywhere. |
| M8 | P1 | `.mission-target__name` | Remove `text-shadow`. | Enemy art and aura own the red glow (budget). |
| M9 | P1 | `.mission-objectives` at `@media (max-height: 760px)` (new) | `max-height: 34%`; `.objective { padding-block: 3px; }`. | The seventh objective is no longer cut at 1280x720 (`before/11-mission-brief--1280.png`). |
| M10 | P1 | `.mission-conflict`, `.mission-restore-bar` | Already alert-cut; switch the literal `10px` to `var(--cut-md)`. Restore bar background `rgba(24, 6, 11, .95)` stays (6.27:1 steel). | Documented alert grammar. |
| M11 | P1 | Local triplets at the top of `.screen.screen--mission` | Delete `--blood-rgb`, `--acid-rgb`, `--amber-rgb`, `--cyan-rgb` (now global, T1). | No duplicated tokens. |
| M12 | P2 | `.mission-objectives` at >= 1100 px | Option (decide with design owner): keep the list but render it as a compact checklist (`.objective__name` 12 px, single line with ellipsis plus a `title` attribute set in `mission.js`), freeing about 120 px for the brief. Do not hide it on desktop: it is the only place long objective names are not truncated. | Less duplication without losing information. |
| M13 | P2 | **[JS]** `mission.js` | Fail beat order: set the HACK button to its RETRY state before `ctx.dialogue.play(pool…)` (around line 1215). | `before/16a-dialogue-fail--1440.png` shows RETRY, not BREACHING 07/07, under the fail line. |

### 5.4 `client/css/editor.css`

| ID | P | Change | Result |
|---|---|---|---|
| E1 | P0 | `--syn-comment: #7a879c` (was `#66758b`, 4.30:1). Keep `--syn-comment-code #86c9d6` and `--syn-header #a6bad1`. | The instructions in the starter comments pass AA (5.54:1). Comments stay visibly quieter than code (`--syn-text #c5cfde`). |
| E2 | P1 | `--ce-num: #5b667a` (was `#343c4b`, 1.80:1). Leave `--ce-num-active #e6f4ff`. `.ce-gcur` unfocused `#5d6b80` to `var(--meta)`. | Line numbers readable (3.4:1) without competing with code; the active number still pops. |
| E3 | P2 | `--syn-punct #6d7a90` is 4.64:1: leave. | (Measured, no change.) |

### 5.5 `client/css/dialogue.css` (core loop: every mission intro, fail and victory line)

`dialogue.js` is not in the other engineer's list, but this pass needs no markup change.

| ID | P | Selector | Property change | Expected result |
|---|---|---|---|---|
| D1 | P1 | `.dialogue` | Panel language (the frame pseudo-elements are `position: absolute; inset: 0`; if a line ever overflows, move `overflow: auto` to `.dialogue__text` so the frame does not scroll away): `--accent: var(--speaker, var(--cyan)); --c: var(--cut-lg); border: 0; background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 7%, transparent), transparent 120px), var(--surface-modal); clip-path: polygon(var(--c) 0, 100% 0, 100% calc(100% - var(--c)), calc(100% - var(--c)) 100%, 0 100%, 0 var(--c)); box-shadow: none;` plus a `::before` hairline frame copied from `.panel::before` using `color-mix(in srgb, var(--accent) 35%, transparent)` for the line and `var(--accent)` for the two chamfer diagonals, and a `::after` with the two corner brackets from `.panel::after`. `transition: border-color, box-shadow` becomes `transition: background-color var(--t-med) var(--ease-out)`. | The transmission looks like a HUD panel from the same ship, tinted per speaker (`before/10-dialogue-intro--1440.png` loses the plain rectangle and the 44 px glow). |
| D2 | P1 | `.dialogue` placement | `margin: auto auto max(24px, 9vh);` (native `<dialog>` stays modal in the top layer). `.dialogue::backdrop { background: linear-gradient(to top, rgba(3,7,16,.86) 0, rgba(3,7,16,.55) 55%, rgba(3,7,16,.4)); }` | The line sits in the lower third like comms subtitles; the editor/target the line talks about stays visible above it. |
| D3 | P0 | `.dialogue button:focus-visible` | Replace `2px solid #ffb000; outline-offset: 4px` with `outline: var(--focus-w) solid var(--accent); outline-offset: var(--focus-offset);`. | Amber is reserved for warnings; focus follows the speaker colour (cyan for CIPHER: 13.9:1). |
| D4 | P1 | `.dialogue__label`, `.dialogue__count` | `color: var(--steel)` (same 6.2:1 as today's literal `#8299a9`, now a token), `.dialogue__label { font: 600 var(--fs-label)/1 var(--font-display); letter-spacing: var(--tracking-label); }`. `.dialogue__speaker { font-size: var(--fs-h2); letter-spacing: var(--tracking-display); }` (26 to 24 px). `.dialogue__text { text-wrap: pretty; }` | Same label voice as panel heads; one scale. |
| D5 | P2 | `.dialogue` font stack | Use tokens: `font: 400 var(--fs-lead)/1.65 var(--font-mono);` and `.dialogue__speaker { font-family: var(--font-display); }`. | No hard-coded families. |

### 5.6 `client/css/victory.css`

| ID | P | Selector | Property change | Expected result |
|---|---|---|---|---|
| V1 | P0 | `.victory__title` at `@media (max-width: 640px)` (new) | `white-space: normal; text-wrap: balance; font-size: clamp(30px, 11vw, 44px); letter-spacing: var(--tracking-display-xl);` | `ACCESS GRANTED` fits at 390 on two balanced lines (`before/21-victory-l01-full--390.png`). |
| V2 | P0 | `.reward--missed`, `.reward--missed .reward__detail`, `.reward--missed .reward__value` | `var(--dim)` to `var(--meta)`. | Missed bonus readable (5.1:1). |
| V3 | P0 | `.victory__skip` | `color: var(--meta)`; replace its `v-breathe` (opacity .85 to .35, which drops the hint to about 1.6:1 at the low point) with a dedicated `@keyframes v-hint { from { opacity: 1 } to { opacity: .7 } }` at the same timing; keep `v-breathe` for `.victory__cast`. **[JS, coordinate: `victory.js` line 297]** text `ANY KEY — SKIP` to `ANY KEY // SKIP` (em-dash out, house separator in). | Skip hint 4.5:1+. |
| V4 | P1 | `.reward__value` (non-total), `.victory__callsign` | Remove `text-shadow` at rest; keep it on `.reward--total .reward__value` and during `.is-hot`. | TOTAL XP is the one glowing number. |
| V5 | P1 | `.screen--victory .stamp` (DELETED) | `color: #ff6b81` for the stamp text (6.5:1 on its plate), keep the 2 px border and the strike on `.victory__enemy` only (already). | DELETED reads at 13 px over green. |
| V6 | P1 | `.victory__actions .btn` | `min-width: 240px` stays; add `@media (max-width: 560px) { .victory__actions { flex-direction: column; width: 100%; } .victory__actions .btn { width: 100%; } }`. | Stacked full-width actions on phones. |
| V7 | P1 | Local triplets at the top of `.screen.screen--victory` | Delete (global since T1). | No duplicated tokens. |
| V8 | P2 | `.victory__stats` at 390 | `gap: 6px 18px;` and `.victory__stat .label { font-size: var(--fs-micro); }`. | Stats wrap to two tidy rows. |

### 5.7 `client/css/cutscene.css`

`cutscene.js` belongs to the other engineer; these are CSS-only.

| ID | P | Selector | Property change | Expected result |
|---|---|---|---|---|
| C1 | P0 | `.cs-hud__src` | `color: var(--meta)` (was steel @ 70%, 3.64:1). `.cs-skip.is-in { opacity: 1; }` and `.cs-skip { color: var(--meta); }` | Bar HUD text 5.8:1. |
| C2 | P1 | `.screen.screen--cutscene` | `--bar: min(max(0px, calc((100vh - 100vw / 2.39) / 2)), 16vh);` | 390x844: 135 px bars, a 574 px picture (was 163 px). 1280x720 unchanged (92 px); 1440x900 144 px (was 149, imperceptible). |
| C3 | P2 | Local `--magenta-rgb`, `--violet-rgb` | Delete (global since T1). | No duplicated tokens. |
| C4 | P2 | `.cs-status` | `--c: var(--cut-sm)` with the alert polygon written in `var(--c)` (today literal 8 px). | Documented alert grammar. |

### 5.8 `client/css/story.css` (owned by the other engineer: hand these over, do not edit in parallel)

| ID | P | Selector | Property change | Expected result |
|---|---|---|---|---|
| S1 | P1 | `.story-chapter__state.chip--bad` (new) | `--accent: var(--meta); --accent-rgb: 124, 135, 155;` | LOCKED chips neutral (`before/26-story-archive--390.png`). |
| S2 | P1 | `.story-chapter.is-locked`, `.story-chapter.is-locked .story-chapter__index, .story-chapter.is-locked .story-chapter__play` | `var(--dim)` to `var(--muted)`. | ENCRYPTED rows at 3.6:1 (inactive UI) instead of 2.45:1. |
| S3 | P2 | `.story-chapter__index` | Remove `text-shadow`. | Glow budget. |

### 5.9 `client/css/productivity.css` (secondary screen)

| ID | P | Change | Result |
|---|---|---|---|
| PR1 | P2 | The ten `color: var(--dim)` text rules (`.ops-xp__op`, `.ops-empty`, `.ops-course.is-idle .ops-course__min`, `.ops-chart__axis`, `.ops-field__hint`, `.ops-input::placeholder`, `.ops-milestone__mark`, `.ops-milestone__desc`, `.ops-habit__mark`, `.ops-event__date`) to `var(--meta)`; keep `.ops-milestone__mark`/`.ops-habit__mark` on `--dim` if they are glyph decorations. | AA on the Command Center. |
| PR2 | P2 | `.ops-topbar__name`, `.ops-ring__value`, `.ops-big`: local `text-shadow` in the panel accent (T3). | Correct glow colour per panel. |

### 5.10 Copy (chrome strings only; level content is out of scope)

P2. The taste skill bans em-dashes in UI chrome; the house separator is `//` (LEVEL 01 // COLD BOOT)
or `·`. Candidates (all **[JS]**, coordinate where the file is owned by the other engineer):
`victory.js` `ANY KEY — SKIP` (V3) and the `"<ENEMY> — DELETED"` stamp separator (`.victory__dash`);
`hub.js` gallery notes `Feed offline — add a Higgsfield key…` (two strings). Keep strings the
tests read (§6) byte-identical.

### 5.11 Execution order

1. T1, T2 (tokens), then A1 to A4, M3, M4, E1, D3, V2, C1 (contrast + focus, CSS only). Run the
   browser tests.
2. M1, M2, M5, M6 (mission layout), A5, A6 (hub CTA + narrow), V1 (victory narrow).
3. P1 items by screen: dialogue (D1, D2, D4), hub glow/motion (A7 to A15), boot (A16, A17),
   settings (A18), alerts (A19 to A21), victory (V4 to V7), cutscene (C2).
4. P2 sweep, then hand S1 to S3 and the JS copy items to the owner of those files.

---

## 6. Test contract: selectors, text and keys that must not change

Grepped from `tests/test_client_fixes.py`, `tests/test_client_story.py`,
`tests/test_client_productivity.py` at `HEAD`. CSS changes above keep all of these; any markup
change must too.

**Screen and state classes**: `.screen--boot`, `.screen--hub.is-active`, `.screen--hub.is-active .deploy`,
`.screen--hub.is-active .hub-ops`, `.screen--mission.is-active .mission-editor textarea`,
`.screen--victory.is-active`, `.screen--victory.is-revealed`, `.screen--cutscene`,
`.screen--cutscene.is-active`, `.screen--cutscene.is-active:not(.screen--story)`,
`.screen--cutscene.screen--story.is-active`, `.screen--story` (and its `aria-label`, which must
contain the scene title, e.g. `THE NULL EVENT`, `DAWN OVER THE DEAD ZONE`),
`.screen--story .cs-hud__rec` (text contains `PROLOGUE`, `ACT I`…), `.screen--productivity`
(+ `.is-active`, `.is-loading` toggling), `body.reduce-motion`.

**Mission**: `.mission-editor textarea`, `.mission-sync` (text `SYNCED`, compared after
`toUpperCase()`), `.mission-restore` (+ `aria-expanded` `true`/`false`, focus returns to it),
`.mission-restore-bar`, `.mission-restore-bar:not([hidden])`, `.mission-restore-bar__go`,
`.mission-restore-bar__cancel` (focused first; **Shift+Tab from Cancel must reach Go**: keep the
DOM order Go, Cancel in `.mission-restore-bar__actions`), `.mission-log` (text contains
`Starter code restored`), `.hack-btn`, `#toasts` (text contains `RESTORED`, `RESTORE FAILED`,
`disk is read-only`).

**Dialogue**: `dialog.dialogue[open]` and a button with text `SKIP STORY`.

**Victory**: `.victory__rank` (text `SCRIPT KIDDIE`), `.victory__xp-num` (whitespace-normalised
`150 / 400 XP`), `.victory__rankup` (contains `SCRIPT KIDDIE`), `.victory__identity`,
`.victory__meter`, and the module export `priorProfile` from `/js/ui/screens/victory.js`.

**Hub, gallery, archive**: `.hub-gallery__list` (contains `Clear your first level`),
`.hub-gallery__empty`, `.hub-gallery__count` (text `01`), `.frag--transmission` (`aria-label`
contains `Replay transmission L01`), `.hub-story`, `.story-reel`, `.story-chapter`,
`.story-chapter:not(:disabled)`, `[data-story="epilogue"] .story-chapter__title` (contains `DAWN`),
`.hub-ops`, `.hub-ops.is-offline`, `.hub-ops__title` (exact `Study 120 / 360 min`, starts with
`Study`), `.hub-ops__sub`.

**Command Center**: every `#ops-*` id and `.ops-*` class in `test_client_productivity.py`
(`#ops-study-minutes`, `#ops-form-study .ops-form__submit`, `#ops-tab-study|workout|weight`
with `aria-selected`, `.ops-ring` with `aria-valuenow`/`aria-valuemax`, `.ops-chart`
`aria-label` containing `N weigh-ins`, `.ops-xp__chip--total .ops-xp__value`, `.ops-milestone`,
`.ops-milestones__more`, `.ops-feed .ops-event`, `.ops-fault`, `.ops-armory`, `.ops-weight__togo`,
`.ops-topbar__date`, `.ops-course.is-idle`, …); `aria-invalid` on invalid fields.

**Keys**: Space (boot), Enter (deploy, victory primary), Escape (skip scene, close archive /
viewer / restore bar, open settings from the hub), `s` (story archive), `o` (command center),
`h` (victory to hub), `Alt+R` (restore), `Control+Enter` (hack), ArrowUp/ArrowDown (archive
list, wraps).

Notes for implementers: CSS `text-transform` does not change `textContent`, so case changes
are safe; `display: none` on `.mission-objectives` (M5/M6) is safe (no test reads it, and
`mission.js` only toggles classes on its rows); hiding `.hub-feed` / `.hub-sector` below 768 px
(A6) is safe (tests run at desktop size; neither is asserted).

---

## 7. Verification checklist

Run after each step of §5.11, from a temp copy, never the repo folder:

1. `python -m unittest tests.test_client_fixes tests.test_client_story tests.test_client_productivity -v`
   (Playwright + Chromium; they skip when unavailable) and the full suite.
2. Re-capture with `scripts/capture.py` into `scratchpad/design/after/` at 1440x900, 1280x720,
   390x844 and compare pairwise with `before/`. Look at every pair.
3. Contrast: re-run `scripts/contrast.py` with the final values; every text row at 4.5:1
   (3:1 for text 18 px+ / bold 14 px+, and for locked/disabled UI).
4. Editor width: at 1440 the L01 header rule (`====…`) and `TARGET: WATCHDOG` fit without
   horizontal scroll; at 1280 at most the longest header line scrolls.
5. Narrow: at 390 the mission editor is visible and typeable, HACK is reachable, the hub map
   scrolls horizontally with traces still 45 degrees, nothing overlaps in either topbar.
6. Focus: Tab through hub, mission, dialogue, victory, settings, archive: every stop shows the
   2 px solid ring in the local colour; no amber ring outside warnings.
7. Glow budget: count glowing elements at rest per screen against §4.6.
8. Reduced motion (OS setting and in-game toggle): no idle loop runs; event beats complete.
9. `quality-low` and `body.no-webgl`: glass becomes opaque and every text pair still passes.
10. Pre-flight (design-taste §14, game-relevant boxes): no wrapped CTA at desktop, one
    corner-cut grammar per kind (structural / alert), one focus ring, no em-dash in chrome
    strings touched, no new gradient besides the logo, reduced motion honoured.

---

## 8. Implementation notes (deviations found while executing)

- **Mission tabs (M7)**: the narrower brief column (M1) no longer fits the full tab labels at
  1440. The tabs switch to the short labels (COMMS / WHY / MANUAL) by *container* width
  (`container-type: inline-size` on `.mission-brief`, threshold 336 px) instead of the old
  1180 px media query, so they never clip at any window size.
- **Layer names (M1)**: instead of ellipsizing the code chip ("Frame integrity - i..."), layer
  names wrap to at most two lines (`-webkit-line-clamp: 2`), unclamped when INTEL is open. The
  list scrolls in the tight case (INTEL open at 900 px tall). The enemy readout's "· 7 LAYERS"
  drops by container width.
- **Narrow grids (M6, A6)**: the single-column hub and mission use `grid-auto-rows: max-content`
  (auto rows collapse scroll containers to their min-content size); the phone brief has a fixed
  42 dvh height and the attempt counter, timer label and level number leave the phone topbar.
- **DEPLOY (A5)**: boss titles would still wrap ("L15 · BOSS: THE FORGEMASTER"), so the deploy
  title uses the short title and the kicker reads "DEPLOY ▸ // BOSS" (hub.js).
- **Dialogue (D1)**: `dialogue.js` sets `--speaker-rgb` next to `--speaker`, so the frame, the
  buttons and the focus ring all tint per speaker through the normal `--accent-rgb` hooks.
- **Boot (A16)**: the scrim fades in with the reveal (on the pure-black pre-reveal veil it showed
  as a grey disc) and the subtitle gets the cutscene subtitles' dark text shadow. Measured over
  the beam core: 1.09:1 before, 4.1:1 against the brightest neighbouring beam pixel after.
- **Victory skip (V3)**: `--text-2` pulsing 1 to .75 opacity (5.2:1 at the low point); `--meta`
  pulsing would dip under AA. DELETED stamp: `--blood-ink #ff6b81` on a dark plate. Enemy
  readout: `--blood-ink` at 85 % (blood at 85 % measured 4.1:1).
- **Cutscene on phones (C2)**: with the 16 vh bar cap the subtitles no longer fit inside the
  lower bar, so below 640 px they sit over the picture just above it.
- **Not done**: M12 (compact objective checklist) is left as the open option it was written as.
