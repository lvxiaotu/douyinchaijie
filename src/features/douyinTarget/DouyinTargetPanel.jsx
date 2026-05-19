import { useEffect, useMemo, useState } from "react";
import { Badge } from "../../components/common/index";
import {
  createDouyinTargetSet,
  collectDouyinTargetInteractions,
  collectDouyinTargetVideos,
  deleteDouyinTargetSet,
  deleteDouyinTargetVideoAnalysis,
  enqueueDouyinTargetAnalysis,
  fetchDouyinTargetSet,
  fetchDouyinTargetSets,
  updateDouyinTargetSet,
  saveDouyinTargetUsers,
  searchDouyinTargets,
  syncDouyinTargetAnalysis,
} from "../../services/api";

function compactNumber(value) {
  if (value === null || value === undefined || value === "") return "未知";
  const number = Number(value);
  if (!Number.isFinite(number)) return "未知";
  if (number >= 100000000) return `${(number / 100000000).toFixed(1)}亿`;
  if (number >= 10000) return `${(number / 10000).toFixed(1)}万`;
  return String(number);
}

function optionalCompactNumber(value) {
  const text = compactNumber(value);
  return text === "未知" ? "暂无" : text;
}

function formatDate(seconds) {
  if (!seconds) return "未知";
  return new Date(Number(seconds) * 1000).toLocaleDateString("zh-CN");
}

function optionalDate(seconds) {
  const text = formatDate(seconds);
  return text === "未知" ? "暂无" : text;
}

function analysisStatusLabel(status) {
  const labels = {
    none: "未拆解",
    pending: "排队中",
    running: "拆解中",
    done: "已完成",
    failed: "失败",
    superseded: "已替换",
  };
  return labels[status || "none"] || status;
}

function commentStatusLabel(video) {
  const status = video.comment_snapshot_status || "none";
  const comments = Number(video.comment_saved_count || 0);
  const replies = Number(video.reply_saved_count || 0);
  if (status === "done") return `评论已保存 ${comments} 条 / 回复 ${replies} 条`;
  if (status === "failed") return "评论采集失败";
  if (status === "running") return "评论采集中";
  return "评论未采集";
}

function commentStatusTone(video) {
  const status = video.comment_snapshot_status || "none";
  if (status === "done") return "done";
  if (status === "failed") return "error";
  if (status === "running") return "running";
  return "draft";
}

function analysisStatusTone(status) {
  if (status === "done") return "done";
  if (status === "failed") return "error";
  if (status === "pending" || status === "running") return "running";
  return "draft";
}

function hasAnalysisRecord(video) {
  const status = video.analysis_status || "none";
  return status !== "none" || Boolean(video.analysis_task_id);
}

function busyLabel(busy) {
  const labels = {
    search: "正在持续搜索账号，直到达到目标数量或没有更多结果...",
    "search-more": "正在加载下一页账号...",
    collect: "正在逐个账号采集作品，账号较多时会比较久，请保持页面打开...",
    interactions: "正在补全评论、回复和互动洞察，视频较多时会比较久...",
    "interaction-one": "正在补全单条视频互动数据...",
    enqueue: "正在加入 AI 拆解任务池...",
    sync: "正在同步拆解结果...",
    save: "正在保存选中账号...",
    "create-set": "正在创建合集...",
    "update-set": "正在保存合集修改...",
    "delete-set": "正在删除合集...",
    "delete-analysis": "正在删除拆解记录...",
  };
  return labels[busy] || "";
}

function userId(user) {
  return user.sec_user_id || user.sec_uid || user.uid || user.unique_id;
}

function cleanKeyword(value) {
  return String(value || "").trim();
}

