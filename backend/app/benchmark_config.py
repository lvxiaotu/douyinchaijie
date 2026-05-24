from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INDEX_DIR = ROOT_DIR / "data" / "runtime" / "benchmark_index"

DEFAULT_PUBLIC_ENGAGEMENT_WEIGHTS = {
    "digg": 1.0,
    "comment": 3.0,
    "collect": 4.0,
    "share": 5.0,
}

WEIGHT_FIELDS = [
    {"key": "digg", "label": "点赞", "default": 1.0, "hint": "浅层认可，保留但权重最低。"},
    {"key": "comment", "label": "评论", "default": 3.0, "hint": "表达成本更高，用于发现讨论型内容。"},
    {"key": "collect", "label": "收藏", "default": 4.0, "hint": "更接近复看/学习意图，当前优先级高。"},
    {"key": "share", "label": "分享", "default": 5.0, "hint": "外溢传播信号强，但需警惕诱导分享。"},
]

METRIC_GROUPS = [
    {"name": "原始公开指标", "items": ["点赞数", "评论数", "收藏数", "分享数", "粉丝数"]},
    {"name": "代理指标", "items": ["收藏倾向", "评论倾向", "分享倾向", "小号效率", "公开互动强度"]},
    {"name": "评论样本指标", "items": ["有效评论占比", "长评占比", "提问占比", "刷屏风险"]},
    {"name": "AI 拆解指标", "items": ["复刻分", "商业价值", "评论潜力", "综合潜力"]},
]

UNAVAILABLE_COMPETITOR_METRICS = [
    {"key": "play_count", "label": "播放量", "reason": "竞品公开页不可稳定获取，不能作为对标分母。"},
    {"key": "retention_5s", "label": "5秒完播/3秒留存", "reason": "只存在于账号后台或投放后台，竞品对标不可见。"},
    {"key": "completion_rate", "label": "整体完播率", "reason": "缺少真实播放行为链路，不做完播评级。"},
    {"key": "revisit_rate", "label": "复访率", "reason": "需要用户级回访数据，竞品不可见。"},
    {"key": "core_fan_interaction", "label": "铁粉互动", "reason": "需要粉丝分层与互动身份数据，竞品不可见。"},
]


def config_path() -> Path:
    base = Path(os.getenv("BENCHMARK_INDEX_DIR") or DEFAULT_INDEX_DIR).resolve()
    return base / "metric_config.json"


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


def normalize_weights(weights: dict[str, Any] | None = None) -> dict[str, float]:
    normalized = dict(DEFAULT_PUBLIC_ENGAGEMENT_WEIGHTS)
    for key in normalized:
        raw = (weights or {}).get(key)
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        normalized[key] = max(0.0, min(value, 20.0))
    return normalized


def default_metric_config() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": 0,
        "public_engagement_weights": dict(DEFAULT_PUBLIC_ENGAGEMENT_WEIGHTS),
        "weight_fields": WEIGHT_FIELDS,
        "metric_groups": METRIC_GROUPS,
        "unavailable_competitor_metrics": UNAVAILABLE_COMPETITOR_METRICS,
        "evaluation_scope": "public_competitor_only",
        "notes": [
            "对标账号只使用可见公开数据、评论样本和 AI 拆解结果。",
            "综合分只用于快速粗排，不是科学定律。",
            "播放、留存、完播、复访和铁粉互动不参与竞品评分。",
        ],
    }


def load_metric_config() -> dict[str, Any]:
    config = default_metric_config()
    saved = _read_json(config_path())
    if isinstance(saved, dict):
        config.update(saved)
    config["public_engagement_weights"] = normalize_weights(config.get("public_engagement_weights"))
    config["weight_fields"] = WEIGHT_FIELDS
    config["metric_groups"] = METRIC_GROUPS
    config["unavailable_competitor_metrics"] = UNAVAILABLE_COMPETITOR_METRICS
    config["evaluation_scope"] = "public_competitor_only"
    return config


def save_metric_config(weights: dict[str, Any]) -> dict[str, Any]:
    current = load_metric_config()
    current["public_engagement_weights"] = normalize_weights(weights)
    current["version"] = int(current.get("version") or 1) + 1
    current["updated_at"] = int(time.time())
    _write_json(config_path(), current)
    return current
