"""The Grid Arena: ranked 1v1 races against NPC netrunners (docs/GAME_DESIGN.md §4).

You and a rival get the *same* seeded drill. You race the clock the server gives the
rival; finish before it and you win. This module holds the rules of that race and
nothing else:

* the ladder: ``DIVISIONS`` and the ``RIVALS`` you can fight,
* the rating maths: Elo (``expected_score``, ``k_factor``, ``rating_change``),
* matchmaking: who you fight by default and who you may challenge,
* the adaptive rival clock: ``rival_eta`` (so matches stay close at *your* real speed),
* bookkeeping: ``resolve`` writes the result into the save,
* the ``GET /api/arena`` payload: ``payload``.

It is pure: no files, no network, no locks, and no clock. When something needs the time
(the history entry of a match) the caller passes ``now`` in. Randomness also comes in
from outside as a ``random.Random``, which makes every function easy to test: give it
``random.Random(7)`` and you always get the same answer.

The save's ``arena`` dict looks like this (all keys optional; old saves have ``{}``)::

    {"rating": 800, "peak": 800, "wins": 0, "losses": 0, "streak": 0, "matches": 0,
     "pace_samples": [1.2, 0.9, ...],            # seconds / par of recent clears (<= 20)
     "history": [{"rival", "result", "delta", "drill", "seconds", "at"}, ...],  # <= 20
     "records": {"vex": {"wins": 1, "losses": 4}, ...}}   # your record vs each rival
"""
from __future__ import annotations

import math
import random
import statistics
from typing import Iterable

# ── tuning ───────────────────────────────────────────────────────────────────────────

START_RATING = 800
RATING_FLOOR = 100            # Elo can't push you below this: nobody is rated negative
K_NEW = 48                    # big swings while the game is still learning your level...
K_SETTLED = 32                # ...then steadier ones
PLACEMENT_MATCHES = 10        # how many matches count as "new"
CHALLENGE_RANGE = 300         # you may challenge rivals within +-300 of your rating
GRUDGE_RIVAL = "vex"          # ...and VEX at any time
HISTORY_LIMIT = 20
PACE_LIMIT = 20               # pace samples kept
DEFAULT_PACE = 1.6            # a new player takes ~1.6x par
PACE_SAMPLE_RANGE = (0.1, 10.0)   # one absurd clear can't wreck the median
ETA_SPREAD = 0.22             # sigma of the lognormal luck factor
ETA_CLAMP = (0.35, 3.0)       # rival finishes within [0.35, 3] x par x pace
SEED_LIMIT = 1 << 24          # seeds fit the 24-bit field of a challenge code

# (name, minimum rating). Your division is the last row whose minimum you've reached.
DIVISIONS: tuple[tuple[str, int], ...] = (
    ("BRONZE", 0),
    ("SILVER", 1000),
    ("GOLD", 1200),
    ("PLATINUM", 1400),
    ("DIAMOND", 1600),
    ("MASTER", 1800),
    ("BLACK ICE", 2000),
)

# Which drill tiers each division races on (§4 "Drill choice").
DIVISION_TIERS: dict[str, tuple[int, ...]] = {
    "BRONZE": (1, 2),
    "SILVER": (2,),
    "GOLD": (2, 3),
    "PLATINUM": (3,),
    "DIAMOND": (3, 4),
    "MASTER": (4, 5),
    "BLACK ICE": (5,),
}


class ArenaError(Exception):
    """A request the arena rules refuse. `status` is the HTTP status to answer with."""

    def __init__(self, status: int, message: str, code: str = "arena"):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


# ── the ladder ───────────────────────────────────────────────────────────────────────
# Every line is <= 160 characters. `start` is said when the match begins, `win` when the
# RIVAL wins (you lost), `loss` when the rival loses (you won). Lines may use {callsign}.

def _rival(rid, name, rating, color, style, bio, start, win, loss) -> dict:
    return {"id": rid, "name": name, "rating": rating, "color": color, "style": style,
            "bio": bio, "lines": {"start": list(start), "win": list(win), "loss": list(loss)}}


