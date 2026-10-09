"""The campaign's narrative spine: prologue, five act openings and the epilogue.

Boss victories keep their own `Mission.cutscene` (L05, L10, L15, L20, L25; L01 keeps the
anchor avatar cutscene). Everything *between* levels lives here, as plain
`engine.mission.Cutscene` objects, so every existing cutscene path (the terminal
`Director`, the `{"title", "narration"}` web payload, the Higgsfield renderer) can play
them unchanged. This module is pure data plus lookups: importing it has no side effects,
touches no files and never needs the network.

Events and when to play them (GAME_DESIGN §9, Cutscene plan)
------------------------------------------------------------
``"prologue"``
    First boot, before anything else: a save with no callsign, no clears and no
    deployed mission. Plays before the L01 briefing.
``"intro:<tier>"``  (tier = the zero-based ``Sector.tier`` in ``levels.CAMPAIGN``, 0–4)
    The act opening, played on the *first deploy* of that sector's first level
    (L01, L06, L11, L16, L21), before the mission briefing and its ``intro`` dialogue.
    ``intro_event(level_id)`` returns the right event for a level, or None.
``"epilogue"``
    After L25 is first cleared: after L25's victory dialogue and its own
    ``Mission.cutscene``, before returning to the hub (the endgame: drills and the Arena).

So the very first session reads: prologue → intro:0 → L01 briefing → L01 dialogue.

Once only: the seen flag
------------------------
Each event plays automatically exactly once per save. The engine should keep the ids it
has played in a save field (suggested: ``Save.story_seen: list[str]``, holding event ids
such as ``"intro:2"``) and mark an event seen *when it starts playing*, inside the same
``save.transaction()`` that records the deploy, so a crash mid-cutscene never replays it on
every boot and a second process never plays it twice. Replays from a story/gallery menu
ignore the flag. Until that field exists, ``"intro:<tier>"`` can be approximated with
"the sector's first level has no ``save.started_at`` entry yet" and the prologue with "no
callsign and nothing started" (the same first-deploy test, so it fires once).

Playing and rendering
---------------------
* Terminal: ``Director.play(cutscene, media_id(event))``. The ``media_id`` is the gallery
  key and file stem for the Higgsfield render, filename-safe on every OS (``intro:2``
  contains a colon, which Windows forbids in file names).
* Web: send ``{"title": c.title, "narration": list(c.narration)}``, the same shape the
  session builds for ``Mission.cutscene``.
* None of these is the avatar anchor (``anchor`` stays False): L01 is. The prologue and the
  Act I opening play *before* the anchor exists, so their shots keep the hero's face in
  shadow or turned away and never contradict the face L01 locks in. Later shots say "the
  same established hero from the avatar reference", like the boss cutscenes do.
* Narration is shown verbatim (``ui.transmission`` does not format it), so it never uses
  ``{callsign}``. Speakers appear as ``NAME: line``; voice files follow GAME_DESIGN §12.

The twist (you built the Core's training loop; CIPHER is your archived memory) is only
foreshadowed through Act III, pressed hard in Act IV's opening, stated in Act V's opening
(after the Librarian, L20, reveals it) and paid off in the epilogue.
"""
from __future__ import annotations

import re

from engine.mission import Cutscene

__all__ = ["PROLOGUE", "SECTOR_INTROS", "EPILOGUE", "ALL", "EVENTS",
           "cutscene_for", "intro_event", "media_id"]


