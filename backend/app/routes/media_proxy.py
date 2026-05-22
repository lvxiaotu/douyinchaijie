from typing import Any
from urllib.parse import unquote, urlparse

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.app.error_log_store import write_error_log

router = APIRouter(prefix="/api/media", tags=["media"])

DEFAULT_REFERER = "https://www.douyin.com/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
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


def proxy_remote_media(
    *,
    url: str,
    referer: str | None = None,
    request: Request | None = None,
    namespace: str = "media-proxy",
    default_referer: str = DEFAULT_REFERER,
) -> StreamingResponse:
    target_url = unquote(url)
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid media url")

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": referer or default_referer,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    range_header = request.headers.get("range") if request else None
    headers["Range"] = range_header or "bytes=0-"

    response: requests.Response | None = None
    try:
        response = requests.get(target_url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        return StreamingResponse(
            response.iter_content(chunk_size=1024 * 512),
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "application/octet-stream"),
            headers=_proxy_headers(response),
        )
    except Exception as exc:
        _log_media_proxy_error(
            namespace=namespace,
            path=parsed.path or "/proxy",
            request={
                "params": {"url": target_url, "referer": referer or ""},
                "headers": headers,
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
):
    return proxy_remote_media(url=url, referer=referer, request=request)
