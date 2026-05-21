# 抖音对标工具计划文档

## 1. 目标

新增一个“抖音对标”前端工具，围绕 TikHub 的抖音搜索和作品接口，完成从关键词发现达人、筛选候选对标账号、沉淀到待对标数据库、批量选择对标视频、进入 AI 视频拆解任务池、再把拆解结果回写数据库的闭环。

核心场景：

1. 用户输入关键词，例如“可爱”。
2. 系统通过 TikHub 搜索相关抖音用户。
3. 用户在前端按粉丝量区间、总点赞数、视频数区间、最近更新区间等条件筛选。
4. 用户选择一批账号，保存到“待对标数据库”。
5. 用户从待对标库中选择账号，并设置每个账号抓取哪些视频。
6. 系统批量拉取目标账号视频，按规则选择对标视频。
7. 选中的视频进入 AI 拆解任务池，按并发限制逐个拆解。
8. 拆解完成后，任务结果回写到对标数据库，供后续查看、归档、比较和内容创作参考。

## 2. 当前代码现状

### 2.1 已有 TikHub 适配器

文件：

- `integrations/tikhub_douyin_api/adapter.py`
- `backend/app/routes/tikhub_douyin.py`
- `backend/app/routes/douyin_target.py`

已有能力：

- `TikhubDouyinApiAdapter.search_users()`：调用 TikHub 用户搜索接口。
- `TikhubDouyinApiAdapter.get_user_videos()`：调用 TikHub 用户作品接口。
- `TikhubDouyinApiAdapter.get_one_video()`：调用 TikHub 单视频详情接口。
- `/api/tools/douyin-target/search`：已有对标搜索雏形。
- `/api/tools/douyin-target/users`：已有候选用户入库接口。
- `/api/tools/douyin-target/users/videos`：已有拉取用户视频接口。
- `/api/tools/douyin-target/videos`：已有视频入库接口。

### 2.2 已有数据库雏形

文件：

- `backend/app/tiktok_target_store.py`

已有表：

- `tiktok_target_users`：对标用户表。
- `tiktok_target_sets`：对标集合表，也就是前端的“合集”。
- `tiktok_target_set_users`：集合和用户关联表。
- `tiktok_target_videos`：对标视频表。
- `tiktok_target_tasks`：对标拆解任务关联表。

这些表已经覆盖了“用户池、集合、视频、任务关联”的大方向，但字段和接口还不够完整。

### 2.3 已有 AI 视频拆解任务池

文件：

- `backend/app/routes/ai_video_analysis.py`
- `backend/app/task_store.py`
- `backend/app/video_task_limiter.py`

已有能力：

- `/api/tools/ai-video-analysis/jobs`：创建单个视频拆解任务。
- `tasks`（PostgreSQL）：保存通用任务、任务事件、拆解结果。
- 通过 `AI_VIDEO_MAX_CONCURRENT_TASKS` 控制视频拆解并发。
- 前端已有任务中心展示进行中、已完成、异常任务。

这部分可以直接复用，新的对标工具只需要批量创建任务，并维护“目标视频和任务结果”的关联。

## 3. 当前缺口和风险

### 3.1 TikHub 路由和适配器参数不一致

`backend/app/routes/tikhub_douyin.py` 调用：

```python
adapter().search_users(
    keyword=payload.keyword,
    offset=payload.offset,
    count=payload.count,
    user_search_follower_count=payload.user_search_follower_count,
    user_search_profile_type=payload.user_search_profile_type,
    user_search_other_pref=payload.user_search_other_pref,
)
```

但 `TikhubDouyinApiAdapter.search_users()` 当前签名是：

```python
search_users(keyword, page=1, userType="", douyin_user_fans="")
```

结果是 `/api/integrations/tikhub/douyin/user-search` 现在会因为未知参数报错。需要先统一 TikHub 搜索参数模型。

### 3.2 TikHub 搜索结果归一化不完整

`tikhub_sample.json` 中用户数据结构是：

```json
{
  "user_info": {
    "sec_uid": "...",
    "unique_id": "...",
    "nickname": "...",
    "follower_count": 15586,
    "total_favorited": 2299080,
    "aweme_count": 353
  }
}
```

但当前 `_normalize_user(item)` 直接从 `item` 读取字段，没有优先解包 `item.user_info`。这会导致搜索结果里的 `sec_uid`、昵称、粉丝量等字段为空。

### 3.3 当前筛选逻辑会误过滤

