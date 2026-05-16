import { useState } from "react";
import { Badge } from "../../components/common/index";
import { cleanScriptValue, safeSlice, sceneDuration, sceneSummary } from "../../utils/appUtils";

export const studioComponentMap = {
  SeedInput: StudioSeedInputBlock,
  AngleSelector: StudioAngleSelectorBlock,
  ConceptBible: StudioConceptBibleBlock,
  SceneBlueprint: StudioSceneBlueprintBlock,
  ThinkingBlock: StudioThinkingBlock,
  ErrorBlock: StudioErrorBlock,
};

export function StudioBlockRenderer({ block, onAction, onRetry }) {
  const Component = studioComponentMap[block.componentType] || StudioErrorBlock;
  return <Component data={block.payload} locked={block.isLocked} onAction={onAction} onRetry={onRetry} />;
}

export function StudioSeedInputBlock({ data, locked, onAction }) {
  const [draft, setDraft] = useState({
    type: data?.type || "短视频",
    creativePreset: data?.creativePreset || "default",
    title: data?.title || "",
    idea: data?.idea || "",
    provider: data?.provider || "",
  });

  if (locked) {
    return (
      <article className="studio-block locked">
        <Badge status="done">已锁定</Badge>
        <div className="studio-block-kicker">Seed</div>
        <h3>{draft.title || safeSlice(draft.idea, 18) || "未命名灵感"}</h3>
        <p>{draft.idea}</p>
        <div className="studio-chip-row">
          <span>{draft.type}</span>
          <span>{draft.creativePreset}</span>
        </div>
      </article>
    );
  }

  return (
    <form className="studio-block active" onSubmit={(event) => {
      event.preventDefault();
      onAction({ type: "submit", payload: draft });
    }}>
      <div className="panel-header">
        <div>
          <h3>提供灵感</h3>
          <p>先输入一个种子，AI 只负责发散方向，不直接写分镜。</p>
        </div>
        <Badge>The Seed</Badge>
      </div>
      <div className="studio-seed-grid">
        <label>
          题材 / 流派
          <select value={draft.creativePreset} onChange={(event) => setDraft({ ...draft, creativePreset: event.target.value })}>
            <option value="default">通用短剧模板</option>
            <option value="mysticism_lead">玄学引流模板</option>
            <option value="ancient爽文">古风爽文漫剧</option>
            <option value="ai_pet">AI 小动物剧情</option>
          </select>
        </label>
        <label>
          标题
          <input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="例如：我在盛唐写天下" />
        </label>
        <label>
          AI Provider
          <select value={draft.provider} onChange={(event) => setDraft({ ...draft, provider: event.target.value })}>
            <option value="">使用当前全局 AI</option>
            <option value="mock">mock 调试</option>
          </select>
        </label>
      </div>
      <label>
        灵感关键词
        <textarea value={draft.idea} onChange={(event) => setDraft({ ...draft, idea: event.target.value })} placeholder="例如：塔罗牌为什么总能说中你的心事" required />
      </label>
      <div className="script-action-strip">
        <button className="primary-button" type="submit">让 AI 发散方向</button>
      </div>
    </form>
  );
}

