import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleAlert, RefreshCw, RotateCcw, Server, TimerReset, Trash2, Users, X } from "lucide-react";
import { Badge } from "../../components/common/index";
import { cancelAiVideoQueueJob, deleteAiVideoQueueJob, fetchAiVideoQueueStatus, retryAiVideoQueueJob } from "../../services/api";

function formatDateTime(value) {
  const timestamp = Number(value);
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "-";
  return new Date(timestamp * 1000).toLocaleString("zh-CN", { hour12: false });
}

function formatDuration(startAt, endAt) {
  const start = Number(startAt || 0);
  const end = Number(endAt || 0);
  if (!start || !end || end <= start) return "-";
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remain = seconds % 60;
  return remain ? `${minutes}m ${remain}s` : `${minutes}m`;
}

function queueStatusTone(status) {
  if (status === "running" || status === "claimed") return "running";
  if (status === "retry_waiting" || status === "queued" || status === "stale_requeued") return "draft";
  if (status === "failed_final") return "error";
  if (status === "cancelled") return "paused";
  return "done";
}

function QueueStat({ label, value, tone = "draft" }) {
  return (
    <article className="queue-stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <Badge status={tone}>{tone}</Badge>
    </article>
  );
}

function QueueRow({ item, kind }) {
  const positionLabel = kind === "backlog" ? `#${item.position || "-"}` : item.stage || "-";
  const updated = formatDateTime(item.task_updated_at || item.updated_at);
  const lockedAt = formatDateTime(item.locked_at);
  const heartbeatAt = formatDateTime(item.heartbeat_at);
  const duration = formatDuration(item.locked_at, item.heartbeat_at || Math.floor(Date.now() / 1000));
  const isFailed = item.status === "failed_final";
  const isQueued = ["queued", "retry_waiting", "stale_requeued"].includes(item.status);
  const isActive = ["running", "claimed"].includes(item.status);

  return (
    <article className="queue-item">
      <div className="queue-item-main">
        <div className="queue-item-head">
          <div>
            <strong>{item.title || item.task_id}</strong>
            <p>{item.task_message || item.error_message || item.task_id}</p>
          </div>
          <Badge status={queueStatusTone(item.status)}>
            {item.status}
          </Badge>
        </div>
        <div className="queue-item-meta">
          <span>{positionLabel}</span>
          <span>{item.task_progress || item.progress || 0}%</span>
          <span>{item.priority != null ? `P${item.priority}` : "-"}</span>
          <span>{item.provider || item.task_provider || "-"}</span>
          <span>{updated}</span>
        </div>
        <div className="queue-item-actions">
          {isQueued && (
            <button className="text-button danger-text-button" type="button" onClick={() => item.onCancel?.(item)} disabled={item.actionPending}>
              <X size={14} />
              取消
            </button>
          )}
          {isFailed && (
            <button className="text-button" type="button" onClick={() => item.onRetry?.(item)} disabled={item.actionPending}>
              <RotateCcw size={14} />
              重试
            </button>
          )}
          {!isActive && (
            <button className="text-button danger-text-button" type="button" onClick={() => item.onDelete?.(item)} disabled={item.actionPending}>
              <Trash2 size={14} />
              删除
            </button>
          )}
        </div>
      </div>
      <div className="queue-item-side">
        <span>{kind === "worker" ? item.locked_by || "worker" : `尝试 ${item.attempts || 0}/${item.max_attempts || 0}`}</span>
        <span>{kind === "worker" ? `锁定 ${lockedAt}` : `重试 ${item.retry_after ? formatDateTime(item.retry_after) : "-"}`}</span>
        <span>{kind === "worker" ? `心跳 ${heartbeatAt}` : `等待 ${duration}`}</span>
      </div>
    </article>
  );
}

