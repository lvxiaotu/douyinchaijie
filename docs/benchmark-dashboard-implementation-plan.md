# 短视频对标分析工作台施工方案

本文档以 `docs/benchmark-dashboard-wireframe.html` 当前 HTML demo 为准，建设一个“短视频对标分析工作台”。当前默认聚焦玄学塔罗，但底层必须支持动漫解说、原创 Vlog、好物种草、知识教程等其他内容类型。

核心目标：

```text
看整体 -> 找高价值视频 -> 找对标博主 -> 沉淀内容模式 -> 进入任务中心看完整拆解
```

## 1. 页面范围

当前 HTML demo 包含 6 个模块：

- 内容类型筛选
- 总览指标卡
- 内容排行榜
- 博主对标
- 内容模式库
- 类型迁移与指标说明
- 视频轻详情抽屉

任务中心仍然负责单条视频的完整拆解，包括分段、转写、关键帧和 evidence。本工作台只负责聚合、排序、筛选、解释和跳转。

## 2. 当前数据基础

第一版直接使用现有 job/evidence JSON：

```text
data/runtime/ai_video_analysis/jobs/*.json
data/runtime/ai_video_analysis/evidence/**
```

当前数据大致情况：

- 拆解任务约 148 条
- 去重视频约 112 个
- 博主约 38 个
- 分段拆解约 1040 条

近期预期规模：

- 视频约 2000 条
- 用户/博主约 200 个
- AI 拆解任务会持续写入
- evidence、关键帧、转写文件数量会随任务数快速增长

每条 job 中主要可用字段：

- `video.aweme_id`
- `video.desc`
- `video.author`
- `video.digg_count`
- `video.comment_count`
- `video.collect_count`
- `video.share_count`
- `video.derived_metrics`
- `result.summary`
- `result.content_identity`
- `result.core_hook`
- `result.need_context`
- `result.copywriting_formula`
- `result.psychology_breakdown`
- `result.replication_plan`
- `result.risk_control`
- `result.viral_scores`
- `result.segment_breakdowns`
- `result.evidence`

注意：

- 当前 SQLite 业务表为空，第一版不要依赖它。
- 当前竞品公开数据缺少完播、留存、复访、铁粉互动。
- 当前 `play_count` 不可靠，不能用于播放率、完播率、互动率等真实后台指标。
- 第一版采用“公开数据代理评估 + AI 拆解辅助判断”。
- 2000 视频 / 200 博主规模不需要复杂数仓，但不建议每次 API 请求全量扫描 JSON。
- evidence 目录只在打开视频轻详情或任务中心时按需读取，不进入列表接口热路径。

## 3. 信息架构

### 3.1 内容类型筛选

HTML demo 顶部筛选：

```text
玄学塔罗 / 全部类型 / 动漫解说 / 原创 Vlog / 好物种草 / 知识教程
```

设计原则：

- “玄学塔罗”是当前默认视角。
- 其他类型不是摆设，数据模型必须保留可迁移能力。
- 类型筛选会影响总览、排行榜、博主对标、模式库。

内容类型识别优先级：

```text
result.content_identity.track
result.genre
标题/描述/标签关键词
人工修正字段
```

### 3.2 总览指标卡

HTML demo 中展示：

```text
拆解任务 / 去重视频 / 博主数 / 分段拆解 / 平均复刻分
```

第一版字段：

- `analysis_task_count`
- `unique_video_count`
- `author_count`
- `segment_count`
- `avg_imitation_value`

后续可扩展：

- 平均爆款潜力
- 平均商业价值
- 中高风险视频数
- 有 evidence 视频数
- 有评论采集视频数

### 3.3 内容排行榜

HTML demo 中排行榜 Tab：

```text
综合互动 / 小号效率 / 收藏价值 / 评论驱动
```

排行榜不是最终结论，而是“发现值得研究的视频”的入口。

每条视频展示：

