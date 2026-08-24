# Research: Foundation Errand Runner

**Feature**: 001-foundation-errand-runner | **Date**: 2026-08-24

All Technical Context unknowns are resolved below. Each decision records the choice, the
reason, and the alternatives that were considered and rejected.

## D1. Browser automation engine

- **Decision**: Playwright for Python (1.62), launching the installed Google Chrome through
  `chromium.launch_persistent_context(user_data_dir, channel="chrome", headless=False)`.
- **Rationale**: Verified on this machine on 2026-08-24: Python 3.14 wheel installs, the
  installed Chrome 151 launches headed, and the user agent is not flagged as headless.
  Playwright gives selectors, waits, screenshots, and CDP attach (`connect_over_cdp`) in one
  dependency with no daemon.
- **Alternatives considered**: raw CDP over websockets (more code for no gain); Selenium
  (weaker waits, driver management); `browser-use` / Stagehand (LLM-driven agents; the
  constitution wants deterministic scripts with the model as an optional fallback, so they
  sit above this layer, not in it); Vercel `agent-browser` CLI (good for ad-hoc agent use,
  not for reviewable scripts).

## D2. Browser profile strategy

- **Decision**: a dedicated persistent profile directory outside the repo
  (`HEADLESS_PROFILE_DIR`, default `~/.headless/chrome-profile`), seeded by the Director
  logging in by hand in the visible window. Optional attach to a running Chrome via
  `HEADLESS_CDP_URL` for cases where the Director prefers to start Chrome with
  `--remote-debugging-port` themselves.
- **Rationale**: Login and 2FA are the dominant failure mode of browser agents (Stagehand's
  own evaluation: 6 of 10 failures). A persisted session sidesteps it. Chrome 136+ refuses
  remote debugging on the default user-data directory, so the everyday profile cannot be
  driven even if wanted; a separate profile is also the privacy boundary the constitution
  requires.
