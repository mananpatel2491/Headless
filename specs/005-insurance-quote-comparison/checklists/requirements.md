# Specification Quality Checklist: Insurance Quote Comparison

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-25
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

- Validation pass 1 (2026-08-25): the draft names `FieldPlan`, `ClickStep`, `HumanStep`,
  `CaptureStep`, `#zipCode_mma`, `#qsButton_mma`, and `registry:address.home.zip` directly in the
  requirements, acceptance scenarios, and success criteria. These are the substance of what this
  feature verifiably guarantees (a walk's exact step vocabulary, the two selectors actually
  verified before this feature was scoped) and not an implementation choice being smuggled into
  the document - the same reasoning spec 004's own checklist gave for keeping `age`, `getpass`,
  and `/dev/tty` in its own requirements, and spec 003's for keeping `chromium_sandbox` and a
  cookie's `expires` marker in its own. `insurers` and `current_policy` also appear naming newly
  introduced vault items, not incidental configuration this feature could have designed away
  (spec 004's own precedent for `HEADLESS_AGE_FILE`).
- Validation pass 2: the spec's Non-Functional Requirements subsection (NFR-001 through NFR-004)
  exists for the same reason spec 003's and spec 004's own NFR subsections do - properties named in
  this feature's brief (a report that renders with zero external requests; a unit suite with zero
  browser launches and zero passphrase prompts; every message this feature adds being provably
  value-free; one insurer's failure never propagating past the orchestrator's own loop) that do
  not read naturally as user-facing functional behavior but are still testable, measurable
  constraints. Keeping them separate from the numbered Functional Requirements list keeps that
  list's numbering aligned one-to-one with concrete, user-observable behavior.
- Validation pass 3: FR-020 (no LLM call anywhere in the comparison engine's path) was checked
  against the "no implementation details" criterion specifically, since "no LLM" names a class of
  implementation technique rather than a system behavior on its face. It stays as a Functional
  Requirement, not an Assumption, for the same reason spec 004's own checklist kept FR-023 (never
  store a password or a card value) as a requirement rather than an assumption: it is directly
  testable (does a rendered report's every figure trace back to a capture file or `current_policy`,
  or not) and is the single most safety-critical requirement in this specification, extending the
  constitution's own existing "nothing an LLM derives is ever typed" rule to a second surface
  (reading and comparing) this feature is the first to touch - demoting it to an assumption would
  understate its weight relative to, for example, spec 004's own FR-019 ("list never prints a
  value")-shaped siblings elsewhere in this repository's own prior specs.
- Validation pass 4: FR-010 (no submit/pay/verify/otp step type, ever, in this walk or any future
  insurer walk built on this framework) was checked for scope creep beyond what this delivery
  itself can enforce - a future spec 006 or later, adding a second insurer's walk, is technically
  free to add whatever step type it wants unless this framework itself structurally prevents it.
  The requirement is phrased as a constraint on the framework this delivery ships (`Step`'s closed,
  four-member union has no submit-shaped member and cannot silently grow one without a new spec
  explicitly widening it), not as an unenforceable promise about specs this delivery does not
  control - matching how the existing constitution's own "no `--submit` flag exists or may be
  added" rule is similarly a constraint on the gates module's own closed set of modes, not a
  promise about code nobody has written yet.