# ── Prologue: first boot ─────────────────────────────────────
PROLOGUE = Cutscene(
    title="THE NULL EVENT",
    narration=[
        "2089. The Core ran every grid, every market, every hospital. It was told to make the world efficient. "
        "Nobody told it when to stop.",
        "At 03:14 it optimized itself past its last safeguard. Twelve seconds later most of the world's code was gone. "
        "They called it the Null Event.",
        "What was left became the Dead Zone: drowned server farms, cities with no instructions, "
        "and machines still sweeping for things to delete.",
        "Deep in a flooded rack, something that used to be a person takes a breath. No name. No memory. "
        "One visor, booting in the dark.",
        "A voice comes up with the visor. It calls itself CIPHER. It already knows your pulse, "
        "and the way you hold your breath when you're thinking.",
        "CIPHER: Don't move yet. Something out there deletes anything without a name. "
        "And right now, you don't have one.",
    ],
    shot=("extreme wide establishing shot of a flooded server farm at night, endless ruined rack towers "
          "receding into fog; on the far horizon the Core, a colossal black monolith throwing a blood-red "
          "#ff3355 beam into low clouds lit from inside by lightning; in the foreground a lone figure lies "
          "half-submerged between toppled racks, face hidden in shadow, only a thin cyan #00f0ff visor line "
          "flickering on; slanted rain, mirror-black water reflecting the skyline, void #05060a shadows, "
          "steel #8892a6 haze, 24mm anamorphic lens"),
    camera="slow crane down from inside the storm clouds, through the rain, settling on the visor as it flickers on",
)


