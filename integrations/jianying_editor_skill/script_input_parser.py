from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from integrations.video_pipeline.script_schema import ScriptGenerateRequest


JIANYING_SCRIPT_CONTRACT = """
JianYing Editor Skill 剧本输出约束：
1. 把用户自然语言输入拆成可执行剪映草稿的原子镜头，不只复述输入。
2. 每个镜头必须同时给出视觉轨 visual_prompt、听觉轨 audio_narration、屏幕花字 onscreen_text。
3. 用秒作为时长单位，只输出 estimated_duration，不输出 HH:MM:SS、帧号、start_time、end_time。
4. assets.video_path / image_path / audio_path 暂时保持空字符串，duration 为 0，等待后续素材回填。
5. edit 字段要包含 transition、animation、pacing、camera，用于后续剪映自动化组装。
6. 返回合法 JSON 对象，禁止 Markdown 代码块和解释文本。
""".strip()


@dataclass
class ParsedJianyingInput:
    script_request: ScriptGenerateRequest
    raw_text: str
    intent: str
    source_paths: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class JianyingScriptInputParser:
    """Parse free-form editing instructions into the local script schema.

    The rules mirror the jianying-editor-skill examples: users can ask for a
    vlog, commentary, tutorial, web VFX intro, or generic short video in one
    sentence. This parser extracts the stable production settings before the
    LLM expands the actual structured script.
    """

    PRESET_HINTS = [
        (re.compile(r"玄学|塔罗|星座|运势|疗愈"), "mysticism_lead", "玄学 / 情绪疗愈"),
        (re.compile(r"古风|盛唐|穿越|爽文|逆袭|修仙"), "ancient爽文", "古风 / 穿越 / 爽文漫剧"),
        (re.compile(r"萌宠|猫|狗|小动物|治愈"), "ai_pet", "AI 小动物 / 治愈短剧"),
    ]

    PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^，。；;\"'\n]+?\.(?:mp4|mov|mkv|avi|mp3|wav|png|jpg|jpeg|webm)|(?:\.{1,2}[\\/])?[^\s，。；;\"']+\.(?:mp4|mov|mkv|avi|mp3|wav|png|jpg|jpeg|webm)", re.I)

    def parse(
        self,
        text: str,
        *,
        title: str = "",
        provider: str | None = None,
        creative_preset: str = "",
        duration_seconds: int | None = None,
        scene_count: int | None = None,
        resolution: str = "",
    ) -> ParsedJianyingInput:
        raw_text = (text or "").strip()
        if not raw_text:
            raise ValueError("自然语言输入不能为空")

        intent = self._detect_intent(raw_text)
        inferred_title = title.strip() or self._infer_title(raw_text, intent)
        inferred_duration = duration_seconds or self._infer_duration(raw_text, intent)
        inferred_scene_count = scene_count or self._infer_scene_count(raw_text, inferred_duration, intent)
        inferred_resolution = resolution or self._infer_resolution(raw_text)
        preset = creative_preset or self._infer_preset(raw_text)
        genre = self._infer_genre(raw_text, intent, preset)
        style = self._infer_style(raw_text, intent)
        tone = self._infer_tone(raw_text, intent)
        structure = self._infer_structure(intent)
        cta = "引导关注、收藏或继续观看下一集" if intent != "movie_commentary" else "用悬念引导看完整解说"
        source_paths = self.PATH_PATTERN.findall(raw_text)

        notes = [
            "输入来自 JianYing Editor Skill 自然语言解析适配器",
            f"识别意图：{intent}",
        ]
        if source_paths:
            notes.append(f"识别素材路径：{', '.join(source_paths)}")

        request = ScriptGenerateRequest(
            title=inferred_title,
            idea=self._compose_idea(raw_text, intent, source_paths),
            creative_preset=preset,
            genre=genre,
            style=style,
            audience=self._infer_audience(raw_text, intent),
            tone=tone,
            structure=structure,
            cta=cta,
            duration_seconds=inferred_duration,
            scene_count=inferred_scene_count,
            resolution=inferred_resolution,  # type: ignore[arg-type]
            provider=provider,
        )
        return ParsedJianyingInput(script_request=request, raw_text=raw_text, intent=intent, source_paths=source_paths, notes=notes)

    def _detect_intent(self, text: str) -> str:
        if re.search(r"影视解说|解说|高光片段|原声片段|电影片段", text):
            return "movie_commentary"
        if re.search(r"录屏|教程|软件教程|智能变焦", text):
            return "screen_tutorial"
        if re.search(r"网页|HTML|Canvas|SVG|粒子|片头|动效|VFX", text, re.I):
            return "web_vfx"
        if re.search(r"Vlog|旅行|露营|日常|相册|照片", text, re.I):
            return "vlog"
        return "short_video"

    def _infer_title(self, text: str, intent: str) -> str:
        quoted = re.search(r"(?:标题|命名|叫|取名)[为叫：: ]*[“\"'「《](.+?)[”\"'」》]", text)
        if quoted:
            return quoted.group(1).strip()[:36]
        return self._timestamp_name()

    def _timestamp_name(self) -> str:
        return f"jianying_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def _infer_duration(self, text: str, intent: str) -> int:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(秒|s|分钟|min)", text, re.I)
        if match:
            value = float(match.group(1))
            seconds = int(value * 60 if match.group(2).lower() in {"分钟", "min"} else value)
            return max(5, min(600, seconds))
        if intent == "movie_commentary":
            return 60
        if intent == "web_vfx":
            return 5
        return 30

    def _infer_scene_count(self, text: str, duration: int, intent: str) -> int:
        match = re.search(r"(\d+)\s*(个)?\s*(镜头|分镜|片段|高光)", text)
        if match:
            return max(1, min(30, int(match.group(1))))
        if intent == "movie_commentary":
            return max(8, min(12, round(duration / 6)))
        if intent == "web_vfx":
            return max(1, min(4, round(duration / 2)))
        return max(3, min(10, round(duration / 6)))

    def _infer_resolution(self, text: str) -> str:
        if "16:9" in text or re.search(r"横屏|宽屏", text):
            return "16:9"
        if "1:1" in text or re.search(r"方形|正方形", text):
            return "1:1"
        return "9:16"

    def _infer_preset(self, text: str) -> str:
        for pattern, preset, _ in self.PRESET_HINTS:
            if pattern.search(text):
                return preset
        return "default"

    def _infer_genre(self, text: str, intent: str, preset: str) -> str:
        for _, item_preset, genre in self.PRESET_HINTS:
            if preset == item_preset:
                return genre
        genres = {
            "movie_commentary": "影视解说 / 高光混剪",
            "screen_tutorial": "软件教程 / 录屏演示",
            "web_vfx": "网页动效 / 片头 VFX",
            "vlog": "Vlog / 生活方式",
        }
        return genres.get(intent, "短视频 / 剧情分镜")

    def _infer_style(self, text: str, intent: str) -> str:
        style_bits = []
        for keyword in ["赛博朋克", "温柔", "治愈", "热血", "悬疑", "电影感", "科技感", "古风", "可爱", "高冷"]:
            if keyword in text:
                style_bits.append(keyword)
        defaults = {
            "movie_commentary": "犀利、幽默、强悬念、快节奏影视解说",
            "screen_tutorial": "清晰、专业、有重点标记的软件教学风格",
            "web_vfx": "视觉冲击强、适合片头的动态设计",
            "vlog": "轻快、真实、生活感、节奏自然",
        }
        return "、".join(style_bits) if style_bits else defaults.get(intent, "节奏清晰、冲突明确、适合短视频")

    def _infer_tone(self, text: str, intent: str) -> str:
        for keyword in ["幽默", "悬念", "温柔", "燃", "治愈", "压迫", "轻快", "高级"]:
            if keyword in text:
                return keyword
        return {
            "movie_commentary": "犀利、有悬念、短句推进",
            "screen_tutorial": "稳、清楚、有操作感",
            "web_vfx": "酷、干脆、视觉驱动",
            "vlog": "轻松、亲近、自然",
        }.get(intent, "有钩子、有转折")

    def _infer_audience(self, text: str, intent: str) -> str:
        return {
            "movie_commentary": "短视频影视解说观众",
            "screen_tutorial": "需要快速学会操作的软件用户",
            "web_vfx": "喜欢视觉冲击和片头包装的短视频观众",
            "vlog": "喜欢旅行、日常和生活方式内容的观众",
        }.get(intent, "短视频泛内容用户")

    def _infer_structure(self, intent: str) -> str:
        return {
            "movie_commentary": "开场悬念 -> 关键高光 -> 原声爆点 -> 反转总结",
            "screen_tutorial": "问题场景 -> 操作步骤 -> 重点标记 -> 结果展示",
            "web_vfx": "视觉引爆 -> 主体出现 -> 动效强化 -> 标题定格",
            "vlog": "开场氛围 -> 旅程片段 -> 细节情绪 -> 轻快收束",
        }.get(intent, "开场钩子 -> 冲突升级 -> 反转证明 -> 收束行动")

    def _compose_idea(self, text: str, intent: str, source_paths: list[str]) -> str:
        chunks = [text]
        if intent == "movie_commentary":
            chunks.append("按 JianYing Movie Commentary 模式生成：筛选 8-12 个高光片段，解说词用短句和标点拆分，保留适量原声爆点。")
        elif intent == "web_vfx":
            chunks.append("按 JianYing Web-to-Video 模式生成：把网页动效拆成可录制、可导入剪映的视觉分镜。")
        elif intent == "screen_tutorial":
            chunks.append("按 JianYing 录屏教程模式生成：强调鼠标点击、重点标记、智能变焦和步骤节奏。")
        if source_paths:
            chunks.append(f"用户提到的素材路径：{', '.join(source_paths)}。先作为素材线索写入镜头需求，不直接填入 assets 路径。")
        return "\n".join(chunks)
