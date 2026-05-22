from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from backend.app.tiktok_target_store import (
    get_target_user,
    get_target_video_interaction_dataset,
    mark_target_video_comment_snapshot,
    normalize_comment,
    replace_target_video_comments,
    resolve_target_video,
)
from integrations.tikhub_douyin_api import TikhubDouyinApiAdapter


ProgressCallback = Callable[[int, str], None]


DEFAULT_COMMENT_OPTIONS = {
    "enabled": True,
    "adaptive_by_ratio": True,
    "max_comments": 160,
    "min_comments": 30,
    "page_size": 20,
    "include_replies": True,
    "replies_per_comment": 3,
}


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _maybe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _option_value(options: Any, key: str, default: Any = None) -> Any:
    if isinstance(options, dict):
        return options.get(key, default)
    return getattr(options, key, default)


def normalize_comment_options(options: Any | None = None) -> dict[str, Any]:
    source = options or {}
    normalized = dict(DEFAULT_COMMENT_OPTIONS)
    if isinstance(source, dict):
        if "collect_comments" in source and "enabled" not in source:
            normalized["enabled"] = source.get("collect_comments") is not False
        normalized.update({key: value for key, value in source.items() if value is not None})
    else:
        for key in DEFAULT_COMMENT_OPTIONS:
            value = getattr(source, key, None)
            if value is not None:
                normalized[key] = value
        if hasattr(source, "collect_comments") and not hasattr(source, "enabled"):
            normalized["enabled"] = getattr(source, "collect_comments") is not False

    normalized["enabled"] = normalized.get("enabled") is not False
    normalized["adaptive_by_ratio"] = normalized.get("adaptive_by_ratio") is not False
    normalized["max_comments"] = max(1, min(_to_int(normalized.get("max_comments")) or 160, 500))
    normalized["min_comments"] = max(0, min(_to_int(normalized.get("min_comments")), normalized["max_comments"]))
    normalized["page_size"] = max(1, min(_to_int(normalized.get("page_size")) or 20, 50))
    normalized["include_replies"] = normalized.get("include_replies") is not False
    normalized["replies_per_comment"] = max(0, min(_to_int(normalized.get("replies_per_comment")), 50))
    return normalized


def short_error(exc: Exception | str) -> str:
    text = str(exc).replace("\n", " ").strip()
    if "fetch_user_post_videos" in text and "HTTP 400" in text:
        return "TikHub Douyin Web 作品接口拒绝该账号标识，请确认 sec_user_id 或 Cookie"
    return text[:300] + ("..." if len(text) > 300 else "")


def comment_like_ratio(video: dict[str, Any]) -> float:
    metrics = video.get("metrics") if isinstance(video.get("metrics"), dict) else {}
    ratio = _to_float(video.get("comment_like_ratio"))
    if ratio is None:
        ratio = _to_float(metrics.get("comment_like_ratio"))
    if ratio is None and isinstance(metrics.get("ratios"), dict):
        ratio = _to_float(metrics["ratios"].get("comment_like_ratio"))
    if ratio is not None:
        return max(0.0, ratio)
    likes = _to_int(video.get("digg_count"))
    comments = _to_int(video.get("comment_count"))
    if likes <= 0:
        return 0.0
    return round(comments / likes, 6)


