"""Prevent duplicate follows when primary and backup GitHub crons both fire.

GitHub's run-name embeds the cron expression, so its REST API run history can
identify each intended Toronto slot even if the runner starts hours late.
A scheduled run is elected only once for its local slot/date. If GitHub
history is unavailable or the cron cannot be identified, fail closed visibly.
"""
from datetime import datetime
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.instagram_schedule import SLOTS, TORONTO, occurrence_for_cron, parse_cron

RUN_TITLE_PREFIX = "Instagram cron: "


def get_run_slot_and_date(run):
    """Infer cron slot and Toronto scheduled date from GitHub run metadata."""
    if run.get("event") != "schedule":
        return None
    title = run.get("display_title") or ""
    if not title.startswith(RUN_TITLE_PREFIX):
        return None
    cron = title[len(RUN_TITLE_PREFIX):].strip()
    parsed = parse_cron(cron)
    if not parsed:
        return None
    try:
        created = datetime.fromisoformat(
            run["created_at"].replace("Z", "+00:00")
        )
        scheduled = occurrence_for_cron(cron, created)
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    minute, hour = parsed
    return SLOTS[hour][0], scheduled.strftime("%Y-%m-%d")


def same_slot(run, slot, local_date):
    return get_run_slot_and_date(run) == (slot, local_date)


def should_execute(run_id, slot, local_date, runs):
    """Elect the earliest created scheduled run from this slot's cron triggers."""
    current = next((r for r in runs if str(r.get("id")) == str(run_id)), None)
    if current is None:
        raise ValueError("Current scheduled run absent from GitHub history")
    if not same_slot(current, slot, local_date):
        raise ValueError(
            "Current run has no matching scheduled cron and Toronto date "
            "(check run-name metadata)"
        )
    relevant = [r for r in runs if same_slot(r, slot, local_date)]
    elected = min(relevant, key=lambda r: (r["created_at"], int(r["id"])))
    return str(elected["id"]) == str(run_id), elected["id"]


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
                raise RuntimeError("Could not check GitHub scheduled run history") from exc
            time.sleep(2)
    raise RuntimeError("Could not check GitHub scheduled run history")


def main():
    event = os.environ.get("GITHUB_EVENT_NAME")
    slot = os.environ.get("SLOT")
    local_date = os.environ.get("LOCAL_DATE")
    if slot not in {value[0] for value in SLOTS.values()}:
        raise SystemExit("Invalid Toronto Instagram slot")
    if event == "workflow_dispatch":
        # Manual dispatch is explicit. It doesn't count as a scheduled backup.
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
            print(
                "Schedule guard failed; Instagram actions NOT attempted:",
                type(exc).__name__, str(exc), flush=True
            )
            raise SystemExit(2)
    else:
        raise SystemExit("Unknown event for scheduled Instagram workflow")
    print(
        f"Guard: slot={slot} date={local_date} "
        f"allow_live_actions={allowed} reason={reason}", flush=True
    )
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"run={str(allowed).lower()}\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(
            f"**GitHub schedule deduplication:** {reason}. "
            f"Instagram actions {'authorized' if allowed else 'skipped'}.\n"
        )


if __name__ == "__main__":
    main()
