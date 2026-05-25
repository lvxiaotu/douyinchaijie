import json
import os
import unittest
from unittest.mock import patch

from integrations.douyin_provider.factory import configured_provider_mode, get_douyin_provider
from integrations.douyin_provider.fallback import FallbackDouyinProvider
from integrations.douyin_provider.observed import ObservedDouyinProvider
from integrations.douyin_provider.observability import get_provider_metrics
from integrations.douyin_spider_provider import DouyinSpiderAdapter
from integrations.douyin_spider_provider.adapter import DouyinSpiderApiError
from integrations.douyin_spider_provider.sidecar_server import app as sidecar_app
from backend.app.routes import douyin as douyin_routes
from backend.app.routes import douyin_legacy_tikhub as legacy_routes
from backend.app.routes import media_proxy as media_proxy_routes
from backend.app.routes import douyin_target as target_routes
from fastapi.testclient import TestClient


class FakeMediaProxyResponse:
    def __init__(self, status_code=200, content=b"video", url="https://example.test/video.mp4"):
        self.status_code = status_code
        self.content = content
        self.url = url
        self.headers = {"content-type": "video/mp4", "content-length": str(len(content))}
        self.text = content.decode("utf-8", errors="ignore")
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"{self.status_code} Client Error")

    def iter_content(self, chunk_size=1024):
        yield self.content

    def close(self):
        self.closed = True