RIVALS: tuple[dict, ...] = (
    _rival(
        "patch", "PATCH", 850, "#8fd694", "scavenger",
        "Scrapyard kid who learned Python from salvaged error logs. Copies first, understands "
        "later. He is getting better faster than he admits.",
        ["Okay. Okay okay okay. Same drill, right? No peeking. I mean, I wasn't gonna peek.",
         "I read the whole manual this time. Well. Most of it. The code parts.",
         "RUST says you're the new one. I'm the new one too. Was. Whatever. Go."],
        ["I WON? Wait, let me run it again. ...Still green. Huh. Huh!",
         "Don't tell anyone I cried a little. It's the scrap dust.",
         "Guess the error logs taught me something after all."],
        ["Yeah. Yeah, that's fair. Your loop was cleaner. I'm stealing it. Learning it. Same thing.",
         "I had it! I had... an IndexError. I had an IndexError.",
         "Rematch later? After I read the rest of the manual."]),
    _rival(
        "mute", "MUTE", 960, "#a7b4c2", "terse",
        "Never speaks aloud. Communicates only in code comments, ships only clean diffs, and "
        "has never once been seen debugging.",
        ["# ready.", "# same seed. same tests. go.", "# talk less. type more."],
        ["# done. tests green. you: not yet.", "# speed is just fewer wrong guesses.",
         "# good attempt. read your traceback."],
        ["# noted.", "# you were faster. i will be quieter about it.",
         "# TODO: practise more."]),
    _rival(
        "kilo", "KILO", 1050, "#ff8c42", "brute",
        "Dock loader from the flooded port. Codes like he lifts: slow, steady, everything "
        "checked twice. Has never shipped a bug he didn't later fix.",
        ["Lift with your legs, code with your head. Let's haul.",
         "I'm not fast. I'm just never wrong twice.",
         "Every test's a crate. We stack 'em one at a time."],
        ["Slow and steady still gets the crate on the ship, runner.",
         "You sprinted and dropped the load. I walked and delivered.",
         "Check your edges. Empty list's a crate too."],
        ["Hah! Clean lift. Didn't even scratch the paint.",
         "You move freight like you were born on the docks.",
         "Alright. Buy you a ration bar. Next time I'm hauling faster."]),
    _rival(
        "lark", "LARK", 1150, "#ffd166", "novice",
        "A Monastery novice two seasons ahead of you. Earnest, polite, quotes the Order's "
        "sayings at the worst possible moments.",
        ["The Order says: read the whole error before you touch the code. Good luck, {callsign}.",
         "May your tests be honest and your loops terminate.",
         "I've been practising since dawn rites. Please don't go easy."],
        ["Thank you for the match. The Order says losing is just a slower kind of learning.",
         "Your logic was sound. Your edge cases weren't. That's the whole difference.",
         "I'll light a shrine LED for your next run. Truly."],
        ["Oh. Oh, that was beautiful. May I read your solution afterwards?",
         "The student becomes... well. A faster student. Well run.",
         "I'll tell the Abbot. She'll be insufferable about it."]),
    _rival(
        "sable", "SABLE", 1260, "#7b61ff", "corporate",
        "Former senior sysadmin for a megacorp that no longer exists. Still dresses for "
        "the quarterly review. Still thinks you're an intern.",
        ["Let's keep this brief. I have a standing meeting with nobody at three.",
         "Per my previous message: you are going to lose.",
         "I've reviewed your commit history. It was a short review."],
        ["As expected. I'll circulate the minutes.",
         "Don't take it personally. Take it as feedback.",
         "Ten years of uptime, {callsign}. You can't speedrun experience."],
        ["Interesting. Let's take this offline.",
         "I'll be escalating this. To myself. Privately.",
         "Fine. Your performance has been noted for the review cycle."]),
    _rival(
        "tin-saint", "TIN SAINT", 1360, "#c8a96a", "zealot",
        "A cyborg monk who recites PEP 8 like scripture and believes readable code is a "
        "form of prayer. Terrifying with a list comprehension.",
        ["Beautiful is better than ugly. Explicit is better than implicit. Begin.",
         "Four spaces, child. Never tabs. Never.",
         "Let us see whether your code is fit to be read by others."],
        ["Simple is better than complex. You chose complex.",
         "Errors should never pass silently. Yours screamed.",
         "Go in peace. Name your variables better."],
        ["Readability counts. Yours did. I yield.",
         "There should be one obvious way to do it. You found it first.",
         "A clean solution. I will meditate on my defeat."]),
    _rival(
        "hexa", "THE HEX TWINS", 1480, "#00ffa3", "pair",
        "Two runners, one rig. They pair-program in a shared visor and finish each "
        "other's functions. Nobody knows which one is typing.",
        ["We'll take the first half. We'll take the second half. Ready?",
         "Two heads, one keyboard, zero mercy.",
         "We already agreed on the variable names. Did you?"],
        ["We win. We always win. Well. We usually win.",
         "Next time bring a partner. Or a rubber duck.",
         "She found the bug. No, I found the bug. We found the bug."],
        ["We lost? We lost. Whose fault was that? ...Yours. No, yours.",
         "Respect from both of us. Mostly from her.",
         "Pair programming beaten by one runner. That stings twice."]),
    _rival(
        "rook", "ROOK", 1590, "#4cc9f0", "tactician",
        "Former logistics planner who treats every drill like an endgame. Reads the whole "
        "board before moving a single piece.",
        ["Every problem is a position. Let's see how you play this one.",
         "I've already planned my first twelve moves. How many have you planned?",
         "The opening matters less than people think. Begin."],
        ["Checkmate. You attacked before you understood the position.",
         "You played fast. I played correct. Correct won.",
         "Plan your data structure, {callsign}. The rest follows."],
        ["A clean sacrifice. I didn't see it coming.",
         "You out-calculated me. That doesn't happen often.",
         "Good game. I'll study this one."]),
    _rival(
        "mirage", "MIRAGE", 1720, "#e0aaff", "trickster",
        "Illusionist of the night markets. Loves elegant one-liners, misdirection, and "
        "making hard problems look effortless. Usually it is an act.",
        ["Watch closely. Nothing up my sleeve but a generator expression.",
         "The trick is making it look easy. The secret is it's never easy.",
         "Pick a test. Any test. I've already passed it."],
        ["And for my final trick: I'm done. You're not.",
         "You were watching my hands. You should've watched your loop bounds.",
         "Applause is optional. Debugging isn't."],
        ["Ah. You saw through it. Nobody sees through it.",
         "The illusion breaks. Well played, {callsign}.",
         "Even magicians lose a card sometimes. Take a bow."]),
    _rival(
        "deadlock", "DEADLOCK", 1880, "#ff5f1f", "enforcer",
        "A Core enforcement daemon that defected after the Null Event. Gravel voice, no "
        "patience, and an instinct for the exact line that will fail.",
        ["Acquiring lock. You won't get it back.",
         "I used to delete runners like you. Now I just beat them.",
         "Two processes, one resource. Only one of us finishes."],
        ["Contention resolved. In my favour.",
         "You waited on yourself, {callsign}. Classic deadlock.",
         "Go home. Review your exceptions. Come back hungrier."],
        ["...Lock released. You earned it.",
         "Fast. Clean. The Core would have flagged you as a threat.",
         "Hm. Maybe defecting was the right call. Runners like you exist."]),
    _rival(
        "vex", "VEX", 2150, "#ff2bd6", "ace",
        "The Grid's fastest courier turned the Arena's queen. Cocky, loud, and number two "
        "on the ladder. She hates that number almost as much as she hates losing.",
        ["Oh, it's you. Try to keep up this time, {callsign}.",
         "Clock's running, rookie. Mine's already halfway done.",
         "Grudge match? Love it. Let's make it quick, I've got a reputation.",
         "Same drill, same seed. Only difference is who's better. Spoiler: me."],
        ["Too slow! Again! You're fun, you know that? Like a training dummy with opinions.",
         "Close. Closer than last time. Don't let it go to your head.",
         "Read your traceback, then come find me. I'll be at the top. Well. Near it.",
         "That's how it's done. Watch the replay. Take notes."],
        ["...Okay. Okay! Lucky seed. Rematch. Now.",
         "Fine. FINE. That was actually clean. Don't make me say it twice.",
         "Who taught you to write loops like that? ...Never mind. Don't answer.",
         "You beat me. Enjoy it. I'm going to be insufferable about the rematch."]),
    _rival(
        "oracle-proxy", "ORACLE PROXY", 2300, "#d7263d", "proxy",
        "A shard of the Core's voice that sits atop the ladder and plays every runner who "
        "climbs this high. Unfailingly polite. Has never been seen to hurry.",
        ["Welcome, {callsign}. I have been looking forward to measuring you.",
         "Please, take all the time you need. I will not need much.",
         "Same inputs. Same expected outputs. Let us see which of us generalises."],
        ["Thank you. Your effort has been recorded and found insufficient.",
         "A respectable result. For a human. Please try again.",
         "You optimised for speed. I optimised for you."],
        ["Fascinating. You were not supposed to be able to do that.",
         "I will update my model of you. That is the highest compliment I can offer.",
         "Well played. The Core is listening now."]),
)

