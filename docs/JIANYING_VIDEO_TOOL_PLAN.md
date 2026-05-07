# 剪映与 HTML 视频工具链实施计划

这份计划用于把 `pyJianYingDraft`、`jianying-editor-skill` 的剪映草稿能力，以及 `hyperframes` 启发的 HTML 视频渲染能力，逐步接入当前个人工具工作台。

目标不是一次性做一个完整剪辑软件，而是先做一套可组合的本地视频生产工具链，让后续可以从“采集/分析视频”继续走到“生成素材/套模板/创建剪映草稿”。

## 0. 当前项目约束

当前项目形态：

- 前端：Vite + React，入口在 `src/`。
- 后端：FastAPI，入口在 `backend/app/main.py`。
- 第三方能力：统一放进 `integrations/`，通过 adapter 暴露。
- 长任务：已有 SQLite task store，路径为 `data/runtime/tasks.sqlite3`。
- 运行数据：统一进入 `data/runtime/`，不提交 Git。

因此新能力必须遵守：

- 不把第三方项目逻辑直接写进主后端。
- 每个外部能力先做 integration adapter。
- 主后端只暴露稳定 API。
- 前端只调用主后端 API。
- 素材、草稿、任务结果全部落在 `data/runtime/` 或用户配置的本地目录。

## 1. 总体设计

做两个 integration，不做一堆散脚本：

```text
integrations/
  jianying_draft/
    adapter.py
    draft_engine.py
    asset_manager.py
    template_manager.py
    decrypt_adapter.py
    media_pipeline.py
    README.md
    vendor/

  html_video_render/
    adapter.py
    composition_builder.py
    render_runner.py
    README.md
    vendor/
```

它们在产品上组成一条视频生产链：

```text
视频采集/视频分析
-> 提炼脚本/模板变量
-> HTML 动效素材生成
-> 素材入库与检查
-> 剪映草稿生成/模板替换
-> 用户打开剪映继续精修或导出
```

## 2. 工具入口设计

工作台里不要只放一个“剪映工具”。建议露出多个工具卡片，但共享同一个剪映 integration。

第一批工具入口：

```text
剪映素材库
剪映草稿工厂
剪映模板库
HTML 动效素材生成器
脚本转剪映工程
```

每个工具做的事：

- 剪映素材库：扫描、入库、检查缺失、路径重映射。
- 剪映草稿工厂：根据素材和脚本创建基础草稿。
- 剪映模板库：导入已有剪映草稿，识别可替换槽位。
- HTML 动效素材生成器：用 HTML/CSS/JS 生成标题卡、贴片、转场、数据图表等视频素材。
- 脚本转剪映工程：编排以上能力，形成端到端任务。

## 3. 集成边界

### 3.1 `jianying_draft`

底层优先使用 `pyJianYingDraft`。

职责：

- 创建剪映草稿。
- 添加视频、图片、音频、字幕、文字、贴纸。
- 读取和修改模板草稿。
- 接入用户的新版草稿解密/还原工具。该工具可能是外部 exe，且可能需要手动操作。
- 检查素材是否缺失。
- 输出草稿路径和诊断报告。

不负责：

- 复杂 HTML 动效渲染。
- AI 分析视频内容。
- 直接采集抖音数据。

### 3.2 `html_video_render`

借鉴 `hyperframes` 思路，但先做轻量实现。

职责：

- 接收一个 HTML composition。
- 使用浏览器或渲染器预览。
- 渲染成 mp4/webm/mov 等素材。
- 将渲染产物交给素材库入库。

不负责：

- 直接编辑剪映草稿。
- 扫描剪映缓存。
- 管理模板槽位。

## 4. 配置项

新增 `.env.example` 项，实际值写入 `.env`。

```text
JIANYING_DRAFT_ROOT=
JIANYING_ASSET_LIBRARY_DIR=./data/runtime/jianying/assets
JIANYING_OUTPUT_DIR=./data/runtime/jianying/drafts
JIANYING_DECRYPT_TOOL=
JIANYING_RESTORE_TOOL=
JIANYING_CACHE_DIR=
JIANYING_DECRYPT_MODE=manual

HTML_VIDEO_OUTPUT_DIR=./data/runtime/html_video_render
HTML_VIDEO_RENDERER=playwright
HTML_VIDEO_FPS=30
HTML_VIDEO_WIDTH=1080
HTML_VIDEO_HEIGHT=1920
FFMPEG_BINARY=ffmpeg
FFPROBE_BINARY=ffprobe
```

