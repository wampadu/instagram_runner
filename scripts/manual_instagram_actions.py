"""Manual Instagram GitHub Actions job: preview verified posts or follow+like ONE.

No Meta app or paid API. The existing saved Instagram session is only accepted
from an encrypted GitHub Actions secret (or an existing LOCAL Termux session).
This tool never performs a username/password login, never auto-retries writes,
and does not schedule itself. A fresh Actions run may trigger Instagram login
verification due to GitHub's different network; it then stops.

Actions are intentionally limited to one selected post and its author per run.
"""
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

from scripts.instagram_web_recent import load_http, retrieve
from scripts.instagram_web_recent_probe import SESSION, TAG
from scripts.instagram_web_recent_probe import verified as web_verified

EXPECTED_ACCOUNT = "follow_back_aswell"
POST_URL_RE = re.compile(
    r"^https://(?:www\.)?instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)/?(?:\?[^#]*)?$",
    re.I,
)
USER_RE = re.compile(r"^[A-Za-z0-9_.]{1,30}$")
EXACT = "FOLLOW_AND_LIKE"


class SafeStop(Exception):
    """Known failure with no sensitive exception text."""


def contains_tag(caption, tag):
    return isinstance(caption, str) and bool(re.search(
        r"(?<!\w)#" + re.escape(tag) + r"(?!\w)", caption, re.I
    ))


def post_code_from_url(url):
    match = POST_URL_RE.fullmatch((url or "").strip())
    return match.group(1) if match else None


def age_hours(value, now=None):
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - value.astimezone(timezone.utc)).total_seconds() / 3600


def check_target_media(media, code, tag, max_hours=None, expected_user=None):
    """Validate an authenticated read before permitting ANY write. Age cutoff is unused."""
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
    """Get saved session without exposing it in GitHub files, stdout or logs."""
    raw = os.environ.get("IG_SESSION_JSON", "")
    packed = os.environ.get("IG_SESSION_GZIP_B64", "")
    if raw or packed:
        try:
            if packed:
                compressed = base64.b64decode(packed, validate=True)
                if len(compressed) > 50_000:
                    raise ValueError("Compressed session too large")
                # Bound decompression and reject malformed data.
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
    logging.disable(logging.CRITICAL)  # Avoid raw upstream errors containing secrets.
    cl = NoReplayClient(with_challenge_flow=False)
    cl.load_settings(session_path)
    configure(cl)
    info = cl.account_info()
    if getattr(info, "username", "").lower() != EXPECTED_ACCOUNT:
        raise SafeStop("Saved session belongs to an unexpected Instagram account.")
    return cl


def engagement(client, code, tag, max_hours=None, expected_user=None):
    """At most one follow request, then one like request. No automatic retries."""
    result = {"follow": "not_attempted", "like": "not_attempted"}
    try:
        media_pk = client.media_pk_from_code(code)
        media = client.media_info(media_pk, use_cache=False)
        target = check_target_media(media, code, tag, max_hours, expected_user)
        result.update({k:v for k,v in target.items() if k not in ("uid","media_id")})
    except SafeStop as exc:
        result["error"] = str(exc)
        return result
    except Exception as exc:
        result["error"] = "Post verification failed: " + type(exc).__name__
        return result

    try:
        if str(client.user_id) == target["uid"]:
            result["error"] = "Own Instagram account; no actions taken."
            return result
        rel = client.user_friendship_v1(target["uid"])
        if rel is None:
            raise SafeStop("Friendship state is unavailable.")
        if bool(getattr(rel,"following",False)):
            result["follow"] = "already_following"
        elif bool(getattr(rel,"outgoing_request",False)):
            result["follow"] = "already_requested"
        else:
            # No replay after write exceptions, including transport timeouts.
            ok = client.user_follow(target["uid"])
            if ok is not True:
                result["follow"] = "unconfirmed"
                result["error"] = "Instagram did not confirm the follow; like not attempted."
                return result
            result["follow"] = "confirmed"
    except Exception as exc:
        result["follow"] = "uncertain"
        result["error"] = "Follow failed or was not confirmed: " + type(exc).__name__
        return result

    try:
        if getattr(media, "has_liked", None) is True:
            result["like"] = "already_liked"
        else:
            ok = client.media_like(target["media_id"])
            if ok is not True:
                result["like"] = "unconfirmed"
                result["error"] = "Instagram did not confirm the like. No retry."
                return result
            result["like"] = "confirmed"
    except Exception as exc:
        result["like"] = "uncertain"
        result["error"] = "Like failed or was not confirmed: " + type(exc).__name__
    return result


