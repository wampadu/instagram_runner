"""Regressions for actual GitHub-scheduled delays across Toronto EST/EDT."""
from datetime import datetime, timezone
import unittest
from zoneinfo import ZoneInfo

from scripts.instagram_schedule import (
    BACKUP_MINUTE, MANUAL_SLOTS, PRIMARY_MINUTE,
    SLOTS, occurrence_for_cron, select_session,
)

TORONTO = ZoneInfo("America/Toronto")


class ScheduleTests(unittest.TestCase):
    def test_all_five_slots_one_hashtag(self):
        self.assertEqual(list(SLOTS), [5, 9, 15, 18, 22])
        self.assertEqual(
            [tag for _, tag in SLOTS.values()],
            ["followforfollow", "likeforlike", "likeforfollow",
             "follow4follow", "like4like"],
        )
        self.assertEqual((PRIMARY_MINUTE, BACKUP_MINUTE), (11, 36))

    def test_normal_trigger_primary_and_backup_est_and_edt(self):
        for month in (1, 7):
            for hour, (slot, hashtag) in SLOTS.items():
                for minute, expected_kind in ((11, "primary"), (36, "backup")):
                    with self.subTest(month=month, hour=hour, minute=minute):
                        now = datetime(2026, month, 15, hour, minute,
                                       tzinfo=TORONTO)
                        d = select_session(
                            "schedule", f"{minute} {hour} * * *", now=now
                        )
                        self.assertTrue(d["run"])
                        self.assertEqual(d["slot"], slot)
                        self.assertEqual(d["hashtag"], hashtag)
                        self.assertEqual(d["kind"], expected_kind)
                        self.assertEqual(d["local_date"], now.strftime("%Y-%m-%d"))
                        self.assertEqual(d["delay_minutes"], 0)

    def test_real_delayed_github_runs_previous_silently_skipped(self):
        # Every one of these is taken from actual GitHub run creation times.
        samples = [
            ("11 5 * * *", "2026-11-08T16:38:01Z", "5am", "2026-11-08"),
            ("36 5 * * *", "2026-11-08T16:46:30Z", "5am", "2026-11-08"),
            ("11 9 * * *", "2026-11-08T18:49:08Z", "9am", "2026-11-08"),
            ("36 9 * * *", "2026-11-08T19:03:31Z", "9am", "2026-11-08"),
            ("11 15 * * *", "2026-11-08T23:38:53Z", "3pm", "2026-11-08"),
            ("36 15 * * *", "2026-11-08T23:58:00Z", "3pm", "2026-11-08"),
            ("11 18 * * *", "2026-11-09T02:37:16Z", "6pm", "2026-11-08"),
            ("36 18 * * *", "2026-11-09T02:56:45Z", "6pm", "2026-11-08"),
            ("11 22 * * *", "2026-11-09T11:23:19Z", "10pm", "2026-11-08"),
            ("36 22 * * *", "2026-11-09T12:04:26Z", "10pm", "2026-11-08"),
            ("36 22 * * *", "2026-11-08T10:44:31Z", "10pm", "2026-11-07"),
        ]
        for cron, iso, slot, date in samples:
            with self.subTest(cron=cron, iso=iso):
                now = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                d = select_session("schedule", cron, now=now)
                self.assertTrue(d["run"], d)
                self.assertEqual(d["slot"], slot)
                self.assertEqual(d["local_date"], date)
                self.assertGreater(d["delay_minutes"], 0)

    def test_scheduled_date_is_prior_day_after_midnight(self):
        at = datetime(2026, 11, 9, 6, 14, tzinfo=TORONTO)
        d = select_session("schedule", "11 22 * * *", now=at)
        self.assertEqual(d["local_date"], "2026-11-08")
        self.assertEqual(d["hashtag"], "like4like")

    def test_no_unknown_cron_gives_silent_success(self):
        for cron in ("0 5 * * *", "11 6 * * *", "36 17 * * *",
                     "11 5 * * 1", ""):
            with self.subTest(cron=cron):
                with self.assertRaises(ValueError):
                    select_session("schedule", cron)

    def test_other_events_cannot_be_scheduled_runs(self):
        d = select_session("push", "11 5 * * *")
        self.assertFalse(d["run"])

    def test_manual_dispatch_chooses_exact_slot(self):
        for slot, (hour, tag) in MANUAL_SLOTS.items():
            with self.subTest(slot=slot):
                d = select_session("workflow_dispatch", manual_slot=slot)
                self.assertTrue(d["run"])
                self.assertEqual(d["hour"], hour)
                self.assertEqual(d["hashtag"], tag)
                self.assertEqual(d["kind"], "manual")

    def test_reject_invalid_manual_choice(self):
        with self.assertRaises(ValueError):
            select_session("workflow_dispatch", manual_slot="3am")


if __name__ == "__main__":
    unittest.main()
