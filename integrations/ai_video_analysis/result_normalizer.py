from __future__ import annotations

import json
import re
from typing import Any

from integrations.ai_video_analysis.result_schema import validate_analysis_result, validate_segment_breakdown


def parse_model_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = {"summary": cleaned}
    if not isinstance(data, dict):
        data = {"summary": cleaned}

    return validate_analysis_result(normalize_analysis_result(data, raw_text=cleaned))


def parse_segment_json(text: str, segment: dict[str, Any]) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = {"summary": cleaned}
    if not isinstance(data, dict):
        data = {"summary": cleaned}
    data.setdefault("segment_id", segment.get("segment_id"))
    data.setdefault("time_range", segment.get("time_range"))
    data.setdefault("genre", segment.get("genre") or "")
    if "visual_style" not in data:
        data["visual_style"] = data.get("visual_signal") or ""
    if "audio_pacing" not in data:
        data["audio_pacing"] = data.get("audio_rhythm") or data.get("audio_signal") or ""
    if "narrative_technique" not in data:
        data["narrative_technique"] = data.get("copywriting_pattern") or data.get("segment_role") or ""
    if "retention_mechanism" not in data:
        data["retention_mechanism"] = data.get("hook") or data.get("comment_trigger") or data.get("replicable_point") or ""
    if "copywriting_intent" not in data:
        data["copywriting_intent"] = data.get("hook") or data.get("conflict_or_value") or data.get("copywriting_pattern") or ""
    if "psychology_principle" not in data:
        data["psychology_principle"] = data.get("psychological_principle") or data.get("psychology") or data.get("retention_mechanism") or ""
    if "suggestion_mechanism" not in data:
        data["suggestion_mechanism"] = data.get("suggestion") or data.get("cue") or data.get("emotion") or ""
    if "emotion" not in data:
        data["emotion"] = data.get("emotional_trigger") or data.get("affect") or ""
    if "copywriting_pattern" not in data:
        data["copywriting_pattern"] = data.get("script_formula") or data.get("copywriting_intent") or ""
    if "commerce_signal" not in data:
        data["commerce_signal"] = data.get("product_power") or data.get("cta") or ""
    if "comment_trigger" not in data:
        data["comment_trigger"] = data.get("comment_bait") or data.get("question_hook") or ""
    if "replicable_point" not in data:
        data["replicable_point"] = data.get("reusable_elements") or data.get("hook") or data.get("narrative_technique") or ""
    if "replication_action" not in data:
        data["replication_action"] = data.get("replicable_point") or data.get("copywriting_pattern") or ""
    return validate_segment_breakdown(data)


