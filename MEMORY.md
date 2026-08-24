# Headless - project memory

Read this at the start of every session (`CLAUDE.md` requires it). It is the operating
ledger: what the environment looks like, what each site is known to do, what has been run,
and what is open.

## Identity and environment

- Repo: `github.com/mananpatel2491/Headless` (private), personal identity `mananpatel2491`
  (git identity routed by remote URL via `~/.gitconfig-personal`; `gh` may need
  `GH_TOKEN=$(gh auth token -u mananpatel2491)` when another account is active).
- Machine: macOS, Python 3.14, Playwright 1.62, Google Chrome 151 installed. Headless launches
  the installed Chrome (`channel="chrome"`), headed, on its own persistent profile at
  `~/.headless/chrome-profile`.
- Secrets backend: macOS Keychain (`security` CLI, account `headless`). GCP Secret Manager is
  code-ready but inactive: `gcloud` is not installed on this machine yet.
- Tooling gaps: `pwsh` absent, so `../worktree.ps1` cannot run; create worktrees by hand at
  `../worktrees/Headless/<branch>` with `git worktree add`.

## Known site traps

*(none yet; add one row per site as errands land: selector quirks, anti-bot behaviour,
session expiry, 2FA flow)*

## Errands run (dated)

| Date | Errand | Mode | Outcome |
| :--- | :--- | :--- | :--- |
| 2026-08-24 | `probe https://example.com` | preview | Ran twice against a temporary `HEADLESS_PROFILE_DIR`. Both runs exit 0, printed `Title: Example Domain`, and wrote a `previews/probe-<timestamp>.png/.json` pair. First run created the profile directory; second run reused it with no error, confirming the persistent-profile session survives between invocations (SC-001 groundwork; login persistence itself needs a real login-protected site, not yet run). |
| 2026-08-24 | `check_env` | n/a (self-test, no browser window) | Default (keychain) backend: 4/4 PASS in about 1.1s. `HEADLESS_SECRETS_BACKEND=gcp` with `HEADLESS_GCP_PROJECT` unset: `vault` row FAILs naming `HEADLESS_GCP_PROJECT`, other rows SKIP, exit 1 in about 0.07s (SC-004, SC-006). |

## Claude Code sessions (for resuming)

Record each working session's id here so it can be resumed with `claude --resume <id>`.

| Date | Session id | Notes |
| :--- | :--- | :--- |
| 2026-08-24 | `09a98ca6-0de1-49dc-83fb-d42e642c4b02` | Bootstrapped the repo from AVF (Director layer, Spec Kit 1.0.2), created the GitHub repo, spec 001 foundation |

## Open items

- Install `gcloud`, create the Secret Manager project through `terraform/`, and switch
  `HEADLESS_SECRETS_BACKEND=gcp` (Director-interactive auth needed).
- Seed the Headless Chrome profile with the logins the first real errands need (ITR portal,
  ticketing, insurance) by running `scripts/probe.py <url>` and logging in by hand.
- First real errand candidates (each its own spec): ITR portal walk (reuse `itr-wala` for the
  tax math; Headless owns only the portal steps up to Submit), movie-ticket availability,
  insurance quote collection, work-portal chores.
