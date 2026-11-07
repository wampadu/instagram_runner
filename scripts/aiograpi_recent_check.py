"""Read-only validation of the Instagram 'recent' hashtag feed.

Runs locally with saved aiograpi settings; never asks for or transmits
passwords to GitHub, never initiates login, and never likes/follows.
"""
import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SESSION = Path.home() / ".instagram_runner" / "aiograpi-session.json"


def age_in_hours(taken_at, now=None):
    """Return media age; assume a naive Instagram datetime denotes UTC."""
    if not isinstance(taken_at, datetime):
        return None
    if taken_at.tzinfo is None:
        taken_at = taken_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return round((now - taken_at.astimezone(timezone.utc)).total_seconds() / 3600, 2)


async def fetch_recent(client, tag, amount=8):
    """Fetch only the private mobile API's 'recent' hashtag tab."""
    return await client.hashtag_medias_recent(tag, amount=amount)


async def check(tag, amount, session, source="private"):
    from aiograpi import Client

    stage = "loading local session"
    client = Client()
    client.load_settings(session)
    if not getattr(client, "user_id", None):
        raise RuntimeError("Saved settings contain no authenticated user")
    stage = "authenticated session check"
    try:
        await client.account_info()
    except Exception as exc:
        raise RuntimeError(f"{stage}: {type(exc).__name__}") from None
    stage = "reading recent hashtag tab"
    try:
        if source == "private":
            items = await fetch_recent(client, tag, amount)
        else:
            # An independent GraphQL surface with show_ranked=False. Instagram
            # may still rank/limit these results; verify actual timestamps.
            items, _cursor = await client.hashtag_medias_paginated_gql(tag, amount=amount)
    except Exception as exc:
        raise RuntimeError(f"{stage}: {type(exc).__name__}") from None

    print("Authenticated session reuse: PASS")
    if source == "private":
        print("Endpoint: PRIVATE mobile hashtag tab=recent; NO Top-post fallback")
    else:
        print("Endpoint: PUBLIC GraphQL show_ranked=False; NOT guaranteed chronological; NO Top-post fallback")
    print("Hashtag:", "#" + tag)
    print("Returned posts:", len(items))
    ages = [age_in_hours(getattr(m, "taken_at", None)) for m in items]
    known = [x for x in ages if x is not None]
    print("Posts with readable timestamps:", len(known))
    print("Posts dated in last 24 hours:", sum(0 <= x <= 24 for x in known))
    print("Posts dated in last 48 hours:", sum(0 <= x <= 48 for x in known))
    for n, h in enumerate(ages, 1):
        print(f"Post {n} age (hours): {h if h is not None else 'unknown'}")
    print("No likes, follows, comments, downloads, or session exports performed.")
    recent24 = sum(0 <= x <= 24 for x in known)
    if not items:
        print("RECENT POSTS NOT VERIFIED: endpoint returned zero posts. Keep write actions disabled.")
        return 3
    if not known or recent24 == 0:
        print("RECENT POSTS NOT VERIFIED: no retrieved post demonstrably under 24 hours old.")
        return 3
    print("RECENT POST AGE VERIFIED: at least one post is less than 24 hours old.")
    print("This does NOT prove complete chronological hashtag coverage.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="One read-only recent-hashtag check using a saved Instagram session")
    parser.add_argument("--tag", default="toronto", help="Hashtag without the #")
    parser.add_argument("--amount", type=int, default=8)
    parser.add_argument("--source", choices=("private", "public-gql"), default="private")
    args = parser.parse_args()
    tag = args.tag.strip().lstrip("#")
    if not tag or args.amount < 1 or args.amount > 15 or not tag.replace("_", "").isalnum():
        print("Invalid hashtag or amount; choose 1-15.")
        return 2
    if not DEFAULT_SESSION.is_file():
        print("Saved session missing. Interactive login must succeed first.")
        return 1
    try:
        return asyncio.run(asyncio.wait_for(check(tag, args.amount, DEFAULT_SESSION, args.source), timeout=90))
    except Exception as exc:
        print("Read-only recent check failed. Error class:", type(exc).__name__)
        # Only print sanitized exception strings created here (no raw network responses).
        if isinstance(exc, RuntimeError) and str(exc).startswith(("authenticated session check:", "reading recent hashtag tab:")):
            print("Stage:", str(exc))
        print("Saved session untouched. No password login attempted.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