function timestampLabel(date = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}`;
}

function defaultSetName(keyword) {
  return `${cleanKeyword(keyword) || "抖音对标"}-${timestampLabel()}`;
}

function createSetDraft(keyword) {
  const nextKeyword = cleanKeyword(keyword);
  return {
    name: defaultSetName(nextKeyword),
    note: "",
    keyword: nextKeyword,
    status: "draft",
  };
}

const InitialKeyword = "可爱";
const SearchPageSize = 20;
const MaxContinuousSearchPages = 25;

function mergeUniqueUsers(current, incoming) {
  const seen = new Set(current.map(userId).filter(Boolean));
  const merged = [...current];
  incoming.forEach((item) => {
    const id = userId(item);
    if (id && seen.has(id)) return;
    if (id) seen.add(id);
    merged.push(item);
  });
  return merged;
}

function appendSelectedUserIds(current, items) {
  const next = new Set(current);
  items.forEach((item) => {
    const id = userId(item);
    if (id) next.add(id);
  });
  return next;
}

function targetAccountCount(filters) {
  const count = Number(filters.targetAccountCount || 0);
  if (!Number.isFinite(count)) return SearchPageSize;
  return Math.max(1, Math.min(Math.floor(count), 500));
}

function hasMoreSearchResults(result, items) {
  const hasMore = result?.has_more ?? result?.pagination?.has_more ?? result?.normalized?.has_more;
  if (hasMore === false || hasMore === 0) return false;
  if (hasMore === true || hasMore === 1) return true;
  return items.length > 0;
}

function formatCollectErrors(errors = []) {
  const visible = errors.slice(0, 8);
  const names = visible.map((item) => item.nickname || item.user_id || "未命名账号").join("、");
  const suffix = errors.length > visible.length ? ` 等 ${errors.length} 个账号` : "";
  const firstDetail = errors.find((item) => item.error)?.error;
  return `部分账号采集失败 ${errors.length} 个：${names}${suffix}${firstDetail ? `。首个错误：${firstDetail}` : ""}`;
}

const FollowerRanges = [
  ["", "全部"],
  ["1-5w", "1-5W粉丝"],
  ["5-10w", "5-10W粉丝"],
  ["10-20w", "10-20W粉丝"],
  ["20-50w", "20-50W粉丝"],
  ["50w+", "50W以上粉丝"],
];

const FollowerThresholds = [
  ["below_1w", "1万以下"],
  ["above_1w", "1万以上（全部）"],
];

const VideoRanges = [
  ["", "全部"],
  ["0-50", "0-50"],
  ["50-100", "50-100"],
  ["100-500", "100-500"],
  ["500+", "500以上"],
];

const UpdateRanges = [
  ["", "全部"],
  ["7", "一周以内"],
  ["30", "一个月以内"],
  ["180", "半年以内"],
  ["365", "一年以内"],
  ["365+", "一年以上"],
];

function buildSearchPayload(filters) {
  const payload = {
    minLikes: filters.minLikes,
    sortBy: filters.sortBy,
  };
  const followerThreshold = filters.followerThreshold || "above_1w";
  const followerRange = filters.followerRange || "";
  const videoRange = filters.videoRange || "";
  const updateRange = filters.updateRange || "";
  if (followerThreshold === "above_1w") {
    payload.minFollowers = 10000;
  } else if (followerThreshold === "below_1w") {
    payload.maxFollowers = 9999;
  }

  if (followerThreshold !== "below_1w" && followerRange === "1-5w") {
    payload.minFollowers = 10000;
    payload.maxFollowers = 50000;
  } else if (followerThreshold !== "below_1w" && followerRange === "5-10w") {
    payload.minFollowers = 50000;
    payload.maxFollowers = 100000;
  } else if (followerThreshold !== "below_1w" && followerRange === "10-20w") {
    payload.minFollowers = 100000;
    payload.maxFollowers = 200000;
  } else if (followerThreshold !== "below_1w" && followerRange === "20-50w") {
    payload.minFollowers = 200000;
    payload.maxFollowers = 500000;
  } else if (followerThreshold !== "below_1w" && followerRange === "50w+") {
    payload.minFollowers = 500000;
  }

  if (videoRange === "0-50") {
    payload.minVideos = 0;
    payload.maxVideos = 50;
  } else if (videoRange === "50-100") {
    payload.minVideos = 50;
    payload.maxVideos = 100;
  } else if (videoRange === "100-500") {
    payload.minVideos = 100;
    payload.maxVideos = 500;
  } else if (videoRange === "500+") {
    payload.minVideos = 500;
  }

  if (updateRange === "7") {
    payload.recentWithinDays = 7;
  } else if (updateRange === "30") {
    payload.recentWithinDays = 30;
  } else if (updateRange === "180") {
    payload.recentWithinDays = 180;
  } else if (updateRange === "365") {
    payload.recentWithinDays = 365;
  } else if (updateRange === "365+") {
    payload.olderThanDays = 365;
  }

  return payload;
}

function normalizeUserForSave(user, keyword) {
  return {
    keyword,
    sec_user_id: user.sec_uid || user.sec_user_id || "",
    sec_uid: user.sec_uid || user.sec_user_id || "",
    uid: user.uid || "",
    unique_id: user.unique_id || "",
    nickname: user.nickname || "",
    avatar_url: user.avatar || user.avatar_url || "",
    signature: user.signature || "",
    follower_count: user.follower_count ?? null,
    like_count: user.like_count ?? null,
    aweme_count: user.aweme_count ?? null,
    following_count: user.following_count ?? null,
    recent_update_at: user.recent_update_at || user.last_post_at || null,
    last_post_at: user.last_post_at || user.recent_update_at || null,
    verified: Boolean(user.verified),
    is_private: Boolean(user.is_private),
    status: "selected",
    source_json: user.raw || user,
  };
}

export function DouyinTargetPanel() {
  const [keyword, setKeyword] = useState(InitialKeyword);
  const [filters, setFilters] = useState({
    targetAccountCount: 50,
    followerThreshold: "above_1w",
    followerRange: "",
    minLikes: "",
    videoRange: "",
    updateRange: "",
    sortBy: "likes",
  });
  const [searchResult, setSearchResult] = useState(null);
  const [searchRequest, setSearchRequest] = useState(null);
  const [searchPage, setSearchPage] = useState(0);
  const [searchHasMore, setSearchHasMore] = useState(false);
  const [selectedUsers, setSelectedUsers] = useState(new Set());
  const [sets, setSets] = useState([]);
  const [activeSetId, setActiveSetId] = useState("");
  const [activeSet, setActiveSet] = useState(null);
  const [setForm, setSetForm] = useState(() => createSetDraft(InitialKeyword));
  const [strategy, setStrategy] = useState({
    mode: "top",
    perUserLimit: 5,
    fetchCount: 20,
    sortMetric: "digg_count",
  });
  const [autoCollectInteractions, setAutoCollectInteractions] = useState(true);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const users = searchResult?.items || [];
  const selectedCount = selectedUsers.size;
  const activeVideos = activeSet?.videos || [];
  const activeUsers = activeSet?.users || [];
  const isCreatingSet = !activeSetId;
  const resolvedSetKeyword = cleanKeyword(setForm.keyword) || cleanKeyword(keyword);
  const resolvedSetName = cleanKeyword(setForm.name) || defaultSetName(resolvedSetKeyword);
  const visibleSetKeyword = isCreatingSet ? resolvedSetKeyword : setForm.keyword;
  const visibleSetName = isCreatingSet ? resolvedSetName : setForm.name;
  const busyText = busyLabel(busy);

  const selectedSearchUsers = useMemo(
    () => users.filter((item) => selectedUsers.has(userId(item))),
    [selectedUsers, users],
  );

  const searchPayload = useMemo(() => buildSearchPayload(filters), [filters]);

  async function loadSets(nextActiveSetId = activeSetId) {
    const data = await fetchDouyinTargetSets();
    setSets(data);
    const resolvedSetId = nextActiveSetId || "";
    setActiveSetId(resolvedSetId);
    if (resolvedSetId) {
      const detail = await fetchDouyinTargetSet(resolvedSetId);
      setActiveSet(detail);
      setSetForm({
        name: detail.name || "",
        note: detail.note || "",
        keyword: detail.keyword || "",
        status: detail.status || "draft",
      });
    } else {
      setActiveSet(null);
      setSetForm(createSetDraft(keyword));
    }
  }

  useEffect(() => {
    loadSets().catch(() => {});
  }, []);

  async function run(label, runner) {
    setBusy(label);
    setError("");
    setMessage("");
    try {
      const result = await runner();
      return result;
    } catch (err) {
      setError(err.message || String(err));
      return null;
    } finally {
      setBusy("");
    }
  }

  function handleKeywordChange(event) {
    const nextKeyword = event.target.value;
    setKeyword(nextKeyword);
    if (!activeSetId) {
      setSetForm((current) => ({
        ...current,
        ...createSetDraft(nextKeyword),
        note: current.note,
        status: current.status || "draft",
      }));
    }
  }

  async function selectSet(setId) {
    setActiveSetId(setId);
    if (setId) {
      fetchDouyinTargetSet(setId)
        .then((detail) => {
          setActiveSet(detail);
          setSetForm({
            name: detail.name || "",
            note: detail.note || "",
            keyword: detail.keyword || "",
            status: detail.status || "draft",
          });
        })
        .catch((err) => setError(err.message));
      return;
    }
    setActiveSet(null);
    setSetForm(createSetDraft(keyword));
  }

  async function handleSearch(event) {
    event.preventDefault();
    const request = { keyword, ...searchPayload };
    const targetCount = targetAccountCount(filters);
    const result = await run("search", async () => {
      let page = 1;
      let lastResult = null;
      let mergedItems = [];
      let hasMore = true;
      let loadedPages = 0;

      while (mergedItems.length < targetCount && hasMore && page <= MaxContinuousSearchPages) {
        const pageResult = await searchDouyinTargets({ ...request, page, count: SearchPageSize });
        const pageItems = pageResult.items || [];
        mergedItems = mergeUniqueUsers(mergedItems, pageItems).slice(0, targetCount);
        lastResult = pageResult;
        loadedPages = page;
        hasMore = hasMoreSearchResults(pageResult, pageItems);
        if (!hasMore) break;
        page += 1;
      }

      if (!lastResult) return null;
      return {
        ...lastResult,
        items: mergedItems,
        count: mergedItems.length,
        loaded_count: mergedItems.length,
        loaded_pages: loadedPages,
        requested_count: targetCount,
        reached_target: mergedItems.length >= targetCount,
        has_more: hasMore,
      };
    });
    if (result) {
      const nextItems = result.items || [];
      setSearchResult(result);
      setSearchRequest(request);
      setSearchPage(result.loaded_pages || 1);
      setSearchHasMore(hasMoreSearchResults(result, nextItems));
      setSelectedUsers(new Set(nextItems.map(userId).filter(Boolean)));
      if (!activeSetId) {
        setSetForm((current) => ({
          ...current,
          ...createSetDraft(keyword),
          note: current.note,
          status: current.status || "draft",
        }));
      }
      setMessage(
        result.reached_target
          ? `已持续搜索 ${result.loaded_pages || 1} 页，达到目标 ${nextItems.length}/${targetCount} 个候选账号`
          : `已搜索到 ${nextItems.length}/${targetCount} 个候选账号，暂无更多满足条件的账号`,
      );
    }
  }

  async function handleLoadMoreSearch() {
    if (!searchResult || busy) return;
    const nextPage = searchPage + 1;
    const request = searchRequest || { keyword, ...searchPayload };
    const result = await run("search-more", () =>
      searchDouyinTargets({ ...request, page: nextPage, count: SearchPageSize }),
    );
    if (result) {
      const nextItems = result.items || [];
      setSearchResult((current) => {
        const mergedItems = mergeUniqueUsers(current?.items || [], nextItems);
        return {
          ...result,
          items: mergedItems,
          count: mergedItems.length,
          loaded_count: mergedItems.length,
        };
      });
      setSearchPage(nextPage);
      setSearchHasMore(hasMoreSearchResults(result, nextItems));
      setSelectedUsers((current) => appendSelectedUserIds(current, nextItems));
      setMessage(`已加载第 ${nextPage} 页，新增 ${nextItems.length} 个候选账号`);
    }
  }

  async function handleSaveUsers() {
    if (!selectedSearchUsers.length) {
      setError("请先选择要保存的账号。");
      return;
    }
    const payload = {
      users: selectedSearchUsers.map((item) => normalizeUserForSave(item, keyword)),
      setId: activeSetId,
      setName: activeSetId ? "" : resolvedSetName,
      keyword: activeSetId ? keyword : resolvedSetKeyword,
      filters: searchPayload,
    };
    const result = await run("save", () => saveDouyinTargetUsers(payload));
    if (result) {
      setMessage(`已保存 ${result.count} 个账号到待对标库`);
      await loadSets(result.set?.id || activeSetId);
    }
  }

  async function handleCreateSet() {
    const result = await run("create-set", () =>
      createDouyinTargetSet({
        name: resolvedSetName,
        note: setForm.note,
        keyword: resolvedSetKeyword,
        filters: searchPayload,
        videoStrategy: strategy,
        status: setForm.status || "draft",
      }),
    );
    if (result) {
      setMessage(`已创建合集「${result.name}」`);
      await loadSets(result.id);
    }
  }

  async function handleUpdateSet() {
    if (!activeSetId) {
      setError("请先选择一个合集。");
      return;
    }
    const result = await run("update-set", () =>
      updateDouyinTargetSet(activeSetId, {
        name: setForm.name || activeSet?.name,
        note: setForm.note,
        keyword: setForm.keyword || keyword,
        filters: searchPayload,
        videoStrategy: strategy,
        status: setForm.status || activeSet?.status,
      }),
    );
    if (result) {
      setMessage(`已更新合集「${result.name}」`);
      await loadSets(activeSetId);
    }
  }

  async function handleDeleteSet(setId = activeSetId, setName = activeSet?.name) {
    if (!setId) {
      return;
    }
    if (!window.confirm(`确认删除合集「${setName || "当前合集"}」吗？`)) {
      return;
    }
    const result = await run("delete-set", () => deleteDouyinTargetSet(setId));
    if (result) {
      setMessage("已删除合集");
      await loadSets(setId === activeSetId ? "" : activeSetId);
    }
  }

  async function handleCollectVideos() {
    if (!activeSetId) {
      setError("请先选择或创建一个对标集合。");
      return;
    }
    const result = await run("collect", () => collectDouyinTargetVideos({ setId: activeSetId, ...strategy }));
    if (result) {
      setMessage(`已采集并选中 ${result.count} 条对标视频`);
      if (result.errors?.length) {
        setError(formatCollectErrors(result.errors));
      }
      await loadSets(activeSetId);
    }
  }

  async function handleCollectInteractions(videoId = "") {
    if (!activeSetId && !videoId) {
      setError("请先选择一个对标集合。");
      return;
    }
    const result = await run(videoId ? "interaction-one" : "interactions", () =>
      collectDouyinTargetInteractions({
        setId: activeSetId,
        videoIds: videoId ? [videoId] : [],
        adaptiveByRatio: true,
        maxComments: 160,
        minComments: 30,
        includeReplies: true,
        repliesPerComment: 3,
      }),
    );
    if (result) {
      setMessage(`已补全 ${result.count} 条视频互动数据${result.errors?.length ? `，失败 ${result.errors.length} 条` : ""}`);
      if (result.errors?.length) {
        setError(`部分互动数据补全失败：${result.errors.slice(0, 3).map((item) => item.error).join("；")}`);
      }
      await loadSets(activeSetId);
    }
  }

  async function handleDeleteVideoAnalysis(video) {
    if (!video?.id) return;
    if ((video.analysis_status || "") === "running") {
      setError("该视频拆解仍在运行中，请先在 AI 视频队列中取消或等待结束后再删除。");
      return;
    }
    const title = video.desc || video.aweme_id || video.id;
    if (
      !window.confirm(
        `确认删除「${title}」的拆解记录吗？\n\n只会删除拆解任务、队列记录和拆解结果，不会删除视频指标、评论、回复和互动洞察。删除后可以重新补全互动数据并再次加入 AI 拆解。`,
      )
    ) {
      return;
    }
    const result = await run("delete-analysis", () => deleteDouyinTargetVideoAnalysis(video.id));
    if (result) {
      setMessage("已删除该视频的拆解记录，评论和指标已保留，可重新加入 AI 拆解。");
      await loadSets(activeSetId);
    }
  }

  async function handleEnqueue() {
    if (!activeSetId) {
      setError("请先选择一个对标集合。");
      return;
    }
    const result = await run("enqueue", () =>
      enqueueDouyinTargetAnalysis({
        setId: activeSetId,
        collectComments: autoCollectInteractions,
      }),
    );
    if (result) {
      setMessage(`已加入 ${result.count} 个拆解任务，跳过 ${result.skipped?.length || 0} 个已有任务`);
      await loadSets(activeSetId);
    }
  }

  async function handleSync() {
    if (!activeSetId) return;
    const result = await run("sync", () => syncDouyinTargetAnalysis(activeSetId));
    if (result) {
      setMessage(`已同步 ${result.count} 个对标拆解任务`);
      await loadSets(activeSetId);
    }
  }

  return (
    <section className="douyin-target-layout">
      <section className="panel douyin-target-search">
        <div className="panel-header">
          <div>
            <h2>抖音对标</h2>
            <p>用关键词发现账号，筛选后沉淀进待对标库，再批量选择视频进入 AI 拆解任务池。</p>
          </div>
          <Badge status={busy ? "running" : "ready"}>{busy ? "执行中" : "TikHub"}</Badge>
        </div>

        <form className="target-search-form" onSubmit={handleSearch}>
          <label className="wide-field">
            关键词
            <input value={keyword} onChange={handleKeywordChange} placeholder="可爱、宠物、穿搭..." required />
          </label>
          <label>
            目标账号数
            <input
              type="number"
              min="1"
              max="500"
              value={filters.targetAccountCount}
              onChange={(event) => setFilters((current) => ({ ...current, targetAccountCount: event.target.value }))}
            />
          </label>
          <label>
            粉丝阈值
            <select value={filters.followerThreshold} onChange={(event) => setFilters((current) => ({ ...current, followerThreshold: event.target.value }))}>
              {FollowerThresholds.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            粉丝范围
            <select
              value={filters.followerRange}
              onChange={(event) => setFilters((current) => ({ ...current, followerRange: event.target.value }))}
              disabled={filters.followerThreshold === "below_1w"}
            >
              {FollowerRanges.map(([value, label]) => (
                <option key={value || "all"} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            最小点赞
            <input type="number" value={filters.minLikes} onChange={(event) => setFilters((current) => ({ ...current, minLikes: event.target.value }))} />
          </label>
          <label>
            视频数
            <select value={filters.videoRange} onChange={(event) => setFilters((current) => ({ ...current, videoRange: event.target.value }))}>
              {VideoRanges.map(([value, label]) => (
                <option key={value || "all"} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            更新天数
            <select value={filters.updateRange} onChange={(event) => setFilters((current) => ({ ...current, updateRange: event.target.value }))}>
              {UpdateRanges.map(([value, label]) => (
                <option key={value || "all"} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            排序
            <select value={filters.sortBy} onChange={(event) => setFilters((current) => ({ ...current, sortBy: event.target.value }))}>
              <option value="relevance">相关性</option>
              <option value="followers">粉丝量</option>
              <option value="likes">总点赞</option>
              <option value="videos">视频数</option>
              <option value="recent">最近更新</option>
            </select>
          </label>
          <button className="primary-button" type="submit" disabled={busy === "search"}>
            {busy === "search" ? "搜索中..." : "搜索账号"}
          </button>
        </form>

        {busyText && (
          <div className="target-busy-banner">
            <span className="target-spinner" aria-hidden="true" />
            <span>{busyText}</span>
          </div>
        )}
        {message && <div className="running-note">{message}</div>}
        {error && <div className="error-box">{error}</div>}

        <section className="target-result-toolbar target-set-ops">
          <div className="target-set-ops-heading">
            <div>
              <span className="target-set-ops-kicker">Collection Ops</span>
              <h3>合集操作</h3>
            </div>
            <Badge status={activeSetId ? "ready" : "draft"}>
              {activeSetId ? "编辑当前合集" : "新建合集"}
            </Badge>
          </div>
          <div className="target-set-controls">
            <label>
              合集名称
              <input
                value={visibleSetName}
                onChange={(event) => setSetForm((current) => ({ ...current, name: event.target.value }))}
                placeholder={defaultSetName(keyword)}
              />
            </label>
            <label>
              关键词
              <input
                value={visibleSetKeyword}
                onChange={(event) => setSetForm((current) => ({ ...current, keyword: event.target.value }))}
                placeholder={cleanKeyword(keyword) || "用于沉淀这组对标的搜索词"}
              />
            </label>
            <label className="wide-field">
              备注
              <input
                value={setForm.note}
                onChange={(event) => setSetForm((current) => ({ ...current, note: event.target.value }))}
                placeholder="可写赛道、目标、复盘备注"
              />
            </label>
            <label>
              状态
              <select value={setForm.status} onChange={(event) => setSetForm((current) => ({ ...current, status: event.target.value }))}>
                <option value="draft">草稿</option>
                <option value="active">启用</option>
                <option value="archived">归档</option>
              </select>
            </label>
            <label>
              选择合集
              <select
                value={activeSetId}
                onChange={(event) => selectSet(event.target.value)}
              >
                <option value="">新建合集</option>
                {sets.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <button className="text-button" type="button" onClick={handleCreateSet} disabled={busy === "create-set"}>
              新建合集
            </button>
            <button className="text-button" type="button" onClick={handleUpdateSet} disabled={!activeSetId || busy === "update-set"}>
              保存修改
            </button>
            <button className="text-button" type="button" onClick={() => handleDeleteSet()} disabled={!activeSetId || busy === "delete-set"}>
              删除合集
            </button>
            <button className="text-button" type="button" onClick={handleSaveUsers} disabled={!selectedCount || busy === "save"}>
              保存选中账号到合集（{selectedCount}）
            </button>
          </div>
        </section>

        <section className="douyin-target-library target-library-inline">
        <div className="panel-header">
          <div>
            <h2>待对标库</h2>
            <p>选择集合后，可以采集账号视频、创建拆解任务并同步结果。</p>
          </div>
          <Badge>{activeUsers.length} 个账号 / {activeVideos.length} 条视频</Badge>
        </div>

        <div className="target-library-grid">
          <aside className="target-set-list">
            {sets.map((item) => (
              <div className={activeSetId === item.id ? "target-set-item active" : "target-set-item"} key={item.id}>
                <button className="target-set-select" type="button" onClick={() => selectSet(item.id)}>
                  <strong>{item.name}</strong>
                  <span>{item.user_count || 0} 账号 / {item.video_count || 0} 视频</span>
                </button>
                <button
                  className="target-set-delete"
                  type="button"
                  onClick={() => handleDeleteSet(item.id, item.name)}
                  disabled={busy === "delete-set"}
                  aria-label={`删除合集 ${item.name}`}
                >
                  删除
                </button>
              </div>
            ))}
            {!sets.length && <div className="empty-result">保存账号后会生成对标集合。</div>}
          </aside>

          <div className="target-workbench">
            <div className="target-strategy">
              <label>
                视频策略
                <select value={strategy.mode} onChange={(event) => setStrategy((current) => ({ ...current, mode: event.target.value }))}>
                  <option value="top">最高数据</option>
                  <option value="pinned">置顶优先</option>
                  <option value="recent">最近发布</option>
                  <option value="mixed">混合策略</option>
                </select>
              </label>
              <label>
                每账号视频数
                <input type="number" min="1" max="20" value={strategy.perUserLimit} onChange={(event) => setStrategy((current) => ({ ...current, perUserLimit: event.target.value }))} />
              </label>
              <label>
                候选视频池
                <input type="number" min="1" max="50" value={strategy.fetchCount} onChange={(event) => setStrategy((current) => ({ ...current, fetchCount: event.target.value }))} />
              </label>
              <div className="field-hint target-strategy-hint">每个账号先拉取多少条作品作为候选，再从候选里按策略选出上方数量的视频。</div>
              <button className="text-button" type="button" onClick={handleCollectVideos} disabled={!activeSetId || busy === "collect"}>
                {busy === "collect" ? "采集中..." : "采集并选择视频"}
              </button>
              <button className="text-button" type="button" onClick={() => handleCollectInteractions()} disabled={!activeVideos.length || busy === "interactions"}>
                {busy === "interactions" ? "补全中..." : "补全互动数据"}
              </button>
              <label className="target-auto-enrich-toggle">
                <input
                  type="checkbox"
                  checked={autoCollectInteractions}
                  onChange={(event) => setAutoCollectInteractions(event.target.checked)}
                />
                拆解前自动补全互动数据
              </label>
              <button className="primary-button" type="button" onClick={handleEnqueue} disabled={!activeVideos.length || busy === "enqueue"}>
                加入 AI 拆解
              </button>
              <button className="text-button" type="button" onClick={handleSync} disabled={!activeSetId || busy === "sync"}>
                同步结果
              </button>
            </div>

            <div className="target-mini-columns">
              <div className="target-mini-panel">
                <div className="target-mini-heading">
                  <h3>账号</h3>
                  <span>{activeUsers.length} 个</span>
                </div>
                <div className="target-mini-scroll">
                  {activeUsers.map((item) => (
                    <div className="target-mini-row" key={item.id}>
                      <strong>{item.nickname || item.unique_id}</strong>
                      <span>{compactNumber(item.follower_count)} 粉丝</span>
                    </div>
                  ))}
                  {!activeUsers.length && <div className="empty-result">当前集合还没有账号。</div>}
                </div>
              </div>
              <div className="target-mini-panel">
                <div className="target-mini-heading">
                  <h3>视频与拆解状态</h3>
                  <span>{activeVideos.length} 条</span>
                </div>
                <div className="target-mini-scroll">
                  {activeVideos.map((item) => (
                    <div className="target-video-row" key={item.id}>
                      <div>
                        <strong>{item.desc || item.aweme_id}</strong>
                        <span>点赞 {optionalCompactNumber(item.digg_count)} / 日期 {optionalDate(item.create_time)}</span>
                        <span>{commentStatusLabel(item)}</span>
                      </div>
                      <div className="target-video-actions">
                        <Badge status={commentStatusTone(item)}>
                          {item.comment_snapshot_status === "done" ? "互动已补全" : "互动待补全"}
                        </Badge>
                        <Badge status={analysisStatusTone(item.analysis_status)}>
                          {analysisStatusLabel(item.analysis_status)}
                        </Badge>
                        <button className="text-button compact-target-action" type="button" onClick={() => handleCollectInteractions(item.id)} disabled={busy === "interaction-one" || busy === "interactions"}>
                          补全
                        </button>
                        {hasAnalysisRecord(item) && (
                          <button
                            className="text-button compact-target-action danger-target-action"
                            type="button"
                            onClick={() => handleDeleteVideoAnalysis(item)}
                            disabled={busy === "delete-analysis" || item.analysis_status === "running"}
                          >
                            删除拆解
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                  {!activeVideos.length && <div className="empty-result">采集视频后会出现在这里。</div>}
                </div>
              </div>
            </div>
          </div>
        </div>
        </section>

        <div className="target-user-table">
          {users.map((item) => {
            const id = userId(item);
            const checked = selectedUsers.has(id);
            return (
              <article className="target-user-row" key={id || item.nickname}>
                <label className="target-check">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) => {
                      setSelectedUsers((current) => {
                        const next = new Set(current);
                        if (event.target.checked) next.add(id);
                        else next.delete(id);
                        return next;
                      });
                    }}
                  />
                </label>
                <img src={item.avatar} alt="" />
                <div className="target-user-main">
                  <strong>{item.nickname || "未命名账号"}</strong>
                  <p>{item.unique_id || item.uid || item.sec_uid}</p>
                  <span>{item.signature || "暂无简介"}</span>
                </div>
                <div className="target-user-stats">
                  <span>粉丝 {compactNumber(item.follower_count)}</span>
                  <span>点赞 {compactNumber(item.like_count)}</span>
                  <span>视频 {compactNumber(item.aweme_count)}</span>
                </div>
                <div className="target-user-flags">
                  <Badge status={item.verified ? "ready" : "draft"}>{item.verified ? "认证" : "普通"}</Badge>
                  <span>{formatDate(item.last_post_at || item.recent_update_at)}</span>
                </div>
              </article>
            );
          })}
          {!users.length && <div className="empty-result">输入关键词后开始搜索候选账号。</div>}
        </div>
        {searchResult && (
          <div className="target-search-pagination">
            <span>已展示 {users.length} 个候选账号{searchPage ? ` / 第 ${searchPage} 页` : ""}</span>
            <button className="text-button" type="button" onClick={handleLoadMoreSearch} disabled={!searchHasMore || busy === "search-more"}>
              {searchHasMore ? "下一页，展示更多" : "没有更多账号"}
            </button>
          </div>
        )}
      </section>
    </section>
  );
}
