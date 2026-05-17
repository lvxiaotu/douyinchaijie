from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from integrations.tikhub_douyin_api import TikhubDouyinApiAdapter

router = APIRouter(prefix="/api/integrations/tikhub/douyin", tags=["tikhub-douyin"])


class TikhubUserSearchRequest(BaseModel):
    keyword: str = Field(..., description="Search keyword")
    page: int = Field(default=1, ge=1)
    cursor: int | None = Field(default=None, ge=0)
    search_id: str = Field(default="")
    offset: int = Field(default=0, ge=0)
    count: int = Field(default=20, ge=1, le=50)
    user_type: str = Field(default="")
    douyin_user_type: str = Field(default="")
    follower_filter: str = Field(default="")
    user_search_follower_count: str = Field(default="")
    user_search_profile_type: str = Field(default="")
    user_search_other_pref: str = Field(default="")


class TikhubUserVideosRequest(BaseModel):
    sec_user_id: str | None = Field(default=None)
    unique_id: str | None = Field(default=None)
    max_cursor: int = Field(default=0, ge=0)
    count: int = Field(default=20, ge=1, le=50)
    sort_type: int = Field(default=0)


class TikhubOneVideoRequest(BaseModel):
    aweme_id: str
    region: str = Field(default="US")


class TikhubConfigPayload(BaseModel):
    api_base: str = Field(default="https://api.tikhub.io")
    api_key_env: str = Field(default="TIKHUB_API_KEY")



def adapter() -> TikhubDouyinApiAdapter:
    return TikhubDouyinApiAdapter()


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
    }


@router.post("/user-search")
def user_search(payload: TikhubUserSearchRequest) -> dict[str, Any]:
    return adapter().search_users(
        keyword=payload.keyword,
        page=payload.page,
        cursor=payload.cursor,
        search_id=payload.search_id,
        offset=payload.offset,
        count=payload.count,
        user_type=payload.user_type,
        douyin_user_type=payload.douyin_user_type,
        follower_filter=payload.follower_filter,
        user_search_follower_count=payload.user_search_follower_count,
        user_search_profile_type=payload.user_search_profile_type,
        user_search_other_pref=payload.user_search_other_pref,
    )


@router.post("/user-videos")
def user_videos(payload: TikhubUserVideosRequest) -> dict[str, Any]:
    return adapter().get_user_videos(
        sec_user_id=payload.sec_user_id,
        unique_id=payload.unique_id,
        max_cursor=payload.max_cursor,
        count=payload.count,
        sort_type=payload.sort_type,
    )


@router.post("/one-video")
def one_video(payload: TikhubOneVideoRequest) -> dict[str, Any]:
    return adapter().get_one_video(payload.aweme_id, region=payload.region)


@router.post("/test")
def test_config(payload: TikhubConfigPayload) -> dict[str, Any]:
    instance = TikhubDouyinApiAdapter({"api_base": payload.api_base, "api_key_env": payload.api_key_env})
    errors = instance.validate_config({"api_base": payload.api_base, "api_key_env": payload.api_key_env})
    return {"ready": not errors, "errors": errors}
