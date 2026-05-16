from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.tiktok_target_store import (
    add_user_to_target_set,
    create_target_set,
    create_target_video,
    get_target_set,
    get_target_user,
    get_target_video,
    init_db,
    list_target_users,
    upsert_target_user,
)
from integrations.tikhub_douyin_api import TikhubDouyinApiAdapter

router = APIRouter(prefix="/api/tools/douyin-target", tags=["douyin-target"])


class TargetSearchRequest(BaseModel):
    keyword: str
    minFollowers: int | None = None
    maxFollowers: int | None = None
    minLikes: int | None = None
    recentOnly: bool = True


class TargetUserCreate(BaseModel):
    keyword: str = Field(default="")
    sec_user_id: str
    unique_id: str = Field(default="")
    nickname: str = Field(default="")
    follower_count: int | None = None
    like_count: int | None = None
    recent_update_at: int | None = None
    verified: bool = False
    status: str = Field(default="candidate")
    source_json: dict[str, Any] = Field(default_factory=dict)


class TargetSetCreate(BaseModel):
    name: str
    note: str = Field(default="")


class AddUserToSet(BaseModel):
    set_id: str
    user_id: str


class TargetVideoCreate(BaseModel):
    user_id: str
    aweme_id: str
    desc: str = Field(default="")
    cover_url: str = Field(default="")
    play_url: str = Field(default="")
    download_url: str = Field(default="")
    selected: bool = False
    source_json: dict[str, Any] = Field(default_factory=dict)


class UserVideoQuery(BaseModel):
    sec_user_id: str | None = None
    unique_id: str | None = None
    max_cursor: int = 0
    count: int = 20
    sort_type: int = 0


@router.on_event("startup")
def _startup() -> None:
    init_db()


@router.post("/search")
def search(payload: TargetSearchRequest) -> dict[str, Any]:
    result = TikhubDouyinApiAdapter().search_users(keyword=payload.keyword, page=1)
    items = []
    for item in result.get("items", []):
        follower_count = int(item.get("follower_count") or 0)
        like_count = int(item.get("raw", {}).get("total_favorited") or item.get("like_count") or 0)
        if payload.minFollowers is not None and follower_count < payload.minFollowers:
            continue
        if payload.maxFollowers is not None and follower_count > payload.maxFollowers:
            continue
        if payload.minLikes is not None and like_count < payload.minLikes:
            continue
        if payload.recentOnly and not item.get("raw", {}).get("create_time") and not item.get("raw", {}).get("last_post_time"):
            continue
        item["like_count"] = like_count
        items.append(item)
    result["items"] = items
    result["count"] = len(items)
    return result


@router.get("/users")
def users(status: str | None = None) -> list[dict[str, Any]]:
    return list_target_users(status=status)


@router.post("/users")
def create_user(payload: TargetUserCreate) -> dict[str, Any]:
    user_id = payload.sec_user_id or payload.unique_id or str(uuid4())
    return upsert_target_user(
        user_id,
        {
            "keyword": payload.keyword,
            "sec_user_id": payload.sec_user_id,
            "unique_id": payload.unique_id,
            "nickname": payload.nickname,
            "follower_count": payload.follower_count,
            "like_count": payload.like_count,
            "recent_update_at": payload.recent_update_at,
            "verified": payload.verified,
            "status": payload.status,
            "source_json": payload.source_json,
        },
    )


@router.post("/sets")
def create_set(payload: TargetSetCreate) -> dict[str, Any]:
    set_id = str(uuid4())
    return create_target_set(set_id, payload.name, payload.note)


@router.post("/sets/add-user")
def add_set_user(payload: AddUserToSet) -> dict[str, Any]:
    if not get_target_set(payload.set_id):
        raise HTTPException(status_code=404, detail="Target set not found")
    if not get_target_user(payload.user_id):
        raise HTTPException(status_code=404, detail="Target user not found")
    return add_user_to_target_set(payload.set_id, payload.user_id)


@router.post("/users/videos")
def user_videos(payload: UserVideoQuery) -> dict[str, Any]:
    return TikhubDouyinApiAdapter().get_user_videos(
        sec_user_id=payload.sec_user_id,
        unique_id=payload.unique_id,
        max_cursor=payload.max_cursor,
        count=payload.count,
        sort_type=payload.sort_type,
    )


@router.post("/videos")
def create_video(payload: TargetVideoCreate) -> dict[str, Any]:
    video_id = payload.aweme_id or str(uuid4())
    return create_target_video(
        video_id,
        payload.user_id,
        {
            "aweme_id": payload.aweme_id,
            "desc": payload.desc,
            "cover_url": payload.cover_url,
            "play_url": payload.play_url,
            "download_url": payload.download_url,
            "selected": payload.selected,
            "source_json": payload.source_json,
        },
    )
