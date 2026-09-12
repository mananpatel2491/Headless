---

description: "Task list for feature 011 Product Scan"

---

# Tasks: Product Scan

**Input**: Design documents from `/specs/011-product-scan/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/scan-and-report.md,
quickstart.md

**Tests**: REQUIRED by the specification (NFR-001, and SC-001 through SC-013 each name a
unit-test-provable outcome).

**Organization**: tasks are grouped by user story so each story is independently implementable and
testable, per this repository's own `tasks-template.md` convention.

**Status**: this document is the delivery plan for a feature built in parallel from the same
Director brief this spec set documents (brief `brief-011-product-scan.md`, 2026-09-11): a builder
session implements `headless/products.py`, `scripts/product_scan.py`, their tests, and the docs of
record, while this spec set is authored alongside it. Every task below is marked `[X]` as it maps
to that brief; the orchestrator reconciles any as-built delta against this document after an Opus
verification, the same reconciliation discipline `specs/009-activity-scan/tasks.md` already
records for its own later phases. No `.py` file and no doc of record is edited by this spec
delivery itself - `headless/products.py`, `scripts/product_scan.py`, `tests/test_products.py`,
`tests/test_product_scan.py`, `PATTERNS.md`, `Project_Structure.md`, `Function_Mapping.md`,
`scripts/README.md`, and `MEMORY.md` are the parallel implementation builder's own files.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on another unchecked task)
- **[Story]**: which user story this task belongs to (US1, US2, US3, US4), or unmarked for
  Foundational/Cross-cutting/Polish
- Every task names its own exact file path

## Path Conventions

Single project at the repository root: `headless/` (the package this feature adds a module to),
`scripts/` (the new errand), `tests/` (pytest). All paths below are relative to the worktree root
`../worktrees/Headless/v0.0.11/`.

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: the shapes, selector constants, and small parsers every user story's own logic reads.

- [x] T001 [P] `headless/products.py`: define `Listing`, `SITES`, `REFERENCE_HOSTS`,
  `WALL_TITLES`, `CHECK_SELECTORS`, and the live selector constants for Amazon (card, card title,
  card link, card price, card rating, card reviews, sponsored marker), Home Depot (pod, pod
  header, pod link, pod price, pod rating), and the Amazon and Walmart product-page selectors
- [x] T002 [P] `tests/test_products.py`: unit tests for `parse_price`, `parse_rating`,
  `parse_rating_and_count`, `parse_count`, `canonical_url`, `search_url`, and `wall_reason`
- [x] T003 [P] `headless/products.py`: implement those same functions

**Checkpoint**: every later phase can call a tested parser, a tested URL builder, or the wall
detector with no further wiring of its own.

---

## Phase 2: User Story 1 - The Director scans a product query and gets a ranked, tiered report (Priority: P1) 🎯 MVP

**Goal**: the scan reads Amazon's own search pages, parses, folds, scores, tiers, and reports.

**Independent Test**: stub the Amazon search read with a fixed set of listing titles drawn from
the 2026-09-11 recon (one excluded by category, one plastic, one metal); run the script end to
end; assert the report keeps the two kept listings, tiered correctly, and omits the excluded one.

### Tests for User Story 1

- [x] T004 [P] [US1] `tests/test_products.py`: tests for `parse_attributes` against every real
  recon title this feature's own brief names (Bluepro, MIXC, EasyFlex 100ft, Bonviee `2 x 50FT
  1.5"`, "4-Inch x 33 FT ... 50 Spikes", "EasyFlex ... 4.5 in. Tall Decorative", "EasyFlex 2.5"
  Tall Wall ... 100 Foot", "EasyFlex Tall Wall ... 90' kit", "Amazon Basics Flexible Landscape
  Edging Coil" (no height, no length), "42.5ft(L) x 13in(H) Animal Barrier Fence" (excluded,
  height 13, length 42.5), "4 in × 40 FT Landscape Edging No Dig with 36 Spikes" (U+00D7),
  "Quibbay 3.15" x 100' Landscape Edging ... 150 A", "SnugNiture Corrugated Metal Garden
  Edging,6"×50'Sturdy Lawn Edging Border" (metal, 6, 50), "Metal Landscape Edging 6 Pack 40" L x
  6" H | 20 FT Galvanized Bendable" (steel, height 6, length 20), "Landscape Edging Stone for Lawn
  Edging,12 Pack 24 Bricks 15.5FT Kit" (stone-look, 15.5), "Orgrimmar Garden Edging Kit 40PCS
  Pound-in Interlocking Black(20”x5.3”) | Plasti" (plastic, height 5.3, no length), "TISHO 3" x
  48" Black Rubber No Dig" (rubber, 3, no length), "Vigoro60 ft.​ No-​Dig Plastic
  Landscape Edging Kit" (plastic, 60, no_dig), "BSHAPPLUS® 4in x 40ft No Dig Landscape Edging Kit
  with 45 Unbreakable Steel Stakes, Flexible HDPE" (plastic, 4, 40, 45 steel stakes), "GOTGELIF
  Landscape Edging 2inch Tall, 40/100ft No-Dig ... with 60/120 Spikes Plastic" (2, 40, stakes 60),
  and "5-Pack Steel Landscape Edging (39x4 in), Bendable Heavy Duty Metal" (steel, height 4, no
  length)
