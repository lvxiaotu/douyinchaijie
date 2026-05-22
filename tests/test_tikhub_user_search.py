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
from integrations.tikhub_douyin_api.adapter import (
    DEFAULT_AWEME_ID_PATH,
    DEFAULT_SEC_USER_ID_PATH,
    DEFAULT_USER_COLLECTION_VIDEOS_PATH,
    DEFAULT_USER_SEARCH_PATH,
    DEFAULT_VIDEO_COMMENT_REPLIES_PATH,
    DEFAULT_VIDEO_COMMENTS_PATH,
    USER_SEARCH_CACHE_SOURCE,
    TikhubDouyinApiAdapter,
)
from tests.postgres_test_utils import isolated_postgres_schema


class TikhubUserSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pg_schema = isolated_postgres_schema("tikhub_user_search")
        self.pg_schema.__enter__()
        self.addCleanup(self.pg_schema.__exit__, None, None, None)
        store.init_db()

    def tearDown(self):
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
                            "signature": "Profile intro",
                            "ip_location": "广东",
                            "follower_count": 12000,
                            "total_favorited": 345600,
                            "aweme_count": 88,
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
            source=USER_SEARCH_CACHE_SOURCE,
            keyword="塔罗",
            cursor=0,
            count=0,
        )
        self.assertIsNotNone(cached)
        self.assertEqual(len(cached["items"]), 2)
        self.assertEqual(cached["request"], {"keyword": "塔罗", "cursor": 0})
        self.assertEqual(cached["douyin_user_fans"], "")
        self.assertEqual(cached["douyin_user_type"], "")
        user = store.get_target_user("user-1")
        self.assertIsNotNone(user)
        self.assertEqual(user["signature"], "Profile intro")
        self.assertEqual(user["ip_location"], "广东")
        self.assertEqual(user["follower_count"], 12000)
        self.assertEqual(user["like_count"], 345600)
        self.assertEqual(user["aweme_count"], 88)
        self.assertIsNotNone(store.get_target_user("user-2"))

    def test_user_profile_enrichment_persists_ip_location(self):
        search_payload = {
            "status_code": 0,
            "data": {
                "cursor": 0,
                "has_more": 0,
                "user_list": [
                    {
                        "user_info": {
                            "uid": "user-profile",
                            "sec_uid": "sec-profile",
                            "unique_id": "profile1",
                            "nickname": "Profile 1",
                        }
                    }
                ],
            },
        }
        profile_payload = {
            "status_code": 0,
            "data": {
                "user": {
                    "uid": "user-profile",
                    "sec_uid": "sec-profile",
                    "unique_id": "profile1",
                    "nickname": "Profile 1",
                    "signature": "Full profile intro",
                    "ip_location": "上海",
                    "aweme_count": 990,
                    "total_favorited": 20191000,
                    "follower_count": 728000,
                }
            },
        }

        def fake_request(adapter, spec):
            if spec.path.endswith("handler_user_profile"):
                return profile_payload
            return search_payload

        with patch.object(TikhubDouyinApiAdapter, "_request_json", autospec=True, side_effect=fake_request):
            result = TikhubDouyinApiAdapter({"api_key": "test"}).search_users(keyword="菊菊塔罗", cursor=0, count=1)

        self.assertEqual(result["items"][0]["signature"], "Full profile intro")
        self.assertEqual(result["items"][0]["ip_location"], "上海")
        self.assertEqual(result["items"][0]["aweme_count"], 990)
        self.assertEqual(result["items"][0]["like_count"], 20191000)
        self.assertEqual(result["items"][0]["follower_count"], 728000)
        user = store.get_target_user("user-profile")
        self.assertEqual(user["signature"], "Full profile intro")
        self.assertEqual(user["ip_location"], "上海")
        self.assertEqual(user["aweme_count"], 990)
        self.assertEqual(user["like_count"], 20191000)
        self.assertEqual(user["follower_count"], 728000)

    def test_user_profile_enrichment_uses_sec_uid_from_search_wrapper(self):
        search_payload = {
            "status_code": 0,
            "data": {
                "cursor": 0,
                "has_more": 0,
                "user_list": [
                    {
                        "sec_uid": "wrapper-sec",
                        "user_info": {
                            "uid": "wrapper-user",
                            "unique_id": "wrapper1",
                            "nickname": "Wrapper 1",
                        },
                    }
                ],
            },
        }
        profile_payload = {
            "status_code": 0,
            "data": {
                "user": {
                    "uid": "wrapper-user",
                    "sec_uid": "wrapper-sec",
                    "unique_id": "wrapper1",
                    "nickname": "Wrapper 1",
                    "signature": "Profile from handler_user_profile",
                    "ip_location": "IP属地：山东",
                    "aweme_count": 949,
                    "total_favorited": 20194153,
                    "follower_count": 728067,
                }
            },
        }
        seen_paths = []

        def fake_request(adapter, spec):
            seen_paths.append(spec.path)
            if spec.path.endswith("handler_user_profile"):
                self.assertEqual(spec.params, {"sec_user_id": "wrapper-sec"})
                return profile_payload
            return search_payload

        with patch.object(TikhubDouyinApiAdapter, "_request_json", autospec=True, side_effect=fake_request):
            result = TikhubDouyinApiAdapter({"api_key": "test"}).search_users(keyword="葱葱塔罗", cursor=0, count=1)

        self.assertIn("/api/v1/douyin/web/handler_user_profile", seen_paths)
        self.assertEqual(result["items"][0]["signature"], "Profile from handler_user_profile")
        self.assertEqual(result["items"][0]["ip_location"], "IP属地：山东")
        self.assertEqual(result["items"][0]["aweme_count"], 949)
        self.assertEqual(result["items"][0]["like_count"], 20194153)
        user = store.get_target_user("wrapper-user")
        self.assertEqual(user["signature"], "Profile from handler_user_profile")
        self.assertEqual(user["ip_location"], "IP属地：山东")

    def test_user_profile_enrichment_treats_search_user_id_as_sec_user_id(self):
        sec_user_id = "MS4wLjABAAAAsearchUserIdIsActuallySecUid"
        search_payload = {
            "status_code": 0,
            "data": {
                "cursor": 0,
                "has_more": 0,
                "user_list": [
                    {
                        "user_id": sec_user_id,
                        "nick_name": "Search V2 User",
                        "fans_cnt": 12345,
                    }
                ],
            },
        }
        profile_payload = {
            "status_code": 0,
            "data": {
                "user": {
                    "uid": "real-uid",
                    "sec_uid": sec_user_id,
                    "unique_id": "search_v2_user",
                    "nickname": "Search V2 User",
                    "signature": "Fetched by handler_user_profile",
                    "ip_location": "IP属地：北京",
                    "aweme_count": 12,
                    "total_favorited": 34567,
                    "follower_count": 12345,
                }
            },
        }

        def fake_request(adapter, spec):
            if spec.path.endswith("handler_user_profile"):
                self.assertEqual(spec.params, {"sec_user_id": sec_user_id})
                return profile_payload
            return search_payload

        with patch.object(TikhubDouyinApiAdapter, "_request_json", autospec=True, side_effect=fake_request):
            result = TikhubDouyinApiAdapter({"api_key": "test"}).search_users(keyword="搜索V2", cursor=0, count=1)

        self.assertEqual(result["items"][0]["sec_uid"], sec_user_id)
        self.assertEqual(result["items"][0]["signature"], "Fetched by handler_user_profile")
        self.assertEqual(result["items"][0]["ip_location"], "IP属地：北京")
        user = store.get_target_user("real-uid")
        self.assertEqual(user["sec_user_id"], sec_user_id)
        self.assertEqual(user["signature"], "Fetched by handler_user_profile")

    def test_profile_payload_data_user_fields_are_extracted_when_saved(self):
        profile_payload = {
            "code": 200,
            "data": {
                "status_code": 0,
                "user": {
                    "uid": "raw-user",
                    "sec_uid": "raw-sec",
                    "unique_id": "raw_unique",
                    "nickname": "Raw User",
                    "signature": "不会用小号主动关注私信",
                    "ip_location": "IP属地：山东",
                    "aweme_count": 949,
                    "total_favorited": 20194153,
                    "follower_count": 728067,
                },
            },
        }

        saved = store.upsert_target_user(
            "raw-user",
            {
                "sec_user_id": "raw-sec",
                "unique_id": "raw_unique",
                "nickname": "Raw User",
                "source_json": profile_payload,
            },
        )

        self.assertEqual(saved["signature"], "不会用小号主动关注私信")
        self.assertEqual(saved["ip_location"], "IP属地：山东")
        self.assertEqual(saved["aweme_count"], 949)
        self.assertEqual(saved["like_count"], 20194153)
        self.assertEqual(saved["total_favorited"], 20194153)
        self.assertEqual(saved["follower_count"], 728067)

    def test_comments_and_replies_use_tikhub_web_endpoints(self):
        seen = []

        def fake_request(adapter, spec):
            seen.append(spec)
            if spec.path == DEFAULT_VIDEO_COMMENTS_PATH:
                self.assertEqual(spec.params, {"aweme_id": "aweme-1", "cursor": 0, "count": 2})
                return {
                    "data": {
                        "comments": [
                            {"cid": "c1", "text": "第一条", "digg_count": 3},
                            {"cid": "c2", "text": "第二条", "digg_count": 1},
                        ],
                        "cursor": 0,
                        "has_more": 0,
                    }
                }
            if spec.path == DEFAULT_VIDEO_COMMENT_REPLIES_PATH:
                self.assertEqual(spec.params, {"item_id": "aweme-1", "comment_id": "c1", "cursor": 0, "count": 1})
                return {
                    "data": {
                        "reply_comments": [{"cid": "r1", "text": "回复"}],
                        "cursor": 0,
                        "has_more": 0,
                    }
                }
            raise AssertionError(f"unexpected path: {spec.path}")

        with patch.object(TikhubDouyinApiAdapter, "_request_json", autospec=True, side_effect=fake_request):
            adapter = TikhubDouyinApiAdapter({"api_key": "test"})
            comments = adapter.get_video_comments("aweme-1", max_items=2, page_size=2)
            replies = adapter.get_video_comment_replies("aweme-1", "c1", max_items=1, page_size=1)

        self.assertEqual(comments["endpoint"], DEFAULT_VIDEO_COMMENTS_PATH)
        self.assertEqual([item["cid"] for item in comments["items"]], ["c1", "c2"])
        self.assertEqual(replies["endpoint"], DEFAULT_VIDEO_COMMENT_REPLIES_PATH)
        self.assertEqual(replies["items"][0]["cid"], "r1")
        self.assertEqual([spec.path for spec in seen], [DEFAULT_VIDEO_COMMENTS_PATH, DEFAULT_VIDEO_COMMENT_REPLIES_PATH])

    def test_favorites_use_tikhub_collection_endpoint(self):
        seen = []

        def fake_request(adapter, spec):
            seen.append(spec)
            self.assertEqual(spec.path, DEFAULT_USER_COLLECTION_VIDEOS_PATH)
            self.assertEqual(spec.method, "POST")
            self.assertEqual(spec.json_body, {"cookie": "cookie-value", "max_cursor": 0, "counts": 2})
            return {
                "data": {
                    "aweme_list": [
                        {
                            "aweme_id": "fav-1",
                            "desc": "收藏视频",
                            "statistics": {"digg_count": 9, "comment_count": 1},
                            "video": {
                                "play_addr": {"url_list": ["https://example.test/play.mp4"]},
                                "download_addr": {"url_list": ["https://example.test/download.mp4"]},
                            },
                        }
                    ],
                    "max_cursor": 0,
                    "has_more": 0,
                }
            }

        with patch.object(TikhubDouyinApiAdapter, "_request_json", autospec=True, side_effect=fake_request):
            result = TikhubDouyinApiAdapter({"api_key": "test", "douyin_web_cookie": "cookie-value"}).get_favorite_videos(
                max_items=2,
                page_size=2,
            )

        self.assertEqual(result["endpoint"], DEFAULT_USER_COLLECTION_VIDEOS_PATH)
        self.assertEqual(result["items"][0]["aweme_id"], "fav-1")
        self.assertEqual(result["items"][0]["download_url"], "https://example.test/download.mp4")
        self.assertEqual(len(seen), 1)

    def test_download_favorites_downloads_media_urls_locally(self):
        favorite_payload = {
            "data": {
                "aweme_list": [
                    {
                        "aweme_id": "fav-download-1",
                        "desc": "下载收藏视频",
                        "video": {
                            "download_addr": {"url_list": ["https://media.example.test/video.mp4"]},
                        },
                    }
                ],
                "max_cursor": 0,
                "has_more": 0,
            }
        }

        class FakeResponse:
            url = "https://media.example.test/video.mp4"
            status_code = 200
            headers = {"content-type": "video/mp4"}
            text = ""

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size=1):
                yield b"video-bytes"

        with patch.object(TikhubDouyinApiAdapter, "_request_json", return_value=favorite_payload):
            with patch("integrations.tikhub_douyin_api.adapter.requests.get", return_value=FakeResponse()) as download:
                adapter = TikhubDouyinApiAdapter(
                    {
                        "api_key": "test",
                        "douyin_web_cookie": "cookie-value",
                        "output_dir": str(Path(self.tmp.name) / "downloads"),
                    }
                )
                result = adapter.download_favorite_videos(max_items=1, page_size=1)

        download.assert_called_once()
        self.assertEqual(result["mode"], "downloaded")
        self.assertEqual(result["downloaded"][0]["aweme_id"], "fav-download-1")
        saved_path = Path(result["downloaded"][0]["path"])
        self.assertTrue(saved_path.exists())
        self.assertEqual(saved_path.read_bytes(), b"video-bytes")
        self.assertEqual(result["skipped"], [])

    def test_url_id_helpers_use_tikhub_web_endpoints(self):
        def fake_request(adapter, spec):
            if spec.path == DEFAULT_AWEME_ID_PATH:
                self.assertEqual(spec.params, {"url": "https://www.douyin.com/video/1"})
                return {"data": {"aweme_id": "aweme-from-url"}}
            if spec.path == DEFAULT_SEC_USER_ID_PATH:
                self.assertEqual(spec.params, {"url": "https://www.douyin.com/user/1"})
                return {"data": {"sec_user_id": "sec-from-url"}}
            raise AssertionError(f"unexpected path: {spec.path}")

        with patch.object(TikhubDouyinApiAdapter, "_request_json", autospec=True, side_effect=fake_request):
            adapter = TikhubDouyinApiAdapter({"api_key": "test"})
            self.assertEqual(adapter.get_aweme_id("https://www.douyin.com/video/1"), "aweme-from-url")
            self.assertEqual(adapter.get_sec_user_id("https://www.douyin.com/user/1"), "sec-from-url")


if __name__ == "__main__":
    unittest.main()
