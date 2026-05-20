from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.ai_video_comment_service import (
    collect_video_comment_snapshot,
    comment_sampling_plan,
)
from backend.app.ai_provider_state import active_ai_provider
from backend.app.routes.ai_video_analysis import adapter as ai_video_adapter
from backend.app.routes.ai_video_analysis import retry_job_comments
from backend.app.routes.ai_video_analysis import video_title
from backend.app.task_store import create_task, delete_task, get_task
from backend.app.video_analysis_queue import delete_ai_video_job, enqueue_ai_video_job, get_ai_video_job, queue_stats
from backend.app.tiktok_target_store import (
    add_user_to_target_set,
    clear_target_video_analysis,
    create_target_set,
    create_target_task,
    create_target_video,
    delete_target_set,
    find_target_task_for_video,
    get_target_set,
    get_target_set_detail,
    get_target_user,
    get_target_video,
    get_target_video_interaction_dataset,
    init_db,
    list_target_sets,
    list_target_tasks,
    list_target_videos,
    mark_target_video_comment_snapshot,
    normalize_comment,
    replace_target_video_comments,
    resolve_target_video,
    update_target_set,
    update_target_task_from_ai_task,
    upsert_target_user,
)
from integrations.douyin_download_api.adapter import DouyinDownloadApiAdapter
from integrations.tikhub_douyin_api import TikhubDouyinApiAdapter
from integrations.tikhub_douyin_api.adapter import TikhubApiError

router = APIRouter(prefix="/api/tools/douyin-target", tags=["douyin-target"])


class TargetSearchRequest(BaseModel):
    keyword: str
    page: int = Field(default=1, ge=1)
    count: int = Field(default=20, ge=1, le=50)
    minFollowers: int | None = None
    maxFollowers: int | None = None
    minLikes: int | None = None
    maxLikes: int | None = None
    minVideos: int | None = None
    maxVideos: int | None = None
    recentOnly: bool = False
    recentWithinDays: int | None = None
    olderThanDays: int | None = None
    verified: str = Field(default="all")
    privateFilter: str = Field(default="exclude")
    sortBy: str = Field(default="relevance")


class TargetUserCreate(BaseModel):
    keyword: str = Field(default="")
    sec_user_id: str = Field(default="")
    sec_uid: str = Field(default="")
    uid: str = Field(default="")
    unique_id: str = Field(default="")
    nickname: str = Field(default="")
    avatar_url: str = Field(default="")
    avatar: str = Field(default="")
    signature: str = Field(default="")
    follower_count: int | None = None
    like_count: int | None = None
    aweme_count: int | None = None
    following_count: int | None = None
    recent_update_at: int | None = None
    last_post_at: int | None = None
    verified: bool = False
    is_private: bool = False
    status: str = Field(default="candidate")
    source_json: dict[str, Any] = Field(default_factory=dict)


class TargetBulkSave(BaseModel):
    users: list[TargetUserCreate]
    set_id: str | None = None
    set_name: str = Field(default="")
    note: str = Field(default="")
    keyword: str = Field(default="")
    filters: dict[str, Any] = Field(default_factory=dict)


class TargetSetCreate(BaseModel):
    name: str
    note: str = Field(default="")
    keyword: str = Field(default="")
    filters: dict[str, Any] = Field(default_factory=dict)
    video_strategy: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="draft")


class TargetSetUpdate(BaseModel):
    name: str | None = None
    note: str | None = None
    keyword: str | None = None
    filters: dict[str, Any] | None = None
    video_strategy: dict[str, Any] | None = None
    status: str | None = None


class VideoStrategy(BaseModel):
    mode: str = Field(default="top")
    per_user_limit: int = Field(default=5, ge=1, le=20)
    fetch_count: int = Field(default=20, ge=1, le=50)
    sort_metric: str = Field(default="digg_count")


class CollectVideosRequest(BaseModel):
    set_id: str
    user_ids: list[str] = Field(default_factory=list)
    strategy: VideoStrategy = Field(default_factory=VideoStrategy)


class EnqueueAnalysisRequest(BaseModel):
    set_id: str = Field(default="")
    video_ids: list[str] = Field(default_factory=list)
    force: bool = False
    provider: str | None = None
    collect_comments: bool = True
    adaptive_comments: bool = True
    max_comments: int = Field(default=160, ge=1, le=500)
    min_comments: int = Field(default=30, ge=0, le=500)
    replies_per_comment: int = Field(default=3, ge=0, le=50)


class CollectCommentsRequest(BaseModel):
    video_ids: list[str] = Field(default_factory=list)
    set_id: str = Field(default="")
    adaptive_by_ratio: bool = True
    max_comments: int = Field(default=160, ge=1, le=500)
    min_comments: int = Field(default=30, ge=0, le=500)
    page_size: int = Field(default=20, ge=1, le=50)
    include_replies: bool = True
    replies_per_comment: int = Field(default=3, ge=0, le=50)


@router.on_event("startup")
def _startup() -> None:
    init_db()


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


