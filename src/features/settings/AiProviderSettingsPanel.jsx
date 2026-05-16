import { useEffect, useState } from "react";
import { Badge } from "../../components/common/index";
import { fetchAiProviderConfig, saveAiProviderConfig, testAiProviderConfig } from "../../services/api";

export function LegacyAiProviderSettingsPanel() {
  const [provider, setProvider] = useState("gemini");
  const [accessMode, setAccessMode] = useState("official");
  const [nativeApiKey, setNativeApiKey] = useState("");
  const [relayBaseUrl, setRelayBaseUrl] = useState("https://jeniya.top");
  const [relayApiKey, setRelayApiKey] = useState("");
  const [model, setModel] = useState("gemini-2.5-flash");
  const [localEndpoint, setLocalEndpoint] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    fetchAiProviderConfig()
      .then((config) => {
        setProvider(config.provider || "gemini");
        setAccessMode(config.access_mode || "official");
        setNativeApiKey(config.native_api_key || "");
        setRelayBaseUrl(config.relay_base_url || "https://jeniya.top");
        setRelayApiKey(config.relay_api_key || "");
        setModel(config.model || "gemini-2.5-flash");
        setLocalEndpoint(config.local_endpoint || "");
      })
      .catch((err) => setError(err.message || String(err)));
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await saveAiProviderConfig({ provider, accessMode, nativeApiKey, relayBaseUrl, relayApiKey, model, localEndpoint });
      setMessage("全局 AI 连接配置已保存。之后新增 AI 工具会优先读取这组配置。");
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setError("");
    setTestResult(null);
    try {
      const result = await testAiProviderConfig({ provider, accessMode, nativeApiKey, relayBaseUrl, relayApiKey, model, localEndpoint });
      setTestResult(result);
    } catch (err) {
      setTestResult({
        ok: false,
        message: err.message || String(err),
      });
    } finally {
      setTesting(false);
    }
  }

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>AI 模型连接配置</h2>
          <p>全局 AI 工具共用。切换官方或中转站后，后续任务会按这里的配置执行。</p>
        </div>
        <Badge status={accessMode === "relay" ? "ready" : "draft"}>{accessMode}</Badge>
      </div>
      <form className="settings-form" onSubmit={handleSubmit}>
        <label>
          模型供应商
          <select value={provider} onChange={(event) => setProvider(event.target.value)}>
            <option value="gemini">gemini</option>
            <option value="openai">openai</option>
            <option value="local">local</option>
          </select>
        </label>
        <label>
          接入方式
          <select value={accessMode} onChange={(event) => setAccessMode(event.target.value)}>
            <option value="official">原生官方</option>
            <option value="relay">中转站</option>
          </select>
        </label>
        <label>
          原生 API Key
          <input type="password" value={nativeApiKey} onChange={(event) => setNativeApiKey(event.target.value)} />
        </label>
        <label>
          中转站 Base URL
          <input value={relayBaseUrl} onChange={(event) => setRelayBaseUrl(event.target.value)} />
        </label>
        <label>
          中转站 Token
          <input type="password" value={relayApiKey} onChange={(event) => setRelayApiKey(event.target.value)} />
        </label>
        <label>
          默认模型
          <input value={model} onChange={(event) => setModel(event.target.value)} />
        </label>
        <label className="wide-field">
          本地模型地址
          <input value={localEndpoint} onChange={(event) => setLocalEndpoint(event.target.value)} placeholder="http://127.0.0.1:..." />
        </label>
        <button className="secondary-action-button" type="button" onClick={handleTest} disabled={testing}>
          {testing ? "测试中" : "测试连接"}
        </button>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存全局 AI 配置"}
        </button>
      </form>
      {testResult && (
        <div className={testResult.ok ? "running-note" : "error-box"}>
          {testResult.ok ? "测试成功" : "测试失败"}：{testResult.message}
          {testResult.sample ? ` 返回：${testResult.sample}` : ""}
        </div>
      )}
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}

