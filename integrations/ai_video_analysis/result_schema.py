from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "；".join(_text(item) for item in value if _text(item))
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values() if _text(item))
    return str(value)


def _score(value: Any) -> int:
    try:
        number = int(float(str(value).replace("分", "").strip()))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ContentIdentity(FlexibleModel):
    track: str = ""
    niche_fit: str = ""
    account_persona: str = ""


class CoreHook(FlexibleModel):
    opening_3s: str = ""
    curiosity_gap: str = ""
    emotional_trigger: str = ""
    comment_bait: str = ""


class NeedContext(FlexibleModel):
    pain_point: str = ""
    application_scene: str = ""
    hidden_desire: str = ""


class ProductPower(FlexibleModel):
    core_benefit: str = ""
    trigger_moment: str = ""
    trust_builder: str = ""
    product_role: str = ""


class VisualStructure(FlexibleModel):
    shot_structure: str = ""
    reusable_elements: str = ""
    timeline_beats: str | list[Any] = ""
    audio_rhythm: str = ""


class CopywritingFormula(FlexibleModel):
    title_formula: str = ""
    script_formula: str = ""
    golden_lines: str | list[Any] = ""
    cta: str = ""


class MarketPositioning(FlexibleModel):
    suitable_products: str = ""
    target_audience: str = ""
    creative_direction: str = ""


class ReplicationPlan(FlexibleModel):
    pattern_name: str = ""
    reusable_formula: str = ""
    cross_genre_variants: str | list[Any] = ""
    mysticism_variant: str = ""
    ai_pet_variant: str = ""
    ai_commerce_variant: str = ""
    difficulty: str = ""
    priority: str = ""


class RiskControl(FlexibleModel):
    risk_level: str = ""
    platform_risks: str | list[Any] = ""
    safe_rewrite: str = ""


class ViralScores(FlexibleModel):
    viral_potential: int = Field(default=0, ge=0, le=100)
    imitation_value: int = Field(default=0, ge=0, le=100)
    commerce_value: int = Field(default=0, ge=0, le=100)
    comment_potential: int = Field(default=0, ge=0, le=100)
    overall: int = Field(default=0, ge=0, le=100)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_score(cls, value: Any) -> int:
        return _score(value)


class SegmentBreakdown(FlexibleModel):
    segment_id: str = ""
    time_range: str = ""
    genre: str = ""
    segment_role: str = ""
    visual_style: str = ""
    audio_pacing: str = ""
    narrative_technique: str = ""
    retention_mechanism: str = ""
    transcript: str = ""
    start: float | None = None
    end: float | None = None

    @field_validator("segment_id", "time_range", "genre", "segment_role", "visual_style", "audio_pacing", "narrative_technique", "retention_mechanism", "transcript", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return _text(value)


class EvidenceMetadata(FlexibleModel):
    evidence_path: str = ""
    transcript_provider: str = ""
    transcript_model: str = ""
    transcript_language: str = ""
    transcript_segments_count: int = 0
    analysis_segments_count: int = 0
    keyframes_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommentCollectionState(FlexibleModel):
    status: str = ""
    video_id: str = ""
    aweme_id: str = ""
    snapshot_at: int | None = None
    comment_saved_count: int = 0
    reply_saved_count: int = 0
    error: str = ""
    reason: str = ""


class AnalysisResult(FlexibleModel):
    genre: str = ""
    summary: str = ""
    content_identity: ContentIdentity = Field(default_factory=ContentIdentity)
    core_hook: CoreHook = Field(default_factory=CoreHook)
    need_context: NeedContext = Field(default_factory=NeedContext)
    product_power: ProductPower = Field(default_factory=ProductPower)
    visual_structure: VisualStructure = Field(default_factory=VisualStructure)
    copywriting_formula: CopywritingFormula = Field(default_factory=CopywritingFormula)
    market_positioning: MarketPositioning = Field(default_factory=MarketPositioning)
    replication_plan: ReplicationPlan = Field(default_factory=ReplicationPlan)
    standard_remake_template: str = ""
    risk_control: RiskControl = Field(default_factory=RiskControl)
    viral_scores: ViralScores = Field(default_factory=ViralScores)
    segment_breakdowns: list[SegmentBreakdown] = Field(default_factory=list)
    evidence: EvidenceMetadata | dict[str, Any] = Field(default_factory=dict)
    comment_collection: CommentCollectionState | dict[str, Any] = Field(default_factory=dict)
    raw_model_json: dict[str, Any] = Field(default_factory=dict)
    raw_model_text: str = ""

    @field_validator("genre", "summary", "standard_remake_template", "raw_model_text", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return _text(value)


def validate_analysis_result(value: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    model = AnalysisResult.model_validate(raw)
    data = model.model_dump(mode="python")
    for key, extra_value in raw.items():
        if key not in data:
            data[key] = extra_value
    if not data.get("raw_model_json"):
        data["raw_model_json"] = raw.get("raw_model_json") if isinstance(raw.get("raw_model_json"), dict) else raw
    return data


def validate_segment_breakdown(value: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    model = SegmentBreakdown.model_validate(raw)
    data = model.model_dump(mode="python")
    for key, extra_value in raw.items():
        if key not in data:
            data[key] = extra_value
    return data

