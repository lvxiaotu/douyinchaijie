from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.app.routes.douyin import read_env_map, write_env_values
from backend.app.task_store import create_task, update_task

router = APIRouter(prefix="/api/tools/runninghub-tts", tags=["runninghub-tts"])

ROOT = Path(__file__).resolve().parents[3]
UPLOAD_DIR = ROOT / "data" / "runtime" / "runninghub_tts"
DEFAULT_API_BASE = "https://www.runninghub.cn"
DEFAULT_WORKFLOW_KEY = "runninghub/tts_index2.json"
WORKFLOW_ID_MAP = {
    "runninghub/tts_index2.json": "1983718528991862786",
    "runninghub/tts_edge.json": "1983513964837543938",
    "runninghub/tts_spark.json": "1983921902282539009",
}


class RunningHubTtsConfigPayload(BaseModel):
    api_key: str = Field(default="")
    api_base: str = Field(default=DEFAULT_API_BASE)
    workflow_key: str = Field(default=DEFAULT_WORKFLOW_KEY)
    instance_type: str = Field(default="")
    poll_interval_seconds: float = Field(default=3, ge=1, le=30)


class RunningHubTtsJobPayload(BaseModel):
    text: str = Field(min_length=1)
    workflow_key: str = Field(default=DEFAULT_WORKFLOW_KEY)
    api_key: str | None = Field(default=None)
    api_base: str | None = Field(default=None)
    ref_audio_path: str | None = Field(default=None)
    ref_audio_url: str | None = Field(default=None)
    voice: str | None = Field(default=None)
    speed: float | None = Field(default=None)


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _env_get_bool(value: str | None) -> bool:
    return bool(value and value.strip())


def _http_json(response: requests.Response) -> dict[str, Any]:
    try:
        return response.json()
    except Exception:
        return {"raw": response.text}


def _raise_http(response: requests.Response, message: str | None = None) -> None:
    payload = _http_json(response)
    detail = message or payload.get("message") or payload.get("msg") or payload.get("error") or response.text[:500]
    raise HTTPException(status_code=response.status_code or 502, detail={"message": detail, "payload": payload})


def _auth_headers(api_key: str) -> dict[str, str]:
    if not api_key:
        raise HTTPException(status_code=400, detail={"message": "RunningHub API key is required"})
    return {"Authorization": f"Bearer {api_key}"}


def _resolve_workflow_id(workflow_key: str) -> str:
    return WORKFLOW_ID_MAP.get(workflow_key, workflow_key.split("/", 1)[-1].removesuffix(".json"))


def _upload_reference_audio(api_base: str, api_key: str, path: Path) -> str:
    if not path.exists():
        raise HTTPException(status_code=400, detail={"message": "Reference audio file not found"})
    endpoint = f"{api_base.rstrip('/')}/task/openapi/upload"
    with path.open("rb") as handle:
        response = requests.post(
            endpoint,
            headers=_auth_headers(api_key),
            files={"file": (path.name, handle, "audio/wav")},
            data={"apiKey": api_key, "fileType": "audio"},
            timeout=120,
        )
    payload = _http_json(response)
    if not response.ok:
        _raise_http(response)
    return (
        payload.get("data", {}).get("fileName")
        or payload.get("data", {}).get("fileUrl")
        or payload.get("data", {}).get("url")
        or payload.get("fileName")
        or payload.get("fileUrl")
        or payload.get("url")
        or ""
    )


def _submit_runninghub_task(api_base: str, api_key: str, workflow_key: str, text: str, ref_audio: str | None, voice: str | None, speed: float | None) -> dict[str, Any]:
    node_info_list: list[dict[str, Any]] = [
        {"nodeId": "3", "fieldName": "text", "fieldValue": text},
    ]
    if ref_audio:
        node_info_list.append({"nodeId": "12", "fieldName": "audio", "fieldValue": ref_audio})
    if voice:
        node_info_list.append({"nodeId": "5", "fieldName": "voice", "fieldValue": voice})
    if speed is not None:
        node_info_list.append({"nodeId": "5", "fieldName": "speed", "fieldValue": speed})

    response = requests.post(
        f"{api_base.rstrip('/')}/task/openapi/create",
        headers={**_auth_headers(api_key), "Content-Type": "application/json"},
        json={
            "apiKey": api_key,
            "workflowId": _resolve_workflow_id(workflow_key),
            "nodeInfoList": node_info_list,
        },
        timeout=120,
    )
    payload = _http_json(response)
    if not response.ok:
        _raise_http(response)
    return payload


def _query_task_status(api_base: str, api_key: str, task_id: str) -> dict[str, Any]:
    response = requests.post(
        f"{api_base.rstrip('/')}/task/openapi/status",
        headers={**_auth_headers(api_key), "Content-Type": "application/json"},
        json={"apiKey": api_key, "taskId": task_id},
        timeout=60,
    )
    payload = _http_json(response)
    if not response.ok:
        _raise_http(response)
    return payload


def _query_task_outputs(api_base: str, api_key: str, task_id: str) -> dict[str, Any]:
    response = requests.post(
        f"{api_base.rstrip('/')}/task/openapi/outputs",
        headers={**_auth_headers(api_key), "Content-Type": "application/json"},
        json={"apiKey": api_key, "taskId": task_id},
        timeout=60,
    )
    payload = _http_json(response)
    if not response.ok:
        _raise_http(response)
    return payload


