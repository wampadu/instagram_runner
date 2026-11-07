import unittest
from datetime import datetime,timezone
from scripts.hashtag_recent_provider import exact_tag,iso_datetime,verified_posts

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,7,2,0,tzinfo=timezone.utc)
        self.post={"createdAt":"2026-11-07T01:00:00Z","caption":"testing #follow_for_follow","url":"https://www.instagram.com/p/ABC123/","owner":{"username":"creator"}}

    def test_exact_tag(self):
        self.assertTrue(exact_tag("#follow_for_follow", "follow_for_follow"))
        self.assertFalse(exact_tag("#followforfollow", "follow_for_follow"))
        self.assertFalse(exact_tag("#follow_for_follow2", "follow_for_follow"))
        self.assertFalse(exact_tag(None, "follow_for_follow"))

    def test_socialfetch_recent_and_filter(self):
        posts=[dict(self.post),{**self.post,"createdAt":"2026-11-04T01:00:00Z","url":"https://www.instagram.com/p/OLD/"},{**self.post,"caption":"#another","url":"https://www.instagram.com/p/OTHER/"}]
        result,n=verified_posts({"data":{"lookupStatus":"found","media":posts}},"socialfetch","follow_for_follow",48,self.now)
        self.assertEqual(n,3)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0][3],"https://www.instagram.com/p/ABC123/")

    def test_openhandle(self):
        result,n=verified_posts({"data":[self.post,self.post]},"openhandle","follow_for_follow",48,self.now)
        self.assertEqual(len(result),1)
        self.assertEqual(n,2)

    def test_url_and_age_must_be_valid(self):
        result,_=verified_posts({"data":[{**self.post,"url":"https://example.com/phishing"}, {**self.post,"createdAt":"2026-11-08T01:00:00Z"}]},"openhandle","follow_for_follow",48,self.now)
        self.assertFalse(result)

    def test_timestamp(self):
        self.assertEqual(iso_datetime("2026-11-07T01:00:00Z").hour,1)
        self.assertIsNone(iso_datetime("garbage"))
