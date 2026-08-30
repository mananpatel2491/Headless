---

description: "Task list for feature 007 Extraction Fidelity"
---

# Tasks: Extraction Fidelity

**Input**: Design documents from `/specs/007-extraction-fidelity/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/fidelity.md,
quickstart.md

**Tests**: REQUIRED by the specification (NFR-001 through NFR-003, and SC-001 through SC-009 each
name a unit-test-provable outcome). Every test task is written, and made to fail, before the
implementation task it covers.

**Organization**: tasks are grouped by user story so each story is independently implementable and
testable, per this repository's own `tasks-template.md` convention.

**Status**: IMPLEMENTED (2026-08-30, builder session, worktree `v0.0.7`). T001 through T030 are
complete, staged and uncommitted pending Opus verification; the orchestrator-run live probe (T029)
was executed against the Director's own three real declarations PDFs under explicit orchestrator
authorization (paths passed on a throwaway scratchpad script's own argv only, never written into
this repository) - see that task's own note below for the outcome. T031 (Director-only UAT) remains
genuinely out of this delivery's own scope and is not performed. No commit, no push, no merge, no
branch, and `~/.headless/` untouched, per this delivery's own brief.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on another unchecked task)
- **[Story]**: which user story this task belongs to (US1, US2, US3, US4), or unmarked for
  Foundational/Cross-cutting/Polish
- Every task names its own exact file path

## Path Conventions

Single project at the repository root: `headless/` (the package this feature changes), `tests/`
(pytest). No new script, no new top-level directory. All paths below are relative to the worktree
root `../worktrees/Headless/v0.0.7/`.

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: the de-glue transformation every later phase reads through - both the corrected
term-derivation helper (phrase detection) and the sanity pass operate on the text this phase
produces.

**CRITICAL**: no user story task may begin until this phase is complete.

- [x] T001 [P] `tests/test_policydoc.py`: write tests (to fail first) for the de-glue
  transformation - a lowercase-to-uppercase boundary insertion, a letter-to-digit and a
  digit-to-letter boundary insertion, a same-case glued word pair left unresolved (the documented
  residual), and confirmation that no digit's own value, currency symbol, or existing punctuation
  character is ever altered (spec FR-012 through FR-015)
- [x] T002 `headless/policydoc.py`: implement the de-glue transformation against T001; wire it into
  the conversion step so `ConvertedDocument.text` always carries the de-glued form before any
  generator, the term-derivation helper, or the sanity pass ever reads it (spec FR-012, FR-016)
  (depends on T001 existing and failing first)

**Checkpoint**: every later phase reads de-glued text with no further wiring of its own.

---

## Phase 2: User Story 1 - A verbatim composite figure survives the gate (Priority: P1) 🎯 MVP

**Goal**: the sanity pass tokenizes a proposed figure the same way it already tokenizes the source
text, so a composite or spaced verbatim figure survives while a genuine hallucination is still
stripped.

**Independent Test**: construct a synthetic fixture whose source text states a composite,
multi-digit-run figure verbatim, and a candidate proposing that exact string; assert the corrected
sanity pass leaves it unchanged, while a figure absent from the source (including one sharing only a
digit-run suffix or prefix with a real, unrelated source figure) is still stripped.

### Tests for User Story 1 (write first)

- [x] T003 [P] [US1] `tests/test_policydoc.py`: write tests (to fail first) for the corrected
  per-token tokenization - a split, labeled composite figure ("<amount> each person/<amount> each
  accident"-shaped) passes; a spaced-digit-group identifier ("NNN NNN NNN"-shaped) passes; a value
  sharing only a digit-run suffix or prefix with an unrelated source figure still strips (spec 006's
  own anti-hallucination guarantee, re-verified under the corrected tokenization); a non-numeric
  value stays exempt (spec FR-001 through FR-005, SC-001, SC-002)

### Implementation for User Story 1

- [x] T004 [US1] `headless/policydoc.py`: rewrite the source/proposed tokenization and the
  membership check so both sides strip only `$` and `,` (never whitespace) and a proposed value
  passes only when every one of its own digit-run tokens is a member of the source's own token set
  (spec FR-001, FR-002) (depends on T003 existing and failing first)
- [x] T005 [P] [US1] `tests/test_policydoc.py`: write a regression test (to fail first, if not
  already covered by T003) confirming a clean regex-derived candidate is never stripped by the
  corrected gate - unchanged from spec 006's own guarantee that a regex match is by construction a
  substring of its own source
- [x] T006 [US1] Run `pytest -q -k "sanity_pass or figure_present"` and confirm every test in T003
  and T005 passes; no file beyond T004 is expected to change in this phase

**Checkpoint**: User Story 1 is independently functional - the corrected gate no longer destroys a
verbatim composite figure, and spec 006's own anti-hallucination guarantee still holds.

---

## Phase 3: User Story 2 - The derived term reflects the real policy period (Priority: P1)

**Goal**: the term-derivation helper never pairs an unrelated date before a policy-period label with
the real period's own dates, and an explicit de-glued phrase always outranks date arithmetic.

**Independent Test**: construct a synthetic fixture placing an unrelated date before a
policy-period label, followed by the label and the real period's own two dates; assert the
corrected helper derives the term from the real period dates only. Construct a second fixture whose
de-glued text carries an explicit "N-month" phrase alongside two period dates that would derive a
different term; assert the phrase wins.

### Tests for User Story 2 (write first)

- [x] T007 [P] [US2] `tests/test_policydoc.py`: write tests (to fail first) for scanning every
  label occurrence, windowing after each occurrence only (~400 characters, never before), and
  computing the term from the maximum and minimum date collected across every window - including a
  fixture reproducing an unrelated date positioned before the label (spec FR-006 through FR-009,
  SC-003)
- [x] T008 [P] [US2] `tests/test_policydoc.py`: write tests (to fail first) for phrase preference -
  a de-glued "N-month"/"N month" phrase takes precedence over the date-derived value, for both the
  local-model generator and the regex-based generator (spec FR-010, FR-011, SC-004)

### Implementation for User Story 2

- [x] T009 [US2] `headless/policydoc.py`: rewrite the label-occurrence scan and the window to
  search after each occurrence only; rewrite the date-collection step to gather every parseable date
  across every window and compute the span from the maximum and minimum date collected (spec
  FR-006 through FR-009) (depends on T007 existing and failing first)
- [x] T010 [US2] `headless/policydoc.py`: wire phrase preference into both generators' own term
  resolution, checked ahead of the corrected date-derivation helper from T009 (spec FR-010, FR-011)
  (depends on T008 existing and failing first, and on T009)

**Checkpoint**: User Stories 1 and 2 both work independently - a correct extraction reaches the
Director, and the derived term reflects the real policy period even when an unrelated date sits
near the label.

---

## Phase 4: User Story 3 - The Director sees every stripped figure before he confirms (Priority: P1)

**Goal**: the confirmed reference's own cache carries the sanity pass's own warnings, and the
confirmation prompt gives them a distinct, hard-to-miss summary before the existing question.

**Independent Test**: construct a candidate carrying two warnings and assert the confirmation
prompt's own printed output contains a distinct, labeled warnings section, in addition to the full
JSON block, before the accept-correct-decline question. Confirm a candidate and assert the
resulting cache file's own JSON contains the same warnings list; assert a cache file written before
this feature existed still reads back with an empty warnings list.

### Tests for User Story 3 (write first)

- [x] T011 [P] [US3] `tests/test_policydoc.py`: write tests (to fail first) for the confirmed
  reference's own `warnings` field round-tripping through write/read, defaulting to an empty list
  when absent from an older cache file (spec FR-017, FR-018, SC-006)
- [x] T012 [P] [US3] `tests/test_policydoc.py`: write tests (to fail first) for the confirmation
  prompt's own new warnings section - printed before the existing JSON block and question when the
  candidate carries at least one warning, entirely absent when it carries zero (spec FR-019 through
  FR-021, SC-007)

### Implementation for User Story 3

- [x] T013 [US3] `headless/policydoc.py`: extend `PolicyReference` with `warnings`; update the
  write/read functions (and the provenance reader) to carry it through the existing round trip
  (spec FR-017, FR-018) (depends on T011 existing and failing first)
- [x] T014 [US3] `headless/policydoc.py`: extend `confirm_candidate` to print the warnings section
  ahead of the existing JSON block and question (spec FR-019 through FR-021) (depends on T012
  existing and failing first)
- [x] T015 [US3] `scripts/policy_extract.py`: pass the confirmed candidate's own warnings through
  to the constructed `PolicyReference` (depends on T013)

**Checkpoint**: User Stories 1 through 3 all work independently - a correct, verifiably-stripped-free
extraction reaches the Director, and he can see exactly what survived it before he decides.

---

## Phase 5: User Story 4 - The schema captures every field a real declarations page states (Priority: P2)

**Goal**: the extended candidate/policy shapes capture a policy-level deductible, a policy number,
explicit period dates, the insured asset, named insureds, excluded drivers, discounts, fees, and a
subtotal - each gated correctly - with no change to `headless/compare.py`'s own ranking outcome
except through the alias-table extension.

**Independent Test**: construct a synthetic fixture stating a policy-level deductible, a policy
number, an effective and expiration date, and a discount; assert the extended candidate captures
every one of them, that the figure-shaped ones pass through the corrected gate, that `term_months`
is computed from the two dates when both parse, and that every existing `headless/compare.py` test
still passes unchanged.

### Tests for User Story 4 (write first)

- [x] T016 [P] [US4] `tests/test_policydoc.py`: write tests (to fail first) for the ten new
  fields - a policy-level deductible, a policy number, an effective/expiration date pair that
  computes `term_months`, an asset (address, or vehicle plus VIN), `named_insureds`/
  `excluded_drivers`, discounts, fees, and subtotal - each new figure-shaped field subject to the
  corrected gate, each date subject to a date-parse check (spec FR-022 through FR-026, SC-008)
- [x] T017 [P] [US4] `tests/test_policydoc.py`: write a test (to fail first) confirming every new
  text field (`asset`, `named_insureds`, `excluded_drivers`, every entry `label`) is exempt from the
  sanity pass, mirroring spec 006's own insurer-name exemption test (spec FR-027)
- [x] T018 [P] [US4] `tests/test_compare.py`: write tests (to fail first) for the alias-table
  extension - a "Standard Collision"-shaped name into the existing `collision` key, a "Liability to
  Others"-shaped name into a new `personal_liability` key alongside a "Personal Liability"-shaped
  canonical phrasing, and the five other new homeowners keys - plus a regression test confirming
  "Personal Injury Protection (PIP)"-shaped phrasing already matches under the existing
  `medical_payments` alias with no table change needed (spec FR-030, FR-031, SC-009)

### Implementation for User Story 4

- [x] T019 [US4] `headless/policydoc.py`: extend `ExtractionCandidate` and the local-model
  extraction prompt with the ten new fields (spec FR-022, FR-023, FR-029); extend the sanity pass to
  gate the new figure-shaped fields (spec FR-025) and date-parse-check `effective_date`/
  `expiration_date` (spec FR-026); compute `term_months` from the two dates when both parse (spec
  FR-024) (depends on T016, T017 existing and failing first)
- [x] T020 [US4] `headless/capture.py`: extend `CurrentPolicy`'s `to_dict`/`from_dict` with the same
  ten fields, defaulting each to its own empty shape when absent from a corrected JSON document
  (spec FR-023) (depends on T019)
- [x] T021 [US4] `headless/compare.py`: extend `_ALIASES` per T018 (spec FR-030, FR-031) (depends
  on T018 existing and failing first)
- [x] T022 [P] [US4] Run the full existing `tests/test_compare.py` suite and confirm every
  pre-existing test still passes unchanged after T021 (spec FR-028, SC-009) - re-run this exact
  suite as part of this phase's own verification, not merely at final commit-gate time, since it is
  the one existing suite this feature's own alias-table change most directly risks breaking

**Checkpoint**: all four user stories are independently functional; the schema now captures what a
real declarations page states, and `headless/compare.py`'s own comparison outcome is unaffected
except through the alias-table extension.

---

## Phase 6: Cross-Cutting - Context-Window Guard (Priority: P2, no dedicated user story)

**Goal**: an explicit `num_ctx` value and a length-estimate warning close the silent-truncation gap
research.md D7 identifies. Not tied to any single numbered user story in spec.md - a standalone P2
hardening item alongside User Story 4.

- [x] T023 [P] `tests/test_localllm.py`: write tests (to fail first) for the `num_ctx` payload field
  and the length-estimate guard - a converted document short enough to pass unremarked, and one long
  enough to trigger the value-free warning naming only the estimated count and the threshold (spec
  FR-032)
- [x] T024 `headless/localllm.py`: add `num_ctx` to the request's own `options` object;
  `headless/policydoc.py`: add the length-estimate check against the de-glued text before the
  request is built (spec FR-032) (depends on T023 existing and failing first)

**Checkpoint**: the local-model request always states its own context window, and a document long
enough to risk silent truncation is flagged, never silently mishandled.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: docs of record, the orchestrator-run live-probe verification, and the commit gate.

- [x] T025 [P] `PATTERNS.md`: add one new entry, "Extraction fidelity: the corrected figure gate,
  term derivation, de-glue pass, visible warnings, and schema extension (v0.0.7, spec
  007-extraction-fidelity)," documenting each corrected mechanism and the schema/alias extensions -
  following this file's own established entry style exactly
- [x] T026 [P] `Project_Structure.md`: update the descriptions for `headless/policydoc.py`,
  `headless/compare.py`, `headless/localllm.py`, and `headless/capture.py`; append a new Changelog
  row for v0.0.7 following this file's own established row format exactly
- [x] T027 [P] `scripts/README.md`: update `policy_extract.py`'s own table row to mention the
  corrected pipeline and the new confirm-prompt warnings section
- [x] T028 [P] `MEMORY.md`: add a dated entry under "Open items" recording this feature's own
  delivery and the pending live-probe verification (T029) and Director UAT (T031)
- [x] T029 Run the read-only reviewer probe (quickstart.md Scenarios 1 and 2) against the
  Director's own three real declarations PDFs - **orchestrator-run, orchestrator-authorized within
  this implementation session (2026-08-30), COMPLETE**; a throwaway scratchpad script (never
  committed to this repository) converted each PDF with the real `pymupdf4llm` path, ran the
  corrected `derive_term_from_dates`, harvested each document's own coverage-table figures
  verbatim and fed them back through `apply_sanity_pass` alongside three deliberately hallucinated
  figures. Result, matching SC-005 exactly on all three: derived terms twelve, six, and twelve
  months respectively; zero verbatim source figures stripped as hallucinated on any of the three;
  every hallucinated figure correctly stripped (the anti-hallucination invariant held throughout).
  No real figure value left the scratchpad script; the paths themselves were never written into
  this repository. See `MEMORY.md`'s own dated entry.
- [x] T030 Run the full commit gate: `python -m pytest -q`, `python scripts/verify_structure.py`,
  `python scripts/scan_secrets.py --staged` - all three green, with zero real network calls, zero
  real local-model invocations, and zero real PDF file reads anywhere in the default suite (spec
  NFR-001, NFR-003, SC-010)
- [ ] T031 Run quickstart.md Scenarios 3 through 5 against the Director's own real declarations PDF,
  with his own Ollama running - **Director-only UAT, pending**; explicitly out of this delivery's own
  scope (research.md D9) and not performed by any automated task above

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: no dependencies - can start immediately; BLOCKS every user story
  (the de-glue transformation is read by the corrected term helper's own phrase check and by every
  generator)
- **User Story 1 (Phase 2)**: depends on Foundational; independent of every other user story's own
  implementation tasks
- **User Story 2 (Phase 3)**: depends on Foundational (needs de-glued text for phrase detection);
  independent of User Story 1's own implementation, though both touch the same file - sequential
  within `headless/policydoc.py`, safe to test in parallel
- **User Story 3 (Phase 4)**: depends on Foundational only; independent of User Stories 1 and 2
- **User Story 4 (Phase 5)**: depends on Foundational, User Story 1 (reuses the corrected gate for
  its own new figure-shaped fields), and User Story 2 (reuses the date-parsing helper for its own
  date-parse check) - the only user story with a real dependency on two others
- **Cross-cutting context guard (Phase 6)**: depends on Foundational only; independent of every user
  story
- **Polish (Phase 7)**: depends on all four user stories and the context guard being complete

### Within Each User Story

- Test tasks (marked `[P]`) before their own implementation task
- Tests MUST fail before the implementation task that makes them pass
- `headless/policydoc.py` implementation tasks are NOT marked `[P]` against each other within a
  phase (all touch the same file); test tasks across different files remain `[P]` against each other

### Parallel Opportunities

- T003 and T005 (User Story 1 tests) in parallel
- T007 and T008 (User Story 2 tests) in parallel
- T011 and T012 (User Story 3 tests) in parallel
- T016, T017, and T018 (User Story 4 tests, two different files) in parallel
- T025-T028 (Polish, independent files) in parallel

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (Foundational)
2. Complete Phase 2 (User Story 1)
3. **STOP and VALIDATE**: run `pytest -q -k policydoc` and confirm every corrected-gate test from
   T003 and T005 passes
4. Phases 3 through 6 harden and extend the MVP; none is required for User Story 1's own value to be
   real, but User Stories 2 and 3 are Priority P1 in `spec.md` and are expected before this feature is
   considered complete

### Incremental Delivery

1. Foundational -> the de-glue transformation is ready for every later phase
2. User Story 1 -> independently testable -> the audit's own most damaging defect (destroyed
   liability limits) is closed
3. User Story 2 -> independently testable -> a wrong derived term can no longer silently override a
   correct model claim
4. User Story 3 -> independently testable -> the Director can see exactly what survived extraction
   before he confirms
5. User Story 4 -> independently testable -> the schema is ready for a future comparison feature,
   with zero change to today's own ranking outcome
6. Context guard -> a long document's own silent-truncation risk is now a visible warning, not an
   invisible gap
7. Polish -> docs of record, the orchestrator-run live-probe verification (T029), the commit gate
   (T030), then Director UAT (T031, out of this delivery's own scope)

## Notes

- `[P]` tasks touch different files with no dependency on another unchecked task in this list
- `[Story]` maps a task to spec.md's own numbered user story for traceability
- Verify each test task's own test fails before writing the implementation task that follows it
- This delivery stops at spec authoring; T001 onward are for a future implementation delivery to
  execute, not for this session
- No merge task and no push task appear anywhere in this list, by this delivery's own brief
- Avoid: vague tasks, two tasks racing to edit the same file without a stated dependency,
  cross-story dependencies that would break either story's own independent testability beyond the
  one already named above (User Story 4's own dependency on User Stories 1 and 2)
