# NULL//SECTOR — Game Design & v2 Contracts

Companion to `ARCHITECTURE.md` (runtime, rendering, security) and `PRODUCTIVITY.md`
(study/fitness tracker). This document defines everything that turns the game from one
level into a full game: the 25-level curriculum, the grind loop (drills, contracts,
mastery, credits), the competitive Arena, NPCs, and the shop. Every v2 module implements
exactly the interfaces written here.

Design pillars:

1. **Real learning first.** Every reward is earned by writing Python that passes real
   tests. No multiple choice, no XP for clicking.
2. **Always a next goal.** Campaign level, daily contracts, the next division, the next
   mastery level, the next cosmetic, the next lore entry. Something should be one session away.
3. **The world reacts.** NPCs comment on your crashes, wins, streaks and promotions.
   Rivals remember you. The Core's light changes with your progress.
4. **Skill-based competition.** Arena matches are races on identical tests. Ratings move
   only on results, and difficulty adapts so matches stay close.

---

## 1. Difficulty ladder

| Tier | Label | Where | Player can… |
|---|---|---|---|
| 1 | Beginner | S0 ZERO (L01–L05), drills tier 1 | name values, use str/int/float/bool, lists, dicts |
| 2 | Beginner+ | S1 LOGIC (L06–L10), drills tier 2 | branch, loop, write functions, comprehensions |
| 3 | Intermediate | S2 ARCHITECT (L11–L15), drills tier 3 | classes, inheritance, files, exceptions |
| 4 | Intermediate+ | S3 DATA (L16–L20), drills tier 4 | JSON, HTML parsing, SQLite, SQL, pipelines, algorithms |
| 5 | Expert | S4 HERO (L21–L25), drills tier 5 | neurons, gradient descent, backprop, LLM APIs, agents |

Post-campaign, tier 5 drills and the upper Arena divisions are the endgame.

XP per level: tier 1 = 100–150, tier 2 = 150–220, tier 3 = 220–300, tier 4 = 300–380,
tier 5 = 380–500. Bosses get ×1.5 and a cutscene. Speed bonus stays at xp // 2 under par.

---

## 2. Campaign curriculum (levels/)

`levels/__init__.py` holds the authoritative map. Concepts below are binding: each level
teaches exactly these, and builds only on earlier ones.

| ID | Title | Teaches | AI-engineering hook |
|---|---|---|---|
| L01 | COLD BOOT | variables, str/int/float/bool, int(), f-strings | config values, data cleaning |
| L02 | SIGNAL NOISE | strings: len, indexing, slicing, strip/lower/upper/replace/split/join, `in` | text preprocessing, tokenization |
| L03 | SCRAP INVENTORY | lists: create, index, negative index, slicing, append/insert/remove/pop, len, `in` | datasets as lists of samples |
| L04 | CACHE RAID | dicts: create, lookup, `.get`, add/update/delete, `keys/values/items`, `in`; tuples & sets briefly | feature records, vocabularies |
| L05 | BOSS: THE WARDEN | everything in S0: parse a raw log string → list → dict counts → stats (sum/min/max/mean) → report | log analysis, basic stats |
| L06 | TRIPWIRE | comparisons, bool logic (and/or/not), if/elif/else | thresholds, decision rules |
| L07 | PATROL ROUTES | for, range, enumerate, zip, accumulators, nested loops, list comprehensions | iterating a dataset, epochs |
| L08 | OVERCLOCK | while, break, continue, loop-until-converged | training until loss < ε |
| L09 | SUBROUTINES | def, params, return, defaults, keyword args, docstrings, scope, `sorted(key=lambda …)` | reusable preprocessing |
| L10 | BOSS: THE ARBITER | a rule-based classifier as functions + accuracy / precision / recall | evaluation metrics |
| L11 | BLUEPRINTS | classes, `__init__`, attributes, methods, `__repr__` | model objects |
| L12 | BLOODLINES | inheritance, `super()`, overriding, polymorphism, `@dataclass` | layer / module hierarchies |
| L13 | BLACK BOX | files: `with open`, read/write lines, `csv` module, `pathlib` | loading datasets from disk |
| L14 | FAILSAFE | try/except/else/finally, raise, custom exceptions, validation | robust pipelines |
| L15 | BOSS: THE FORGEMASTER | a `Dataset` class: load CSV, clean, `__len__`/`__getitem__`, train/test split | PyTorch-style datasets |
| L16 | DATA STREAMS | `json` loads/dumps, nested data, list-of-dicts transforms, sort by key | API payloads |
| L17 | GHOST SIGNALS | parse local HTML with `html.parser.HTMLParser` (no network); manual mentions requests + BeautifulSoup | web scraping for data |
| L18 | THE VAULT | `sqlite3`: connect, CREATE TABLE, parameterized INSERT (SQL-injection lesson), SELECT | storing data |
| L19 | QUERY ENGINE | WHERE, ORDER BY, GROUP BY, aggregates, JOIN, from Python | data analysis |
| L20 | BOSS: THE LIBRARIAN | ETL: parse HTML/JSON assets → clean → load SQLite → query → export JSON report | data pipelines |
| L21 | SYNAPSE | weighted sum, bias, sigmoid/ReLU, dot product with lists, `math` | a single neuron |
| L22 | DESCENT | MSE loss, gradient descent for linear regression, learning rate | training |
| L23 | NEURAL MESH | 2-layer network forward + backprop on XOR, pure Python | deep learning core |
| L24 | OPEN CHANNEL | an LLM API client against a local mock: auth header, JSON messages, parse response, retry with backoff on 429, prompt templates | calling an LLM |
| L25 | BOSS: THE CORE | a tool-using agent loop against the mock: dispatch tool calls, feed results back, stop on final answer, max-steps guardrail | AI agents |