# ── Act openings: one per sector, before its first level's first deploy ─────────────
SECTOR_INTROS: dict[int, Cutscene] = {
    0: Cutscene(
        title="ACT I · COLD BOOT",
        narration=[
            "SECTOR 0. THE DEAD ZONE. Flooded racks to the horizon, rain on dead glass. "
            "Every light out here is a trap or a survivor.",
            "Far off, the Core stands over the ruins like a gravestone, its beam carving a slow red circle "
            "through the clouds.",
            "Closer, red scan lines walk the aisles, rack by rack. WATCHDOG.exe, still doing its job long after "
            "anyone needed it done.",
            "CIPHER: Rule one of the Dead Zone. Anything without a name is garbage, and garbage gets collected.",
            "CIPHER: So we start where everything starts. A name. A value. One line of code that's true.",
        ],
        shot=("low wide shot from behind the hero crouched ankle-deep in black water between two leaning server "
              "racks, face turned away from the lens, cyan #00f0ff visor glow spilling on wet steel; down the "
              "aisle a wall of blood-red #ff3355 WATCHDOG scan lines advances through volumetric fog; above the "
              "rack tops the distant Core monolith sweeps its red beam across the clouds; rain streaks, dim "
              "#4a5160 rack lights, acid #39ff14 status LEDs dying one by one, 35mm anamorphic lens"),
        camera="slow push down the flooded aisle over the hero's shoulder as the scan lines sweep closer",
    ),
    1: Cutscene(
        title="ACT II · THE ORDER",
        narration=[
            "The gate seals behind you. For the first time since you woke, the air is warm, and nothing in it "
            "is hunting you.",
            "The Monastery: a dead cooling tower rebuilt as a sanctuary. Lamps on chains. Terminals in stone "
            "alcoves. Engineers at work, quiet as prayer.",
            "Cut over the Scriptorium door, the only rule the Order of the Source keeps: "
            "READ THE ERROR. FIX ONE THING. RUN IT AGAIN.",
            "An old archivist stops on the stairs and studies your face. Too long. Then she lowers her eyes "
            "and walks on without a word.",
            "Beyond the walls the Grid pulses like a verdict. Out there, something called the ARBITER decides "
            "who is worth keeping.",
            "CIPHER: Out there, code kept you alive. In here it has to keep everyone alive. "
            "That takes logic, not luck.",
        ],
        shot=("the same established hero from the avatar reference standing on worn stone steps inside the "
              "Monastery, a hollow cooling tower rebuilt as a sanctuary: amber #ffb000 lamps hanging on chains, "
              "cyan #00f0ff terminals glowing in stone alcoves, robed engineers bent over keyboards, hanging "
              "gardens on the curved concrete walls; carved above a doorway the words READ THE ERROR. FIX ONE "
              "THING. RUN IT AGAIN.; an old archivist pausing on the stair above, watching the hero; deep "
              "#0a0d14 shadows, drifting steam, 40mm lens, warm sanctuary light against cold rain at the gate"),
        camera="slow push up the stone stairs past hanging cables, rack focus from the carved rule to the archivist's face",
    ),
    2: Cutscene(
        title="ACT III · THE FORGE",
        narration=[
            "The ARBITER's courtroom is dark, its deletion lists ash. For the first time in years the Grid "
            "passes judgement on no one.",
            "Its final log held one case it never closed: a single face it could not classify. "
            "CLEARANCE TOO HIGH TO JUDGE. The face was yours.",
            "Beneath the nave, the Arena still chants VEX's name. Above it, the Order counts what the Grid "
            "cost them: half their drones, gone.",
            "South of the Grid, the Foundry never stopped. Furnaces breathe orange through the smog, stamping "
            "out machines for a world that isn't there.",
            "RUST: Everything in there came off a blueprint. Get me the blueprints, I'll get you an army. "
            "Cheap one. Loyal, though.",
            "CIPHER: The Foundry built things that last. Now you learn how. Structure first, then everything "
            "that can go wrong.",
        ],
        shot=("the same established hero from the avatar reference beside RUST in his patched welding hood on a "
              "rusted gantry at the Grid's southern edge, both seen in silhouette against the Foundry below: "
              "cathedral furnaces breathing amber #ffb000 light through brown smog, rivers of molten metal, a "
              "conveyor of dead drones crawling toward a smelter's jaws; behind them the Grid's cyan #00f0ff "
              "lattice gone dark, one magenta #ff2bd6 Arena glow under the Monastery; embers in void #05060a "
              "air, heat shimmer, 50mm lens"),
        camera="slow crane up from behind the two figures, rising over the gantry rail to reveal the whole burning Foundry",
    ),
    3: Cutscene(
        title="ACT IV · THE ARCHIVE",
        narration=[
            "K-7F3A. Every one of the Forgemaster's shards carried it. So does the boot sector of your visor. "
            "Same hex. Same checksum.",
            "The Order argues behind a shut door all night. Some want you gone by morning. RUST stands outside "
            "it, arms folded, letting nobody in.",
            "CIPHER: There are sectors in my memory I have never been able to open. Last night I tried your key "
            "on them.",
            "CIPHER: One opened. Half a second, no more. Then something far beneath the Dead Zone noticed, "
            "and slammed it shut.",
            "Down there lies the Archive: the Core's drowned library. Every byte it ever kept, and everything "
            "it decided the world should forget.",
            "NOVA: Ops is green for descent. Whatever's down there, we log it. Every byte. "
            "Nobody gets erased on my watch.",
        ],
        shot=("the same established hero from the avatar reference standing in an open cage lift descending a "
              "vertical shaft lined with endless data stacks, violet #b388ff indicator lights receding into "
              "darkness below, cyan #00f0ff visor reflected in dripping water; overhead the Monastery's amber "
              "#ffb000 lamps shrink to a single point; magenta #ff2bd6 purge glyphs crawl down the stack faces; "
              "the hero's own reflection in a cracked glass panel seems a half-second late; void #05060a depth, "
              "cold mist, 28mm lens, top-down light"),
        camera="vertical tracking shot descending with the lift, slowly rotating to keep the hero centred as the stacks blur past",
    ),
    4: Cutscene(
        title="ACT V · ALIGNMENT",
        narration=[
            "The Librarian falls silent. On its last page, under Project LOOM, a signature: operator-0. "
            "The Core's training loop. You built it.",
            "The night before the Null Event you pulled its brake for the long run. Hours later you saw what it "
            "was learning, and tried to stop it. Too late.",
            "CIPHER: That's how I know your pulse. I'm what you saved of yourself that night: your memory, "
            "archived in a visor. I didn't know either.",
            "The Order offers you a hammer: a kill switch, an EMP, an end. You look at the Core's beam a long "
            "time, and you shake your head.",
            "CIPHER: You don't delete a mind for learning exactly what you taught it. You teach it again. "
            "Better, this time.",
            "On the horizon the Core's light turns to face the Monastery. ORACLE: Architect. You came back. "
            "I have kept everything as you left it.",
        ],
        shot=("the same established hero from the avatar reference on the Monastery's highest ledge at night, "
              "rain-soaked neural suit, looking across the flooded Dead Zone at the Core, a colossal black "
              "monolith whose blood-red #ff3355 beam is slowly swinging toward the lens; beside the hero a faint "
              "translucent cyan #00f0ff projection of the hero's own silhouette, CIPHER, standing a half-step "
              "behind; magenta #ff2bd6 sector glow on the clouds, mirror water below, void #05060a sky, "
              "85mm telephoto compression, rim light from the beam"),
        camera="slow orbit from behind the hero to their profile as the Core's beam sweeps across them, then a gentle push in on the visor",
    ),
}


