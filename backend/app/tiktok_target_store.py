from __future__ import annotations

import hashlib
import json
import time
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.postgres_store import ensure_columns, pg_connection, placeholders, quote_identifier, run_once

CHINA_TZ = timezone(timedelta(hours=8))

GENRE_ALIASES = {
    "tarot": "mysticism",
    "mystic": "mysticism",
    "mysticism": "mysticism",
    "astrology": "mysticism",
    "\u7384\u5b66": "mysticism",
    "\u5854\u7f57": "mysticism",
    "\u5360\u535c": "mysticism",
    "\u661f\u5ea7": "mysticism",
}

GENERIC_INTERACTION_KEYWORDS = (
    "\u592a\u771f\u5b9e",
    "\u8fd9\u5c31\u662f\u6211",
    "\u5171\u9e23",
    "\u7834\u9632",
    "\u540c\u611f",
    "\u8bf4\u5230\u5fc3\u91cc",
    "\u771f\u7684\u5047\u7684",
    "\u6211\u4e0d\u4fe1",
    "\u6709\u4f9d\u636e\u5417",
    "\u79bb\u8c31",
    "\u667a\u5546\u7a0e",
    "\u54ea\u91cc\u4e70",
    "\u600e\u4e48\u4e70",
    "\u6c42\u94fe\u63a5",
    "\u94fe\u63a5",
    "\u591a\u5c11\u94b1",
    "\u600e\u4e48\u6536\u8d39",
    "\u540c\u6b3e",
    "\u56e2\u8d2d",
    "\u6253\u5361",
    "\u7559\u540d",
    "\u8e72",
    "\u63d2\u773c",
    "\u6c42\u6559\u7a0b",
    "\u6559\u7a0b",
    "\u6c42\u65b9\u6cd5",
    "\u600e\u4e48\u505a",
    "\u600e\u4e48\u529e",
    "\u600e\u4e48\u9009",
    "\u63a8\u8350",
    "\u907f\u5751",
    "\u8c22\u8c22",
    "\u611f\u8c22",
    "\u5b66\u5230\u4e86",
    "\u6709\u7528",
    "\u6536\u85cf",
    "\u7801\u4f4f",
    "\u5e72\u8d27",
)

GENRE_INTERACTION_KEYWORDS = {
    "mysticism": (
        "\u9886\u53d6\u597d\u8fd0",
        "\u63a5\u597d\u8fd0",
        "\u663e\u5316",
        "\u63a5",
        "\u7cbe\u51c6",
        "\u597d\u8fd0",
        "\u8bb8\u613f",
        "\u8fd8\u613f",
        "\u611f\u6069",
        "\u592a\u51c6",
        "\u51c6",
        "\u5012\u9709",
        "\u5931\u604b",
        "\u5206\u624b",
        "\u7126\u8651",
        "\u96be\u53d7",
        "\u590d\u5408",
        "\u6b63\u7f18",
        "\u6843\u82b1",
        "\u4e0a\u5cb8",
        "\u4e8b\u4e1a",
        "\u8d22\u8fd0",
        "\u66b4\u5bcc",
    ),
}

INTERACTION_KEYWORDS = GENERIC_INTERACTION_KEYWORDS

MOTIVATION_BUCKETS = {
    "resonance": (
        "\u592a\u771f\u5b9e",
        "\u8fd9\u5c31\u662f\u6211",
        "\u5171\u9e23",
        "\u7834\u9632",
        "\u540c\u611f",
        "\u8bf4\u5230\u5fc3\u91cc",
        "\u61c2\u6211",
        "\u771f\u5b9e",
    ),
    "doubt_or_controversy": (
        "\u771f\u7684\u5047\u7684",
        "\u6211\u4e0d\u4fe1",
        "\u6709\u4f9d\u636e\u5417",
        "\u79bb\u8c31",
        "\u4e0d\u53ef\u80fd",
        "\u9a97\u4eba",
        "\u667a\u5546\u7a0e",
        "\u4e0d\u662f\u5427",
    ),
    "purchase_or_link": (
        "\u54ea\u91cc\u4e70",
        "\u600e\u4e48\u4e70",
        "\u6c42\u94fe\u63a5",
        "\u94fe\u63a5",
        "\u591a\u5c11\u94b1",
        "\u4ef7\u683c",
        "\u540c\u6b3e",
        "\u56e2\u8d2d",
        "\u4e0b\u5355",
        "\u5e97\u540d",
        "\u5730\u5740",
        "\u600e\u4e48\u6536\u8d39",
    ),
    "checkin_or_ritual": (
        "\u6253\u5361",
        "\u7559\u540d",
        "\u8e72",
        "\u63d2\u773c",
        "\u575a\u6301",
        "\u8bb0\u5f55",
    ),
    "advice_or_question": (
        "\u600e\u4e48\u505a",
        "\u600e\u4e48\u529e",
        "\u6c42\u6559\u7a0b",
        "\u6559\u7a0b",
        "\u6c42\u65b9\u6cd5",
        "\u600e\u4e48\u5f04",
        "\u600e\u4e48\u9009",
        "\u63a8\u8350",
        "\u6c42\u63a8\u8350",
        "\u907f\u5751",
    ),
    "thanks_or_validation": (
        "\u8c22\u8c22",
        "\u611f\u8c22",
        "\u5b66\u5230\u4e86",
        "\u6709\u7528",
        "\u6536\u85cf\u4e86",
        "\u5df2\u6536\u85cf",
        "\u7801\u4f4f",
        "\u9a6c\u514b",
        "\u5e72\u8d27",
        "\u9760\u8c31",
    ),
}

GENRE_MOTIVATION_BUCKETS = {
    "mysticism": {
        "mysticism_manifest": (
            "\u63a5",
            "\u9886\u53d6",
            "\u663e\u5316",
            "\u597d\u8fd0",
            "\u8bb8\u613f",
            "\u8e72",
            "\u6c42",
        ),
        "mysticism_distress": (
            "\u5012\u9709",
            "\u5931\u604b",
            "\u5206\u624b",
            "\u7126\u8651",
            "\u96be\u53d7",
            "\u5d29\u6e83",
            "\u4f4e\u8c37",
            "\u4e0d\u987a",
            "\u600e\u4e48\u529e",
        ),
        "mysticism_thanks_validation": (
            "\u8fd8\u613f",
            "\u611f\u6069",
            "\u8c22\u8c22",
            "\u51c6",
            "\u7075",
            "\u5b9e\u73b0",
        ),
        "mysticism_relationship": (
            "\u590d\u5408",
            "\u6b63\u7f18",
            "\u6843\u82b1",
            "\u524d\u4efb",
            "\u8131\u5355",
        ),
        "mysticism_money_career": (
            "\u8d22\u8fd0",
            "\u4e0a\u5cb8",
            "\u4e8b\u4e1a",
            "\u5de5\u4f5c",
            "\u66b4\u5bcc",
            "offer",
        ),
    },
}

EMOTION_BUCKETS = MOTIVATION_BUCKETS

RETENTION_TACTIC_KEYWORDS = {
    "ask_for_comment": ("\u8bc4\u8bba", "\u7559\u8a00", "\u544a\u8bc9\u6211", "\u8bc4\u8bba\u533a", "\u4f60\u600e\u4e48\u770b"),
    "private_conversion": ("\u79c1\u4fe1", "\u4e3b\u9875", "\u7c89\u4e1d\u7fa4", "\u52a0\u7fa4", "\u54a8\u8be2"),
    "pin_or_thread": ("\u7f6e\u9876", "\u76d6\u697c", "\u8e72", "\u63d2\u773c", "\u697c\u4e2d\u697c"),
    "next_content": ("\u4e0b\u4e00\u6761", "\u660e\u5929", "\u540e\u7eed", "\u7b49\u6211", "\u4e0b\u671f", "\u5408\u96c6"),
    "purchase_conversion": ("\u94fe\u63a5", "\u6a71\u7a97", "\u56e2\u8d2d", "\u4f18\u60e0", "\u4e0b\u5355", "\u540c\u6b3e"),
    "save_or_share_prompt": ("\u6536\u85cf", "\u8f6c\u53d1", "\u5206\u4eab", "\u5b58\u4e0b", "\u7801\u4f4f"),
}

GENRE_RETENTION_TACTIC_KEYWORDS = {
    "mysticism": {
        "mysticism_claim_or_manifest": ("\u63a5", "\u9886\u53d6", "\u663e\u5316", "\u8bb8\u613f", "\u8fd8\u613f"),
    },
}

LEGACY_MYSTICISM_INTERACTION_KEYWORDS = (
    "\u9886\u53d6\u597d\u8fd0",
    "\u63a5\u597d\u8fd0",
    "\u663e\u5316",
    "\u63a5",
    "\u7cbe\u51c6",
    "\u597d\u8fd0",
    "\u8bb8\u613f",
    "\u8fd8\u613f",
    "\u611f\u6069",
    "\u8c22\u8c22",
    "\u592a\u51c6",
    "\u51c6",
    "\u5012\u9709",
    "\u5931\u604b",
    "\u5206\u624b",
    "\u7126\u8651",
    "\u96be\u53d7",
    "\u590d\u5408",
    "\u6b63\u7f18",
    "\u6843\u82b1",
    "\u4e0a\u5cb8",
    "\u4e8b\u4e1a",
    "\u8d22\u8fd0",
    "\u66b4\u5bcc",
    "\u79c1\u4fe1",
    "\u7f6e\u9876",
    "\u8e72",
)

TARGET_USER_COLUMNS = {
    "avatar_url": "avatar_url TEXT NOT NULL DEFAULT ''",
    "signature": "signature TEXT NOT NULL DEFAULT ''",
    "ip_location": "ip_location TEXT NOT NULL DEFAULT ''",
    "total_favorited": "total_favorited INTEGER",
    "aweme_count": "aweme_count INTEGER",
    "following_count": "following_count INTEGER",
    "is_private": "is_private INTEGER NOT NULL DEFAULT 0",
    "last_post_at": "last_post_at INTEGER",
    "searched_at": "searched_at INTEGER",
}

TARGET_SET_COLUMNS = {
    "keyword": "keyword TEXT NOT NULL DEFAULT ''",
    "filters_json": "filters_json TEXT NOT NULL DEFAULT '{}'",
    "video_strategy_json": "video_strategy_json TEXT NOT NULL DEFAULT '{}'",
    "deleted_at": "deleted_at INTEGER",
}

TARGET_SET_USER_COLUMNS = {
    "deleted_at": "deleted_at INTEGER",
}

