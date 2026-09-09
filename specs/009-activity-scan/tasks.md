---

description: "Task list for feature 009 Activity Scan"

---

# Tasks: Activity Scan

**Input**: Design documents from `/specs/009-activity-scan/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/scan-and-report.md,
quickstart.md

**Tests**: REQUIRED by the specification (NFR-001, and SC-001 through SC-010 each name a
unit-test-provable outcome). Every test in `tests/test_activities.py` and
`tests/test_activity_scan.py` already exists and passes.

**Organization**: tasks are grouped by user story so each story is independently implementable
and testable, per this repository's own `tasks-template.md` convention.

**Status**: IMPLEMENTED (already-built feature; this delivery documents it as a Spec Kit set).
T001 through T019 and T025 through T029 reflect code and tests already present in this worktree
(`headless/activities.py`, `scripts/activity_scan.py`, `tests/test_activities.py`,
`tests/test_activity_scan.py`), the latter range being the orchestrator's own post-scan ranking
patch. T036 through T051 (Phases 10 and 11) record an Opus verifier's own fix batch and a
subsequent re-verification's own further fix batch, both also already present in this worktree.
This delivery's own new work is the document set itself (T020 through T024, then T030 onward)
plus the docs-of-record updates, now reconciled a second time against Phases 10 and 11 - the two
new test modules hold 140 tests (`pytest -q tests/test_activities.py tests/test_activity_scan.py`),
and the whole suite is 789 passed, 9 skipped. No `.py` file is touched by this delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on another unchecked task)
- **[Story]**: which user story this task belongs to (US1, US2, US3, US4), or unmarked for
  Foundational/Cross-cutting/Polish
- Every task names its own exact file path

## Path Conventions

Single project at the repository root: `headless/` (the package this feature adds a module to),
`scripts/` (the new errand), `tests/` (pytest). All paths below are relative to the worktree root
`../worktrees/Headless/v0.0.9/`.

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: the parsers, geography, and shape definitions every user story's own logic reads.

- [x] T001 [P] `headless/activities.py`: define `Venue`, `DAYS`, `EXCLUDED_CATEGORY_TERMS`,
  `DEFAULT_QUERIES`, and the live selector constants (`FEED_SELECTOR`, `PLACE_LINK_SELECTOR`,
  `RATING_SELECTOR`, `HOURS_ROW_SELECTOR`, `WEBSITE_SELECTOR`, `PHONE_SELECTOR`,
  `ADDRESS_SELECTOR`, `END_OF_LIST_TEXT`, `CHECK_SELECTORS`)
- [x] T002 [P] `tests/test_activities.py`: unit tests for the card, rating-label, hours-text,
  weekly-rows, and geocode-response parsers (`parse_card_lines`, `parse_rating_label`,
  `parse_hours_text`, `parse_weekly_rows`, `parse_geocode_response`, `parse_place_href`,
  `parse_near`, `strip_prefix`)
- [x] T003 [P] `headless/activities.py`: implement those same parsers, plus `haversine_miles`,
  `estimate_drive_minutes`, `nominatim_url`, `search_url`, `window_minutes`, `overlap_minutes`

**Checkpoint**: every later phase can call a tested parser or a tested geography function with no
further wiring of its own.

---

## Phase 2: User Story 1 - The Director scans a point and gets ranked venues (Priority: P1) 🎯 MVP

**Goal**: the scan searches, folds, locates, excludes, scores, enriches, re-ranks, and reports.

**Independent Test**: stub the two browser-reading functions with fixed venue lists and run the
script end to end; assert the report contains the kept venue, excludes the ruled-out one, and
ranks by score.

### Tests for User Story 1

- [x] T004 [P] [US1] `tests/test_activities.py`: tests for `apply_day_window`
  (closed/open/partial/unknown, including a day missing from `weekly_hours`), `score_venue` (the
  Bayesian shrink, the distance penalty, the day-window adjustment), `fold_duplicates`
  (sponsored-vs-organic preference, `matched_queries` union), `is_excluded`, and `rank` (excluded
  and out-of-radius venues dropped, remainder sorted)
- [x] T005 [P] [US1] `tests/test_activities.py`: tests for `render_markdown` and `render_json`
  (the "Top picks overall" and per-tag sections, an unrated/no-website venue's own fallback text)
- [x] T006 [P] [US1] `tests/test_activity_scan.py`: `FakeSession`/`FakePage` fixtures, and a test
  that a full scan run (with `read_search_page`/`read_place_page` stubbed) writes exactly one
  Markdown and one JSON report file, that an excluded-category venue never reaches either, and
  that a scored venue's `day_status`/`window_overlap_minutes` match its stubbed hours

### Implementation for User Story 1

- [x] T007 [US1] `headless/activities.py`: implement `apply_day_window`, `score_venue`,
  `fold_duplicates`, `is_excluded`, `rank`, `locate`, `render_markdown`, `render_json` (depends
  on T004, T005 existing and passing)
- [x] T008 [US1] `scripts/activity_scan.py`: implement `_scroll_feed_to_end`, `read_search_page`,
  `read_place_page`, `_settle`, and `run_scan` - the search-fold-locate-rank-detail-rerank-render
  pipeline (depends on T006 existing and passing, and on T007)
- [x] T009 [US1] `scripts/activity_scan.py`: wire the module docstring,
  `HANDOFF = "n/a (read-only errand)"`, and the argument parser's
  `--near`/`--area`/`--day`/`--start`/`--end`/`--radius-miles`/`--details` flags (depends on
  T008)

**Checkpoint**: User Story 1 is independently functional - a scan against stubbed browser reads
produces a correct, ranked, two-file report.

---

## Phase 3: User Story 2 - The Director points the scan at a plain address (Priority: P1)

**Goal**: `--near` resolves through Nominatim when it is not a coordinate pair, and a resolution
failure refuses before any browser session opens.

**Independent Test**: call the resolver with a fixture address and a stubbed HTTP fetch; assert
the expected point comes back, and that a fetch failure returns `None` rather than raising.

### Tests for User Story 2

- [x] T010 [P] [US2] `tests/test_activity_scan.py`: tests for `resolve_near` (a coordinate pair
  short-circuits with no fetch call; an address calls the injected `fetch`; a fetch exception or
  an empty geocode result returns `None`) and for the CLI refusing before any `Session` is
  constructed on an unresolvable `--near`

### Implementation for User Story 2

- [x] T011 [US2] `scripts/activity_scan.py`: implement `resolve_near` and `_fetch` (a
  `urllib.request` call with the fixed User-Agent), and wire `main`'s own refusal path when
  resolution fails (depends on T010 existing and passing)

**Checkpoint**: User Stories 1 and 2 both work independently - the Director can give either a
coordinate pair or an address, and a bad address refuses cleanly.

---

## Phase 4: User Story 3 - The Director checks the scan's own selectors (Priority: P2)

**Goal**: `--check` probes the dependent selectors read-only, against one search page, and never
scrolls, enriches, or writes a report.

**Independent Test**: stub the session's `probe` call to report every selector but one as found;
assert the summary line names the correct counts and that no report file is written.

### Tests for User Story 3

- [x] T012 [P] [US3] `tests/test_activity_scan.py`: a test that `--check` navigates to the first
  query's own search URL only, prints `CHECK <n> found, <m> missing`, and constructs the
  `Session` in `Mode.PREVIEW`

### Implementation for User Story 3

- [x] T013 [US3] `scripts/activity_scan.py`: implement `run_check` and wire the `--check` flag
  into `main` (depends on T012 existing and passing)

**Checkpoint**: User Stories 1 through 3 all work independently - a Director can verify the
scan's own health before trusting a real run.

---

## Phase 5: User Story 4 - The Director substitutes his own list of queries (Priority: P2)

**Goal**: `--queries-file` fully replaces `DEFAULT_QUERIES`; an untagged line defaults to
`"custom"`.

**Independent Test**: a fixture file with a tagged line, a comment, a blank line, and an
untagged line; assert the loader keeps only the tagged and untagged lines, defaulting the latter
to `"custom"`.

### Tests for User Story 4

- [x] T014 [P] [US4] `tests/test_activity_scan.py`: tests for `_load_queries` (default list when
  no path given; a file's own tagged and untagged lines; comments and blank lines skipped)

### Implementation for User Story 4

- [x] T015 [US4] `scripts/activity_scan.py`: implement `_load_queries` and wire the
  `--queries-file` flag into `main` (depends on T014 existing and passing)

**Checkpoint**: all four user stories are independently functional.

---

## Phase 6: Cross-Cutting - Refusals, Exit Codes, and the Read-Only Guarantee

**Goal**: `--apply` is always refused before any session; a malformed window refuses; an
unhandled exception exits 2 with a value-free message.

- [x] T016 [P] `tests/test_activity_scan.py`: a test that `--apply` refuses before any `Session`
  is constructed (`RefusingSession`, an assertion double that raises if constructed)
- [x] T017 [P] `tests/test_activity_scan.py`: a test that identical `--start`/`--end` refuses with
  no `Session` constructed
- [x] T018 [P] `tests/test_activity_scan.py`: a source-level test
  (`test_no_apply_help_and_no_submit_anywhere`) confirming no submit/pay/confirm/OTP token
  appears anywhere in `scripts/activity_scan.py`
- [x] T019 `scripts/activity_scan.py`: implement `main`'s own refusal-before-session ordering and
  the exit-code table (1 for a refusal, 2 for a usage error or an unhandled exception, 0
  otherwise) (depends on T016, T017, T018 existing and passing)

**Checkpoint**: the read-only guarantee is proven, not merely stated - every refusal path is
exercised by a test that never constructs a real session.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: docs of record and the commit gate.

- [x] T020 [P] `PATTERNS.md`: append one new entry recording the selector choice, the read-only
  posture, and the recon findings (v0.0.9, spec 009-activity-scan)
- [x] T021 [P] `Project_Structure.md`: extend the `headless/` and `reports/` row text, add a
  `scripts/activity_scan.py` row, and append one new Changelog row for v0.0.9
- [x] T022 [P] `scripts/README.md`: add an Errands table row for `activity_scan.py`
- [x] T023 [P] `Function_Mapping.md`: add a table row for `scripts/activity_scan.py`
- [x] T024 Run the full commit gate: `python -m pytest -q`, `python scripts/verify_structure.py`,
  `python scripts/scan_secrets.py --paths <every file this delivery wrote or edited>` - all
  green, with zero real network calls and zero real browser launches anywhere in the default
  suite (spec NFR-001, SC-001)

---

## Phase 8: Ranking Patch and the Single-Place Path (after the first live scan, 2026-09-09)

**Purpose**: the orchestrator's own post-scan patch to `headless/activities.py` and
`scripts/activity_scan.py`, made after the first live scan surfaced loosely related results deep
in several queries' own result lists, and one query ("Topgolf") that Google answered by opening a
place page directly (research.md D9, D10).

- [x] T025 [P] `headless/activities.py`: add `Venue.position` (a card's own 0-based place in its
  query's result list) and `Venue.relevant` (unset until ranked); extend
  `EXCLUDED_CATEGORY_TERMS` from four movie/dinner terms to the full retail, venue-for-hire,
  trade-service, and kid-only list; add `_GENERIC_QUERY_WORDS`, `query_tokens`, and
  `relevance_hit`
- [x] T026 [P] `headless/activities.py`: update `score_venue` to subtract `0.015` per known
  `position` and add `0.35`/subtract `0.25` for `relevant`; update `fold_duplicates` to keep the
  lower of two copies' own `position`; add the `/@<lat>,<lon>,` viewport fallback to
  `parse_place_href`; add the "Found via" column (the first two of `matched_queries`) to
  `render_markdown`'s tables
- [x] T027 [P] `tests/test_activities.py`: tests for `query_tokens`, `relevance_hit`, the
  position and relevance terms in `score_venue`, the extended `EXCLUDED_CATEGORY_TERMS`, the
  position tie-break in `fold_duplicates`, the viewport fallback in `parse_place_href`, and the
  "Found via" column in `render_markdown`
- [x] T028 [P] `scripts/activity_scan.py`: number each card's own `position` in
  `read_search_page`; add `read_single_place` (name from the page title, coordinates from the
  URL's own viewport, rating from the header's star label, then the same place-page detail read
  as any other venue); wire the no-feed / `/maps/place/` branch into `run_scan`, printing
  `1 result (Google opened the place directly)`; raise `--details`'s own default from 30 to 60
- [x] T029 [P] `tests/test_activity_scan.py`: a test that a query answered with a place page
  directly (no results feed, a `/maps/place/` URL) is read through `read_single_place` and
  reported with the `1 result (Google opened the place directly)` line

**Checkpoint**: the ranking patch and the single-place path are proven by test, and the code these
tasks describe is what every later phase's own documentation now matches exactly.

---

## Phase 9: Documentation Reconciliation (this delivery)

**Purpose**: bring every document of record in line with the Phase 8 patch, which this Spec Kit
set had not yet reflected.

- [x] T030 [P] `specs/009-activity-scan/spec.md`: add FR-031 through FR-034 (position, relevance,
  the single-place path, the viewport-coordinate fallback), update FR-005/FR-007/FR-009/FR-011/
  FR-016 in place, add SC-012/SC-013, add the single-place edge case, and correct the test count
  to 128 (following the Opus verifier's own later fix batch)
- [x] T031 [P] `specs/009-activity-scan/research.md`: add D9 (relevance and list-position terms,
  extended exclusions) and D10 (a query that opens one place directly)
- [x] T032 [P] `specs/009-activity-scan/data-model.md`, `contracts/scan-and-report.md`: the two
  new `Venue` fields, the single-place pipeline step, the relevance step before scoring, the
  "Found via" column, the `--details` default, and the `position`/`relevant` JSON keys
- [x] T033 [P] `specs/009-activity-scan/quickstart.md`, `plan.md`,
  `checklists/requirements.md`, `research.md`: the `--details` default (including D6's own stated
  default), the D1-D10 count, and the corrected test count
- [x] T034 [P] `PATTERNS.md`, `Project_Structure.md`, `scripts/README.md`,
  `Function_Mapping.md`: the final scoring rule, the extended exclusion families, the
  single-place path, and the `--details` default, wherever each already states one of these
- [x] T035 Run the full commit gate again: `python -m pytest -q`, `python
  scripts/verify_structure.py`, `python scripts/scan_secrets.py --paths <every file this
  delivery edited>`

---

## Phase 10: Opus Verifier Fix Batch (first pass, 2026-09-09)

**Purpose**: an Opus verifier's own review of the code and tests Phases 1 through 9 shipped
found the issues this phase's tasks record as fixed, raising the test count from 87 to 128
across `tests/test_activities.py` and `tests/test_activity_scan.py` combined.

- [x] T036 [P] `headless/activities.py`: rewrite `is_excluded`'s own category match to a
  word-boundary check (`_has_word`) so a bare "shop" cannot match inside "Pottery workshop";
  narrow the kid-only school terms in `EXCLUDED_CATEGORY_TERMS` to name only the kid-only kinds,
  never a bare "school" (which would also have excluded "Dance school" and "Cooking school")
- [x] T037 [P] `headless/activities.py`: add the `KEPT_CATEGORY_TERMS` keep-list - at this point
  holding only the bare, unqualified word "rental" - checked before any exclusion, so a rental
  business is never excluded
- [x] T038 [P] `headless/activities.py`: `apply_day_window` now reads a day's own hours text that
  parses to no time range and does not contain "closed" as `day_status = "unknown"`, never
  `"closed"`
- [x] T039 [P] `headless/activities.py`: rewrite `relevance_pattern` from a prefix match to a
  whole-word-plus-inflection match, so "comedy" no longer matches "Comerica" and "mini" no longer
  matches "Mining"
- [x] T040 [P] `scripts/activity_scan.py`: `_scroll_feed_to_end` now stops only after two
  consecutive scrolls each load no new card, never after one slow-loading scroll
- [x] T041 [P] `scripts/activity_scan.py`: `run_scan`'s own per-query navigation and read now
  fail-soft (`note: query skipped for '<query>' (<ExceptionClass>)`), matching the already
  fail-soft per-venue detail read (FR-035); confirm the fixed, identifying `USER_AGENT` header
  reaches every Nominatim request
- [x] T042 [P] `scripts/activity_scan.py`: add the report writer's chmod bracket (`os.chmod`
  before the open and again after the write) so a same-date rerun over a file whose mode drifted
  restores `0600`
- [x] T043 [P] `scripts/activity_scan.py`: `window_minutes` now refuses a non-clock `HH:MM` value
  (an hour outside 00-23 or a minute outside 00-59) with a stated `ValueError`; `resolve_near`/
  `looks_like_coordinates` refuse a coordinate-shaped pair that is out of range (for example,
  "95,0") with no geocoder request ever sent
- [x] T044 [P] `tests/test_activities.py`, `tests/test_activity_scan.py`: tests for every fix
  above (test count 87 -> 128)

**Checkpoint**: every fix above is proven by a test that exercises the corrected behavior, not
merely stated in a code comment.

---

## Phase 11: Re-Verification Fix Batch (second pass, 2026-09-09)

**Purpose**: a re-verification of Phase 10's own fix batch found the further issues this phase's
tasks record as fixed, raising the test count from 128 to 140.

- [x] T045 [P] `headless/activities.py`: rewrite `KEPT_CATEGORY_TERMS` from the earlier bare,
  unqualified word "rental" to eight named activity-rental phrases ("kayak rental", "canoe
  rental", "paddleboard rental", "boat rental", "bike rental", "bicycle rental", "ski rental",
  "skate rental"), so "Tuxedo rental shop" and "Party rental store" no longer survive exclusion
  (research.md D11)
- [x] T046 [P] `headless/activities.py`: correct `EXCLUDED_CATEGORY_TERMS`'s earlier, unhyphenated
  spelling of the coworking term to "co-working" (alongside the existing "coworking")
- [x] T047 [P] `headless/activities.py`: `relevance_hit`/`relevance_pattern` now return `None`
  (neutral, no score change) when no query that surfaced the venue carries a meaning-carrying
  token at all (for example, a `--queries-file` line reading "cafe bar club"); the docstring now
  documents both residual classes (ordinary-word false positives and compound-name false
  negatives) (research.md D12)
- [x] T048 [P] `headless/activities.py`: `looks_like_coordinates`/`parse_near` now accept an
  optional leading "+" and an optional trailing ",<zoom>" or ",<zoom>z" (a pasted lat,lon,zoom
  triple from a map URL); "95,0,17z" is still coordinate-shaped and still refused without a
  geocoder request
- [x] T049 [P] `scripts/activity_scan.py`: the per-query stdout lines (results count, single
  result, query-skipped note, no-feed note, details-skipped note) now quote the query and the
  venue name with explicit single quotes rather than Python's own `repr`, so an apostrophe in a
  name prints as-is
- [x] T050 [P] `tests/test_activity_scan.py`: extend the chmod-bracket test to run the scan twice
  over files chmod-ed to `0644` in between, proving the bracket's own job rather than only its
  starting state (research.md D13)
- [x] T051 [P] `tests/test_activities.py`, `tests/test_activity_scan.py`: tests for every fix
  above (test count 128 -> 140)

**Checkpoint**: every re-verification finding above is proven by a test; the full suite is 789
passed, 9 skipped.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: no dependencies - can start immediately; BLOCKS every user story
  (every later phase calls a parser or a geography function this phase defines)
- **User Story 1 (Phase 2)**: depends on Foundational; independent of every other user story's
  own implementation tasks
- **User Story 2 (Phase 3)**: depends on Foundational only; independent of User Story 1
- **User Story 3 (Phase 4)**: depends on Foundational only; independent of User Stories 1 and 2
- **User Story 4 (Phase 5)**: depends on Foundational only; independent of every other user story
- **Cross-cutting refusals (Phase 6)**: depends on Foundational, and on User Stories 1 through 4
  having defined `main`'s own flags (the refusal ordering wraps every flag's own branch)
- **Polish (Phase 7)**: depends on all four user stories and the cross-cutting phase being
  complete
- **Ranking patch and the single-place path (Phase 8)**: depends on Phase 7's own code (it
  patches the same functions Phase 2 and Phase 7 already implemented); independent of the
  document set Phase 7 wrote
- **Documentation reconciliation (Phase 9)**: depends on Phase 8 - it documents what Phase 8
  changed
- **Opus verifier fix batch (Phase 10)**: depends on Phases 1 through 9 (the shipped code and its
  first document set); independent of any later phase's own tasks
- **Re-verification fix batch (Phase 11)**: depends on Phase 10

### Within Each User Story

- Test tasks (marked `[P]`) before their own implementation task
- `scripts/activity_scan.py` implementation tasks are NOT marked `[P]` against each other across
  phases (all touch the same file); test tasks across different files remain `[P]` against each
  other

### Parallel Opportunities

- T001, T002, T003 (Foundational) in parallel across `headless/activities.py` and
  `tests/test_activities.py`
- T004, T005, T006 (User Story 1 tests) in parallel
- T010 (User Story 2 tests) in parallel with T012 (User Story 3 tests) and T014 (User Story 4
  tests)
- T020-T023 (Polish, independent files) in parallel
- T025-T029 (the ranking patch and the single-place path, mostly independent files) in parallel
- T030-T034 (Documentation reconciliation, independent files) in parallel
- T036-T043 (Opus verifier fix batch, Phase 10) in parallel; T044 depends on all of them
- T045-T050 (re-verification fix batch, Phase 11) in parallel; T051 depends on all of them

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (Foundational)
2. Complete Phase 2 (User Story 1)
3. **STOP and VALIDATE**: run `pytest -q -k "activities or activity_scan"` and confirm every test
   from T004 through T006 passes
4. Phases 3 through 6 extend the MVP with address resolution, the check mode, custom queries, and
   the refusal guarantees; all four were already part of the Director's own approved brief for
   this feature and ship together in this delivery

### Incremental Delivery

1. Foundational -> every parser and geography function is ready for every later phase
2. User Story 1 -> independently testable -> the core scan-and-report loop works
3. User Story 2 -> independently testable -> the Director can give an address, not only
   coordinates
4. User Story 3 -> independently testable -> the Director can verify the scan's own health first
5. User Story 4 -> independently testable -> the Director can run his own query list
6. Cross-cutting refusals -> the read-only guarantee is proven by test, not merely documented
7. Polish -> docs of record, the commit gate
8. Ranking patch and the single-place path -> the first live scan's own findings feed back into
   the ranking rule and the search-page read
9. Documentation reconciliation -> every document of record catches up to Phase 8's own code
10. Opus verifier fix batch -> word-boundary exclusion, the whole-word relevance rewrite,
    per-query fail-soft reads, the unparseable-hours "unknown" case, the out-of-range-coordinate
    refusal, and the chmod bracket, each proven by a new test
11. Re-verification fix batch -> the named activity-rental keep-list, the "co-working" spelling,
    the neutral relevance case, the lat/lon/zoom triple, single-quoted stdout, and a
    double-run chmod-bracket proof, each proven by a new test

## Notes

- `[P]` tasks touch different files with no dependency on another unchecked task in this list
- `[Story]` maps a task to spec.md's own numbered user story for traceability
- This delivery documents an already-implemented, already-tested feature; T001 through T019
  describe code and tests that exist in this worktree today, not future work
- T025 through T029 describe the orchestrator's own post-scan ranking patch, also already
  present in this worktree before T030 through T035 (this same delivery) reconciled the document
  set against it
- T036 through T051 (Phases 10 and 11) describe an Opus verifier's own fix batch and a
  subsequent re-verification's own further fix batch, both also already present in this worktree
  before this delivery reconciled the document set against them a second time
- No merge task and no push task appear anywhere in this list, per this delivery's own brief
