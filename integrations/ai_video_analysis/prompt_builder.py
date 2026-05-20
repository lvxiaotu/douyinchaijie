from __future__ import annotations

import json
from typing import Any


GENRE_ALIASES = {
    "knowledge": "knowledge",
    "education": "knowledge",
    "science": "knowledge",
    "科普": "knowledge",
    "知识": "knowledge",
    "干货": "knowledge",
    "beauty": "beauty",
    "makeup": "beauty",
    "skincare": "beauty",
    "美妆": "beauty",
    "护肤": "beauty",
    "好物": "commerce",
    "种草": "commerce",
    "带货": "commerce",
    "commerce": "commerce",
    "product": "commerce",
    "探店": "local_life",
    "本地生活": "local_life",
    "local_life": "local_life",
    "剧情": "drama",
    "情感": "drama",
    "drama": "drama",
    "story": "drama",
    "玄学": "mysticism",
    "塔罗": "mysticism",
    "占卜": "mysticism",
    "星座": "mysticism",
    "tarot": "mysticism",
    "mysticism": "mysticism",
}

GENRE_PROFILES = {
    "generic": {
        "label": "泛赛道",
        "timeline": "钩子筛选 -> 痛点/价值铺垫 -> 证据/反转 -> 情绪或利益强化 -> CTA",
        "dimensions": "受众筛选、好奇心、信任建构、评论诱因、转化路径、复刻变量",
    },
    "knowledge": {
        "label": "知识/科普",
        "timeline": "反常识提问 -> 现状否定 -> 底层原理解析 -> 案例证明 -> 总结避坑/收藏",
        "dimensions": "知识密度、可信证据、概念降维、误区纠正、收藏动机",
    },
    "beauty": {
        "label": "美妆/护肤",
        "timeline": "痛点唤醒 -> 成分/效果展示 -> 前后对比 -> 使用场景 -> 价格/优惠刺激",
        "dimensions": "肤质/妆效痛点、视觉前后差、产品证据、真实感、求链接动机",
    },
    "commerce": {
        "label": "好物/种草/带货",
        "timeline": "问题场景 -> 产品介入 -> 效果证明 -> 信任背书 -> 限时/价格/下单 CTA",
        "dimensions": "商品利益点、信任背书、购买阻力、评论求链接、转化口令",
    },
    "drama": {
        "label": "剧情/情感",
        "timeline": "冲突爆发 -> 关系张力 -> 反转制造 -> 情绪释放 -> 金句/评论站队",
        "dimensions": "人物关系、冲突强度、反转节奏、共鸣台词、站队评论",
    },
    "local_life": {
        "label": "探店/本地生活",
        "timeline": "地点/价格钩子 -> 环境展示 -> 核心体验 -> 避坑/性价比 -> 到店 CTA",
        "dimensions": "地理位置、价格锚点、环境真实感、体验证据、到店理由",
    },
    "mysticism": {
        "label": "玄学/塔罗/星座",
        "timeline": "命中式开场 -> 情绪安慰 -> 象征解释 -> 评论仪式 -> 安全化 CTA",
        "dimensions": "情绪安慰、仪式感、模糊命中、评论打卡、避免绝对承诺",
    },
}

VIRAL_BREAKDOWN_GUIDE = """
泛赛道爆款拆解要求：
1. 不要只总结内容，要拆出通用短视频结构：钩子、冲突/价值、信任证据、视觉行为、评论诱因、转化设计。
2. 使用“数据指标抓异常，分段多模态抓手法，全局大模型找公式”的口径，所有结论必须能回到文本、时间点、评论或关键帧证据。
3. 根据 genre 自适应行业术语，但输出字段必须保持通用，方便美妆、知识科普、剧情、探店、好物推荐、玄学等赛道共用。
4. 必须给出脱敏后的标准复刻脚本模板，使用 [人群]、[痛点]、[场景]、[证据]、[反转]、[CTA] 等占位符。
5. 必须检查平台风险：AIGC 标识、版权/肖像、虚假宣传、绝对化承诺、疗效/财富/情感保证、价格误导。
6. 评分必须是 0-100 的整数；无法确认的内容请说明“未能从证据中确认，但可推测为……”，不要编造硬数据。
""".strip()

