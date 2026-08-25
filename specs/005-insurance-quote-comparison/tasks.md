---

description: "Task list for feature 005 Insurance Quote Comparison"
---

# Tasks: Insurance Quote Comparison

**Input**: Design documents from `/specs/005-insurance-quote-comparison/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/walk-capture-report.md,
quickstart.md

**Tests**: REQUIRED by the specification (SC-001 through SC-013). Test tasks are included and are
written before the module code they cover, per this repository's own Continuous Errand Validation
principle.

**Organization**: Tasks are grouped by user story so each story is independently implementable and
testable, mirroring spec 003's and spec 004's own tasks.md shape.

**Status**: NOT implemented. This delivery is spec-authoring only, per this feature's own brief (no
code, no browser, no branch, no commit). Every task below is unchecked `[ ]`; none has been run.
`/speckit-implement` (a separate, later, explicitly authorized run) is what actually executes this
list.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1..US4)
- Every task names its file path

## Path Conventions

Single project at the repository root: `headless/` (the package this feature extends), `scripts/`
(one new orchestrating script), `tests/` (pytest). All paths below are relative to the worktree
root `../worktrees/Headless/v0.0.5/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: the one filesystem-level precondition (`reports/` gitignored) in place before
anything writes there.

- [ ] T001 Update `.gitignore`: add `reports/` as a new top-level entry, mirroring the existing
  `previews/` entry exactly (research.md D4: `reports/` is a new sibling directory, derived
  location, no new environment variable)

**Checkpoint**: nothing this feature writes under `reports/` can ever land in a commit, from the
first file this feature adds onward.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the walk framework itself - the four `Step` kinds, `Session.click`/`Session.capture`,
`Errand.walk()`'s default and dispatch loop, `PreviewRecord.steps` - built and proven correct
against fixtures before either the Progressive walk (US2) or the orchestrator (US4) can be written
against it. Tests first.

