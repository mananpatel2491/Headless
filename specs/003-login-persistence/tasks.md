---

description: "Task list for feature 003 Login Persistence"
---

# Tasks: Login Persistence

**Input**: Design documents from `/specs/003-login-persistence/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/session-state.md, quickstart.md

**Tests**: REQUIRED by the specification (SC-003, SC-004, SC-005, SC-006, SC-007). Test tasks are included and are written before the module code they cover.

**Organization**: Tasks are grouped by user story so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1..US3)
- Every task names its file path

## Path Conventions

Single project at the repository root: `headless/` (the package this feature changes),
`scripts/` (one existing maintenance script gains one launch-option change), `tests/` (pytest).
All paths below are relative to the worktree root `../worktrees/Headless/v0.0.3/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: the state file's name and path helper, in place before either the import or the
export function is written against them.

- [x] T001 [P] Update `.gitignore`: add `session-cookies.json` as a belt-and-braces entry (the
  profile directory it normally lives in is already excluded via `chrome-profile/`, but a
  `HEADLESS_PROFILE_DIR` pointed inside the repository should not risk this file specifically)
- [x] T002 Add `SESSION_COOKIE_FILENAME = "session-cookies.json"` and
  `_session_cookie_path(profile_dir: Path) -> Path` to `headless/session.py`, with a short
  comment pointing at `specs/003-login-persistence/data-model.md`; no wiring into
  `__enter__`/`__exit__` yet, so Foundational tests can import and call these directly

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the import and export functions themselves - parsing, masking-free note
construction, atomic write, mode `0600` - built and proven correct in isolation before either is
wired into the `Session` lifecycle. Tests first.