def comment_sampling_plan(video: dict[str, Any], options: Any) -> dict[str, Any]:
    normalized = normalize_comment_options(options)
    cap = normalized["max_comments"]
    floor = normalized["min_comments"]
    metrics = video.get("metrics") if isinstance(video.get("metrics"), dict) else {}
    known_comment_count = _maybe_int(video.get("comment_count"))
    if known_comment_count is None:
        known_comment_count = _maybe_int(metrics.get("comment_count"))
    known_like_count = _maybe_int(video.get("digg_count"))
    if known_like_count is None:
        known_like_count = _maybe_int(metrics.get("digg_count"))
    comment_count = known_comment_count or 0
    like_count = known_like_count or 0
    ratio = comment_like_ratio(video)

    if not normalized["adaptive_by_ratio"]:
        target = cap
        bucket = "fixed"
    elif known_comment_count is None:
        target = min(max(floor, 50), cap)
        bucket = "unknown_metrics"
    elif comment_count <= 0:
        target = 0
        bucket = "no_comments"
    elif ratio >= 0.12:
        target = min(160, cap)
        bucket = "extreme_interaction"
    elif ratio >= 0.08:
        target = min(120, cap)
        bucket = "very_high_interaction"
    elif ratio >= 0.05:
        target = min(100, cap)
        bucket = "high_interaction"
    elif ratio >= 0.02:
        target = min(80, cap)
        bucket = "active_interaction"
    elif ratio >= 0.01:
        target = min(50, cap)
        bucket = "normal_interaction"
    else:
        target = min(30, cap)
        bucket = "low_interaction"

    if known_comment_count is not None and comment_count > 0:
        target = min(max(floor, target), comment_count, cap)
    target = max(0, target)

    if not normalized["include_replies"] or target <= 0:
        replies_per_comment = 0
    elif not normalized["adaptive_by_ratio"]:
        replies_per_comment = normalized["replies_per_comment"]
    elif ratio >= 0.05:
        replies_per_comment = normalized["replies_per_comment"]
    elif ratio >= 0.02:
        replies_per_comment = min(normalized["replies_per_comment"], 2)
    else:
        replies_per_comment = min(normalized["replies_per_comment"], 1)

    return {
        "strategy": "comment_like_ratio" if normalized["adaptive_by_ratio"] else "fixed",
        "bucket": bucket,
        "like_count": like_count,
        "comment_count": comment_count,
        "comment_like_ratio": ratio,
        "max_comments": target,
        "cap_comments": cap,
        "min_comments": floor,
        "page_size": max(1, min(normalized["page_size"], max(1, target or normalized["page_size"]))),
        "include_replies": normalized["include_replies"],
        "replies_per_comment": replies_per_comment,
    }


def author_identity_from_video(video: dict[str, Any]) -> set[str]:
    source = video.get("source_json") if isinstance(video.get("source_json"), dict) else {}
    raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}
    containers = []
    for item in (source, raw, video):
        if isinstance(item, dict):
            containers.append(item.get("author") if isinstance(item.get("author"), dict) else {})
            containers.append(item.get("user") if isinstance(item.get("user"), dict) else {})
            containers.append(item.get("owner") if isinstance(item.get("owner"), dict) else {})
    identities = set()
    for container in containers:
        for key in ("uid", "id", "user_id", "sec_uid", "secUid", "sec_user_id"):
            value = container.get(key)
            if value not in [None, ""]:
                identities.add(str(value))
    return identities


def _progress(progress: ProgressCallback | None, value: int, message: str) -> None:
    if progress:
        progress(max(0, min(100, int(value))), message)


def _collect_progress(
    *,
    comment_index: int,
    comment_target: int,
    reply_index: int = 0,
    reply_target: int = 0,
) -> int:
    if comment_target <= 0:
        return 20
    comment_ratio = min(1.0, comment_index / max(1, comment_target))
    reply_ratio = min(1.0, reply_index / max(1, reply_target)) if reply_target else 0.0
    return int(12 + comment_ratio * 12 + reply_ratio * 6)


