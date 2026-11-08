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

COOLDOWN_AFTER_PAIRS = 50
COOLDOWN_MIN_SECONDS = 10 * 60
COOLDOWN_MAX_SECONDS = 13 * 60

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
        "url": f"https://www.instagram.com/p/{code}/",
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
    """Attempt one verified NEW follow+like pair; never retry uncertain writes."""
    result = {"follow": "not_attempted", "like": "not_attempted",
              "code": code, "hashtag": tag}
    try:
        media_pk = client.media_pk_from_code(code)
        media = client.media_info(media_pk, use_cache=False)
        target = check_target_media(media, code, tag, expected_user)
        result["username"] = target["username"]
        result["url"] = target["url"]
        if str(client.user_id) == target["uid"]:
            result["status"] = "own_post_skipped"
            return result, False
        # Both actions must be genuinely new.
        if getattr(media, "has_liked", None) is True:
            result["status"] = "already_liked"
            return result, False
        if getattr(media, "has_liked", None) is not False:
            result["status"] = "like_state_unknown"
            return result, False
        relationship = client.user_friendship_v1(target["uid"])
        if relationship is None:
            raise SafeStop("Follow state unavailable.")
        if (getattr(relationship, "following", False)
                or getattr(relationship, "outgoing_request", False)):
            result["status"] = "already_following_or_requested"
            return result, False
    except SafeStop as exc:
        result["status"] = "verification_skipped"
        result["reason"] = str(exc)
        return result, False
    except Exception as exc:
        result["status"] = "read_skipped"
        result["reason"] = type(exc).__name__
        return result, False

    try:
        time.sleep(random.uniform(1, 30))
        if client.user_follow(target["uid"]) is not True:
            result["follow"] = "unconfirmed"
            result["error"] = "Instagram did not confirm the follow."
            return result, False
        result["follow"] = "confirmed"
    except Exception as exc:
        kind = type(exc).__name__
        if kind == "FeedbackRequired":
            result["follow"] = "blocked"
            result["restriction"] = "instagram_action_restriction"
            result["error"] = (
                "Instagram rejected the follow (FeedbackRequired). "
                "Stop automated follows and review the account in Instagram. "
                "Do not retry while restricted."
            )
        else:
            result["follow"] = "uncertain"
            result["error"] = "Follow outcome uncertain (" + kind + ")."
        return result, False

    try:
        time.sleep(random.uniform(1, 30))
        if client.media_like(target["media_id"]) is not True:
            result["like"] = "unconfirmed"
            result["error"] = "Instagram did not confirm the like."
            return result, False
        result["like"] = "confirmed"
        result["status"] = "confirmed"
        return result, True
    except Exception as exc:
        kind = type(exc).__name__
        if kind == "FeedbackRequired":
            result["like"] = "blocked"
            result["restriction"] = "instagram_action_restriction"
            result["error"] = (
                "Instagram rejected the like (FeedbackRequired). "
                "Stop automated likes and review the account in Instagram. "
                "Do not retry while restricted."
            )
        else:
            result["like"] = "uncertain"
            result["error"] = "Like outcome uncertain (" + kind + ")."
        return result, False
def fetch_feed_candidates(session_path, hashtag, max_pages=2):
    """Get verified hashtag posts; do not silently treat fetch errors as zero."""
    http = load_http(session_path)
    records, pages = retrieve(http, hashtag, max_pages=max_pages)
    if not pages or any(p.get("http") != "200" for p in pages):
        raise SafeStop("Hashtag discovery unavailable for #" + hashtag + ".")
    distinct = {}
    for item in records:
        code, age = item.get("code"), item.get("age")
        if (isinstance(code, str) and isinstance(age, (int, float))
                and age >= 0 and (code not in distinct or age < distinct[code]["age"])):
            distinct[code] = item
    return sorted(distinct.values(), key=lambda item: item["age"])
