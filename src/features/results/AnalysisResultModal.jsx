import { useEffect, useMemo, useRef, useState } from "react";
import { compactNumber, normalizeModelRuns } from "../../utils/appUtils";
import {
  buildEvidenceRows,
  buildInteractionSnapshot,
  buildRadarItems,
  buildSummaryStats,
  buildTopMetaTags,
  buildTranscriptLines,
  mergeFilledObject,
  mergeSegmentBreakdowns,
  normalizeAnalysisResult,
  resolveAuthorProfile,
  resolvePosterUrl,
  resolveSourceVideoUrl,
  resolveTargetVideoId,
  sanitizeFileName,
  seekStartSeconds,
} from "../../utils/aiVideoAnalysisView";
import { rewriteAiVideoRemake, saveAiVideoRemakeExport, sendAiVideoRemakeToScript } from "../../services/api";
import { ModelRunSummary } from "./ModelRunSummary";
import { CommentIntelligence, RemakeLab, ResultOverview, SectionRows, SegmentTimeline, VideoTranscriptSyncPanel } from "./AnalysisResultSections";
import { useAiVideoEvidence } from "./useAiVideoEvidence";
import { useDouyinInteractions } from "./useDouyinInteractions";

function copyToClipboard(text) {
  if (!text) throw new Error("没有可复制内容");
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text);
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
  return Promise.resolve();
}

function downloadTextFile({ fileName, text }) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function AnalysisResultModal({ task, onClose, pageMode = false }) {
  const videoRef = useRef(null);
  const [actionStatus, setActionStatus] = useState("");
  const [pendingAction, setPendingAction] = useState("");
  const [targetGenre, setTargetGenre] = useState("beauty");
  const [activeTranscriptId, setActiveTranscriptId] = useState("");

  const result = useMemo(() => normalizeAnalysisResult(task?.result || {}), [task]);
  const evidence = result.evidence || {};
  const targetVideoId = useMemo(() => resolveTargetVideoId(task, result), [task, result]);
  const { dataset: evidenceDataset, status: evidenceStatus } = useAiVideoEvidence(task?.id);
  const { dataset: liveInteractions, status: liveInteractionStatus } = useDouyinInteractions(targetVideoId);
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
      { label: "获赞", value: author.total_favorited == null ? "未返回" : compactNumber(author.total_favorited) },
      { label: "视频", value: author.aweme_count == null ? "未返回" : compactNumber(author.aweme_count) },
      { label: "属地", value: author.ip_location || "未知" },
    ],
    [task, result, videoInfo, author],
  );
  const summaryStats = useMemo(
    () => buildSummaryStats({ result, evidence, segmentCount: segmentBreakdowns.length, modelRunCount: modelRuns.length }),
    [result, evidence, segmentBreakdowns.length, modelRuns.length],
  );
  const evidenceRows = useMemo(
    () => buildEvidenceRows({ result, evidence, segmentCount: segmentBreakdowns.length, modelRunCount: modelRuns.length }),
    [result, evidence, segmentBreakdowns.length, modelRuns.length],
  );
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
      // Ignore teardown failures.
    }
  }

  useEffect(() => {
    setActiveTranscriptId("");
  }, [task?.id]);

  useEffect(() => () => stopTranscriptVideo(true), [task?.id]);

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
      playPromise.catch(() => {});
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
          <ResultOverview
            author={author}
            evidence={evidence}
            genre={genre}
            radarItems={radarItems}
            result={result}
            segmentCount={segmentBreakdowns.length}
            task={task}
            taskVideo={taskVideo}
            topMetaStats={topMetaStats}
            topMetaTags={topMetaTags}
            videoInfo={videoInfo}
          />
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
