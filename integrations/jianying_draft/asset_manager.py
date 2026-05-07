from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


MEDIA_EXTENSIONS = {
    ".mp4": "video",
    ".mov": "video",
    ".mkv": "video",
    ".webm": "video",
    ".avi": "video",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".gif": "image",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".aac": "audio",
    ".flac": "audio",
}


class JianyingAssetManager:
    """Small first-pass asset scanner. Metadata extraction comes later."""

    def scan_directory(self, asset_dir: str, *, limit: int = 500) -> dict[str, Any]:
        root = Path(asset_dir)
        if not root.exists():
            return {"asset_dir": str(root), "exists": False, "assets": [], "count": 0}

        assets: list[dict[str, Any]] = []
        for path in root.rglob("*"):
            if len(assets) >= limit:
                break
            if not path.is_file():
                continue
            asset_type = MEDIA_EXTENSIONS.get(path.suffix.lower())
            if not asset_type:
                continue
            stat = path.stat()
            fingerprint = self._fingerprint(path, stat.st_size, stat.st_mtime_ns)
            assets.append(
                {
                    "id": fingerprint,
                    "type": asset_type,
                    "name": path.name,
                    "source": "local",
                    "path": str(path),
                    "suffix": path.suffix.lower(),
                    "size": stat.st_size,
                    "hash": fingerprint,
                    "status": "available",
                    "meta": {
                        "suffix": path.suffix.lower(),
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                    },
                }
            )
        return {"asset_dir": str(root), "exists": True, "assets": assets, "count": len(assets)}

    def _fingerprint(self, path: Path, size: int, mtime_ns: int) -> str:
        value = f"{path.resolve()}|{size}|{mtime_ns}".encode("utf-8", errors="ignore")
        return hashlib.sha256(value).hexdigest()