def run(args):
    """Engage verified new authors in 20-pair hashtag batches.

    Skip exhausted hashtags rather than counting missing engagements as successes.
    A bounded second pass can use fresh, still-untried candidates from earlier tags.
    """
    count = args.target_count
    report = {
        "requested": count, "confirmed_likes": 0, "confirmed_follows": 0,
        "batches": [], "results": [], "cooldowns": [], "skipped": 0, "error": None,
    }
    try:
        if not isinstance(count, int) or not 1 <= count <= 100:
            raise SafeStop("Target count must be between 1 and 100.")
        if not TAG.fullmatch(args.hashtag):
            raise SafeStop("Invalid starting hashtag.")
        # Fixed daily sessions must never spill into another session's tag.
        # Existing multi-tag mode remains available for other callers.
        single_hashtag = getattr(args, "single_hashtag", False)
        current_pool = (
            [args.hashtag] if single_hashtag
            else [args.hashtag] + [tag for tag in HASHTAG_POOL if tag != args.hashtag]
        )
        with private_session_path() as session_path:
            client = make_client(session_path)
            seen_posts, seen_authors = set(), set()
            # A finite limit prevents repeated polling when no useful posts remain.
            for pass_number in range(1, 2 if single_hashtag else 6):
                if report["confirmed_likes"] >= count:
                    break
                progress_in_pass = 0
                for tag in current_pool:
                    remaining = count - report["confirmed_likes"]
                    if remaining <= 0:
                        break
                    quota = min(20, remaining)
                    batch = {
                        "pass": pass_number, "hashtag": tag, "requested": quota,
                        "confirmed_likes": 0, "confirmed_follows": 0,
                        "available": 0, "skipped": 0, "status": "pending",
                    }
                    report["batches"].append(batch)
                    try:
                        candidates = fetch_feed_candidates(
                            session_path, tag, args.max_pages
                        )
                    except SafeStop:
                        # A failed/blocked HTTP retrieval is not an empty feed.
                        raise
                    except Exception as exc:
                        raise SafeStop(
                            f"Feed read failed for #{tag} ({type(exc).__name__})."
                        ) from None
                    batch["available"] = len(candidates)
                    if not candidates:
                        batch["status"] = "no_candidates"
                        continue
                    for item in candidates:
                        if batch["confirmed_likes"] >= quota:
                            break
                        code, username = item.get("code"), item.get("username")
                        if (not isinstance(code, str)
                                or not isinstance(username, str)
                                or not USER_RE.fullmatch(username)
                                or code in seen_posts
                                or username.lower() in seen_authors):
                            report["skipped"] += 1
                            batch["skipped"] += 1
                            continue
                        # Do not repeat a post or author, even if the first read
                        # found that they were already followed or liked.
                        seen_posts.add(code)
                        seen_authors.add(username.lower())
                        outcome, succeeded = execute_single_engagement(
                            client, code, tag, expected_user=username
                        )
                        report["results"].append(outcome)
                        if outcome.get("follow") == "confirmed":
                            report["confirmed_follows"] += 1
                            batch["confirmed_follows"] += 1
                        if outcome.get("like") == "confirmed":
                            report["confirmed_likes"] += 1
                            batch["confirmed_likes"] += 1
                        if outcome.get("error"):
                            batch["status"] = "unconfirmed_write"
                            raise SafeStop(
                                "Action stopped on #" + tag + ": " +
                                outcome["error"]
                            )
                        if succeeded:
                            progress_in_pass += 1
                            # Count only confirmed NEW follow+like pairs.
                            # Do not delay after the final requested pair.
                            if (report["confirmed_likes"] % COOLDOWN_AFTER_PAIRS == 0
                                    and report["confirmed_likes"] < count):
                                seconds = random.uniform(
                                    COOLDOWN_MIN_SECONDS, COOLDOWN_MAX_SECONDS
                                )
                                cooldown = {
                                    "after_confirmed_pairs": report["confirmed_likes"],
                                    "seconds": round(seconds, 1),
                                    "status": "started",
                                }
                                report["cooldowns"].append(cooldown)
                                print(
                                    f"Cooldown after {report['confirmed_likes']} "
                                    f"confirmed pairs: {seconds / 60:.2f} minutes",
                                    flush=True,
                                )
                                time.sleep(seconds)
                                cooldown["status"] = "completed"
                        else:
                            report["skipped"] += 1
                            batch["skipped"] += 1
                    batch["status"] = (
                        "complete" if batch["confirmed_likes"] == quota
                        else "partial_or_exhausted"
                    )
                    # Missing engagements never increase the global counter.
                    # Continue to the next hashtag, carrying the unmet target.
                if report["confirmed_likes"] >= count:
                    break
                if progress_in_pass == 0:
                    raise SafeStop(
                        "No more eligible new follow-and-like pairs found "
                        "across the available hashtags; remaining target: " +
                        str(count - report["confirmed_likes"]) + "."
                    )
            if report["confirmed_likes"] < count:
                raise SafeStop(
                    "Stopped after five hashtag passes with " +
                    str(report["confirmed_likes"]) + "/" + str(count) +
                    " confirmed new likes; no missing actions were counted."
                )
    except SafeStop as exc:
        report["error"] = str(exc)
    except Exception as exc:
        report["error"] = "Stopped (" + type(exc).__name__ + ")."

    if args.output_dir:
        target = Path(args.output_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / "results.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        summary_lines = [
            "# Instagram engagement cycle", "",
            f"- Requested new follow+like pairs: {report['requested']}",
            f"- Confirmed new follows: {report['confirmed_follows']}",
            f"- Confirmed new likes: {report['confirmed_likes']}",
            f"- Skipped: {report['skipped']}",
            f"- Cooldowns taken: {len(report['cooldowns'])}",
            f"- Restriction detected: {'yes' if any(r.get('restriction') for r in report['results']) else 'no'}", "",
            "| Pass | Hashtag | Target | New follows | New likes | Candidates | Status |",
            "|---:|---|---:|---:|---:|---:|---|",
        ]
        for batch in report["batches"]:
            summary_lines.append(
                f"| {batch['pass']} | #{batch['hashtag']} | {batch['requested']} "
                f"| {batch['confirmed_follows']} | {batch['confirmed_likes']} "
                f"| {batch['available']} | {batch['status']} |"
            )
        for cooldown in report["cooldowns"]:
            summary_lines.append(
                f"- Cooldown after {cooldown['after_confirmed_pairs']} pairs: "
                f"{cooldown['seconds'] / 60:.2f} minutes "
                f"({cooldown['status']})"
            )
        if report["error"]:
            summary_lines.append("\n**Stopped:** " + report["error"])
            if any(r.get("restriction") for r in report["results"]):
                summary_lines.append(
                    "\n**Instagram-side restriction:** No automatic retry was made. "
                    "Daily live activity should remain paused until the account "
                    "can follow normally from the Instagram app."
                )
        summary_lines.append(
            "\nUnconfirmed writes are not retried. Missing posts do not "
            "advance the count."
        )
        summary = "\n".join(summary_lines) + "\n"
        (target / "results.md").write_text(summary, encoding="utf-8")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
                out.write(summary)
    print(
        f"Requested={count} confirmed_follows={report['confirmed_follows']} "
        f"confirmed_likes={report['confirmed_likes']} skipped={report['skipped']}"
    )
    if report["error"]:
        print("Stopped:", report["error"])
        return 2
    return 0


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hashtag", default="followforfollow")
    p.add_argument(
        "--single-hashtag", action="store_true",
        help="Limit the entire run to exactly the supplied hashtag"
    )
    p.add_argument("--target-count", type=int, default=2)
    p.add_argument("--max-pages", type=int, choices=(1, 2, 3), default=3)
    p.add_argument("--output-dir", default="")
    args = p.parse_args()
    args.hashtag = args.hashtag.lower().lstrip("#")
    return args

if __name__ == "__main__":
    sys.exit(run(parse_args()))
    
