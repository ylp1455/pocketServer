from __future__ import annotations

import json
import mimetypes
import os
import platform
import shutil
import socket
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import __version__
from .aria2 import Aria2Client, Aria2Error
from .auth import AdminSession, SessionStore, new_password_record, verify_password
from .config import load_config, save_config
from .media import chunks, safe_media_path, scan_media
from .metadata import MetadataService, SAFE_IMDB_ID
from .requests import MediaRequestStore


class PocketServer:
    def __init__(self, data_dir: Path, host: str, port: int) -> None:
        self.started = time.monotonic()
        self.data_dir = data_dir.expanduser().resolve()
        self.media_dir = self.data_dir / "media"
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.config = load_config(self.data_dir)
        self.host = host
        self.port = port
        self.aria2 = Aria2Client(self.data_dir, self.config)
        self.metadata = MetadataService(self.data_dir, self.config)
        self.requests = MediaRequestStore(self.data_dir)
        self.sessions = SessionStore()
        self.static_dir = Path(__file__).with_name("static")
        self.httpd: ThreadingHTTPServer | None = None

    @property
    def media_roots(self) -> list[Path]:
        return [self.media_dir, self.aria2.download_dir]

    def run(self, open_browser: bool = True) -> None:
        self.aria2.start()
        app = self

        class Handler(PocketRequestHandler):
            server_app = app

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.httpd.daemon_threads = True
        local_ip = discover_ip()
        print(f"PocketServer {__version__}")
        print(f"Data: {self.data_dir}")
        print(f"Local: http://127.0.0.1:{self.port}")
        print(f"Network: http://{local_ip}:{self.port}")
        print(f"Admin: http://{local_ip}:{self.port}/admin")
        if not self.aria2.available():
            print("Warning: aria2c was not found. Install aria2 to enable downloads.")
        if open_browser and self.host in {"127.0.0.1", "localhost"}:
            threading.Timer(0.5, webbrowser.open, args=(f"http://127.0.0.1:{self.port}",)).start()
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping PocketServer...")
        finally:
            self.aria2.stop()
            self.metadata.close()
            self.httpd.server_close()


