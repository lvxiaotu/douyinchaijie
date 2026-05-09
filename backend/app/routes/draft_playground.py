from __future__ import annotations

import json
import os
import re
from typing import Any

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.ai_provider_state import active_ai_provider, active_api_format, active_model, openai_compatible_credentials

router = APIRouter(prefix="/api/tools/draft-playground", tags=["draft-playground"])


class RandomDraftJsonRequest(BaseModel):
    theme: str = Field(default="随机短视频剧情")
    aspect_ratio: str = Field(default="9:16")
    scene_count: int = Field(default=5, ge=1, le=12)
    provider: str | None = Field(default=None)


@router.post("/random-json")
def random_json(payload: RandomDraftJsonRequest) -> dict[str, Any]:
    try:
        provider = payload.provider or active_ai_provider("mock")
        if provider == "mock":
            return {"provider": provider, "draft_json": _mock_draft_json(payload)}
        prompt = _random_draft_prompt(payload)
        raw_text = _call_model(provider, prompt)
        return {"provider": provider, "draft_json": _parse_json(raw_text), "raw_model_text": raw_text}
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error_type": type(exc).__name__, "message": str(exc)}) from exc


def _random_draft_prompt(payload: RandomDraftJsonRequest) -> str:
    return "\n\n".join(
        [
            "You generate valid JSON only.",
            "Create a reasonable Jianying draft payload for pyJianYingDraft.",
            'Schema: {"name":"","aspect_ratio":"9:16","default_media_duration_seconds":3,"media":[],"audio":[],"texts":[{"text":"","track":"text","start_seconds":0,"duration_seconds":3,"style":{"size":8,"bold":true,"color":[1,1,1],"alpha":1,"align":1,"auto_wrapping":true,"max_line_width":0.82},"background":{"color":"#000000","alpha":0.45,"round_radius":0.08,"height":0.14,"width":0.14}}]}',
            "Requirements:",
            f"- theme: {payload.theme}",
            f"- aspect_ratio: {payload.aspect_ratio}",
            f"- scene_count: {payload.scene_count}",
            "- media/audio paths must be empty arrays for now or omitted if unavailable.",
            "- texts should form a coherent short-video draft timeline.",
            "- Use cumulative start_seconds and reasonable duration_seconds.",
        ]
    )


def _mock_draft_json(payload: RandomDraftJsonRequest) -> dict[str, Any]:
    texts = []
    for index in range(payload.scene_count):
        texts.append(
            {
                "text": f"第{index + 1}幕：围绕“{payload.theme}”展开一个有钩子的短视频片段。",
                "track": "text",
                "start_seconds": index * 3,
                "duration_seconds": 3,
                "style": {
                    "size": 8,
                    "bold": True,
                    "color": [1, 1, 1],
                    "alpha": 1,
                    "align": 1,
                    "auto_wrapping": True,
                    "max_line_width": 0.82,
                },
                "background": {
                    "color": "#000000",
                    "alpha": 0.45,
                    "round_radius": 0.08,
                    "height": 0.14,
                    "width": 0.14,
                },
            }
        )
    return {
        "name": _safe_name(payload.theme),
        "aspect_ratio": payload.aspect_ratio,
        "default_media_duration_seconds": 3,
        "media": [],
        "audio": [],
        "texts": texts,
    }


def _safe_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_")
    return safe or "jianying_draft"


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if match:
        cleaned = match.group(0)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("AI response is not a JSON object.")
    return data


def _call_model(provider: str, prompt: str) -> str:
    if provider == "gemini":
        return _call_gemini(prompt)
    return _call_openai_compatible(provider, prompt)


def _call_gemini(prompt: str) -> str:
    access_mode = os.getenv("GEMINI_ACCESS_MODE") or os.getenv("AI_ACCESS_MODE") or "official"
    model = os.getenv("GEMINI_MODEL") or active_model("gemini-2.5-flash")
    if access_mode == "relay":
        api_key = os.getenv("GEMINI_RELAY_API_KEY") or os.getenv("AI_RELAY_API_KEY") or ""
        base_url = (os.getenv("GEMINI_RELAY_BASE_URL") or os.getenv("AI_RELAY_BASE_URL") or "https://jeniya.top").rstrip("/")
        if not api_key:
            raise RuntimeError("Missing GEMINI_RELAY_API_KEY")
        response = requests.post(
            f"{base_url}/v1beta/models/{model}:generateContent?key=",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}},
            timeout=120,
        )
        if not response.ok:
            raise RuntimeError(f"Gemini relay HTTP {response.status_code}: {response.text[:500]}")
        data = response.json()
        parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
        return "\n".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("AI_NATIVE_API_KEY") or ""
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY")
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    return (response.text or "").strip()


def _call_openai_compatible(provider: str, prompt: str) -> str:
    creds = openai_compatible_credentials(provider)
    api_key = creds.get("api_key") or ""
    base_url = (creds.get("base_url") or "").rstrip("/")
    model = active_model(os.getenv("OPENAI_MODEL") or "gpt-4.1-mini")
    api_format = active_api_format("chat_completions")
    if not api_key or not base_url:
        raise RuntimeError(f"Missing API config for provider: {provider}")
    if api_format == "responses":
        response = requests.post(
            f"{base_url}/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": prompt},
            timeout=120,
        )
        if not response.ok:
            raise RuntimeError(f"Responses HTTP {response.status_code}: {response.text[:500]}")
        data = response.json()
        return data.get("output_text") or ""

    response = requests.post(
        f"{base_url}/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.9,
        },
        timeout=120,
    )
    if not response.ok:
        raise RuntimeError(f"Chat completions HTTP {response.status_code}: {response.text[:500]}")
    data = response.json()
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
