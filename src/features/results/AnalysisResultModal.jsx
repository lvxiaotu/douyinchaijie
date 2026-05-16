import { sections } from "../../constants/appConfig";
import { normalizeCommercialAnalysisResult } from "../../utils/appUtils";

export function AnalysisResultModal({ task, onClose }) {
  if (!task) return null;
  const result = normalizeCommercialAnalysisResult(task.result || {});
  const sections = [
    [
      "内容定位",
      [
        ["内容赛道", result.content_identity?.track],
        ["赛道适配", result.content_identity?.niche_fit],
        ["账号人设", result.content_identity?.account_persona],
      ],
    ],
    [
      "核心钩子",
      [
        ["开头3秒钩子", result.core_hook?.opening_3s],
        ["信息差/悬念", result.core_hook?.curiosity_gap],
        ["情绪触发", result.core_hook?.emotional_trigger],
        ["评论诱因", result.core_hook?.comment_bait],
      ],
    ],
    [
      "需求与场景",
      [
        ["痛点定位", result.need_context?.pain_point],
        ["应用场景", result.need_context?.application_scene],
        ["隐性欲望", result.need_context?.hidden_desire],
      ],
    ],
    [
      "产品表现",
      [
        ["利益点提炼", result.product_power?.core_benefit],
        ["转化瞬间", result.product_power?.trigger_moment],
        ["信任来源", result.product_power?.trust_builder],
        ["产品角色", result.product_power?.product_role],
      ],
    ],
    [
      "视觉与结构",
      [
        ["镜头结构", result.visual_structure?.shot_structure],
        ["可复用元素", result.visual_structure?.reusable_elements],
        ["时间线节奏", result.visual_structure?.timeline_beats],
        ["声音节奏", result.visual_structure?.audio_rhythm],
      ],
    ],
    [
      "文案公式",
      [
        ["标题公式", result.copywriting_formula?.title_formula],
        ["脚本公式", result.copywriting_formula?.script_formula],
        ["可复用金句", result.copywriting_formula?.golden_lines],
        ["行动号召", result.copywriting_formula?.cta],
      ],
    ],
    [
      "商业定位",
      [
        ["适合产品", result.market_positioning?.suitable_products],
        ["目标人群", result.market_positioning?.target_audience],
        ["创作方向", result.market_positioning?.creative_direction],
      ],
    ],
    [
      "复刻计划",
      [
        ["公式名", result.replication_plan?.pattern_name],
        ["可复刻公式", result.replication_plan?.reusable_formula],
        ["玄学改编", result.replication_plan?.mysticism_variant],
        ["AI小动物改编", result.replication_plan?.ai_pet_variant],
        ["AI带货改编", result.replication_plan?.ai_commerce_variant],
        ["制作难度", result.replication_plan?.difficulty],
        ["模仿优先级", result.replication_plan?.priority],
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
  const scoreRows = [
    ["爆款潜力", result.viral_scores?.viral_potential],
    ["模仿价值", result.viral_scores?.imitation_value],
    ["商业价值", result.viral_scores?.commerce_value],
    ["评论潜力", result.viral_scores?.comment_potential],
    ["综合评分", result.viral_scores?.overall],
  ].filter(([, value]) => value);
  const segmentBreakdowns = Array.isArray(result.segment_breakdowns) ? result.segment_breakdowns : [];
  const evidence = result.evidence || {};

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="modal-panel" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header">
          <div>
            <h2>AI 视频拆解结果</h2>
            <p>{task.title}</p>
          </div>
          <button className="text-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="analysis-result-body">
          <p>{result.summary || "暂无摘要"}</p>
          {(result.analysis_mode || evidence.evidence_path) && (
            <div className="analysis-section">
              <strong>证据包</strong>
              <div className="analysis-field">
                <span>分析模式</span>
                <p>{result.analysis_mode || "暂无内容"}</p>
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
            </div>
          )}
          {scoreRows.length > 0 && (
            <div className="analysis-score-grid">
              {scoreRows.map(([label, value]) => (
                <div className="analysis-score-card" key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
          )}
          {segmentBreakdowns.length > 0 && (
            <div className="analysis-section">
              <strong>分段拆解</strong>
              {segmentBreakdowns.map((segment, index) => (
                <div className="analysis-field" key={segment.segment_id || index}>
                  <span>
                    {segment.time_range || segment.segment_id || `片段 ${index + 1}`} · {segment.segment_role || "未标注角色"}
                  </span>
                  <p>
                    {[segment.hook, segment.conflict_or_value, segment.emotion, segment.copywriting_pattern, segment.commerce_signal, segment.replicable_point]
                      .filter(Boolean)
                      .join(" / ") || "暂无内容"}
                  </p>
                </div>
              ))}
            </div>
          )}
          {sections.map(([sectionTitle, rows]) => (
            <div className="analysis-section" key={sectionTitle}>
              <strong>{sectionTitle}</strong>
              {rows.map(([label, value]) => (
                <div className="analysis-field" key={label}>
                  <span>{label}</span>
                  <p>{value || "暂无内容"}</p>
                </div>
              ))}
            </div>
          ))}
          <details className="raw-json">
            <summary>查看原始 JSON</summary>
            <pre className="result-box">{JSON.stringify(result.raw_model_json || result, null, 2)}</pre>
          </details>
        </div>
      </section>
    </div>
  );
}
