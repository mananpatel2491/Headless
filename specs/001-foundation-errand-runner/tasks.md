---

description: "Task list for feature 001 Foundation Errand Runner"
---

# Tasks: Foundation Errand Runner

**Input**: Design documents from `/specs/001-foundation-errand-runner/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli-and-package.md, quickstart.md

**Tests**: REQUIRED by the specification (FR-014, SC-002, SC-003, SC-005). Test tasks are included and are written before the module they cover.

**Organization**: Tasks are grouped by user story so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1..US4)
- Every task names its file path

## Path Conventions

Single project at the repository root: `headless/` (package), `scripts/` (errands), `tests/` (pytest). All paths below are relative to the worktree root `../worktrees/Headless/v0.0.1/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton, optional GCP extra, test scaffolding

- [ ] T001 Create `headless/__init__.py` with the package docstring and `__version__ = "0.0.1"`
- [ ] T002 [P] Create `requirements-gcp.txt` containing `google-cloud-secret-manager>=2.20` (optional extra; not in `requirements.txt`)
- [ ] T003 [P] Create `tests/conftest.py` with `FakeVault` (in-memory `VaultBackend`), a `tmp_preview_dir` fixture, and a `fixture_form_url` fixture returning the `file://` URL of `tests/fixtures/form.html`
- [ ] T004 [P] Create `tests/fixtures/form.html`: text inputs `#full_name`, `#pan`, `#email`, a `<select id="form_type">` with options `ITR-1`/`ITR-2`, a checkbox `#agree`, a submit `<button id="submit">` whose click handler sets `#clicks` (hidden) to `"submitted"`, and no element matching `#does-not-exist`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config, gates, fields, and preview record: every story depends on these. Tests first.

- [ ] T005 [P] Write `tests/test_config.py`: defaults; `~` expansion of `HEADLESS_PROFILE_DIR`; CLI overrides win over env; `HEADLESS_SECRETS_BACKEND=gcp` without `HEADLESS_GCP_PROJECT` raises `ConfigError` naming the setting; unknown backend raises `ConfigError`
- [ ] T006 [P] Write `tests/test_gates.py`: `resolve_mode` table from data-model.md (preview default, check, apply with tty+headed, refusals for no-tty and headless); `add_mode_arguments` makes `--apply --check` an argparse error; parser rejects `--submit`, `--pay`, `--verify`, `--otp`, `--yes`, `--confirm`
- [ ] T007 [P] Write `tests/test_fields.py`: `parse_source` for `registry:`, `secret:`, `literal:` and rejection of anything else; `redact("hunter2-XY") == "****XY"`, `redact("ab") == "****"`, `redact("") == "****"`
- [ ] T008 [P] Write `tests/test_preview.py`: a `PreviewRecord` built from registry and secret sources holds only masked values (search the JSON dump for the raw value, assert absent); literal values pass through; `write_artifacts` names files `<errand>-<YYYYMMDDTHHMMSSZ>.png/.json` under the preview dir and creates the dir
- [ ] T009 Implement `headless/config.py`: `ConfigError`, frozen `Config`, `load_config(overrides=None)` reading `.env` via `python-dotenv` from the repo root then environment, applying overrides, expanding `~`, validating backend and `gcp_project` (data-model.md "Config")
- [ ] T010 Implement `headless/gates.py`: `Mode` enum (three values only), `GateRefused`, `add_mode_arguments(parser)` (mutually exclusive `--apply`/`--check`, plus `--profile-dir`, `--headless`, `--preview-dir`), `resolve_mode(args, *, isatty, headed)` per the table
- [ ] T011 Implement `headless/fields.py`: `Source` (kind + ref), `parse_source`, frozen `FieldPlan(name, selector, source, kind="fill")`, `redact`
- [ ] T012 Implement `headless/preview.py`: `PreviewRecord` (masks registry/secret values in `__post_init__`, keeps literals), `to_json()`, `write_artifacts(record, screenshot_png, preview_dir) -> (png_path, json_path)` using a UTC timestamp
- [ ] T013 Run `python -m pytest -q tests/test_config.py tests/test_gates.py tests/test_fields.py tests/test_preview.py` and make them pass

**Checkpoint**: Foundation ready; secrets, session, errand base, and scripts can proceed

---

## Phase 3: User Story 2 - Secrets and personal values never leave the vault (Priority: P1)