JSON_RESPONSE_CONTRACT = """
请只返回一个合法 JSON 对象，不要返回 Markdown、解释文字或代码块。字段名必须使用下面这些英文 key：
{
  "genre": "视频赛道，优先使用输入 genre；如果自动识别，请写识别结果",
  "summary": "一句话概括视频的爆款套路和可复用价值",
  "content_identity": {
    "track": "内容赛道：美妆/知识科普/剧情情感/探店/好物推荐/玄学/泛娱乐/其他",
    "niche_fit": "该结构适合迁移到哪些赛道，说明迁移变量，不要局限于固定三赛道",
    "account_persona": "账号人设、叙事视角或可复制角色"
  },
  "core_hook": {
    "opening_3s": "开头 3 秒如何完成受众筛选或好奇心勾引",
    "curiosity_gap": "制造了什么信息差、悬念、反常识或未完成感",
    "emotional_trigger": "触发了什么情绪：焦虑、爽感、治愈、猎奇、共鸣、占便宜等",
    "comment_bait": "诱发评论、争议、转发、收藏、求链接或打卡的点"
  },
  "need_context": {
    "pain_point": "用户痛点或焦虑",
    "application_scene": "具体生活、消费、关系或工作场景",
    "hidden_desire": "用户没有明说但会被击中的深层欲望"
  },
  "product_power": {
    "core_benefit": "核心功能、情绪价值、信息价值或利益点",
    "trigger_moment": "让观众想买、想试、想收藏、想评论或想转发的瞬间",
    "trust_builder": "信任背书、证据、对比、实测或真实感来源",
    "product_role": "产品/观点/人物在视频里扮演主角、解决方案、道具、证据还是隐形植入"
  },
  "visual_structure": {
    "shot_structure": "镜头流转逻辑",
    "reusable_elements": "可复刻的转场、BGM、花字、特效、角度、道具或节奏",
    "timeline_beats": ["00:00-00:03：钩子", "00:03-00:08：冲突/铺垫"],
    "audio_rhythm": "口播、BGM、音效、停顿、字幕节奏"
  },
  "copywriting_formula": {
    "title_formula": "标题公式，使用变量占位",
    "script_formula": "脚本公式，按步骤拆成可替换模板",
    "golden_lines": ["可复用金句、字幕或口播句式"],
    "cta": "关注、评论、收藏、私信、求链接、到店、下单等行动号召"
  },
  "market_positioning": {
    "suitable_products": "这种套路适合的关联产品、服务、账号类型或内容栏目",
    "target_audience": "目标人群画像",
    "creative_direction": "后续适合深耕的创作方向"
  },
  "replication_plan": {
    "pattern_name": "给这个爆款结构起一个便于归档的公式名",
    "reusable_formula": "一句话描述可复刻公式：谁在什么场景遇到什么冲突，如何反转并转化",
    "cross_genre_variants": "至少给出 3 个跨赛道改写方向",
    "mysticism_variant": "如适用，迁移到玄学方向的安全化改编建议；不适用也说明原因",
    "ai_pet_variant": "如适用，迁移到 AI 小动物方向的改编建议；不适用也说明原因",
    "ai_commerce_variant": "如适用，迁移到 AI 带货方向的改编建议；不适用也说明原因",
    "difficulty": "低/中/高，并说明制作难点",
    "priority": "低/中/高，并说明是否值得优先模仿"
  },
  "standard_remake_template": "将原视频完全脱敏后的通用复刻脚本模板，必须使用 [占位符]",
  "risk_control": {
    "risk_level": "低/中/高",
    "platform_risks": ["可能的平台、版权、AIGC标识、虚假宣传或绝对化承诺风险"],
    "safe_rewrite": "更稳妥的表达方式"
  },
  "viral_scores": {
    "viral_potential": 0,
    "imitation_value": 0,
    "commerce_value": 0,
    "comment_potential": 0,
    "overall": 0
  }
}
""".strip()