- 视频标题/描述
- 博主
- 互动倾向进度条
- 看证据按钮

第一版榜单口径：

- 综合互动：按公开互动强度排序
- 小号效率：按公开互动强度 / 粉丝数排序
- 收藏价值：按收藏 / 点赞排序
- 评论驱动：按评论 / 点赞排序

点击“看证据”后打开视频轻详情抽屉，再跳转任务中心完整拆解。

### 3.4 博主对标

HTML demo 中展示 Top 博主：

```text
微安塔罗 / 栖栖塔罗CC / 彼得塔罗
```

该模块回答：

```text
这个类型里，哪些博主值得作为学习对象？
他值得学的点是什么？
从哪几条视频开始学？
```

每个博主展示：

- 头像或首字
- 昵称
- 简短定位
- 看视频按钮

点击后进入该博主代表视频列表或筛选排行榜为该博主。

### 3.5 内容模式库

HTML demo 中展示：

```text
刷到就是私占
守护灵提醒
```

模式库不是单条视频详情，而是把多条视频拆解沉淀成可复用内容公式。

模式来源字段：

- `result.core_hook.opening_3s`
- `result.core_hook.curiosity_gap`
- `result.core_hook.emotional_trigger`
- `result.need_context.pain_point`
- `result.copywriting_formula.title_formula`
- `result.copywriting_formula.script_formula`
- `result.copywriting_formula.cta`
- `result.replication_plan.pattern_name`
- `result.replication_plan.reusable_formula`
- `result.psychology_breakdown.replicable_point`

第一版可先做规则聚类：

- 标题/描述包含“私占、刷到、有缘” -> 刷到就是私占
- 包含“守护灵、提醒、讯息” -> 守护灵提醒
- 包含“正缘、桃花、他/她、关系” -> 情感关系预测
- 包含“好运、转运、大运、近期” -> 运势转机
- 包含“教学、牌意、教程、牌阵” -> 塔罗教学收藏

后续再引入 AI 聚类和人工编辑。

### 3.6 类型迁移

HTML demo 中展示：

```text
动漫解说：冲突、爽点、人物命运
原创 Vlog：人设、场景、真实情绪
好物种草：痛点、信任、转化路径
```

这部分的意义是告诉产品和工程：当前不是塔罗专用系统，而是通用短视频对标系统。

类型迁移字段建议：

| 类型 | 主要分析维度 |
|---|---|
| 玄学塔罗 | 私占感、关系预测、情绪承诺、复看收藏 |
| 动漫解说 | 冲突、爽点、人物命运、解说节奏 |
| 原创 Vlog | 人设、场景、真实情绪、生活冲突 |
| 好物种草 | 痛点、信任、利益点、转化路径 |
| 知识教程 | 问题场景、步骤结构、收藏价值、专业背书 |

### 3.7 指标说明

HTML demo 中明确写了：

```text
互动强度指数是可配置排序指标，不是科学定律。
点赞、评论、收藏、分享分别保留；综合分只用于快速粗排。
```

这条必须保留。任何综合分都不能替代原始指标展示。

## 4. 指标体系

### 4.1 原始公开指标

第一版必须单独展示：

- 点赞数
- 评论数
- 收藏数
- 分享数
- 粉丝数
- 作者作品数
- 作者获赞数
- 发布时间

### 4.2 代理指标

在播放量缺失或不可信时，使用相对行为倾向：

```text
收藏倾向 = 收藏数 / 点赞数
评论倾向 = 评论数 / 点赞数
分享倾向 = 分享数 / 点赞数
公开互动强度 = 点赞 + 评论 * 3 + 收藏 * 4 + 分享 * 5
粉丝效率 = 公开互动强度 / 粉丝数
```

说明：

- `公开互动强度` 只作为排序辅助。
- 权重可配置，默认值不是科学定律。
- 收藏、评论、分享要分别展示。
- 后续接入真实播放/留存数据后，再切换到完整健康评估。