- [x] T003 [P] Write import tests in `tests/test_session.py`: state file absent -> zero calls to
  a fake context's `add_cookies`, nothing printed; state file present and valid -> `add_cookies`
  called once with the parsed entries; state file malformed (not valid JSON, or valid JSON that
  is not a list) -> exactly one `note: session cookies not restored (...)` line, zero calls to
  `add_cookies`; state file present but empty (zero bytes) -> the same one-line note (empty is a
  parse failure, not a special case); state file present at a permission mode looser than `0600`
  -> import still succeeds (research.md D6's "wrong mode" case: only export enforces the mode)
- [x] T004 [P] Write export tests in `tests/test_session.py`: a fake context's `cookies()`
  returning a mix of entries with `expires == -1` and entries with a real expiry -> only the
  `expires == -1` entries land in the written file; the write happens atomically (assert no
  half-written file is ever observable at the final path, e.g. by monkeypatching `os.replace` and
  checking it was called exactly once with a temp path and the final path); the resulting file
  exists at mode `0600` after both a first-time write and a write that replaces an existing file
  previously at a looser mode; a write failure (monkeypatch the write step to raise) -> exactly
  one `note: session cookies not saved (...)` line, and the exception never propagates out of the
  export call
- [x] T005 [P] Write `add_cookies`-failure and no-leak tests in `tests/test_session.py`: a fake
  context whose `add_cookies()` raises for the call as a whole -> exactly one note, zero cookies
  treated as imported (not a partial recovery); every test added across T003-T005 uses a
  distinctive synthetic cookie value (e.g. `sess=1` value shape, domain `example.com`, never a
  value shaped like a real secret) and asserts that value never appears in any `capsys`-captured
  stdout/stderr for that test (SC-005)
- [x] T006 Implement `_import_session_cookies(context, profile_dir: Path) -> None` in
  `headless/session.py`: resolve the path via `_session_cookie_path`, return immediately with no
  output if it does not exist, otherwise read and parse it as JSON and call
  `context.add_cookies(entries)` once; wrap the read-parse-add sequence in one `try`/`except
  Exception` that prints `note: session cookies not restored ({type(exc).__name__})` and never
  re-raises
- [x] T007 Implement `_export_session_cookies(context, profile_dir: Path) -> None` in
  `headless/session.py`: call `context.cookies()`, filter to entries where `expires == -1`, write
  the filtered list as JSON to a temporary file inside `profile_dir`, set its mode to `0600`,
  then atomically replace `_session_cookie_path(profile_dir)` with it; wrap the whole sequence in
  one `try`/`except Exception` that prints `note: session cookies not saved
  ({type(exc).__name__})` and never re-raises
- [x] T008 Run `python -m pytest -q tests/test_session.py -k cookie` and make T003-T005 green
  against the T006-T007 implementation (neither function is called from `__enter__`/`__exit__`
  yet, so these tests call them directly)

**Checkpoint**: the import/export mechanism is proven correct and fail-soft in isolation. Every
user story below only has to wire these two functions into the right two places, or prove a
property that already holds once they are wired in.

---

## Phase 3: User Story 1 - A seeded login persists to the next run (Priority: P1) 🎯 MVP

**Goal**: wire `_import_session_cookies`/`_export_session_cookies` into `Session.__enter__`/
`__exit__`, launched-profile path only; prove cross-run survival both with fakes and with a real
(local, fixture-page) browser.

**Independent Test**: quickstart Scenario 1 (hand-run UAT against a real site) and Scenario 5
(opt-in browser test).

- [x] T009 [P] [US1] Write a sequential-launch test in `tests/test_session.py`: using two fake
  context objects standing in for two successive launches against the same `tmp_path` profile
  directory (the second constructed only after the first's simulated `__exit__` has written the
  state file), prove that a session cookie the first context's `cookies()` reports at close is
  present in the arguments the second context's `add_cookies()` receives at the next open - this
  proves the wiring end to end, not just the two functions in isolation
- [x] T010 [US1] Wire `_import_session_cookies(self.context, self.config.profile_dir)` into
  `Session.__enter__`, launched-profile branch only, immediately after `self.page = ...` is
  assigned and before the `_should_hide_window` check
- [x] T011 [US1] Wire `_export_session_cookies(self.context, self.config.profile_dir)` into
  `Session.__exit__`, launched-profile branch only, immediately before `self.context.close()`
- [x] T012 [P] [US1] Add the opt-in real-browser test to `tests/test_gates_browser.py`, under the
  existing `HEADLESS_TEST_BROWSER=1` `pytestmark` guard: serve (or reuse) a small fixture page
  that sets a session cookie via `document.cookie` from `127.0.0.1` (a new fixture file plus a
  `127.0.0.1` `http.server` thread, or `context.add_cookies` with domain `127.0.0.1` against an
  existing fixture - either satisfies research.md D6, implementer's choice), open a `Session`,
  navigate to the page so the cookie gets set, close the `Session`, open a second `Session` on
  the same `tmp_path` profile directory, and assert the same cookie is present in
  `context.cookies()` before any navigation on the second launch
- [ ] T013 [US1] Run `python -m pytest -q tests/test_session.py -k cookie`, then
  `HEADLESS_TEST_BROWSER=1 python -m pytest -q tests/test_gates_browser.py -k persist`, then
  quickstart Scenario 1 by hand against a real site: seed a login with `--apply`, confirm the
  following preview run's `previews/*.json` `"title"` field and screenshot show the logged-in
  page. Automated parts DONE and green (`pytest -k cookie`: 13 passed; `HEADLESS_TEST_BROWSER=1
  pytest -k persist`: 1 passed). The hand-run part against a real site is (Director UAT, pending).

**Checkpoint**: MVP core delivered. A login seeded once now survives to the next run, proven both
mechanically and by hand against the exact defect the Director reported.

---

## Phase 4: User Story 2 - The apply window shows no sandbox warning (Priority: P2)

**Goal**: `chromium_sandbox=True` on every Chrome launch in the codebase.

**Independent Test**: quickstart Scenario 2 (hand-run) and Scenario 3 (unit-level).

- [x] T014 [P] [US2] Write a launch-kwargs test in `tests/test_session.py`: monkeypatch the
  `launch_persistent_context` call `Session.__enter__` makes (via the same seam existing tests
  already use to avoid a real browser launch) to capture its keyword arguments, construct and
  enter a launched-profile `Session`, and assert `chromium_sandbox is True` was passed
- [x] T015 [P] [US2] Write a matching launch-kwargs test in `tests/test_check_env.py`:
  monkeypatch the `chromium.launch` call `_check_browser()` makes, call
  `check_env._check_browser()`, and assert `chromium_sandbox is True` was passed
- [x] T016 [US2] Add `chromium_sandbox=True` to the `launch_persistent_context(...)` call in
  `headless/session.py`'s `Session.__enter__`
- [x] T017 [US2] Add `chromium_sandbox=True` to the `p.chromium.launch(channel="chrome",
  headless=True)` call in `scripts/check_env.py`'s `_check_browser()`
- [ ] T018 [US2] Run `python -m pytest -q tests/test_session.py -k sandbox` and
  `python -m pytest -q tests/test_check_env.py -k sandbox`, then quickstart Scenario 2 by hand:
  run a real `--apply`, confirm the "unsupported command-line flag" warning bar is gone at the
  "Your turn" prompt. Automated parts DONE and green (both `-k sandbox` runs: 1 passed each). The
  hand-run visual confirmation is (Director UAT, pending).

**Checkpoint**: independent of User Story 1 - both depend only on Phase 2 leaving
`Session.__enter__`/`__exit__`'s existing structure otherwise unchanged; neither story's tasks
touch the other's lines.

---

## Phase 5: User Story 3 - The persisted state file is safe (Priority: P1)

**Goal**: prove the safety properties end to end across everything Phases 2-4 already built:
mode `0600`, atomic replace, CDP-path exclusion, and that no cookie value ever reaches a printed
line anywhere this feature touches. The mechanism itself was already built in Phase 2; like spec
002's User Story 4 (allowlist), this phase is validation and coverage, not new production
behavior.

**Independent Test**: quickstart Scenario 4 (hand inspection) and Scenario 6 (unit-level
CDP-exclusion proof).

- [x] T019 [P] [US3] Write a CDP-attach exclusion test in `tests/test_session.py`: construct a
  `Session` on the CDP-attach path (`config.cdp_url` set, using a minimal CDP stub in the style
  of the existing `_StubContextForHiding` conventions), enter and exit it with
  `_import_session_cookies`/`_export_session_cookies` patched to raise if called, and assert
  neither was called and that no file was created under the stub's profile directory (FR-012,
  SC-006)
- [x] T020 [P] [US3] Write a consolidated no-leak test in `tests/test_session.py`: run every
  import/export scenario from Phase 2 and Phase 3 against one distinctive synthetic cookie value,
  and assert that value never appears in any `capsys`-captured stdout/stderr across the whole
  test module's run, as a single cross-cutting proof rather than only the per-test assertions
  T003-T005 already added (SC-005, NFR-001)
- [x] T021 [US3] Add a dedicated regression test in `tests/test_session.py`, if not already
  covered by T004/T007: a state file that existed before the run at a looser-than-`0600` mode is
  corrected to exactly `0600` by the next export, proving FR-005's "whether the file is being
  created or replaced" clause for the replace case specifically
- [ ] T022 [US3] Run quickstart Scenario 4 by hand: after a real Scenario 1 run, inspect
  `~/.headless/chrome-profile/session-cookies.json`'s permission bits (`ls -l`, expect
  `-rw-------`) and confirm every entry's `"expires"` field reads `-1`; run quickstart Scenario 6
  (`pytest -k cdp_cookie`) and confirm it passes. Automated part DONE and green (`pytest -k
  cdp_cookie`: 1 passed). The hand inspection of the real
  `~/.headless/chrome-profile/session-cookies.json` is (Director UAT, pending) - this builder run
  never touched `~/.headless/chrome-profile`, per the brief's hard constraint.

