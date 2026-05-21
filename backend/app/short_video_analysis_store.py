from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.postgres_store import pg_connection, run_once
from integrations.ai_video_analysis.result_schema import validate_analysis_result

CHINA_TZ = timezone(timedelta(hours=8))

DEFAULT_BASELINE_THRESHOLDS = {
    "interaction_rate": 0.05,
    "save_rate": 0.08,
    "share_rate": 0.03,
}

BASELINE_ENV_NAMES = {
    "interaction_rate": "SHORT_VIDEO_BASELINE_INTERACTION_RATE",
    "save_rate": "SHORT_VIDEO_BASELINE_SAVE_RATE",
    "share_rate": "SHORT_VIDEO_BASELINE_SHARE_RATE",
}

PROPERTY_TAG_RULES = {
    "interaction_rate": "high_interaction_or_controversy",
    "save_rate": "high_value_or_save_worthy",
    "share_rate": "high_resonance_or_shareable",
}


def connect():
    return pg_connection("short_video_analysis")


def load_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ratio(numerator: Any, denominator: Any) -> float | None:
    num = to_int(numerator)
    den = to_int(denominator)
    if num is None or den in (None, 0):
        return None
    return round(num / den, 6)


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def baseline_thresholds(genre: str = "") -> dict[str, float]:
    normalized_genre = str(genre or "").strip().upper().replace("-", "_").replace(" ", "_")
    thresholds: dict[str, float] = {}
    for metric, default in DEFAULT_BASELINE_THRESHOLDS.items():
        env_name = BASELINE_ENV_NAMES[metric]
        candidates = []
        if normalized_genre:
            candidates.append(f"SHORT_VIDEO_BASELINE_{normalized_genre}_{metric.upper()}")
        candidates.append(env_name)
        value = None
        for candidate in candidates:
            value = to_float(os.getenv(candidate))
            if value is not None:
                break
        thresholds[metric] = value if value is not None else default
    return thresholds


def now() -> int:
    return int(time.time())


def init_db() -> None:
    def initialize() -> None:
        _init_db()

    run_once("short_video_analysis_store", initialize)