- [x] T005 [P] [US1] `tests/test_products.py`: tests for `price_per_ft` (rounding, `None`
  propagation), `score_listing` (the Bayesian shrink, the price-weight term, the unknown-length/
  unknown-price fixed penalty and flag, the position term, the sponsored penalty, scoring
  monotonicity), `tier` (every material mapping), `rank` (excluded and below-`min_height_in`
  listings dropped and counted, an unknown-height listing kept and flagged, remainder tiered and
  sorted), and `fold_duplicates` (canonical-URL key, lowest `(page, position)` kept, non-sponsored
  beats sponsored, `found_on_pages` union)
- [x] T006 [P] [US1] `tests/test_products.py`: tests for `render_markdown` (header counts, one
  table per tier in order, `## Notes`, `## Excluded` counts per reason) and `render_json` (the
  `meta`/`tiers`/`excluded` shape)
- [x] T007 [P] [US1] `tests/test_product_scan.py`: `FakeSession`/`FakePage` fixtures, modeled on
  `tests/test_activity_scan.py`'s own fakes, and a test that a full Amazon-only scan run (with
  `read_amazon_search` stubbed) writes exactly one Markdown and one JSON report file at `0600`,
  that a fence-category listing never reaches either, and that a kept listing's tier and score
  match its stubbed title and price

### Implementation for User Story 1

- [x] T008 [US1] `headless/products.py`: implement `parse_attributes` (depends on T004 existing
  and passing)
- [x] T009 [US1] `headless/products.py`: implement `price_per_ft`, `score_listing`, `tier`, `rank`,
  `fold_duplicates`, `render_markdown`, `render_json` (depends on T005, T006 existing and passing)
- [x] T010 [US1] `scripts/product_scan.py`: implement `read_amazon_search`, `_settle`, and
  `run_scan`'s Amazon-only path (search, parse, fold, score, tier, render, the report-writing
  chmod bracket) (depends on T007 existing and passing, and on T008, T009)
- [x] T011 [US1] `scripts/product_scan.py`: wire the module docstring, `HANDOFF = "n/a (read-only
  errand)"`, the repo-root `sys.path` bootstrap, and the argument parser's `--query`/`--pages`/
  `--sites` flags (depends on T010)

**Checkpoint**: User Story 1 is independently functional - a scan against a stubbed Amazon read
produces a correct, ranked, tiered, two-file report.

---

## Phase 3: User Story 2 - The Director sees where the listing he was sent would rank (Priority: P1)

**Goal**: `--reference-url` and `--reference` both feed one reference listing into the same
scoring and tiering pipeline as a search result, and the report states its rank.

**Independent Test**: stub an Amazon product-page read returning a fixed title, price, and rating;
run the scan with `--reference-url` pointing at that fixture and a small set of stubbed search
results; assert the report's reference block names the correct rank and tier.

### Tests for User Story 2

- [x] T012 [P] [US2] `tests/test_products.py`: tests for `parse_reference_literal` (`"Title |
  31.58 | 40"`, with and without a leading `$` and a trailing `ft`/`'`; every malformed shape -
  missing parts, an unparsable price, an unparsable length - raising `ValueError`)
