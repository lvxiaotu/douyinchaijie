from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.ai_provider_state import active_ai_provider
from integrations.video_pipeline.script_generator import VideoScriptGenerator
from integrations.video_pipeline.script_schema import BibleGenerateRequest, BlueprintGenerateRequest, ConceptBible

router = APIRouter(prefix="/api/studio", tags=["studio"])


class StudioBrainstormRequest(BaseModel):
    type: str = Field(default="短视频")
    inspiration: str = Field(min_length=1)
    provider: str | None = Field(default=None)


class StudioAngle(BaseModel):
    id: str
    title: str
    description: str


class StudioLockConceptRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    angle_id: str = Field(default="")
    feedback: str = Field(default="")
    provider: str | None = Field(default=None)


class StudioBlueprintRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    bible: ConceptBible
    title: str = Field(default="未命名短视频")
    idea: str = Field(min_length=1)
    genre: str = Field(default="")
    creative_preset: str = Field(default="default")
    duration_seconds: int = Field(default=30, ge=5, le=600)
    scene_count: int = Field(default=5, ge=1, le=30)
    resolution: Literal["9:16", "16:9", "1:1"] = Field(default="9:16")
    provider: str | None = Field(default=None)


def generator() -> VideoScriptGenerator:
    return VideoScriptGenerator()


@router.post("/brainstorm")
def brainstorm(payload: StudioBrainstormRequest) -> dict[str, Any]:
    try:
        provider = payload.provider or active_ai_provider("mock")
        if provider == "mock":
            return {"angles": _mock_angles(payload), "provider": provider}
        prompt = "\n\n".join(
            [
                "Return JSON only.",
                "Generate three distinct short-video story angles. Do not write scenes.",
                'Schema: {"angles":[{"id":"a1","title":"","description":""}]}',
                f"Video type: {payload.type}",
                f"Inspiration: {payload.inspiration}",
            ]
        )
        data = generator()._parse_json(generator()._call_model(provider, prompt))
        angles = data.get("angles") if isinstance(data.get("angles"), list) else []
        normalized = _normalize_angles(angles) or _mock_angles(payload)
        return {"angles": normalized, "provider": provider}
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error_type": type(exc).__name__, "message": str(exc)}) from exc


@router.post("/lock_concept")
def lock_concept(payload: StudioLockConceptRequest) -> dict[str, Any]:
    try:
        seed = payload.context.get("seed") if isinstance(payload.context.get("seed"), dict) else {}
        angle = payload.context.get("angle") if isinstance(payload.context.get("angle"), dict) else {}
        idea = seed.get("idea") or seed.get("inspiration") or angle.get("description") or payload.feedback or "短视频灵感"
        title = seed.get("title") or idea[:18] or "未命名短视频"
        genre = seed.get("genre") or seed.get("type") or ""
        creative_preset = seed.get("creativePreset") or seed.get("creative_preset") or "default"
        request = BibleGenerateRequest(
            title=title,
            idea=f"{idea}\nSelected angle: {angle.get('title', payload.angle_id)}\nFeedback: {payload.feedback}",
            genre=genre,
            creative_preset=creative_preset,
            provider=payload.provider,
        )
        result = generator().generate_bible(request)
        return {"bible": result["bible"], "provider": result.get("provider")}
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error_type": type(exc).__name__, "message": str(exc)}) from exc


@router.post("/generate_blueprint")
def generate_blueprint(payload: StudioBlueprintRequest) -> dict[str, Any]:
    try:
        project_id = uuid4().hex
        result = generator().generate_blueprint_with_project_id(
            BlueprintGenerateRequest(
                title=payload.title,
                idea=payload.idea,
                genre=payload.genre,
                creative_preset=payload.creative_preset,
                bible=payload.bible,
                duration_seconds=payload.duration_seconds,
                scene_count=payload.scene_count,
                resolution=payload.resolution,
                provider=payload.provider,
            ),
            project_id,
        )
        script = result["script"]
        return {
            "project_id": project_id,
            "script": script,
            "scenes": script.get("scenes", []),
            "script_path": result.get("script_path", ""),
            "provider": result.get("provider", ""),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error_type": type(exc).__name__, "message": str(exc)}) from exc


def _mock_angles(payload: StudioBrainstormRequest) -> list[dict[str, str]]:
    inspiration = payload.inspiration.strip()
    return [
        {"id": "a1", "title": "情绪共鸣流", "description": f"从用户对“{inspiration}”的焦虑或好奇切入，先让观众觉得被说中。"},
        {"id": "a2", "title": "干货破解流", "description": f"把“{inspiration}”拆成三个容易理解的判断点，制造收藏价值。"},
        {"id": "a3", "title": "反转故事流", "description": f"先给出一个看似普通的场景，再用“{inspiration}”完成反转和行动引导。"},
    ]


def _normalize_angles(items: list[Any]) -> list[dict[str, str]]:
    angles: list[dict[str, str]] = []
    for index, item in enumerate(items[:3], start=1):
        if not isinstance(item, dict):
            continue
        angles.append(
            StudioAngle(
                id=str(item.get("id") or f"a{index}"),
                title=str(item.get("title") or f"方向 {index}"),
                description=str(item.get("description") or item.get("summary") or ""),
            ).model_dump()
        )
    return angles
