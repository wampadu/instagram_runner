## Daily Instagram hashtag discovery — 9 AM Toronto, read-only

[**Open the daily discovery workflow**](https://github.com/wampadu/instagram_runner/actions/workflows/daily-instagram-review.yml).

Runs automatically each day at **9 AM America/Toronto**, with daylight saving time handled using two UTC cron slots and a date-aware gate. GitHub can delay scheduled jobs, so a specific delivery minute is not guaranteed. It can also be started immediately with **Run workflow**.

This scheduled workflow checks the user's **five original exact hashtags**: `#followforfollow`, `#likeforlike`, `#likeforfollow`, `#follow4follow`, `#like4like`. It collects **up to 20 distinct creator accounts per hashtag**, with global deduplication, for **up to 100 accounts total**. It checks a maximum of three Instagram web Recent pages per hashtag, verifies the exact caption hashtag and post timestamp, and sorts sample results **newest to oldest without an age cutoff**. It never pads a shortfall with unrelated results. Since Instagram controls the sampled feed, reaching 20 per tag (or 100 total) cannot be guaranteed.

The scheduled workflow is **read-only**: no follows, likes, comments or profile changes. It uses six-second spacing between hashtag-read groups to avoid excessive request bursts, without evading challenges or rate limits; it immediately stops on an HTTP error. It never stores the Instagram session in the Git repository and reads the existing `IG_SESSION_JSON` / `IG_SESSION_GZIP_B64` Actions secret. It uses the `contents: read` GitHub token permission.

Each run displays a **Summary** with links to each post and public profile, post age and the number of accounts found per hashtag. It also uploads `daily-review.json` and `daily-review.md` for review. The existing separate [single-account manual workflow](https://github.com/wampadu/instagram_runner/actions/workflows/manual-instagram.yml) is unchanged.

---

## Manual GitHub Actions — newest to oldest, **no age cutoff**

**[Run the Instagram workflow manually](https://github.com/wampadu/instagram_runner/actions/workflows/manual-instagram.yml).**

The GitHub Actions workflow discovers posts matching an exact Instagram hashtag using your saved session and Instagram's web `tab=recent` feed, verifies their captions and publication timestamps, **keeps all returned verified posts regardless of age**, and sorts them **newest to oldest**. No 6-hour, 24-hour, or seven-day age restriction is applied. We cannot control which posts Instagram supplies, only sort the sampled posts it returns. Multiple pages may be available, and a sorted sample is not guaranteed to be a complete chronological hashtag timeline.

- **Preview (default):** Shows all verified posts in the sampled results, including older posts, newest to oldest, with clickable links and publication ages. Does not like/follow anyone.
- **follow_like:** Selects the newest verified post in the sample or an explicitly provided Instagram post URL, re-verifies its caption, actual author and timestamp, then attempts **at most one follow and one like** after the `FOLLOW_AND_LIKE` confirmation. It **does not reject a post solely because it is older than 24 hours**. It avoids automatic retries and reports actual confirmed/unconfirmed statuses.
- **Reports:** The GitHub Actions run Summary shows all matched posts and any engagement results. A downloadable JSON/Markdown artifact is also produced. The workflow is **manual only**, with no schedule.

### Private session configuration

GitHub-hosted runs use the encrypted repository secret `IG_SESSION_JSON` (or `IG_SESSION_GZIP_B64`) for the existing Instagram session. The session must never be committed to your repository or pasted into a chat. If needed, open [Settings → Secrets and variables → Actions](https://github.com/wampadu/instagram_runner/settings/secrets/actions) to check that the secret exists. Running from GitHub's network may require an Instagram security check even if Termux works.

### Termux read-only alternative

```bash
cd ~/instagram_runner
git pull --ff-only
bash recent_web_termux.sh follow_for_follow
```

Without an age argument, the Termux command also **keeps all verified posts and sorts newest to oldest**. You can optionally pass a number of hours as a second argument only if you explicitly want to filter, e.g., `bash recent_web_termux.sh toronto 24`.

**Note:** Instagram's unofficial endpoints can change or restrict access. Neither sorting nor a successful preview guarantees a like/follow will succeed. Automated writes are not retried after uncertain outcomes, and the repository does not yet retain an across-run engagement ledger.

---

## WORKING FREE SOLUTION (November 2026): Instagram web Recent posts, no Meta app

**Use this instead of the older Android `aiograpi.hashtag_medias_recent` or a paid data provider.** Tested live on a Pixel 9 Pro using only its pre-existing private local Termux session. No Meta developer account, no Graph API key, no credit card, no other registration. No like/follow actions.

The key discovery is a **different Instagram web endpoint** from the old broken Android-mobile private API. This approach was adapted from [vrajdesai78/instagram-skill](https://github.com/vrajdesai78/instagram-skill), using `POST https://www.instagram.com/api/v1/tags/{tag}/sections/` with `supported_tabs=["top","recent","clips"]`, `tab=recent`, existing Instagram cookies and web headers. Only the local phone sends the cookies to instagram.com; they are never written to GitHub or printed.

Run in Termux:

```bash
cd ~/instagram_runner
git pull --ff-only
bash recent_web_termux.sh follow_for_follow 168
bash recent_web_termux.sh followforfollow 24
```

The command outputs exact caption-hashtag matches in timestamp order, with profile names, publication ages and post URLs. The number is the maximum age in hours. Defaults: 2 pages; bounded to at most 3 pages, no automatic retries, no external services. Python entrypoint: `python -m scripts.instagram_web_recent <tag> --hours 24 --max-pages 2` inside `venv-instagrapi`.

**Actual live results on 2026-11-06 / Nov 7 UTC:**

- `#follow_for_follow`: 2 Recent web API pages, both HTTP 200, **57 raw media candidates**, **51 matched exact hashtag captions**, **4 posts within 7 days**. Newest verified was about **30.6 hours old**; **zero under 24 hours in sampled pages**. This is not evidence the hashtag has zero new posts overall.
- `#toronto`: recent web API returned verified exact-caption posts published within **minutes** (some around 0.2–0.6 hours).
- `#followforfollow` (no underscores): verified exact-tag posts also published within **an hour**. This is a different hashtag from `#follow_for_follow`.
- `test_instagram_web_recent_probe.py` (2 offline tests) and `test_instagram_web_recent.py` (3 offline tests) passed on the phone.

**Limitations:** Instagram may rank/filter results even when `tab=recent`; sorting retrieved posts by timestamp does not make a globally exhaustive chronological feed. The exact `#follow_for_follow` tag may have low discoverability or few current results. API access is undocumented and can change, expire, or rate-limit; do not claim guaranteed unlimited queries. This script deliberately performs zero account mutations and has no auto-follow/auto-like behavior. Session stays only in `/root/.instagram_runner/aiograpi-session.json` and should never be pasted or committed.

---

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


## Exact hashtag '#follow_for_follow' — 2026-11-06/07 investigation

**Working Instagram login does not imply working chronological hashtag access.** Live read-only tests from Termux found:
- `hashtag_info_v1("follow_for_follow")` returned a roughly 143,905 total media count.
- The private `tags/follow_for_follow/sections/` endpoint returned `status=ok` but zero Top and Recent sections.
- A limited account-first search of 12 public accounts inspected 61 posts and found zero *verified exact-tag* posts in the last 48 hours. This does NOT mean the tag has zero new posts.
- Public keyword media search and public GraphQL did not supply usable current hashtag results; do not silently fall back to Top and call the result chronological.

### New read-only API option — first 100 lookups/credits free, not forever free

Two providers *advertise* a functioning `recent` hashtag feed, but have **not yet been live-tested with this particular tag** using an API key:

- **Social Fetch**: `GET /v2/instagram/hashtags/follow_for_follow/media?tab=recent`, 100 one-time free credits. https://www.socialfetch.dev/
- **Openhandle**: `GET /v1/instagram/hashtags/follow_for_follow/posts?sort=recent`, 100 one-time free requests. https://openhandle.dev/

Both require their own API key; neither requires an Instagram password, session JSON, or Meta developer app. The new `scripts/hashtag_recent_provider.py` script only prints posts with timestamps inside your window **and an exact matching hashtag in the caption**, sorts them newest-first, and avoids duplicates. It does not like, follow, or log in to Instagram. The new parser passed offline tests, **not** a live provider lookup.

Inside your existing Termux repo:

```bash
git pull --ff-only
bash recent_provider_termux.sh socialfetch follow_for_follow
# or, if you obtained an Openhandle key:
bash recent_provider_termux.sh openhandle follow_for_follow
```

Enter the selected provider's API key **only in Termux**, when prompted invisibly. Do not paste a key or your existing Instagram session into chat, GitHub, an issue or a repository file. If no posts are shown, the provider may hide that hashtag too; this cannot be bypassed by treating ranked posts as recent.

The working local account-first discovery remains available with `bash discover_termux.sh follow_for_follow --max-age-hours 48`, but **it is incomplete and not a hashtag-wide latest feed**. The existing write automation remains separate and disabled for these new read-only pathways.

## Old instagrapi vs new aiograpi: controlled November 2026 comparison

The user's historical script called `instagrapi.Client.hashtag_medias_recent(name, amount=60)`. This and `aiograpi.Client.hashtag_medias_recent(name, amount=...)` both use Instagram's private `tags/{name}/sections/` endpoint, with `tab=recent` and `media_recency_filter=top_recent_posts`. The different synchronous/asynchronous execution does **not** amount to a different hashtag feed API.

The old script calls `set_device({...Pixel 9 Pro...})` **before** `load_settings()`. The library's `load_settings()` reinitializes the client, so saved session settings replace manually configured device values; this was confirmed with an on-device comparison (device and app-version equality were both false).

**Controlled read-only live tests on the same local saved session** (no fresh login and no write actions):

| Check | Old instagrapi 3.2.6 | New aiograpi |
|---|---|---|
| Account authentication via session | PASS | PASS |
| `#follow_for_follow` Recent | 0 posts | 0 posts |
| `#followforfollow` Recent | 0 posts | Previously tested as empty in new-client tests |

The old original code's hashtag list contained `followforfollow` without underscores, which is a different hashtag. A successful historical run cannot establish that the same endpoint still delivers posts in November 2026. Instagram currently acknowledges the hashtag and returns a media count, while the sections endpoint returns an empty response. The exact server-side reason remains **unknown**; do not claim the old device signature or a synchronous API would fix it.

For a read-only on-phone repetition (not recommended repeatedly because the endpoint currently returns empty):

```bash
cd ~/instagram_runner
bash compare_old_termux.sh
```

Keep automated likes and follows disabled until there is a dependable discovery method with verifiable timestamps and appropriate account safety checks.

## November 2026: strongest verified next test for exact `#follow_for_follow` Recent feed

### Findings, not assumptions

1. Saved `aiograpi` login is valid on the user's Termux phone. `instagrapi 3.2.6` also authenticates from the same session.
2. The private `tags/follow_for_follow/sections/` response gives `status=ok` and `sections=[]`, for **both Recent and Top**. The old `instagrapi` uses this same endpoint. Changing parser, request amount, sleep, Python sync/async style or device model is not a demonstrated fix.
3. Instagram returns a historical media count for `#follow_for_follow`, but that does not prove any *newest* posts are available. This tag is **not** the same as `#followforfollow`; both were previously tested.
4. A separate indexed provider search for the exact caption returned zero indexed results; that provider is **not a live full hashtag feed**. Public hashtag-search websites may time out. Do not claim a successful live hashtag feed on this evidence.
5. The official Meta Facebook Login Instagram Graph API does have `ig_hashtag_search` and `/{hashtag-id}/recent_media`, but requires professional-account access, Meta permissions and potentially App Review, and is limited to 30 distinct hashtag queries per rolling 7 days. Sensitive/restricted hashtags can be unavailable.

### Capped free-credit test with Apify (no Instagram password or cookies)

Apify offers a free plan with **US$5 of usage credits per month**. The independent `coregent/instagram-hashtag-scraper` Actor documents `sort: RECENT` and `postsNewerThan: 24 hours`. The code at `scripts/apify_recent_verified.py` invokes that documented Actor through the Apify API, strictly verifies exact tag/caption, timestamp and URL, sorts newest first, and **caps the run total charge to US$0.10** using Apify's `maxTotalChargeUsd` API parameter. It never uses the user's Instagram session. Five local offline tests passed on Android/Termux. **We have NOT yet live-confirmed that this Actor returns any `#follow_for_follow` results**: a real API token is still required.

1. Register for a free Apify account at https://console.apify.com and copy an API token privately from your account's Settings → API & Integrations.
2. In Termux:

```bash
cd ~/instagram_runner
git pull --ff-only
bash apify_recent_termux.sh follow_for_follow
```

3. Enter the **Apify** token in the Termux hidden prompt (never in ChatGPT, GitHub source code, or terminal command history). If any verified links are found, they will be printed with publication age. A zero result or provider error means **do not claim this hashtag's Recent feed is working**.
4. Do not enable mass-following/liking merely because post retrieval starts working. This pathway is strictly read-only.

Official provider documentation: https://apify.com/pricing ; https://apify.com/coregent/instagram-hashtag-scraper ; https://docs.apify.com/api/v2/actor-run-sync-get-dataset-items-get .

**Do not confuse the independent Social Fetch `401` test with evidence about whether its hashtag feed exists:** that result establishes failed API authorization, not feed contents. The prior `recent_provider_termux.sh` remains experimental, not a confirmed solution. Apify credits are finite; test a few rows before considering ongoing automation.

## Free official Meta Facebook Graph API — read-only Recent hashtag integration

As of November 2026, Instagram API **with Facebook Login** supports hashtag lookup by IG Hashtag ID and a Recent media endpoint. Meta does not list a charge for API calls. The API **with Instagram Login** is different and does not support public hashtag discovery.

### Before running
- The Instagram account must be a **Business or Creator** account linked to a **Facebook Page** the Facebook user manages. On November 6, 2026, the owner's Instagram account **follow_back_aswell** was checked in the app and still showed **Switch to professional account**, so this account is currently personal. Do not convert without the owner's explicit choice; conversion can affect privacy/features.
- Register an app in **Meta for Developers** with **Facebook Login** (not solely Instagram Login). The Facebook User access token should permit page access with pages_show_list, pages_read_engagement and instagram_basic.
- Hashtag Search requires **Instagram Public Content Access** permission/feature, often gated behind **Meta App Review even for the account owner**. Denied permissions cannot be fixed by retrying requests.
- The hashtag may be considered restricted/sensitive, and eligibility of **#follow_for_follow** remains untested.
- Recent media includes public posts from approximately the **past 24 hours**, max 50/page, no author **username** field, and at most 30 unique hashtags per account in a rolling 7 days. Meta also does not provide follow/like actions on unrelated users through this API.

### First: check linked Instagram account without using hashtag quota

From Termux, enter:

    cd ~/instagram_runner
    git pull --ff-only
    bash meta_graph_termux.sh --check-access

Enter the **Facebook User Access Token** in the hidden terminal prompt. Do not enter Instagram/Facebook passwords, App Secret, saved Instagram session JSON or 2FA codes. The token is used via HTTPS Authorization header and is not printed, uploaded to the GitHub repo or saved by the script.

The access check only calls Facebook Graph **/me/accounts**, then lists connected professional Instagram accounts. A personal account is not eligible.

### Next: query official Recent hashtag posts (after review/permission access)

    bash meta_graph_termux.sh --recent follow_for_follow

The program calls **/ig_hashtag_search** then **/{hashtag-id}/recent_media**, validates exact caption hashtag, recent timestamp and official Instagram permalink, removes duplicates, and sorts returned records newest-first. A sorted page does not guarantee exhaustive timeline coverage.

Implementation: scripts/meta_graph_recent.py. Five network-free unit tests passed on Android using test_meta_graph_recent.py. **No live Graph API hashtag lookup has succeeded yet**, because the user has not granted a professional Page-linked account and Meta Facebook User token. The app must have Instagram Public Content Access approval.

Official references: https://developers.facebook.com/apps/ and https://developers.facebook.com/tools/explorer/ and https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api .
