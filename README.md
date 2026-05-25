# Personal Ops Workbench

一个面向个人内容生产与自动化处理的工作台项目。

当前仓库把前端工作台、FastAPI 后端、第三方能力适配层，以及剪映相关 SDK 能力整合在一起，目标是把“采集素材 -> 分析视频 -> 生成脚本 -> 进入剪映生产链路”串成一套可持续演进的本地工具链。

## 数据策略

抖音链路已改成默认的“先查库，再上游”模式：

- 原始数据和规范化数据同时落库
- 用户、视频、评论、分页结果都支持关键 ID / 分页键复用
- 同一页结果命中后直接回库，不重复打上游
- `recent_update_at`、`last_post_at` 必须保留
- `play_count` 不能最终落成 0
- AI 视频拆解里的评论采集是一个独立步骤，失败不阻断拆解
- 评论失败会在任务中心保留状态，并支持再次获取

## 数据库

当前运行时只使用 PostgreSQL，不再依赖 SQLite。

### 需要配置的环境变量

```env
DATABASE_URL=
CORE_TASK_DATABASE_URL=
TASK_AUDIT_DATABASE_URL=
AI_VIDEO_QUEUE_DATABASE_URL=
TIKTOK_TARGET_DATABASE_URL=
TIKTOK_TARGET_CACHE_DATABASE_URL=
SHORT_VIDEO_ANALYSIS_DATABASE_URL=
ARCHIVE_DATABASE_URL=
MEDIA_DATABASE_URL=
POSTGRES_SCHEMA=
```

如果你不想拆多库，也可以先让这些变量都指向同一个 PostgreSQL DSN，再逐步拆分。

统一错误落盘目录：

```text
data/runtime/error/<namespace>/<YYYYMMDD>/*.json
```

当前 namespace：

- `tikhub`
- `douyin-download-api`
- `ai-provider`

## 当前能力

- 抖音采集集成
  - 用户主页信息
  - 用户作品列表
  - 单作品详情
  - 收藏视频列表与下载
  - 搜索结果、作品页、评论页缓存复用
  - 上游报错统一写入 `data/runtime/error`
- AI 视频拆解
  - 后端异步任务执行
  - 拆解结果归档
  - 基于证据管线的截图、转写、分段分析
- AI 提示词反推
  - 从视频内容反推出主提示词、负向提示词和风格关键词
  - 结果归档
- RunningHub TTS
  - 独立承载 RunningHub index-tts 工作流
  - 支持保存 API Key、Workflow 标识、Workflow ID 和轮询间隔
  - 支持引用 RunningHub 预置工作流或用户自定义 workflowId
  - 默认切到稳定情感工作流 `2053641347223044097`
  - 支持上传参考音频、查看任务进度、下载和试听生成音频
- 创作工作台 Studio
  - 选题脑暴
  - 概念锁定
  - 分镜脚本蓝图生成
- 剪映能力接入
  - 草稿检查与查看
  - SDK 深度诊断
  - 资产搜索
  - TTS、Web VFX、智能缩放、电影解说草稿、自动导出等能力入口

## 技术栈

- 前端：Vite + React
- 后端：FastAPI
- 数据存储：PostgreSQL
- 集成方式：`integrations/` 适配层
- 运行环境：Windows 优先，部分剪映能力仅支持 Windows

## 目录结构

```text
.
├─ src/                             前端工作台
├─ backend/app/                     FastAPI 后端
├─ integrations/                    第三方工具与业务适配层
│  ├─ douyin_download_api/          抖音下载服务适配器
│  ├─ douyin_legacy_tikhub/         老 TikHub 抖音接口显式别名
│  ├─ douyin_spider_provider/       新 Douyin_Spider 抖音接口与 sidecar
│  ├─ douyin_provider/              抖音接口聚合层与 fallback
│  ├─ ai_video_analysis/            AI 视频拆解
│  ├─ ai_prompt_reverse/            AI 提示词反推
│  ├─ jianying_draft/               剪映草稿生成
│  ├─ jianying_editor_skill/        剪映 SDK 桥接层
│  └─ video_pipeline/               脚本与生产链路
├─ sdks/                            上游 SDK 快照
├─ scripts/                         辅助脚本
├─ tests/                           测试
├─ data/                            运行时数据目录
├─ package.json                     前端依赖与脚本
├─ requirements-base.txt            后端与通用依赖
├─ requirements-sdk.txt             剪映 SDK 相关依赖
└─ requirements.txt                 完整本地环境依赖
```

