import { useEffect, useMemo, useState } from "react";
import { Badge } from "../../components/common/index";
import { statusText } from "../../constants/appConfig";
import { createTextToAssetsJob, deleteTask, fetchTasks } from "../../services/api";
import { groupTasksByStatus, normalizeTextToAssetsTask } from "../../utils/appUtils";
import { TaskRecordModal } from "../tasks/TaskRecordModal";
import { TaskStatusRow } from "../tasks/TaskStatusRow";
import { TextToAssetsResultModal } from "./TextToAssetsResultModal";

export function TextToAssetsPanel() {
  const [idea, setIdea] = useState("做一个展示智能玻璃膜防水性能的宣传片");
  const [title, setTitle] = useState("");
  const [provider, setProvider] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [task, setTask] = useState(null);
  const [taskList, setTaskList] = useState([]);
  const [activeTaskStatus, setActiveTaskStatus] = useState("running");
  const [selectedTaskRecord, setSelectedTaskRecord] = useState(null);
  const [selectedResultTask, setSelectedResultTask] = useState(null);

  const groupedTasks = useMemo(() => groupTasksByStatus(taskList), [taskList]);
  const latestTask = task || taskList[0] || null;
  const hasActiveTasks = useMemo(
    () => taskList.some((item) => !["done", "error"].includes(item.status)),
    [taskList],
  );

  async function refreshTextToAssetsTasks() {
    try {
      const tasks = await fetchTasks("text_to_assets");
      setTaskList(tasks.map((item) => normalizeTextToAssetsTask(item)));
    } catch {
      // keep quiet during backend startup
    }
  }

  useEffect(() => {
    refreshTextToAssetsTasks();
  }, []);

  useEffect(() => {
    if (!hasActiveTasks && !submitting) return undefined;
    const timer = window.setInterval(async () => {
      await refreshTextToAssetsTasks();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [hasActiveTasks, submitting]);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      const result = await createTextToAssetsJob({
        idea,
        title,
        provider,
      });
      const normalized = normalizeTextToAssetsTask(result);
      setTask(normalized);
      setMessage("任务已提交，正在生成素材清单。");
      await refreshTextToAssetsTasks();
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel settings-wide text-to-assets-panel">
      <div className="panel-header">
        <div>
          <h2>一句话转素材</h2>
          <p>输入一个抽象方案，让 AI 拆成主视觉 Prompt、补充镜头、音效、BGM 和旁白台词。</p>
        </div>
        <Badge status={latestTask ? latestTask.status : "draft"}>
          {latestTask ? statusText[latestTask.status] || latestTask.status : "等待任务"}
        </Badge>
      </div>
      <form className="settings-form" onSubmit={handleSubmit}>
        <label>
          任务标题
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="可选，不填则自动取方案前 24 个字" />
        </label>
        <label>
          Provider
          <input value={provider} onChange={(event) => setProvider(event.target.value)} placeholder="留空使用当前全局 AI provider" />
        </label>
        <label className="wide-field">
          一句话方案
          <textarea
            rows={6}
            value={idea}
            onChange={(event) => setIdea(event.target.value)}
            placeholder="例如：做一个展示智能玻璃膜防水性能的宣传片"
          />
        </label>
        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? "生成中" : "生成素材清单"}
        </button>
      </form>
      <div className="workflow-intro-strip text-to-assets-strip">
        <span>A-Roll 主视觉 Prompt</span>
        <span>B-Roll 补充镜头清单</span>
        <span>SFX / BGM / Voiceover</span>
      </div>
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
      {latestTask && (
        <div className="workflow-summary-card">
          <strong>最新任务</strong>
          <p>{latestTask.message || latestTask.status}</p>
          <code>{latestTask.id}</code>
        </div>
      )}
      <TaskStatusRow
        title="Text-to-Assets 任务"
        desc="按进行中 / 已完成 / 异常查看任务，点击任意任务可展开进度与结构化结果。"
        groups={groupedTasks}
        activeStatus={activeTaskStatus}
        onChangeStatus={setActiveTaskStatus}
        onOpenTask={(taskItem) =>
          setSelectedTaskRecord({
            type: "text_to_assets",
            title: "一句话转素材",
            task: taskItem,
          })
        }
      />
      <TaskRecordModal
        record={selectedTaskRecord}
        archivedIds={new Set()}
        onClose={() => setSelectedTaskRecord(null)}
        onOpenResult={(taskItem) => setSelectedResultTask(taskItem)}
        onArchiveTask={null}
        onDeleteTask={async (taskItem) => {
          try {
            await deleteTask(taskItem.id);
            setSelectedTaskRecord(null);
            setSelectedResultTask((current) => (current?.id === taskItem.id ? null : current));
            await refreshTextToAssetsTasks();
          } catch (err) {
            setError(err.message || String(err));
          }
        }}
      />
      <TextToAssetsResultModal task={selectedResultTask} onClose={() => setSelectedResultTask(null)} />
    </section>
  );
}
