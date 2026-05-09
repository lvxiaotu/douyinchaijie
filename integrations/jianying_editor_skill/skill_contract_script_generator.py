from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from integrations.jianying_editor_skill.script_contract_adapter import generate_structured_script
from integrations.video_pipeline.script_schema import ScriptGenerateRequest, VideoScene, VideoScript, VideoScriptConfig


@dataclass
class SkillContractGeneratedScript:
    script: VideoScript
    raw_output: dict[str, Any]
    notes: list[str]


class JianyingSkillContractScriptGenerator:
    """Generate a structured script through project-owned JianYing Skill contract rules."""

    def generate(self, payload: ScriptGenerateRequest, project_id: str) -> SkillContractGeneratedScript:
        payload_dict = payload.model_dump()
        notes: list[str] = []
        try:
            raw_output = generate_structured_script(payload_dict)
            notes.append("Used project-owned JianYing Skill contract adapter.")
        except Exception as exc:
            raw_output = self._generate_fallback(payload_dict)
            notes.append(f"Skill contract fallback used: {type(exc).__name__}: {exc}")
        script = self._normalize(raw_output, payload, project_id)
        return SkillContractGeneratedScript(script=script, raw_output=raw_output, notes=notes)

    def _generate_fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        idea = str(payload.get("idea") or payload.get("title") or "").strip()
        title = str(payload.get("title") or "Untitled short video").strip()
        duration = int(payload.get("duration_seconds") or 30)
        scene_count = max(1, int(payload.get("scene_count") or 5))
        per_scene = max(2.0, round(duration / scene_count, 1))
        scenes: list[dict[str, Any]] = []
        for index in range(1, scene_count + 1):
            scenes.append(
                {
                    "id": index,
                    "title": f"Scene {index}",
                    "summary": f"{idea[:48]} · Skill scene {index}",
                    "estimated_duration": per_scene,
                    "scene_goal": self._goal(index),
                    "audio_narration": f"{title} 第{index}镜，围绕“{idea[:32]}”推进情绪和信息。",
                    "onscreen_text": f"{title} {index}",
                    "visual_prompt": f"{idea}, short video frame, scene {index}, cinematic composition",
                    "assets": {"video_path": "", "image_path": "", "audio_path": "", "duration": 0},
                    "edit": {"transition": "fade", "animation": "zoom_in", "pacing": "steady", "camera": "slow push in"},
                    "status": "waiting_assets",
                }
            )
        return {
            "config": {
                "title": title,
                "genre": str(payload.get("genre") or ""),
                "resolution": str(payload.get("resolution") or "9:16"),
                "fps": 30,
                "style": str(payload.get("style") or ""),
                "audience": str(payload.get("audience") or ""),
                "total_duration_seconds": duration,
            },
            "scenes": scenes,
        }

    def _normalize(self, data: dict[str, Any], payload: ScriptGenerateRequest, project_id: str) -> VideoScript:
        config = data.get("config") if isinstance(data.get("config"), dict) else {}
        scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
        normalized: list[VideoScene] = []
        for index, scene in enumerate(scenes[: payload.scene_count], start=1):
            item = scene if isinstance(scene, dict) else {}
            normalized.append(
                VideoScene.model_validate(
                    {
                        "id": index,
                        "title": str(item.get("title") or f"Scene {index}"),
                        "summary": str(item.get("summary") or ""),
                        "estimated_duration": float(item.get("estimated_duration") or 3),
                        "scene_goal": str(item.get("scene_goal") or self._goal(index)),
                        "audio_narration": str(item.get("audio_narration") or item.get("summary") or ""),
                        "onscreen_text": str(item.get("onscreen_text") or ""),
                        "visual_prompt": str(item.get("visual_prompt") or ""),
                        "assets": {"video_path": "", "image_path": "", "audio_path": "", "duration": 0},
                        "edit": {
                            "transition": ((item.get("edit") or {}).get("transition") if isinstance(item.get("edit"), dict) else None) or "fade",
                            "animation": ((item.get("edit") or {}).get("animation") if isinstance(item.get("edit"), dict) else None) or "zoom_in",
                            "pacing": ((item.get("edit") or {}).get("pacing") if isinstance(item.get("edit"), dict) else None) or "",
                            "camera": ((item.get("edit") or {}).get("camera") if isinstance(item.get("edit"), dict) else None) or "",
                        },
                        "status": "waiting_assets",
                    }
                )
            )
        while len(normalized) < payload.scene_count:
            index = len(normalized) + 1
            normalized.append(
                VideoScene(
                    id=index,
                    title=f"Scene {index}",
                    summary=f"Skill scene {index}",
                    estimated_duration=3,
                    scene_goal=self._goal(index),
                    audio_narration=f"Scene {index} narration placeholder.",
                    onscreen_text=f"Scene {index}",
                    visual_prompt=f"Scene {index}, short video frame",
                    assets={"video_path": "", "image_path": "", "audio_path": "", "duration": 0},
                    edit={"transition": "fade", "animation": "zoom_in", "pacing": "steady", "camera": "slow push in"},
                    status="waiting_assets",
                )
            )

        return VideoScript(
            project_id=project_id,
            config=VideoScriptConfig(
                title=str(config.get("title") or payload.title or "Untitled short video"),
                genre=str(config.get("genre") or payload.genre or ""),
                resolution=(config.get("resolution") or payload.resolution or "9:16"),
                fps=int(config.get("fps") or 30),
                style=str(config.get("style") or payload.style or ""),
                audience=str(config.get("audience") or payload.audience or ""),
                total_duration_seconds=float(config.get("total_duration_seconds") or payload.duration_seconds or 0),
            ),
            scenes=normalized,
        )

    def _goal(self, index: int) -> str:
        goals = ["opening hook", "setup", "development", "turn", "close"]
        return goals[(index - 1) % len(goals)]
