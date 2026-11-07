"""One-shot, read-only recent hashtag search with an external public-data API.

No Instagram session is read, and no Instagram password is required.
New providers give 100 free *one-time* requests/credits; continuing afterward
may cost money. API keys are accepted only privately via terminal or env vars.
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

TAG = re.compile(r"^[a-zA-Z0-9_]{1,60}$")
IG_URL = re.compile(r"^https://(?:www\.)?instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+/?(?:\?.*)?$")


def exact_tag(caption, tag):
    return isinstance(caption, str) and bool(re.search(
        r"(?<!\w)#" + re.escape(tag) + r"(?!\w)", caption, flags=re.IGNORECASE
    ))


def iso_datetime(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def verified_posts(payload, provider, tag, hours, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(payload, dict):
        raise ValueError("Unexpected API response")
    if provider == "socialfetch":
        result = payload.get("data")
        if not isinstance(result, dict):
            raise ValueError("Missing result data")
        status = result.get("lookupStatus")
        if status not in ("found", "not_found"):
            raise ValueError("Unknown hashtag lookup status")
        posts = result.get("media") or []
    else:
        posts = payload.get("data") or []
    if not isinstance(posts, list):
        raise ValueError("Expected post list")
    found, seen = [], set()
    for media in posts:
        if not isinstance(media, dict):
            continue
        date = iso_datetime(media.get("createdAt"))
        if date is None:
            continue
        age = (now-date).total_seconds()/3600
        if not 0 <= age <= hours:
            continue
        caption = media.get("caption") or media.get("text")
        if isinstance(caption, dict):
            caption = caption.get("text")
        # Strict verification: no caption, no proof it used this exact tag.
        if not exact_tag(caption, tag):
            continue
        url = media.get("url") or media.get("permalink")
        if not url:
            shortcode = media.get("shortcode") or media.get("code")
            if isinstance(shortcode, str) and re.fullmatch(r"[A-Za-z0-9_-]+",shortcode):
                kind = "reel" if media.get("kind") == "reel" else "p"
                url = f"https://www.instagram.com/{kind}/{shortcode}/"
        if not isinstance(url,str) or not IG_URL.fullmatch(url):
            continue
        url=url.split("?",1)[0]
        if url in seen:
            continue
        seen.add(url)
        owner = media.get("owner") or media.get("author") or {}
        username = owner.get("handle") or owner.get("username") if isinstance(owner,dict) else None
        found.append((date,round(age,2),username if isinstance(username,str) else "unknown",url))
    return sorted(found,key=lambda row:row[0],reverse=True),len(posts)


def api_request(provider, tag, key):
    if provider == "socialfetch":
        url = "https://api.socialfetch.dev/v2/instagram/hashtags/" + tag + "/media?tab=recent"
        header_name,header_value="x-api-key",key
    else:
        url = "https://api.openhandle.dev/v1/instagram/hashtags/" + tag + "/posts?sort=recent"
        header_name,header_value="Authorization","Bearer "+key
    request = urllib.request.Request(url,headers={header_name:header_value,"Accept":"application/json","User-Agent":"InstagramRecentChecker/1.0"})
    with urllib.request.urlopen(request,timeout=45) as response:
        if response.status != 200:
            raise ValueError("Unexpected HTTP status")
        data=response.read(3_000_000)
    return json.loads(data)


def main():
    p=argparse.ArgumentParser(description="Read-only, newest-first hashtag query from a public data provider")
    p.add_argument("tag",help="exact hashtag name without #")
    p.add_argument("--provider",choices=("socialfetch","openhandle"),default="socialfetch")
    p.add_argument("--hours",type=int,default=48)
    args=p.parse_args()
    tag=args.tag.strip().lstrip("#").lower()
    if not TAG.fullmatch(tag) or not 1<=args.hours<=168:
        p.error("Use one valid hashtag and an age window of 1-168 hours")
    secret_name="SOCIALFETCH_API_KEY" if args.provider=="socialfetch" else "OPENHANDLE_API_KEY"
    key=os.getenv(secret_name) or getpass.getpass(f"Enter {args.provider} API key locally (hidden): ")
    if not key or any(x in key for x in "\r\n"):
        print("Missing or invalid provider key.")
        return 2
    try:
        payload=api_request(args.provider,tag,key)
        matches,total=verified_posts(payload,args.provider,tag,args.hours)
    except urllib.error.HTTPError as exc:
        print("Provider HTTP status:",exc.code,"(response hidden)")
        return 2
    except Exception as exc:
        print("Provider check failed:",type(exc).__name__,"(details hidden)")
        return 2
    print("Provider:",args.provider)
    print("Requested hashtag:",f"#{tag}"," | sorted newest first among retrieved posts")
    print("Provider returned:",total,"posts; verified exact-tag in time window:",len(matches))
    for _,hours,username,url in matches:
        print(f"@{username} | {hours:.1f} hours ago | {url}")
    if not matches:
        print("No verified matches in the retrieved results; NOT proof the hashtag has no recent posts.")
    print("No Instagram password, session export, likes or follows used.")
    return 0 if matches else 3


if __name__=="__main__":
    sys.exit(main())
