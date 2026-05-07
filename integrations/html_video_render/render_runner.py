from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


class HtmlVideoRenderRunner:
    """First-pass render runner that writes inspectable HTML artifacts."""

    def __init__(self, output_dir: str, ffmpeg_binary: str = ""):
        self.output_dir = Path(output_dir)
        self.ffmpeg_binary = ffmpeg_binary

    def render(self, payload: dict[str, Any], *, renderer: str = "placeholder") -> dict[str, Any]:
        name = self._safe_name(str(payload.get("name") or f"html-render-{int(time.time())}"))
        width = int(payload.get("width") or 1080)
        height = int(payload.get("height") or 1920)
        fps = int(payload.get("fps") or 30)
        duration = float(payload.get("duration_seconds") or 3)
        html = str(payload.get("html") or self.default_html(name, width, height, duration))

        render_dir = self.output_dir / name
        render_dir.mkdir(parents=True, exist_ok=True)
        html_path = render_dir / "composition.html"
        manifest_path = render_dir / "render.json"
        html_path.write_text(html, encoding="utf-8")
        video_path = ""
        status = "placeholder"
        if renderer == "python_frames":
            video_path = str(self.render_python_frames(render_dir, html, name, width, height, fps, duration))
            status = "done"
        elif renderer in {"playwright", "hyperframes"}:
            status = "renderer_not_available"

        asset_path = video_path or str(html_path)
        asset_status = "available" if video_path else status
        manifest = {
            "render_id": name,
            "status": status,
            "html_path": str(html_path),
            "video_path": video_path,
            "poster_path": "",
            "canvas": {"width": width, "height": height, "fps": fps, "duration_seconds": duration},
            "created_at": int(time.time()),
            "asset": {
                "id": f"html-render:{name}",
                "type": "rendered",
                "name": name,
                "source": "html_render",
                "path": asset_path,
                "status": asset_status,
                "meta": {
                    "html_path": str(html_path),
                    "manifest_path": str(manifest_path),
                    "video_path": video_path,
                    "canvas": {"width": width, "height": height, "fps": fps, "duration_seconds": duration},
                },
            },
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest

    def render_placeholder(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.render(payload, renderer="placeholder")

    def render_python_frames(
        self,
        render_dir: Path,
        html: str,
        name: str,
        width: int,
        height: int,
        fps: int,
        duration: float,
    ) -> Path:
        try:
            import imageio_ffmpeg
        except Exception as exc:
            raise RuntimeError("python_frames renderer requires imageio-ffmpeg") from exc

        video_path = render_dir / f"{name}.mp4"
        title = self.extract_title(html) or name
        font_file = self.font_file()
        font_size = max(28, min(width, height) // 15)
        footer_size = max(16, min(width, height) // 34)
        filtergraph = (
            f"color=c=0x101418:s={width}x{height}:d={duration}:r={fps},"
            "format=yuv420p,"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=0x14532d@0.35:t=fill,"
            f"drawtext=fontfile='{self.ffmpeg_escape(font_file)}':"
            f"text='{self.ffmpeg_escape(title)}':"
            f"fontsize={font_size}:fontcolor=white:"
            "x=(w-text_w)/2:y=(h-text_h)/2,"
            f"drawtext=fontfile='{self.ffmpeg_escape(font_file)}':"
            "text='HTML composition render':"
            f"fontsize={footer_size}:fontcolor=0xbbf7d0:"
            "x=(w-text_w)/2:y=h-text_h-64"
        )
        ffmpeg = self.resolve_ffmpeg_binary(imageio_ffmpeg)
        command = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            filtergraph,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(video_path),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(30, int(duration * 4 + 30)),
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr[-1000:] or "ffmpeg render failed")
        return video_path

    def resolve_ffmpeg_binary(self, imageio_ffmpeg: Any) -> str:
        if self.ffmpeg_binary:
            candidate = Path(self.ffmpeg_binary)
            if candidate.exists():
                return str(candidate)
            if self.ffmpeg_binary.lower() == "ffmpeg":
                return self.ffmpeg_binary
            raise RuntimeError(f"Configured FFmpeg binary does not exist: {self.ffmpeg_binary}")
        return imageio_ffmpeg.get_ffmpeg_exe()

    def font_file(self) -> str:
        candidates = [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        return ""

    def extract_title(self, html: str) -> str:
        match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
        if not match:
            match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        text = re.sub(r"<[^>]+>", "", match.group(1))
        return re.sub(r"\s+", " ", text).strip()

    def wrap_text(self, text: str, max_chars: int) -> list[str]:
        text = text.strip() or "HTML composition"
        if len(text) <= max_chars:
            return [text]
        lines: list[str] = []
        current = ""
        for char in text:
            current += char
            if len(current) >= max_chars:
                lines.append(current)
                current = ""
        if current:
            lines.append(current)
        return lines[:4]

    def ffmpeg_escape(self, value: str) -> str:
        return value.replace("\\", "/").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")

    def default_html(self, name: str, width: int, height: int, duration: float) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{name}</title>
  <style>
    html, body {{
      margin: 0;
      width: 100%;
      height: 100%;
      background: #101418;
      color: #f8fafc;
      font-family: Inter, system-ui, sans-serif;
    }}
    .stage {{
      width: {width}px;
      height: {height}px;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, #111827 0%, #14532d 100%);
    }}
    h1 {{
      max-width: 80%;
      font-size: 72px;
      line-height: 1.1;
      text-align: center;
      letter-spacing: 0;
    }}
  </style>
</head>
<body>
  <main class="stage" data-duration="{duration}">
    <h1>{name}</h1>
  </main>
</body>
</html>
"""

    def _safe_name(self, name: str) -> str:
        safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in name).strip("_")
        return safe_name or "html-render"
