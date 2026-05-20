import { Check, Copy, Download, Play, Send, Wand2 } from "lucide-react";
import { Badge } from "../../components/common/index";
import {
  actionableText,
  buildRemakeItems,
  buildRemakeMarkdown,
  formatValue,
  formatTimeLabel,
  getCommentKeywords,
  getCommentMotivations,
  radarConclusion,
  secondsToLabel,
} from "../../utils/aiVideoAnalysisView";
import { compactNumber } from "../../utils/appUtils";

const RADAR_SIZE = 190;
const RADAR_CENTER = RADAR_SIZE / 2;
const RADAR_RADIUS = 72;
const EMPTY_TEXT = "暂无内容";

function clampScore(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, Math.round(number)));
}

function radarPoint(index, total, value = 100) {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / total;
  const radius = RADAR_RADIUS * (clampScore(value) / 100);
  return [RADAR_CENTER + Math.cos(angle) * radius, RADAR_CENTER + Math.sin(angle) * radius];
}

function radarAxisPoint(index, total) {
  return radarPoint(index, total, 100);
}

export function InfoPill({ label, value, tone = "neutral" }) {
  return (
    <div className={`content-lab-info-pill ${tone}`}>
      <span>{label}</span>
      <strong>{value || EMPTY_TEXT}</strong>
    </div>
  );
}

export function MetricRadar({ items, genre }) {
  const points = items.map(([, value], index) => radarPoint(index, items.length, value).join(",")).join(" ");
  const gridLevels = [25, 50, 75, 100];
  return (
    <div className="content-lab-radar-card">
      <svg className="content-lab-radar" viewBox={`0 0 ${RADAR_SIZE} ${RADAR_SIZE}`} role="img" aria-label="多维数据雷达图">
        {gridLevels.map((level) => (
          <polygon
            key={level}
            points={items.map((_, index) => radarPoint(index, items.length, level).join(",")).join(" ")}
            className="radar-grid"
          />
        ))}
        {items.map((_, index) => {
          const [x, y] = radarAxisPoint(index, items.length);
          return <line key={index} x1={RADAR_CENTER} y1={RADAR_CENTER} x2={x} y2={y} className="radar-axis" />;
        })}
        <polygon points={points} className="radar-shape" />
        {items.map(([label, value], index) => {
          const [x, y] = radarAxisPoint(index, items.length);
          return (
            <text key={label} x={x} y={y} textAnchor="middle" dominantBaseline="middle" className="radar-label">
              {label} {clampScore(value)}
            </text>
          );
        })}
      </svg>
      <p>{radarConclusion(items, genre)}</p>
    </div>
  );
}