class DouyinProviderTests(unittest.TestCase):
    def test_factory_defaults_to_legacy_tikhub(self):
        with patch.dict(os.environ, {"DOUYIN_PROVIDER_MODE": ""}):
            provider = get_douyin_provider()
            self.assertEqual(configured_provider_mode(), "tikhub")
            self.assertIsInstance(provider, ObservedDouyinProvider)
            self.assertEqual(provider.provider.__class__.__name__, "LegacyTikhubDouyinAdapter")

    def test_factory_accepts_spider_first_mode(self):
        with patch.dict(os.environ, {"DOUYIN_PROVIDER_MODE": "spider_first"}):
            provider = get_douyin_provider()
            self.assertEqual(configured_provider_mode(), "spider_first")
            self.assertIsInstance(provider.provider, FallbackDouyinProvider)

    def test_factory_falls_back_to_legacy_on_invalid_mode(self):
        with patch.dict(os.environ, {"DOUYIN_PROVIDER_MODE": "unknown"}):
            provider = get_douyin_provider()
            self.assertEqual(configured_provider_mode(), "tikhub")
            self.assertEqual(provider.provider.__class__.__name__, "LegacyTikhubDouyinAdapter")

    def test_fallback_provider_records_trace_when_primary_fails(self):
        class BadProvider:
            def get_user_profile(self, sec_user_id):
                raise RuntimeError("primary failed")

        class GoodProvider:
            class manifest:
                id = "good-provider"

            def get_user_profile(self, sec_user_id):
                return {"status": "ok", "sec_user_id": sec_user_id}

        provider = FallbackDouyinProvider(BadProvider(), GoodProvider())
        result = provider.get_user_profile("sec-1")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["sec_user_id"], "sec-1")
        self.assertTrue(result["provider_trace"]["fallback_used"])
        self.assertEqual(result["provider_trace"]["provider"], "good-provider")
        self.assertIn("primary failed", result["provider_trace"]["primary_error"])

    def test_compat_douyin_route_uses_provider_factory(self):
        class Provider:
            def get_user_profile(self, sec_user_id):
                return {"status": "ok", "source": "provider", "sec_user_id": sec_user_id}

        with patch.object(douyin_routes, "get_douyin_provider", return_value=Provider()):
            result = douyin_routes.user_profile(douyin_routes.UserProfileRequest(sec_user_id="sec-1"))

        self.assertEqual(result["source"], "provider")
        self.assertEqual(result["sec_user_id"], "sec-1")

    def test_douyin_config_saves_provider_mode(self):
        with (
            patch.object(douyin_routes, "write_env_values") as write_env,
            patch.object(douyin_routes, "get_config", return_value={"provider_mode": "spider_first"}),
        ):
            result = douyin_routes.save_config(
                douyin_routes.DouyinConfigPayload(
                    api_base="https://api.tikhub.io",
                    output_dir="./data/runtime/douyin/downloads",
                    cookie="",
                    provider_mode="spider_first",
                )
            )

        self.assertEqual(result["config"]["provider_mode"], "spider_first")
        self.assertEqual(write_env.call_args.args[0]["DOUYIN_PROVIDER_MODE"], "spider_first")

    def test_target_search_still_uses_legacy_search_provider(self):
        class SearchProvider:
            def search_users(self, **kwargs):
                return {"status": "ok", "items": [{"sec_user_id": "sec-1", "nickname": "用户"}]}

            def enrich_user_profiles(self, items, **kwargs):
                return [{**item, "enriched": True} for item in items]

        with patch.object(target_routes, "get_douyin_search_provider", return_value=SearchProvider()):
            result = target_routes.search(target_routes.TargetSearchRequest(keyword="塔罗", count=1))

        self.assertEqual(result["count"], 1)
        self.assertTrue(result["items"][0]["enriched"])

    def test_legacy_route_uses_legacy_adapter_namespace(self):
        class LegacyProvider:
            def search_users(self, **kwargs):
                return {"status": "ok", "source": "legacy", "items": []}

        with patch.object(legacy_routes, "legacy_adapter", return_value=LegacyProvider()):
            result = legacy_routes.user_search(legacy_routes.UserSearchRequest(keyword="塔罗"))

        self.assertEqual(result["source"], "legacy")

    def test_observed_provider_records_metrics(self):
        class GoodProvider:
            class manifest:
                id = "observed-good"

            def get_user_profile(self, sec_user_id):
                return {"status": "ok", "sec_user_id": sec_user_id}

        provider = ObservedDouyinProvider(GoodProvider(), mode="test")
        result = provider.get_user_profile("sec-1")
        metrics = get_provider_metrics()

        self.assertEqual(result["sec_user_id"], "sec-1")
        self.assertGreaterEqual(metrics["total_calls"], 1)
        self.assertTrue(any(item["provider"] == "observed-good" for item in metrics["calls"]))

    def test_spider_sidecar_mode_delegates_run(self):
        adapter = DouyinSpiderAdapter({"execution_mode": "sidecar", "sidecar_base_url": "http://sidecar.test"})

        with patch.object(adapter, "_sidecar_run", return_value={"status": "ok", "source": "sidecar"}) as sidecar_run:
            result = adapter.get_user_profile("sec-1")

        self.assertEqual(result["source"], "sidecar")
        self.assertEqual(sidecar_run.call_args.args[0]["action"], "user_profile")

    def test_sidecar_server_uses_inprocess_adapter(self):
        with patch.object(DouyinSpiderAdapter, "status", return_value={"ready": True, "errors": [], "execution_mode": "inprocess"}):
            client = TestClient(sidecar_app)
            result = client.get("/status")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["execution_mode"], "inprocess")

    def test_spider_download_candidates_prefer_play_addr(self):
        adapter = DouyinSpiderAdapter({"execution_mode": "inprocess", "cookie": "s_v_web_id=test"})
        item = adapter._normalize_video(
            {
                "aweme_id": "123456",
                "video": {
                    "play_addr": {
                        "uri": "video-uri-1",
                        "url_list": [
                            "https://play.example/first.mp4",
                            "https://play.example/second.mp4",
                        ],
                    },
                    "play_addr_h264": {"url_list": ["https://h264.example/video.mp4"]},
                    "download_addr": {"url_list": ["https://download.example/video.mp4"]},
                },
            }
        )

        urls = adapter._downloadable_video_urls(item)

        self.assertEqual(urls[0], "https://play.example/first.mp4")
        self.assertIn("https://play.example/second.mp4", urls)
        self.assertIn("https://aweme.snssdk.com/aweme/v1/play/?video_id=video-uri-1&ratio=1080p&line=0", urls)
        self.assertGreater(urls.index("https://download.example/video.mp4"), urls.index("https://play.example/first.mp4"))

    def test_spider_download_tries_next_candidate_after_failure(self):
        adapter = DouyinSpiderAdapter({"execution_mode": "inprocess", "cookie": "s_v_web_id=test"})

        with patch.object(adapter, "_download_media_url", side_effect=[RuntimeError("403"), "saved.mp4"]) as download:
            path, used_url = adapter._download_media_urls(
                ["https://bad.example/video.mp4", "https://good.example/video.mp4"],
                "123456",
                item={},
            )

        self.assertEqual(path, "saved.mp4")
        self.assertEqual(used_url, "https://good.example/video.mp4")
        self.assertEqual(download.call_count, 2)

    def test_spider_comments_empty_json_response_is_failed_risk_control(self):
        adapter = DouyinSpiderAdapter({"execution_mode": "inprocess", "cookie": "s_v_web_id=test"})
        error = DouyinSpiderApiError(
            method="get_work_out_comment",
            message="Douyin_Spider get_work_out_comment failed: Expecting value: line 1 column 1 (char 0)",
            cause=json.JSONDecodeError("Expecting value", "", 0),
        )

        with patch.object(adapter, "_call", side_effect=error):
            with self.assertRaises(DouyinSpiderApiError) as caught:
                adapter.get_video_comments("123456", max_items=5, page_size=5)

        self.assertEqual(caught.exception.method, "get_work_out_comment")
        self.assertIn("risk control", str(caught.exception))
        self.assertIn("not as zero comments", str(caught.exception))

    def test_spider_comment_replies_empty_json_response_is_failed_risk_control(self):
        adapter = DouyinSpiderAdapter({"execution_mode": "inprocess", "cookie": "s_v_web_id=test"})
        error = DouyinSpiderApiError(
            method="get_work_inner_comment",
            message="Douyin_Spider get_work_inner_comment failed: Expecting value: line 1 column 1 (char 0)",
            cause=json.JSONDecodeError("Expecting value", "", 0),
        )

        with patch.object(adapter, "_call", side_effect=error):
            with self.assertRaises(DouyinSpiderApiError) as caught:
                adapter.get_video_comment_replies("123456", "comment-1", max_items=5, page_size=5)

        self.assertEqual(caught.exception.method, "get_work_inner_comment")
        self.assertIn("risk control", str(caught.exception))
        self.assertIn("not as zero comments", str(caught.exception))

    def test_media_proxy_refreshes_douyin_url_after_forbidden_response(self):
        calls = []

        def fake_get(url, **_kwargs):
            calls.append(url)
            if url == "https://stale.example/video.mp4":
                return FakeMediaProxyResponse(status_code=403, url=url)
            return FakeMediaProxyResponse(status_code=200, content=b"fresh", url=url)

        class Provider:
            def get_one_video(self, aweme_id, prefer_cache=True):
                return {
                    "video": {"aweme_id": aweme_id},
                    "download_urls": {"play_addr": "https://fresh.example/video.mp4"},
                }

        with (
            patch("backend.app.routes.media_proxy.requests.get", side_effect=fake_get),
            patch("integrations.douyin_provider.factory.get_douyin_provider", return_value=Provider()),
        ):
            response = media_proxy_routes.proxy_remote_media(
                url="https://stale.example/video.mp4",
                referer="https://www.douyin.com/video/123456",
                aweme_id="123456",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, ["https://stale.example/video.mp4", "https://fresh.example/video.mp4"])


if __name__ == "__main__":
    unittest.main()
