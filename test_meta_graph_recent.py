"""No-network contract and data-validation tests for official Meta Graph API."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from scripts.meta_graph_recent import (
    clean_media, exact_hashtag, get_recent_media, list_linked_instagram_accounts, graph_get
)


class MetaGraphTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.post = {
            "id": "123456789",
            "caption": "Hello #follow_for_follow",
            "permalink": "https://www.instagram.com/p/ABC123/",
            "timestamp": (self.now - timedelta(hours=1)).isoformat(),
            "media_type": "IMAGE",
        }

    def test_exact_hashtag_not_prefix(self):
        self.assertTrue(exact_hashtag("hi #follow_for_follow!", "follow_for_follow"))
        self.assertFalse(exact_hashtag("#followforfollow", "follow_for_follow"))
        self.assertFalse(exact_hashtag("#follow_for_follow99", "follow_for_follow"))

    def test_recent_filter_and_time(self):
        result = clean_media(self.post, "follow_for_follow", self.now)
        self.assertEqual(result["url"], "https://www.instagram.com/p/ABC123/")
        self.assertEqual(result["age_hours"], 1)
        self.assertIsNone(clean_media({**self.post, "timestamp": (self.now - timedelta(hours=26)).isoformat()}, "follow_for_follow", self.now))
        self.assertIsNone(clean_media({**self.post, "timestamp": "2026-11-07T01:00:00"}, "follow_for_follow", self.now))
        self.assertIsNone(clean_media({**self.post, "permalink": "https://evil.example/post"}, "follow_for_follow", self.now))

    @patch("scripts.meta_graph_recent.graph_get")
    def test_page_linked_account_discovery(self, get):
        get.return_value = {"data": [
            {"id": "10", "name": "My Page",
             "instagram_business_account": {"id": "17800000001", "username": "follow_back_aswell"}},
            {"id": "11", "name": "Unlinked Page"},
        ]}
        accounts = list_linked_instagram_accounts("fake_token")
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["ig_username"], "follow_back_aswell")
        self.assertEqual(get.call_args.args[0], "/me/accounts")

    @patch("scripts.meta_graph_recent.graph_get")
    def test_hashtag_endpoint_contract(self, get):
        get.side_effect = [
            {"data": [{"id": "17840000000000000"}]},
            {"data": [self.post, self.post, {"caption": "#another"}],
             "paging": {"next": "https://graph.facebook.com/more"}},
        ]
        rows, total, more, error = get_recent_media("fake_token", "17800000001", "follow_for_follow")
        self.assertIsNone(error)
        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 1)
        self.assertTrue(more)
        self.assertEqual(get.call_args_list[0].args[0], "/ig_hashtag_search")
        self.assertEqual(get.call_args_list[0].args[2]["q"], "follow_for_follow")
        self.assertEqual(get.call_args_list[1].args[0], "/17840000000000000/recent_media")
        self.assertEqual(get.call_args_list[1].args[2]["limit"], 50)
        self.assertNotIn("username", get.call_args_list[1].args[2]["fields"])

    @patch("urllib.request.urlopen")
    def test_authorization_not_in_query_parameters(self, request):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *exc): pass
            def read(self, max_bytes): return b'{"data":[]}'
        request.return_value = Response()
        graph_get("/me/accounts", "secret_test_token", {"fields": "id"})
        req = request.call_args.args[0]
        self.assertNotIn("secret_test_token", req.full_url)
        self.assertEqual(req.get_header("Authorization"), "Bearer secret_test_token")


if __name__ == "__main__":
    unittest.main()
