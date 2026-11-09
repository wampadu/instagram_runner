"""Select exactly one Toronto Instagram slot using the scheduled cron.

GitHub Actions creates scheduled events irregularly and sometimes many hours
late. The cron expression—not the wall-clock hour when the runner starts—owns
the slot/hashtag choice. Never silently skip a valid cron due to runner delays.

A schedule token identifies the last Toronto-local occurrence of that cron
before the runner woke up. The deduplication guard independently computes the
same occurrence from each GitHub workflow-run's *created_at* timestamp.
"""
from datetime import datetime, timedelta
import os
import re
from zoneinfo import ZoneInfo

TORONTO = ZoneInfo("America/Toronto")
SLOTS = {
    5: ("5am", "followforfollow"),
    9: ("9am", "likeforlike"),
    15: ("3pm", "likeforfollow"),
    18: ("6pm", "follow4follow"),
    22: ("10pm", "like4like"),
}
MANUAL_SLOTS = {slot: (hour, hashtag) for hour, (slot, hashtag) in SLOTS.items()}
PRIMARY_MINUTE = 11
BACKUP_MINUTE = 36
CRON_RE = re.compile(r"(11|36) (5|9|15|18|22) \* \* \*")


def parse_cron(cron):
    match = CRON_RE.fullmatch(cron or "")
    if not match:
        return None
    return tuple(map(int, match.groups()))


def occurrence_for_cron(cron, timestamp):
    """Last scheduled Toronto-local occurrence <= observed timestamp.

    The date is based on when GitHub *created* the run for duplicate checking,
    and on current time only when creating the first session decision.
    """
    parsed = parse_cron(cron)
    if not parsed:
        raise ValueError("Unrecognized Instagram schedule cron")
    minute, hour = parsed
    now_local = timestamp.astimezone(TORONTO)
    event = now_local.replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    if now_local < event:
        event -= timedelta(days=1)
    return event


def select_session(event_name, cron_expression="", manual_slot="5am", now=None):
    """Pure schedule selection with no Instagram network calls."""
    current = (now or datetime.now(TORONTO)).astimezone(TORONTO)
    if event_name == "workflow_dispatch":
        if manual_slot not in MANUAL_SLOTS:
            raise ValueError("Unknown manual Instagram session slot")
        hour, hashtag = MANUAL_SLOTS[manual_slot]
        return {
            "run": True, "slot": manual_slot, "hour": hour,
            "hashtag": hashtag, "local_date": current.strftime("%Y-%m-%d"),
            "kind": "manual",
        }
    if event_name != "schedule":
        return {"run": False, "reason": "not_schedule_or_dispatch"}
    parsed = parse_cron(cron_expression)
    if parsed is None:
        # Unknown crons are errors, not misleading green "successful" jobs.
        raise ValueError("Unknown cron expression: " + str(cron_expression))
    minute, hour = parsed
    occurrence = occurrence_for_cron(cron_expression, current)
    slot, hashtag = SLOTS[hour]
    return {
        "run": True, "slot": slot, "hour": hour, "hashtag": hashtag,
        "local_date": occurrence.strftime("%Y-%m-%d"),
        "kind": "backup" if minute == BACKUP_MINUTE else "primary",
        "scheduled_at": occurrence.isoformat(),
        "delay_minutes": max(0, int((current - occurrence).total_seconds() / 60)),
    }


def main():
    decision = select_session(
        os.environ.get("GITHUB_EVENT_NAME", ""),
        os.environ.get("CRON_EXPRESSION", ""),
        os.environ.get("MANUAL_SLOT", "5am"),
    )
    print("Toronto session decision:", decision, flush=True)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            for field in ("run", "slot", "hashtag", "local_date", "kind"):
                value = decision.get(field, "")
                if isinstance(value, bool):
                    value = str(value).lower()
                output.write(f"{field}={value}\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as output:
            if decision["run"]:
                output.write(
                    f"GitHub delivered the **{decision['slot']} Toronto** "
                    f"#{decision['hashtag']} trigger "
                    f"({decision['kind']}, capped at 20 pairs).\n"
                )
                if decision.get("delay_minutes", 0) > 20:
                    output.write(
                        "**GitHub scheduler was late:** "
                        f"{decision['delay_minutes']} minutes after its slot. "
                        "No engagement has yet been attempted.\n"
                    )
            else:
                output.write(
                    f"No live action: {decision.get('reason', 'unknown')}.\n"
                )


if __name__ == "__main__":
    main()
