from __future__ import annotations

from typing import Any

from integrations.base import IntegrationManifest


class FallbackDouyinProvider:
    manifest = IntegrationManifest(
        id="douyin-provider-fallback",
        name="Douyin Provider Fallback",
        description="Primary Douyin provider with legacy fallback.",
        tags=["douyin", "provider", "fallback"],
    )

    def __init__(self, primary: Any, fallback: Any, *, mode: str = "spider_first"):
        self.primary = primary
        self.fallback = fallback
        self.mode = mode

    def status(self) -> dict[str, Any]:
        primary_status = self._safe_status(self.primary)
        fallback_status = self._safe_status(self.fallback)
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "ready": bool(primary_status.get("ready") or fallback_status.get("ready")),
            "provider": "douyin-provider",
            "mode": self.mode,
            "primary": primary_status,
            "fallback": fallback_status,
            "search_provider": "legacy-tikhub",
        }

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]:
        primary_errors = self._safe_validate(self.primary, config)
        fallback_errors = self._safe_validate(self.fallback, config)
        if not primary_errors or not fallback_errors:
            return []
        return [f"primary: {error}" for error in primary_errors] + [f"fallback: {error}" for error in fallback_errors]

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("run", payload)

    def get_sec_user_id(self, user_url: str) -> str:
        return self._call("get_sec_user_id", user_url)

    def get_aweme_id(self, work_url: str) -> str:
        return self._call("get_aweme_id", work_url)

    def get_user_profile(self, sec_user_id: str) -> dict[str, Any]:
        return self._call("get_user_profile", sec_user_id)

    def get_user_videos(
        self,
        sec_user_id: str | None = None,
        unique_id: str | None = None,
        max_cursor: int = 0,
        count: int = 20,
        sort_type: int = 0,
        filter_type: int | None = None,
    ) -> dict[str, Any]:
        return self._call(
            "get_user_videos",
            sec_user_id=sec_user_id,
            unique_id=unique_id,
            max_cursor=max_cursor,
            count=count,
            sort_type=sort_type,
            filter_type=filter_type,
        )

    def get_work_detail(self, work_url: str, region: str = "US") -> dict[str, Any]:
        return self._call("get_work_detail", work_url, region=region)

    def get_one_video(self, aweme_id: str, region: str = "US", *, prefer_cache: bool = True) -> dict[str, Any]:
        return self._call("get_one_video", aweme_id, region=region, prefer_cache=prefer_cache)

    def get_favorite_videos(
        self,
        max_items: int | str | None = None,
        page_size: int = 18,
        max_cursor: int = 0,
        all_pages: bool = False,
    ) -> dict[str, Any]:
        return self._call("get_favorite_videos", max_items=max_items, page_size=page_size, max_cursor=max_cursor, all_pages=all_pages)

    def download_favorite_videos(self, max_items: int = 18, page_size: int = 18) -> dict[str, Any]:
        return self._call("download_favorite_videos", max_items=max_items, page_size=page_size)

    def get_video_comments(
        self,
        aweme_id: str,
        max_items: int | str | None = 100,
        page_size: int = 20,
        cursor: int = 0,
        all_pages: bool = True,
    ) -> dict[str, Any]:
        return self._call("get_video_comments", aweme_id=aweme_id, max_items=max_items, page_size=page_size, cursor=cursor, all_pages=all_pages)

    def get_video_comment_replies(
        self,
        item_id: str,
        comment_id: str,
        max_items: int | str | None = 20,
        page_size: int = 20,
        cursor: int = 0,
        all_pages: bool = True,
    ) -> dict[str, Any]:
        return self._call(
            "get_video_comment_replies",
            item_id=item_id,
            comment_id=comment_id,
            max_items=max_items,
            page_size=page_size,
            cursor=cursor,
            all_pages=all_pages,
        )

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        try:
            result = getattr(self.primary, method)(*args, **kwargs)
            return self._annotate(result, provider=self._provider_id(self.primary), fallback_used=False)
        except Exception as primary_exc:
            result = getattr(self.fallback, method)(*args, **kwargs)
            return self._annotate(
                result,
                provider=self._provider_id(self.fallback),
                fallback_used=True,
                primary_error=f"{type(primary_exc).__name__}: {primary_exc}",
            )

    def _annotate(
        self,
        result: Any,
        *,
        provider: str,
        fallback_used: bool,
        primary_error: str = "",
    ) -> Any:
        if not isinstance(result, dict):
            return result
        trace = {
            "mode": self.mode,
            "provider": provider,
            "primary": self._provider_id(self.primary),
            "fallback": self._provider_id(self.fallback),
            "fallback_used": fallback_used,
        }
        if primary_error:
            trace["primary_error"] = primary_error
        return {**result, "provider_trace": trace}

    @staticmethod
    def _provider_id(provider: Any) -> str:
        manifest = getattr(provider, "manifest", None)
        return str(getattr(manifest, "id", "") or provider.__class__.__name__)

    @classmethod
    def _safe_status(cls, provider: Any) -> dict[str, Any]:
        status = getattr(provider, "status", None)
        if callable(status):
            try:
                result = status()
                if isinstance(result, dict):
                    return result
            except Exception as exc:
                return {
                    "id": cls._provider_id(provider),
                    "ready": False,
                    "errors": [f"{type(exc).__name__}: {exc}"],
                }
        validate = getattr(provider, "validate_config", None)
        if callable(validate):
            try:
                errors = validate()
                return {
                    "id": cls._provider_id(provider),
                    "ready": not errors,
                    "errors": errors,
                }
            except Exception as exc:
                return {
                    "id": cls._provider_id(provider),
                    "ready": False,
                    "errors": [f"{type(exc).__name__}: {exc}"],
                }
        return {"id": cls._provider_id(provider), "ready": True, "errors": []}

    @staticmethod
    def _safe_validate(provider: Any, config: dict[str, Any] | None = None) -> list[str]:
        validate = getattr(provider, "validate_config", None)
        if not callable(validate):
            return []
        try:
            return validate(config)
        except TypeError:
            return validate()
        except Exception as exc:
            return [f"{type(exc).__name__}: {exc}"]

