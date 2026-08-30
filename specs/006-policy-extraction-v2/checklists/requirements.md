# Specification Quality Checklist: Policy Extraction v2

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

- Validation pass 1 (2026-08-29): this specification names specific technical concepts directly
  in its requirements and success criteria - `pypdf`, a "layout-aware converter," an Ollama-shaped
  local-model request, `"think": false`, `HEADLESS_OLLAMA_URL`, `localhost`/`127.0.0.1`, and the
  literal provenance strings `"regex-v1"`/`"local-llm:<model-name>"`. As with spec 002's own
  precedent for "JWT" and "IBAN," and spec 005's own precedent for `Decimal`-only arithmetic and
  the `pypdf`-only extraction rule it is now amending, these name the substance of the requirement
  itself - what a candidate figure must be checked against, which endpoint may ever receive policy
  text, which literal flag prevents a verified empty-response failure mode - not an implementation
  choice being made casually in this document. `HEADLESS_PROFILE_DIR`-style environment variable
  names appear the same way spec 004's and 005's own checklists already accepted: as
  already-documented-by-convention facts (the new ones this feature adds are explicitly scoped as
  new in FR-006 and section 6 of `contracts/extraction-v2.md`), not undisclosed new configuration
  this document is trying to hide.
- Validation pass 2: the ten design decisions (D1-D10) this specification is built from were fixed
  by the Director before drafting began (per this feature's own brief) and are treated as settled
  inputs, not requirements this checklist re-litigates - `research.md` records each decision's own
  rationale and rejected alternatives, and `spec.md`'s own FR/SC numbering is a fresh, independent
  sequence for this feature (FR-001 through FR-029, SC-001 through SC-008, NFR-001 through
  NFR-004), not a continuation of spec 005's own numbering, since this is its own feature
  directory with its own acceptance surface.
- Validation pass 3: this specification **deliberately amends** an existing hard rule (spec 005's
  own FR-051, and the parallel clause in `CLAUDE.md`'s Secrets section and
  `.specify/memory/constitution.md`) rather than only adding new requirements alongside it.
  `plan.md`'s own Constitution Check section records this explicitly, including the drafted
  replacement wording and the version-bump call (MINOR, `1.3.1 -> 1.4.0`); applying that amendment
  to `CLAUDE.md` and the constitution distillation is `tasks.md` T037/T038, a future
  implementation-phase task, not something this spec-authoring pass performs itself. This is
  recorded here because a specification that recasts a governing rule, rather than only extending
  one, is exactly the kind of change a later reviewer should be able to find called out plainly,
  not discovered only by diffing `CLAUDE.md` after the fact.
- Validation pass 4: every fixture and example value named anywhere in `spec.md`, `research.md`,
  `data-model.md`, `contracts/extraction-v2.md`, and `quickstart.md` is wholly synthetic
  (`director@example.com`-class placeholders, or a generically-described scrambled-column artifact
  with no real date, dollar amount, policy number, or insurer name attached to it). No value,
  name, policy number, or premium from the Director's own real declarations PDF appears anywhere
  in this document set, consistent with this feature's own house rule and with this repository's
  standing public-repository hygiene requirement.
- All items pass. Ready for `/speckit-plan` review and, on a later delivery, `/speckit-tasks`
  execution and `/speckit-implement` - both already drafted in this same delivery per this
  feature's own brief, and both explicitly out of scope for this delivery to execute.
