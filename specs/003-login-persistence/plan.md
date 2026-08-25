# Implementation Plan: Login Persistence

**Branch**: `v0.0.3` | **Date**: 2026-08-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-login-persistence/spec.md`

## Summary

Fix the two defects the Director found in UAT of v0.0.1: a seeded login does not survive to the
next run, and the apply window shows Chrome's `--no-sandbox` warning bar. Both live entirely in
`headless/session.py` (plus one matching launch-option change in `scripts/check_env.py`'s browser
probe). Persistence is added on the launched-profile path only: `Session.__enter__` imports
previously exported session cookies before any navigation, and `Session.__exit__` exports the
context's current session cookies (only the entries with no expiry) before closing, writing
`<profile_dir>/session-cookies.json` atomically at file mode `0600`. The CDP-attach path is
untouched by design (D1). The sandbox fix is one launch-option change, `chromium_sandbox=True`,
applied everywhere the codebase launches Chrome. Decisions are recorded in
[research.md](research.md).

## Technical Context

**Language/Version**: Python 3.14 (venv per worktree, same as the rest of the repository)

**Primary Dependencies**: none new. Both fixes use Playwright APIs already available in the
pinned version (1.62, per `MEMORY.md`): `context.cookies()`, `context.add_cookies()`, and the
`chromium_sandbox` launch option on `launch_persistent_context`/`chromium.launch`. The state
file is read and written with the standard library only (`json`, `os.replace` for the atomic
rename, `os.open`/`os.chmod` for the `0600` mode).

**Storage**: one new persisted artifact, `<profile_dir>/session-cookies.json`, a plain JSON file
holding only the session-cookie subset of what `context.cookies()` returns. Not a database, not
versioned, replaced whole on every export. `profile_dir` is already outside the repository and
already documented as vault-grade local data (`CLAUDE.md`'s Secrets section); this file inherits
that status rather than introducing a new one.

**Testing**: `pytest>=8` (already a dependency). All new logic-level tests use fake context
objects (no browser), matching the existing convention in `tests/test_session.py`
(`_bare_session()`, stub pages). One new opt-in browser test is added to
`tests/test_gates_browser.py` (`HEADLESS_TEST_BROWSER=1`), proving a `document.cookie` session
cookie set on a local fixture page survives a `Session` close and relaunch; it uses headless
Chrome, no visible window, and no request to any host outside `127.0.0.1`/`file://`.

**Target Platform**: same as the rest of `headless/`: the Director's macOS machine for the
launched-profile path (Chrome 151, channel `chrome`); nothing in this feature is macOS-specific
beyond what `session.py` already assumes.

**Project Type**: package change (no new script, no new errand). Single project, same as v0.0.1
and v0.0.2.

**Performance Goals**: the import/export pair adds no perceptible latency to a run (SC-003: the
unit suite covering both stays under 1 second, no browser); the real-world cost is one
`context.cookies()` call and one small JSON write per run, both far below anything a Director
would notice next to the browser launch itself.

**Constraints**: no new environment variable, no new CLI flag (spec FR-002); the CDP-attach path
must never read or write the state file (FR-012); no cookie name or value may ever appear in any
printed note, exception message, or preview artifact (FR-010, NFR-001); the export never retries
(NFR-002); the state file must exist at mode `0600` and be written atomically (FR-005); existing
`Session` tests that construct it with fakes must keep passing unmodified.

