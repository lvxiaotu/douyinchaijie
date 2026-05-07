from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from integrations.ai_video_analysis.adapter import AiVideoAnalysisAdapter
from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline
from backend.app.ai_provider_state import active_ai_provider
from integrations.base import IntegrationAdapter, IntegrationManifest


DEFAULT_OUTPUT_DIR = Path("data/runtime/ai_prompt_reverse")
REPLICA_REVERSE_CONTRACT = """
复刻级反推要求：
1. 目标不是摘要，而是让用户能按镜头重建同类型 AI 视频。
2. 必须结合转写文本、关键帧时间戳和关键帧网格图判断画面；无法确认的细节写“无法确认”，不要编造。
3. 每个镜头都要拆出：脚本文案/旁白、画面描述、首帧、尾帧、主体动作、镜头运动、景别构图、光线色彩、转场、可直接复制的生成提示词。
4. shot_prompts 必须按视频时间顺序排列，尽量覆盖全片；长视频可按片段输出代表性镜头。
5. master_prompt 用于统一风格；shot_prompts 用于逐镜头生成；negative_prompt 用于质量控制。

最终 JSON schema：
{
  "summary": "一句话说明原视频结构、视觉风格和复刻价值",
  "reconstruction_strategy": "如何复刻：先生成哪些画面、如何保持角色/风格一致、如何剪辑成片",
  "master_prompt": "全片统一风格提示词，包含主体设定、场景、画面比例、质感、镜头语言、光线、色彩、节奏",
  "negative_prompt": "全片通用负向提示词",
  "audio_script": [
    {"time_range": "00:00-00:05", "line": "旁白/字幕/台词；无则写无"}
  ],
  "shot_prompts": [
    {
      "shot": "镜头1",
      "time_range": "00:00-00:05",
      "script_line": "这一镜的旁白/字幕/剧情动作",
      "visual_description": "画面中真实可见的主体、场景、道具和动作",
      "first_frame": "首帧画面如何构图",
      "last_frame": "尾帧画面如何变化",
      "camera_movement": "推/拉/摇/移/跟拍/旋转/静止等运镜",
      "subject_motion": "主体动作变化",
      "composition": "景别、角度、构图、画面比例",
      "lighting_color": "光线、色彩、材质和氛围",
      "transition": "与前后镜头的转场方式",
      "prompt": "可直接复制到文生视频或图生视频工具的中文镜头提示词",
      "negative_prompt": "该镜头需要避免的问题",
      "reference_frames": ["00:00", "00:03"]
    }
  ],
  "style_keywords": ["统一风格关键词"],
  "usage_notes": ["复刻步骤、模型建议、首尾帧用法、剪辑建议"]
}
""".strip()
RICH_REVERSE_PROMPT_CONTRACT = """
输出必须是一个合法 JSON 对象，不要 Markdown、解释文字或代码块。字段名必须保持英文。

反推要求：
1. 不要只总结内容，要把视频还原成可复用的生成指令。
2. master_prompt 至少包含：主体外观、场景空间、关键道具、动作链路、镜头语言、构图、景别、运动方式、光线、色彩、材质、氛围、节奏、画面比例、清晰度、商业表达。建议 180-350 个中文字符。
3. shot_prompts 至少输出 4 个镜头；每个 prompt 都要能单独复制到文生视频或图生视频工具中使用，包含主体、动作、景别、镜头运动、光线和情绪。
4. negative_prompt 至少包含 10 类需要避免的问题。
5. style_keywords 至少 8 个，覆盖风格、镜头、光线、色彩、质感、节奏。
6. usage_notes 至少 4 条，说明适合哪些模型、如何替换主体/产品、如何改写成图生视频、如何扩展成脚本。

JSON schema：
{
  "summary": "一句话说明视频的画面风格、内容结构和可复用价值",
  "master_prompt": "完整可复用提示词，包含主体、场景、动作、镜头、光线、色彩、质感、情绪、节奏、商业表达",
  "negative_prompt": "生成时需要避免的画面、风格或质量问题",
  "shot_prompts": [
    {"shot": "镜头1", "prompt": "这个镜头可复用的生成提示词"}
  ],
  "style_keywords": ["风格关键词"],
  "usage_notes": ["使用建议、适合模型、改写方向"]
}
""".strip()
DEFAULT_REVERSE_PROMPT = """
你是一个视频生成提示词反推专家。请观看这个视频，并只返回 JSON，不要返回 Markdown。

视频标题或描述：{desc}
作者：{author}

请根据视频反推出适合文生视频、图生视频或脚本生成模型使用的提示词。JSON 字段必须保持英文不变，字段值使用中文：
{
  "summary": "一句话说明这个视频的画面风格、内容结构和可复用价值",
  "master_prompt": "完整可复用提示词，包含主体、场景、动作、镜头、光线、色彩、质感、情绪、节奏、商业表达",
  "negative_prompt": "生成时需要避免的画面、风格或质量问题",
  "shot_prompts": [
    {"shot": "镜头1", "prompt": "这个镜头可复用的生成提示词"}
  ],
  "style_keywords": ["风格关键词"],
  "usage_notes": ["使用建议、适合模型、改写方向"]
}

请让 master_prompt 足够具体，可以直接复制到视频或图像生成工具里二次创作。
""".strip()


