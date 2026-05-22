import logging
import os
import json
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from dotenv import dotenv_values

from backend.app.routes.media_proxy import proxy_remote_media
from integrations.tikhub_douyin_api import TikhubDouyinApiAdapter
from integrations.tikhub_douyin_api.adapter import TikhubApiError

router = APIRouter(prefix="/api/integrations/douyin", tags=["douyin"])
logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT / ".env"


class UserProfileRequest(BaseModel):
    user_url: str = Field(..., description="Douyin user page URL")
    sec_user_id: str | None = Field(default=None, description="Douyin sec_user_id")


class UserVideosRequest(BaseModel):
    user_url: str | None = Field(default=None, description="Douyin user page URL")
    sec_user_id: str | None = Field(default=None, description="Douyin sec_user_id")
    max_items: int | None = Field(default=None, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=50)
    max_cursor: int = Field(default=0, ge=0)


class WorkDetailRequest(BaseModel):
    work_url: str = Field(..., description="Douyin video/work URL")
    region: str = Field(default="US", description="TikHub region for app/v3 video endpoint")


class VideoCommentsRequest(BaseModel):
    aweme_id: str = Field(..., description="Douyin aweme_id")
    max_items: int | None = Field(default=100, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=50)
    cursor: int = Field(default=0, ge=0)


class VideoCommentRepliesRequest(BaseModel):
    item_id: str = Field(..., description="Douyin aweme_id/item_id")
    comment_id: str = Field(..., description="Parent comment id")
    max_items: int | None = Field(default=20, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=50)
    cursor: int = Field(default=0, ge=0)


class FavoriteDownloadRequest(BaseModel):
    sec_user_id: str | None = Field(default=None, description="Optional target sec_user_id")
    max_items: int = Field(default=18, ge=1, le=300)
    page_size: int = Field(default=18, ge=1, le=50)


class FavoriteItemsRequest(BaseModel):
    max_items: int | None = Field(default=None, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=50)
    max_cursor: int = Field(default=0, ge=0)


class DouyinConfigPayload(BaseModel):
    api_base: str = Field(default="https://api.tikhub.io")
    output_dir: str = Field(default="./data/runtime/douyin/downloads")
    cookie: str = Field(default="")


def tikhub_adapter() -> TikhubDouyinApiAdapter:
    return TikhubDouyinApiAdapter()


def _is_upstream_unavailable(exc: Exception) -> bool:
    current: Exception | None = exc
    while current is not None:
        if isinstance(current, (requests.ConnectionError, requests.Timeout)):
            return True
        text = f"{type(current).__name__}: {current}".lower()
        if any(
            marker in text
            for marker in (
                "connection refused",
                "failed to establish a new connection",
                "max retries exceeded",
                "connectionpool",
                "read timed out",
                "connect timed out",
            )
        ):
            return True
        current = current.__cause__ if isinstance(current.__cause__, Exception) else None
        if current is None and isinstance(exc.__context__, Exception):
            current = exc.__context__
    return False


def integration_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TikhubApiError):
        logger.warning("TikHub Douyin integration failed: %s", exc)
        return HTTPException(
            status_code=exc.status_code or 502,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
                "hint": "检查 TIKHUB_API_KEY、TikHub 额度或接口参数。",
                "upstream": exc.to_dict(),
            },
        )
    if _is_upstream_unavailable(exc):
        logger.warning("Douyin integration upstream unavailable: %s", exc)
        return HTTPException(
            status_code=503,
            detail={
                "error_type": type(exc).__name__,
                "message": "TikHub Douyin API 无法连接或请求超时",
                "hint": "请检查 TIKHUB_API_BASE、网络和 TikHub 服务状态。",
            },
        )
    logger.exception("Douyin integration failed")
    return HTTPException(
        status_code=500,
        detail={
            "error_type": type(exc).__name__,
            "message": str(exc),
            "hint": "检查 TIKHUB_API_KEY、TIKHUB_DOUYIN_WEB_COOKIE/DOUYIN_WEB_COOKIE 或接口参数。",
        },
    )


def read_env_map() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    return {key: value or "" for key, value in dotenv_values(ENV_PATH).items()}


def write_env_values(updates: dict[str, str]) -> None:
    existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen = set()
    output = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            value = encode_env_value(updates[key])
            output.append(f"{key}={value}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={encode_env_value(value)}")
    ENV_PATH.write_text("\n".join(output) + "\n", encoding="utf-8")
    for key, value in updates.items():
        os.environ[key] = value


