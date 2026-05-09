from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SDK_SCRIPTS_DIR = ROOT / "sdks" / "jianying-editor-skill" / "scripts"


class JianyingSdkDraftEngine:
    """Build drafts through jianying-editor-skill JyProject."""

    def __init__(self, output_dir: str, draft_root: str = ""):
        self.output_dir = Path(output_dir)
        self.draft_root = Path(draft_root) if draft_root else self.output_dir

    def dependency_status(self) -> dict[str, Any]:
        if not SDK_SCRIPTS_DIR.exists():
            return {"jianying_editor_skill": "missing", "error": f"SDK scripts dir not found: {SDK_SCRIPTS_DIR}"}
        try:
            self._prepare_imports()
            from jy_wrapper import JyProject  # type: ignore  # noqa: F401

            return {"jianying_editor_skill": "available"}
        except Exception as exc:
            return {"jianying_editor_skill": "error", "error": str(exc)}

    def create_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        dependency = self.dependency_status()
        if dependency.get("jianying_editor_skill") != "available":
            raise RuntimeError(dependency.get("error") or "JianYing Editor Skill SDK is not available")
        return self._create_with_sdk(payload)

    def _prepare_imports(self) -> None:
        scripts_dir = str(SDK_SCRIPTS_DIR)
        vendor_dir = str(SDK_SCRIPTS_DIR / "vendor")
        for entry in [scripts_dir, vendor_dir]:
            if entry not in sys.path:
                sys.path.insert(0, entry)

    def _create_with_sdk(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._prepare_imports()
        from jy_wrapper import JyProject  # type: ignore

        name = self._safe_name(str(payload.get("name") or "jianying_sdk_draft"))
        width, height = self._canvas_size(str(payload.get("aspect_ratio") or "9:16"))
        self.draft_root.mkdir(parents=True, exist_ok=True)

        project = JyProject(name, width=width, height=height, drafts_root=str(self.draft_root), overwrite=True)

        media = list(payload.get("media") or [])
        audio = list(payload.get("audio") or [])
        texts = list(payload.get("texts") or [])
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        scene_plan = meta.get("scene_plan") if isinstance(meta.get("scene_plan"), list) else []
        default_media_duration = float(payload.get("default_media_duration_seconds") or 3.0)
        video_segments: dict[str, Any] = {}

        for item in media:
            media_path = str(item.get("path") or "").strip()
            if not media_path:
                continue
            start_seconds = float(item.get("start_seconds") or 0)
            duration_seconds = float(item.get("duration_seconds") or default_media_duration)
            track_name = str(item.get("track") or "VideoTrack")
            kwargs: dict[str, Any] = {}
            clip_settings = item.get("clip_settings") if isinstance(item.get("clip_settings"), dict) else {}
            sdk_clip_settings = self._build_sdk_clip_settings(clip_settings)
            if sdk_clip_settings is not None:
                kwargs["clip_settings"] = sdk_clip_settings
            segment = project.add_media_safe(
                media_path,
                start_time=f"{start_seconds}s",
                duration=f"{duration_seconds}s",
                track_name=track_name,
                **kwargs,
            )
            role = str(item.get("role") or "").strip()
            if role and segment is not None:
                video_segments[role] = segment

        for item in audio:
            media_path = str(item.get("path") or "").strip()
            if not media_path:
                continue
            start_seconds = float(item.get("start_seconds") or 0)
            duration_seconds = float(item.get("duration_seconds") or default_media_duration)
            track_name = str(item.get("track") or "AudioTrack")
            project.add_audio_safe(
                media_path,
                start_time=f"{start_seconds}s",
                duration=f"{duration_seconds}s",
                track_name=track_name,
            )

        for item in texts:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            start_seconds = float(item.get("start_seconds") or 0)
            duration_seconds = float(item.get("duration_seconds") or default_media_duration)
            track_name = str(item.get("track") or "Subtitles")
            kwargs: dict[str, Any] = {}
            style = item.get("style")
            background = item.get("background")
            if isinstance(style, dict):
                kwargs["style"] = self._build_sdk_text_style(style)
            if isinstance(background, dict):
                kwargs["background"] = self._build_sdk_text_background(background)
            clip_settings = item.get("clip_settings")
            if isinstance(clip_settings, dict):
                sdk_clip_settings = self._build_sdk_clip_settings(clip_settings)
                if sdk_clip_settings is not None:
                    kwargs["clip_settings"] = sdk_clip_settings
            project.add_text_simple(
                text,
                start_time=f"{start_seconds}s",
                duration=f"{duration_seconds}s",
                track_name=track_name,
                **kwargs,
            )

        edit_report = self._apply_scene_edits(project, video_segments, scene_plan)

        stdout = sys.stdout
        encoding = getattr(stdout, "encoding", "") or ""
        wrapped_stdout = None
        try:
            if encoding.lower() in {"gbk", "cp936"} and hasattr(stdout, "buffer"):
                wrapped_stdout = io.TextIOWrapper(stdout.buffer, encoding="utf-8", errors="ignore", line_buffering=True)
                sys.stdout = wrapped_stdout
            save_result = project.save()
        finally:
            if wrapped_stdout is not None:
                try:
                    wrapped_stdout.flush()
                    wrapped_stdout.detach()
                except Exception:
                    pass
                sys.stdout = stdout

        return {
            "name": name,
            "draft_path": str((self.draft_root / name).resolve()),
            "status": "created",
            "dependency": self.dependency_status(),
            "canvas": {"width": width, "height": height},
            "save_result": save_result,
            "applied_edits": edit_report["applied_edits"],
            "failed_edits": edit_report["failed_edits"],
        }

    def _apply_scene_edits(self, project: Any, video_segments: dict[str, Any], scene_plan: list[Any]) -> dict[str, list[dict[str, Any]]]:
        if not scene_plan:
            return {"applied_edits": [], "failed_edits": []}
        self._prepare_imports()
        import pyJianYingDraft as draft  # type: ignore
        from pyJianYingDraft import KeyframeProperty as KP  # type: ignore

        applied: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for index, item in enumerate(scene_plan):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            segment = video_segments.get(role)
            edit = item.get("edit") if isinstance(item.get("edit"), dict) else {}
            transition_name = str(edit.get("transition") or "").strip()
            animation_name = str(edit.get("animation") or "").strip()
            camera_name = str(edit.get("camera") or "").strip()
            if segment is None:
                for field_name, original_value in [
                    ("transition", transition_name),
                    ("animation", animation_name),
                    ("camera", camera_name),
                ]:
                    if original_value:
                        failed.append(self._failed_edit(role, field_name, original_value, "", "segment_not_found"))
                continue

            if transition_name and index > 0:
                mapped_transition = transition_name
                try:
                    mapped_transition = self._map_transition_name(transition_name)
                    result = project.add_transition_simple(mapped_transition, video_segment=segment, duration="0.6s")
                    if result is None:
                        failed.append(self._failed_edit(role, "transition", transition_name, mapped_transition, "enum_not_found"))
                    else:
                        applied.append(self._applied_edit(role, "transition", transition_name, mapped_transition))
                except Exception as exc:
                    failed.append(self._failed_edit(role, "transition", transition_name, mapped_transition, f"{type(exc).__name__}: {exc}"))
            elif transition_name:
                failed.append(self._failed_edit(role, "transition", transition_name, "", "first_segment_has_no_previous_transition_target"))

            if animation_name:
                try:
                    mapped_animation = self._apply_animation(segment, animation_name, draft, KP)
                    if mapped_animation:
                        applied.append(self._applied_edit(role, "animation", animation_name, mapped_animation))
                    else:
                        failed.append(self._failed_edit(role, "animation", animation_name, "", "enum_not_found_or_empty_timerange"))
                except Exception as exc:
                    failed.append(self._failed_edit(role, "animation", animation_name, "", f"{type(exc).__name__}: {exc}"))

            if camera_name:
                try:
                    mapped_camera = self._apply_camera(segment, camera_name, KP)
                    if mapped_camera:
                        applied.append(self._applied_edit(role, "camera", camera_name, mapped_camera))
                    else:
                        failed.append(self._failed_edit(role, "camera", camera_name, "", "unsupported_camera_or_empty_timerange"))
                except Exception as exc:
                    failed.append(self._failed_edit(role, "camera", camera_name, "", f"{type(exc).__name__}: {exc}"))

        return {"applied_edits": applied, "failed_edits": failed}

    def _applied_edit(self, role: str, field: str, original: str, applied: str) -> dict[str, Any]:
        return {
            "role": role,
            "field": field,
            "input": original,
            "applied": applied,
        }

    def _failed_edit(self, role: str, field: str, original: str, target: str, reason: str) -> dict[str, Any]:
        return {
            "role": role,
            "field": field,
            "input": original,
            "target": target,
            "reason": reason,
        }

    def _apply_animation(self, segment: Any, animation_name: str, draft: Any, keyframe_property: Any) -> str:
        if not animation_name:
            return ""
        normalized = self._normalize_keyword(animation_name)
        if any(token in normalized for token in ("zoomin", "zoom", "pushin", "push")):
            return "zoom_in" if self._apply_zoom_keyframes(segment, keyframe_property, scale=1.08) else ""
        if any(token in normalized for token in ("zoomout", "pullout")):
            return "zoom_out" if self._apply_zoom_keyframes(segment, keyframe_property, scale=0.94) else ""

        outro_name = self._map_outro_name(animation_name)
        if outro_name:
            enum_value = self._resolve_enum(draft.OutroType, outro_name)
            if enum_value:
                segment.add_animation(enum_value)
                return outro_name

        intro_name = self._map_intro_name(animation_name)
        enum_value = self._resolve_enum(draft.IntroType, intro_name)
        if enum_value:
            segment.add_animation(enum_value)
            return intro_name

        group_name = self._map_group_animation_name(animation_name)
        group_value = self._resolve_enum(draft.GroupAnimationType, group_name)
        if group_value:
            segment.add_animation(group_value)
            return group_name
        return ""

    def _apply_camera(self, segment: Any, camera_name: str, keyframe_property: Any) -> str:
        if not camera_name:
            return ""
        normalized = self._normalize_keyword(camera_name)
        if any(token in normalized for token in ("pushin", "push", "zoomin", "tuijin", "lajin")):
            return "push_in" if self._apply_zoom_keyframes(segment, keyframe_property, scale=1.12) else ""
        if any(token in normalized for token in ("pullout", "pull", "zoomout", "layuan")):
            return "pull_out" if self._apply_zoom_keyframes(segment, keyframe_property, scale=0.92) else ""
        if any(token in normalized for token in ("panleft", "moveleft", "left", "zuoyi")):
            return "pan_left" if self._apply_pan_keyframes(segment, keyframe_property, axis="x", start=-0.08, end=0.08) else ""
        if any(token in normalized for token in ("panright", "moveright", "right", "youyi")):
            return "pan_right" if self._apply_pan_keyframes(segment, keyframe_property, axis="x", start=0.08, end=-0.08) else ""
        if any(token in normalized for token in ("panup", "moveup", "up", "shangyi")):
            return "pan_up" if self._apply_pan_keyframes(segment, keyframe_property, axis="y", start=0.08, end=-0.08) else ""
        if any(token in normalized for token in ("pandown", "movedown", "down", "xiayi")):
            return "pan_down" if self._apply_pan_keyframes(segment, keyframe_property, axis="y", start=-0.08, end=0.08) else ""
        return ""

    def _apply_zoom_keyframes(self, segment: Any, keyframe_property: Any, scale: float) -> bool:
        duration = int(getattr(segment.target_timerange, "duration", 0) or 0)
        if duration <= 0:
            return False
        segment.add_keyframe(keyframe_property.uniform_scale, 0, 1.0)
        segment.add_keyframe(keyframe_property.uniform_scale, duration, float(scale))
        return True

    def _apply_pan_keyframes(self, segment: Any, keyframe_property: Any, *, axis: str, start: float, end: float) -> bool:
        duration = int(getattr(segment.target_timerange, "duration", 0) or 0)
        if duration <= 0:
            return False
        prop = keyframe_property.position_x if axis == "x" else keyframe_property.position_y
        segment.add_keyframe(prop, 0, float(start))
        segment.add_keyframe(prop, duration, float(end))
        return True

    def _resolve_enum(self, enum_cls: Any, name: str) -> Any:
        if not name:
            return None
        method = getattr(enum_cls, "from_name", None)
        if callable(method):
            try:
                return method(name)
            except Exception:
                pass
        normalized = self._normalize_keyword(name)
        for member_name in dir(enum_cls):
            if member_name.startswith("_"):
                continue
            if self._normalize_keyword(member_name) == normalized:
                return getattr(enum_cls, member_name)
        return None

    def _normalize_keyword(self, value: str) -> str:
        return "".join(ch for ch in str(value).lower() if ch.isalnum())

    def _map_transition_name(self, value: str) -> str:
        normalized = self._normalize_keyword(value)
        mapping = {
            "fade": "淡入淡出",
            "crossfade": "淡入淡出",
            "mix": "混合",
            "blend": "混合",
            "dissolve": "溶解",
            "wipe": "线性",
            "slide": "滑动",
            "push": "推进",
        }
        return mapping.get(normalized, value)

    def _map_intro_name(self, value: str) -> str:
        normalized = self._normalize_keyword(value)
        mapping = {
            "in": "淡入",
            "intro": "淡入",
            "fadein": "淡入",
            "appear": "淡入",
            "slidein": "向左滑入",
            "leftin": "向左滑入",
            "rightin": "向右滑入",
            "upin": "向上滑入",
            "downin": "向下滑入",
        }
        return mapping.get(normalized, value)

    def _map_outro_name(self, value: str) -> str | None:
        normalized = self._normalize_keyword(value)
        mapping = {
            "out": "淡出",
            "outro": "淡出",
            "fadeout": "淡出",
            "disappear": "淡出",
            "slideout": "向左滑出",
            "leftout": "向左滑出",
            "rightout": "向右滑出",
        }
        return mapping.get(normalized)

    def _map_group_animation_name(self, value: str) -> str:
        normalized = self._normalize_keyword(value)
        mapping = {
            "shake": "左右抖动",
            "glitch": "故障",
            "swing": "左右摇摆",
            "bounce": "弹跳",
            "flash": "闪烁",
        }
        return mapping.get(normalized, value)

    def _canvas_size(self, aspect_ratio: str) -> tuple[int, int]:
        normalized = aspect_ratio.strip().lower()
        if normalized in {"16:9", "landscape", "horizontal"}:
            return 1920, 1080
        if normalized in {"1:1", "square"}:
            return 1080, 1080
        return 1080, 1920

    def _safe_name(self, value: str) -> str:
        safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_")
        return safe_name or "jianying_sdk_draft"

    def _build_sdk_text_style(self, config: dict[str, Any]) -> Any:
        import pyJianYingDraft as draft  # type: ignore

        kwargs: dict[str, Any] = {}
        for key in ("size", "bold", "italic", "underline", "alpha", "align", "vertical", "letter_spacing", "line_spacing", "auto_wrapping", "max_line_width"):
            if key in config and config[key] not in (None, ""):
                kwargs[key] = config[key]
        color = config.get("color")
        if isinstance(color, (list, tuple)) and len(color) == 3:
            kwargs["color"] = tuple(float(v) for v in color)
        return draft.TextStyle(**kwargs) if kwargs else None

    def _build_sdk_text_background(self, config: dict[str, Any]) -> Any:
        import pyJianYingDraft as draft  # type: ignore

        color = config.get("color")
        if not color:
            return None
        kwargs = {"color": str(color)}
        for key in ("style", "alpha", "round_radius", "height", "width", "horizontal_offset", "vertical_offset"):
            if key in config and config[key] not in (None, ""):
                kwargs[key] = config[key]
        return draft.TextBackground(**kwargs)

    def _build_sdk_clip_settings(self, config: dict[str, Any]) -> Any:
        if not config:
            return None
        import pyJianYingDraft as draft  # type: ignore

        kwargs: dict[str, Any] = {}
        for key in ("alpha", "rotation", "scale_x", "scale_y", "transform_x", "transform_y", "flip_horizontal", "flip_vertical"):
            if key in config and config[key] not in (None, ""):
                kwargs[key] = config[key]
        return draft.ClipSettings(**kwargs) if kwargs else None