TARGET_VIDEO_COLUMNS = {
    "set_id": "set_id TEXT NOT NULL DEFAULT ''",
    "create_time": "create_time INTEGER",
    "publish_hour": "publish_hour INTEGER",
    "publish_weekday": "publish_weekday INTEGER",
    "publish_date": "publish_date TEXT NOT NULL DEFAULT ''",
    "publish_hour_bucket": "publish_hour_bucket TEXT NOT NULL DEFAULT ''",
    "digg_count": "digg_count INTEGER",
    "comment_count": "comment_count INTEGER",
    "share_count": "share_count INTEGER",
    "collect_count": "collect_count INTEGER",
    "play_count": "play_count INTEGER",
    "like_collect_ratio": "like_collect_ratio REAL",
    "collect_like_ratio": "collect_like_ratio REAL",
    "comment_like_ratio": "comment_like_ratio REAL",
    "share_like_ratio": "share_like_ratio REAL",
    "engagement_score": "engagement_score REAL",
    "engagement_rate": "engagement_rate REAL",
    "description": "description TEXT NOT NULL DEFAULT ''",
    "metrics_json": "metrics_json TEXT NOT NULL DEFAULT '{}'",
    "comment_snapshot_status": "comment_snapshot_status TEXT NOT NULL DEFAULT 'none'",
    "comment_snapshot_at": "comment_snapshot_at INTEGER",
    "comment_saved_count": "comment_saved_count INTEGER NOT NULL DEFAULT 0",
    "reply_saved_count": "reply_saved_count INTEGER NOT NULL DEFAULT 0",
    "is_top": "is_top INTEGER NOT NULL DEFAULT 0",
    "selection_strategy": "selection_strategy TEXT NOT NULL DEFAULT ''",
    "analysis_status": "analysis_status TEXT NOT NULL DEFAULT 'none'",
    "analysis_task_id": "analysis_task_id TEXT NOT NULL DEFAULT ''",
    "analysis_result_json": "analysis_result_json TEXT NOT NULL DEFAULT '{}'",
    "analyzed_at": "analyzed_at INTEGER",
    "deleted_at": "deleted_at INTEGER",
}

TARGET_TASK_COLUMNS = {
    "strategy": "strategy TEXT NOT NULL DEFAULT ''",
    "retry_count": "retry_count INTEGER NOT NULL DEFAULT 0",
    "synced_at": "synced_at INTEGER",
    "deleted_at": "deleted_at INTEGER",
}

TARGET_VIDEO_COMMENT_COLUMNS = {
    "deleted_at": "deleted_at INTEGER",
}

TARGET_VIDEO_INTERACTION_INSIGHT_COLUMNS = {
    "deleted_at": "deleted_at INTEGER",
}

TARGET_VIDEO_COMMENT_PAGE_COLUMNS = {
    "cache_key": "cache_key TEXT NOT NULL DEFAULT ''",
    "source": "source TEXT NOT NULL DEFAULT ''",
    "video_id": "video_id TEXT NOT NULL DEFAULT ''",
    "aweme_id": "aweme_id TEXT NOT NULL DEFAULT ''",
    "item_id": "item_id TEXT NOT NULL DEFAULT ''",
    "comment_id": "comment_id TEXT NOT NULL DEFAULT ''",
    "page_kind": "page_kind TEXT NOT NULL DEFAULT 'comments'",
    "cursor": "cursor INTEGER NOT NULL DEFAULT 0",
    "count": "count INTEGER NOT NULL DEFAULT 0",
    "request_json": "request_json TEXT NOT NULL DEFAULT '{}'",
    "items_json": "items_json TEXT NOT NULL DEFAULT '[]'",
    "raw_json": "raw_json TEXT NOT NULL DEFAULT '{}'",
    "pagination_json": "pagination_json TEXT NOT NULL DEFAULT '{}'",
    "normalized_json": "normalized_json TEXT NOT NULL DEFAULT '{}'",
    "fetched_at": "fetched_at INTEGER",
}


def connect():
    return pg_connection("tiktok_target")


def cache_connection():
    return pg_connection("tiktok_target_cache")


