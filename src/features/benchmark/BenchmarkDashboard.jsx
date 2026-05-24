import React, { useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, FileDown, RefreshCw, Search, Sparkles } from "lucide-react";
import {
  analyzeBenchmarkAuthorProfile,
  fetchBenchmarkAuthor,
  fetchBenchmarkAuthors,
  fetchBenchmarkCommentInsights,
  fetchBenchmarkMetricConfig,
  fetchBenchmarkOverview,
  fetchBenchmarkPattern,
  fetchBenchmarkPatterns,
  fetchBenchmarkVideo,
  fetchBenchmarkVideos,
  reindexBenchmark,
  updateBenchmarkPattern,
  updateBenchmarkMetricConfig,
} from "../../services/api";

const contentTypes = ["玄学塔罗", "全部类型", "动漫解说", "原创 Vlog", "好物种草", "知识教程"];
const rankTabs = [
  ["overall", "综合互动"],
  ["small_account", "小号效率"],
  ["collect", "收藏价值"],
  ["comment", "评论驱动"],
];
const authorSortOptions = [
  ["benchmark", "对标分"],
  ["collect", "收藏倾向"],
  ["comment", "评论驱动"],
  ["small_account", "小号效率"],
  ["imitation", "复刻分"],
];

function compactNumber(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  if (number >= 100000000) return `${(number / 100000000).toFixed(1)}亿`;
  if (number >= 10000) return `${(number / 10000).toFixed(1)}万`;
  return String(Math.round(number));
}

function percent(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0%";
  return `${Math.round(number * 100)}%`;
}

