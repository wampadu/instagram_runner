"""Meta's official, free Instagram Graph API hashtag Recent-media reader.

Read-only. Requires Facebook User Access Token from a Meta developer app,
a Page-linked Instagram Business/Creator account, and Instagram Public Content
Access approval for hashtag reads. Does NOT use private Instagram sessions.
Does NOT return post authors' usernames or support following/liking.
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

BASE = "https://graph.facebook.com/v26.0"
TAG_PATTERN = re.compile(r"[a-z0-9_]{1,60}", re.I)
POST_URL = re.compile(r"https://(?:www\.)?instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+/?(?:\?.*)?")


class GraphFailure(Exception):
    def __init__(self, http_status, code=None, subcode=None, error_type=None):
        super().__init__("Meta API request failed")
        self.http_status = http_status
        self.code = code
        self.subcode = subcode
        self.error_type = error_type


def graph_get(path, token, params=None):
    """A single request with token in HTTPS Authorization, not query URL."""
    if not path.startswith("/") or "?" in path or ".." in path:
        raise ValueError("Unsafe Graph path")
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "TermuxIGRecentGraph/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read(2_000_000)
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(30_000)
            err = json.loads(raw).get("error") or {}
        except Exception:
            err = {}
        raise GraphFailure(exc.code, err.get("code"), err.get("error_subcode"), err.get("type")) from None
    except urllib.error.URLError:
        raise RuntimeError("Network connection unavailable") from None
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("Invalid JSON from Meta") from None
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected response type")
    if "error" in data:
        err = data["error"] if isinstance(data["error"], dict) else {}
        raise GraphFailure(None, err.get("code"), err.get("error_subcode"), err.get("type"))
    return data


def list_linked_instagram_accounts(token):
    """Facebook Pages linked to Instagram professional accounts."""
    pages = graph_get("/me/accounts", token, {
        "fields": "id,name,instagram_business_account{id,username}",
        "limit": 50,
    })
    if not isinstance(pages.get("data"), list):
        raise ValueError("Meta returned no page list")
    accounts = []
    for page in pages["data"]:
        if not isinstance(page, dict):
            continue
        ig = page.get("instagram_business_account")
        if not isinstance(ig, dict) or not str(ig.get("id", "")).isdigit():
            continue
        accounts.append({
            "page_id": str(page.get("id", "")),
            "page_name": str(page.get("name") or ""),
            "ig_id": str(ig["id"]),
            "ig_username": str(ig.get("username") or "(not supplied)"),
        })
    return accounts


def exact_hashtag(caption, tag):
    return isinstance(caption, str) and bool(
        re.search(r"(?<!\w)#" + re.escape(tag) + r"(?!\w)", caption, re.I)
    )


def clean_media(media, tag, now=None):
    if not isinstance(media, dict) or not exact_hashtag(media.get("caption"), tag):
        return None
    url = media.get("permalink")
    if not isinstance(url, str) or not POST_URL.fullmatch(url):
        return None
    ts = media.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        published = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if published.tzinfo is None:
        return None
    published = published.astimezone(timezone.utc)
    now = now or datetime.now(timezone.utc)
    age = (now - published).total_seconds() / 3600
    if not 0 <= age <= 24:
        return None
    return {"url": url.split("?", 1)[0], "timestamp": published, "age_hours": round(age, 2),
            "media_type": str(media.get("media_type") or "UNKNOWN")}


def get_recent_media(token, ig_id, tag):
    results = graph_get("/ig_hashtag_search", token, {"user_id": ig_id, "q": tag})
    candidates = results.get("data")
    if not isinstance(candidates, list) or not candidates:
        return [], 0, False, "Hashtag ID not returned"
    hid = candidates[0].get("id")
    if not isinstance(hid, str) or not hid.isdigit():
        return [], 0, False, "Invalid hashtag ID"
    response = graph_get("/" + hid + "/recent_media", token, {
        "user_id": ig_id,
        "fields": "id,caption,media_type,permalink,timestamp",
        "limit": 50,
    })
    items = response.get("data")
    if not isinstance(items, list):
        raise ValueError("Recent media response missing list")
    seen, verified = set(), []
    for item in items:
        post = clean_media(item, tag)
        if post is None or post["url"] in seen:
            continue
        seen.add(post["url"])
        verified.append(post)
    verified.sort(key=lambda x: x["timestamp"], reverse=True)
    has_next = bool((response.get("paging") or {}).get("next"))
    return verified, len(items), has_next, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-access", action="store_true",
                        help="Check Page-linked professional IG account only; never spend a hashtag query")
    parser.add_argument("--recent", metavar="TAG",
                        help="Query exact hashtag recent_media; requires Instagram Public Content Access")
    args = parser.parse_args()
    if not args.check_access and not args.recent:
        parser.error("Specify --check-access or --recent TAG")
    tag = (args.recent or "").strip().lower().lstrip("#")
    if args.recent and not TAG_PATTERN.fullmatch(tag):
        parser.error("Hashtag must contain only letters, digits or underscores")
    token = os.environ.get("META_FACEBOOK_USER_TOKEN") or getpass.getpass(
        "Meta Facebook User token (hidden; do NOT use your Instagram password): "
    ).strip()
    if not token or any(ch in token for ch in "\r\n"):
        print("Missing/invalid Meta User token.")
        return 2
    try:
        accounts = list_linked_instagram_accounts(token)
        print("Page-linked professional Instagram accounts:", len(accounts))
        for i, acc in enumerate(accounts, 1):
            print(f"  {i}. @{acc['ig_username']} (Facebook Page: {acc['page_name']})")
        if not accounts:
            print("No linked professional account found. Check Business/Creator status,")
            print("connected Facebook Page, Page role, pages_show_list and pages_read_engagement.")
            return 3
        if args.check_access:
            print("CHECK PASS: Facebook token can see a Page-linked professional account.")
            print("Hashtag permissions have NOT yet been checked.")
            return 0
        if len(accounts) > 1:
            matching = [a for a in accounts if a["ig_username"].lower() == "follow_back_aswell"]
            if len(matching) != 1:
                print("Multiple IG accounts found. Use token/Page scoped to the intended account.")
                return 3
            account = matching[0]
        else:
            account = accounts[0]
        print(f"Requesting Meta's official Recent media for #{tag}")
        matches, total, more, error = get_recent_media(token, account["ig_id"], tag)
        if error:
            print(error)
            return 3
        print("Returned entries:", total, "verified exact-tag posts <24 hours:", len(matches))
        for m in matches:
            print(f"  {m['age_hours']:.2f} hours | {m['timestamp'].isoformat()} | {m['url']}")
        print("More pages available:", "yes" if more else "no")
        print("Meta omits poster usernames, and response ordering/completeness is not guaranteed.")
        print("No Instagram login, session export, follows, likes or comments.")
        return 0 if matches else 3
    except GraphFailure as exc:
        print("Meta Graph API error (sanitized): HTTP", exc.http_status,
              "code", exc.code, "subcode", exc.subcode,
              "type", exc.error_type)
        print("Check Meta app permissions, token expiry and Instagram Public Content Access review.")
        print("No automatic retry or token disclosure.")
        return 2
    except Exception as exc:
        print("Access/read check failed:", type(exc).__name__)
        print("No automatic retry.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