def markdown_report(report):
    lines=[
        "# Manual Instagram test",
        "",
        f"- Mode: **{report['mode']}**",
        f"- Exact hashtag: **#{report['hashtag']}**",
        "- Sorting: **newest to oldest (no age cutoff)**",
    ]
    if report.get("error"):
        lines.append("- Status: **Stopped — " + html.escape(report["error"]) + "**")
    discovery=report.get("discovery") or {}
    if discovery:
        lines.extend([
            f"- Pages: **{discovery.get('pages',0)}**",
            f"- Candidates: **{discovery.get('raw',0)}**",
            f"- Verified exact-hashtag posts: **{discovery.get('verified',0)}**",
            f"- Displayed verified posts: **{discovery.get('eligible',0)}**",
        ])
    if report.get("candidates"):
        lines.extend(["", "## Recent verified posts (newest to oldest)", "",
                      "| Author | Age | Instagram link |","|---|---:|---|"])
        for c in report["candidates"]:
            user=c.get("username") or "(unknown)"
            if not USER_RE.fullmatch(user):
                user="(unavailable)"
            lines.append(f"| @{user} | {float(c['age']):.1f} h | [View post]({c['url']}) |")
    if "skipped_existing" in report:
        lines.append(f"- Skipped existing follows/likes: **{report['skipped_existing']}**")
        lines.append(f"- Skipped unverified posts: **{report['skipped_unverified']}**")
    if report.get("engagement"):
        r=report["engagement"]
        lines.extend([
            "", "## Follow and like result", "",
            f"- Author: **@{r.get('username','unavailable')}**",
            f"- Post: {r.get('url','unavailable')}",
            f"- Follow: **{r.get('follow','not_attempted')}**",
            f"- Like: **{r.get('like','not_attempted')}**",
        ])
        if r.get("error"):
            lines.append("- Error: **" + html.escape(r["error"]) + "**")
    lines.extend(["", "No credentials/session are included in this report.",
                  "Web Recent results are not guaranteed to be an exhaustive hashtag timeline.",
                  "Actions were not automatically retried."])
    return "\n".join(lines)+"\n"


