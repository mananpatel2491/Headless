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
- Secrets backend: as of v0.0.4 (2026-08-25, spec 004-age-vault), the default backend is a
  local, open-source, passphrase-encrypted `age` vault (`~/.headless/profile.age`), replacing
  the earlier plan to default to GCP Secret Manager plus PAM approval - the Director
  superseded that plan (a second Google account would have been needed solely to hold the
  approver role, since Google forbids approving one's own PAM grant, on top of a standing
  cloud dependency and its cost). `age` reads its passphrase from the terminal directly, never
  from anything Python passes it, so every secret- or registry-touching run needs the
  Director at the keyboard - this is the approval gate GCP's PAM was meant to provide, built
  instead from a property of the encryption tool itself. The macOS Keychain (`security` CLI,
  account `headless`) and GCP Secret Manager both remain selectable via
  `HEADLESS_SECRETS_BACKEND` (`keychain`, `gcp`) but neither is the default any more;
  `GcpBackend`'s code stays code-ready but inactive (`gcloud` is not installed on this machine
  yet).
- Tooling gaps: `pwsh` absent, so `../worktree.ps1` cannot run; create worktrees by hand at
  `../worktrees/Headless/<branch>` with `git worktree add`.
- Commit safety gate active: `core.hooksPath=.githooks` must be set in every clone/worktree
  (see README); CI scans full history on every push.

## Known site traps