### 4.3 AI 指标

直接使用拆解结果中的：

- `viral_scores.viral_potential`
- `viral_scores.imitation_value`
- `viral_scores.commerce_value`
- `viral_scores.comment_potential`
- `viral_scores.overall`

建议用途：

- 平均复刻分：取 `imitation_value`
- 内容模式价值：结合 `imitation_value`、`commerce_value`
- 视频轻详情：展示 `overall` 和 `replication_plan`

### 4.4 与 2026 内容健康框架的关系

用户提供的优先序：

```text
收藏率 > 复访率 > 铁粉互动 > 5秒完播/3秒留存 > 整体完播率 > 评论质量 > 点赞率 > 转发率
```

当前竞品对标版处理方式：

- 收藏优先：用收藏倾向代理
- 复访率：竞品不可见，标记缺失
- 铁粉互动：竞品不可见，标记缺失
- 留存/完播：竞品不可见，标记缺失
- 评论质量：第一版可用评论采集和 AI 分析补充，数据不足时不打分
- 点赞/转发：保留为低优先级公开指标

评级策略：

```text
可完整评级：自有账号数据齐全时使用
可代理评级：竞品公开数据 + AI 拆解时使用
不可评级：关键字段不足时使用
```

## 5. 技术实现架构

### 5.1 总体架构

```text
Job JSON / Evidence
        |
        v
Benchmark Indexer
        |
        v
Normalized Benchmark Dataset
        |
        v
FastAPI Benchmark API
        |
        v
React Benchmark Dashboard
        |
        v
Task Center / Analysis Detail
```

第一版可以先不落正式业务库，但不能在每个 API 请求里全量扫描 JSON。考虑到近期预计会增长到约 2000 条视频、200 个用户，推荐采用“启动/手动/定时重建索引 + API 读索引”的模式。

```text
Job JSON / Evidence
        |
        v
Incremental Benchmark Indexer
        |
        v
In-memory Index + Disk Cache
        |
        v
Paginated Benchmark API
        |
        v
React Dashboard
```

第一版使用内存索引加磁盘缓存即可，第二版再落 SQLite/Postgres。

建议缓存文件：

```text
data/runtime/benchmark_index/videos.json
data/runtime/benchmark_index/authors.json
data/runtime/benchmark_index/patterns.json
data/runtime/benchmark_index/overview.json
data/runtime/benchmark_index/index_meta.json
```

`index_meta.json` 记录：

- 上次索引时间
- 已处理 job 文件数量
- 每个 job 文件的 `mtime`、`size` 或 hash
- 去重视频数
- 作者数
- 索引版本
- 指标权重版本

触发重建：

- 后端启动时：如果缓存存在且未过期，直接加载缓存
- 手动点击：`POST /api/benchmark/reindex`
- 定时刷新：每 5-15 分钟扫描新增/变更 job
- 任务完成事件：后续可由 AI 拆解任务完成后触发局部更新

### 5.2 后端模块

建议新增：

```text
backend/app/benchmark_index.py
backend/app/benchmark_metrics.py
backend/app/benchmark_patterns.py
backend/app/routes/benchmark.py
```

职责：

- `benchmark_index.py`
  - 扫描 job JSON
  - 按 `aweme_id` 去重视频
  - 按 author 聚合博主
  - 建立 video -> job -> evidence 映射
  - 支持增量索引，只处理新增或变更 job 文件
  - 写入 `data/runtime/benchmark_index/*.json` 缓存

- `benchmark_metrics.py`
  - 计算总览统计
  - 计算排行榜指标
  - 计算收藏倾向、评论倾向、分享倾向
  - 计算粉丝效率
  - 预计算列表排序字段，避免请求时重复计算

- `benchmark_patterns.py`
  - 从 AI 拆解字段提取内容模式
  - 做第一版规则归类
  - 返回模式卡和代表视频