## 快速启动

建议至少准备两个终端窗口：

1. 启动后端
2. 启动前端

如果你要使用新的 `Douyin_Spider` 抖音采集接口，还需要额外启动 `8131` sidecar。旧的 `Douyin_TikTok_Download_API` 是 `8123` 服务，只在仍使用旧下载适配层时需要。

### 1. 安装依赖

Python：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Node.js：

```powershell
npm install
```

如果你暂时不需要剪映 SDK 相关能力，也可以只安装基础依赖：

```powershell
pip install -r requirements-base.txt
```

### 2. 配置环境变量

先复制示例文件：

```powershell
Copy-Item .env.example .env
```

最常用的配置项如下：

```env
VITE_API_BASE=http://127.0.0.1:8010
DOUYIN_DOWNLOAD_API_BASE=http://127.0.0.1:8123
DOUYIN_OUTPUT_DIR=./data/runtime/douyin/downloads
DY_COOKIES=
DOUYIN_PROVIDER_MODE=tikhub
DOUYIN_SPIDER_EXECUTION_MODE=sidecar
DOUYIN_SPIDER_API_BASE=http://127.0.0.1:8131
DOUYIN_SPIDER_VENDOR_PATH=./integrations/douyin_spider_provider/vendor/Douyin_Spider
DOUYIN_PROVIDER_OBSERVABILITY_ENABLED=true

AI_MODEL_PROVIDER=gemini
AI_ACCESS_MODE=official
AI_NATIVE_API_KEY=
AI_RELAY_BASE_URL=
AI_RELAY_API_KEY=
AI_MODEL=gemini-2.5-flash

AI_VIDEO_OUTPUT_DIR=./data/runtime/ai_video_analysis
AI_PROMPT_REVERSE_OUTPUT_DIR=./data/runtime/ai_prompt_reverse

FFMPEG_BINARY=./ffmpeg-8.1.1-essentials_build/bin/ffmpeg.exe
FFPROBE_BINARY=./ffmpeg-8.1.1-essentials_build/bin/ffprobe.exe
LOCAL_VIDEO_MODEL_ENDPOINT=
```

如果要做旧 SQLite 数据迁移，可运行：

```powershell
python scripts/migrate_sqlite_to_postgres.py --dry-run
python scripts/migrate_sqlite_to_postgres.py --bootstrap --truncate --verify
```

说明：

- `.env` 不应提交到 Git。
- 新 `Douyin_Spider` 抖音采集依赖 `DY_COOKIES` 和本地 `8131` sidecar。
- 旧 `Douyin_TikTok_Download_API` 下载适配层才依赖 `DOUYIN_DOWNLOAD_API_BASE=http://127.0.0.1:8123`。
- 抖音可替换接口通过 `DOUYIN_PROVIDER_MODE=tikhub|spider_first|spider` 切换；搜索固定保留 TikHub。
- 新 `Douyin_Spider` 默认通过 sidecar 隔离运行。启动命令：`python -m uvicorn integrations.douyin_spider_provider.sidecar_server:app --host 127.0.0.1 --port 8131`。
- AI 相关工具优先读取通用 `AI_*` 配置。
- 剪映、AI 视频拆解和 AI 提示词反推都依赖 `ffmpeg`/`ffprobe`。Windows 本地开发优先使用项目内置的 `./ffmpeg-8.1.1-essentials_build/bin/ffmpeg.exe` 与 `./ffmpeg-8.1.1-essentials_build/bin/ffprobe.exe`；如果服务器已把二者加入 PATH，也可以配置为 `ffmpeg` / `ffprobe`。
- `ffmpeg` 负责抽音频、截帧；`ffprobe` 负责读取视频时长。`ffprobe` 找不到时，AI 证据管线会把时长读成 `0.0`；如果同时遇到无语音或 ASR 返回空转写，就无法按时长做视觉切段，可能出现 `RuntimeError: 转写结果为空，无法进行分段爆款拆解。`

