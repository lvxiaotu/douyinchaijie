from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.error_log_store import write_error_log
from .douyin import read_env_map, write_env_values
from backend.app.ai_provider_state import summarize_provider_state

router = APIRouter(prefix="/api/ai-provider", tags=["ai-provider"])


def _dump_payload(payload: Any) -> dict[str, Any]:
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    dict_dump = getattr(payload, "dict", None)
    if callable(dict_dump):
        return dict_dump()
    return dict(payload)


def _log_ai_provider_error(
    *,
    path: str,
    method: str,
    request: dict[str, Any],
    exc: Exception,
    api_base: str,
    status_code: int | None = None,
    response_text: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    write_error_log(
        namespace="ai-provider",
        path=path,
        method=method,
        request=request,
        exc=exc,
        api_base=api_base,
        status_code=status_code,
        response_text=response_text,
        extra=extra,
    )


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    return "***"


def _request_payload(payload: AiProviderConfigPayload) -> dict[str, Any]:
    data = _dump_payload(payload)
    data["native_api_key"] = _mask_secret(str(data.get("native_api_key") or ""))
    data["relay_api_key"] = _mask_secret(str(data.get("relay_api_key") or ""))
    return {"json_body": data}


class AiProviderConfigPayload(BaseModel):
    provider: str = Field(default="gemini")
    access_mode: str = Field(default="relay")
    native_api_key: str = Field(default="")
    relay_base_url: str = Field(default="https://jeniya.top")
    relay_api_key: str = Field(default="")
    model: str = Field(default="gemini-2.5-flash")
    local_endpoint: str = Field(default="")
    api_format: str = Field(default="responses")
    models: list[str] = Field(default_factory=list)


@router.get("/config")
def get_config() -> dict[str, Any]:
    env = read_env_map()
    gemini = {
        "provider": "gemini",
        "access_mode": "relay",
        "native_api_key": "",
        "relay_base_url": env.get("GEMINI_RELAY_BASE_URL") or env.get("YUNWU_BASE_URL") or env.get("AI_RELAY_BASE_URL", "https://yunwu.ai"),
        "relay_api_key": env.get("GEMINI_RELAY_API_KEY") or env.get("YUNWU_API_KEY") or env.get("AI_RELAY_API_KEY", ""),
        "model": env.get("GEMINI_MODEL") or env.get("AI_MODEL", "gemini-2.5-flash"),
        "models": env_list(env, "GEMINI_MODELS", ["gemini-2.5-flash", "gemini-2.0-flash"]),
        "api_format": "generate_content",
        "local_endpoint": "",
    }
    openai = {
        "provider": "openai",
        "access_mode": "relay",
        "native_api_key": "",
        "relay_base_url": env.get("OPENAI_RELAY_BASE_URL") or env.get("AI_RELAY_BASE_URL") or env.get("YUNWU_BASE_URL", "https://yunwu.ai/v1"),
        "relay_api_key": env.get("OPENAI_RELAY_API_KEY") or env.get("AI_RELAY_API_KEY") or env.get("YUNWU_API_KEY", ""),
        "model": env.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "models": env_list(env, "OPENAI_MODELS", ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"]),
        "api_format": env.get("OPENAI_API_FORMAT", "chat_completions"),
        "local_endpoint": "",
    }
    local = {
        "provider": "local",
        "access_mode": "local",
        "native_api_key": "",
        "relay_base_url": "",
        "relay_api_key": "",
        "model": env.get("LOCAL_AI_MODEL", ""),
        "models": env_list(env, "LOCAL_AI_MODELS", []),
        "api_format": "local",
        "local_endpoint": env.get("LOCAL_VIDEO_MODEL_ENDPOINT", ""),
    }
    simple_relay = {
        "provider": "simple_relay",
        "access_mode": "relay",
        "native_api_key": "",
        "relay_base_url": env.get("SIMPLE_RELAY_BASE_URL", ""),
        "relay_api_key": env.get("SIMPLE_RELAY_API_KEY", ""),
        "model": env.get("SIMPLE_RELAY_MODEL", "gemini-2.5-flash"),
        "models": env_list(env, "SIMPLE_RELAY_MODELS", ["gemini-2.5-flash", "gemini-2.0-flash"]),
        "api_format": env.get("SIMPLE_RELAY_API_FORMAT", "gemini_generate_content"),
        "local_endpoint": "",
    }
    yunwu = {
        "provider": "yunwu",
        "access_mode": "relay",
        "native_api_key": "",
        "relay_base_url": env.get("YUNWU_BASE_URL", "https://yunwu.ai"),
        "relay_api_key": env.get("YUNWU_API_KEY", ""),
        "model": env.get("YUNWU_MODEL", "gemini-2.5-flash"),
        "models": env_list(env, "YUNWU_MODELS", ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro", "gpt-4o-mini"]),
        "api_format": env.get("YUNWU_API_FORMAT", "gemini_generate_content"),
        "local_endpoint": "",
    }
    deepseek = {
        "provider": "deepseek",
        "access_mode": "official",
        "native_api_key": env.get("DEEPSEEK_API_KEY", ""),
        "relay_base_url": env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        "relay_api_key": env.get("DEEPSEEK_API_KEY", ""),
        "model": env.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "models": env_list(
            env,
            "DEEPSEEK_MODELS",
            ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
        ),
        "api_format": "chat_completions",
        "local_endpoint": "",
    }
    volcano = {
        "provider": "volcano",
        "access_mode": "official",
        "native_api_key": env.get("VOLCANO_API_KEY", ""),
        "relay_base_url": env.get("VOLCANO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        "relay_api_key": env.get("VOLCANO_API_KEY", ""),
        "model": env.get("VOLCANO_MODEL", ""),
        "models": env_list(env, "VOLCANO_MODELS", []),
        "api_format": "chat_completions",
        "local_endpoint": "",
    }
    active_provider = env.get("AI_MODEL_PROVIDER", "gemini")
    provider_map = {
        "gemini": gemini,
        "openai": openai,
        "simple_relay": simple_relay,
        "yunwu": yunwu,
        "deepseek": deepseek,
        "volcano": volcano,
        "local": local,
    }
    active = provider_map.get(active_provider, gemini)
    config = {
        "active_provider": active_provider,
        "providers": {key: with_key_flags(value) for key, value in provider_map.items()},
        "provider": env.get("AI_MODEL_PROVIDER", "gemini"),
        "access_mode": active["access_mode"],
        "native_api_key": active["native_api_key"],
        "has_native_api_key": bool(active["native_api_key"]),
        "relay_base_url": active["relay_base_url"],
        "relay_api_key": active["relay_api_key"],
        "has_relay_api_key": bool(active["relay_api_key"]),
        "model": active["model"],
        "api_format": active["api_format"],
        "local_endpoint": active["local_endpoint"],
    }
    return config


@router.get("/diagnostics")
def diagnostics() -> dict[str, Any]:
    return summarize_provider_state()


@router.post("/config")
def save_config(payload: AiProviderConfigPayload) -> dict[str, Any]:
    try:
        model = payload.model or first_model(payload.models)
        encoded_models = encode_models(payload.models)
        updates = {"AI_MODEL_PROVIDER": payload.provider}
        if payload.provider == "gemini":
            updates.update(
                {
                    "AI_ACCESS_MODE": "relay",
                    "AI_NATIVE_API_KEY": "",
                    "AI_RELAY_BASE_URL": payload.relay_base_url,
                    "AI_RELAY_API_KEY": payload.relay_api_key,
                    "AI_MODEL": model,
                    "GEMINI_ACCESS_MODE": "relay",
                    "GEMINI_API_KEY": "",
                    "GEMINI_RELAY_BASE_URL": payload.relay_base_url,
                    "GEMINI_RELAY_API_KEY": payload.relay_api_key,
                    "GEMINI_MODEL": model,
                    "GEMINI_MODELS": encoded_models,
                }
            )
        if payload.provider == "openai":
            updates.update(
                {
                    "AI_ACCESS_MODE": "relay",
                    "AI_NATIVE_API_KEY": "",
                    "AI_RELAY_BASE_URL": payload.relay_base_url,
                    "AI_RELAY_API_KEY": payload.relay_api_key,
                    "AI_MODEL": model,
                    "OPENAI_ACCESS_MODE": "relay",
                    "OPENAI_API_KEY": "",
                    "OPENAI_RELAY_BASE_URL": payload.relay_base_url,
                    "OPENAI_RELAY_API_KEY": payload.relay_api_key,
                    "OPENAI_MODEL": model,
                    "OPENAI_MODELS": encoded_models,
                    "OPENAI_API_FORMAT": payload.api_format,
                }
            )
        if payload.provider == "simple_relay":
            updates.update(
                {
                    "AI_ACCESS_MODE": "relay",
                    "AI_NATIVE_API_KEY": "",
                    "AI_RELAY_BASE_URL": payload.relay_base_url,
                    "AI_RELAY_API_KEY": payload.relay_api_key,
                    "AI_MODEL": model,
                    "SIMPLE_RELAY_BASE_URL": payload.relay_base_url,
                    "SIMPLE_RELAY_API_KEY": payload.relay_api_key,
                    "SIMPLE_RELAY_MODEL": model,
                    "SIMPLE_RELAY_MODELS": encoded_models,
                    "SIMPLE_RELAY_API_FORMAT": payload.api_format,
                    "GEMINI_ACCESS_MODE": "relay",
                    "GEMINI_RELAY_BASE_URL": payload.relay_base_url,
                    "GEMINI_RELAY_API_KEY": payload.relay_api_key,
                    "GEMINI_MODEL": model,
                }
            )
        if payload.provider == "yunwu":
            updates.update(
                {
                    "AI_ACCESS_MODE": "relay",
                    "AI_NATIVE_API_KEY": "",
                    "AI_RELAY_BASE_URL": payload.relay_base_url,
                    "AI_RELAY_API_KEY": payload.relay_api_key,
                    "AI_MODEL": model,
                    "YUNWU_BASE_URL": payload.relay_base_url,
                    "YUNWU_API_KEY": payload.relay_api_key,
                    "YUNWU_MODEL": model,
                    "YUNWU_MODELS": encoded_models,
                    "YUNWU_API_FORMAT": payload.api_format,
                    "GEMINI_ACCESS_MODE": "relay",
                    "GEMINI_RELAY_BASE_URL": payload.relay_base_url,
                    "GEMINI_RELAY_API_KEY": payload.relay_api_key,
                    "GEMINI_MODEL": model,
                }
            )
        if payload.provider == "deepseek":
            key = payload.native_api_key or payload.relay_api_key
            updates.update(
                {
                    "AI_ACCESS_MODE": "official",
                    "AI_NATIVE_API_KEY": key,
                    "AI_RELAY_BASE_URL": payload.relay_base_url,
                    "AI_RELAY_API_KEY": key,
                    "AI_MODEL": model,
                    "DEEPSEEK_API_KEY": key,
                    "DEEPSEEK_BASE_URL": payload.relay_base_url,
                    "DEEPSEEK_MODEL": model,
                    "DEEPSEEK_MODELS": encoded_models,
                }
            )
        if payload.provider == "volcano":
            key = payload.native_api_key or payload.relay_api_key
            updates.update(
                {
                    "AI_ACCESS_MODE": "official",
                    "AI_NATIVE_API_KEY": key,
                    "AI_RELAY_BASE_URL": payload.relay_base_url,
                    "AI_RELAY_API_KEY": key,
                    "AI_MODEL": model,
                    "VOLCANO_API_KEY": key,
                    "VOLCANO_BASE_URL": payload.relay_base_url,
                    "VOLCANO_MODEL": model,
                    "VOLCANO_MODELS": encoded_models,
                }
            )
        if payload.provider == "local":
            updates.update(
                {
                    "LOCAL_AI_MODEL": model,
                    "LOCAL_AI_MODELS": encoded_models,
                    "LOCAL_VIDEO_MODEL_ENDPOINT": payload.local_endpoint,
                }
            )
        write_env_values(updates)
        return {"status": "ok", "config": get_config()}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
                "hint": "Unable to save AI provider config.",
            },
        ) from exc


@router.post("/test")
def test_config(payload: AiProviderConfigPayload) -> dict[str, Any]:
    try:
        if not payload.model:
            payload.model = first_model(payload.models)
        if payload.provider == "gemini":
            payload.access_mode = "relay"
            return test_gemini_relay(payload)
        if payload.provider == "openai":
            payload.access_mode = "relay"
            if payload.api_format == "responses":
                payload.api_format = "chat_completions"
            return test_openai_compatible(payload)
        if payload.provider in {"simple_relay", "yunwu"} and payload.api_format == "gemini_generate_content":
            return test_gemini_relay(payload)
        if payload.provider in {"simple_relay", "yunwu", "deepseek", "volcano"}:
            return test_openai_compatible(payload)
        if payload.provider == "local":
            return test_local_endpoint(payload)
        raise ValueError(f"Unsupported provider: {payload.provider}")
    except Exception as exc:
        return {
            "ok": False,
            "provider": payload.provider,
            "access_mode": payload.access_mode,
            "model": payload.model,
            "message": f"{type(exc).__name__}: {exc}",
        }


def test_gemini_relay(payload: AiProviderConfigPayload) -> dict[str, Any]:
    if not payload.relay_api_key:
        raise ValueError("Missing relay token.")
    base_url = (payload.relay_base_url or "https://jeniya.top").rstrip("/")
    url = f"{base_url}/v1beta/models/{payload.model}:generateContent?key="
    request_payload = {
        "json_body": {
            "contents": [{"parts": [{"text": "Reply with exactly: ok"}]}],
            "generationConfig": {"responseMimeType": "text/plain"},
        },
        "headers": {
            "Authorization": "Bearer ***",
            "Content-Type": "application/json",
        },
    }
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {payload.relay_api_key}",
                "Content-Type": "application/json",
            },
            json=request_payload["json_body"],
            timeout=60,
        )
    except requests.RequestException as exc:
        _log_ai_provider_error(
            path=urlparse(url).path or "/v1beta/models/:generateContent",
            method="POST",
            request=request_payload,
            exc=exc,
            api_base=base_url,
            extra={"phase": "relay_request_exception", "model": payload.model},
        )
        raise
    if not response.ok:
        _log_ai_provider_error(
            path=urlparse(url).path or "/v1beta/models/:generateContent",
            method="POST",
            request=request_payload,
            exc=RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}"),
            api_base=base_url,
            status_code=response.status_code,
            response_text=response.text[:4000],
            extra={"phase": "relay_http_error", "model": payload.model},
        )
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    try:
        data = response.json()
    except ValueError as exc:
        _log_ai_provider_error(
            path=urlparse(url).path or "/v1beta/models/:generateContent",
            method="POST",
            request=request_payload,
            exc=exc,
            api_base=base_url,
            status_code=response.status_code,
            response_text=response.text[:4000],
            extra={"phase": "relay_non_json_response", "model": payload.model},
        )
        raise RuntimeError(f"Non-JSON response: {response.text[:500]}") from exc
    sample = extract_gemini_text(data)
    return {
        "ok": True,
        "provider": payload.provider,
        "access_mode": payload.access_mode,
        "model": payload.model,
        "message": "中转站连接成功。",
        "sample": sample[:200],
    }


