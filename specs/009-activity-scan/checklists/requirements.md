# Specification Quality Checklist: Activity Scan

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

- Validation pass 1 (2026-09-09): like spec 005's and spec 007's own precedent, this
  specification names specific technical concepts directly in its requirements and success
  criteria - a selector's own role or attribute, `DEFAULT_QUERIES`, `matched_queries`, the
  literal field names on `Venue`. These name the substance of the requirement itself - which
  selector the scan depends on, which field a ranked report carries - not an implementation
  choice made casually in this document.
- Validation pass 2: this document is retro-documentation of an already-implemented,
  already-unit-tested feature (128 tests in `tests/test_activities.py` and
  `tests/test_activity_scan.py`), following the same `/retro-spec` discipline this repository
  already uses elsewhere in its own history. `tasks.md` records every implementation task as
  `[X]`, since the code and its tests exist in this worktree before this document set was
  written.
- Validation pass 3: no real personal address, no personal place name, and no household-role
  reference appears anywhere in this document set. The one worked example point,
  `42.4800,-83.3800`, and the area label `Farmington Hills, MI`, are used consistently across
  `spec.md`, `research.md`, `data-model.md`, and `quickstart.md` as a synthetic round-number
  point inside a public city - never described as, or traceable to, any real chosen point.
  `quickstart.md`'s own street-address example uses a placeholder ("1 Example Street"), matching
  the same placeholder this feature's own test suite already uses for a resolvable-address
  fixture. This validation also covers the test suite itself: `tests/test_activities.py` and
  `tests/test_activity_scan.py` name no real address, no personal place name, and no
  household-member role anywhere - their own example constant is
  `NEAR_POINT = (42.4800, -83.3800)`, the same synthetic round-number point, and their geocode
  fixture is the same four-decimal pair. `EXCLUDED_CATEGORY_TERMS` (`headless/activities.py`)
  checks a venue's category text against a small, named set of category words a Google Maps
  listing might carry, and excludes a match - a category word this scan checks for, never a
  reference to any real place.
- Validation pass 4: this specification does not amend any hard rule in `CLAUDE.md` or
  `.specify/memory/constitution.md`. It adds one new read-only errand and one new pure-logic
  module inside the existing package layout; `plan.md`'s own Constitution Check records every
  hard rule this feature touches as already satisfied by the errand's own read-only design.
- Validation pass 5: `spec.md`'s own success criteria distinguish what this repository's
  automated `pytest -q` suite proves (SC-001 through SC-010, every one already proven by an
  existing test) from the one outcome only a live recon session could prove (SC-011, the
  2026-09-09 recon against the real Google Maps, Yelp, and TripAdvisor pages) - the two are
  never conflated.
- Validation pass 6 (2026-09-09, after the first live scan): this document set was reconciled
  against the orchestrator's own post-scan ranking patch before being considered final - the
  `Venue.position`/`relevant` fields, the extended `EXCLUDED_CATEGORY_TERMS` list, `query_tokens`
  and `relevance_hit`, the position and relevance terms in `score_venue`, the single-place path
  (`read_single_place`, the viewport-coordinate fallback in `parse_place_href`), and the "Found
  via" report column. `tasks.md` records this patch's own tasks as `[X]`, alongside the original
  T001-T024. The test count above is corrected to 128 (up from the original 87, following an
  Opus verifier's own fix batch the same day - word-boundary category exclusion, the rewritten
  whole-word relevance rule, per-query and per-detail fail-soft reads, the unparseable-hours
  "unknown" case, the out-of-range-coordinate refusal, and the report file's chmod bracket, each
  covered by new tests), verified by running
  `pytest -q tests/test_activities.py tests/test_activity_scan.py` in this worktree.
- Validation pass 7 (2026-09-09, after a re-verification of the fix batch validation pass 6
  describes): a further batch of findings was applied, raising the test count from 128 to 140
  (verified by running `pytest -q tests/test_activities.py tests/test_activity_scan.py` in this
  worktree - 140 passed - and the full `pytest -q` suite - 789 passed, 9 skipped). Code changes:
  `KEPT_CATEGORY_TERMS` rewritten from the earlier bare, unqualified word "rental" to eight named
  activity-rental phrases, so "Tuxedo rental shop" and "Party rental store" no longer survive
  exclusion; `EXCLUDED_CATEGORY_TERMS`'s earlier, unhyphenated spelling of the coworking term
  corrected to "co-working";
  `relevance_hit`/`relevance_pattern` now return `None` (neutral, no score change) when no query
  that surfaced a venue carries a meaning-carrying token at all; `looks_like_coordinates`/
  `parse_near` now accept an optional leading "+" and an optional trailing ",<zoom>" or
  ",<zoom>z" (a pasted lat,lon,zoom triple); the per-query stdout lines now quote the query and
  the venue name with explicit single quotes rather than Python's own `repr`; and the report
  file's chmod bracket is now proven by a test that runs the scan twice over files chmod-ed to
  `0644` in between. This document set (`spec.md`, `plan.md`, `research.md` - new decisions
  D11-D13 - `data-model.md`, `contracts/scan-and-report.md`, `tasks.md` - new phases 10 and 11 -
  and this checklist, including the reworded validation pass 3 above, which no longer names the
  exclusion-term word directly) was reconciled against every one of these changes.
- All items pass. This document set records an already-shipped, already-tested feature; no
  further `/speckit-plan` or `/speckit-tasks` pass is expected to change its own scope.
