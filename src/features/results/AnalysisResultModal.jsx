import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Copy, Download, Play, Send, Wand2 } from "lucide-react";
import { Badge } from "../../components/common/index";
import { compactNumber, normalizeCommercialAnalysisResult, normalizeModelRuns, normalizeTagList } from "../../utils/appUtils";
import { fetchAiVideoEvidence, fetchDouyinTargetVideoInteractions, rewriteAiVideoRemake, saveAiVideoRemakeExport, sendAiVideoRemakeToScript } from "../../services/api";
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

function secondsToLabel(value) {
  const seconds = Math.max(0, Number(value || 0));
  if (!Number.isFinite(seconds)) return "00:00";
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  const base = `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  return hours ? `${String(hours).padStart(2, "0")}:${base}` : base;
}

function firstUrlValue(...values) {
  for (const value of values) {
    if (!value) continue;
    if (typeof value === "string" && value.trim()) return value.trim();
    if (Array.isArray(value)) {
      const nested = firstUrlValue(...value);
      if (nested) return nested;
    }
    if (value && typeof value === "object") {
      const nested = firstUrlValue(value.url_list, value.url, value.play_addr, value.download_addr);
      if (nested) return nested;
    }
  }
  return "";
}

function proxiedDouyinMediaUrl(url) {
  if (!url) return "";
  if (/^\/api\//.test(url) || url.startsWith("blob:") || url.startsWith("data:")) return url;
  return `/api/integrations/douyin/media-proxy?url=${encodeURIComponent(url)}&referer=${encodeURIComponent("https://www.douyin.com/")}`;
}

function resolveSourceVideoUrl(task, evidenceDataset) {
  const mediaUrl = evidenceDataset?.media?.video_url;
  if (mediaUrl) return mediaUrl;
  const video = task?.video || task?.payload?.video || task?.raw?.video || {};
  const nestedVideo = video?.video || video?.video_data || {};
  const sourceUrl = firstUrlValue(
    video.source_video_url,
    video.video_url,
    video.download_url,
    video.play_url,
    video.nwm_video_url_HQ,
    video.wm_video_url_HQ,
    nestedVideo.play_addr,
    nestedVideo.download_addr,
    nestedVideo.nwm_video_url_HQ,
    nestedVideo.wm_video_url_HQ,
  );
  return proxiedDouyinMediaUrl(sourceUrl);
}

function resolvePosterUrl(task) {
  const video = task?.video || task?.payload?.video || task?.raw?.video || {};
  const nestedVideo = video?.video || video?.video_data || {};
  return firstUrlValue(
    video.cover_url,
    video.cover,
    video.origin_cover,
    video.dynamic_cover,
    nestedVideo.cover,
    nestedVideo.origin_cover,
    nestedVideo.dynamic_cover,
  );
}

function normalizeTranscriptItem(item, index = 0) {
  if (typeof item === "string") {
    return { id: `line-${index}`, start: 0, end: 0, text: item };
  }
  if (!item || typeof item !== "object") {
    return { id: `line-${index}`, start: 0, end: 0, text: "" };
  }
  const start = Number(item.start ?? item.start_time ?? item.begin_time ?? item.offset ?? 0);
  const end = Number(item.end ?? item.end_time ?? item.stop_time ?? item.finish_time ?? start);
  return {
    ...item,
    id: item.id || item.utterance_id || item.segment_id || `line-${index}`,
    start: Number.isFinite(start) ? start : 0,
    end: Number.isFinite(end) ? end : Number.isFinite(start) ? start : 0,
    text: firstTextValue(item.text, item.content, item.transcript, item.sentence),
  };
}

function parseTimeToSeconds(value) {
  if (typeof value === "number") return value;
  if (typeof value !== "string") return 0;
  const text = value.trim();
  if (!text) return 0;
  const first = text.split(/[-~—–至]/)[0]?.trim() || text;
  const parts = first.split(":").map((part) => Number(part));
  if (parts.some((part) => !Number.isFinite(part))) {
    const numeric = Number(first.replace(/[^\d.]/g, ""));
    return Number.isFinite(numeric) ? numeric : 0;
  }
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return parts[0] || 0;
}

function seekStartSeconds(item) {
  const value = item?.start ?? item?.start_seconds ?? item?.startTime ?? item?.time ?? item?.time_label ?? item?.time_range;
  const seconds = typeof value === "string" ? parseTimeToSeconds(value) : Number(value || 0);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : 0;
}

function mergeSegmentBreakdowns(resultSegments, evidenceSegments) {
  const evidenceById = new Map();
  for (const item of Array.isArray(evidenceSegments) ? evidenceSegments : []) {
    if (!item || typeof item !== "object") continue;
    const id = item.segment_id || item.id;
    if (id) evidenceById.set(String(id), item);
  }
  return (Array.isArray(resultSegments) ? resultSegments : []).map((segment, index) => {
    const id = segment?.segment_id || segment?.id || `seg_${index + 1}`;
    const evidence = evidenceById.get(String(id)) || {};
    return {
      ...evidence,
      ...segment,
      id: segment?.id || evidence.id || id,
      segment_id: segment?.segment_id || evidence.segment_id || id,
      start: segment?.start ?? evidence.start,
      end: segment?.end ?? evidence.end,
      time_range: segment?.time_range || evidence.time_range,
      transcript: segment?.transcript || evidence.transcript,
      transcript_segments: segment?.transcript_segments || evidence.transcript_segments || [],
    };
  });
}

function buildTranscriptLines({ evidenceDataset, result, segmentBreakdowns }) {
  const transcript = evidenceDataset?.transcript && typeof evidenceDataset.transcript === "object" ? evidenceDataset.transcript : {};
  const evidenceSegments = Array.isArray(transcript.segments) ? transcript.segments : [];
  if (evidenceSegments.length) {
    return evidenceSegments.map(normalizeTranscriptItem).filter((item) => item.text);
  }
  const words = Array.isArray(transcript.words) ? transcript.words : [];
  if (words.length) {
    return words.map(normalizeTranscriptItem).filter((item) => item.text);
  }
  const rawEvidence = result?.raw_model_json?.transcript;
  const rawSegments = rawEvidence && typeof rawEvidence === "object" && Array.isArray(rawEvidence.segments) ? rawEvidence.segments : [];
  if (rawSegments.length) {
    return rawSegments.map(normalizeTranscriptItem).filter((item) => item.text);
  }
  return segmentBreakdowns
    .map((segment, index) => normalizeTranscriptItem({
      id: segment.segment_id || segment.id,
      start: seekStartSeconds(segment),
      end: segment.end,
      text: segment.transcript || segment.segment_text || segment.summary,
    }, index))
    .filter((item) => item.text);
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

function mergeFilledObject(...sources) {
  const merged = {};
  for (const source of sources) {
    if (!source || typeof source !== "object") continue;
    for (const [key, value] of Object.entries(source)) {
      if (value === undefined || value === null || value === "") continue;
      if (typeof value === "number" && !Number.isFinite(value)) continue;
      merged[key] = value;
    }
  }
  return merged;
}

function parseObjectMaybe(value) {
  if (!value) return {};
  if (typeof value === "object" && !Array.isArray(value)) return value;
  if (typeof value !== "string") return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function numberFromMixed(value) {
  if (value === undefined || value === null || value === "") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const text = String(value).replace(/,/g, "").trim();
  if (!text) return null;
  const match = text.match(/-?\d+(?:\.\d+)?/);
  if (!match) return null;
  const base = Number(match[0]);
  if (!Number.isFinite(base)) return null;
  if (text.includes("亿")) return Math.round(base * 100000000);
  if (text.includes("万")) return Math.round(base * 10000);
  return base;
}

function firstNumberValue(...values) {
  for (const value of values) {
    const number = numberFromMixed(value);
    if (number !== null) return number;
  }
  return null;
}

function firstPositiveNumberValue(...values) {
  let fallback = null;
  for (const value of values) {
    const number = numberFromMixed(value);
    if (number === null) continue;
    if (number > 0) return number;
    if (fallback === null) fallback = number;
  }
  return fallback;
}

function resolveCommonFlagsFollowerCount(author, taskVideo) {
  const flags = parseObjectMaybe(
    taskVideo?.raw?.feed_comment_config?.common_flags
      || taskVideo?.feed_comment_config?.common_flags
      || taskVideo?.statistics?.common_flags
      || taskVideo?.common_flags,
  );
  const followerMap = parseObjectMaybe(flags.mix_follower_count);
  if (!Object.keys(followerMap).length) return null;
  const ids = [
    author.uid,
    author.user_id,
    author.id,
    author.sec_uid,
    author.sec_user_id,
    taskVideo?.author_user_id,
    taskVideo?.raw?.author_user_id,
  ].filter(Boolean).map(String);
  for (const id of ids) {
    const value = firstNumberValue(followerMap[id]);
    if (value !== null) return value;
  }
  return firstNumberValue(...Object.values(followerMap));
}

function resolveAuthorProfile(task, taskVideo, result) {
  const rawAuthor = mergeFilledObject(
    taskVideo?.raw?.author,
    taskVideo?.author?.raw,
    task?.payload?.douyin_target?.author,
    task?.payload?.author,
    result?.douyin_target?.author,
    result?.author?.raw,
  );
  const author = mergeFilledObject(
    rawAuthor,
    taskVideo?.author,
    taskVideo?.user,
    taskVideo?.owner,
    result?.author,
  );
  const authorSources = [rawAuthor, taskVideo?.author, taskVideo?.user, taskVideo?.owner, result?.author].filter(
    (item) => item && typeof item === "object",
  );
  const avatar = firstUrlValue(
    author.avatar,
    author.avatar_url,
    author.avatar_thumb,
    author.avatar_medium,
    author.avatar_large,
    rawAuthor.avatar,
    rawAuthor.avatar_thumb,
    rawAuthor.avatar_medium,
    rawAuthor.avatar_large,
  );
  const uid = firstTextValue(author.uid, author.user_id, author.id, taskVideo?.author_user_id, taskVideo?.raw?.author_user_id);
  const uniqueId = firstTextValue(author.unique_id, author.uniqueId, author.short_id, author.display_id, author.search_user_name);
  const secUid = firstTextValue(author.sec_uid, author.sec_user_id);
  const displayId = uniqueId || uid || secUid;
  const followerCount = firstPositiveNumberValue(
    ...authorSources.flatMap((source) => [source.follower_count, source.fans_count, source.followers]),
    resolveCommonFlagsFollowerCount(author, taskVideo),
  );
  return {
    ...author,
    avatar,
    uid,
    unique_id: uniqueId,
    sec_uid: secUid,
    display_id: displayId,
    nickname: firstTextValue(author.nickname, author.name, author.author_name, author.user_name, uniqueId, uid),
    signature: firstTextValue(author.signature, author.desc, author.intro, author.bio),
    follower_count: followerCount,
    following_count: firstPositiveNumberValue(...authorSources.flatMap((source) => [source.following_count, source.following, source.follow_count])),
    like_count: firstPositiveNumberValue(...authorSources.flatMap((source) => [source.like_count, source.total_favorited, source.total_favorite, source.digg_count])),
    aweme_count: firstPositiveNumberValue(...authorSources.flatMap((source) => [source.aweme_count, source.video_count, source.item_count])),
    verified: Boolean(author.verified || author.is_verified || author.custom_verify || author.enterprise_verify_reason),
  };
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

function formatTimeLabel(value) {
  if (!value) return "未返回发布时间";
  if (typeof value === "number") {
    const date = new Date(value * 1000);
    return Number.isFinite(date.getTime()) ? date.toLocaleString("zh-CN") : String(value);
  }
  const text = String(value).trim();
  if (!text) return "未返回发布时间";
  const numeric = Number(text);
  if (Number.isFinite(numeric) && numeric > 1e9) {
    const date = new Date(numeric * 1000);
    if (Number.isFinite(date.getTime())) return date.toLocaleString("zh-CN");
  }
  return text;
}

function buildTopMetaTags({ genre, result, evidence, author, video }) {
  return normalizeTagList(
    [
      genre,
      result.content_identity?.track,
      result.content_identity?.niche_fit,
      result.content_identity?.account_persona,
      result.copywriting_formula?.title_formula,
      result.replication_plan?.pattern_name,
      result.market_positioning?.creative_direction,
      author.verified ? "已认证" : "",
      video.music_title,
      video.desc,
      evidence.transcript_provider,
    ],
    result.tags,
    video.tags,
    video.topic_tags,
    video.hashtags,
    author.tags,
    result.douyin_target?.keywords,
  ).slice(0, 8);
}

function InfoPill({ label, value, tone = "neutral" }) {
  return (
    <div className={`content-lab-info-pill ${tone}`}>
      <span>{label}</span>
      <strong>{value || EMPTY_TEXT}</strong>
    </div>
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

function VideoTranscriptSyncPanel({ videoRef, videoUrl, posterUrl, transcriptLines, activeTranscriptId, evidenceStatus, onSeek }) {
  return (
    <section className="analysis-section content-lab-video-sync">
      <div className="content-lab-section-head">
        <strong>原视频同步拆解</strong>
        <span className="content-lab-sync-count">{transcriptLines.length ? `${transcriptLines.length} 条转写` : "暂无转写片段"}</span>
      </div>
      <div className="content-lab-video-sync-grid">
        <div className="content-lab-video-frame">
          {videoUrl ? (
            <video ref={videoRef} src={videoUrl} poster={posterUrl || undefined} controls preload="metadata" playsInline />
          ) : (
            <div className="content-lab-video-empty">
              <Play size={32} />
              <p>{evidenceStatus.loading ? "正在读取证据视频..." : "暂无可播放视频"}</p>
            </div>
          )}
        </div>
        <div className="content-lab-transcript-panel">
          <div className="content-lab-transcript-head">
            <span>语音转文字</span>
            {evidenceStatus.error && <small>证据读取失败：{evidenceStatus.error}</small>}
          </div>
          <div className="content-lab-transcript-list">
            {transcriptLines.length ? (
              transcriptLines.map((line, index) => {
                const isActive = String(activeTranscriptId) === String(line.id);
                return (
                  <button
                    className={`content-lab-transcript-line ${isActive ? "active" : ""}`}
                    type="button"
                    key={`${line.id}-${index}`}
                    onClick={() => onSeek(line)}
                  >
                    <span>{secondsToLabel(line.start)}</span>
                    <p>{line.text}</p>
                  </button>
                );
              })
            ) : (
              <p className="field-hint">{evidenceStatus.loading ? "正在读取完整 ASR 文本..." : "暂无完整转写文本"}</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function SegmentTimeline({ segments, onSeek, activeTranscriptId }) {
  if (!segments.length) return null;
  return (
    <div className="analysis-section content-lab-timeline">
      <strong>多模态双轨时间线</strong>
      <div className="content-lab-timeline-list">
        {segments.map((segment, index) => (
          <article
            className={`content-lab-timeline-item ${segment.transcript ? "has-transcript" : ""}`}
            key={segment.id || segment.segment_id || index}
          >
            <div className="content-lab-time-mark">
              <button
                className="content-lab-time-jump"
                type="button"
                onClick={() => onSeek?.(segment)}
              >
                {segment.time_range || secondsToLabel(segment.start) || `片段 ${index + 1}`}
              </button>
              <strong>{segment.segment_role || "未标注"}</strong>
            </div>
            {segment.transcript && (
              <div className="content-lab-track content-lab-track-wide">
                <span>语音转文字</span>
                <button
                  className={`content-lab-segment-transcript ${String(activeTranscriptId) === String(segment.id || segment.segment_id) ? "active" : ""}`}
                  type="button"
                  onClick={() => onSeek?.(segment)}
                >
                  {segment.transcript}
                </button>
              </div>
            )}
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

export function AnalysisResultModal({ task, onClose, pageMode = false }) {
  const videoRef = useRef(null);
  const [actionStatus, setActionStatus] = useState("");
  const [pendingAction, setPendingAction] = useState("");
  const [targetGenre, setTargetGenre] = useState("beauty");
  const [liveInteractions, setLiveInteractions] = useState(null);
  const [liveInteractionStatus, setLiveInteractionStatus] = useState({ loading: false, error: "" });
  const [evidenceDataset, setEvidenceDataset] = useState(null);
  const [evidenceStatus, setEvidenceStatus] = useState({ loading: false, error: "" });
  const [activeTranscriptId, setActiveTranscriptId] = useState("");

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
  const segmentBreakdowns = useMemo(
    () => mergeSegmentBreakdowns(result.segment_breakdowns, evidenceDataset?.analysis_segments),
    [result.segment_breakdowns, evidenceDataset?.analysis_segments],
  );
  const transcriptLines = useMemo(
    () => buildTranscriptLines({ evidenceDataset, result, segmentBreakdowns }),
    [evidenceDataset, result, segmentBreakdowns],
  );
  const videoUrl = useMemo(() => resolveSourceVideoUrl(task, evidenceDataset), [task, evidenceDataset]);
  const posterUrl = useMemo(() => resolvePosterUrl(task), [task]);
  const radarItems = useMemo(() => buildRadarItems(result), [result]);
  const genre = result.content_identity?.track || result.genre || "泛赛道";
  const taskVideo = task?.video || task?.payload?.video || task?.raw?.video || {};
  const author = resolveAuthorProfile(task, taskVideo, result);
  const videoInfo = mergeFilledObject(taskVideo, result.video);
  const topMetaTags = useMemo(() => buildTopMetaTags({ genre, result, evidence, author, video: videoInfo }), [genre, result, evidence, author, videoInfo]);
  const topMetaStats = useMemo(
    () => [
      { label: "点赞", value: compactNumber(task?.video?.statistics?.digg_count || result?.douyin_target?.metrics?.digg_count || videoInfo.digg_count) },
      { label: "评论", value: compactNumber(task?.video?.statistics?.comment_count || result?.douyin_target?.metrics?.comment_count || videoInfo.comment_count) },
      { label: "收藏", value: compactNumber(task?.video?.statistics?.collect_count || result?.douyin_target?.metrics?.collect_count || videoInfo.collect_count) },
      { label: "分享", value: compactNumber(task?.video?.statistics?.share_count || result?.douyin_target?.metrics?.share_count || videoInfo.share_count) },
      { label: "粉丝量", value: author.follower_count == null ? "未返回" : compactNumber(author.follower_count) },
      { label: "获赞", value: compactNumber(author.like_count) },
    ],
    [task, result, videoInfo, author],
  );
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

  function stopTranscriptVideo(unload = false) {
    const video = videoRef.current;
    if (!video) return;
    try {
      video.pause?.();
      if (unload) {
        video.removeAttribute("src");
        video.load?.();
      }
    } catch {
      // Ignore teardown failures during modal close or task switch.
    }
  }

  useEffect(() => {
    let cancelled = false;
    setEvidenceDataset(null);
    setEvidenceStatus({ loading: false, error: "" });
    setActiveTranscriptId("");
    if (!task?.id) return () => {
      cancelled = true;
    };
    setEvidenceStatus({ loading: true, error: "" });
    fetchAiVideoEvidence(task.id)
      .then((dataset) => {
        if (!cancelled) {
          setEvidenceDataset(dataset);
          setEvidenceStatus({ loading: false, error: "" });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setEvidenceStatus({ loading: false, error: err?.message || String(err) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [task?.id]);

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

  useEffect(() => {
    return () => {
      stopTranscriptVideo(true);
    };
  }, [task?.id]);

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

  function handleSeekTranscript(item) {
    const seconds = seekStartSeconds(item);
    if (!Number.isFinite(seconds) || seconds < 0) return;
    setActiveTranscriptId(item?.id || item?.segment_id || `${seconds}`);
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    const playPromise = video.play?.();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch(() => {
        // Some browsers may briefly reject during seek; keep the jump and let the user resume manually.
      });
    }
  }

  function handleClose() {
    stopTranscriptVideo(true);
    onClose?.();
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
  const isPageMode = Boolean(pageMode);

  if (!task) return null;

  return (
    <div className={isPageMode ? "result-page-host" : "modal-backdrop content-lab-backdrop"} role={isPageMode ? undefined : "presentation"} onClick={isPageMode ? undefined : handleClose}>
      <section
        className={`modal-panel content-lab-modal ${isPageMode ? "result-page-panel" : ""}`}
        role={isPageMode ? "region" : "dialog"}
        aria-modal={isPageMode ? undefined : true}
        onClick={isPageMode ? undefined : (event) => event.stopPropagation()}
      >
        <div className="panel-header content-lab-header">
          <div>
            <span className="content-lab-kicker">全赛道内容实验室</span>
            <h2>AI 视频拆解结果</h2>
            <p>{task.title}</p>
          </div>
          <button className="text-button" type="button" onClick={handleClose}>
            {isPageMode ? "返回列表" : "关闭"}
          </button>
        </div>
        <div className="analysis-result-body content-lab-body">
          <section className="content-lab-overview">
            <div className="content-lab-summary">
              <span>{genre}</span>
              <p>{result.summary || "暂无摘要"}</p>
              {(result.analysis_mode || evidence.evidence_path) && (
                <small>
                  {result.analysis_mode || "evidence"} · {(evidence.transcript_provider || "未知转写器")} · {evidence.analysis_segments_count || segmentBreakdowns.length || 0} 个分析片段 · {evidence.keyframes_count || 0} 张关键帧
                </small>
              )}
              <div className="content-lab-summary-lower">
                <div className="content-lab-summary-lower-left">
                  <div className="content-lab-profile-author">
                    {author.avatar ? (
                      <img className="content-lab-profile-avatar" src={author.avatar} alt="作者头像" />
                    ) : (
                      <div className="content-lab-profile-avatar placeholder">{(author.nickname || task?.title || "A").slice(0, 1)}</div>
                    )}
                    <div>
                      <strong>{author.nickname || task?.title || "未返回作者信息"}</strong>
                      <p>账号标识：{author.display_id || author.unique_id || author.uid || author.sec_uid || "未返回"}</p>
                      <span>简介：{author.signature || "暂无简介"}</span>
                    </div>
                  </div>
                  <div className="content-lab-profile-meta">
                    <InfoPill label="赛道" value={genre} tone="blue" />
                    <InfoPill label="发布时间" value={formatTimeLabel(videoInfo.create_time || taskVideo?.create_time)} />
                    <InfoPill label="作品ID" value={videoInfo.aweme_id || taskVideo?.aweme_id || "未返回"} />
                    <InfoPill label="作品时长" value={videoInfo.duration ? `${videoInfo.duration}s` : "未返回"} />
                    <InfoPill label="粉丝量" value={author.follower_count == null ? "未返回" : compactNumber(author.follower_count)} />
                    <InfoPill label="作者获赞" value={author.like_count == null ? "未返回" : compactNumber(author.like_count)} />
                  </div>
                  <div className="content-lab-profile-tags">
                    {topMetaTags.length ? topMetaTags.map((tag) => <Badge key={tag}>{tag}</Badge>) : <span className="field-hint">暂无标签数据</span>}
                  </div>
                  <div className="content-lab-profile-stats">
                    {topMetaStats.map((item) => (
                      <InfoPill key={item.label} label={item.label} value={item.value} />
                    ))}
                  </div>
                </div>
              </div>
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

          <VideoTranscriptSyncPanel
            videoRef={videoRef}
            videoUrl={videoUrl}
            posterUrl={posterUrl}
            transcriptLines={transcriptLines}
            activeTranscriptId={activeTranscriptId}
            evidenceStatus={evidenceStatus}
            onSeek={handleSeekTranscript}
          />

          <SegmentTimeline segments={segmentBreakdowns} onSeek={handleSeekTranscript} activeTranscriptId={activeTranscriptId} />

          <div className="content-lab-workspace">
            <CommentIntelligence snapshot={interactionSnapshot} loading={liveInteractionStatus.loading} error={liveInteractionStatus.error} />
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
          </div>

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
