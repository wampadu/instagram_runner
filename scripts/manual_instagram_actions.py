"""Automated Instagram GitHub Actions job with hashtag cycling and random delays."""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import html
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import random

from scripts.instagram_web_recent import load_http, retrieve
from scripts.instagram_web_recent_probe import SESSION, TAG
from scripts.instagram_web_recent_probe import verified as web_verified

EXPECTED_ACCOUNT = "follow_back_aswell"
POST_URL_RE = re.compile(
    r"^https://(?:www\.)?instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)/?(?:\?[^#]*)?$",
    re.I,
)
USER_RE = re.compile(r"^[A-Za-z0-9_.]{1,30}$")

HASHTAG_POOL = [
    "followforfollow",
    "likeforlike",
    "likeforfollow",
    "follow4follow",
    "like4like"
]

class SafeStop(Exception):
    """Known failure with no sensitive exception text."""

def contains_tag(caption, tag):
    return isinstance(caption, str) and bool(re.search(
        r"(?<!\w)#" + re.escape(tag) + r"(?!\w)", caption, re.I
    ))

def age_hours(value, now=None):
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - value.astimezone(timezone.utc)).total_seconds() / 3600

def check_target_media(media, code, tag, expected_user=None):
    if getattr(media, "code", None) != code:
        raise SafeStop("Media shortcode verification failed.")
    user = getattr(media, "user", None)
    username = getattr(user, "username", None)
    uid = getattr(user, "pk", None)
    if not isinstance(username, str) or not USER_RE.fullmatch(username):
        raise SafeStop("Post author cannot be verified.")
    if not uid or not str(uid).isdigit():
        raise SafeStop("Post author ID cannot be verified.")
    if expected_user and expected_user.lower() != username.lower():
        raise SafeStop("Post author differs from the web discovery result.")
    if getattr(user, "is_private", False):
        raise SafeStop("This action requires a public post author.")
    if not contains_tag(getattr(media, "caption_text", None), tag):
        raise SafeStop("Post caption does not contain the exact requested hashtag.")
    age = age_hours(getattr(media, "taken_at", None))
    if age is None or age < 0:
        raise SafeStop("Post timestamp is invalid or in the future.")
    media_id = getattr(media, "id", None)
    if not isinstance(media_id, str) or not re.fullmatch(r"[0-9]+_[0-9]+", media_id):
        raise SafeStop("Media ID is missing or unexpected.")
    return {
        "username": username,
        "uid": str(uid),
        "media_id": media_id,
        "code": code,
        "age_hours": round(age, 2),
        "url": f"https://instagram.com{code}/",
    }

@contextmanager
def private_session_path():
    raw = os.environ.get("IG_SESSION_JSON", "")
    packed = os.environ.get("IG_SESSION_GZIP_B64", "")
    if raw or packed:
        try:
            if packed:
                compressed = base64.b64decode(packed, validate=True)
                if len(compressed) > 50_000:
                    raise ValueError("Compressed session too large")
                with gzip.GzipFile(fileobj=__import__("io").BytesIO(compressed)) as g:
                    body = g.read(200_001)
                if len(body) > 200_000:
                    raise ValueError("Decompressed session too large")
                raw = body.decode("utf-8")
            payload = json.loads(raw)
            cookies = payload.get("cookies") if isinstance(payload, dict) else None
            if not isinstance(cookies, dict) or not isinstance(cookies.get("sessionid"), str):
                raise ValueError("Missing cookie")
        except (ValueError, UnicodeError, OSError) as exc:
            raise SafeStop("GitHub session secret is not a valid Instagram session.") from None
        with tempfile.TemporaryDirectory(prefix="instagram-private-",
                                         dir=os.environ.get("RUNNER_TEMP") or None) as folder:
            p = Path(folder) / "session.json"
            os.chmod(folder, 0o700)
            with p.open("w", encoding="utf-8") as f:
                os.chmod(p, 0o600)
                json.dump(payload, f)
            yield p
    elif os.environ.get("GITHUB_ACTIONS") == "true":
        raise SafeStop("Missing GitHub Actions secret: IG_SESSION_JSON or IG_SESSION_GZIP_B64.")
    elif SESSION.exists():
        yield SESSION
    else:
        raise SafeStop("Local Termux Instagram session is missing.")

def make_client(session_path):
    from client import NoReplayClient, configure
    logging.disable(logging.CRITICAL)
    cl = NoReplayClient(with_challenge_flow=False)
    cl.load_settings(session_path)
    configure(cl)
    info = cl.account_info()
    if getattr(info, "username", "").lower() != EXPECTED_ACCOUNT:
        raise SafeStop("Saved session belongs to an unexpected Instagram account.")
    return cl