`/api/tools/douyin-target/search` 当前从 `item.raw.total_favorited`、`item.raw.create_time`、`item.raw.last_post_time` 取数据。但 TikHub 样例里的点赞数和作品数在 `raw.user_info` 下，最近更新字段也不一定直接存在。

如果 `recentOnly=True`，当前逻辑很可能把大部分结果过滤掉。

### 3.4 视频表 upsert 有字段错误

`backend/app/tiktok_target_store.py` 的 `create_target_video()` 更新语句中有：

```sql
updated = excluded.updated_at
```

但表字段是 `updated_at`，不是 `updated`。视频重复入库时会报错。需要改成：

```sql
updated_at = excluded.updated_at
```

### 3.5 对标任务表还没有完整读写接口

`tiktok_target_tasks` 已建表，但缺少：

- 创建对标拆解任务关联。
- 查询某个 set/user/video 的拆解状态。
- 把 AI 拆解任务完成结果回写到目标视频。
- 批量重试、跳过、取消、重新拆解。

### 3.6 前端还没有对标工具入口

当前前端主要是“抖音采集”和“AI 拆解”工具。还没有：

- 对标关键词搜索页。
- 对标用户筛选列表。
- 待对标用户数据库页。
- 视频选择策略配置。
- 批量拆解任务入口。
- 对标结果库。

## 4. 产品流程设计

### 4.1 关键词搜索

输入：

- 关键词：必填，例如“可爱”。
- 搜索页数：默认 1 页，可设置 1 到 10 页。
- 每页数量：默认 20。
- TikHub 原生筛选：如粉丝区间、用户类型等，如果 TikHub 支持则透传。

输出：

- 用户头像、昵称、抖音号、简介。
- 粉丝量。
- 总点赞数。
- 视频数。
- 认证状态。
- 最近更新时间或最近作品时间。
- 原始 TikHub 响应，便于排错和后续字段补齐。

### 4.2 前端筛选

筛选项建议：

- 粉丝量区间：1-5W、5-10W、10-20W、20-50W、50W以上。
- 总点赞区间：可保留为补充筛选，不作为必填项。
- 视频数区间：0-50、50-100、100-500、500以上。
- 最近更新：一周以内、一个月以内、半年以内、一年以内、一年以上。
- 认证状态：不限、仅认证、排除认证。
- 私密账号：不限、排除私密。
- 排序：相关性、粉丝量降序、点赞数降序、视频数降序、最近更新降序。
- 不再设置单独保存上限，保存动作只围绕合集展开。

前端筛选用于快速交互，后端也要支持同样筛选，保证批量保存时结果一致。

### 4.3 保存到待对标数据库

用户可执行：

- 单个保存账号。
- 勾选多个账号保存。
- 保存当前筛选结果到一个合集。
- 新建合集、修改合集、删除合集。
- 追加账号到已有合集。

入库时需要做去重：

- 优先用 `sec_uid` 作为用户主键。
- 没有 `sec_uid` 时用 `uid`。
- 再不行用 `unique_id`。
- 同一个集合中同一个用户只能出现一次。

用户状态建议：

- `candidate`：候选。
- `selected`：已选为对标。
- `ignored`：已忽略。
- `archived`：已归档。

### 4.4 选择对标视频

对每个对标用户，用户可以选择视频策略：

- 最高数据量视频：按点赞、评论、分享、收藏或综合热度排序取前 N 个。
- 置顶视频：优先取用户置顶视频。
- 最近视频：取最近 N 个。
- 手动选择：展示视频列表后勾选。
- 混合策略：例如置顶 1 个，加爆款前 3 个，加最近 2 个。

每个用户视频数量：

- 默认 3 到 5 个。
- 支持设置全局数量。
- 支持对单个用户覆盖数量。

视频需要保存：

- `aweme_id`
- 描述、封面、播放地址、下载地址。
- 创建时间。
- 点赞、评论、分享、收藏、播放量，如接口有返回。
- 是否置顶。
- 视频选择策略。
- 所属用户和所属集合。
- 原始 TikHub JSON。

### 4.5 批量进入 AI 拆解任务池

开始拆解时：

1. 读取选中的集合、用户和视频。
2. 对每个视频创建或复用 `tiktok_target_videos` 记录。
3. 对未拆解或需要重试的视频创建 `/api/tools/ai-video-analysis/jobs` 任务。
4. 在 `tiktok_target_tasks` 中记录 `target_video_id -> ai_task_id` 的关联。
5. 由现有 AI 视频拆解任务池按并发限制一个一个处理。