def encode_env_value(value: str) -> str:
    if any(char in value for char in ["\n", "\r", "#", '"', "'"]):
        return json.dumps(value, ensure_ascii=False)
    return value


@router.get("/status")
def status() -> dict[str, Any]:
    instance = tikhub_adapter()
    errors = instance.validate_config()
    return {
        "id": instance.manifest.id,
        "name": instance.manifest.name,
        "repo_url": instance.manifest.repo_url,
        "ready": not errors,
        "errors": errors,
        "api_base": instance.api_base,
        "provider": "tikhub",
        "output_dir": str(instance.output_dir),
        "media_proxy": "local",
    }


@router.get("/config")
def get_config() -> dict[str, Any]:
    env = read_env_map()
    return {
        "api_base": env.get("TIKHUB_API_BASE", "https://api.tikhub.io"),
        "output_dir": env.get("DOUYIN_OUTPUT_DIR", "./data/runtime/douyin/downloads"),
        "cookie": env.get("TIKHUB_DOUYIN_WEB_COOKIE") or env.get("DOUYIN_WEB_COOKIE") or "",
        "has_cookie": bool(env.get("TIKHUB_DOUYIN_WEB_COOKIE") or env.get("DOUYIN_WEB_COOKIE")),
    }


@router.post("/config")
def save_config(payload: DouyinConfigPayload) -> dict[str, Any]:
    try:
        write_env_values(
            {
                "TIKHUB_API_BASE": payload.api_base,
                "DOUYIN_OUTPUT_DIR": payload.output_dir,
                "TIKHUB_DOUYIN_WEB_COOKIE": payload.cookie,
            }
        )
        return {"status": "ok", "config": get_config(), "upstream_cookie_sync": {"synced": False, "reason": "配置已保存；TikHub Cookie 会在收藏请求中随请求发送。"}}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/user-profile")
def user_profile(payload: UserProfileRequest) -> dict[str, Any]:
    try:
        instance = tikhub_adapter()
        sec_user_id = payload.sec_user_id or instance.get_sec_user_id(payload.user_url)
        return instance.get_user_profile(sec_user_id)
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/user-videos")
def user_videos(payload: UserVideosRequest) -> dict[str, Any]:
    try:
        instance = tikhub_adapter()
        sec_user_id = payload.sec_user_id or (instance.get_sec_user_id(payload.user_url) if payload.user_url else "")
        count = payload.max_items or payload.page_size
        return instance.get_user_videos(
            sec_user_id=sec_user_id,
            count=count,
            max_cursor=payload.max_cursor,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/work-detail")
def work_detail(payload: WorkDetailRequest) -> dict[str, Any]:
    try:
        return tikhub_adapter().get_work_detail(payload.work_url, region=payload.region)
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/video-comments")
def video_comments(payload: VideoCommentsRequest) -> dict[str, Any]:
    try:
        return tikhub_adapter().get_video_comments(
            aweme_id=payload.aweme_id,
            max_items=payload.max_items,
            page_size=payload.page_size,
            cursor=payload.cursor,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/video-comment-replies")
def video_comment_replies(payload: VideoCommentRepliesRequest) -> dict[str, Any]:
    try:
        return tikhub_adapter().get_video_comment_replies(
            item_id=payload.item_id,
            comment_id=payload.comment_id,
            max_items=payload.max_items,
            page_size=payload.page_size,
            cursor=payload.cursor,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/favorites/download")
def download_favorites(payload: FavoriteDownloadRequest) -> dict[str, Any]:
    try:
        return tikhub_adapter().download_favorite_videos(
            max_items=payload.max_items,
            page_size=payload.page_size,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/favorites/items")
def favorite_items(payload: FavoriteItemsRequest) -> dict[str, Any]:
    try:
        return tikhub_adapter().get_favorite_videos(
            max_items=payload.max_items,
            page_size=payload.page_size,
            max_cursor=payload.max_cursor,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.get("/media-proxy")
def media_proxy(
    request: Request,
    url: str = Query(...),
    referer: str | None = Query(default=None),
):
    return proxy_remote_media(
        url=url,
        referer=referer,
        request=request,
        namespace="douyin-media-proxy",
        default_referer="https://www.douyin.com/",
    )
