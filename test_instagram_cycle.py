"""Offline regression tests for the live Instagram cycle, no network/writes."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
import unittest

from scripts.manual_instagram_actions import (
    HASHTAG_POOL, check_target_media, execute_single_engagement, parse_args, run,
)


class CycleTests(unittest.TestCase):
    @staticmethod
    @contextmanager
    def session():
        yield Path("/tmp/mock-instagram-session.json")

    def setUp(self):
        self.user_id = "123456789"
        self.media = NS(
            code="POST1", id="111111_234567890", has_liked=False,
            taken_at=datetime.now(timezone.utc) - timedelta(hours=2),
            caption_text="Hello #followforfollow",
            user=NS(pk="234567890", username="other_person", is_private=False),
        )
        self.client = NS(
            user_id=self.user_id,
            media_pk_from_code=MagicMock(return_value="111111"),
            media_info=MagicMock(return_value=self.media),
            user_friendship_v1=MagicMock(return_value=NS(
                following=False, outgoing_request=False
            )),
            user_follow=MagicMock(return_value=True),
            media_like=MagicMock(return_value=True),
        )

    @staticmethod
    def args(count=2, tag="followforfollow"):
        return NS(target_count=count, hashtag=tag, max_pages=3, output_dir="")

    def invoke(self, args, candidates_per_tag=24, outcomes=None):
        calls = []

        def fetch(session_path, tag, max_pages):
            calls.append(tag)
            index = HASHTAG_POOL.index(tag)
            return [
                {"code": f"{index}POST{i}", "username": f"author{index}_{i}",
                 "age": float(i)}
                for i in range(candidates_per_tag)
            ]

        if outcomes is None:
            def outcomes(client, code, tag, expected_user):
                return {
                    "follow": "confirmed", "like": "confirmed",
                    "username": expected_user, "status": "confirmed",
                }, True

        with patch("scripts.manual_instagram_actions.private_session_path", self.session), \
             patch("scripts.manual_instagram_actions.make_client", return_value=self.client), \
             patch("scripts.manual_instagram_actions.fetch_feed_candidates", side_effect=fetch), \
             patch("scripts.manual_instagram_actions.execute_single_engagement", side_effect=outcomes):
            status = run(args)
        return status, calls

    def test_argument_parsing_no_mode(self):
        with patch("sys.argv", [
            "manual_instagram_actions", "--hashtag", "followforfollow",
            "--target-count", "2", "--max-pages", "3",
        ]):
            args = parse_args()
            self.assertEqual(args.target_count, 2)
            self.assertEqual(args.hashtag, "followforfollow")

    def test_default_two_pairs_only_first_hashtag(self):
        status, calls = self.invoke(self.args(2))
        self.assertEqual(status, 0)
        self.assertEqual(calls, ["followforfollow"])

    def test_twenty_first_pair_switches_hashtag(self):
        status, calls = self.invoke(self.args(21))
        self.assertEqual(status, 0)
        self.assertEqual(calls, list(HASHTAG_POOL[:2]))

    def test_all_five_hashtags_at_hundred(self):
        status, calls = self.invoke(self.args(100))
        self.assertEqual(status, 0)
        self.assertEqual(calls, list(HASHTAG_POOL))

    def test_insufficient_posts_stop_no_invented_count(self):
        status, calls = self.invoke(self.args(21), candidates_per_tag=19)
        self.assertEqual(status, 2)
        self.assertEqual(calls, ["followforfollow"])

    def test_error_in_follow_cannot_count_as_pair(self):
        def fail(client, code, tag, expected_user):
            return {"follow": "uncertain", "like": "not_attempted",
                    "error": "Follow outcome uncertain"}, False
        status, calls = self.invoke(self.args(21), outcomes=fail)
        self.assertEqual(status, 2)
        self.assertEqual(calls, ["followforfollow"])

    def test_rejects_out_of_bounds_before_network(self):
        for count in (0, 101):
            with self.subTest(count=count), \
                 patch("scripts.manual_instagram_actions.private_session_path") as secret:
                self.assertEqual(run(self.args(count)), 2)
                secret.assert_not_called()

    def test_skips_already_liked_without_writes(self):
        self.media.has_liked = True
        with patch("scripts.manual_instagram_actions.time.sleep"):
            outcome, success = execute_single_engagement(
                self.client, "POST1", "followforfollow",
                expected_user="other_person"
            )
        self.assertFalse(success)
        self.assertEqual(outcome["status"], "already_liked")
        self.client.user_follow.assert_not_called()
        self.client.media_like.assert_not_called()

    def test_skips_already_following_without_writes(self):
        self.client.user_friendship_v1.return_value = NS(
            following=True, outgoing_request=False
        )
        with patch("scripts.manual_instagram_actions.time.sleep"):
            outcome, success = execute_single_engagement(
                self.client, "POST1", "followforfollow",
                expected_user="other_person"
            )
        self.assertFalse(success)
        self.assertEqual(outcome["status"], "already_following_or_requested")
        self.client.user_follow.assert_not_called()
        self.client.media_like.assert_not_called()

    def test_one_new_follow_and_one_new_like(self):
        with patch("scripts.manual_instagram_actions.time.sleep"):
            outcome, success = execute_single_engagement(
                self.client, "POST1", "followforfollow",
                expected_user="other_person"
            )
        self.assertTrue(success)
        self.assertEqual(outcome["follow"], "confirmed")
        self.assertEqual(outcome["like"], "confirmed")
        self.client.user_follow.assert_called_once_with("234567890")
        self.client.media_like.assert_called_once_with("111111_234567890")

    def test_unconfirmed_follow_does_not_like(self):
        self.client.user_follow.return_value = False
        with patch("scripts.manual_instagram_actions.time.sleep"):
            outcome, success = execute_single_engagement(
                self.client, "POST1", "followforfollow",
                expected_user="other_person"
            )
        self.assertFalse(success)
        self.assertEqual(outcome["follow"], "unconfirmed")
        self.client.media_like.assert_not_called()

    def test_verified_link_points_to_correct_post(self):
        target = check_target_media(self.media, "POST1", "followforfollow")
        self.assertEqual(target["url"], "https://www.instagram.com/p/POST1/")


if __name__ == "__main__":
    unittest.main()
