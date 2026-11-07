"""Offline tests for the 20-likes-per-hashtag rotation."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
import unittest

from scripts.like_posts_variable import HASHTAGS, hashtag_plan, run, parse_args


class VariableEngagementTests(unittest.TestCase):
    @staticmethod
    @contextmanager
    def session():
        yield Path("/tmp/mock-ig-session.json")

    @staticmethod
    def args(mode="follow_like", count=2):
        return NS(mode=mode, count=count, max_pages=3, output_dir="")

    def setUp(self):
        self.media = {}
        self.posts = {}
        sequence = 0
        for tag in HASHTAGS:
            self.posts[tag] = []
            for i in range(21):
                sequence += 1
                code = f"POST{sequence}"
                user_id = str(600000000 + sequence)
                user = f"author{sequence}"
                self.posts[tag].append(
                    {"code": code, "username": user, "age": float(i + 1)}
                )
                self.media[code] = NS(
                    code=code, id=f"{sequence}_{user_id}", has_liked=False,
                    taken_at=datetime.now(timezone.utc) - timedelta(hours=2),
                    caption_text=f"Hello #{tag}",
                    user=NS(pk=user_id, username=user, is_private=False),
                )
        self.client = NS(
            user_id="123",
            media_pk_from_code=MagicMock(side_effect=lambda code: code),
            media_info=MagicMock(side_effect=lambda code, use_cache: self.media[code]),
            user_friendship_v1=MagicMock(
                return_value=NS(following=False, outgoing_request=False)
            ),
        )

    def execute(self, args, outcome=None):
        if outcome is None:
            outcome = {"follow": "confirmed", "like": "confirmed"}

        def discover(http, tag, max_pages):
            return self.posts[tag], [{"http": "200"}]

        with patch("scripts.like_posts_variable.private_session_path", self.session), \
             patch("scripts.like_posts_variable.load_http", return_value=object()), \
             patch("scripts.like_posts_variable.retrieve", side_effect=discover) as search, \
             patch("scripts.like_posts_variable.make_client",
                   return_value=self.client) as make, \
             patch("scripts.like_posts_variable.engagement",
                   return_value=outcome) as engagement, \
             patch("scripts.like_posts_variable.time.sleep"), \
             patch("scripts.like_posts_variable.save_report") as save:
            status = run(args)
            return status, save.call_args.args[0], search, make, engagement

    def test_actual_cli_two_post_parse(self):
        with patch("sys.argv", [
            "like_posts_variable", "--mode", "follow_like",
            "--count", "2", "--max-pages", "3",
        ]):
            args = parse_args()
            self.assertEqual(args.count, 2)
            self.assertEqual(args.mode, "follow_like")
            self.assertEqual(args.max_pages, 3)

    def test_plan_counts_and_order(self):
        self.assertEqual(hashtag_plan(2), [("followforfollow", 2)])
        self.assertEqual(hashtag_plan(20), [("followforfollow", 20)])
        self.assertEqual(hashtag_plan(21), [
            ("followforfollow", 20), ("likeforlike", 1)
        ])
        self.assertEqual(hashtag_plan(45), [
            ("followforfollow", 20), ("likeforlike", 20),
            ("likeforfollow", 5)
        ])
        self.assertEqual(hashtag_plan(100), [
            (tag, 20) for tag in HASHTAGS
        ])

    def test_current_two_post_test_does_not_switch(self):
        status, report, search, _, engage = self.execute(self.args(count=2))
        self.assertEqual(status, 0)
        self.assertEqual(report["confirmed"], 2)
        self.assertEqual(report["follows_confirmed"], 2)
        self.assertEqual([c.args[1] for c in search.call_args_list], [HASHTAGS[0]])
        self.assertEqual(engage.call_count, 2)

    def test_first_switch_happens_at_21(self):
        status, report, search, _, engage = self.execute(self.args(count=21))
        self.assertEqual(status, 0)
        self.assertEqual(report["confirmed"], 21)
        self.assertEqual(report["follows_confirmed"], 21)
        self.assertEqual([c.args[1] for c in search.call_args_list], list(HASHTAGS[:2]))
        self.assertEqual([b["confirmed"] for b in report["batches"]], [20, 1])
        self.assertEqual([c.args[2] for c in engage.call_args_list[:20]], [HASHTAGS[0]] * 20)
        self.assertEqual(engage.call_args_list[20].args[2], HASHTAGS[1])

    def test_full_five_hashtags(self):
        status, report, search, _, engage = self.execute(self.args(count=100))
        self.assertEqual(status, 0)
        self.assertEqual(report["confirmed"], 100)
        self.assertEqual(report["follows_confirmed"], 100)
        self.assertEqual([b["confirmed"] for b in report["batches"]], [20] * 5)
        self.assertEqual([c.args[1] for c in search.call_args_list], list(HASHTAGS))
        self.assertEqual(engage.call_count, 100)

    def test_preview_all_five_hashtags_has_no_writes(self):
        status, report, search, make, engage = self.execute(
            self.args(mode="preview", count=100)
        )
        self.assertEqual(status, 0)
        self.assertEqual(report["confirmed"], 0)
        self.assertEqual(len(report["results"]), 100)
        self.assertEqual(search.call_count, 5)
        make.assert_not_called()
        engage.assert_not_called()

    def test_shortage_stops_without_starting_next_hashtag(self):
        self.posts[HASHTAGS[0]] = self.posts[HASHTAGS[0]][:19]
        status, report, search, _, engage = self.execute(self.args(count=21))
        self.assertEqual(status, 2)
        self.assertEqual(report["confirmed"], 19)
        self.assertEqual(engage.call_count, 19)
        self.assertEqual(search.call_count, 1)
        self.assertIn("Next hashtag not started", report["error"])

    def test_already_liked_post_does_not_count_toward_switch(self):
        self.media[self.posts[HASHTAGS[0]][0]["code"]].has_liked = True
        status, report, _, _, engage = self.execute(self.args(count=21))
        self.assertEqual(status, 0)
        self.assertEqual(report["already_liked"], 1)
        self.assertEqual([b["confirmed"] for b in report["batches"]], [20, 1])
        self.assertEqual(engage.call_count, 21)

    def test_unconfirmed_action_stops_without_retry_or_switch(self):
        status, report, search, _, engage = self.execute(
            self.args(count=21),
            outcome={"follow": "confirmed", "like": "uncertain", "error": "timeout"},
        )
        self.assertEqual(status, 2)
        self.assertEqual(report["confirmed"], 0)
        self.assertEqual(report["follows_confirmed"], 1)
        self.assertEqual(search.call_count, 1)
        self.assertEqual(engage.call_count, 1)

    def test_invalid_count_rejected_before_network(self):
        for count in (0, 101):
            with self.subTest(count=count), \
                 patch("scripts.like_posts_variable.private_session_path") as session, \
                 patch("scripts.like_posts_variable.save_report"):
                self.assertEqual(run(self.args(count=count)), 2)
                session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