def collect_video_comment_snapshot(
    video: dict[str, Any],
    adapter: TikhubDouyinApiAdapter | None = None,
    options: Any | None = None,
    *,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    normalized_options = normalize_comment_options(options)
    video_id = str(video.get("id") or "")
    aweme_id = str(video.get("aweme_id") or video_id)
    if not video_id:
        raise RuntimeError("missing target video id")
    if not aweme_id:
        raise RuntimeError("missing aweme_id")

    adapter = adapter or TikhubDouyinApiAdapter()
    author_ids = author_identity_from_video(video)
    sampling_plan = comment_sampling_plan(video, normalized_options)
    _progress(progress, 12, f"开始获取评论数据：目标 {sampling_plan['max_comments']} 条")
    if sampling_plan["max_comments"] <= 0:
        dataset = replace_target_video_comments(
            video_id,
            [],
            status="done",
            raw_ai={
                "collector": "tikhub-douyin-api",
                "comment_pages": [],
                "request": normalized_options,
                "sampling_plan": sampling_plan,
            },
        )
        _progress(progress, 20, "该视频评论数为 0，评论步骤完成")
        return dataset

    cached_dataset = get_target_video_interaction_dataset(video_id)
    cached_video = cached_dataset.get("video") if isinstance(cached_dataset.get("video"), dict) else {}
    cached_comment_count = int(cached_video.get("comment_saved_count") or cached_dataset.get("comment_count") or 0)
    cached_reply_count = int(cached_video.get("reply_saved_count") or cached_dataset.get("reply_count") or 0)
    cached_ready = cached_video and cached_comment_count >= sampling_plan["max_comments"]
    if cached_ready and not normalized_options.get("force_refresh"):
        _progress(
            progress,
            18,
            f"评论数据已在库中：评论 {cached_comment_count} 条 / 回复 {cached_reply_count} 条",
        )
        if cached_video.get("comment_snapshot_status") != "done":
            mark_target_video_comment_snapshot(video_id, "done", "")
        return cached_dataset

    result = adapter.get_video_comments(
        aweme_id=aweme_id,
        max_items=sampling_plan["max_comments"],
        page_size=sampling_plan["page_size"],
    )
    normalized = []
    comments = [comment for comment in result.get("items", []) if isinstance(comment, dict)]
    _progress(progress, 20, f"已获取一级评论 {len(comments)}/{sampling_plan['max_comments']} 条")
    for index, comment in enumerate(comments):
        parent = normalize_comment(
            video_id,
            aweme_id,
            comment,
            rank_index=index,
            level=1,
            author_user_ids=author_ids,
        )
        normalized.append(parent)
        if not normalized_options["include_replies"] or sampling_plan["replies_per_comment"] <= 0:
            continue
        reply_total = _to_int(parent.get("reply_count"))
        if reply_total <= 0:
            continue
        reply_limit = min(sampling_plan["replies_per_comment"], reply_total)
        try:
            replies = adapter.get_video_comment_replies(
                item_id=aweme_id,
                comment_id=parent["comment_id"],
                max_items=reply_limit,
                page_size=min(normalized_options["page_size"], max(1, sampling_plan["replies_per_comment"])),
            )
        except Exception as exc:
            parent_source = parent.get("source_json") if isinstance(parent.get("source_json"), dict) else {}
            parent["source_json"] = {**parent_source, "reply_fetch_error": short_error(exc)}
            continue
        for reply_index, reply in enumerate(replies.get("items", [])):
            if not isinstance(reply, dict):
                continue
            normalized.append(
                normalize_comment(
                    video_id,
                    aweme_id,
                    reply,
                    rank_index=index * 1000 + reply_index,
                    parent_comment_id=parent["comment_id"],
                    level=2,
                    author_user_ids=author_ids,
                )
            )
        _progress(
            progress,
            _collect_progress(
                comment_index=index + 1,
                comment_target=max(1, len(comments)),
                reply_index=index + 1,
                reply_target=max(1, len(comments)),
            ),
            f"正在获取评论回复 {index + 1}/{len(comments)}",
        )

    dataset = replace_target_video_comments(
        video_id,
        normalized,
        status="done",
        raw_ai={
            "collector": "tikhub-douyin-api",
            "comment_pages": result.get("raw_pages", []),
            "request": normalized_options,
            "sampling_plan": sampling_plan,
        },
    )
    _progress(
        progress,
        30,
        f"评论数据已保存：评论 {dataset.get('comment_count') or 0} 条 / 回复 {dataset.get('reply_count') or 0} 条",
    )
    return dataset


def comment_state_from_dataset(dataset: dict[str, Any], *, status: str = "done", error: str = "") -> dict[str, Any]:
    video = dataset.get("video") if isinstance(dataset.get("video"), dict) else {}
    insights = dataset.get("insights") if isinstance(dataset.get("insights"), dict) else {}
    return {
        "status": status,
        "video_id": video.get("id") or "",
        "aweme_id": video.get("aweme_id") or "",
        "snapshot_at": video.get("comment_snapshot_at"),
        "comment_saved_count": video.get("comment_saved_count") or dataset.get("comment_count") or insights.get("comment_count_saved") or 0,
        "reply_saved_count": video.get("reply_saved_count") or dataset.get("reply_count") or insights.get("reply_count_saved") or 0,
        "error": error,
    }


def build_target_interaction_context(video: dict[str, Any]) -> dict[str, Any]:
    dataset = get_target_video_interaction_dataset(str(video.get("id") or video.get("aweme_id") or ""))
    latest_video = dataset.get("video") if isinstance(dataset.get("video"), dict) else video
    insights = dataset.get("insights") if isinstance(dataset.get("insights"), dict) else {}
    comments = dataset.get("comments") if isinstance(dataset.get("comments"), list) else []
    top_comments = _dedupe_compact_comments(
        [
            {
                "comment_id": item.get("comment_id"),
                "nickname": item.get("nickname"),
                "text": item.get("text"),
                "digg_count": item.get("digg_count"),
                "reply_count": item.get("reply_count"),
                "is_pinned": item.get("is_pinned"),
                "is_author": item.get("is_author"),
            }
            for item in comments
            if int(item.get("level") or 1) == 1
        ]
    )
    top_comments = sorted(top_comments, key=lambda item: int(item.get("digg_count") or 0), reverse=True)[:30]
    metrics = latest_video.get("metrics") if isinstance(latest_video.get("metrics"), dict) else {}
    return {
        "set_id": latest_video.get("set_id"),
        "video_id": latest_video.get("id"),
        "aweme_id": latest_video.get("aweme_id"),
        "metrics": {
            "create_time": latest_video.get("create_time"),
            "publish_hour": latest_video.get("publish_hour"),
            "publish_weekday": latest_video.get("publish_weekday"),
            "publish_date": latest_video.get("publish_date"),
            "publish_hour_bucket": latest_video.get("publish_hour_bucket"),
            "digg_count": latest_video.get("digg_count"),
            "comment_count": latest_video.get("comment_count"),
            "share_count": latest_video.get("share_count"),
            "collect_count": latest_video.get("collect_count"),
            "play_count": latest_video.get("play_count"),
            "like_collect_ratio": latest_video.get("like_collect_ratio"),
            "collect_like_ratio": latest_video.get("collect_like_ratio"),
            "comment_like_ratio": latest_video.get("comment_like_ratio"),
            "share_like_ratio": latest_video.get("share_like_ratio"),
            "engagement_score": latest_video.get("engagement_score"),
            "engagement_rate": latest_video.get("engagement_rate"),
            "metrics": metrics,
        },
        "interaction_snapshot": {
            "status": latest_video.get("comment_snapshot_status"),
            "snapshot_at": latest_video.get("comment_snapshot_at"),
            "comment_saved_count": latest_video.get("comment_saved_count"),
            "reply_saved_count": latest_video.get("reply_saved_count"),
            "error": (metrics.get("comment_snapshot_error") if isinstance(metrics, dict) else "") or latest_video.get("comment_snapshot_error") or "",
            "keyword_counts": insights.get("keyword_counts") or {},
            "symbol_counts": insights.get("symbol_counts") or {},
            "emotion_profile": insights.get("emotion_profile") or {},
            "creator_reply_tactics": insights.get("creator_reply_tactics") or {},
            "pinned_comments": _dedupe_compact_comments(insights.get("pinned_comments") or []),
            "author_replies": _dedupe_compact_comments(insights.get("author_replies") or []),
            "top_comments": _dedupe_compact_comments(insights.get("top_comments") or top_comments),
        },
    }


def _dedupe_compact_comments(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        text = re.sub(r"\s+", "", str(comment.get("text") or comment.get("content") or ""))
        author = re.sub(
            r"\s+",
            "",
            str(comment.get("user_id") or comment.get("sec_uid") or comment.get("unique_id") or comment.get("nickname") or ""),
        )
        identities = []
        comment_id = str(comment.get("comment_id") or comment.get("cid") or comment.get("id") or "").strip()
        if comment_id:
            identities.append(f"id:{comment_id}")
        if text and author:
            identities.append(f"author_text:{author}:{text[:200]}")
        if not identities and text:
            identities.append(f"text:{text[:200]}")
        if any(identity in seen for identity in identities):
            continue
        seen.update(identities)
        unique.append(comment)
    return unique


def merge_target_context(existing: dict[str, Any], latest: dict[str, Any]) -> dict[str, Any]:
    merged = {**(existing or {}), **(latest or {})}
    old_snapshot = existing.get("interaction_snapshot") if isinstance(existing.get("interaction_snapshot"), dict) else {}
    new_snapshot = latest.get("interaction_snapshot") if isinstance(latest.get("interaction_snapshot"), dict) else {}
    if old_snapshot or new_snapshot:
        merged["interaction_snapshot"] = {**old_snapshot, **new_snapshot}
    old_metrics = existing.get("metrics") if isinstance(existing.get("metrics"), dict) else {}
    new_metrics = latest.get("metrics") if isinstance(latest.get("metrics"), dict) else {}
    if old_metrics or new_metrics:
        merged["metrics"] = {**old_metrics, **new_metrics}
    return merged

def merge_comment_context_into_result(
    result: dict[str, Any],
    *,
    video: dict[str, Any],
    comment_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    existing_context = video.get("douyin_target_context") if isinstance(video.get("douyin_target_context"), dict) else {}
    douyin_target = result.get("douyin_target") if isinstance(result.get("douyin_target"), dict) else {}
    merged_context = merge_target_context(existing_context, douyin_target)
    if merged_context:
        result = {**result, "douyin_target": merged_context}
    if comment_state:
        result["comment_collection"] = comment_state
    return result


def merge_comment_state_into_payload(
    payload: dict[str, Any],
    *,
    video: dict[str, Any] | None = None,
    comment_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    next_payload = {**payload}
    if video is not None:
        next_payload["video"] = video
    if comment_state:
        next_payload["comment_collection_state"] = comment_state
    return next_payload


def merge_comment_state_into_task_result(
    result: Any,
    *,
    video: dict[str, Any],
    comment_state: dict[str, Any],
) -> dict[str, Any]:
    base = result if isinstance(result, dict) else {}
    return merge_comment_context_into_result({**base}, video=video, comment_state=comment_state)


def resolve_target_video_for_ai_task(task: dict[str, Any]) -> dict[str, Any] | None:
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
    context = video.get("douyin_target_context") if isinstance(video.get("douyin_target_context"), dict) else {}
    payload_context = payload.get("douyin_target") if isinstance(payload.get("douyin_target"), dict) else {}
    candidates = [
        context.get("video_id"),
        payload_context.get("video_id"),
        context.get("aweme_id"),
        payload_context.get("aweme_id"),
        video.get("target_video_id"),
        video.get("aweme_id"),
        video.get("id"),
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        target_video = resolve_target_video(text)
        if target_video:
            return target_video
    return None


def comment_options_from_task(task: dict[str, Any]) -> dict[str, Any]:
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    options = payload.get("comment_collection")
    if not isinstance(options, dict):
        options = payload.get("comment_options") if isinstance(payload.get("comment_options"), dict) else {}
    return normalize_comment_options(options)


def collect_comments_for_ai_task(
    task: dict[str, Any],
    *,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    video = dict(payload.get("video") or {})
    options = comment_options_from_task(task)
    if not options["enabled"]:
        return {"status": "skipped", "reason": "disabled"}, video

    target_video = resolve_target_video_for_ai_task(task)
    if not target_video:
        _progress(progress, 12, "未关联对标库视频，跳过评论数据获取")
        return {"status": "skipped", "reason": "target_video_not_found"}, video

    existing_context = video.get("douyin_target_context") if isinstance(video.get("douyin_target_context"), dict) else {}
    if target_video.get("comment_snapshot_status") == "done" and not force:
        latest_context = build_target_interaction_context(target_video)
        video["douyin_target_context"] = merge_target_context(existing_context, latest_context)
        dataset = get_target_video_interaction_dataset(target_video["id"])
        state = comment_state_from_dataset(dataset, status="done")
        _progress(
            progress,
            20,
            f"评论数据已存在：评论 {state['comment_saved_count']} 条 / 回复 {state['reply_saved_count']} 条",
        )
        return state, video

    try:
        mark_target_video_comment_snapshot(target_video["id"], "running", "")
        dataset = collect_video_comment_snapshot(target_video, options=options, progress=progress)
        latest_video = dataset.get("video") if isinstance(dataset.get("video"), dict) else target_video
        latest_context = build_target_interaction_context(latest_video)
        video["douyin_target_context"] = merge_target_context(existing_context, latest_context)
        return comment_state_from_dataset(dataset, status="done"), video
    except Exception as exc:
        failed_video = mark_target_video_comment_snapshot(target_video["id"], "failed", short_error(exc)) or target_video
        latest_context = build_target_interaction_context(failed_video)
        video["douyin_target_context"] = merge_target_context(existing_context, latest_context)
        state = {
            "status": "failed",
            "video_id": target_video.get("id") or "",
            "aweme_id": target_video.get("aweme_id") or "",
            "error": short_error(exc),
        }
        _progress(progress, 20, f"评论数据获取失败，继续拆解：{state['error']}")
        return state, video


def target_user_for_video(video: dict[str, Any]) -> dict[str, Any] | None:
    user_id = str(video.get("user_id") or "")
    return get_target_user(user_id) if user_id else None
