# AI 视频拆解优化代办

日期：2026-05-20

目标：基于当前 AI 视频拆解链路的代码审查，整理后续可执行优化项。本文只记录架构现状、风险点和代办拆分，不代表已实施。

## 1. 当前架构概览

| 层级 | 主要文件 | 当前职责 | 审查结论 |
| --- | --- | --- | --- |
| 前端对标入口 | `src/features/douyinTarget/DouyinTargetPanel.jsx` | 对标账号/视频选择，批量加入 AI 拆解队列 | 组件偏大，筛选、采集、入队状态混在一起 |
| AI 视频配置页 | `src/features/settings/AiVideoSettingsPanel.jsx` | 配置 evidence、ASR、分段、并发、提示词 | 字段多且手写映射，适合 schema/reducer 化 |
| AI 视频 API 路由 | `backend/app/routes/ai_video_analysis.py` | 配置、任务创建、队列操作、证据文件、复刻导出、改写、送脚本 | 职责过宽，且仍保留旧执行函数 `run_breakdown_task` |
| 抖音对标入队路由 | `backend/app/routes/douyin_target.py` | 生成 AI 拆解 payload，创建 task、target_task、queue job | 与 AI 视频路由存在 payload/任务组装重复 |
| 队列存储 | `backend/app/video_analysis_queue.py` | `ai_video_jobs`、claim、retry、cancel、stale requeue、model runs | 队列主干可用；`ai_video_artifacts` / `ai_video_chunks` 目前未充分使用 |
| Worker 调度 | `backend/app/video_analysis_worker.py` | 多线程 worker 认领任务，采评论，调用 adapter，落库，同步对标状态 | 主流程清晰；取消机制依赖 progress 回调，长阻塞阶段不可快速中断 |
| 评论采集 | `backend/app/ai_video_comment_service.py` | 自适应评论采样、回复采集、互动上下文合并 | 职责相对清晰，可进一步变成独立 pipeline step |
| AI 拆解适配器 | `integrations/ai_video_analysis/adapter.py` | provider 选择、prompt、模型调用、分段/全局拆解、结果归一化 | 最大单体风险，建议拆分 |
| 证据包流水线 | `integrations/ai_video_analysis/evidence_pipeline.py` | 视频定位/下载、FFmpeg、ASR、切片、抽帧、网格图、evidence JSON | 阶段边界存在，但类内职责过多 |
| 模型/ASR 接入 | `integrations/ai_video_analysis/relay_clients.py`、`doubao_asr.py`、`transcribers.py`、`audio_publication.py` | Gemini/Yunwu/OpenAI-compatible relay、DeepSeek、豆包 ASR、音频发布 | 已拆出部分网关能力；adapter 仍有过多 provider 判断 |
| 分析结果落库 | `backend/app/short_video_analysis_store.py` | 视频、指标快照、analysis run、segments、formula、remake exports | 数据结构有价值，但 result schema 偏宽松 |
| 结果展示 | `src/features/results/AnalysisResultModal.jsx` | 视频同步、转写、评论洞察、复刻实验室、model runs 展示 | 组件过大，派生数据、请求和操作动作混在一起 |

## 2. P0/P1：优先优化项

### TODO 1：统一 AI 视频拆解执行入口（已完成）

- [x] 抽出 `AnalysisJobRunner` 或等价 service，承载完整执行流。
- [x] 让 `VideoAnalysisCoordinator.run_claimed_job()` 调用该 runner。
- [x] 删除或封存 `backend/app/routes/ai_video_analysis.py` 中旧的 `run_breakdown_task`。
- [x] 保证任务执行逻辑只维护一份：评论采集、adapter 调用、结果 merge、archive、dataset、target sync。
- [x] 跑测试验证：worker 执行与 runner 返回状态一致。

实施记录：

- 新增 `backend/app/ai_video_analysis_runner.py`。
- `backend/app/video_analysis_worker.py` 改为委托 runner 执行完整拆解流程。
- `backend/app/routes/ai_video_analysis.py` 中旧 `run_breakdown_task` 保留兼容入口，但内部已委托 runner，不再维护第二套执行逻辑。
- 相关 AI 视频测试已通过。

验收标准：

- 创建 AI 视频任务后只走 queue + worker。
- 不存在两套可分叉的拆解执行逻辑。
- 现有 `tests/test_ai_video_queue.py` 通过。

### TODO 2：拆分 `AiVideoAnalysisAdapter`

- [x] 新建 `integrations/ai_video_analysis/prompt_builder.py`。
- [x] 新建 `integrations/ai_video_analysis/model_gateway.py`。
- [x] 新建 `integrations/ai_video_analysis/result_normalizer.py`。
- [x] 新建 `integrations/ai_video_analysis/analysis_runner.py` 或 `evidence_breakdown_runner.py`。
- [x] 保留 `adapter.py` 作为薄适配入口，减少 provider/prompt/normalize 混杂。
- [x] 清理 official/native Gemini 不可达代码或移动到独立 experimental 分支。

建议职责拆分：

