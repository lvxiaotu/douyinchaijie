# AI 短视频生产流水线实施方案

## 目标

本方案只实现三个工具，并且严格按顺序执行：

1. 灵感剧本
2. 素材整理
3. 草稿生成

整体流程：

```text
灵感输入 -> 生成 script.json -> 根据剧本整理素材 -> 回填 script.json -> 调用 pyJianYingDraft 生成剪映草稿
```

`script.json` 是三个工具之间的唯一核心数据。前一个工具的输出必须成为后一个工具的输入。

## 工具一：灵感剧本

### 目标

用户输入灵感、主题、风格、分镜数量和视频比例，系统调用 AI 生成结构化 `script.json`。

工具一只负责生成剧本，不处理素材，也不生成草稿。

### 输入

```json
{
  "title": "五月星象",
  "idea": "做一个关于五月运势的短视频",
  "style": "神秘、治愈、节奏舒缓",
  "scene_count": 5,
  "resolution": "9:16"
}
```

### 输出

```json
{
  "project_id": "uuid",
  "config": {
    "title": "五月星象",
    "resolution": "9:16",
    "fps": 30
  },
  "scenes": [
    {
      "id": 1,
      "narration": "五月的星光，正在悄悄改变你的方向。",
      "visual_prompt": "night sky, stars, soft glowing light",
      "assets": {
        "video_path": "",
        "image_path": "",
        "audio_path": "",
        "duration": 0
      },
      "edit": {
        "transition": "fade",
        "animation": "zoom_in"
      },
      "status": "waiting_assets"
    }
  ]
}
```

### 后端实现

新增脚本模型和生成逻辑：

```text
integrations/video_pipeline/script_schema.py
integrations/video_pipeline/script_generator.py
backend/app/routes/video_script.py
```

建议接口：

```text
POST /api/tools/video-script/generate
GET  /api/tools/video-script/{project_id}
POST /api/tools/video-script/{project_id}/save
```

实现要求：

- 复用当前项目已有 AI Provider 配置。
- AI 返回内容必须校验为合法 `script.json`。
- 生成后保存到项目运行目录。
- 允许用户后续编辑并保存剧本。

建议保存位置：

```text
data/runtime/video_pipeline/projects/{project_id}/script.json
```

### 前端实现

页面需要提供：

- 标题输入。
- 灵感输入。
- 风格输入。
- 分镜数量。
- 视频比例。
- 生成剧本按钮。
- `script.json` 分镜展示。
- 分镜旁白、视觉提示词、转场、动画的编辑能力。

### 验收标准

- 能输入灵感。
- 能生成合法 `script.json`。
- 能保存项目。
- 刷新后能重新读取。
- 工具一不依赖素材。
- 工具一不生成草稿。

## 工具二：素材整理

### 目标

根据工具一生成的 `script.json` 展示每个分镜的素材框，扫描素材目录，并把视频、图片、音频对应到具体 scene。

工具二不是普通文件管理，而是为工具三的 `pyJianYingDraft` 草稿生成准备合法素材输入。

### 核心原则

- 根据 `script.json.scenes` 渲染素材整理界面。
- 每个 scene 都要显示素材对应状态。
- 视频和图片最终进入 `pyJianYingDraft.VideoSegment`。
- 音频最终进入 `pyJianYingDraft.AudioSegment`。
- 旁白文本来自 `scene.narration`，不作为素材文件。
- 每个 scene 至少需要一个视觉素材：`video_path` 或 `image_path`。
- 路径必须是本机真实存在的文件路径。
- 不支持的文件类型不能绑定。
- 第二步只回填 `script.json`，不生成草稿。

### 页面展示

每个 scene 展示一个素材整理框：

```text
分镜 1
旁白：五月的星光，正在悄悄改变你的方向。
视觉提示词：night sky, stars, soft glowing light

[视频/图片素材框]  未对应 / 已对应 scene_01.mp4
[音频素材框]      未对应 / 已对应 scene_01.wav
[预计时长]        6.2 秒 / 未识别
[状态]            缺少视觉素材 / 已就绪
```

每个分镜至少展示：

```text
scene id
narration
visual_prompt
视觉素材框
音频素材框
duration
status
```

### 状态定义

```text
waiting_assets    等待素材
missing_visual    缺少视频或图片
partial_ready     有视觉素材，但缺音频或时长
ready             可进入草稿生成
invalid_path      路径不存在
unsupported_type  类型不支持
```

### 支持的素材类型

视觉素材，最终进入 `VideoSegment`：

```text
.mp4
.mov
.mkv
.webm
.avi
.jpg
.jpeg
.png
.webp
```

音频素材，最终进入 `AudioSegment`：

```text
.mp3
.wav
.m4a
.aac
.flac
```

### 素材扫描输出