def _comment_like_ratio(video: dict[str, Any]) -> float:
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


def _comment_sampling_plan(video: dict[str, Any], payload: CollectCommentsRequest) -> dict[str, Any]:
    cap = max(1, min(_to_int(payload.max_comments) or 100, 500))
    floor = max(0, min(_to_int(payload.min_comments), cap))
    metrics = video.get("metrics") if isinstance(video.get("metrics"), dict) else {}
    known_comment_count = _maybe_int(video.get("comment_count"))
    if known_comment_count is None:
        known_comment_count = _maybe_int(metrics.get("comment_count"))
    known_like_count = _maybe_int(video.get("digg_count"))
    if known_like_count is None:
        known_like_count = _maybe_int(metrics.get("digg_count"))
    comment_count = known_comment_count or 0
    like_count = known_like_count or 0
    ratio = _comment_like_ratio(video)

    if not payload.adaptive_by_ratio:
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

    if not payload.include_replies or target <= 0:
        replies_per_comment = 0
    elif not payload.adaptive_by_ratio:
        replies_per_comment = payload.replies_per_comment
    elif ratio >= 0.05:
        replies_per_comment = payload.replies_per_comment
    elif ratio >= 0.02:
        replies_per_comment = min(payload.replies_per_comment, 2)
    else:
        replies_per_comment = min(payload.replies_per_comment, 1)

    return {
        "strategy": "comment_like_ratio" if payload.adaptive_by_ratio else "fixed",
        "bucket": bucket,
        "like_count": like_count,
        "comment_count": comment_count,
        "comment_like_ratio": ratio,
        "max_comments": target,
        "cap_comments": cap,
        "min_comments": floor,
        "page_size": max(1, min(payload.page_size, max(1, target or payload.page_size))),
        "include_replies": payload.include_replies,
        "replies_per_comment": replies_per_comment,
    }


def _target_user_id(user: TargetUserCreate | dict[str, Any]) -> str:
    getter = user.get if isinstance(user, dict) else lambda key, default=None: getattr(user, key, default)
    return str(getter("sec_user_id") or getter("sec_uid") or getter("uid") or getter("unique_id") or "") or str(uuid4())


def _target_user_payload(user: TargetUserCreate, fallback_keyword: str = "") -> dict[str, Any]:
    source = user.source_json or {}
    return {
        "keyword": user.keyword or fallback_keyword,
        "sec_user_id": user.sec_user_id or user.sec_uid,
        "unique_id": user.unique_id,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url or user.avatar,
        "signature": user.signature,
        "follower_count": user.follower_count,
        "like_count": user.like_count,
        "aweme_count": user.aweme_count,
        "following_count": user.following_count,
        "recent_update_at": user.recent_update_at or user.last_post_at,
        "last_post_at": user.last_post_at or user.recent_update_at,
        "verified": user.verified,
        "is_private": user.is_private,
        "status": user.status,
        "source_json": source or user.model_dump(),
    }


def _nested_dict(value: Any, key: str) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get(key), dict):
        return value[key]
    return {}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _looks_like_sec_user_id(value: Any) -> bool:
    text = _as_text(value)
    return len(text) >= 20 and " " not in text and "@" not in text


def _user_video_query_candidates(user: dict[str, Any]) -> list[dict[str, str]]:
    source = user.get("source_json") if isinstance(user.get("source_json"), dict) else {}
    raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}
    profile_raw = source.get("profile_raw") if isinstance(source.get("profile_raw"), dict) else {}
    containers = [
        ("stored", user),
        ("source", source),
        ("raw", raw),
        ("raw_user_info", _nested_dict(raw, "user_info")),
        ("raw_user", _nested_dict(raw, "user")),
        ("profile_raw", profile_raw),
        ("profile_user", _nested_dict(profile_raw, "user")),
        ("profile_user_info", _nested_dict(profile_raw, "user_info")),
    ]
    seen: set[tuple[str, str]] = set()
    candidates: list[dict[str, str]] = []

    def add(label: str, sec_user_id: Any = "", unique_id: Any = "") -> None:
        sec = _as_text(sec_user_id)
        unique = _as_text(unique_id)
        if not sec and not unique:
            return
        key = (sec, unique)
        if key in seen:
            return
        seen.add(key)
        candidates.append({"label": label, "sec_user_id": sec, "unique_id": unique})

    for label, container in containers:
        if not isinstance(container, dict):
            continue
        sec = container.get("sec_user_id") or container.get("sec_uid") or container.get("secUid")
        unique = container.get("unique_id") or container.get("uniqueId") or container.get("short_id")
        add(label, sec, unique)

    stored_unique = user.get("unique_id")
    if _looks_like_sec_user_id(user.get("id")):
        add("stored_id", user.get("id"), stored_unique)
    return candidates


def _short_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ").strip()
    if "fetch_user_post_videos" in text and "HTTP 400" in text:
        return "TikHub Douyin Web 作品接口拒绝该账号标识，请确认 sec_user_id 或 Cookie"
    return text[:300] + ("..." if len(text) > 300 else "")