- [x] T013 [P] [US2] `tests/test_product_scan.py`: tests for a successful `--reference-url`
  (Amazon) read populating `origin="reference-url"` and the rendered rank sentence; a Walmart
  `--reference-url` wall printing the fixed note and falling back to `--reference`'s own literal;
  an unsupported `--reference-url` host refusing before any `Session` is constructed; and both
  flags given together preferring a successful URL read over the literal

### Implementation for User Story 2

- [x] T014 [US2] `scripts/product_scan.py`: implement `read_amazon_product` and
  `read_walmart_product` (depends on T013 existing and passing)
- [x] T015 [US2] `headless/products.py`: implement `parse_reference_literal` (depends on T012
  existing and passing)
- [x] T016 [US2] `scripts/product_scan.py`: wire `--reference-url`/`--reference` into `main` - the
  host-validation refusal, the reference-read-after-search ordering, the wall-fallback note, and
  locating the read or literal reference inside its own tier's ranked list for the rank sentence
  (depends on T014, T015)

**Checkpoint**: User Stories 1 and 2 both work independently - the Director can run a plain scan,
or point it at the specific listing the errand's own question is about.

---

## Phase 4: User Story 3 - The Director checks the scan's own selectors (Priority: P2)

**Goal**: `--check` probes each selected site's own dependent selectors, read-only, against page 1
only, and never scrolls, reads a reference, or writes a report.

**Independent Test**: stub the session's `probe` call to report every Amazon selector but one as
found; assert the summary line names the correct counts and that no report file is written.

### Tests for User Story 3

- [x] T017 [P] [US3] `tests/test_product_scan.py`: a test that `--check` navigates to page 1 of
  every selected site only, prints `CHECK <n> found, <m> missing`, constructs the `Session` in
  `Mode.PREVIEW`, and writes no report file

### Implementation for User Story 3

- [x] T018 [US3] `scripts/product_scan.py`: implement `run_check` and wire the `--check` flag into
  `main` (depends on T017 existing and passing)

**Checkpoint**: User Stories 1 through 3 all work independently - a Director can verify the scan's
own health before trusting a real run.

---

## Phase 5: User Story 4 - The Director opts into Home Depot as a second search site (Priority: P2)

**Goal**: `--sites amazon,homedepot` adds Home Depot's own lazy-loaded search pages; a wall on
Home Depot's own page 1 skips its remaining pages without affecting Amazon's results.

**Independent Test**: stub a Home Depot search read returning 24 pods for 12 unique products (the
observed DOM-duplication shape); assert the folded report holds 12 listings, not 24.

### Tests for User Story 4

