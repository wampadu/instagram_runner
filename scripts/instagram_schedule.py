"""Map GitHub's UTC cron triggers to five local Toronto Instagram sessions.

Two cron hours are scheduled for each local time (EST/EDT); the incorrect
seasonal UTC hour becomes a no-op. Manual runs choose an explicit slot.
"""
from datetime import datetime, timedelta, timezone
import os
import re
from zoneinfo import ZoneInfo

TORONTO = ZoneInfo("America/Toronto")
# One hashtag per session. Five sessions are requested, despite "four" in prose.
SLOTS = {
    5: ("5am", "followforfollow"),
    9: ("9am", "likeforlike"),
    15: ("3pm", "likeforfollow"),
    18: ("6pm", "follow4follow"),
    22: ("10pm", "like4like"),
}
MANUAL_SLOTS = {slot: (hour, hashtag) for hour, (slot, hashtag) in SLOTS.items()}
# 10 paired cron hours; only five match Toronto local clock on a given day.
UTC_CRON_HOURS = (2, 3, 9, 10, 13, 14, 19, 20, 22, 23)
MAX_SCHEDULE_DELAY = timedelta(hours=3)


def select_session(event_name, cron_expression="", manual_slot="5am", now_utc=None):
    """Return a fixed run/slot/hashtag decision; no Instagram access."""
    if event_name == "workflow_dispatch":
        if manual_slot not in MANUAL_SLOTS:
            raise ValueError("Unknown manual Instagram session slot")
        hour, hashtag = MANUAL_SLOTS[manual_slot]
        return {"run": True, "slot": manual_slot, "hour": hour, "hashtag": hashtag}

    if event_name != "schedule":
        return {"run": False, "reason": "not_schedule_or_dispatch"}
    match = re.fullmatch(r"0 (\d{1,2}) \* \* \*", cron_expression or "")
    if not match:
        return {"run": False, "reason": "unrecognized_cron"}
    utc_hour = int(match.group(1))
    if utc_hour not in UTC_CRON_HOURS:
        return {"run": False, "reason": "unrecognized_hour"}

    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    # A scheduled 10 PM Toronto session occurs at 02:00/03:00 UTC the next
    # calendar day, so identify the UTC cron event rather than using today
    # in Toronto to guess the associated UTC date.
    events = [
        datetime.combine(
            (now + timedelta(days=offset)).date(),
            datetime.min.time(), tzinfo=timezone.utc
        ).replace(hour=utc_hour)
        for offset in (-1, 0, 1)
    ]
    triggered = min(events, key=lambda event: abs(event - now))
    if abs(now - triggered) > MAX_SCHEDULE_DELAY:
        return {"run": False, "reason": "stale_cron_event"}
    local = triggered.astimezone(TORONTO)
    slot = SLOTS.get(local.hour)
    if not slot or local.minute != 0:
        return {"run": False, "reason": "wrong_dst_hour"}
    return {
        "run": True,
        "slot": slot[0],
        "hour": local.hour,
        "hashtag": slot[1],
        "local_date": local.strftime("%Y-%m-%d"),
        "local_timezone": local.tzname(),
    }


def main():
    decision = select_session(
        os.environ.get("GITHUB_EVENT_NAME", ""),
        os.environ.get("CRON_EXPRESSION", ""),
        os.environ.get("MANUAL_SLOT", "5am"),
    )
    print("Session decision:", decision)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            for key in ("run", "slot", "hashtag"):
                value = decision.get(key, "")
                if isinstance(value, bool):
                    value = str(value).lower()
                handle.write(f"{key}={value}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            if decision["run"]:
                handle.write(
                    f"Instagram session: **{decision['slot']} Toronto** · "
                    f"**#{decision['hashtag']}** · maximum 20 new follow+like pairs\n"
                )
            else:
                handle.write(
                    f"UTC trigger skipped: {decision.get('reason', 'unspecified')}\n"
                )


if __name__ == "__main__":
    main()
