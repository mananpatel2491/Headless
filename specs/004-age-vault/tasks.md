---

description: "Task list for feature 004 Age Vault"
---

# Tasks: Age Vault

**Input**: Design documents from `/specs/004-age-vault/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/vault-and-cli.md, quickstart.md

**Tests**: REQUIRED by the specification (SC-001, SC-002, SC-003, SC-004, SC-005, SC-006, SC-007,
SC-008). Test tasks are included and are written before the module code they cover.

**Organization**: Tasks are grouped by user story so each story is independently implementable
and testable.

**Status**: this delivery is spec-authoring only (per this feature's brief: no implementation,
no commit). Every task below is unchecked - none of this feature's code exists yet. This differs
from specs/003-login-persistence/tasks.md, whose boxes were already ticked because that feature's
spec set was authored after its implementation had landed in the same delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1..US3)
- Every task names its file path

## Path Conventions

Single project at the repository root: `headless/` (the package this feature changes), `scripts/`
(one new maintenance script plus one existing script's small update), `tests/` (pytest). All
paths below are relative to the worktree root `../worktrees/Headless/v0.0.4/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: the config surface (`age` as a valid, default backend value; the `age_file` field and
its resolution rule) in place before either the backend or the CLI is written against it.

- [ ] T001 [P] Update `.gitignore`: add `*.age` as a belt-and-braces entry (the vault lives
  outside the repository by default, per `HEADLESS_AGE_FILE`'s default; this is the second line
  of defense, mirroring v0.0.3's `session-cookies.json*` entry)
- [ ] T002 [P] Update `.env.example`: change the `HEADLESS_SECRETS_BACKEND` comment to name `age`
  as the default (alongside `keychain`/`gcp`), and add a new `HEADLESS_AGE_FILE` line documenting
  its default (`~/.headless/profile.age`) and its absolute-or-`~`-relative-only rule
- [ ] T003 Update `headless/config.py`: add `"age"` to `VALID_SECRETS_BACKENDS`; change
  `secrets_backend`'s default (the `pick(...)` call's fallback) from `"keychain"` to `"age"`; add
  `age_file: Path` to the `Config` dataclass; resolve it from `HEADLESS_AGE_FILE`, default
  `~/.headless/profile.age`, `~`-expanded; raise `ConfigError` if the expanded result is not
  absolute (spec FR-004, research.md D2)

**Checkpoint**: `load_config()` with no environment overrides now resolves `secrets_backend ==
"age"` and a usable `age_file` path. No backend or CLI code depends on this yet, but both need
it to exist first.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `AgeBackend` itself - decrypt-once-and-cache, every failure mode, the write-path
refusal, the no-decrypt `self_test()` - built and proven correct in isolation, with an injectable
fake runner, before `scripts/vault.py` or `check_env.py` are wired to depend on it. Tests first.

- [ ] T004 [P] Write `AgeBackend` decrypt/cache tests in `tests/test_secrets.py`: first
  `get_secret(name)` call invokes the fake runner exactly once with an argv shaped like
  `["age", "-d", str(vault_file)]` (or equivalent); a second `get_secret` call for a different
  name in the same instance invokes the runner zero additional times (SC-002); the returned value
  matches the fixture document's value for that name, exactly
- [ ] T005 [P] Write `AgeBackend` failure-mode tests in `tests/test_secrets.py`: vault file
  missing -> a config-style error naming only the path, zero runner calls; runner returns
  nonzero -> a value-free error naming only the exit code plus the fixed hint `wrong passphrase or
  corrupted vault`, and a distinctive fixture-shaped stderr string the fake runner returns never
  appears anywhere in the raised exception's message (SC-007); `name` absent from a successfully
  decrypted document -> the existing `SecretMissing(name)`, unchanged
- [ ] T006 [P] Write `AgeBackend` write-path and `self_test()` tests in `tests/test_secrets.py`:
  `put_secret`/`delete_secret` raise immediately, mentioning `scripts/vault.py`, with zero runner
  calls in either case; `self_test()` returns `True` when a stubbed `PATH` lookup and file
  existence check both succeed, `False` when either does not, and in every case invokes zero
  decrypt-shaped runner calls (SC-005)
