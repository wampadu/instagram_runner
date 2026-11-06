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
