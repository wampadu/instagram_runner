"""Daily read-only Instagram hashtag review: up to 20 DISTINCT public authors/tag.

This job is discovery only. It NEVER follows, likes, comments, logs in by
password, bypasses Instagram challenges, or retries rate-limited responses.
Existing GitHub Actions Instagram session is read from an encrypted secret.

Returned Instagram web "recent" items may be incomplete or ranked. Candidates
are sorted by real publication time; no post-age cutoff is applied.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from zoneinfo import ZoneInfo

from scripts.instagram_web_recent import load_http, retrieve
from scripts.manual_instagram_actions import private_session_path, USER_RE, SafeStop

HASHTAGS = (
    "followforfollow",
    "likeforlike",
    "likeforfollow",
    "follow4follow",
    "like4like",
)
PER_HASHTAG = 20
TORONTO = ZoneInfo("America/Toronto")
CODE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def select_distinct_authors(records, *, existing=None, per_tag=PER_HASHTAG):
    """Keep only a creator's newest qualifying post, unique across the batch."""
    taken = existing if existing is not None else set()
    candidates = []
    for entry in sorted(records, key=lambda item: item.get("age", float("inf"))):
        username = entry.get("username")
        code = entry.get("code")
        age = entry.get("age")
        if (
            not isinstance(username, str)
            or not USER_RE.fullmatch(username)
            or not isinstance(code, str)
            or not CODE_RE.fullmatch(code)
            or not isinstance(age, (int, float))
            or not 0 <= age < float("inf")
        ):
            continue
        lowered = username.lower()
        if lowered in taken:
            continue
        taken.add(lowered)
        candidates.append({
            "username": username,
            "age_hours": round(age, 2),
            "post_url": "https://www.instagram.com/p/" + code + "/",
            "profile_url": "https://www.instagram.com/" + username + "/",
        })
        if len(candidates) >= per_tag:
            break
    return candidates


def build_report(fetch, *, tags=HASHTAGS, per_tag=PER_HASHTAG):
    """fetch(tag) returns (verified_posts, pages); no engagement functions used."""
    seen_accounts = set()
    per_hashtag = []
    errors = []
    for tag in tags:
        try:
            posts, pages = fetch(tag)
        except Exception as exc:
            # No repr/str: upstream exceptions may contain private session data.
            errors.append({"hashtag": tag, "error_type": type(exc).__name__})
            break

        statuses = [str(p.get("http", "missing")) for p in pages]
        if not statuses or any(code != "200" for code in statuses):
            errors.append({"hashtag": tag, "error_type": "InstagramReadError", "statuses": statuses})
            # Stop all further requests on errors, challenges, or rate limits.
            break

        selected = select_distinct_authors(
            posts, existing=seen_accounts, per_tag=per_tag
        )
        per_hashtag.append({
            "hashtag": tag,
            "retrieved_verified_posts": len(posts),
            "pages": len(pages),
            "unique_accounts": len(selected),
            "target_accounts": per_tag,
            "candidates": selected,
        })
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "read_only_instagram_web",
        "ordering": "newest_to_oldest_among_retrieved_posts",
        "requested_hashtags": list(tags),
        "target_per_hashtag": per_tag,
        "total_unique_accounts": len(seen_accounts),
        "results": per_hashtag,
        "errors": errors,
        "warning": "Instagram's sampled Recent feed may be incomplete or ranked. A shortfall is not filled with unrelated posts. Nothing was liked or followed.",
    }


def markdown(report):
    lines = [
        "# Daily Instagram hashtag review",
        "",
        f"**Retrieved:** {report['total_unique_accounts']} unique creators (goal: up to 100)",
        "",
        "Sorted by publication time within each hashtag, **newest to oldest**, with no age cutoff. "
        "**No likes or follows were performed.**",
        "",
        "| Hashtag | Accounts found | Goal |",
        "|---|---:|---:|",
    ]
    for result in report["results"]:
        lines.append(
            f"| \`#{result['hashtag']}\` | {result['unique_accounts']} | {result['target_accounts']} |"
        )
    lines.extend(["", "## Posts and profiles for review", ""])
    for result in report["results"]:
        lines.append(f"### #{result['hashtag']}")
        if not result["candidates"]:
            lines.append("No verified distinct creators returned in this sample.")
        else:
            lines.extend(["| Creator | Post age | Links |", "|---|---:|---|"])
            for row in result["candidates"]:
                lines.append(
                    f"| @{row['username']} | {row['age_hours']:.2f} h | "
                    f"[Post]({row['post_url']}) · [Profile]({row['profile_url']}) |"
                )
        lines.append("")
    if report["errors"]:
        lines.extend([
            "## Retrieval stopped",
            "The API returned an error, or account access failed. No retry or account actions were attempted.",
            "",
        ])
    lines.extend([
        "Instagram determines which posts the web endpoint returns; sorting here does not establish a complete chronological feed.",
        "Use the existing *manual* workflow to review any creator and decide on individual actions.",
    ])
    return "\n".join(lines) + "\n"


def write_output(report, directory):
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    (target / "daily-review.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    md = markdown(report)
    (target / "daily-review.md").write_text(md, encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(md)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-pages", type=int, default=3, choices=(1, 2, 3))
    p.add_argument("--read-spacing-seconds", type=float, default=6.0)
    args = p.parse_args()
    if not 0 <= args.read_spacing_seconds <= 15:
        p.error("Read spacing must be between 0 and 15 seconds")
    try:
        with private_session_path() as session_file:
            http = load_http(session_file)
            count = 0

            def fetch(tag):
                nonlocal count
                if count:
                    # Fixed spacing reduces read traffic; never masks a block.
                    time.sleep(args.read_spacing_seconds)
                count += 1
                return retrieve(http, tag, max_pages=args.max_pages)

            report = build_report(fetch)
    except SafeStop as exc:
        report = {
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "method": "read_only_instagram_web",
            "ordering": "newest_to_oldest_among_retrieved_posts",
            "requested_hashtags": list(HASHTAGS),
            "target_per_hashtag": PER_HASHTAG,
            "total_unique_accounts": 0,
            "results": [],
            "errors": [{"error_type": "SessionUnavailable", "message": str(exc)}],
        }
    except Exception as exc:
        report = {
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "method": "read_only_instagram_web",
            "ordering": "newest_to_oldest_among_retrieved_posts",
            "requested_hashtags": list(HASHTAGS),
            "target_per_hashtag": PER_HASHTAG,
            "total_unique_accounts": 0,
            "results": [],
            "errors": [{"error_type": type(exc).__name__}],
        }
    write_output(report, args.output_dir)
    print("Hashtags requested:", ", ".join("#" + t for t in HASHTAGS))
    print("Unique creator candidates:", report["total_unique_accounts"])
    print("Hashtags completed:", len(report["results"]))
    print("Error count:", len(report["errors"]))
    print("No follow, like, or comment actions performed.")
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