class AiPromptReverseAdapter(IntegrationAdapter):
    manifest = IntegrationManifest(
        id="ai-prompt-reverse",
        name="AI 提示词反推",
        description="选择已采集视频，根据可配置要求反推出可复用生成提示词。",
        repo_url="",
        tags=["ai", "prompt", "video"],
        config_schema={
            "provider": "mock | gemini",
            "output_dir": "任务和结果保存目录",
            "reverse_prompt": "反推提示词模板",
        },
    )

    def __init__(self, config: dict[str, Any] | None = None):
        load_dotenv()
        self.config = config or {}
        self.provider = self.config.get("provider") or active_ai_provider("mock")
        self.output_dir = Path(
            self.config.get("output_dir")
            or os.getenv("AI_PROMPT_REVERSE_OUTPUT_DIR")
            or DEFAULT_OUTPUT_DIR
        )
        self.reverse_prompt = (
            self.config.get("reverse_prompt")
            or os.getenv("AI_PROMPT_REVERSE_PROMPT")
            or DEFAULT_REVERSE_PROMPT
        )
        self.pipeline_mode = (
            self.config.get("pipeline_mode")
            or os.getenv("AI_PROMPT_REVERSE_PIPELINE_MODE")
            or "evidence"
        ).lower()

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]:
        cfg = {**self.config, **(config or {})}
        provider = cfg.get("provider") or active_ai_provider(self.provider)
        if provider == "gemini":
            access_mode = os.getenv("GEMINI_ACCESS_MODE") or os.getenv("AI_ACCESS_MODE", "official")
            if access_mode == "relay" and not (os.getenv("GEMINI_RELAY_API_KEY") or os.getenv("AI_RELAY_API_KEY")):
                return ["Missing GEMINI_RELAY_API_KEY"]
            if access_mode != "relay" and not (os.getenv("GEMINI_API_KEY") or os.getenv("AI_NATIVE_API_KEY")):
                return ["Missing GEMINI_API_KEY"]
        return []

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "create_job":
            return self.create_job(payload.get("video") or {}, payload.get("provider"))
        raise ValueError(f"Unsupported AI prompt reverse action: {action}")

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
        job_id = job_id or f"prompt-reverse-{aweme_id}-{int(time.time())}"
        selected_provider = provider or self.provider
        prompt = self._reverse_prompt(video)
        if progress:
            progress(10, "准备 AI 提示词反推任务")

        if selected_provider == "gemini" or self._uses_gemini_relay_provider(selected_provider):
            result = self._reverse_result(video, job_id=job_id, progress=progress, prompt=prompt)
            status = "done"
        else:
            raise RuntimeError(
                f"当前全局 AI 模型 {selected_provider} 暂不支持视频上传反推。"
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
            progress(100, "提示词反推完成")
        return job

    def _reverse_result(
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
                progress(15, "启动复刻级反推证据管线")
            evidence = VideoEvidencePipeline(output_dir=self.output_dir).build(video, job_id=job_id, progress=progress)
            result = self._evidence_replica_reverse(video, evidence=evidence, progress=progress)
            helper = AiVideoAnalysisAdapter({"output_dir": str(self.output_dir)})
            result["reverse_mode"] = "evidence_pipeline"
            result["evidence"] = helper._compact_evidence(evidence)
            return result
        except Exception as exc:
            if self.pipeline_mode == "evidence":
                raise
            if progress:
                progress(60, f"证据管线不可用，回退整段视频反推：{type(exc).__name__}")
            result = self._gemini_result(video, progress=progress, prompt=prompt)
            result["reverse_mode"] = "direct_video_fallback"
            result["pipeline_error"] = f"{type(exc).__name__}: {exc}"
            return result

    def _evidence_replica_reverse(
        self,
        video: dict[str, Any],
        *,
        evidence: dict[str, Any],
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        segments = evidence.get("analysis_segments") or []
        if not segments:
            raise RuntimeError("转写结果为空，无法进行复刻级提示词反推。")

        helper = AiVideoAnalysisAdapter({"output_dir": str(self.output_dir)})
        max_segments = int(os.getenv("AI_PROMPT_REVERSE_MAX_SEGMENTS") or os.getenv("AI_VIDEO_MAX_SEGMENTS", "18"))
        selected_segments = segments[:max_segments]
        evidence_path = Path(str(evidence.get("evidence_path") or ""))
        checkpoint_dir = (evidence_path.parent if evidence_path.parent else self.output_dir) / "replica_reverse_segments"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        resume_enabled = os.getenv("AI_VIDEO_RESUME_ENABLED", "true").lower() not in {"0", "false", "no"}
        if progress:
            skipped = len(segments) - len(selected_segments)
            suffix = f"，跳过 {skipped} 个超出上限片段" if skipped > 0 else ""
            progress(60, f"准备逐段复刻反推：{len(selected_segments)} 个片段{suffix}")

        segment_results: list[dict[str, Any]] = []
        for index, segment in enumerate(selected_segments, start=1):
            checkpoint_path = checkpoint_dir / f"{segment.get('segment_id') or index}.json"
            if resume_enabled and checkpoint_path.exists():
                try:
                    parsed = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                    segment_results.append(parsed)
                    if progress:
                        progress(60 + int(24 * index / max(1, len(selected_segments))), f"断点续跑：复用第 {index}/{len(selected_segments)} 段复刻反推")
                    continue
                except Exception:
                    if progress:
                        progress(60, f"第 {index} 段复刻 checkpoint 读取失败，重新反推")
            prompt = self._segment_replica_prompt(video, segment)
            image_paths = helper._segment_image_paths(segment)
            if progress:
                message = f"提交第 {index}/{len(selected_segments)} 段复刻反推：{segment.get('time_range')}"
                if image_paths:
                    message += f"，附带 {Path(image_paths[0]).name}"
                progress(60 + int(18 * (index - 1) / max(1, len(selected_segments))), message)
            text = helper._generate_text_json(prompt, action="请求模型生成镜头级复刻反推", image_paths=image_paths)
            parsed = self._parse_segment_replica_json(text, segment)
            parsed["checkpoint_path"] = str(checkpoint_path)
            checkpoint_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            segment_results.append(parsed)
            if progress:
                progress(60 + int(24 * index / max(1, len(selected_segments))), f"第 {index}/{len(selected_segments)} 段复刻反推完成")

        global_checkpoint = (evidence_path.parent if evidence_path.parent else self.output_dir) / "global_replica_reverse.json"
        if resume_enabled and global_checkpoint.exists():
            try:
                result = json.loads(global_checkpoint.read_text(encoding="utf-8"))
                if progress:
                    progress(90, "断点续跑：复用全局复刻提示词")
            except Exception:
                result = self._global_replica_reverse(video, evidence=evidence, segment_results=segment_results, helper=helper)
                result["checkpoint_path"] = str(global_checkpoint)
                global_checkpoint.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            if progress:
                progress(88, "汇总全片脚本、首尾帧、运镜和提示词")
            result = self._global_replica_reverse(video, evidence=evidence, segment_results=segment_results, helper=helper)
            result["checkpoint_path"] = str(global_checkpoint)
            global_checkpoint.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["segment_reconstructions"] = segment_results
        if progress:
            progress(94, "复刻级提示词反推整理完成")
        return self._parse_json(json.dumps(result, ensure_ascii=False))

    def _global_replica_reverse(
        self,
        video: dict[str, Any],
        *,
        evidence: dict[str, Any],
        segment_results: list[dict[str, Any]],
        helper: AiVideoAnalysisAdapter,
    ) -> dict[str, Any]:
        payload = {
            "video_title": video.get("desc") or video.get("title") or "",
            "transcript_excerpt": str((evidence.get("transcript") or {}).get("full_text") or "")[:12000],
            "segment_reconstructions": segment_results,
        }
        prompt = "\n\n".join(
            [
                self._reverse_prompt(video),
                "下面是基于转写和关键帧网格逐段得到的镜头级复刻结果。请合并成全片可执行复刻方案，去重、补齐顺序、统一角色和风格。不要编造证据外事实。",
                json.dumps(payload, ensure_ascii=False),
                REPLICA_REVERSE_CONTRACT,
            ]
        )
        text = helper._generate_text_json(prompt, action="请求模型汇总全片复刻提示词")
        return self._parse_json(text)

    def _segment_replica_prompt(self, video: dict[str, Any], segment: dict[str, Any]) -> str:
        desc = video.get("desc") or video.get("title") or ""
        keyframes = [
            {"time": frame.get("time_label"), "image_path": frame.get("image_path")}
            for frame in (segment.get("keyframes") or [])
        ]
        grid = (segment.get("keyframe_grid") or {}).get("image_path") if isinstance(segment.get("keyframe_grid"), dict) else ""
        return f"""
你是 AI 视频复刻级提示词反推师。请只返回合法 JSON，不要 Markdown。

视频标题：{desc}
当前片段：{segment.get("time_range")}
片段转写：
{str(segment.get("transcript") or "")[:7000]}

关键帧索引：
{json.dumps(keyframes, ensure_ascii=False)}

关键帧网格图：
{grid or "无"}

请基于转写、时间戳和关键帧网格，把这一段拆成可复刻镜头。不能确认的画面细节写“无法确认”。

返回 JSON：
{{
  "segment_id": "{segment.get("segment_id")}",
  "time_range": "{segment.get("time_range")}",
  "segment_script": "这一段的旁白、字幕或剧情脚本；无则写无",
  "shots": [
    {{
      "shot": "镜头1",
      "time_range": "00:00-00:05",
      "script_line": "该镜头对应旁白/字幕/动作",
      "visual_description": "主体、场景、道具、动作",
      "first_frame": "首帧构图和画面状态",
      "last_frame": "尾帧构图和画面变化",
      "camera_movement": "运镜方式",
      "subject_motion": "主体动作",
      "composition": "景别、角度、构图、比例",
      "lighting_color": "光线、色彩、材质、氛围",
      "transition": "转场",
      "prompt": "可直接复制的镜头生成提示词",
      "negative_prompt": "该镜头负向提示词",
      "reference_frames": ["00:00"]
    }}
  ],
  "style_observations": ["从画面可见的风格特征"],
  "continuity_notes": "角色/场景/道具如何保持一致"
}}
""".strip()

    def _parse_segment_replica_json(self, text: str, segment: dict[str, Any]) -> dict[str, Any]:
        data = self._parse_json(text).get("raw_model_json") or {}
        if not isinstance(data, dict):
            data = {"summary": str(text or "")}
        data.setdefault("segment_id", segment.get("segment_id"))
        data.setdefault("time_range", segment.get("time_range"))
        shots = data.get("shots") or data.get("shot_prompts") or []
        data["shots"] = shots if isinstance(shots, list) else []
        return data

    def _gemini_result(
        self,
        video: dict[str, Any],
        progress: Callable[[int, str], None] | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        helper = AiVideoAnalysisAdapter({"output_dir": str(self.output_dir)})
        prompt = prompt or self._reverse_prompt(video)
        if progress:
            progress(20, "定位或下载视频文件")
        video_path = helper._resolve_video_file(video)

        access_mode = (os.getenv("GEMINI_ACCESS_MODE") or os.getenv("AI_ACCESS_MODE") or "official").lower()
        if access_mode == "relay" or self._uses_gemini_relay_provider(active_ai_provider("")):
            if progress:
                progress(45, "准备 Gemini 中转站视频数据")
            text = helper._generate_with_relay(
                video_path=video_path,
                prompt=prompt,
                model=os.getenv("SIMPLE_RELAY_MODEL") or os.getenv("GEMINI_MODEL") or os.getenv("AI_MODEL", "gemini-2.5-flash"),
                progress=progress,
                system_instruction="你是视频生成提示词反推专家。必须观察视频画面、镜头和节奏，输出丰富、可直接复制到生成工具的合法 JSON。",
                action="请求 Gemini 中转站反推提示词",
            )
            if progress:
                progress(90, "解析提示词反推结果")
            return self._parse_json(text)

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Missing dependency google-genai. Run: pip install -r requirements.txt") from exc

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("AI_NATIVE_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY in .env before using Gemini prompt reverse.")
        model = os.getenv("GEMINI_MODEL") or os.getenv("AI_MODEL", "gemini-2.5-flash")
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
            model=model,
            contents=[prompt, uploaded],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
            progress=progress,
            action="请求 Gemini 反推提示词",
        )
        if progress:
            progress(90, "解析提示词反推结果")
        return self._parse_json(response.text)

    def _uses_gemini_relay_provider(self, provider: str) -> bool:
        if provider == "simple_relay":
            return os.getenv("SIMPLE_RELAY_API_FORMAT", "gemini_generate_content") == "gemini_generate_content"
        if provider == "yunwu":
            return os.getenv("YUNWU_API_FORMAT", "gemini_generate_content") == "gemini_generate_content"
        return False

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

    def _reverse_prompt(self, video: dict[str, Any]) -> str:
        desc = video.get("desc") or video.get("title") or ""
        author = video.get("author") or {}
        author_name = author.get("nickname") if isinstance(author, dict) else author
        prompt = self._clean_prompt(self.reverse_prompt)
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
                REPLICA_REVERSE_CONTRACT,
                RICH_REVERSE_PROMPT_CONTRACT,
            ]
        )

    def _clean_prompt(self, prompt: str) -> str:
        cleaned = str(prompt or "").strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
            cleaned = cleaned[1:-1]
        cleaned = cleaned.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
        return cleaned.strip() or DEFAULT_REVERSE_PROMPT

    def _parse_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            data = {"summary": cleaned}
        if not isinstance(data, dict):
            data = {"summary": cleaned}
        shot_prompts = data.get("shot_prompts") or data.get("分镜提示词") or data.get("镜头提示词") or []
        style_keywords = data.get("style_keywords") or data.get("风格关键词") or []
        usage_notes = data.get("usage_notes") or data.get("使用建议") or []
        audio_script = data.get("audio_script") or data.get("脚本") or []
        segment_reconstructions = data.get("segment_reconstructions") or []
        return {
            "summary": data.get("summary") or data.get("摘要") or "",
            "reconstruction_strategy": data.get("reconstruction_strategy") or data.get("复刻策略") or "",
            "master_prompt": data.get("master_prompt") or data.get("完整提示词") or data.get("主提示词") or "",
            "negative_prompt": data.get("negative_prompt") or data.get("负向提示词") or "",
            "audio_script": audio_script if isinstance(audio_script, list) else [],
            "shot_prompts": shot_prompts if isinstance(shot_prompts, list) else [],
            "segment_reconstructions": segment_reconstructions if isinstance(segment_reconstructions, list) else [],
            "style_keywords": style_keywords if isinstance(style_keywords, list) else [],
            "usage_notes": usage_notes if isinstance(usage_notes, list) else [],
            "raw_model_json": data,
        }

    def _mock_result(self, video: dict[str, Any]) -> dict[str, Any]:
        desc = video.get("desc") or video.get("title") or "未命名视频"
        return {
            "summary": f"待接入真实模型。当前已接收视频《{desc}》，可用于反推生成提示词。",
            "master_prompt": "主体清晰，生活化场景，短视频竖屏构图，真实自然光，强钩子开场，产品利益点明确，节奏紧凑，适合种草内容。",
            "negative_prompt": "避免画面模糊、主体不清、过度塑料质感、无关文字、水印、低清晰度。",
            "shot_prompts": [
                {"shot": "开场镜头", "prompt": "竖屏短视频，强视觉钩子，主体居中，快速吸引注意力。"},
                {"shot": "效果展示", "prompt": "展示使用前后变化，动作清晰，重点突出产品利益。"},
            ],
            "style_keywords": ["真实感", "种草", "生活化", "竖屏", "高转化"],
            "usage_notes": ["可复制 master_prompt 到视频生成工具，并按具体产品替换主体和场景。"],
        }