export function StudioAngleSelectorBlock({ data, locked, onAction }) {
  const [selectedId, setSelectedId] = useState(data?.selectedAngle?.id || data?.angles?.[0]?.id || "");
  const [feedback, setFeedback] = useState(data?.feedback || "");
  const selectedAngle = (data?.angles || []).find((angle) => angle.id === selectedId) || data?.selectedAngle;

  if (locked) {
    return (
      <article className="studio-block locked">
        <Badge status="done">已锁定</Badge>
        <div className="studio-block-kicker">Angle</div>
        <h3>{selectedAngle?.title || "已选择方向"}</h3>
        <p>{selectedAngle?.description}</p>
        {feedback && <blockquote>{feedback}</blockquote>}
      </article>
    );
  }

  return (
    <section className="studio-block active">
      <div className="panel-header">
        <div>
          <h3>选择剧情脉络</h3>
          <p>先决定切入点，再让 AI 收束为设定集。</p>
        </div>
        <Badge>3 angles</Badge>
      </div>
      <div className="studio-angle-grid">
        {(data?.angles || []).map((angle) => (
          <button className={`studio-angle-card ${selectedId === angle.id ? "active" : ""}`} key={angle.id} type="button" onClick={() => setSelectedId(angle.id)}>
            <strong>{angle.title}</strong>
            <span>{angle.description}</span>
          </button>
        ))}
      </div>
      <label>
        微调意见
        <textarea value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="例如：选方向一，但语调要再高冷一点" />
      </label>
      <div className="script-action-strip">
        <button className="primary-button" type="button" onClick={() => onAction({ type: "select", payload: { selectedAngle, feedback } })} disabled={!selectedAngle}>
          锁定方向并生成设定集
        </button>
      </div>
    </section>
  );
}

export function StudioConceptBibleBlock({ data, locked, onAction }) {
  const [bible, setBibleDraft] = useState(data?.bible || {});
  const [settings, setSettings] = useState({ durationSeconds: 30, sceneCount: 5, resolution: "9:16" });
  const update = (key, value) => setBibleDraft((current) => ({ ...current, [key]: value }));

  if (locked) {
    return (
      <article className="studio-block locked">
        <Badge status="done">已锁定</Badge>
        <div className="studio-block-kicker">Concept Bible</div>
        <h3>设定集已锁定</h3>
        <dl className="studio-readonly-grid">
          <dt>主角</dt><dd>{bible.character_base_prompt}</dd>
          <dt>画风</dt><dd>{bible.art_style_prompt}</dd>
          <dt>声音</dt><dd>{bible.voice_vibe}</dd>
        </dl>
      </article>
    );
  }

  return (
    <section className="studio-block active">
      <div className="panel-header">
        <div>
          <h3>审查设定集</h3>
          <p>这里是关键拦截点。锁定后，后续镜头会继承这些全局 Prompt。</p>
        </div>
        <Badge>The Bible</Badge>
      </div>
      <div className="script-bible-grid">
        <label>主角视觉特征<textarea value={bible.character_base_prompt || ""} onChange={(event) => update("character_base_prompt", event.target.value)} /></label>
        <label>画面整体风格<textarea value={bible.art_style_prompt || ""} onChange={(event) => update("art_style_prompt", event.target.value)} /></label>
        <label>配音音色要求<textarea value={bible.voice_vibe || ""} onChange={(event) => update("voice_vibe", event.target.value)} /></label>
        <label>BGM 检索词<textarea value={bible.bgm_keywords || ""} onChange={(event) => update("bgm_keywords", event.target.value)} /></label>
      </div>
      <div className="script-chassis-grid studio-inline-settings">
        <label>预计总时长<input type="number" min="5" max="600" value={settings.durationSeconds} onChange={(event) => setSettings({ ...settings, durationSeconds: Number(event.target.value) })} /></label>
        <label>分镜上限<input type="number" min="1" max="30" value={settings.sceneCount} onChange={(event) => setSettings({ ...settings, sceneCount: Number(event.target.value) })} /></label>
        <label>视频比例<select value={settings.resolution} onChange={(event) => setSettings({ ...settings, resolution: event.target.value })}><option value="9:16">9:16</option><option value="16:9">16:9</option><option value="1:1">1:1</option></select></label>
      </div>
      <div className="script-action-strip">
        <button className="primary-button" type="button" onClick={() => onAction({ type: "confirm", payload: { bible, settings } })}>
          锁定设定并生成蓝图
        </button>
      </div>
    </section>
  );
}