def _init_db() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS short_video_items (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL DEFAULT '',
                source_id TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                author_id TEXT NOT NULL DEFAULT '',
                author_name TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                genre TEXT NOT NULL DEFAULT '',
                publish_time INTEGER,
                publish_hour INTEGER,
                publish_weekday INTEGER,
                cover_url TEXT NOT NULL DEFAULT '',
                video_url TEXT NOT NULL DEFAULT '',
                local_video_path TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(platform, source_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS short_video_metric_snapshots (
                id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                like_count INTEGER,
                comment_count INTEGER,
                share_count INTEGER,
                collect_count INTEGER,
                play_count INTEGER,
                interaction_rate REAL,
                save_rate REAL,
                share_rate REAL,
                engagement_score REAL,
                engagement_rate REAL,
                property_tags_json TEXT NOT NULL DEFAULT '[]',
                raw_json TEXT NOT NULL DEFAULT '{}',
                captured_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS short_video_analysis_runs (
                id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                task_id TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                model_summary TEXT NOT NULL DEFAULT '',
                genre TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'done',
                evidence_path TEXT NOT NULL DEFAULT '',
                job_path TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL DEFAULT '{}',
                markdown_report TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(task_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS short_video_analysis_segments (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                video_id TEXT NOT NULL,
                segment_id TEXT NOT NULL DEFAULT '',
                start_seconds REAL,
                end_seconds REAL,
                time_range TEXT NOT NULL DEFAULT '',
                transcript TEXT NOT NULL DEFAULT '',
                visual_style TEXT NOT NULL DEFAULT '',
                audio_pacing TEXT NOT NULL DEFAULT '',
                narrative_technique TEXT NOT NULL DEFAULT '',
                retention_mechanism TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(run_id, segment_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS short_video_formula_library (
                id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                genre TEXT NOT NULL DEFAULT '',
                formula_name TEXT NOT NULL DEFAULT '',
                generic_formula TEXT NOT NULL DEFAULT '',
                hook_template TEXT NOT NULL DEFAULT '',
                script_template TEXT NOT NULL DEFAULT '',
                cta_template TEXT NOT NULL DEFAULT '',
                visual_blueprint_json TEXT NOT NULL DEFAULT '{}',
                risk_json TEXT NOT NULL DEFAULT '{}',
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS short_video_remake_exports (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL DEFAULT '',
                video_id TEXT NOT NULL DEFAULT '',
                task_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                genre TEXT NOT NULL DEFAULT '',
                target_genre TEXT NOT NULL DEFAULT '',
                export_type TEXT NOT NULL DEFAULT 'remake_package',
                markdown TEXT NOT NULL DEFAULT '',
                source_json TEXT NOT NULL DEFAULT '{}',
                rewritten_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'saved',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_short_video_items_genre ON short_video_items(genre, updated_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_short_video_metrics_video ON short_video_metric_snapshots(video_id, captured_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_short_video_runs_video ON short_video_analysis_runs(video_id, updated_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_short_video_segments_run ON short_video_analysis_segments(run_id, start_seconds)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_short_video_formula_genre ON short_video_formula_library(genre, updated_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_short_video_remake_exports_run ON short_video_remake_exports(run_id, updated_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_short_video_remake_exports_genre ON short_video_remake_exports(genre, target_genre, updated_at)")


def row_to_video(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["raw"] = load_json(item.pop("raw_json"), {})
    return item


def row_to_metric(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["property_tags"] = load_json(item.pop("property_tags_json"), [])
    item["raw"] = load_json(item.pop("raw_json"), {})
    return item


def row_to_run(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["result"] = load_json(item.pop("result_json"), {})
    return item


def row_to_segment(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["raw"] = load_json(item.pop("raw_json"), {})
    return item


def row_to_formula(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["visual_blueprint"] = load_json(item.pop("visual_blueprint_json"), {})
    item["risk"] = load_json(item.pop("risk_json"), {})
    item["raw"] = load_json(item.pop("raw_json"), {})
    return item


def row_to_remake_export(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["source"] = load_json(item.pop("source_json"), {})
    item["rewritten"] = load_json(item.pop("rewritten_json"), {})
    return item


def publish_parts(timestamp: int | None) -> dict[str, Any]:
    if not timestamp:
        return {"publish_hour": None, "publish_weekday": None}
    published = datetime.fromtimestamp(timestamp, CHINA_TZ)
    return {"publish_hour": published.hour, "publish_weekday": published.weekday()}


def detect_platform(video: dict[str, Any]) -> str:
    if video.get("platform"):
        return str(video.get("platform") or "")
    if video.get("aweme_id") or "douyin" in str(video.get("source_url") or video.get("url") or "").lower():
        return "douyin"
    return str(video.get("source") or "unknown")


def normalize_video_source_id(video: dict[str, Any]) -> str:
    return str(video.get("aweme_id") or video.get("id") or video.get("source_id") or "")


def first_text(*values: Any) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def extract_counts(video: dict[str, Any]) -> dict[str, Any]:
    stats = video.get("statistics") if isinstance(video.get("statistics"), dict) else {}
    derived = video.get("derived_metrics") if isinstance(video.get("derived_metrics"), dict) else {}
    return {
        "like_count": to_int(video.get("digg_count") or stats.get("digg_count") or stats.get("like_count")),
        "comment_count": to_int(video.get("comment_count") or stats.get("comment_count")),
        "share_count": to_int(video.get("share_count") or stats.get("share_count")),
        "collect_count": to_int(video.get("collect_count") or stats.get("collect_count") or stats.get("favorite_count")),
        "play_count": to_int(video.get("play_count") or stats.get("play_count")),
        "derived_metrics": derived,
    }


def property_tags(metrics: dict[str, Any], *, genre: str = "") -> list[str]:
    tags: list[str] = []
    thresholds = baseline_thresholds(genre)
    for metric, tag in PROPERTY_TAG_RULES.items():
        value = metrics.get(metric)
        threshold = thresholds[metric]
        if isinstance(value, (int, float)) and value >= threshold:
            tags.append(tag)
    return tags


def metric_baseline_profile(metrics: dict[str, Any], *, genre: str = "") -> dict[str, Any]:
    thresholds = baseline_thresholds(genre)
    return {
        "genre": genre or "",
        "thresholds": thresholds,
        "deltas": {
            metric: round(metrics[metric] - threshold, 6)
            for metric, threshold in thresholds.items()
            if isinstance(metrics.get(metric), (int, float))
        },
        "tag_rules": PROPERTY_TAG_RULES,
    }


def derive_metrics(video: dict[str, Any], *, genre: str = "") -> dict[str, Any]:
    counts = extract_counts(video)
    like_count = counts["like_count"] or 0
    comment_count = counts["comment_count"] or 0
    share_count = counts["share_count"] or 0
    collect_count = counts["collect_count"] or 0
    play_count = counts["play_count"] or 0
    derived = counts["derived_metrics"] if isinstance(counts["derived_metrics"], dict) else {}
    metrics = {
        "like_count": like_count,
        "comment_count": comment_count,
        "share_count": share_count,
        "collect_count": collect_count,
        "play_count": play_count,
        "interaction_rate": derived.get("comment_like_ratio") if derived.get("comment_like_ratio") is not None else ratio(comment_count, like_count),
        "save_rate": derived.get("collect_like_ratio") if derived.get("collect_like_ratio") is not None else ratio(collect_count, like_count),
        "share_rate": derived.get("share_like_ratio") if derived.get("share_like_ratio") is not None else ratio(share_count, like_count),
        "engagement_score": derived.get("engagement_score") if derived.get("engagement_score") is not None else like_count + comment_count * 3 + share_count * 5 + collect_count * 4,
    }
    metrics["engagement_rate"] = derived.get("engagement_rate") if derived.get("engagement_rate") is not None else ratio(metrics["engagement_score"], play_count)
    metrics["property_tags"] = property_tags(metrics, genre=genre)
    metrics["baseline_profile"] = metric_baseline_profile(metrics, genre=genre)
    return metrics


def upsert_video(video: dict[str, Any], *, genre: str = "") -> dict[str, Any]:
    init_db()
    current = now()
    platform = detect_platform(video)
    source_id = normalize_video_source_id(video) or f"local-{current}"
    video_id = f"{platform}:{source_id}"
    publish_time = to_int(video.get("create_time") or video.get("publish_time"))
    publish = publish_parts(publish_time)
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO short_video_items (
                id, platform, source_id, source_url, author_id, author_name, title,
                description, genre, publish_time, publish_hour, publish_weekday,
                cover_url, video_url, local_video_path, raw_json, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(platform, source_id) DO UPDATE SET
                source_url = excluded.source_url,
                author_id = excluded.author_id,
                author_name = excluded.author_name,
                title = excluded.title,
                description = excluded.description,
                genre = COALESCE(NULLIF(excluded.genre, ''), short_video_items.genre),
                publish_time = excluded.publish_time,
                publish_hour = excluded.publish_hour,
                publish_weekday = excluded.publish_weekday,
                cover_url = excluded.cover_url,
                video_url = excluded.video_url,
                local_video_path = excluded.local_video_path,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
            """,
            (
                video_id,
                platform,
                source_id,
                first_text(video.get("share_url"), video.get("source_url"), video.get("url")),
                first_text(video.get("author_id"), (video.get("author") or {}).get("uid") if isinstance(video.get("author"), dict) else ""),
                first_text(video.get("author_name"), video.get("author") if isinstance(video.get("author"), str) else "", (video.get("author") or {}).get("nickname") if isinstance(video.get("author"), dict) else ""),
                first_text(video.get("title"), video.get("desc")),
                first_text(video.get("desc"), video.get("title")),
                genre or first_text(video.get("genre")),
                publish_time,
                publish["publish_hour"],
                publish["publish_weekday"],
                first_text(video.get("cover_url")),
                first_text(video.get("source_video_url"), video.get("video_url"), video.get("download_url"), video.get("play_url")),
                first_text(video.get("local_video_path"), video.get("video_path")),
                json.dumps(video, ensure_ascii=False),
                current,
                current,
            ),
        )
    return get_video(video_id) or {}


def save_metric_snapshot(video_id: str, video: dict[str, Any]) -> dict[str, Any]:
    init_db()
    current = now()
    saved_video = get_video(video_id)
    genre = first_text(video.get("genre"), saved_video.get("genre") if saved_video else "")
    metrics = derive_metrics(video, genre=genre)
    snapshot_id = f"{video_id}:{current}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO short_video_metric_snapshots (
                id, video_id, like_count, comment_count, share_count, collect_count,
                play_count, interaction_rate, save_rate, share_rate, engagement_score,
                engagement_rate, property_tags_json, raw_json, captured_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                snapshot_id,
                video_id,
                metrics["like_count"],
                metrics["comment_count"],
                metrics["share_count"],
                metrics["collect_count"],
                metrics["play_count"],
                metrics["interaction_rate"],
                metrics["save_rate"],
                metrics["share_rate"],
                metrics["engagement_score"],
                metrics["engagement_rate"],
                json.dumps(metrics["property_tags"], ensure_ascii=False),
                json.dumps(
                    {
                        "statistics": video.get("statistics") or {},
                        "baseline_profile": metrics["baseline_profile"],
                    },
                    ensure_ascii=False,
                ),
                current,
                current,
                current,
            ),
        )
    return get_metric_snapshot(snapshot_id) or {}


def infer_genre(video: dict[str, Any], result: dict[str, Any]) -> str:
    context = video.get("douyin_target_context") if isinstance(video.get("douyin_target_context"), dict) else {}
    for value in (
        video.get("genre"),
        result.get("genre"),
        (result.get("content_identity") or {}).get("track") if isinstance(result.get("content_identity"), dict) else "",
        context.get("genre"),
    ):
        if value:
            return str(value)
    return ""


def extract_markdown_report(result: dict[str, Any]) -> str:
    for key in ("final_markdown", "markdown_report", "report_markdown", "summary_markdown"):
        if isinstance(result.get(key), str):
            return str(result.get(key) or "")
    return ""


def model_summary(result: dict[str, Any]) -> str:
    runs = result.get("model_runs") if isinstance(result.get("model_runs"), list) else []
    if not runs:
        return ""
    labels = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        label = "/".join(str(part) for part in (run.get("provider"), run.get("model"), run.get("purpose")) if part)
        if label:
            labels.append(label)
    return "; ".join(labels[:12])


def save_analysis_run(
    *,
    task_id: str,
    video_id: str,
    video: dict[str, Any],
    result: dict[str, Any],
    provider: str = "",
    job_path: str = "",
) -> dict[str, Any]:
    init_db()
    current = now()
    result = validate_analysis_result(result if isinstance(result, dict) else {})
    run_id = task_id or f"run-{video_id}-{current}"
    genre = infer_genre(video, result)
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO short_video_analysis_runs (
                id, video_id, task_id, provider, model_summary, genre, status,
                evidence_path, job_path, result_json, markdown_report, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'done', %s, %s, %s, %s, %s, %s)
            ON CONFLICT(task_id) DO UPDATE SET
                video_id = excluded.video_id,
                provider = excluded.provider,
                model_summary = excluded.model_summary,
                genre = excluded.genre,
                status = excluded.status,
                evidence_path = excluded.evidence_path,
                job_path = excluded.job_path,
                result_json = excluded.result_json,
                markdown_report = excluded.markdown_report,
                updated_at = excluded.updated_at
            """,
            (
                run_id,
                video_id,
                task_id,
                provider,
                model_summary(result),
                genre,
                str(evidence.get("evidence_path") or ""),
                job_path,
                json.dumps(result, ensure_ascii=False),
                extract_markdown_report(result),
                current,
                current,
            ),
        )
    save_segments(run_id=run_id, video_id=video_id, result=result)
    save_formula(run_id=run_id, video_id=video_id, genre=genre, result=result)
    return get_analysis_run(run_id) or {}


def save_segments(*, run_id: str, video_id: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    init_db()
    current = now()
    segments = result.get("segment_breakdowns") if isinstance(result.get("segment_breakdowns"), list) else []
    saved_ids: list[str] = []
    with connect() as connection:
        for index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue
            segment_id = str(segment.get("segment_id") or f"seg_{index + 1:03d}")
            row_id = f"{run_id}:{segment_id}"
            saved_ids.append(row_id)
            connection.execute(
                """
                INSERT INTO short_video_analysis_segments (
                    id, run_id, video_id, segment_id, start_seconds, end_seconds,
                    time_range, transcript, visual_style, audio_pacing,
                    narrative_technique, retention_mechanism, raw_json, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(run_id, segment_id) DO UPDATE SET
                    start_seconds = excluded.start_seconds,
                    end_seconds = excluded.end_seconds,
                    time_range = excluded.time_range,
                    transcript = excluded.transcript,
                    visual_style = excluded.visual_style,
                    audio_pacing = excluded.audio_pacing,
                    narrative_technique = excluded.narrative_technique,
                    retention_mechanism = excluded.retention_mechanism,
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at
                """,
                (
                    row_id,
                    run_id,
                    video_id,
                    segment_id,
                    segment.get("start"),
                    segment.get("end"),
                    first_text(segment.get("time_range")),
                    first_text(segment.get("transcript")),
                    first_text(segment.get("visual_style"), segment.get("visual_signal")),
                    first_text(segment.get("audio_pacing"), segment.get("audio_rhythm")),
                    first_text(segment.get("narrative_technique"), segment.get("segment_role"), segment.get("copywriting_pattern")),
                    first_text(segment.get("retention_mechanism"), segment.get("hook"), segment.get("replicable_point")),
                    json.dumps(segment, ensure_ascii=False),
                    current,
                    current,
                ),
            )
    return [get_segment(row_id) for row_id in saved_ids if get_segment(row_id)]


def save_formula(*, run_id: str, video_id: str, genre: str, result: dict[str, Any]) -> dict[str, Any]:
    init_db()
    current = now()
    replication = result.get("replication_plan") if isinstance(result.get("replication_plan"), dict) else {}
    copywriting = result.get("copywriting_formula") if isinstance(result.get("copywriting_formula"), dict) else {}
    visual = result.get("visual_structure") if isinstance(result.get("visual_structure"), dict) else result.get("visual_blueprint") if isinstance(result.get("visual_blueprint"), dict) else {}
    risk = result.get("risk_control") if isinstance(result.get("risk_control"), dict) else {}
    formula_id = f"{run_id}:formula"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO short_video_formula_library (
                id, video_id, run_id, genre, formula_name, generic_formula, hook_template,
                script_template, cta_template, visual_blueprint_json, risk_json,
                raw_json, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(id) DO UPDATE SET
                genre = excluded.genre,
                formula_name = excluded.formula_name,
                generic_formula = excluded.generic_formula,
                hook_template = excluded.hook_template,
                script_template = excluded.script_template,
                cta_template = excluded.cta_template,
                visual_blueprint_json = excluded.visual_blueprint_json,
                risk_json = excluded.risk_json,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
            """,
            (
                formula_id,
                video_id,
                run_id,
                genre,
                first_text(replication.get("pattern_name"), result.get("pattern_name")),
                first_text(replication.get("reusable_formula"), result.get("viral_formula"), result.get("summary")),
                first_text((result.get("core_hook") or {}).get("opening_3s") if isinstance(result.get("core_hook"), dict) else "", copywriting.get("title_formula")),
                first_text(copywriting.get("script_formula"), result.get("standard_remake_template")),
                first_text(copywriting.get("cta")),
                json.dumps(visual, ensure_ascii=False),
                json.dumps(risk, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                current,
                current,
            ),
        )
    return get_formula(formula_id) or {}


def persist_analysis_result(
    *,
    task_id: str,
    video: dict[str, Any],
    result: dict[str, Any],
    provider: str = "",
    job_path: str = "",
) -> dict[str, Any]:
    genre = infer_genre(video, result)
    saved_video = upsert_video(video, genre=genre)
    metric = save_metric_snapshot(saved_video["id"], video)
    run = save_analysis_run(
        task_id=task_id,
        video_id=saved_video["id"],
        video=video,
        result=result,
        provider=provider,
        job_path=job_path,
    )
    return {"video": saved_video, "metric": metric, "analysis_run": run}


def get_video(video_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM short_video_items WHERE id = %s", (video_id,)).fetchone()
    return row_to_video(row) if row else None


def get_metric_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM short_video_metric_snapshots WHERE id = %s", (snapshot_id,)).fetchone()
    return row_to_metric(row) if row else None


def get_analysis_run(run_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM short_video_analysis_runs WHERE id = %s", (run_id,)).fetchone()
    return row_to_run(row) if row else None


def get_segment(segment_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM short_video_analysis_segments WHERE id = %s", (segment_id,)).fetchone()
    return row_to_segment(row) if row else None


def get_formula(formula_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT * FROM short_video_formula_library WHERE id = %s", (formula_id,)).fetchone()
    return row_to_formula(row) if row else None


def get_analysis_dataset(run_id: str) -> dict[str, Any] | None:
    run = get_analysis_run(run_id)
    if not run:
        return None
    with connect() as connection:
        video_row = connection.execute("SELECT * FROM short_video_items WHERE id = %s", (run["video_id"],)).fetchone()
        metric_rows = connection.execute(
            "SELECT * FROM short_video_metric_snapshots WHERE video_id = %s ORDER BY captured_at DESC LIMIT 20",
            (run["video_id"],),
        ).fetchall()
        segment_rows = connection.execute(
            "SELECT * FROM short_video_analysis_segments WHERE run_id = %s ORDER BY start_seconds ASC",
            (run_id,),
        ).fetchall()
        formula_row = connection.execute(
            "SELECT * FROM short_video_formula_library WHERE run_id = %s ORDER BY updated_at DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        export_rows = connection.execute(
            "SELECT * FROM short_video_remake_exports WHERE run_id = %s ORDER BY updated_at DESC LIMIT 20",
            (run_id,),
        ).fetchall()
    return {
        "run": run,
        "video": row_to_video(video_row) if video_row else None,
        "metrics": [row_to_metric(row) for row in metric_rows],
        "segments": [row_to_segment(row) for row in segment_rows],
        "formula": row_to_formula(formula_row) if formula_row else None,
        "remake_exports": [row_to_remake_export(row) for row in export_rows],
    }


def save_remake_export(
    *,
    run_id: str = "",
    task_id: str = "",
    title: str = "",
    genre: str = "",
    target_genre: str = "",
    markdown: str = "",
    source: dict[str, Any] | None = None,
    rewritten: dict[str, Any] | None = None,
    export_type: str = "remake_package",
    status: str = "saved",
) -> dict[str, Any]:
    init_db()
    current = now()
    run = get_analysis_run(run_id or task_id) if (run_id or task_id) else None
    resolved_run_id = run_id or task_id
    video_id = str((run or {}).get("video_id") or "")
    resolved_genre = genre or str((run or {}).get("genre") or "")
    export_id = f"remake-export-{resolved_run_id or 'manual'}-{current}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO short_video_remake_exports (
                id, run_id, video_id, task_id, title, genre, target_genre,
                export_type, markdown, source_json, rewritten_json, status,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                export_id,
                resolved_run_id,
                video_id,
                task_id or resolved_run_id,
                title,
                resolved_genre,
                target_genre,
                export_type,
                markdown,
                json.dumps(source or {}, ensure_ascii=False),
                json.dumps(rewritten or {}, ensure_ascii=False),
                status,
                current,
                current,
            ),
        )
        row = connection.execute("SELECT * FROM short_video_remake_exports WHERE id = %s", (export_id,)).fetchone()
    return row_to_remake_export(row) if row else {"id": export_id}


def list_remake_exports(*, run_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    limit = max(1, min(int(limit or 100), 500))
    with connect() as connection:
        if run_id:
            rows = connection.execute(
                "SELECT * FROM short_video_remake_exports WHERE run_id = %s ORDER BY updated_at DESC LIMIT %s",
                (run_id, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM short_video_remake_exports ORDER BY updated_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
    return [row_to_remake_export(row) for row in rows]
