import { useEffect, useMemo, useState } from "react";
import { Badge } from "../../components/common/index";
import { fetchAiVideoConfig, fetchAiVideoConfigSchema, saveAiVideoConfig } from "../../services/api";

const FALLBACK_SCHEMA = [
  { name: "pipeline_mode", label: "拆解流程", type: "select", default: "evidence", options: [{ value: "evidence", label: "证据包优先：转写 + 关键帧 + 分段拆解" }, { value: "auto", label: "自动：证据包失败时回退直接视频分析" }, { value: "direct", label: "直接视频分析：跳过转写流程" }] },
  { name: "output_dir", label: "输出目录", type: "text", default: "./data/runtime/ai_video_analysis" },
  { name: "analysis_prompt", label: "拆解提示词模板", type: "textarea", rows: 12, default: "", wide: true },
];

function normalizeFields(schema) {
  const fields = Array.isArray(schema?.fields) ? schema.fields : Array.isArray(schema) ? schema : [];
  return fields.length ? fields : FALLBACK_SCHEMA;
}

function defaultsFromFields(fields) {
  return fields.reduce((acc, field) => {
    acc[field.name] = field.default ?? (field.type === "boolean" ? false : "");
    return acc;
  }, {});
}

function parseFieldValue(field, value) {
  if (field.type === "number") {
    const number = Number(value);
    return Number.isFinite(number) ? number : Number(field.default || 0);
  }
  if (field.type === "boolean") return Boolean(value);
  return value ?? "";
}

function ConfigField({ field, value, onChange }) {
  const className = `${field.type === "textarea" ? "textarea-label" : ""} ${field.wide ? "wide-field" : ""}`.trim() || undefined;
  if (field.type === "boolean") {
    return (
      <label className={`checkbox-field ${field.wide ? "wide-field" : ""}`}>
        <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(field.name, event.target.checked)} />
        <span>{field.label}</span>
      </label>
    );
  }
  return (
    <label className={className}>
      {field.label}
      {field.type === "select" ? (
        <select value={value ?? ""} onChange={(event) => onChange(field.name, event.target.value)}>
          {(field.options || []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label || option.value}
            </option>
          ))}
        </select>
      ) : field.type === "textarea" ? (
        <textarea
          value={value ?? ""}
          onChange={(event) => onChange(field.name, event.target.value)}
          rows={field.rows || 8}
          placeholder={field.placeholder || ""}
        />
      ) : (
        <input
          type={field.type === "number" ? "number" : "text"}
          min={field.min}
          max={field.max}
          value={value ?? ""}
          placeholder={field.placeholder || ""}
          onChange={(event) => onChange(field.name, event.target.value)}
        />
      )}
      {field.hint && <span className="field-hint">{field.hint}</span>}
    </label>
  );
}

export function AiVideoSettingsPanel() {
  const [fields, setFields] = useState(FALLBACK_SCHEMA);
  const [values, setValues] = useState(() => defaultsFromFields(FALLBACK_SCHEMA));
  const [message, setMessage] = useState("");
  const [saveDetail, setSaveDetail] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchAiVideoConfig(), fetchAiVideoConfigSchema().catch(() => ({ fields: FALLBACK_SCHEMA }))])
      .then(([config, schema]) => {
        if (cancelled) return;
        const nextFields = normalizeFields(schema);
        setFields(nextFields);
        setValues({ ...defaultsFromFields(nextFields), ...config });
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const pipelineMode = values.pipeline_mode || "evidence";
  const groupedFields = useMemo(() => {
    const visible = fields.filter((field) => field.name && field.type !== "hidden");
    return visible.reduce((acc, field) => {
      const section = field.section || "main";
      if (!acc[section]) acc[section] = [];
      acc[section].push(field);
      return acc;
    }, {});
  }, [fields]);

  function updateValue(name, value) {
    setValues((current) => ({ ...current, [name]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    setSaveDetail(null);
    try {
      const payload = {};
      for (const field of fields) {
        payload[field.name] = parseFieldValue(field, values[field.name]);
      }
      const result = await saveAiVideoConfig(payload);
      setSaveDetail(result?.worker_reconcile || null);
      setMessage("AI 视频拆解配置已保存。模型连接仍使用全局 AI 模型配置。");
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>AI 视频拆解配置</h2>
          <p>配置证据包、转写、分段、关键帧和拆解提示词。模型连接请到“AI 模型”里统一设置。</p>
        </div>
        <Badge status={pipelineMode === "direct" ? "draft" : "ready"}>{pipelineMode}</Badge>
      </div>
      <form className="settings-form" onSubmit={handleSubmit}>
        {Object.entries(groupedFields).map(([section, sectionFields]) => (
          <div className="settings-schema-group" key={section}>
            {sectionFields.map((field) => (
              <ConfigField key={field.name} field={field} value={values[field.name]} onChange={updateValue} />
            ))}
          </div>
        ))}
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存拆解配置"}
        </button>
      </form>
      {message && <div className="running-note">{message}</div>}
      {saveDetail && (
        <div className="running-note">
          worker 目标 {saveDetail.target_thread_count ?? 0}，当前 {saveDetail.thread_count ?? 0}，已新增 {saveDetail.spawned ?? 0}。
        </div>
      )}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}