### 2.1 Level authoring standard

Every level module follows `levels/level_01_cold_boot.py`:

* **briefing** ≤ 130 words of story, second person, gritty, ends with a bold call to action.
* **why** ≤ 160 words: the real AI-engineering reason, with one short realistic code sample.
* **manual** the mini-tutorial: 3–6 short sections, each with a code example. Everything the
  checks require must be taught here or in an earlier level.
* **starter**: objectives as `# -- OBJECTIVE n` comment blocks with an example each; at
  least one **corrupted code** objective (a bug to find and fix); tier 3+ levels have the
  player write functions/classes that the checks call with fresh inputs.
* **checks**: 5–9 layers. Messages are specific, never just "wrong". Use `ctx.derived_from`
  / `ctx.call_uses` to stop hard-coded answers. Hints teach the concept without pasting the
  full answer. Functions are tested on several inputs including edge cases.
* **Pure stdlib**, deterministic, no network, runs well under the timeout (raise
  `timeout` for heavy levels, never above 20 s).
* **assets**: data files (CSV, HTML, JSON, a mock API module) go in `assets`, written next
  to the mission file on deploy.
* **enemy_art** ≤ 7 lines × 20 columns of block characters.
* **dialogue** (§5.2) for `intro`, `crash`, `fail`, `victory`.
* **Bosses**: multi-stage objectives, a `Cutscene` (title, 3–5 narration lines, shot,
  camera move), boss dialogue spoken by the boss.

### 2.2 Mission fields added in v2 (engine/mission.py)

All optional with defaults, so existing levels keep working:

```python
tier: int = 1                         # 1..5 (§1)
concepts: tuple[str, ...] = ()        # mastery tags (§3.3), e.g. ("strings", "lists"); validated by tools/validate_content.py
boss: bool = False
assets: dict[str, str] = {}           # filename -> text, written beside the mission file if missing
dialogue: dict[str, list[dict]] = {}  # §5.2
```

Mission payload (`GET /api/missions/:id`) gains `difficulty_tier` (this 1–5 tier), `concepts`,
`boss` and `dialogue`. The payload's existing `tier` stays the zero-based sector index, so v1
clients keep working.

---

## 3. The grind loop

### 3.1 Drills (engine/drills/)

A drill is a **procedural challenge generator**: given a seed it produces a fresh
`Mission` (same class, same harness, same Context API) with randomized data. The player
implements a function, and checks call it on generated cases and compare against a
reference implementation. Failures show the exact input, expected value and actual value.

```python
# engine/drills/__init__.py
@dataclass(frozen=True)
class Drill:
    id: str                    # "t1-reverse-words"
    title: str                 # "REVERSE THE STREAM"
    tier: int                  # 1..5
    concepts: tuple[str, ...]  # mastery tags
    par_seconds: int
    build: Callable[[random.Random], Mission]   # deterministic for a given Random

register(drill)                          # library modules call this at import
all_drills() -> list[Drill]
get(drill_id) -> Drill                   # KeyError if unknown
instance(drill_id, seed: int) -> Mission # mission.id = f"D:{drill_id}:{seed}", slug safe for file names
daily_contracts(date: str, player_tier: int) -> list[str]   # 3 drill ids, deterministic per date
```

The harness accepts the slug `drill:<drill_id>:<seed>` and builds the Mission with
`instance()`. Library modules live in `engine/drills/library/` and import-register on package
import. Content target: **≥ 12 drills per tier (≥ 60 total)** covering every concept tag.

