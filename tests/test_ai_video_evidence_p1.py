import os
import tempfile
import unittest
from pathlib import Path

from backend.app import task_store
from backend.app.video_analysis_queue import init_ai_video_queue_db, list_ai_model_runs, record_ai_model_run
from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline


class AiVideoEvidenceP1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = task_store.DB_PATH
        self.old_env = {
            key: os.environ.get(key)
            for key in [
                "AI_VIDEO_MIN_CHUNK_SECONDS",
                "AI_VIDEO_TARGET_CHUNK_SECONDS",
                "AI_VIDEO_MAX_CHUNK_SECONDS",
                "AI_VIDEO_CHUNK_OVERLAP_SECONDS",
                "AI_VIDEO_CHUNK_PAUSE_TOLERANCE_SECONDS",
                "AI_VIDEO_CHUNK_PAUSE_BONUS_SECONDS",
                "AI_VIDEO_FRAME_MAX_PER_CHUNK",
                "AI_VIDEO_FRAME_MIN_INTERVAL_SECONDS",
                "AI_VIDEO_FRAME_EXTRACT_MODE",
            ]
        }
        task_store.DB_PATH = Path(self.tmp.name) / "tasks.sqlite3"
        task_store.init_db()
        init_ai_video_queue_db()

    def tearDown(self):
        task_store.DB_PATH = self.old_db_path
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def pipeline(self) -> VideoEvidencePipeline:
        return VideoEvidencePipeline(output_dir=Path(self.tmp.name))

    def test_dynamic_chunking_uses_overlap(self):
        os.environ["AI_VIDEO_MIN_CHUNK_SECONDS"] = "5"
        os.environ["AI_VIDEO_TARGET_CHUNK_SECONDS"] = "10"
        os.environ["AI_VIDEO_MAX_CHUNK_SECONDS"] = "15"
        os.environ["AI_VIDEO_CHUNK_OVERLAP_SECONDS"] = "3"
        pipe = self.pipeline()
        segments = [
            {"start": index * 2, "end": index * 2 + 2, "text": f"s{index}"}
            for index in range(10)
        ]

        chunks = pipe.chunk_transcript(segments, duration=20)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("s4", chunks[0]["transcript"])
        self.assertIn("s4", chunks[1]["transcript"])
        self.assertLessEqual(chunks[0]["end"] - chunks[0]["start"], 15)

    def test_dynamic_chunking_prefers_nearby_pause_point(self):
        os.environ["AI_VIDEO_MIN_CHUNK_SECONDS"] = "5"
        os.environ["AI_VIDEO_TARGET_CHUNK_SECONDS"] = "10"
        os.environ["AI_VIDEO_MAX_CHUNK_SECONDS"] = "20"
        os.environ["AI_VIDEO_CHUNK_OVERLAP_SECONDS"] = "0"
        os.environ["AI_VIDEO_CHUNK_PAUSE_TOLERANCE_SECONDS"] = "1.5"
        pipe = self.pipeline()
        segments = [
            {"start": 0, "end": 4, "text": "a"},
            {"start": 4, "end": 8, "text": "b"},
            {"start": 8, "end": 12, "text": "c"},
            {"start": 12, "end": 16, "text": "d"},
        ]
        pause_points = [{"start": 7.8, "end": 8.2, "duration": 0.4, "reason": "word_gap"}]

        chunks = pipe.chunk_transcript(segments, duration=16, pause_points=pause_points)

        self.assertEqual(chunks[0]["end"], 8)
        self.assertEqual(chunks[0]["cut_reason"], "pause_point")
        self.assertEqual(chunks[1]["start"], 8)

    def test_frame_candidate_merge_prefers_chunk_start(self):
        os.environ["AI_VIDEO_FRAME_MIN_INTERVAL_SECONDS"] = "1"
        pipe = self.pipeline()
        merged = pipe.merge_frame_candidates(
            [
                {"time": 10.0, "source": "fallback"},
                {"time": 10.4, "source": "scene"},
                {"time": 10.2, "source": "chunk_start"},
                {"time": 15.0, "source": "fallback"},
            ]
        )

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["source"], "chunk_start")
        self.assertEqual(merged[1]["source"], "fallback")

    def test_parse_mpdecimate_showinfo_times(self):
        pipe = self.pipeline()
        output = """
        [Parsed_showinfo_2 @ 000001] n:   0 pts:      0 pts_time:0       pos: 1
        [Parsed_showinfo_2 @ 000001] n:   1 pts:  20480 pts_time:1.28    pos: 2
        [Parsed_showinfo_2 @ 000001] n:   2 pts:  40960 pts_time:2.56    pos: 3
        """

        candidates = pipe.parse_showinfo_times(output, duration=3, source="mpdecimate")

        self.assertEqual(
            candidates,
            [
                {"time": 1.28, "source": "mpdecimate", "scene_score": None},
                {"time": 2.56, "source": "mpdecimate", "scene_score": None},
            ],
        )

    def test_segment_frame_selection_prioritizes_scene_and_chunk_start(self):
        os.environ["AI_VIDEO_FRAME_MAX_PER_CHUNK"] = "3"
        pipe = self.pipeline()
        frames = [
            {"time": 1, "source": "fallback"},
            {"time": 2, "source": "scene"},
            {"time": 3, "source": "fallback"},
            {"time": 4, "source": "chunk_start"},
            {"time": 5, "source": "scene"},
        ]

        selected = pipe.select_segment_frames(frames)

        self.assertEqual([frame["source"] for frame in selected], ["scene", "chunk_start", "scene"])
        self.assertEqual([frame["time"] for frame in selected], [2, 4, 5])

    def test_record_model_run_persists(self):
        record_ai_model_run(
            task_id="task-1",
            provider="yunwu",
            model="gemini-2.5flash",
            purpose="segment_breakdown",
            chunk_id="seg_001",
            latency_ms=123,
            meta={"action": "segment breakdown"},
        )

        runs = list_ai_model_runs("task-1")

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["model"], "gemini-2.5flash")
        self.assertEqual(runs[0]["purpose"], "segment_breakdown")
        self.assertEqual(runs[0]["latency_ms"], 123)
        self.assertEqual(runs[0]["meta"]["action"], "segment breakdown")


if __name__ == "__main__":
    unittest.main()
