"""Local web server: the static client, a JSON API over GameSession, and Server-Sent Events.

Stdlib only (`ThreadingHTTPServer`). Contracts: docs/ARCHITECTURE.md §3.2–3.4.

Security model — this server runs the player's code, so every rule is enforced:
  1. Binds a loopback address only (anything else is refused at startup).
  2. The `Host` header must be `127.0.0.1:<port>` or `localhost:<port>` (DNS rebinding).
  3. A per-launch token (`secrets.token_urlsafe(24)`) is injected into index.html
     (`{{NS_TOKEN}}`). Every /api request must send it as `X-NS-Token`; only the
     EventSource stream may pass `?token=`. A custom header forces a CORS preflight,
     which this server never approves (it never emits Access-Control-* headers).
  4. Static paths are resolved and must stay inside their root: no `..`, no
     dotfiles, no backslashes or NULs, symlinks resolved before the check.
  5. Request bodies are capped at 1 MB.

Threads
  * one per HTTP connection (daemon; HTTP/1.1 keep-alive),
  * `MissionWatcher`: polls the active mission file every 300 ms and streams
    external edits as `file` events; writes made through the API are wrapped in
    `own_write()`, which re-baselines the content hash so they never echo back.
    It also polls save.json: progress saved by another process (`game.py tui`,
    `hack`, `watch`) is adopted and pushed to every tab as a `state` event,
  * `CutsceneJobs`: a single worker that renders Higgsfield cutscenes (minutes
    long) and streams progress as `cutscene` events. A victory queues the render
    immediately so it cooks while the player reads the reward screen.
  * `EventBroker` fans SSE messages out through one bounded queue per client; a
    client that falls behind is dropped (EventSource reconnects) rather than
    letting memory grow.

Static files are served with ETag revalidation (`Cache-Control: no-cache`),
single-range requests (video scrubbing) and zero-copy `sendfile`. API responses
are `no-store`. Access logging is silent; only real server faults reach stderr.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import ipaddress
import json
import os
import queue
import re
import secrets
import signal
import socket
import socketserver
import sys
import threading
import time
import traceback
import webbrowser
from email.utils import formatdate
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import parse_qs, unquote, urlsplit

from engine.cinematics import MEDIA_EXTS
from engine.session import GameSession, SessionError
from engine.state import GAME_DIR

__all__ = ["serve", "create_server", "GameServer", "EventBroker", "MissionWatcher", "CutsceneJobs",
           "CLIENT_DIR", "DEFAULT_PORT", "MAX_BODY"]

CLIENT_DIR = GAME_DIR / "client"
DEFAULT_PORT = 7777
PORT_FALLBACKS = 20                 # try port, port+1, … port+20
MAX_BODY = 1024 * 1024              # 1 MB request body cap
DISCARD_LIMIT = 16 * 1024 * 1024    # oversized bodies up to this are drained so the 413 arrives cleanly
KEEPALIVE_SECONDS = 15.0
WATCH_INTERVAL = 0.3
CLIENT_QUEUE = 256                  # SSE messages buffered per client before it counts as fallen behind
TOKEN_PLACEHOLDER = "{{NS_TOKEN}}"
MISSION_ID = r"(?P<mission_id>[A-Za-z0-9_-]{1,32})"

MIME_TYPES = {
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8", ".glsl": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".avif": "image/avif", ".ico": "image/x-icon",
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf",
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wasm": "application/wasm",
}


_DISCONNECTS = (ConnectionError, TimeoutError, socket.timeout)


class HttpError(Exception):
    def __init__(self, status: int, message: str, headers: dict | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.headers = headers or {}


def json_bytes(data) -> bytes:
    """Compact UTF-8 JSON that can never fail to encode.

    Text holding a lone UTF-16 surrogate (it can arrive through argv or old rows) is
    not valid UTF-8; such payloads fall back to ASCII escapes, which every JSON
    parser accepts, instead of turning the response into a 500.
    """
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        return json.dumps(data, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def encode_event(event: str, data) -> bytes:
    """One SSE message. json.dumps never emits raw newlines, so `data:` stays on one line."""
    return f"event: {event}\ndata: ".encode("utf-8") + json_bytes(data) + b"\n\n"


def content_type(path: Path) -> str:
    return MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")


# ── SSE fan-out ─────────────────────────────────────────────
class _Subscriber:
    __slots__ = ("queue",)

    def __init__(self, size: int):
        self.queue: queue.Queue = queue.Queue(size)


class EventBroker:
    """Publish once, deliver to every connected EventSource through its own bounded queue."""

    def __init__(self, queue_size: int = CLIENT_QUEUE):
        self._subscribers: set[_Subscriber] = set()
        self._lock = threading.Lock()
        self._size = queue_size
        self._closed = False

    def subscribe(self) -> _Subscriber:
        sub = _Subscriber(self._size)
        with self._lock:
            if not self._closed:
                self._subscribers.add(sub)
                return sub
        sub.queue.put_nowait(None)   # broker already closed: the stream ends immediately
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        with self._lock:
            self._subscribers.discard(sub)

    def publish(self, event: str, data) -> None:
        message = encode_event(event, data)
        with self._lock:
            subscribers = tuple(self._subscribers)
        for sub in subscribers:
            try:
                sub.queue.put_nowait(message)
            except queue.Full:
                self._drop(sub)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            subscribers = tuple(self._subscribers)
        for sub in subscribers:
            self._drop(sub)

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def _drop(self, sub: _Subscriber) -> None:
        """Disconnect a client: empty its backlog and leave the end-of-stream sentinel."""
        self.unsubscribe(sub)
        with contextlib.suppress(queue.Empty):
            while True:
                sub.queue.get_nowait()
        with contextlib.suppress(queue.Full):
            sub.queue.put_nowait(None)


# ── mission file watcher ────────────────────────────────────
def _file_signature(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def _read_source(path: Path) -> tuple[str, bytes, float] | None:
    """(normalised text, content hash, mtime) or None if the file is gone."""
    try:
        raw = path.read_bytes()
        mtime = path.stat().st_mtime
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return text, hashlib.blake2b(text.encode("utf-8"), digest_size=16).digest(), mtime


class MissionWatcher:
    """Streams edits the player makes in their own editor into the browser (SSE `file`)."""

    SETTLE_STEPS = 4          # editors often truncate, then write: wait for the file to hold still
    SETTLE_SECONDS = 0.05

    def __init__(self, session: GameSession, broker: EventBroker, interval: float = WATCH_INTERVAL):
        self._session = session
        self._broker = broker
        self._interval = interval
        self._lock = threading.Lock()     # serialises API writes against poll checks
        self._mission: str | None = None
        self._path: Path | None = None
        self._signature: tuple[int, int] | None = None
        self._digest: bytes | None = None   # hash of the content the client is known to have
        self._reloads = session.save_reloads   # save.json changes from other processes already published
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def mission(self) -> str | None:
        return self._mission

    def start(self) -> None:
        current = self._session.current_playable_id()
        if current:
            self.track(current, rebaseline=True)
        self._thread = threading.Thread(target=self._run, name="ns-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def track(self, mission_id: str, rebaseline: bool = False) -> None:
        """Watch this mission's file. Re-baselining adopts what is on disk now without reporting it.

        Only playable missions are tracked, so a refused request never steals the watch.
        """
        with self._lock:
            if mission_id == self._mission and not rebaseline:
                return
            if not self._session.playable(mission_id):
                return
            try:
                path = self._session.mission_path(mission_id)
            except SessionError:
                return
            self._mission, self._path = mission_id, path
            self._adopt_disk()

    @contextlib.contextmanager
    def own_write(self, mission_id: str) -> Iterator[None]:
        """Wrap a write made on the client's behalf so it is never reported back as an external edit."""
        self.track(mission_id)
        with self._lock:
            try:
                yield
            finally:
                if self._mission == mission_id:
                    self._adopt_disk()

    def poll_save(self) -> None:
        """Push progress another process saved (a terminal clear, say) to every open tab."""
        self._session.refresh()
        for notice in self._session.take_notices():
            print(f"  ! {notice}", file=sys.stderr)
        reloads = self._session.save_reloads
        if reloads != self._reloads:
            self._reloads = reloads
            self._broker.publish("state", self._session.snapshot())

    def _adopt_disk(self) -> None:
        self._signature = _file_signature(self._path)
        current = _read_source(self._path)
        self._digest = current[1] if current else None

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.poll()
            except Exception:  # noqa: BLE001 — the watcher must outlive any odd filesystem state
                traceback.print_exc()

    def poll(self) -> None:
        self.poll_save()
        path = self._path
        if path is None:
            current = self._session.current_playable_id()
            if current:
                self.track(current, rebaseline=True)
            return
        signature = _file_signature(path)
        if signature == self._signature:
            return
        for _ in range(self.SETTLE_STEPS):
            time.sleep(self.SETTLE_SECONDS)
            again = _file_signature(path)
            if again == signature:
                break
            signature = again
        with self._lock:
            if self._path != path:
                return
            self._signature = _file_signature(path)
            current = _read_source(path)
            if current is None or current[1] == self._digest:
                return
            text, self._digest, mtime = current
            mission = self._mission
        self._broker.publish("file", {"mission": mission, "source": text, "mtime": mtime})


