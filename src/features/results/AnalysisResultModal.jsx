import { useEffect, useMemo, useState } from "react";
import { Check, Copy, Download, Send, Wand2 } from "lucide-react";
import { normalizeCommercialAnalysisResult, normalizeModelRuns } from "../../utils/appUtils";
import { fetchDouyinTargetVideoInteractions, rewriteAiVideoRemake, saveAiVideoRemakeExport, sendAiVideoRemakeToScript } from "../../services/api";
import { ModelRunSummary } from "./ModelRunSummary";

const RADAR_SIZE = 190;
const RADAR_CENTER = RADAR_SIZE / 2;
const RADAR_RADIUS = 72;
const EMPTY_TEXT = "暂无内容";

function clampScore(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, Math.round(number)));
}

function formatValue(value) {
  if (Array.isArray(value)) return value.filter(Boolean).join("，");
  if (value && typeof value === "object") {
    if (typeof value.text === "string") return value.text;
    return JSON.stringify(value, null, 2);
  }
  return value || EMPTY_TEXT;
}

function actionableText(value) {
  const text = formatValue(value).trim();
  return text && text !== EMPTY_TEXT ? text : "";
}

function sanitizeFileName(value) {
  return String(value || "ai-video-remake-lab")
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, "-")
    .slice(0, 80);
}

function buildRemakeItems(result) {
  const plan = result.replication_plan || {};
  const copywriting = result.copywriting_formula || {};
  return [
    {
      id: "template",
      label: "标准复刻脚本",
      value: result.standard_remake_template || copywriting.script_formula,
      wide: true,
    },
    {
      id: "cross-genre",
      label: "跨赛道改写",
      value: plan.cross_genre_variants,
      wide: true,
    },
    {
      id: "hook",
      label: "Hook",
      value: result.core_hook?.opening_3s || copywriting.title_formula,
    },
    {
      id: "core",
      label: "Core",
      value: plan.reusable_formula || copywriting.script_formula,
    },
    {
      id: "cta",
      label: "CTA",
      value: copywriting.cta,
    },
  ];
}

function buildRemakeMarkdown({ result, title, genre, targetGenre }) {
  const items = buildRemakeItems(result);
  const lines = [
    `# ${title || "AI 视频拆解复刻实验"}`,
    "",
    `- 赛道: ${genre || result.genre || "泛赛道"}`,
    `- 目标赛道: ${targetGenre || "未指定"}`,
    `- 摘要: ${result.summary || EMPTY_TEXT}`,
    "",
    "## 复刻组件",
    "",
  ];
  for (const item of items) {
    lines.push(`### ${item.label}`, "", actionableText(item.value) || EMPTY_TEXT, "");
  }
  lines.push("## 爆款公式", "", actionableText(result.replication_plan?.reusable_formula) || EMPTY_TEXT, "");
  lines.push(
    "## 风险控制",
    "",
    actionableText(result.risk_control?.safe_rewrite || result.risk_control?.platform_risks) || EMPTY_TEXT,
    "",
  );
  return lines.join("\n");
}

async function copyToClipboard(text) {
  if (!text) throw new Error("没有可复制内容");
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // fallback below
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) throw new Error("复制失败，请手动选择文本复制");
}

function downloadTextFile({ fileName, text }) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function topEntries(source, limit = 6) {
  if (!source || typeof source !== "object" || Array.isArray(source)) return [];
  return Object.entries(source)
    .filter(([, value]) => Number(value) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, limit);
}

function firstTextValue(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && String(value).trim()) {
      return String(value).trim();
    }
  }
  return "";
}

