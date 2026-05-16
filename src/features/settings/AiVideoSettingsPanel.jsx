import { useEffect, useState } from "react";
import { Badge } from "../../components/common/index";
import { fetchAiVideoConfig, saveAiVideoConfig } from "../../services/api";

export function AiVideoSettingsPanel() {
  const [outputDir, setOutputDir] = useState("./data/runtime/ai_video_analysis");
  const [pipelineMode, setPipelineMode] = useState("evidence");
  const [transcriber, setTranscriber] = useState("auto");
  const [transcribeModel, setTranscribeModel] = useState("small");
  const [transcribeLanguage, setTranscribeLanguage] = useState("zh");
  const [transcribeDevice, setTranscribeDevice] = useState("cpu");
  const [transcribeComputeType, setTranscribeComputeType] = useState("int8");
  const [segmentSeconds, setSegmentSeconds] = useState(90);
  const [silentSegmentSeconds, setSilentSegmentSeconds] = useState(6);
  const [keyframeIntervalSeconds, setKeyframeIntervalSeconds] = useState(30);
  const [maxSegments, setMaxSegments] = useState(18);
  const [maxConcurrentTasks, setMaxConcurrentTasks] = useState(1);
  const [resumeEnabled, setResumeEnabled] = useState(true);
  const [highlightScreenshots, setHighlightScreenshots] = useState(true);
  const [gridColumns, setGridColumns] = useState(3);
  const [gridMaxFrames, setGridMaxFrames] = useState(9);
  const [gridCellWidth, setGridCellWidth] = useState(320);
  const [gridCellHeight, setGridCellHeight] = useState(180);
  const [ffmpegBinary, setFfmpegBinary] = useState("ffmpeg");
  const [ffprobeBinary, setFfprobeBinary] = useState("ffprobe");
  const [analysisPrompt, setAnalysisPrompt] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchAiVideoConfig()
      .then((config) => {
        setOutputDir(config.output_dir || "./data/runtime/ai_video_analysis");
        setPipelineMode(config.pipeline_mode || "evidence");
        setTranscriber(config.transcriber || "auto");
        setTranscribeModel(config.transcribe_model || "small");
        setTranscribeLanguage(config.transcribe_language || "zh");
        setTranscribeDevice(config.transcribe_device || "cpu");
        setTranscribeComputeType(config.transcribe_compute_type || "int8");
        setSegmentSeconds(config.segment_seconds || 90);
        setSilentSegmentSeconds(config.silent_segment_seconds || 6);
        setKeyframeIntervalSeconds(config.keyframe_interval_seconds || 30);
        setMaxSegments(config.max_segments || 18);
        setMaxConcurrentTasks(config.max_concurrent_tasks || 1);
        setResumeEnabled(Boolean(config.resume_enabled));
        setHighlightScreenshots(Boolean(config.highlight_screenshots));
        setGridColumns(config.grid_columns || 3);
        setGridMaxFrames(config.grid_max_frames || 9);
        setGridCellWidth(config.grid_cell_width || 320);
        setGridCellHeight(config.grid_cell_height || 180);
        setFfmpegBinary(config.ffmpeg_binary || "ffmpeg");
        setFfprobeBinary(config.ffprobe_binary || "ffprobe");
        setAnalysisPrompt(config.analysis_prompt || "");
      })
      .catch((err) => setError(err.message || String(err)));
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await saveAiVideoConfig({
        outputDir,
        pipelineMode,
        transcriber,
        transcribeModel,
        transcribeLanguage,
        transcribeDevice,
        transcribeComputeType,
        segmentSeconds,
        silentSegmentSeconds,
        keyframeIntervalSeconds,
        maxSegments,
        maxConcurrentTasks,
        resumeEnabled,
        highlightScreenshots,
        gridColumns,
        gridMaxFrames,
        gridCellWidth,
        gridCellHeight,
        ffmpegBinary,
        ffprobeBinary,
        analysisPrompt,
      });
      setMessage("AI 视频拆解配置已保存。模型连接仍使用全局 AI 模型配置。");
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>AI 视频拆解配置</h2>
          <p>配置证据包、转写、分段、关键帧和拆解提示词。模型连接请到“AI 模型”里统一设置。</p>
        </div>
        <Badge status={pipelineMode === "direct" ? "draft" : "ready"}>{pipelineMode}</Badge>
      </div>
      <form className="settings-form" onSubmit={handleSubmit}>
        <label>
          拆解流程
          <select value={pipelineMode} onChange={(event) => setPipelineMode(event.target.value)}>
            <option value="evidence">证据包优先：转写 + 关键帧 + 分段拆解</option>
            <option value="auto">自动：证据包失败时回退直接视频分析</option>
            <option value="direct">直接视频分析：跳过转写流程</option>
          </select>
        </label>
        <label>
          输出目录
          <input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} />
        </label>
        <label>
          转写器
          <select value={transcriber} onChange={(event) => setTranscriber(event.target.value)}>
            <option value="auto">自动选择</option>
            <option value="faster_whisper">faster-whisper</option>
            <option value="openai_whisper">openai-whisper</option>
          </select>
        </label>
        <label>
          Whisper 模型
          <input value={transcribeModel} onChange={(event) => setTranscribeModel(event.target.value)} placeholder="small / medium" />
        </label>
        <label>
          转写语言
          <input value={transcribeLanguage} onChange={(event) => setTranscribeLanguage(event.target.value)} placeholder="zh" />
        </label>
        <label>
          转写设备
          <select value={transcribeDevice} onChange={(event) => setTranscribeDevice(event.target.value)}>
            <option value="cpu">cpu</option>
            <option value="cuda">cuda</option>
            <option value="auto">auto</option>
          </select>
        </label>
        <label>
          计算精度
          <select value={transcribeComputeType} onChange={(event) => setTranscribeComputeType(event.target.value)}>
            <option value="int8">int8</option>
            <option value="float16">float16</option>
            <option value="float32">float32</option>
          </select>
        </label>
        <label>
          分段秒数
          <input type="number" min="30" max="600" value={segmentSeconds} onChange={(event) => setSegmentSeconds(event.target.value)} />
        </label>
        <label>
          无语音视觉切段秒数
          <input type="number" min="2" max="30" value={silentSegmentSeconds} onChange={(event) => setSilentSegmentSeconds(event.target.value)} />
          <span className="field-hint">适合 AI 小动物、音乐卡点、纯画面视频。无转写文本时按这个秒数切割。</span>
        </label>
        <label>
          关键帧间隔秒数
          <input type="number" min="5" max="300" value={keyframeIntervalSeconds} onChange={(event) => setKeyframeIntervalSeconds(event.target.value)} />
        </label>
        <label>
          最多 AI 拆解片段
          <input type="number" min="1" max="100" value={maxSegments} onChange={(event) => setMaxSegments(event.target.value)} />
        </label>
        <label>
          最大并发任务数
          <input type="number" min="1" max="4" value={maxConcurrentTasks} onChange={(event) => setMaxConcurrentTasks(event.target.value)} />
          <span className="field-hint">普通 CPU 建议保持 1。多任务会同时占用 Whisper、FFmpeg 和 API 调用，可能导致机器明显卡顿。</span>
        </label>
        <label>
          网格列数
          <input type="number" min="1" max="6" value={gridColumns} onChange={(event) => setGridColumns(event.target.value)} />
        </label>
        <label>
          每段最多关键帧
          <input type="number" min="1" max="24" value={gridMaxFrames} onChange={(event) => setGridMaxFrames(event.target.value)} />
        </label>
        <label>
          网格单格宽度
          <input type="number" min="120" max="960" value={gridCellWidth} onChange={(event) => setGridCellWidth(event.target.value)} />
        </label>
        <label>
          网格单格高度
          <input type="number" min="90" max="720" value={gridCellHeight} onChange={(event) => setGridCellHeight(event.target.value)} />
        </label>
        <label className="checkbox-field wide-field">
          <input type="checkbox" checked={resumeEnabled} onChange={(event) => setResumeEnabled(event.target.checked)} />
          <span>启用断点续跑：逐步复用已完成的音频、转写、关键帧、分段拆解和全局汇总</span>
        </label>
        <label className="checkbox-field wide-field">
          <input type="checkbox" checked={highlightScreenshots} onChange={(event) => setHighlightScreenshots(event.target.checked)} />
          <span>让 AI 标注爆点截图时间，并自动截取对应画面</span>
        </label>
        <label>
          FFmpeg
          <input value={ffmpegBinary} onChange={(event) => setFfmpegBinary(event.target.value)} placeholder="ffmpeg 或绝对路径" />
        </label>
        <label>
          FFprobe
          <input value={ffprobeBinary} onChange={(event) => setFfprobeBinary(event.target.value)} placeholder="ffprobe 或绝对路径" />
        </label>
        <label className="textarea-label">
          拆解提示词模板
          <textarea
            value={analysisPrompt}
            onChange={(event) => setAnalysisPrompt(event.target.value)}
            rows={12}
            placeholder="可使用变量：{desc}、{author}"
          />
          <span className="field-hint">可使用变量：{"{desc}"} 视频描述，{"{author}"} 作者。建议要求模型严格返回 JSON。</span>
        </label>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存拆解配置"}
        </button>
      </form>
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}
