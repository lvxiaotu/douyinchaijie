import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from integrations.ai_video_analysis.audio_publication import AudioPublisher, TosAudioPublisher
from integrations.ai_video_analysis.doubao_asr import (
    DoubaoAsrConfig,
    DoubaoFileAsrClient,
    DoubaoFileAsrTranscriber,
    doubao_asr_status,
    validate_doubao_asr_environment,
)
from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline
from integrations.ai_video_analysis.http_policy import get_with_retries
from backend.app import short_video_analysis_store
from backend.app.routes.ai_video_analysis import RemakeExportPayload, save_remake_export_route
from tests.postgres_test_utils import isolated_postgres_schema


class FakeAsrResponse:
    def __init__(self, *, headers=None, payload=None, status_code=200):
        self.headers = headers or {}
        self._payload = payload or {}
        self.status_code = status_code
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeAsrSession:
    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeAsrResponse(
            headers={"X-Api-Status-Code": "20000000"},
            payload={
                "result": {
                    "text": "ok",
                    "utterances": [
                        {
                            "start_time": 0,
                            "end_time": 500,
                            "text": "ok",
                            "words": [{"start_time": 0, "end_time": 500, "text": "ok"}],
                        }
                    ],
                },
                "audio_info": {"duration": 500},
            },
        )


class FakePresignedUrl:
    signed_url = "https://bucket.tos.example/signed/audio.wav?token=1"


class FakeTosHttpMethodType:
    Http_Method_Get = "GET"


class FakeTosModule:
    HttpMethodType = FakeTosHttpMethodType


class FakeTosClient:
    def __init__(self):
        self.uploads = []
        self.presigns = []

    def put_object_from_file(self, bucket, key, file_path, content_type=None):
        self.uploads.append({"bucket": bucket, "key": key, "file_path": file_path, "content_type": content_type})

    def pre_signed_url(self, http_method, bucket, key, expires):
        self.presigns.append({"method": http_method, "bucket": bucket, "key": key, "expires": expires})
        return FakePresignedUrl()


class FakeTranscriptPipeline(VideoEvidencePipeline):
    def resolve_video_file(self, video, *, evidence_dir, progress=None):
        path = evidence_dir / "video.mp4"
        path.write_bytes(b"video")
        return path

    def probe_duration(self, video_path):
        return 1.0

    def extract_audio(self, video_path, audio_path, *, duration=0.0, progress=None):
        audio_path.write_bytes(b"audio")

    def transcribe(self, audio_path, *, duration=0.0, progress=None):
        return {
            "provider": "doubao_file_asr",
            "model": "volc.seedasr.auc",
            "language": "zh",
            "full_text": "ok",
            "segments": [{"start": 0.0, "end": 1.0, "text": "ok"}],
            "words": [{"start": 0.0, "end": 1.0, "text": "ok"}],
            "pause_points": [],
            "audio_url": "https://example.test/audio.wav",
            "raw_response": {"result": {"text": "ok"}},
        }

    def extract_keyframes(self, video_path, segments, output_dir, *, progress=None):
        return []


class FakeDownloadResponse:
    def __init__(self, status_code=200, content=b"video"):
        self.status_code = status_code
        self.text = "error" if status_code >= 400 else "ok"
        self.headers = {"content-length": str(len(content))}
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=1):
        yield self._content


class BrokenDownloadResponse(FakeDownloadResponse):
    def iter_content(self, chunk_size=1):
        yield b"partial-video"
        raise TimeoutError("stalled stream")


class FlakyDownloadSession:
    def __init__(self):
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return FakeDownloadResponse(status_code=503)
        return FakeDownloadResponse(status_code=200)