def _passes_search_filters(item: dict[str, Any], payload: TargetSearchRequest) -> bool:
    follower_count = _maybe_int(item.get("follower_count"))
    like_count = _maybe_int(item.get("like_count"))
    aweme_count = _maybe_int(item.get("aweme_count"))
    recent_at = _to_int(item.get("last_post_at") or item.get("recent_update_at"))
    if payload.minFollowers is not None and (follower_count is None or follower_count < payload.minFollowers):
        return False
    if payload.maxFollowers is not None and (follower_count is None or follower_count > payload.maxFollowers):
        return False
    if payload.minLikes is not None and (like_count is None or like_count < payload.minLikes):
        return False
    if payload.maxLikes is not None and (like_count is None or like_count > payload.maxLikes):
        return False
    if payload.minVideos is not None and (aweme_count is None or aweme_count < payload.minVideos):
        return False
    if payload.maxVideos is not None and (aweme_count is None or aweme_count > payload.maxVideos):
        return False
    if payload.verified == "only" and not item.get("verified"):
        return False
    if payload.verified == "exclude" and item.get("verified"):
        return False
    if payload.privateFilter == "exclude" and item.get("is_private"):
        return False
    if payload.privateFilter == "only" and not item.get("is_private"):
        return False
    if payload.recentOnly and not recent_at:
        return False
    if payload.recentWithinDays and payload.recentWithinDays > 0:
        if not recent_at:
            return False
        cutoff = int(time.time()) - payload.recentWithinDays * 86400
        if recent_at < cutoff:
            return False
    if payload.olderThanDays and payload.olderThanDays > 0:
        if not recent_at:
            return False
        cutoff = int(time.time()) - payload.olderThanDays * 86400
        if recent_at >= cutoff:
            return False
    return True


def _sort_users(items: list[dict[str, Any]], sort_by: str) -> list[dict[str, Any]]:
    sort_keys = {
        "followers": "follower_count",
        "likes": "like_count",
        "videos": "aweme_count",
        "recent": "last_post_at",
    }
    key = sort_keys.get(sort_by)
    if not key:
        return items
    return sorted(items, key=lambda item: _to_int(item.get(key) or item.get("recent_update_at")), reverse=True)


def _video_metric(video: dict[str, Any], metric: str) -> int:
    if metric == "heat":
        return (
            _to_int(video.get("digg_count"))
            + _to_int(video.get("comment_count")) * 3
            + _to_int(video.get("share_count")) * 5
            + _to_int(video.get("collect_count")) * 4
        )
    return _to_int(video.get(metric))


def _select_videos(videos: list[dict[str, Any]], strategy: VideoStrategy) -> list[dict[str, Any]]:
    limit = strategy.per_user_limit
    if strategy.mode == "recent":
        return sorted(videos, key=lambda item: _to_int(item.get("create_time")), reverse=True)[:limit]
    if strategy.mode == "pinned":
        pinned = [item for item in videos if item.get("is_top")]
        fallback = sorted(videos, key=lambda item: _video_metric(item, strategy.sort_metric), reverse=True)
        merged = pinned + [item for item in fallback if item not in pinned]
        return merged[:limit]
    if strategy.mode == "mixed":
        selected: list[dict[str, Any]] = []
        for bucket in [
            [item for item in videos if item.get("is_top")],
            sorted(videos, key=lambda item: _video_metric(item, strategy.sort_metric), reverse=True),
            sorted(videos, key=lambda item: _to_int(item.get("create_time")), reverse=True),
        ]:
            for item in bucket:
                if item not in selected:
                    selected.append(item)
                if len(selected) >= limit:
                    return selected
        return selected
    return sorted(videos, key=lambda item: _video_metric(item, strategy.sort_metric), reverse=True)[:limit]


def _looks_like_tiktok_noise(video: dict[str, Any]) -> bool:
    desc = str(video.get("desc") or "").lower()
    markers = ("#fyp", "#foryou", "#foryoupage", "#pov")
    return sum(1 for marker in markers if marker in desc) >= 2