def execute_single_engagement(client, code, tag, expected_user=None):
    """Performs random delays and runs structural validation before hitting follow/like endpoints."""
    result = {"follow": "not_attempted", "like": "not_attempted"}
    try:
        media_pk = client.media_pk_from_code(code)
        media = client.media_info(media_pk, use_cache=False)
        target = check_target_media(media, code, tag, expected_user)
        result.update({k:v for k,v in target.items() if k not in ("uid","media_id")})
    except Exception as exc:
        result["error"] = "Post verification failed: " + type(exc).__name__
        return result, False

    # Execute Follow Action (1-30s Delay)
    try:
        if str(client.user_id) == target["uid"]:
            return result, False
        rel = client.user_friendship_v1(target["uid"])
        if rel is None or bool(getattr(rel,"following",False)) or bool(getattr(rel,"outgoing_request",False)):
            result["follow"] = "already_following_or_requested"
        else:
            delay = random.randint(1, 30)
            print(f"Delaying {delay}s before following @{target['username']}...")
            time.sleep(delay)
            if client.user_follow(target["uid"]) is True:
                result["follow"] = "confirmed"
    except Exception as exc:
        result["follow"] = "failed"

    # Execute Like Action (1-30s Delay)
    action_success = False
    try:
        if getattr(media, "has_liked", None) is True:
            result["like"] = "already_liked"
        else:
            delay = random.randint(1, 30)
            print(f"Delaying {delay}s before liking post {code}...")
            time.sleep(delay)
            if client.media_like(target["media_id"]) is True:
                result["like"] = "confirmed"
                action_success = True
    except Exception as exc:
        result["like"] = "failed"
        
    return result, action_success

def fetch_feed_candidates(session_path, hashtag, max_pages=2):
    """Harvests target candidates using the unauthenticated recent web parser."""
    try:
        http = load_http(session_path)
        records, _ = retrieve(http, hashtag, max_pages=max_pages)
        return sorted((c for c in records if c["age"] >= 0), key=lambda c: c["age"])
    except Exception:
        return []

def run(args):
    print(f"Starting automation. Target goal: {args.target_count} interactions.")
    
    current_pool = list(HASHTAG_POOL)
    if args.hashtag in current_pool:
        current_pool.remove(args.hashtag)
    current_pool.insert(0, args.hashtag)
    
    hashtag_index = 0
    total_successful_likes = 0
    engagement_history = []
    
    try:
        with private_session_path() as session_path:
            client = make_client(session_path)
            
            while total_successful_likes < args.target_count:
                hashtag_index = (total_successful_likes // 20) % len(current_pool)
                active_hashtag = current_pool[hashtag_index]
                
                print(f"\n--- Active Feed Target: #{active_hashtag} (Progress: {total_successful_likes}/{args.target_count}) ---")
                candidates = fetch_feed_candidates(session_path, active_hashtag, args.max_pages)
                
                if not candidates:
                    print(f"Feed context for #{active_hashtag} empty or rate limited. Cycling up early.")
                    total_successful_likes = ((total_successful_likes // 20) + 1) * 20
                    continue
                
                acted_in_this_batch = False
                for target_item in candidates:
                    if total_successful_likes >= args.target_count:
                        break
                        
                    code = target_item.get("code")
                    username = target_item.get("username")
                    if not code or not username or not USER_RE.fullmatch(username):
                        continue
                        
                    res_log, success = execute_single_engagement(client, code, active_hashtag, expected_user=username)
                    engagement_history.append(res_log)
                    
                    if success:
                        total_successful_likes += 1
                        acted_in_this_batch = True
                        print(f"Successfully processed engagement pair. Total counter: {total_successful_likes}")
                
                if not acted_in_this_batch:
                    print("No fresh interactive candidates left in this batch. Advancing hashtag tier.")
                    total_successful_likes = ((total_successful_likes // 20) + 1) * 20

    except SafeStop as exc:
        print(f"Stopped safely: {exc}")
    except Exception as exc:
        print(f"Unexpected termination: {type(exc).__name__}")
        
    print(f"\nAutomation cycle concluded. Completed actions: {total_successful_likes}")
    return 0

def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hashtag", default="follow_for_follow")
    p.add_argument("--target-count", type=int, default=5)
    p.add_argument("--max-pages", type=int, default=3)
    p.add_argument("--output-dir", default="")
    args = p.parse_args()
    args.hashtag = args.hashtag.lower().lstrip("#")
    return args

if __name__ == "__main__":
    sys.exit(run(parse_args()))
    
