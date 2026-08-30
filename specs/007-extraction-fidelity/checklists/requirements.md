# Specification Quality Checklist: Extraction Fidelity

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-29
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

- Validation pass 1 (2026-08-29): like spec 006's own precedent (and spec 002's before it), this
  specification names specific technical concepts directly in its requirements and success criteria
  - a digit-run token, a policy-period label, a "N-month"/"N month" phrase, `num_ctx`, and the
    literal field names `policy_number`/`effective_date`/`expiration_date`/
    `policy_level_deductibles`/`asset`/`named_insureds`/`excluded_drivers`/`discounts`/`fees`/
    `subtotal`. As with spec 006's own precedent for `pypdf`, a "layout-aware converter," and
    `HEADLESS_OLLAMA_URL`, these name the substance of the requirement itself - which check a
    proposed figure must pass, which window a date scan may search, which field a new schema slot
    is called - not an implementation choice made casually in this document.
- Validation pass 2: the nine design decisions (D1-D9) this specification is built from were fixed
  by the Director's own approved fix/extension plan before drafting began (per this feature's own
  brief) and are treated as settled inputs, not requirements this checklist re-litigates -
  `research.md` records each decision's own rationale and rejected alternatives, and `spec.md`'s own
  FR/SC numbering is a fresh, independent sequence for this feature (FR-001 through FR-032, SC-001
  through SC-011, NFR-001 through NFR-004), not a continuation of spec 006's own numbering, since
  this is its own feature directory with its own acceptance surface. Every place this specification
  amends a specific spec 006 requirement names that requirement by number (FR-017 through FR-021 for
  the sanity pass; FR-019 through FR-021 for the term-derivation window and override), so a later
  reader can trace exactly what changed and why without diffing the two feature directories by hand.
- Validation pass 3: unlike spec 006, this specification does **not** amend any hard rule in
  `CLAUDE.md` or `.specify/memory/constitution.md` - `plan.md`'s own Constitution Check records this
  explicitly. The corrected sanity pass still strips a figure absent from the source; the corrected
  term helper still derives from policy-period dates; the confirmation step is still mandatory before
  any cache write. This specification corrects how an already-approved rule is enforced, not what the
  rule itself requires, so no constitutional wording change is drafted here, unlike spec 006's own
  MINOR version bump.
- Validation pass 4: every fixture and example value named anywhere in `spec.md`, `research.md`,
  `data-model.md`, `contracts/fidelity.md`, and `quickstart.md` is wholly synthetic or a structural,
  reconstructed shape standing in for what the audit actually observed (`"<amount> each
  person/<amount> each accident"`-shaped composite figures, `"NNN NNN NNN"`-shaped spaced
  identifiers, `"Total6month"`-shaped glued phrases). No real figure, premium, limit, policy number,
  person name, address, VIN, or real PDF filesystem path from the Director's own three audited
  documents appears anywhere in this document set - consistent with this feature's own NFR-002 and
  this repository's standing public-repository hygiene requirement (`headless_public_repo_hygiene`
  memory entry).
- Validation pass 5: this specification's own success criteria distinguish what this repository's
  automated `pytest -q` suite can assert (SC-001 through SC-004, SC-006 through SC-011, every one
  proven by a synthetic fixture) from what only an orchestrator-run, read-only session against the
  Director's own real PDFs can prove (SC-005) - the two are never conflated, and NFR-004 states
  plainly that the automated suite never attempts SC-005 itself. This mirrors spec 006's own
  NFR-002/opt-in-integration-test split between a synthetic default suite and a real-model
  verification step gated behind an explicit environment variable, adapted here to a read-only
  document probe instead.
- All items pass. Ready for `/speckit-plan` review and, on a later delivery, `/speckit-tasks`
  execution and `/speckit-implement` - both already drafted in this same delivery per this feature's
  own brief, and both explicitly out of scope for this delivery to execute.
