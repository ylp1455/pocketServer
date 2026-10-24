from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Iterator


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".mpeg", ".mpg"}


def scan_media(*roots: Path) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            stat = path.stat()
            items.append(
                {
                    "name": path.stem,
                    "filename": path.name,
                    "path": str(resolved),
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime),
                    "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                }
            )
    return sorted(items, key=lambda item: int(item["modified"]), reverse=True)


def safe_media_path(encoded_path: str, roots: list[Path]) -> Path | None:
    candidate = Path(encoded_path).resolve()
    for root in roots:
        try:
            candidate.relative_to(root.resolve())
            if candidate.is_file():
                return candidate
        except ValueError:
            continue
    return None


def chunks(path: Path, start: int, length: int, chunk_size: int = 256 * 1024) -> Iterator[bytes]:
    remaining = length
    with path.open("rb") as file:
        file.seek(start)
        while remaining > 0:
            data = file.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data