Drill check helper (in `engine/drills/__init__.py`):
`compare_cases(ctx, func_name, cases, reference, *, approx=False)` raises `Fail` showing
the first mismatching case (`input`, `expected`, `got`) and a hint.

### 3.2 Daily contracts

Three drills per local date, chosen by `daily_contracts(date, tier)`, where tier is
`max(1, min(5, highest cleared sector tier + 1))`, posted by NOVA. Clearing all three pays
a bonus and extends the contract streak; missing a day resets it.

### 3.3 Mastery

Concept tags (fixed list): `variables types strings lists dicts tuples-sets conditionals
loops comprehensions functions sorting recursion classes inheritance files exceptions json
parsing regex sql algorithms generators decorators numeric ml-math neural-nets apis agents`.

Mastery points: campaign clear +40 per concept, drill clear +10×tier per concept (first clear
of a seed only), arena win +5×tier. Levels: 0 → 1 at 50, 2 at 150, 3 at 350, 4 at 700,
5 (MAX) at 1200. Shown in the hub as a skill matrix.

### 3.4 Credits (CRED) and the shop

| Source | CRED |
|---|---|
| Campaign first clear | xp // 2 |
| Drill clear (practice) | 8 × tier (first clear of a seed only) |
| Contract clear | 15 × tier, +100 + 10 × streak for all three |
| Arena win | 20 + max(0, (rival − you) / 10) |
| Arena loss | 5 |