def _cache_key(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_video_comment_page_cache_key(
    *,
    source: str,
    video_id: str,
    aweme_id: str = "",
    item_id: str = "",
    comment_id: str = "",
    page_kind: str = "comments",
    cursor: int = 0,
    count: int = 20,
) -> str:
    return _cache_key(
        {
            "source": source,
            "video_id": video_id,
            "aweme_id": aweme_id or "",
            "item_id": item_id or "",
            "comment_id": comment_id or "",
            "page_kind": page_kind,
            "cursor": int(cursor or 0),
            "count": int(count or 0),
        }
    )


def init_db() -> None:
    def initialize() -> None:
        _init_db()

    run_once("tiktok_target_store", initialize)


def _init_db() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_users (
                id TEXT PRIMARY KEY,
                keyword TEXT NOT NULL DEFAULT '',
                sec_user_id TEXT NOT NULL DEFAULT '',
                unique_id TEXT NOT NULL DEFAULT '',
                nickname TEXT NOT NULL DEFAULT '',
                follower_count INTEGER,
                like_count INTEGER,
                recent_update_at INTEGER,
                verified INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'candidate',
                source_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_sets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_set_users (
                id TEXT PRIMARY KEY,
                set_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(set_id, user_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_videos (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                aweme_id TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                cover_url TEXT NOT NULL DEFAULT '',
                play_url TEXT NOT NULL DEFAULT '',
                download_url TEXT NOT NULL DEFAULT '',
                source_json TEXT NOT NULL DEFAULT '{}',
                selected INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(user_id, aweme_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_tasks (
                id TEXT PRIMARY KEY,
                set_id TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL DEFAULT '',
                video_id TEXT NOT NULL DEFAULT '',
                task_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                result_json TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_video_comments (
                id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                aweme_id TEXT NOT NULL DEFAULT '',
                comment_id TEXT NOT NULL DEFAULT '',
                parent_comment_id TEXT NOT NULL DEFAULT '',
                reply_to_comment_id TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL DEFAULT '',
                sec_uid TEXT NOT NULL DEFAULT '',
                unique_id TEXT NOT NULL DEFAULT '',
                nickname TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL DEFAULT '',
                digg_count INTEGER,
                reply_count INTEGER,
                create_time INTEGER,
                is_pinned INTEGER NOT NULL DEFAULT 0,
                is_author INTEGER NOT NULL DEFAULT 0,
                rank_index INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                source_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                deleted_at INTEGER,
                UNIQUE(video_id, comment_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_video_interaction_insights (
                video_id TEXT PRIMARY KEY,
                aweme_id TEXT NOT NULL DEFAULT '',
                comment_count_saved INTEGER NOT NULL DEFAULT 0,
                reply_count_saved INTEGER NOT NULL DEFAULT 0,
                keyword_counts_json TEXT NOT NULL DEFAULT '{}',
                symbol_counts_json TEXT NOT NULL DEFAULT '{}',
                emotion_profile_json TEXT NOT NULL DEFAULT '{}',
                creator_reply_tactics_json TEXT NOT NULL DEFAULT '{}',
                top_comments_json TEXT NOT NULL DEFAULT '[]',
                pinned_comments_json TEXT NOT NULL DEFAULT '[]',
                author_replies_json TEXT NOT NULL DEFAULT '[]',
                raw_ai_json TEXT NOT NULL DEFAULT '{}',
                analyzed_at INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                deleted_at INTEGER
            )
            """
        )
        ensure_columns(connection, "tiktok_target_users", TARGET_USER_COLUMNS)
        ensure_columns(connection, "tiktok_target_sets", TARGET_SET_COLUMNS)
        ensure_columns(connection, "tiktok_target_set_users", TARGET_SET_USER_COLUMNS)
        ensure_columns(connection, "tiktok_target_videos", TARGET_VIDEO_COLUMNS)
        ensure_columns(connection, "tiktok_target_tasks", TARGET_TASK_COLUMNS)
        ensure_columns(connection, "tiktok_target_video_comments", TARGET_VIDEO_COMMENT_COLUMNS)
        ensure_columns(connection, "tiktok_target_video_interaction_insights", TARGET_VIDEO_INTERACTION_INSIGHT_COLUMNS)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_users_keyword ON tiktok_target_users(keyword, status)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_videos_user ON tiktok_target_videos(user_id, selected)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_set_users_set ON tiktok_target_set_users(set_id, deleted_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_videos_set ON tiktok_target_videos(set_id, selected)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_videos_metrics ON tiktok_target_videos(set_id, engagement_score DESC, digg_count DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_tasks_status ON tiktok_target_tasks(status, created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_tasks_video ON tiktok_target_tasks(video_id, status)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_comments_video ON tiktok_target_video_comments(video_id, level, rank_index)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_comments_parent ON tiktok_target_video_comments(video_id, parent_comment_id)")
        connection.execute(
            """
            UPDATE tiktok_target_users
            SET recent_update_at = COALESCE(NULLIF(recent_update_at, 0), NULLIF(searched_at, 0), created_at),
                last_post_at = COALESCE(NULLIF(last_post_at, 0), NULLIF(searched_at, 0), created_at)
            WHERE recent_update_at IS NULL
               OR recent_update_at = 0
               OR last_post_at IS NULL
               OR last_post_at = 0
            """
        )
        _backfill_target_user_profile_fields(connection)
    with cache_connection() as connection:
        connection.execute("DROP TABLE IF EXISTS tiktok_target_user_video_pages")
        connection.execute("DROP TABLE IF EXISTS tiktok_target_user_search_pages")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_target_video_comment_pages (
                id TEXT PRIMARY KEY,
                cache_key TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL DEFAULT '',
                video_id TEXT NOT NULL DEFAULT '',
                aweme_id TEXT NOT NULL DEFAULT '',
                item_id TEXT NOT NULL DEFAULT '',
                comment_id TEXT NOT NULL DEFAULT '',
                page_kind TEXT NOT NULL DEFAULT 'comments',
                cursor INTEGER NOT NULL DEFAULT 0,
                count INTEGER NOT NULL DEFAULT 0,
                request_json TEXT NOT NULL DEFAULT '{}',
                items_json TEXT NOT NULL DEFAULT '[]',
                raw_json TEXT NOT NULL DEFAULT '{}',
                pagination_json TEXT NOT NULL DEFAULT '{}',
                normalized_json TEXT NOT NULL DEFAULT '{}',
                fetched_at INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        ensure_columns(connection, "tiktok_target_video_comment_pages", TARGET_VIDEO_COMMENT_PAGE_COLUMNS)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_video_comment_pages_cache ON tiktok_target_video_comment_pages(cache_key)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_target_video_comment_pages_video ON tiktok_target_video_comment_pages(video_id, page_kind, cursor)")


def now() -> int:
    return int(time.time())


def load_json(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _target_user_source_candidates(source: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(value: Any, depth: int = 0) -> None:
        if not isinstance(value, dict) or depth > 4:
            return
        marker = id(value)
        if marker in seen:
            return
        seen.add(marker)
        candidates.append(value)
        for key in (
            "user",
            "user_info",
            "profile",
            "author",
            "owner",
            "account",
            "data",
            "raw",
            "payload",
            "result",
        ):
            add(value.get(key), depth + 1)

    add(source)
    return candidates


def _first_text_from_user_source(source: Any, keys: tuple[str, ...]) -> str:
    for candidate in _target_user_source_candidates(source):
        for key in keys:
            value = candidate.get(key)
            if value is None or value == "" or isinstance(value, (dict, list)):
                continue
            text = str(value).strip()
            if text:
                return text
    return ""


def _first_int_from_user_source(source: Any, keys: tuple[str, ...]) -> int | None:
    fallback: int | None = None
    for candidate in _target_user_source_candidates(source):
        for key in keys:
            number = to_int(candidate.get(key))
            if number is None:
                continue
            if number > 0:
                return number
            if fallback is None:
                fallback = number
    return fallback


def _backfill_target_user_profile_fields(connection: Any) -> None:
    rows = connection.execute(
        """
        SELECT id, source_json, signature, ip_location, follower_count, like_count,
               total_favorited, aweme_count, following_count
        FROM tiktok_target_users
        WHERE signature = ''
           OR ip_location = ''
           OR follower_count IS NULL
           OR like_count IS NULL
           OR total_favorited IS NULL
           OR aweme_count IS NULL
           OR following_count IS NULL
        """
    ).fetchall()
    for row in rows:
        source = load_json(row.get("source_json"), {})
        if not isinstance(source, dict):
            continue
        updates: dict[str, Any] = {}
        signature = _first_text_from_user_source(source, ("signature", "desc", "intro", "bio"))
        if not row.get("signature") and signature:
            updates["signature"] = signature
        ip_location = _first_text_from_user_source(source, ("ip_location", "ipLocation", "location"))
        if not row.get("ip_location") and ip_location:
            updates["ip_location"] = ip_location

        follower_count = _first_int_from_user_source(source, ("follower_count", "followers", "followerCount", "fans_cnt", "fans_count"))
        if row.get("follower_count") in [None, ""] and follower_count is not None:
            updates["follower_count"] = follower_count

        like_count = _first_int_from_user_source(source, ("like_count", "total_favorited", "total_favorited_count", "like_cnt"))
        if row.get("like_count") in [None, ""] and like_count is not None:
            updates["like_count"] = like_count

        total_favorited = _first_int_from_user_source(source, ("total_favorited", "total_favorited_count", "like_count", "like_cnt"))
        if total_favorited is None and row.get("like_count") not in [None, ""]:
            total_favorited = to_int(row.get("like_count"))
        if row.get("total_favorited") in [None, ""] and total_favorited is not None:
            updates["total_favorited"] = total_favorited

        aweme_count = _first_int_from_user_source(source, ("aweme_count", "video_count", "awemeCount", "publish_cnt", "publish_count"))
        if row.get("aweme_count") in [None, ""] and aweme_count is not None:
            updates["aweme_count"] = aweme_count

        following_count = _first_int_from_user_source(source, ("following_count", "follow_count", "following", "followingCount"))
        if row.get("following_count") in [None, ""] and following_count is not None:
            updates["following_count"] = following_count

        if not updates:
            continue
        updates["updated_at"] = now()
        set_clause = ", ".join(f"{quote_identifier(column)} = %s" for column in updates)
        connection.execute(
            f"UPDATE tiktok_target_users SET {set_clause} WHERE id = %s",
            (*updates.values(), row["id"]),
        )


def first_positive_int(*values: Any, default: int = 1) -> int:
    for value in values:
        number = to_int(value)
        if number is not None and number > 0:
            return number
    return default


def normalize_genre(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    return GENRE_ALIASES.get(lowered) or GENRE_ALIASES.get(raw) or lowered


def infer_interaction_genre(video: dict[str, Any] | None = None, *, comments: list[dict[str, Any]] | None = None) -> str:
    video = video or {}
    source = video.get("source_json") if isinstance(video.get("source_json"), dict) else {}
    metrics = video.get("metrics") if isinstance(video.get("metrics"), dict) else {}
    candidates = [
        video.get("genre"),
        source.get("genre"),
        source.get("category"),
        metrics.get("genre"),
        video.get("selection_strategy"),
        video.get("desc"),
    ]
    for value in candidates:
        genre = normalize_genre(value)
        if genre in GENRE_MOTIVATION_BUCKETS or genre in GENRE_INTERACTION_KEYWORDS:
            return genre
    text_parts = [str(value or "") for value in candidates if value]
    if comments:
        text_parts.extend(str(comment.get("text") or "") for comment in comments[:30])
    combined = re.sub(r"\s+", "", " ".join(text_parts)).lower()
    for alias, canonical in GENRE_ALIASES.items():
        if alias.lower() in combined:
            return canonical
    return normalize_genre(candidates[0]) if candidates and candidates[0] else ""


def to_float_ratio(numerator: Any, denominator: Any) -> float | None:
    num = to_int(numerator)
    den = to_int(denominator)
    if num is None or den in (None, 0):
        return None
    return round(num / den, 6)


def publish_bucket(hour: int | None) -> str:
    if hour is None:
        return ""
    if 0 <= hour <= 5:
        return "late_night"
    if 6 <= hour <= 10:
        return "morning"
    if 11 <= hour <= 13:
        return "noon"
    if 14 <= hour <= 17:
        return "afternoon"
    if 18 <= hour <= 21:
        return "evening"
    return "night"


def derive_video_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    create_time = to_int(payload.get("create_time"))
    digg_count = to_int(payload.get("digg_count")) or 0
    comment_count = to_int(payload.get("comment_count")) or 0
    share_count = to_int(payload.get("share_count")) or 0
    collect_count = to_int(payload.get("collect_count")) or 0
    source_json = payload.get("source_json") if isinstance(payload.get("source_json"), dict) else {}
    metrics_json = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    raw_json = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
    nested_stats = source_json.get("statistics") if isinstance(source_json.get("statistics"), dict) else {}
    nested_raw_stats = raw_json.get("statistics") if isinstance(raw_json.get("statistics"), dict) else {}
    play_count = first_positive_int(
        payload.get("play_count"),
        payload.get("play_count_raw"),
        metrics_json.get("play_count"),
        metrics_json.get("play_count_raw"),
        source_json.get("play_count"),
        source_json.get("playCount"),
        source_json.get("view_count"),
        source_json.get("video_view_count"),
        nested_stats.get("play_count"),
        nested_stats.get("playCount"),
        nested_stats.get("view_count"),
        nested_stats.get("video_view_count"),
        raw_json.get("play_count"),
        raw_json.get("playCount"),
        raw_json.get("view_count"),
        raw_json.get("video_view_count"),
        nested_raw_stats.get("play_count"),
        nested_raw_stats.get("playCount"),
        nested_raw_stats.get("view_count"),
        nested_raw_stats.get("video_view_count"),
    )
    published = datetime.fromtimestamp(create_time, CHINA_TZ) if create_time else None
    engagement_score = digg_count + comment_count * 3 + share_count * 5 + collect_count * 4
    engagement_rate = round(engagement_score / play_count, 6) if play_count else None
    metrics = {
        "publish_hour": published.hour if published else None,
        "publish_weekday": published.weekday() if published else None,
        "publish_date": published.strftime("%Y-%m-%d") if published else "",
        "publish_hour_bucket": publish_bucket(published.hour if published else None),
        "digg_count": digg_count,
        "comment_count": comment_count,
        "share_count": share_count,
        "collect_count": collect_count,
        "play_count": play_count,
        "like_collect_ratio": to_float_ratio(digg_count, collect_count),
        "collect_like_ratio": to_float_ratio(collect_count, digg_count),
        "comment_like_ratio": to_float_ratio(comment_count, digg_count),
        "share_like_ratio": to_float_ratio(share_count, digg_count),
        "engagement_score": engagement_score,
        "engagement_rate": engagement_rate,
        "play_count_raw": to_int(payload.get("play_count")) or 0,
    }
    metrics["metrics_json"] = {
        "ratios": {
            "like_collect_ratio": metrics["like_collect_ratio"],
            "collect_like_ratio": metrics["collect_like_ratio"],
            "comment_like_ratio": metrics["comment_like_ratio"],
            "share_like_ratio": metrics["share_like_ratio"],
        },
        "weights": {
            "engagement_score": "digg + comment*3 + share*5 + collect*4",
        },
        "publish": {
            "hour": metrics["publish_hour"],
            "weekday": metrics["publish_weekday"],
            "date": metrics["publish_date"],
            "bucket": metrics["publish_hour_bucket"],
            "timezone": "Asia/Shanghai",
        },
    }
    return metrics


def row_to_target_user(row: Any) -> dict[str, Any]:
    user = dict(row)
    user["verified"] = bool(user.get("verified"))
    user["is_private"] = bool(user.get("is_private"))
    user["source_json"] = load_json(user.get("source_json"), {})
    source = user["source_json"] if isinstance(user["source_json"], dict) else {}
    if not user.get("signature"):
        user["signature"] = _first_text_from_user_source(source, ("signature", "desc", "intro", "bio"))
    if not user.get("ip_location"):
        user["ip_location"] = _first_text_from_user_source(source, ("ip_location", "ipLocation", "location"))
    if user.get("total_favorited") in [None, ""] and user.get("like_count") not in [None, ""]:
        user["total_favorited"] = user.get("like_count")
    if user.get("follower_count") in [None, ""]:
        maybe = _first_int_from_user_source(source, ("follower_count", "followers", "followerCount", "fans_cnt", "fans_count"))
        if maybe is not None:
            user["follower_count"] = maybe
    if user.get("like_count") in [None, ""]:
        maybe = _first_int_from_user_source(source, ("like_count", "total_favorited", "total_favorited_count", "like_cnt"))
        if maybe is not None:
            user["like_count"] = maybe
            user["total_favorited"] = maybe
    if user.get("total_favorited") in [None, ""]:
        maybe = _first_int_from_user_source(source, ("total_favorited", "total_favorited_count", "like_count", "like_cnt"))
        if maybe is not None:
            user["total_favorited"] = maybe
            if user.get("like_count") in [None, ""]:
                user["like_count"] = maybe
    if user.get("aweme_count") in [None, ""]:
        maybe = _first_int_from_user_source(source, ("aweme_count", "video_count", "awemeCount", "publish_cnt", "publish_count"))
        if maybe is not None:
            user["aweme_count"] = maybe
    if user.get("following_count") in [None, ""]:
        maybe = _first_int_from_user_source(source, ("following_count", "follow_count", "following", "followingCount"))
        if maybe is not None:
            user["following_count"] = maybe
    return user


def row_to_target_set(row: Any) -> dict[str, Any]:
    target_set = dict(row)
    target_set["deleted"] = bool(target_set.get("deleted_at"))
    target_set["filters"] = load_json(target_set.pop("filters_json", "{}"), {})
    target_set["video_strategy"] = load_json(target_set.pop("video_strategy_json", "{}"), {})
    return target_set


def row_to_target_video(row: Any) -> dict[str, Any]:
    video = dict(row)
    video["deleted"] = bool(video.get("deleted_at"))
    video["desc"] = video.pop("description", video.get("desc", ""))
    video["selected"] = bool(video.get("selected"))
    video["is_top"] = bool(video.get("is_top"))
    video["source_json"] = load_json(video.get("source_json"), {})
    video["metrics"] = load_json(video.pop("metrics_json", "{}"), {})
    video["analysis_result"] = load_json(video.pop("analysis_result_json", "{}"), {})
    return video


def row_to_target_task(row: Any) -> dict[str, Any]:
    task = dict(row)
    task["deleted"] = bool(task.get("deleted_at"))
    task["result"] = load_json(task.pop("result_json", "{}"), {})
    return task


def row_to_target_video_comment_page(row: Any) -> dict[str, Any]:
    page = dict(row)
    page["request"] = load_json(page.pop("request_json", "{}"), {})
    page["items"] = load_json(page.pop("items_json", "[]"), [])
    page["raw"] = load_json(page.pop("raw_json", "{}"), {})
    page["pagination"] = load_json(page.pop("pagination_json", "{}"), {})
    page["normalized"] = load_json(page.pop("normalized_json", "{}"), {})
    return page


def row_to_target_comment(row: Any) -> dict[str, Any]:
    comment = dict(row)
    comment["deleted"] = bool(comment.get("deleted_at"))
    comment["is_pinned"] = bool(comment.get("is_pinned"))
    comment["is_author"] = bool(comment.get("is_author"))
    comment["source_json"] = load_json(comment.get("source_json"), {})
    return comment


def row_to_interaction_insights(row: Any) -> dict[str, Any]:
    insights = dict(row)
    insights["deleted"] = bool(insights.get("deleted_at"))
    for key, fallback in {
        "keyword_counts_json": {},
        "symbol_counts_json": {},
        "emotion_profile_json": {},
        "creator_reply_tactics_json": {},
        "top_comments_json": [],
        "pinned_comments_json": [],
        "author_replies_json": [],
        "raw_ai_json": {},
    }.items():
        public_key = key.removesuffix("_json")
        insights[public_key] = load_json(insights.pop(key, "{}"), fallback)
    emotion_profile = insights.get("emotion_profile") if isinstance(insights.get("emotion_profile"), dict) else {}
    insights["genre"] = str(emotion_profile.get("genre") or "")
    return insights


def _comment_user(comment: dict[str, Any]) -> dict[str, Any]:
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    return {
        "user_id": str(user.get("uid") or user.get("id") or user.get("user_id") or comment.get("user_id") or ""),
        "sec_uid": str(user.get("sec_uid") or user.get("secUid") or comment.get("sec_uid") or ""),
        "unique_id": str(user.get("unique_id") or user.get("short_id") or comment.get("unique_id") or ""),
        "nickname": str(user.get("nickname") or comment.get("nickname") or ""),
    }


def normalize_comment(
    video_id: str,
    aweme_id: str,
    comment: dict[str, Any],
    *,
    rank_index: int = 0,
    parent_comment_id: str = "",
    level: int = 1,
    author_user_ids: set[str] | None = None,
) -> dict[str, Any]:
    user = _comment_user(comment)
    comment_id = str(
        comment.get("cid")
        or comment.get("comment_id")
        or comment.get("id")
        or comment.get("reply_id")
        or f"{video_id}:{parent_comment_id or 'root'}:{rank_index}"
    )
    resolved_parent_comment_id = str(
        parent_comment_id
        or comment.get("parent_comment_id")
        or comment.get("reply_to_reply_id")
        or comment.get("reply_comment_id")
        or ""
    )
    resolved_level = int(comment.get("level") or level or (2 if resolved_parent_comment_id else 1))
    text = str(comment.get("text") or comment.get("content") or comment.get("reply_comment") or "")
    sticky = comment.get("stick_position") or comment.get("is_pinned") or comment.get("is_top")
    author_ids = author_user_ids or set()
    is_author = bool(
        comment.get("is_author")
        or comment.get("is_creator")
        or (user["user_id"] and user["user_id"] in author_ids)
        or (user["sec_uid"] and user["sec_uid"] in author_ids)
    )
    return {
        "id": f"{video_id}:{comment_id}",
        "video_id": video_id,
        "aweme_id": str(comment.get("aweme_id") or aweme_id or ""),
        "comment_id": comment_id,
        "parent_comment_id": resolved_parent_comment_id,
        "reply_to_comment_id": str(comment.get("reply_to_reply_id") or comment.get("reply_comment_id") or resolved_parent_comment_id or ""),
        "user_id": user["user_id"],
        "sec_uid": user["sec_uid"],
        "unique_id": user["unique_id"],
        "nickname": user["nickname"],
        "text": text,
        "digg_count": to_int(comment.get("digg_count") or comment.get("like_count")),
        "reply_count": to_int(comment.get("reply_comment_total") or comment.get("reply_count")),
        "create_time": to_int(comment.get("create_time")),
        "is_pinned": bool(sticky not in (None, "", 0, "0", False)),
        "is_author": is_author,
        "rank_index": rank_index,
        "level": resolved_level,
        "source_json": comment,
    }


def _compact_comment(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "comment_id": comment.get("comment_id"),
        "parent_comment_id": comment.get("parent_comment_id"),
        "nickname": comment.get("nickname"),
        "text": comment.get("text"),
        "digg_count": comment.get("digg_count"),
        "reply_count": comment.get("reply_count"),
        "create_time": comment.get("create_time"),
        "is_pinned": bool(comment.get("is_pinned")),
        "is_author": bool(comment.get("is_author")),
        "rank_index": comment.get("rank_index"),
        "level": comment.get("level"),
    }


def _dedupe_comments(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for comment in comments:
        identities = []
        raw_identity = str(comment.get("comment_id") or comment.get("cid") or comment.get("id") or "").strip()
        if raw_identity:
            identities.append(f"id:{raw_identity}")
        text = re.sub(r"\s+", "", str(comment.get("text") or ""))
        author = re.sub(
            r"\s+",
            "",
            str(
                comment.get("user_id")
                or comment.get("sec_uid")
                or comment.get("unique_id")
                or comment.get("nickname")
                or ""
            ),
        )
        if text and author:
            identities.append(f"author_text:{author}:{text[:200]}")
        if not identities and text:
            identities.append(f"text:{text[:200]}")
        if any(identity in seen for identity in identities):
            continue
        seen.update(identities)
        unique.append(comment)
    return unique


def _genre_keyword_set(genre: str = "") -> tuple[str, ...]:
    normalized_genre = normalize_genre(genre)
    genre_keywords = GENRE_INTERACTION_KEYWORDS.get(normalized_genre, ())
    return tuple(dict.fromkeys((*GENERIC_INTERACTION_KEYWORDS, *genre_keywords)))


def _genre_motivation_buckets(genre: str = "") -> dict[str, tuple[str, ...]]:
    normalized_genre = normalize_genre(genre)
    buckets = {name: tuple(keywords) for name, keywords in MOTIVATION_BUCKETS.items()}
    buckets.update(GENRE_MOTIVATION_BUCKETS.get(normalized_genre, {}))
    return buckets


def _genre_retention_tactics(genre: str = "") -> dict[str, tuple[str, ...]]:
    normalized_genre = normalize_genre(genre)
    tactics = {name: tuple(keywords) for name, keywords in RETENTION_TACTIC_KEYWORDS.items()}
    tactics.update(GENRE_RETENTION_TACTIC_KEYWORDS.get(normalized_genre, {}))
    return tactics


def _count_keywords(texts: list[str], *, genre: str = "") -> dict[str, int]:
    counts: Counter[str] = Counter()
    keywords = _genre_keyword_set(genre)
    for text in texts:
        compact = re.sub(r"\s+", "", text)
        for keyword in keywords:
            count = compact.count(keyword)
            if count:
                counts[keyword] += count
    return dict(counts.most_common(40))


def _count_symbols(texts: list[str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for text in texts:
        for symbol in re.findall(r"[#@\uFF01!\uFF1F%s\u2764\u2665\U0001F495\U0001F496\u2728\U0001F64F]+", text):
            counts[symbol] += 1
    return dict(counts.most_common(30))


def _emotion_profile(texts: list[str], *, genre: str = "") -> dict[str, Any]:
    bucket_counts: dict[str, int] = {}
    total_hits = 0
    normalized_genre = normalize_genre(genre)
    buckets = _genre_motivation_buckets(normalized_genre)
    for name, keywords in buckets.items():
        count = 0
        for text in texts:
            compact = re.sub(r"\s+", "", text)
            if any(keyword in compact for keyword in keywords):
                count += 1
        bucket_counts[name] = count
        total_hits += count
    dominant = max(bucket_counts, key=bucket_counts.get) if bucket_counts else ""
    generic_counts = {key: bucket_counts.get(key, 0) for key in MOTIVATION_BUCKETS}
    genre_counts = {key: value for key, value in bucket_counts.items() if key not in MOTIVATION_BUCKETS}
    return {
        "buckets": bucket_counts,
        "dominant": dominant if bucket_counts.get(dominant, 0) else "",
        "motivation_buckets": generic_counts,
        "dominant_motivation": max(generic_counts, key=generic_counts.get) if generic_counts and max(generic_counts.values()) else "",
        "genre": normalized_genre,
        "genre_plugin_buckets": genre_counts,
        "total_labeled_comments": total_hits,
    }


def _creator_reply_tactics(comments: list[dict[str, Any]], *, genre: str = "") -> dict[str, Any]:
    author_replies = [comment for comment in comments if comment.get("is_author")]
    tactic_counts: dict[str, int] = {}
    examples: list[dict[str, Any]] = []
    tactics = _genre_retention_tactics(genre)
    for comment in author_replies:
        text = re.sub(r"\s+", "", str(comment.get("text") or ""))
        matched = []
        for tactic, keywords in tactics.items():
            if any(keyword in text for keyword in keywords):
                tactic_counts[tactic] = tactic_counts.get(tactic, 0) + 1
                matched.append(tactic)
        if matched and len(examples) < 12:
            examples.append({**_compact_comment(comment), "matched_tactics": matched})
    return {
        "counts": tactic_counts,
        "examples": examples,
        "author_reply_count": len(author_replies),
    }


def build_interaction_insights(
    video_id: str,
    aweme_id: str,
    comments: list[dict[str, Any]],
    raw_ai: dict[str, Any] | None = None,
    genre: str = "",
) -> dict[str, Any]:
    comments = _dedupe_comments(comments)
    fan_comments = [comment for comment in comments if not comment.get("is_author")]
    texts = [str(comment.get("text") or "") for comment in fan_comments if comment.get("text")]
    normalized_genre = normalize_genre(genre)
    top_comments = sorted(
        [comment for comment in comments if int(comment.get("level") or 1) == 1],
        key=lambda item: (to_int(item.get("digg_count")) or 0, to_int(item.get("reply_count")) or 0),
        reverse=True,
    )[:20]
    pinned_comments = [comment for comment in comments if comment.get("is_pinned")][:20]
    author_replies = [comment for comment in comments if comment.get("is_author")][:30]
    return {
        "video_id": video_id,
        "aweme_id": aweme_id,
        "genre": normalized_genre,
        "comment_count_saved": len([comment for comment in comments if int(comment.get("level") or 1) == 1]),
        "reply_count_saved": len([comment for comment in comments if int(comment.get("level") or 1) > 1]),
        "keyword_counts": _count_keywords(texts, genre=normalized_genre),
        "symbol_counts": _count_symbols(texts),
        "emotion_profile": _emotion_profile(texts, genre=normalized_genre),
        "creator_reply_tactics": _creator_reply_tactics(comments, genre=normalized_genre),
        "top_comments": [_compact_comment(comment) for comment in top_comments],
        "pinned_comments": [_compact_comment(comment) for comment in pinned_comments],
        "author_replies": [_compact_comment(comment) for comment in author_replies],
        "raw_ai": raw_ai or {},
    }


def upsert_target_user(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    current = now()
    user_id = str(user_id or payload.get("uid") or payload.get("user_id") or "").strip()
    payload_sec_user_id = str(payload.get("sec_user_id") or payload.get("sec_uid") or "").strip()
    payload_unique_id = str(payload.get("unique_id") or "").strip()
    existing = get_target_user_by_identifiers(sec_user_id=payload_sec_user_id) if payload_sec_user_id else None
    if not existing:
        existing = get_target_user(user_id) if user_id else None
    if not existing:
        existing = get_target_user_by_identifiers(
            user_id=user_id,
            unique_id=payload_unique_id if not payload_sec_user_id else "",
        )
    if existing:
        user_id = str(existing.get("id") or user_id)
    if not user_id:
        user_id = payload_sec_user_id or payload_unique_id
    if not user_id:
        raise ValueError("Target user id is required")
    existing = existing or {}
    existing_source = existing.get("source_json") if isinstance(existing.get("source_json"), dict) else {}
    incoming_source = payload.get("source_json") if isinstance(payload.get("source_json"), dict) else {}
    merged_source = {**existing_source, **incoming_source} if existing_source or incoming_source else payload.get("source_json") or {}

    def pick_text(key: str, *aliases: str, source_keys: tuple[str, ...] = (), default: str = "") -> str:
        for candidate in (key, *aliases):
            value = payload.get(candidate)
            if value not in [None, ""]:
                return str(value)
        for candidate in (key, *aliases):
            value = existing.get(candidate)
            if value not in [None, ""]:
                return str(value)
        if source_keys:
            value = _first_text_from_user_source(merged_source, source_keys)
            if value:
                return value
        return default

    def pick_int(key: str, *aliases: str, source_keys: tuple[str, ...] = ()) -> int | None:
        candidates = (key, *aliases)
        incoming = None
        for candidate in candidates:
            value = payload.get(candidate)
            if value not in [None, ""]:
                incoming = to_int(value)
                if incoming is not None:
                    break
        current_value = None
        for candidate in candidates:
            if existing.get(candidate) not in [None, ""]:
                current_value = to_int(existing.get(candidate))
                if current_value is not None:
                    break
        source_value = _first_int_from_user_source(merged_source, source_keys) if source_keys else None
        if incoming and incoming > 0:
            return incoming
        if current_value and current_value > 0:
            return current_value
        if source_value and source_value > 0:
            return source_value
        for value in (incoming, current_value, source_value):
            if value is not None:
                return value
        return None

    def pick_bool(key: str, *, default: bool = False) -> bool:
        if key in payload:
            return bool(payload.get(key))
        if key in existing:
            return bool(existing.get(key))
        return default

    resolved_recent_update_at = max(
        to_int(payload.get("recent_update_at") or payload.get("last_post_at") or payload.get("searched_at")) or 0,
        to_int(existing.get("recent_update_at")) or 0,
        to_int(existing.get("searched_at")) or 0,
    ) or current
    resolved_last_post_at = max(
        to_int(payload.get("last_post_at") or payload.get("recent_update_at") or payload.get("searched_at")) or 0,
        to_int(existing.get("last_post_at")) or 0,
        to_int(existing.get("searched_at")) or 0,
        resolved_recent_update_at,
    ) or resolved_recent_update_at
    resolved_status = str(payload.get("status") or "").strip() or str(existing.get("status") or "candidate")
    if resolved_status == "candidate" and str(existing.get("status") or "").strip() and str(existing.get("status")) != "candidate":
        resolved_status = str(existing.get("status"))
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_users (
                id, keyword, sec_user_id, unique_id, nickname, follower_count, like_count,
                recent_update_at, verified, status, source_json, created_at, updated_at,
                avatar_url, signature, ip_location, total_favorited, aweme_count, following_count, is_private, last_post_at, searched_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(id) DO UPDATE SET
                keyword = excluded.keyword,
                sec_user_id = excluded.sec_user_id,
                unique_id = excluded.unique_id,
                nickname = excluded.nickname,
                follower_count = excluded.follower_count,
                like_count = excluded.like_count,
                recent_update_at = excluded.recent_update_at,
                verified = excluded.verified,
                status = excluded.status,
                source_json = excluded.source_json,
                avatar_url = excluded.avatar_url,
                signature = excluded.signature,
                ip_location = excluded.ip_location,
                total_favorited = excluded.total_favorited,
                aweme_count = excluded.aweme_count,
                following_count = excluded.following_count,
                is_private = excluded.is_private,
                last_post_at = excluded.last_post_at,
                searched_at = excluded.searched_at,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                pick_text('keyword'),
                pick_text('sec_user_id'),
                pick_text('unique_id'),
                pick_text('nickname'),
                pick_int('follower_count', source_keys=("follower_count", "followers", "followerCount", "fans_cnt", "fans_count")),
                pick_int('like_count', 'total_favorited', source_keys=("like_count", "total_favorited", "total_favorited_count", "like_cnt")),
                resolved_recent_update_at,
                1 if pick_bool('verified') else 0,
                resolved_status,
                json.dumps(merged_source or payload, ensure_ascii=False),
                current,
                current,
                pick_text('avatar_url') or pick_text('avatar'),
                pick_text('signature', source_keys=("signature", "desc", "intro", "bio")),
                pick_text('ip_location', 'ipLocation', 'location', source_keys=("ip_location", "ipLocation", "location")),
                pick_int('total_favorited', 'like_count', source_keys=("total_favorited", "total_favorited_count", "like_count", "like_cnt")),
                pick_int('aweme_count', source_keys=("aweme_count", "video_count", "awemeCount", "publish_cnt", "publish_count")),
                pick_int('following_count', 'follow_count', source_keys=("following_count", "follow_count", "following", "followingCount")),
                1 if pick_bool('is_private') else 0,
                resolved_last_post_at,
                to_int(payload.get('searched_at')) or to_int(existing.get('searched_at')) or current,
            ),
        )
    return get_target_user(user_id) or {}


def get_target_user(user_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tiktok_target_users WHERE id = %s", (user_id,)).fetchone()
    return row_to_target_user(row) if row else None


def get_target_user_by_identifiers(
    *,
    user_id: str = "",
    sec_user_id: str = "",
    unique_id: str = "",
) -> dict[str, Any] | None:
    init_db()
    conditions = []
    values: list[Any] = []
    if user_id:
        conditions.append("id = %s")
        values.append(user_id)
    if sec_user_id:
        conditions.append("sec_user_id = %s")
        values.append(sec_user_id)
    if unique_id:
        conditions.append("unique_id = %s")
        values.append(unique_id)
    if not conditions:
        return None
    where = " OR ".join(conditions)
    query = f"SELECT * FROM tiktok_target_users WHERE {where} ORDER BY updated_at DESC LIMIT 1"
    with connect() as connection:
        row = connection.execute(query, values).fetchone()
    return row_to_target_user(row) if row else None


def get_target_video_comment_page_by_cache_key(cache_key: str) -> dict[str, Any] | None:
    init_db()
    with cache_connection() as connection:
        row = connection.execute(
            "SELECT * FROM tiktok_target_video_comment_pages WHERE cache_key = %s",
            (cache_key,),
        ).fetchone()
    return row_to_target_video_comment_page(row) if row else None


def get_target_video_comment_page(
    *,
    source: str,
    video_id: str,
    aweme_id: str = "",
    item_id: str = "",
    comment_id: str = "",
    page_kind: str = "comments",
    cursor: int = 0,
    count: int = 20,
) -> dict[str, Any] | None:
    cache_key = build_video_comment_page_cache_key(
        source=source,
        video_id=video_id,
        aweme_id=aweme_id,
        item_id=item_id,
        comment_id=comment_id,
        page_kind=page_kind,
        cursor=cursor,
        count=count,
    )
    return get_target_video_comment_page_by_cache_key(cache_key)


def upsert_target_video_comment_page(
    *,
    source: str,
    video_id: str,
    aweme_id: str = "",
    item_id: str = "",
    comment_id: str = "",
    page_kind: str = "comments",
    cursor: int = 0,
    count: int = 20,
    request: dict[str, Any] | None = None,
    items: list[dict[str, Any]] | None = None,
    raw: dict[str, Any] | None = None,
    pagination: dict[str, Any] | None = None,
    normalized: dict[str, Any] | None = None,
    fetched_at: int | None = None,
) -> dict[str, Any]:
    init_db()
    current = now()
    request = request or {}
    items = items or []
    raw = raw or {}
    pagination = pagination or {}
    normalized = normalized or {}
    cache_key = build_video_comment_page_cache_key(
        source=source,
        video_id=video_id,
        aweme_id=aweme_id,
        item_id=item_id,
        comment_id=comment_id,
        page_kind=page_kind,
        cursor=cursor,
        count=count,
    )
    with cache_connection() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_video_comment_pages (
                id, cache_key, source, video_id, aweme_id, item_id, comment_id, page_kind,
                cursor, count, request_json, items_json, raw_json, pagination_json,
                normalized_json, fetched_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(cache_key) DO UPDATE SET
                source = excluded.source,
                video_id = excluded.video_id,
                aweme_id = excluded.aweme_id,
                item_id = excluded.item_id,
                comment_id = excluded.comment_id,
                page_kind = excluded.page_kind,
                cursor = excluded.cursor,
                count = excluded.count,
                request_json = excluded.request_json,
                items_json = excluded.items_json,
                raw_json = excluded.raw_json,
                pagination_json = excluded.pagination_json,
                normalized_json = excluded.normalized_json,
                fetched_at = excluded.fetched_at,
                updated_at = excluded.updated_at
            """,
            (
                cache_key,
                cache_key,
                source,
                video_id,
                aweme_id,
                item_id,
                comment_id,
                page_kind,
                int(cursor or 0),
                int(count or 0),
                json.dumps(request, ensure_ascii=False),
                json.dumps(items, ensure_ascii=False),
                json.dumps(raw, ensure_ascii=False),
                json.dumps(pagination, ensure_ascii=False),
                json.dumps(normalized, ensure_ascii=False),
                fetched_at or current,
                current,
                current,
            ),
        )
    return get_target_video_comment_page_by_cache_key(cache_key) or {}


def list_target_users(status: str | None = None, limit: int = 200, set_id: str | None = None) -> list[dict[str, Any]]:
    init_db()
    values: list[Any] = []
    if set_id:
        with connect() as connection:
            link_rows = connection.execute(
            "SELECT user_id FROM tiktok_target_set_users WHERE set_id = %s AND deleted_at IS NULL ORDER BY created_at DESC LIMIT %s",
                (set_id, limit),
            ).fetchall()
        user_ids = [str(row["user_id"]) for row in link_rows]
        if not user_ids:
            return []
        id_placeholders = placeholders(len(user_ids))
        query = f"SELECT * FROM tiktok_target_users WHERE id IN ({id_placeholders})"
        values.extend(user_ids)
        if status:
            query += " AND status = %s"
            values.append(status)
        query += " ORDER BY updated_at DESC LIMIT %s"
        values.append(limit)
        with connect() as connection:
            rows = connection.execute(query, values).fetchall()
        users = [row_to_target_user(row) for row in rows]
        seen = set()
        unique_users = []
        for user in users:
            identity = str(user.get("sec_user_id") or "").strip() or f'id:{user["id"]}'
            if identity in seen:
                continue
            seen.add(identity)
            unique_users.append(user)
        return unique_users

    query = "SELECT * FROM tiktok_target_users"
    if status:
        query += " WHERE status = %s"
        values.append(status)
    query += " ORDER BY updated_at DESC LIMIT %s"
    values.append(limit)
    with connect() as connection:
        rows = connection.execute(query, values).fetchall()
    return [row_to_target_user(row) for row in rows]


def list_target_set_sec_user_ids(set_id: str) -> set[str]:
    init_db()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT target_user.sec_user_id
            FROM tiktok_target_set_users AS set_user
            JOIN tiktok_target_users AS target_user ON target_user.id = set_user.user_id
            WHERE set_user.set_id = %s
              AND set_user.deleted_at IS NULL
              AND target_user.sec_user_id != ''
            """,
            (set_id,),
        ).fetchall()
    return {str(row["sec_user_id"]).strip() for row in rows if str(row["sec_user_id"]).strip()}


def create_target_set(
    set_id: str,
    name: str,
    note: str = '',
    *,
    keyword: str = '',
    filters: dict[str, Any] | None = None,
    video_strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_sets (
                id, name, note, status, created_at, updated_at, keyword, filters_json, video_strategy_json
            )
            VALUES (%s, %s, %s, 'draft', %s, %s, %s, %s, %s)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                note = excluded.note,
                keyword = excluded.keyword,
                filters_json = excluded.filters_json,
                video_strategy_json = excluded.video_strategy_json,
                status = CASE WHEN tiktok_target_sets.status = 'deleted' THEN excluded.status ELSE tiktok_target_sets.status END,
                deleted_at = NULL,
                updated_at = excluded.updated_at
            """,
            (
                set_id,
                name,
                note,
                current,
                current,
                keyword,
                json.dumps(filters or {}, ensure_ascii=False),
                json.dumps(video_strategy or {}, ensure_ascii=False),
            ),
        )
    return get_target_set(set_id) or {}


def get_target_set(set_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tiktok_target_sets WHERE id = %s AND deleted_at IS NULL", (set_id,)).fetchone()
    return row_to_target_set(row) if row else None


def update_target_set(
    set_id: str,
    *,
    name: str | None = None,
    note: str | None = None,
    keyword: str | None = None,
    filters: dict[str, Any] | None = None,
    video_strategy: dict[str, Any] | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    init_db()
    current = now()
    updates: dict[str, Any] = {"updated_at": current}
    if name is not None:
        updates["name"] = name
    if note is not None:
        updates["note"] = note
    if keyword is not None:
        updates["keyword"] = keyword
    if filters is not None:
        updates["filters_json"] = json.dumps(filters, ensure_ascii=False)
    if video_strategy is not None:
        updates["video_strategy_json"] = json.dumps(video_strategy, ensure_ascii=False)
    if status is not None:
        updates["status"] = status
    assignments = ", ".join(f"{key} = %s" for key in updates)
    values = list(updates.values()) + [set_id]
    with connect() as connection:
        cursor = connection.execute(f"UPDATE tiktok_target_sets SET {assignments} WHERE id = %s", values)
    if cursor.rowcount == 0:
        return None
    return get_target_set(set_id)


def delete_target_set(set_id: str) -> bool:
    init_db()
    deleted_at = now()
    with connect() as connection:
        connection.execute(
            "UPDATE tiktok_target_set_users SET deleted_at = %s WHERE set_id = %s AND deleted_at IS NULL",
            (deleted_at, set_id),
        )
        connection.execute(
            "UPDATE tiktok_target_tasks SET deleted_at = %s, status = 'deleted', updated_at = %s WHERE set_id = %s AND deleted_at IS NULL",
            (deleted_at, deleted_at, set_id),
        )
        cursor = connection.execute(
            "UPDATE tiktok_target_sets SET deleted_at = %s, status = 'deleted', updated_at = %s WHERE id = %s AND deleted_at IS NULL",
            (deleted_at, deleted_at, set_id),
        )
    return cursor.rowcount > 0


def list_target_sets(limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    with connect() as connection:
        set_rows = connection.execute(
            "SELECT * FROM tiktok_target_sets WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    if not set_rows:
        return []

    set_ids = [str(row["id"]) for row in set_rows]
    id_placeholders = placeholders(len(set_ids))
    with connect() as connection:
        user_count_rows = connection.execute(
            f"""
            SELECT
                set_user.set_id,
                COUNT(DISTINCT COALESCE(NULLIF(target_user.sec_user_id, ''), target_user.id)) AS user_count
            FROM tiktok_target_set_users AS set_user
            JOIN tiktok_target_users AS target_user ON target_user.id = set_user.user_id
            WHERE set_user.set_id IN ({id_placeholders})
              AND set_user.deleted_at IS NULL
            GROUP BY set_user.set_id
            """,
            set_ids,
        ).fetchall()
        video_count_rows = connection.execute(
            f"""
            SELECT
                set_user.set_id,
                COUNT(DISTINCT video.id) AS video_count,
                COUNT(DISTINCT CASE WHEN video.analysis_status = 'done' THEN video.id END) AS analyzed_count
            FROM tiktok_target_set_users AS set_user
            JOIN tiktok_target_users AS target_user ON target_user.id = set_user.user_id
            LEFT JOIN tiktok_target_videos AS video
              ON video.user_id = target_user.id
             AND video.deleted_at IS NULL
            WHERE set_user.set_id IN ({id_placeholders})
              AND set_user.deleted_at IS NULL
            GROUP BY set_user.set_id
            """,
            set_ids,
        ).fetchall()

    user_counts = {str(row["set_id"]): int(row["user_count"] or 0) for row in user_count_rows}
    video_counts = {
        str(row["set_id"]): {
            "video_count": int(row["video_count"] or 0),
            "analyzed_count": int(row["analyzed_count"] or 0),
        }
        for row in video_count_rows
    }
    result = []
    for row in set_rows:
        item = dict(row)
        set_id = str(item["id"])
        counts = video_counts.get(set_id, {})
        item["user_count"] = user_counts.get(set_id, 0)
        item["video_count"] = counts.get("video_count", 0)
        item["analyzed_count"] = counts.get("analyzed_count", 0)
        result.append(row_to_target_set(item))
    return result


def get_target_set_detail(set_id: str) -> dict[str, Any] | None:
    target_set = get_target_set(set_id)
    if not target_set:
        return None
    target_set["users"] = list_target_users(set_id=set_id, limit=500)
    target_set["videos"] = list_target_videos(set_id=set_id, limit=1000)
    target_set["tasks"] = list_target_tasks(set_id=set_id, limit=1000)
    return target_set


def add_user_to_target_set(set_id: str, user_id: str) -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_set_users (id, set_id, user_id, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(set_id, user_id) DO UPDATE SET deleted_at = NULL
            """,
            (f'{set_id}:{user_id}', set_id, user_id, current),
        )
    return {"set_id": set_id, "user_id": user_id}


def remove_user_from_target_set(set_id: str, user_id: str) -> bool:
    init_db()
    current = now()
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE tiktok_target_set_users SET deleted_at = %s WHERE set_id = %s AND user_id = %s AND deleted_at IS NULL",
            (current, set_id, user_id),
        )
    return cursor.rowcount > 0


def create_target_video(video_id: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    current = now()
    incoming_aweme_id = str(payload.get("aweme_id") or video_id or "").strip()
    existing = get_target_video(video_id) or (resolve_target_video(incoming_aweme_id) if incoming_aweme_id else None) or {}
    if existing:
        video_id = str(existing.get("id") or video_id)
    existing_source = existing.get("source_json") if isinstance(existing.get("source_json"), dict) else {}
    incoming_source = payload.get("source_json") if isinstance(payload.get("source_json"), dict) else {}
    merged_source = {**existing_source, **incoming_source} if existing_source or incoming_source else payload.get("source_json") or payload
    metrics = derive_video_metrics(payload)
    if metrics["play_count"] <= 0:
        metrics["play_count"] = first_positive_int(
            payload.get("play_count"),
            payload.get("source_json", {}).get("statistics", {}).get("play_count") if isinstance(payload.get("source_json"), dict) else None,
            payload.get("source_json", {}).get("statistics", {}).get("view_count") if isinstance(payload.get("source_json"), dict) else None,
            payload.get("raw", {}).get("statistics", {}).get("play_count") if isinstance(payload.get("raw"), dict) else None,
            payload.get("raw", {}).get("statistics", {}).get("view_count") if isinstance(payload.get("raw"), dict) else None,
            existing.get("play_count"),
        )
        metrics["engagement_rate"] = round(metrics["engagement_score"] / metrics["play_count"], 6) if metrics["play_count"] else None
    for metric_key in ("digg_count", "comment_count", "share_count", "collect_count"):
        existing_value = to_int(existing.get(metric_key)) if existing.get(metric_key) not in [None, ""] else 0
        if metrics[metric_key] <= 0 and existing_value > 0:
            metrics[metric_key] = existing_value
    metrics["metrics_json"] = {**(existing.get("metrics") if isinstance(existing.get("metrics"), dict) else {}), **metrics["metrics_json"]}
    resolved_desc = str(payload.get("desc") or existing.get("desc") or "")
    resolved_cover_url = str(payload.get("cover_url") or existing.get("cover_url") or "")
    resolved_play_url = str(payload.get("play_url") or existing.get("play_url") or "")
    resolved_download_url = str(payload.get("download_url") or existing.get("download_url") or "")
    resolved_set_id = str(existing.get("set_id") or "")
    resolved_analysis_status = str(payload.get("analysis_status") or existing.get("analysis_status") or "none")
    resolved_analysis_task_id = str(payload.get("analysis_task_id") or existing.get("analysis_task_id") or "")
    resolved_is_top = bool(payload.get("is_top")) or bool(existing.get("is_top"))
    resolved_selected = bool(payload.get("selected")) or bool(existing.get("selected"))
    resolved_aweme_id = str(payload.get("aweme_id") or existing.get("aweme_id") or "")
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_videos AS target (
                id, user_id, aweme_id, description, cover_url, play_url, download_url, source_json,
                selected, created_at, updated_at, set_id, create_time, digg_count, comment_count,
                share_count, collect_count, play_count, publish_hour, publish_weekday, publish_date,
                publish_hour_bucket, like_collect_ratio, collect_like_ratio, comment_like_ratio,
                share_like_ratio, engagement_score, engagement_rate, metrics_json, is_top,
                selection_strategy, analysis_status, analysis_task_id, analysis_result_json, analyzed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(id) DO UPDATE SET
                user_id = excluded.user_id,
                aweme_id = excluded.aweme_id,
                description = excluded.description,
                cover_url = excluded.cover_url,
                play_url = excluded.play_url,
                download_url = excluded.download_url,
                source_json = excluded.source_json,
                updated_at = excluded.updated_at,
                selected = excluded.selected,
                set_id = excluded.set_id,
                create_time = excluded.create_time,
                digg_count = excluded.digg_count,
                comment_count = excluded.comment_count,
                share_count = excluded.share_count,
                collect_count = excluded.collect_count,
                play_count = excluded.play_count,
                publish_hour = excluded.publish_hour,
                publish_weekday = excluded.publish_weekday,
                publish_date = excluded.publish_date,
                publish_hour_bucket = excluded.publish_hour_bucket,
                like_collect_ratio = excluded.like_collect_ratio,
                collect_like_ratio = excluded.collect_like_ratio,
                comment_like_ratio = excluded.comment_like_ratio,
                share_like_ratio = excluded.share_like_ratio,
                engagement_score = excluded.engagement_score,
                engagement_rate = excluded.engagement_rate,
                metrics_json = excluded.metrics_json,
                is_top = excluded.is_top,
                selection_strategy = COALESCE(NULLIF(excluded.selection_strategy, ''), target.selection_strategy),
                analysis_status = COALESCE(NULLIF(excluded.analysis_status, ''), target.analysis_status),
                analysis_task_id = COALESCE(NULLIF(excluded.analysis_task_id, ''), target.analysis_task_id),
                analysis_result_json = CASE
                    WHEN excluded.analysis_result_json IS NOT NULL AND excluded.analysis_result_json != '{}' THEN excluded.analysis_result_json
                    ELSE target.analysis_result_json
                END,
                analyzed_at = COALESCE(excluded.analyzed_at, target.analyzed_at),
                deleted_at = NULL
            """,
            (
                video_id,
                user_id,
                resolved_aweme_id,
                resolved_desc,
                resolved_cover_url,
                resolved_play_url,
                resolved_download_url,
                json.dumps(merged_source or payload, ensure_ascii=False),
                1 if resolved_selected else 0,
                current,
                current,
                resolved_set_id,
                payload.get('create_time') if payload.get('create_time') not in [None, ""] else existing.get('create_time'),
                metrics["digg_count"],
                metrics["comment_count"],
                metrics["share_count"],
                metrics["collect_count"],
                metrics["play_count"],
                metrics["publish_hour"],
                metrics["publish_weekday"],
                metrics["publish_date"],
                metrics["publish_hour_bucket"],
                metrics["like_collect_ratio"],
                metrics["collect_like_ratio"],
                metrics["comment_like_ratio"],
                metrics["share_like_ratio"],
                metrics["engagement_score"],
                metrics["engagement_rate"],
                json.dumps(metrics["metrics_json"], ensure_ascii=False),
                1 if resolved_is_top else 0,
                payload.get('selection_strategy', '') or existing.get('selection_strategy') or '',
                resolved_analysis_status,
                resolved_analysis_task_id,
                json.dumps(payload.get('analysis_result') or payload.get('analysis_result_json') or {}, ensure_ascii=False),
                payload.get('analyzed_at') if payload.get('analyzed_at') not in [None, ""] else existing.get('analyzed_at'),
            ),
        )
    return get_target_video(video_id) or {}


def get_target_video(video_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tiktok_target_videos WHERE id = %s AND deleted_at IS NULL", (video_id,)).fetchone()
    return row_to_target_video(row) if row else None


def resolve_target_video(video_id_or_aweme_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM tiktok_target_videos
            WHERE (id = %s OR aweme_id = %s)
              AND deleted_at IS NULL
            ORDER BY CASE WHEN id = %s THEN 0 ELSE 1 END, updated_at DESC
            LIMIT 1
            """,
            (video_id_or_aweme_id, video_id_or_aweme_id, video_id_or_aweme_id),
        ).fetchone()
    return row_to_target_video(row) if row else None


def list_target_videos(
    *,
    set_id: str | None = None,
    user_id: str | None = None,
    selected: bool | None = None,
    analysis_status: str | None = None,
    limit: int | None = 500,
) -> list[dict[str, Any]]:
    init_db()
    joins = []
    conditions = []
    values: list[Any] = []
    if set_id:
        joins.append(
            """
            JOIN tiktok_target_set_users AS set_user
              ON set_user.user_id = video.user_id
             AND set_user.set_id = %s
             AND set_user.deleted_at IS NULL
            """
        )
        values.append(set_id)
    if user_id:
        conditions.append("video.user_id = %s")
        values.append(user_id)
    if selected is not None:
        conditions.append("video.selected = %s")
        values.append(1 if selected else 0)
    if analysis_status:
        conditions.append("video.analysis_status = %s")
        values.append(analysis_status)
    conditions.append("video.deleted_at IS NULL")
    where = f"WHERE {' AND '.join(conditions)}"
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT %s"
        values.append(limit)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT video.*
            FROM tiktok_target_videos AS video
            {' '.join(joins)}
            {where}
            ORDER BY video.selected DESC, video.digg_count DESC, video.create_time DESC
            {limit_clause}
            """,
            values,
        ).fetchall()
    return [row_to_target_video(row) for row in rows]


def replace_target_video_comments(
    video_id: str,
    comments: list[dict[str, Any]],
    *,
    status: str = "done",
    raw_ai: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    current = now()
    video = get_target_video(video_id)
    if not video:
        raise ValueError(f"Target video not found: {video_id}")
    aweme_id = str(video.get("aweme_id") or video_id)
    normalized = []
    for index, comment in enumerate(comments):
        if not isinstance(comment, dict):
            continue
        if "comment_id" in comment and "video_id" in comment:
            item = {**comment}
        else:
            item = normalize_comment(video_id, aweme_id, comment, rank_index=index)
        item["video_id"] = video_id
        item["aweme_id"] = str(item.get("aweme_id") or aweme_id)
        item["rank_index"] = int(item.get("rank_index") or index)
        item["level"] = int(item.get("level") or (2 if item.get("parent_comment_id") else 1))
        item["id"] = str(item.get("id") or f"{video_id}:{item.get('comment_id') or index}")
        normalized.append(item)

    genre = infer_interaction_genre(video, comments=normalized)
    insights = build_interaction_insights(video_id, aweme_id, normalized, raw_ai=raw_ai, genre=genre)
    with connect() as connection:
        connection.execute(
            "UPDATE tiktok_target_video_comments SET deleted_at = %s, updated_at = %s WHERE video_id = %s AND deleted_at IS NULL",
            (current, current, video_id),
        )
        for item in normalized:
            connection.execute(
                """
                INSERT INTO tiktok_target_video_comments (
                    id, video_id, aweme_id, comment_id, parent_comment_id, reply_to_comment_id,
                    user_id, sec_uid, unique_id, nickname, text, digg_count, reply_count,
                    create_time, is_pinned, is_author, rank_index, level, source_json,
                    created_at, updated_at, deleted_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(video_id, comment_id) DO UPDATE SET
                    aweme_id = excluded.aweme_id,
                    parent_comment_id = excluded.parent_comment_id,
                    reply_to_comment_id = excluded.reply_to_comment_id,
                    user_id = excluded.user_id,
                    sec_uid = excluded.sec_uid,
                    unique_id = excluded.unique_id,
                    nickname = excluded.nickname,
                    text = excluded.text,
                    digg_count = excluded.digg_count,
                    reply_count = excluded.reply_count,
                    create_time = excluded.create_time,
                    is_pinned = excluded.is_pinned,
                    is_author = excluded.is_author,
                    rank_index = excluded.rank_index,
                    level = excluded.level,
                    source_json = excluded.source_json,
                    deleted_at = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    item["id"],
                    video_id,
                    item.get("aweme_id") or aweme_id,
                    item.get("comment_id") or "",
                    item.get("parent_comment_id") or "",
                    item.get("reply_to_comment_id") or "",
                    item.get("user_id") or "",
                    item.get("sec_uid") or "",
                    item.get("unique_id") or "",
                    item.get("nickname") or "",
                    item.get("text") or "",
                    to_int(item.get("digg_count")),
                    to_int(item.get("reply_count")),
                    to_int(item.get("create_time")),
                    1 if item.get("is_pinned") else 0,
                    1 if item.get("is_author") else 0,
                    int(item.get("rank_index") or 0),
                    int(item.get("level") or 1),
                    json.dumps(item.get("source_json") or item, ensure_ascii=False),
                    current,
                    current,
                    None,
                ),
            )
        connection.execute(
            """
            INSERT INTO tiktok_target_video_interaction_insights (
                video_id, aweme_id, comment_count_saved, reply_count_saved,
                keyword_counts_json, symbol_counts_json, emotion_profile_json,
                creator_reply_tactics_json, top_comments_json, pinned_comments_json,
                author_replies_json, raw_ai_json, analyzed_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(video_id) DO UPDATE SET
                aweme_id = excluded.aweme_id,
                comment_count_saved = excluded.comment_count_saved,
                reply_count_saved = excluded.reply_count_saved,
                keyword_counts_json = excluded.keyword_counts_json,
                symbol_counts_json = excluded.symbol_counts_json,
                emotion_profile_json = excluded.emotion_profile_json,
                creator_reply_tactics_json = excluded.creator_reply_tactics_json,
                top_comments_json = excluded.top_comments_json,
                pinned_comments_json = excluded.pinned_comments_json,
                author_replies_json = excluded.author_replies_json,
                raw_ai_json = excluded.raw_ai_json,
                analyzed_at = excluded.analyzed_at,
                deleted_at = NULL,
                updated_at = excluded.updated_at
            """,
            (
                video_id,
                aweme_id,
                insights["comment_count_saved"],
                insights["reply_count_saved"],
                json.dumps(insights["keyword_counts"], ensure_ascii=False),
                json.dumps(insights["symbol_counts"], ensure_ascii=False),
                json.dumps(insights["emotion_profile"], ensure_ascii=False),
                json.dumps(insights["creator_reply_tactics"], ensure_ascii=False),
                json.dumps(insights["top_comments"], ensure_ascii=False),
                json.dumps(insights["pinned_comments"], ensure_ascii=False),
                json.dumps(insights["author_replies"], ensure_ascii=False),
                json.dumps(insights["raw_ai"], ensure_ascii=False),
                current,
                current,
                current,
            ),
        )
        connection.execute(
            """
            UPDATE tiktok_target_videos
            SET comment_snapshot_status = %s,
                comment_snapshot_at = %s,
                comment_saved_count = %s,
                reply_saved_count = %s,
                updated_at = %s
            WHERE id = %s
            """,
            (
                status,
                current,
                insights["comment_count_saved"],
                insights["reply_count_saved"],
                current,
                video_id,
            ),
        )
    return get_target_video_interaction_dataset(video_id)


def get_target_video_comments(video_id: str, *, include_replies: bool = True, limit: int = 500) -> list[dict[str, Any]]:
    init_db()
    query = "SELECT * FROM tiktok_target_video_comments WHERE video_id = %s AND deleted_at IS NULL"
    values: list[Any] = [video_id]
    if not include_replies:
        query += " AND level = 1"
    query += " ORDER BY level ASC, rank_index ASC, digg_count DESC LIMIT %s"
    values.append(limit)
    with connect() as connection:
        rows = connection.execute(query, values).fetchall()
    return [row_to_target_comment(row) for row in rows]


def get_target_video_interaction_insights(video_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM tiktok_target_video_interaction_insights WHERE video_id = %s AND deleted_at IS NULL",
            (video_id,),
        ).fetchone()
    return row_to_interaction_insights(row) if row else None


def get_target_video_interaction_dataset(video_id: str) -> dict[str, Any]:
    video = resolve_target_video(video_id)
    resolved_video_id = str(video.get("id") or video_id) if video else video_id
    comments = get_target_video_comments(resolved_video_id, include_replies=True, limit=1000)
    insights = get_target_video_interaction_insights(resolved_video_id)
    return {
        "video": video,
        "comments": comments,
        "insights": insights,
        "comment_count": len([item for item in comments if int(item.get("level") or 1) == 1]),
        "reply_count": len([item for item in comments if int(item.get("level") or 1) > 1]),
    }


def mark_target_video_comment_snapshot(video_id: str, status: str, error: str = "") -> dict[str, Any] | None:
    init_db()
    current = now()
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE tiktok_target_videos
            SET comment_snapshot_status = %s,
                comment_snapshot_at = %s,
                metrics_json = jsonb_set(COALESCE(NULLIF(metrics_json, '')::jsonb, '{}'::jsonb), '{comment_snapshot_error}', to_jsonb(%s::text), true)::text,
                updated_at = %s
            WHERE id = %s
            """,
            (status, current, error, current, video_id),
        )
    if cursor.rowcount == 0:
        return None
    return get_target_video(video_id)


def update_target_video_analysis(
    video_id: str,
    *,
    status: str,
    task_id: str = "",
    result: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any] | None:
    init_db()
    current = now()
    analyzed_at = current if status == "done" else None
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE tiktok_target_videos
            SET analysis_status = %s,
                analysis_task_id = COALESCE(NULLIF(%s, ''), analysis_task_id),
                analysis_result_json = %s,
                analyzed_at = COALESCE(%s, analyzed_at),
                updated_at = %s
            WHERE id = %s
            """,
            (
                status,
                task_id,
                json.dumps(result or {}, ensure_ascii=False),
                analyzed_at,
                current,
                video_id,
            ),
        )
    if cursor.rowcount == 0:
        return None
    return get_target_video(video_id)


def clear_target_video_analysis(video_id: str) -> dict[str, Any] | None:
    init_db()
    current = now()
    with connect() as connection:
        task_cursor = connection.execute(
            "UPDATE tiktok_target_tasks SET deleted_at = %s, status = 'deleted', updated_at = %s WHERE video_id = %s AND deleted_at IS NULL",
            (current, current, video_id),
        )
        cursor = connection.execute(
            """
            UPDATE tiktok_target_videos
            SET analysis_status = 'none',
                analysis_task_id = '',
                analysis_result_json = '{}',
                analyzed_at = NULL,
                updated_at = %s
            WHERE id = %s
            """,
            (current, video_id),
        )
        deleted_target_task_count = task_cursor.rowcount
    if cursor.rowcount == 0:
        return None
    video = get_target_video(video_id)
    if video is not None:
        video["deleted_target_task_count"] = deleted_target_task_count
    return video


def create_target_task(
    task_id: str,
    *,
    set_id: str = "",
    user_id: str = "",
    video_id: str = "",
    ai_task_id: str = "",
    status: str = "pending",
    strategy: str = "",
) -> dict[str, Any]:
    init_db()
    current = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tiktok_target_tasks (
                id, set_id, user_id, video_id, task_id, status, result_json, error,
                created_at, updated_at, strategy, retry_count, synced_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, '{}', '', %s, %s, %s, 0, %s)
            ON CONFLICT(id) DO UPDATE SET
                set_id = excluded.set_id,
                user_id = excluded.user_id,
                video_id = excluded.video_id,
                task_id = excluded.task_id,
                status = excluded.status,
                strategy = excluded.strategy,
                deleted_at = NULL,
                updated_at = excluded.updated_at,
                synced_at = excluded.synced_at
            """,
            (task_id, set_id, user_id, video_id, ai_task_id, status, current, current, strategy, current),
        )
    update_target_video_analysis(video_id, status=status, task_id=ai_task_id)
    return get_target_task(task_id) or {}


def get_target_task(target_task_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM tiktok_target_tasks WHERE id = %s AND deleted_at IS NULL", (target_task_id,)).fetchone()
    return row_to_target_task(row) if row else None


def find_target_task_for_video(video_id: str, statuses: set[str] | None = None) -> dict[str, Any] | None:
    init_db()
    values: list[Any] = [video_id]
    query = "SELECT * FROM tiktok_target_tasks WHERE video_id = %s AND deleted_at IS NULL"
    if statuses:
        status_placeholders = placeholders(len(statuses))
        query += f" AND status IN ({status_placeholders})"
        values.extend(sorted(statuses))
    query += " ORDER BY created_at DESC LIMIT 1"
    with connect() as connection:
        row = connection.execute(query, values).fetchone()
    return row_to_target_task(row) if row else None


def find_target_task_for_ai_task(ai_task_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM tiktok_target_tasks WHERE task_id = %s AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1",
            (ai_task_id,),
        ).fetchone()
    return row_to_target_task(row) if row else None


def clear_target_video_analysis_for_ai_task(ai_task_id: str) -> dict[str, Any] | None:
    init_db()
    current = now()
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM tiktok_target_tasks WHERE task_id = %s AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1",
            (ai_task_id,),
        ).fetchone()
        if not row:
            return None
        video_id = str(row["video_id"] or "")
        if not video_id:
            return None
        task_cursor = connection.execute(
            "UPDATE tiktok_target_tasks SET deleted_at = %s, status = 'deleted', updated_at = %s WHERE task_id = %s AND deleted_at IS NULL",
            (current, current, ai_task_id),
        )
        video_cursor = connection.execute(
            """
            UPDATE tiktok_target_videos
            SET analysis_status = 'none',
                analysis_task_id = '',
                analysis_result_json = '{}',
                analyzed_at = NULL,
                updated_at = %s
            WHERE id = %s
              AND (analysis_task_id = %s OR COALESCE(analysis_task_id, '') = '')
            """,
            (current, video_id, ai_task_id),
        )
        deleted_target_task_count = task_cursor.rowcount
        cleared_current_analysis = video_cursor.rowcount > 0
    video = get_target_video(video_id)
    if video is not None:
        video["deleted_target_task_count"] = deleted_target_task_count
        video["cleared_current_analysis"] = cleared_current_analysis
    return video


def list_target_tasks(
    *,
    set_id: str | None = None,
    video_id: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    init_db()
    conditions = []
    values: list[Any] = []
    if set_id:
        conditions.append("set_id = %s")
        values.append(set_id)
    if video_id:
        conditions.append("video_id = %s")
        values.append(video_id)
    if status:
        conditions.append("status = %s")
        values.append(status)
    conditions.append("deleted_at IS NULL")
    where = f"WHERE {' AND '.join(conditions)}"
    values.append(limit)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM tiktok_target_tasks {where} ORDER BY created_at DESC LIMIT %s",
            values,
        ).fetchall()
    return [row_to_target_task(row) for row in rows]


def update_target_task_from_ai_task(target_task_id: str, ai_task: dict[str, Any]) -> dict[str, Any] | None:
    init_db()
    current = now()
    ai_status = ai_task.get("status") or "pending"
    status = "failed" if ai_status in {"failed", "error"} else ai_status
    result = ai_task.get("result") or {}
    error = ai_task.get("error") or ""
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE tiktok_target_tasks
            SET status = %s,
                result_json = %s,
                error = %s,
                updated_at = %s,
                synced_at = %s
            WHERE id = %s
            """,
            (
                status,
                json.dumps(result, ensure_ascii=False),
                error,
                current,
                current,
                target_task_id,
            ),
        )
        row = connection.execute("SELECT * FROM tiktok_target_tasks WHERE id = %s AND deleted_at IS NULL", (target_task_id,)).fetchone()
    if cursor.rowcount == 0 or not row:
        return None
    target_task = row_to_target_task(row)
    update_target_video_analysis(
        target_task["video_id"],
        status=status,
        task_id=target_task.get("task_id") or "",
        result=result,
        error=error,
    )
    return target_task


def update_target_task_by_ai_task_id(ai_task: dict[str, Any]) -> dict[str, Any] | None:
    target_task = find_target_task_for_ai_task(str(ai_task.get("id") or ""))
    if not target_task:
        return None
    return update_target_task_from_ai_task(target_task["id"], ai_task)
