# Douyin_Spider 备用供应商替换技术方案

## 目标

在不破坏当前 TikHub 稳定链路的前提下，引入 `cvv-cat/Douyin_Spider` 作为备用或替代采集供应商。

搜索接口暂不替换。老接口、新接口、聚合接口命名必须清晰隔离，避免后续维护时混在一起。

## 核心原则

1. 现有 TikHub 逻辑不直接删除，保留为 `legacy`。
2. `Douyin_Spider` 作为 `spider` 新供应商独立封装。
3. 前端业务默认调用统一聚合接口，由配置决定走老接口还是新接口。
4. 搜索接口固定走 TikHub。
5. 新接口失败时可自动 fallback 老接口。
6. 一键回滚只改 `.env`，不需要改业务代码。

## 命名架构

现有 TikHub 适配器建议重命名或包一层别名：

```text
integrations/
  douyin_legacy_tikhub/
    adapter.py              # 老接口：TikHub 专用
    normalizer.py
    errors.py

  douyin_spider_provider/
    adapter.py              # 新接口：Douyin_Spider 专用
    sidecar_client.py
    normalizer.py
    errors.py

  douyin_provider/
    factory.py              # 统一供应商选择
    fallback.py             # spider_first / fallback 逻辑
    contracts.py            # 统一方法签名和返回结构
```

后端路由也明确区分：

```text
/api/integrations/douyin-legacy-tikhub/*
/api/integrations/douyin-spider/*
/api/integrations/douyin-provider/*
```

| 路由 | 用途 | 是否给前端主业务用 |
|---|---|---|
| `/api/integrations/douyin-legacy-tikhub/*` | 老 TikHub 调试/兜底接口 | 否 |
| `/api/integrations/douyin-spider/*` | 新 Douyin_Spider 调试接口 | 否 |
| `/api/integrations/douyin-provider/*` | 聚合接口，一键切换入口 | 是 |

## 统一接口设计

前端主业务以后只调用：

```text
POST /api/integrations/douyin-provider/user-profile
POST /api/integrations/douyin-provider/user-videos
POST /api/integrations/douyin-provider/work-detail
POST /api/integrations/douyin-provider/video-comments
POST /api/integrations/douyin-provider/video-comment-replies
POST /api/integrations/douyin-provider/favorites/items
POST /api/integrations/douyin-provider/favorites/download
```

老接口保留但明确命名：

```text
POST /api/integrations/douyin-legacy-tikhub/user-profile
POST /api/integrations/douyin-legacy-tikhub/user-videos
POST /api/integrations/douyin-legacy-tikhub/work-detail
POST /api/integrations/douyin-legacy-tikhub/video-comments
POST /api/integrations/douyin-legacy-tikhub/video-comment-replies
POST /api/integrations/douyin-legacy-tikhub/favorites/items
POST /api/integrations/douyin-legacy-tikhub/favorites/download
```

新接口单独暴露：

```text
POST /api/integrations/douyin-spider/user-profile
POST /api/integrations/douyin-spider/user-videos
POST /api/integrations/douyin-spider/work-detail
POST /api/integrations/douyin-spider/video-comments
POST /api/integrations/douyin-spider/video-comment-replies
POST /api/integrations/douyin-spider/favorites/items
POST /api/integrations/douyin-spider/favorites/download
```

搜索接口保持原样或明确命名为：

```text
POST /api/integrations/douyin-legacy-tikhub/user-search
POST /api/tools/douyin-target/search
```

## 配置开关

```env
DOUYIN_PROVIDER_MODE=tikhub
# tikhub | spider | spider_first

DOUYIN_SEARCH_PROVIDER=tikhub
DOUYIN_FALLBACK_PROVIDER=tikhub

DOUYIN_SPIDER_API_BASE=http://127.0.0.1:8131
DOUYIN_SPIDER_VENDOR_PATH=./integrations/douyin_spider_provider/vendor/Douyin_Spider
```

| 模式 | 行为 |
|---|---|
| `tikhub` | 全部可替换接口仍走老 TikHub |
| `spider_first` | 先走 Douyin_Spider，失败自动回 TikHub |
| `spider` | 只走 Douyin_Spider，搜索仍走 TikHub |

## 替换范围

