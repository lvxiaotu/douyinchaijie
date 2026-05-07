# DouYin_Spider 接入

上游项目：<https://github.com/cv-cat/DouYin_Spider>

本适配器只接入三块能力：

- 用户主页信息
- 作品详情
- 收藏列表视频下载

未接入直播、搜索、评论、互动等能力。

## 安装上游项目

把上游仓库放到：

```text
integrations/douyin_spider/vendor/DouYin_Spider
```

推荐命令：

```powershell
git clone https://github.com/cv-cat/DouYin_Spider integrations/douyin_spider/vendor/DouYin_Spider
pip install -r requirements.txt
cd integrations/douyin_spider/vendor/DouYin_Spider
npm install jsrsasign
cd ../../../..
```

或者在 `.env` 指定：

```text
DOUYIN_SPIDER_VENDOR_PATH=G:/path/to/DouYin_Spider
```

## 环境变量

```text
DY_COOKIES=你的抖音网页版 Cookie
DOUYIN_OUTPUT_DIR=./data/runtime/douyin/downloads
```

Cookie 只放本机 `.env`，不要写进代码或提交到仓库。

## API

```text
GET  /api/integrations/douyin/status
POST /api/integrations/douyin/user-profile
POST /api/integrations/douyin/work-detail
POST /api/integrations/douyin/favorites/download
```

下载接口默认下载当前 Cookie 对应账号的收藏视频，也可以传 `sec_user_id` 指定用户。
