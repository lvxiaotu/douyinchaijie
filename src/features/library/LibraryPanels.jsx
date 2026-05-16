import { archivePresentation } from "../../utils/appUtils";

export function LibraryArchiveGroup({ title, desc, items, children }) {
  if (!items.length) return null;
  return (
    <section className="library-tool-section">
      <div className="library-tool-heading">
        <div>
          <span>归档结果</span>
          <h2>{title}</h2>
        </div>
        <p>{desc}</p>
      </div>
      <div className="library-card-grid">{children}</div>
    </section>
  );
}

export function LibraryItemModal({ item, onClose }) {
  if (!item) return null;
  const presentation = item.presentation || archivePresentation(item);
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-panel">
        <div className="panel-header">
          <div>
            <h2>{presentation.headline}</h2>
            <p>{presentation.toolDetail}</p>
          </div>
          <button className="text-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="result-grid">
          <article>
            <span>摘要</span>
            <p>{presentation.summary}</p>
          </article>
          {presentation.highlights.map(([label, value]) => (
            <article key={label}>
              <span>{label}</span>
              <p>{value}</p>
            </article>
          ))}
          {presentation.tags.length > 0 && (
            <article>
              <span>标签</span>
              <p>{presentation.tags.join(" / ")}</p>
            </article>
          )}
        </div>
        <pre className="result-box">{JSON.stringify(item.raw || item, null, 2)}</pre>
      </div>
    </div>
  );
}
