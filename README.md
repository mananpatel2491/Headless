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
5. Verify: `python scripts/check_env.py`.
6. Seed logins: `python scripts/probe.py https://<site> --apply` opens the Headless Chrome
   window - hidden at first, surfaced only at the "Your turn" prompt - so log in by hand once
   there and press Enter. The profile persists under `HEADLESS_PROFILE_DIR`. Add `--show` to
   keep the window visible throughout instead (useful the first time, to watch what happens).

## Running an errand

```bash
python scripts/<errand>.py            # preview: invisible, no site writes, artifact in previews/
python scripts/<errand>.py --check    # read-only: invisible, prove the selectors still resolve
python scripts/<errand>.py --apply    # fill up to the handoff point, window hidden until then,
                                       # then "Your turn"
python scripts/<errand>.py --show     # any mode, with the window visible from the start
```

There is no submit flag. See `CLAUDE.md` for the rules that make this safe.

## Development

- Every feature runs the GitHub Spec Kit chain in Claude Code: `/speckit-specify`,
  `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`. Artifacts land in `specs/`.
- Commit gate: `python -m pytest -q` and `python scripts/verify_structure.py`.
- Work on a `vX.Y.Z` branch in a worktree, `merge --no-ff` to `main`.
