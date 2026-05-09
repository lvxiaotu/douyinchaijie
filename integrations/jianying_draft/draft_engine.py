from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from integrations.jianying_draft.name_utils import default_draft_name, safe_draft_name


class JianyingDraftEngine:
    """Placeholder for pyJianYingDraft-backed draft operations."""

    def __init__(self, output_dir: str, draft_root: str = ""):
        self.output_dir = Path(output_dir)
        self.draft_root = Path(draft_root) if draft_root else self.output_dir

    def dependency_status(self) -> dict[str, Any]:
        try:
            import pyJianYingDraft  # type: ignore  # noqa: F401

            return {"pyJianYingDraft": "available"}
        except Exception as exc:
            return {"pyJianYingDraft": "missing", "error": str(exc)}

    def create_placeholder_draft(self, name: str) -> dict[str, Any]:
        draft_name = safe_draft_name(name, fallback=default_draft_name())
        draft_dir = self.output_dir / draft_name
        draft_dir.mkdir(parents=True, exist_ok=True)
        return {
            "name": draft_name,
            "draft_path": str(draft_dir),
            "status": "created_placeholder",
        }

    def create_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        dependency = self.dependency_status()
        if dependency.get("pyJianYingDraft") != "available":
            result = self.create_placeholder_draft(str(payload.get("name") or "jianying_draft"))
            result.update(
                {
                    "status": "dependency_missing",
                    "dependency": dependency,
                    "asset_report": self.asset_report(payload),
                }
            )
            return result

        return self._create_with_pyjianying(payload)

    def asset_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        entries = list(payload.get("media") or []) + list(payload.get("audio") or [])
        available: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for item in entries:
            path = Path(str(item.get("path") or ""))
            record = {
                "path": str(path),
                "type": item.get("type") or "",
                "role": item.get("role") or "",
            }
            if path.exists():
                available.append(record)
            else:
                missing.append(record)
        return {"available": available, "missing": missing}

    def _create_with_pyjianying(self, payload: dict[str, Any]) -> dict[str, Any]:
        import pyJianYingDraft as draft  # type: ignore

        name = safe_draft_name(str(payload.get("name") or ""), fallback=default_draft_name())
        width, height = self._canvas_size(str(payload.get("aspect_ratio") or "9:16"))
        draft_root = self.draft_root
        draft_root.mkdir(parents=True, exist_ok=True)

        draft_folder_cls = self._draft_attr(draft, "DraftFolder", "Draft_folder")
        track_type = self._draft_attr(draft, "TrackType", "Track_type")
        video_segment_cls = self._draft_attr(draft, "VideoSegment", "Video_segment")
        audio_segment_cls = self._draft_attr(draft, "AudioSegment", "Audio_segment")
        text_segment_cls = self._draft_attr(draft, "TextSegment", "Text_segment")
        text_style_cls = self._draft_attr(draft, "TextStyle")
        text_background_cls = self._draft_attr(draft, "TextBackground")

        folder = draft_folder_cls(str(draft_root))
        script = folder.create_draft(name, width, height)
        self._ensure_track(script, track_type.video, "video")
        self._ensure_track(script, track_type.audio, "audio")
        self._ensure_track(script, track_type.text, "text")

        cursor_us = 0
        default_media_duration_us = int(float(payload.get("default_media_duration_seconds") or 3) * 1_000_000)
        for item in payload.get("media") or []:
            path = Path(str(item.get("path") or ""))
            if not path.exists():
                continue
            duration_us = int(float(item.get("duration_seconds") or 0) * 1_000_000) or default_media_duration_us
            start_us = int(float(item.get("start_seconds") or 0) * 1_000_000) if item.get("start_seconds") is not None else cursor_us
            source_timerange = self._trange(draft, 0, duration_us)
            target_timerange = self._trange(draft, start_us, duration_us)
            segment = video_segment_cls(str(path), source_timerange, target_timerange)
            script.add_segment(segment, track_name=str(item.get("track") or "video"))
            cursor_us = max(cursor_us, start_us + duration_us)

        for item in payload.get("audio") or []:
            path = Path(str(item.get("path") or ""))
            if not path.exists():
                continue
            duration_us = int(float(item.get("duration_seconds") or 0) * 1_000_000) or max(cursor_us, default_media_duration_us)
            start_us = int(float(item.get("start_seconds") or 0) * 1_000_000)
            source_timerange = self._trange(draft, 0, duration_us)
            target_timerange = self._trange(draft, start_us, duration_us)
            segment = audio_segment_cls(str(path), source_timerange, target_timerange)
            script.add_segment(segment, track_name=str(item.get("track") or "audio"))

        for item in payload.get("texts") or []:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            duration_us = int(float(item.get("duration_seconds") or 0) * 1_000_000) or default_media_duration_us
            start_us = int(float(item.get("start_seconds") or 0) * 1_000_000)
            style = self._build_text_style(text_style_cls, item.get("style") if isinstance(item.get("style"), dict) else {})
            background = self._build_text_background(
                text_background_cls,
                item.get("background") if isinstance(item.get("background"), dict) else {},
            )
            segment = text_segment_cls(
                text,
                self._trange(draft, start_us, duration_us),
                style=style,
                background=background,
            )
            script.add_segment(segment, track_name=str(item.get("track") or "text"))

        script.save()
        return {
            "name": name,
            "draft_path": str(draft_root / name),
            "status": "created",
            "asset_report": self.asset_report(payload),
            "dependency": self.dependency_status(),
            "canvas": {"width": width, "height": height},
        }

    def _ensure_track(self, script: Any, track_type: Any, name: str) -> None:
        try:
            script.add_track(track_type, track_name=name)
        except TypeError:
            script.add_track(track_type, name)

    def _draft_attr(self, module: Any, *names: str) -> Any:
        for name in names:
            if hasattr(module, name):
                return getattr(module, name)
        raise AttributeError(f"pyJianYingDraft is missing expected API: {' or '.join(names)}")

    def _trange(self, module: Any, start_us: int, duration_us: int) -> Any:
        try:
            return module.trange(start_us, duration_us)
        except TypeError:
            start_seconds = start_us / 1_000_000
            duration_seconds = duration_us / 1_000_000
            return module.trange(f"{start_seconds}s", f"{duration_seconds}s")

    def _canvas_size(self, aspect_ratio: str) -> tuple[int, int]:
        normalized = aspect_ratio.strip().lower()
        if normalized in {"16:9", "landscape", "horizontal"}:
            return 1920, 1080
        if normalized in {"1:1", "square"}:
            return 1080, 1080
        return 1080, 1920

    def _build_text_style(self, style_cls: Any, config: dict[str, Any]) -> Any:
        if not config:
            return None
        kwargs: dict[str, Any] = {}
        for key in ("size", "bold", "italic", "underline", "alpha", "align", "vertical", "letter_spacing", "line_spacing", "auto_wrapping", "max_line_width"):
            if key in config and config[key] not in (None, ""):
                kwargs[key] = config[key]
        color = config.get("color")
        if isinstance(color, (list, tuple)) and len(color) == 3:
            kwargs["color"] = tuple(float(v) for v in color)
        return style_cls(**kwargs) if kwargs else None

    def _build_text_background(self, background_cls: Any, config: dict[str, Any]) -> Any:
        color = config.get("color")
        if not color:
            return None
        kwargs = {"color": str(color)}
        for key in ("style", "alpha", "round_radius", "height", "width", "horizontal_offset", "vertical_offset"):
            if key in config and config[key] not in (None, ""):
                kwargs[key] = config[key]
        return background_cls(**kwargs)