class PocketRequestHandler(BaseHTTPRequestHandler):
    server_app: PocketServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/auth/session":
            self._auth_session()
        elif parsed.path == "/api/status":
            if not self._require_admin():
                return
            self._status()
        elif parsed.path == "/api/downloads":
            if not self._require_admin():
                return
            self._downloads()
        elif parsed.path == "/api/requests":
            if not self._require_admin():
                return
            self._json({"items": self.server_app.requests.all()})
        elif parsed.path == "/api/media":
            self._media_list()
        elif parsed.path == "/media":
            query = urllib.parse.parse_qs(parsed.query)
            self._stream_media(query.get("path", [""])[0])
        elif parsed.path.startswith("/poster/"):
            self._serve_poster(parsed.path.removeprefix("/poster/").removesuffix(".jpg"))
        else:
            self._static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        try:
            if parsed.path == "/api/auth/login":
                self._login()
                return
            if parsed.path == "/api/requests":
                item = self.server_app.requests.create(self._json_body())
                self._json({"request": item}, HTTPStatus.CREATED)
                return
            session = self._require_admin(csrf=True)
            if not session:
                return
            if parsed.path == "/api/auth/logout":
                self.server_app.sessions.remove(session.token)
                self._json(
                    {"ok": True},
                    extra_headers={"Set-Cookie": "pocket_admin=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"},
                )
            elif parsed.path == "/api/auth/password":
                self._change_password(session)
            elif parsed.path == "/api/downloads/uri":
                payload = self._json_body()
                uri = str(payload.get("uri", "")).strip()
                if not uri.startswith(("http://", "https://", "magnet:?")):
                    self._json({"error": "Enter an HTTP, HTTPS, or magnet link."}, HTTPStatus.BAD_REQUEST)
                    return
                self._ensure_space()
                gid = self.server_app.aria2.add_uri(uri)
                self._json({"gid": gid}, HTTPStatus.CREATED)
            elif parsed.path == "/api/downloads/torrent":
                self._ensure_space()
                length = min(int(self.headers.get("Content-Length", "0")), 8 * 1024 * 1024)
                if length <= 0:
                    self._json({"error": "The torrent file is empty."}, HTTPStatus.BAD_REQUEST)
                    return
                torrent = self.rfile.read(length)
                gid = self.server_app.aria2.add_torrent(torrent)
                self._json({"gid": gid}, HTTPStatus.CREATED)
            elif parsed.path == "/api/settings/schedule":
                payload = self._json_body()
                enabled = bool(payload.get("enabled", False))
                start = str(payload.get("start", "00:00"))
                end = str(payload.get("end", "06:00"))
                for value in (start, end):
                    try:
                        datetime.strptime(value, "%H:%M")
                    except ValueError as exc:
                        raise ValueError("Times must use the HH:MM format.") from exc
                window = {"enabled": enabled, "start": start, "end": end}
                self.server_app.config["download_window"] = window
                save_config(self.server_app.data_dir, self.server_app.config)
                self.server_app.aria2.schedule_changed()
                self._json({"schedule": window, "active_now": self.server_app.aria2.schedule_active_now()})
            elif parsed.path == "/api/settings/metadata":
                payload = self._json_body()
                supplied_key = str(payload.get("api_key", "")).strip()
                enabled = bool(payload.get("enabled", False) or supplied_key)
                settings = self.server_app.config.setdefault("metadata", {})
                previous_key = str(settings.get("api_key", ""))
                previous_enabled = bool(settings.get("enabled", False))
                if supplied_key:
                    if len(supplied_key) > 128:
                        raise ValueError("The OMDb API key is too long.")
                    settings["api_key"] = supplied_key
                if enabled and not (settings.get("api_key") or os.environ.get("OMDB_API_KEY")):
                    raise ValueError("Enter an OMDb API key before enabling metadata.")
                settings["enabled"] = enabled
                settings["provider"] = "omdb"
                save_config(self.server_app.data_dir, self.server_app.config)
                if (supplied_key and supplied_key != previous_key) or (enabled and not previous_enabled):
                    self.server_app.metadata.refresh()
                if enabled:
                    self.server_app.metadata.enrich(scan_media(*self.server_app.media_roots))
                self._json({"metadata": self.server_app.metadata.stats()})
            elif parsed.path == "/api/metadata/refresh":
                self.server_app.metadata.refresh()
                self._json({"ok": True})
            elif parsed.path.startswith("/api/requests/"):
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 4 or parts[3] != "status":
                    raise ValueError("Invalid request action URL.")
                payload = self._json_body()
                item = self.server_app.requests.set_status(parts[2], str(payload.get("status", "")))
                self._json({"request": item})
            elif parsed.path.startswith("/api/downloads/"):
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 4:
                    raise ValueError("invalid action URL")
                _, _, gid, action = parts
                result = self.server_app.aria2.action(gid, action)
                self._json({"result": result})
            else:
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except (Aria2Error, ValueError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _login(self) -> None:
        payload = self._json_body()
        username = str(payload.get("username", ""))
        password = str(payload.get("password", ""))
        auth_config = self.server_app.config["auth"]
        if username != str(auth_config.get("username", "admin")) or not verify_password(password, auth_config):
            time.sleep(0.35)
            self._json({"error": "Invalid username or password."}, HTTPStatus.UNAUTHORIZED)
            return
        session = self.server_app.sessions.create()
        self._json(
            {
                "authenticated": True,
                "username": auth_config.get("username", "admin"),
                "csrf_token": session.csrf_token,
                "must_change_password": bool(auth_config.get("must_change_password", False)),
            },
            extra_headers={
                "Set-Cookie": "pocket_admin=" + session.token + "; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400"
            },
        )

    def _auth_session(self) -> None:
        session = self._current_session()
        if not session:
            self._json({"authenticated": False})
            return
        auth_config = self.server_app.config["auth"]
        self._json(
            {
                "authenticated": True,
                "username": auth_config.get("username", "admin"),
                "csrf_token": session.csrf_token,
                "must_change_password": bool(auth_config.get("must_change_password", False)),
            }
        )

    def _change_password(self, session: AdminSession) -> None:
        payload = self._json_body()
        current = str(payload.get("current_password", ""))
        new = str(payload.get("new_password", ""))
        if not verify_password(current, self.server_app.config["auth"]):
            self._json({"error": "The current password is incorrect."}, HTTPStatus.BAD_REQUEST)
            return
        if len(new) < 8:
            self._json({"error": "The new password must contain at least 8 characters."}, HTTPStatus.BAD_REQUEST)
            return
        if hmac_compare(current, new):
            self._json({"error": "Choose a password different from the current password."}, HTTPStatus.BAD_REQUEST)
            return
        self.server_app.config["auth"] = new_password_record(new, must_change=False)
        save_config(self.server_app.data_dir, self.server_app.config)
        self.server_app.sessions.keep_only(session.token)
        self._json({"ok": True, "must_change_password": False})

    def _current_session(self) -> AdminSession | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            return None
        morsel = cookie.get("pocket_admin")
        return self.server_app.sessions.get(morsel.value if morsel else None)

    def _require_admin(self, csrf: bool = False) -> AdminSession | None:
        session = self._current_session()
        if not session:
            self.close_connection = True
            self._json(
                {"error": "Admin authentication is required."},
                HTTPStatus.UNAUTHORIZED,
                extra_headers={"Connection": "close"},
            )
            return None
        if csrf and not hmac_compare(self.headers.get("X-CSRF-Token", ""), session.csrf_token):
            self.close_connection = True
            self._json(
                {"error": "The security token is invalid. Refresh the admin page."},
                HTTPStatus.FORBIDDEN,
                extra_headers={"Connection": "close"},
            )
            return None
        return session

    def _status(self) -> None:
        disk = shutil.disk_usage(self.server_app.data_dir)
        memory = memory_info()
        stats: dict[str, Any] = {}
        aria2_available = self.server_app.aria2.available()
        if aria2_available:
            try:
                stats = self.server_app.aria2.global_stats()
            except Aria2Error:
                aria2_available = False
        self._json(
            {
                "name": self.server_app.config["server_name"],
                "version": __version__,
                "hostname": socket.gethostname(),
                "platform": platform.system(),
                "python": platform.python_version(),
                "uptime_seconds": int(time.monotonic() - self.server_app.started),
                "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
                "memory": memory,
                "aria2_available": aria2_available,
                "download_speed": int(stats.get("downloadSpeed", 0)),
                "upload_speed": int(stats.get("uploadSpeed", 0)),
                "active_downloads": int(stats.get("numActive", 0)),
                "waiting_downloads": int(stats.get("numWaiting", 0)),
                "schedule": self.server_app.config["download_window"],
                "schedule_active_now": self.server_app.aria2.schedule_active_now(),
                "metadata": self.server_app.metadata.stats(),
                "pending_requests": self.server_app.requests.pending_count(),
            }
        )

    def _downloads(self) -> None:
        if not self.server_app.aria2.available():
            self._json({"available": False, "items": []})
            return
        try:
            self._json({"available": True, "items": self.server_app.aria2.downloads()})
        except Aria2Error as exc:
            self._json({"available": False, "items": [], "error": str(exc)})

    def _media_list(self) -> None:
        items = scan_media(*self.server_app.media_roots)
        self.server_app.metadata.enrich(items)
        for item in items:
            item["url"] = "/media?" + urllib.parse.urlencode({"path": item.pop("path")})
        self._json({"items": items})

    def _serve_poster(self, imdb_id: str) -> None:
        if not SAFE_IMDB_ID.fullmatch(imdb_id):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        path = self.server_app.metadata.poster_path(imdb_id)
        if path is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=604800")
        self.end_headers()
        self.wfile.write(data)

    def _stream_media(self, encoded_path: str) -> None:
        path = safe_media_path(encoded_path, self.server_app.media_roots)
        if path is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        size = path.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            try:
                first, last = range_header.removeprefix("bytes=").split("-", 1)
                if first:
                    start = int(first)
                    end = min(int(last), size - 1) if last else size - 1
                elif last:
                    start = max(0, size - int(last))
                if start > end or start >= size:
                    raise ValueError
                status = HTTPStatus.PARTIAL_CONTENT
            except ValueError:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{urllib.parse.quote(path.name)}")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            for data in chunks(path, start, length):
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _static(self, request_path: str) -> None:
        if request_path in {"", "/"}:
            name = "client.html"
        elif request_path.rstrip("/") == "/admin":
            name = "index.html"
        else:
            name = request_path.lstrip("/")
        candidate = (self.server_app.static_dir / name).resolve()
        try:
            candidate.relative_to(self.server_app.static_dir.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            candidate = self.server_app.static_dir / "index.html"
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache" if candidate.name == "index.html" else "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self) -> dict[str, Any]:
        length = min(int(self.headers.get("Content-Length", "0")), 1024 * 1024)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _json(
        self,
        body: Any,
        status: HTTPStatus = HTTPStatus.OK,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _ensure_space(self) -> None:
        free_mb = shutil.disk_usage(self.server_app.data_dir).free // (1024 * 1024)
        minimum = int(self.server_app.config["minimum_free_mb"])
        if free_mb < minimum:
            raise ValueError(f"Only {free_mb} MB is free; at least {minimum} MB is required.")

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.path.startswith("/api/") and self.command == "GET":
            return
        super().log_message(fmt, *args)


def discover_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def hmac_compare(first: str, second: str) -> bool:
    """Constant-time string comparison for credentials and request tokens."""
    import hmac

    return hmac.compare_digest(first.encode("utf-8"), second.encode("utf-8"))


def memory_info() -> dict[str, int] | None:
    if sys.platform.startswith("linux"):
        try:
            values: dict[str, int] = {}
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0]) * 1024
            total = values["MemTotal"]
            available = values.get("MemAvailable", values.get("MemFree", 0))
            return {"total": total, "used": total - available, "free": available}
        except (OSError, KeyError, ValueError):
            return None
    return None
