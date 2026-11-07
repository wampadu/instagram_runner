# Instagram runner for Linux

This is a rewrite of the supplied hashtag-follow-and-like script using instagrapi 3.2.6
and Python 3.11+. It does not claim to prevent Instagram restrictions. Local tests use
fake clients; a live account has not been tested. Do not reuse your exported browser
session JSON in this program. It creates a separate mobile API session during login.

## Install and first test

Extract the zip, open a terminal in this directory, then:

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest -v
.venv/bin/python runner.py login -u YOUR_USERNAME
.venv/bin/python runner.py check -u YOUR_USERNAME
```

`login` prompts locally for your password and, if enabled, a current 2FA code.
No password is supplied on the command line or stored by this script. The session
file is an authentication credential: keep the entire `state/` directory private.
Do not paste passwords, codes, cookies, session JSON or proxy credentials into chat.

If login raises a challenge, stop and resolve it in the official Instagram app or
website. This runner has no challenge bypass. A successful browser verification
does not guarantee that the mobile API login will work. Do not repeatedly retry.

Preview candidates (network reads, but no follows or likes):

```bash
.venv/bin/python runner.py run -u YOUR_USERNAME --hashtags photography --fetch 5
```

One live follow, no likes, for the first engagement test:

```bash
.venv/bin/python runner.py run -u YOUR_USERNAME --hashtags photography --execute --max-follows 1 --likes 0
```

After inspecting the result in Instagram, a run with follows and likes:

```bash
.venv/bin/python runner.py run -u YOUR_USERNAME --hashtags photography travel --execute --max-follows 10 --likes 3 --max-likes 30
.venv/bin/python runner.py status -u YOUR_USERNAME
```

Those numbers are configurable attempt limits, NOT established safe limits. The
ledger uses a rolling 24-hour window, including previous runs and unconfirmed
attempts. If you already made one follow in the test, it counts toward the next run.
The runner stops adding follows once that budget is reached. It may find fewer
eligible accounts than requested, especially with small fetches or duplicates.
`--source top` uses top hashtag posts instead of recent posts; neither option ranks
accounts by the number of posts they have made under a hashtag.

## What changed

- Native login and atomically saved session/device state; no hardcoded phone profile.
- Existing sessions are checked without password login on scheduled runs.
- Successful follows are recorded before fetching or liking posts.
- A durable SQLite ledger avoids repeating follows and likes across runs/hashtags.
- Writes are reserved before sending: uncertain results consume budget and are never
  blindly repeated. An interrupted follow may therefore be skipped permanently.
- Existing follows and outgoing follow requests are skipped. The ledger cannot track
  unrelated manual actions made outside this program.
- Separate global rolling limits for follows and likes; one process per account.
- Any API error propagated to the runner pauses the account in the local ledger. Scheduled runs then exit
  without network requests. No one-hour sleep followed by automatic resumption.
- Upstream log output and raw exception bodies are suppressed; error class and stage
  are printed. Unknown local configuration errors exit without retries.

`client.py` adapts the pinned library to disable transport retries and bypass its
automatic timeout replay for non-login writes. Read operations and the interactive
login still use upstream request logic, which can include fallbacks. This adapter
uses library internals: rerun the tests and review it before upgrading instagrapi.

After investigating an error, `check` validates the session and clears the local
pause. Passing that check does not prove action restrictions are gone. Use `login`
only if authentication needs renewal. A changed proxy configuration requires an
interactive login review; changing it does not clear a challenge.

## Optional proxy

The runner uses your normal connection unless `IG_PROXY` is set. To set a proxy
without placing its credentials in terminal history:

```bash
read -rsp 'Proxy URL (or Enter for none): ' IG_PROXY
echo
export IG_PROXY
```

This supports one endpoint per run, not rotating pools. A fixed hostname may still
rotate its exit IP; this script does not verify the provider's actual exit IP.
It fingerprints the configured URL locally to catch accidental configuration
changes. It does not print the URL. No proxy is required for the first test.

## Optional daily schedule (after the live tests pass)

The computer must be on and connected at the scheduled time. Use a user systemd
timer; leave `Persistent=false` to avoid unexpected catch-up runs. These steps
create a scheduled job on YOUR computer, not in this workspace or on GitHub.

Copy the examples, replacing `/ABSOLUTE/PATH/instagram-runner` and `YOUR_USERNAME`:

```bash
mkdir -p ~/.config/systemd/user
cp instagram-runner.service instagram-runner.timer ~/.config/systemd/user/
${EDITOR:-nano} ~/.config/systemd/user/instagram-runner.service
systemctl --user daemon-reload
systemctl --user enable --now instagram-runner.timer
systemctl --user list-timers instagram-runner.timer
journalctl --user -u instagram-runner.service -n 30 --no-pager
```

The example has no proxy. If needed, create a private environment file and add
`EnvironmentFile=/absolute/path/to/file` under `[Service]`. Put `IG_PROXY=...`
in that file and restrict its permissions with `chmod 600`. Do not commit it.

Disable the schedule with:

```bash
systemctl --user disable --now instagram-runner.timer
```

User timers may stop after logout, depending on your Linux setup. A server can
use user lingering if configured by its administrator. Nothing is installed or
enabled automatically by this download.

## Research and repository choice

- [instagrapi](https://github.com/subzeroid/instagrapi): selected because it supports
  the requested operations and documents persistent mobile sessions. Its own
  [best practices](https://subzeroid.github.io/instagrapi/latest/usage-guide/best-practices/)
  warn about browser-cookie reuse and the unpredictability of private API automation.
- [InstaPy](https://github.com/InstaPy/InstaPy): browser/Selenium alternative;
  its README says its creator has moved away from social media. It does not establish
  current working compatibility for this account.
- [GramAddict](https://github.com/GramAddict/bot): Android UI alternative; requires
  Android hardware/emulation, and its README advertises partial support for an old
  Instagram app version. Not selected for a Linux-only setup with no Android device.

This is a local deliverable, not a new GitHub repository. No account was accessed,
followed or liked during development, and no background schedule was enabled.

## Interactive aiograpi login (Windows / Surface, recommended)

The GitHub Actions login test can install the client, but **cannot privately answer Instagram's live email/SMS challenge** and must not be repeatedly retried. The tested GitHub development revision used here fixes the released package's missing password-key handling. It may still be rejected by Instagram.

1. On a **trusted Windows computer**, download this repository using **Code → Download ZIP**, and extract it into a local folder. Do not upload it to a shared folder.
2. Install **Python 3.12** if missing, ensuring the Windows `py` launcher is installed.
3. Double-click **`login_windows.cmd`** in the extracted repository. The script creates a separate Python environment and installs a pinned version of `aiograpi` directly from GitHub. It does **not** use any proxy.
4. Enter your Instagram username/password privately in the terminal. If prompted, enter the **current, unexpired verification code** in that same terminal—not in chat, GitHub Actions inputs or issues.
5. Only success after the authenticated `account_info` read is reported as a pass. The session is saved at `%USERPROFILE%\\.instagram_runner\\aiograpi-session.json` and must be treated like a password.

**Security:** Never commit, upload, paste, or email the session file or any 2FA code. The script does not enable automated likes/follows, and successful login alone does not prove that recent hashtag retrieval works. Complete any Instagram security challenge in the official app, and do not repeatedly retry rejected logins.


## Android / Termux interactive login (no laptop)

Run this on a trusted Android phone with Termux installed (prefer Termux from F-Droid). In Termux, paste these commands one line at a time:

```sh
pkg install -y git
git clone https://github.com/wampadu/instagram_runner.git
cd instagram_runner
bash login_termux.sh
```

The script installs the pinned upstream `aiograpi` development revision, then prompts for your username and password privately in Termux. If Instagram asks for a verification code, enter a **fresh** code in Termux, not in chat or GitHub. Do not reuse an expired code. A successful authenticated API read saves session settings to `~/.instagram_runner/aiograpi-session.json` on the phone. Never upload or share that file. The session is **not** automatically transferred to GitHub Actions; GitHub-hosted runners may still face verification and separate IP/device checks.

**Limitations:** Termux installation of `aiograpi`'s compiled Python dependencies can fail on Android/ARM even when Windows/Linux installation succeeds. The Termux installer has not yet been tested on your particular phone. Do not keep retrying authentication after a challenge or rejection. This login setup does not enable likes/follows or verify newest hashtag results.

## Working alternative: discover fresh hashtagged posts in Termux (read-only)

The old Instagram `tags/{hashtag}/sections/` endpoint returned `status=ok` but **no sections even for Top** in live November 2026 testing. Repeating that request or changing JSON parsers cannot produce posts. The separate `aiograpi` account-first discovery script uses **working** authenticated `search_users()` and `user_medias_v1()` requests, then verifies the *exact caption hashtag* and the media publication timestamp. It never uses Top hashtag posts and never performs likes/follows. **It searches accounts by name, not a global hashtag timeline: results are necessarily incomplete.**

Tested live on an existing saved phone session with `#toronto`: searched 6 public accounts, scanned 30 posts, and found two qualifying posts from the previous six hours. No password login required.

From the existing `~/instagram_runner` folder in Termux:

```bash
git pull --ff-only
bash discover_termux.sh toronto --max-age-hours 48
bash discover_termux.sh followforfollow likeforlike --max-accounts 6 --per-account 5 --max-age-hours 48
```

The output contains verified post links, the post's public username, and hours since publication. Defaults: 6 public accounts per query, 5 posts per account, and an adjustable age limit (up to 168 hours). Queries that find zero matching posts are **not** proof that a hashtag has no recent posts. The saved session remains under `/root/.instagram_runner/` inside the Termux Debian environment; never upload or paste it publicly. The original `runner.py` remains separate and is not enabled to follow/like on this alternative discovery path.

