from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from .benchmark_metrics import average

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INDEX_DIR = ROOT_DIR / "data" / "runtime" / "benchmark_index"

PATTERN_RULES = [
    {
        "id": "private-reading",
        "name": "刷到就是私占",
        "keywords": ["私占", "刷到", "有缘", "看到就是", "命中注定"],
        "description": "强缘分暗示 + 情绪承诺 + 评论/私信引导",
    },
    {
        "id": "guardian-message",
        "name": "守护灵提醒",
        "keywords": ["守护灵", "提醒", "讯息", "传讯", "宇宙"],
        "description": "神秘主体 + 近期转机 + 用户自我代入",
    },
    {
        "id": "relationship-reading",
        "name": "情感关系预测",
        "keywords": ["正缘", "桃花", "复合", "他", "她", "关系", "旧人", "感情"],
        "description": "关系悬念 + 结果暗示 + 情绪确认",
    },
    {
        "id": "fortune-shift",
        "name": "运势转机提示",
        "keywords": ["好运", "转运", "大运", "近期", "未来", "财富", "事业"],
        "description": "时间窗口 + 转机承诺 + 行动暗示",
    },
    {
        "id": "tarot-learning",
        "name": "塔罗教学收藏",
        "keywords": ["教学", "牌意", "教程", "牌阵", "学习", "自学", "塔罗牌教学"],
        "description": "知识解释 + 步骤结构 + 收藏复看",
    },
]


def pattern_override_path() -> Path:
    base = Path(os.getenv("BENCHMARK_INDEX_DIR") or DEFAULT_INDEX_DIR).resolve()
    return base / "pattern_overrides.json"


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


def load_pattern_overrides() -> dict[str, dict[str, Any]]:
    data = _read_json(pattern_override_path())
    return data if isinstance(data, dict) else {}


def save_pattern_override(pattern_id: str, values: dict[str, Any]) -> dict[str, Any]:
    overrides = load_pattern_overrides()
    current = overrides.get(pattern_id, {})
    allowed = {key: values.get(key) for key in ["name", "description", "manual_notes"] if key in values}
    current.update({key: value for key, value in allowed.items() if value not in (None, "")})
    current["updated_at"] = int(time.time())
    overrides[pattern_id] = current
    _write_json(pattern_override_path(), overrides)
    return current


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


def _pattern_id_from_name(name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"ai-{digest}"


def apply_pattern_override(pattern: dict[str, Any], overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    override = (overrides or load_pattern_overrides()).get(pattern.get("pattern_id") or "")
    if not override:
        return pattern
    return {**pattern, **{key: value for key, value in override.items() if key in {"name", "description", "manual_notes", "updated_at"}}}


def classify_video_pattern(video: dict[str, Any]) -> dict[str, str]:
    haystack = " ".join(
        [
            _text(video.get("desc")),
            _text(video.get("summary")),
            _text(video.get("opening_3s")),
            _text(video.get("replicable_point")),
            _text(video.get("pattern_name")),
            _text(video.get("title_formula")),
        ]
    )
    for rule in PATTERN_RULES:
        if any(keyword in haystack for keyword in rule["keywords"]):
            return {"pattern_id": rule["id"], "name": rule["name"], "description": rule["description"], "source": "rule"}
    if video.get("pattern_name"):
        pattern_name = str(video.get("pattern_name"))
        return {
            "pattern_id": _pattern_id_from_name(pattern_name),
            "name": pattern_name,
            "description": "来自 AI 拆解字段的相似模式聚类",
            "source": "ai_breakdown",
        }
    return {"pattern_id": "general-short-video", "name": "通用短视频结构", "description": "钩子 + 情绪/信息价值 + 行动引导"}


def build_pattern_library(videos: list[dict[str, Any]], genre: str = "") -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    overrides = load_pattern_overrides()
    for video in videos:
        if genre and genre not in {video.get("content_type"), video.get("genre")}:
            continue
        pattern = classify_video_pattern(video)
        bucket = buckets.setdefault(
            pattern["pattern_id"],
            {
                "pattern_id": pattern["pattern_id"],
                "name": pattern["name"],
                "description": pattern["description"],
                "content_type": genre or video.get("content_type") or video.get("genre") or "全部类型",
                "source": pattern.get("source") or "rule",
                "representative_video_ids": [],
                "openings": [],
                "replicable_points": [],
                "title_formulas": [],
                "video_count": 0,
                "avg_imitation_value": 0,
                "avg_comment_quality_score": 0,
                "avg_collect_tendency": 0,
                "avg_comment_tendency": 0,
                "avg_share_tendency": 0,
                "avg_public_engagement_score": 0,
                "_imitation_values": [],
                "_comment_quality_scores": [],
                "_collect_tendencies": [],
                "_comment_tendencies": [],
                "_share_tendencies": [],
                "_public_engagement_scores": [],
            },
        )
        bucket["video_count"] += 1
        if len(bucket["representative_video_ids"]) < 5:
            bucket["representative_video_ids"].append(video.get("video_id"))
        for target, source in [
            ("openings", video.get("opening_3s")),
            ("replicable_points", video.get("replicable_point")),
            ("title_formulas", video.get("title_formula")),
        ]:
            if source and source not in bucket[target] and len(bucket[target]) < 5:
                bucket[target].append(source)
        bucket["_imitation_values"].append(video.get("imitation_value"))
        bucket["_collect_tendencies"].append(video.get("collect_tendency"))
        bucket["_comment_tendencies"].append(video.get("comment_tendency"))
        bucket["_share_tendencies"].append(video.get("share_tendency"))
        bucket["_public_engagement_scores"].append(video.get("public_engagement_score"))
        quality = video.get("comment_quality") if isinstance(video.get("comment_quality"), dict) else {}
        if quality.get("status") == "ready":
            bucket["_comment_quality_scores"].append(quality.get("score"))

    items = []
    for bucket in buckets.values():
        bucket["avg_imitation_value"] = average(bucket.pop("_imitation_values", []))
        bucket["avg_comment_quality_score"] = average(bucket.pop("_comment_quality_scores", []))
        bucket["avg_collect_tendency"] = average(bucket.pop("_collect_tendencies", []))
        bucket["avg_comment_tendency"] = average(bucket.pop("_comment_tendencies", []))
        bucket["avg_share_tendency"] = average(bucket.pop("_share_tendencies", []))
        bucket["avg_public_engagement_score"] = average(bucket.pop("_public_engagement_scores", []))
        items.append(apply_pattern_override(bucket, overrides))
    return sorted(items, key=lambda item: (item["video_count"], item["avg_imitation_value"]), reverse=True)
