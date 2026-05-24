import gc
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import task_store
from backend.app import ai_video_analysis_runner
from backend.app.routes import ai_production_reverse, ai_prompt_reverse, ai_video_analysis, text_to_assets
from tests.postgres_test_utils import isolated_postgres_schema


class TaskRetryRouteTests(unittest.TestCase):
    def setUp(self):
        self.pg_schema = isolated_postgres_schema("task_retry_routes")
        self.pg_schema.__enter__()
        task_store.init_db()

    def tearDown(self):
        gc.collect()
        self.pg_schema.__exit__(None, None, None)

    def _failed_task(self, task_id: str, task_type: str, payload: dict):
        task_store.create_task(
            task_id=task_id,
            task_type=task_type,
            title=task_id,
            provider="mock",
            payload=payload,
        )
        return task_store.update_task(
            task_id,
            status="failed",
            progress=100,
            message="failed",
            result_json={"partial": True},
            error="boom",
        )

    def test_prompt_reverse_retry_resets_task_and_schedules_background_run(self):
        self._failed_task("prompt-retry", "ai_prompt_reverse", {"video": {"aweme_id": "video-1"}})
        background = BackgroundTasks()

        response = ai_prompt_reverse.retry_prompt_reverse_job("prompt-retry", background)

        self.assertEqual(response["task"]["status"], "pending")
        self.assertEqual(response["task"]["progress"], 0)
        self.assertIsNone(response["task"]["result"])
        self.assertIsNone(response["task"]["error"])
        self.assertEqual(len(background.tasks), 1)

    def test_production_reverse_retry_resets_task_and_schedules_background_run(self):
        self._failed_task("production-retry", "ai_production_reverse", {"video": {"aweme_id": "video-2"}})
        background = BackgroundTasks()

        response = ai_production_reverse.retry_production_reverse_job("production-retry", background)

        self.assertEqual(response["task"]["status"], "pending")
        self.assertEqual(response["task"]["progress"], 0)
        self.assertIsNone(response["task"]["result"])
        self.assertIsNone(response["task"]["error"])
        self.assertEqual(len(background.tasks), 1)

    def test_text_to_assets_retry_resets_task_and_schedules_background_run(self):
        self._failed_task("assets-retry", "text_to_assets", {"idea": "做一条拆解视频", "title": "素材", "provider": "mock"})
        background = BackgroundTasks()

        response = text_to_assets.retry_text_to_assets_job("assets-retry", background)

        self.assertEqual(response["task"]["status"], "pending")
        self.assertEqual(response["task"]["progress"], 0)
        self.assertIsNone(response["task"]["result"])
        self.assertIsNone(response["task"]["error"])
        self.assertEqual(len(background.tasks), 1)

    def test_ai_video_retry_restarts_running_task_and_clears_partial_result(self):
        task_store.create_task(
            task_id="analysis-restart",
            task_type="ai_video_analysis",
            title="analysis-restart",
            provider="mock",
            payload={"video": {"aweme_id": "video-3"}},
        )
        task_store.update_task(
            "analysis-restart",
            status="running",
            progress=42,
            message="stuck",
            result_json={"partial": True},
        )

        with (
            patch.object(ai_video_analysis, "retry_ai_video_job", return_value={"task_id": "analysis-restart"}),
            patch.object(ai_video_analysis, "queue_stats", return_value={"queued": 1}),
        ):
            response = ai_video_analysis.retry_job("analysis-restart")

        task = task_store.get_task("analysis-restart")
        self.assertEqual(response["status"], "ok")
        self.assertEqual(task["status"], "pending")
        self.assertEqual(task["progress"], 0)
        self.assertIsNone(task["result"])
        self.assertIsNone(task["error"])

    def test_ai_video_comment_retry_updates_active_task(self):
        task_store.create_task(
            task_id="analysis-comments-retry",
            task_type="ai_video_analysis",
            title="analysis-comments-retry",
            provider="mock",
            payload={
                "video": {"aweme_id": "video-4"},
                "comment_collection_state": {"status": "failed", "error": "comments failed"},
            },
        )
        task_store.update_task("analysis-comments-retry", status="running", progress=42, message="running")

        with patch.object(
            ai_video_analysis,
            "collect_comments_for_ai_task",
            return_value=(
                {"status": "done", "comment_saved_count": 3, "reply_saved_count": 1},
                {"aweme_id": "video-4"},
            ),
        ):
            response = ai_video_analysis.retry_job_comments("analysis-comments-retry")

        task = response["task"]
        self.assertEqual(task["status"], "running")
        self.assertEqual(task["payload"]["comment_collection_state"]["status"], "done")
        self.assertEqual(task["result"]["comment_collection"]["status"], "done")

    def test_ai_video_runner_keeps_comment_retry_success(self):
        task_store.create_task(
            task_id="analysis-comments-runner",
            task_type="ai_video_analysis",
            title="analysis-comments-runner",
            provider="mock",
            payload={"video": {"aweme_id": "video-5"}},
        )

        class Adapter:
            def create_job(self, *, job_id: str, **_kwargs):
                task_store.update_task(
                    job_id,
                    payload_json={
                        "video": {"aweme_id": "video-5"},
                        "comment_collection_state": {"status": "done", "comment_saved_count": 4},
                    },
                )
                return {"status": "running", "provider": "mock", "result": {"summary": "partial"}}

        with (
            patch.object(
                ai_video_analysis_runner,
                "collect_comments_for_ai_task",
                return_value=(
                    {"status": "failed", "error": "first comment request failed"},
                    {"aweme_id": "video-5"},
                ),
            ),
            patch.object(ai_video_analysis_runner, "list_ai_model_runs", return_value=[]),
        ):
            result = ai_video_analysis_runner.AiVideoAnalysisRunner(adapter_factory=Adapter).run(
                task_id="analysis-comments-runner",
                video={"aweme_id": "video-5"},
                provider="mock",
            )

        task = task_store.get_task("analysis-comments-runner")
        self.assertEqual(result.result["comment_collection"]["status"], "done")
        self.assertEqual(task["result"]["comment_collection"]["status"], "done")


if __name__ == "__main__":
    unittest.main()
