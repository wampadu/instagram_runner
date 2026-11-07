"""Offline pagination and exact-tag verification tests; no live requests."""
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from scripts.instagram_web_recent import retrieve, parse_page

class WebRecentTests(unittest.TestCase):
    def test_first_page_and_dedup(self):
        media={"code":"AAA11","caption":{"text":"#follow_for_follow"},
               "user":{"username":"example"},
               "taken_at":(datetime.now(timezone.utc)-timedelta(minutes=15)).timestamp()}
        def body(page):
            return {"sections":[{"layout_content":{"medias":[{"media":media}]}}],
                    "more_available":False}
        with patch("scripts.instagram_web_recent.request_once", return_value={"status":"200","data":body(1)}):
            items,pages=retrieve(object(),"follow_for_follow",2)
        self.assertEqual(len(items),1)
        self.assertEqual(len(pages),1)
        self.assertLess(items[0]["age"],1)

    def test_cursor_consumed_and_no_repeats(self):
        now=datetime.now(timezone.utc)
        def media(code,hrs):
            return {"code":code,"caption":{"text":"#follow_for_follow"},
                    "user":{"username":"example"},
                    "taken_at":(now-timedelta(hours=hrs)).timestamp()}
        one={"sections":[{"layout_content":{"medias":[{"media":media("AAAA",1)}]}}],
             "more_available":True,"next_max_id":"cursor1","next_media_ids":["one"]}
        two={"sections":[{"layout_content":{"medias":[{"media":media("BBBB",2)}]}}],
             "more_available":False}
        with patch("scripts.instagram_web_recent.request_once",side_effect=[
                {"status":"200","data":one},{"status":"200","data":two}]) as mock:
            posts,pages=retrieve(object(),"follow_for_follow",3)
        self.assertEqual(len(posts),2)
        self.assertEqual([x["code"] for x in posts],["AAAA","BBBB"])
        self.assertEqual(mock.call_args_list[1].kwargs["data"]["max_id"],"cursor1")
        self.assertEqual(len(pages),2)

    def test_no_fallback_on_block(self):
        with patch("scripts.instagram_web_recent.request_once",return_value={"status":"403","data":None}):
            posts,pages=retrieve(object(),"follow_for_follow",3)
        self.assertEqual(posts,[])
        self.assertEqual(len(pages),1)