def _analysis_author_payload(video: dict[str, Any], target_user: dict[str, Any] | None = None) -> dict[str, Any]:
    source = video.get("source_json") if isinstance(video.get("source_json"), dict) else {}
    raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}
    author: dict[str, Any] = {}
    for container in (
        _nested_dict(raw, "author"),
        _nested_dict(raw, "user"),
        _nested_dict(source, "author"),
        _nested_dict(source, "user"),
        video.get("author") if isinstance(video.get("author"), dict) else {},
        video.get("user") if isinstance(video.get("user"), dict) else {},
        video.get("owner") if isinstance(video.get("owner"), dict) else {},
    ):
        for key, value in container.items():
            if value is None or value == "":
                continue
            author[key] = value

    if target_user:
        user_source = target_user.get("source_json") if isinstance(target_user.get("source_json"), dict) else {}

        def pick_text(*values: Any) -> str:
            for value in values:
                if value is None or value == "" or isinstance(value, (dict, list)):
                    continue
                text = str(value).strip()
                if text:
                    return text
            return ""

        def pick_number(*values: Any) -> int | None:
            fallback: int | None = None
            for value in values:
                number = _maybe_int(value)
                if number is None:
                    continue
                if number > 0:
                    return number
                if fallback is None:
                    fallback = number
            return fallback

        user_id = pick_text(target_user.get("id"), author.get("uid"), author.get("user_id"))
        if user_id:
            author["uid"] = author.get("uid") or user_id
            author["user_id"] = author.get("user_id") or user_id
            author["id"] = author.get("id") or user_id

        sec_uid = pick_text(target_user.get("sec_uid"), target_user.get("sec_user_id"), author.get("sec_uid"), author.get("sec_user_id"))
        if sec_uid:
            author["sec_uid"] = sec_uid
            author["sec_user_id"] = author.get("sec_user_id") or sec_uid

        unique_id = pick_text(target_user.get("unique_id"), author.get("unique_id"), author.get("uniqueId"), author.get("short_id"), author.get("display_id"))
        if unique_id:
            author["unique_id"] = unique_id
            author["uniqueId"] = author.get("uniqueId") or unique_id
            author["short_id"] = author.get("short_id") or unique_id
            author["display_id"] = author.get("display_id") or unique_id

        nickname = pick_text(target_user.get("nickname"), author.get("nickname"), author.get("name"), author.get("author_name"), author.get("user_name"), unique_id, user_id)
        if nickname:
            author["nickname"] = nickname
            author["name"] = author.get("name") or nickname
            author["author_name"] = author.get("author_name") or nickname
            author["user_name"] = author.get("user_name") or nickname

        signature = pick_text(target_user.get("signature"), author.get("signature"), author.get("desc"), author.get("intro"), author.get("bio"))
        if signature:
            author["signature"] = signature
            author["desc"] = author.get("desc") or signature
            author["intro"] = author.get("intro") or signature
            author["bio"] = author.get("bio") or signature

        avatar = pick_text(
            target_user.get("avatar_url"),
            target_user.get("avatar"),
            author.get("avatar"),
            author.get("avatar_url"),
            author.get("avatar_thumb"),
            author.get("avatar_medium"),
            author.get("avatar_large"),
        )
        if avatar:
            author["avatar"] = avatar
            author["avatar_url"] = avatar

        follower_count = pick_number(
            target_user.get("follower_count"),
            author.get("follower_count"),
            author.get("fans_count"),
            author.get("followers"),
            user_source.get("follower_count") if isinstance(user_source, dict) else None,
        )
        if follower_count is not None:
            author["follower_count"] = follower_count
            author["fans_count"] = follower_count
            author["followers"] = follower_count

        like_count = pick_number(
            target_user.get("like_count"),
            author.get("like_count"),
            author.get("total_favorited"),
            author.get("total_favorite"),
            author.get("digg_count"),
            user_source.get("like_count") if isinstance(user_source, dict) else None,
        )
        if like_count is not None:
            author["like_count"] = like_count
            author["total_favorited"] = like_count
            author["total_favorite"] = like_count
            author["digg_count"] = like_count

        aweme_count = pick_number(
            target_user.get("aweme_count"),
            author.get("aweme_count"),
            author.get("video_count"),
            author.get("item_count"),
            user_source.get("aweme_count") if isinstance(user_source, dict) else None,
        )
        if aweme_count is not None:
            author["aweme_count"] = aweme_count
            author["video_count"] = aweme_count
            author["item_count"] = aweme_count

        following_count = pick_number(
            target_user.get("following_count"),
            author.get("following_count"),
            author.get("follow_count"),
            user_source.get("following_count") if isinstance(user_source, dict) else None,
        )
        if following_count is not None:
            author["following_count"] = following_count
            author["follow_count"] = following_count

        if target_user.get("verified") is True:
            author["verified"] = True
            author["is_verified"] = True

        if target_user.get("is_private") is not None:
            author["is_private"] = bool(target_user.get("is_private"))

        author["target_user_id"] = target_user.get("id") or author.get("target_user_id") or ""
        author["source"] = "tiktok_target_users"

    return author


