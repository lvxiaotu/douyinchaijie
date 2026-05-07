from __future__ import annotations

import os
from typing import Any


def active_ai_provider(default: str = "mock") -> str:
    return os.getenv("AI_MODEL_PROVIDER") or default


def is_gemini_provider(provider: str) -> bool:
    return provider == "gemini"


def is_openai_compatible_provider(provider: str) -> bool:
    return provider in {"openai", "simple_relay", "yunwu", "deepseek", "volcano"}


def active_model(default: str = "") -> str:
    return os.getenv("AI_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv("GEMINI_MODEL") or default


def active_api_format(default: str = "chat_completions") -> str:
    provider = active_ai_provider()
    if provider == "openai":
        return os.getenv("OPENAI_API_FORMAT", "responses")
    if provider == "simple_relay":
        return os.getenv("SIMPLE_RELAY_API_FORMAT", default)
    return default


def openai_compatible_credentials(provider: str | None = None) -> dict[str, str]:
    selected = provider or active_ai_provider()
    if selected == "openai":
        access_mode = os.getenv("OPENAI_ACCESS_MODE") or os.getenv("AI_ACCESS_MODE") or "official"
        if access_mode == "relay":
            return {
                "api_key": os.getenv("OPENAI_RELAY_API_KEY") or os.getenv("AI_RELAY_API_KEY") or "",
                "base_url": os.getenv("OPENAI_RELAY_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "",
                "access_mode": access_mode,
            }
        return {
            "api_key": os.getenv("OPENAI_API_KEY") or os.getenv("AI_NATIVE_API_KEY") or "",
            "base_url": "https://api.openai.com",
            "access_mode": access_mode,
        }
    if selected == "simple_relay":
        return {
            "api_key": os.getenv("SIMPLE_RELAY_API_KEY") or os.getenv("AI_RELAY_API_KEY") or "",
            "base_url": os.getenv("SIMPLE_RELAY_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "",
            "access_mode": "relay",
        }
    if selected == "yunwu":
        return {
            "api_key": os.getenv("YUNWU_API_KEY") or os.getenv("AI_RELAY_API_KEY") or "",
            "base_url": os.getenv("YUNWU_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://yunwu.ai",
            "access_mode": "relay",
        }
    if selected == "deepseek":
        return {
            "api_key": os.getenv("DEEPSEEK_API_KEY") or "",
            "base_url": os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
            "access_mode": "official",
        }
    if selected == "volcano":
        return {
            "api_key": os.getenv("VOLCANO_API_KEY") or "",
            "base_url": os.getenv("VOLCANO_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3",
            "access_mode": "official",
        }
    return {"api_key": "", "base_url": "", "access_mode": ""}


def summarize_provider_state() -> dict[str, Any]:
    provider = active_ai_provider()
    creds = openai_compatible_credentials(provider) if is_openai_compatible_provider(provider) else {}
    return {
        "provider": provider,
        "model": active_model(),
        "api_format": active_api_format(),
        "access_mode": creds.get("access_mode") or os.getenv("GEMINI_ACCESS_MODE") or os.getenv("AI_ACCESS_MODE") or "",
        "base_url": creds.get("base_url") or os.getenv("GEMINI_RELAY_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "",
        "has_api_key": bool(creds.get("api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_RELAY_API_KEY") or os.getenv("AI_NATIVE_API_KEY") or os.getenv("AI_RELAY_API_KEY")),
    }
