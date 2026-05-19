const RAW_API_BASE = import.meta.env.VITE_API_BASE || "";
const API_BASE = (() => {
  if (typeof window === "undefined" || !RAW_API_BASE) {
    return RAW_API_BASE;
  }
  try {
    const pageUrl = new URL(window.location.href);
    const apiUrl = new URL(RAW_API_BASE, pageUrl.origin);
    const localHosts = new Set(["127.0.0.1", "localhost"]);
    const viteDevPorts = new Set(["5173", "5174"]);
    if (
      localHosts.has(pageUrl.hostname) &&
      localHosts.has(apiUrl.hostname) &&
      viteDevPorts.has(pageUrl.port) &&
      apiUrl.port === "8010"
    ) {
      return "";
    }
  } catch {
    // Fall back to the configured API base if URL parsing fails.
  }
  return RAW_API_BASE.replace(/\/$/, "");
})();

export async function fetchWorkbench() {
  const response = await fetch(`${API_BASE}/api/workbench`);
  if (!response.ok) {
    throw new Error(`Workbench API failed: ${response.status}`);
  }
  return response.json();
}

async function postJson(path, payload) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message =
      data?.detail?.message ||
      data?.detail?.error ||
      data?.detail ||
      `Request failed: ${response.status}`;
    const hint = data?.detail?.hint ? `\n${data.detail.hint}` : "";
    const errorType = data?.detail?.error_type ? `${data.detail.error_type}: ` : "";
    if (typeof message === "string") {
      throw new Error(`${errorType}${message}${hint}`);
    }
    throw new Error(JSON.stringify(message, null, 2));
  }
  return data;
}

export function fetchDouyinUserProfile(userUrl) {
  return postJson("/api/integrations/douyin/user-profile", { user_url: userUrl });
}

export function fetchDouyinUserVideos({ userUrl, secUserId, maxItems, pageSize, maxCursor }) {
  const payload = {
    page_size: Number(pageSize),
    max_cursor: Number(maxCursor || 0),
  };
  if (userUrl) {
    payload.user_url = userUrl;
  }
  if (secUserId) {
    payload.sec_user_id = secUserId;
  }
  if (maxItems) {
    payload.max_items = Number(maxItems);
  }
  return postJson("/api/integrations/douyin/user-videos", payload);
}

export function fetchDouyinWorkDetail(workUrl) {
  return postJson("/api/integrations/douyin/work-detail", { work_url: workUrl });
}

export function downloadDouyinFavorites({ maxItems, pageSize }) {
  return postJson("/api/integrations/douyin/favorites/download", {
    max_items: Number(maxItems),
    page_size: Number(pageSize),
  });
}

export function fetchDouyinFavoriteItems({ maxItems, pageSize, maxCursor }) {
  const payload = {
    page_size: Number(pageSize),
    max_cursor: Number(maxCursor || 0),
  };
  if (maxItems) {
    payload.max_items = Number(maxItems);
  }
  return postJson("/api/integrations/douyin/favorites/items", payload);
}

