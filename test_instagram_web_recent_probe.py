"""Offline structural tests of the web endpoint parser."""
import unittest
from datetime import datetime,timezone,timedelta
from scripts.instagram_web_recent_probe import verified, media_from_container


class WebProbeTests(unittest.TestCase):
    def test_exact_hashtag(self):
        media={"caption":{"text":"Hello #follow_for_follow!"},"code":"AbC123",
               "taken_at":(datetime.now(timezone.utc)-timedelta(hours=1)).timestamp(),
               "user":{"username":"sampleuser"}}
        self.assertIsNotNone(verified(media,"follow_for_follow"))
        media["caption"]["text"]="#followforfollow"
        self.assertIsNone(verified(media,"follow_for_follow"))
        media["caption"]["text"]="#follow_for_follow_extended"
        self.assertIsNone(verified(media,"follow_for_follow"))

    def test_nested_recent_sections(self):
        m={"caption":{"text":"#follow_for_follow"},"code":"Abc",
           "taken_at":(datetime.now(timezone.utc)-timedelta(minutes=30)).timestamp()}
        data={"sections":[{"layout_content":{"medias":[{"media":m}]}}]}
        self.assertEqual(media_from_container(data),[m])
        clips={"sectional_items":[{"layout_content":{"one_by_two_item":{"clips":{"items":[{"media":m}]}}}}]}
        self.assertEqual(media_from_container(clips),[m])
