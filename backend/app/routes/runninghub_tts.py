from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.app.routes.douyin import read_env_map, write_env_values
from backend.app.task_store import create_task, get_task, list_tasks, update_task

router = APIRouter(prefix="/api/tools/runninghub-tts", tags=["runninghub-tts"])

ROOT = Path(__file__).resolve().parents[3]
UPLOAD_DIR = ROOT / "data" / "runtime" / "runninghub_tts"
DEFAULT_API_BASE = "https://www.runninghub.cn"
DEFAULT_WORKFLOW_KEY = "runninghub/tts_stable_emotion.json"
DEFAULT_STATUS_TIMEOUT_SECONDS = 600
WORKFLOW_ID_MAP = {
    "runninghub/tts_stable_emotion.json": "2053641347223044097",
    "runninghub/tts_index2.json": "1983718528991862786",
    "runninghub/tts_edge.json": "1983513964837543938",
    "runninghub/tts_spark.json": "1983921902282539009",
}


class RunningHubTtsConfigPayload(BaseModel):
    api_key: str = Field(default="")
    api_base: str = Field(default=DEFAULT_API_BASE)
    workflow_key: str = Field(default=DEFAULT_WORKFLOW_KEY)
    workflow_id: str | None = Field(default=None)
    instance_type: str = Field(default="")
    poll_interval_seconds: float = Field(default=3, ge=1, le=30)


class RunningHubTtsJobPayload(BaseModel):
    text: str = Field(min_length=1)
    workflow_key: str = Field(default=DEFAULT_WORKFLOW_KEY)
    workflow_id: str | None = Field(default=None)
    api_key: str | None = Field(default=None)
    api_base: str | None = Field(default=None)
    instance_type: str | None = Field(default=None)
    ref_audio_path: str | None = Field(default=None)
    ref_audio_url: str | None = Field(default=None)
    voice: str | None = Field(default=None)
    speed: float | None = Field(default=None)
    enable_duration_control: bool | None = Field(default=None)
    duration_mode: str | None = Field(default=None)
    speed_multiplier: float | None = Field(default=None)
    target_duration: float | None = Field(default=None)
    enable_emotion_control: bool | None = Field(default=None)
    emotion_mode: str | None = Field(default=None)
    emotion_audio_path: str | None = Field(default=None)
    emotion_audio_url: str | None = Field(default=None)
    emotion_alpha: float | None = Field(default=None)
    emotion_text: str | None = Field(default=None)
    happy: float | None = Field(default=None)
    angry: float | None = Field(default=None)
    sad: float | None = Field(default=None)
    fear: float | None = Field(default=None)
    hate: float | None = Field(default=None)
    love: float | None = Field(default=None)
    surprise: float | None = Field(default=None)
    neutral: float | None = Field(default=None)


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _env_get_bool(value: str | None) -> bool:
    return bool(value and value.strip())


def _http_json(response: requests.Response) -> dict[str, Any]:
    try:
        return response.json()
    except Exception:
        return {"raw": response.text}


def _auth_headers(api_key: str) -> dict[str, str]:
    if not api_key:
        raise HTTPException(status_code=400, detail={"message": "RunningHub API key is required"})
    return {"Authorization": f"Bearer {api_key}"}


def _payload_message(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, str) and data.strip():
        return data.strip()
    candidates: list[Any] = [
        payload.get("message"),
        payload.get("msg"),
        payload.get("error"),
        payload.get("errorMessage"),
        payload.get("errorMessages"),
        payload.get("detail"),
    ]
    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("message"),
                data.get("msg"),
                data.get("error"),
                data.get("errorMessage"),
                data.get("promptTips"),
                data.get("status"),
                data.get("taskStatus"),
            ]
        )
    for value in candidates:
        if isinstance(value, list):
            value = "；".join(str(item) for item in value if item)
        if value:
            return str(value)
    return ""


def _normalize_emotion_mode(mode: str | None) -> str | None:
    if mode is None:
        return None
    normalized = str(mode).strip().lower()
    if not normalized:
        return None
    aliases = {
        "text_prompt": "text_description",
        "text": "text_description",
        "text_desc": "text_description",
        "emotion_text": "text_description",
        "vector": "emotion_vector",
        "emotion": "emotion_vector",
        "audio": "audio_prompt",
    }
    return aliases.get(normalized, normalized)


