from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from dotenv import load_dotenv

from backend.app.error_log_store import write_error_log
from backend.app.tiktok_target_store import (
    create_target_video,
    get_target_user_by_identifiers,
    get_target_video,
    upsert_target_video_comment_page,
    upsert_target_user,
)
from integrations.base import IntegrationAdapter, IntegrationManifest


DEFAULT_API_BASE = "https://api.tikhub.io"
DEFAULT_API_KEY_ENV = "TIKHUB_API_KEY"
DEFAULT_USER_SEARCH_PATH = "/api/v1/douyin/search/fetch_user_search_v2"
DEFAULT_USER_SEARCH_V2_PATH = DEFAULT_USER_SEARCH_PATH
DEFAULT_USER_PROFILE_PATH = "/api/v1/douyin/web/handler_user_profile"
DEFAULT_USER_VIDEOS_PATH = "/api/v1/douyin/web/fetch_user_post_videos"
DEFAULT_ONE_VIDEO_PATH = "/api/v1/douyin/app/v3/fetch_one_video_v3"
DEFAULT_USER_COLLECTION_VIDEOS_PATH = "/api/v1/douyin/web/fetch_user_collection_videos"
DEFAULT_AWEME_ID_PATH = "/api/v1/douyin/web/get_aweme_id"
DEFAULT_SEC_USER_ID_PATH = "/api/v1/douyin/web/get_sec_user_id"
DEFAULT_VIDEO_COMMENTS_PATH = "/api/v1/douyin/web/fetch_video_comments"
DEFAULT_VIDEO_COMMENT_REPLIES_PATH = "/api/v1/douyin/web/fetch_video_comment_replies"
DEFAULT_OUTPUT_DIR = Path("data/runtime/douyin/downloads")
USER_SEARCH_FANS_ALIASES = {
    "": "",
    "0_1k": "0_1k",
    "below_1k": "0_1k",
    "under_1k": "0_1k",
    "1k_5k": "1k_5k",
    "5k_10k": "5k_10k",
    "10k_100k": "10k_100k",
    "1w_10w": "10k_100k",
    "10w_100w": "100k_1M",
    "100k_1m": "100k_1M",
    "100k_1M": "100k_1M",
    "1m_": "1M_",
    "1M_": "1M_",
    "100w_": "1M_",
}

USER_SEARCH_TYPE_ALIASES = {
    "": "",
    "300": "300",
    "creator": "300",
    "creator_user": "300",
    "900": "900",
    "shop": "900",
    "shop_user": "900",
    "mall": "900",
    "700": "700",
    "music": "700",
    "musician": "700",
    "800": "800",
    "star": "800",
    "celebrity": "800",
    "common_user": "",
    "enterprise_user": "",
    "personal_user": "",
}


@dataclass
class TikhubRequestSpec:
    path: str
    method: str
    params: dict[str, Any] | None = None
    json_body: dict[str, Any] | None = None