# ── cutscene render jobs ────────────────────────────────────
class CutsceneJobs:
    """A single background worker for Higgsfield renders, reported through SSE `cutscene` events."""

    def __init__(self, session: GameSession, broker: EventBroker):
        self._session = session
        self._broker = broker
        self._states: dict[str, str] = {}      # mission -> queued | rendering | done | failed
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="ns-cutscenes", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._queue.put(None)   # a render in flight finishes on its own; the thread is a daemon

    def state(self, mission_id: str) -> str | None:
        with self._lock:
            return self._states.get(mission_id)

    def request(self, mission_id: str) -> dict:
        """POST /api/missions/:id/cutscene → {"mission", "state": queued|done|offline, "url"?, "reason"?}."""
        cutscene = self._session.cutscene(mission_id)
        cinema = self._session.cinema
        if cutscene is None:
            return {"mission": mission_id, "state": "offline", "reason": "this mission has no transmission"}
        if cinema.is_rendered(mission_id):
            return self._done(mission_id)
        if self.state(mission_id) in ("queued", "rendering"):
            return {"mission": mission_id, "state": "queued"}
        online, reason = cinema.status()
        if not online:
            if cinema.best_entry(mission_id):      # a still survived an earlier partial render
                return self._done(mission_id)
            return {"mission": mission_id, "state": "offline", "reason": reason}
        self._enqueue(mission_id)
        return {"mission": mission_id, "state": "queued"}

    def on_victory(self, mission_id: str) -> None:
        """Latency hiding: start rendering while the player is still on the reward screen."""
        try:
            cutscene = self._session.cutscene(mission_id)
        except SessionError:
            return
        cinema = self._session.cinema
        if cutscene is None or cinema.is_rendered(mission_id):
            return
        online, reason = cinema.status()
        if online:
            self._enqueue(mission_id)
        else:
            self._broker.publish("cutscene", {"mission": mission_id, "state": "offline", "stage": "still",
                                              "error": reason})

    def _done(self, mission_id: str) -> dict:
        entry = self._session.cinema.best_entry(mission_id)
        return {"mission": mission_id, "state": "done", "url": self._session.media_url(entry) if entry else ""}

    def _enqueue(self, mission_id: str) -> None:
        with self._lock:
            if self._states.get(mission_id) in ("queued", "rendering"):
                return
            self._states[mission_id] = "queued"
        self._queue.put(mission_id)

    def _run(self) -> None:
        while True:
            mission_id = self._queue.get()
            if mission_id is None:
                return
            self._render(mission_id)

    def _set_state(self, mission_id: str, state: str) -> None:
        with self._lock:
            self._states[mission_id] = state

    def _render(self, mission_id: str) -> None:
        self._set_state(mission_id, "rendering")
        published = {"any": False, "failed": False}

        def progress(stage: str, state: str, entry: dict | None = None, error: str | None = None) -> None:
            if state == "fallback":
                return
            if state == "failed":
                # Record it before the event lands, so a client retrying on that event is re-queued.
                self._set_state(mission_id, "failed")
            payload = {"mission": mission_id, "state": state, "stage": stage}
            if entry:
                payload["url"] = self._session.media_url(entry)
                payload["kind"] = entry.get("kind", "image")
            if error:
                payload["error"] = error
            published["any"] = True
            published["failed"] |= state == "failed"
            self._broker.publish("cutscene", payload)
            if state == "done":
                self._broker.publish("state", self._session.snapshot())

        try:
            cutscene = self._session.cutscene(mission_id)
            if cutscene is not None:
                self._session.cinema.render(cutscene, mission_id, on_progress=progress)
        except Exception as exc:  # noqa: BLE001 — a failed render must never take the server down
            self._set_state(mission_id, "failed")
            if not published["failed"]:
                self._broker.publish("cutscene", {"mission": mission_id, "state": "failed", "stage": "still",
                                                  "error": f"{type(exc).__name__}: {exc}"})
            return
        if not published["any"]:
            entry = self._session.cinema.best_entry(mission_id)
            if entry:
                progress("video" if entry.get("kind") == "video" else "still", "done", entry=entry)
        self._set_state(mission_id, "done")


