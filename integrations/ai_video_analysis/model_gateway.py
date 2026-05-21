from __future__ import annotations

from dataclasses import dataclass
import os

from backend.app.ai_provider_state import openai_compatible_credentials


OPENAI_COMPATIBLE_FORMATS = {"openai_chat_completions", "chat_completions"}
GEMINI_GENERATE_CONTENT_FORMATS = {"gemini_generate_content", "generate_content"}


@dataclass(frozen=True)
class AiVideoProviderRoute:
    provider: str
    family: str
    api_format: str
    base_url: str
    api_key: str
    config_errors: tuple[str, ...] = ()

    @property
    def can_use_direct_video(self) -> bool:
        return self.family in {"mock", "gemini_relay"}

    @property
    def can_use_evidence_pipeline(self) -> bool:
        return self.family in {"mock", "gemini_relay", "openai_compatible_relay"}

    @property
    def error_message(self) -> str:
        if self.config_errors:
            return "；".join(self.config_errors)
        return ""


def resolve_ai_video_provider_route(
    provider: str | None = None,
    *,
    active_provider: str = "",
    pipeline_mode: str = "auto",
) -> AiVideoProviderRoute:
    selected_provider = (provider or active_provider or os.getenv("AI_MODEL_PROVIDER") or "mock").strip().lower()
    api_format = _resolve_video_api_format(selected_provider)
    family = _resolve_video_family(selected_provider, api_format)
    base_url, api_key = _resolve_video_credentials(selected_provider, family)
    errors = _validate_video_route(selected_provider, family, api_key, pipeline_mode=pipeline_mode)
    return AiVideoProviderRoute(
        provider=selected_provider,
        family=family,
        api_format=api_format,
        base_url=base_url,
        api_key=api_key,
        config_errors=tuple(errors),
    )


def uses_gemini_relay_provider(provider: str) -> bool:
    return resolve_ai_video_provider_route(provider).family == "gemini_relay"


def uses_openai_compatible_relay(provider: str | None = None, *, active_provider: str = "") -> bool:
    return resolve_ai_video_provider_route(provider, active_provider=active_provider).family == "openai_compatible_relay"


def relay_base_url(active_provider: str) -> str:
    return resolve_ai_video_provider_route(active_provider, active_provider=active_provider).base_url


def relay_token(active_provider: str) -> str:
    return resolve_ai_video_provider_route(active_provider, active_provider=active_provider).api_key


def _resolve_video_api_format(provider: str) -> str:
    if provider == "simple_relay":
        return (os.getenv("SIMPLE_RELAY_API_FORMAT") or os.getenv("AI_VIDEO_RELAY_API_FORMAT") or "gemini_generate_content").lower()
    if provider == "yunwu":
        return (os.getenv("YUNWU_API_FORMAT") or os.getenv("AI_VIDEO_RELAY_API_FORMAT") or "gemini_generate_content").lower()
    if provider == "gemini":
        return (os.getenv("GEMINI_RELAY_API_FORMAT") or os.getenv("AI_VIDEO_RELAY_API_FORMAT") or "gemini_generate_content").lower()
    if provider in {"openai", "deepseek", "volcano"}:
        return (os.getenv("AI_VIDEO_RELAY_API_FORMAT") or os.getenv("OPENAI_API_FORMAT") or "chat_completions").lower()
    return (
        os.getenv("AI_VIDEO_RELAY_API_FORMAT")
        or os.getenv("YUNWU_API_FORMAT")
        or os.getenv("SIMPLE_RELAY_API_FORMAT")
        or os.getenv("OPENAI_API_FORMAT")
        or ""
    ).lower()


def _resolve_video_family(provider: str, api_format: str) -> str:
    if provider == "mock":
        return "mock"
    if provider == "local":
        return "unsupported"
    if provider == "gemini":
        return "gemini_relay"
    if provider in {"simple_relay", "yunwu"}:
        if api_format in OPENAI_COMPATIBLE_FORMATS:
            return "openai_compatible_relay"
        return "gemini_relay"
    if provider in {"openai", "deepseek", "volcano"}:
        return "openai_compatible_relay"
    if api_format in OPENAI_COMPATIBLE_FORMATS:
        return "openai_compatible_relay"
    if api_format in GEMINI_GENERATE_CONTENT_FORMATS:
        return "gemini_relay"
    return "unsupported"


def _resolve_video_credentials(provider: str, family: str) -> tuple[str, str]:
    if family == "mock":
        return "", ""
    if family == "gemini_relay":
        if provider == "simple_relay":
            base_url = os.getenv("AI_VIDEO_RELAY_BASE_URL") or os.getenv("SIMPLE_RELAY_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://jeniya.top"
            api_key = (
                os.getenv("AI_VIDEO_RELAY_API_KEY")
                or os.getenv("SIMPLE_RELAY_API_KEY")
                or os.getenv("YUNWU_API_KEY")
                or os.getenv("AI_RELAY_API_KEY")
                or ""
            )
            return base_url.rstrip("/"), api_key
        if provider == "yunwu":
            base_url = os.getenv("AI_VIDEO_RELAY_BASE_URL") or os.getenv("YUNWU_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://yunwu.ai"
            api_key = (
                os.getenv("AI_VIDEO_RELAY_API_KEY")
                or os.getenv("YUNWU_API_KEY")
                or os.getenv("AI_RELAY_API_KEY")
                or ""
            )
            return base_url.rstrip("/"), api_key
        base_url = os.getenv("AI_VIDEO_RELAY_BASE_URL") or os.getenv("GEMINI_RELAY_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://jeniya.top"
        api_key = (
            os.getenv("AI_VIDEO_RELAY_API_KEY")
            or os.getenv("GEMINI_RELAY_API_KEY")
            or os.getenv("YUNWU_API_KEY")
            or os.getenv("AI_RELAY_API_KEY")
            or ""
        )
        return base_url.rstrip("/"), api_key
    if family == "openai_compatible_relay":
        creds = openai_compatible_credentials(provider)
        base_url = os.getenv("AI_VIDEO_RELAY_BASE_URL") or creds.get("base_url") or os.getenv("AI_RELAY_BASE_URL") or "https://yunwu.ai/v1"
        api_key = os.getenv("AI_VIDEO_RELAY_API_KEY") or creds.get("api_key") or ""
        return base_url.rstrip("/"), api_key
    return "", ""


def _validate_video_route(provider: str, family: str, api_key: str, *, pipeline_mode: str) -> list[str]:
    errors: list[str] = []
    if family == "unsupported":
        if provider == "local":
            errors.append("当前 AI 视频拆解不支持本地模型。")
        else:
            errors.append(f"当前 AI 视频拆解不支持 provider: {provider}")
    elif family in {"gemini_relay", "openai_compatible_relay"} and not api_key:
        errors.append("Missing AI_VIDEO_RELAY_API_KEY")
    if pipeline_mode == "direct" and family == "openai_compatible_relay":
        errors.append("AI_VIDEO_PIPELINE_MODE=direct requires Gemini relay")
    return errors


def normalized_usage(usage: dict, *, action: str, latency_ms: int, output_token_keys: tuple[str, ...], input_token_keys: tuple[str, ...]) -> dict:
    return {
        "input_tokens": int(_first_usage_value(usage, input_token_keys)),
        "output_tokens": int(_first_usage_value(usage, output_token_keys)),
        "latency_ms": latency_ms,
        "action": action,
    }


def _first_usage_value(usage: dict, keys: tuple[str, ...]) -> int:
    for key in keys:
        value = usage.get(key)
        if value:
            return int(value)
    return 0
