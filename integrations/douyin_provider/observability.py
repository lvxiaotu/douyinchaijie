from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


_lock = threading.Lock()
_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "errors": 0, "fallbacks": 0, "latency_ms_total": 0})


def observability_enabled() -> bool:
    return str(os.getenv("DOUYIN_PROVIDER_OBSERVABILITY_ENABLED", "true")).strip().lower() not in {"0", "false", "no"}


def event_log_path() -> Path:
    configured = os.getenv("DOUYIN_PROVIDER_EVENT_LOG")
    if configured:
        return Path(configured)
    return Path(os.getenv("DATA_DIR") or "data/runtime") / "douyin" / "provider_events.jsonl"


def record_provider_call(
    *,
    mode: str,
    provider: str,
    method: str,
    status: str,
    latency_ms: int,
    fallback_used: bool = False,
    error_type: str = "",
    error_message: str = "",
) -> None:
    if not observability_enabled():
        return
    event = {
        "ts": int(time.time()),
        "mode": mode,
        "provider": provider,
        "method": method,
        "status": status,
        "latency_ms": latency_ms,
        "fallback_used": fallback_used,
        "error_type": error_type,
        "error_message": error_message[:500],
    }
    event = {key: value for key, value in event.items() if value not in ["", None, False]}
    key = f"{mode}:{provider}:{method}"
    with _lock:
        bucket = _stats[key]
        bucket["calls"] += 1
        bucket["latency_ms_total"] += latency_ms
        if status != "ok":
            bucket["errors"] += 1
        if fallback_used:
            bucket["fallbacks"] += 1
        path = event_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")


def get_provider_metrics() -> dict[str, Any]:
    log_summary = _read_log_summary()
    with _lock:
        calls = []
        total_calls = 0
        total_errors = 0
        total_fallbacks = 0
        for key, value in sorted(_stats.items()):
            mode, provider, method = key.split(":", 2)
            count = int(value.get("calls") or 0)
            latency_total = int(value.get("latency_ms_total") or 0)
            errors = int(value.get("errors") or 0)
            fallbacks = int(value.get("fallbacks") or 0)
            total_calls += count
            total_errors += errors
            total_fallbacks += fallbacks
            calls.append(
                {
                    "mode": mode,
                    "provider": provider,
                    "method": method,
                    "calls": count,
                    "errors": errors,
                    "fallbacks": fallbacks,
                    "avg_latency_ms": round(latency_total / count, 2) if count else 0,
                }
            )
        return {
            "enabled": observability_enabled(),
            "event_log": str(event_log_path()),
            "total_calls": total_calls,
            "total_errors": total_errors,
            "total_fallbacks": total_fallbacks,
            "calls": calls,
            "log_total_calls": log_summary["total_calls"],
            "log_total_errors": log_summary["total_errors"],
            "log_total_fallbacks": log_summary["total_fallbacks"],
            "recent_events": log_summary["recent_events"],
        }


def _read_log_summary(max_events: int = 1000) -> dict[str, Any]:
    path = event_log_path()
    if not path.exists():
        return {"total_calls": 0, "total_errors": 0, "total_fallbacks": 0, "recent_events": []}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-max_events:]
    except OSError:
        return {"total_calls": 0, "total_errors": 0, "total_fallbacks": 0, "recent_events": []}
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return {
        "total_calls": len(events),
        "total_errors": sum(1 for item in events if item.get("status") != "ok"),
        "total_fallbacks": sum(1 for item in events if item.get("fallback_used")),
        "recent_events": events[-20:],
    }
