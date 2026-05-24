from __future__ import annotations

from collections import Counter
from typing import Any

from .benchmark_metrics import normalize_score, number

QUESTION_MARKERS = ["?", "？", "吗", "么", "怎么", "如何", "求", "想问", "在哪", "哪里"]
LOW_VALUE_TEXTS = {"1", "11", "111", "蹲", "来了", "哈哈", "哈哈哈", "666", "。", "."}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def extract_comment_snapshot(job: dict[str, Any]) -> dict[str, Any]:
    video = job.get("video") if isinstance(job.get("video"), dict) else {}
    context = video.get("douyin_target_context") if isinstance(video.get("douyin_target_context"), dict) else {}
    snapshot = context.get("interaction_snapshot") if isinstance(context.get("interaction_snapshot"), dict) else {}
    return snapshot if isinstance(snapshot, dict) else {}


def _is_valid_comment(text: str) -> bool:
    compact = text.strip()
    if len(compact) < 5:
        return False
    if compact in LOW_VALUE_TEXTS:
        return False
    return any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in compact)


def analyze_comments(snapshot: dict[str, Any]) -> dict[str, Any]:
    comments = snapshot.get("top_comments") if isinstance(snapshot.get("top_comments"), list) else []
    texts = [_text(comment.get("text")) for comment in comments if isinstance(comment, dict) and _text(comment.get("text"))]
    total = len(texts)
    if total <= 0:
        return {
            "status": "missing",
            "score": 0,
            "analyzed_comment_count": 0,
            "saved_comment_count": int(number(snapshot.get("comment_saved_count"))),
            "valid_comment_ratio": 0,
            "long_comment_ratio": 0,
            "question_ratio": 0,
            "duplicate_ratio": 0,
            "brush_risk": False,
            "examples": [],
        }

    counts = Counter(texts)
    valid_count = sum(1 for text in texts if _is_valid_comment(text))
    long_count = sum(1 for text in texts if len(text) >= 20)
    question_count = sum(1 for text in texts if any(marker in text for marker in QUESTION_MARKERS))
    duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
    valid_ratio = valid_count / total
    long_ratio = long_count / total
    question_ratio = question_count / total
    duplicate_ratio = duplicate_count / total
    author_reply_count = len(snapshot.get("author_replies") or [])
    brush_risk = duplicate_ratio >= 0.25 or valid_ratio < 0.35
    score = normalize_score(
        valid_ratio * 35
        + long_ratio * 25
        + min(question_ratio * 100, 15)
        + min(author_reply_count * 4, 10)
        + (1 - duplicate_ratio) * 15
        - (20 if brush_risk else 0)
    )
    examples = sorted(
        [
            {
                "text": _text(comment.get("text")),
                "digg_count": int(number(comment.get("digg_count"))),
                "reply_count": int(number(comment.get("reply_count"))),
            }
            for comment in comments
            if isinstance(comment, dict) and _text(comment.get("text"))
        ],
        key=lambda item: item["digg_count"],
        reverse=True,
    )[:5]

    return {
        "status": "ready",
        "score": score,
        "analyzed_comment_count": total,
        "saved_comment_count": int(number(snapshot.get("comment_saved_count"))),
        "valid_comment_ratio": round(valid_ratio, 6),
        "long_comment_ratio": round(long_ratio, 6),
        "question_ratio": round(question_ratio, 6),
        "duplicate_ratio": round(duplicate_ratio, 6),
        "author_reply_count": author_reply_count,
        "brush_risk": brush_risk,
        "examples": examples,
    }


def _average(values: list[Any]) -> float:
    cleaned = [number(value) for value in values if value not in (None, "")]
    return round(sum(cleaned) / len(cleaned), 6) if cleaned else 0


def build_comment_insights(videos: list[dict[str, Any]]) -> dict[str, Any]:
    ready: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for video in videos:
        quality = video.get("comment_quality") if isinstance(video.get("comment_quality"), dict) else {}
        if quality.get("status") == "ready":
            ready.append((video, quality))

    examples: list[dict[str, Any]] = []
    for video, quality in ready:
        for comment in quality.get("examples") or []:
            if not isinstance(comment, dict):
                continue
            examples.append(
                {
                    "text": _text(comment.get("text")),
                    "digg_count": int(number(comment.get("digg_count"))),
                    "reply_count": int(number(comment.get("reply_count"))),
                    "video_id": video.get("video_id") or "",
                    "video_desc": video.get("desc") or "",
                    "author_name": video.get("author_name") or "未知博主",
                    "quality_score": quality.get("score") or 0,
                }
            )
    examples = sorted(examples, key=lambda item: (item["digg_count"], item["reply_count"]), reverse=True)[:8]

    avg_score = _average([quality.get("score") for _, quality in ready])
    valid_ratio = _average([quality.get("valid_comment_ratio") for _, quality in ready])
    long_ratio = _average([quality.get("long_comment_ratio") for _, quality in ready])
    question_ratio = _average([quality.get("question_ratio") for _, quality in ready])
    duplicate_ratio = _average([quality.get("duplicate_ratio") for _, quality in ready])
    brush_risk_count = sum(1 for _, quality in ready if quality.get("brush_risk"))
    author_reply_count = sum(int(number(quality.get("author_reply_count"))) for _, quality in ready)
    analyzed_count = sum(int(number(quality.get("analyzed_comment_count"))) for _, quality in ready)
    saved_count = sum(int(number(quality.get("saved_comment_count"))) for _, quality in ready)

    topic_counter: Counter[str] = Counter()
    for item in examples:
        text = item["text"]
        for marker in ["收藏", "私信", "求", "想问", "准", "新手", "复合", "正缘", "守护", "牌阵", "教程"]:
            if marker in text:
                topic_counter[marker] += 1

    suggestions = []
    if question_ratio >= 0.18:
        suggestions.append("评论区已有提问氛围，适合复刻开放式提问和答疑型置顶评论。")
    else:
        suggestions.append("提问占比偏低，可在口播或置顶评论里预埋更具体的问题。")
    if long_ratio >= 0.18:
        suggestions.append("长评占比较好，说明话题能承接真实经历和情绪表达。")
    else:
        suggestions.append("长评不足，建议把标题/开头从泛情绪改成更具体的场景冲突。")
    if brush_risk_count:
        suggestions.append("部分样本存在低质或重复评论，复刻时不要把刷屏式口令当成有效互动。")
    if avg_score >= 70:
        suggestions.append("评论质量整体较高，可优先拆这些视频的评论区问题和博主回复。")

    return {
        "video_count": len(videos),
        "ready_video_count": len(ready),
        "coverage_ratio": round(len(ready) / len(videos), 6) if videos else 0,
        "avg_quality_score": avg_score,
        "valid_comment_ratio": valid_ratio,
        "long_comment_ratio": long_ratio,
        "question_ratio": question_ratio,
        "duplicate_ratio": duplicate_ratio,
        "brush_risk_video_count": brush_risk_count,
        "author_reply_count": author_reply_count,
        "analyzed_comment_count": analyzed_count,
        "saved_comment_count": saved_count,
        "top_topics": [{"name": name, "count": count} for name, count in topic_counter.most_common(8)],
        "examples": examples,
        "suggestions": suggestions[:4],
    }