def save_report(report, output_dir):
    if output_dir:
        target=Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        # Keep public report artifact strictly separate from session.
        (target/"results.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        (target/"results.md").write_text(markdown_report(report),encoding="utf-8")
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as out:
            out.write(markdown_report(report))


def choose_new_post(client, eligible, hashtag, report):
    """Find one author we do not follow and one post we have not liked."""
    seen_authors = set()
    report["skipped_existing"] = 0
    report["skipped_unverified"] = 0
    for item in eligible:
        code, username = item.get("code"), item.get("username")
        if not isinstance(code, str) or not USER_RE.fullmatch(username or ""):
            report["skipped_unverified"] += 1
            continue
        try:
            pk = client.media_pk_from_code(code)
            media = client.media_info(pk, use_cache=False)
            verified = check_target_media(
                media, code, hashtag, expected_user=username
            )
        except Exception:
            report["skipped_unverified"] += 1
            continue
        if str(client.user_id) == verified["uid"] or verified["uid"] in seen_authors:
            report["skipped_existing"] += 1
            continue
        seen_authors.add(verified["uid"])
        if getattr(media, "has_liked", None) is True:
            report["skipped_existing"] += 1
            continue
        if getattr(media, "has_liked", None) is not False:
            report["skipped_unverified"] += 1
            continue
        try:
            relation = client.user_friendship_v1(verified["uid"])
        except Exception as exc:
            raise SafeStop(
                "Could not verify follow state (" + type(exc).__name__ + ")."
            ) from None
        if relation is None:
            raise SafeStop("Follow state unavailable. No actions taken.")
        if (bool(getattr(relation, "following", False)) or
                bool(getattr(relation, "outgoing_request", False))):
            report["skipped_existing"] += 1
            continue
        return item
    raise SafeStop(
        "No unliked posts from unfollowed authors in the verified sample; "
        "no new follow or like attempted."
    )


def run(args):
    result = {
        "mode":args.mode, "hashtag":args.hashtag,
        "candidates":[],"engagement":None,"error":None,
    }
    try:
        if args.mode == "follow_like" and args.confirm != EXACT:
            raise SafeStop("To engage, set confirmation to FOLLOW_AND_LIKE.")
        with private_session_path() as session_path:
            picked=None
            post_code=post_code_from_url(args.post_url)
            if args.post_url and not post_code:
                raise SafeStop("Post URL must be a valid Instagram post or Reel URL.")
            # Direct URL is user-selected; validate its exact hashtag via media_info.
            if not post_code:
                http=load_http(session_path)
                records,pages=retrieve(http,args.hashtag,max_pages=args.max_pages)
                failed=[p["http"] for p in pages if p["http"]!="200"]
                result["discovery"]={
                    "pages":len(pages), "raw":sum(p["raw"] for p in pages),
                    "verified":len(records),
                    "eligible":sum(c["age"] >= 0 for c in records),
                    "http_statuses":[p["http"] for p in pages],
                }
                if failed:
                    raise SafeStop("Instagram web feed unavailable: "+",".join(failed))
                eligible=sorted((c for c in records if c["age"] >= 0), key=lambda c: c["age"])
                for c in eligible:
                    username=c["username"] if USER_RE.fullmatch(c["username"]) else "(unavailable)"
                    result["candidates"].append({
                        "username":username,"age":c["age"],
                        "url":f"https://www.instagram.com/p/{c['code']}/",
                    })
            if args.mode=="follow_like":
                client=make_client(session_path)
                if not post_code:
                    picked=choose_new_post(client, eligible, args.hashtag, result)
                    post_code=picked["code"]
                result["engagement"]=engagement(
                    client,post_code,args.hashtag,None,
                    expected_user=picked["username"] if picked else None,
                )
                outcome=result["engagement"]
                if (outcome.get("error") or outcome.get("follow") != "confirmed"
                        or outcome.get("like") != "confirmed"):
                    result["error"]="No new follow-and-like pair confirmed; check individual action statuses."
    except SafeStop as exc:
        result["error"]=str(exc)
    except Exception as exc:
        result["error"]="Stopped safely: "+type(exc).__name__
    save_report(result,args.output_dir)
    print(f"Mode={result['mode']} tag=#{result['hashtag']} matches={len(result['candidates'])}")
    if result.get("engagement"):
        print("Follow:",result["engagement"]["follow"],"Like:",result["engagement"]["like"])
    if result.get("error"):
        print("Stopped:",result["error"])
        return 2
    print("Results are in the GitHub Actions Summary and report artifact.")
    return 0


def parse_args():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",choices=["preview","follow_like"],default="preview")
    p.add_argument("--hashtag",default="follow_for_follow")
    p.add_argument("--post-url",default="",help="Optional exact Instagram URL; bypasses discovery in follow_like mode")
    p.add_argument("--max-pages",type=int,choices=[1,2,3],default=2)
    p.add_argument("--confirm",default="")
    p.add_argument("--output-dir",default="")
    args=p.parse_args()
    args.hashtag=args.hashtag.lower().lstrip("#")
    if not TAG.fullmatch(args.hashtag):
        p.error("Use one valid hashtag name")
    return args


if __name__=="__main__":
    sys.exit(run(parse_args()))
