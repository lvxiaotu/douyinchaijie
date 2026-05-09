from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class JianyingDraftOutputWriter:
    def finalize(self, draft_path: str) -> dict[str, Any]:
        root = Path(draft_path)
        content_path = root / "draft_content.json"
        meta_path = root / "draft_meta_info.json"

        if not root.exists():
            raise FileNotFoundError(f"draft output directory not found: {draft_path}")
        if not root.is_dir():
            raise NotADirectoryError(f"draft output path is not a directory: {draft_path}")

        content = self._read_json_if_possible(content_path)
        meta = self._read_json_if_possible(meta_path)

        return {
            "draft_directory": str(root.resolve()),
            "draft_name": root.name,
            "draft_root": str(root.parent.resolve()),
            "target_is_jianying_root": root.parent.name == "com.lveditor.draft",
            "files": {
                "draft_content": {
                    "path": str(content_path.resolve()),
                    "exists": content_path.exists(),
                    "size": content_path.stat().st_size if content_path.exists() else 0,
                    "readable_json": isinstance(content, dict),
                },
                "draft_meta_info": {
                    "path": str(meta_path.resolve()),
                    "exists": meta_path.exists(),
                    "size": meta_path.stat().st_size if meta_path.exists() else 0,
                    "readable_json": isinstance(meta, dict),
                },
            },
            "summary": {
                "track_count": len(content.get("tracks") or []) if isinstance(content, dict) else 0,
                "duration_us": int(content.get("duration") or 0) if isinstance(content, dict) else 0,
                "draft_id": str(meta.get("draft_id") or "") if isinstance(meta, dict) else "",
                "draft_fold_path": str(meta.get("draft_fold_path") or "") if isinstance(meta, dict) else "",
            },
        }

    def _read_json_if_possible(self, path: Path) -> dict[str, Any] | None:
        if not path.exists() or not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return None
