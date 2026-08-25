# Research: Login Persistence

**Feature**: 003-login-persistence | **Date**: 2026-08-25

All Technical Context unknowns are resolved below. Each decision records the choice, the
verified evidence behind it, and the alternatives that were considered and rejected. D1-D7 mirror
the decisions the orchestrator made and fixed before this feature entered planning; they are not
re-opened here, only recorded with their evidence. D8 and D9 (tests, out of scope) are this
feature's own equivalents of spec 002's research.md D8 and D10.

## Root cause, verified before this feature was scoped

The orchestrator ran headless experiments on scratch Chrome profiles (this machine, Playwright
1.62, Chrome 151, `launch_persistent_context(..., channel="chrome")`) before any design decision
below was made:

- A cookie with an expiry survives a restart of the persistent context. A cookie with no expiry
  (a session cookie, which is what most logins actually set) is dropped on every restart.
- Seeding Chrome's `session.restore_on_startup = 1` ("continue where you left off") into
  `Default/Preferences` before the first launch does not change this under Playwright: the
  session cookies are still dropped, even though the preference itself survives.
- A Playwright `context.storage_state()` export taken at close, followed by
  `context.add_cookies(saved["cookies"])` after the next launch, does restore them: both a cookie
  set through `add_cookies` and one set by the page itself through `document.cookie` come back.
- The Director's own profile (`~/.headless/chrome-profile/Default/Cookies`) after the UAT run
  held 18 persistent tracking/CDN cookies for `.progressive.com` and zero cookies for any account
  host, consistent with the login's own cookies having been session cookies that Chrome purged on
  the next launch.

This is the evidence base for D1 through D6.

## D1. Scope: launched-profile path only

- **Decision**: persistence lives entirely in `headless/session.py`, on the launched-profile
  path (`launch_persistent_context`). The CDP-attach path (`HEADLESS_CDP_URL` set) gets no new
  behavior at all: it neither reads nor writes the state file.
- **Rationale**: the defect the Director hit only exists on the launched-profile path, because
  that is the only path where Headless owns the browser process's lifetime across restarts.
  Attaching over CDP means attaching to a Chrome the Director started and controls; that
  browser's session cookies are the Director's own Chrome's problem to keep or drop, and
  `PATTERNS.md`'s existing CDP-attach entry already establishes the boundary this decision
  extends: "attach only to a Chrome started for Headless - the attached context carries every
  session that browser holds." Reading or writing a state file for a browser process Headless
  does not own would be reaching into state that is not this feature's to manage.
- **Alternatives considered**: persisting cookies on the CDP-attach path too, for symmetry
  (rejected: the Director's own Chrome already persists its own sessions the normal way; adding
  a second, Headless-owned cookie jar on top of the Director's actual browsing session would be
  redundant at best and a source of stale-state confusion at worst - which cookie jar is
  authoritative would become an open question this feature has no reason to create).

## D2. State file location: derived, not configured

- **Decision**: `Path(config.profile_dir) / "session-cookies.json"`. No new environment
  variable, no new CLI flag. `.gitignore` gains `session-cookies.json` as a belt-and-braces
  entry for anyone who points `HEADLESS_PROFILE_DIR` inside the repository.
