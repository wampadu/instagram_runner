"""Read-only Instagram post discovery using public accounts as search seeds.

Uses the existing private-on-phone aiograpi session, not fresh password login.
Unlike the broken hashtag sections API, uses working account search and
per-account posts. This is NOT a comprehensive chronological hashtag feed.
Only explicitly hashtagged recent posts are returned. No engagement actions.
"""
import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SESSION = Path.home() / ".instagram_runner" / "aiograpi-session.json"
TAG_RE = re.compile(r"^[a-zA-Z0-9_]{1,60}$")


def media_age_hours(taken_at, now=None):
    if isinstance(taken_at, (int, float)):
        taken_at = datetime.fromtimestamp(taken_at, timezone.utc)
    if not isinstance(taken_at, datetime):
        return None
    if taken_at.tzinfo is None:
        taken_at = taken_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return (now - taken_at.astimezone(timezone.utc)).total_seconds() / 3600


def caption_contains_hashtag(caption, tag):
    # No substring false positive (#toronto must not match #torontolife).
    # Word-boundary excludes other digits/letters/underscore and Unicode letters.
    if not isinstance(caption, str):
        return False
    return bool(re.search(r"(?<!\\w)#" + re.escape(tag) + r"(?!\\w)", caption, re.I))


def verified_post(media, tag, max_hours, now=None):
    age = media_age_hours(getattr(media, "taken_at", None), now=now)
    caption = getattr(media, "caption_text", None)
    if age is None or not 0 <= age <= max_hours or not caption_contains_hashtag(caption, tag):
        return None
    code = getattr(media, "code", None)
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", code):
        return None
    user = getattr(media, "user", None)
    username = getattr(user, "username", None)
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", username):
        return None
    return {"username": username, "age_hours": round(age, 1), "url": f"https://www.instagram.com/p/{code}/"}


async def discover(client, tag, max_accounts, per_account, max_hours):
    """Read-only discovery from public account-name matches; no feed fallback."""
    candidates = await asyncio.wait_for(client.search_users(tag), timeout=35)
    if not isinstance(candidates, list):
        raise RuntimeError("Account search did not return a list")
    matches, examined, inspected, failed = [], 0, 0, 0
    seen_users, seen_codes = set(), set()
    for user in candidates:
        pk = getattr(user, "pk", None)
        if not pk or getattr(user, "is_private", False) or str(pk) in seen_users:
            continue
        seen_users.add(str(pk))
        if examined >= max_accounts:
            break
        examined += 1
        try:
            posts = await asyncio.wait_for(client.user_medias_v1(pk, amount=per_account), timeout=35)
        except Exception as exc:
            # Do not mask authentication/rate limiting as normal empty results.
            if type(exc).__name__ in ("ClientUnauthorizedError", "ClientThrottledError", "LoginRequired", "ClientLoginRequired", "PleaseWaitFewMinutes"):
                raise RuntimeError(f"Discovery stopped: {type(exc).__name__}") from None
            failed += 1
            continue
        for media in posts:
            inspected += 1
            code = getattr(media, "code", None)
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            record = verified_post(media, tag, max_hours)
            if record:
                matches.append(record)
    return {
        "public_accounts_checked": examined,
        "posts_inspected": inspected,
        "account_read_errors": failed,
        "matches": sorted(matches, key=lambda x:x["age_hours"]),
    }


async def run(args):
    from aiograpi import Client
    logging.disable(logging.CRITICAL)
    if not SESSION.is_file():
        print("Local saved Instagram session missing. No password login attempted.")
        return 2
    client = Client()
    client.load_settings(SESSION)
    try:
        await asyncio.wait_for(client.account_info(), timeout=30)
    except Exception as exc:
        print("Saved Instagram session not authenticated:", type(exc).__name__)
        return 2
    print("Saved Instagram session: PASS")
    print("Discovery method: account-name search + each public account's recent posts")
    print("Coverage warning: not a hashtag-wide or chronological feed.")
    for tag in args.hashtags:
        try:
            result = await discover(client,tag,args.max_accounts,args.per_account,args.max_age_hours)
        except Exception as exc:
            print(f"#{tag}: failed: {type(exc).__name__}. No retry.")
            return 2
        print(f"#{tag}: public accounts={result['public_accounts_checked']}, posts scanned={result['posts_inspected']}, read errors={result['account_read_errors']}")
        print(f"#{tag}: exact-tag posts within {args.max_age_hours} hours={len(result['matches'])}")
        for post in result["matches"]:
            print(f"  @{post['username']} | age {post['age_hours']} hours | {post['url']}")
    print("No follows, likes, comments, downloads, credentials or session export.")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("hashtags", nargs="+", help="One or two hashtags to search, without '#'")
    p.add_argument("--max-accounts", type=int, default=6)
    p.add_argument("--per-account", type=int, default=5)
    p.add_argument("--max-age-hours", type=int, default=168)
    args = p.parse_args()
    args.hashtags=[x.lower().lstrip("#") for x in args.hashtags]
    if (len(args.hashtags)>2 or any(not TAG_RE.fullmatch(t) for t in args.hashtags)
        or not 1<=args.max_accounts<=12 or not 1<=args.per_account<=12
        or not 1<=args.max_age_hours<=168):
        p.error("Limit: 1-2 hashtags, up to 12 accounts and 12 posts/account, age up to 168 hours")
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        print("Read-only discovery stopped:", type(exc).__name__)
        return 2


if __name__ == "__main__":
    sys.exit(main())
