from __future__ import annotations

import asyncio
import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any

from integrations.jianying_editor_skill.sdk_cli_runner import SdkCliRunner


class SdkCapabilityService:
    """Stable business wrapper for selected JianYing Editor Skill CLI capabilities."""

    def __init__(self, runner: SdkCliRunner | None = None):
        self.runner = runner or SdkCliRunner()

    def list_drafts(self, *, root: str = "", limit: int = 20) -> dict[str, Any]:
        args = ["list", "--limit", str(max(0, int(limit or 0))), "--json"]
        if root:
            args = ["--root", root, *args]
        return self.runner.run("draft_inspector.py", args, timeout_seconds=20).to_dict()

    def summarize_draft(self, *, root: str = "", name: str = "", path: str = "") -> dict[str, Any]:
        args = ["summary", "--json"]
        if root:
            args = ["--root", root, *args]
        if path:
            args.extend(["--path", path])
        elif name:
            args.extend(["--name", name])
        else:
            return self._invalid("Either draft name or draft path is required.")
        return self.runner.run("draft_inspector.py", args, timeout_seconds=20).to_dict()

    def show_draft(self, *, root: str = "", name: str = "", path: str = "", kind: str = "content") -> dict[str, Any]:
        safe_kind = kind if kind in {"content", "meta", "both"} else "content"
        args = ["show", "--kind", safe_kind, "--json"]
        if root:
            args = ["--root", root, *args]
        if path:
            args.extend(["--path", path])
        elif name:
            args.extend(["--name", name])
        else:
            return self._invalid("Either draft name or draft path is required.")
        return self.runner.run("draft_inspector.py", args, timeout_seconds=20).to_dict()

    def search_assets(self, *, query: str, category: str = "", limit: int = 20) -> dict[str, Any]:
        cleaned_query = query.strip()
        if not cleaned_query:
            return self._invalid("Search query is required.")
        args = [cleaned_query, "--limit", str(max(1, min(int(limit or 20), 200))), "--json"]
        if category.strip():
            args.extend(["--category", category.strip()])
        return self.runner.run("asset_search.py", args, timeout_seconds=20).to_dict()

    def export_draft(
        self,
        *,
        name: str,
        output_path: str,
        resolution: str = "",
        framerate: str = "",
    ) -> dict[str, Any]:
        draft_name = name.strip()
        output = output_path.strip()
        if not draft_name:
            return self._invalid("Draft name is required.")
        if not output:
            return self._invalid("Output path is required.")
        output_parent = Path(output).expanduser().resolve().parent
        output_parent.mkdir(parents=True, exist_ok=True)

        args = [draft_name, str(Path(output).expanduser())]
        if resolution:
            args.extend(["--res", resolution])
        if framerate:
            args.extend(["--fps", framerate])
        args.append("--json")
        return self.runner.run("auto_exporter.py", args, timeout_seconds=1800).to_dict()

    def record_web_vfx(
        self,
        *,
        source: str,
        output_path: str,
        max_duration_seconds: float = 30,
    ) -> dict[str, Any]:
        cleaned_source = source.strip()
        output = output_path.strip()
        if not cleaned_source:
            return self._invalid("Web VFX source URL or HTML path is required.")
        if not output:
            return self._invalid("Output path is required.")
        output = str(Path(output).expanduser())
        Path(output).resolve().parent.mkdir(parents=True, exist_ok=True)

        def action() -> dict[str, Any]:
            self._prepare_sdk_imports()
            from web_recorder import record_web_animation  # type: ignore

            ok = bool(record_web_animation(cleaned_source, output, max_duration=float(max_duration_seconds)))
            return {
                "source": cleaned_source,
                "output": output,
                "max_duration_seconds": max_duration_seconds,
                "exists": Path(output).expanduser().exists(),
                "recorded": ok,
            }

        return self._run_local_action(action, code="web_vfx_recorded", fail_code="web_vfx_failed")

    def generate_tts(
        self,
        *,
        text: str,
        output_path: str,
        speaker: str = "zh_male_huoli",
        backend: str = "",
        allow_fallback: bool = True,
        sami_retries: int = 2,
    ) -> dict[str, Any]:
        cleaned_text = text.strip()
        output = output_path.strip()
        cleaned_backend = backend.strip().lower()
        if not cleaned_text:
            return self._invalid("TTS text is required.")
        if not output:
            return self._invalid("Output path is required.")
        if cleaned_backend and cleaned_backend not in {"sami", "edge"}:
            return self._invalid("TTS backend must be empty, sami, or edge.")
        output = str(Path(output).expanduser())
        Path(output).resolve().parent.mkdir(parents=True, exist_ok=True)

        def action() -> dict[str, Any]:
            self._prepare_sdk_imports()
            from universal_tts import generate_voice_with_meta  # type: ignore

            audio_path, backend_used = asyncio.run(
                generate_voice_with_meta(
                    cleaned_text,
                    output,
                    speaker=speaker.strip() or "zh_male_huoli",
                    backend=cleaned_backend or None,
                    allow_fallback=allow_fallback,
                    sami_retries=sami_retries,
                )
            )
            if not audio_path:
                raise RuntimeError("TTS generation failed.")
            return {
                "text_length": len(cleaned_text),
                "output": audio_path,
                "backend": backend_used,
                "exists": Path(audio_path).expanduser().exists(),
            }

        return self._run_local_action(action, code="tts_generated", fail_code="tts_failed")

    def resolve_cloud_asset(self, *, query: str, force: bool = False) -> dict[str, Any]:
        cleaned_query = query.strip()
        if not cleaned_query:
            return self._invalid("Cloud asset query is required.")

        def action() -> dict[str, Any]:
            self._prepare_sdk_imports()
            from cloud_manager import CloudManager  # type: ignore

            manager = CloudManager()
            asset = manager.find_asset(cleaned_query)
            if not asset:
                raise ValueError(f"Cloud asset not found or has no downloadable URL: {cleaned_query}")
            local_path = manager.download_asset(cleaned_query, force=force) if asset else None
            return {
                "query": cleaned_query,
                "force": force,
                "asset": asset or {},
                "local_path": local_path or "",
                "downloaded": bool(local_path),
            }

        return self._run_local_action(action, code="cloud_asset_resolved", fail_code="cloud_asset_failed")

    def sync_cloud_music_library(self, *, projects_root: str = "", dry_run: bool = False) -> dict[str, Any]:
        args = ["--json"]
        if projects_root.strip():
            args.extend(["--projects-root", projects_root.strip()])
        if dry_run:
            args.append("--dry-run")
        return self.runner.run("build_cloud_music_library.py", args, timeout_seconds=120).to_dict()

    def create_smart_zoom_draft(
        self,
        *,
        project_name: str,
        video_path: str,
        events_json_path: str,
        zoom_scale: int = 150,
        hold_seconds: float = 5,
    ) -> dict[str, Any]:
        cleaned_name = project_name.strip()
        video = Path(video_path.strip()).expanduser()
        events = Path(events_json_path.strip()).expanduser()
        if not cleaned_name:
            return self._invalid("Project name is required.")
        if not video.exists():
            return self._invalid(f"Video file not found: {video}")
        if not events.exists():
            return self._invalid(f"Events JSON file not found: {events}")

        def action() -> dict[str, Any]:
            self._prepare_sdk_imports()
            from jy_wrapper import JyProject  # type: ignore
            from pyJianYingDraft.keyframe import KeyframeProperty as KP  # type: ignore

            with events.open("r", encoding="utf-8") as file:
                raw_events = json.load(file)
            if not isinstance(raw_events, list):
                raise ValueError("Events JSON must be a list.")
            click_events = [
                event
                for event in raw_events
                if isinstance(event, dict) and event.get("type") == "click"
            ]
            if not click_events:
                raise ValueError("Events JSON does not contain click events.")

            project = JyProject(cleaned_name, overwrite=True)
            segment = project.add_media_safe(str(video), "0s")
            if segment is None:
                raise RuntimeError("Failed to add video to smart zoom draft.")

            scale = float(zoom_scale) / 100.0
            zoom_in_us = 300_000
            zoom_out_us = 600_000
            hold_us = int(float(hold_seconds) * 1_000_000)

            for event in click_events:
                event_time = max(0.0, float(event.get("time") or 0))
                x = min(1.0, max(0.0, float(event.get("x") or 0.5)))
                y = min(1.0, max(0.0, float(event.get("y") or 0.5)))
                start_us = max(0, int(event_time * 1_000_000) - zoom_in_us)
                focus_us = int(event_time * 1_000_000)
                hold_end_us = focus_us + hold_us
                restore_us = hold_end_us + zoom_out_us
                pos_x = -(x - 0.5) * 2 * scale
                pos_y = (y - 0.5) * 2 * scale
                limit = max(0.0, scale - 1.0)
                pos_x = max(-limit, min(pos_x, limit))
                pos_y = max(-limit, min(pos_y, limit))

                segment.add_keyframe(KP.uniform_scale, start_us, 1.0)
                segment.add_keyframe(KP.position_x, start_us, 0.0)
                segment.add_keyframe(KP.position_y, start_us, 0.0)
                segment.add_keyframe(KP.uniform_scale, focus_us, scale)
                segment.add_keyframe(KP.position_x, focus_us, pos_x)
                segment.add_keyframe(KP.position_y, focus_us, pos_y)
                segment.add_keyframe(KP.uniform_scale, hold_end_us, scale)
                segment.add_keyframe(KP.position_x, hold_end_us, pos_x)
                segment.add_keyframe(KP.position_y, hold_end_us, pos_y)
                segment.add_keyframe(KP.uniform_scale, restore_us, 1.0)
                segment.add_keyframe(KP.position_x, restore_us, 0.0)
                segment.add_keyframe(KP.position_y, restore_us, 0.0)

            save_result = project.save()
            return {
                "project": cleaned_name,
                "video": str(video),
                "events": str(events),
                "click_count": len(click_events),
                "zoom_scale": zoom_scale,
                "hold_seconds": hold_seconds,
                "save_result": save_result,
            }

        return self._run_local_action(action, code="smart_zoom_draft_created", fail_code="smart_zoom_failed")

    def create_movie_commentary_draft(
        self,
        *,
        video_path: str,
        storyboard_path: str,
        project_name: str = "Movie_Commentary_Project",
        bgm_path: str = "",
        mask_path: str = "",
    ) -> dict[str, Any]:
        video = video_path.strip()
        storyboard = storyboard_path.strip()
        name = project_name.strip() or "Movie_Commentary_Project"
        if not video:
            return self._invalid("Video path is required.")
        if not storyboard:
            return self._invalid("Storyboard JSON path is required.")
        args = ["--video", video, "--json", storyboard, "--name", name]
        if bgm_path.strip():
            args.extend(["--bgm", bgm_path.strip()])
        if mask_path.strip():
            args.extend(["--mask", mask_path.strip()])
        result = self.runner.run("movie_commentary_builder.py", args, timeout_seconds=300).to_dict()
        if result["ok"] and not result["data"]:
            result["data"] = {
                "ok": True,
                "code": "movie_commentary_created",
                "reason": "",
                "data": {"project": name, "video": video, "storyboard": storyboard},
            }
        return result

    def _prepare_sdk_imports(self) -> None:
        for entry in [self.runner.scripts_dir, self.runner.scripts_dir / "vendor"]:
            path = str(entry)
            if path not in sys.path:
                sys.path.insert(0, path)

    def _run_local_action(self, action, *, code: str, fail_code: str) -> dict[str, Any]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                data = action()
        except Exception as exc:
            return self._local_result(
                ok=False,
                code=fail_code,
                reason=f"{type(exc).__name__}: {exc}",
                data={},
                stdout=stdout.getvalue(),
                stderr=stderr.getvalue(),
                error=f"{type(exc).__name__}: {exc}",
            )
        return self._local_result(
            ok=True,
            code=code,
            reason="",
            data=data,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        )

    def _local_result(
        self,
        *,
        ok: bool,
        code: str,
        reason: str,
        data: dict[str, Any],
        stdout: str,
        stderr: str,
        error: str = "",
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "exit_code": 0 if ok else 1,
            "command": [],
            "data": {"ok": ok, "code": code, "reason": reason, "data": data},
            "stdout_tail": stdout.strip().splitlines()[-20:],
            "stderr_tail": stderr.strip().splitlines()[-20:],
            "error": error,
        }

    def _invalid(self, message: str) -> dict[str, Any]:
        return {
            "ok": False,
            "exit_code": None,
            "command": [],
            "data": {"ok": False, "code": "invalid_input", "reason": message, "data": {}},
            "stdout_tail": [],
            "stderr_tail": [],
            "error": message,
        }
