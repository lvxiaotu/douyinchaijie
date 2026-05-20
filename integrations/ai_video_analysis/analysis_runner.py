from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.app.video_analysis_queue import AiVideoTaskCancelled, record_ai_video_artifact, upsert_ai_video_chunk


def run_evidence_breakdown(
    adapter: Any,
    video: dict[str, Any],
    *,
    evidence: dict[str, Any],
    progress: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    segments = evidence.get("analysis_segments") or []
    if not segments:
        raise RuntimeError("转写结果为空，无法进行分段爆款拆解。")

    max_segments = int(os.getenv("AI_VIDEO_MAX_SEGMENTS", "18"))
    selected_segments = segments[:max_segments]
    evidence_path = Path(str(evidence.get("evidence_path") or ""))
    task_id = evidence_path.parent.name if evidence_path.parent else ""
    checkpoint_dir = (evidence_path.parent if evidence_path.parent else adapter.output_dir) / "segment_breakdowns"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    resume_enabled = os.getenv("AI_VIDEO_RESUME_ENABLED", "true").lower() not in {"0", "false", "no"}
    if progress:
        skipped = len(segments) - len(selected_segments)
        suffix = f"，跳过 {skipped} 个超出上限片段" if skipped > 0 else ""
        progress(60, f"准备分段 AI 拆解：{len(selected_segments)} 个片段{suffix}")
    adapter._check_cancelled(task_id)
    genre_context = adapter._prompt_context(video, evidence)
    segment_breakdowns = []
    for index, segment in enumerate(selected_segments, start=1):
        adapter._check_cancelled(task_id)
        segment.setdefault("genre", genre_context["genre"])
        checkpoint_path = checkpoint_dir / f"{segment.get('segment_id') or index}.json"
        if resume_enabled and checkpoint_path.exists():
            try:
                parsed = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                segment_breakdowns.append(parsed)
                if progress:
                    progress(60 + int(25 * index / max(1, len(selected_segments))), f"断点续跑：复用第 {index}/{len(selected_segments)} 段拆解结果")
                continue
            except Exception:
                if progress:
                    progress(60, f"第 {index} 段 checkpoint 读取失败，重新拆解")
        if progress:
            progress(60 + int(20 * (index - 1) / max(1, len(selected_segments))), f"提交第 {index}/{len(selected_segments)} 段给模型：{segment.get('time_range')}")
        prompt = adapter._segment_breakdown_prompt(video, segment)
        image_paths = adapter._segment_image_paths(segment)
        if progress and image_paths:
            progress(60 + int(20 * (index - 1) / max(1, len(selected_segments))), f"附带关键帧网格图：{Path(image_paths[0]).name}")
        upsert_ai_video_chunk(
            task_id=task_id,
            chunk_index=index,
            start_time=float(segment.get("start") or 0),
            end_time=float(segment.get("end") or 0),
            status="running",
            transcript=str(segment.get("transcript") or ""),
            frame_count=len(segment.get("keyframes") or []),
            grid_uri=str((segment.get("keyframe_grid") or {}).get("image_path") or ""),
            increment_attempts=True,
            meta={"segment_id": segment.get("segment_id") or "", "time_range": segment.get("time_range") or ""},
        )
        started = time.perf_counter()
        try:
            adapter._check_cancelled(task_id)
            text = adapter._generate_text_json(prompt, action="请求模型生成分段拆解", image_paths=image_paths)
            adapter._check_cancelled(task_id)
            latency_ms = int((time.perf_counter() - started) * 1000)
            adapter._record_model_run(
                task_id=task_id,
                chunk_id=str(segment.get("segment_id") or index),
                purpose="segment_breakdown",
                input_uri=str((segment.get("keyframe_grid") or {}).get("image_path") or ""),
                output_uri=str(checkpoint_path),
                latency_ms=latency_ms,
                usage=adapter._consume_last_model_usage(),
            )
        except AiVideoTaskCancelled:
            upsert_ai_video_chunk(
                task_id=task_id,
                chunk_index=index,
                start_time=float(segment.get("start") or 0),
                end_time=float(segment.get("end") or 0),
                status="cancelled",
                transcript=str(segment.get("transcript") or ""),
                frame_count=len(segment.get("keyframes") or []),
                grid_uri=str((segment.get("keyframe_grid") or {}).get("image_path") or ""),
                error_message="Cancellation requested.",
                meta={"segment_id": segment.get("segment_id") or "", "time_range": segment.get("time_range") or ""},
            )
            raise
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            upsert_ai_video_chunk(
                task_id=task_id,
                chunk_index=index,
                start_time=float(segment.get("start") or 0),
                end_time=float(segment.get("end") or 0),
                status="failed",
                transcript=str(segment.get("transcript") or ""),
                frame_count=len(segment.get("keyframes") or []),
                grid_uri=str((segment.get("keyframe_grid") or {}).get("image_path") or ""),
                error_message=f"{type(exc).__name__}: {exc}",
                meta={"segment_id": segment.get("segment_id") or "", "time_range": segment.get("time_range") or ""},
            )
            adapter._record_model_run(
                task_id=task_id,
                chunk_id=str(segment.get("segment_id") or index),
                purpose="segment_breakdown",
                input_uri=str((segment.get("keyframe_grid") or {}).get("image_path") or ""),
                output_uri=str(checkpoint_path),
                status="failed",
                latency_ms=latency_ms,
                error_message=f"{type(exc).__name__}: {exc}",
            )
            raise
        parsed = adapter._parse_segment_json(text, segment)
        parsed["checkpoint_path"] = str(checkpoint_path)
        checkpoint_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        record_ai_video_artifact(
            task_id=task_id,
            type="segment_breakdown",
            uri=str(checkpoint_path),
            meta={"segment_id": segment.get("segment_id") or "", "chunk_index": index},
        )
        upsert_ai_video_chunk(
            task_id=task_id,
            chunk_index=index,
            start_time=float(segment.get("start") or 0),
            end_time=float(segment.get("end") or 0),
            status="done",
            transcript=str(segment.get("transcript") or ""),
            frame_count=len(segment.get("keyframes") or []),
            grid_uri=str((segment.get("keyframe_grid") or {}).get("image_path") or ""),
            vision_result_uri=str(checkpoint_path),
            meta={"segment_id": segment.get("segment_id") or "", "time_range": segment.get("time_range") or "", "segment_role": parsed.get("segment_role") or ""},
        )
        segment_breakdowns.append(parsed)
        if progress:
            role = parsed.get("segment_role") or "未标注角色"
            progress(60 + int(25 * index / max(1, len(selected_segments))), f"第 {index}/{len(selected_segments)} 段拆解完成：{role}")
        adapter._check_cancelled(task_id)

    if progress:
        progress(87, "提交全部分段结果，汇总全局爆款公式")
    adapter._check_cancelled(task_id)
    if os.getenv("AI_VIDEO_HIGHLIGHT_SCREENSHOTS", "true").lower() not in {"0", "false", "no"}:
        adapter._extract_highlight_screenshots(evidence=evidence, segment_breakdowns=segment_breakdowns, progress=progress)
        adapter._check_cancelled(task_id)
    global_checkpoint = checkpoint_dir.parent / "global_breakdown.json"
    if resume_enabled and global_checkpoint.exists():
        try:
            result = json.loads(global_checkpoint.read_text(encoding="utf-8"))
            if progress:
                progress(92, "断点续跑：复用全局爆款公式汇总")
        except Exception:
            result = _generate_global_breakdown(
                adapter,
                video,
                evidence=evidence,
                segment_breakdowns=segment_breakdowns,
                evidence_path=evidence_path,
                global_checkpoint=global_checkpoint,
                task_id=task_id,
            )
    else:
        result = _generate_global_breakdown(
            adapter,
            video,
            evidence=evidence,
            segment_breakdowns=segment_breakdowns,
            evidence_path=evidence_path,
            global_checkpoint=global_checkpoint,
            task_id=task_id,
        )
    if progress:
        progress(92, "全局爆款公式汇总完成，整理结果")
    adapter._check_cancelled(task_id)
    result["segment_breakdowns"] = segment_breakdowns
    return result


def _generate_global_breakdown(
    adapter: Any,
    video: dict[str, Any],
    *,
    evidence: dict[str, Any],
    segment_breakdowns: list[dict[str, Any]],
    evidence_path: Path,
    global_checkpoint: Path,
    task_id: str,
) -> dict[str, Any]:
    global_prompt = adapter._global_breakdown_prompt(video, evidence=evidence, segment_breakdowns=segment_breakdowns)
    started = time.perf_counter()
    try:
        adapter._check_cancelled(task_id)
        global_text = adapter._generate_global_summary_json(global_prompt, action="请求模型汇总全局爆款公式")
        adapter._check_cancelled(task_id)
        latency_ms = int((time.perf_counter() - started) * 1000)
        adapter._record_model_run(
            task_id=task_id,
            purpose="global_breakdown",
            input_uri=str(evidence_path),
            output_uri=str(global_checkpoint),
            latency_ms=latency_ms,
            usage=adapter._consume_last_model_usage(),
            provider=adapter._last_model_provider("global_breakdown"),
            model=adapter._last_model_name("global_breakdown"),
        )
    except AiVideoTaskCancelled:
        raise
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        adapter._record_model_run(
            task_id=task_id,
            purpose="global_breakdown",
            input_uri=str(evidence_path),
            output_uri=str(global_checkpoint),
            status="failed",
            latency_ms=latency_ms,
            error_message=f"{type(exc).__name__}: {exc}",
        )
        raise
    result = adapter._parse_model_json(global_text)
    result["checkpoint_path"] = str(global_checkpoint)
    global_checkpoint.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    record_ai_video_artifact(
        task_id=task_id,
        type="global_breakdown",
        uri=str(global_checkpoint),
        meta={"segment_count": len(segment_breakdowns)},
    )
    return result