**Scale/Scope**: one file materially changed (`headless/session.py`: import/export functions,
their wiring into `__enter__`/`__exit__`, the `chromium_sandbox=True` launch option), one small
matching change (`scripts/check_env.py`'s `_check_browser()`), one `.gitignore` line, new tests
in `tests/test_session.py` and `tests/test_gates_browser.py`, plus the docs-of-record updates
listed in Project Structure below. No new errand, no new cloud resource, no change to
`headless/config.py`'s `Config` shape (the state file's path is derived from the existing
`profile_dir` field, not a new one).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / rule | Status | Evidence |
| :--- | :--- | :--- |
| I. Context-First Architecture Map | PASS | `Project_Structure.md` gains a v0.0.3 Changelog row naming every file touched, in the implementation commit (a tasks.md Polish task, not done in this spec-only run). |
| II. Pattern Reference Integrity | PASS | `PATTERNS.md` gains two entries at implementation time: "Session cookie persistence" and "Chrome sandbox on" (tasks.md Polish phase); this plan does not pre-empt their wording. |
| III. Automated Maintenance via Agentic Skills | N/A | This feature changes package code (`headless/session.py`) and one existing maintenance script's browser probe; it adds no new `scripts/` entry point. |
| IV. Continuous Errand Validation | PASS | Pure logic (state-file parsing, masking-free note construction, atomic write, mode enforcement) gets unit tests with fake context objects, matching the pattern `tests/test_session.py` already uses. There is no new site and no new `--check` mode to add; the live-behavior proof is the opt-in browser test (`HEADLESS_TEST_BROWSER=1`), the same carve-out `research.md` D6 in spec 002 already used for a maintenance script with no site of its own, here applied to a package feature with no site of its own either. |
| V. IaC and Cost Gating | N/A | No cloud resource. |
| Gates hard rule (preview/apply/check, no submit) | PASS, unaffected | No new mode, no new flag, no path toward a submit/pay/verify/otp concept. Export runs identically in preview, check, and apply, which is a statement about *when* it runs, not a new gate. |
| Secrets hard rule | PASS, directly extended | The state file holds the same class of data (typed/session values) `CLAUDE.md`'s Secrets section already governs for `previews/` and the profile directory; this feature extends the existing vault-grade classification to one more file inside a directory that already carries it, and never prints a value (FR-010, NFR-001), matching `redact()`'s existing convention in `headless/fields.py`. |
| Browser hard rule | PASS, directly extended | "Attach only to a Chrome started for Headless" and "the Director's daily Chrome profile is never used" already draw the exact boundary this feature respects: the CDP-attach path (the Director's own browser, when used) is explicitly untouched (FR-012, D1). `CLAUDE.md`'s Browser and Secrets sections each gain one sentence recording this (tasks.md Polish phase). |
| Spec-driven workflow | PASS | This feature runs specify -> plan -> tasks on `v0.0.3` in this worktree, per the mananUtils worktree protocol; implementation is a later run, not part of this spec-only delivery. |

No violations; Complexity Tracking is empty.

**Post-design re-check (after Phase 1)**: the data model (`SessionCookieState`,
`SessionCookieEntry`) and the one new contract (`contracts/session-state.md`) introduce no
runtime dependency and no abstraction beyond the two functions named in the Technical Context
(`_import_session_cookies`, `_export_session_cookies`) plus one launch-option change. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/003-login-persistence/
├── spec.md
├── plan.md                    # This file
├── research.md                # Phase 0: decisions D1-D9
├── data-model.md              # Phase 1: SessionCookieState, SessionCookieEntry, state transitions
├── quickstart.md              # Phase 1: the Director's re-UAT script
├── contracts/
│   └── session-state.md       # the state file contract, the Session behavior contract, the sandbox launch contract
├── checklists/
│   └── requirements.md
└── tasks.md                   # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
headless/
└── session.py            # updated: SESSION_COOKIE_FILENAME, _session_cookie_path,
                           # _import_session_cookies, _export_session_cookies, wired into
                           # __enter__/__exit__ on the launched path only; chromium_sandbox=True
                           # added to the launch_persistent_context call

scripts/
└── check_env.py           # updated: _check_browser()'s launch() call gains chromium_sandbox=True

.gitignore                 # updated: session-cookies.json added as a belt-and-braces entry

tests/
├── test_session.py        # updated: import/export unit tests against fake context objects,
│                           #   note-line coverage, atomic-write/mode-0600 proof, CDP-path
│                           #   exclusion, chromium_sandbox launch-kwargs assertion
├── test_check_env.py       # updated: chromium_sandbox assertion on the browser row's launch call
└── test_gates_browser.py  # updated: one opt-in real-browser test proving cross-relaunch survival

CLAUDE.md                   # updated: one sentence each in Browser and Secrets (tasks.md Polish)
.specify/memory/constitution.md   # updated: 1.2.0 -> 1.2.1 (PATCH: wording only, no new hard rule
                                   # beyond what CLAUDE.md's existing Browser/Secrets rules already
                                   # cover)
PATTERNS.md                 # updated: two new entries (Session cookie persistence; Chrome sandbox on)
README.md                   # updated: Setup step 7 and "Running an errand" gain one sentence on persistence
Project_Structure.md        # updated: v0.0.3 Changelog row (this is also where the repository's
                             # version is recorded; there is no separate VERSION file, confirmed by
                             # grep across the tree)
MEMORY.md                   # updated: the 2026-08-25 UAT result rows and the probe/progressive.com
                             # errand-run row

headless/config.py          # UNCHANGED - the state file's path is derived from the existing
                             # profile_dir field, not a new Config field (spec FR-002)
headless/errand.py           # UNCHANGED - the run state machine does not change; import/export are
                              # entirely inside Session's own __enter__/__exit__
headless/gates.py            # UNCHANGED - no new mode, no new flag
requirements.txt             # UNCHANGED - no new dependency
terraform/README.md          # UNCHANGED - no new cloud resource
Function_Mapping.md          # UNCHANGED - this feature touches no errand's field mapping
```

**Structure Decision**: single project, same as v0.0.1 and v0.0.2. Both fixes land inside
`headless/session.py`, the module that already owns the launched-profile Chrome lifecycle
(`PATTERNS.md`'s "Persistent Chrome profile" and "Quiet by default" entries); there is no reason
to introduce a new module for two additions to an existing lifecycle a single class already
manages. The one other file touched, `scripts/check_env.py`, changes only its existing
`_check_browser()` launch call for consistency with the same launch option, not for any new
responsibility.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

None.
