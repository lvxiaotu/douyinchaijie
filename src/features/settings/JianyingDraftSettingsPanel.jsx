import { Badge } from "../../components/common/index";

export function JianyingDraftSettingsPanel() {
  return (
    <section className="panel settings-wide">
      <div className="panel-header">
        <div>
          <h2>剪映草稿说明</h2>
          <p>草稿生成已经统一收口到 `剪映 Skill` 主流程，这里只保留查看路径、命名规则和使用说明，不再重复提供第二套生成入口。</p>
        </div>
        <Badge status="ready">Unified</Badge>
      </div>

      <section className="collector-card">
        <h3>当前统一链路</h3>
        <div className="step-list">
          {[
            ["1", "AI 生成内部结构规范", "先得到可继续补素材、补配音并生成草稿的结构结果。"],
            ["2", "输入第三方素材路径", "可以粘贴视频、图片、音频路径，也可以只给一部分。"],
            ["3", "自动补齐并生成 JyProject 草稿", "缺失素材可交给 AI 补齐，生成前支持手动修改草稿名称。"],
          ].map(([index, name, desc]) => (
            <article className="step-item" key={index}>
              <span>{index}</span>
              <div>
                <strong>{name}</strong>
                <p>{desc}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="collector-card">
        <h3>命名规则</h3>
        <div className="workflow-summary-grid compact">
          <article className="workflow-summary-card">
            <strong>默认命名</strong>
            <p>系统默认按日期时间命名，例如 `2026年5月9日16时22分`，方便你在剪映草稿目录里一眼识别。</p>
          </article>
          <article className="workflow-summary-card">
            <strong>生成前可改</strong>
            <p>在 `剪映 Skill` 的“补齐素材并生成草稿”步骤里，可以直接修改草稿名称，再输出到剪映。</p>
          </article>
          <article className="workflow-summary-card">
            <strong>查看方式</strong>
            <p>草稿生成后，到“查看草稿”里按项目点开，会看到可读解释，不只是原始 JSON。</p>
          </article>
        </div>
      </section>

      <section className="collector-card">
        <h3>建议使用</h3>
        <div className="script-action-strip">
          <button className="primary-button" type="button" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
            返回顶部
          </button>
          <span className="field-hint">主操作请使用左侧导航中的 `剪映 Skill` 与 `查看草稿`。</span>
        </div>
      </section>
    </section>
  );
}