| 模块 | 负责内容 |
| --- | --- |
| `prompt_builder.py` | 分段 prompt、全局 prompt、赛道 profile |
| `model_gateway.py` | DeepSeek、Gemini relay、OpenAI-compatible relay 调用和重试 |
| `result_normalizer.py` | 模型 JSON 清洗、字段兼容、schema repair |
| `analysis_runner.py` | evidence 分段拆解、checkpoint、model run 记录 |
| `adapter.py` | 对外 `create_job()` 入口和 provider 选择 |

验收标准：

- `adapter.py` 行数明显下降。
- prompt、模型调用、normalize 可独立单测。
- 行为不变，旧测试通过。

实施记录：

- P1 第一阶段已抽出 `integrations/ai_video_analysis/result_normalizer.py`，承载模型 JSON 清洗、字段兼容和评分归一化。
- `integrations/ai_video_analysis/adapter.py` 的 `_parse_model_json()` 已改为薄包装，委托 `parse_model_json()`。
- 新增独立 normalizer 单测，覆盖 Markdown code fence、中文字段别名和分数字符串归一化。
- 分段模型 JSON 清洗也已迁移到 `result_normalizer.py`，`adapter.py` 的 `_parse_segment_json()` 仅保留兼容薄包装。
- P1 第二阶段已抽出 `integrations/ai_video_analysis/prompt_builder.py`，承载 genre profile、分段 prompt、全局 prompt 和直连 prompt 构造。
- `integrations/ai_video_analysis/adapter.py` 保留原有 prompt 相关方法名作为兼容薄包装，降低调用方迁移风险。
- 新增独立 prompt builder 单测，覆盖分段 prompt 的赛道注入和片段字段输出。
- P1 第三阶段已抽出 `integrations/ai_video_analysis/model_gateway.py`，先承载 provider/relay 判定、relay base/token 解析和模型 usage 归一化纯逻辑。
- `integrations/ai_video_analysis/adapter.py` 的实际 HTTP 调用暂未迁移，避免一次性改动 provider 行为。
- 新增独立 model gateway 单测，覆盖 OpenAI-compatible relay 判定和 usage 归一化。
- P1 第四阶段已抽出 `integrations/ai_video_analysis/analysis_runner.py`，承载 evidence 分段拆解、checkpoint 复用、全局汇总和 model run 记录编排。
- `adapter.py` 的 `_evidence_breakdown()` 已变为薄包装；模型调用、截图抽取、入库记录仍通过 adapter 原方法，保持行为兼容。
- 清理了 `adapter.py` 中 `raise` 之后不可达的 official/native Gemini 分支，以及未被调用的旧 relay POST/retry 辅助方法。

### TODO 3：将 evidence 阶段状态写入 DB

- [x] 明确 `ai_video_artifacts` 写入点。
- [x] 明确 `ai_video_chunks` 写入点。
- [x] evidence 生成后记录 video/audio/transcript/keyframes/grid/global json artifact。
- [x] 分段拆解开始、完成、失败时写入 chunk 状态。
- [x] queue status API 返回当前 chunk/stage 细节。
- [x] 前端队列页展示卡在哪个阶段、哪个片段。

验收标准：

- 一个任务从排队到完成，DB 可追溯所有关键产物。
- 删除 queue job 时能清理对应 artifacts/chunks/model_runs。
- 失败任务能看到失败阶段和失败片段。

实施记录：

- 新增 `backend/app/video_analysis_queue.py` 中 artifact/chunk 读写 API：`record_ai_video_artifact()`、`list_ai_video_artifacts()`、`upsert_ai_video_chunk()`、`list_ai_video_chunks()`。
- `queue_snapshot(task_id=...)` 已返回指定任务的 `job`、`artifacts`、`chunks`，供状态 API 展示。
- evidence 生成后写入 video/audio/transcript/transcript_raw/keyframes/keyframe_grid/evidence_json artifacts，并初始化 chunk pending 状态。
- 分段模型调用开始/成功/失败时更新 chunk running/done/failed，成功时写入 `segment_breakdown` artifact；全局汇总成功时写入 `global_breakdown` artifact。
- 删除 queue job 已沿用原有清理逻辑，覆盖 artifacts/chunks/model_runs。
- 前端 `AiVideoQueuePanel` 已在指定任务视图中展示分段状态和关键产物列表。

### TODO 4：增强取消机制

- [x] 引入 `CancellationToken` 或等价对象。
- [x] 在评论采集、视频下载、FFmpeg、ASR、分段模型、全局总结阶段入口/出口检查取消状态。
- [x] 外部 HTTP 请求统一 timeout 和 retry policy。
- [x] FFmpeg subprocess 支持取消时终止。
- [x] 队列 UI 明确显示“取消已请求/等待安全点停止”。

验收标准：

- running 任务点击取消后，不需要等完整模型/ASR 全部结束才停止。
- cancelled 任务不再继续写入 done 结果。
- 取消后的 task、queue job、target task 状态一致。

实施记录：