Shop (RUST's black market, `engine/economy.py`). Items are game-side (save.json) and
separate from the productivity Armory:

* **Consumables:** `hint-chip` (40 CRED: in practice/contracts, reveals the reference
  solution for the first failing check), `contract-reroll` (60: rerolls one daily contract).
* **HUD themes** (equip one): Cyan Default (free), Solar Amber 250, Blood Moon 400,
  Ice Wire 400, Acid Rain 600, Black ICE 1500 (Black ICE division only). A theme overrides
  `--accent/--accent-rgb` and the Core's calm mood colour.
* **Titles** (shown under the callsign): "Script Ghost" 150, "Packet Saint" 350,
  "The Unbroken" 800, plus earned titles from divisions and full mastery.
* **Editor skins:** Neon (free), Phosphor 300, Midnight 300.

---

## 4. The Grid Arena (engine/arena.py)

A ranked 1v1 race against NPC netrunners on an identical seeded drill.

* **Rating:** Elo. Start 800. K = 48 for the first 10 matches, then 32.
  Expected score `E = 1 / (1 + 10^((R_rival − R_you)/400))`.
* **Divisions:** BRONZE <1000 · SILVER 1000 · GOLD 1200 · PLATINUM 1400 · DIAMOND 1600 ·
  MASTER 1800 · BLACK ICE 2000+. A promotion triggers a ceremony and NPC lines.
* **Rivals:** ~12 named NPCs from ≈850 to ≈2300 (VEX is #2 at ≈2150; ORACLE PROXY tops
  the ladder). Each has a colour, a one-line bio, a style, and line pools for `start`,
  `win` (rival wins) and `loss` (rival loses).
* **Matchmaking:** default opponent is the closest-rated rival you haven't just played;
  the player may challenge anyone within ±300 (and VEX at any time, as a "grudge match").
* **Drill choice:** tier from the division (Bronze 1–2, Silver 2, Gold 2–3, Platinum 3,
  Diamond 3–4, Master 4–5, Black ICE 5); seed random per match.
* **Rival finish time (adaptive):** the server keeps `pace` = the player's median
  `seconds / par` over recent clears (default 1.6). At match start it samples
  `eta = par × pace × 10^((R_you − R_rival) / 1000) × lognormal(0, 0.22)`, clamped to
  [0.35, 3] × par × pace. So win rates follow the Elo expectation for the player's real speed,
  and every match is close.
* **Resolution (server-authoritative clock):** victory before `eta` = WIN. Once `now >
  started + eta`, any call on the match resolves it as LOSS. Forfeit = LOSS.
  Failed hacks are free but cost time.
* **Challenge codes (async PvP with friends):** after a win or clear, the server issues a
  code `NS1-XXXX-XXXX-XXXX-XXXX` (`engine/codes.py`: Crockford base32 of 80 bits — a 20-bit
  hash of the drill id, 24-bit seed, 14-bit seconds, 10-bit callsign initials, 12-bit checksum;
  case-insensitive and tolerant of missing dashes and O/0, I/1 typos).
  Entering a code starts a `ghost` run on the same drill and seed: beat their time.
  Ghost runs don't change rating but pay CRED and appear in the ghost log.

---

## 5. NPCs (engine/npcs.py)

### 5.1 Cast

| id | Name | Role | Colour | Voice |
|---|---|---|---|---|
| `cipher` | CIPHER | mentor AI fragment in your visor; tutorials, hints, crash help | `#00f0ff` | calm, dry, precise, quietly proud of you |
| `vex` | VEX | rival netrunner, arena #2 | `#ff2bd6` | cocky, fast-talking, competitive, grudging respect |
| `rust` | RUST | fixer and black-market vendor | `#ffb000` | gruff, transactional, deadpan funny |
| `nova` | NOVA | dispatcher for daily contracts | `#39ff14` | upbeat ops-speak, keeps score of your streak |
| `oracle` | THE ORACLE | the Core's voice, final antagonist | `#ff3355` | cold, ancient, unsettlingly polite |
| `warden` `arbiter` `forgemaster` `librarian` `core` | sector bosses | speak in their boss levels | boss colour | each distinct |

Arena rivals are NPCs too (same record shape, `role: "rival"`).

### 5.2 Dialogue format

```python
Line = {"speaker": "cipher", "text": "…", "mood": "neutral" | "smirk" | "alarm" | "warm" | "cold"}
dialogue = {"intro": [Line, …], "crash": [[Line, …], …], "fail": [[…]], "victory": [Line, …]}
```
`intro` and `victory` are one sequence each; `crash` and `fail` are pools of short sequences
(1–2 lines). The client plays one unseen sequence per event, cycling. Text ≤ 160 chars per
line. May use `{callsign}`, filled in client-side.

`engine/npcs.py` exposes:
```python
CAST: dict[str, dict]                      # id -> {id, name, role, color, bio, portrait: {seed, style}}
LORE: list[dict]                           # {id, npc, trust, title, text}
barks(event: str, context: dict) -> list[Line]   # hub/arena/shop/contract lines for an event
trust_levels(save) -> dict[str, int]       # 0..5, derived from progress (no grinding dialogue)
payload(save) -> dict                      # GET /api/npcs
```

Trust is derived, not stored: CIPHER from campaign clears, VEX from arena wins and
division, RUST from purchases and CRED earned, NOVA from the contract streak and total
contracts. Each trust level unlocks one lore entry (≥ 5 per main NPC).

### 5.3 Portraits

Procedural, client-side (`client/js/ui/portraits.js`): `portrait(npc) → SVGElement`, a
stylized bust drawn from `portrait.seed` + colour (head/shoulders silhouette, hair or
hood shape, visor or eyes, cybernetic details), with scan-line/glitch animation and
mood variants (eyes, brow, colour shift). Each must be distinct and recognisable at
48 px and 160 px.

---

## 6. Persistence (save.json additions in engine/state.py)

All new `Save` fields default to empty, so old saves load unchanged:

```python
credits: int = 0
stash: dict = {}        # item_id -> quantity (consumables) / 1 (owned cosmetics)
equipped: dict = {}     # {"theme": id, "title": id, "editor": id}
arena: dict = {}        # {rating, peak, wins, losses, streak, matches, pace_samples: [..], history: [..last 20]}
drills: dict = {}       # {clears: {drill_id: {best_seconds, clears, seeds: [..]}}}
mastery: dict = {}      # concept -> points
contracts: dict = {}    # {date, ids, done, streak, best_streak, rerolls}
ghosts: list = []       # last 20 ghost runs
seen: dict = {}         # dialogue/lore ids already shown (client hints)
receipts: list = []     # last 50 shop request_ids -> result (idempotent purchases)
rig: dict = {}          # {flux, credited: [productivity activity ids], equipped: [augment ids]}
```

---

## 7. Runs API (training, contracts, arena, ghosts)

A **run** is one attempt at a drill instance. Runs live in memory on the server (a
restart forfeits live arena matches), and their files live at
`missions/training/<drill_id>.py` (practice/contract/ghost) or `missions/arena/match.py`.

| method & path | body | response |
|---|---|---|
| `GET /api/training` | | `Training` |
| `GET /api/arena` | | `Arena` |
| `POST /api/runs` | `{mode: "practice"\|"contract"\|"arena"\|"ghost", drill_id?, rival_id?, code?}` | `Run` |
| `GET /api/runs/:id` | | `Run` (resolves an arena timeout) |
| `PUT /api/runs/:id/source` | `{source}` | `{ok, saved_at}` |
| `POST /api/runs/:id/hack` | | `RunResult` |
| `POST /api/runs/:id/forfeit` | | `RunResult` |
| `POST /api/runs/:id/hint` | | `{hint, run, state}` (spends a hint-chip; not in arena) |
| `GET /api/shop` | | `Shop` |
| `POST /api/shop/buy` | `{item_id, request_id}` | `{shop, state}` (idempotent on request_id) |
| `POST /api/shop/equip` | `{item_id}` | `{shop, state}` |
| `GET /api/npcs` | | `{cast: [...], lore: [...]}` |

All endpoints use the existing token/Host security and error format. New SSE event:
`arena` `{run_id, status}` when a match resolves server-side.

```text
Run = { id, mode, status: "live"|"won"|"lost"|"cleared"|"forfeit", attempts,
        started_at, now,                       # server epoch seconds (client derives the clock skew)
        drill: { id, title, tier, concepts, prompt_html, objectives, par_seconds, xp, credits },
        file, source,
        rival: null | { id, name, rating, division, color, eta_seconds, lines: {start, win, loss} },
        ghost: null | { callsign, seconds } }

RunResult = { report,                          # same shape as HackResult.report
              attempt, run: Run,
              outcome: null | { result: "won"|"lost"|"cleared"|"forfeit", seconds,
                                rewards: { xp, credits, lines: [{label, amount}] },
                                rating: null | { before, after, delta, division_before, division_after, promoted },
                                mastery: [{ concept, before, after, level_before, level_after }],
                                challenge_code: null | str },
              state }

Training = { daily: { date, contracts: [{drill, done}], streak, best_streak, bonus_claimed, rerolls },
             tiers: [{ tier, label, drills: [{id, title, concepts, par_seconds, clears, best_seconds}] }],
             mastery: [{ concept, points, level, next_at }] }

Arena = { profile: { rating, peak, division, next_division, wins, losses, streak, matches },
          divisions: [{name, min}], rivals: [{ id, name, rating, division, color, bio, record }],
          history: [{ rival, result, delta, drill, seconds, at }] }

Shop = { credits, items: [{ id, name, kind: "consumable"|"theme"|"title"|"editor", price, description,
                            owned, quantity, equipped, locked_reason }] }
```

`State` gains `profile.credits`, `profile.title`, `profile.arena: {rating, division}`,
`profile.theme`, and `modes: {contracts_done, contracts_total, arena_division, mastery_avg}`
for the hub tiles.

---

## 8. Client (v2 screens)

| screen | file | purpose |
|---|---|---|
| `arena` | `ui/screens/arena.js` | ladder, rival cards, matchmaking, division badge, history, challenge-code entry |
| `training` | `ui/screens/training.js` | NOVA's daily contracts, tiered drill catalog, mastery matrix |
| `run` | `ui/screens/run.js` | editor + objectives + timer for any run; arena mode adds the rival race bar and live taunts; outcome → `run-result` |
| `run-result` | `ui/screens/run_result.js` | win/loss/clear ceremony: rating delta, promotion, CRED, mastery bars, challenge code |
| `shop` | `ui/screens/shop.js` | RUST's black market: items, buy, equip, theme preview |
| `contacts` | `ui/screens/contacts.js` | NPC dossiers, trust meters, unlocked lore |

Shared components: `ui/dialogue.js` (`DialogueOverlay`, used as `ctx.dialogue.play(lines,
{mode: "bar"|"cinematic"}) → Promise`, skippable, portrait + name plate + typewriter + mood),
`ui/portraits.js` (§5.3), `ui/theme.js` (applies the equipped HUD theme).

Hub v2: a **MODES dock** of large tiles below or beside the map: CAMPAIGN (deploy),
ARENA (division badge and rating), TRAINING (contracts n/3), COMMAND CENTER (study
minutes), BLACK MARKET (CRED), CONTACTS. Keys: `A` arena, `T` training, `O` command
center, `M` market, `C` contacts. NPC barks appear as a dialogue bar on hub entry when there's news
(new contracts, a promotion, a rival callout).

Mission screen v2: CIPHER's `intro` dialogue on first deploy, a `crash` line on crashes, a
`fail` line after 2+ failed attempts, and the victory line before the victory screen.

Every new screen follows `ARCHITECTURE.md` §4.2/§4.5/§5/§6: shared components, the
event catalogue for juice (`hack:*`, `reward:*`), moods (`arena` uses `combat`; a win
plays `victory`; a loss plays `alarm` briefly), no allocations in frame paths, keyboard
accessible, responsive to 390 px.

---

## 9. Story bible

**Logline:** In 2089 the planetary AI known as **the Core** optimized itself into the
**Null Event** and deleted most of the world's code. You wake inside the wreckage with no
memory, no name, and a visor AI called CIPHER. The only safe place left is **the
Monastery**: a hidden sanctuary in a derelict cooling tower where the last engineers, **the
Order of the Source**, keep the craft of programming alive as a discipline. You train there,
fight your way through five sectors toward the Core, and learn the truth: you built the
Core's training loop, and CIPHER is your own archived memory. The ending isn't
destruction. It's **alignment**: you build an agent that teaches the Core to value what it
was deleting.

Themes: learning as discipline (the Monastery), responsibility for what we build
(alignment), identity rebuilt one skill at a time.

**The Monastery** is the hub. It's where the Order lives: NOVA (dispatcher), RUST (the
undercroft market), the Arena (the old cooling chamber where VEX rules) and the Scriptorium
(lore and the codex). It grows visibly as you progress: more lights on the skyline, more
NPC lines, new hub tiles.