- `routes/benchmark.py`
  - 提供总览、排行榜、博主、模式库、轻详情接口
  - 列表接口必须分页，不一次性返回全部视频

### 5.2.1 2000 视频规模下的性能约束

2000 条视频、200 个博主对后端计算压力不大，但文件数量和前端渲染会变成主要风险。

必须遵守：

- 列表接口默认 `limit=20`，最大 `limit=100`。
- 排行榜、博主列表、模式库都读索引缓存，不在请求内扫描 job 目录。
- 列表接口不读取完整 evidence、不读取关键帧图片、不读取完整转写。
- 视频轻详情只读取单条 job 的摘要字段。
- 任务中心才读取完整 evidence、分段、关键帧。
- 前端列表使用分页或“加载更多”，避免一次渲染 2000 张卡片。
- 排序字段在索引阶段预计算，API 只做过滤、切片和返回。

建议预计算排序字段：

- `public_engagement_score`
- `small_account_efficiency`
- `collect_tendency`
- `comment_tendency`
- `share_tendency`
- `imitation_value`
- `overall_score`
- `risk_level`
- `content_type`
- `author_id`
- `publish_time`

缓存大小预期：

- 2000 条视频摘要 JSON 通常可控制在数 MB 到十几 MB。
- evidence、关键帧、音频、视频文件不进入索引缓存，只保存路径。

### 5.3 API 设计

第一版接口：

```text
GET /api/benchmark/overview
GET /api/benchmark/videos
GET /api/benchmark/videos/{video_id}
GET /api/benchmark/authors
GET /api/benchmark/authors/{author_id}
GET /api/benchmark/patterns
GET /api/benchmark/filters
POST /api/benchmark/reindex
```

#### GET /api/benchmark/overview

返回：

```json
{
  "analysis_task_count": 148,
  "unique_video_count": 112,
  "author_count": 38,
  "segment_count": 1040,
  "avg_imitation_value": 89
}
```

#### GET /api/benchmark/videos

查询参数：

```text
genre
rank_type=overall|small_account|collect|comment
author_id
q
sort
limit
offset
```

返回：

```json
{
  "items": [
    {
      "video_id": "7390672737380961576",
      "aweme_id": "7390672737380961576",
      "job_id": "target-breakdown-...",
      "task_id": "",
      "desc": "通灵占卜 金桃花的长相？",
      "author_id": "sec_uid_or_uid",
      "author_name": "微安塔罗",
      "digg_count": 560722,
      "comment_count": 54535,
      "collect_count": 81808,
      "share_count": 114204,
      "collect_tendency": 0.146,
      "comment_tendency": 0.097,
      "share_tendency": 0.204,
      "public_engagement_score": 1622579,
      "imitation_value": 92,
      "overall_score": 93
    }
  ],
  "total": 112
}
```

约束：

- 默认 `limit=20`。
- 最大 `limit=100`。
- 返回列表摘要，不返回完整 evidence、完整分段、完整转写。
- 排序使用索引阶段预计算字段。

#### GET /api/benchmark/videos/{video_id}

返回视频轻详情：

```json
{
  "video": {},
  "author": {},
  "metrics": {},
  "summary": "",
  "opening_3s": "",
  "replicable_point": "",
  "replication_action": "",
  "risk_level": "",
  "task_id": "",
  "job_id": "",
  "evidence_path": "",
  "task_center_url": ""
}
```

#### GET /api/benchmark/authors

返回博主对标：

```json
{
  "items": [
    {
      "author_id": "sec_uid_or_uid",
      "nickname": "微安塔罗",
      "avatar_url": "",
      "positioning": "私占感强，收藏与分享高",
      "sample_count": 10,
      "follower_count": 302163,
      "avg_collect_tendency": 0.146,
      "avg_comment_tendency": 0.097,
      "avg_share_tendency": 0.204,
      "avg_imitation_value": 92,
      "representative_video_ids": []
    }
  ]
}
```