class AiVideoP3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pg_schema = isolated_postgres_schema("ai_video_p3")
        self.pg_schema.__enter__()
        self.addCleanup(self.pg_schema.__exit__, None, None, None)
        self.old_env = {
            key: os.environ.get(key)
            for key in [
                "AI_VIDEO_ASR_PUBLIC_BASE_URL",
                "AI_VIDEO_ASR_PUBLIC_DIR",
                "AI_VIDEO_ASR_PUBLIC_TOKEN_SALT",
                "AI_VIDEO_ASR_UPLOAD_MODE",
                "AI_VIDEO_ASR_PUBLISHER",
                "VOLCENGINE_ASR_APP_ID",
                "VOLCENGINE_ASR_ACCESS_TOKEN",
                "VOLCENGINE_ASR_DIRECT_URL",
                "VOLCENGINE_TOS_ACCESS_KEY",
                "VOLCENGINE_TOS_SECRET_KEY",
                "VOLCENGINE_TOS_ENDPOINT",
                "VOLCENGINE_TOS_REGION",
                "VOLCENGINE_TOS_BUCKET",
            ]
        }

    def tearDown(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_audio_publisher_copies_file_and_builds_stable_url(self):
        root = Path(self.tmp.name)
        audio = root / "evidence" / "job-1" / "audio.wav"
        audio.parent.mkdir(parents=True)
        audio.write_bytes(b"audio-bytes")
        publisher = AudioPublisher(public_dir=root / "public", public_base_url="https://public.example/asr")

        published = publisher.publish(audio)

        self.assertEqual(published.mode, "copied")
        self.assertTrue(Path(published.path).exists())
        self.assertTrue(published.url.startswith("https://public.example/asr/job-1/"))
        self.assertTrue(published.url.endswith(".wav"))

    def test_tos_publisher_uploads_file_and_returns_presigned_url(self):
        root = Path(self.tmp.name)
        audio = root / "evidence" / "job-1" / "audio.wav"
        audio.parent.mkdir(parents=True)
        audio.write_bytes(b"audio-bytes")
        client = FakeTosClient()
        publisher = TosAudioPublisher(
            ak="ak",
            sk="sk",
            endpoint="tos-cn.example.volces.com",
            region="cn-beijing",
            bucket="bucket",
            prefix="asr/audio",
            tos_module=FakeTosModule(),
            client=client,
            presign_expires_seconds=3600,
        )

        published = publisher.publish(audio)

        self.assertEqual(published.mode, "tos_presigned")
        self.assertEqual(published.url, "https://bucket.tos.example/signed/audio.wav?token=1")
        self.assertEqual(client.uploads[0]["bucket"], "bucket")
        self.assertTrue(client.uploads[0]["key"].startswith("asr/audio/"))
        self.assertEqual(client.presigns[0]["method"], "GET")
        self.assertEqual(published.expires_in_seconds, 3600)

    def test_doubao_base64_mode_posts_audio_data_without_url_publication(self):
        audio = Path(self.tmp.name) / "audio.wav"
        audio.write_bytes(b"audio")
        session = FakeAsrSession()
        client = DoubaoFileAsrClient(
            DoubaoAsrConfig(
                app_id="app",
                access_token="token",
                secret_key="secret",
                resource_id="volc.seedasr.auc",
                submit_url="https://submit.example",
                query_url="https://query.example",
                poll_interval_seconds=0,
                timeout_seconds=1,
                max_wait_seconds=1,
                upload_mode="base64",
                direct_url="https://direct.example",
                direct_max_bytes=100,
            ),
            session=session,
        )
        transcriber = DoubaoFileAsrTranscriber(client)

        transcript = transcriber.transcribe(audio, model="model", language="zh")

        self.assertEqual(transcript["upload_mode"], "base64")
        self.assertEqual(transcript["audio_url"], "")
        self.assertEqual(session.calls[0]["url"], "https://direct.example")
        self.assertIn("data", session.calls[0]["json"]["audio"])
        self.assertNotIn("url", session.calls[0]["json"]["audio"])

    def test_evidence_writes_raw_asr_response_to_checkpoint(self):
        root = Path(self.tmp.name)
        pipeline = FakeTranscriptPipeline(output_dir=root)

        evidence = pipeline.build({"id": "v1", "title": "Video"}, job_id="job-1")

        raw_path = Path(evidence["checkpoints"]["transcript_raw_path"])
        transcript_path = Path(evidence["checkpoints"]["transcript_path"])
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        self.assertTrue(raw_path.exists())
        self.assertEqual(json.loads(raw_path.read_text(encoding="utf-8"))["result"]["text"], "ok")
        self.assertNotIn("raw_response", transcript)
        self.assertEqual(evidence["schema_version"], "2.0")
        self.assertEqual(evidence["asr"]["provider"], "doubao_file_asr")
        self.assertEqual(evidence["metadata"]["audio_url"], "https://example.test/audio.wav")

    def test_evidence_preserves_douyin_target_context(self):
        root = Path(self.tmp.name)
        pipeline = FakeTranscriptPipeline(output_dir=root)
        video = {
            "id": "v1",
            "title": "Video",
            "statistics": {"digg_count": 100, "comment_count": 8},
            "derived_metrics": {"comment_like_ratio": 0.08},
            "douyin_target_context": {
                "metrics": {"share_like_ratio": 0.03},
                "interaction_snapshot": {
                    "keyword_counts": {"\u63a5": 2},
                    "top_comments": [{"text": "\u63a5\u597d\u8fd0"}],
                },
            },
        }

        evidence = pipeline.build(video, job_id="job-target")

        self.assertEqual(evidence["metadata"]["statistics"]["digg_count"], 100)
        self.assertEqual(evidence["metadata"]["derived_metrics"]["comment_like_ratio"], 0.08)
        self.assertEqual(evidence["douyin_target"]["metrics"]["share_like_ratio"], 0.03)
        evidence_path = Path(evidence["evidence_path"])
        persisted = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["douyin_target"]["interaction_snapshot"]["keyword_counts"]["\u63a5"], 2)

    def test_doubao_status_reports_tos_config_without_secrets(self):
        os.environ["VOLCENGINE_ASR_APP_ID"] = "app"
        os.environ["VOLCENGINE_ASR_ACCESS_TOKEN"] = "token"
        os.environ["AI_VIDEO_ASR_UPLOAD_MODE"] = "url"
        os.environ["AI_VIDEO_ASR_PUBLISHER"] = "tos"
        os.environ["VOLCENGINE_TOS_ACCESS_KEY"] = "ak"
        os.environ["VOLCENGINE_TOS_SECRET_KEY"] = "sk"
        os.environ["VOLCENGINE_TOS_ENDPOINT"] = "tos-cn.example.volces.com"
        os.environ["VOLCENGINE_TOS_REGION"] = "cn-beijing"
        os.environ["VOLCENGINE_TOS_BUCKET"] = "bucket"

        status = doubao_asr_status()

        self.assertTrue(status["provider_ready"])
        self.assertEqual(status["errors"], [])

    def test_remake_export_route_persists_export(self):
        short_video_analysis_store.init_db()
        payload = RemakeExportPayload(
            run_id="run-1",
            task_id="run-1",
            title="demo",
            genre="knowledge",
            target_genre="beauty",
            markdown="# demo",
            result={"summary": "source"},
            rewritten={"script": "rewrite"},
            export_type="cross_genre_rewrite",
        )

        response = save_remake_export_route(payload)

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["export"]["target_genre"], "beauty")
        self.assertEqual(response["export"]["rewritten"]["script"], "rewrite")

    def test_doubao_base64_validation_requires_direct_url(self):
        config = DoubaoAsrConfig(
            app_id="app",
            access_token="token",
            secret_key="secret",
            resource_id="volc.seedasr.auc",
            submit_url="https://submit.example",
            query_url="https://query.example",
            poll_interval_seconds=0,
            timeout_seconds=1,
            max_wait_seconds=1,
            upload_mode="base64",
            direct_url="",
            direct_max_bytes=100,
        )

        errors = validate_doubao_asr_environment(config=config, publisher="local")

        self.assertIn("AI_VIDEO_ASR_UPLOAD_MODE=base64 requires VOLCENGINE_ASR_DIRECT_URL", errors)

    def test_http_policy_retries_transient_download_errors(self):
        session = FlakyDownloadSession()

        with patch("integrations.ai_video_analysis.http_policy.time.sleep", lambda _seconds: None):
            response = get_with_retries("https://example.test/video.mp4", session=session, max_retries=1, timeout=1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.calls, 2)

    def test_evidence_refreshes_douyin_video_url_after_forbidden_download(self):
        root = Path(self.tmp.name)
        evidence_dir = root / "evidence" / "job-refresh"
        evidence_dir.mkdir(parents=True)
        pipeline = VideoEvidencePipeline(output_dir=root)
        calls = []

        def fake_download(url, **_kwargs):
            calls.append(url)
            if url == "https://stale.example/video.mp4":
                return FakeDownloadResponse(status_code=403)
            return FakeDownloadResponse(status_code=200, content=b"fresh-video")

        video = {"aweme_id": "aweme-refresh", "source_video_url": "https://stale.example/video.mp4"}
        with (
            patch("integrations.ai_video_analysis.evidence_pipeline.get_with_retries", side_effect=fake_download),
            patch.object(pipeline, "refresh_douyin_video_urls", return_value=["https://fresh.example/video.mp4"]) as refresh_urls,
        ):
            path = pipeline.resolve_video_file(video, evidence_dir=evidence_dir)

        self.assertEqual(path.read_bytes(), b"fresh-video")
        self.assertEqual(calls, ["https://stale.example/video.mp4", "https://fresh.example/video.mp4"])
        refresh_urls.assert_called_once_with(video)

    def test_evidence_discards_partial_video_when_stream_download_stalls(self):
        root = Path(self.tmp.name)
        evidence_dir = root / "evidence" / "job-stalled"
        evidence_dir.mkdir(parents=True)
        pipeline = VideoEvidencePipeline(output_dir=root)
        target = evidence_dir / "aweme-stalled.mp4"

        with patch(
            "integrations.ai_video_analysis.evidence_pipeline.get_with_retries",
            return_value=BrokenDownloadResponse(status_code=200, content=b"ignored"),
        ):
            with self.assertRaisesRegex(TimeoutError, "stalled stream"):
                pipeline.resolve_video_file(
                    {"aweme_id": "aweme-stalled", "source_video_url": "https://example.test/stalled.mp4"},
                    evidence_dir=evidence_dir,
                )

        self.assertFalse(target.exists())
        self.assertFalse(target.with_name(f"{target.name}.part").exists())

    def test_ffmpeg_command_stops_when_cancel_requested(self):
        pipeline = VideoEvidencePipeline(output_dir=Path(self.tmp.name))
        calls = {"count": 0}

        def cancel_check():
            calls["count"] += 1
            if calls["count"] >= 2:
                raise RuntimeError("cancelled")

        pipeline.cancel_check = cancel_check

        with self.assertRaises(RuntimeError):
            pipeline.run_command_capture(["python", "-c", "import time; time.sleep(30)"], timeout=30)

        self.assertGreaterEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()