def _analysis_video_payload(video: dict[str, Any], target_user: dict[str, Any] | None = None) -> dict[str, Any]:
    source = video.get("source_json") if isinstance(video.get("source_json"), dict) else {}
    payload = {**source}
    metrics = video.get("metrics") if isinstance(video.get("metrics"), dict) else {}
    author = _analysis_author_payload(video, target_user)
    payload.update(
        {
            "id": video.get("aweme_id") or video.get("id"),
            "aweme_id": video.get("aweme_id") or video.get("id"),
            "desc": video.get("desc") or source.get("desc") or "",
            "cover_url": video.get("cover_url") or source.get("cover_url") or "",
            "source_video_url": video.get("download_url")
            or video.get("play_url")
            or source.get("source_video_url")
            or source.get("download_url")
            or source.get("play_url"),
            "video_url": video.get("play_url") or video.get("download_url") or source.get("video_url"),
            "statistics": source.get("statistics")
            or {
                "digg_count": video.get("digg_count"),
                "comment_count": video.get("comment_count"),
                "share_count": video.get("share_count"),
                "collect_count": video.get("collect_count"),
                "play_count": video.get("play_count"),
            },
            "derived_metrics": {
                "publish_hour": video.get("publish_hour"),
                "publish_weekday": video.get("publish_weekday"),
                "publish_date": video.get("publish_date"),
                "publish_hour_bucket": video.get("publish_hour_bucket"),
                "like_collect_ratio": video.get("like_collect_ratio"),
                "collect_like_ratio": video.get("collect_like_ratio"),
                "comment_like_ratio": video.get("comment_like_ratio"),
                "share_like_ratio": video.get("share_like_ratio"),
                "engagement_score": video.get("engagement_score"),
                "engagement_rate": video.get("engagement_rate"),
                "metrics": metrics,
            },
            "author": author,
            "user": author,
            "owner": author,
            "author_user_id": author.get("uid") or author.get("user_id") or (target_user.get("id") if target_user else video.get("user_id")) or "",
        }
    )
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
    raw = dict(raw)
    raw["author"] = author
    raw["user"] = author
    raw["owner"] = author
    payload["raw"] = raw
    return payload


def _analysis_target_context(video: dict[str, Any], target_user: dict[str, Any] | None = None) -> dict[str, Any]:
    dataset = get_target_video_interaction_dataset(video["id"])
    insights = dataset.get("insights") or {}
    comments = dataset.get("comments") or []
    author = _analysis_author_payload(video, target_user)
    top_comments = [
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
    top_comments = sorted(top_comments, key=lambda item: int(item.get("digg_count") or 0), reverse=True)[:30]
    return {
        "set_id": video.get("set_id"),
        "video_id": video.get("id"),
        "aweme_id": video.get("aweme_id"),
        "author": author,
        "metrics": {
            "create_time": video.get("create_time"),
            "publish_hour": video.get("publish_hour"),
            "publish_weekday": video.get("publish_weekday"),
            "publish_date": video.get("publish_date"),
            "publish_hour_bucket": video.get("publish_hour_bucket"),
            "digg_count": video.get("digg_count"),
            "comment_count": video.get("comment_count"),
            "share_count": video.get("share_count"),
            "collect_count": video.get("collect_count"),
            "play_count": video.get("play_count"),
            "like_collect_ratio": video.get("like_collect_ratio"),
            "collect_like_ratio": video.get("collect_like_ratio"),
            "comment_like_ratio": video.get("comment_like_ratio"),
            "share_like_ratio": video.get("share_like_ratio"),
            "engagement_score": video.get("engagement_score"),
            "engagement_rate": video.get("engagement_rate"),
        },
        "interaction_snapshot": {
            "status": video.get("comment_snapshot_status"),
            "snapshot_at": video.get("comment_snapshot_at"),
            "comment_saved_count": video.get("comment_saved_count"),
            "reply_saved_count": video.get("reply_saved_count"),
            "keyword_counts": insights.get("keyword_counts") or {},
            "symbol_counts": insights.get("symbol_counts") or {},
            "emotion_profile": insights.get("emotion_profile") or {},
            "creator_reply_tactics": insights.get("creator_reply_tactics") or {},
            "pinned_comments": insights.get("pinned_comments") or [],
            "author_replies": insights.get("author_replies") or [],
            "top_comments": insights.get("top_comments") or top_comments,
        },
    }


def _author_identity_from_video(video: dict[str, Any]) -> set[str]:
    source = video.get("source_json") if isinstance(video.get("source_json"), dict) else {}
    raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}
    containers = []
    for item in (source, raw):
        if isinstance(item, dict):
            containers.append(item.get("author") if isinstance(item.get("author"), dict) else {})
            containers.append(item.get("user") if isinstance(item.get("user"), dict) else {})
    identities = set()
    for container in containers:
        for key in ("uid", "id", "user_id", "sec_uid", "secUid", "sec_user_id"):
            value = container.get(key)
            if value not in [None, ""]:
                identities.add(str(value))
    return identities


