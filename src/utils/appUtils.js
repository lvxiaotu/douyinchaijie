import { API_BASE, taskBoardStatuses } from "../constants/appConfig";

export function generationModeLabel(mode) {
  if (mode === "skill_contract" || mode === "sdk") {
    return "Skill 规则";
  }
  return "本地";
}

export function normalizeOptionalText(value) {
  return cleanScriptValue(value).trim();
}

export function deriveBgmKeywords(script) {
  return normalizeOptionalText(script?.bible?.bgm_keywords || script?.config?.genre || "");
}

export function deriveOptionalWorkflowFlags(script) {
  const bible = script?.bible || {};
  return {
    hasBgm: Boolean(normalizeOptionalText(bible.bgm_keywords)),
    hasVoice: Boolean(normalizeOptionalText(bible.voice_vibe)),
    hasVisualStyle: Boolean(normalizeOptionalText(bible.art_style_prompt)),
    hasOnscreenText: Boolean((script?.scenes || []).some((scene) => normalizeOptionalText(scene?.onscreen_text))),
    hasNarration: Boolean((script?.scenes || []).some((scene) => normalizeOptionalText(scene?.audio_narration || scene?.narration))),
  };
}

export function createScriptFallbackBible(script) {
  const title = script?.config?.title || "未命名剧本";
  const genre = script?.config?.genre || "短视频";
  return {
    art_style_prompt: `${genre}, clean short-video visual style, readable framing, cinematic lighting`,
    character_base_prompt: `${title} 的核心角色特征，保持镜头间一致`,
    voice_vibe: "自然、清晰、稳定的中文旁白",
    bgm_keywords: `${genre}, emotional, cinematic, uplifting`,
  };
}

export function sdkResultData(result) {
  return result?.data?.data || {};
}

export function sdkResultReason(result) {
  return result?.data?.reason || result?.error || "";
}

export function firstUrl(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return firstUrl(value[0]);
  if (Array.isArray(value.url_list)) return value.url_list[0] || "";
  return "";
}