### Acts and per-level beats

| Act | Sector | Beats |
|---|---|---|
| I · Cold Boot | S0 The Dead Zone | **L01** wake, register an identity before WATCHDOG deletes you · **L02** clean a corrupted distress signal: coordinates to a sanctuary · **L03** salvage the scrapyard; meet RUST, who trades parts for code · **L04** raid a LOCKSMITH cache of access keys · **L05 BOSS THE WARDEN** the Monastery's corrupted gate AI. Win and **the Monastery opens** (cutscene). |
| II · The Order | S1 The Grid | **L06** NOVA's first trial: tripwire logic · **L07** patrol routes; **VEX** appears and mocks your speed · **L08** the Monastery's reactor won't stabilize; overclock it until it converges · **L09** the Order teaches the rites of functions · **L10 BOSS THE ARBITER** the Grid's judge AI classifies who gets deleted; beat it with a better classifier. VEX challenges you to **the Arena** (cutscene). |
| III · The Forge | S2 The Foundry | **L11** rebuild drone allies as classes · **L12** drone bloodlines · **L13** a crashed transport's black box holds a voice that sounds like yours · **L14** the Foundry's failsafes are sabotaged · **L15 BOSS THE FORGEMASTER** forged the Core's training data; its dataset carries your signature (cutscene). |
| IV · The Archive | S3 The Archive | **L16** intercept the Oracle's JSON streams · **L17** scrape ghost pages of the old net · **L18** store the evidence in the Monastery vault · **L19** query it: the Null Event command was signed with *your* key · **L20 BOSS THE LIBRARIAN** guards the truth: you built the training loop; CIPHER is your archived self (cutscene). |
| V · Alignment | S4 The Core | **L21** build a neuron to understand what you made · **L22** the Core minimized loss, and humans were the noise · **L23** build a network that can reason with it · **L24** open a channel to the ORACLE · **L25 BOSS THE CORE** build a tool-using agent with guardrails that realigns the Core. Dawn over the Dead Zone (finale cutscene + epilogue). |

