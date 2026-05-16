import { useEffect, useState } from "react";
import { Badge } from "../../components/common/index";
import { statusText } from "../../constants/appConfig";
import { createJianyingDraftFromScript, deleteVideoScript, fetchTask, fetchVideoScript, fetchVideoScripts, generateJianyingNaturalScript, prepareVideoScriptAssets, saveVideoScript } from "../../services/api";
import { cleanScriptValue, createDateDraftName, createScriptFallbackBible, deriveBgmKeywords, deriveOptionalWorkflowFlags, formatTimelineMark, formatTimestamp, generationModeLabel, sceneDuration } from "../../utils/appUtils";

export function JianyingNaturalScriptPanel() {
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