### 3. 启动后端

```powershell
.\.venv\Scripts\activate
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
```

健康检查：

```text
http://127.0.0.1:8010/api/health
```

### 4. 启动前端

```powershell
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

### 5. 可选：启动 Douyin_Spider 新接口 sidecar

当 `DOUYIN_PROVIDER_MODE=spider` 或 `DOUYIN_PROVIDER_MODE=spider_first` 时，建议先启动新接口 sidecar：

```powershell
.\.venv\Scripts\activate
python -m uvicorn integrations.douyin_spider_provider.sidecar_server:app --host 127.0.0.1 --port 8131
```

验证 sidecar 进程：

```powershell
Invoke-RestMethod http://127.0.0.1:8131/health
Invoke-RestMethod http://127.0.0.1:8131/status
```

验证主后端能调用新接口：

```powershell
Invoke-RestMethod http://127.0.0.1:8010/api/integrations/douyin-spider/status
Invoke-RestMethod http://127.0.0.1:8010/api/integrations/douyin-provider/status
```

启动关系：

```text
前端 5173 -> 主后端 8010 -> Douyin_Spider sidecar 8131
```

`8131` 不直接给前端调用，只给主后端隔离运行 `Douyin_Spider`。如果要完全避免 TikHub 消耗，使用 `DOUYIN_PROVIDER_MODE=spider`；如果要更稳妥地先试新接口，使用 `DOUYIN_PROVIDER_MODE=spider_first`。

最小接口测试：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8010/api/integrations/douyin-provider/one-video `
  -ContentType "application/json" `
  -Body '{"aweme_id":"这里替换成真实 aweme_id"}'
```

如果 `8131` 端口被占用，确认是本项目遗留进程后可停止：

```powershell
Get-NetTCPConnection -LocalPort 8131 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

### 6. 可选：启动旧抖音下载上游服务

如果你仍要调用 `DOUYIN_DOWNLOAD_API_BASE` 对应的旧下载适配层，请单独启动旧上游项目：

```powershell
cd integrations\douyin_download_api\vendor\Douyin_TikTok_Download_API
.\.venv312\Scripts\activate
python start.py
```

默认地址：

```text
http://127.0.0.1:8123/docs
```

## 默认端口

```text
5173  前端 Vite
8010  主后端 FastAPI
8131  Douyin_Spider 新接口 sidecar
8123  Douyin_TikTok_Download_API
```

## 核心接口

### 基础接口

```text
GET /api/health
GET /api/workbench
```

### 抖音集成

```text
GET  /api/integrations/douyin/status
GET  /api/integrations/douyin/config
POST /api/integrations/douyin/config
POST /api/integrations/douyin/user-profile
POST /api/integrations/douyin/user-videos
POST /api/integrations/douyin/work-detail
POST /api/integrations/douyin/video-comments
POST /api/integrations/douyin/video-comment-replies
POST /api/integrations/douyin/favorites/items
POST /api/integrations/douyin/favorites/download
GET  /api/integrations/douyin/media-proxy
```

抖音新旧接口显式分层：

```text
GET  /api/integrations/douyin-provider/status
GET  /api/integrations/douyin-provider/metrics
POST /api/integrations/douyin-provider/one-video
POST /api/integrations/douyin-provider/user-profile
POST /api/integrations/douyin-provider/user-videos
POST /api/integrations/douyin-provider/work-detail
POST /api/integrations/douyin-provider/video-comments
POST /api/integrations/douyin-provider/video-comment-replies
POST /api/integrations/douyin-provider/favorites/items
POST /api/integrations/douyin-provider/favorites/download

