import unittest
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from datetime import datetime, timezone
from scripts.apify_recent_verified import normalize_rows, hashtag_in_caption, parse_timestamp, apify_recent_request


class RecentApifyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 7, 2, 0, tzinfo=timezone.utc)
        self.good = {
            "rowType": "post", "status": "SUCCESS",
            "queryHashtag": "follow_for_follow",
            "timestamp": "2026-11-07T01:00:00Z",
            "caption": "Hello #follow_for_follow and friends",
            "url": "https://www.instagram.com/reel/XYZ987/",
            "owner": {"username": "public.creator"},
        }

    def test_exact_tag(self):
        self.assertTrue(hashtag_in_caption("#follow_for_follow!", "follow_for_follow"))
        for bad in ("#followforfollow", "#follow_for_follow99", "follow_for_follow", "#follow_for_follow_more"):
            self.assertFalse(hashtag_in_caption(bad, "follow_for_follow"))

    def test_verified_records(self):
        records, statuses, total = normalize_rows([self.good], "follow_for_follow", now=self.now)
        self.assertEqual(total, 1)
        self.assertEqual(statuses["SUCCESS"], 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["hours_ago"], 1.0)

    def test_no_unknown_timestamps_or_wrong_tags(self):
        rows = [
            {**self.good, "timestamp": None},
            {**self.good, "timestamp": "not a date"},
            {**self.good, "caption": "#followforfollow"},
            {**self.good, "queryHashtag": "another"},
            {**self.good, "url": "https://evil.example/reel/xyz"},
            {**self.good, "timestamp": "2026-11-04T01:00:00Z"},
        ]
        records, _, _ = normalize_rows(rows, "follow_for_follow", now=self.now)
        self.assertFalse(records)

    def test_sort_dedup_and_error_row(self):
        earlier = {**self.good, "timestamp": "2026-11-07T00:10:00Z", "url": "https://www.instagram.com/p/GOOD123/"}
        records, statuses, total = normalize_rows(
            [earlier, self.good, self.good, {"rowType": "error", "status": "PARTIAL_RESULT"}],
            "follow_for_follow", now=self.now)
        self.assertEqual(len(records), 2)
        self.assertTrue(records[0]["url"].endswith("XYZ987/"))
        self.assertEqual(statuses["PARTIAL_RESULT"], 1)
        self.assertEqual(total, 4)

    def test_timezone_required(self):
        self.assertIsNone(parse_timestamp("2026-11-07T01:00:00"))

class ContractTests(unittest.TestCase):
    def test_request_exact_recent_and_charge_cap(self):
        class Response:
            status = 201
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, max_bytes): return b'[]'
        with patch("urllib.request.urlopen", return_value=Response()) as request_mock:
            rows=apify_recent_request("dummy-apify-token","follow_for_follow",20,0.10)
        self.assertEqual(rows,[])
        request=request_mock.call_args.args[0]
        url=urlsplit(request.full_url)
        self.assertIn("coregent~instagram-hashtag-scraper",url.path)
        self.assertEqual(parse_qs(url.query)["maxTotalChargeUsd"],["0.10"])
        body=json.loads(request.data)
        self.assertEqual(body["hashtags"],["follow_for_follow"])
        self.assertEqual(body["sort"],"RECENT")
        self.assertEqual(body["postsNewerThan"],"24 hours")
        self.assertFalse(body["includeMediaUrls"])
        self.assertEqual(request.get_method(),"POST")
