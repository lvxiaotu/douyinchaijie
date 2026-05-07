from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any

import requests
from dotenv import load_dotenv

from integrations.base import IntegrationAdapter, IntegrationManifest
from backend.app.ai_provider_state import active_ai_provider
from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline


DEFAULT_OUTPUT_DIR = Path("data/runtime/ai_video_analysis")
VIRAL_BREAKDOWN_GUIDE = """
爆款拆解增强要求：
1. 不要只总结内容，要拆出可进入公式库的结构：钩子、情绪、冲突、镜头、文案、评论诱因、转化设计。
2. 必须判断该视频能否迁移到三个重点方向：玄学、AI小动物、AI带货。
3. 必须给出可复刻公式、三赛道改编建议、制作难度、模仿优先级。
4. 必须检查风险：AIGC标识、版权/肖像、虚假宣传、迷信绝对承诺、疗效/财富/情感保证。
5. 评分必须是 0-100 的整数；无法确认的内容请说明“未能从视频中确认，但可推测为……”，不要编造硬数据。
""".strip()
JSON_RESPONSE_CONTRACT = """
请只返回一个合法 JSON 对象，不要返回 Markdown、解释文字或代码块。字段名必须使用下面这些英文 key：
{
  "summary": "一句话概括视频的爆款套路和可复用价值",
  "content_identity": {
    "track": "内容赛道：玄学/AI小动物/AI带货/泛娱乐/种草/其他",
    "niche_fit": "是否适合迁移到玄学、AI小动物、AI带货，说明原因",
    "account_persona": "账号人设、叙事视角或可复制角色"
  },
  "core_hook": {
    "opening_3s": "开头 3 秒如何抓住注意力",
    "curiosity_gap": "制造了什么信息差、悬念或反常识",
    "emotional_trigger": "触发了什么情绪：焦虑、爽感、治愈、猎奇、共鸣、占便宜等",
    "comment_bait": "诱发评论、争议、转发或收藏的点"
  },
  "need_context": {
    "pain_point": "用户痛点或焦虑",
    "application_scene": "具体生活或工作场景",
    "hidden_desire": "用户没有明说但会被击中的深层欲望"
  },
  "product_power": {
    "core_benefit": "核心功能或利益点",
    "trigger_moment": "让观众想买、想试或想收藏的瞬间",
    "trust_builder": "信任背书、证据、对比或真实感来源",
    "product_role": "产品在视频里扮演主角、解决方案、道具、仪式感载体还是隐形植入"
  },
  "visual_structure": {
    "shot_structure": "镜头流转逻辑",
    "reusable_elements": "可复刻的转场、BGM、花字、特效、角度或节奏",
    "timeline_beats": ["00:00-00:03：钩子", "00:03-00:08：冲突/铺垫"],
    "audio_rhythm": "口播、BGM、音效、停顿、字幕节奏"
  },
  "copywriting_formula": {
    "title_formula": "标题公式，使用变量占位",
    "script_formula": "脚本公式，按步骤拆成可替换模板",
    "golden_lines": ["可复用金句、字幕或口播句式"],
    "cta": "关注、评论、收藏、私信、下单等行动号召"
  },
  "market_positioning": {
    "suitable_products": "这种套路适合的关联产品",
    "target_audience": "目标人群画像",
    "creative_direction": "后续适合深耕的创作方向"
  },
  "replication_plan": {
    "pattern_name": "给这个爆款结构起一个便于归档的公式名",
    "reusable_formula": "一句话描述可复刻公式：谁在什么场景遇到什么冲突，如何反转并转化",
    "mysticism_variant": "迁移到玄学方向的改编建议",
    "ai_pet_variant": "迁移到 AI 小动物方向的改编建议",
    "ai_commerce_variant": "迁移到 AI 带货方向的改编建议",
    "difficulty": "低/中/高，并说明制作难点",
    "priority": "低/中/高，并说明是否值得优先模仿"
  },
  "risk_control": {
    "risk_level": "低/中/高",
    "platform_risks": ["可能的平台、版权、AIGC标识、虚假宣传或迷信承诺风险"],
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
你是一个顶级短视频爆款拆解师、AI 内容编导和带货转化顾问。请分析这个视频，并只返回 JSON，不要返回 Markdown。

视频标题或描述：{desc}
作者：{author}

目标：不要只总结内容，要拆出可以沉淀进素材库的爆款公式，方便后续迁移到“玄学、AI 小动物、AI 带货”三个方向。

拆解原则：
1. 先判断它属于什么赛道、靠什么火：情绪、猎奇、爽感、信息差、痛点、视觉奇观、评论争议、商品利益点。
2. 拆开头 3 秒、剧情推进、镜头节奏、文案公式、评论诱因、转化设计。
3. 不要照抄原视频的具体表达，要抽象成可替换变量和可复用模板。
4. 如果视频不带货，也要判断它能否迁移成带货内容。
5. 如果涉及玄学、疗效、财富、情感挽回、夸大效果、真实人物肖像、AI 生成内容等风险，必须指出并给出安全改写。
6. 评分使用 0-100 的整数，越高越值得优先模仿。

请严格按以下 JSON 结构输出，字段名必须保持英文不变，字段值使用中文：
{
  "summary": "一句话概括这个视频的爆款套路和可复用价值",
  "content_identity": {
    "track": "内容赛道：玄学/AI小动物/AI带货/泛娱乐/种草/其他",
    "niche_fit": "是否适合迁移到玄学、AI小动物、AI带货，说明原因",
    "account_persona": "账号人设、叙事视角或可复制角色"
  },
  "core_hook": {
    "opening_3s": "开头3秒钩子：视频如何抓住注意力，是视觉冲击、悬念提问、利益承诺、情绪共鸣还是反差画面？",
    "curiosity_gap": "信息差/悬念：观众为什么想继续看？",
    "emotional_trigger": "情绪触发：焦虑、爽感、治愈、猎奇、共鸣、占便宜、恐惧错过等。",
    "comment_bait": "评论诱因：哪些表达会让观众想评论、反驳、求链接、求后续或艾特别人？"
  },
  "need_context": {
    "pain_point": "痛点定位：戳中了用户生活中的哪个具体痛点或焦虑？",
    "application_scene": "应用场景：发生在什么具体生活或工作场景？",
    "hidden_desire": "隐性欲望：用户真正想获得的安全感、掌控感、陪伴感、变美、变强、好运、效率或省钱是什么？"
  },
  "product_power": {
    "core_benefit": "利益点提炼：展示的核心功能、情绪价值、仪式感或结果承诺是什么？",
    "trigger_moment": "转化瞬间：哪个瞬间让观众产生我想买/想试/想收藏/想转发的冲动？",
    "trust_builder": "信任来源：对比、实测、前后变化、专家/达人背书、真实生活细节、评论反馈等。",
    "product_role": "产品角色：主角、解决方案、剧情道具、仪式感载体、陪伴物、隐形植入或无产品。"
  },
  "visual_structure": {
    "shot_structure": "镜头结构：按时间顺序拆解为钩子 -> 铺垫 -> 冲突 -> 反转/效果 -> 信任 -> 行动号召。",
    "reusable_elements": "可复用元素：角色、场景、转场、BGM、花字、特效、拍摄角度、AI画面风格、节奏等。",
    "timeline_beats": ["00:00-00:03：钩子", "00:03-00:08：冲突/铺垫", "00:08-00:15：反转/证明"],
    "audio_rhythm": "声音节奏：口播速度、BGM情绪、音效点、停顿、字幕密度。"
  },
  "copywriting_formula": {
    "title_formula": "标题公式：用变量占位，比如【人群】千万别在【场景】做【行为】。",
    "script_formula": "脚本公式：按 1/2/3/4 步写成可替换模板。",
    "golden_lines": ["可复用金句、字幕或口播句式"],
    "cta": "行动号召：关注、评论、收藏、私信、求链接、下单等。"
  },
  "market_positioning": {
    "suitable_products": "适合产品：这种套路还适合哪些关联产品？",
    "target_audience": "目标人群：性别、年龄、职业、心理状态等画像。",
    "creative_direction": "创作方向：后续适合深耕的细分赛道或风格。"
  },
  "replication_plan": {
    "pattern_name": "给这个爆款结构起一个便于归档的公式名。",
    "reusable_formula": "一句话公式：谁在什么场景遇到什么冲突，如何反转并转化。",
    "mysticism_variant": "玄学方向改编：星座、塔罗、运势、能量、民俗、梦境、情绪安慰等怎么套，但避免绝对承诺。",
    "ai_pet_variant": "AI小动物方向改编：适合什么动物角色、剧情设定、连续剧冲突和视觉风格。",
    "ai_commerce_variant": "AI带货方向改编：适合什么产品、如何自然植入、如何展示结果和信任。",
    "difficulty": "低/中/高，并说明制作难点。",
    "priority": "低/中/高，并说明是否值得优先模仿。"
  },
  "risk_control": {
    "risk_level": "低/中/高",
    "platform_risks": ["可能的平台、版权、AIGC标识、虚假宣传或迷信承诺风险"],
    "safe_rewrite": "更稳妥的表达方式。"
  },
  "viral_scores": {
    "viral_potential": 0,
    "imitation_value": 0,
    "commerce_value": 0,
    "comment_potential": 0,
    "overall": 0
  }
}

请尽量具体，优先输出“能直接进入公式库”的内容。不要编造视频里不存在的硬性数据；如果无法判断，请写“未能从视频中确认，但可推测为……”。
""".strip()


