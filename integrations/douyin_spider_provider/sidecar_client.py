from __future__ import annotations

from typing import Any

import requests


class DouyinSpiderSidecarClient:
    def __init__(self, base_url: str, *, timeout: int = 60):
        self.base_url = str(base_url or "").rstrip("/")
        self.timeout = timeout

    def status(self) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}/status", timeout=min(self.timeout, 10))
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {"ready": False, "errors": ["Invalid sidecar status response"]}

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(f"{self.base_url}/run", json=payload, timeout=self.timeout)
        try:
            data = response.json() if response.text else {}
        except ValueError:
            data = {"raw_text": response.text}
        if response.status_code >= 400:
            message = data.get("detail") if isinstance(data, dict) else data
            raise RuntimeError(f"Douyin Spider sidecar HTTP {response.status_code}: {message}")
        return data if isinstance(data, dict) else {"status": "ok", "data": data}
