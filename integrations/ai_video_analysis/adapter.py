from __future__ import annotations

import json
import os
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

from integrations.base import IntegrationAdapter, IntegrationManifest
from backend.app.ai_provider_state import active_ai_provider
from backend.app.video_analysis_queue import raise_if_ai_video_cancelled, record_ai_model_run, record_ai_video_artifact, upsert_ai_video_chunk
from integrations.ai_video_analysis.analysis_runner import run_evidence_breakdown
from integrations.ai_video_analysis.call_helpers import call_generate_text_hook
from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline
from integrations.ai_video_analysis.model_gateway import (
    AiVideoProviderRoute,
    normalized_usage,
    resolve_ai_video_provider_route,
)
from integrations.ai_video_analysis.http_policy import default_max_retries, default_timeout_seconds, get_with_retries
from integrations.ai_video_analysis.prompt_builder import (
    DEFAULT_ANALYSIS_PROMPT,
    analysis_prompt as build_analysis_prompt,
    clean_prompt,
    genre_profile,
    global_breakdown_prompt as build_global_breakdown_prompt,
    infer_genre,
    normalize_genre,
    prompt_context,
    segment_breakdown_prompt as build_segment_breakdown_prompt,
)
from integrations.ai_video_analysis.relay_clients import DeepSeekChatClient, GeminiGenerateContentRelayClient, OpenAICompatibleRelayClient
from integrations.ai_video_analysis.result_normalizer import parse_model_json, parse_segment_json