export function SectionRows({ title, rows }) {
  return (
    <section className="analysis-section content-lab-detail-card">
      <strong>{title}</strong>
      <div className="content-lab-field-grid">
        {rows.map(([label, value]) => (
          <div className="analysis-field" key={label}>
            <span>{label}</span>
            <p>{formatValue(value)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export function ResultOverview({
  author,
  evidence,
  genre,
  radarItems,
  result,
  segmentCount,
  task,
  taskVideo,
  topMetaStats,
  topMetaTags,
  videoInfo,
}) {
  return (
    <section className="content-lab-overview">
      <div className="content-lab-summary">
        <span>{genre}</span>
        <p>{result.summary || "暂无摘要"}</p>
        {(result.analysis_mode || evidence.evidence_path) && (
          <small>
            {result.analysis_mode || "evidence"} · {(evidence.transcript_provider || "未知转写器")} · {evidence.analysis_segments_count || segmentCount || 0} 个分析片段 · {evidence.keyframes_count || 0} 张关键帧
          </small>
        )}
        <div className="content-lab-summary-lower">
          <div className="content-lab-summary-lower-left">
            <div className="content-lab-profile-author">
              {author.avatar ? (
                <img className="content-lab-profile-avatar" src={author.avatar} alt="作者头像" />
              ) : (
                <div className="content-lab-profile-avatar placeholder">{(author.nickname || task?.title || "A").slice(0, 1)}</div>
              )}
              <div>
                <strong>{author.nickname || task?.title || "未返回作者信息"}</strong>
                <p>账号标识：{author.display_id || author.unique_id || author.uid || author.sec_uid || "未返回"}</p>
                <span>简介：{author.signature || "暂无简介"}</span>
              </div>
            </div>
            <div className="content-lab-profile-meta">
              <InfoPill label="赛道" value={genre} tone="blue" />
              <InfoPill label="发布时间" value={formatTimeLabel(videoInfo.create_time || taskVideo?.create_time)} />
              <InfoPill label="作品ID" value={videoInfo.aweme_id || taskVideo?.aweme_id || "未返回"} />
              <InfoPill label="作品时长" value={videoInfo.duration ? `${videoInfo.duration}s` : "未返回"} />
              <InfoPill label="粉丝量" value={author.follower_count == null ? "未返回" : compactNumber(author.follower_count)} />
              <InfoPill label="作者获赞" value={author.like_count == null ? "未返回" : compactNumber(author.like_count)} />
            </div>
            <div className="content-lab-profile-tags">
              {topMetaTags.length ? topMetaTags.map((tag) => <Badge key={tag}>{tag}</Badge>) : <span className="field-hint">暂无标签数据</span>}
            </div>
            <div className="content-lab-profile-stats">
              {topMetaStats.map((item) => (
                <InfoPill key={item.label} label={item.label} value={item.value} />
              ))}
            </div>
          </div>
        </div>
      </div>
      <MetricRadar items={radarItems} genre={genre} />
    </section>
  );
}

export function CommentIntelligence({ snapshot, loading, error }) {
  const keywords = getCommentKeywords(snapshot);
  const motivations = getCommentMotivations(snapshot);
  const pinned = Array.isArray(snapshot?.pinned_comments) ? snapshot.pinned_comments : [];
  const topComments = Array.isArray(snapshot?.top_comments) ? snapshot.top_comments : [];
  const authorReplies = Array.isArray(snapshot?.author_replies) ? snapshot.author_replies : [];
  const savedTotal = Number(snapshot?.comment_saved_count || 0) + Number(snapshot?.reply_saved_count || 0);
  return (
    <div className="analysis-section content-lab-comments">
      <strong>评论区洞察</strong>
      {loading && <p className="field-hint">正在读取评论库...</p>}
      {error && <p className="field-hint">评论库读取失败：{error}</p>}
      <div className="content-lab-chip-grid">
        {(motivations.length ? motivations : [[savedTotal ? "已保存评论/回复" : "暂无动机数据", savedTotal]]).map(([label, value]) => (
          <span key={label}>
            {label} · {value}
          </span>
        ))}
      </div>
      <div className="content-lab-comment-grid">
        <div className="analysis-field">
          <span>高频互动词</span>
          <p>{keywords.map(([label, value]) => `${label}(${value})`).join(" / ") || "暂无内容"}</p>
        </div>
        <div className="analysis-field">
          <span>置顶/神评</span>
          <p>{formatValue(pinned[0] || topComments[0])}</p>
        </div>
        <div className="analysis-field">
          <span>作者留人话术</span>
          <p>{formatValue(authorReplies[0])}</p>
        </div>
      </div>
      <div className="content-lab-top-comments">
        <span>点赞最高评论</span>
        {topComments.length ? (
          topComments.map((comment, index) => (
            <article key={comment.id || `${comment.text}-${index}`}>
              <div>
                <strong>
                  {index + 1}. {comment.nickname || "匿名用户"}
                </strong>
                <p>{comment.text}</p>
              </div>
              <small>
                {comment.digg_count || 0} 赞 · {comment.reply_count || 0} 回复
              </small>
            </article>
          ))
        ) : (
          <p>{loading ? "正在加载评论..." : "暂无已保存评论"}</p>
        )}
      </div>
    </div>
  );
}

export function VideoTranscriptSyncPanel({ videoRef, videoUrl, posterUrl, transcriptLines, activeTranscriptId, evidenceStatus, onSeek }) {
  return (
    <section className="analysis-section content-lab-video-sync">
      <div className="content-lab-section-head">
        <strong>原视频同步拆解</strong>
        <span className="content-lab-sync-count">{transcriptLines.length ? `${transcriptLines.length} 条转写` : "暂无转写片段"}</span>
      </div>
      <div className="content-lab-video-sync-grid">
        <div className="content-lab-video-frame">
          {videoUrl ? (
            <video ref={videoRef} src={videoUrl} poster={posterUrl || undefined} controls preload="metadata" playsInline />
          ) : (
            <div className="content-lab-video-empty">
              <Play size={32} />
              <p>{evidenceStatus.loading ? "正在读取证据视频..." : "暂无可播放视频"}</p>
            </div>
          )}
        </div>
        <div className="content-lab-transcript-panel">
          <div className="content-lab-transcript-head">
            <span>语音转文字</span>
            {evidenceStatus.error && <small>证据读取失败：{evidenceStatus.error}</small>}
          </div>
          <div className="content-lab-transcript-list">
            {transcriptLines.length ? (
              transcriptLines.map((line, index) => {
                const isActive = String(activeTranscriptId) === String(line.id);
                return (
                  <button
                    className={`content-lab-transcript-line ${isActive ? "active" : ""}`}
                    type="button"
                    key={`${line.id}-${index}`}
                    onClick={() => onSeek(line)}
                  >
                    <span>{secondsToLabel(line.start)}</span>
                    <p>{line.text}</p>
                  </button>
                );
              })
            ) : (
              <p className="field-hint">{evidenceStatus.loading ? "正在读取完整 ASR 文本..." : "暂无完整转写文本"}</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

export function SegmentTimeline({ segments, onSeek, activeTranscriptId }) {
  if (!segments.length) return null;
  return (
    <div className="analysis-section content-lab-timeline">
      <strong>多模态双轨时间线</strong>
      <div className="content-lab-timeline-list">
        {segments.map((segment, index) => (
          <article
            className={`content-lab-timeline-item ${segment.transcript ? "has-transcript" : ""}`}
            key={segment.id || segment.segment_id || index}
          >
            <div className="content-lab-time-mark">
              <button className="content-lab-time-jump" type="button" onClick={() => onSeek?.(segment)}>
                {segment.time_range || secondsToLabel(segment.start) || `片段 ${index + 1}`}
              </button>
              <strong>{segment.segment_role || "未标注"}</strong>
            </div>
            {segment.transcript && (
              <div className="content-lab-track content-lab-track-wide">
                <span>语音转文字</span>
                <button
                  className={`content-lab-segment-transcript ${String(activeTranscriptId) === String(segment.id || segment.segment_id) ? "active" : ""}`}
                  type="button"
                  onClick={() => onSeek?.(segment)}
                >
                  {segment.transcript}
                </button>
              </div>
            )}
            <div className="content-lab-track">
              <span>视听手法</span>
              <p>{[segment.visual_style, segment.audio_pacing].filter(Boolean).join(" / ") || "暂无内容"}</p>
            </div>
            <div className="content-lab-track">
              <span>心理拆解</span>
              <p>{[segment.narrative_technique, segment.retention_mechanism].filter(Boolean).join(" / ") || "暂无内容"}</p>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

export function RemakeLab({
  result,
  title,
  genre,
  targetGenre,
  onTargetGenreChange,
  onCopy,
  onExport,
  onRewrite,
  onSendToScript,
  actionStatus,
  pendingAction,
}) {
  const items = buildRemakeItems(result);
  const markdown = buildRemakeMarkdown({ result, title, genre, targetGenre });
  return (
    <div className="analysis-section content-lab-remake">
      <div className="content-lab-section-head">
        <strong>复刻实验室</strong>
        <div className="content-lab-actions">
          <button className="text-button" type="button" onClick={() => onCopy("full", markdown)}>
            {actionStatus === "copy:full" ? <Check size={15} /> : <Copy size={15} />}
            复制整套模板
          </button>
          <button className="text-button" type="button" onClick={() => onExport(markdown)}>
            <Download size={15} />
            导出 Markdown
          </button>
        </div>
      </div>

      <label className="analysis-field content-lab-target-field">
        <span>目标赛道</span>
        <input
          type="text"
          value={targetGenre}
          placeholder="beauty / knowledge / comedy / ecommerce"
          onChange={(event) => onTargetGenreChange(event.target.value)}
        />
      </label>

      <div className="content-lab-remake-grid">
        {items.map((item) => {
          const text = actionableText(item.value);
          const copied = actionStatus === `copy:${item.id}`;
          return (
            <div className={item.wide ? "content-lab-template" : "content-lab-token-row"} key={item.id}>
              <div className="content-lab-copy-head">
                <span>{item.label}</span>
                <button className="text-button compact-copy-button" type="button" disabled={!text} onClick={() => onCopy(item.id, text)}>
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  {copied ? "已复制" : "复制"}
                </button>
              </div>
              <p>{text || EMPTY_TEXT}</p>
            </div>
          );
        })}
      </div>

      <div className="content-lab-actions content-lab-lab-actions">
        <button className="text-button" type="button" onClick={() => onRewrite(markdown)} disabled={pendingAction === "rewrite"}>
          <Wand2 size={15} />
          {pendingAction === "rewrite" ? "改写中..." : "跨赛道改写"}
        </button>
        <button className="text-button" type="button" onClick={() => onSendToScript(markdown)} disabled={pendingAction === "script"}>
          <Send size={15} />
          {pendingAction === "script" ? "送入脚本..." : "送入脚本生成"}
        </button>
      </div>
    </div>
  );
}
