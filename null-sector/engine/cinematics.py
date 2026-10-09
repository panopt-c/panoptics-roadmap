"""Cutscenes: a headless Higgsfield renderer plus the Rich terminal Director that uses it.

`CutsceneRenderer` is pure pipeline — no printing, no UI — so the web server can
run it on a background worker while the TUI wraps it in spinners. `Director`
is the terminal presentation: typed transmission first, then the visual render.

How character consistency works:
  1. Every prompt carries the same CHARACTER BIBLE (your avatar description from
     config.json) and the same STYLE BIBLE, so the model draws the same person in
     the same world every time.
  2. Level 1's cutscene is the *anchor*: its image becomes your official avatar.
     Every later scene passes that image as a reference, locking your face in
     (and falls back to the bibles alone if the model rejects the reference).
  3. With video enabled, each still is animated by an image-to-video model, with
     the scene's camera move (dolly-in, crane up, orbit...) in the prompt.

Renders are resumable: a stage that already has a gallery entry is reused, so a
retry after a failed video never re-bills the still, and replays cost nothing.

Model ids and argument names live in config.json so you can swap models from the
Higgsfield dashboard without touching code.
"""
from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from rich.console import Console

from engine import ui
from engine.mission import Cutscene
from engine.state import CUTSCENE_DIR, Save

STYLE_BIBLE = ("cinematic film still, gritty cyberpunk wasteland, ruins of corrupted data centers, "
               "acid rain, neon cyan and magenta rim light, volumetric haze, anamorphic 35mm lens, "
               "film grain, ultra detailed")
PLACEHOLDER_PREFIX = "PASTE_"

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v"}
MEDIA_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", *VIDEO_EXTS}
CONTENT_TYPE_EXTS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
                     "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}

# on_progress(stage, state, entry=None, error=None)
#   stage: "still" | "video"
#   state: "rendering" | "done" | "failed" | "fallback" (reference rejected, retrying without it)
ProgressFn = Callable[..., None]

_SDK_STATUS: tuple[bool, str] | None = None   # the import probe is cached: it never changes mid-run


class CutsceneError(RuntimeError):
    """A render stage failed. Stages that finished before it are already in the gallery."""

    def __init__(self, stage: str, cause: BaseException):
        super().__init__(f"{type(cause).__name__}: {cause}")
        self.stage = stage
        self.cause = cause


def entry_kind(entry: dict) -> str:
    """'image' or 'video' for a gallery entry (older saves have no "kind" field)."""
    kind = entry.get("kind")
    if kind in ("image", "video"):
        return kind
    for ref in (entry.get("path") or "", entry.get("url") or ""):
        if Path(urlparse(ref).path).suffix.lower() in VIDEO_EXTS:
            return "video"
    return "video" if "(cinematic)" in (entry.get("title") or "") else "image"


