from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from .auth import new_password_record


DEFAULT_CONFIG: dict[str, Any] = {
    "server_name": "PocketServer",
    "minimum_free_mb": 512,
    "download_window": {"enabled": False, "start": "00:00", "end": "06:00"},
    "aria2": {
        "rpc_port": 6800,
        "rpc_secret": "",
        "max_concurrent_downloads": 2,
        "seed_time_minutes": 0,
    },
    "auth": {},
}


def _merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(data_dir: Path) -> dict[str, Any]:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "config.json"
    saved: dict[str, Any] = {}
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
    config = _merge(DEFAULT_CONFIG, saved)
    if not config["aria2"]["rpc_secret"]:
        config["aria2"]["rpc_secret"] = secrets.token_urlsafe(24)
    auth = config.get("auth", {})
    if not auth.get("password_hash") or not auth.get("password_salt"):
        config["auth"] = new_password_record("admin", must_change=True)
    save_config(data_dir, config)
    return config


def save_config(data_dir: Path, config: dict[str, Any]) -> None:
    """Persist configuration without leaving a partially written JSON file."""
    path = data_dir / "config.json"
    temporary = data_dir / "config.json.tmp"
    temporary.write_text(json.dumps(config, indent=2), encoding="utf-8")
    temporary.replace(path)
