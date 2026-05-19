import os
import gc
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import task_store
from backend.app import short_video_analysis_store
from backend.app import tiktok_target_store
from backend.app import video_analysis_queue
from backend.app.routes.douyin_target import delete_video_analysis
from backend.app.video_analysis_worker import coordinator


class AiVideoQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = task_store.DB_PATH
        self.old_analysis_db_path = short_video_analysis_store.DB_PATH
        self.old_target_db_path = tiktok_target_store.DB_PATH
        self.old_limit = os.environ.get("AI_VIDEO_MAX_CONCURRENT_TASKS")
        task_store.DB_PATH = Path(self.tmp.name) / "tasks.sqlite3"
        short_video_analysis_store.DB_PATH = Path(self.tmp.name) / "short_video_analysis.sqlite3"
        tiktok_target_store.DB_PATH = Path(self.tmp.name) / "tiktok_targeting.sqlite3"
        os.environ["AI_VIDEO_MAX_CONCURRENT_TASKS"] = "3"
        task_store.init_db()
        video_analysis_queue.init_ai_video_queue_db()
        short_video_analysis_store.init_db()
        tiktok_target_store.init_db()

    def tearDown(self):
        task_store.DB_PATH = self.old_db_path
        short_video_analysis_store.DB_PATH = self.old_analysis_db_path
        tiktok_target_store.DB_PATH = self.old_target_db_path
        if self.old_limit is None:
            os.environ.pop("AI_VIDEO_MAX_CONCURRENT_TASKS", None)
        else:
            os.environ["AI_VIDEO_MAX_CONCURRENT_TASKS"] = self.old_limit
        gc.collect()
        self.tmp.cleanup()

    def create_task_and_job(self, index: int):
        task_id = f"video-task-{index}"
        video = {"id": f"video-{index}", "desc": f"Video {index}", "source_video_url": f"https://example.com/{index}.mp4"}
        task_store.create_task(
            task_id=task_id,
            task_type="ai_video_analysis",
            title=f"Video {index}",
            provider="mock",
            payload={"video": video},
        )
        return video_analysis_queue.enqueue_ai_video_job(task_id=task_id, video=video, provider="mock")

    def test_claim_respects_global_limit_three(self):
        for index in range(5):
            self.create_task_and_job(index)

        claimed = [
            video_analysis_queue.claim_next_ai_video_job(f"worker-{index}")
            for index in range(4)
        ]

        self.assertEqual(len([job for job in claimed if job]), 3)
        self.assertIsNone(claimed[3])
        stats = video_analysis_queue.queue_stats()
        self.assertEqual(stats["max_concurrent"], 3)
        self.assertEqual(stats["active"], 3)
        self.assertEqual(stats["queued"], 2)

    def test_cancel_queued_job_marks_cancelled(self):
        self.create_task_and_job(1)

        job = video_analysis_queue.cancel_ai_video_job("video-task-1")

        self.assertEqual(job["status"], "cancelled")
        self.assertTrue(job["cancel_requested"])

    def test_retry_failed_job_requeues(self):
        self.create_task_and_job(1)
        video_analysis_queue.claim_next_ai_video_job("worker-1")
        failed = video_analysis_queue.fail_ai_video_job(
            "video-task-1",
            error_code="MODEL_TIMEOUT",
            error_message="timeout",
            retryable=False,
        )
        self.assertEqual(failed["status"], "failed_final")

        retried = video_analysis_queue.retry_ai_video_job("video-task-1")

        self.assertEqual(retried["status"], "queued")
        self.assertEqual(retried["attempts"], 0)
        self.assertFalse(retried["cancel_requested"])

    def test_delete_done_job_removes_queue_record_and_keeps_task_available(self):
        self.create_task_and_job(1)
        video_analysis_queue.complete_ai_video_job("video-task-1")

        deleted = video_analysis_queue.delete_ai_video_job("video-task-1")

        self.assertTrue(deleted["deleted"])
        self.assertIsNone(video_analysis_queue.get_ai_video_job("video-task-1"))
        self.assertIsNotNone(task_store.get_task("video-task-1"))

    def test_delete_active_job_is_blocked_by_default(self):
        self.create_task_and_job(1)
        video_analysis_queue.claim_next_ai_video_job("worker-1")

        deleted = video_analysis_queue.delete_ai_video_job("video-task-1")

        self.assertFalse(deleted["deleted"])
        self.assertTrue(deleted["delete_blocked"])
        self.assertIsNotNone(video_analysis_queue.get_ai_video_job("video-task-1"))

    def test_queue_snapshot_includes_backlog_and_workers(self):
        for index in range(4):
            self.create_task_and_job(index)
        video_analysis_queue.claim_next_ai_video_job("worker-1")

        snapshot = video_analysis_queue.queue_snapshot(backlog_limit=3)

        self.assertIn("workers", snapshot)
        self.assertIn("backlog", snapshot)
        self.assertIn("failed_recent", snapshot)
        self.assertIn("done_recent", snapshot)
        self.assertLessEqual(len(snapshot["backlog"]), 3)
        self.assertEqual(snapshot["max_concurrent"], 3)

    def test_queue_status_includes_worker_runtime_state(self):
        snapshot = video_analysis_queue.queue_snapshot(backlog_limit=2)
        self.assertIn("workers", snapshot)
        self.assertIn("backlog", snapshot)
        snapshot["worker_enabled"] = coordinator.enabled()
        snapshot["worker_started"] = coordinator.started
        snapshot["thread_count"] = len(coordinator.threads)

        self.assertIn("worker_enabled", snapshot)
        self.assertIn("worker_started", snapshot)
        self.assertIn("thread_count", snapshot)

    def test_failed_jobs_show_up_in_recent_snapshot(self):
        self.create_task_and_job(1)
        failed = video_analysis_queue.fail_ai_video_job(
            "video-task-1",
            error_code="MODEL_TIMEOUT",
            error_message="timeout",
            retryable=False,
        )

        snapshot = video_analysis_queue.queue_snapshot(backlog_limit=3)

        self.assertEqual(failed["status"], "failed_final")
        self.assertTrue(any(item["task_id"] == "video-task-1" for item in snapshot["failed_recent"]))

    def test_worker_completion_persists_generic_analysis_dataset(self):
        video = {
            "aweme_id": "worker-aweme-1",
            "desc": "Worker video",
            "digg_count": 100,
            "comment_count": 6,
            "share_count": 4,
            "collect_count": 10,
            "play_count": 1000,
            "genre": "knowledge",
        }
        task_store.create_task(
            task_id="video-task-worker",
            task_type="ai_video_analysis",
            title="Worker video",
            provider="mock",
            payload={"video": video},
        )
        job = video_analysis_queue.enqueue_ai_video_job(task_id="video-task-worker", video=video, provider="mock")

        coordinator.run_claimed_job("worker-test", job)

        task = task_store.get_task("video-task-worker")
        dataset = short_video_analysis_store.get_analysis_dataset("video-task-worker")
        self.assertEqual(task["status"], "done")
        self.assertIsNotNone(dataset)
        self.assertEqual(dataset["video"]["id"], "douyin:worker-aweme-1")
        self.assertGreaterEqual(len(dataset["metrics"]), 1)
        self.assertIn("high_interaction_or_controversy", dataset["metrics"][0]["property_tags"])

    def test_worker_completion_syncs_target_video_status(self):
        video = {
            "aweme_id": "target-aweme-1",
            "desc": "Target video",
            "digg_count": 100,
            "comment_count": 6,
            "share_count": 4,
            "collect_count": 10,
            "genre": "knowledge",
            "douyin_target_context": {"video_id": "target-aweme-1", "metrics": {"comment_like_ratio": 0.06}},
        }
        tiktok_target_store.create_target_video(
            "target-aweme-1",
            "user-1",
            {
                "aweme_id": "target-aweme-1",
                "desc": "Target video",
                "digg_count": 100,
                "comment_count": 6,
                "share_count": 4,
                "collect_count": 10,
                "selected": True,
                "genre": "knowledge",
            },
        )
        tiktok_target_store.create_target_task(
            "target-task-1",
            video_id="target-aweme-1",
            ai_task_id="video-task-target",
            status="pending",
        )
        task_store.create_task(
            task_id="video-task-target",
            task_type="ai_video_analysis",
            title="Target video",
            provider="mock",
            payload={"video": video, "douyin_target": video["douyin_target_context"]},
        )
        job = video_analysis_queue.enqueue_ai_video_job(task_id="video-task-target", video=video, provider="mock")

        coordinator.run_claimed_job("worker-test", job)

        target_video = tiktok_target_store.get_target_video("target-aweme-1")
        target_task = tiktok_target_store.get_target_task("target-task-1")
        self.assertEqual(target_video["analysis_status"], "done")
        self.assertEqual(target_task["status"], "done")
        self.assertTrue(target_video["analysis_result"])

    def test_delete_target_video_analysis_clears_task_and_preserves_comments(self):
        tiktok_target_store.create_target_video(
            "target-delete-aweme",
            "user-1",
            {
                "aweme_id": "target-delete-aweme",
                "desc": "Delete analysis only",
                "digg_count": 100,
                "comment_count": 2,
                "share_count": 1,
                "collect_count": 8,
                "selected": True,
            },
        )
        tiktok_target_store.replace_target_video_comments(
            "target-delete-aweme",
            [
                {
                    "cid": "c1",
                    "text": "\u592a\u771f\u5b9e\u4e86\uff0c\u8fd9\u5c31\u662f\u6211",
                    "digg_count": 12,
                    "user": {"uid": "fan-1", "nickname": "fan"},
                }
            ],
        )
        tiktok_target_store.create_target_task(
            "target-delete-task",
            video_id="target-delete-aweme",
            ai_task_id="video-delete-task",
            status="done",
        )
        task_store.create_task(
            task_id="video-delete-task",
            task_type="ai_video_analysis",
            title="Delete analysis only",
            provider="mock",
            payload={"video": {"aweme_id": "target-delete-aweme"}},
        )
        task_store.update_task("video-delete-task", status="done", result_json={"summary": "done"})
        video_analysis_queue.enqueue_ai_video_job(
            task_id="video-delete-task",
            video={"aweme_id": "target-delete-aweme"},
            provider="mock",
        )
        video_analysis_queue.complete_ai_video_job("video-delete-task")

        result = delete_video_analysis("target-delete-aweme", delete_archives=True)
        video = tiktok_target_store.get_target_video("target-delete-aweme")
        dataset = tiktok_target_store.get_target_video_interaction_dataset("target-delete-aweme")

        self.assertTrue(result["deleted"])
        self.assertEqual(video["analysis_status"], "none")
        self.assertEqual(video["analysis_task_id"], "")
        self.assertEqual(video["analysis_result"], {})
        self.assertIsNone(tiktok_target_store.get_target_task("target-delete-task"))
        self.assertIsNone(task_store.get_task("video-delete-task"))
        self.assertIsNone(video_analysis_queue.get_ai_video_job("video-delete-task"))
        self.assertEqual(dataset["comment_count"], 1)
        self.assertEqual(dataset["video"]["comment_snapshot_status"], "done")


if __name__ == "__main__":
    unittest.main()
