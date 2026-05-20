from __future__ import annotations

import os
import time
from typing import Any

import requests


RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def default_timeout_seconds(kind: str = "download") -> float:
    env_name = {
        "download": "AI_VIDEO_DOWNLOAD_TIMEOUT_SECONDS",
        "model": "AI_VIDEO_MODEL_TIMEOUT_SECONDS",
        "asr": "VOLCENGINE_ASR_HTTP_TIMEOUT_SECONDS",
    }.get(kind, "AI_VIDEO_HTTP_TIMEOUT_SECONDS")
    return env_float(env_name, env_float("AI_VIDEO_HTTP_TIMEOUT_SECONDS", 120.0))


def default_max_retries(kind: str = "download") -> int:
    env_name = {
        "download": "AI_VIDEO_DOWNLOAD_MAX_RETRIES",
        "model": "AI_VIDEO_MODEL_MAX_RETRIES",
        "asr": "VOLCENGINE_ASR_MAX_RETRIES",
    }.get(kind, "AI_VIDEO_HTTP_MAX_RETRIES")
    return env_int(env_name, env_int("AI_VIDEO_HTTP_MAX_RETRIES", 2))


def retry_delays(max_retries: int) -> list[float]:
    raw = os.getenv("AI_VIDEO_HTTP_RETRY_DELAYS", "2,5,10")
    values: list[float] = []
    for item in raw.split(","):
        try:
            values.append(max(0.0, float(item.strip())))
        except ValueError:
            continue
    if not values:
        values = [2.0, 5.0, 10.0]
    while len(values) < max_retries:
        values.append(values[-1])
    return values


def request_with_retries(
    method: str,
    url: str,
    *,
    session: Any | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
    retryable_status_codes: set[int] | None = None,
    cancel_check: Any | None = None,
    **kwargs: Any,
):
    client = session or requests
    timeout_seconds = timeout if timeout is not None else default_timeout_seconds()
    retries = default_max_retries() if max_retries is None else max_retries
    statuses = retryable_status_codes or RETRYABLE_STATUS_CODES
    delays = retry_delays(retries)
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        if cancel_check:
            cancel_check()
        try:
            response = getattr(client, method.lower())(url, timeout=timeout_seconds, **kwargs)
            if getattr(response, "status_code", 0) in statuses and attempt < retries:
                last_error = RuntimeError(f"HTTP {response.status_code}: {getattr(response, 'text', '')[:500]}")
                if cancel_check:
                    cancel_check()
                time.sleep(delays[min(attempt, len(delays) - 1)])
                continue
            return response
        except Exception as exc:
            if exc.__class__.__name__ == "AiVideoTaskCancelled":
                raise
            last_error = exc
            if attempt >= retries:
                break
            if cancel_check:
                cancel_check()
            time.sleep(delays[min(attempt, len(delays) - 1)])
    raise RuntimeError(f"HTTP {method.upper()} request failed after {retries + 1} attempt(s): {last_error}") from last_error


def get_with_retries(url: str, **kwargs: Any):
    return request_with_retries("GET", url, **kwargs)


def post_with_retries(url: str, **kwargs: Any):
    return request_with_retries("POST", url, **kwargs)
