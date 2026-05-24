import { useState } from "react";
import { ChevronDown, RefreshCw, Trash2 } from "lucide-react";
import { Badge } from "../../components/common/index";
import { statusText, taskBoardStatuses } from "../../constants/appConfig";
import { commentCollectionLabel, commentCollectionTone, preferredTaskStatus } from "../../utils/appUtils";

export function TaskStatusRow({
  title,
  desc,
  groups,
  activeStatus,
  onChangeStatus,
  onOpenTask,
  onRestartTask,
  onRetryTask,
  onDeleteTask,
}) {
  const [expanded, setExpanded] = useState(false);
  const total = taskBoardStatuses.reduce((sum, [key]) => sum + (groups[key]?.length || 0), 0);
  const resolvedStatus = preferredTaskStatus(groups, activeStatus);
  const activeTasks = groups[resolvedStatus] || [];
  const emptyText = {
    pending: "当前没有等待中的任务。",
    running: "当前没有进行中的任务。",
    done: "当前没有已完成的任务。",
    error: "当前没有异常任务。",
  }[resolvedStatus];

  return (
    <section className="panel task-row-panel">
      <button
        className={`panel-header task-row-header task-row-toggle ${expanded ? "expanded" : ""}`}
        type="button"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
      >
        <div>
          <h2>{title}</h2>
          <p>{desc}</p>
        </div>
        <div className="task-row-toggle-meta">
          <Badge status={total ? "running" : "draft"}>{total ? `${total} 个任务` : "暂无任务"}</Badge>
          <span className="task-row-toggle-label">{expanded ? "点击收起" : "点击展开"}</span>
          <ChevronDown size={18} className={`task-row-toggle-icon ${expanded ? "expanded" : ""}`} />
        </div>
      </button>
      {expanded && (
        <>
          <div className="task-status-tabs">
            {taskBoardStatuses.map(([key, label]) => (
              <button
                className={`task-status-tab ${resolvedStatus === key ? "active" : ""}`}
                key={key}
                type="button"
                onClick={() => onChangeStatus(key)}
              >
                <span>{label}</span>
                <strong>{groups[key]?.length || 0}</strong>
              </button>
            ))}
          </div>
          <div className="task-row-list">
            {activeTasks.length ? (
              activeTasks.map((task) => {
                const taskTitle = String(task.title || "").trim() || "未命名任务";
                const commentLabel = task.commentCollection ? commentCollectionLabel(task.commentCollection) : "";
                return (
                  <div className="task-list-row" key={task.id}>
                    <button
                      className="task-list-row-main task-list-row-open"
                      type="button"
                      onClick={() => onOpenTask(task)}
                    >
                      <strong>{taskTitle}</strong>
                      <p>{task.message || `${title} 任务`}</p>
                    </button>
                    <div className="task-list-row-meta">
                      {commentLabel && (
                        <span className="task-list-row-comment-status" title={commentLabel}>
                          <Badge status={commentCollectionTone(task.commentCollection)}>
                            {commentLabel}
                          </Badge>
                        </span>
                      )}
                      <Badge status={task.status}>{statusText[task.status] || task.status}</Badge>
                      <span className="task-list-progress">{task.progress}%</span>
                      <span>{task.updated}</span>
                      <div className="task-list-row-actions">
                        {["pending", "running"].includes(resolvedStatus) && onRestartTask && (
                          <button
                            className="text-button task-list-row-retry"
                            type="button"
                            aria-label={`重新开始任务 ${taskTitle}`}
                            onClick={() => onRestartTask(task)}
                          >
                            <RefreshCw size={14} />
                            重新开始
                          </button>
                        )}
                        {resolvedStatus === "error" && onRetryTask && (
                          <button
                            className="text-button task-list-row-retry"
                            type="button"
                            aria-label={`重试任务 ${taskTitle}`}
                            onClick={() => onRetryTask(task)}
                          >
                            <RefreshCw size={14} />
                            重试
                          </button>
                        )}
                        {onDeleteTask && (
                          <button
                            className="text-button danger-text-button task-list-row-delete"
                            type="button"
                            aria-label={`删除任务 ${taskTitle}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              onDeleteTask(task);
                            }}
                          >
                            <Trash2 size={14} />
                            删除
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="empty-result">{emptyText}</div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