DEFAULT_ANALYSIS_PROMPT = """
你是泛赛道短视频逆向工程专家。请分析这个视频，并只返回 JSON，不要返回 Markdown。

视频标题或描述：{desc}
作者：{author}
视频赛道类型：{genre}

目标：把原视频拆成一套可迁移到任意赛道的多模态爆款公式，而不是只服务某个垂类。请综合文本、画面、节奏、评论反馈和数据指标，输出可沉淀进公式库的结构。

拆解原则：
1. 先判断它属于什么赛道、靠什么火：情绪共鸣、争议互动、干货收藏、视觉爽点、反常识、商品利益、关系冲突、地点/价格吸引等。
2. 拆开头 3 秒、剧情推进、镜头节奏、文案公式、评论诱因、信任建构、转化设计。
3. 不要照抄原视频具体表达，要抽象成可替换变量和可复用模板。
4. 如果视频不带货，也要判断它能否迁移成商业内容；如果视频是商业内容，也要拆出非商业赛道可复用的叙事结构。
5. 对不同赛道使用对应行业术语，但最终字段保持通用。
6. 如果涉及玄学、疗效、财富、情感挽回、夸大效果、真实人物肖像、AI 生成内容等风险，必须指出并给出安全改写。
7. 评分使用 0-100 的整数，越高越值得优先复刻。
""".strip()