export function AiProviderSettingsPanel() {
  const [configs, setConfigs] = useState({
    gemini: {
      provider: "gemini",
      accessMode: "official",
      nativeApiKey: "",
      relayBaseUrl: "https://jeniya.top",
      relayApiKey: "",
      model: "gemini-2.5-flash",
      models: ["gemini-2.5-flash", "gemini-2.0-flash"],
      apiFormat: "generate_content",
      localEndpoint: "",
    },
    openai: {
      provider: "openai",
      accessMode: "official",
      nativeApiKey: "",
      relayBaseUrl: "",
      relayApiKey: "",
      model: "gpt-4.1-mini",
      models: ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"],
      apiFormat: "responses",
      localEndpoint: "",
    },
    simple_relay: {
      provider: "simple_relay",
      accessMode: "relay",
      nativeApiKey: "",
      relayBaseUrl: "",
      relayApiKey: "",
      model: "gemini-2.5-flash",
      models: ["gemini-2.5-flash", "gemini-2.0-flash"],
      apiFormat: "gemini_generate_content",
      localEndpoint: "",
    },
    yunwu: {
      provider: "yunwu",
      accessMode: "relay",
      nativeApiKey: "",
      relayBaseUrl: "https://yunwu.ai",
      relayApiKey: "",
      model: "gemini-2.5-flash",
      models: ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro", "gpt-4o-mini"],
      apiFormat: "gemini_generate_content",
      localEndpoint: "",
    },
    deepseek: {
      provider: "deepseek",
      accessMode: "official",
      nativeApiKey: "",
      relayBaseUrl: "https://api.deepseek.com",
      relayApiKey: "",
      model: "deepseek-chat",
      models: ["deepseek-chat", "deepseek-reasoner"],
      apiFormat: "chat_completions",
      localEndpoint: "",
    },
    volcano: {
      provider: "volcano",
      accessMode: "official",
      nativeApiKey: "",
      relayBaseUrl: "https://ark.cn-beijing.volces.com/api/v3",
      relayApiKey: "",
      model: "",
      models: [],
      apiFormat: "chat_completions",
      localEndpoint: "",
    },
    local: {
      provider: "local",
      accessMode: "local",
      nativeApiKey: "",
      relayBaseUrl: "",
      relayApiKey: "",
      model: "",
      models: [],
      apiFormat: "local",
      localEndpoint: "",
    },
  });
  const [selectedProvider, setSelectedProvider] = useState("gemini");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busyProvider, setBusyProvider] = useState("");
  const [testResults, setTestResults] = useState({});

  useEffect(() => {
    fetchAiProviderConfig()
      .then((config) => {
        const providers = config.providers || {};
        setSelectedProvider(config.active_provider || "gemini");
        setConfigs((current) => ({
          gemini: normalizeAiProviderConfig(providers.gemini, current.gemini),
          openai: normalizeAiProviderConfig(providers.openai, current.openai),
          simple_relay: normalizeAiProviderConfig(providers.simple_relay, current.simple_relay),
          yunwu: normalizeAiProviderConfig(providers.yunwu, current.yunwu),
          deepseek: normalizeAiProviderConfig(providers.deepseek, current.deepseek),
          volcano: normalizeAiProviderConfig(providers.volcano, current.volcano),
          local: normalizeAiProviderConfig(providers.local, current.local),
        }));
      })
      .catch((err) => setError(err.message || String(err)));
  }, []);

  function updateProviderConfig(providerId, key, value) {
    setConfigs((current) => ({
      ...current,
      [providerId]: {
        ...current[providerId],
        [key]: value,
      },
    }));
  }

  async function handleSave(providerId) {
    setBusyProvider(`save:${providerId}`);
    setError("");
    setMessage("");
    try {
      await saveAiProviderConfig(configs[providerId]);
      setMessage(`${providerId} 配置已保存。`);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusyProvider("");
    }
  }

  async function handleTest(providerId) {
    setBusyProvider(`test:${providerId}`);
    setError("");
    setTestResults((current) => ({ ...current, [providerId]: null }));
    try {
      const result = await testAiProviderConfig(configs[providerId]);
      setTestResults((current) => ({ ...current, [providerId]: result }));
    } catch (err) {
      setTestResults((current) => ({
        ...current,
        [providerId]: { ok: false, message: err.message || String(err) },
      }));
    } finally {
      setBusyProvider("");
    }
  }

  const providerOptions = [
    ["gemini", "Gemini"],
    ["openai", "OpenAI"],
    ["simple_relay", "简单中转站"],
    ["yunwu", "云雾 API"],
    ["deepseek", "DeepSeek"],
    ["volcano", "火山引擎"],
    ["local", "本地或其他 API"],
  ];
  const providerMeta = {
    gemini: ["Gemini API", "支持 Google 原生 Gemini 和 Gemini 原生格式中转站。"],
    openai: ["OpenAI API", "原生路线使用 Responses API；中转站可切换 Responses 或 Chat Completions 兼容格式。"],
    simple_relay: ["简单中转站", "推荐用于视频工具：选择 Gemini 原生 generateContent，可绕开官方账号额度。"],
    yunwu: ["云雾 API", "根据云雾文档接入：支持 Gemini 原生 generateContent 和 OpenAI-compatible Chat Completions。"],
    deepseek: ["DeepSeek API", "DeepSeek 使用 OpenAI-compatible Chat Completions 格式。"],
    volcano: ["火山引擎 API", "火山方舟使用 OpenAI-compatible Chat Completions 格式。"],
    local: ["本地或其他 API", "预留给本地模型、局域网服务或后续其他服务。"],
  };
  const selectedMeta = providerMeta[selectedProvider] || providerMeta.gemini;

  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>AI 模型 API 配置</h2>
          <p>每个供应商独立保存。API Key 明文显示，方便个人本地调试和切换。</p>
        </div>
        <Badge status="ready">{selectedProvider}</Badge>
      </div>
      <div className="model-settings-layout">
        <aside className="provider-list-panel">
          {providerOptions.map(([value, label]) => {
            const item = configs[value] || {};
            return (
              <button
                className={`provider-list-item ${selectedProvider === value ? "active" : ""}`}
                key={value}
                type="button"
                onClick={() => setSelectedProvider(value)}
              >
                <span>{label}</span>
                <small>{item.model || "未设置模型"}</small>
              </button>
            );
          })}
        </aside>
        <AiProviderConfigCard
          title={selectedMeta[0]}
          description={selectedMeta[1]}
          config={configs[selectedProvider] || configs.gemini}
          providerId={selectedProvider}
          busyProvider={busyProvider}
          testResult={testResults[selectedProvider]}
          onChange={updateProviderConfig}
          onSave={handleSave}
          onTest={handleTest}
        />
      </div>
      <label className="provider-selector">
        当前全局 AI 模型
        <select value={selectedProvider} onChange={(event) => setSelectedProvider(event.target.value)}>
          {providerOptions.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <AiProviderConfigCard
        title={selectedMeta[0]}
        description={selectedMeta[1]}
        config={configs[selectedProvider] || configs.gemini}
        providerId={selectedProvider}
        busyProvider={busyProvider}
        testResult={testResults[selectedProvider]}
        onChange={updateProviderConfig}
        onSave={handleSave}
        onTest={handleTest}
      />
      {false && (
        <>
      <AiProviderConfigCard
        title="OpenAI API"
        description="原生路线使用 Responses API；中转站可切换 Responses 或 Chat Completions 兼容格式。"
        config={configs.openai}
        providerId="openai"
        busyProvider={busyProvider}
        testResult={testResults.openai}
        onChange={updateProviderConfig}
        onSave={handleSave}
        onTest={handleTest}
      />
      <AiProviderConfigCard
        title="Gemini API"
        description="支持 Google 原生 Gemini 和 Gemini 原生格式中转站。"
        config={configs.gemini}
        providerId="gemini"
        busyProvider={busyProvider}
        testResult={testResults.gemini}
        onChange={updateProviderConfig}
        onSave={handleSave}
        onTest={handleTest}
      />
      <AiProviderConfigCard
        title="本地或其他 API"
        description="预留给本地模型、局域网服务或后续其他 OpenAI-compatible 服务。"
        config={configs.local}
        providerId="local"
        busyProvider={busyProvider}
        testResult={testResults.local}
        onChange={updateProviderConfig}
        onSave={handleSave}
        onTest={handleTest}
      />
        </>
      )}
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}