export function AiVideoQueuePanel({ taskId, onDeleted }) {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionBusyId, setActionBusyId] = useState("");

  async function loadSnapshot() {
    setLoading(true);
    try {
      const data = await fetchAiVideoQueueStatus(taskId, 20);
      setSnapshot(data);
      setError("");
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleCancel(item) {
    if (!window.confirm(`确认取消任务「${item.title || item.task_id}」吗？`)) return;
    setActionBusyId(item.task_id);
    try {
      await cancelAiVideoQueueJob(item.task_id);
      await loadSnapshot();
      setActionError("");
    } catch (err) {
      setActionError(err?.message || String(err));
    } finally {
      setActionBusyId("");
    }
  }

  async function handleRetry(item) {
    if (!window.confirm(`确认重试任务「${item.title || item.task_id}」吗？`)) return;
    setActionBusyId(item.task_id);
    try {
      await retryAiVideoQueueJob(item.task_id);
      await loadSnapshot();
      setActionError("");
    } catch (err) {
      setActionError(err?.message || String(err));
    } finally {
      setActionBusyId("");
    }
  }

  async function handleDelete(item) {
    if (!window.confirm(`确认删除任务「${item.title || item.task_id}」吗？已完成任务也会从任务中心移除。`)) return;
    setActionBusyId(item.task_id);
    try {
      await deleteAiVideoQueueJob(item.task_id);
      await loadSnapshot();
      await onDeleted?.(item);
      setActionError("");
    } catch (err) {
      setActionError(err?.message || String(err));
    } finally {
      setActionBusyId("");
    }
  }

  useEffect(() => {
    loadSnapshot().catch(() => {});
    const timer = window.setInterval(() => loadSnapshot().catch(() => {}), 10000);
    return () => window.clearInterval(timer);
  }, [taskId]);

  const metrics = useMemo(() => {
    if (!snapshot) return [];
    return [
      { label: "并发上限", value: snapshot.max_concurrent ?? 0, tone: "ready" },
      { label: "活跃中", value: snapshot.active ?? 0, tone: "running" },
      { label: "排队中", value: snapshot.queued ?? 0, tone: "draft" },
      { label: "重试中", value: snapshot.retry_waiting ?? 0, tone: "paused" },
      { label: "已完成", value: snapshot.done ?? 0, tone: "done" },
      { label: "失败", value: snapshot.failed ?? 0, tone: "error" },
    ];
  }, [snapshot]);

  return (
    <section className="panel queue-dashboard-panel">
      <div className="panel-header">
        <div>
          <h2>AI 视频队列</h2>
          <p>查看当前 backlog、worker 和任务位置。</p>
        </div>
        <button className="text-button" type="button" onClick={() => loadSnapshot().catch(() => {})} disabled={loading}>
          <RefreshCw size={15} className={loading ? "spin" : ""} />
          刷新
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}
      {actionError && <div className="error-box">{actionError}</div>}

      <div className="queue-metrics-grid">
        {metrics.map((metric) => (
          <QueueStat key={metric.label} {...metric} />
        ))}
      </div>

      {snapshot && (
        <>
          <div className="queue-summary-row">
            <Badge status={snapshot.worker_started ? "done" : "draft"}>{snapshot.worker_started ? "worker 已启动" : "worker 未启动"}</Badge>
            <Badge status={snapshot.worker_enabled ? "ready" : "error"}>{snapshot.worker_enabled ? "worker 启用" : "worker 停用"}</Badge>
            <Badge status="running">{snapshot.thread_count || 0} 条线程</Badge>
            <Badge status="running">{snapshot.oldest_queued_at ? `最早排队 ${formatDateTime(snapshot.oldest_queued_at)}` : "暂无排队"}</Badge>
          </div>

          <div className="queue-section">
            <div className="queue-section-head">
              <Server size={16} />
              <strong>活跃 worker</strong>
            </div>
            <div className="queue-list">
              {snapshot.workers?.length ? snapshot.workers.map((item) => <QueueRow key={item.task_id} item={{ ...item, actionPending: actionBusyId === item.task_id, onCancel: handleCancel, onRetry: handleRetry, onDelete: handleDelete }} kind="worker" />) : <div className="empty-result">当前没有活跃 worker。</div>}
            </div>
          </div>

          <div className="queue-section">
            <div className="queue-section-head">
              <TimerReset size={16} />
              <strong>队列前排</strong>
            </div>
            <div className="queue-list">
              {snapshot.backlog?.length ? snapshot.backlog.map((item) => <QueueRow key={item.task_id} item={{ ...item, actionPending: actionBusyId === item.task_id, onCancel: handleCancel, onRetry: handleRetry, onDelete: handleDelete }} kind="backlog" />) : <div className="empty-result">当前没有待处理任务。</div>}
            </div>
          </div>

          <div className="queue-section">
            <div className="queue-section-head">
              <CheckCircle2 size={16} />
              <strong>最近完成</strong>
            </div>
            <div className="queue-list">
              {snapshot.done_recent?.length ? snapshot.done_recent.map((item) => <QueueRow key={item.task_id} item={{ ...item, actionPending: actionBusyId === item.task_id, onCancel: handleCancel, onRetry: handleRetry, onDelete: handleDelete }} kind="backlog" />) : <div className="empty-result">当前没有最近完成任务。</div>}
            </div>
          </div>

          <div className="queue-section">
            <div className="queue-section-head">
              <CircleAlert size={16} />
              <strong>最近失败</strong>
            </div>
            <div className="queue-list">
              {snapshot.failed_recent?.length ? snapshot.failed_recent.map((item) => <QueueRow key={item.task_id} item={{ ...item, actionPending: actionBusyId === item.task_id, onCancel: handleCancel, onRetry: handleRetry, onDelete: handleDelete }} kind="backlog" />) : <div className="empty-result">当前没有最近失败任务。</div>}
            </div>
          </div>

          {taskId && snapshot.task_id && (
            <div className="queue-section">
              <div className="queue-section-head">
                <Users size={16} />
                <strong>当前任务</strong>
              </div>
              <div className="queue-task-card">
                <div>
                  <strong>{snapshot.task?.title || snapshot.task_id}</strong>
                  <p>{snapshot.task?.message || "等待更新"}</p>
                </div>
                <div className="queue-task-meta">
                  <span>位置 {snapshot.position ?? "-"}</span>
                  <span>状态 {snapshot.task?.status || snapshot.job?.status || "-"}</span>
                  <span>阶段 {snapshot.job?.stage || "-"}</span>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
