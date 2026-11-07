"""Interactive one-time Instagram login on a trusted local computer.

Run only on the user's computer. Credentials are prompted privately and never
placed in command-line arguments, logs, GitHub Actions, or repository files.
"""
import asyncio
import getpass
import os
import sys
from pathlib import Path

SESSION_PATH = Path.home() / ".instagram_runner" / "aiograpi-session.json"

async def authenticate(client, username, password, initial_code, session_path=SESSION_PATH):
    async def challenge_code_handler(account_username, choice, **kwargs):
        print("Instagram requested an email/SMS/2FA verification code.")
        return getpass.getpass("Enter verification code here (not in chat): ").strip()

    client.challenge_code_handler = challenge_code_handler
    if session_path.is_file():
        client.load_settings(session_path)
    ok = await client.login(username, password, verification_code=initial_code)
    if ok is not True:
        raise RuntimeError("Instagram did not confirm login")
    info = await client.account_info()
    if getattr(info, "username", "").lower() != username.lower():
        raise RuntimeError("Authenticated account does not match requested username")
    session_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        session_path.parent.chmod(0o700)
    if os.name != "nt":
        # Restrictive permissions apply from creation, not just afterward.
        previous_umask = os.umask(0o077)
        try:
            if session_path.exists():
                session_path.chmod(0o600)
            client.dump_settings(session_path)
        finally:
            os.umask(previous_umask)
        session_path.chmod(0o600)
    else:
        client.dump_settings(session_path)
    return session_path

def main():
    username = input("Instagram username: ").strip().lstrip("@")
    if not username:
        print("Username cannot be empty.")
        return 1
    password = getpass.getpass("Instagram password (hidden): ")
    if not password:
        print("Password cannot be empty.")
        return 1
    initial_code = getpass.getpass(
        "Current 2FA code, if already available (otherwise press Enter): "
    ).strip()
    try:
        from aiograpi import Client
        path = asyncio.run(authenticate(Client(), username, password, initial_code))
    except Exception as exc:
        print("Login did not complete. Error class:", type(exc).__name__)
        print("If Instagram requests app-based verification, complete it there.")
        print("Do not repeatedly retry a rejected login.")
        return 1
    print("Authenticated API read: PASS.")
    print("Session saved locally to:", path)
    print("Keep this file private. Never upload it to a public repository or chat.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
