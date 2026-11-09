"""Offline guard tests with the exact delayed times from actual GitHub runs."""
import unittest

from scripts.instagram_run_guard import (
    RUN_TITLE_PREFIX, get_run_slot_and_date, same_slot, should_execute,
)


def fake(run_id, utc_date, cron="11 5 * * *", event="schedule"):
    return {
        "id": run_id, "event": event, "created_at": utc_date,
        "display_title": RUN_TITLE_PREFIX + cron,
    }


class GuardTests(unittest.TestCase):
    def test_backup_skips_when_primary_exists_even_hours_late(self):
        runs = [
            fake(42500881233, "2026-11-08T16:38:01Z", "11 5 * * *"),
            fake(42501592132, "2026-11-08T16:46:30Z", "36 5 * * *"),
        ]
        allowed, elected = should_execute(
            42501592132, "5am", "2026-11-08", runs
        )
        self.assertFalse(allowed)
        self.assertEqual(elected, 42500881233)
        allowed, elected = should_execute(
            42500881233, "5am", "2026-11-08", runs
        )
        self.assertTrue(allowed)

    def test_backup_runs_when_primary_never_created(self):
        runs = [fake(102, "2026-11-08T16:46:30Z", "36 5 * * *")]
        allowed, elected = should_execute(102, "5am", "2026-11-08", runs)
        self.assertTrue(allowed)
        self.assertEqual(elected, 102)

    def test_ten_pm_cron_delivered_next_morning(self):
        runs = [
            fake(42608643505, "2026-11-09T11:23:19Z", "11 22 * * *"),
            fake(42613975705, "2026-11-09T12:04:26Z", "36 22 * * *"),
        ]
        self.assertEqual(
            get_run_slot_and_date(runs[0]), ("10pm", "2026-11-08")
        )
        allowed, first = should_execute(
            42613975705, "10pm", "2026-11-08", runs
        )
        self.assertFalse(allowed)
        self.assertEqual(first, 42608643505)

    def test_five_slots_all_route_regardless_of_delay(self):
        examples = [
            ("11 5 * * *", "2026-11-08T16:38:01Z", "5am"),
            ("11 9 * * *", "2026-11-08T18:49:08Z", "9am"),
            ("11 15 * * *", "2026-11-08T23:38:53Z", "3pm"),
            ("11 18 * * *", "2026-11-09T02:37:16Z", "6pm"),
            ("11 22 * * *", "2026-11-09T11:23:19Z", "10pm"),
        ]
        for i, (cron, timestamp, slot) in enumerate(examples):
            with self.subTest(slot=slot):
                run = fake(100 + i, timestamp, cron)
                self.assertTrue(same_slot(run, slot, "2026-11-08"))
                allowed, elected = should_execute(
                    run["id"], slot, "2026-11-08", [run]
                )
                self.assertTrue(allowed)
                self.assertEqual(elected, run["id"])

    def test_different_toronto_dates_are_not_duplicates(self):
        previous = fake(101, "2026-11-08T10:44:31Z", "36 22 * * *")
        current = fake(102, "2026-11-09T11:23:19Z", "11 22 * * *")
        self.assertTrue(same_slot(previous, "10pm", "2026-11-07"))
        allowed, elected = should_execute(
            102, "10pm", "2026-11-08", [previous, current]
        )
        self.assertTrue(allowed)
        self.assertEqual(elected, 102)

    def test_summer_edt_date(self):
        run = fake(103, "2026-07-16T02:36:31Z", "36 22 * * *")
        self.assertTrue(same_slot(run, "10pm", "2026-07-15"))
        run2 = fake(104, "2026-07-15T09:11:09Z", "11 5 * * *")
        self.assertTrue(same_slot(run2, "5am", "2026-07-15"))

    def test_manual_runs_do_not_satisfy_schedule_dedupe(self):
        manual = fake(101, "2026-11-08T10:11:00Z",
                      event="workflow_dispatch")
        scheduled = fake(102, "2026-11-08T16:38:01Z")
        allowed, elected = should_execute(
            102, "5am", "2026-11-08", [manual, scheduled]
        )
        self.assertTrue(allowed)

    def test_earliest_scheduled_wins_even_if_failed(self):
        primary = {
            **fake(101, "2026-11-08T23:38:53Z", "11 15 * * *"),
            "conclusion": "failure",
        }
        backup = fake(102, "2026-11-08T23:58:00Z", "36 15 * * *")
        allowed, elected = should_execute(
            102, "3pm", "2026-11-08", [primary, backup]
        )
        self.assertFalse(allowed)
        self.assertEqual(elected, 101)

    def test_fail_closed_if_current_run_missing_or_unlabelled(self):
        with self.assertRaises(ValueError):
            should_execute(102, "5am", "2026-11-08", [
                fake(101, "2026-11-08T10:11:00Z")
            ])
        unlabelled = {
            **fake(102, "2026-11-08T16:38:01Z"),
            "display_title": "Instagram — Five Toronto Sessions",
        }
        with self.assertRaisesRegex(ValueError, "no matching scheduled cron"):
            should_execute(102, "5am", "2026-11-08", [unlabelled])

    def test_wrong_cron_does_not_sneak_into_same_slot(self):
        run = fake(102, "2026-11-08T16:38:01Z", "11 13 * * *")
        self.assertIsNone(get_run_slot_and_date(run))


if __name__ == "__main__":
    unittest.main()