| 能力 | 老方法名 | 新方法名 | 替换策略 |
|---|---|---|---|
| 用户主页 | `LegacyTikhubDouyinAdapter.get_user_profile` | `DouyinSpiderAdapter.get_user_profile` | 可替 |
| 用户作品 | `LegacyTikhubDouyinAdapter.get_user_videos` | `DouyinSpiderAdapter.get_user_videos` | 可替 |
| 单作品详情 | `LegacyTikhubDouyinAdapter.get_work_detail` / `get_one_video` | `DouyinSpiderAdapter.get_work_detail` / `get_one_video` | 可替 |
| 一级评论 | `LegacyTikhubDouyinAdapter.get_video_comments` | `DouyinSpiderAdapter.get_video_comments` | 可替 |
| 评论回复 | `LegacyTikhubDouyinAdapter.get_video_comment_replies` | `DouyinSpiderAdapter.get_video_comment_replies` | 可替 |
| 收藏作品 | `LegacyTikhubDouyinAdapter.get_favorite_videos` | `DouyinSpiderAdapter.get_favorite_videos` | 可替 |
| 收藏下载 | `LegacyTikhubDouyinAdapter.download_favorite_videos` | `DouyinSpiderAdapter.download_favorite_videos` | 可替 |
| 用户搜索 | `LegacyTikhubDouyinAdapter.search_users` | 暂不接入 | 保持 TikHub |

## Provider Factory

统一调用入口：

```python
provider = get_douyin_provider()

provider.get_user_videos(...)
provider.get_video_comments(...)
```

内部根据配置选择：

```python
if mode == "tikhub":
    return LegacyTikhubDouyinAdapter()

if mode == "spider":
    return DouyinSpiderAdapter()

if mode == "spider_first":
    return FallbackDouyinProvider(
        primary=DouyinSpiderAdapter(),
        fallback=LegacyTikhubDouyinAdapter(),
    )
```

## Douyin_Spider Sidecar

`Douyin_Spider` 有 Python/Node 依赖，并且会在导入时改 `subprocess.Popen`。为避免影响主后端稳定性，新 provider 默认通过独立本地 sidecar 运行；sidecar 进程内部才会以 `inprocess` 模式导入 vendor。

当前结构：

```text
integrations/douyin_spider_provider/
  adapter.py              # 主后端 adapter；默认 HTTP 调 sidecar
  sidecar_client.py       # HTTP client
  sidecar_server.py       # FastAPI sidecar
  vendor/Douyin_Spider/   # 固定 commit 的上游源码
```

主后端只通过 `DOUYIN_SPIDER_API_BASE` 调 sidecar。即使 sidecar 崩溃，主后端仍可通过 `spider_first` 自动回 TikHub。

启动 sidecar：

```powershell
.\.venv\Scripts\python.exe -m uvicorn integrations.douyin_spider_provider.sidecar_server:app --host 127.0.0.1 --port 8131
```

关键配置：

```env
DOUYIN_SPIDER_EXECUTION_MODE=sidecar
DOUYIN_SPIDER_API_BASE=http://127.0.0.1:8131
DOUYIN_SPIDER_VENDOR_PATH=./integrations/douyin_spider_provider/vendor/Douyin_Spider
```

## 需要改造的调用点

| 文件 | 改造点 |
|---|---|
| `backend/app/routes/douyin.py` | 通用采集接口：用户主页、作品、详情、评论、收藏 |
| `backend/app/routes/douyin_target.py` | 对标采作品、采评论；搜索不动 |
| `backend/app/ai_video_comment_service.py` | AI 分析自动补评论 |
| `integrations/ai_video_analysis/evidence_pipeline.py` | 下载失败后刷新视频 URL |

改造后这些位置不再直接 `TikhubDouyinApiAdapter()`，统一改成：

```python
from integrations.douyin_provider.factory import get_douyin_provider

provider = get_douyin_provider()
```

搜索场景单独使用：

```python
from integrations.douyin_provider.factory import get_douyin_search_provider

search_provider = get_douyin_search_provider()
```

`get_douyin_search_provider()` 第一阶段固定返回 `LegacyTikhubDouyinAdapter()`。

## 观测和安全阀

每次上游调用记录以下字段：

```text
provider
method
status
fallback_used
item_count
duration_ms
error_type
```

不得记录：

```text
Cookie
TIKHUB_API_KEY
完整原始响应中的敏感字段
```

推荐增加 health check：

```text
GET /api/integrations/douyin-provider/status
GET /api/integrations/douyin-spider/status
GET /api/integrations/douyin-legacy-tikhub/status
```

## 上线步骤

