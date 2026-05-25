from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from integrations.douyin_spider_provider.adapter import DouyinSpiderAdapter, DouyinSpiderApiError


app = FastAPI(title="Douyin Spider Sidecar")


class RunRequest(BaseModel):
    action: str = Field(..., description="Douyin Spider adapter action")

    class Config:
        extra = "allow"


def adapter() -> DouyinSpiderAdapter:
    return DouyinSpiderAdapter({"execution_mode": "inprocess"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict[str, Any]:
    return adapter().status()


@app.post("/run")
def run(payload: RunRequest) -> dict[str, Any]:
    try:
        return adapter().run(payload.model_dump())
    except DouyinSpiderApiError as exc:
        raise HTTPException(status_code=502, detail=exc.to_dict()) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error_type": type(exc).__name__, "message": str(exc)},
        ) from exc
