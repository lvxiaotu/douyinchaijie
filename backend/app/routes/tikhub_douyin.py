from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from integrations.tikhub_douyin_api import TikhubDouyinApiAdapter

router = APIRouter(prefix="/api/integrations/tikhub/douyin", tags=["tikhub-douyin"])


class TikhubUserSearchRequest(BaseModel):
    keyword: str = Field(..., description="Search keyword")
    offset: int = Field(default=0, ge=0)
    count: int = Field(default=20, ge=1, le=50)
    user_search_follower_count: str = Field(default="")
    user_search_profile_type: str = Field(default="")
    user_search_other_pref: str = Field(default="")


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
        offset=payload.offset,
        count=payload.count,
        user_search_follower_count=payload.user_search_follower_count,
        user_search_profile_type=payload.user_search_profile_type,
        user_search_other_pref=payload.user_search_other_pref,
    )


@router.post("/test")
def test_config(payload: TikhubConfigPayload) -> dict[str, Any]:
    instance = TikhubDouyinApiAdapter({"api_base": payload.api_base, "api_key_env": payload.api_key_env})
    errors = instance.validate_config({"api_base": payload.api_base, "api_key_env": payload.api_key_env})
    return {"ready": not errors, "errors": errors}
