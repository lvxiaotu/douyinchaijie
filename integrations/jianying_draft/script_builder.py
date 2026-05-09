from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JianyingScriptDraftBuilder:
    """Convert script.json-like payloads into pyJianYingDraft create_draft payloads."""

    def load_script(self, *, script_path: str | None = None, script: dict[str, Any] | None = None) -> dict[str, Any]:
        if script and isinstance(script, dict):
            return script
        if script_path:
            path = Path(script_path)
            if not path.exists():
                raise FileNotFoundError(f"script file not found: {script_path}")
            return json.loads(path.read_text(encoding="utf-8"))
        raise ValueError("Either script_path or script must be provided")

    def build_payload(
        self,
        *,
        script_data: dict[str, Any],
        name: str | None = None,
        include_onscreen_text: bool = True,
        subtitle_from_narration: bool = False,
        default_media_duration_seconds: float = 3.0,
        text_style: dict[str, Any] | None = None,
        text_background: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        config = script_data.get("config") if isinstance(script_data.get("config"), dict) else {}
        scenes = script_data.get("scenes") if isinstance(script_data.get("scenes"), list) else []
        aspect_ratio = str(config.get("resolution") or "9:16")
        draft_name = name or str(config.get("title") or script_data.get("project_id") or "jianying_draft")

        media: list[dict[str, Any]] = []
        audio: list[dict[str, Any]] = []
        texts: list[dict[str, Any]] = []
        cursor = 0.0

        for index, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                continue
            assets = scene.get("assets") if isinstance(scene.get("assets"), dict) else {}
            start_seconds = float(scene.get("start_seconds") or cursor)
            duration_seconds = self._scene_duration(scene, assets, default_media_duration_seconds)

            visual_path = str(assets.get("video_path") or assets.get("image_path") or "").strip()
            if visual_path:
                media.append(
                    {
                        "path": visual_path,
                        "type": "video" if str(assets.get("video_path") or "").strip() else "image",
                        "role": f"scene_{index}",
                        "track": "video",
                        "start_seconds": start_seconds,
                        "duration_seconds": duration_seconds,
                    }
                )

            audio_path = str(assets.get("audio_path") or "").strip()
            if audio_path:
                audio.append(
                    {
                        "path": audio_path,
                        "type": "audio",
                        "role": f"scene_{index}_narration",
                        "track": "audio",
                        "start_seconds": start_seconds,
                        "duration_seconds": duration_seconds,
                    }
                )

            onscreen_text = str(scene.get("onscreen_text") or "").strip()
            narration = str(scene.get("audio_narration") or scene.get("narration") or "").strip()
            if include_onscreen_text and onscreen_text:
                texts.append(
                    {
                        "text": onscreen_text,
                        "track": "text",
                        "start_seconds": start_seconds,
                        "duration_seconds": duration_seconds,
                        "style": text_style or {},
                        "background": text_background or {},
                    }
                )
            if subtitle_from_narration and narration:
                texts.append(
                    {
                        "text": narration,
                        "track": "subtitle",
                        "start_seconds": start_seconds,
                        "duration_seconds": duration_seconds,
                        "style": text_style or {},
                        "background": text_background or {},
                    }
                )
            elif not include_onscreen_text and narration:
                texts.append(
                    {
                        "text": narration,
                        "track": "text",
                        "start_seconds": start_seconds,
                        "duration_seconds": duration_seconds,
                        "style": text_style or {},
                        "background": text_background or {},
                    }
                )

            cursor = max(cursor, start_seconds + duration_seconds)

        total_duration = float(config.get("total_duration_seconds") or cursor or 0)
        return {
            "name": self._safe_name(draft_name),
            "aspect_ratio": aspect_ratio,
            "default_media_duration_seconds": default_media_duration_seconds,
            "media": media,
            "audio": audio,
            "texts": texts,
            "meta": {
                "source_project_id": script_data.get("project_id") or "",
                "source_title": config.get("title") or "",
                "scene_count": len(scenes),
                "total_duration_seconds": total_duration,
            },
        }

    def _scene_duration(self, scene: dict[str, Any], assets: dict[str, Any], default_value: float) -> float:
        for value in (
            assets.get("duration"),
            scene.get("estimated_duration"),
            scene.get("duration_seconds"),
        ):
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                return number
        return float(default_value)

    def _safe_name(self, value: str) -> str:
        safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_")
        return safe or "jianying_draft"
