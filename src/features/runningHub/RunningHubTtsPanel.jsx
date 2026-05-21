import { useEffect, useMemo, useState } from "react";
import { createRunningHubTtsJob, deleteTask, fetchRunningHubTtsConfig, fetchRunningHubTtsStatus, fetchTask, fetchTasks, saveRunningHubTtsConfig, syncRunningHubTtsTasks, uploadRunningHubTtsAudio } from "../../services/api";
import { Badge } from "../../components/common/index";
import { runningHubEmotionFields } from "../../constants/appConfig";
import { TaskRecordModal, TaskStatusRow } from "../tasks/TaskPanels";
import { groupTasksByStatus, normalizeRunningHubTtsTask } from "../../utils/appUtils";

export function RunningHubTtsPanel() {
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("https://www.runninghub.cn");
  const [workflowKey, setWorkflowKey] = useState("runninghub/tts_stable_emotion.json");
  const [workflowId, setWorkflowId] = useState("2053641347223044097");
  const [instanceType, setInstanceType] = useState("");
  const [pollIntervalSeconds, setPollIntervalSeconds] = useState(3);
  const [text, setText] = useState("请帮我生成一段更自然、更稳的中文旁白，适合短视频开场。");
  const [voice, setVoice] = useState("");
  const [refAudioPath, setRefAudioPath] = useState("");
  const [refAudioFileName, setRefAudioFileName] = useState("");
  const [enableDurationControl, setEnableDurationControl] = useState(false);
  const [durationMode, setDurationMode] = useState("speed_control");
  const [speedMultiplier, setSpeedMultiplier] = useState(1);
  const [targetDuration, setTargetDuration] = useState(0);
  const [enableEmotionControl, setEnableEmotionControl] = useState(false);
  const [emotionMode, setEmotionMode] = useState("audio_prompt");
  const [emotionAudioPath, setEmotionAudioPath] = useState("");
  const [emotionAudioFileName, setEmotionAudioFileName] = useState("");
  const [emotionAlpha, setEmotionAlpha] = useState(1);
  const [emotionText, setEmotionText] = useState("");
  const [emotionValues, setEmotionValues] = useState({
    happy: 0,
    angry: 0,
    sad: 0,
    fear: 0,
    hate: 0,
    love: 0,
    surprise: 0,
    neutral: 1,
  });
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [task, setTask] = useState(null);
  const [taskList, setTaskList] = useState([]);
  const [availableWorkflows, setAvailableWorkflows] = useState([]);
  const [activeTaskStatus, setActiveTaskStatus] = useState("running");
  const [selectedTaskRecord, setSelectedTaskRecord] = useState(null);

  const groupedTasks = useMemo(() => groupTasksByStatus(taskList), [taskList]);
  const latestTask = task || taskList[0] || null;
  const hasActiveTasks = useMemo(
    () => taskList.some((item) => !["done", "error"].includes(item.status)),
    [taskList],
  );

  async function refreshRunningHubTtsTasks({ sync = false } = {}) {
    try {
      if (sync) {
        await syncRunningHubTtsTasks();
      }
      const tasks = await fetchTasks("runninghub_tts");
      setTaskList(tasks.map((item) => normalizeRunningHubTtsTask(item)));
    } catch {
      // keep quiet while backend comes up
    }
  }

  async function openTaskRecord(taskItem) {
    const summaryTask = normalizeRunningHubTtsTask(taskItem);
    setSelectedTaskRecord({
      type: "runninghub_tts",
      title: "RunningHub TTS",
      task: summaryTask,
    });
    try {
      const fullTask = await fetchTask(taskItem.id);
      setSelectedTaskRecord({
        type: "runninghub_tts",
        title: "RunningHub TTS",
        task: normalizeRunningHubTtsTask(fullTask),
      });
    } catch (err) {
      setError(err.message || String(err));
    }
  }

  useEffect(() => {
    Promise.all([fetchRunningHubTtsConfig(), fetchRunningHubTtsStatus()])
      .then(([config, ttsStatus]) => {
        setApiKey(config.api_key || "");
        setApiBase(config.api_base || "https://www.runninghub.cn");
        setWorkflowKey(config.workflow_key || "runninghub/tts_stable_emotion.json");
        setWorkflowId(config.workflow_id || "2053641347223044097");
        setInstanceType(config.instance_type || "");
        setPollIntervalSeconds(config.poll_interval_seconds || 3);
        setAvailableWorkflows(config.available_workflows || []);
        setStatus(ttsStatus);
      })
      .catch((err) => setError(err.message || String(err)));
    refreshRunningHubTtsTasks();
  }, []);

  useEffect(() => {
    if (!hasActiveTasks && !submitting) return undefined;
    const timer = window.setInterval(async () => {
      await refreshRunningHubTtsTasks({ sync: true });
    }, 10000);
    return () => window.clearInterval(timer);
  }, [hasActiveTasks, submitting]);

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await saveRunningHubTtsConfig({
        apiKey,
        apiBase,
        workflowKey,
        workflowId,
        instanceType,
        pollIntervalSeconds,
      });
      setMessage("配置已保存。");
      setApiKey(result?.config?.api_key || apiKey);
      setWorkflowId(result?.config?.workflow_id || workflowId);
      setAvailableWorkflows(result?.config?.available_workflows || []);
      setStatus({ ready: Boolean(result?.config?.api_key), ...result?.config });
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleFileUpload(file) {
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      const result = await uploadRunningHubTtsAudio(file);
      setRefAudioPath(result.path || "");
      setRefAudioFileName(file.name);
      setMessage(`参考音频已上传：${file.name}`);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleEmotionAudioUpload(file) {
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      const result = await uploadRunningHubTtsAudio(file);
      setEmotionAudioPath(result.path || "");
      setEmotionAudioFileName(file.name);
      setMessage(`情感参考音频已上传：${file.name}`);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      const result = await createRunningHubTtsJob({
        text,
        workflowKey,
        workflowId,
        apiKey,
        apiBase,
        instanceType,
        refAudioPath: refAudioPath || undefined,
        voice,
        enableDurationControl,
        durationMode,
        speedMultiplier,
        targetDuration,
        enableEmotionControl,
        emotionMode,
        emotionAudioPath: emotionAudioPath || undefined,
        emotionAlpha,
        emotionText,
        ...emotionValues,
      });
      setTask(normalizeRunningHubTtsTask(result));
      setMessage("任务已提交，正在后台处理。");
      await refreshRunningHubTtsTasks({ sync: true });
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSubmitting(false);
    }
  }

  function applyPresetWorkflow(nextValue) {
    const preset = availableWorkflows.find((item) => item.key === nextValue || item.workflow_id === nextValue);
    if (preset) {
      setWorkflowKey(preset.key || nextValue);
      setWorkflowId(preset.workflow_id || "");
      return;
    }
    setWorkflowKey(nextValue);
  }

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>RunningHub TTS</h2>
          <p>使用稳定版 RunningHub 情感 TTS 工作流，主流程聚焦文本与参考音频，高级参数按需展开。</p>
        </div>
        <Badge status={status?.ready ? "ready" : "draft"}>{status?.ready ? "可用" : "未配置"}</Badge>
      </div>
      <form className="settings-form" onSubmit={handleSave}>
        <label>
          API Key
          <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="明文显示并从已保存配置回填" />
        </label>
        <label>
          API Base
          <input value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
        </label>
        <label>
          Workflow 标识
          <input
            value={workflowKey}
            onChange={(event) => setWorkflowKey(event.target.value)}
            placeholder="支持 runninghub/tts_stable_emotion.json、workflowId 或 workflow 链接"
          />
        </label>
        <label>
          Workflow ID
          <input
            value={workflowId}
            onChange={(event) => setWorkflowId(event.target.value)}
            placeholder="可直接填 RunningHub workflowId，留空则按上面的标识解析"
          />
        </label>
        <label>
          Instance Type
          <input value={instanceType} onChange={(event) => setInstanceType(event.target.value)} placeholder="plus" />
        </label>
        <label>
          轮询间隔(秒)
          <input type="number" min="1" max="30" step="1" value={pollIntervalSeconds} onChange={(event) => setPollIntervalSeconds(Number(event.target.value))} />
        </label>
        {availableWorkflows.length > 0 && (
          <label className="wide-field">
            预置工作流
            <select value="" onChange={(event) => applyPresetWorkflow(event.target.value)}>
              <option value="">从预置工作流快速填充</option>
              {availableWorkflows.map((item) => (
                <option key={item.workflow_id || item.key} value={item.key}>
                  {item.label} · {item.workflow_id}
                </option>
              ))}
            </select>
          </label>
        )}
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存配置"}
        </button>
      </form>
      <form className="settings-form" onSubmit={handleSubmit}>
        <label className="wide-field">
          生成文本
          <textarea rows={6} value={text} onChange={(event) => setText(event.target.value)} />
        </label>
        <label>
          参考音频
          <input
            type="file"
            accept="audio/*"
            onChange={(event) => handleFileUpload(event.target.files?.[0])}
          />
          {refAudioFileName && <small>{refAudioFileName}</small>}
        </label>
        <label>
          Voice
          <input value={voice} onChange={(event) => setVoice(event.target.value)} placeholder="可选" />
        </label>
        <label className="wide-field">
          已上传参考音频路径
          <input value={refAudioPath} readOnly />
        </label>
        <details className="workflow-advanced wide-field">
          <summary>高级配置</summary>
          <div className="workflow-advanced-grid">
            <div className="analysis-section">
              <strong>情感控制</strong>
              <div className="settings-form">
                <label className="checkbox-field wide-field">
                  <input
                    type="checkbox"
                    checked={enableEmotionControl}
                    onChange={(event) => setEnableEmotionControl(event.target.checked)}
                  />
                  启用情感控制
                </label>
                <label>
                  Emotion Mode
                  <select value={emotionMode} onChange={(event) => setEmotionMode(event.target.value)}>
                    <option value="audio_prompt">audio_prompt</option>
                    <option value="text_description">text_description</option>
                    <option value="emotion_vector">emotion_vector</option>
                    <option value="mixed">mixed</option>
                  </select>
                </label>
                <label>
                  Emotion Alpha
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={emotionAlpha}
                    onChange={(event) => setEmotionAlpha(Number(event.target.value))}
                  />
                </label>
                <label className="wide-field">
                  Emotion Text
                  <textarea
                    rows={3}
                    value={emotionText}
                    onChange={(event) => setEmotionText(event.target.value)}
                    placeholder="Describe the desired emotion..."
                  />
                </label>
                <label>
                  情感参考音频
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={(event) => handleEmotionAudioUpload(event.target.files?.[0])}
                  />
                  {emotionAudioFileName && <small>{emotionAudioFileName}</small>}
                </label>
                <label>
                  已上传情感音频路径
                  <input value={emotionAudioPath} readOnly />
                </label>
              </div>
            </div>
            <div className="analysis-section">
              <strong>情感滑块</strong>
              <div className="settings-form">
                {runningHubEmotionFields.map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <input
                      type="number"
                      min="0"
                      max="1"
                      step="0.1"
                      value={emotionValues[key]}
                      onChange={(event) =>
                        setEmotionValues((current) => ({
                          ...current,
                          [key]: Number(event.target.value),
                        }))
                      }
                    />
                  </label>
                ))}
              </div>
            </div>
          </div>
        </details>
        <button className="primary-button" type="submit" disabled={submitting || loading}>
          {submitting ? "提交中" : "生成 TTS"}
        </button>
      </form>
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
        title="RunningHub TTS 任务"
        desc="和抖音解析一致，按进行中 / 已完成 / 异常分栏查看；点击任务可展开完整进度与结果。"
        groups={groupedTasks}
        activeStatus={activeTaskStatus}
        onChangeStatus={setActiveTaskStatus}
        onOpenTask={openTaskRecord}
        onDeleteTask={async (taskItem) => {
          try {
            await deleteTask(taskItem.id);
            await refreshRunningHubTtsTasks();
            setSelectedTaskRecord((current) => (current?.task?.id === taskItem.id ? null : current));
          } catch (err) {
            setError(err.message || String(err));
          }
        }}
      />
      <TaskRecordModal
        record={selectedTaskRecord}
        archivedIds={new Set()}
        onClose={() => setSelectedTaskRecord(null)}
        onOpenResult={null}
        onArchiveTask={null}
        onDeleteTask={async (taskItem) => {
          try {
            await deleteTask(taskItem.id);
            setSelectedTaskRecord(null);
            await refreshRunningHubTtsTasks();
          } catch (err) {
            setError(err.message || String(err));
          }
        }}
      />
    </section>
  );
}
