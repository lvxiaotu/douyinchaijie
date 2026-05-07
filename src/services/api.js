const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8010";

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
    throw new Error(typeof message === "string" ? message : JSON.stringify(message, null, 2));
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

export function createAiPromptReverseJob(video, provider) {
  const payload = { video };
  if (provider) {
    payload.provider = provider;
  }
  return postJson("/api/tools/ai-prompt-reverse/jobs", payload);
}

export async function fetchTasks(taskType) {
  const query = taskType ? `?task_type=${encodeURIComponent(taskType)}` : "";
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

export async function fetchAiVideoArchives() {
  const response = await fetch(`${API_BASE}/api/tools/ai-video-analysis/archives`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}

export async function fetchAiPromptReverseArchives() {
  const response = await fetch(`${API_BASE}/api/tools/ai-prompt-reverse/archives`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data?.detail || data, null, 2));
  }
  return data;
}
