"""Opt-in local parent companion with one-use pairing and UI-thread commands."""

import hmac
import ipaddress
import json
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any

from .storage import Store, encode


class ParentBridge:
    def __init__(self) -> None:
        self.commands: Queue[tuple[dict[str, Any], Queue[dict[str, Any]], Callable[[], bool]]] = (
            Queue(maxsize=32)
        )
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {}
        self.export_path: Path | None = None
        self.url = ""
        self.code = ""
        self.rotate: Callable[[], str] | None = None

    def publish(self, state: dict[str, Any], export_path: Path | None) -> None:
        with self.lock:
            self.state, self.export_path = state, export_path

    def process(self, handler: Callable[[dict[str, Any]], None]) -> None:
        for _ in range(8):
            try:
                command, reply, authorized = self.commands.get_nowait()
            except Empty:
                return
            try:
                if not authorized():
                    raise ValueError("Session expired or revoked before execution")
                handler(command)
                reply.put({"ok": True})
            except (ValueError, OSError, sqlite3.Error):
                reply.put(
                    {"ok": False, "error": "Action could not be saved or is no longer available."}
                )


class ParentServer:
    def __init__(
        self, bridge: ParentBridge, store: Store, host: str = "127.0.0.1", port: int = 8765
    ):
        address = ipaddress.ip_address(host)
        if (
            address.version != 4
            or address.is_unspecified
            or address.is_multicast
            or not (address.is_private or address.is_loopback)
        ):
            raise ValueError("Use a specific local IPv4 address, not 0.0.0.0 or a public address.")
        self.bridge, self.store = bridge, store
        self.lock = threading.Lock()
        self.sessions: dict[str, float] = {}
        self.code, self.expires, self.attempts = "", 0.0, 0
        self.server = ThreadingHTTPServer((host, port), self._handler())
        self.server.daemon_threads = True
        self.authority = f"{host}:{self.server.server_port}"
        bridge.url = f"http://{self.authority}"
        bridge.rotate = self.rotate_pairing
        self.rotate_pairing()
        self.thread = threading.Thread(
            target=self.server.serve_forever, name="quest-parent", daemon=True
        )

    def rotate_pairing(self) -> str:
        with self.lock:
            self.code = f"{secrets.randbelow(1000000):06}"
            self.expires, self.attempts = time.monotonic() + 300, 0
            self.sessions.clear()
            self.bridge.code = self.code
            return self.code

    def start(self) -> None:
        self.thread.start()

    def session_valid(self, token: str) -> bool:
        with self.lock:
            return self.sessions.get(token, 0) > time.monotonic()

    def close(self) -> None:
        if self.thread.is_alive():
            self.server.shutdown()
            self.thread.join()
        self.server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(10)

            def log_message(self, format: str, *args: object) -> None:
                pass  # Never log pairing codes, cookies, request bodies or photos.

            def send_body(
                self,
                status: int,
                body: bytes,
                content_type: str = "application/json",
                cookie: str | None = None,
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                )
                if cookie:
                    self.send_header("Set-Cookie", cookie)
                self.end_headers()
                self.wfile.write(body)

            def fail(self, status: int, message: str) -> None:
                self.send_body(status, json.dumps({"error": message}).encode())

            def valid_host(self) -> bool:
                if self.headers.get("Host") != owner.authority:
                    self.fail(403, "Unrecognized host")
                    return False
                return True

            def authenticated(self) -> bool:
                try:
                    cookie = SimpleCookie(self.headers.get("Cookie", ""))
                    token = cookie["quest_session"].value if "quest_session" in cookie else ""
                except Exception:
                    token = ""
                valid = owner.session_valid(token)
                self.session_token = token
                if not valid:
                    self.fail(401, "Pair this browser first")
                return valid

            def do_GET(self) -> None:
                if not self.valid_host():
                    return
                assets = {
                    "/": ("parent.html", "text/html; charset=utf-8"),
                    "/parent.js": ("parent.js", "text/javascript; charset=utf-8"),
                    "/parent.css": ("parent.css", "text/css; charset=utf-8"),
                }
                if self.path in assets:
                    name, content_type = assets[self.path]
                    self.send_body(
                        200, (Path(__file__).parent / "web" / name).read_bytes(), content_type
                    )
                    return
                if not self.authenticated():
                    return
                with owner.bridge.lock:
                    state, export_path = owner.bridge.state, owner.bridge.export_path
                if self.path == "/api/state":
                    self.send_body(200, json.dumps(state).encode())
                elif self.path.startswith("/api/photo/"):
                    photo_id = self.path.removeprefix("/api/photo/")
                    if photo_id not in {p["id"] for p in state.get("photos", [])}:
                        self.fail(404, "Photo unavailable")
                        return
                    try:
                        picture = owner.store.image(photo_id, True)
                        picture.thumbnail((320, 240))
                        self.send_body(200, encode(picture), "image/png")
                    except (OSError, ValueError):
                        self.fail(404, "Photo unavailable")
                elif self.path == "/api/export" and export_path is not None:
                    try:
                        with export_path.open("rb") as source:
                            self.send_response(200)
                            self.send_header("Content-Type", "application/zip")
                            self.send_header(
                                "Content-Disposition",
                                'attachment; filename="pocket-quest-photos.zip"',
                            )
                            self.send_header("Cache-Control", "no-store")
                            self.send_header("Content-Length", str(export_path.stat().st_size))
                            self.end_headers()
                            while chunk := source.read(1024 * 1024):
                                self.wfile.write(chunk)
                    except OSError:
                        self.close_connection = True
                else:
                    self.fail(404, "Not found")

            def do_POST(self) -> None:
                if not self.valid_host():
                    return
                if self.headers.get("Origin") != owner.bridge.url:
                    self.fail(403, "Open the companion directly before making changes")
                    return
                if self.headers.get("Content-Type") != "application/json":
                    self.fail(415, "JSON required")
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 4096:
                        raise ValueError
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError
                except (ValueError, UnicodeError):
                    self.fail(400, "Invalid request")
                    return
                if self.path == "/api/pair":
                    with owner.lock:
                        owner.attempts += 1
                        candidate = data.get("code")
                        valid = (
                            isinstance(candidate, str)
                            and candidate.isascii()
                            and owner.attempts <= 5
                            and bool(owner.code)
                            and time.monotonic() < owner.expires
                            and hmac.compare_digest(candidate, owner.code)
                        )
                        if valid:
                            token = secrets.token_urlsafe(32)
                            owner.sessions[token] = time.monotonic() + 12 * 3600
                            owner.code, owner.bridge.code = "", ""
                    if not valid:
                        self.fail(
                            403,
                            "Pairing failed. Get a new code on the device after five attempts or five minutes.",
                        )
                    else:
                        self.send_body(
                            200,
                            b'{"ok":true}',
                            cookie=f"quest_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200",
                        )
                    return
                if not self.authenticated():
                    return
                if self.path != "/api/action":
                    self.fail(404, "Not found")
                    return
                reply: Queue[dict[str, Any]] = Queue(maxsize=1)
                token = self.session_token

                def still_authorized() -> bool:
                    return owner.session_valid(token)

                try:
                    owner.bridge.commands.put_nowait((data, reply, still_authorized))
                    result = reply.get(timeout=5)
                except (Full, Empty):
                    self.fail(503, "Device busy. Check the current state before trying again.")
                    return
                self.send_body(200 if result["ok"] else 400, json.dumps(result).encode())

        return Handler
