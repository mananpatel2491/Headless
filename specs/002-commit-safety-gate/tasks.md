---

description: "Task list for feature 002 Commit Safety Gate"
---

# Tasks: Commit Safety Gate

**Input**: Design documents from `/specs/002-commit-safety-gate/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli-and-hooks.md, quickstart.md

**Tests**: REQUIRED by the specification (FR-016, SC-001, SC-002, SC-003, SC-004, SC-005). Test tasks are included and are written before the module they cover.

**Organization**: Tasks are grouped by user story so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1..US4)
- Every task names its file path

## Path Conventions

Single project at the repository root: `scripts/` (the scanner), `.githooks/`, `.github/workflows/`, `.claude/`, `tests/` (pytest). All paths below are relative to the worktree root `../worktrees/Headless/v0.0.2/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scanner skeleton, seeded allowlist, test scaffolding

- [x] T001 Create `scripts/scan_secrets.py` with a module docstring (background: the repository went public 2026-08-24; the four scan modes; that it never writes anything, in any mode) and an `argparse` skeleton with a mutually exclusive, required group: `--staged`, `--paths PATH [PATH ...]`, `--history`, `--stdin-hook`; no other flags exist
- [x] T002 [P] Create `.scanignore` at the repository root, seeded with the D3 fixture list as exact-string entries, one per line, with a comment header explaining the file's grammar (`re:` prefix for a regex entry, `#` for a comment): `ABCDE1234F`, `director@example.com`, `9998-8877-7666`, `1234 5678 9012`, `super-secret-value-12345`, `hunter2-XY`, `Director Name`
- [x] T003 [P] Create `tests/test_scan_secrets.py` with a `_run(args, stdin=None)` subprocess/CLI-invocation helper, a temporary-git-repo fixture (for the `--staged` and `--history` proofs), and one synthetic sample constant per Pattern in data-model.md (15 total). **Guidance to avoid the gate blocking its own first commit**: a sample already covered by the seeded `.scanignore` list (T002) needs nothing extra; every other sample (the credential-shaped ones, `phone_in`, `phone_us`, `payment_card`, `iban`) must either carry an inline `# scan:allow` marker on the line that defines it, or be assembled at test-run time (e.g. string concatenation) so the complete matching value never appears as one contiguous literal in this file's own committed source - otherwise this very test file fails its own `--staged`/`--history` scan on commit

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The Pattern table, matching, masking, Luhn validation, and `.scanignore` suppression: every scan mode depends on these. Tests first.

