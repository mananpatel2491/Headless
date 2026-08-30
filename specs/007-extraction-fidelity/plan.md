# Implementation Plan: Extraction Fidelity

**Branch**: `v0.0.7` | **Date**: 2026-08-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-extraction-fidelity/spec.md`

## Summary

Fix four defects an independent audit probe-proved against three of the Director's own real
declarations PDFs in spec 006-policy-extraction-v2's own pipeline, and extend that pipeline's schema
and one alias table. Nothing in this feature touches spec 006's own constitutional floor: a local
model only, never cloud; a mechanical sanity pass before confirmation; and mandatory Director
confirmation before any cache write. The four fixes correct how that floor is enforced; they do not
change what the floor requires. Decisions are recorded in [research.md](research.md) (D1-D9).

## Technical Context

**Language/Version**: Python 3.14 (this worktree's own `.venv`, unchanged from spec 006 and every
prior feature in this repository).

**Primary Dependencies**: none new. This feature amends `headless/policydoc.py` and
`headless/localllm.py` (both already present, spec 006), and `headless/compare.py` (already
present, spec 005). No new entry in `requirements.txt`.

**Storage**: no new persisted directory. `reports/policy/<asset-key>.json` (spec 005, extended by
spec 006 with `generator`/`converter`) gains one additive field, `warnings` (FR-017), plus whichever
of the FR-022/FR-023 schema fields a given confirmed candidate actually carries.

**Testing**: `pytest>=8` (already a dependency). Every path this feature adds is exercised through a
synthetic fixture or an injectable fake in the default suite (spec NFR-001); the one verification
step that reads a real PDF (SC-005) is explicitly out of the automated suite (NFR-004) and is an
orchestrator-run, implementation-phase task (tasks.md), not something `pytest -q` ever executes.

**Target Platform**: macOS (this Director's own machine, unchanged from spec 006). Nothing in this
feature is platform-specific.

**Project Type**: package change only (`headless/policydoc.py`, `headless/compare.py`,
`headless/localllm.py`, `headless/capture.py` modified; no new module). No new errand, no new
browser surface, no new CLI flag on `scripts/policy_extract.py`.

**Performance Goals**: not a latency-sensitive path, unchanged from spec 006. The context-window
guard (FR-032) is a cheap length estimate on already-in-memory text, not a second model call.

**Constraints**: no candidate, from either generator, reaches the cache or the comparison engine
without the unchanged mandatory confirmation step (spec 006 FR-025, FR-026, untouched by this
feature); no policy document text or converted text ever reaches a non-local endpoint (spec 006
FR-007, FR-029, untouched); every fixture and example in this feature's own document set and test
suite is wholly synthetic (NFR-002).

**Scale/Scope**: unchanged from spec 006 - one Director, per-asset one-shot extraction, no
concurrency, no batching.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Unlike spec 006, this feature does **not** recast any hard rule's own substance - it corrects how an
already-approved rule is enforced (the sanity pass still strips a figure absent from the source; the
term helper still derives from policy-period dates; confirmation is still mandatory) and extends an
additive schema. No `CLAUDE.md` or `.specify/memory/constitution.md` wording change is required.

| Principle / Hard Rule | Status | Notes |
| :--- | :--- | :--- |
| I. Context-First Architecture Map | Pass (planned) | `Project_Structure.md` gains an updated description for `headless/policydoc.py`, `headless/compare.py`, `headless/localllm.py` and a new Changelog row - a `tasks.md` polish-phase task, not applied by this spec-authoring pass |
| II. Pattern Reference Integrity | Pass (planned) | `PATTERNS.md` gains one new entry documenting the corrected gate, the corrected term helper, the de-glue pass, the visible warnings, and the schema/alias extensions - a `tasks.md` task |
| III. Automated Maintenance via Agentic Skills | Pass | No new script; `scripts/policy_extract.py`'s own CLI surface and exit codes are unchanged |
| IV. Continuous Errand Validation | Pass | Every corrected or new code path gets a unit test, written to fail first, per `tasks.md`'s own tests-first ordering; `pytest -q`, `verify_structure.py`, and `scan_secrets.py --staged` continue to gate every commit unchanged |
| V. Infrastructure-as-Code and Cost Gating | Pass, trivially | No cloud resource of any kind; Ollama continues to run entirely on the Director's own machine at $0/month |
| **Secrets Hard Rule: "extraction may attempt a local-only model... no candidate ever reaches the cache... without passing the mechanical sanity pass... and mandatory Director confirmation"** (spec 006's own recast, `CLAUDE.md` Secrets section) | Unaffected | This feature corrects the sanity pass's own internal check (FR-001 through FR-011) and adds a confirm-prompt visibility improvement (FR-017 through FR-021); it does not change the rule's own two gates (sanity pass, then mandatory confirmation), so no further constitutional wording change is needed |
| **Registry Hard Rule: "a script may type a value only if it exists in the profile registry"** | Unaffected | Unchanged by this feature; no new typed value anywhere |

No amendment is drafted for this feature; the Complexity Tracking table below is intentionally
empty for the same reason.

## Project Structure

### Documentation (this feature)

```text
specs/007-extraction-fidelity/
├── plan.md              # This file
├── research.md          # D1-D9, evidence (structural, no real values)
├── data-model.md         # Extended candidate/CurrentPolicy/cache shapes, gate token semantics,
│                          # term-derivation state machine, de-glue rules
├── contracts/
│   └── fidelity.md       # Normative tables: gate rules, term-derivation rules, de-glue
│                          # transformations, new schema fields, cache compatibility, num_ctx
│                          # guard, confirm-prompt warning display format
├── quickstart.md          # The Director's later re-extraction session steps (out of delivery),
│                          # plus the reviewer's own probe expectations (terms only, no values)
├── tasks.md               # Tests-first task breakdown; no merge/push tasks
└── checklists/
    └── requirements.md    # Specification quality checklist
