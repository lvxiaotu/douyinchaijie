import { buildProductionEvidenceUrl, normalizeLikelihoods } from "../../utils/appUtils";

export function EvidenceGallery({ title, items }) {
  if (!Array.isArray(items) || !items.length) return null;
  return (
    <div className="production-evidence-block">
      <strong>{title}</strong>
      <div className="production-evidence-grid">
        {items.map((item, index) => {
          const imagePath = item?.image_path || "";
          const src = buildProductionEvidenceUrl(imagePath);
          return (
            <article className="production-evidence-card" key={`${title}-${imagePath || index}`}>
              {src ? <img src={src} alt={item?.time_label || `${title} ${index + 1}`} loading="lazy" /> : <div className="empty-result">暂无图片</div>}
              <div className="production-evidence-meta">
                <span>{item?.time_label || `证据 ${index + 1}`}</span>
                <p>{item?.reason || "暂无说明"}</p>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

export function LikelihoodPanel({ title, items }) {
  const normalizedItems = normalizeLikelihoods(items);
  if (!normalizedItems.length) return null;
  return (
    <div className="analysis-section">
      <strong>{title}</strong>
      <div className="production-likelihood-grid">
        {normalizedItems.map((item) => (
          <article className="production-likelihood-card" key={`${title}-${item.name}`}>
            <div className="production-likelihood-head">
              <span>{item.name}</span>
              <strong>{item.score != null ? `${item.score}` : "-"}</strong>
            </div>
            <div className="progress production-likelihood-progress" aria-label={`${item.name} 倾向评分`}>
              <span style={{ width: `${Math.max(0, Math.min(100, item.score || 0))}%` }} />
            </div>
            <p>{item.reason || "暂无依据说明"}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
