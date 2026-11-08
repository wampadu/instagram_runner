"""Avoid duplicate scheduled Instagram sessions when GitHub's backup cron fires.

A read-only GitHub Actions API lookup elects the earliest created scheduled
workflow run for each Toronto local date and slot. Duplicate runs exit before
the login, the Instagram session, or any follow/like calls. Fails closed if
the API cannot be read, rather than guessing and risking double engagement.
"""
from datetime import datetime, timedelta
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TORONTO = ZoneInfo("America/Toronto")
SLOT_HOURS = {"5am": 5, "9am": 9, "3pm": 15, "6pm": 18, "10pm": 22}


def same_slot(run, slot, local_date):
    """Whether the run was created within this local slot's 2h45m window."""
    if run.get("event") != "schedule":
        return False
    try:
        created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        created = created.astimezone(TORONTO)
        start = datetime.fromisoformat(local_date).replace(
            tzinfo=TORONTO, hour=SLOT_HOURS[slot]
        )
    except (KeyError, ValueError, TypeError):
        return False
    return start <= created < start + timedelta(hours=2, minutes=45)


def should_execute(run_id, slot, local_date, runs):
    """Elect only the first scheduled run in the slot, regardless of status."""
    relevant = [r for r in runs if same_slot(r, slot, local_date)]
    candidate_ids = {str(r.get("id")) for r in relevant}
    if str(run_id) not in candidate_ids:
        raise ValueError("Current scheduled run absent from GitHub run history")
    first = min(relevant, key=lambda r: (r["created_at"], int(r["id"])))
    return str(first["id"]) == str(run_id), first["id"]


def fetch_runs(repo, token):
    if not repo or "/" not in repo or not token:
        raise ValueError("Missing GitHub repository or Actions read token")
    url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/"
        "manual-instagram.yml/runs?event=schedule&per_page=100"
    )
    req = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "instagram-scheduled-session-guard",
    })
    # Read-only retries for transient GitHub REST errors are safe.
    for attempt in range(3):
        try:
            with urlopen(req, timeout=20) as response:
                data = json.load(response)
            runs = data.get("workflow_runs")
            if not isinstance(runs, list):
                raise ValueError("GitHub workflow run listing missing")
            return runs
        except (HTTPError, URLError, TimeoutError) as exc:
            if attempt == 2:
                raise RuntimeError("Could not check prior GitHub scheduled runs") from exc
            time.sleep(2)
    raise RuntimeError("Could not check prior GitHub scheduled runs")


def main():
    event = os.environ.get("GITHUB_EVENT_NAME")
    slot = os.environ.get("SLOT")
    local_date = os.environ.get("LOCAL_DATE")
    if slot not in SLOT_HOURS:
        raise SystemExit("Invalid Toronto Instagram slot")
    if event == "workflow_dispatch":
        allowed, reason = True, "manual_dispatch"
    elif event == "schedule":
        try:
            runs = fetch_runs(
                os.environ.get("GITHUB_REPOSITORY"),
                os.environ.get("GH_TOKEN"),
            )
            allowed, elected_id = should_execute(
                os.environ["GITHUB_RUN_ID"], slot, local_date, runs
            )
            reason = (
                "elected_first_run" if allowed
                else f"duplicate_of_run_{elected_id}"
            )
        except (ValueError, KeyError, RuntimeError) as exc:
            print("Guard stopped: cannot safely determine first scheduled run:",
                  type(exc).__name__, str(exc), flush=True)
            raise SystemExit(2)
    else:
        allowed, reason = False, "not_manual_or_scheduled"

    print(f"Guard: slot={slot} date={local_date} "
          f"allow_live_actions={allowed} reason={reason}", flush=True)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"run={str(allowed).lower()}\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(f"Schedule deduplication: **{reason}**\n")


if __name__ == "__main__":
    main()
