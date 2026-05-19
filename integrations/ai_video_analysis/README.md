# AI 视频拆解

这个工具用于接收已经采集到的视频条目，创建后台拆解任务，并把 AI 输出沉淀为结构化结果。

## 设计目标

- 从抖音采集结果中选择单个视频，点击“拆解”。
- 后端创建任务，记录视频来源、标题、作者、统计数据、原始 JSON。
- 后续 provider 层可接入 Gemini、OpenAI GPT、多模态开源模型或本地推理服务。
- 输出统一结构，前端不关心具体模型供应商。

## 预留配置

```env
AI_VIDEO_PROVIDER=mock
AI_VIDEO_OUTPUT_DIR=./data/runtime/ai_video_analysis
AI_VIDEO_PIPELINE_MODE=auto
AI_VIDEO_TRANSCRIBER=auto
AI_VIDEO_TRANSCRIBE_MODEL=small
AI_VIDEO_TRANSCRIBE_LANGUAGE=zh
AI_VIDEO_SEGMENT_SECONDS=90
AI_VIDEO_SILENT_SEGMENT_SECONDS=6
AI_VIDEO_KEYFRAME_INTERVAL_SECONDS=30
AI_VIDEO_MAX_SEGMENTS=18
AI_VIDEO_MAX_CONCURRENT_TASKS=1
AI_VIDEO_RESUME_ENABLED=true
AI_VIDEO_HIGHLIGHT_SCREENSHOTS=true
AI_VIDEO_GRID_COLUMNS=3
AI_VIDEO_GRID_MAX_FRAMES=9
AI_VIDEO_GRID_CELL_WIDTH=320
AI_VIDEO_GRID_CELL_HEIGHT=180
FFMPEG_BINARY=ffmpeg
FFPROBE_BINARY=ffprobe
GEMINI_API_KEY=
OPENAI_API_KEY=
LOCAL_VIDEO_MODEL_ENDPOINT=
```

## 长视频证据包流程

默认 `AI_VIDEO_PIPELINE_MODE=auto` 会优先走证据包流程：

1. 定位本地视频，或从 `source_video_url` 下载视频。
2. 使用 FFmpeg 提取 16k 单声道 wav 音频。
3. 使用 `faster-whisper` 或 `openai-whisper` 转写为带时间戳的 `transcript_segments`。
4. 按 `AI_VIDEO_SEGMENT_SECONDS` 切成多个分析片段；如果没有识别到语音，则按 `AI_VIDEO_SILENT_SEGMENT_SECONDS` 秒数进行视觉切段。
5. 按片段抽关键帧，并生成带时间戳的关键帧网格图。
6. 每个片段携带转写文本和网格图先做一次小拆解，再汇总成全局爆款公式。

`AI_VIDEO_PIPELINE_MODE` 可选值：

- `auto`：优先证据包流程；缺少 FFmpeg/Whisper 时回退旧的直接视频上传分析。
- `evidence`：强制证据包流程；转写失败时任务失败，适合长视频稳定拆解。
- `direct`：跳过转写，使用旧的 Gemini 视频上传分析。

`AI_VIDEO_MAX_CONCURRENT_TASKS` 默认是 `1`。普通 CPU 机器建议保持单任务；调高后多个 Whisper/FFmpeg 任务会并行运行，CPU、内存和磁盘 IO 压力会明显增加。

`AI_VIDEO_HIGHLIGHT_SCREENSHOTS=true` 时，每段 AI 拆解会输出 `highlight_screenshots` 时间点，后端会自动从原视频截取对应爆点画面并写回分段结果。

证据包会保存到：

```text
data/runtime/ai_video_analysis/evidence/{task_id}/analysis_evidence.json
```

如果 `AI_VIDEO_RESUME_ENABLED=true`，任务重跑时会逐步复用已完成的中间产物，而不是整包复用证据包。当前断点包括：`audio.wav`、`transcript.json`、`keyframes.json`、关键帧网格图、每段 AI 拆解 JSON、`global_breakdown.json`。

## 统一输出结构

```json
{
  "summary": "一句话概括视频的爆款套路和可复用价值",
  "content_identity": {
    "track": "内容赛道",
    "niche_fit": "跨赛道迁移判断",
    "account_persona": "账号人设或叙事视角"
  },
  "core_hook": {
    "opening_3s": "开头3秒钩子",
    "curiosity_gap": "信息差或悬念",
    "emotional_trigger": "情绪触发",
    "comment_bait": "评论诱因"
  },
  "need_context": {
    "pain_point": "用户痛点",
    "application_scene": "应用场景",
    "hidden_desire": "隐性欲望"
  },
  "product_power": {
    "core_benefit": "利益点提炼",
    "trigger_moment": "转化瞬间",
    "trust_builder": "信任来源",
    "product_role": "产品角色"
  },
  "visual_structure": {
    "shot_structure": "镜头流转逻辑",
    "reusable_elements": "可复刻元素",
    "timeline_beats": ["00:00-00:03：钩子"],
    "audio_rhythm": "声音与字幕节奏"
  },
  "copywriting_formula": {
    "title_formula": "标题公式",
    "script_formula": "脚本公式",
    "golden_lines": ["可复用金句"],
    "cta": "行动号召"
  },
  "market_positioning": {
    "suitable_products": "适合产品",
    "target_audience": "目标人群",
    "creative_direction": "后续创作方向"
  },
  "replication_plan": {
    "pattern_name": "公式名",
    "reusable_formula": "可复刻公式",
    "cross_genre_variants": "跨赛道改写方向",
    "mysticism_variant": "玄学改编",
    "ai_pet_variant": "AI小动物改编",
    "ai_commerce_variant": "AI带货改编",
    "difficulty": "制作难度",
    "priority": "模仿优先级"
  },
  "standard_remake_template": "脱敏后的通用复刻脚本模板",
  "risk_control": {
    "risk_level": "低/中/高",
    "platform_risks": ["AIGC标识、版权、虚假宣传、迷信承诺等风险"],
    "safe_rewrite": "更稳妥的表达方式"
  },
  "viral_scores": {
    "viral_potential": 0,
    "imitation_value": 0,
    "commerce_value": 0,
    "comment_potential": 0,
    "overall": 0
  }
}
```

## 接入步骤

1. 先用 `mock` provider 跑通任务创建、结果保存和前端展示。
2. Gemini provider 已接入：
   - 配置 `AI_VIDEO_PROVIDER=gemini`
   - 配置 `GEMINI_API_KEY`
   - 可选配置 `GEMINI_MODEL=gemini-2.5-flash`
3. Gemini 会优先复用本地视频文件；没有本地文件时，从采集结果里的视频地址下载到 `data/runtime/ai_video_analysis/media/`，再上传到 Gemini Files API。
4. 如果后续接 OpenAI 或本地模型，在 `adapter.py` 中新增 provider 分支。
5. 每次大的字段变动，需要同步更新这里的输出结构说明。
