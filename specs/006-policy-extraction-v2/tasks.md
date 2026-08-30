---

description: "Task list for feature 006 Policy Extraction v2"
---

# Tasks: Policy Extraction v2

**Input**: Design documents from `/specs/006-policy-extraction-v2/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/extraction-v2.md,
quickstart.md

**Tests**: REQUIRED by the specification (NFR-001, NFR-002, and SC-002 through SC-007 each name a
unit-test-provable outcome). Every test task is written, and made to fail, before the
implementation task it covers.

**Organization**: tasks are grouped by user story so each story is independently implementable and
testable, per this repository's own `tasks-template.md` convention.

**Status**: NOT STARTED. This delivery is spec-authoring only (`spec.md`, `plan.md`,
`research.md`, `data-model.md`, `contracts/extraction-v2.md`, `quickstart.md`, this file, and
`checklists/requirements.md`) - no source file under `headless/`, `scripts/`, `tests/`, or
`requirements.txt` has been touched, and no branch beyond the existing `v0.0.6` worktree has been
created. Every checkbox below is unchecked.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on another unchecked task)
- **[Story]**: which user story this task belongs to (US1, US2, US3), or unmarked for
  Setup/Foundational/Polish
- Every task names its own exact file path

## Path Conventions

Single project at the repository root: `headless/` (the package this feature changes), `scripts/`
(one existing script's own CLI addition), `tests/` (pytest). All paths below are relative to the
worktree root `../worktrees/Headless/v0.0.6/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: the dependency and configuration surface every later phase builds on.

- [ ] T001 [P] Update `requirements.txt`: add `pymupdf4llm` as an ordinary entry (research.md D2 -
  not a separate optional-extras file)
- [ ] T002 [P] Update `.env.example`: document `HEADLESS_OLLAMA_MODEL` (default `qwen3.5:35b`)
  and `HEADLESS_OLLAMA_URL` (default `http://localhost:11434`), including the localhost-only rule,
  matching the existing comment style for `HEADLESS_AGE_FILE`
- [ ] T003 [P] `tests/test_config.py`: write tests (to fail first) for `ollama_model`/`ollama_url`
  default resolution, override via environment, and the `ConfigError` refusal of any
  `HEADLESS_OLLAMA_URL` whose host is not `localhost`/`127.0.0.1` (spec FR-006, FR-007)
- [ ] T004 `headless/config.py`: add `ollama_model: str` and `ollama_url: str` fields to `Config`;
  resolve both from `HEADLESS_OLLAMA_MODEL`/`HEADLESS_OLLAMA_URL` with the documented defaults;
  raise `ConfigError` for a non-localhost host, mirroring `age_file`'s own load-time validation
  pattern exactly (depends on T003 existing and failing first)

**Checkpoint**: `Config` carries everything the local-model seam needs; every existing `Config(...)`
construction site in the test suite (mirroring v0.0.4's own BLOCK 1 lesson - grep the tree for
`Config(` before this phase is considered done) has the two new required-or-defaulted fields
addressed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the local-model transport contract and the shared term-derivation helper, both
needed by every user story below, before any generator-dispatch work begins.

**CRITICAL**: no user story task may begin until this phase is complete.

- [ ] T005 [P] `tests/test_localllm.py`: write tests (to fail first) for request construction (the
  exact payload shape including `"think": false` and `"options": {"temperature": 0}`, spec
  FR-005), the injectable-transport seam never opening a real socket (spec FR-009), and every
  failure classification in `contracts/extraction-v2.md` section 1 (connection failure, missing
  model, timeout, empty response, non-JSON response, schema-mismatch response) each collapsing to
  the same "failed attempt" outcome
- [ ] T006 `headless/localllm.py` (NEW): implement the request/response contract against T005 -
  the injectable transport callable, the payload builder, the response parser and schema
  validator, and the localhost-only host check (using `Config.ollama_url`, already validated by
  T004 at load time) (depends on T005 existing and failing first)
