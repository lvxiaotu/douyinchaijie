# 个人工具工作台

这是一个个人自动化工具工作台，用来逐步接入下载、采集、分析、ComfyUI、文件处理等个人工作流。项目原则是：主系统保持稳定，第三方开源项目通过 `integrations/` 适配器接入。

以后有大的需求变动、配置变动、端口变动、第三方项目替换，都优先记录在本 README 的“变更记录”和“配置变更记录”里。

## 当前技术选型

- 前端：Vite + React
- 后端：Python + FastAPI
- 集成方式：第三方项目独立运行或独立封装，本项目通过适配器调用
- 当前抖音集成：`Evil0ctal/Douyin_TikTok_Download_API`
- 当前 AI 视频拆解：`integrations/ai_video_analysis`，先使用 mock provider 跑通任务链路

## 目录结构

```text
.
├─ src/                         # 前端工作台
├─ backend/app/                 # 主后端 FastAPI
├─ integrations/                # 第三方项目适配器
├─ integrations/douyin_download_api/
│  ├─ adapter.py                # 抖音 API HTTP 适配器
│  └─ vendor/                   # 上游仓库本地目录，不提交
├─ integrations/ai_video_analysis/
│  ├─ adapter.py                # AI 视频拆解适配器
│  └─ README.md                 # 工具设计和输出结构
├─ docs/                        # 架构说明
├─ data/runtime/                # 运行时数据与下载结果，不提交
├─ scripts/                     # 辅助脚本
├─ .env.example                 # 配置示例
├─ package.json                 # 前端依赖
└─ requirements.txt             # 主后端依赖
```

## 启动顺序

需要开 3 个 PowerShell 窗口。

### 1. 启动上游抖音服务

```powershell
cd G:\ob-book\codex-project\integrations\douyin_download_api\vendor\Douyin_TikTok_Download_API
.\.venv312\Scripts\activate
python start.py
```

确认地址：

```text
http://127.0.0.1:8123/docs
```

### 2. 启动主后端

```powershell
cd G:\ob-book\codex-project
.\.venv\Scripts\activate
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
```

确认地址：

```text
http://127.0.0.1:8010/api/integrations/douyin/status
```

正常应返回：

```json
{
  "ready": true
}
```

### 3. 启动前端