def normalize_genre(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    return GENRE_ALIASES.get(lowered) or GENRE_ALIASES.get(raw) or lowered


def infer_genre(video: dict[str, Any], evidence: dict[str, Any] | None = None) -> str:
    evidence = evidence or {}
    metadata = evidence.get("metadata") if isinstance(evidence.get("metadata"), dict) else {}
    target_context = video.get("douyin_target_context") if isinstance(video.get("douyin_target_context"), dict) else {}
    content_identity = video.get("content_identity") if isinstance(video.get("content_identity"), dict) else {}
    candidates = [
        video.get("genre"),
        metadata.get("genre"),
        target_context.get("genre"),
        content_identity.get("track"),
        video.get("category"),
        video.get("desc"),
        video.get("title"),
    ]
    for value in candidates:
        genre = normalize_genre(value)
        if genre in GENRE_PROFILES and genre != "generic":
            return genre
    combined = " ".join(str(item or "") for item in candidates if item).lower()
    for alias, canonical in GENRE_ALIASES.items():
        if alias.lower() in combined:
            return canonical
    return normalize_genre(candidates[0]) if candidates and candidates[0] else "generic"


def genre_profile(genre: str) -> dict[str, str]:
    normalized = normalize_genre(genre) or "generic"
    profile = GENRE_PROFILES.get(normalized) or GENRE_PROFILES["generic"]
    return {"key": normalized, **profile}


def prompt_context(video: dict[str, Any], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    genre = infer_genre(video, evidence)
    return {
        "genre": genre,
        "genre_profile": genre_profile(genre),
    }


def segment_breakdown_prompt(video: dict[str, Any], segment: dict[str, Any]) -> str:
    desc = video.get("desc") or video.get("title") or ""
    context = prompt_context(video)
    profile = context["genre_profile"]
    keyframes = [
        {"time": frame.get("time_label"), "image_path": frame.get("image_path")}
        for frame in (segment.get("keyframes") or [])
    ]
    grid = (segment.get("keyframe_grid") or {}).get("image_path") if isinstance(segment.get("keyframe_grid"), dict) else ""
    return f"""
你是通用短视频视听语言解构专家。请只返回合法 JSON，不要返回 Markdown。

视频标题：{desc}
视频赛道类型：{profile["label"]} ({context["genre"]})
赛道典型节奏：{profile["timeline"]}
本赛道重点观察维度：{profile["dimensions"]}
当前片段：{segment.get("time_range")}
片段转写：
{str(segment.get("transcript") or "")[:7000]}

关键帧索引：
{json.dumps(keyframes, ensure_ascii=False)}

关键帧网格图：
{grid or "无"}

请输出：
{{
  "segment_id": "{segment.get("segment_id")}",
  "time_range": "{segment.get("time_range")}",
  "genre": "{context["genre"]}",
  "segment_role": "开头钩子/冲突建立/信息铺垫/证明演示/情绪爆点/转化推动/结尾收口/其他",
  "visual_style": "画面视觉手法，如双机位切换、近景大头、B面素材、绿幕、混剪、特写、对比图；无法确认则写无法确认",
  "audio_pacing": "声音特征，如语速突变、BGM卡点、音效、停顿、字幕密度",
  "narrative_technique": "本段叙事技巧，如提出疑问、展示痛点、给出反转、硬核科普、视觉爽点、卖点展现",
  "retention_mechanism": "本段靠什么留住用户，如视觉冲击、好奇心、情绪共鸣、利益诱导、争议站队",
  "hook": "这一段如何抓注意力",
  "conflict_or_value": "这一段制造的冲突、价值或信息差",
  "emotion": "情绪触发",
  "copywriting_pattern": "可复用文案句式",
  "commerce_signal": "产品、购买、收藏、私信、信任背书等转化信号",
  "comment_trigger": "评论诱因",
  "replicable_point": "这一段最值得复刻的点",
  "highlight_screenshots": [
    {{"time": 12.5, "time_label": "00:12", "reason": "最能证明钩子、反转、产品利益点或情绪爆点的画面"}}
  ]
}}
""".strip()


def global_breakdown_prompt(
    video: dict[str, Any],
    *,
    evidence: dict[str, Any],
    segment_breakdowns: list[dict[str, Any]],
    prompt_template: str,
) -> str:
    desc = video.get("desc") or video.get("title") or ""
    metadata = evidence.get("metadata") or {}
    context = prompt_context(video, evidence)
    profile = context["genre_profile"]
    payload = {
        "metadata": metadata,
        "genre_context": context,
        "douyin_target": evidence.get("douyin_target") or video.get("douyin_target_context") or {},
        "segment_breakdowns": segment_breakdowns,
        "transcript_excerpt": str((evidence.get("transcript") or {}).get("full_text") or "")[:12000],
    }
    base_prompt = clean_prompt(prompt_template)
    base_prompt = (
        base_prompt
        .replace("{desc}", desc)
        .replace("{author}", str(metadata.get("author") or "未知"))
        .replace("{genre}", profile["label"])
    )
    return "\n\n".join(
        [
            base_prompt,
            f"赛道上下文：{json.dumps(context, ensure_ascii=False)}",
            VIRAL_BREAKDOWN_GUIDE,
            "下面是已由音频转写、评论数据和分段多模态分析得到的证据包。请基于证据汇总全局爆款公式，不要编造证据中不存在的事实。请重点输出爆款公式、文本心理学、视觉节奏模板和脱敏后的 standard_remake_template：",
            json.dumps(payload, ensure_ascii=False),
            JSON_RESPONSE_CONTRACT,
        ]
    )


def analysis_prompt(video: dict[str, Any], prompt_template: str) -> str:
    desc = video.get("desc") or video.get("title") or ""
    author = video.get("author") or {}
    author_name = author.get("nickname") if isinstance(author, dict) else author
    context = prompt_context(video)
    profile = context["genre_profile"]
    prompt = clean_prompt(prompt_template)
    prompt = (
        prompt
        .replace("{desc}", desc)
        .replace("{author}", author_name or "未知")
        .replace("{genre}", profile["label"])
    )
    metadata = {
        "video_title": desc,
        "author": author_name or "未知",
        "aweme_id": video.get("aweme_id") or video.get("id") or "",
        "genre": context["genre"],
        "genre_profile": profile,
    }
    return "\n\n".join(
        [
            prompt,
            f"视频元数据：{json.dumps(metadata, ensure_ascii=False)}",
            VIRAL_BREAKDOWN_GUIDE,
            JSON_RESPONSE_CONTRACT,
        ]
    )


def clean_prompt(prompt: str) -> str:
    cleaned = str(prompt or "").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1]
    cleaned = cleaned.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    return cleaned.strip() or DEFAULT_ANALYSIS_PROMPT
