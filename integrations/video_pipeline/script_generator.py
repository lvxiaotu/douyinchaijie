from __future__ import annotations

import json
import os
import shutil
import re
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import requests
from dotenv import load_dotenv

from backend.app.ai_provider_state import active_ai_provider, active_api_format, active_model, openai_compatible_credentials
from backend.app.task_store import save_jianying_draft
from integrations.jianying_editor_skill.script_input_parser import (
    JIANYING_SCRIPT_CONTRACT,
    JianyingScriptInputParser,
)
from integrations.jianying_editor_skill.sdk_script_generator import JianyingEditorSdkScriptGenerator
from integrations.video_pipeline.script_schema import (
    BibleGenerateRequest,
    BlueprintGenerateRequest,
    ConceptBible,
    NaturalLanguageScriptRequest,
    ScriptExpandRequest,
    ScriptGenerateRequest,
    VideoScene,
    VideoScript,
    VideoScriptConfig,
)


ROOT = Path(__file__).resolve().parents[2]
PROJECTS_DIR = ROOT / "data" / "runtime" / "video_pipeline" / "projects"

CREATIVE_PRESETS = {
    "default": {
        "label": "通用短剧模板",
        "genre": "短剧 / 情绪反转",
        "style": "节奏清晰、冲突明确、适合短视频",
        "audience": "短视频泛内容用户",
        "tone": "有悬念、有转折",
        "structure": "开场钩子 -> 冲突升级 -> 反转证明 -> 收束行动",
        "cta": "引导关注或收藏",
    },
    "mysticism_lead": {
        "label": "玄学引流模板",
        "genre": "玄学 / 情绪疗愈 / 引流短剧",
        "style": "神秘、治愈、带命运感和反转感",
        "audience": "关注星座、运势、情绪疗愈和自我成长的用户",
        "tone": "温柔、有悬念、笃定",
        "structure": "命运钩子 -> 情绪共鸣 -> 暗示转机 -> 收藏/评论引导",
        "cta": "引导收藏、评论关键词或私信",
    },
    "ancient爽文": {
        "label": "古风爽文漫剧",
        "genre": "古风 / 穿越 / 爽文漫剧",
        "style": "热血、盛唐史诗感、强反击爽点",
        "audience": "喜欢穿越、逆袭、古风爽文的用户",
        "tone": "压迫感强、反击干脆、情绪燃",
        "structure": "现代困境 -> 穿越死局 -> 当众反击 -> 权威震动 -> 山河展开",
        "cta": "引导追更下一集",
    },
    "ai_pet": {
        "label": "AI 小动物剧情",
        "genre": "AI 小动物 / 治愈短剧 / 连续剧情",
        "style": "可爱、温暖、轻反转、适合连续更新",
        "audience": "喜欢萌宠、治愈、拟人剧情的用户",
        "tone": "轻松、治愈、带一点委屈和反击",
        "structure": "萌宠困境 -> 情绪共鸣 -> 小反转 -> 治愈收束",
        "cta": "引导关注下一集",
    },
}

CREATIVE_PRESETS.update(
    {
        "default": {
            "label": "通用短剧模板",
            "genre": "短剧 / 情绪反转",
            "style": "节奏清晰、冲突明确、适合短视频",
            "audience": "短视频泛内容用户",
            "tone": "有悬念、有转折",
            "structure": "开场钩子 -> 冲突升级 -> 反转证明 -> 收束行动",
            "cta": "引导关注或收藏",
        },
        "mysticism_lead": {
            "label": "玄学引流模板",
            "genre": "玄学 / 情绪疗愈 / 引流短剧",
            "style": "神秘、治愈、带命运感和反转感",
            "audience": "关注星座、运势、情绪疗愈和自我成长的用户",
            "tone": "温柔、有悬念、笃定",
            "structure": "命运钩子 -> 情绪共鸣 -> 暗示转机 -> 收藏/评论引导",
            "cta": "引导收藏、评论关键词或私信",
        },
        "ancient爽文": {
            "label": "古风爽文漫剧",
            "genre": "古风 / 穿越 / 爽文漫剧",
            "style": "热血、盛唐史诗感、强反击爽点",
            "audience": "喜欢穿越、逆袭、古风爽文的用户",
            "tone": "压迫感强、反击干脆、情绪燃",
            "structure": "现代困境 -> 穿越死局 -> 当众反击 -> 权威震动 -> 山河展开",
            "cta": "引导追更下一集",
        },
        "ai_pet": {
            "label": "AI 小动物剧情",
            "genre": "AI 小动物 / 治愈短剧 / 连续剧情",
            "style": "可爱、温暖、轻反转、适合连续更新",
            "audience": "喜欢萌宠、治愈、拟人剧情的用户",
            "tone": "轻松、治愈、带一点委屈和反击",
            "structure": "萌宠困境 -> 情绪共鸣 -> 小反转 -> 治愈收束",
            "cta": "引导关注下一集",
        },
    }
)


