import json
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from backend.app import task_store
from backend.app.video_analysis_queue import (
    AiVideoTaskCancelled,
    cancel_ai_video_job,
    enqueue_ai_video_job,
    init_ai_video_queue_db,
    list_ai_model_runs,
    list_ai_video_artifacts,
    list_ai_video_chunks,
    record_ai_model_run,
)
from integrations.ai_video_analysis.doubao_asr import normalize_doubao_asr_response
from integrations.ai_video_analysis.adapter import AiVideoAnalysisAdapter
from integrations.ai_video_analysis.analysis_runner import run_evidence_breakdown
from integrations.ai_video_analysis.evidence_pipeline import VideoEvidencePipeline
from integrations.ai_video_analysis.model_gateway import normalized_usage, resolve_ai_video_provider_route, uses_openai_compatible_relay
from integrations.ai_video_analysis.prompt_builder import segment_breakdown_prompt
from integrations.ai_video_analysis.result_normalizer import parse_model_json, parse_segment_json
from integrations.ai_video_analysis.result_schema import validate_analysis_result, validate_segment_breakdown
from integrations.ai_video_analysis.relay_clients import GeminiGenerateContentRelayClient, OpenAICompatibleRelayClient
from integrations.ai_video_analysis.relay_clients import DeepSeekChatClient