- [ ] T007 [P] `tests/test_policydoc.py` (new test functions, existing file): write tests (to fail
  first) for the shared term-derivation helper - two dates in either order near a period label,
  the 11-13-month and 5-7-month normalization bands, the "outside the two common terms" warning
  path, and the "fewer than two dates found" no-op path (spec FR-021)
- [ ] T008 `headless/policydoc.py`: implement the term-derivation helper against T007, as a
  standalone function usable by both generators (spec FR-022) (depends on T007 existing and
  failing first)

**Checkpoint**: the local-model transport and the term-derivation helper are both implemented and
unit-tested in isolation, with zero dependency yet on the conversion step or the sanity pass -
every later phase composes these two pieces rather than reimplementing either.

---

## Phase 3: User Story 1 - The Director's real declarations PDF yields a correct confirmed reference (Priority: P1) 🎯 MVP

**Goal**: extraction converts a PDF with layout awareness, proposes a candidate via the local
model, and correctly derives an annual term from policy-period dates with no explicit "N-month"
phrase present.

**Independent Test**: run `scripts/policy_extract.py` against a synthetic fixture reproducing the
real document's own scrambled-column, no-explicit-term shape, with an injected fake local-model
transport returning a valid candidate; assert the resulting confirmed reference has the correct
figures and `term_months` `"12"`.

### Tests for User Story 1 (write first)

- [ ] T009 [P] [US1] `tests/fixtures/`: add a wholly synthetic fixture reproducing the real
  document's own shape - a scrambled-column-order text (or a small built-once PDF, implementer's
  choice per research.md D9) whose policy-period dates are eleven to thirteen months apart with
  no "N-month" phrase anywhere; NO real value, name, policy number, or premium of any kind
  (spec NFR-003)
- [ ] T010 [P] [US1] `tests/test_policydoc.py`: write tests (to fail first) for the
  layout-aware-conversion-succeeds path using a fake converter double (never a real
  `pymupdf4llm` call), asserting the converted text is what the local-model generator (via a fake
  transport) and the regex generator each receive
- [ ] T011 [P] [US1] `tests/test_policydoc.py`: write a test (to fail first) for the end-to-end
  happy path against T009's fixture - fake converter, fake local-model transport returning a
  valid candidate with `term_months` omitted or wrong, asserting the term-derivation helper (T008)
  supplies or overrides it to `"12"` (spec FR-020, SC-001)
- [ ] T012 [P] [US1] `tests/test_policy_extract.py`: write a test (to fail first) asserting the
  cached reference for this scenario carries `generator: "local-llm:<model>"` and
  `converter: "<layout-aware converter name>"` (spec FR-023)

### Implementation for User Story 1

- [ ] T013 [US1] `headless/policydoc.py`: implement the conversion step - call the layout-aware
  converter first, producing a `ConvertedDocument`-shaped `(text, converter_name)` pair; on import
  failure or a raised exception, fall back to the existing `pypdf` raw-text call, recording
  `converter_name = "pypdf-raw"` (spec FR-001, FR-002) (depends on T010 existing and failing
  first)
- [ ] T014 [US1] `headless/policydoc.py`: implement the local-model generator - build the prompt
  from the converted text, call `headless/localllm.py`'s transport (T006), and construct an
  `ExtractionCandidate` from a successful, schema-valid response (spec FR-004, FR-005, FR-010)
  (depends on T006, T013)
- [ ] T015 [US1] `headless/policydoc.py`: wire the term-derivation helper (T008) into the
  local-model generator's own candidate construction, applying the override-and-note rule from
  spec FR-020 when the model's own claim disagrees (depends on T008, T014)
- [ ] T016 [US1] `headless/policydoc.py`: extend `PolicyReference` with the two new provenance
  fields (`generator`, `converter`); update `write_policy_reference`'s own serialization to
  include them (spec FR-023) (depends on T014)
