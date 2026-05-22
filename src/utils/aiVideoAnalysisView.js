import { normalizeCommercialAnalysisResult, normalizeTagList } from "./appUtils";

const EMPTY_TEXT = "暂无内容";

export function formatValue(value) {
  if (Array.isArray(value)) return value.filter(Boolean).join("，");
  if (value && typeof value === "object") {
    if (typeof value.text === "string") return value.text;
    return JSON.stringify(value, null, 2);
  }
  return value || EMPTY_TEXT;
}

export function actionableText(value) {
  const text = formatValue(value).trim();
  return text && text !== EMPTY_TEXT ? text : "";
}

export function sanitizeFileName(value) {
  return String(value || "ai-video-remake-lab")
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, "-")
    .slice(0, 80);
}

export function secondsToLabel(value) {
  const seconds = Math.max(0, Number(value || 0));
  if (!Number.isFinite(seconds)) return "00:00";
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  const base = `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  return hours ? `${String(hours).padStart(2, "0")}:${base}` : base;
}

export function firstTextValue(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
    if (value != null && typeof value !== "object") return String(value);
  }
  return "";
}

export function firstUrlValue(...values) {
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

export function firstNumberValue(...values) {
  let fallback = null;
  for (const value of values) {
    if (value === null || value === undefined || value === "") continue;
    const number = Number(value);
    if (!Number.isFinite(number)) continue;
    if (number > 0) return number;
    if (fallback === null) fallback = number;
  }
  return fallback;
}

export function proxiedDouyinMediaUrl(url) {
  if (!url) return "";
  if (/^\/api\//.test(url) || url.startsWith("blob:") || url.startsWith("data:")) return url;
  return `/api/media/proxy?url=${encodeURIComponent(url)}&referer=${encodeURIComponent("https://www.douyin.com/")}`;
}

export function resolveSourceVideoUrl(task, evidenceDataset) {
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

export function resolvePosterUrl(task) {
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

export function parseTimeToSeconds(value) {
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

export function seekStartSeconds(item) {
  const value = item?.start ?? item?.start_seconds ?? item?.startTime ?? item?.time ?? item?.time_label ?? item?.time_range;
  const seconds = typeof value === "string" ? parseTimeToSeconds(value) : Number(value || 0);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : 0;
}

export function mergeFilledObject(...sources) {
  const result = {};
  for (const source of sources) {
    if (!source || typeof source !== "object" || Array.isArray(source)) continue;
    for (const [key, value] of Object.entries(source)) {
      if (value === undefined || value === null || value === "") continue;
      const current = result[key];
      if (Array.isArray(value)) {
        if (!Array.isArray(current) || !current.length) {
          result[key] = value;
        }
        continue;
      }
      if (value && typeof value === "object") {
        if (!current || typeof current !== "object" || Array.isArray(current) || !Object.keys(current).length) {
          result[key] = value;
        }
        continue;
      }
      if (current === undefined || current === null || current === "") {
        result[key] = value;
      } else if (Number(current) <= 0 && Number(value) > 0) {
        result[key] = value;
      }
    }
  }
  return result;
}

function topEntries(source, limit = 6) {
  if (!source || typeof source !== "object") return [];
  return Object.entries(source)
    .map(([label, value]) => [label, Number(value || 0)])
    .filter(([, value]) => value > 0)
    .sort((left, right) => right[1] - left[1])
    .slice(0, limit);
}

function sortTopComments(comments, limit = 8) {
  if (!Array.isArray(comments)) return [];
  return comments
    .map((comment) => ({
      ...comment,
      text: firstTextValue(comment?.text, comment?.content, comment?.comment),
      nickname: firstTextValue(comment?.nickname, comment?.unique_id, comment?.user_name),
      digg_count: Number(comment?.digg_count || comment?.like_count || 0),
      reply_count: Number(comment?.reply_count || comment?.replies_count || 0),
    }))
    .filter((comment) => comment.text)
    .filter((comment, index, normalized) => {
      const identity = commentIdentity(comment);
      return normalized.findIndex((item) => commentIdentity(item) === identity) === index;
    })
    .sort((left, right) => right.digg_count - left.digg_count || right.reply_count - left.reply_count)
    .slice(0, limit);
}

function mergeLikeCountComments(comments, limit = 8) {
  return sortTopComments(comments, limit);
}

function compactCommentText(value) {
  return String(value || "").replace(/\s+/g, "").trim();
}

function commentIdentity(comment) {
  const id = firstTextValue(comment?.comment_id, comment?.cid, comment?.id);
  if (id) return `id:${id}`;
  const text = compactCommentText(comment?.text || comment?.content || comment?.comment);
  const author = compactCommentText(comment?.user_id || comment?.sec_uid || comment?.unique_id || comment?.nickname || comment?.user_name);
  return author && text ? `author_text:${author}:${text.slice(0, 200)}` : `text:${text.slice(0, 200)}`;
}

export function buildRemakeItems(result) {
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

export function buildRemakeMarkdown({ result, title, genre, targetGenre }) {
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

export function radarConclusion(items, genre) {
  const sorted = [...items].sort((a, b) => b[1] - a[1]);
  const [first, second] = sorted;
  if (!first || first[1] <= 0) return `${genre || "泛赛道"}样本，等待更多指标形成画像`;
  return `${genre || "泛赛道"}样本偏向${first[0]}，其次是${second?.[0] || "其他"}，适合优先拆结构`;
}

export function buildRadarItems(result) {
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

export function buildSummaryStats({ result, evidence, segmentCount, modelRunCount }) {
  const scores = result.viral_scores || {};
  const overall = Math.max(0, Math.min(100, Math.round(scores.overall || scores.viral_potential || 0)));
  return [
    ["分析模式", result.analysis_mode || (evidence.evidence_path ? "evidence" : "direct")],
    ["综合评分", overall ? `${overall} / 100` : "暂无"],
    ["分段数量", `${segmentCount || 0} 段`],
    ["关键帧", `${evidence.keyframes_count || 0} 张`],
    ["模型调用", `${modelRunCount || 0} 次`],
    ["证据文件", evidence.evidence_path ? "已生成" : "暂无"],
  ];
}

export function buildEvidenceRows({ result, evidence, segmentCount, modelRunCount }) {
  return [
    ["分析模式", result.analysis_mode || "evidence"],
    ["转写器", evidence.transcript_provider || "暂无"],
    ["证据路径", evidence.evidence_path || "暂无"],
    ["分段数量", `${evidence.analysis_segments_count || segmentCount || 0} 段`],
    ["关键帧数量", `${evidence.keyframes_count || 0} 张`],
    ["模型调用", `${modelRunCount || 0} 次`],
  ];
}

export function buildTopMetaTags({ genre, result, evidence, author, video }) {
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

export function resolveTargetVideoId(task, result) {
  const video = task?.video || task?.payload?.video || {};
  return firstTextValue(
    result?.douyin_target?.video_id,
    result?.douyin_target?.aweme_id,
    video?.douyin_target_context?.video_id,
    video?.aweme_id,
    video?.id,
  );
}

export function buildInteractionSnapshot(snapshot, liveDataset) {
  const base = snapshot && typeof snapshot === "object" ? snapshot : {};
  const live = liveDataset && typeof liveDataset === "object" ? liveDataset : {};
  const comments = Array.isArray(live.comments) ? live.comments : Array.isArray(live.items) ? live.items : [];
  const insights = live.insights || {};
  const topFromComments = mergeLikeCountComments(comments.filter((item) => Number(item?.level || 1) === 1), 8);
  return {
    comment_saved_count: base.comment_saved_count || insights.comment_count_saved || live.comment_count || 0,
    reply_saved_count: base.reply_saved_count || insights.reply_count_saved || live.reply_count || 0,
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

export function resolveAuthorProfile(task, taskVideo, result) {
  const rawAuthor = mergeFilledObject(
    task?.author,
    task?.payload?.author,
    task?.payload?.douyin_target?.author,
    task?.payload?.douyin_target?.user,
    taskVideo?.author,
    result?.author,
    result?.douyin_target?.author,
    result?.douyin_target?.user,
    result?.video?.author,
    result?.raw_model_json?.author,
    result?.raw_model_json?.douyin_target?.author,
  );
  const author = mergeFilledObject(
    rawAuthor,
    task?.payload?.author,
    task?.payload?.douyin_target?.author,
    task?.payload?.douyin_target?.user,
    taskVideo?.author,
    taskVideo?.raw?.author,
    result?.author,
    result?.douyin_target?.author,
    result?.douyin_target?.user,
    result?.video?.author,
    result?.raw_model_json?.author,
    result?.raw_model_json?.douyin_target?.author,
  );
  const uid = firstTextValue(author.uid, author.user_id, author.id, taskVideo?.author_user_id, taskVideo?.raw?.author_user_id);
  const uniqueId = firstTextValue(author.unique_id, author.uniqueId, author.short_id, author.display_id, author.search_user_name);
  const secUid = firstTextValue(author.sec_uid, author.sec_user_id);
  const followerCount = firstNumberValue(author.follower_count, author.fans_count, author.followers_count);
  const followingCount = firstNumberValue(author.following_count, author.follow_count);
  const likeCount = firstNumberValue(author.like_count, author.total_favorited, author.total_favorite, author.digg_count);
  const awemeCount = firstNumberValue(author.aweme_count, author.video_count, author.item_count);
  return {
    uid,
    sec_uid: secUid,
    unique_id: uniqueId || uid || secUid,
    display_id: firstTextValue(author.display_id, uniqueId, uid),
    nickname: firstTextValue(author.nickname, author.name, author.author_name, author.user_name, uniqueId, uid),
    signature: firstTextValue(author.signature, author.desc, author.intro, author.bio),
    ip_location: firstTextValue(author.ip_location, author.ipLocation, author.location),
    avatar: firstTextValue(author.avatar, author.avatar_url, author.avatar_thumb, author.avatar_larger),
    follower_count: followerCount,
    following_count: followingCount,
    like_count: likeCount,
    total_favorited: likeCount,
    aweme_count: awemeCount,
    verified: Boolean(author.verified || author.is_verified),
    tags: author.tags || author.keywords || [],
  };
}

export function formatTimeLabel(value) {
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

export function mergeSegmentBreakdowns(resultSegments, evidenceSegments) {
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

export function normalizeTranscriptItem(item, index = 0) {
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

export function buildTranscriptLines({ evidenceDataset, result, segmentBreakdowns }) {
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
      start: Number(segment.start || 0),
      end: segment.end,
      text: segment.transcript || segment.segment_text || segment.summary,
    }, index))
    .filter((item) => item.text);
}

export function normalizeAnalysisResult(source) {
  return normalizeCommercialAnalysisResult(source);
}

export function getCommentKeywords(snapshot) {
  return topEntries(snapshot?.keyword_counts, 8);
}

export function getCommentMotivations(snapshot) {
  const emotion = snapshot?.emotion_profile || {};
  const motivation = emotion.motivation_buckets || emotion.buckets || {};
  return topEntries(motivation, 6);
}