export function StudioSceneBlueprintBlock({ data }) {
  const scenes = data?.scenes || data?.script?.scenes || [];
  return (
    <section className="studio-block active">
      <div className="panel-header">
        <div>
          <h3>素材蓝图</h3>
          <p>这些卡片就是后续生成图片、音频并回填草稿的采购单。</p>
        </div>
        <Badge status="ready">{scenes.length} 镜</Badge>
      </div>
      <div className="script-output-grid">
        {scenes.map((scene) => (
          <article className="script-output-card" key={scene.id || scene.scene_index}>
            <header>
              <div>
                <strong>{scene.title || `Scene ${scene.id || scene.scene_index}`}</strong>
                <span>{sceneSummary(scene)}</span>
              </div>
              <Badge>预计 {sceneDuration(scene)}s</Badge>
            </header>
            <label>配音文案<textarea readOnly value={cleanScriptValue(scene.audio_narration)} /></label>
            <label>生图/分镜提示词<textarea readOnly value={cleanScriptValue(scene.visual_prompt)} /></label>
            <div className="script-asset-status-row">
              <span>图片/视频 pending</span>
              <span>音频 pending</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function StudioThinkingBlock({ data }) {
  return (
    <section className="studio-block thinking">
      <span className="thinking-dot" />
      <strong>{data?.text || "AI 正在思考..."}</strong>
    </section>
  );
}

export function StudioErrorBlock({ data, onRetry }) {
  return (
    <section className="studio-block error">
      <strong>这一步失败了</strong>
      <p>{data?.message || "未知错误"}</p>
      <button className="secondary-action-button" type="button" onClick={onRetry}>回到这一步重试</button>
    </section>
  );
}

export function ScriptSceneWorkbench({ script, selectedSceneId, onSelectScene, onUpdateScene, onUpdateSceneEdit }) {
  const scenes = script?.scenes || [];
  const totalDuration = Number(script?.config?.total_duration_seconds || 0);
  const fallbackDuration = scenes.length && totalDuration ? Math.round((totalDuration / scenes.length) * 10) / 10 : 3;
  const selectedScene = scenes.find((scene) => scene.id === selectedSceneId) || scenes[0];

  if (!selectedScene) {
    return <div className="empty-result">当前剧本还没有镜头。</div>;
  }

  const audioValue = cleanScriptValue(selectedScene.audio_narration || selectedScene.narration);

  return (
    <section className="script-workbench">
      <aside className="scene-master-list">
        <div className="scene-master-head">
          <strong>分镜列表</strong>
          <span>{scenes.length} 个原子镜头</span>
        </div>
        <div className="scene-master-items">
          {scenes.map((scene, index) => (
            <button
              className={`scene-master-item ${scene.id === selectedScene.id ? "active" : ""}`}
              key={scene.id || index}
              type="button"
              onClick={() => onSelectScene(scene.id)}
            >
              <span>Scene {index + 1}</span>
              <small>{sceneDuration(scene, fallbackDuration)}s</small>
              <p>{sceneSummary(scene)}</p>
            </button>
          ))}
        </div>
      </aside>

      <section className="scene-detail-desk">
        <header className="scene-detail-head">
          <div>
            <span>Scene {scenes.indexOf(selectedScene) + 1}</span>
            <h3>{selectedScene.title || "原子镜头"}</h3>
          </div>
          <Badge>预计 {sceneDuration(selectedScene, fallbackDuration)}s</Badge>
        </header>

        <div className="track-editor-grid">
          <article className="track-card visual-track-card">
            <div className="track-card-head">
              <strong>文案</strong>
              <span>给脚本表达、屏幕文字和镜头摘要使用</span>
            </div>
            <label>
              镜头概括
              <textarea
                value={cleanScriptValue(selectedScene.summary)}
                onChange={(event) => onUpdateScene(selectedScene.id, "summary", event.target.value)}
              />
            </label>
            <label>
              屏幕花字
              <textarea
                value={cleanScriptValue(selectedScene.onscreen_text)}
                onChange={(event) => onUpdateScene(selectedScene.id, "onscreen_text", event.target.value)}
              />
            </label>
          </article>

          <article className="track-card audio-track-card">
            <div className="track-card-head">
              <strong>音频需求</strong>
              <span>给 TTS、旁白和声音设计使用</span>
            </div>
            <label>
              配音文案
              <textarea
                value={audioValue}
                onChange={(event) => {
                  onUpdateScene(selectedScene.id, "audio_narration", event.target.value);
                }}
              />
            </label>
            <label>
              音频需求
              <textarea
                value={cleanScriptValue(selectedScene.edit?.pacing || selectedScene.emotional_beat)}
                onChange={(event) => onUpdateSceneEdit(selectedScene.id, "pacing", event.target.value)}
                placeholder="例如：温柔女声、轻环境音、结尾加提示音"
              />
            </label>
            <label>
              音频素材路径
              <input
                value={cleanScriptValue(selectedScene.assets?.audio_path)}
                onChange={(event) => onUpdateScene(selectedScene.id, "assets.audio_path", event.target.value)}
                placeholder="例如：D:\\素材\\scene1.wav"
              />
            </label>
          </article>

          <article className="track-card visual-track-card">
            <div className="track-card-head">
              <strong>画面素材需求</strong>
              <span>给生图、找素材和画面合成使用</span>
            </div>
            <label>
              生图提示词
              <textarea
                value={cleanScriptValue(selectedScene.visual_prompt || selectedScene.shot_description)}
                onChange={(event) => onUpdateScene(selectedScene.id, "visual_prompt", event.target.value)}
              />
            </label>
            <label>
              画面主体
              <textarea
                value={cleanScriptValue(selectedScene.asset_requirements?.main_subject)}
                onChange={(event) => onUpdateScene(selectedScene.id, "asset_requirements.main_subject", event.target.value)}
                placeholder="例如：女孩手拿奶茶在落叶街道回头"
              />
            </label>
            <label>
              背景 / 场景
              <textarea
                value={cleanScriptValue(selectedScene.asset_requirements?.background)}
                onChange={(event) => onUpdateScene(selectedScene.id, "asset_requirements.background", event.target.value)}
                placeholder="例如：傍晚街道、暖黄色灯光、秋叶飘落"
              />
            </label>
            <label>
              情绪 / 画面氛围
              <textarea
                value={cleanScriptValue(selectedScene.asset_requirements?.mood)}
                onChange={(event) => onUpdateScene(selectedScene.id, "asset_requirements.mood", event.target.value)}
                placeholder="例如：温柔、治愈、轻松、心动"
              />
            </label>
            <label>
              视频素材路径
              <input
                value={cleanScriptValue(selectedScene.assets?.video_path)}
                onChange={(event) => onUpdateScene(selectedScene.id, "assets.video_path", event.target.value)}
                placeholder="例如：D:\\素材\\scene1.mp4"
              />
            </label>
            <label>
              图片素材路径
              <input
                value={cleanScriptValue(selectedScene.assets?.image_path)}
                onChange={(event) => onUpdateScene(selectedScene.id, "assets.image_path", event.target.value)}
                placeholder="例如：D:\\素材\\scene1.png"
              />
            </label>
          </article>

          <article className="track-card audio-track-card">
            <div className="track-card-head">
              <strong>转场 / 动效要求</strong>
              <span>给 JyProject 映射到剪映工程使用</span>
            </div>
            <label>
              转场
              <input
                value={cleanScriptValue(selectedScene.edit?.transition)}
                onChange={(event) => onUpdateSceneEdit(selectedScene.id, "transition", event.target.value)}
                placeholder="例如：fade / mix / 淡入淡出 / 混合"
              />
            </label>
            <label>
              动画
              <input
                value={cleanScriptValue(selectedScene.edit?.animation)}
                onChange={(event) => onUpdateSceneEdit(selectedScene.id, "animation", event.target.value)}
                placeholder="例如：fadein / glitch / zoom_in"
              />
            </label>
            <label>
              镜头运动
              <input
                value={cleanScriptValue(selectedScene.edit?.camera)}
                onChange={(event) => onUpdateSceneEdit(selectedScene.id, "camera", event.target.value)}
                placeholder="例如：push in / pan left / pan right"
              />
            </label>
            <label>
              实际素材时长（秒）
              <input
                type="number"
                min="0"
                step="0.1"
                value={selectedScene.assets?.duration ?? 0}
                onChange={(event) => onUpdateScene(selectedScene.id, "assets.duration", Number(event.target.value))}
              />
            </label>
          </article>
        </div>
      </section>
    </section>
  );
}

export function ScriptShotTable({ script }) {
  const scenes = script?.scenes || [];
  const totalDuration = Number(script?.config?.total_duration_seconds || 0);
  const defaultDuration = scenes.length && totalDuration ? Math.round((totalDuration / scenes.length) * 10) / 10 : 3;

  return (
    <section className="script-shot-table-panel">
      <div className="script-shot-toolbar">
        <div>
          <strong>脚本视图</strong>
          <span>{script?.config?.title || "未命名剧本"} · {scenes.length} 镜</span>
        </div>
        <Badge status="ready">{script?.config?.genre || "未分类"}</Badge>
      </div>
      <div className="script-shot-table-wrap">
        <table className="script-shot-table">
          <thead>
            <tr>
              <th>镜号</th>
              <th>时长</th>
              <th>标题</th>
              <th>镜头目标</th>
              <th>画面概括</th>
              <th>视觉提示词</th>
              <th>旁白</th>
              <th>屏幕文字</th>
              <th>转场</th>
              <th>动画</th>
              <th>节奏</th>
              <th>镜头运动</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {scenes.map((scene, index) => {
              const duration = scene.estimated_duration || scene.assets?.duration || defaultDuration;
              return (
                <tr key={scene.id || index}>
                  <td>{scene.id || index + 1}</td>
                  <td>{duration}</td>
                  <td>{scene.title || "-"}</td>
                  <td>{scene.scene_goal || "-"}</td>
                  <td>{scene.summary || "-"}</td>
                  <td>{scene.visual_prompt || "-"}</td>
                  <td>{scene.audio_narration || "-"}</td>
                  <td>{scene.onscreen_text || "-"}</td>
                  <td>{scene.edit?.transition || "-"}</td>
                  <td>{scene.edit?.animation || "-"}</td>
                  <td>{scene.edit?.pacing || "-"}</td>
                  <td>{scene.edit?.camera || "-"}</td>
                  <td>{scene.status || "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function ScriptRecordRow({ item, onOpen, onDelete }) {
  const progress = Math.max(0, Math.min(100, item.progress || 0));
  const done = item.status === "done";
  const failed = item.status === "failed" || item.status === "error";
  const statusLabel = done ? "完成" : failed ? "失败" : `进度 ${progress}%`;

  return (
    <details className="script-record-row">
      <summary>
        <strong>{item.title || "未命名剧本"}</strong>
        <span>{item.genre || "未填写类型"} · {item.scene_count || 0} 幕 · {item.resolution || "-"}</span>
        <Badge status={done ? "done" : failed ? "error" : "running"}>{statusLabel}</Badge>
      </summary>
      <div className="script-record-detail">
        <p>{item.message || "暂无进度信息"}</p>
        {!done && !failed && (
          <div className="progress">
            <span style={{ width: `${progress}%` }} />
          </div>
        )}
        <div className="task-action-row">
          {item.project_id && (
            <button className="text-button" type="button" onClick={() => onOpen(item.project_id)}>
              打开剧本
            </button>
          )}
          {item.project_id && (
            <button className="text-button danger-text-button" type="button" onClick={() => onDelete(item.project_id)}>
              删除
            </button>
          )}
        </div>
      </div>
    </details>
  );
}
