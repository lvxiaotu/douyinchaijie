from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from integrations.jianying_draft.draft_validator import JianyingDraftValidator


class JianyingTemplateManager:
    """Inspect template-like draft content for replaceable slots."""

    def __init__(self):
        self.validator = JianyingDraftValidator()

    def inspect_placeholder(self, template_path: str) -> dict[str, Any]:
        return {
            "template_path": template_path,
            "status": "not_implemented",
            "text_slots": [],
            "media_slots": [],
            "audio_slots": [],
            "required_assets": [],
        }

    def inspect(self, template_path: str) -> dict[str, Any]:
        validation = self.validator.validate(template_path)
        report: dict[str, Any] = {
            "template_path": template_path,
            "status": "needs_decrypt" if validation.get("needs_decrypt") else "inspected",
            "needs_decrypt": validation.get("needs_decrypt", False),
            "text_slots": [],
            "media_slots": [],
            "audio_slots": [],
            "required_assets": validation.get("assets") or {},
            "validation": validation,
        }
        if validation.get("needs_decrypt") or not validation.get("readable_json"):
            return report

        content_path = Path(template_path) / "draft_content.json"
        content = json.loads(content_path.read_text(encoding="utf-8"))
        text_slots: list[dict[str, Any]] = []
        media_slots: list[dict[str, Any]] = []
        audio_slots: list[dict[str, Any]] = []
        self.walk(content, [], text_slots, media_slots, audio_slots)
        report["text_slots"] = dedupe_slots(text_slots)
        report["media_slots"] = dedupe_slots(media_slots)
        report["audio_slots"] = dedupe_slots(audio_slots)
        return report

    def render(
        self,
        *,
        template_path: str,
        output_path: str,
        text_replacements: dict[str, str] | None = None,
        media_replacements: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        source = Path(template_path)
        target = Path(output_path)
        if not source.exists() or not source.is_dir():
            return {"status": "failed", "error": "Template path does not exist or is not a directory"}
        if target.exists():
            return {"status": "failed", "error": "Output path already exists"}
        shutil.copytree(source, target)
        content_path = target / "draft_content.json"
        if not content_path.exists():
            return {"status": "needs_decrypt", "output_path": str(target), "error": "draft_content.json not found"}
        try:
            content = json.loads(content_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"status": "needs_decrypt", "output_path": str(target), "error": str(exc)}

        text_count = self.apply_text_replacements(content, text_replacements or {})
        media_count = self.apply_media_replacements(content, media_replacements or {})
        content_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        validation = self.validator.validate(str(target))
        status = "rendered"
        if validation.get("needs_decrypt"):
            status = "needs_restore"
        elif validation.get("assets", {}).get("missing"):
            status = "has_missing_assets"
        return {
            "status": status,
            "template_path": str(source),
            "output_path": str(target),
            "text_replacements": text_count,
            "media_replacements": media_count,
            "validation": validation,
        }

    def walk(
        self,
        value: Any,
        path: list[str],
        text_slots: list[dict[str, Any]],
        media_slots: list[dict[str, Any]],
        audio_slots: list[dict[str, Any]],
    ) -> None:
        if isinstance(value, dict):
            slot_id = str(value.get("id") or value.get("material_id") or value.get("segment_id") or "")
            name = str(value.get("name") or value.get("text") or value.get("content") or "")
            if self.looks_like_text_slot(value):
                text_slots.append(
                    {
                        "id": slot_id,
                        "name": name[:80],
                        "json_path": ".".join(path),
                        "text": str(value.get("text") or value.get("content") or ""),
                    }
                )
            local_path = self.local_asset_path(value)
            if local_path:
                slot = {
                    "id": slot_id,
                    "name": str(value.get("name") or Path(local_path).name),
                    "json_path": ".".join(path),
                    "path": local_path,
                }
                if self.is_audio_path(local_path):
                    audio_slots.append(slot)
                else:
                    media_slots.append(slot)
            for key, item in value.items():
                self.walk(item, path + [str(key)], text_slots, media_slots, audio_slots)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self.walk(item, path + [str(index)], text_slots, media_slots, audio_slots)

    def looks_like_text_slot(self, value: dict[str, Any]) -> bool:
        if "text" in value and isinstance(value.get("text"), str) and value.get("text"):
            return True
        if "content" in value and isinstance(value.get("content"), str) and value.get("content"):
            return True
        value_type = str(value.get("type") or value.get("material_type") or "").lower()
        return "text" in value_type

    def local_asset_path(self, value: dict[str, Any]) -> str:
        for key in ("path", "file_path", "local_path", "material_path", "audio_path", "video_path"):
            item = value.get(key)
            if isinstance(item, str) and self.validator.looks_like_asset_path(key, item):
                return item
        return ""

    def is_audio_path(self, path: str) -> bool:
        return path.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".flac"))

    def apply_text_replacements(self, value: Any, replacements: dict[str, str]) -> int:
        count = 0
        if isinstance(value, dict):
            slot_id = str(value.get("id") or value.get("material_id") or value.get("segment_id") or "")
            for key in ("text", "content"):
                if key in value and isinstance(value.get(key), str):
                    old_text = str(value.get(key) or "")
                    replacement = replacements.get(slot_id) or replacements.get(old_text)
                    if replacement is not None:
                        value[key] = replacement
                        count += 1
            for item in value.values():
                count += self.apply_text_replacements(item, replacements)
        elif isinstance(value, list):
            for item in value:
                count += self.apply_text_replacements(item, replacements)
        return count

    def apply_media_replacements(self, value: Any, replacements: dict[str, str]) -> int:
        count = 0
        if isinstance(value, dict):
            slot_id = str(value.get("id") or value.get("material_id") or value.get("segment_id") or "")
            for key in ("path", "file_path", "local_path", "material_path", "audio_path", "video_path"):
                item = value.get(key)
                if isinstance(item, str):
                    replacement = replacements.get(slot_id) or replacements.get(item) or replacements.get(Path(item).name)
                    if replacement is not None:
                        value[key] = replacement
                        count += 1
            for item in value.values():
                count += self.apply_media_replacements(item, replacements)
        elif isinstance(value, list):
            for item in value:
                count += self.apply_media_replacements(item, replacements)
        return count


def dedupe_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for slot in slots:
        key = (slot.get("id") or "", slot.get("json_path") or "", slot.get("path") or slot.get("text") or "")
        if key in seen:
            continue
        seen.add(key)
        output.append(slot)
    return output
