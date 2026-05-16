import { useEffect, useState } from "react";
import { Badge } from "../../components/common/index";
import { inspectJianyingDraft, listJianyingDraftProjects, openJianyingDraftPath } from "../../services/api";
import { buildMaterialIndex, flattenDraftSegments, formatCanvasSize, formatDuration, formatMicroseconds, formatTimestamp, materialSubtitle, materialTitle, objectEntries } from "../../utils/appUtils";

export function DraftInspectorPanel() {
  const [draftRoot, setDraftRoot] = useState("D:\\jianying\\JianyingPro Drafts");
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [projectDetail, setProjectDetail] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    handleLoadProjects().catch(() => {});
  }, []);

  async function handleLoadProjects() {
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const data = await listJianyingDraftProjects(draftRoot);
      setProjects(data.projects || []);
      setSelectedProject(null);
      setProjectDetail(null);
      setMessage(`已加载 ${data.projects?.length || 0} 个剪映项目`);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectProject(project) {
    setSelectedProject(project);
    setProjectDetail(null);
    setDetailOpen(true);
    setDetailLoading(true);
    setMessage("");
    setError("");
    try {
      const data = await inspectJianyingDraft(project.draft_path);
      setProjectDetail(data);
    } catch (err) {
      setProjectDetail({
        draft_path: project.draft_path,
        summary: {},
        details: {},
        draft_content: {},
        needs_decrypt: true,
        error: err.message || String(err),
      });
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleOpenDraftPath(path) {
    try {
      await openJianyingDraftPath(path);
    } catch (err) {
      setError(err.message || String(err));
    }
  }

  async function handleCopyPath(path) {
    try {
      await navigator.clipboard.writeText(path);
      setMessage("草稿路径已复制");
    } catch (err) {
      setError(err.message || String(err));
    }
  }

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>查看草稿</h2>
          <p>按项目查看剪映草稿，点击项目后读取 draft_content.json。</p>
        </div>
        <Badge status="ready">Inspect</Badge>
      </div>

      <section className="collector-card">
        <h3>剪映草稿根目录</h3>
        <div className="collector-fields">
          <label>
            Draft Root
            <input value={draftRoot} onChange={(event) => setDraftRoot(event.target.value)} placeholder="输入 JianyingPro Drafts 目录绝对路径" />
          </label>
        </div>
        <div className="script-action-strip">
          <button className="primary-button" type="button" onClick={handleLoadProjects} disabled={loading || !draftRoot.trim()}>
            {loading ? "扫描中" : "扫描项目"}
          </button>
          <button className="text-button" type="button" onClick={() => handleOpenDraftPath(draftRoot)} disabled={!draftRoot.trim()}>
            打开目录
          </button>
          <button className="text-button" type="button" onClick={() => handleCopyPath(draftRoot)} disabled={!draftRoot.trim()}>
            复制路径
          </button>
        </div>
      </section>

      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}

      <section className="collector-card">
        <div className="section-title-row">
          <h3>剪映项目</h3>
          <Badge>{projects.length}</Badge>
        </div>
        <div className="draft-project-list">
          {projects.length ? projects.map((project) => (
            <article
              className={`draft-project-row ${selectedProject?.draft_path === project.draft_path ? "active" : ""} ${project.needs_decrypt ? "needs-decrypt" : ""}`}
              key={project.draft_path}
            >
              <div>
                <strong>{project.name}</strong>
                <p>{project.draft_path}</p>
              </div>
              <div className="draft-project-meta">
                <Badge status={project.needs_decrypt ? "error" : "ready"}>
                  {project.needs_decrypt ? "待解密" : "可查看"}
                </Badge>
                <span>{formatTimestamp(project.last_modified)}</span>
                <button className="text-button" type="button" onClick={() => handleSelectProject(project)}>
                  点击查看
                </button>
              </div>
            </article>
          )) : <div className="empty-result">还没有扫描到剪映项目。</div>}
        </div>
      </section>

      {detailOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setDetailOpen(false)}>
          <section className="draft-detail-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <header className="draft-detail-modal-head">
              <div>
                <h3>{selectedProject?.name || "草稿详情"}</h3>
                <p>{selectedProject?.draft_path || ""}</p>
              </div>
              <div className="draft-detail-actions">
                {detailLoading ? <Badge status="running">读取中</Badge> : projectDetail?.needs_decrypt ? <Badge status="error">待解密</Badge> : <Badge status="ready">draft_content.json</Badge>}
                <button className="text-button" type="button" onClick={() => setDetailOpen(false)}>关闭</button>
              </div>
            </header>
          {detailLoading ? (
            <div className="running-note">正在读取 draft_content.json...</div>
          ) : projectDetail?.needs_decrypt ? (
            <div className="error-box">{projectDetail.error || "draft_content.json 不是标准格式，可能需要先解密。"}</div>
          ) : projectDetail ? (
            <DraftDetailContent projectDetail={projectDetail} />
          ) : null}
          </section>
        </div>
      )}
    </section>
  );
}

