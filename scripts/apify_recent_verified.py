"""One-shot, budget-capped, read-only Apify Recent Instagram hashtag check.

Requires an Apify API token, NOT an Instagram password or session. It never
touches Instagram account actions and validates caption, timestamps, URLs.
Results depend on third-party live availability; no completeness guarantee.
"""
import argparse
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ACTOR = "coregent~instagram-hashtag-scraper"
VALID_TAG = re.compile(r"^[a-zA-Z0-9_]{1,60}$")
POST_URL = re.compile(r"^https://(?:www\.)?instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+/?(?:\?.*)?$")


def parse_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None  # Never assume a missing timezone
    return dt.astimezone(timezone.utc)


def hashtag_in_caption(caption, tag):
    return isinstance(caption, str) and bool(
        re.search(r"(?<!\w)#" + re.escape(tag) + r"(?!\w)", caption, re.I)
    )


def normalize_rows(rows, tag, max_age_hours=24, now=None):
    """Returns (newest-first records, status counts, number of raw rows)."""
    if not isinstance(rows, list):
        raise ValueError("Apify did not return a list of rows")
    now = now or datetime.now(timezone.utc)
    seen, matches, statuses = set(), [], {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = row.get("status") or "UNKNOWN"
        statuses[status] = statuses.get(status, 0) + 1
        if row.get("rowType") != "post" or status != "SUCCESS":
            continue
        if str(row.get("queryHashtag", "")).lower().lstrip("#") != tag:
            continue
        ts = parse_timestamp(row.get("timestamp"))
        if ts is None:
            continue
        age = (now - ts).total_seconds() / 3600
        if not 0 <= age <= max_age_hours:
            continue
        if not hashtag_in_caption(row.get("caption"), tag):
            continue
        url = row.get("url")
        if not isinstance(url, str) or not POST_URL.fullmatch(url):
            continue
        url = url.split("?", 1)[0]
        if url in seen:
            continue
        seen.add(url)
        owner = row.get("owner")
        username = owner.get("username") if isinstance(owner, dict) else None
        if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", username):
            username = "(unavailable)"
        matches.append({"timestamp": ts, "hours_ago": round(age, 2),
                        "username": username, "url": url})
    return sorted(matches, key=lambda x: x["timestamp"], reverse=True), statuses, len(rows)


def apify_recent_request(token, tag, limit, max_charge_usd):
    params = urllib.parse.urlencode({
        "maxTotalChargeUsd": f"{max_charge_usd:.2f}",
        "timeout": "180",
        "maxItems": str(limit + 2),
    })
    url = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items?{params}"
    body = {
        "hashtags": [tag],
        "maxResultsPerHashtag": limit,
        "sort": "RECENT",
        "postsNewerThan": "24 hours",
        "contentTypes": ["ALL"],
        "includeMediaUrls": False,
        "includeOwnerDetails": True,
        "includeAudio": False,
        "includeLocation": False,
        "maxConcurrency": 1,
        "debugMode": False,
    }
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=195) as resp:
        if resp.status != 201 and resp.status != 200:
            raise ValueError("Unexpected provider HTTP status")
        raw = resp.read(3_000_000)
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hashtag", nargs="?", default="follow_for_follow")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-charge-usd", type=float, default=0.10)
    args = parser.parse_args()
    tag = args.hashtag.strip().lower().lstrip("#")
    if not VALID_TAG.fullmatch(tag) or not 1 <= args.limit <= 30:
        parser.error("Choose one valid hashtag and limit 1–30")
    if not 0.01 <= args.max_charge_usd <= 0.20:
        parser.error("Maximum charge limit must be between US$0.01 and US$0.20")
    token = os.environ.get("APIFY_TOKEN") or getpass.getpass(
        "Enter Apify API token privately (not Instagram credentials): "
    ).strip()
    if not token or any(c in token for c in "\r\n"):
        print("No valid Apify API token supplied.")
        return 2
    print(f"Requesting #{tag}, Recent, <=24 hours, maximum provider charge US${args.max_charge_usd:.2f}")
    try:
        data = apify_recent_request(token, tag, args.limit, args.max_charge_usd)
        posts, statuses, total = normalize_rows(data, tag)
    except urllib.error.HTTPError as exc:
        print("Apify HTTP error:", exc.code, "(response body hidden; no automatic retry)")
        return 2
    except Exception as exc:
        print("Provider request or validation failed:", type(exc).__name__)
        print("No retry made; failed attempts may still use provider resources.")
        return 2
    print("Returned rows:", total, "Provider status counts:", statuses)
    print("Strict verified posts in last 24 hours:", len(posts))
    for p in posts:
        print(f"  @{p['username']} | {p['hours_ago']:.1f} hours old | {p['url']}")
    if not posts:
        print("NO VERIFIED RECENT RESULTS. Provider might have no feed for this hashtag.")
        print("An empty sample does not prove zero recent posts exist.")
        return 3
    print("Sorted by actual publication timestamp. Feed completeness NOT established.")
    print("No Instagram password/session used; no likes, follows or comments performed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
