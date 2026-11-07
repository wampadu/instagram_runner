"""Read-only verification that the write-client can inspect a selected post.

No like/follow operations are called. Uses existing private Termux session,
or an encrypted GitHub Actions secret if configured.
"""
import argparse
import logging
import sys
from scripts.manual_instagram_actions import (
    private_session_path, make_client, post_code_from_url, check_target_media, SafeStop
)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("post_url")
    p.add_argument("--tag",default="follow_for_follow")
    p.add_argument("--hours",type=int,default=168)
    args=p.parse_args()
    code=post_code_from_url(args.post_url)
    if not code or not 1 <= args.hours <=168:
        p.error("Provide a valid Instagram post URL and hours 1-168")
    logging.disable(logging.CRITICAL)
    try:
        with private_session_path() as path:
            client=make_client(path)
            media=client.media_info(client.media_pk_from_code(code),use_cache=False)
            record=check_target_media(media,code,args.tag,args.hours)
            rel=client.user_friendship_v1(record["uid"])
            print("READ_ONLY_PREFLIGHT_PASS")
            print("Author:",record["username"],"age_hours:",record["age_hours"])
            print("Already following:",bool(getattr(rel,"following",False)))
            print("Follow request pending:",bool(getattr(rel,"outgoing_request",False)))
            print("Already liked:",getattr(media,"has_liked",None))
            print("Like/follow calls made: ZERO")
            return 0
    except SafeStop as exc:
        print("Preflight refused:",str(exc))
        return 2
    except Exception as exc:
        print("Preflight failed:",type(exc).__name__)
        return 2


if __name__=="__main__":
    sys.exit(main())