- Validation pass 5: cross-checked every User Story's Acceptance Scenario against a corresponding
  Functional Requirement and, where measurable, a Success Criterion, mirroring spec 003's and spec
  004's own final validation passes. No requirement traces to zero scenario; no scenario traces to
  zero requirement. One deliberate asymmetry, noted rather than silently left: User Story 4's
  Acceptance Scenario 3 (freshest-capture-wins across runs) and Edge Cases' matching entry both
  trace to FR-021, but the *unit-level* proof of that specific scenario is deferred to a
  fixture-driven orchestrator test (tasks.md T038) rather than being its own numbered SC, since
  SC-005 and SC-007 already cover the two closely related mechanisms (failure isolation, unmapped
  rows) this scenario's own test builds on incrementally - adding a fourth, narrowly overlapping
  SC for the same test file was judged to add numbering noise without adding a distinct, checkable
  guarantee beyond what T038 itself already states plainly. All items otherwise pass. Ready for
  `/speckit-plan` (already produced in this same delivery, per this feature's brief) and, on a
  later, separately authorized run, `/speckit-tasks` (also already produced in this delivery,
  ahead of the usual sequencing, per this feature's brief's explicit file-set instruction) and
  `/speckit-implement`.
- Validation pass 6 (post-Director-amendment, 2026-08-25): three amendments were folded into this
  already-drafted spec set mid-delivery - `scripts/vault.py get NAME` (FR-037 through FR-039), the
  registry shape restructure (spec.md's Assumptions and Out of Scope sections, research.md D11),
  and `identity.currently_insured` joining the Progressive walk (FR-035, FR-036). Checked each
  against the same content-quality criteria as the original draft: FR-037 through FR-039 describe
  already-shipped, externally-verified behavior (a specific merge and commit hash, research.md
  D12) rather than a testable requirement this delivery's own tasks.md builds - this is noted
  explicitly in each FR's own status line and in tasks.md's own "Status" preamble, so a reader does
  not mistake a fact-of-record for an open implementation item; the two new Success Criteria
  (SC-014, SC-015) stay in scope because they are checkable claims *about this delivery's own
  code* (nothing under `headless/` calls `get`; no shipped step references `spouse.`/
  `property.rental.`), not claims about the already-shipped `vault.py` code itself. FR-035's
  registry path and field-kind choice (`select` or `check`, whichever recon finds) is deliberately
  left open rather than guessed, consistent with FR-032's existing "unproven selector never ships"
  discipline - the same reasoning that already governs every other selector past the landing page.
  All items otherwise still pass.
- Validation pass 7 (post-Director-amendment, 2026-08-25, rounds 4-8): four further amendments
  landed after pass 6 - the Director's actual live profile schema (three JSON arrays plus
  `feature_configs`, superseding an intermediate nested-block proposal), a further schema
  finalization (`profile.template.json` as the enforced contract, nested `licence`, `dwelling_type`,
  the `"work"` address type), the deletion of hand-typed `current_policy` in favor of per-asset
  `policy_doc` PDF extraction plus mandatory Director confirmation (a genuinely new deliverable,
  FR-050 through FR-060), the `"n/a"` exclusion sentinel (FR-061 through FR-066), and two further
  already-shipped-elsewhere vault CLI amendments (`vault.py verify`, FR-039b). Checked each against
  the same criteria as prior passes: FR-011 through FR-013 were rewritten in place a second time
  (not a third, contradicting FR block appended) for the same reason pass 5's own note gives -
  one authoritative statement per requirement, not two under different numbers. FR-050 through
  FR-060's own "mandatory confirmation" language was checked against "no implementation details" -
  it stays as a functional requirement rather than a design note because the confirm-or-decline
  behavior is directly user-observable and testable (SC-019), the same reasoning that kept FR-020's
  "no LLM" rule a requirement rather than an assumption. The `"n/a"` sentinel's own FR-061 defines a
  data convention rather than a system behavior on its face; kept as a requirement because every
  consumer's treatment of it is independently testable (FR-062/FR-063 each have their own SC).
  All items otherwise still pass. Every quickstart scenario number was re-verified against
  tasks.md's own T025/T043/T052 cross-references after two internal renumbering passes (one to
  correct a dropped scenario, one to keep Scenario 3/5/7 stable); the final numbering (1-15) is
  believed consistent throughout this spec set as of this delivery, though the sheer number of
  amendment rounds folded into one drafting session (eight) is itself worth a verifier's own
  independent cross-reference pass before this spec set is treated as final.