- [x] T019 [P] [US4] `tests/test_product_scan.py` (fix batch B18, 2026-09-11: corrected from
  `tests/test_products.py` - Home Depot's own pod parsing is exercised through
  `scripts/product_scan.py`'s `read_homedepot_search`, not through `headless/products.py` itself):
  tests for Home Depot's own pod parsing - the zero-width-space-stripped header
  ("Vigoro60 ft.​ No-​Dig Plastic Landscape Edging Kit"), the split-price-span
  reassembly (`"$\n41\n.\n97"` -> `41.97`), and the combined rating/count label
  (`"(4.5 /\xa04091)"` -> `(4.5, 4091)`)
- [x] T020 [P] [US4] `tests/test_product_scan.py`: tests for `read_homedepot_search`'s own
  lazy-scroll loop stopping after two consecutive stale scrolls (the `activity_scan` stale-pass
  rule); the 24-pods/12-unique DOM-duplication shape folding to 12 listings; the `Error Page` wall
  on Home Depot's own page 1 printing the skip note and continuing with Amazon's own results; and
  an unknown `--sites` id refusing before any `Session` is constructed

### Implementation for User Story 4

- [x] T021 [US4] `scripts/product_scan.py`: implement `read_homedepot_search`, including the
  lazy-load scroll loop (`page.evaluate("window.scrollBy(0, document.body.scrollHeight)")` plus a
  wait, up to 6 attempts, stopping after two consecutive scrolls add no new pod) (depends on T019,
  T020 existing and passing)
- [x] T022 [US4] `scripts/product_scan.py`: wire `--sites` parsing and validation, and multi-site
  iteration, into `run_scan` and `run_check` (depends on T021)

**Checkpoint**: all four user stories are independently functional.

---

## Phase 6: Cross-Cutting - Refusals, Exit Codes, and the Read-Only Guarantee

**Goal**: `--apply` is always refused before any session; every malformed-input refusal is proven
before a session is constructed; an unhandled exception exits 2 with a value-free message.

- [x] T023 [P] `tests/test_product_scan.py`: a test that `--apply` refuses before any `Session` is
  constructed (a `RefusingSession` assertion double that raises if constructed)
- [x] T024 [P] `tests/test_product_scan.py`: tests that an empty `--query`, a `--pages` value
  outside 1 through 5, a malformed `--reference`, and an unsupported `--reference-url` host each
  refuse with no `Session` constructed
- [x] T025 [P] `tests/test_no_direct_typing.py`: confirm the existing structural scan (its own
  `ast`-based walk of every file under `scripts/`) already covers `scripts/product_scan.py` with
  no exception needed - no `.fill`/`.type`/`.press`/`.click`/`.dblclick`/`.select_option`/`.check`/
  `.set_input_files` call exists anywhere in that file
- [x] T026 [P] `tests/test_product_scan.py`: a subprocess test that runs
  `python scripts/product_scan.py --help` from a working directory outside the repository and
  asserts exit 0, proving the repo-root `sys.path` bootstrap (FR-040) works standalone
- [x] T027 [P] `tests/test_product_scan.py`: a test that an unhandled exception during the browser
  session prints only the exception's own class name and exits 2, with the full traceback gated
  behind `HEADLESS_DEBUG=1`; and a test that a `GateRefused` raised inside the session exits 1
  with `REFUSED: <message>`
- [x] T028 `scripts/product_scan.py`: implement `main`'s own refusal-before-session ordering and
  the exit-code table (0 report/check, 1 refusal, 2 usage error or unhandled exception) (depends
  on T023 through T027 existing and passing)

**Checkpoint**: the read-only guarantee is proven, not merely stated - every refusal path is
exercised by a test that never constructs a real session.

---

## Phase 7: Polish & Cross-Cutting Concerns (docs of record; implementation builder only)

**Purpose**: bring every document of record in line with this feature. These tasks are performed
by the parallel implementation builder, not by this spec-authoring delivery; they are listed here
so the delivery plan is complete and the orchestrator can check the whole feature off in one place.

- [x] T029 [P] `PATTERNS.md`: append one new entry recording the ranking rule, the site-tiering
  decision (Amazon primary, Home Depot opt-in, Walmart reference-only), the attribute-parsing
  order (stake stripping before material matching), and the recon findings (v0.0.11, spec
  011-product-scan)
- [x] T030 [P] `Project_Structure.md`: extend the `headless/`/`reports/` row text, add a
  `scripts/product_scan.py` row, and append one new Changelog row for v0.0.11
- [x] T031 [P] `scripts/README.md`: add an Errands table row for `product_scan.py`
- [x] T032 [P] `Function_Mapping.md`: add a table row for `scripts/product_scan.py` (site(s),
  reads, writes up to `reports/product/`, secrets/profile fields none, handoff
  `n/a (read-only errand)`)
- [x] T033 [P] `MEMORY.md`: add the new site traps (Home Depot's `Error Page` repeat-visit wall,
  Walmart's `Robot or human?` wall, Lowe's `Access Denied`, Google Shopping's `/sorry/index`
  captcha, Menards' blank page, Target's unaddressable card markup - each dated 2026-09-11 with
  its own observed title), an Errands run row for today's recon probes (site names and titles
  only - the query, never a person), and an Open item for spec 011 in the style of the 009 item
- [x] T034 Run the full commit gate: `.venv/bin/python -m pytest -q`,
  `.venv/bin/python scripts/verify_structure.py`,
  `python3 scripts/scan_secrets.py --paths <every file this delivery wrote or edited>` - all
  green, with zero real network calls and zero real browser launches anywhere in the default suite
  (spec NFR-001, SC-001)

---

## Phase 8: Fix batch (post-live-run and post-Opus-verification, 2026-09-11)

**Purpose**: the three live scans (`no dig landscape edging`, `4 inch tall landscape edging`,
`steel landscape edging`) and an Opus verification of the Phase 1-7 delivery both found defects
and gaps; this phase closes them, in `headless/products.py`, `scripts/product_scan.py`, their
tests, this spec set, and the docs of record.

