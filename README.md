# Headless

A personal errand runner. Headless drives Google Chrome on a profile you have logged into,
runs one script per errand, shows you a preview before it types anything, and always stops
before the step only you may take (pay, submit, e-verify, OTP). Quiet by default: preview and
check run invisibly; apply opens a real window but keeps it hidden until it is actually your
turn to act.

Built on the [Agentic-Vibe-Fleet](https://github.com/mananpatel2491/Agentic-Vibe-Fleet)
methodology. The constitution is `CLAUDE.md`; the pattern registry is `PATTERNS.md`; the
architecture map is `Project_Structure.md`.

## Setup

1. Install Google Chrome (the installed browser is used, not a bundled Chromium).
2. Create the environment:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python -m playwright install chromium
   ```
3. Copy `.env.example` to `.env`. It holds non-secret configuration only.
4. Store secrets in the macOS Keychain (default backend):
   ```bash
   security add-generic-password -a headless -s <secret-name> -w
   ```
   Set `HEADLESS_SECRETS_BACKEND=gcp` and `HEADLESS_GCP_PROJECT` to use Google Cloud Secret
   Manager instead (see `terraform/README.md`).
5. Activate the commit safety gate (mandatory - see "Public repo hygiene" below):
   ```bash
   git config core.hooksPath .githooks
   ```
6. Verify: `python scripts/check_env.py`. The `git_hooks` row confirms step 5 took effect.
7. Seed logins: `python scripts/probe.py https://<site> --apply` opens the Headless Chrome
   window - hidden at first, surfaced only at the "Your turn" prompt - so log in by hand once
   there and press Enter. The profile persists under `HEADLESS_PROFILE_DIR`, including the
   login itself, which now survives to later runs instead of needing to be seeded again every
   time. Add `--show` to keep the window visible throughout instead (useful the first time, to
   watch what happens).

## Running an errand

```bash
python scripts/<errand>.py            # preview: invisible, no site writes, artifact in previews/
python scripts/<errand>.py --check    # read-only: invisible, prove the selectors still resolve
python scripts/<errand>.py --apply    # fill up to the handoff point, window hidden until then,
                                       # then "Your turn"
python scripts/<errand>.py --show     # any mode, with the window visible from the start
```

The apply window no longer shows Chrome's "unsupported command-line flag: --no-sandbox"
warning bar. There is no submit flag. See `CLAUDE.md` for the rules that make this safe.

## Public repo hygiene

This repository is public. `scripts/scan_secrets.py` (standard library only, no install
step beyond what running the project already needs) looks for credentials and personal
identifiers at three points before a change becomes public history:

1. **Locally, before a commit exists.** `.githooks/pre-commit` runs
   `python3 scripts/scan_secrets.py --staged` and refuses the commit on a finding. This
   needs the one-time-per-clone step in Setup above (`git config core.hooksPath
   .githooks`) - `git` never runs a tracked hook file on its own, and
   `scripts/check_env.py`'s `git_hooks` row reports whether it is active on this clone.
2. **Before Claude Code writes a file.** `.claude/settings.json` registers a
   `PreToolUse` hook (`--stdin-hook`) that refuses a `Write`/`Edit`/`MultiEdit`/
   `NotebookEdit` whose new content contains a finding, feeding the (masked) reason back
   to the assistant so it can correct its own output. This fires only for a Claude Code
   session whose project root is this repository; a session started elsewhere relies on
   the git hook and CI below.
3. **In CI, on every push and pull request.** `.github/workflows/secret-scan.yml` runs
   `python scripts/scan_secrets.py --history` (every blob reachable from the pushed
   ref, not only its latest snapshot) alongside `gitleaks/gitleaks-action@v2`, both free
   for a public repository, and alongside GitHub's own secret scanning and push
   protection (already enabled on this repository, independent of anything here).

A finding never reveals the value it matched: only a fixed mask plus its own last two
characters. A known-safe value (a test fixture that intentionally resembles a real
secret) is exempted in `.scanignore` (one entry per line, an exact string or a `re:`
pattern) or with an inline `# scan:allow` marker on that one line - never by weakening a
pattern. See `specs/002-commit-safety-gate/` for the full design.

## Development

- Every feature runs the GitHub Spec Kit chain in Claude Code: `/speckit-specify`,
  `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`. Artifacts land in `specs/`.
- Commit gate: `python -m pytest -q`, `python scripts/verify_structure.py`, and
  `python scripts/scan_secrets.py --staged` (see "Public repo hygiene" above).
- Work on a `vX.Y.Z` branch in a worktree, `merge --no-ff` to `main`.
