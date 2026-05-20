from __future__ import annotations

import os
import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from integrations.ai_video_analysis.audio_publication import AudioPublisher, configured_publisher_mode, tos_config_status
from integrations.ai_video_analysis.http_policy import default_max_retries, post_with_retries


SUCCESS_CODE = "20000000"
PROCESSING_CODES = {"20000001", "20000002"}
SILENCE_CODE = "20000003"
TOS_PUBLISHER_ALIASES = {"tos", "volcengine_tos", "object_storage", "oss"}


@dataclass
class DoubaoAsrConfig:
    app_id: str
    access_token: str
    secret_key: str
    resource_id: str
    submit_url: str
    query_url: str
    poll_interval_seconds: float
    timeout_seconds: float
    max_wait_seconds: float
    upload_mode: str
    direct_url: str
    direct_max_bytes: int

    @classmethod
    def from_env(cls) -> "DoubaoAsrConfig":
        return cls(
            app_id=os.getenv("VOLCENGINE_ASR_APP_ID") or os.getenv("VOLCENGINE_ASR_APP_KEY") or os.getenv("DOUBAO_ASR_APP_ID") or "",
            access_token=(
                os.getenv("VOLCENGINE_ASR_ACCESS_TOKEN")
                or os.getenv("VOLCENGINE_ASR_ACCESS_KEY")
                or os.getenv("DOUBAO_ASR_ACCESS_TOKEN")
                or ""
            ),
            secret_key=os.getenv("VOLCENGINE_ASR_SECRET_KEY") or os.getenv("DOUBAO_ASR_SECRET_KEY") or "",
            resource_id=os.getenv("VOLCENGINE_ASR_RESOURCE_ID") or "volc.seedasr.auc",
            submit_url=os.getenv("VOLCENGINE_ASR_SUBMIT_URL") or "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
            query_url=os.getenv("VOLCENGINE_ASR_QUERY_URL") or "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query",
            poll_interval_seconds=float(os.getenv("VOLCENGINE_ASR_POLL_INTERVAL_SECONDS", "3") or 3),
            timeout_seconds=float(os.getenv("VOLCENGINE_ASR_HTTP_TIMEOUT_SECONDS", "60") or 60),
            max_wait_seconds=float(os.getenv("VOLCENGINE_ASR_MAX_WAIT_SECONDS", "900") or 900),
            upload_mode=(os.getenv("AI_VIDEO_ASR_UPLOAD_MODE") or os.getenv("VOLCENGINE_ASR_UPLOAD_MODE") or "url").lower(),
            direct_url=os.getenv("VOLCENGINE_ASR_DIRECT_URL") or "",
            direct_max_bytes=int(os.getenv("VOLCENGINE_ASR_DIRECT_MAX_BYTES", str(20 * 1024 * 1024)) or (20 * 1024 * 1024)),
        )

    def validate(self) -> None:
        missing = []
        if not self.app_id:
            missing.append("VOLCENGINE_ASR_APP_ID")
        if not self.access_token:
            missing.append("VOLCENGINE_ASR_ACCESS_TOKEN")
        if missing:
            raise RuntimeError(f"Missing Doubao ASR credentials: {', '.join(missing)}")


def doubao_asr_status() -> dict[str, Any]:
    config = DoubaoAsrConfig.from_env()
    publisher = configured_publisher_mode()
    tos_status = tos_config_status()
    errors = validate_doubao_asr_environment(config=config, publisher=publisher, tos_status=tos_status)
    return {
        "provider_ready": not errors,
        "errors": errors,
        "app_id_configured": bool(config.app_id),
        "access_token_configured": bool(config.access_token),
        "secret_key_configured": bool(config.secret_key),
        "resource_id": config.resource_id,
        "submit_url": config.submit_url,
        "query_url": config.query_url,
        "upload_mode": config.upload_mode,
        "direct_url_configured": bool(config.direct_url),
        "publisher": publisher,
        "public_base_url_configured": bool(os.getenv("AI_VIDEO_ASR_PUBLIC_BASE_URL") or os.getenv("AI_VIDEO_PUBLIC_BASE_URL")),
        "explicit_audio_url_configured": bool(os.getenv("AI_VIDEO_ASR_AUDIO_URL") or os.getenv("VOLCENGINE_ASR_AUDIO_URL")),
        "tos": tos_status,
    }