- [ ] T017 [US1] `scripts/policy_extract.py`: wire the new dispatch (conversion, then local-model
  generation) into the existing per-asset loop, constructing the extended `PolicyReference` with
  the generator/converter values the pipeline now carries (depends on T016)
- [ ] T018 [US1] `headless/report.py`: extend the provenance footer to surface the two new fields
  from a confirmed reference, alongside the existing `source_path`/`confirmed_at` (spec FR-024)
- [ ] T019 [P] [US1] `tests/test_report.py`: write and pass a test asserting the footer renders
  the two new provenance fields when present, and degrades to the existing v0.0.5 footer shape
  when a cache file predates this feature (no `generator`/`converter` keys)

**Checkpoint**: User Story 1 is independently functional - a synthetic fixture reproducing the
real document's own failure mode now extracts correctly end to end, via a fake local model.

---

## Phase 4: User Story 2 - Nothing unconfirmed or non-local ever feeds a figure (Priority: P1)

**Goal**: the mechanical sanity pass strips any figure absent from the source document before the
Director's own confirmation prompt, and the local-model endpoint is refused outright when it is
not local.

**Independent Test**: construct a candidate with a figure absent from the source text and assert
the sanity pass removes it before `confirm_candidate` is called; set a non-local
`HEADLESS_OLLAMA_URL` and assert refusal before any conversion or network call.

### Tests for User Story 2 (write first)

- [ ] T020 [P] [US2] `tests/test_policydoc.py`: write tests (to fail first) for the sanity pass -
  a hallucinated premium amount, a hallucinated coverage limit, and a hallucinated deductible each
  stripped with the exact value-free warning text from `contracts/extraction-v2.md` section 2
  (spec FR-017, FR-018, SC-002); a clean candidate (every figure present in the source) passes
  through unchanged; `insurer` and each coverage line's own name are never checked (spec FR-028)
- [ ] T021 [P] [US2] `tests/test_policydoc.py`: write a test (to fail first) for the
  regex-generated candidate case - since a regex match is always a substring of its own source, a
  clean regex-derived candidate must never have any figure stripped by the sanity pass
- [ ] T022 [P] [US2] `tests/test_config.py`: confirm (from T003, extend if needed) that the
  localhost-only refusal happens with zero network call and zero PDF conversion attempted - a
  structural assertion via a fake transport/converter that must never be invoked (spec SC-003)
- [ ] T023 [P] [US2] `tests/test_policydoc.py`: write a test (to fail first) proving a candidate
  that fails confirmation (declined, or an uncorrectable correction) at the unchanged
  `confirm_candidate` step is never written to the cache, regardless of which generator produced
  it (spec FR-026)

### Implementation for User Story 2

- [ ] T024 [US2] `headless/policydoc.py`: implement the sanity pass - the normalization rule and
  the figure-by-figure literal-match check from `contracts/extraction-v2.md` section 2, called
  against every candidate (from either generator) before it reaches `confirm_candidate` (spec
  FR-017, FR-018, FR-019, FR-026) (depends on T020, T021 existing and failing first)
- [ ] T025 [US2] `headless/policydoc.py`: wire the sanity pass into the extraction dispatch
  between candidate generation (T014, or the regex path) and `confirm_candidate` (depends on T024)
