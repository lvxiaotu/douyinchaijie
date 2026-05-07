# Douyin_TikTok_Download_API 接入

上游项目：<https://github.com/Evil0ctal/Douyin_TikTok_Download_API>

本适配器不再 import 第三方爬虫源码，而是调用它启动后的本地 HTTP API。当前只接入：

- 用户主页信息：`/api/douyin/web/get_sec_user_id` + `/api/douyin/web/handler_user_profile`
- 作品详情：`/api/douyin/web/get_aweme_id` + `/api/douyin/web/fetch_one_video`
- 收藏列表视频下载：`/api/douyin/web/fetch_user_collection_videos` + `/api/download`

## 启动上游服务

建议把上游仓库放在项目外部或 `integrations/douyin_download_api/vendor/` 下。

```powershell
git clone https://github.com/Evil0ctal/Douyin_TikTok_Download_API integrations/douyin_download_api/vendor/Douyin_TikTok_Download_API
```

按上游 README 安装依赖并启动服务。默认适配器会访问：

```text
http://127.0.0.1:80
```

如果你改了端口，在 `.env` 里设置：

```text
DOUYIN_DOWNLOAD_API_BASE=http://127.0.0.1:你的端口
```

## 本项目环境变量

```text
DY_COOKIES=你的抖音网页版 Cookie
DOUYIN_DOWNLOAD_API_BASE=http://127.0.0.1:80
DOUYIN_OUTPUT_DIR=./data/runtime/douyin/downloads
```

Cookie 只放本机 `.env`，不要写进代码或提交到仓库。