- **Progressive (`www.progressive.com/auto/`), 2026-08-26** - refuses the automated quote-start
  submission under headless Chrome. Three bounded, synthetic-data-only recon walks (spec
  005-insurance-quote-comparison, research.md D8) all confirmed the two landing selectors
  (`#zipCode_mma`, `#qsButton_mma`) resolve, then found the same result across three different
  submission attempts (a direct click, an Enter keypress, a JS-dispatched click): three
  `Failed to load resource: 403 Forbidden` console errors and zero navigation away from the
  landing page within a 20-second wait, every time. Recorded as evidence for the repository's
  standing headless-user-agent question (`PATTERNS.md`'s "Quiet by default" entry) - untested
  whether a real `--apply` run (a real, non-headless windowed Chrome, per "quiet by default")
  hits the same block, since recon is headless-only by its own authorization (D8). The shipped
  Progressive walk (`headless/insurers/progressive.py`) therefore ships only the two landing
  steps; nothing past them is automated in this delivery.

## Errands run (dated)

| Date | Errand | Mode | Outcome |
| :--- | :--- | :--- | :--- |
| 2026-08-24 | `probe https://example.com` | preview | Ran twice against a temporary `HEADLESS_PROFILE_DIR`. Both runs exit 0, printed `Title: Example Domain`, and wrote a `previews/probe-<timestamp>.png/.json` pair. First run created the profile directory; second run reused it with no error, confirming the persistent-profile session survives between invocations (SC-001 groundwork; login persistence itself needs a real login-protected site, not yet run). |
| 2026-08-24 | `check_env` | n/a (self-test, no browser window) | Default (keychain) backend: 4/4 PASS in about 1.1s. `HEADLESS_SECRETS_BACKEND=gcp` with `HEADLESS_GCP_PROJECT` unset: `vault` row FAILs naming `HEADLESS_GCP_PROJECT`, other rows SKIP, exit 1 in about 0.07s (SC-004, SC-006). |
| 2026-08-25 | `check_env` | n/a (self-test, no browser window) | Director UAT of v0.0.1: 5/5 PASS (the `git_hooks` row, added in v0.0.2, brought the total from 4 to 5). |
| 2026-08-25 | `probe https://www.progressive.com/` | preview | Director UAT of v0.0.1: no window opened, correct. |
| 2026-08-25 | `probe https://www.progressive.com/ --apply` | apply | Director UAT of v0.0.1: window stayed hidden until "Your turn", correct; Director logged in by hand and pressed Enter. A following preview run of the same site then showed a logged-out page: the login did not persist. Root cause confirmed (specs/003-login-persistence): Chrome drops any cookie carrying no expiry (a session cookie, what most logins set) on every `launch_persistent_context` restart, even though a cookie with an expiry survives. Separately, the apply window showed Chrome's own "unsupported command-line flag: --no-sandbox" warning bar; root cause confirmed as Playwright adding `--no-sandbox` to every launch unless `chromium_sandbox=True` is passed. Both fixed in v0.0.3 (session cookie persistence on the launched-profile path; `chromium_sandbox=True` on every Chrome launch in the codebase). Site name only recorded here - no account details, no cookie names or values. |
| 2026-08-25 | `probe https://www.progressive.com/ --apply`, then `probe https://www.progressive.com/` | apply, preview | Director UAT of v0.0.3: the `--no-sandbox` warning bar is gone (confirmed by the Director). The seed exported 7 session cookies (login, loginrouter, account.apps and policyservicing hosts) and the following preview re-imported them, so persistence works as specified; the Director judged login state from the public homepage, which shows the same header for everyone, and accepted the automated proof instead of re-running. OPEN QUESTION, not a defect: whether this site honours a restored session under the headless `HeadlessChrome` user agent. One orchestrator check of the login URL 100 minutes after the seed landed on the login page, which an idle timeout explains as well as user-agent binding would; the discriminating test (seed, then headless and `--show` previews of the login URL within a minute) is in the session transcript and has not been run. |
| 2026-08-25 | `vault.py init` + `vault.py set profile` + `check_env` | n/a (vault maintenance, no browser errand) | Director UAT of v0.0.4: `check_env` 5/5 PASS with `vault PASS - age backend` after init (his first `set profile` before `init` was correctly refused with the init hint - the designed order guard). UAT-reported polish item, cosmetic only: every Playwright-using command on this machine (check_env, probe) prints a `Task was destroyed ... TargetClosedError` block AFTER its output - a Playwright 1.62 sync-API shutdown race on Python 3.14; exit codes are unaffected. Open: suppress or upstream-fix; fold into a later release. |

## Claude Code sessions (for resuming)

Record each working session's id here so it can be resumed with `claude --resume <id>`.

| Date | Session id | Notes |
| :--- | :--- | :--- |
| 2026-08-24 | `09a98ca6-0de1-49dc-83fb-d42e642c4b02` | Bootstrapped the repo from AVF (Director layer, Spec Kit 1.0.2), created the GitHub repo, spec 001 foundation |

## Open items

- **Spec 006 (policy extraction v2, v0.0.6, 2026-08-29): implementation delivered, Director UAT
  pending.** The Director's own first real declarations PDF (a three-page homeowners policy)
  exposed two independent gaps in v0.0.5's regex-only extraction: `pypdf`'s own plain-text
  extraction scrambled the multi-column layout, and an annual policy never states an "N-month"
  phrase v0.0.5's own term regex looks for. Fixed with a pipeline: layout-aware conversion
  (`pymupdf4llm`, `headless/policydoc.py`'s `convert_document`), a local-only Ollama model
  attempt (`headless/localllm.py`, falling back automatically to the unchanged v0.0.5 regex
  heuristics on any failure or `--no-llm`), a shared date-arithmetic term-derivation helper
  (`derive_term_from_dates`, an average-day month span not calendar-month arithmetic, used by
  both generators), and a mechanical sanity pass (`apply_sanity_pass`) that strips any figure not
  an exact digit-run-token match against the converted source text before the unchanged Director
  confirmation gate ever sees it. `PolicyReference` gains `generator`/`converter` provenance
  fields, surfaced in the comparison report's footer. `headless/config.py` gains
  `ollama_model`/`ollama_url`, with a value-free `ConfigError` refusing any
  non-`localhost`/`127.0.0.1` `HEADLESS_OLLAMA_URL` before any conversion or network call.
  **Opus verifier fix batch, same day, applied before commit**: 4 FIX-FIRST (a schema-valid but
  empty-coverages/all-empty-figures local-model response now folds into the ordinary
  failed-attempt fallback instead of being confirmed as-is; the sanity pass rewritten from
  substring containment to exact digit-run token matching, closing a real hallucination-detection
  gap an adversarial review found; docs reworded to the actual arithmetic/matching semantics; the
  one FR-019 exemption test rewritten against a fixture that actually exercises the exemption),
  1 IMPORTANT (a new test covers `scripts/quote_compare.py`'s own provenance 4-tuple wiring,
  previously untested), 6 NIT (the integration test now uses the real prompt builder and fails
  rather than skips on a schema mismatch; a tightened date-regex lookbehind plus a documented,
  tested known false negative; the local-model fallback note now prints even when the regex path
  also finds nothing; numeric leaves from the model are coerced to strings; a non-numeric figure
  value passes through untouched; this changelog row's own Files Affected list corrected) - see
  `Project_Structure.md`'s own v0.0.6 row for the full account. Unit suite green after the fix
  batch (574 passed, 9 skipped, up from the 478/8 v0.0.5 baseline), `verify_structure.py`
  SUCCESS, `scan_secrets.py --staged` clean, opt-in browser suite green (8 passed), and the
  opt-in `HEADLESS_TEST_OLLAMA=1` integration test run twice against the real local
  `qwen3.5:35b` server on this machine - passed both times (6.48s, then 6.66s after the fix
  batch), schema-valid response each time. Pending: the Director's own
  run against his real declarations PDF with his own Ollama running (quickstart.md Scenarios
  1-5) - this delivery's own brief is implementation-only and never touches `~/.headless/` or
  opens a real browser window.
- **Spec 005 (insurance quote comparison, v0.0.5, 2026-08-25/26): implementation delivered,
  Director UAT pending.** Walk framework (`headless/steps.py`, `Session.click`/`capture`,
  `Errand.walk()`), type-discriminated array addressing in `ProfileRegistry` plus
  `RegistryAmbiguous`, the `profile.template.json` drift test, the capture model
  (`headless/capture.py`), per-asset `policy_doc` PDF extraction and Director confirmation
  (`headless/policydoc.py`, `scripts/policy_extract.py`), the `Decimal`-only comparison engine
  (`headless/compare.py`), the self-contained HTML report generator (`headless/report.py`), the
  Progressive walk (landing-page-only, see the site-trap entry above), and the multi-insurer
  orchestrator (`scripts/quote_compare.py`) are all implemented and unit-tested. Pending: the
  Director's own `--apply` run against the real Progressive site (does the headless-only block
  found in recon also occur in a real, non-headless apply window - unverified either way);
  `scripts/policy_extract.py` against a real policy PDF (the heuristics are unproven against real
  declarations-page layouts, research.md D15's own accepted residual); the profile-seeding round
  trip (quickstart Scenarios 1-2); the full quickstart Scenarios 3-10.
- Run this repository's own `vault.py init` / `vault.py set profile` on this machine (spec
  004-age-vault; not yet done in this delivery, since the brief for that delivery excluded
  touching `~/.headless/`) and record the outcome in the "Errands run" table below.
- (Superseded 2026-08-25, spec 004-age-vault) ~~Install `gcloud`, create the Secret Manager
  project through `terraform/`, and switch `HEADLESS_SECRETS_BACKEND=gcp`~~: the GCP Secret
  Manager plus PAM plan is superseded by the local `age` vault above; `gcloud` install is no
  longer on the critical path to a working secrets backend, only to activating `gcp` as a
  non-default, explicitly-selected alternative.
- Seed the Headless Chrome profile with the logins the first real errands need (ITR portal,
  ticketing, insurance) by running `scripts/probe.py <url>` and logging in by hand.
- First real errand candidates (each its own spec): ITR portal walk (reuse `itr-wala` for the
  tax math; Headless owns only the portal steps up to Submit), movie-ticket availability,
  insurance quote collection, work-portal chores.
