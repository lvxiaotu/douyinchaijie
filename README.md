# Personal Ops Workbench

一个面向个人内容生产与自动化处理的工作台项目。

当前仓库把前端工作台、FastAPI 后端、第三方能力适配层，以及剪映相关 SDK 能力整合在一起，目标是把“采集素材 -> 分析视频 -> 生成脚本 -> 进入剪映生产链路”串成一套可持续演进的本地工具链。

## 当前能力

- 抖音采集集成
  - 用户主页信息
  - 用户作品列表
  - 单作品详情
  - 收藏视频列表与下载
- AI 视频拆解
  - 后端异步任务执行
  - 拆解结果归档
  - 基于证据管线的截图、转写、分段分析
- AI 提示词反推
  - 从视频内容反推出主提示词、负向提示词和风格关键词
  - 结果归档
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
- 数据存储：SQLite
- 集成方式：`integrations/` 适配层
- 运行环境：Windows 优先，部分剪映能力仅支持 Windows

## 目录结构

```text
.
├─ src/                             前端工作台
├─ backend/app/                     FastAPI 后端
├─ integrations/                    第三方工具与业务适配层
│  ├─ douyin_download_api/          抖音下载服务适配器
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

如果你要使用抖音采集能力，还需要额外启动上游 `Douyin_TikTok_Download_API` 服务。

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

AI_MODEL_PROVIDER=gemini
AI_ACCESS_MODE=official
AI_NATIVE_API_KEY=
AI_RELAY_BASE_URL=
AI_RELAY_API_KEY=
AI_MODEL=gemini-2.5-flash

AI_VIDEO_OUTPUT_DIR=./data/runtime/ai_video_analysis
AI_PROMPT_REVERSE_OUTPUT_DIR=./data/runtime/ai_prompt_reverse

FFMPEG_BINARY=ffmpeg
FFPROBE_BINARY=ffprobe
LOCAL_VIDEO_MODEL_ENDPOINT=
```

说明：

- `.env` 不应提交到 Git。
- 抖音采集依赖 `DY_COOKIES` 和上游下载服务。
- AI 相关工具优先读取通用 `AI_*` 配置。
- 剪映与视频分析链路建议提前准备好 `ffmpeg` 和 `ffprobe`。

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

### 5. 可选：启动抖音上游服务

如果你要调用抖音相关接口，请单独启动上游项目：

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
POST /api/integrations/douyin/favorites/items
POST /api/integrations/douyin/favorites/download
GET  /api/integrations/douyin/media-proxy
```

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

### AI 提示词反推

```text
GET  /api/tools/ai-prompt-reverse/status
GET  /api/tools/ai-prompt-reverse/config
POST /api/tools/ai-prompt-reverse/config
POST /api/tools/ai-prompt-reverse/jobs
GET  /api/tools/ai-prompt-reverse/archives
GET  /api/tools/ai-prompt-reverse/archives/{archive_id}
```

### 任务中心

任务由后端写入 SQLite，前端可轮询任务状态。相关路由在 `backend/app/routes/tasks.py`。

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
- SQLite 任务库

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