# ── HTTP ────────────────────────────────────────────────────
class RequestHandler(BaseHTTPRequestHandler):
    server: "GameServer"
    protocol_version = "HTTP/1.1"
    server_version = "NullSector/1.0"
    sys_version = ""
    timeout = 75                     # idle keep-alive connections are reaped after this

    ROUTES = (
        ("GET", re.compile(r"/api/state"), "api_state"),
        ("GET", re.compile(r"/api/productivity"), "api_productivity"),
        ("GET", re.compile(r"/api/productivity/rewards"), "api_productivity_rewards"),
        ("POST", re.compile(r"/api/productivity/(?P<command>study|workout|weight|habit)"), "api_log_productivity"),
        ("GET", re.compile(r"/api/events"), "api_events"),
        ("GET", re.compile(rf"/api/missions/{MISSION_ID}"), "api_mission"),
        ("POST", re.compile(rf"/api/missions/{MISSION_ID}/deploy"), "api_deploy"),
        ("PUT", re.compile(rf"/api/missions/{MISSION_ID}/source"), "api_source"),
        ("POST", re.compile(rf"/api/missions/{MISSION_ID}/hack"), "api_hack"),
        ("POST", re.compile(rf"/api/missions/{MISSION_ID}/reset"), "api_reset"),
        ("POST", re.compile(rf"/api/missions/{MISSION_ID}/cutscene"), "api_cutscene"),
    )

    # quiet: the terminal belongs to the game banner
    def log_message(self, format, *args):  # noqa: A002 — signature fixed by the base class
        pass

    def version_string(self) -> str:
        return self.server_version

    def do_GET(self):
        self._handle("GET")

    def do_HEAD(self):
        self._handle("HEAD")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_OPTIONS(self):
        self._handle("OPTIONS")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_PATCH(self):
        self._handle("PATCH")

    # ── dispatch ────────────────────────────────────────────
    def _handle(self, method: str) -> None:
        self._sent = False
        self._body_consumed = False
        try:
            host = (self.headers.get("Host") or "").strip().lower()
            if host not in self.server.allowed_hosts:
                raise HttpError(403, "forbidden host")
            url = urlsplit(self.path)
            if url.path == "/api" or url.path.startswith("/api/"):
                self._api(method, url)
            else:
                self._static(method, url.path)
        except HttpError as exc:
            self._fail(exc.status, exc.message, exc.headers)
        except SessionError as exc:
            self._fail(exc.status, exc.message)
        except _DISCONNECTS:
            self.close_connection = True
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._fail(500, "internal server error")
        finally:
            if not self._body_consumed and self._declared_length() > 0:
                self.close_connection = True   # never parse leftover body bytes as the next request

    def _api(self, method: str, url) -> None:
        self._authorize(url, allow_query=(method == "GET" and url.path == "/api/events"))
        allowed = []
        for verb, pattern, name in self.ROUTES:
            match = pattern.fullmatch(url.path)
            if match:
                if verb == method:
                    getattr(self, name)(**match.groupdict())
                    return
                allowed.append(verb)
        if allowed:
            raise HttpError(405, "method not allowed", {"Allow": ", ".join(allowed)})
        raise HttpError(404, "no such endpoint")

    def _authorize(self, url, allow_query: bool) -> None:
        supplied = self.headers.get("X-NS-Token")
        if supplied is None and allow_query:
            supplied = (parse_qs(url.query).get("token") or [None])[0]
        if not supplied:
            raise HttpError(401, "missing session token")
        if not hmac.compare_digest(supplied.encode("utf-8"), self.server.token.encode("utf-8")):
            raise HttpError(403, "invalid session token")

    # ── API endpoints ───────────────────────────────────────
    def api_state(self) -> None:
        self._json(200, self.server.session.snapshot())

    def api_productivity(self) -> None:
        self._json(200, self.server.session.productivity_snapshot())

    def api_productivity_rewards(self) -> None:
        self._json(200, self.server.session.productivity_rewards())

    def api_log_productivity(self, command: str) -> None:
        result = self.server.session.log_productivity(command, self._read_json())
        self._json(200, result)
        self.server.broker.publish("productivity", result["snapshot"])

    def api_mission(self, mission_id: str) -> None:
        self._json(200, self.server.session.mission(mission_id))

    def api_deploy(self, mission_id: str) -> None:
        self._read_body()
        # Deploy may drop the starter file; the payload already carries it, so it is not an external edit.
        with self.server.watcher.own_write(mission_id):
            payload = self.server.session.deploy(mission_id)
        self._json(200, payload)

    def api_source(self, mission_id: str) -> None:
        body = self._read_json()
        source = body.get("source") if isinstance(body, dict) else None
        if not isinstance(source, str):
            raise HttpError(400, 'body must be {"source": str}')
        with self.server.watcher.own_write(mission_id):
            result = self.server.session.write_source(mission_id, source)
        self._json(200, result)

    def api_hack(self, mission_id: str) -> None:
        self._read_body()
        result = self.server.session.attack(mission_id)
        self.server.watcher.track(mission_id)
        if result["victory"]:
            self.server.jobs.on_victory(mission_id)
        self._json(200, result)
        if result["victory"]:
            self.server.broker.publish("state", result["state"])

    def api_reset(self, mission_id: str) -> None:
        self._read_body()
        with self.server.watcher.own_write(mission_id):
            result = self.server.session.reset(mission_id)
        self._json(200, result)

    def api_cutscene(self, mission_id: str) -> None:
        self._read_body()
        self._json(200, self.server.jobs.request(mission_id))

    def api_events(self) -> None:
        broker = self.server.broker
        sub = broker.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")      # the stream ends when the socket does
            self.end_headers()
            write = self.wfile.write
            write(b"retry: 1500\n\n" + encode_event("hello", {"server_time": time.time()}))
            while True:
                try:
                    message = sub.queue.get(timeout=KEEPALIVE_SECONDS)
                except queue.Empty:
                    message = b": keepalive\n\n"
                if message is None:
                    break
                write(message)
        finally:
            broker.unsubscribe(sub)
            self.close_connection = True

    # ── static files ────────────────────────────────────────
    def _static(self, method: str, path: str) -> None:
        if method not in ("GET", "HEAD"):
            raise HttpError(405, "method not allowed", {"Allow": "GET, HEAD"})
        if path in ("/", "/index.html"):
            body = self.server.index_html()
            self._respond(200, body, "text/html; charset=utf-8", {"Cache-Control": "no-store"})
            return
        if path.startswith("/cutscenes/"):
            file = resolve_static(self.server.cutscene_root, path[len("/cutscenes/"):])
            if file.suffix.lower() not in MEDIA_EXTS:
                raise HttpError(404, "not found")
        else:
            try:
                file = resolve_static(self.server.client_root, path.lstrip("/"))
            except HttpError as exc:
                if path == "/favicon.ico" and exc.status == 404:   # no icon shipped: answer quietly
                    self._respond(204, b"", "image/x-icon", {"Cache-Control": "no-cache"})
                    return
                raise
        self._send_file(file)

    def _send_file(self, file: Path) -> None:
        st = file.stat()
        size = st.st_size
        etag = f'"{st.st_mtime_ns:x}-{size:x}"'
        headers = {"Cache-Control": "no-cache", "ETag": etag, "Accept-Ranges": "bytes",
                   "Last-Modified": formatdate(st.st_mtime, usegmt=True)}
        if etag in [tag.strip().removeprefix("W/") for tag in (self.headers.get("If-None-Match") or "").split(",")]:
            self._respond(304, None, None, headers)
            return
        status, start, length = 200, 0, size
        byte_range = parse_range(self.headers.get("Range"), size)
        if byte_range is not None:
            start, end = byte_range
            status, length = 206, end - start + 1
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        self.send_response(status)
        self.send_header("Content-Type", content_type(file))
        self.send_header("Content-Length", str(length))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command == "HEAD" or length == 0:
            return
        with open(file, "rb") as handle:
            self.connection.sendfile(handle, offset=start, count=length)

    # ── request bodies ──────────────────────────────────────
    def _declared_length(self) -> int:
        try:
            return max(int(self.headers.get("Content-Length") or 0), 0)
        except (TypeError, ValueError, AttributeError):
            return 0

    def _read_body(self) -> bytes:
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            self.close_connection = True
            raise HttpError(411, "chunked request bodies are not supported")
        raw_length = self.headers.get("Content-Length") or "0"
        try:
            length = int(raw_length)
        except ValueError:
            self.close_connection = True
            raise HttpError(400, "invalid Content-Length") from None
        if length < 0:
            self.close_connection = True
            raise HttpError(400, "invalid Content-Length")
        if length > MAX_BODY:
            self._discard_body(length)
            raise HttpError(413, f"request body too large (max {MAX_BODY // 1024} KB)")
        data = self.rfile.read(length) if length else b""
        self._body_consumed = True
        if len(data) != length:
            self.close_connection = True
            raise HttpError(400, "incomplete request body")
        return data

    def _discard_body(self, length: int) -> None:
        """Drain a moderately oversized body (never stored) so the client can read our 413."""
        if length > DISCARD_LIMIT:
            self.close_connection = True
            return
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                self.close_connection = True
                return
            remaining -= len(chunk)
        self._body_consumed = True

    def _read_json(self):
        data = self._read_body()
        try:
            return json.loads(data.decode("utf-8"))
        except (ValueError, RecursionError):
            # ValueError covers invalid UTF-8, malformed JSON and integers too long to convert;
            # RecursionError covers absurdly nested arrays. None of it may reach a traceback.
            raise HttpError(400, "body is not valid JSON") from None

    # ── responses ───────────────────────────────────────────
    def _json(self, status: int, payload, headers: dict | None = None) -> None:
        body = json_bytes(payload)
        self._respond(status, body, "application/json; charset=utf-8", {"Cache-Control": "no-store", **(headers or {})})

    def _respond(self, status: int, body: bytes | None, ctype: str | None, headers: dict | None = None) -> None:
        self.send_response(status)
        if ctype:
            self.send_header("Content-Type", ctype)
        if status != 304:
            self.send_header("Content-Length", str(len(body or b"")))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _fail(self, status: int, message: str, headers: dict | None = None) -> None:
        if self._sent:                       # mid-stream failure: all we can do is hang up
            self.close_connection = True
            return
        if status >= 400 and not self._body_consumed and self._declared_length() > 0:
            self.close_connection = True
        extra = dict(headers or {})
        if self.close_connection:
            extra["Connection"] = "close"
        self._json(status, {"error": message}, extra)

    def send_error(self, code, message=None, explain=None):
        """Protocol-level errors from the base class (bad request line, unknown verb…) as JSON too."""
        self._sent = getattr(self, "_sent", False)
        self._body_consumed = True
        self.close_connection = True
        try:
            phrase = HTTPStatus(code).phrase
        except ValueError:
            phrase = "error"
        self._json(code, {"error": message or phrase}, {"Connection": "close"})

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()
        self._sent = True


