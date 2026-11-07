"""Read-only browser-web Instagram endpoint probe, using private local session.

No new account, Meta app, API key, developer login, proxy, follow, like, or
password. Never prints/stores cookies, CSRF token, body, headers, sessionid,
Instagram internal IDs, or raw JSON. Requests ONLY www.instagram.com.
Tests distinct web endpoints (not instagrapi's Android mobile transport).
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

SESSION = Path.home() / ".instagram_runner" / "aiograpi-session.json"
TAG = re.compile(r"^[a-z0-9_]{1,60}$")
CODE = re.compile(r"^[A-Za-z0-9_-]+$")
BASE = "https://www.instagram.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "x-ig-app-id": "936619743392459",
    "x-requested-with": "XMLHttpRequest",
    "Accept": "*/*",
    "Origin": BASE,
    "Referer": BASE + "/",
}


def verified(media, tag):
    if not isinstance(media, dict):
        return None
    caption=media.get("caption")
    if isinstance(caption,dict):
        caption=caption.get("text")
    if not isinstance(caption,str):
        return None
    if not re.search(r"(?<!\w)#"+re.escape(tag)+r"(?!\w)", caption, re.I):
        return None
    code=media.get("code")
    if not isinstance(code,str) or not CODE.fullmatch(code):
        return None
    when=media.get("taken_at")
    if isinstance(when,(int,float)):
        dt=datetime.fromtimestamp(when,timezone.utc)
    else:
        value=media.get("taken_at_iso")
        try:
            dt=datetime.fromisoformat(value.replace("Z","+00:00"))
            if dt.tzinfo is None:
                dt=dt.replace(tzinfo=timezone.utc)
        except (AttributeError,ValueError):
            return None
    age=(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds()/3600
    if age < 0:
        return None
    user=media.get("user") or {}
    return {"code":code, "age":age,
            "username":str(user.get("username") or "(unavailable)")}


def media_from_container(data):
    if not isinstance(data,dict):
        return []
    sections=data.get("sections")
    if not isinstance(sections,list):
        sections=data.get("sectional_items") or []
    medias=[]
    for section in sections:
        if not isinstance(section,dict):
            continue
        lc=section.get("layout_content") or {}
        if not isinstance(lc,dict):
            continue
        pools=[lc.get("medias") or [],lc.get("fill_items") or []]
        one=lc.get("one_by_two_item") or {}
        if isinstance(one,dict):
            clip=one.get("clips") or {}
            if isinstance(clip,dict):
                pools.append(clip.get("items") or [])
        for pool in pools:
            if isinstance(pool,list):
                for elem in pool:
                    if isinstance(elem,dict):
                        m=elem.get("media")
                        medias.append(m if isinstance(m,dict) else elem)
    for k in ("items","ranked_items"):
        pool=data.get(k)
        if isinstance(pool,list):
            for p in pool:
                if isinstance(p,dict):
                    m=p.get("media")
                    medias.append(m if isinstance(m,dict) else p)
    return medias


def request_once(http, method, path, data=None, params=None):
    if not path.startswith("/api/v1/") or ".." in path:
        raise ValueError("Bad Instagram web path")
    try:
        if method=="POST":
            r=http.post(BASE+path, data=data, timeout=22,allow_redirects=False)
        else:
            r=http.get(BASE+path, params=params, timeout=22,allow_redirects=False)
    except requests.RequestException as exc:
        return {"status":"transport:"+type(exc).__name__, "data":None}
    if r.status_code != 200:
        return {"status":str(r.status_code), "data":None}
    try:
        return {"status":str(r.status_code),"data":r.json()}
    except ValueError:
        return {"status":"200-non-JSON","data":None}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tag",default="follow_for_follow")
    args=p.parse_args()
    tag=args.tag.lower().lstrip("#")
    if not TAG.fullmatch(tag):
        p.error("Invalid exact hashtag")
    if not SESSION.is_file():
        print("Saved local session missing; no login attempted.")
        return 2
    with SESSION.open("r") as f:
        settings=json.load(f)
    cookies=settings.get("cookies")
    if not isinstance(cookies,dict) or not cookies.get("sessionid"):
        print("Saved Android session does not include reusable web cookies.")
        return 3
    http=requests.Session()
    http.headers.update(HEADERS)
    for name in ("sessionid","csrftoken","ds_user_id","mid","ig_did","rur"):
        value=cookies.get(name)
        if isinstance(value,str) and value:
            http.cookies.set(name,value,domain=".instagram.com",path="/",secure=True)
    csrf=cookies.get("csrftoken")
    if isinstance(csrf,str) and csrf:
        http.headers["x-csrftoken"]=csrf

    print("Using local Instagram session cookies in memory; web API, no Meta token.")
    print("Tag:", "#"+tag)
    endpoints=[
        ("recent-web","POST",f"/api/v1/tags/{quote(tag)}/sections/",
         {"supported_tabs":json.dumps(["top","recent","clips"]),"tab":"recent"},None),
        ("clips-web","POST",f"/api/v1/tags/{quote(tag)}/sections/",
         {"supported_tabs":json.dumps(["top","recent","clips"]),"tab":"clips"},None),
        ("keyword-web","GET","/api/v1/discover/web/explore_grid/",None,
         {"_d":"clips_search","q":tag,"include_fixed_destinations":"true","omit_cover_media":"true"}),
    ]
    any_match=False
    for label,method,path,data,params in endpoints:
        response=request_once(http,method,path,data,params)
        container=response["data"]
        media=media_from_container(container)
        seen={}
        for item in media:
            record=verified(item,tag)
            if record:
                seen[record["code"]]=record
        records=sorted(seen.values(),key=lambda x:x["age"])
        print(label,"HTTP:",response["status"],
              "sections:",len(container.get("sections") or []) if isinstance(container,dict) else "n/a",
              "media candidates:",len(media),
              "exact-tag verified:",len(records),
              "within 24h:",sum(x["age"]<=24 for x in records))
        for record in records[:10]:
            print("  ",record["age"],"hours @"+record["username"],
                  "https://www.instagram.com/p/"+record["code"]+"/")
        if records:
            any_match=True
        if response["status"] in ("401","403","429"):
            print("Session rejected or rate-limited; stopping without retry.")
            break
    print("No passwords/session/API keys printed or uploaded. No write actions.")
    return 0 if any_match else 3


if __name__=="__main__":
    sys.exit(main())