def _extract_failed_reason(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data")
    failed_reason = data.get("failedReason") if isinstance(data, dict) else None
    if not isinstance(failed_reason, dict):
        failed_reason = payload.get("failedReason")
    if not isinstance(failed_reason, dict):
        return ""

    node_name = failed_reason.get("node_name") or failed_reason.get("nodeName") or ""
    node_id = failed_reason.get("node_id") or failed_reason.get("nodeId") or ""
    exception_message = failed_reason.get("exception_message") or failed_reason.get("exceptionMessage") or ""
    traceback = failed_reason.get("traceback")
    traceback_text = ""
    if isinstance(traceback, list):
        traceback_text = " ".join(str(item) for item in traceback if item)
    elif traceback:
        traceback_text = str(traceback)

    details = [part for part in [exception_message, traceback_text] if part]
    message = " | ".join(details)
    prefix = f"{node_name} (node {node_id})" if node_name and node_id else str(node_name or node_id or "")
    if prefix and message:
        return f"{prefix}: {message}"
    return prefix or message


def _raise_runninghub_error(
    payload: dict[str, Any],
    *,
    status_code: int = 502,
    message: str | None = None,
    default_message: str = "RunningHub API 调用失败",
) -> None:
    detail = message or _payload_message(payload) or default_message
    raise HTTPException(status_code=status_code, detail={"message": detail, "payload": payload})


def _raise_http(response: requests.Response, message: str | None = None) -> None:
    payload = _http_json(response)
    _raise_runninghub_error(
        payload,
        status_code=response.status_code or 502,
        message=message,
        default_message=response.text[:500] or "RunningHub HTTP 请求失败",
    )


def _runninghub_ok(payload: dict[str, Any]) -> bool:
    return payload.get("code") in (0, "0", None, "SUCCESS", "success")


def _runninghub_post(api_base: str, api_key: str, path: str, body: dict[str, Any], *, timeout: int = 60) -> dict[str, Any]:
    response = requests.post(
        f"{api_base.rstrip('/')}{path}",
        headers={**_auth_headers(api_key), "Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    payload = _http_json(response)
    if not response.ok:
        _raise_http(response)
    if not _runninghub_ok(payload):
        _raise_runninghub_error(payload)
    return payload


def _runninghub_post_allow_failure_detail(
    api_base: str,
    api_key: str,
    path: str,
    body: dict[str, Any],
    *,
    timeout: int = 60,
) -> dict[str, Any]:
    response = requests.post(
        f"{api_base.rstrip('/')}{path}",
        headers={**_auth_headers(api_key), "Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    payload = _http_json(response)
    if not response.ok:
        _raise_http(response)
    if not _runninghub_ok(payload) and not _extract_failed_reason(payload):
        _raise_runninghub_error(payload)
    return payload


def _resolve_workflow_id(workflow_key: str | None, workflow_id: str | None = None) -> str:
    explicit = str(workflow_id or "").strip()
    if explicit:
        if "/workflow/" in explicit:
            explicit = explicit.rstrip("/").split("/workflow/")[-1].split("?")[0]
        return explicit
    fallback = str(workflow_key or "").strip()
    if not fallback:
        raise HTTPException(status_code=400, detail={"message": "Workflow ID 不能为空"})
    if fallback in WORKFLOW_ID_MAP:
        return WORKFLOW_ID_MAP[fallback]
    if "/workflow/" in fallback:
        return fallback.rstrip("/").split("/workflow/")[-1].split("?")[0]
    if fallback.isdigit():
        return fallback
    return fallback.split("/", 1)[-1].removesuffix(".json")


def _extract_prompt_json(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    prompt_raw = data.get("prompt") if isinstance(data, dict) else None
    if not prompt_raw:
        _raise_runninghub_error(payload, message="RunningHub 未返回 workflow prompt", default_message="缺少 workflow prompt")
    try:
        return json.loads(prompt_raw)
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"message": f"解析 workflow prompt 失败: {exc}", "payload": payload}) from exc


def _workflow_meta(api_base: str, api_key: str, workflow_id: str) -> dict[str, Any]:
    payload = _runninghub_post(
        api_base,
        api_key,
        "/api/openapi/getJsonApiFormat",
        {"apiKey": api_key, "workflowId": workflow_id},
        timeout=120,
    )
    return {"payload": payload, "prompt": _extract_prompt_json(payload)}


def _iter_inputs(prompt: dict[str, Any]) -> list[tuple[str, str, Any, str]]:
    items: list[tuple[str, str, Any, str]] = []
    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        title = str((node.get("_meta") or {}).get("title") or node.get("class_type") or node_id)
        for field_name, value in inputs.items():
            items.append((str(node_id), str(field_name), value, title))
    return items


def _find_input_node(
    prompt: dict[str, Any],
    *,
    title_tokens: tuple[str, ...] = (),
    field_tokens: tuple[str, ...] = (),
    prefer_scalar: bool = False,
) -> tuple[str, str] | None:
    normalized_titles = tuple(token.lower() for token in title_tokens if token)
    normalized_fields = tuple(token.lower() for token in field_tokens if token)
    candidates: list[tuple[str, str, Any, str]] = []
    for node_id, field_name, value, title in _iter_inputs(prompt):
        title_lower = title.lower()
        field_lower = field_name.lower()
        if normalized_titles and not any(token in title_lower for token in normalized_titles):
            continue
        if normalized_fields and not any(token in field_lower for token in normalized_fields):
            continue
        candidates.append((node_id, field_name, value, title))
    if prefer_scalar:
        scalar_candidates = [item for item in candidates if not isinstance(item[2], list)]
        if scalar_candidates:
            candidates = scalar_candidates
    return (candidates[0][0], candidates[0][1]) if candidates else None


def _find_field_by_name(
    prompt: dict[str, Any],
    *field_names: str,
    title_tokens: tuple[str, ...] = (),
    prefer_scalar: bool = False,
) -> tuple[str, str] | None:
    normalized_names = tuple(name.lower() for name in field_names if name)
    normalized_titles = tuple(token.lower() for token in title_tokens if token)
    candidates: list[tuple[str, str, Any, str]] = []
    for node_id, field_name, value, title in _iter_inputs(prompt):
        field_lower = field_name.lower()
        title_lower = title.lower()
        if normalized_names and field_lower not in normalized_names:
            continue
        if normalized_titles and not any(token in title_lower for token in normalized_titles):
            continue
        candidates.append((node_id, field_name, value, title))
    if prefer_scalar:
        scalar_candidates = [item for item in candidates if not isinstance(item[2], list)]
        if scalar_candidates:
            candidates = scalar_candidates
    return (candidates[0][0], candidates[0][1]) if candidates else None


def _normalize_numeric_value(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _append_node_value(
    node_info_list: list[dict[str, Any]],
    prompt: dict[str, Any],
    value: Any,
    *,
    field_names: tuple[str, ...] = (),
    title_tokens: tuple[str, ...] = (),
    prefer_scalar: bool = False,
) -> bool:
    if value is None or value == "":
        return False
    value = _normalize_numeric_value(value)
    node = _find_field_by_name(
        prompt,
        *field_names,
        title_tokens=title_tokens,
        prefer_scalar=prefer_scalar,
    )
    if not node and field_names:
        node = _find_input_node(
            prompt,
            title_tokens=title_tokens,
            field_tokens=field_names,
            prefer_scalar=prefer_scalar,
        )
    if not node:
        return False
    node_info_list.append({"nodeId": node[0], "fieldName": node[1], "fieldValue": value})
    return True


def _append_linked_input_value(
    node_info_list: list[dict[str, Any]],
    prompt: dict[str, Any],
    value: Any,
    *,
    field_names: tuple[str, ...] = (),
    title_tokens: tuple[str, ...] = (),
    upstream_field_names: tuple[str, ...] = ("audio",),
) -> bool:
    if value is None or value == "":
        return False
    value = _normalize_numeric_value(value)
    node = _find_field_by_name(
        prompt,
        *field_names,
        title_tokens=title_tokens,
        prefer_scalar=False,
    )
    if not node and field_names:
        node = _find_input_node(
            prompt,
            title_tokens=title_tokens,
            field_tokens=field_names,
            prefer_scalar=False,
        )
    if not node:
        return False

    node_data = prompt.get(node[0]) if isinstance(prompt, dict) else None
    linked_value = None
    if isinstance(node_data, dict):
        inputs = node_data.get("inputs")
        if isinstance(inputs, dict):
            linked_value = inputs.get(node[1])
    if not (isinstance(linked_value, list) and linked_value):
        return False

    upstream_node_id = str(linked_value[0])
    upstream_node = prompt.get(upstream_node_id) if isinstance(prompt, dict) else None
    if not isinstance(upstream_node, dict):
        return False
    upstream_inputs = upstream_node.get("inputs")
    if not isinstance(upstream_inputs, dict):
        return False

    for upstream_field_name in upstream_field_names:
        if upstream_field_name in upstream_inputs:
            node_info_list.append(
                {
                    "nodeId": upstream_node_id,
                    "fieldName": upstream_field_name,
                    "fieldValue": value,
                }
            )
            return True
    return False


def _append_first_matching_node_value(
    node_info_list: list[dict[str, Any]],
    prompt: dict[str, Any],
    value: Any,
    *,
    field_name_groups: tuple[tuple[str, ...], ...],
    title_tokens: tuple[str, ...] = (),
    prefer_scalar: bool = False,
) -> bool:
    if value is None or value == "":
        return False
    for field_names in field_name_groups:
        if _append_node_value(
            node_info_list,
            prompt,
            value,
            field_names=field_names,
            title_tokens=title_tokens,
            prefer_scalar=prefer_scalar,
        ):
            return True
    return False


def _build_node_info_list(
    prompt: dict[str, Any],
    *,
    text: str,
    ref_audio: str | None,
    voice: str | None,
    speed: float | None,
    enable_duration_control: bool | None = None,
    duration_mode: str | None = None,
    speed_multiplier: float | None = None,
    target_duration: float | None = None,
    enable_emotion_control: bool | None = None,
    emotion_mode: str | None = None,
    emotion_audio: str | None = None,
    emotion_alpha: float | None = None,
    emotion_text: str | None = None,
    emotion_sliders: dict[str, float | None] | None = None,
) -> list[dict[str, Any]]:
    emotion_mode = _normalize_emotion_mode(emotion_mode)
    text_node = _find_input_node(
        prompt,
        title_tokens=("$text", "text _o", "text"),
        field_tokens=("text",),
        prefer_scalar=True,
    )
    if not text_node:
        text_node = _find_field_by_name(prompt, "text", prefer_scalar=True)
    if not text_node:
        raise HTTPException(status_code=400, detail={"message": "未在 workflow 中找到文本输入节点"})

    node_info_list: list[dict[str, Any]] = [
        {"nodeId": text_node[0], "fieldName": text_node[1], "fieldValue": text},
    ]

    if ref_audio:
        appended_ref_audio = _append_linked_input_value(
            node_info_list,
            prompt,
            ref_audio,
            field_names=("speaker_audio", "reference_audio", "ref_audio", "audio_prompt"),
            title_tokens=("advanced", "index", "tts", "voice", "speaker", "audio"),
        )
        if not appended_ref_audio:
            appended_ref_audio = _append_first_matching_node_value(
                node_info_list,
                prompt,
                ref_audio,
                field_name_groups=(
                    ("speaker_audio",),
                    ("reference_audio",),
                    ("ref_audio",),
                    ("audio_prompt",),
                ),
                title_tokens=("advanced", "index", "tts", "voice", "speaker", "audio"),
            )
        if not appended_ref_audio:
            _append_node_value(
                node_info_list,
                prompt,
                ref_audio,
                field_names=("audio",),
                title_tokens=("$ref_audio", "audio upload", "load audio"),
            )

    if voice:
        voice_node = _find_input_node(
            prompt,
            title_tokens=("voice", "tts", "index"),
            field_tokens=("voice", "speaker", "character"),
            prefer_scalar=True,
        )
        if voice_node:
            node_info_list.append({"nodeId": voice_node[0], "fieldName": voice_node[1], "fieldValue": voice})

    if speed is not None:
        speed_node = _find_input_node(
            prompt,
            title_tokens=("voice", "tts", "index"),
            field_tokens=("speed", "rate"),
            prefer_scalar=True,
        )
        if speed_node:
            node_info_list.append({"nodeId": speed_node[0], "fieldName": speed_node[1], "fieldValue": speed})

    _append_node_value(
        node_info_list,
        prompt,
        enable_duration_control,
        field_names=("enable_duration_control",),
        title_tokens=("advanced", "duration", "tts", "index"),
        prefer_scalar=True,
    )
    _append_node_value(
        node_info_list,
        prompt,
        duration_mode,
        field_names=("duration_mode",),
        title_tokens=("advanced", "duration", "tts", "index"),
        prefer_scalar=True,
    )
    _append_node_value(
        node_info_list,
        prompt,
        speed_multiplier,
        field_names=("speed_multiplier",),
        title_tokens=("advanced", "duration", "tts", "index"),
        prefer_scalar=True,
    )
    _append_node_value(
        node_info_list,
        prompt,
        target_duration,
        field_names=("target_duration",),
        title_tokens=("advanced", "duration", "tts", "index"),
        prefer_scalar=True,
    )

    _append_node_value(
        node_info_list,
        prompt,
        enable_emotion_control,
        field_names=("enable_emotion_control",),
        title_tokens=("advanced", "emotion", "tts", "index"),
        prefer_scalar=True,
    )
    _append_node_value(
        node_info_list,
        prompt,
        emotion_mode,
        field_names=("emotion_mode",),
        title_tokens=("advanced", "emotion", "tts", "index"),
        prefer_scalar=True,
    )
    _append_node_value(
        node_info_list,
        prompt,
        emotion_audio,
        field_names=("emotion_audio",),
        title_tokens=("advanced", "emotion", "tts", "index"),
        prefer_scalar=True,
    )
    _append_node_value(
        node_info_list,
        prompt,
        emotion_alpha,
        field_names=("emotion_alpha",),
        title_tokens=("advanced", "emotion", "tts", "index"),
        prefer_scalar=True,
    )
    _append_node_value(
        node_info_list,
        prompt,
        emotion_text,
        field_names=("emotion_text",),
        title_tokens=("advanced", "emotion", "tts", "index"),
        prefer_scalar=True,
    )

    for field_name, field_value in (emotion_sliders or {}).items():
        slider_field_groups: dict[str, tuple[tuple[str, ...], ...]] = {
            "love": (("love",), ("low",)),
        }
        if not _append_first_matching_node_value(
            node_info_list,
            prompt,
            field_value,
            field_name_groups=slider_field_groups.get(field_name, ((field_name,),)),
            title_tokens=("advanced", "emotion", "tts", "index"),
            prefer_scalar=True,
        ):
            continue

    return node_info_list


def _normalize_ref_audio_path(raw_path: str | None) -> str | None:
    if not raw_path:
        return None
    candidate = Path(raw_path)
    if candidate.exists():
        return str(candidate)
    recent_uploads = sorted(UPLOAD_DIR.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True)
    if recent_uploads:
        return str(recent_uploads[0])
    return str(candidate)


def _upload_reference_audio(api_base: str, api_key: str, path: Path) -> str:
    if not path.exists():
        raise HTTPException(status_code=400, detail={"message": "Reference audio file not found"})
    with path.open("rb") as handle:
        response = requests.post(
            f"{api_base.rstrip('/')}/task/openapi/upload",
            headers=_auth_headers(api_key),
            files={"file": (path.name, handle, "audio/wav")},
            data={"apiKey": api_key, "fileType": "audio"},
            timeout=120,
        )
    payload = _http_json(response)
    if not response.ok:
        _raise_http(response)
    if not _runninghub_ok(payload):
        _raise_runninghub_error(payload, default_message="上传参考音频失败")
    return (
        payload.get("data", {}).get("fileName")
        or payload.get("data", {}).get("fileUrl")
        or payload.get("data", {}).get("url")
        or payload.get("fileName")
        or payload.get("fileUrl")
        or payload.get("url")
        or ""
    )


def _submit_runninghub_task(
    api_base: str,
    api_key: str,
    workflow_key: str | None,
    workflow_id: str | None,
    instance_type: str | None,
    text: str,
    ref_audio: str | None,
    voice: str | None,
    speed: float | None,
    enable_duration_control: bool | None = None,
    duration_mode: str | None = None,
    speed_multiplier: float | None = None,
    target_duration: float | None = None,
    enable_emotion_control: bool | None = None,
    emotion_mode: str | None = None,
    emotion_audio: str | None = None,
    emotion_alpha: float | None = None,
    emotion_text: str | None = None,
    emotion_sliders: dict[str, float | None] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    resolved_workflow_id = _resolve_workflow_id(workflow_key, workflow_id)
    workflow_meta = _workflow_meta(api_base, api_key, resolved_workflow_id)
    node_info_list = _build_node_info_list(
        workflow_meta["prompt"],
        text=text,
        ref_audio=ref_audio,
        voice=voice,
        speed=speed,
        enable_duration_control=enable_duration_control,
        duration_mode=duration_mode,
        speed_multiplier=speed_multiplier,
        target_duration=target_duration,
        enable_emotion_control=enable_emotion_control,
        emotion_mode=emotion_mode,
        emotion_audio=emotion_audio,
        emotion_alpha=emotion_alpha,
        emotion_text=emotion_text,
        emotion_sliders=emotion_sliders,
    )
    payload = _runninghub_post(
        api_base,
        api_key,
        "/task/openapi/create",
        {
            "apiKey": api_key,
            "workflowId": resolved_workflow_id,
            **({"instanceType": instance_type.strip()} if instance_type and instance_type.strip() else {}),
            "randomSeed": True,
            "retainSeconds": 0,
            "usePersonalQueue": False,
            "nodeInfoList": node_info_list,
        },
        timeout=120,
    )
    return payload, node_info_list, resolved_workflow_id


def _query_task_status(api_base: str, api_key: str, task_id: str) -> dict[str, Any]:
    return _runninghub_post(
        api_base,
        api_key,
        "/task/openapi/status",
        {"apiKey": api_key, "taskId": task_id},
        timeout=60,
    )


def _query_task_outputs(api_base: str, api_key: str, task_id: str) -> dict[str, Any]:
    return _runninghub_post_allow_failure_detail(
        api_base,
        api_key,
        "/task/openapi/outputs",
        {"apiKey": api_key, "taskId": task_id},
        timeout=60,
    )


def _extract_remote_task_id(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        candidate = data.get("taskId") or data.get("id")
        if candidate:
            return str(candidate)
    candidate = payload.get("taskId") or payload.get("id")
    return str(candidate or "")


def _extract_status_text(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, str) and data.strip():
        return data.strip().upper()
    if isinstance(data, dict):
        candidate = data.get("taskStatus") or data.get("status")
        if candidate:
            return str(candidate).upper()
    candidate = payload.get("taskStatus") or payload.get("status")
    return str(candidate or "").upper()


def _extract_status_percent(payload: dict[str, Any]) -> int | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    for candidate in (data.get("progress"), data.get("schedule"), data.get("percent"), data.get("process")):
        if candidate is None or candidate == "":
            continue
        try:
            return max(0, min(100, int(float(candidate))))
        except Exception:
            continue
    return None


def _extract_status_message(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, str) and data.strip():
        return data.strip()
    if isinstance(data, dict):
        for candidate in (data.get("promptTips"), data.get("message"), data.get("msg")):
            if candidate:
                return str(candidate)
    for candidate in (payload.get("promptTips"), payload.get("message"), payload.get("msg")):
        if candidate:
            return str(candidate)
    return ""


def _status_to_progress(status_text: str, reported_progress: int | None) -> int:
    if reported_progress is not None:
        return reported_progress
    if status_text in {"SUCCESS", "DONE", "COMPLETED"}:
        return 95
    if status_text in {"FAILED", "ERROR", "CANCELLED", "CANCELED"}:
        return 100
    if status_text in {"PENDING", "QUEUE", "QUEUED"}:
        return 20
    if status_text in {"RUNNING", "PROCESSING"}:
        return 60
    return 45


def _normalize_outputs_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, list):
        outputs = data
    elif isinstance(data, dict) and isinstance(data.get("outputs"), list):
        outputs = data.get("outputs") or []
    else:
        outputs = []
    failed_reason = data.get("failedReason") if isinstance(data, dict) else None
    if not isinstance(failed_reason, dict):
        failed_reason = payload.get("failedReason") or {}
    return {
        "taskId": payload.get("taskId") or "",
        "status": payload.get("status") or "",
        "errorCode": payload.get("errorCode") or "",
        "errorMessage": payload.get("errorMessage") or "",
        "results": [
            {
                "url": item.get("fileUrl") or item.get("url") or "",
                "nodeId": item.get("nodeId") or "",
                "outputType": item.get("fileType") or item.get("outputType") or "",
                "text": item.get("text"),
            }
            for item in outputs
        ],
        "promptTips": payload.get("promptTips") or "",
        "failedReason": failed_reason,
        "usage": payload.get("usage") or {},
        "taskUsageList": payload.get("taskUsageList") or [],
        "raw": payload,
    }


def _task_outputs_ready(task: dict[str, Any]) -> bool:
    result = task.get("result") or {}
    outputs = result.get("outputs") or {}
    results = outputs.get("results")
    return bool(task.get("status") == "done" and isinstance(results, list) and results)


def _sync_task_with_remote(task: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    result = task.get("result") or {}
    remote_task_id = result.get("remote_task_id") or result.get("submit", {}).get("data", {}).get("taskId")
    if not remote_task_id:
        return task

    config = get_config()
    api_key = (task.get("payload") or {}).get("api_key") or config["api_key"]
    api_base = (task.get("payload") or {}).get("api_base") or config["api_base"]
    if not api_key:
        return task

    if _task_outputs_ready(task):
        return task

    status_payload = _query_task_status(api_base, api_key, remote_task_id)
    status_text = _extract_status_text(status_payload)
    progress = _status_to_progress(status_text, _extract_status_percent(status_payload))
    status_message = _extract_status_message(status_payload) or status_text or "等待 RunningHub 更新"

    workflow_meta = result.get("workflow_meta") or {}
    base_result = {
        "submit": result.get("submit") or {},
        "remote_task_id": remote_task_id,
        "last_status": status_payload,
        "workflow_meta": workflow_meta,
    }

    if status_text in {"SUCCESS", "DONE", "COMPLETED"}:
        outputs_payload = _query_task_outputs(api_base, api_key, remote_task_id)
        normalized_outputs = _normalize_outputs_payload(outputs_payload)
        existing_outputs = result.get("outputs") if isinstance(result.get("outputs"), dict) else {}
        if (
            task.get("status") == "done"
            and task.get("progress") == 100
            and existing_outputs.get("results") == normalized_outputs.get("results")
        ):
            return task
        update_task(
            task["id"],
            status="done",
            progress=100,
            message="TTS 完成",
            result_json={**base_result, "outputs": normalized_outputs},
            error=None,
        )
        return get_task(task["id"]) or task

    if status_text in {"FAILED", "ERROR", "CANCELLED", "CANCELED"}:
        outputs_payload = _query_task_outputs(api_base, api_key, remote_task_id)
        normalized_outputs = _normalize_outputs_payload(outputs_payload)
        failed_reason = _extract_failed_reason(outputs_payload)
        update_task(
            task["id"],
            status="error",
            progress=100,
            message=failed_reason or "RunningHub TTS 失败",
            result_json={**base_result, "outputs": normalized_outputs},
            error=failed_reason or _payload_message(outputs_payload) or _payload_message(status_payload) or "RunningHub 任务失败",
        )
        return get_task(task["id"]) or task

    if force or task.get("status") != "running" or task.get("message") != status_message or task.get("progress") != progress:
        update_task(
            task["id"],
            status="running",
            progress=max(40, min(95, progress)),
            message=status_message,
            result_json=base_result,
        )
    return get_task(task["id"]) or task


def _poll_runninghub_task(
    api_base: str,
    api_key: str,
    task_id: str,
    poll_interval_seconds: float,
    progress_callback,
) -> dict[str, Any]:
    deadline = time.time() + DEFAULT_STATUS_TIMEOUT_SECONDS
    while time.time() < deadline:
        status_payload = _query_task_status(api_base, api_key, task_id)
        status_text = _extract_status_text(status_payload)
        status_message = _extract_status_message(status_payload) or status_text or "等待 RunningHub 更新"
        progress = _status_to_progress(status_text, _extract_status_percent(status_payload))
        progress_callback(status_text, progress, status_message, status_payload)
        if status_text in {"SUCCESS", "DONE", "COMPLETED"}:
            return _normalize_outputs_payload(_query_task_outputs(api_base, api_key, task_id))
        if status_text in {"FAILED", "ERROR", "CANCELLED", "CANCELED"}:
            outputs_payload = _query_task_outputs(api_base, api_key, task_id)
            _raise_runninghub_error(
                outputs_payload,
                message=_extract_failed_reason(outputs_payload) or _payload_message(outputs_payload),
                default_message="RunningHub 任务执行失败",
            )
        time.sleep(poll_interval_seconds)
    raise HTTPException(status_code=504, detail={"message": "RunningHub task timed out", "task_id": task_id})


def _error_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            payload = detail.get("payload")
            payload_text = f" | payload={json.dumps(payload, ensure_ascii=False)}" if payload else ""
            return f"{detail.get('message') or 'HTTP 错误'}{payload_text}"
        return str(detail)
    return f"{type(exc).__name__}: {exc}"


def _run_tts_job(task_id: str, payload: RunningHubTtsJobPayload) -> None:
    config = get_config()
    api_key = payload.api_key or config["api_key"]
    api_base = payload.api_base or config["api_base"]
    instance_type = payload.instance_type if payload.instance_type is not None else config["instance_type"]
    poll_interval_seconds = float(config["poll_interval_seconds"])
    if not api_key:
        update_task(task_id, status="error", progress=100, message="Missing RunningHub API Key", error="Missing RunningHub API key")
        return

    try:
        update_task(task_id, status="running", progress=10, message="Preparing RunningHub TTS request")

        ref_audio = payload.ref_audio_url
        if payload.ref_audio_path:
            resolved_ref_audio_path = _normalize_ref_audio_path(payload.ref_audio_path)
            update_task(task_id, status="running", progress=18, message="Uploading speaker reference audio to RunningHub")
            ref_audio = _upload_reference_audio(api_base, api_key, Path(resolved_ref_audio_path))

        emotion_audio = payload.emotion_audio_url
        if payload.emotion_audio_path:
            resolved_emotion_audio_path = _normalize_ref_audio_path(payload.emotion_audio_path)
            update_task(task_id, status="running", progress=22, message="Uploading emotion reference audio to RunningHub")
            emotion_audio = _upload_reference_audio(api_base, api_key, Path(resolved_emotion_audio_path))

        update_task(task_id, status="running", progress=28, message="Reading RunningHub workflow metadata")
        emotion_sliders = {
            "happy": payload.happy,
            "angry": payload.angry,
            "sad": payload.sad,
            "fear": payload.fear,
            "hate": payload.hate,
            "love": payload.love,
            "surprise": payload.surprise,
            "neutral": payload.neutral,
        }
        submit, node_info_list, resolved_workflow_id = _submit_runninghub_task(
            api_base,
            api_key,
            payload.workflow_key,
            payload.workflow_id,
            instance_type,
            payload.text,
            ref_audio,
            payload.voice,
            payload.speed,
            payload.enable_duration_control,
            payload.duration_mode,
            payload.speed_multiplier,
            payload.target_duration,
            payload.enable_emotion_control,
            payload.emotion_mode,
            emotion_audio,
            payload.emotion_alpha,
            payload.emotion_text,
            emotion_sliders,
        )
        remote_task_id = _extract_remote_task_id(submit)
        base_result = {
            "submit": submit,
            "remote_task_id": remote_task_id,
            "workflow_meta": {
                "workflow_id": resolved_workflow_id,
                "workflow_key": payload.workflow_key,
                "node_info_list": node_info_list,
            },
        }
        update_task(
            task_id,
            status="running",
            progress=40,
            message="RunningHub accepted the task, polling progress",
            result_json=base_result,
            error=None,
        )

        outputs = _poll_runninghub_task(
            api_base,
            api_key,
            remote_task_id or task_id,
            poll_interval_seconds,
            progress_callback=lambda status_text, progress, message, raw: update_task(
                task_id,
                status="running",
                progress=max(40, min(95, progress)),
                message=message,
                result_json={**base_result, "last_status": raw},
                error=None,
            ),
        )
        update_task(
            task_id,
            status="done",
            progress=100,
            message="TTS completed",
            result_json={**base_result, "outputs": outputs},
            error=None,
        )
    except Exception as exc:
        update_task(task_id, status="error", progress=100, message="RunningHub TTS failed", error=_error_text(exc))


@router.get("/config")
def get_config() -> dict[str, Any]:
    env = read_env_map()
    workflow_key = env.get("RUNNINGHUB_TTS_WORKFLOW", DEFAULT_WORKFLOW_KEY)
    workflow_id = env.get("RUNNINGHUB_TTS_WORKFLOW_ID", "")
    return {
        "api_key": env.get("RUNNINGHUB_API_KEY", ""),
        "api_base": env.get("RUNNINGHUB_API_BASE", DEFAULT_API_BASE),
        "workflow_key": workflow_key,
        "workflow_id": _resolve_workflow_id(workflow_key, workflow_id),
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
        "workflow_id": config["workflow_id"],
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
            "RUNNINGHUB_TTS_WORKFLOW_ID": payload.workflow_id or "",
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


@router.post("/sync")
def sync_runninghub_tts_tasks(force: bool = False) -> dict[str, Any]:
    synced: list[dict[str, Any]] = []
    for task in list_tasks(task_type="runninghub_tts", limit=100):
        try:
            updated = _sync_task_with_remote(task, force=force)
            synced.append(
                {
                    "id": updated.get("id"),
                    "status": updated.get("status"),
                    "progress": updated.get("progress"),
                    "message": updated.get("message"),
                }
            )
        except Exception as exc:
            synced.append(
                {
                    "id": task.get("id"),
                    "status": task.get("status"),
                    "progress": task.get("progress"),
                    "message": f"同步失败：{_error_text(exc)}",
                }
            )
    return {"status": "ok", "count": len(synced), "tasks": synced}


@router.post("/sync/{task_id}")
def sync_runninghub_tts_task(task_id: str, force: bool = True) -> dict[str, Any]:
    task = get_task(task_id)
    if not task or task.get("type") != "runninghub_tts":
        raise HTTPException(status_code=404, detail={"message": "RunningHub TTS task not found"})
    updated = _sync_task_with_remote(task, force=force)
    return {"status": "ok", "task": updated}
