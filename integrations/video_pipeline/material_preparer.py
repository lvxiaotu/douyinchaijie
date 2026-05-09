from __future__ import annotations

import base64
import json
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from backend.app.ai_provider_state import active_ai_provider, openai_compatible_credentials
from integrations.video_pipeline.script_schema import VideoScript


ROOT = Path(__file__).resolve().parents[2]
MEDIA_EXTENSIONS = {
    "video": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".bmp"},
    "audio": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"},
}


@dataclass
class PreparationOptions:
    source_paths: list[str]
    resolve_local_materials: bool = True
    generate_audio: bool = True
    generate_images: bool = True
    generate_videos: bool = False
    overwrite_existing: bool = False
    ffprobe_binary: str = "ffprobe"
    tts_provider: str = "openai"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "alloy"
    tts_format: str = "mp3"
    image_provider: str = "gemini"
    image_model: str = "imagen-4.0-generate-001"


class ScriptMaterialPreparer:
    def __init__(self, *, project_id: str, ffprobe_binary: str = "ffprobe") -> None:
        self.project_id = project_id
        self.project_dir = ROOT / "data" / "runtime" / "video_pipeline" / "projects" / project_id
        self.generated_dir = self.project_dir / "generated_assets"
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.ffprobe_binary = ffprobe_binary

    def prepare(self, script: VideoScript, options: PreparationOptions) -> dict[str, Any]:
        source_files = self._collect_source_files(options.source_paths) if options.resolve_local_materials else []
        scene_reports: list[dict[str, Any]] = []
        ready_count = 0

        for scene in script.scenes:
            report = {
                "scene_id": scene.id,
                "title": scene.title,
                "local_matches": [],
                "generated": [],
                "warnings": [],
            }
            assets = scene.assets

            if options.resolve_local_materials:
                matches = self._resolve_scene_materials(scene.model_dump(), source_files)
                report["local_matches"] = matches
                if matches:
                    selected = matches[0]
                    media_type = selected["media_type"]
                    if media_type == "audio" and (options.overwrite_existing or not assets.audio_path):
                        assets.audio_path = selected["path"]
                    if media_type == "video" and (options.overwrite_existing or not assets.video_path):
                        assets.video_path = selected["path"]
                    if media_type == "image" and (options.overwrite_existing or not assets.image_path):
                        assets.image_path = selected["path"]

            if options.generate_audio and scene.audio_narration and (options.overwrite_existing or not assets.audio_path):
                try:
                    audio_path = self._generate_tts_audio(scene.model_dump(), options)
                    assets.audio_path = str(audio_path)
                    report["generated"].append({"kind": "audio", "path": str(audio_path), "provider": options.tts_provider})
                except Exception as exc:
                    report["warnings"].append(f"TTS failed: {type(exc).__name__}: {exc}")

            has_visual = bool((assets.video_path or "").strip() or (assets.image_path or "").strip())
            if options.generate_images and not has_visual and (scene.visual_prompt or scene.asset_requirements.main_subject):
                try:
                    image_path = self._generate_image(scene.model_dump(), options)
                    assets.image_path = str(image_path)
                    report["generated"].append({"kind": "image", "path": str(image_path), "provider": options.image_provider})
                except Exception as exc:
                    report["warnings"].append(f"Image generation failed: {type(exc).__name__}: {exc}")

            if options.generate_videos and not (assets.video_path or "").strip():
                report["warnings"].append("Video generation is not implemented yet in this SDK pipeline stage.")

            duration_seconds = self._scene_duration_seconds(scene.model_dump())
            assets.duration = round(duration_seconds, 3) if duration_seconds > 0 else float(assets.duration or 0)
            scene.status = "ready" if any([(assets.audio_path or "").strip(), (assets.video_path or "").strip(), (assets.image_path or "").strip()]) else "waiting_assets"
            if scene.status == "ready":
                ready_count += 1

            report["duration_ms"] = int(round((assets.duration or 0) * 1000))
            report["status"] = scene.status
            scene_reports.append(report)

        return {
            "script": script,
            "report": {
                "project_id": script.project_id,
                "scene_count": len(script.scenes),
                "ready_scene_count": ready_count,
                "source_path_count": len(options.source_paths),
                "generated_assets_dir": str(self.generated_dir),
                "scenes": scene_reports,
            },
        }

    def _collect_source_files(self, source_paths: list[str]) -> list[Path]:
        candidates: list[Path] = []
        seen: set[str] = set()
        for raw_path in source_paths:
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = (ROOT / path).resolve()
            if not path.exists():
                continue
            if path.is_file():
                resolved = str(path.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    candidates.append(path.resolve())
                continue
            for child in path.rglob("*"):
                if not child.is_file():
                    continue
                resolved = str(child.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    candidates.append(child.resolve())
        return candidates

    def _resolve_scene_materials(self, scene: dict[str, Any], source_files: list[Path]) -> list[dict[str, Any]]:
        keywords = self._scene_keywords(scene)
        if not keywords:
            return []
        ranked: list[tuple[int, Path, str]] = []
        for file_path in source_files:
            media_type = self._media_type(file_path)
            if not media_type:
                continue
            haystack = f"{file_path.stem} {file_path.parent.name}".lower()
            score = 0
            for keyword in keywords:
                if keyword and keyword in haystack:
                    score += max(2, len(keyword))
            if score <= 0:
                continue
            ranked.append((score, file_path, media_type))
        ranked.sort(key=lambda item: (-item[0], len(str(item[1]))))
        return [
            {"path": str(path), "media_type": media_type, "score": score}
            for score, path, media_type in ranked[:3]
        ]

    def _scene_keywords(self, scene: dict[str, Any]) -> list[str]:
        values = [
            scene.get("title") or "",
            scene.get("summary") or "",
            scene.get("visual_prompt") or "",
            scene.get("audio_narration") or "",
            ((scene.get("asset_requirements") or {}).get("main_subject") or ""),
            ((scene.get("asset_requirements") or {}).get("background") or ""),
        ]
        keywords: list[str] = []
        for value in values:
            text = str(value).replace("\n", " ").replace("，", " ").replace(",", " ")
            for token in text.split():
                token = token.strip().lower()
                if len(token) >= 2 and token not in keywords:
                    keywords.append(token)
        scene_id = str(scene.get("id") or "")
        if scene_id:
            keywords.append(f"scene{scene_id}")
            keywords.append(scene_id)
        return keywords[:16]

    def _media_type(self, path: Path) -> str:
        suffix = path.suffix.lower()
        for media_type, extensions in MEDIA_EXTENSIONS.items():
            if suffix in extensions:
                return media_type
        return ""

    def _scene_duration_seconds(self, scene: dict[str, Any]) -> float:
        assets = scene.get("assets") or {}
        for key in ("audio_path", "video_path"):
            path_value = str(assets.get(key) or "").strip()
            if not path_value:
                continue
            duration = self._probe_duration(Path(path_value))
            if duration > 0:
                return duration
        explicit = float(assets.get("duration") or 0)
        if explicit > 0:
            return explicit
        estimated = float(scene.get("estimated_duration") or 0)
        return estimated if estimated > 0 else 0.0

    def _probe_duration(self, path: Path) -> float:
        if not path.exists():
            return 0.0
        duration = self._probe_with_ffprobe(path)
        if duration > 0:
            return duration
        if path.suffix.lower() == ".wav":
            try:
                with wave.open(str(path), "rb") as wav_file:
                    frames = wav_file.getnframes()
                    rate = wav_file.getframerate() or 1
                    return frames / float(rate)
            except Exception:
                return 0.0
        return 0.0

    def _probe_with_ffprobe(self, path: Path) -> float:
        binary = self.ffprobe_binary
        if not shutil.which(binary):
            return 0.0
        command = [
            binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
            data = json.loads(completed.stdout or "{}")
            return float((data.get("format") or {}).get("duration") or 0)
        except Exception:
            return 0.0

    def _generate_tts_audio(self, scene: dict[str, Any], options: PreparationOptions) -> Path:
        provider = (options.tts_provider or "openai").lower()
        if provider == "openai":
            return self._generate_openai_tts(scene, options)
        raise RuntimeError(f"Unsupported TTS provider: {provider}")

    def _generate_openai_tts(self, scene: dict[str, Any], options: PreparationOptions) -> Path:
        credentials = self._resolve_openai_tts_credentials()
        if not credentials["api_key"] or not credentials["base_url"]:
            raise RuntimeError("Missing OpenAI-compatible credentials for TTS.")
        output_path = self.generated_dir / f"scene_{int(scene.get('id') or 0):02d}_narration.{options.tts_format}"
        response = requests.post(
            f"{credentials['base_url'].rstrip('/')}/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {credentials['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": options.tts_model,
                "voice": options.tts_voice,
                "input": str(scene.get("audio_narration") or "").strip(),
                "response_format": options.tts_format,
            },
            timeout=180,
        )
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:400]}")
        output_path.write_bytes(response.content)
        return output_path

    def _resolve_openai_tts_credentials(self) -> dict[str, str]:
        active_provider = active_ai_provider("")
        if active_provider in {"openai", "simple_relay", "yunwu", "deepseek", "volcano"}:
            creds = openai_compatible_credentials(active_provider)
            if creds.get("api_key") and creds.get("base_url"):
                return {"api_key": creds["api_key"], "base_url": creds["base_url"]}
        fallback = openai_compatible_credentials("openai")
        return {"api_key": fallback.get("api_key", ""), "base_url": fallback.get("base_url", "")}

    def _generate_image(self, scene: dict[str, Any], options: PreparationOptions) -> Path:
        provider = (options.image_provider or "gemini").lower()
        if provider == "gemini":
            return self._generate_gemini_image(scene, options)
        raise RuntimeError(f"Unsupported image provider: {provider}")

    def _generate_gemini_image(self, scene: dict[str, Any], options: PreparationOptions) -> Path:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Missing dependency google-genai. Run: pip install -r requirements.txt") from exc

        api_key = self._resolve_gemini_api_key()
        if not api_key:
            raise RuntimeError("Missing Gemini API key for Imagen generation.")

        prompt = self._scene_image_prompt(scene)
        client = genai.Client(api_key=api_key)
        response = client.models.generate_images(
            model=options.image_model,
            prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1),
        )
        generated_images = getattr(response, "generated_images", None) or []
        if not generated_images:
            raise RuntimeError("Imagen returned no image bytes.")
        image_bytes = generated_images[0].image.image_bytes
        output_path = self.generated_dir / f"scene_{int(scene.get('id') or 0):02d}_image.png"
        output_path.write_bytes(image_bytes)
        return output_path

    def _resolve_gemini_api_key(self) -> str:
        import os

        return (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("AI_NATIVE_API_KEY")
            or os.getenv("GEMINI_RELAY_API_KEY")
            or os.getenv("AI_RELAY_API_KEY")
            or ""
        )

    def _scene_image_prompt(self, scene: dict[str, Any]) -> str:
        requirements = scene.get("asset_requirements") or {}
        chunks = [
            str(scene.get("visual_prompt") or "").strip(),
            str(requirements.get("main_subject") or "").strip(),
            str(requirements.get("background") or "").strip(),
            str(requirements.get("mood") or "").strip(),
            str(scene.get("summary") or "").strip(),
        ]
        return ", ".join(chunk for chunk in chunks if chunk)