export function DraftDetailContent({ projectDetail }) {
  const content = projectDetail.draft_content || {};
  const materialIndex = buildMaterialIndex(content.materials);
  const segments = flattenDraftSegments(content.tracks, materialIndex);
  const readable = projectDetail.readable || {};
  const identity = readable.identity || {};
  const canvas = readable.canvas || {};
  const timeline = readable.timeline || {};
  const materials = readable.materials || {};
  const texts = readable.texts || {};
  const effects = readable.effects || {};
  const projectFiles = readable.project_files || [];

  return (
    <div className="draft-detail-body">
      <section className="draft-detail-section">
        <h4>草稿概览</h4>
        <div className="workflow-summary-grid compact">
          <article className="workflow-summary-card hero">
            <strong>{identity.name || projectDetail.summary?.draft_name || "未命名草稿"}</strong>
            <p>{readable.overview || "这里会总结这个草稿的时长、轨道和主要素材结构。"}</p>
          </article>
          <article className="workflow-summary-card">
            <strong>创建时间</strong>
            <p>{identity.created_at || "未记录"}</p>
          </article>
          <article className="workflow-summary-card">
            <strong>最后修改</strong>
            <p>{identity.modified_at || projectDetail.summary?.modified_at || "未记录"}</p>
          </article>
        </div>
      </section>

      <div className="draft-canvas-detail">
        <div><strong>画布比例</strong><p>{projectDetail.summary?.canvas?.ratio || "-"}</p></div>
        <div><strong>画布尺寸</strong><p>{canvas.size || formatCanvasSize(projectDetail.summary?.canvas)}</p></div>
        <div><strong>草稿时长</strong><p>{formatDuration(projectDetail.summary?.duration_seconds)}</p></div>
        <div><strong>轨道数量</strong><p>{projectDetail.summary?.track_count ?? "-"}</p></div>
        <div><strong>轨道类型</strong><p>{Array.isArray(projectDetail.summary?.track_types) ? projectDetail.summary.track_types.join(", ") : "-"}</p></div>
        <div><strong>素材组数</strong><p>{projectDetail.summary?.material_groups ?? "-"}</p></div>
        <div><strong>Draft ID</strong><p>{projectDetail.summary?.draft_id || projectDetail.details?.id || "-"}</p></div>
        <div><strong>版本</strong><p>{projectDetail.details?.new_version || projectDetail.details?.version || "-"}</p></div>
      </div>

      <section className="draft-detail-section">
        <h4>时间线说明</h4>
        <div className="workflow-summary-grid compact">
          <article className="workflow-summary-card">
            <strong>轨道结构</strong>
            <p>{timeline.track_headline || "暂无轨道摘要"}</p>
          </article>
          <article className="workflow-summary-card">
            <strong>可读文字</strong>
            <p>{texts.headline || "暂无文字摘要"}</p>
          </article>
          <article className="workflow-summary-card">
            <strong>素材来源</strong>
            <p>{materials.headline || "暂无素材摘要"}</p>
          </article>
        </div>
      </section>

      <section className="draft-detail-section">
        <h4>轨道</h4>
        <div className="draft-track-list">
          {timeline.track_explanations?.length ? timeline.track_explanations.map((track) => (
            <article className="draft-track-row" key={track.id || `${track.type}-${track.segments}`}>
              <strong>{track.title}</strong>
              <span>{track.segments} 段</span>
              <p>{track.explanation}</p>
            </article>
          )) : <div className="empty-result">没有轨道数据。</div>}
        </div>
      </section>

      {texts.items?.length > 0 && (
        <section className="draft-detail-section">
          <h4>文字内容</h4>
          <div className="draft-material-items">
            {texts.items.map((item, index) => (
              <article className="draft-material-row" key={`${item.title}-${index}`}>
                <strong>{item.title}</strong>
                <p>{item.content}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      {materials.sources?.length > 0 && (
        <section className="draft-detail-section">
          <h4>素材来源</h4>
          <div className="draft-material-items">
            {materials.sources.map((item, index) => (
              <article className="draft-material-row" key={`${item.group}-${item.path}-${index}`}>
                <strong>{item.title}</strong>
                <p>{item.path}</p>
                <code>{item.group}</code>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="draft-detail-section">
        <h4>时间线片段</h4>
        <div className="draft-segment-table">
          <div className="draft-segment-head">
            <span>轨道</span><span>开始</span><span>时长</span><span>素材</span><span>文本/路径</span>
          </div>
          {segments.length ? segments.map((segment) => (
            <div className="draft-segment-row" key={segment.id}>
              <span>{segment.trackType}</span>
              <span>{formatMicroseconds(segment.start)}</span>
              <span>{formatMicroseconds(segment.duration)}</span>
              <span>{segment.materialType || segment.materialId || "-"}</span>
              <p>{segment.preview || "-"}</p>
            </div>
          )) : <div className="empty-result">没有片段数据。</div>}
        </div>
      </section>

      <section className="draft-detail-section">
        <h4>素材明细</h4>
        <div className="draft-material-list">
          {objectEntries(content.materials).length ? objectEntries(content.materials).map(([group, items]) => (
            <details className="draft-material-group" key={group}>
              <summary>{group} <Badge>{Array.isArray(items) ? items.length : 0}</Badge></summary>
              <div className="draft-material-items">
                {Array.isArray(items) && items.length ? items.map((item, index) => (
                  <article className="draft-material-row" key={item.id || `${group}-${index}`}>
                    <strong>{materialTitle(item, index)}</strong>
                    <p>{materialSubtitle(item)}</p>
                    <code>{item.id || "-"}</code>
                  </article>
                )) : <div className="empty-result">没有素材条目。</div>}
              </div>
            </details>
          )) : <div className="empty-result">没有素材数据。</div>}
        </div>
      </section>

      <section className="draft-detail-section">
        <h4>特效 / 配置</h4>
        <div className="workflow-summary-card">
          <strong>解释</strong>
          <p>{effects.headline || "无明显特效或配置项。"}</p>
          <div className="draft-chip-grid">
            {objectEntries(projectDetail.details?.keyframe_counts).map(([key, value]) => <span key={key}>{key}: {value}</span>)}
            {(projectDetail.details?.config_keys || []).map((key) => <span key={key}>config: {key}</span>)}
            {!objectEntries(projectDetail.details?.keyframe_counts).length && !(projectDetail.details?.config_keys || []).length && <span>无关键帧配置</span>}
          </div>
        </div>
      </section>

      <section className="draft-detail-section">
        <h4>项目文件</h4>
        <div className="draft-material-items">
          {projectFiles.length ? projectFiles.map((item) => (
            <article className="draft-material-row" key={item.relative_path || item.name}>
              <strong>{item.name}</strong>
              <p>{item.relative_path}</p>
              <code>{item.status}{item.needs_decrypt ? " · 可能需解密" : ""}</code>
            </article>
          )) : <div className="empty-result">没有列出项目文件。</div>}
        </div>
      </section>

      <section className="draft-detail-section">
        <h4>草稿结构字段</h4>
        <div className="draft-chip-grid">
          {Object.keys(content).map((key) => <span key={key}>{key}</span>)}
        </div>
      </section>

      <details className="draft-json-panel">
        <summary>查看完整 draft_content.json</summary>
        <pre className="result-box">{JSON.stringify(content, null, 2)}</pre>
      </details>
    </div>
  );
}