class TikhubApiError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int | None = None,
        path: str = "",
        method: str = "",
        request_payload: dict[str, Any] | None = None,
        response_payload: Any = None,
        response_text: str = "",
        message: str = "",
        previous_errors: list[dict[str, Any]] | None = None,
        error_log_path: str = "",
    ):
        self.status_code = status_code
        self.path = path
        self.method = method
        self.request_payload = request_payload or {}
        self.response_payload = response_payload
        self.response_text = response_text
        self.previous_errors = previous_errors or []
        self.error_log_path = error_log_path
        super().__init__(message or self._fallback_message())

    def _fallback_message(self) -> str:
        status = f" HTTP {self.status_code}" if self.status_code else ""
        return f"TikHub API{status} request failed"

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "status_code": self.status_code,
            "path": self.path,
            "method": self.method,
            "request": self.request_payload,
            "message": str(self),
        }
        if self.response_payload is not None:
            payload["response"] = self.response_payload
            if isinstance(self.response_payload, dict):
                source = self.response_payload.get("detail") if isinstance(self.response_payload.get("detail"), dict) else self.response_payload
                payload["request_id"] = source.get("request_id") or self.response_payload.get("request_id")
                payload["router"] = source.get("router") or self.response_payload.get("router")
                payload["docs"] = source.get("docs") or self.response_payload.get("docs")
        elif self.response_text:
            payload["response_text"] = self.response_text[:2000]
        if self.previous_errors:
            payload["previous_errors"] = self.previous_errors
        if self.error_log_path:
            payload["error_log_path"] = self.error_log_path
        return {key: value for key, value in payload.items() if value not in [None, "", {}]}


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
        self.douyin_web_cookie = self.config.get("douyin_web_cookie") or os.getenv("TIKHUB_DOUYIN_WEB_COOKIE") or os.getenv("DOUYIN_WEB_COOKIE") or ""
        self.output_dir = Path(
            self.config.get("output_dir")
            or os.getenv("DOUYIN_OUTPUT_DIR")
            or DEFAULT_OUTPUT_DIR
        )

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
        if action == "favorite_items":
            return self.get_favorite_videos(
                max_items=payload.get("max_items"),
                page_size=int(payload.get("page_size", 20)),
                max_cursor=int(payload.get("max_cursor") or 0),
            )
        if action == "download_favorites":
            return self.download_favorite_videos(
                max_items=int(payload.get("max_items", 18)),
                page_size=int(payload.get("page_size", 18)),
            )
        if action == "video_comments":
            return self.get_video_comments(
                aweme_id=payload["aweme_id"],
                max_items=payload.get("max_items"),
                page_size=int(payload.get("page_size", 20)),
                cursor=int(payload.get("cursor") or 0),
            )
        if action == "video_comment_replies":
            return self.get_video_comment_replies(
                item_id=payload["item_id"],
                comment_id=payload["comment_id"],
                max_items=payload.get("max_items"),
                page_size=int(payload.get("page_size", 20)),
                cursor=int(payload.get("cursor") or 0),
            )
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
        profile_limit: int | None = None,
    ) -> dict[str, Any]:
        keyword = str(keyword or "").strip()
        if not keyword:
            raise ValueError("TikHub 用户搜索 keyword 不能为空。")
        resolved_page = page if page > 0 else 1
        target_count = max(1, min(int(count or 20), 50))
        resolved_cursor = cursor if cursor is not None else 0
        if offset is not None and offset > 0 and cursor is None and page <= 1:
            resolved_cursor = offset
        data: dict[str, Any] = {}
        raw_pages: list[dict[str, Any]] = []
        spec: TikhubRequestSpec | None = None

        if cursor is not None or resolved_page <= 1:
            data, spec, errors = self._request_user_search_page(
                keyword=keyword,
                cursor=resolved_cursor,
            )
            raw_pages.append(data)
        else:
            current_cursor = 0
            for page_index in range(1, resolved_page + 1):
                data, spec, errors = self._request_user_search_page(
                    keyword=keyword,
                    cursor=current_cursor,
                )
                raw_pages.append(data)
                if page_index >= resolved_page:
                    break
                pagination = self._extract_user_search_pagination(data)
                next_cursor = self._to_int(pagination.get("cursor"))
                if not self._has_more(pagination.get("has_more")) or next_cursor is None or next_cursor == current_cursor:
                    break
                current_cursor = next_cursor

        spec = spec or TikhubRequestSpec(path=DEFAULT_USER_SEARCH_PATH, method="POST", json_body={})
        items = self._extract_items(data)
        if enrich_profiles:
            items = self._enrich_users(
                items,
                limit=profile_limit if profile_limit is not None else target_count,
            )
        pagination = self._extract_user_search_pagination(data)
        response = {
            "status": "ok",
            "source": self.manifest.id,
            "endpoint": spec.path,
            "keyword": keyword,
            "page": resolved_page,
            "cursor": (spec.json_body or {}).get("cursor", resolved_cursor),
            "search_id": pagination.get("search_id") or "",
            "count": len(items),
            "raw_count": len(items),
            "requested_count": target_count,
            "request": {k: v for k, v in (spec.json_body or {}).items() if v is not None},
            "raw": data,
            "raw_pages": raw_pages,
            "items": items,
            "pagination": pagination,
            "normalized": self._normalize_response(data),
            "next_cursor": pagination.get("cursor"),
            "has_more": self._has_more(pagination.get("has_more")),
        }
        self._upsert_search_users(keyword, response["items"], fallback_search_id=str(response["search_id"] or ""))
        return response

    def _request_user_search_page(
        self,
        *,
        keyword: str,
        cursor: int,
    ) -> tuple[dict[str, Any], TikhubRequestSpec, list[dict[str, Any]]]:
        spec = TikhubRequestSpec(
            path=DEFAULT_USER_SEARCH_PATH,
            method="POST",
            json_body={
                "keyword": keyword,
                "cursor": int(cursor or 0),
            },
        )
        return self._request_json(spec), spec, []

    def get_user_profile(self, sec_user_id: str) -> dict[str, Any]:
        sec_user_id = str(sec_user_id or "").strip()
        if not sec_user_id:
            raise ValueError("TikHub 用户信息接口需要 sec_user_id。")
        params = {"sec_user_id": sec_user_id}
        if self.douyin_web_cookie:
            params["cookie"] = self.douyin_web_cookie
        spec = TikhubRequestSpec(
            path=DEFAULT_USER_PROFILE_PATH,
            method="GET",
            params=params,
        )
        data = self._request_json(spec)
        user = self._extract_profile_user(data)
        normalized = self._normalize_user(user) if user else {}
        if normalized:
            self._upsert_normalized_user(sec_user_id=sec_user_id, normalized=normalized, raw=data)
        return {
            "status": "ok",
            "source": self.manifest.id,
            "request": spec.params,
            "raw": data,
            "user": normalized,
            "profile": normalized,
            "sec_user_id": sec_user_id,
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
        resolved_filter_type = int(filter_type if filter_type is not None else sort_type or 0)
        initial_cursor = int(max_cursor or 0)
        request_payload = {
            "sec_user_id": sec,
            "unique_id": str(unique_id or ""),
            "max_cursor": initial_cursor,
            "count": target_count,
            "sort_type": int(sort_type or 0),
            "filter_type": resolved_filter_type,
        }

        page_size = min(target_count, 20)
        current_cursor = initial_cursor
        raw_pages: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        pagination: dict[str, Any] = {}
        last_page_raw: dict[str, Any] = {}

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
            data = self._request_json(spec)
            raw_pages.append(data)
            last_page_raw = data
            page_items = self._extract_video_items(data)
            pagination = self._extract_video_pagination(data)
            items.extend(page_items)

            next_cursor = pagination.get("max_cursor")
            has_more = pagination.get("has_more")
            if not page_items or has_more in (False, 0, "0") or next_cursor in (None, "", current_cursor):
                break
            current_cursor = int(next_cursor)

        raw = last_page_raw if last_page_raw else {}
        response = {
            "status": "ok",
            "source": self.manifest.id,
            "endpoint": DEFAULT_USER_VIDEOS_PATH,
            "request": request_payload,
            "raw": raw,
            "raw_pages": raw_pages,
            "items": items[:target_count],
            "pagination": pagination,
            "normalized": self._normalize_video_response(raw),
            "next_cursor": pagination.get("max_cursor"),
            "has_more": bool(pagination.get("has_more")),
        }
        self._upsert_videos_from_items(sec, response["items"], unique_id=str(unique_id or ""), source_page=response)
        return response

    def get_work_detail(self, work_url: str, region: str = "US") -> dict[str, Any]:
        aweme_id = self.get_aweme_id(work_url)
        result = self.get_one_video(aweme_id, region=region)
        video = result.get("video") if isinstance(result.get("video"), dict) else {}
        return {**result, "aweme_id": aweme_id, "detail": video}

    def get_one_video(self, aweme_id: str, region: str = "US") -> dict[str, Any]:
        cached_video = get_target_video(aweme_id)
        if cached_video:
            return {
                "status": "ok",
                "source": self.manifest.id,
                "request": {"aweme_id": aweme_id, "region": region},
                "raw": cached_video.get("source_json") or {},
                "video": cached_video,
                "detail": cached_video,
                "aweme_id": cached_video.get("aweme_id") or aweme_id,
                "download_urls": {
                    "play_addr": cached_video.get("play_url") or "",
                    "download_addr": cached_video.get("download_url") or "",
                },
                "cache": {"hit": True, "video_id": cached_video.get("id")},
            }
        spec = TikhubRequestSpec(path=DEFAULT_ONE_VIDEO_PATH, method="GET", params={"aweme_id": aweme_id, "region": region})
        data = self._request_json(spec)
        video = self._extract_one_video(data)
        if video:
            self._upsert_videos_from_items("", [video], source_page={"endpoint": DEFAULT_ONE_VIDEO_PATH})
        return {
            "status": "ok",
            "source": self.manifest.id,
            "request": spec.params,
            "raw": data,
            "video": video,
            "detail": video,
            "aweme_id": video.get("aweme_id") or aweme_id,
            "download_urls": self._extract_download_urls(data),
        }

    def get_favorite_videos(
        self,
        max_items: int | str | None = None,
        page_size: int = 18,
        max_cursor: int = 0,
        all_pages: bool = False,
    ) -> dict[str, Any]:
        if not self.douyin_web_cookie:
            raise RuntimeError("Set TIKHUB_DOUYIN_WEB_COOKIE or DOUYIN_WEB_COOKIE in .env before fetching Douyin favorites.")
        limit = None if max_items in [None, "", 0, "0", "all"] else int(max_items)
        request_count = max(1, min(int(page_size or 18), 50))
        current_cursor = int(max_cursor or 0)
        items: list[dict[str, Any]] = []
        raw_pages: list[dict[str, Any]] = []
        pagination: dict[str, Any] = {}

        while limit is None or len(items) < limit:
            remaining = request_count if limit is None else max(1, min(request_count, limit - len(items)))
            spec = TikhubRequestSpec(
                path=DEFAULT_USER_COLLECTION_VIDEOS_PATH,
                method="POST",
                json_body={"cookie": self.douyin_web_cookie, "max_cursor": current_cursor, "counts": remaining},
            )
            data = self._request_json(spec)
            raw_pages.append(data)
            page_items = self._extract_video_items(data)
            if not page_items:
                break
            items.extend(page_items)
            pagination = self._extract_video_pagination(data)
            next_cursor = self._to_int(pagination.get("max_cursor") or pagination.get("cursor"))
            has_more = self._has_more(pagination.get("has_more"))
            if (
                not all_pages
                or (limit is not None and len(items) >= limit)
                or not has_more
                or next_cursor in [None, current_cursor]
            ):
                break
            current_cursor = int(next_cursor)

        normalized_items = items[:limit] if limit is not None else items
        self._upsert_videos_from_items("", normalized_items, source_page={"endpoint": DEFAULT_USER_COLLECTION_VIDEOS_PATH})
        return {
            "status": "ok",
            "source": self.manifest.id,
            "endpoint": DEFAULT_USER_COLLECTION_VIDEOS_PATH,
            "items": normalized_items,
            "count": len(normalized_items),
            "next_cursor": pagination.get("max_cursor") or pagination.get("cursor") or current_cursor,
            "has_more": self._has_more(pagination.get("has_more")),
            "raw_pages": raw_pages,
        }

    def download_favorite_videos(self, max_items: int = 18, page_size: int = 18) -> dict[str, Any]:
        favorite_data = self.get_favorite_videos(max_items=max_items, page_size=page_size, all_pages=True)
        videos = [item for item in favorite_data.get("items", []) if isinstance(item, dict)]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []
        skipped = []

        for index, item in enumerate(videos, start=1):
            aweme_id = str(item.get("aweme_id") or item.get("id") or index)
            url = self._downloadable_video_url(item)
            if not url:
                skipped.append({"aweme_id": aweme_id, "reason": "missing_download_url"})
                continue
            try:
                saved_path = self._download_media_url(url, aweme_id)
            except Exception as exc:
                skipped.append({"aweme_id": aweme_id, "reason": f"{type(exc).__name__}: {exc}"})
                continue
            downloaded.append({"aweme_id": aweme_id, "path": saved_path, "source_url": url})

        manifest = {
            "status": "ok",
            "source": self.manifest.id,
            "mode": "downloaded",
            "items": videos,
            "count": len(videos),
            "downloaded": downloaded,
            "skipped": skipped,
            "output_dir": str(self.output_dir),
            "raw_pages": favorite_data.get("raw_pages", []),
        }
        manifest_path = self.output_dir / "favorites_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest

    def _downloadable_video_url(self, item: dict[str, Any]) -> str:
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        raw_video = raw.get("video") if isinstance(raw.get("video"), dict) else {}
        return str(
            item.get("download_url")
            or item.get("source_video_url")
            or self._first_url(video.get("download_addr"))
            or self._first_url(raw_video.get("download_addr"))
            or item.get("play_url")
            or self._first_url(video.get("play_addr"))
            or self._first_url(video.get("play_addr_h264"))
            or self._first_url(raw_video.get("play_addr"))
            or self._first_url(raw_video.get("play_addr_h264"))
            or ""
        )

    def _download_media_url(self, url: str, fallback_name: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        response: requests.Response | None = None
        try:
            response = requests.get(url, headers=headers, timeout=300, stream=True)
            response.raise_for_status()
        except requests.RequestException as exc:
            write_error_log(
                namespace="tikhub-douyin-download",
                path=urlparse(url).path or "/download",
                method="GET",
                request={"params": {"url": url}, "headers": headers},
                exc=exc,
                api_base=urlparse(url).netloc,
                status_code=response.status_code if response is not None else None,
                response_text=response.text[:4000] if response is not None else "",
                extra={"phase": "download_media_request"},
            )
            raise

        file_name = self._download_filename(response, fallback_name)
        target = self._unique_download_path(file_name)
        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if chunk:
                    file.write(chunk)
        return str(target)

    def _download_filename(self, response: requests.Response, fallback_name: str) -> str:
        disposition = response.headers.get("content-disposition", "")
        file_name = ""
        if "filename*=" in disposition:
            file_name = unquote(disposition.split("filename*=", 1)[1].split("''")[-1].strip('"'))
        elif "filename=" in disposition:
            file_name = disposition.split("filename=", 1)[1].strip('"')
        if not file_name:
            file_name = Path(urlparse(response.url).path).name
        if not file_name or "." not in file_name:
            content_type = response.headers.get("content-type", "").lower()
            suffix = ".mp4"
            if "image/" in content_type:
                suffix = "." + content_type.split("image/", 1)[1].split(";", 1)[0].replace("jpeg", "jpg")
            file_name = f"douyin_{fallback_name}{suffix}"
        return Path(file_name).name

    def _unique_download_path(self, file_name: str) -> Path:
        target = self.output_dir / file_name
        if not target.exists():
            return target
        stem = target.stem
        suffix = target.suffix
        for index in range(1, 10000):
            candidate = self.output_dir / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Unable to allocate download filename for {file_name}")

    def get_video_comments(
        self,
        aweme_id: str,
        max_items: int | str | None = 100,
        page_size: int = 20,
        cursor: int = 0,
        all_pages: bool = True,
    ) -> dict[str, Any]:
        aweme_id = str(aweme_id or "").strip()
        if not aweme_id:
            raise ValueError("TikHub 评论接口需要 aweme_id。")
        limit = None if max_items in [None, "", 0, "0", "all"] else int(max_items)
        current_cursor = int(cursor or 0)
        request_count = max(1, min(int(page_size or 20), 50))
        items: list[dict[str, Any]] = []
        raw_pages: list[dict[str, Any]] = []
        pagination: dict[str, Any] = {}

        while limit is None or len(items) < limit:
            remaining = request_count if limit is None else max(1, min(request_count, limit - len(items)))
            spec = TikhubRequestSpec(
                path=DEFAULT_VIDEO_COMMENTS_PATH,
                method="GET",
                params={"aweme_id": aweme_id, "cursor": current_cursor, "count": remaining},
            )
            data = self._request_json(spec)
            raw_pages.append(data)
            page_items = self._extract_comment_items(data)
            items.extend(page_items)
            pagination = self._extract_comment_pagination(data)
            self._cache_comment_page(
                video_id=aweme_id,
                aweme_id=aweme_id,
                item_id="",
                comment_id="",
                page_kind="comments",
                cursor=current_cursor,
                count=remaining,
                request=spec.params or {},
                items=page_items,
                raw=data,
                raw_pages=[data],
                pagination=pagination,
            )
            next_cursor = self._to_int(pagination.get("cursor") or pagination.get("next_cursor") or pagination.get("max_cursor"))
            has_more = self._has_more(pagination.get("has_more"))
            if (
                not all_pages
                or (limit is not None and len(items) >= limit)
                or not has_more
                or next_cursor in [None, current_cursor]
            ):
                break
            current_cursor = int(next_cursor)

        normalized_items = items[:limit] if limit is not None else items
        self._cache_comment_page(
            video_id=aweme_id,
            aweme_id=aweme_id,
            item_id="",
            comment_id="",
            page_kind="comments",
            cursor=cursor,
            count=len(normalized_items) if limit is None else int(limit),
            request={"aweme_id": aweme_id, "cursor": cursor, "count": page_size},
            items=normalized_items,
            raw=raw_pages[-1] if raw_pages else {},
            raw_pages=raw_pages,
            pagination=pagination,
        )
        return {
            "status": "ok",
            "source": self.manifest.id,
            "endpoint": DEFAULT_VIDEO_COMMENTS_PATH,
            "aweme_id": aweme_id,
            "request": {"aweme_id": aweme_id, "cursor": cursor, "count": page_size},
            "items": normalized_items,
            "count": len(normalized_items),
            "next_cursor": pagination.get("cursor") or pagination.get("next_cursor") or pagination.get("max_cursor") or current_cursor,
            "has_more": self._has_more(pagination.get("has_more")),
            "pagination": pagination,
            "raw": raw_pages[-1] if raw_pages else {},
            "raw_pages": raw_pages,
        }

    def get_video_comment_replies(
        self,
        item_id: str,
        comment_id: str,
        max_items: int | str | None = 20,
        page_size: int = 20,
        cursor: int = 0,
        all_pages: bool = True,
    ) -> dict[str, Any]:
        item_id = str(item_id or "").strip()
        comment_id = str(comment_id or "").strip()
        if not item_id:
            raise ValueError("TikHub 评论回复接口需要 item_id。")
        if not comment_id:
            raise ValueError("TikHub 评论回复接口需要 comment_id。")
        limit = None if max_items in [None, "", 0, "0", "all"] else int(max_items)
        current_cursor = int(cursor or 0)
        request_count = max(1, min(int(page_size or 20), 50))
        items: list[dict[str, Any]] = []
        raw_pages: list[dict[str, Any]] = []
        pagination: dict[str, Any] = {}

        while limit is None or len(items) < limit:
            remaining = request_count if limit is None else max(1, min(request_count, limit - len(items)))
            spec = TikhubRequestSpec(
                path=DEFAULT_VIDEO_COMMENT_REPLIES_PATH,
                method="GET",
                params={"item_id": item_id, "comment_id": comment_id, "cursor": current_cursor, "count": remaining},
            )
            data = self._request_json(spec)
            raw_pages.append(data)
            page_items = self._extract_comment_items(data)
            items.extend(page_items)
            pagination = self._extract_comment_pagination(data)
            self._cache_comment_page(
                video_id=item_id,
                aweme_id=item_id,
                item_id=item_id,
                comment_id=comment_id,
                page_kind="replies",
                cursor=current_cursor,
                count=remaining,
                request=spec.params or {},
                items=page_items,
                raw=data,
                raw_pages=[data],
                pagination=pagination,
            )
            next_cursor = self._to_int(pagination.get("cursor") or pagination.get("next_cursor") or pagination.get("max_cursor"))
            has_more = self._has_more(pagination.get("has_more"))
            if (
                not all_pages
                or (limit is not None and len(items) >= limit)
                or not has_more
                or next_cursor in [None, current_cursor]
            ):
                break
            current_cursor = int(next_cursor)

        normalized_items = items[:limit] if limit is not None else items
        self._cache_comment_page(
            video_id=item_id,
            aweme_id=item_id,
            item_id=item_id,
            comment_id=comment_id,
            page_kind="replies",
            cursor=cursor,
            count=len(normalized_items) if limit is None else int(limit),
            request={"item_id": item_id, "comment_id": comment_id, "cursor": cursor, "count": page_size},
            items=normalized_items,
            raw=raw_pages[-1] if raw_pages else {},
            raw_pages=raw_pages,
            pagination=pagination,
        )
        return {
            "status": "ok",
            "source": self.manifest.id,
            "endpoint": DEFAULT_VIDEO_COMMENT_REPLIES_PATH,
            "item_id": item_id,
            "comment_id": comment_id,
            "request": {"item_id": item_id, "comment_id": comment_id, "cursor": cursor, "count": page_size},
            "items": normalized_items,
            "count": len(normalized_items),
            "next_cursor": pagination.get("cursor") or pagination.get("next_cursor") or pagination.get("max_cursor") or current_cursor,
            "has_more": self._has_more(pagination.get("has_more")),
            "pagination": pagination,
            "raw": raw_pages[-1] if raw_pages else {},
            "raw_pages": raw_pages,
        }

    def get_sec_user_id(self, user_url: str) -> str:
        url = str(user_url or "").strip()
        if not url:
            raise ValueError("TikHub get_sec_user_id 需要用户主页链接。")
        spec = TikhubRequestSpec(path=DEFAULT_SEC_USER_ID_PATH, method="GET", params={"url": url})
        data = self._request_json(spec)
        return self._extract_value(data, ["sec_user_id", "sec_uid", "secUid", "data", "id"])

    def get_aweme_id(self, work_url: str) -> str:
        url = str(work_url or "").strip()
        if not url:
            raise ValueError("TikHub get_aweme_id 需要作品链接。")
        spec = TikhubRequestSpec(path=DEFAULT_AWEME_ID_PATH, method="GET", params={"url": url})
        data = self._request_json(spec)
        return self._extract_value(data, ["aweme_id", "item_id", "id", "data"])

    def _request_json(self, spec: TikhubRequestSpec) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            response = requests.request(spec.method, f"{self.api_base}{spec.path}", params=spec.params, json=spec.json_body, headers=headers, timeout=60)
        except requests.RequestException as exc:
            error_log_path = write_error_log(
                namespace="tikhub",
                path=spec.path,
                method=spec.method,
                request=self._safe_request_payload(spec),
                exc=exc,
                api_base=self.api_base,
                extra={"phase": "request_exception"},
            )
            raise TikhubApiError(
                path=spec.path,
                method=spec.method,
                request_payload=self._safe_request_payload(spec),
                message=f"TikHub API 请求失败：{exc}",
                error_log_path=error_log_path,
            ) from exc
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            error = self._build_http_error(response, spec)
            error.error_log_path = write_error_log(
                namespace="tikhub",
                path=spec.path,
                method=spec.method,
                request=self._safe_request_payload(spec),
                exc=exc,
                api_base=self.api_base,
                status_code=response.status_code,
                response_payload=error.response_payload,
                response_text=error.response_text,
                extra={"phase": "http_error"},
            )
            raise error from exc
        try:
            return response.json()
        except ValueError as exc:
            error_log_path = write_error_log(
                namespace="tikhub",
                path=spec.path,
                method=spec.method,
                request=self._safe_request_payload(spec),
                exc=exc,
                api_base=self.api_base,
                status_code=response.status_code,
                response_text=response.text.strip(),
                extra={"phase": "non_json_response"},
            )
            raise TikhubApiError(
                status_code=response.status_code,
                path=spec.path,
                method=spec.method,
                request_payload=self._safe_request_payload(spec),
                response_text=response.text.strip(),
                message=f"TikHub API 返回非 JSON 响应：{response.text.strip()[:220]}",
                error_log_path=error_log_path,
            ) from exc

    def _safe_request_payload(self, spec: TikhubRequestSpec) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if spec.params:
            payload["params"] = self._redact_request_secrets(spec.params)
        if spec.json_body:
            payload["json_body"] = self._redact_request_secrets(spec.json_body)
        return payload

    def _redact_request_secrets(self, value: dict[str, Any]) -> dict[str, Any]:
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in {"cookie", "authorization", "token", "api_key", "apikey"}:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = item
        return redacted

    def _build_http_error(self, response: requests.Response, spec: TikhubRequestSpec) -> TikhubApiError:
        response_payload: Any = None
        response_text = ""
        try:
            response_payload = response.json()
        except ValueError:
            response_text = response.text.strip()
        return TikhubApiError(
            status_code=response.status_code,
            path=spec.path,
            method=spec.method,
            request_payload=self._safe_request_payload(spec),
            response_payload=response_payload,
            response_text=response_text,
            message=self._format_http_error(response, response_payload=response_payload, response_text=response_text),
        )

    def _format_http_error(self, response: requests.Response, *, response_payload: Any = None, response_text: str = "") -> str:
        payload = response_payload
        if payload is None:
            try:
                payload = response.json()
            except ValueError:
                body = (response_text or response.text).strip().replace("\n", " ")
                return f"TikHub API HTTP {response.status_code}: {body[:220]}"
        if not isinstance(payload, dict):
            body = str(payload).strip().replace("\n", " ")
            return f"TikHub API HTTP {response.status_code}: {body[:220]}"
        detail = payload.get("detail") if isinstance(payload, dict) else None
        source = detail if isinstance(detail, dict) else payload
        message = source.get("message_zh") or source.get("message") or payload.get("message_zh") or payload.get("message")
        router = source.get("router") or payload.get("router")
        request_id = source.get("request_id") or payload.get("request_id")
        docs = source.get("docs") or payload.get("docs")
        parts = [f"TikHub API HTTP {response.status_code}"]
        if message:
            parts.append(str(message))
        if router:
            parts.append(f"接口：{router}")
        if request_id:
            parts.append(f"request_id：{request_id}")
        if docs:
            parts.append(f"docs：{docs}")
        return "；".join(parts)

    def _normalize_user_search_fans(self, value: Any) -> str:
        text = str(value or "").strip()
        return USER_SEARCH_FANS_ALIASES.get(text, USER_SEARCH_FANS_ALIASES.get(text.lower(), ""))

    def _normalize_user_search_type(self, value: Any) -> str:
        text = str(value or "").strip()
        return USER_SEARCH_TYPE_ALIASES.get(text, USER_SEARCH_TYPE_ALIASES.get(text.lower(), ""))

    def _has_more(self, value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "none", "no"}
        return bool(value)

    def _looks_like_sec_user_id(self, value: Any) -> bool:
        text = str(value or "").strip()
        return len(text) >= 20 and " " not in text and "@" not in text and (text.startswith("MS4w") or text.startswith("MS4"))

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
        root = self._user_search_root(data)
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
        root = self._user_search_root(data)
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

    def _extract_comment_items(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        root = self._payload_root(data)
        if isinstance(root, dict):
            for key in ("comments", "comment_list", "reply_comments", "replies", "items", "list"):
                value = root.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            nested = root.get("data")
            if isinstance(nested, dict):
                for key in ("comments", "comment_list", "reply_comments", "replies", "items", "list"):
                    value = nested.get(key)
                    if isinstance(value, list):
                        return [item for item in value if isinstance(item, dict)]
        if isinstance(root, list):
            return [item for item in root if isinstance(item, dict)]
        return []

    def _cache_comment_page(
        self,
        *,
        video_id: str,
        aweme_id: str = "",
        item_id: str = "",
        comment_id: str = "",
        page_kind: str = "comments",
        cursor: int = 0,
        count: int = 20,
        request: dict[str, Any] | None = None,
        items: list[dict[str, Any]] | None = None,
        raw: dict[str, Any] | None = None,
        raw_pages: list[dict[str, Any]] | None = None,
        pagination: dict[str, Any] | None = None,
    ) -> None:
        clean_request = {
            key: value
            for key, value in (request or {}).items()
            if str(key).lower() not in {"cookie", "authorization", "token", "api_key", "apikey"}
        }
        upsert_target_video_comment_page(
            source=self.manifest.id,
            video_id=video_id,
            aweme_id=aweme_id,
            item_id=item_id,
            comment_id=comment_id,
            page_kind=page_kind,
            cursor=int(cursor or 0),
            count=int(count or 0),
            request=clean_request,
            items=items or [],
            raw={"raw": raw or {}, "raw_pages": raw_pages or ([] if not raw else [raw])},
            pagination=pagination or {},
            normalized=pagination or {},
            fetched_at=int(time.time()),
        )

    def _upsert_search_users(self, keyword: str, items: list[dict[str, Any]], *, fallback_search_id: str = "") -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            user_id = str(item.get("uid") or item.get("user_id") or item.get("id") or "")
            sec_user_id = str(item.get("sec_uid") or item.get("sec_user_id") or "")
            unique_id = str(item.get("unique_id") or "")
            if not sec_user_id and self._looks_like_sec_user_id(user_id):
                sec_user_id = user_id
            if not user_id:
                user_id = sec_user_id or unique_id
            if not user_id:
                continue
            upsert_target_user(
                user_id,
                {
                    "keyword": keyword,
                    "sec_user_id": sec_user_id,
                    "unique_id": unique_id,
                    "nickname": item.get("nickname") or "",
                    "avatar_url": item.get("avatar") or item.get("avatar_url") or "",
                    "signature": item.get("signature") or "",
                    "ip_location": item.get("ip_location") or "",
                    "follower_count": item.get("follower_count"),
                    "like_count": item.get("like_count"),
                    "total_favorited": item.get("total_favorited") if item.get("total_favorited") not in [None, ""] else item.get("like_count"),
                    "aweme_count": item.get("aweme_count"),
                    "following_count": item.get("following_count"),
                    "recent_update_at": item.get("recent_update_at") or item.get("last_post_at"),
                    "last_post_at": item.get("last_post_at") or item.get("recent_update_at"),
                    "verified": item.get("verified"),
                    "is_private": item.get("is_private"),
                    "status": "candidate",
                    "searched_at": int(time.time()),
                    "source_json": item,
                },
            )
        if fallback_search_id and items:
            first = items[0]
            user_id = str(first.get("uid") or first.get("user_id") or first.get("id") or "")
            if user_id:
                upsert_target_user(user_id, {"keyword": keyword, "searched_at": int(time.time())})

    def _upsert_normalized_user(self, *, sec_user_id: str, normalized: dict[str, Any], raw: dict[str, Any]) -> None:
        user_id = str(normalized.get("uid") or normalized.get("user_id") or normalized.get("id") or sec_user_id or "")
        if not user_id:
            return
        upsert_target_user(
            user_id,
            {
                "keyword": "",
                "sec_user_id": sec_user_id,
                "unique_id": normalized.get("unique_id") or "",
                "nickname": normalized.get("nickname") or "",
                "avatar_url": normalized.get("avatar") or normalized.get("avatar_url") or "",
                "signature": normalized.get("signature") or "",
                "ip_location": normalized.get("ip_location") or "",
                "follower_count": normalized.get("follower_count"),
                "like_count": normalized.get("like_count"),
                "total_favorited": normalized.get("total_favorited"),
                "aweme_count": normalized.get("aweme_count"),
                "following_count": normalized.get("following_count"),
                "recent_update_at": normalized.get("recent_update_at") or normalized.get("last_post_at"),
                "last_post_at": normalized.get("last_post_at") or normalized.get("recent_update_at"),
                "verified": normalized.get("verified"),
                "is_private": normalized.get("is_private"),
                "status": "candidate",
                "searched_at": int(time.time()),
                "source_json": raw or normalized,
            },
        )

    def _upsert_videos_from_items(
        self,
        sec_user_id: str,
        items: list[dict[str, Any]],
        *,
        unique_id: str = "",
        source_page: dict[str, Any] | None = None,
    ) -> None:
        source_page = source_page or {}
        for item in items:
            if not isinstance(item, dict):
                continue
            aweme_id = str(item.get("aweme_id") or item.get("id") or "")
            if not aweme_id:
                continue
            author = item.get("author") if isinstance(item.get("author"), dict) else {}
            user_id = str(author.get("uid") or author.get("user_id") or author.get("id") or sec_user_id or "")
            if not user_id:
                user_id = sec_user_id or aweme_id
            create_target_video(
                aweme_id,
                user_id,
                {
                    "set_id": "",
                    "aweme_id": aweme_id,
                    "desc": item.get("desc") or "",
                    "cover_url": item.get("cover_url") or "",
                    "play_url": item.get("play_url") or "",
                    "download_url": item.get("download_url") or item.get("source_video_url") or "",
                    "create_time": item.get("create_time"),
                    "digg_count": item.get("digg_count"),
                    "comment_count": item.get("comment_count"),
                    "share_count": item.get("share_count"),
                    "collect_count": item.get("collect_count"),
                    "play_count": item.get("play_count") or item.get("play_count_raw"),
                    "is_top": item.get("is_top"),
                    "selected": False,
                    "selection_strategy": "api_refresh",
                    "source_json": {
                        **item,
                        "unique_id": unique_id,
                        "source_page": source_page.get("endpoint") or "",
                    },
                },
            )

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
        wrapper = item if isinstance(item, dict) else {}
        raw_user_id = user.get("user_id") or wrapper.get("user_id")
        raw_uid = user.get("uid") or wrapper.get("uid") or user.get("id") or wrapper.get("id")
        follower_count = self._to_int(
            user.get("follower_count")
            or wrapper.get("follower_count")
            or user.get("followers")
            or wrapper.get("followers")
            or user.get("followerCount")
            or wrapper.get("followerCount")
            or user.get("fans_cnt")
            or wrapper.get("fans_cnt")
            or user.get("fans_count")
            or wrapper.get("fans_count")
        )
        like_count = self._to_int(
            user.get("total_favorited")
            or wrapper.get("total_favorited")
            or user.get("total_favorited_count")
            or wrapper.get("total_favorited_count")
            or user.get("like_count")
            or wrapper.get("like_count")
            or user.get("like_cnt")
            or wrapper.get("like_cnt")
        )
        aweme_count = self._to_int(
            user.get("aweme_count")
            or wrapper.get("aweme_count")
            or user.get("video_count")
            or wrapper.get("video_count")
            or user.get("awemeCount")
            or wrapper.get("awemeCount")
            or user.get("publish_cnt")
            or wrapper.get("publish_cnt")
            or user.get("publish_count")
            or wrapper.get("publish_count")
        )
        last_post_at = self._to_int(
            user.get("last_post_time")
            or wrapper.get("last_post_time")
            or user.get("last_aweme_time")
            or wrapper.get("last_aweme_time")
            or user.get("latest_post_time")
            or wrapper.get("latest_post_time")
            or user.get("recent_update_at")
            or wrapper.get("recent_update_at")
        )
        verified = bool(
            user.get("verified")
            or wrapper.get("verified")
            or user.get("is_verified")
            or wrapper.get("is_verified")
            or user.get("isVerified")
            or wrapper.get("isVerified")
            or user.get("verification_type")
            or wrapper.get("verification_type")
            or user.get("custom_verify")
            or wrapper.get("custom_verify")
            or user.get("enterprise_verify_reason")
            or wrapper.get("enterprise_verify_reason")
        )
        is_private = bool(
            user.get("is_private_account")
            or wrapper.get("is_private_account")
            or user.get("private_account")
            or wrapper.get("private_account")
            or user.get("secret")
            or wrapper.get("secret")
        )
        sec_uid = (
            user.get("sec_uid")
            or wrapper.get("sec_uid")
            or user.get("secUid")
            or wrapper.get("secUid")
            or user.get("sec_user_id")
            or wrapper.get("sec_user_id")
            or (raw_user_id if self._looks_like_sec_user_id(raw_user_id) else None)
        )
        uid = raw_uid or (None if self._looks_like_sec_user_id(raw_user_id) else raw_user_id)
        unique_id = (
            user.get("unique_id")
            or wrapper.get("unique_id")
            or user.get("uniqueId")
            or wrapper.get("uniqueId")
            or user.get("short_id")
            or wrapper.get("short_id")
            or user.get("search_user_name")
            or wrapper.get("search_user_name")
        )
        nickname = (
            user.get("nickname")
            or wrapper.get("nickname")
            or user.get("nick_name")
            or wrapper.get("nick_name")
            or user.get("display_name")
            or wrapper.get("display_name")
            or user.get("nickname_display")
            or wrapper.get("nickname_display")
            or user.get("search_user_desc")
            or wrapper.get("search_user_desc")
        )
        return {
            "sec_uid": sec_uid,
            "sec_user_id": sec_uid,
            "uid": uid,
            "user_id": uid,
            "unique_id": unique_id,
            "nickname": nickname,
            "signature": user.get("signature") or wrapper.get("signature") or user.get("desc") or wrapper.get("desc") or "",
            "ip_location": user.get("ip_location") or wrapper.get("ip_location") or user.get("ipLocation") or wrapper.get("ipLocation") or user.get("location") or wrapper.get("location") or "",
            "avatar": self._first_avatar_url(user) or self._first_avatar_url(wrapper) or user.get("avatar_url") or wrapper.get("avatar_url") or user.get("avatar") or wrapper.get("avatar"),
            "follower_count": follower_count,
            "following_count": self._to_int(user.get("following_count") or wrapper.get("following_count") or user.get("follow_count") or wrapper.get("follow_count")),
            "like_count": like_count,
            "total_favorited": like_count,
            "aweme_count": aweme_count,
            "recent_update_at": last_post_at,
            "last_post_at": last_post_at,
            "verified": verified,
            "is_private": is_private,
            "raw": item,
        }

    def enrich_user_profiles(
        self,
        items: list[dict[str, Any]],
        *,
        keyword: str = "",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        enriched = self._enrich_users(items, limit=limit)
        if keyword:
            self._upsert_search_users(keyword, enriched)
        return enriched

    def _enrich_users(
        self,
        items: list[dict[str, Any]],
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if not items:
            return []
        normalized_items = [item if isinstance(item, dict) else {} for item in items]
        enrich_limit = len(normalized_items) if limit is None else max(0, min(int(limit or 0), len(normalized_items)))
        if enrich_limit <= 0:
            return normalized_items

        def enrich_one(index: int, item: dict[str, Any]) -> tuple[int, dict[str, Any]]:
            item = {**item}
            sec_user_id = self._resolve_sec_user_id_for_profile(item)
            if not sec_user_id:
                item["profile_error"] = "missing sec_user_id for handler_user_profile"
                return index, item
            try:
                profile = self.get_user_profile(str(sec_user_id)).get("user") or {}
            except Exception as exc:
                item["profile_error"] = str(exc)
                return index, item
            return index, self._merge_user_profile(item, profile)

        enriched = list(normalized_items)
        max_workers = min(4, enrich_limit)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(enrich_one, index, normalized_items[index]) for index in range(enrich_limit)]
            for future in as_completed(futures):
                index, item = future.result()
                enriched[index] = item
        return enriched

    def _merge_user_profile(self, item: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        if not profile:
            return item
        merged = {**item}
        for key in (
            "sec_uid",
            "sec_user_id",
            "uid",
            "user_id",
            "unique_id",
            "nickname",
            "signature",
            "ip_location",
            "avatar",
            "follower_count",
            "following_count",
            "like_count",
            "total_favorited",
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

    def _resolve_sec_user_id_for_profile(self, item: dict[str, Any]) -> str:
        if not isinstance(item, dict):
            return ""
        for source in (item, item.get("raw"), item.get("profile_raw")):
            user = self._extract_user_info(source) if isinstance(source, dict) else {}
            for candidate in (
                item.get("sec_uid"),
                item.get("sec_user_id"),
                user.get("sec_uid"),
                user.get("secUid"),
                user.get("sec_user_id"),
                user.get("user_id") if self._looks_like_sec_user_id(user.get("user_id")) else None,
                source.get("user_id") if isinstance(source, dict) and self._looks_like_sec_user_id(source.get("user_id")) else None,
            ):
                if candidate not in [None, ""]:
                    return str(candidate)
        cached = get_target_user_by_identifiers(
            user_id=str(item.get("uid") or item.get("user_id") or item.get("id") or ""),
            unique_id=str(item.get("unique_id") or ""),
        )
        if cached:
            sec_user_id = cached.get("sec_user_id") or cached.get("sec_uid")
            if sec_user_id not in [None, ""]:
                return str(sec_user_id)
        return ""

    def _normalize_video(self, item: dict[str, Any]) -> dict[str, Any]:
        stats = item.get("statistics") or item.get("stats") or {}
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        play_url = self._first_url(video.get("play_addr")) or self._first_url(video.get("play_addr_h264"))
        download_url = self._first_url(video.get("download_addr")) or play_url
        cover_url = self._first_url(video.get("cover")) or self._first_url(video.get("origin_cover")) or self._first_url(video.get("dynamic_cover"))
        play_count = self._to_int(
            stats.get("play_count")
            or stats.get("playCount")
            or stats.get("view_count")
            or stats.get("video_view_count")
            or item.get("play_count")
            or item.get("view_count")
        )
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
            "play_count": play_count if play_count and play_count > 0 else 1,
            "play_count_raw": play_count or 0,
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
                nested_data = parsed.get("data")
                if isinstance(nested_data, dict):
                    nested = nested_data.get("user") or nested_data.get("user_info") or nested_data.get("profile")
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

    def _user_search_root(self, data: dict[str, Any]) -> dict[str, Any]:
        root = self._payload_root(data)
        if not isinstance(root, dict):
            return {}
        nested = root.get("data")
        if isinstance(nested, dict):
            if any(key in nested for key in ("user_list", "has_more", "cursor", "extra", "log_pb")):
                return nested
        return root

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

    def _extract_value(self, data: Any, keys: list[str]) -> str:
        if data in [None, ""]:
            return ""
        if isinstance(data, str):
            return data
        if isinstance(data, (int, float)):
            return str(data)
        if isinstance(data, list):
            for item in data:
                value = self._extract_value(item, keys)
                if value:
                    return value
            return ""
        if not isinstance(data, dict):
            return ""
        for key in keys:
            value = data.get(key)
            if isinstance(value, (str, int, float)) and str(value):
                return str(value)
        for key in ("data", "result", "aweme", "aweme_detail", "user", "user_info"):
            value = self._extract_value(data.get(key), keys)
            if value:
                return value
        return ""

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

    def _extract_comment_pagination(self, data: dict[str, Any]) -> dict[str, Any]:
        root = self._payload_root(data)
        root = root if isinstance(root, dict) else {}
        nested = root.get("data") if isinstance(root.get("data"), dict) else {}
        source = {**nested, **root}
        return {
            "cursor": source.get("cursor"),
            "next_cursor": source.get("next_cursor"),
            "max_cursor": source.get("max_cursor"),
            "has_more": source.get("has_more"),
            "total": source.get("total"),
        }
