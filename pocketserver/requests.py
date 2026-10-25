from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUEST_TYPES = {"movie", "series"}
REQUEST_STATUSES = {"pending", "approved", "available", "declined"}


class MediaRequestStore:
    """Thread-safe, JSON-backed request queue for small home servers."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "requests.json"
        self._lock = threading.Lock()
        self._items = self._load()

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in reversed(self._items)]

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = str(payload.get("title", "")).strip()
        media_type = str(payload.get("type", "movie")).strip().lower()
        year = str(payload.get("year", "")).strip()
        requested_by = str(payload.get("requested_by", "")).strip()
        notes = str(payload.get("notes", "")).strip()
        if not title or len(title) > 120:
            raise ValueError("Enter a title containing no more than 120 characters.")
        if media_type not in REQUEST_TYPES:
            raise ValueError("Choose movie or series.")
        if year and (not year.isdigit() or len(year) != 4 or not 1888 <= int(year) <= 2100):
            raise ValueError("Enter a valid four-digit year.")
        if len(requested_by) > 60:
            raise ValueError("Your name must contain no more than 60 characters.")
        if len(notes) > 500:
            raise ValueError("Notes must contain no more than 500 characters.")
        with self._lock:
            duplicate = next(
                (
                    item
                    for item in self._items
                    if item["status"] in {"pending", "approved"}
                    and item["title"].casefold() == title.casefold()
                    and item.get("year", "") == year
                ),
                None,
            )
            if duplicate:
                raise ValueError("This title has already been requested.")
            item = {
                "id": secrets.token_hex(8),
                "title": title,
                "type": media_type,
                "year": year,
                "requested_by": requested_by,
                "notes": notes,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            self._items.append(item)
            self._save_locked()
            return dict(item)

    def set_status(self, request_id: str, status: str) -> dict[str, Any]:
        status = status.strip().lower()
        if status not in REQUEST_STATUSES:
            raise ValueError("Invalid request status.")
        with self._lock:
            item = next((value for value in self._items if value["id"] == request_id), None)
            if item is None:
                raise ValueError("Request not found.")
            item["status"] = status
            item["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._save_locked()
            return dict(item)

    def pending_count(self) -> int:
        with self._lock:
            return sum(item["status"] == "pending" for item in self._items)

    def _load(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save_locked(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._items, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