- **Alternatives considered**: driving the everyday Chrome (blocked by Chrome policy, and
  it would expose all of the Director's sessions to the script); a fresh profile per run
  (loses logins, triggers 2FA every time); bundled Chromium (fingerprinted more often than
  real Chrome by consumer sites).

## D3. Secrets backend

- **Decision**: one interface `get_secret(name) -> str` and `put_secret(name, value)` with
  two backends. `keychain` (default) shells out to the macOS `security` CLI
  (`add-generic-password -U`, `find-generic-password -w`, `delete-generic-password`) under
  a fixed account name. `gcp` uses `google-cloud-secret-manager`, imported lazily and only
  when selected; the dependency lives in `requirements-gcp.txt`, not the base requirements.
- **Rationale**: The Keychain round-trip was verified on this machine on 2026-08-24 with
  no extra dependency. `gcloud` is not installed here, so the GCP path is implemented and
  unit-tested against a fake client now and activated later (tracked in `terraform/README.md`
  and `MEMORY.md`), which keeps the code path honest without blocking the feature.
- **Alternatives considered**: the `keyring` library (extra dependency, same OS store
  underneath); `.env` secrets (forbidden by the constitution); 1Password / Bitwarden CLIs
  (viable later as extra backends behind the same interface; not needed for one person on
  one machine today).

## D4. Profile registry storage

- **Decision**: the registry is one JSON document stored in the vault under the item name
  `profile` and loaded through the same secrets interface; lookups use dotted paths
  (`identity.pan`, `address.home.line1`).
- **Rationale**: keeps every personal value in the vault, gives one place to edit, and lets
  the GCP backend hold the same document as a single secret later. Keychain generic
  passwords hold multi-kilobyte strings without issue.
- **Alternatives considered**: one vault item per field (dozens of items, hard to review);
  a gitignored `profile.local.json` (plaintext on disk, rejected); a database (overkill).

## D5. Run modes and the handoff

- **Decision**: `argparse` with a mutually exclusive group `--apply` / `--check`; absence of
  both is preview. Apply refuses when `sys.stdin.isatty()` is false or when the browser is
  headless. The handoff blocks on `input()` after printing "Your turn"; on return the
  session closes and reports if the Director had already closed the window.
- **Rationale**: mirrors the `--apply`-default-off convention of the Director's Atlassian
  toolkit and adds the human presence check the browser context needs. No submit path is
  implemented anywhere, so the absence is structural, not a flag default.
- **Alternatives considered**: a `--yes` style confirmation for submit (rejected by the
  constitution); a timeout on the handoff (rejected: the human decides the pace).

## D6. Preview artifacts and redaction

- **Decision**: `previews/<errand>-<UTC yyyymmddThhmmssZ>.png` plus `.json`. The JSON is
  built from a `PreviewRecord` whose field values are already masked by
  `redact(value) = "****" + value[-2:]` (or `"****"` when shorter than three characters).
  Registry and secret values are always masked; hand-authored literals declared in the
  script are shown as-is because they are not personal data.
- **Rationale**: the Director reviews the plan of typed fields by field name and a two
  character tail, enough to spot the wrong value without exposing it. Masking happens at
  record construction, so no later code path can serialize a raw value.
- **Alternatives considered**: full values in previews (rejected); no JSON, screenshot only
  (cannot be diffed or searched).

## D7. Typing sources

- **Decision**: a `FieldPlan` names its source as `registry:<dotted.path>`,
  `secret:<item>`, or `literal:<constant>`. The session's `fill()` accepts only a
  `FieldPlan`, never a raw string, and resolves the value itself at fill-time.
- **Rationale**: makes "registry is the only writable source" a type-level property:
  there is no API to type an arbitrary string, so an LLM-produced value has no path into a
  form. Literals exist for hand-authored constants (a form-type selection, a country code)
  and are visible in the preview for review.
- **Alternatives considered**: allowing `fill(selector, value: str)` with a lint rule
  (weaker; a lint can be bypassed).

## D8. Testing strategy

- **Decision**: `pytest`. Unit tests (no browser) for configuration parsing, mode
  resolution and refusals, redaction, registry lookup, the fake-backed secrets interface,
  and the preview record. One integration module drives a local fixture page
  (`tests/fixtures/form.html`) in headless Chromium through preview, check, and a stubbed
  apply (handoff confirm injected as a no-op, headed requirement bypassed only in the test
  via an explicit `allow_headless_apply_for_tests` argument). The integration module is
  skipped unless `HEADLESS_TEST_BROWSER=1`, so the commit gate stays under 10 seconds.
- **Rationale**: matches SC-005 (fast browser-free suite) while still proving SC-003 on a
  page that cannot change under us.
- **Alternatives considered**: testing against a live site (flaky, may write); mocking
  Playwright entirely (would not prove the gate).

## D9. Configuration

- **Decision**: a frozen `Config` dataclass loaded from environment variables with
  `python-dotenv` reading `.env` from the repo root; command-line flags override
  (`--profile-dir`, `--headless`, `--preview-dir`). `~` is expanded. The `gcp` backend
  requires `HEADLESS_GCP_PROJECT`; its absence is a `ConfigError` raised before any browser
  work.
- **Rationale**: same shape as the Atlassian toolkit's `config.py`, which has held up over
  95 scripts.

## D10. Environment self-test scope

- **Decision**: `check_env` verifies four rows: Chrome present (Playwright can resolve the
  `chrome` channel executable), Playwright runtime importable and its browser cache present,
  profile directory creatable and writable, vault reachable (keychain: add, read, delete a
  `headless-selftest` item; gcp: client constructible and project set). Each row prints
  PASS/FAIL with a hint; exit code 1 on any FAIL.
- **Rationale**: these are exactly the four things that failed or were missing while
  bootstrapping this machine (no `gcloud`, no CDP listener, Python 3.14 wheel doubt, profile
  policy).