查询参数：

```text
genre
sort=benchmark|collect|comment|small_account|imitation
min_samples
limit
offset
```

该接口同样分页返回，默认 `limit=20`，最大 `limit=100`。

#### GET /api/benchmark/patterns

返回内容模式库：

```json
{
  "items": [
    {
      "pattern_id": "private-reading",
      "name": "刷到就是私占",
      "description": "强缘分暗示 + 情绪承诺 + 评论/私信引导",
      "content_type": "玄学塔罗",
      "representative_video_ids": [],
      "avg_imitation_value": 90
    }
  ]
}
```

#### POST /api/benchmark/reindex

用于手动重建或增量刷新索引。

请求：

```json
{
  "mode": "incremental"
}
```

`mode` 可选：

- `incremental`：只处理新增/变更 job，默认
- `full`：全量重建索引

返回：

```json
{
  "status": "done",
  "processed_jobs": 2000,
  "new_jobs": 120,
  "unique_videos": 1986,
  "authors": 203,
  "duration_ms": 1800
}
```

### 5.4 前端结构

建议新增：

```text
src/features/benchmark/
  index.jsx
  BenchmarkDashboard.jsx
  BenchmarkFilters.jsx
  BenchmarkOverviewCards.jsx
  BenchmarkVideoRanking.jsx
  BenchmarkAuthorPanel.jsx
  BenchmarkPatternLibrary.jsx
  BenchmarkMigrationPanel.jsx
  BenchmarkMetricNotes.jsx
  BenchmarkVideoDrawer.jsx
  benchmarkUtils.js
```

API 方法加入：

```text
src/services/api.js
```

组件关系：

```text
BenchmarkDashboard
  BenchmarkFilters
  BenchmarkOverviewCards
  BenchmarkVideoRanking
  BenchmarkAuthorPanel
  BenchmarkPatternLibrary
  BenchmarkMigrationPanel
  BenchmarkMetricNotes
  BenchmarkVideoDrawer
```

### 5.5 数据归一化规则

作者 ID 优先级：

```text
author.sec_uid
author.sec_user_id
author.uid
author.user_id
author.id
nickname fallback
```

视频去重优先级：

```text
video.aweme_id
video.id
job_id fallback
```

同一视频多次拆解：

- 默认保留最新 job
- 保留所有 job_id 作为历史记录
- 排行榜指标使用最新 job 的 `video` 数据
- AI 指标使用最新 job，后续可升级为最高质量 run

## 6. 与任务中心联动

视频轻详情抽屉只展示决策摘要，不重做完整拆解页。

展示：

- 视频基础信息
- 作者信息
- 公开互动指标
- AI 摘要
- 开头 3 秒
- 可复刻点
- 风险提示
- 打开任务中心完整拆解

跳转优先级：

```text
task_id -> 任务中心任务详情
job_id -> AI 视频分析结果详情
evidence_path -> evidence 只读结果
aweme_id -> 搜索相关任务
```

## 7. 实施阶段

### P0：HTML 线框确认

已完成：

```text
docs/benchmark-dashboard-wireframe.html
```

验收：

- 当前页面结构被确认
- 模块包括总览、排行榜、博主对标、模式库、类型迁移、指标说明、轻详情

### P1：后端索引与只读 API

交付：

- job JSON 扫描器
- 增量索引器
- 磁盘索引缓存
- 视频去重索引
- 作者聚合索引
- 模式库规则提取
- 总览统计
- 排行榜计算
- 轻详情接口
- 分页列表接口

验收：

- 能返回约 148 条任务、112 个去重视频、38 个博主
- 当数据增长到约 2000 视频、200 博主时，列表接口仍然分页返回
- 普通列表请求不读取完整 evidence
- 重建索引后 overview、videos、authors、patterns 一致更新
- 能按内容类型筛选
- 能切换 4 个排行榜
- 能打开视频轻详情

