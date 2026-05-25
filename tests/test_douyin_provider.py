import os
import unittest
from unittest.mock import patch

from integrations.douyin_provider.factory import configured_provider_mode, get_douyin_provider
from integrations.douyin_provider.fallback import FallbackDouyinProvider
from integrations.douyin_provider.observed import ObservedDouyinProvider
from integrations.douyin_provider.observability import get_provider_metrics
from integrations.douyin_spider_provider import DouyinSpiderAdapter
from integrations.douyin_spider_provider.sidecar_server import app as sidecar_app
from backend.app.routes import douyin as douyin_routes
from backend.app.routes import douyin_legacy_tikhub as legacy_routes
from backend.app.routes import douyin_target as target_routes
from fastapi.testclient import TestClient


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


if __name__ == "__main__":
    unittest.main()
