from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

from integrations.jianying_draft.name_utils import default_draft_name, safe_draft_name


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
        draft_name = name or str(config.get("title") or "") or default_draft_name()

        media: list[dict[str, Any]] = []
        audio: list[dict[str, Any]] = []
        texts: list[dict[str, Any]] = []
        protocol_tracks = {"video": [], "audio": [], "subtitle": []}
        cursor = 0.0

        for index, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                continue
            assets = scene.get("assets") if isinstance(scene.get("assets"), dict) else {}
            edit = scene.get("edit") if isinstance(scene.get("edit"), dict) else {}
            start_seconds = float(scene.get("start_seconds") or cursor)
            duration_seconds = self._scene_duration(scene, assets, default_media_duration_seconds)
            role = f"scene_{index}"
            source_ref = self._source_ref(scene, assets, role)

            visual_path = str(assets.get("video_path") or assets.get("image_path") or "").strip()
            if visual_path:
                media_type = "video" if str(assets.get("video_path") or "").strip() else "image"
                clip_settings = self._scene_clip_settings(scene)
                media_item = {
                    "path": visual_path,
                    "type": media_type,
                    "role": role,
                    "track": "video",
                    "start_seconds": start_seconds,
                    "duration_seconds": duration_seconds,
                    "material_id": self._material_id("video", role, visual_path),
                    "source_ref": source_ref,
                    "clip_settings": clip_settings,
                    "transform": clip_settings,
                }
                media.append(media_item)
                protocol_tracks["video"].append(
                    {
                        "segment_id": self._segment_id("video", role),
                        "track": "video",
                        "role": role,
                        "material_id": media_item["material_id"],
                        "source_path": visual_path,
                        "source_type": media_type,
                        "start_ms": self._to_ms(start_seconds),
                        "end_ms": self._to_ms(start_seconds + duration_seconds),
                        "duration_ms": self._to_ms(duration_seconds),
                        "clip_settings": clip_settings,
                        "edit": {
                            "transition": str(edit.get("transition") or ""),
                            "animation": str(edit.get("animation") or ""),
                            "camera": str(edit.get("camera") or ""),
                        },
                    }
                )

            audio_path = str(assets.get("audio_path") or "").strip()
            if audio_path:
                audio_role = f"{role}_narration"
                audio_item = {
                    "path": audio_path,
                    "type": "audio",
                    "role": audio_role,
                    "track": "audio",
                    "start_seconds": start_seconds,
                    "duration_seconds": duration_seconds,
                    "material_id": self._material_id("audio", audio_role, audio_path),
                    "source_ref": source_ref,
                }
                audio.append(audio_item)
                protocol_tracks["audio"].append(
                    {
                        "segment_id": self._segment_id("audio", audio_role),
                        "track": "audio",
                        "role": audio_role,
                        "material_id": audio_item["material_id"],
                        "source_path": audio_path,
                        "start_ms": self._to_ms(start_seconds),
                        "end_ms": self._to_ms(start_seconds + duration_seconds),
                        "duration_ms": self._to_ms(duration_seconds),
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
                        "role": f"{role}_text",
                    }
                )
            if subtitle_from_narration and narration:
                subtitle_segments = self._split_subtitles(narration, start_seconds, duration_seconds, role)
                for subtitle in subtitle_segments:
                    texts.append(
                        {
                            "text": subtitle["text"],
                            "track": "subtitle",
                            "start_seconds": subtitle["start_seconds"],
                            "duration_seconds": subtitle["duration_seconds"],
                            "style": text_style or {},
                            "background": text_background or {},
                            "clip_settings": {"transform_y": -0.8},
                            "role": subtitle["role"],
                            "material_id": subtitle["material_id"],
                        }
                    )
                    protocol_tracks["subtitle"].append(
                        {
                            "segment_id": self._segment_id("subtitle", subtitle["role"]),
                            "track": "subtitle",
                            "role": subtitle["role"],
                            "material_id": subtitle["material_id"],
                            "text": subtitle["text"],
                            "start_ms": self._to_ms(subtitle["start_seconds"]),
                            "end_ms": self._to_ms(subtitle["start_seconds"] + subtitle["duration_seconds"]),
                            "duration_ms": self._to_ms(subtitle["duration_seconds"]),
                            "clip_settings": {"transform_y": -0.8},
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
                        "role": f"{role}_text",
                    }
                )

            cursor = max(cursor, start_seconds + duration_seconds)

        total_duration = float(config.get("total_duration_seconds") or cursor or 0)
        return {
            "name": safe_draft_name(draft_name, fallback=default_draft_name()),
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
                "protocol_encoding": {
                    "version": "draft_content_v1",
                    "tracks": protocol_tracks,
                    "material_bindings": self._material_bindings(protocol_tracks),
                },
                "scene_plan": [
                    {
                        "id": scene.get("id") or index,
                        "role": f"scene_{index}",
                        "estimated_duration": self._scene_duration(
                            scene if isinstance(scene, dict) else {},
                            (scene.get("assets") if isinstance(scene, dict) and isinstance(scene.get("assets"), dict) else {}),
                            default_media_duration_seconds,
                        )
                        if isinstance(scene, dict)
                        else float(default_media_duration_seconds),
                        "edit": (scene.get("edit") if isinstance(scene, dict) and isinstance(scene.get("edit"), dict) else {}),
                        "protocol": {
                            "start_ms": self._to_ms(float(scene.get("start_seconds") or 0) if isinstance(scene, dict) else 0),
                            "duration_ms": self._to_ms(
                                self._scene_duration(
                                    scene if isinstance(scene, dict) else {},
                                    (scene.get("assets") if isinstance(scene, dict) and isinstance(scene.get("assets"), dict) else {}),
                                    default_media_duration_seconds,
                                )
                            ),
                        },
                    }
                    for index, scene in enumerate(scenes, start=1)
                ],
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

    def _material_id(self, kind: str, role: str, source: str) -> str:
        payload = f"{kind}|{role}|{source}".encode("utf-8", errors="ignore")
        return hashlib.md5(payload).hexdigest()

    def _segment_id(self, kind: str, role: str) -> str:
        return f"{kind}_{role}"

    def _to_ms(self, seconds: float) -> int:
        return int(round(float(seconds or 0) * 1000))

    def _scene_clip_settings(self, scene: dict[str, Any]) -> dict[str, Any]:
        visual_prompt = str(scene.get("visual_prompt") or "")
        edit = scene.get("edit") if isinstance(scene.get("edit"), dict) else {}
        camera = str(edit.get("camera") or "")
        prompt_blob = f"{visual_prompt} {camera}".lower()
        scale = 1.0
        rotation = 0.0
        alpha = 1.0
        if any(token in prompt_blob for token in ("close up", "特写", "push in", "zoom in")):
            scale = 1.08
        if "rotate" in prompt_blob or "旋转" in prompt_blob:
            rotation = 3.0
        if "overlay" in prompt_blob or "叠加" in prompt_blob:
            alpha = 0.92
        return {
            "alpha": alpha,
            "rotation": rotation,
            "scale_x": scale,
            "scale_y": scale,
            "transform_x": 0.0,
            "transform_y": 0.0,
        }

    def _split_subtitles(self, narration: str, start_seconds: float, duration_seconds: float, role: str) -> list[dict[str, Any]]:
        parts = [item.strip() for item in re.split(r"[，。！？!?；;\n\r]+", narration) if item.strip()]
        if not parts:
            parts = [narration.strip()]
        if not parts:
            return []
        total_chars = sum(max(1, len(part)) for part in parts)
        cursor = start_seconds
        segments: list[dict[str, Any]] = []
        for index, part in enumerate(parts, start=1):
            weight = max(1, len(part)) / total_chars
            seg_duration = duration_seconds * weight
            if index == len(parts):
                seg_duration = max(0, start_seconds + duration_seconds - cursor)
            seg_role = f"{role}_subtitle_{index}"
            segments.append(
                {
                    "role": seg_role,
                    "text": part,
                    "start_seconds": round(cursor, 3),
                    "duration_seconds": round(max(seg_duration, 0.2), 3),
                    "material_id": self._material_id("subtitle", seg_role, part),
                }
            )
            cursor += seg_duration
        return segments

    def _source_ref(self, scene: dict[str, Any], assets: dict[str, Any], role: str) -> dict[str, Any]:
        return {
            "role": role,
            "scene_id": scene.get("id"),
            "video_path": str(assets.get("video_path") or ""),
            "image_path": str(assets.get("image_path") or ""),
            "audio_path": str(assets.get("audio_path") or ""),
        }

    def _material_bindings(self, tracks: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        bindings: list[dict[str, Any]] = []
        for items in tracks.values():
            for item in items:
                bindings.append(
                    {
                        "material_id": item.get("material_id") or "",
                        "track": item.get("track") or "",
                        "role": item.get("role") or "",
                        "source_path": item.get("source_path") or "",
                        "text": item.get("text") or "",
                    }
                )
        return bindings