RIVAL_BY_ID: dict[str, dict] = {r["id"]: r for r in RIVALS}


# ── reading the save safely ──────────────────────────────────────────────────────────

def _num(value, default: float = 0) -> float:
    """A real number from save data, or `default` for anything else (None, "x", True...)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return default
    return value


def _arena(save) -> dict:
    """The save's arena dict for reading (never modified; `{}` for old saves)."""
    data = getattr(save, "arena", None)
    return data if isinstance(data, dict) else {}


def _arena_rw(save) -> dict:
    """The save's arena dict for writing: created and repaired if missing or broken."""
    data = getattr(save, "arena", None)
    if not isinstance(data, dict):
        data = {}
        save.arena = data
    return data


def rating_of(save) -> int:
    """The player's current rating (800 before the first match)."""
    return int(_num(_arena(save).get("rating"), START_RATING))


def peak_of(save) -> int:
    """The best rating ever reached. Never lower than the current rating."""
    data = _arena(save)
    return int(max(_num(data.get("peak"), START_RATING), rating_of(save)))


def matches_of(save) -> int:
    return int(max(0, _num(_arena(save).get("matches"), 0)))


def history_of(save) -> list[dict]:
    """Stored match history, oldest first, keeping only well-formed entries."""
    history = _arena(save).get("history")
    return [h for h in history if isinstance(h, dict)] if isinstance(history, list) else []


