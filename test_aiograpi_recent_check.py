"""Offline checks for read-only recent hashtag retrieval."""
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from scripts.aiograpi_recent_check import age_in_hours, fetch_recent


class RecentMediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_not_top(self):
        media = [SimpleNamespace(taken_at=datetime(2026, 1, 1, tzinfo=timezone.utc))]
        client = SimpleNamespace(
            hashtag_medias_recent=AsyncMock(return_value=media),
            hashtag_medias_top=AsyncMock(),
            media_like=AsyncMock(),
            user_follow=AsyncMock(),
        )
        result = await fetch_recent(client, "toronto", amount=8)
        self.assertEqual(result, media)
        client.hashtag_medias_recent.assert_awaited_once_with("toronto", amount=8)
        client.hashtag_medias_top.assert_not_awaited()
        client.media_like.assert_not_awaited()
        client.user_follow.assert_not_awaited()

    async def test_age_utc(self):
        now = datetime(2026, 11, 7, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(age_in_hours(now - timedelta(hours=3), now), 3.0)
        self.assertEqual(age_in_hours((now - timedelta(hours=3)).replace(tzinfo=None), now), 3.0)
        self.assertIsNone(age_in_hours(None, now))
