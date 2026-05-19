from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv:
    load_dotenv(ROOT / ".env")

from integrations.ai_video_analysis.audio_publication import AudioPublisher, configured_publisher_mode
from integrations.ai_video_analysis.doubao_asr import (
    DoubaoAsrConfig,
    DoubaoFileAsrClient,
    DoubaoFileAsrTranscriber,
    validate_doubao_asr_environment,
)
from integrations.ai_video_analysis.relay_clients import DeepSeekChatClient, GeminiGenerateContentRelayClient, OpenAICompatibleRelayClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test real AI-video external APIs without printing secrets.")
    parser.add_argument("--audio", help="Local audio file for TOS/ASR smoke. If omitted, a tiny WAV is generated for TOS only.")
    parser.add_argument("--tos", action="store_true", help="Test Volcengine TOS audio publication.")
    parser.add_argument("--asr", action="store_true", help="Test Volcengine/Doubao recording-file ASR.")
    parser.add_argument("--gemini", action="store_true", help="Test Yunwu Gemini via OpenAI-compatible chat/completions.")
    parser.add_argument("--deepseek", action="store_true", help="Test official DeepSeek chat/completions.")
    parser.add_argument("--all", action="store_true", help="Run all checks.")
    parser.add_argument("--run", action="store_true", help="Actually call/upload to remote APIs. Without this, only config is checked.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    selected = selected_checks(args)
    result: dict[str, Any] = {
        "mode": "run" if args.run else "dry_run",
        "run_required_for_side_effects": True,
        "selected": selected,
        "config": config_report(),
        "checks": {},
        "errors": [],
    }

    if not args.run:
        result["blocked"] = True
        result["message"] = "Pass --run to upload/call real external APIs. No network side effects were performed."
        return finish(result, as_json=args.json, exit_code=2 if selected else 0)

    audio_path: Path | None = None
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        if "tos" in selected or "asr" in selected:
            try:
                audio_path, temp_dir = resolve_audio_path(args.audio, allow_generated="asr" not in selected)
            except Exception as exc:
                result["errors"].append(f"audio: {type(exc).__name__}: {exc}")
        checks = {
            "tos": lambda: run_tos_smoke(audio_path),
            "asr": lambda: run_asr_smoke(audio_path),
            "gemini": run_gemini_smoke,
            "deepseek": run_deepseek_smoke,
        }
        for name in selected:
            if name in {"tos", "asr"} and audio_path is None:
                continue
            try:
                result["checks"][name] = checks[name]()
            except Exception as exc:
                result["checks"][name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                result["errors"].append(f"{name}: {type(exc).__name__}: {exc}")
    finally:
        if temp_dir:
            temp_dir.cleanup()

    return finish(result, as_json=args.json, exit_code=0 if not result["errors"] else 1)


def selected_checks(args: argparse.Namespace) -> list[str]:
    if args.all:
        return ["tos", "asr", "gemini", "deepseek"]
    selected = []
    if args.tos:
        selected.append("tos")
    if args.asr:
        selected.append("asr")
    if args.gemini:
        selected.append("gemini")
    if args.deepseek:
        selected.append("deepseek")
    return selected or ["tos", "asr", "gemini", "deepseek"]


def config_report() -> dict[str, Any]:
    asr_config = DoubaoAsrConfig.from_env()
    publisher = configured_publisher_mode()
    return {
        "tos": {
            "publisher": publisher,
            "access_key_configured": configured("VOLCENGINE_TOS_ACCESS_KEY", "TOS_ACCESS_KEY", "TOS_AK"),
            "secret_key_configured": configured("VOLCENGINE_TOS_SECRET_KEY", "TOS_SECRET_KEY", "TOS_SK"),
            "endpoint_configured": configured("VOLCENGINE_TOS_ENDPOINT", "TOS_ENDPOINT"),
            "region_configured": configured("VOLCENGINE_TOS_REGION", "TOS_REGION"),
            "bucket_configured": configured("VOLCENGINE_TOS_BUCKET", "TOS_BUCKET"),
            "use_presigned_url": os.getenv("VOLCENGINE_TOS_USE_PRESIGNED_URL", "true").lower() not in {"0", "false", "no"},
        },
        "asr": {
            "app_id_configured": bool(asr_config.app_id),
            "access_token_configured": bool(asr_config.access_token),
            "secret_key_configured": bool(asr_config.secret_key),
            "resource_id": asr_config.resource_id,
            "upload_mode": asr_config.upload_mode,
            "submit_url": asr_config.submit_url,
            "query_url": asr_config.query_url,
            "errors": validate_doubao_asr_environment(config=asr_config, publisher=publisher),
        },
        "gemini": {
            "provider": "yunwu",
            "base_url": os.getenv("AI_VIDEO_RELAY_BASE_URL") or os.getenv("YUNWU_BASE_URL") or "https://yunwu.ai/v1",
            "api_key_configured": configured("AI_VIDEO_RELAY_API_KEY", "YUNWU_API_KEY", "AI_RELAY_API_KEY"),
            "model": os.getenv("AI_VIDEO_VISION_MODEL") or os.getenv("GEMINI_MODEL") or os.getenv("YUNWU_MODEL") or "gemini-2.5-flash",
            "api_format": os.getenv("AI_VIDEO_RELAY_API_FORMAT") or os.getenv("YUNWU_API_FORMAT") or "openai_chat_completions",
        },
        "deepseek": {
            "provider": "official",
            "base_url": os.getenv("AI_VIDEO_SUMMARY_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
            "api_key_configured": configured("AI_VIDEO_SUMMARY_API_KEY", "DEEPSEEK_API_KEY"),
            "model": os.getenv("AI_VIDEO_SUMMARY_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat",
        },
    }


def configured(*names: str) -> bool:
    return any(bool(os.getenv(name)) for name in names)


def resolve_audio_path(audio: str | None, *, allow_generated: bool) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if audio:
        path = Path(audio).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"Audio file not found: {path}")
        return path, None
    if not allow_generated:
        raise RuntimeError("Missing --audio. ASR smoke needs real speech audio for a meaningful recognition request.")
    temp_dir = tempfile.TemporaryDirectory()
    audio_path = Path(temp_dir.name) / "tos-smoke.wav"
    write_tiny_wav(audio_path)
    return audio_path, temp_dir


def write_tiny_wav(path: Path) -> None:
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 16000
    duration_seconds = 1
    silence = b"\x00\x00" * sample_rate * duration_seconds
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(sample_rate)
        file.writeframes(silence)


def run_tos_smoke(audio_path: Path | None) -> dict[str, Any]:
    if audio_path is None:
        raise RuntimeError("TOS smoke requires an audio path.")
    published = AudioPublisher().resolve_or_publish(audio_path)
    if not published:
        raise RuntimeError("Audio publication did not produce a URL. Set AI_VIDEO_ASR_PUBLISHER=tos and TOS env.")
    return {
        "ok": True,
        "mode": published.mode,
        "url": redact_url(published.url),
        "path": published.path,
        "relative_path": published.relative_path,
        "storage_key": published.storage_key,
        "expires_in_seconds": published.expires_in_seconds,
        "source_audio": str(audio_path),
    }


def run_asr_smoke(audio_path: Path | None) -> dict[str, Any]:
    if audio_path is None:
        raise RuntimeError("ASR smoke requires --audio.")
    started = time.perf_counter()
    transcript = DoubaoFileAsrTranscriber(DoubaoFileAsrClient()).transcribe(
        audio_path,
        model=os.getenv("AI_VIDEO_TRANSCRIBE_MODEL", "volc.seedasr.auc"),
        language=os.getenv("AI_VIDEO_TRANSCRIBE_LANGUAGE", "zh") or None,
    )
    return {
        "ok": True,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "provider": transcript.get("provider") or "",
        "model": transcript.get("model") or "",
        "language": transcript.get("language") or "",
        "upload_mode": transcript.get("upload_mode") or "",
        "audio_url": redact_url(str(transcript.get("audio_url") or "")),
        "segment_count": len(transcript.get("segments") or []),
        "word_count": len(transcript.get("words") or []),
        "pause_count": len(transcript.get("pause_points") or []),
        "text_preview": str(transcript.get("full_text") or "")[:200],
    }


def run_gemini_smoke() -> dict[str, Any]:
    model = os.getenv("AI_VIDEO_VISION_MODEL") or os.getenv("GEMINI_MODEL") or os.getenv("YUNWU_MODEL") or "gemini-2.5-flash"
    api_format = (os.getenv("AI_VIDEO_RELAY_API_FORMAT") or os.getenv("YUNWU_API_FORMAT") or "openai_chat_completions").lower()
    if api_format in {"gemini_generate_content", "generate_content"}:
        return run_gemini_generate_content_smoke(model)

    client = OpenAICompatibleRelayClient(
        base_url=os.getenv("AI_VIDEO_RELAY_BASE_URL") or os.getenv("YUNWU_BASE_URL") or "https://yunwu.ai/v1",
        api_key=os.getenv("AI_VIDEO_RELAY_API_KEY") or os.getenv("YUNWU_API_KEY") or os.getenv("AI_RELAY_API_KEY") or "",
        model=model,
    )
    started = time.perf_counter()
    response = client.generate_text(
        prompt='Return JSON only: {"ok": true, "provider": "gemini"}.',
        image_paths=[],
        model=model,
        system_prompt="Return valid JSON only.",
        temperature=0,
    )
    return {
        "ok": True,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "base_url": client.base_url,
        "api_format": "openai_chat_completions",
        "model": model,
        "text_preview": response.text[:300],
        "usage": compact_usage(response.usage),
    }


def run_gemini_generate_content_smoke(model: str) -> dict[str, Any]:
    client = GeminiGenerateContentRelayClient(
        base_url=os.getenv("AI_VIDEO_RELAY_BASE_URL") or os.getenv("YUNWU_BASE_URL") or os.getenv("GEMINI_RELAY_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://yunwu.ai",
        api_key=os.getenv("AI_VIDEO_RELAY_API_KEY") or os.getenv("YUNWU_API_KEY") or os.getenv("GEMINI_RELAY_API_KEY") or os.getenv("AI_RELAY_API_KEY") or "",
        model=model,
    )
    started = time.perf_counter()
    response = client.generate_text(
        prompt='Return JSON only: {"ok": true, "provider": "gemini"}.',
        model=model,
        system_instruction="Return valid JSON only.",
        temperature=0,
    )
    return {
        "ok": True,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "base_url": client.base_url,
        "api_format": "gemini_generate_content",
        "model": model,
        "text_preview": response.text[:300],
        "usage": compact_usage(response.usage),
    }


def run_deepseek_smoke() -> dict[str, Any]:
    model = os.getenv("AI_VIDEO_SUMMARY_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
    client = DeepSeekChatClient(model=model)
    started = time.perf_counter()
    response = client.generate_summary(
        prompt='Return JSON only: {"ok": true, "provider": "deepseek"}.',
        model=model,
        system_prompt="Return valid JSON only.",
    )
    return {
        "ok": True,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "base_url": client.base_url,
        "model": model,
        "text_preview": response.text[:300],
        "usage": compact_usage(response.usage),
    }


def compact_usage(usage: dict[str, Any]) -> dict[str, Any]:
    return {
        key: usage.get(key)
        for key in [
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "input_tokens",
            "output_tokens",
            "promptTokenCount",
            "candidatesTokenCount",
            "totalTokenCount",
        ]
        if usage.get(key) is not None
    }


def extract_generate_content_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if candidates:
        parts = ((candidates[0].get("content") or {}).get("parts")) or []
        text = "\n".join(str(part.get("text") or "") for part in parts if isinstance(part, dict) and part.get("text"))
        if text:
            return text
    if isinstance(data.get("text"), str):
        return str(data["text"])
    return json.dumps(data, ensure_ascii=False)[:300]


def redact_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value)
    if not parsed.query:
        return value
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "[redacted-query]", parsed.fragment))


def finish(result: dict[str, Any], *, as_json: bool, exit_code: int) -> int:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result)
    return exit_code


def print_human(result: dict[str, Any]) -> None:
    print("AI video external API smoke")
    print(f"- mode: {result['mode']}")
    print(f"- selected: {', '.join(result['selected'])}")
    for name, check in result.get("checks", {}).items():
        print(f"- {name}: ok")
        if check.get("latency_ms") is not None:
            print(f"  latency_ms: {check['latency_ms']}")
        if check.get("model"):
            print(f"  model: {check['model']}")
        if check.get("url"):
            print(f"  url: {check['url']}")
        if check.get("text_preview"):
            print(f"  text_preview: {check['text_preview']}")
    if result.get("blocked"):
        print(f"- blocked: {result['message']}")
    if result["errors"]:
        print("- errors:")
        for error in result["errors"]:
            print(f"  - {error}")


if __name__ == "__main__":
    raise SystemExit(main())