def record_vs(save, rival_id: str) -> dict:
    """Your {wins, losses} against one rival."""
    records = _arena(save).get("records")
    rec = records.get(rival_id) if isinstance(records, dict) else None
    rec = rec if isinstance(rec, dict) else {}
    return {"wins": int(_num(rec.get("wins"), 0)), "losses": int(_num(rec.get("losses"), 0))}


def last_rival(save) -> str | None:
    """The id of the rival you played most recently, if any."""
    history = history_of(save)
    return history[-1].get("rival") if history else None


# ── divisions ────────────────────────────────────────────────────────────────────────

def division(rating: float) -> str:
    """The division name for a rating: BRONZE below 1000 ... BLACK ICE from 2000."""
    name = DIVISIONS[0][0]
    for div_name, minimum in DIVISIONS:
        if rating >= minimum:
            name = div_name
    return name


def division_index(name_or_rating) -> int:
    """0 for BRONZE ... 6 for BLACK ICE. Accepts a division name or a rating."""
    name = division(name_or_rating) if isinstance(name_or_rating, (int, float)) else name_or_rating
    for i, (div_name, _) in enumerate(DIVISIONS):
        if div_name == name:
            return i
    return 0


def next_division(rating: float) -> dict | None:
    """The next division up as ``{name, min}``, or None in BLACK ICE."""
    i = division_index(division(rating))
    if i + 1 >= len(DIVISIONS):
        return None
    name, minimum = DIVISIONS[i + 1]
    return {"name": name, "min": minimum}