- [ ] T007 Implement `AgeBackend` in `headless/secrets.py`: constructor takes `vault_file: Path`
  and an optional `runner` callable (default wraps `subprocess.run` against the real `age`
  binary); `get_secret` decrypts at most once per instance, caches the parsed
  `dict[str, str]`, and serves every later call from that cache (data-model.md's `locked` ->
  `decrypted-cached` transition); `put_secret`/`delete_secret` raise directing the caller to
  `scripts/vault.py`; `self_test()` checks only `shutil.which("age")` and `vault_file.exists()`
- [ ] T008 Update `open_vault` in `headless/secrets.py`: add the `"age"` branch, constructing
  `AgeBackend(config.age_file)`
- [ ] T009 Run `python -m pytest -q tests/test_secrets.py -k age` and make T004-T006 green against
  the T007-T008 implementation

**Checkpoint**: `AgeBackend` is proven correct and prompt-free-in-tests in isolation. Every user
story below only has to wire it into `open_vault`'s existing dispatch (already done, T008) or
build the CLI and docs around it.

---

## Phase 3: User Story 1 - The vault holds everything in one encrypted file (Priority: P1) 🎯 MVP

**Goal**: prove the vault's consumer-facing contract end to end: `get_secret("profile")` still
feeds `ProfileRegistry.load` correctly, the default backend really is `age` with zero
configuration, and a relative `HEADLESS_AGE_FILE` is refused the same way an out-of-bounds
`HEADLESS_PREVIEW_DIR` already is.

**Independent Test**: quickstart Scenarios 2-4 (hand-run: init, seed `profile`, confirm
`check_env` and `vault.py list`) plus the automated tests below.

- [ ] T010 [P] [US1] Write a default-backend test in `tests/test_config.py`: `load_config()` with
  `HEADLESS_SECRETS_BACKEND` unset (and no override) resolves `secrets_backend == "age"` (SC-003)
- [ ] T011 [P] [US1] Write `age_file` resolution tests in `tests/test_config.py`: no override ->
  the `~`-expanded default; an absolute override -> used as-is; a bare relative override (for
  example `"myvault.age"`) -> `ConfigError`, mirroring the existing `HEADLESS_PREVIEW_DIR`
  relative-path test's shape (research.md D2)
- [ ] T012 [US1] Write a `ProfileRegistry` integration test in `tests/test_profile.py` (or
  `tests/test_secrets.py`, implementer's choice, matching whichever file already covers this
  kind of cross-module test): an `AgeBackend` constructed with a fake runner whose fixture
  document holds a `profile` key equal to a small JSON registry string feeds
  `ProfileRegistry.load(vault)` correctly, and `registry.get("identity.name")` returns the
  expected value - proving FR-006's "unchanged consumer contract" claim end to end, not only at
  the `AgeBackend.get_secret` level T004 already covers
- [ ] T013 [US1] Run `python -m pytest -q tests/test_config.py tests/test_secrets.py
  tests/test_profile.py -k "age or backend"`, then quickstart Scenarios 2-4 by hand (Director
  UAT): `vault.py init`, `vault.py set profile` with a synthetic example, `check_env.py` reporting
  the `vault` row PASS, `vault.py list` printing `profile` only. (Director UAT, pending - this
  spec-authoring delivery does not execute it, per the brief's hard constraint against touching
  `~/.headless/`.)

**Checkpoint**: MVP core delivered. The vault holds one encrypted file, the default backend is
`age` with zero configuration, and the existing `ProfileRegistry` contract is unchanged.

---

## Phase 4: User Story 2 - Nothing decrypts without the passphrase (Priority: P1)

**Goal**: prove the gate: exactly one prompt per process for any secret-touching run, no prompt
at all for an empty plan, a clean refusal on a wrong passphrase or a missing terminal, and
`check_env.py`'s vault row staying entirely decrypt-free.

