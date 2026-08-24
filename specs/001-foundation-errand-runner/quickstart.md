# Quickstart: Foundation Errand Runner

**Feature**: 001-foundation-errand-runner | **Date**: 2026-08-24

Runnable validation scenarios that prove the feature end-to-end. Contracts are in
[contracts/cli-and-package.md](contracts/cli-and-package.md); entities in
[data-model.md](data-model.md).

## Prerequisites

- macOS with Google Chrome installed.
- From the repo (or worktree) root:
  ```bash
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  python -m playwright install chromium
  cp .env.example .env
  ```

## Scenario 1: environment self-test (US4, SC-004)

```bash
python scripts/check_env.py
```

Expected: four rows (`browser`, `playwright`, `profile_dir`, `vault`) all `PASS`, exit 0,
under 30 seconds, no browser window. To see a failure row: `HEADLESS_SECRETS_BACKEND=gcp
python scripts/check_env.py` on a machine without `HEADLESS_GCP_PROJECT` prints a `FAIL`
on `vault` naming the missing setting, exit 1.

## Scenario 2: probe and persistent login (US1, SC-001)

```bash
python scripts/probe.py https://example.com
```

Expected: a visible Chrome window opens on the page, the title `Example Domain` is
printed, and `previews/probe-<timestamp>.png` and `.json` exist. The profile directory
`~/.headless/chrome-profile` now exists.

For the login persistence check, run `python scripts/probe.py <login-protected site>
--apply`, log in by hand in the window, press Enter in the terminal, then run the same
command again: the page opens already logged in.

## Scenario 3: secrets never leak (US2, SC-002)

```bash
security add-generic-password -a headless -s headless-test-secret -w 'hunter2-XY' -U
python -m pytest -q tests/test_redaction.py tests/test_preview.py
security delete-generic-password -a headless -s headless-test-secret
```

Expected: tests pass; `tests/test_preview.py` asserts that a record built from a secret
contains only `****XY`. The fake-vault tests also cover `SecretMissing` and the `gcp`
misconfiguration path (SC-006).

## Scenario 4: gates on the fixture form (US3, SC-003)

```bash
HEADLESS_TEST_BROWSER=1 python -m pytest -q tests/test_gates_browser.py
```

Expected: three passes. Preview leaves every fixture field empty; check reports each
dependent selector found (and one deliberately missing selector as missing); apply (with
the handoff confirm stubbed) fills the mapped fields and the fixture's submit control is
never clicked (the page records clicks into a hidden element the test reads).

Refusals without a browser:

```bash
python -m pytest -q tests/test_gates.py
```

Expected: `--apply` from a non-tty is refused; `--apply --headless` is refused; no errand
parser accepts `--submit`.

## Scenario 5: commit gate (SC-005)

```bash
python -m pytest -q
python scripts/verify_structure.py
```

Expected: the browser-free suite passes in under 10 seconds (the browser module is skipped
without `HEADLESS_TEST_BROWSER=1`) and the structure check prints SUCCESS.
