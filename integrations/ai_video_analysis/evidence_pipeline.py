from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import importlib.util
import sys
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from integrations.ai_video_analysis.transcribers import resolve_transcriber


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
        self.silent_segment_seconds = int(os.getenv("AI_VIDEO_SILENT_SEGMENT_SECONDS", "6") or 6)
        self.keyframe_interval_seconds = keyframe_interval_seconds or int(os.getenv("AI_VIDEO_KEYFRAME_INTERVAL_SECONDS", "30"))
        self.ffmpeg = self.resolve_ffmpeg_binary(os.getenv("FFMPEG_BINARY") or "ffmpeg")
        self.ffprobe = os.getenv("FFPROBE_BINARY") or "ffprobe"
        self.resume_enabled = os.getenv("AI_VIDEO_RESUME_ENABLED", "true").lower() not in {"0", "false", "no"}

    def build(
        self,
        video: dict[str, Any],
        *,
        job_id: str,
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        evidence_dir = self.output_dir / "evidence" / job_id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_dir / "analysis_evidence.json"

        if progress:
            progress(12, f"创建证据包目录：{evidence_dir}")
        video_path = self.resolve_video_file(video, evidence_dir=evidence_dir, progress=progress)
        if progress:
            progress(20, f"视频文件准备完成：{video_path.name}")
        duration = self.probe_duration(video_path)
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
        if progress:
            progress(32, f"音频提取完成：{audio_path.name}")

        if progress:
            progress(34, "开始转写音频：加载 Whisper 模型")
        transcript_path = evidence_dir / "transcript.json"
        if self.resume_enabled and transcript_path.exists():
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            if progress:
                progress(48, f"断点续跑：复用已转写文本 {len(transcript.get('segments') or [])} 个片段")
        else:
            transcript = self.transcribe(audio_path, duration=duration, progress=progress)
            transcript_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        if progress:
            progress(48, f"转写完成：{len(transcript.get('segments') or [])} 个时间戳片段")

        if progress:
            progress(50, f"按 {self.segment_seconds} 秒切分转写文本")
        analysis_segments = self.chunk_transcript(transcript.get("segments") or [], duration=duration)
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
            keyframes_path.write_text(json.dumps(keyframes, ensure_ascii=False, indent=2), encoding="utf-8")
        if progress:
            progress(58, f"关键帧抽取完成：{len(keyframes)} 张")
        keyframes_by_segment = self.assign_keyframes(analysis_segments, keyframes)
        for segment in analysis_segments:
            segment["keyframes"] = keyframes_by_segment.get(segment["segment_id"], [])

        if progress:
            progress(58, "生成带时间戳的关键帧网格图")
        self.create_segment_grids(analysis_segments, evidence_dir / "keyframe_grids", progress=progress)

        metadata = {
            "video_title": video.get("desc") or video.get("title") or "",
            "author": self.author_name(video),
            "aweme_id": video.get("aweme_id") or video.get("id") or "",
            "duration": duration,
            "video_path": str(video_path),
            "audio_path": str(audio_path),
        }
        evidence = {
            "metadata": metadata,
            "transcript": transcript,
            "analysis_segments": analysis_segments,
            "keyframes": keyframes,
            "checkpoints": {
                "audio_path": str(audio_path),
                "transcript_path": str(transcript_path),
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

    def dependency_status(self) -> dict[str, Any]:
        faster_whisper_ready = bool(importlib.util.find_spec("faster_whisper"))
        openai_whisper_ready = bool(importlib.util.find_spec("whisper"))
        imageio_ffmpeg_ready = bool(importlib.util.find_spec("imageio_ffmpeg"))
        return {
            "python_executable": sys.executable,
            "mode": os.getenv("AI_VIDEO_PIPELINE_MODE", "auto"),
            "transcriber": os.getenv("AI_VIDEO_TRANSCRIBER", "auto"),
            "transcribe_model": os.getenv("AI_VIDEO_TRANSCRIBE_MODEL", "small"),
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
            "silent_segment_seconds": self.silent_segment_seconds,
            "keyframe_interval_seconds": self.keyframe_interval_seconds,
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

        url = video.get("source_video_url") or video.get("video_url")
        if not url:
            raise RuntimeError("没有找到本地视频路径或 source_video_url，无法生成转写证据包。")

        target = evidence_dir / f"{video.get('aweme_id') or video.get('id') or int(time.time())}.mp4"
        if target.exists() and target.stat().st_size > 0:
            if progress:
                progress(16, f"复用已下载视频：{target.name}")
            return target

        import requests

        if progress:
            progress(14, "开始下载视频到证据包目录")
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
        total = int(response.headers.get("content-length") or 0)
        downloaded = 0
        last_percent = -1
        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if chunk:
                    file.write(chunk)
                    downloaded += len(chunk)
                    if progress and total:
                        percent = min(19, 14 + int(downloaded * 5 / total))
                        if percent != last_percent:
                            last_percent = percent
                            progress(percent, f"下载视频中：{downloaded / 1024 / 1024:.1f}MB / {total / 1024 / 1024:.1f}MB")
        return target

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
            completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
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
        command = [
            self.ffmpeg,
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
            str(audio_path),
        ]
        if progress:
            progress(24, "FFmpeg 正在提取音频")
        self.run_command(command, "FFmpeg 音频提取失败")

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

    def chunk_transcript(self, transcript_segments: list[dict[str, Any]], *, duration: float = 0.0) -> list[dict[str, Any]]:
        if not transcript_segments:
            return self.chunk_silent_video(duration=duration)

        chunks: list[dict[str, Any]] = []
        current: list[dict[str, Any]] = []
        chunk_start = float(transcript_segments[0].get("start") or 0)
        chunk_end = chunk_start

        for item in transcript_segments:
            start = float(item.get("start") or chunk_end)
            end = float(item.get("end") or start)
            if current and end - chunk_start > self.segment_seconds:
                chunks.append(self.make_chunk(len(chunks) + 1, chunk_start, chunk_end, current))
                current = []
                chunk_start = start
            current.append(item)
            chunk_end = end

        if current:
            chunks.append(self.make_chunk(len(chunks) + 1, chunk_start, chunk_end or duration, current))
        return chunks

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

    def make_chunk(self, index: int, start: float, end: float, items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "segment_id": f"seg_{index:03d}",
            "start": round(start, 2),
            "end": round(end, 2),
            "time_range": f"{self.format_time(start)}-{self.format_time(end)}",
            "transcript": "\n".join(str(item.get("text") or "").strip() for item in items if str(item.get("text") or "").strip()),
            "transcript_segments": items,
        }

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
        sorted_times = sorted(times)
        total = len(sorted_times)
        for index, seconds in enumerate(sorted_times, start=1):
            image_path = output_dir / f"frame_{index:04d}_{int(seconds):06d}.jpg"
            if progress:
                percent = 54 + int(index * 4 / max(1, total))
                progress(percent, f"抽取关键帧 {index}/{total}：{self.format_time(seconds)}")
            command = [
                self.ffmpeg,
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
            except RuntimeError:
                continue
            if image_path.exists() and image_path.stat().st_size > 0:
                keyframes.append({"time": round(seconds, 2), "time_label": self.format_time(seconds), "image_path": str(image_path)})
        return keyframes

    def extract_frame(self, video_path: Path, seconds: float, image_path: Path) -> None:
        if not self.ffmpeg:
            raise RuntimeError("未找到 ffmpeg。请安装 FFmpeg，或在 .env 配置 FFMPEG_BINARY。")
        image_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.ffmpeg,
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
            result[segment["segment_id"]] = [
                frame for frame in keyframes if start <= float(frame.get("time") or 0) <= max(end, start + 1)
            ]
        return result

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
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"{error_message}: {detail[:800]}")

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