def test_openai_compatible(payload: AiProviderConfigPayload) -> dict[str, Any]:
    api_key = payload.relay_api_key if payload.access_mode == "relay" else payload.native_api_key
    if payload.provider in {"deepseek", "volcano"}:
        api_key = payload.native_api_key or payload.relay_api_key
    if payload.provider in {"simple_relay", "yunwu"}:
        api_key = payload.relay_api_key
    if not api_key:
        raise ValueError("Missing API key.")
    base_url = resolve_openai_compatible_base_url(payload).rstrip("/")
    if payload.api_format == "responses":
        return test_openai_responses(payload, api_key, base_url)
    return test_openai_chat_completions(payload, api_key, base_url)


def resolve_openai_compatible_base_url(payload: AiProviderConfigPayload) -> str:
    if payload.relay_base_url:
        return payload.relay_base_url
    defaults = {
        "openai": "https://yunwu.ai/v1",
        "deepseek": "https://api.deepseek.com",
        "volcano": "https://ark.cn-beijing.volces.com/api/v3",
    }
    return defaults.get(payload.provider, "")


def test_openai_responses(payload: AiProviderConfigPayload, api_key: str, base_url: str) -> dict[str, Any]:
    if payload.provider == "openai":
        raise RuntimeError("OpenAI native Responses API is disabled. Use relay chat_completions.")
    url = f"{base_url}/v1/responses"
    request_payload = {
        "json_body": {
            "model": payload.model,
            "input": "Reply with exactly: ok",
            "max_output_tokens": 16,
        },
        "headers": {
            "Authorization": "Bearer ***",
            "Content-Type": "application/json",
        },
    }
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_payload["json_body"],
            timeout=60,
        )
    except requests.RequestException as exc:
        _log_ai_provider_error(
            path=urlparse(url).path or "/v1/responses",
            method="POST",
            request=request_payload,
            exc=exc,
            api_base=base_url,
            extra={"phase": "openai_responses_request_exception", "model": payload.model},
        )
        raise
    if not response.ok:
        _log_ai_provider_error(
            path=urlparse(url).path or "/v1/responses",
            method="POST",
            request=request_payload,
            exc=RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}"),
            api_base=base_url,
            status_code=response.status_code,
            response_text=response.text[:4000],
            extra={"phase": "openai_responses_http_error", "model": payload.model},
        )
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    try:
        data = response.json()
    except ValueError as exc:
        _log_ai_provider_error(
            path=urlparse(url).path or "/v1/responses",
            method="POST",
            request=request_payload,
            exc=exc,
            api_base=base_url,
            status_code=response.status_code,
            response_text=response.text[:4000],
            extra={"phase": "openai_responses_non_json_response", "model": payload.model},
        )
        raise RuntimeError(f"Non-JSON response: {response.text[:500]}") from exc
    sample = data.get("output_text") or extract_openai_responses_text(data)
    return {
        "ok": True,
        "provider": payload.provider,
        "access_mode": payload.access_mode,
        "model": payload.model,
        "message": "OpenAI Responses 连接成功。",
        "sample": sample[:200],
    }