去重规则：

- 同一个 `target_video_id` 已有 `pending/running/done` 任务时，默认不重复创建。
- 用户可以选择“强制重新拆解”，生成新任务并把旧任务标记为 `superseded`。

### 4.6 结果回写

任务完成后需要同步：

- 从 PostgreSQL 的 `tasks` 读取 AI 拆解任务状态和结果。
- 更新 `tiktok_target_tasks.status/result_json/error`。
- 更新 `tiktok_target_videos.analysis_status/analysis_result_json/analysis_task_id/analyzed_at`。

同步方式：

- MVP 可用前端轮询触发 `/api/tools/douyin-target/tasks/sync`。
- 后续可在任务完成时自动回调或在后端定时同步。

## 5. 建议数据模型

### 5.1 对标用户表

基于 `tiktok_target_users` 扩展：

```sql
ALTER TABLE tiktok_target_users ADD COLUMN avatar_url TEXT NOT NULL DEFAULT '';
ALTER TABLE tiktok_target_users ADD COLUMN signature TEXT NOT NULL DEFAULT '';
ALTER TABLE tiktok_target_users ADD COLUMN aweme_count INTEGER;
ALTER TABLE tiktok_target_users ADD COLUMN following_count INTEGER;
ALTER TABLE tiktok_target_users ADD COLUMN is_private INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tiktok_target_users ADD COLUMN last_post_at INTEGER;
ALTER TABLE tiktok_target_users ADD COLUMN searched_at INTEGER;
```

说明：

- `like_count` 存总点赞数。
- `aweme_count` 存视频数。
- `recent_update_at` 可继续保留，建议语义改成最近活跃时间。
- `last_post_at` 存最近作品发布时间。

### 5.2 对标集合表

基于 `tiktok_target_sets` 扩展：

```sql
ALTER TABLE tiktok_target_sets ADD COLUMN keyword TEXT NOT NULL DEFAULT '';
ALTER TABLE tiktok_target_sets ADD COLUMN filters_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE tiktok_target_sets ADD COLUMN video_strategy_json TEXT NOT NULL DEFAULT '{}';
```

说明：

- 一个集合就是一次对标项目。
- 保存搜索关键词、筛选条件和视频选择策略，方便复盘。

### 5.3 对标视频表

基于 `tiktok_target_videos` 扩展：

```sql
ALTER TABLE tiktok_target_videos ADD COLUMN set_id TEXT NOT NULL DEFAULT '';
ALTER TABLE tiktok_target_videos ADD COLUMN create_time INTEGER;
ALTER TABLE tiktok_target_videos ADD COLUMN digg_count INTEGER;
ALTER TABLE tiktok_target_videos ADD COLUMN comment_count INTEGER;
ALTER TABLE tiktok_target_videos ADD COLUMN share_count INTEGER;
ALTER TABLE tiktok_target_videos ADD COLUMN collect_count INTEGER;
ALTER TABLE tiktok_target_videos ADD COLUMN play_count INTEGER;
ALTER TABLE tiktok_target_videos ADD COLUMN is_top INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tiktok_target_videos ADD COLUMN selection_strategy TEXT NOT NULL DEFAULT '';
ALTER TABLE tiktok_target_videos ADD COLUMN analysis_status TEXT NOT NULL DEFAULT 'none';
ALTER TABLE tiktok_target_videos ADD COLUMN analysis_task_id TEXT NOT NULL DEFAULT '';
ALTER TABLE tiktok_target_videos ADD COLUMN analysis_result_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE tiktok_target_videos ADD COLUMN analyzed_at INTEGER;
```

说明：

- `analysis_status` 可取 `none/pending/running/done/failed/superseded`。
- `analysis_result_json` 保存 AI 拆解结果快照，减少跨库查询成本。

### 5.4 对标任务表

基于 `tiktok_target_tasks` 扩展：

```sql
ALTER TABLE tiktok_target_tasks ADD COLUMN strategy TEXT NOT NULL DEFAULT '';
ALTER TABLE tiktok_target_tasks ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tiktok_target_tasks ADD COLUMN synced_at INTEGER;
```

说明：

- 继续保留 `task_id` 指向通用 `tasks` 表。
- `result_json` 保存通用任务结果快照。

## 6. 后端接口计划

### 6.1 TikHub 集成层

修复并统一：

- `POST /api/integrations/tikhub/douyin/user-search`
- `POST /api/integrations/tikhub/douyin/user-videos`
- `POST /api/integrations/tikhub/douyin/one-video`

