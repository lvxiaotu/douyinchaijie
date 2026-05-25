from __future__ import annotations

import builtins
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from dotenv import load_dotenv

from integrations.base import IntegrationAdapter, IntegrationManifest
from integrations.douyin_spider_provider.sidecar_client import DouyinSpiderSidecarClient


DEFAULT_VENDOR_DIR = Path("integrations/douyin_spider_provider/vendor/Douyin_Spider")
DEFAULT_OUTPUT_DIR = Path("data/runtime/douyin/downloads")
DEFAULT_SIDECAR_BASE_URL = "http://127.0.0.1:8131"


@dataclass
class DouyinSpiderModules:
    auth_cls: Any
    api_cls: Any
    header_builder: Any
    header_type: Any
    params_cls: Any


class DouyinSpiderApiError(RuntimeError):
    def __init__(
        self,
        *,
        method: str = "",
        request_payload: dict[str, Any] | None = None,
        message: str = "",
        cause: Exception | None = None,
    ):
        self.method = method
        self.request_payload = request_payload or {}
        self.cause = cause
        super().__init__(message or f"Douyin_Spider request failed: {method}")

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "method": self.method,
            "request": self.request_payload,
            "message": str(self),
        }
        if self.cause is not None:
            payload["cause_type"] = type(self.cause).__name__
            payload["cause"] = str(self.cause)
        return {key: value for key, value in payload.items() if value not in [None, "", {}]}