- **Rationale**: the profile directory is already outside the repository by default and already
  vault-grade (`CLAUDE.md`'s Secrets section); a file living inside it inherits that status for
  free. A new environment variable or flag would be a second place to configure something that
  has exactly one correct value for any given profile directory, and `Config`'s existing shape
  (`headless/config.py`) already has no field for a "session state path" - adding one would mean
  a second source of truth for where a profile's data lives, when `profile_dir` is already that
  source.
- **Alternatives considered**: a new `HEADLESS_SESSION_STATE_PATH` environment variable
  (rejected: nothing about this file's location should ever differ from its profile directory,
  so a configurable path would only ever be set to the one value it already resolves to, at the
  cost of one more thing to document and one more way to misconfigure it); storing the state
  file next to `previews/` instead of inside the profile directory (rejected: `previews/` is
  disposable output the Director is told he may delete freely at any time - `PATTERNS.md`'s
  "Previews are disposable" entry - which is exactly the wrong property for a file whose entire
  purpose is to survive between runs).

## D3. Import and export timing

- **Decision**: **Import** happens in `Session.__enter__`, on the launched-profile path only,
  immediately after a successful launch and before any navigation: if the state file exists,
  parse it and call `context.add_cookies(cookies)` with the parsed entries. **Export** happens in
  `Session.__exit__`, on the launched-profile path only, before `self.context.close()`: call
  `context.cookies()` and write only the entries whose `expires` value is `-1` (Playwright's
  marker for a session cookie) to the state file. The export replaces the previous file's
  contents entirely on every run (self-healing: a cookie the site cleared since the last export
  simply does not appear in the new file).
- **Rationale**: "before any navigation" matters because `goto()` is the first thing that could
  observe whether the login is already active; importing any later would mean the very first page
  load of a run could still see a logged-out state even when a valid session exists. "Before
  `context.close()`" on export matters for the same reason in reverse: exporting after close
  would be exporting from a context that may already be tearing down. Writing the whole file
  fresh on every export (rather than merging with what was already there) means the file can
  never drift from what the browser context actually held at its last clean close - there is no
  accumulation of stale entries to reason about.
- **Alternatives considered**: importing lazily, only if a plan actually needs a logged-in page
  (rejected: adds a conditional the errand-authoring contract has no way to express, and every
  errand that reads a page's content, not just ones with a field plan, benefits from starting
  logged in); merging the export with the file's previous content instead of replacing it
  outright (rejected: a merge would need its own reconciliation rule for a cookie the export run
  did not observe at all - was it cleared by the site, or just not touched by this particular
  page? - a replace-in-full export never has to answer that question, because the fresh
  `context.cookies()` call is always ground truth for what this context held at close).

## D4. Failure handling: fail soft, never print a value, one note per problem

- **Decision**: every failure mode collapses to the same shape: catch it, print exactly one
  `note: session cookies not restored (<reason class>)` (import side) or
  `note: session cookies not saved (<reason class>)` (export side) line, and continue the run.
  `<reason class>` is the caught exception's class name (`type(exc).__name__`), never its message
  and never any value it might carry. A **missing** state file is not a failure at all and prints
  nothing: it is the expected shape of a fresh or never-seeded profile. An **unreadable** file (an
  `OSError` opening it), a **malformed** file (invalid JSON, or valid JSON that is not the
  expected list-of-entries shape), and an **empty** file (zero bytes, which fails to parse as
  JSON the same way malformed content does) all resolve to the same import-side note. If
  `context.add_cookies()` itself raises when handed the parsed entries - the JSON parsed fine, but
  Playwright rejects one or more of the entries at add-time - the whole call is caught as one
  failure and produces the same single note, rather than retrying entry-by-entry; the run
  proceeds with zero cookies imported for that session, the same outcome as if the file had never
  existed. An export that fails to write (for example, an unwritable profile directory) produces
  the export-side note and the session still closes normally.
- **Rationale**: a persistence feature exists to make a run smoother, never to make it more
  fragile than a run without it; every failure path here must degrade to exactly the behavior
  Headless already had before this feature existed (logged out, but working). Collapsing
  `add_cookies` failures to the same single-note, zero-imported outcome as a malformed file
  (rather than attempting a partial per-entry recovery) is a deliberate simplification: the spec's
  language ("catch, print one note, continue") describes the fail-soft posture, not a requirement
  to salvage the entries that would have worked, and a partial recovery would need its own test
  matrix (which entries succeeded, in what order, does order matter) for a benefit - saving a
  session cookie or two out of a rejected batch - that has not been asked for. Never printing the
  exception's own message (only its class name) matters because a `KeyError` or `ValueError`
  raised while parsing untrusted JSON can embed a fragment of that JSON's content in its message;
  the class name alone is informative enough to debug from and carries no risk of surfacing a
  cookie value the same way `errand.py`'s existing post-session exception handling already treats
  an unclassified exception (class name only, never `str(exc)`, unless `HEADLESS_DEBUG=1`).
- **Alternatives considered**: printing the underlying exception's message for easier debugging
  (rejected: the whole point of FR-010/NFR-001 is that nothing about a cookie's content is ever
  in a printed line, and a parse-error message is exactly the kind of thing that can quote back a
  fragment of what it failed to parse); retrying an export once before giving up (rejected by
  NFR-002 and by `PATTERNS.md`'s own "Reads retry; writes never retry" convention, already
  established for `goto()` versus `fill()` - an export is a write); attempting a per-entry
  `add_cookies` call so only the genuinely bad entries are skipped (rejected above, kept as a
  documented simplification rather than a silent gap - see rationale).

## D5. Export cadence and accepted residuals

- **Decision**: export runs on every clean close, in every mode (preview, check, apply), exactly
  the way a real browser would save its state on exit. Two residuals are accepted, not solved by
  this feature:
  1. A site's bot defense that logs the profile out server-side because the headless
     preview/check user agent still identifies as `HeadlessChrome` on this machine (confirmed in
     `PATTERNS.md`'s "Quiet by default" entry) will cause that run's export to faithfully write
     whatever session cookies remain, which may be none. Recovery is the same `--apply` seed the
     Director already knows to run.
  2. Logins that live in `sessionStorage` rather than in a cookie (the India ITR e-filing
     portal's JWT is the known example in this repository's own `MEMORY.md`) are not covered by
     this feature at all; `context.cookies()` has no visibility into `sessionStorage`, and adding
     that would be a materially different mechanism.
- **Rationale**: exporting on every mode, not only apply, means a preview or check run that
  happens to observe a session cookie the Director logged in through some other run keeps that
  cookie current too - there is no reason a read-only run should let the state file go stale
  relative to what the browser context actually holds. Naming the two residuals explicitly, here
  and in the spec's Edge Cases and Out of Scope, means a future session does not rediscover either
  as a surprise bug report; both are already known limits of the cookie-based mechanism this
  feature deliberately chose (D1's evidence base), not gaps in how this feature implements that
  mechanism.
- **Alternatives considered**: exporting only on `--apply` runs, on the theory that only apply
  ever changes a login (rejected: a preview or check run can still observe a session cookie
  refreshed by the site itself, for example a sliding-expiry token reissued on any page load, and
  skipping the export there would silently let the state file fall behind); detecting and warning
  about a `sessionStorage`-only login (rejected as premature: no errand in this repository
  currently needs a `sessionStorage`-based login, and building detection for a case with no real
  caller yet would be speculative).

## D6. Tests

- **Decision**: existing `Session` tests that construct it with fake context/page objects
  (`tests/test_session.py`'s `_bare_session()` and its stub classes) must keep passing
  unmodified; nothing about this feature's wiring may require changing how those tests construct
  a `Session`. New unit tests, all using fake context objects (no real browser), cover: import
  when the state file is absent (silent, no note, zero cookies added); import when it is present
  and valid (the parsed entries are handed to `add_cookies`); import when it is malformed
  (one note, zero cookies added); import when the file's on-disk mode is looser than `0600`
  before the run (import still succeeds - only export enforces the mode, correcting it on the
  next write); export writes only the entries with `expires == -1`; export replaces the file
  atomically and leaves it at mode `0600`; the CDP-attach path never calls either function, in a
  test that asserts zero file operations happened; no test's captured output ever contains the
  cookie value each test's own fixture entries use. One opt-in browser test
  (`HEADLESS_TEST_BROWSER=1`, headless Chrome, no visible window, no request to a public network)
  proves a `document.cookie`-set session cookie survives a `Session` close and a fresh relaunch on
  the same profile directory; it uses a local fixture page served from `tests/fixtures/` (a
  `127.0.0.1` `http.server` thread, so `document.cookie` can set a cookie scoped to a real origin
  the way `file://` cannot) or, if that proves unnecessary, `add_cookies` with domain `127.0.0.1`
  against a locally served page - the implementation phase decides which is simpler once it is
  actually writing the test, per plan.md's Technical Context.
- **Rationale**: this is the same shape of proof `constitution.md`'s Principle IV already
  requires (pure logic unit-tested without a browser, the one live-behavior claim proven by an
  actual browser run) applied to a package feature that has no site or `--check` mode of its own,
  the same carve-out spec 002's research.md D8 already used for a maintenance script; here it is a
  `Session` capability instead of a scanner, but the shape - fake-object tests for every branch,
  one opt-in real-browser test for the one claim that cannot be faked - is identical.
- **Alternatives considered**: skipping the opt-in browser test and trusting the fake-object
  tests alone (rejected: every fake-object test can prove the code calls `add_cookies` with the
  right arguments, but none of them can prove Chrome actually restores the cookie the way the
  root-cause investigation found it does - that claim needs a real browser at least once);
  requiring a live login-protected site for the browser test (rejected: this repository has no
  such site under its own control, and using a real one would make the test flaky, slow, and a
  privacy risk the way `MEMORY.md`'s "Errands run" table already avoids by using `example.com` for
  its own browser-proof runs).

## D7. Chrome sandbox

- **Decision**: pass `chromium_sandbox=True` on every Chrome launch in the codebase: the
  launched-profile path in `headless/session.py` (`launch_persistent_context`) and
  `scripts/check_env.py`'s `_check_browser()` probe (`chromium.launch`). No flag exists, or may
  be added, to turn the sandbox back off.
- **Rationale**: verified by reading Playwright's own driver bundle
  (`coreBundle.js`, line 43075): `if (options.chromiumSandbox !== true) chromeArguments.push
  ("--no-sandbox")` - Playwright adds `--no-sandbox` to every Chromium launch unless this exact
  option is passed as `True`. This is the entire root cause of the warning bar the Director saw
  at the apply handoff; there is no other Chrome launch flag involved. Verified live on this
  machine: `launch_persistent_context(..., channel="chrome", headless=True,
  chromium_sandbox=True)` launches normally, and the resulting page reads back a correct title
  and user agent - passing the option introduces no new failure mode on this machine.
  `check_env.py`'s probe is included even though the Director never sees that launch, for the
  same reason `PATTERNS.md`'s existing "check_env's 'browser' row launches, briefly, headless"
  entry already gives for that probe existing at all: consistency between every place this
  codebase starts Chrome, so a future session auditing "does Headless ever pass `--no-sandbox`"
  gets one consistent answer instead of one exception to remember.
- **Alternatives considered**: leaving `check_env.py`'s probe unchanged, on the reasoning that its
  window is never visible and the warning bar is a cosmetic issue (rejected: the fix is one
  keyword argument, the two call sites are already inconsistent in every other respect they could
  be, and leaving one Chrome launch in the codebase still adding `--no-sandbox` would be a
  needless asterisk on "every Chrome launch passes chromium_sandbox=True" for no real saving);
  investigating whether the sandbox itself needs any other adjustment on this machine (out of
  scope - the verified fix is exactly one launch option, and nothing in the UAT report or the
  root-cause investigation pointed at any sandbox-related failure beyond the warning bar itself).

## D8. Docs of record

- **Decision**: this feature's implementation phase updates, in the same change (tasks.md's
  Polish phase, not this spec-only run): `CLAUDE.md`'s Browser and Secrets sections, one sentence
  each, stating that the profile directory holds a plaintext session-cookie file and stays
  vault-grade; `.specify/memory/constitution.md`, bumped to 1.2.1 (PATCH: wording only - this
  feature extends the reach of an already-stated hard rule, it does not add a new one);
  `PATTERNS.md`, two new entries ("Session cookie persistence", "Chrome sandbox on");
  `Project_Structure.md`, a v0.0.3 Changelog row (also where the repository's version is recorded
  - confirmed by grep across the tree that no separate `VERSION`, `pyproject.toml`, or
  `package.json` file exists); `README.md`, one sentence each in Setup step 7 and "Running an
  errand"; `MEMORY.md`, the 2026-08-25 UAT result rows (what passed, the two defects, the verified
  root causes) and the "Errands run" table entry for the `probe` run against progressive.com
  (site name only, no account details).
- **Rationale**: mirrors constitution Principle I (every file addition or material change logged
  in the same change) and spec 002's research.md D9, which set this same precedent for its own
  feature. A PATCH constitution bump (rather than MINOR) is correct here because this feature does
  not add a new hard rule the way spec 002's commit safety gate did - it extends the concrete
  behavior already promised by the existing Browser and Secrets hard rules ("the Director's daily
  Chrome profile is never used", "secrets and personal profile values never live in ... previews
  or logs") to one more file inside a directory those rules already govern, which the
  constitution's own Governance section treats as a wording-only change.
- **Alternatives considered**: a MINOR bump, on the reasoning that a new persisted file is a new
  fact about the system (rejected: the constitution's existing wording already fully covers a
  session-cookie file living in the vault-grade profile directory and never being printed; nothing
  in the Core Principles or Hard Rules needs new text to already be true of this feature, only
  clearer text describing what was already true).

## D9. Out of scope

- **Decision**: this feature does not touch the CDP-attach path (D1), does not add any new
  environment variable or CLI flag (D2), does not persist `sessionStorage`-based logins (D5), and
  does not encrypt the state file beyond the operating system's own file permission bits.
- **Rationale**: each of these was named explicitly in the brief this feature was scoped from,
  as a boundary already decided rather than a question this research phase needed to resolve.
  Encrypting the file specifically was considered and rejected because the profile directory
  already holds equivalent plaintext data (Chrome's own SQLite cookie database, at whatever
  permissions the operating system gives a user's own files) at the same level of protection;
  this feature does not need to raise the bar beyond matching what is already true of the rest of
  the profile directory it lives inside.
- **Alternatives considered**: encrypting the state file with a key derived from the macOS
  Keychain (rejected: `headless/secrets.py`'s Keychain backend already exists for exactly this
  kind of local-secret storage, but introducing it here would mean every read of the state file
  now depends on the vault being reachable, turning a fail-soft convenience feature into one more
  thing that can go wrong before a run can even start - disproportionate to the actual threat
  model of a single-user local machine).