配置原则：

- `JIANYING_DECRYPT_MODE` 支持 `manual`、`exe`、`none`。
- `manual` 表示用户在外部工具里手动解密/还原，本项目只检测文件状态和给出下一步提示。
- `exe` 表示本项目尝试调用外部 exe，但仍要允许用户确认、等待和重试。
- `none` 表示只处理未加密或已解密草稿。
- 解密/还原 exe 只做调用适配，不把破解逻辑写进主项目。
- 素材库默认在 `data/runtime/jianying/assets`，但允许用户改到大盘目录。

## 5. 后端 API 计划

### 阶段 1 API

```text
GET  /api/tools/jianying/status
GET  /api/tools/jianying/config
POST /api/tools/jianying/config
POST /api/tools/jianying/assets/scan
POST /api/tools/jianying/drafts/create

GET  /api/tools/html-video/status
POST /api/tools/html-video/render
```

当前实现说明：

- `html-video/render` 第一阶段使用 `placeholder` 渲染器，先生成 `composition.html` 和 `render.json`。
- 渲染结果会以 `source=html_render`、`type=rendered` 写入 `jianying_assets`。
- 后续接入 Playwright/FFmpeg 后，只需要把 asset 的 `path` 从 HTML 文件切换为视频文件。

### 解密/还原辅助 API

新版剪映草稿如果需要外部 exe 或手动操作，使用辅助 API 管理状态：

```text
POST /api/tools/jianying/decrypt/prepare
POST /api/tools/jianying/decrypt/check
POST /api/tools/jianying/decrypt/confirm
POST /api/tools/jianying/restore/prepare
POST /api/tools/jianying/restore/check
POST /api/tools/jianying/restore/confirm
```

这些 API 不负责破解算法，只负责：

- 判断当前草稿是否需要解密。
- 生成用户需要操作的源路径、目标路径和说明。
- 在 `exe` 模式下尝试启动或调用外部 exe。
- 在 `manual` 模式下等待用户确认。
- 确认解密/还原后的文件是否存在、是否可读、是否符合预期结构。

### 阶段 2 API

```text
POST /api/tools/jianying/templates/inspect
POST /api/tools/jianying/templates/render
POST /api/tools/jianying/drafts/validate
POST /api/tools/jianying/drafts/repair-assets
GET  /api/tools/jianying/assets
GET  /api/tools/jianying/templates
```

### 阶段 3 API

```text
POST /api/tools/video-production/jobs
GET  /api/tools/video-production/jobs/{task_id}
```

这个阶段的 `video-production` 是编排层，不是新的第三方 integration。它会调用：

- AI 视频分析结果
- HTML 视频渲染
- 剪映素材库
- 剪映草稿工厂

## 6. 数据表计划

可以继续放在现有 `tasks.sqlite3`。

第一阶段先新增：

```text
jianying_assets
jianying_drafts
```

`jianying_assets` 字段：

```text
id
type              video/audio/image/effect/filter/sticker/font/music/rendered
name
source            local/jianying_cache/template/html_render/imported
path
resource_id
effect_id
duration
width
height
hash
status            available/missing/unknown/needs_download
meta_json
created_at
updated_at
```

`jianying_drafts` 字段：

```text
id
name
draft_path
source            created/template_render/imported
status            created/validated/has_missing_assets/failed
asset_report_json
meta_json
created_at
updated_at
```

第二阶段新增：

```text
jianying_templates
html_video_renders
```

`jianying_templates` 保存模板槽位：

```text
id
name
template_path
text_slots_json
media_slots_json
audio_slots_json
required_assets_json
status
created_at
updated_at
```

## 7. 素材策略

素材是这个工具链的核心，不要后置。

必须支持四类素材：

```text
用户本地素材
剪映缓存素材
模板内引用素材
HTML 渲染生成素材
```

第一阶段只做：

- 扫描本地素材目录。
- 用 ffprobe 获取 duration、width、height。
- 计算 hash，避免重复入库。
- 检查文件是否存在。
- 生成素材列表。

第二阶段再做：

- 扫描剪映缓存目录。
- 读取缓存音乐/音效元数据。
- 从模板草稿里抽取 resource_id、effect_id、素材路径。
- 检查模板需要的素材是否可用。