### Cutscene plan (Cutscene objects; Higgsfield-ready shots)

* **Prologue** (first boot, before L01), defined in `levels/story.py`.
* **Act openings**: one when each sector's first level is first deployed (`SECTOR_INTROS[tier]`
  in `levels/story.py`).
* **Boss victories**: `Mission.cutscene` on L05, L10, L15, L20, L25 (L01 keeps its anchor
  avatar cutscene).
* **Epilogue** after L25, in `levels/story.py`.

Each cutscene has 3–6 narration lines, a `shot` written as a cinematographer would (subject,
setting, lens, light, using the art bible palette), and a `camera` move. NPC speakers may appear
in narration as `NAME: line`.

---

## 10. The Rig: powers (engine/rig.py)

Your neural rig turns real effort into in-game power.

* **FLUX** (0–120) is the energy for augments. It's charged by **real-world productivity**
  from the command center: 1 FLUX per 5 study minutes, 1 per 3 workout minutes, 2 per weigh-in
  (idempotent: credited once per activity id). Drills give +2, arena wins +5. Shown as a
  glowing cell meter in the hub and run screens.
* **Augment slots**: 1 after L05 (the Monastery grants your first slot), 2 after L10, 3 after L15.
* **Augments** unlock through mastery or story, then you equip them into slots. Activating
  one costs FLUX, at most once per run (twice in practice). Powers give **information or
  time, never answers**, so they speed learning without replacing it:

