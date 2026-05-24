from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .benchmark_comments import analyze_comments, extract_comment_snapshot
from .benchmark_config import load_metric_config
from .benchmark_metrics import average, benchmark_author_score, int_number, sort_items, video_metric_summary
from .benchmark_patterns import build_pattern_library, classify_video_pattern

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_AI_VIDEO_DIR = ROOT_DIR / "data" / "runtime" / "ai_video_analysis"
DEFAULT_INDEX_DIR = ROOT_DIR / "data" / "runtime" / "benchmark_index"
INDEX_VERSION = 5
_INDEX_LOCK = threading.RLock()


def ai_video_dir() -> Path:
    return Path(os.getenv("BENCHMARK_AI_VIDEO_DIR") or DEFAULT_AI_VIDEO_DIR).resolve()


def index_dir() -> Path:
    return Path(os.getenv("BENCHMARK_INDEX_DIR") or DEFAULT_INDEX_DIR).resolve()


def _read_json(path: Path) -> Any | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def _job_files() -> list[Path]:
    jobs_dir = ai_video_dir() / "jobs"
    if not jobs_dir.exists():
        return []
    return sorted(jobs_dir.glob("target-breakdown-*.json"))


def _job_signature(path: Path) -> dict[str, int | str]:
    stat = path.stat()
    return {"mtime": int(stat.st_mtime), "size": int(stat.st_size), "path": str(path)}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    return str(value)


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _author_id(author: dict[str, Any], fallback: str) -> str:
    return str(
        _first(
            author.get("sec_uid"),
            author.get("sec_user_id"),
            author.get("uid"),
            author.get("user_id"),
            author.get("id"),
            author.get("nickname"),
            fallback,
        )
    )


def _content_type(result: dict[str, Any], video: dict[str, Any]) -> str:
    content_identity = result.get("content_identity") if isinstance(result.get("content_identity"), dict) else {}
    raw = str(_first(content_identity.get("track"), result.get("genre"), video.get("genre"), "") or "")
    haystack = " ".join([raw, _text(video.get("desc"))])
    if any(keyword in haystack for keyword in ["塔罗", "玄学", "占卜", "守护灵", "正缘"]):
        return "玄学塔罗"
    if any(keyword in haystack for keyword in ["动漫", "解说", "番", "剧情"]):
        return "动漫解说"
    if any(keyword in haystack for keyword in ["vlog", "Vlog", "日常", "生活"]):
        return "原创 Vlog"
    if any(keyword in haystack for keyword in ["好物", "种草", "推荐", "商品"]):
        return "好物种草"
    if any(keyword in haystack for keyword in ["教学", "教程", "知识", "学习"]):
        return "知识教程"
    return raw or "未分类"


def _risk_level(result: dict[str, Any]) -> str:
    risk = result.get("risk_control") if isinstance(result.get("risk_control"), dict) else {}
    return str(risk.get("risk_level") or "未知")