扫描素材目录后返回素材池：

```json
{
  "visual_assets": [
    {
      "id": "hash",
      "name": "scene_01.mp4",
      "path": "G:/assets/may-star/scene_01.mp4",
      "type": "video",
      "status": "available",
      "duration": 6.2
    }
  ],
  "audio_assets": [
    {
      "id": "hash",
      "name": "scene_01.wav",
      "path": "G:/assets/may-star/scene_01.wav",
      "type": "audio",
      "status": "available",
      "duration": 6.2
    }
  ]
}
```

### 自动匹配规则

自动匹配只做简单、可解释的规则，不做复杂语义匹配：

```text
scene_01.mp4 -> scene id 1
scene-01.wav -> scene id 1
01.png       -> scene id 1
第 1 个视频   -> scene id 1
第 1 个音频   -> scene id 1
```

无法确定时保持未对应，由用户手动选择。

### 手动指定规则

用户可以对每个 scene 执行：

```text
选择视频/图片
选择音频
清除对应
```

手动绑定请求示例：

```json
{
  "project_id": "uuid",
  "scene_id": 1,
  "slot": "visual",
  "path": "G:/assets/may-star/scene_01.mp4"
}
```

`slot` 只允许：

```text
visual
audio
```

### 更新后的 script.json

工具二完成后，`script.json` 中的 scene 应变为：

```json
{
  "id": 1,
  "narration": "五月的星光，正在悄悄改变你的方向。",
  "visual_prompt": "night sky, stars, soft glowing light",
  "assets": {
    "video_path": "G:/assets/may-star/scene_01.mp4",
    "image_path": "",
    "audio_path": "G:/assets/may-star/scene_01.wav",
    "duration": 6.2
  },
  "edit": {
    "transition": "fade",
    "animation": "zoom_in"
  },
  "status": "ready"
}
```

### 和 pyJianYingDraft 的对应关系

工具二字段必须能直接服务工具三：

```text
scene.assets.video_path
-> draft.VideoSegment(video_path, target_timerange)

scene.assets.image_path
-> draft.VideoSegment(image_path, target_timerange)

scene.assets.audio_path
-> draft.AudioSegment(audio_path, target_timerange)

scene.narration
-> draft.TextSegment(narration, target_timerange)

scene.assets.duration
-> draft.trange(start, duration)
```

### 后端实现

新增素材整理逻辑：

```text
integrations/video_pipeline/asset_sync.py
backend/app/routes/video_assets.py
```

建议接口：

```text
POST /api/tools/video-assets/scan
POST /api/tools/video-assets/auto-assign
POST /api/tools/video-assets/assign
GET  /api/tools/video-assets/{project_id}/status
```

接口职责：

```text
scan         扫描素材目录，不修改剧本
auto-assign  根据文件名和 scene 顺序自动回填
assign       用户手动把素材绑定到某个 scene
status       返回每个 scene 的素材对应状态
```

### 前端实现

页面需要提供：

- 素材目录输入。
- 扫描素材按钮。
- 自动匹配按钮。
- 每个 scene 的视觉素材框。
- 每个 scene 的音频素材框。
- 每个 scene 的 ready / missing 状态。
- 手动选择素材。
- 清除对应。

### 验收标准

- 能根据 `script.json.scenes` 展示素材框。
- 每个 scene 都能看到视觉素材是否已对应。
- 每个 scene 都能看到音频素材是否已对应。
- 每个 scene 都能看到是否可进入草稿生成。
- 能扫描素材目录。
- 能识别视频、图片、音频。
- 能自动匹配。
- 能手动改配。
- 能清除对应。
- 不支持的文件类型不能绑定。
- 路径不存在不能标记为 `ready`。
- 最终保存回 `script.json`。
- 所有 `ready` 的 scene 都能被工具三直接转换为 `pyJianYingDraft` Segment。

## 工具三：草稿生成

### 目标

读取工具二已经补全素材的 `script.json`，严格按 `pyJianYingDraft` 的项目逻辑生成剪映草稿。

工具三不负责生成剧本，也不负责整理素材。

### pyJianYingDraft 标准流程

草稿生成必须按以下顺序执行：

```text
DraftFolder
-> create_draft
-> add_track
-> VideoSegment / AudioSegment / TextSegment
-> add_segment
-> save
```

### 输入

```json
{
  "project_id": "uuid"
}
```

### 校验规则

读取：

```text
data/runtime/video_pipeline/projects/{project_id}/script.json
```

必须校验：

```text
project_id 存在
config.title 存在
config.resolution 存在
scenes 不为空
每个 scene 至少有 video_path 或 image_path
素材路径真实存在
duration 大于 0，或者能从素材推算
```

校验失败时，直接终止，不创建草稿。

### 初始化草稿

严格使用 `pyJianYingDraft`：