建议请求模型：

```json
{
  "keyword": "可爱",
  "page": 1,
  "count": 20,
  "user_type": "",
  "follower_filter": ""
}
```

适配器需要：

- 支持 TikHub 当前接口参数。
- 兼容旧的 `offset/count` 入参。
- 正确解包 `user_info`。
- 补齐 `like_count`、`aweme_count`、`last_post_at`、`is_private`。
- 保留 `raw` 字段。

### 6.2 对标工具接口

建议新增或完善：

```http
POST /api/tools/douyin-target/search
POST /api/tools/douyin-target/users/bulk-save
GET  /api/tools/douyin-target/users
PATCH /api/tools/douyin-target/users/{user_id}

POST /api/tools/douyin-target/sets
GET  /api/tools/douyin-target/sets
GET  /api/tools/douyin-target/sets/{set_id}
POST /api/tools/douyin-target/sets/{set_id}/users
DELETE /api/tools/douyin-target/sets/{set_id}/users/{user_id}

POST /api/tools/douyin-target/videos/collect
GET  /api/tools/douyin-target/videos
PATCH /api/tools/douyin-target/videos/{video_id}

POST /api/tools/douyin-target/analysis/enqueue
GET  /api/tools/douyin-target/analysis/tasks
POST /api/tools/douyin-target/analysis/sync
POST /api/tools/douyin-target/analysis/retry
```

重点接口说明：

`POST /search`

- 调用 TikHub 搜索。
- 后端执行筛选、排序、截断。
- 返回可直接保存的规范化用户列表。

`POST /users/bulk-save`

- 保存勾选用户或筛选结果到合集。
- 可同时创建或追加到现有合集。

`POST /videos/collect`

- 输入 set_id、user_ids、视频策略。
- 拉取用户视频。
- 按策略选择视频。
- 保存到 `tiktok_target_videos`，并把视频挂到对应合集下。

`POST /analysis/enqueue`

- 输入 set_id、video_ids 或筛选条件。
- 批量创建 AI 视频拆解任务。
- 写入 `tiktok_target_tasks`。

`POST /analysis/sync`

- 同步通用任务池状态和结果。
- 回写对标任务表和视频表。

## 7. 前端页面计划

### 7.1 新工具入口

新增导航或工具卡：

- 名称：抖音对标
- 位置：建议放在主导航，和“抖音采集”平级，或放在“工具中心”中作为可打开工具。
- 功能定位：从关键词批量发现对标账号，并把账号视频送入 AI 拆解流水线。

### 7.2 页面结构

建议一个页面拆成四个工作区：

1. 搜索发现
2. 待对标库
3. 视频选择
4. 拆解任务与结果

### 7.3 搜索发现区

组件：

- 关键词输入框。
- 搜索按钮。
- TikHub 状态提示。
- 筛选面板。
- 排序和合集管理。
- 用户结果表格。

表格字段：

- 头像、昵称、抖音号。
- 粉丝量、总点赞、视频数。
- 最近更新。
- 认证、私密。
- 操作：保存、忽略、查看原始 JSON。

### 7.4 待对标库区

组件：

- 对标集合列表。
- 集合详情。
- 已选用户表。
- 用户状态切换。
- 批量移除、批量归档。

重点交互：

- 从搜索结果保存后自动进入当前合集。
- 同一个账号再次保存时更新指标，不重复新增。

### 7.5 视频选择区

组件：

- 选择集合和用户。
- 视频策略配置。
- 候选视频池。
- 视频列表。
- 手动勾选视频。

策略控件：

- 每个用户视频数：3、5、10、自定义。
- 选择方式：最高数据、置顶、最近、混合、手动。
- 热度指标：点赞、评论、分享、收藏、综合分。

### 7.6 拆解任务与结果区

组件：

- 开始拆解按钮。
- 任务状态列表。
- 每个账号拆解进度。
- 每个视频状态。
- 拆解结果预览。
- 重试失败任务。

展示：

- 总视频数。
- 已排队、进行中、已完成、失败数量。
- 当前并发限制。
- 最近一次同步时间。

## 8. AI 拆解结果结构建议

对标库中结果需要适合后续横向比较，建议在保留现有 AI 拆解原始结果的同时，增加一层摘要字段：

```json
{
  "summary": "",
  "hook": "",
  "content_structure": [],
  "visual_style": "",
  "editing_rhythm": "",
  "audio_strategy": "",
  "copywriting_patterns": [],
  "conversion_points": [],
  "replicable_points": [],
  "risk_notes": []
}
```