export async function fetchDouyinConfig() {
  const response = await fetch(`${API_BASE}/api/integrations/douyin/config`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function saveDouyinConfig(config) {
  return postJson("/api/integrations/douyin/config", {
    api_base: config.apiBase,
    output_dir: config.outputDir,
    cookie: config.cookie,
  });
}

export async function fetchAiProviderConfig() {
  const response = await fetch(`${API_BASE}/api/ai-provider/config`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function saveAiProviderConfig(config) {
  return postJson("/api/ai-provider/config", {
    provider: config.provider,
    access_mode: config.accessMode,
    native_api_key: config.nativeApiKey,
    relay_base_url: config.relayBaseUrl,
    relay_api_key: config.relayApiKey,
    model: config.model,
    local_endpoint: config.localEndpoint,
    api_format: config.apiFormat,
    models: config.models || [],
  });
}

export function testAiProviderConfig(config) {
  return postJson("/api/ai-provider/test", {
    provider: config.provider,
    access_mode: config.accessMode,
    native_api_key: config.nativeApiKey,
    relay_base_url: config.relayBaseUrl,
    relay_api_key: config.relayApiKey,
    model: config.model,
    local_endpoint: config.localEndpoint,
    api_format: config.apiFormat,
    models: config.models || [],
  });
}

export function createAiVideoBreakdownJob(video, provider) {
  const payload = { video };
  if (provider) {
    payload.provider = provider;
  }
  return postJson("/api/tools/ai-video-analysis/jobs", payload);
}

async function patchJson(path, payload) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message =
      data?.detail?.message ||
      data?.detail?.error ||
      data?.detail ||
      `Request failed: ${response.status}`;
    const hint = data?.detail?.hint ? `\n${data.detail.hint}` : "";
    const errorType = data?.detail?.error_type ? `${data.detail.error_type}: ` : "";
    if (typeof message === "string") {
      throw new Error(`${errorType}${message}${hint}`);
    }
    throw new Error(typeof message === "string" ? message : JSON.stringify(message, null, 2));
  }
  return data;
}

export function searchDouyinTargets(payload) {
  return postJson("/api/tools/douyin-target/search", {
    keyword: payload.keyword || "",
    page: Number(payload.page || 1),
    count: Number(payload.count || 20),
    minFollowers: payload.minFollowers !== "" && payload.minFollowers != null ? Number(payload.minFollowers) : undefined,
    maxFollowers: payload.maxFollowers !== "" && payload.maxFollowers != null ? Number(payload.maxFollowers) : undefined,
    minLikes: payload.minLikes !== "" && payload.minLikes != null ? Number(payload.minLikes) : undefined,
    maxLikes: payload.maxLikes !== "" && payload.maxLikes != null ? Number(payload.maxLikes) : undefined,
    minVideos: payload.minVideos !== "" && payload.minVideos != null ? Number(payload.minVideos) : undefined,
    maxVideos: payload.maxVideos !== "" && payload.maxVideos != null ? Number(payload.maxVideos) : undefined,
    recentWithinDays: payload.recentWithinDays !== "" && payload.recentWithinDays != null ? Number(payload.recentWithinDays) : undefined,
    olderThanDays: payload.olderThanDays !== "" && payload.olderThanDays != null ? Number(payload.olderThanDays) : undefined,
    verified: payload.verified || "all",
    privateFilter: payload.privateFilter || "exclude",
    sortBy: payload.sortBy || "relevance",
  });
}

export async function fetchDouyinTargetSets() {
  const response = await fetch(`${API_BASE}/api/tools/douyin-target/sets`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchDouyinTargetSet(setId) {
  const response = await fetch(`${API_BASE}/api/tools/douyin-target/sets/${encodeURIComponent(setId)}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function saveDouyinTargetUsers(payload) {
  return postJson("/api/tools/douyin-target/users/bulk-save", {
    users: payload.users || [],
    set_id: payload.setId || undefined,
    set_name: payload.setName || "",
    note: payload.note || "",
    keyword: payload.keyword || "",
    filters: payload.filters || {},
  });
}

export function createDouyinTargetSet(payload) {
  return postJson("/api/tools/douyin-target/sets", {
    name: payload.name || "",
    note: payload.note || "",
    keyword: payload.keyword || "",
    filters: payload.filters || {},
    video_strategy: payload.videoStrategy || {},
    status: payload.status || "draft",
  });
}

export function updateDouyinTargetSet(setId, payload) {
  return patchJson(`/api/tools/douyin-target/sets/${encodeURIComponent(setId)}`, {
    name: payload.name,
    note: payload.note,
    keyword: payload.keyword,
    filters: payload.filters,
    video_strategy: payload.videoStrategy,
    status: payload.status,
  });
}

export async function deleteDouyinTargetSet(setId) {
  const response = await fetch(`${API_BASE}/api/tools/douyin-target/sets/${encodeURIComponent(setId)}`, {
    method: "DELETE",
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function collectDouyinTargetVideos(payload) {
  return postJson("/api/tools/douyin-target/videos/collect", {
    set_id: payload.setId,
    user_ids: payload.userIds || [],
    strategy: {
      mode: payload.mode || "top",
      per_user_limit: Number(payload.perUserLimit || 5),
      fetch_count: Number(payload.fetchCount || 20),
      sort_metric: payload.sortMetric || "digg_count",
    },
  });
}

export function collectDouyinTargetInteractions(payload) {
  return postJson("/api/tools/douyin-target/comments/collect", {
    set_id: payload.setId || "",
    video_ids: payload.videoIds || [],
    adaptive_by_ratio: payload.adaptiveByRatio !== false,
    max_comments: Number(payload.maxComments || 160),
    min_comments: Number(payload.minComments ?? 30),
    page_size: Number(payload.pageSize || 20),
    include_replies: payload.includeReplies !== false,
    replies_per_comment: Number(payload.repliesPerComment ?? 3),
  });
}

export async function deleteDouyinTargetVideoAnalysis(videoId) {
  const response = await fetch(`${API_BASE}/api/tools/douyin-target/videos/${encodeURIComponent(videoId)}/analysis`, {
    method: "DELETE",
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message =
      data?.detail?.message ||
      data?.detail?.error ||
      data?.detail ||
      `Request failed: ${response.status}`;
    if (typeof message === "string") {
      throw new Error(message);
    }
    throw new Error(JSON.stringify(message, null, 2));
  }
  return data;
}

export function enqueueDouyinTargetAnalysis(payload) {
  return postJson("/api/tools/douyin-target/analysis/enqueue", {
    set_id: payload.setId || "",
    video_ids: payload.videoIds || [],
    force: Boolean(payload.force),
    provider: payload.provider || undefined,
    collect_comments: payload.collectComments !== false,
    adaptive_comments: payload.adaptiveComments !== false,
    max_comments: Number(payload.maxComments || 160),
    min_comments: Number(payload.minComments ?? 30),
    replies_per_comment: Number(payload.repliesPerComment ?? 3),
  });
}

export async function fetchDouyinTargetVideoInteractions(videoId) {
  const response = await fetch(`${API_BASE}/api/tools/douyin-target/videos/${encodeURIComponent(videoId)}/interactions`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function syncDouyinTargetAnalysis(setId) {
  const query = setId ? `?set_id=${encodeURIComponent(setId)}` : "";
  return postJson(`/api/tools/douyin-target/analysis/sync${query}`, {});
}

export function createAiPromptReverseJob(video, provider) {
  const payload = { video };
  if (provider) {
    payload.provider = provider;
  }
  return postJson("/api/tools/ai-prompt-reverse/jobs", payload);
}

export function createAiProductionReverseJob(video, provider) {
  const payload = { video };
  if (provider) {
    payload.provider = provider;
  }
  return postJson("/api/tools/ai-production-reverse/jobs", payload);
}

export async function fetchRunningHubTtsConfig() {
  const response = await fetch(`${API_BASE}/api/tools/runninghub-tts/config`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function saveRunningHubTtsConfig(config) {
  return postJson("/api/tools/runninghub-tts/config", {
    api_key: config.apiKey || "",
    api_base: config.apiBase || "https://www.runninghub.cn",
    workflow_key: config.workflowKey || "runninghub/tts_stable_emotion.json",
    workflow_id: config.workflowId || "",
    instance_type: config.instanceType || "",
    poll_interval_seconds: Number(config.pollIntervalSeconds || 3),
  });
}

export async function fetchRunningHubTtsStatus() {
  const response = await fetch(`${API_BASE}/api/tools/runninghub-tts/status`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function syncRunningHubTtsTasks() {
  const response = await fetch(`${API_BASE}/api/tools/runninghub-tts/sync`, {
    method: "POST",
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function uploadRunningHubTtsAudio(file) {
  const formData = new FormData();
  formData.append("file", file);
  return fetch(`${API_BASE}/api/tools/runninghub-tts/upload`, {
    method: "POST",
    body: formData,
  }).then(async (response) => {
    const data = await response.json();
    if (!response.ok) {
      throw new Error(JSON.stringify(data?.detail || data, null, 2));
    }
    return data;
  });
}

export function createRunningHubTtsJob(payload) {
  return postJson("/api/tools/runninghub-tts/jobs", {
    text: payload.text || "",
    workflow_key: payload.workflowKey || "runninghub/tts_stable_emotion.json",
    workflow_id: payload.workflowId || undefined,
    api_key: payload.apiKey || undefined,
    api_base: payload.apiBase || undefined,
    instance_type: payload.instanceType || undefined,
    ref_audio_path: payload.refAudioPath || undefined,
    ref_audio_url: payload.refAudioUrl || undefined,
    voice: payload.voice || undefined,
    speed: payload.speed != null ? Number(payload.speed) : undefined,
    enable_duration_control: payload.enableDurationControl != null ? Boolean(payload.enableDurationControl) : undefined,
    duration_mode: payload.durationMode || undefined,
    speed_multiplier: payload.speedMultiplier != null ? Number(payload.speedMultiplier) : undefined,
    target_duration: payload.targetDuration != null ? Number(payload.targetDuration) : undefined,
    enable_emotion_control: payload.enableEmotionControl != null ? Boolean(payload.enableEmotionControl) : undefined,
    emotion_mode: payload.emotionMode || undefined,
    emotion_audio_path: payload.emotionAudioPath || undefined,
    emotion_audio_url: payload.emotionAudioUrl || undefined,
    emotion_alpha: payload.emotionAlpha != null ? Number(payload.emotionAlpha) : undefined,
    emotion_text: payload.emotionText || undefined,
    happy: payload.happy != null ? Number(payload.happy) : undefined,
    angry: payload.angry != null ? Number(payload.angry) : undefined,
    sad: payload.sad != null ? Number(payload.sad) : undefined,
    fear: payload.fear != null ? Number(payload.fear) : undefined,
    hate: payload.hate != null ? Number(payload.hate) : undefined,
    love: payload.love != null ? Number(payload.love) : undefined,
    surprise: payload.surprise != null ? Number(payload.surprise) : undefined,
    neutral: payload.neutral != null ? Number(payload.neutral) : undefined,
  });
}

export function createTextToAssetsJob(payload) {
  return postJson("/api/tools/text-to-assets/jobs", {
    idea: payload.idea || "",
    title: payload.title || undefined,
    provider: payload.provider || undefined,
  });
}

export async function fetchTasks(taskType, options = {}) {
  const params = new URLSearchParams();
  if (taskType) params.set("task_type", taskType);
  if (options.limit) params.set("limit", String(options.limit));
  if (options.includeResult) params.set("include_result", "true");
  if (options.includeEvents) params.set("include_events", "true");
  const query = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${API_BASE}/api/tasks${query}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchTaskEvents(taskId) {
  const response = await fetch(`${API_BASE}/api/tasks/${encodeURIComponent(taskId)}/events`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function deleteTask(taskId, deleteArchives = true) {
  const response = await fetch(`${API_BASE}/api/tasks/${encodeURIComponent(taskId)}?delete_archives=${deleteArchives}`, {
    method: "DELETE",
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function archiveTask(taskId) {
  return postJson(`/api/tasks/${encodeURIComponent(taskId)}/archive`, {});
}

export async function fetchAiVideoConfig() {
  const response = await fetch(`${API_BASE}/api/tools/ai-video-analysis/config`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function saveAiVideoConfig(config) {
  return postJson("/api/tools/ai-video-analysis/config", {
    output_dir: config.outputDir,
    pipeline_mode: config.pipelineMode,
    transcriber: config.transcriber,
    transcribe_model: config.transcribeModel,
    transcribe_language: config.transcribeLanguage,
    transcribe_device: config.transcribeDevice,
    transcribe_compute_type: config.transcribeComputeType,
    asr_upload_mode: config.asrUploadMode,
    asr_publisher: config.asrPublisher,
    asr_public_base_url: config.asrPublicBaseUrl,
    asr_public_dir: config.asrPublicDir,
    summary_provider: config.summaryProvider,
    summary_model: config.summaryModel,
    summary_fallback_provider: config.summaryFallbackProvider,
    segment_seconds: Number(config.segmentSeconds),
    silent_segment_seconds: Number(config.silentSegmentSeconds || 6),
    keyframe_interval_seconds: Number(config.keyframeIntervalSeconds),
    max_segments: Number(config.maxSegments),
    max_concurrent_tasks: Number(config.maxConcurrentTasks),
    resume_enabled: Boolean(config.resumeEnabled),
    highlight_screenshots: Boolean(config.highlightScreenshots),
    grid_columns: Number(config.gridColumns),
    grid_max_frames: Number(config.gridMaxFrames),
    grid_cell_width: Number(config.gridCellWidth),
    grid_cell_height: Number(config.gridCellHeight),
    ffmpeg_binary: config.ffmpegBinary,
    ffprobe_binary: config.ffprobeBinary,
    analysis_prompt: config.analysisPrompt,
  });
}

export async function fetchAiVideoQueueStatus(taskId, backlogLimit = 20) {
  const params = new URLSearchParams();
  if (taskId) {
    params.set("task_id", taskId);
  }
  if (backlogLimit) {
    params.set("backlog_limit", String(backlogLimit));
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${API_BASE}/api/tools/ai-video-analysis/queue/status${query}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchAiVideoEvidence(taskId) {
  const path = `/api/tools/ai-video-analysis/jobs/${encodeURIComponent(taskId)}/evidence`;
  const bases = [API_BASE];
  if (typeof window !== "undefined" && ["127.0.0.1", "localhost"].includes(window.location.hostname)) {
    bases.push("", "http://127.0.0.1:8010");
  }
  let lastError = null;
  for (const base of [...new Set(bases)]) {
    try {
      const response = await fetch(`${base}${path}`);
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) {
        lastError = new Error(JSON.stringify(data?.detail || data || `Request failed: ${response.status}`, null, 2));
        continue;
      }
      if (base && data?.media) {
        return {
          ...data,
          media: {
            ...data.media,
            video_url: data.media.video_url?.startsWith("/api/") ? `${base}${data.media.video_url}` : data.media.video_url || "",
            audio_url: data.media.audio_url?.startsWith("/api/") ? `${base}${data.media.audio_url}` : data.media.audio_url || "",
          },
        };
      }
      return data;
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError || new Error("Evidence API failed");
}

export async function cancelAiVideoQueueJob(taskId) {
  const response = await fetch(`${API_BASE}/api/tools/ai-video-analysis/jobs/${encodeURIComponent(taskId)}/cancel`, {
    method: "POST",
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function retryAiVideoQueueJob(taskId) {
  const response = await fetch(`${API_BASE}/api/tools/ai-video-analysis/jobs/${encodeURIComponent(taskId)}/retry`, {
    method: "POST",
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function deleteAiVideoQueueJob(taskId) {
  const response = await fetch(`${API_BASE}/api/tools/ai-video-analysis/jobs/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function saveAiVideoRemakeExport(payload) {
  return postJson("/api/tools/ai-video-analysis/remake-exports", {
    run_id: payload.runId || "",
    task_id: payload.taskId || "",
    title: payload.title || "",
    genre: payload.genre || "",
    target_genre: payload.targetGenre || "",
    markdown: payload.markdown || "",
    result: payload.result || {},
    rewritten: payload.rewritten || {},
    export_type: payload.exportType || "remake_package",
  });
}

export function rewriteAiVideoRemake(payload) {
  return postJson("/api/tools/ai-video-analysis/remake-exports/rewrite", {
    run_id: payload.runId || "",
    task_id: payload.taskId || "",
    title: payload.title || "",
    source_genre: payload.sourceGenre || "",
    target_genre: payload.targetGenre || "",
    markdown: payload.markdown || "",
    result: payload.result || {},
  });
}

export function sendAiVideoRemakeToScript(payload) {
  return postJson("/api/tools/ai-video-analysis/remake-exports/send-to-script", {
    run_id: payload.runId || "",
    task_id: payload.taskId || "",
    title: payload.title || "",
    source_genre: payload.sourceGenre || "",
    target_genre: payload.targetGenre || "",
    markdown: payload.markdown || "",
    result: payload.result || {},
    duration_seconds: Number(payload.durationSeconds || 60),
    scene_count: Number(payload.sceneCount || 6),
    provider: payload.provider || null,
  });
}

export async function fetchAiPromptReverseStatus() {
  const response = await fetch(`${API_BASE}/api/tools/ai-prompt-reverse/status`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchAiPromptReverseConfig() {
  const response = await fetch(`${API_BASE}/api/tools/ai-prompt-reverse/config`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function saveAiPromptReverseConfig(config) {
  return postJson("/api/tools/ai-prompt-reverse/config", {
    output_dir: config.outputDir,
    pipeline_mode: config.pipelineMode,
    max_segments: Number(config.maxSegments || 18),
    reverse_prompt: config.reversePrompt,
  });
}

export async function fetchAiProductionReverseStatus() {
  const response = await fetch(`${API_BASE}/api/tools/ai-production-reverse/status`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchAiProductionReverseConfig() {
  const response = await fetch(`${API_BASE}/api/tools/ai-production-reverse/config`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function saveAiProductionReverseConfig(config) {
  return postJson("/api/tools/ai-production-reverse/config", {
    output_dir: config.outputDir,
    pipeline_mode: config.pipelineMode,
    max_segments: Number(config.maxSegments || 18),
    production_prompt: config.productionPrompt,
  });
}

export async function fetchAiVideoArchives(options = {}) {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.includeResult) params.set("include_result", "true");
  const query = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${API_BASE}/api/tools/ai-video-analysis/archives${query}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchAiPromptReverseArchives(options = {}) {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.includeResult) params.set("include_result", "true");
  const query = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${API_BASE}/api/tools/ai-prompt-reverse/archives${query}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchAiProductionReverseArchives(options = {}) {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.includeResult) params.set("include_result", "true");
  const query = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${API_BASE}/api/tools/ai-production-reverse/archives${query}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchAiVideoArchive(archiveId) {
  const response = await fetch(`${API_BASE}/api/tools/ai-video-analysis/archives/${encodeURIComponent(archiveId)}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchAiPromptReverseArchive(archiveId) {
  const response = await fetch(`${API_BASE}/api/tools/ai-prompt-reverse/archives/${encodeURIComponent(archiveId)}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchAiProductionReverseArchive(archiveId) {
  const response = await fetch(`${API_BASE}/api/tools/ai-production-reverse/archives/${encodeURIComponent(archiveId)}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function createJianyingDraftFromScript(payload) {
  return postJson("/api/tools/jianying/drafts/create-from-script", {
    name: payload.name || "",
    script_path: payload.scriptPath || undefined,
    script: payload.script || undefined,
    engine: payload.engine || "pyjianying",
    include_onscreen_text: Boolean(payload.includeOnscreenText),
    subtitle_from_narration: Boolean(payload.subtitleFromNarration),
    default_media_duration_seconds: Number(payload.defaultMediaDurationSeconds || 3),
    text_style: payload.textStyle || {},
    text_background: payload.textBackground || {},
  });
}

export async function fetchJianyingDrafts(status) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const response = await fetch(`${API_BASE}/api/tools/jianying/drafts${query}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function openJianyingDraftPath(draftPath) {
  return postJson("/api/tools/jianying/drafts/open-path", {
    draft_path: draftPath,
  });
}

export function inspectJianyingDraft(draftPath) {
  return postJson("/api/tools/jianying/drafts/inspect", {
    draft_path: draftPath,
  });
}

export function listJianyingDraftProjects(draftRoot) {
  return postJson("/api/tools/jianying/drafts/projects", {
    draft_root: draftRoot,
  });
}

export async function fetchJianyingEditorSdkStatus() {
  const response = await fetch(`${API_BASE}/api/tools/jianying-editor-sdk/status`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function runJianyingEditorSdkDiagnostics(payload = {}) {
  return postJson("/api/tools/jianying-editor-sdk/diagnostics/deep", {
    project: payload.project || "",
    video: payload.video || "",
    strict: Boolean(payload.strict),
  });
}

export function listJianyingEditorSdkDrafts(payload) {
  return postJson("/api/tools/jianying-editor-sdk/drafts/list", {
    root: payload.root || "",
    limit: Number(payload.limit || 20),
  });
}

export function summarizeJianyingEditorSdkDraft(payload) {
  return postJson("/api/tools/jianying-editor-sdk/drafts/summary", {
    root: payload.root || "",
    name: payload.name || "",
    path: payload.path || "",
  });
}

export function showJianyingEditorSdkDraft(payload) {
  return postJson("/api/tools/jianying-editor-sdk/drafts/show", {
    root: payload.root || "",
    name: payload.name || "",
    path: payload.path || "",
    kind: payload.kind || "content",
  });
}

export function searchJianyingEditorSdkAssets(payload) {
  return postJson("/api/tools/jianying-editor-sdk/assets/search", {
    query: payload.query || "",
    category: payload.category || "",
    limit: Number(payload.limit || 20),
  });
}

export function exportJianyingEditorSdkDraft(payload) {
  return postJson("/api/tools/jianying-editor-sdk/exports", {
    name: payload.name || "",
    output_path: payload.outputPath || "",
    resolution: payload.resolution || "",
    framerate: payload.framerate || "",
  });
}

export function recordJianyingEditorSdkWebVfx(payload) {
  return postJson("/api/tools/jianying-editor-sdk/web-vfx/record", {
    source: payload.source || "",
    output_path: payload.outputPath || "",
    max_duration_seconds: Number(payload.maxDurationSeconds || 30),
  });
}

export function generateJianyingEditorSdkTts(payload) {
  return postJson("/api/tools/jianying-editor-sdk/tts", {
    text: payload.text || "",
    output_path: payload.outputPath || "",
    speaker: payload.speaker || "zh_male_huoli",
    backend: payload.backend || "",
    allow_fallback: payload.allowFallback !== false,
    sami_retries: Number(payload.samiRetries ?? 2),
  });
}

export function resolveJianyingEditorSdkCloudAsset(payload) {
  return postJson("/api/tools/jianying-editor-sdk/cloud/assets/resolve", {
    query: payload.query || "",
    force: Boolean(payload.force),
  });
}

export function syncJianyingEditorSdkCloudMusicLibrary(payload) {
  return postJson("/api/tools/jianying-editor-sdk/cloud/music-library/sync", {
    projects_root: payload.projectsRoot || "",
    dry_run: Boolean(payload.dryRun),
  });
}

export function createJianyingEditorSdkSmartZoomDraft(payload) {
  return postJson("/api/tools/jianying-editor-sdk/smart-zoom/drafts", {
    project_name: payload.projectName || "",
    video_path: payload.videoPath || "",
    events_json_path: payload.eventsJsonPath || "",
    zoom_scale: Number(payload.zoomScale || 150),
    hold_seconds: Number(payload.holdSeconds || 5),
  });
}

export function createJianyingEditorSdkMovieCommentaryDraft(payload) {
  return postJson("/api/tools/jianying-editor-sdk/movie-commentary/drafts", {
    video_path: payload.videoPath || "",
    storyboard_path: payload.storyboardPath || "",
    project_name: payload.projectName || "Movie_Commentary_Project",
    bgm_path: payload.bgmPath || "",
    mask_path: payload.maskPath || "",
  });
}

export function generateVideoScript(payload) {
  return postJson("/api/tools/video-script/generate", {
    title: payload.title,
    idea: payload.idea,
    creative_preset: payload.creativePreset,
    genre: payload.genre,
    style: payload.style,
    audience: payload.audience,
    tone: payload.tone,
    structure: payload.structure,
    cta: payload.cta,
    duration_seconds: Number(payload.durationSeconds || 30),
    scene_count: Number(payload.sceneCount || 5),
    resolution: payload.resolution || "9:16",
    provider: payload.provider || undefined,
  });
}

export function generateJianyingNaturalScript(payload) {
  return postJson("/api/tools/video-script/natural-language/generate", {
    input: payload.input,
    title: payload.title || "",
    creative_preset: payload.creativePreset || "",
    duration_seconds: payload.durationSeconds ? Number(payload.durationSeconds) : undefined,
    scene_count: payload.sceneCount ? Number(payload.sceneCount) : undefined,
    resolution: payload.resolution || "",
    generation_mode: payload.generationMode || "local",
    provider: payload.provider || undefined,
  });
}

export function generateVideoScriptBible(payload) {
  return postJson("/api/tools/video-script/bible", {
    title: payload.title,
    idea: payload.idea,
    genre: payload.genre,
    creative_preset: payload.creativePreset,
    provider: payload.provider || undefined,
  });
}

export function generateVideoScriptBlueprint(payload) {
  return postJson("/api/tools/video-script/blueprint", {
    title: payload.title,
    idea: payload.idea,
    genre: payload.genre,
    creative_preset: payload.creativePreset,
    bible: payload.bible,
    duration_seconds: Number(payload.durationSeconds || 30),
    scene_count: Number(payload.sceneCount || 5),
    resolution: payload.resolution || "9:16",
    provider: payload.provider || undefined,
  });
}

export function brainstormStudio(payload) {
  return postJson("/api/studio/brainstorm", {
    type: payload.type || "短视频",
    inspiration: payload.inspiration,
    provider: payload.provider || undefined,
  });
}

export function lockStudioConcept(payload) {
  return postJson("/api/studio/lock_concept", {
    context: payload.context || {},
    angle_id: payload.angleId || "",
    feedback: payload.feedback || "",
    provider: payload.provider || undefined,
  });
}

export function generateStudioBlueprint(payload) {
  return postJson("/api/studio/generate_blueprint", {
    context: payload.context || {},
    bible: payload.bible,
    title: payload.title,
    idea: payload.idea,
    genre: payload.genre || "",
    creative_preset: payload.creativePreset || "default",
    duration_seconds: Number(payload.durationSeconds || 30),
    scene_count: Number(payload.sceneCount || 5),
    resolution: payload.resolution || "9:16",
    provider: payload.provider || undefined,
  });
}

export async function fetchVideoScripts() {
  const response = await fetch(`${API_BASE}/api/tools/video-script`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchTask(taskId) {
  const response = await fetch(`${API_BASE}/api/tasks/${encodeURIComponent(taskId)}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchVideoScript(projectId) {
  const response = await fetch(`${API_BASE}/api/tools/video-script/${encodeURIComponent(projectId)}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export function saveVideoScript(projectId, script) {
  return postJson(`/api/tools/video-script/${encodeURIComponent(projectId)}/save`, { script });
}

export function expandVideoScript(projectId, payload) {
  return postJson(`/api/tools/video-script/${encodeURIComponent(projectId)}/expand`, {
    idea: payload.idea || "",
    expand_count: Number(payload.expandCount || 1),
    provider: payload.provider || undefined,
  });
}

export function prepareVideoScriptAssets(projectId, payload) {
  return postJson(`/api/tools/video-script/${encodeURIComponent(projectId)}/prepare-assets`, {
    script: payload.script || undefined,
    source_paths: payload.sourcePaths || [],
    resolve_local_materials: payload.resolveLocalMaterials !== false,
    generate_audio: payload.generateAudio !== false,
    generate_images: payload.generateImages !== false,
    generate_videos: Boolean(payload.generateVideos),
    overwrite_existing: Boolean(payload.overwriteExisting),
    ffprobe_binary: payload.ffprobeBinary || "ffprobe",
    tts_provider: payload.ttsProvider || "openai",
    tts_model: payload.ttsModel || "gpt-4o-mini-tts",
    tts_voice: payload.ttsVoice || "alloy",
    tts_format: payload.ttsFormat || "mp3",
    image_provider: payload.imageProvider || "gemini",
    image_model: payload.imageModel || "imagen-4.0-generate-001",
  });
}

export async function deleteVideoScript(projectId) {
  const response = await fetch(`${API_BASE}/api/tools/video-script/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}
