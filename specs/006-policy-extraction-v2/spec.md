# Feature Specification: Policy Extraction v2 (Layout-Aware Conversion Plus a Local Model)

**Feature Branch**: `v0.0.6` (spec directory `006-policy-extraction-v2`)

**Created**: 2026-08-29

**Status**: Draft

**Input**: User description: "I see reading issue when using policy_extract.py. Shouldn't we use
pdf to md converter and use a little AI (maybe local llm) to identify policy values."

## Why

`scripts/policy_extract.py` (v0.0.5) reads a policy PDF's text with `pypdf` and applies regex
heuristics to find a premium, a term, and coverage limits. Against the Director's first real
document - a three-page homeowners declarations PDF with a full text layer - `pypdf` read the
text in the wrong order: a multi-column layout came back scrambled (the observed text ran
"12/01/2026To:12/01/2025From:Policy Period:" - the two dates and both labels interleaved and
reversed). No regex heuristic can reliably parse text in that shape. The same real-world
declarations page also exposed a second, independent gap: home insurance policies are annual, so
the page never contains an "N-month" phrase the v0.0.5 term regex looks for - the term has to be
worked out from the policy-period dates themselves, which v0.0.5 never attempted.

This feature replaces `policy_extract.py`'s candidate-generation step with a layout-aware PDF
conversion followed by a local (never cloud) language model that proposes a candidate from the
converted text, gated by a new mechanical check that strips any figure the model invents. Every
other part of the v0.0.5 pipeline - the Director's own mandatory review and correction, the
`reports/policy/` cache, and everything the comparison engine reads from it - continues exactly as
it already does.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The Director's real declarations PDF yields a correct confirmed reference (Priority: P1)

The Director runs `scripts/policy_extract.py` against his own real homeowners declarations PDF -
the same document whose scrambled column order defeated v0.0.5. With his local Ollama model
running, the tool converts the PDF with layout awareness, proposes a candidate, and correctly
derives a 12-month term from the policy-period dates even though the document itself never states
"12-month." He reviews the printed candidate at the existing confirmation prompt and accepts it.

**Why this priority**: this is the defect the Director actually hit. Without it, the extraction
path he depends on for his own real insurance documents stays broken exactly as UAT found it -
every other part of this feature exists to make this one outcome safe to ship.

**Independent Test**: run `scripts/policy_extract.py` against a wholly synthetic fixture that
reproduces the same scrambled-column, no-explicit-term shape as the real document, with an
injected fake local-model transport returning a valid, schema-conformant candidate. Confirm the
resulting cached reference carries the correct figures and `term_months` `"12"`, derived from the
two dates rather than a stated term phrase.

**Acceptance Scenarios**:

1. **Given** a converted document whose text contains two policy-period dates eleven to thirteen
   months apart and no "N-month" phrase, **When** extraction runs, **Then** the confirmed
   reference's `term_months` is `"12"`.
2. **Given** a converted document whose column order the source PDF originally scrambled,
   **When** the layout-aware converter succeeds, **Then** the candidate's figures are read from
   correctly-ordered text, not the scrambled order a plain text extraction would have produced.
3. **Given** a candidate the local model proposes, **When** the Director is shown the
   confirmation prompt, **Then** he sees the same accept-correct-decline choice v0.0.5 already
   offers, unchanged.

---

### User Story 2 - Nothing unconfirmed or non-local ever feeds a figure (Priority: P1)

Whatever the local model proposes, nothing reaches the `reports/policy/` cache or the comparison
engine until it has passed a mechanical check that strips any figure absent from the source
document, and until the Director has explicitly confirmed it. The model itself never runs
anywhere but the Director's own machine.

