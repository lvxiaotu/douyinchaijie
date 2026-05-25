from typing import Any
from urllib.parse import unquote, urlparse
import re
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.app.error_log_store import write_error_log
from integrations.ai_video_analysis.evidence_pipeline import VIDEO_URL_REFRESH_STATUS_CODES, VideoEvidencePipeline

router = APIRouter(prefix="/api/media", tags=["media"])

DEFAULT_REFERER = "https://www.douyin.com/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36"
)


def _proxy_headers(response: requests.Response) -> dict[str, str]:
    headers = {
        "Accept-Ranges": response.headers.get("accept-ranges") or "bytes",
        "Cache-Control": "private, max-age=300",
    }
    for source, target in (
        ("content-length", "Content-Length"),
        ("content-range", "Content-Range"),
        ("etag", "ETag"),
        ("last-modified", "Last-Modified"),
    ):
        value = response.headers.get(source)
        if value:
            headers[target] = value
    return headers


def _iter_response_content(response: requests.Response):
    try:
        yield from response.iter_content(chunk_size=1024 * 512)
    finally:
        response.close()


def _stream_response(response: requests.Response) -> StreamingResponse:
    return StreamingResponse(
        _iter_response_content(response),
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/octet-stream"),
        headers=_proxy_headers(response),
    )


def _extract_aweme_id(*values: str | None) -> str:
    for value in values:
        text = unquote(str(value or ""))
        for pattern in (r"/video/(\d+)", r"[?&]modal_id=(\d+)", r"[?&]aweme_id=(\d+)"):
            match = re.search(pattern, text)
            if match:
                return match.group(1)
    return ""


def _refresh_douyin_media_urls(aweme_id: str, *, referer: str, original_url: str) -> list[str]:
    if not aweme_id:
        return []
    try:
        from integrations.douyin_provider.factory import get_douyin_provider

        refreshed = get_douyin_provider().get_one_video(aweme_id, prefer_cache=False)
    except Exception:
        return []

    refreshed_video = refreshed.get("video") if isinstance(refreshed.get("video"), dict) else {}
    download_urls = refreshed.get("download_urls") if isinstance(refreshed.get("download_urls"), dict) else {}
    raw = refreshed.get("raw") if isinstance(refreshed.get("raw"), dict) else {}
    video = {
        **refreshed_video,
        "aweme_id": aweme_id,
        "share_url": referer,
        "work_url": referer,
        "source_video_url": original_url,
        "download_urls": download_urls,
        "raw": raw,
    }
    return VideoEvidencePipeline(output_dir=Path("data/runtime/media_proxy")).video_url_candidates(video)


def proxy_remote_media(
    *,
    url: str,
    referer: str | None = None,
    request: Request | None = None,
    namespace: str = "media-proxy",
    default_referer: str = DEFAULT_REFERER,
    aweme_id: str | None = None,
) -> StreamingResponse:
    target_url = unquote(url)
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid media url")

    resolved_referer = referer or default_referer
    resolved_aweme_id = str(aweme_id or "").strip() or _extract_aweme_id(referer, target_url)
    video_context = {
        "aweme_id": resolved_aweme_id,
        "share_url": resolved_referer,
        "work_url": resolved_referer,
        "source_video_url": target_url,
    }
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": resolved_referer,
        "Origin": "https://www.douyin.com",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Sec-Fetch-Dest": "video",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
    }
    range_header = request.headers.get("range") if request else None
    headers["Range"] = range_header or "bytes=0-"
    cookie = VideoEvidencePipeline.video_download_cookie(target_url)
    if cookie:
        headers["Cookie"] = cookie

    response: requests.Response | None = None
    attempted: set[str] = set()
    try:
        attempted.add(target_url)
        response = requests.get(target_url, headers=headers, stream=True, timeout=30)
        if response.status_code not in VIDEO_URL_REFRESH_STATUS_CODES:
            response.raise_for_status()
            return _stream_response(response)

        last_response = response
        refreshed_urls = _refresh_douyin_media_urls(
            resolved_aweme_id,
            referer=resolved_referer,
            original_url=target_url,
        )
        for refreshed_url in refreshed_urls:
            if refreshed_url in attempted:
                continue
            attempted.add(refreshed_url)
            candidate_headers = VideoEvidencePipeline(output_dir=Path("data/runtime/media_proxy")).video_download_headers(
                video_context,
                url=refreshed_url,
                base=headers,
            )
            candidate_response = requests.get(refreshed_url, headers=candidate_headers, stream=True, timeout=30)
            if candidate_response.status_code not in VIDEO_URL_REFRESH_STATUS_CODES:
                candidate_response.raise_for_status()
                last_response.close()
                return _stream_response(candidate_response)
            last_response.close()
            last_response = candidate_response

        response = last_response
        response.raise_for_status()
        return _stream_response(response)
    except Exception as exc:
        _log_media_proxy_error(
            namespace=namespace,
            path=parsed.path or "/proxy",
            request={
                "params": {"url": target_url, "referer": referer or "", "aweme_id": resolved_aweme_id},
                "headers": headers,
                "attempted_urls": list(attempted),
            },
            exc=exc,
            api_base=parsed.netloc,
            status_code=response.status_code if response is not None else None,
            response_text=_safe_response_text(response),
        )
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=502,
            detail={"error_type": type(exc).__name__, "message": str(exc)},
        ) from exc


def _safe_response_text(response: requests.Response | None) -> str:
    if response is None:
        return ""
    try:
        return response.text[:2000]
    except Exception:
        return ""


def _log_media_proxy_error(
    *,
    namespace: str,
    path: str,
    request: dict[str, Any],
    exc: Exception,
    api_base: str,
    status_code: int | None = None,
    response_text: str = "",
) -> None:
    write_error_log(
        namespace=namespace,
        path=path,
        method="GET",
        request=request,
        exc=exc,
        api_base=api_base,
        status_code=status_code,
        response_text=response_text,
        extra={"phase": "media_proxy_request_exception"},
    )


@router.get("/proxy")
def media_proxy(
    request: Request,
    url: str = Query(...),
    referer: str | None = Query(default=None),
    aweme_id: str | None = Query(default=None),
):
    return proxy_remote_media(url=url, referer=referer, aweme_id=aweme_id, request=request)
