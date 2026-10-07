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

This starts a small local server and opens the game in your browser at `http://127.0.0.1:7777`
(if that port is busy, the next free one is used, and the terminal shows the link). Press
`Ctrl+C` in the terminal to quit. Your progress is saved automatically.

| Key | What it does |
|---|---|
| `Ctrl+Enter` (`⌘+Enter` on macOS) | **Hack**: run your code against the enemy's firewall |
| `Ctrl+S` (`⌘+S`) | Save your mission file |
| `Esc` | Settings: volume, screen shake, CRT effects, graphics quality |

Write code in the in-game editor (it also saves as you type), or open `missions/level_01_cold_boot.py`
in your own editor: every save shows up in the browser instantly. If the in-game editor has unsaved
changes at that moment, the game asks which version to keep.

### Commands

| Command | What it does |
|---|---|
| `python game.py` | Play in the browser (default) |
| `python game.py --port 8000` | Use another port |
| `python game.py --no-browser` | Start the server without opening a tab |
| `python game.py tui` | Play the original terminal version |
| `python game.py watch` | Terminal: attack every time you save your mission file |
| `python game.py hack` | Terminal: attack once |
| `python game.py reset` | Restore your mission file to its starter code |
| `--fast` | Skip terminal animations |

Both versions share one save file, so you can switch between them at any time.

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
still with a camera move. Model ids and argument names live in `config.json`.

In the browser, rendering starts the moment you win, while you read the reward screen. Without a key,
or if Higgsfield rejects a call, you get the in-engine cutscene instead, so you never lose progress.
Rendered media is saved in `cutscenes/`.

## Security

The game server runs your code, so it only listens on `127.0.0.1`, ignores requests addressed to any
other host name, and requires a secret token (new on every launch) for every API call. Other websites
open in your browser can't use it.

## Layout

```
game.py              command line: browser (default) | tui | hack | watch | reset
engine/
  session.py         GameSession: every game rule (attempts, par timer, XP, ranks, unlocks)
  server.py          local web server: the client, a JSON API and live events
  content.py         mission markdown -> HTML with highlighted Python
  tui.py, ui.py      the Rich terminal version
  state.py           config.json + save.json
  mission.py         Mission / Check / Fail: the level-building toolkit
  harness.py         grades your file inside an isolated subprocess
  runner.py          launches the harness with a timeout (catches infinite loops)
  errors.py          Python error -> plain English
  cinematics.py      Higgsfield cutscenes with character consistency
levels/
  __init__.py        the 25-level campaign map
  level_01_*.py      one file per level: story, lesson, starter code, checks
client/              the browser game (WebGL2, plain JavaScript modules, no build step)
missions/            YOUR code lives here
cutscenes/           generated images and videos
tests/               python -m unittest discover -s tests
docs/ARCHITECTURE.md how it all fits together
```