def validate_doubao_asr_environment(
    *,
    config: DoubaoAsrConfig | None = None,
    publisher: str | None = None,
    tos_status: dict[str, bool] | None = None,
) -> list[str]:
    config = config or DoubaoAsrConfig.from_env()
    publisher = (publisher or configured_publisher_mode()).lower()
    tos_status = tos_status or tos_config_status()
    errors: list[str] = []
    if not config.app_id:
        errors.append("Missing VOLCENGINE_ASR_APP_ID")
    if not config.access_token:
        errors.append("Missing VOLCENGINE_ASR_ACCESS_TOKEN")
    if config.upload_mode not in {"url", "base64"}:
        errors.append("AI_VIDEO_ASR_UPLOAD_MODE must be url or base64")
    if config.upload_mode == "base64" and not config.direct_url:
        errors.append("AI_VIDEO_ASR_UPLOAD_MODE=base64 requires VOLCENGINE_ASR_DIRECT_URL")
    if config.upload_mode == "url":
        if publisher in TOS_PUBLISHER_ALIASES:
            missing = [
                name
                for name, ready in [
                    ("VOLCENGINE_TOS_ACCESS_KEY", tos_status.get("access_key_configured", False)),
                    ("VOLCENGINE_TOS_SECRET_KEY", tos_status.get("secret_key_configured", False)),
                    ("VOLCENGINE_TOS_ENDPOINT", tos_status.get("endpoint_configured", False)),
                    ("VOLCENGINE_TOS_REGION", tos_status.get("region_configured", False)),
                    ("VOLCENGINE_TOS_BUCKET", tos_status.get("bucket_configured", False)),
                ]
                if not ready
            ]
            if missing:
                errors.append(f"AI_VIDEO_ASR_PUBLISHER=tos missing: {', '.join(missing)}")
        elif not (
            os.getenv("AI_VIDEO_ASR_AUDIO_URL")
            or os.getenv("VOLCENGINE_ASR_AUDIO_URL")
            or os.getenv("AI_VIDEO_ASR_PUBLIC_BASE_URL")
            or os.getenv("AI_VIDEO_PUBLIC_BASE_URL")
        ):
            errors.append("AI_VIDEO_ASR_UPLOAD_MODE=url requires AI_VIDEO_ASR_PUBLIC_BASE_URL, AI_VIDEO_PUBLIC_BASE_URL, or AI_VIDEO_ASR_AUDIO_URL")
    return errors


