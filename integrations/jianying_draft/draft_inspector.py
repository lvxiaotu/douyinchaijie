from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JianyingDraftInspector:
    """Load and summarize a Jianying draft directory."""

    DRAFT_DOCUMENT_NAMES = {
        "attachment_editing.json",
        "attachment_pc_common.json",
        "attachment_pc_timeline.json",
        "attachment_script_video.json",
        "coperate_create.json",
        "draft.extra",
        "draft_agency_config.json",
        "draft_biz_config.json",
        "draft_content.json",
        "draft_meta_info.json",
        "draft_settings",
        "draft_virtual_store.json",
        "key_value.json",
        "performance_opt_info.json",
        "project.json",
        "timeline_backup_manifest.json",
        "timeline_layout.json",
    }

    def inspect(self, draft_path: str) -> dict[str, Any]:
        root = Path(draft_path)
        content_path = root / "draft_content.json"
        meta_path = root / "draft_meta_info.json"

        report: dict[str, Any] = {
            "draft_path": str(root),
            "exists": root.exists(),
            "draft_content_exists": content_path.exists(),
            "draft_meta_exists": meta_path.exists(),
            "draft_content": {},
            "draft_meta": {},
            "files": [],
            "needs_decrypt": False,
            "error": "",
            "summary": {},
        }

        if not root.exists():
            raise FileNotFoundError(f"draft path not found: {draft_path}")
        if not root.is_dir():
            raise NotADirectoryError(f"draft path is not a directory: {draft_path}")

        report["files"] = [
            self._inspect_path(path, root)
            for path in sorted(root.rglob("*"))
            if self._should_include_path(path, root)
        ]

        content_file = self._find_file(report["files"], "draft_content.json")
        meta_file = self._find_file(report["files"], "draft_meta_info.json")

        if content_file and content_file.get("status") == "parsed_json":
            report["draft_content"] = content_file.get("content") or {}
        elif content_file and content_file.get("needs_decrypt"):
            report["needs_decrypt"] = True
            report["error"] = content_file.get("error") or "draft_content.json is not readable."
        if meta_file and meta_file.get("status") == "parsed_json":
            report["draft_meta"] = meta_file.get("content") or {}

        report["summary"] = self._summary(report["draft_content"], report["draft_meta"])
        report["details"] = self._details(report["draft_content"])
        return report

    def list_projects(self, draft_root: str) -> dict[str, Any]:
        root = Path(draft_root)
        if not root.exists():
            raise FileNotFoundError(f"draft root not found: {draft_root}")
        if not root.is_dir():
            raise NotADirectoryError(f"draft root is not a directory: {draft_root}")

        projects = []
        for path in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
            if not path.is_dir() or path.name.startswith("."):
                continue
            content_path = path / "draft_content.json"
            meta_path = path / "draft_meta_info.json"
            content_state = self._draft_content_state(content_path)
            projects.append(
                {
                    "name": path.name,
                    "draft_path": str(path),
                    "last_modified": path.stat().st_mtime,
                    "draft_content_exists": content_path.exists(),
                    "draft_meta_exists": meta_path.exists(),
                    "status": content_state["status"],
                    "needs_decrypt": content_state["needs_decrypt"],
                    "error": content_state["error"],
                }
            )

        return {"draft_root": str(root), "projects": projects}

    def _draft_content_state(self, content_path: Path) -> dict[str, Any]:
        if not content_path.exists():
            return {"status": "missing_content", "needs_decrypt": True, "error": "draft_content.json not found"}
        if content_path.is_dir():
            return {"status": "needs_decrypt", "needs_decrypt": True, "error": "draft_content.json is a directory"}
        try:
            json.loads(content_path.read_text(encoding="utf-8-sig"))
            return {"status": "ready", "needs_decrypt": False, "error": ""}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return {"status": "needs_decrypt", "needs_decrypt": True, "error": f"{exc.__class__.__name__}: {exc}"}

    def _inspect_path(self, path: Path, root: Path) -> dict[str, Any]:
        if path.is_dir():
            return self._inspect_directory(path, root)
        return self._inspect_file(path, root)

    def _inspect_directory(self, path: Path, root: Path) -> dict[str, Any]:
        return {
            "name": path.name,
            "relative_path": path.relative_to(root).as_posix(),
            "path": str(path),
            "kind": "draft_document",
            "size": None,
            "child_count": 0,
            "status": "needs_decrypt",
            "needs_decrypt": True,
            "content": None,
            "error": "Draft document is a directory and may need decrypting first.",
        }

    def _inspect_file(self, path: Path, root: Path) -> dict[str, Any]:
        item: dict[str, Any] = {
            "name": path.name,
            "relative_path": path.relative_to(root).as_posix(),
            "path": str(path),
            "kind": "file",
            "size": path.stat().st_size,
            "child_count": 0,
            "status": "unreadable",
            "needs_decrypt": False,
            "content": None,
            "error": "",
        }

        if path.suffix.lower() == ".json":
            try:
                item["content"] = json.loads(path.read_text(encoding="utf-8-sig"))
                item["status"] = "parsed_json"
                return item
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                item["status"] = "needs_decrypt"
                item["needs_decrypt"] = True
                item["error"] = f"{exc.__class__.__name__}: {exc}"
                return item

        try:
            item["content"] = path.read_text(encoding="utf-8")
            item["status"] = "text"
        except UnicodeDecodeError as exc:
            item["status"] = "needs_decrypt"
            item["needs_decrypt"] = True
            item["error"] = f"{exc.__class__.__name__}: {exc}"
        return item

    def _find_file(self, files: list[dict[str, Any]], relative_path: str) -> dict[str, Any] | None:
        normalized = relative_path.replace("\\", "/")
        return next((item for item in files if item.get("relative_path") == normalized), None)

    def _should_include_path(self, path: Path, root: Path) -> bool:
        relative_parts = path.relative_to(root).parts
        if any(self._looks_like_draft_document_name(part) for part in relative_parts[:-1]):
            return False
        if path.is_dir():
            return self._looks_like_draft_document_name(path.name)
        return self._looks_like_draft_document_name(path.name)

    def _looks_like_draft_document_name(self, name: str) -> bool:
        normalized = name.lower()
        return (
            normalized in self.DRAFT_DOCUMENT_NAMES
            or normalized.endswith(".json")
            or normalized.endswith(".json.bak")
            or (normalized.startswith("template") and normalized.endswith(".tmp"))
            or normalized.endswith(".save.bak")
            or normalized.endswith(".close.bak")
            or normalized.endswith(".load.bak")
        )

    def _summary(self, content: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
        tracks = content.get("tracks") if isinstance(content.get("tracks"), list) else []
        meta_materials = meta.get("draft_materials") if isinstance(meta.get("draft_materials"), list) else []
        content_materials = content.get("materials") if isinstance(content.get("materials"), dict) else {}
        canvas = content.get("canvas_config") if isinstance(content.get("canvas_config"), dict) else {}
        return {
            "track_count": len(tracks),
            "track_types": [track.get("type") for track in tracks if isinstance(track, dict)],
            "material_groups": len(content_materials) or len(meta_materials),
            "canvas": {**canvas, "ratio": canvas.get("ratio") or self._canvas_ratio(canvas)},
            "duration_seconds": round(float(content.get("duration") or 0) / 1_000_000, 2),
            "draft_id": meta.get("draft_id") or "",
            "draft_name": Path(str(meta.get("draft_fold_path") or "")).name if meta.get("draft_fold_path") else "",
        }

    def _details(self, content: dict[str, Any]) -> dict[str, Any]:
        if not content:
            return {}
        tracks = content.get("tracks") if isinstance(content.get("tracks"), list) else []
        materials = content.get("materials") if isinstance(content.get("materials"), dict) else {}
        keyframes = content.get("keyframes") if isinstance(content.get("keyframes"), dict) else {}
        return {
            "id": content.get("id") or "",
            "version": content.get("version") or "",
            "new_version": content.get("new_version") or "",
            "platform": content.get("platform") or "",
            "last_modified_platform": content.get("last_modified_platform") or "",
            "color_space": content.get("color_space"),
            "track_details": [
                {
                    "id": track.get("id") or "",
                    "type": track.get("type") or "",
                    "name": track.get("name") or "",
                    "segments": len(track.get("segments") or []),
                    "render_index": track.get("render_index"),
                    "mute": track.get("mute"),
                }
                for track in tracks
                if isinstance(track, dict)
            ],
            "material_counts": {
                key: len(value)
                for key, value in materials.items()
                if isinstance(value, list) and value
            },
            "keyframe_counts": {
                key: len(value)
                for key, value in keyframes.items()
                if isinstance(value, list) and value
            },
            "config_keys": sorted((content.get("config") or {}).keys()) if isinstance(content.get("config"), dict) else [],
        }

    def _canvas_ratio(self, canvas: dict[str, Any]) -> str:
        width = int(canvas.get("width") or canvas.get("canvas_width") or 0)
        height = int(canvas.get("height") or canvas.get("canvas_height") or 0)
        if not width or not height:
            return ""
        if width * 16 == height * 9:
            return "9:16"
        if width * 9 == height * 16:
            return "16:9"
        if width == height:
            return "1:1"
        return f"{width}:{height}"
