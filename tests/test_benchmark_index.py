import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import benchmark_index
from backend.app.benchmark_config import save_metric_config


class BenchmarkIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.jobs = self.base / "ai_video_analysis" / "jobs"
        self.jobs.mkdir(parents=True)
        self.index = self.base / "benchmark_index"
        self.old_env = {
            "BENCHMARK_AI_VIDEO_DIR": os.environ.get("BENCHMARK_AI_VIDEO_DIR"),
            "BENCHMARK_INDEX_DIR": os.environ.get("BENCHMARK_INDEX_DIR"),
        }
        os.environ["BENCHMARK_AI_VIDEO_DIR"] = str(self.base / "ai_video_analysis")
        os.environ["BENCHMARK_INDEX_DIR"] = str(self.index)

    def tearDown(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def write_job(self, name, aweme_id, author_name, digg=100, collect=20, comment=10, share=5, updated=1000, top_comments=None):
        path = self.jobs / name
        payload = {
            "job_id": path.stem,
            "status": "done",
            "video": {
                "aweme_id": aweme_id,
                "desc": "刷到就是私占 #塔罗",
                "create_time": 1716076800,
                "author": {
                    "sec_uid": f"sec-{author_name}",
                    "nickname": author_name,
                    "follower_count": 1000,
                    "total_favorited": 5000,
                    "aweme_count": 12,
                },
                "digg_count": digg,
                "comment_count": comment,
                "collect_count": collect,
                "share_count": share,
                "douyin_target_context": {
                    "interaction_snapshot": {
                        "comment_saved_count": len(top_comments or []),
                        "author_replies": [],
                        "top_comments": top_comments or [],
                    }
                },
            },
            "result": {
                "genre": "玄学/塔罗",
                "summary": "demo",
                "content_identity": {"track": "玄学/塔罗"},
                "core_hook": {"opening_3s": "刷到即有缘"},
                "psychology_breakdown": {"replicable_point": "私占感"},
                "viral_scores": {
                    "viral_potential": 80,
                    "imitation_value": 90,
                    "commerce_value": 70,
                    "comment_potential": 85,
                    "overall": 88,
                },
                "segment_breakdowns": [{"segment_id": "seg_001"}],
                "risk_control": {"risk_level": "中"},
                "evidence": {"evidence_path": "G:/tmp/evidence.json"},
            },
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.utime(path, (updated, updated))

    def test_rebuild_index_deduplicates_videos_and_builds_author_pattern(self):
        self.write_job("target-breakdown-a-1.json", "video-1", "微安塔罗", digg=100, collect=30, updated=1000)
        self.write_job("target-breakdown-a-2.json", "video-1", "微安塔罗", digg=120, collect=40, updated=2000)
        self.write_job("target-breakdown-b-1.json", "video-2", "彼得塔罗", digg=50, collect=5, updated=1500)

        meta = benchmark_index.rebuild_index("full")
        dataset = benchmark_index.load_index()

        self.assertEqual(meta["processed_jobs"], 3)
        self.assertEqual(meta["unique_videos"], 2)
        self.assertEqual(meta["authors"], 2)
        self.assertEqual(dataset["overview"]["unique_video_count"], 2)
        self.assertEqual(dataset["overview"]["author_count"], 2)
        video = next(item for item in dataset["videos"] if item["video_id"] == "video-1")
        self.assertEqual(video["digg_count"], 120)
        self.assertEqual(len(video["job_ids"]), 2)
        self.assertEqual(video["task_id"], video["job_id"])
        self.assertEqual(dataset["patterns"][0]["pattern_id"], "private-reading")

    def test_filtered_items_and_page(self):
        self.write_job("target-breakdown-a-1.json", "video-1", "微安塔罗")
        benchmark_index.rebuild_index("full")
        dataset = benchmark_index.load_index()

        filtered = benchmark_index.filtered_items(dataset["videos"], genre="玄学塔罗", q="微安")
        page = benchmark_index.page(filtered, limit=1, offset=0)

        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["author_name"], "微安塔罗")

    def test_metric_config_rebuilds_public_engagement_scores(self):
        self.write_job(
            "target-breakdown-a-1.json",
            "video-1",
            "微安塔罗",
            digg=100,
            collect=10,
            comment=0,
            share=0,
        )
        save_metric_config({"digg": 1, "comment": 1, "collect": 10, "share": 1})
        meta = benchmark_index.rebuild_index("full")
        dataset = benchmark_index.load_index()
        video = dataset["videos"][0]

        self.assertEqual(video["public_engagement_score"], 200)
        self.assertEqual(meta["public_engagement_weights"]["collect"], 10)

        save_metric_config({"digg": 1, "comment": 1, "collect": 1, "share": 1})
        meta = benchmark_index.rebuild_index("incremental")
        dataset = benchmark_index.load_index()
        video = dataset["videos"][0]

        self.assertEqual(meta["mode"], "full")
        self.assertEqual(meta["requested_mode"], "incremental")
        self.assertEqual(video["public_engagement_score"], 110)

    def test_comment_quality_is_public_competitor_signal(self):
        self.write_job(
            "target-breakdown-a-1.json",
            "video-1",
            "微安塔罗",
            digg=100,
            collect=60,
            comment=30,
            share=10,
            top_comments=[
                {"text": "这个开头真的很有代入感，我会收藏反复看，后面再研究结构", "digg_count": 20},
                {"text": "想问这个牌阵适合新手吗", "digg_count": 10},
                {"text": "我也遇到类似情况", "digg_count": 5},
                {"text": "收藏了，下次再看", "digg_count": 4},
                {"text": "这个问题讲清楚了", "digg_count": 3},
            ],
        )

        benchmark_index.rebuild_index("full")
        dataset = benchmark_index.load_index()
        video = dataset["videos"][0]

        self.assertEqual(video["comment_quality"]["status"], "ready")
        self.assertNotIn("health_rating", video)
        self.assertEqual(dataset["overview"]["public_signal_video_count"], 1)
        self.assertEqual(dataset["overview"]["comment_quality_video_count"], 1)
        self.assertEqual(dataset["overview"]["evaluation_scope"], "public_competitor_only")


if __name__ == "__main__":
    unittest.main()