class DoubaoFileAsrClient:
    """Two-step Doubao/Volcengine recording-file ASR client."""

    def __init__(self, config: DoubaoAsrConfig | None = None, *, session: Any | None = None):
        self.config = config or DoubaoAsrConfig.from_env()
        self.session = session or requests

    def transcribe_url(
        self,
        *,
        audio_url: str,
        audio_format: str = "wav",
        language: str | None = None,
        request_id: str | None = None,
        progress: Any | None = None,
    ) -> dict[str, Any]:
        self.config.validate()
        task_id = request_id or str(uuid4())
        self.submit(audio_url=audio_url, audio_format=audio_format, language=language, request_id=task_id)
        deadline = time.monotonic() + self.config.max_wait_seconds
        while True:
            code, raw = self.query(task_id)
            if code == SUCCESS_CODE:
                return raw
            if code == SILENCE_CODE:
                return {"result": {"text": "", "utterances": []}, "audio_info": {}, "asr_status_code": code}
            if code not in PROCESSING_CODES:
                message = str(raw.get("message") or raw.get("error") or raw)[:500]
                raise RuntimeError(f"Doubao ASR query failed: {code} {message}")
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Doubao ASR timed out after {int(self.config.max_wait_seconds)}s")
            if progress:
                progress(42, "Doubao ASR task is still processing")
            time.sleep(self.config.poll_interval_seconds)

    def submit(self, *, audio_url: str, audio_format: str, language: str | None, request_id: str) -> None:
        payload = self.build_payload(audio={"url": audio_url}, audio_format=audio_format, language=language)
        response = post_with_retries(
            self.config.submit_url,
            session=self.session,
            headers=self.headers(request_id=request_id, include_sequence=True),
            json=payload,
            timeout=self.config.timeout_seconds,
            max_retries=default_max_retries("asr"),
        )
        code = response.headers.get("X-Api-Status-Code") or ""
        if code != SUCCESS_CODE:
            message = response.headers.get("X-Api-Message") or response.text[:500]
            raise RuntimeError(f"Doubao ASR submit failed: {code or response.status_code} {message}")

    def transcribe_bytes(
        self,
        *,
        audio_path: Path,
        audio_format: str = "wav",
        language: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        self.config.validate()
        if not self.config.direct_url:
            raise RuntimeError("Set VOLCENGINE_ASR_DIRECT_URL before using AI_VIDEO_ASR_UPLOAD_MODE=base64.")
        size = audio_path.stat().st_size
        if size > self.config.direct_max_bytes:
            raise RuntimeError(
                f"Audio file is {size} bytes, above VOLCENGINE_ASR_DIRECT_MAX_BYTES={self.config.direct_max_bytes}. "
                "Use AI_VIDEO_ASR_UPLOAD_MODE=url for long audio."
            )
        request_id = request_id or str(uuid4())
        encoded = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        payload = self.build_payload(audio={"data": encoded}, audio_format=audio_format, language=language)
        response = post_with_retries(
            self.config.direct_url,
            session=self.session,
            headers=self.headers(request_id=request_id, include_sequence=False),
            json=payload,
            timeout=self.config.timeout_seconds,
            max_retries=default_max_retries("asr"),
        )
        code = response.headers.get("X-Api-Status-Code") or ""
        try:
            data = response.json() if response.text else {}
        except ValueError:
            data = {"raw_text": response.text}
        if response.status_code >= 400 and not code:
            response.raise_for_status()
        if code and code != SUCCESS_CODE:
            message = response.headers.get("X-Api-Message") or str(data)[:500]
            raise RuntimeError(f"Doubao ASR direct upload failed: {code} {message}")
        return data

    def build_payload(self, *, audio: dict[str, Any], audio_format: str, language: str | None) -> dict[str, Any]:
        payload = {
            "user": {"uid": self.config.app_id},
            "audio": {
                **audio,
                "format": audio_format,
                "rate": 16000,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "show_utterances": True,
                "enable_timestamp": True,
            },
        }
        if language:
            payload["audio"]["language"] = language
        return payload

    def query(self, request_id: str) -> tuple[str, dict[str, Any]]:
        response = post_with_retries(
            self.config.query_url,
            session=self.session,
            headers=self.headers(request_id=request_id, include_sequence=False),
            json={},
            timeout=self.config.timeout_seconds,
            max_retries=default_max_retries("asr"),
        )
        code = response.headers.get("X-Api-Status-Code") or ""
        try:
            data = response.json() if response.text else {}
        except ValueError:
            data = {"raw_text": response.text}
        if response.status_code >= 400 and not code:
            response.raise_for_status()
        return code, data

    def headers(self, *, request_id: str, include_sequence: bool) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Api-App-Key": self.config.app_id,
            "X-Api-Access-Key": self.config.access_token,
            "X-Api-Resource-Id": self.config.resource_id,
            "X-Api-Request-Id": request_id,
        }
        if include_sequence:
            headers["X-Api-Sequence"] = "-1"
        return headers