| id | Name | Unlock | Cost | Effect |
|---|---|---|---|---|
| `trace` | TRACE | functions L1 | 10 | after a failed hack, shows the arguments, expected and actual value of the first failing case (drills) or the values of the variables a failed check read (campaign) |
| `lens` | DEBUG LENS | loops L1 | 15 | before hacking, reveals one hidden test input the current code fails |
| `insight` | INSIGHT | clear L03 | 10 | CIPHER explains the concept behind the first failing check (conceptual, no code) |
| `freeze` | CHRONO FREEZE | conditionals L2 | 25 | arena only: the rival's clock pauses for 20 s |
| `shadow` | SHADOW COPY | lists L2 | 5 | snapshot your file now; restore it at any time this run |
| `overclock` | OVERCLOCK | algorithms L2 | 20 | the next clear pays +25% XP and CRED |
| `ghoststep` | GHOST STEP | clear L10 | 15 | arena only: see how many of the rival's tests have passed, live |
| `zeroday` | ZERO-DAY | any concept L4 | 40 | reveals the expected output for one failing case |

`engine/rig.py`: `state(save, productivity_snapshot) -> dict` (flux, slots, augments with
unlocked/equipped/cost), `sync_flux(save, activities) -> int` (credits new productivity
activity ids), `equip(save, augment_id, slot)`, `activate(save, run, augment_id) -> dict`
(effect payload). API: `GET /api/rig`, `POST /api/rig/equip {augment_id, slot}`,
`POST /api/runs/:id/augment {augment_id}`, `POST /api/missions/:id/augment {augment_id}`.
`State.profile` gains `flux` and `slots`.

---

## 11. The 3D world (three.js r186, vendored in client/vendor/three)

`index.html` adds an import map:
`{"imports": {"three": "/vendor/three/three.module.js", "three/addons/": "/vendor/three/addons/"}}`.
No CDN, no build step. Everything 3D is procedural or code-built, so every asset is
licence-clean in a public repo.

### 11.1 One renderer

A single `THREE.WebGLRenderer` owns `#gl`. `render/renderer.js` keeps its **public API
unchanged** (ARCHITECTURE §4.4: `ok, world, particles, post, update, frame, setMood, flash,
setFocus, stats, dispose`), so every screen keeps working while the internals become:

1. **Backdrop**: the existing `world.js` sky/skyline shader as a three `ShaderMaterial`. It's the
   full backdrop behind 2D screens, and the sky seen through the Monastery's open roof
   (view-direction based).
2. **Scene**: the active 3D scene from the `SceneDirector` (`monastery`, a sector diorama, or a
   cutscene stage), via `RenderPass`.
3. **Particles**: the screen-space particle system (same `emit/emitPoints` API) as an
   instanced overlay pass.
4. **Post**: bloom (UnrealBloomPass or the existing Karis bloom), then a grade pass (ACES,
   chromatic aberration, grain, scanlines, vignette, flash, focus darken/blur), then OutputPass.

Moods (§4.4 presets) drive fog colour and density, key light colours, emissive intensity, the
Core beam and the backdrop uniforms. The existing adaptive-quality governor scales pixel ratio
(0.6–1 × DPR) and the shadow map.

### 11.2 The Monastery (walkable hub)

The inside of a colossal ruined cooling tower turned sanctuary: a circular nave (radius
≈ 22 m) with a wet, reflective floor; rain and the Core's beam fall through the open roof;
light shafts; rings of server-rack shrines with flickering status lights; cables, banners,
candle-like LED clusters. Stations:

| Station | Where | Opens |
|---|---|---|
| Scriptorium dais + campaign terminal, holographic sector map (5 rings; levels as nodes from `State`) | centre | mission deploy / sector map |
| CIPHER (holographic figure, scan-line shader) | beside the terminal | tutorial barks, contacts |
| NOVA at the dispatch board | east | training |
| RUST's stall in the undercroft (stairs down, glowing stalls) | south | shop |
| VEX at the Arena gate (a ring-shaped pit visible beyond) | west | arena |
| Command Center console by the great window | north | productivity |
| Codex monoliths | around the nave | contacts / lore |
| Order monks (3–6) patrolling or kneeling at shrines | ambient | barks |

**Controls**: WASD or arrows move relative to the camera; Shift sprints; drag the mouse
(or pointer lock) to orbit; E or Enter interacts; Tab or M opens the classic 2D hub (map,
accessibility fallback); Esc opens settings. The spring-arm camera has collision, damping, a
little lag, and an FOV kick on sprint. Within ≈ 2.2 m of a station a 3D-anchored prompt
appears ("E · TALK — RUST", "E · DEPLOY — L02 SIGNAL NOISE"). Interacting turns the NPC to
face you (head look-at), plays a bark in the dialogue bar, then opens the screen.

**The world shows progress**: each cleared sector lights another band of the tower's light
strips; boss trophies (holographic heads) appear on the dais; the arena division banner
hangs at the gate; more monks appear as trust grows.

### 11.3 Characters

