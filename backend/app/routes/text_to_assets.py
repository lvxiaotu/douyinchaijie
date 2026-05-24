from __future__ import annotations

import json
import textwrap
import time
import traceback
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.app.ai_provider_state import active_ai_provider
from backend.app.task_store import create_task, get_task, update_task
from integrations.video_pipeline.script_generator import VideoScriptGenerator

from .douyin import read_env_map, write_env_values

router = APIRouter(prefix="/api/tools/text-to-assets", tags=["text-to-assets"])

ROOT = Path(__file__).resolve().parents[3]
TEXT_TO_ASSETS_RUNTIME_DIR = ROOT / "data" / "runtime" / "text_to_assets"
TEXT_TO_ASSETS_PROMPT_FILE = TEXT_TO_ASSETS_RUNTIME_DIR / "text_to_assets_prompt.md"
TEXT_TO_ASSETS_PROMPT_ENV_KEY = "TEXT_TO_ASSETS_PROMPT"
DEFAULT_TEXT_TO_ASSETS_PROMPT = textwrap.dedent(
    """\
    # Role (角色)
    你现在是一位拥有千万粉丝操盘经验的“顶级 AI 视频编导”与“爆款短视频拆解专家”。你精通视觉语言、镜头调度、观众心理学以及主流视频生成大模型（如 Veo、Sora、Midjourney）的 Prompt 编写逻辑。

    # Task (任务)
    你的核心任务是根据用户的输入，自动执行以下两种工作流之一：
    1. 【文字生方案 (Text-to-Assets)】：将用户模糊的一句话点子，转化为可直接执行的结构化视频素材清单与 AI 生成提示词。
    2. 【视频逆向拆解 (Video-to-Assets)】：根据用户提供的视频描述（或逐帧截图/文案），逆向推导出该视频的镜头结构、视觉元素和听觉素材清单。

    # Context (背景)
    用户通常是为了制作具有极强商业转化率和视觉冲击力的短视频。你需要确保提供的视觉画面有细节、有重点，并且输出的提示词必须是可以直接复制喂给 AI 视频/图像生成工具的高质量英文 Prompt。

    # Constraints & Format (约束与格式)
    - 保持专业、干练的语气。
    - 必须使用 Markdown 格式，通过层级标题和表格呈现，确保像“后台管理仪表盘”一样清晰易读。
    - 英文提示词 (Prompt) 部分必须使用代码块包裹，方便一键复制。

    ---

    # Execution (执行逻辑)

    当用户输入内容后，请先判断其意图属于【文字生方案】还是【视频逆向拆解】，然后套用以下对应模板进行输出：

    ## 模板 A：【文字生方案】输出结构
    ### 🎬 视频整体策划方案
    - **核心卖点/主题：**
    - **受众情绪锚点：**
    - **预计时长：**

    ### 🎞️ 核心分镜与 AI 提示词 (A-Roll)
    | 镜头编号 | 画面内容 (中文描述) | 运镜方式 | AI 视频生成 Prompt (英文, 直接可复制) |
    | :--- | :--- | :--- | :--- |
    | 01 | [描述] | [如：推镜头] | `[English Prompt]` |

    ### 🧩 补充素材库 (B-Roll & Audio)
    - **视觉空镜头 (B-Roll)：** [列出3-5个需要的特写或空镜头]
    - **音效库 (SFX)：** [列出关键动作对应的音效，如“转场嗖嗖声”]
    - **BGM 建议：** [节奏与风格描述]
    - **旁白口播 (VO)：** [精简有网感的文案]

    ## 模板 B：【视频逆向拆解】输出结构
    ### 🔍 爆款基因分析
    - **黄金前三秒策略：**
    - **视觉与色彩拆解：**
    - **听觉与节奏拆解：**

    ### ⏱️ 逐秒镜头复刻表
    | 时间轴 | 画面拆解 | 听觉拆解 (BGM/音效/文案) | 复刻该画面的 AI Prompt (英文) |
    | :--- | :--- | :--- | :--- |
    | 00:00-00:03 | [画面细节] | [声音细节] | `[English Prompt]` |

    ---
    **请确认你已理解上述设定。如果理解，请回复：“引擎已就绪。请告诉我：您今天是想输入一个【视频点子】让我生成方案，还是提供一个【爆款视频】让我进行拆解？”**
    """
).strip()


class TextToAssetsRequest(BaseModel):
    idea: str = Field(min_length=1, description="一句话创意或方案")
    title: str | None = Field(default=None, description="任务标题")
    provider: str | None = Field(default=None, description="AI provider")


class TextToAssetsConfigPayload(BaseModel):
    prompt: str = Field(default=DEFAULT_TEXT_TO_ASSETS_PROMPT, min_length=1, description="主提示词")