class DoubaoFileAsrTranscriber:
    provider = "doubao_file_asr"

    def __init__(self, client: DoubaoFileAsrClient | None = None):
        self.client = client or DoubaoFileAsrClient()

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str,
        language: str | None,
        duration: float = 0.0,
        progress: Any | None = None,
        format_time: Any | None = None,
    ) -> dict[str, Any]:
        upload_mode = self.client.config.upload_mode
        if progress:
            progress(35, f"Submitting audio to Doubao ASR via {upload_mode} mode")
        audio_url = ""
        if upload_mode == "base64":
            raw = self.client.transcribe_bytes(audio_path=audio_path, audio_format=self.audio_format(audio_path), language=language)
        else:
            audio_url = self.resolve_audio_url(audio_path)
            if not audio_url:
                raise RuntimeError(
                    "Doubao recording-file ASR requires a public audio URL in url mode. "
                    "Set AI_VIDEO_ASR_AUDIO_URL for one-off tests, set AI_VIDEO_ASR_PUBLIC_BASE_URL for local publication, "
                    "or switch AI_VIDEO_ASR_UPLOAD_MODE=base64 with VOLCENGINE_ASR_DIRECT_URL for direct upload."
                )
            raw = self.client.transcribe_url(
                audio_url=audio_url,
                audio_format=self.audio_format(audio_path),
                language=language,
                progress=progress,
            )
        normalized = normalize_doubao_asr_response(
            raw,
            provider=self.provider,
            model=self.client.config.resource_id or model,
            language=language or "",
        )
        normalized["audio_url"] = audio_url
        normalized["upload_mode"] = upload_mode
        return normalized

    def resolve_audio_url(self, audio_path: Path) -> str:
        published = AudioPublisher().resolve_or_publish(audio_path)
        return published.url if published else ""

    def audio_format(self, audio_path: Path) -> str:
        suffix = audio_path.suffix.lower().lstrip(".")
        if suffix in {"wav", "mp3", "ogg"}:
            return suffix
        return "wav"


def normalize_doubao_asr_response(
    raw: dict[str, Any],
    *,
    provider: str = "doubao_file_asr",
    model: str = "volc.seedasr.auc",
    language: str = "",
) -> dict[str, Any]:
    result = raw.get("result") or {}
    if isinstance(result, list):
        result = result[0] if result and isinstance(result[0], dict) else {}
    utterances = result.get("utterances") or []
    segments: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    for index, utterance in enumerate(utterances):
        if not isinstance(utterance, dict):
            continue
        text = str(utterance.get("text") or "").strip()
        start = ms_to_seconds(utterance.get("start_time"))
        end = ms_to_seconds(utterance.get("end_time"))
        if text:
            segments.append(
                {
                    "start": start,
                    "end": end,
                    "text": text,
                    "utterance_id": index,
                    "definite": bool(utterance.get("definite", True)),
                    "additions": utterance.get("additions") or {},
                }
            )
        for word in utterance.get("words") or []:
            if not isinstance(word, dict):
                continue
            word_text = str(word.get("text") or "").strip()
            if not word_text:
                continue
            words.append(
                {
                    "start": ms_to_seconds(word.get("start_time")),
                    "end": ms_to_seconds(word.get("end_time")),
                    "text": word_text,
                    "utterance_id": index,
                    "blank_duration": ms_to_seconds(word.get("blank_duration")),
                }
            )
    full_text = str(result.get("text") or "").strip() or "\n".join(segment["text"] for segment in segments)
    audio_info = raw.get("audio_info") or {}
    return {
        "provider": provider,
        "model": model,
        "language": language,
        "full_text": full_text,
        "segments": segments,
        "words": words,
        "pause_points": pause_points_from_words(words),
        "audio_duration": ms_to_seconds(audio_info.get("duration")),
        "raw_response": raw,
    }


def pause_points_from_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    threshold = float(os.getenv("AI_VIDEO_ASR_PAUSE_THRESHOLD_SECONDS", "0.5") or 0.5)
    pauses: list[dict[str, Any]] = []
    previous_end: float | None = None
    for word in words:
        start = float(word.get("start") or 0)
        end = float(word.get("end") or start)
        blank_duration = float(word.get("blank_duration") or 0)
        if previous_end is not None:
            gap = max(0.0, start - previous_end)
            if gap >= threshold:
                pauses.append({"start": round(previous_end, 3), "end": round(start, 3), "duration": round(gap, 3), "reason": "word_gap"})
        if blank_duration >= threshold:
            pauses.append({"time": round(start, 3), "duration": round(blank_duration, 3), "reason": "blank_duration"})
        previous_end = max(previous_end or 0.0, end)
    return pauses


def ms_to_seconds(value: Any) -> float:
    try:
        return round(float(value or 0) / 1000.0, 3)
    except (TypeError, ValueError):
        return 0.0
