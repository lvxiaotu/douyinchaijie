from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

from integrations.base import IntegrationAdapter, IntegrationManifest


DEFAULT_API_BASE = "https://api.tikhub.io"
DEFAULT_API_KEY_ENV = "TIKHUB_API_KEY"
DEFAULT_USER_SEARCH_PATH = "/api/v1/douyin/search/fetch_user_search_v5"
DEFAULT_USER_VIDEOS_PATH = "/api/v1/tiktok/app/v3/fetch_user_post_videos_v3"
DEFAULT_ONE_VIDEO_PATH = "/api/v1/tiktok/app/v3/fetch_one_video_v3"


@dataclass
class TikhubRequestSpec:
    path: str
    method: str
    params: dict[str, Any] | None = None
    json_body: dict[str, Any] | None = None


class TikhubDouyinApiAdapter(IntegrationAdapter):
    manifest = IntegrationManifest(
        id="tikhub-douyin-api",
        name="TikHub Douyin API",
        description="TikHub-based Douyin API adapter for future endpoints such as user search, profile, and work data.",
        repo_url="https://docs.tikhub.io/370212785e0",
        tags=["douyin", "tikhub", "api"],
        config_schema={
            "api_base": "TikHub API root URL, default https://api.tikhub.io",
            "api_key_env": "Environment variable holding the API key, default TIKHUB_API_KEY",
        },
    )

    def __init__(self, config: dict[str, Any] | None = None):
        load_dotenv()
        self.config = config or {}
        self.api_base = (self.config.get("api_base") or os.getenv("TIKHUB_API_BASE") or DEFAULT_API_BASE).rstrip("/")
        self.api_key_env = self.config.get("api_key_env") or DEFAULT_API_KEY_ENV
        self.api_key = self.config.get("api_key") or os.getenv(self.api_key_env, "")

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]:
        cfg = {**self.config, **(config or {})}
        api_base = (cfg.get("api_base") or os.getenv("TIKHUB_API_BASE") or self.api_base).rstrip("/")
        api_key_env = cfg.get("api_key_env") or self.api_key_env
        api_key = cfg.get("api_key") or os.getenv(api_key_env, "")
        errors = []
        if not api_key:
            errors.append(f"Missing env api key: {api_key_env}")
        try:
            response = requests.get(api_base, timeout=5)
            if response.status_code >= 500:
                errors.append(f"API service unhealthy: HTTP {response.status_code}")
        except requests.RequestException as exc:
            errors.append(f"API service not reachable: {api_base} ({exc})")
        return errors

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "user_search":
            return self.search_users(
                keyword=payload["keyword"],
                page=int(payload.get("page", 1)),
                userType=payload.get("userType", ""),
                douyin_user_fans=payload.get("douyin_user_fans", ""),
            )
        if action == "user_videos":
            return self.get_user_videos(
                sec_user_id=payload.get("sec_user_id"),
                unique_id=payload.get("unique_id"),
                max_cursor=int(payload.get("max_cursor", 0)),
                count=int(payload.get("count", 20)),
                sort_type=int(payload.get("sort_type", 0)),
            )
        if action == "one_video":
            return self.get_one_video(payload["aweme_id"], region=payload.get("region", "US"))
        raise ValueError(f"Unsupported TikHub action: {action}")

    def search_users(
        self,
        keyword: str,
        page: int = 1,
        userType: str = "",
        douyin_user_fans: str = "",
    ) -> dict[str, Any]:
        spec = TikhubRequestSpec(
            path=DEFAULT_USER_SEARCH_PATH,
            method="POST",
            json_body={
                "keyword": keyword,
                "page": page,
                "userType": userType,
                "douyin_user_fans": douyin_user_fans,
            },
        )
        data = self._request_json(spec)
        return {
            "status": "ok",
            "source": self.manifest.id,
            "keyword": keyword,
            "page": page,
            "request": {k: v for k, v in (spec.json_body or {}).items() if v not in [None, ""]},
            "raw": data,
            "items": self._extract_items(data),
            "pagination": self._extract_user_search_pagination(data),
            "normalized": self._normalize_response(data),
        }

    def get_user_videos(self, sec_user_id: str | None = None, unique_id: str | None = None, max_cursor: int = 0, count: int = 20, sort_type: int = 0) -> dict[str, Any]:
        spec = TikhubRequestSpec(
            path=DEFAULT_USER_VIDEOS_PATH,
            method="GET",
            params={
                "sec_user_id": sec_user_id or "",
                "unique_id": unique_id or "",
                "max_cursor": max_cursor,
                "count": count,
                "sort_type": sort_type,
            },
        )
        data = self._request_json(spec)
        return {
            "status": "ok",
            "source": self.manifest.id,
            "request": {k: v for k, v in spec.params.items() if v not in [None, ""]},
            "raw": data,
            "items": self._extract_video_items(data),
            "pagination": self._extract_video_pagination(data),
            "normalized": self._normalize_video_response(data),
        }

    def get_one_video(self, aweme_id: str, region: str = "US") -> dict[str, Any]:
        spec = TikhubRequestSpec(path=DEFAULT_ONE_VIDEO_PATH, method="GET", params={"aweme_id": aweme_id, "region": region})
        data = self._request_json(spec)
        return {
            "status": "ok",
            "source": self.manifest.id,
            "request": spec.params,
            "raw": data,
            "video": self._extract_one_video(data),
            "download_urls": self._extract_download_urls(data),
        }

    def _request_json(self, spec: TikhubRequestSpec) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        response = requests.request(spec.method, f"{self.api_base}{spec.path}", params=spec.params, json=spec.json_body, headers=headers, timeout=60)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"TikHub API failed: HTTP {response.status_code}, body={response.text[:1200]}") from exc
        return response.json()

    def _normalize_response(self, data: dict[str, Any]) -> dict[str, Any]:
        root = data.get("data") if isinstance(data.get("data"), dict) else {}
        return {
            "code": data.get("code"),
            "message": data.get("message"),
            "message_zh": data.get("message_zh"),
            "request_id": data.get("request_id"),
            "cursor": root.get("cursor"),
            "has_more": root.get("has_more"),
            "search_id": root.get("extra", {}).get("logid") if isinstance(root.get("extra"), dict) else None,
            "impr_id": root.get("log_pb", {}).get("impr_id") if isinstance(root.get("log_pb"), dict) else None,
        }

    def _extract_user_search_pagination(self, data: dict[str, Any]) -> dict[str, Any]:
        root = data.get("data") if isinstance(data.get("data"), dict) else {}
        return {"page": root.get("page") or data.get("page"), "has_more": root.get("has_more"), "cursor": root.get("cursor")}

    def _normalize_video_response(self, data: dict[str, Any]) -> dict[str, Any]:
        root = data.get("data") if isinstance(data.get("data"), dict) else {}
        return {"max_cursor": root.get("max_cursor"), "has_more": root.get("has_more"), "cursor": root.get("cursor")}

    def _extract_items(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        root = data.get("data") if isinstance(data.get("data"), dict) else data
        user_list = None
        if isinstance(root, dict):
            user_list = root.get("user_list")
            if not isinstance(user_list, list):
                for key in ("users", "items", "list", "user_list_info", "search_user_list"):
                    value = root.get(key)
                    if isinstance(value, list):
                        user_list = value
                        break
        elif isinstance(root, list):
            user_list = root
        if not isinstance(user_list, list):
            return []
        return [self._normalize_user(item) for item in user_list if isinstance(item, dict)]

    def _extract_video_items(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        root = data.get("data") if isinstance(data.get("data"), dict) else data
        aweme_list = None
        if isinstance(root, dict):
            for key in ("aweme_list", "items", "videos", "list"):
                value = root.get(key)
                if isinstance(value, list):
                    aweme_list = value
                    break
            if aweme_list is None and isinstance(root.get("aweme_list"), dict):
                maybe = root["aweme_list"].get("aweme_list")
                if isinstance(maybe, list):
                    aweme_list = maybe
        elif isinstance(root, list):
            aweme_list = root
        if not isinstance(aweme_list, list):
            return []
        return [self._normalize_video(item) for item in aweme_list if isinstance(item, dict)]

    def _extract_one_video(self, data: dict[str, Any]) -> dict[str, Any]:
        root = data.get("data") if isinstance(data.get("data"), dict) else data
        aweme = root.get("aweme_detail") if isinstance(root, dict) else None
        if not isinstance(aweme, dict) and isinstance(root, dict):
            aweme = root.get("aweme") if isinstance(root.get("aweme"), dict) else root
        if not isinstance(aweme, dict):
            return {}
        return self._normalize_video(aweme)

    def _extract_download_urls(self, data: dict[str, Any]) -> dict[str, Any]:
        video = self._extract_one_video(data)
        raw = video.get("raw") if isinstance(video.get("raw"), dict) else {}
        video_data = raw.get("video") if isinstance(raw.get("video"), dict) else {}
        return {"play_addr": self._first_url(video_data.get("play_addr")), "play_addr_h264": self._first_url(video_data.get("play_addr_h264")), "play_addr_bytevc1": self._first_url(video_data.get("play_addr_bytevc1")), "download_addr": self._first_url(video_data.get("download_addr"))}

    def _normalize_user(self, item: dict[str, Any]) -> dict[str, Any]:
        return {"sec_uid": item.get("sec_uid") or item.get("secUid") or item.get("sec_user_id"), "uid": item.get("uid") or item.get("user_id") or item.get("id"), "unique_id": item.get("unique_id") or item.get("uniqueId") or item.get("short_id"), "nickname": item.get("nickname") or item.get("display_name") or item.get("nickname_display"), "signature": item.get("signature") or item.get("desc"), "avatar": self._first_avatar_url(item), "follower_count": item.get("follower_count") or item.get("followers") or item.get("followerCount"), "verified": item.get("verified") or item.get("is_verified") or item.get("isVerified"), "raw": item}

    def _normalize_video(self, item: dict[str, Any]) -> dict[str, Any]:
        return {"aweme_id": item.get("aweme_id") or item.get("id"), "desc": item.get("desc") or item.get("title"), "create_time": item.get("create_time"), "author": self._normalize_user(item.get("author", {})) if isinstance(item.get("author"), dict) else None, "video": item.get("video"), "statistics": item.get("statistics") or item.get("stats"), "raw": item}

    def _first_avatar_url(self, item: dict[str, Any]) -> Any:
        avatar = item.get("avatar_thumb") or item.get("avatar_large") or item.get("avatar")
        if isinstance(avatar, dict):
            for key in ("url_list", "url"):
                value = avatar.get(key)
                if isinstance(value, list) and value:
                    return value[0]
                if isinstance(value, str) and value:
                    return value
        if isinstance(avatar, list) and avatar:
            return avatar[0]
        if isinstance(avatar, str):
            return avatar
        return None

    def _first_url(self, value: Any) -> Any:
        if isinstance(value, dict):
            for key in ("url_list", "url"):
                candidate = value.get(key)
                if isinstance(candidate, list) and candidate:
                    return candidate[0]
                if isinstance(candidate, str) and candidate:
                    return candidate
        if isinstance(value, list) and value:
            return value[0]
        if isinstance(value, str):
            return value
        return None

    def _extract_pagination(self, data: dict[str, Any]) -> dict[str, Any]:
        root = data.get("data") if isinstance(data.get("data"), dict) else {}
        extra = root.get("extra") if isinstance(root.get("extra"), dict) else {}
        log_pb = root.get("log_pb") if isinstance(root.get("log_pb"), dict) else {}
        return {"cursor": root.get("cursor"), "has_more": root.get("has_more"), "search_id": extra.get("logid") or log_pb.get("impr_id")}

    def _extract_video_pagination(self, data: dict[str, Any]) -> dict[str, Any]:
        root = data.get("data") if isinstance(data.get("data"), dict) else {}
        return {"max_cursor": root.get("max_cursor"), "has_more": root.get("has_more")}
