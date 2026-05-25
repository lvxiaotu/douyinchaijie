# AI 提示词反推

这个工具用于选择一个已采集视频，使用类似 BiliNote 的“转写 + 分段 + 关键帧证据”流程，把视频重建成可复刻的 AI 视频脚本和镜头提示词。

## 使用场景

- 反推出可用于文生视频、图生视频或脚本生成的提示词。
- 从爆款视频中提取镜头、风格、节奏、主体、场景、动作和商业表达。
- 复刻 AI 视频：逐镜头输出脚本、首帧、尾帧、运镜、主体动作、构图、光线、转场和负向提示词。
- 将反推结果归档，之后可以在其他生成工具中复用。

## 配置项

```env
AI_PROMPT_REVERSE_OUTPUT_DIR=./data/runtime/ai_prompt_reverse
AI_PROMPT_REVERSE_PIPELINE_MODE=evidence
AI_PROMPT_REVERSE_MAX_SEGMENTS=18
AI_PROMPT_REVERSE_PROMPT=
```

`AI_PROMPT_REVERSE_PIPELINE_MODE`：

- `evidence`：强制使用证据管线，推荐。先用 FFmpeg + Whisper 转写，再抽关键帧和网格图，最后逐段反推镜头。
- `auto`：证据管线失败时回退整段视频直传。
- `direct`：旧方式，直接把整段视频交给 Gemini。

证据管线复用 AI 视频拆解的基础配置，例如：

```env
AI_VIDEO_TRANSCRIBER=faster-whisper
AI_VIDEO_TRANSCRIBE_MODEL=base
AI_VIDEO_SEGMENT_SECONDS=90
AI_VIDEO_SILENT_SEGMENT_SECONDS=6
AI_VIDEO_KEYFRAME_INTERVAL_SECONDS=30
AI_VIDEO_RESUME_ENABLED=true
FFMPEG_BINARY=./ffmpeg-8.1.1-essentials_build/bin/ffmpeg.exe
FFPROBE_BINARY=./ffmpeg-8.1.1-essentials_build/bin/ffprobe.exe
```

反推工具和 AI 视频拆解共用同一套证据管线，所以也需要 `ffmpeg` 和 `ffprobe`。`ffmpeg` 用于抽音频和关键帧，`ffprobe` 用于读取视频时长。若 `ffprobe` 不可用，视频时长会被记录为 `0.0`；当 ASR 对纯画面、音乐、无对白视频返回空转写时，就无法触发按 `AI_VIDEO_SILENT_SEGMENT_SECONDS` 的视觉切段兜底。

模型连接复用“AI 模型”全局配置。Gemini Key 和模型示例：

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

## 输出结构

```json
{
  "summary": "反推摘要",
  "reconstruction_strategy": "复刻步骤和一致性策略",
  "master_prompt": "完整可复用提示词",
  "negative_prompt": "需要规避的内容",
  "audio_script": [
    {"time_range": "00:00-00:05", "line": "旁白/字幕/剧情脚本"}
  ],
  "shot_prompts": [
    {
      "shot": "镜头1",
      "time_range": "00:00-00:05",
      "script_line": "该镜头脚本",
      "visual_description": "画面描述",
      "first_frame": "首帧",
      "last_frame": "尾帧",
      "camera_movement": "运镜",
      "subject_motion": "主体动作",
      "composition": "景别构图",
      "lighting_color": "光线色彩",
      "transition": "转场",
      "prompt": "镜头提示词",
      "negative_prompt": "镜头负向提示词",
      "reference_frames": ["00:00", "00:03"]
    }
  ],
  "style_keywords": ["风格关键词"],
  "usage_notes": ["使用建议"]
}
```
