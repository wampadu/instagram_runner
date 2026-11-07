"""Unit tests of exact hashtag and recency verification."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from scripts.aiograpi_discover_posts import caption_contains_hashtag, media_age_hours, verified_post, discover

class MatchingTests(unittest.TestCase):
    def test_whole_hashtag_not_prefix(self):
        self.assertTrue(caption_contains_hashtag("Here is #Toronto, yay", "toronto"))
        self.assertFalse(caption_contains_hashtag("#torontolife", "toronto"))
        self.assertFalse(caption_contains_hashtag("toronto", "toronto"))
        self.assertFalse(caption_contains_hashtag("#toronto123", "toronto"))

    def test_age(self):
        now=datetime(2026,11,7,0,0,tzinfo=timezone.utc)
        self.assertAlmostEqual(media_age_hours(now-timedelta(hours=2),now),2)
        self.assertIsNone(media_age_hours(None,now))

    def test_record_fresh_and_valid(self):
        now=datetime(2026,11,7,0,0,tzinfo=timezone.utc)
        media=SimpleNamespace(code="ABC123",taken_at=now-timedelta(hours=2),caption_text="hello #toronto",user=SimpleNamespace(username="tester"))
        record=verified_post(media,"toronto",48,now)
        self.assertEqual(record["url"],"https://www.instagram.com/p/ABC123/")
        self.assertIsNone(verified_post(media,"toronto",1,now))
        media.caption_text="not the tag"
        self.assertIsNone(verified_post(media,"toronto",48,now))

class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_deduplicates_users_and_posts(self):
        users=[SimpleNamespace(pk=1,is_private=False),SimpleNamespace(pk=1,is_private=False),SimpleNamespace(pk=2,is_private=True)]
        now=datetime.now(timezone.utc)
        media=SimpleNamespace(code="ABC123",taken_at=now-timedelta(hours=2),caption_text="#toronto",user=SimpleNamespace(username="tester"))
        cl=SimpleNamespace(search_users=AsyncMock(return_value=users),user_medias_v1=AsyncMock(return_value=[media,media]))
        result=await discover(cl,"toronto",3,5,48)
        self.assertEqual(result["public_accounts_checked"],1)
        self.assertEqual(result["posts_inspected"],2)
        self.assertEqual(len(result["matches"]),1)
        cl.user_medias_v1.assert_awaited_once_with(1,amount=5)