- [x] T035 [P] `headless/products.py`: drop bare "stone"/"paver" from the stone-look material rule
  (D-stone-look); `tests/test_products.py` gains real-title coverage for both the paver
  reclassification and the still-stone-look titles (Polyrock, Faux Stone/Stone-Look, Stone Effect,
  Stone Texture, Bricks)
- [x] T036 [P] `headless/products.py`: strip every stake/spike phrase (counted or not) before
  material/height/length parsing, and guard the counted-phrase regex against starting on a decimal
  fraction's own trailing digits (D-stakes); `tests/test_products.py` gains the 80FT/Metal-Stakes,
  Jorvila/120-Pcs, and both decimal-fraction titles
- [x] T037 [P] `headless/products.py`: the foot-mark candidate requires a LONE single quote (never
  adjacent to another `'` or a `"`), and a title-stated grand total overrides every other length
  candidate (D-quote); `tests/test_products.py` gains the double-prime and total-marker titles
- [x] T038 [P] `headless/products.py`: both height context windows stop at the next dimension's
  own digit and never end mid-word (D-height-window); `tests/test_products.py` gains the
  `L x W x H` triple and the Gardzen mid-word-truncation titles
- [x] T039 [P] `headless/products.py`: `is_pack`/the `"pack: per-piece length"` flag, applied by
  the script's `_fill_attributes` and by `parse_reference_literal`, with `" (per piece)"` appended
  to the report's own Length cell when set
- [x] T040 [P] `headless/products.py`: `score_listing` sets the `"unrated"` flag when `rating` is
  `None` (FR-024); `rank(listings, min_height_in=None)` returns a `RankResult`
  (`tiers`/`excluded`/`dropped_by_height`) instead of a bare tier dictionary, checking exclusion
  before the height drop (FR-028); `render_markdown`/`render_json` take a `RankResult`, escape a
  literal `|` in a title before it enters a table cell (D-pipe-escape), list each excluded/
  height-dropped listing by title, and add the JSON `"excluded"` array plus the reference object's
  own `"rank"`/`"tier"`/`"tier_size"` keys
- [x] T041 [P] `headless/products.py`: `slugify(query)`; `scripts/product_scan.py` names the report
  files `product-scan-<slug>-<UTC date>.md`/`.json`
- [x] T042 [P] `headless/products.py`: `parse_reference_literal` accepts an optional 4th (rating,
  0-5) and 5th (reviews, >= 0) pipe-separated part, and refuses a zero/negative price or length or
  a leading `-` on either
- [x] T043 [P] `scripts/product_scan.py`: `read_amazon_search`/`read_homedepot_search` take a
  `start_position` so `position` is a running index per SITE across every page read, not reset per
  page (D-position); `CHECK_SELECTORS` becomes card/pod-scoped, never a bare page-level selector;
  a wall note carries a `wall: ` prefix and a zero-cards page's own note is emitted by `run_scan`
  itself (reaching the report's own `## Notes`), not printed unconditionally inside the read
  functions
- [x] T044 [P] `tests/test_products.py`/`tests/test_product_scan.py`: replace every 80-char-
  truncated fixture with the FULL real title from the three live-run JSON files; pin the exact
  "Your pick would rank #3 of 3 in the plastic tier." sentence plus both rank boundary cases
  (#1 of n, #n+1 of n); add the 24-pods/12-unique Home Depot fold test and the multi-site test
  proving a Home Depot wall never affects Amazon's own results in the same run (this phase's own
  correction to T019's file location, above)
- [x] T045 [P] This spec set: reconcile `spec.md` (FR-010, FR-013, FR-016, FR-017 through FR-020,
  FR-023a (NEW), FR-026, FR-031 through FR-033, FR-035, SC-007, SC-008), `data-model.md`,
  `contracts/scan-and-report.md` (rewritten from a real render), `quickstart.md` (the B19 wording
  fix, the A4 reference format, the slugged file name), and `research.md` (the fix-batch addenda
  above) against the as-built code; replace every household reference with "a listing the Director
  was sent" across this document set (D-household-redaction, fix batch B20 - the repository is
  PUBLIC)
- [x] T046 [P] Docs of record: `PATTERNS.md` (append the fix-batch findings to the existing
  product-scan entry), `Project_Structure.md` (the `tests/` row gains the two new test files; the
  v0.0.11 Changelog row gains the fix-batch summary and the final test count), `scripts/README.md`
  (the `--pages`-out-of-range refusal in the exit-code list; the card-scoped `--check` note; the
  A4 reference format), `MEMORY.md` (three "Errands run" rows for the three live scans; one row
  for the pre-batch `--check` result plus a placeholder for the post-batch one; the spec 011 open
  item rewritten with this fix batch's own summary; "seven" corrected to "ten" in the recon row;
  every household reference removed)
- [x] T047 Re-run the full commit gate after T035-T046: `.venv/bin/python -m pytest -q`,
  `.venv/bin/python scripts/verify_structure.py`, `python3 scripts/scan_secrets.py --paths <every
  file this fix batch touched>`, a hyphen-only grep, and a scratch re-parse of every title in the
  three live-run JSON files proving the material/tier/height/length/stake-count deltas this batch
  intended

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: no dependencies - can start immediately; BLOCKS every user story
  (every later phase calls a parser, a URL builder, or the wall detector this phase defines)
- **User Story 1 (Phase 2)**: depends on Foundational; independent of every other user story's own
  implementation tasks
- **User Story 2 (Phase 3)**: depends on Foundational and on User Story 1's own `Listing`/scoring/
  tiering functions (the reference listing is scored and tiered by the same functions a search
  result is)
- **User Story 3 (Phase 4)**: depends on Foundational and on User Story 4's own `CHECK_SELECTORS`
  entries for both sites being defined, but not on either story's own read implementation
- **User Story 4 (Phase 5)**: depends on Foundational only; independent of User Stories 1 through 3
  at the parsing level, though its own search read feeds the same fold/score/tier pipeline User
  Story 1 builds
- **Cross-cutting refusals (Phase 6)**: depends on Foundational, and on User Stories 1 through 4
  having defined `main`'s own flags (the refusal ordering wraps every flag's own branch)
