from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.ai_provider_state import active_ai_provider
from backend.app.benchmark_comments import build_comment_insights
from backend.app.benchmark_config import load_metric_config, save_metric_config
from backend.app.benchmark_index import filtered_items, load_index, page, rebuild_index
from backend.app.benchmark_metrics import sort_items
from backend.app.benchmark_patterns import build_pattern_library, save_pattern_override
from integrations.video_pipeline.script_generator import VideoScriptGenerator

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])


class ReindexRequest(BaseModel):
    mode: str = Field(default="incremental", pattern="^(incremental|full)$")


class MetricConfigRequest(BaseModel):
    public_engagement_weights: dict[str, float] = Field(default_factory=dict)
    reindex: bool = True


class PatternUpdateRequest(BaseModel):
    name: str = ""
    description: str = ""
    manual_notes: str = ""


class ProfileAnalysisRequest(BaseModel):
    provider: str | None = None


def _dataset() -> dict[str, Any]:
    return load_index()


def _plain(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _public_meta(meta: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in (meta or {}).items() if key != "job_files"}


def _videos(
    dataset: dict[str, Any],
    genre: str = "",
    q: str = "",
    author_id: str = "",
    pattern_id: str = "",
) -> list[dict[str, Any]]:
    items = filtered_items(dataset["videos"], genre=genre, q=q)
    if author_id:
        items = [item for item in items if str(item.get("author_id") or "") == author_id]
    if pattern_id:
        items = [item for item in items if str(item.get("pattern_id") or "") == pattern_id]
    return items


def _string_list(value: Any, fallback: list[str] | None = None) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        if items:
            return items
    return list(fallback or [])


def _normalize_profile_analysis(data: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    return {
        "persona_type": str(payload.get("persona_type") or fallback.get("persona_type") or "内容型账号"),
        "summary": str(payload.get("summary") or fallback.get("summary") or ""),
        "commerce_signals": _string_list(payload.get("commerce_signals"), fallback.get("commerce_signals") or []),
        "trust_signals": _string_list(payload.get("trust_signals"), fallback.get("trust_signals") or []),
        "risk_signals": _string_list(payload.get("risk_signals"), fallback.get("risk_signals") or []),
        "learning_focus": _string_list(payload.get("learning_focus"), fallback.get("learning_focus") or []),
    }


@router.get("/overview")
def benchmark_overview(genre: str = Query(default="")) -> dict[str, Any]:
    genre = _plain(genre)
    dataset = _dataset()
    if not genre or genre == "全部类型":
        return {**dataset["overview"], "index_meta": _public_meta(dataset["meta"])}
    videos = filtered_items(dataset["videos"], genre=genre)
    authors = filtered_items(dataset["authors"], genre=genre)
    return {
        "analysis_task_count": sum(len(video.get("job_ids") or [video.get("job_id")]) for video in videos),
        "unique_video_count": len(videos),
        "author_count": len(authors),
        "segment_count": sum(int(video.get("segment_count") or 0) for video in videos),
        "avg_imitation_value": round(
            sum(float(video.get("imitation_value") or 0) for video in videos) / len(videos)
        )
        if videos
        else 0,
        "content_type_counts": {genre: len(videos)},
        "public_signal_video_count": sum(
            1
            for video in videos
            if any(int(video.get(key) or 0) > 0 for key in ("digg_count", "comment_count", "collect_count", "share_count"))
        ),
        "comment_quality_video_count": sum(
            1 for video in videos if (video.get("comment_quality") or {}).get("status") == "ready"
        ),
        "evaluation_scope": "public_competitor_only",
        "index_meta": _public_meta(dataset["meta"]),
    }


@router.get("/videos")
def benchmark_videos(
    genre: str = Query(default=""),
    rank_type: str = Query(default="overall"),
    author_id: str = Query(default=""),
    pattern_id: str = Query(default=""),
    q: str = Query(default=""),
    sort: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    genre = _plain(genre)
    rank_type = _plain(rank_type, "overall")
    author_id = _plain(author_id)
    pattern_id = _plain(pattern_id)
    q = _plain(q)
    sort = _plain(sort)
    dataset = _dataset()
    items = _videos(dataset, genre=genre, q=q, author_id=author_id, pattern_id=pattern_id)
    items = sort_items(items, sort or rank_type)
    return page(items, limit=limit, offset=offset)


@router.get("/videos/{video_id}")
def benchmark_video_detail(video_id: str) -> dict[str, Any]:
    dataset = _dataset()
    for video in dataset["videos"]:
        if video_id in {str(video.get("video_id")), str(video.get("aweme_id")), str(video.get("job_id"))}:
            return {
                "video": video,
                "author": video.get("author") or {},
                "metrics": {
                    "digg_count": video.get("digg_count"),
                    "comment_count": video.get("comment_count"),
                    "collect_count": video.get("collect_count"),
                    "share_count": video.get("share_count"),
                    "collect_tendency": video.get("collect_tendency"),
                    "comment_tendency": video.get("comment_tendency"),
                    "share_tendency": video.get("share_tendency"),
                    "public_engagement_score": video.get("public_engagement_score"),
                    "small_account_efficiency": video.get("small_account_efficiency"),
                },
                "comment_quality": video.get("comment_quality") or {},
                "summary": video.get("summary") or "",
                "opening_3s": video.get("opening_3s") or "",
                "replicable_point": video.get("replicable_point") or "",
                "replication_action": video.get("replication_action") or "",
                "risk_level": video.get("risk_level") or "",
                "task_id": video.get("task_id") or "",
                "job_id": video.get("job_id") or "",
                "evidence_path": video.get("evidence_path") or "",
                "task_center_url": f"/tasks/{video.get('task_id')}" if video.get("task_id") else "",
            }
    raise HTTPException(status_code=404, detail="Benchmark video not found")


@router.get("/authors")
def benchmark_authors(
    genre: str = Query(default=""),
    sort: str = Query(default="benchmark"),
    min_samples: int = Query(default=0, ge=0),
    q: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    genre = _plain(genre)
    sort = _plain(sort, "benchmark")
    q = _plain(q)
    dataset = _dataset()
    items = filtered_items(dataset["authors"], genre=genre, q=q)
    if min_samples:
        items = [item for item in items if int(item.get("sample_count") or 0) >= min_samples]
    sort_map = {
        "collect": "avg_collect_tendency",
        "comment": "avg_comment_tendency",
        "small_account": "avg_small_account_efficiency",
        "imitation": "avg_imitation_value",
        "benchmark": "benchmark_score",
    }
    items = sort_items(items, sort_map.get(sort, sort), default_key="benchmark_score")
    return page(items, limit=limit, offset=offset)


@router.get("/authors/{author_id}")
def benchmark_author_detail(author_id: str) -> dict[str, Any]:
    dataset = _dataset()
    author = next((item for item in dataset["authors"] if str(item.get("author_id") or "") == author_id), None)
    if not author:
        raise HTTPException(status_code=404, detail="Benchmark author not found")
    videos = [video for video in dataset["videos"] if str(video.get("author_id") or "") == author_id]
    videos = sort_items(videos, "overall")[:10]
    return {
        "author": author,
        "profile": {
            "positioning": author.get("positioning") or "",
            "content_types": sorted({video.get("content_type") or "未分类" for video in videos}),
            "learning_points": author.get("learning_points") or [],
            "common_hooks": [video.get("opening_3s") for video in videos if video.get("opening_3s")][:5],
            "risk_notes": sorted({video.get("risk_level") or "未知" for video in videos}),
        },
        "metrics": author,
        "representative_videos": videos[:5],
    }


@router.post("/authors/{author_id}/profile-analysis")
def benchmark_author_profile_analysis(author_id: str, payload: ProfileAnalysisRequest | None = None) -> dict[str, Any]:
    dataset = _dataset()
    author = next((item for item in dataset["authors"] if str(item.get("author_id") or "") == author_id), None)
    if not author:
        raise HTTPException(status_code=404, detail="Benchmark author not found")
    videos = [video for video in dataset["videos"] if str(video.get("author_id") or "") == author_id]
    videos = sort_items(videos, "overall")[:12]
    fallback = author.get("profile_analysis") if isinstance(author.get("profile_analysis"), dict) else {}
    provider = (payload.provider if payload else None) or active_ai_provider("mock")
    if provider == "mock":
        return {"analysis": _normalize_profile_analysis(fallback, fallback), "provider": "local_rules", "source": "local_rules"}

    prompt = "\n\n".join(
        [
            "你是短视频对标分析师。只返回 JSON，不要解释。",
            'Schema: {"persona_type":"","summary":"","commerce_signals":[],"trust_signals":[],"risk_signals":[],"learning_focus":[]}',
            "任务：结合博主简介、标题、AI拆解摘要，判断账号定位、人设、转化线索、信任线索、风险信号和可学习重点。",
            f"博主：{author.get('nickname') or '未知博主'}",
            f"简介：{author.get('signature') or '暂无'}",
            "样本："
            + "\n".join(
                [
                    f"- 标题：{video.get('desc') or ''}；开头：{video.get('opening_3s') or ''}；复刻点：{video.get('replicable_point') or ''}；摘要：{video.get('summary') or ''}"
                    for video in videos
                ]
            ),
            "要求：summary 不超过 60 字；risk_signals 只列需要改写规避的词或表达；learning_focus 给 2-4 条可执行学习点。",
        ]
    )
    try:
        generator = VideoScriptGenerator()
        raw = generator._call_model(provider, prompt)
        data = generator._parse_json(raw)
        return {"analysis": _normalize_profile_analysis(data, fallback), "provider": provider, "source": "ai"}
    except Exception as exc:
        return {
            "analysis": _normalize_profile_analysis(fallback, fallback),
            "provider": provider,
            "source": "local_rules",
            "warning": f"{type(exc).__name__}: {exc}",
        }


@router.get("/authors/{author_id}/videos")
def benchmark_author_videos(
    author_id: str,
    sort: str = Query(default="overall"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    dataset = _dataset()
    items = [video for video in dataset["videos"] if str(video.get("author_id") or "") == author_id]
    items = sort_items(items, sort)
    return page(items, limit=limit, offset=offset)


@router.get("/comments/insights")
def benchmark_comment_insights(
    genre: str = Query(default=""),
    author_id: str = Query(default=""),
    pattern_id: str = Query(default=""),
) -> dict[str, Any]:
    genre = _plain(genre)
    author_id = _plain(author_id)
    pattern_id = _plain(pattern_id)
    dataset = _dataset()
    return build_comment_insights(_videos(dataset, genre=genre, author_id=author_id, pattern_id=pattern_id))


@router.get("/patterns")
def benchmark_patterns(
    genre: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    genre = _plain(genre)
    dataset = _dataset()
    items = build_pattern_library(dataset["videos"], genre=genre) if genre else dataset["patterns"]
    return page(items, limit=limit, offset=offset)


@router.get("/patterns/{pattern_id}")
def benchmark_pattern_detail(pattern_id: str, genre: str = Query(default="")) -> dict[str, Any]:
    genre = _plain(genre)
    dataset = _dataset()
    patterns = build_pattern_library(dataset["videos"], genre=genre) if genre else dataset["patterns"]
    pattern = next((item for item in patterns if str(item.get("pattern_id") or "") == pattern_id), None)
    if not pattern:
        raise HTTPException(status_code=404, detail="Benchmark pattern not found")
    representative_ids = set(pattern.get("representative_video_ids") or [])
    videos = [
        video
        for video in dataset["videos"]
        if video.get("video_id") in representative_ids or video.get("pattern_id") == pattern_id
    ]
    videos = sort_items(videos, "overall")[:10]
    return {
        "pattern": pattern,
        "representative_videos": videos,
        "metrics": {
            "video_count": pattern.get("video_count") or len(videos),
            "avg_imitation_value": pattern.get("avg_imitation_value") or 0,
            "avg_comment_quality_score": pattern.get("avg_comment_quality_score") or 0,
            "avg_collect_tendency": pattern.get("avg_collect_tendency") or 0,
            "avg_comment_tendency": pattern.get("avg_comment_tendency") or 0,
            "avg_share_tendency": pattern.get("avg_share_tendency") or 0,
            "avg_public_engagement_score": pattern.get("avg_public_engagement_score") or 0,
        },
    }


@router.put("/patterns/{pattern_id}")
def benchmark_update_pattern(pattern_id: str, payload: PatternUpdateRequest) -> dict[str, Any]:
    values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    save_pattern_override(pattern_id, values)
    rebuild_index("full")
    return benchmark_pattern_detail(pattern_id)


@router.get("/filters")
def benchmark_filters() -> dict[str, Any]:
    dataset = _dataset()
    content_types = sorted({video.get("content_type") or "未分类" for video in dataset["videos"]})
    return {
        "content_types": content_types,
        "rank_types": ["overall", "small_account", "collect", "comment"],
        "author_sorts": ["benchmark", "collect", "comment", "small_account", "imitation"],
        "metric_config": load_metric_config(),
        "index_meta": _public_meta(dataset["meta"]),
    }


@router.get("/metric-config")
def benchmark_metric_config() -> dict[str, Any]:
    dataset = _dataset()
    return {"config": load_metric_config(), "index_meta": _public_meta(dataset["meta"])}


@router.put("/metric-config")
def benchmark_update_metric_config(payload: MetricConfigRequest) -> dict[str, Any]:
    config = save_metric_config(payload.public_engagement_weights)
    meta = rebuild_index("full") if payload.reindex else _dataset()["meta"]
    return {"config": config, "index_meta": _public_meta(meta)}


@router.post("/reindex")
def benchmark_reindex(payload: ReindexRequest | None = None) -> dict[str, Any]:
    mode = payload.mode if payload else "incremental"
    return _public_meta(rebuild_index(mode=mode))