def _normalize_video(
    job: dict[str, Any],
    path: Path,
    weights: dict[str, float] | None = None,
) -> dict[str, Any] | None:
    video = job.get("video") if isinstance(job.get("video"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    if not video:
        return None
    aweme_id = str(_first(video.get("aweme_id"), video.get("id"), path.stem) or path.stem)
    author = video.get("author") if isinstance(video.get("author"), dict) else {}
    author_id = _author_id(author, aweme_id)
    metrics = video_metric_summary(video, author, weights=weights)
    comment_snapshot = extract_comment_snapshot(job)
    comment_quality = analyze_comments(comment_snapshot)
    viral_scores = result.get("viral_scores") if isinstance(result.get("viral_scores"), dict) else {}
    core_hook = result.get("core_hook") if isinstance(result.get("core_hook"), dict) else {}
    psychology = result.get("psychology_breakdown") if isinstance(result.get("psychology_breakdown"), dict) else {}
    copywriting = result.get("copywriting_formula") if isinstance(result.get("copywriting_formula"), dict) else {}
    replication = result.get("replication_plan") if isinstance(result.get("replication_plan"), dict) else {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    content_type = _content_type(result, video)
    normalized = {
        "video_id": aweme_id,
        "aweme_id": aweme_id,
        "job_id": str(job.get("job_id") or path.stem),
        "task_id": str(_first(job.get("task_id"), video.get("analysis_task_id"), job.get("job_id"), path.stem) or ""),
        "job_path": str(path),
        "evidence_path": str(evidence.get("evidence_path") or ""),
        "desc": str(video.get("desc") or ""),
        "cover_url": str(video.get("cover_url") or ""),
        "play_url": str(video.get("play_url") or video.get("video_url") or ""),
        "publish_time": int_number(video.get("create_time")),
        "content_type": content_type,
        "genre": str(_first(result.get("genre"), content_type) or content_type),
        "author_id": author_id,
        "author_name": str(_first(author.get("nickname"), author.get("name"), "未知博主") or "未知博主"),
        "author": {
            "author_id": author_id,
            "nickname": str(_first(author.get("nickname"), author.get("name"), "未知博主") or "未知博主"),
            "avatar_url": str(_first(author.get("avatar_url"), author.get("avatar"), "") or ""),
            "signature": str(_first(author.get("signature"), author.get("desc"), "") or ""),
            "follower_count": int_number(author.get("follower_count")),
            "total_favorited": int_number(_first(author.get("total_favorited"), author.get("like_count"))),
            "aweme_count": int_number(author.get("aweme_count")),
        },
        "summary": str(result.get("summary") or ""),
        "opening_3s": str(core_hook.get("opening_3s") or ""),
        "curiosity_gap": str(core_hook.get("curiosity_gap") or ""),
        "emotional_trigger": str(core_hook.get("emotional_trigger") or ""),
        "replicable_point": str(psychology.get("replicable_point") or replication.get("reusable_formula") or ""),
        "replication_action": str(psychology.get("replication_action") or replication.get("mysticism_variant") or ""),
        "pattern_name": str(replication.get("pattern_name") or ""),
        "title_formula": str(copywriting.get("title_formula") or ""),
        "risk_level": _risk_level(result),
        "segment_count": len(result.get("segment_breakdowns") or []),
        "viral_potential": int_number(viral_scores.get("viral_potential")),
        "imitation_value": int_number(viral_scores.get("imitation_value")),
        "commerce_value": int_number(viral_scores.get("commerce_value")),
        "comment_potential": int_number(viral_scores.get("comment_potential")),
        "overall_score": int_number(viral_scores.get("overall")),
        "updated_at": int(path.stat().st_mtime),
    }
    normalized.update(metrics)
    normalized["comment_quality"] = comment_quality
    normalized.update(classify_video_pattern(normalized))
    return normalized


def _merge_duplicate(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if candidate.get("updated_at", 0) >= existing.get("updated_at", 0):
        merged = {**candidate}
        merged["job_ids"] = sorted(set((existing.get("job_ids") or [existing.get("job_id")]) + [candidate.get("job_id")]))
        return merged
    existing["job_ids"] = sorted(set((existing.get("job_ids") or [existing.get("job_id")]) + [candidate.get("job_id")]))
    return existing


def _build_authors(videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for video in videos:
        grouped[str(video.get("author_id") or "unknown")].append(video)

    authors: list[dict[str, Any]] = []
    for author_id, rows in grouped.items():
        first = rows[0]
        author = first.get("author") if isinstance(first.get("author"), dict) else {}
        risk_counts = Counter(row.get("risk_level") or "未知" for row in rows)
        content_counts = Counter(row.get("content_type") or "未分类" for row in rows)
        item = {
            "author_id": author_id,
            "nickname": author.get("nickname") or first.get("author_name") or "未知博主",
            "avatar_url": author.get("avatar_url") or "",
            "signature": author.get("signature") or "",
            "positioning": _author_positioning(rows),
            "content_type": content_counts.most_common(1)[0][0] if content_counts else "未分类",
            "sample_count": sum(len(row.get("job_ids") or [row.get("job_id")]) for row in rows),
            "video_count": len(rows),
            "follower_count": author.get("follower_count") or 0,
            "total_favorited": author.get("total_favorited") or 0,
            "aweme_count": author.get("aweme_count") or 0,
            "avg_collect_tendency": average([row.get("collect_tendency") for row in rows]),
            "avg_comment_tendency": average([row.get("comment_tendency") for row in rows]),
            "avg_share_tendency": average([row.get("share_tendency") for row in rows]),
            "avg_small_account_efficiency": average([row.get("small_account_efficiency") for row in rows]),
            "avg_imitation_value": average([row.get("imitation_value") for row in rows]),
            "avg_public_engagement_score": average([row.get("public_engagement_score") for row in rows]),
            "risk_level": risk_counts.most_common(1)[0][0] if risk_counts else "未知",
            "representative_video_ids": [row["video_id"] for row in sort_items(rows, "overall")[:5]],
            "learning_points": _learning_points(rows),
        }
        item["profile_analysis"] = _author_profile_analysis(item, rows)
        item["benchmark_score"] = benchmark_author_score(item)
        authors.append(item)
    return sort_items(authors, "benchmark", default_key="benchmark_score")


def _author_positioning(rows: list[dict[str, Any]]) -> str:
    content_type = Counter(row.get("content_type") or "未分类" for row in rows).most_common(1)[0][0]
    signals = []
    if average([row.get("collect_tendency") for row in rows]) >= 0.12:
        signals.append("收藏倾向高")
    if average([row.get("comment_tendency") for row in rows]) >= 0.08:
        signals.append("评论驱动强")
    if average([row.get("share_tendency") for row in rows]) >= 0.12:
        signals.append("分享传播强")
    if average([row.get("imitation_value") for row in rows]) >= 85:
        signals.append("复刻价值高")
    return " / ".join([content_type, *signals[:3]])


def _learning_points(rows: list[dict[str, Any]]) -> list[str]:
    points = []
    if average([row.get("collect_tendency") for row in rows]) >= 0.12:
        points.append("收藏价值")
    if average([row.get("comment_tendency") for row in rows]) >= 0.08:
        points.append("评论驱动")
    if average([row.get("share_tendency") for row in rows]) >= 0.12:
        points.append("传播钩子")
    if any(row.get("opening_3s") for row in rows):
        points.append("开头钩子")
    if average([row.get("imitation_value") for row in rows]) >= 85:
        points.append("复刻结构")
    return points[:5] or ["内容结构"]


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword and keyword in text]


def _author_profile_analysis(author: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    signature = str(author.get("signature") or "")
    corpus = " ".join(
        [
            signature,
            str(author.get("nickname") or ""),
            " ".join(str(row.get("desc") or "") for row in rows[:12]),
            " ".join(str(row.get("summary") or "") for row in rows[:8]),
        ]
    )
    persona = "内容型账号"
    if _keyword_hits(corpus, ["教学", "教程", "新手", "课程", "招生", "学习"]):
        persona = "教学/课程型"
    elif _keyword_hits(corpus, ["疗愈", "治愈", "能量", "陪伴", "心灵", "守护"]):
        persona = "疗愈陪伴型"
    elif _keyword_hits(corpus, ["私占", "接占", "占卜", "传讯", "有缘人"]):
        persona = "私占转化型"

    commerce_hits = _keyword_hits(corpus, ["收徒", "课程", "招生", "私信", "微信", "vx", "VX", "V：", "小号", "矩阵", "橱窗", "接占"])
    trust_hits = _keyword_hits(corpus, ["原创", "认证", "官方", "唯一", "本人", "专业", "国际", "独家", "禁止搬运"])
    risk_hits = _keyword_hits(corpus, ["私信", "微信", "vx", "VX", "收徒", "接占", "神明", "逆天改命", "暴富", "复合"])

    learning_focus = []
    if average([row.get("collect_tendency") for row in rows]) >= 0.12:
        learning_focus.append("简介与内容共同强化收藏复看价值")
    if average([row.get("comment_tendency") for row in rows]) >= 0.08:
        learning_focus.append("用强代入话题驱动评论区表达")
    if commerce_hits:
        learning_focus.append("简介承担私域/课程/接占转化入口")
    if trust_hits:
        learning_focus.append("用原创、资质或唯一渠道建立信任")
    if not learning_focus:
        learning_focus.append("观察其昵称、简介和标题之间的定位一致性")

    return {
        "persona_type": persona,
        "commerce_signals": sorted(set(commerce_hits)),
        "trust_signals": sorted(set(trust_hits)),
        "risk_signals": sorted(set(risk_hits)),
        "summary": f"{persona}；简介中可见{len(set(commerce_hits))}类转化线索、{len(set(trust_hits))}类信任线索。",
        "learning_focus": learning_focus[:4],
    }


def _build_overview(videos: list[dict[str, Any]], authors: list[dict[str, Any]], raw_job_count: int) -> dict[str, Any]:
    comment_quality_count = sum(
        1 for video in videos if (video.get("comment_quality") or {}).get("status") == "ready"
    )
    public_signal_count = sum(
        1
        for video in videos
        if any(int_number(video.get(key)) > 0 for key in ("digg_count", "comment_count", "collect_count", "share_count"))
    )
    return {
        "analysis_task_count": raw_job_count,
        "unique_video_count": len(videos),
        "author_count": len(authors),
        "segment_count": sum(int_number(video.get("segment_count")) for video in videos),
        "avg_imitation_value": int(round(average([video.get("imitation_value") for video in videos]))),
        "content_type_counts": dict(Counter(video.get("content_type") or "未分类" for video in videos)),
        "public_signal_video_count": public_signal_count,
        "comment_quality_video_count": comment_quality_count,
        "evaluation_scope": "public_competitor_only",
    }


def rebuild_index(mode: str = "incremental") -> dict[str, Any]:
    with _INDEX_LOCK:
        return _rebuild_index_unlocked(mode)


def _rebuild_index_unlocked(mode: str = "incremental") -> dict[str, Any]:
    start = time.perf_counter()
    files = _job_files()
    requested_mode = mode
    metric_config = load_metric_config()
    metric_weights = metric_config.get("public_engagement_weights") or {}
    previous_meta = _read_json(index_dir() / "index_meta.json") if mode == "incremental" else {}
    if mode == "incremental" and isinstance(previous_meta, dict) and previous_meta.get("public_engagement_weights") != metric_weights:
        mode = "full"
        previous_meta = {}
    if mode == "incremental" and isinstance(previous_meta, dict) and int(previous_meta.get("index_version") or 0) != INDEX_VERSION:
        mode = "full"
        previous_meta = {}
    previous_signatures = previous_meta.get("job_files") if isinstance(previous_meta, dict) else {}
    previous_videos = _read_json(index_dir() / "videos.json") if mode == "incremental" else []
    videos_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(previous_videos, list):
        for video in previous_videos:
            if isinstance(video, dict) and video.get("video_id"):
                videos_by_id[str(video["video_id"])] = video
    changed = 0
    job_signatures: dict[str, dict[str, int | str]] = {}
    for path in files:
        signature = _job_signature(path)
        path_key = str(path)
        job_signatures[path_key] = signature
        if mode == "incremental" and previous_signatures.get(path_key) == signature:
            continue
        job = _read_json(path)
        if not job or job.get("status") not in {None, "done"}:
            continue
        video = _normalize_video(job, path, weights=metric_weights)
        if not video:
            continue
        changed += 1
        video_id = str(video["video_id"])
        if video_id in videos_by_id:
            videos_by_id[video_id] = _merge_duplicate(videos_by_id[video_id], video)
        else:
            video["job_ids"] = [video.get("job_id")]
            videos_by_id[video_id] = video

    videos = list(videos_by_id.values())
    authors = _build_authors(videos)
    patterns = build_pattern_library(videos)
    indexed_job_count = sum(len(video.get("job_ids") or [video.get("job_id")]) for video in videos)
    overview = _build_overview(videos, authors, indexed_job_count)
    meta = {
        "status": "done",
        "mode": mode,
        "requested_mode": requested_mode,
        "index_version": INDEX_VERSION,
        "metric_config_version": int(metric_config.get("version") or 1),
        "public_engagement_weights": metric_weights,
        "indexed_at": int(time.time()),
        "processed_jobs": indexed_job_count,
        "changed_jobs": changed,
        "job_file_count": len(files),
        "unique_videos": len(videos),
        "authors": len(authors),
        "patterns": len(patterns),
        "public_signal_video_count": overview["public_signal_video_count"],
        "comment_quality_video_count": overview["comment_quality_video_count"],
        "duration_ms": int((time.perf_counter() - start) * 1000),
        "job_files": job_signatures,
    }

    base = index_dir()
    _write_json(base / "videos.json", videos)
    _write_json(base / "authors.json", authors)
    _write_json(base / "patterns.json", patterns)
    _write_json(base / "overview.json", overview)
    _write_json(base / "index_meta.json", meta)
    return meta


def _load_cached(name: str) -> Any | None:
    return _read_json(index_dir() / name) if name.endswith(".json") else None


def load_index(force: bool = False) -> dict[str, Any]:
    base = index_dir()
    required = ["videos.json", "authors.json", "patterns.json", "overview.json", "index_meta.json"]
    if force or not all((base / name).exists() for name in required):
        rebuild_index("full" if force else "incremental")
    else:
        meta = _read_json(base / "index_meta.json") or {}
        metric_config = load_metric_config()
        metric_weights = metric_config.get("public_engagement_weights") or {}
        refresh_seconds = int(os.getenv("BENCHMARK_AUTO_REFRESH_SECONDS") or "300")
        indexed_at = int(meta.get("indexed_at") or 0) if isinstance(meta, dict) else 0
        if isinstance(meta, dict) and int(meta.get("index_version") or 0) != INDEX_VERSION:
            rebuild_index("full")
        elif isinstance(meta, dict) and meta.get("public_engagement_weights") != metric_weights:
            rebuild_index("full")
        elif refresh_seconds > 0 and int(time.time()) - indexed_at > refresh_seconds:
            rebuild_index("incremental")
    return {
        "videos": _read_json(base / "videos.json") or [],
        "authors": _read_json(base / "authors.json") or [],
        "patterns": _read_json(base / "patterns.json") or [],
        "overview": _read_json(base / "overview.json") or {},
        "meta": _read_json(base / "index_meta.json") or {},
    }


def filtered_items(items: list[dict[str, Any]], genre: str = "", q: str = "") -> list[dict[str, Any]]:
    next_items = items
    if genre and genre != "全部类型":
        next_items = [item for item in next_items if genre in {item.get("content_type"), item.get("genre")}]
    if q:
        needle = q.lower()
        next_items = [
            item
            for item in next_items
            if needle in _text(item.get("desc")).lower()
            or needle in _text(item.get("author_name")).lower()
            or needle in _text(item.get("nickname")).lower()
        ]
    return next_items


def page(items: list[dict[str, Any]], limit: int = 20, offset: int = 0) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 100))
    safe_offset = max(0, int(offset or 0))
    return {"items": items[safe_offset : safe_offset + safe_limit], "total": len(items), "limit": safe_limit, "offset": safe_offset}