def normalize_analysis_result(data: dict[str, Any], raw_text: str = "") -> dict[str, Any]:
    genre = _first_text(data, ["genre", "赛道", "内容赛道"])
    summary = _first_text(data, ["summary", "摘要", "视频摘要", "一句话摘要"])
    content_identity = _first_dict(data, ["content_identity", "内容定位", "赛道判断"])
    core_hook = _first_dict(data, ["core_hook", "核心钩子", "核心勾子"])
    need_context = _first_dict(data, ["need_context", "需求与场景", "需求场景"])
    product_power = _first_dict(data, ["product_power", "产品表现", "产品力", "产品价值"])
    visual_structure = _first_dict(data, ["visual_structure", "视觉与结构", "视觉结构"])
    psychology_breakdown = _first_dict(data, ["psychology_breakdown", "心理拆解", "心理文案拆解"])
    copywriting_formula = _first_dict(data, ["copywriting_formula", "文案公式", "脚本公式"])
    market_positioning = _first_dict(data, ["market_positioning", "商业定位", "市场定位"])
    replication_plan = _first_dict(data, ["replication_plan", "复刻计划", "模仿计划"])
    risk_control = _first_dict(data, ["risk_control", "风险控制", "合规风险"])
    viral_scores = _first_dict(data, ["viral_scores", "爆款评分", "评分"])

    return {
        "genre": genre or _first_text(content_identity, ["track", "内容赛道", "赛道"]),
        "summary": summary,
        "content_identity": {
            "track": _first_text(content_identity, ["track", "内容赛道", "赛道"]),
            "niche_fit": _first_text(content_identity, ["niche_fit", "赛道适配", "适配方向"]),
            "account_persona": _first_text(content_identity, ["account_persona", "账号人设", "人设"]),
        },
        "core_hook": {
            "opening_3s": _first_text(core_hook, ["opening_3s", "开头3秒钩子", "开头3秒勾子", "开头3秒狗子"])
            or _join_old(data.get("hooks")),
            "curiosity_gap": _first_text(core_hook, ["curiosity_gap", "信息差", "悬念"]),
            "emotional_trigger": _first_text(core_hook, ["emotional_trigger", "情绪触发", "情绪"]),
            "comment_bait": _first_text(core_hook, ["comment_bait", "评论诱因", "评论钩子"]),
        },
        "need_context": {
            "pain_point": _first_text(need_context, ["pain_point", "痛点定位", "痛点"]),
            "application_scene": _first_text(need_context, ["application_scene", "应用场景", "场景"]),
            "hidden_desire": _first_text(need_context, ["hidden_desire", "隐性欲望", "深层欲望"]),
        },
        "product_power": {
            "core_benefit": _first_text(product_power, ["core_benefit", "功效提炼", "核心功效", "核心利益点"]),
            "trigger_moment": _first_text(product_power, ["trigger_moment", "激励点", "触发点", "转化瞬间"]),
            "trust_builder": _first_text(product_power, ["trust_builder", "信任来源", "信任背书"]),
            "product_role": _first_text(product_power, ["product_role", "产品角色", "产品定位"]),
        },
        "visual_structure": {
            "shot_structure": _first_text(visual_structure, ["shot_structure", "镜头结构", "结构"])
            or _join_old(data.get("timeline")),
            "reusable_elements": _first_text(visual_structure, ["reusable_elements", "可复用元素", "可服用元素"])
            or _join_old(data.get("visuals")),
            "timeline_beats": _first_list_text(visual_structure, ["timeline_beats", "时间线", "节奏点"]),
            "audio_rhythm": _first_text(visual_structure, ["audio_rhythm", "声音节奏", "音频节奏"]),
        },
        "psychology_breakdown": {
            "copywriting_intent": _first_text(psychology_breakdown, ["copywriting_intent", "文案意图", "话术意图"]),
            "psychology_principle": _first_text(psychology_breakdown, ["psychology_principle", "心理原理", "心理学原理"]),
            "suggestion_mechanism": _first_text(psychology_breakdown, ["suggestion_mechanism", "暗示机制", "暗示"]),
            "emotion": _first_text(psychology_breakdown, ["emotion", "情绪"]),
            "copywriting_pattern": _first_text(psychology_breakdown, ["copywriting_pattern", "文案句式", "文案模式"]),
            "commerce_signal": _first_text(psychology_breakdown, ["commerce_signal", "转化信号", "商业信号"]),
            "comment_trigger": _first_text(psychology_breakdown, ["comment_trigger", "评论诱因", "互动诱因"]),
            "replicable_point": _first_text(psychology_breakdown, ["replicable_point", "可复刻点", "复刻动作"]),
            "replication_action": _first_text(psychology_breakdown, ["replication_action", "复刻动作", "动作建议"]),
        },
        "copywriting_formula": {
            "title_formula": _first_text(copywriting_formula, ["title_formula", "标题公式"]),
            "script_formula": _first_text(copywriting_formula, ["script_formula", "脚本公式"]),
            "golden_lines": _first_list_text(copywriting_formula, ["golden_lines", "金句", "可复用句式"]),
            "cta": _first_text(copywriting_formula, ["cta", "行动号召", "转化口令"]),
        },
        "market_positioning": {
            "suitable_products": _first_text(market_positioning, ["suitable_products", "适合产品", "适配产品"]),
            "target_audience": _first_text(market_positioning, ["target_audience", "目标人群", "目标用户"]),
            "creative_direction": _first_text(market_positioning, ["creative_direction", "创作方向", "后续方向"])
            or _join_old(data.get("rewrite_prompts")),
        },
        "replication_plan": {
            "pattern_name": _first_text(replication_plan, ["pattern_name", "公式名", "模式名"]),
            "reusable_formula": _first_text(replication_plan, ["reusable_formula", "可复刻公式", "复用公式"]),
            "cross_genre_variants": _first_list_text(replication_plan, ["cross_genre_variants", "跨赛道改写", "跨赛道变体"]),
            "mysticism_variant": _first_text(replication_plan, ["mysticism_variant", "玄学方向", "玄学改编"]),
            "ai_pet_variant": _first_text(replication_plan, ["ai_pet_variant", "AI小动物方向", "小动物改编"]),
            "ai_commerce_variant": _first_text(replication_plan, ["ai_commerce_variant", "AI带货方向", "带货改编"]),
            "difficulty": _first_text(replication_plan, ["difficulty", "制作难度", "难度"]),
            "priority": _first_text(replication_plan, ["priority", "优先级", "模仿优先级"]),
        },
        "standard_remake_template": _first_text(data, ["standard_remake_template", "通用复刻脚本模板", "复刻脚本模板", "脱敏脚本模板"]),
        "risk_control": {
            "risk_level": _first_text(risk_control, ["risk_level", "风险等级"]),
            "platform_risks": _first_list_text(risk_control, ["platform_risks", "平台风险", "风险点"]),
            "safe_rewrite": _first_text(risk_control, ["safe_rewrite", "安全改写", "合规表达"]),
        },
        "viral_scores": {
            "viral_potential": _first_number(viral_scores, ["viral_potential", "爆款潜力"]),
            "imitation_value": _first_number(viral_scores, ["imitation_value", "模仿价值"]),
            "commerce_value": _first_number(viral_scores, ["commerce_value", "商业价值"]),
            "comment_potential": _first_number(viral_scores, ["comment_potential", "评论潜力"]),
            "overall": _first_number(viral_scores, ["overall", "综合评分"]),
        },
        "raw_model_json": data,
        "raw_model_text": raw_text,
    }


def _first_dict(data: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _first_text(data: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            return _join_old(value)
        if value is not None and not isinstance(value, dict):
            return str(value)
    return ""


def _first_list_text(data: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return _join_old(value)
        if isinstance(value, str):
            return value.strip()
    return ""


def _first_number(data: dict[str, Any], keys: list[str]) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)):
            return max(0, min(100, int(value)))
        if isinstance(value, str):
            match = re.search(r"\d+", value)
            if match:
                return max(0, min(100, int(match.group(0))))
    return 0


def _join_old(value: Any) -> str:
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(" ".join(str(part) for part in item.values()))
            else:
                parts.append(str(item))
        return "；".join(parts)
    return str(value or "")
