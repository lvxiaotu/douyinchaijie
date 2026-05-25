from __future__ import annotations

import time
from typing import Any

from integrations.douyin_provider.observability import record_provider_call


class ObservedDouyinProvider:
    def __init__(self, provider: Any, *, mode: str):
        self.provider = provider
        self.mode = mode

    @property
    def manifest(self) -> Any:
        return getattr(self.provider, "manifest", None)

    def status(self) -> dict[str, Any]:
        status = getattr(self.provider, "status", None)
        if callable(status):
            return status()
        return {"id": self.provider_id(), "ready": True, "errors": []}

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]:
        validate = getattr(self.provider, "validate_config", None)
        if not callable(validate):
            return []
        try:
            return validate(config)
        except TypeError:
            return validate()

    def provider_id(self) -> str:
        manifest = getattr(self.provider, "manifest", None)
        return str(getattr(manifest, "id", "") or self.provider.__class__.__name__)

    def __getattr__(self, name: str) -> Any:
        target = getattr(self.provider, name)
        if name.startswith("_") or not callable(target):
            return target

        def observed_call(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            provider_id = self.provider_id()
            try:
                result = target(*args, **kwargs)
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                record_provider_call(
                    mode=self.mode,
                    provider=provider_id,
                    method=name,
                    status="error",
                    latency_ms=latency_ms,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                raise
            latency_ms = int((time.perf_counter() - started) * 1000)
            trace = result.get("provider_trace") if isinstance(result, dict) and isinstance(result.get("provider_trace"), dict) else {}
            record_provider_call(
                mode=self.mode,
                provider=str(trace.get("provider") or provider_id),
                method=name,
                status="ok",
                latency_ms=latency_ms,
                fallback_used=bool(trace.get("fallback_used")),
            )
            return result

        return observed_call
