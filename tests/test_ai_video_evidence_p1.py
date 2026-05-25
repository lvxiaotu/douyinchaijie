import os
import tempfile
import unittest
from pathlib import Path

from backend.app import task_store
from backend.app.video_analysis_queue import (
    AiVideoTaskCancelled,
    cancel_ai_video_job,
    delete_ai_video_job,
    enqueue_ai_video_job,
    init_ai_video_queue_db,
    list_ai_model_runs,
    list_ai_video_artifacts,
    list_ai_video_chunks,
    queue_snapshot,
    record_ai_model_run,
    record_ai_video_artifact,
    raise_if_ai_video_cancelled,
    upsert_ai_video_chunk,
)
from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline
from tests.postgres_test_utils import isolated_postgres_schema


class AiVideoEvidenceP1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pg_schema = isolated_postgres_schema("ai_video_evidence")
        self.pg_schema.__enter__()
        self.addCleanup(self.pg_schema.__exit__, None, None, None)
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
        task_store.init_db()
        init_ai_video_queue_db()

    def tearDown(self):
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

    def test_video_url_candidates_prefer_nested_play_urls(self):
        pipe = self.pipeline()
        urls = pipe.video_url_candidates(
            {
                "download_url": "https://download.example/video.mp4",
                "raw": {
                    "video": {
                        "play_addr": {
                            "url_list": [
                                "https://play.example/first.mp4",
                                "https://play.example/second.mp4",
                            ]
                        },
                        "download_addr": {"url_list": ["https://raw-download.example/video.mp4"]},
                    }
                },
            }
        )

        self.assertEqual(urls[0], "https://play.example/first.mp4")
        self.assertIn("https://play.example/first.mp4", urls)
        self.assertIn("https://play.example/second.mp4", urls)
        self.assertGreater(urls.index("https://download.example/video.mp4"), urls.index("https://play.example/first.mp4"))

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

    def test_artifacts_and_chunks_round_trip_in_queue_snapshot(self):
        artifact_path = Path(self.tmp.name) / "artifact.json"
        artifact_path.write_text('{"ok": true}', encoding="utf-8")

        record_ai_video_artifact(
            task_id="task-1",
            type="evidence_json",
            uri=str(artifact_path),
            meta={"schema_version": "2.0"},
        )
        upsert_ai_video_chunk(
            task_id="task-1",
            chunk_index=1,
            start_time=0,
            end_time=12.5,
            status="running",
            transcript="hello",
            frame_count=2,
            grid_uri="grid.jpg",
            increment_attempts=True,
            meta={"segment_id": "seg_001"},
        )
        upsert_ai_video_chunk(
            task_id="task-1",
            chunk_index=1,
            status="done",
            vision_result_uri="segment.json",
            meta={"segment_role": "hook"},
        )

        artifacts = list_ai_video_artifacts("task-1")
        chunks = list_ai_video_chunks("task-1")
        snapshot = queue_snapshot(task_id="task-1")

        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["type"], "evidence_json")
        self.assertGreater(artifacts[0]["size_bytes"], 0)
        self.assertEqual(chunks[0]["status"], "done")
        self.assertEqual(chunks[0]["attempts"], 1)
        self.assertEqual(chunks[0]["vision_result_uri"], "segment.json")
        self.assertEqual(chunks[0]["meta"]["segment_role"], "hook")
        self.assertEqual(snapshot["artifacts"][0]["type"], "evidence_json")
        self.assertEqual(snapshot["chunks"][0]["status"], "done")

    def test_delete_job_clears_artifacts_and_chunks(self):
        video = {"id": "v1", "desc": "video"}
        task_store.create_task(
            task_id="task-delete",
            task_type="ai_video_analysis",
            title="video",
            provider="mock",
            payload={"video": video},
        )
        enqueue_ai_video_job(task_id="task-delete", video=video, provider="mock")
        record_ai_video_artifact(task_id="task-delete", type="evidence_json", uri="evidence.json")
        upsert_ai_video_chunk(task_id="task-delete", chunk_index=1, status="done")

        deleted = delete_ai_video_job("task-delete")

        self.assertTrue(deleted["deleted"])
        self.assertEqual(list_ai_video_artifacts("task-delete"), [])
        self.assertEqual(list_ai_video_chunks("task-delete"), [])

    def test_cancel_check_raises_special_exception(self):
        video = {"id": "v1", "desc": "video"}
        task_store.create_task(
            task_id="task-cancel",
            task_type="ai_video_analysis",
            title="video",
            provider="mock",
            payload={"video": video},
        )
        enqueue_ai_video_job(task_id="task-cancel", video=video, provider="mock")
        cancel_ai_video_job("task-cancel")

        with self.assertRaises(AiVideoTaskCancelled):
            raise_if_ai_video_cancelled("task-cancel")


if __name__ == "__main__":
    unittest.main()