def _collect_video_comment_snapshot(
    video: dict[str, Any],
    adapter: DouyinDownloadApiAdapter,
    payload: CollectCommentsRequest,
) -> dict[str, Any]:
    video_id = str(video.get("id") or "")
    aweme_id = str(video.get("aweme_id") or video_id)
    if not aweme_id:
        raise RuntimeError("missing aweme_id")
    author_ids = _author_identity_from_video(video)
    sampling_plan = _comment_sampling_plan(video, payload)
    if sampling_plan["max_comments"] <= 0:
        return replace_target_video_comments(
            video_id,
            [],
            status="done",
            raw_ai={
                "collector": "douyin-download-api",
                "comment_pages": [],
                "request": payload.model_dump(),
                "sampling_plan": sampling_plan,
            },
        )
    result = adapter.get_video_comments(
        aweme_id=aweme_id,
        max_items=sampling_plan["max_comments"],
        page_size=sampling_plan["page_size"],
    )
    normalized = []
    for index, comment in enumerate(result.get("items", [])):
        if not isinstance(comment, dict):
            continue
        parent = normalize_comment(
            video_id,
            aweme_id,
            comment,
            rank_index=index,
            level=1,
            author_user_ids=author_ids,
        )
        normalized.append(parent)
        if not payload.include_replies or sampling_plan["replies_per_comment"] <= 0:
            continue
        reply_total = _to_int(parent.get("reply_count"))
        if reply_total <= 0:
            continue
        try:
            replies = adapter.get_video_comment_replies(
                item_id=aweme_id,
                comment_id=parent["comment_id"],
                max_items=min(sampling_plan["replies_per_comment"], reply_total),
                page_size=min(payload.page_size, max(1, sampling_plan["replies_per_comment"])),
            )
        except Exception as exc:
            parent_source = parent.get("source_json") if isinstance(parent.get("source_json"), dict) else {}
            parent["source_json"] = {**parent_source, "reply_fetch_error": _short_error(exc)}
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
    return replace_target_video_comments(
        video_id,
        normalized,
        status="done",
        raw_ai={
            "collector": "douyin-download-api",
            "comment_pages": result.get("raw_pages", []),
            "request": payload.model_dump(),
            "sampling_plan": sampling_plan,
        },
    )


@router.post("/search")
def search(payload: TargetSearchRequest) -> dict[str, Any]:
    try:
        result = TikhubDouyinApiAdapter().search_users(keyword=payload.keyword, page=payload.page, count=payload.count)
    except TikhubApiError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
                "hint": "TikHub 搜索失败：请先核对 openapi 里 fetch_user_search 的参数，仅保留 keyword/cursor/douyin_user_fans/douyin_user_type/search_id。若仍失败，改用 v2 或把 upstream JSON 发给支持团队。",
                "demo_request": {
                    "keyword": payload.keyword,
                    "cursor": 0,
                    "douyin_user_fans": "",
                    "douyin_user_type": "",
                    "search_id": "",
                },
                "upstream": exc.to_dict(),
                "error_log_path": exc.error_log_path,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
                "hint": "TikHub 搜索失败，请检查 TIKHUB_API_KEY、TIKHUB_API_BASE 或上游接口状态。",
            },
        ) from exc
    items = [item for item in result.get("items", []) if _passes_search_filters(item, payload)]
    items = _sort_users(items, payload.sortBy)
    result["items"] = items
    result["count"] = len(items)
    result["filters"] = payload.model_dump()
    return result


@router.post("/users/bulk-save")
def bulk_save_users(payload: TargetBulkSave) -> dict[str, Any]:
    target_set = None
    set_id = payload.set_id or ""
    if set_id:
        target_set = get_target_set(set_id)
        if not target_set:
            raise HTTPException(status_code=404, detail="Target set not found")
    elif payload.set_name:
        set_id = str(uuid4())
        target_set = create_target_set(
            set_id,
            payload.set_name,
            payload.note,
            keyword=payload.keyword,
            filters=payload.filters,
        )

    saved = []
    for user in payload.users:
        user_id = _target_user_id(user)
        saved_user = upsert_target_user(user_id, _target_user_payload(user, fallback_keyword=payload.keyword))
        if set_id:
            add_user_to_target_set(set_id, user_id)
        saved.append(saved_user)

    return {
        "status": "ok",
        "set": get_target_set_detail(set_id) if set_id else target_set,
        "users": saved,
        "count": len(saved),
    }


@router.post("/sets")
def create_set(payload: TargetSetCreate) -> dict[str, Any]:
    set_id = str(uuid4())
    target_set = create_target_set(
        set_id,
        payload.name,
        payload.note,
        keyword=payload.keyword,
        filters=payload.filters,
        video_strategy=payload.video_strategy,
    )
    if payload.status and payload.status != "draft":
        target_set = update_target_set(set_id, status=payload.status)
    return target_set