function formatDateTime(timestamp) {
  const value = Number(timestamp || 0);
  if (!value) return "暂无";
  return new Date(value * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function normalizeWeights(weights = {}) {
  return {
    digg: Number(weights.digg ?? 1),
    comment: Number(weights.comment ?? 3),
    collect: Number(weights.collect ?? 4),
    share: Number(weights.share ?? 5),
  };
}

function MetricCard({ label, value }) {
  return (
    <div className="benchmark-card benchmark-metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ProgressBar({ value }) {
  const width = Math.max(4, Math.min(100, Number(value || 0)));
  return (
    <div className="benchmark-bar">
      <span style={{ width: `${width}%` }} />
    </div>
  );
}

function profileAnalysis(author = {}, overrides = {}) {
  const analysis = overrides[author.author_id] || author.profile_analysis || {};
  return {
    persona: analysis.persona_type || "待分析账号",
    summary: analysis.summary || "暂无简介分析，可在索引更新后生成。",
    commerce: analysis.commerce_signals || [],
    trust: analysis.trust_signals || [],
    risk: analysis.risk_signals || [],
    focus: analysis.learning_focus || author.learning_points || [],
  };
}

function PatternValueMatrix({ patterns = [], onSelectPattern }) {
  const chartRef = useRef(null);

  useEffect(() => {
    let active = true;
    let chart = null;
    const resize = () => chart?.resize();
    Promise.all([
      import("echarts/core"),
      import("echarts/charts"),
      import("echarts/components"),
      import("echarts/renderers"),
    ]).then(([core, charts, components, renderers]) => {
      if (!active || !chartRef.current) return;
      core.use([charts.ScatterChart, components.GridComponent, components.TooltipComponent, renderers.CanvasRenderer]);
      chart = core.init(chartRef.current);
      const items = patterns.slice(0, 28);
      const highlightedNames = new Set(
        [...items]
          .sort((left, right) => {
            const rightValue =
              Number(right.video_count || 0) * 10 +
              (Number(right.avg_collect_tendency || 0) + Number(right.avg_comment_tendency || 0)) * 100;
            const leftValue =
              Number(left.video_count || 0) * 10 +
              (Number(left.avg_collect_tendency || 0) + Number(left.avg_comment_tendency || 0)) * 100;
            return rightValue - leftValue;
          })
          .slice(0, 8)
          .map((pattern) => pattern.name),
      );
      chart.setOption({
        grid: { left: 48, right: 22, top: 24, bottom: 42 },
        tooltip: {
          trigger: "item",
          formatter: (params) => {
            const [imitation, value, count, name] = params.value;
            return `${name}<br/>复刻分：${imitation}<br/>收藏+评论倾向：${value}%<br/>视频数：${count}`;
          },
        },
        xAxis: {
          name: "复刻分",
          min: 60,
          max: 100,
          axisLine: { lineStyle: { color: "#94a3b8" } },
          splitLine: { lineStyle: { color: "#e2e8f0" } },
        },
        yAxis: {
          name: "互动倾向",
          axisLabel: { formatter: "{value}%" },
          axisLine: { lineStyle: { color: "#94a3b8" } },
          splitLine: { lineStyle: { color: "#e2e8f0" } },
        },
        series: [
          {
            type: "scatter",
            symbolSize: (value) => Math.max(14, Math.min(44, Number(value[2] || 1) * 1.5)),
            itemStyle: { color: "#2563eb", opacity: 0.78 },
            label: {
              show: false,
              formatter: (params) => (params.value[4] ? String(params.value[3] || "").slice(0, 6) : ""),
              position: "top",
              color: "#1f2a44",
              fontSize: 11,
            },
            emphasis: {
              label: {
                show: true,
                formatter: (params) => String(params.value[3] || "").slice(0, 10),
              },
            },
            data: items.map((pattern) => [
              Math.round(Number(pattern.avg_imitation_value || 0)),
              Math.round((Number(pattern.avg_collect_tendency || 0) + Number(pattern.avg_comment_tendency || 0)) * 100),
              Number(pattern.video_count || 0),
              pattern.name || "未命名模式",
              highlightedNames.has(pattern.name),
              pattern.pattern_id,
            ]),
          },
        ],
      });
      chart.on("click", (params) => {
        const patternId = params?.value?.[5];
        const pattern = items.find((item) => item.pattern_id === patternId);
        if (pattern) onSelectPattern?.(pattern);
      });
      window.addEventListener("resize", resize);
    });
    return () => {
      active = false;
      window.removeEventListener("resize", resize);
      chart?.dispose();
    };
  }, [patterns]);

  return <div className="benchmark-chart" ref={chartRef} role="img" aria-label="内容模式价值矩阵" />;
}

function reportLine(label, value) {
  return `- ${label}：${value ?? "暂无"}`;
}

function buildBenchmarkReport({ genre, overview, videos, authors, patterns, compareAuthors, commentInsights, profileOverrides }) {
  const lines = [
    `# ${genre || "全部类型"}对标分析报告`,
    "",
    `生成时间：${new Date().toLocaleString("zh-CN")}`,
    "",
    "## 数据范围",
    reportLine("拆解任务", compactNumber(overview?.analysis_task_count)),
    reportLine("去重视频", compactNumber(overview?.unique_video_count)),
    reportLine("博主数", compactNumber(overview?.author_count)),
    reportLine("评论样本视频", compactNumber(overview?.comment_quality_video_count)),
    "",
    "## 当前优先对标博主",
    ...(compareAuthors.length ? compareAuthors : authors.items.slice(0, 5)).map((author, index) => {
      const analysis = profileAnalysis(author, profileOverrides);
      return `${index + 1}. ${author.nickname || "未知博主"}：对标分 ${compactNumber(author.benchmark_score)}，${author.positioning || analysis.persona}`;
    }),
    "",
    "## 内容排行榜样本",
    ...videos.items.slice(0, 8).map((video, index) => `${index + 1}. ${video.desc || "未命名视频"}｜${video.author_name || "未知博主"}`),
    "",
    "## 内容模式",
    ...patterns.items.slice(0, 8).map((pattern, index) => {
      const value = Math.round((Number(pattern.avg_collect_tendency || 0) + Number(pattern.avg_comment_tendency || 0)) * 100);
      return `${index + 1}. ${pattern.name}：${compactNumber(pattern.video_count)} 条，复刻分 ${compactNumber(pattern.avg_imitation_value)}，互动倾向 ${value}%`;
    }),
    "",
    "## 评论洞察",
    reportLine("评论覆盖", `${compactNumber(commentInsights?.ready_video_count)} / ${compactNumber(commentInsights?.video_count)} 个视频`),
    reportLine("平均评论质量", compactNumber(commentInsights?.avg_quality_score)),
    reportLine("提问占比", percent(commentInsights?.question_ratio)),
    reportLine("长评占比", percent(commentInsights?.long_comment_ratio)),
    ...(commentInsights?.suggestions || []).map((item) => `- ${item}`),
  ];
  return `${lines.join("\n")}\n`;
}

function downloadTextFile(filename, text) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function extractTaskId(detail) {
  return detail?.task_id || detail?.video?.task_id || detail?.job_id || detail?.video?.job_id || "";
}

function authorSortMetric(author, sort) {
  const metricMap = {
    benchmark: ["对标分", compactNumber(author.benchmark_score)],
    collect: ["收藏倾向", percent(author.avg_collect_tendency)],
    comment: ["评论倾向", percent(author.avg_comment_tendency)],
    small_account: ["小号效率", compactNumber(author.avg_small_account_efficiency)],
    imitation: ["复刻分", compactNumber(author.avg_imitation_value)],
  };
  return metricMap[sort] || metricMap.benchmark;
}

function authorMetricRows(authorDetail) {
  const metrics = authorDetail?.metrics || authorDetail?.author || {};
  return [
    ["样本任务", compactNumber(metrics.sample_count)],
    ["去重视频", compactNumber(metrics.video_count)],
    ["粉丝数", compactNumber(metrics.follower_count)],
    ["收藏倾向", percent(metrics.avg_collect_tendency)],
    ["评论倾向", percent(metrics.avg_comment_tendency)],
    ["对标分", compactNumber(metrics.benchmark_score)],
  ];
}

export function BenchmarkDashboard({ onOpenTask }) {
  const [genre, setGenre] = useState("玄学塔罗");
  const [rankType, setRankType] = useState("overall");
  const [authorFilter, setAuthorFilter] = useState(null);
  const [videoLimit, setVideoLimit] = useState(20);
  const [authorQuery, setAuthorQuery] = useState("");
  const [authorSort, setAuthorSort] = useState("benchmark");
  const [authorLimit, setAuthorLimit] = useState(12);
  const [overview, setOverview] = useState(null);
  const [videos, setVideos] = useState({ items: [], total: 0 });
  const [authors, setAuthors] = useState({ items: [], total: 0 });
  const [patterns, setPatterns] = useState({ items: [], total: 0 });
  const [commentInsights, setCommentInsights] = useState(null);
  const [metricConfig, setMetricConfig] = useState(null);
  const [metricDraft, setMetricDraft] = useState(normalizeWeights());
  const [selectedVideo, setSelectedVideo] = useState(null);
  const [selectedAuthor, setSelectedAuthor] = useState(null);
  const [selectedPattern, setSelectedPattern] = useState(null);
  const [patternFilter, setPatternFilter] = useState(null);
  const [compareAuthors, setCompareAuthors] = useState([]);
  const [profileOverrides, setProfileOverrides] = useState({});
  const [analyzingAuthors, setAnalyzingAuthors] = useState({});
  const [patternDraft, setPatternDraft] = useState({ name: "", description: "", manual_notes: "" });
  const [status, setStatus] = useState({ loading: false, error: "" });
  const [reindexing, setReindexing] = useState(false);
  const [savingMetrics, setSavingMetrics] = useState(false);
  const [savingPattern, setSavingPattern] = useState(false);

  const queryGenre = genre === "全部类型" ? "" : genre;

  async function loadDashboard() {
    setStatus({ loading: true, error: "" });
    try {
      const [nextOverview, nextVideos, nextAuthors, nextPatterns, nextMetricConfig, nextCommentInsights] = await Promise.all([
        fetchBenchmarkOverview({ genre: queryGenre }),
        fetchBenchmarkVideos({
          genre: queryGenre,
          rankType,
          authorId: authorFilter?.author_id,
          patternId: patternFilter?.pattern_id,
          limit: videoLimit,
        }),
        fetchBenchmarkAuthors({ genre: queryGenre, sort: authorSort, query: authorQuery.trim(), limit: authorLimit }),
        fetchBenchmarkPatterns({ genre: queryGenre, limit: 80 }),
        fetchBenchmarkMetricConfig(),
        fetchBenchmarkCommentInsights({
          genre: queryGenre,
          authorId: authorFilter?.author_id,
          patternId: patternFilter?.pattern_id,
        }),
      ]);
      setOverview(nextOverview);
      setVideos(nextVideos);
      setAuthors(nextAuthors);
      setPatterns(nextPatterns);
      setMetricConfig(nextMetricConfig);
      setCommentInsights(nextCommentInsights);
      setMetricDraft(normalizeWeights(nextMetricConfig?.config?.public_engagement_weights));
      setStatus({ loading: false, error: "" });
    } catch (err) {
      setStatus({ loading: false, error: err.message || String(err) });
    }
  }

  useEffect(() => {
    loadDashboard();
  }, [queryGenre, rankType, authorFilter?.author_id, patternFilter?.pattern_id, videoLimit, authorSort, authorQuery, authorLimit]);

  useEffect(() => {
    setAuthorFilter(null);
    setPatternFilter(null);
    setVideoLimit(20);
    setAuthorLimit(12);
    setCompareAuthors([]);
  }, [queryGenre, rankType]);

  useEffect(() => {
    setAuthorLimit(12);
  }, [authorQuery, authorSort]);

  async function openVideo(videoId) {
    try {
      const detail = await fetchBenchmarkVideo(videoId);
      setSelectedVideo(detail);
      setSelectedAuthor(null);
      setSelectedPattern(null);
    } catch (err) {
      setStatus({ loading: false, error: err.message || String(err) });
    }
  }

  async function openAuthor(author) {
    try {
      const detail = await fetchBenchmarkAuthor(author.author_id);
      setSelectedAuthor(detail);
      setSelectedVideo(null);
      setSelectedPattern(null);
    } catch (err) {
      setStatus({ loading: false, error: err.message || String(err) });
    }
  }

  async function openPattern(pattern) {
    try {
      const detail = await fetchBenchmarkPattern(pattern.pattern_id, { genre: queryGenre });
      setSelectedPattern(detail);
      setSelectedVideo(null);
      setSelectedAuthor(null);
      setPatternDraft({
        name: detail.pattern?.name || "",
        description: detail.pattern?.description || "",
        manual_notes: detail.pattern?.manual_notes || "",
      });
    } catch (err) {
      setStatus({ loading: false, error: err.message || String(err) });
    }
  }

  function focusAuthorVideos(author) {
    setAuthorFilter(author);
    setVideoLimit(20);
    setSelectedAuthor(null);
  }

  async function focusPatternVideos(pattern, options = {}) {
    setPatternFilter(pattern);
    setVideoLimit(20);
    if (options.openDetail !== false) {
      await openPattern(pattern);
    }
  }

  function toggleCompareAuthor(author) {
    setCompareAuthors((current) => {
      if (current.some((item) => item.author_id === author.author_id)) {
        return current.filter((item) => item.author_id !== author.author_id);
      }
      return [...current.slice(-3), author];
    });
  }

  function clearCompareAuthors() {
    setCompareAuthors([]);
  }

  async function handleAnalyzeAuthor(author) {
    if (!author?.author_id) return;
    setAnalyzingAuthors((current) => ({ ...current, [author.author_id]: true }));
    try {
      const response = await analyzeBenchmarkAuthorProfile(author.author_id);
      setProfileOverrides((current) => ({ ...current, [author.author_id]: response.analysis }));
    } catch (err) {
      setStatus({ loading: false, error: err.message || String(err) });
    } finally {
      setAnalyzingAuthors((current) => ({ ...current, [author.author_id]: false }));
    }
  }

  function handleExportReport() {
    const report = buildBenchmarkReport({
      genre,
      overview,
      videos,
      authors,
      patterns,
      compareAuthors,
      commentInsights,
      profileOverrides,
    });
    const date = new Date().toISOString().slice(0, 10);
    downloadTextFile(`benchmark-report-${date}.md`, report);
  }

  async function handleReindex() {
    setReindexing(true);
    try {
      await reindexBenchmark("incremental");
      await loadDashboard();
    } catch (err) {
      setStatus({ loading: false, error: err.message || String(err) });
    } finally {
      setReindexing(false);
    }
  }

  async function handleSaveMetricConfig() {
    setSavingMetrics(true);
    try {
      const response = await updateBenchmarkMetricConfig(metricDraft, { reindex: true });
      setMetricConfig(response);
      await loadDashboard();
    } catch (err) {
      setStatus({ loading: false, error: err.message || String(err) });
    } finally {
      setSavingMetrics(false);
    }
  }

  function updateMetricDraft(key, value) {
    setMetricDraft((current) => ({ ...current, [key]: value }));
  }

  async function handleSavePattern() {
    const patternId = selectedPattern?.pattern?.pattern_id;
    if (!patternId) return;
    setSavingPattern(true);
    try {
      const detail = await updateBenchmarkPattern(patternId, patternDraft);
      setSelectedPattern(detail);
      await loadDashboard();
    } catch (err) {
      setStatus({ loading: false, error: err.message || String(err) });
    } finally {
      setSavingPattern(false);
    }
  }

  const metricCards = useMemo(
    () => [
      ["拆解任务", compactNumber(overview?.analysis_task_count)],
      ["去重视频", compactNumber(overview?.unique_video_count)],
      ["博主数", compactNumber(overview?.author_count)],
      ["分段拆解", compactNumber(overview?.segment_count)],
      ["平均复刻分", compactNumber(overview?.avg_imitation_value)],
      ["公开信号", compactNumber(overview?.public_signal_video_count)],
      ["评论样本", compactNumber(overview?.comment_quality_video_count)],
    ],
    [overview],
  );

  const indexMeta = overview?.index_meta || metricConfig?.index_meta || {};
  const weightFields = metricConfig?.config?.weight_fields || [];
  const unavailableMetrics = metricConfig?.config?.unavailable_competitor_metrics || [];
  const metricGroups = metricConfig?.config?.metric_groups || [];
  const matrixPatterns = useMemo(
    () => (patterns.items || []).filter((pattern) => Number(pattern.video_count || 0) > 0),
    [patterns.items],
  );
  const compareInsights = useMemo(() => {
    if (!compareAuthors.length) return [];
    const bestCollect = [...compareAuthors].sort((a, b) => Number(b.avg_collect_tendency || 0) - Number(a.avg_collect_tendency || 0))[0];
    const bestSmall = [...compareAuthors].sort((a, b) => Number(b.avg_small_account_efficiency || 0) - Number(a.avg_small_account_efficiency || 0))[0];
    const strongestRisk = compareAuthors.find((author) => profileAnalysis(author, profileOverrides).risk.length);
    return [
      bestCollect ? `收藏结构优先看：${bestCollect.nickname || "未知博主"}` : "",
      bestSmall ? `小号效率优先看：${bestSmall.nickname || "未知博主"}` : "",
      strongestRisk ? `${strongestRisk.nickname || "未知博主"} 的简介存在导流/敏感词，复刻时要改写表达。` : "已选账号暂未发现明显简介风险词。",
    ].filter(Boolean);
  }, [compareAuthors, profileOverrides]);

  return (
    <section className="benchmark-dashboard">
      <div className="benchmark-head">
        <div>
          <h2>短视频对标分析工作台</h2>
          <p>从 AI 拆解结果中聚合对标视频、博主和可复用内容模式。</p>
        </div>
        <div className="benchmark-head-actions">
          <button className="secondary-action-button" type="button" onClick={handleExportReport}>
            <FileDown size={16} />
            导出报告
          </button>
          <button className="secondary-action-button" type="button" onClick={handleReindex} disabled={reindexing}>
            <RefreshCw size={16} className={reindexing ? "spin" : ""} />
            {reindexing ? "更新中" : "更新索引"}
          </button>
        </div>
      </div>

      <div className="benchmark-filter-row">
        {contentTypes.map((item) => (
          <button className={`benchmark-chip ${genre === item ? "active" : ""}`} key={item} type="button" onClick={() => setGenre(item)}>
            {item}
          </button>
        ))}
      </div>

      <div className="benchmark-index-strip">
        <span>最近索引：{formatDateTime(indexMeta.indexed_at)}</span>
        <span>视频 {compactNumber(indexMeta.unique_videos)}</span>
        <span>博主 {compactNumber(indexMeta.authors)}</span>
        <span>任务 {compactNumber(indexMeta.processed_jobs)}</span>
        <span>权重版本 v{metricConfig?.config?.version || indexMeta.metric_config_version || 1}</span>
      </div>

      {status.error && <div className="form-error">对标工作台加载失败：{status.error}</div>}

      <div className="benchmark-metric-grid">
        {metricCards.map(([label, value]) => (
          <MetricCard key={label} label={label} value={value} />
        ))}
      </div>

      <div className="benchmark-main-grid">
        <section className="benchmark-card benchmark-ranking">
          <div className="benchmark-card-head">
            <h3>内容排行榜</h3>
            <div className="benchmark-tabs">
              {rankTabs.map(([id, label]) => (
                <button className={rankType === id ? "active" : ""} key={id} type="button" onClick={() => setRankType(id)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          {(authorFilter || patternFilter) && (
            <div className="benchmark-active-filter">
              <div className="benchmark-filter-tags">
                {authorFilter && <span>当前博主：{authorFilter.nickname || "未知博主"}</span>}
                {patternFilter && <span>当前模式：{patternFilter.name || "未知模式"}</span>}
              </div>
              <div className="benchmark-row-actions">
                {authorFilter && (
                  <button className="text-button compact" type="button" onClick={() => setAuthorFilter(null)}>
                    清除博主
                  </button>
                )}
                {patternFilter && (
                  <button className="text-button compact" type="button" onClick={() => setPatternFilter(null)}>
                    清除模式
                  </button>
                )}
              </div>
            </div>
          )}
          <div className="benchmark-ranking-scroll">
          <table className="benchmark-table">
            <thead>
              <tr>
                <th>视频</th>
                <th>博主</th>
                <th>互动倾向</th>
                <th>动作</th>
              </tr>
            </thead>
            <tbody>
              {videos.items.map((video) => (
                <tr key={`${video.video_id}-${video.job_id}`}>
                  <td>{video.desc || "未命名视频"}</td>
                  <td>{video.author_name || "未知博主"}</td>
                  <td>
                    <ProgressBar value={video.overall_score || video.imitation_value || 60} />
                  </td>
                  <td>
                    <button className="text-button compact" type="button" onClick={() => openVideo(video.video_id)}>
                      看证据
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {videos.items.length < videos.total && (
            <button className="secondary-action-button benchmark-load-more" type="button" onClick={() => setVideoLimit((current) => current + 20)}>
              加载更多 {Math.min(20, videos.total - videos.items.length)} 条
            </button>
          )}
          </div>
          <p className="benchmark-note">点击视频进入轻详情，再跳到任务中心完整拆解。</p>
        </section>

        <section className="benchmark-card benchmark-author-panel">
          <div className="benchmark-card-head">
            <div>
              <h3>博主对标</h3>
              <p className="benchmark-note">按指标排序后选择博主，可直接筛出他的全部样本视频。</p>
            </div>
            <span className="benchmark-total">共 {compactNumber(authors.total)} 个</span>
          </div>
          <div className="benchmark-author-toolbar">
            <label className="benchmark-search-box">
              <Search size={15} />
              <input
                type="search"
                placeholder="搜索博主名称"
                value={authorQuery}
                onChange={(event) => setAuthorQuery(event.target.value)}
              />
            </label>
            <label className="benchmark-sort-select">
              <span>排序</span>
              <select value={authorSort} onChange={(event) => setAuthorSort(event.target.value)}>
                {authorSortOptions.map(([id, label]) => (
                  <option value={id} key={id}>{label}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="benchmark-author-scroll">
          <div className="benchmark-author-list">
            {authors.items.map((author) => {
              const [metricLabel, metricValue] = authorSortMetric(author, authorSort);
              return (
              <article className="benchmark-author-row" key={author.author_id}>
                <div className="benchmark-avatar">{(author.nickname || "博").slice(0, 1)}</div>
                <div className="benchmark-author-main">
                  <strong>{author.nickname || "未知博主"}</strong>
                  <span>{author.positioning || "暂无定位"}</span>
                </div>
                <div className="benchmark-author-score">
                  <b>{metricValue}</b>
                  <span>{metricLabel}</span>
                </div>
                <div className="benchmark-row-actions">
                  <button
                    className={`text-button compact ${compareAuthors.some((item) => item.author_id === author.author_id) ? "active" : ""}`}
                    type="button"
                    onClick={() => toggleCompareAuthor(author)}
                  >
                    {compareAuthors.some((item) => item.author_id === author.author_id) ? "已对比" : "对比"}
                  </button>
                  <button className="text-button compact" type="button" onClick={() => openAuthor(author)}>
                    详情
                  </button>
                  <button className="text-button compact" type="button" onClick={() => focusAuthorVideos(author)}>
                    看视频
                  </button>
                </div>
              </article>
              );
            })}
            {!authors.items.length && <p className="benchmark-note">没有找到匹配的博主。</p>}
          </div>
          {authors.items.length < authors.total && (
            <button className="secondary-action-button benchmark-load-more" type="button" onClick={() => setAuthorLimit((current) => current + 12)}>
              加载更多博主 {Math.min(12, authors.total - authors.items.length)} 个
            </button>
          )}
          </div>
        </section>
      </div>

      <div className="benchmark-decision-grid">
        <section className="benchmark-card benchmark-compare-card">
          <div className="benchmark-card-head">
            <div>
              <h3>博主多选对比</h3>
              <p className="benchmark-note">从右侧博主列表加入 2-4 个账号，横向比较是否值得对标。</p>
            </div>
            {compareAuthors.length > 0 && (
              <button className="text-button compact" type="button" onClick={clearCompareAuthors}>
                清空
              </button>
            )}
          </div>
          {compareAuthors.length ? (
            <>
              <div className="benchmark-insight-list">
                {compareInsights.map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
              <div className="benchmark-compare-table-wrap">
                <table className="benchmark-table compact benchmark-compare-table">
                  <thead>
                    <tr>
                      <th>指标</th>
                      {compareAuthors.map((author) => (
                        <th key={author.author_id}>{author.nickname || "未知博主"}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ["账号类型", (author) => profileAnalysis(author, profileOverrides).persona],
                      ["粉丝量", (author) => compactNumber(author.follower_count)],
                      ["样本视频", (author) => compactNumber(author.video_count)],
                      ["对标分", (author) => compactNumber(author.benchmark_score)],
                      ["收藏倾向", (author) => percent(author.avg_collect_tendency)],
                      ["评论倾向", (author) => percent(author.avg_comment_tendency)],
                      ["小号效率", (author) => compactNumber(author.avg_small_account_efficiency)],
                      ["商业线索", (author) => profileAnalysis(author, profileOverrides).commerce.slice(0, 3).join(" / ") || "暂无"],
                      ["简介风险", (author) => profileAnalysis(author, profileOverrides).risk.slice(0, 3).join(" / ") || "暂无"],
                    ].map(([label, render]) => (
                      <tr key={label}>
                        <td>{label}</td>
                        {compareAuthors.map((author) => (
                          <td key={`${author.author_id}-${label}`}>{render(author)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="benchmark-note">还没有选择博主。点击博主卡片里的“对比”，这里会生成横向对比表。</p>
          )}
        </section>

        <section className="benchmark-card benchmark-profile-card">
          <div className="benchmark-card-head">
            <div>
              <h3>简介 AI 分析</h3>
              <p className="benchmark-note">把博主简介拆成定位、人设、转化线索和风险信号。</p>
            </div>
          </div>
          <div className="benchmark-profile-list">
            {(compareAuthors.length ? compareAuthors : authors.items.slice(0, 3)).map((author) => {
              const analysis = profileAnalysis(author, profileOverrides);
              return (
                <article className="benchmark-profile-cardlet" key={author.author_id}>
                  <div className="benchmark-cardlet-head">
                    <strong>{author.nickname || "未知博主"}</strong>
                    <button
                      className="text-button compact ghost"
                      type="button"
                      onClick={() => handleAnalyzeAuthor(author)}
                      disabled={!!analyzingAuthors[author.author_id]}
                    >
                      <Sparkles size={14} />
                      {analyzingAuthors[author.author_id] ? "分析中" : "AI分析"}
                    </button>
                  </div>
                  <span>{analysis.persona}</span>
                  <p>{analysis.summary}</p>
                  <div className="benchmark-pill-row">
                    {analysis.focus.slice(0, 3).map((item) => (
                      <span key={item}>{item}</span>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <section className="benchmark-card benchmark-comment-card">
          <div className="benchmark-card-head">
            <div>
              <h3>评论洞察</h3>
              <p className="benchmark-note">只使用已采集评论样本，观察提问、长评、低质重复和可复刻互动话术。</p>
            </div>
          </div>
          <div className="benchmark-comment-grid">
            <span><b>{compactNumber(commentInsights?.ready_video_count)}</b>有评论样本</span>
            <span><b>{compactNumber(commentInsights?.avg_quality_score)}</b>平均质量</span>
            <span><b>{percent(commentInsights?.question_ratio)}</b>提问占比</span>
            <span><b>{percent(commentInsights?.long_comment_ratio)}</b>长评占比</span>
            <span><b>{compactNumber(commentInsights?.brush_risk_video_count)}</b>刷屏风险</span>
          </div>
          <div className="benchmark-comment-layout">
            <div>
              <b>可操作建议</b>
              <ul className="benchmark-plain-list">
                {(commentInsights?.suggestions || []).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
            <div>
              <b>高赞评论样本</b>
              <div className="benchmark-comment-examples">
                {(commentInsights?.examples || []).slice(0, 4).map((item) => (
                  <button className="benchmark-comment-example" key={`${item.video_id}-${item.text}`} type="button" onClick={() => openVideo(item.video_id)}>
                    <span>{item.text}</span>
                    <small>{item.author_name} · 赞 {compactNumber(item.digg_count)}</small>
                  </button>
                ))}
                {!(commentInsights?.examples || []).length && <p className="benchmark-note">当前筛选下暂无评论样本。</p>}
              </div>
            </div>
            <div>
              <b>评论主题词</b>
              <div className="benchmark-pill-row">
                {(commentInsights?.top_topics || []).map((topic) => (
                  <span key={topic.name}>{topic.name} {topic.count}</span>
                ))}
                {!(commentInsights?.top_topics || []).length && <span>暂无主题词</span>}
              </div>
            </div>
          </div>
        </section>

        <section className="benchmark-card benchmark-matrix-card">
          <div className="benchmark-card-head">
            <div>
              <h3>内容模式价值矩阵</h3>
              <p className="benchmark-note">横轴是平均复刻分，纵轴是收藏+评论倾向，气泡大小代表样本数。</p>
            </div>
          </div>
          <PatternValueMatrix patterns={matrixPatterns} onSelectPattern={(pattern) => focusPatternVideos(pattern)} />
        </section>
      </div>

      <div className="benchmark-wide-grid">
        <section className="benchmark-card">
          <h3>内容模式库</h3>
          <div className="benchmark-pattern-list">
            {patterns.items.slice(0, 4).map((pattern) => (
              <article className="benchmark-pattern-card" key={pattern.pattern_id}>
                <strong>{pattern.name}</strong>
                <span>{pattern.description}</span>
                <div className="benchmark-row-actions">
                  <button className="text-button compact" type="button" onClick={() => openPattern(pattern)}>
                    详情/编辑
                  </button>
                  <button className="text-button compact" type="button" onClick={() => focusPatternVideos(pattern, { openDetail: false })}>
                    筛视频
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="benchmark-card">
          <h3>类型迁移</h3>
          <p className="benchmark-note">同一套看板支持其他垂类，只替换垂类标签和模式字段。</p>
          <table className="benchmark-table compact">
            <tbody>
              <tr><td>动漫解说</td><td>冲突、爽点、人物命运</td></tr>
              <tr><td>原创 Vlog</td><td>人设、场景、真实情绪</td></tr>
              <tr><td>好物种草</td><td>痛点、信任、转化路径</td></tr>
            </tbody>
          </table>
        </section>

        <section className="benchmark-card">
          <h3>指标说明</h3>
          <p className="benchmark-note">对标账号只使用公开可见指标、评论样本和 AI 拆解结果；互动强度指数是可配置排序指标，不是科学定律。</p>
          <div className="benchmark-weight-grid">
            {weightFields.map((field) => (
              <label key={field.key}>
                <span>{field.label}</span>
                <input
                  min="0"
                  max="20"
                  step="0.5"
                  type="number"
                  value={metricDraft[field.key] ?? field.default}
                  onChange={(event) => updateMetricDraft(field.key, event.target.value)}
                />
              </label>
            ))}
          </div>
          <button className="secondary-action-button benchmark-save-metrics" type="button" onClick={handleSaveMetricConfig} disabled={savingMetrics}>
            {savingMetrics ? "保存中" : "保存权重并重建"}
          </button>
          <div className="benchmark-pill-row">
            {metricGroups.map((group) => (
              <span key={group.name}>{group.name}</span>
            ))}
          </div>
          <p>点赞、评论、收藏、分享分别保留；综合分只用于快速粗排，不替代人工判断。</p>
          <details className="benchmark-missing-metrics">
            <summary>竞品不可见指标</summary>
            {unavailableMetrics.slice(0, 5).map((metric) => (
              <p key={metric.key}><b>{metric.label}：</b>{metric.reason}</p>
            ))}
          </details>
        </section>

        <section className="benchmark-card">
          <h3>对标依据</h3>
          <p className="benchmark-note">本页不做完播、留存、复访类健康评级，只做竞品可见信号的排序和模式拆解。</p>
          <div className="benchmark-grade-grid">
            <span><b>{compactNumber(overview?.public_signal_video_count)}</b>公开互动</span>
            <span><b>{compactNumber(overview?.comment_quality_video_count)}</b>评论样本</span>
            <span><b>{compactNumber(patterns.total)}</b>内容模式</span>
            <span><b>{compactNumber(overview?.unique_video_count)}</b>可对标视频</span>
          </div>
        </section>
      </div>

      {selectedVideo && (
        <aside className="benchmark-drawer" aria-label="视频轻详情">
          <button className="benchmark-drawer-close" type="button" onClick={() => setSelectedVideo(null)}>×</button>
          <h3>视频轻详情抽屉</h3>
          <p className="benchmark-note">从排行榜或博主页打开</p>
          <div className="benchmark-drawer-title">{selectedVideo.video?.desc || "未命名视频"}</div>
          <p><b>博主：</b>{selectedVideo.author?.nickname || selectedVideo.video?.author_name || "未知"}</p>
          <p><b>开头 3 秒：</b>{selectedVideo.opening_3s || "暂无开头摘要"}</p>
          <p><b>可复刻点：</b>{selectedVideo.replicable_point || "暂无复刻点"}</p>
          <div className="benchmark-drawer-metrics">
            <span>赞 {compactNumber(selectedVideo.metrics?.digg_count)}</span>
            <span>评 {compactNumber(selectedVideo.metrics?.comment_count)}</span>
            <span>藏 {compactNumber(selectedVideo.metrics?.collect_count)}</span>
            <span>转 {compactNumber(selectedVideo.metrics?.share_count)}</span>
            <span>收藏倾向 {percent(selectedVideo.metrics?.collect_tendency)}</span>
          </div>
          <div className="benchmark-author-section">
            <b>可见数据对标</b>
            <p className="benchmark-note">不使用播放量、完播率、留存率、复访率和铁粉互动；这些属于竞品后台不可见数据。</p>
            <div className="benchmark-author-metrics">
              <span><b>{compactNumber(selectedVideo.metrics?.public_engagement_score)}</b>公开互动分</span>
              <span><b>{percent(selectedVideo.metrics?.collect_tendency)}</b>收藏倾向</span>
              <span><b>{percent(selectedVideo.metrics?.comment_tendency)}</b>评论倾向</span>
              <span><b>{percent(selectedVideo.metrics?.share_tendency)}</b>分享倾向</span>
            </div>
          </div>
          <div className="benchmark-author-section">
            <b>评论质量：{selectedVideo.comment_quality?.status === "ready" ? `${selectedVideo.comment_quality.score}分` : "暂无样本"}</b>
            {selectedVideo.comment_quality?.status === "ready" && (
              <div className="benchmark-drawer-metrics">
                <span>有效 {percent(selectedVideo.comment_quality.valid_comment_ratio)}</span>
                <span>长评 {percent(selectedVideo.comment_quality.long_comment_ratio)}</span>
                <span>提问 {percent(selectedVideo.comment_quality.question_ratio)}</span>
                <span>{selectedVideo.comment_quality.brush_risk ? "疑似刷屏" : "未见刷屏"}</span>
              </div>
            )}
          </div>
          <button
            className="primary-button"
            type="button"
            onClick={() => {
              const taskId = extractTaskId(selectedVideo);
              if (taskId) {
                onOpenTask?.(taskId);
              }
            }}
            disabled={!extractTaskId(selectedVideo)}
          >
            <ExternalLink size={16} />
            {extractTaskId(selectedVideo) ? "打开任务中心完整拆解" : "暂无任务中心关联"}
          </button>
        </aside>
      )}

      {selectedPattern && (
        <aside className="benchmark-drawer benchmark-author-drawer" aria-label="模式详情">
          <button className="benchmark-drawer-close" type="button" onClick={() => setSelectedPattern(null)}>×</button>
          <h3>内容模式详情</h3>
          <p className="benchmark-note">{selectedPattern.pattern?.source === "ai_breakdown" ? "来自 AI 拆解字段聚类" : "来自规则聚类"}</p>
          <label className="benchmark-edit-field">
            <span>模式名</span>
            <input value={patternDraft.name} onChange={(event) => setPatternDraft((current) => ({ ...current, name: event.target.value }))} />
          </label>
          <label className="benchmark-edit-field">
            <span>描述</span>
            <textarea value={patternDraft.description} onChange={(event) => setPatternDraft((current) => ({ ...current, description: event.target.value }))} />
          </label>
          <label className="benchmark-edit-field">
            <span>人工备注</span>
            <textarea value={patternDraft.manual_notes} onChange={(event) => setPatternDraft((current) => ({ ...current, manual_notes: event.target.value }))} />
          </label>
          <button className="secondary-action-button" type="button" onClick={handleSavePattern} disabled={savingPattern}>
            {savingPattern ? "保存中" : "保存模式编辑"}
          </button>
          <div className="benchmark-author-metrics">
            <span><b>{compactNumber(selectedPattern.metrics?.video_count)}</b>视频</span>
            <span><b>{compactNumber(selectedPattern.metrics?.avg_imitation_value)}</b>复刻分</span>
            <span><b>{compactNumber(selectedPattern.metrics?.avg_comment_quality_score)}</b>评论质量</span>
            <span><b>{percent(selectedPattern.metrics?.avg_collect_tendency)}</b>收藏倾向</span>
            <span><b>{percent(selectedPattern.metrics?.avg_comment_tendency)}</b>评论倾向</span>
            <span><b>{percent(selectedPattern.metrics?.avg_share_tendency)}</b>分享倾向</span>
          </div>
          <div className="benchmark-author-section">
            <b>代表开头</b>
            {(selectedPattern.pattern?.openings || []).slice(0, 3).map((item, index) => (
              <p key={`${item}-${index}`}>{item}</p>
            ))}
          </div>
          <div className="benchmark-author-section">
            <b>代表视频</b>
            <div className="benchmark-author-videos">
              {(selectedPattern.representative_videos || []).slice(0, 5).map((video) => (
                <button key={video.video_id} className="text-button compact" type="button" onClick={() => openVideo(video.video_id)}>
                  {video.desc || "未命名视频"}
                </button>
              ))}
            </div>
          </div>
          <button
            className="primary-button"
            type="button"
            onClick={() => {
              focusPatternVideos(selectedPattern.pattern, { openDetail: false });
              setSelectedPattern(null);
            }}
          >
            筛选该模式视频
          </button>
        </aside>
      )}

      {selectedAuthor && (
        <aside className="benchmark-drawer benchmark-author-drawer" aria-label="博主详情">
          <button className="benchmark-drawer-close" type="button" onClick={() => setSelectedAuthor(null)}>×</button>
          <h3>博主对标详情</h3>
          <p className="benchmark-note">{selectedAuthor.profile?.positioning || selectedAuthor.author?.positioning || "暂无定位"}</p>
          <div className="benchmark-drawer-title">{selectedAuthor.author?.nickname || "未知博主"}</div>
          <div className="benchmark-author-metrics">
            {authorMetricRows(selectedAuthor).map(([label, value]) => (
              <span key={label}><b>{value}</b>{label}</span>
            ))}
          </div>
          {(selectedAuthor.author?.profile_analysis || profileOverrides[selectedAuthor.author?.author_id]) && (
            <div className="benchmark-author-section">
              <div className="benchmark-cardlet-head">
                <b>简介分析</b>
                <button
                  className="text-button compact ghost"
                  type="button"
                  onClick={() => handleAnalyzeAuthor(selectedAuthor.author)}
                  disabled={!!analyzingAuthors[selectedAuthor.author?.author_id]}
                >
                  <Sparkles size={14} />
                  {analyzingAuthors[selectedAuthor.author?.author_id] ? "分析中" : "重新AI分析"}
                </button>
              </div>
              <p>{profileAnalysis(selectedAuthor.author, profileOverrides).summary}</p>
              <div className="benchmark-pill-row">
                {(profileAnalysis(selectedAuthor.author, profileOverrides).focus || []).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </div>
          )}
          <div className="benchmark-author-section">
            <b>学习点</b>
            <div className="benchmark-pill-row">
              {(selectedAuthor.profile?.learning_points || selectedAuthor.author?.learning_points || []).map((point) => (
                <span key={point}>{point}</span>
              ))}
            </div>
          </div>
          <div className="benchmark-author-section">
            <b>常见开头</b>
            {(selectedAuthor.profile?.common_hooks || []).slice(0, 3).map((hook, index) => (
              <p key={`${hook}-${index}`}>{hook}</p>
            ))}
          </div>
          <div className="benchmark-author-section">
            <b>代表视频</b>
            <div className="benchmark-author-videos">
              {(selectedAuthor.representative_videos || []).slice(0, 4).map((video) => (
                <button key={video.video_id} className="text-button compact" type="button" onClick={() => openVideo(video.video_id)}>
                  {video.desc || "未命名视频"}
                </button>
              ))}
            </div>
          </div>
          <button
            className="primary-button"
            type="button"
            onClick={() => {
              focusAuthorVideos(selectedAuthor.author);
              setSelectedAuthor(null);
            }}
          >
            筛选该博主视频
          </button>
        </aside>
      )}
    </section>
  );
}
