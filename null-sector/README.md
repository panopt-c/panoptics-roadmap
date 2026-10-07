# NULL//SECTOR

A cyberpunk survival RPG that teaches Python from zero to AI engineering.
You're an engineer trapped in a corrupted digital wasteland. You survive by writing real
`.py` files that break through enemy firewalls.

## Play

```bash
cd null-sector
pip install -r requirements.txt
python game.py
```

The fastest way to play is with two windows side by side:

```bash
python game.py watch     # every time you save your mission file, the game attacks
```

Open `missions/level_01_cold_boot.py` in your editor in the other window, write code, and save.

| Command | What it does |
|---|---|
| `python game.py` | Main menu: HUD, sector map, briefings |
| `python game.py watch` | Auto-attack each time you save |
| `python game.py hack` | Attack once |
| `python game.py reset` | Restore your mission file to its starter code |
| `--fast` | Skip animations |

## How a mission works

1. **Briefing:** the story, *why* the concept matters in real AI engineering, and a short field manual.
2. **Mission file:** a starter `.py` appears in `missions/`, with objectives written as comments.
3. **Hack:** the engine runs your file in a separate, sandboxed process, then checks your variables,
   output and code. Each passing check breaks one firewall layer.
4. **Victory:** you get XP (plus a speed bonus if you beat the par time), rank up, and unlock a cutscene.

If your code crashes, the **COMBAT LOG** shows the line that broke, Python's raw error, and a
plain-English translation.

## Higgsfield cutscenes (optional)

1. Create an API key at [cloud.higgsfield.ai](https://cloud.higgsfield.ai).
2. Run the game once so it creates `config.json`, then paste your key and secret into it.
   (Or set the `HF_KEY="key:secret"` environment variable.)
3. Change `avatar.description` so the character looks like you.

`config.json` is git-ignored, so your key can't be pushed to this public repo by accident.

Level 1's cutscene renders your **anchor avatar**. Every later cutscene sends that image as a
reference, so it's the same character in every scene. Set `"video_enabled": true` to animate each
still with a camera move. Model ids and argument names live in `config.json`. If Higgsfield rejects
a call, the game prints the error and continues with the terminal cutscene, so you never lose progress.

## Layout

```
game.py              entry point: menus, combat loop, rewards
engine/
  state.py           config.json + save.json, XP and ranks
  mission.py         Mission / Check / Fail: the level-building toolkit
  harness.py         grades your file inside an isolated subprocess
  runner.py          launches the harness with a timeout (catches infinite loops)
  errors.py          Python error -> plain English
  ui.py              Rich HUD, sector map, battle animation, transmissions
  cinematics.py      Higgsfield cutscenes with character consistency
levels/
  __init__.py        the 25-level campaign map
  level_01_*.py      one file per level: story, lesson, starter code, checks
missions/            YOUR code lives here
cutscenes/           generated images and videos
```
