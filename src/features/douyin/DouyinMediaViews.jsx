import { useEffect, useState } from "react";
import { Badge } from "../../components/common/index";
import { API_BASE } from "../../constants/appConfig";
import { createAiVideoBreakdownJob, fetchDouyinFavoriteItems, fetchDouyinUserVideos } from "../../services/api";
import { compactNumber, firstUrl, unwrapDouyinData } from "../../utils/appUtils";

export function DouyinProfileView({ result }) {
  const data = unwrapDouyinData(result);
  const user = data?.user || data?.user_info || result?.profile || {};
  const avatar =
    firstUrl(user.avatar_larger) ||
    firstUrl(user.avatar_300x300) ||
    firstUrl(user.avatar_medium) ||
    firstUrl(user.avatar_thumb) ||
    result?.profile?.avatar;

  return (
    <article className="douyin-result-card profile-result">
      {avatar && <img className="profile-avatar" src={avatar} alt="用户头像" />}
      <div>
        <h3>{user.nickname || result?.profile?.nickname || "未命名用户"}</h3>
        <p>{user.signature || result?.profile?.signature || "暂无简介"}</p>
        <div className="stat-grid">
          <span>作品 {compactNumber(user.aweme_count || result?.profile?.aweme_count)}</span>
          <span>粉丝 {compactNumber(user.follower_count || result?.profile?.follower_count)}</span>
          <span>关注 {compactNumber(user.following_count || result?.profile?.following_count)}</span>
          <span>获赞 {compactNumber(user.total_favorited || result?.profile?.total_favorited)}</span>
        </div>
      </div>
    </article>
  );
}