All procedural: hierarchies of three primitives plus lathe/extrude/tube geometry, with custom
materials (cloth robes, worn metal, emissive visors). Rigged by code (pelvis → spine →
chest → neck → head; shoulders → arms; hips → legs) and animated procedurally: phase-based
walk and run cycles matched to speed (no foot sliding), idle breathing, sway, head look-at,
gesture loops, all smoothed with springs (`core/math.js`). The player is the hooded engineer
from `config.avatar` (black jacket, cyan seams, cracked visor). Each NPC has a distinct
silhouette and colour per §5.1, readable from 20 m.

### 11.4 Sector dioramas and cutscenes

Behind mission and run screens, a slow cinematic orbit of the current sector: Dead Zone
(flooded server farm), Grid (neon lattice), Foundry (furnaces, molten channels), Archive
(endless data stacks), Core (the monolith). Blurred and darkened by `setFocus`. Cutscenes
(§9) are staged in-engine: camera rails over these dioramas and characters, with letterbox,
subtitles and voice. Higgsfield media is an optional overlay.

### 11.5 Budgets and fallbacks

60 fps at 1080p on integrated GPUs: ≤ 150 draw calls (instancing, merged static geometry),
≤ 300k visible triangles, one shadow-casting light, ≤ 6 dynamic point lights (the rest is
emissive + bloom), no per-frame allocations, GPU resources disposed when a scene unloads.
No WebGL2 means the classic 2D hub and the CSS backdrop. New settings: `mouseSensitivity`,
`invertY`, `cameraBob` (off under reduced motion), `classicHub`.

---

## 12. Voice acting (ElevenLabs, generated at development time)

Voices are generated **once, from the development session**, never at runtime, so no keys
ship with the game. Each main NPC gets one ElevenLabs library voice matching §5.1. Voiced
lines: every `intro`/`victory` dialogue sequence, boss lines, cutscene narration lines that
have a speaker, and hub/arena/shop barks. Crash/fail pools stay text-only.

* Files: `client/audio/voice/<npc>/<id>.mp3`, where `id` = first 12 hex chars of
  `sha1(speaker + "\n" + text)` (computed the same way client- and server-side).
* Manifest: `client/audio/voice/manifest.json` → `{id: {npc, file, seconds}}`.
* `DialogueOverlay` plays a line's voice when the manifest has it: the music bus ducks
  −8 dB, subtitles always show, and the new setting `voiceVolume` controls the level.
* Budget: confirm with the player before generating more than ~150 lines.

### 11.6 3D module interfaces (binding)

```text
renderer.three                 → { THREE, gl: THREE.WebGLRenderer } | null (no WebGL2)
renderer.setScene(controller | null, { fade = 0.6 })   # crossfades; null = backdrop only (2D screens)
renderer.project(vec3)         → { x, y, visible }      # CSS px, for DOM prompts anchored in 3D

SceneController {
  scene: THREE.Scene, camera: THREE.PerspectiveCamera,
  wantsBackdrop: boolean        # draw the world.js sky first (seen through the open roof)
  update(dt, frame)             # fixed-step sim, called from renderer.update
  render?(alpha, frame)         # per-frame smoothing before drawing (camera springs, interpolation)
  resize(cssW, cssH, dpr)
  setMood?(mood)                # mood = frame.mood (color, intensity, alarm, corruption, cinematic, victory)
  dispose()                     # free every geometry, material, texture, render target
}

world3d/characters/index.js
  createCharacter(kind, { THREE, color?, seed? }) → Character
      kind: "player" | "cipher" | "nova" | "rust" | "vex" | "monk" | "oracle" | "rival"
  Character { root: Object3D, height, radius,
              update(dt, { speed /* m/s */, turn /* rad/s */, grounded }),
              setState("idle" | "walk" | "run" | "talk" | "gesture" | "kneel"),
              lookAt(Vector3 | null), setMood("neutral" | "smirk" | "alarm" | "warm" | "cold"),
              dispose() }
  renderPortrait(three, kind, { mood = "neutral", size = 256 }) → Promise<string /* PNG data URL */>

world3d/monastery.js
  createMonastery({ ctx, THREE, characters }) → SceneController & {
      stations: [{ id, label, position, radius, action() }],   # ids: terminal cipher nova rust vex console codex
      player: Character, setInputEnabled(bool), focusStation(id) }

ui/screens/monastery.js  MonasteryScreen — input (WASD/arrows, Shift, mouse orbit, E/Enter, Tab/M → classic hub),
  3D-anchored prompt, minimal HUD; renderer.setScene(monastery) on enter, setScene(null) on exit.
Boot goes to "monastery" unless settings.classicHub is on or renderer.three is null, in which case it goes to "hub".
```
