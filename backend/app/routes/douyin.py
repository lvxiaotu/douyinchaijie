import logging
import os
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import dotenv_values

from backend.app.error_log_store import write_error_log
from integrations.douyin_download_api.adapter import DouyinDownloadApiAdapter

router = APIRouter(prefix="/api/integrations/douyin", tags=["douyin"])
logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT / ".env"


class UserProfileRequest(BaseModel):
    user_url: str = Field(..., description="Douyin user page URL")


class UserVideosRequest(BaseModel):
    user_url: str | None = Field(default=None, description="Douyin user page URL")
    sec_user_id: str | None = Field(default=None, description="Douyin sec_user_id")
    max_items: int | None = Field(default=None, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=50)
    max_cursor: int = Field(default=0, ge=0)


class WorkDetailRequest(BaseModel):
    work_url: str = Field(..., description="Douyin video/work URL")


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
    api_base: str = Field(default="http://127.0.0.1:8123")
    output_dir: str = Field(default="./data/runtime/douyin/downloads")
    cookie: str = Field(default="")


def adapter() -> DouyinDownloadApiAdapter:
    return DouyinDownloadApiAdapter()


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
    if _is_upstream_unavailable(exc):
        logger.warning("Douyin integration upstream unavailable: %s", exc)
        return HTTPException(
            status_code=503,
            detail={
                "error_type": type(exc).__name__,
                "message": "Douyin_TikTok_Download_API 未启动或无法连接到 127.0.0.1:8123",
                "hint": "请先启动本地 Douyin_TikTok_Download_API 服务，再重试该接口。",
            },
        )
    logger.exception("Douyin integration failed")
    return HTTPException(
        status_code=500,
        detail={
            "error_type": type(exc).__name__,
            "message": str(exc),
            "hint": "Check DY_COOKIES and whether Douyin_TikTok_Download_API is running.",
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


def _log_douyin_upstream_error(
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
        namespace="douyin-download-api",
        path=path,
        method=method,
        request=request,
        exc=exc,
        api_base=api_base,
        status_code=status_code,
        response_text=response_text,
        extra=extra,
    )


def sync_upstream_cookie(api_base: str, cookie: str) -> dict[str, Any]:
    if not cookie:
        return {"synced": False, "reason": "empty cookie"}
    request_payload = {"json_body": {"service": "douyin", "cookie": cookie}}
    target_path = "/api/hybrid/update_cookie"
    try:
        response = requests.post(
            f"{api_base.rstrip('/')}{target_path}",
            json=request_payload["json_body"],
            timeout=10,
        )
        if not response.ok:
            _log_douyin_upstream_error(
                path=target_path,
                method="POST",
                request=request_payload,
                exc=RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}"),
                api_base=api_base,
                status_code=response.status_code,
                response_text=response.text[:4000],
                extra={"phase": "sync_upstream_cookie_http_error"},
            )
        return {"synced": response.ok, "status_code": response.status_code, "body": response.text[:500]}
    except Exception as exc:
        _log_douyin_upstream_error(
            path=target_path,
            method="POST",
            request=request_payload,
            exc=exc,
            api_base=api_base,
            extra={"phase": "sync_upstream_cookie_request_exception"},
        )
        return {"synced": False, "reason": str(exc)}


@router.get("/status")
def status() -> dict[str, Any]:
    instance = adapter()
    errors = instance.validate_config()
    return {
        "id": instance.manifest.id,
        "name": instance.manifest.name,
        "repo_url": instance.manifest.repo_url,
        "ready": not errors,
        "errors": errors,
        "api_base": instance.api_base,
        "output_dir": str(instance.output_dir),
    }


@router.get("/config")
def get_config() -> dict[str, Any]:
    env = read_env_map()
    return {
        "api_base": env.get("DOUYIN_DOWNLOAD_API_BASE", "http://127.0.0.1:8123"),
        "output_dir": env.get("DOUYIN_OUTPUT_DIR", "./data/runtime/douyin/downloads"),
        "cookie": env.get("DY_COOKIES", ""),
        "has_cookie": bool(env.get("DY_COOKIES")),
    }


@router.post("/config")
def save_config(payload: DouyinConfigPayload) -> dict[str, Any]:
    try:
        write_env_values(
            {
                "DOUYIN_DOWNLOAD_API_BASE": payload.api_base,
                "DOUYIN_OUTPUT_DIR": payload.output_dir,
                "DY_COOKIES": payload.cookie,
            }
        )
        sync_result = sync_upstream_cookie(payload.api_base, payload.cookie)
        return {"status": "ok", "config": get_config(), "upstream_cookie_sync": sync_result}
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/user-profile")
def user_profile(payload: UserProfileRequest) -> dict[str, Any]:
    try:
        return adapter().get_user_profile(payload.user_url)
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/user-videos")
def user_videos(payload: UserVideosRequest) -> dict[str, Any]:
    try:
        return adapter().get_user_videos(
            user_url=payload.user_url,
            sec_user_id=payload.sec_user_id,
            max_items=payload.max_items,
            page_size=payload.page_size,
            max_cursor=payload.max_cursor,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/work-detail")
def work_detail(payload: WorkDetailRequest) -> dict[str, Any]:
    try:
        return adapter().get_work_detail(payload.work_url)
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/video-comments")
def video_comments(payload: VideoCommentsRequest) -> dict[str, Any]:
    try:
        return adapter().get_video_comments(
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
        return adapter().get_video_comment_replies(
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
        return adapter().download_favorite_videos(
            max_items=payload.max_items,
            page_size=payload.page_size,
            max_cursor=payload.max_cursor,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/favorites/items")
def favorite_items(payload: FavoriteItemsRequest) -> dict[str, Any]:
    try:
        return adapter().get_favorite_videos(
            max_items=payload.max_items,
            page_size=payload.page_size,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.get("/media-proxy")
def media_proxy(url: str = Query(...), referer: str | None = Query(default=None)):
    try:
        target_url = unquote(url)
        parsed = urlparse(target_url)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Referer": referer or "https://www.douyin.com/",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Range": "bytes=0-",
        }
        response = requests.get(target_url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        media_type = response.headers.get("content-type", "video/mp4")
        proxy_headers = {
            "Accept-Ranges": response.headers.get("accept-ranges", "bytes"),
            "Cache-Control": "private, max-age=300",
        }
        if response.headers.get("content-length"):
            proxy_headers["Content-Length"] = response.headers["content-length"]
        return StreamingResponse(
            response.iter_content(chunk_size=1024 * 512),
            media_type=media_type,
            headers=proxy_headers,
        )
    except Exception as exc:
        _log_douyin_upstream_error(
            path=parsed.path if "parsed" in locals() and parsed.path else "/media-proxy",
            method="GET",
            request={
                "params": {
                    "url": target_url if "target_url" in locals() else url,
                    "referer": referer or "",
                },
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    "Referer": referer or "https://www.douyin.com/",
                    "Accept": "*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Range": "bytes=0-",
                },
            },
            exc=exc,
            api_base=parsed.netloc if "parsed" in locals() else "",
            extra={"phase": "media_proxy_request_exception"},
        )
        raise integration_error(exc) from exc
