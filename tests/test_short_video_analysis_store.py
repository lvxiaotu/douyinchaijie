import gc
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import short_video_analysis_store as store
from tests.postgres_test_utils import isolated_postgres_schema


class ShortVideoAnalysisStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pg_schema = isolated_postgres_schema("short_video_analysis")
        self.pg_schema.__enter__()
        self.addCleanup(self.pg_schema.__exit__, None, None, None)
        self.old_env = {
            "SHORT_VIDEO_BASELINE_INTERACTION_RATE": os.environ.get("SHORT_VIDEO_BASELINE_INTERACTION_RATE"),
            "SHORT_VIDEO_BASELINE_KNOWLEDGE_INTERACTION_RATE": os.environ.get("SHORT_VIDEO_BASELINE_KNOWLEDGE_INTERACTION_RATE"),
        }
        os.environ.pop("SHORT_VIDEO_BASELINE_INTERACTION_RATE", None)
        os.environ.pop("SHORT_VIDEO_BASELINE_KNOWLEDGE_INTERACTION_RATE", None)
        store.init_db()

    def tearDown(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        gc.collect()
        self.tmp.cleanup()

    def test_persist_analysis_result_saves_video_metrics_segments_and_formula(self):
        video = {
            "aweme_id": "aweme-100",
            "desc": "demo video",
            "create_time": 1716076800,
            "digg_count": 100,
            "comment_count": 8,
            "share_count": 4,
            "collect_count": 12,
            "play_count": 1000,
            "cover_url": "https://example.test/cover.jpg",
            "source_video_url": "https://example.test/video.mp4",
            "genre": "knowledge",
        }
        result = {
            "summary": "generic formula",
            "genre": "knowledge",
            "content_identity": {"track": "knowledge"},
            "core_hook": {"opening_3s": "hook template"},
            "copywriting_formula": {
                "script_formula": "[question] + [proof] + [summary]",
                "cta": "save this",
            },
            "visual_structure": {"shot_structure": "talking head + b-roll"},
            "replication_plan": {
                "pattern_name": "question proof summary",
                "reusable_formula": "[反常识问题] + [论证] + [避坑总结]",
            },
            "risk_control": {"risk_level": "low"},
            "segment_breakdowns": [
                {
                    "segment_id": "seg_001",
                    "start": 0,
                    "end": 12,
                    "time_range": "00:00-00:12",
                    "transcript": "segment text",
                    "visual_style": "close-up",
                    "audio_pacing": "fast",
                    "narrative_technique": "question",
                    "retention_mechanism": "curiosity",
                }
            ],
            "evidence": {"evidence_path": "G:/tmp/evidence.json"},
        }

        saved = store.persist_analysis_result(
            task_id="task-100",
            video=video,
            result=result,
            provider="deepseek",
            job_path="G:/tmp/job.json",
        )
        dataset = store.get_analysis_dataset("task-100")

        self.assertEqual(saved["video"]["id"], "douyin:aweme-100")
        self.assertIsNotNone(dataset)
        self.assertEqual(dataset["video"]["genre"], "knowledge")
        self.assertEqual(dataset["metrics"][0]["interaction_rate"], 0.08)
        self.assertIn("high_interaction_or_controversy", dataset["metrics"][0]["property_tags"])
        self.assertIn("high_value_or_save_worthy", dataset["metrics"][0]["property_tags"])
        self.assertIn("high_resonance_or_shareable", dataset["metrics"][0]["property_tags"])
        self.assertEqual(dataset["segments"][0]["visual_style"], "close-up")
        self.assertEqual(dataset["formula"]["formula_name"], "question proof summary")
        self.assertEqual(dataset["formula"]["script_template"], "[question] + [proof] + [summary]")

    def test_property_tags_use_configurable_genre_baselines(self):
        os.environ["SHORT_VIDEO_BASELINE_KNOWLEDGE_INTERACTION_RATE"] = "0.10"

        metrics = store.derive_metrics(
            {
                "digg_count": 100,
                "comment_count": 8,
                "share_count": 4,
                "collect_count": 12,
                "play_count": 1000,
            },
            genre="knowledge",
        )

        self.assertNotIn("high_interaction_or_controversy", metrics["property_tags"])
        self.assertIn("high_value_or_save_worthy", metrics["property_tags"])
        self.assertEqual(metrics["baseline_profile"]["thresholds"]["interaction_rate"], 0.10)

    def test_save_remake_export_is_searchable_by_run(self):
        video = {
            "aweme_id": "aweme-200",
            "desc": "demo video",
            "digg_count": 100,
            "comment_count": 8,
            "share_count": 4,
            "collect_count": 12,
            "genre": "knowledge",
        }
        store.persist_analysis_result(
            task_id="task-200",
            video=video,
            result={"summary": "formula", "genre": "knowledge"},
            provider="deepseek",
        )

        export = store.save_remake_export(
            run_id="task-200",
            task_id="task-200",
            title="demo export",
            genre="knowledge",
            target_genre="beauty",
            markdown="# export",
            source={"summary": "formula"},
            rewritten={"script": "rewritten script"},
            export_type="cross_genre_rewrite",
            status="rewritten",
        )
        dataset = store.get_analysis_dataset("task-200")
        exports = store.list_remake_exports(run_id="task-200")

        self.assertEqual(export["target_genre"], "beauty")
        self.assertEqual(export["rewritten"]["script"], "rewritten script")
        self.assertEqual(dataset["remake_exports"][0]["id"], export["id"])
        self.assertEqual(exports[0]["export_type"], "cross_genre_rewrite")


if __name__ == "__main__":
    unittest.main()
