"""Offline regression tests of read-only scheduled-run deduplication."""
from datetime import datetime, timezone
import unittest

from scripts.instagram_run_guard import same_slot, should_execute


def fake(run_id, utc_date, event="schedule"):
    return {"id": run_id, "event": event, "created_at": utc_date}


class GuardTests(unittest.TestCase):
    def test_backup_skips_when_primary_exists(self):
        runs = [
            fake(101, "2026-11-08T10:11:00Z"),
            fake(102, "2026-11-08T10:36:00Z"),
        ]
        allowed, elected = should_execute(102, "5am", "2026-11-08", runs)
        self.assertFalse(allowed)
        self.assertEqual(elected, 101)
        primary_allowed, elected = should_execute(
            101, "5am", "2026-11-08", runs
        )
        self.assertTrue(primary_allowed)
        self.assertEqual(elected, 101)

    def test_backup_executes_when_first_schedule_was_dropped(self):
        runs = [fake(102, "2026-11-08T10:36:00Z")]
        allowed, elected = should_execute(102, "5am", "2026-11-08", runs)
        self.assertTrue(allowed)
        self.assertEqual(elected, 102)

    def test_same_local_date_including_ten_pm_next_utc_date(self):
        self.assertTrue(same_slot(
            fake(103, "2026-11-08T03:11:00Z"), "10pm", "2026-11-07"
        ))
        self.assertFalse(same_slot(
            fake(104, "2026-11-09T03:11:00Z"), "10pm", "2026-11-07"
        ))

    def test_time_change_summer_edt(self):
        self.assertTrue(same_slot(
            fake(104, "2026-07-16T02:36:00Z"), "10pm", "2026-07-15"
        ))
        self.assertTrue(same_slot(
            fake(105, "2026-07-15T09:11:00Z"), "5am", "2026-07-15"
        ))

    def test_other_slot_and_manual_runs_do_not_block(self):
        runs = [
            fake(101, "2026-11-08T10:11:00Z"),  # 5 AM
            fake(103, "2026-11-08T14:11:00Z", event="workflow_dispatch"),
            fake(104, "2026-11-08T14:36:00Z"),  # 9 AM
        ]
        allowed, elected = should_execute(104, "9am", "2026-11-08", runs)
        self.assertTrue(allowed)
        self.assertEqual(elected, 104)

    def test_duplicate_after_failed_primary_still_skips_retry(self):
        runs = [
            {**fake(101, "2026-11-08T23:11:00Z"), "conclusion": "failure"},
            fake(102, "2026-11-08T23:36:00Z"),
        ]
        allowed, elected = should_execute(102, "6pm", "2026-11-08", runs)
        self.assertFalse(allowed)
        self.assertEqual(elected, 101)

    def test_fail_closed_when_current_run_missing_from_api(self):
        runs = [fake(101, "2026-11-08T10:11:00Z")]
        with self.assertRaises(ValueError):
            should_execute(102, "5am", "2026-11-08", runs)

    def test_not_a_schedule_and_out_of_window_ignored(self):
        self.assertFalse(same_slot(
            fake(200, "2026-11-08T10:11:00Z", event="workflow_dispatch"),
            "5am", "2026-11-08"
        ))
        self.assertFalse(same_slot(
            fake(201, "2026-11-08T14:11:00Z"), "5am", "2026-11-08"
        ))


if __name__ == "__main__":
    unittest.main()
