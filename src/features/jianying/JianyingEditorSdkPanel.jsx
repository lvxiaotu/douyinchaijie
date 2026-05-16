import { useEffect, useState } from "react";
import { Badge } from "../../components/common/index";
import { API_BASE } from "../../constants/appConfig";
import { fetchJianyingEditorSdkStatus } from "../../services/api";

export function JianyingEditorSdkPanel({ activeView = "overview" }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    fetchJianyingEditorSdkStatus()
      .then((data) => {
        if (mounted) {
          setStatus(data);
          setError("");
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(err.message || String(err));
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const guideUrl = `${API_BASE}/api/tools/jianying-editor-sdk/page`;
  const entries = status?.entries || [];
  const checks = status?.checks || {};
  const capabilityItems = status?.capability_matrix || [];
  const warnings = status?.warnings || [];
  const readinessItems = [
    ["JyProject 导入", checks.jyproject_import],
    ["必要依赖", checks.sdk_requirements],
    ["可选依赖", checks.optional_requirements],
    ["平台限制", checks.platform],
  ];
  const workflowCapabilityItems = (capabilityItems || []).filter((item) => item?.implemented || item?.available);
  const sdkStateLabel = status?.ready ? "可接入" : status ? "需补环境" : "检查中";

  return (
    <section className="jianying-sdk-panel sdk-reference-panel">
      <section className="panel sdk-hero-panel">
        <div className="panel-header">
          <div>
            <h2>开发者参考</h2>
            <p>这里不再承担主操作流程，只说明当前本地 SDK 是否能支撑“结构规范 到 素材补齐 到 JyProject 草稿”这条链路。</p>
          </div>
          <Badge status={status?.ready ? "ready" : status ? "draft" : "draft"}>{sdkStateLabel}</Badge>
        </div>
        {error ? (
          <div className="error-box">{error}</div>
        ) : (
          <div className="sdk-summary-grid">
            <div>
              <span>本地路径</span>
              <strong>{status?.root || "sdks/jianying-editor-skill"}</strong>
            </div>
            <div>
              <span>上游仓库</span>
              <a href={status?.repo_url || "https://github.com/luoluoluo22/jianying-editor-skill"} target="_blank" rel="noreferrer">
                GitHub
              </a>
            </div>
            <div>
              <span>版本</span>
              <strong>{status?.version || "读取中"}</strong>
            </div>
            <div>
              <span>锁定模式</span>
              <strong>{status?.lock?.mode || "未读取"}</strong>
            </div>
          </div>
        )}
      </section>

      <section className="sdk-reference-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>链路判断</h2>
              <p>重点看当前项目是否具备你要的三步闭环。</p>
            </div>
          </div>
          <div className="sdk-entry-list">
            <article className="sdk-entry">
              <div>
                <strong>1. AI 生成结构规范</strong>
                <p>前端主流程已改成结构段/时间线导向，不再要求用户在页面里逐镜头编辑。</p>
              </div>
              <Badge status="ready">已对齐</Badge>
            </article>
            <article className="sdk-entry">
              <div>
                <strong>2. 输入第三方素材路径</strong>
                <p>支持直接粘贴视频、图片、音频路径，也允许不全量手工准备。</p>
              </div>
              <Badge status="ready">已对齐</Badge>
            </article>
            <article className="sdk-entry">
              <div>
                <strong>3. 自动补齐并生成 `JyProject` 草稿</strong>
                <p>可调用素材补齐与草稿生成链路；字幕、BGM 等保持可选，不强行塞进主操作面板。</p>
              </div>
              <Badge status={status?.ready ? "ready" : "draft"}>{status?.ready ? "可执行" : "依赖待确认"}</Badge>
            </article>
          </div>
          {warnings.length > 0 && <div className="running-note">{warnings.join(" ")}</div>}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>环境状态</h2>
              <p>只保留这条主链路相关的环境信号。</p>
            </div>
          </div>
          <div className="sdk-entry-list">
            {readinessItems.map(([label, check]) => (
              <article className="sdk-entry" key={label}>
                <div>
                  <strong>{label}</strong>
                  <p>{check?.message || "等待状态接口返回"}</p>
                </div>
                <Badge status={check?.ok ? "ready" : "draft"}>{check?.ok ? "通过" : "待确认"}</Badge>
              </article>
            ))}
          </div>
        </section>
      </section>

      <section className="sdk-reference-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>当前接入能力</h2>
              <p>这里只展示已接入或已声明的能力，不再把它们全部做成操作工作台。</p>
            </div>
          </div>
          <div className="sdk-entry-list">
            {workflowCapabilityItems.length ? workflowCapabilityItems.map((item) => (
              <article className="sdk-entry" key={item.key}>
                <div>
                  <strong>{item.label}</strong>
                  <p>{item.message || (item.available ? "当前环境可尝试使用" : "当前环境未完全验证")}</p>
                  <div className="sdk-capability-meta">
                    <code>{item.endpoint}</code>
                    <span>{item.invocation}</span>
                  </div>
                </div>
                <Badge status={item.available ? "ready" : "draft"}>{item.available ? "可用" : "已接入"}</Badge>
              </article>
            )) : <div className="empty-result">能力矩阵尚未返回。</div>}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>SDK 入口</h2>
              <p>保留源码入口和网页说明，方便后续继续接 SDK 能力。</p>
            </div>
            <a className="text-button" href={guideUrl} target="_blank" rel="noreferrer">
              打开网页说明
            </a>
          </div>
          <div className="sdk-entry-list">
            {entries.length ? entries.map((entry) => (
              <article className="sdk-entry" key={entry.relative_path}>
                <div>
                  <strong>{entry.name}</strong>
                  <p>{entry.description}</p>
                  <code>{entry.relative_path}</code>
                </div>
                <Badge status={entry.exists ? "ready" : "error"}>{entry.exists ? "已找到" : "缺失"}</Badge>
              </article>
            )) : <div className="empty-result">正在读取 SDK 入口...</div>}
          </div>
        </section>
      </section>
    </section>
  );
}