- **Polish (Phase 7)**: depends on all four user stories and the cross-cutting phase being
  complete; performed by the implementation builder, not this spec delivery

### Within Each User Story

- Test tasks (marked `[P]`) before their own implementation task
- `scripts/product_scan.py` implementation tasks are NOT marked `[P]` against each other across
  phases (all touch the same file); test tasks across different files remain `[P]` against each
  other

### Parallel Opportunities

- T001, T002, T003 (Foundational) in parallel across `headless/products.py` and
  `tests/test_products.py`
- T004, T005, T006, T007 (User Story 1 tests) in parallel
- T012, T013 (User Story 2 tests) in parallel with T017 (User Story 3 tests) and T019, T020 (User
  Story 4 tests)
- T023 through T027 (Cross-cutting tests) in parallel; T028 depends on all of them
- T029 through T033 (Polish, independent files) in parallel; T034 depends on all of them

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (Foundational)
2. Complete Phase 2 (User Story 1)
3. **STOP and VALIDATE**: run `pytest -q -k "products or product_scan"` and confirm every test
   from T004 through T007 passes
4. Phases 3 through 6 extend the MVP with the reference comparison, the check mode, the Home Depot
   opt-in, and the refusal guarantees; all four were part of the Director's own approved brief for
   this feature and ship together in this delivery

### Incremental Delivery

1. Foundational -> every parser, URL builder, and the wall detector are ready for every later
   phase
2. User Story 1 -> independently testable -> the core scan-fold-score-tier-report loop works
   against Amazon alone
3. User Story 2 -> independently testable -> the Director can compare a specific listing, not only
   browse a ranked field
4. User Story 3 -> independently testable -> the Director can verify the scan's own health first
5. User Story 4 -> independently testable -> the Director can widen the field to Home Depot when
   it happens to cooperate
6. Cross-cutting refusals -> the read-only guarantee is proven by test, not merely documented
7. Polish -> docs of record, the commit gate (implementation builder)

## Notes

- `[P]` tasks touch different files with no dependency on another unchecked task in this list
- `[Story]` maps a task to spec.md's own numbered user story for traceability
- This document is the delivery plan for a feature built in parallel with this spec set from the
  same Director brief; T001 through T034 describe the intended build, marked `[X]` per that
  brief's own instruction, and the orchestrator reconciles any as-built delta against this
  document after an Opus verification of the implementation builder's own output
- No merge task and no push task appear anywhere in this list, per this delivery's own brief
