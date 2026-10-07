"""Cutscenes. The terminal version always plays; Higgsfield renders the visual one when connected.

How character consistency works:
  1. Every prompt carries the same CHARACTER BIBLE (your avatar description from
     config.json) and the same STYLE BIBLE, so the model draws the same person in
     the same world every time.
  2. Level 1's cutscene is the *anchor*: its image becomes your official avatar.
     Every later scene passes that image as a reference, locking your face in.
  3. With video enabled, each still is animated by an image-to-video model, with
     the scene's camera move (dolly-in, crane up, orbit...) in the prompt.

Model ids and argument names live in config.json so you can swap models from the
Higgsfield dashboard without touching code.
"""
from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from rich.console import Console

from engine import ui
from engine.mission import Cutscene
from engine.state import CUTSCENE_DIR, Save

STYLE_BIBLE = ("cinematic film still, gritty cyberpunk wasteland, ruins of corrupted data centers, "
               "acid rain, neon cyan and magenta rim light, volumetric haze, anamorphic 35mm lens, "
               "film grain, ultra detailed")
PLACEHOLDER_PREFIX = "PASTE_"


class Director:
    def __init__(self, console: Console, config: dict, save: Save):
        self.console = console
        self.cfg = config["higgsfield"]
        self.avatar = config["avatar"]["description"]
        self.ui_cfg = config["ui"]
        self.save = save

    # ── connection ──────────────────────────────────────────
    def _credentials(self) -> str | None:
        """Env vars win over config.json (HF_KEY, or HF_API_KEY + HF_API_SECRET)."""
        if os.getenv("HF_KEY"):
            return os.environ["HF_KEY"]
        key = os.getenv("HF_API_KEY") or self.cfg.get("api_key", "")
        secret = os.getenv("HF_API_SECRET") or self.cfg.get("api_secret", "")
        if not key or not secret or key.startswith(PLACEHOLDER_PREFIX) or secret.startswith(PLACEHOLDER_PREFIX):
            return None
        return f"{key}:{secret}"

    def status(self) -> tuple[bool, str]:
        try:
            import higgsfield_client  # noqa: F401
        except ImportError:
            return False, "higgsfield-client not installed (pip install -r requirements.txt)"
        if not self._credentials():
            return False, "no API key in config.json"
        return True, "online"

    # ── the show ────────────────────────────────────────────
    def play(self, cutscene: Cutscene, mission_id: str) -> None:
        animate = self.ui_cfg["animations"]
        ui.transmission(self.console, cutscene, animate, self.ui_cfg["typing_speed"])
        online, reason = self.status()
        if not online:
            self.console.print(f"  [muted]◌ visual feed offline — {reason}[/]\n")
            return
        try:
            with self.console.status("[pink]Rendering memory fragment via Higgsfield…[/]", spinner="dots12"):
                still_url = self._render_still(cutscene)
            still_path = self._download(still_url, f"{mission_id}_still")
            if cutscene.anchor:
                self.save.avatar_url = still_url
            self._record(mission_id, cutscene.title, still_url, still_path)
            self.console.print(f"  [ok]◉ MEMORY FRAGMENT SAVED[/] [steel]{_short(still_path) or still_url}[/]")
            final = still_path

            if self.cfg.get("video_enabled"):
                with self.console.status(f"[pink]Animating scene — camera: {cutscene.camera}…[/]",
                                         spinner="dots12"):
                    video_url = self._render_video(cutscene, still_url)
                video_path = self._download(video_url, f"{mission_id}_cinematic")
                self._record(mission_id, f"{cutscene.title} (cinematic)", video_url, video_path)
                self.console.print(f"  [ok]◉ CINEMATIC SAVED[/] [steel]{_short(video_path) or video_url}[/]")
                final = video_path or final
            if final and self.cfg.get("auto_open"):
                webbrowser.open(Path(final).resolve().as_uri())
        except KeyboardInterrupt:
            self.console.print("  [muted]◌ render skipped[/]")
        except Exception as exc:  # noqa: BLE001 — a failed render must never cost you a level
            self.console.print(f"  [bad]◌ SIGNAL LOST[/] [steel]{type(exc).__name__}: {exc}[/]")
            self.console.print("  [muted]Check model ids / argument names in config.json against the "
                               "model page on cloud.higgsfield.ai[/]")
        finally:
            self.save.write()
        self.console.print()

    # ── Higgsfield calls ────────────────────────────────────
    def _client(self):
        import higgsfield_client
        return higgsfield_client.SyncClient(api_key=self._credentials())

    def _prompt(self, cutscene: Cutscene, motion: bool = False) -> str:
        parts = [cutscene.shot, f"The hero: {self.avatar}", STYLE_BIBLE]
        if motion and cutscene.camera:
            parts.insert(1, f"Camera: {cutscene.camera}")
        return ". ".join(parts)

    def _render_still(self, cutscene: Cutscene) -> str:
        client = self._client()
        args = {"prompt": self._prompt(cutscene), **self.cfg.get("image_arguments", {})}
        ref_key = self.cfg.get("reference_argument")
        if self.save.avatar_url and ref_key and not cutscene.anchor:
            try:
                return _first_url(client.subscribe(self.cfg["image_model"], {**args, ref_key: self.save.avatar_url}))
            except Exception as exc:  # noqa: BLE001
                self.console.print(f"  [warn]reference image rejected ({exc}); rendering from the character "
                                   "bible alone[/]")
        return _first_url(client.subscribe(self.cfg["image_model"], args))

    def _render_video(self, cutscene: Cutscene, still_url: str) -> str:
        args = {"prompt": self._prompt(cutscene, motion=True),
                self.cfg["video_image_argument"]: still_url,
                **self.cfg.get("video_arguments", {})}
        return _first_url(self._client().subscribe(self.cfg["video_model"], args))

    # ── files ───────────────────────────────────────────────
    def _download(self, url: str, stem: str) -> str | None:
        import httpx  # installed alongside higgsfield-client
        try:
            ext = Path(urlparse(url).path).suffix or ".bin"
            path = CUTSCENE_DIR / f"{stem}{ext}"
            CUTSCENE_DIR.mkdir(exist_ok=True)
            resp = httpx.get(url, follow_redirects=True, timeout=120)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            return str(path)
        except Exception:  # noqa: BLE001 — the URL is still recorded, so nothing is lost
            return None

    def _record(self, mission_id: str, title: str, url: str, path: str | None) -> None:
        self.save.gallery.append({"mission": mission_id, "title": title, "url": url, "path": path})


def _first_url(result) -> str:
    """Find the media URL in a Higgsfield result, e.g. result['images'][0]['url']."""
    if isinstance(result, str) and result.startswith("http"):
        return result
    if isinstance(result, dict):
        for key in ("images", "image", "video", "videos", "url", "output", "outputs", "result"):
            if key in result:
                try:
                    return _first_url(result[key])
                except ValueError:
                    pass
        for value in result.values():
            try:
                return _first_url(value)
            except ValueError:
                pass
    if isinstance(result, list):
        for item in result:
            try:
                return _first_url(item)
            except ValueError:
                pass
    raise ValueError(f"no media URL in Higgsfield response: {str(result)[:200]}")


def _short(path: str | None) -> str | None:
    return str(Path(path).relative_to(CUTSCENE_DIR.parent)) if path else None