@router.get("/sets")
def sets(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    return list_target_sets(limit=limit)


@router.get("/sets/{set_id}")
def set_detail(set_id: str) -> dict[str, Any]:
    target_set = get_target_set_detail(set_id)
    if not target_set:
        raise HTTPException(status_code=404, detail="Target set not found")
    return target_set


@router.patch("/sets/{set_id}")
def update_set(set_id: str, payload: TargetSetUpdate) -> dict[str, Any]:
    target_set = update_target_set(
        set_id,
        name=payload.name,
        note=payload.note,
        keyword=payload.keyword,
        filters=payload.filters,
        video_strategy=payload.video_strategy,
        status=payload.status,
    )
    if not target_set:
        raise HTTPException(status_code=404, detail="Target set not found")
    return target_set


@router.delete("/sets/{set_id}")
def remove_set(set_id: str) -> dict[str, Any]:
    deleted = delete_target_set(set_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Target set not found")
    return {"status": "ok", "deleted": True, "set_id": set_id}


@router.get("/videos/{video_id}/interactions")
def video_interactions(video_id: str) -> dict[str, Any]:
    video = resolve_target_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Target video not found")
    dataset = get_target_video_interaction_dataset(video["id"])
    target_user = get_target_user(video.get("user_id") or "")
    author = _analysis_author_payload(video, target_user)
    dataset["author"] = author
    dataset["video"] = {
        **(dataset.get("video") if isinstance(dataset.get("video"), dict) else video),
        "author": author,
        "user": author,
        "owner": author,
        "author_user_id": author.get("uid") or author.get("user_id") or video.get("user_id") or "",
    }
    return dataset


@router.post("/comments/collect")
def collect_comments(payload: CollectCommentsRequest) -> dict[str, Any]:
    if payload.video_ids:
        target_videos = [video for video_id in payload.video_ids if (video := get_target_video(video_id))]
    elif payload.set_id:
        target_videos = list_target_videos(set_id=payload.set_id, selected=True, limit=2000)
    else:
        raise HTTPException(status_code=400, detail="set_id or video_ids is required")

    adapter = DouyinDownloadApiAdapter()
    saved = []
    errors = []
    for video in target_videos:
        video_id = video["id"]
        try:
            saved.append(_collect_video_comment_snapshot(video, adapter, payload))
        except Exception as exc:
            mark_target_video_comment_snapshot(video_id, "failed", _short_error(exc))
            errors.append({"video_id": video_id, "aweme_id": video.get("aweme_id"), "error": _short_error(exc)})
    return {"status": "ok", "count": len(saved), "datasets": saved, "errors": errors}


@router.delete("/videos/{video_id}/analysis")
def delete_video_analysis(video_id: str, delete_archives: bool = Query(default=True)) -> dict[str, Any]:
    video = resolve_target_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Target video not found")

    resolved_video_id = str(video.get("id") or video_id)
    target_tasks = list_target_tasks(video_id=resolved_video_id, limit=2000)
    linked_task_id = str(video.get("analysis_task_id") or "")
    if linked_task_id and linked_task_id not in {str(item.get("task_id") or "") for item in target_tasks}:
        target_tasks.append(
            {
                "id": "",
                "task_id": linked_task_id,
                "status": video.get("analysis_status") or "",
            }
        )
    active_tasks = []
    for target_task in target_tasks:
        ai_task_id = str(target_task.get("task_id") or "")
        if not ai_task_id:
            continue
        job = get_ai_video_job(ai_task_id)
        if job and job.get("status") in {"running", "claimed"}:
            active_tasks.append({"target_task_id": target_task.get("id"), "task_id": ai_task_id, "status": job.get("status")})
    if active_tasks:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "该视频拆解任务正在运行，请先在 AI 视频队列中取消或等待结束后再删除拆解。",
                "active_tasks": active_tasks,
            },
        )

    deleted_tasks = []
    for target_task in target_tasks:
        ai_task_id = str(target_task.get("task_id") or "")
        deleted_job = delete_ai_video_job(ai_task_id) if ai_task_id else None
        deleted_generic_task = delete_task(ai_task_id, delete_archives=delete_archives) if ai_task_id else False
        deleted_tasks.append(
            {
                "target_task_id": target_task.get("id"),
                "task_id": ai_task_id,
                "target_status": target_task.get("status"),
                "queue_deleted": bool(deleted_job and deleted_job.get("deleted")),
                "task_deleted": bool(deleted_generic_task),
            }
        )

    cleared_video = clear_target_video_analysis(resolved_video_id)
    if not cleared_video:
        raise HTTPException(status_code=404, detail="Target video not found")
    return {
        "status": "ok",
        "deleted": True,
        "video": cleared_video,
        "deleted_tasks": deleted_tasks,
        "preserved": ["video_metrics", "comments", "comment_replies", "interaction_insights"],
        "delete_archives": delete_archives,
    }


