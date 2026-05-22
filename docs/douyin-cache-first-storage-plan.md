# 抖音采集链路缓存策略变更

日期：2026-05-22

## 结论

账号搜索分页缓存和账号视频分页缓存已废弃：

- 删除 `tiktok_target_user_search_pages`
- 删除 `tiktok_target_user_video_pages`
- 搜索账号、补充账号主页、采集账号视频时直接请求 TikHub
- 返回结果继续 upsert 到实体表：
  - `tiktok_target_users`
  - `tiktok_target_videos`
  - `tiktok_target_video_comments`

评论分页缓存 `tiktok_target_video_comment_pages` 暂时保留。

## 行为

同条件再次搜索或采集视频不再命中分页缓存，会重新请求上游并用最新数据更新本地实体表。
