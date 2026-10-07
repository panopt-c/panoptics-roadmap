"""The local web server: security rules, the JSON API, Server-Sent Events, the file watcher and cutscene jobs.

Each test gets its own server on a free port, a temp game folder and a tiny
temp client (index.html with the {{NS_TOKEN}} placeholder), so nothing here
depends on the real client/ files or touches the real save.
"""
from __future__ import annotations

import http.client
import json
import os
import queue
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import (ROOT, SOLUTION, STARTER, FakeHiggsfield, SandboxTestCase, assert_hack_result,  # noqa: E402
                   assert_mission, assert_state, online_higgsfield)

from engine.server import MAX_BODY, PORT_FALLBACKS, create_server  # noqa: E402

INDEX = '<!doctype html><html><head><meta name="ns-token" content="{{NS_TOKEN}}"></head><body></body></html>'
STATIC = {
    "js/main.js": ("export const ok = true;\n", "text/javascript"),
    "js/lib.mjs": ("export default 1;\n", "text/javascript"),
    "css/app.css": ("body { color: #8892a6; }\n", "text/css"),
    "img/icon.svg": ("<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"),
    "img/a.png": ("png", "image/png"),
    "img/b.jpg": ("jpg", "image/jpeg"),
    "img/c.webp": ("webp", "image/webp"),
    "media/d.mp4": ("mp4", "video/mp4"),
    "media/e.webm": ("webm", "video/webm"),
    "fonts/f.woff2": ("woff2", "font/woff2"),
    "data/g.json": ("{}", "application/json"),
}
SECRET = "TOP-SECRET-MARKER"


class Response:
    def __init__(self, status: int, headers, body: bytes):
        self.status, self.headers, self.body = status, headers, body

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")


