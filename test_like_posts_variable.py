"""Offline tests for variable-controlled Instagram follow+like workflow."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
import unittest

from scripts.like_posts_variable import run


class VariableEngagementTests(unittest.TestCase):
    @staticmethod
    @contextmanager
    def session():
        yield Path("/tmp/mock-ig-session.json")

    def setUp(self):
        self.posts = [
            {"code": "POST1", "username": "author1", "age": 1.0},
            {"code": "POST2", "username": "author2", "age": 2.0},
            {"code": "POST3", "username": "author3", "age": 3.0},
        ]
        self.media = {
            post["code"]: NS(
                code=post["code"], id=f"{n}_45678{n}", has_liked=False,
                taken_at=datetime.now(timezone.utc)-timedelta(hours=2),
                caption_text="Hello #followforfollow",
                user=NS(pk=f"45678{n}", username=post["username"], is_private=False),
            ) for n, post in enumerate(self.posts, start=1)
        }
        self.client = NS(
            user_id="123",
            media_pk_from_code=MagicMock(side_effect=lambda code: code),
            media_info=MagicMock(side_effect=lambda code, use_cache: self.media[code]),
            user_friendship_v1=MagicMock(return_value=NS(
                following=False, outgoing_request=False,
            )),
        )

    @staticmethod
    def args(mode="follow_like", count=2):
        return NS(mode=mode, count=count, hashtag="followforfollow",
                  max_pages=3, output_dir="")

    def execute(self, args, outcomes=None):
        if outcomes is None:
            outcomes = [{"follow": "confirmed", "like": "confirmed"}]*3
        with patch("scripts.like_posts_variable.private_session_path", self.session), \
             patch("scripts.like_posts_variable.load_http", return_value=object()), \
             patch("scripts.like_posts_variable.retrieve",
                   return_value=(self.posts, [{"http": "200"}])), \
             patch("scripts.like_posts_variable.make_client",
                   return_value=self.client) as make, \
             patch("scripts.like_posts_variable.engagement",
                   side_effect=outcomes) as action, \
             patch("scripts.like_posts_variable.time.sleep"), \
             patch("scripts.like_posts_variable.save_report") as save:
            status = run(args)
            return status, save.call_args.args[0], make, action

    def test_two_posts_means_two_follows_and_two_likes(self):
        status, report, _, action = self.execute(self.args())
        self.assertEqual(status, 0)
        self.assertEqual(report["confirmed"], 2)
        self.assertEqual(report["follows_confirmed"], 2)
        self.assertEqual(action.call_count, 2)

    def test_variable_one_reduces_actions(self):
        status, report, _, action = self.execute(self.args(count=1))
        self.assertEqual(status, 0)
        self.assertEqual(report["confirmed"], 1)
        self.assertEqual(action.call_count, 1)

    def test_preview_no_writes(self):
        status, report, make, action = self.execute(self.args(mode="preview"))
        self.assertEqual(status, 0)
        self.assertEqual(report["confirmed"], 0)
        make.assert_not_called()
        action.assert_not_called()

    def test_skips_already_liked(self):
        self.media["POST1"].has_liked = True
        status, report, _, action = self.execute(self.args())
        self.assertEqual(status, 0)
        self.assertEqual(report["already_liked"], 1)
        self.assertEqual(action.call_count, 2)

    def test_unconfirmed_action_stops_not_retried(self):
        status, report, _, action = self.execute(
            self.args(), [{"follow": "confirmed", "like": "uncertain", "error": "timeout"}]
        )
        self.assertEqual(status, 2)
        self.assertEqual(report["follows_confirmed"], 1)
        self.assertEqual(report["confirmed"], 0)
        self.assertEqual(action.call_count, 1)

    def test_rejects_count_over_100_before_network(self):
        with patch("scripts.like_posts_variable.private_session_path") as session, \
             patch("scripts.like_posts_variable.save_report"):
            self.assertEqual(run(self.args(count=101)), 2)
            session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