def division_tiers(name: str) -> tuple[int, ...]:
    """Drill tiers raced in a division (unknown names race tier 1-2, like BRONZE)."""
    return DIVISION_TIERS.get(name, DIVISION_TIERS["BRONZE"])


# ── Elo ──────────────────────────────────────────────────────────────────────────────

def expected_score(you: float, rival: float) -> float:
    """Elo's prediction of your chance to win: E = 1 / (1 + 10^((R_rival - R_you) / 400)).

    Equal ratings give 0.5. A rival 400 points above you gives about 0.09.
    """
    return 1.0 / (1.0 + 10 ** ((rival - you) / 400.0))


def k_factor(matches_played: int) -> int:
    """48 for your first 10 matches, then 32."""
    return K_NEW if matches_played < PLACEMENT_MATCHES else K_SETTLED


def rating_change(you: float, rival: float, won: bool, matches_played: int) -> int:
    """How many points you gain (positive) or lose (negative) from one result.

    delta = round(K x (score - expected)), where score is 1 for a win and 0 for a loss.
    Beating a stronger rival pays more; losing to a weaker one costs more.
    """
    score = 1.0 if won else 0.0
    return int(round(k_factor(matches_played) * (score - expected_score(you, rival))))


# ── matchmaking ──────────────────────────────────────────────────────────────────────

def rival(rival_id: str) -> dict:
    """A rival by id. Raises ArenaError(404) for unknown ids."""
    try:
        return RIVAL_BY_ID[rival_id]
    except (KeyError, TypeError):
        raise ArenaError(404, f"No rival called {rival_id!r} on the ladder.", "unknown_rival") from None


def suggested_rival(save) -> dict:
    """The default opponent: the closest-rated rival you didn't *just* play.

    Ties go to the higher-rated rival (always lean towards a challenge).
    """
    you = rating_of(save)
    previous = last_rival(save)
    pool = [r for r in RIVALS if r["id"] != previous] or list(RIVALS)
    return min(pool, key=lambda r: (abs(r["rating"] - you), -r["rating"]))


def challenge_status(save, rival_id: str) -> tuple[bool, str]:
    """May the player challenge this rival right now? Returns (allowed, reason).

    Allowed within +-300 rating, and VEX is always allowed as a grudge match.
    The reason is "" when allowed.
    """
    target = rival(rival_id)
    if target["id"] == GRUDGE_RIVAL:
        return True, ""
    gap = target["rating"] - rating_of(save)
    if abs(gap) <= CHALLENGE_RANGE:
        return True, ""
    if gap > 0:
        return False, f"{target['name']} won't race you yet: climb to {target['rating'] - CHALLENGE_RANGE}."
    return False, f"{target['name']} is beneath your rating now: no glory in that race."


def is_grudge(save, rival_id: str) -> bool:
    """A VEX challenge from outside the normal +-300 window is a grudge match."""
    return rival_id == GRUDGE_RIVAL and abs(RIVAL_BY_ID[GRUDGE_RIVAL]["rating"] - rating_of(save)) > CHALLENGE_RANGE


def choose_rival(save, rival_id: str | None = None) -> dict:
    """Resolve who you fight: the suggested rival when `rival_id` is empty, else check the challenge.

    Raises ArenaError(404) for an unknown rival and ArenaError(403) for one out of range.
    """
    if not rival_id:
        return suggested_rival(save)
    allowed, reason = challenge_status(save, rival_id)
    if not allowed:
        raise ArenaError(403, reason, "out_of_range")
    return rival(rival_id)