第三阶段做：

- 自动路径重映射。
- 缺失素材替换建议。
- 根据标签、比例、时长自动选素材。

## 8. 草稿生成策略

先不要做复杂时间线编辑器，先支持“可控模板化生成”。

第一阶段输入：

```json
{
  "name": "demo-draft",
  "aspect_ratio": "9:16",
  "media": [
    {"path": "...", "type": "video"},
    {"path": "...", "type": "image"}
  ],
  "audio": [],
  "captions": [],
  "texts": []
}
```

第一阶段输出：

```json
{
  "draft_id": "...",
  "draft_path": "...",
  "status": "created",
  "asset_report": {
    "available": [],
    "missing": []
  }
}
```

第二阶段支持：

- SRT 导入。
- 文本字幕自动分段。
- BGM 添加。
- 多轨道叠加。
- 片头/片尾素材插入。

第三阶段支持：

- 模板槽位替换。
- 批量生成多个草稿。
- 从 AI 视频分析结果生成分镜草稿。

## 8.1 新版草稿读写状态机

因为新版草稿可能需要外部 exe 手动解密或还原，所有“读取已有新版草稿”和“修改后写回新版草稿”的流程都按状态机设计。

读取模板草稿：

```text
created
-> checking_encryption
-> waiting_for_decrypt       # manual 模式停在这里
-> decrypting                # exe 模式可能进入这里
-> decrypted_ready
-> inspecting_template
-> done
```

修改并还原草稿：

```text
patch_ready
-> writing_decrypted_content
-> waiting_for_restore       # manual 模式停在这里
-> restoring                 # exe 模式可能进入这里
-> restored_ready
-> validating
-> done
```

任务结果必须包含：

```json
{
  "task_id": "...",
  "state": "waiting_for_decrypt",
  "manual_action": {
    "title": "请使用外部 exe 解密草稿",
    "source_path": "...",
    "expected_output_path": "...",
    "instructions": ["打开 exe", "选择草稿目录", "完成后点击确认"]
  }
}
```

前端策略：

- 如果任务状态是 `waiting_for_decrypt`，显示“我已完成解密”按钮。
- 如果任务状态是 `waiting_for_restore`，显示“我已完成还原”按钮。
- 如果配置了 exe 路径，可以显示“尝试启动工具”按钮。
- 用户确认后调用 `confirm` API，后端继续后续步骤。

## 9. HTML 视频渲染策略

`hyperframes` 的启发是：复杂视觉效果先做成普通视频素材，再交给剪映。

第一阶段不做完整 clone，只做一个简单渲染器：

输入：

```json
{
  "name": "title-card",
  "width": 1080,
  "height": 1920,
  "fps": 30,
  "duration": 4,
  "html": "<html>...</html>"
}
```

输出：

```json
{
  "render_id": "...",
  "video_path": "...",
  "poster_path": "...",
  "status": "done"
}
```

可生成素材类型：

- 标题卡
- 字幕卡
- 评论飞入
- 商品卖点卡
- 数据图表
- 片头/片尾
- 透明贴片

后续如果 `hyperframes` 足够稳定，可以把它作为 vendor 或 npm 子工具接入。

## 10. 阶段计划

### Phase 1：最小闭环

目标：能从素材生成一个剪映草稿，并能生成一个 HTML 动效素材。

任务：

- 新建 `integrations/jianying_draft/`。
- 新建 `integrations/html_video_render/`。
- 新建 `backend/app/routes/jianying.py`。
- 新建 `backend/app/routes/html_video.py`。
- 接入 `/status`、`/config`。
- 实现本地素材扫描。
- 实现基础剪映草稿创建。
- 实现简单 HTML 渲染任务骨架。
- 在工作台注册工具卡片。

验收：

- 后端能返回剪映工具状态。
- 能扫描一个本地素材目录。
- 能创建一个包含视频/图片的剪映草稿。
- 能生成一个标题卡 HTML composition，并将产物入库为可追踪素材。
- 任务能出现在现有任务中心。

### Phase 2：素材库与模板库

目标：能导入模板草稿、识别槽位、检查素材缺失。

任务：

- 新增素材表和草稿表。
- 新增模板表。
- 实现模板 inspect。
- 实现草稿 validate。
- 实现素材缺失报告。
- 支持解密 adapter 的手动/外部 exe 流程。
- 前端增加素材库/模板库列表。

