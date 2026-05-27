from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import importlib.util
import sys
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from integrations.ai_video_analysis.audio_publication import configured_publisher_mode, tos_config_status
from integrations.ai_video_analysis.http_policy import default_max_retries, env_float, env_int, get_with_retries
from integrations.ai_video_analysis.transcribers import resolve_transcriber


VIDEO_URL_REFRESH_STATUS_CODES = {401, 403, 404, 410}


class NonRetryableEvidenceError(RuntimeError):
    """Evidence errors that are deterministic for the current input file."""


class AudioExtractionTimeoutError(NonRetryableEvidenceError):
    pass


class VideoEvidencePipeline:
    """Build transcript/keyframe evidence so long videos can be analyzed in chunks."""

    def __init__(
        self,
        *,
        output_dir: Path,
        segment_seconds: int | None = None,
        keyframe_interval_seconds: int | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.segment_seconds = segment_seconds or int(os.getenv("AI_VIDEO_SEGMENT_SECONDS", "90"))
        self.min_chunk_seconds = float(os.getenv("AI_VIDEO_MIN_CHUNK_SECONDS", "45") or 45)
        self.target_chunk_seconds = float(os.getenv("AI_VIDEO_TARGET_CHUNK_SECONDS", str(self.segment_seconds)) or self.segment_seconds)
        self.max_chunk_seconds = float(os.getenv("AI_VIDEO_MAX_CHUNK_SECONDS", "150") or 150)
        self.chunk_overlap_seconds = float(os.getenv("AI_VIDEO_CHUNK_OVERLAP_SECONDS", "4") or 4)
        self.chunk_pause_tolerance_seconds = float(os.getenv("AI_VIDEO_CHUNK_PAUSE_TOLERANCE_SECONDS", "1.2") or 1.2)
        self.chunk_pause_bonus_seconds = float(os.getenv("AI_VIDEO_CHUNK_PAUSE_BONUS_SECONDS", "3.0") or 3.0)
        self.silent_segment_seconds = int(os.getenv("AI_VIDEO_SILENT_SEGMENT_SECONDS", "6") or 6)
        self.keyframe_interval_seconds = keyframe_interval_seconds or int(os.getenv("AI_VIDEO_KEYFRAME_INTERVAL_SECONDS", "30"))
        self.frame_extract_mode = os.getenv("AI_VIDEO_FRAME_EXTRACT_MODE", "scene").lower()
        self.scene_threshold = float(os.getenv("AI_VIDEO_SCENE_THRESHOLD", "0.10") or 0.10)
        self.mpdecimate_sample_fps = float(os.getenv("AI_VIDEO_MPDECIMATE_SAMPLE_FPS", "1") or 1)
        self.mpdecimate_max = os.getenv("AI_VIDEO_MPDECIMATE_MAX", "0")
        self.mpdecimate_hi = os.getenv("AI_VIDEO_MPDECIMATE_HI", "768")
        self.mpdecimate_lo = os.getenv("AI_VIDEO_MPDECIMATE_LO", "320")
        self.mpdecimate_frac = os.getenv("AI_VIDEO_MPDECIMATE_FRAC", "0.33")
        self.frame_min_interval_seconds = float(os.getenv("AI_VIDEO_FRAME_MIN_INTERVAL_SECONDS", "1.0") or 1.0)
        self.frame_fallback_interval_seconds = float(os.getenv("AI_VIDEO_FRAME_FALLBACK_INTERVAL_SECONDS", "8.0") or 8.0)
        self.frame_max_per_chunk = int(os.getenv("AI_VIDEO_FRAME_MAX_PER_CHUNK", os.getenv("AI_VIDEO_GRID_MAX_FRAMES", "12")) or 12)
        self.phash_dedup_enabled = os.getenv("AI_VIDEO_PHASH_DEDUP_ENABLED", "false").lower() in {"1", "true", "yes"}
        self.phash_dedup_threshold = int(os.getenv("AI_VIDEO_PHASH_DEDUP_THRESHOLD", "6") or 6)
        self.ocr_enabled = os.getenv("AI_VIDEO_OCR_ENABLED", "false").lower() in {"1", "true", "yes"}
        self.ffmpeg = self.resolve_ffmpeg_binary(os.getenv("FFMPEG_BINARY") or "ffmpeg")
        self.ffprobe = os.getenv("FFPROBE_BINARY") or "ffprobe"
        self.resume_enabled = os.getenv("AI_VIDEO_RESUME_ENABLED", "true").lower() not in {"0", "false", "no"}
        self.cancel_check: Callable[[], None] | None = None

    def build(
        self,
        video: dict[str, Any],
        *,
        job_id: str,
        progress: Callable[[int, str], None] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        previous_cancel_check = self.cancel_check
        self.cancel_check = cancel_check
        try:
            return self._build(video, job_id=job_id, progress=progress)
        finally:
            self.cancel_check = previous_cancel_check

    def _build(
        self,
        video: dict[str, Any],
        *,
        job_id: str,
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        evidence_dir = self.output_dir / "evidence" / job_id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_dir / "analysis_evidence.json"

        self.check_cancelled()
        if progress:
            progress(12, f"创建证据包目录：{evidence_dir}")
        video_path = self.resolve_video_file(video, evidence_dir=evidence_dir, progress=progress)
        self.check_cancelled()
        if progress:
            progress(20, f"视频文件准备完成：{video_path.name}")
        duration = self.probe_duration(video_path)
        self.check_cancelled()
        if progress:
            duration_text = self.format_time(duration) if duration else "未知"
            progress(21, f"读取视频时长：{duration_text}")

        if progress:
            progress(22, "开始提取音频：FFmpeg 转为 16k 单声道 wav")
        audio_path = evidence_dir / "audio.wav"
        if self.resume_enabled and self.valid_file(audio_path):
            if progress:
                progress(32, f"断点续跑：复用已提取音频 {audio_path.name}")
        else:
            self.extract_audio(video_path, audio_path, duration=duration, progress=progress)
        self.check_cancelled()
        if progress:
            progress(32, f"音频提取完成：{audio_path.name}")

        if progress:
            progress(34, "开始转写音频：加载 Whisper 模型")
        transcript_path = evidence_dir / "transcript.json"
        transcript_raw_path = evidence_dir / "transcript_raw_doubao.json"
        if self.resume_enabled and transcript_path.exists():
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            if progress:
                progress(48, f"断点续跑：复用已转写文本 {len(transcript.get('segments') or [])} 个片段")
        else:
            transcript = self.transcribe(audio_path, duration=duration, progress=progress)
            self.check_cancelled()
            raw_response = transcript.pop("raw_response", None)
            if raw_response is not None:
                transcript_raw_path.write_text(json.dumps(raw_response, ensure_ascii=False, indent=2), encoding="utf-8")
                transcript["raw_response_path"] = str(transcript_raw_path)
            transcript_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        if progress:
            progress(48, f"转写完成：{len(transcript.get('segments') or [])} 个时间戳片段")

        if progress:
            progress(50, f"按 {self.segment_seconds} 秒切分转写文本")
        self.check_cancelled()
        analysis_segments = self.chunk_transcript(
            transcript.get("segments") or [],
            duration=duration,
            pause_points=transcript.get("pause_points") or [],
            words=transcript.get("words") or [],
        )
        if progress:
            progress(52, f"文本切分完成：{len(analysis_segments)} 个分析片段")

        if progress:
            progress(54, f"开始抽取关键帧：每段开头 + 每 {self.keyframe_interval_seconds} 秒")
        keyframes_path = evidence_dir / "keyframes.json"
        if self.resume_enabled and keyframes_path.exists():
            keyframes = json.loads(keyframes_path.read_text(encoding="utf-8"))
            if progress:
                progress(58, f"断点续跑：复用已抽取关键帧 {len(keyframes)} 张")
        else:
            keyframes = self.extract_keyframes(video_path, analysis_segments, evidence_dir / "keyframes", progress=progress)
            self.check_cancelled()
            keyframes_path.write_text(json.dumps(keyframes, ensure_ascii=False, indent=2), encoding="utf-8")
        if progress:
            progress(58, f"关键帧抽取完成：{len(keyframes)} 张")
        keyframes_by_segment = self.assign_keyframes(analysis_segments, keyframes)
        for segment in analysis_segments:
            segment["keyframes"] = keyframes_by_segment.get(segment["segment_id"], [])

        if progress:
            progress(58, "生成带时间戳的关键帧网格图")
        self.check_cancelled()
        self.create_segment_grids(analysis_segments, evidence_dir / "keyframe_grids", progress=progress)
        self.check_cancelled()

        douyin_target_context = video.get("douyin_target_context") if isinstance(video.get("douyin_target_context"), dict) else {}
        metadata = {
            "video_title": video.get("desc") or video.get("title") or "",
            "author": self.author_name(video),
            "aweme_id": video.get("aweme_id") or video.get("id") or "",
            "genre": video.get("genre") or douyin_target_context.get("genre") or "",
            "duration": duration,
            "video_path": str(video_path),
            "audio_path": str(audio_path),
            "audio_url": str(transcript.get("audio_url") or ""),
            "statistics": video.get("statistics") or {},
            "derived_metrics": video.get("derived_metrics") or {},
        }
        evidence = {
            "schema_version": "2.0",
            "metadata": metadata,
            "douyin_target": video.get("douyin_target_context") or {},
            "transcript": transcript,
            "asr": {
                "provider": transcript.get("provider") or "",
                "model": transcript.get("model") or "",
                "language": transcript.get("language") or "",
                "audio_url": transcript.get("audio_url") or "",
                "raw_response_path": transcript.get("raw_response_path") or "",
                "doc_url": os.getenv("AI_VIDEO_ASR_DOC_URL") or "https://www.volcengine.com/docs/6561/1354868?lang=zh",
            },
            "analysis_segments": analysis_segments,
            "keyframes": keyframes,
            "checkpoints": {
                "audio_path": str(audio_path),
                "transcript_path": str(transcript_path),
                "transcript_raw_path": str(transcript.get("raw_response_path") or ""),
                "keyframes_path": str(keyframes_path),
            },
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
        }
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        evidence["evidence_path"] = str(evidence_path)
        if progress:
            progress(59, f"证据包已保存：{evidence_path}")
        return evidence

    def check_cancelled(self) -> None:
        if self.cancel_check:
            self.cancel_check()

    def dependency_status(self) -> dict[str, Any]:
        faster_whisper_ready = bool(importlib.util.find_spec("faster_whisper"))
        openai_whisper_ready = bool(importlib.util.find_spec("whisper"))
        imageio_ffmpeg_ready = bool(importlib.util.find_spec("imageio_ffmpeg"))
        tos_status = tos_config_status()
        doubao_status: dict[str, Any] = {}
        if (os.getenv("AI_VIDEO_TRANSCRIBER", "auto").lower() in {"doubao", "doubao_file_asr", "volcengine", "volcengine_asr"}):
            from integrations.ai_video_analysis.doubao_asr import doubao_asr_status

            doubao_status = doubao_asr_status()
        return {
            "python_executable": sys.executable,
            "mode": os.getenv("AI_VIDEO_PIPELINE_MODE", "auto"),
            "transcriber": os.getenv("AI_VIDEO_TRANSCRIBER", "auto"),
            "transcribe_model": os.getenv("AI_VIDEO_TRANSCRIBE_MODEL", "small"),
            "asr_upload_mode": os.getenv("AI_VIDEO_ASR_UPLOAD_MODE") or os.getenv("VOLCENGINE_ASR_UPLOAD_MODE") or "url",
            "asr_public_dir": os.getenv("AI_VIDEO_ASR_PUBLIC_DIR") or "",
            "asr_public_base_url": os.getenv("AI_VIDEO_ASR_PUBLIC_BASE_URL") or "",
            "asr_publisher": configured_publisher_mode(),
            "asr_doubao": doubao_status,
            "tos_config": tos_status,
            "tos_bucket_configured": tos_status["bucket_configured"],
            "tos_sdk_ready": bool(importlib.util.find_spec("tos")),
            "ffmpeg_binary": self.ffmpeg or "",
            "ffmpeg_ready": bool(self.ffmpeg),
            "ffprobe_binary": self.ffprobe,
            "ffprobe_ready": bool(shutil.which(self.ffprobe)),
            "faster_whisper_ready": faster_whisper_ready,
            "openai_whisper_ready": openai_whisper_ready,
            "imageio_ffmpeg_ready": imageio_ffmpeg_ready,
            "pillow_ready": bool(importlib.util.find_spec("PIL")),
            "transcriber_ready": faster_whisper_ready or openai_whisper_ready,
            "resume_enabled": self.resume_enabled,
            "segment_seconds": self.segment_seconds,
            "min_chunk_seconds": self.min_chunk_seconds,
            "target_chunk_seconds": self.target_chunk_seconds,
            "max_chunk_seconds": self.max_chunk_seconds,
            "chunk_overlap_seconds": self.chunk_overlap_seconds,
            "chunk_pause_tolerance_seconds": self.chunk_pause_tolerance_seconds,
            "chunk_pause_bonus_seconds": self.chunk_pause_bonus_seconds,
            "silent_segment_seconds": self.silent_segment_seconds,
            "keyframe_interval_seconds": self.keyframe_interval_seconds,
            "frame_extract_mode": self.frame_extract_mode,
            "scene_threshold": self.scene_threshold,
            "mpdecimate_sample_fps": self.mpdecimate_sample_fps,
            "mpdecimate_max": self.mpdecimate_max,
            "mpdecimate_hi": self.mpdecimate_hi,
            "mpdecimate_lo": self.mpdecimate_lo,
            "mpdecimate_frac": self.mpdecimate_frac,
            "frame_min_interval_seconds": self.frame_min_interval_seconds,
            "frame_fallback_interval_seconds": self.frame_fallback_interval_seconds,
            "frame_max_per_chunk": self.frame_max_per_chunk,
            "phash_dedup_enabled": self.phash_dedup_enabled,
            "phash_dedup_threshold": self.phash_dedup_threshold,
            "ocr_enabled": self.ocr_enabled,
        }

    def resolve_video_file(
        self,
        video: dict[str, Any],
        *,
        evidence_dir: Path,
        progress: Callable[[int, str], None] | None = None,
    ) -> Path:
        for key in ["local_path", "path", "file_path"]:
            value = video.get(key)
            if value and Path(value).exists():
                if progress:
                    progress(15, f"使用本地视频文件：{Path(value).name}")
                return Path(value)

        urls = self.video_url_candidates(video)
        if not urls:
            raise RuntimeError("没有找到本地视频路径或 source_video_url，无法生成转写证据包。")

        target = evidence_dir / f"{video.get('aweme_id') or video.get('id') or int(time.time())}.mp4"
        if target.exists() and target.stat().st_size > 0:
            if progress:
                progress(16, f"复用已下载视频：{target.name}")
            return target
        if target.exists():
            target.unlink()

        if progress:
            progress(14, "开始下载视频到证据包目录")
        headers = self.video_download_headers(video)
        self.download_video_file(video, urls, target, headers=headers, progress=progress)
        return target

    def download_video_file(
        self,
        video: dict[str, Any],
        urls: list[str],
        target: Path,
        *,
        headers: dict[str, str],
        progress: Callable[[int, str], None] | None = None,
    ) -> None:
        attempted: set[str] = set()
        refreshed = False
        candidate_urls = urls
        last_error: Exception | None = None
        while True:
            response = self.try_video_urls(video, candidate_urls, headers=headers, attempted=attempted)
            if response is None:
                if not refreshed:
                    refreshed = True
                    if progress:
                        progress(14, "视频下载地址不可用，正在重新获取抖音下载地址。")
                    candidate_urls = self.refresh_douyin_video_urls(video)
                    if candidate_urls:
                        continue
                if last_error is not None:
                    raise last_error
                raise RuntimeError("没有可下载的视频地址。")

            if getattr(response, "status_code", 0) in VIDEO_URL_REFRESH_STATUS_CODES:
                self.close_response(response)
                if not refreshed:
                    refreshed = True
                    if progress:
                        progress(14, "视频直链失效，正在重新获取抖音下载地址。")
                    candidate_urls = self.refresh_douyin_video_urls(video)
                    if candidate_urls:
                        continue
                response.raise_for_status()

            try:
                response.raise_for_status()
                self.write_video_response(response, target, progress=progress)
                return
            except Exception as exc:
                last_error = exc
                self.close_response(response)
                if not self.should_retry_video_download_error(exc):
                    raise
                if progress:
                    progress(14, "视频下载流超时或中断，正在切换备用地址。")

    def write_video_response(
        self,
        response: Any,
        target: Path,
        *,
        progress: Callable[[int, str], None] | None = None,
    ) -> None:
        total = int(response.headers.get("content-length") or 0)
        downloaded = 0
        last_percent = -1
        last_progress_bytes = 0
        progress_step = max(1024 * 1024, env_int("AI_VIDEO_DOWNLOAD_PROGRESS_MB_STEP", 8) * 1024 * 1024)
        max_seconds = max(0.0, env_float("AI_VIDEO_DOWNLOAD_MAX_SECONDS", 600.0))
        started_at = time.monotonic()
        partial = target.with_name(f"{target.name}.part")
        partial.unlink(missing_ok=True)
        try:
            with partial.open("wb") as file:
                for chunk in response.iter_content(chunk_size=self.video_download_chunk_bytes()):
                    self.check_cancelled()
                    if max_seconds and time.monotonic() - started_at >= max_seconds:
                        raise TimeoutError(f"Video download exceeded AI_VIDEO_DOWNLOAD_MAX_SECONDS={max_seconds:g}")
                    if not chunk:
                        continue
                    file.write(chunk)
                    downloaded += len(chunk)
                    if progress and total:
                        percent = min(19, 14 + int(downloaded * 5 / total))
                        if percent != last_percent or downloaded - last_progress_bytes >= progress_step:
                            last_percent = percent
                            last_progress_bytes = downloaded
                            progress(percent, f"下载视频中：{downloaded / 1024 / 1024:.1f}MB / {total / 1024 / 1024:.1f}MB")
            if downloaded <= 0:
                raise RuntimeError("视频下载响应没有返回文件内容。")
            partial.replace(target)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        finally:
            self.close_response(response)

    def video_url_candidates(self, video: dict[str, Any]) -> list[str]:
        raw = video.get("raw") if isinstance(video.get("raw"), dict) else {}
        raw_video = raw.get("video") if isinstance(raw.get("video"), dict) else {}
        normalized_video = video.get("video") if isinstance(video.get("video"), dict) else {}
        download_urls = video.get("download_urls") if isinstance(video.get("download_urls"), dict) else {}
        return self.unique_video_urls(
            [
                video.get("play_url"),
                video.get("video_url"),
                download_urls.get("play_addr"),
                download_urls.get("play_addr_h264"),
                download_urls.get("play_addr_bytevc1"),
                normalized_video.get("play_addr"),
                normalized_video.get("play_addr_h264"),
                normalized_video.get("play_addr_bytevc1"),
                raw_video.get("play_addr"),
                raw_video.get("play_addr_h264"),
                raw_video.get("play_addr_bytevc1"),
                video.get("source_video_url"),
                video.get("download_url"),
                download_urls.get("download_addr"),
                normalized_video.get("download_addr"),
                raw_video.get("download_addr"),
            ]
        )

    @classmethod
    def unique_video_urls(cls, values: list[Any]) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for value in values:
            for url in cls.iter_video_url_values(value):
                if url in seen:
                    continue
                urls.append(url)
                seen.add(url)
        return urls

    @classmethod
    def iter_video_url_values(cls, value: Any):
        if isinstance(value, str):
            url = value.strip()
            if url.startswith(("http://", "https://")):
                yield url
            return
        if isinstance(value, dict):
            for key in (
                "url_list",
                "url_list_1",
                "urls",
                "url",
                "download_url",
                "play_url",
                "source_video_url",
                "main_url",
                "backup_url",
            ):
                if key in value:
                    yield from cls.iter_video_url_values(value.get(key))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                yield from cls.iter_video_url_values(item)

    def download_video_response(
        self,
        video: dict[str, Any],
        urls: list[str],
        *,
        headers: dict[str, str],
        progress: Callable[[int, str], None] | None = None,
    ):
        attempted: set[str] = set()
        failed_response = self.try_video_urls(video, urls, headers=headers, attempted=attempted)
        if failed_response is None:
            raise RuntimeError("没有可下载的视频地址。")
        if getattr(failed_response, "status_code", 0) not in VIDEO_URL_REFRESH_STATUS_CODES:
            failed_response.raise_for_status()
            return failed_response

        if progress:
            progress(14, "视频直链失效，正在重新获取抖音下载地址。")
        refreshed_urls = self.refresh_douyin_video_urls(video)
        refreshed_response = self.try_video_urls(video, refreshed_urls, headers=headers, attempted=attempted)
        if refreshed_response is not None and getattr(refreshed_response, "status_code", 0) not in VIDEO_URL_REFRESH_STATUS_CODES:
            self.close_response(failed_response)
            refreshed_response.raise_for_status()
            return refreshed_response

        if refreshed_response is not None:
            refreshed_response.raise_for_status()
        failed_response.raise_for_status()
        return failed_response

    def try_video_urls(self, video: dict[str, Any], urls: list[str], *, headers: dict[str, str], attempted: set[str]):
        last_response = None
        last_error: Exception | None = None
        for url in urls:
            if url in attempted:
                continue
            attempted.add(url)
            try:
                response = get_with_retries(
                    url,
                    headers=self.video_download_headers(video, url=url, base=headers),
                    stream=True,
                    timeout=self.video_download_timeout(),
                    max_retries=default_max_retries("download"),
                    cancel_check=self.check_cancelled,
                )
            except Exception as exc:
                last_error = exc
                continue
            if getattr(response, "status_code", 0) not in VIDEO_URL_REFRESH_STATUS_CODES:
                self.close_response(last_response)
                return response
            self.close_response(last_response)
            last_response = response
        if last_response is None and last_error is not None:
            raise last_error
        return last_response

    def refresh_douyin_video_urls(self, video: dict[str, Any]) -> list[str]:
        aweme_id = str(video.get("aweme_id") or "").strip()
        if not aweme_id:
            return []

        try:
            from integrations.douyin_provider.factory import get_douyin_provider

            refreshed = get_douyin_provider().get_one_video(aweme_id, prefer_cache=False)
        except Exception:
            return []

        refreshed_video = refreshed.get("video") if isinstance(refreshed.get("video"), dict) else {}
        for key in ("source_video_url", "download_url", "video_url", "play_url"):
            value = refreshed_video.get(key)
            if value:
                video[key] = value

        download_urls = refreshed.get("download_urls") if isinstance(refreshed.get("download_urls"), dict) else {}
        return self.unique_video_urls(
            [
                download_urls.get("play_addr"),
                download_urls.get("play_addr_h264"),
                download_urls.get("play_addr_bytevc1"),
                refreshed_video.get("play_url"),
                refreshed_video.get("video_url"),
                refreshed_video.get("source_video_url"),
                refreshed_video.get("download_url"),
                download_urls.get("download_addr"),
            ]
        )

    def video_download_headers(
        self,
        video: dict[str, Any],
        *,
        url: str | None = None,
        base: dict[str, str] | None = None,
    ) -> dict[str, str]:
        headers = dict(base or {})
        referer = self.video_referer(video)
        headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/132.0.0.0 Safari/537.36"
                ),
                "Referer": referer,
                "Origin": "https://www.douyin.com",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Sec-Fetch-Dest": "video",
                "Sec-Fetch-Mode": "no-cors",
                "Sec-Fetch-Site": "cross-site",
                "Connection": "keep-alive",
            }
        )
        range_header = os.getenv("AI_VIDEO_DOWNLOAD_RANGE_HEADER", "bytes=0-").strip()
        if range_header:
            headers["Range"] = range_header
        cookie = self.video_download_cookie(url)
        if cookie:
            headers["Cookie"] = cookie
        return headers

    @staticmethod
    def video_referer(video: dict[str, Any]) -> str:
        share_info = video.get("share_info") if isinstance(video.get("share_info"), dict) else {}
        referer = str(
            share_info.get("share_url")
            or video.get("share_url")
            or video.get("work_url")
            or ""
        ).strip()
        if referer:
            return referer
        aweme_id = str(video.get("aweme_id") or video.get("id") or "").strip()
        if aweme_id:
            return f"https://www.douyin.com/video/{aweme_id}"
        return "https://www.douyin.com/"

    @staticmethod
    def video_download_cookie(url: str | None = None) -> str:
        include_cookie = os.getenv("AI_VIDEO_DOWNLOAD_INCLUDE_DOUYIN_COOKIE", "true").strip().lower()
        if include_cookie in {"0", "false", "no"}:
            return ""
        if url:
            host = urlparse(url).hostname or ""
            if not any(marker in host for marker in ("douyin", "zjcdn", "byte", "bytedance", "snssdk")):
                return ""
        for name in ("DY_COOKIES", "DOUYIN_SPIDER_COOKIE", "TIKHUB_DOUYIN_WEB_COOKIE", "DOUYIN_WEB_COOKIE"):
            cookie = str(os.getenv(name) or "").strip().strip('"').strip("'")
            if cookie:
                return cookie.replace("\\n", "").replace("\\r", "").replace("\r", "").replace("\n", "").strip()
        return ""

    @staticmethod
    def should_retry_video_download_error(exc: Exception) -> bool:
        if exc.__class__.__name__ == "AiVideoTaskCancelled":
            return False
        if isinstance(exc, (TimeoutError, requests.RequestException)):
            return True
        if isinstance(exc, RuntimeError):
            message = str(exc).lower()
            return any(
                marker in message
                for marker in (
                    "download",
                    "content",
                    "stream",
                    "stalled",
                    "timed out",
                    "timeout",
                    "文件内容",
                )
            )
        return False

    @staticmethod
    def close_response(response: Any) -> None:
        close = getattr(response, "close", None)
        if callable(close):
            close()

    @staticmethod
    def video_download_chunk_bytes() -> int:
        return max(16 * 1024, env_int("AI_VIDEO_DOWNLOAD_CHUNK_KB", 128) * 1024)

    @staticmethod
    def video_download_timeout() -> tuple[float, float]:
        return (
            max(1.0, env_float("AI_VIDEO_DOWNLOAD_CONNECT_TIMEOUT_SECONDS", 20.0)),
            max(1.0, env_float("AI_VIDEO_DOWNLOAD_READ_TIMEOUT_SECONDS", 45.0)),
        )

    def probe_duration(self, video_path: Path) -> float:
        if not shutil.which(self.ffprobe):
            return 0.0
        command = [
            self.ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ]
        try:
            completed = self.run_command_capture(command, timeout=30, check=True)
            data = json.loads(completed.stdout or "{}")
            return float((data.get("format") or {}).get("duration") or 0)
        except Exception:
            return 0.0

    def extract_audio(
        self,
        video_path: Path,
        audio_path: Path,
        *,
        duration: float = 0.0,
        progress: Callable[[int, str], None] | None = None,
    ) -> None:
        if not self.ffmpeg:
            raise RuntimeError("未找到 ffmpeg。请安装 FFmpeg，或在 .env 配置 FFMPEG_BINARY。")
        if audio_path.exists() and audio_path.stat().st_size <= 0:
            audio_path.unlink()
        legacy_temp_audio_path = audio_path.with_suffix(f"{audio_path.suffix}.part")
        if legacy_temp_audio_path.exists():
            legacy_temp_audio_path.unlink()
        suffix = audio_path.suffix or ".wav"
        temp_audio_path = audio_path.with_name(f"{audio_path.stem}.part{suffix}")
        if temp_audio_path.exists():
            temp_audio_path.unlink()
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-acodec",
            "pcm_s16le",
            "-f",
            "wav",
            str(temp_audio_path),
        ]
        if progress:
            progress(24, "FFmpeg 正在提取音频")
        timeout = self.audio_extract_timeout(duration=duration)
        try:
            self.run_command(command, "FFmpeg 音频提取失败", timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if temp_audio_path.exists():
                temp_audio_path.unlink()
            raise AudioExtractionTimeoutError(
                f"FFmpeg audio extraction timed out after {int(timeout)} seconds. video={video_path.name}"
            ) from exc
        except Exception:
            if temp_audio_path.exists() and temp_audio_path.stat().st_size <= 0:
                temp_audio_path.unlink()
            raise
        if not self.valid_file(temp_audio_path):
            if temp_audio_path.exists():
                temp_audio_path.unlink()
            raise NonRetryableEvidenceError("FFmpeg audio extraction produced an empty audio file.")
        temp_audio_path.replace(audio_path)

    @staticmethod
    def audio_extract_timeout(*, duration: float = 0.0) -> int:
        configured = env_int("AI_VIDEO_AUDIO_EXTRACT_TIMEOUT_SECONDS", 0)
        if configured > 0:
            return configured
        base = env_int("AI_VIDEO_AUDIO_EXTRACT_BASE_TIMEOUT_SECONDS", 120)
        per_minute = env_float("AI_VIDEO_AUDIO_EXTRACT_TIMEOUT_PER_VIDEO_MINUTE", 6.0)
        max_timeout = env_int("AI_VIDEO_AUDIO_EXTRACT_MAX_TIMEOUT_SECONDS", 900)
        if duration and duration > 0:
            computed = base + int((float(duration) / 60.0) * max(per_minute, 0.0))
            return max(30, min(computed, max_timeout))
        return max(30, min(300, max_timeout))

    def transcribe(
        self,
        audio_path: Path,
        *,
        duration: float = 0.0,
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        provider = os.getenv("AI_VIDEO_TRANSCRIBER", "auto").lower()
        model = os.getenv("AI_VIDEO_TRANSCRIBE_MODEL", "small")
        language = os.getenv("AI_VIDEO_TRANSCRIBE_LANGUAGE", "zh") or None
        if progress:
            progress(34, f"选择转写器 provider：{provider}")
        transcriber = resolve_transcriber(provider)
        return transcriber.transcribe(
            audio_path,
            model=model,
            language=language,
            duration=duration,
            progress=progress,
            format_time=self.format_time,
        )

    def chunk_transcript(
        self,
        transcript_segments: list[dict[str, Any]],
        *,
        duration: float = 0.0,
        pause_points: list[dict[str, Any]] | None = None,
        words: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if not transcript_segments:
            return self.chunk_silent_video(duration=duration)

        pauses = self.normalize_pause_points(pause_points or [], words=words or [])
        chunks: list[dict[str, Any]] = []
        current: list[dict[str, Any]] = []
        chunk_start = float(transcript_segments[0].get("start") or 0)
        chunk_end = chunk_start

        for item_index, item in enumerate(transcript_segments):
            start = float(item.get("start") or chunk_end)
            end = float(item.get("end") or start)
            current.append(item)
            chunk_end = end
            has_more_items = item_index < len(transcript_segments) - 1
            should_cut = current and has_more_items and (
                chunk_end - chunk_start >= self.max_chunk_seconds
                or (chunk_end - chunk_start >= self.target_chunk_seconds and chunk_end - chunk_start >= self.min_chunk_seconds)
            )
            if should_cut:
                cut_index = self.best_pause_cut_index(
                    current,
                    chunk_start=chunk_start,
                    chunk_end=chunk_end,
                    pauses=pauses,
                )
                chunk_items = current[:cut_index]
                carry_items = current[cut_index:]
                if not chunk_items:
                    chunk_items = current
                    carry_items = []
                actual_end = float(chunk_items[-1].get("end") or chunk_items[-1].get("start") or chunk_end)
                cut_reason = "pause_point" if cut_index < len(current) else "duration"
                chunks.append(self.make_chunk(len(chunks) + 1, chunk_start, actual_end, chunk_items, cut_reason=cut_reason))
                overlap_items = self.overlap_items(chunk_items, overlap_seconds=self.chunk_overlap_seconds)
                current = overlap_items + carry_items
                current = self.dedupe_transcript_items(current)
                chunk_start = float((current[0].get("start") if current else actual_end) or actual_end)
                chunk_end = float((current[-1].get("end") if current else actual_end) or actual_end)

        if current:
            chunks.append(self.make_chunk(len(chunks) + 1, chunk_start, chunk_end or duration, current, cut_reason="end"))
        return chunks

    def normalize_pause_points(self, pause_points: list[dict[str, Any]], *, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for point in pause_points:
            if not isinstance(point, dict):
                continue
            start_value = point.get("start", point.get("time"))
            end_value = point.get("end", start_value)
            start = self.float_value(start_value)
            end = self.float_value(end_value)
            duration = self.float_value(point.get("duration"))
            if duration <= 0 and end >= start:
                duration = end - start
            time_value = (start + end) / 2 if end > start else start
            if time_value > 0:
                normalized.append(
                    {
                        "time": round(time_value, 3),
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "duration": round(max(0.0, duration), 3),
                        "reason": point.get("reason") or "pause",
                    }
                )
        if normalized:
            return sorted(normalized, key=lambda item: float(item.get("time") or 0))

        previous_end: float | None = None
        threshold = float(os.getenv("AI_VIDEO_ASR_PAUSE_THRESHOLD_SECONDS", "0.5") or 0.5)
        for word in words:
            start = self.float_value(word.get("start"))
            end = self.float_value(word.get("end", start))
            if previous_end is not None:
                gap = max(0.0, start - previous_end)
                if gap >= threshold:
                    normalized.append(
                        {
                            "time": round((previous_end + start) / 2, 3),
                            "start": round(previous_end, 3),
                            "end": round(start, 3),
                            "duration": round(gap, 3),
                            "reason": "word_gap",
                        }
                    )
            previous_end = max(previous_end or 0.0, end)
        return sorted(normalized, key=lambda item: float(item.get("time") or 0))

    def best_pause_cut_index(
        self,
        items: list[dict[str, Any]],
        *,
        chunk_start: float,
        chunk_end: float,
        pauses: list[dict[str, Any]],
    ) -> int:
        if len(items) <= 1:
            return len(items)
        target_time = chunk_start + self.target_chunk_seconds
        min_time = chunk_start + self.min_chunk_seconds
        max_time = min(chunk_start + self.max_chunk_seconds, chunk_end)
        best_score: float | None = abs(chunk_end - target_time) if min_time <= chunk_end <= max_time else None
        best_index = len(items)
        for index in range(1, len(items)):
            previous = items[index - 1]
            current = items[index]
            boundary_start = self.float_value(previous.get("end", previous.get("start")))
            boundary_next = self.float_value(current.get("start", boundary_start))
            boundary_time = boundary_start
            if boundary_time < min_time or boundary_time > max_time:
                continue
            gap = max(0.0, boundary_next - boundary_start)
            nearby_pause = self.nearest_pause(boundary_time, pauses)
            pause_distance = abs(float(nearby_pause.get("time") or boundary_time) - boundary_time) if nearby_pause else 9999.0
            pause_duration = float(nearby_pause.get("duration") or 0) if nearby_pause else 0.0
            is_pause_boundary = bool(nearby_pause and pause_distance <= self.chunk_pause_tolerance_seconds)
            score = abs(boundary_time - target_time)
            if is_pause_boundary:
                score -= self.chunk_pause_bonus_seconds + pause_duration
            if gap >= float(os.getenv("AI_VIDEO_ASR_PAUSE_THRESHOLD_SECONDS", "0.5") or 0.5):
                score -= min(gap, self.chunk_pause_bonus_seconds)
            if best_score is None or score < best_score:
                best_score = score
                best_index = index
        return best_index

    def nearest_pause(self, boundary_time: float, pauses: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not pauses:
            return None
        return min(pauses, key=lambda point: abs(float(point.get("time") or 0) - boundary_time))

    def dedupe_transcript_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[float, float, str]] = set()
        for item in items:
            key = (
                round(self.float_value(item.get("start")), 3),
                round(self.float_value(item.get("end")), 3),
                str(item.get("text") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def overlap_items(self, items: list[dict[str, Any]], *, overlap_seconds: float) -> list[dict[str, Any]]:
        if not items or overlap_seconds <= 0:
            return []
        end = float(items[-1].get("end") or items[-1].get("start") or 0)
        threshold = max(0.0, end - overlap_seconds)
        selected = [item for item in items if float(item.get("end") or item.get("start") or 0) >= threshold]
        return selected[-5:]

    def chunk_silent_video(self, *, duration: float = 0.0) -> list[dict[str, Any]]:
        if duration <= 0:
            return []
        step = max(2, min(30, self.silent_segment_seconds))
        chunks: list[dict[str, Any]] = []
        start = 0.0
        while start < duration:
            end = min(duration, start + step)
            chunks.append(
                {
                    "segment_id": f"seg_{len(chunks) + 1:03d}",
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "time_range": f"{self.format_time(start)}-{self.format_time(end)}",
                    "transcript": "无语音转写；该片段按视频时长自动视觉切分。",
                    "transcript_segments": [],
                    "visual_only": True,
                }
            )
            start = end
        return chunks

    def make_chunk(
        self,
        index: int,
        start: float,
        end: float,
        items: list[dict[str, Any]],
        *,
        cut_reason: str = "",
    ) -> dict[str, Any]:
        return {
            "segment_id": f"seg_{index:03d}",
            "start": round(start, 2),
            "end": round(end, 2),
            "time_range": f"{self.format_time(start)}-{self.format_time(end)}",
            "transcript": "\n".join(str(item.get("text") or "").strip() for item in items if str(item.get("text") or "").strip()),
            "transcript_segments": items,
            "cut_reason": cut_reason,
        }

    def float_value(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def extract_keyframes(
        self,
        video_path: Path,
        segments: list[dict[str, Any]],
        output_dir: Path,
        *,
        progress: Callable[[int, str], None] | None = None,
    ) -> list[dict[str, Any]]:
        output_dir.mkdir(parents=True, exist_ok=True)
        if not self.ffmpeg:
            return []

        times = set()
        for segment in segments:
            start = float(segment.get("start") or 0)
            end = float(segment.get("end") or start)
            times.add(max(0.0, start + 1.0))
            cursor = start + self.keyframe_interval_seconds
            while cursor < end:
                times.add(cursor)
                cursor += self.keyframe_interval_seconds

        keyframes: list[dict[str, Any]] = []
        time_candidates = self.keyframe_time_candidates(video_path, segments, duration=self.probe_duration(video_path))
        for candidate in time_candidates:
            times.add(float(candidate.get("time") or 0))
        sorted_candidates = self.merge_frame_candidates(
            [{"time": seconds, "source": "interval", "scene_score": None} for seconds in times] + time_candidates
        )
        total = len(sorted_candidates)
        for index, candidate in enumerate(sorted_candidates, start=1):
            seconds = float(candidate.get("time") or 0)
            image_path = output_dir / f"frame_{index:04d}_{int(seconds):06d}_{str(candidate.get('source') or 'frame')}.jpg"
            if progress:
                percent = 54 + int(index * 4 / max(1, total))
                progress(percent, f"抽取关键帧 {index}/{total}：{self.format_time(seconds)} · {candidate.get('source') or 'frame'}")
            command = [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-ss",
                str(round(seconds, 2)),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(image_path),
            ]
            try:
                self.run_command(command, "FFmpeg 关键帧抽取失败", timeout=45)
            except (RuntimeError, subprocess.TimeoutExpired):
                if image_path.exists() and image_path.stat().st_size <= 0:
                    image_path.unlink()
                continue
            if image_path.exists() and image_path.stat().st_size > 0:
                keyframes.append(
                    {
                        "frame_id": f"frame_{index:04d}",
                        "time": round(seconds, 2),
                        "time_label": self.format_time(seconds),
                        "image_path": str(image_path),
                        "source": candidate.get("source") or "frame",
                        "scene_score": candidate.get("scene_score"),
                        "ocr_text": self.extract_frame_ocr_text(image_path),
                    }
                )
        return self.dedupe_keyframes(keyframes)

    def keyframe_time_candidates(self, video_path: Path, segments: list[dict[str, Any]], *, duration: float = 0.0) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for segment in segments:
            start = float(segment.get("start") or 0)
            end = float(segment.get("end") or start)
            candidates.append({"time": max(0.0, start + 1.0), "source": "chunk_start", "scene_score": None})
            cursor = start + max(1.0, self.frame_fallback_interval_seconds)
            while cursor < end:
                candidates.append({"time": cursor, "source": "fallback", "scene_score": None})
                cursor += max(1.0, self.frame_fallback_interval_seconds)
        if self.frame_extract_mode in {"scene", "hybrid"}:
            candidates.extend(self.detect_scene_change_times(video_path, duration=duration))
        if self.frame_extract_mode in {"mpdecimate", "hybrid", "scene_mpdecimate"}:
            candidates.extend(self.detect_mpdecimate_times(video_path, duration=duration))
        return candidates

    def detect_scene_change_times(self, video_path: Path, *, duration: float = 0.0) -> list[dict[str, Any]]:
        if not self.ffmpeg:
            return []
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-i",
            str(video_path),
            "-filter:v",
            f"select='gt(scene,{self.scene_threshold})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ]
        try:
            completed = self.run_command_capture(command, timeout=180)
        except Exception:
            return []
        text = "\n".join([completed.stderr or "", completed.stdout or ""])
        return self.parse_showinfo_times(text, duration=duration, source="scene")

    def detect_mpdecimate_times(self, video_path: Path, *, duration: float = 0.0) -> list[dict[str, Any]]:
        if not self.ffmpeg:
            return []
        fps = max(0.1, self.mpdecimate_sample_fps)
        filters = [
            f"fps={fps:g}",
            f"mpdecimate=max={self.mpdecimate_max}:hi={self.mpdecimate_hi}:lo={self.mpdecimate_lo}:frac={self.mpdecimate_frac}",
            "showinfo",
        ]
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-i",
            str(video_path),
            "-filter:v",
            ",".join(filters),
            "-an",
            "-f",
            "null",
            "-",
        ]
        try:
            completed = self.run_command_capture(command, timeout=180)
        except Exception:
            return []
        return self.parse_showinfo_times(
            "\n".join([completed.stderr or "", completed.stdout or ""]),
            duration=duration,
            source="mpdecimate",
        )

    def parse_showinfo_times(self, text: str, *, duration: float = 0.0, source: str = "showinfo") -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[float] = set()
        import re

        for match in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", text):
            seconds = round(float(match.group(1)), 2)
            if seconds <= 0 or (duration and seconds > duration):
                continue
            if seconds in seen:
                continue
            seen.add(seconds)
            candidates.append({"time": seconds, "source": source, "scene_score": None})
        return candidates

    def merge_frame_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        priority = {"chunk_start": 0, "scene": 1, "mpdecimate": 2, "fallback": 3, "interval": 4}
        sorted_items = sorted(candidates, key=lambda item: (float(item.get("time") or 0), priority.get(str(item.get("source")), 9)))
        merged: list[dict[str, Any]] = []
        for item in sorted_items:
            seconds = float(item.get("time") or 0)
            if seconds < 0:
                continue
            existing = next(
                (frame for frame in merged if abs(float(frame.get("time") or 0) - seconds) < self.frame_min_interval_seconds),
                None,
            )
            if existing:
                if priority.get(str(item.get("source")), 9) < priority.get(str(existing.get("source")), 9):
                    existing.update(item)
                continue
            merged.append({"time": round(seconds, 2), "source": item.get("source") or "frame", "scene_score": item.get("scene_score")})
        return merged

    def extract_frame(self, video_path: Path, seconds: float, image_path: Path) -> None:
        if not self.ffmpeg:
            raise RuntimeError("未找到 ffmpeg。请安装 FFmpeg，或在 .env 配置 FFMPEG_BINARY。")
        image_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            str(round(max(0.0, seconds), 2)),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(image_path),
        ]
        self.run_command(command, "FFmpeg 爆点截图失败", timeout=45)

    def assign_keyframes(self, segments: list[dict[str, Any]], keyframes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for segment in segments:
            start = float(segment.get("start") or 0)
            end = float(segment.get("end") or start)
            frames = [frame for frame in keyframes if start <= float(frame.get("time") or 0) <= max(end, start + 1)]
            result[segment["segment_id"]] = self.select_segment_frames(frames)
        return result

    def select_segment_frames(self, frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
        frames = self.dedupe_keyframes(frames)
        if len(frames) <= self.frame_max_per_chunk:
            return frames
        priority = {"chunk_start": 0, "scene": 1, "mpdecimate": 2, "fallback": 3, "interval": 4}
        selected = sorted(frames, key=lambda frame: (priority.get(str(frame.get("source")), 9), float(frame.get("time") or 0)))[: self.frame_max_per_chunk]
        return sorted(selected, key=lambda frame: float(frame.get("time") or 0))

    def dedupe_keyframes(self, frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.phash_dedup_enabled or len(frames) <= 1:
            return frames
        try:
            from PIL import Image
        except ImportError:
            return frames

        selected: list[dict[str, Any]] = []
        selected_hashes: list[tuple[int, dict[str, Any]]] = []
        duplicate_count = 0
        for frame in sorted(frames, key=lambda item: float(item.get("time") or 0)):
            image_path = Path(str(frame.get("image_path") or ""))
            image_hash = self.dhash_image(image_path, Image)
            if image_hash is None:
                selected.append(frame)
                continue
            duplicate_of = next(
                (
                    existing_frame
                    for existing_hash, existing_frame in selected_hashes
                    if self.hamming_distance(image_hash, existing_hash) <= self.phash_dedup_threshold
                ),
                None,
            )
            if duplicate_of:
                duplicate_count += 1
                frame["deduped"] = True
                frame["duplicate_of"] = duplicate_of.get("frame_id") or duplicate_of.get("image_path") or ""
                continue
            frame["perceptual_hash"] = f"{image_hash:016x}"
            selected.append(frame)
            selected_hashes.append((image_hash, frame))
        if duplicate_count:
            for frame in selected:
                frame["dedupe_removed_count"] = duplicate_count
        return selected

    def dhash_image(self, image_path: Path, Image: Any) -> int | None:
        if not image_path.exists():
            return None
        try:
            image = Image.open(image_path).convert("L").resize((9, 8))
        except Exception:
            return None
        pixels = list(image.getdata())
        value = 0
        for row in range(8):
            for col in range(8):
                left = pixels[row * 9 + col]
                right = pixels[row * 9 + col + 1]
                value = (value << 1) | (1 if left > right else 0)
        mean_bucket = max(0, min(15, int((sum(pixels) / max(1, len(pixels))) // 16)))
        return (value << 4) | mean_bucket

    def hamming_distance(self, left: int, right: int) -> int:
        return int(left ^ right).bit_count()

    def extract_frame_ocr_text(self, image_path: Path) -> str:
        if not self.ocr_enabled:
            return ""
        try:
            import pytesseract  # type: ignore
            from PIL import Image
        except ImportError:
            return ""
        try:
            return str(pytesseract.image_to_string(Image.open(image_path), lang=os.getenv("AI_VIDEO_OCR_LANG", "chi_sim+eng")) or "").strip()
        except Exception:
            return ""

    def create_segment_grids(
        self,
        segments: list[dict[str, Any]],
        output_dir: Path,
        *,
        progress: Callable[[int, str], None] | None = None,
    ) -> None:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            if progress:
                progress(58, "未安装 Pillow，跳过关键帧网格图生成")
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        total = len(segments)
        for index, segment in enumerate(segments, start=1):
            self.check_cancelled()
            frames = segment.get("keyframes") or []
            if not frames:
                continue
            grid_path = output_dir / f"{segment.get('segment_id') or index}.jpg"
            if self.resume_enabled and self.valid_file(grid_path):
                segment["keyframe_grid"] = {
                    "image_path": str(grid_path),
                    "frames": [{"time": frame.get("time_label"), "image_path": frame.get("image_path")} for frame in frames],
                }
                if progress:
                    progress(58, f"断点续跑：复用关键帧网格图 {index}/{total}：{grid_path.name}")
                continue
            try:
                self.create_grid_image(frames, grid_path, Image, ImageDraw, ImageFont)
            except Exception as exc:
                if progress:
                    progress(58, f"关键帧网格图生成失败：{segment.get('segment_id')} {type(exc).__name__}")
                continue
            segment["keyframe_grid"] = {
                "image_path": str(grid_path),
                "frames": [{"time": frame.get("time_label"), "image_path": frame.get("image_path")} for frame in frames],
            }
            if progress:
                progress(58, f"关键帧网格图 {index}/{total}：{grid_path.name}")

    def create_grid_image(self, frames: list[dict[str, Any]], grid_path: Path, Image: Any, ImageDraw: Any, ImageFont: Any) -> None:
        cell_width = int(os.getenv("AI_VIDEO_GRID_CELL_WIDTH", "320"))
        cell_height = int(os.getenv("AI_VIDEO_GRID_CELL_HEIGHT", "180"))
        columns = int(os.getenv("AI_VIDEO_GRID_COLUMNS", "3"))
        selected_frames = frames[: int(os.getenv("AI_VIDEO_GRID_MAX_FRAMES", "9"))]
        rows = max(1, math.ceil(len(selected_frames) / columns))
        label_height = 26
        canvas = Image.new("RGB", (columns * cell_width, rows * (cell_height + label_height)), "white")
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except Exception:
            font = ImageFont.load_default()

        for idx, frame in enumerate(selected_frames):
            image_path = Path(str(frame.get("image_path") or ""))
            if not image_path.exists():
                continue
            image = Image.open(image_path).convert("RGB")
            image.thumbnail((cell_width, cell_height))
            col = idx % columns
            row = idx // columns
            x = col * cell_width + (cell_width - image.width) // 2
            y = row * (cell_height + label_height)
            canvas.paste(image, (x, y))
            label = str(frame.get("time_label") or self.format_time(float(frame.get("time") or 0)))
            label_y = y + cell_height
            draw.rectangle([col * cell_width, label_y, (col + 1) * cell_width, label_y + label_height], fill=(15, 23, 42))
            draw.text((col * cell_width + 8, label_y + 4), label, fill=(255, 255, 255), font=font)

        canvas.save(grid_path, quality=88, optimize=True)

    def valid_file(self, path: Path) -> bool:
        return path.exists() and path.is_file() and path.stat().st_size > 0

    def run_command(self, command: list[str], error_message: str, *, timeout: int = 300) -> None:
        completed = self.run_command_capture(command, timeout=timeout)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"{error_message}: {detail[:800]}")

    def run_command_capture(self, command: list[str], *, timeout: int = 300, check: bool = False) -> subprocess.CompletedProcess:
        started = time.monotonic()
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            while True:
                self.check_cancelled()
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                    if check and completed.returncode != 0:
                        raise subprocess.CalledProcessError(completed.returncode, command, output=stdout, stderr=stderr)
                    return completed
                if timeout and time.monotonic() - started > timeout:
                    self.terminate_process(process)
                    stdout, stderr = process.communicate()
                    raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
                time.sleep(0.25)
        except BaseException:
            if process.poll() is None:
                self.terminate_process(process)
                process.communicate()
            raise

    def terminate_process(self, process: subprocess.Popen) -> None:
        try:
            if os.name == "nt":
                process.terminate()
            else:
                process.send_signal(signal.SIGTERM)
        except Exception:
            pass
        try:
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def author_name(self, video: dict[str, Any]) -> str:
        author = video.get("author") or {}
        return str(author.get("nickname") if isinstance(author, dict) else author or "未知")

    def resolve_ffmpeg_binary(self, configured: str) -> str:
        if configured and shutil.which(configured):
            return configured
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return configured if shutil.which(configured) else ""

    def format_time(self, seconds: float) -> str:
        seconds = max(0, int(seconds or 0))
        minutes, sec = divmod(seconds, 60)
        hours, minute = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minute:02d}:{sec:02d}"
        return f"{minute:02d}:{sec:02d}"