def choose_drill(division_name: str, rng: random.Random, drills: Iterable | None = None):
    """Pick the match drill and its seed: ``(drill, seed)``.

    The tier comes from the division (BRONZE races tier 1-2, ... BLACK ICE tier 5), the
    drill is a seeded choice among registered drills of that tier, and the seed is a fresh
    random number below 2**24 so it fits a challenge code. If no drill of the wanted tiers
    is registered yet, the nearest tier that has drills is used instead.

    `drills` defaults to ``engine.drills.all_drills()``; tests pass a small list.
    Raises ArenaError(503) if there are no drills at all.
    """
    if drills is None:
        from engine.drills import all_drills   # imported lazily: keeps this module light
        drills = all_drills()
    pool = sorted(drills, key=lambda d: (d.tier, d.id))
    if not pool:
        raise ArenaError(503, "No drills are installed, so the Arena is closed.", "no_drills")
    tiers = division_tiers(division_name)
    tier = rng.choice(tiers)
    available = sorted({d.tier for d in pool})
    if tier not in available:
        tier = min(available, key=lambda t: (abs(t - tier), t))
    candidates = [d for d in pool if d.tier == tier]
    drill = rng.choice(candidates)
    seed = rng.randrange(1, SEED_LIMIT)
    return drill, seed


# ── the adaptive rival clock ─────────────────────────────────────────────────────────

def pace(save) -> float:
    """Your typical speed: the median of seconds/par over recent clears (1.6 with no data).

    1.0 means you finish right on par; 0.5 means twice as fast as par.
    """
    samples = _arena(save).get("pace_samples")
    values = [float(v) for v in samples if _num(v, -1) > 0] if isinstance(samples, list) else []
    return round(statistics.median(values), 4) if values else DEFAULT_PACE


def record_pace(save, seconds: float, par: float) -> float | None:
    """Remember one clear's seconds/par for the pace median. Returns the sample (or None).

    Call this for every successful clear in practice, contract and ghost runs; ``resolve``
    records arena wins itself. Each sample is clamped to [0.1, 10] and only the newest
    20 are kept. Bad input (no par, negative time) is ignored.
    """
    seconds, par = _num(seconds, -1), _num(par, 0)
    if seconds < 0 or par <= 0:
        return None
    low, high = PACE_SAMPLE_RANGE
    sample = round(min(high, max(low, seconds / par)), 4)
    data = _arena_rw(save)
    samples = data.get("pace_samples")
    samples = [v for v in samples if _num(v, -1) > 0] if isinstance(samples, list) else []
    samples.append(sample)
    data["pace_samples"] = samples[-PACE_LIMIT:]
    return sample


def rival_eta(save, rival_id: str, par: float, rng: random.Random) -> float:
    """Seconds the rival will need for this match (sampled once, at match start).

        base = par x pace
        eta  = base x 10^((R_you - R_rival) / 1000) x lognormal(0, 0.22)
        eta  is clamped to [0.35, 3] x base

    A stronger rival (higher rating) finishes sooner; a weaker one later. Because ``base``
    uses YOUR measured pace, your chance of winning tracks the Elo expectation whatever
    your real speed is, so every match is close. Returns seconds rounded to 0.1.
    """
    target = rival(rival_id)
    base = max(1.0, _num(par, 0)) * pace(save)
    skill = 10 ** ((rating_of(save) - target["rating"]) / 1000.0)
    luck = rng.lognormvariate(0.0, ETA_SPREAD)
    low, high = ETA_CLAMP
    eta = min(high * base, max(low * base, base * skill * luck))
    return round(eta, 1)


def run_rival(rival_id: str, save, eta_seconds: float) -> dict:
    """The ``Run.rival`` block (§7) for a live match."""
    target = rival(rival_id)
    return {"id": target["id"], "name": target["name"], "rating": target["rating"],
            "division": division(target["rating"]), "color": target["color"],
            "eta_seconds": eta_seconds, "grudge": is_grudge(save, rival_id),
            "lines": {k: list(v) for k, v in target["lines"].items()}}


# ── results ──────────────────────────────────────────────────────────────────────────