- [ ] T026 [P] [US2] `tests/test_structural_grep.py`: confirm (no code change expected, per
  research.md D4's own "verified compatible without change" finding) that
  `test_sc022_no_llm_or_ai_client_import_in_the_comparison_or_extraction_path` still passes once
  `headless/localllm.py` and its `urllib.request`-based call exist - re-run this exact test as
  part of this phase's own verification, not merely at final commit-gate time, since it is the
  one existing test this feature's own design most directly risks breaking

**Checkpoint**: User Stories 1 AND 2 both work independently - a correct extraction reaches the
Director, and nothing invented or non-local can reach him.

---

## Phase 5: User Story 3 - Graceful degradation without Ollama (Priority: P2)

**Goal**: any local-model failure mode falls back automatically to the regex-based generator, and
`--no-llm` forces that path deliberately.

**Independent Test**: inject a transport double that raises a connection error and confirm the
run still produces the same regex-generated result v0.0.5's own suite already covers, plus one
value-free note.

### Tests for User Story 3 (write first)

- [ ] T027 [P] [US3] `tests/test_policydoc.py`: write tests (to fail first) for every fallback
  trigger in `contracts/extraction-v2.md` section 3 - connection failure, missing model, timeout,
  empty response, non-JSON response, schema-mismatch response - each producing exactly one
  value-free note and a regex-generated candidate (spec FR-013, SC-004)
- [ ] T028 [P] [US3] `tests/test_policy_extract.py`: write a test (to fail first) for the
  `--no-llm` flag - the injected local-model transport must never be invoked for any asset in
  that run, and every cached reference's own `generator` field reads `"regex-v1"` (spec FR-014,
  SC-005)
- [ ] T029 [P] [US3] `tests/test_policydoc.py`: write a test (to fail first) confirming a
  converted-but-empty document (from either converter) still yields `None`, never a crash,
  unchanged from v0.0.5 (spec FR-015, SC-007)

### Implementation for User Story 3

- [ ] T030 [US3] `headless/policydoc.py`: implement the fallback dispatch - any local-model
  failure per T027's own classification triggers the regex-based generator automatically, with
  exactly one value-free note (spec FR-013) (depends on T027 existing and failing first)
- [ ] T031 [US3] `scripts/policy_extract.py`: add the `--no-llm` argparse flag; when set, skip
  the local-model attempt entirely for every asset processed in the run (spec FR-014) (depends on
  T028 existing and failing first)
- [ ] T032 [US3] `headless/policydoc.py`: confirm (add a regression test if not already covered
  by T029) that the existing empty-conversion / zero-coverage-lines `None` path is unchanged by
  the new dispatch (spec FR-015)

**Checkpoint**: all three user stories are independently functional; the feature degrades safely
under every failure mode this specification names.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: docs of record, the constitutional amendment, the opt-in integration test, and the
commit gate.

- [ ] T033 [P] `PATTERNS.md`: add one new entry, "Local-model extraction with a mechanical figure
  gate (v0.0.6, spec 006-policy-extraction-v2)," documenting the pipeline (conversion, local-model
  generation, sanity pass, unchanged confirmation gate), the fallback matrix, and the
  provenance-field convention - following this file's own established entry style exactly
- [ ] T034 [P] `Project_Structure.md`: add rows for `headless/localllm.py` (new); update the
  descriptions for `headless/policydoc.py`, `headless/config.py`, `scripts/policy_extract.py`,
  and `requirements.txt`; append a new Changelog row for v0.0.6 following this file's own
  established row format exactly
- [ ] T035 [P] `scripts/README.md`: update `policy_extract.py`'s own table row to mention the
  local-model attempt, the `--no-llm` flag, and the fallback behavior
- [ ] T036 [P] `MEMORY.md`: add a dated entry under "Open items" (or "Errands run" once a real
  Director run has happened) recording this feature's own delivery and the pending Director UAT
  against his real declarations PDF
- [ ] T037 `CLAUDE.md`: apply the drafted Secrets-section replacement text from `plan.md`'s own
  "Constitutional amendment" subsection verbatim (or as adapted during implementation)
- [ ] T038 `.specify/memory/constitution.md`: bump to `1.4.0` (MINOR) and add the drafted Sync
  Impact Report line from `plan.md` to the file's own header comment; update the Secrets Hard
  Rules bullet to match T037 (depends on T037)
- [ ] T039 [P] An opt-in integration test, gated by `HEADLESS_TEST_OLLAMA=1`
  (`tests/test_localllm.py` or a dedicated `tests/test_localllm_integration.py`): runs the real
  local-model seam against the synthetic scrambled snippet from T009/research.md and asserts
  schema validity only, never an exact value (spec NFR-002)
