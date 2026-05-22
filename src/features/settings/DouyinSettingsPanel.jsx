import { useEffect, useState } from "react";
import { Badge } from "../../components/common/index";
import { fetchDouyinConfig, saveDouyinConfig } from "../../services/api";

export function DouyinSettingsPanel() {
  const [apiBase, setApiBase] = useState("https://api.tikhub.io");
  const [outputDir, setOutputDir] = useState("./data/runtime/douyin/downloads");
  const [cookie, setCookie] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchDouyinConfig()
      .then((config) => {
        setApiBase(config.api_base || "https://api.tikhub.io");
        setOutputDir(config.output_dir || "./data/runtime/douyin/downloads");
        setCookie(config.cookie || "");
      })
      .catch((err) => setError(err.message || String(err)));
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await saveDouyinConfig({ apiBase, outputDir, cookie });
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
          <p>TikHub 抖音接口配置，保存到项目 `.env`。</p>
        </div>
        <Badge status="ready">TikHub</Badge>
      </div>
      <form className="douyin-settings-form" onSubmit={handleSubmit}>
        <label>
          TikHub API 地址
          <input value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
        </label>
        <label>
          下载目录
          <input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} />
        </label>
        <label className="textarea-label">
          抖音 Web Cookie（收藏数据使用）
          <textarea value={cookie} onChange={(event) => setCookie(event.target.value)} rows={7} />
        </label>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中" : "保存配置"}
        </button>
      </form>
      {message && <div className="running-note">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </section>
  );
}
