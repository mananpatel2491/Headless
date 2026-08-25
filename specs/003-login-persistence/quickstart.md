# Quickstart: Login Persistence

**Feature**: 003-login-persistence | **Date**: 2026-08-25

Runnable validation scenarios that prove the feature end-to-end, including the exact re-UAT
script the Director ran when he first found the two defects. Contracts are in
[contracts/session-state.md](contracts/session-state.md); entities in
[data-model.md](data-model.md).

## Prerequisites

- From the worktree root, the existing `.venv` (no new dependency):
  ```bash
  source .venv/bin/activate
  ```
- No setup step beyond what v0.0.1 and v0.0.2 already require. Nothing about this feature is
  configured: the state file's location is derived from whatever `HEADLESS_PROFILE_DIR` already
  resolves to (default `~/.headless/chrome-profile`).

## Scenario 1: the Director's re-UAT - a seeded login persists (US1, SC-001)

This is the same shape of run that first found the defect, repeated to confirm the fix.

```bash
python scripts/probe.py <login page URL> --apply
```

Log in by hand at the "Your turn" prompt, exactly as before, then press Enter. Then:

```bash
python scripts/probe.py <a page only reachable while logged in>
```

Expected: the preview's printed `Title:` line, and the screenshot in the new `previews/*.png`, show
the logged-in page - not a login form or a logged-out landing page. Confirm two ways:

1. **JSON**: open the newest `previews/probe-*.json` and read its `"title"` field; it should
   match the logged-in page's actual title, not the site's login-page title.
2. **Screenshot**: open the newest `previews/probe-*.png`; it should visibly be the logged-in
   page (masked form controls per the existing screenshot convention, but page-rendered content,
   including a login state the page itself renders, is unaffected by that mask - see
   `PATTERNS.md`'s "Screenshots are masked, not redacted" entry).

Clean up disposable output after confirming: `rm -rf previews` (`previews/` is gitignored and
documented as disposable; this is routine hygiene, not part of the proof itself).

**If the page still shows logged out**: check whether the site's bot defense may have detected
the headless preview's `HeadlessChrome` user agent and logged the profile out server-side - this
is the accepted residual in research.md D5, not necessarily a regression. Re-run the same page
with `--show` (a visible, non-headless run) to see what the site actually renders, and re-seed
with `--apply` if needed.

## Scenario 2: confirming the sandbox warning bar is gone (US2, SC-002)

```bash
python scripts/probe.py <any URL> --apply
```

Expected: at the "Your turn" prompt, the visible Chrome window has no yellow warning bar reading
"You are using an unsupported command-line flag: --no-sandbox. Stability and security will
suffer." above the page content. This is the entire observable proof for a Director doing this by
eye; the unit-level proof (below) checks the same fact mechanically.

## Scenario 3: unit-level proof, no browser (SC-002, SC-003, SC-004)

```bash
python -m pytest -q tests/test_session.py -k "cookie or sandbox"
python -m pytest -q tests/test_check_env.py -k sandbox
```

Expected: every import/export/note-line/atomic-write/mode/CDP-exclusion test and both
`chromium_sandbox=True` launch-kwargs tests pass, and the combined run for this feature's own
tests completes in well under 1 second (SC-003) - no browser is opened by any of these.

## Scenario 4: the state file's own safety properties (US3, SC-004, SC-005)

After Scenario 1 has run at least once (so a real state file exists):

```bash
ls -l "$HEADLESS_PROFILE_DIR/session-cookies.json" 2>/dev/null || \
  ls -l ~/.headless/chrome-profile/session-cookies.json
```

Expected: permission bits read `-rw-------` (owner read/write only - mode `0600`).

```bash
cat ~/.headless/chrome-profile/session-cookies.json | python -m json.tool | head -20
```

Expected: a JSON array of cookie objects; every object's `"expires"` field reads `-1` (no
entry with any other expiry value should ever appear here - if one does, that is a defect in the
export filter, not an expected state). Do not paste this output anywhere outside a local
terminal: it contains real cookie values from whatever site was last seeded.

## Scenario 5: proving persistence without a real login-protected site (SC-001, SC-007)

For a repeatable, network-free proof that does not depend on any real site's availability or
login flow:

```bash
HEADLESS_TEST_BROWSER=1 python -m pytest -q tests/test_gates_browser.py -k persist
```

Expected: the opt-in browser test passes, headless, with no visible window and no request to any
host outside `127.0.0.1`/`file://`. It sets a `document.cookie` session cookie on a local fixture
page, closes the `Session`, relaunches on the same profile directory, and asserts the same cookie
is present before any navigation on the second launch - the same claim Scenario 1 proves by hand
against a real site, proven here mechanically and repeatably.

## Scenario 6: the CDP-attach path is untouched (FR-012, SC-006)

```bash
python -m pytest -q tests/test_session.py -k cdp_cookie
```

Expected: a test asserting that, on the CDP-attach path, neither the import function nor the
export function is ever called, and the state file is never created, read, or modified, passes.
There is no manual/live equivalent of this scenario worth running by hand: the whole point is
that nothing observable happens on this path, which is exactly what the unit test is built to
prove.

## Scenario 7: commit gate (all user stories)

```bash
python -m pytest -q
python scripts/verify_structure.py
git add -A
python scripts/scan_secrets.py --staged
```

Expected: the full unit suite passes (including this feature's new tests), `verify_structure.py`
reports SUCCESS with every changed/new file accounted for in `Project_Structure.md`'s Changelog,
and `scan_secrets.py --staged` reports clean - this feature's own state-file example content in
any test fixture must use an obviously synthetic value (for example `sess=1`, domain
`example.com`), never anything shaped like a real credential.
