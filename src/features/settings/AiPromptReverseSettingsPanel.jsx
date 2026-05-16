import { useEffect, useState } from "react";
import { Badge } from "../../components/common/index";
import { fetchAiPromptReverseConfig, fetchAiPromptReverseStatus, saveAiPromptReverseConfig } from "../../services/api";

export function AiPromptReverseSettingsPanel() {
  const [outputDir, setOutputDir] = useState("./data/runtime/ai_prompt_reverse");
  const [pipelineMode, setPipelineMode] = useState("evidence");
  const [maxSegments, setMaxSegments] = useState(18);
  const [reversePrompt, setReversePrompt] = useState("");
  const [statusInfo, setStatusInfo] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchAiPromptReverseConfig()
      .then((config) => {
        setOutputDir(config.output_dir || "./data/runtime/ai_prompt_reverse");
        setPipelineMode(config.pipeline_mode || "evidence");
        setMaxSegments(config.max_segments || 18);
        setReversePrompt(config.reverse_prompt || "");
      })
      .catch((err) => setError(err.message || String(err)));
    fetchAiPromptReverseStatus()
      .then(setStatusInfo)
      .catch(() => setStatusInfo(null));
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await saveAiPromptReverseConfig({ outputDir, pipelineMode, maxSegments, reversePrompt });
      setMessage("AI 提示词反推配置已保存。重启主后端后会稳定生效。");
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
          <h2>AI 提示词反推配置</h2>
          <p>配置复刻流程、片段上限和反推要求。模型连接请到“AI 模型”里统一设置。</p>
        </div>
        <Badge status={pipelineMode === "direct" ? "draft" : "ready"}>{pipelineMode}</Badge>
      </div>
      {statusInfo && (
        <div className={`task-sync-banner ${statusInfo.ready ? "" : "error"}`}>
          反推依赖：FFmpeg {statusInfo.pipeline?.ffmpeg_ready ? "可用" : "不可用"} · FFprobe{" "}
          {statusInfo.pipeline?.ffprobe_ready ? "可用" : "不可用"} · 转写器 {statusInfo.pipeline?.transcriber_ready ? "可用" : "不可用"}
        </div>
      )}
      <form className="settings-form" onSubmit={handleSubmit}>
        <label>
          输出目录
          <input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} />
        </label>
        <label>
          反推模式
          <select value={pipelineMode} onChange={(event) => setPipelineMode(event.target.value)}>
            <option value="evidence">证据管线复刻</option>
            <option value="auto">证据失败后回退整段视频</option>
            <option value="direct">整段视频直传</option>
          </select>
          <span className="field-hint">建议使用证据管线复刻：转写 + 分段 + 关键帧网格 + 逐镜头反推。</span>
        </label>
        <label>
          最大反推片段数
          <input type="number" min="1" max="100" value={maxSegments} onChange={(event) => setMaxSegments(event.target.value)} />
          <span className="field-hint">数值越高越接近完整复刻，但耗时和 API 成本也越高。</span>
        </label>
        <label className="textarea-label">
          反推提示词模板
          <textarea
            value={reversePrompt}
            onChange={(event) => setReversePrompt(event.target.value)}
            rows={12}
            placeholder="可使用变量：{desc}、{author}"
          />
          <span className="field-hint">可使用变量：{"{desc}"} 视频描述，{"{author}"} 作者。Gemini Key 复用上方 AI 视频拆解配置。</span>
        </label>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存反推配置"}
        </button>
      </form>
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}
