# 完全弃用 SQLite，只保留 PostgreSQL 的迁移实施清单

## 目标

- 运行时不再读取或创建 `data/runtime/*.sqlite3`
- 业务代码里不再出现 `sqlite3.connect(...)`
- 不建外键，不做级联删除，不做跨库 JOIN
- 关系只保留 `id + snapshot`
- 先保留现有 API 形状，只替换存储层

## 推荐拆分

| 新库 | 表 |
|---|---|
| `core_task_db` | `tasks` |
| `task_audit_db` | `task_events` |
| `archive_db` | `analysis_archives` / `prompt_reverse_archives` / `production_reverse_archives` |
| `ai_video_queue_db` | `ai_video_jobs` / `ai_video_chunks` / `ai_video_artifacts` / `ai_model_runs` |
| `tiktok_target_db` | `tiktok_target_users` / `tiktok_target_sets` / `tiktok_target_set_users` / `tiktok_target_videos` / `tiktok_target_tasks` / `tiktok_target_video_comments` / `tiktok_target_video_interaction_insights` |
| `tiktok_target_cache_db` | `tiktok_target_video_comment_pages` |
| `short_video_analysis_db` | `short_video_items` / `short_video_metric_snapshots` / `short_video_analysis_runs` / `short_video_analysis_segments` / `short_video_formula_library` / `short_video_remake_exports` |
| `media_db` | `jianying_assets` / `jianying_drafts` / `jianying_templates` |

## 实施清单

### 1. PostgreSQL 基础设施

- [x] 准备可直连的 PostgreSQL 实例（本机或远程均可，不依赖 Docker）
- [x] 配好独立连接串
  - `CORE_TASK_DATABASE_URL`
  - `TASK_AUDIT_DATABASE_URL`
  - `AI_VIDEO_QUEUE_DATABASE_URL`
  - `TIKTOK_TARGET_DATABASE_URL`
  - `TIKTOK_TARGET_CACHE_DATABASE_URL`
  - `SHORT_VIDEO_ANALYSIS_DATABASE_URL`
  - `ARCHIVE_DATABASE_URL`
  - `MEDIA_DATABASE_URL`
- [x] 加入 `psycopg[binary,pool]`、`alembic`
- [x] FastAPI 启动时只做 PG 初始化，不再 init SQLite

### 2. 重写存储层

必须重写：

- `backend/app/task_store.py`
- `backend/app/video_analysis_queue.py`
- `backend/app/tiktok_target_store.py`
- `backend/app/short_video_analysis_store.py`

做法：

- [x] 抽出统一 PG 连接池层
- [x] 保留现有函数名，内部改成 PostgreSQL
- [x] 去掉 `DB_PATH`
- [x] 去掉 `init_db()` / `init_ai_video_queue_db()` 的 SQLite 建表逻辑
- [x] `sqlite3.Row` 改成 dict row
- [x] `?` 占位符改成 PostgreSQL 参数风格
- [x] `INSERT OR REPLACE` 改成 `INSERT ... ON CONFLICT DO UPDATE`
- [x] `lastrowid` 改成 `RETURNING`
- [x] `PRAGMA busy_timeout / journal_mode` 全删

### 3. 热点写路径优先迁移

优先级最高：

- `backend/app/video_analysis_worker.py`
- `backend/app/ai_video_analysis_runner.py`
- `backend/app/video_analysis_queue.py`

重点：

- [x] `claim_next_ai_video_job()` 改成 `FOR UPDATE SKIP LOCKED`
- [x] heartbeat 只更新单行，不触发多表写
- [x] progress 写入节流
- [x] 事件日志改成 append-only

### 4. 主任务与审计拆分

- [x] `tasks` 只存主状态
- [x] `task_events` 独立到 `task_audit_db`
- [x] `analysis_archives` 系列独立到 `archive_db`
- [x] `backend/app/main.py` 不再启动时触发 SQLite 初始化

相关调用点：

- `backend/app/main.py`
- `backend/app/routes/tasks.py`
- `backend/app/routes/ai_video_analysis.py`

### 5. 抖音目标采集拆分

- [x] `tiktok_target_users / sets / videos / tasks / comments / insights` 迁到 `tiktok_target_db`
- [x] 评论页缓存表迁到 `tiktok_target_cache_db`，账号搜索页/账号视频页缓存表已废弃
- [x] 不做外键，集合关系用 `id` 维护
- [x] 查询页改成读模型/聚合结果，不依赖跨表强耦合

相关调用点：

- `backend/app/routes/douyin_target.py`
- `backend/app/tiktok_target_store.py`

### 6. 短视频分析拆分

- [x] `short_video_analysis_store.py` 全部迁到 `short_video_analysis_db`
- [x] `metric_snapshots` / `analysis_runs` / `segments` 做按时间分区或至少强索引
- [x] 大查询改成按 `video_id` / `run_id` 精确取数

### 7. 归档与素材库拆分

- [x] `analysis_archives` 系列迁到 `archive_db`
- [x] `jianying_assets / drafts / templates` 迁到 `media_db`
- [x] 删除式操作改软删或两阶段删除，避免跨表级联

相关调用点：

- `backend/app/routes/jianying.py`
- `backend/app/routes/ai_prompt_reverse.py`
- `backend/app/routes/ai_production_reverse.py`

### 8. 测试改造

当前测试里有大量 SQLite monkeypatch，需要改成 PostgreSQL fixture：

- `tests/test_ai_video_queue.py`
- `tests/test_ai_video_p2.py`
- `tests/test_ai_video_p3.py`
- `tests/test_ai_video_evidence_p1.py`
- `tests/test_tiktok_target_interactions.py`
- `tests/test_tikhub_user_search.py`
- `tests/test_short_video_analysis_store.py`

改造方向：

- [x] Postgres 测试库 fixture
- [x] 每个测试用独立 schema 或独立数据库
- [x] 不再设置 `DB_PATH`
- [x] 加入真实并发/锁竞争测试

### 9. 一次性迁移

- [x] 先冻结写入
- [x] 从旧 SQLite 导出/导入脚本已落地：`scripts/migrate_sqlite_to_postgres.py`
- [x] 使用脚本导入 PostgreSQL
- [x] 逐表核对行数和关键抽样（账号搜索页缓存、账号视频页缓存已废弃并删除）
- [x] 切环境变量到 PG
- [x] 重启 worker 和 API

如果不保留旧数据，可以直接不迁，只做新库初始化；SQLite 只作为冷备份文件，不再参与运行。评论页缓存可冷启动重新生成；账号搜索页/账号视频页缓存不再重建。

### 10. 清理 SQLite 依赖

- [x] 删除运行时代码中的 `sqlite3` 引用
- [x] 删除 `DB_PATH` 相关逻辑
- [x] 文档里去掉 SQLite 说明
- [x] 如果仓库里也要零 sqlite，处理 `sdks/jianying-editor-skill/scripts/sync_jy_assets.py`

## 验收标准

- `backend/app` 里不再有 SQLite 运行时路径
- 启动日志不再创建任何 `*.sqlite3`
- `rg -n "sqlite3.connect|DB_PATH|init_ai_video_queue_db|init_db\\(" backend/app` 只剩迁移/测试/外部脚本
- `database is locked` 不再出现
- 1700+ 任务可持续下降，不再长期卡在 Pending
