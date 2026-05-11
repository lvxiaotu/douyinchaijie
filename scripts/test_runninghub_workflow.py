from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.routes.runninghub_tts import (
    _extract_failed_reason,
    _extract_remote_task_id,
    _extract_status_message,
    _extract_status_percent,
    _extract_status_text,
    _normalize_outputs_payload,
    _runninghub_post,
    _submit_runninghub_task,
    _upload_reference_audio,
    _workflow_meta,
    get_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test a RunningHub TTS workflow from the local project environment.")
    parser.add_argument("--workflow-id", required=True, help="RunningHub workflow ID")
    parser.add_argument("--workflow-url", default="", help="Optional RunningHub workflow URL")
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--ref-audio", default="", help="Reference audio path; defaults to first audio file in data/runtime/runninghub_tts")
    parser.add_argument("--instance-type", default="", help="RunningHub instance type, such as plus")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--timeout-seconds", type=float, default=180.0, help="Max polling time in seconds")
    parser.add_argument("--output", default="", help="Optional output JSON path")
    return parser.parse_args()


def resolve_ref_audio(raw_path: str) -> Path:
    if raw_path:
        path = Path(raw_path)
        if path.exists():
            return path
        raise FileNotFoundError(f"Reference audio not found: {raw_path}")
    runtime_dir = Path(__file__).resolve().parents[1] / "data" / "runtime" / "runninghub_tts"
    for item in runtime_dir.iterdir():
        if item.suffix.lower() in {".m4a", ".mp3", ".wav", ".ogg"}:
            return item
    raise FileNotFoundError(f"No reference audio found in {runtime_dir}")


def _linked_input(prompt: dict[str, object], node_id: str, field_name: str) -> list[object] | None:
    node = prompt.get(str(node_id))
    if not isinstance(node, dict):
        return None
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return None
    value = inputs.get(field_name)
    return value if isinstance(value, list) and value else None


def _target_advanced_node(prompt: dict[str, object]) -> str | None:
    candidates = [
        str(node_id)
        for node_id, node in prompt.items()
        if isinstance(node, dict) and node.get("class_type") == "IndexTTS2_Advanced"
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: int(item) if item.isdigit() else item)[-1]


def _resolve_text_override(prompt: dict[str, object], node_id: str, text: str) -> list[dict[str, object]]:
    link = _linked_input(prompt, node_id, "text")
    visited: set[str] = set()
    while isinstance(link, list) and link:
        upstream_id = str(link[0])
        if upstream_id in visited:
            break
        visited.add(upstream_id)
        upstream_node = prompt.get(upstream_id)
        if not isinstance(upstream_node, dict):
            break
        upstream_inputs = upstream_node.get("inputs")
        if not isinstance(upstream_inputs, dict):
            break
        if upstream_node.get("class_type") == "CR Prompt Text" and "prompt" in upstream_inputs:
            return [{"nodeId": upstream_id, "fieldName": "prompt", "fieldValue": text}]
        if "text" in upstream_inputs and not isinstance(upstream_inputs.get("text"), list):
            return [{"nodeId": upstream_id, "fieldName": "text", "fieldValue": text}]
        if "prompt" in upstream_inputs and not isinstance(upstream_inputs.get("prompt"), list):
            return [{"nodeId": upstream_id, "fieldName": "prompt", "fieldValue": text}]
        if isinstance(upstream_inputs.get("text"), list):
            link = upstream_inputs["text"]
            continue
        if isinstance(upstream_inputs.get("prompt"), list):
            link = upstream_inputs["prompt"]
            continue
        break
    node = prompt.get(node_id)
    if isinstance(node, dict):
        inputs = node.get("inputs")
        if isinstance(inputs, dict) and "text" in inputs and not isinstance(inputs.get("text"), list):
            return [{"nodeId": node_id, "fieldName": "text", "fieldValue": text}]
    return []


def _resolve_bool_override(prompt: dict[str, object], node_id: str, field_name: str, value: bool) -> list[dict[str, object]]:
    link = _linked_input(prompt, node_id, field_name)
    if isinstance(link, list) and link:
        upstream_id = str(link[0])
        upstream_node = prompt.get(upstream_id)
        if isinstance(upstream_node, dict):
            upstream_inputs = upstream_node.get("inputs")
            if isinstance(upstream_inputs, dict) and "value" in upstream_inputs:
                return [{"nodeId": upstream_id, "fieldName": "value", "fieldValue": value}]
    return [{"nodeId": node_id, "fieldName": field_name, "fieldValue": value}]


def _resolve_audio_overrides(prompt: dict[str, object], node_id: str, uploaded_ref: str) -> list[dict[str, object]]:
    link = _linked_input(prompt, node_id, "speaker_audio")
    visited: set[str] = set()
    overrides: list[dict[str, object]] = []
    while isinstance(link, list) and link:
        upstream_id = str(link[0])
        if upstream_id in visited:
            break
        visited.add(upstream_id)
        upstream_node = prompt.get(upstream_id)
        if not isinstance(upstream_node, dict):
            break
        upstream_inputs = upstream_node.get("inputs")
        if not isinstance(upstream_inputs, dict):
            break
        class_type = str(upstream_node.get("class_type") or "")
        if class_type == "LoadAudio" and "audio" in upstream_inputs:
            overrides.append({"nodeId": upstream_id, "fieldName": "audio", "fieldValue": uploaded_ref})
            return overrides
        if class_type == "Switch any [Crystools]":
            overrides.append({"nodeId": upstream_id, "fieldName": "boolean", "fieldValue": True})
            next_link = upstream_inputs.get("on_true")
            link = next_link if isinstance(next_link, list) else None
            continue
        next_link = upstream_inputs.get("audio")
        if isinstance(next_link, list):
            link = next_link
            continue
        if "audio" in upstream_inputs:
            overrides.append({"nodeId": upstream_id, "fieldName": "audio", "fieldValue": uploaded_ref})
            return overrides
        break
    return overrides


def _dedupe_node_info_list(items: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: dict[tuple[str, str], dict[str, object]] = {}
    for item in items:
        key = (str(item["nodeId"]), str(item["fieldName"]))
        deduped[key] = item
    return list(deduped.values())


def _submit_linked_advanced_workflow(
    *,
    api_base: str,
    api_key: str,
    workflow_id: str,
    instance_type: str | None,
    prompt: dict[str, object],
    text: str,
    uploaded_ref: str,
) -> tuple[dict[str, object], list[dict[str, object]], str]:
    advanced_node_id = _target_advanced_node(prompt)
    if not advanced_node_id:
        raise RuntimeError("No IndexTTS2_Advanced node found for linked workflow fallback")

    node_info_list: list[dict[str, object]] = []
    node_info_list.extend(_resolve_text_override(prompt, advanced_node_id, text))
    node_info_list.extend(_resolve_audio_overrides(prompt, advanced_node_id, uploaded_ref))
    node_info_list.extend(_resolve_bool_override(prompt, advanced_node_id, "enable_duration_control", False))
    node_info_list.extend(_resolve_bool_override(prompt, advanced_node_id, "enable_emotion_control", False))
    node_info_list.extend(
        [
            {"nodeId": advanced_node_id, "fieldName": "duration_mode", "fieldValue": "speed_control"},
            {"nodeId": advanced_node_id, "fieldName": "speed_multiplier", "fieldValue": 1},
            {"nodeId": advanced_node_id, "fieldName": "target_duration", "fieldValue": 0},
            {"nodeId": advanced_node_id, "fieldName": "emotion_mode", "fieldValue": "audio_prompt"},
            {"nodeId": advanced_node_id, "fieldName": "emotion_alpha", "fieldValue": 1},
            {"nodeId": advanced_node_id, "fieldName": "happy", "fieldValue": 0},
            {"nodeId": advanced_node_id, "fieldName": "angry", "fieldValue": 0},
            {"nodeId": advanced_node_id, "fieldName": "sad", "fieldValue": 0},
            {"nodeId": advanced_node_id, "fieldName": "fear", "fieldValue": 0},
            {"nodeId": advanced_node_id, "fieldName": "hate", "fieldValue": 0},
            {"nodeId": advanced_node_id, "fieldName": "low", "fieldValue": 0},
            {"nodeId": advanced_node_id, "fieldName": "surprise", "fieldValue": 0},
            {"nodeId": advanced_node_id, "fieldName": "neutral", "fieldValue": 1},
        ]
    )
    node_info_list = _dedupe_node_info_list(node_info_list)

    payload = _runninghub_post(
        api_base,
        api_key,
        "/task/openapi/create",
        {
            "apiKey": api_key,
            "workflowId": workflow_id,
            **({"instanceType": instance_type.strip()} if instance_type and instance_type.strip() else {}),
            "randomSeed": True,
            "retainSeconds": 0,
            "usePersonalQueue": False,
            "nodeInfoList": node_info_list,
        },
        timeout=120,
    )
    return payload, node_info_list, workflow_id


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    config = get_config()
    api_base = config["api_base"]
    api_key = config["api_key"]
    workflow_input = args.workflow_url or args.workflow_id

    result: dict[str, object] = {
        "workflow_id": args.workflow_id,
        "workflow_input": workflow_input,
        "instance_type": args.instance_type,
        "text": args.text,
    }

    try:
        meta = _workflow_meta(api_base, api_key, args.workflow_id)
        prompt = meta["prompt"]
        result["workflow_summary"] = [
            {
                "node_id": str(node_id),
                "class_type": node.get("class_type"),
                "title": ((node.get("_meta") or {}).get("title")) or node.get("class_type") or str(node_id),
                "fields": list((node.get("inputs") or {}).keys()) if isinstance(node.get("inputs"), dict) else [],
            }
            for node_id, node in sorted(prompt.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else str(item[0]))
            if isinstance(node, dict)
        ]
    except Exception as exc:
        result["workflow_meta_error"] = str(exc)
        output_path = Path(args.output) if args.output else None
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        if output_path:
            output_path.write_text(payload, encoding="utf-8")
            print(output_path)
        else:
            print(payload)
        return 1

    ref_audio = resolve_ref_audio(args.ref_audio)
    uploaded_ref = _upload_reference_audio(api_base, api_key, ref_audio)
    result["ref_audio"] = str(ref_audio)
    result["uploaded_ref"] = uploaded_ref

    advanced_node_present = any(
        isinstance(node, dict) and node.get("class_type") == "IndexTTS2_Advanced" for node in prompt.values()
    )
    linked_prompt_text = any(
        isinstance(node, dict)
        and node.get("class_type") == "IndexTTS2_Advanced"
        and isinstance((node.get("inputs") or {}).get("text"), list)
        for node in prompt.values()
    )

    if advanced_node_present and linked_prompt_text:
        result["submission_mode"] = "linked_advanced_fallback"
        submit, node_info_list, resolved_workflow_id = _submit_linked_advanced_workflow(
            api_base=api_base,
            api_key=api_key,
            workflow_id=args.workflow_id,
            instance_type=args.instance_type or None,
            prompt=prompt,
            text=args.text,
            uploaded_ref=uploaded_ref,
        )
    else:
        result["submission_mode"] = "default_tts_submit"
        submit, node_info_list, resolved_workflow_id = _submit_runninghub_task(
            api_base=api_base,
            api_key=api_key,
            workflow_key=workflow_input,
            workflow_id=args.workflow_id,
            instance_type=args.instance_type or None,
            text=args.text,
            ref_audio=uploaded_ref,
            voice=None,
            speed=None,
            enable_duration_control=False,
            duration_mode="speed_control",
            speed_multiplier=1,
            target_duration=0,
            enable_emotion_control=False,
            emotion_mode="audio_prompt",
            emotion_audio=None,
            emotion_alpha=1,
            emotion_text="",
            emotion_sliders={
                "happy": 0,
                "angry": 0,
                "sad": 0,
                "fear": 0,
                "hate": 0,
                "love": 0,
                "surprise": 0,
                "neutral": 1,
            },
        )
    remote_task_id = _extract_remote_task_id(submit)
    result["resolved_workflow_id"] = resolved_workflow_id
    result["remote_task_id"] = remote_task_id
    result["submit"] = submit
    result["node_info_list"] = node_info_list

    deadline = time.time() + args.timeout_seconds
    while time.time() < deadline:
        from backend.app.routes.runninghub_tts import _query_task_outputs, _query_task_status

        status_payload = _query_task_status(api_base, api_key, remote_task_id)
        status_text = _extract_status_text(status_payload)
        result["last_status"] = {
            "status_text": status_text,
            "status_message": _extract_status_message(status_payload),
            "status_percent": _extract_status_percent(status_payload),
            "payload": status_payload,
        }
        if status_text in {"SUCCESS", "DONE", "COMPLETED", "FAILED", "ERROR", "CANCELLED", "CANCELED"}:
            outputs_payload = _query_task_outputs(api_base, api_key, remote_task_id)
            result["outputs_payload"] = outputs_payload
            result["failed_reason"] = _extract_failed_reason(outputs_payload)
            result["normalized_outputs"] = _normalize_outputs_payload(outputs_payload)
            break
        time.sleep(args.poll_seconds)

    output_path = Path(args.output) if args.output else None
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if output_path:
        output_path.write_text(payload, encoding="utf-8")
        print(output_path)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