export function DouyinVideoView({ item, compact = false, onBreakdown, onPromptReverse, onProductionReverse }) {
  const [breakdown, setBreakdown] = useState(null);
  const [breakdownLoading, setBreakdownLoading] = useState(false);
  const [breakdownError, setBreakdownError] = useState("");
  const [reverseLoading, setReverseLoading] = useState(false);
  const [productionLoading, setProductionLoading] = useState(false);
  const video = item?.video || item?.video_data || {};
  const author = item?.author || {};
  const cover =
    firstUrl(video.cover) ||
    firstUrl(video.origin_cover) ||
    firstUrl(video.dynamic_cover) ||
    firstUrl(item?.images?.[0]);
  const videoUrl =
    firstUrl(video.play_addr) ||
    firstUrl(video.download_addr) ||
    video.nwm_video_url_HQ ||
    video.wm_video_url_HQ ||
    item?.video_url;
  const proxiedVideoUrl = videoUrl
    ? `${API_BASE}/api/integrations/douyin/media-proxy?url=${encodeURIComponent(videoUrl)}&referer=${encodeURIComponent(
        item?.share_info?.share_url || "https://www.douyin.com/",
      )}`
    : "";
  const images = Array.isArray(item?.images) ? item.images : [];
  const stats = item?.statistics || {};

  async function handleBreakdown() {
    setBreakdownLoading(true);
    setBreakdownError("");
    try {
      const videoPayload = {
        ...item,
        preview_cover: cover,
        source_video_url: videoUrl,
      };
      const job = onBreakdown ? await onBreakdown(videoPayload) : await createAiVideoBreakdownJob(videoPayload);
      setBreakdown(job);
    } catch (err) {
      setBreakdownError(err.message || String(err));
    } finally {
      setBreakdownLoading(false);
    }
  }

  async function handlePromptReverse() {
    setReverseLoading(true);
    setBreakdownError("");
    try {
      const videoPayload = {
        ...item,
        preview_cover: cover,
        source_video_url: videoUrl,
      };
      await onPromptReverse?.(videoPayload);
    } catch (err) {
      setBreakdownError(err.message || String(err));
    } finally {
      setReverseLoading(false);
    }
  }

  async function handleProductionReverse() {
    setProductionLoading(true);
    setBreakdownError("");
    try {
      const videoPayload = {
        ...item,
        preview_cover: cover,
        source_video_url: videoUrl,
      };
      await onProductionReverse?.(videoPayload);
    } catch (err) {
      setBreakdownError(err.message || String(err));
    } finally {
      setProductionLoading(false);
    }
  }

  return (
    <article className={`douyin-result-card video-result ${compact ? "compact-video-card" : ""}`}>
      <div className="media-frame">
        {videoUrl ? (
          <video src={proxiedVideoUrl} poster={cover} controls preload="metadata" />
        ) : cover ? (
          <img src={cover} alt="作品封面" />
        ) : (
          <div className="empty-result">没有可预览媒体</div>
        )}
      </div>
      <div className="video-info">
        <h3>{item?.desc || item?.title || "未命名作品"}</h3>
        <p>{author.nickname ? `作者：${author.nickname}` : "作者信息未返回"}</p>
        <div className="stat-grid">
          <span>点赞 {compactNumber(stats.digg_count)}</span>
          <span>评论 {compactNumber(stats.comment_count)}</span>
          <span>收藏 {compactNumber(stats.collect_count)}</span>
          <span>分享 {compactNumber(stats.share_count)}</span>
        </div>
        {item?.share_info?.share_url && (
          <a className="result-link" href={item.share_info.share_url} target="_blank" rel="noreferrer">
            打开原始链接
          </a>
        )}
        <div className="breakdown-action-row">
          <button className="breakdown-button" type="button" onClick={handleBreakdown} disabled={breakdownLoading}>
            {breakdownLoading ? "拆解中" : "AI 视频拆解"}
          </button>
          <button className="secondary-action-button" type="button" onClick={handlePromptReverse} disabled={reverseLoading}>
            {reverseLoading ? "反推中" : "反推提示词"}
          </button>
          <button className="secondary-action-button" type="button" onClick={handleProductionReverse} disabled={productionLoading}>
            {productionLoading ? "分析中" : "制作方式反推"}
          </button>
        </div>
        {breakdownError && <div className="error-box">{breakdownError}</div>}
        {breakdown?.result && (
          <div className="breakdown-result">
            <strong>AI 拆解结果</strong>
            <p>{breakdown.result.summary}</p>
            <div className="breakdown-tags">
              {(breakdown.result.keywords || []).map((keyword) => (
                <Badge key={keyword}>{keyword}</Badge>
              ))}
            </div>
          </div>
        )}
        {images.length > 0 && (
          <div className="image-strip">
            {images.slice(0, 6).map((image, index) => (
              <img key={index} src={firstUrl(image.url_list || image)} alt={`图片 ${index + 1}`} />
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

export function DouyinCollectionView({ result, title = "收藏作品", fetchMore, pageSize = 4, onBreakdown, onPromptReverse, onProductionReverse }) {
  const data = unwrapDouyinData(result);
  const initialItems = result?.items || data?.aweme_list || data?.videos || data?.list || [];
  const [items, setItems] = useState(initialItems);
  const [nextCursor, setNextCursor] = useState(result?.next_cursor || 0);
  const [hasMore, setHasMore] = useState(Boolean(result?.has_more));
  const [loadingMore, setLoadingMore] = useState(false);
  const downloaded = result?.downloaded || [];

  useEffect(() => {
    setItems(initialItems);
    setNextCursor(result?.next_cursor || 0);
    setHasMore(Boolean(result?.has_more));
  }, [result]);

  async function handleLoadMore() {
    if (!fetchMore || loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const nextPage = await fetchMore({ maxCursor: nextCursor, pageSize });
      const nextItems = nextPage?.items || unwrapDouyinData(nextPage)?.aweme_list || [];
      setItems((current) => [...current, ...nextItems]);
      setNextCursor(nextPage?.next_cursor || nextCursor);
      setHasMore(Boolean(nextPage?.has_more) && nextPage?.next_cursor !== nextCursor);
    } finally {
      setLoadingMore(false);
    }
  }

  if (downloaded.length > 0) {
    return (
      <div className="result-list">
        {downloaded.map((item) => (
          <article className="download-row" key={item.path || item.aweme_id}>
            <strong>{item.aweme_id || "已下载视频"}</strong>
            <span>{item.path}</span>
          </article>
        ))}
      </div>
    );
  }

  if (!items.length) return null;

  return (
    <>
      <div className="collection-toolbar">
        <span>
          {title}：已加载 {items.length} 条
        </span>
      </div>
      <div className="result-list collection-grid">
        {items.map((item) => (
          <DouyinVideoView
            key={item.aweme_id || item.id || item.desc}
            item={item}
            compact
            onBreakdown={onBreakdown}
            onPromptReverse={onPromptReverse}
            onProductionReverse={onProductionReverse}
          />
        ))}
      </div>
      {hasMore && fetchMore && (
        <button
          className="load-more-button"
          type="button"
          disabled={loadingMore}
          onClick={handleLoadMore}
        >
          {loadingMore ? "加载中" : "加载更多"}
        </button>
      )}
    </>
  );
}

export function DouyinResultView({ value, onBreakdown, onPromptReverse, onProductionReverse }) {
  if (!value) return null;
  const data = unwrapDouyinData(value);
  const isProfile = Boolean(data?.user || data?.user_info || value?.profile);
  const isCollection = Boolean(data?.aweme_list || data?.videos || data?.list || value?.downloaded || value?.items);
  const isVideo = Boolean(data?.video || data?.video_data || data?.aweme_id || value?.detail);

  return (
    <div className="result-view">
      {isProfile && <DouyinProfileView result={value} />}
      {value?.user_videos && (
        <DouyinCollectionView
          result={value.user_videos}
          title="用户作品"
          fetchMore={({ maxCursor, pageSize }) =>
            fetchDouyinUserVideos({
              secUserId: value.user_videos.sec_user_id || value.sec_user_id,
              maxCursor,
              pageSize,
            })
          }
          onBreakdown={onBreakdown}
          onPromptReverse={onPromptReverse}
          onProductionReverse={onProductionReverse}
        />
      )}
      {isCollection && (
        <DouyinCollectionView
          result={value}
          fetchMore={({ maxCursor, pageSize }) => fetchDouyinFavoriteItems({ maxCursor, pageSize })}
          onBreakdown={onBreakdown}
          onPromptReverse={onPromptReverse}
          onProductionReverse={onProductionReverse}
        />
      )}
      {!isProfile && !isCollection && isVideo && (
        <DouyinVideoView item={data} onBreakdown={onBreakdown} onPromptReverse={onPromptReverse} onProductionReverse={onProductionReverse} />
      )}
    </div>
  );
}

export function JsonPreview({ value, onBreakdown, onPromptReverse, onProductionReverse }) {
  if (!value) {
    return <div className="empty-result">结果会显示在这里</div>;
  }
  return (
    <>
      <DouyinResultView value={value} onBreakdown={onBreakdown} onPromptReverse={onPromptReverse} onProductionReverse={onProductionReverse} />
      <details className="raw-json">
        <summary>查看原始 JSON</summary>
        <pre className="result-box">{JSON.stringify(value, null, 2)}</pre>
      </details>
    </>
  );
}
