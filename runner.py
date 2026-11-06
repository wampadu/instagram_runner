#!/usr/bin/env python3
"""Single-account Linux runner. Login locally; never import browser cookies."""
import argparse
import fcntl
import getpass
import hashlib
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys
import time


class StopRun(Exception):
    pass


class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS actions (
            kind TEXT, target TEXT, state TEXT, at REAL,
            PRIMARY KEY(kind, target))""")
        self.db.execute("CREATE TABLE IF NOT EXISTS control (key TEXT PRIMARY KEY, value TEXT)")
        self.db.commit()

    def get(self, key):
        row = self.db.execute("SELECT value FROM control WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO control VALUES (?,?)", (key, value))
        self.db.commit()

    def seen(self, kind, target):
        return self.db.execute("SELECT 1 FROM actions WHERE kind=? AND target=?",
                               (kind, str(target))).fetchone() is not None

    def count(self, kind):
        # Pending requests also consume budget: a timeout may hide a successful write.
        return self.db.execute("SELECT count(*) FROM actions WHERE kind=? AND at>=?",
                               (kind, time.time() - 86400)).fetchone()[0]

    def reserve(self, kind, target, limit):
        if self.seen(kind, target) or self.count(kind) >= limit:
            return False
        self.db.execute("INSERT INTO actions VALUES (?,?,?,?)",
                        (kind, str(target), "pending", time.time()))
        self.db.commit()
        return True

    def finish(self, kind, target):
        self.db.execute("UPDATE actions SET state='done' WHERE kind=? AND target=?",
                        (kind, str(target)))
        self.db.commit()


def save_session(client, path):
    temp = path.with_suffix(".tmp")
    client.dump_settings(temp)
    temp.chmod(0o600)
    temp.replace(path)


def call(ledger, operation, fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        # Do not print response bodies, tokens, proxy URLs, or exception messages.
        name = type(exc).__name__
        ledger.set("blocked", f"{operation}: {name}")
        raise StopRun(f"{operation} failed ({name}). Paused; no automatic retries.") from None


def write_action(client, ledger, session, kind, target, limit, fn, delay):
    if not ledger.reserve(kind, target, limit):
        return False
    result = call(ledger, kind, fn, target)
    if result is not True:
        ledger.set("blocked", f"{kind}: unconfirmed result")
        raise StopRun(f"{kind} was not confirmed; paused. Pending action will not be repeated.")
    ledger.finish(kind, target)
    save_session(client, session)
    print(f"Confirmed {kind}: {target}", flush=True)
    time.sleep(delay)
    return True


def run(client, ledger, session, args):
    seen = set()
    for tag in dict.fromkeys(t.lstrip("#") for t in args.hashtags):
        if args.execute and ledger.count("follow") >= args.max_follows:
            break
        method = client.hashtag_medias_recent if args.source == "recent" else client.hashtag_medias_top
        medias = call(ledger, "hashtag lookup", method, tag, args.fetch)
        follows_this_tag = 0
        for media in medias:
            uid = str(media.user.pk)
            if uid == str(client.user_id) or uid in seen or ledger.seen("follow", uid):
                continue
            seen.add(uid)
            if follows_this_tag >= args.per_tag:
                break
            if not args.execute:
                print(f"PREVIEW #{tag}: @{media.user.username} ({uid})")
                follows_this_tag += 1
                continue
            if ledger.count("follow") >= args.max_follows:
                return
            # Avoid following an existing contact or duplicating a pending request.
            rel = call(ledger, "friendship lookup", client.user_friendship_v1, uid)
            if rel.following or rel.outgoing_request:
                continue
            if write_action(client, ledger, session, "follow", uid, args.max_follows,
                            client.user_follow, args.pause):
                follows_this_tag += 1
            if args.likes and ledger.count("like") < args.max_likes:
                posts = call(ledger, "user posts", client.user_medias_v1, uid, args.likes)
                for post in posts[:args.likes]:
                    if ledger.count("like") >= args.max_likes:
                        break
                    write_action(client, ledger, session, "like", str(post.id), args.max_likes,
                                 client.media_like, args.pause)
        save_session(client, session)


def positive(value):
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["login", "check", "run", "status"])
    p.add_argument("-u", "--username", required=True)
    p.add_argument("--state-dir", type=Path, default=Path(__file__).resolve().parent / "state")
    p.add_argument("--hashtags", nargs="+", default=["followforfollow", "likeforlike"])
    p.add_argument("--source", choices=["recent", "top"], default="recent")
    p.add_argument("--fetch", type=positive, default=20)
    p.add_argument("--per-tag", type=positive, default=5)
    p.add_argument("--max-follows", type=positive, default=10, help="rolling 24h attempt limit")
    p.add_argument("--max-likes", type=positive, default=30, help="rolling 24h attempt limit")
    p.add_argument("--likes", type=int, choices=range(4), default=3)
    p.add_argument("--pause", type=positive, default=60, help="seconds between writes; not a safe-limit claim")
    p.add_argument("--execute", action="store_true", help="perform follows/likes; otherwise preview")
    a = p.parse_args()
    a.username = a.username.lower().lstrip("@")
    if not re.fullmatch(r"[a-z0-9._]{1,30}", a.username):
        p.error("invalid Instagram username")
    if any(not re.fullmatch(r"\w+", t.lstrip("#")) for t in a.hashtags):
        p.error("hashtags must be individual names, without spaces")
    return a


def main():
    args = parse_args()
    os.umask(0o077)
    directory = args.state_dir.expanduser().resolve() / args.username
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    with (directory / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another run is already active.")
            return 1
        ledger = Ledger(directory / "actions.sqlite3")
        if args.command == "status":
            print(f"Last 24h attempts: follows={ledger.count('follow')}, likes={ledger.count('like')}")
            print(f"Pause: {ledger.get('blocked') or 'none'}")
            return 0
        if args.command == "run" and ledger.get("blocked"):
            raise StopRun(f"Account paused: {ledger.get('blocked')}. Resolve in Instagram; run check afterward.")
        session = directory / "session.json"
        if args.command != "login" and not session.exists():
            raise StopRun("No native session. Run the login command locally first.")
        # Suppress upstream exception bodies that can contain account/session information.
        logging.disable(logging.CRITICAL)
        from client import NoReplayClient, configure
        client = NoReplayClient(with_challenge_flow=False)
        if session.exists():
            client.load_settings(session)
        configure(client)
        proxy = os.environ.get("IG_PROXY", "")
        proxy_hash = hashlib.sha256(proxy.encode()).hexdigest()
        previous = ledger.get("proxy_hash")
        if previous and previous != proxy_hash and args.command != "login":
            raise StopRun("Proxy configuration changed. Review it and use interactive login before continuing.")
        if proxy:
            client.set_proxy(proxy)
        if args.command == "login":
            if not sys.stdin.isatty():
                raise StopRun("Login is interactive. Run it in your terminal.")
            password = getpass.getpass("Instagram password (local, hidden): ")
            code = getpass.getpass("2FA code, if enabled (otherwise Enter): ")
            call(ledger, "login", lambda: client.login(args.username, password, verification_code=code))
        info = call(ledger, "session check", client.account_info)
        if info.username.lower() != args.username:
            ledger.set("blocked", "session belongs to a different account")
            raise StopRun("Session belongs to a different account.")
        save_session(client, session)
        ledger.set("proxy_hash", proxy_hash)
        print(f"Authenticated as @{info.username}", flush=True)
        if args.command in ("login", "check"):
            ledger.set("blocked", "")
            print("Session check passed; pause cleared. This does not prove engagement restrictions are cleared.")
        else:
            run(client, ledger, session, args)
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except StopRun as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("Stopped; any unconfirmed write stays pending.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"Stopped ({type(exc).__name__}). No automatic retry; check local configuration.", file=sys.stderr)
        sys.exit(1)