def test_openai_chat_completions(payload: AiProviderConfigPayload, api_key: str, base_url: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/chat/completions" if base_url.rstrip("/").endswith("/v1") else f"{base_url}/v1/chat/completions"
    request_payload = {
        "json_body": {
            "model": payload.model,
            "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
            "max_tokens": 8,
        },
        "headers": {
            "Authorization": "Bearer ***",
            "Content-Type": "application/json",
        },
    }
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_payload["json_body"],
            timeout=60,
        )
    except requests.RequestException as exc:
        _log_ai_provider_error(
            path=urlparse(url).path or "/v1/chat/completions",
            method="POST",
            request=request_payload,
            exc=exc,
            api_base=base_url,
            extra={"phase": "openai_chat_request_exception", "model": payload.model},
        )
        raise
    if not response.ok:
        _log_ai_provider_error(
            path=urlparse(url).path or "/v1/chat/completions",
            method="POST",
            request=request_payload,
            exc=RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}"),
            api_base=base_url,
            status_code=response.status_code,
            response_text=response.text[:4000],
            extra={"phase": "openai_chat_http_error", "model": payload.model},
        )
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    try:
        data = response.json()
    except ValueError as exc:
        _log_ai_provider_error(
            path=urlparse(url).path or "/v1/chat/completions",
            method="POST",
            request=request_payload,
            exc=exc,
            api_base=base_url,
            status_code=response.status_code,
            response_text=response.text[:4000],
            extra={"phase": "openai_chat_non_json_response", "model": payload.model},
        )
        raise RuntimeError(f"Non-JSON response: {response.text[:500]}") from exc
    sample = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    return {
        "ok": True,
        "provider": payload.provider,
        "access_mode": payload.access_mode,
        "model": payload.model,
        "message": "OpenAI 兼容连接成功。",
        "sample": sample[:200],
    }


