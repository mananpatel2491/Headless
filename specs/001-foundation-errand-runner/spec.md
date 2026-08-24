# Feature Specification: Foundation Errand Runner

**Feature Branch**: `v0.0.1` (spec directory `001-foundation-errand-runner`)

**Created**: 2026-08-24

**Status**: Draft

**Input**: User description: "Foundation: headed persistent Chrome session, secrets backend seam, profile registry, preview/apply/check gates, redacted preview artifacts, check_env and probe errands"

## Why

Headless exists to run errands on websites for one person, the Director, using accounts and
personal data that must never leak. Before any real errand (ITR portal walk, ticket search,
insurance quotes) can be written, the repo needs the small set of shared mechanics every
errand composes: a browser the Director has logged into that stays logged in, a place to
keep secrets that is not the repo, a registry of the only values a script may type, the
three run modes that make a script safe by default, and preview artifacts that show what a
script would do without exposing what it knows. This feature delivers those mechanics plus
two errands that prove them: an environment self-test and a URL probe.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stay logged in between runs (Priority: P1)

The Director runs the probe errand against a site, sees a Chrome window open (not hidden),
logs in by hand once, and closes the run. On the next run against the same site the page
opens already logged in. Every run leaves a preview artifact (a screenshot and a small JSON
record) the Director can open afterwards.

**Why this priority**: Login and two-factor steps are where browser automation fails most.
Persisting a hand-seeded session removes that failure class for every later errand. Without
it, no real errand can be built.

**Independent Test**: Run `probe` twice against a site that requires login, logging in by
hand during the first run only. The second run shows the logged-in page. The preview folder
holds two screenshot and JSON pairs.

**Acceptance Scenarios**:

1. **Given** no Headless profile directory exists, **When** the Director runs `probe` with a
   URL, **Then** the profile directory is created, a visible Chrome window opens on that URL,
   and a preview artifact is written.
2. **Given** the Director logged in during a previous run, **When** `probe` runs again on the
   same site, **Then** the page opens in the logged-in state with no credential entry.
3. **Given** the Director's everyday Chrome is open, **When** Headless runs, **Then** the
   everyday browser and its profile are untouched.

---

### User Story 2 - Secrets and personal values never leave the vault (Priority: P1)

The Director stores a secret (for example a portal password) and the profile document
(name, addresses, identifiers) in the system vault. An errand fetches a value only at the
moment it fills a field. Nothing the script prints, logs, or writes to a preview contains the
value; the preview shows the field name and a masked form only.

**Why this priority**: The tool operates with the Director's real identity. A single leak
into a log, a commit, or an artifact outweighs any convenience the tool provides.

**Independent Test**: Store a known test secret and a test profile in the vault, run an
errand that fetches both and writes a preview, then search every output (stdout, preview
files) for the raw values. None is found; masked forms are present.

**Acceptance Scenarios**:

1. **Given** a secret exists in the vault, **When** an errand needs it, **Then** the errand
   receives it at fill-time and the value never appears in stdout, logs, or preview files.
2. **Given** a required secret is missing, **When** an errand starts, **Then** it stops
   before opening any site, names the missing item, and performs no partial fill.
3. **Given** the vault backend is set to the cloud option but not configured, **When** any
   errand starts, **Then** it fails at startup naming the missing configuration, before any
   browser launches.
4. **Given** a value is not in the profile registry, **When** a script tries to type it,
   **Then** the attempt is refused and reported; the registry is the only source of typed
   values.

---

### User Story 3 - Safe by default, human at the end (Priority: P1)

The Director runs any errand with no flags and gets a preview: nothing on the site changes,
and the preview shows every field the script would fill. With `--apply` the script fills
those fields and navigates up to the errand's declared handoff point, then leaves the window
open and tells the Director "Your turn". With `--check` the script only proves that the
page elements it depends on still exist. No mode submits, pays, verifies, or handles a
one-time code.

**Why this priority**: These three modes are the safety model of the whole tool. Every later
errand inherits them, so they must exist and be tested before the first real errand.

**Independent Test**: Using a local fixture page with a form and a submit control, run a
fixture errand in each mode. Preview leaves the form empty; apply fills the mapped fields
and stops with the submit control untouched; check reports each element as found or missing.

**Acceptance Scenarios**:

1. **Given** an errand and no flags, **When** it runs, **Then** no field on the site is
   changed and a preview artifact lists every planned field with masked values.
2. **Given** `--apply` in an interactive terminal, **When** the errand runs, **Then** the
   mapped fields are filled, the script stops at the declared handoff, prints "Your turn",
   and keeps the window open until the Director confirms.
3. **Given** `--apply` from a non-interactive terminal, **When** the errand starts, **Then**
   it refuses to run, because no human is present for the handoff.
4. **Given** `--check`, **When** the errand runs, **Then** every element it depends on is
   reported as found or missing and nothing is typed.
5. **Given** any errand, **When** its options are listed, **Then** no submit, pay, verify,
   or code-entry option exists.

---

### User Story 4 - Know the environment is ready (Priority: P2)

The Director runs the environment self-test and gets a short pass/fail table: browser
installed, profile directory usable, vault reachable, automation runtime present. Each
failure says what to do.

**Why this priority**: Saves a debugging session on every new machine or after an OS
update, but no real errand depends on it.

**Independent Test**: Run `check_env` on a configured machine and see all rows pass; rename
the profile directory read-only and see that row fail with an instruction.

**Acceptance Scenarios**:

