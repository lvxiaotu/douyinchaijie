import gc
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import tiktok_target_store as store
from integrations.tikhub_douyin_api.adapter import DEFAULT_USER_SEARCH_PATH, TikhubDouyinApiAdapter


class TikhubUserSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = store.DB_PATH
        store.DB_PATH = Path(self.tmp.name) / "tiktok_targeting.sqlite3"
        store.init_db()

    def tearDown(self):
        store.DB_PATH = self.old_db_path
        gc.collect()
        self.tmp.cleanup()

    def test_user_search_uses_v2_cursor_only_and_persists_full_page(self):
        upstream = {
            "status_code": 0,
            "data": {
                "cursor": 20,
                "has_more": 1,
                "extra": {"logid": "log-1"},
                "user_list": [
                    {
                        "user_info": {
                            "uid": "user-1",
                            "sec_uid": "sec-1",
                            "unique_id": "creator1",
                            "nickname": "Creator 1",
                            "follower_count": 12000,
                        }
                    },
                    {
                        "user_info": {
                            "uid": "user-2",
                            "sec_uid": "sec-2",
                            "unique_id": "creator2",
                            "nickname": "Creator 2",
                            "follower_count": 800,
                        }
                    },
                ],
            },
        }

        with patch.object(TikhubDouyinApiAdapter, "_request_json", return_value=upstream) as request_json:
            result = TikhubDouyinApiAdapter({"api_key": "test"}).search_users(
                keyword="塔罗",
                cursor=0,
                count=1,
                follower_filter="10k_100k",
                douyin_user_type="300",
                enrich_profiles=False,
            )

        spec = request_json.call_args.args[0]
        self.assertEqual(spec.path, DEFAULT_USER_SEARCH_PATH)
        self.assertEqual(spec.json_body, {"keyword": "塔罗", "cursor": 0})
        self.assertEqual(result["endpoint"], "/api/v1/douyin/search/fetch_user_search_v2")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["raw_count"], 2)
        self.assertEqual(result["requested_count"], 1)
        self.assertEqual(result["next_cursor"], 20)
        self.assertTrue(result["has_more"])

        cached = store.get_target_user_search_page(
            source="tikhub-douyin-api",
            keyword="塔罗",
            cursor=0,
            count=0,
        )
        self.assertIsNotNone(cached)
        self.assertEqual(len(cached["items"]), 2)
        self.assertEqual(cached["request"], {"keyword": "塔罗", "cursor": 0})
        self.assertEqual(cached["douyin_user_fans"], "")
        self.assertEqual(cached["douyin_user_type"], "")
        self.assertIsNotNone(store.get_target_user("user-1"))
        self.assertIsNotNone(store.get_target_user("user-2"))


if __name__ == "__main__":
    unittest.main()
