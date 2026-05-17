from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

from integrations.base import IntegrationAdapter, IntegrationManifest


DEFAULT_API_BASE = "https://api.tikhub.io"
DEFAULT_API_KEY_ENV = "TIKHUB_API_KEY"
DEFAULT_USER_SEARCH_PATH = "/api/v1/douyin/search/fetch_user_search"
DEFAULT_USER_PROFILE_PATH = "/api/v1/douyin/web/handler_user_profile"
DEFAULT_USER_VIDEOS_PATH = "/api/v1/douyin/web/fetch_user_post_videos"
DEFAULT_ONE_VIDEO_PATH = "/api/v1/douyin/app/v3/fetch_one_video_v3"


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
        repo_url="https://docs.tikhub.io/186826143e0",
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
        self.douyin_web_cookie = self.config.get("douyin_web_cookie") or os.getenv("TIKHUB_DOUYIN_WEB_COOKIE") or os.getenv("DOUYIN_WEB_COOKIE") or ""

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
            cursor = payload.get("cursor")
            cursor = int(cursor) if cursor not in [None, ""] else None
            return self.search_users(
                keyword=payload["keyword"],
                page=int(payload.get("page", 1)),
                count=int(payload.get("count", 20)),
                user_type=payload.get("user_type") or payload.get("userType", ""),
                follower_filter=payload.get("follower_filter") or payload.get("douyin_user_fans", ""),
                cursor=cursor,
                search_id=payload.get("search_id") or "",
                douyin_user_type=payload.get("douyin_user_type") or "",
            )
        if action == "user_videos":
            return self.get_user_videos(
                sec_user_id=payload.get("sec_user_id"),
                unique_id=payload.get("unique_id"),
                max_cursor=int(payload.get("max_cursor", 0)),
                count=int(payload.get("count", 20)),
                filter_type=int(payload.get("filter_type", payload.get("sort_type", 0))),
            )
        if action == "one_video":
            return self.get_one_video(payload["aweme_id"], region=payload.get("region", "US"))
        raise ValueError(f"Unsupported TikHub action: {action}")

    def search_users(
        self,
        keyword: str,
        page: int = 1,
        count: int = 20,
        user_type: str = "",
        follower_filter: str = "",
        offset: int | None = None,
        user_search_follower_count: str = "",
        user_search_profile_type: str = "",
        user_search_other_pref: str = "",
        cursor: int | None = None,
        search_id: str = "",
        douyin_user_type: str = "",
        enrich_profiles: bool = True,
    ) -> dict[str, Any]:
        resolved_page = page if page > 0 else 1
        resolved_cursor = cursor if cursor is not None else 0
        if offset is not None and offset > 0 and cursor is None and page <= 1:
            resolved_cursor = offset
        if resolved_cursor == 0 and resolved_page > 1 and cursor is None:
            resolved_cursor = (resolved_page - 1) * max(count, 1)
        resolved_user_type = user_type or user_search_profile_type or douyin_user_type
        resolved_follower_filter = follower_filter or user_search_follower_count
        spec = TikhubRequestSpec(
            path=DEFAULT_USER_SEARCH_PATH,
            method="POST",
            json_body={
                "keyword": keyword,
                "page": resolved_page,
                "cursor": resolved_cursor,
                "search_id": search_id,
                "userType": resolved_user_type,
                "douyin_user_fans": resolved_follower_filter,
                "douyin_user_type": resolved_user_type,
                "count": count,
            },
        )
        if user_search_other_pref:
            spec.json_body["user_search_other_pref"] = user_search_other_pref
        data = self._request_json(spec)
        items = self._extract_items(data)
        if enrich_profiles:
            items = self._enrich_users(items[:count] if count else items)
        return {
            "status": "ok",
            "source": self.manifest.id,
            "keyword": keyword,
            "page": resolved_page,
            "cursor": resolved_cursor,
            "search_id": search_id,
            "count": count,
            "request": {k: v for k, v in (spec.json_body or {}).items() if v not in [None, ""]},
            "raw": data,
            "items": items[:count] if count else items,
            "pagination": self._extract_user_search_pagination(data),
            "normalized": self._normalize_response(data),
        }

    def get_user_profile(self, sec_user_id: str) -> dict[str, Any]:
        spec = TikhubRequestSpec(
            path=DEFAULT_USER_PROFILE_PATH,
            method="GET",
            params={"sec_user_id": sec_user_id},
        )
        data = self._request_json(spec)
        user = self._extract_profile_user(data)
        return {
            "status": "ok",
            "source": self.manifest.id,
            "request": spec.params,
            "raw": data,
            "user": self._normalize_user(user) if user else {},
        }

    def get_user_videos(
        self,
        sec_user_id: str | None = None,
        unique_id: str | None = None,
        max_cursor: int = 0,
        count: int = 20,
        sort_type: int = 0,
        filter_type: int | None = None,
    ) -> dict[str, Any]:
        sec = str(sec_user_id or "").strip()
        if not sec:
            raise ValueError("Douyin Web 作品接口需要 sec_user_id，当前账号缺少可用的 sec_user_id。")

        target_count = max(1, min(int(count or 20), 50))
        page_size = min(target_count, 20)
        current_cursor = int(max_cursor or 0)
        resolved_filter_type = int(filter_type if filter_type is not None else sort_type or 0)
        raw_pages: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        last_spec: TikhubRequestSpec | None = None
        pagination: dict[str, Any] = {}

        while len(items) < target_count:
            current_page_size = min(page_size, target_count - len(items))
            spec = TikhubRequestSpec(
                path=DEFAULT_USER_VIDEOS_PATH,
                method="GET",
                params=self._user_videos_params(
                    sec_user_id=sec,
                    max_cursor=current_cursor,
                    count=current_page_size,
                    filter_type=resolved_filter_type,
                ),
            )
            last_spec = spec
            data = self._request_json(spec)
            raw_pages.append(data)
            page_items = self._extract_video_items(data)
            items.extend(page_items)
            pagination = self._extract_video_pagination(data)

            next_cursor = pagination.get("max_cursor")
            has_more = pagination.get("has_more")
            if not page_items or has_more in (False, 0, "0") or next_cursor in (None, "", current_cursor):
                break
            current_cursor = int(next_cursor)

        raw = raw_pages[0] if raw_pages else {}
        return {
            "status": "ok",
            "source": self.manifest.id,
            "endpoint": DEFAULT_USER_VIDEOS_PATH,
            "request": {k: v for k, v in ((last_spec.params if last_spec else {}) or {}).items() if v not in [None, ""] and k != "cookie"},
            "raw": raw,
            "raw_pages": raw_pages,
            "items": items[:target_count],
            "pagination": pagination,
            "normalized": self._normalize_video_response(raw),
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
            raise RuntimeError(self._format_http_error(response)) from exc
        return response.json()

    def _format_http_error(self, response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            body = response.text.strip().replace("\n", " ")
            return f"TikHub API HTTP {response.status_code}: {body[:220]}"
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if isinstance(detail, dict):
            message = detail.get("message_zh") or detail.get("message") or payload.get("message")
            router = detail.get("router")
            request_id = detail.get("request_id")
            parts = [f"TikHub API HTTP {response.status_code}"]
            if message:
                parts.append(str(message))
            if router:
                parts.append(f"接口：{router}")
            if request_id:
                parts.append(f"request_id：{request_id}")
            return "；".join(parts)
        message = payload.get("message_zh") or payload.get("message") if isinstance(payload, dict) else ""
        return f"TikHub API HTTP {response.status_code}: {message or str(payload)[:220]}"

    def _user_videos_params(
        self,
        sec_user_id: str,
        max_cursor: int,
        count: int,
        filter_type: int,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "sec_user_id": sec_user_id,
            "max_cursor": int(max_cursor or 0),
            "count": min(max(int(count or 20), 1), 20),
            "filter_type": int(filter_type or 0),
        }
        if self.douyin_web_cookie:
            params["cookie"] = self.douyin_web_cookie
        return params

    def _payload_root(self, data: dict[str, Any]) -> Any:
        if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
            return data["data"]
        return data

    def _normalize_response(self, data: dict[str, Any]) -> dict[str, Any]:
        root = self._payload_root(data)
        root = root if isinstance(root, dict) else {}
        return {
            "code": data.get("code") or data.get("status_code"),
            "message": data.get("message"),
            "message_zh": data.get("message_zh"),
            "request_id": data.get("request_id") or data.get("rid"),
            "cursor": root.get("cursor"),
            "has_more": root.get("has_more"),
            "search_id": root.get("extra", {}).get("logid") if isinstance(root.get("extra"), dict) else None,
            "impr_id": root.get("log_pb", {}).get("impr_id") if isinstance(root.get("log_pb"), dict) else None,
        }

    def _extract_user_search_pagination(self, data: dict[str, Any]) -> dict[str, Any]:
        root = self._payload_root(data)
        root = root if isinstance(root, dict) else {}
        extra = root.get("extra") if isinstance(root.get("extra"), dict) else {}
        log_pb = root.get("log_pb") if isinstance(root.get("log_pb"), dict) else {}
        search_id = extra.get("logid") or log_pb.get("impr_id") or root.get("rid") or data.get("rid")
        return {
            "page": root.get("page") or data.get("page"),
            "has_more": root.get("has_more"),
            "cursor": root.get("cursor"),
            "search_id": search_id,
        }

    def _normalize_video_response(self, data: dict[str, Any]) -> dict[str, Any]:
        root = self._payload_root(data)
        root = root if isinstance(root, dict) else {}
        return {"max_cursor": root.get("max_cursor"), "has_more": root.get("has_more"), "cursor": root.get("cursor")}

    def _extract_items(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        root = self._payload_root(data)
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
        root = self._payload_root(data)
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
        root = self._payload_root(data)
        aweme = root.get("aweme_detail") if isinstance(root, dict) else None
        if not isinstance(aweme, dict) and isinstance(root, dict):
            aweme = root.get("aweme") if isinstance(root.get("aweme"), dict) else root
        if not isinstance(aweme, dict):
            return {}
        return self._normalize_video(aweme)

    def _extract_profile_user(self, data: dict[str, Any]) -> dict[str, Any]:
        root = self._payload_root(data)
        if isinstance(root, dict):
            user = root.get("user") or root.get("user_info") or root.get("profile")
            if isinstance(user, dict):
                return user
        return {}

    def _extract_download_urls(self, data: dict[str, Any]) -> dict[str, Any]:
        video = self._extract_one_video(data)
        raw = video.get("raw") if isinstance(video.get("raw"), dict) else {}
        video_data = raw.get("video") if isinstance(raw.get("video"), dict) else {}
        return {"play_addr": self._first_url(video_data.get("play_addr")), "play_addr_h264": self._first_url(video_data.get("play_addr_h264")), "play_addr_bytevc1": self._first_url(video_data.get("play_addr_bytevc1")), "download_addr": self._first_url(video_data.get("download_addr"))}

    def _normalize_user(self, item: dict[str, Any]) -> dict[str, Any]:
        user = self._extract_user_info(item)
        follower_count = self._to_int(user.get("follower_count") or user.get("followers") or user.get("followerCount"))
        like_count = self._to_int(user.get("total_favorited") or user.get("total_favorited_count") or user.get("like_count"))
        aweme_count = self._to_int(user.get("aweme_count") or user.get("video_count") or user.get("awemeCount"))
        last_post_at = self._to_int(
            user.get("last_post_time")
            or user.get("last_aweme_time")
            or user.get("latest_post_time")
            or user.get("recent_update_at")
        )
        verified = bool(
            user.get("verified")
            or user.get("is_verified")
            or user.get("isVerified")
            or user.get("verification_type")
            or user.get("custom_verify")
            or user.get("enterprise_verify_reason")
        )
        is_private = bool(user.get("is_private_account") or user.get("private_account") or user.get("secret"))
        return {
            "sec_uid": user.get("sec_uid") or user.get("secUid") or user.get("sec_user_id"),
            "uid": user.get("uid") or user.get("user_id") or user.get("id"),
            "unique_id": user.get("unique_id") or user.get("uniqueId") or user.get("short_id") or user.get("search_user_name"),
            "nickname": user.get("nickname") or user.get("display_name") or user.get("nickname_display") or user.get("search_user_desc"),
            "signature": user.get("signature") or user.get("desc") or user.get("search_user_desc") or "",
            "avatar": self._first_avatar_url(user),
            "follower_count": follower_count,
            "following_count": self._to_int(user.get("following_count")),
            "like_count": like_count,
            "aweme_count": aweme_count,
            "recent_update_at": last_post_at,
            "last_post_at": last_post_at,
            "verified": verified,
            "is_private": is_private,
            "raw": item,
        }

    def _enrich_users(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for item in items:
            sec_user_id = item.get("sec_uid") or item.get("sec_user_id")
            if not sec_user_id:
                enriched.append(item)
                continue
            try:
                profile = self.get_user_profile(str(sec_user_id)).get("user") or {}
            except Exception as exc:
                item["profile_error"] = str(exc)
                enriched.append(item)
                continue
            enriched.append(self._merge_user_profile(item, profile))
        return enriched

    def _merge_user_profile(self, item: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        if not profile:
            return item
        merged = {**item}
        for key in (
            "sec_uid",
            "uid",
            "unique_id",
            "nickname",
            "signature",
            "avatar",
            "follower_count",
            "following_count",
            "like_count",
            "aweme_count",
            "recent_update_at",
            "last_post_at",
            "verified",
            "is_private",
        ):
            value = profile.get(key)
            if value not in [None, ""]:
                merged[key] = value
        merged["profile_raw"] = profile.get("raw")
        return merged

    def _normalize_video(self, item: dict[str, Any]) -> dict[str, Any]:
        stats = item.get("statistics") or item.get("stats") or {}
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        play_url = self._first_url(video.get("play_addr")) or self._first_url(video.get("play_addr_h264"))
        download_url = self._first_url(video.get("download_addr")) or play_url
        cover_url = self._first_url(video.get("cover")) or self._first_url(video.get("origin_cover")) or self._first_url(video.get("dynamic_cover"))
        return {
            "aweme_id": item.get("aweme_id") or item.get("id"),
            "desc": item.get("desc") or item.get("title") or "",
            "create_time": self._to_int(item.get("create_time")),
            "author": self._normalize_user(item.get("author", {})) if isinstance(item.get("author"), dict) else None,
            "video": video,
            "statistics": stats,
            "digg_count": self._to_int(stats.get("digg_count") or stats.get("like_count")),
            "comment_count": self._to_int(stats.get("comment_count")),
            "share_count": self._to_int(stats.get("share_count")),
            "collect_count": self._to_int(stats.get("collect_count") or stats.get("favorite_count")),
            "play_count": self._to_int(stats.get("play_count")),
            "is_top": bool(item.get("is_top") or item.get("is_pinned") or item.get("is_top_item")),
            "cover_url": cover_url,
            "play_url": play_url,
            "download_url": download_url,
            "source_video_url": download_url or play_url,
            "raw": item,
        }

    def _extract_user_info(self, item: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        user_info = item.get("user_info")
        if isinstance(user_info, dict):
            return user_info

        for key in ("dynamic_patch", "raw_data", "data", "payload"):
            parsed = self._maybe_parse_json(item.get(key))
            if isinstance(parsed, dict):
                nested = parsed.get("user_info")
                if isinstance(nested, dict):
                    return nested
                nested = parsed.get("user")
                if isinstance(nested, dict):
                    return nested
                if "sec_uid" in parsed or "unique_id" in parsed or "nickname" in parsed:
                    return parsed

        dynamic_patch = item.get("dynamic_patch")
        if isinstance(dynamic_patch, dict):
            parsed = self._maybe_parse_json(dynamic_patch.get("raw_data"))
            if isinstance(parsed, dict):
                nested = parsed.get("user_info")
                if isinstance(nested, dict):
                    return nested
                nested = parsed.get("user")
                if isinstance(nested, dict):
                    return nested
                if "sec_uid" in parsed or "unique_id" in parsed or "nickname" in parsed:
                    return parsed

        return item

    def _maybe_parse_json(self, value: Any) -> Any:
        if not isinstance(value, str) or not value:
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

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

    def _to_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _extract_pagination(self, data: dict[str, Any]) -> dict[str, Any]:
        root = self._payload_root(data)
        root = root if isinstance(root, dict) else {}
        extra = root.get("extra") if isinstance(root.get("extra"), dict) else {}
        log_pb = root.get("log_pb") if isinstance(root.get("log_pb"), dict) else {}
        return {"cursor": root.get("cursor"), "has_more": root.get("has_more"), "search_id": extra.get("logid") or log_pb.get("impr_id")}

    def _extract_video_pagination(self, data: dict[str, Any]) -> dict[str, Any]:
        root = self._payload_root(data)
        root = root if isinstance(root, dict) else {}
        return {"max_cursor": root.get("max_cursor"), "has_more": root.get("has_more")}
