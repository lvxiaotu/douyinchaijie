from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.routes.douyin_provider import (
    FavoriteDownloadRequest,
    FavoriteItemsRequest,
    OneVideoRequest,
    UserProfileRequest,
    UserVideosRequest,
    VideoCommentRepliesRequest,
    VideoCommentsRequest,
    WorkDetailRequest,
    integration_error,
)
from integrations.douyin_legacy_tikhub import LegacyTikhubDouyinAdapter


router = APIRouter(prefix="/api/integrations/douyin-legacy-tikhub", tags=["douyin-legacy-tikhub"])


class UserSearchRequest(BaseModel):
    keyword: str
    page: int = Field(default=1, ge=1)
    cursor: int | None = Field(default=None, ge=0)
    count: int = Field(default=20, ge=1, le=50)
    user_type: str = Field(default="")
    follower_filter: str = Field(default="")
    search_id: str = Field(default="")
    douyin_user_type: str = Field(default="")
    enrich_profiles: bool = Field(default=False)


def legacy_adapter() -> LegacyTikhubDouyinAdapter:
    return LegacyTikhubDouyinAdapter()


@router.get("/status")
def status() -> dict[str, Any]:
    instance = legacy_adapter()
    errors = instance.validate_config()
    return {
        "id": instance.manifest.id,
        "name": instance.manifest.name,
        "repo_url": instance.manifest.repo_url,
        "ready": not errors,
        "errors": errors,
        "provider": "douyin-legacy-tikhub",
        "api_base": instance.api_base,
        "output_dir": str(instance.output_dir),
    }


@router.post("/user-search")
def user_search(payload: UserSearchRequest) -> dict[str, Any]:
    try:
        return legacy_adapter().search_users(
            keyword=payload.keyword,
            page=payload.page,
            cursor=payload.cursor,
            count=payload.count,
            user_type=payload.user_type,
            follower_filter=payload.follower_filter,
            search_id=payload.search_id,
            douyin_user_type=payload.douyin_user_type,
            enrich_profiles=payload.enrich_profiles,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/user-profile")
def user_profile(payload: UserProfileRequest) -> dict[str, Any]:
    try:
        provider = legacy_adapter()
        sec_user_id = payload.sec_user_id or provider.get_sec_user_id(payload.user_url or "")
        return provider.get_user_profile(sec_user_id)
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/user-videos")
def user_videos(payload: UserVideosRequest) -> dict[str, Any]:
    try:
        provider = legacy_adapter()
        sec_user_id = payload.sec_user_id or (provider.get_sec_user_id(payload.user_url or "") if payload.user_url else "")
        count = payload.max_items or payload.page_size
        return provider.get_user_videos(sec_user_id=sec_user_id, count=count, max_cursor=payload.max_cursor)
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/work-detail")
def work_detail(payload: WorkDetailRequest) -> dict[str, Any]:
    try:
        return legacy_adapter().get_work_detail(payload.work_url, region=payload.region)
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/one-video")
def one_video(payload: OneVideoRequest) -> dict[str, Any]:
    try:
        return legacy_adapter().get_one_video(payload.aweme_id, region=payload.region)
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/video-comments")
def video_comments(payload: VideoCommentsRequest) -> dict[str, Any]:
    try:
        return legacy_adapter().get_video_comments(
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
        return legacy_adapter().get_video_comment_replies(
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
        return legacy_adapter().get_favorite_videos(
            max_items=payload.max_items,
            page_size=payload.page_size,
            max_cursor=payload.max_cursor,
        )
    except Exception as exc:
        raise integration_error(exc) from exc


@router.post("/favorites/download")
def download_favorites(payload: FavoriteDownloadRequest) -> dict[str, Any]:
    try:
        return legacy_adapter().download_favorite_videos(max_items=payload.max_items, page_size=payload.page_size)
    except Exception as exc:
        raise integration_error(exc) from exc
