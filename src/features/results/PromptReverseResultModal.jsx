import { Badge } from "../../components/common/index";

export function PromptReverseResultModal({ task, onClose }) {
  if (!task) return null;
  const result = task.result || {};
  const shotPrompts = Array.isArray(result.shot_prompts) ? result.shot_prompts : [];
  const audioScript = Array.isArray(result.audio_script) ? result.audio_script : [];
  const segmentReconstructions = Array.isArray(result.segment_reconstructions) ? result.segment_reconstructions : [];

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="modal-panel" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <h2>AI 提示词反推结果</h2>
            <p>{task.title}</p>
          </div>
          <button className="text-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="analysis-result-body">
          <p>{result.summary || "暂无摘要"}</p>
          {result.reconstruction_strategy && (
            <div className="analysis-section">
              <strong>复刻策略</strong>
              <p>{result.reconstruction_strategy}</p>
            </div>
          )}
          <div className="analysis-section">
            <strong>完整提示词</strong>
            <p>{result.master_prompt || "暂无内容"}</p>
          </div>
          <div className="analysis-section">
            <strong>负向提示词</strong>
            <p>{result.negative_prompt || "暂无内容"}</p>
          </div>
          <div className="analysis-section">
            <strong>脚本时间线</strong>
            {audioScript.length ? (
              audioScript.map((item, index) => (
                <div className="analysis-field" key={index}>
                  <span>{item.time_range || `片段 ${index + 1}`}</span>
                  <p>{item.line || item.text || "暂无内容"}</p>
                </div>
              ))
            ) : (
              <p>暂无脚本时间线</p>
            )}
          </div>
          <div className="analysis-section">
            <strong>镜头级复刻</strong>
            {shotPrompts.length ? (
              shotPrompts.map((item, index) => (
                <div className="analysis-field shot-replica-field" key={index}>
                  <span>{item.shot || `镜头 ${index + 1}`} {item.time_range ? `· ${item.time_range}` : ""}</span>
                  <dl className="shot-replica-list">
                    <div>
                      <dt>脚本</dt>
                      <dd>{item.script_line || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>画面</dt>
                      <dd>{item.visual_description || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>首帧</dt>
                      <dd>{item.first_frame || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>尾帧</dt>
                      <dd>{item.last_frame || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>运镜</dt>
                      <dd>{item.camera_movement || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>主体动作</dt>
                      <dd>{item.subject_motion || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>构图</dt>
                      <dd>{item.composition || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>光色</dt>
                      <dd>{item.lighting_color || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>转场</dt>
                      <dd>{item.transition || "暂无内容"}</dd>
                    </div>
                    <div className="wide">
                      <dt>镜头提示词</dt>
                      <dd>{item.prompt || "暂无内容"}</dd>
                    </div>
                    <div className="wide">
                      <dt>负向提示词</dt>
                      <dd>{item.negative_prompt || "暂无内容"}</dd>
                    </div>
                  </dl>
                  {Array.isArray(item.reference_frames) && item.reference_frames.length > 0 && (
                    <p>参考帧：{item.reference_frames.join(" / ")}</p>
                  )}
                </div>
              ))
            ) : (
              <p>暂无镜头级复刻内容</p>
            )}
          </div>
          {segmentReconstructions.length > 0 && (
            <div className="analysis-section">
              <strong>分段证据复刻</strong>
              {segmentReconstructions.map((segment, index) => (
                <div className="analysis-field" key={segment.segment_id || index}>
                  <span>{segment.time_range || segment.segment_id || `片段 ${index + 1}`}</span>
                  <p>{segment.segment_script || segment.continuity_notes || "暂无内容"}</p>
                  {Array.isArray(segment.shots) && segment.shots.length > 0 && (
                    <p>{segment.shots.map((shot) => `${shot.shot || "镜头"}：${shot.prompt || shot.visual_description || ""}`).join("\n")}</p>
                  )}
                </div>
              ))}
            </div>
          )}
          <div className="analysis-section">
            <strong>风格关键词</strong>
            <div className="breakdown-tags">
              {(result.style_keywords || []).map((keyword) => (
                <Badge key={keyword}>{keyword}</Badge>
              ))}
            </div>
          </div>
          <div className="analysis-section">
            <strong>使用建议</strong>
            {(result.usage_notes || []).map((note, index) => (
              <p key={index}>{note}</p>
            ))}
          </div>
          <details className="raw-json">
            <summary>查看原始 JSON</summary>
            <pre className="result-box">{JSON.stringify(task, null, 2)}</pre>
          </details>
        </div>
      </section>
    </div>
  );
}