- 新增 `AiVideoTaskCancelled`、`is_ai_video_cancel_requested()`、`raise_if_ai_video_cancelled()` 作为取消 token 等价机制。
- Adapter 在任务开始、mock 生成前、evidence build 前后、evidence state 写入后检查取消状态。
- Analysis runner 在分段循环、分段模型调用前后、截图前后、全局汇总前后检查取消状态，避免取消后继续写入 done/global 结果。
- Worker 捕获 `AiVideoTaskCancelled` 后统一落 `cancelled` task/job 状态。
- 队列 API 已返回 `cancel_requested` 和错误消息，队列页现有状态/阶段区域可展示“取消已请求/等待安全点停止”。
- 新增 `integrations/ai_video_analysis/http_policy.py`，统一下载、模型 relay、Doubao ASR 的 timeout/retry 默认策略。
- `VideoEvidencePipeline` 支持 `cancel_check`，FFmpeg/FFprobe 从 `subprocess.run` 改为 `Popen` 轮询；取消或超时时会终止子进程。

### TODO 5：清理 provider 分支和不可达代码

- [ ] 梳理当前支持矩阵：`evidence + relay`、`direct + gemini relay`、`mock`。
- [ ] 删除或隔离 `raise` 之后不可达的 official/native Gemini 代码。
- [ ] 将 provider 判断集中到 `model_gateway.py`。
- [ ] 将错误信息从“配置云雾/简单中转站”抽成统一配置诊断。

验收标准：

- provider 选择逻辑只有一个权威入口。
- direct/evidence 模式错误提示准确。
- `validate_config()` 与实际调用路径一致。

### TODO 6：配置保存后支持 worker 扩缩容

- [ ] 保存 `AI_VIDEO_MAX_CONCURRENT_TASKS` 后触发 worker reconcile。
- [ ] 或新增 `/api/tools/ai-video-analysis/workers/restart`。
- [ ] queue status 返回 configured limit 与实际 thread_count 的差异。
- [ ] 前端配置页提示保存后是否需要重启 worker。

验收标准：

- 配置从 1 改到 3 后，无需重启 FastAPI 即可增加 worker。
- 配置从 3 改到 1 后，不再新认领超过 1 个 active job。

## 3. P2：结构和维护性优化

### TODO 7：拆分前端结果页

- [x] 新建 `useAiVideoEvidence(taskId)`。
- [x] 新建 `useDouyinInteractions(videoId)`。
- [x] 拆出 `ResultOverview`。
- [x] 拆出 `VideoTranscriptSyncPanel` 到独立文件。
- [x] 拆出 `SegmentTimeline` 到独立文件。
- [x] 拆出 `RemakeLab` 到独立文件。
- [x] 将结果 normalize 逻辑尽量集中到 `src/utils/appUtils.js` 或专用 util。

验收标准：

- `AnalysisResultModal.jsx` 只负责页面组装。
- 组件文件规模下降，异步请求 hook 可单独测试。

### TODO 8：配置页改为 schema-driven form

- [x] 后端 `/config` 增加字段元数据或新增 `/config/schema`。
- [x] 前端使用字段数组渲染大部分 input/select。
- [x] 数字、布尔、枚举字段统一 parse/serialize。
- [x] 保留复杂字段如 `analysis_prompt` 的定制 UI。

验收标准：

- 新增配置项时，不需要同时改多组 `useState` 和手写 payload 映射。
- 前端发送字段名与后端 Pydantic 字段一致。

### TODO 9：结果 schema 强约束

- [x] 定义 Pydantic `AnalysisResult`。
- [x] 定义 Pydantic `SegmentBreakdown`。
- [x] 定义 Pydantic `EvidenceMetadata`。
- [x] 定义 Pydantic `CommentCollectionState`。
- [x] 模型输出先 validate/repair，再落库。
- [x] 不合法字段写入 `raw_model_json`，规范字段写入结构化 result。

验收标准：

- 前端不再需要处理过多字段别名。
- 落库结果结构稳定。
- 模型返回非 JSON 或字段缺失时有明确 repair/fallback 策略。

### TODO 10：补齐测试覆盖

- [ ] 配置保存后 worker 扩缩容测试。
- [x] running job cancel 边界测试。
- [x] artifact/chunk DB 写入测试。
- [x] evidence JSON 包含完整 `evidence_path` 和 checkpoint 测试。
- [x] fake-provider 端到端测试：入队 -> worker -> evidence -> model_runs -> dataset -> target sync。
- [ ] 前端关键 hook 的请求成功/失败测试。

验收标准：

- `python -m unittest discover -s tests -p "test_ai_video*.py"` 通过。
- 关键状态流有回归保护。

## 4. 建议实施顺序

1. 先抽 `AnalysisJobRunner`，消除执行逻辑重复。
2. 再落地 artifacts/chunks，把运行状态变得可观察。
3. 然后拆 `adapter.py`，降低后续改 provider/prompt 的风险。
4. 最后做前端组件拆分和 schema 化配置页。

## 5. 非目标

- 本轮不改模型 prompt 业务口径。
- 本轮不切换评论接口供应商。
- 本轮不改对标账号采集策略。
- 本轮不重做 UI 视觉风格。
