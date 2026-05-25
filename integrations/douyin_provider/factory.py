from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from integrations.douyin_legacy_tikhub import LegacyTikhubDouyinAdapter
from integrations.douyin_provider.fallback import FallbackDouyinProvider
from integrations.douyin_provider.observability import get_provider_metrics
from integrations.douyin_provider.observed import ObservedDouyinProvider
from integrations.douyin_spider_provider import DouyinSpiderAdapter


VALID_PROVIDER_MODES = {"tikhub", "spider", "spider_first"}


def configured_provider_mode() -> str:
    load_dotenv()
    mode = str(os.getenv("DOUYIN_PROVIDER_MODE") or "tikhub").strip().lower()
    return mode if mode in VALID_PROVIDER_MODES else "tikhub"


def get_douyin_provider(mode: str | None = None, *, observed: bool = True) -> Any:
    resolved_mode = (mode or configured_provider_mode()).strip().lower()
    if resolved_mode == "spider":
        provider: Any = DouyinSpiderAdapter()
    elif resolved_mode == "spider_first":
        provider = FallbackDouyinProvider(
            primary=DouyinSpiderAdapter(),
            fallback=LegacyTikhubDouyinAdapter(),
            mode="spider_first",
        )
    else:
        resolved_mode = "tikhub"
        provider = LegacyTikhubDouyinAdapter()
    return ObservedDouyinProvider(provider, mode=resolved_mode) if observed else provider


def get_douyin_search_provider() -> LegacyTikhubDouyinAdapter:
    return LegacyTikhubDouyinAdapter()


def get_douyin_provider_status() -> dict[str, Any]:
    mode = configured_provider_mode()
    active = get_douyin_provider(mode)
    legacy = LegacyTikhubDouyinAdapter()
    spider = DouyinSpiderAdapter()
    return {
        "status": "ok",
        "provider": "douyin-provider",
        "mode": mode,
        "active": _safe_status(active),
        "legacy_tikhub": _safe_status(legacy),
        "spider": _safe_status(spider),
        "search_provider": "legacy-tikhub",
        "modes": sorted(VALID_PROVIDER_MODES),
        "metrics": get_provider_metrics(),
    }


def _safe_status(provider: Any) -> dict[str, Any]:
    status = getattr(provider, "status", None)
    if callable(status):
        try:
            result = status()
            if isinstance(result, dict):
                return result
        except Exception as exc:
            return {
                "id": _provider_id(provider),
                "ready": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
    validate = getattr(provider, "validate_config", None)
    if callable(validate):
        try:
            errors = validate()
            return {
                "id": _provider_id(provider),
                "ready": not errors,
                "errors": errors,
            }
        except Exception as exc:
            return {
                "id": _provider_id(provider),
                "ready": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
    return {"id": _provider_id(provider), "ready": True, "errors": []}


def _provider_id(provider: Any) -> str:
    if isinstance(provider, ObservedDouyinProvider):
        return provider.provider_id()
    manifest = getattr(provider, "manifest", None)
    return str(getattr(manifest, "id", "") or provider.__class__.__name__)
