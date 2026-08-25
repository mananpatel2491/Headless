# Pattern Registry: Headless

This document records established engineering patterns and design decisions so that later
sessions inherit them instead of re-litigating them. Every entry reflects the actual codebase.

## 1. Architectural Patterns

- **Thin package, one script per errand** (inherited from the Director's Atlassian toolkit).
  Reusable mechanics live in `headless/` (config, browser session, secrets, profile, gates,
  preview). Each errand is one runnable `scripts/<errand>.py` that composes them. Extend the
  package; never re-implement browser or secrets plumbing inside a script.
- **Preview-by-default, `--apply` to act, human handoff at the terminal step.** Scripts share
  the gate helpers in `headless/gates.py`. The three modes are `preview` (default, no site
  writes), `apply` (fills up to the declared handoff point), and `check` (read-only selector
  probe). There is no submit mode by design; see `CLAUDE.md`.
- **Registry is the only writable source.** The profile registry (`headless/profile.py`) is
  the sole source of values a script may type, alongside the vault and hand-authored literals
  (`headless/fields.py`'s `Source`). Field mappings are hand-authored dicts inside the errand
  script, reviewed in the preview before `--apply`.
- **`Session.fill` is the only sanctioned way to type; `Session.page` is exposed for reads
  (v0.0.1).** A structural test (`tests/test_no_direct_typing.py`) parses `scripts/*.py` with `ast` and
  refuses any direct `.fill(`, `.type(`, `.press(`, `.click(`, `.dblclick(`, `.select_option(`,
  `.check(`, or `.set_input_files(` call on a page or locator, so an errand cannot type outside the registry/vault/literal path
  without failing the commit gate. This replaces an earlier, weaker claim ("derived or
  LLM-produced values are structurally unwritable") that described only the `FieldPlan`/`Source`
  type shape, not an enforced boundary; the mechanical scan is the actual enforcement.
- **Secrets backend seam.** `headless/secrets.py` exposes `get_secret(name)` over a backend
  chosen by `HEADLESS_SECRETS_BACKEND`: `keychain` (macOS `security` CLI, default) or `gcp`
  (Secret Manager, lazy import, only when configured). Scripts never read `.env` for secrets;
  `.env` holds non-secret configuration only.
- **Persistent Chrome profile.** `headless/session.py` launches the installed Chrome
  (`channel="chrome"`) with `launch_persistent_context` on `HEADLESS_PROFILE_DIR`, or attaches
  over CDP when `HEADLESS_CDP_URL` is set. Logins are seeded by the Director in that window
  and survive between runs. Reads retry; writes never retry.
- **Quiet by default (v0.0.1, Director decision 2026-08-24).** Two independent `Config` axes:
  `headed` (can a real windowed Chrome process be produced at all - `HEADLESS_HEADED`,
  `--headless`, unchanged in meaning) and `show` (is the window visible from launch -
  `HEADLESS_SHOW`, `--show`, new, default `False`). `headless/session.py`'s
  `_effective_headed(mode, config)` decouples the two: preview/check ignore `config.headed`
  entirely and launch invisible (Chrome's own headless mode) unless `show` is set, regardless
  of `HEADLESS_HEADED`; apply always launches a real window (`config.headed`, gated as before
  by `resolve_mode`) but, unless `show`, hides it immediately after launch
  (`Session._hide_window`, called only on the launched - never the CDP-attach - path so the
  Director's own browser window is never touched) and restores it (`_restore_window`) only at
  `handoff()`, right before printing "Your turn". `--headless` and `--show` are mutually
  exclusive CLI flags; `--headless` with `--apply` is still refused (unchanged: the handoff
  needs a window). Empirically verified on this machine (macOS, Chrome 151, no Accessibility
  permission granted to this automated session) that hiding is imperfect: CDP's
  `Browser.setWindowBounds({"windowState": "minimized"})` never took effect (the window kept
  reporting - and staying - `"normal"`); the `--start-minimized` and
  `--window-position=-32000,-32000` launch args were both silently ignored; `osascript`/System
  Events native minimize failed with "not allowed assistive access" (-1719, needs an
  interactive one-time Accessibility grant this session cannot make). What DID have a partial
  effect: a post-launch `Browser.setWindowBounds` position move - macOS clamps it so some
  minimum sliver stays reachable, smallest pushing towards the bottom-right of the screen on
  this display (roughly a 40x131 point corner sliver, versus ~258 points or more pushing
  left/up). `_hide_window` therefore does both (attempts the CDP minimize, harmless if
  ineffective and may work on another machine/Chrome version, then pushes towards that corner)
  and is explicitly documented as best-effort, not a hard guarantee of zero visible pixels; a
  future session with Accessibility permissions granted could add a real `osascript` minimize
  as a strictly better mechanism. Restore uses explicit on-screen `left`/`top` plus
  `page.bring_to_front()`. **Correction to an assumption used to draft this feature**: this
  Chrome (channel `chrome`, v151, launched `headless=True` via Playwright, both with and
  without an explicit `--headless=new` arg) DOES report `HeadlessChrome` in
  `navigator.userAgent` (verified 2026-08-24) - the "new headless mode drops HeadlessChrome
  from the UA" claim does not hold here. Anti-bot fingerprinting of headless Chrome (by UA or
  otherwise) is a real, unresolved risk for real errands; `--show` (or `--check` first, to see
  what a site does before committing to headless preview) is the escape hatch.
- **CDP attach never touches the Director's own tabs (v0.0.1, FIX-FIRST 5).** On the CDP
  path, `Session.__enter__` always opens a brand-new page (`context.new_page()`), never
  reusing `context.pages[0]` - an attached context may already hold the Director's own
  actively-used tabs. `__exit__` closes only that page, then calls `browser.close()` to
  disconnect. Verified live 2026-08-24 (this machine): attaching to a real Chrome started
  with `--remote-debugging-port`, using it, and exiting the `Session` leaves the original
  Chrome process running and its pre-existing tab untouched; `browser.close()` on a
  CDP-attached `Browser` disconnects the client, it does not terminate the real Chrome
  process. The launched (persistent-profile) path is unaffected: it owns the whole browser
  process and closes the context normally. Attaching is not a privacy boundary the same way
  the persistent profile is, though: when attaching over CDP (`HEADLESS_CDP_URL`), attach only
  to a Chrome started for Headless - the attached context carries every session that browser
  holds.
- **Screenshots are masked, not redacted (v0.0.1).**
  `headless/preview.py` writes `<errand>-<UTC timestamp>.png` and `.json` under
  `HEADLESS_PREVIEW_DIR` (default `<repo root>/previews`, gitignored). The JSON's `fields`
  pass through `PreviewRecord.__post_init__`'s redaction (secrets/registry values masked to
  `****` plus the last two characters; literals shown as-is) before the record exists in any
  other form. The `.png` is different: `Session.screenshot()` injects a `<style>` tag
  (`-webkit-text-security: disc` on `input`/`textarea`/`[contenteditable]`; transparent text
  on `select`) right before capturing, then removes it, so a just-typed secret or registry
  value is not legible as text in the image - but this is a *visual mask*, not redaction, and
  page-rendered data the mask cannot reach (e.g. a logged-in portal displaying the Director's
  own name) can still appear. The mask preserves length (one disc per character), so a
  screenshot still discloses how long a typed value is. If the page's own CSP (e.g.
  `style-src 'self'`) refuses the mask's inline `<style>` injection, `screenshot()` never
  falls back to capturing unmasked: it returns `None` (same as `--no-screenshot`, JSON-only)
  and prints one note (`note: screenshot skipped, the page's CSP blocked the mask`).
  `--no-screenshot` / `HEADLESS_SCREENSHOTS=0` (`Config.screenshots`, default `True`) skips the
  screenshot entirely and writes only the JSON. Because of the screenshot's weaker guarantee,
  `previews/` as a whole is vault-grade local data: gitignored, never shared or attached
  anywhere, disposable. See `CLAUDE.md`'s Secrets section for the same reasoning spelled out
  for the Director.
- **Cross-Platform Automation (AVF).** Maintenance and errand scripts are Python with
  `argparse`; Spec Kit helper scripts are the Python variant (`.specify/scripts/python/`).
- **Automation-First CLI (AVF).** Every script runs non-interactively with flags
  (`--apply`, `--check`, `--profile-dir`, `--headless`) so it can run from cron or CI, and
  every action-taking path has a safe preview.
- **Proactive Hardening (AVF).** When touching an existing file, audit it for leaked secrets,
  injection through page content, and resource leaks (unclosed browser contexts); patch
  immediately.
- **Spec-Driven Feature Workflow (Spec Kit).** Features beyond trivial fixes run
  `specify -> clarify -> plan -> tasks -> implement` and leave durable artifacts in
  `specs/NNN-slug/`. `.specify/memory/constitution.md` is always a distillation of
  `CLAUDE.md` plus this file, with an explicit precedence header; it never introduces new
  rules.
- **Lazy registry loading (v0.0.1).** `headless/errand.py`'s `Errand.run()` never calls
  `ProfileRegistry.load(vault)` eagerly; it hands `plan()` a lazy wrapper that only
  fetches the `profile` vault item on the first `.get()` call a `FieldPlan` actually
  triggers. A read-only errand with an empty plan (`probe.py`) therefore never needs a
  `profile` vault item to exist. Apply mode still pre-resolves every planned source
  (which may trigger the lazy load) before any browser window opens.
- **check_env's "browser" row launches, briefly, headless (v0.0.1).** Playwright's
  Python API has no public way to resolve a `channel="chrome"` executable path without
  starting it (only `chromium.executable_path` for the bundled, non-channel browser).
  `scripts/check_env.py` proves Chrome is reachable by launching it with `headless=True`
  and closing it immediately; this does not violate "check_env opens no window" because
  no visible window is created (the headed/headless distinction used throughout this
  repo is about visibility, not process existence).
- **Commit safety gate (v0.0.2).** The repository went public 2026-08-24. One scanner,
  `scripts/scan_secrets.py`, is a direct instance of the **Cross-Platform Automation**
  pattern below: standard-library-only Python, `argparse`, so every enforcement layer
  works on a fresh clone with no install step beyond what the project already needs -
  it runs identically under the project's `.venv` and under the macOS system `python3`
  (verified 3.9.6 on this machine), since `.githooks/pre-commit` cannot assume a
  virtualenv is active. Four mutually exclusive modes (`--staged`, `--paths`, `--history`,
  `--stdin-hook`) share one pattern table, one masking function
  (`redact(value) = "****" + value[-2:]`, identical to `headless/preview.py`'s
  convention), and one `.scanignore` allowlist (exact string or `re:` entry, plus an
  inline `# scan:allow` marker for a single line) so a pattern is added once and every
  layer inherits it. `scan_secrets.py` deliberately does not import `headless.config`
  (which pulls in `python-dotenv`, a non-stdlib dependency) - importing it would break
  the zero-install guarantee the pre-commit hook and the Claude Code hook both depend on
  before `pip install` has ever run on a fresh clone. `--history` scans every blob
  reachable from `HEAD` exactly once (deduped by blob sha via `git rev-list --objects`
  piped into one `git cat-file --batch` call, two subprocess calls total regardless of
  history size) rather than once per commit, so it stays well under its 2-second budget
  even though it walks the whole reachable history, not just the working tree. The
  `--stdin-hook` mode's deny/allow signaling mirrors `~/.claude/hooks/no-em-dash.py`
  exactly (JSON `hookSpecificOutput`/`permissionDecision` on stdout, always exit `0`,
  fail-open on any input it cannot parse) rather than an exit-code convention, matching
  the one other `PreToolUse` hook already solving the same kind of problem in this
  environment; both hooks are registered on the same `Write|Edit|MultiEdit|NotebookEdit`
  matcher and run independently, either one denying is enough. `.githooks/pre-commit`
  locates the repository root via `git rev-parse --show-toplevel` (so it works when
  invoked from any subdirectory) and runs the system `python3`, never the venv, since a
  git hook's environment does not activate one; `core.hooksPath` is a per-clone git
  setting a tracked file cannot turn on by itself (git never executes a tracked
  `.git/hooks` file), so `scripts/check_env.py` gained a fifth row, `git_hooks`, to catch
  a clone where this was missed. **Empirically discovered false positives (v0.0.2, this
  machine, 2026-08-24), corrected 2026-08-25**: the first real `--history` run against this
  repository's own pre-existing v0.0.1 history found four legitimate, non-secret matches the
  `phone_us` and `generic_secret_assignment` patterns fired on (a Spec Kit template file's
  SHA-256 hash, a bash `int64`-max constant appearing twice, and a Python f-string that quotes
  two `Source` prefix kinds back to back in a way that reads like a keyword-colon-quote
  assignment). These were first handled by adding each as its own exact-string entry to
  `.scanignore` rather than weakening either pattern - and a same-day guidance sentence here told
  a future session to do the same for the next large integer or hex/base64 hash it hit. A
  post-implementation review the next day (2026-08-25) found that guidance backwards: each of the
  four was a genuine **pattern-boundary bug** - `phone_us` and `generic_secret_assignment` had no
  digit-adjacency or embedded-delimiter guard, so a shape-only match inside an unrelated large
  number or a piece of prose could fire - not a property of large integers or hashes in general.
  Both were fixed at the pattern instead: `phone_us` (and `phone_in`, `payment_card`) gained a
  `(?<![0-9A-Za-z])`/`(?![0-9A-Za-z])` alphanumeric-boundary assertion so a window inside a longer digit run can no
  longer match at all, `aadhaar_in` and `iban` gained a checksum (Verhoeff, mod-97) the same way
  `payment_card` already had Luhn, and `generic_secret_assignment` was tightened so its captured
  value can never contain an embedded quote or comma, closing the two-adjacent-quoted-strings
  shape that produced the fourth false positive. All four `.scanignore` entries for these were
  then removed as no longer needed (proven by `--history` on this repository's own real history
  still exiting `0` - D10). **Corrected guidance**: a false positive on a non-secret shape is a
  pattern-boundary bug, not a fact about the world to work around; fix the pattern with a boundary
  assertion or a checksum, and allowlist only genuine synthetic fixtures (a value that really is
  secret- or PII-shaped and exists on purpose, such as this feature's own test fixtures) - never a
  value that merely happens to collide with an under-specified pattern.
- **Session cookie persistence (v0.0.3, UAT of v0.0.1 2026-08-25).** A login that does not
  survive between runs defeats the point of the persistent Chrome profile: Chrome drops any
  cookie carrying no expiry (a session cookie - what most logins actually set) on every
  `launch_persistent_context` restart, even though a cookie that already carries an expiry
  survives on its own (verified empirically before this feature was scoped; the Headless
  profile, `~/.headless/chrome-profile/Default/Cookies`, held 18 persistent tracking cookies
  for `.progressive.com` and zero cookies for any account host after the UAT run). Also
  verified and recorded as a negative result (2026-08-25, this machine): seeding Chrome's own
  `session.restore_on_startup = 1` ("continue where you left off") preference into
  `Default/Preferences` before the first launch does **not** keep session cookies across a
  `launch_persistent_context` restart under Playwright - the preference itself survives, but
  the session cookies are still dropped the same as without it. This is why persistence needed
  its own export/import mechanism rather than relying on that Chrome preference. Persistence
  lives entirely in
  `headless/session.py`, on the launched-profile path only (D1) - the CDP-attach path
  (`HEADLESS_CDP_URL` set) neither reads nor writes anything this feature adds, because that
  browser's session cookies are the Director's own Chrome's problem to keep or drop, not
  Headless's. The state file's location is derived, never configured (D2):
  `<profile_dir>/session-cookies.json`, no new environment variable, no new CLI flag.
  **Import** happens in `Session.__enter__`, immediately after `self.page = ...` and before
  any navigation: if the file exists, parse it and call `context.add_cookies(entries)` once.
  **Export** happens in `Session.__exit__`, immediately before `self.context.close()`: read
  `context.cookies()`, keep only the entries with `expires == -1` (Chrome's own persistent
  profile already keeps anything with a real expiry), and replace the file's entire previous
  content via a temp file in the same directory plus an atomic `os.replace`, always leaving
  it at mode `0600` (D3). Every failure mode collapses to the same fail-soft shape (D4): a
  **missing** file is the expected shape of a fresh or never-seeded profile and prints
  nothing; an unreadable, malformed, or empty file, or `context.add_cookies()` itself
  rejecting the whole call, is caught and produces exactly one note -
  `note: session cookies not restored (<ExceptionClassName>)` on import,
  `note: session cookies not saved (<ExceptionClassName>)` on export - naming only the
  caught exception's class, never its message (a parse error on untrusted JSON can quote
  back a fragment of what it failed to parse) and never a cookie name or value. Export runs
  on every clean close, in every mode (preview, check, apply), not apply only, so a read-only
  run that happens to observe a refreshed session cookie keeps the state file current too.
  Two residuals are accepted, not solved by this feature: a site's bot defense that logs the
  profile out server-side because the headless preview/check user agent still identifies as
  `HeadlessChrome` on this machine (this file's own "Quiet by default" entry) causes that
  run's export to faithfully write whatever session cookies remain, which may be none -
  recovery is the same `--apply` seed the Director already knows; and a login that lives in
  `sessionStorage` rather than a cookie (the India ITR e-filing portal's JWT is the known
  example in this repository's own `MEMORY.md`) is not persisted at all, since
  `context.cookies()` has no visibility into `sessionStorage`. See
  `specs/003-login-persistence/` for the full research and contracts.
- **Chrome sandbox on (v0.0.3).** The apply window showed Chrome's own "unsupported
  command-line flag: --no-sandbox" warning bar at the handoff - the one window the Director
  actually watches. Root cause, verified by reading Playwright's own driver bundle
  (`coreBundle.js`, line 43075): `if (options.chromiumSandbox !== true) chromeArguments.push
  ("--no-sandbox")` - Playwright adds `--no-sandbox` to every Chromium launch unless
  `chromium_sandbox=True` is passed explicitly; there is no other flag involved. The fix is
  that exact option, passed on every Chrome launch in the codebase: `headless/session.py`'s
  `launch_persistent_context` call (the launched-profile path) and
  `scripts/check_env.py`'s `_check_browser()` probe (`chromium.launch`), the latter included
  even though the Director never sees that launch, for the same consistency reason this
  file's own "check_env's 'browser' row launches, briefly, headless" entry already gives for
  that probe existing at all. No flag exists, or may be added, to turn the sandbox back off.
  Verified live on this machine: launching this way starts normally and the resulting page
  reads back a correct title and user agent - passing the option introduces no new failure
  mode here.
- **Age vault (v0.0.4, spec 004-age-vault).** The Director replaced the planned GCP Secret
  Manager plus PAM approval backend with a local, open-source, passphrase-encrypted vault
  built on `age`: `HEADLESS_SECRETS_BACKEND` gains `"age"` and it is now the *default* (was
  `"keychain"`), so a fresh clone on any platform - not only macOS - gets a working backend
  with zero configuration (research.md D1). `KeychainBackend` and `GcpBackend` are unchanged
  and remain selectable; the GCP plan itself is superseded, not deleted (`terraform/README.md`
  carries the status note). The vault file's path is `Config.age_file`, resolved from
  `HEADLESS_AGE_FILE`, default `~/.headless/profile.age`; like `preview_dir`'s existing rule,
  ANY value still relative after `~`-expansion raises `ConfigError` - stricter than
  `profile_dir`'s current handling, because a misresolved vault path could mean a script
  decrypts, or worse writes, a file the Director never intended to touch (D2). `.gitignore`
  gained `*.age` as a second line of defense; the file lives outside the repo by default.
  The vault's whole decrypted content is one JSON object (`dict[str, str]`, no wrapper, no
  version field - the same "no speculative structure" reasoning `SessionCookieState` already
  established in v0.0.3); `get_secret("profile")` keeps returning the registry JSON string
  unchanged, so `ProfileRegistry` and every existing caller are untouched by this feature
  (D3). `AgeBackend.get_secret` decrypts **at most once per process**: the first call runs
  `age -d <vault_file>` (or an injected fake runner, FR-009/NFR-002) with stdout captured
  entirely in memory, parses it as JSON, and caches the mapping for the rest of the process;
  every later call, for any name, is served from that cache with zero further runner calls and
  zero further prompts - this is what makes the passphrase gate liveable (an errand plan
  touching three registry paths still prompts once, not three times, D4). `age` prompts for
  the passphrase on the controlling terminal (`/dev/tty`) directly, never on this process's
  own stdin/stdout, so **no code in `headless/` or `scripts/` ever reads, builds, stores, or
  logs the passphrase's characters** - this is the entire headline security property the
  feature is built on, verified empirically before the feature was scoped (a full
  encrypt-then-decrypt round trip, byte-exact, on this machine's `age` 1.3.1). A failed
  decrypt (wrong passphrase, corrupted or non-`age` file) raises a value-free `GateRefused`
  naming only `age`'s exit code plus one fixed hint (`"wrong passphrase, corrupted vault, or no terminal for the passphrase prompt"`)
  - never any fragment of `age`'s own stderr, on the theory that stderr could in principle
  echo back something about the file it failed to read, the same reasoning v0.0.3's
  session-cookie notes already applied to a caught exception's message (FR-012, NFR-004).
  `AgeBackend.put_secret`/`delete_secret` always raise, directing the caller to
  `scripts/vault.py`: this is a structural guarantee, not a convention, that an errand can
  never trigger a surprise decrypt-mutate-re-encrypt prompt chain mid-run (FR-013, D5).
  `scripts/vault.py` is therefore the *only* place the vault is ever written -
  `init`/`set NAME`/`unset NAME`/`list`/`path` subcommands, each its own passphrase prompt,
  nothing cached across invocations (FR-021, matching `AgeBackend`'s own per-process-only
  cache). Every write follows DECRYPT (skipped for `init`) -> MUTATE (in memory only) ->
  RE-ENCRYPT (skipped for `list`/`path`): the mutated document's JSON bytes are piped to
  `age -e -p -a` via the child process's `stdin` (never a temp plaintext file - `age` reads
  its own passphrase prompt from `/dev/tty`, so `stdin` is completely free for this), the
  resulting ciphertext is captured from `stdout` and written to a temp file in the vault's own
  directory, then atomically replaced onto the vault path (`os.replace`) at mode `0600` -
  reusing `headless/session.py`'s `_export_session_cookies` atomic-write shape from v0.0.3
  exactly, rather than a second, independently-reviewed implementation of the same job (D6).
  `set NAME`'s value is read via `getpass.getpass()`, never `argv`, never an environment
  variable - the one place this feature's own design has *no* residual equivalent to
  `KeychainBackend.put_secret`'s accepted `-w <value>` argv-exposure window (`PATTERNS.md`'s
  own FIX-FIRST 13 entry), because `age` offers a `stdin` path `security` does not (SC-008).
  `chmod 0600` on the temp file is a documented no-op on Windows (no POSIX mode bits there)
  and is wrapped so it cannot raise (FR-022). `scripts/check_env.py`'s `vault` row, for the
  `age` backend, checks *only* `shutil.which("age")` and `config.age_file.exists()` - it never
  calls `open_vault()`/`self_test()` and never decrypts, so `check_env` stays the prompt-free,
  few-second self-test it has always been; the two failure hints (`brew install age`,
  `python scripts/vault.py init`) name exactly which piece is missing, something a single
  collapsed boolean could not (D7, FR-014, FR-015).
- **Passphrase is the gate (v0.0.4, spec 004-age-vault).** The vault's passphrase prompt *is*
  the human-approval step the superseded GCP Secret Manager plus PAM plan would have provided
  from a cloud service - built instead from a property of the encryption tool itself, with no
  cloud account, no second approver, and no ongoing cost. `errand.py`'s existing pre-resolution
  loop (every plan source resolved before any browser window opens, in every mode) is
  unchanged in shape, but now touches `AgeBackend` whenever the default backend is active: any
  errand whose plan includes a `secret:` or `registry:` source prompts for the passphrase on
  *every* run, in *every* mode including `preview` and `--check`, not only `--apply` - and
  therefore needs a real controlling terminal in every one of those modes (FR-024). There is no
  saved passphrase, no cached unlock, and no flag that suppresses a required prompt: caching of
  any kind (an environment variable, a keychain item, a file, a CLI flag) was explicitly
  rejected, since it would defeat the per-run approval gate that is this feature's whole point.
  `probe.py`'s field plan is empty, so it never touches the vault and never prompts, in any
  mode - the one carve-out, unchanged from before this feature and proven again against the new
  default backend. No backend (`age`, Keychain, or GCP) is ever used to store a password or a
  payment card value - the profile registry holds only the identifiers an errand types into a
  form (name, address, date of birth, PAN, VIN, licence and policy numbers, and similar); a
  login persists through the v0.0.3 session-cookie mechanism instead, and any payment action
  stays human-only per `CLAUDE.md`'s existing "Terminal actions are human-only" rule (FR-023).
  This is recorded as permanent policy, not a temporary scope boundary: `vault.py set` does not
  validate or reject a value by shape (there is no passphrase-or-value strength policy of any
  kind, entirely the Director's own choice), so the safeguard is this stated policy plus the
  simple fact that every login this tool needs already has a better home than the vault.

## 2. Coding Standards

- `argparse` for every script; a module docstring that states the errand's background, the
  site, the handoff point, and the secrets it needs.
- Type hints and `from __future__ import annotations` throughout `headless/`.
- Tests under `tests/` with `pytest`; pure logic (mapping, gates, redaction, config parsing)
  is unit-tested without a browser. Browser paths are exercised by `--check`.

## 3. Tooling Conventions
  **Accepted residuals (2026-08-25, second review)**: (1) the snippet cap bounds output size only; text on the same line that no pattern matched (for example a 40-character AWS secret access key beside a detected token) is printed when it sits within the 200-character window, so review `--staged` output before pushing and rely on gitleaks in CI for keyword-context secrets. (2) `vendor/`, `node_modules/`, `site-packages/`, lockfiles, `*.min.js`, `*.map`, `*.svg` are skipped in every mode by design (performance and noise); gitleaks in CI is the only cover there. (3) `payment_card` requires a known issuer prefix (Visa, Mastercard, Amex, Discover, JCB, Diners) on top of Luhn, so a coincidentally Luhn-valid port or id list is not a finding; a card from an unlisted network would be missed.
- **Commit gate**: `python -m pytest -q` and `python scripts/verify_structure.py` both pass.
  Exception string (must appear verbatim in the commit message):
  `I understand the Headless validation gate is failing and I allow the exception to have the code committed to the repo`.
- **Hyphens only**: no em or en dashes in any file (global PreToolUse hook denies the write).
- **Version branches**: `vX.Y.Z` in a worktree under `../worktrees/Headless/`, `merge --no-ff`
  into `main`; `CHANGELOG` lives in the `Project_Structure.md` Changelog table.
- **Previews are disposable**: `previews/` is gitignored; delete freely.
- **Chrome profile-lock error text (v0.0.1, this machine, 2026-08-24)**: a second
  `launch_persistent_context` on a profile directory already held by another Chrome
  instance raises a Playwright `Error` whose message contains
  `Failed to create a ProcessSingleton for your profile directory` and
  `SingletonLock: File exists`. `headless/session.py` matches on these substrings to
  turn it into the "profile in use" `GateRefused` the edge cases call for, instead of a
  raw stack trace.
- **Benign Playwright sync-API teardown warning**: a clean `with sync_playwright() as p:`
  run (used by `headless/session.py` and `scripts/check_env.py`'s browser/playwright
  rows) can still print `Task was destroyed but it is pending!` /
  `TargetClosedError: Target page, context or browser has been closed` to stderr after
  the process's real work is done and the exit code is correct. This is a known
  cosmetic race in Playwright's sync wrapper, not a Headless bug; do not chase it.
- **`security add-generic-password` has no stdin path for a value (v0.0.1, FIX-FIRST 13)**:
  `-w <value>` is the only interface it offers, so during `KeychainBackend.put_secret`'s
  call the value is a real argv element of the child process, visible to local tools that
  can read another process's argv (`ps -ww`) for that brief window. Accepted for a
  single-user Mac Headless already trusts with the Keychain itself; the `profile` item is
  meant to be seeded by hand, not written by an unattended errand. A failed `security` call
  (non-zero exit) is never silently ignored: `put_secret`/`delete_secret` raise
  `RuntimeError(f"keychain write failed for item {name!r} (security exit {exc.returncode})")`
  from the caught `subprocess.CalledProcessError`, `from None` so the original (whose `.cmd`
  holds the raw value) is never chained onto the traceback.
- **`GcpBackend` detects `NotFound` by exception class name, not `isinstance`**: it never
  imports `google.api_core.exceptions` (that would defeat the lazy-import guarantee for a
  package that is deliberately not installed here). `get_secret`/`put_secret` check
  `type(exc).__name__ == "NotFound"` instead, which matches both the real SDK's exception
  (named `NotFound`) and a test double of the same name with no import required.