- [ ] T040 Run the full commit gate: `python -m pytest -q`, `python scripts/verify_structure.py`,
  `python scripts/scan_secrets.py --staged` - all three green, with the opt-in browser suite and
  `HEADLESS_TEST_OLLAMA=1` suite both left unrun by default (unchanged convention, spec NFR-001)
- [ ] T041 Run `python scripts/policy_extract.py` (quickstart.md Scenarios 1-4) against the
  Director's own real declarations PDF, with his own Ollama running - **Director UAT, pending**;
  this delivery's own brief is spec-authoring only and does not perform this task
- [ ] T042 Run quickstart.md Scenario 6 (the localhost-only refusal) - safe to run without a real
  PDF or a real Ollama instance; a reasonable first automated-adjacent check once implementation
  lands, ahead of T041's own Director-only scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies - can start immediately
- **Foundational (Phase 2)**: depends on Setup (needs `Config.ollama_url`/`ollama_model` from
  T004) - BLOCKS every user story
- **User Story 1 (Phase 3)**: depends on Foundational (needs `headless/localllm.py` from T006 and
  the term helper from T008)
- **User Story 2 (Phase 4)**: depends on Foundational; independent of User Story 1's own
  implementation tasks, though its sanity pass wraps whatever candidate User Story 1's dispatch
  produces - safe to implement in parallel with Phase 3 if staffed, sequential otherwise
- **User Story 3 (Phase 5)**: depends on Foundational; its fallback dispatch wraps User Story 1's
  own local-model call, so T030 in particular is easiest to implement once T014 exists, even
  though the two stories are independently testable
- **Polish (Phase 6)**: depends on all three user stories being complete

### Within Each User Story

- Fixture and test tasks (marked `[P]`) before their own implementation task
- Tests MUST fail before the implementation task that makes them pass
- `headless/policydoc.py` implementation tasks are NOT marked `[P]` against each other within a
  phase (all touch the same file); test and fixture tasks across different files remain `[P]`
  against each other

### Parallel Opportunities

- T001-T003 (Setup) in parallel
- T005 and T007 (Foundational tests, different files) in parallel
- T009-T012 (User Story 1 tests/fixture, different files) in parallel
- T020-T023 (User Story 2 tests, different files) in parallel
- T027-T029 (User Story 3 tests, different files) in parallel
- T033-T036, T039 (Polish, independent files) in parallel

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational)
2. Complete Phase 3 (User Story 1)
3. **STOP and VALIDATE**: run `pytest -q -k policydoc` and confirm the synthetic-fixture end-to-
   end test (T011) passes
4. Phases 4 and 5 harden the MVP; neither is required for User Story 1's own value to be real, but
   both are Priority P1/P2 in `spec.md` and are expected before this feature is considered
   complete

### Incremental Delivery

1. Setup + Foundational -> foundation ready
2. User Story 1 -> independently testable -> the Director's real reading-order and annual-term
   gaps are closed
3. User Story 2 -> independently testable -> the constitutional floor (no hallucination, no
   non-local call) is proven, not merely asserted
4. User Story 3 -> independently testable -> the tool degrades safely on a day Ollama is not
   running
5. Polish -> docs of record, the constitutional amendment, the commit gate, then Director UAT
   (T041, pending by this delivery's own brief)

## Notes

- `[P]` tasks touch different files with no dependency on another unchecked task in this list
- `[Story]` maps a task to spec.md's own numbered user story for traceability
- Verify each test task's own test fails before writing the implementation task that follows it
- This delivery stops at spec authoring; T004 onward are for a future implementation delivery to
  execute, not for this session
- Avoid: vague tasks, two tasks racing to edit the same file without a stated dependency,
  cross-story dependencies that would break either story's own independent testability
