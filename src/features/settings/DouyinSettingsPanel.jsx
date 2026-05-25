import { useEffect, useState } from "react";
import { Badge } from "../../components/common/index";
import { fetchDouyinConfig, saveDouyinConfig } from "../../services/api";

const providerModes = [
  { value: "tikhub", label: "TikHub", description: "全部可替换接口继续走老接口。" },
  { value: "spider_first", label: "Spider 优先", description: "先走新接口，失败自动回 TikHub。" },
  { value: "spider", label: "Spider", description: "全部可替换接口强制走新接口。" },
];

export function DouyinSettingsPanel() {
  const [apiBase, setApiBase] = useState("https://api.tikhub.io");
  const [outputDir, setOutputDir] = useState("./data/runtime/douyin/downloads");
  const [cookie, setCookie] = useState("");
  const [providerMode, setProviderMode] = useState("tikhub");
  const [spiderApiBase, setSpiderApiBase] = useState("http://127.0.0.1:8131");
  const [spiderExecutionMode, setSpiderExecutionMode] = useState("sidecar");
  const [spiderVendorPath, setSpiderVendorPath] = useState("./integrations/douyin_spider_provider/vendor/Douyin_Spider");
  const [observabilityEnabled, setObservabilityEnabled] = useState(true);
  const [providerStatus, setProviderStatus] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchDouyinConfig()
      .then((config) => {
        setApiBase(config.api_base || "https://api.tikhub.io");
        setOutputDir(config.output_dir || "./data/runtime/douyin/downloads");
        setCookie(config.cookie || "");
        setProviderMode(config.provider_mode || "tikhub");
        setSpiderApiBase(config.spider_api_base || "http://127.0.0.1:8131");
        setSpiderExecutionMode(config.spider_execution_mode || "sidecar");
        setSpiderVendorPath(config.spider_vendor_path || "./integrations/douyin_spider_provider/vendor/Douyin_Spider");
        setObservabilityEnabled(config.observability_enabled !== false);
        setProviderStatus(config.provider_status || null);
      })
      .catch((err) => setError(err.message || String(err)));
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await saveDouyinConfig({
        apiBase,
        outputDir,
        cookie,
        providerMode,
        spiderApiBase,
        spiderExecutionMode,
        spiderVendorPath,
        observabilityEnabled,
      });
      if (result.config?.provider_status) {
        setProviderStatus(result.config.provider_status);
      }
      setMessage(result.upstream_cookie_sync?.reason || "配置已保存。");
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
          <h2>抖音采集配置</h2>
          <p>抖音接口配置，保存到项目 `.env`；搜索固定保留 TikHub。</p>
        </div>
        <Badge status="ready">{providerModes.find((mode) => mode.value === providerMode)?.label || "TikHub"}</Badge>
      </div>
      <form className="douyin-settings-form" onSubmit={handleSubmit}>
        <label className="textarea-label">
          接口模式
          <div className="segmented" role="group" aria-label="抖音接口模式">
            {providerModes.map((mode) => (
              <button
                className={providerMode === mode.value ? "active" : ""}
                key={mode.value}
                type="button"
                title={mode.description}
                onClick={() => setProviderMode(mode.value)}
              >
                {mode.label}
              </button>
            ))}
          </div>
          <span className="field-hint">{providerModes.find((mode) => mode.value === providerMode)?.description}</span>
        </label>
        <label>
          TikHub API 地址
          <input value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
        </label>
        <label>
          Spider Sidecar 地址
          <input value={spiderApiBase} onChange={(event) => setSpiderApiBase(event.target.value)} />
        </label>
        <label>
          Spider 执行模式
          <select value={spiderExecutionMode} onChange={(event) => setSpiderExecutionMode(event.target.value)}>
            <option value="sidecar">sidecar</option>
            <option value="inprocess">inprocess</option>
          </select>
        </label>
        <label>
          Spider Vendor 路径
          <input value={spiderVendorPath} onChange={(event) => setSpiderVendorPath(event.target.value)} />
        </label>
        <label>
          下载目录
          <input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} />
        </label>
        <label className="checkbox-field textarea-label">
          <input type="checkbox" checked={observabilityEnabled} onChange={(event) => setObservabilityEnabled(event.target.checked)} />
          记录 provider 调用日志
        </label>
        <label className="textarea-label">
          抖音 Web Cookie（收藏数据使用）
          <textarea value={cookie} onChange={(event) => setCookie(event.target.value)} rows={7} />
        </label>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存配置"}
        </button>
      </form>
      {providerStatus && (
        <div className="running-note">
          当前模式：{providerStatus.mode || providerMode}；搜索接口：{providerStatus.search_provider || "legacy-tikhub"}；当前可替换接口：
          {providerStatus.active?.id || "douyin-provider"}
        </div>
      )}
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}
