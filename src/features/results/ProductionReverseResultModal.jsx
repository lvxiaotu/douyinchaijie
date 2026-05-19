import { buildProductionEvidenceUrl, renderTextList } from "../../utils/appUtils";
import { EvidenceGallery, LikelihoodPanel } from "./ProductionEvidence";

export function ProductionReverseResultModal({ task, onClose, pageMode = false }) {
  if (!task) return null;
  const result = task.result || {};
  const timelineBreakdown = Array.isArray(result.timeline_breakdown) ? result.timeline_breakdown : [];
  const segmentBreakdowns = Array.isArray(result.segment_production_breakdowns) ? result.segment_production_breakdowns : [];
  const overview = result.production_overview || {};
  const inventory = result.asset_inventory || {};
  const editingStyle = result.editing_style || {};
  const audioAnalysis = result.audio_analysis || {};
  const reproductionPlan = result.reproduction_plan || {};
  const evidence = result.evidence || {};
  const evidenceMedia = result.evidence_media || {};
  const overviewHighlights = [
    ["内容类型", overview.content_type],
    ["主流程", overview.main_workflow],
    ["可能工具", renderTextList(overview.estimated_tools)],
    ["制作难度", overview.difficulty],
    ["素材构成", renderTextList(overview.source_mix)],
    ["工具痕迹", renderTextList(overview.tool_signatures)],
    ["模板痕迹", overview.template_signature],
    ["自动化程度", overview.automation_level],
  ];
  const styleHighlights = [
    ["节奏", editingStyle.pace],
    ["镜头规律", editingStyle.shot_pattern],
    ["字幕风格", editingStyle.subtitle_style],
    ["字幕动效", editingStyle.subtitle_animation],
    ["转场风格", editingStyle.transition_style],
    ["贴纸风格", editingStyle.sticker_style],
    ["覆盖布局", editingStyle.overlay_layout],
    ["包装风格", editingStyle.packaging_style],
    ["镜头运动模式", editingStyle.camera_motion_pattern],
    ["卡点方式", editingStyle.rhythm_sync_style],
    ["人声类型", audioAnalysis.voice_type],
    ["声线特征", audioAnalysis.voice_character],
    ["BGM 类型", audioAnalysis.bgm_type],
    ["音效类型", renderTextList(audioAnalysis.sfx_type)],
    ["混音判断", audioAnalysis.mixing_guess],
    ["音画同步", audioAnalysis.beat_sync_style],
  ];
  const reproductionHighlights = [
    ["最少素材", renderTextList(reproductionPlan.minimum_assets_needed)],
    ["建议步骤", renderTextList(reproductionPlan.recommended_production_steps)],
    ["可交给 AI", renderTextList(reproductionPlan.can_be_generated_by_ai)],
    ["需手工剪辑", renderTextList(reproductionPlan.need_manual_editing)],
    ["可能工具链", renderTextList(reproductionPlan.likely_toolchain)],
    ["质检点", renderTextList(reproductionPlan.quality_control_points)],
  ];
  const topToolLikelihoods = overview.tool_likelihoods || [];
  const topSourceLikelihoods = overview.source_likelihoods || [];
  const isPageMode = Boolean(pageMode);

  return (
    <div className={isPageMode ? "result-page-host" : "modal-backdrop"} role={isPageMode ? undefined : "presentation"} onClick={isPageMode ? undefined : onClose}>
      <section
        className={`modal-panel ${isPageMode ? "result-page-panel" : ""}`}
        role={isPageMode ? "region" : "dialog"}
        aria-modal={isPageMode ? undefined : true}
        onClick={isPageMode ? undefined : (event) => event.stopPropagation()}
      >
        <div className="panel-header">
          <div>
            <h2>AI 制作方式反推结果</h2>
            <p>{task.title}</p>
          </div>
          <button className="text-button" type="button" onClick={onClose}>
            {isPageMode ? "返回列表" : "关闭"}
          </button>
        </div>
        <div className="analysis-result-body">
          <p>{result.summary || "暂无摘要"}</p>
          {(result.production_mode || evidence.evidence_path) && (
            <div className="analysis-section">
              <strong>证据包</strong>
              <div className="analysis-field">
                <span>分析模式</span>
                <p>{result.production_mode || "暂无内容"}</p>
              </div>
              <div className="analysis-field">
                <span>转写信息</span>
                <p>
                  {(evidence.transcript_provider || "未知转写器")} · {evidence.transcript_model || "未知模型"} ·{" "}
                  {evidence.transcript_segments_count || 0} 个转写片段 · {evidence.analysis_segments_count || 0} 个分析片段 ·{" "}
                  {evidence.keyframes_count || 0} 张关键帧
                </p>
              </div>
              {result.pipeline_error && (
                <div className="analysis-field">
                  <span>回退原因</span>
                  <p>{result.pipeline_error}</p>
                </div>
              )}
              <div className="analysis-field">
                <span>证据图统计</span>
                <p>
                  {evidenceMedia.segment_count || timelineBreakdown.length || 0} 个片段 · {evidenceMedia.keyframe_grid_count || 0} 张关键帧网格 ·{" "}
                  {evidenceMedia.keyframe_count || 0} 张关键帧 · {evidenceMedia.highlight_screenshot_count || 0} 张高价值截图
                </p>
              </div>
            </div>
          )}
          <LikelihoodPanel title="工具倾向评分" items={topToolLikelihoods} />
          <LikelihoodPanel title="素材来源倾向评分" items={topSourceLikelihoods} />
          <div className="analysis-section">
            <strong>制作总览</strong>
            {overviewHighlights.map(([label, value]) => (
              <div className="analysis-field" key={label}>
                <span>{label}</span>
                <p>{value || "暂无内容"}</p>
              </div>
            ))}
          </div>
          <div className="analysis-section">
            <strong>时间线拆解</strong>
            {timelineBreakdown.length ? (
              timelineBreakdown.map((item, index) => (
                <div className="analysis-field shot-replica-field" key={item.segment_id || index}>
                  <span>{item.time_range || item.segment_id || `片段 ${index + 1}`} {item.segment_role ? `· ${item.segment_role}` : ""}</span>
                  <dl className="shot-replica-list">
                    <div>
                      <dt>画面来源</dt>
                      <dd>{item.visual_source_type || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>剪辑动作</dt>
                      <dd>{Array.isArray(item.editing_actions) && item.editing_actions.length ? item.editing_actions.join(" / ") : "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>转场</dt>
                      <dd>{[item.transition, item.transition_confidence ? `信心 ${item.transition_confidence}` : ""].filter(Boolean).join(" / ") || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>滤镜/调色</dt>
                      <dd>{[item.filter_or_grade, item.filter_strength ? `强度 ${item.filter_strength}` : ""].filter(Boolean).join(" / ") || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>贴纸覆盖</dt>
                      <dd>{renderTextList(item.stickers_overlays)}</dd>
                    </div>
                    <div>
                      <dt>屏幕文字</dt>
                      <dd>{renderTextList(item.onscreen_text)}</dd>
                    </div>
                    <div>
                      <dt>音频判断</dt>
                      <dd>{renderTextList(item.audio_guess)}</dd>
                    </div>
                    <div>
                      <dt>信心</dt>
                      <dd>{item.confidence || "暂无内容"}</dd>
                    </div>
                    <div className="wide">
                      <dt>素材元素</dt>
                      <dd>{renderTextList(item.material_elements)}</dd>
                    </div>
                    <div className="wide">
                      <dt>来源推测</dt>
                      <dd>{renderTextList(item.source_provenance)}</dd>
                    </div>
                    <div className="wide">
                      <dt>字幕包装</dt>
                      <dd>{[item.subtitle_style, item.subtitle_animation].filter(Boolean).join(" / ") || "暂无内容"}</dd>
                    </div>
                    <div className="wide">
                      <dt>贴纸与布局</dt>
                      <dd>{[item.sticker_style, item.overlay_layout].filter(Boolean).join(" / ") || "暂无内容"}</dd>
                    </div>
                    <div className="wide">
                      <dt>镜头与轨道</dt>
                      <dd>{[item.camera_movement_guess, renderTextList(item.track_layer_guess)].filter(Boolean).join(" / ") || "暂无内容"}</dd>
                    </div>
                    <div className="wide">
                      <dt>卡点说明</dt>
                      <dd>{renderTextList(item.sync_points)}</dd>
                    </div>
                    <div className="wide">
                      <dt>生成/工具猜测</dt>
                      <dd>{[renderTextList(item.generation_guess), renderTextList(item.tool_signatures), item.template_signature].filter((value) => value && value !== "暂无内容").join(" / ") || "暂无内容"}</dd>
                    </div>
                    <div className="wide">
                      <dt>判断依据</dt>
                      <dd>{renderTextList(item.evidence)}</dd>
                    </div>
                    {item.notes && (
                      <div className="wide">
                        <dt>备注</dt>
                        <dd>{item.notes}</dd>
                      </div>
                    )}
                  </dl>
                  <LikelihoodPanel title="片段工具倾向" items={item.tool_likelihoods} />
                  <LikelihoodPanel title="片段来源倾向" items={item.source_likelihoods} />
                  <details className="production-evidence-details">
                    <summary>查看该片段证据图</summary>
                    <div className="production-evidence-stack">
                      {item.evidence_media?.keyframe_grid?.image_path ? (
                        <div className="production-evidence-block">
                          <strong>关键帧网格</strong>
                          <div className="production-evidence-grid single-grid">
                            <article className="production-evidence-card">
                              <img
                                src={buildProductionEvidenceUrl(item.evidence_media.keyframe_grid.image_path)}
                                alt={`${item.time_range || item.segment_id || `片段 ${index + 1}`} 关键帧网格`}
                                loading="lazy"
                              />
                              <div className="production-evidence-meta">
                                <span>关键帧网格</span>
                                <p>用于辅助判断这段画面的节奏、转场和包装连续性。</p>
                              </div>
                            </article>
                          </div>
                        </div>
                      ) : null}
                      <EvidenceGallery title="关键帧" items={item.evidence_media?.keyframes} />
                      <EvidenceGallery title="高价值截图" items={item.evidence_media?.highlight_screenshots} />
                    </div>
                  </details>
                </div>
              ))
            ) : (
              <p>暂无时间线拆解</p>
            )}
          </div>
          {segmentBreakdowns.length > 0 && (
            <div className="analysis-section">
              <strong>分段证据判断</strong>
              {segmentBreakdowns.map((segment, index) => (
                <div className="analysis-field" key={segment.segment_id || index}>
                  <span>{segment.time_range || segment.segment_id || `片段 ${index + 1}`}</span>
                  <p>
                    {[
                      segment.visual_source_type,
                      renderTextList(segment.editing_actions),
                      segment.transition,
                      segment.filter_or_grade,
                      segment.subtitle_style,
                      segment.sticker_style,
                    ].filter(Boolean).join(" / ") || "暂无内容"}
                  </p>
                </div>
              ))}
            </div>
          )}
          <div className="analysis-section">
            <strong>素材盘点</strong>
            {[
              ["视频素材", inventory.video_materials],
              ["图片素材", inventory.image_materials],
              ["音频素材", inventory.audio_materials],
              ["贴纸图形", inventory.graphics_and_stickers],
              ["文字元素", inventory.text_elements],
              ["来源推测", inventory.source_provenance],
            ].map(([label, value]) => (
              <div className="analysis-field" key={label}>
                <span>{label}</span>
                <p>{renderTextList(value)}</p>
              </div>
            ))}
          </div>
          <div className="analysis-section">
            <strong>剪辑与音频风格</strong>
            {styleHighlights.map(([label, value]) => (
              <div className="analysis-field" key={label}>
                <span>{label}</span>
                <p>{value || "暂无内容"}</p>
              </div>
            ))}
          </div>
          <div className="analysis-section">
            <strong>复做方案</strong>
            {reproductionHighlights.map(([label, value]) => (
              <div className="analysis-field" key={label}>
                <span>{label}</span>
                <p>{value || "暂无内容"}</p>
              </div>
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