```python
import pyJianYingDraft as draft

draft_folder = draft.DraftFolder(jianying_draft_root)
script = draft_folder.create_draft(
    draft_name,
    width,
    height,
    fps,
    allow_replace=True,
)
```

分辨率映射：

```text
9:16 -> 1080 x 1920
16:9 -> 1920 x 1080
1:1  -> 1080 x 1080
```

`fps` 默认 30，优先读取 `script.json.config.fps`。

### 创建轨道

第一版只创建必要轨道：

```python
script.add_track(draft.TrackType.video, "main_video")
script.add_track(draft.TrackType.audio, "main_audio")
script.add_track(draft.TrackType.text, "narration_text")
```

### 时间线计算

按 scene 顺序累加时间线，不由前端随意传入：

```text
scene_1 start = 0
scene_2 start = scene_1 start + scene_1 duration
scene_3 start = scene_2 start + scene_2 duration
```

duration 来源优先级：

```text
scene.assets.duration
-> 音频时长
-> 视频时长
-> 默认 5 秒
```

### 创建视觉片段

视频和图片都进入 `VideoSegment`：

```python
target_range = draft.trange(f"{start_seconds}s", f"{duration_seconds}s")

segment = draft.VideoSegment(
    media_path,
    target_range,
)
script.add_segment(segment, "main_video")
```

如果需要截取素材指定片段，才使用 `source_timerange`：

```python
segment = draft.VideoSegment(
    media_path,
    target_range,
    source_timerange=draft.trange("0s", f"{duration_seconds}s"),
)
```

注意：

```text
draft.trange(start, duration) 的第二个参数是持续时长，不是结束时间。
```

### 创建音频片段

如果 scene 有 `audio_path`：

```python
audio_segment = draft.AudioSegment(
    audio_path,
    draft.trange(f"{start_seconds}s", f"{duration_seconds}s"),
)
script.add_segment(audio_segment, "main_audio")
```

`pyJianYingDraft 0.2.6` 的正确参数逻辑是：

```python
AudioSegment(material, target_timerange, source_timerange=None)
```

不能写成：

```python
AudioSegment(path, source_timerange, target_timerange)
```

### 创建文本片段

旁白文本来自 `scene.narration`：

```python
text_segment = draft.TextSegment(
    scene["narration"],
    draft.trange(f"{start_seconds}s", f"{duration_seconds}s"),
)
script.add_segment(text_segment, "narration_text")
```

第一版只做基础文本，不做复杂文字样式。

### 保存草稿

所有 scene 添加完成后：

```python
script.save()
```

保存后写入当前项目数据库：

```text
jianying_drafts
```

记录字段包括：

```json
{
  "project_id": "uuid",
  "draft_name": "五月星象",
  "draft_path": "G:/.../JianyingPro Drafts/五月星象",
  "status": "created",
  "scene_count": 5
}
```

### 后端实现

需要先修正当前已有剪映适配层：

```text
backend/app/main.py
integrations/jianying_draft/draft_engine.py
```

然后新增映射逻辑：

```text
integrations/video_pipeline/draft_mapper.py
backend/app/routes/video_draft.py
```

建议接口：

```text
POST /api/tools/video-draft/build
GET  /api/tools/video-draft/{project_id}/result
```

### 返回结果

```json
{
  "status": "created",
  "project_id": "uuid",
  "draft_name": "五月星象",
  "draft_path": "G:/.../JianyingPro Drafts/五月星象"
}
```

### 验收标准

- 只从工具二完成后的 `script.json` 生成草稿。
- 严格使用 `DraftFolder -> create_draft -> add_track -> add_segment -> save`。
- `VideoSegment` / `AudioSegment` 参数符合 `pyJianYingDraft 0.2.6` API。
- `trange(start, duration)` 不把 duration 当结束时间。
- 每个 scene 顺序进入时间线。
- 每个 scene 至少生成一个画面片段。
- 有旁白就生成文本轨道片段。
- 有音频就生成音频轨道片段。
- 素材缺失时不生成草稿，返回明确错误。
- 草稿生成结果写入 `jianying_drafts`。

## 严格开发顺序

必须按以下顺序开发和验收：

```text
第一步：工具一 灵感剧本
第二步：工具二 素材整理
第三步：工具三 草稿生成
```

不能跳过：

```text
没有 script.json，就没有素材回填目标。
没有素材回填，就没有可靠的草稿生成输入。
没有合法素材输入，就不能调用 pyJianYingDraft 生成稳定草稿。
```

## 最终用户操作路径

```text
输入灵感
-> 生成剧本
-> 检查/编辑分镜
-> 选择素材目录
-> 展示每个分镜的素材框
-> 整理并回填素材
-> 检查素材状态
-> 生成剪映草稿
-> 获得草稿路径
```
