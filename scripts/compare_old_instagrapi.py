"""Read-only old-instagram-client comparison with the saved aiograpi session.

One authenticated profile check followed by one recent-hashtag call. No login,
session writes, likes, follows, proxy configuration, or raw response logging.
"""
import argparse
import importlib.metadata
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SESSION=Path.home()/".instagram_runner"/"aiograpi-session.json"
OLD_DEVICE={
    "app_version":"439.0.0.43.89",
    "android_version":"35",
    "android_release":"15",
    "dpi":"495dpi",
    "resolution":"1280x2856",
    "manufacturer":"Google",
    "device":"caiman",
    "model":"Pixel 9 Pro",
    "cpu":"google_tensor_g4",
    "version_code":"638914275",
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag",default="follow_for_follow")
    parser.add_argument("--amount",type=int,default=6)
    args=parser.parse_args()
    tag=args.tag.lstrip("#").lower()
    if not re.fullmatch(r"[a-z0-9_]{1,60}",tag) or not 1<=args.amount<=12:
        parser.error("Provide one valid hashtag and between 1 and 12 posts")
    if not SESSION.is_file():
        print("Saved local session missing. No login attempted.")
        return 2

    logging.disable(logging.CRITICAL)
    from instagrapi import Client
    print("Old library version:",importlib.metadata.version("instagrapi"))
    cl=Client(with_challenge_flow=False)
    cl.set_device(OLD_DEVICE)
    before=dict(cl.device_settings)
    cl.load_settings(SESSION)
    after=dict(cl.device_settings)
    print("Device settings changed after load_settings:",before!=after)
    print("Saved app version equals old manually set version:",after.get("app_version")==OLD_DEVICE["app_version"])
    print("Saved device model equals old Pixel setting:",after.get("model")==OLD_DEVICE["model"])
    try:
        info=cl.account_info()
    except Exception as exc:
        print("Old library authenticated read failed:",type(exc).__name__)
        print("No new password login attempted. Saved session was not changed.")
        return 2
    print("Old library authenticated read: PASS")
    if not getattr(info,"username",None):
        print("No authenticated username returned.")
        return 2
    try:
        medias=cl.hashtag_medias_recent(tag,amount=args.amount)
    except Exception as exc:
        print("Old library hashtag read failed:",type(exc).__name__)
        print("No automatic recovery or second login.")
        return 2
    print("Endpoint: same private tags/{tag}/sections/ recent feed")
    print("Hashtag:",f"#{tag}")
    print("Returned media:",len(medias))
    for media in medias:
        taken=getattr(media,"taken_at",None)
        if isinstance(taken,datetime):
            if taken.tzinfo is None:
                taken=taken.replace(tzinfo=timezone.utc)
            age=(datetime.now(timezone.utc)-taken.astimezone(timezone.utc)).total_seconds()/3600
        else:
            age=None
        code=getattr(media,"code",None)
        print("Post age hours:",round(age,2) if age is not None else "unknown",
              "url:", f"https://www.instagram.com/p/{code}/" if isinstance(code,str) and re.fullmatch(r"[A-Za-z0-9_-]+",code) else "unknown")
    print("No likes, follows, session export, or new authentication.")
    return 0


if __name__=="__main__":
    sys.exit(main())
