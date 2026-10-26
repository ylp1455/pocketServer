from __future__ import annotations

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any


DEFAULT_BASE_URL = "https://yts.vg"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MOVIE_PATH = re.compile(r"^/movie/[a-z0-9][a-z0-9-]{0,180}$")
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
RATING = re.compile(r"\b(\d(?:\.\d)?)\s*/\s*10\b")
QUALITY = re.compile(
    r"\b(480p|720p|1080p|2160p)(?:\s+(x264|x265|hevc|web|bluray))?",
    re.IGNORECASE,
)
BTIH = re.compile(r"(?:^|[?&])xt=urn:btih:(?:[a-f0-9]{40}|[a-z2-7]{32})(?:&|$)", re.IGNORECASE)
VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class YtsError(RuntimeError):
    pass


class _SearchParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: list[dict[str, Any]] = []
        self._item: dict[str, Any] | None = None
        self._depth = 0
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if self._item is not None:
            if tag not in VOID_ELEMENTS:
                self._depth += 1
            if tag == "img" and not self._item.get("poster"):
                source = values.get("src") or values.get("data-src")
                if source:
                    self._item["poster"] = urllib.parse.urljoin(self.base_url, source)
            return
        if tag != "a":
            return
        path = _safe_provider_movie_href(values.get("href", ""), self.base_url)
        title = (values.get("title") or "").strip()
        if path and title:
            self._item = {"path": path, "title": title, "poster": ""}
            self._depth = 1
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._item is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._item is None:
            return
        if tag in VOID_ELEMENTS:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        text = " ".join(" ".join(self._text).split())
        year = YEAR.search(text)
        rating = RATING.search(text)
        qualities = []
        for match in QUALITY.finditer(text):
            value = " ".join(part for part in match.groups() if part).lower()
            if value not in qualities:
                qualities.append(value)
        self._item.update(
            {
                "year": year.group(0) if year else "",
                "rating": rating.group(1) if rating else "",
                "qualities": qualities,
            }
        )
        if not any(existing["path"] == self._item["path"] for existing in self.items):
            self.items.append(self._item)
        self._item = None
        self._text = []
        self._depth = 0


class _TorrentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.torrents: list[dict[str, str]] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self._quality = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and self._anchor_href is None:
            self._anchor_href = (dict(attrs).get("href") or "").strip()
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._anchor_href is None:
            return
        href = self._anchor_href
        text = " ".join(" ".join(self._anchor_text).split())
        match = QUALITY.search(text)
        if _safe_magnet(href):
            label = self._quality or (match.group(0).lower() if match else "Torrent")
            if not any(item["magnet"] == href for item in self.torrents):
                self.torrents.append({"label": label, "magnet": href})
            self._quality = ""
        elif match:
            self._quality = text.lower()[:50]
        self._anchor_href = None
        self._anchor_text = []


class YtsClient:
    def __init__(self, base_url: str | None = None) -> None:
        configured = base_url or os.environ.get("POCKETSERVER_YTS_BASE_URL") or DEFAULT_BASE_URL
        self.base_url = configured.rstrip("/")

    def search(self, query: str) -> list[dict[str, Any]]:
        clean = " ".join(query.split())
        if not 2 <= len(clean) <= 80:
            raise ValueError("Enter between 2 and 80 characters to search YTS.")
        html = self._fetch("/search?" + urllib.parse.urlencode({"search": clean}))
        parser = _SearchParser(self.base_url)
        parser.feed(html)
        return parser.items[:12]

    def torrents(self, movie_path: str) -> list[dict[str, str]]:
        path = _safe_movie_path(movie_path)
        if not path:
            raise ValueError("Invalid YTS movie path.")
        parser = _TorrentParser()
        parser.feed(self._fetch(path))
        if not parser.torrents:
            raise YtsError("No torrent options were found for this title.")
        return parser.torrents

    def _fetch(self, path: str) -> str:
        request = urllib.request.Request(
            urllib.parse.urljoin(self.base_url + "/", path.lstrip("/")),
            headers={
                "User-Agent": "PocketServer/1.0 (+local media server)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                data = response.read(MAX_RESPONSE_BYTES + 1)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise YtsError("The YTS response was too large.")
                return data.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            raise YtsError("YTS is unavailable right now. Try again later.") from exc


def _safe_movie_path(value: str) -> str | None:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return None
    path = parsed.path.rstrip("/")
    return path if MOVIE_PATH.fullmatch(path) else None


def _safe_provider_movie_href(value: str, base_url: str) -> str | None:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme or parsed.netloc:
        provider = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != provider.netloc.lower():
            return None
        value = parsed.path
    return _safe_movie_path(value)


def _safe_magnet(value: str) -> bool:
    return len(value) <= 4096 and value.lower().startswith("magnet:?") and bool(BTIH.search(value))