SCRIPT_JSON_CONTRACT = """
只返回一个合法 JSON 对象，不要返回 Markdown、解释或代码块。JSON 结构必须是：
{
  "config": {
    "title": "短视频标题",
    "genre": "类型，例如：古风 / 穿越 / 爽文漫剧",
    "resolution": "9:16",
    "fps": 30,
    "style": "整体风格",
    "audience": "目标人群",
    "total_duration_seconds": 30
  },
  "scenes": [
    {
      "id": 1,
      "title": "镜头标题，例如：小墨看日历",
      "summary": "一句核心画面概括",
      "estimated_duration": 3,
      "scene_goal": "这一幕承担的叙事作用，例如开场钩子/铺垫/反转/证明/收束",
      "audio_narration": "给 TTS 引擎朗读的旁白文本",
      "onscreen_text": "这一幕建议显示在画面上的短字幕或花字",
      "visual_prompt": "这一幕需要的画面/生图/视频提示词",
      "assets": {
        "video_path": "",
        "image_path": "",
        "audio_path": "",
        "duration": 0
      },
      "edit": {
        "transition": "fade",
        "animation": "zoom_in",
        "pacing": "节奏说明",
        "camera": "镜头运动建议"
      },
      "status": "waiting_assets"
    }
  ]
}
要求：
1. scenes 数量必须等于用户要求的分镜数量。
2. id 从 1 开始递增。
3. 每个 scene 是一个扁平原子镜头，禁止输出 characters、dialogue、action、shot_id、start_time、end_time 等复杂结构。
4. visual_prompt 是视觉轨，给生图/视频模型使用；audio_narration 是听觉轨，给 TTS 引擎使用。
5. 只能输出 estimated_duration，禁止计算绝对时间戳。
6. assets 内路径必须保持空字符串，duration 必须为 0。
7. status 必须是 waiting_assets。
""".strip()


