from __future__ import annotations

import json
from datetime import datetime
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
        report["readable"] = self._readable_report(root, report["draft_content"], report["draft_meta"], report["files"])
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
        draft_name = self._draft_name(meta, content)
        return {
            "track_count": len(tracks),
            "track_types": [track.get("type") for track in tracks if isinstance(track, dict)],
            "material_groups": len(content_materials) or len(meta_materials),
            "canvas": {**canvas, "ratio": canvas.get("ratio") or self._canvas_ratio(canvas)},
            "duration_seconds": round(float(content.get("duration") or 0) / 1_000_000, 2),
            "draft_id": meta.get("draft_id") or "",
            "draft_name": draft_name,
            "created_at": self._format_meta_timestamp(meta.get("tm_draft_create")),
            "modified_at": self._format_meta_timestamp(meta.get("tm_draft_modified")),
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

    def _readable_report(
        self,
        root: Path,
        content: dict[str, Any],
        meta: dict[str, Any],
        files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        summary = self._summary(content, meta)
        details = self._details(content)
        materials = content.get("materials") if isinstance(content.get("materials"), dict) else {}
        tracks = content.get("tracks") if isinstance(content.get("tracks"), list) else []
        material_counts = details.get("material_counts") if isinstance(details.get("material_counts"), dict) else {}
        track_details = details.get("track_details") if isinstance(details.get("track_details"), list) else []
        text_items = self._extract_text_items(materials)
        media_sources = self._extract_media_sources(materials)
        file_items = [self._present_file_item(item) for item in files]
        track_types = [item for item in summary.get("track_types", []) if item]
        dominant_groups = sorted(material_counts.items(), key=lambda item: item[1], reverse=True)
        total_segments = sum(int(track.get("segments") or 0) for track in track_details)
        overview_parts = []
        if summary.get("duration_seconds"):
            overview_parts.append(f"总时长约 {summary['duration_seconds']} 秒")
        if summary.get("track_count"):
            overview_parts.append(f"{summary['track_count']} 条轨道")
        if total_segments:
            overview_parts.append(f"{total_segments} 个时间线片段")
        if dominant_groups:
            overview_parts.append(f"素材主要由 {', '.join(f'{name} {count} 个' for name, count in dominant_groups[:3])} 组成")
        overview_text = "，".join(overview_parts) if overview_parts else "这个草稿目前只包含很少的可读时间线信息。"

        return {
            "identity": {
                "name": summary.get("draft_name") or root.name,
                "path": str(root),
                "draft_id": summary.get("draft_id") or details.get("id") or "",
                "created_at": summary.get("created_at") or "",
                "modified_at": summary.get("modified_at") or "",
            },
            "overview": overview_text,
            "canvas": {
                "ratio": summary.get("canvas", {}).get("ratio") or "",
                "size": self._canvas_size_label(summary.get("canvas", {})),
                "duration_seconds": summary.get("duration_seconds") or 0,
                "color_space": details.get("color_space") or "",
            },
            "timeline": {
                "track_count": summary.get("track_count") or 0,
                "segment_count": total_segments,
                "track_types": track_types,
                "track_explanations": [self._present_track_detail(track) for track in track_details],
                "track_headline": self._track_headline(track_details),
            },
            "materials": {
                "counts": material_counts,
                "headline": self._material_headline(material_counts),
                "sources": media_sources,
            },
            "texts": {
                "count": len(text_items),
                "items": text_items[:24],
                "headline": self._text_headline(text_items),
            },
            "effects": {
                "keyframes": details.get("keyframe_counts") or {},
                "config_keys": details.get("config_keys") or [],
                "headline": self._effects_headline(details),
            },
            "project_files": file_items,
            "raw_hints": {
                "top_level_keys": sorted(content.keys()) if isinstance(content, dict) else [],
                "material_groups": sorted(materials.keys()) if isinstance(materials, dict) else [],
            },
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

    def _draft_name(self, meta: dict[str, Any], content: dict[str, Any]) -> str:
        candidates = [
            meta.get("draft_name"),
            meta.get("tm_draft_name"),
            Path(str(meta.get("draft_fold_path") or "")).name if meta.get("draft_fold_path") else "",
            content.get("name") if isinstance(content.get("name"), str) else "",
        ]
        return next((str(item).strip() for item in candidates if str(item or "").strip()), "")

    def _format_meta_timestamp(self, value: Any) -> str:
        try:
            raw = int(value or 0)
        except (TypeError, ValueError):
            return ""
        if raw <= 0:
            return ""
        if raw > 1_000_000_000_000:
            timestamp = raw / 1_000_000
        elif raw > 10_000_000_000:
            timestamp = raw / 1_000
        else:
            timestamp = raw
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    def _canvas_size_label(self, canvas: dict[str, Any]) -> str:
        width = int(canvas.get("width") or canvas.get("canvas_width") or 0)
        height = int(canvas.get("height") or canvas.get("canvas_height") or 0)
        if not width or not height:
            return ""
        return f"{width} x {height}"

    def _extract_text_items(self, materials: dict[str, Any]) -> list[dict[str, str]]:
        items = materials.get("texts") if isinstance(materials.get("texts"), list) else []
        result: list[dict[str, str]] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            text = self._extract_text_content(item)
            if not text:
                continue
            result.append(
                {
                    "title": item.get("name") or item.get("material_name") or f"文字 {index}",
                    "content": text,
                }
            )
        return result

    def _extract_text_content(self, item: dict[str, Any]) -> str:
        if isinstance(item.get("text"), str) and item.get("text", "").strip():
            return str(item.get("text")).strip()
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            return ""
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return content.strip()[:180]
        if isinstance(parsed, dict):
            for key in ("text", "content", "value"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return content.strip()[:180]

    def _extract_media_sources(self, materials: dict[str, Any]) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for group_name, items in materials.items():
            if not isinstance(items, list):
                continue
            for item in items[:12]:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or item.get("file_Path") or item.get("file_path") or "").strip()
                if not path:
                    continue
                result.append(
                    {
                        "group": str(group_name),
                        "title": str(item.get("name") or item.get("material_name") or Path(path).name or group_name),
                        "path": path,
                    }
                )
        return result

    def _present_track_detail(self, track: dict[str, Any]) -> dict[str, Any]:
        track_type = str(track.get("type") or "")
        segments = int(track.get("segments") or 0)
        return {
            "title": track.get("name") or track_type or "未命名轨道",
            "type": track_type,
            "segments": segments,
            "explanation": self._track_description(track_type, segments),
            "id": track.get("id") or "",
        }

    def _track_description(self, track_type: str, segments: int) -> str:
        if track_type == "video":
            return f"这条轨道主要承载画面内容，目前有 {segments} 个片段。"
        if track_type == "audio":
            return f"这条轨道主要承载旁白、配乐或音效，目前有 {segments} 个片段。"
        if track_type in {"text", "subtitle"}:
            return f"这条轨道主要承载屏幕文字或字幕，目前有 {segments} 个片段。"
        return f"这是一条 {track_type or '未标注类型'} 轨道，目前有 {segments} 个片段。"

    def _track_headline(self, track_details: list[dict[str, Any]]) -> str:
        if not track_details:
            return "这个草稿暂时没有可读的轨道结构。"
        parts = [f"{track.get('type') or '未标注'}轨 {track.get('segments') or 0} 段" for track in track_details[:4]]
        return "，".join(parts)

    def _material_headline(self, material_counts: dict[str, Any]) -> str:
        if not material_counts:
            return "还没有识别到明确的素材分组。"
        parts = [f"{name} {count} 个" for name, count in sorted(material_counts.items(), key=lambda item: item[1], reverse=True)[:5]]
        return "素材分组包括 " + "，".join(parts)

    def _text_headline(self, text_items: list[dict[str, str]]) -> str:
        if not text_items:
            return "这个草稿里没有识别到可直接阅读的文字内容。"
        return f"共识别到 {len(text_items)} 条可读文字，可用来理解字幕、屏幕文案或标题。"

    def _effects_headline(self, details: dict[str, Any]) -> str:
        keyframes = details.get("keyframe_counts") if isinstance(details.get("keyframe_counts"), dict) else {}
        config_keys = details.get("config_keys") if isinstance(details.get("config_keys"), list) else []
        if not keyframes and not config_keys:
            return "没有明显的关键帧或额外配置项。"
        parts = []
        if keyframes:
            parts.append("关键帧：" + "，".join(f"{key} {value}" for key, value in keyframes.items()))
        if config_keys:
            parts.append("配置项：" + "，".join(config_keys[:8]))
        return "；".join(parts)

    def _present_file_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": item.get("name") or "",
            "relative_path": item.get("relative_path") or "",
            "status": item.get("status") or "",
            "needs_decrypt": bool(item.get("needs_decrypt")),
            "size": item.get("size"),
        }
