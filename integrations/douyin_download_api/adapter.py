from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from dotenv import load_dotenv

from integrations.base import IntegrationAdapter, IntegrationManifest


DEFAULT_API_BASE = "http://127.0.0.1:8123"
DEFAULT_OUTPUT_DIR = Path("data/runtime/douyin/downloads")


class DouyinDownloadApiAdapter(IntegrationAdapter):
    manifest = IntegrationManifest(
        id="douyin-download-api",
        name="Douyin TikTok Download API 适配器",
        description="调用 Evil0ctal/Douyin_TikTok_Download_API，仅接入用户主页、作品详情、收藏视频下载。",
        repo_url="https://github.com/Evil0ctal/Douyin_TikTok_Download_API",
        tags=["douyin", "api", "download"],
        config_schema={
            "api_base": "Douyin_TikTok_Download_API 本地服务地址，默认 http://127.0.0.1:8123",
            "cookie_env": "保存抖音 Cookie 的环境变量名，默认 DY_COOKIES",
            "output_dir": "收藏视频下载目录",
        },
    )

    def __init__(self, config: dict[str, Any] | None = None):
        load_dotenv()
        self.config = config or {}
        self.api_base = (
            self.config.get("api_base")
            or os.getenv("DOUYIN_DOWNLOAD_API_BASE")
            or DEFAULT_API_BASE
        ).rstrip("/")
        self.cookie_env = self.config.get("cookie_env") or "DY_COOKIES"
        self.output_dir = Path(
            self.config.get("output_dir")
            or os.getenv("DOUYIN_OUTPUT_DIR")
            or DEFAULT_OUTPUT_DIR
        )

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]:
        cfg = {**self.config, **(config or {})}
        api_base = (cfg.get("api_base") or os.getenv("DOUYIN_DOWNLOAD_API_BASE") or self.api_base).rstrip("/")
        cookie_env = cfg.get("cookie_env") or self.cookie_env
        errors = []
        try:
            response = requests.get(f"{api_base}/docs", timeout=5)
            if response.status_code >= 500:
                errors.append(f"API service unhealthy: HTTP {response.status_code}")
        except requests.RequestException as exc:
            errors.append(f"API service not reachable: {api_base} ({exc})")
        if not os.getenv(cookie_env):
            errors.append(f"Missing env cookie: {cookie_env}")
        return errors

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "user_profile":
            return self.get_user_profile(payload["user_url"])
        if action == "user_videos":
            return self.get_user_videos(
                user_url=payload.get("user_url"),
                sec_user_id=payload.get("sec_user_id"),
                max_items=payload.get("max_items"),
                page_size=int(payload.get("page_size", 20)),
                max_cursor=int(payload.get("max_cursor") or 0),
            )
        if action == "work_detail":
            return self.get_work_detail(payload["work_url"])
        if action == "download_favorites":
            return self.download_favorite_videos(
                max_items=int(payload.get("max_items", 18)),
                page_size=int(payload.get("page_size", 18)),
            )
        if action == "favorite_items":
            return self.get_favorite_videos(
                max_items=payload.get("max_items"),
                page_size=int(payload.get("page_size", 18)),
                max_cursor=int(payload.get("max_cursor") or 0),
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
        raise ValueError(f"Unsupported Douyin action: {action}")

    def get_user_profile(self, user_url: str) -> dict[str, Any]:
        sec_user_id = self.get_sec_user_id(user_url)
        data = self._get_json("/api/douyin/web/handler_user_profile", {"sec_user_id": sec_user_id})
        return {
            "status": "ok",
            "source": self.manifest.id,
            "sec_user_id": sec_user_id,
            "raw": data,
            "profile": self._extract_profile(data),
        }

    def get_user_videos(
        self,
        user_url: str | None = None,
        sec_user_id: str | None = None,
        max_items: int | str | None = None,
        page_size: int = 20,
        max_cursor: int = 0,
        all_pages: bool = False,
    ) -> dict[str, Any]:
        target_sec_user_id = sec_user_id or self.get_sec_user_id(user_url or "")
        limit = None if max_items in [None, "", 0, "0", "all"] else int(max_items)
        items = []
        pages = []
        current_cursor = max_cursor

        while True:
            remaining = page_size if limit is None else max(1, min(page_size, limit - len(items)))
            page = self._get_json(
                "/api/douyin/web/fetch_user_post_videos",
                {"sec_user_id": target_sec_user_id, "max_cursor": current_cursor, "count": remaining},
            )
            pages.append(page)
            videos = self._extract_aweme_list(page)
            if not videos:
                break

            for item in videos:
                if limit is not None and len(items) >= limit:
                    break
                items.append(item)

            next_cursor = self._extract_next_cursor(page)
            has_more = self._extract_has_more(page)
            if (
                not all_pages
                or (limit is not None and len(items) >= limit)
                or not has_more
                or next_cursor == current_cursor
            ):
                break
            current_cursor = next_cursor

        return {
            "status": "ok",
            "source": self.manifest.id,
            "sec_user_id": target_sec_user_id,
            "items": items,
            "count": len(items),
            "next_cursor": self._extract_next_cursor(pages[-1]) if pages else current_cursor,
            "has_more": self._extract_has_more(pages[-1]) if pages else False,
            "raw_pages": pages,
        }

    def get_work_detail(self, work_url: str) -> dict[str, Any]:
        aweme_id = None
        try:
            data = self._get_json("/api/hybrid/video_data", {"url": work_url, "minimal": "false"})
        except RuntimeError:
            aweme_id = self.get_aweme_id(work_url)
            data = self._get_json("/api/douyin/web/fetch_one_video", {"aweme_id": aweme_id})
        return {
            "status": "ok",
            "source": self.manifest.id,
            "aweme_id": aweme_id or self._extract_work(data).get("aweme_id"),
            "raw": data,
            "detail": self._extract_work(data),
        }

    def download_favorite_videos(self, max_items: int = 18, page_size: int = 18) -> dict[str, Any]:
        favorite_data = self.get_favorite_videos(max_items=max_items, page_size=page_size, all_pages=True)
        videos = favorite_data.get("items", [])

        self.output_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []
        skipped = []

        for item in videos:
            url = self._extract_share_url(item)
            aweme_id = str(item.get("aweme_id") or item.get("id") or "")
            if not url and aweme_id:
                url = f"https://www.douyin.com/video/{aweme_id}"
            if not url:
                skipped.append({"aweme_id": aweme_id, "reason": "missing_url"})
                continue
            saved_path = self._download_one(url, aweme_id or str(len(downloaded) + 1))
            downloaded.append({"aweme_id": aweme_id, "path": saved_path, "source_url": url})

        manifest = {
            "status": "ok",
            "source": self.manifest.id,
            "downloaded": downloaded,
            "skipped": skipped,
            "output_dir": str(self.output_dir),
        }
        manifest_path = self.output_dir / "favorites_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest

    def get_favorite_videos(
        self,
        max_items: int | str | None = None,
        page_size: int = 18,
        max_cursor: int = 0,
        all_pages: bool = False,
    ) -> dict[str, Any]:
        cookie = os.getenv(self.cookie_env)
        if not cookie:
            raise RuntimeError(f"Set {self.cookie_env} in .env before fetching favorites.")

        limit = None if max_items in [None, "", 0, "0", "all"] else int(max_items)
        items = []
        pages = []
        current_cursor = max_cursor

        while True:
            remaining = page_size if limit is None else max(1, min(page_size, limit - len(items)))
            page = self._get_json(
                "/api/douyin/web/fetch_user_collection_videos",
                {"cookie": cookie, "max_cursor": current_cursor, "counts": remaining},
            )
            pages.append(page)
            videos = self._extract_aweme_list(page)
            if not videos:
                break

            for item in videos:
                if limit is not None and len(items) >= limit:
                    break
                items.append(item)

            next_cursor = self._extract_next_cursor(page)
            has_more = self._extract_has_more(page)
            if (
                not all_pages
                or (limit is not None and len(items) >= limit)
                or not has_more
                or next_cursor == current_cursor
            ):
                break
            current_cursor = next_cursor

        return {
            "status": "ok",
            "source": self.manifest.id,
            "items": items,
            "count": len(items),
            "next_cursor": self._extract_next_cursor(pages[-1]) if pages else current_cursor,
            "has_more": self._extract_has_more(pages[-1]) if pages else False,
            "raw_pages": pages,
        }

    def get_video_comments(
        self,
        aweme_id: str,
        max_items: int | str | None = 100,
        page_size: int = 20,
        cursor: int = 0,
        all_pages: bool = True,
    ) -> dict[str, Any]:
        limit = None if max_items in [None, "", 0, "0", "all"] else int(max_items)
        items = []
        pages = []
        current_cursor = int(cursor or 0)

        while True:
            remaining = page_size if limit is None else max(1, min(page_size, limit - len(items)))
            page = self._get_json(
                "/api/douyin/web/fetch_video_comments",
                {"aweme_id": aweme_id, "cursor": current_cursor, "count": remaining},
            )
            pages.append(page)
            comments = self._extract_comments(page)
            if not comments:
                break
            for item in comments:
                if limit is not None and len(items) >= limit:
                    break
                items.append(item)

            next_cursor = self._extract_comment_cursor(page)
            has_more = self._extract_has_more(page)
            if (
                not all_pages
                or (limit is not None and len(items) >= limit)
                or not has_more
                or next_cursor == current_cursor
            ):
                break
            current_cursor = next_cursor

        return {
            "status": "ok",
            "source": self.manifest.id,
            "aweme_id": aweme_id,
            "items": items,
            "count": len(items),
            "next_cursor": self._extract_comment_cursor(pages[-1]) if pages else current_cursor,
            "has_more": self._extract_has_more(pages[-1]) if pages else False,
            "raw_pages": pages,
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
        limit = None if max_items in [None, "", 0, "0", "all"] else int(max_items)
        items = []
        pages = []
        current_cursor = int(cursor or 0)

        while True:
            remaining = page_size if limit is None else max(1, min(page_size, limit - len(items)))
            page = self._get_json(
                "/api/douyin/web/fetch_video_comment_replies",
                {"item_id": item_id, "comment_id": comment_id, "cursor": current_cursor, "count": remaining},
            )
            pages.append(page)
            replies = self._extract_comments(page)
            if not replies:
                break
            for item in replies:
                if limit is not None and len(items) >= limit:
                    break
                items.append(item)

            next_cursor = self._extract_comment_cursor(page)
            has_more = self._extract_has_more(page)
            if (
                not all_pages
                or (limit is not None and len(items) >= limit)
                or not has_more
                or next_cursor == current_cursor
            ):
                break
            current_cursor = next_cursor

        return {
            "status": "ok",
            "source": self.manifest.id,
            "item_id": item_id,
            "comment_id": comment_id,
            "items": items,
            "count": len(items),
            "next_cursor": self._extract_comment_cursor(pages[-1]) if pages else current_cursor,
            "has_more": self._extract_has_more(pages[-1]) if pages else False,
            "raw_pages": pages,
        }

    def get_sec_user_id(self, user_url: str) -> str:
        data = self._get_json("/api/douyin/web/get_sec_user_id", {"url": user_url})
        return self._extract_value(data, ["sec_user_id", "data", "sec_uid", "secUid"])

    def get_aweme_id(self, work_url: str) -> str:
        data = self._get_json("/api/douyin/web/get_aweme_id", {"url": work_url})
        return self._extract_value(data, ["aweme_id", "data", "id"])

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = requests.get(f"{self.api_base}{path}", params=params, timeout=60)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Upstream API failed: HTTP {response.status_code}, body={response.text[:1200]}"
            ) from exc
        return response.json()

    def _download_one(self, url: str, fallback_name: str) -> str:
        response = requests.get(
            f"{self.api_base}/api/download",
            params={"url": url, "prefix": "true", "with_watermark": "false"},
            timeout=300,
            stream=True,
        )
        response.raise_for_status()
        file_name = self._filename_from_response(response) or f"douyin_{fallback_name}.mp4"
        target = self.output_dir / file_name
        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if chunk:
                    file.write(chunk)
        return str(target)

    def _filename_from_response(self, response: requests.Response) -> str | None:
        disposition = response.headers.get("content-disposition", "")
        if "filename*=" in disposition:
            return unquote(disposition.split("filename*=", 1)[1].split("''")[-1].strip('"'))
        if "filename=" in disposition:
            return disposition.split("filename=", 1)[1].strip('"')
        parsed = urlparse(response.url)
        name = Path(parsed.path).name
        return name or None

    def _extract_value(self, data: dict[str, Any], keys: list[str]) -> str:
        for key in keys:
            value = data.get(key)
            if value:
                return str(value)
        nested = data.get("data")
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if value:
                    return str(value)
        if isinstance(nested, str):
            return nested
        raise RuntimeError(f"Unable to extract value from response: {data}")

    def _extract_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        profile = data.get("data") if isinstance(data.get("data"), dict) else data
        user = profile.get("user") or profile.get("user_info") or profile
        return {
            "sec_uid": user.get("sec_uid"),
            "uid": user.get("uid"),
            "nickname": user.get("nickname"),
            "signature": user.get("signature"),
            "avatar": self._first_url(user.get("avatar_thumb") or user.get("avatar_larger")),
            "following_count": user.get("following_count"),
            "follower_count": user.get("follower_count"),
            "total_favorited": user.get("total_favorited"),
            "aweme_count": user.get("aweme_count"),
        }

    def _extract_work(self, data: dict[str, Any]) -> dict[str, Any]:
        item = data.get("data") if isinstance(data.get("data"), dict) else data
        item = item.get("aweme_detail") or item.get("aweme") or item
        return {
            "aweme_id": item.get("aweme_id"),
            "desc": item.get("desc"),
            "create_time": item.get("create_time"),
            "author": (item.get("author") or {}).get("nickname"),
            "share_url": (item.get("share_info") or {}).get("share_url"),
        }

    def _extract_aweme_list(self, page: dict[str, Any]) -> list[dict[str, Any]]:
        data = page.get("data") if isinstance(page.get("data"), dict) else page
        items = data.get("aweme_list") or data.get("videos") or data.get("list") or []
        return items if isinstance(items, list) else []

    def _extract_comments(self, page: dict[str, Any]) -> list[dict[str, Any]]:
        data = page.get("data") if isinstance(page.get("data"), dict) else page
        for key in ("comments", "comment_list", "reply_comments", "replies", "list", "items"):
            items = data.get(key) if isinstance(data, dict) else None
            if isinstance(items, list):
                return items
        return data if isinstance(data, list) else []

    def _extract_next_cursor(self, page: dict[str, Any]) -> int:
        data = page.get("data") if isinstance(page.get("data"), dict) else page
        return int(data.get("max_cursor") or data.get("cursor") or 0)

    def _extract_comment_cursor(self, page: dict[str, Any]) -> int:
        data = page.get("data") if isinstance(page.get("data"), dict) else page
        return int(data.get("cursor") or data.get("next_cursor") or data.get("max_cursor") or 0)

    def _extract_has_more(self, page: dict[str, Any]) -> bool:
        data = page.get("data") if isinstance(page.get("data"), dict) else page
        return bool(data.get("has_more") in [1, True, "1", "true", "True"])

    def _extract_share_url(self, item: dict[str, Any]) -> str | None:
        share_info = item.get("share_info") or {}
        return share_info.get("share_url") or item.get("share_url")

    def _first_url(self, value: Any) -> str | None:
        if isinstance(value, dict):
            urls = value.get("url_list") or []
            return urls[0] if urls else None
        return value if isinstance(value, str) else None
