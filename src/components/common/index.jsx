import { statusText } from "../../constants/appConfig";

export function Badge({ status, children }) {
  return <span className={`badge ${status || ""}`}>{children}</span>;
}

export function ToolCard({ tool, onOpen }) {
  return (
    <article className="tool-card">
      <header>
        <div className="tool-title">
          <span className="tool-avatar">{tool.icon}</span>
          <div>
            <h3>{tool.name}</h3>
            <p>{tool.updated}</p>
          </div>
        </div>
        <Badge status={tool.status}>{statusText[tool.status] || tool.status}</Badge>
      </header>
      <p>{tool.desc}</p>
      <div className="tool-meta">
        {tool.tags.map((tag) => (
          <Badge key={tag}>{tag}</Badge>
        ))}
      </div>
      {onOpen && (
        <div className="tool-card-actions">
          <button className="text-button" type="button" onClick={() => onOpen(tool)}>
            打开工具
          </button>
        </div>
      )}
    </article>
  );
}

export function JobRow({ job, table }) {
  const progress = Math.max(0, Math.min(100, job.progress));

  if (table) {
    return (
      <tr>
        <td>{job.name}</td>
        <td>{job.tool}</td>
        <td>
          <Badge status={job.status}>{statusText[job.status] || job.status}</Badge>
        </td>
        <td>
          <div className="table-progress">
            <div className="progress">
              <span style={{ width: `${progress}%` }} />
            </div>
            <span>{progress}%</span>
          </div>
        </td>
        <td>{job.updated}</td>
      </tr>
    );
  }

  return (
    <article className="job-row">
      <div className="panel-header">
        <strong>{job.name}</strong>
        <Badge status={job.status}>{statusText[job.status] || job.status}</Badge>
      </div>
      <div className="progress" aria-label={`进度 ${progress}%`}>
        <span style={{ width: `${progress}%` }} />
      </div>
      <div className="job-meta">
        <span>{job.tool}</span>
        <span>{job.updated}</span>
      </div>
    </article>
  );
}