1. 新增 `douyin_legacy_tikhub`，把现有 TikHub 代码迁移或别名化，行为不变。
2. 新增 `douyin_spider_provider`，封装 `Douyin_Spider`。
3. 新增 `douyin_provider` 聚合层，默认 `DOUYIN_PROVIDER_MODE=tikhub`。
4. 把业务调用点从 `TikhubDouyinApiAdapter()` 改成 `get_douyin_provider()`。
5. 前端设置页新增“抖音采集供应商”。
6. 先开启 `spider_first` 灰度验证。
7. 稳定后再切到 `spider`。

## 验证计划

第一阶段使用固定样本验证以下接口：

| 能力 | 验证内容 |
|---|---|
| 用户主页 | 是否返回昵称、头像、粉丝数、作品数、`sec_user_id` |
| 用户作品 | 是否返回 `aweme_id`、描述、封面、播放地址、互动数、分页游标 |
| 单作品详情 | 是否返回视频详情、下载/播放地址、作者信息 |
| 一级评论 | 是否返回评论 ID、正文、作者、点赞数、回复数、游标 |
| 评论回复 | 是否返回父评论 ID、回复 ID、正文、作者 |
| 收藏作品 | 是否返回收藏作品列表和分页状态 |

验收标准：

1. `DOUYIN_PROVIDER_MODE=tikhub` 时现有测试和行为不变。
2. `DOUYIN_PROVIDER_MODE=spider_first` 时 Spider 成功则不消耗 TikHub。
3. Spider 失败、空响应或字段不完整时自动 fallback TikHub。
4. `/api/tools/douyin-target/search` 始终走 TikHub。
5. 任意异常可通过改回 `DOUYIN_PROVIDER_MODE=tikhub` 回滚。

## 回滚方案

任何异常只需要改：

```env
DOUYIN_PROVIDER_MODE=tikhub
```

然后重启后端，即可恢复当前稳定版本。

## 当前实现状态

已新增明确分层：

```text
integrations/douyin_legacy_tikhub/      # 老 TikHub 显式别名
integrations/douyin_spider_provider/    # 新 Douyin_Spider provider
integrations/douyin_provider/           # 聚合 factory / fallback
```

已新增独立路由：

```text
/api/integrations/douyin-legacy-tikhub/*
/api/integrations/douyin-spider/*
/api/integrations/douyin-provider/*
```

现有兼容入口已接入聚合层：

```text
/api/integrations/douyin/*
/api/tools/douyin-target/*
```

其中搜索仍固定走 `get_douyin_search_provider()`，也就是 legacy TikHub；用户主页、作品、作品详情、评论、评论回复、收藏列表、收藏下载、对标视频采集、对标评论采集、AI 拆解评论采集、视频直链刷新会按 `DOUYIN_PROVIDER_MODE` 选择 provider。

前端“抖音采集配置”已新增 provider 模式切换：

```text
tikhub       # 全部可替换接口走老 TikHub
spider_first # 新 Douyin_Spider 优先，失败回 TikHub
spider       # 强制走新 Douyin_Spider
```

配置页同时维护：

```text
DOUYIN_SPIDER_EXECUTION_MODE
DOUYIN_SPIDER_API_BASE
DOUYIN_SPIDER_VENDOR_PATH
DOUYIN_PROVIDER_OBSERVABILITY_ENABLED
```

生产观测：

- 所有通过 `get_douyin_provider()` 的调用都会记录 provider、method、latency、error、fallback 使用情况。
- 状态接口 `/api/integrations/douyin-provider/status` 会返回 `metrics`。
- 独立指标接口 `/api/integrations/douyin-provider/metrics` 会返回聚合调用统计。
- JSONL 事件默认写入 `data/runtime/douyin/provider_events.jsonl`，可用 `DOUYIN_PROVIDER_EVENT_LOG` 覆盖。

当前验证结果：

1. `DOUYIN_PROVIDER_MODE` 未配置时默认 `tikhub`。
2. `DOUYIN_PROVIDER_MODE=spider` 时走 `DouyinSpiderAdapter`。
3. `DOUYIN_PROVIDER_MODE=spider_first` 时走 `FallbackDouyinProvider`。
4. `spider_first` 主供应商失败时会回退到 legacy TikHub，并在响应中写入 `provider_trace`。
5. 用户主页、用户作品、单作品详情、一级评论、评论回复、收藏列表已用固定样本 smoke 通过。
6. 后端新增 provider/legacy/search 路由单测通过。
7. sidecar `/status` 通过，主后端 `DouyinSpiderAdapter` 默认 sidecar 模式可连通。
8. 收藏下载已用新 Spider sidecar 跑 1 条真实小样本，下载文件和 manifest 均生成成功。
