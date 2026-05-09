from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VideoScriptConfig(BaseModel):
    title: str = Field(default="未命名短视频")
    genre: str = Field(default="")
    resolution: Literal["9:16", "16:9", "1:1"] = Field(default="9:16")
    fps: int = Field(default=30, ge=1, le=120)
    style: str = Field(default="")
    audience: str = Field(default="")
    total_duration_seconds: float = Field(default=0, ge=0)


class SceneAssets(BaseModel):
    video_path: str = Field(default="")
    image_path: str = Field(default="")
    audio_path: str = Field(default="")
    duration: float = Field(default=0, ge=0)


class SceneEdit(BaseModel):
    transition: str = Field(default="fade")
    animation: str = Field(default="zoom_in")
    pacing: str = Field(default="")
    camera: str = Field(default="")


class ConceptBible(BaseModel):
    art_style_prompt: str = Field(default="", description="Global visual style prompt.")
    character_base_prompt: str = Field(default="", description="Fixed protagonist visual prompt.")
    voice_vibe: str = Field(default="", description="Global TTS voice direction.")
    bgm_keywords: str = Field(default="", description="Background music search keywords.")


class SceneAssetRequirements(BaseModel):
    visual_type: str = Field(default="video_or_image")
    main_subject: str = Field(default="")
    background: str = Field(default="")
    mood: str = Field(default="")
    must_have: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class VideoScene(BaseModel):
    id: int = Field(ge=1)
    title: str = Field(default="")
    summary: str = Field(default="")
    estimated_duration: float = Field(default=3, ge=0)
    scene_goal: str = Field(default="")
    audio_narration: str = Field(default="")
    onscreen_text: str = Field(default="")
    visual_prompt: str = Field(default="")
    asset_requirements: SceneAssetRequirements = Field(default_factory=SceneAssetRequirements)
    assets: SceneAssets = Field(default_factory=SceneAssets)
    edit: SceneEdit = Field(default_factory=SceneEdit)
    status: str = Field(default="waiting_assets")


class VideoScript(BaseModel):
    project_id: str
    config: VideoScriptConfig
    bible: ConceptBible | None = Field(default=None)
    scenes: list[VideoScene] = Field(default_factory=list)


class ScriptGenerateRequest(BaseModel):
    title: str = Field(default="未命名短视频")
    idea: str = Field(min_length=1)
    creative_preset: str = Field(default="default")
    genre: str = Field(default="")
    style: str = Field(default="")
    audience: str = Field(default="")
    tone: str = Field(default="")
    structure: str = Field(default="")
    cta: str = Field(default="")
    duration_seconds: int = Field(default=30, ge=5, le=600)
    scene_count: int = Field(default=5, ge=1, le=30)
    resolution: Literal["9:16", "16:9", "1:1"] = Field(default="9:16")
    provider: str | None = Field(default=None)


class NaturalLanguageScriptRequest(BaseModel):
    input: str = Field(min_length=1)
    title: str = Field(default="")
    creative_preset: str = Field(default="")
    duration_seconds: int | None = Field(default=None, ge=5, le=600)
    scene_count: int | None = Field(default=None, ge=1, le=30)
    resolution: Literal["", "9:16", "16:9", "1:1"] = Field(default="")
    generation_mode: Literal["local", "skill_contract", "sdk"] = Field(default="local")
    provider: str | None = Field(default=None)


class BibleGenerateRequest(BaseModel):
    title: str = Field(default="未命名短视频")
    idea: str = Field(min_length=1)
    genre: str = Field(default="")
    creative_preset: str = Field(default="default")
    provider: str | None = Field(default=None)


class BlueprintGenerateRequest(BaseModel):
    title: str = Field(default="未命名短视频")
    idea: str = Field(min_length=1)
    genre: str = Field(default="")
    creative_preset: str = Field(default="default")
    bible: ConceptBible
    duration_seconds: int = Field(default=30, ge=5, le=600)
    scene_count: int = Field(default=5, ge=1, le=30)
    resolution: Literal["9:16", "16:9", "1:1"] = Field(default="9:16")
    provider: str | None = Field(default=None)


class ScriptSaveRequest(BaseModel):
    script: VideoScript


class ScriptExpandRequest(BaseModel):
    idea: str = Field(default="")
    expand_count: int = Field(default=1, ge=1, le=5)
    provider: str | None = Field(default=None)


class ScriptPrepareAssetsRequest(BaseModel):
    script: VideoScript | None = Field(default=None)
    source_paths: list[str] = Field(default_factory=list)
    resolve_local_materials: bool = Field(default=True)
    generate_audio: bool = Field(default=True)
    generate_images: bool = Field(default=True)
    generate_videos: bool = Field(default=False)
    overwrite_existing: bool = Field(default=False)
    ffprobe_binary: str = Field(default="ffprobe")
    tts_provider: str = Field(default="openai")
    tts_model: str = Field(default="gpt-4o-mini-tts")
    tts_voice: str = Field(default="alloy")
    tts_format: str = Field(default="mp3")
    image_provider: str = Field(default="gemini")
    image_model: str = Field(default="imagen-4.0-generate-001")
