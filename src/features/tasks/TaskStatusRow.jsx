import { useState } from "react";
import { Badge } from "../../components/common/index";
import { statusText, taskBoardStatuses } from "../../constants/appConfig";
import { commentCollectionLabel, commentCollectionTone, preferredTaskStatus } from "../../utils/appUtils";
import { ChevronDown } from "lucide-react";

export function TaskStatusRow({ title, desc, groups, activeStatus, onChangeStatus, onOpenTask }) {
  const [expanded, setExpanded] = useState(false);
  const total = taskBoardStatuses.reduce((sum, [key]) => sum + (groups[key]?.length || 0), 0);
  const resolvedStatus = preferredTaskStatus(groups, activeStatus);
  const activeTasks = groups[resolvedStatus] || [];
  const emptyText = {
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
              activeTasks.map((task) => (
                <button className="task-list-row" key={task.id} type="button" onClick={() => onOpenTask(task)}>
                  <div className="task-list-row-main">
                    <strong>{task.title}</strong>
                    <p>{task.message || `${title} 任务`}</p>
                  </div>
                  <div className="task-list-row-meta">
                    {task.commentCollection && (
                      <Badge status={commentCollectionTone(task.commentCollection)}>
                        {commentCollectionLabel(task.commentCollection)}
                      </Badge>
                    )}
                    <Badge status={task.status}>{statusText[task.status] || task.status}</Badge>
                    <span className="task-list-progress">{task.progress}%</span>
                    <span>{task.updated}</span>
                  </div>
                </button>
              ))
            ) : (
              <div className="empty-result">{emptyText}</div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