```

### Source code (repository root)

```text
headless/
├── policydoc.py          # MODIFIED: _figure_present/_source_digit_tokens rewritten to
│                          # per-token membership on both sides (FR-001, FR-002); _find_period_dates
│                          # rewritten to scan every label occurrence and window after-only
│                          # (FR-006, FR-007); derive_term_from_dates extended to collect every
│                          # date and use max-minus-min (FR-008); a new de-glue function
│                          # (FR-012 through FR-016); ExtractionCandidate/CurrentPolicy/
│                          # PolicyReference extended (FR-017, FR-022, FR-023); confirm_candidate
│                          # extended to print the warnings section (FR-019, FR-020); the
│                          # extraction prompt extended (FR-029)
├── localllm.py            # MODIFIED: `options` gains `num_ctx` (FR-032); a length-estimate guard
│                          # against the converted text
├── compare.py              # MODIFIED: alias table extended (FR-030); every new schema field
│                          # ignored except through the extended alias table (FR-028)
└── capture.py               # MODIFIED (minimal): `CurrentPolicy` gains the FR-022/FR-023 fields
                            # in its own `to_dict`/`from_dict`

scripts/
└── policy_extract.py     # UNCHANGED: no new CLI flag, no exit-code change

requirements.txt          # UNCHANGED: no new dependency

tests/
├── test_policydoc.py      # MODIFIED: new tests for the corrected gate, the corrected term
│                          # helper, the de-glue pass, the visible warnings, and the schema
│                          # extension - each against a wholly synthetic fixture
├── test_compare.py         # MODIFIED: new tests for the alias-table extension; every existing
│                          # test continues to pass unchanged
├── test_localllm.py        # MODIFIED: new tests for the `num_ctx` payload field and the
│                          # length-estimate guard
├── test_policy_extract.py  # MODIFIED (minimal, if the cached-file shape assertions need updating
│                          # for the new `warnings` field)
└── fixtures/
    └── (wholly synthetic fixtures reproducing each defect's own structural shape - no real value,
       name, policy number, or premium)

PATTERNS.md, Project_Structure.md, MEMORY.md, scripts/README.md   # MODIFIED: docs of record
                                                                   # (tasks.md polish phase)
```

**Structure Decision**: single project, same layout every prior feature in this repository uses. No
new top-level directory, no new module - every change lands inside a file spec 005 or spec 006
already created.

## Complexity Tracking

*No entry.* This feature records no constitutional deviation - see Constitution Check, above.
