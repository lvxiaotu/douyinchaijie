from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.app.task_store import (
    delete_task,
    get_task,
    list_task_events,
    list_tasks,
    save_analysis_archive,
    save_production_reverse_archive,
    save_prompt_reverse_archive,
)
from backend.app.video_analysis_queue import delete_ai_video_job, get_ai_video_job, list_ai_model_runs

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def attach_ai_video_model_runs(task: dict[str, Any]) -> dict[str, Any]:
    if task.get("type") != "ai_video_analysis":
        return task
    runs = list_ai_model_runs(str(task.get("id") or ""))
    if not runs:
        return task
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    task["result"] = {**result, "model_runs": runs}
    task["model_runs"] = runs
    return task


@router.get("")
def tasks(
    task_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    include_result: bool = Query(default=False),
    include_events: bool = Query(default=False),
) -> list[dict[str, Any]]:
    rows = list_tasks(
        task_type=task_type,
        limit=limit,
        include_result=include_result,
        include_events=include_events,
    )
    if task_type == "ai_video_analysis" and include_result:
        return [attach_ai_video_model_runs(task) for task in rows]
    return rows


@router.get("/{task_id}")
def task_detail(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return attach_ai_video_model_runs(task)


@router.get("/{task_id}/events")
def task_events(task_id: str, limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return list_task_events(task_id, limit=limit)


@router.post("/{task_id}/archive")
def archive_task(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("status") not in {"done", "completed"}:
        raise HTTPException(status_code=400, detail="Only completed tasks can be archived")

    video = (task.get("payload") or {}).get("video") or task.get("video") or {}
    result = task.get("result") or {}
    task_type = task.get("type")

    if task_type == "ai_video_analysis":
        result = {**result, "model_runs": list_ai_model_runs(task_id)}
        archive = save_analysis_archive(
            archive_id=task_id,
            task_id=task_id,
            title=task.get("title") or "AI 视频拆解",
            provider=task.get("provider") or "",
            video=video,
            result=result,
        )
        return {"status": "ok", "archive_type": "analysis", "archive": archive}

    if task_type == "ai_prompt_reverse":
        archive = save_prompt_reverse_archive(
            archive_id=task_id,
            task_id=task_id,
            title=task.get("title") or "AI 提示词反推",
            provider=task.get("provider") or "",
            video=video,
            result=result,
        )
        return {"status": "ok", "archive_type": "prompt", "archive": archive}

    if task_type == "ai_production_reverse":
        archive = save_production_reverse_archive(
            archive_id=task_id,
            task_id=task_id,
            title=task.get("title") or "AI 制作方式反推",
            provider=task.get("provider") or "",
            video=video,
            result=result,
        )
        return {"status": "ok", "archive_type": "production", "archive": archive}

    raise HTTPException(status_code=400, detail=f"Task type {task_type} cannot be archived")


@router.delete("/{task_id}")
def remove_task(task_id: str, delete_archives: bool = Query(default=True)) -> dict[str, Any]:
    task = get_task(task_id)
    if task and task.get("type") == "ai_video_analysis":
        job = get_ai_video_job(task_id)
        if job and job.get("status") in {"running", "claimed"}:
            raise HTTPException(status_code=409, detail="AI video task is running. Cancel it before deleting.")
        delete_ai_video_job(task_id)
    deleted = delete_task(task_id, delete_archives=delete_archives)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "deleted": True, "task_id": task_id, "delete_archives": delete_archives}
