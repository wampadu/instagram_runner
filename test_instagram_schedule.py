"""Offline validation of five 20-pair local Toronto Instagram sessions."""
from datetime import datetime, timedelta, timezone
import unittest

from scripts.instagram_schedule import (
    MANUAL_SLOTS, SLOTS, UTC_CRON_HOURS, select_session,
)


class ScheduleTests(unittest.TestCase):
    SUMMER = {5: 9, 9: 13, 15: 19, 18: 22, 22: 2}
    WINTER = {5: 10, 9: 14, 15: 20, 18: 23, 22: 3}

    def test_five_times_and_unique_hashtags(self):
        self.assertEqual(list(SLOTS), [5, 9, 15, 18, 22])
        self.assertEqual(
            [hashtag for _, hashtag in SLOTS.values()],
            ["followforfollow", "likeforlike", "likeforfollow",
             "follow4follow", "like4like"],
        )
        self.assertEqual(len(UTC_CRON_HOURS), 10)

    def test_summer_ed_toronto_hours(self):
        for hour, utc_hour in self.SUMMER.items():
            with self.subTest(toronto_hour=hour):
                # 22:00 local is at 02:00 UTC the following day.
                day = 2 if hour == 22 else 1
                now = datetime(2026, 7, day, utc_hour, tzinfo=timezone.utc)
                d = select_session("schedule", f"0 {utc_hour} * * *", now_utc=now)
                self.assertTrue(d["run"], d)
                self.assertEqual(d["hour"], hour)
                self.assertEqual(d["hashtag"], SLOTS[hour][1])
                self.assertEqual(d["local_timezone"], "EDT")

    def test_winter_est_toronto_hours(self):
        for hour, utc_hour in self.WINTER.items():
            with self.subTest(toronto_hour=hour):
                day = 16 if hour == 22 else 15
                now = datetime(2026, 1, day, utc_hour, tzinfo=timezone.utc)
                d = select_session("schedule", f"0 {utc_hour} * * *", now_utc=now)
                self.assertTrue(d["run"], d)
                self.assertEqual(d["hour"], hour)
                self.assertEqual(d["hashtag"], SLOTS[hour][1])
                self.assertEqual(d["local_timezone"], "EST")

    def test_incorrect_dst_crons_skip(self):
        # Winter cron triggers are one local hour too late in summer.
        for hour in self.WINTER.values():
            day = 2 if hour == 3 else 1
            now = datetime(2026, 7, day, hour, tzinfo=timezone.utc)
            result = select_session("schedule", f"0 {hour} * * *", now_utc=now)
            self.assertFalse(result["run"], result)
            self.assertEqual(result["reason"], "wrong_dst_hour")

        # Summer cron triggers are one local hour too early in winter.
        for hour in self.SUMMER.values():
            day = 16 if hour == 2 else 15
            now = datetime(2026, 1, day, hour, tzinfo=timezone.utc)
            result = select_session("schedule", f"0 {hour} * * *", now_utc=now)
            self.assertFalse(result["run"], result)
            self.assertEqual(result["reason"], "wrong_dst_hour")

    def test_manual_dispatch_chooses_exact_slot(self):
        for slot, (hour, tag) in MANUAL_SLOTS.items():
            with self.subTest(slot=slot):
                d = select_session("workflow_dispatch", manual_slot=slot)
                self.assertTrue(d["run"])
                self.assertEqual(d["hour"], hour)
                self.assertEqual(d["hashtag"], tag)

    def test_unrecognized_trigger_never_runs(self):
        for event, cron in [
            ("push", "0 9 * * *"),
            ("schedule", "1 9 * * *"),
            ("schedule", "0 16 * * *"),
        ]:
            with self.subTest(event=event, cron=cron):
                self.assertFalse(select_session(event, cron)["run"])

    def test_very_late_schedule_skips_instead_of_running_off_cycle(self):
        now = datetime(2026, 7, 1, 16, 10, tzinfo=timezone.utc)
        d = select_session("schedule", "0 9 * * *", now_utc=now)
        self.assertFalse(d["run"])
        self.assertEqual(d["reason"], "stale_cron_event")

    def test_reject_invalid_manual_choice(self):
        with self.assertRaises(ValueError):
            select_session("workflow_dispatch", manual_slot="3am")


if __name__ == "__main__":
    unittest.main()