export function compactNumber(value) {
  if (value === undefined || value === null || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return value;
  if (number >= 10000) return `${(number / 10000).toFixed(1)}万`;
  return String(number);
}

export function unwrapDouyinData(value) {
  return value?.raw?.data || value?.data || value?.raw || value;
}

export function cleanScriptValue(value) {
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

export function sceneDuration(scene, fallback = 3) {
  const value = Number(scene?.estimated_duration || scene?.assets?.duration || 0);
  return value > 0 ? value : fallback;
}

export function sceneSummary(scene) {
  return safeSlice(cleanScriptValue(scene?.summary || scene?.visual_prompt || scene?.audio_narration || scene?.narration), 42) || "未填写内容概括";
}

export function formatTimelineMark(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return "0s";
  const rounded = Number.isInteger(seconds) ? seconds : seconds.toFixed(1);
  return `${rounded}s`;
}

export function createDateDraftName(date = new Date()) {
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日${date.getHours()}时${date.getMinutes()}分`;
}

export function objectEntries(value) {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value);
}

export function buildMaterialIndex(materials) {
  const index = {};
  for (const [group, items] of objectEntries(materials)) {
    if (!Array.isArray(items)) continue;
    for (const item of items) {
      if (item?.id) index[item.id] = { ...item, group };
    }
  }
  return index;
}

export function flattenDraftSegments(tracks, materialIndex) {
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

export function materialTitle(item, index) {
  return item.name || item.material_name || item.type || `素材 ${index + 1}`;
}

export function materialSubtitle(item) {
  return materialPreview(item) || item.path || item.resource_id || item.type || "-";
}

export function materialPreview(item) {
  if (!item || typeof item !== "object") return "";
  const text = extractTextMaterial(item);
  if (text) return text;
  return item.path || item.name || item.material_name || item.resource_id || item.effect_id || "";
}

export function safeSlice(value, length) {
  return typeof value === "string" ? value.slice(0, length) : String(value || "").slice(0, length);
}

export function extractTextMaterial(item) {
  if (typeof item.content !== "string") return "";
  try {
    const parsed = JSON.parse(item.content);
    return parsed.text || "";
  } catch {
    return safeSlice(item.content, 120);
  }
}

export function formatMicroseconds(value) {
  const microseconds = Number(value || 0);
  if (!Number.isFinite(microseconds) || microseconds <= 0) return "0s";
  return `${(microseconds / 1_000_000).toFixed(2)}s`;
}

export function formatCanvasSize(canvas) {
  if (!canvas || typeof canvas !== "object") return "-";
  const width = canvas.width || canvas.canvas_width;
  const height = canvas.height || canvas.canvas_height;
  return width && height ? `${width} x ${height}` : "-";
}

export function formatDuration(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return "-";
  return `${seconds}s`;
}

export function formatTimestamp(value) {
  const timestamp = Number(value);
  if (!Number.isFinite(timestamp)) return "-";
  return new Date(timestamp * 1000).toLocaleString();
}

export function videoTitle(video) {
  return video?.desc || video?.title || video?.aweme_id || video?.id || "未命名视频";
}

export function parseJsonString(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

export function firstText(source, keys) {
  if (!source || typeof source !== "object") return "";
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string") return value.trim();
    if (Array.isArray(value)) return value.map((item) => (typeof item === "string" ? item : JSON.stringify(item))).join("\n");
    if (value != null && typeof value !== "object") return String(value);
  }
  return "";
}

export function firstObject(source, keys) {
  if (!source || typeof source !== "object") return {};
  for (const key of keys) {
    const value = source[key];
    if (value && typeof value === "object" && !Array.isArray(value)) return value;
  }
  return {};
}

export function firstNumber(source, keys) {
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

export function firstArray(source, keys) {
  if (!source || typeof source !== "object") return [];
  for (const key of keys) {
    const value = source[key];
    if (Array.isArray(value)) return value;
    if (typeof value === "string" && value.trim()) {
      return value
        .split(/\n|；|;|、/)
        .map((item) => item.trim())
        .filter(Boolean);
    }
  }
  return [];
}

export function firstUrlFromObject(source, keys) {
  if (!source || typeof source !== "object") return "";
  for (const key of keys) {
    const value = source[key];
    const url = firstUrl(value);
    if (url) return url;
  }
  return "";
}

export function normalizeTagList(...sources) {
  const tags = [];
  const seen = new Set();
  for (const source of sources) {
    const values = Array.isArray(source)
      ? source
      : typeof source === "string"
        ? source.split(/[,，、/|]/)
        : source && typeof source === "object"
          ? [
              source.tags,
              source.keywords,
              source.hashtags,
              source.topic_tags,
              source.topic_list,
              source.aweme_text_extra,
            ]
          : [];
    for (const value of values.flat?.() || values) {
      const text = typeof value === "string"
        ? value.trim()
        : value && typeof value === "object"
          ? (value.name || value.keyword || value.text || value.tag_name || value.challenge_name || value.hashtag_name || "").trim?.() || ""
          : "";
      const cleaned = text.replace(/^#/, "").trim();
      if (!cleaned || seen.has(cleaned.toLowerCase())) continue;
      seen.add(cleaned.toLowerCase());
      tags.push(cleaned);
      if (tags.length >= 12) break;
    }
    if (tags.length >= 12) break;
  }
  return tags;
}

export function normalizeCommercialAnalysisResult(source) {
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
  const douyinTarget = firstObject(raw, ["douyin_target", "douyin_target_context", "抖音数据"]);
  const interactionSnapshot = firstObject(douyinTarget, ["interaction_snapshot", "interaction", "互动快照"]);
  const targetMetrics = firstObject(douyinTarget, ["metrics", "指标"]);
  const rawSegments = Array.isArray(raw?.segment_breakdowns) ? raw.segment_breakdowns : [];
  const authorSource = firstObject(raw, ["author", "user", "owner", "作者", "博主", "account", "profile"]);
  const videoSource = firstObject(raw, ["video", "video_data", "aweme", "作品", "视频"]);
  const mediaTags = normalizeTagList(
    raw?.tags,
    raw?.keywords,
    raw?.topic_tags,
    raw?.topic_list,
    authorSource,
    videoSource,
    douyinTarget,
  );

  return {
    analysis_mode: firstText(raw, ["analysis_mode"]),
    pipeline_error: firstText(raw, ["pipeline_error"]),
    evidence: raw?.evidence && typeof raw.evidence === "object" && !Array.isArray(raw.evidence) ? raw.evidence : {},
    genre: firstText(raw, ["genre", "赛道", "内容赛道"]) || firstText(contentIdentity, ["track", "内容赛道", "赛道"]),
    summary: firstText(raw, ["summary", "摘要", "视频摘要", "一句话摘要"]),
    author: {
      nickname: firstText(authorSource, ["nickname", "name", "author_name", "unique_id", "user_name", "username", "sec_nickname"]),
      unique_id: firstText(authorSource, ["unique_id", "user_id", "uid", "sec_uid", "sec_user_id"]),
      signature: firstText(authorSource, ["signature", "desc", "intro", "bio"]),
      avatar: firstUrlFromObject(authorSource, ["avatar", "avatar_url", "avatar_larger", "avatar_thumb", "avatar_300x300", "avatar_medium"]),
      follower_count: Number(firstText(authorSource, ["follower_count", "fans_count", "粉丝数"]) || 0),
      following_count: Number(firstText(authorSource, ["following_count", "关注数"]) || 0),
      like_count: Number(firstText(authorSource, ["like_count", "total_favorited", "获赞"]) || 0),
      aweme_count: Number(firstText(authorSource, ["aweme_count", "作品数", "video_count"]) || 0),
      verified: Boolean(authorSource?.verified || authorSource?.is_verified),
    },
    video: {
      aweme_id: firstText(videoSource, ["aweme_id", "id", "video_id", "item_id"]),
      desc: firstText(videoSource, ["desc", "title", "text", "content", "video_desc"]),
      create_time: firstText(videoSource, ["create_time", "created_at", "publish_time", "发布时间"]),
      duration: firstText(videoSource, ["duration", "duration_seconds", "video_duration"]),
      music_title: firstText(videoSource, ["music_title", "music_name", "bgm", "song_title"]),
      share_url: firstText(videoSource, ["share_url", "share_link", "url"]),
      cover: firstUrlFromObject(videoSource, ["cover", "cover_url", "origin_cover", "dynamic_cover"]),
      play_url: firstUrlFromObject(videoSource, ["play_addr", "download_addr", "play_url", "video_url"]),
    },
    tags: mediaTags,
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
      cross_genre_variants: firstText(replicationPlan, ["cross_genre_variants", "跨赛道改写", "跨赛道变体"]),
      mysticism_variant: firstText(replicationPlan, ["mysticism_variant", "玄学方向", "玄学改编"]),
      ai_pet_variant: firstText(replicationPlan, ["ai_pet_variant", "AI小动物方向", "小动物改编"]),
      ai_commerce_variant: firstText(replicationPlan, ["ai_commerce_variant", "AI带货方向", "带货改编"]),
      difficulty: firstText(replicationPlan, ["difficulty", "制作难度", "难度"]),
      priority: firstText(replicationPlan, ["priority", "优先级", "模仿优先级"]),
    },
    standard_remake_template: firstText(raw, ["standard_remake_template", "通用复刻脚本模板", "复刻脚本模板", "脱敏脚本模板"]),
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
    douyin_target: {
      metrics: targetMetrics,
      interaction_snapshot: interactionSnapshot,
      keyword_counts: firstObject(interactionSnapshot, ["keyword_counts", "关键词"]),
      symbol_counts: firstObject(interactionSnapshot, ["symbol_counts", "符号"]),
      emotion_profile: firstObject(interactionSnapshot, ["emotion_profile", "评论情绪"]),
      creator_reply_tactics: firstObject(interactionSnapshot, ["creator_reply_tactics", "作者回复策略"]),
      top_comments: firstArray(interactionSnapshot, ["top_comments", "热门评论"]),
      pinned_comments: firstArray(interactionSnapshot, ["pinned_comments", "置顶评论"]),
      author_replies: firstArray(interactionSnapshot, ["author_replies", "作者回复"]),
    },
    segment_breakdowns: rawSegments.map((segment, index) => ({
      ...segment,
      id: segment?.segment_id || `segment-${index + 1}`,
      segment_id: segment?.segment_id || `seg_${index + 1}`,
      time_range: firstText(segment, ["time_range", "时间范围"]) || `${segment?.start ?? ""}-${segment?.end ?? ""}`,
      segment_role: firstText(segment, ["segment_role", "片段角色"]),
      visual_style: firstText(segment, ["visual_style", "visual_signal", "画面视觉特征"]),
      audio_pacing: firstText(segment, ["audio_pacing", "audio_rhythm", "声音特征"]),
      narrative_technique: firstText(segment, ["narrative_technique", "copywriting_pattern", "叙事技巧"]),
      retention_mechanism: firstText(segment, ["retention_mechanism", "hook", "replicable_point", "留存机制"]),
    })),
    model_runs: Array.isArray(raw?.model_runs) ? raw.model_runs : [],
    raw_model_json: raw?.raw_model_json || raw,
  };
}

export function formatModelRunPurpose(value) {
  const labels = {
    segment_breakdown: "分段视觉拆解",
    global_breakdown: "全局爆款汇总",
  };
  return labels[value] || value || "模型调用";
}

export function formatModelRunStatus(value) {
  if (value === "done") return "完成";
  if (value === "failed") return "失败";
  if (value === "pending") return "等待";
  return value || "-";
}

export function formatModelRunTime(value) {
  const timestamp = Number(value);
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "";
  return new Date(timestamp * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatLatency(value) {
  const latency = Number(value || 0);
  if (!Number.isFinite(latency) || latency <= 0) return "-";
  if (latency >= 1000) return `${(latency / 1000).toFixed(1)}s`;
  return `${Math.round(latency)}ms`;
}

export function normalizeModelRuns(...sources) {
  const source = sources.find((items) => Array.isArray(items) && items.length) || [];
  return source.map((run, index) => {
    const meta = run?.meta && typeof run.meta === "object" ? run.meta : {};
    return {
      ...run,
      id: run?.id || `${run?.purpose || "model"}-${index}`,
      provider: run?.provider || "-",
      model: run?.model || "-",
      purpose: run?.purpose || "",
      purposeLabel: formatModelRunPurpose(run?.purpose),
      status: run?.status || "",
      statusLabel: formatModelRunStatus(run?.status),
      statusClass: run?.status === "failed" ? "error" : run?.status === "done" ? "done" : "running",
      chunkLabel: run?.chunk_id ? `片段 ${run.chunk_id}` : "全局",
      latencyLabel: formatLatency(run?.latency_ms || meta.latency_ms),
      tokenLabel: `${Number(run?.input_tokens || 0)} / ${Number(run?.output_tokens || 0)}`,
      timeLabel: formatModelRunTime(run?.created_at),
      fallbackLabel: meta.fallback_from ? `${meta.fallback_from} -> ${meta.fallback_provider || run?.provider || "-"}` : "",
      fallbackError: meta.fallback_error || "",
      errorMessage: run?.error_message || "",
      action: meta.action || "",
    };
  });
}

export function resolveCommentCollectionState(taskOrResult = {}) {
  const result = taskOrResult?.result && typeof taskOrResult.result === "object" ? taskOrResult.result : taskOrResult;
  const payload = taskOrResult?.payload && typeof taskOrResult.payload === "object" ? taskOrResult.payload : {};
  const video = taskOrResult?.video || payload.video || {};
  const resultState = result?.comment_collection;
  const payloadState = payload?.comment_collection_state;
  const snapshot = result?.douyin_target?.interaction_snapshot || video?.douyin_target_context?.interaction_snapshot || {};
  const state =
    (resultState && typeof resultState === "object" && resultState) ||
    (payloadState && typeof payloadState === "object" && payloadState) ||
    (snapshot && typeof snapshot === "object" && snapshot) ||
    null;
  if (!state) {
    return null;
  }
  const status = state.status || snapshot.status || "";
  return {
    status,
    video_id: state.video_id || result?.douyin_target?.video_id || video?.douyin_target_context?.video_id || "",
    aweme_id: state.aweme_id || result?.douyin_target?.aweme_id || video?.aweme_id || video?.id || "",
    snapshot_at: state.snapshot_at || snapshot.snapshot_at || null,
    comment_saved_count: Number(state.comment_saved_count || snapshot.comment_saved_count || 0),
    reply_saved_count: Number(state.reply_saved_count || snapshot.reply_saved_count || 0),
    error: state.error || snapshot.error || state.reason || "",
  };
}

export function commentCollectionLabel(state) {
  if (!state) return "评论数据：等待 AI 拆解步骤获取";
  if (state.status === "done") {
    return `评论数据：已保存 ${state.comment_saved_count || 0} 条评论 / ${state.reply_saved_count || 0} 条回复`;
  }
  if (state.status === "failed") {
    return `评论数据：获取失败${state.error ? `（${safeSlice(state.error, 80)}）` : ""}`;
  }
  if (state.status === "running") return "评论数据：获取中";
  if (state.status === "skipped") return "评论数据：已跳过";
  return "评论数据：等待获取";
}

export function commentCollectionTone(state) {
  if (!state) return "draft";
  if (state.status === "done") return "done";
  if (state.status === "failed") return "error";
  if (state.status === "running") return "running";
  return "draft";
}

export function normalizeAnalysisTask(task, normalizeResult = normalizeCommercialAnalysisResult) {
  const updated = task.updated_at ? new Date(task.updated_at * 1000) : new Date();
  const result = normalizeResult(task.result?.result || task.result || {});
  const rawResult = task.result?.result || task.result || {};
  const commentCollection = resolveCommentCollectionState({ ...task, result: rawResult });
  const modelRuns = normalizeModelRuns(task.model_runs, task.result?.model_runs, result.model_runs);
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
    commentCollection,
    modelRuns,
    error: task.error,
    events,
  };
}

export function normalizePromptReverseTask(task) {
  return normalizeAnalysisTask(task, (result) => result || {});
}

export function normalizeProductionReverseTask(task) {
  return normalizeAnalysisTask(task, (result) => result || {});
}

export function normalizeRunningHubTtsTask(task) {
  const normalized = normalizeAnalysisTask(task, (result) => result || {});
  const result = normalized.result || {};
  const workflowMeta = result.workflow_meta || {};
  const outputs = result.outputs || {};
  const outputItems = Array.isArray(outputs.results)
    ? outputs.results
    : Array.isArray(outputs.data)
      ? outputs.data
      : Array.isArray(outputs.data?.outputs)
        ? outputs.data.outputs
        : [];
  return {
    ...normalized,
    title:
      (task.payload?.text && task.payload.text.trim().slice(0, 48)) ||
      task.title ||
      "RunningHub TTS",
    workflowId: workflowMeta.workflow_id || task.payload?.workflow_id || "",
    workflowKey: workflowMeta.workflow_key || task.payload?.workflow_key || "",
    remoteTaskId: result.remote_task_id || result.submit?.data?.taskId || result.submit?.taskId || "",
    outputItems,
    resultSummary:
      outputItems[0]?.fileUrl ||
      outputItems[0]?.url ||
      outputItems[0]?.fileName ||
      result.outputs?.message ||
      normalized.message ||
      "",
  };
}

export function normalizeTextToAssetsTask(task) {
  const normalized = normalizeAnalysisTask(task, (result) => result || {});
  const result = normalized.result || {};
  const aRollItems = Array.isArray(result.a_roll_prompts) ? result.a_roll_prompts : [];
  const bRollItems = Array.isArray(result.b_roll_list) ? result.b_roll_list : [];
  const audioPlan = result.audio_plan && typeof result.audio_plan === "object" ? result.audio_plan : {};
  const voiceoverItems = Array.isArray(audioPlan.voiceover) ? audioPlan.voiceover : [];
  const sfxItems = Array.isArray(audioPlan.sfx) ? audioPlan.sfx : [];
  const creativeDirection = result.creative_direction && typeof result.creative_direction === "object" ? result.creative_direction : {};
  const bgmStyle = audioPlan.bgm_style && typeof audioPlan.bgm_style === "object"
    ? audioPlan.bgm_style
    : { genre: audioPlan.bgm_style || "" };
  const notes = Array.isArray(result.notes) ? result.notes : [];

  return {
    ...normalized,
    title:
      task.title ||
      (task.payload?.idea && task.payload.idea.trim().slice(0, 40)) ||
      "一句话转素材",
    idea: task.payload?.idea || "",
    creativeDirection,
    aRollItems,
    bRollItems,
    audioPlan: {
      sfx: sfxItems,
      bgmStyle,
      voiceover: voiceoverItems,
    },
    notes,
    resultSummary:
      result.summary ||
      creativeDirection.positioning ||
      creativeDirection.visual_style ||
      aRollItems[0]?.prompt ||
      normalized.message ||
      "",
  };
}

export function archiveIdSet(archives) {
  return new Set(archives.map((item) => item.task_id || item.id).filter(Boolean));
}

export function groupTasksByStatus(tasks) {
  return {
    running: tasks.filter((task) => !["done", "error"].includes(task.status)),
    done: tasks.filter((task) => task.status === "done"),
    error: tasks.filter((task) => task.status === "error"),
  };
}

export function preferredTaskStatus(groups, currentStatus) {
  if ((groups[currentStatus] || []).length > 0) {
    return currentStatus;
  }
  const fallback = taskBoardStatuses.find(([key]) => (groups[key] || []).length > 0);
  return fallback?.[0] || "running";
}

export function archivePresentation(item) {
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
  if (item.archiveType === "production") {
    const result = item.result || {};
    return {
      toolLabel: "AI 制作方式反推",
      toolDetail: "制作流程归档",
      headline: item.title || "未命名视频",
      summary: result.summary || result.production_overview?.main_workflow || "暂无摘要",
      highlights: [
        ["内容类型", result.production_overview?.content_type],
        ["工具痕迹", Array.isArray(result.production_overview?.tool_signatures) ? result.production_overview.tool_signatures[0] : ""],
        ["模板感", result.production_overview?.template_signature || result.production_overview?.automation_level || result.production_overview?.main_workflow],
      ].filter(([, value]) => value),
      tags: [item.provider, "制作反推"].filter(Boolean),
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

export function renderTextList(value) {
  return Array.isArray(value) && value.length ? value.join(" / ") : "暂无内容";
}

export function buildProductionEvidenceUrl(path) {
  if (!path) return "";
  return `${API_BASE}/api/tools/ai-production-reverse/evidence-file?path=${encodeURIComponent(path)}`;
}

export function normalizeLikelihoods(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      return {
        name: item.name || item.label || "",
        score: typeof item.score === "number" ? item.score : Number.isFinite(Number(item.score)) ? Number(item.score) : null,
        reason: item.reason || item.evidence || "",
      };
    })
    .filter((item) => item?.name);
}