**Checkpoint**: every user story independently proven. The feature's safety claims (FR-005
through FR-012, NFR-001, NFR-002) are each backed by a passing test, not only by Phase 2's
happy-path coverage.

**Verifier-driven addition (Opus verifier, 2026-08-25, applied post-implementation, same
worktree)**: FIX-FIRST 1 - a failed import (state file existed but `context.add_cookies()`
rejected it, or the file was malformed) must not let `__exit__`'s unconditional export overwrite
the still-good file with an empty one; `_import_session_cookies` now returns a bool, stored on
`Session._cookie_import_ok`, and `__exit__` skips the export when it is `False`. FIX-FIRST 2 - a
failure between the temp write and the atomic replace left `session-cookies.json.tmp` behind,
un-gitignored; `_export_session_cookies` now unlinks the temp file best-effort on any failure, and
`.gitignore` covers the temp-file variant too. Five new tests added to `tests/test_session.py`
(import return-value contract, two full `Session.__enter__`/`__exit__` lifecycle tests proving the
original file survives a failed import, and a temp-file cleanup test). `research.md` D4,
`contracts/session-state.md`'s export table, `spec.md` FR-003 and FR-011, `Project_Structure.md`,
`PATTERNS.md`, and `scripts/check_env.py`'s sandbox-failure hint updated in the same pass. No new
task IDs; nothing above is re-ticked.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T023 [P] Update `CLAUDE.md`: one sentence in the Browser section and one in the Secrets
  section stating that the profile directory now also holds a plaintext session-cookie file
  (`session-cookies.json`) that stays vault-grade, per research.md D8
