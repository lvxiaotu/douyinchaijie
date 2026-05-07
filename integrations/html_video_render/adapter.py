from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from integrations.base import IntegrationAdapter, IntegrationManifest
from integrations.html_video_render.render_runner import HtmlVideoRenderRunner


DEFAULT_OUTPUT_DIR = Path("data/runtime/html_video_render")


class HtmlVideoRenderAdapter(IntegrationAdapter):
    manifest = IntegrationManifest(
        id="html-video-render",
        name="HTML 动效素材生成器",
        description="将 HTML/CSS/JS composition 渲染为可导入剪映的视频素材。",
        repo_url="https://github.com/heygen-com/hyperframes",
        tags=["html", "video", "render", "assets"],
        config_schema={
            "output_dir": "HTML 渲染产物目录",
            "renderer": "placeholder | python_frames | playwright | hyperframes",
            "width": "默认画布宽度",
            "height": "默认画布高度",
            "fps": "默认帧率",
        },
    )

    def __init__(self, config: dict[str, Any] | None = None):
        load_dotenv()
        self.config = config or {}
        self.output_dir = Path(self._value("output_dir", "HTML_VIDEO_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
        self.renderer = self._value("renderer", "HTML_VIDEO_RENDERER", "placeholder")
        self.width = int(self._value("width", "HTML_VIDEO_WIDTH", "1080"))
        self.height = int(self._value("height", "HTML_VIDEO_HEIGHT", "1920"))
        self.fps = int(self._value("fps", "HTML_VIDEO_FPS", "30"))
        self.ffmpeg_binary = self._value("ffmpeg_binary", "HTML_VIDEO_FFMPEG_BINARY", os.getenv("FFMPEG_BINARY", ""))
        self.runner = HtmlVideoRenderRunner(str(self.output_dir), ffmpeg_binary=self.ffmpeg_binary)

    def _value(self, config_key: str, env_key: str, default: str) -> str:
        return str(self.config.get(config_key) or os.getenv(env_key) or default)

    def validate_config(self, config: dict[str, Any] | None = None) -> list[str]:
        cfg = {**self.config, **(config or {})}
        errors: list[str] = []
        renderer = str(cfg.get("renderer") or self.renderer)
        if renderer not in {"placeholder", "python_frames", "playwright", "hyperframes"}:
            errors.append("HTML_VIDEO_RENDERER must be one of placeholder, python_frames, playwright, hyperframes")
        output_dir = Path(str(cfg.get("output_dir") or self.output_dir))
        if output_dir.exists() and not output_dir.is_dir():
            errors.append("HTML_VIDEO_OUTPUT_DIR is not a directory")
        ffmpeg_binary = str(cfg.get("ffmpeg_binary") or self.ffmpeg_binary or "")
        if ffmpeg_binary and ffmpeg_binary.lower() != "ffmpeg" and not Path(ffmpeg_binary).exists():
            errors.append("HTML_VIDEO_FFMPEG_BINARY does not exist")
        return errors

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "render":
            return self.render(payload)
        raise ValueError(f"Unsupported HTML video render action: {action}")

    def status(self) -> dict[str, Any]:
        errors = self.validate_config()
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "repo_url": self.manifest.repo_url,
            "ready": not errors,
            "errors": errors,
            "output_dir": str(self.output_dir),
            "renderer": self.renderer,
            "canvas": {"width": self.width, "height": self.height, "fps": self.fps},
            "ffmpeg_binary": self.ffmpeg_binary,
        }

    def config_snapshot(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "renderer": self.renderer,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "ffmpeg_binary": self.ffmpeg_binary,
        }

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        render_payload = {
            "name": payload.get("name") or "html-render",
            "width": payload.get("width") or self.width,
            "height": payload.get("height") or self.height,
            "fps": payload.get("fps") or self.fps,
            "duration_seconds": payload.get("duration_seconds") or 3,
            "html": payload.get("html") or "",
        }
        return self.runner.render(render_payload, renderer=self.renderer)