def resolve_static(root: Path, rel: str) -> Path:
    """Map a URL path under `root` to a file, refusing anything that could escape it."""
    rel = unquote(rel)
    if not rel or rel.endswith("/"):
        raise HttpError(404, "not found")
    if "\x00" in rel or "\\" in rel or ":" in rel:
        raise HttpError(403, "forbidden path")
    parts = rel.split("/")
    if any(part in ("", ".", "..") or part.startswith(".") for part in parts):
        raise HttpError(403, "forbidden path")
    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        raise HttpError(403, "forbidden path")
    if not candidate.is_file():
        raise HttpError(404, "not found")
    return candidate


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """A single `bytes=` range → (start, end) inclusive; None = serve everything. Raises 416."""
    if not header or size <= 0:
        return None
    match = re.fullmatch(r"\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*", header)
    if not match or not (match.group(1) or match.group(2)):
        return None                               # malformed or multi-range: full response is valid
    if match.group(1):
        start = int(match.group(1))
        end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
    else:
        suffix = int(match.group(2))
        if suffix == 0:
            raise HttpError(416, "unsatisfiable range", {"Content-Range": f"bytes */{size}"})
        start, end = max(size - suffix, 0), size - 1
    if start >= size or start > end:
        raise HttpError(416, "unsatisfiable range", {"Content-Range": f"bytes */{size}"})
    return start, end


class GameServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = os.name != "nt"   # on Windows SO_REUSEADDR would let two servers share a port

    def __init__(self, session: GameSession, address: tuple[str, int], client_dir: Path = CLIENT_DIR):
        super().__init__(address, RequestHandler)
        self.session = session
        self.token = secrets.token_urlsafe(24)
        self.client_root = Path(client_dir).resolve()
        self.cutscene_root = session.paths.cutscene_dir.resolve()
        host, port = self.server_address[:2]
        self.allowed_hosts = frozenset({f"127.0.0.1:{port}", f"localhost:{port}", f"{address[0]}:{port}".lower()})
        self.broker = EventBroker()
        self.watcher = MissionWatcher(session, self.broker)
        self.jobs = CutsceneJobs(session, self.broker)
        self._index: tuple[tuple[int, int], bytes] | None = None
        self._index_lock = threading.Lock()
        self._serve_thread: threading.Thread | None = None
        self._services = False
        self._closed = False

    def server_bind(self) -> None:
        # HTTPServer.server_bind() calls socket.getfqdn(), a reverse-DNS lookup that can stall
        # startup for seconds on some machines. We never use the name, so skip it.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    @property
    def port(self) -> int:
        return self.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start_services(self) -> None:
        if not self._services:
            self._services = True
            self.watcher.start()
            self.jobs.start()

    def start_background(self) -> threading.Thread:
        """Serve from a daemon thread (tests, embedding). Stop with close()."""
        self.start_services()
        self._serve_thread = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.1},
                                              name="ns-http", daemon=True)
        self._serve_thread.start()
        return self._serve_thread

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.broker.close()        # ends every SSE stream so its thread exits
        self.watcher.stop()
        self.jobs.stop()
        if self._serve_thread is not None and self._serve_thread.is_alive():
            self.shutdown()
            self._serve_thread.join(timeout=2)
        self.server_close()

    def index_html(self) -> bytes:
        """client/index.html with the launch token injected (re-read only when the file changes)."""
        path = self.client_root / "index.html"
        try:
            st = path.stat()
        except OSError:
            raise HttpError(503, "web client not found (client/index.html) — try: python game.py tui") from None
        key = (st.st_mtime_ns, st.st_size)
        with self._index_lock:
            if self._index and self._index[0] == key:
                return self._index[1]
            html = path.read_text(encoding="utf-8")
            if TOKEN_PLACEHOLDER in html:
                html = html.replace(TOKEN_PLACEHOLDER, self.token)
            else:
                meta = f'<meta name="ns-token" content="{self.token}">'
                html, count = re.subn(r"(<head\b[^>]*>)", lambda m: m.group(1) + meta, html, count=1, flags=re.I)
                if not count:
                    html = meta + html
            body = html.encode("utf-8")
            self._index = (key, body)
            return body

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], _DISCONNECTS):
            return   # the browser went away mid-request: not an error worth a traceback
        super().handle_error(request, client_address)


