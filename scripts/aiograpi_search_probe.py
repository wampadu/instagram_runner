"""Probe Instagram's current keyword/media search as a read-only alternative.

The hashtag endpoint may return zero. Search results are *ranked*, NOT an
exhaustive or chronological hashtag feed. Count posts only if their caption
contains the exact hashtag and their timestamp is within the age window.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

SESSION=Path.home()/".instagram_runner"/"aiograpi-session.json"


def age_hours(taken_at):
    if isinstance(taken_at,(int,float)):
        taken_at=datetime.fromtimestamp(taken_at,timezone.utc)
    if not isinstance(taken_at,datetime):
        return None
    if taken_at.tzinfo is None:
        taken_at=taken_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc)-taken_at.astimezone(timezone.utc)).total_seconds()/3600


def matches_tag(caption,tag):
    return bool(re.search(r"(?<![\\w#])#"+re.escape(tag)+r"(?![\\w])",caption or "",re.I))


async def main():
    logging.disable(logging.CRITICAL)
    from aiograpi import Client
    cl=Client()
    if not SESSION.is_file():
        print("Session missing; no login performed.")
        return 2
    cl.load_settings(SESSION)
    try:
        await cl.account_info()
        print("Saved session: PASS")
    except Exception as exc:
        print("Session verification error:",type(exc).__name__)
        return 2
    tag="torontophotography"
    try:
        posts=await asyncio.wait_for(cl.media_search(tag,amount=12),timeout=75)
    except Exception as exc:
        print("Media search error:",type(exc).__name__)
        return 1
    print("Search source: private keyword media search, ranking unknown")
    print("Returned posts:",len(posts))
    matched=0
    recent=0
    for media in posts:
        caption=getattr(media,"caption_text","") or ""
        age=age_hours(getattr(media,"taken_at",None))
        if matches_tag(caption,tag):
            matched+=1
            if age is not None and 0<=age<=48:
                recent+=1
                print("VERIFIED RECENT", "age_hours:",round(age,1),"link:","https://www.instagram.com/p/"+str(media.code)+"/")
    print("Posts with exact hashtag in caption:",matched)
    print("Exact-hashtag posts under 48 hours:",recent)
    print("No like/follow/comment actions or session export.")
    return 0 if recent else 3


if __name__=="__main__":
    try:
        raise SystemExit(asyncio.run(asyncio.wait_for(main(),timeout=90)))
    except Exception as exc:
        print("Probe failed:",type(exc).__name__)
        raise SystemExit(1)