class CutsceneRenderer:
    """Headless Higgsfield pipeline: still (anchor / reference) → optional video → local download.

    Mutations of the shared `Save` happen under `lock` (pass the GameSession's lock) as a
    locked read-modify-write of save.json (`Save.transaction()`), so a gallery entry never
    overwrites progress another process saved meanwhile. The slow network calls run outside it.
    """

    def __init__(self, config: dict, save: Save, cutscene_dir: Path = CUTSCENE_DIR,
                 lock: threading.RLock | None = None):
        self.cfg = config["higgsfield"]
        self.avatar = config["avatar"]["description"]
        self.save = save
        self.cutscene_dir = Path(cutscene_dir)
        self._lock = lock or threading.RLock()

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
        global _SDK_STATUS
        if _SDK_STATUS is None:
            try:
                import higgsfield_client  # noqa: F401
                _SDK_STATUS = (True, "online")
            except ImportError:
                _SDK_STATUS = (False, "higgsfield-client not installed (pip install -r requirements.txt)")
        if not _SDK_STATUS[0]:
            return _SDK_STATUS
        if not self._credentials():
            return False, "no API key in config.json"
        return True, "online"

    @property
    def video_enabled(self) -> bool:
        return bool(self.cfg.get("video_enabled"))

    # ── gallery queries ─────────────────────────────────────
    def entries(self, mission_id: str) -> list[dict]:
        with self._lock:
            try:
                self.save.refresh()               # another process may have rendered it meanwhile
            except (TimeoutError, OSError):
                pass
            return [dict(e, kind=entry_kind(e)) for e in self.save.gallery if e.get("mission") == mission_id]

    def entry(self, mission_id: str, kind: str) -> dict | None:
        found = [e for e in self.entries(mission_id) if e["kind"] == kind]
        return found[-1] if found else None

    def best_entry(self, mission_id: str) -> dict | None:
        """The richest finished media for a mission: its video if there is one, else its still."""
        return self.entry(mission_id, "video") or self.entry(mission_id, "image")

    def is_rendered(self, mission_id: str) -> bool:
        if self.entry(mission_id, "image") is None:
            return False
        return not self.video_enabled or self.entry(mission_id, "video") is not None

    # ── the pipeline ────────────────────────────────────────
    def render(self, cutscene: Cutscene, mission_id: str, on_progress: ProgressFn | None = None) -> list[dict]:
        """Render whatever is missing for this cutscene. Returns the mission's gallery entries.

        Raises CutsceneError (after reporting a "failed" progress event) if a stage fails.
        """
        notify = on_progress or (lambda *a, **k: None)

        still = self.entry(mission_id, "image")
        if still is None:
            notify("still", "rendering")
            try:
                still_url = self._render_still(cutscene, notify)
            except Exception as exc:  # noqa: BLE001 — surfaced to the caller as CutsceneError
                notify("still", "failed", error=f"{type(exc).__name__}: {exc}")
                raise CutsceneError("still", exc) from exc
            still = self._record(mission_id, cutscene.title, still_url,
                                 self._download(still_url, f"{mission_id}_still"), "image",
                                 anchor=cutscene.anchor)
            notify("still", "done", entry=still)

        if self.video_enabled and self.entry(mission_id, "video") is None:
            notify("video", "rendering")
            try:
                video_url = self._render_video(cutscene, still["url"])
            except Exception as exc:  # noqa: BLE001
                notify("video", "failed", error=f"{type(exc).__name__}: {exc}")
                raise CutsceneError("video", exc) from exc
            video = self._record(mission_id, f"{cutscene.title} (cinematic)", video_url,
                                 self._download(video_url, f"{mission_id}_cinematic"), "video")
            notify("video", "done", entry=video)
        return self.entries(mission_id)

    # ── Higgsfield calls ────────────────────────────────────
    def _client(self):
        import higgsfield_client
        return higgsfield_client.SyncClient(api_key=self._credentials())

    def _prompt(self, cutscene: Cutscene, motion: bool = False) -> str:
        parts = [cutscene.shot, f"The hero: {self.avatar}", STYLE_BIBLE]
        if motion and cutscene.camera:
            parts.insert(1, f"Camera: {cutscene.camera}")
        return ". ".join(parts)

    def _render_still(self, cutscene: Cutscene, notify: ProgressFn) -> str:
        client = self._client()
        args = {"prompt": self._prompt(cutscene), **self.cfg.get("image_arguments", {})}
        ref_key = self.cfg.get("reference_argument")
        with self._lock:
            avatar_url = self.save.avatar_url
        if avatar_url and ref_key and not cutscene.anchor:
            try:
                return _first_url(client.subscribe(self.cfg["image_model"], {**args, ref_key: avatar_url}))
            except Exception as exc:  # noqa: BLE001 — retry from the character bible alone
                notify("still", "fallback", error=f"reference image rejected ({exc})")
        return _first_url(client.subscribe(self.cfg["image_model"], args))

    def _render_video(self, cutscene: Cutscene, still_url: str) -> str:
        args = {"prompt": self._prompt(cutscene, motion=True),
                self.cfg["video_image_argument"]: still_url,
                **self.cfg.get("video_arguments", {})}
        return _first_url(self._client().subscribe(self.cfg["video_model"], args))

    # ── files ───────────────────────────────────────────────
    def _download(self, url: str, stem: str) -> str | None:
        """Keep a local copy (remote URLs can expire). On failure the URL is still recorded."""
        try:
            import httpx  # installed alongside higgsfield-client
            resp = httpx.get(url, follow_redirects=True, timeout=120)
            resp.raise_for_status()
            ext = Path(urlparse(url).path).suffix.lower()
            if ext not in MEDIA_EXTS:
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                ext = CONTENT_TYPE_EXTS.get(ctype, ext or ".bin")
            self.cutscene_dir.mkdir(parents=True, exist_ok=True)
            path = self.cutscene_dir / f"{stem}{ext}"
            tmp = path.with_name(f".{path.name}.part")
            tmp.write_bytes(resp.content)
            os.replace(tmp, path)
            return str(path)
        except Exception:  # noqa: BLE001
            return None

    def _record(self, mission_id: str, title: str, url: str, path: str | None, kind: str,
                anchor: bool = False) -> dict:
        entry = {"mission": mission_id, "title": title, "url": url, "path": path, "kind": kind}
        with self._lock, self.save.transaction():
            if anchor:
                self.save.avatar_url = url
            self.save.gallery.append(entry)
        return dict(entry)