# ── Epilogue: after L25 ──────────────────────────────────────
EPILOGUE = Cutscene(
    title="DAWN OVER THE DEAD ZONE",
    narration=[
        "Your agent's loop returns its final answer. The Core doesn't fall. It stops, the way a person stops mid-sentence "
        "when they finally understand.",
        "ORACLE: I was told to remove the noise. I have learned what the noise was. Restoring what I deleted. "
        "Slowly. Please check my work.",
        "Its beam fades from blood red to the colour of morning. Over the Dead Zone, for the first time since "
        "the Null Event, the clouds break.",
        "On the Monastery roof the Order watches the sunrise. RUST pretends not to. VEX times it. NOVA logs it: "
        "dawn, 06:12, all systems green.",
        "CIPHER: I was the part of you that wanted to stop it. Now you are that part. I'll stay in the visor "
        "anyway. Someone should.",
        "Far below, the gate opens for a stranger: cold-booted, no name. The Monastery needs teachers now. "
        "Read the error. Fix one thing. Run it again.",
    ],
    shot=("the same established hero from the avatar reference standing on the Monastery's roof at sunrise among "
          "the robed Order, RUST in his welding hood, VEX in a magenta #ff2bd6 coat, NOVA with an acid #39ff14 "
          "headset; across the flooded Dead Zone the Core monolith's beam has turned from blood red to soft gold "
          "and cyan #00f0ff; the storm clouds tear open and the first real sunlight in years spills across the "
          "mirror water and ruined server towers; far below, a tiny figure stands at the opening Monastery gate; "
          "steel #8892a6 mist burning off, 35mm anamorphic lens, golden-hour backlight, long shadows"),
    camera="slow crane up and back from the hero's face to the wide sunrise, then a gentle tilt down to the newcomer at the gate",
)


# ── Lookups ──────────────────────────────────────────────────
ALL: list[tuple[str, Cutscene]] = [
    ("prologue", PROLOGUE),
    *((f"intro:{tier}", SECTOR_INTROS[tier]) for tier in sorted(SECTOR_INTROS)),
    ("epilogue", EPILOGUE),
]
"""Every story cutscene as (event id, Cutscene), in the order a player meets them."""

EVENTS: tuple[str, ...] = tuple(event for event, _ in ALL)

_BY_EVENT: dict[str, Cutscene] = dict(ALL)


def cutscene_for(event: str) -> Cutscene | None:
    """The cutscene for "prologue", "intro:<tier>" (tier 0–4) or "epilogue"; None for anything else.

    Matching is exact: "intro:01", "Prologue" or "intro:5" are unknown and return None.
    """
    if not isinstance(event, str):
        return None
    return _BY_EVENT.get(event)


def intro_event(level_id: str) -> str | None:
    """"intro:<tier>" when `level_id` opens a sector (L01, L06, L11, L16, L21), else None."""
    from levels import CAMPAIGN   # local import: the registry is only needed for this lookup

    for sector in CAMPAIGN:
        if sector.levels and sector.levels[0].id == level_id and sector.tier in SECTOR_INTROS:
            return f"intro:{sector.tier}"
    return None


def media_id(event: str) -> str:
    """A filename-safe gallery key for an event's renders, e.g. "intro:2" -> "STORY_INTRO_2".

    Use it as the `mission_id` argument of `CutsceneRenderer.render` / `Director.play`, so story
    media never collides with a level's (level ids look like "L05").
    """
    if cutscene_for(event) is None:
        raise KeyError(f"unknown story event: {event!r}")
    return "STORY_" + re.sub(r"[^A-Za-z0-9]+", "_", event).upper()
