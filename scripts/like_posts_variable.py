"""Manually follow the author and like a configurable number of verified posts.

Reuses the existing session, exact-hashtag checks, and follow/like routine.
Never automatically retries write operations.
"""
import argparse
import json
import os
from pathlib import Path
import random
import re
import sys
import time
from scripts.instagram_web_recent import load_http, retrieve
from scripts.instagram_web_recent_probe import TAG
from scripts.manual_instagram_actions import (
    SafeStop, check_target_media, engagement, make_client, private_session_path,
)

MAX_LIKES_PER_RUN = 100
CODE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def markdown_report(report):
    lines = [
        "# Instagram variable-controlled like test", "",
        f"- Mode: **{report['mode']}**",
        f"- Hashtag: **#{report['hashtag']}**",
        f"- Requested new likes (IG_LIKE_COUNT): **{report['requested']}**",
        f"- Confirmed new likes: **{report['confirmed']}**",
        f"- Confirmed new follows: **{report['follows_confirmed']}**",
        f"- Already-followed/requested authors skipped: **{report['already_following']}**",
        f"- Already-liked posts skipped: **{report['already_liked']}**",
        f"- Other posts skipped: **{report['skipped']}**",
        "- Selection: newest verified posts first; no 24-hour cutoff",
        "",
        "| Post | Result |", "|---|---|",
    ]
    for item in report["results"]:
        lines.append(f"| [View post]({item['url']}) | {item['status']}" + (f" (follow: {item['follow']})" if item.get("follow") else "") + " |")
    if report["error"]:
        lines.extend(["", f"**Status:** {report['error']}"])
    lines.extend(["", "Only Instagram-confirmed likes count.",
                  "Uncertain writes are never retried. No session data is exported."])
    return "\n".join(lines) + "\n"


def save_report(report, output_dir):
    if output_dir:
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "results.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        (folder / "results.md").write_text(markdown_report(report), encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(markdown_report(report))


def run(args):
    report = {
        "mode": args.mode, "hashtag": args.hashtag,
        "requested": args.count, "confirmed": 0, "already_liked": 0,
        "skipped": 0, "follows_confirmed": 0, "already_following": 0,
        "results": [], "error": None,
    }
    try:
        if not TAG.fullmatch(args.hashtag):
            raise SafeStop("Invalid hashtag.")
        if not 1 <= args.count <= MAX_LIKES_PER_RUN:
            raise SafeStop(f"IG_LIKE_COUNT must be 1-{MAX_LIKES_PER_RUN}.")
        with private_session_path() as session_path:
            http = load_http(session_path)
            records, pages = retrieve(http, args.hashtag, max_pages=args.max_pages)
            if any(p.get("http") != "200" for p in pages):
                raise SafeStop("Instagram hashtag retrieval unavailable.")
            distinct = {}
            for post in records:
                code, age = post.get("code"), post.get("age")
                if (isinstance(code, str) and CODE_RE.fullmatch(code)
                        and isinstance(age, (int, float)) and age >= 0):
                    if code not in distinct or age < distinct[code]["age"]:
                        distinct[code] = post
            candidates = sorted(distinct.values(), key=lambda p: p["age"])
            report["available"] = len(candidates)
            if args.mode == "preview":
                for p in candidates[:args.count]:
                    report["results"].append({
                        "url": f"https://www.instagram.com/p/{p['code']}/",
                        "status": "preview_only",
                    })
                if len(candidates) < args.count:
                    raise SafeStop(f"Only {len(candidates)} verified posts available.")
            elif args.mode == "follow_like":
                client = make_client(session_path)
                seen_authors = set()
                for p in candidates:
                    if report["confirmed"] >= args.count:
                        break
                    code = p["code"]
                    item = {"url": f"https://www.instagram.com/p/{code}/",
                            "status": "not_attempted"}
                    report["results"].append(item)
                    try:
                        pk = client.media_pk_from_code(code)
                        media = client.media_info(pk, use_cache=False)
                        target = check_target_media(
                            media, code, args.hashtag,
                            expected_user=p.get("username"),
                        )
                    except SafeStop:
                        item["status"] = "verification_failed"
                        report["skipped"] += 1
                        continue
                    except Exception:
                        item["status"] = "read_failed"
                        report["skipped"] += 1
                        continue
                    if str(client.user_id) == target["uid"]:
                        item["status"] = "own_post_skipped"
                        report["skipped"] += 1
                        continue
                    if target["uid"] in seen_authors:
                        item["status"] = "duplicate_author_skipped"
                        report["skipped"] += 1
                        continue
                    state = getattr(media, "has_liked", None)
                    if state is True:
                        item["status"] = "already_liked"
                        report["already_liked"] += 1
                        continue
                    if state is not False:
                        item["status"] = "like_state_unknown"
                        report["skipped"] += 1
                        continue
                    try:
                        relationship = client.user_friendship_v1(target["uid"])
                    except Exception as exc:
                        raise SafeStop(
                            "Could not verify follow state (" + type(exc).__name__ + ")."
                        ) from None
                    if relationship is None:
                        raise SafeStop("Follow state unavailable; stopped without writes.")
                    if (getattr(relationship, "following", False) or
                            getattr(relationship, "outgoing_request", False)):
                        item["status"] = "already_following_or_requested"
                        report["already_following"] += 1
                        continue
                    seen_authors.add(target["uid"])
                    outcome = engagement(
                        client, code, args.hashtag, expected_user=target["username"]
                    )
                    item["follow"] = outcome.get("follow", "not_attempted")
                    item["like"] = outcome.get("like", "not_attempted")
                    item["status"] = outcome.get("like", "not_attempted")
                    if item["follow"] == "confirmed":
                        report["follows_confirmed"] += 1
                    if item["like"] == "confirmed":
                        report["confirmed"] += 1
                    if outcome.get("error") or item["follow"] != "confirmed" or item["like"] != "confirmed":
                        raise SafeStop(
                            "Follow/like did not fully confirm; stopped without retry."
                        )
                    if report["confirmed"] < args.count:
                        time.sleep(random.uniform(4, 8))
                if report["confirmed"] < args.count or report["follows_confirmed"] < args.count:
                    raise SafeStop(
                        f"Only {report['follows_confirmed']} follows and "
                        f"{report['confirmed']} likes confirmed of {args.count} requested."
                    )
            else:
                raise SafeStop("Unknown mode.")
    except SafeStop as exc:
        report["error"] = str(exc)
    except Exception as exc:
        report["error"] = "Stopped (" + type(exc).__name__ + ")."
    save_report(report, args.output_dir)
    print(f"Mode={args.mode} requested={args.count} confirmed={report['confirmed']}")
    if report["error"]:
        print("Stopped:", report["error"])
        return 2
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["preview", "follow_like"], default="preview")
    parser.add_argument("--count", type=int, default=os.environ.get("IG_LIKE_COUNT", "2"))
    parser.add_argument("--hashtag", default="followforfollow")
    parser.add_argument("--max-pages", type=int, choices=[1, 2, 3], default=3)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    args.hashtag = args.hashtag.lower().lstrip("#")
    return args


if __name__ == "__main__":
    sys.exit(run(parse_args()))