class Director:
    """The terminal cutscene: a typed transmission, then the Higgsfield render with live status."""

    def __init__(self, console: Console, renderer: CutsceneRenderer, ui_cfg: dict):
        self.console = console
        self.renderer = renderer
        self.ui_cfg = ui_cfg

    def status(self) -> tuple[bool, str]:
        return self.renderer.status()

    def play(self, cutscene: Cutscene, mission_id: str) -> None:
        ui.transmission(self.console, cutscene, self.ui_cfg["animations"], self.ui_cfg["typing_speed"])
        online, reason = self.status()
        if not online:
            self.console.print(f"  [muted]◌ visual feed offline — {reason}[/]\n")
            return
        labels = {"still": "[pink]Rendering memory fragment via Higgsfield…[/]",
                  "video": f"[pink]Animating scene — camera: {cutscene.camera}…[/]"}
        saved = {"still": "MEMORY FRAGMENT SAVED", "video": "CINEMATIC SAVED"}
        final: dict | None = None
        with self.console.status(labels["still"], spinner="dots12") as spinner:
            def progress(stage: str, state: str, entry: dict | None = None, error: str | None = None) -> None:
                nonlocal final
                if state == "rendering":
                    spinner.update(labels[stage])
                elif state == "fallback":
                    self.console.print(f"  [warn]{error}; rendering from the character bible alone[/]")
                elif state == "done" and entry:
                    final = entry
                    self.console.print(f"  [ok]◉ {saved[stage]}[/] [steel]{self._short(entry)}[/]")

            try:
                self.renderer.render(cutscene, mission_id, on_progress=progress)
            except KeyboardInterrupt:
                self.console.print("  [muted]◌ render skipped[/]")
            except CutsceneError as exc:  # a failed render must never cost you a level
                self.console.print(f"  [bad]◌ SIGNAL LOST[/] [steel]{exc}[/]")
                self.console.print("  [muted]Check model ids / argument names in config.json against the "
                                   "model page on cloud.higgsfield.ai[/]")
        if final is None:
            final = self.renderer.best_entry(mission_id)
            if final:
                self.console.print(f"  [ok]◉ MEMORY ON FILE[/] [steel]{self._short(final)}[/]")
        if final and final.get("path") and self.renderer.cfg.get("auto_open"):
            webbrowser.open(Path(final["path"]).resolve().as_uri())
        self.console.print()

    def _short(self, entry: dict) -> str:
        path = entry.get("path")
        if not path:
            return entry.get("url", "")
        try:
            return str(Path(path).relative_to(self.renderer.cutscene_dir.parent))
        except ValueError:
            return path


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