验收：

- 能导入一个现有剪映草稿作为模板。
- 能列出文字槽位、媒体槽位、必需素材。
- 能发现缺失文件路径。
- 能保存模板记录。

### Phase 3：脚本转剪映工程

目标：从脚本和素材自动生成可打开的剪映工程。

任务：

- 定义统一 video composition JSON。
- 将 composition 输出到 HTML render。
- 将 composition 输出到 Jianying draft。
- 支持字幕、BGM、片头、标题卡。
- 支持调用已有 AI 视频分析结果生成草稿参数。

验收：

- 输入标题、脚本、素材，生成剪映草稿。
- 标题卡/贴片由 HTML 渲染生成。
- 草稿 validate 通过。
- 输出完整素材报告。

### Phase 4：批量模板生产

目标：批量套模板，服务短视频生产。

任务：

- 模板变量表单。
- 批量输入 CSV/JSON。
- 批量渲染 HTML 片段。
- 批量生成剪映草稿。
- 缺失素材自动替换建议。

验收：

- 一个模板可生成多个草稿。
- 每个草稿有独立报告。
- 失败任务可重试。

## 11. 执行选择

后续每一步对话可以从这些动作里选：

```text
A. 先搭剪映 integration 骨架
B. 先搭 HTML 视频渲染 integration 骨架
C. 先做素材库扫描和 SQLite 表
D. 先做剪映草稿创建 API
E. 先做前端工具卡片和配置页
F. 先写统一 video composition JSON 规范
G. 先接你的新版草稿解密工具
```

推荐顺序：

```text
A -> C -> D -> B -> E -> F -> G
```

如果想最快看到效果：

```text
A -> D
```

如果想先把地基打稳：

```text
A -> C -> G -> D
```

如果想先验证 hyperframes 思路：

```text
B -> E -> F
```

## 12. 风险与处理

### pyJianYingDraft 兼容性

风险：新版剪映草稿结构变化，底层库不一定完全覆盖。

处理：

- 第一阶段只生成简单草稿。
- 复杂模板替换走 JSON patch 和 decrypt adapter。
- 必要时 vendor fork `pyJianYingDraft`。

### 新版草稿解密/还原工具

风险：用户的解密方式是外部 exe，不一定能作为静默命令行工具稳定调用，也可能需要手动选择文件、点击按钮或分阶段还原。

处理：

- `decrypt_adapter.py` 不假设一定能自动解密。
- 把解密流程设计成状态机，而不是普通函数调用。
- 允许三种模式：`manual`、`exe`、`none`。
- 所有需要解密的任务先进入 `waiting_for_decrypt` 状态。
- 前端展示需要用户操作的路径、文件名、目标动作和完成确认按钮。
- 用户手动完成解密后，点击“我已完成解密”，后端再继续 inspect/patch/validate。
- 还原/重新加密同理，任务进入 `waiting_for_restore` 状态。
- 如果 exe 支持命令行参数，再由 adapter 调用；如果不支持，就只负责生成操作说明。

### 素材缺失

风险：草稿打开后素材丢失、缓存素材不可用、云素材未下载。

处理：

- 素材库前置。
- 每次创建草稿后 validate。
- 模板 inspect 时保存 required assets。
- HTML 生成的视觉素材优先使用本地文件，减少对剪映云素材依赖。

### Windows 本机依赖

风险：剪映、缓存目录、自动导出都偏 Windows。

处理：

- 核心功能只生成草稿，不强依赖自动导出。
- status/doctor 明确提示环境状态。
- 自动导出后置，不进入 MVP。

### 渲染链路复杂

风险：浏览器渲染、录屏、ffmpeg 合成容易踩坑。

处理：

- 第一阶段只支持固定尺寸、固定时长的简单 HTML。
- 优先输出普通 mp4。
- 透明通道、复杂音频混合后置。

## 13. 我后续执行时的默认原则

除非你另有指定，我会默认：

- 先做后端 adapter，再做前端入口。
- 先做本地可控素材，再考虑剪映云素材。
- 先生成草稿，不自动导出。
- 先跑通一个视频/一套素材，再做批量。
- 新版草稿默认按“需要手动解密/还原”设计，不默认静默破解。
- 所有长任务接入现有 task store。
- 所有运行产物进入 `data/runtime/`。
- 不破坏现有抖音下载、AI 视频分析、提示词反推工具。
