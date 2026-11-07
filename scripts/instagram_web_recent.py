"""Free Instagram web Recent hashtag discovery via existing private Termux login.

No Meta developer app, extra API keys, purchases, passwords or saved-session
exports. Uses the working browser-web endpoint; NOT the Android private API.
Read-only and does not perform follow/like/comment actions.

Important: Instagram can rank/filter returned items. Sorting *retrieved* posts
by timestamp is not proof of a complete chronological hashtag feed.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import requests
from scripts.instagram_web_recent_probe import (
    SESSION, BASE, HEADERS, TAG, request_once, media_from_container, verified
)


def load_http(session_path=SESSION):
    session_path=Path(session_path)
    if not session_path.is_file():
        raise ValueError("Saved Termux session missing")
    with session_path.open("r") as f:
        saved=json.load(f)
    cookies=saved.get("cookies")
    if not isinstance(cookies,dict) or not isinstance(cookies.get("sessionid"),str):
        raise ValueError("Saved session is missing sessionid cookie")
    http=requests.Session()
    http.headers.update(HEADERS)
    for name in ("sessionid","csrftoken","ds_user_id","mid","ig_did","rur"):
        value=cookies.get(name)
        if isinstance(value,str) and value:
            http.cookies.set(name,value,domain=".instagram.com",path="/",secure=True)
    csrf=cookies.get("csrftoken")
    if isinstance(csrf,str) and csrf:
        http.headers["x-csrftoken"]=csrf
    return http


def parse_page(result, tag):
    raw=media_from_container(result)
    out={}
    for m in raw:
        rec=verified(m,tag)
        if rec and rec["code"] not in out:
            out[rec["code"]]=rec
    return list(out.values()),len(raw)


def retrieve(http, tag, max_pages=2):
    """Returns posts, metadata; no refresh, retries or engagement actions."""
    if not TAG.fullmatch(tag) or not 1<=max_pages<=3:
        raise ValueError("Invalid tag or number of pages")
    base={"supported_tabs":json.dumps(["top","recent","clips"]),"tab":"recent"}
    records={}
    metadata=[]
    seen_cursors=set()
    for page in range(max_pages):
        form=base.copy()
        if metadata:
            old=metadata[-1]
            if not old["has_more"] or not old["cursor"]:
                break
            if old["cursor"] in seen_cursors:
                break
            seen_cursors.add(old["cursor"])
            form["max_id"]=old["cursor"]
            if old["next_media_ids"] is not None:
                form["next_media_ids"]=json.dumps(old["next_media_ids"])
        response=request_once(http,"POST",f"/api/v1/tags/{tag}/sections/",data=form)
        if response["status"]!="200":
            metadata.append({"http":response["status"],"has_more":False,"cursor":None,"next_media_ids":None,"raw":0})
            break
        raw=response["data"]
        if not isinstance(raw,dict):
            metadata.append({"http":"non-object-json","has_more":False,"cursor":None,"next_media_ids":None,"raw":0})
            break
        matches,raw_n=parse_page(raw,tag)
        for row in matches:
            records[row["code"]]=row
        metadata.append({
            "http":"200",
            "has_more":bool(raw.get("more_available")),
            "cursor":raw.get("next_max_id") if isinstance(raw.get("next_max_id"),str) else None,
            "next_media_ids":raw.get("next_media_ids"),
            "raw":raw_n,
            "verified":len(matches),
        })
        if not raw.get("more_available") or not raw.get("next_max_id"):
            break
    return sorted(records.values(),key=lambda item:item["age"]), metadata


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("hashtag",nargs="?",default="follow_for_follow")
    p.add_argument("--max-pages",type=int,default=2,choices=(1,2,3))
    p.add_argument("--hours",type=int,default=168)
    args=p.parse_args()
    tag=args.hashtag.lower().lstrip("#")
    if not TAG.fullmatch(tag) or not 1<=args.hours<=168:
        p.error("One valid hashtag and age window of 1-168 hours")
    try:
        http=load_http()
        matches,pages=retrieve(http,tag,args.max_pages)
    except Exception as exc:
        print("Web read stopped:",type(exc).__name__,"(session details withheld)")
        return 2
    print("Hashtag:", "#"+tag)
    print("Free source: authenticated Instagram web endpoint, no Meta API key")
    print("Pages:",len(pages),"HTTP statuses:",[x["http"] for x in pages])
    print("Candidates:",sum(x["raw"] for x in pages),"Exact-caption-tag posts:",len(matches))
    within=[m for m in matches if m["age"]<=args.hours]
    print(f"Verified posts within {args.hours}h:",len(within))
    for m in within[:30]:
        print(f"@{m['username']} | {m['age']:.2f}h | https://www.instagram.com/p/{m['code']}/")
    if not within:
        if matches:
            print("Newest verified accessible post:",matches[0]["age"],"hours ago")
        print("Instagram returned no exact-tag posts within that age in this sample.")
    if pages and pages[-1]["has_more"] and pages[-1]["cursor"]:
        print("Further pages may be available; completeness NOT guaranteed.")
    print("No like/follow/comment, no secret printed, no session uploaded.")
    return 0 if within else 3


if __name__ == "__main__":
    sys.exit(main())