class SSEClient:
    """A minimal EventSource: parses the stream on a reader thread into (event, data) tuples."""

    def __init__(self, port: int, path: str, host: str | None = None):
        self.events: queue.Queue = queue.Queue()
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host or f'127.0.0.1:{port}'}\r\n"
                           "Accept: text/event-stream\r\n\r\n").encode())
        self.file = self.sock.makefile("rb")
        self.status = int(self.file.readline().split()[1])
        self.headers = {}
        while (line := self.file.readline().decode().strip()):
            key, _, value = line.partition(":")
            self.headers[key.strip().lower()] = value.strip()
        self.sock.settimeout(None)
        self.closed = threading.Event()
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self) -> None:
        name, data = "message", []
        try:
            for raw in self.file:
                line = raw.decode("utf-8").rstrip("\r\n")
                if not line:
                    if data:
                        self.events.put((name, json.loads("\n".join(data))))
                    name, data = "message", []
                elif line.startswith("event:"):
                    name = line[6:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].strip())
        except (OSError, ValueError):
            pass
        finally:
            self.closed.set()

    def next(self, event: str | None = None, timeout: float = 5.0):
        """The next event (optionally the next one named `event`, skipping others)."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"no {event or 'SSE'} event within {timeout}s")
            try:
                name, data = self.events.get(timeout=remaining)
            except queue.Empty:
                continue
            if event is None or name == event:
                return name, data

    def drain(self) -> list[tuple[str, dict]]:
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.closed.wait(2)      # the reader sees EOF, then the buffered file can be closed safely
        self.file.close()
        self.sock.close()


class ServerTestCase(SandboxTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client_dir = self.root / "client"
        self.client_dir.mkdir()
        (self.client_dir / "index.html").write_text(INDEX, encoding="utf-8")
        for rel, (content, _ctype) in STATIC.items():
            path = self.client_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="")
        (self.root / "secret.txt").write_text(SECRET, encoding="utf-8")
        self.server = create_server(self.session, port=0, client_dir=self.client_dir)
        self.server.start_background()
        self.addCleanup(self.server.close)
        self.port = self.server.port
        self.token = self.server.token

    def request(self, method: str, path: str, body=None, *, token=True, host: str | None = None,
                headers: dict | None = None) -> Response:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", host if host is not None else f"127.0.0.1:{self.port}")
            if token is True:
                token = self.token
            if token:
                conn.putheader("X-NS-Token", token)
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            if body is not None or method in ("POST", "PUT"):
                conn.putheader("Content-Type", "application/json")
                conn.putheader("Content-Length", str(len(body or b"")))
            for key, value in (headers or {}).items():
                conn.putheader(key, value)
            conn.endheaders(body)
            resp = conn.getresponse()
            return Response(resp.status, resp.headers, resp.read())
        finally:
            conn.close()

    def sse(self, path: str | None = None, host: str | None = None) -> SSEClient:
        stream = SSEClient(self.port, path or f"/api/events?token={self.token}", host=host)
        self.addCleanup(stream.close)
        return stream

    def win(self) -> dict:
        self.request("POST", "/api/missions/L01/deploy")
        self.assertEqual(self.request("PUT", "/api/missions/L01/source", {"source": SOLUTION}).status, 200)
        result = self.request("POST", "/api/missions/L01/hack").json()
        self.assertTrue(result["victory"])
        return result


class SecurityTests(ServerTestCase):
    def test_token_is_injected_into_index(self):
        resp = self.request("GET", "/", token=None)
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.headers["Content-Type"].startswith("text/html"))
        self.assertEqual(resp.headers["Cache-Control"], "no-store")
        self.assertIn(f'<meta name="ns-token" content="{self.token}">', resp.text)
        self.assertNotIn("{{NS_TOKEN}}", resp.text)
        self.assertGreaterEqual(len(self.token), 32)
        self.assertEqual(self.request("GET", "/index.html", token=None).text, resp.text)
        other = create_server(self.session, port=0, client_dir=self.client_dir)
        self.addCleanup(other.close)
        self.assertNotEqual(other.token, self.token, "the token is per launch")

    def test_index_without_placeholder_still_gets_the_meta(self):
        (self.client_dir / "index.html").write_text("<html><head><title>x</title></head></html>", encoding="utf-8")
        html = self.request("GET", "/", token=None).text
        self.assertIn(f'<head><meta name="ns-token" content="{self.token}">', html)

    def test_missing_client_is_a_clear_503(self):
        (self.client_dir / "index.html").unlink()
        resp = self.request("GET", "/", token=None)
        self.assertEqual(resp.status, 503)
        self.assertIn("client/index.html", resp.json()["error"])

    def test_wrong_host_is_rejected(self):
        for host in ("evil.example", f"evil.example:{self.port}", f"127.0.0.1:{self.port + 1}", "127.0.0.1", ""):
            for path in ("/", "/js/main.js", "/api/state"):
                with self.subTest(host=host, path=path):
                    resp = self.request("GET", path, host=host)
                    self.assertEqual(resp.status, 403)
                    self.assertEqual(resp.json(), {"error": "forbidden host"})
        self.assertEqual(self.request("GET", "/api/state", host=f"localhost:{self.port}").status, 200)
        self.assertEqual(self.request("GET", "/api/state", host=f"LOCALHOST:{self.port}").status, 200)

    def test_api_requires_the_token(self):
        missing = self.request("GET", "/api/state", token=None)
        self.assertEqual(missing.status, 401)
        self.assertEqual(set(missing.json()), {"error"})
        self.assertEqual(self.request("GET", "/api/state", token="wrong").status, 403)
        self.assertEqual(self.request("GET", "/api/state", token=self.token[:-1]).status, 403)
        self.assertEqual(self.request("GET", "/api/state").status, 200)
        for method, path in (("POST", "/api/missions/L01/hack"), ("PUT", "/api/missions/L01/source"),
                             ("POST", "/api/missions/L01/reset"), ("POST", "/api/missions/L01/deploy"),
                             ("GET", "/api/missions/L01"), ("POST", "/api/missions/L01/cutscene")):
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path, token=None).status, 401)
                self.assertEqual(self.request(method, path, token="nope").status, 403)
        self.assertEqual(self.session.save.attempts, {}, "an unauthorised hack never ran")

    def test_query_token_only_works_for_the_event_stream(self):
        self.assertEqual(self.request("GET", f"/api/state?token={self.token}", token=None).status, 401)
        self.assertEqual(self.request("POST", f"/api/missions/L01/hack?token={self.token}", token=None).status, 401)
        self.assertEqual(self.sse("/api/events").status, 401)
        self.assertEqual(self.sse("/api/events?token=forged").status, 403)
        self.assertEqual(self.sse(host="evil.example").status, 403)

    def test_cors_preflight_is_never_approved(self):
        resp = self.request("OPTIONS", "/api/missions/L01/hack", token=None, headers={
            "Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-ns-token"})
        self.assertGreaterEqual(resp.status, 400)
        self.assertFalse(any(k.lower().startswith("access-control-") for k in resp.headers.keys()))

    def test_path_traversal_is_blocked(self):
        (self.client_dir / ".env").write_text(SECRET, encoding="utf-8")
        attempts = ["/../secret.txt", "/js/../../secret.txt", "/%2e%2e/secret.txt", "/js/%2e%2e/%2e%2e/secret.txt",
                    "/js/..%2f..%2fsecret.txt", "/js/..%5c..%5csecret.txt", "/js/link.js", "/.env", "/js/%00.js",
                    "/cutscenes/../save.json", "/cutscenes/..%2fsave.json", "/cutscenes/%2e%2e/secret.txt",
                    f"/{self.root}/secret.txt", "//etc/passwd", "/js/./main.js"]
        for path in attempts:
            with self.subTest(path=path):
                resp = self.request("GET", path, token=None)
                self.assertIn(resp.status, (403, 404))
                self.assertNotIn(SECRET.encode(), resp.body)
                self.assertNotIn(b'"xp"', resp.body)

    def test_symlink_traversal_is_blocked(self):
        try:
            os.symlink(self.root / "secret.txt", self.client_dir / "js" / "link.js")
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows account does not have symlink creation privilege")
            raise
        response = self.request("GET", "/js/link.js", token=None)
        self.assertIn(response.status, (403, 404))
        self.assertNotIn(SECRET.encode(), response.body)

    def test_cutscene_route_only_serves_media(self):
        self.paths.cutscene_dir.mkdir()
        (self.paths.cutscene_dir / "notes.txt").write_text(SECRET, encoding="utf-8")
        (self.paths.cutscene_dir / "L01_still.png").write_bytes(b"\x89PNG")
        self.assertEqual(self.request("GET", "/cutscenes/notes.txt", token=None).status, 404)
        resp = self.request("GET", "/cutscenes/L01_still.png", token=None)
        self.assertEqual((resp.status, resp.headers["Content-Type"], resp.body), (200, "image/png", b"\x89PNG"))

    def test_put_body_is_capped_at_1mb(self):
        self.request("POST", "/api/missions/L01/deploy")
        before = self.mission_file().read_bytes()
        huge = json.dumps({"source": "x" * MAX_BODY})
        resp = self.request("PUT", "/api/missions/L01/source", huge)
        self.assertEqual(resp.status, 413)
        self.assertIn("too large", resp.json()["error"])
        self.assertEqual(self.mission_file().read_bytes(), before)
        big_but_legal = "# " + "x" * (MAX_BODY - 200) + "\n"
        self.assertEqual(self.request("PUT", "/api/missions/L01/source", {"source": big_but_legal}).status, 200)
        self.assertEqual(self.mission_file().read_text(encoding="utf-8"), big_but_legal)

    def test_bad_bodies_are_400(self):
        self.assertEqual(self.request("PUT", "/api/missions/L01/source", "not json").status, 400)
        self.assertEqual(self.request("PUT", "/api/missions/L01/source", {"source": 5}).status, 400)
        self.assertEqual(self.request("PUT", "/api/missions/L01/source", ["source"]).status, 400)
        self.assertEqual(self.request("PUT", "/api/missions/L01/source", b"\xff\xfe").status, 400)

    def test_security_headers(self):
        for path, token in (("/", None), ("/js/main.js", None), ("/api/state", True)):
            headers = self.request("GET", path, token=token).headers
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertEqual(headers["Server"], "NullSector/1.0")

    def test_refuses_to_bind_beyond_loopback(self):
        for host in ("0.0.0.0", "192.168.1.10", "example.com"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                create_server(self.session, host=host, port=0, client_dir=self.client_dir)


class StaticTests(ServerTestCase):
    def test_mime_types_and_cache_policy(self):
        for rel, (content, ctype) in STATIC.items():
            with self.subTest(file=rel):
                resp = self.request("GET", f"/{rel}", token=None)
                self.assertEqual(resp.status, 200)
                self.assertEqual(resp.headers["Content-Type"].split(";")[0], ctype)
                self.assertEqual(resp.headers["Cache-Control"], "no-cache")
                self.assertEqual(resp.body, content.encode())

    def test_etag_revalidation_and_head(self):
        first = self.request("GET", "/js/main.js", token=None)
        etag = first.headers["ETag"]
        again = self.request("GET", "/js/main.js", token=None, headers={"If-None-Match": etag})
        self.assertEqual((again.status, again.body), (304, b""))
        head = self.request("HEAD", "/js/main.js", token=None)
        self.assertEqual((head.status, head.body), (200, b""))
        self.assertEqual(head.headers["Content-Length"], str(len(first.body)))

    def test_byte_ranges_for_video_scrubbing(self):
        resp = self.request("GET", "/media/d.mp4", token=None, headers={"Range": "bytes=1-2"})
        self.assertEqual((resp.status, resp.body, resp.headers["Content-Range"]), (206, b"p4", "bytes 1-2/3"))
        self.assertEqual(self.request("GET", "/media/d.mp4", token=None, headers={"Range": "bytes=9-"}).status, 416)

    def test_missing_files(self):
        self.assertEqual(self.request("GET", "/js/nope.js", token=None).status, 404)
        self.assertEqual(self.request("GET", "/favicon.ico", token=None).status, 204)
        self.assertEqual(self.request("POST", "/js/main.js", token=None).status, 405)


class ApiTests(ServerTestCase):
    def test_payload_shapes_match_the_contract(self):
        resp = self.request("GET", "/api/state")
        self.assertEqual(resp.headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(resp.headers["Cache-Control"], "no-store")
        assert_state(self, resp.json())

        mission = self.request("GET", "/api/missions/L01").json()
        assert_mission(self, mission)
        deployed = self.request("POST", "/api/missions/L01/deploy").json()
        assert_mission(self, deployed)
        self.assertEqual(deployed["source"], STARTER)

        crash = self.request("POST", "/api/missions/L01/hack").json()
        assert_hack_result(self, crash)
        self.assertEqual(crash["report"]["status"], "crash")

        saved = self.request("PUT", "/api/missions/L01/source", {"source": SOLUTION}).json()
        self.assertEqual(set(saved), {"ok", "saved_at"})
        self.assertIs(saved["ok"], True)
        self.assertIsInstance(saved["saved_at"], float)

        win = self.request("POST", "/api/missions/L01/hack").json()
        assert_hack_result(self, win)
        self.assertEqual(win["reward"]["gained"], 150)
        self.assertEqual(win["state"]["profile"]["rank"], "SCRIPT KIDDIE")
        self.assertEqual(win["next"]["status"], "encrypted")

        cutscene = self.request("POST", "/api/missions/L01/cutscene").json()
        self.assertEqual(set(cutscene), {"mission", "state", "reason"})
        self.assertEqual((cutscene["mission"], cutscene["state"]), ("L01", "offline"))

        reset = self.request("POST", "/api/missions/L01/reset").json()
        self.assertEqual(reset, {"source": STARTER})

    def test_errors_are_json_with_status(self):
        cases = [("GET", "/api/missions/L99", 404), ("GET", "/api/missions/L03", 403),
                 ("POST", "/api/missions/L03/hack", 403), ("POST", "/api/missions/L01/cutscene", 403),
                 ("GET", "/api/nope", 404), ("DELETE", "/api/state", 405), ("POST", "/api/state", 405),
                 ("GET", "/api/missions/L01/hack", 405)]
        for method, path, status in cases:
            with self.subTest(method=method, path=path):
                resp = self.request(method, path)
                self.assertEqual(resp.status, status)
                body = resp.json()
                self.assertEqual(set(body), {"error"})
                self.assertIsInstance(body["error"], str)
        self.assertEqual(self.request("POST", "/api/state").headers["Allow"], "GET")

    def test_encrypted_level_after_clear(self):
        self.win()
        self.assertEqual(self.request("POST", "/api/missions/L02/deploy").status, 403)
        self.assertEqual(self.request("GET", "/api/missions/L01").json()["cleared"], True)

    def test_keep_alive_connection_serves_several_requests(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        self.addCleanup(conn.close)
        for _ in range(3):
            conn.request("GET", "/api/state", headers={"X-NS-Token": self.token})
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            resp.read()


class EventStreamTests(ServerTestCase):
    def test_hello_on_connect(self):
        stream = self.sse()
        self.assertEqual(stream.status, 200)
        self.assertTrue(stream.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(stream.headers["cache-control"], "no-store")
        name, data = stream.next()
        self.assertEqual(name, "hello")
        self.assertEqual(set(data), {"server_time"})
        self.assertAlmostEqual(data["server_time"], time.time(), delta=5)

    def test_header_token_also_opens_the_stream(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        self.addCleanup(conn.close)
        conn.request("GET", "/api/events", headers={"X-NS-Token": self.token})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertIn(b"event: hello", resp.fp.readline() + resp.fp.readline() + resp.fp.readline())

    def test_state_event_after_victory(self):
        stream = self.sse()
        stream.next("hello")
        self.win()
        got = {}
        while len(got) < 2:
            name, data = stream.next()
            got.setdefault(name, data)
        state, cutscene = got["state"], got["cutscene"]
        assert_state(self, state)
        self.assertEqual(state["profile"]["xp"], 150)
        self.assertEqual((cutscene["mission"], cutscene["state"], cutscene["stage"]), ("L01", "offline", "still"))
        self.assertIn("error", cutscene)

    def test_watcher_reports_external_edits_but_never_echoes_the_client(self):
        stream = self.sse()
        stream.next("hello")
        settle = 3 * 0.3 + 0.3   # three watcher polls plus its settle time

        self.request("POST", "/api/missions/L01/deploy")          # creates the starter file
        put = "# saved from the browser\nx = 1\n"
        self.assertEqual(self.request("PUT", "/api/missions/L01/source", {"source": put}).status, 200)
        time.sleep(settle)
        self.assertEqual(self.request("POST", "/api/missions/L01/reset").status, 200)
        time.sleep(settle)
        os.utime(self.mission_file(), None)                        # touched, same content: not an edit
        time.sleep(settle)

        external = "# typed in my own editor\ncallsign = 'Nyx'\n"
        self.mission_file().write_text(external, encoding="utf-8")
        _, data = stream.next("file", timeout=5)
        self.assertEqual(set(data), {"mission", "source", "mtime"})
        self.assertEqual(data["mission"], "L01")
        self.assertEqual(data["source"], external, "the first file event must be the external edit, not an echo")
        self.assertAlmostEqual(data["mtime"], self.mission_file().stat().st_mtime, places=3)

        # Once the browser saves that content back, it is not reported again.
        self.request("PUT", "/api/missions/L01/source", {"source": external})
        time.sleep(settle)
        self.assertEqual([e for e in stream.drain() if e[0] == "file"], [])

    def test_slow_clients_are_dropped_not_buffered(self):
        broker = self.server.broker
        sub = broker.subscribe()
        self.assertEqual(broker.client_count, 1)
        for i in range(400):
            broker.publish("state", {"i": i})
        self.assertEqual(broker.client_count, 0)
        self.assertIsNone(sub.queue.get_nowait(), "a dropped client gets the end-of-stream sentinel")

    def test_close_ends_streams_and_threads(self):
        stream = self.sse()
        stream.next("hello")
        self.server.close()
        self.assertTrue(stream.closed.wait(5), "the SSE stream ends when the server shuts down")
        self.assertFalse(self.server.watcher._thread.is_alive())


class CutsceneJobTests(ServerTestCase):
    def test_victory_queues_the_render_and_streams_progress(self):
        client = FakeHiggsfield()
        online_higgsfield(self, client)
        self.session.config["higgsfield"]["video_enabled"] = True
        self.assertTrue(self.request("GET", "/api/state").json()["higgsfield"]["online"])
        self.assertEqual(self.request("POST", "/api/missions/L01/cutscene").status, 403, "locked until cleared")
        stream = self.sse()
        stream.next("hello")
        self.win()

        seen = []
        while not (seen and seen[-1]["stage"] == "video" and seen[-1]["state"] == "done"):
            seen.append(stream.next("cutscene", timeout=10)[1])
        self.assertEqual([(e["stage"], e["state"]) for e in seen],
                         [("still", "rendering"), ("still", "done"), ("video", "rendering"), ("video", "done")])
        self.assertEqual((seen[1]["url"], seen[1]["kind"]), ("/cutscenes/L01_still.png", "image"))
        self.assertEqual((seen[3]["url"], seen[3]["kind"]), ("/cutscenes/L01_cinematic.mp4", "video"))
        self.assertTrue(all(e["mission"] == "L01" for e in seen))

        media = self.request("GET", seen[3]["url"], token=None)
        self.assertEqual((media.status, media.headers["Content-Type"]), (200, "video/mp4"))
        job = self.request("POST", "/api/missions/L01/cutscene").json()
        self.assertEqual(job, {"mission": "L01", "state": "done", "url": "/cutscenes/L01_cinematic.mp4"})
        gallery = self.request("GET", "/api/state").json()["gallery"]
        self.assertEqual([(g["mission"], g["url"], g["kind"]) for g in gallery],
                         [("L01", "/cutscenes/L01_still.png", "image"), ("L01", "/cutscenes/L01_cinematic.mp4", "video")])
        self.assertEqual(len(client.calls), 2, "rendered exactly once")

    def test_failed_render_reports_and_can_be_retried(self):
        client = FakeHiggsfield(fail="still")
        online_higgsfield(self, client)
        stream = self.sse()
        stream.next("hello")
        self.win()
        _, rendering = stream.next("cutscene", timeout=10)
        self.assertEqual(rendering["state"], "rendering")
        _, failed = stream.next("cutscene", timeout=10)
        self.assertEqual((failed["state"], failed["stage"]), ("failed", "still"))
        self.assertIn("quota", failed["error"])
        client.fail = None
        retry = self.request("POST", "/api/missions/L01/cutscene").json()
        self.assertEqual(retry, {"mission": "L01", "state": "queued"})
        _, done = stream.next("cutscene", timeout=10)
        while done["state"] != "done":
            _, done = stream.next("cutscene", timeout=10)
        self.assertEqual(done["url"], "/cutscenes/L01_still.png")


class LifecycleTests(SandboxTestCase):
    def test_port_fallback(self):
        blocker = socket.socket()
        self.addCleanup(blocker.close)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        taken = blocker.getsockname()[1]
        if taken + PORT_FALLBACKS > 65535:
            self.skipTest("ephemeral port too close to the top of the range")
        server = create_server(self.session, port=taken, client_dir=self.root)
        self.addCleanup(server.close)
        self.assertGreater(server.port, taken)
        self.assertLessEqual(server.port, taken + PORT_FALLBACKS)
        self.assertIn(f"localhost:{server.port}", server.allowed_hosts)
        self.assertEqual(server.url, f"http://127.0.0.1:{server.port}/")

    @unittest.skipIf(os.name == "nt", "Popen SIGINT delivery requires POSIX; server.close is tested on Windows")
    def test_serve_shuts_down_cleanly_on_ctrl_c(self):
        script = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(ROOT)!r})
            from pathlib import Path
            from engine.server import serve
            from engine.session import GameSession
            from engine.state import Paths
            session = GameSession(Paths.rooted({str(self.root)!r}))
            serve(session, port=0, open_browser=False, client_dir=Path({str(self.root)!r}),
                  on_ready=lambda url: print(url, flush=True))
            print("closed", flush=True)
        """)
        env = {k: v for k, v in os.environ.items() if k not in ("HF_KEY", "HF_API_KEY", "HF_API_SECRET")}
        proc = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=env)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        url = proc.stdout.readline().strip()
        self.assertRegex(url, r"^http://127\.0\.0\.1:\d+/$")
        port = int(url.rsplit(":", 1)[1].rstrip("/"))
        probe = SSEClient(port, "/api/events?token=wrong")
        self.addCleanup(probe.close)
        self.assertEqual(probe.status, 403)
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate(timeout=10)
        self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(out.strip(), "closed")
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