**Why this priority**: this is the constitutional floor the rest of the feature sits on.
Introducing a model into the extraction path is only acceptable if it cannot regress the rule
that kept the path trustworthy before this feature existed (spec 005's own FR-051: "no LLM call
at any point"). Without this story, the feature would trade a known extraction gap for an
unbounded one.

**Independent Test**: construct a candidate carrying a figure that does not appear anywhere in the
source text and assert the mechanical check removes it before `confirm_candidate` is ever called.
Set `HEADLESS_OLLAMA_URL` to a non-local host and assert configuration refuses before any
conversion, extraction, or network call happens.

**Acceptance Scenarios**:

1. **Given** a local-model candidate proposing a coverage limit that does not appear anywhere in
   the converted source text, **When** the mechanical check runs, **Then** that figure is removed
   from the candidate and replaced by a value-free warning, and the Director's own confirmation
   prompt never shows the invented figure.
2. **Given** `HEADLESS_OLLAMA_URL` set to any host other than `localhost` or `127.0.0.1`,
   **When** `scripts/policy_extract.py` starts, **Then** the run refuses with a value-free
   configuration error before any PDF conversion or network call occurs.
3. **Given** a local-model candidate that passed the mechanical check, **When** the Director
   declines it at the confirmation prompt, **Then** no cache file is written, exactly as v0.0.5
   already behaves for a declined candidate.

---

### User Story 3 - Graceful degradation without Ollama (Priority: P2)

The Director's machine does not have Ollama running, the configured model is not pulled, or the
call times out. The tool notices, falls back automatically to the same regex heuristics v0.0.5
shipped, and the run still completes - a local model being unavailable on a given day never blocks
the Director from extracting a policy reference.

**Why this priority**: valuable resilience, but the tool remains usable, at v0.0.5's own prior
capability, even without a working local model. This is the safety net behind User Story 1, not
the story's own headline value.

**Independent Test**: inject a fake transport that raises a connection error and confirm the run
still produces the same regex-generated result v0.0.5's own test suite already covers, plus one
value-free note naming the fallback.

**Acceptance Scenarios**:

1. **Given** Ollama is unreachable at the configured URL, **When** extraction runs, **Then** one
   value-free note prints, the regex-based generator produces the candidate instead, and the run
   completes with the same exit code v0.0.5 would have produced.
2. **Given** the Director passes `--no-llm`, **When** extraction runs, **Then** no local-model
   request is ever constructed and every candidate comes from the regex-based generator.
3. **Given** a converted document from which the regex-based generator itself cannot parse any
   coverage line, **When** extraction runs, **Then** the outcome is the same "no candidate to
   confirm" result v0.0.5 already defines for that case - not a crash and not treated as a
   failure of the whole run.

### Edge Cases

- A three-page declarations PDF whose original column order pypdf's own plain-text extraction
  scrambles (the real, verified failure this feature is scoped from) - see User Story 1.
- An annual policy whose declarations page never states "6-month" or "12-month" anywhere -
  the term must be derived from the two policy-period dates instead (User Story 1).
- A local model that spends its output on its own internal reasoning and returns an empty
  response field even though the request explicitly disabled that behavior - treated as a failed
  local-model attempt, never a crash, never an empty candidate (User Story 3's own fallback path).
- A local-model candidate proposing a figure that exists nowhere in the source document (a
  hallucination) - stripped by the mechanical check before the Director ever sees it (User Story
  2).
- `HEADLESS_OLLAMA_URL` pointed at a non-local host - refused before any conversion, extraction,
  or network call (User Story 2).
- Ollama not installed, not running, or the configured model not pulled - one value-free note,
  automatic fallback to the regex-based generator, the run still completes (User Story 3).
- A standalone deductible line the converted layout does not visually attach to any particular
  coverage row (an observed residual even on a clean synthetic test) - not corrected
  automatically; it surfaces, unattached, at the Director's own confirmation prompt for him to
  accept as printed or correct by hand, the same accept-or-correct choice he already has.
- The layout-aware converter itself is unavailable (its package failed to import) - extraction
  falls back to the existing `pypdf` raw-text path with one value-free note, and everything
  downstream behaves exactly as v0.0.5 already does against that raw text.
- A converted document with no extractable text at all - the same "nothing to offer the Director"
  outcome (`None`, no candidate) v0.0.5 already defines for an unreadable PDF.

## Requirements *(mandatory)*

### Functional Requirements

**Conversion**

- **FR-001**: `scripts/policy_extract.py`'s extraction step MUST convert a `policy_doc` PDF's
  content to layout-aware Markdown text before generating any candidate from it.
- **FR-002**: When the layout-aware converter cannot be imported, or its conversion call raises,
  extraction MUST fall back to the existing `pypdf` raw-text extraction (v0.0.5's own path) and
  record which converter served the run in the candidate's own provenance (FR-023).
- **FR-003**: The layout-aware converter dependency MUST be recorded as an ordinary (not a
  separate optional) entry in `requirements.txt`.

**Local-model candidate generation**

- **FR-004**: Candidate generation MUST attempt a local model first, unless the Director passes
  `--no-llm` (FR-014); the regex-based heuristics that shipped in v0.0.5 remain in the codebase
  as the automatic fallback generator, used whenever the local-model attempt does not produce a
  usable candidate.
- **FR-005**: The local-model request MUST be an HTTP POST whose JSON body contains at minimum
  `"model"`, `"prompt"`, `"format": "json"`, `"stream": false`, `"think": false`, and
  `"options": {"temperature": 0}`.
- **FR-006**: The model name and the local endpoint MUST each resolve through this codebase's
  existing configuration path (`headless/config.py`), the same way every other environment-driven
  setting already does, defaulting to a named model and `http://localhost:11434` respectively.
- **FR-007**: Configuration MUST refuse, with a value-free configuration error, any local-model
  endpoint whose host is not `localhost` or `127.0.0.1` - the policy document's text and its
  converted content MUST NEVER be sent to a non-local endpoint.
- **FR-008**: The local-model call MUST use a bounded timeout, exactly one attempt, and no retry
  loop.
- **FR-009**: The component that performs the local-model HTTP call MUST be an injectable
  callable, so that no unit test ever opens a real network connection or reaches a real local
  model process.
- **FR-010**: A response that is not valid JSON, or that does not match the expected candidate
  schema (a missing or wrong-typed `insurer`, `premium`, or `coverages` field), MUST be treated as
  a failed local-model attempt - never as a partial or best-effort candidate.
- **FR-011**: An empty response body MUST be treated the same as a non-JSON response under
  FR-010 - a failed attempt, never a crash and never an empty candidate.
- **FR-012**: A connection failure, or a response indicating the requested model is not
  installed, MUST be treated the same as a failed local-model attempt under FR-010.

**Fallback and degradation**

- **FR-013**: Any failed local-model attempt (FR-010 through FR-012, or the timeout in FR-008)
  MUST produce exactly one value-free note and fall back automatically to the regex-based
  generator - never a hard refusal of the run, and never a partially-populated candidate built
  from the failed attempt.
- **FR-014**: `scripts/policy_extract.py` MUST accept a `--no-llm` flag that skips the
  local-model attempt entirely, generating every candidate through the regex-based generator,
  unchanged from v0.0.5's own behavior.
- **FR-015**: A converted document with no extractable text MUST continue to produce no candidate
  (`None`) - the same outcome v0.0.5 already defines for an unreadable PDF or a zero-coverage-
  lines extraction.
- **FR-016**: `scripts/policy_extract.py`'s exit codes MUST remain unchanged from v0.0.5 (`0` on
  completion regardless of how many assets were skipped, declined, or extracted with zero lines;
  `1` on a vault-level refusal; `2` on a usage error).

**Mechanical sanity pass**

- **FR-017**: Before any candidate, from either generator, reaches `confirm_candidate`, every
  figure string it proposes (the premium amount, and each coverage line's own limit, deductible,
  and premium) MUST be checked for literal presence in the converted source text, comparing both
  sides after stripping currency symbols, commas, and whitespace and reducing each to its own
  digit sequence.
- **FR-018**: A proposed figure absent from the normalized source text under FR-017 MUST be
  removed from the candidate and replaced by a value-free warning naming only the field it was
  removed from - never the figure's own value, and never a fragment of surrounding source text.
- **FR-019**: `term_months` MUST be exempt from the literal-match check in FR-017 only when it
  was derived by the deterministic date-arithmetic helper (FR-021) from two policy-period dates
  found in the converted text; a `term_months` value proposed any other way (an explicit
  "N-month" phrase, or an unexplained model guess) remains subject to FR-017.
- **FR-020**: When a local-model candidate's own claimed `term_months` disagrees with the value
  the date-arithmetic helper (FR-021) derives from the same converted text, the helper's own
  derivation MUST replace the model's claim, and the candidate MUST carry a value-free note
  recording that the derived term overrode the model's claim.

**Term derivation**

- **FR-021**: A new deterministic helper MUST locate two dates, in common United States date
  formats, appearing near a policy-period label in the converted text, and compute a term by
  calendar-month arithmetic between them: a computed span of eleven to thirteen months yields
  `"12"`; a span of five to seven months yields `"6"`; any other span yields the exact rounded
  month count as a string, accompanied by a value-free warning that the term fell outside the two
  common terms.
- **FR-022**: The helper in FR-021 MUST be usable by both the local-model generator and the
  regex-based generator, so that an annual policy with no "12-month" phrase resolves a term
  through either generator, not only the local-model one.

**Provenance**

- **FR-023**: The confirmed reference cached by `write_policy_reference` MUST record, alongside
  every field it already records, which generator produced the confirmed candidate
  (`"regex-v1"` or `"local-llm:<model-name>"`) and which converter produced the source text
  (the layout-aware converter's own name, or `"pypdf-raw"`).
- **FR-024**: The comparison report's provenance footer MUST surface the generator and converter
  fields recorded under FR-023, alongside the `source_path` and `confirmed_at` fields it already
  surfaces.

**Confirm gate and constitutional boundary**

- **FR-025**: `ExtractionCandidate`, `confirm_candidate`, `PolicyReference`, `write_policy_
  reference`, `read_policy_reference`, and `scripts/quote_compare.py`'s own consumption of a
  confirmed reference MUST remain exactly as v0.0.5 shipped them, except for the additive
  provenance fields in FR-023.
- **FR-026**: No candidate MUST ever be cached, and no candidate MUST ever reach the comparison
  engine, without passing through the unchanged confirmation step that already exists for this
  purpose - a local-model-generated candidate is never treated as pre-confirmed, and the
  mechanical sanity pass (FR-017 through FR-020) MUST run before, never in place of, that
  confirmation step.
- **FR-027**: Model output of any kind MUST NOT be typed into any site by any errand - the
  existing "nothing an LLM derives is ever typed" rule is unaffected by this feature; the local
  model's only sanctioned output is a candidate a human reviews and confirms.
- **FR-028**: An insurer's own name and a coverage line's own name are text fields, not figures,
  and are exempt from the sanity pass in FR-017; they continue to surface for the Director's own
  review at the existing confirmation prompt exactly as v0.0.5 already presents them.

**Locality**

- **FR-029**: No policy document text, no converted text, and no candidate content MUST ever be
  sent to a network endpoint other than the local endpoint enforced by FR-007 - this feature MUST
  NOT call, or offer a code path toward, a cloud-hosted model of any kind.

### Non-Functional Requirements

- **NFR-001**: The default `pytest -q` run MUST exercise every path above using injectable fakes
  only - a fake converter, a fake local-model transport (covering a canned valid response, an
  empty-response case, a malformed-JSON case, and a schema-mismatch case), and a hallucinated-
  figure candidate the sanity pass must strip - with zero real network calls, zero real local-
  model process invocations, and zero real PDF file dependencies.
- **NFR-002**: An opt-in integration test, gated by `HEADLESS_TEST_OLLAMA=1`, MAY run the real
  local-model seam against a wholly synthetic, scrambled-order snippet and MUST assert only that
  the response parses into the expected schema shape - never an exact value, since a real model's
  own wording can vary between runs.
- **NFR-003**: Every test fixture this feature adds MUST contain no real policy value, name,
  policy number, or premium - wholly synthetic content only, matching this codebase's existing
  fixture convention.
- **NFR-004**: The new and changed test modules together MUST run in comparable time to v0.0.5's
  own equivalent addition (well under one second combined), since none of them touch a real
  network, process, or filesystem PDF.

### Key Entities

- **ConvertedDocument**: the layout-aware (or, on fallback, raw) text produced from a `policy_doc`
  PDF, plus which converter produced it. In-memory only; never written to disk.
- **ExtractionCandidate**: unchanged from v0.0.5 - the best-effort, unconfirmed proposal a
  generator produces, now populated by either the local-model generator or the regex-based one.
- **PolicyReference**: v0.0.5's confirmed, cached reference, extended with the generator and
  converter provenance fields (FR-023).
- **Term derivation result**: the outcome of the FR-021 helper - a term string plus, when the
  computed span fell outside the two common terms, a value-free warning.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given a converted document whose text carries two policy-period dates eleven to
  thirteen months apart and no "N-month" phrase, extraction derives `term_months` `"12"` -
  matching the real-world gap this feature was scoped from and the behavior already proven
  against a synthetic scrambled snippet during research for this feature.
- **SC-002**: A candidate figure absent from the converted source text is never present on the
  candidate shown at the Director's own confirmation prompt - proven by a unit test that
  constructs a hallucinated figure and asserts the sanity pass removes it before
  `confirm_candidate` is ever called.
- **SC-003**: Setting the local-model endpoint to any host other than `localhost` or `127.0.0.1`
  refuses the run with a value-free configuration error before any conversion, extraction, or
  network call happens.
- **SC-004**: When the local model is unreachable, its configured name is missing, or a call
  times out, `scripts/policy_extract.py` still produces a result (a confirmed reference, a
  decline, or a "no candidate" outcome) for every eligible asset via the regex-based fallback -
  never a hard failure of the whole run.
- **SC-005**: `python scripts/policy_extract.py --no-llm` reaches every confirmation prompt
  without ever constructing a local-model request, verified by a unit test that fails if the
  injectable transport is invoked at all.
- **SC-006**: The full `pytest -q` suite, including this feature's own new tests, completes with
  zero real local-model invocations, zero real network connections, and zero real PDF file reads -
  the same zero-external-dependency property v0.0.5's own extraction suite already holds.
- **SC-007**: An asset whose converted document carries no extractable text still yields `None`
  (no candidate), never a crash, matching v0.0.5's own existing behavior for that case.
- **SC-008**: The confirmed reference cached for an asset names, in its own JSON, which generator
  and which converter produced it, so a later reader (the Director inspecting the cache file
  directly, or the comparison report's own footer) can always tell whether a given figure was
  regex-derived or local-model-derived.

## Assumptions

- The Director's own machine already has a local model pulled and reachable through Ollama's
  default port before he runs this feature's local-model path; this feature does not install,
  configure, or pull a model on his behalf.
- The layout-aware converter's dual open-source/commercial license is acceptable for this
  personal tool, which is never distributed or run as a service on anyone else's behalf; a
  `requirements.txt` entry for a dependency does not relicense this repository.
- The mandatory Director confirmation step (unchanged from v0.0.5) remains the final safety net;
  the mechanical sanity pass this feature adds reduces, but does not eliminate, the chance of an
  incorrect figure reaching that confirmation prompt - correcting a candidate by hand remains the
  Director's own recourse, exactly as v0.0.5 already provides.
- A future feature may swap in a different local model, or a different layout-aware converter,
  without changing the confirmation-gate contract, since both sit behind fixed function
  boundaries this feature establishes.

## Out of Scope

- OCR for an image-only PDF with no text layer at all.
- Any cloud-hosted model, under any configuration - the local-only enforcement in FR-007 and
  FR-029 is permanent policy, not a temporary default.
- Auto-accepting a candidate without the Director's own confirmation, at any confidence level.
- This repository's separate `local-llm-batch` parity-register process, which governs bulk,
  mechanically-validated jobs across other personal tools; this feature's own local-model seam
  has its own, stronger gate (the mechanical sanity pass plus mandatory human confirmation on
  every single document) and is not registered there.
- Any change to `headless/compare.py`'s comparison or ranking logic, or to `headless/report.py`'s
  rendering, beyond the provenance pass-through in FR-024.