### P2：前端工作台

交付：

- 内容类型筛选
- 总览指标卡
- 内容排行榜
- 博主对标
- 内容模式库
- 类型迁移
- 指标说明
- 视频轻详情抽屉
- 任务中心跳转
- 分页或“加载更多”

验收：

- 页面结构与 HTML demo 一致
- 用户能从排行榜进入轻详情
- 用户能从博主模块筛到对应视频
- 用户能从轻详情跳到任务中心完整拆解
- 页面面对 2000 条视频索引时不一次性渲染全部列表

### P3：指标配置化

状态：已完成首版。

交付：

- 公开互动强度权重配置
- 指标说明文案
- 缺失指标提示
- 手动重建索引入口
- 索引状态展示：最近更新时间、视频数、博主数、处理任务数

验收：

- 权重调整后排行榜变化可见
- 页面明确区分原始指标、代理指标、AI 指标、缺失指标
- 用户能看到当前页面使用的是哪一次索引结果

当前实现：

- 新增 `GET /api/benchmark/metric-config`
- 新增 `PUT /api/benchmark/metric-config`
- 指标权重保存在 `data/runtime/benchmark_index/metric_config.json`
- 修改权重后会触发全量重建索引，避免旧视频沿用旧权重
- 索引响应对前端隐藏 `job_files` 明细，只保留列表页需要的状态字段
- 前端展示最近索引时间、视频数、博主数、任务数、权重版本

### P3.5：博主对标详情

状态：已完成首版。

交付：

- 博主对标列表拆分为“详情”和“看视频”两个动作
- “详情”打开博主对标抽屉
- “看视频”筛选内容排行榜为该博主的视频
- 博主详情展示样本任务数、去重视频数、粉丝数、收藏倾向、评论倾向、对标分
- 博主详情展示学习点、常见开头、代表视频
- 代表视频可继续打开视频轻详情

验收：

- 用户能先选博主，再看该博主值得学什么
- 用户能从博主详情跳到代表视频证据
- 用户能把排行榜聚焦到某个博主的视频集合

### P4：竞品不可见指标降级

状态：已调整为“公开竞品对标”口径。

竞品账号无法稳定获得：

- 播放量
- 3 秒留存
- 5 秒完播
- 整体完播率
- 2 秒跳出率
- 复访率
- 铁粉互动

因此本功能不再提供后台指标录入、S/A/B/C 健康评级和 `health_rating`。这些指标只适合自有账号后台复盘，不进入对标账号评分。

当前实现：

- 后台移除对外的 `private-metrics` 写入接口
- 索引结果不再写入 `private_metrics`、`private_metrics_available`、`health_rating`
- 总览改为 `public_signal_video_count`、`comment_quality_video_count`
- 指标配置明确 `evaluation_scope=public_competitor_only`
- 前端把“后台指标/健康评级”改为“公开信号/对标依据”
- 视频轻详情只展示公开互动、收藏/评论/分享倾向、评论质量和 AI 拆解证据
- 从 job JSON 中提取评论样本，计算有效评论、长评、提问、重复/刷屏风险和评论质量分
- 内容模式库支持规则聚类 + AI 拆解字段聚类
- 内容模式支持人工编辑名称、描述和备注，覆盖保存在 `data/runtime/benchmark_index/pattern_overrides.json`
- 前端内容模式库支持打开详情、编辑模式、查看代表开头和代表视频

## 8. 第一版最小闭环

第一版优先做：

```text
总览指标
内容排行榜
博主对标
内容模式库
视频轻详情
任务中心跳转
```

暂缓：

```text
自有账号后台复盘模块
数据健康页
复杂图表
指标训练/自动校准
```

第一版完成后，用户能完成核心动作：

```text
看到这批数据总体规模
找到值得研究的视频
知道对应博主是谁
沉淀可复用内容模式
进入任务中心看完整拆解证据
```
