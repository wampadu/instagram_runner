"""Offline tests for the manually-triggered GitHub follow+like workflow."""
import contextlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
import json
import tempfile
import unittest

from scripts.manual_instagram_actions import (
    SafeStop, check_target_media, contains_tag, engagement, markdown_report,
    post_code_from_url, private_session_path, run,
)


class ManualWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.media=NS(
            code="ABC123",
            id="123456789_987654321",
            taken_at=datetime.now(timezone.utc)-timedelta(hours=2),
            caption_text="Great! #follow_for_follow",
            user=NS(pk="987654321",username="public.author",is_private=False),
            has_liked=False,
        )
        self.client=NS(
            user_id="11223344",
            media_pk_from_code=MagicMock(return_value="123456789"),
            media_info=MagicMock(return_value=self.media),
            user_friendship_v1=MagicMock(return_value=NS(following=False,outgoing_request=False)),
            user_follow=MagicMock(return_value=True),
            media_like=MagicMock(return_value=True),
        )

    def test_hashtag_and_url_are_strict(self):
        self.assertTrue(contains_tag("Hello #follow_for_follow.", "follow_for_follow"))
        self.assertFalse(contains_tag("#followforfollow", "follow_for_follow"))
        self.assertFalse(contains_tag("#follow_for_follow99", "follow_for_follow"))
        self.assertEqual(post_code_from_url("https://www.instagram.com/p/ABC123/?igsh=test"),"ABC123")
        self.assertEqual(post_code_from_url("https://www.instagram.com/reel/ABC123/"),"ABC123")
        self.assertIsNone(post_code_from_url("https://instagram.evil.com/p/ABC123/"))
        self.assertIsNone(post_code_from_url("http://www.instagram.com/p/ABC123/"))

    def test_exact_one_follow_and_one_like(self):
        result=engagement(self.client,"ABC123","follow_for_follow",24,expected_user="public.author")
        self.assertEqual(result["follow"],"confirmed")
        self.assertEqual(result["like"],"confirmed")
        self.client.user_follow.assert_called_once_with("987654321")
        self.client.media_like.assert_called_once_with("123456789_987654321")

    def test_no_follow_when_already_following_but_like_still_works(self):
        self.client.user_friendship_v1.return_value=NS(following=True,outgoing_request=False)
        result=engagement(self.client,"ABC123","follow_for_follow",24)
        self.assertEqual(result["follow"],"already_following")
        self.assertEqual(result["like"],"confirmed")
        self.client.user_follow.assert_not_called()

    def test_already_liked_is_not_resent(self):
        self.media.has_liked=True
        result=engagement(self.client,"ABC123","follow_for_follow",24)
        self.assertEqual(result["like"],"already_liked")
        self.client.media_like.assert_not_called()

    def test_follow_unconfirmed_stops_like(self):
        self.client.user_follow.return_value=False
        result=engagement(self.client,"ABC123","follow_for_follow",24)
        self.assertEqual(result["follow"],"unconfirmed")
        self.assertEqual(result["like"],"not_attempted")
        self.client.media_like.assert_not_called()

    def test_follow_error_does_not_retry_or_like(self):
        self.client.user_follow.side_effect=TimeoutError("sensitive token")
        result=engagement(self.client,"ABC123","follow_for_follow",24)
        self.assertEqual(result["follow"],"uncertain")
        self.assertEqual(result["like"],"not_attempted")
        self.assertNotIn("sensitive token",repr(result))
        self.client.user_follow.assert_called_once()
        self.client.media_like.assert_not_called()

    def test_wrong_post_hashtag_username_age_are_rejected(self):
        for invalid in [
            {"caption_text":"#followforfollow"},
            {"user":NS(pk="987654321",username="another",is_private=False)},
            {"taken_at":datetime.now(timezone.utc)+timedelta(hours=1)},
        ]:
            saved={k:getattr(self.media,k) for k in invalid}
            for k,v in invalid.items():setattr(self.media,k,v)
            result=engagement(self.client,"ABC123","follow_for_follow",24,
                              expected_user="public.author")
            self.assertEqual(result["follow"],"not_attempted")
            self.assertEqual(result["like"],"not_attempted")
            self.client.user_follow.assert_not_called()
            self.client.media_like.assert_not_called()
            for k,v in saved.items():setattr(self.media,k,v)

    def test_older_valid_post_can_be_selected_for_one_manual_action(self):
        self.media.taken_at=datetime.now(timezone.utc)-timedelta(days=21)
        result=engagement(self.client,"ABC123","follow_for_follow")
        self.assertEqual(result["follow"],"confirmed")
        self.assertEqual(result["like"],"confirmed")
        self.client.user_follow.assert_called_once()
        self.client.media_like.assert_called_once()

    def test_self_follow_rejected(self):
        self.client.user_id="987654321"
        result=engagement(self.client,"ABC123","follow_for_follow",24)
        self.assertEqual(result["follow"],"not_attempted")
        self.client.user_follow.assert_not_called()

    def test_secret_validation_without_logging(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            "os.environ",{"IG_SESSION_JSON":json.dumps({"cookies":{"sessionid":"secret_session_token"}}),
                          "RUNNER_TEMP":folder},clear=False
        ):
            with private_session_path() as path:
                self.assertTrue(Path(path).exists())
                self.assertEqual(Path(path).stat().st_mode&0o777,0o600)
            self.assertFalse(Path(path).exists())

    def test_github_requires_secret_no_fallback_to_phone(self):
        with patch.dict("os.environ",{"GITHUB_ACTIONS":"true","IG_SESSION_JSON":"",
                                     "IG_SESSION_GZIP_B64":""},clear=False):
            with self.assertRaises(SafeStop):
                with private_session_path() as _:
                    pass

    def test_preview_never_loads_write_client(self):
        @contextlib.contextmanager
        def fake_session():
            yield Path("/tmp/fake-ig-private.json")
        args=NS(mode="preview",hashtag="follow_for_follow",hours=24,max_pages=1,
                confirm="",post_url="",output_dir="")
        with patch("scripts.manual_instagram_actions.private_session_path",fake_session), \
             patch("scripts.manual_instagram_actions.load_http",return_value=object()), \
             patch("scripts.manual_instagram_actions.retrieve",return_value=(
                 [{"code":"ABC123","username":"public.author","age":2}],[
                 {"http":"200","raw":1}])), \
             patch("scripts.manual_instagram_actions.make_client") as make, \
             patch("scripts.manual_instagram_actions.save_report") as save:
            self.assertEqual(run(args),0)
            make.assert_not_called()
            report=save.call_args.args[0]
            self.assertEqual(report["discovery"]["eligible"],1)
            self.assertIsNone(report["engagement"])

    def test_preview_keeps_older_posts_and_sorts_newest_first(self):
        @contextlib.contextmanager
        def fake_session():
            yield Path("/tmp/fake-ig-private.json")
        args=NS(mode="preview",hashtag="follow_for_follow",hours=24,max_pages=1,
                confirm="",post_url="",output_dir="")
        # Deliberately unsorted; Instagram's response order is not trusted.
        records=[
            {"code":"OLD","username":"olduser","age":24.1},
            {"code":"SECOND","username":"second","age":9.0},
            {"code":"NEW","username":"newest","age":0.25},
            {"code":"FIRST","username":"first","age":3.2},
            {"code":"NEGATIVE","username":"wrong","age":-1.0},
        ]
        with patch("scripts.manual_instagram_actions.private_session_path",fake_session), \
             patch("scripts.manual_instagram_actions.load_http",return_value=object()), \
             patch("scripts.manual_instagram_actions.retrieve",return_value=(
                 records,[{"http":"200","raw":len(records)}])), \
             patch("scripts.manual_instagram_actions.make_client") as make, \
             patch("scripts.manual_instagram_actions.save_report") as save:
            self.assertEqual(run(args),0)
            make.assert_not_called()
            report=save.call_args.args[0]
            self.assertEqual(report["discovery"]["eligible"],4)
            self.assertEqual([p["username"] for p in report["candidates"]],
                             ["newest","first","second","olduser"])

    def test_selects_newest_even_when_it_is_older_than_24_hours(self):
        @contextlib.contextmanager
        def fake_session():
            yield Path("/tmp/fake-ig-private.json")
        args=NS(mode="follow_like",hashtag="follow_for_follow",hours=24,max_pages=1,
                confirm="FOLLOW_AND_LIKE",post_url="",output_dir="")
        with patch("scripts.manual_instagram_actions.private_session_path",fake_session), \
             patch("scripts.manual_instagram_actions.load_http",return_value=object()), \
             patch("scripts.manual_instagram_actions.retrieve",return_value=(
                 [{"code":"OLD","username":"someuser","age":30}],[{"http":"200","raw":1}])), \
             patch("scripts.manual_instagram_actions.make_client",return_value=self.client) as make, \
             patch("scripts.manual_instagram_actions.engagement",return_value={"follow":"confirmed","like":"confirmed"}) as action, \
             patch("scripts.manual_instagram_actions.save_report") as save:
            self.assertEqual(run(args),0)
            make.assert_called_once()
            self.assertEqual(save.call_args.args[0]["candidates"][0]["age"],30)
            self.assertEqual(action.call_args.args[1],"OLD")


    def test_preview_includes_all_rows_even_more_than_fifteen(self):
        @contextlib.contextmanager
        def fake_session():
            yield Path("/tmp/fake-ig-private.json")
        args=NS(mode="preview",hashtag="follow_for_follow",max_pages=2,
                confirm="",post_url="",output_dir="")
        records=[
            {"code":f"CODE{i}", "username":f"account{i}", "age":float(100-i)}
            for i in range(40)
        ]
        with patch("scripts.manual_instagram_actions.private_session_path",fake_session), \
             patch("scripts.manual_instagram_actions.load_http",return_value=object()), \
             patch("scripts.manual_instagram_actions.retrieve",return_value=(records,[{"http":"200","raw":40}])), \
             patch("scripts.manual_instagram_actions.save_report") as save:
            self.assertEqual(run(args),0)
            report=save.call_args.args[0]
            self.assertEqual(len(report["candidates"]),40)
            self.assertEqual([x["age"] for x in report["candidates"]], sorted(x["age"] for x in records))
            self.assertEqual(markdown_report(report).count("[View post]"),40)


    def test_execute_requires_confirmation_before_session_or_writes(self):
        args=NS(mode="follow_like",hashtag="follow_for_follow",hours=24,max_pages=1,
                confirm="",post_url="",output_dir="")
        with patch("scripts.manual_instagram_actions.private_session_path") as secret, \
             patch("scripts.manual_instagram_actions.save_report") as save:
            self.assertEqual(run(args),2)
            secret.assert_not_called()
            self.assertIn("FOLLOW_AND_LIKE",save.call_args.args[0]["error"])


if __name__=="__main__":
    unittest.main()