- [x] T004 [P] Write pattern-detection tests in `tests/test_scan_secrets.py`: each of the 15 named patterns (data-model.md) fires on its synthetic sample and produces a `Finding` with the right `pattern` name and `severity`; an email at `example.com`, `example.org`, a `noreply@` address, or `users.noreply.github.com` never fires (FR-006)
- [x] T005 [P] Write masking tests in `tests/test_scan_secrets.py`: `masked_snippet` for every fired Finding never contains the raw sample value (search, don't just spot-check); a value under 3 characters masks to bare `"****"`; the printed line format matches `<file>:<line>: <pattern> (<severity>) <masked_snippet>` exactly
- [x] T006 [P] Write Luhn tests in `tests/test_scan_secrets.py`: a real 16-digit test card number (Luhn-valid) fires `payment_card`; a random 16-digit string that is not Luhn-valid does not
- [x] T007 [P] Write `.scanignore` tests in `tests/test_scan_secrets.py`: an exact-string entry suppresses only that value, everywhere it appears; a `re:` entry suppresses by pattern; blank lines and `#`-comment lines are not entries; an inline `# scan:allow` marker suppresses only Findings on its own line, and only for that one scan; an unrelated occurrence of the same value on a non-allowlisted, non-marked line is still flagged
- [x] T008 Implement the Pattern table in `scripts/scan_secrets.py`: the 15 named patterns from data-model.md, each with its `category` and fixed `severity`, plus the Luhn checksum helper `payment_card` depends on
- [x] T009 Implement `Finding` construction and masking in `scripts/scan_secrets.py`: `redact(value)` (`"****" + value[-2:]`, or bare `"****"` under 3 characters), the allowed-email-domain check (FR-006), and the `<file>:<line>: <pattern> (<severity>) <masked_snippet>` line formatter - masking MUST happen at the same point the match is found, with no code path that holds the raw value longer than that step
- [x] T010 Implement `.scanignore` loading and suppression in `scripts/scan_secrets.py`: parse exact/`re:`/comment/blank lines once per invocation; suppress a Finding whose value matches a loaded entry; suppress a Finding whose source line contains `# scan:allow`, independent of `.scanignore`
- [x] T011 Run `python -m pytest -q tests/test_scan_secrets.py` (only the T004-T007 tests will exist and pass at this point; the CLI modes below don't exist yet) and make it green

**Checkpoint**: the detection engine (pattern matching, masking, suppression) is proven without git or Claude Code involved; every user story below only has to wire a mode around it

---

## Phase 3: User Story 1 - A commit is refused before it exists (Priority: P1) 🎯 MVP

**Goal**: `--staged` mode, the pre-commit hook, and the `check_env` activation self-test

**Independent Test**: quickstart Scenario 1

- [x] T012 [P] [US1] Write `--staged` tests in `tests/test_scan_secrets.py`: on a temporary git repo, a staged secret in an added line exits `1` and prints the finding; a staged change that only *removes* a line that contained a secret does not flag it (only added lines are examined, FR-002); a clean staged diff exits `0`
- [x] T013 [US1] Implement `--staged` in `scripts/scan_secrets.py`: run `git diff --cached` via `subprocess`, parse unified-diff added lines (lines starting with a single `+`, excluding the `+++` file header) with their target file and line number, match every Pattern, apply suppression, print Findings, exit `0`/`1`
- [x] T014 [US1] Create `.githooks/pre-commit` (POSIX `sh`, executable bit set): `#!/bin/sh` then `python3 scripts/scan_secrets.py --staged`
- [x] T015 [US1] Add a fifth row, `git_hooks`, to `scripts/check_env.py`: `PASS` when `git config core.hooksPath` reports `.githooks`, `FAIL` with the exact activation command (`git config core.hooksPath .githooks`) as the hint; add it to `ROW_NAMES` and the row list in `main()`
- [x] T016 [P] [US1] Write a `git_hooks` row test (PASS and FAIL branches, `git config` stubbed) in `tests/test_check_env.py`
- [x] T017 [US1] Run `python -m pytest -q tests/test_scan_secrets.py tests/test_check_env.py`, then quickstart Scenario 1 by hand: `git config core.hooksPath .githooks`, stage a synthetic secret, confirm `git commit` is refused with no commit created, fix or allowlist it, confirm the retry succeeds

**Checkpoint**: a real commit in this repository can be refused locally, with the activation state provable by `check_env`

---

## Phase 4: User Story 2 - Claude Code cannot write the content to disk (Priority: P1) 🎯 MVP

**Goal**: `--stdin-hook` mode and the repository's own `.claude/settings.json`

**Independent Test**: quickstart Scenario 2

- [x] T018 [P] [US2] Write `--stdin-hook` tests in `tests/test_scan_secrets.py`: a `Write` payload containing a synthetic PAN produces the deny JSON on stdout (`hookSpecificOutput.permissionDecision == "deny"`, `permissionDecisionReason` contains only the masked snippet) and exit `0`; a clean `Write` payload produces no stdout and exit `0`; malformed JSON, an unrecognized `tool_name`, and a missing/non-string text field each produce no stdout and exit `0` (fail-open, never a non-zero exit - FR-012); `Edit`/`MultiEdit` read `tool_input.new_string`, `NotebookEdit` reads `tool_input.new_source`
- [x] T019 [US2] Implement `--stdin-hook` in `scripts/scan_secrets.py`: read stdin as bytes, decode UTF-8 with `errors="replace"`, parse JSON inside a catch-all that resolves to "allow, no output" on any failure; select the text field by `tool_name` (contracts/cli-and-hooks.md section 4 table); skip binary/vendored/always-skipped paths using `tool_input.file_path` when present; match every Pattern against the text, apply suppression; on any remaining Finding, print one `hookSpecificOutput`/`permissionDecision: "deny"` JSON object built only from masked Finding lines plus a fixed closing line naming both allowlist mechanisms; always exit `0`
- [x] T020 [US2] Create `.claude/settings.json`: `PreToolUse` hook, matcher `Write|Edit|MultiEdit|NotebookEdit`, command `python3 "$CLAUDE_PROJECT_DIR/scripts/scan_secrets.py" --stdin-hook`, `timeout: 10`, `statusMessage: "Scanning for credentials and personal identifiers"` (contracts/cli-and-hooks.md section 4)
- [x] T021 [US2] Run `python -m pytest -q tests/test_scan_secrets.py -k stdin_hook`, then quickstart Scenario 2 by hand: pipe both a secret-bearing and a clean payload directly into `--stdin-hook`, then ask Claude Code itself to write a file containing a synthetic secret and confirm the write is refused with the reason surfaced back to the assistant

**Checkpoint**: MVP complete. A secret can be refused locally at commit time (Phase 3) and at write time (Phase 4), neither depending on the other.

---

## Phase 5: User Story 3 - CI and GitHub catch anything that slipped (Priority: P2)

**Goal**: `--history` mode and the CI workflow

**Independent Test**: quickstart Scenario 4

- [x] T022 [P] [US3] Write `--history` tests in `tests/test_scan_secrets.py`: on a temporary git repo, a secret added in one commit and then removed in a later commit is still reported (the working tree is clean, only history is not); the Finding's `file` label is `<sha>:<path>`; running `--history` against this repository's own real, current history exits `0` (SC-002's history half, D10's known-clean assumption)
- [x] T023 [US3] Implement `--history` in `scripts/scan_secrets.py`: enumerate commits reachable from `HEAD`, enumerate each commit's tracked blobs, read each blob's content via `git cat-file`, skip binary/always-skipped paths, match every Pattern, apply suppression, print Findings labeled `<sha>:<path>`, exit `0`/`1`
- [x] T024 [US3] Create `.github/workflows/secret-scan.yml`: triggers `push` and `pull_request`; job `scan` (`ubuntu-latest`, Python 3.12): `python scripts/scan_secrets.py --history` then `python -m pytest -q` then `python scripts/verify_structure.py`; job `gitleaks`: `gitleaks/gitleaks-action@v2`, no license key
- [x] T025 [US3] Run `python -m pytest -q tests/test_scan_secrets.py -k history`, then `time python scripts/scan_secrets.py --history` on this repository (expect exit `0`, under 2 seconds - SC-006); push a scratch branch and confirm both CI jobs run and pass alongside GitHub's own secret scanning and push protection

**Checkpoint**: a secret that reaches the shared repository through any path, local hook active or not, is still caught before it is reviewable

---

## Phase 6: User Story 4 - The Director allowlists a known-safe fixture (Priority: P3)

**Goal**: prove the allowlist mechanism end to end on this feature's own fixtures. The mechanism itself was already built in Phase 2 (T010); this phase is validation and coverage, not new scanner code.

**Independent Test**: quickstart Scenario 3

- [x] T026 [US4] Audit every synthetic sample used across `tests/test_scan_secrets.py`, `.scanignore` (T002), and any inline `# scan:allow` markers added in T003/T018: confirm each intentionally secret-shaped value is covered by exactly one mechanism, and add any entry or marker still missing
- [x] T027 [P] [US4] Write a regression test in `tests/test_scan_secrets.py` asserting `.scanignore`'s seven seeded entries exactly match the D3 list, so a future edit cannot silently drop or rename one without failing the suite
- [x] T028 [US4] Run quickstart Scenario 3 by hand: temporarily comment out the `ABCDE1234F` line in `.scanignore`, confirm the PAN fixture is now flagged, restore the line; add then remove a `# scan:allow` marker on a scratch line and confirm the flag follows the marker

**Checkpoint**: every user story independently proven; the feature's own commit is unblocked by its own gate

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T029 [P] Update `scripts/README.md` Maintenance table with a `scan_secrets.py` row (the four modes, one usage line each)
- [x] T030 [P] Update `CLAUDE.md`'s Lesson 4 gate sentence: name `python scripts/scan_secrets.py --staged` as part of every commit, and `.githooks` activation (`git config core.hooksPath .githooks`) as mandatory on every clone
- [x] T031 Bump `.specify/memory/constitution.md` to **1.2.0** (MINOR: a new hard rule, no principle removed or redefined) with a Sync Impact Report line describing the addition
- [x] T032 [P] Add the "Commit safety gate (v0.0.2)" entry to `PATTERNS.md`, referencing the existing Cross-Platform Automation pattern it instantiates
- [x] T033 [P] Update `README.md`: a new Setup step for `git config core.hooksPath .githooks`, and a "Public repo hygiene" section summarizing the three layers (local hook, Claude Code hook, CI backstop) and the allowlist
- [x] T034 Add the v0.0.2 Changelog row to `Project_Structure.md` listing every new file (`scripts/scan_secrets.py`, `.githooks/pre-commit`, `.github/workflows/secret-scan.yml`, `.scanignore`, `.claude/settings.json`, `tests/test_scan_secrets.py`) and add Director-layer table rows for `.githooks/`, `.github/`, `.scanignore`, `.claude/`
- [x] T035 Run the commit gate: `python -m pytest -q` (full suite, including `tests/test_scan_secrets.py`) and `python scripts/verify_structure.py` (expect SUCCESS)

---

## Dependencies & Execution Order

- **Setup (Phase 1)** -> **Foundational (Phase 2)** -> user stories.
- **US1 (Phase 3)** depends only on Phase 2.
- **US2 (Phase 4)** depends only on Phase 2; independent of US1 (this is why both together are the MVP - neither waits on the other).
- **US3 (Phase 5)** depends only on Phase 2; independent of US1 and US2 (it reuses the same pattern engine, not their CLI modes).
- **US4 (Phase 6)** depends on Phase 2 (the suppression logic) and, to have anything meaningful to audit, on the fixtures introduced in Phases 1, 3, 4, and 5 already existing - practically last among the stories.
- **Polish (Phase 7)** last.

### Parallel Opportunities

- T002, T003 together; T004 to T007 together; T012 with T016; T018 stands alone within its phase; T022 stands alone within its phase; T027 alongside T026; T029, T030, T032, T033 together.

## Implementation Strategy

MVP is Phases 1, 2, 3, and 4: with those, a secret is refused both at commit time and at
write time, independently of each other. US3 (the CI backstop, Phase 5) is a fast follow within
the same version - it is what actually protects the repository if the local layers are ever
skipped, so it should not lag far behind the MVP. US4 (Phase 6) closes the loop so the feature's
own test suite can be committed at all, and should be finished before the Polish phase's commit
gate run (T035) is attempted. Commit once at the end of Phase 7 after the gate passes; the
orchestrator verifies before the commit.
