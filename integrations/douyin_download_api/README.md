# Douyin_TikTok_Download_API 接入

上游项目：<https://github.com/Evil0ctal/Douyin_TikTok_Download_API>

本适配器不再 import 第三方爬虫源码，而是调用它启动后的本地 HTTP API。当前接入：

- 用户主页信息：`/api/douyin/web/get_sec_user_id` + `/api/douyin/web/handler_user_profile`
- 用户作品列表：`/api/douyin/web/fetch_user_post_videos`
- 作品详情：`/api/douyin/web/get_aweme_id` + `/api/douyin/web/fetch_one_video`
- 视频评论：`/api/douyin/web/fetch_video_comments`
- 评论回复：`/api/douyin/web/fetch_video_comment_replies`
- 收藏列表视频下载：`/api/douyin/web/fetch_user_collection_videos` + `/api/download`

## 缓存与落库

本项目所有抖音对标数据走“先查库，再上游”：

- 用户主页先查 `tiktok_target_users`
- 用户作品页先查 `tiktok_target_user_video_pages`
- 单视频详情先查 `tiktok_target_videos`
- 评论/回复页先查 `tiktok_target_video_comment_pages`
- 采集完成后再写入规范化实体表和原始 JSON

重要规则：

- `recent_update_at`、`last_post_at` 必须保存
- `play_count` 优先保留上游正数或库内已有正数，避免落成 0
- 作品分页按 `sec_user_id + max_cursor + count` 保存梯度缓存
- 评论采集已并入 AI 视频拆解步骤，失败不会阻断拆解，可在任务中心重试

上游报错统一写入：

```text
data/runtime/error/douyin-download-api/<YYYYMMDD>/*.json
```

## 启动上游服务

建议把上游仓库放在项目外部或 `integrations/douyin_download_api/vendor/` 下。

```powershell
git clone https://github.com/Evil0ctal/Douyin_TikTok_Download_API integrations/douyin_download_api/vendor/Douyin_TikTok_Download_API
```

按上游 README 安装依赖并启动服务。默认适配器会访问：

```text
http://127.0.0.1:8123
```

如果你改了端口，在 `.env` 里设置：

```text
DOUYIN_DOWNLOAD_API_BASE=http://127.0.0.1:你的端口
```

## 本项目环境变量

```text
DY_COOKIES=你的抖音网页版 Cookie
DOUYIN_DOWNLOAD_API_BASE=http://127.0.0.1:8123
DOUYIN_OUTPUT_DIR=./data/runtime/douyin/downloads
```

Cookie 只放本机 `.env`，不要写进代码或提交到仓库。
