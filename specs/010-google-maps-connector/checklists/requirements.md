# Specification Quality Checklist: Google Maps Connector

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-09
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Validation pass 1 (2026-09-09): like spec 009's own precedent, this specification names
  specific technical concepts directly in its requirements and success criteria - a JSON-RPC
  field name, `CheckOutcome`'s own dataclass fields, a Terraform resource address. These name
  the substance of the requirement itself - which server this repository registers, which fields
  a check result carries - not an implementation choice made casually in this document.
- Validation pass 2: this document is retro-documentation of an already-implemented,
  already-unit-tested feature (25 tests in `tests/test_maps_check.py`), following the same
  `/retro-spec` discipline this repository already uses elsewhere in its own history (spec 009).
  `tasks.md` records every implementation task as `[X]`, since the code, `.mcp.json`, and the
  terraform declaration exist in this worktree before this document set was written.
- Validation pass 3: no real API key value appears anywhere in this document set. Every example
  key value is an obviously synthetic placeholder (`"k-test"`, `"k-secret-value"`, matching the
  test suite's own fixtures); the only key text used in prose is the literal placeholder
  `${HEADLESS_MAPS_API_KEY}` or the words "the key". No phone number, email address, street
  address, or household reference appears anywhere in this document set either.
- Validation pass 4: this specification does not amend any hard rule in `CLAUDE.md` or
  `.specify/memory/constitution.md`. It adds one registration file, one pure-logic module, one
  maintenance script, and one small Terraform declaration inside the existing package layout;
  `plan.md`'s own Constitution Check records every hard rule this feature touches as already
  satisfied, including the one documented, deliberate exception (the key's home is the Keychain,
  not the age vault - research.md D3).
- Validation pass 5: `spec.md`'s own success criteria distinguish what this repository's
  automated `pytest -q` suite proves (SC-001 through SC-005, every one already proven by an
  existing test, `urllib.request.urlopen` stubbed throughout) from what only a live run against
  the real hosted endpoint could prove (SC-006, the 2026-09-09 no-key live run recorded in
  MEMORY.md) and what only `terraform validate` could prove (SC-007) - the three are never
  conflated.
- Validation pass 6: no resource under `terraform/` was created, and no `terraform apply` was
  run, by the session that wrote this document set - `terraform validate` only. Every Director
  action this feature still needs (pick the project, `terraform plan`/`apply`, store the key,
  export it, approve the server, acknowledge the terms) is recorded as pending in `MEMORY.md`'s
  Open items, not claimed as complete here.
- All items pass. This document set records an already-shipped, already-tested feature; no
  further `/speckit-plan` or `/speckit-tasks` pass is expected to change its own scope. The
  Director's own remaining actions (terraform apply, the key, the approval prompt, the terms
  acknowledgment) are operational follow-through, not a specification gap.