- [ ] T002 [P] Write `Step` dataclass shape tests in `tests/test_steps.py` (new file): `ClickStep`,
  `HumanStep`, `CaptureStep` each construct with their documented fields (data-model.md's table)
  and are frozen/immutable, matching `FieldPlan`'s own existing `@dataclass(frozen=True)` shape
- [ ] T003 [P] Write `Session.click` tests in `tests/test_session.py`: refuses outside apply mode
  with `GateRefused`, matching `Session.fill`'s existing refusal test's shape; a successful click
  against a fixture page calls the locator's `click()` exactly once, no retry; a locator-click
  exception is wrapped into `ClickFailed` naming only `step_name`/`selector`/`cause_class`, never
  the underlying exception's own message (mirrors the existing `FillFailed` leak-proof test)
- [ ] T004 [P] Write `Session.capture` tests in `tests/test_session.py`: an extractor whose
  selector resolves returns its stripped text; an extractor whose selector does not resolve
  returns `""` plus exactly one `note: capture field ... not found` line, and the call still
  processes every remaining extractor in the same dict (SC-009); the returned dict always has the
  same keys as the input `extractors` dict, regardless of how many resolved
- [ ] T005 Implement `ClickStep`, `HumanStep`, `CaptureStep` in `headless/steps.py` (new file):
  three frozen dataclasses per data-model.md's table; `Step = FieldPlan | ClickStep | HumanStep |
  CaptureStep` type alias (import `FieldPlan` from `headless/fields.py`, do not redefine it)
- [ ] T006 Implement `Session.click` and `ClickFailed` in `headless/session.py`: `click(selector)`
  refuses outside apply mode (same `GateRefused` message pattern as `fill`); one `locator.click()`
  call, no retry; wraps any exception into `ClickFailed` (new class alongside `FillFailed`, no
  `redact()` call needed since a click carries no typed value)
- [ ] T007 Implement `Session.capture` in `headless/session.py`: for each `(field_key, selector)`
  in `extractors`, check `locator(selector).count() > 0`; found -> stripped text; not found -> `""`
  plus one `note:` print; never raises for a missing selector; returns a dict with every input key
  present
- [ ] T008 Run `python -m pytest -q tests/test_steps.py tests/test_session.py -k "click or
  capture"` and make T002-T004 green against the T005-T007 implementation

**T054-T059 below were added by Director amendment after this phase was first drafted (Amendments
4 and 5: type-discriminated array addressing, and the `profile.template.json` drift test); their
IDs are out of numeric sequence with the rest of this phase but they belong here structurally -
foundational, general framework capability every `registry:` path benefits from, not specific to
Progressive or to insurance. Do not renumber: every existing cross-reference to T002-T053 in this
document and others stays valid this way.**

- [ ] T054 [P] Write `ProfileRegistry` array-traversal tests in `tests/test_profile.py`: a dotted
  path reaching a list node selects the unique element whose `type` field equals the next segment,
  then traversal continues from that element (including through a second list nested inside the
  matched element); a segment matching zero elements raises the existing `RegistryMissing(path)`,
  unchanged; a segment matching two or more elements raises a new `RegistryAmbiguous(path)`, naming
  only the path, never either matched element's own content (SC-016); an element with no `type`
  field is never a match candidate (skipped, not an error); a path fully consumed while the current
  node is still a list or a dict continues to raise the existing non-scalar `RegistryMissing`,
  unchanged from before this amendment; every existing dict-traversal and scalar-leaf test in this
  file still passes unmodified (zero behavior change for a document with no list anywhere in it)
- [ ] T055 Implement the array-traversal branch and `RegistryAmbiguous` in `headless/profile.py`
  per data-model.md's resolver state machine and contracts/walk-capture-report.md section 7
  (spec FR-040 through FR-044)
- [ ] T056 [P] Write a `RegistryAmbiguous`-prints-via-REFUSED test in `tests/test_errand.py`: a
  fixture `Errand` whose plan resolves a path that raises `RegistryAmbiguous` prints
  `REFUSED: {exc}` and exits `1`, the same pre-session treatment `RegistryMissing` already
  receives. Then wire `RegistryAmbiguous` into `headless/errand.py`'s existing pre-session
  exception tuple alongside `ConfigError`/`GateRefused`/`SecretMissing`/`RegistryMissing`
  (spec FR-045)
- [ ] T057 Run `python -m pytest -q tests/test_profile.py tests/test_errand.py -k "registry or
  ambiguous"` and make T054/T056 green against the T055/T056 implementation
- [ ] T058 [P] Write the `profile.template.json` drift test in `tests/test_profile.py` (or a new
  `tests/test_profile_template.py`, implementer's choice): load `profile.template.json` (a plain
  file read from the repository root, never through the vault, never prompting for a passphrase)
  and resolve, through `ProfileRegistry.get`, every registry path any shipped walk in this delivery
  references - including the Progressive walk's full field list and
  `vehicles.primary.currently_insured` once T023 has shipped it - failing the test if any path does
  not resolve (spec FR-048). This delivery MUST NOT create or recreate `profile.template.json`
  itself - it already exists on `main` (research.md D14); this task only adds the test that reads
  it. Until this worktree has the real file (a merge-forward or rebase this delivery does not
  perform - research.md D12/D14's own worktree-gap note), prove this test's own logic against a
  synthetic in-memory fixture document standing in for the template (spec SC-018), so the test is
  a direct drop-in, unmodified, once the real file is present
- [ ] T059 Run `python -m pytest -q -k template` and confirm T058's test passes against its interim
  fixture; re-run it once this worktree has merged forward from or been rebased onto current `main`
  to confirm it passes against the real `profile.template.json` too (deferred - not this
  delivery's own commit gate, since the file is not yet present here)

**Checkpoint**: the four `Step` kinds exist and `Session` can execute the two new ones in
isolation, proven correct against fixtures with zero browser launches; `ProfileRegistry.get` can
address one element of an array by `type`, with `RegistryAmbiguous` closing the duplicate-match
case, and a drift test guards every shipped walk's own paths against `profile.template.json`.
Neither `Errand.walk()` nor any insurer walk depends on anything beyond this yet.

---

## Phase 3: User Story 1 - The walk framework crosses a multi-page journey with human handoffs (Priority: P1) 🎯 MVP

**Goal**: prove the framework's own consumer-facing contract end to end: `Errand.walk()` defaults
to `plan()` with zero behavior change for every existing errand, preview over a walk never
navigates past the landing page, apply dispatches all four step kinds in order, and the window
stays visible for the rest of a run once any `HumanStep` has surfaced it.

**Independent Test**: a fixture `Errand` subclass whose `walk()` returns one of each `Step` kind,
run against a fake `Session`, in preview then apply mode (spec.md's own Independent Test for this
story).

- [ ] T009 [P] [US1] Write a default-`walk()` test in `tests/test_errand.py`: a fixture `Errand`
  subclass that overrides only `plan()` (not `walk()`) produces a `walk()` result identical to
  `plan()`'s own return value, and every existing `test_errand.py` scenario (pre-resolution,
  preview masking, apply filling, the trailing handoff) still passes unmodified, proving zero
  behavior change for a `plan()`-only errand (spec Acceptance Scenario US1-1)
- [ ] T010 [P] [US1] Write a preview-never-navigates-past-landing test in `tests/test_errand.py`:
  a fixture `Errand` whose `walk()` returns one `FieldPlan` plus one each of `ClickStep`,
  `HumanStep`, `CaptureStep`, run in preview mode against a fake `Session` that records every
  method call - assert `goto` was called exactly once and `click`/`handoff`/`capture` were called
  zero times (SC-001); assert the preview JSON's new `steps` list names the three non-`FieldPlan`
  steps by kind and name only
- [ ] T011 [P] [US1] Write an apply-mode four-step-dispatch test in `tests/test_errand.py`: the
  same fixture walk, run in apply mode against a fake `Session`, proves `fill`/`click`/`handoff`/
  `capture` each fire exactly once, in the walk's own declared order, followed by exactly one more
  `handoff` call for the trailing `self.HANDOFF` (spec Acceptance Scenario US1-4)
- [ ] T012 [US1] Write a window-stays-visible test in `tests/test_session.py` (or
  `tests/test_errand.py`, implementer's choice matching whichever file already covers this kind of
  cross-call test): a walk with two `HumanStep`s, run in apply mode against a fake `Session` whose
  `_restore_window`/`_hide_window`-equivalent calls are spied on, proves the hide-equivalent path
  is never invoked a second time after the first `HumanStep` fires (spec Acceptance Scenario US1-5)
- [ ] T013 [US1] Implement `Errand.walk(registry)` in `headless/errand.py`: default `return
  self.plan(registry)`; update the pre-resolution loop to iterate `self.walk(registry)` and skip
  any entry without a `.source` attribute (i.e. anything other than `FieldPlan`); update the
  apply-mode loop to dispatch by `isinstance` across the four `Step` kinds per data-model.md's
  table; update the preview-mode loop to record masked `FieldPlan` sources unchanged and append
  `{"kind": ..., "name": ...}` for every other step kind to a new `PreviewRecord.steps` list; leave
  the trailing `session.handoff(self.HANDOFF)` call unchanged in shape (research.md D2: no new
  conditional there)
- [ ] T014 [US1] Update `headless/preview.py`'s `PreviewRecord`: add `steps: list[dict] =
  field(default_factory=list)` (additive, backward-compatible field); include it in `to_json()`'s
  payload
- [ ] T015 [US1] Run `python -m pytest -q tests/test_errand.py tests/test_session.py tests/
  test_preview.py -k "walk or steps"` and make T009-T012 green against the T013-T014
  implementation

**Checkpoint**: MVP core delivered. The walk framework exists, is proven safe in preview (never
navigates past landing), correct in apply (all four kinds dispatch in order), and backward
compatible (every existing errand is unaffected). Nothing insurer-specific exists yet.

---

## Phase 4: User Story 2 - The Progressive journey is captured end to end (Priority: P1)

**Goal**: one real, working insurer walk, proving the framework from Phase 3 against a live site,
and the capture model that turns its quote page into structured data.

**Independent Test**: `scripts/quote_compare.py --check` (once T029 exists) against the verified
landing selectors, plus this phase's own unit tests against fixture data (spec.md's own
Independent Test for this story defers the real-site proof to Director UAT).

- [ ] T016 [P] [US2] Write `companies` parsing tests in `tests/test_capture.py` (new file):
  `parse_companies` (given the already-parsed `feature_configs.insurance.companies` fragment, not
  a raw string - `profile` as a whole is parsed once by the caller) accepts a valid array
  (including the empty array `[]`) and rejects a missing, non-array, or non-string-entry shape
  with `QuoteInputError` naming only `feature_configs`/`insurance`/`companies` (whichever piece is
  missing or malformed), never the fixture's own content (SC-008's unit-level half). There is no
  `parse_current_policy` in this delivery's own design (D3, revised twice) - `CurrentPolicy`
  values are built only by `headless/policydoc.py`'s extraction-and-confirmation path (Phase 2b
  below), never parsed from `profile` directly.
- [ ] T017 [P] [US2] Write `assemble_capture`/capture file tests in `tests/test_capture.py`: a
  fixture flat `raw_fields` dict (using the `premium.amount`/`coverage.<slug>.limit` vocabulary,
  data-model.md) assembles into the documented `QuoteCapture` shape; an out-of-vocabulary key in
  `raw_fields` is ignored, not an error; `write_capture` writes to
  `reports/captures/<insurer>-<timestamp>.json` and a second call for the same insurer never
  overwrites the first (accumulates); `read_freshest_capture` against a fixture directory with
  several timestamped files for one insurer returns the newest by filename timestamp, and returns
  `None` for an insurer with no capture file at all
- [ ] T018 [US2] Implement `CurrentPolicy` (the dataclass shape only - no parse function),
  `QuoteCapture`, `QuoteInputError`, `parse_companies`, `assemble_capture`, `write_capture`,
  `read_freshest_capture` in `headless/capture.py` (new file) per data-model.md's full contract
- [ ] T019 [US2] Run `python -m pytest -q tests/test_capture.py` and make T016-T017 green against
  the T018 implementation

**Phase 2b (Director amendment 6): per-asset `policy_doc` extraction, confirmation, and cache -
`headless/policydoc.py` + `scripts/policy_extract.py`. Inserted here (after the capture model,
before the Progressive walk itself needs it) because the comparison engine's own `current_policy`
input now comes from this mechanism, not from hand-typed JSON - Phase 5 (US3) depends on it.**

- [ ] T019b [P] Add `pypdf` to `requirements.txt` (spec's new runtime dependency, plan.md's own
  Primary Dependencies note)
- [ ] T019c [P] Write `ExtractionCandidate`/`extract_candidate` tests in
  `tests/test_policydoc.py` (new file): a fixture PDF (synthetic declarations-page text, built via
  a fake `pypdf` reader double so the test never needs a real binary PDF asset) with clean,
  parseable coverage lines extracts a candidate shaped per `CurrentPolicy` plus `warnings: []`; a
  fixture PDF with unparseable or absent text extracts `None`, not an exception (spec FR-058);
  every heuristic (dollar amounts, split-limit `100,000/300,000` patterns, deductible-line
  detection, premium/term detection) gets at least one fixture proving it fires correctly on a
  clean input and degrades to `None`/a `warnings` entry, never a crash, on a hostile one
- [ ] T019d [P] Write `confirm_candidate` tests in `tests/test_policydoc.py`: an injectable
  `input_fn` returning "accept" returns the candidate unchanged as a `CurrentPolicy`; an
  `input_fn` returning a corrected JSON document returns that corrected `CurrentPolicy` instead;
  an `input_fn` returning "decline" (or anything not recognized as accept/correct) returns `None`;
  no real `input()` call happens in any test (SC-019's unit-level half)
- [ ] T019e [P] Write `PolicyReference`/cache tests in `tests/test_policydoc.py`: `write_policy_
  reference` writes `reports/policy/<asset-key>.json` at mode `0600` with the confirmed
  `CurrentPolicy` fields plus `source_path`/`confirmed_at` (SC-021); `read_policy_reference`
  returns `None` for a missing or malformed file, never raising (FR-058); a fixture proves
  `write_policy_reference` is never called when `confirm_candidate` returned `None` (SC-019)
- [ ] T019f [P] Write `is_excluded` tests in `tests/test_policydoc.py`: `"n/a"` on either
  `currently_insured` or `policy_doc` returns `True`; an absent field, or any other string, returns
  `False`; the function never mutates its input
- [ ] T019g Implement `CurrentPolicy` reuse (import from `headless/capture.py`, no duplicate
  definition), `ExtractionCandidate`, `extract_candidate`, `confirm_candidate`, `PolicyReference`,
  `write_policy_reference`, `read_policy_reference`, `is_excluded` in `headless/policydoc.py` (new
  file) per data-model.md's contract - `pypdf` for text extraction, deterministic heuristics only,
  no LLM call anywhere (spec FR-051, SC-022)
- [ ] T019h Run `python -m pytest -q tests/test_policydoc.py` and make T019c-T019f green against
  the T019g implementation
- [ ] T019i [P] Write `scripts/policy_extract.py`'s own orchestration tests in
  `tests/test_policy_extract.py` (new file): a fixture `profile` document with two assets - one
  eligible (`policy_doc` a real path), one excluded (`"n/a"`) - processes only the eligible one,
  with zero extraction attempted for the excluded one and no note printed for it (SC-023's
  extraction half); the CLI's optional single-asset-path argument (e.g. `vehicles.primary`)
  restricts processing to just that one asset; the script's own vault read happens exactly once
  regardless of how many eligible assets exist (single passphrase prompt, no N+1 residual, unlike
  `quote_compare.py`)
- [ ] T019j Implement `scripts/policy_extract.py` (new file) per contracts/
  walk-capture-report.md section 9: asset discovery (direct `profile` JSON parse, never
  `ProfileRegistry`), the extract-confirm-cache sequence per eligible asset, the optional
  single-asset CLI argument, zero-argument batch mode
- [ ] T019k Run `python -m pytest -q tests/test_policy_extract.py` and make T019i green against
  the T019j implementation
- [ ] T020 [P] [US2] Write the Progressive walk's own pure-logic tests in
  `tests/test_insurers_progressive.py` (new file): `ProgressiveQuoteErrand.dependencies` contains
  exactly the two verified landing selectors (`#zipCode_mma`, `#qsButton_mma`); `plan()`/`walk()`'s
  first two steps are a `FieldPlan` sourced `registry:addresses.home.zip` targeting `#zipCode_mma`
  and a `ClickStep` targeting `#qsButton_mma`, matching the two selectors verified before this
  feature was scoped (spec FR-031) - no assertion about any step beyond these two, since nothing
  beyond the landing page is proven until implementation-time recon (T022) actually runs
- [ ] T021 [US2] Implement `WALK_REGISTRY` in `headless/insurers/__init__.py` (new package) and a
  landing-page-only `ProgressiveQuoteErrand(Errand)` in `headless/insurers/progressive.py` (new
  file) per T020's assertions: `name = "progressive"`, `HANDOFF` describing the walk's own
  terminal state (research.md D2: e.g. "review the report; nothing further to do in the browser"),
  `dependencies = ["#zipCode_mma", "#qsButton_mma"]`, `url()` returning
  `https://www.progressive.com/auto/`, `walk(registry)` returning the landing `FieldPlan` and
  `ClickStep` only - no funnel steps yet, pending T022
- [ ] T022 [US2] Perform implementation-time recon (research.md D8): at most three headless,
  scratch-Chrome-profile walks against the real Progressive site, synthetic data only, never the
  Director's real identity/address/dob/licence, never a purchase/submit/payment click. Record the
  outcome in `research.md` (a new "Recon results" section, dated): which selectors past the
  landing page resolved (add as further `FieldPlan`/`ClickStep`/`CaptureStep` entries to T021's
  walk), which points could not be automated or verified (add as `HumanStep` entries instead),
  whether an "are you currently insured?" question appears on any page reached and, if so, its
  selector and control shape (fill/select/check) - spec FR-035 - and whether the funnel refused
  headless Chrome at any point (record as evidence for the standing headless-user-agent question
  regardless of outcome) - spec FR-032/FR-033/FR-034, SC-012
- [ ] T023 [US2] Extend `ProgressiveQuoteErrand.walk()` in `headless/insurers/progressive.py` with
  whatever T022's recon actually proved: further `FieldPlan`/`ClickStep` entries for anything
  automatable (including a `FieldPlan` sourced `registry:vehicles.primary.currently_insured` if
  T022 found that question on a reachable page, spec FR-035), `HumanStep` entries for anything
  recon could not cross or verify, and a terminal `CaptureStep` on the quote page with extractors
  named per data-model.md's vocabulary (`premium.amount`, `premium.term_months`,
  `coverage.<slug>.limit`/`.deductible`/`.premium`) for whatever fields the quote page actually
  exposed. MUST NOT reference `identities.spouse.*` or `addresses.rental.*` at any registry path,
  in any step (spec FR-036) - both are seeded in the Director's profile for a future feature, not
  this one. If a referenced field is not yet in `profile.template.json` (repository root, already
  exists on `main`, Amendment 5), extend that one file in this same change - never invent a second
  schema document (spec FR-049); the drift test added in Phase 2 (T058) enforces this.
- [ ] T024 [US2] Update `tests/test_insurers_progressive.py` to cover whatever T023 actually
  shipped (the exact steps recon proved) - this task's scope is bounded by T022's real findings,
  not predicted here. Also add the SC-015 proof: a grep or an AST-walk test over
  `headless/insurers/progressive.py`'s own source confirming it contains no `identities.spouse.`
  or `addresses.rental.` substring at any registry-path reference, so FR-036's guard is checked
  mechanically, not only by the task description above.
- [ ] T025 [US2] Run `python -m pytest -q tests/test_insurers_progressive.py`, then quickstart
  Scenario 3 (`scripts/quote_compare.py --check`, once T029 exists) and Scenario 5 (a real `--apply`
  run) by hand (Director UAT): confirm the landing selectors still probe found, and confirm a
  `reports/captures/progressive-<timestamp>.json` file appears shaped per data-model.md after a
  real apply run

**Checkpoint**: Progressive is a real, working, recon-proven insurer walk. Every selector it ships
is proven, not assumed (FR-032). The capture model is proven against both fixture data and (via
Director UAT) a real quote page.

---

## Phase 5: User Story 3 - The comparison engine and HTML report recommend a quote (Priority: P1)

**Goal**: turn `current_policy` (or its documented absence, FR-046/FR-047) plus whatever captures
exist into a ranked, explained recommendation, and render it as one self-contained HTML file - the
feature's actual deliverable.

**Independent Test**: synthetic `QuoteCapture` fixtures plus a synthetic `current_policy`, run
through the comparison engine and the report generator directly, no browser, no vault (spec.md's
own Independent Test for this story).

- [ ] T026 [P] [US3] Write coverage-line normalization and classification tests in
  `tests/test_compare.py` (new file): two differently-worded fixture line names (e.g. "Bodily
  Injury Liability" and "BI") normalize to the same alias-table key; a captured line classifies as
  better/equal/worse against a matching `current_policy` line per its limit; a captured field with
  an empty-string value classifies as missing
- [ ] T027 [P] [US3] Write ranking-rule tests in `tests/test_compare.py`: a strictly-better,
  cheaper fixture quote outranks `current_policy`; a fixture quote with zero worse lines outranks
  a cheaper fixture quote with one worse line, regardless of price (SC-006); two quotes tied on
  "no worse line" rank by lower normalized premium; a premium-and-worse-line tie breaks by fewer
  missing lines; the rule-trail string for the top-ranked quote states the rule in plain language,
  built only from the same comparison data
- [ ] T028 [P] [US3] Write determinism tests in `tests/test_compare.py`: calling
  `build_comparison` twice with the same fixture inputs (including a `captures` dict constructed
  in a different key-insertion order the second time) produces byte-identical `ranked_quotes`
  ordering and `rule_trail` text both times
- [ ] T028b [P] [US3] Write no-current-policy fallback tests in `tests/test_compare.py`: calling
  `build_comparison(None, captures)` produces a `ComparisonResult` with `has_current_policy is
  False`, every `RankedQuote.line_classifications` empty (no better/worse/equal/missing computed),
  quotes ranked by monthly-equivalent premium (`amount / term_months`) ascending, and a
  `rule_trail` stating plainly that no current policy was on file (spec FR-046)
- [ ] T029 [US3] Implement the coverage-line alias table, `classify_line`, `rank_quotes`,
  `ComparisonResult`, `RankedQuote`, `build_comparison` in `headless/compare.py` (new file) per
  data-model.md's contract and research.md D5/D10 - pure functions, no I/O, no LLM call anywhere
  in this module; `build_comparison`'s `current_policy` parameter accepts `None` per FR-046
- [ ] T030 [US3] Run `python -m pytest -q tests/test_compare.py` and make T026-T028b green against
  the T029 implementation
- [ ] T031 [P] [US3] Write report-structure tests in `tests/test_report.py` (new file): a fixture
  `ComparisonResult` renders a table with one column per fixture quote plus `current_policy`'s own
  column, one row per fixture coverage line, correctly marked cells, a premium row, and a
  recommendation banner naming the fixture's own top-ranked quote and rule trail; a
  `ComparisonResult` with `recommended is None` (empty `ranked_quotes`) renders a plain
  no-comparison-yet statement instead of a broken banner
- [ ] T032 [P] [US3] Write zero-external-reference and value-free-failure-row tests in
  `tests/test_report.py`: a rendered report contains no `http(s)://`, `<script src=`, or `<link
  rel="stylesheet" href=` outside the provenance footer's own plain-text `source_url` values
  (SC-002); a distinctive fixture-shaped failure string passed as part of a `failed` insurer's
  context never appears anywhere in the rendered output for that row - only the fixed "no
  successful capture yet" phrase does (SC-003); the provenance footer names each included
  fixture quote's `fetched_at` and `source_url` and duplicates no other capture field there
  (SC-010)
- [ ] T032b [P] [US3] Write the no-current-policy report test in `tests/test_report.py`: a fixture
  `ComparisonResult` with `has_current_policy is False` renders "no current policy on file" in
  every row of the current-policy column, no better/worse/missing/equal mark on any quote's own
  cells, and a rule-trail statement naming premium-only ranking (spec FR-047, SC-017's report half)
- [ ] T033 [US3] Implement `render_report` and `write_report` in `headless/report.py` (new file)
  per contracts/walk-capture-report.md section 5 - standard-library string construction only
  (research.md D6), `html.escape` on every piece of captured or current-policy text before it
  reaches the output, one inline `<style>` block, no external reference, no required JavaScript;
  `render_report` reads `comparison.has_current_policy` to choose between FR-023's normal rendering
  and FR-047's marker
- [ ] T034 [US3] Run `python -m pytest -q tests/test_report.py` and make T031-T032b green against
  the T033 implementation

**Checkpoint**: the comparison engine and report generator are fully proven against synthetic
fixtures, independent of whether Progressive's own walk (Phase 4) or the orchestrator (Phase 6)
exist yet - this phase's own tests construct `QuoteCapture`/`CurrentPolicy` fixtures directly, with
no dependency on either.

---

## Phase 6: User Story 4 - Multiple insurers run in one invocation, unmapped ones included (Priority: P2)

**Goal**: `scripts/quote_compare.py` - the orchestrator that ties every prior phase together,
composing each mapped insurer's own `Errand` subclass, isolating one insurer's failure from the
rest, and driving the comparison-and-report step only in apply mode, only after every insurer's
walk has finished.

**Independent Test**: `insurance.companies` (inside a fixture `profile` document) seeded with
`["progressive", "geico"]` (a fixture id with no registered walk), run in preview mode, confirming
`geico` produces a "not mapped yet" line with zero browser activity attempted for it (spec.md's
own Independent Test for this story).

- [ ] T035 [P] [US4] Write unmapped-insurer tests in `tests/test_quote_compare.py` (new file): a
  fixture `profile` document whose `feature_configs.insurance.companies` contains an id absent
  from `WALK_REGISTRY`, run in every mode, produces a "not mapped yet" line for that id and
  triggers zero constructions of any `Errand`/`Config`/`Session`-shaped fixture spy for it (SC-007)
- [ ] T036 [P] [US4] Write malformed-input-refuses-first tests in `tests/test_quote_compare.py`: a
  fixture `profile` document whose `feature_configs` or `feature_configs.insurance` object is
  missing, or whose `companies` is malformed, causes the run to refuse before any mapped insurer's
  `Errand` subclass is constructed, for every mode including preview (SC-008). A missing or
  unparseable `reports/policy/vehicles-primary.json` cache file does **not** refuse - the run
  proceeds with `current_policy = None` (spec FR-013/FR-058, T028b/T032b's own fallback behavior);
  this is a deliberate asymmetry from the pre-Amendment-6 design, where a malformed hand-typed
  `current_policy` value used to refuse - there is no hand-typed value to malform any more.
- [ ] T036b [P] [US4] Write excluded-asset tests in `tests/test_quote_compare.py`: a fixture
  targeted asset (`vehicles.primary`) with `currently_insured` or `policy_doc` set to `"n/a"`
  causes zero insurer `Errand` constructions in every mode, one informative exclusion line, and
  (apply mode only) a written report whose content states the exclusion rather than a comparison
  table (spec FR-063, FR-064, SC-023's orchestration half)
- [ ] T037 [P] [US4] Write per-insurer-isolation tests in `tests/test_quote_compare.py`: two
  fixture mapped insurers, the first's `Errand.run()` stubbed to return a non-zero exit code, the
  second's stubbed to return `0` and produce a fixture capture - the orchestrator's apply-mode run
  still calls the second insurer's `run()` and still reaches the report-writing step, with the
  first insurer's failure recorded as a value-free note (SC-005)
- [ ] T038 [P] [US4] Write freshest-capture-wins tests in `tests/test_quote_compare.py`: a fixture
  insurer whose `run()` returns non-zero this invocation, but who has an older capture file already
  on disk from a fixture "prior run," still contributes that older capture to the comparison
  (not a "failed" row), with its own older `fetched_at` value intact in the resulting report input
- [ ] T039 [P] [US4] Write flag-forwarding tests in `tests/test_quote_compare.py`: the
  orchestrator's own `--profile-dir`/`--headless`/`--show`/`--preview-dir`/`--no-screenshot` values
  are present, unchanged, in the argv forwarded to a fixture mapped insurer's `run()` call
- [ ] T040 [US4] Implement `scripts/quote_compare.py` (new file) per contracts/
  walk-capture-report.md section 4: `add_mode_arguments()`-based argparse, the startup sequence
  (parse `profile`, parse `feature_configs.insurance.companies` and refuse before any `Errand` is
  constructed on malformed input, find the targeted `vehicles.primary` asset and check
  `policydoc.is_excluded` before anything else runs, partition mapped/unmapped), per-mode dispatch
  (excluded: one line, zero insurer runs, apply-mode-only exclusion report; preview/check: run each
  mapped insurer's own `Errand.run()` in that mode plus print unmapped insurers; apply: run each
  mapped insurer's own `Errand.run()` in sequence recording exit codes, then
  `read_freshest_capture` per mapped insurer and `capture.read_policy_reference("vehicles-primary",
  ...)`, then `compare.build_comparison`, then `report.render_report`/`write_report`), the
  exit-code rule (0 when a report was written - including the exclusion-case report, 1 for a
  pre-flight refusal, 2 for a usage error)
- [ ] T041 [US4] Run `python -m pytest -q tests/test_quote_compare.py` and make T035, T036,
  T036b, T037, T038, T039 all green
  against the T040 implementation
- [ ] T042 [US4] Run the structural typing test against the new script:
  `python -m pytest -q tests/test_no_direct_typing.py` - `scripts/quote_compare.py` must pass
  unmodified (it only ever calls another `Errand` subclass's `.run()`, never a locator method
  directly, so no change to `FORBIDDEN_ATTRS` or `EXCLUDED` should be needed; if it is, that is a
  sign `quote_compare.py` reached into a page directly instead of composing an `Errand`, and the
  implementation needs correcting, not the test)
- [ ] T043 [US4] Run quickstart Scenarios 1-10 by hand (Director UAT): seed `profile`'s
  `identities`/`addresses`/`vehicles`/`feature_configs` via the `get`/edit/`set`/`verify` round
  trip (Scenarios 1-2), confirm the `--check`/preview/apply sequence, confirm the HumanStep
  etiquette and the trailing handoff, confirm the report renders correctly, run
  `scripts/policy_extract.py` against a real policy PDF and confirm the candidate (Scenario 8 -
  this is also the first real-PDF proof of the extraction heuristics, research.md D15's own
  accepted-residual tuning work starts here), confirm the excluded-asset "n/a" case produces zero
  insurer journeys and an exclusion-stating report (Scenario 9), and confirm the malformed-input
  refusal path (Scenario 10). Scenario 7 (multi-insurer failure isolation on a real second
  insurer) is not exercisable until a second insurer has its own future spec and its own
  registered walk - defer its real-site half; T037's fixture test already proves the mechanism.

**Checkpoint**: every user story independently proven; the orchestrator ties Phases 2-5 together
without any of them needing to change. The report the Director asked for exists and is correct
against both fixture data (automated) and a real Progressive quote (Director UAT).

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T044 [P] Update `CLAUDE.md`'s Secrets section: name `feature_configs.insurance.companies`
  as living inside `profile` (not a separate item), the deletion of `current_policy` in favor of
  per-asset `policy_doc` extraction and confirmation (D15), and `reports/`'s (including
  `reports/policy/`'s) vault-grade classification (mirroring `previews/`'s existing sentence).
  Confirm whether `vault.py get`'s and `vault.py verify`'s deliberate, sole print-a-value
  exceptions (already shipped in v0.0.4.1/v0.0.4.2, spec FR-039/FR-039b) are already recorded here
  from those hotfixes' own docs-of-record updates; if not, add sentences naming both exceptions
  and their scope so this file stays the accurate constitution of record for the vault's own
  never-print-a-value convention.
- [ ] T045 Regenerate `.specify/memory/constitution.md`: version bump assessed against the actual
  wording change once T044 and T046-T049 exist (plan.md's own note: likely PATCH, extending
  existing hard rules' reach rather than adding a new one - confirm or revise against the real
  diff, do not assume PATCH without checking)
- [ ] T046 [P] Add three new entries to `PATTERNS.md`: the sanctioned-click pattern
  (`Session.click`, mirroring `Session.fill`'s "the only sanctioned way" framing and the structural
  `tests/test_no_direct_typing.py` guarantee), the walk-entry pattern (`Errand.walk()` defaulting
  to `plan()`, the mode matrix, the window-stays-visible-after-first-HumanStep rule), and
  `reports/`'s vault-grade classification (mirroring `previews/`'s own entry, noting the
  accumulates-vs-overwrites distinction between `captures/` and the dated report)
- [ ] T047 [P] Update `scripts/README.md`: a new "Orchestrators" section documenting
  `scripts/quote_compare.py` as distinct from Maintenance and Errands (it composes other `Errand`
  subclasses rather than being one itself); a short amendment to the existing "Errand contract"
  section describing `walk()`/`HumanStep` etiquette for any future errand that adopts the walk
  framework, alongside the unchanged `plan()`-only contract for one that does not. (`vault.py`'s
  own `get NAME` row was already added to this file's Maintenance table by hotfix v0.0.4.1 on
  `main`, ahead of this feature - no action needed here for it; T052 below is the only
  `get`-related task this delivery carries.)
- [ ] T048 Add the v0.0.5 Changelog row to `Project_Structure.md` listing every file touched
  (`headless/steps.py` [new], `headless/session.py`, `headless/errand.py`, `headless/preview.py`,
  `headless/profile.py` [array addressing, `RegistryAmbiguous`], `headless/capture.py` [new],
  `headless/compare.py` [new], `headless/report.py` [new], `headless/policydoc.py` [new],
  `headless/insurers/__init__.py` [new], `headless/insurers/progressive.py` [new],
  `scripts/quote_compare.py` [new], `scripts/policy_extract.py` [new], `requirements.txt`
  [pypdf], `.gitignore`, every new/updated test file, plus every docs-of-record file touched in
  this phase) and new Application Layer rows for the new modules, the new package, and `reports/`
  (including `reports/policy/`)
- [ ] T049 [P] Update `Function_Mapping.md`: a row for `headless/insurers/progressive.py`'s
  `ProgressiveQuoteErrand` (site, reads, writes-up-to, secrets/profile fields per whatever T022's
  recon actually shipped, handoff point); a note that `scripts/quote_compare.py` is an orchestrator
  composing other errands, not an errand itself, and has no row of its own here
- [ ] T050 [P] Update `MEMORY.md`: record the Director's decision (this feature's own brief,
  2026-08-25) under a dated entry; add "Errands run" rows once Director UAT (T025, T043) produces
  real outcomes to record - site/tool name and PASS/FAIL only, never a captured premium or coverage
  figure
- [ ] T052 Verify (do not implement or test) that this spec set's own references to
  `scripts/vault.py get NAME` and `scripts/vault.py verify` - spec.md FR-037 through FR-039b,
  contracts/walk-capture-report.md sections 6 and 11, and quickstart.md Scenarios 1, 2, and 14
  (the seeding round trip, the `verify` check, and the later revise-it round trip) - match the
  actual shipped CLI on `main` (hotfix v0.0.4.1 commit `9cc3b20` for `get`, hotfix v0.0.4.2 for
  `verify`) once this worktree's `v0.0.5` branch has merged forward from or been rebased onto
  current `main`. Also verify quickstart.md's own references to `profile.template.json`
  (Scenario 1's seeding example, Scenario 14's own extension note) match the actual shipped
  file's real shape once this worktree has it (research.md D14). This is a documentation-accuracy
  check against already-shipped code - it adds no implementation and no test of any of it to this
  delivery.
- [ ] T053 Run the commit gate: `python -m pytest -q && python scripts/verify_structure.py &&
  git add -A && python scripts/scan_secrets.py --staged` - the orchestrator (or an Opus verifier,
  per the global agent conventions) reviews before any commit; committing itself happens on the
  Director's explicit instruction, not automatically at the end of this task list

---

## Dependencies & Execution Order

- **Setup (Phase 1)** -> **Foundational (Phase 2, including Phase 2b)** -> user stories.
- **US1 (Phase 3)** depends only on Phase 2 (the `Step` kinds and `Session.click`/`capture` must
  exist before `Errand.walk()`'s dispatch loop can be tested against them). Independent of Phase
  2b's array-addressing and extraction work.
- **Phase 2b** (T019b-T019k, the array-addressing task cluster T054-T059, and the
  `policydoc`/`policy_extract` task cluster) is its own Foundational sub-phase: it depends only on
  Phase 2's own `Step`/`Session` work being done first (so its own test files do not collide with
  Phase 2's), not on Phase 3-6. `compare.build_comparison`'s `current_policy: CurrentPolicy | None`
  parameter (Phase 5) and `quote_compare.py`'s own cache read (Phase 6) both depend on
  `headless/policydoc.py` existing (T019g) - this is Phase 2b's own critical path.
- **US2 (Phase 4)** depends on Phase 2 (the walk framework `ProgressiveQuoteErrand.walk()` is
  built against) and, for its capture-writing tasks (T017-T019), on nothing from Phase 3 - the
  capture model is independent, pure-data work. T022's recon and T023's walk extension are the
  critical path for how deep the shipped walk actually goes; every other task in this phase can
  start immediately.
- **US3 (Phase 5)** depends on nothing from Phase 4, but does depend on Phase 2b's `CurrentPolicy`/
  `headless/policydoc.py` existing for its own `current_policy: CurrentPolicy | None` fixtures
  (T026-T028b, T031-T032b) - not on a real Progressive capture or a real extraction, only on the
  shapes themselves. It can proceed in parallel with Phase 4 once Phases 2 and 2b are done.
- **US4 (Phase 6)** depends on Phase 4 (needs at least one real mapped insurer, `progressive`, to
  compose) and Phase 5 (needs `compare.build_comparison`/`report.render_report` to call) - it is
  the integration phase that ties everything together, so it is sequenced last among the stories,
  the same "validation lands last, mechanism came first" reasoning spec 003's and spec 004's own
  final phases already used.
- **Polish (Phase 7)** last. T052 specifically has its own external precondition beyond this
  feature's own task graph: it cannot run until `v0.0.5` has merged forward from, or been rebased
  onto, current `main` (research.md D12) - it may end up the last task actually completed in this
  phase, after T053's own commit gate, if that merge happens after everything else here is done.

### Parallel Opportunities

- T002, T003, T004 together (different test concerns, written before T005-T007 exist).
- T009, T010, T011 together (same file, disjoint test functions, written before T013 exists); T012
  can start alongside them.
- T016, T017 together (same new file, disjoint test functions, written before T018 exists).
- T020 can start as soon as Phase 2 lands, independent of T016-T019.
- T026, T027, T028 together (same new file, disjoint test functions, written before T029 exists).
- T031, T032 together (same new file, disjoint test functions, written before T033 exists); this
  phase (US3) overall can run in parallel with Phase 4 (US2) once Phase 2 is done.
- T035, T036, T037, T038, T039 together (same new file, disjoint test functions, written before
  T040 exists).
- T044, T046, T047, T049, T050 together (five different docs-of-record files, no shared state).

## Implementation Strategy

MVP is Phases 1-3: with those, the walk framework exists, is proven safe (preview never navigates
past landing) and correct (all four step kinds dispatch in order, the window-visibility rule
holds), and is fully backward compatible with every prior errand - but nothing insurer-specific
exists yet, so there is nothing to demo to the Director at this checkpoint beyond the fixture
tests themselves. Phases 4 and 5 (US2, US3) can proceed in parallel once Phase 2 lands, since
neither depends on the other - Phase 4 needs the walk framework and produces real capture files;
Phase 5 needs only synthetic fixtures and produces the comparison engine and report generator that
will eventually read those real captures. Phase 6 (US4) is the integration phase: it is where the
Director first sees the actual deliverable (a real report, from a real Progressive quote, compared
against his real current policy) - sequenced last not because it is less important, but because it
needs Phases 4 and 5 both finished to compose. Commit once at the end of Phase 7 after the gate
passes; the orchestrator or an Opus verifier reviews before the commit step - none of that happens
in this spec-authoring delivery, per this feature's own brief.