**Goal**: vault seam with Keychain and GCP backends; profile registry as the only typeable source

**Independent Test**: quickstart Scenario 3 (unit tests with `FakeVault`; optional live Keychain round-trip)

- [ ] T014 [P] [US2] Write `tests/test_secrets.py`: `FakeVault` get/put/delete/self_test; `SecretMissing` names the item; `KeychainBackend` builds the exact `security` argv for add/find/delete (subprocess patched) and maps a non-zero find to `SecretMissing`; `GcpBackend(project, client=fake)` reads `projects/<p>/secrets/<name>/versions/latest` and maps NotFound to `SecretMissing`; `open_vault(config)` picks the backend and, for `gcp`, imports lazily (test asserts no import of `google.cloud` when backend is keychain)
- [ ] T015 [P] [US2] Write `tests/test_profile.py`: `ProfileRegistry.load(FakeVault)` parses the `profile` JSON; `get("identity.pan")` returns the scalar; nested dict result is refused; missing path raises `RegistryMissing(path)`; malformed JSON raises a clear error
- [ ] T016 [US2] Implement `headless/secrets.py`: `SecretMissing`, `VaultBackend` Protocol (`get_secret`, `put_secret`, `delete_secret`, `self_test`), `KeychainBackend(account)` via `subprocess.run(["security", ...])` with `-w` for values (never echo values), `GcpBackend(project, client=None)` with lazy `from google.cloud import secretmanager`, `open_vault(config)`
- [ ] T017 [US2] Implement `headless/profile.py`: `RegistryMissing`, `ProfileRegistry.load(vault, item="profile")`, `get(dotted)` with scalar check
- [ ] T018 [US2] Run `python -m pytest -q tests/test_secrets.py tests/test_profile.py` and make them pass; then a live Keychain round-trip: `python -c` that puts, gets, and deletes `headless-selftest` through `KeychainBackend("headless")` and prints only `OK`

**Checkpoint**: secrets and registry proven without a browser

---

## Phase 4: User Story 3 - Safe by default, human at the end (Priority: P1)

**Goal**: `Session` and the `Errand` base class implementing the preview/check/apply state machine with handoff

**Independent Test**: quickstart Scenario 4 (`tests/test_gates.py` refusals plus `tests/test_gates_browser.py` on the fixture form)

- [ ] T019 [P] [US3] Write `tests/test_errand.py`: with a stubbed `Session` (records calls), `Errand.run([])` produces a preview record with the planned fields and no `fill` calls; `run(["--check"])` calls `probe` with `dependencies` and no `fill`; `run(["--apply"])` with `isatty=True, headed=True` fills each plan in order then calls `handoff(HANDOFF)`; apply refuses (exit 1, no session opened) when a `secret:` item is missing or a `registry:` path is missing; exit codes per contract
- [ ] T020 [P] [US3] Write `tests/test_gates_browser.py` (skipped unless `HEADLESS_TEST_BROWSER=1`): a `FixtureErrand` mapping `#full_name <- registry:identity.full_name`, `#pan <- registry:identity.pan`, `#email <- secret:test-email`, `#form_type <- literal:ITR-2` (kind select), dependencies including `#does-not-exist`; preview leaves all inputs empty; check reports `#does-not-exist` missing and the rest found; apply (confirm stubbed, `allow_headless_apply_for_tests=True`, temp profile dir) fills the four fields and `#clicks` stays empty; the JSON artifact contains no raw registry or secret value
- [ ] T021 [US3] Implement `headless/session.py`: `Session(config, mode, *, confirm=input, allow_headless_apply_for_tests=False)`; context manager launching `launch_persistent_context(profile_dir, channel="chrome", headless=not headed)` or `connect_over_cdp(cdp_url)`; `goto(url)` with one retry on `playwright.sync_api.Error` for navigation; `probe(selectors) -> list[(selector, found)]` using `page.locator(sel).count() > 0`; `fill(plan, vault, registry)` refusing unless `mode is APPLY`, resolving the source at call time, dispatching on `kind` (`fill` / `select_option` / `check`); `screenshot() -> bytes`; `handoff(text)` printing `Your turn: <text>` then `confirm()` and returning whether the page is still open; a "profile in use" message when Chrome reports the lock
- [ ] T022 [US3] Implement `headless/errand.py`: `Errand` base (`name`, `HANDOFF`, `dependencies`, `plan(registry)`, `add_arguments(parser)` hook, `run(argv=None) -> int`) executing: `load_config` -> `resolve_mode` -> (apply) pre-resolve every plan source so missing items fail before any window -> `Session` -> `goto` -> mode branch -> `PreviewRecord` + `write_artifacts` -> final stdout line per contract -> exit code; catches `ConfigError`, `GateRefused`, `SecretMissing`, `RegistryMissing` as exit 1 and Playwright errors after launch as exit 2
- [ ] T023 [US3] Run `python -m pytest -q tests/test_errand.py` then `HEADLESS_TEST_BROWSER=1 python -m pytest -q tests/test_gates_browser.py` and make both pass