**Independent Test**: quickstart Scenarios 5, 6, and 9 (hand-run) plus the automated tests below.
The mechanism itself (decrypt-once-and-cache, fail-soft-free error shapes) was already built and
tested in Phase 2; this phase proves the properties that fall out of it, the same shape spec
003's own User Story 3 validated properties Phase 2 there had already built.

- [ ] T014 [P] [US2] Write an `errand.py` pre-resolution test in `tests/test_errand.py`: an
  `Errand` subclass whose `plan()` returns one `registry:`-sourced `FieldPlan`, run against a
  `FakeVault`-equivalent `AgeBackend` (fake runner) in `preview` mode (no `--apply`), triggers
  exactly one runner call - proving FR-024's "every mode, not only apply" claim holds for the new
  default backend the same way it already holds for `FakeVault` in existing tests
- [ ] T015 [P] [US2] Write a probe-has-no-prompt test in `tests/test_errand.py` (or extend an
  existing `probe.py` test, implementer's choice): running an `Errand` with an empty `plan()`
  against an `AgeBackend` (fake runner) triggers zero runner calls, in every mode - proving
  FR-024's `probe.py` carve-out still holds under the new default backend
- [ ] T016 [P] [US2] Write the `check_env.py` vault-row age-branch tests in
  `tests/test_check_env.py`: `age` present on `PATH` and vault file present -> PASS, zero runner
  calls of the decrypt shape; `age` absent -> FAIL with the `brew install age` hint; vault file
  absent -> FAIL with the `python scripts/vault.py init` hint; in every case, zero decrypt-shaped
  calls happen (SC-006, mirrors T006's `self_test()` proof at the `check_env` row level)
- [ ] T017 [US2] Update `scripts/check_env.py`'s `_check_vault(config)`: when
  `config.secrets_backend == "age"`, check `shutil.which("age")` and
  `config.age_file.exists()` only (no `open_vault`/`self_test()` call that could differ from this
  contract); return the two hint strings from contracts/vault-and-cli.md's row 4 table; leave the
  `keychain`/`gcp` branches unchanged
- [ ] T018 [US2] Run `python -m pytest -q tests/test_errand.py -k age`, then
  `python -m pytest -q tests/test_check_env.py -k vault`, then quickstart Scenarios 5, 6, and 9 by
  hand (Director UAT): confirm the passphrase prompt appears exactly once for a
  registry-resolving snippet, confirm a wrong passphrase refuses cleanly with the fixed hint, and
  re-read the policy reminder in Scenario 9. Automated parts pending implementation. The hand-run
  parts are (Director UAT, pending).

**Checkpoint**: independent of User Story 1 in the same sense spec 003's US1/US2 were - both
depend only on Phase 2's `AgeBackend` existing; neither story's tasks touch a line the other
changes.

---

## Phase 5: User Story 3 - First-time setup works, macOS or Windows (Priority: P2)

**Goal**: `scripts/vault.py` exists and is fully tested against the fake-runner seam, and
`README.md` carries a First-time setup section a fresh clone can follow start to finish on either
platform.

**Independent Test**: quickstart Scenario 10 (the fresh-clone walkthrough, hand-run) plus the
automated tests below.

- [ ] T019 [P] [US3] Write `vault.py init` tests in `tests/test_vault.py` (new file): vault file
  absent -> the fake runner is invoked once with an encrypt-shaped call, an empty (`{}`) plaintext
  document piped as its stdin payload, exit `0`, resolved path printed; vault file already present
  -> refused before any runner call, exit `1`, existing file's content untouched
- [ ] T020 [P] [US3] Write `vault.py set`/`unset` tests in `tests/test_vault.py`: `set NAME` with
  a `getpass`-stubbed value decrypts once, mutates the in-memory document, re-encrypts once, and
  the constructed encrypt-call's stdin payload (parsed back as JSON) contains `NAME` mapped to the
  stubbed value; the value never appears in any captured `argv` across every subprocess call this
  test observes (SC-008); `unset NAME` removes an existing key the same way and also succeeds,
  unchanged in exit code, when `NAME` was never present (FR-018's idempotence); a failed decrypt
  on either subcommand never reaches the mutate or re-encrypt step (data-model.md's failure
  isolation)
- [ ] T021 [P] [US3] Write `vault.py list`/`path` tests in `tests/test_vault.py`: `list` against
  a fixture document with distinctive synthetic values prints every name, sorted, one per line,
  and none of the fixture's values appear anywhere in captured stdout (SC-004); `list` against an
  empty document prints zero lines; `path` prints the resolved `age_file` path and triggers zero
  runner calls of any kind, decrypt or encrypt
- [ ] T022 [US3] Implement `scripts/vault.py`: `argparse` with subcommands `init`, `set NAME`,
  `unset NAME`, `list`, `path`; each subcommand follows data-model.md's DECRYPT -> MUTATE ->
  RE-ENCRYPT lifecycle (skipping DECRYPT for `init`, skipping RE-ENCRYPT for `list`/`path`);
  `set`'s value is read via `getpass.getpass()`, never `argv`; the re-encrypt step pipes the
  mutated document's JSON bytes to the runner's stdin, writes the returned ciphertext to a temp
  file in the vault's own directory, `chmod 0600` (no-op on Windows, wrapped so it cannot raise
  there), then `os.replace` onto the vault path, mirroring `headless/session.py`'s
  `_export_session_cookies` atomic-write shape (research.md D6)
- [ ] T023 [US3] Run `python -m pytest -q tests/test_vault.py` and make T019-T021 green against
  the T022 implementation
- [ ] T024 [US3] Add a "First-time setup" section to `README.md`: installing `age` (`brew install
  age` on macOS; `winget install FiloSottile.age` or `scoop install age` on Windows, presented as
  alternatives), the venv/`requirements.txt`/`playwright install chromium` steps already
  documented, `git config core.hooksPath .githooks`, `python scripts/vault.py init` and
  `python scripts/vault.py set profile` with a minimal, obviously synthetic example registry
  (never real identifiers), `python scripts/check_env.py` as the section's finish line; note that
  the Keychain backend is macOS-only and `age` is the cross-platform default; update the existing
  Setup section's secrets step to reflect the new default backend (research.md D9)
- [ ] T025 [US3] Run quickstart Scenario 10 by hand on at least one machine (Director UAT,
  pending): follow only the new README section top to bottom on a fresh-enough setup, confirm
  `check_env.py` reaches 5/5 PASS with the `vault` row naming `age`, and record the outcome (tool
  name, platform, PASS/FAIL only - never any typed value) in `MEMORY.md`'s "Errands run" table

**Checkpoint**: every user story independently proven. `scripts/vault.py` is the only vault write
path (FR-013 held structurally, T006's write-refusal tests plus this phase's own tests together),
and a fresh clone has a documented path to a working vault on either platform.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T026 [P] Update `CLAUDE.md`'s Secrets section: state the new default backend (`age`, local
  passphrase-encrypted vault, GCP Secret Manager plan superseded), the per-run passphrase gate
  (no caching of any kind), and the never-store-passwords-or-cards policy (FR-023, research.md D8)
- [ ] T027 Regenerate `.specify/memory/constitution.md` to **1.3.0** (MINOR: the default secrets
  backend changed, and one new explicit hard rule - never store a password or a card value - is
  added; not a wording-only PATCH, unlike v0.0.3's own bump) with a Sync Impact Report line
  describing the change
- [ ] T028 [P] Add two new entries to `PATTERNS.md`: "Age vault" (summarizing D1-D7:
  default-backend change, the derived vault-file location, decrypt-once-and-cache, the
  never-write-from-AgeBackend rule, the terminal-prompt-not-stdin mechanism that keeps the
  passphrase out of Python entirely, `check_env`'s reachability-only row) and "Passphrase is the
  gate" (summarizing the User Story 2 property: no caching of any kind, every secret-touching run
  in every mode prompts exactly once, `probe.py`'s empty plan does not)
- [ ] T029 [P] Update `README.md`'s existing Setup section: the secrets step now names `age` as
  the default and points at the new First-time setup section for the full walkthrough (T024
  already added that section; this task is the small cross-reference update to the older section
  so the two do not contradict each other)
- [ ] T030 Add the v0.0.4 Changelog row to `Project_Structure.md` listing every file touched
  (`headless/secrets.py`, `headless/config.py`, `scripts/vault.py` [new], `scripts/check_env.py`,
  `.gitignore`, `.env.example`, `tests/test_secrets.py`, `tests/test_vault.py` [new],
  `tests/test_config.py`, `tests/test_errand.py`, `tests/test_check_env.py`, plus every
  docs-of-record file touched in this phase) and new Application/Director Layer rows for
  `scripts/vault.py` - this table is also where the repository's version is recorded, since no
  separate `VERSION`, `pyproject.toml`, or `package.json` file exists anywhere in the tree
  (confirmed by the same repository-wide search spec 003's research.md D8 already ran)
- [ ] T031 [P] Update `terraform/README.md`: add a status paragraph recording that the local
  `age` vault (this feature) replaces the planned GCP Secret Manager backend (Director decision
  2026-08-25); no cloud resource will be created under this plan; `GcpBackend`'s code stays in the
  tree, inert, in case a future decision reverses this
- [ ] T032 [P] Update `MEMORY.md`: record the Director's decision to supersede the GCP Secret
  Manager plus PAM plan with the local `age` vault (dated 2026-08-25), and add the "Errands run"
  table entry for the fresh-clone walkthrough once T025 has produced a real outcome to record
- [ ] T033 Run the commit gate: `python -m pytest -q && python scripts/verify_structure.py &&
  git add -A && python scripts/scan_secrets.py --staged`

---

## Dependencies & Execution Order

- **Setup (Phase 1)** -> **Foundational (Phase 2)** -> user stories.
- **US1 (Phase 3)** depends only on Phase 2 (`AgeBackend` must exist and be wired into
  `open_vault` before its consumer contract can be tested).
- **US2 (Phase 4)** depends only on Phase 2 (the decrypt-once-and-cache mechanism and the
  fail-soft error shapes it validates against real callers). Independent of US1 - neither
  story's tasks touch a line the other changes, which is why both land in the same MVP window
  without one waiting on the other, mirroring spec 003's US1/US2 relationship.
- **US3 (Phase 5)** depends on Phase 2 (`AgeBackend`'s contract, which `vault.py` must match on
  the read side) but not on US1 or US2's own tasks - `scripts/vault.py` is a new file neither
  story touches. Ordered last among the stories because the README walkthrough (T024) reads more
  naturally once the reader can point at a backend whose default-and-gate behavior (US1, US2) is
  already proven, the same "validation lands last, mechanism came first" reasoning spec 003's
  own Phase 5 used.
- **Polish (Phase 6)** last.

### Parallel Opportunities

- T001, T002 do not conflict but neither depends on the other; both can start immediately.
- T004, T005, T006 together (same file, disjoint test functions, written before T007/T008 exist).
- T010, T011 together (same file, disjoint test functions); T012 can start alongside them once
  T007/T008 land, since it depends on the implementation, not on T010/T011.
- T014, T015, T016 together (T014/T015 share `tests/test_errand.py` but are disjoint test
  functions; T016 is a different file entirely).
- T019, T020, T021 together (same new file, disjoint test functions, written before T022 exists).
- T026, T028, T029, T031, T032 together (five different docs-of-record files, no shared state).

## Implementation Strategy

MVP is Phases 1, 2, 3, and 4: with those, the vault holds everything in one encrypted file and
nothing decrypts without the passphrase, independently of each other (Phase 3 and Phase 4 touch
disjoint parts of the codebase once Phase 2's `AgeBackend` exists). Phase 5 (User Story 3) is not
deferred lower-priority work despite landing last in execution order - it is the CLI and the
documentation that make the mechanism from Phases 2-4 actually reachable by someone who is not
the Director's own already-set-up machine, sequenced last only because it needs `AgeBackend`'s
contract (Phase 2) to build `vault.py`'s read side against, the same reasoning spec 003's own
Phase 5 used for its validation phase. Commit once at the end of Phase 6 after the gate passes;
the orchestrator (or an Opus verifier, per the global agent conventions) reviews before the
commit - none of that happens in this spec-authoring delivery, per this feature's brief.