def _poll_runninghub_task(api_base: str, api_key: str, task_id: str, poll_interval_seconds: float) -> dict[str, Any]:
    deadline = time.time() + 600
    while time.time() < deadline:
        if not task_id:
            raise HTTPException(status_code=500, detail={"message": "RunningHub did not return a taskId"})
        status_payload = _query_task_status(api_base, api_key, task_id)
        status_text = str(
            status_payload.get("data", {}).get("taskStatus")
            or status_payload.get("data", {}).get("status")
            or status_payload.get("taskStatus")
            or status_payload.get("status")
            or ""
        ).upper()
        if status_text in {"SUCCESS", "DONE", "COMPLETED"}:
            return _query_task_outputs(api_base, api_key, task_id)
        if status_text in {"FAILED", "ERROR", "CANCELLED", "CANCELED"}:
            raise HTTPException(status_code=502, detail={"message": "RunningHub task failed", "status": status_payload})
        time.sleep(poll_interval_seconds)
    raise HTTPException(status_code=504, detail={"message": "RunningHub task timed out", "task_id": task_id})


def _run_tts_job(task_id: str, payload: RunningHubTtsJobPayload) -> None:
    config = get_config()
    api_key = payload.api_key or config["api_key"]
    api_base = payload.api_base or config["api_base"]
    poll_interval_seconds = float(config["poll_interval_seconds"])
    if not api_key:
        update_task(task_id, status="error", progress=100, message="缺少 RunningHub API Key", error="Missing RunningHub API key")
        return

    try:
        update_task(task_id, status="running", progress=10, message="准备提交 RunningHub 任务")
        ref_audio = payload.ref_audio_url
        if payload.ref_audio_path:
            ref_audio = _upload_reference_audio(api_base, api_key, Path(payload.ref_audio_path))
        submit = _submit_runninghub_task(api_base, api_key, payload.workflow_key, payload.text, ref_audio, payload.voice, payload.speed)
        remote_task_id = str(submit.get("data", {}).get("taskId") or submit.get("taskId") or "")
        update_task(task_id, status="running", progress=35, message="RunningHub 已接收任务", result_json={"submit": submit, "remote_task_id": remote_task_id})
        outputs = _poll_runninghub_task(api_base, api_key, remote_task_id or task_id, poll_interval_seconds)
        update_task(task_id, status="done", progress=100, message="TTS 完成", result_json={"submit": submit, "outputs": outputs}, error=None)
    except Exception as exc:
        update_task(task_id, status="error", progress=100, message="RunningHub TTS 失败", error=f"{type(exc).__name__}: {exc}")


@router.get("/config")
def get_config() -> dict[str, Any]:
    env = read_env_map()
    return {
        "api_key": env.get("RUNNINGHUB_API_KEY", ""),
        "api_base": env.get("RUNNINGHUB_API_BASE", DEFAULT_API_BASE),
        "workflow_key": env.get("RUNNINGHUB_TTS_WORKFLOW", DEFAULT_WORKFLOW_KEY),
        "instance_type": env.get("RUNNINGHUB_INSTANCE_TYPE", ""),
        "poll_interval_seconds": float(env.get("RUNNINGHUB_POLL_INTERVAL_SECONDS", "3") or 3),
        "available_workflows": [
            {"key": key, "workflow_id": value, "label": key.split("/", 1)[-1]} for key, value in WORKFLOW_ID_MAP.items()
        ],
    }


@router.get("/status")
def status() -> dict[str, Any]:
    config = get_config()
    return {
        "ready": _env_get_bool(config["api_key"]),
        "workflow_key": config["workflow_key"],
        "api_base": config["api_base"],
        "instance_type": config["instance_type"],
    }


@router.post("/config")
def save_config(payload: RunningHubTtsConfigPayload) -> dict[str, Any]:
    write_env_values(
        {
            "RUNNINGHUB_API_KEY": payload.api_key,
            "RUNNINGHUB_API_BASE": payload.api_base,
            "RUNNINGHUB_TTS_WORKFLOW": payload.workflow_key,
            "RUNNINGHUB_INSTANCE_TYPE": payload.instance_type,
            "RUNNINGHUB_POLL_INTERVAL_SECONDS": str(payload.poll_interval_seconds),
        }
    )
    return {"status": "ok", "config": get_config()}


@router.post("/upload")
async def upload_reference_audio(file: UploadFile = File(...)) -> dict[str, Any]:
    _ensure_upload_dir()
    target = UPLOAD_DIR / file.filename
    content = await file.read()
    target.write_bytes(content)
    return {"status": "ok", "path": str(target), "size": len(content)}


@router.post("/jobs")
def create_job(payload: RunningHubTtsJobPayload, background_tasks: BackgroundTasks) -> dict[str, Any]:
    task_id = f"runninghub-tts-{uuid4().hex}"
    task = create_task(
        task_id=task_id,
        task_type="runninghub_tts",
        title=payload.text[:48] or "RunningHub TTS",
        provider="runninghub",
        payload=payload.model_dump(),
        message="已创建 RunningHub TTS 任务",
    )
    background_tasks.add_task(_run_tts_job, task_id, payload)
    return task