**Checkpoint**: the safety model is proven on a page that cannot change

---

## Phase 5: User Story 1 - Stay logged in between runs (Priority: P1)

**Goal**: the `probe` errand on the persistent profile

**Independent Test**: quickstart Scenario 2

- [ ] T024 [US1] Implement `scripts/probe.py`: docstring per the errand contract, `HANDOFF = "n/a (read-only errand)"`, positional `url`, empty plan, `dependencies = ["body"]`; in apply mode with an empty plan it still performs the handoff so the Director can log in; imports `headless` via `sys.path` insertion of the repo root
- [ ] T025 [US1] Run `python scripts/probe.py https://example.com` (preview) from the worktree with `HEADLESS_PROFILE_DIR` pointing at a temporary directory; confirm the title line, the artifact pair, and that the directory was created; run it a second time to confirm the profile is reused (no error, same directory)

**Checkpoint**: first errand runs end to end on this machine

---

## Phase 6: User Story 4 - Know the environment is ready (Priority: P2)

**Goal**: the `check_env` self-test

**Independent Test**: quickstart Scenario 1

- [ ] T026 [US4] Implement `scripts/check_env.py`: rows `browser` (Playwright resolves the `chrome` channel executable path), `playwright` (import + `chromium.executable_path` exists), `profile_dir` (create if absent, write and remove a probe file), `vault` (`open_vault(config).self_test()`; for keychain that is put/get/delete of `headless-selftest`); prints a PASS/FAIL table with a hint per failure; exit 1 on any FAIL; opens no window
- [ ] T027 [US4] Run `python scripts/check_env.py` (expect 4 PASS, exit 0) and `HEADLESS_SECRETS_BACKEND=gcp python scripts/check_env.py` (expect `vault` FAIL naming `HEADLESS_GCP_PROJECT`, exit 1, under 2 seconds)

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T028 [P] Update `scripts/README.md` inventory with `check_env.py` and `probe.py` and their usage lines
- [ ] T029 [P] Update `Function_Mapping.md` with rows for `check_env` and `probe` (site, reads, writes-up-to, secrets, handoff)
- [ ] T030 [P] Add a `PATTERNS.md` entry only for facts learned during implementation that are not already registered (for example the exact Chrome profile-lock error text); otherwise leave it unchanged
- [ ] T031 Add the v0.0.1 Changelog row to `Project_Structure.md` listing every new file (`headless/*.py`, `scripts/check_env.py`, `scripts/probe.py`, `requirements-gcp.txt`, `tests/**`) and update the Application Layer table (remove "Planned" markers)
- [ ] T032 Append two rows to the `MEMORY.md` "Errands run" table for the T025 and T027 runs
- [ ] T033 Run the commit gate: `python -m pytest -q` (under 10 s, browser module skipped) and `python scripts/verify_structure.py` (SUCCESS)

---

## Dependencies & Execution Order

- **Setup (Phase 1)** -> **Foundational (Phase 2)** -> user stories.
- **US2 (Phase 3)** depends only on Phase 2.
- **US3 (Phase 4)** depends on Phase 2 and on US2 (the session resolves sources through the vault and registry).
- **US1 (Phase 5)** and **US4 (Phase 6)** depend on US3's `Errand` base and on US2's `open_vault`; they are independent of each other.
- **Polish (Phase 7)** last.

### Parallel Opportunities

- T002, T003, T004 together; T005 to T008 together; T014 with T015; T019 with T020; T028 to T030 together.

## Implementation Strategy

MVP is Phases 1 to 4 plus `probe` (Phase 5): with those, the Director can seed logins and
every later errand has its safety model. `check_env` (Phase 6) is a fast follow within the
same version. Commit once at the end of Phase 7 after the gate passes; the orchestrator
verifies before the commit.