class FakeRelayResponse:
    status_code = 200
    text = '{"ok": true}'

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [{"message": {"content": "{\"summary\":\"ok\"}"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        }


class FakeGeminiRelayResponse:
    status_code = 200
    text = '{"ok": true}'

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "candidates": [{"content": {"parts": [{"text": "{\"summary\":\"gemini\"}"}]}}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3, "totalTokenCount": 8},
        }


class FakeRelaySession:
    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeRelayResponse()


class FakeGeminiRelaySession(FakeRelaySession):
    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeGeminiRelayResponse()


class AiVideoP2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = task_store.DB_PATH
        self.old_env = {
            key: os.environ.get(key)
            for key in [
                "AI_VIDEO_RELAY_API_KEY",
                "AI_VIDEO_RELAY_BASE_URL",
                "AI_VIDEO_RELAY_API_FORMAT",
                "YUNWU_API_KEY",
                "AI_RELAY_API_KEY",
                "AI_VIDEO_PHASH_DEDUP_ENABLED",
                "AI_VIDEO_PHASH_DEDUP_THRESHOLD",
                "YUNWU_API_FORMAT",
                "AI_VIDEO_SUMMARY_PROVIDER",
                "AI_VIDEO_SUMMARY_API_KEY",
                "AI_VIDEO_SUMMARY_BASE_URL",
                "AI_VIDEO_SUMMARY_MODEL",
                "AI_VIDEO_SUMMARY_FALLBACK_PROVIDER",
                "DEEPSEEK_API_KEY",
                "DEEPSEEK_BASE_URL",
                "DEEPSEEK_MODEL",
            ]
        }

    def tearDown(self):
        task_store.DB_PATH = self.old_db_path
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_analysis_task_model_runs_round_trip(self):
        task_store.DB_PATH = Path(self.tmp.name) / "tasks.sqlite3"
        task_store.init_db()
        init_ai_video_queue_db()
        task_store.create_task(
            task_id="task-1",
            task_type="ai_video_analysis",
            title="Video",
            provider="yunwu",
            payload={"video": {"id": "v1", "desc": "Video"}},
        )
        record_ai_model_run(
            task_id="task-1",
            provider="deepseek",
            model="deepseek-v4-flash",
            purpose="global_breakdown",
            latency_ms=456,
            meta={"fallback_from": "deepseek", "fallback_provider": "openai_compatible_relay"},
        )

        runs = list_ai_model_runs("task-1")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["meta"]["fallback_from"], "deepseek")
        self.assertEqual(runs[0]["meta"]["fallback_provider"], "openai_compatible_relay")

    def test_openai_compatible_relay_uses_single_v1_chat_completions_path(self):
        os.environ["AI_VIDEO_RELAY_API_KEY"] = "test-key"
        session = FakeRelaySession()
        client = OpenAICompatibleRelayClient(
            base_url="https://yunwu.ai/v1",
            api_key="test-key",
            model="gemini-2.5flash",
            session=session,
            max_retries=0,
        )

        response = client.generate_text(prompt="return json")

        self.assertEqual(session.calls[0]["url"], "https://yunwu.ai/v1/chat/completions")
        self.assertNotIn("/v1/v1/", session.calls[0]["url"])
        self.assertEqual(session.calls[0]["json"]["model"], "gemini-2.5flash")
        self.assertEqual(response.text, "{\"summary\":\"ok\"}")
        self.assertEqual(response.usage["prompt_tokens"], 11)

    def test_openai_compatible_relay_adds_v1_only_for_host_root(self):
        self.assertEqual(
            OpenAICompatibleRelayClient.normalize_base_url("https://yunwu.ai"),
            "https://yunwu.ai/v1",
        )

    def test_gemini_generate_content_relay_uses_yunwu_v1beta_path(self):
        session = FakeGeminiRelaySession()
        client = GeminiGenerateContentRelayClient(
            base_url="https://yunwu.ai",
            api_key="test-key",
            model="gemini-2.5-flash",
            session=session,
            max_retries=0,
        )

        response = client.generate_text(prompt="return json", image_paths=[], temperature=0)

        self.assertEqual(session.calls[0]["url"], "https://yunwu.ai/v1beta/models/gemini-2.5-flash:generateContent")
        self.assertEqual(session.calls[0]["json"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(session.calls[0]["json"]["contents"][0]["parts"][0]["text"], "return json")
        self.assertEqual(response.text, "{\"summary\":\"gemini\"}")
        self.assertEqual(response.usage["promptTokenCount"], 5)

    def test_adapter_yunwu_generate_content_format_uses_native_relay_client(self):
        os.environ["AI_VIDEO_RELAY_API_FORMAT"] = "gemini_generate_content"
        os.environ["YUNWU_API_FORMAT"] = "gemini_generate_content"
        adapter = AiVideoAnalysisAdapter({"provider": "yunwu"})

        route = resolve_ai_video_provider_route("yunwu")
        self.assertEqual(route.family, "gemini_relay")
        self.assertEqual(route.base_url, "https://yunwu.ai")
        self.assertEqual(route.api_format, "gemini_generate_content")
        self.assertEqual(route.config_errors, ())
        self.assertEqual(adapter.validate_config(), [])

    def test_deepseek_official_url_does_not_add_v1(self):
        client = DeepSeekChatClient(api_key="key", base_url="https://api.deepseek.com", model="deepseek-v4-flash")

        self.assertEqual(client.base_url, "https://api.deepseek.com")
        self.assertEqual(client.chat_completions_url, "https://api.deepseek.com/chat/completions")

    def test_yunwu_provider_is_allowed_when_openai_compatible_format_is_enabled(self):
        os.environ["AI_VIDEO_RELAY_API_FORMAT"] = "openai_chat_completions"
        os.environ["YUNWU_API_FORMAT"] = "openai_chat_completions"
        os.environ["AI_VIDEO_RELAY_API_KEY"] = ""
        os.environ["YUNWU_API_KEY"] = ""
        os.environ["AI_RELAY_API_KEY"] = ""
        adapter = AiVideoAnalysisAdapter({"provider": "yunwu"})

        route = resolve_ai_video_provider_route("yunwu")
        self.assertEqual(route.family, "openai_compatible_relay")
        self.assertIn("Missing AI_VIDEO_RELAY_API_KEY", adapter.validate_config())
        self.assertIn("Missing AI_VIDEO_RELAY_API_KEY", route.config_errors)
        self.assertEqual(
            OpenAICompatibleRelayClient.normalize_base_url("https://yunwu.ai/v1/chat/completions"),
            "https://yunwu.ai/v1",
        )

    def test_direct_pipeline_rejects_openai_compatible_route(self):
        os.environ["AI_VIDEO_RELAY_API_FORMAT"] = "openai_chat_completions"
        os.environ["YUNWU_API_FORMAT"] = "openai_chat_completions"
        os.environ["AI_VIDEO_RELAY_API_KEY"] = "test-key"
        adapter = AiVideoAnalysisAdapter({"provider": "yunwu", "pipeline_mode": "direct"})

        route = resolve_ai_video_provider_route("yunwu", pipeline_mode="direct")
        self.assertIn("AI_VIDEO_PIPELINE_MODE=direct requires Gemini relay", route.config_errors)
        self.assertIn("AI_VIDEO_PIPELINE_MODE=direct requires Gemini relay", adapter.validate_config())

    def test_model_gateway_openai_compatible_detection_is_independent(self):
        os.environ["AI_VIDEO_RELAY_API_FORMAT"] = "chat_completions"

        self.assertTrue(uses_openai_compatible_relay("yunwu"))
        self.assertEqual(
            normalized_usage(
                {"promptTokenCount": 7, "candidatesTokenCount": 4},
                action="summary",
                latency_ms=123,
                input_token_keys=("promptTokenCount", "prompt_tokens"),
                output_token_keys=("candidatesTokenCount", "completion_tokens"),
            ),
            {"input_tokens": 7, "output_tokens": 4, "latency_ms": 123, "action": "summary"},
        )

    def test_doubao_response_normalizes_segments_words_and_pause_points(self):
        raw = {
            "result": {
                "text": "你好世界",
                "utterances": [
                    {
                        "start_time": 0,
                        "end_time": 1000,
                        "text": "你好",
                        "words": [
                            {"start_time": 0, "end_time": 300, "text": "你"},
                            {"start_time": 900, "end_time": 1000, "text": "好"},
                        ],
                    },
                    {
                        "start_time": 1500,
                        "end_time": 2000,
                        "text": "世界",
                        "words": [{"start_time": 1500, "end_time": 2000, "text": "世界"}],
                    },
                ],
            },
            "audio_info": {"duration": 2000},
        }

        transcript = normalize_doubao_asr_response(raw, language="zh")

        self.assertEqual(transcript["full_text"], "你好世界")
        self.assertEqual(len(transcript["segments"]), 2)
        self.assertEqual(transcript["segments"][1]["start"], 1.5)
        self.assertEqual(len(transcript["words"]), 3)
        self.assertTrue(any(point["reason"] == "word_gap" for point in transcript["pause_points"]))

    def test_dhash_keyframe_dedupe_removes_near_identical_images(self):
        os.environ["AI_VIDEO_PHASH_DEDUP_ENABLED"] = "true"
        os.environ["AI_VIDEO_PHASH_DEDUP_THRESHOLD"] = "1"
        root = Path(self.tmp.name)
        first = root / "first.jpg"
        second = root / "second.jpg"
        third = root / "third.jpg"
        Image.new("RGB", (32, 32), "white").save(first)
        Image.new("RGB", (32, 32), "white").save(second)
        Image.new("RGB", (32, 32), "black").save(third)
        pipe = VideoEvidencePipeline(output_dir=root)

        deduped = pipe.dedupe_keyframes(
            [
                {"frame_id": "a", "time": 1, "image_path": str(first)},
                {"frame_id": "b", "time": 2, "image_path": str(second)},
                {"frame_id": "c", "time": 3, "image_path": str(third)},
            ]
        )

        self.assertEqual([frame["frame_id"] for frame in deduped], ["a", "c"])
        self.assertEqual(deduped[0]["dedupe_removed_count"], 1)

    def test_deepseek_summary_uses_dedicated_global_model(self):
        os.environ["AI_VIDEO_SUMMARY_PROVIDER"] = "deepseek"
        os.environ["AI_VIDEO_SUMMARY_API_KEY"] = "summary-key"
        os.environ["AI_VIDEO_SUMMARY_BASE_URL"] = "https://api.deepseek.com"
        os.environ["AI_VIDEO_SUMMARY_MODEL"] = "deepseek-v4-flash"
        session = FakeRelaySession()
        adapter = AiVideoAnalysisAdapter({"provider": "yunwu", "summary_provider": "deepseek", "summary_model": "deepseek-v4-flash"})

        original_client = adapter._generate_text_with_deepseek
        def fake_deepseek(prompt, action):
            from integrations.ai_video_analysis.relay_clients import DeepSeekChatClient

            client = DeepSeekChatClient(api_key="summary-key", session=session, max_retries=0)
            response = client.generate_summary(prompt=prompt, model="deepseek-v4-flash")
            adapter._last_model_usage = response.usage
            adapter._last_model_provider_value = "deepseek"
            adapter._last_model_name_value = "deepseek-v4-flash"
            return response.text

        adapter._generate_text_with_deepseek = fake_deepseek
        try:
            text = adapter._generate_global_summary_json("return json", action="summary")
        finally:
            adapter._generate_text_with_deepseek = original_client

        self.assertEqual(text, "{\"summary\":\"ok\"}")
        self.assertEqual(session.calls[0]["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(session.calls[0]["json"]["model"], "deepseek-v4-flash")
        self.assertEqual(adapter._last_model_provider(""), "deepseek")
        self.assertEqual(adapter._last_model_name(""), "deepseek-v4-flash")

    def test_deepseek_summary_falls_back_to_segment_model(self):
        adapter = AiVideoAnalysisAdapter(
            {
                "provider": "yunwu",
                "summary_provider": "deepseek",
                "summary_model": "deepseek-v4-flash",
                "summary_fallback_provider": "vision",
            }
        )

        def fail_deepseek(prompt, action):
            raise RuntimeError("deepseek down")

        def fallback(prompt, action, image_paths=None, **kwargs):
            adapter._last_model_usage = {"prompt_tokens": 3, "completion_tokens": 2}
            adapter._last_model_provider_value = "openai_compatible_relay"
            adapter._last_model_name_value = "gemini-2.5flash"
            return "{\"summary\":\"fallback\"}"

        adapter._generate_text_with_deepseek = fail_deepseek
        adapter._generate_text_json = fallback

        text = adapter._generate_global_summary_json("return json", action="summary")

        self.assertEqual(text, "{\"summary\":\"fallback\"}")
        self.assertEqual(adapter._last_model_usage["fallback_from"], "deepseek")
        self.assertIn("deepseek down", adapter._last_model_usage["fallback_error"])
        self.assertEqual(adapter._last_model_provider(""), "openai_compatible_relay")

    def test_deepseek_summary_can_disable_fallback(self):
        adapter = AiVideoAnalysisAdapter(
            {
                "provider": "yunwu",
                "summary_provider": "deepseek",
                "summary_model": "deepseek-v4-flash",
                "summary_fallback_provider": "none",
            }
        )

        def fail_deepseek(prompt, action):
            raise RuntimeError("deepseek down")

        adapter._generate_text_with_deepseek = fail_deepseek

        with self.assertRaises(RuntimeError):
            adapter._generate_global_summary_json("return json", action="summary")

    def test_prompt_engine_injects_genre_profile_into_segment_prompt(self):
        adapter = AiVideoAnalysisAdapter({"provider": "mock"})
        prompt = adapter._segment_breakdown_prompt(
            {"desc": "3 个护肤避坑", "genre": "beauty"},
            {
                "segment_id": "seg_001",
                "time_range": "00:00-00:12",
                "transcript": "敏感肌不要乱叠加",
                "keyframes": [],
                "keyframe_grid": {},
            },
        )

        self.assertIn("美妆/护肤", prompt)
        self.assertIn("visual_style", prompt)
        self.assertIn("audio_pacing", prompt)
        self.assertIn("narrative_technique", prompt)
        self.assertIn("retention_mechanism", prompt)

    def test_prompt_builder_segment_prompt_is_independent(self):
        prompt = segment_breakdown_prompt(
            {"desc": "3 个护肤避坑", "genre": "beauty"},
            {"segment_id": "seg_001", "time_range": "00:00-00:12", "transcript": "敏感肌不要乱叠加"},
        )

        self.assertIn("美妆/护肤", prompt)
        self.assertIn('"segment_id": "seg_001"', prompt)
        self.assertIn("敏感肌不要乱叠加", prompt)

    def test_global_prompt_uses_generic_cross_genre_contract(self):
        adapter = AiVideoAnalysisAdapter({"provider": "mock"})
        prompt = adapter._global_breakdown_prompt(
            {"desc": "反常识科普", "genre": "knowledge"},
            evidence={
                "metadata": {"author": "creator", "genre": "knowledge"},
                "transcript": {"full_text": "原来很多人都理解错了"},
                "douyin_target": {"metrics": {"comment_like_ratio": 0.08}},
            },
            segment_breakdowns=[
                {
                    "segment_id": "seg_001",
                    "visual_style": "talking head",
                    "retention_mechanism": "反常识",
                }
            ],
        )

        self.assertIn("知识/科普", prompt)
        self.assertIn("cross_genre_variants", prompt)
        self.assertIn("standard_remake_template", prompt)
        self.assertIn("数据指标抓异常", prompt)

    def test_parse_model_json_preserves_generic_p2_fields(self):
        adapter = AiVideoAnalysisAdapter({"provider": "mock"})
        result = adapter._parse_model_json(
            json.dumps(
                {
                    "genre": "knowledge",
                    "summary": "ok",
                    "content_identity": {"track": "knowledge"},
                    "replication_plan": {
                        "pattern_name": "反常识拆解",
                        "cross_genre_variants": ["美妆", "数码", "探店"],
                    },
                    "standard_remake_template": "[人群] 以为 [误区]，其实 [真相]",
                },
                ensure_ascii=False,
            )
        )

        self.assertEqual(result["genre"], "knowledge")
        self.assertIn("美妆", result["replication_plan"]["cross_genre_variants"])
        self.assertEqual(result["standard_remake_template"], "[人群] 以为 [误区]，其实 [真相]")

    def test_result_normalizer_parse_model_json_is_independent(self):
        result = parse_model_json(
            "```json\n"
            + json.dumps(
                {
                    "summary": "ok",
                    "核心钩子": {"开头3秒钩子": "先抛反常识"},
                    "评分": {"综合评分": "88分"},
                },
                ensure_ascii=False,
            )
            + "\n```"
        )

        self.assertEqual(result["summary"], "ok")
        self.assertEqual(result["core_hook"]["opening_3s"], "先抛反常识")
        self.assertEqual(result["viral_scores"]["overall"], 88)

    def test_result_normalizer_parse_segment_json_repairs_aliases(self):
        result = parse_segment_json(
            json.dumps({"visual_signal": "近景切换", "audio_rhythm": "快节奏", "hook": "反常识"}, ensure_ascii=False),
            {"segment_id": "seg_001", "time_range": "00:00-00:05", "genre": "knowledge"},
        )

        self.assertEqual(result["segment_id"], "seg_001")
        self.assertEqual(result["visual_style"], "近景切换")
        self.assertEqual(result["audio_pacing"], "快节奏")
        self.assertEqual(result["retention_mechanism"], "反常识")

    def test_result_schema_clamps_scores_and_keeps_raw_json(self):
        result = validate_analysis_result(
            {
                "summary": ["ok", "next"],
                "viral_scores": {"overall": "108分", "comment_potential": "-5"},
                "segment_breakdowns": [{"segment_id": "seg_001", "visual_style": ["近景", "字幕"]}],
                "unexpected": {"keep": True},
            }
        )

        self.assertEqual(result["summary"], "ok；next")
        self.assertEqual(result["viral_scores"]["overall"], 100)
        self.assertEqual(result["viral_scores"]["comment_potential"], 0)
        self.assertEqual(result["segment_breakdowns"][0]["visual_style"], "近景；字幕")
        self.assertTrue(result["unexpected"]["keep"])
        self.assertIn("raw_model_json", result)

    def test_segment_schema_normalizes_text_fields(self):
        result = validate_segment_breakdown(
            {
                "segment_id": 1,
                "time_range": "00:00-00:05",
                "visual_style": {"shot": "close"},
                "audio_pacing": ["fast", "beat"],
            }
        )

        self.assertEqual(result["segment_id"], "1")
        self.assertEqual(result["visual_style"], "close")
        self.assertEqual(result["audio_pacing"], "fast；beat")

    def test_adapter_records_evidence_artifacts_and_initial_chunks(self):
        root = Path(self.tmp.name)
        task_store.DB_PATH = root / "tasks.sqlite3"
        task_store.init_db()
        init_ai_video_queue_db()
        video_path = root / "video.mp4"
        audio_path = root / "audio.wav"
        transcript_path = root / "transcript.json"
        keyframes_path = root / "keyframes.json"
        grid_path = root / "grid.jpg"
        evidence_path = root / "analysis_evidence.json"
        for path in [video_path, audio_path, transcript_path, keyframes_path, grid_path, evidence_path]:
            path.write_text("x", encoding="utf-8")
        adapter = AiVideoAnalysisAdapter({"provider": "mock", "output_dir": str(root)})

        adapter._record_evidence_state(
            "task-1",
            {
                "schema_version": "2.0",
                "evidence_path": str(evidence_path),
                "metadata": {"video_path": str(video_path), "audio_path": str(audio_path), "duration": 12},
                "asr": {"provider": "fake"},
                "keyframes": [{"image_path": "frame.jpg"}],
                "checkpoints": {"transcript_path": str(transcript_path), "keyframes_path": str(keyframes_path)},
                "analysis_segments": [
                    {
                        "segment_id": "seg_001",
                        "start": 0,
                        "end": 12,
                        "time_range": "00:00-00:12",
                        "transcript": "hello",
                        "keyframes": [{"image_path": "frame.jpg"}],
                        "keyframe_grid": {"image_path": str(grid_path)},
                    }
                ],
            },
        )

        artifact_types = {item["type"] for item in list_ai_video_artifacts("task-1")}
        chunks = list_ai_video_chunks("task-1")
        self.assertTrue({"video", "audio", "transcript", "keyframes", "keyframe_grid", "evidence_json"}.issubset(artifact_types))
        self.assertEqual(chunks[0]["status"], "pending")
        self.assertEqual(chunks[0]["grid_uri"], str(grid_path))
        self.assertEqual(chunks[0]["meta"]["segment_id"], "seg_001")

    def test_analysis_runner_stops_after_segment_model_when_cancel_requested(self):
        root = Path(self.tmp.name)
        task_store.DB_PATH = root / "tasks.sqlite3"
        task_store.init_db()
        init_ai_video_queue_db()
        evidence_dir = root / "task-cancel-runner"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_dir / "analysis_evidence.json"
        evidence_path.write_text("{}", encoding="utf-8")
        grid_path = evidence_dir / "grid.jpg"
        grid_path.write_text("x", encoding="utf-8")
        task_store.create_task(
            task_id="task-cancel-runner",
            task_type="ai_video_analysis",
            title="video",
            provider="mock",
            payload={"video": {"id": "v1"}},
        )
        enqueue_ai_video_job(task_id="task-cancel-runner", video={"id": "v1"}, provider="mock")
        adapter = AiVideoAnalysisAdapter({"provider": "mock", "output_dir": str(root)})

        def fake_generate(prompt, *, action, image_paths=None, **kwargs):
            cancel_ai_video_job("task-cancel-runner")
            return json.dumps({"segment_role": "hook"}, ensure_ascii=False)

        adapter._generate_text_json = fake_generate

        with self.assertRaises(AiVideoTaskCancelled):
            run_evidence_breakdown(
                adapter,
                {"id": "v1"},
                evidence={
                    "evidence_path": str(evidence_path),
                    "analysis_segments": [
                        {
                            "segment_id": "seg_001",
                            "start": 0,
                            "end": 5,
                            "time_range": "00:00-00:05",
                            "transcript": "hello",
                            "keyframes": [],
                            "keyframe_grid": {"image_path": str(grid_path)},
                        }
                    ],
                },
            )

        chunks = list_ai_video_chunks("task-cancel-runner")
        self.assertEqual(chunks[0]["status"], "cancelled")
        self.assertFalse(list_ai_video_artifacts("task-cancel-runner"))


if __name__ == "__main__":
    unittest.main()