@router.post("/videos/collect")
def collect_videos(payload: CollectVideosRequest) -> dict[str, Any]:
    target_set = get_target_set_detail(payload.set_id)
    if not target_set:
        raise HTTPException(status_code=404, detail="Target set not found")
    users = [user for user in target_set.get("users", []) if not payload.user_ids or user["id"] in payload.user_ids]
    adapter = TikhubDouyinApiAdapter()
    saved = []
    errors = []
    for user in users:
        try:
            result = None
            attempts = []
            for candidate in _user_video_query_candidates(user):
                attempts.append(candidate)
                try:
                    result = adapter.get_user_videos(
                        sec_user_id=candidate.get("sec_user_id") or None,
                        unique_id=candidate.get("unique_id") or None,
                        count=payload.strategy.fetch_count,
                    )
                    break
                except Exception as exc:
                    attempts[-1]["error"] = _short_error(exc)
            if result is None:
                raise RuntimeError(attempts[-1].get("error") if attempts else "缺少 sec_user_id 或 unique_id，无法采集作品")
            videos = [video for video in result.get("items", []) if not _looks_like_tiktok_noise(video)]
            if not videos:
                raise RuntimeError("接口成功但未返回有效作品，可能是账号私密、无作品、ID 不匹配或上游仅返回空列表")
            selected_videos = _select_videos(videos, payload.strategy)
            for video in selected_videos:
                aweme_id = str(video.get("aweme_id") or uuid4())
                saved.append(
                    create_target_video(
                        aweme_id,
                        user["id"],
                        {
                            "set_id": payload.set_id,
                            "aweme_id": aweme_id,
                            "desc": video.get("desc", ""),
                            "cover_url": video.get("cover_url") or "",
                            "play_url": video.get("play_url") or "",
                            "download_url": video.get("download_url") or video.get("source_video_url") or "",
                            "create_time": video.get("create_time"),
                            "digg_count": video.get("digg_count"),
                            "comment_count": video.get("comment_count"),
                            "share_count": video.get("share_count"),
                            "collect_count": video.get("collect_count"),
                            "play_count": video.get("play_count"),
                            "is_top": video.get("is_top"),
                            "selection_strategy": payload.strategy.mode,
                            "selected": True,
                            "source_json": video,
                        },
                    )
                )
        except Exception as exc:
            errors.append({"user_id": user["id"], "nickname": user.get("nickname"), "error": _short_error(exc)})
    return {"status": "ok", "count": len(saved), "videos": saved, "errors": errors}


@router.post("/analysis/enqueue")
def enqueue_analysis(payload: EnqueueAnalysisRequest) -> dict[str, Any]:
    if payload.video_ids:
        target_videos = [video for video_id in payload.video_ids if (video := get_target_video(video_id))]
    elif payload.set_id:
        target_videos = list_target_videos(set_id=payload.set_id, selected=True, limit=2000)
    else:
        raise HTTPException(status_code=400, detail="set_id or video_ids is required")

    instance = ai_video_adapter()
    provider = payload.provider or active_ai_provider(instance.provider)
    enqueued = []
    skipped = []
    comment_errors = []
    for target_video in target_videos:
        existing = find_target_task_for_video(target_video["id"], {"pending", "running", "done"})
        if existing and not payload.force:
            skipped.append({"video_id": target_video["id"], "task_id": existing.get("task_id"), "status": existing.get("status")})
            continue

        target_user = get_target_user(target_video.get("user_id") or "")
        analysis_video = _analysis_video_payload(target_video, target_user)
        target_context = _analysis_target_context(target_video, target_user)
        analysis_video["douyin_target_context"] = target_context
        comment_collection = {
            "enabled": payload.collect_comments,
            "adaptive_by_ratio": payload.adaptive_comments,
            "max_comments": payload.max_comments,
            "min_comments": payload.min_comments,
            "page_size": 20,
            "include_replies": True,
            "replies_per_comment": payload.replies_per_comment,
        }
        task_id = f"target-breakdown-{target_video.get('aweme_id') or target_video['id']}-{int(time.time())}-{uuid4().hex[:8]}"
        task = create_task(
            task_id=task_id,
            task_type="ai_video_analysis",
            title=video_title(analysis_video),
            provider=provider,
            payload={
                "video": analysis_video,
                "author": analysis_video.get("author") or {},
                "douyin_target": target_context,
                "comment_collection": comment_collection,
            },
            message="已从抖音对标工具加入拆解队列，等待评论数据",
        )
        enqueue_ai_video_job(task_id=task_id, video=analysis_video, provider=provider)
        target_task = create_target_task(
            f"target-task-{uuid4().hex}",
            set_id=target_video.get("set_id") or payload.set_id,
            user_id=target_video.get("user_id") or "",
            video_id=target_video["id"],
            ai_task_id=task_id,
            status=task.get("status") or "pending",
            strategy=target_video.get("selection_strategy") or "",
        )
        enqueued.append({"task": task, "target_task": target_task, "video": target_video})
    return {
        "status": "ok",
        "enqueued": enqueued,
        "skipped": skipped,
        "comment_errors": comment_errors,
        "count": len(enqueued),
        "queue": queue_stats(),
    }


@router.post("/analysis/sync")
def sync_analysis_tasks(set_id: str | None = None) -> dict[str, Any]:
    target_tasks = list_target_tasks(set_id=set_id, limit=2000)
    synced = []
    missing = []
    for target_task in target_tasks:
        ai_task = get_task(target_task.get("task_id") or "")
        if not ai_task:
            missing.append(target_task)
            continue
        updated = update_target_task_from_ai_task(target_task["id"], ai_task)
        if updated:
            synced.append(updated)
    return {"status": "ok", "synced": synced, "missing": missing, "count": len(synced)}


@router.post("/analysis/{task_id}/retry-comments")
def retry_analysis_comments(task_id: str) -> dict[str, Any]:
    return retry_job_comments(task_id)