def _require_loopback(host: str) -> None:
    if host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise ValueError(f"refusing to bind {host!r}: the game server only listens on the loopback interface")


def create_server(session: GameSession, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                  client_dir: Path = CLIENT_DIR) -> GameServer:
    """Bind the first free port in [port, port + 20] (port 0 = any free port)."""
    _require_loopback(host)
    if not 0 <= port <= 65535:
        raise ValueError(f"port {port} is out of range (0-65535)")
    last_port = min(port + PORT_FALLBACKS, 65535)
    candidates = [0] if port == 0 else range(port, last_port + 1)
    last_error: OSError | None = None
    for candidate in candidates:
        try:
            return GameServer(session, (host, candidate), client_dir)
        except OSError as exc:
            last_error = exc
    raise OSError(f"no free port between {port} and {last_port} ({last_error})")


def serve(session: GameSession, host: str = "127.0.0.1", port: int = DEFAULT_PORT, open_browser: bool = True,
          client_dir: Path = CLIENT_DIR, *, on_ready: Callable[[str], None] | None = None) -> None:
    """Run the web client until Ctrl+C (or SIGTERM), then shut every thread down cleanly."""
    server = create_server(session, host, port, client_dir)
    server.start_services()
    if on_ready:
        on_ready(server.url)
    for notice in session.take_notices():      # e.g. a damaged save.json was moved aside
        print(f"  ! {notice}", file=sys.stderr)
    if open_browser:
        threading.Thread(target=webbrowser.open, args=(server.url,), name="ns-browser", daemon=True).start()

    previous = None
    if threading.current_thread() is threading.main_thread() and hasattr(signal, "SIGTERM"):
        def _terminate(signum, frame):
            raise KeyboardInterrupt
        previous = signal.signal(signal.SIGTERM, _terminate)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)