- [x] T024 Regenerate `.specify/memory/constitution.md` to **1.2.1** (PATCH: wording only - this
  feature extends the reach of the existing Browser and Secrets hard rules, it does not add a
  new one) with a Sync Impact Report line describing the change
- [x] T025 [P] Add two new entries to `PATTERNS.md`: "Session cookie persistence" (summarizing
  D1-D6: launched-profile-only scope, derived file location, import/export timing, fail-soft
  error handling, export cadence and the two accepted residuals) and "Chrome sandbox on"
  (summarizing D7: the Playwright default and the fix)
- [x] T026 [P] Update `README.md`: one sentence in Setup step 7 (a seeded login now persists
  across runs, not just for the session that seeded it) and one sentence in "Running an errand"
  (no sandbox warning bar at the apply handoff)
- [x] T027 Add the v0.0.3 Changelog row to `Project_Structure.md` listing every file touched
  (`headless/session.py`, `scripts/check_env.py`, `.gitignore`, `tests/test_session.py`,
  `tests/test_check_env.py`, `tests/test_gates_browser.py`, plus every docs-of-record file
  touched in this phase) - this table is also where the repository's version is recorded, since
  no separate `VERSION`, `pyproject.toml`, or `package.json` file exists anywhere in the tree
  (confirmed by a repository-wide search; research.md D8)
- [x] T028 [P] Update `MEMORY.md`: add the 2026-08-25 UAT result rows (check_env 5/5 PASS, plain
  preview correct, `probe --apply` correct through the handoff, the two defects found and their
  verified root causes) and the "Errands run" table entry for the `probe` run against
  progressive.com (site name only - no account details, no cookie names or values, matching the
  existing table's convention of never recording a real credential)
- [x] T029 Run the commit gate: `python -m pytest -q && python scripts/verify_structure.py &&
  git add -A && python scripts/scan_secrets.py --staged`

---

## Dependencies & Execution Order

- **Setup (Phase 1)** -> **Foundational (Phase 2)** -> user stories.
- **US1 (Phase 3)** depends only on Phase 2 (the import/export functions must exist before they
  can be wired in).
- **US2 (Phase 4)** depends only on Phase 2's `Session.__enter__` still having its existing
  structure to add one keyword argument to; independent of US1 - neither's tasks touch a line the
  other changes, which is why both land in the same MVP window without one waiting on the other.
- **US3 (Phase 5)** depends on Phase 2 (the mechanism it validates), Phase 3 (the wiring it
  proves is CDP-excluded correctly presupposes `__enter__`/`__exit__` already call the T006/T007
  functions), and, for full coverage, on US2 having landed too (T020's consolidated no-leak sweep
  is more useful once every note-producing and launch-kwargs path already exists) - practically
  last among the stories, mirroring spec 002's User Story 4 ordering.
- **Polish (Phase 6)** last.

### Parallel Opportunities

- T001, T002 do not conflict but T002 has no dependency on T001; both can start immediately.
- T003, T004, T005 together (same file, disjoint test functions, written before T006/T007 exist).
- T009 and T012 together (different files: `test_session.py` vs `test_gates_browser.py`).
- T014 and T015 together (different files: `test_session.py` vs `test_check_env.py`).
- T019 and T020 together (same file, disjoint test functions).
- T023, T025, T026, T028 together (four different docs-of-record files, no shared state).

## Implementation Strategy

MVP is Phases 1, 2, 3, and 4: with those, a seeded login survives to the next run and the apply
window shows no sandbox warning, independently of each other (Phase 3 and Phase 4 touch
disjoint parts of `Session.__enter__`). Phase 5 (User Story 3) is not deferred lower-priority
work despite landing last in execution order - it is validation of safety properties the spec
ranks at the same priority as persistence itself (both P1), sequenced last only because it needs
the mechanism and the wiring from every earlier phase to have something real to validate against,
the same reasoning spec 002 used for its own allowlist validation phase. Commit once at the end
of Phase 6 after the gate passes; the orchestrator (or an Opus verifier, per the global agent
conventions) reviews before the commit.