def test_local_endpoint(payload: AiProviderConfigPayload) -> dict[str, Any]:
    if not payload.local_endpoint:
        raise ValueError("Missing local endpoint.")
    try:
        response = requests.get(payload.local_endpoint, timeout=15)
    except requests.RequestException as exc:
        _log_ai_provider_error(
            path=urlparse(payload.local_endpoint).path or "/api/ai-provider/test/local-endpoint",
            method="GET",
            request={"url": payload.local_endpoint},
            exc=exc,
            api_base=payload.local_endpoint,
            extra={"phase": "local_endpoint_request_exception"},
        )
        raise
    if not response.ok:
        _log_ai_provider_error(
            path=urlparse(payload.local_endpoint).path or "/api/ai-provider/test/local-endpoint",
            method="GET",
            request={"url": payload.local_endpoint},
            exc=RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}"),
            api_base=payload.local_endpoint,
            status_code=response.status_code,
            response_text=response.text[:4000],
            extra={"phase": "local_endpoint_http_error"},
        )
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    return {
        "ok": response.ok,
        "provider": payload.provider,
        "access_mode": payload.access_mode,
        "model": payload.model,
        "message": f"本地地址响应 HTTP {response.status_code}。",
        "sample": response.text[:200],
    }


def extract_gemini_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    return "\n".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()


def extract_openai_responses_text(data: dict[str, Any]) -> str:
    chunks = []
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def with_key_flags(config: dict[str, Any]) -> dict[str, Any]:
    result = dict(config)
    result["has_native_api_key"] = bool(result.get("native_api_key"))
    result["has_relay_api_key"] = bool(result.get("relay_api_key"))
    return result


def env_list(env: dict[str, str], key: str, fallback: list[str]) -> list[str]:
    value = env.get(key, "")
    if not value:
        return fallback
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def encode_models(models: list[str]) -> str:
    cleaned = [model.strip() for model in models if model.strip()]
    return json.dumps(cleaned, ensure_ascii=False)


def first_model(models: list[str]) -> str:
    for model in models:
        if model.strip():
            return model.strip()
    return ""
