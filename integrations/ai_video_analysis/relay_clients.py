from __future__ import annotations

import base64
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

from backend.app.error_log_store import write_error_log


@dataclass
class RelayChatResponse:
    text: str
    usage: dict[str, Any]
    raw: dict[str, Any]


class OpenAICompatibleRelayClient:
    """Small OpenAI-compatible chat/completions client for vision relay vendors."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        session: Any | None = None,
    ):
        self.base_url = self.normalize_base_url(
            base_url
            or os.getenv("AI_VIDEO_RELAY_BASE_URL")
            or os.getenv("YUNWU_BASE_URL")
            or os.getenv("AI_RELAY_BASE_URL")
            or "https://yunwu.ai/v1"
        )
        self.api_key = api_key or os.getenv("AI_VIDEO_RELAY_API_KEY") or os.getenv("YUNWU_API_KEY") or os.getenv("AI_RELAY_API_KEY") or ""
        self.model = model or os.getenv("AI_VIDEO_VISION_MODEL") or os.getenv("GEMINI_MODEL") or os.getenv("YUNWU_MODEL") or os.getenv("AI_MODEL") or "gemini-2.5-flash"
        self.timeout_seconds = float(timeout_seconds or os.getenv("AI_VIDEO_MODEL_TIMEOUT_SECONDS", "180") or 180)
        self.max_retries = int(max_retries if max_retries is not None else os.getenv("AI_VIDEO_MODEL_MAX_RETRIES", "2") or 2)
        self.session = session or requests

    @classmethod
    def normalize_base_url(cls, base_url: str) -> str:
        base = (base_url or "https://yunwu.ai/v1").strip().rstrip("/")
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
        parsed = urlsplit(base)
        path_parts = [part for part in parsed.path.split("/") if part]
        if not path_parts:
            base = urlunsplit((parsed.scheme, parsed.netloc, "/v1", "", ""))
        return base.rstrip("/")

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def generate_text(
        self,
        *,
        prompt: str,
        image_paths: list[str] | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> RelayChatResponse:
        if not self.api_key:
            raise RuntimeError("Set AI_VIDEO_RELAY_API_KEY or YUNWU_API_KEY before using the OpenAI-compatible relay.")
        payload = self.build_payload(
            prompt=prompt,
            image_paths=image_paths or [],
            model=model or self.model,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        delays = [10, 20, 40]
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    self.chat_completions_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    last_error = RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
                    time.sleep(delays[min(attempt, len(delays) - 1)])
                    continue
                response.raise_for_status()
                data = response.json()
                return RelayChatResponse(text=self.extract_text(data), usage=data.get("usage") or {}, raw=data)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(delays[min(attempt, len(delays) - 1)])
        write_error_log(
            namespace="ai-provider",
            path="/v1/chat/completions",
            method="POST",
            request={"json_body": payload, "headers": {"Authorization": "Bearer ***", "Content-Type": "application/json"}},
            exc=last_error or RuntimeError("OpenAI-compatible relay request failed"),
            api_base=self.base_url,
            extra={"phase": "relay_chat_completions", "model": payload.get("model") or model},
        )
        raise RuntimeError(f"OpenAI-compatible relay request failed: {last_error}") from last_error

    def build_payload(
        self,
        *,
        prompt: str,
        image_paths: list[str],
        model: str,
        system_prompt: str | None,
        temperature: float,
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image_path in image_paths:
            data_url = self.image_data_url(Path(image_path))
            if data_url:
                content.append({"type": "image_url", "image_url": {"url": data_url}})

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt or "You are a short-video analysis assistant. Return valid JSON only.",
                },
                {"role": "user", "content": content},
            ],
            "temperature": temperature,
        }
        if os.getenv("AI_VIDEO_RELAY_JSON_MODE", "true").lower() not in {"0", "false", "no"}:
            payload["response_format"] = {"type": "json_object"}
        max_tokens = os.getenv("AI_VIDEO_RELAY_MAX_TOKENS")
        if max_tokens:
            payload["max_tokens"] = int(max_tokens)
        return payload

    def image_data_url(self, image_path: Path) -> str:
        if not image_path.exists() or not image_path.is_file():
            return ""
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def extract_text(self, data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str) and content:
                return content
            if isinstance(content, list):
                texts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
                text = "\n".join(item for item in texts if item)
                if text:
                    return text
        if isinstance(data.get("text"), str) and data["text"]:
            return str(data["text"])
        raise RuntimeError(f"OpenAI-compatible relay returned no text: {data}")


class GeminiGenerateContentRelayClient:
    """Gemini native generateContent client for relay vendors such as Yunwu."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        session: Any | None = None,
    ):
        self.base_url = self.normalize_base_url(
            base_url
            or os.getenv("AI_VIDEO_RELAY_BASE_URL")
            or os.getenv("YUNWU_BASE_URL")
            or os.getenv("GEMINI_RELAY_BASE_URL")
            or os.getenv("AI_RELAY_BASE_URL")
            or "https://yunwu.ai"
        )
        self.api_key = (
            api_key
            or os.getenv("AI_VIDEO_RELAY_API_KEY")
            or os.getenv("YUNWU_API_KEY")
            or os.getenv("GEMINI_RELAY_API_KEY")
            or os.getenv("AI_RELAY_API_KEY")
            or ""
        )
        self.model = model or os.getenv("AI_VIDEO_VISION_MODEL") or os.getenv("GEMINI_MODEL") or os.getenv("YUNWU_MODEL") or os.getenv("AI_MODEL") or "gemini-2.5-flash"
        self.timeout_seconds = float(timeout_seconds or os.getenv("AI_VIDEO_MODEL_TIMEOUT_SECONDS", "180") or 180)
        self.max_retries = int(max_retries if max_retries is not None else os.getenv("AI_VIDEO_MODEL_MAX_RETRIES", "2") or 2)
        self.session = session or requests

    @classmethod
    def normalize_base_url(cls, base_url: str) -> str:
        base = (base_url or "https://yunwu.ai").strip().rstrip("/")
        if base.endswith(":generateContent") or base.endswith(":streamGenerateContent"):
            base = base.rsplit("/v1beta/models/", 1)[0]
        return base.rstrip("/")

    def generate_content_url(self, model: str | None = None) -> str:
        selected_model = model or self.model
        if self.base_url.endswith("/v1beta"):
            return f"{self.base_url}/models/{selected_model}:generateContent"
        return f"{self.base_url}/v1beta/models/{selected_model}:generateContent"

    def generate_text(
        self,
        *,
        prompt: str,
        image_paths: list[str] | None = None,
        video_path: str | Path | None = None,
        model: str | None = None,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> RelayChatResponse:
        if not self.api_key:
            raise RuntimeError("Set AI_VIDEO_RELAY_API_KEY or YUNWU_API_KEY before using the Gemini generateContent relay.")
        selected_model = model or self.model
        payload = self.build_payload(
            prompt=prompt,
            image_paths=image_paths or [],
            video_path=Path(video_path) if video_path else None,
            system_instruction=system_instruction,
            temperature=temperature,
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        delays = [10, 20, 40]
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    self.generate_content_url(selected_model),
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    last_error = RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
                    time.sleep(delays[min(attempt, len(delays) - 1)])
                    continue
                response.raise_for_status()
                data = response.json()
                return RelayChatResponse(
                    text=self.extract_text(data),
                    usage=data.get("usageMetadata") or data.get("usage") or {},
                    raw=data,
                )
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(delays[min(attempt, len(delays) - 1)])
        write_error_log(
            namespace="ai-provider",
            path="/v1beta/models/:generateContent",
            method="POST",
            request={"json_body": payload, "headers": {"Authorization": "Bearer ***", "Content-Type": "application/json"}},
            exc=last_error or RuntimeError("Gemini generateContent relay request failed"),
            api_base=self.base_url,
            extra={"phase": "relay_generate_content", "model": selected_model},
        )
        raise RuntimeError(f"Gemini generateContent relay request failed: {last_error}") from last_error

    def build_payload(
        self,
        *,
        prompt: str,
        image_paths: list[str],
        video_path: Path | None,
        system_instruction: str | None,
        temperature: float,
    ) -> dict[str, Any]:
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for image_path in image_paths:
            media = self.inline_data(Path(image_path))
            if media:
                parts.append(media)
        if video_path:
            media = self.inline_data(video_path, default_mime_type="video/mp4")
            if media:
                parts.append(media)

        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        thinking_budget = os.getenv("AI_VIDEO_GEMINI_THINKING_BUDGET")
        if thinking_budget:
            payload["generationConfig"]["thinkingConfig"] = {
                "includeThoughts": os.getenv("AI_VIDEO_GEMINI_INCLUDE_THOUGHTS", "false").lower() in {"1", "true", "yes"},
                "thinkingBudget": int(thinking_budget),
            }
        return payload

    def inline_data(self, media_path: Path, *, default_mime_type: str = "image/jpeg") -> dict[str, Any]:
        if not media_path.exists() or not media_path.is_file():
            return {}
        mime_type = mimetypes.guess_type(media_path.name)[0] or default_mime_type
        encoded = base64.b64encode(media_path.read_bytes()).decode("ascii")
        return {"inline_data": {"mime_type": mime_type, "data": encoded}}

    def extract_text(self, data: dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        if candidates:
            parts = ((candidates[0].get("content") or {}).get("parts")) or []
            text = "\n".join(str(part.get("text") or "") for part in parts if isinstance(part, dict) and part.get("text"))
            if text:
                return text
        if isinstance(data.get("text"), str) and data["text"]:
            return str(data["text"])
        raise RuntimeError(f"Gemini generateContent relay returned no text: {data}")


class DeepSeekChatClient(OpenAICompatibleRelayClient):
    """OpenAI-compatible client for DeepSeek global text summarization."""

    @property
    def chat_completions_url(self) -> str:
        if self.base_url.rstrip("/") == "https://api.deepseek.com":
            return f"{self.base_url}/chat/completions"
        return super().chat_completions_url

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        session: Any | None = None,
    ):
        raw_base_url = base_url or os.getenv("AI_VIDEO_SUMMARY_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        super().__init__(
            base_url=raw_base_url,
            api_key=api_key or os.getenv("AI_VIDEO_SUMMARY_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or "",
            model=model or os.getenv("AI_VIDEO_SUMMARY_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash",
            timeout_seconds=timeout_seconds or float(os.getenv("AI_VIDEO_SUMMARY_TIMEOUT_SECONDS", "240") or 240),
            max_retries=max_retries,
            session=session,
        )
        parsed = urlsplit(raw_base_url.rstrip("/"))
        if parsed.netloc == "api.deepseek.com" and parsed.path in {"", "/"}:
            self.base_url = urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")

    def generate_summary(
        self,
        *,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> RelayChatResponse:
        return self.generate_text(
            prompt=prompt,
            image_paths=[],
            model=model or self.model,
            system_prompt=system_prompt or "You are a senior short-video growth strategist. Return valid JSON only.",
            temperature=float(os.getenv("AI_VIDEO_SUMMARY_TEMPERATURE", "0.2") or 0.2),
        )