1. **Given** a configured machine, **When** `check_env` runs, **Then** every row passes and
   the exit status is success.
2. **Given** the vault is unreachable, **When** `check_env` runs, **Then** that row fails,
   names the backend, and the exit status is failure.

---

### Edge Cases

- The profile directory is already in use by another Headless run: the browser refuses the
  lock; the script reports "profile in use" instead of a raw stack trace.
- Chrome is not installed: the session reports the missing browser with the install step.
- The profile directory path contains `~`: it is expanded to the home directory.
- Headless (invisible) mode is requested together with `--apply`: refused, because the
  handoff requires a visible window.
- The preview directory does not exist: it is created on first write.
- A registry lookup uses a dotted path that does not exist: refused with the path named.
- The Director closes the browser window during the handoff wait: the script ends cleanly
  and reports that the window was closed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The runner MUST open a visible browser window on a persistent Headless-only
  profile stored outside the repository at a configurable location, creating it when absent.
- **FR-002**: The runner MUST be able to attach to an already-running browser when a
  debugging endpoint is configured, instead of launching one.
- **FR-003**: The runner MUST fetch secrets from a vault backend at fill-time through one
  interface, with the operating-system keychain as the default backend and Google Cloud
  Secret Manager as a selectable backend.
- **FR-004**: The runner MUST stop before opening any site when a required secret is
  missing, and MUST fail at startup, before any browser launch, when the selected backend is
  not configured.
- **FR-005**: The profile registry MUST be loaded from the vault as one document and MUST be
  the only source of values a script can type; lookups use dotted paths and missing paths
  are refused.
- **FR-006**: Every errand MUST support three modes: preview (default, no site writes),
  apply (fills up to a declared handoff point), and check (read-only element probe).
- **FR-007**: No errand and no shared helper MAY offer a submit, pay, verify, or one-time-code
  step; apply MUST stop at the handoff, print "Your turn", and keep the window open until the
  Director confirms.
- **FR-008**: Apply mode MUST refuse to start from a non-interactive terminal and MUST refuse
  to run in invisible (headless) browser mode.
- **FR-009**: Every run MUST write a preview artifact consisting of a screenshot and a JSON
  record (errand, mode, address, timestamp, planned fields) where every value has passed
  through a redaction step: secrets and registry values are masked to their last two
  characters.
- **FR-010**: No secret or registry value MAY appear in stdout, logs, or preview files.
- **FR-011**: The `check_env` errand MUST report, per component (browser, profile directory,
  vault backend, automation runtime), pass or fail with a remediation hint, and MUST exit
  non-zero on any failure.
- **FR-012**: The `probe` errand MUST open a given address in the Headless profile, write a
  preview artifact, and print the page title; it MUST run visible by default.
- **FR-013**: Non-secret configuration MUST come from environment variables (optionally via
  a `.env` file) with command-line overrides; documentation MUST state that `.env` never
  holds secrets.
- **FR-014**: Pure logic (configuration, mode resolution, refusals, redaction, registry
  lookup) MUST be covered by automated tests that run without a browser.
- **FR-015**: Every errand script MUST declare its handoff point as a named constant and MUST
  be listed in the errand map and the scripts inventory in the same change.

### Key Entities

- **Errand**: one runnable script for one task on one or more sites; declares a handoff
  point and a field mapping; runs in exactly one mode per invocation.
- **Session**: the visible browser on the Headless profile (launched or attached); owns
  page navigation and element probing; never retries writes.
- **Vault (secrets backend)**: where secrets and the profile document live; keychain or
  cloud; addressed by item name.
- **Profile registry**: the vault document of typeable personal values; dotted-path lookup;
  the only writable source.
- **Mode**: preview, apply, or check; resolved from flags and the terminal state; apply
  requires a human.
- **Preview artifact**: screenshot plus JSON record of one run, written after redaction.
- **Handoff**: the declared step after which only the Director acts; the script waits, the
  window stays open.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a login-protected site, the second `probe` run opens in the logged-in state
  with zero credential entries, after one hand login in the first run.
- **SC-002**: Across the full automated test run, zero occurrences of any test secret or
  registry value in stdout or in preview files (asserted by search).
- **SC-003**: On the fixture form, preview mode changes 0 fields in 100% of runs; apply mode
  fills 100% of mapped fields and leaves the submit control untouched; check mode reports
  100% of dependent elements with a found or missing status.
- **SC-004**: `check_env` finishes in under 30 seconds and, when a component is broken, the
  failing row names that component and a remediation step.
- **SC-005**: The browser-free test suite completes in under 10 seconds and the commit gate
  (tests plus structure check) passes on the feature branch.
- **SC-006**: Selecting the cloud vault without configuration fails in under 2 seconds with
  the missing setting named and no browser window opened.

## Assumptions

- The Director works on macOS with Google Chrome installed; other platforms are out of
  scope for this feature.
- The Director is present at the terminal during `--apply` runs; unattended apply is out of
  scope by design.
- The cloud vault backend is implemented and unit-tested with a fake client in this feature;
  activating it needs the cloud SDK and an interactive login, which is a later step tracked
  in `MEMORY.md` and `terraform/README.md`.
- Gate behaviour is tested against a local fixture page shipped with the tests, not a live
  third-party site.
- Real errands (ITR portal, tickets, insurance, work portals) are separate features; this
  feature ships only `check_env` and `probe`.
- The mananUtils worktree protocol and the repo's constitution (`CLAUDE.md`) apply; the
  feature branch is `v0.0.1`.