```powershell
cd G:\ob-book\codex-project
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

## 当前端口

```text
5173  前端 Vite
8010  主后端 FastAPI
8123  Douyin_TikTok_Download_API
```

## 当前抖音接口

主项目统一暴露这些接口：

```text
GET  /api/integrations/douyin/status
POST /api/integrations/douyin/user-profile
POST /api/integrations/douyin/work-detail
POST /api/integrations/douyin/favorites/download
```

目前已确认：

- `user-profile` 已测试成功
- `work-detail` 需要继续确认上游参数和 Cookie 配置
- `favorites/download` 需要小批量测试后再接入完整任务流

## 当前 AI 视频拆解接口

```text
GET  /api/tools/ai-video-analysis/status
POST /api/tools/ai-video-analysis/jobs
```

当前状态：

- 已在视频卡片上预留“拆解”按钮。
- 当前 provider 为 `mock`，用于验证任务创建、结果保存、前端展示。
- 后续接 Gemini、GPT 或本地模型时，替换 `integrations/ai_video_analysis/adapter.py` 中的 provider 调用逻辑。

## 配置文件

本项目配置在：

```text
G:\ob-book\codex-project\.env
```

关键配置：

```text
VITE_API_BASE=http://127.0.0.1:8010
DOUYIN_DOWNLOAD_API_BASE=http://127.0.0.1:8123
DOUYIN_OUTPUT_DIR=./data/runtime/douyin/downloads
DY_COOKIES=你的抖音网页版 Cookie
AI_VIDEO_PROVIDER=mock
AI_VIDEO_OUTPUT_DIR=./data/runtime/ai_video_analysis
GEMINI_API_KEY=
AI_VIDEO_ANALYSIS_PROMPT=
AI_PROMPT_REVERSE_PROVIDER=mock
AI_PROMPT_REVERSE_OUTPUT_DIR=./data/runtime/ai_prompt_reverse
AI_PROMPT_REVERSE_PROMPT=
OPENAI_API_KEY=
LOCAL_VIDEO_MODEL_ENDPOINT=
```

注意：

- `.env` 不要提交到 Git。
- Cookie、API Key、账号相关配置只放本机。
- 上游 `Douyin_TikTok_Download_API` 也有自己的配置文件，位于 `crawlers/douyin/web/config.yaml`。

## 第三方项目接入规则

每个 GitHub 开源项目都按这个方式接入：

```text
integrations/项目名/
├─ adapter.py
├─ README.md
└─ vendor/
```

原则：

- 主后端不直接混入第三方项目源码。
- 适配器负责调用第三方项目、整理参数、归一化结果。
- 第三方项目依赖和运行环境尽量独立。
- 如果替换第三方项目，只替换适配器，不改主接口。

详细架构说明见：

```text
docs/ARCHITECTURE.md
```

## 配置变更记录

以后端口、路径、环境变量、第三方服务地址变更，都记录在这里。

```text
2026-04-30
- Douyin_TikTok_Download_API 端口使用 8123。
- 主后端端口使用 8010。
- 前端端口使用 5173。
- 抖音集成从 cv-cat/DouYin_Spider 替换为 Evil0ctal/Douyin_TikTok_Download_API。
- 主项目通过 HTTP 调用上游抖音服务，不再 import 上游爬虫源码。
- 新增 AI 视频拆解工具骨架，默认使用 mock provider，任务结果保存到 `data/runtime/ai_video_analysis/jobs/`。
- 新增 SQLite 任务库 `data/runtime/tasks.sqlite3`，任务中心从后端任务状态读取，不再只依赖前端内存。
```

## 需求变更记录

以后大的需求变动记录在这里。

```text
2026-04-30
- 当前阶段目标：做个人工具工作台简略版。
- 第一批功能：抖音用户主页信息、作品详情、收藏列表视频下载。
- 前端要求：这些接口集成到主页面，填写参数即可调用。
- 后续方向：任务中心、下载记录、素材库入库、视频内容分析。
- 新增工具：AI 视频拆解。入口从已采集视频卡片触发，目标是输出摘要、时间线、画面、声音、文案钩子、关键词和可复用提示词。
- AI 视频拆解任务改为后端后台执行：创建任务后写入 SQLite，前端轮询 `/api/tasks?task_type=ai_video_analysis` 展示进度和完成状态。
- AI 视频拆解支持在配置页编辑提示词模板，模板可使用 `{desc}` 和 `{author}` 变量。
- AI 视频拆解结果改为商业拆解结构：核心钩子、需求与场景、产品表现、视觉与结构、商业定位。
- 已完成的 AI 视频拆解会写入 SQLite 的 `analysis_archives` 表，可通过 `/api/tools/ai-video-analysis/archives` 查询。
- 新增 AI 提示词反推工具：从采集视频反推出 `master_prompt`、`negative_prompt`、分镜提示词、风格关键词和使用建议。
- 已完成的 AI 提示词反推会写入 SQLite 的 `prompt_reverse_archives` 表，可通过 `/api/tools/ai-prompt-reverse/archives` 查询。
```

## 开发备注

- 旧目录 `integrations/douyin_spider/` 已弃用，仅保留以避免误删本地文件。
- `integrations/*/vendor/*` 已加入 `.gitignore`，第三方仓库不提交。
- `data/runtime/` 已加入 `.gitignore`，下载结果不提交。

## Gemini 中转站配置

```text
2026-04-30
- Gemini 新增中转站模式：GEMINI_ACCESS_MODE=official|relay。
- 中转站地址默认 GEMINI_RELAY_BASE_URL=https://jeniya.top，令牌写入 GEMINI_RELAY_API_KEY。
- AI 视频拆解和 AI 提示词反推都复用同一组 Gemini 接入配置。
- 中转站模式使用 Gemini 原生 REST generateContent 格式，将视频文件以 inline_data base64 方式发送。
- 新增全局 AI 连接配置：AI_MODEL_PROVIDER、AI_ACCESS_MODE、AI_NATIVE_API_KEY、AI_RELAY_BASE_URL、AI_RELAY_API_KEY、AI_MODEL。
- 配置页的“AI 模型连接配置”会同步写入通用 AI_* 配置和当前 Gemini 兼容配置，后续新 AI 工具优先读取 AI_*。
- OpenAI API 路线独立配置：OPENAI_ACCESS_MODE、OPENAI_API_KEY、OPENAI_RELAY_BASE_URL、OPENAI_RELAY_API_KEY、OPENAI_MODEL、OPENAI_API_FORMAT。
- 配置页按供应商拆分为 OpenAI、Gemini、本地或其他 API，每个供应商可单独选择原生/中转、单独测试、单独保存；API Key 明文显示。
- 配置页调整为“当前全局 AI 模型”下拉，只展示当前选中的供应商配置；保存哪个供应商，后续 AI 工具默认使用哪个供应商。
- 预留供应商：Gemini、OpenAI、简单中转站、DeepSeek、火山引擎、本地或其他 API。
- AI 模型管理参考 Cherry Studio 的 Provider Settings 结构：左侧供应商列表，右侧当前供应商配置；支持模型列表、默认模型选择、测试连接和保存为全局默认。
- 新增云雾 API 供应商：默认 Base URL 为 `https://yunwu.ai`，默认接口格式为 Gemini 原生 `generateContent`，适合 AI 视频拆解和提示词反推的视频上传链路。
```
