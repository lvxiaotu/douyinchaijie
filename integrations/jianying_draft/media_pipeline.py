from __future__ import annotations

from pathlib import Path
from typing import Any


class JianyingMediaPipeline:
    """Placeholder for ffprobe/ffmpeg normalization."""

    def probe_placeholder(self, media_path: str) -> dict[str, Any]:
        path = Path(media_path)
        return {
            "path": str(path),
            "exists": path.exists(),
            "status": "not_implemented",
        }