DEFAULT_OUTPUT_DIR = Path("data/runtime/ai_video_analysis")


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
        self.gemini_model = (
            self.config.get("gemini_model")
            or os.getenv("AI_VIDEO_VISION_MODEL")
            or os.getenv("GEMINI_MODEL")
            or os.getenv("YUNWU_MODEL")
            or os.getenv("AI_MODEL", "gemini-2.5-flash")
        )
        self.summary_provider = (
            self.config.get("summary_provider")
            or os.getenv("AI_VIDEO_SUMMARY_PROVIDER")
            or os.getenv("AI_VIDEO_GLOBAL_SUMMARY_PROVIDER")
            or ""
        ).lower()
        self.summary_model = (
            self.config.get("summary_model")
            or os.getenv("AI_VIDEO_SUMMARY_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or "deepseek-v4-flash"
        )
        self.summary_fallback_provider = (
            self.config.get("summary_fallback_provider")
            or os.getenv("AI_VIDEO_SUMMARY_FALLBACK_PROVIDER")
            or "vision"
        ).lower()
        self.analysis_prompt = self.config.get("analysis_prompt") or os.getenv("AI_VIDEO_ANALYSIS_PROMPT") or DEFAULT_ANALYSIS_PROMPT
        self.pipeline_mode = (self.config.get("pipeline_mode") or os.getenv("AI_VIDEO_PIPELINE_MODE") or "auto").lower()
        self.output_dir = Path(
            self.config.get("output_dir")
            or os.getenv("AI_VIDEO_OUTPUT_DIR")
            or DEFAULT_OUTPUT_DIR
        )

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]:
        cfg = {**self.config, **(config or {})}
        route = self._provider_route(
            cfg.get("provider") or self.provider,
            pipeline_mode=(cfg.get("pipeline_mode") or self.pipeline_mode),
        )
        errors = list(route.config_errors)
        summary_provider = (cfg.get("summary_provider") or os.getenv("AI_VIDEO_SUMMARY_PROVIDER") or "").lower()
        if summary_provider == "deepseek" and not (os.getenv("AI_VIDEO_SUMMARY_API_KEY") or os.getenv("DEEPSEEK_API_KEY")):
            errors.append("Missing DEEPSEEK_API_KEY")
        if (os.getenv("AI_VIDEO_TRANSCRIBER", "auto").lower() in {"doubao", "doubao_file_asr", "volcengine", "volcengine_asr"}):
            from integrations.ai_video_analysis.doubao_asr import validate_doubao_asr_environment

            errors.extend(validate_doubao_asr_environment())
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
        route = self._provider_route(selected_provider)
        if route.config_errors:
            raise RuntimeError(route.error_message)
        prompt = self._analysis_prompt(video)
        if progress:
            progress(10, "准备 AI 视频拆解任务")
        self._check_cancelled(job_id)
        if route.family == "mock":
            if progress:
                progress(60, "生成 mock 拆解结果")
            self._check_cancelled(job_id)
            result = self._mock_result(video)
            status = "done"
        elif route.can_use_evidence_pipeline:
            result = self._analysis_result(video, route=route, job_id=job_id, progress=progress, prompt=prompt)
            status = "done"
        else:
            raise RuntimeError(route.error_message or f"当前全局 AI 模型 {selected_provider} 暂不支持视频上传任务。")
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
        route: AiVideoProviderRoute,
        job_id: str,
        progress: Callable[[int, str], None] | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        if self.pipeline_mode == "direct":
            if not route.can_use_direct_video:
                raise RuntimeError(route.error_message or "AI_VIDEO_PIPELINE_MODE=direct requires Gemini relay")
            return self._gemini_result(video, route=route, progress=progress, prompt=prompt)

        try:
            self._check_cancelled(job_id)
            evidence = VideoEvidencePipeline(output_dir=self.output_dir).build(video, job_id=job_id, progress=progress, cancel_check=lambda: self._check_cancelled(job_id))
            self._check_cancelled(job_id)
            self._record_evidence_state(job_id, evidence)
            self._check_cancelled(job_id)
            result = self._evidence_breakdown(video, evidence=evidence, progress=progress, route=route)
            result["analysis_mode"] = "evidence_pipeline"
            result["evidence"] = self._compact_evidence(evidence)
            return result
        except Exception as exc:
            if self.pipeline_mode == "evidence":
                raise
            if progress:
                progress(60, f"证据包流程不可用，回退直接视频分析：{type(exc).__name__}")
            result = self._gemini_result(video, route=route, progress=progress, prompt=prompt)
            result["analysis_mode"] = "direct_video_fallback"
            result["pipeline_error"] = f"{type(exc).__name__}: {exc}"
            return result

    def _evidence_breakdown(
        self,
        video: dict[str, Any],
        *,
        evidence: dict[str, Any],
        route: AiVideoProviderRoute | None = None,
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        return run_evidence_breakdown(self, video, evidence=evidence, progress=progress, route=route)

    def _check_cancelled(self, task_id: str) -> None:
        raise_if_ai_video_cancelled(task_id)

    def _record_evidence_state(self, task_id: str, evidence: dict[str, Any]) -> None:
        if not task_id:
            return
        metadata = evidence.get("metadata") if isinstance(evidence.get("metadata"), dict) else {}
        checkpoints = evidence.get("checkpoints") if isinstance(evidence.get("checkpoints"), dict) else {}
        artifact_specs = [
            ("video", metadata.get("video_path"), {"duration": metadata.get("duration") or 0}),
            ("audio", metadata.get("audio_path"), {"audio_url": metadata.get("audio_url") or ""}),
            ("transcript", checkpoints.get("transcript_path"), {"provider": (evidence.get("asr") or {}).get("provider") or ""}),
            ("transcript_raw", checkpoints.get("transcript_raw_path"), {"provider": (evidence.get("asr") or {}).get("provider") or ""}),
            ("keyframes", checkpoints.get("keyframes_path"), {"count": len(evidence.get("keyframes") or [])}),
            ("evidence_json", evidence.get("evidence_path"), {"schema_version": evidence.get("schema_version") or ""}),
        ]
        for artifact_type, uri, meta in artifact_specs:
            if uri:
                record_ai_video_artifact(task_id=task_id, type=artifact_type, uri=str(uri), meta=meta)
        for segment in evidence.get("analysis_segments") or []:
            index = self._segment_index(segment)
            grid = segment.get("keyframe_grid") if isinstance(segment.get("keyframe_grid"), dict) else {}
            grid_uri = str(grid.get("image_path") or "")
            if grid_uri:
                record_ai_video_artifact(
                    task_id=task_id,
                    type="keyframe_grid",
                    uri=grid_uri,
                    meta={"segment_id": segment.get("segment_id") or "", "chunk_index": index},
                )
            upsert_ai_video_chunk(
                task_id=task_id,
                chunk_index=index,
                start_time=float(segment.get("start") or 0),
                end_time=float(segment.get("end") or 0),
                status="pending",
                transcript=str(segment.get("transcript") or ""),
                frame_count=len(segment.get("keyframes") or []),
                grid_uri=grid_uri,
                meta={"segment_id": segment.get("segment_id") or "", "time_range": segment.get("time_range") or ""},
            )

    def _segment_index(self, segment: dict[str, Any]) -> int:
        raw_id = str(segment.get("segment_id") or "")
        digits = "".join(char for char in raw_id if char.isdigit())
        if digits:
            return max(1, int(digits))
        return max(1, int(segment.get("chunk_index") or segment.get("index") or 1))

    def _record_model_run(
        self,
        *,
        task_id: str,
        purpose: str,
        chunk_id: str = "",
        input_uri: str = "",
        output_uri: str = "",
        status: str = "done",
        latency_ms: int = 0,
        error_message: str = "",
        usage: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        if not task_id:
            return
        usage = usage or {}
        try:
            run_meta = self._model_run_meta_from_usage(usage)
            record_ai_model_run(
                task_id=task_id,
                chunk_id=chunk_id,
                provider=provider or active_ai_provider(self.provider) or self.provider,
                model=model or self.gemini_model,
                purpose=purpose,
                prompt_version=os.getenv("AI_VIDEO_PROMPT_VERSION", "default"),
                input_uri=input_uri,
                output_uri=output_uri,
                status=status,
                latency_ms=latency_ms,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                error_message=error_message,
                meta=run_meta,
            )
        except Exception:
            pass

    def _model_run_meta_from_usage(self, usage: dict[str, Any]) -> dict[str, Any]:
        allowed_keys = (
            "action",
            "fallback_from",
            "fallback_error",
            "fallback_provider",
            "latency_ms",
        )
        return {key: usage.get(key) for key in allowed_keys if usage.get(key) not in (None, "")}

    def _consume_last_model_usage(self) -> dict[str, Any]:
        usage = getattr(self, "_last_model_usage", {}) or {}
        self._last_model_usage = {}
        return usage

    def _last_model_provider(self, fallback: str = "") -> str:
        return str(getattr(self, "_last_model_provider_value", "") or fallback)

    def _last_model_name(self, fallback: str = "") -> str:
        return str(getattr(self, "_last_model_name_value", "") or fallback)

    def _normalize_genre(self, value: Any) -> str:
        return normalize_genre(value)

    def _infer_genre(self, video: dict[str, Any], evidence: dict[str, Any] | None = None) -> str:
        return infer_genre(video, evidence)

    def _genre_profile(self, genre: str) -> dict[str, str]:
        return genre_profile(genre)

    def _prompt_context(self, video: dict[str, Any], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        return prompt_context(video, evidence)

    def _segment_breakdown_prompt(self, video: dict[str, Any], segment: dict[str, Any]) -> str:
        return build_segment_breakdown_prompt(video, segment)

    def _global_breakdown_prompt(
        self,
        video: dict[str, Any],
        *,
        evidence: dict[str, Any],
        segment_breakdowns: list[dict[str, Any]],
    ) -> str:
        return build_global_breakdown_prompt(
            video,
            evidence=evidence,
            segment_breakdowns=segment_breakdowns,
            prompt_template=self.analysis_prompt,
        )

    def _segment_image_paths(self, segment: dict[str, Any]) -> list[str]:
        grid = segment.get("keyframe_grid") or {}
        image_path = grid.get("image_path") if isinstance(grid, dict) else ""
        if image_path and Path(image_path).exists():
            return [str(image_path)]
        return []

    def _generate_text_json(
        self,
        prompt: str,
        *,
        action: str,
        image_paths: list[str] | None = None,
        route: AiVideoProviderRoute | None = None,
    ) -> str:
        route = route or self._provider_route()
        self._last_model_provider_value = route.provider or active_ai_provider(self.provider) or self.provider
        self._last_model_name_value = self.gemini_model
        if route.family == "openai_compatible_relay":
            return self._generate_text_with_openai_compatible_relay(
                prompt=prompt,
                model=self.gemini_model,
                action=action,
                image_paths=image_paths,
                route=route,
            )
        if route.family == "gemini_relay":
            return self._generate_text_with_relay(
                prompt=prompt,
                model=self.gemini_model,
                action=action,
                image_paths=image_paths,
                route=route,
            )
        raise RuntimeError(route.error_message or "Gemini official/native access is disabled. Configure Yunwu or another relay provider.")

    def _generate_global_summary_json(
        self,
        prompt: str,
        *,
        action: str,
        route: AiVideoProviderRoute | None = None,
    ) -> str:
        if self.summary_provider == "deepseek":
            try:
                return self._generate_text_with_deepseek(prompt=prompt, action=action)
            except Exception as exc:
                if self.summary_fallback_provider not in {"vision", "gemini", "relay"}:
                    raise
                fallback_text = call_generate_text_hook(
                    self._generate_text_json,
                    prompt,
                    action=f"{action} (fallback)",
                    route=route,
                )
                self._last_model_usage["fallback_from"] = "deepseek"
                self._last_model_usage["fallback_error"] = f"{type(exc).__name__}: {exc}"
                self._last_model_usage["fallback_provider"] = self._last_model_provider("global_breakdown")
                return fallback_text
        return call_generate_text_hook(self._generate_text_json, prompt, action=action, route=route)

    def _generate_text_with_openai_compatible_relay(
        self,
        *,
        prompt: str,
        model: str,
        action: str,
        image_paths: list[str] | None = None,
        route: AiVideoProviderRoute | None = None,
    ) -> str:
        route = route or self._provider_route()
        client = OpenAICompatibleRelayClient(base_url=route.base_url, api_key=route.api_key, model=model)
        started = time.perf_counter()
        response = client.generate_text(
            prompt=prompt,
            image_paths=image_paths or [],
            model=model,
            system_prompt="You are a short-video commercial analysis assistant. Return valid JSON only.",
        )
        self._last_model_usage = normalized_usage(
            response.usage,
            action=action,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_token_keys=("prompt_tokens", "input_tokens"),
            output_token_keys=("completion_tokens", "output_tokens"),
        )
        self._last_model_provider_value = "openai_compatible_relay"
        self._last_model_name_value = model
        return response.text

    def _generate_text_with_deepseek(self, *, prompt: str, action: str) -> str:
        client = DeepSeekChatClient(model=self.summary_model)
        started = time.perf_counter()
        response = client.generate_summary(prompt=prompt, model=self.summary_model)
        self._last_model_usage = normalized_usage(
            response.usage,
            action=action,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_token_keys=("prompt_tokens", "input_tokens"),
            output_token_keys=("completion_tokens", "output_tokens"),
        )
        self._last_model_provider_value = "deepseek"
        self._last_model_name_value = self.summary_model
        return response.text

    def _generate_text_with_relay(
        self,
        *,
        prompt: str,
        model: str,
        action: str,
        image_paths: list[str] | None = None,
        route: AiVideoProviderRoute | None = None,
    ) -> str:
        route = route or self._provider_route()
        client = GeminiGenerateContentRelayClient(
            base_url=route.base_url,
            api_key=route.api_key,
            model=model,
        )
        started = time.perf_counter()
        response = client.generate_text(
            prompt=prompt,
            image_paths=image_paths or [],
            model=model,
            system_instruction="You are a short-video commercial analysis assistant. Return valid JSON only.",
        )
        self._last_model_usage = normalized_usage(
            response.usage,
            action=action,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_token_keys=("promptTokenCount", "prompt_tokens", "input_tokens"),
            output_token_keys=("candidatesTokenCount", "completion_tokens", "output_tokens"),
        )
        self._last_model_provider_value = "gemini_generate_content_relay"
        self._last_model_name_value = model
        return response.text

    def _parse_segment_json(self, text: str, segment: dict[str, Any]) -> dict[str, Any]:
        return parse_segment_json(text, segment)

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
            self._check_cancelled(evidence_path.parent.name)
            screenshots = []
            for item in self._highlight_items(segment):
                self._check_cancelled(evidence_path.parent.name)
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
        *,
        route: AiVideoProviderRoute | None = None,
        progress: Callable[[int, str], None] | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        prompt = prompt or self._analysis_prompt(video)
        route = route or self._provider_route()
        if route.family == "openai_compatible_relay":
            raise RuntimeError(
                "OpenAI-compatible relay does not support direct full-video upload in this adapter. "
                "Use AI_VIDEO_PIPELINE_MODE=evidence so the system sends transcript chunks plus keyframe grids."
            )
        if route.family != "gemini_relay":
            raise RuntimeError(route.error_message or "Gemini official/native access is disabled. Configure Yunwu or another relay provider.")
        return self._gemini_relay_result(video, route=route, progress=progress, prompt=prompt)

    def _gemini_relay_result(
        self,
        video: dict[str, Any],
        *,
        route: AiVideoProviderRoute | None = None,
        progress: Callable[[int, str], None] | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        prompt = prompt or self._analysis_prompt(video)
        route = route or self._provider_route()
        if not route.api_key:
            raise RuntimeError(route.error_message or "Set GEMINI_RELAY_API_KEY in .env before using Gemini relay.")
        if progress:
            progress(20, "定位或下载视频文件")
        video_path = self._resolve_video_file(video)
        if progress:
            progress(45, "准备 Gemini 中转站视频数据")
        text = self._generate_with_relay(
            video_path=video_path,
            prompt=prompt,
            model=self.gemini_model,
            route=route,
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
        route: AiVideoProviderRoute | None = None,
        system_instruction: str | None = None,
    ) -> str:
        route = route or self._provider_route()
        client = GeminiGenerateContentRelayClient(
            base_url=route.base_url,
            api_key=route.api_key,
            model=model,
        )
        started = time.perf_counter()
        response = client.generate_text(
            prompt=prompt,
            video_path=video_path,
            model=model,
            system_instruction=system_instruction
            or "You are a short-video commercial analysis assistant. Analyze the video and return valid JSON only.",
        )
        self._last_model_usage = normalized_usage(
            response.usage,
            action=action,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_token_keys=("promptTokenCount", "prompt_tokens", "input_tokens"),
            output_token_keys=("candidatesTokenCount", "completion_tokens", "output_tokens"),
        )
        self._last_model_provider_value = "gemini_generate_content_relay"
        self._last_model_name_value = model
        return response.text

    def _provider_route(
        self,
        provider: str | None = None,
        *,
        pipeline_mode: str | None = None,
    ) -> AiVideoProviderRoute:
        return resolve_ai_video_provider_route(
            provider or self.provider,
            active_provider=self.provider,
            pipeline_mode=pipeline_mode or self.pipeline_mode,
        )

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
        response = get_with_retries(
            url,
            headers=headers,
            stream=True,
            timeout=default_timeout_seconds("download"),
            max_retries=default_max_retries("download"),
            cancel_check=lambda: self._check_cancelled(str(video.get("task_id") or video.get("job_id") or "")) if (video.get("task_id") or video.get("job_id")) else None,
        )
        response.raise_for_status()
        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if chunk:
                    file.write(chunk)
        return target

    def _analysis_prompt(self, video: dict[str, Any]) -> str:
        return build_analysis_prompt(video, self.analysis_prompt)

    def _clean_prompt(self, prompt: str) -> str:
        return clean_prompt(prompt)

    def _parse_model_json(self, text: str) -> dict[str, Any]:
        return parse_model_json(text)

    def _mock_result(self, video: dict[str, Any]) -> dict[str, Any]:
        desc = video.get("desc") or video.get("title") or "未命名视频"
        author = video.get("author") or {}
        author_name = author.get("nickname") if isinstance(author, dict) else author
        context = self._prompt_context(video)
        profile = context["genre_profile"]
        return {
            "genre": context["genre"],
            "summary": f"待接入真实模型。当前已接收视频《{desc}》，作者：{author_name or '未知'}；真实模型会按{profile['label']}赛道输出爆款公式、跨赛道改编和风险控制。",
            "content_identity": {
                "track": profile["label"],
                "niche_fit": "判断该结构适合迁移到哪些赛道，并说明可替换变量。",
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
                "shot_structure": f"按赛道典型节奏拆解：{profile['timeline']}。",
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
                "cross_genre_variants": "输出至少 3 个跨赛道改写方向，例如美妆、知识科普、剧情、探店、好物推荐。",
                "mysticism_variant": "迁移到玄学方向，但避免绝对化财富、情感、疗效承诺。",
                "ai_pet_variant": "迁移到 AI 小动物方向，设计动物角色、连续剧情和反差冲突。",
                "ai_commerce_variant": "迁移到 AI 带货方向，匹配产品、植入场景、证明方式和转化口令。",
                "difficulty": "低/中/高，说明制作难点。",
                "priority": "低/中/高，说明是否值得优先模仿。",
            },
            "standard_remake_template": "【开头】[人群] 在 [场景] 遇到 [痛点/冲突]；【推进】用 [证据/对比/反转] 建立可信度；【收束】给出 [解决路径/情绪释放/利益点]；【CTA】引导 [评论/收藏/求链接/到店/下单]。",
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
