"""One-shot, read-only aiograpi authentication check.

Never prints raw upstream responses or credential/session values.
"""
import asyncio
import contextlib
import io
import logging
import os
import sys

async def verify_client(client, username, password, code, stage):
    stage["value"] = "await login"
    logged_in = await client.login(username, password, verification_code=code)
    if logged_in is not True:
        raise RuntimeError("Login did not confirm success")
    stage["value"] = "authenticated identity"
    if not getattr(client, "user_id", None):
        raise RuntimeError("Missing authenticated user ID")
    stage["value"] = "authenticated account_info"
    info = await client.account_info()
    if getattr(info, "username", "").lower() != username.lower():
        raise RuntimeError("Account verification mismatch")

def main():
    logging.disable(logging.CRITICAL)
    username = os.environ.get("IG_USERNAME", "").strip().lstrip("@")
    password = os.environ.get("IG_PASSWORD", "")
    code = os.environ.get("IG_2FA_CODE", "").strip()
    if not username or not password:
        print("Configuration error: IG_USERNAME or IG_PASSWORD is missing")
        return 1
    stage = {"value": "client initialization"}
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from aiograpi import Client
            client = Client()
            if hasattr(client, "with_challenge_flow"):
                client.with_challenge_flow = False
            asyncio.run(verify_client(client, username, password, code, stage))
    except Exception as exc:
        print("Failed stage:", stage["value"])
        print("Error class:", type(exc).__name__)
        print("No automatic retries. Resolve any challenge using Instagram directly.")
        print("No likes, follows or hashtag requests were attempted.")
        return 1
    print("PASS: Login was awaited, and an authenticated account-info read succeeded.")
    print("No proxy, likes, follows, hashtag requests or session export.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
