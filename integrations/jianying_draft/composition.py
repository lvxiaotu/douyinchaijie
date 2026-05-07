from __future__ import annotations

from typing import Any


VISUAL_TRACK_TYPES = {"video", "image", "overlay", "rendered"}


def normalize_composition(composition: dict[str, Any]) -> dict[str, Any]:
    """Convert generic video composition JSON into draft creation payload."""

    canvas = composition.get("canvas") or {}
    width = int(canvas.get("width") or 1080)
    height = int(canvas.get("height") or 1920)
    payload: dict[str, Any] = {
        "name": composition.get("name") or "jianying_draft",
        "aspect_ratio": aspect_ratio_from_canvas(width, height),
        "canvas": {
            "width": width,
            "height": height,
            "fps": int(canvas.get("fps") or 30),
            "duration_seconds": canvas.get("duration_seconds"),
        },
        "media": [],
        "audio": [],
        "texts": [],
    }

    for track in composition.get("tracks") or []:
        track_type = str(track.get("type") or "").lower()
        track_id = str(track.get("id") or track_type or "track")
        for item in track.get("items") or []:
            if track_type in VISUAL_TRACK_TYPES:
                path = str(item.get("path") or "").strip()
                if not path:
                    continue
                payload["media"].append(media_item(item, track_type, track_id))
            elif track_type == "audio":
                path = str(item.get("path") or "").strip()
                if not path:
                    continue
                payload["audio"].append(media_item(item, track_type, track_id))
            elif track_type == "text":
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                payload["texts"].append(text_item(item, track_id))

    return payload


def media_item(item: dict[str, Any], item_type: str, track_id: str) -> dict[str, Any]:
    jianying = item.get("jianying") or {}
    return {
        "path": str(item.get("path") or ""),
        "type": item_type,
        "role": item.get("role") or "",
        "track": jianying.get("track") or item.get("track") or track_id,
        "start_seconds": float(item.get("start_seconds") or 0),
        "duration_seconds": duration_or_none(item),
    }


def text_item(item: dict[str, Any], track_id: str) -> dict[str, Any]:
    jianying = item.get("jianying") or {}
    return {
        "text": str(item.get("text") or ""),
        "track": jianying.get("track") or item.get("track") or track_id,
        "start_seconds": float(item.get("start_seconds") or 0),
        "duration_seconds": duration_or_none(item),
        "style": item.get("style") or {},
    }


def duration_or_none(item: dict[str, Any]) -> float | None:
    value = item.get("duration_seconds")
    if value is None or value == "":
        return None
    return float(value)


def aspect_ratio_from_canvas(width: int, height: int) -> str:
    if width == height:
        return "1:1"
    if width > height:
        return "16:9"
    return "9:16"

