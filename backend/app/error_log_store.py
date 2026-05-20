from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[2]
ERROR_LOG_ROOT = ROOT_DIR / "data" / "runtime" / "error"


def write_error_log(
    *,
    namespace: str,
    path: str,
    method: str,
    request: dict[str, Any] | None,
    exc: Exception,
    api_base: str = "",
    status_code: int | None = None,
    response_payload: Any = None,
    response_text: str = "",
    extra: dict[str, Any] | None = None,
) -> str:
    try:
        timestamp = datetime.now().astimezone()
        error_dir = ERROR_LOG_ROOT / namespace / timestamp.strftime("%Y%m%d")
        error_dir.mkdir(parents=True, exist_ok=True)
        endpoint_slug = (path.strip("/").split("/")[-1] or "request").replace(":", "_")
        file_name = f"{timestamp.strftime('%H%M%S-%f')}_{method.lower()}_{endpoint_slug}_{uuid4().hex[:8]}.json"
        record: dict[str, Any] = {
            "timestamp": timestamp.isoformat(timespec="seconds"),
            "timestamp_unix": int(timestamp.timestamp()),
            "namespace": namespace,
            "api_base": api_base,
            "path": path,
            "method": method,
            "request": request or {},
            "status_code": status_code,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        }
        if response_payload is not None:
            record["response"] = response_payload
        if response_text:
            record["response_text"] = response_text[:4000]
        if extra:
            record.update(extra)
        file_path = error_dir / file_name
        file_path.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return str(file_path)
    except Exception:
        return ""
