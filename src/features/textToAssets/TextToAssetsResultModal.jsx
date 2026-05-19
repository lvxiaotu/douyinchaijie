export function TextToAssetsResultModal({ task, onClose, pageMode = false }) {
  if (!task) return null;
  const result = task.result || {};
  const aRollItems = Array.isArray(result.a_roll_prompts) ? result.a_roll_prompts : [];
  const bRollItems = Array.isArray(result.b_roll_list) ? result.b_roll_list : [];
  const creativeDirection = result.creative_direction && typeof result.creative_direction === "object" ? result.creative_direction : {};
  const audioPlan = result.audio_plan && typeof result.audio_plan === "object" ? result.audio_plan : {};
  const sfxItems = Array.isArray(audioPlan.sfx) ? audioPlan.sfx : [];
  const voiceoverItems = Array.isArray(audioPlan.voiceover) ? audioPlan.voiceover : [];
  const bgmStyle = audioPlan.bgm_style && typeof audioPlan.bgm_style === "object"
    ? audioPlan.bgm_style
    : { genre: audioPlan.bgm_style || "" };
  const notes = Array.isArray(result.notes) ? result.notes : [];
  const isPageMode = Boolean(pageMode);

  return (
    <div className={isPageMode ? "result-page-host" : "modal-backdrop"} role={isPageMode ? undefined : "presentation"} onClick={isPageMode ? undefined : onClose}>
      <section
        className={`modal-panel ${isPageMode ? "result-page-panel" : ""}`}
        role={isPageMode ? "region" : "dialog"}
        aria-modal={isPageMode ? undefined : true}
        onClick={isPageMode ? undefined : (event) => event.stopPropagation()}
      >
        <div className="panel-header">
          <div>
            <h2>Text-to-Assets 结果</h2>
            <p>{task.title}</p>
          </div>
          <button className="text-button" type="button" onClick={onClose}>
            {isPageMode ? "返回列表" : "关闭"}
          </button>
        </div>
        <div className="analysis-result-body">
          <p>{result.summary || "暂无摘要"}</p>
          {result.master_prompt && (
            <div className="analysis-section">
              <strong>已应用主提示词</strong>
              <pre className="result-box">{result.master_prompt}</pre>
            </div>
          )}
          {result.draft_markdown && (
            <div className="analysis-section">
              <strong>AI 初稿 Markdown</strong>
              <pre className="result-box">{result.draft_markdown}</pre>
            </div>
          )}
          {result.creative_direction && (
            <div className="analysis-section">
              <strong>创意执行方向</strong>
              <div className="result-grid">
                <article>
                  <span>内容定位</span>
                  <p>{creativeDirection.positioning || "暂无内容"}</p>
                </article>
                <article>
                  <span>目标观众</span>
                  <p>{creativeDirection.audience || "暂无内容"}</p>
                </article>
                <article>
                  <span>整体气质</span>
                  <p>{creativeDirection.tone || "暂无内容"}</p>
                </article>
                <article>
                  <span>画面风格</span>
                  <p>{creativeDirection.visual_style || "暂无内容"}</p>
                </article>
                <article>
                  <span>节奏设计</span>
                  <p>{creativeDirection.rhythm || "暂无内容"}</p>
                </article>
                <article>
                  <span>开头钩子</span>
                  <p>{creativeDirection.hook || "暂无内容"}</p>
                </article>
                <article>
                  <span>转化目标</span>
                  <p>{creativeDirection.conversion_goal || "暂无内容"}</p>
                </article>
              </div>
            </div>
          )}
          <div className="analysis-section">
            <strong>主视觉画面 A-Roll 提示词</strong>
            {aRollItems.length ? (
              aRollItems.map((item, index) => (
                <div className="analysis-field shot-replica-field" key={item.id || index}>
                  <span>{item.id || `A${index + 1}`} · {item.title || `主镜头 ${index + 1}`}</span>
                  <dl className="shot-replica-list">
                    <div className="wide">
                      <dt>Prompt</dt>
                      <dd>{item.prompt || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>镜头目标</dt>
                      <dd>{item.shot_goal || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>运镜方式</dt>
                      <dd>{item.camera || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>构图设计</dt>
                      <dd>{item.composition || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>光线设计</dt>
                      <dd>{item.lighting || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>主体动作</dt>
                      <dd>{item.subject_action || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>转场方式</dt>
                      <dd>{item.transition || "暂无内容"}</dd>
                    </div>
                    <div>
                      <dt>时长</dt>
                      <dd>{item.duration_seconds ? `${item.duration_seconds} 秒` : "暂无内容"}</dd>
                    </div>
                    <div className="wide">
                      <dt>执行补充</dt>
                      <dd>{item.art_direction_notes || "暂无内容"}</dd>
                    </div>
                  </dl>
                </div>
              ))
            ) : (
              <p>暂无 A-Roll 内容</p>
            )}
          </div>
          <div className="analysis-section">
            <strong>空镜头 / B-Roll 清单</strong>
            {bRollItems.length ? (
              bRollItems.map((item, index) => (
                <div className="analysis-field" key={`${item.title || "b-roll"}-${index}`}>
                  <span>{item.title || `B-Roll ${index + 1}`}</span>
                  <p>{item.description || "暂无内容"}</p>
                  <p>{item.purpose ? `用途：${item.purpose}` : "用途：暂无内容"}</p>
                  <p>{item.insert_timing ? `插入位置：${item.insert_timing}` : "插入位置：暂无内容"}</p>
                  <p>{item.capture_notes ? `拍摄提醒：${item.capture_notes}` : "拍摄提醒：暂无内容"}</p>
                </div>
              ))
            ) : (
              <p>暂无 B-Roll 内容</p>
            )}
          </div>
          <div className="analysis-section">
            <strong>音频素材清单</strong>
            <div className="result-grid">
              <article>
                <span>音效 SFX</span>
                <p>
                  {sfxItems.length
                    ? sfxItems
                        .map((item) =>
                          typeof item === "string"
                            ? item
                            : [item.name, item.usage && `用途：${item.usage}`, item.timing && `时机：${item.timing}`]
                                .filter(Boolean)
                                .join(" / "),
                        )
                        .join("\n")
                    : "暂无内容"}
                </p>
              </article>
              <article>
                <span>BGM 风格</span>
                <p>
                  {[
                    bgmStyle.genre && `类型：${bgmStyle.genre}`,
                    bgmStyle.mood && `情绪：${bgmStyle.mood}`,
                    bgmStyle.tempo && `节奏：${bgmStyle.tempo}`,
                    Array.isArray(bgmStyle.instruments) && bgmStyle.instruments.length
                      ? `元素：${bgmStyle.instruments.join(" / ")}`
                      : "",
                    bgmStyle.mix_notes && `混音建议：${bgmStyle.mix_notes}`,
                  ]
                    .filter(Boolean)
                    .join("\n") || "暂无内容"}
                </p>
              </article>
            </div>
          </div>
          <div className="analysis-section">
            <strong>旁白台词 Voiceover</strong>
            {voiceoverItems.length ? (
              voiceoverItems.map((item, index) => (
                <div className="analysis-field" key={item.id || index}>
                  <span>{item.id || `V${index + 1}`} {item.for_shot ? `· 对应 ${item.for_shot}` : ""}</span>
                  <p>{item.line || "暂无内容"}</p>
                  <p>{item.tone ? `语气：${item.tone}` : "语气：暂无内容"}</p>
                  <p>{item.delivery_notes ? `朗读建议：${item.delivery_notes}` : "朗读建议：暂无内容"}</p>
                </div>
              ))
            ) : (
              <p>暂无旁白内容</p>
            )}
          </div>
          {notes.length > 0 && (
            <div className="analysis-section">
              <strong>执行备注</strong>
              {notes.map((note, index) => (
                <div className="analysis-field" key={index}>
                  <span>{typeof note === "string" ? `备注 ${index + 1}` : note.title || `备注 ${index + 1}`}</span>
                  <p>{typeof note === "string" ? note : note.detail || "暂无内容"}</p>
                </div>
              ))}
            </div>
          )}
          {result.final_markdown && (
            <div className="analysis-section">
              <strong>最终汇总 Markdown</strong>
              <pre className="result-box">{result.final_markdown}</pre>
            </div>
          )}
          <details className="raw-json">
            <summary>查看原始 JSON</summary>
            <pre className="result-box">{JSON.stringify(task, null, 2)}</pre>
          </details>
        </div>
      </section>
    </div>
  );
}
