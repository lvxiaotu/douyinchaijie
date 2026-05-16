import { useEffect, useState } from "react";
import { Badge } from "../../components/common/index";
import { fetchAiProductionReverseConfig, fetchAiProductionReverseStatus, saveAiProductionReverseConfig } from "../../services/api";

export function AiProductionReverseSettingsPanel() {
  const [outputDir, setOutputDir] = useState("./data/runtime/ai_production_reverse");
  const [pipelineMode, setPipelineMode] = useState("evidence");
  const [maxSegments, setMaxSegments] = useState(18);
  const [productionPrompt, setProductionPrompt] = useState("");
  const [statusInfo, setStatusInfo] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchAiProductionReverseConfig()
      .then((config) => {
        setOutputDir(config.output_dir || "./data/runtime/ai_production_reverse");
        setPipelineMode(config.pipeline_mode || "evidence");
        setMaxSegments(config.max_segments || 18);
        setProductionPrompt(config.production_prompt || "");
      })
      .catch((err) => setError(err.message || String(err)));
    fetchAiProductionReverseStatus()
      .then(setStatusInfo)
      .catch(() => setStatusInfo(null));
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await saveAiProductionReverseConfig({ outputDir, pipelineMode, maxSegments, productionPrompt });
      setMessage("AI 制作方式反推配置已保存。");
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
          <h2>AI 制作方式反推配置</h2>
          <p>配置素材/剪辑反推流程、片段上限和输出模板。模型连接请到“AI 模型”里统一设置。</p>
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
            <option value="evidence">证据管线优先</option>
            <option value="auto">证据失败后回退整段视频</option>
            <option value="direct">整段视频直传</option>
          </select>
          <span className="field-hint">建议优先用证据管线：转写 + 分段 + 关键帧网格 + 时间线制作分析。</span>
        </label>
        <label>
          最大分析片段数
          <input type="number" min="1" max="100" value={maxSegments} onChange={(event) => setMaxSegments(event.target.value)} />
          <span className="field-hint">数值越高，时间线越完整，但耗时和 API 成本也会增加。</span>
        </label>
        <label className="textarea-label">
          反推提示词模板
          <textarea
            value={productionPrompt}
            onChange={(event) => setProductionPrompt(event.target.value)}
            rows={14}
            placeholder="可使用变量：{desc}、{author}"
          />
          <span className="field-hint">建议要求模型谨慎判断，不确定的地方输出“无法确认”或“推测”。</span>
        </label>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存制作反推配置"}
        </button>
      </form>
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}