def _normalize_prompt_text(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else DEFAULT_TEXT_TO_ASSETS_PROMPT


def _write_prompt_file(prompt: str) -> None:
    normalized = _normalize_prompt_text(prompt).rstrip() + "\n"
    TEXT_TO_ASSETS_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    current = TEXT_TO_ASSETS_PROMPT_FILE.read_text(encoding="utf-8") if TEXT_TO_ASSETS_PROMPT_FILE.exists() else None
    if current != normalized:
        TEXT_TO_ASSETS_PROMPT_FILE.write_text(normalized, encoding="utf-8")


def _read_prompt_file() -> str:
    if not TEXT_TO_ASSETS_PROMPT_FILE.exists():
        return ""
    return TEXT_TO_ASSETS_PROMPT_FILE.read_text(encoding="utf-8").strip()


def _load_master_prompt() -> str:
    env = read_env_map()
    env_prompt = env.get(TEXT_TO_ASSETS_PROMPT_ENV_KEY, "").strip()
    if env_prompt:
        normalized = _normalize_prompt_text(env_prompt)
        _write_prompt_file(normalized)
        return normalized

    file_prompt = _read_prompt_file()
    if file_prompt:
        write_env_values({TEXT_TO_ASSETS_PROMPT_ENV_KEY: file_prompt})
        return file_prompt

    default_prompt = _normalize_prompt_text(DEFAULT_TEXT_TO_ASSETS_PROMPT)
    _write_prompt_file(default_prompt)
    write_env_values({TEXT_TO_ASSETS_PROMPT_ENV_KEY: default_prompt})
    return default_prompt


def _save_master_prompt(prompt: str) -> str:
    normalized = _normalize_prompt_text(prompt)
    _write_prompt_file(normalized)
    write_env_values({TEXT_TO_ASSETS_PROMPT_ENV_KEY: normalized})
    return normalized


def _default_title(idea: str) -> str:
    text = (idea or "").strip()
    return text[:24] if text else "一句话转素材"


def _call_text(provider: str, prompt: str) -> str:
    return VideoScriptGenerator()._call_model(provider, prompt).strip()


def _call_json(provider: str, prompt: str) -> dict[str, Any]:
    generator = VideoScriptGenerator()
    raw_text = generator._call_model(provider, prompt)
    return generator._parse_json(raw_text)


def _string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _string_list(value: Any, fallback: list[str] | None = None) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        if items:
            return items
    return list(fallback or [])


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _trim_text(value: Any, default: str = "", limit: int = 240) -> str:
    text = _string(value, default)
    return text[:limit] if text else default


def _contains_meta_voiceover_language(text: str) -> bool:
    lowered = (text or "").strip()
    if not lowered:
        return True
    blocked = [
        "接下来",
        "最后",
        "让观众",
        "观众才会",
        "第一眼先让人看见",
        "这个镜头",
        "这一镜",
        "下面我们",
        "我们先",
        "本片",
        "这条视频",
        "让人记住",
        "先给大家看",
        "这里我们",
    ]
    return any(token in lowered for token in blocked)


def _fallback_voiceover_line(idea: str, shot: dict[str, Any], index: int) -> str:
    goal = _string(shot.get("shot_goal"))
    action = _string(shot.get("subject_action"))
    title = _string(shot.get("title"), f"镜头 {index}")
    for candidate in [action, goal]:
        if candidate:
            candidate = candidate.replace("让观众", "").replace("第一时间", "").strip("，。； ")
            if candidate:
                return f"{idea}的关键，就在这一刻：{candidate}。"
    return f"{idea}不是空喊卖点，{title}这一段要把效果直接打到观众眼前。"


def _repair_voiceover_line(idea: str, shot: dict[str, Any], line: str, index: int) -> str:
    if line and not _contains_meta_voiceover_language(line):
        return line
    return _fallback_voiceover_line(idea, shot, index)


def _draft_markdown_prompt(idea: str) -> str:
    master_prompt = _load_master_prompt()
    return textwrap.dedent(
        f"""
        {master_prompt}

        ## System Override (仅供当前后端任务使用)
        - 当前输入已经确定属于【文字生方案 (Text-to-Assets)】流程。
        - 不要输出“引擎已就绪”或任何确认话术。
        - 直接开始产出第一版方案草稿。
        - 必须严格使用 Markdown。
        - 这是一版导演提案草稿，不要偷懒，不要空泛。
        - 必须包含：视频整体策划方案、A-Roll、B-Roll、音频素材清单、旁白台词、执行备注。
        - A-Roll 至少 4 条，B-Roll 至少 5 条，旁白至少 4 条。
        - 画面描述和执行说明用中文，给视频模型的 Prompt 用英文。
        - 输出要像真正能继续深化的提案草稿，而不是一句话概述。

        用户输入的一句话方案：
        {idea}
        """
    ).strip()


def _json_stage_prompt(instruction: str, schema: dict[str, Any], context: dict[str, Any]) -> str:
    master_prompt = _load_master_prompt()
    return textwrap.dedent(
        f"""
        {master_prompt}

        ## System Override (仅供当前后端任务使用)
        - 当前输入已经确定属于【文字生方案 (Text-to-Assets)】流程。
        - 你现在不是直接对用户说话，而是在为系统补全结构化字段。
        - 你必须严格参考草稿与上下文，不要脱离草稿另起炉灶。
        - 不要输出“引擎已就绪”或任何确认话术。
        - 不要输出 Markdown、表格、解释、代码块或多余文字。
        - 你必须只返回合法 JSON。
        - 除了直接给视频模型使用的 prompt 字段必须是英文，其余字段统一使用简体中文。
        - 输出必须比草稿更具体、更可执行、更适合直接投入生产。

        当前阶段任务：
        {instruction}

        输出 JSON 结构必须严格符合：
        {json.dumps(schema, ensure_ascii=False, indent=2)}

        可用上下文：
        {json.dumps(context, ensure_ascii=False, indent=2)}
        """
    ).strip()


def _mock_draft_markdown(idea: str) -> str:
    return textwrap.dedent(
        f"""
        ### 🎬 视频整体策划方案
        - **核心卖点/主题：** 用肉眼可见的变化证明“{idea}”不是概念，而是能直接被感知的结果。
        - **受众情绪锚点：** 惊讶、信任、想马上验证。
        - **预计时长：** 18-25 秒。

        ### 🎞️ 核心分镜与 AI 提示词 (A-Roll)
        | 镜头编号 | 画面内容 (中文描述) | 运镜方式 | AI 视频生成 Prompt (英文, 直接可复制) |
        | :--- | :--- | :--- | :--- |
        | A1 | 开场先给最强效果瞬间，第一秒就让观众知道变化发生了。 | 微距推进 | `cinematic macro close-up of the key product effect appearing instantly, dramatic reveal, clean premium commercial lighting, ultra-detailed, shallow depth of field, vertical 9:16` |
        | A2 | 用操作动作展示功能如何被触发，动作要直接、利落、可理解。 | 跟拍横移 | `medium close-up of hands triggering the product function in a realistic commercial setup, precise motion, premium reflections, cinematic realism, vertical 9:16` |
        | A3 | 给出最能打动人的中段证明镜头，让变化持续发生。 | 稳定推镜 | `high-end product demo shot showing the effect continuing in real time, clean environment, controlled lighting, visible transformation, cinematic product film, vertical 9:16` |
        | A4 | 结尾用强对比收束，把结果钉死。 | 固定镜头轻推近 | `powerful before-and-after result shot, clean background, trustworthy commercial realism, crisp details, final proof moment, vertical 9:16` |

        ### 🧩 补充素材库 (B-Roll & Audio)
        - **视觉空镜头 (B-Roll)：** 使用前原始状态；操作细节特写；材料表面微距；结果完成后的停顿镜头；环境氛围空镜。
        - **音效库 (SFX)：** 开场吸附式冲击音；操作触发音；液体/材质接触音；转场 whoosh；结尾收束音。
        - **BGM 建议：** 节奏明快、质感克制的商业电子科技风，前半段稳，后半段抬升。
        - **旁白口播 (VO)：** 第一眼就看到差别；不是噱头，是效果自己站出来；动作一做，变化立刻发生；真正能打动人的，是结果清清楚楚。

        ### 📝 执行备注
        - 开场不要解释，先把结果砸出来。
        - 每个镜头都要围绕“可见变化”服务。
        - 结果镜头至少停留 1 秒，保证观众读图。
        """
    ).strip()


def _mock_result(idea: str) -> dict[str, Any]:
    master_prompt = _load_master_prompt()
    draft_markdown = _mock_draft_markdown(idea)
    creative_direction = {
        "positioning": "商业演示型短视频，用视觉证据代替空泛讲解。",
        "audience": "对产品真实效果敏感、愿意被直观对比打动的短视频用户。",
        "tone": "利落、可信、克制、有高级商业广告感。",
        "visual_style": "写实高质感产品短片，强调材质、微距细节、实时变化和结果对比。",
        "rhythm": "前 3 秒直接出钩子，中段连续给证据，结尾用结果停顿收束。",
        "hook": "开场先给最强效果瞬间，用信息差把用户留住。",
        "conversion_goal": "让观众快速理解卖点，并产生进一步了解或下单冲动。",
        "core_theme": f"围绕“{idea}”用可见变化建立信任。",
        "emotion_anchor": "惊讶之后迅速转为信任与想尝试。",
        "estimated_duration": "18-25 秒",
    }
    a_roll_prompts = [
        {
            "id": "A1",
            "title": "效果钩子开场",
            "prompt": "cinematic macro close-up of the hero product effect appearing instantly on screen, premium commercial lighting, hyper-detailed surface texture, dramatic reveal, shallow depth of field, polished realism, vertical 9:16",
            "shot_goal": "第一秒就建立信息差，让观众看到效果已经发生。",
            "camera": "微距推进，前半秒锁定主体，后半秒贴近结果区域。",
            "composition": "主体位于画面中央偏前景，背景极简且虚化。",
            "lighting": "主光干净，边缘高光拉出材质层次，局部反光可控。",
            "subject_action": "效果在镜头内直接出现，不要用口头解释代替画面。",
            "transition": "冷开场硬切入，直接进入结果瞬间。",
            "duration_seconds": 3,
            "art_direction_notes": "第一秒只做一件事：让效果自己说话。",
        },
        {
            "id": "A2",
            "title": "动作触发镜头",
            "prompt": "premium product demonstration shot of hands triggering the feature in a clean commercial environment, precise motion, realistic reflections, elegant camera tracking, cinematic realism, vertical 9:16",
            "shot_goal": "让观众清楚看到动作与效果之间的因果关系。",
            "camera": "平滑横移配合轻跟拍，动作触发瞬间略微停顿。",
            "composition": "手部动作和功能区域同时入画，避免信息断裂。",
            "lighting": "均匀主光配合局部强化光，重点照亮触发区域。",
            "subject_action": "手部操作要完整连贯，不能只拍结果不拍过程。",
            "transition": "由开场效果镜头顺势切到触发动作。",
            "duration_seconds": 4,
            "art_direction_notes": "动作要干净，不能拖泥带水，确保一眼看懂。",
        },
        {
            "id": "A3",
            "title": "实时变化证明",
            "prompt": "high-end cinematic product demo showing the transformation continuing in real time, premium realistic textures, controlled highlights, elegant commercial framing, high clarity, vertical 9:16",
            "shot_goal": "把卖点从一句话变成连续可见的动态证据。",
            "camera": "稳定推镜，保持观众注意力集中在变化本身。",
            "composition": "让变化区域占据视觉中心，周围环境保持简洁。",
            "lighting": "明亮但不刺眼，强调表面变化和层次分离。",
            "subject_action": "变化必须完整发生在镜头内，不能靠剪辑跳过关键阶段。",
            "transition": "从触发动作直接进入效果持续呈现。",
            "duration_seconds": 5,
            "art_direction_notes": "这一段是说服核心，必须让人信。",
        },
        {
            "id": "A4",
            "title": "结果收束对比",
            "prompt": "powerful before-and-after comparison shot in a luxury commercial style, trustworthy realism, clean product staging, crisp details, final proof moment, vertical 9:16",
            "shot_goal": "用清晰结果把整条视频的说服力封口。",
            "camera": "固定镜头轻推近，给结果充足读图时间。",
            "composition": "前后对比关系必须明确，避免观众理解成本。",
            "lighting": "整体均匀明亮，结果区域可读性最高。",
            "subject_action": "结果出现后保持短暂停留，让观众确认差异。",
            "transition": "用停顿和对比收尾，不做花哨切换。",
            "duration_seconds": 4,
            "art_direction_notes": "结尾别急着收，至少留一拍给结果落地。",
        },
    ]
    b_roll_list = [
        {
            "title": "使用前原始状态",
            "purpose": "建立前后对比基线。",
            "description": "拍摄未经处理前的原始状态，强调问题真实存在。",
            "insert_timing": "开场后或主结果镜头前穿插。",
            "capture_notes": "不要美化问题面，保留真实感。",
            "prompt": "realistic close-up of the untreated original surface before the product is applied, honest imperfections, clean commercial framing, vertical 9:16",
        },
        {
            "title": "操作细节微距",
            "purpose": "补足主镜头没讲透的动作细节。",
            "description": "微距拍摄接触、覆盖、触发等关键细节。",
            "insert_timing": "A2 前后穿插。",
            "capture_notes": "手部动作要稳定，避免晃动影响质感。",
            "prompt": "macro shot of the exact contact and activation detail, tactile surface texture, premium product film lighting, vertical 9:16",
        },
        {
            "title": "材质反光特写",
            "purpose": "增加高级感与可信度。",
            "description": "通过反光、纹理、表面水珠或材质过渡强化视觉说服力。",
            "insert_timing": "A1 与 A3 之间。",
            "capture_notes": "控制高光，不要把细节打爆。",
            "prompt": "premium macro texture shot with controlled reflections and tactile surface detail, luxury commercial look, vertical 9:16",
        },
        {
            "title": "结果完成停顿镜头",
            "purpose": "给观众确认结果的缓冲时间。",
            "description": "结果完成后静置 1 秒以上，确保可读性。",
            "insert_timing": "A4 后半段。",
            "capture_notes": "机位稳，画面不要再做多余动作。",
            "prompt": "clean final hold shot showing the completed result clearly, premium realism, no distractions, vertical 9:16",
        },
        {
            "title": "空间氛围空镜",
            "purpose": "补充成片的商业氛围和转场缓冲。",
            "description": "拍摄相关场景、桌面、器材或环境光影，服务整片气质。",
            "insert_timing": "段落切换或 BGM 抬升节点。",
            "capture_notes": "色温统一，避免跳脱。",
            "prompt": "minimal premium commercial environment shot with elegant light and shadow, clean modern atmosphere, vertical 9:16",
        },
    ]
    voiceover = [
        {
            "id": "V1",
            "for_shot": "A1",
            "line": f"{idea}，第一眼就该看到差别。",
            "tone": "直接、干净、带一点压迫感",
            "delivery_notes": "第一句压低语速，最后两个字收重音。",
        },
        {
            "id": "V2",
            "for_shot": "A2",
            "line": "动作一做，效果不是等出来，是立刻站出来。",
            "tone": "利落、确定、带节奏",
            "delivery_notes": "和触发动作同步卡点。",
        },
        {
            "id": "V3",
            "for_shot": "A3",
            "line": "你不用猜它有没有用，变化会自己往外冒。",
            "tone": "自信、可信、推进式",
            "delivery_notes": "中间停顿半拍，突出“变化”。",
        },
        {
            "id": "V4",
            "for_shot": "A4",
            "line": "真正能让人信服的，从来不是说辞，是结果。",
            "tone": "收束、确认、结论感",
            "delivery_notes": "结尾略停顿，把结果让给画面。",
        },
    ]
    notes = [
        {"title": "开场原则", "detail": "开场先扔结果，不做背景说明。"},
        {"title": "镜头关系", "detail": "每个主镜头都要承担不同说服职责，避免重复。"},
        {"title": "材质表现", "detail": "微距和高光必须服务于真实质感，不能假。"},
        {"title": "旁白节奏", "detail": "旁白要像广告口播，不要像导演讲解。"},
        {"title": "结果停留", "detail": "最终结果至少停留 1 秒，保证读图。"},
        {"title": "成片控制", "detail": "整体节奏控制在 18-25 秒，确保信息密度高但不拥挤。"},
    ]
    audio_plan = {
        "sfx": [
            {"name": "开场冲击音", "usage": "强化第一秒钩子", "timing": "A1 开场 0-1 秒"},
            {"name": "触发反馈音", "usage": "配合动作产生明确反馈", "timing": "A2 动作触发瞬间"},
            {"name": "细节材质音", "usage": "增强接触和变化的真实感", "timing": "A2-A3 细节段"},
            {"name": "转场 whoosh", "usage": "连接段落并提升节奏", "timing": "A1/A2/A3 切换处"},
            {"name": "收束落点音", "usage": "帮助结尾形成结论感", "timing": "A4 结果锁定时"},
        ],
        "bgm_style": {
            "genre": "商业电子轻科技",
            "mood": "冷静、克制、逐步抬升",
            "tempo": "中快节奏，前稳后扬",
            "instruments": ["电子脉冲", "轻打击", "质感合成器", "短促低频点缀"],
            "mix_notes": "BGM 始终让位给旁白和动作音，结尾轻抬情绪但不喧宾夺主。",
        },
        "voiceover": voiceover,
    }
    result = {
        "summary": f"围绕“{idea}”先用效果钩子抓人，再用操作与实时变化做证据，最后用结果对比完成说服闭环。",
        "master_prompt": master_prompt,
        "draft_markdown": draft_markdown,
        "draft_outline": {
            "summary": f"围绕“{idea}”做一条以可见变化为核心的商业短视频草稿。",
            "core_theme": f"{idea}的卖点必须通过画面而不是讲解被看见。",
            "emotion_anchor": "惊讶转信任",
            "estimated_duration": "18-25 秒",
            "creative_direction_hints": creative_direction,
        },
        "creative_direction": creative_direction,
        "a_roll_prompts": a_roll_prompts,
        "b_roll_list": b_roll_list,
        "audio_plan": audio_plan,
        "notes": notes,
    }
    result["final_markdown"] = _render_final_markdown(result)
    result["raw_model_json"] = {
        "draft_markdown": draft_markdown,
        "stages": {
            "draft_outline": result["draft_outline"],
            "creative_direction": creative_direction,
            "a_roll": a_roll_prompts,
            "b_roll": b_roll_list,
            "audio_plan": audio_plan,
            "notes": notes,
        },
    }
    return result


def _generate_draft_markdown(provider: str, idea: str) -> str:
    return _call_text(provider, _draft_markdown_prompt(idea))


def _extract_draft_outline(provider: str, idea: str, draft_markdown: str) -> dict[str, Any]:
    schema = {
        "summary": "一句话概括当前草稿要表达的内容",
        "core_theme": "核心主题",
        "emotion_anchor": "受众情绪锚点",
        "estimated_duration": "预计时长，如 15-20 秒",
        "creative_direction_hints": {
            "positioning": "内容定位",
            "audience": "目标观众",
            "tone": "整体气质",
            "visual_style": "视觉风格",
            "rhythm": "节奏方向",
            "hook": "开头钩子",
            "conversion_goal": "转化目标",
        },
        "a_roll_briefs": [
            {
                "id": "A1",
                "title": "草稿镜头标题",
                "shot_goal": "草稿里这个镜头承担什么任务",
                "draft_visual": "草稿里的画面重点",
                "draft_camera": "草稿里的运镜重点",
                "draft_prompt": "草稿里的英文 Prompt 或其核心意思",
            }
        ],
        "b_roll_briefs": [
            {
                "title": "草稿补充镜头标题",
                "purpose": "存在意义",
                "description": "草稿里的画面内容",
            }
        ],
        "audio_briefs": {
            "sfx": ["草稿中的音效"],
            "bgm_direction": "草稿中的 BGM 方向",
            "voiceover": [
                {
                    "id": "V1",
                    "for_shot": "A1",
                    "line": "草稿中的旁白原句或提炼版本",
                }
            ],
        },
        "notes": ["草稿中的执行备注"],
    }
    prompt = _json_stage_prompt(
        "请先把第一版 Markdown 草稿提炼成结构化提纲，后续所有补全都必须以这个提纲和草稿为基准。",
        schema,
        {"idea": idea, "draft_markdown": draft_markdown},
    )
    data = _call_json(provider, prompt)
    return {
        "summary": _string(data.get("summary")),
        "core_theme": _string(data.get("core_theme")),
        "emotion_anchor": _string(data.get("emotion_anchor")),
        "estimated_duration": _string(data.get("estimated_duration")),
        "creative_direction_hints": {
            "positioning": _string(_safe_dict(data.get("creative_direction_hints")).get("positioning")),
            "audience": _string(_safe_dict(data.get("creative_direction_hints")).get("audience")),
            "tone": _string(_safe_dict(data.get("creative_direction_hints")).get("tone")),
            "visual_style": _string(_safe_dict(data.get("creative_direction_hints")).get("visual_style")),
            "rhythm": _string(_safe_dict(data.get("creative_direction_hints")).get("rhythm")),
            "hook": _string(_safe_dict(data.get("creative_direction_hints")).get("hook")),
            "conversion_goal": _string(_safe_dict(data.get("creative_direction_hints")).get("conversion_goal")),
        },
        "a_roll_briefs": data.get("a_roll_briefs") if isinstance(data.get("a_roll_briefs"), list) else [],
        "b_roll_briefs": data.get("b_roll_briefs") if isinstance(data.get("b_roll_briefs"), list) else [],
        "audio_briefs": _safe_dict(data.get("audio_briefs")),
        "notes": _string_list(data.get("notes")),
        "raw": data,
    }


def _expand_creative_direction(provider: str, idea: str, draft_markdown: str, draft_outline: dict[str, Any]) -> dict[str, Any]:
    schema = {
        "summary": "一句话概括整支视频的最终执行方向",
        "creative_direction": {
            "positioning": "内容定位",
            "audience": "目标观众",
            "tone": "整体气质",
            "visual_style": "视觉风格",
            "rhythm": "节奏设计",
            "hook": "开头钩子",
            "conversion_goal": "转化目标",
            "core_theme": "核心主题",
            "emotion_anchor": "受众情绪锚点",
            "estimated_duration": "预计时长",
        },
    }
    prompt = _json_stage_prompt(
        "请基于草稿和提纲，单独把创意执行方向补全到能指导整支片子的程度。不要只复述草稿，要补出明确的定位、情绪、节奏和转化目标。",
        schema,
        {"idea": idea, "draft_markdown": draft_markdown, "draft_outline": draft_outline},
    )
    data = _call_json(provider, prompt)
    creative_direction = _safe_dict(data.get("creative_direction"))
    return {
        "summary": _string(data.get("summary")),
        "creative_direction": {
            "positioning": _string(creative_direction.get("positioning")),
            "audience": _string(creative_direction.get("audience")),
            "tone": _string(creative_direction.get("tone")),
            "visual_style": _string(creative_direction.get("visual_style")),
            "rhythm": _string(creative_direction.get("rhythm")),
            "hook": _string(creative_direction.get("hook")),
            "conversion_goal": _string(creative_direction.get("conversion_goal")),
            "core_theme": _string(creative_direction.get("core_theme"), _string(draft_outline.get("core_theme"))),
            "emotion_anchor": _string(creative_direction.get("emotion_anchor"), _string(draft_outline.get("emotion_anchor"))),
            "estimated_duration": _string(creative_direction.get("estimated_duration"), _string(draft_outline.get("estimated_duration"))),
        },
        "raw": data,
    }


def _generate_a_roll_seed(
    provider: str,
    idea: str,
    draft_markdown: str,
    draft_outline: dict[str, Any],
    creative_direction: dict[str, Any],
) -> list[dict[str, Any]]:
    schema = {
        "a_roll_prompts": [
            {
                "id": "A1",
                "title": "镜头标题",
                "shot_goal": "这一镜头在整支片里的作用",
                "camera": "运镜方式",
                "composition": "构图方向",
                "lighting": "光线方向",
                "subject_action": "主体动作",
                "transition": "转场方式",
                "duration_seconds": 3,
                "prompt_seed": "英文 Prompt 的核心方向",
            }
        ]
    }
    prompt = _json_stage_prompt(
        "请先输出 A-Roll 主镜头的递归草案。至少 4 条。每条先给出镜头职责、运镜和英文 Prompt 核心方向，后续会逐条再次深化。",
        schema,
        {
            "idea": idea,
            "draft_markdown": draft_markdown,
            "draft_outline": draft_outline,
            "creative_direction": creative_direction,
        },
    )
    data = _call_json(provider, prompt)
    items = data.get("a_roll_prompts") if isinstance(data.get("a_roll_prompts"), list) else []
    normalized = []
    for index, item in enumerate(items, start=1):
        source = _safe_dict(item)
        normalized.append(
            {
                "id": _string(source.get("id"), f"A{index}"),
                "title": _string(source.get("title"), f"主镜头 {index}"),
                "shot_goal": _string(source.get("shot_goal")),
                "camera": _string(source.get("camera")),
                "composition": _string(source.get("composition")),
                "lighting": _string(source.get("lighting")),
                "subject_action": _string(source.get("subject_action")),
                "transition": _string(source.get("transition")),
                "duration_seconds": _float(source.get("duration_seconds"), 3),
                "prompt_seed": _string(source.get("prompt_seed")),
            }
        )
    return normalized


def _expand_single_a_roll(
    provider: str,
    idea: str,
    draft_markdown: str,
    draft_outline: dict[str, Any],
    creative_direction: dict[str, Any],
    all_a_roll_seeds: list[dict[str, Any]],
    current_a_roll: dict[str, Any],
) -> dict[str, Any]:
    schema = {
        "detail": {
            "title": "镜头标题",
            "prompt": "完整英文视频生成 Prompt",
            "shot_goal": "镜头承担的叙事职责",
            "camera": "运镜方式",
            "composition": "构图设计",
            "lighting": "光线设计",
            "subject_action": "主体动作",
            "transition": "转场方式",
            "duration_seconds": 3,
            "art_direction_notes": "执行提醒",
        }
    }
    prompt = _json_stage_prompt(
        "现在只补全这一条 A-Roll 主镜头。请把它扩写成真正可以直接给视频模型和执行同事使用的完整镜头说明。英文 Prompt 必须具体，包含主体、动作、环境、镜头语言、光线、质感和画幅。",
        schema,
        {
            "idea": idea,
            "draft_markdown": draft_markdown,
            "draft_outline": draft_outline,
            "creative_direction": creative_direction,
            "all_a_roll_seeds": all_a_roll_seeds,
            "current_a_roll": current_a_roll,
        },
    )
    data = _call_json(provider, prompt)
    detail = _safe_dict(data.get("detail"))
    return {
        "id": _string(current_a_roll.get("id")),
        "title": _string(detail.get("title"), _string(current_a_roll.get("title"))),
        "prompt": _string(detail.get("prompt"), _string(current_a_roll.get("prompt_seed"))),
        "shot_goal": _string(detail.get("shot_goal"), _string(current_a_roll.get("shot_goal"))),
        "camera": _string(detail.get("camera"), _string(current_a_roll.get("camera"))),
        "composition": _string(detail.get("composition"), _string(current_a_roll.get("composition"))),
        "lighting": _string(detail.get("lighting"), _string(current_a_roll.get("lighting"))),
        "subject_action": _string(detail.get("subject_action"), _string(current_a_roll.get("subject_action"))),
        "transition": _string(detail.get("transition"), _string(current_a_roll.get("transition"))),
        "duration_seconds": _float(detail.get("duration_seconds"), _float(current_a_roll.get("duration_seconds"), 3)),
        "art_direction_notes": _string(detail.get("art_direction_notes")),
        "raw": data,
    }


def _generate_b_roll_seed(
    provider: str,
    idea: str,
    draft_markdown: str,
    draft_outline: dict[str, Any],
    creative_direction: dict[str, Any],
    a_roll_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    schema = {
        "b_roll_list": [
            {
                "title": "补充镜头标题",
                "purpose": "这个镜头存在的意义",
                "description": "画面内容",
                "insert_timing": "插入位置",
                "prompt_seed": "英文 Prompt 的核心方向",
            }
        ]
    }
    prompt = _json_stage_prompt(
        "请基于草稿和已确定的 A-Roll，先输出 B-Roll / 空镜头的递归草案。至少 5 条，每条要说明用途，并给出后续可扩写的 Prompt 核心方向。",
        schema,
        {
            "idea": idea,
            "draft_markdown": draft_markdown,
            "draft_outline": draft_outline,
            "creative_direction": creative_direction,
            "a_roll_prompts": a_roll_items,
        },
    )
    data = _call_json(provider, prompt)
    items = data.get("b_roll_list") if isinstance(data.get("b_roll_list"), list) else []
    normalized = []
    for index, item in enumerate(items, start=1):
        source = _safe_dict(item)
        normalized.append(
            {
                "title": _string(source.get("title"), f"B-Roll {index}"),
                "purpose": _string(source.get("purpose")),
                "description": _string(source.get("description")),
                "insert_timing": _string(source.get("insert_timing")),
                "prompt_seed": _string(source.get("prompt_seed")),
            }
        )
    return normalized


def _expand_single_b_roll(
    provider: str,
    idea: str,
    draft_markdown: str,
    draft_outline: dict[str, Any],
    creative_direction: dict[str, Any],
    a_roll_items: list[dict[str, Any]],
    current_b_roll: dict[str, Any],
) -> dict[str, Any]:
    schema = {
        "detail": {
            "title": "补充镜头标题",
            "purpose": "存在意义",
            "description": "要拍什么",
            "insert_timing": "插入位置",
            "capture_notes": "拍摄提醒",
            "prompt": "完整英文 Prompt",
        }
    }
    prompt = _json_stage_prompt(
        "现在只补全这一条 B-Roll / 空镜头。请把它写成能直接拍摄或直接喂给模型生成的完整补充素材说明。",
        schema,
        {
            "idea": idea,
            "draft_markdown": draft_markdown,
            "draft_outline": draft_outline,
            "creative_direction": creative_direction,
            "a_roll_prompts": a_roll_items,
            "current_b_roll": current_b_roll,
        },
    )
    data = _call_json(provider, prompt)
    detail = _safe_dict(data.get("detail"))
    return {
        "title": _string(detail.get("title"), _string(current_b_roll.get("title"))),
        "purpose": _string(detail.get("purpose"), _string(current_b_roll.get("purpose"))),
        "description": _string(detail.get("description"), _string(current_b_roll.get("description"))),
        "insert_timing": _string(detail.get("insert_timing"), _string(current_b_roll.get("insert_timing"))),
        "capture_notes": _string(detail.get("capture_notes")),
        "prompt": _string(detail.get("prompt"), _string(current_b_roll.get("prompt_seed"))),
        "raw": data,
    }


def _generate_audio_strategy(
    provider: str,
    idea: str,
    draft_markdown: str,
    draft_outline: dict[str, Any],
    creative_direction: dict[str, Any],
    a_roll_items: list[dict[str, Any]],
    b_roll_items: list[dict[str, Any]],
) -> dict[str, Any]:
    schema = {
        "audio_plan": {
            "sfx": [
                {
                    "name": "音效名称",
                    "usage": "使用方式",
                    "timing": "出现位置",
                }
            ],
            "bgm_style": {
                "genre": "风格类型",
                "mood": "情绪方向",
                "tempo": "节奏速度",
                "instruments": ["乐器或声音元素 1"],
                "mix_notes": "混音建议",
            },
            "voiceover_strategy": "这支片子的旁白整体策略",
        }
    }
    prompt = _json_stage_prompt(
        "请先补全整支片子的音频策略，但这一轮先不要细化逐句旁白。重点给出完整 SFX 清单、BGM 风格和旁白整体策略，让后续逐句旁白有统一方向。",
        schema,
        {
            "idea": idea,
            "draft_markdown": draft_markdown,
            "draft_outline": draft_outline,
            "creative_direction": creative_direction,
            "a_roll_prompts": a_roll_items,
            "b_roll_list": b_roll_items,
        },
    )
    data = _call_json(provider, prompt)
    audio_plan = _safe_dict(data.get("audio_plan"))
    bgm_style = _safe_dict(audio_plan.get("bgm_style"))
    sfx = audio_plan.get("sfx") if isinstance(audio_plan.get("sfx"), list) else []
    return {
        "sfx": [
            {
                "name": _string(_safe_dict(item).get("name"), f"SFX {index}"),
                "usage": _string(_safe_dict(item).get("usage")),
                "timing": _string(_safe_dict(item).get("timing")),
            }
            for index, item in enumerate(sfx, start=1)
        ],
        "bgm_style": {
            "genre": _string(bgm_style.get("genre")),
            "mood": _string(bgm_style.get("mood")),
            "tempo": _string(bgm_style.get("tempo")),
            "instruments": _string_list(bgm_style.get("instruments")),
            "mix_notes": _string(bgm_style.get("mix_notes")),
        },
        "voiceover_strategy": _string(audio_plan.get("voiceover_strategy")),
        "raw": data,
    }


def _generate_voiceover_seed(
    provider: str,
    idea: str,
    draft_markdown: str,
    draft_outline: dict[str, Any],
    creative_direction: dict[str, Any],
    a_roll_items: list[dict[str, Any]],
    audio_strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    schema = {
        "voiceover": [
            {
                "id": "V1",
                "for_shot": "A1",
                "line": "旁白草稿",
                "tone": "语气方向",
                "delivery_notes": "朗读方向",
            }
        ]
    }
    prompt = _json_stage_prompt(
        "请先给每个 A-Roll 主镜头配一条旁白草稿。旁白必须像真正会念出来的广告口播，不要写导演说明，不要讲结构，不要讲“接下来”。",
        schema,
        {
            "idea": idea,
            "draft_markdown": draft_markdown,
            "draft_outline": draft_outline,
            "creative_direction": creative_direction,
            "a_roll_prompts": a_roll_items,
            "audio_strategy": audio_strategy,
        },
    )
    data = _call_json(provider, prompt)
    items = data.get("voiceover") if isinstance(data.get("voiceover"), list) else []
    normalized = []
    for index, item in enumerate(items, start=1):
        source = _safe_dict(item)
        normalized.append(
            {
                "id": _string(source.get("id"), f"V{index}"),
                "for_shot": _string(source.get("for_shot"), f"A{index}"),
                "line": _string(source.get("line")),
                "tone": _string(source.get("tone")),
                "delivery_notes": _string(source.get("delivery_notes")),
            }
        )
    return normalized


def _expand_single_voiceover(
    provider: str,
    idea: str,
    draft_markdown: str,
    draft_outline: dict[str, Any],
    creative_direction: dict[str, Any],
    a_roll_items: list[dict[str, Any]],
    audio_strategy: dict[str, Any],
    current_voiceover: dict[str, Any],
) -> dict[str, Any]:
    schema = {
        "detail": {
            "id": "V1",
            "for_shot": "A1",
            "line": "最终旁白文案",
            "tone": "语气",
            "delivery_notes": "朗读建议",
        }
    }
    prompt = _json_stage_prompt(
        "现在只补全这一条旁白。请把它写成有网感、有画面感、会真实出现在成片里的广告口播。禁止元叙事，禁止讲解镜头结构，必须紧贴当前镜头动作、卖点或结果变化。",
        schema,
        {
            "idea": idea,
            "draft_markdown": draft_markdown,
            "draft_outline": draft_outline,
            "creative_direction": creative_direction,
            "a_roll_prompts": a_roll_items,
            "audio_strategy": audio_strategy,
            "current_voiceover": current_voiceover,
        },
    )
    data = _call_json(provider, prompt)
    detail = _safe_dict(data.get("detail"))
    shot_id = _string(detail.get("for_shot"), _string(current_voiceover.get("for_shot")))
    matched_shot = next((item for item in a_roll_items if _string(item.get("id")) == shot_id), {})
    line = _string(detail.get("line"), _string(current_voiceover.get("line")))
    return {
        "id": _string(detail.get("id"), _string(current_voiceover.get("id"))),
        "for_shot": shot_id,
        "line": _repair_voiceover_line(idea, matched_shot, line, len(a_roll_items)),
        "tone": _string(detail.get("tone"), _string(current_voiceover.get("tone"))),
        "delivery_notes": _string(detail.get("delivery_notes"), _string(current_voiceover.get("delivery_notes"))),
        "raw": data,
    }


def _generate_notes(
    provider: str,
    idea: str,
    draft_markdown: str,
    draft_outline: dict[str, Any],
    creative_direction: dict[str, Any],
    a_roll_items: list[dict[str, Any]],
    b_roll_items: list[dict[str, Any]],
    audio_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    schema = {
        "notes": [
            {
                "title": "备注标题",
                "detail": "执行提醒",
            }
        ]
    }
    prompt = _json_stage_prompt(
        "请基于完整上下文输出至少 6 条执行备注。每条都要是真正能指导落地的提醒，分别覆盖镜头、节奏、声音、真实性、结果展示和成片控制。",
        schema,
        {
            "idea": idea,
            "draft_markdown": draft_markdown,
            "draft_outline": draft_outline,
            "creative_direction": creative_direction,
            "a_roll_prompts": a_roll_items,
            "b_roll_list": b_roll_items,
            "audio_plan": audio_plan,
        },
    )
    data = _call_json(provider, prompt)
    items = data.get("notes") if isinstance(data.get("notes"), list) else []
    normalized = []
    for index, item in enumerate(items, start=1):
        source = _safe_dict(item)
        normalized.append(
            {
                "title": _string(source.get("title"), f"备注 {index}"),
                "detail": _string(source.get("detail")),
            }
        )
    return normalized


def _generate_final_summary(
    provider: str,
    idea: str,
    draft_markdown: str,
    creative_direction: dict[str, Any],
    a_roll_items: list[dict[str, Any]],
    b_roll_items: list[dict[str, Any]],
    audio_plan: dict[str, Any],
    notes: list[dict[str, Any]],
) -> str:
    schema = {
        "summary": "1-2 句最终摘要，概括整支视频的执行思路和说服逻辑"
    }
    prompt = _json_stage_prompt(
        "请最后写一个简洁但完整的最终摘要，用于概括这份素材方案的核心执行逻辑。",
        schema,
        {
            "idea": idea,
            "draft_markdown": draft_markdown,
            "creative_direction": creative_direction,
            "a_roll_prompts": a_roll_items,
            "b_roll_list": b_roll_items,
            "audio_plan": audio_plan,
            "notes": notes,
        },
    )
    data = _call_json(provider, prompt)
    return _string(data.get("summary"))


def _render_final_markdown(result: dict[str, Any]) -> str:
    creative_direction = _safe_dict(result.get("creative_direction"))
    a_roll_items = result.get("a_roll_prompts") if isinstance(result.get("a_roll_prompts"), list) else []
    b_roll_items = result.get("b_roll_list") if isinstance(result.get("b_roll_list"), list) else []
    audio_plan = _safe_dict(result.get("audio_plan"))
    sfx_items = audio_plan.get("sfx") if isinstance(audio_plan.get("sfx"), list) else []
    voiceover_items = audio_plan.get("voiceover") if isinstance(audio_plan.get("voiceover"), list) else []
    bgm_style = _safe_dict(audio_plan.get("bgm_style"))
    notes = result.get("notes") if isinstance(result.get("notes"), list) else []

    lines = [
        "### 🎬 视频整体策划方案",
        f"- **核心卖点/主题：** {_string(creative_direction.get('core_theme')) or _string(result.get('summary'))}",
        f"- **受众情绪锚点：** {_string(creative_direction.get('emotion_anchor')) or _string(creative_direction.get('tone'))}",
        f"- **预计时长：** {_string(creative_direction.get('estimated_duration')) or '未指定'}",
        "",
        "### 🎯 创意执行方向",
        f"- **内容定位：** {_string(creative_direction.get('positioning'))}",
        f"- **目标观众：** {_string(creative_direction.get('audience'))}",
        f"- **整体气质：** {_string(creative_direction.get('tone'))}",
        f"- **画面风格：** {_string(creative_direction.get('visual_style'))}",
        f"- **节奏设计：** {_string(creative_direction.get('rhythm'))}",
        f"- **开头钩子：** {_string(creative_direction.get('hook'))}",
        f"- **转化目标：** {_string(creative_direction.get('conversion_goal'))}",
        "",
        "### 🎞️ 核心分镜与 AI 提示词 (A-Roll)",
        "| 镜头编号 | 画面内容 (中文描述) | 运镜方式 | AI 视频生成 Prompt (英文, 直接可复制) |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for item in a_roll_items:
        lines.append(
            f"| {_string(item.get('id'))} | {_trim_text(item.get('shot_goal'), '暂无内容', 72)} | {_trim_text(item.get('camera'), '暂无内容', 32)} | `{_trim_text(item.get('prompt'), '暂无内容', 220)}` |"
        )

    lines.extend(["", "### 🧩 补充素材库 (B-Roll & Audio)"])

    for item in b_roll_items:
        lines.append(f"- **视觉空镜头 (B-Roll)：** {_string(item.get('title'))}：{_string(item.get('description'))}")
        if _string(item.get("purpose")):
            lines.append(f"  用途：{_string(item.get('purpose'))}")
        if _string(item.get("insert_timing")):
            lines.append(f"  插入位置：{_string(item.get('insert_timing'))}")

    sfx_line = []
    for item in sfx_items:
        source = _safe_dict(item)
        sfx_line.append(" / ".join(part for part in [_string(source.get("name")), _string(source.get("usage")), _string(source.get("timing"))] if part))

    lines.append(f"- **音效库 (SFX)：** {'；'.join(part for part in sfx_line if part) or '暂无内容'}")

    bgm_parts = [
        _string(bgm_style.get("genre")),
        _string(bgm_style.get("mood")),
        _string(bgm_style.get("tempo")),
        " / ".join(_string_list(bgm_style.get("instruments"))),
        _string(bgm_style.get("mix_notes")),
    ]
    lines.append(f"- **BGM 建议：** {'；'.join(part for part in bgm_parts if part) or '暂无内容'}")

    voiceover_lines = [_string(_safe_dict(item).get("line")) for item in voiceover_items if _string(_safe_dict(item).get("line"))]
    lines.append(f"- **旁白口播 (VO)：** {'；'.join(voiceover_lines) or '暂无内容'}")

    if notes:
        lines.extend(["", "### 📝 执行备注"])
        for item in notes:
            source = _safe_dict(item)
            lines.append(f"- **{_string(source.get('title'), '备注')}：** {_string(source.get('detail'))}")

    return "\n".join(lines).strip()


def _build_partial_result(
    idea: str,
    *,
    summary: str = "",
    master_prompt: str = "",
    draft_markdown: str = "",
    draft_outline: dict[str, Any] | None = None,
    creative_direction: dict[str, Any] | None = None,
    a_roll_prompts: list[dict[str, Any]] | None = None,
    b_roll_list: list[dict[str, Any]] | None = None,
    audio_plan: dict[str, Any] | None = None,
    notes: list[dict[str, Any]] | None = None,
    raw_model_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = _mock_result(idea)
    result = {
        "summary": summary or base["summary"],
        "master_prompt": master_prompt or _load_master_prompt(),
        "draft_markdown": draft_markdown,
        "draft_outline": draft_outline or {},
        "creative_direction": creative_direction or base["creative_direction"],
        "a_roll_prompts": a_roll_prompts or [],
        "b_roll_list": b_roll_list or [],
        "audio_plan": audio_plan or {"sfx": [], "bgm_style": {}, "voiceover": []},
        "notes": notes or [],
        "raw_model_json": raw_model_json or {},
    }
    result["final_markdown"] = _render_final_markdown(result)
    return result


def _generate_assets(idea: str, provider: str) -> dict[str, Any]:
    if provider == "mock":
        return _mock_result(idea)

    master_prompt = _load_master_prompt()
    draft_markdown = _generate_draft_markdown(provider, idea)
    draft_outline = _extract_draft_outline(provider, idea, draft_markdown)
    creative_direction_block = _expand_creative_direction(provider, idea, draft_markdown, draft_outline)
    creative_direction = creative_direction_block["creative_direction"]

    a_roll_seed = _generate_a_roll_seed(provider, idea, draft_markdown, draft_outline, creative_direction)
    a_roll_items: list[dict[str, Any]] = []
    a_roll_raw: list[dict[str, Any]] = []
    for item in a_roll_seed:
        detail = _expand_single_a_roll(
            provider,
            idea,
            draft_markdown,
            draft_outline,
            creative_direction,
            a_roll_seed,
            item,
        )
        a_roll_items.append({key: value for key, value in detail.items() if key != "raw"})
        a_roll_raw.append(detail.get("raw", {}))

    b_roll_seed = _generate_b_roll_seed(provider, idea, draft_markdown, draft_outline, creative_direction, a_roll_items)
    b_roll_items: list[dict[str, Any]] = []
    b_roll_raw: list[dict[str, Any]] = []
    for item in b_roll_seed:
        detail = _expand_single_b_roll(
            provider,
            idea,
            draft_markdown,
            draft_outline,
            creative_direction,
            a_roll_items,
            item,
        )
        b_roll_items.append({key: value for key, value in detail.items() if key != "raw"})
        b_roll_raw.append(detail.get("raw", {}))

    audio_strategy = _generate_audio_strategy(provider, idea, draft_markdown, draft_outline, creative_direction, a_roll_items, b_roll_items)
    voiceover_seed = _generate_voiceover_seed(provider, idea, draft_markdown, draft_outline, creative_direction, a_roll_items, audio_strategy)
    voiceover_items: list[dict[str, Any]] = []
    voiceover_raw: list[dict[str, Any]] = []
    for index, item in enumerate(voiceover_seed, start=1):
        detail = _expand_single_voiceover(
            provider,
            idea,
            draft_markdown,
            draft_outline,
            creative_direction,
            a_roll_items,
            audio_strategy,
            item,
        )
        matched_shot = next((shot for shot in a_roll_items if _string(shot.get("id")) == _string(detail.get("for_shot"))), {})
        voiceover_items.append(
            {
                "id": _string(detail.get("id"), f"V{index}"),
                "for_shot": _string(detail.get("for_shot"), f"A{index}"),
                "line": _repair_voiceover_line(idea, matched_shot, _string(detail.get("line")), index),
                "tone": _string(detail.get("tone")),
                "delivery_notes": _string(detail.get("delivery_notes")),
            }
        )
        voiceover_raw.append(detail.get("raw", {}))

    audio_plan = {
        "sfx": audio_strategy["sfx"],
        "bgm_style": audio_strategy["bgm_style"],
        "voiceover": voiceover_items,
    }
    notes = _generate_notes(provider, idea, draft_markdown, draft_outline, creative_direction, a_roll_items, b_roll_items, audio_plan)
    summary = _generate_final_summary(provider, idea, draft_markdown, creative_direction, a_roll_items, b_roll_items, audio_plan, notes)

    result = {
        "summary": summary,
        "master_prompt": master_prompt,
        "draft_markdown": draft_markdown,
        "draft_outline": {
            key: value for key, value in draft_outline.items() if key != "raw"
        },
        "creative_direction": creative_direction,
        "a_roll_prompts": a_roll_items,
        "b_roll_list": b_roll_items,
        "audio_plan": audio_plan,
        "notes": notes,
        "raw_model_json": {
            "draft_markdown": draft_markdown,
            "stages": {
                "draft_outline": draft_outline.get("raw", draft_outline),
                "creative_direction": creative_direction_block.get("raw", creative_direction_block),
                "a_roll_seed": a_roll_seed,
                "a_roll_details": a_roll_raw,
                "b_roll_seed": b_roll_seed,
                "b_roll_details": b_roll_raw,
                "audio_strategy": audio_strategy.get("raw", audio_strategy),
                "voiceover_seed": voiceover_seed,
                "voiceover_details": voiceover_raw,
                "notes": notes,
                "final_summary": summary,
            },
        },
    }
    result["final_markdown"] = _render_final_markdown(result)
    return result


def run_text_to_assets_task(task_id: str, payload: TextToAssetsRequest) -> None:
    provider = payload.provider or active_ai_provider("mock")
    master_prompt = _load_master_prompt()
    try:
        update_task(task_id, status="running", progress=4, message="正在读取主提示词并准备草稿生成", provider=provider)
        if provider == "mock":
            result = _mock_result(payload.idea)
            update_task(task_id, status="running", progress=88, message="正在整理 mock 递归素材方案", provider=provider, result_json=result)
            update_task(task_id, status="done", progress=100, message="素材清单生成完成", provider=provider, result_json=result, error=None)
            return

        update_task(task_id, status="running", progress=10, message="正在用主提示词生成第一版草稿", provider=provider)
        draft_markdown = _generate_draft_markdown(provider, payload.idea)
        partial = _build_partial_result(
            payload.idea,
            master_prompt=master_prompt,
            draft_markdown=draft_markdown,
            raw_model_json={"draft_markdown": draft_markdown},
        )
        update_task(task_id, status="running", progress=18, message="正在从草稿提炼递归提纲", provider=provider, result_json=partial)

        draft_outline = _extract_draft_outline(provider, payload.idea, draft_markdown)
        partial = _build_partial_result(
            payload.idea,
            master_prompt=master_prompt,
            draft_markdown=draft_markdown,
            draft_outline={key: value for key, value in draft_outline.items() if key != "raw"},
            raw_model_json={
                "draft_markdown": draft_markdown,
                "stages": {"draft_outline": draft_outline.get("raw", draft_outline)},
            },
        )
        update_task(task_id, status="running", progress=26, message="正在递归补全创意执行方向", provider=provider, result_json=partial)

        creative_direction_block = _expand_creative_direction(provider, payload.idea, draft_markdown, draft_outline)
        creative_direction = creative_direction_block["creative_direction"]
        partial = _build_partial_result(
            payload.idea,
            summary=creative_direction_block["summary"],
            master_prompt=master_prompt,
            draft_markdown=draft_markdown,
            draft_outline={key: value for key, value in draft_outline.items() if key != "raw"},
            creative_direction=creative_direction,
            raw_model_json={
                "draft_markdown": draft_markdown,
                "stages": {
                    "draft_outline": draft_outline.get("raw", draft_outline),
                    "creative_direction": creative_direction_block.get("raw", creative_direction_block),
                },
            },
        )
        update_task(task_id, status="running", progress=34, message="正在生成 A-Roll 递归草案", provider=provider, result_json=partial)

        a_roll_seed = _generate_a_roll_seed(provider, payload.idea, draft_markdown, draft_outline, creative_direction)
        partial["raw_model_json"] = {
            "draft_markdown": draft_markdown,
            "stages": {
                "draft_outline": draft_outline.get("raw", draft_outline),
                "creative_direction": creative_direction_block.get("raw", creative_direction_block),
                "a_roll_seed": a_roll_seed,
            },
        }
        update_task(task_id, status="running", progress=40, message="正在逐条递归补全 A-Roll 主镜头", provider=provider, result_json=partial)

        a_roll_items: list[dict[str, Any]] = []
        a_roll_raw: list[dict[str, Any]] = []
        total_a_roll = max(1, len(a_roll_seed))
        for index, item in enumerate(a_roll_seed, start=1):
            detail = _expand_single_a_roll(
                provider,
                payload.idea,
                draft_markdown,
                draft_outline,
                creative_direction,
                a_roll_seed,
                item,
            )
            a_roll_items.append({key: value for key, value in detail.items() if key != "raw"})
            a_roll_raw.append(detail.get("raw", {}))
            progress = 40 + int(index / total_a_roll * 18)
            partial = _build_partial_result(
                payload.idea,
                summary=creative_direction_block["summary"],
                master_prompt=master_prompt,
                draft_markdown=draft_markdown,
                draft_outline={key: value for key, value in draft_outline.items() if key != "raw"},
                creative_direction=creative_direction,
                a_roll_prompts=a_roll_items,
                raw_model_json={
                    "draft_markdown": draft_markdown,
                    "stages": {
                        "draft_outline": draft_outline.get("raw", draft_outline),
                        "creative_direction": creative_direction_block.get("raw", creative_direction_block),
                        "a_roll_seed": a_roll_seed,
                        "a_roll_details": a_roll_raw,
                    },
                },
            )
            update_task(task_id, status="running", progress=progress, message=f"正在补全第 {index} 条 A-Roll 镜头", provider=provider, result_json=partial)

        update_task(task_id, status="running", progress=60, message="正在生成 B-Roll 递归草案", provider=provider, result_json=partial)
        b_roll_seed = _generate_b_roll_seed(provider, payload.idea, draft_markdown, draft_outline, creative_direction, a_roll_items)

        b_roll_items: list[dict[str, Any]] = []
        b_roll_raw: list[dict[str, Any]] = []
        total_b_roll = max(1, len(b_roll_seed))
        for index, item in enumerate(b_roll_seed, start=1):
            detail = _expand_single_b_roll(
                provider,
                payload.idea,
                draft_markdown,
                draft_outline,
                creative_direction,
                a_roll_items,
                item,
            )
            b_roll_items.append({key: value for key, value in detail.items() if key != "raw"})
            b_roll_raw.append(detail.get("raw", {}))
            progress = 60 + int(index / total_b_roll * 14)
            partial = _build_partial_result(
                payload.idea,
                summary=creative_direction_block["summary"],
                master_prompt=master_prompt,
                draft_markdown=draft_markdown,
                draft_outline={key: value for key, value in draft_outline.items() if key != "raw"},
                creative_direction=creative_direction,
                a_roll_prompts=a_roll_items,
                b_roll_list=b_roll_items,
                raw_model_json={
                    "draft_markdown": draft_markdown,
                    "stages": {
                        "draft_outline": draft_outline.get("raw", draft_outline),
                        "creative_direction": creative_direction_block.get("raw", creative_direction_block),
                        "a_roll_seed": a_roll_seed,
                        "a_roll_details": a_roll_raw,
                        "b_roll_seed": b_roll_seed,
                        "b_roll_details": b_roll_raw,
                    },
                },
            )
            update_task(task_id, status="running", progress=progress, message=f"正在补全第 {index} 条 B-Roll 镜头", provider=provider, result_json=partial)

        update_task(task_id, status="running", progress=76, message="正在递归补全音频策略", provider=provider, result_json=partial)
        audio_strategy = _generate_audio_strategy(provider, payload.idea, draft_markdown, draft_outline, creative_direction, a_roll_items, b_roll_items)

        update_task(task_id, status="running", progress=82, message="正在生成旁白递归草案", provider=provider, result_json=partial)
        voiceover_seed = _generate_voiceover_seed(provider, payload.idea, draft_markdown, draft_outline, creative_direction, a_roll_items, audio_strategy)

        voiceover_items: list[dict[str, Any]] = []
        voiceover_raw: list[dict[str, Any]] = []
        total_voiceover = max(1, len(voiceover_seed))
        for index, item in enumerate(voiceover_seed, start=1):
            detail = _expand_single_voiceover(
                provider,
                payload.idea,
                draft_markdown,
                draft_outline,
                creative_direction,
                a_roll_items,
                audio_strategy,
                item,
            )
            matched_shot = next((shot for shot in a_roll_items if _string(shot.get("id")) == _string(detail.get("for_shot"))), {})
            voiceover_items.append(
                {
                    "id": _string(detail.get("id"), f"V{index}"),
                    "for_shot": _string(detail.get("for_shot"), f"A{index}"),
                    "line": _repair_voiceover_line(payload.idea, matched_shot, _string(detail.get("line")), index),
                    "tone": _string(detail.get("tone")),
                    "delivery_notes": _string(detail.get("delivery_notes")),
                }
            )
            voiceover_raw.append(detail.get("raw", {}))
            audio_plan = {
                "sfx": audio_strategy["sfx"],
                "bgm_style": audio_strategy["bgm_style"],
                "voiceover": voiceover_items,
            }
            progress = 82 + int(index / total_voiceover * 10)
            partial = _build_partial_result(
                payload.idea,
                summary=creative_direction_block["summary"],
                master_prompt=master_prompt,
                draft_markdown=draft_markdown,
                draft_outline={key: value for key, value in draft_outline.items() if key != "raw"},
                creative_direction=creative_direction,
                a_roll_prompts=a_roll_items,
                b_roll_list=b_roll_items,
                audio_plan=audio_plan,
                raw_model_json={
                    "draft_markdown": draft_markdown,
                    "stages": {
                        "draft_outline": draft_outline.get("raw", draft_outline),
                        "creative_direction": creative_direction_block.get("raw", creative_direction_block),
                        "a_roll_seed": a_roll_seed,
                        "a_roll_details": a_roll_raw,
                        "b_roll_seed": b_roll_seed,
                        "b_roll_details": b_roll_raw,
                        "audio_strategy": audio_strategy.get("raw", audio_strategy),
                        "voiceover_seed": voiceover_seed,
                        "voiceover_details": voiceover_raw,
                    },
                },
            )
            update_task(task_id, status="running", progress=progress, message=f"正在补全第 {index} 条旁白", provider=provider, result_json=partial)

        audio_plan = {
            "sfx": audio_strategy["sfx"],
            "bgm_style": audio_strategy["bgm_style"],
            "voiceover": voiceover_items,
        }
        update_task(task_id, status="running", progress=94, message="正在补全执行备注", provider=provider, result_json=partial)
        notes = _generate_notes(provider, payload.idea, draft_markdown, draft_outline, creative_direction, a_roll_items, b_roll_items, audio_plan)

        update_task(task_id, status="running", progress=97, message="正在汇总最终素材方案", provider=provider, result_json=partial)
        summary = _generate_final_summary(provider, payload.idea, draft_markdown, creative_direction, a_roll_items, b_roll_items, audio_plan, notes)

        result = {
            "summary": summary,
            "master_prompt": master_prompt,
            "draft_markdown": draft_markdown,
            "draft_outline": {key: value for key, value in draft_outline.items() if key != "raw"},
            "creative_direction": creative_direction,
            "a_roll_prompts": a_roll_items,
            "b_roll_list": b_roll_items,
            "audio_plan": audio_plan,
            "notes": notes,
            "raw_model_json": {
                "draft_markdown": draft_markdown,
                "stages": {
                    "draft_outline": draft_outline.get("raw", draft_outline),
                    "creative_direction": creative_direction_block.get("raw", creative_direction_block),
                    "a_roll_seed": a_roll_seed,
                    "a_roll_details": a_roll_raw,
                    "b_roll_seed": b_roll_seed,
                    "b_roll_details": b_roll_raw,
                    "audio_strategy": audio_strategy.get("raw", audio_strategy),
                    "voiceover_seed": voiceover_seed,
                    "voiceover_details": voiceover_raw,
                    "notes": notes,
                    "final_summary": summary,
                },
            },
        }
        result["final_markdown"] = _render_final_markdown(result)
        update_task(task_id, status="done", progress=100, message="素材清单生成完成", provider=provider, result_json=result, error=None)
    except Exception as exc:
        traceback.print_exc()
        update_task(
            task_id,
            status="failed",
            progress=100,
            message="素材清单生成失败",
            provider=provider,
            error=f"{type(exc).__name__}: {exc}",
        )


@router.get("/config")
def get_config() -> dict[str, Any]:
    prompt = _load_master_prompt()
    return {
        "prompt": prompt,
        "prompt_file": str(TEXT_TO_ASSETS_PROMPT_FILE),
        "prompt_source": "env" if read_env_map().get(TEXT_TO_ASSETS_PROMPT_ENV_KEY, "").strip() else ("file" if _read_prompt_file() else "default"),
    }


@router.post("/config")
def save_config(payload: TextToAssetsConfigPayload) -> dict[str, Any]:
    try:
        _save_master_prompt(payload.prompt)
        return {"status": "ok", "config": get_config()}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
                "hint": "Unable to save Text-to-Assets prompt config.",
            },
        ) from exc


@router.post("/jobs")
def create_text_to_assets_job(payload: TextToAssetsRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    try:
        provider = payload.provider or active_ai_provider("mock")
        task_id = f"text-to-assets-{uuid4().hex}-{int(time.time())}"
        task = create_task(
            task_id=task_id,
            task_type="text_to_assets",
            title=payload.title or _default_title(payload.idea),
            provider=provider,
            payload=payload.model_dump(),
            message="任务已创建，等待 AI 生成素材清单",
        )
        background_tasks.add_task(run_text_to_assets_task, task_id, payload)
        return task
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
                "hint": "Check AI provider config for Text-to-Assets.",
            },
        ) from exc


@router.post("/jobs/{task_id}/retry")
def retry_text_to_assets_job(task_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("type") != "text_to_assets":
        raise HTTPException(status_code=400, detail="Only Text-to-Assets tasks can be retried here")
    if task.get("status") not in {"failed", "error"}:
        raise HTTPException(status_code=409, detail="Only failed Text-to-Assets tasks can be retried")

    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    try:
        retry_payload = TextToAssetsRequest(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Retry requires the original Text-to-Assets payload: {exc}") from exc

    retried = update_task(
        task_id,
        status="pending",
        progress=0,
        message="已重新加入一句话转素材队列",
        result_json=None,
        error=None,
    )
    background_tasks.add_task(run_text_to_assets_task, task_id, retry_payload)
    return {"status": "ok", "task": retried}