GET  /api/integrations/douyin-spider/status
POST /api/integrations/douyin-spider/one-video
POST /api/integrations/douyin-spider/user-profile
POST /api/integrations/douyin-spider/user-videos
POST /api/integrations/douyin-spider/work-detail
POST /api/integrations/douyin-spider/video-comments
POST /api/integrations/douyin-spider/video-comment-replies
POST /api/integrations/douyin-spider/favorites/items
POST /api/integrations/douyin-spider/favorites/download

GET  /api/integrations/douyin-legacy-tikhub/status
POST /api/integrations/douyin-legacy-tikhub/user-search
```

`/api/integrations/douyin/*` 是兼容入口，当前也接入聚合层；新开发优先看 `/api/integrations/douyin-provider/*`，调试新接口时使用 `/api/integrations/douyin-spider/*`。

### 抖音对标与 AI 拆解

```text
POST /api/tools/douyin-target/search
POST /api/tools/douyin-target/users/bulk
GET  /api/tools/douyin-target/sets
POST /api/tools/douyin-target/sets
GET  /api/tools/douyin-target/sets/{set_id}
PATCH /api/tools/douyin-target/sets/{set_id}
DELETE /api/tools/douyin-target/sets/{set_id}
POST /api/tools/douyin-target/videos/collect
GET  /api/tools/douyin-target/videos/{video_id}/interactions
POST /api/tools/douyin-target/analysis/enqueue
POST /api/tools/douyin-target/analysis/{task_id}/retry-comments
POST /api/tools/ai-video-analysis/jobs/{task_id}/comments/retry
```

对标链路的数据保存：

- `tiktok_target_users`：对标用户，保存名称、简介、头像、粉丝数、点赞数、作品数、关注数、认证/私密状态、`recent_update_at`、`last_post_at`、`source_json`
- `tiktok_target_user_search_pages`：TikHub 用户搜索页原始响应、请求参数、分页信息、规范化 items
- `tiktok_target_user_video_pages`：用户作品分页缓存，按 `source + sec_user_id + max_cursor + count + sort/filter` 复用
- `tiktok_target_videos`：视频详情、播放/点赞/评论/转发/收藏、发布时间、派生指标、`source_json`
- `tiktok_target_video_comment_pages`：评论页/回复页原始响应和分页缓存
- `tiktok_target_video_comments`：评论和回复明细
- `tiktok_target_video_interaction_insights`：互动洞察、Top 评论、置顶评论、作者回复、关键词/情绪统计

### AI 模型配置

```text
GET  /api/ai-provider/config
GET  /api/ai-provider/diagnostics
POST /api/ai-provider/config
POST /api/ai-provider/test
```

当前支持的提供商配置包括：

- Gemini
- OpenAI
- simple relay
- 云雾
- DeepSeek
- 火山引擎
- 本地模型端点

### AI 视频拆解

```text
GET  /api/tools/ai-video-analysis/status
GET  /api/tools/ai-video-analysis/config
POST /api/tools/ai-video-analysis/config
POST /api/tools/ai-video-analysis/jobs
GET  /api/tools/ai-video-analysis/archives
GET  /api/tools/ai-video-analysis/archives/{archive_id}
```

证据管线会先下载/定位视频，再用 `ffmpeg` 抽取音频和关键帧、用 `ffprobe` 读取时长。纯音乐、无对白、噪声较重的视频可能让 ASR 返回空转写；只要 `ffprobe` 能正确读到时长，系统会按 `AI_VIDEO_SILENT_SEGMENT_SECONDS` 做无语音视觉切段。若任务报 `转写结果为空，无法进行分段爆款拆解`，优先检查：

- `.env` 中 `FFPROBE_BINARY` 指向的文件是否存在。
- 失败任务的 `data/runtime/ai_video_analysis/evidence/{task_id}/analysis_evidence.json` 中 `metadata.duration` 是否为 `0.0`。
- 是否开启了 `AI_VIDEO_RESUME_ENABLED=true` 并复用了旧的空 `transcript.json` / `keyframes.json`；修复依赖后可删除对应 evidence 目录或临时关闭 resume 后重跑。

### AI 提示词反推

```text
GET  /api/tools/ai-prompt-reverse/status
GET  /api/tools/ai-prompt-reverse/config
POST /api/tools/ai-prompt-reverse/config
POST /api/tools/ai-prompt-reverse/jobs
GET  /api/tools/ai-prompt-reverse/archives
GET  /api/tools/ai-prompt-reverse/archives/{archive_id}
```

### RunningHub TTS

```text
GET  /api/tools/runninghub-tts/status
GET  /api/tools/runninghub-tts/config
POST /api/tools/runninghub-tts/config
POST /api/tools/runninghub-tts/upload
POST /api/tools/runninghub-tts/jobs
POST /api/tools/runninghub-tts/sync
POST /api/tools/runninghub-tts/sync/{task_id}
```

### 任务中心

任务由后端写入 PostgreSQL，前端可轮询任务状态。相关路由在 `backend/app/routes/tasks.py`。

### RunningHub TTS 参数说明

配置区：

- `API Key`
  - RunningHub 密钥，必填。
  - 用于提交任务、查询任务状态、拉取输出结果。
  - 该字段会保存到本地配置，下次打开页面自动回填。
- `API Base`
  - RunningHub 接口地址，默认值为 `https://www.runninghub.cn`。
  - 除非有代理、镜像或私有部署需求，否则不建议修改。
- `Workflow 标识`
  - 工作流标识符。
  - 当前默认预置为 `runninghub/tts_stable_emotion.json`，对应稳定情感工作流 `2053641347223044097`。
  - 也支持其他预置名，如 `runninghub/tts_index2.json`。
  - 支持直接填写 `workflowId`。
  - 支持填写 RunningHub 工作流链接。
  - 当 `Workflow ID` 为空时，系统会用这个字段自动解析目标工作流。
- `Workflow ID`
  - 显式指定 RunningHub 的 workflowId。
  - 该字段优先级高于 `Workflow 标识`。
  - 推荐在接入用户自己的工作流时直接填写这个字段。
- `Instance Type`
  - 可选，例如 `plus`。
  - 当前版本已经会随创建任务请求一起透传给 RunningHub。
- `轮询间隔(秒)`
  - 后端轮询 RunningHub 状态接口的时间间隔，范围 `1-30` 秒。
  - 建议值为 `3-5` 秒。
  - 该参数需要先点击“保存配置”，后续新任务才会按新的轮询间隔运行。
- `预置工作流`
  - 用于快速填充预置的 `Workflow 标识` 和 `Workflow ID`。
  - 当前包含稳定情感工作流，以及 `tts_index2 / tts_edge / tts_spark` 等预置项。

生成区：

- `生成文本`
  - 必填。
  - 这是最终送入 RunningHub 工作流文本输入节点的内容。
- `参考音频`
  - 可选。
  - 上传后会先保存到本地，再由后端转传到 RunningHub。
  - 只有你的目标工作流本身支持音频输入时，这个参数才会真正生效。
- `Voice`
  - 可选。
  - 只有目标工作流存在 `voice`、`speaker`、`character` 之类的输入字段时才会生效。
  - 这个值通常应填写工作流约定的角色名、音色名或 speaker id，而不是任意自然语言描述。
- `已上传参考音频路径`
  - 上传成功后自动回填的本地路径。
  - 提交任务时后端会读取这个路径，并把音频上传到 RunningHub。
- `高级配置`
  - 前端默认收起，避免干扰主流程。
  - 当前会把情感模式、情感参考音频、Emotion Alpha、Emotion Text 和情感滑块放入高级配置。
  - 速度/时长控制相关参数已暂时从前端主界面隐藏，但后端仍保留兼容能力，便于后续接回其他工作流。

使用建议：

- 最小可用填写方式：`API Key + Workflow ID + 生成文本`。
- 如果你引用的是自己的工作流，推荐直接填写 `Workflow ID`，不要只依赖 `Workflow 标识` 推断。
- 如果你希望 `参考音频 / Voice / 情感控制` 生效，必须确保目标 workflow 中本身存在对应输入节点。
- 对于默认稳定工作流 `2053641347223044097`，推荐主流程只填写 `生成文本 + 参考音频`，情感相关按需去高级配置中调整。
- 任务完成后，任务详情会展示输出文件链接和内置音频播放器，可直接试听结果。

### Studio 创作工作台

```text
POST /api/studio/brainstorm
POST /api/studio/lock_concept
POST /api/studio/generate_blueprint
```

### 剪映 SDK 能力

```text
GET  /api/tools/jianying-editor-sdk/status
POST /api/tools/jianying-editor-sdk/diagnostics/deep
GET  /api/tools/jianying-editor-sdk/page
POST /api/tools/jianying-editor-sdk/drafts/list
POST /api/tools/jianying-editor-sdk/drafts/summary
POST /api/tools/jianying-editor-sdk/drafts/show
POST /api/tools/jianying-editor-sdk/assets/search
POST /api/tools/jianying-editor-sdk/exports
POST /api/tools/jianying-editor-sdk/web-vfx/record
POST /api/tools/jianying-editor-sdk/tts
POST /api/tools/jianying-editor-sdk/cloud/assets/resolve
POST /api/tools/jianying-editor-sdk/cloud/music-library/sync
POST /api/tools/jianying-editor-sdk/smart-zoom/drafts
POST /api/tools/jianying-editor-sdk/movie-commentary/drafts
```

## 运行数据与产物

默认运行数据位于：

```text
data/runtime/
```

其中通常包含：

- 下载的视频素材
- AI 拆解任务产物
- AI 反推任务产物
- PostgreSQL 任务库

这些内容属于运行时数据，不建议提交到仓库。

## 剪映 SDK 说明

仓库中的 `sdks/jianying-editor-skill/` 采用 vendor snapshot 管理方式，锁定信息记录在：

```text
sdks/jianying-editor-skill.lock.json
```

职责边界如下：

```text
integrations/video_pipeline/         生成标准脚本数据
integrations/jianying_draft/         将脚本转换为剪映草稿
integrations/jianying_editor_skill/  负责 SDK 桥接、能力发现和诊断
sdks/jianying-editor-skill/          上游 SDK 快照
```

注意事项：

- 自动导出仅在 Windows 环境下可用。
- 自动导出依赖 `uiautomation`。
- 当前逻辑要求检测到剪映版本 `<= 5.9` 才会标记为可自动导出。
- 如自动检测失败，可尝试设置 `JY_JIANYING_VERSION=5.9.0` 进行覆盖。

## 开发约定

- 主业务逻辑不要直接侵入第三方仓库源码。
- 新能力优先放在 `integrations/` 下，通过适配器接入。
- 上游项目、运行时缓存、下载结果应尽量与主仓库隔离。
- 根目录 `.gitignore` 已忽略常见产物目录，如 `node_modules/`、`dist/`、`.venv/` 和 `data/runtime/`。

## 测试

当前仓库包含至少一组剪映 SDK 相关测试：

```powershell
pytest tests/test_jianying_editor_sdk.py
```

如果只想快速验证后端是否可启动，也可以先访问：

```text
http://127.0.0.1:8010/api/health
```

## 后续维护建议

- README 以“当前代码实际可用能力”为准更新，不再保留历史变更流水账。
- 如果端口、环境变量、外部依赖或核心接口发生变化，请优先同步更新本文件。
- 对于某个集成的设计细节，优先补充到对应 `integrations/<name>/README.md` 中。