class AiVideoAnalysisAdapter(IntegrationAdapter):
    manifest = IntegrationManifest(
        id="ai-video-analysis",
        name="AI 视频拆解",
        description="选择已采集视频后创建 AI 拆解任务，后续可接入 Gemini、GPT 或本地模型。",
        repo_url="",
        tags=["ai", "video", "analysis"],
        config_schema={
            "provider": "mock | gemini | openai | local",
            "output_dir": "任务和结果保存目录",
        },
    )

    def __init__(self, config: dict[str, Any] | None = None):
        load_dotenv()
        self.config = config or {}
        self.provider = self.config.get("provider") or active_ai_provider(os.getenv("AI_VIDEO_PROVIDER") or "mock")
        self.gemini_model = self.config.get("gemini_model") or os.getenv("GEMINI_MODEL") or os.getenv("AI_MODEL", "gemini-2.5-flash")
        self.gemini_access_mode = self.config.get("gemini_access_mode") or os.getenv("GEMINI_ACCESS_MODE") or os.getenv("AI_ACCESS_MODE") or "official"
        self.analysis_prompt = self.config.get("analysis_prompt") or os.getenv("AI_VIDEO_ANALYSIS_PROMPT") or DEFAULT_ANALYSIS_PROMPT
        self.pipeline_mode = (self.config.get("pipeline_mode") or os.getenv("AI_VIDEO_PIPELINE_MODE") or "auto").lower()
        self.output_dir = Path(
            self.config.get("output_dir")
            or os.getenv("AI_VIDEO_OUTPUT_DIR")
            or DEFAULT_OUTPUT_DIR
        )

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]:
        cfg = {**self.config, **(config or {})}
        provider = cfg.get("provider") or os.getenv("AI_VIDEO_PROVIDER", self.provider)
        errors = []
        if provider == "gemini":
            access_mode = cfg.get("gemini_access_mode") or os.getenv("GEMINI_ACCESS_MODE") or os.getenv("AI_ACCESS_MODE", self.gemini_access_mode)
            if access_mode == "relay" and not (os.getenv("GEMINI_RELAY_API_KEY") or os.getenv("AI_RELAY_API_KEY")):
                errors.append("Missing GEMINI_RELAY_API_KEY")
            if access_mode != "relay" and not (os.getenv("GEMINI_API_KEY") or os.getenv("AI_NATIVE_API_KEY")):
                errors.append("Missing GEMINI_API_KEY")
        if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
            errors.append("Missing OPENAI_API_KEY")
        if provider == "local" and not os.getenv("LOCAL_VIDEO_MODEL_ENDPOINT"):
            errors.append("Missing LOCAL_VIDEO_MODEL_ENDPOINT")
        return errors

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "create_job":
            return self.create_job(payload.get("video") or {}, payload.get("provider"))
        raise ValueError(f"Unsupported AI video analysis action: {action}")

    def create_job(
        self,
        video: dict[str, Any],
        provider: str | None = None,
        job_id: str | None = None,
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        jobs_dir = self.output_dir / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)

        aweme_id = str(video.get("aweme_id") or video.get("id") or int(time.time()))
        job_id = job_id or f"video-breakdown-{aweme_id}-{int(time.time())}"
        selected_provider = provider or self.provider
        prompt = self._analysis_prompt(video)
        if progress:
            progress(10, "准备 AI 视频拆解任务")
        if selected_provider == "mock":
            if progress:
                progress(60, "生成 mock 拆解结果")
            result = self._mock_result(video)
            status = "done"
        elif selected_provider == "gemini" or self._uses_gemini_relay_provider(selected_provider):
            result = self._analysis_result(video, selected_provider=selected_provider, job_id=job_id, progress=progress, prompt=prompt)
            status = "done"
        else:
            raise RuntimeError(
                f"当前全局 AI 模型 {selected_provider} 暂不支持视频上传任务。"
                "请在配置 -> AI 模型中选择 云雾 API 或 简单中转站，并将 API 格式设为 Gemini 原生 generateContent。"
            )
        job = {
            "job_id": job_id,
            "status": status,
            "provider": selected_provider,
            "created_at": int(time.time()),
            "video": video,
            "prompt": prompt,
            "result": result,
        }

        job_path = jobs_dir / f"{job_id}.json"
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        job["job_path"] = str(job_path)
        if progress:
            progress(100, "拆解完成")
        return job

    def _analysis_result(
        self,
        video: dict[str, Any],
        *,
        selected_provider: str,
        job_id: str,
        progress: Callable[[int, str], None] | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        if self.pipeline_mode == "direct":
            return self._gemini_result(video, progress=progress, prompt=prompt)

        try:
            evidence = VideoEvidencePipeline(output_dir=self.output_dir).build(video, job_id=job_id, progress=progress)
            result = self._evidence_breakdown(video, evidence=evidence, progress=progress)
            result["analysis_mode"] = "evidence_pipeline"
            result["evidence"] = self._compact_evidence(evidence)
            return result
        except Exception as exc:
            if self.pipeline_mode == "evidence":
                raise
            if progress:
                progress(60, f"证据包流程不可用，回退直接视频分析：{type(exc).__name__}")
            result = self._gemini_result(video, progress=progress, prompt=prompt)
            result["analysis_mode"] = "direct_video_fallback"
            result["pipeline_error"] = f"{type(exc).__name__}: {exc}"
            return result

    def _evidence_breakdown(
        self,
        video: dict[str, Any],
        *,
        evidence: dict[str, Any],
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        segments = evidence.get("analysis_segments") or []
        if not segments:
            raise RuntimeError("转写结果为空，无法进行分段爆款拆解。")

        max_segments = int(os.getenv("AI_VIDEO_MAX_SEGMENTS", "18"))
        selected_segments = segments[:max_segments]
        evidence_path = Path(str(evidence.get("evidence_path") or ""))
        checkpoint_dir = (evidence_path.parent if evidence_path.parent else self.output_dir) / "segment_breakdowns"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        resume_enabled = os.getenv("AI_VIDEO_RESUME_ENABLED", "true").lower() not in {"0", "false", "no"}
        if progress:
            skipped = len(segments) - len(selected_segments)
            suffix = f"，跳过 {skipped} 个超出上限片段" if skipped > 0 else ""
            progress(60, f"准备分段 AI 拆解：{len(selected_segments)} 个片段{suffix}")
        segment_breakdowns = []
        for index, segment in enumerate(selected_segments, start=1):
            checkpoint_path = checkpoint_dir / f"{segment.get('segment_id') or index}.json"
            if resume_enabled and checkpoint_path.exists():
                try:
                    parsed = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                    segment_breakdowns.append(parsed)
                    if progress:
                        progress(60 + int(25 * index / max(1, len(selected_segments))), f"断点续跑：复用第 {index}/{len(selected_segments)} 段拆解结果")
                    continue
                except Exception:
                    if progress:
                        progress(60, f"第 {index} 段 checkpoint 读取失败，重新拆解")
            if progress:
                progress(60 + int(20 * (index - 1) / max(1, len(selected_segments))), f"提交第 {index}/{len(selected_segments)} 段给模型：{segment.get('time_range')}")
            prompt = self._segment_breakdown_prompt(video, segment)
            image_paths = self._segment_image_paths(segment)
            if progress and image_paths:
                progress(60 + int(20 * (index - 1) / max(1, len(selected_segments))), f"附带关键帧网格图：{Path(image_paths[0]).name}")
            text = self._generate_text_json(prompt, action="请求模型生成分段拆解", image_paths=image_paths)
            parsed = self._parse_segment_json(text, segment)
            parsed["checkpoint_path"] = str(checkpoint_path)
            checkpoint_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            segment_breakdowns.append(parsed)
            if progress:
                role = parsed.get("segment_role") or "未标注角色"
                progress(60 + int(25 * index / max(1, len(selected_segments))), f"第 {index}/{len(selected_segments)} 段拆解完成：{role}")

        if progress:
            progress(87, "提交全部分段结果，汇总全局爆款公式")
        if os.getenv("AI_VIDEO_HIGHLIGHT_SCREENSHOTS", "true").lower() not in {"0", "false", "no"}:
            self._extract_highlight_screenshots(evidence=evidence, segment_breakdowns=segment_breakdowns, progress=progress)
        global_checkpoint = checkpoint_dir.parent / "global_breakdown.json"
        if resume_enabled and global_checkpoint.exists():
            try:
                result = json.loads(global_checkpoint.read_text(encoding="utf-8"))
                if progress:
                    progress(92, "断点续跑：复用全局爆款公式汇总")
            except Exception:
                global_prompt = self._global_breakdown_prompt(video, evidence=evidence, segment_breakdowns=segment_breakdowns)
                global_text = self._generate_text_json(global_prompt, action="请求模型汇总全局爆款公式")
                result = self._parse_model_json(global_text)
                result["checkpoint_path"] = str(global_checkpoint)
                global_checkpoint.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            global_prompt = self._global_breakdown_prompt(video, evidence=evidence, segment_breakdowns=segment_breakdowns)
            global_text = self._generate_text_json(global_prompt, action="请求模型汇总全局爆款公式")
            result = self._parse_model_json(global_text)
            result["checkpoint_path"] = str(global_checkpoint)
            global_checkpoint.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if progress:
            progress(92, "全局爆款公式汇总完成，整理结果")
        result["segment_breakdowns"] = segment_breakdowns
        return result

    def _segment_breakdown_prompt(self, video: dict[str, Any], segment: dict[str, Any]) -> str:
        desc = video.get("desc") or video.get("title") or ""
        keyframes = [
            {"time": frame.get("time_label"), "image_path": frame.get("image_path")}
            for frame in (segment.get("keyframes") or [])
        ]
        grid = (segment.get("keyframe_grid") or {}).get("image_path") if isinstance(segment.get("keyframe_grid"), dict) else ""
        return f"""
你是短视频爆款拆解师。请只返回合法 JSON，不要返回 Markdown。

视频标题：{desc}
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
  "segment_role": "开头钩子/冲突建立/信息铺垫/证明演示/情绪爆点/带货转化/结尾收口/其他",
  "hook": "这一段如何抓注意力",
  "conflict_or_value": "这一段制造的冲突、价值或信息差",
  "emotion": "情绪触发",
  "visual_signal": "从关键帧可判断的视觉信号；无法确认则写无法确认",
  "copywriting_pattern": "可复用文案句式",
  "commerce_signal": "产品、购买、收藏、私信、信任背书等转化信号",
  "comment_trigger": "评论诱因",
  "replicable_point": "这一段最值得复刻的点",
  "highlight_screenshots": [
    {{"time": 12.5, "time_label": "00:12", "reason": "最能证明钩子、反转、产品利益点或情绪爆点的画面"}}
  ]
}}
""".strip()

    def _global_breakdown_prompt(
        self,
        video: dict[str, Any],
        *,
        evidence: dict[str, Any],
        segment_breakdowns: list[dict[str, Any]],
    ) -> str:
        desc = video.get("desc") or video.get("title") or ""
        metadata = evidence.get("metadata") or {}
        payload = {
            "metadata": metadata,
            "segment_breakdowns": segment_breakdowns,
            "transcript_excerpt": str((evidence.get("transcript") or {}).get("full_text") or "")[:12000],
        }
        return "\n\n".join(
            [
                self._clean_prompt(self.analysis_prompt).replace("{desc}", desc).replace("{author}", str(metadata.get("author") or "未知")),
                VIRAL_BREAKDOWN_GUIDE,
                "下面是已由音频转写和分段分析得到的证据包，请基于证据汇总全局爆款公式，不要编造证据中不存在的事实：",
                json.dumps(payload, ensure_ascii=False),
                JSON_RESPONSE_CONTRACT,
            ]
        )

    def _segment_image_paths(self, segment: dict[str, Any]) -> list[str]:
        grid = segment.get("keyframe_grid") or {}
        image_path = grid.get("image_path") if isinstance(grid, dict) else ""
        if image_path and Path(image_path).exists():
            return [str(image_path)]
        return []

    def _generate_text_json(self, prompt: str, *, action: str, image_paths: list[str] | None = None) -> str:
        if self._uses_gemini_relay_provider(active_ai_provider("")) or (self.gemini_access_mode or "").lower() == "relay":
            return self._generate_text_with_relay(prompt=prompt, model=self.gemini_model, action=action, image_paths=image_paths)

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("AI_NATIVE_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY in .env before using Gemini text analysis.")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Missing dependency google-genai. Run: pip install -r requirements.txt") from exc
        client = genai.Client(api_key=api_key)
        contents: list[Any] = [prompt]
        uploads = []
        if image_paths:
            for image_path in image_paths:
                try:
                    uploads.append(client.files.upload(file=str(image_path)))
                except Exception:
                    pass
        if uploads:
            contents.extend(uploads)
        response = self._generate_with_retry(
            client=client,
            model=self.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
            progress=None,
            action=action,
        )
        return response.text

    def _generate_text_with_relay(self, *, prompt: str, model: str, action: str, image_paths: list[str] | None = None) -> str:
        base_url = self._relay_base_url()
        token = self._relay_token()
        if not token:
            raise RuntimeError("Set GEMINI_RELAY_API_KEY or AI_RELAY_API_KEY before using Gemini relay.")
        url = f"{base_url}/v1beta/models/{model}:generateContent?key="
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for image_path in image_paths or []:
            path = Path(image_path)
            if not path.exists():
                continue
            mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            image_data = base64.b64encode(path.read_bytes()).decode("ascii")
            parts.append({"inline_data": {"mime_type": mime_type, "data": image_data}})
        payload = {
            "systemInstruction": {"parts": [{"text": "你是短视频爆款拆解助手。必须只返回合法 JSON。"}]},
            "contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        return self._relay_post_with_retry(url=url, payload=payload, headers=headers, progress=None, action=action)

    def _parse_segment_json(self, text: str, segment: dict[str, Any]) -> dict[str, Any]:
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
        return data

    def _extract_highlight_screenshots(
        self,
        *,
        evidence: dict[str, Any],
        segment_breakdowns: list[dict[str, Any]],
        progress: Callable[[int, str], None] | None = None,
    ) -> None:
        video_path = Path(str((evidence.get("metadata") or {}).get("video_path") or ""))
        evidence_path = Path(str(evidence.get("evidence_path") or ""))
        if not video_path.exists() or not evidence_path.parent.exists():
            return
        try:
            from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline

            pipeline = VideoEvidencePipeline(output_dir=self.output_dir)
        except Exception:
            return
        output_dir = evidence_path.parent / "highlight_screenshots"
        output_dir.mkdir(parents=True, exist_ok=True)
        total = sum(len(self._highlight_items(segment)) for segment in segment_breakdowns)
        done = 0
        for segment in segment_breakdowns:
            screenshots = []
            for item in self._highlight_items(segment):
                seconds = self._highlight_seconds(item)
                if seconds is None:
                    continue
                done += 1
                image_path = output_dir / f"{segment.get('segment_id') or 'segment'}_{int(seconds * 1000):08d}.jpg"
                if not image_path.exists() or image_path.stat().st_size == 0:
                    if progress:
                        progress(86, f"截取爆点截图 {done}/{max(1, total)}：{pipeline.format_time(seconds)}")
                    try:
                        pipeline.extract_frame(video_path, seconds, image_path)
                    except Exception:
                        continue
                screenshots.append(
                    {
                        "time": seconds,
                        "time_label": item.get("time_label") or pipeline.format_time(seconds),
                        "reason": item.get("reason") or "",
                        "image_path": str(image_path),
                    }
                )
            if screenshots:
                segment["highlight_screenshots"] = screenshots

    def _highlight_items(self, segment: dict[str, Any]) -> list[dict[str, Any]]:
        value = segment.get("highlight_screenshots") or segment.get("screenshots") or []
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    def _highlight_seconds(self, item: dict[str, Any]) -> float | None:
        value = item.get("time")
        if isinstance(value, (int, float)):
            return max(0.0, float(value))
        if isinstance(value, str):
            parts = value.strip().split(":")
            try:
                if len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                if len(parts) == 2:
                    return int(parts[0]) * 60 + float(parts[1])
                return max(0.0, float(value))
            except ValueError:
                return None
        label = item.get("time_label")
        if isinstance(label, str):
            return self._highlight_seconds({"time": label})
        return None

    def _compact_evidence(self, evidence: dict[str, Any]) -> dict[str, Any]:
        transcript = evidence.get("transcript") or {}
        return {
            "metadata": evidence.get("metadata") or {},
            "evidence_path": evidence.get("evidence_path") or "",
            "transcript_provider": transcript.get("provider") or "",
            "transcript_model": transcript.get("model") or "",
            "transcript_language": transcript.get("language") or "",
            "transcript_segments_count": len(transcript.get("segments") or []),
            "analysis_segments_count": len(evidence.get("analysis_segments") or []),
            "keyframes_count": len(evidence.get("keyframes") or []),
        }

    def _gemini_result(
        self,
        video: dict[str, Any],
        progress: Callable[[int, str], None] | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        prompt = prompt or self._analysis_prompt(video)
        access_mode = (os.getenv("GEMINI_ACCESS_MODE") or os.getenv("AI_ACCESS_MODE") or self.gemini_access_mode).lower()
        if access_mode == "relay" or self._uses_gemini_relay_provider(active_ai_provider("")):
            return self._gemini_relay_result(video, progress=progress, prompt=prompt)

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("AI_NATIVE_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY in .env before using Gemini video analysis.")

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Missing dependency google-genai. Run: pip install -r requirements.txt") from exc

        if progress:
            progress(20, "定位或下载视频文件")
        video_path = self._resolve_video_file(video)
        client = genai.Client(api_key=api_key)
        if progress:
            progress(35, "上传视频到 Gemini Files API")
        uploaded = client.files.upload(file=str(video_path))

        while getattr(uploaded, "state", None) and getattr(uploaded.state, "name", "") == "PROCESSING":
            if progress:
                progress(55, "Gemini 正在处理视频文件")
            time.sleep(2)
            uploaded = client.files.get(name=uploaded.name)

        if getattr(uploaded, "state", None) and getattr(uploaded.state, "name", "") == "FAILED":
            raise RuntimeError("Gemini file processing failed.")

        response = self._generate_with_retry(
            client=client,
            model=self.gemini_model,
            contents=[prompt, uploaded],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
            progress=progress,
            action="请求 Gemini 生成拆解结果",
        )
        if progress:
            progress(90, "解析模型返回结果")
        return self._parse_model_json(response.text)

    def _gemini_relay_result(
        self,
        video: dict[str, Any],
        progress: Callable[[int, str], None] | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        prompt = prompt or self._analysis_prompt(video)
        if not (self._relay_token()):
            raise RuntimeError("Set GEMINI_RELAY_API_KEY in .env before using Gemini relay.")
        if progress:
            progress(20, "定位或下载视频文件")
        video_path = self._resolve_video_file(video)
        if progress:
            progress(45, "准备 Gemini 中转站视频数据")
        text = self._generate_with_relay(
            video_path=video_path,
            prompt=prompt,
            model=self.gemini_model,
            progress=progress,
            action="请求 Gemini 中转站生成拆解结果",
        )
        if progress:
            progress(90, "解析模型返回结果")
        return self._parse_model_json(text)

    def _generate_with_relay(
        self,
        *,
        video_path: Path,
        prompt: str,
        model: str,
        progress: Callable[[int, str], None] | None,
        action: str,
        system_instruction: str | None = None,
    ) -> str:
        base_url = self._relay_base_url()
        token = self._relay_token()
        mime_type = mimetypes.guess_type(video_path.name)[0] or "video/mp4"
        video_data = base64.b64encode(video_path.read_bytes()).decode("ascii")
        url = f"{base_url}/v1beta/models/{model}:generateContent?key="
        payload = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": system_instruction
                        or "你是短视频商业拆解助手。必须严格按用户要求分析视频，并只返回合法 JSON。"
                    }
                ]
            },
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime_type, "data": video_data}},
                    ]
                }
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        return self._relay_post_with_retry(url=url, payload=payload, headers=headers, progress=progress, action=action)

    def _uses_gemini_relay_provider(self, provider: str) -> bool:
        if provider == "simple_relay":
            return os.getenv("SIMPLE_RELAY_API_FORMAT", "gemini_generate_content") == "gemini_generate_content"
        if provider == "yunwu":
            return os.getenv("YUNWU_API_FORMAT", "gemini_generate_content") == "gemini_generate_content"
        return False

    def _relay_base_url(self) -> str:
        if active_ai_provider("") == "yunwu":
            return (os.getenv("YUNWU_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://yunwu.ai").rstrip("/")
        if self._uses_gemini_relay_provider(active_ai_provider("")):
            return (os.getenv("SIMPLE_RELAY_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://jeniya.top").rstrip("/")
        return (os.getenv("GEMINI_RELAY_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://jeniya.top").rstrip("/")

    def _relay_token(self) -> str:
        if active_ai_provider("") == "yunwu":
            return os.getenv("YUNWU_API_KEY") or os.getenv("AI_RELAY_API_KEY") or ""
        if self._uses_gemini_relay_provider(active_ai_provider("")):
            return os.getenv("SIMPLE_RELAY_API_KEY") or os.getenv("AI_RELAY_API_KEY") or ""
        return os.getenv("GEMINI_RELAY_API_KEY") or os.getenv("AI_RELAY_API_KEY") or ""

    def _relay_post_with_retry(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        progress: Callable[[int, str], None] | None,
        action: str,
    ) -> str:
        delays = [10, 20, 40]
        last_error: Exception | None = None
        for attempt in range(len(delays) + 1):
            if progress:
                progress(75, action if attempt == 0 else f"Gemini 中转站第 {attempt + 1} 次重试")
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=180)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < len(delays):
                    last_error = RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
                    time.sleep(delays[attempt])
                    continue
                response.raise_for_status()
                return self._extract_relay_text(response.json())
            except Exception as exc:
                last_error = exc
                if attempt >= len(delays):
                    break
                time.sleep(delays[attempt])
        raise RuntimeError(f"Gemini relay request failed: {last_error}") from last_error

    def _extract_relay_text(self, data: dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        if candidates:
            parts = ((candidates[0].get("content") or {}).get("parts")) or []
            texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
            text = "\n".join(part for part in texts if part)
            if text:
                return text
        if data.get("text"):
            return str(data["text"])
        raise RuntimeError(f"Gemini relay returned no text: {json.dumps(data, ensure_ascii=False)[:1000]}")

    def _generate_with_retry(
        self,
        *,
        client: Any,
        model: str,
        contents: list[Any],
        config: Any,
        progress: Callable[[int, str], None] | None,
        action: str,
    ) -> Any:
        delays = [10, 20, 40]
        last_error: Exception | None = None
        for attempt in range(len(delays) + 1):
            if progress:
                progress(75, action if attempt == 0 else f"Gemini 繁忙，正在第 {attempt + 1} 次重试")
            try:
                return client.models.generate_content(model=model, contents=contents, config=config)
            except Exception as exc:
                last_error = exc
                text = str(exc)
                retryable = "503" in text or "429" in text or "UNAVAILABLE" in text
                if not retryable or attempt >= len(delays):
                    break
                time.sleep(delays[attempt])
        raise RuntimeError(f"Gemini 暂时不可用或请求过载，请稍后重试。原始错误：{last_error}") from last_error

    def _resolve_video_file(self, video: dict[str, Any]) -> Path:
        for key in ["local_path", "path", "file_path"]:
            value = video.get(key)
            if value and Path(value).exists():
                return Path(value)

        url = video.get("source_video_url") or video.get("video_url")
        if not url:
            raise RuntimeError("No local video file or source_video_url found for Gemini upload.")

        media_dir = self.output_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        aweme_id = str(video.get("aweme_id") or video.get("id") or int(time.time()))
        target = media_dir / f"{aweme_id}.mp4"
        if target.exists() and target.stat().st_size > 0:
            return target

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Referer": (video.get("share_info") or {}).get("share_url") or "https://www.douyin.com/",
            "Accept": "*/*",
        }
        response = requests.get(url, headers=headers, stream=True, timeout=120)
        response.raise_for_status()
        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if chunk:
                    file.write(chunk)
        return target

    def _analysis_prompt(self, video: dict[str, Any]) -> str:
        desc = video.get("desc") or video.get("title") or ""
        author = video.get("author") or {}
        author_name = author.get("nickname") if isinstance(author, dict) else author
        prompt = self._clean_prompt(self.analysis_prompt)
        prompt = prompt.replace("{desc}", desc).replace("{author}", author_name or "未知")
        metadata = {
            "video_title": desc,
            "author": author_name or "未知",
            "aweme_id": video.get("aweme_id") or video.get("id") or "",
        }
        return "\n\n".join(
            [
                prompt,
                f"视频元数据：{json.dumps(metadata, ensure_ascii=False)}",
                VIRAL_BREAKDOWN_GUIDE,
                JSON_RESPONSE_CONTRACT,
            ]
        )

    def _clean_prompt(self, prompt: str) -> str:
        cleaned = str(prompt or "").strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
            cleaned = cleaned[1:-1]
        cleaned = cleaned.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
        return cleaned.strip() or DEFAULT_ANALYSIS_PROMPT

    def _parse_model_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            data = {"summary": cleaned}
        if not isinstance(data, dict):
            data = {"summary": cleaned}

        return self._normalize_analysis_result(data, raw_text=cleaned)

    def _normalize_analysis_result(self, data: dict[str, Any], raw_text: str = "") -> dict[str, Any]:
        summary = self._first_text(data, ["summary", "摘要", "视频摘要", "一句话摘要"])
        content_identity = self._first_dict(data, ["content_identity", "内容定位", "赛道判断"])
        core_hook = self._first_dict(data, ["core_hook", "核心钩子", "核心勾子"])
        need_context = self._first_dict(data, ["need_context", "需求与场景", "需求场景"])
        product_power = self._first_dict(data, ["product_power", "产品表现", "产品力", "产品价值"])
        visual_structure = self._first_dict(data, ["visual_structure", "视觉与结构", "视觉结构"])
        copywriting_formula = self._first_dict(data, ["copywriting_formula", "文案公式", "脚本公式"])
        market_positioning = self._first_dict(data, ["market_positioning", "商业定位", "市场定位"])
        replication_plan = self._first_dict(data, ["replication_plan", "复刻计划", "模仿计划"])
        risk_control = self._first_dict(data, ["risk_control", "风险控制", "合规风险"])
        viral_scores = self._first_dict(data, ["viral_scores", "爆款评分", "评分"])

        return {
            "summary": summary,
            "content_identity": {
                "track": self._first_text(content_identity, ["track", "内容赛道", "赛道"]),
                "niche_fit": self._first_text(content_identity, ["niche_fit", "赛道适配", "适配方向"]),
                "account_persona": self._first_text(content_identity, ["account_persona", "账号人设", "人设"]),
            },
            "core_hook": {
                "opening_3s": self._first_text(core_hook, ["opening_3s", "开头3秒钩子", "开头3秒勾子", "开头3秒狗子"])
                or self._join_old(data.get("hooks")),
                "curiosity_gap": self._first_text(core_hook, ["curiosity_gap", "信息差", "悬念"]),
                "emotional_trigger": self._first_text(core_hook, ["emotional_trigger", "情绪触发", "情绪"]),
                "comment_bait": self._first_text(core_hook, ["comment_bait", "评论诱因", "评论钩子"]),
            },
            "need_context": {
                "pain_point": self._first_text(need_context, ["pain_point", "痛点定位", "痛点"]),
                "application_scene": self._first_text(need_context, ["application_scene", "应用场景", "场景"]),
                "hidden_desire": self._first_text(need_context, ["hidden_desire", "隐性欲望", "深层欲望"]),
            },
            "product_power": {
                "core_benefit": self._first_text(product_power, ["core_benefit", "功效提炼", "核心功效", "核心利益点"]),
                "trigger_moment": self._first_text(product_power, ["trigger_moment", "激励点", "触发点", "转化瞬间"]),
                "trust_builder": self._first_text(product_power, ["trust_builder", "信任来源", "信任背书"]),
                "product_role": self._first_text(product_power, ["product_role", "产品角色", "产品定位"]),
            },
            "visual_structure": {
                "shot_structure": self._first_text(visual_structure, ["shot_structure", "镜头结构", "结构"])
                or self._join_old(data.get("timeline")),
                "reusable_elements": self._first_text(visual_structure, ["reusable_elements", "可复用元素", "可服用元素"])
                or self._join_old(data.get("visuals")),
                "timeline_beats": self._first_list_text(visual_structure, ["timeline_beats", "时间线", "节奏点"]),
                "audio_rhythm": self._first_text(visual_structure, ["audio_rhythm", "声音节奏", "音频节奏"]),
            },
            "copywriting_formula": {
                "title_formula": self._first_text(copywriting_formula, ["title_formula", "标题公式"]),
                "script_formula": self._first_text(copywriting_formula, ["script_formula", "脚本公式"]),
                "golden_lines": self._first_list_text(copywriting_formula, ["golden_lines", "金句", "可复用句式"]),
                "cta": self._first_text(copywriting_formula, ["cta", "行动号召", "转化口令"]),
            },
            "market_positioning": {
                "suitable_products": self._first_text(market_positioning, ["suitable_products", "适合产品", "适配产品"]),
                "target_audience": self._first_text(market_positioning, ["target_audience", "目标人群", "目标用户"]),
                "creative_direction": self._first_text(market_positioning, ["creative_direction", "创作方向", "后续方向"])
                or self._join_old(data.get("rewrite_prompts")),
            },
            "replication_plan": {
                "pattern_name": self._first_text(replication_plan, ["pattern_name", "公式名", "模式名"]),
                "reusable_formula": self._first_text(replication_plan, ["reusable_formula", "可复刻公式", "复用公式"]),
                "mysticism_variant": self._first_text(replication_plan, ["mysticism_variant", "玄学方向", "玄学改编"]),
                "ai_pet_variant": self._first_text(replication_plan, ["ai_pet_variant", "AI小动物方向", "小动物改编"]),
                "ai_commerce_variant": self._first_text(replication_plan, ["ai_commerce_variant", "AI带货方向", "带货改编"]),
                "difficulty": self._first_text(replication_plan, ["difficulty", "制作难度", "难度"]),
                "priority": self._first_text(replication_plan, ["priority", "优先级", "模仿优先级"]),
            },
            "risk_control": {
                "risk_level": self._first_text(risk_control, ["risk_level", "风险等级"]),
                "platform_risks": self._first_list_text(risk_control, ["platform_risks", "平台风险", "风险点"]),
                "safe_rewrite": self._first_text(risk_control, ["safe_rewrite", "安全改写", "合规表达"]),
            },
            "viral_scores": {
                "viral_potential": self._first_number(viral_scores, ["viral_potential", "爆款潜力"]),
                "imitation_value": self._first_number(viral_scores, ["imitation_value", "模仿价值"]),
                "commerce_value": self._first_number(viral_scores, ["commerce_value", "商业价值"]),
                "comment_potential": self._first_number(viral_scores, ["comment_potential", "评论潜力"]),
                "overall": self._first_number(viral_scores, ["overall", "综合评分"]),
            },
            "raw_model_json": data,
            "raw_model_text": raw_text,
        }

    def _first_dict(self, data: dict[str, Any], keys: list[str]) -> dict[str, Any]:
        for key in keys:
            value = data.get(key)
            if isinstance(value, dict):
                return value
        return {}

    def _first_text(self, data: dict[str, Any], keys: list[str]) -> str:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str):
                return value.strip()
            if isinstance(value, list):
                return self._join_old(value)
            if value is not None and not isinstance(value, dict):
                return str(value)
        return ""

    def _first_list_text(self, data: dict[str, Any], keys: list[str]) -> str:
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return self._join_old(value)
            if isinstance(value, str):
                return value.strip()
        return ""

    def _first_number(self, data: dict[str, Any], keys: list[str]) -> int:
        for key in keys:
            value = data.get(key)
            if isinstance(value, (int, float)):
                return max(0, min(100, int(value)))
            if isinstance(value, str):
                match = re.search(r"\d+", value)
                if match:
                    return max(0, min(100, int(match.group(0))))
        return 0

    def _join_old(self, value: Any) -> str:
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    parts.append(" ".join(str(part) for part in item.values()))
                else:
                    parts.append(str(item))
            return "；".join(parts)
        return str(value or "")

    def _mock_result(self, video: dict[str, Any]) -> dict[str, Any]:
        desc = video.get("desc") or video.get("title") or "未命名视频"
        author = video.get("author") or {}
        author_name = author.get("nickname") if isinstance(author, dict) else author
        return {
            "summary": f"待接入真实模型。当前已接收视频《{desc}》，作者：{author_name or '未知'}；真实模型会输出爆款公式、三赛道改编和风险控制。",
            "content_identity": {
                "track": "待模型识别：玄学/AI小动物/AI带货/泛娱乐/种草/其他。",
                "niche_fit": "判断该视频是否适合迁移到玄学、AI小动物、AI带货，并说明迁移原因。",
                "account_persona": "提炼账号人设、叙事视角或可复制角色。",
            },
            "core_hook": {
                "opening_3s": "识别开头 3 秒使用的是视觉冲击、悬念提问、利益承诺还是情绪共鸣。",
                "curiosity_gap": "拆出信息差、悬念、反常识或未完成感。",
                "emotional_trigger": "识别焦虑、爽感、治愈、猎奇、共鸣、占便宜或恐惧错过。",
                "comment_bait": "提取会激发评论、反驳、求链接、求后续或艾特别人的点。",
            },
            "need_context": {
                "pain_point": "定位用户在生活或工作中的具体痛点与焦虑。",
                "application_scene": "描述视频发生的具体场景，以及用户为什么会在该场景下产生需求。",
                "hidden_desire": "挖掘用户真正想获得的安全感、掌控感、陪伴感、好运、效率或省钱。",
            },
            "product_power": {
                "core_benefit": "提炼产品或方法提供的核心功能、效率提升或情绪价值。",
                "trigger_moment": "找出让观众产生必须买、必须试、必须收藏的关键瞬间。",
                "trust_builder": "识别对比、实测、前后变化、生活细节、评论反馈等信任来源。",
                "product_role": "判断产品是主角、解决方案、剧情道具、仪式感载体、陪伴物还是隐形植入。",
            },
            "visual_structure": {
                "shot_structure": "按痛点切入 -> 解决方案 -> 效果展示 -> 信任背书 -> 行动号召拆解镜头流。",
                "reusable_elements": "提取可复刻的转场、BGM、花字、特效、拍摄角度和节奏。",
                "timeline_beats": "00:00-00:03：钩子；00:03-00:08：冲突/铺垫；00:08-00:15：反转/证明。",
                "audio_rhythm": "拆出口播速度、BGM情绪、音效点、停顿和字幕密度。",
            },
            "copywriting_formula": {
                "title_formula": "用变量沉淀标题公式，例如：【人群】千万别在【场景】做【行为】。",
                "script_formula": "把脚本拆成可替换模板：钩子 -> 痛点 -> 反转 -> 证明 -> 行动。",
                "golden_lines": "提取可复用金句、字幕或口播句式。",
                "cta": "识别关注、评论、收藏、私信、求链接、下单等行动号召。",
            },
            "market_positioning": {
                "suitable_products": "列出适合套用该视频套路的关联产品或服务。",
                "target_audience": "描述目标人群的性别、年龄、职业、心理状态与消费动机。",
                "creative_direction": "建议后续可深耕的细分内容赛道和创作风格。",
            },
            "replication_plan": {
                "pattern_name": "为该爆款结构命名，方便归档到公式库。",
                "reusable_formula": "总结成：谁在什么场景遇到什么冲突，如何反转并转化。",
                "mysticism_variant": "迁移到玄学方向，但避免绝对化财富、情感、疗效承诺。",
                "ai_pet_variant": "迁移到 AI 小动物方向，设计动物角色、连续剧情和反差冲突。",
                "ai_commerce_variant": "迁移到 AI 带货方向，匹配产品、植入场景、证明方式和转化口令。",
                "difficulty": "低/中/高，说明制作难点。",
                "priority": "低/中/高，说明是否值得优先模仿。",
            },
            "risk_control": {
                "risk_level": "待模型判断。",
                "platform_risks": "识别 AIGC 标识、版权、虚假宣传、迷信承诺、疗效承诺等风险。",
                "safe_rewrite": "输出更稳妥的平台表达方式。",
            },
            "viral_scores": {
                "viral_potential": 0,
                "imitation_value": 0,
                "commerce_value": 0,
                "comment_potential": 0,
                "overall": 0,
            },
        }

    def _provider_placeholder(self, video: dict[str, Any], provider: str) -> dict[str, Any]:
        return {
            "summary": f"{provider} provider 已预留，等待接入真实上传和模型调用逻辑。",
            "timeline": [],
            "hooks": [],
            "visuals": [],
            "audio": [],
            "copywriting": [],
            "keywords": [],
            "rewrite_prompts": [],
        }
