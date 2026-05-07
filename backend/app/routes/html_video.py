from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.routes.douyin import read_env_map, write_env_values
from backend.app.task_store import jianying_asset_counts, upsert_jianying_assets
from integrations.html_video_render.adapter import HtmlVideoRenderAdapter

router = APIRouter(prefix="/api/tools/html-video", tags=["html-video"])
logger = logging.getLogger(__name__)


class HtmlVideoConfigPayload(BaseModel):
    output_dir: str = Field(default="./data/runtime/html_video_render")
    renderer: str = Field(default="placeholder", pattern="^(placeholder|python_frames|playwright|hyperframes)$")
    width: int = Field(default=1080, ge=120, le=7680)
    height: int = Field(default=1920, ge=120, le=7680)
    fps: int = Field(default=30, ge=1, le=120)
    ffmpeg_binary: str = Field(default="")


class HtmlVideoRenderRequest(BaseModel):
    name: str = Field(default="html-render")
    width: int | None = Field(default=None, ge=120, le=7680)
    height: int | None = Field(default=None, ge=120, le=7680)
    fps: int | None = Field(default=None, ge=1, le=120)
    duration_seconds: float = Field(default=3, ge=0.1, le=600)
    html: str = Field(default="")
    renderer: str | None = Field(default=None, pattern="^(placeholder|python_frames|playwright|hyperframes)$")


def adapter() -> HtmlVideoRenderAdapter:
    return HtmlVideoRenderAdapter()


def integration_error(exc: Exception) -> HTTPException:
    logger.exception("HTML video render integration failed")
    return HTTPException(
        status_code=500,
        detail={
            "error_type": type(exc).__name__,
            "message": str(exc),
            "hint": "Check HTML video render config and output directory.",
        },
    )


@router.get("/status")
def status() -> dict[str, Any]:
    return adapter().status()


@router.get("/config")
def get_config() -> dict[str, Any]:
    env = read_env_map()
    return {
        "output_dir": env.get("HTML_VIDEO_OUTPUT_DIR", "./data/runtime/html_video_render"),
        "renderer": env.get("HTML_VIDEO_RENDERER", "placeholder"),
        "width": int(env.get("HTML_VIDEO_WIDTH", "1080") or 1080),
        "height": int(env.get("HTML_VIDEO_HEIGHT", "1920") or 1920),
        "fps": int(env.get("HTML_VIDEO_FPS", "30") or 30),
        "ffmpeg_binary": env.get("HTML_VIDEO_FFMPEG_BINARY", env.get("FFMPEG_BINARY", "")),
    }


@router.post("/config")
def save_config(payload: HtmlVideoConfigPayload) -> dict[str, Any]:
    try:
        write_env_values(
            {
                "HTML_VIDEO_OUTPUT_DIR": payload.output_dir,
                "HTML_VIDEO_RENDERER": payload.renderer,
                "HTML_VIDEO_WIDTH": str(payload.width),
                "HTML_VIDEO_HEIGHT": str(payload.height),
                "HTML_VIDEO_FPS": str(payload.fps),
                "HTML_VIDEO_FFMPEG_BINARY": payload.ffmpeg_binary,
            }
        )
        return {"status": "ok", "config": get_config(), "tool_status": status()}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/render")
def render(payload: HtmlVideoRenderRequest) -> dict[str, Any]:
    try:
        instance = HtmlVideoRenderAdapter(config={"renderer": payload.renderer} if payload.renderer else None)
        result = instance.render(payload.model_dump())
        asset = result.get("asset")
        if asset:
            saved = upsert_jianying_assets([asset], source="html_render")
            result["asset_saved"] = saved[0] if saved else None
            result["asset_counts"] = jianying_asset_counts()
        return result
    except Exception as exc:
        raise integration_error(exc) from exc