export function AiProviderConfigCard({ title, description, config, providerId, busyProvider, testResult, onChange, onSave, onTest }) {
  const isBusySaving = busyProvider === `save:${providerId}`;
  const isBusyTesting = busyProvider === `test:${providerId}`;
  const isLocal = providerId === "local";
  const isOpenAI = providerId === "openai";
  const isSimpleRelay = providerId === "simple_relay" || providerId === "yunwu";
  const isFixedOpenAICompatible = providerId === "deepseek" || providerId === "volcano";
  const showAccessMode = !isLocal && !isSimpleRelay && !isFixedOpenAICompatible;
  const showApiFormat = isOpenAI || isSimpleRelay;
  const showNativeKey = !isLocal && !isSimpleRelay;
  const showRelayFields = !isLocal && (config.accessMode === "relay" || isSimpleRelay || isFixedOpenAICompatible);
  const modelsText = (config.models || []).join("\n");
  return (
    <div className="settings-subpanel">
      <div className="panel-header compact-header">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        <Badge status={config.accessMode === "relay" ? "ready" : "draft"}>{config.accessMode}</Badge>
      </div>
      <form className="settings-form" onSubmit={(event) => event.preventDefault()}>
        {showAccessMode && (
          <label>
            接入方式
            <select value={config.accessMode} onChange={(event) => onChange(providerId, "accessMode", event.target.value)}>
              <option value="official">原生官方</option>
              <option value="relay">中转站</option>
            </select>
          </label>
        )}
        {showApiFormat && (
          <label>
            API 格式
            <select value={config.apiFormat} onChange={(event) => onChange(providerId, "apiFormat", event.target.value)}>
              <option value="responses">Responses API</option>
              <option value="chat_completions">Chat Completions</option>
              {isSimpleRelay && <option value="gemini_generate_content">Gemini 原生 generateContent</option>}
            </select>
          </label>
        )}
        {showNativeKey && (
          <label>
            {isFixedOpenAICompatible ? "API Key" : "原生 API Key"}
            <input value={config.nativeApiKey} onChange={(event) => onChange(providerId, "nativeApiKey", event.target.value)} />
          </label>
        )}
        {showRelayFields && (
          <label>
            {isSimpleRelay ? "Base URL" : "API Base URL"}
            <input value={config.relayBaseUrl} onChange={(event) => onChange(providerId, "relayBaseUrl", event.target.value)} placeholder="https://..." />
          </label>
        )}
        {(isOpenAI && config.accessMode === "relay") || isSimpleRelay ? (
          <label>
            {isSimpleRelay ? "API Key" : "中转站 API Key"}
            <input value={config.relayApiKey} onChange={(event) => onChange(providerId, "relayApiKey", event.target.value)} />
          </label>
        ) : null}
        <label>
          默认模型
          {(config.models || []).length ? (
            <select value={config.model} onChange={(event) => onChange(providerId, "model", event.target.value)}>
              {(config.models || []).map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          ) : (
            <input value={config.model} onChange={(event) => onChange(providerId, "model", event.target.value)} />
          )}
        </label>
        <label className="textarea-label">
          模型列表
          <textarea
            value={modelsText}
            onChange={(event) => {
              const models = event.target.value
                .split(/\n|,/)
                .map((item) => item.trim())
                .filter(Boolean);
              onChange(providerId, "models", models);
              if (!models.includes(config.model)) {
                onChange(providerId, "model", models[0] || "");
              }
            }}
            rows={5}
            placeholder="每行一个模型，例如 gpt-4.1-mini"
          />
        </label>
        {isLocal && (
          <label className="wide-field">
            本地 API 地址
            <input value={config.localEndpoint} onChange={(event) => onChange(providerId, "localEndpoint", event.target.value)} placeholder="http://127.0.0.1:..." />
          </label>
        )}
        <button className="secondary-action-button" type="button" onClick={() => onTest(providerId)} disabled={isBusyTesting}>
          {isBusyTesting ? "测试中" : "测试连接"}
        </button>
        <button className="primary-button" type="button" onClick={() => onSave(providerId)} disabled={isBusySaving}>
          {isBusySaving ? "保存中" : `保存 ${title}`}
        </button>
      </form>
      {testResult && (
        <div className={testResult.ok ? "running-note" : "error-box"}>
          {testResult.ok ? "测试成功" : "测试失败"}：{testResult.message}
          {testResult.sample ? ` 返回：${testResult.sample}` : ""}
        </div>
      )}
    </div>
  );
}

export function normalizeAiProviderConfig(value, fallback) {
  if (!value) {
    return fallback;
  }
  return {
    ...fallback,
    provider: value.provider || fallback.provider,
    accessMode: value.access_mode || fallback.accessMode,
    nativeApiKey: value.native_api_key || "",
    relayBaseUrl: value.relay_base_url || fallback.relayBaseUrl,
    relayApiKey: value.relay_api_key || "",
    model: value.model || fallback.model,
    models: Array.isArray(value.models) ? value.models : fallback.models || [],
    apiFormat: value.api_format || fallback.apiFormat,
    localEndpoint: value.local_endpoint || fallback.localEndpoint,
  };
}