class VideoScriptGenerator:
    def __init__(self) -> None:
        load_dotenv()

    def generate(self, payload: ScriptGenerateRequest) -> dict[str, Any]:
        project_id = uuid4().hex
        return self.generate_with_project_id(payload, project_id)

    def generate_from_natural_language(
        self,
        payload: NaturalLanguageScriptRequest,
        project_id: str,
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        if progress:
            progress(8, "解析剪映自然语言输入")
        parsed = JianyingScriptInputParser().parse(
            payload.input,
            title=payload.title,
            provider=payload.provider,
            creative_preset=payload.creative_preset,
            duration_seconds=payload.duration_seconds,
            scene_count=payload.scene_count,
            resolution=payload.resolution,
        )
        if progress:
            progress(14, f"识别为 {parsed.intent}，准备生成结构化剧本")
        generation_mode = payload.generation_mode or "local"
        if generation_mode == "sdk":
            result = self.generate_with_sdk_project_id(parsed.script_request, project_id, progress=progress)
        else:
            result = self.generate_with_project_id(parsed.script_request, project_id, progress=progress)
        metadata_path = Path(result["metadata_path"])
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        metadata["natural_language_input"] = parsed.raw_text
        metadata["jianying_editor_intent"] = parsed.intent
        metadata["jianying_editor_notes"] = parsed.notes
        metadata["source_paths"] = parsed.source_paths
        metadata["generation_mode"] = generation_mode
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        result["parsed_input"] = {
            "intent": parsed.intent,
            "request": parsed.script_request.model_dump(),
            "source_paths": parsed.source_paths,
            "notes": parsed.notes,
        }
        result["generation_mode"] = generation_mode
        return result

    def generate_with_sdk_project_id(
        self,
        payload: ScriptGenerateRequest,
        project_id: str,
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        if progress:
            progress(22, "调用 JianYing Editor Skill SDK")
        generated = JianyingEditorSdkScriptGenerator().generate(payload, project_id)
        if progress:
            progress(86, "整理 SDK script.json")
        return self.save(
            generated.script,
            provider=payload.provider or active_ai_provider("mock"),
            prompt=self._prompt(payload),
            raw_text=json.dumps(generated.raw_output, ensure_ascii=False, indent=2),
            metadata_extra={
                "generation_mode": "sdk",
                "sdk_notes": generated.notes,
            },
        )

    def generate_with_project_id(
        self,
        payload: ScriptGenerateRequest,
        project_id: str,
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        provider = payload.provider or active_ai_provider("mock")
        if provider == "mock":
            if progress:
                progress(30, "生成剧本大纲")
            script = self._mock_script(payload, project_id)
            for index in range(payload.scene_count):
                if progress:
                    progress(35 + int((index + 1) / payload.scene_count * 45), f"扩写第 {index + 1} 幕")
            return self.save(script, provider=provider, prompt=self._prompt(payload))

        outline_prompt = self._outline_prompt(payload)
        if progress:
            progress(25, "生成剧本大纲")
        outline_text = self._call_model(provider, outline_prompt)
        outline = self._parse_json(outline_text)
        script = self._script_from_outline(outline, payload, project_id)
        generated_scenes: list[dict[str, Any]] = []

        for index in range(payload.scene_count):
            scene_prompt = self._scene_prompt(payload, script, outline, index + 1, generated_scenes)
            if progress:
                progress(30 + int(index / max(1, payload.scene_count) * 55), f"生成第 {index + 1} 幕")
            scene_text = self._call_model(provider, scene_prompt)
            scene_data = self._parse_json(scene_text)
            scene = self._normalize_scene(scene_data, index + 1)
            script.scenes.append(scene)
            generated_scenes.append(scene.model_dump())

        if progress:
            progress(88, "整理 script.json")
        return self.save(
            script,
            provider=provider,
            prompt="\n\n--- OUTLINE ---\n\n".join([outline_prompt, self._prompt(payload)]),
            raw_text=outline_text,
            metadata_extra={"generation_mode": "local"},
        )

    def save(
        self,
        script: VideoScript,
        *,
        provider: str = "",
        prompt: str = "",
        raw_text: str = "",
        metadata_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        project_dir = self.project_dir(script.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        now = int(time.time())
        record = {
            "project_id": script.project_id,
            "provider": provider,
            "prompt": prompt,
            "raw_model_text": raw_text,
            "created_at": now,
            "updated_at": now,
            "script": script.model_dump(),
        }
        if metadata_extra:
            record.update(metadata_extra)
        existing = self.load_record(script.project_id)
        if existing:
            record["created_at"] = existing.get("created_at", now)
        (project_dir / "script.json").write_text(
            json.dumps(script.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (project_dir / "metadata.json").write_text(
            json.dumps({key: value for key, value in record.items() if key != "script"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        save_jianying_draft(
            draft_id=f"script-{script.project_id}",
            name=script.config.title or f"script-{script.project_id}",
            draft_path=str(project_dir),
            source="script_ready",
            status="script_ready",
            meta={
                "script_path": str(project_dir / "script.json"),
                "metadata_path": str(project_dir / "metadata.json"),
                "provider": provider,
                "scene_count": len(script.scenes),
                "title": script.config.title,
                "generation_mode": (metadata_extra or {}).get("generation_mode", "local"),
            },
        )
        return {
            "project_id": script.project_id,
            "script": script.model_dump(),
            "script_path": str(project_dir / "script.json"),
            "metadata_path": str(project_dir / "metadata.json"),
            "provider": provider,
            "generation_mode": (metadata_extra or {}).get("generation_mode", "local"),
        }

    def expand(self, project_id: str, payload: ScriptExpandRequest) -> dict[str, Any]:
        loaded = self.load(project_id)
        if not loaded:
            raise ValueError("Video script project not found")
        script = VideoScript.model_validate(loaded["script"])
        provider = payload.provider or active_ai_provider("mock")
        if provider == "mock":
            expanded = self._mock_expand(script, payload)
        else:
            raw_text = self._call_model(provider, self._expand_prompt(script, payload))
            data = self._parse_json(raw_text)
            expanded = self._normalize_expand_result(script, data, payload)
        return self.save(expanded, provider=provider, prompt=self._expand_prompt(script, payload))

    def load(self, project_id: str) -> dict[str, Any] | None:
        script_path = self.project_dir(project_id) / "script.json"
        if not script_path.exists():
            return None
        script = VideoScript.model_validate(json.loads(script_path.read_text(encoding="utf-8")))
        metadata = self.load_record(project_id) or {}
        return {
            "project_id": project_id,
            "script": script.model_dump(),
            "script_path": str(script_path),
            "metadata": metadata,
        }

    def list_projects(self, limit: int = 100) -> list[dict[str, Any]]:
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        items: list[dict[str, Any]] = []
        for script_path in PROJECTS_DIR.glob("*/script.json"):
            try:
                script = VideoScript.model_validate(json.loads(script_path.read_text(encoding="utf-8")))
                metadata = self.load_record(script.project_id) or {}
                items.append(
                    {
                        "project_id": script.project_id,
                        "title": script.config.title,
                        "genre": script.config.genre,
                        "scene_count": len(script.scenes),
                        "resolution": script.config.resolution,
                        "generation_mode": metadata.get("generation_mode") or "local",
                        "updated_at": metadata.get("updated_at") or int(script_path.stat().st_mtime),
                        "script_path": str(script_path),
                    }
                )
            except Exception:
                continue
        return sorted(items, key=lambda item: item.get("updated_at") or 0, reverse=True)[:limit]

    def delete_project(self, project_id: str) -> bool:
        project_dir = self.project_dir(project_id)
        if not project_dir.exists():
            return False
        shutil.rmtree(project_dir)
        return True

    def load_record(self, project_id: str) -> dict[str, Any] | None:
        metadata_path = self.project_dir(project_id) / "metadata.json"
        if not metadata_path.exists():
            return None
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def project_dir(self, project_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", project_id)
        return PROJECTS_DIR / safe_id

    def _prompt(self, payload: ScriptGenerateRequest) -> str:
        preset = self._preset(payload)
        return "\n\n".join(
            [
                "你是短视频编导。请把用户灵感拆成可用于剪映草稿生产的结构化分镜剧本。",
                "请大胆扩写，不要只复述用户的一句话。要补出冲突、转折、爽点、画面概括、旁白、屏幕花字和剪辑节奏。",
                "如果需要人物、对白或动作，请压缩进 summary、audio_narration、onscreen_text、visual_prompt，不要新增 characters、dialogue、action 字段。",
                "如果用户只写一句话，请自动判断题材并写成有开端、冲突、反转和收束的短剧章节。",
                f"标题：{payload.title}",
                f"灵感：{payload.idea}",
                f"创作预设：{preset['label']}",
                f"类型：{payload.genre or preset['genre']}",
                f"风格：{payload.style or preset['style']}",
                f"目标人群：{payload.audience or preset['audience']}",
                f"语气：{payload.tone or preset['tone']}",
                f"结构偏好：{payload.structure or preset['structure']}",
                f"行动号召：{payload.cta or preset['cta']}",
                f"分镜数量：{payload.scene_count}",
                f"总时长：{payload.duration_seconds} 秒",
                f"视频比例：{payload.resolution}",
                JIANYING_SCRIPT_CONTRACT,
                SCRIPT_JSON_CONTRACT,
            ]
        )

    def _outline_prompt(self, payload: ScriptGenerateRequest) -> str:
        preset = self._preset(payload)
        return "\n\n".join(
            [
                "你是短剧总编剧。请先根据一句话灵感生成剧本大纲，不要写完整分镜。",
                "只返回 JSON，不要 Markdown。结构：",
                '{"config":{"title":"","genre":"","style":"","audience":"","total_duration_seconds":0},"outline":[{"id":1,"title":"","summary":"","scene_goal":"","estimated_duration":3}]}',
                f"标题：{payload.title}",
                f"灵感：{payload.idea}",
                f"创作预设：{preset['label']}",
                f"类型：{payload.genre or preset['genre']}",
                f"风格：{payload.style or preset['style']}",
                f"目标人群：{payload.audience or preset['audience']}",
                f"语气：{payload.tone or preset['tone']}",
                f"结构偏好：{payload.structure or preset['structure']}",
                f"行动号召：{payload.cta or preset['cta']}",
                f"分镜数量：{payload.scene_count}",
                f"总时长：{payload.duration_seconds} 秒",
                JIANYING_SCRIPT_CONTRACT,
                "要求：outline 数量必须等于分镜数量；每一幕只写扁平摘要和预估时长，不写时间戳。",
            ]
        )

    def _scene_prompt(
        self,
        payload: ScriptGenerateRequest,
        script: VideoScript,
        outline: dict[str, Any],
        scene_id: int,
        generated_scenes: list[dict[str, Any]],
    ) -> str:
        outline_items = outline.get("outline") if isinstance(outline.get("outline"), list) else []
        current_outline = outline_items[scene_id - 1] if scene_id - 1 < len(outline_items) else {}
        return "\n\n".join(
            [
                "你是短剧分镜编剧。请只生成当前这一幕的完整分镜 JSON。",
                "不要一次性生成全部剧本。只返回一个 JSON 对象，字段必须符合 scene 结构。",
                f"当前生成：第 {scene_id} 幕",
                f"剧本配置：{json.dumps(script.config.model_dump(), ensure_ascii=False)}",
                f"当前幕大纲：{json.dumps(current_outline, ensure_ascii=False)}",
                f"已生成前文：{json.dumps(generated_scenes, ensure_ascii=False)}",
                f"原始灵感：{payload.idea}",
                JIANYING_SCRIPT_CONTRACT,
                "scene JSON 字段：id, title, summary, estimated_duration, scene_goal, visual_prompt, audio_narration, onscreen_text, assets, edit, status。",
                "重点字段：visual_prompt 给画图 AI；audio_narration 给 TTS；onscreen_text 给屏幕花字。不要把对象塞进字符串。",
                "要求：只生成扁平原子镜头；禁止 characters、dialogue、action、shot_id、start_time、end_time；assets 路径必须为空，duration 为 0，status 为 waiting_assets。",
            ]
        )

    def _script_from_outline(self, outline: dict[str, Any], payload: ScriptGenerateRequest, project_id: str) -> VideoScript:
        preset = self._preset(payload)
        config = outline.get("config") if isinstance(outline.get("config"), dict) else {}
        return VideoScript(
            project_id=project_id,
            config=VideoScriptConfig(
                title=str(config.get("title") or payload.title or "未命名短视频"),
                genre=str(config.get("genre") or payload.genre or preset["genre"]),
                resolution=payload.resolution,
                fps=30,
                style=str(config.get("style") or payload.style or preset["style"]),
                audience=str(config.get("audience") or payload.audience or preset["audience"]),
                total_duration_seconds=float(config.get("total_duration_seconds") or payload.duration_seconds or 0),
            ),
            scenes=[],
        )

    def _normalize_scene(self, data: dict[str, Any], scene_id: int) -> VideoScene:
        scene = data.get("scene") if isinstance(data.get("scene"), dict) else data
        return VideoScene.model_validate(
            {
                "id": scene_id,
                "title": str(scene.get("title") or self._default_act_title(scene_id)),
                "summary": str(scene.get("summary") or ""),
                "estimated_duration": float(scene.get("estimated_duration") or 3),
                "scene_goal": str(scene.get("scene_goal") or ""),
                "audio_narration": str(scene.get("audio_narration") or scene.get("narration") or scene.get("summary") or ""),
                "onscreen_text": str(scene.get("onscreen_text") or ""),
                "visual_prompt": str(scene.get("visual_prompt") or ""),
                "assets": {"video_path": "", "image_path": "", "audio_path": "", "duration": 0},
                "edit": {
                    "transition": ((scene.get("edit") or {}).get("transition") if isinstance(scene.get("edit"), dict) else None) or "fade",
                    "animation": ((scene.get("edit") or {}).get("animation") if isinstance(scene.get("edit"), dict) else None) or "zoom_in",
                    "pacing": ((scene.get("edit") or {}).get("pacing") if isinstance(scene.get("edit"), dict) else None) or "",
                    "camera": ((scene.get("edit") or {}).get("camera") if isinstance(scene.get("edit"), dict) else None) or "",
                },
                "status": "waiting_assets",
            }
        )

    def _expand_prompt(self, script: VideoScript, payload: ScriptExpandRequest) -> str:
        return "\n\n".join(
            [
                "你是短剧编导。请基于已有 script.json 继续扩写后续章节/分镜。",
                "只返回 JSON 对象，结构为：{\"scenes\": [...]}。新增 scenes 必须沿用原结构。",
                f"扩写数量：{payload.expand_count}",
                f"额外灵感：{payload.idea or '承接当前剧情自然推进'}",
                f"已有剧本：{json.dumps(script.model_dump(), ensure_ascii=False)}",
                JIANYING_SCRIPT_CONTRACT,
                SCRIPT_JSON_CONTRACT,
            ]
        )

    def _call_model(self, provider: str, prompt: str) -> str:
        if provider == "gemini":
            return self._call_gemini(prompt)
        return self._call_openai_compatible(provider, prompt)

    def _call_gemini(self, prompt: str) -> str:
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
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
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
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Missing dependency google-genai. Run: pip install -r requirements.txt") from exc
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=prompt)
        return (response.text or "").strip()

    def _call_openai_compatible(self, provider: str, prompt: str) -> str:
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
            return data.get("output_text") or self._extract_responses_text(data)

        response = requests.post(
            f"{base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You return valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
            },
            timeout=120,
        )
        if not response.ok:
            raise RuntimeError(f"Chat completions HTTP {response.status_code}: {response.text[:500]}")
        data = response.json()
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")

    def _extract_responses_text(self, data: dict[str, Any]) -> str:
        chunks: list[str] = []
        for item in data.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") in {"output_text", "text"}:
                    chunks.append(content.get("text", ""))
        return "\n".join(chunk for chunk in chunks if chunk).strip()

    def _parse_json(self, text: str) -> dict[str, Any]:
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

    def _normalize_expand_result(self, script: VideoScript, data: dict[str, Any], payload: ScriptExpandRequest) -> VideoScript:
        scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
        start_id = len(script.scenes) + 1
        for offset, scene in enumerate(scenes[: payload.expand_count]):
            if not isinstance(scene, dict):
                scene = {}
            scene_id = start_id + offset
            script.scenes.append(
                VideoScene.model_validate(
                    {
                        "id": scene_id,
                        "title": str(scene.get("title") or self._default_act_title(scene_id)),
                        "summary": str(scene.get("summary") or ""),
                        "estimated_duration": float(scene.get("estimated_duration") or 3),
                        "scene_goal": str(scene.get("scene_goal") or "承接上一幕推进剧情"),
                        "audio_narration": str(scene.get("audio_narration") or scene.get("narration") or scene.get("summary") or ""),
                        "onscreen_text": str(scene.get("onscreen_text") or ""),
                        "visual_prompt": str(scene.get("visual_prompt") or ""),
                        "asset_requirements": self._normalize_asset_requirements(scene.get("asset_requirements")),
                        "assets": {"video_path": "", "image_path": "", "audio_path": "", "duration": 0},
                        "edit": {
                            "transition": ((scene.get("edit") or {}).get("transition") if isinstance(scene.get("edit"), dict) else None) or "fade",
                            "animation": ((scene.get("edit") or {}).get("animation") if isinstance(scene.get("edit"), dict) else None) or "zoom_in",
                            "pacing": ((scene.get("edit") or {}).get("pacing") if isinstance(scene.get("edit"), dict) else None) or "",
                            "camera": ((scene.get("edit") or {}).get("camera") if isinstance(scene.get("edit"), dict) else None) or "",
                        },
                        "status": "waiting_assets",
                    }
                )
            )
        while len(script.scenes) < start_id + payload.expand_count - 1:
            scene_id = len(script.scenes) + 1
            script.scenes.append(self._mock_expand_scene(script, scene_id, payload.idea))
        return script

    def _default_act_title(self, index: int) -> str:
        titles = ["序幕", "第一幕", "第二幕", "第三幕", "第四幕", "第五幕"]
        return titles[index - 1] if index <= len(titles) else f"第 {index} 幕"

    def _normalize_asset_requirements(self, value: Any) -> dict[str, Any]:
        source = value if isinstance(value, dict) else {}
        return {
            "visual_type": str(source.get("visual_type") or "video_or_image"),
            "main_subject": str(source.get("main_subject") or ""),
            "background": str(source.get("background") or ""),
            "mood": str(source.get("mood") or ""),
            "must_have": self._string_list(source.get("must_have")),
            "avoid": self._string_list(source.get("avoid")),
        }

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in re.split(r"[,，、\n]", value) if item.strip()]
        return []

    def _preset(self, payload: ScriptGenerateRequest) -> dict[str, str]:
        return CREATIVE_PRESETS.get(payload.creative_preset, CREATIVE_PRESETS["default"])

    def _mock_expand(self, script: VideoScript, payload: ScriptExpandRequest) -> VideoScript:
        for _ in range(payload.expand_count):
            scene_id = len(script.scenes) + 1
            script.scenes.append(self._mock_expand_scene(script, scene_id, payload.idea))
        return script

    def _normalize_script(self, data: dict[str, Any], payload: ScriptGenerateRequest, project_id: str) -> VideoScript:
        preset = self._preset(payload)
        config = data.get("config") if isinstance(data.get("config"), dict) else {}
        scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
        normalized_scenes = [self._normalize_scene(scene if isinstance(scene, dict) else {}, index) for index, scene in enumerate(scenes[: payload.scene_count], start=1)]
        while len(normalized_scenes) < payload.scene_count:
            scene_id = len(normalized_scenes) + 1
            title = self._default_act_title(scene_id)
            normalized_scenes.append(
                VideoScene(
                    id=scene_id,
                    title=title,
                    summary=f"{title} placeholder scene",
                    estimated_duration=3,
                    scene_goal="Continue the narrative with one focused beat.",
                    audio_narration=f"{title}: narration placeholder, waiting for AI rewrite.",
                    onscreen_text=title,
                    visual_prompt=f"{title}, clean short-video frame, clear subject, cinematic composition",
                    asset_requirements=self._normalize_asset_requirements(
                        {
                            "visual_type": "video_or_image",
                            "main_subject": title,
                            "background": "clean short-video frame",
                            "mood": "neutral",
                            "must_have": [title],
                            "avoid": [],
                        }
                    ),
                    assets={"video_path": "", "image_path": "", "audio_path": "", "duration": 0},
                    edit={"transition": "fade", "animation": "zoom_in", "pacing": "steady", "camera": "slow push in"},
                    status="waiting_assets",
                )
            )
        return VideoScript(
            project_id=project_id,
            config=VideoScriptConfig(
                title=str(config.get("title") or payload.title or "Untitled short video"),
                genre=str(config.get("genre") or payload.genre or preset["genre"]),
                resolution=payload.resolution,
                fps=int(config.get("fps") or 30),
                style=str(config.get("style") or payload.style or preset["style"]),
                audience=str(config.get("audience") or payload.audience or preset["audience"]),
                total_duration_seconds=float(config.get("total_duration_seconds") or payload.duration_seconds or 0),
            ),
            scenes=normalized_scenes,
        )

    def _mock_script(self, payload: ScriptGenerateRequest, project_id: str) -> VideoScript:
        preset = self._preset(payload)
        title_text = (payload.title or "Untitled short video").strip()
        idea = (payload.idea or title_text).strip()
        per_scene_duration = round(payload.duration_seconds / max(1, payload.scene_count), 1)
        goals = ["opening hook", "emotional setup", "core reveal", "turning point", "closing action"]
        scenes: list[VideoScene] = []
        for index in range(1, payload.scene_count + 1):
            goal = goals[(index - 1) % len(goals)]
            scene_title = f"Scene {index}"
            summary = f"{goal}: {idea[:36]}"
            narration = (
                f"{title_text} scene {index}. {idea[:48]} "
                f"is shaped into a {payload.tone or preset['tone']} beat, pushing the viewer to the next moment."
            )
            scenes.append(
                VideoScene(
                    id=index,
                    title=scene_title,
                    summary=summary,
                    estimated_duration=per_scene_duration,
                    scene_goal=goal,
                    audio_narration=narration,
                    onscreen_text=f"{title_text} · {index}",
                    visual_prompt=(
                        f"{payload.style or preset['style']}, {summary}, clear subject, cinematic composition, "
                        f"short-video frame, {payload.resolution}, no text watermark"
                    ),
                    assets={"video_path": "", "image_path": "", "audio_path": "", "duration": 0},
                    edit={"transition": "fade", "animation": "zoom_in", "pacing": f"about {per_scene_duration}s", "camera": "slow push in"},
                    status="waiting_assets",
                )
            )
        return VideoScript(
            project_id=project_id,
            config=VideoScriptConfig(
                title=title_text,
                genre=payload.genre or preset["genre"],
                resolution=payload.resolution,
                fps=30,
                style=payload.style or preset["style"],
                audience=payload.audience or preset["audience"],
                total_duration_seconds=payload.duration_seconds,
            ),
            scenes=scenes,
        )

    def _mock_expand_scene(self, script: VideoScript, scene_id: int, idea: str = "") -> VideoScene:
        title = script.config.title or "Untitled short video"
        cue = (idea or title).strip()
        summary = f"new conflict beat: {cue[:36]}"
        narration = f"{title} continues. {cue[:48]} becomes the next pressure point, forcing the story into a stronger turn."
        return VideoScene(
            id=scene_id,
            title=f"Scene {scene_id}",
            summary=summary,
            estimated_duration=3,
            scene_goal="Extend the current story with one new atomic beat.",
            audio_narration=narration,
            onscreen_text=f"{title} · new beat",
            visual_prompt=f"{title}, {summary}, dramatic cinematic short-video frame, clear subject, high tension",
            assets={"video_path": "", "image_path": "", "audio_path": "", "duration": 0},
            edit={"transition": "fade", "animation": "zoom_in", "pacing": "faster", "camera": "push in to the subject"},
            status="waiting_assets",
        )

    def generate_bible(self, payload: BibleGenerateRequest) -> dict[str, Any]:
        provider = payload.provider or active_ai_provider("mock")
        if provider == "mock":
            bible = self._mock_bible(payload)
            return {"bible": bible.model_dump(), "provider": provider, "prompt": self._bible_prompt(payload)}
        raw_text = self._call_model(provider, self._bible_prompt(payload))
        bible = self._normalize_bible(self._parse_json(raw_text), payload)
        return {"bible": bible.model_dump(), "provider": provider, "prompt": self._bible_prompt(payload), "raw_model_text": raw_text}

    def generate_blueprint_with_project_id(
        self,
        payload: BlueprintGenerateRequest,
        project_id: str,
        progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        provider = payload.provider or active_ai_provider("mock")
        if progress:
            progress(20, "已锁定设定集，准备生成分镜")
        if provider == "mock":
            script = self._mock_blueprint(payload, project_id)
            if progress:
                progress(80, "生成原子镜头卡片")
            return self.save(script, provider=provider, prompt=self._blueprint_prompt(payload))

        raw_text = self._call_model(provider, self._blueprint_prompt(payload))
        data = self._parse_json(raw_text)
        script = self._normalize_blueprint(data, payload, project_id)
        if progress:
            progress(88, "整理资产清单")
        return self.save(script, provider=provider, prompt=self._blueprint_prompt(payload), raw_text=raw_text)

    def _bible_prompt(self, payload: BibleGenerateRequest) -> str:
        preset = self._preset_from_name(payload.creative_preset)
        return "\n\n".join(
            [
                "You are an AI short-video art director. Return JSON only. Do not write scenes yet.",
                "Create a ConceptBible for the user idea. Fields must be: art_style_prompt, character_base_prompt, voice_vibe, bgm_keywords.",
                "art_style_prompt: global visual style, Midjourney-friendly.",
                "character_base_prompt: fixed protagonist visual traits, Midjourney-friendly.",
                "voice_vibe: global TTS voice and emotion direction.",
                "bgm_keywords: short searchable music keywords.",
                f"Title: {payload.title}",
                f"Genre: {payload.genre or preset['genre']}",
                f"Preset style: {preset['style']}",
                f"Idea: {payload.idea}",
            ]
        )

    def _blueprint_prompt(self, payload: BlueprintGenerateRequest) -> str:
        preset = self._preset_from_name(payload.creative_preset)
        return "\n\n".join(
            [
                "You are an AI short-video storyboard writer. Return JSON only.",
                "Based on the locked ConceptBible, expand the idea into atomic scene cards.",
                "Return structure: {\"scenes\":[...]} only. Each scene must include: id, title, summary, estimated_duration, scene_goal, visual_prompt, audio_narration, onscreen_text, assets, edit, status.",
                "visual_prompt must include the locked art style and character traits. audio_narration must match the locked voice vibe.",
                "No absolute timestamps. No characters/dialogue/action/shot_id/start_time/end_time. Asset paths must be empty strings.",
                f"Title: {payload.title}",
                f"Genre: {payload.genre or preset['genre']}",
                f"Idea: {payload.idea}",
                f"Scene count: {payload.scene_count}",
                f"Total duration seconds: {payload.duration_seconds}",
                f"Resolution: {payload.resolution}",
                f"Locked ConceptBible: {json.dumps(payload.bible.model_dump(), ensure_ascii=False)}",
                SCRIPT_JSON_CONTRACT,
            ]
        )

    def _normalize_bible(self, data: dict[str, Any], payload: BibleGenerateRequest) -> ConceptBible:
        bible = data.get("bible") if isinstance(data.get("bible"), dict) else data
        mock = self._mock_bible(payload)
        return ConceptBible(
            art_style_prompt=str(bible.get("art_style_prompt") or mock.art_style_prompt),
            character_base_prompt=str(bible.get("character_base_prompt") or mock.character_base_prompt),
            voice_vibe=str(bible.get("voice_vibe") or mock.voice_vibe),
            bgm_keywords=str(bible.get("bgm_keywords") or mock.bgm_keywords),
        )

    def _normalize_blueprint(self, data: dict[str, Any], payload: BlueprintGenerateRequest, project_id: str) -> VideoScript:
        scene_items = data.get("scenes") if isinstance(data.get("scenes"), list) else []
        scenes = []
        for index, item in enumerate(scene_items[: payload.scene_count], start=1):
            scene = self._normalize_scene(item if isinstance(item, dict) else {}, index)
            scene.visual_prompt = self._compose_visual_prompt(payload.bible, scene.visual_prompt)
            scene.assets.video_path = ""
            scene.assets.image_path = ""
            scene.assets.audio_path = ""
            scene.assets.duration = 0
            scenes.append(scene)
        while len(scenes) < payload.scene_count:
            scenes.append(self._mock_blueprint_scene(payload, len(scenes) + 1))
        return VideoScript(
            project_id=project_id,
            bible=payload.bible,
            config=VideoScriptConfig(
                title=payload.title or "Untitled short video",
                genre=payload.genre or self._preset_from_name(payload.creative_preset)["genre"],
                resolution=payload.resolution,
                fps=30,
                style=payload.bible.art_style_prompt,
                audience="",
                total_duration_seconds=payload.duration_seconds,
            ),
            scenes=scenes,
        )

    def _mock_bible(self, payload: BibleGenerateRequest) -> ConceptBible:
        preset = self._preset_from_name(payload.creative_preset)
        idea = payload.idea.strip()
        return ConceptBible(
            art_style_prompt=f"{preset['style']}, cinematic lighting, vertical short video, rich details, no watermark",
            character_base_prompt=f"consistent protagonist inspired by {idea[:32]}, expressive face, clean silhouette, distinctive outfit",
            voice_vibe=f"{preset['tone']}, clear Mandarin narration, steady emotional rhythm",
            bgm_keywords=f"{payload.genre or preset['genre']}, mysterious, cinematic, emotional build",
        )

    def _mock_blueprint(self, payload: BlueprintGenerateRequest, project_id: str) -> VideoScript:
        scenes = [self._mock_blueprint_scene(payload, index) for index in range(1, payload.scene_count + 1)]
        return VideoScript(
            project_id=project_id,
            bible=payload.bible,
            config=VideoScriptConfig(
                title=payload.title or "Untitled short video",
                genre=payload.genre or self._preset_from_name(payload.creative_preset)["genre"],
                resolution=payload.resolution,
                fps=30,
                style=payload.bible.art_style_prompt,
                audience="",
                total_duration_seconds=payload.duration_seconds,
            ),
            scenes=scenes,
        )

    def _mock_blueprint_scene(self, payload: BlueprintGenerateRequest, index: int) -> VideoScene:
        per_scene_duration = round(payload.duration_seconds / max(1, payload.scene_count), 1)
        goals = ["开场钩子", "情绪共鸣", "核心暗示", "转折强化", "行动收束"]
        goal = goals[(index - 1) % len(goals)]
        summary = f"{goal}: {payload.idea[:36]}"
        local_visual = f"{summary}, focused composition, strong readable subject, scene {index}"
        return VideoScene(
            id=index,
            title=f"Scene {index}",
            summary=summary,
            estimated_duration=per_scene_duration,
            scene_goal=goal,
            visual_prompt=self._compose_visual_prompt(payload.bible, local_visual),
            audio_narration=f"{payload.idea[:48]}，这一刻进入{goal}，用一句有记忆点的旁白推动用户继续看下去。",
            onscreen_text=f"{goal}",
            assets={"video_path": "", "image_path": "", "audio_path": "", "duration": 0},
            edit={"transition": "fade", "animation": "zoom_in", "pacing": payload.bible.voice_vibe, "camera": "slow push in"},
            status="waiting_assets",
        )

    def _compose_visual_prompt(self, bible: ConceptBible, local_prompt: str) -> str:
        chunks = [bible.art_style_prompt, bible.character_base_prompt, local_prompt]
        return ", ".join(chunk.strip() for chunk in chunks if chunk and chunk.strip())

    def _preset_from_name(self, name: str) -> dict[str, str]:
        return CREATIVE_PRESETS.get(name, CREATIVE_PRESETS["default"])
