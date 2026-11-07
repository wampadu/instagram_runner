"""Read-only alternate Instagram post discovery viability test.

Checks whether account-search and user-media endpoints work, and whether reels
search exposes any result containers. Prints no private account data/IDs.
"""
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

SESSION = Path.home()/".instagram_runner"/"aiograpi-session.json"


def age_h(value):
    if isinstance(value,datetime):
        if value.tzinfo is None:
            value=value.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc)-value.astimezone(timezone.utc)).total_seconds()/3600
    return None


async def main():
    from aiograpi import Client
    logging.disable(logging.CRITICAL)
    client=Client()
    client.load_settings(SESSION)
    await client.account_info()
    print("Auth: PASS; no login attempted")
    query="torontophotography"
    try:
        users=await asyncio.wait_for(client.search_users(query,count=5),timeout=40)
        print("Accounts search count:",len(users))
    except Exception as e:
        users=[]
        print("Accounts search:",type(e).__name__)
    if users:
        target=next((u for u in users if not getattr(u,"is_private",False)),None)
        if target:
            try:
                posts=await asyncio.wait_for(client.user_medias_v1(target.pk,amount=5),timeout=40)
                print("First public matching account recent post count:",len(posts))
                ages=[age_h(getattr(p,"taken_at",None)) for p in posts]
                print("Posts dated within 48h:",sum(v is not None and 0<=v<=48 for v in ages))
                print("Posts captioned with exact query hashtag:",sum("#"+query in (getattr(p,"caption_text","") or "").lower() for p in posts))
            except Exception as e:
                print("User media:",type(e).__name__)
    try:
        response=await asyncio.wait_for(client.fbsearch_reels_v2(query),timeout=40)
        if isinstance(response,dict):
            allowlist=("reels","clips","items","media","media_grid","reels_grid","sections","results")
            print("Reels search response status ok:",response.get("status")=="ok")
            print("Reels search present containers:",{k: len(v) if isinstance(v,(list,dict)) else "other" for k in allowlist if (v:=response.get(k)) is not None})
        else:
            print("Reels response type:",type(response).__name__)
    except Exception as e:
        print("Reels search:",type(e).__name__)
    print("NO writes. NO credentials/session exported.")


if __name__=="__main__":
    try:
        asyncio.run(asyncio.wait_for(main(),timeout=125))
    except Exception as e:
        print("Probe failed:",type(e).__name__)
        raise SystemExit(1)
