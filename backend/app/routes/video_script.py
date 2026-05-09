from __future__ import annotations

import traceback
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from backend.app.ai_provider_state import active_ai_provider
from backend.app.task_store import connect, create_task, delete_task, update_task
from integrations.video_pipeline.script_generator import VideoScriptGenerator
from integrations.video_pipeline.script_schema import (
    BibleGenerateRequest,
    BlueprintGenerateRequest,
    ScriptExpandRequest,
    ScriptGenerateRequest,
    ScriptSaveRequest,
)

router = APIRouter(prefix="/api/tools/video-script", tags=["video-script"])


def generator() -> VideoScriptGenerator:
    return VideoScriptGenerator()


def run_script_generation_task(task_id: str, project_id: str, payload: ScriptGenerateRequest) -> None:
    try:
        provider = payload.provider or active_ai_provider("mock")
        update_task(task_id, status="running", progress=15, message=f"调用 AI 生成剧本：{provider}", provider=provider)

        def report(progress: int, message: str) -> None:
            update_task(task_id, status="running", progress=progress, message=message, provider=provider)

        result = generator().generate_with_project_id(payload, project_id, progress=report)
        update_task(task_id, status="running", progress=92, message="保存 script.json", result_json=result)
        update_task(task_id, status="done", progress=100, message="灵感剧本生成完成", provider=provider, result_json=result, error=None)
    except Exception as exc:
        traceback.print_exc()
        update_task(task_id, status="failed", progress=100, message="灵感剧本生成失败", error=f"{type(exc).__name__}: {exc}")


def run_blueprint_generation_task(task_id: str, project_id: str, payload: BlueprintGenerateRequest) -> None:
    try:
        provider = payload.provider or active_ai_provider("mock")
        update_task(task_id, status="running", progress=15, message=f"调用 AI 生成原子分镜：{provider}", provider=provider)

        def report(progress: int, message: str) -> None:
            update_task(task_id, status="running", progress=progress, message=message, provider=provider)

        result = generator().generate_blueprint_with_project_id(payload, project_id, progress=report)
        update_task(task_id, status="running", progress=92, message="保存 script.json", result_json=result)
        update_task(task_id, status="done", progress=100, message="资产清单生成完成", provider=provider, result_json=result, error=None)
    except Exception as exc:
        traceback.print_exc()
        update_task(task_id, status="failed", progress=100, message="资产清单生成失败", error=f"{type(exc).__name__}: {exc}")


@router.post("/generate")
def generate_script(payload: ScriptGenerateRequest, background_tasks: BackgroundTasks) -> dict:
    try:
        project_id = uuid4().hex
        task_id = f"video-script-{project_id}"
        task = create_task(
            task_id=task_id,
            task_type="video_script",
            title=payload.title or "灵感剧本",
            provider=payload.provider or active_ai_provider("mock"),
            payload={"project_id": project_id, "request": payload.model_dump()},
            message="已创建，等待生成灵感剧本",
        )
        background_tasks.add_task(run_script_generation_task, task_id, project_id, payload)
        return {**task, "project_id": project_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error_type": type(exc).__name__, "message": str(exc)}) from exc


@router.post("/bible")
def generate_bible(payload: BibleGenerateRequest) -> dict:
    try:
        return generator().generate_bible(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error_type": type(exc).__name__, "message": str(exc)}) from exc


@router.post("/blueprint")
def generate_blueprint(payload: BlueprintGenerateRequest, background_tasks: BackgroundTasks) -> dict:
    try:
        project_id = uuid4().hex
        task_id = f"video-script-{project_id}"
        task = create_task(
            task_id=task_id,
            task_type="video_script",
            title=payload.title or "资产清单",
            provider=payload.provider or active_ai_provider("mock"),
            payload={"project_id": project_id, "request": payload.model_dump()},
            message="已锁定设定，等待生成资产清单",
        )
        background_tasks.add_task(run_blueprint_generation_task, task_id, project_id, payload)
        return {**task, "project_id": project_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error_type": type(exc).__name__, "message": str(exc)}) from exc


@router.get("")
def list_scripts(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    return {"projects": generator().list_projects(limit=limit)}


@router.get("/{project_id}")
def get_script(project_id: str) -> dict:
    result = generator().load(project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Video script project not found")
    return result


@router.delete("/{project_id}")
def delete_script(project_id: str) -> dict:
    deleted = generator().delete_project(project_id)
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM tasks WHERE type = ? AND payload_json LIKE ?",
            ("video_script", f"%{project_id}%"),
        ).fetchall()
    deleted_tasks = []
    for row in rows:
        if delete_task(row["id"], delete_archives=False):
            deleted_tasks.append(row["id"])
    if not deleted and not deleted_tasks:
        raise HTTPException(status_code=404, detail="Video script project not found")
    return {"status": "ok", "deleted": deleted, "project_id": project_id, "deleted_tasks": deleted_tasks}


@router.post("/{project_id}/save")
def save_script(project_id: str, payload: ScriptSaveRequest) -> dict:
    try:
        script = payload.script
        if script.project_id != project_id:
            raise ValueError("project_id in path and script do not match")
        return generator().save(script)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error_type": type(exc).__name__, "message": str(exc)}) from exc


@router.post("/{project_id}/expand")
def expand_script(project_id: str, payload: ScriptExpandRequest) -> dict:
    try:
        return generator().expand(project_id, payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error_type": type(exc).__name__, "message": str(exc)}) from exc