function commentLikeCount(comment) {
  const value = Number(comment?.digg_count ?? comment?.like_count ?? comment?.likes ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function normalizeCommentItem(comment, index = 0) {
  if (typeof comment === "string") {
    return { id: `comment-${index}`, text: comment, nickname: "", digg_count: 0, reply_count: 0 };
  }
  if (!comment || typeof comment !== "object") {
    return { id: `comment-${index}`, text: "", nickname: "", digg_count: 0, reply_count: 0 };
  }
  return {
    ...comment,
    id: comment.id || comment.comment_id || `comment-${index}`,
    text: firstTextValue(comment.text, comment.content, comment.comment),
    nickname: firstTextValue(comment.nickname, comment.unique_id, comment.user_name),
    digg_count: commentLikeCount(comment),
    reply_count: Number(comment.reply_count || 0),
  };
}

function commentIdentity(comment) {
  const primaryId = firstTextValue(comment?.comment_id, comment?.id, comment?.cid);
  if (primaryId) return `id:${primaryId}`;
  const text = firstTextValue(comment?.text, comment?.content, comment?.comment)
    .replace(/\s+/g, "")
    .slice(0, 120);
  const nickname = firstTextValue(comment?.nickname, comment?.unique_id, comment?.user_name).replace(/\s+/g, "");
  return `text:${nickname}:${text}`;
}

function sortTopComments(comments, limit = 8) {
  const seen = new Set();
  return (Array.isArray(comments) ? comments : [])
    .map(normalizeCommentItem)
    .filter((comment) => {
      if (!comment.text) return false;
      const key = commentIdentity(comment);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => commentLikeCount(b) - commentLikeCount(a))
    .slice(0, limit);
}

function buildInteractionSnapshot(snapshot, liveDataset) {
  const base = snapshot && typeof snapshot === "object" ? snapshot : {};
  const insights = liveDataset?.insights && typeof liveDataset.insights === "object" ? liveDataset.insights : {};
  const comments = Array.isArray(liveDataset?.comments) ? liveDataset.comments : [];
  const topFromComments = sortTopComments(comments.filter((item) => Number(item?.level || 1) === 1), 8);
  return {
    ...base,
    status: base.status || liveDataset?.video?.comment_snapshot_status || "",
    comment_saved_count: base.comment_saved_count || insights.comment_count_saved || liveDataset?.comment_count || 0,
    reply_saved_count: base.reply_saved_count || insights.reply_count_saved || liveDataset?.reply_count || 0,
    keyword_counts: Object.keys(base.keyword_counts || {}).length ? base.keyword_counts : insights.keyword_counts || {},
    symbol_counts: Object.keys(base.symbol_counts || {}).length ? base.symbol_counts : insights.symbol_counts || {},
    emotion_profile: Object.keys(base.emotion_profile || {}).length ? base.emotion_profile : insights.emotion_profile || {},
    creator_reply_tactics: Object.keys(base.creator_reply_tactics || {}).length ? base.creator_reply_tactics : insights.creator_reply_tactics || {},
    pinned_comments: Array.isArray(base.pinned_comments) && base.pinned_comments.length ? base.pinned_comments : insights.pinned_comments || [],
    author_replies: Array.isArray(base.author_replies) && base.author_replies.length ? base.author_replies : insights.author_replies || [],
    top_comments: sortTopComments(
      [
        ...(Array.isArray(base.top_comments) ? base.top_comments : []),
        ...(Array.isArray(insights.top_comments) ? insights.top_comments : []),
        ...topFromComments,
      ],
      8,
    ),
  };
}

function resolveTargetVideoId(task, result) {
  const video = task?.video || task?.payload?.video || {};
  return firstTextValue(
    result?.douyin_target?.video_id,
    result?.douyin_target?.aweme_id,
    video?.douyin_target_context?.video_id,
    video?.aweme_id,
    video?.id,
  );
}

function radarPoint(index, total, value = 100) {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / total;
  const radius = RADAR_RADIUS * (clampScore(value) / 100);
  return [RADAR_CENTER + Math.cos(angle) * radius, RADAR_CENTER + Math.sin(angle) * radius];
}

function radarAxisPoint(index, total) {
  return radarPoint(index, total, 100);
}

function buildRadarItems(result) {
  const scores = result.viral_scores || {};
  const metrics = result.douyin_target?.metrics || {};
  const interactionRate = Math.min(100, Math.round(Number(metrics.comment_like_ratio || metrics.interaction_rate || 0) * 1000));
  const saveRate = Math.min(100, Math.round(Number(metrics.collect_like_ratio || metrics.save_rate || 0) * 1000));
  const shareRate = Math.min(100, Math.round(Number(metrics.share_like_ratio || metrics.share_rate || 0) * 1200));
  return [
    ["爆款", scores.viral_potential || scores.overall || 0],
    ["模仿", scores.imitation_value || 0],
    ["商业", scores.commerce_value || 0],
    ["评论", scores.comment_potential || interactionRate],
    ["收藏", saveRate || scores.imitation_value || 0],
    ["破圈", shareRate || scores.viral_potential || 0],
  ];
}

function buildSummaryStats({ result, evidence, segmentCount, modelRunCount }) {
  const scores = result.viral_scores || {};
  const overall = clampScore(scores.overall || scores.viral_potential || 0);
  return [
    ["分析模式", result.analysis_mode || (evidence.evidence_path ? "evidence" : "direct")],
    ["综合评分", overall ? `${overall} / 100` : "暂无"],
    ["分段数量", `${segmentCount || 0} 段`],
    ["关键帧", `${evidence.keyframes_count || 0} 张`],
    ["模型调用", `${modelRunCount || 0} 次`],
    ["证据文件", evidence.evidence_path ? "已生成" : "暂无"],
  ];
}

function buildEvidenceRows({ result, evidence, segmentCount, modelRunCount }) {
  return [
    ["分析模式", result.analysis_mode || "evidence"],
    ["转写器", evidence.transcript_provider || "暂无"],
    ["证据路径", evidence.evidence_path || "暂无"],
    ["分段数量", `${evidence.analysis_segments_count || segmentCount || 0} 段`],
    ["关键帧数量", `${evidence.keyframes_count || 0} 张`],
    ["模型调用", `${modelRunCount || 0} 次`],
  ];
}

function radarConclusion(items, genre) {
  const sorted = [...items].sort((a, b) => b[1] - a[1]);
  const [first, second] = sorted;
  if (!first || first[1] <= 0) return `${genre || "泛赛道"}样本，等待更多指标形成画像`;
  return `${genre || "泛赛道"}样本偏向${first[0]}，其次是${second?.[0] || "其他"}，适合优先拆结构`;
}

function MetricRadar({ items, genre }) {
  const points = items.map(([, value], index) => radarPoint(index, items.length, value).join(",")).join(" ");
  const gridLevels = [25, 50, 75, 100];
  return (
    <div className="content-lab-radar-card">
      <svg className="content-lab-radar" viewBox={`0 0 ${RADAR_SIZE} ${RADAR_SIZE}`} role="img" aria-label="多维数据雷达图">
        {gridLevels.map((level) => (
          <polygon
            key={level}
            points={items.map((_, index) => radarPoint(index, items.length, level).join(",")).join(" ")}
            className="radar-grid"
          />
        ))}
        {items.map((_, index) => {
          const [x, y] = radarAxisPoint(index, items.length);
          return <line key={index} x1={RADAR_CENTER} y1={RADAR_CENTER} x2={x} y2={y} className="radar-axis" />;
        })}
        <polygon points={points} className="radar-shape" />
        {items.map(([label, value], index) => {
          const [x, y] = radarAxisPoint(index, items.length);
          return (
            <text key={label} x={x} y={y} textAnchor="middle" dominantBaseline="middle" className="radar-label">
              {label} {clampScore(value)}
            </text>
          );
        })}
      </svg>
      <p>{radarConclusion(items, genre)}</p>
    </div>
  );
}

function SectionRows({ title, rows }) {
  return (
    <section className="analysis-section content-lab-detail-card">
      <strong>{title}</strong>
      <div className="content-lab-field-grid">
        {rows.map(([label, value]) => (
          <div className="analysis-field" key={label}>
            <span>{label}</span>
            <p>{formatValue(value)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function CommentIntelligence({ snapshot, loading, error }) {
  const emotion = snapshot?.emotion_profile || {};
  const motivation = emotion.motivation_buckets || emotion.buckets || {};
  const keywords = topEntries(snapshot?.keyword_counts, 8);
  const motivations = topEntries(motivation, 6);
  const pinned = Array.isArray(snapshot?.pinned_comments) ? snapshot.pinned_comments : [];
  const topComments = sortTopComments(snapshot?.top_comments, 8);
  const authorReplies = Array.isArray(snapshot?.author_replies) ? snapshot.author_replies : [];
  const savedTotal = Number(snapshot?.comment_saved_count || 0) + Number(snapshot?.reply_saved_count || 0);
  return (
    <div className="analysis-section content-lab-comments">
      <strong>评论区洞察</strong>
      {loading && <p className="field-hint">正在读取评论库...</p>}
      {error && <p className="field-hint">评论库读取失败：{error}</p>}
      <div className="content-lab-chip-grid">
        {(motivations.length ? motivations : [[savedTotal ? "已保存评论/回复" : "暂无动机数据", savedTotal]]).map(([label, value]) => (
          <span key={label}>{label} · {value}</span>
        ))}
      </div>
      <div className="content-lab-comment-grid">
        <div className="analysis-field">
          <span>高频互动词</span>
          <p>{keywords.map(([label, value]) => `${label}(${value})`).join(" / ") || "暂无内容"}</p>
        </div>
        <div className="analysis-field">
          <span>置顶/神评</span>
          <p>{formatValue(pinned[0] || topComments[0])}</p>
        </div>
        <div className="analysis-field">
          <span>作者留人话术</span>
          <p>{formatValue(authorReplies[0])}</p>
        </div>
      </div>
      <div className="content-lab-top-comments">
        <span>点赞最高评论</span>
        {topComments.length ? (
          topComments.map((comment, index) => (
            <article key={comment.id || `${comment.text}-${index}`}>
              <div>
                <strong>{index + 1}. {comment.nickname || "匿名用户"}</strong>
                <p>{comment.text}</p>
              </div>
              <small>{comment.digg_count || 0} 赞 · {comment.reply_count || 0} 回复</small>
            </article>
          ))
        ) : (
          <p>{loading ? "正在加载评论..." : "暂无已保存评论"}</p>
        )}
      </div>
    </div>
  );
}

function SegmentTimeline({ segments }) {
  if (!segments.length) return null;
  return (
    <div className="analysis-section content-lab-timeline">
      <strong>多模态双轨时间线</strong>
      <div className="content-lab-timeline-list">
        {segments.map((segment, index) => (
          <article className="content-lab-timeline-item" key={segment.id || segment.segment_id || index}>
            <div className="content-lab-time-mark">
              <span>{segment.time_range || `片段 ${index + 1}`}</span>
              <strong>{segment.segment_role || "未标注"}</strong>
            </div>
            <div className="content-lab-track">
              <span>视听手法</span>
              <p>{[segment.visual_style, segment.audio_pacing].filter(Boolean).join(" / ") || "暂无内容"}</p>
            </div>
            <div className="content-lab-track">
              <span>心理拆解</span>
              <p>{[segment.narrative_technique, segment.retention_mechanism].filter(Boolean).join(" / ") || "暂无内容"}</p>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function RemakeLab({
  result,
  title,
  genre,
  targetGenre,
  onTargetGenreChange,
  onCopy,
  onExport,
  onRewrite,
  onSendToScript,
  actionStatus,
  pendingAction,
}) {
  const items = buildRemakeItems(result);
  const markdown = buildRemakeMarkdown({ result, title, genre, targetGenre });
  return (
    <div className="analysis-section content-lab-remake">
      <div className="content-lab-section-head">
        <strong>复刻实验室</strong>
        <div className="content-lab-actions">
          <button className="text-button" type="button" onClick={() => onCopy("full", markdown)}>
            {actionStatus === "copy:full" ? <Check size={15} /> : <Copy size={15} />}
            复制整套模板
          </button>
          <button className="text-button" type="button" onClick={() => onExport(markdown)}>
            <Download size={15} />
            导出 Markdown
          </button>
        </div>
      </div>

      <label className="analysis-field content-lab-target-field">
        <span>目标赛道</span>
        <input
          type="text"
          value={targetGenre}
          placeholder="beauty / knowledge / comedy / ecommerce"
          onChange={(event) => onTargetGenreChange(event.target.value)}
        />
      </label>

      <div className="content-lab-remake-grid">
        {items.map((item) => {
          const text = actionableText(item.value);
          const copied = actionStatus === `copy:${item.id}`;
          return (
            <div className={item.wide ? "content-lab-template" : "content-lab-token-row"} key={item.id}>
              <div className="content-lab-copy-head">
                <span>{item.label}</span>
                <button className="text-button compact-copy-button" type="button" disabled={!text} onClick={() => onCopy(item.id, text)}>
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  {copied ? "已复制" : "复制"}
                </button>
              </div>
              <p>{text || EMPTY_TEXT}</p>
            </div>
          );
        })}
      </div>

      <div className="content-lab-actions content-lab-lab-actions">
        <button className="text-button" type="button" onClick={() => onRewrite(markdown)} disabled={pendingAction === "rewrite"}>
          <Wand2 size={15} />
          {pendingAction === "rewrite" ? "改写中..." : "跨赛道改写"}
        </button>
        <button className="text-button" type="button" onClick={() => onSendToScript(markdown)} disabled={pendingAction === "script"}>
          <Send size={15} />
          {pendingAction === "script" ? "送入脚本..." : "送入脚本生成"}
        </button>
      </div>
    </div>
  );
}

export function AnalysisResultModal({ task, onClose }) {
  const [actionStatus, setActionStatus] = useState("");
  const [pendingAction, setPendingAction] = useState("");
  const [targetGenre, setTargetGenre] = useState("beauty");
  const [liveInteractions, setLiveInteractions] = useState(null);
  const [liveInteractionStatus, setLiveInteractionStatus] = useState({ loading: false, error: "" });

  const result = useMemo(() => normalizeCommercialAnalysisResult(task?.result || {}), [task]);
  const evidence = result.evidence || {};
  const targetVideoId = useMemo(() => resolveTargetVideoId(task, result), [task, result]);
  const interactionSnapshot = useMemo(
    () => buildInteractionSnapshot(result.douyin_target?.interaction_snapshot || result.douyin_target, liveInteractions),
    [result.douyin_target, liveInteractions],
  );
  const modelRuns = useMemo(
    () => normalizeModelRuns(task?.modelRuns, task?.model_runs, task?.result?.model_runs, result.model_runs),
    [task, result.model_runs],
  );
  const segmentBreakdowns = Array.isArray(result.segment_breakdowns) ? result.segment_breakdowns : [];
  const radarItems = useMemo(() => buildRadarItems(result), [result]);
  const genre = result.content_identity?.track || result.genre || "泛赛道";
  const summaryStats = buildSummaryStats({
    result,
    evidence,
    segmentCount: segmentBreakdowns.length,
    modelRunCount: modelRuns.length,
  });
  const evidenceRows = buildEvidenceRows({
    result,
    evidence,
    segmentCount: segmentBreakdowns.length,
    modelRunCount: modelRuns.length,
  });
  const remakeMarkdown = useMemo(() => buildRemakeMarkdown({ result, title: task?.title, genre, targetGenre }), [result, task, genre, targetGenre]);

  useEffect(() => {
    let cancelled = false;
    setLiveInteractions(null);
    setLiveInteractionStatus({ loading: false, error: "" });
    if (!targetVideoId) return () => {
      cancelled = true;
    };
    setLiveInteractionStatus({ loading: true, error: "" });
    fetchDouyinTargetVideoInteractions(targetVideoId)
      .then((dataset) => {
        if (!cancelled) {
          setLiveInteractions(dataset);
          setLiveInteractionStatus({ loading: false, error: "" });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setLiveInteractionStatus({ loading: false, error: err?.message || String(err) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [targetVideoId]);

  async function handleCopy(id, text) {
    try {
      await copyToClipboard(text);
      setActionStatus(`copy:${id}`);
      window.setTimeout(() => setActionStatus(""), 1600);
    } catch (err) {
      setActionStatus(`error:${err.message || "复制失败"}`);
      window.setTimeout(() => setActionStatus(""), 2200);
    }
  }

  function handleExport(markdown) {
    downloadTextFile({
      fileName: `${sanitizeFileName(task?.title)}-remake-lab.md`,
      text: markdown,
    });
    saveAiVideoRemakeExport({
      runId: task?.result?.evidence?.run_id || task?.id || "",
      taskId: task?.id || "",
      title: task?.title || "",
      genre,
      targetGenre: targetGenre.trim() || "generic",
      markdown,
      result,
      exportType: "remake_package",
    })
      .then(() => {
        setActionStatus("exported");
        window.setTimeout(() => setActionStatus(""), 1600);
      })
      .catch((err) => {
        setActionStatus(`error:${err.message || "导出保存失败"}`);
        window.setTimeout(() => setActionStatus(""), 2400);
      });
  }

  async function handleRewrite(markdown) {
    setPendingAction("rewrite");
    try {
      const payload = {
        runId: task?.result?.evidence?.run_id || task?.id || "",
        taskId: task?.id || "",
        title: task?.title || "",
        sourceGenre: genre,
        targetGenre: targetGenre.trim() || "generic",
        markdown,
        result,
      };
      await rewriteAiVideoRemake(payload);
      setActionStatus("rewritten");
      window.setTimeout(() => setActionStatus(""), 1600);
    } catch (err) {
      setActionStatus(`error:${err.message || "改写失败"}`);
      window.setTimeout(() => setActionStatus(""), 2800);
    } finally {
      setPendingAction("");
    }
  }

  async function handleSendToScript(markdown) {
    setPendingAction("script");
    try {
      const payload = {
        runId: task?.result?.evidence?.run_id || task?.id || "",
        taskId: task?.id || "",
        title: task?.title || "",
        sourceGenre: genre,
        targetGenre: targetGenre.trim() || "generic",
        markdown,
        result,
        durationSeconds: 60,
        sceneCount: 6,
      };
      await sendAiVideoRemakeToScript(payload);
      setActionStatus("sent");
      window.setTimeout(() => setActionStatus(""), 1600);
    } catch (err) {
      setActionStatus(`error:${err.message || "发送失败"}`);
      window.setTimeout(() => setActionStatus(""), 2800);
    } finally {
      setPendingAction("");
    }
  }

  const sections = [
    ["内容定位", [["内容赛道", genre], ["赛道适配", result.content_identity?.niche_fit], ["账号人设", result.content_identity?.account_persona]]],
    [
      "文本与话术技巧",
      [
        ["开头留存", result.core_hook?.opening_3s],
        ["信息差/悬念", result.core_hook?.curiosity_gap],
        ["情绪触发", result.core_hook?.emotional_trigger],
        ["评论/转化钩子", result.core_hook?.comment_bait],
      ],
    ],
    [
      "视觉与节奏模板",
      [
        ["镜头结构", result.visual_structure?.shot_structure],
        ["视觉爽点/信息密度", result.visual_structure?.reusable_elements],
        ["黄金节奏点", result.visual_structure?.timeline_beats],
        ["声音节奏", result.visual_structure?.audio_rhythm],
      ],
    ],
    [
      "爆款公式与定位",
      [
        ["公式名", result.replication_plan?.pattern_name],
        ["可复刻公式", result.replication_plan?.reusable_formula],
        ["适合产品/栏目", result.market_positioning?.suitable_products],
        ["目标人群", result.market_positioning?.target_audience],
        ["创作方向", result.market_positioning?.creative_direction],
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

  if (!task) return null;

  return (
    <div className="modal-backdrop content-lab-backdrop" role="presentation" onClick={onClose}>
      <section className="modal-panel content-lab-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header content-lab-header">
          <div>
            <span className="content-lab-kicker">全赛道内容实验室</span>
            <h2>AI 视频拆解结果</h2>
            <p>{task.title}</p>
          </div>
          <button className="text-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="analysis-result-body content-lab-body">
          <section className="content-lab-overview">
            <div className="content-lab-summary">
              <span>{genre}</span>
              <p>{result.summary || "暂无摘要"}</p>
              {(result.analysis_mode || evidence.evidence_path) && (
                <small>
                  {result.analysis_mode || "evidence"} · {(evidence.transcript_provider || "未知转写器")} · {evidence.analysis_segments_count || segmentBreakdowns.length || 0} 个分析片段 ·{" "}
                  {evidence.keyframes_count || 0} 张关键帧
                </small>
              )}
            </div>
            <MetricRadar items={radarItems} genre={genre} />
          </section>

          <div className="content-lab-stat-strip">
            {summaryStats.map(([label, value]) => (
              <article className="content-lab-stat-card" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </article>
            ))}
          </div>

          <div className="content-lab-workspace">
            <div className="content-lab-main">
              <CommentIntelligence snapshot={interactionSnapshot} loading={liveInteractionStatus.loading} error={liveInteractionStatus.error} />
              <SegmentTimeline segments={segmentBreakdowns} />
              <RemakeLab
                result={result}
                title={task.title}
                genre={genre}
                targetGenre={targetGenre}
                onTargetGenreChange={setTargetGenre}
                onCopy={handleCopy}
                onExport={handleExport}
                onRewrite={handleRewrite}
                onSendToScript={handleSendToScript}
                actionStatus={actionStatus}
                pendingAction={pendingAction}
              />
            </div>

            <aside className="content-lab-side">
              <SectionRows title="证据概览" rows={evidenceRows} />
              <ModelRunSummary runs={modelRuns} compact />
              {actionStatus && (
                <div className={`content-lab-action-status ${actionStatus.startsWith("error:") ? "error" : ""}`} role="status">
                  {actionStatus.startsWith("error:")
                    ? actionStatus.replace("error:", "")
                    : actionStatus === "exported"
                      ? "Markdown 已导出"
                      : actionStatus === "rewritten"
                        ? "已完成跨赛道改写并保存"
                        : actionStatus === "sent"
                          ? "已送入脚本生成并保存"
                          : "内容已复制"}
                </div>
              )}
            </aside>
          </div>

          <div className="content-lab-detail-grid">
            {sections.map(([sectionTitle, rows]) => (
              <SectionRows title={sectionTitle} rows={rows} key={sectionTitle} />
            ))}
          </div>

          <details className="raw-json">
            <summary>查看原始 JSON</summary>
            <pre className="result-box">{JSON.stringify(result.raw_model_json || result, null, 2)}</pre>
          </details>
        </div>
      </section>
    </div>
  );
}
