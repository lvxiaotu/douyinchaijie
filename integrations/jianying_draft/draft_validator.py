from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JianyingDraftValidator:
    """Inspect a Jianying draft directory and report missing local assets."""

    def validate(self, draft_path: str) -> dict[str, Any]:
        root = Path(draft_path)
        content_path = root / "draft_content.json"
        report: dict[str, Any] = {
            "draft_path": str(root),
            "exists": root.exists(),
            "is_dir": root.is_dir() if root.exists() else False,
            "draft_content_path": str(content_path),
            "draft_content_exists": content_path.exists(),
            "readable_json": False,
            "needs_decrypt": False,
            "assets": {
                "total": 0,
                "available": [],
                "missing": [],
                "unknown": [],
            },
            "errors": [],
        }

        if not root.exists():
            report["errors"].append("Draft path does not exist")
            return report
        if not root.is_dir():
            report["errors"].append("Draft path is not a directory")
            return report
        if not content_path.exists():
            report["needs_decrypt"] = True
            report["errors"].append("draft_content.json not found")
            return report

        try:
            content = json.loads(content_path.read_text(encoding="utf-8"))
            report["readable_json"] = True
        except UnicodeDecodeError:
            report["needs_decrypt"] = True
            report["errors"].append("draft_content.json is not UTF-8 readable")
            return report
        except json.JSONDecodeError as exc:
            report["needs_decrypt"] = True
            report["errors"].append(f"draft_content.json is not valid JSON: {exc}")
            return report

        paths = self.extract_asset_paths(content)
        report["assets"]["total"] = len(paths)
        for path in paths:
            if not path:
                continue
            asset_path = Path(path)
            record = {"path": path}
            if asset_path.exists():
                report["assets"]["available"].append(record)
            elif self.is_local_path(path):
                report["assets"]["missing"].append(record)
            else:
                report["assets"]["unknown"].append(record)
        return report

    def extract_asset_paths(self, value: Any) -> list[str]:
        paths: list[str] = []
        self.walk(value, paths)
        seen = set()
        unique_paths = []
        for path in paths:
            normalized = path.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_paths.append(normalized)
        return unique_paths

    def walk(self, value: Any, paths: list[str]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, str) and self.looks_like_asset_path(key, item):
                    paths.append(item)
                else:
                    self.walk(item, paths)
        elif isinstance(value, list):
            for item in value:
                self.walk(item, paths)

    def looks_like_asset_path(self, key: str, value: str) -> bool:
        lower_key = key.lower()
        lower_value = value.lower()
        if lower_key in {"path", "file_path", "local_path", "material_path", "audio_path", "video_path"}:
            return self.has_media_suffix(lower_value) or self.is_local_path(value)
        return self.has_media_suffix(lower_value) and self.is_local_path(value)

    def has_media_suffix(self, value: str) -> bool:
        return value.endswith(
            (
                ".mp4",
                ".mov",
                ".mkv",
                ".webm",
                ".avi",
                ".mp3",
                ".wav",
                ".m4a",
                ".aac",
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif",
            )
        )

    def is_local_path(self, value: str) -> bool:
        return ":" in value[:4] or value.startswith(("/", "\\", "./", "../"))

