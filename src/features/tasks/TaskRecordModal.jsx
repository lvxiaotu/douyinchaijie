import { Badge } from "../../components/common/index";
import { statusText } from "../../constants/appConfig";
import { commentCollectionLabel, commentCollectionTone } from "../../utils/appUtils";
import { ModelRunSummary } from "../results/ModelRunSummary";
import { Archive } from "lucide-react";

export function TaskRecordModal({
  record,
  archivedIds,
  onClose,
  onOpenResult,
  onArchiveTask,
  onDeleteTask,
  onRetryComments,
}) {
  if (!record?.task) return null;

  const { task, title, type } = record;
  const resultSummary =
    type === "analysis"
      ? task.result?.summary || ""
      : type === "runninghub_tts"
        ? task.resultSummary || task.outputItems?.[0]?.fileUrl || task.outputItems?.[0]?.url || ""
        : type === "text_to_assets"
          ? task.resultSummary || task.result?.summary || task.result?.creative_direction || ""
        : task.result?.summary || task.result?.master_prompt || "";
  const createdAt = task.created_at
    ? new Date(task.created_at * 1000).toLocaleString("zh-CN")
    : "";
  const updatedAt = task.updated_at
    ? new Date(task.updated_at * 1000).toLocaleString("zh-CN")
    : task.updated || "";
  const commentCollection = task.commentCollection;
  const canRetryComments = type === "analysis" && commentCollection?.status === "failed";

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="modal-panel task-detail-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header task-detail-header">
          <div className="task-detail-header-main">
            <h2>{task.title}</h2>
            <p>{title}</p>
            <div className="task-detail-badges">
              <Badge status={task.status}>{statusText[task.status] || task.status}</Badge>
              <Badge>{task.provider || title}</Badge>
            </div>
          </div>
          <div className="task-detail-header-actions">
            {task.status === "done" && onOpenResult && (
              <button className="primary-button" type="button" onClick={() => onOpenResult(task)}>
                查看完整结果
              </button>
            )}
            <button className="text-button" type="button" onClick={onClose}>
              关闭
            </button>
          </div>
        </div>

        <div className="task-detail-meta-grid">
          <article className="task-detail-meta-card">
            <span>当前状态</span>
            <p>{task.message || "等待后端更新"}</p>
          </article>
          <article className="task-detail-meta-card">
            <span>任务进度</span>
            <p>{task.progress}%</p>
          </article>
          <article className="task-detail-meta-card">
            <span>更新时间</span>
            <p>{updatedAt || "暂无记录"}</p>
          </article>
          {createdAt && (
            <article className="task-detail-meta-card">
              <span>创建时间</span>
              <p>{createdAt}</p>
            </article>
          )}
          <article className="task-detail-meta-card">
            <span>任务 ID</span>
            <p>{task.id}</p>
          </article>
          {type === "analysis" && (
            <article className="task-detail-meta-card">
              <span>评论数据</span>
              <p>{commentCollectionLabel(commentCollection)}</p>
            </article>
          )}
          {type === "runninghub_tts" && task.remoteTaskId && (
            <article className="task-detail-meta-card">
              <span>远端任务 ID</span>
              <p>{task.remoteTaskId}</p>
            </article>
          )}
          {type === "runninghub_tts" && (task.workflowId || task.workflowKey) && (
            <article className="task-detail-meta-card">
              <span>工作流</span>
              <p>{task.workflowId || task.workflowKey}</p>
            </article>
          )}
          <article className="task-detail-meta-card">
            <span>事件数量</span>
            <p>{task.events?.length || 0} 条</p>
          </article>
        </div>

        <div className="progress" aria-label={`进度 ${task.progress}%`}>
          <span style={{ width: `${task.progress}%` }} />
        </div>

        {resultSummary && (
          <section className="analysis-section task-detail-section">
            <strong>结果摘要</strong>
            <p>{resultSummary}</p>
          </section>
        )}

        {type === "runninghub_tts" && task.outputItems?.length > 0 && (
          <section className="analysis-section task-detail-section">
            <strong>输出文件</strong>
            {task.outputItems.map((item, index) => (
              <div className="analysis-field" key={item.fileUrl || item.url || item.fileName || index}>
                <span>{item.fileName || `输出 ${index + 1}`}</span>
                <p>
                  {item.fileUrl || item.url ? (
                    <a className="result-link" href={item.fileUrl || item.url} target="_blank" rel="noreferrer">
                      {item.fileUrl || item.url}
                    </a>
                  ) : (
                    "暂无下载链接"
                  )}
                </p>
                {((item.outputType || "").toLowerCase() === "mp3" ||
                  (item.outputType || "").toLowerCase() === "wav" ||
                  (item.outputType || "").toLowerCase() === "ogg" ||
                  (item.fileUrl || item.url)) && (item.fileUrl || item.url) && (
                  <audio
                    controls
                    preload="none"
                    src={item.fileUrl || item.url}
                    style={{ width: "100%", marginTop: "0.5rem" }}
                  />
                )}
              </div>
            ))}
          </section>
        )}

        {type === "text_to_assets" && (
          <section className="analysis-section task-detail-section">
            <strong>结果概览</strong>
            <div className="result-grid">
              <article>
                <span>创意方向</span>
                <p>{task.creativeDirection?.positioning || task.creativeDirection?.visual_style || "暂无内容"}</p>
              </article>
              <article>
                <span>A-Roll 主镜头</span>
                <p>{Array.isArray(task.aRollItems) ? `${task.aRollItems.length} 条` : "0 条"}</p>
              </article>
              <article>
                <span>B-Roll 补充镜头</span>
                <p>{Array.isArray(task.bRollItems) ? `${task.bRollItems.length} 条` : "0 条"}</p>
              </article>
              <article>
                <span>Voiceover</span>
                <p>{Array.isArray(task.audioPlan?.voiceover) ? `${task.audioPlan.voiceover.length} 条` : "0 条"}</p>
              </article>
              <article>
                <span>执行备注</span>
                <p>{Array.isArray(task.notes) ? `${task.notes.length} 条` : "0 条"}</p>
              </article>
            </div>
          </section>
        )}

        {task.error && <div className="error-box">{task.error}</div>}

        {type === "analysis" && <ModelRunSummary runs={task.modelRuns || task.result?.model_runs || task.model_runs} compact />}

        {type === "analysis" && commentCollection && (
          <section className="analysis-section task-detail-section">
            <strong>AI 拆解评论数据步骤</strong>
            <div className="task-detail-badges">
              <Badge status={commentCollectionTone(commentCollection)}>{commentCollectionLabel(commentCollection)}</Badge>
            </div>
            {commentCollection.error && <p className="field-hint">评论数据获取失败，但拆解任务已继续执行：{commentCollection.error}</p>}
            {canRetryComments && onRetryComments && (
              <button className="text-button" type="button" onClick={() => onRetryComments(task)}>
                再次获取评论数据
              </button>
            )}
          </section>
        )}

        <div className="task-detail-actions">
          {task.status === "done" && onArchiveTask && (
            <button
              className="text-button"
              type="button"
              disabled={archivedIds?.has(task.id)}
              onClick={() => onArchiveTask(task)}
            >
              <Archive size={15} />
              {archivedIds?.has(task.id) ? "已归档" : "归档"}
            </button>
          )}
          {onDeleteTask && (
            <button className="text-button danger-text-button" type="button" onClick={() => onDeleteTask(task)}>
              删除任务
            </button>
          )}
        </div>

        {task.events?.length > 0 && (
          <section className="analysis-section task-detail-section">
            <strong>进度日志</strong>
            <div className="task-event-timeline">
              <div className="task-event-summary">
                <span>时间线</span>
                <span>{task.events.length} 条</span>
              </div>
              {task.events.slice(-100).map((event) => (
                <div className="task-event-row" key={event.id || `${event.created_at}-${event.message}`}>
                  <span className="task-event-dot" />
                  <span className="task-event-time">{event.time}</span>
                  <span className="task-event-progress">{event.progress}%</span>
                  <span className="task-event-message">{event.message || event.status || "更新任务状态"}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        <details className="raw-json">
          <summary>查看任务 JSON</summary>
          <pre className="result-box">{JSON.stringify(task, null, 2)}</pre>
        </details>
      </section>
    </div>
  );
}
