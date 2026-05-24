from __future__ import annotations

from statistics import mean
from typing import Any

from .benchmark_config import DEFAULT_PUBLIC_ENGAGEMENT_WEIGHTS, load_metric_config

DEFAULT_WEIGHTS = DEFAULT_PUBLIC_ENGAGEMENT_WEIGHTS


def number(value: Any, default: float = 0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def int_number(value: Any, default: int = 0) -> int:
    return int(number(value, default))


def ratio(numerator: Any, denominator: Any) -> float:
    base = number(denominator)
    if base <= 0:
        return 0.0
    return round(number(numerator) / base, 6)


def public_engagement_score(video: dict[str, Any], weights: dict[str, float] | None = None) -> float:
    next_weights = {**DEFAULT_WEIGHTS, **(weights or load_metric_config().get("public_engagement_weights") or {})}
    return (
        number(video.get("digg_count")) * next_weights["digg"]
        + number(video.get("comment_count")) * next_weights["comment"]
        + number(video.get("collect_count")) * next_weights["collect"]
        + number(video.get("share_count")) * next_weights["share"]
    )


def video_metric_summary(
    video: dict[str, Any],
    author: dict[str, Any] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    digg_count = int_number(video.get("digg_count"))
    comment_count = int_number(video.get("comment_count"))
    collect_count = int_number(video.get("collect_count"))
    share_count = int_number(video.get("share_count"))
    engagement = public_engagement_score(video, weights=weights)
    follower_count = int_number((author or {}).get("follower_count"))
    return {
        "digg_count": digg_count,
        "comment_count": comment_count,
        "collect_count": collect_count,
        "share_count": share_count,
        "collect_tendency": ratio(collect_count, digg_count),
        "comment_tendency": ratio(comment_count, digg_count),
        "share_tendency": ratio(share_count, digg_count),
        "public_engagement_score": round(engagement, 6),
        "small_account_efficiency": round(engagement / follower_count, 6) if follower_count > 0 else 0,
    }


def average(values: list[Any]) -> float:
    numbers = [number(value) for value in values if value is not None]
    if not numbers:
        return 0.0
    return round(mean(numbers), 6)


def normalize_score(value: Any) -> int:
    score = int(round(number(value)))
    return max(0, min(100, score))


def benchmark_author_score(author: dict[str, Any]) -> int:
    collect_score = min(100.0, number(author.get("avg_collect_tendency")) * 300)
    comment_score = min(100.0, number(author.get("avg_comment_tendency")) * 600)
    imitation_score = normalize_score(author.get("avg_imitation_value"))
    stability_score = min(100.0, number(author.get("video_count")) * 12)
    small_account_score = min(100.0, number(author.get("avg_small_account_efficiency")) * 5)
    risk_score = {"低": 100, "中": 70, "高": 30}.get(str(author.get("risk_level") or ""), 70)
    total = (
        collect_score * 0.25
        + comment_score * 0.20
        + imitation_score * 0.20
        + stability_score * 0.15
        + small_account_score * 0.10
        + risk_score * 0.10
    )
    return normalize_score(total)


def sort_items(items: list[dict[str, Any]], sort_key: str, default_key: str = "public_engagement_score") -> list[dict[str, Any]]:
    key_map = {
        "overall": "public_engagement_score",
        "benchmark": "benchmark_score",
        "small_account": "small_account_efficiency",
        "collect": "collect_tendency",
        "comment": "comment_tendency",
        "share": "share_tendency",
        "imitation": "imitation_value",
        "commerce": "commerce_value",
        "latest": "publish_time",
    }
    resolved_key = key_map.get(sort_key, sort_key or default_key)
    return sorted(items, key=lambda item: number(item.get(resolved_key)), reverse=True)