这层可以在 AI 拆解 prompt 里要求输出，也可以后续做二次归纳。

## 9. 实施阶段

### 阶段一：修复接口和数据归一化

目标：让 TikHub 搜索和对标搜索可用。

任务：

- 修复 `tikhub_douyin.py` 路由参数和适配器签名不一致。
- `_normalize_user()` 支持 `user_info`。
- 提取 `total_favorited`、`aweme_count`、`last_post_at`、`is_private`。
- 修复 `create_target_video()` 的 `updated_at` 字段错误。
- 给 `/api/tools/douyin-target/search` 增加视频数、点赞数、最近更新筛选。

验收：

- 输入“可爱”能返回规范化用户。
- 筛选粉丝、点赞、视频数不会误删全部结果。
- 用户和视频可重复保存且不报错。

### 阶段二：完善对标数据库接口

目标：打通“搜索结果入库”和“集合管理”。

任务：

- 增加 bulk save。
- 增加 sets 列表和详情。
- 增加集合内用户管理。
- 扩展用户表和集合表字段。
- 返回结构中解包 `source_json`，前端无需自己解析字符串。

验收：

- 可创建“可爱赛道”集合。
- 可把筛选后的前 N 个账号保存到集合。
- 集合详情能显示所有账号和关键指标。

### 阶段三：视频选择和入库

目标：按策略为对标账号选择视频。

任务：

- 增加 `/videos/collect`。
- 支持最高数据、置顶、最近、混合、手动选择。
- 扩展视频表字段。
- 保存选择策略。

验收：

- 每个账号可自动选出 3 到 5 条视频。
- 可手动调整选中视频。
- 视频重复采集可更新指标，不重复创建。

### 阶段四：批量拆解任务

目标：让选中视频进入现有 AI 拆解任务池。

任务：

- 增加 `/analysis/enqueue`。
- 写入 `tiktok_target_tasks`。
- 复用 `/api/tools/ai-video-analysis/jobs` 的后台执行逻辑。
- 增加任务去重和强制重跑。

验收：

- 一次可为多个用户、多个视频创建拆解任务。
- 任务中心能看到对应 AI 拆解任务。
- 对标工具页面能看到每条视频的拆解状态。

### 阶段五：结果回写和对标结果库

目标：完成从任务池回到对标库的闭环。

任务：

- 增加 `/analysis/sync`。
- 同步 `tasks` 表中的状态和结果。
- 回写到 `tiktok_target_tasks` 和 `tiktok_target_videos`。
- 前端展示每条视频的拆解结果。
- 支持按账号、集合、关键词查看拆解结果。

验收：

- 拆解完成的视频在对标库中显示结果。
- 失败任务可重试。
- 用户可以按集合查看全部对标视频的 AI 拆解摘要。

## 10. MVP 范围建议

第一版建议只做这些：

- 关键词搜索。
- 粉丝量、点赞量、视频数筛选。
- 保存筛选结果到合集。
- 对每个用户先拉取候选视频池，默认 20 条。
- 按点赞数取前 3 到 5 条。
- 批量创建 AI 视频拆解任务。
- 手动点击同步任务结果。
- 在对标库中查看拆解状态和结果。

暂不做：

- 很复杂的达人画像评分。
- 多关键词自动巡检。
- 自动定时更新。
- 跨集合对比大盘。
- 自动生成选题或脚本。

## 11. 后续增强方向

- 对标账号评分：粉丝量、点赞率、更新频率、爆款率、内容垂直度。
- 视频热度综合分：点赞、评论、收藏、分享按权重计算。
- 批量刷新账号数据：更新粉丝、点赞、最新作品。
- 对标结果聚合：总结一个集合的共性钩子、结构、镜头、标题套路。
- 与脚本生成联动：从对标结果生成选题、脚本、分镜和剪映草稿。
- 与素材库联动：把拆解中的优秀镜头、音频、字幕风格沉淀为素材。

## 12. 推荐优先级

最高优先级：

1. 修复 TikHub 搜索接口参数不一致。
2. 修复 TikHub 用户结果归一化。
3. 修复视频入库 upsert 字段错误。
4. 做出对标搜索和批量保存用户。

第二优先级：

1. 视频策略选择。
2. 批量创建 AI 拆解任务。
3. 对标任务状态同步。

第三优先级：

1. 对标结果库。
2. 集合级横向分析。
3. 和脚本生成、剪映草稿联动。