def resolve(save, rival_id: str, won: bool, seconds: float | None, par: float,
            drill, now: float | None = None) -> dict:
    """Apply one finished match to the save and return the §7 rating block.

    Updates rating (Elo, never below 100), peak, wins/losses, win streak, match count,
    your record against this rival, and the history (newest 20 kept). A win also adds a
    pace sample (seconds / par). A loss or forfeit is ``won=False``; `seconds` may then be
    None. `drill` is a drill id or any object with an ``id``. `now` is the epoch time to
    stamp on the history entry (this module never reads the clock itself).

    Returns ``{before, after, delta, division_before, division_after, promoted}``.
    """
    target = rival(rival_id)
    data = _arena_rw(save)
    before = rating_of(save)
    played = matches_of(save)
    delta = rating_change(before, target["rating"], bool(won), played)
    after = max(RATING_FLOOR, before + delta)
    delta = after - before

    wins = int(_num(data.get("wins"), 0)) + (1 if won else 0)
    losses = int(_num(data.get("losses"), 0)) + (0 if won else 1)
    streak = int(max(0, _num(data.get("streak"), 0))) + 1 if won else 0
    data.update(rating=after, peak=max(peak_of(save), after), wins=wins, losses=losses,
                streak=streak, matches=played + 1)

    records = data.get("records")
    if not isinstance(records, dict):
        records = data["records"] = {}
    rec = record_vs(save, rival_id)
    rec["wins" if won else "losses"] += 1
    records[rival_id] = rec

    drill_id = getattr(drill, "id", drill)
    secs = None if seconds is None else round(max(0.0, _num(seconds, 0)), 1)
    history = history_of(save)
    history.append({"rival": rival_id, "result": "won" if won else "lost", "delta": delta,
                    "drill": drill_id if isinstance(drill_id, str) else None,
                    "seconds": secs, "at": now})
    data["history"] = history[-HISTORY_LIMIT:]

    if won and secs is not None:
        record_pace(save, secs, par)

    div_before, div_after = division(before), division(after)
    return {"before": before, "after": after, "delta": delta,
            "division_before": div_before, "division_after": div_after,
            "promoted": division_index(div_after) > division_index(div_before)}


# ── payloads ─────────────────────────────────────────────────────────────────────────

def profile(save) -> dict:
    """``Arena.profile`` (§7). ``next_division`` is ``{name, min}`` or None at the top."""
    data = _arena(save)
    rating = rating_of(save)
    return {"rating": rating, "peak": peak_of(save), "division": division(rating),
            "next_division": next_division(rating),
            "wins": int(_num(data.get("wins"), 0)), "losses": int(_num(data.get("losses"), 0)),
            "streak": int(max(0, _num(data.get("streak"), 0))), "matches": matches_of(save),
            "pace": pace(save)}


def payload(save) -> dict:
    """The ``GET /api/arena`` body (§7 ``Arena``).

    Rivals are listed top of the ladder first. Besides the contract fields each rival
    carries ``style``, ``challengeable`` (+ ``locked_reason``), ``grudge`` and
    ``suggested`` for the matchmaking UI. History is newest first.
    """
    suggested = suggested_rival(save)["id"]
    rivals = []
    for r in sorted(RIVALS, key=lambda r: -r["rating"]):
        allowed, reason = challenge_status(save, r["id"])
        rivals.append({"id": r["id"], "name": r["name"], "rating": r["rating"],
                       "division": division(r["rating"]), "color": r["color"], "bio": r["bio"],
                       "style": r["style"], "record": record_vs(save, r["id"]),
                       "challengeable": allowed, "locked_reason": reason or None,
                       "grudge": is_grudge(save, r["id"]), "suggested": r["id"] == suggested})
    history = []
    for h in reversed(history_of(save)):
        meta = RIVAL_BY_ID.get(h.get("rival"), {})
        history.append({"rival": h.get("rival"), "rival_name": meta.get("name", "UNKNOWN"),
                        "color": meta.get("color", "#888888"), "result": h.get("result"),
                        "delta": h.get("delta", 0), "drill": h.get("drill"),
                        "seconds": h.get("seconds"), "at": h.get("at")})
    return {"profile": profile(save),
            "divisions": [{"name": n, "min": m} for n, m in DIVISIONS],
            "rivals": rivals, "suggested": suggested, "history": history}
