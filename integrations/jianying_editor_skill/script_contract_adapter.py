from __future__ import annotations

from typing import Any


def generate_structured_script(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate a script.json-shaped object from the local Skill contract rules.

    This is project-owned bridge logic. It intentionally lives outside
    ``sdks/jianying-editor-skill`` so upstream SDK updates cannot overwrite it.
    """
    title = str(payload.get("title") or "Untitled short video").strip()
    idea = str(payload.get("idea") or title).strip()
    duration = int(payload.get("duration_seconds") or 30)
    scene_count = max(1, int(payload.get("scene_count") or 5))
    resolution = str(payload.get("resolution") or "9:16")
    style = str(payload.get("style") or "clean short-video rhythm").strip()
    genre = str(payload.get("genre") or "short video").strip()
    audience = str(payload.get("audience") or "short video audience").strip()

    beat_duration = max(2.0, round(duration / scene_count, 1))
    goals = ["opening hook", "setup", "conflict", "turn", "close"]
    scenes: list[dict[str, Any]] = []
    for index in range(1, scene_count + 1):
        goal = goals[(index - 1) % len(goals)]
        scenes.append(
            {
                "id": index,
                "title": f"Skill Scene {index}",
                "summary": f"{idea[:48]} · {goal}",
                "estimated_duration": beat_duration,
                "scene_goal": goal,
                "audio_narration": f"{title} 第{index}镜，用 {style or '自然'} 的节奏推进“{idea[:28]}”。",
                "onscreen_text": f"{title} {index}",
                "visual_prompt": f"{idea}, {style}, scene {index}, {resolution}, cinematic short video frame",
                "assets": {"video_path": "", "image_path": "", "audio_path": "", "duration": 0},
                "edit": {"transition": "fade", "animation": "zoom_in", "pacing": "steady", "camera": "slow push in"},
                "status": "waiting_assets",
            }
        )

    return {
        "config": {
            "title": title,
            "genre": genre,
            "resolution": resolution,
            "fps": 30,
            "style": style,
            "audience": audience,
            "total_duration_seconds": duration,
        },
        "scenes": scenes,
    }
