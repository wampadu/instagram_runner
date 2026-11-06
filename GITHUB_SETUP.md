# GitHub Actions setup

Two different things are needed: a private code repository, and a machine that
executes the jobs. No Instagram credentials or session have been created/uploaded.

## Included workflows

- **Offline tests:** runs on GitHub-hosted Ubuntu after a push to main or a manual
  trigger. Needs no Instagram account, session, password or proxy.
- **Instagram (persistent Linux runner):** manual preview/execute plus an optional
  daily schedule. Runs on your persistent Linux computer/server, registered with
  GitHub as a self-hosted runner with the extra label `instagram`. It does NOT
  run on a GitHub-hosted machine. The machine must be on and connected.

The Instagram workflow only runs for a private repository. Its scheduled job is
disabled unless you set the repository variable `IG_ENABLE_DAILY` to `true`.
The manual trigger previews by default; select `execute` to make changes.
No pull-request trigger is included. Only give trusted people workflow/code access
to the repository: those workflows execute on the machine holding your session.

## Bootstrap on the persistent machine

Follow GitHub's setup under Settings > Actions > Runners > New self-hosted runner.
Use a dedicated non-root Linux user and add the custom runner label `instagram`.

As THAT SAME Linux user, in a copy of this repository, run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python runner.py login -u YOUR_USERNAME --state-dir "$HOME/.local/state/instagram-runner"
```

The password/2FA prompts run locally. Session and ledger stay outside the checkout
in the runner user's private state directory, so checkout cleanup does not erase
them. This workflow does not upload them to GitHub, logs, caches or artifacts.

Set the repository variable `IG_USERNAME` at Settings > Secrets and variables >
Actions > Variables. Optionally set `IG_HASHTAGS` (space-separated names).

If using a proxy, set `IG_PROXY` directly in GitHub's repository Secrets UI, and use
that same endpoint during local bootstrap. Never put it in code or chat. A
rotating provider can still change its actual exit IP, which this script cannot
prevent. No Instagram password needs to be stored on GitHub for scheduled runs.

Then open Actions > Instagram (persistent Linux runner) > Run workflow. Run the
preview first. The workflow must be on the default branch to appear in that list.
Once tested, set `IG_ENABLE_DAILY=true` for the daily 12:00 UTC job, or leave it
unset and trigger jobs manually. Do not enable both systemd and Actions schedules.

If a challenge/expired session pauses the account, investigate in Instagram and
use the local `check` or `login` command with the same `--state-dir`. A check only
validates authentication; it does not certify that engagement restrictions ended.

## GitHub-hosted execution

Do not change `runs-on` to `ubuntu-latest` and expect the above setup to work.
GitHub-hosted jobs normally start on a fresh machine. Persistent sessions, the
action ledger, and account pauses would need a separate durable, protected state
store. GitHub's network addresses can also change between runs. That requires
a different workflow design; the included Instagram workflow deliberately uses
the persistent Linux machine instead.

Reference: https://docs.github.com/en/actions/concepts/runners/self-hosted-runners
