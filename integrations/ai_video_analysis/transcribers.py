from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol


class Transcriber(Protocol):
    provider: str

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str,
        language: str | None,
        duration: float = 0.0,
        progress: Callable[[int, str], None] | None = None,
        format_time: Callable[[float], str] | None = None,
    ) -> dict[str, Any]:
        ...


class FasterWhisperTranscriber:
    provider = "faster-whisper"

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str,
        language: str | None,
        duration: float = 0.0,
        progress: Callable[[int, str], None] | None = None,
        format_time: Callable[[float], str] | None = None,
    ) -> dict[str, Any]:
        from faster_whisper import WhisperModel

        device = os.getenv("AI_VIDEO_TRANSCRIBE_DEVICE", "cpu")
        compute_type = os.getenv("AI_VIDEO_TRANSCRIBE_COMPUTE_TYPE", "int8")
        if progress:
            progress(35, f"加载 faster-whisper 模型：{model} / {device} / {compute_type}")
        whisper = WhisperModel(model, device=device, compute_type=compute_type)
        if progress:
            progress(38, "Whisper 模型加载完成，开始识别语音")
        segments, info = whisper.transcribe(str(audio_path), language=language, vad_filter=True)
        normalized = []
        last_percent = -1
        time_formatter = format_time or self.default_format_time
        for segment in segments:
            if segment.text and segment.text.strip():
                normalized.append({"start": float(segment.start), "end": float(segment.end), "text": segment.text.strip()})
            if progress:
                if duration:
                    percent = min(47, 38 + int(float(segment.end) * 9 / duration))
                    if percent != last_percent:
                        last_percent = percent
                        progress(percent, f"Whisper 转写中：{time_formatter(float(segment.end))} / {time_formatter(duration)}")
                elif len(normalized) % 10 == 0:
                    progress(42, f"Whisper 转写中：已生成 {len(normalized)} 个片段")
        return {
            "provider": self.provider,
            "model": model,
            "language": getattr(info, "language", language or ""),
            "full_text": "\n".join(segment["text"] for segment in normalized),
            "segments": normalized,
        }

    def default_format_time(self, seconds: float) -> str:
        seconds = max(0, int(seconds or 0))
        minutes, sec = divmod(seconds, 60)
        hours, minute = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minute:02d}:{sec:02d}"
        return f"{minute:02d}:{sec:02d}"


class OpenAIWhisperTranscriber:
    provider = "openai-whisper"

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str,
        language: str | None,
        duration: float = 0.0,
        progress: Callable[[int, str], None] | None = None,
        format_time: Callable[[float], str] | None = None,
    ) -> dict[str, Any]:
        import whisper

        if progress:
            progress(35, f"加载 openai-whisper 模型：{model}")
        whisper_model = whisper.load_model(model)
        if progress:
            progress(38, "Whisper 模型加载完成，开始识别语音")
        result = whisper_model.transcribe(str(audio_path), language=language, verbose=False)
        if progress:
            progress(47, "Whisper 转写文本整理中")
        normalized = [
            {
                "start": float(segment.get("start") or 0),
                "end": float(segment.get("end") or 0),
                "text": str(segment.get("text") or "").strip(),
            }
            for segment in result.get("segments", [])
            if str(segment.get("text") or "").strip()
        ]
        return {
            "provider": self.provider,
            "model": model,
            "language": result.get("language") or language or "",
            "full_text": str(result.get("text") or "\n".join(segment["text"] for segment in normalized)).strip(),
            "segments": normalized,
        }


def resolve_transcriber(provider: str) -> Transcriber:
    selected = (provider or "auto").lower()
    if selected in {"doubao", "doubao_file_asr", "volcengine", "volcengine_asr"}:
        from integrations.ai_video_analysis.doubao_asr import DoubaoFileAsrTranscriber

        return DoubaoFileAsrTranscriber()
    if selected in {"auto", "faster_whisper"}:
        try:
            import faster_whisper  # noqa: F401

            return FasterWhisperTranscriber()
        except ImportError:
            if selected == "faster_whisper":
                raise RuntimeError("缺少 faster-whisper。请安装后重试：pip install faster-whisper") from None
    if selected in {"auto", "whisper", "openai_whisper"}:
        try:
            import whisper  # noqa: F401

            return OpenAIWhisperTranscriber()
        except ImportError:
            if selected in {"whisper", "openai_whisper"}:
                raise RuntimeError("缺少 openai-whisper。请安装后重试：pip install openai-whisper") from None
    raise RuntimeError("没有可用的本地转写器。请安装 faster-whisper 或 openai-whisper，或设置 AI_VIDEO_PIPELINE_MODE=direct 使用旧的视频上传分析。")
