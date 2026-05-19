from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is a project dependency, but keep the smoke script portable.
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe smoke test helper for AI video Doubao ASR publication.")
    parser.add_argument("--audio", help="Local audio file path, usually audio.wav extracted by ffmpeg.")
    parser.add_argument("--publish-only", action="store_true", help="Publish audio and print a redacted URL summary.")
    parser.add_argument("--transcribe", action="store_true", help="Run Doubao ASR and print a transcript summary.")
    parser.add_argument("--run", action="store_true", help="Actually publish/upload/call remote APIs. Without this, only config is checked.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    result = build_config_report()
    wants_effect = args.publish_only or args.transcribe
    if wants_effect and not args.run:
        result["blocked"] = True
        result["message"] = "Pass --run to publish audio or call Doubao ASR. No network or upload action was performed."
        return finish(result, as_json=args.json, exit_code=2)

    if wants_effect:
        if not args.audio:
            result["errors"].append("Missing --audio for publish/transcribe smoke test.")
            return finish(result, as_json=args.json, exit_code=2)
        audio_path = Path(args.audio).expanduser().resolve()
        if not audio_path.exists() or not audio_path.is_file():
            result["errors"].append(f"Audio file not found: {audio_path}")
            return finish(result, as_json=args.json, exit_code=2)
        if args.publish_only:
            result["publication"] = publish_audio(audio_path)
        if args.transcribe:
            result["transcription"] = transcribe_audio(audio_path)

    return finish(result, as_json=args.json, exit_code=0 if not result["errors"] else 1)


def build_config_report() -> dict[str, Any]:
    config = DoubaoAsrConfig.from_env()
    publisher = configured_publisher_mode()
    errors = validate_doubao_asr_environment(config=config, publisher=publisher)
    return {
        "mode": "dry_run",
        "run_required_for_side_effects": True,
        "asr": {
            "app_id_configured": bool(config.app_id),
            "access_token_configured": bool(config.access_token),
            "secret_key_configured": bool(config.secret_key),
            "resource_id": config.resource_id,
            "submit_url": config.submit_url,
            "query_url": config.query_url,
            "upload_mode": config.upload_mode,
            "direct_url_configured": bool(config.direct_url),
        },
        "publisher": {
            "mode": publisher,
            "public_base_url_configured": bool(os.getenv("AI_VIDEO_ASR_PUBLIC_BASE_URL") or os.getenv("AI_VIDEO_PUBLIC_BASE_URL")),
            "public_dir": os.getenv("AI_VIDEO_ASR_PUBLIC_DIR") or "",
            "tos_bucket_configured": bool(os.getenv("VOLCENGINE_TOS_BUCKET") or os.getenv("TOS_BUCKET")),
            "tos_endpoint_configured": bool(os.getenv("VOLCENGINE_TOS_ENDPOINT") or os.getenv("TOS_ENDPOINT")),
            "tos_region_configured": bool(os.getenv("VOLCENGINE_TOS_REGION") or os.getenv("TOS_REGION")),
            "tos_access_key_configured": bool(os.getenv("VOLCENGINE_TOS_ACCESS_KEY") or os.getenv("TOS_ACCESS_KEY") or os.getenv("TOS_AK")),
            "tos_secret_key_configured": bool(os.getenv("VOLCENGINE_TOS_SECRET_KEY") or os.getenv("TOS_SECRET_KEY") or os.getenv("TOS_SK")),
        },
        "errors": errors,
    }
def publish_audio(audio_path: Path) -> dict[str, Any]:
    published = AudioPublisher().resolve_or_publish(audio_path)
    if not published:
        raise RuntimeError("Audio publication did not produce a URL. Check AI_VIDEO_ASR_PUBLIC_BASE_URL or TOS env.")
    return {
        "mode": published.mode,
        "url": redact_url(published.url),
        "path": published.path,
        "relative_path": published.relative_path,
        "storage_key": published.storage_key,
        "expires_in_seconds": published.expires_in_seconds,
    }


def transcribe_audio(audio_path: Path) -> dict[str, Any]:
    transcript = DoubaoFileAsrTranscriber(DoubaoFileAsrClient()).transcribe(
        audio_path,
        model=os.getenv("AI_VIDEO_TRANSCRIBE_MODEL", "volc.seedasr.auc"),
        language=os.getenv("AI_VIDEO_TRANSCRIBE_LANGUAGE", "zh") or None,
    )
    return {
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
    print("AI video ASR smoke check")
    print(f"- upload_mode: {result['asr']['upload_mode']}")
    print(f"- publisher: {result['publisher']['mode']}")
    print(f"- asr app id configured: {result['asr']['app_id_configured']}")
    print(f"- asr token configured: {result['asr']['access_token_configured']}")
    print(f"- tos bucket configured: {result['publisher']['tos_bucket_configured']}")
    if result.get("publication"):
        print(f"- published URL: {result['publication']['url']}")
        print(f"- publication mode: {result['publication']['mode']}")
    if result.get("transcription"):
        print(f"- transcript segments: {result['transcription']['segment_count']}")
        print(f"- transcript preview: {result['transcription']['text_preview']}")
    if result.get("blocked"):
        print(f"- blocked: {result['message']}")
    if result["errors"]:
        print("- errors:")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("- config check: ok")


if __name__ == "__main__":
    raise SystemExit(main())
