from __future__ import annotations

import json
import os
import sys
import builtins
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from integrations.base import IntegrationAdapter, IntegrationManifest


DEFAULT_VENDOR_PATH = Path(__file__).parent / "vendor" / "DouYin_Spider"
DEFAULT_OUTPUT_DIR = Path("data/runtime/douyin/downloads")


def apply_python3_compatibility_patches() -> None:
    """Patch Python 2 names used by old third-party dependencies."""
    if not hasattr(builtins, "long"):
        builtins.long = int
    if not hasattr(builtins, "unicode"):
        builtins.unicode = str
    if not hasattr(builtins, "basestring"):
        builtins.basestring = (str, bytes)


def ensure_execjs_runtime_dirs(vendor_path: Path) -> None:
    # login.js does not need packages, but PyExecJS still requires cwd to exist.
    (vendor_path / "static" / "node_modules").mkdir(parents=True, exist_ok=True)


@contextmanager
def vendor_import_path(vendor_path: Path):
    apply_python3_compatibility_patches()
    ensure_execjs_runtime_dirs(vendor_path)
    resolved = str(vendor_path.resolve())
    sys.path.insert(0, resolved)
    try:
        yield
    finally:
        if resolved in sys.path:
            sys.path.remove(resolved)


class DouyinSpiderAdapter(IntegrationAdapter):
    manifest = IntegrationManifest(
        id="douyin-spider",
        name="DouYin Spider 数据采集",
        description="仅封装用户主页信息、作品详情、收藏列表视频下载。",
        repo_url="https://github.com/cv-cat/DouYin_Spider",
        tags=["douyin", "crawler", "download"],
        config_schema={
            "vendor_path": "DouYin_Spider 仓库本地路径",
            "cookie_env": "保存抖音 Cookie 的环境变量名，默认 DY_COOKIES",
            "output_dir": "收藏视频下载目录",
        },
    )

    def __init__(self, config: dict[str, Any] | None = None):
        load_dotenv()
        self.config = config or {}
        self.vendor_path = Path(
            self.config.get("vendor_path")
            or os.getenv("DOUYIN_SPIDER_VENDOR_PATH")
            or DEFAULT_VENDOR_PATH
        )
        self.cookie_env = self.config.get("cookie_env") or "DY_COOKIES"
        self.output_dir = Path(
            self.config.get("output_dir")
            or os.getenv("DOUYIN_OUTPUT_DIR")
            or DEFAULT_OUTPUT_DIR
        )

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]:
        cfg = {**self.config, **(config or {})}
        vendor_path = Path(
            cfg.get("vendor_path")
            or os.getenv("DOUYIN_SPIDER_VENDOR_PATH")
            or self.vendor_path
        )
        cookie_env = cfg.get("cookie_env") or self.cookie_env
        errors = []
        if not vendor_path.exists():
            errors.append(f"DouYin_Spider repo not found: {vendor_path}")
        if vendor_path.exists() and not (vendor_path / "node_modules" / "jsrsasign").exists():
            errors.append(f"Missing Node dependency jsrsasign. Run npm install jsrsasign in: {vendor_path}")
        if not os.getenv(cookie_env):
            errors.append(f"Missing env cookie: {cookie_env}")
        return errors

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "user_profile":
            return self.get_user_profile(payload["user_url"])
        if action == "work_detail":
            return self.get_work_detail(payload["work_url"])
        if action == "download_favorites":
            return self.download_favorite_videos(
                sec_user_id=payload.get("sec_user_id"),
                max_items=int(payload.get("max_items", 18)),
                page_size=str(payload.get("page_size", "18")),
            )
        raise ValueError(f"Unsupported Douyin action: {action}")

    def _auth(self):
        errors = self.validate_config()
        if errors:
            raise RuntimeError("; ".join(errors))
        cookie = os.getenv(self.cookie_env)
        if not cookie:
            raise RuntimeError(f"Set {self.cookie_env} in .env before using Douyin Spider.")
        with vendor_import_path(self.vendor_path):
            from builder.auth import DouyinAuth

            auth = DouyinAuth()
            auth.perepare_auth(cookie, "", "")
            return auth

    def get_user_profile(self, user_url: str) -> dict[str, Any]:
        with vendor_import_path(self.vendor_path):
            from dy_apis.douyin_api import DouyinAPI

            raw = DouyinAPI.get_user_info(self._auth(), user_url)
        user = raw.get("user", {})
        return {
            "status": "ok",
            "source": "DouYin_Spider",
            "raw": raw,
            "profile": {
                "sec_uid": user.get("sec_uid"),
                "uid": user.get("uid"),
                "nickname": user.get("nickname"),
                "signature": user.get("signature"),
                "avatar": (user.get("avatar_thumb") or {}).get("url_list", [None])[0],
                "following_count": user.get("following_count"),
                "follower_count": user.get("follower_count"),
                "total_favorited": user.get("total_favorited"),
                "aweme_count": user.get("aweme_count"),
            },
        }

    def get_work_detail(self, work_url: str) -> dict[str, Any]:
        with vendor_import_path(self.vendor_path):
            from dy_apis.douyin_api import DouyinAPI
            from utils.data_util import handle_work_info

            raw = DouyinAPI.get_work_info(self._auth(), work_url)
            detail = raw.get("aweme_detail") or raw.get("aweme") or {}
            normalized = handle_work_info(detail) if detail else None
        return {
            "status": "ok" if normalized else "empty",
            "source": "DouYin_Spider",
            "raw": raw,
            "detail": normalized,
        }

    def download_favorite_videos(
        self,
        sec_user_id: str | None = None,
        max_items: int = 18,
        page_size: str = "18",
    ) -> dict[str, Any]:
        with vendor_import_path(self.vendor_path):
            from dy_apis.douyin_api import DouyinAPI
            from utils.data_util import download_work, handle_work_info

            auth = self._auth()
            target_sec_uid = sec_user_id or DouyinAPI.get_my_sec_uid(auth)
            self.output_dir.mkdir(parents=True, exist_ok=True)

            downloaded = []
            skipped = []
            max_cursor = "0"
            while len(downloaded) + len(skipped) < max_items:
                page = self._fetch_favorites_page(auth, target_sec_uid, max_cursor, page_size)
                aweme_list = page.get("aweme_list") or []
                for aweme in aweme_list:
                    if len(downloaded) + len(skipped) >= max_items:
                        break
                    work = handle_work_info(aweme)
                    if work.get("work_type") != "视频":
                        skipped.append({"work_id": work.get("work_id"), "reason": "not_video"})
                        continue
                    saved_path = download_work(work, str(self.output_dir), "media-video")
                    downloaded.append({"work_id": work.get("work_id"), "path": saved_path, "title": work.get("title")})
                if page.get("has_more") != 1 or not aweme_list:
                    break
                max_cursor = str(page.get("max_cursor", "0"))

        manifest_path = self.output_dir / "favorites_manifest.json"
        manifest = {
            "status": "ok",
            "sec_user_id": target_sec_uid,
            "downloaded": downloaded,
            "skipped": skipped,
            "output_dir": str(self.output_dir),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest

    def _fetch_favorites_page(self, auth, sec_user_id: str, max_cursor: str, count: str) -> dict[str, Any]:
        with vendor_import_path(self.vendor_path):
            from builder.header import HeaderBuilder, HeaderType
            from builder.params import Params

            refer = f"https://www.douyin.com/user/{sec_user_id}?showTab=like"
            headers = HeaderBuilder().build(HeaderType.GET)
            headers.set_referer(refer)
            params = Params()
            params.add_param("device_platform", "webapp")
            params.add_param("aid", "6383")
            params.add_param("channel", "channel_pc_web")
            params.add_param("sec_user_id", sec_user_id)
            params.add_param("max_cursor", max_cursor)
            params.add_param("min_cursor", "0")
            params.add_param("count", count)
            params.add_param("publish_video_strategy_type", "2")
            params.add_param("pc_client_type", "1")
            params.add_param("version_code", "170400")
            params.add_param("version_name", "17.4.0")
            params.add_param("cookie_enabled", "true")
            params.with_web_id(auth=auth, url=refer)
            params.add_param("verifyFp", auth.cookie["s_v_web_id"])
            params.add_param("fp", auth.cookie["s_v_web_id"])
            params.add_param("msToken", auth.msToken)
            params.with_a_bogus()

            response = requests.get(
                "https://www.douyin.com/aweme/v1/web/aweme/favorite/",
                params=params.get(),
                headers=headers.get(),
                cookies=auth.cookie,
                timeout=30,
                verify=False,
            )
            response.raise_for_status()
            return response.json()
