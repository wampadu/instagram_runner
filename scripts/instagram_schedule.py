"""Select exactly one Toronto Instagram slot from a GitHub Actions cron.

GitHub supports 'timezone: America/Toronto' in each schedule entry, so the
cron's HOUR is a local hour, including across daylight saving changes.
Each slot has a primary attempt at :11 and a backup at :36. The backup must
pass a separate GitHub run-history guard before running live actions.
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
MAX_DELAY = timedelta(hours=2)


def select_session(event_name, cron_expression="", manual_slot="5am", now=None):
    """Pure selection logic; no network, no Instagram calls."""
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

    match = re.fullmatch(r"(11|36) (5|9|15|18|22) \* \* \*", cron_expression or "")
    if not match:
        return {"run": False, "reason": "unknown_cron"}
    minute, hour = map(int, match.groups())
    candidates = [
        (current + timedelta(days=day)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        for day in (-1, 0, 1)
    ]
    scheduled = min(candidates, key=lambda d: abs(d - current))
    if current - scheduled > MAX_DELAY or current < scheduled - timedelta(minutes=2):
        return {"run": False, "reason": "stale_or_early_trigger"}
    slot, tag = SLOTS[hour]
    return {
        "run": True, "slot": slot, "hour": hour, "hashtag": tag,
        "local_date": scheduled.strftime("%Y-%m-%d"),
        "kind": "backup" if minute == BACKUP_MINUTE else "primary",
    }


def main():
    decision = select_session(
        os.environ.get("GITHUB_EVENT_NAME", ""),
        os.environ.get("CRON_EXPRESSION", ""),
        os.environ.get("MANUAL_SLOT", "5am"),
    )
    print("Toronto session decision:", decision)
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
                    f"Instagram {decision['kind']} schedule: "
                    f"**{decision['slot']} Toronto**, "
                    f"**#{decision['hashtag']}**, max **20** pairs.\n"
                )
            else:
                output.write(
                    f"Skipped schedule: {decision.get('reason', 'unknown')}\n"
                )


if __name__ == "__main__":
    main()
