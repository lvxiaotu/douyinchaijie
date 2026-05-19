import { Badge } from "../../components/common/index";
import { normalizeModelRuns } from "../../utils/appUtils";

export function ModelRunSummary({ runs, compact = false }) {
  const modelRuns = normalizeModelRuns(runs);
  if (!modelRuns.length) return null;

  const failed = modelRuns.filter((run) => run.status === "failed").length;
  const fallback = modelRuns.filter((run) => run.fallbackLabel).length;

  return (
    <section className={`analysis-section model-run-section ${compact ? "compact" : ""}`}>
      <strong>模型运行轨迹</strong>
      <div className="model-run-overview">
        <Badge status={failed ? "error" : "done"}>{modelRuns.length} 次调用</Badge>
        {fallback > 0 && <Badge status="running">{fallback} 次 fallback</Badge>}
      </div>
      <div className="model-run-list">
        {modelRuns.map((run) => (
          <article className="model-run-card" key={run.id}>
            <div className="model-run-head">
              <div>
                <span>{run.purposeLabel}</span>
                <p>{run.provider} / {run.model}</p>
              </div>
              <Badge status={run.statusClass}>{run.statusLabel}</Badge>
            </div>
            <div className="model-run-meta">
              <span>{run.chunkLabel}</span>
              <span>{run.latencyLabel}</span>
              <span>{run.tokenLabel}</span>
              {run.timeLabel && <span>{run.timeLabel}</span>}
            </div>
            {run.fallbackLabel && <p className="model-run-note">fallback: {run.fallbackLabel}</p>}
            {run.fallbackError && <p className="model-run-note error">{run.fallbackError}</p>}
            {run.errorMessage && <p className="model-run-note error">{run.errorMessage}</p>}
          </article>
        ))}
      </div>
    </section>
  );
}
