import { Badge } from "../../components/common/index";
import { Archive, Clock3 } from "lucide-react";

export function AnalysisTaskPanel({
  tasks,
  onOpenResult,
  onDeleteTask,
  onArchiveTask,
  archivedIds,
  compact = false,
  title = "AI 视频拆解任务",
  emptyText = "点击视频卡片里的 AI 视频拆解后，任务会显示在这里。",
}) {
  const visibleTasks = compact ? tasks.slice(0, 3) : tasks;

  return (
    <section className={`panel analysis-task-panel ${compact ? "compact-analysis-panel" : ""}`}>
      <div className="panel-header">
        <h2>{title}</h2>
        <Badge status={tasks.length ? "running" : "draft"}>{tasks.length ? `${tasks.length} 个任务` : "暂无任务"}</Badge>
      </div>
      {visibleTasks.length ? (
        <div className="analysis-task-list">
          {visibleTasks.map((task) => (
            <article className="analysis-task-card" key={task.id}>
              <div className="analysis-task-head">
                <strong>{task.title}</strong>
                <Badge status={task.status}>{task.status === "done" ? "已完成" : task.status === "error" ? "失败" : "运行中"}</Badge>
              </div>
              <div className="progress">
                <span style={{ width: `${task.progress}%` }} />
              </div>
              {!["done", "error"].includes(task.status) && (
                <div className="task-current-stage">
                  <Clock3 size={15} />
                  <span>当前阶段：{task.message || "等待后端更新"} · {task.progress}%</span>
                </div>
              )}
              <div className="analysis-task-foot">
                <span>{task.message || "AI 视频拆解"} · {task.updated}</span>
              </div>
              <div className="task-action-row">
                {task.status === "done" && (
                  <button className="text-button" type="button" onClick={() => onOpenResult(task)}>
                    查看结果
                  </button>
                )}
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
                    删除
                  </button>
                )}
              </div>
              {task.status === "error" && <p className="task-error-text">{task.error}</p>}
              {task.events?.length > 0 && (
                <div className="task-event-timeline">
                  <div className="task-event-summary">
                    <span>进度日志</span>
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
              )}
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-result">{emptyText}</div>
      )}
    </section>
  );
}
