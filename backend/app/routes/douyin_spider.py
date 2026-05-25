from __future__ import annotations

import logging
from typing import Any

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from integrations.douyin_spider_provider import DouyinSpiderAdapter
from integrations.douyin_spider_provider.adapter import DouyinSpiderApiError


router = APIRouter(prefix="/api/integrations/douyin-spider", tags=["douyin-spider"])
logger = logging.getLogger(__name__)


class UserProfileRequest(BaseModel):
    user_url: str | None = Field(default=None, description="Douyin user page URL")
    sec_user_id: str | None = Field(default=None, description="Douyin sec_user_id")


class UserVideosRequest(BaseModel):
    user_url: str | None = Field(default=None, description="Douyin user page URL")
    sec_user_id: str | None = Field(default=None, description="Douyin sec_user_id")
    max_items: int | None = Field(default=None, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=50)
    max_cursor: int = Field(default=0, ge=0)


class WorkDetailRequest(BaseModel):
    work_url: str = Field(..., description="Douyin video/work URL")
    region: str = Field(default="US", description="Reserved for compatibility with TikHub routes")


class OneVideoRequest(BaseModel):
    aweme_id: str = Field(..., description="Douyin aweme_id")
    region: str = Field(default="US", description="Reserved for compatibility with TikHub routes")


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
    max_items: int = Field(default=18, ge=1, le=300)
    page_size: int = Field(default=18, ge=1, le=50)


class FavoriteItemsRequest(BaseModel):
    max_items: int | None = Field(default=None, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=50)
    max_cursor: int = Field(default=0, ge=0)


def spider_adapter() -> DouyinSpiderAdapter:
    return DouyinSpiderAdapter()


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
    if isinstance(exc, DouyinSpiderApiError):
        logger.warning("Douyin_Spider integration failed: %s", exc)
        return HTTPException(
            status_code=502,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
                "hint": "Check DOUYIN_SPIDER_VENDOR_PATH, npm dependencies, DY_COOKIES, and Douyin request parameters.",
                "upstream": exc.to_dict(),
            },
        )
    if _is_upstream_unavailable(exc):
        logger.warning("Douyin_Spider upstream unavailable: %s", exc)
        return HTTPException(
            status_code=503,
            detail={
                "error_type": type(exc).__name__,
                "message": "Douyin_Spider upstream request is unavailable or timed out.",
                "hint": "Check network, cookie validity, and Douyin_Spider runtime dependencies.",
            },
        )
    logger.exception("Douyin_Spider integration failed")
    return HTTPException(
        status_code=500,
        detail={
            "error_type": type(exc).__name__,
            "message": str(exc),
            "hint": "Check DOUYIN_SPIDER_VENDOR_PATH, DY_COOKIES, and request parameters.",
        },
    )


@router.get("/status")
def status() -> dict[str, Any]:
    return spider_adapter().status()


@router.post("/user-profile")
def user_profile(payload: UserProfileRequest) -> dict[str, Any]:
    try:
        instance = spider_adapter()
        sec_user_id = payload.sec_user_id or instance.get_sec_user_id(payload.user_url or "")
        return instance.get_user_profile(sec_user_id)
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/user-videos")
def user_videos(payload: UserVideosRequest) -> dict[str, Any]:
    try:
        instance = spider_adapter()
        sec_user_id = payload.sec_user_id or (instance.get_sec_user_id(payload.user_url or "") if payload.user_url else "")
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
        return spider_adapter().get_work_detail(payload.work_url, region=payload.region)
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/one-video")
def one_video(payload: OneVideoRequest) -> dict[str, Any]:
    try:
        return spider_adapter().get_one_video(payload.aweme_id, region=payload.region)
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/video-comments")
def video_comments(payload: VideoCommentsRequest) -> dict[str, Any]:
    try:
        return spider_adapter().get_video_comments(
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
        return spider_adapter().get_video_comment_replies(
            item_id=payload.item_id,
            comment_id=payload.comment_id,
            max_items=payload.max_items,
            page_size=payload.page_size,
            cursor=payload.cursor,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/favorites/items")
def favorite_items(payload: FavoriteItemsRequest) -> dict[str, Any]:
    try:
        return spider_adapter().get_favorite_videos(
            max_items=payload.max_items,
            page_size=payload.page_size,
            max_cursor=payload.max_cursor,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/favorites/download")
def download_favorites(payload: FavoriteDownloadRequest) -> dict[str, Any]:
    try:
        return spider_adapter().download_favorite_videos(
            max_items=payload.max_items,
            page_size=payload.page_size,
        )
    except Exception as exc:
        raise integration_error(exc) from exc

