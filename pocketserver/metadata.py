from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


QUALITY_TOKENS = re.compile(
    r"\b(?:480p|720p|1080p|2160p|4k|uhd|bluray|blu-ray|brrip|webrip|web-dl|hdrip|dvdrip|"
    r"xvid|x264|x265|h264|h265|hevc|aac|dts|proper|repack|extended|remastered)\b",
    re.IGNORECASE,
)
YEAR_TOKEN = re.compile(r"\b((?:19|20)\d{2})\b")
SAFE_IMDB_ID = re.compile(r"^tt\d{5,12}$")


def title_from_filename(filename: str) -> tuple[str, str | None]:
    stem = Path(filename).stem
    year_match = YEAR_TOKEN.search(stem)
    year = year_match.group(1) if year_match else None
    if year_match:
        stem = stem[: year_match.start()]
    stem = re.sub(r"[._\-\[\]()]+", " ", stem)
    stem = QUALITY_TOKENS.sub(" ", stem)
    title = re.sub(r"\s+", " ", stem).strip()
    return title or Path(filename).stem, year


class MetadataService:
    """Small, single-worker OMDb metadata cache for low-memory devices."""

    def __init__(self, data_dir: Path, config: dict[str, Any]) -> None:
        self.data_dir = data_dir
        self.config = config
        self.cache_path = data_dir / "metadata.json"
        self.poster_dir = data_dir / "posters"
        self.poster_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._pending: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="metadata")
        self._cache = self._load_cache()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def configured(self) -> bool:
        settings = self.config.get("metadata", {})
        return bool(settings.get("enabled") and self._api_key())

    def stats(self) -> dict[str, Any]:
        with self._lock:
            matched = sum(1 for value in self._cache.values() if not value.get("not_found"))
            pending = len(self._pending)
        return {
            "provider": "OMDb",
            "enabled": bool(self.config.get("metadata", {}).get("enabled", False)),
            "configured": bool(self._api_key()),
            "cached_titles": matched,
            "pending": pending,
        }

    def enrich(self, items: list[dict[str, object]]) -> None:
        for item in items:
            title, year = title_from_filename(str(item.get("filename", item.get("name", ""))))
            key = self._cache_key(title, year)
            with self._lock:
                record = self._cache.get(key)
            item["metadata"] = None if not record or record.get("not_found") else dict(record)
            item["lookup_title"] = title
            if record is None and self.configured():
                self._schedule(key, title, year)

    def poster_path(self, imdb_id: str) -> Path | None:
        if not SAFE_IMDB_ID.fullmatch(imdb_id):
            return None
        path = self.poster_dir / f"{imdb_id}.jpg"
        return path if path.is_file() else None

    def refresh(self) -> None:
        with self._lock:
            self._cache.clear()
            self._save_cache_locked()

    def _schedule(self, key: str, title: str, year: str | None) -> None:
        with self._lock:
            if key in self._pending:
                return
            self._pending.add(key)
        self._executor.submit(self._fetch_and_store, key, title, year)

    def _fetch_and_store(self, key: str, title: str, year: str | None) -> None:
        try:
            query = {"apikey": self._api_key(), "t": title, "plot": "full", "r": "json"}
            if year:
                query["y"] = year
            url = "https://www.omdbapi.com/?" + urllib.parse.urlencode(query)
            request = urllib.request.Request(url, headers={"User-Agent": "PocketServer/0.2"})
            with urllib.request.urlopen(request, timeout=12) as response:
                payload = json.load(response)
            if payload.get("Response") != "True":
                record: dict[str, Any] = {"not_found": True, "lookup_title": title}
            else:
                record = self._normalize(payload)
                poster = record.get("poster_remote")
                imdb_id = record.get("imdb_id")
                if poster and imdb_id:
                    self._download_poster(str(poster), str(imdb_id))
                    if self.poster_path(str(imdb_id)):
                        record["poster"] = f"/poster/{imdb_id}.jpg"
            with self._lock:
                self._cache[key] = record
                self._save_cache_locked()
        except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
            # Network errors are not cached so a later library refresh can retry.
            pass
        finally:
            with self._lock:
                self._pending.discard(key)

    @staticmethod
    def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
        def value(name: str) -> str | None:
            result = str(payload.get(name, "")).strip()
            return result if result and result != "N/A" else None

        imdb_id = value("imdbID")
        poster = value("Poster")
        return {
            "title": value("Title"),
            "year": value("Year"),
            "rated": value("Rated"),
            "runtime": value("Runtime"),
            "genres": [part.strip() for part in (value("Genre") or "").split(",") if part.strip()],
            "director": value("Director"),
            "actors": [part.strip() for part in (value("Actors") or "").split(",") if part.strip()],
            "plot": value("Plot"),
            "imdb_rating": value("imdbRating"),
            "imdb_votes": value("imdbVotes"),
            "imdb_id": imdb_id,
            "type": value("Type"),
            "poster_remote": poster if poster and poster.startswith("https://") else None,
            "poster": poster if poster and poster.startswith("https://") else None,
        }

    def _download_poster(self, url: str, imdb_id: str) -> None:
        if not SAFE_IMDB_ID.fullmatch(imdb_id) or not url.startswith("https://"):
            return
        destination = self.poster_dir / f"{imdb_id}.jpg"
        if destination.exists():
            return
        request = urllib.request.Request(url, headers={"User-Agent": "PocketServer/0.2"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                content_type = response.headers.get("Content-Type", "")
                data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024 or not content_type.startswith("image/"):
                return
            temporary = destination.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(destination)
        except (OSError, urllib.error.URLError):
            return

    def _api_key(self) -> str:
        return os.environ.get("OMDB_API_KEY", str(self.config.get("metadata", {}).get("api_key", ""))).strip()

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_cache_locked(self) -> None:
        temporary = self.cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.cache_path)

    @staticmethod
    def _cache_key(title: str, year: str | None) -> str:
        return f"{title.casefold()}|{year or ''}"
