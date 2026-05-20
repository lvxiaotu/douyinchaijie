from __future__ import annotations

import os


OPENAI_COMPATIBLE_FORMATS = {"openai_chat_completions", "chat_completions"}
GEMINI_GENERATE_CONTENT_FORMATS = {"gemini_generate_content", "generate_content"}


def uses_gemini_relay_provider(provider: str) -> bool:
    if provider == "simple_relay":
        return os.getenv("SIMPLE_RELAY_API_FORMAT", "gemini_generate_content") == "gemini_generate_content"
    if provider == "yunwu":
        api_format = (os.getenv("AI_VIDEO_RELAY_API_FORMAT") or os.getenv("YUNWU_API_FORMAT", "gemini_generate_content")).lower()
        return api_format in GEMINI_GENERATE_CONTENT_FORMATS
    return False


def uses_openai_compatible_relay(provider: str | None = None, *, active_provider: str = "") -> bool:
    api_format = (
        os.getenv("AI_VIDEO_RELAY_API_FORMAT")
        or os.getenv("YUNWU_API_FORMAT")
        or os.getenv("SIMPLE_RELAY_API_FORMAT")
        or ""
    ).lower()
    selected_provider = provider or os.getenv("AI_VIDEO_VISION_PROVIDER") or active_provider
    return api_format in OPENAI_COMPATIBLE_FORMATS or selected_provider == "yunwu_openai"


def relay_base_url(active_provider: str) -> str:
    if active_provider == "yunwu":
        return (os.getenv("YUNWU_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://yunwu.ai").rstrip("/")
    if uses_gemini_relay_provider(active_provider):
        return (os.getenv("SIMPLE_RELAY_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://jeniya.top").rstrip("/")
    return (os.getenv("GEMINI_RELAY_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://jeniya.top").rstrip("/")


def relay_token(active_provider: str) -> str:
    if active_provider == "yunwu":
        return os.getenv("YUNWU_API_KEY") or os.getenv("AI_RELAY_API_KEY") or ""
    if uses_gemini_relay_provider(active_provider):
        return os.getenv("SIMPLE_RELAY_API_KEY") or os.getenv("YUNWU_API_KEY") or os.getenv("AI_RELAY_API_KEY") or ""
    return os.getenv("GEMINI_RELAY_API_KEY") or os.getenv("YUNWU_API_KEY") or os.getenv("AI_RELAY_API_KEY") or ""


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
