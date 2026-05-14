from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from backend.app.ai_provider_state import active_ai_provider
from integrations.ai_video_analysis.adapter import AiVideoAnalysisAdapter
from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline
from integrations.base import IntegrationManifest


DEFAULT_OUTPUT_DIR = Path("data/runtime/ai_production_reverse")
PRODUCTION_REVERSE_CONTRACT = """
你是短视频制作方式反推助手。目标不是分析它为什么火，也不是只给生成提示词，而是尽可能还原“这条视频大概率是怎么做出来的”。

请严格遵守：
1. 只返回合法 JSON，不要返回 Markdown 或解释文本。
2. 字段名必须保持英文，字段值使用中文。
3. 不确定的地方明确写“无法确认”或“推测”，不要编造。
4. 重点拆解素材来源、剪辑方式、字幕包装、贴纸覆盖、转场、滤镜、音频构成、工具痕迹和复做流程。
5. 如果画面像剪映 / CapCut / 模板库 / AI 生图后做图生视频 / 首帧视频化 / 录屏 / 截图 / 素材库，请明确写成“推测”和对应依据。
6. 时间线拆解里尽量细化到每一段使用了什么素材、什么包装、什么动效、可能需要几层轨道。
""".strip()

DEFAULT_PRODUCTION_PROMPT = """
请分析这个视频是如何被制作出来的，并且只返回 JSON，不要返回 Markdown。
视频标题或描述：{desc}
作者：{author}

请尽量根据转写文本、关键帧、关键帧网格和时间线反推视频制作方式，尤其要回答：
1. 每个时间段用了哪些素材，分别更像实拍、口播、素材库、录屏、截图、AI 生图、AI 视频、模板包装还是混剪。
2. 每个时间段里字幕样式、字幕动效、贴纸样式、覆盖布局、转场、滤镜、调色、卡点是怎么处理的。
3. 哪些地方像剪映、CapCut、模板库默认效果，哪些地方像人工手搓，哪些地方像 AI 生成。
4. 音频更像真人口播、AI 配音、平台原声、BGM、音效还是混合方式，并说明节奏关系。
5. 最终给出复做路径：哪些步骤可交给 AI，哪些步骤仍然需要人工剪辑和校对。

输出字段必须保持英文，返回结构如下：
{
  "summary": "一句话概括这条视频的大致制作方式",
  "production_overview": {
    "content_type": "内容类型",
    "main_workflow": "大致制作主流程",
    "estimated_tools": ["可能用到的工具"],
    "difficulty": "低/中/高",
    "source_mix": ["整片素材构成"],
    "tool_signatures": ["明显的工具或软件痕迹"],
    "template_signature": "是否像套模板，以及原因",
    "automation_level": "自动化程度判断",
    "tool_likelihoods": [
      {"name": "剪映", "score": 0, "reason": "依据"},
      {"name": "CapCut", "score": 0, "reason": "依据"}
    ],
    "source_likelihoods": [
      {"name": "素材库", "score": 0, "reason": "依据"},
      {"name": "AI 生图后视频化", "score": 0, "reason": "依据"}
    ]
  },
  "timeline_breakdown": [
    {
      "time_range": "00:00-00:03",
      "segment_role": "开场钩子/铺垫/主体/转折/收尾",
      "visual_source_type": "实拍/口播/素材库/截图录屏/AI生图/AI视频/模板动效/混剪/无法确认",
      "material_elements": ["人物", "商品", "背景", "界面截图", "字幕条"],
      "source_provenance": ["更具体的来源推测"],
      "editing_actions": ["快切", "放大", "卡点"],
      "transition": "硬切/叠化/白闪/缩放转场/遮罩/无明显转场",
      "transition_confidence": "高/中/低",
      "filter_or_grade": "滤镜或调色判断",
      "filter_strength": "弱/中/强",
      "stickers_overlays": ["箭头", "emoji", "高亮框"],
      "sticker_style": "贴纸样式判断",
      "overlay_layout": "覆盖布局判断",
      "onscreen_text": ["标题", "标语", "重点词", "字幕"],
      "subtitle_style": "字幕风格",
      "subtitle_animation": "字幕动效",
      "camera_movement_guess": "镜头运动推测",
      "track_layer_guess": ["可能的轨道层级"],
      "sync_points": ["卡点、字卡或音画同步点"],
      "audio_guess": ["AI配音", "BGM", "点击音效"],
      "generation_guess": ["可能的生成或制作方式"],
      "tool_signatures": ["像剪映或 CapCut 的信号"],
      "template_signature": "模板痕迹",
      "tool_likelihoods": [
        {"name": "剪映", "score": 0, "reason": "依据"}
      ],
      "source_likelihoods": [
        {"name": "实拍", "score": 0, "reason": "依据"}
      ],
      "confidence": "高/中/低",
      "evidence": ["判断依据1", "判断依据2"],
      "notes": "补充说明"
    }
  ],
  "asset_inventory": {
    "video_materials": ["视频素材类型或来源猜测"],
    "image_materials": ["图片素材类型或来源猜测"],
    "audio_materials": ["音频素材类型或来源猜测"],
    "graphics_and_stickers": ["贴纸、遮罩、边框、图形元素"],
    "text_elements": ["标题、口播字幕、价格信息、CTA"],
    "source_provenance": ["整片层面的素材来源判断"]
  },
  "evidence_media": {
    "segment_count": 0,
    "keyframe_grid_count": 0,
    "keyframe_count": 0,
    "highlight_screenshot_count": 0
  },
  "editing_style": {
    "pace": "快节奏/中节奏/慢节奏",
    "shot_pattern": "镜头切换规律",
    "subtitle_style": "字幕风格",
    "subtitle_animation": "字幕动效风格",
    "transition_style": "转场风格",
    "sticker_style": "贴纸风格",
    "overlay_layout": "覆盖布局风格",
    "packaging_style": "整体包装风格",
    "camera_motion_pattern": "镜头运动模式",
    "rhythm_sync_style": "卡点和音画同步方式"
  },
  "audio_analysis": {
    "voice_type": "真人口播/AI配音/原声/无法确认",
    "voice_character": "声线和播报感觉",
    "bgm_type": "BGM 风格",
    "sfx_type": ["音效类型"],
    "mixing_guess": "人声、BGM、音效的大致混音关系",
    "beat_sync_style": "音频和剪辑节奏关系"
  },
  "reproduction_plan": {
    "minimum_assets_needed": ["最少需要准备哪些素材"],
    "recommended_production_steps": ["建议复做步骤"],
    "can_be_generated_by_ai": ["哪些部分适合交给 AI"],
    "need_manual_editing": ["哪些部分更适合手工剪辑"],
    "likely_toolchain": ["更像的生产工具链"],
    "quality_control_points": ["复做时需要人工校对的关键点"]
  }
}
""".strip()


