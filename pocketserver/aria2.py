from __future__ import annotations

import base64
import json
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


class Aria2Error(RuntimeError):
    pass


class Aria2Client:
    def __init__(self, data_dir: Path, config: dict[str, Any]) -> None:
        self.data_dir = data_dir
        self.download_dir = data_dir / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.port = int(config["aria2"]["rpc_port"])
        self.secret = str(config["aria2"]["rpc_secret"])
        self.url = f"http://127.0.0.1:{self.port}/jsonrpc"
        self.process: subprocess.Popen[bytes] | None = None
        self._request_id = 0
        self._scheduler_stop = threading.Event()
        self._scheduler_wake = threading.Event()

    def start(self) -> None:
        if self.available():
            self._start_scheduler()
            return
        executable = shutil.which("aria2c")
        if executable is None:
            self._start_scheduler()
            return
        session = self.data_dir / "aria2.session"
        session.touch(exist_ok=True)
        log = self.data_dir / "aria2.log"
        args = [
            executable,
            "--enable-rpc=true",
            "--rpc-listen-all=false",
            f"--rpc-listen-port={self.port}",
            f"--rpc-secret={self.secret}",
            f"--dir={self.download_dir}",
            f"--input-file={session}",
            f"--save-session={session}",
            "--save-session-interval=30",
            "--continue=true",
            "--auto-file-renaming=false",
            "--allow-overwrite=false",
            f"--max-concurrent-downloads={int(self.config['aria2']['max_concurrent_downloads'])}",
            f"--seed-time={int(self.config['aria2']['seed_time_minutes'])}",
            f"--log={log}",
            "--log-level=notice",
        ]
        self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            if self.available():
                break
            time.sleep(0.1)
        self._start_scheduler()

    def stop(self) -> None:
        self._scheduler_stop.set()
        self._scheduler_wake.set()
        if self.process and self.process.poll() is None:
            try:
                self.call("aria2.saveSession")
                self.call("aria2.shutdown")
                self.process.wait(timeout=3)
            except (Aria2Error, subprocess.TimeoutExpired):
                self.process.terminate()

    def call(self, method: str, *params: Any) -> Any:
        self._request_id += 1
        auth_params: list[Any] = [f"token:{self.secret}", *params]
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": auth_params}
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                body = json.load(response)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise Aria2Error("aria2c is not available") from exc
        if "error" in body:
            raise Aria2Error(body["error"].get("message", "aria2 request failed"))
        return body.get("result")

    def available(self) -> bool:
        try:
            self.call("aria2.getVersion")
            return True
        except Aria2Error:
            return False

    def add_uri(self, uri: str) -> str:
        return str(self.call("aria2.addUri", [uri], self._download_options()))

    def add_torrent(self, torrent: bytes) -> str:
        encoded = base64.b64encode(torrent).decode("ascii")
        return str(self.call("aria2.addTorrent", encoded, [], self._download_options()))

    def schedule_changed(self) -> None:
        """Wake the scheduler so settings take effect without a polling delay."""
        self._scheduler_wake.set()

    def schedule_active_now(self) -> bool:
        window = self.config.get("download_window", {})
        return bool(window.get("enabled")) and self._inside_window(
            str(window.get("start", "00:00")), str(window.get("end", "06:00"))
        )

    def _download_options(self) -> dict[str, str]:
        options = {"dir": str(self.download_dir)}
        window = self.config.get("download_window", {})
        if window.get("enabled") and not self.schedule_active_now():
            options["pause"] = "true"
        return options

    def downloads(self) -> list[dict[str, Any]]:
        keys = [
            "gid", "status", "totalLength", "completedLength", "downloadSpeed",
            "uploadSpeed", "files", "bittorrent", "errorMessage", "connections",
        ]
        active = self.call("aria2.tellActive", keys)
        waiting = self.call("aria2.tellWaiting", 0, 100, keys)
        stopped = self.call("aria2.tellStopped", 0, 50, keys)
        return [self._normalize(item) for item in [*active, *waiting, *stopped]]

    def global_stats(self) -> dict[str, Any]:
        return self.call("aria2.getGlobalStat")

    def action(self, gid: str, action: str) -> Any:
        methods = {
            "pause": "aria2.pause",
            "resume": "aria2.unpause",
            "remove": "aria2.remove",
            "remove-result": "aria2.removeDownloadResult",
        }
        if action not in methods:
            raise Aria2Error("unsupported download action")
        try:
            return self.call(methods[action], gid)
        except Aria2Error:
            if action == "remove":
                return self.call("aria2.removeDownloadResult", gid)
            raise

    @staticmethod
    def _normalize(item: dict[str, Any]) -> dict[str, Any]:
        files = item.get("files", [])
        name = "Unknown download"
        if files:
            path = files[0].get("path", "")
            name = Path(path).name or path or name
        info = item.get("bittorrent", {}).get("info", {})
        if info.get("name"):
            name = info["name"]
        total = int(item.get("totalLength", 0))
        completed = int(item.get("completedLength", 0))
        speed = int(item.get("downloadSpeed", 0))
        return {
            "gid": item.get("gid"),
            "name": name,
            "status": item.get("status", "unknown"),
            "total": total,
            "completed": completed,
            "progress": round((completed / total * 100), 1) if total else 0,
            "download_speed": speed,
            "upload_speed": int(item.get("uploadSpeed", 0)),
            "connections": int(item.get("connections", 0)),
            "eta_seconds": max(0, (total - completed) // speed) if speed else None,
            "torrent": bool(item.get("bittorrent")),
            "error": item.get("errorMessage", ""),
        }

    def _start_scheduler(self) -> None:
        thread = threading.Thread(target=self._scheduler_loop, name="download-scheduler", daemon=True)
        thread.start()

    def _scheduler_loop(self) -> None:
        previous: bool | None = None
        was_enabled = False
        while not self._scheduler_stop.is_set():
            window = self.config.get("download_window", {})
            enabled = bool(window.get("enabled"))
            available = self.available()
            if not enabled or not available:
                if was_enabled and available:
                    try:
                        self.call("aria2.unpauseAll")
                    except Aria2Error:
                        pass
                previous = None
            else:
                allowed = self.schedule_active_now()
                if allowed != previous:
                    try:
                        self.call("aria2.unpauseAll" if allowed else "aria2.pauseAll")
                        previous = allowed
                    except Aria2Error:
                        pass
            was_enabled = enabled
            self._scheduler_wake.wait(30)
            self._scheduler_wake.clear()

    @staticmethod
    def _inside_window(start: str, end: str) -> bool:
        now = datetime.now().strftime("%H:%M")
        return Aria2Client._time_in_window(now, start, end)

    @staticmethod
    def _time_in_window(now: str, start: str, end: str) -> bool:
        if start == end:
            return True
        if start <= end:
            return start <= now < end
        return now >= start or now < end
