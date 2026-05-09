import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Archive,
  Boxes,
  Clock3,
  Database,
  FileText,
  FolderCog,
  Home,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Scissors,
  Wrench,
} from "lucide-react";
import {
  archiveTask,
  createAiVideoBreakdownJob,
  createAiPromptReverseJob,
  createJianyingDraftFromScript,
  deleteVideoScript,
  deleteTask,
  downloadDouyinFavorites,
  fetchAiVideoConfig,
  fetchAiVideoArchives,
  fetchAiPromptReverseConfig,
  fetchAiPromptReverseStatus,
  fetchAiPromptReverseArchives,
  fetchAiProviderConfig,
  fetchDouyinConfig,
  fetchDouyinFavoriteItems,
  fetchJianyingEditorSdkStatus,
  fetchDouyinUserProfile,
  fetchDouyinUserVideos,
  fetchTasks,
  fetchDouyinWorkDetail,
  fetchWorkbench,
  fetchTask,
  fetchVideoScript,
  fetchVideoScripts,
  generateJianyingNaturalScript,
  inspectJianyingDraft,
  listJianyingDraftProjects,
  openJianyingDraftPath,
  prepareVideoScriptAssets,
  saveDouyinConfig,
  saveAiVideoConfig,
  saveAiPromptReverseConfig,
  saveAiProviderConfig,
  saveVideoScript,
  testAiProviderConfig,
} from "./services/api";
import { fallbackWorkbench } from "./workbenchSeed";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "";

const sections = {
  dashboard: ["首页", "查看最近任务、常用工具和素材状态。"],
  videoScript: ["灵感剧本", "把创作灵感生成可编辑的 script.json。"],
  draftInspector: ["查看草稿", "查看剪映草稿项目和画布详情。"],
  jianyingEditor: ["剪映 Skill", "围绕 AI 剧本、第三方素材补齐和剪映草稿生成的主工作流。"],
  tools: ["工具中心", "以后每个新功能都可以作为一个独立工具接入。"],
  jobs: ["任务中心", "统一查看后台任务、进度和失败状态。"],
  library: ["素材库", "沉淀下载、分析和处理后的内容。"],
  integrations: ["开源项目接入", "为 GitHub 项目、脚本和外部服务预留适配层。"],
  settings: ["配置", "集中管理路径、接口地址和运行策略。"],
};

const navItems = [
  ["dashboard", Home, "首页"],
  ["videoScript", FileText, "灵感剧本"],
  ["draftInspector", Database, "查看草稿"],
  ["jianyingEditor", Scissors, "剪映 Skill"],
  ["tools", Wrench, "工具中心"],
  ["jobs", Clock3, "任务中心"],
  ["library", Archive, "素材库"],
  ["integrations", Boxes, "接入"],
  ["settings", Settings, "配置"],
];

const settingItems = [
  ["ai-provider", "AI 模型"],
  ["douyin", "抖音采集"],
  ["ai-video", "AI 视频拆解"],
  ["ai-prompt", "反推提示词"],
  ["jianying", "剪映草稿"],
];

const jianyingEditorItems = [
  ["script", "剧本生成"],
  ["reference", "开发者参考"],
];

const statusText = {
  ready: "可用",
  partial_ready: "部分补齐",
  script_ready: "剧本就绪",
  waiting_assets: "待补齐",
  waiting_audio: "待补音频",
  waiting_visual: "待补画面",
  draft: "草稿",
  running: "运行中",
  done: "完成",
  paused: "暂停",
  error: "失败",
};

function Badge({ status, children }) {
  return <span className={`badge ${status || ""}`}>{children}</span>;
}

function generationModeLabel(mode) {
  if (mode === "skill_contract" || mode === "sdk") {
    return "Skill 规则";
  }
  return "本地";
}

function normalizeOptionalText(value) {
  return cleanScriptValue(value).trim();
}

function deriveBgmKeywords(script) {
  return normalizeOptionalText(script?.bible?.bgm_keywords || script?.config?.genre || "");
}

function deriveOptionalWorkflowFlags(script) {
  const bible = script?.bible || {};
  return {
    hasBgm: Boolean(normalizeOptionalText(bible.bgm_keywords)),
    hasVoice: Boolean(normalizeOptionalText(bible.voice_vibe)),
    hasVisualStyle: Boolean(normalizeOptionalText(bible.art_style_prompt)),
    hasOnscreenText: Boolean((script?.scenes || []).some((scene) => normalizeOptionalText(scene?.onscreen_text))),
    hasNarration: Boolean((script?.scenes || []).some((scene) => normalizeOptionalText(scene?.audio_narration || scene?.narration))),
  };
}

function createScriptFallbackBible(script) {
  const title = script?.config?.title || "未命名剧本";
  const genre = script?.config?.genre || "短视频";
  return {
    art_style_prompt: `${genre}, clean short-video visual style, readable framing, cinematic lighting`,
    character_base_prompt: `${title} 的核心角色特征，保持镜头间一致`,
    voice_vibe: "自然、清晰、稳定的中文旁白",
    bgm_keywords: `${genre}, emotional, cinematic, uplifting`,
  };
}

function sdkResultData(result) {
  return result?.data?.data || {};
}

function sdkResultReason(result) {
  return result?.data?.reason || result?.error || "";
}

function ToolCard({ tool, onOpen }) {
  return (
    <article className="tool-card">
      <header>
        <div className="tool-title">
          <span className="tool-avatar">{tool.icon}</span>
          <div>
            <h3>{tool.name}</h3>
            <p>{tool.updated}</p>
          </div>
        </div>
        <Badge status={tool.status}>{statusText[tool.status] || tool.status}</Badge>
      </header>
      <p>{tool.desc}</p>
      <div className="tool-meta">
        {tool.tags.map((tag) => (
          <Badge key={tag}>{tag}</Badge>
        ))}
      </div>
      {onOpen && (
        <div className="tool-card-actions">
          <button className="text-button" type="button" onClick={() => onOpen(tool)}>
            打开工具
          </button>
        </div>
      )}
    </article>
  );
}

function JobRow({ job, table }) {
  const progress = Math.max(0, Math.min(100, job.progress));

  if (table) {
    return (
      <tr>
        <td>{job.name}</td>
        <td>{job.tool}</td>
        <td>
          <Badge status={job.status}>{statusText[job.status] || job.status}</Badge>
        </td>
        <td>
          <div className="table-progress">
            <div className="progress">
              <span style={{ width: `${progress}%` }} />
            </div>
            <span>{progress}%</span>
          </div>
        </td>
        <td>{job.updated}</td>
      </tr>
    );
  }

  return (
    <article className="job-row">
      <div className="panel-header">
        <strong>{job.name}</strong>
        <Badge status={job.status}>{statusText[job.status] || job.status}</Badge>
      </div>
      <div className="progress" aria-label={`进度 ${progress}%`}>
        <span style={{ width: `${progress}%` }} />
      </div>
      <div className="job-meta">
        <span>{job.tool}</span>
        <span>{job.updated}</span>
      </div>
    </article>
  );
}

function firstUrl(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return firstUrl(value[0]);
  if (Array.isArray(value.url_list)) return value.url_list[0] || "";
  return "";
}

function compactNumber(value) {
  if (value === undefined || value === null || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return value;
  if (number >= 10000) return `${(number / 10000).toFixed(1)}万`;
  return String(number);
}

function unwrapDouyinData(value) {
  return value?.raw?.data || value?.data || value?.raw || value;
}

function DouyinProfileView({ result }) {
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

function DouyinVideoView({ item, compact = false, onBreakdown, onPromptReverse }) {
  const [breakdown, setBreakdown] = useState(null);
  const [breakdownLoading, setBreakdownLoading] = useState(false);
  const [breakdownError, setBreakdownError] = useState("");
  const [reverseLoading, setReverseLoading] = useState(false);
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

function DouyinCollectionView({ result, title = "收藏作品", fetchMore, pageSize = 4, onBreakdown, onPromptReverse }) {
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

function DouyinResultView({ value, onBreakdown, onPromptReverse }) {
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
        />
      )}
      {isCollection && (
        <DouyinCollectionView
          result={value}
          fetchMore={({ maxCursor, pageSize }) => fetchDouyinFavoriteItems({ maxCursor, pageSize })}
          onBreakdown={onBreakdown}
          onPromptReverse={onPromptReverse}
        />
      )}
      {!isProfile && !isCollection && isVideo && (
        <DouyinVideoView item={data} onBreakdown={onBreakdown} onPromptReverse={onPromptReverse} />
      )}
    </div>
  );
}

function JsonPreview({ value, onBreakdown, onPromptReverse }) {
  if (!value) {
    return <div className="empty-result">结果会显示在这里</div>;
  }
  return (
    <>
      <DouyinResultView value={value} onBreakdown={onBreakdown} onPromptReverse={onPromptReverse} />
      <details className="raw-json">
        <summary>查看原始 JSON</summary>
        <pre className="result-box">{JSON.stringify(value, null, 2)}</pre>
      </details>
    </>
  );
}

function cleanScriptValue(value) {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") {
    const trimmed = value.trim();
    if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
      try {
        return cleanScriptValue(JSON.parse(trimmed.replaceAll("'", '"')));
      } catch {
        return trimmed;
      }
    }
    return trimmed;
  }
  if (Array.isArray(value)) {
    return value.map(cleanScriptValue).filter(Boolean).join("\n");
  }
  if (typeof value === "object") {
    return Object.values(value).map(cleanScriptValue).filter(Boolean).join("\n");
  }
  return String(value);
}

function sceneDuration(scene, fallback = 3) {
  const value = Number(scene?.estimated_duration || scene?.assets?.duration || 0);
  return value > 0 ? value : fallback;
}

function sceneSummary(scene) {
  return cleanScriptValue(scene?.summary || scene?.visual_prompt || scene?.audio_narration || scene?.narration).slice(0, 42) || "未填写内容概括";
}

function formatTimelineMark(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return "0s";
  const rounded = Number.isInteger(seconds) ? seconds : seconds.toFixed(1);
  return `${rounded}s`;
}