class AiProductionReverseAdapter(AiVideoAnalysisAdapter):
    manifest = IntegrationManifest(
        id="ai-production-reverse",
        name="AI 制作方式反推",
        description="从已采集视频反推素材来源、剪辑方式、包装元素、音频构成和复做流程。",
        repo_url="",
        tags=["ai", "video", "production"],
        config_schema={
            "provider": "gemini",
            "output_dir": "任务和结果保存目录",
            "production_prompt": "制作方式反推提示词模板",
        },
    )

    def __init__(self, config: dict[str, Any] | None = None):
        load_dotenv()
        super().__init__(config)
        self.config = config or {}
        self.provider = self.config.get("provider") or active_ai_provider("mock")
        self.output_dir = Path(
            self.config.get("output_dir")
            or os.getenv("AI_PRODUCTION_REVERSE_OUTPUT_DIR")
            or DEFAULT_OUTPUT_DIR
        )
        self.production_prompt = (
            self.config.get("production_prompt")
            or os.getenv("AI_PRODUCTION_REVERSE_PROMPT")
            or DEFAULT_PRODUCTION_PROMPT
        )
        self.pipeline_mode = (
            self.config.get("pipeline_mode")
            or os.getenv("AI_PRODUCTION_REVERSE_PIPELINE_MODE")
            or "evidence"
        ).lower()

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "create_job":
            return self.create_job(payload.get("video") or {}, payload.get("provider"))
        raise ValueError(f"Unsupported AI production reverse action: {action}")

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
        job_id = job_id or f"production-reverse-{aweme_id}-{int(time.time())}"
        selected_provider = provider or self.provider
        prompt = self._analysis_prompt(video)

        if progress:
            progress(10, "准备 AI 制作方式反推任务")

        if selected_provider == "gemini" or self._uses_gemini_relay_provider(selected_provider):
            result = self._production_result(video, job_id=job_id, progress=progress, prompt=prompt)
            status = "done"
        else:
            raise RuntimeError(
                f"当前全局 AI 模型 {selected_provider} 暂不支持视频制作方式反推。"
                "请在配置 -> AI 模型里选择 Gemini 原生或 Gemini 原生格式中转站。"
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
            progress(100, "制作方式反推完成")
        return job

    def _production_result(
        self,
        video: dict[str, Any],
        *,
        job_id: str,
        progress: Callable[[int, str], None] | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        if self.pipeline_mode == "direct":
            return self._gemini_result(video, progress=progress, prompt=prompt)

        try:
            if progress:
                progress(15, "启动制作方式反推证据管线")
            evidence = VideoEvidencePipeline(output_dir=self.output_dir).build(video, job_id=job_id, progress=progress)
            result = self._evidence_production_reverse(video, evidence=evidence, progress=progress)
            result["production_mode"] = "evidence_pipeline"
            result["evidence"] = self._compact_evidence(evidence)
            return result
        except Exception as exc:
            if self.pipeline_mode == "evidence":
                raise
            if progress:
                progress(60, f"证据管线不可用，回退整段视频反推：{type(exc).__name__}")
            result = self._gemini_result(video, progress=progress, prompt=prompt)
            result["production_mode"] = "direct_video_fallback"
            result["pipeline_error"] = f"{type(exc).__name__}: {exc}"
            return result

    def _evidence_production_reverse(
        self,
        video: dict[str, Any],
        *,
        evidence: dict[str, Any],
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        segments = evidence.get("analysis_segments") or []
        if not segments:
            raise RuntimeError("转写结果为空，无法进行制作方式反推。")

        max_segments = int(os.getenv("AI_PRODUCTION_REVERSE_MAX_SEGMENTS") or os.getenv("AI_VIDEO_MAX_SEGMENTS", "18"))
        selected_segments = segments[:max_segments]
        evidence_path = Path(str(evidence.get("evidence_path") or ""))
        base_dir = evidence_path.parent if evidence_path.parent else self.output_dir
        checkpoint_dir = base_dir / "production_reverse_segments"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        resume_enabled = os.getenv("AI_VIDEO_RESUME_ENABLED", "true").lower() not in {"0", "false", "no"}

        if progress:
            skipped = len(segments) - len(selected_segments)
            suffix = f"，跳过 {skipped} 个超出上限片段" if skipped > 0 else ""
            progress(60, f"准备逐段反推制作方式：{len(selected_segments)} 个片段{suffix}")

        segment_results: list[dict[str, Any]] = []
        total_segments = max(1, len(selected_segments))
        for index, segment in enumerate(selected_segments, start=1):
            checkpoint_path = checkpoint_dir / f"{segment.get('segment_id') or index}.json"
            if resume_enabled and checkpoint_path.exists():
                try:
                    parsed = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                    segment_results.append(self._normalize_timeline_item(parsed, index))
                    if progress:
                        progress(
                            60 + int(24 * index / total_segments),
                            f"断点续跑：复用第 {index}/{len(selected_segments)} 段制作方式反推",
                        )
                    continue
                except Exception:
                    if progress:
                        progress(60, f"第 {index} 段 checkpoint 读取失败，重新分析")

            prompt = self._segment_production_prompt(video, segment)
            image_paths = self._segment_image_paths(segment)
            if progress:
                message = f"提交第 {index}/{len(selected_segments)} 段制作方式反推：{segment.get('time_range')}"
                if image_paths:
                    message += f"，附带 {Path(image_paths[0]).name}"
                progress(60 + int(18 * (index - 1) / total_segments), message)

            text = self._generate_text_json(prompt, action="请求模型分析片段制作方式", image_paths=image_paths)
            parsed = self._parse_segment_production_json(text, segment)
            parsed["checkpoint_path"] = str(checkpoint_path)
            checkpoint_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            segment_results.append(parsed)

            if progress:
                progress(60 + int(24 * index / total_segments), f"第 {index}/{len(selected_segments)} 段制作方式反推完成")

        global_checkpoint = base_dir / "global_production_reverse.json"
        if resume_enabled and global_checkpoint.exists():
            try:
                result = json.loads(global_checkpoint.read_text(encoding="utf-8"))
                if progress:
                    progress(90, "断点续跑：复用整片制作方式汇总")
            except Exception:
                result = self._global_production_reverse(video, evidence=evidence, segment_results=segment_results)
                result["checkpoint_path"] = str(global_checkpoint)
                global_checkpoint.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            if progress:
                progress(88, "汇总整片素材、剪辑方式和复做方案")
            result = self._global_production_reverse(video, evidence=evidence, segment_results=segment_results)
            result["checkpoint_path"] = str(global_checkpoint)
            global_checkpoint.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        normalized = self._normalize_production_result(result, raw_text=json.dumps(result, ensure_ascii=False))
        normalized_segments = []
        for index, item in enumerate(segment_results, start=1):
            normalized_item = self._normalize_timeline_item(item, index)
            normalized_segments.append(
                self._attach_segment_evidence(
                    normalized_item,
                    self._find_segment_by_id(segments, normalized_item.get("segment_id")),
                )
            )
        normalized["segment_production_breakdowns"] = normalized_segments
        normalized["timeline_breakdown"] = self._merge_timeline_with_segments(
            normalized.get("timeline_breakdown") or [],
            normalized_segments,
        )
        normalized["evidence_media"] = self._build_evidence_media_summary(normalized["timeline_breakdown"])
        if progress:
            progress(94, "制作方式反推整理完成")
        return normalized

    def _global_production_reverse(
        self,
        video: dict[str, Any],
        *,
        evidence: dict[str, Any],
        segment_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {
            "video_title": video.get("desc") or video.get("title") or "",
            "transcript_excerpt": str((evidence.get("transcript") or {}).get("full_text") or "")[:12000],
            "evidence_summary": self._compact_evidence(evidence),
            "segment_production_breakdowns": segment_results,
        }
        prompt = "\n\n".join(
            [
                self._analysis_prompt(video),
                "下面是基于转写、关键帧和关键帧网格逐段得到的制作方式判断。请合并成整片制作方式反推报告，统一时间线和表述，不要编造证据之外的确定性结论。",
                "请重点补强：素材来源推测、字幕/贴纸/滤镜/转场风格、像剪映或 CapCut 的工具痕迹、是否像模板化生产、以及哪些步骤更适合 AI 自动化。",
                json.dumps(payload, ensure_ascii=False),
                PRODUCTION_REVERSE_CONTRACT,
            ]
        )
        text = self._generate_text_json(prompt, action="请求模型汇总整片制作方式")
        return self._parse_model_json(text)

    def _segment_production_prompt(self, video: dict[str, Any], segment: dict[str, Any]) -> str:
        desc = video.get("desc") or video.get("title") or ""
        keyframes = [
            {"time": frame.get("time_label"), "image_path": frame.get("image_path")}
            for frame in (segment.get("keyframes") or [])
        ]
        grid = (segment.get("keyframe_grid") or {}).get("image_path") if isinstance(segment.get("keyframe_grid"), dict) else ""
        transcript = str(segment.get("transcript") or "")[:7000]
        return f"""
你是短视频制作方式反推师。请只返回合法 JSON，不要输出 Markdown。
视频标题：{desc}
当前片段：{segment.get("time_range")}
片段转写：{transcript}

关键帧索引：
{json.dumps(keyframes, ensure_ascii=False)}

关键帧网格图：{grid or "无"}

请基于这段转写和关键帧，判断它大概率是怎么做出来的。不确定的地方明确写“无法确认”或“推测”。
重点观察：
1. 这段到底更像实拍、口播、素材库、录屏、截图、AI 生图、AI 视频、首帧视频化还是模板包装。
2. 字幕是否像剪映 / CapCut 默认样式，是否有描边大字、底条字幕、关键词高亮、逐字出现、弹入弹出等动效。
3. 是否出现箭头、emoji、高亮框、贴纸、边框、遮罩、价格签、按钮条等覆盖层，它们的布局是否模板化。
4. 转场是硬切、白闪、缩放、遮罩还是卡点切换，并给出信心。
5. 滤镜、调色、镜头运动、卡点、BGM、音效和音画同步方式。
6. 是否能看出像剪映、CapCut、模板库、素材网站、AI 图生视频等明显工具痕迹。
7. 推测这一段至少需要几层轨道，例如主画面、字幕、贴纸、音效、BGM。

返回 JSON：
{{
  "segment_id": "{segment.get("segment_id")}",
  "time_range": "{segment.get("time_range")}",
  "segment_role": "开场钩子/铺垫/主体/转折/收尾/无法确认",
  "visual_source_type": "实拍/口播/素材库/截图录屏/AI生图/AI视频/模板动效/混剪/无法确认",
  "material_elements": ["这一段画面里可见的素材元素"],
  "source_provenance": ["更具体的来源推测"],
  "editing_actions": ["快切/停顿/放大/卡点/速度变化等"],
  "transition": "转场方式",
  "transition_confidence": "高/中/低",
  "filter_or_grade": "滤镜、调色或画面风格判断",
  "filter_strength": "弱/中/强/无法确认",
  "stickers_overlays": ["箭头/emoji/高亮框/边框等覆盖元素"],
  "sticker_style": "贴纸样式判断",
  "overlay_layout": "覆盖布局判断",
  "onscreen_text": ["标题/标语/重点词/字幕"],
  "subtitle_style": "字幕风格",
  "subtitle_animation": "字幕动效",
  "camera_movement_guess": "镜头运动推测",
  "track_layer_guess": ["可能的轨道层级"],
  "sync_points": ["音画同步、字卡同步或卡点说明"],
  "audio_guess": ["真人口播/AI配音/BGM/音效/环境音等判断"],
  "generation_guess": ["可能使用的生成或制作方式"],
  "tool_signatures": ["像剪映/CapCut/模板库/AI 生成的工具信号"],
  "template_signature": "模板痕迹",
  "confidence": "高/中/低",
  "evidence": ["判断依据，必须基于转写、关键帧或画面特征"],
  "notes": "补充说明"
}}
""".strip()

    def _parse_segment_production_json(self, text: str, segment: dict[str, Any]) -> dict[str, Any]:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            data = {"notes": cleaned}
        if not isinstance(data, dict):
            data = {"notes": cleaned}
        data.setdefault("segment_id", segment.get("segment_id"))
        data.setdefault("time_range", segment.get("time_range"))
        return self._normalize_timeline_item(data, 0)

    def _analysis_prompt(self, video: dict[str, Any]) -> str:
        desc = video.get("desc") or video.get("title") or ""
        author = video.get("author") or {}
        author_name = author.get("nickname") if isinstance(author, dict) else author
        prompt = self._clean_prompt(self.production_prompt)
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
                PRODUCTION_REVERSE_CONTRACT,
            ]
        )

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
        return self._normalize_production_result(data, raw_text=cleaned)

    def _normalize_production_result(self, data: dict[str, Any], raw_text: str = "") -> dict[str, Any]:
        production_overview = self._first_dict(data, ["production_overview", "制作总览", "制作概览"])
        asset_inventory = self._first_dict(data, ["asset_inventory", "素材清单", "素材盘点"])
        editing_style = self._first_dict(data, ["editing_style", "剪辑风格", "包装风格"])
        audio_analysis = self._first_dict(data, ["audio_analysis", "音频分析", "声音分析"])
        reproduction_plan = self._first_dict(data, ["reproduction_plan", "复做方案", "复刻方案"])

        timeline_items = (
            data.get("timeline_breakdown")
            or data.get("timeline")
            or data.get("segments")
            or data.get("segment_breakdowns")
            or data.get("timeline_analysis")
            or []
        )
        if not isinstance(timeline_items, list):
            timeline_items = []

        segment_breakdowns = data.get("segment_production_breakdowns") or data.get("segment_breakdowns") or []
        if not isinstance(segment_breakdowns, list):
            segment_breakdowns = []

        normalized_segments = [
            self._normalize_timeline_item(item, index)
            for index, item in enumerate(segment_breakdowns, start=1)
        ]
        normalized_timeline = [
            self._normalize_timeline_item(item, index)
            for index, item in enumerate(timeline_items or normalized_segments, start=1)
        ]

        main_workflow = self._first_text(production_overview, ["main_workflow", "主流程", "制作主流程"])
        summary = self._first_text(data, ["summary", "摘要", "一句话摘要"]) or main_workflow

        return {
            "summary": summary,
            "production_overview": {
                "content_type": self._first_text(production_overview, ["content_type", "内容类型", "视频类型"]),
                "main_workflow": main_workflow,
                "estimated_tools": self._coalesce_list(
                    production_overview,
                    ["estimated_tools", "possible_tools", "tools", "可能工具", "工具组合"],
                ),
                "difficulty": self._first_text(production_overview, ["difficulty", "难度", "制作难度"]),
                "source_mix": self._coalesce_list(
                    production_overview,
                    ["source_mix", "source_structure", "source_breakdown", "素材组合", "素材来源结构"],
                ),
                "tool_signatures": self._coalesce_list(
                    production_overview,
                    ["tool_signatures", "tool_hints", "software_signatures", "工具痕迹", "工具信号", "软件痕迹"],
                ),
                "template_signature": self._first_text(
                    production_overview,
                    ["template_signature", "template_hint", "模板痕迹", "模板信号"],
                ),
                "automation_level": self._first_text(
                    production_overview,
                    ["automation_level", "automation_guess", "自动化程度", "AI 参与程度"],
                ),
                "tool_likelihoods": self._normalize_likelihoods(
                    self._first_value(
                        production_overview,
                        ["tool_likelihoods", "tool_scores", "工具倾向评分", "工具评分"],
                    )
                ),
                "source_likelihoods": self._normalize_likelihoods(
                    self._first_value(
                        production_overview,
                        ["source_likelihoods", "source_scores", "来源倾向评分", "来源评分"],
                    )
                ),
            },
            "timeline_breakdown": normalized_timeline,
            "asset_inventory": {
                "video_materials": self._coalesce_list(asset_inventory, ["video_materials", "视频素材"]),
                "image_materials": self._coalesce_list(asset_inventory, ["image_materials", "图片素材"]),
                "audio_materials": self._coalesce_list(asset_inventory, ["audio_materials", "音频素材"]),
                "graphics_and_stickers": self._coalesce_list(
                    asset_inventory,
                    ["graphics_and_stickers", "贴纸图形", "graphics", "stickers"],
                ),
                "text_elements": self._coalesce_list(asset_inventory, ["text_elements", "文字元素"]),
                "source_provenance": self._coalesce_list(
                    asset_inventory,
                    ["source_provenance", "素材来源推测", "素材来源", "material_provenance"],
                ),
            },
            "evidence_media": self._normalize_evidence_media(data.get("evidence_media") or data.get("media_evidence") or {}),
            "editing_style": {
                "pace": self._first_text(editing_style, ["pace", "节奏"]),
                "shot_pattern": self._first_text(editing_style, ["shot_pattern", "镜头规律", "镜头模式"]),
                "subtitle_style": self._first_text(editing_style, ["subtitle_style", "字幕风格"]),
                "subtitle_animation": self._first_text(editing_style, ["subtitle_animation", "字幕动效", "text_animation"]),
                "transition_style": self._first_text(editing_style, ["transition_style", "转场风格"]),
                "sticker_style": self._first_text(editing_style, ["sticker_style", "贴纸风格", "overlay_style"]),
                "overlay_layout": self._first_text(editing_style, ["overlay_layout", "覆盖布局", "layout_style"]),
                "packaging_style": self._first_text(editing_style, ["packaging_style", "包装风格"]),
                "camera_motion_pattern": self._first_text(
                    editing_style,
                    ["camera_motion_pattern", "camera_pattern", "镜头运动模式"],
                ),
                "rhythm_sync_style": self._first_text(
                    editing_style,
                    ["rhythm_sync_style", "beat_sync_style", "卡点方式", "音画同步方式"],
                ),
            },
            "audio_analysis": {
                "voice_type": self._first_text(audio_analysis, ["voice_type", "人声类型", "配音类型"]),
                "voice_character": self._first_text(audio_analysis, ["voice_character", "声线特征", "voice_style"]),
                "bgm_type": self._first_text(audio_analysis, ["bgm_type", "BGM 类型", "背景音乐"]),
                "sfx_type": self._coalesce_list(audio_analysis, ["sfx_type", "音效类型", "sound_effects"]),
                "mixing_guess": self._first_text(audio_analysis, ["mixing_guess", "混音判断", "混音关系"]),
                "beat_sync_style": self._first_text(
                    audio_analysis,
                    ["beat_sync_style", "rhythm_sync_style", "节奏关系", "音画同步方式"],
                ),
            },
            "reproduction_plan": {
                "minimum_assets_needed": self._coalesce_list(
                    reproduction_plan,
                    ["minimum_assets_needed", "最少素材", "minimum_assets"],
                ),
                "recommended_production_steps": self._coalesce_list(
                    reproduction_plan,
                    ["recommended_production_steps", "建议步骤", "steps"],
                ),
                "can_be_generated_by_ai": self._coalesce_list(
                    reproduction_plan,
                    ["can_be_generated_by_ai", "可交给AI", "ai_generatable_parts"],
                ),
                "need_manual_editing": self._coalesce_list(
                    reproduction_plan,
                    ["need_manual_editing", "需手工剪辑", "manual_edit_parts"],
                ),
                "likely_toolchain": self._coalesce_list(
                    reproduction_plan,
                    ["likely_toolchain", "可能工具链", "toolchain_guess"],
                ),
                "quality_control_points": self._coalesce_list(
                    reproduction_plan,
                    ["quality_control_points", "质检点", "quality_checks"],
                ),
            },
            "segment_production_breakdowns": normalized_segments,
            "raw_model_json": data,
            "raw_model_text": raw_text,
        }

    def _normalize_timeline_item(self, item: Any, index: int) -> dict[str, Any]:
        if not isinstance(item, dict):
            item = {"notes": str(item or "")}

        return {
            "segment_id": self._first_text(item, ["segment_id", "片段ID"]) or f"segment-{index}",
            "time_range": self._first_text(item, ["time_range", "时间段", "时间范围", "time", "range"]),
            "segment_role": self._first_text(item, ["segment_role", "片段角色", "角色", "segment_type"]),
            "visual_source_type": self._first_text(
                item,
                ["visual_source_type", "画面来源类型", "素材类型", "visual_type"],
            ),
            "material_elements": self._coalesce_list(item, ["material_elements", "素材元素", "elements"]),
            "source_provenance": self._coalesce_list(
                item,
                ["source_provenance", "素材来源推测", "素材来源", "source_guess", "provenance"],
            ),
            "editing_actions": self._coalesce_list(item, ["editing_actions", "剪辑动作", "edit_actions"]),
            "transition": self._first_text(item, ["transition", "转场"]),
            "transition_confidence": self._first_text(
                item,
                ["transition_confidence", "转场信心", "transition_confidence_level"],
            ),
            "filter_or_grade": self._first_text(
                item,
                ["filter_or_grade", "滤镜或调色", "画面风格", "filter_grade"],
            ),
            "filter_strength": self._first_text(item, ["filter_strength", "滤镜强度", "调色强度"]),
            "stickers_overlays": self._coalesce_list(
                item,
                ["stickers_overlays", "贴纸覆盖", "overlays", "stickers"],
            ),
            "sticker_style": self._first_text(item, ["sticker_style", "贴纸样式", "overlay_style"]),
            "overlay_layout": self._first_text(item, ["overlay_layout", "覆盖布局", "layout_guess"]),
            "onscreen_text": self._coalesce_list(
                item,
                ["onscreen_text", "屏幕文字", "text_elements", "text_on_screen"],
            ),
            "subtitle_style": self._first_text(item, ["subtitle_style", "字幕风格", "text_style"]),
            "subtitle_animation": self._first_text(
                item,
                ["subtitle_animation", "字幕动效", "subtitle_motion", "text_animation"],
            ),
            "camera_movement_guess": self._first_text(
                item,
                ["camera_movement_guess", "镜头运动推测", "camera_motion"],
            ),
            "track_layer_guess": self._coalesce_list(
                item,
                ["track_layer_guess", "轨道层级推测", "track_layers", "layer_guess"],
            ),
            "sync_points": self._coalesce_list(
                item,
                ["sync_points", "卡点同步点", "节奏点", "beat_points", "sync_cues"],
            ),
            "audio_guess": self._coalesce_list(item, ["audio_guess", "音频判断", "audio"]),
            "generation_guess": self._coalesce_list(
                item,
                ["generation_guess", "生成方式猜测", "tools_guess", "production_guess"],
            ),
            "tool_signatures": self._coalesce_list(
                item,
                ["tool_signatures", "tool_hints", "工具信号", "工具痕迹", "软件痕迹"],
            ),
            "template_signature": self._first_text(
                item,
                ["template_signature", "模板痕迹", "template_hint"],
            ),
            "tool_likelihoods": self._normalize_likelihoods(
                self._first_value(item, ["tool_likelihoods", "tool_scores", "工具倾向评分", "工具评分"])
            ),
            "source_likelihoods": self._normalize_likelihoods(
                self._first_value(item, ["source_likelihoods", "source_scores", "来源倾向评分", "来源评分"])
            ),
            "confidence": self._first_text(item, ["confidence", "置信度", "判断信心"]),
            "evidence": self._coalesce_list(item, ["evidence", "依据", "判断依据"]),
            "notes": self._first_text(item, ["notes", "备注", "说明"]),
            "checkpoint_path": self._first_text(item, ["checkpoint_path"]),
            "evidence_media": self._normalize_segment_evidence_media(item.get("evidence_media") or item.get("media_evidence") or {}),
        }

    def _find_segment_by_id(self, segments: list[dict[str, Any]], segment_id: str | None) -> dict[str, Any] | None:
        if not segment_id:
            return None
        for segment in segments:
            if str(segment.get("segment_id") or "") == str(segment_id):
                return segment
        return None

    def _attach_segment_evidence(
        self,
        normalized_item: dict[str, Any],
        source_segment: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not source_segment:
            normalized_item["evidence_media"] = self._normalize_segment_evidence_media(
                normalized_item.get("evidence_media") or {}
            )
            return normalized_item

        keyframes = []
        for frame in source_segment.get("keyframes") or []:
            if not isinstance(frame, dict):
                continue
            keyframes.append(
                {
                    "time": frame.get("time"),
                    "time_label": frame.get("time_label"),
                    "image_path": str(frame.get("image_path") or ""),
                }
            )

        grid = source_segment.get("keyframe_grid") or {}
        grid_path = grid.get("image_path") if isinstance(grid, dict) else ""
        highlight_screenshots = source_segment.get("highlight_screenshots") or []

        normalized_item["evidence_media"] = self._normalize_segment_evidence_media(
            {
                "keyframe_grid": {
                    "image_path": str(grid_path or ""),
                    "frames": grid.get("frames") if isinstance(grid, dict) else [],
                },
                "keyframes": keyframes,
                "highlight_screenshots": highlight_screenshots,
            }
        )
        return normalized_item

    def _merge_timeline_with_segments(
        self,
        timeline_items: list[dict[str, Any]],
        normalized_segments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not timeline_items:
            return normalized_segments

        segment_by_id = {
            item.get("segment_id"): item
            for item in normalized_segments
            if isinstance(item, dict) and item.get("segment_id")
        }
        merged: list[dict[str, Any]] = []
        for item in timeline_items:
            item_id = item.get("segment_id")
            source = segment_by_id.get(item_id)
            if not source:
                merged.append(item)
                continue
            next_item = dict(item)
            for key in [
                "evidence_media",
                "tool_likelihoods",
                "source_likelihoods",
                "subtitle_style",
                "subtitle_animation",
                "sticker_style",
                "overlay_layout",
                "camera_movement_guess",
                "track_layer_guess",
                "sync_points",
                "tool_signatures",
                "template_signature",
            ]:
                if key not in next_item or next_item.get(key) in (None, "", [], {}):
                    next_item[key] = source.get(key)
            merged.append(next_item)
        return merged

    def _normalize_likelihoods(self, value: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if isinstance(value, dict):
            for name, raw in value.items():
                if isinstance(raw, dict):
                    score = raw.get("score")
                    reason = raw.get("reason") or raw.get("evidence") or ""
                else:
                    score = raw
                    reason = ""
                items.append(self._likelihood_item(name, score, reason))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    name = self._first_text(item, ["name", "label", "tool", "source", "title"])
                    score = item.get("score")
                    reason = self._first_text(item, ["reason", "evidence", "note", "summary"])
                    if name:
                        items.append(self._likelihood_item(name, score, reason))
                elif isinstance(item, str):
                    items.append(self._likelihood_item(item, None, ""))
        elif isinstance(value, str) and value.strip():
            for text in self._as_text_list(value):
                items.append(self._likelihood_item(text, None, ""))
        return [item for item in items if item.get("name")]

    def _likelihood_item(self, name: Any, score: Any, reason: Any) -> dict[str, Any]:
        numeric_score: int | None = None
        if isinstance(score, (int, float)):
            numeric_score = max(0, min(100, int(score)))
        elif isinstance(score, str):
            match = re.search(r"\d{1,3}", score)
            if match:
                numeric_score = max(0, min(100, int(match.group(0))))
        return {
            "name": str(name or "").strip(),
            "score": numeric_score,
            "reason": str(reason or "").strip(),
        }

    def _normalize_segment_evidence_media(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            value = {}
        keyframe_grid = value.get("keyframe_grid") or value.get("grid") or {}
        if not isinstance(keyframe_grid, dict):
            keyframe_grid = {}
        return {
            "keyframe_grid": {
                "image_path": str(keyframe_grid.get("image_path") or keyframe_grid.get("path") or ""),
                "frames": keyframe_grid.get("frames") if isinstance(keyframe_grid.get("frames"), list) else [],
            },
            "keyframes": self._normalize_media_frame_list(value.get("keyframes") or value.get("frames") or []),
            "highlight_screenshots": self._normalize_media_frame_list(
                value.get("highlight_screenshots") or value.get("screenshots") or []
            ),
        }

    def _normalize_media_frame_list(self, value: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not isinstance(value, list):
            return items
        for item in value:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "time": item.get("time"),
                    "time_label": item.get("time_label") or item.get("time"),
                    "reason": str(item.get("reason") or ""),
                    "image_path": str(item.get("image_path") or item.get("path") or ""),
                }
            )
        return items

    def _normalize_evidence_media(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            value = {}
        return {
            "segment_count": self._safe_count(value.get("segment_count")),
            "keyframe_grid_count": self._safe_count(value.get("keyframe_grid_count")),
            "keyframe_count": self._safe_count(value.get("keyframe_count")),
            "highlight_screenshot_count": self._safe_count(value.get("highlight_screenshot_count")),
        }

    def _build_evidence_media_summary(self, timeline_items: list[dict[str, Any]]) -> dict[str, Any]:
        segment_count = len(timeline_items)
        keyframe_grid_count = 0
        keyframe_count = 0
        highlight_screenshot_count = 0
        for item in timeline_items:
            media = item.get("evidence_media") or {}
            grid = (media.get("keyframe_grid") or {}).get("image_path") if isinstance(media, dict) else ""
            if grid:
                keyframe_grid_count += 1
            keyframe_count += len((media.get("keyframes") or []) if isinstance(media, dict) else [])
            highlight_screenshot_count += len((media.get("highlight_screenshots") or []) if isinstance(media, dict) else [])
        return {
            "segment_count": segment_count,
            "keyframe_grid_count": keyframe_grid_count,
            "keyframe_count": keyframe_count,
            "highlight_screenshot_count": highlight_screenshot_count,
        }

    def _safe_count(self, value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except Exception:
            return 0

    def _first_value(self, data: dict[str, Any], keys: list[str]) -> Any:
        if not isinstance(data, dict):
            return None
        for key in keys:
            if key not in data:
                continue
            value = data.get(key)
            if value not in (None, "", [], {}):
                return value
        return None

    def _coalesce_list(self, data: dict[str, Any], keys: list[str]) -> list[str]:
        return self._as_text_list(self._first_value(data, keys))

    def _as_text_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            items: list[str] = []
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                elif isinstance(item, dict):
                    text = self._first_text(
                        item,
                        ["name", "label", "title", "text", "summary", "value", "step", "tool", "reason"],
                    )
                    if not text:
                        text = " ".join(str(part) for part in item.values() if part not in {None, ""})
                elif item is None:
                    text = ""
                else:
                    text = str(item)
                if text:
                    items.append(text)
            return items

        if isinstance(value, str):
            text = value.replace("\r", "\n").strip()
            if not text:
                return []
            parts = re.split(r"[\n；;]+", text)
            return [part.strip(" -•\t") for part in parts if part.strip(" -•\t")]

        if isinstance(value, dict):
            return self._as_text_list(list(value.values()))

        if value is None:
            return []

        return [str(value)]

    def _mock_result(self, video: dict[str, Any]) -> dict[str, Any]:
        desc = video.get("desc") or video.get("title") or "未命名视频"
        return {
            "summary": f"待接入真实模型。当前已接收视频《{desc}》，真实模型会输出素材来源、剪辑方式、工具痕迹和复做路径。",
            "production_overview": {
                "content_type": "信息流短视频",
                "main_workflow": "开场钩子画面 + 口播/字幕说明 + 节奏型包装 + 收尾 CTA",
                "estimated_tools": ["剪映", "CapCut/剪映模板", "AI 配音"],
                "difficulty": "中",
                "source_mix": ["主体视频", "补充 B-roll", "大字字幕包装"],
                "tool_signatures": ["像剪映常见大字描边字幕", "像模板化卡点包装"],
                "template_signature": "疑似套用了信息流字幕包装模板",
                "automation_level": "中，脚本/配音/部分补画可 AI 生成，节奏剪辑仍需要人工把控",
                "tool_likelihoods": [
                    {"name": "剪映", "score": 82, "reason": "大字描边字幕和卡点包装更像剪映常见模板"},
                    {"name": "CapCut", "score": 68, "reason": "字幕与包装风格也接近 CapCut 的短视频模板"},
                ],
                "source_likelihoods": [
                    {"name": "实拍", "score": 60, "reason": "主体画面更像真人拍摄后叠加包装"},
                    {"name": "模板包装", "score": 78, "reason": "贴纸、字幕和节奏像模板化信息流包装"},
                ],
            },
            "timeline_breakdown": [
                {
                    "segment_id": "segment-1",
                    "time_range": "00:00-00:03",
                    "segment_role": "开场钩子",
                    "visual_source_type": "无法确认",
                    "material_elements": ["主体画面", "大字标题"],
                    "source_provenance": ["疑似主体画面配字幕模板包装"],
                    "editing_actions": ["快切", "轻微放大"],
                    "transition": "硬切",
                    "transition_confidence": "中",
                    "filter_or_grade": "高对比信息流包装",
                    "filter_strength": "中",
                    "stickers_overlays": ["箭头贴纸"],
                    "sticker_style": "信息提示型箭头",
                    "overlay_layout": "标题居中，上层叠加箭头强调",
                    "onscreen_text": ["强钩子标题"],
                    "subtitle_style": "大字描边字幕",
                    "subtitle_animation": "逐条弹入",
                    "camera_movement_guess": "后期轻微数码推近",
                    "track_layer_guess": ["主画面轨", "字幕轨", "贴纸轨", "BGM 轨"],
                    "sync_points": ["标题出现和 BGM 起拍同步"],
                    "audio_guess": ["AI 配音", "节奏型 BGM"],
                    "generation_guess": ["可能使用模板化包装"],
                    "tool_signatures": ["像剪映默认字幕样式"],
                    "template_signature": "轻模板痕迹",
                    "tool_likelihoods": [
                        {"name": "剪映", "score": 84, "reason": "字幕样式与贴纸提示感很像剪映"},
                        {"name": "CapCut", "score": 66, "reason": "同类模板也常见于 CapCut"},
                    ],
                    "source_likelihoods": [
                        {"name": "实拍", "score": 55, "reason": "主体画面更像原始拍摄素材"},
                        {"name": "模板包装", "score": 80, "reason": "字幕贴纸层像后期模板化包装"},
                    ],
                    "confidence": "低",
                    "evidence": ["mock 结果，无真实判断依据"],
                    "notes": "",
                    "checkpoint_path": "",
                    "evidence_media": {
                        "keyframe_grid": {"image_path": "", "frames": []},
                        "keyframes": [],
                        "highlight_screenshots": [],
                    },
                }
            ],
            "asset_inventory": {
                "video_materials": ["主体视频"],
                "image_materials": ["封面图或截图"],
                "audio_materials": ["配音", "BGM"],
                "graphics_and_stickers": ["箭头", "重点框"],
                "text_elements": ["标题", "重点词", "CTA"],
                "source_provenance": ["主体实拍或素材库画面 + 模板化字幕包装"],
            },
            "evidence_media": {
                "segment_count": 1,
                "keyframe_grid_count": 0,
                "keyframe_count": 0,
                "highlight_screenshot_count": 0,
            },
            "editing_style": {
                "pace": "快节奏",
                "shot_pattern": "2-3 秒一切",
                "subtitle_style": "大字重点词",
                "subtitle_animation": "关键词弹入",
                "transition_style": "以硬切为主",
                "sticker_style": "提示型箭头和高亮框",
                "overlay_layout": "中心标题 + 四角辅助贴纸",
                "packaging_style": "典型信息流包装",
                "camera_motion_pattern": "静态画面配轻微后期推拉",
                "rhythm_sync_style": "字幕和 BGM 节拍同步",
            },
            "audio_analysis": {
                "voice_type": "AI 配音",
                "voice_character": "中性、清晰、信息播报感",
                "bgm_type": "情绪型 BGM",
                "sfx_type": ["点击音效"],
                "mixing_guess": "人声前置，BGM 压低",
                "beat_sync_style": "卡点偏字幕和字卡同步",
            },
            "reproduction_plan": {
                "minimum_assets_needed": ["主体画面", "字幕文案", "BGM"],
                "recommended_production_steps": ["先准备脚本", "再找主体素材", "最后统一包装"],
                "can_be_generated_by_ai": ["配音", "部分补充画面"],
                "need_manual_editing": ["卡点剪辑", "字幕节奏微调"],
                "likely_toolchain": ["脚本生成 -> AI 配音 -> 剪映/CapCut 包装 -> 导出复检"],
                "quality_control_points": ["字幕错字", "卡点是否顺拍", "BGM 音量是否压住人声"],
            },
            "segment_production_breakdowns": [],
            "raw_model_json": {},
            "raw_model_text": "",
        }
