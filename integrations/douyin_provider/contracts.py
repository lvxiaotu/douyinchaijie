from __future__ import annotations

from typing import Any, Protocol


class DouyinProvider(Protocol):
    def status(self) -> dict[str, Any]: ...

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]: ...

    def run(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def get_sec_user_id(self, user_url: str) -> str: ...

    def get_aweme_id(self, work_url: str) -> str: ...

    def get_user_profile(self, sec_user_id: str) -> dict[str, Any]: ...

    def get_user_videos(
        self,
        sec_user_id: str | None = None,
        unique_id: str | None = None,
        max_cursor: int = 0,
        count: int = 20,
        sort_type: int = 0,
        filter_type: int | None = None,
    ) -> dict[str, Any]: ...

    def get_work_detail(self, work_url: str, region: str = "US") -> dict[str, Any]: ...

    def get_one_video(self, aweme_id: str, region: str = "US", *, prefer_cache: bool = True) -> dict[str, Any]: ...

    def get_favorite_videos(
        self,
        max_items: int | str | None = None,
        page_size: int = 18,
        max_cursor: int = 0,
        all_pages: bool = False,
    ) -> dict[str, Any]: ...

    def download_favorite_videos(self, max_items: int = 18, page_size: int = 18) -> dict[str, Any]: ...

    def get_video_comments(
        self,
        aweme_id: str,
        max_items: int | str | None = 100,
        page_size: int = 20,
        cursor: int = 0,
        all_pages: bool = True,
    ) -> dict[str, Any]: ...

    def get_video_comment_replies(
        self,
        item_id: str,
        comment_id: str,
        max_items: int | str | None = 20,
        page_size: int = 20,
        cursor: int = 0,
        all_pages: bool = True,
    ) -> dict[str, Any]: ...