function createDateDraftName(date = new Date()) {
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日${date.getHours()}时${date.getMinutes()}分`;
}

function DouyinCollectorPanel({ onBreakdown, onPromptReverse }) {
  const [userUrl, setUserUrl] = useState("");
  const [workUrl, setWorkUrl] = useState("");
  const [maxItems, setMaxItems] = useState(4);
  const [pageSize, setPageSize] = useState(20);
  const [activeTask, setActiveTask] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function runTask(taskName, runner) {
    setActiveTask(taskName);
    setError("");
    setResult(null);
    try {
      const data = await runner();
      setResult(data);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setActiveTask("");
    }
  }

  return (
    <section className="panel douyin-panel">
      <div className="panel-header">
        <div>
          <h2>抖音采集</h2>
          <p>填写参数后直接调用后端接口，Cookie 和服务地址从本地配置读取。</p>
        </div>
        <Badge status="ready">已接入</Badge>
      </div>

      <div className="collector-grid">
        <form
          className="collector-card"
          onSubmit={(event) => {
            event.preventDefault();
            runTask("user", async () => {
              const [profile, userVideos] = await Promise.all([
                fetchDouyinUserProfile(userUrl),
                fetchDouyinUserVideos({ userUrl, pageSize: 4 }),
              ]);
              return { ...profile, user_videos: userVideos };
            });
          }}
        >
          <h3>用户主页信息</h3>
          <label>
            用户主页链接
            <input
              type="url"
              placeholder="https://www.douyin.com/user/..."
              value={userUrl}
              onChange={(event) => setUserUrl(event.target.value)}
              required
            />
          </label>
          <button className="primary-button" type="submit" disabled={activeTask === "user"}>
            查询用户
          </button>
        </form>

        <form
          className="collector-card"
          onSubmit={(event) => {
            event.preventDefault();
            runTask("work", () => fetchDouyinWorkDetail(workUrl));
          }}
        >
          <h3>作品详情</h3>
          <label>
            作品链接
            <input
              type="url"
              placeholder="https://www.douyin.com/video/..."
              value={workUrl}
              onChange={(event) => setWorkUrl(event.target.value)}
              required
            />
          </label>
          <button className="primary-button" type="submit" disabled={activeTask === "work"}>
            查询作品
          </button>
        </form>

        <form
          className="collector-card"
          onSubmit={(event) => {
            event.preventDefault();
            runTask("favorites", () => downloadDouyinFavorites({ maxItems, pageSize }));
          }}
        >
          <h3>收藏视频下载</h3>
          <div className="collector-fields">
            <label>
              下载数量
              <input
                type="number"
                min="1"
                max="50"
                value={maxItems}
                onChange={(event) => setMaxItems(event.target.value)}
              />
            </label>
            <label>
              每页数量
              <input
                type="number"
                min="1"
                max="50"
                value={pageSize}
                onChange={(event) => setPageSize(event.target.value)}
              />
            </label>
          </div>
          <button className="primary-button" type="submit" disabled={activeTask === "favorites"}>
            下载收藏
          </button>
          <button
            className="text-button"
            type="button"
            disabled={activeTask === "favorite-items"}
            onClick={() => runTask("favorite-items", () => fetchDouyinFavoriteItems({ pageSize: 4 }))}
          >
            查看全部收藏数据
          </button>
        </form>
      </div>

      {activeTask && <div className="running-note">正在执行，请稍等...</div>}
      {error && <div className="error-box">{error}</div>}
      <JsonPreview value={result} onBreakdown={onBreakdown} onPromptReverse={onPromptReverse} />
    </section>
  );
}

const studioComponentMap = {
  SeedInput: StudioSeedInputBlock,
  AngleSelector: StudioAngleSelectorBlock,
  ConceptBible: StudioConceptBibleBlock,
  SceneBlueprint: StudioSceneBlueprintBlock,
  ThinkingBlock: StudioThinkingBlock,
  ErrorBlock: StudioErrorBlock,
};

function StudioBlockRenderer({ block, onAction, onRetry }) {
  const Component = studioComponentMap[block.componentType] || StudioErrorBlock;
  return <Component data={block.payload} locked={block.isLocked} onAction={onAction} onRetry={onRetry} />;
}

function StudioSeedInputBlock({ data, locked, onAction }) {
  const [draft, setDraft] = useState({
    type: data?.type || "短视频",
    creativePreset: data?.creativePreset || "default",
    title: data?.title || "",
    idea: data?.idea || "",
    provider: data?.provider || "",
  });

  if (locked) {
    return (
      <article className="studio-block locked">
        <Badge status="done">已锁定</Badge>
        <div className="studio-block-kicker">Seed</div>
        <h3>{draft.title || draft.idea.slice(0, 18) || "未命名灵感"}</h3>
        <p>{draft.idea}</p>
        <div className="studio-chip-row">
          <span>{draft.type}</span>
          <span>{draft.creativePreset}</span>
        </div>
      </article>
    );
  }

  return (
    <form className="studio-block active" onSubmit={(event) => {
      event.preventDefault();
      onAction({ type: "submit", payload: draft });
    }}>
      <div className="panel-header">
        <div>
          <h3>提供灵感</h3>
          <p>先输入一个种子，AI 只负责发散方向，不直接写分镜。</p>
        </div>
        <Badge>The Seed</Badge>
      </div>
      <div className="studio-seed-grid">
        <label>
          题材 / 流派
          <select value={draft.creativePreset} onChange={(event) => setDraft({ ...draft, creativePreset: event.target.value })}>
            <option value="default">通用短剧模板</option>
            <option value="mysticism_lead">玄学引流模板</option>
            <option value="ancient爽文">古风爽文漫剧</option>
            <option value="ai_pet">AI 小动物剧情</option>
          </select>
        </label>
        <label>
          标题
          <input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="例如：我在盛唐写天下" />
        </label>
        <label>
          AI Provider
          <select value={draft.provider} onChange={(event) => setDraft({ ...draft, provider: event.target.value })}>
            <option value="">使用当前全局 AI</option>
            <option value="mock">mock 调试</option>
          </select>
        </label>
      </div>
      <label>
        灵感关键词
        <textarea value={draft.idea} onChange={(event) => setDraft({ ...draft, idea: event.target.value })} placeholder="例如：塔罗牌为什么总能说中你的心事" required />
      </label>
      <div className="script-action-strip">
        <button className="primary-button" type="submit">让 AI 发散方向</button>
      </div>
    </form>
  );
}

function StudioAngleSelectorBlock({ data, locked, onAction }) {
  const [selectedId, setSelectedId] = useState(data?.selectedAngle?.id || data?.angles?.[0]?.id || "");
  const [feedback, setFeedback] = useState(data?.feedback || "");
  const selectedAngle = (data?.angles || []).find((angle) => angle.id === selectedId) || data?.selectedAngle;

  if (locked) {
    return (
      <article className="studio-block locked">
        <Badge status="done">已锁定</Badge>
        <div className="studio-block-kicker">Angle</div>
        <h3>{selectedAngle?.title || "已选择方向"}</h3>
        <p>{selectedAngle?.description}</p>
        {feedback && <blockquote>{feedback}</blockquote>}
      </article>
    );
  }

  return (
    <section className="studio-block active">
      <div className="panel-header">
        <div>
          <h3>选择剧情脉络</h3>
          <p>先决定切入点，再让 AI 收束为设定集。</p>
        </div>
        <Badge>3 angles</Badge>
      </div>
      <div className="studio-angle-grid">
        {(data?.angles || []).map((angle) => (
          <button className={`studio-angle-card ${selectedId === angle.id ? "active" : ""}`} key={angle.id} type="button" onClick={() => setSelectedId(angle.id)}>
            <strong>{angle.title}</strong>
            <span>{angle.description}</span>
          </button>
        ))}
      </div>
      <label>
        微调意见
        <textarea value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="例如：选方向一，但语调要再高冷一点" />
      </label>
      <div className="script-action-strip">
        <button className="primary-button" type="button" onClick={() => onAction({ type: "select", payload: { selectedAngle, feedback } })} disabled={!selectedAngle}>
          锁定方向并生成设定集
        </button>
      </div>
    </section>
  );
}

function StudioConceptBibleBlock({ data, locked, onAction }) {
  const [bible, setBibleDraft] = useState(data?.bible || {});
  const [settings, setSettings] = useState({ durationSeconds: 30, sceneCount: 5, resolution: "9:16" });
  const update = (key, value) => setBibleDraft((current) => ({ ...current, [key]: value }));

  if (locked) {
    return (
      <article className="studio-block locked">
        <Badge status="done">已锁定</Badge>
        <div className="studio-block-kicker">Concept Bible</div>
        <h3>设定集已锁定</h3>
        <dl className="studio-readonly-grid">
          <dt>主角</dt><dd>{bible.character_base_prompt}</dd>
          <dt>画风</dt><dd>{bible.art_style_prompt}</dd>
          <dt>声音</dt><dd>{bible.voice_vibe}</dd>
        </dl>
      </article>
    );
  }

  return (
    <section className="studio-block active">
      <div className="panel-header">
        <div>
          <h3>审查设定集</h3>
          <p>这里是关键拦截点。锁定后，后续镜头会继承这些全局 Prompt。</p>
        </div>
        <Badge>The Bible</Badge>
      </div>
      <div className="script-bible-grid">
        <label>主角视觉特征<textarea value={bible.character_base_prompt || ""} onChange={(event) => update("character_base_prompt", event.target.value)} /></label>
        <label>画面整体风格<textarea value={bible.art_style_prompt || ""} onChange={(event) => update("art_style_prompt", event.target.value)} /></label>
        <label>配音音色要求<textarea value={bible.voice_vibe || ""} onChange={(event) => update("voice_vibe", event.target.value)} /></label>
        <label>BGM 检索词<textarea value={bible.bgm_keywords || ""} onChange={(event) => update("bgm_keywords", event.target.value)} /></label>
      </div>
      <div className="script-chassis-grid studio-inline-settings">
        <label>预计总时长<input type="number" min="5" max="600" value={settings.durationSeconds} onChange={(event) => setSettings({ ...settings, durationSeconds: Number(event.target.value) })} /></label>
        <label>分镜上限<input type="number" min="1" max="30" value={settings.sceneCount} onChange={(event) => setSettings({ ...settings, sceneCount: Number(event.target.value) })} /></label>
        <label>视频比例<select value={settings.resolution} onChange={(event) => setSettings({ ...settings, resolution: event.target.value })}><option value="9:16">9:16</option><option value="16:9">16:9</option><option value="1:1">1:1</option></select></label>
      </div>
      <div className="script-action-strip">
        <button className="primary-button" type="button" onClick={() => onAction({ type: "confirm", payload: { bible, settings } })}>
          锁定设定并生成蓝图
        </button>
      </div>
    </section>
  );
}

function StudioSceneBlueprintBlock({ data }) {
  const scenes = data?.scenes || data?.script?.scenes || [];
  return (
    <section className="studio-block active">
      <div className="panel-header">
        <div>
          <h3>素材蓝图</h3>
          <p>这些卡片就是后续生成图片、音频并回填草稿的采购单。</p>
        </div>
        <Badge status="ready">{scenes.length} 镜</Badge>
      </div>
      <div className="script-output-grid">
        {scenes.map((scene) => (
          <article className="script-output-card" key={scene.id || scene.scene_index}>
            <header>
              <div>
                <strong>{scene.title || `Scene ${scene.id || scene.scene_index}`}</strong>
                <span>{sceneSummary(scene)}</span>
              </div>
              <Badge>预计 {sceneDuration(scene)}s</Badge>
            </header>
            <label>配音文案<textarea readOnly value={cleanScriptValue(scene.audio_narration)} /></label>
            <label>生图/分镜提示词<textarea readOnly value={cleanScriptValue(scene.visual_prompt)} /></label>
            <div className="script-asset-status-row">
              <span>图片/视频 pending</span>
              <span>音频 pending</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function StudioThinkingBlock({ data }) {
  return (
    <section className="studio-block thinking">
      <span className="thinking-dot" />
      <strong>{data?.text || "AI 正在思考..."}</strong>
    </section>
  );
}

function StudioErrorBlock({ data, onRetry }) {
  return (
    <section className="studio-block error">
      <strong>这一步失败了</strong>
      <p>{data?.message || "未知错误"}</p>
      <button className="secondary-action-button" type="button" onClick={onRetry}>回到这一步重试</button>
    </section>
  );
}

function ScriptSceneWorkbench({ script, selectedSceneId, onSelectScene, onUpdateScene, onUpdateSceneEdit }) {
  const scenes = script?.scenes || [];
  const totalDuration = Number(script?.config?.total_duration_seconds || 0);
  const fallbackDuration = scenes.length && totalDuration ? Math.round((totalDuration / scenes.length) * 10) / 10 : 3;
  const selectedScene = scenes.find((scene) => scene.id === selectedSceneId) || scenes[0];

  if (!selectedScene) {
    return <div className="empty-result">当前剧本还没有镜头。</div>;
  }

  const audioValue = cleanScriptValue(selectedScene.audio_narration || selectedScene.narration);

  return (
    <section className="script-workbench">
      <aside className="scene-master-list">
        <div className="scene-master-head">
          <strong>分镜列表</strong>
          <span>{scenes.length} 个原子镜头</span>
        </div>
        <div className="scene-master-items">
          {scenes.map((scene, index) => (
            <button
              className={`scene-master-item ${scene.id === selectedScene.id ? "active" : ""}`}
              key={scene.id || index}
              type="button"
              onClick={() => onSelectScene(scene.id)}
            >
              <span>Scene {index + 1}</span>
              <small>{sceneDuration(scene, fallbackDuration)}s</small>
              <p>{sceneSummary(scene)}</p>
            </button>
          ))}
        </div>
      </aside>

      <section className="scene-detail-desk">
        <header className="scene-detail-head">
          <div>
            <span>Scene {scenes.indexOf(selectedScene) + 1}</span>
            <h3>{selectedScene.title || "原子镜头"}</h3>
          </div>
          <Badge>预计 {sceneDuration(selectedScene, fallbackDuration)}s</Badge>
        </header>

        <div className="track-editor-grid">
          <article className="track-card visual-track-card">
            <div className="track-card-head">
              <strong>文案</strong>
              <span>给脚本表达、屏幕文字和镜头摘要使用</span>
            </div>
            <label>
              镜头概括
              <textarea
                value={cleanScriptValue(selectedScene.summary)}
                onChange={(event) => onUpdateScene(selectedScene.id, "summary", event.target.value)}
              />
            </label>
            <label>
              屏幕花字
              <textarea
                value={cleanScriptValue(selectedScene.onscreen_text)}
                onChange={(event) => onUpdateScene(selectedScene.id, "onscreen_text", event.target.value)}
              />
            </label>
          </article>

          <article className="track-card audio-track-card">
            <div className="track-card-head">
              <strong>音频需求</strong>
              <span>给 TTS、旁白和声音设计使用</span>
            </div>
            <label>
              配音文案
              <textarea
                value={audioValue}
                onChange={(event) => {
                  onUpdateScene(selectedScene.id, "audio_narration", event.target.value);
                }}
              />
            </label>
            <label>
              音频需求
              <textarea
                value={cleanScriptValue(selectedScene.edit?.pacing || selectedScene.emotional_beat)}
                onChange={(event) => onUpdateSceneEdit(selectedScene.id, "pacing", event.target.value)}
                placeholder="例如：温柔女声、轻环境音、结尾加提示音"
              />
            </label>
            <label>
              音频素材路径
              <input
                value={cleanScriptValue(selectedScene.assets?.audio_path)}
                onChange={(event) => onUpdateScene(selectedScene.id, "assets.audio_path", event.target.value)}
                placeholder="例如：D:\\素材\\scene1.wav"
              />
            </label>
          </article>

          <article className="track-card visual-track-card">
            <div className="track-card-head">
              <strong>画面素材需求</strong>
              <span>给生图、找素材和画面合成使用</span>
            </div>
            <label>
              生图提示词
              <textarea
                value={cleanScriptValue(selectedScene.visual_prompt || selectedScene.shot_description)}
                onChange={(event) => onUpdateScene(selectedScene.id, "visual_prompt", event.target.value)}
              />
            </label>
            <label>
              画面主体
              <textarea
                value={cleanScriptValue(selectedScene.asset_requirements?.main_subject)}
                onChange={(event) => onUpdateScene(selectedScene.id, "asset_requirements.main_subject", event.target.value)}
                placeholder="例如：女孩手拿奶茶在落叶街道回头"
              />
            </label>
            <label>
              背景 / 场景
              <textarea
                value={cleanScriptValue(selectedScene.asset_requirements?.background)}
                onChange={(event) => onUpdateScene(selectedScene.id, "asset_requirements.background", event.target.value)}
                placeholder="例如：傍晚街道、暖黄色灯光、秋叶飘落"
              />
            </label>
            <label>
              情绪 / 画面氛围
              <textarea
                value={cleanScriptValue(selectedScene.asset_requirements?.mood)}
                onChange={(event) => onUpdateScene(selectedScene.id, "asset_requirements.mood", event.target.value)}
                placeholder="例如：温柔、治愈、轻松、心动"
              />
            </label>
            <label>
              视频素材路径
              <input
                value={cleanScriptValue(selectedScene.assets?.video_path)}
                onChange={(event) => onUpdateScene(selectedScene.id, "assets.video_path", event.target.value)}
                placeholder="例如：D:\\素材\\scene1.mp4"
              />
            </label>
            <label>
              图片素材路径
              <input
                value={cleanScriptValue(selectedScene.assets?.image_path)}
                onChange={(event) => onUpdateScene(selectedScene.id, "assets.image_path", event.target.value)}
                placeholder="例如：D:\\素材\\scene1.png"
              />
            </label>
          </article>

          <article className="track-card audio-track-card">
            <div className="track-card-head">
              <strong>转场 / 动效要求</strong>
              <span>给 JyProject 映射到剪映工程使用</span>
            </div>
            <label>
              转场
              <input
                value={cleanScriptValue(selectedScene.edit?.transition)}
                onChange={(event) => onUpdateSceneEdit(selectedScene.id, "transition", event.target.value)}
                placeholder="例如：fade / mix / 淡入淡出 / 混合"
              />
            </label>
            <label>
              动画
              <input
                value={cleanScriptValue(selectedScene.edit?.animation)}
                onChange={(event) => onUpdateSceneEdit(selectedScene.id, "animation", event.target.value)}
                placeholder="例如：fadein / glitch / zoom_in"
              />
            </label>
            <label>
              镜头运动
              <input
                value={cleanScriptValue(selectedScene.edit?.camera)}
                onChange={(event) => onUpdateSceneEdit(selectedScene.id, "camera", event.target.value)}
                placeholder="例如：push in / pan left / pan right"
              />
            </label>
            <label>
              实际素材时长（秒）
              <input
                type="number"
                min="0"
                step="0.1"
                value={selectedScene.assets?.duration ?? 0}
                onChange={(event) => onUpdateScene(selectedScene.id, "assets.duration", Number(event.target.value))}
              />
            </label>
          </article>
        </div>
      </section>
    </section>
  );
}

function ScriptShotTable({ script }) {
  const scenes = script?.scenes || [];
  const totalDuration = Number(script?.config?.total_duration_seconds || 0);
  const defaultDuration = scenes.length && totalDuration ? Math.round((totalDuration / scenes.length) * 10) / 10 : 3;

  return (
    <section className="script-shot-table-panel">
      <div className="script-shot-toolbar">
        <div>
          <strong>脚本视图</strong>
          <span>{script?.config?.title || "未命名剧本"} · {scenes.length} 镜</span>
        </div>
        <Badge status="ready">{script?.config?.genre || "未分类"}</Badge>
      </div>
      <div className="script-shot-table-wrap">
        <table className="script-shot-table">
          <thead>
            <tr>
              <th>镜号</th>
              <th>时长</th>
              <th>标题</th>
              <th>镜头目标</th>
              <th>画面概括</th>
              <th>视觉提示词</th>
              <th>旁白</th>
              <th>屏幕文字</th>
              <th>转场</th>
              <th>动画</th>
              <th>节奏</th>
              <th>镜头运动</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {scenes.map((scene, index) => {
              const duration = scene.estimated_duration || scene.assets?.duration || defaultDuration;
              return (
                <tr key={scene.id || index}>
                  <td>{scene.id || index + 1}</td>
                  <td>{duration}</td>
                  <td>{scene.title || "-"}</td>
                  <td>{scene.scene_goal || "-"}</td>
                  <td>{scene.summary || "-"}</td>
                  <td>{scene.visual_prompt || "-"}</td>
                  <td>{scene.audio_narration || "-"}</td>
                  <td>{scene.onscreen_text || "-"}</td>
                  <td>{scene.edit?.transition || "-"}</td>
                  <td>{scene.edit?.animation || "-"}</td>
                  <td>{scene.edit?.pacing || "-"}</td>
                  <td>{scene.edit?.camera || "-"}</td>
                  <td>{scene.status || "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ScriptRecordRow({ item, onOpen, onDelete }) {
  const progress = Math.max(0, Math.min(100, item.progress || 0));
  const done = item.status === "done";
  const failed = item.status === "failed" || item.status === "error";
  const statusLabel = done ? "完成" : failed ? "失败" : `进度 ${progress}%`;

  return (
    <details className="script-record-row">
      <summary>
        <strong>{item.title || "未命名剧本"}</strong>
        <span>{item.genre || "未填写类型"} · {item.scene_count || 0} 幕 · {item.resolution || "-"}</span>
        <Badge status={done ? "done" : failed ? "error" : "running"}>{statusLabel}</Badge>
      </summary>
      <div className="script-record-detail">
        <p>{item.message || "暂无进度信息"}</p>
        {!done && !failed && (
          <div className="progress">
            <span style={{ width: `${progress}%` }} />
          </div>
        )}
        <div className="task-action-row">
          {item.project_id && (
            <button className="text-button" type="button" onClick={() => onOpen(item.project_id)}>
              打开剧本
            </button>
          )}
          {item.project_id && (
            <button className="text-button danger-text-button" type="button" onClick={() => onDelete(item.project_id)}>
              删除
            </button>
          )}
        </div>
      </div>
    </details>
  );
}

function DouyinSettingsPanel() {
  const [apiBase, setApiBase] = useState("http://127.0.0.1:8123");
  const [outputDir, setOutputDir] = useState("./data/runtime/douyin/downloads");
  const [cookie, setCookie] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchDouyinConfig()
      .then((config) => {
        setApiBase(config.api_base || "http://127.0.0.1:8123");
        setOutputDir(config.output_dir || "./data/runtime/douyin/downloads");
        setCookie(config.cookie || "");
      })
      .catch((err) => setError(err.message || String(err)));
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await saveDouyinConfig({ apiBase, outputDir, cookie });
      const synced = result.upstream_cookie_sync?.synced;
      setMessage(synced ? "配置已保存，并已同步上游 Cookie。" : "配置已保存。上游 Cookie 同步未确认，必要时重启上游服务。");
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>抖音采集配置</h2>
          <p>个人本地使用配置，保存到项目 `.env`。</p>
        </div>
        <Badge status="ready">本地</Badge>
      </div>
      <form className="douyin-settings-form" onSubmit={handleSubmit}>
        <label>
          上游 API 地址
          <input value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
        </label>
        <label>
          下载目录
          <input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} />
        </label>
        <label className="textarea-label">
          抖音 Cookie
          <textarea value={cookie} onChange={(event) => setCookie(event.target.value)} rows={7} />
        </label>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存配置"}
        </button>
      </form>
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}

function AiVideoSettingsPanel() {
  const [outputDir, setOutputDir] = useState("./data/runtime/ai_video_analysis");
  const [pipelineMode, setPipelineMode] = useState("evidence");
  const [transcriber, setTranscriber] = useState("auto");
  const [transcribeModel, setTranscribeModel] = useState("small");
  const [transcribeLanguage, setTranscribeLanguage] = useState("zh");
  const [transcribeDevice, setTranscribeDevice] = useState("cpu");
  const [transcribeComputeType, setTranscribeComputeType] = useState("int8");
  const [segmentSeconds, setSegmentSeconds] = useState(90);
  const [silentSegmentSeconds, setSilentSegmentSeconds] = useState(6);
  const [keyframeIntervalSeconds, setKeyframeIntervalSeconds] = useState(30);
  const [maxSegments, setMaxSegments] = useState(18);
  const [maxConcurrentTasks, setMaxConcurrentTasks] = useState(1);
  const [resumeEnabled, setResumeEnabled] = useState(true);
  const [highlightScreenshots, setHighlightScreenshots] = useState(true);
  const [gridColumns, setGridColumns] = useState(3);
  const [gridMaxFrames, setGridMaxFrames] = useState(9);
  const [gridCellWidth, setGridCellWidth] = useState(320);
  const [gridCellHeight, setGridCellHeight] = useState(180);
  const [ffmpegBinary, setFfmpegBinary] = useState("ffmpeg");
  const [ffprobeBinary, setFfprobeBinary] = useState("ffprobe");
  const [analysisPrompt, setAnalysisPrompt] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchAiVideoConfig()
      .then((config) => {
        setOutputDir(config.output_dir || "./data/runtime/ai_video_analysis");
        setPipelineMode(config.pipeline_mode || "evidence");
        setTranscriber(config.transcriber || "auto");
        setTranscribeModel(config.transcribe_model || "small");
        setTranscribeLanguage(config.transcribe_language || "zh");
        setTranscribeDevice(config.transcribe_device || "cpu");
        setTranscribeComputeType(config.transcribe_compute_type || "int8");
        setSegmentSeconds(config.segment_seconds || 90);
        setSilentSegmentSeconds(config.silent_segment_seconds || 6);
        setKeyframeIntervalSeconds(config.keyframe_interval_seconds || 30);
        setMaxSegments(config.max_segments || 18);
        setMaxConcurrentTasks(config.max_concurrent_tasks || 1);
        setResumeEnabled(Boolean(config.resume_enabled));
        setHighlightScreenshots(Boolean(config.highlight_screenshots));
        setGridColumns(config.grid_columns || 3);
        setGridMaxFrames(config.grid_max_frames || 9);
        setGridCellWidth(config.grid_cell_width || 320);
        setGridCellHeight(config.grid_cell_height || 180);
        setFfmpegBinary(config.ffmpeg_binary || "ffmpeg");
        setFfprobeBinary(config.ffprobe_binary || "ffprobe");
        setAnalysisPrompt(config.analysis_prompt || "");
      })
      .catch((err) => setError(err.message || String(err)));
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await saveAiVideoConfig({
        outputDir,
        pipelineMode,
        transcriber,
        transcribeModel,
        transcribeLanguage,
        transcribeDevice,
        transcribeComputeType,
        segmentSeconds,
        silentSegmentSeconds,
        keyframeIntervalSeconds,
        maxSegments,
        maxConcurrentTasks,
        resumeEnabled,
        highlightScreenshots,
        gridColumns,
        gridMaxFrames,
        gridCellWidth,
        gridCellHeight,
        ffmpegBinary,
        ffprobeBinary,
        analysisPrompt,
      });
      setMessage("AI 视频拆解配置已保存。模型连接仍使用全局 AI 模型配置。");
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>AI 视频拆解配置</h2>
          <p>配置证据包、转写、分段、关键帧和拆解提示词。模型连接请到“AI 模型”里统一设置。</p>
        </div>
        <Badge status={pipelineMode === "direct" ? "draft" : "ready"}>{pipelineMode}</Badge>
      </div>
      <form className="settings-form" onSubmit={handleSubmit}>
        <label>
          拆解流程
          <select value={pipelineMode} onChange={(event) => setPipelineMode(event.target.value)}>
            <option value="evidence">证据包优先：转写 + 关键帧 + 分段拆解</option>
            <option value="auto">自动：证据包失败时回退直接视频分析</option>
            <option value="direct">直接视频分析：跳过转写流程</option>
          </select>
        </label>
        <label>
          输出目录
          <input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} />
        </label>
        <label>
          转写器
          <select value={transcriber} onChange={(event) => setTranscriber(event.target.value)}>
            <option value="auto">自动选择</option>
            <option value="faster_whisper">faster-whisper</option>
            <option value="openai_whisper">openai-whisper</option>
          </select>
        </label>
        <label>
          Whisper 模型
          <input value={transcribeModel} onChange={(event) => setTranscribeModel(event.target.value)} placeholder="small / medium" />
        </label>
        <label>
          转写语言
          <input value={transcribeLanguage} onChange={(event) => setTranscribeLanguage(event.target.value)} placeholder="zh" />
        </label>
        <label>
          转写设备
          <select value={transcribeDevice} onChange={(event) => setTranscribeDevice(event.target.value)}>
            <option value="cpu">cpu</option>
            <option value="cuda">cuda</option>
            <option value="auto">auto</option>
          </select>
        </label>
        <label>
          计算精度
          <select value={transcribeComputeType} onChange={(event) => setTranscribeComputeType(event.target.value)}>
            <option value="int8">int8</option>
            <option value="float16">float16</option>
            <option value="float32">float32</option>
          </select>
        </label>
        <label>
          分段秒数
          <input type="number" min="30" max="600" value={segmentSeconds} onChange={(event) => setSegmentSeconds(event.target.value)} />
        </label>
        <label>
          无语音视觉切段秒数
          <input type="number" min="2" max="30" value={silentSegmentSeconds} onChange={(event) => setSilentSegmentSeconds(event.target.value)} />
          <span className="field-hint">适合 AI 小动物、音乐卡点、纯画面视频。无转写文本时按这个秒数切割。</span>
        </label>
        <label>
          关键帧间隔秒数
          <input type="number" min="5" max="300" value={keyframeIntervalSeconds} onChange={(event) => setKeyframeIntervalSeconds(event.target.value)} />
        </label>
        <label>
          最多 AI 拆解片段
          <input type="number" min="1" max="100" value={maxSegments} onChange={(event) => setMaxSegments(event.target.value)} />
        </label>
        <label>
          最大并发任务数
          <input type="number" min="1" max="4" value={maxConcurrentTasks} onChange={(event) => setMaxConcurrentTasks(event.target.value)} />
          <span className="field-hint">普通 CPU 建议保持 1。多任务会同时占用 Whisper、FFmpeg 和 API 调用，可能导致机器明显卡顿。</span>
        </label>
        <label>
          网格列数
          <input type="number" min="1" max="6" value={gridColumns} onChange={(event) => setGridColumns(event.target.value)} />
        </label>
        <label>
          每段最多关键帧
          <input type="number" min="1" max="24" value={gridMaxFrames} onChange={(event) => setGridMaxFrames(event.target.value)} />
        </label>
        <label>
          网格单格宽度
          <input type="number" min="120" max="960" value={gridCellWidth} onChange={(event) => setGridCellWidth(event.target.value)} />
        </label>
        <label>
          网格单格高度
          <input type="number" min="90" max="720" value={gridCellHeight} onChange={(event) => setGridCellHeight(event.target.value)} />
        </label>
        <label className="checkbox-field wide-field">
          <input type="checkbox" checked={resumeEnabled} onChange={(event) => setResumeEnabled(event.target.checked)} />
          <span>启用断点续跑：逐步复用已完成的音频、转写、关键帧、分段拆解和全局汇总</span>
        </label>
        <label className="checkbox-field wide-field">
          <input type="checkbox" checked={highlightScreenshots} onChange={(event) => setHighlightScreenshots(event.target.checked)} />
          <span>让 AI 标注爆点截图时间，并自动截取对应画面</span>
        </label>
        <label>
          FFmpeg
          <input value={ffmpegBinary} onChange={(event) => setFfmpegBinary(event.target.value)} placeholder="ffmpeg 或绝对路径" />
        </label>
        <label>
          FFprobe
          <input value={ffprobeBinary} onChange={(event) => setFfprobeBinary(event.target.value)} placeholder="ffprobe 或绝对路径" />
        </label>
        <label className="textarea-label">
          拆解提示词模板
          <textarea
            value={analysisPrompt}
            onChange={(event) => setAnalysisPrompt(event.target.value)}
            rows={12}
            placeholder="可使用变量：{desc}、{author}"
          />
          <span className="field-hint">可使用变量：{"{desc}"} 视频描述，{"{author}"} 作者。建议要求模型严格返回 JSON。</span>
        </label>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存拆解配置"}
        </button>
      </form>
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}

function LegacyAiProviderSettingsPanel() {
  const [provider, setProvider] = useState("gemini");
  const [accessMode, setAccessMode] = useState("official");
  const [nativeApiKey, setNativeApiKey] = useState("");
  const [relayBaseUrl, setRelayBaseUrl] = useState("https://jeniya.top");
  const [relayApiKey, setRelayApiKey] = useState("");
  const [model, setModel] = useState("gemini-2.5-flash");
  const [localEndpoint, setLocalEndpoint] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    fetchAiProviderConfig()
      .then((config) => {
        setProvider(config.provider || "gemini");
        setAccessMode(config.access_mode || "official");
        setNativeApiKey(config.native_api_key || "");
        setRelayBaseUrl(config.relay_base_url || "https://jeniya.top");
        setRelayApiKey(config.relay_api_key || "");
        setModel(config.model || "gemini-2.5-flash");
        setLocalEndpoint(config.local_endpoint || "");
      })
      .catch((err) => setError(err.message || String(err)));
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await saveAiProviderConfig({ provider, accessMode, nativeApiKey, relayBaseUrl, relayApiKey, model, localEndpoint });
      setMessage("全局 AI 连接配置已保存。之后新增 AI 工具会优先读取这组配置。");
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setError("");
    setTestResult(null);
    try {
      const result = await testAiProviderConfig({ provider, accessMode, nativeApiKey, relayBaseUrl, relayApiKey, model, localEndpoint });
      setTestResult(result);
    } catch (err) {
      setTestResult({
        ok: false,
        message: err.message || String(err),
      });
    } finally {
      setTesting(false);
    }
  }

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>AI 模型连接配置</h2>
          <p>全局 AI 工具共用。切换官方或中转站后，后续任务会按这里的配置执行。</p>
        </div>
        <Badge status={accessMode === "relay" ? "ready" : "draft"}>{accessMode}</Badge>
      </div>
      <form className="settings-form" onSubmit={handleSubmit}>
        <label>
          模型供应商
          <select value={provider} onChange={(event) => setProvider(event.target.value)}>
            <option value="gemini">gemini</option>
            <option value="openai">openai</option>
            <option value="local">local</option>
          </select>
        </label>
        <label>
          接入方式
          <select value={accessMode} onChange={(event) => setAccessMode(event.target.value)}>
            <option value="official">原生官方</option>
            <option value="relay">中转站</option>
          </select>
        </label>
        <label>
          原生 API Key
          <input type="password" value={nativeApiKey} onChange={(event) => setNativeApiKey(event.target.value)} />
        </label>
        <label>
          中转站 Base URL
          <input value={relayBaseUrl} onChange={(event) => setRelayBaseUrl(event.target.value)} />
        </label>
        <label>
          中转站 Token
          <input type="password" value={relayApiKey} onChange={(event) => setRelayApiKey(event.target.value)} />
        </label>
        <label>
          默认模型
          <input value={model} onChange={(event) => setModel(event.target.value)} />
        </label>
        <label className="wide-field">
          本地模型地址
          <input value={localEndpoint} onChange={(event) => setLocalEndpoint(event.target.value)} placeholder="http://127.0.0.1:..." />
        </label>
        <button className="secondary-action-button" type="button" onClick={handleTest} disabled={testing}>
          {testing ? "测试中" : "测试连接"}
        </button>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存全局 AI 配置"}
        </button>
      </form>
      {testResult && (
        <div className={testResult.ok ? "running-note" : "error-box"}>
          {testResult.ok ? "测试成功" : "测试失败"}：{testResult.message}
          {testResult.sample ? ` 返回：${testResult.sample}` : ""}
        </div>
      )}
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}

function AiProviderSettingsPanel() {
  const [configs, setConfigs] = useState({
    gemini: {
      provider: "gemini",
      accessMode: "official",
      nativeApiKey: "",
      relayBaseUrl: "https://jeniya.top",
      relayApiKey: "",
      model: "gemini-2.5-flash",
      models: ["gemini-2.5-flash", "gemini-2.0-flash"],
      apiFormat: "generate_content",
      localEndpoint: "",
    },
    openai: {
      provider: "openai",
      accessMode: "official",
      nativeApiKey: "",
      relayBaseUrl: "",
      relayApiKey: "",
      model: "gpt-4.1-mini",
      models: ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"],
      apiFormat: "responses",
      localEndpoint: "",
    },
    simple_relay: {
      provider: "simple_relay",
      accessMode: "relay",
      nativeApiKey: "",
      relayBaseUrl: "",
      relayApiKey: "",
      model: "gemini-2.5-flash",
      models: ["gemini-2.5-flash", "gemini-2.0-flash"],
      apiFormat: "gemini_generate_content",
      localEndpoint: "",
    },
    yunwu: {
      provider: "yunwu",
      accessMode: "relay",
      nativeApiKey: "",
      relayBaseUrl: "https://yunwu.ai",
      relayApiKey: "",
      model: "gemini-2.5-flash",
      models: ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro", "gpt-4o-mini"],
      apiFormat: "gemini_generate_content",
      localEndpoint: "",
    },
    deepseek: {
      provider: "deepseek",
      accessMode: "official",
      nativeApiKey: "",
      relayBaseUrl: "https://api.deepseek.com",
      relayApiKey: "",
      model: "deepseek-chat",
      models: ["deepseek-chat", "deepseek-reasoner"],
      apiFormat: "chat_completions",
      localEndpoint: "",
    },
    volcano: {
      provider: "volcano",
      accessMode: "official",
      nativeApiKey: "",
      relayBaseUrl: "https://ark.cn-beijing.volces.com/api/v3",
      relayApiKey: "",
      model: "",
      models: [],
      apiFormat: "chat_completions",
      localEndpoint: "",
    },
    local: {
      provider: "local",
      accessMode: "local",
      nativeApiKey: "",
      relayBaseUrl: "",
      relayApiKey: "",
      model: "",
      models: [],
      apiFormat: "local",
      localEndpoint: "",
    },
  });
  const [selectedProvider, setSelectedProvider] = useState("gemini");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busyProvider, setBusyProvider] = useState("");
  const [testResults, setTestResults] = useState({});

  useEffect(() => {
    fetchAiProviderConfig()
      .then((config) => {
        const providers = config.providers || {};
        setSelectedProvider(config.active_provider || "gemini");
        setConfigs((current) => ({
          gemini: normalizeAiProviderConfig(providers.gemini, current.gemini),
          openai: normalizeAiProviderConfig(providers.openai, current.openai),
          simple_relay: normalizeAiProviderConfig(providers.simple_relay, current.simple_relay),
          yunwu: normalizeAiProviderConfig(providers.yunwu, current.yunwu),
          deepseek: normalizeAiProviderConfig(providers.deepseek, current.deepseek),
          volcano: normalizeAiProviderConfig(providers.volcano, current.volcano),
          local: normalizeAiProviderConfig(providers.local, current.local),
        }));
      })
      .catch((err) => setError(err.message || String(err)));
  }, []);

  function updateProviderConfig(providerId, key, value) {
    setConfigs((current) => ({
      ...current,
      [providerId]: {
        ...current[providerId],
        [key]: value,
      },
    }));
  }

  async function handleSave(providerId) {
    setBusyProvider(`save:${providerId}`);
    setError("");
    setMessage("");
    try {
      await saveAiProviderConfig(configs[providerId]);
      setMessage(`${providerId} 配置已保存。`);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusyProvider("");
    }
  }

  async function handleTest(providerId) {
    setBusyProvider(`test:${providerId}`);
    setError("");
    setTestResults((current) => ({ ...current, [providerId]: null }));
    try {
      const result = await testAiProviderConfig(configs[providerId]);
      setTestResults((current) => ({ ...current, [providerId]: result }));
    } catch (err) {
      setTestResults((current) => ({
        ...current,
        [providerId]: { ok: false, message: err.message || String(err) },
      }));
    } finally {
      setBusyProvider("");
    }
  }

  const providerOptions = [
    ["gemini", "Gemini"],
    ["openai", "OpenAI"],
    ["simple_relay", "简单中转站"],
    ["yunwu", "云雾 API"],
    ["deepseek", "DeepSeek"],
    ["volcano", "火山引擎"],
    ["local", "本地或其他 API"],
  ];
  const providerMeta = {
    gemini: ["Gemini API", "支持 Google 原生 Gemini 和 Gemini 原生格式中转站。"],
    openai: ["OpenAI API", "原生路线使用 Responses API；中转站可切换 Responses 或 Chat Completions 兼容格式。"],
    simple_relay: ["简单中转站", "推荐用于视频工具：选择 Gemini 原生 generateContent，可绕开官方账号额度。"],
    yunwu: ["云雾 API", "根据云雾文档接入：支持 Gemini 原生 generateContent 和 OpenAI-compatible Chat Completions。"],
    deepseek: ["DeepSeek API", "DeepSeek 使用 OpenAI-compatible Chat Completions 格式。"],
    volcano: ["火山引擎 API", "火山方舟使用 OpenAI-compatible Chat Completions 格式。"],
    local: ["本地或其他 API", "预留给本地模型、局域网服务或后续其他服务。"],
  };
  const selectedMeta = providerMeta[selectedProvider] || providerMeta.gemini;

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>AI 模型 API 配置</h2>
          <p>每个供应商独立保存。API Key 明文显示，方便个人本地调试和切换。</p>
        </div>
        <Badge status="ready">{selectedProvider}</Badge>
      </div>
      <div className="model-settings-layout">
        <aside className="provider-list-panel">
          {providerOptions.map(([value, label]) => {
            const item = configs[value] || {};
            return (
              <button
                className={`provider-list-item ${selectedProvider === value ? "active" : ""}`}
                key={value}
                type="button"
                onClick={() => setSelectedProvider(value)}
              >
                <span>{label}</span>
                <small>{item.model || "未设置模型"}</small>
              </button>
            );
          })}
        </aside>
        <AiProviderConfigCard
          title={selectedMeta[0]}
          description={selectedMeta[1]}
          config={configs[selectedProvider] || configs.gemini}
          providerId={selectedProvider}
          busyProvider={busyProvider}
          testResult={testResults[selectedProvider]}
          onChange={updateProviderConfig}
          onSave={handleSave}
          onTest={handleTest}
        />
      </div>
      <label className="provider-selector">
        当前全局 AI 模型
        <select value={selectedProvider} onChange={(event) => setSelectedProvider(event.target.value)}>
          {providerOptions.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <AiProviderConfigCard
        title={selectedMeta[0]}
        description={selectedMeta[1]}
        config={configs[selectedProvider] || configs.gemini}
        providerId={selectedProvider}
        busyProvider={busyProvider}
        testResult={testResults[selectedProvider]}
        onChange={updateProviderConfig}
        onSave={handleSave}
        onTest={handleTest}
      />
      {false && (
        <>
      <AiProviderConfigCard
        title="OpenAI API"
        description="原生路线使用 Responses API；中转站可切换 Responses 或 Chat Completions 兼容格式。"
        config={configs.openai}
        providerId="openai"
        busyProvider={busyProvider}
        testResult={testResults.openai}
        onChange={updateProviderConfig}
        onSave={handleSave}
        onTest={handleTest}
      />
      <AiProviderConfigCard
        title="Gemini API"
        description="支持 Google 原生 Gemini 和 Gemini 原生格式中转站。"
        config={configs.gemini}
        providerId="gemini"
        busyProvider={busyProvider}
        testResult={testResults.gemini}
        onChange={updateProviderConfig}
        onSave={handleSave}
        onTest={handleTest}
      />
      <AiProviderConfigCard
        title="本地或其他 API"
        description="预留给本地模型、局域网服务或后续其他 OpenAI-compatible 服务。"
        config={configs.local}
        providerId="local"
        busyProvider={busyProvider}
        testResult={testResults.local}
        onChange={updateProviderConfig}
        onSave={handleSave}
        onTest={handleTest}
      />
        </>
      )}
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}

function AiProviderConfigCard({ title, description, config, providerId, busyProvider, testResult, onChange, onSave, onTest }) {
  const isBusySaving = busyProvider === `save:${providerId}`;
  const isBusyTesting = busyProvider === `test:${providerId}`;
  const isLocal = providerId === "local";
  const isOpenAI = providerId === "openai";
  const isSimpleRelay = providerId === "simple_relay" || providerId === "yunwu";
  const isFixedOpenAICompatible = providerId === "deepseek" || providerId === "volcano";
  const showAccessMode = !isLocal && !isSimpleRelay && !isFixedOpenAICompatible;
  const showApiFormat = isOpenAI || isSimpleRelay;
  const showNativeKey = !isLocal && !isSimpleRelay;
  const showRelayFields = !isLocal && (config.accessMode === "relay" || isSimpleRelay || isFixedOpenAICompatible);
  const modelsText = (config.models || []).join("\n");
  return (
    <div className="settings-subpanel">
      <div className="panel-header compact-header">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        <Badge status={config.accessMode === "relay" ? "ready" : "draft"}>{config.accessMode}</Badge>
      </div>
      <form className="settings-form" onSubmit={(event) => event.preventDefault()}>
        {showAccessMode && (
          <label>
            接入方式
            <select value={config.accessMode} onChange={(event) => onChange(providerId, "accessMode", event.target.value)}>
              <option value="official">原生官方</option>
              <option value="relay">中转站</option>
            </select>
          </label>
        )}
        {showApiFormat && (
          <label>
            API 格式
            <select value={config.apiFormat} onChange={(event) => onChange(providerId, "apiFormat", event.target.value)}>
              <option value="responses">Responses API</option>
              <option value="chat_completions">Chat Completions</option>
              {isSimpleRelay && <option value="gemini_generate_content">Gemini 原生 generateContent</option>}
            </select>
          </label>
        )}
        {showNativeKey && (
          <label>
            {isFixedOpenAICompatible ? "API Key" : "原生 API Key"}
            <input value={config.nativeApiKey} onChange={(event) => onChange(providerId, "nativeApiKey", event.target.value)} />
          </label>
        )}
        {showRelayFields && (
          <label>
            {isSimpleRelay ? "Base URL" : "API Base URL"}
            <input value={config.relayBaseUrl} onChange={(event) => onChange(providerId, "relayBaseUrl", event.target.value)} placeholder="https://..." />
          </label>
        )}
        {(isOpenAI && config.accessMode === "relay") || isSimpleRelay ? (
          <label>
            {isSimpleRelay ? "API Key" : "中转站 API Key"}
            <input value={config.relayApiKey} onChange={(event) => onChange(providerId, "relayApiKey", event.target.value)} />
          </label>
        ) : null}
        <label>
          默认模型
          {(config.models || []).length ? (
            <select value={config.model} onChange={(event) => onChange(providerId, "model", event.target.value)}>
              {(config.models || []).map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          ) : (
            <input value={config.model} onChange={(event) => onChange(providerId, "model", event.target.value)} />
          )}
        </label>
        <label className="textarea-label">
          模型列表
          <textarea
            value={modelsText}
            onChange={(event) => {
              const models = event.target.value
                .split(/\n|,/)
                .map((item) => item.trim())
                .filter(Boolean);
              onChange(providerId, "models", models);
              if (!models.includes(config.model)) {
                onChange(providerId, "model", models[0] || "");
              }
            }}
            rows={5}
            placeholder="每行一个模型，例如 gpt-4.1-mini"
          />
        </label>
        {isLocal && (
          <label className="wide-field">
            本地 API 地址
            <input value={config.localEndpoint} onChange={(event) => onChange(providerId, "localEndpoint", event.target.value)} placeholder="http://127.0.0.1:..." />
          </label>
        )}
        <button className="secondary-action-button" type="button" onClick={() => onTest(providerId)} disabled={isBusyTesting}>
          {isBusyTesting ? "测试中" : "测试连接"}
        </button>
        <button className="primary-button" type="button" onClick={() => onSave(providerId)} disabled={isBusySaving}>
          {isBusySaving ? "保存中" : `保存 ${title}`}
        </button>
      </form>
      {testResult && (
        <div className={testResult.ok ? "running-note" : "error-box"}>
          {testResult.ok ? "测试成功" : "测试失败"}：{testResult.message}
          {testResult.sample ? ` 返回：${testResult.sample}` : ""}
        </div>
      )}
    </div>
  );
}

function normalizeAiProviderConfig(value, fallback) {
  if (!value) {
    return fallback;
  }
  return {
    ...fallback,
    provider: value.provider || fallback.provider,
    accessMode: value.access_mode || fallback.accessMode,
    nativeApiKey: value.native_api_key || "",
    relayBaseUrl: value.relay_base_url || fallback.relayBaseUrl,
    relayApiKey: value.relay_api_key || "",
    model: value.model || fallback.model,
    models: Array.isArray(value.models) ? value.models : fallback.models || [],
    apiFormat: value.api_format || fallback.apiFormat,
    localEndpoint: value.local_endpoint || fallback.localEndpoint,
  };
}

function AiPromptReverseSettingsPanel() {
  const [outputDir, setOutputDir] = useState("./data/runtime/ai_prompt_reverse");
  const [pipelineMode, setPipelineMode] = useState("evidence");
  const [maxSegments, setMaxSegments] = useState(18);
  const [reversePrompt, setReversePrompt] = useState("");
  const [statusInfo, setStatusInfo] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchAiPromptReverseConfig()
      .then((config) => {
        setOutputDir(config.output_dir || "./data/runtime/ai_prompt_reverse");
        setPipelineMode(config.pipeline_mode || "evidence");
        setMaxSegments(config.max_segments || 18);
        setReversePrompt(config.reverse_prompt || "");
      })
      .catch((err) => setError(err.message || String(err)));
    fetchAiPromptReverseStatus()
      .then(setStatusInfo)
      .catch(() => setStatusInfo(null));
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await saveAiPromptReverseConfig({ outputDir, pipelineMode, maxSegments, reversePrompt });
      setMessage("AI 提示词反推配置已保存。重启主后端后会稳定生效。");
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>AI 提示词反推配置</h2>
          <p>配置复刻流程、片段上限和反推要求。模型连接请到“AI 模型”里统一设置。</p>
        </div>
        <Badge status={pipelineMode === "direct" ? "draft" : "ready"}>{pipelineMode}</Badge>
      </div>
      {statusInfo && (
        <div className={`task-sync-banner ${statusInfo.ready ? "" : "error"}`}>
          反推依赖：FFmpeg {statusInfo.pipeline?.ffmpeg_ready ? "可用" : "不可用"} · FFprobe{" "}
          {statusInfo.pipeline?.ffprobe_ready ? "可用" : "不可用"} · 转写器 {statusInfo.pipeline?.transcriber_ready ? "可用" : "不可用"}
        </div>
      )}
      <form className="settings-form" onSubmit={handleSubmit}>
        <label>
          输出目录
          <input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} />
        </label>
        <label>
          反推模式
          <select value={pipelineMode} onChange={(event) => setPipelineMode(event.target.value)}>
            <option value="evidence">证据管线复刻</option>
            <option value="auto">证据失败后回退整段视频</option>
            <option value="direct">整段视频直传</option>
          </select>
          <span className="field-hint">建议使用证据管线复刻：转写 + 分段 + 关键帧网格 + 逐镜头反推。</span>
        </label>
        <label>
          最大反推片段数
          <input type="number" min="1" max="100" value={maxSegments} onChange={(event) => setMaxSegments(event.target.value)} />
          <span className="field-hint">数值越高越接近完整复刻，但耗时和 API 成本也越高。</span>
        </label>
        <label className="textarea-label">
          反推提示词模板
          <textarea
            value={reversePrompt}
            onChange={(event) => setReversePrompt(event.target.value)}
            rows={12}
            placeholder="可使用变量：{desc}、{author}"
          />
          <span className="field-hint">可使用变量：{"{desc}"} 视频描述，{"{author}"} 作者。Gemini Key 复用上方 AI 视频拆解配置。</span>
        </label>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存反推配置"}
        </button>
      </form>
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}

function JianyingDraftSettingsPanel() {
  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>剪映草稿说明</h2>
          <p>草稿生成已经统一收口到 `剪映 Skill` 主流程，这里只保留查看路径、命名规则和使用说明，不再重复提供第二套生成入口。</p>
        </div>
        <Badge status="ready">Unified</Badge>
      </div>

      <section className="collector-card">
        <h3>当前统一链路</h3>
        <div className="step-list">
          {[
            ["1", "AI 生成内部结构规范", "先得到可继续补素材、补配音并生成草稿的结构结果。"],
            ["2", "输入第三方素材路径", "可以粘贴视频、图片、音频路径，也可以只给一部分。"],
            ["3", "自动补齐并生成 JyProject 草稿", "缺失素材可交给 AI 补齐，生成前支持手动修改草稿名称。"],
          ].map(([index, name, desc]) => (
            <article className="step-item" key={index}>
              <span>{index}</span>
              <div>
                <strong>{name}</strong>
                <p>{desc}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="collector-card">
        <h3>命名规则</h3>
        <div className="workflow-summary-grid compact">
          <article className="workflow-summary-card">
            <strong>默认命名</strong>
            <p>系统默认按日期时间命名，例如 `2026年5月9日16时22分`，方便你在剪映草稿目录里一眼识别。</p>
          </article>
          <article className="workflow-summary-card">
            <strong>生成前可改</strong>
            <p>在 `剪映 Skill` 的“补齐素材并生成草稿”步骤里，可以直接修改草稿名称，再输出到剪映。</p>
          </article>
          <article className="workflow-summary-card">
            <strong>查看方式</strong>
            <p>草稿生成后，到“查看草稿”里按项目点开，会看到可读解释，不只是原始 JSON。</p>
          </article>
        </div>
      </section>

      <section className="collector-card">
        <h3>建议使用</h3>
        <div className="script-action-strip">
          <button className="primary-button" type="button" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
            返回顶部
          </button>
          <span className="field-hint">主操作请使用左侧导航中的 `剪映 Skill` 与 `查看草稿`。</span>
        </div>
      </section>
    </section>
  );
}

function JianyingEditorSdkPanel({ activeView = "overview" }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    fetchJianyingEditorSdkStatus()
      .then((data) => {
        if (mounted) {
          setStatus(data);
          setError("");
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(err.message || String(err));
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const guideUrl = `${API_BASE}/api/tools/jianying-editor-sdk/page`;
  const entries = status?.entries || [];
  const checks = status?.checks || {};
  const capabilityItems = status?.capability_matrix || [];
  const warnings = status?.warnings || [];
  const readinessItems = [
    ["JyProject 导入", checks.jyproject_import],
    ["必要依赖", checks.sdk_requirements],
    ["可选依赖", checks.optional_requirements],
    ["平台限制", checks.platform],
  ];
  const workflowCapabilityItems = (capabilityItems || []).filter((item) => item?.implemented || item?.available);
  const sdkStateLabel = status?.ready ? "可接入" : status ? "需补环境" : "检查中";

  return (
    <section className="jianying-sdk-panel sdk-reference-panel">
      <section className="panel sdk-hero-panel">
        <div className="panel-header">
          <div>
            <h2>开发者参考</h2>
            <p>这里不再承担主操作流程，只说明当前本地 SDK 是否能支撑“结构规范 到 素材补齐 到 JyProject 草稿”这条链路。</p>
          </div>
          <Badge status={status?.ready ? "ready" : status ? "draft" : "draft"}>{sdkStateLabel}</Badge>
        </div>
        {error ? (
          <div className="error-box">{error}</div>
        ) : (
          <div className="sdk-summary-grid">
            <div>
              <span>本地路径</span>
              <strong>{status?.root || "sdks/jianying-editor-skill"}</strong>
            </div>
            <div>
              <span>上游仓库</span>
              <a href={status?.repo_url || "https://github.com/luoluoluo22/jianying-editor-skill"} target="_blank" rel="noreferrer">
                GitHub
              </a>
            </div>
            <div>
              <span>版本</span>
              <strong>{status?.version || "读取中"}</strong>
            </div>
            <div>
              <span>锁定模式</span>
              <strong>{status?.lock?.mode || "未读取"}</strong>
            </div>
          </div>
        )}
      </section>

      <section className="sdk-reference-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>链路判断</h2>
              <p>重点看当前项目是否具备你要的三步闭环。</p>
            </div>
          </div>
          <div className="sdk-entry-list">
            <article className="sdk-entry">
              <div>
                <strong>1. AI 生成结构规范</strong>
                <p>前端主流程已改成结构段/时间线导向，不再要求用户在页面里逐镜头编辑。</p>
              </div>
              <Badge status="ready">已对齐</Badge>
            </article>
            <article className="sdk-entry">
              <div>
                <strong>2. 输入第三方素材路径</strong>
                <p>支持直接粘贴视频、图片、音频路径，也允许不全量手工准备。</p>
              </div>
              <Badge status="ready">已对齐</Badge>
            </article>
            <article className="sdk-entry">
              <div>
                <strong>3. 自动补齐并生成 `JyProject` 草稿</strong>
                <p>可调用素材补齐与草稿生成链路；字幕、BGM 等保持可选，不强行塞进主操作面板。</p>
              </div>
              <Badge status={status?.ready ? "ready" : "draft"}>{status?.ready ? "可执行" : "依赖待确认"}</Badge>
            </article>
          </div>
          {warnings.length > 0 && <div className="running-note">{warnings.join(" ")}</div>}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>环境状态</h2>
              <p>只保留这条主链路相关的环境信号。</p>
            </div>
          </div>
          <div className="sdk-entry-list">
            {readinessItems.map(([label, check]) => (
              <article className="sdk-entry" key={label}>
                <div>
                  <strong>{label}</strong>
                  <p>{check?.message || "等待状态接口返回"}</p>
                </div>
                <Badge status={check?.ok ? "ready" : "draft"}>{check?.ok ? "通过" : "待确认"}</Badge>
              </article>
            ))}
          </div>
        </section>
      </section>

      <section className="sdk-reference-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>当前接入能力</h2>
              <p>这里只展示已接入或已声明的能力，不再把它们全部做成操作工作台。</p>
            </div>
          </div>
          <div className="sdk-entry-list">
            {workflowCapabilityItems.length ? workflowCapabilityItems.map((item) => (
              <article className="sdk-entry" key={item.key}>
                <div>
                  <strong>{item.label}</strong>
                  <p>{item.message || (item.available ? "当前环境可尝试使用" : "当前环境未完全验证")}</p>
                  <div className="sdk-capability-meta">
                    <code>{item.endpoint}</code>
                    <span>{item.invocation}</span>
                  </div>
                </div>
                <Badge status={item.available ? "ready" : "draft"}>{item.available ? "可用" : "已接入"}</Badge>
              </article>
            )) : <div className="empty-result">能力矩阵尚未返回。</div>}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>SDK 入口</h2>
              <p>保留源码入口和网页说明，方便后续继续接 SDK 能力。</p>
            </div>
            <a className="text-button" href={guideUrl} target="_blank" rel="noreferrer">
              打开网页说明
            </a>
          </div>
          <div className="sdk-entry-list">
            {entries.length ? entries.map((entry) => (
              <article className="sdk-entry" key={entry.relative_path}>
                <div>
                  <strong>{entry.name}</strong>
                  <p>{entry.description}</p>
                  <code>{entry.relative_path}</code>
                </div>
                <Badge status={entry.exists ? "ready" : "error"}>{entry.exists ? "已找到" : "缺失"}</Badge>
              </article>
            )) : <div className="empty-result">正在读取 SDK 入口...</div>}
          </div>
        </section>
      </section>
    </section>
  );
}

function JianyingNaturalScriptPanel() {
  const [input, setInput] = useState("帮我写一段关于秋天第一杯奶茶的短视频文案，配温柔女声旁白和字幕，再找个温馨 BGM，30 秒，5 个分镜。");
  const [title, setTitle] = useState("");
  const [creativePreset, setCreativePreset] = useState("");
  const [durationSeconds, setDurationSeconds] = useState("");
  const [sceneCount, setSceneCount] = useState("");
  const [resolution, setResolution] = useState("");
  const [generationMode, setGenerationMode] = useState("local");
  const [provider, setProvider] = useState("");
  const [subtitleFromNarration, setSubtitleFromNarration] = useState(false);
  const [enableBgm, setEnableBgm] = useState(true);
  const [allowAutoFill, setAllowAutoFill] = useState(true);
  const [autoGenerateAudio, setAutoGenerateAudio] = useState(true);
  const [autoGenerateImages, setAutoGenerateImages] = useState(true);
  const [customBgmKeywords, setCustomBgmKeywords] = useState("");
  const [externalMaterials, setExternalMaterials] = useState("");
  const [draftName, setDraftName] = useState(() => createDateDraftName());
  const [task, setTask] = useState(null);
  const [result, setResult] = useState(null);
  const [scriptProjects, setScriptProjects] = useState([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [savingScript, setSavingScript] = useState(false);
  const [preparingAssets, setPreparingAssets] = useState(false);
  const [buildingSdkDraft, setBuildingSdkDraft] = useState(false);
  const [draftBuildResult, setDraftBuildResult] = useState(null);
  const [prepareReport, setPrepareReport] = useState(null);

  useEffect(() => {
    loadScriptProjects().catch(() => {});
  }, []);

  useEffect(() => {
    if (!task?.id || ["done", "failed", "error"].includes(task.status)) return undefined;
    let mounted = true;
    const timer = window.setInterval(async () => {
      try {
        const next = await fetchTask(task.id);
        if (!mounted) return;
        setTask(next);
        if (next.status === "done") {
          const nextResult = next.result || next.result_json || null;
          setResult(nextResult);
          loadScriptProjects().catch(() => {});
        }
        if (next.status === "failed" || next.status === "error") {
          setError(next.error || next.message || "生成失败");
        }
      } catch (err) {
        if (mounted) setError(err.message || String(err));
      }
    }, 1200);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [task]);

  async function loadScriptProjects() {
    const data = await fetchVideoScripts();
    setScriptProjects(data.projects || []);
  }

  async function handleOpenScript(projectId) {
    setError("");
    try {
      const data = await fetchVideoScript(projectId);
      setResult(data);
      setDraftName(createDateDraftName());
      setDraftBuildResult(null);
      setPrepareReport(data?.prepare_report || null);
    } catch (err) {
      setError(err.message || String(err));
    }
  }

  async function handleDeleteScript(projectId) {
    if (!window.confirm("确认删除这个结构化剧本吗？关联的剧本生成任务记录也会一起清理。")) {
      return;
    }
    setError("");
    try {
      await deleteVideoScript(projectId);
      if ((result?.project_id || result?.script?.project_id) === projectId) {
        setResult(null);
      }
      await loadScriptProjects();
    } catch (err) {
      setError(err.message || String(err));
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setResult(null);
    setDraftName(createDateDraftName());
    setDraftBuildResult(null);
    setPrepareReport(null);
    try {
      const created = await generateJianyingNaturalScript({
        input,
        title,
        creativePreset,
        durationSeconds,
        sceneCount,
        resolution,
        generationMode,
        provider,
      });
      setTask(created);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSubmitting(false);
    }
  }

  const script = result?.script || result?.result?.script;
  const parsed = result?.parsed_input;
  const currentMode = result?.generation_mode || result?.metadata?.generation_mode || "local";
  const currentProjectId = result?.project_id || script?.project_id || "";
  const workflowFlags = deriveOptionalWorkflowFlags(script);
  const readySceneCount = script?.scenes?.filter((scene) => ["ready", "partial_ready"].includes(scene.status)).length || 0;
  const totalSceneCount = script?.scenes?.length || 0;
  const hasExternalMaterials = Boolean(externalMaterials.trim());
  const hasExistingAssets = Boolean(
    (script?.scenes || []).some((scene) =>
      Boolean(
        cleanScriptValue(scene?.assets?.video_path) ||
        cleanScriptValue(scene?.assets?.image_path) ||
        cleanScriptValue(scene?.assets?.audio_path),
      ),
    ),
  );
  const aiAutoFillEnabled = allowAutoFill && (autoGenerateAudio || autoGenerateImages);
  const structureCountLabel = totalSceneCount || Number(sceneCount || 0) || 0;
  const structureHints = [
    workflowFlags.hasNarration ? "含旁白线" : "",
    workflowFlags.hasOnscreenText ? "含屏幕文字" : "",
    workflowFlags.hasVisualStyle ? "含视觉风格约束" : "",
    workflowFlags.hasBgm && enableBgm ? "含 BGM 建议" : "",
  ].filter(Boolean);
  const timelineItems = (() => {
    let cursor = 0;
    return (script?.scenes || []).map((scene, index) => {
      const duration = sceneDuration(scene);
      const start = cursor;
      const end = cursor + duration;
      cursor = end;
      return {
        id: scene.id || `segment-${index + 1}`,
        index,
        title: scene.title || `结构段 ${index + 1}`,
        start,
        end,
        duration,
        summary: cleanScriptValue(
          scene?.summary ||
          scene?.audio_narration ||
          scene?.narration ||
          scene?.onscreen_text ||
          scene?.visual_prompt,
        ).slice(0, 96) || "等待后续补齐内容",
        status: scene?.status || "draft",
      };
    });
  })();

  function collectSourcePaths() {
    return [
      ...(Array.isArray(result?.parsed_input?.source_paths) ? result.parsed_input.source_paths : []),
      ...(Array.isArray(result?.metadata?.source_paths) ? result.metadata.source_paths : []),
      ...externalMaterials.split(/\r?\n|[,，;]/).map((item) => item.trim()).filter(Boolean),
    ].filter(Boolean);
  }

  async function handleSaveCurrentScript() {
    if (!currentProjectId || !script) return null;
    setSavingScript(true);
    setError("");
    try {
      const nextScript = {
        ...script,
        bible: {
          ...createScriptFallbackBible(script),
          ...(script?.bible || {}),
          ...(enableBgm ? { bgm_keywords: customBgmKeywords.trim() || deriveBgmKeywords(script) } : { bgm_keywords: "" }),
        },
      };
      const saved = await saveVideoScript(currentProjectId, nextScript);
      setResult(saved);
      return saved;
    } catch (err) {
      setError(err.message || String(err));
      return null;
    } finally {
      setSavingScript(false);
    }
  }

  async function handleBuildSdkDraftFromCurrentScript() {
    if (!currentProjectId || !script) return;
    setBuildingSdkDraft(true);
    setError("");
    setDraftBuildResult(null);
    try {
      let working = (await handleSaveCurrentScript()) || result;
      const sourcePaths = collectSourcePaths();
      if (sourcePaths.length || aiAutoFillEnabled) {
        const prepared = await prepareVideoScriptAssets(currentProjectId, {
          script: working?.script || script,
          sourcePaths,
          resolveLocalMaterials: sourcePaths.length > 0,
          generateAudio: allowAutoFill && autoGenerateAudio,
          generateImages: allowAutoFill && autoGenerateImages,
          generateVideos: false,
          overwriteExisting: false,
        });
        working = prepared;
        setResult(prepared);
        setPrepareReport(prepared?.prepare_report || null);
      } else if (!hasExistingAssets) {
        throw new Error("请先输入第三方素材路径，或开启 AI 自动补齐。");
      }
      const latestScript = working?.script || script;
      const response = await createJianyingDraftFromScript({
        name: draftName.trim() || createDateDraftName(),
        script: latestScript,
        engine: "sdk",
        includeOnscreenText: true,
        subtitleFromNarration,
        defaultMediaDurationSeconds: 3,
        textStyle: {
          size: 5,
          bold: true,
          color: [1, 1, 1],
          alpha: 1,
          align: 1,
          auto_wrapping: true,
          max_line_width: 0.82,
        },
        textBackground: {
          color: "#000000",
          alpha: 0.35,
          round_radius: 0.08,
          height: 0.14,
          width: 0.14,
        },
      });
      setDraftBuildResult(response);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBuildingSdkDraft(false);
    }
  }

  async function handlePrepareAssets() {
    if (!currentProjectId || !script) return;
    setPreparingAssets(true);
    setError("");
    setDraftBuildResult(null);
    try {
      const sourcePaths = collectSourcePaths();
      if (!sourcePaths.length && !aiAutoFillEnabled) {
        throw new Error("请先输入第三方素材路径，或开启 AI 自动补齐。");
      }
      const response = await prepareVideoScriptAssets(currentProjectId, {
        script,
        sourcePaths,
        resolveLocalMaterials: sourcePaths.length > 0,
        generateAudio: allowAutoFill && autoGenerateAudio,
        generateImages: allowAutoFill && autoGenerateImages,
        generateVideos: false,
        overwriteExisting: false,
      });
      setResult(response);
      setPrepareReport(response?.prepare_report || null);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setPreparingAssets(false);
    }
  }

  return (
    <section className="jianying-workflow-shell">
      <form className="panel jianying-natural-form" onSubmit={handleSubmit}>
        <div className="panel-header">
          <div>
            <h2>AI 出剧本，补齐素材后直接生成草稿</h2>
            <p>AI 先生成一份能进入下一步的内部结构规范，不要求你在这里逐镜头编辑。</p>
          </div>
          <Badge status="ready">Workflow</Badge>
        </div>
        <div className="workflow-intro-strip">
          <span>1. AI 生成内部结构规范</span>
          <span>2. 贴入第三方素材路径</span>
          <span>3. 自动补齐并生成剪映草稿</span>
        </div>
        <label className="textarea-label">
          剧本需求
          <textarea value={input} onChange={(event) => setInput(event.target.value)} rows={7} required />
        </label>
        <div className="script-chassis-grid">
          <label>标题<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="留空则自动推断" /></label>
          <label>
            类型预设
            <select value={creativePreset} onChange={(event) => setCreativePreset(event.target.value)}>
              <option value="">自动识别</option>
              <option value="default">通用短剧模板</option>
              <option value="mysticism_lead">玄学引流模板</option>
              <option value="ancient爽文">古风爽文漫剧</option>
              <option value="ai_pet">AI 小动物剧情</option>
            </select>
          </label>
          <label>总时长<input type="number" min="5" max="600" value={durationSeconds} onChange={(event) => setDurationSeconds(event.target.value)} placeholder="自动" /></label>
          <label>结构段数<input type="number" min="1" max="30" value={sceneCount} onChange={(event) => setSceneCount(event.target.value)} placeholder="自动" /></label>
          <label>
            画幅
            <select value={resolution} onChange={(event) => setResolution(event.target.value)}>
              <option value="">自动，默认 9:16</option>
              <option value="9:16">9:16</option>
              <option value="16:9">16:9</option>
              <option value="1:1">1:1</option>
            </select>
          </label>
        </div>
        <details className="workflow-advanced">
          <summary>高级生成设置</summary>
          <div className="workflow-advanced-grid">
            <label>
              AI Provider
              <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                <option value="">使用当前全局 AI</option>
                <option value="mock">mock 调试</option>
              </select>
            </label>
            <label>
              生成方式
              <select value={generationMode} onChange={(event) => setGenerationMode(event.target.value)}>
                <option value="local">本地结构化生成</option>
                <option value="skill_contract">Skill 规则生成</option>
              </select>
            </label>
          </div>
        </details>
        <button className="primary-button" type="submit" disabled={submitting || !input.trim()}>
          {submitting ? "提交中" : "先生成剧本"}
        </button>
        {task && (
          <div className="running-note">
            {task.message || "任务已创建"}{task.progress !== undefined ? ` · ${task.progress}%` : ""}
          </div>
        )}
        {error && <div className="error-box">{error}</div>}
      </form>

      <section className="panel workflow-stage-panel">
        <div className="panel-header">
          <div>
            <h2>素材路径与补齐策略</h2>
            <p>{parsed ? `已识别为 ${parsed.intent}，下面只保留进入下一步真正需要的结构信息。` : "先生成结构规范，再输入素材路径和补齐策略。"}</p>
          </div>
          <Badge status={readySceneCount === totalSceneCount && totalSceneCount > 0 ? "ready" : "draft"}>
            {readySceneCount}/{totalSceneCount} 段已补齐
          </Badge>
        </div>
        {script ? (
          <>
            <section className="workflow-summary-grid compact">
              <article className="workflow-summary-card hero">
                <strong>{script?.config?.title || "未命名结构规范"}</strong>
                <p>{generationModeLabel(currentMode)} · {structureCountLabel} 段 · {script?.config?.total_duration_seconds || durationSeconds || "自动"} 秒 · {script?.config?.resolution || "9:16"}</p>
              </article>
              <article className="workflow-summary-card">
                <strong>素材策略</strong>
                <p>{hasExternalMaterials ? "已输入第三方素材路径" : "可以直接粘贴素材路径，也可以完全交给 AI 补齐"}</p>
              </article>
              <article className="workflow-summary-card">
                <strong>可选能力</strong>
                <p>{[
                  subtitleFromNarration ? "字幕开启" : "字幕关闭",
                  enableBgm ? "BGM 可选" : "不写入 BGM",
                  aiAutoFillEnabled ? "AI 补齐开启" : "仅用现有素材",
                ].join(" · ")}</p>
              </article>
            </section>
            {parsed && (
              <div className="workflow-brief-card">
                <strong>内部规范已生成</strong>
                <p>AI 已把你的需求整理成可继续补素材、补配音并生成 `JyProject` 草稿的内部结构。这里不再要求你逐段编辑。</p>
              </div>
            )}
            <section className="workflow-timeline-panel">
              <div className="workflow-timeline-head">
                <div>
                  <h3>结构时间线预览</h3>
                  <p>这里只确认结构段和节奏，不做分镜级编辑。后续素材可以手动指定，也可以交给 AI 自动补齐。</p>
                </div>
                <Badge>{timelineItems.length} 段</Badge>
              </div>
              <div className="workflow-chip-row">
                {(structureHints.length ? structureHints : ["已生成可继续执行的最小结构规范"]).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
              <div className="workflow-timeline-list">
                {timelineItems.map((item) => (
                  <article className="workflow-timeline-item" key={item.id}>
                    <div className="workflow-timeline-mark">
                      <strong>{formatTimelineMark(item.start)} - {formatTimelineMark(item.end)}</strong>
                      <span>{item.duration}s</span>
                    </div>
                    <div className="workflow-timeline-content">
                      <div className="workflow-timeline-title">
                        <strong>{item.title}</strong>
                        <Badge status={item.status === "ready" || item.status === "partial_ready" ? item.status : "draft"}>
                          {statusText[item.status] || "草稿"}
                        </Badge>
                      </div>
                      <p>{item.summary}</p>
                    </div>
                  </article>
                ))}
              </div>
            </section>
            <section className="workflow-main-stage">
              <div className="workflow-main-head">
                <div>
                  <h3>生成草稿前最后一步</h3>
                  <p>输入第三方素材路径；如果你不想手动准备全部素材，也可以打开 AI 自动补齐，让系统补画面、补配音后直接生成草稿。</p>
                </div>
                <Badge status={prepareReport ? "ready" : "draft"}>{prepareReport ? "已运行自动补齐" : "等待补齐"}</Badge>
              </div>
              <div className="workflow-inline-extra">
                <label>
                  草稿名称
                  <input value={draftName} onChange={(event) => setDraftName(event.target.value)} placeholder="例如：2026年5月9日16时22分" />
                </label>
                <label>
                  第三方素材路径
                  <textarea value={externalMaterials} onChange={(event) => setExternalMaterials(event.target.value)} rows={4} placeholder="可粘贴视频、图片、音频路径，支持换行或逗号分隔" />
                </label>
                <label>
                  BGM 检索词
                  <input value={customBgmKeywords} onChange={(event) => setCustomBgmKeywords(event.target.value)} placeholder="留空则沿用 AI 生成的设定集" disabled={!enableBgm} />
                </label>
              </div>
              <div className="workflow-switch-row">
                <label className="jianying-check">
                  <input type="checkbox" checked={enableBgm} onChange={(event) => setEnableBgm(event.target.checked)} />
                  <span>BGM 可选</span>
                </label>
                <label className="jianying-check">
                  <input type="checkbox" checked={subtitleFromNarration} onChange={(event) => setSubtitleFromNarration(event.target.checked)} />
                  <span>字幕可选</span>
                </label>
                <label className="jianying-check">
                  <input type="checkbox" checked={allowAutoFill} onChange={(event) => setAllowAutoFill(event.target.checked)} />
                  <span>缺失素材允许 AI 自动补齐</span>
                </label>
              </div>
              <div className="workflow-switch-row">
                <label className="jianying-check">
                  <input type="checkbox" checked={autoGenerateImages} onChange={(event) => setAutoGenerateImages(event.target.checked)} disabled={!allowAutoFill} />
                  <span>自动补画面</span>
                </label>
                <label className="jianying-check">
                  <input type="checkbox" checked={autoGenerateAudio} onChange={(event) => setAutoGenerateAudio(event.target.checked)} disabled={!allowAutoFill} />
                  <span>自动补配音</span>
                </label>
              </div>
              <div className="script-action-strip">
                <button className="secondary-action-button" type="button" onClick={handleSaveCurrentScript} disabled={savingScript}>
                  {savingScript ? "保存中" : "保存内部规范"}
                </button>
                <button className="secondary-action-button" type="button" onClick={handlePrepareAssets} disabled={savingScript || preparingAssets}>
                  {preparingAssets ? "补齐中" : "自动补齐素材"}
                </button>
                <button className="primary-button" type="button" onClick={handleBuildSdkDraftFromCurrentScript} disabled={savingScript || buildingSdkDraft}>
                  {buildingSdkDraft ? "生成中" : "补齐素材并生成草稿"}
                </button>
              </div>
              <div className="workflow-note-strip">
                <span>外部素材</span>
                <strong>{hasExternalMaterials ? "已提供路径" : "未提供"}</strong>
                <span>AI 补齐</span>
                <strong>{aiAutoFillEnabled ? "开启" : "关闭"}</strong>
                <span>现有素材</span>
                <strong>{hasExistingAssets ? "已有绑定" : "尚未绑定"}</strong>
              </div>
              {prepareReport && (
                <div className="running-note">
                  已准备 {prepareReport.ready_scene_count || 0}/{prepareReport.scene_count || 0} 个结构段
                  {prepareReport.generated_assets_dir ? ` · 输出目录：${prepareReport.generated_assets_dir}` : ""}
                </div>
              )}
              {draftBuildResult && (
                <div className="running-note">
                  草稿已生成：{draftBuildResult.draft_path || "-"}
                </div>
              )}
              {draftBuildResult?.applied_edits?.length > 0 && (
                <details className="raw-json">
                  <summary>查看已应用的 edit 映射</summary>
                  <pre className="result-box">{JSON.stringify(draftBuildResult.applied_edits, null, 2)}</pre>
                </details>
              )}
              {draftBuildResult?.failed_edits?.length > 0 && (
                <details className="raw-json" open>
                  <summary>查看未应用的 edit 映射</summary>
                  <pre className="result-box">{JSON.stringify(draftBuildResult.failed_edits, null, 2)}</pre>
                </details>
              )}
              {prepareReport?.scenes?.length > 0 && (
                <details className="raw-json">
                  <summary>查看素材准备报告</summary>
                  <pre className="result-box">{JSON.stringify(prepareReport, null, 2)}</pre>
                </details>
              )}
            </section>
          </>
        ) : (
          <div className="empty-result">等待生成内部结构规范。</div>
        )}
      </section>

      <section className="panel jianying-script-history-panel">
        <div className="panel-header">
          <div>
            <h2>已生成剧本</h2>
            <p>这里只保留历史结构规范，方便重新打开继续补素材或直接生成草稿。</p>
          </div>
          <button className="text-button" type="button" onClick={() => loadScriptProjects().catch((err) => setError(err.message || String(err)))}>
            刷新
          </button>
        </div>
        <div className="draft-project-list">
          {scriptProjects.length ? scriptProjects.map((project) => (
            <article className="draft-project-row" key={project.project_id}>
              <div>
                <strong>{project.title || project.project_id}</strong>
                <p>{project.script_path}</p>
              </div>
              <div className="draft-project-meta">
                <Badge status={project.status === "script_ready" ? "ready" : "draft"}>{project.scene_count || 0} 段</Badge>
                <Badge>{generationModeLabel(project.generation_mode)}</Badge>
                <span>{project.genre || "未分类"}</span>
                <span>{formatTimestamp(project.updated_at)}</span>
                <button className="text-button" type="button" onClick={() => handleOpenScript(project.project_id)}>
                  点击查看
                </button>
                <button className="text-button danger-text-button" type="button" onClick={() => handleDeleteScript(project.project_id)}>
                  删除
                </button>
              </div>
            </article>
          )) : <div className="empty-result">还没有生成结构化剧本。</div>}
        </div>
      </section>
    </section>
  );
}

function DraftInspectorPanel() {
  const [draftRoot, setDraftRoot] = useState("D:\\jianying\\JianyingPro Drafts");
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [projectDetail, setProjectDetail] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    handleLoadProjects().catch(() => {});
  }, []);

  async function handleLoadProjects() {
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const data = await listJianyingDraftProjects(draftRoot);
      setProjects(data.projects || []);
      setSelectedProject(null);
      setProjectDetail(null);
      setMessage(`已加载 ${data.projects?.length || 0} 个剪映项目`);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectProject(project) {
    setSelectedProject(project);
    setProjectDetail(null);
    setDetailOpen(true);
    setDetailLoading(true);
    setMessage("");
    setError("");
    try {
      const data = await inspectJianyingDraft(project.draft_path);
      setProjectDetail(data);
    } catch (err) {
      setProjectDetail({
        draft_path: project.draft_path,
        summary: {},
        details: {},
        draft_content: {},
        needs_decrypt: true,
        error: err.message || String(err),
      });
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleOpenDraftPath(path) {
    try {
      await openJianyingDraftPath(path);
    } catch (err) {
      setError(err.message || String(err));
    }
  }

  async function handleCopyPath(path) {
    try {
      await navigator.clipboard.writeText(path);
      setMessage("草稿路径已复制");
    } catch (err) {
      setError(err.message || String(err));
    }
  }

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>查看草稿</h2>
          <p>按项目查看剪映草稿，点击项目后读取 draft_content.json。</p>
        </div>
        <Badge status="ready">Inspect</Badge>
      </div>

      <section className="collector-card">
        <h3>剪映草稿根目录</h3>
        <div className="collector-fields">
          <label>
            Draft Root
            <input value={draftRoot} onChange={(event) => setDraftRoot(event.target.value)} placeholder="输入 JianyingPro Drafts 目录绝对路径" />
          </label>
        </div>
        <div className="script-action-strip">
          <button className="primary-button" type="button" onClick={handleLoadProjects} disabled={loading || !draftRoot.trim()}>
            {loading ? "扫描中" : "扫描项目"}
          </button>
          <button className="text-button" type="button" onClick={() => handleOpenDraftPath(draftRoot)} disabled={!draftRoot.trim()}>
            打开目录
          </button>
          <button className="text-button" type="button" onClick={() => handleCopyPath(draftRoot)} disabled={!draftRoot.trim()}>
            复制路径
          </button>
        </div>
      </section>

      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}

      <section className="collector-card">
        <div className="section-title-row">
          <h3>剪映项目</h3>
          <Badge>{projects.length}</Badge>
        </div>
        <div className="draft-project-list">
          {projects.length ? projects.map((project) => (
            <article
              className={`draft-project-row ${selectedProject?.draft_path === project.draft_path ? "active" : ""} ${project.needs_decrypt ? "needs-decrypt" : ""}`}
              key={project.draft_path}
            >
              <div>
                <strong>{project.name}</strong>
                <p>{project.draft_path}</p>
              </div>
              <div className="draft-project-meta">
                <Badge status={project.needs_decrypt ? "error" : "ready"}>
                  {project.needs_decrypt ? "待解密" : "可查看"}
                </Badge>
                <span>{formatTimestamp(project.last_modified)}</span>
                <button className="text-button" type="button" onClick={() => handleSelectProject(project)}>
                  点击查看
                </button>
              </div>
            </article>
          )) : <div className="empty-result">还没有扫描到剪映项目。</div>}
        </div>
      </section>

      {detailOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setDetailOpen(false)}>
          <section className="draft-detail-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <header className="draft-detail-modal-head">
              <div>
                <h3>{selectedProject?.name || "草稿详情"}</h3>
                <p>{selectedProject?.draft_path || ""}</p>
              </div>
              <div className="draft-detail-actions">
                {detailLoading ? <Badge status="running">读取中</Badge> : projectDetail?.needs_decrypt ? <Badge status="error">待解密</Badge> : <Badge status="ready">draft_content.json</Badge>}
                <button className="text-button" type="button" onClick={() => setDetailOpen(false)}>关闭</button>
              </div>
            </header>
          {detailLoading ? (
            <div className="running-note">正在读取 draft_content.json...</div>
          ) : projectDetail?.needs_decrypt ? (
            <div className="error-box">{projectDetail.error || "draft_content.json 不是标准格式，可能需要先解密。"}</div>
          ) : projectDetail ? (
            <DraftDetailContent projectDetail={projectDetail} />
          ) : null}
          </section>
        </div>
      )}
    </section>
  );
}

function DraftDetailContent({ projectDetail }) {
  const content = projectDetail.draft_content || {};
  const materialIndex = buildMaterialIndex(content.materials);
  const segments = flattenDraftSegments(content.tracks, materialIndex);
  const readable = projectDetail.readable || {};
  const identity = readable.identity || {};
  const canvas = readable.canvas || {};
  const timeline = readable.timeline || {};
  const materials = readable.materials || {};
  const texts = readable.texts || {};
  const effects = readable.effects || {};
  const projectFiles = readable.project_files || [];

  return (
    <div className="draft-detail-body">
      <section className="draft-detail-section">
        <h4>草稿概览</h4>
        <div className="workflow-summary-grid compact">
          <article className="workflow-summary-card hero">
            <strong>{identity.name || projectDetail.summary?.draft_name || "未命名草稿"}</strong>
            <p>{readable.overview || "这里会总结这个草稿的时长、轨道和主要素材结构。"}</p>
          </article>
          <article className="workflow-summary-card">
            <strong>创建时间</strong>
            <p>{identity.created_at || "未记录"}</p>
          </article>
          <article className="workflow-summary-card">
            <strong>最后修改</strong>
            <p>{identity.modified_at || projectDetail.summary?.modified_at || "未记录"}</p>
          </article>
        </div>
      </section>

      <div className="draft-canvas-detail">
        <div><strong>画布比例</strong><p>{projectDetail.summary?.canvas?.ratio || "-"}</p></div>
        <div><strong>画布尺寸</strong><p>{canvas.size || formatCanvasSize(projectDetail.summary?.canvas)}</p></div>
        <div><strong>草稿时长</strong><p>{formatDuration(projectDetail.summary?.duration_seconds)}</p></div>
        <div><strong>轨道数量</strong><p>{projectDetail.summary?.track_count ?? "-"}</p></div>
        <div><strong>轨道类型</strong><p>{Array.isArray(projectDetail.summary?.track_types) ? projectDetail.summary.track_types.join(", ") : "-"}</p></div>
        <div><strong>素材组数</strong><p>{projectDetail.summary?.material_groups ?? "-"}</p></div>
        <div><strong>Draft ID</strong><p>{projectDetail.summary?.draft_id || projectDetail.details?.id || "-"}</p></div>
        <div><strong>版本</strong><p>{projectDetail.details?.new_version || projectDetail.details?.version || "-"}</p></div>
      </div>

      <section className="draft-detail-section">
        <h4>时间线说明</h4>
        <div className="workflow-summary-grid compact">
          <article className="workflow-summary-card">
            <strong>轨道结构</strong>
            <p>{timeline.track_headline || "暂无轨道摘要"}</p>
          </article>
          <article className="workflow-summary-card">
            <strong>可读文字</strong>
            <p>{texts.headline || "暂无文字摘要"}</p>
          </article>
          <article className="workflow-summary-card">
            <strong>素材来源</strong>
            <p>{materials.headline || "暂无素材摘要"}</p>
          </article>
        </div>
      </section>

      <section className="draft-detail-section">
        <h4>轨道</h4>
        <div className="draft-track-list">
          {timeline.track_explanations?.length ? timeline.track_explanations.map((track) => (
            <article className="draft-track-row" key={track.id || `${track.type}-${track.segments}`}>
              <strong>{track.title}</strong>
              <span>{track.segments} 段</span>
              <p>{track.explanation}</p>
            </article>
          )) : <div className="empty-result">没有轨道数据。</div>}
        </div>
      </section>

      {texts.items?.length > 0 && (
        <section className="draft-detail-section">
          <h4>文字内容</h4>
          <div className="draft-material-items">
            {texts.items.map((item, index) => (
              <article className="draft-material-row" key={`${item.title}-${index}`}>
                <strong>{item.title}</strong>
                <p>{item.content}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      {materials.sources?.length > 0 && (
        <section className="draft-detail-section">
          <h4>素材来源</h4>
          <div className="draft-material-items">
            {materials.sources.map((item, index) => (
              <article className="draft-material-row" key={`${item.group}-${item.path}-${index}`}>
                <strong>{item.title}</strong>
                <p>{item.path}</p>
                <code>{item.group}</code>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="draft-detail-section">
        <h4>时间线片段</h4>
        <div className="draft-segment-table">
          <div className="draft-segment-head">
            <span>轨道</span><span>开始</span><span>时长</span><span>素材</span><span>文本/路径</span>
          </div>
          {segments.length ? segments.map((segment) => (
            <div className="draft-segment-row" key={segment.id}>
              <span>{segment.trackType}</span>
              <span>{formatMicroseconds(segment.start)}</span>
              <span>{formatMicroseconds(segment.duration)}</span>
              <span>{segment.materialType || segment.materialId || "-"}</span>
              <p>{segment.preview || "-"}</p>
            </div>
          )) : <div className="empty-result">没有片段数据。</div>}
        </div>
      </section>

      <section className="draft-detail-section">
        <h4>素材明细</h4>
        <div className="draft-material-list">
          {objectEntries(content.materials).length ? objectEntries(content.materials).map(([group, items]) => (
            <details className="draft-material-group" key={group}>
              <summary>{group} <Badge>{Array.isArray(items) ? items.length : 0}</Badge></summary>
              <div className="draft-material-items">
                {Array.isArray(items) && items.length ? items.map((item, index) => (
                  <article className="draft-material-row" key={item.id || `${group}-${index}`}>
                    <strong>{materialTitle(item, index)}</strong>
                    <p>{materialSubtitle(item)}</p>
                    <code>{item.id || "-"}</code>
                  </article>
                )) : <div className="empty-result">没有素材条目。</div>}
              </div>
            </details>
          )) : <div className="empty-result">没有素材数据。</div>}
        </div>
      </section>

      <section className="draft-detail-section">
        <h4>特效 / 配置</h4>
        <div className="workflow-summary-card">
          <strong>解释</strong>
          <p>{effects.headline || "无明显特效或配置项。"}</p>
          <div className="draft-chip-grid">
            {objectEntries(projectDetail.details?.keyframe_counts).map(([key, value]) => <span key={key}>{key}: {value}</span>)}
            {(projectDetail.details?.config_keys || []).map((key) => <span key={key}>config: {key}</span>)}
            {!objectEntries(projectDetail.details?.keyframe_counts).length && !(projectDetail.details?.config_keys || []).length && <span>无关键帧配置</span>}
          </div>
        </div>
      </section>

      <section className="draft-detail-section">
        <h4>项目文件</h4>
        <div className="draft-material-items">
          {projectFiles.length ? projectFiles.map((item) => (
            <article className="draft-material-row" key={item.relative_path || item.name}>
              <strong>{item.name}</strong>
              <p>{item.relative_path}</p>
              <code>{item.status}{item.needs_decrypt ? " · 可能需解密" : ""}</code>
            </article>
          )) : <div className="empty-result">没有列出项目文件。</div>}
        </div>
      </section>

      <section className="draft-detail-section">
        <h4>草稿结构字段</h4>
        <div className="draft-chip-grid">
          {Object.keys(content).map((key) => <span key={key}>{key}</span>)}
        </div>
      </section>

      <details className="draft-json-panel">
        <summary>查看完整 draft_content.json</summary>
        <pre className="result-box">{JSON.stringify(content, null, 2)}</pre>
      </details>
    </div>
  );
}

function objectEntries(value) {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value);
}

function buildMaterialIndex(materials) {
  const index = {};
  for (const [group, items] of objectEntries(materials)) {
    if (!Array.isArray(items)) continue;
    for (const item of items) {
      if (item?.id) index[item.id] = { ...item, group };
    }
  }
  return index;
}

function flattenDraftSegments(tracks, materialIndex) {
  if (!Array.isArray(tracks)) return [];
  return tracks.flatMap((track) => (track.segments || []).map((segment, index) => {
    const material = materialIndex[segment.material_id] || {};
    return {
      id: segment.id || `${track.id}-${index}`,
      trackType: track.type || "-",
      start: segment.target_timerange?.start || 0,
      duration: segment.target_timerange?.duration || segment.source_timerange?.duration || 0,
      materialId: segment.material_id || "",
      materialType: material.group || material.type || "",
      preview: materialPreview(material),
    };
  }));
}

function materialTitle(item, index) {
  return item.name || item.material_name || item.type || `素材 ${index + 1}`;
}

function materialSubtitle(item) {
  return materialPreview(item) || item.path || item.resource_id || item.type || "-";
}

function materialPreview(item) {
  if (!item || typeof item !== "object") return "";
  const text = extractTextMaterial(item);
  if (text) return text;
  return item.path || item.name || item.material_name || item.resource_id || item.effect_id || "";
}

function extractTextMaterial(item) {
  if (typeof item.content !== "string") return "";
  try {
    const parsed = JSON.parse(item.content);
    return parsed.text || "";
  } catch {
    return item.content.slice(0, 120);
  }
}

function formatMicroseconds(value) {
  const microseconds = Number(value || 0);
  if (!Number.isFinite(microseconds) || microseconds <= 0) return "0s";
  return `${(microseconds / 1_000_000).toFixed(2)}s`;
}

function formatCanvasSize(canvas) {
  if (!canvas || typeof canvas !== "object") return "-";
  const width = canvas.width || canvas.canvas_width;
  const height = canvas.height || canvas.canvas_height;
  return width && height ? `${width} x ${height}` : "-";
}

function formatDuration(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return "-";
  return `${seconds}s`;
}

function formatTimestamp(value) {
  const timestamp = Number(value);
  if (!Number.isFinite(timestamp)) return "-";
  return new Date(timestamp * 1000).toLocaleString();
}

function videoTitle(video) {
  return video?.desc || video?.title || video?.aweme_id || video?.id || "未命名视频";
}

function parseJsonString(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

function firstText(source, keys) {
  if (!source || typeof source !== "object") return "";
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string") return value.trim();
    if (Array.isArray(value)) return value.map((item) => (typeof item === "string" ? item : JSON.stringify(item))).join("\n");
    if (value != null && typeof value !== "object") return String(value);
  }
  return "";
}

function firstObject(source, keys) {
  if (!source || typeof source !== "object") return {};
  for (const key of keys) {
    const value = source[key];
    if (value && typeof value === "object" && !Array.isArray(value)) return value;
  }
  return {};
}

function firstNumber(source, keys) {
  if (!source || typeof source !== "object") return 0;
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "number") return Math.max(0, Math.min(100, Math.round(value)));
    if (typeof value === "string") {
      const match = value.match(/\d+/);
      if (match) return Math.max(0, Math.min(100, Number(match[0])));
    }
  }
  return 0;
}

function normalizeCommercialAnalysisResult(source) {
  const nested = source?.result && typeof source.result === "object" ? source.result : source;
  const summaryJson = parseJsonString(nested?.summary);
  const raw = summaryJson && typeof summaryJson === "object" ? summaryJson : nested || {};
  const contentIdentity = firstObject(raw, ["content_identity", "内容定位", "赛道判断"]);
  const coreHook = firstObject(raw, ["core_hook", "核心钩子", "核心勾子"]);
  const needContext = firstObject(raw, ["need_context", "需求与场景", "需求场景"]);
  const productPower = firstObject(raw, ["product_power", "产品表现", "产品力", "产品价值"]);
  const visualStructure = firstObject(raw, ["visual_structure", "视觉与结构", "视觉结构"]);
  const copywritingFormula = firstObject(raw, ["copywriting_formula", "文案公式", "脚本公式"]);
  const marketPositioning = firstObject(raw, ["market_positioning", "商业定位", "市场定位"]);
  const replicationPlan = firstObject(raw, ["replication_plan", "复刻计划", "模仿计划"]);
  const riskControl = firstObject(raw, ["risk_control", "风险控制", "合规风险"]);
  const viralScores = firstObject(raw, ["viral_scores", "爆款评分", "评分"]);

  return {
    summary: firstText(raw, ["summary", "摘要", "视频摘要", "一句话摘要"]),
    content_identity: {
      track: firstText(contentIdentity, ["track", "内容赛道", "赛道"]),
      niche_fit: firstText(contentIdentity, ["niche_fit", "赛道适配", "适配方向"]),
      account_persona: firstText(contentIdentity, ["account_persona", "账号人设", "人设"]),
    },
    core_hook: {
      opening_3s: firstText(coreHook, ["opening_3s", "开头3秒钩子", "开头3秒勾子", "开头3秒狗子"]),
      curiosity_gap: firstText(coreHook, ["curiosity_gap", "信息差", "悬念"]),
      emotional_trigger: firstText(coreHook, ["emotional_trigger", "情绪触发", "情绪"]),
      comment_bait: firstText(coreHook, ["comment_bait", "评论诱因", "评论钩子"]),
    },
    need_context: {
      pain_point: firstText(needContext, ["pain_point", "痛点定位", "痛点"]),
      application_scene: firstText(needContext, ["application_scene", "应用场景", "场景"]),
      hidden_desire: firstText(needContext, ["hidden_desire", "隐性欲望", "深层欲望"]),
    },
    product_power: {
      core_benefit: firstText(productPower, ["core_benefit", "功效提炼", "核心功效", "核心利益点"]),
      trigger_moment: firstText(productPower, ["trigger_moment", "激励点", "触发点", "转化瞬间"]),
      trust_builder: firstText(productPower, ["trust_builder", "信任来源", "信任背书"]),
      product_role: firstText(productPower, ["product_role", "产品角色", "产品定位"]),
    },
    visual_structure: {
      shot_structure: firstText(visualStructure, ["shot_structure", "镜头结构", "结构"]),
      reusable_elements: firstText(visualStructure, ["reusable_elements", "可复用元素", "可服用元素"]),
      timeline_beats: firstText(visualStructure, ["timeline_beats", "时间线", "节奏点"]),
      audio_rhythm: firstText(visualStructure, ["audio_rhythm", "声音节奏", "音频节奏"]),
    },
    copywriting_formula: {
      title_formula: firstText(copywritingFormula, ["title_formula", "标题公式"]),
      script_formula: firstText(copywritingFormula, ["script_formula", "脚本公式"]),
      golden_lines: firstText(copywritingFormula, ["golden_lines", "金句", "可复用句式"]),
      cta: firstText(copywritingFormula, ["cta", "行动号召", "转化口令"]),
    },
    market_positioning: {
      suitable_products: firstText(marketPositioning, ["suitable_products", "适合产品", "适配产品"]),
      target_audience: firstText(marketPositioning, ["target_audience", "目标人群", "目标用户"]),
      creative_direction: firstText(marketPositioning, ["creative_direction", "创作方向", "后续方向"]),
    },
    replication_plan: {
      pattern_name: firstText(replicationPlan, ["pattern_name", "公式名", "模式名"]),
      reusable_formula: firstText(replicationPlan, ["reusable_formula", "可复刻公式", "复用公式"]),
      mysticism_variant: firstText(replicationPlan, ["mysticism_variant", "玄学方向", "玄学改编"]),
      ai_pet_variant: firstText(replicationPlan, ["ai_pet_variant", "AI小动物方向", "小动物改编"]),
      ai_commerce_variant: firstText(replicationPlan, ["ai_commerce_variant", "AI带货方向", "带货改编"]),
      difficulty: firstText(replicationPlan, ["difficulty", "制作难度", "难度"]),
      priority: firstText(replicationPlan, ["priority", "优先级", "模仿优先级"]),
    },
    risk_control: {
      risk_level: firstText(riskControl, ["risk_level", "风险等级"]),
      platform_risks: firstText(riskControl, ["platform_risks", "平台风险", "风险点"]),
      safe_rewrite: firstText(riskControl, ["safe_rewrite", "安全改写", "合规表达"]),
    },
    viral_scores: {
      viral_potential: firstNumber(viralScores, ["viral_potential", "爆款潜力"]),
      imitation_value: firstNumber(viralScores, ["imitation_value", "模仿价值"]),
      commerce_value: firstNumber(viralScores, ["commerce_value", "商业价值"]),
      comment_potential: firstNumber(viralScores, ["comment_potential", "评论潜力"]),
      overall: firstNumber(viralScores, ["overall", "综合评分"]),
    },
    raw_model_json: raw?.raw_model_json || raw,
  };
}

function normalizeAnalysisTask(task, normalizeResult = normalizeCommercialAnalysisResult) {
  const updated = task.updated_at ? new Date(task.updated_at * 1000) : new Date();
  const result = normalizeResult(task.result?.result || task.result || {});
  const events = Array.isArray(task.events)
    ? task.events.map((event) => ({
        ...event,
        time: event.created_at
          ? new Date(event.created_at * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
          : "",
        status: event.status === "failed" ? "error" : event.status,
      }))
    : [];
  return {
    ...task,
    id: task.id,
    title: task.title || videoTitle(task.payload?.video || {}),
    status: task.status === "failed" ? "error" : task.status,
    progress: task.progress || 0,
    updated: updated.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }),
    video: task.payload?.video,
    result,
    error: task.error,
    events,
  };
}

function normalizePromptReverseTask(task) {
  return normalizeAnalysisTask(task, (result) => result || {});
}

function archiveIdSet(archives) {
  return new Set(archives.map((item) => item.task_id || item.id).filter(Boolean));
}

function AnalysisTaskPanel({
  tasks,
  onOpenResult,
  onDeleteTask,
  onArchiveTask,
  archivedIds,
  compact = false,
  title = "AI 视频拆解任务",
  emptyText = "点击视频卡片里的 AI 视频拆解后，任务会显示在这里。",
}) {
  const visibleTasks = compact ? tasks.slice(0, 3) : tasks;

  return (
    <section className={`panel analysis-task-panel ${compact ? "compact-analysis-panel" : ""}`}>
      <div className="panel-header">
        <h2>{title}</h2>
        <Badge status={tasks.length ? "running" : "draft"}>{tasks.length ? `${tasks.length} 个任务` : "暂无任务"}</Badge>
      </div>
      {visibleTasks.length ? (
        <div className="analysis-task-list">
          {visibleTasks.map((task) => (
            <article className="analysis-task-card" key={task.id}>
              <div className="analysis-task-head">
                <strong>{task.title}</strong>
                <Badge status={task.status}>{task.status === "done" ? "已完成" : task.status === "error" ? "失败" : "运行中"}</Badge>
              </div>
              <div className="progress">
                <span style={{ width: `${task.progress}%` }} />
              </div>
              {!["done", "error"].includes(task.status) && (
                <div className="task-current-stage">
                  <Clock3 size={15} />
                  <span>当前阶段：{task.message || "等待后端更新"} · {task.progress}%</span>
                </div>
              )}
              <div className="analysis-task-foot">
                <span>{task.message || "AI 视频拆解"} · {task.updated}</span>
              </div>
              <div className="task-action-row">
                {task.status === "done" && (
                  <button className="text-button" type="button" onClick={() => onOpenResult(task)}>
                    查看结果
                  </button>
                )}
                {task.status === "done" && onArchiveTask && (
                  <button
                    className="text-button"
                    type="button"
                    disabled={archivedIds?.has(task.id)}
                    onClick={() => onArchiveTask(task)}
                  >
                    <Archive size={15} />
                    {archivedIds?.has(task.id) ? "已归档" : "归档"}
                  </button>
                )}
                {onDeleteTask && (
                  <button className="text-button danger-text-button" type="button" onClick={() => onDeleteTask(task)}>
                    删除
                  </button>
                )}
              </div>
              {task.status === "error" && <p className="task-error-text">{task.error}</p>}
              {task.events?.length > 0 && (
                <div className="task-event-timeline">
                  <div className="task-event-summary">
                    <span>进度日志</span>
                    <span>{task.events.length} 条</span>
                  </div>
                  {task.events.slice(-100).map((event) => (
                    <div className="task-event-row" key={event.id || `${event.created_at}-${event.message}`}>
                      <span className="task-event-dot" />
                      <span className="task-event-time">{event.time}</span>
                      <span className="task-event-progress">{event.progress}%</span>
                      <span className="task-event-message">{event.message || event.status || "更新任务状态"}</span>
                    </div>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-result">{emptyText}</div>
      )}
    </section>
  );
}

function TaskToolGroup({ title, desc, children }) {
  return (
    <section className="task-tool-section">
      <div className="task-tool-heading">
        <div>
          <span>工具任务</span>
          <h2>{title}</h2>
        </div>
        <p>{desc}</p>
      </div>
      <div className="task-status-grid">{children}</div>
    </section>
  );
}

function archivePresentation(item) {
  if (item.archiveType === "analysis") {
    const result = normalizeCommercialAnalysisResult(item.result || {});
    return {
      toolLabel: "AI 视频拆解",
      toolDetail: "商业拆解归档",
      headline: item.title || "未命名视频",
      summary: result.summary || "暂无摘要",
      highlights: [
        ["核心钩子", result.core_hook?.opening_3s],
        ["目标人群", result.market_positioning?.target_audience],
        ["创作方向", result.market_positioning?.creative_direction],
      ].filter(([, value]) => value),
      tags: [item.provider, "商业拆解"].filter(Boolean),
    };
  }
  if (item.archiveType === "prompt") {
    const result = item.result || {};
    return {
      toolLabel: "AI 提示词反推",
      toolDetail: "生成提示词归档",
      headline: item.title || "未命名视频",
      summary: result.summary || result.master_prompt || "暂无摘要",
      highlights: [
        ["主提示词", result.master_prompt],
        ["分镜数量", Array.isArray(result.shot_prompts) && result.shot_prompts.length ? `${result.shot_prompts.length} 个镜头` : ""],
        ["适用建议", Array.isArray(result.usage_notes) ? result.usage_notes[0] : ""],
      ].filter(([, value]) => value),
      tags: [item.provider, "提示词反推"].filter(Boolean),
    };
  }
  return {
    toolLabel: item.type || "素材",
    toolDetail: "示例素材",
    headline: item.title,
    summary: item.desc,
    highlights: [],
    tags: item.tags || [],
  };
}

function LibraryArchiveGroup({ title, desc, items, children }) {
  if (!items.length) return null;
  return (
    <section className="library-tool-section">
      <div className="library-tool-heading">
        <div>
          <span>归档结果</span>
          <h2>{title}</h2>
        </div>
        <p>{desc}</p>
      </div>
      <div className="library-card-grid">{children}</div>
    </section>
  );
}

function LibraryItemModal({ item, onClose }) {
  if (!item) return null;
  const presentation = item.presentation || archivePresentation(item);
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-panel">
        <div className="panel-header">
          <div>
            <h2>{presentation.headline}</h2>
            <p>{presentation.toolDetail}</p>
          </div>
          <button className="text-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="result-grid">
          <article>
            <span>摘要</span>
            <p>{presentation.summary}</p>
          </article>
          {presentation.highlights.map(([label, value]) => (
            <article key={label}>
              <span>{label}</span>
              <p>{value}</p>
            </article>
          ))}
          {presentation.tags.length > 0 && (
            <article>
              <span>标签</span>
              <p>{presentation.tags.join(" / ")}</p>
            </article>
          )}
        </div>
        <pre className="result-box">{JSON.stringify(item.raw || item, null, 2)}</pre>
      </div>
    </div>
  );
}

function AnalysisResultModal({ task, onClose }) {
  if (!task) return null;
  const result = normalizeCommercialAnalysisResult(task.result || {});
  const sections = [
    [
      "内容定位",
      [
        ["内容赛道", result.content_identity?.track],
        ["赛道适配", result.content_identity?.niche_fit],
        ["账号人设", result.content_identity?.account_persona],
      ],
    ],
    [
      "核心钩子",
      [
        ["开头3秒钩子", result.core_hook?.opening_3s],
        ["信息差/悬念", result.core_hook?.curiosity_gap],
        ["情绪触发", result.core_hook?.emotional_trigger],
        ["评论诱因", result.core_hook?.comment_bait],
      ],
    ],
    [
      "需求与场景",
      [
        ["痛点定位", result.need_context?.pain_point],
        ["应用场景", result.need_context?.application_scene],
        ["隐性欲望", result.need_context?.hidden_desire],
      ],
    ],
    [
      "产品表现",
      [
        ["利益点提炼", result.product_power?.core_benefit],
        ["转化瞬间", result.product_power?.trigger_moment],
        ["信任来源", result.product_power?.trust_builder],
        ["产品角色", result.product_power?.product_role],
      ],
    ],
    [
      "视觉与结构",
      [
        ["镜头结构", result.visual_structure?.shot_structure],
        ["可复用元素", result.visual_structure?.reusable_elements],
        ["时间线节奏", result.visual_structure?.timeline_beats],
        ["声音节奏", result.visual_structure?.audio_rhythm],
      ],
    ],
    [
      "文案公式",
      [
        ["标题公式", result.copywriting_formula?.title_formula],
        ["脚本公式", result.copywriting_formula?.script_formula],
        ["可复用金句", result.copywriting_formula?.golden_lines],
        ["行动号召", result.copywriting_formula?.cta],
      ],
    ],
    [
      "商业定位",
      [
        ["适合产品", result.market_positioning?.suitable_products],
        ["目标人群", result.market_positioning?.target_audience],
        ["创作方向", result.market_positioning?.creative_direction],
      ],
    ],
    [
      "复刻计划",
      [
        ["公式名", result.replication_plan?.pattern_name],
        ["可复刻公式", result.replication_plan?.reusable_formula],
        ["玄学改编", result.replication_plan?.mysticism_variant],
        ["AI小动物改编", result.replication_plan?.ai_pet_variant],
        ["AI带货改编", result.replication_plan?.ai_commerce_variant],
        ["制作难度", result.replication_plan?.difficulty],
        ["模仿优先级", result.replication_plan?.priority],
      ],
    ],
    [
      "风险控制",
      [
        ["风险等级", result.risk_control?.risk_level],
        ["平台风险", result.risk_control?.platform_risks],
        ["安全改写", result.risk_control?.safe_rewrite],
      ],
    ],
  ];
  const scoreRows = [
    ["爆款潜力", result.viral_scores?.viral_potential],
    ["模仿价值", result.viral_scores?.imitation_value],
    ["商业价值", result.viral_scores?.commerce_value],
    ["评论潜力", result.viral_scores?.comment_potential],
    ["综合评分", result.viral_scores?.overall],
  ].filter(([, value]) => value);
  const segmentBreakdowns = Array.isArray(result.segment_breakdowns) ? result.segment_breakdowns : [];
  const evidence = result.evidence || {};

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="modal-panel" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <h2>AI 视频拆解结果</h2>
            <p>{task.title}</p>
          </div>
          <button className="text-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="analysis-result-body">
          <p>{result.summary || "暂无摘要"}</p>
          {(result.analysis_mode || evidence.evidence_path) && (
            <div className="analysis-section">
              <strong>证据包</strong>
              <div className="analysis-field">
                <span>分析模式</span>
                <p>{result.analysis_mode || "暂无内容"}</p>
              </div>
              <div className="analysis-field">
                <span>转写信息</span>
                <p>
                  {(evidence.transcript_provider || "未知转写器")} · {evidence.transcript_model || "未知模型"} ·{" "}
                  {evidence.transcript_segments_count || 0} 个转写片段 · {evidence.analysis_segments_count || 0} 个分析片段 ·{" "}
                  {evidence.keyframes_count || 0} 张关键帧
                </p>
              </div>
              {result.pipeline_error && (
                <div className="analysis-field">
                  <span>回退原因</span>
                  <p>{result.pipeline_error}</p>
                </div>
              )}
            </div>
          )}
          {scoreRows.length > 0 && (
            <div className="analysis-score-grid">
              {scoreRows.map(([label, value]) => (
                <div className="analysis-score-card" key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
          )}
          {segmentBreakdowns.length > 0 && (
            <div className="analysis-section">
              <strong>分段拆解</strong>
              {segmentBreakdowns.map((segment, index) => (
                <div className="analysis-field" key={segment.segment_id || index}>
                  <span>
                    {segment.time_range || segment.segment_id || `片段 ${index + 1}`} · {segment.segment_role || "未标注角色"}
                  </span>
                  <p>
                    {[segment.hook, segment.conflict_or_value, segment.emotion, segment.copywriting_pattern, segment.commerce_signal, segment.replicable_point]
                      .filter(Boolean)
                      .join(" / ") || "暂无内容"}
                  </p>
                </div>
              ))}
            </div>
          )}
          {sections.map(([sectionTitle, rows]) => (
            <div className="analysis-section" key={sectionTitle}>
              <strong>{sectionTitle}</strong>
              {rows.map(([label, value]) => (
                <div className="analysis-field" key={label}>
                  <span>{label}</span>
                  <p>{value || "暂无内容"}</p>
                </div>
              ))}
            </div>
          ))}
          <details className="raw-json">
            <summary>查看原始 JSON</summary>
            <pre className="result-box">{JSON.stringify(result.raw_model_json || result, null, 2)}</pre>
          </details>
        </div>
      </section>
    </div>
  );
}

function PromptReverseResultModal({ task, onClose }) {
  if (!task) return null;
  const result = task.result || {};
  const shotPrompts = Array.isArray(result.shot_prompts) ? result.shot_prompts : [];
  const audioScript = Array.isArray(result.audio_script) ? result.audio_script : [];
  const segmentReconstructions = Array.isArray(result.segment_reconstructions) ? result.segment_reconstructions : [];

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="modal-panel" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <h2>AI 提示词反推结果</h2>
            <p>{task.title}</p>
          </div>
          <button className="text-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="analysis-result-body">
          <p>{result.summary || "暂无摘要"}</p>
          {result.reconstruction_strategy && (
            <div className="analysis-section">
              <strong>复刻策略</strong>
              <p>{result.reconstruction_strategy}</p>
            </div>
          )}
          <div className="analysis-section">
            <strong>完整提示词</strong>
            <p>{result.master_prompt || "暂无内容"}</p>
          </div>
          <div className="analysis-section">
            <strong>负向提示词</strong>
            <p>{result.negative_prompt || "暂无内容"}</p>
          </div>
          <div className="analysis-section">
            <strong>脚本时间线</strong>
            {audioScript.length ? (
              audioScript.map((item, index) => (
                <div className="analysis-field" key={index}>
                  <span>{item.time_range || `片段 ${index + 1}`}</span>
                  <p>{item.line || item.text || "暂无内容"}</p>
                </div>
              ))
            ) : (
              <p>暂无脚本时间线</p>
            )}
          </div>
          <div className="analysis-section">
            <strong>镜头级复刻</strong>
            {shotPrompts.length ? (
              shotPrompts.map((item, index) => (
                <div className="analysis-field shot-replica-field" key={index}>
                  <span>{item.shot || `镜头 ${index + 1}`} {item.time_range ? `· ${item.time_range}` : ""}</span>
                  <dl className="shot-replica-list">
                    <div>
                      <dt>脚本</dt>
                      <dd>{item.script_line || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>画面</dt>
                      <dd>{item.visual_description || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>首帧</dt>
                      <dd>{item.first_frame || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>尾帧</dt>
                      <dd>{item.last_frame || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>运镜</dt>
                      <dd>{item.camera_movement || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>主体动作</dt>
                      <dd>{item.subject_motion || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>构图</dt>
                      <dd>{item.composition || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>光色</dt>
                      <dd>{item.lighting_color || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>转场</dt>
                      <dd>{item.transition || "暂无内容"}</dd>
                    </div>
                    <div className="wide">
                      <dt>镜头提示词</dt>
                      <dd>{item.prompt || "暂无内容"}</dd>
                    </div>
                    <div className="wide">
                      <dt>负向提示词</dt>
                      <dd>{item.negative_prompt || "暂无内容"}</dd>
                    </div>
                  </dl>
                  {Array.isArray(item.reference_frames) && item.reference_frames.length > 0 && (
                    <p>参考帧：{item.reference_frames.join(" / ")}</p>
                  )}
                </div>
              ))
            ) : (
              <p>暂无镜头级复刻内容</p>
            )}
          </div>
          {segmentReconstructions.length > 0 && (
            <div className="analysis-section">
              <strong>分段证据复刻</strong>
              {segmentReconstructions.map((segment, index) => (
                <div className="analysis-field" key={segment.segment_id || index}>
                  <span>{segment.time_range || segment.segment_id || `片段 ${index + 1}`}</span>
                  <p>{segment.segment_script || segment.continuity_notes || "暂无内容"}</p>
                  {Array.isArray(segment.shots) && segment.shots.length > 0 && (
                    <p>{segment.shots.map((shot) => `${shot.shot || "镜头"}：${shot.prompt || shot.visual_description || ""}`).join("\n")}</p>
                  )}
                </div>
              ))}
            </div>
          )}
          <div className="analysis-section">
            <strong>风格关键词</strong>
            <div className="breakdown-tags">
              {(result.style_keywords || []).map((keyword) => (
                <Badge key={keyword}>{keyword}</Badge>
              ))}
            </div>
          </div>
          <div className="analysis-section">
            <strong>使用建议</strong>
            {(result.usage_notes || []).map((note, index) => (
              <p key={index}>{note}</p>
            ))}
          </div>
          <details className="raw-json">
            <summary>查看原始 JSON</summary>
            <pre className="result-box">{JSON.stringify(task, null, 2)}</pre>
          </details>
        </div>
      </section>
    </div>
  );
}

function App() {
  const [activeSection, setActiveSection] = useState("dashboard");
  const [activeSetting, setActiveSetting] = useState("ai-provider");
  const [activeJianyingEditor, setActiveJianyingEditor] = useState("script");
  const [activeToolId, setActiveToolId] = useState("");
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [workbench, setWorkbench] = useState(fallbackWorkbench);
  const [apiState, setApiState] = useState("示例数据");
  const [analysisTasks, setAnalysisTasks] = useState([]);
  const [promptReverseTasks, setPromptReverseTasks] = useState([]);
  const [analysisArchives, setAnalysisArchives] = useState([]);
  const [promptReverseArchives, setPromptReverseArchives] = useState([]);
  const [libraryType, setLibraryType] = useState("all");
  const [selectedAnalysisTask, setSelectedAnalysisTask] = useState(null);
  const [selectedPromptReverseTask, setSelectedPromptReverseTask] = useState(null);
  const [selectedLibraryItem, setSelectedLibraryItem] = useState(null);
  const [taskSyncError, setTaskSyncError] = useState("");
  const [lastTaskRefresh, setLastTaskRefresh] = useState("");

  async function refreshAnalysisTaskList() {
    const tasks = await fetchTasks("ai_video_analysis");
    setAnalysisTasks(tasks.map((task) => normalizeAnalysisTask(task)));
    setTaskSyncError("");
    setLastTaskRefresh(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  }

  async function refreshPromptReverseTaskList() {
    const tasks = await fetchTasks("ai_prompt_reverse");
    setPromptReverseTasks(tasks.map(normalizePromptReverseTask));
    setTaskSyncError("");
    setLastTaskRefresh(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  }

  useEffect(() => {
    fetchWorkbench()
      .then((data) => {
        setWorkbench(data);
        setApiState("后端已连接");
      })
      .catch(() => {
        setApiState("示例数据");
      });
  }, []);

  useEffect(() => {
    async function loadArchives() {
      try {
        const [analysis, promptReverse] = await Promise.all([
          fetchAiVideoArchives(),
          fetchAiPromptReverseArchives(),
        ]);
        setAnalysisArchives(analysis);
        setPromptReverseArchives(promptReverse);
      } catch {
        // Archive panels can stay empty if backend is still starting.
      }
    }

    loadArchives();
  }, [analysisTasks, promptReverseTasks]);

  useEffect(() => {
    let mounted = true;

    async function loadPromptReverseTasks() {
      try {
        if (mounted) {
          await refreshPromptReverseTaskList();
        }
      } catch (err) {
        if (mounted) {
          setTaskSyncError(`提示词反推任务刷新失败：${err.message}`);
        }
      }
    }

    loadPromptReverseTasks();
    const timer = window.setInterval(loadPromptReverseTasks, 2500);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadAnalysisTasks() {
      try {
        if (mounted) {
          await refreshAnalysisTaskList();
        }
      } catch (err) {
        if (mounted) {
          setTaskSyncError(`AI 视频拆解任务刷新失败：${err.message}`);
        }
      }
    }

    loadAnalysisTasks();
    const timer = window.setInterval(loadAnalysisTasks, 2500);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  async function handleCreateVideoBreakdown(video) {
    try {
      const task = await createAiVideoBreakdownJob(video);
      const normalized = normalizeAnalysisTask(task);
      setAnalysisTasks((current) => [normalized, ...current.filter((item) => item.id !== normalized.id)]);
      window.setTimeout(() => refreshAnalysisTaskList().catch((err) => setTaskSyncError(`AI 视频拆解任务刷新失败：${err.message}`)), 800);
      window.setTimeout(() => refreshAnalysisTaskList().catch((err) => setTaskSyncError(`AI 视频拆解任务刷新失败：${err.message}`)), 3000);
      return { job_id: normalized.id, status: normalized.status, result: normalized.result };
    } catch (err) {
      throw err;
    }
  }

  async function handleCreatePromptReverse(video) {
    const task = await createAiPromptReverseJob(video);
    const normalized = normalizePromptReverseTask(task);
    setPromptReverseTasks((current) => [normalized, ...current.filter((item) => item.id !== normalized.id)]);
    window.setTimeout(() => refreshPromptReverseTaskList().catch((err) => setTaskSyncError(`提示词反推任务刷新失败：${err.message}`)), 800);
    window.setTimeout(() => refreshPromptReverseTaskList().catch((err) => setTaskSyncError(`提示词反推任务刷新失败：${err.message}`)), 3000);
    return { job_id: normalized.id, status: normalized.status, result: normalized.result };
  }

  async function handleArchiveAnalysisTask(task) {
    const response = await archiveTask(task.id);
    if (response.archive) {
      setAnalysisArchives((current) => [response.archive, ...current.filter((item) => (item.task_id || item.id) !== task.id)]);
    }
  }

  async function handleArchivePromptReverseTask(task) {
    const response = await archiveTask(task.id);
    if (response.archive) {
      setPromptReverseArchives((current) => [response.archive, ...current.filter((item) => (item.task_id || item.id) !== task.id)]);
    }
  }

  async function handleDeleteAnalysisTask(task) {
    if (!window.confirm("确认删除这个任务及关联归档吗？")) {
      return;
    }
    await deleteTask(task.id);
    setAnalysisTasks((current) => current.filter((item) => item.id !== task.id));
    setAnalysisArchives((current) => current.filter((item) => item.task_id !== task.id && item.id !== task.id));
  }

  async function handleDeletePromptReverseTask(task) {
    if (!window.confirm("确认删除这个任务及关联归档吗？")) {
      return;
    }
    await deleteTask(task.id);
    setPromptReverseTasks((current) => current.filter((item) => item.id !== task.id));
    setPromptReverseArchives((current) => current.filter((item) => item.task_id !== task.id && item.id !== task.id));
  }

  const metrics = workbench.metrics?.length ? workbench.metrics : fallbackWorkbench.metrics;
  const tools = workbench.tools?.length ? workbench.tools : fallbackWorkbench.tools;
  const jobs = workbench.jobs?.length ? workbench.jobs : fallbackWorkbench.jobs;
  const library = workbench.library?.length ? workbench.library : fallbackWorkbench.library;
  const integrations = workbench.integrations?.length
    ? workbench.integrations
    : fallbackWorkbench.integrations;

  const filteredTools = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return tools.filter((tool) => {
      if (tool.id === "jianying-editor-sdk") return false;
      const filterMatched = filter === "all" || tool.status === filter;
      const text = [tool.name, tool.desc, tool.status, ...tool.tags].join(" ").toLowerCase();
      return filterMatched && (!normalized || text.includes(normalized));
    });
  }, [filter, query, tools]);

  const filteredLibrary = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return library;
    return library.filter((item) =>
      [item.title, item.desc, item.type, ...item.tags].join(" ").toLowerCase().includes(normalized),
    );
  }, [query, library]);

  const archiveItems = useMemo(() => {
    const analysisItems = analysisArchives.map((item) => {
      const result = normalizeCommercialAnalysisResult(item.result || {});
      return {
        ...item,
        result,
        archiveType: "analysis",
        type: "AI 视频拆解",
        desc: result.summary || "商业拆解档案",
      };
    });
    const promptItems = promptReverseArchives.map((item) => ({
      ...item,
      archiveType: "prompt",
      type: "AI 提示词反推",
      desc: item.result?.summary || item.result?.master_prompt || "提示词反推档案",
    }));
    const combined = [...analysisItems, ...promptItems];
    if (libraryType === "analysis") return analysisItems;
    if (libraryType === "prompt") return promptItems;
    return combined;
  }, [analysisArchives, promptReverseArchives, libraryType]);

  const archivedAnalysisIds = useMemo(() => archiveIdSet(analysisArchives), [analysisArchives]);
  const archivedPromptReverseIds = useMemo(() => archiveIdSet(promptReverseArchives), [promptReverseArchives]);
  const visibleLibraryItems = useMemo(() => {
    const items = libraryType === "seed" ? filteredLibrary : archiveItems;
    const normalized = query.trim().toLowerCase();
    if (!normalized) return items;
    return items.filter((item) => {
      const presentation = archivePresentation(item);
      const text = [
        presentation.toolLabel,
        presentation.toolDetail,
        presentation.headline,
        presentation.summary,
        ...(presentation.tags || []),
      ].join(" ").toLowerCase();
      return text.includes(normalized);
    });
  }, [archiveItems, filteredLibrary, libraryType, query]);
  const libraryGroups = useMemo(() => {
    if (libraryType === "seed") {
      return [
        {
          key: "seed",
          title: "示例素材",
          desc: "系统内置的参考素材和占位内容。",
          items: visibleLibraryItems,
        },
      ];
    }
    return [
      {
        key: "analysis",
        title: "AI 视频拆解",
        desc: "手动归档的视频商业拆解结果，适合复盘钩子、场景和转化逻辑。",
        items: visibleLibraryItems.filter((item) => item.archiveType === "analysis"),
      },
      {
        key: "prompt",
        title: "AI 提示词反推",
        desc: "手动归档的生成提示词反推结果，适合二次创作和模型复用。",
        items: visibleLibraryItems.filter((item) => item.archiveType === "prompt"),
      },
    ].filter((group) => libraryType === "all" || group.key === libraryType);
  }, [libraryType, visibleLibraryItems]);

  const visibleAnalysisTasks = analysisTasks.filter((task) => !archivedAnalysisIds.has(task.id));
  const visiblePromptReverseTasks = promptReverseTasks.filter((task) => !archivedPromptReverseIds.has(task.id));
  const failedAnalysisTasks = visibleAnalysisTasks.filter((task) => task.status === "error");
  const runningAnalysisTasks = visibleAnalysisTasks.filter((task) => !["done", "error"].includes(task.status));
  const completedAnalysisTasks = visibleAnalysisTasks.filter((task) => task.status === "done");
  const failedPromptReverseTasks = visiblePromptReverseTasks.filter((task) => task.status === "error");
  const runningPromptReverseTasks = visiblePromptReverseTasks.filter((task) => !["done", "error"].includes(task.status));
  const completedPromptReverseTasks = visiblePromptReverseTasks.filter((task) => task.status === "done");

  const [title, subtitle] = sections[activeSection];

  return (
    <>
      <aside className="sidebar" aria-label="主导航">
        <div className="brand">
          <div className="brand-mark">T</div>
          <div>
            <strong>工具工作台</strong>
            <span>Personal Ops</span>
          </div>
        </div>

        <nav className="nav-list">
          {navItems.map(([id, Icon, label]) => (
            <React.Fragment key={id}>
              <button
                className={`nav-item ${activeSection === id ? "active" : ""}`}
                type="button"
                onClick={() => setActiveSection(id)}
              >
                <Icon size={18} />
                <span>{label}</span>
              </button>
              {id === "settings" && activeSection === "settings" && (
                <div className="settings-subnav">
                  {settingItems.map(([value, text]) => (
                    <button
                      className={`settings-subnav-item ${activeSetting === value ? "active" : ""}`}
                      key={value}
                      type="button"
                      onClick={() => setActiveSetting(value)}
                    >
                      <span className="settings-subnav-arrow">{activeSetting === value ? "▾" : "▸"}</span>
                      <span>{text}</span>
                    </button>
                  ))}
                </div>
              )}
              {id === "jianyingEditor" && activeSection === "jianyingEditor" && (
                <div className="settings-subnav">
                  {jianyingEditorItems.map(([value, text]) => (
                    <button
                      className={`settings-subnav-item ${activeJianyingEditor === value ? "active" : ""}`}
                      key={value}
                      type="button"
                      onClick={() => setActiveJianyingEditor(value)}
                    >
                      <span className="settings-subnav-arrow">{activeJianyingEditor === value ? "▾" : "▸"}</span>
                      <span>{text}</span>
                    </button>
                  ))}
                </div>
              )}
            </React.Fragment>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className="status-dot" />
          <span>{apiState}</span>
        </div>
      </aside>

      <main className="shell">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
          <div className="topbar-actions">
            <label className="search-box">
              <Search size={17} />
              <input
                type="search"
                placeholder="搜索工具、任务、素材"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <button className="icon-button" type="button" title="刷新">
              <RefreshCw size={17} />
            </button>
          </div>
        </header>

        <section className={activeSection === "dashboard" ? "" : "section-cache-hidden"}>
            <DouyinCollectorPanel onBreakdown={handleCreateVideoBreakdown} onPromptReverse={handleCreatePromptReverse} />
            {failedAnalysisTasks.length > 0 && (
              <AnalysisTaskPanel
                tasks={failedAnalysisTasks}
                onOpenResult={setSelectedAnalysisTask}
                compact
                title="异常的 AI 视频拆解"
              />
            )}
            {failedPromptReverseTasks.length > 0 && (
              <AnalysisTaskPanel
                tasks={failedPromptReverseTasks}
                onOpenResult={setSelectedPromptReverseTask}
                compact
                title="异常的提示词反推"
              />
            )}

            <div className="metric-grid">
              {metrics.map((metric) => (
                <article className="metric" key={metric.label}>
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                  <small>{metric.hint}</small>
                </article>
              ))}
            </div>
            <div className="dashboard-grid">
              <section className="panel">
                <div className="panel-header">
                  <h2>常用工具</h2>
                  <button className="text-button" type="button" onClick={() => setActiveSection("tools")}>
                    查看全部
                  </button>
                </div>
                <div className="tool-list">
                  {tools.slice(0, 2).map((tool) => (
                    <ToolCard key={tool.id} tool={tool} />
                  ))}
                </div>
              </section>

              <section className="panel">
                <div className="panel-header">
                  <h2>最近任务</h2>
                  <button className="text-button" type="button" onClick={() => setActiveSection("jobs")}>
                    任务中心
                  </button>
                </div>
                <div className="job-list">
                  {jobs.slice(0, 3).map((job) => (
                    <JobRow key={job.id} job={job} />
                  ))}
                </div>
              </section>
            </div>

            <div className="sample-grid">
              <section className="panel">
                <div className="panel-header">
                  <h2>工具接入流程</h2>
                  <Badge status="ready">模板已预留</Badge>
                </div>
                <div className="step-list">
                  {[
                    ["1", "添加 GitHub 项目适配器", "在 integrations/ 下新建目录，记录仓库地址、配置项和运行入口。"],
                    ["2", "注册到工具中心", "在后端注册工具名称、输入表单、任务类型和输出结果格式。"],
                    ["3", "接入任务中心", "耗时任务统一进入队列，页面只关心进度、日志和结果。"],
                  ].map(([index, name, desc]) => (
                    <article className="step-item" key={index}>
                      <span>{index}</span>
                      <div>
                        <strong>{name}</strong>
                        <p>{desc}</p>
                      </div>
                    </article>
                  ))}
                </div>
              </section>

              <section className="panel">
                <div className="panel-header">
                  <h2>下一批样例工具</h2>
                  <button className="text-button" type="button" onClick={() => setActiveSection("integrations")}>
                    查看接入
                  </button>
                </div>
                <div className="mini-card-list">
                  {[
                    ["B站收藏归档", "同步收藏夹，生成标签和摘要。"],
                    ["图片批量放大", "封装开源超分项目，输出到素材库。"],
                    ["日报生成器", "读取本地工作记录，生成 Markdown 日报。"],
                  ].map(([name, desc]) => (
                    <article className="mini-card" key={name}>
                      <Activity size={18} />
                      <div>
                        <strong>{name}</strong>
                        <p>{desc}</p>
                      </div>
                    </article>
                  ))}
                </div>
              </section>

              <section className="panel wide-panel">
                <div className="panel-header">
                  <h2>数据流转预览</h2>
                  <Badge>示例</Badge>
                </div>
                <div className="flow-row">
                  {["采集", "下载/调用开源项目", "内容分析", "入库", "页面查看"].map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
              </section>
            </div>
        </section>

        {activeSection === "tools" && (
          <section>
            {activeToolId === "jianying-editor-sdk" ? (
              <>
                <div className="section-toolbar">
                  <button className="text-button" type="button" onClick={() => setActiveToolId("")}>
                    返回工具列表
                  </button>
                </div>
                <JianyingEditorSdkPanel />
              </>
            ) : (
              <>
                <div className="section-toolbar">
                  <div className="segmented">
                    {[
                      ["all", "全部"],
                      ["ready", "可用"],
                      ["draft", "草稿"],
                    ].map(([id, label]) => (
                      <button
                        className={filter === id ? "active" : ""}
                        key={id}
                        type="button"
                        onClick={() => setFilter(id)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <button className="primary-button" type="button">
                    <Plus size={16} />
                    新工具
                  </button>
                </div>
                <div className="tool-grid">
                  {filteredTools.map((tool) => (
                    <ToolCard key={tool.id} tool={tool} onOpen={(item) => setActiveToolId(item.id)} />
                  ))}
                </div>
              </>
            )}
          </section>
        )}

        {activeSection === "jianyingEditor" && (
          <section>
            {activeJianyingEditor === "script" ? (
              <JianyingNaturalScriptPanel />
            ) : (
              <JianyingEditorSdkPanel activeView={activeJianyingEditor} />
            )}
          </section>
        )}

        {activeSection === "draftInspector" && (
          <section>
            <DraftInspectorPanel />
          </section>
        )}

        {activeSection === "jobs" && (
          <section className="jobs-layout">
            <div className={`task-sync-banner ${taskSyncError ? "error" : ""}`}>
              {taskSyncError || `任务进度自动刷新中${lastTaskRefresh ? ` · 最后刷新 ${lastTaskRefresh}` : ""}`}
            </div>
            <TaskToolGroup title="AI 视频拆解" desc="查看视频商业拆解任务的运行、完成和异常状态。">
              <AnalysisTaskPanel
                tasks={runningAnalysisTasks}
                onOpenResult={setSelectedAnalysisTask}
                onDeleteTask={handleDeleteAnalysisTask}
                onArchiveTask={handleArchiveAnalysisTask}
                archivedIds={archivedAnalysisIds}
                title="进行中"
                emptyText="当前没有运行中的视频拆解任务。"
              />
              <AnalysisTaskPanel
                tasks={completedAnalysisTasks}
                onOpenResult={setSelectedAnalysisTask}
                onDeleteTask={handleDeleteAnalysisTask}
                onArchiveTask={handleArchiveAnalysisTask}
                archivedIds={archivedAnalysisIds}
                title="已完成"
                emptyText="完成的视频拆解会显示在这里。"
              />
              <AnalysisTaskPanel
                tasks={failedAnalysisTasks}
                onOpenResult={setSelectedAnalysisTask}
                onDeleteTask={handleDeleteAnalysisTask}
                onArchiveTask={handleArchiveAnalysisTask}
                archivedIds={archivedAnalysisIds}
                title="异常"
                emptyText="暂无异常的视频拆解任务。"
              />
            </TaskToolGroup>

            <TaskToolGroup title="AI 提示词反推" desc="查看从视频反推出生成提示词的任务状态和结果。">
              <AnalysisTaskPanel
                tasks={runningPromptReverseTasks}
                onOpenResult={setSelectedPromptReverseTask}
                onDeleteTask={handleDeletePromptReverseTask}
                onArchiveTask={handleArchivePromptReverseTask}
                archivedIds={archivedPromptReverseIds}
                title="进行中"
                emptyText="当前没有运行中的提示词反推任务。"
              />
              <AnalysisTaskPanel
                tasks={completedPromptReverseTasks}
                onOpenResult={setSelectedPromptReverseTask}
                onDeleteTask={handleDeletePromptReverseTask}
                onArchiveTask={handleArchivePromptReverseTask}
                archivedIds={archivedPromptReverseIds}
                title="已完成"
                emptyText="完成的提示词反推会显示在这里。"
              />
              <AnalysisTaskPanel
                tasks={failedPromptReverseTasks}
                onOpenResult={setSelectedPromptReverseTask}
                onDeleteTask={handleDeletePromptReverseTask}
                onArchiveTask={handleArchivePromptReverseTask}
                archivedIds={archivedPromptReverseIds}
                title="异常"
                emptyText="暂无异常的提示词反推任务。"
              />
            </TaskToolGroup>
            <section className="table-panel">
              <table>
                <thead>
                  <tr>
                    <th>任务</th>
                    <th>所属工具</th>
                    <th>状态</th>
                    <th>进度</th>
                    <th>更新时间</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <JobRow key={job.id} job={job} table />
                  ))}
                </tbody>
              </table>
            </section>
          </section>
        )}

        {activeSection === "library" && (
          <section className="library-layout">
            <aside className="filter-panel">
              <div className="filter-panel-head">
                <div>
                  <h2>筛选</h2>
                  <p>点击下方条目查看完整内容。</p>
                </div>
                <Badge>{visibleLibraryItems.length} 条结果</Badge>
              </div>
              <label>
                类型
                <select value={libraryType} onChange={(event) => setLibraryType(event.target.value)}>
                  <option value="all">AI 归档全部</option>
                  <option value="analysis">AI 拆解</option>
                  <option value="prompt">反推提示词</option>
                  <option value="seed">示例素材</option>
                </select>
              </label>
              <label>
                标签
                <select>
                  <option>全部标签</option>
                  <option>灵感</option>
                  <option>工作</option>
                  <option>待处理</option>
                </select>
              </label>
            </aside>
            <div className="library-list">
              {libraryGroups.map((group) => (
                <LibraryArchiveGroup key={group.key} title={group.title} desc={group.desc} items={group.items}>
                  {group.items.map((item) => {
                    const presentation = archivePresentation(item);
                    return (
                      <article
                        className={`library-card ${item.archiveType ? "archive-library-card" : ""}`}
                        key={item.id}
                        onClick={() => {
                          if (item.archiveType === "analysis") {
                            setSelectedAnalysisTask({
                              id: item.task_id,
                              title: item.title,
                              result: item.result,
                            });
                          }
                          if (item.archiveType === "prompt") {
                            setSelectedPromptReverseTask({
                              id: item.task_id,
                              title: item.title,
                              result: item.result,
                            });
                          }
                          if (!item.archiveType) {
                            setSelectedLibraryItem({
                              ...item,
                              presentation,
                              raw: item,
                            });
                          }
                        }}
                      >
                        <div className="archive-thumb">
                          <span>{presentation.toolLabel}</span>
                          <strong>{item.archiveType === "analysis" ? "拆解" : item.archiveType === "prompt" ? "提示词" : "素材"}</strong>
                        </div>
                        <div className="archive-card-body">
                          <div className="archive-card-head">
                            <span>{presentation.toolDetail}</span>
                            <h3>{presentation.headline}</h3>
                          </div>
                          <p>{presentation.summary}</p>
                          {presentation.highlights.length > 0 && (
                            <div className="archive-highlight-grid">
                              {presentation.highlights.slice(0, 3).map(([label, value]) => (
                                <div className="archive-highlight" key={label}>
                                  <span>{label}</span>
                                  <p>{value}</p>
                                </div>
                              ))}
                            </div>
                          )}
                          <div className="library-meta">
                            {presentation.tags.map((tag) => (
                              <Badge key={tag}>{tag}</Badge>
                            ))}
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </LibraryArchiveGroup>
              ))}
              {!visibleLibraryItems.length && <div className="empty-result">暂无归档内容。在任务中心点击“归档”后会出现在这里。</div>}
            </div>
          </section>
        )}

        {activeSection === "integrations" && (
          <section className="integration-grid">
            {integrations.map((integration) => (
              <article className="panel integration-card" key={integration.id}>
                <div className="integration-icon">
                  {integration.kind === "python" ? <FolderCog size={20} /> : <Database size={20} />}
                </div>
                <div>
                  <h2>{integration.name}</h2>
                  <p>{integration.desc}</p>
                  <div className="tool-meta">
                    <Badge>{integration.kind}</Badge>
                    <Badge status={integration.status}>{integration.status}</Badge>
                  </div>
                </div>
              </article>
            ))}
          </section>
        )}

        {activeSection === "settings" && (
          <section className="settings-grid">
            {activeSetting === "ai-provider" && <AiProviderSettingsPanel />}
            {activeSetting === "douyin" && <DouyinSettingsPanel />}
            {activeSetting === "ai-video" && <AiVideoSettingsPanel />}
            {activeSetting === "ai-prompt" && <AiPromptReverseSettingsPanel />}
            {activeSetting === "jianying" && <JianyingDraftSettingsPanel />}
          </section>
        )}
      </main>
      <AnalysisResultModal task={selectedAnalysisTask} onClose={() => setSelectedAnalysisTask(null)} />
      <PromptReverseResultModal task={selectedPromptReverseTask} onClose={() => setSelectedPromptReverseTask(null)} />
      <LibraryItemModal item={selectedLibraryItem} onClose={() => setSelectedLibraryItem(null)} />
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
