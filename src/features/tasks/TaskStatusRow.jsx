import { ChevronDown, RefreshCw, Trash2 } from "lucide-react";
import { Badge } from "../../components/common/index";
import { statusText, taskBoardStatuses } from "../../constants/appConfig";
import { commentCollectionLabel, commentCollectionTone } from "../../utils/appUtils";

const emptyTextByStatus = {
  pending: "当前没有等待中的任务。",
  running: "当前没有进行中的任务。",
  done: "当前没有已完成的任务。",
  error: "当前没有异常任务。",
};

function statusCount(counts, groups, status) {
  return Math.max(Number(counts?.[status] || 0), groups[status]?.length || 0);
}

export function TaskStatusRow({
  title,
  desc,
  groups = {},
  counts = {},
  activeStatus,
  loadingStatus = "",
  pageSize = 10,
  onChangeStatus,
  onLoadMore,
  onOpenTask,
  onRestartTask,
  onRetryTask,
  onDeleteTask,
}) {
  const statusCounts = taskBoardStatuses.reduce(
    (result, [key]) => ({
      ...result,
      [key]: statusCount(counts, groups, key),
    }),
    {},
  );
  const calculatedTotal = taskBoardStatuses.reduce((sum, [key]) => sum + statusCounts[key], 0);
  const total = Math.max(Number(counts?.total || 0), calculatedTotal);
  const resolvedStatus = activeStatus || "";
  const activeTasks = resolvedStatus ? groups[resolvedStatus] || [] : [];
  const activeTotal = resolvedStatus ? Math.max(statusCounts[resolvedStatus] || 0, activeTasks.length) : 0;
  const loading = Boolean(resolvedStatus && loadingStatus === resolvedStatus);
  const hasMore = Boolean(resolvedStatus && activeTasks.length < activeTotal);
  const emptyText = emptyTextByStatus[resolvedStatus] || "点击上方状态查看任务。";

  function handleStatusClick(status) {
    onChangeStatus?.(resolvedStatus === status ? "" : status);
  }

  function handleListScroll(event) {
    if (!hasMore || loading) return;
    const target = event.currentTarget;
    if (target.scrollHeight - target.scrollTop - target.clientHeight < 80) {
      onLoadMore?.(resolvedStatus);
    }
  }

  return (
    <section className="panel task-row-panel">
      <div className="panel-header task-row-header">
        <div>
          <h2>{title}</h2>
          <p>{desc}</p>
        </div>
        <div className="task-row-summary">
          <Badge status={total ? "running" : "draft"}>{total ? `${total} 个任务` : "暂无任务"}</Badge>
          <span>{resolvedStatus ? `已显示 ${activeTasks.length}/${activeTotal}` : "默认收起"}</span>
        </div>
      </div>

      <div className="task-status-tabs">
        {taskBoardStatuses.map(([key, label]) => (
          <button
            className={`task-status-tab ${resolvedStatus === key ? "active" : ""}`}
            key={key}
            type="button"
            aria-expanded={resolvedStatus === key}
            onClick={() => handleStatusClick(key)}
          >
            <span>{label}</span>
            <strong>{statusCounts[key]}</strong>
            <ChevronDown size={16} className={`task-status-tab-icon ${resolvedStatus === key ? "expanded" : ""}`} />
          </button>
        ))}
      </div>

      {resolvedStatus && (
        <div className="task-status-section">
          <div className="task-status-section-head">
            <Badge>{taskBoardStatuses.find(([key]) => key === resolvedStatus)?.[1] || "任务"}</Badge>
            <span>每次加载 {pageSize} 条</span>
          </div>
          <div className="task-row-list" onScroll={handleListScroll}>
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
                          <Badge status={commentCollectionTone(task.commentCollection)}>{commentLabel}</Badge>
                        </span>
                      )}
                      <Badge status={task.status}>{statusText[task.status] || task.status || "未知"}</Badge>
                      <span className="task-list-progress">{task.progress ?? 0}%</span>
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
              <div className="empty-result">{loading ? "任务加载中..." : emptyText}</div>
            )}
            {(hasMore || loading) && (
              <div className="task-row-list-footer">
                <button
                  className="load-more-button"
                  type="button"
                  disabled={loading}
                  onClick={() => onLoadMore?.(resolvedStatus)}
                >
                  {loading ? "加载中..." : `加载更多（已显示 ${activeTasks.length}/${activeTotal}）`}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
