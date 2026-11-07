"""Follow and like posts across five hashtag batches (20 confirmed likes each).

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

HASHTAGS = ("followforfollow", "likeforlike", "likeforfollow", "follow4follow", "like4like")
LIKES_PER_HASHTAG = 20
MAX_LIKES_PER_RUN = len(HASHTAGS) * LIKES_PER_HASHTAG
CODE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def hashtag_plan(total):
    """Plan batches of 20 confirmed likes each, in fixed hashtag order."""
    if not isinstance(total, int) or not 1 <= total <= MAX_LIKES_PER_RUN:
        raise SafeStop(f"IG_LIKE_COUNT must be 1-{MAX_LIKES_PER_RUN}.")
    return [(tag, min(LIKES_PER_HASHTAG, total - i * LIKES_PER_HASHTAG))
            for i, tag in enumerate(HASHTAGS)
            if total > i * LIKES_PER_HASHTAG]


def newest_unique(records):
    posts = {}
    for item in records:
        code, age = item.get("code"), item.get("age")
        if (isinstance(code, str) and CODE_RE.fullmatch(code)
                and isinstance(age, (int, float)) and age >= 0):
            if code not in posts or age < posts[code]["age"]:
                posts[code] = item
    return sorted(posts.values(), key=lambda item: item["age"])


def markdown_report(report):
    lines = [
        "# Instagram five-hashtag rotation", "",
        f"- Mode: **{report['mode']}**",
        f"- Requested new likes: **{report['requested']}**",
        f"- Confirmed new likes: **{report['confirmed']}**",
        f"- Confirmed new follows: **{report['follows_confirmed']}**",
        f"- Hashtag batch size: **{LIKES_PER_HASHTAG} confirmed likes**",
        f"- Already-followed/requested authors skipped: **{report['already_following']}**",
        f"- Already-liked posts skipped: **{report['already_liked']}**",
        f"- Other posts skipped: **{report['skipped']}**",
        "- Newest verified posts first; no age cutoff", "",
        "| Hashtag | Requested | Confirmed likes | Confirmed follows | Available |",
        "|---|---:|---:|---:|---:|",
    ]
    for batch in report["batches"]:
        lines.append(
            f"| #{batch['hashtag']} | {batch['quota']} | {batch['confirmed']} "
            f"| {batch['follows_confirmed']} | {batch['available']} |"
        )
    lines.extend(["", "| Hashtag | Post | Like | Follow |", "|---|---|---|---|"])
    for item in report["results"]:
        lines.append(
            f"| #{item['hashtag']} | [View post]({item['url']}) | "
            f"{item['status']} | {item.get('follow', 'not_attempted')} |"
        )
    if report["error"]:
        lines.extend(["", f"**Status:** {report['error']}"])
    lines.extend(["", "Only confirmed new likes advance the hashtag counter.",
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
        "mode": args.mode, "requested": args.count, "confirmed": 0,
        "follows_confirmed": 0, "already_liked": 0, "already_following": 0,
        "skipped": 0, "results": [], "batches": [], "error": None,
    }
    try:
        plan = hashtag_plan(args.count)
        with private_session_path() as session_path:
            http = load_http(session_path)
            client = make_client(session_path) if args.mode == "follow_like" else None
            seen_authors, seen_posts = set(), set()
            for hashtag, quota in plan:
                batch = {
                    "hashtag": hashtag, "quota": quota,
                    "confirmed": 0, "follows_confirmed": 0, "available": 0,
                }
                report["batches"].append(batch)
                records, pages = retrieve(http, hashtag, max_pages=args.max_pages)
                if any(p.get("http") != "200" for p in pages):
                    raise SafeStop(f"Instagram retrieval unavailable for #{hashtag}.")
                candidates = newest_unique(records)
                batch["available"] = len(candidates)
                if args.mode == "preview":
                    for p in candidates[:quota]:
                        report["results"].append({
                            "hashtag": hashtag,
                            "url": f"https://www.instagram.com/p/{p['code']}/",
                            "status": "preview_only",
                        })
                    if len(candidates) < quota:
                        raise SafeStop(
                            f"Only {len(candidates)} posts for #{hashtag}; "
                            f"required {quota}. Rotation stopped."
                        )
                    continue
                if args.mode != "follow_like":
                    raise SafeStop("Unknown mode.")
                for p in candidates:
                    if batch["confirmed"] >= quota:
                        break
                    code = p["code"]
                    item = {
                        "hashtag": hashtag,
                        "url": f"https://www.instagram.com/p/{code}/",
                        "status": "not_attempted",
                    }
                    report["results"].append(item)
                    if code in seen_posts:
                        item["status"] = "duplicate_post_skipped"
                        report["skipped"] += 1
                        continue
                    seen_posts.add(code)
                    try:
                        pk = client.media_pk_from_code(code)
                        media = client.media_info(pk, use_cache=False)
                        target = check_target_media(
                            media, code, hashtag, expected_user=p.get("username")
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
                    if getattr(media, "has_liked", None) is True:
                        item["status"] = "already_liked"
                        report["already_liked"] += 1
                        continue
                    if getattr(media, "has_liked", None) is not False:
                        item["status"] = "like_state_unknown"
                        report["skipped"] += 1
                        continue
                    try:
                        relation = client.user_friendship_v1(target["uid"])
                    except Exception as exc:
                        raise SafeStop(
                            f"Could not verify follow state ({type(exc).__name__})."
                        ) from None
                    if relation is None:
                        raise SafeStop("Follow state unavailable; stopped.")
                    if (getattr(relation, "following", False)
                            or getattr(relation, "outgoing_request", False)):
                        item["status"] = "already_following_or_requested"
                        report["already_following"] += 1
                        continue
                    seen_authors.add(target["uid"])
                    outcome = engagement(
                        client, code, hashtag, expected_user=target["username"]
                    )
                    item["follow"] = outcome.get("follow", "not_attempted")
                    item["status"] = outcome.get("like", "not_attempted")
                    if item["follow"] == "confirmed":
                        report["follows_confirmed"] += 1
                        batch["follows_confirmed"] += 1
                    if item["status"] == "confirmed":
                        report["confirmed"] += 1
                        batch["confirmed"] += 1
                    if (outcome.get("error") or item["follow"] != "confirmed"
                            or item["status"] != "confirmed"):
                        raise SafeStop(
                            f"Follow/like for #{hashtag} was not fully confirmed; "
                            "stopped without retry."
                        )
                    if report["confirmed"] < args.count:
                        time.sleep(random.uniform(4, 8))
                if batch["confirmed"] < quota:
                    raise SafeStop(
                        f"Only {batch['confirmed']} of {quota} new likes confirmed "
                        f"for #{hashtag}. Next hashtag not started."
                    )
    except SafeStop as exc:
        report["error"] = str(exc)
    except Exception as exc:
        report["error"] = f"Stopped ({type(exc).__name__})."
    save_report(report, args.output_dir)
    print(
        f"Mode={args.mode} requested={args.count} "
        f"confirmed_likes={report['confirmed']} "
        f"confirmed_follows={report['follows_confirmed']}"
    )
    if report["error"]:
        print("Stopped:", report["error"])
        return 2
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["preview", "follow_like"], default="preview")
    parser.add_argument("--count", type=int, default=os.environ.get("IG_LIKE_COUNT", "2"))
    parser.add_argument("--max-pages", type=int, choices=[1, 2, 3], default=3)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    sys.exit(run(parse_args()))
