"""Offline tests for timezone-aware Toronto primary and backup crons."""
from datetime import datetime, timedelta
import unittest
from zoneinfo import ZoneInfo

from scripts.instagram_schedule import (
    BACKUP_MINUTE, MANUAL_SLOTS, PRIMARY_MINUTE, SLOTS, select_session
)

TORONTO = ZoneInfo("America/Toronto")


class ScheduleTests(unittest.TestCase):
    def test_all_five_times_one_tag_each(self):
        self.assertEqual(list(SLOTS), [5, 9, 15, 18, 22])
        self.assertEqual(
            [tag for _, tag in SLOTS.values()],
            ["followforfollow", "likeforlike", "likeforfollow",
             "follow4follow", "like4like"],
        )
        self.assertEqual((PRIMARY_MINUTE, BACKUP_MINUTE), (11, 36))

    def test_winter_est_primary_and_backup_correct(self):
        for hour, (slot, hashtag) in SLOTS.items():
            for minute, expected_kind in ((11, "primary"), (36, "backup")):
                with self.subTest(hour=hour, minute=minute):
                    now = datetime(2026, 1, 15, hour, minute, tzinfo=TORONTO)
                    decision = select_session(
                        "schedule", f"{minute} {hour} * * *", now=now
                    )
                    self.assertTrue(decision["run"], decision)
                    self.assertEqual(decision["slot"], slot)
                    self.assertEqual(decision["hashtag"], hashtag)
                    self.assertEqual(decision["kind"], expected_kind)
                    self.assertEqual(decision["local_date"], "2026-01-15")

    def test_summer_edt_primary_and_backup_correct(self):
        for hour, (slot, hashtag) in SLOTS.items():
            for minute in (11, 36):
                with self.subTest(hour=hour, minute=minute):
                    now = datetime(2026, 7, 15, hour, minute, tzinfo=TORONTO)
                    decision = select_session(
                        "schedule", f"{minute} {hour} * * *", now=now
                    )
                    self.assertTrue(decision["run"], decision)
                    self.assertEqual(decision["slot"], slot)
                    self.assertEqual(decision["local_date"], "2026-07-15")

    def test_delayed_trigger_still_selects_correct_slot(self):
        now = datetime(2026, 7, 15, 23, 2, tzinfo=TORONTO)
        decision = select_session("schedule", "36 22 * * *", now=now)
        self.assertTrue(decision["run"])
        self.assertEqual(decision["slot"], "10pm")
        self.assertEqual(decision["local_date"], "2026-07-15")

    def test_more_than_two_hours_late_does_not_run(self):
        now = datetime(2026, 7, 16, 0, 44, tzinfo=TORONTO)
        decision = select_session("schedule", "36 22 * * *", now=now)
        self.assertFalse(decision["run"])
        self.assertEqual(decision["reason"], "stale_or_early_trigger")

    def test_unexpected_cron_does_not_start_instagram(self):
        for event, cron in [
            ("push", "11 5 * * *"),
            ("schedule", "0 5 * * *"),
            ("schedule", "11 6 * * *"),
            ("schedule", "36 17 * * *"),
            ("schedule", "11 5 * * 1"),
        ]:
            with self.subTest(event=event, cron=cron):
                self.assertFalse(select_session(event, cron)["run"])

    def test_manual_slot_mapping(self):
        for slot, (hour, hashtag) in MANUAL_SLOTS.items():
            with self.subTest(slot=slot):
                d = select_session(
                    "workflow_dispatch", manual_slot=slot,
                    now=datetime(2026, 11, 7, 21, 0, tzinfo=TORONTO),
                )
                self.assertTrue(d["run"])
                self.assertEqual(d["hour"], hour)
                self.assertEqual(d["hashtag"], hashtag)
                self.assertEqual(d["kind"], "manual")

    def test_manual_invalid_slot_raises(self):
        with self.assertRaises(ValueError):
            select_session("workflow_dispatch", manual_slot="7pm")


if __name__ == "__main__":
    unittest.main()
