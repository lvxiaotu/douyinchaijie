import gc
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import tiktok_target_store as store
from tests.postgres_test_utils import isolated_postgres_schema


class TiktokTargetInteractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pg_schema = isolated_postgres_schema("tiktok_target")
        self.pg_schema.__enter__()
        self.addCleanup(self.pg_schema.__exit__, None, None, None)
        store.init_db()

    def tearDown(self):
        gc.collect()
        self.tmp.cleanup()

    def test_video_metrics_are_derived_on_save(self):
        video = store.create_target_video(
            "aweme-1",
            "user-1",
            {
                "aweme_id": "aweme-1",
                "desc": "demo",
                "create_time": 1716076800,
                "digg_count": 100,
                "comment_count": 10,
                "share_count": 5,
                "collect_count": 20,
                "play_count": 1000,
                "selected": True,
            },
        )

        self.assertEqual(video["digg_count"], 100)
        self.assertEqual(video["publish_hour"], 8)
        self.assertEqual(video["publish_hour_bucket"], "morning")
        self.assertEqual(video["like_collect_ratio"], 5)
        self.assertEqual(video["collect_like_ratio"], 0.2)
        self.assertEqual(video["comment_like_ratio"], 0.1)
        self.assertEqual(video["share_like_ratio"], 0.05)
        self.assertEqual(video["engagement_score"], 235)
        self.assertEqual(video["engagement_rate"], 0.235)
        self.assertEqual(video["metrics"]["publish"]["timezone"], "Asia/Shanghai")

    def test_existing_video_is_updated_when_collected_again_by_aweme_id(self):
        original = store.create_target_video(
            "target-row-1",
            "user-1",
            {
                "set_id": "set-1",
                "aweme_id": "same-aweme",
                "desc": "old desc",
                "digg_count": 10,
                "comment_count": 1,
                "selected": True,
                "source_json": {"old": True},
            },
        )

        updated = store.create_target_video(
            "same-aweme",
            "user-2",
            {
                "set_id": "set-1",
                "aweme_id": "same-aweme",
                "desc": "new desc",
                "digg_count": 99,
                "comment_count": 8,
                "selected": True,
                "source_json": {"new": True},
            },
        )

        videos = store.list_target_videos(limit=10)
        self.assertEqual(len(videos), 1)
        self.assertEqual(updated["id"], original["id"])
        self.assertEqual(updated["user_id"], "user-2")
        self.assertEqual(updated["desc"], "new desc")
        self.assertEqual(updated["digg_count"], 99)
        self.assertEqual(updated["comment_count"], 8)
        self.assertTrue(updated["source_json"]["old"])
        self.assertTrue(updated["source_json"]["new"])

    def test_set_video_views_follow_accounts_not_video_set_id(self):
        store.create_target_set("set-a", "Set A")
        store.create_target_set("set-b", "Set B")
        store.upsert_target_user(
            "user-1",
            {
                "sec_user_id": "sec-user-1",
                "unique_id": "user-one",
                "nickname": "User One",
            },
        )
        store.add_user_to_target_set("set-a", "user-1")
        store.add_user_to_target_set("set-b", "user-1")

        video = store.create_target_video(
            "account-video",
            "user-1",
            {
                "set_id": "legacy-set",
                "aweme_id": "account-video",
                "desc": "account owned video",
                "digg_count": 20,
                "selected": True,
                "analysis_status": "done",
            },
        )

        self.assertEqual(video["set_id"], "")
        self.assertEqual([item["id"] for item in store.list_target_videos(set_id="set-a")], ["account-video"])
        self.assertEqual([item["id"] for item in store.list_target_videos(set_id="set-b")], ["account-video"])

        sets = {item["id"]: item for item in store.list_target_sets(limit=10)}
        self.assertEqual(sets["set-a"]["video_count"], 1)
        self.assertEqual(sets["set-a"]["analyzed_count"], 1)
        self.assertEqual(sets["set-b"]["video_count"], 1)
        self.assertEqual(sets["set-b"]["analyzed_count"], 1)

        self.assertTrue(store.delete_target_set("set-a"))
        self.assertIsNotNone(store.get_target_video("account-video"))
        self.assertEqual(store.list_target_videos(set_id="set-a"), [])
        self.assertEqual([item["id"] for item in store.list_target_videos(set_id="set-b")], ["account-video"])

    def test_target_user_upsert_reuses_existing_sec_user_id(self):
        original = store.upsert_target_user(
            "user-row-1",
            {
                "sec_user_id": "sec-user-1",
                "unique_id": "first-handle",
                "nickname": "Old Name",
            },
        )

        updated = store.upsert_target_user(
            "different-user-row",
            {
                "sec_user_id": "sec-user-1",
                "unique_id": "new-handle",
                "nickname": "New Name",
            },
        )

        self.assertEqual(updated["id"], original["id"])
        self.assertEqual(updated["unique_id"], "new-handle")
        self.assertEqual(updated["nickname"], "New Name")
        self.assertEqual(len(store.list_target_users(limit=10)), 1)

    def test_bulk_save_skips_existing_set_user_by_sec_user_id(self):
        from backend.app.routes.douyin_target import TargetBulkSave, bulk_save_users

        store.create_target_set("set-sec-dedupe", "Sec ID Set")

        first = bulk_save_users(
            TargetBulkSave(
                set_id="set-sec-dedupe",
                users=[
                    {
                        "sec_user_id": "sec-user-save",
                        "uid": "uid-first",
                        "unique_id": "first-handle",
                        "nickname": "First",
                    },
                    {
                        "sec_user_id": "sec-user-save",
                        "uid": "uid-second",
                        "unique_id": "second-handle",
                        "nickname": "Second",
                    },
                ],
            )
        )

        self.assertEqual(first["added_count"], 1)
        self.assertEqual(first["count"], 1)
        self.assertEqual(first["skipped_duplicate_count"], 1)
        self.assertEqual(len(store.get_target_set_detail("set-sec-dedupe")["users"]), 1)
        store.add_user_to_target_set("set-sec-dedupe", "missing-user-row")
        self.assertEqual(store.list_target_sets(limit=10)[0]["user_count"], 1)

        second = bulk_save_users(
            TargetBulkSave(
                set_id="set-sec-dedupe",
                users=[
                    {
                        "sec_user_id": "sec-user-save",
                        "uid": "uid-third",
                        "unique_id": "third-handle",
                        "nickname": "Third",
                    }
                ],
            )
        )

        self.assertEqual(second["added_count"], 0)
        self.assertEqual(second["count"], 0)
        self.assertEqual(second["skipped_duplicate_count"], 1)
        self.assertEqual(len(store.get_target_set_detail("set-sec-dedupe")["users"]), 1)

    def test_comments_replies_and_insights_are_persisted(self):
        store.create_target_video(
            "video-row-2",
            "user-1",
            {
                "aweme_id": "aweme-2",
                "desc": "generic short video",
                "digg_count": 200,
                "comment_count": 4,
                "share_count": 10,
                "collect_count": 50,
            },
        )
        comments = [
            {
                "cid": "c1",
                "text": "\u592a\u771f\u5b9e\u4e86\uff0c\u8fd9\u5c31\u662f\u6211\uff0c\u771f\u7684\u5f88\u5171\u9e23",
                "digg_count": 30,
                "reply_comment_total": 1,
                "user": {"uid": "fan-1", "nickname": "fan"},
            },
            {
                "cid": "r1",
                "text": "\u8bb0\u5f97\u5728\u8bc4\u8bba\u533a\u544a\u8bc9\u6211\uff0c\u4e5f\u53ef\u4ee5\u770b\u4e3b\u9875\u94fe\u63a5",
                "digg_count": 5,
                "user": {"uid": "author-1", "nickname": "author"},
                "parent_comment_id": "c1",
                "level": 2,
                "is_author": True,
            },
            {
                "cid": "c2",
                "text": "\u54ea\u91cc\u4e70\uff1f\u6c42\u94fe\u63a5\uff0c\u591a\u5c11\u94b1",
                "digg_count": 20,
                "reply_comment_total": 0,
                "user": {"uid": "fan-2", "nickname": "lost"},
                "is_pinned": True,
            },
            {
                "cid": "c3",
                "text": "\u771f\u7684\u5047\u7684\uff1f\u6211\u4e0d\u4fe1\uff0c\u6709\u4f9d\u636e\u5417",
                "digg_count": 10,
                "reply_comment_total": 0,
                "user": {"uid": "fan-3", "nickname": "doubt"},
            },
        ]

        dataset = store.replace_target_video_comments("video-row-2", comments)
        aweme_dataset = store.get_target_video_interaction_dataset("aweme-2")

        self.assertEqual(dataset["comment_count"], 3)
        self.assertEqual(aweme_dataset["comment_count"], 3)
        self.assertEqual(aweme_dataset["video"]["id"], "video-row-2")
        self.assertEqual(dataset["reply_count"], 1)
        self.assertEqual(dataset["video"]["comment_snapshot_status"], "done")
        self.assertEqual(dataset["video"]["comment_saved_count"], 3)
        self.assertEqual(dataset["video"]["reply_saved_count"], 1)
        self.assertGreaterEqual(dataset["insights"]["keyword_counts"]["\u592a\u771f\u5b9e"], 1)
        self.assertEqual(dataset["insights"]["emotion_profile"]["dominant"], "resonance")
        self.assertEqual(dataset["insights"]["emotion_profile"]["dominant_motivation"], "resonance")
        self.assertGreaterEqual(dataset["insights"]["emotion_profile"]["buckets"]["purchase_or_link"], 1)
        self.assertGreaterEqual(dataset["insights"]["emotion_profile"]["buckets"]["doubt_or_controversy"], 1)
        self.assertEqual(dataset["insights"]["creator_reply_tactics"]["author_reply_count"], 1)
        self.assertGreaterEqual(dataset["insights"]["creator_reply_tactics"]["counts"]["ask_for_comment"], 1)
        self.assertEqual(dataset["insights"]["pinned_comments"][0]["comment_id"], "c2")

    def test_existing_comment_is_updated_when_collected_again(self):
        store.create_target_video(
            "video-comment-upsert",
            "user-1",
            {
                "aweme_id": "aweme-comment-upsert",
                "desc": "comments update",
                "digg_count": 100,
                "comment_count": 1,
            },
        )
        store.replace_target_video_comments(
            "video-comment-upsert",
            [
                {
                    "cid": "c1",
                    "text": "old comment",
                    "digg_count": 1,
                    "user": {"uid": "fan-1", "nickname": "fan"},
                }
            ],
        )

        dataset = store.replace_target_video_comments(
            "video-comment-upsert",
            [
                {
                    "cid": "c1",
                    "text": "new comment",
                    "digg_count": 9,
                    "user": {"uid": "fan-1", "nickname": "fan"},
                }
            ],
        )

        self.assertEqual(dataset["comment_count"], 1)
        self.assertEqual(dataset["comments"][0]["comment_id"], "c1")
        self.assertEqual(dataset["comments"][0]["text"], "new comment")
        self.assertEqual(dataset["comments"][0]["digg_count"], 9)

    def test_mysticism_comment_plugin_is_genre_scoped(self):
        store.create_target_video(
            "aweme-3",
            "user-1",
            {
                "aweme_id": "aweme-3",
                "desc": "\u5854\u7f57\u8fd0\u52bf",
                "digg_count": 100,
                "comment_count": 1,
                "share_count": 1,
                "collect_count": 1,
            },
        )
        dataset = store.replace_target_video_comments(
            "aweme-3",
            [
                {
                    "cid": "c1",
                    "text": "\u63a5\u597d\u8fd0\uff0c\u9886\u53d6\u597d\u8fd0\uff0c\u663e\u5316\u6210\u529f",
                    "digg_count": 3,
                    "user": {"uid": "fan-1", "nickname": "fan"},
                }
            ],
        )

        self.assertEqual(dataset["insights"]["genre"], "mysticism")
        self.assertGreaterEqual(dataset["insights"]["keyword_counts"]["\u63a5\u597d\u8fd0"], 1)
        self.assertGreaterEqual(dataset["insights"]["emotion_profile"]["genre_plugin_buckets"]["mysticism_manifest"], 1)

    def test_comment_sampling_plan_scales_with_comment_like_ratio(self):
        video = store.create_target_video(
            "aweme-4",
            "user-1",
            {
                "aweme_id": "aweme-4",
                "desc": "adaptive sampling",
                "digg_count": 1000,
                "comment_count": 180,
                "share_count": 20,
                "collect_count": 50,
            },
        )

        from backend.app.routes.douyin_target import CollectCommentsRequest, _comment_sampling_plan

        high_plan = _comment_sampling_plan(video, CollectCommentsRequest(max_comments=200, min_comments=30))
        self.assertEqual(high_plan["strategy"], "comment_like_ratio")
        self.assertEqual(high_plan["bucket"], "extreme_interaction")
        self.assertEqual(high_plan["max_comments"], 160)
        self.assertEqual(high_plan["replies_per_comment"], 3)

        low_video = store.create_target_video(
            "aweme-5",
            "user-1",
            {
                "aweme_id": "aweme-5",
                "desc": "low interaction",
                "digg_count": 5000,
                "comment_count": 20,
                "share_count": 4,
                "collect_count": 10,
            },
        )
        low_plan = _comment_sampling_plan(low_video, CollectCommentsRequest(max_comments=200, min_comments=30))
        self.assertEqual(low_plan["bucket"], "low_interaction")
        self.assertEqual(low_plan["max_comments"], 20)
        self.assertEqual(low_plan["replies_per_comment"], 1)

    def test_duplicate_comments_are_deduped_in_interaction_insights(self):
        store.create_target_video(
            "aweme-dedupe",
            "user-1",
            {
                "aweme_id": "aweme-dedupe",
                "desc": "duplicate comments",
                "digg_count": 100,
                "comment_count": 2,
            },
        )
        comment = {
            "cid": "same-comment",
            "text": "\u91cd\u590d\u8bc4\u8bba",
            "digg_count": 99,
            "user": {"uid": "fan-1", "nickname": "fan"},
        }

        dataset = store.replace_target_video_comments("aweme-dedupe", [comment, comment])

        self.assertEqual(len(dataset["insights"]["top_comments"]), 1)
        self.assertEqual(dataset["insights"]["top_comments"][0]["comment_id"], "same-comment")

    def test_same_author_same_text_comments_are_deduped_even_with_different_ids(self):
        store.create_target_video(
            "aweme-dedupe-text",
            "user-1",
            {
                "aweme_id": "aweme-dedupe-text",
                "desc": "duplicate comments by text",
                "digg_count": 100,
                "comment_count": 2,
            },
        )
        comments = [
            {
                "cid": "comment-a",
                "text": "我还以为逆位是痛苦减轻了呢[流泪]",
                "digg_count": 1681,
                "user": {"uid": "fan-1", "nickname": "~啊biu~"},
            },
            {
                "cid": "comment-b",
                "text": "我还以为逆位是痛苦减轻了呢[流泪]",
                "digg_count": 1681,
                "user": {"uid": "fan-1", "nickname": "~啊biu~"},
            },
        ]

        dataset = store.replace_target_video_comments("aweme-dedupe-text", comments)

        self.assertEqual(len(dataset["insights"]["top_comments"]), 1)
        self.assertEqual(dataset["insights"]["top_comments"][0]["comment_id"], "comment-a")

    def test_clear_analysis_preserves_comments_and_interaction_insights(self):
        store.create_target_video(
            "aweme-6",
            "user-1",
            {
                "aweme_id": "aweme-6",
                "desc": "analysis can be reset without losing comments",
                "digg_count": 100,
                "comment_count": 2,
                "share_count": 1,
                "collect_count": 8,
            },
        )
        store.replace_target_video_comments(
            "aweme-6",
            [
                {
                    "cid": "c1",
                    "text": "\u592a\u771f\u5b9e\u4e86\uff0c\u8fd9\u5c31\u662f\u6211",
                    "digg_count": 12,
                    "user": {"uid": "fan-1", "nickname": "fan"},
                }
            ],
        )
        store.create_target_task(
            "target-task-6",
            video_id="aweme-6",
            ai_task_id="ai-task-6",
            status="done",
        )
        analyzed = store.update_target_video_analysis(
            "aweme-6",
            status="done",
            task_id="ai-task-6",
            result={"summary": "done"},
        )
        self.assertEqual(analyzed["analysis_status"], "done")
        self.assertEqual(store.find_target_task_for_video("aweme-6", {"done"})["task_id"], "ai-task-6")

        cleared = store.clear_target_video_analysis("aweme-6")
        dataset = store.get_target_video_interaction_dataset("aweme-6")

        self.assertEqual(cleared["analysis_status"], "none")
        self.assertEqual(cleared["analysis_task_id"], "")
        self.assertEqual(cleared["analysis_result"], {})
        self.assertIsNone(cleared["analyzed_at"])
        self.assertIsNone(store.find_target_task_for_video("aweme-6", {"done"}))
        self.assertEqual(dataset["comment_count"], 1)
        self.assertEqual(dataset["video"]["comment_snapshot_status"], "done")
        self.assertTrue(dataset["insights"]["top_comments"])


if __name__ == "__main__":
    unittest.main()