class DouyinSpiderAdapter(IntegrationAdapter):
    manifest = IntegrationManifest(
        id="douyin-spider-provider",
        name="Douyin_Spider Provider",
        description="Local Douyin_Spider-based Douyin data adapter.",
        repo_url="https://github.com/cvv-cat/Douyin_Spider",
        tags=["douyin", "spider", "local-api"],
        config_schema={
            "vendor_path": "Path to cvv-cat/Douyin_Spider source tree.",
            "cookie_env": "Cookie env variable, default DY_COOKIES.",
            "output_dir": "Download output directory, default DOUYIN_OUTPUT_DIR.",
            "execution_mode": "sidecar | inprocess, default sidecar.",
            "sidecar_base_url": "Sidecar URL when execution_mode=sidecar.",
        },
    )

    def __init__(self, config: dict[str, Any] | None = None):
        load_dotenv()
        self.config = config or {}
        self.vendor_path = self._select_vendor_path(
            self.config.get("vendor_path") or os.getenv("DOUYIN_SPIDER_VENDOR_PATH") or str(DEFAULT_VENDOR_DIR)
        )
        self.cookie_env = self.config.get("cookie_env") or os.getenv("DOUYIN_SPIDER_COOKIE_ENV") or "DY_COOKIES"
        self.cookie = self._sanitize_cookie(
            self.config.get("cookie")
            or os.getenv(self.cookie_env)
            or os.getenv("DOUYIN_SPIDER_COOKIE")
            or os.getenv("TIKHUB_DOUYIN_WEB_COOKIE")
            or os.getenv("DOUYIN_WEB_COOKIE")
            or ""
        )
        self.output_dir = Path(
            self.config.get("output_dir")
            or os.getenv("DOUYIN_OUTPUT_DIR")
            or DEFAULT_OUTPUT_DIR
        )
        self.timeout = int(self.config.get("timeout") or os.getenv("DOUYIN_SPIDER_TIMEOUT") or 60)
        legacy_sidecar = str(os.getenv("DOUYIN_SPIDER_USE_SIDECAR") or "").strip().lower()
        configured_mode = self.config.get("execution_mode") or os.getenv("DOUYIN_SPIDER_EXECUTION_MODE")
        if not configured_mode and legacy_sidecar in {"0", "false", "no"}:
            configured_mode = "inprocess"
        self.execution_mode = str(configured_mode or "sidecar").strip().lower()
        if self.execution_mode not in {"sidecar", "inprocess"}:
            self.execution_mode = "sidecar"
        self.sidecar_base_url = str(
            self.config.get("sidecar_base_url")
            or os.getenv("DOUYIN_SPIDER_API_BASE")
            or DEFAULT_SIDECAR_BASE_URL
        ).rstrip("/")
        self._modules: DouyinSpiderModules | None = None
        self._sidecar: DouyinSpiderSidecarClient | None = None

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]:
        cfg = {**self.config, **(config or {})}
        execution_mode = str(cfg.get("execution_mode") or self.execution_mode).strip().lower()
        if execution_mode == "sidecar":
            try:
                status = self._sidecar_status()
            except Exception as exc:
                return [f"Douyin Spider sidecar unavailable: {self.sidecar_base_url} ({type(exc).__name__}: {exc})"]
            errors = status.get("errors") if isinstance(status.get("errors"), list) else []
            return [str(error) for error in errors]

        vendor_path = self._select_vendor_path(
            cfg.get("vendor_path") or os.getenv("DOUYIN_SPIDER_VENDOR_PATH") or str(DEFAULT_VENDOR_DIR)
        )
        cookie = self._sanitize_cookie(
            cfg.get("cookie")
            or os.getenv(cfg.get("cookie_env") or os.getenv("DOUYIN_SPIDER_COOKIE_ENV") or self.cookie_env)
            or os.getenv("DOUYIN_SPIDER_COOKIE")
            or os.getenv("TIKHUB_DOUYIN_WEB_COOKIE")
            or os.getenv("DOUYIN_WEB_COOKIE")
            or ""
        )

        errors: list[str] = []
        if not vendor_path.exists():
            errors.append(f"Douyin_Spider vendor path not found: {vendor_path}")
        else:
            for relative in ("dy_apis/douyin_api.py", "builder/auth.py", "static/dy_ab.js"):
                if not (vendor_path / relative).exists():
                    errors.append(f"Missing Douyin_Spider vendor file: {relative}")
            if not (vendor_path / "node_modules").exists():
                errors.append(f"Missing Node dependencies: run npm install in {vendor_path}")
        if not cookie:
            errors.append(f"Missing Douyin cookie env: {self.cookie_env}")
        elif "s_v_web_id=" not in cookie:
            errors.append("Douyin cookie is missing s_v_web_id")
        return errors

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._uses_sidecar():
            return self._sidecar_run(payload)
        action = payload.get("action")
        if action == "user_profile":
            sec_user_id = payload.get("sec_user_id") or self.get_sec_user_id(payload.get("user_url") or "")
            return self.get_user_profile(sec_user_id)
        if action == "user_videos":
            return self.get_user_videos(
                sec_user_id=payload.get("sec_user_id"),
                unique_id=payload.get("unique_id"),
                max_cursor=int(payload.get("max_cursor", 0)),
                count=int(payload.get("count", payload.get("page_size", 20))),
            )
        if action == "one_video":
            return self.get_one_video(payload["aweme_id"])
        if action == "work_detail":
            return self.get_work_detail(payload["work_url"])
        if action == "favorite_items":
            return self.get_favorite_videos(
                max_items=payload.get("max_items"),
                page_size=int(payload.get("page_size", 20)),
                max_cursor=int(payload.get("max_cursor") or 0),
                all_pages=bool(payload.get("all_pages") or False),
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
                all_pages=bool(payload.get("all_pages") if payload.get("all_pages") is not None else True),
            )
        if action == "video_comment_replies":
            return self.get_video_comment_replies(
                item_id=payload["item_id"],
                comment_id=payload["comment_id"],
                max_items=payload.get("max_items"),
                page_size=int(payload.get("page_size", 20)),
                cursor=int(payload.get("cursor") or 0),
                all_pages=bool(payload.get("all_pages") if payload.get("all_pages") is not None else True),
            )
        if action == "my_sec_uid":
            sec_uid = self.get_my_sec_uid()
            return {"status": "ok", "source": self.manifest.id, "sec_user_id": sec_uid, "sec_uid": sec_uid}
        if action == "user_search":
            raise ValueError("Douyin_Spider provider does not implement user_search; keep using legacy TikHub.")
        raise ValueError(f"Unsupported Douyin_Spider action: {action}")

    def status(self) -> dict[str, Any]:
        if self._uses_sidecar():
            sidecar_status: dict[str, Any] = {}
            try:
                sidecar_status = self._sidecar_status()
                errors = sidecar_status.get("errors") if isinstance(sidecar_status.get("errors"), list) else []
            except Exception as exc:
                errors = [f"Douyin Spider sidecar unavailable: {self.sidecar_base_url} ({type(exc).__name__}: {exc})"]
            return {
                "id": self.manifest.id,
                "name": self.manifest.name,
                "repo_url": self.manifest.repo_url,
                "ready": not errors,
                "errors": errors,
                "provider": "douyin-spider",
                "execution_mode": "sidecar",
                "sidecar_base_url": self.sidecar_base_url,
                "sidecar": sidecar_status,
                "search_supported": False,
            }

        errors = self.validate_config()
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "repo_url": self.manifest.repo_url,
            "ready": not errors,
            "errors": errors,
            "provider": "douyin-spider",
            "execution_mode": "inprocess",
            "vendor_path": str(self.vendor_path),
            "output_dir": str(self.output_dir),
            "cookie_env": self.cookie_env,
            "has_cookie": bool(self.cookie),
            "search_supported": False,
        }

    def get_user_profile(self, sec_user_id: str) -> dict[str, Any]:
        if self._uses_sidecar():
            return self._sidecar_run({"action": "user_profile", "sec_user_id": sec_user_id})
        sec_user_id = str(sec_user_id or "").strip()
        if not sec_user_id:
            raise ValueError("Douyin_Spider user profile requires sec_user_id.")
        user_url = self._user_url(sec_user_id)
        raw = self._call("get_user_info", lambda api, auth: api.get_user_info(auth, user_url), {"sec_user_id": sec_user_id})
        user_raw = raw.get("user") if isinstance(raw.get("user"), dict) else {}
        normalized = self._normalize_user(user_raw)
        return {
            "status": "ok",
            "source": self.manifest.id,
            "request": {"sec_user_id": sec_user_id, "user_url": user_url},
            "raw": raw,
            "user": normalized,
            "profile": normalized,
            "sec_user_id": normalized.get("sec_user_id") or sec_user_id,
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
        if self._uses_sidecar():
            return self._sidecar_run(
                {
                    "action": "user_videos",
                    "sec_user_id": sec_user_id,
                    "unique_id": unique_id,
                    "max_cursor": max_cursor,
                    "count": count,
                    "sort_type": sort_type,
                    "filter_type": filter_type,
                }
            )
        sec = str(sec_user_id or "").strip()
        if not sec:
            raise ValueError("Douyin_Spider user videos requires sec_user_id.")
        target_count = max(1, min(int(count or 20), 10000))
        user_url = self._user_url(sec)
        current_cursor = int(max_cursor or 0)
        raw_pages: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        pagination: dict[str, Any] = {}

        while len(items) < target_count:
            raw = self._call(
                "get_user_work_info",
                lambda api, auth, cursor=current_cursor: api.get_user_work_info(auth, user_url, str(cursor)),
                {"sec_user_id": sec, "max_cursor": current_cursor},
            )
            raw_pages.append(raw)
            page_items = raw.get("aweme_list") if isinstance(raw.get("aweme_list"), list) else []
            items.extend(self._normalize_video(item) for item in page_items if isinstance(item, dict))
            pagination = {
                "max_cursor": raw.get("max_cursor"),
                "min_cursor": raw.get("min_cursor"),
                "cursor": raw.get("max_cursor"),
                "has_more": raw.get("has_more"),
            }
            next_cursor = self._to_int(raw.get("max_cursor"))
            if not page_items or not self._has_more(raw.get("has_more")) or next_cursor in [None, current_cursor]:
                break
            current_cursor = int(next_cursor)

        normalized_items = items[:target_count]
        return {
            "status": "ok",
            "source": self.manifest.id,
            "endpoint": "DouyinAPI.get_user_work_info",
            "request": {
                "sec_user_id": sec,
                "unique_id": str(unique_id or ""),
                "max_cursor": int(max_cursor or 0),
                "count": target_count,
                "sort_type": int(sort_type or 0),
                "filter_type": int(filter_type if filter_type is not None else sort_type or 0),
            },
            "raw": raw_pages[-1] if raw_pages else {},
            "raw_pages": raw_pages,
            "items": normalized_items,
            "pagination": pagination,
            "normalized": pagination,
            "next_cursor": pagination.get("max_cursor"),
            "has_more": self._has_more(pagination.get("has_more")),
        }

    def get_work_detail(self, work_url: str, region: str = "US") -> dict[str, Any]:
        if self._uses_sidecar():
            return self._sidecar_run({"action": "work_detail", "work_url": work_url, "region": region})
        aweme_id = self.get_aweme_id(work_url)
        result = self.get_one_video(aweme_id, region=region)
        video = result.get("video") if isinstance(result.get("video"), dict) else {}
        return {**result, "aweme_id": aweme_id, "detail": video}

    def get_one_video(self, aweme_id: str, region: str = "US", *, prefer_cache: bool = True) -> dict[str, Any]:
        if self._uses_sidecar():
            return self._sidecar_run({"action": "one_video", "aweme_id": aweme_id, "region": region, "prefer_cache": prefer_cache})
        aweme_id = str(aweme_id or "").strip()
        if not aweme_id:
            raise ValueError("Douyin_Spider one video requires aweme_id.")
        work_url = self._work_url(aweme_id)
        raw = self._call("get_work_info", lambda api, auth: api.get_work_info(auth, work_url), {"aweme_id": aweme_id})
        aweme = raw.get("aweme_detail") if isinstance(raw.get("aweme_detail"), dict) else {}
        video = self._normalize_video(aweme) if aweme else {}
        return {
            "status": "ok",
            "source": self.manifest.id,
            "request": {"aweme_id": aweme_id, "region": region, "work_url": work_url},
            "raw": raw,
            "video": video,
            "detail": video,
            "aweme_id": video.get("aweme_id") or aweme_id,
            "download_urls": self._extract_download_urls(aweme),
        }

    def get_favorite_videos(
        self,
        max_items: int | str | None = None,
        page_size: int = 18,
        max_cursor: int = 0,
        all_pages: bool = False,
    ) -> dict[str, Any]:
        if self._uses_sidecar():
            return self._sidecar_run(
                {
                    "action": "favorite_items",
                    "max_items": max_items,
                    "page_size": page_size,
                    "max_cursor": max_cursor,
                    "all_pages": all_pages,
                }
            )
        limit = None if max_items in [None, "", 0, "0", "all"] else int(max_items)
        request_count = max(1, min(int(page_size or 18), 50))
        current_cursor = int(max_cursor or 0)
        items: list[dict[str, Any]] = []
        raw_pages: list[dict[str, Any]] = []
        pagination: dict[str, Any] = {}
        sec_uid = self.get_my_sec_uid()

        while limit is None or len(items) < limit:
            remaining = request_count if limit is None else max(1, min(request_count, limit - len(items)))
            raw = self._request_user_favorite(sec_uid=sec_uid, max_cursor=current_cursor, count=remaining)
            raw_pages.append(raw)
            page_items = raw.get("aweme_list") if isinstance(raw.get("aweme_list"), list) else []
            items.extend(self._normalize_video(item) for item in page_items if isinstance(item, dict))
            pagination = {
                "max_cursor": raw.get("max_cursor"),
                "cursor": raw.get("max_cursor") or raw.get("cursor"),
                "has_more": raw.get("has_more"),
            }
            next_cursor = self._to_int(pagination.get("max_cursor") or pagination.get("cursor"))
            if not page_items or not all_pages or (limit is not None and len(items) >= limit) or not self._has_more(raw.get("has_more")) or next_cursor in [None, current_cursor]:
                break
            current_cursor = int(next_cursor)

        normalized_items = items[:limit] if limit is not None else items
        return {
            "status": "ok",
            "source": self.manifest.id,
            "endpoint": "DouyinAPI.favorite",
            "items": normalized_items,
            "count": len(normalized_items),
            "next_cursor": pagination.get("max_cursor") or pagination.get("cursor") or current_cursor,
            "has_more": self._has_more(pagination.get("has_more")),
            "pagination": pagination,
            "raw": raw_pages[-1] if raw_pages else {},
            "raw_pages": raw_pages,
        }

    def download_favorite_videos(self, max_items: int = 18, page_size: int = 18) -> dict[str, Any]:
        if self._uses_sidecar():
            return self._sidecar_run({"action": "download_favorites", "max_items": max_items, "page_size": page_size})
        favorite_data = self.get_favorite_videos(max_items=max_items, page_size=page_size, all_pages=True)
        videos = [item for item in favorite_data.get("items", []) if isinstance(item, dict)]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []
        skipped = []

        for index, item in enumerate(videos, start=1):
            aweme_id = str(item.get("aweme_id") or item.get("id") or index)
            urls = self._downloadable_video_urls(item)
            if not urls:
                skipped.append({"aweme_id": aweme_id, "reason": "missing_download_url"})
                continue
            try:
                saved_path, used_url = self._download_media_urls(urls, aweme_id, item=item)
            except Exception as exc:
                skipped.append({"aweme_id": aweme_id, "reason": f"{type(exc).__name__}: {exc}"})
                continue
            downloaded.append({"aweme_id": aweme_id, "path": saved_path, "source_url": used_url, "source_urls": urls})

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
        manifest_path = self.output_dir / "spider_favorites_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest

    def get_video_comments(
        self,
        aweme_id: str,
        max_items: int | str | None = 100,
        page_size: int = 20,
        cursor: int = 0,
        all_pages: bool = True,
    ) -> dict[str, Any]:
        if self._uses_sidecar():
            return self._sidecar_run(
                {
                    "action": "video_comments",
                    "aweme_id": aweme_id,
                    "max_items": max_items,
                    "page_size": page_size,
                    "cursor": cursor,
                    "all_pages": all_pages,
                }
            )
        aweme_id = str(aweme_id or "").strip()
        if not aweme_id:
            raise ValueError("Douyin_Spider comments requires aweme_id.")
        limit = None if max_items in [None, "", 0, "0", "all"] else int(max_items)
        current_cursor = int(cursor or 0)
        work_url = self._work_url(aweme_id)
        items: list[dict[str, Any]] = []
        raw_pages: list[dict[str, Any]] = []
        pagination: dict[str, Any] = {}

        while limit is None or len(items) < limit:
            try:
                raw = self._call(
                    "get_work_out_comment",
                    lambda api, auth, page_cursor=current_cursor: api.get_work_out_comment(auth, work_url, str(page_cursor)),
                    {"aweme_id": aweme_id, "cursor": current_cursor},
                )
            except DouyinSpiderApiError as exc:
                if self._is_empty_json_response_error(exc):
                    raise self._empty_comment_response_error(
                        exc,
                        aweme_id=aweme_id,
                        cursor=current_cursor,
                        method="get_work_out_comment",
                    ) from exc
                raise
            raw_pages.append(raw)
            page_items = raw.get("comments") if isinstance(raw.get("comments"), list) else []
            items.extend(item for item in page_items if isinstance(item, dict))
            pagination = {
                "cursor": raw.get("cursor"),
                "next_cursor": raw.get("cursor"),
                "has_more": raw.get("has_more"),
                "total": raw.get("total"),
            }
            next_cursor = self._to_int(raw.get("cursor"))
            if not page_items or not all_pages or (limit is not None and len(items) >= limit) or not self._has_more(raw.get("has_more")) or next_cursor in [None, current_cursor]:
                break
            current_cursor = int(next_cursor)

        normalized_items = items[:limit] if limit is not None else items
        return {
            "status": "ok",
            "source": self.manifest.id,
            "endpoint": "DouyinAPI.get_work_out_comment",
            "aweme_id": aweme_id,
            "request": {"aweme_id": aweme_id, "cursor": cursor, "count": page_size},
            "items": normalized_items,
            "count": len(normalized_items),
            "next_cursor": pagination.get("cursor") or current_cursor,
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
        if self._uses_sidecar():
            return self._sidecar_run(
                {
                    "action": "video_comment_replies",
                    "item_id": item_id,
                    "comment_id": comment_id,
                    "max_items": max_items,
                    "page_size": page_size,
                    "cursor": cursor,
                    "all_pages": all_pages,
                }
            )
        item_id = str(item_id or "").strip()
        comment_id = str(comment_id or "").strip()
        if not item_id:
            raise ValueError("Douyin_Spider replies requires item_id.")
        if not comment_id:
            raise ValueError("Douyin_Spider replies requires comment_id.")
        limit = None if max_items in [None, "", 0, "0", "all"] else int(max_items)
        current_cursor = int(cursor or 0)
        request_count = max(1, min(int(page_size or 20), 50))
        comment = {"aweme_id": item_id, "cid": comment_id}
        items: list[dict[str, Any]] = []
        raw_pages: list[dict[str, Any]] = []
        pagination: dict[str, Any] = {}

        while limit is None or len(items) < limit:
            remaining = request_count if limit is None else max(1, min(request_count, limit - len(items)))
            try:
                raw = self._call(
                    "get_work_inner_comment",
                    lambda api, auth, page_cursor=current_cursor, count=remaining: api.get_work_inner_comment(auth, comment, str(page_cursor), str(count)),
                    {"item_id": item_id, "comment_id": comment_id, "cursor": current_cursor, "count": remaining},
                )
            except DouyinSpiderApiError as exc:
                if self._is_empty_json_response_error(exc):
                    raise self._empty_comment_response_error(
                        exc,
                        aweme_id=item_id,
                        cursor=current_cursor,
                        method="get_work_inner_comment",
                        comment_id=comment_id,
                    ) from exc
                raise
            raw_pages.append(raw)
            page_items = raw.get("comments") if isinstance(raw.get("comments"), list) else []
            items.extend(item for item in page_items if isinstance(item, dict))
            pagination = {
                "cursor": raw.get("cursor"),
                "next_cursor": raw.get("cursor"),
                "has_more": raw.get("has_more"),
                "total": raw.get("total"),
            }
            next_cursor = self._to_int(raw.get("cursor"))
            if not page_items or not all_pages or (limit is not None and len(items) >= limit) or not self._has_more(raw.get("has_more")) or next_cursor in [None, current_cursor]:
                break
            current_cursor = int(next_cursor)

        normalized_items = items[:limit] if limit is not None else items
        return {
            "status": "ok",
            "source": self.manifest.id,
            "endpoint": "DouyinAPI.get_work_inner_comment",
            "item_id": item_id,
            "comment_id": comment_id,
            "request": {"item_id": item_id, "comment_id": comment_id, "cursor": cursor, "count": page_size},
            "items": normalized_items,
            "count": len(normalized_items),
            "next_cursor": pagination.get("cursor") or current_cursor,
            "has_more": self._has_more(pagination.get("has_more")),
            "pagination": pagination,
            "raw": raw_pages[-1] if raw_pages else {},
            "raw_pages": raw_pages,
        }

    def get_my_sec_uid(self) -> str:
        if self._uses_sidecar():
            result = self._sidecar_run({"action": "my_sec_uid"})
            return str(result.get("sec_user_id") or result.get("sec_uid") or "")
        return str(self._call("get_my_sec_uid", lambda api, auth: api.get_my_sec_uid(auth), {}) or "")

    def get_sec_user_id(self, user_url: str) -> str:
        value = str(user_url or "").strip()
        if not value:
            raise ValueError("Douyin_Spider get_sec_user_id requires user_url.")
        if self._looks_like_sec_user_id(value):
            return value
        parsed = self._extract_sec_user_id_from_url(value)
        if parsed:
            return parsed
        resolved = self._resolve_redirect_url(value)
        parsed = self._extract_sec_user_id_from_url(resolved)
        if parsed:
            return parsed
        raise ValueError("Unable to extract sec_user_id from user_url.")

    def get_aweme_id(self, work_url: str) -> str:
        value = str(work_url or "").strip()
        if not value:
            raise ValueError("Douyin_Spider get_aweme_id requires work_url.")
        if re.fullmatch(r"\d{5,}", value):
            return value
        parsed = self._extract_aweme_id_from_url(value)
        if parsed:
            return parsed
        resolved = self._resolve_redirect_url(value)
        parsed = self._extract_aweme_id_from_url(resolved)
        if parsed:
            return parsed
        raise ValueError("Unable to extract aweme_id from work_url.")

    def _uses_sidecar(self) -> bool:
        return self.execution_mode == "sidecar"

    def _sidecar_client(self) -> DouyinSpiderSidecarClient:
        if self._sidecar is None:
            self._sidecar = DouyinSpiderSidecarClient(self.sidecar_base_url, timeout=self.timeout)
        return self._sidecar

    def _sidecar_status(self) -> dict[str, Any]:
        return self._sidecar_client().status()

    def _sidecar_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._sidecar_client().run(payload)
        except DouyinSpiderApiError:
            raise
        except Exception as exc:
            raise DouyinSpiderApiError(
                method=f"sidecar:{payload.get('action') or 'run'}",
                request_payload=self._redact_request(payload),
                message=f"Douyin Spider sidecar request failed: {exc}",
                cause=exc,
            ) from exc

    def _call(self, method: str, callback: Any, request_payload: dict[str, Any]) -> Any:
        try:
            modules = self._load_vendor_modules()
            auth = self._auth(modules)
            api = modules.api_cls()
            return callback(api, auth)
        except DouyinSpiderApiError:
            raise
        except Exception as exc:
            raise DouyinSpiderApiError(
                method=method,
                request_payload=self._redact_request(request_payload),
                message=f"Douyin_Spider {method} failed: {exc}",
                cause=exc,
            ) from exc

    def _auth(self, modules: DouyinSpiderModules) -> Any:
        if not self.cookie:
            raise DouyinSpiderApiError(method="auth", message=f"Missing Douyin cookie env: {self.cookie_env}")
        auth = modules.auth_cls()
        auth.perepare_auth(self.cookie)
        return auth

    def _load_vendor_modules(self) -> DouyinSpiderModules:
        if self._modules is not None:
            return self._modules
        errors = self.validate_config()
        if errors:
            raise DouyinSpiderApiError(method="load_vendor", message="; ".join(errors))

        # protobuf-to-dict still references Python 2 names under Python 3.13.
        if not hasattr(builtins, "long"):
            builtins.long = int  # type: ignore[attr-defined]
        if not hasattr(builtins, "unicode"):
            builtins.unicode = str  # type: ignore[attr-defined]

        vendor = str(self.vendor_path)
        if vendor not in sys.path:
            sys.path.insert(0, vendor)
        try:
            from builder.auth import DouyinAuth
            from builder.header import HeaderBuilder, HeaderType
            from builder.params import Params
            from dy_apis.douyin_api import DouyinAPI
        except Exception as exc:
            raise DouyinSpiderApiError(method="load_vendor", message=f"Failed to import Douyin_Spider vendor: {exc}", cause=exc) from exc

        self._modules = DouyinSpiderModules(
            auth_cls=DouyinAuth,
            api_cls=DouyinAPI,
            header_builder=HeaderBuilder,
            header_type=HeaderType,
            params_cls=Params,
        )
        return self._modules

    def _request_user_favorite(self, *, sec_uid: str, max_cursor: int, count: int) -> dict[str, Any]:
        modules = self._load_vendor_modules()
        auth = self._auth(modules)
        headers = modules.header_builder.build(modules.header_type.GET)
        refer = f"https://www.douyin.com/user/{sec_uid}?showTab=like"
        headers.set_referer(refer)
        params = modules.params_cls()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("sec_user_id", sec_uid)
        params.add_param("max_cursor", str(max_cursor))
        params.add_param("min_cursor", "0")
        params.add_param("whale_cut_token", "")
        params.add_param("cut_version", "1")
        params.add_param("count", str(count))
        params.add_param("publish_video_strategy_type", "2")
        params.add_param("update_version_code", "170400")
        params.add_param("pc_client_type", "1")
        params.add_param("version_code", "170400")
        params.add_param("version_name", "17.4.0")
        params.add_param("cookie_enabled", "true")
        params.add_param("screen_width", "1707")
        params.add_param("screen_height", "960")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_platform", "Win32")
        params.add_param("browser_name", "Edge")
        params.add_param("browser_version", "125.0.0.0")
        params.add_param("browser_online", "true")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", "125.0.0.0")
        params.add_param("os_name", "Windows")
        params.add_param("os_version", "10")
        params.add_param("cpu_core_num", "32")
        params.add_param("device_memory", "8")
        params.add_param("platform", "PC")
        params.add_param("downlink", "10")
        params.add_param("effective_type", "4g")
        params.add_param("round_trip_time", "100")
        params.with_web_id(auth=auth, url=refer)
        params.add_param("verifyFp", auth.cookie.get("s_v_web_id", ""))
        params.add_param("fp", auth.cookie.get("s_v_web_id", ""))
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        try:
            response = requests.get(
                "https://www.douyin.com/aweme/v1/web/aweme/favorite/",
                params=params.get(),
                headers=headers.get(),
                cookies=auth.cookie,
                verify=False,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise DouyinSpiderApiError(
                method="favorite",
                request_payload={"sec_user_id": sec_uid, "max_cursor": max_cursor, "count": count},
                message=f"Douyin_Spider favorite request failed: {exc}",
                cause=exc,
            ) from exc

    def _normalize_user(self, item: dict[str, Any]) -> dict[str, Any]:
        item = item if isinstance(item, dict) else {}
        sec_uid = item.get("sec_uid") or item.get("secUid") or item.get("sec_user_id")
        uid = item.get("uid") or item.get("id") or item.get("user_id")
        like_count = self._to_int(item.get("total_favorited") or item.get("like_count") or item.get("digg_count"))
        return {
            "sec_uid": sec_uid,
            "sec_user_id": sec_uid,
            "uid": uid,
            "user_id": uid,
            "unique_id": item.get("unique_id") or item.get("short_id"),
            "nickname": item.get("nickname") or "",
            "signature": item.get("signature") or item.get("desc") or "",
            "ip_location": item.get("ip_location") or item.get("location") or "",
            "avatar": self._first_url(item.get("avatar_thumb")) or self._first_url(item.get("avatar_medium")) or self._first_url(item.get("avatar_larger")),
            "follower_count": self._to_int(item.get("follower_count") or item.get("fans_count")),
            "following_count": self._to_int(item.get("following_count") or item.get("follow_count")),
            "like_count": like_count,
            "total_favorited": like_count,
            "aweme_count": self._to_int(item.get("aweme_count") or item.get("video_count")),
            "recent_update_at": self._to_int(item.get("last_aweme_time") or item.get("last_post_time")),
            "last_post_at": self._to_int(item.get("last_aweme_time") or item.get("last_post_time")),
            "verified": bool(item.get("is_verified") or item.get("custom_verify") or item.get("enterprise_verify_reason")),
            "is_private": bool(item.get("is_private_account") or item.get("secret")),
            "raw": item,
        }

    def _normalize_video(self, item: dict[str, Any]) -> dict[str, Any]:
        item = item if isinstance(item, dict) else {}
        stats = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        play_url = (
            self._first_url(video.get("play_addr"))
            or self._first_url(video.get("play_addr_h264"))
            or self._first_url(video.get("play_addr_bytevc1"))
        )
        download_url = play_url or self._first_url(video.get("download_addr"))
        cover_url = self._first_url(video.get("cover")) or self._first_url(video.get("origin_cover")) or self._first_url(video.get("dynamic_cover"))
        images = item.get("images") if isinstance(item.get("images"), list) else []
        return {
            "aweme_id": str(item.get("aweme_id") or item.get("id") or ""),
            "desc": item.get("desc") or item.get("title") or "",
            "create_time": self._to_int(item.get("create_time")),
            "author": self._normalize_user(item.get("author", {})) if isinstance(item.get("author"), dict) else None,
            "video": video,
            "statistics": stats,
            "digg_count": self._to_int(stats.get("digg_count") or stats.get("like_count")),
            "comment_count": self._to_int(stats.get("comment_count")),
            "share_count": self._to_int(stats.get("share_count")),
            "collect_count": self._to_int(stats.get("collect_count") or stats.get("favorite_count")),
            "play_count": self._to_int(stats.get("play_count") or item.get("play_count")) or 1,
            "is_top": bool(item.get("is_top") or item.get("is_pinned") or item.get("is_top_item")),
            "cover_url": cover_url,
            "play_url": play_url,
            "download_url": download_url,
            "source_video_url": play_url or download_url,
            "download_urls": self._extract_download_urls(item),
            "images": [self._first_url(image) for image in images if self._first_url(image)],
            "share_url": self._work_url(str(item.get("aweme_id") or item.get("id") or "")) if item.get("aweme_id") or item.get("id") else "",
            "raw": item,
        }

    def _extract_download_urls(self, aweme: dict[str, Any]) -> dict[str, Any]:
        video = aweme.get("video") if isinstance(aweme.get("video"), dict) else {}
        uri = self._video_uri(video)
        aweme_play = f"https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio=1080p&line=0" if uri else ""
        aweme_playwm = f"https://aweme.snssdk.com/aweme/v1/playwm/?video_id={uri}&radio=1080p&line=0" if uri else ""
        return {
            "play_addr": self._first_url(video.get("play_addr")),
            "play_addr_h264": self._first_url(video.get("play_addr_h264")),
            "play_addr_bytevc1": self._first_url(video.get("play_addr_bytevc1")),
            "download_addr": self._first_url(video.get("download_addr")),
            "aweme_play": aweme_play,
            "aweme_playwm": aweme_playwm,
        }

    def _downloadable_video_url(self, item: dict[str, Any]) -> str:
        urls = self._downloadable_video_urls(item)
        return urls[0] if urls else ""

    def _downloadable_video_urls(self, item: dict[str, Any]) -> list[str]:
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        raw_video = raw.get("video") if isinstance(raw.get("video"), dict) else {}
        download_urls = item.get("download_urls") if isinstance(item.get("download_urls"), dict) else {}
        return self._unique_urls(
            [
                item.get("play_url"),
                item.get("video_url"),
                download_urls.get("play_addr"),
                download_urls.get("play_addr_h264"),
                download_urls.get("play_addr_bytevc1"),
                download_urls.get("aweme_play"),
                self._all_urls(video.get("play_addr")),
                self._all_urls(video.get("play_addr_h264")),
                self._all_urls(video.get("play_addr_bytevc1")),
                self._all_urls(raw_video.get("play_addr")),
                self._all_urls(raw_video.get("play_addr_h264")),
                self._all_urls(raw_video.get("play_addr_bytevc1")),
                item.get("source_video_url"),
                item.get("download_url"),
                download_urls.get("download_addr"),
                self._all_urls(video.get("download_addr")),
                self._all_urls(raw_video.get("download_addr")),
            ]
        )

    def _download_media_url(self, url: str, fallback_name: str) -> str:
        headers = self._download_headers(fallback_name, url)
        response = requests.get(url, headers=headers, timeout=300, stream=True)
        response.raise_for_status()
        file_name = self._download_filename(response, fallback_name)
        target = self._unique_download_path(file_name)
        partial = target.with_name(f"{target.name}.part")
        partial.unlink(missing_ok=True)
        downloaded = 0
        try:
            with partial.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        file.write(chunk)
                        downloaded += len(chunk)
            if downloaded <= 0:
                raise RuntimeError("Media download response returned no content.")
            partial.replace(target)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        finally:
            response.close()
        return str(target)

    def _download_media_urls(self, urls: list[str], fallback_name: str, *, item: dict[str, Any]) -> tuple[str, str]:
        attempted: set[str] = set()
        last_error: Exception | None = None
        for url in urls:
            if url in attempted:
                continue
            attempted.add(url)
            try:
                return self._download_media_url(url, fallback_name), url
            except Exception as exc:
                last_error = exc

        refreshed_urls = self._refresh_downloadable_video_urls(fallback_name, item)
        for url in refreshed_urls:
            if url in attempted:
                continue
            attempted.add(url)
            try:
                return self._download_media_url(url, fallback_name), url
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise RuntimeError("No downloadable media URL succeeded.")

    def _refresh_downloadable_video_urls(self, aweme_id: str, item: dict[str, Any]) -> list[str]:
        if not str(aweme_id or "").strip():
            return []
        try:
            refreshed = self.get_one_video(str(aweme_id), prefer_cache=False)
        except Exception:
            return []
        refreshed_video = refreshed.get("video") if isinstance(refreshed.get("video"), dict) else {}
        download_urls = refreshed.get("download_urls") if isinstance(refreshed.get("download_urls"), dict) else {}
        merged = {
            **item,
            **refreshed_video,
            "download_urls": download_urls or refreshed_video.get("download_urls") or item.get("download_urls"),
            "raw": refreshed.get("raw") or refreshed_video.get("raw") or item.get("raw"),
        }
        return self._downloadable_video_urls(merged)

    def _download_headers(self, fallback_name: str, url: str) -> dict[str, str]:
        referer = self._work_url(fallback_name) if str(fallback_name or "").strip().isdigit() else "https://www.douyin.com/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
            ),
            "Referer": referer,
            "Origin": "https://www.douyin.com",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Sec-Fetch-Dest": "video",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "cross-site",
            "Connection": "keep-alive",
        }
        range_header = str(os.getenv("DOUYIN_DOWNLOAD_RANGE_HEADER") or "bytes=0-").strip()
        if range_header:
            headers["Range"] = range_header
        if self.cookie and self._should_send_cookie_to_media(url):
            headers["Cookie"] = self.cookie
        return headers

    @staticmethod
    def _should_send_cookie_to_media(url: str) -> bool:
        host = urlparse(str(url or "")).hostname or ""
        return any(marker in host for marker in ("douyin", "zjcdn", "byte", "bytedance", "snssdk"))

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

    def _resolve_redirect_url(self, url: str) -> str:
        try:
            response = requests.get(url, allow_redirects=True, timeout=15)
            return response.url or url
        except requests.RequestException:
            return url

    @staticmethod
    def _extract_sec_user_id_from_url(url: str) -> str:
        match = re.search(r"/user/([^/?#]+)", url)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_aweme_id_from_url(url: str) -> str:
        for pattern in (r"/video/(\d+)", r"modal_id=(\d+)", r"aweme_id=(\d+)"):
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _sanitize_cookie(value: Any) -> str:
        cookie = str(value or "").strip().strip('"').strip("'")
        return cookie.replace("\\n", "").replace("\\r", "").replace("\r", "").replace("\n", "").strip()

    @staticmethod
    def _resolve_vendor_path(value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    @classmethod
    def _select_vendor_path(cls, value: str) -> Path:
        configured = cls._resolve_vendor_path(value)
        default = cls._resolve_vendor_path(str(DEFAULT_VENDOR_DIR))
        if configured.exists() or configured == default:
            return configured
        if default.exists():
            return default
        return configured

    @staticmethod
    def _redact_request(value: dict[str, Any]) -> dict[str, Any]:
        return {
            key: ("***" if str(key).lower() in {"cookie", "authorization", "token", "api_key", "apikey"} else item)
            for key, item in value.items()
        }

    @staticmethod
    def _user_url(sec_user_id: str) -> str:
        return f"https://www.douyin.com/user/{sec_user_id}"

    @staticmethod
    def _work_url(aweme_id: str) -> str:
        return f"https://www.douyin.com/video/{aweme_id}"

    @staticmethod
    def _looks_like_sec_user_id(value: Any) -> bool:
        text = str(value or "")
        return text.startswith("MS4") or len(text) > 40

    @classmethod
    def _first_url(cls, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            for item in value:
                url = cls._first_url(item)
                if url:
                    return url
        if isinstance(value, dict):
            for key in ("url_list", "url", "uri", "src", "href"):
                url = cls._first_url(value.get(key))
                if url:
                    return url
        return ""

    @classmethod
    def _all_urls(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value] if value.startswith(("http://", "https://")) else []
        if isinstance(value, list):
            urls: list[str] = []
            for item in value:
                urls.extend(cls._all_urls(item))
            return urls
        if isinstance(value, dict):
            urls: list[str] = []
            for key in ("url_list", "url_list_1", "urls", "url", "main_url", "backup_url"):
                if key in value:
                    urls.extend(cls._all_urls(value.get(key)))
            return urls
        return []

    @classmethod
    def _unique_urls(cls, values: list[Any]) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for value in values:
            candidates = value if isinstance(value, list) else cls._all_urls(value)
            for url in candidates:
                normalized = str(url or "").strip()
                if not normalized or normalized in seen:
                    continue
                urls.append(normalized)
                seen.add(normalized)
        return urls

    @staticmethod
    def _video_uri(video: dict[str, Any]) -> str:
        for key in ("play_addr", "play_addr_h264", "play_addr_bytevc1", "download_addr"):
            value = video.get(key)
            if isinstance(value, dict) and value.get("uri"):
                return str(value.get("uri") or "")
        return str(video.get("uri") or video.get("video_id") or "").strip()

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value in [None, ""]:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _has_more(value: Any) -> bool:
        return value in (True, 1, "1", "true", "True")

    @staticmethod
    def _is_empty_json_response_error(exc: Exception) -> bool:
        text = f"{type(exc).__name__}: {exc}"
        cause = getattr(exc, "cause", None)
        if cause is not None:
            text = f"{text} {type(cause).__name__}: {cause}"
        return "jsondecodeerror" in text.lower() and "expecting value" in text.lower()

    @staticmethod
    def _empty_comment_response_error(
        exc: DouyinSpiderApiError,
        *,
        aweme_id: str,
        cursor: int,
        method: str,
        comment_id: str = "",
    ) -> DouyinSpiderApiError:
        request = {"aweme_id": aweme_id, "cursor": cursor}
        if comment_id:
            request["comment_id"] = comment_id
        return DouyinSpiderApiError(
            method=method,
            request_payload=getattr(exc, "request_payload", None) or request,
            message=(
                "Douyin_Spider comment response was empty JSON; possible Douyin "
                "risk control or rate limit. Treating it as a failed comment fetch, "
                "not as zero comments."
            ),
            cause=getattr(exc, "cause", None),
        )
