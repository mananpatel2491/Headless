# Feature Specification: Extraction Fidelity (Composite Figures, Correct Terms, Visible Warnings)

**Feature Branch**: `v0.0.7` (spec directory `007-extraction-fidelity`)

**Created**: 2026-08-29

**Status**: Draft

**Input**: User description: "Execute the approved v0.0.7 fix/extension plan for the
policy-extraction feature - an independent audit probe-proved that the figure gate strips
verbatim composite figures, the term derivation mis-pairs dates on 2 of 3 real documents and
overrides the model, converter glue defeats phrase detection, and stripped-figure warnings never
reach the cache or the confirm prompt."

## Why

An independent audit, run 2026-08-29 against three of the Director's own real declarations PDFs
(never reproduced in this repository, at any point, with any real value), probe-proved that
`scripts/policy_extract.py`'s v0.0.6 pipeline (spec 006-policy-extraction-v2) has four defects that
each destroy or mislead a confirmed reference, plus one narrower gap:

- The mechanical sanity pass (spec 006 FR-017, FR-018) strips a figure the moment its own proposed
  string is not, in its whole cleaned form, an exact match for one source digit-run token. A real
  declarations page states many figures as a composite string built from more than one digit run in
  the same cell - a split personal-liability limit written as one line ("<amount> each
  person/<amount> each accident"), a per-row deductible carrying its own row label ("<amount> All
  peril"), or a policy number rendered with internal spaces ("NNN NNN NNN"). Each of these contains
  every one of its own digit runs verbatim in the source text, but the current check demands the
  entire cleaned string - digits, spaces, and label words together - match a single source token, so
  it strips all three as if they were invented. Probed live: feeding one of the three documents its
  own coverage-table text back to itself still stripped that document's own liability limits. Across
  the three confirmed caches the audit built, eight decision-critical figures were destroyed this
  way, leaving one auto policy's own reference with no liability limits at all.
- The term-derivation helper (spec 006 FR-021) finds the first occurrence of a policy-period label,
  opens a window on both sides of it, and takes the first two dates it finds in that window. A real
  declarations page often states an unrelated date (a statement date, an issue date) within that
  window before the label itself. On two of the three real documents, the helper paired that
  unrelated date with the real period's own start date, derived a term of three months and zero
  months respectively, and then overrode the local model's own correct claim under spec 006's own
  FR-020 override rule - the third document escaped only because it happened to have no unrelated
  date nearby.
- The layout-aware converter glues adjacent table cells together at their own visual boundary
  ("Total6month", "Allperil", "eachperson" - reconstructed shapes from the audit, not any
  document's own real text). This gluing corrupts a proposed value once it survives into a cached
  reference, and it defeats the "N-month"/"6-month" phrase pattern spec 006's own term-derivation
  path already looks for before ever falling back to date arithmetic.
- The sanity pass's own `warnings` list, already computed on every candidate, is dropped by
  `PolicyReference.to_dict()` before a reference is ever cached, and the confirmation prompt never
  gives it a distinct, hard-to-miss presentation of its own - it is only ever visible buried inside
  the full candidate JSON block the prompt already prints. The Director confirmed all three of the
  audit's own corrupted caches with no explicit strip-count signal in front of him.
- A narrower gap, not a defect in existing behavior: `headless/compare.py`'s coverage-line alias
  table carries six auto-insurance line names and zero homeowners line names, so a real homeowners
  policy's own coverage-line wording has no shared alias to match against a differently-worded
  competing quote.

This feature amends spec 006 FR-017 through FR-022 (the sanity-pass literal-match rule and the
term-derivation helper), extends spec 006's own `ConvertedDocument`/`ExtractionCandidate`/
`CurrentPolicy`/`PolicyReference` shapes, extends `headless/compare.py`'s alias table, and adds a
context-window guard to the local-model call - all within the confirmation-gated pipeline spec 006
already established. It does not reopen spec 006's own local-only, confirm-gated constitutional
floor: no candidate, from either generator, reaches the cache or the comparison engine without the
unchanged mandatory confirmation step.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A verbatim composite figure survives the gate (Priority: P1)

The Director runs extraction against a declarations page whose coverage table states a limit as one
composite string built from two dollar amounts and their own row labels, or a policy number with
internal spaces. Every digit run in that composite string is present, verbatim, in the source text.
The corrected sanity pass leaves the figure exactly as printed - it is never stripped as a
hallucination.

**Why this priority**: this is the defect that destroyed real liability limits during the audit.
Every other part of this feature exists around a pipeline that must first stop erasing the figures
it already extracted correctly.

**Independent Test**: construct a synthetic fixture whose source text states a composite,
multi-digit-run figure verbatim, and a candidate that proposes that exact composite string. Assert
the corrected sanity pass leaves every one of its digit runs untouched, while a fixture proposing a
figure whose digit run does not appear anywhere in the source is still stripped.

**Acceptance Scenarios**:

1. **Given** a source text stating a coverage limit as two dollar amounts joined by a slash and a
   row label ("<amount> each person/<amount> each accident"-shaped), **When** a candidate proposes
   that exact string, **Then** the corrected sanity pass leaves it unchanged and adds no warning for
   that field.
2. **Given** a source text stating a policy number with internal spaces between three digit groups,
   **When** a candidate proposes that same spaced string, **Then** the corrected sanity pass leaves
   it unchanged - each of the three digit groups is checked as its own token, never as one merged
   blob.
3. **Given** a source text that states only a six-figure limit, **When** a candidate proposes a
   figure sharing a digit-run suffix or prefix with that limit but not equal to any of the source's
   own tokens, **Then** the corrected sanity pass still strips it and records a value-free warning -
   spec 006's own anti-hallucination guarantee is unchanged by this fix.
4. **Given** a candidate figure with no digit at all, **When** the sanity pass runs, **Then** it
   passes through untouched, exactly as spec 006 already defines.

---

### User Story 2 - The derived term reflects the real policy period, never a nearby unrelated date (Priority: P1)

The Director runs extraction against a declarations page that states an unrelated date (a statement
date, an issue date) near the policy-period label, ahead of the label's own two real period dates.
The corrected term-derivation helper finds every occurrence of the label, searches only after each
occurrence, and derives the term from the real period's own earliest and latest date - never from
the unrelated date.

**Why this priority**: a wrong derived term silently overrides the local model's own correct claim
under spec 006's own FR-020 rule, so this defect turns a correct extraction into an incorrect one
without any warning at all. This is the second defect the audit found actually corrupting real
confirmed references.

**Independent Test**: construct a synthetic fixture whose text places an unrelated date before a
policy-period label, followed by the label and the real period's own two dates. Assert the corrected
helper derives the term from the real period dates only.

**Acceptance Scenarios**:

1. **Given** a source text with an unrelated date appearing before a policy-period label, followed
   by the label and two dates roughly a year apart, **When** the term-derivation helper runs,
   **Then** it derives `"12"`, never a term computed from the unrelated date.
2. **Given** a source text with more than one occurrence of a policy-period label, **When** the
   helper runs, **Then** it considers dates found after every occurrence, not only the first.
3. **Given** the de-glued source text contains an explicit "12-month" or "6-month" phrase,
   **When** both a phrase and two period dates are present, **Then** the phrase's own value is used,
   and the date-derived value never overrides it.
4. **Given** a local-model candidate's own claimed term disagrees with a phrase found in the
   de-glued text, **When** the sanity pass runs, **Then** the phrase's own value - not the model's
   claim, and not a date-derived value - is used, with a value-free note recording the correction.

---

### User Story 3 - The Director sees every stripped figure before he confirms (Priority: P1)

Whatever the sanity pass strips, the confirmation prompt shows the Director an explicit,
easy-to-read count and list of every warning before he is asked to accept, correct, or decline - not
only buried inside the full JSON block the prompt already prints. The confirmed reference's own
cache file also carries that warnings list, so a later reader can see what a given confirmed
reference actually survived.

**Why this priority**: the audit's own three corrupted caches were each confirmed by the Director
with no explicit strip-count in front of him - the warnings existed, but nothing about the prompt
made them hard to miss. This is a straight visibility fix, not a new form of protection, but it sits
at the same priority as the other two defects because it is what lets the Director actually catch a
figure the corrected gate (User Story 1) or the corrected term helper (User Story 2) still could not
save.

**Independent Test**: construct a candidate carrying two warnings and assert the confirmation
prompt's own printed output contains a distinct, labeled warnings section, in addition to the full
JSON block, before the accept-correct-decline question is asked. Confirm a candidate and assert the
resulting cache file's own JSON contains the same warnings list.

**Acceptance Scenarios**:

1. **Given** a candidate carrying one or more warnings, **When** the confirmation prompt runs,
   **Then** it prints a distinct section naming the warning count, followed by each warning on its
   own line, before the accept-correct-decline question.
2. **Given** a candidate carrying zero warnings, **When** the confirmation prompt runs, **Then** no
   warnings section prints at all.
3. **Given** the Director accepts a candidate carrying warnings, **When** the reference is cached,
   **Then** the cache file's own JSON carries the same warnings list.
4. **Given** an older cache file written before this feature existed (no `warnings` key at all),
   **When** it is read back, **Then** it reads as an empty warnings list - never an error.

---

### User Story 4 - The schema captures every field a real declarations page states, ready for future comparison (Priority: P2)

A real declarations page states more than a premium and a set of coverage limits: a policy number, a
policy period as two explicit dates, a policy-level deductible that does not belong to any one
coverage line, the insured asset itself (an address, or a vehicle and its VIN), the named insureds,
any excluded drivers, discounts, fees, and a subtotal. The extended schema captures every one of
these fields, subject to the same figure gate (for a genuine figure) or a date-parse check (for a
date), while every text field (a name, a label, an address, a VIN) stays exempt for the Director's
own review, exactly as spec 006 already treats an insurer's own name.

**Why this priority**: valuable groundwork for a later comparison feature, but nothing in `headless/
compare.py`'s own ranking outcome changes because of it - the new fields are additive and ignored by
the comparison engine except where the alias-table extension (also part of this feature) applies.
This is why it sits at P2 behind the three defect fixes above.

**Independent Test**: construct a synthetic fixture whose source text states a policy-level
deductible, a policy number, an effective and expiration date, and a discount. Assert the extended
candidate captures every one of them, that the figure-shaped ones pass through the corrected gate,
that the two dates compute `term_months` when both parse, and that `headless/compare.py`'s own
comparison output is unaffected by their presence.

**Acceptance Scenarios**:

1. **Given** a source text stating a stand-alone policy-level deductible (for example, a percentage
   wind/hail deductible with its own stated dollar equivalent), **When** extraction runs, **Then**
   the candidate carries it under `policy_level_deductibles`, subject to the corrected figure gate.
2. **Given** a source text stating an effective date and an expiration date that both parse,
   **When** extraction runs, **Then** `term_months` is computed from those two dates using the same
   arithmetic the term-derivation helper already uses.
3. **Given** a source text stating the insured vehicle's own VIN, **When** extraction runs, **Then**
   the VIN is captured under `asset` and is never subject to the figure gate - it is a text field,
   reviewed only at the Director's own confirmation step.
4. **Given** a confirmed reference carrying the new fields, **When** `headless/compare.py`'s own
   comparison engine runs, **Then** every existing comparison and ranking test continues to pass
   unchanged - the new fields are ignored except through the alias-table extension.

### Edge Cases

- A composite, multi-digit-run figure in one coverage-table cell (User Story 1).
- A policy number rendered with internal spaces between digit groups, where the source's own
  tokenization already splits it the same way (User Story 1).
- An unrelated date (a statement date, an issue date) positioned before a policy-period label, ahead
  of the label's own real period dates (User Story 2).
- A glued phrase that hides an "N-month" pattern until the de-glue pass runs, and a glued word pair
  sharing neither a case-transition nor a letter/digit boundary, which the de-glue pass cannot
  recover and which surfaces unresolved at the Director's own confirmation step, the same way spec
  006 already documents an unattached standalone deductible line as a residual for his own review.
- A percentage policy-level deductible carrying its own stated dollar equivalent alongside it (User
  Story 4).
- A converted document long enough that the local model's own context window may silently truncate
  it - surfaced as a value-free warning naming only an estimated count and the configured threshold,
  never the document's own content.
- A cache file written before this feature existed, carrying no `warnings` key at all (User Story
  3).

## Requirements *(mandatory)*

### Functional Requirements

**Sanity-pass token check (amends spec 006 FR-017, FR-018)**

- **FR-001**: The sanity pass MUST tokenize a proposed figure value the same way it already
  tokenizes the source text under spec 006 FR-017: strip only `$` and `,` characters - never
  whitespace and never any other character - then extract every maximal digit-run token, normalized
  by spec 006's own existing trailing-zero-fraction rule.
- **FR-002**: A proposed figure MUST pass the literal-match check only when every digit-run token
  FR-001 extracts from it is a member of the source's own digit-run token set - never when the
  value's own single, un-split cleaned string is checked as one blob. This corrects spec 006
  FR-017's own normalization rule, which today strips whitespace from the proposed value before
  comparing it as a whole, collapsing a composite or spaced value into a single token that can no
  longer match the source's own separately-tokenized digit runs.
- **FR-003**: A proposed figure carrying zero digit-run tokens under FR-001 (a purely non-numeric
  value) remains exempt from the check, unchanged from spec 006's own established rule.
- **FR-004**: The corrected check in FR-002 MUST apply, uniformly, to every figure-shaped field the
  sanity pass gates - the fields spec 006 already gates (premium amount, coverage limit,
  deductible, coverage premium) and every figure-shaped field this feature's own schema extension
  adds (FR-024).
- **FR-005**: Spec 006's own anti-hallucination guarantee - a proposed figure sharing only a digit-run
  suffix or prefix with an unrelated real figure elsewhere in the source is still stripped - MUST
  remain true after FR-001 through FR-004 are applied. This is a hard invariant, never relaxed by
  this feature's own composite-figure fix.

**Term derivation (amends spec 006 FR-020, FR-021)**

- **FR-006**: The term-derivation helper MUST locate every occurrence of a policy/premium-period
  label in the converted text, not only the first occurrence spec 006's own current helper stops at.
- **FR-007**: For each label occurrence FR-006 finds, the helper MUST search only the text that
  follows that occurrence - never the text that precedes it. This corrects spec 006 FR-021's own
  window, which searches both before and after the first occurrence and can therefore pair an
  unrelated date appearing before the label with the real period's own date appearing after it.
- **FR-008**: The helper MUST collect every date that parses under spec 006's own recognized United
  States date formats from every window FR-007 defines, then compute the term as the average-day
  month span (spec 006's own unchanged arithmetic) between the maximum and the minimum date
  collected - never merely the first two dates encountered while reading the text in order.
- **FR-009**: When fewer than two distinct dates are collected under FR-008, the helper returns
  nothing, exactly as spec 006 FR-021 already defines for that case.
- **FR-010**: When the de-glued converted text (FR-013) contains an explicit "N-month" or "N month"
  phrase matching spec 006's own existing pattern, that phrase's own value MUST take precedence over
  the date-derived value from FR-008, for both the local-model generator and the regex-based
  generator. This amends spec 006 FR-020, which today lets a date-derived value unconditionally
  replace the local model's own claim with no regard for whether an explicit phrase already existed
  in the text.
- **FR-011**: Spec 006 FR-019's own exemption of `term_months` from the literal-match check continues
  to apply whenever the value equals either the phrase-derived value (FR-010) or the date-derived
  value (FR-008); a `term_months` value matching neither remains subject to the ordinary
  literal-match check (FR-002). **Amended (Opus verifier BLOCK 2, 2026-08-30)**: a `term_months` value
  matching the schema extension's own verified-dates computation (both `effective_date` and
  `expiration_date` present, parsed, AND passing the figure gate - FR-025, FR-026, contracts/
  fidelity.md section 2's own restated one-table precedence) also joins this exemption list, at the
  highest precedence of the four - a value computed from two verified dates is never itself
  re-examined by the ordinary literal-match check.

**De-glue pass (new)**

- **FR-012**: A converted document's own text MUST pass through a deterministic, regex-only
  transformation, exactly once, at conversion time - before either generator, the term-derivation
  helper, or the sanity pass ever reads it.
- **FR-013**: The transformation in FR-012 MUST insert a single space at every lowercase-to-uppercase
  letter boundary and at every letter-to-digit or digit-to-letter boundary found in the text - never
  at any other boundary, and never through a model call of any kind.
- **FR-014**: The transformation in FR-012 MUST NOT alter any digit's own value, any currency symbol,
  or any punctuation character already present in the text - its only effect is inserting new space
  characters at the boundaries FR-013 names.
- **FR-015**: A glued word pair sharing neither a case-transition boundary nor a letter/digit
  boundary is a known, accepted residual FR-012 does not solve. It surfaces unresolved at the
  Director's own confirmation step, the same recourse spec 006 already documents for its own
  unattached standalone deductible-line residual.
- **FR-016**: The transformation in FR-012 MUST run once regardless of which converter produced the
  text - the layout-aware converter's own output, or the `pypdf` raw-text fallback spec 006 already
  defines - and every downstream reader MUST see only the de-glued text.

**Warnings visibility (new)**

- **FR-017**: The confirmed reference's own cache shape MUST carry the sanity pass's own `warnings`
  list (spec 006's own value-free warning strings) as a new field, `warnings` - a plain list, empty
  by default.
- **FR-018**: The confirmed reference's own read and write functions MUST carry the `warnings` field
  in FR-017 through their existing round trip; a cache file written before this feature existed (no
  `warnings` key present) MUST be read back as an empty list, never an error - the same
  additive-only compatibility rule spec 006's own `generator`/`converter` fields already established.
- **FR-019**: The confirmation prompt MUST print a distinct, explicitly labeled warnings section - a
  count line, followed by each warning on its own line - before the accept-correct-decline question,
  whenever the candidate carries one or more warnings.
- **FR-020**: When a candidate carries zero warnings, the section FR-019 defines MUST NOT print.
- **FR-021**: The warnings section FR-019 defines MUST print in addition to, never instead of, the
  full candidate JSON block the confirmation prompt already prints (which already embeds the same
  `warnings` list) - it exists to give the Director an explicit summary, not to replace the existing
  JSON output.

**Schema extension (new)**

- **FR-022**: The candidate and confirmed-policy shapes MUST each gain a `policy_level_deductibles`
  field - a list of entries, each carrying a `label` and a `value` - for a policy-wide deductible
  that does not belong to any single coverage line.
- **FR-023**: The candidate and confirmed-policy shapes MUST each gain: `policy_number`,
  `effective_date`, `expiration_date`, `asset` (an object carrying either an `address` or a
  `vehicle` description plus its `vin`), `named_insureds` (a list of names), `excluded_drivers` (a
  list of names), `discounts` (a list of entries, each carrying a `label` and a `value` that may be
  empty), `fees` (a list of entries, each carrying a `label` and an `amount`), and `subtotal`.
- **FR-024**: `term_months` MUST remain on both shapes for backward compatibility with every existing
  reader (spec 006's own comparison engine and report). When `effective_date` and `expiration_date`
  both parse under the recognized date formats, `term_months` MUST be computed from them using the
  same average-day month-span arithmetic FR-008 uses - never read as a separately proposed value in
  that case.
- **FR-025**: Every figure-shaped field FR-022/FR-023 add - a `policy_level_deductibles` entry's own
  `value`, a `discounts` entry's own `value` when non-empty, a `fees` entry's own `amount`,
  `subtotal`, and `policy_number` - is subject to the corrected sanity-pass check (FR-002 through
  FR-004), exactly like every figure spec 006 already gates.
- **FR-026**: `effective_date` and `expiration_date` are subject to a date-parse check instead of the
  literal-match check: each MUST parse under the same recognized United States date formats the
  term-derivation helper already uses. A value that fails to parse is cleared to an empty string and
  replaced by a value-free warning, in the same shape spec 006's own figure-stripping warnings
  already use.
- **FR-027**: `asset`, `named_insureds`, `excluded_drivers`, and every `label` field inside
  `policy_level_deductibles`, `discounts`, and `fees` are text fields, exempt from the sanity pass,
  exactly as spec 006 FR-028 already exempts an insurer's own name and a coverage line's own name.
- **FR-028**: `headless/compare.py`'s own comparison and ranking functions MUST ignore every field
  FR-022/FR-023 add, with no change to the outcome of any existing comparison test - the schema
  extension is additive-only for the comparison engine, except where the alias-table extension
  (FR-029) applies.
- **FR-029**: The local-model extraction prompt MUST be extended to ask for the fields FR-022/FR-023
  add, using the same "copied verbatim, never invented" instruction spec 006's own prompt already
  states for every existing figure.

**Alias-table extension (new)**

- **FR-030**: `headless/compare.py`'s coverage-line alias table MUST gain the additional real-world
  coverage-line names this feature's own research identifies, each mapped to either an existing
  normalized key or one of the new normalized keys this feature adds for homeowners coverage lines
  the table currently has none of.
- **FR-031**: The alias-table extension in FR-030 introduces no fuzzy matching, no learned weighting,
  and no new comparison behavior beyond matching a differently-worded real coverage line to the
  correct existing key - a hand-authored table extension only, the same kind of change spec 006's
  own research already describes as safe to make "by hand only."

**Context guard (new)**

- **FR-032**: The local-model request's own `options` object MUST gain an explicit context-window
  value, and the converted document's own de-glued text MUST be checked against an estimated token
  count derived from that value; when the estimate exceeds the configured threshold, one value-free
  warning MUST be added, naming only the estimated count and the threshold - never the document's
  own content.

### Non-Functional Requirements

- **NFR-001**: The default `pytest -q` run MUST exercise every path this feature adds using
  injectable fakes and synthetic fixtures only - zero real network calls, zero real local-model
  invocations, and zero real PDF file dependencies, matching spec 006's own NFR-001.
- **NFR-002**: Every fixture, example, and narrative description in this feature's own document set
  and test suite MUST contain no real policy figure, premium, limit, policy number, person name,
  address, VIN, or filesystem path to a real PDF - wholly synthetic content only. This repository is
  public; this rule is stricter than spec 006's own NFR-003 in scope (documents as well as fixtures),
  not merely a restatement of it.
- **NFR-003**: The new and changed test modules together MUST run in comparable time to spec 006's
  own equivalent additions (well under one second combined), since none of them touch a real
  network, process, or filesystem PDF.
- **NFR-004**: The read-only verification step against the Director's own three real declarations
  PDFs (Success Criteria, below) MUST NOT write any file, branch, commit, or cache entry under
  `~/.headless/` or this repository's own tracked tree, and MUST NOT be performed by this delivery's
  own automated test suite - it is a separate, orchestrator-run step, and its outcome is reported in
  conversation only, never persisted with a real value into a spec, a fixture, or a changelog row.

### Key Entities

- **TokenizedFigure**: the corrected per-figure check (FR-001, FR-002) - a proposed value's own
  digit-run tokens, each checked for membership in the source's own digit-run token set,
  independently of any other character (a space, a label word, a slash) surrounding them.
- **TermDerivation (extended)**: spec 006's own result type, now produced by a helper that scans
  every label occurrence, windows only after each one, and prefers an explicit de-glued phrase over
  its own date arithmetic (FR-006 through FR-011).
- **De-glued ConvertedDocument**: spec 006's own `ConvertedDocument`, whose `text` now always carries
  the boundary-inserted, de-glued form (FR-012 through FR-016) before any other function reads it.
- **PolicyLevelDeductible**: `{label, value}` - a policy-wide deductible not tied to one coverage
  line (FR-022).
- **Asset**: `{address}` or `{vehicle, vin}` - the insured asset itself, always a text field (FR-023,
  FR-027).
- **Discount / Fee**: `{label, value}` / `{label, amount}` - the label is always text; the value or
  amount, when present, is a figure subject to the corrected gate (FR-023, FR-025).
- **WarningsSection**: the confirmation prompt's own new, distinct summary of a candidate's own
  warnings list, printed before the accept-correct-decline question (FR-019 through FR-021).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every probe-proposed verbatim composite figure a unit test constructs (a
  split-limit-with-labels shape, a spaced-digit-group identifier) passes the corrected sanity pass
  unchanged.
- **SC-002**: A hallucinated figure absent from the source - including one sharing only a digit-run
  suffix or prefix with a real, unrelated figure elsewhere in the source - is still stripped by the
  corrected gate, proven by a unit test.
- **SC-003**: A synthetic fixture reproducing a statement date positioned before a policy-period
  label, followed by the label and the real period's own two dates, derives the term from the real
  period dates only.
- **SC-004**: A synthetic fixture reproducing a glued "N-month"-shaped phrase is de-glued before
  either generator or the sanity pass reads it, and the phrase becomes detectable by spec 006's own
  existing term pattern once de-glued.
- **SC-005**: On the orchestrator's own read-only verification run against the Director's three real
  declarations PDFs (never reproduced in this repository), extraction derives terms of twelve, six,
  and twelve months respectively, and zero verbatim source figures are stripped as hallucinated on
  any of the three documents. This is an orchestrator-observed outcome (NFR-004), not something this
  repository's own automated suite can assert against a file it never reads.
- **SC-006**: A confirmed reference's own cache file carries its own sanity-pass warnings list;
  reading a cache file written before this feature existed still succeeds, with an empty warnings
  list.
- **SC-007**: The confirmation prompt prints a distinct warnings summary, separate from the JSON
  block, whenever the candidate carries at least one warning, and prints no such section when it
  carries zero.
- **SC-008**: A synthetic fixture stating a policy-level deductible, a policy number, an effective
  and expiration date, and a discount yields a candidate carrying every one of them, with the
  figure-shaped fields passing through the corrected gate and `term_months` computed from the two
  dates when both parse.
- **SC-009**: Every existing `headless/compare.py` comparison and ranking unit test continues to pass
  unchanged after the schema extension and the alias-table extension both land.
- **SC-010**: The full `pytest -q` suite, including this feature's own new tests, completes with zero
  real network calls, zero real local-model invocations, and zero real PDF file reads - the same
  zero-external-dependency property spec 006's own suite already holds.
- **SC-011**: Every fixture, example, and narrative description in this feature's own document set
  contains no real policy figure, premium, limit, policy number, person name, address, VIN, or real
  PDF filesystem path.

## Assumptions

- The three real declarations PDFs the orchestrator's own verification step (SC-005) reads remain
  available at whatever path the orchestrator supplies at run time; this feature's own document set
  never records that path, and no file this feature adds reads it either.
- Ollama, the configured local model, and the layout-aware converter remain configured exactly as
  spec 006 already established; this feature changes neither the model choice, the converter choice,
  nor the localhost-only enforcement spec 006's own `ConfigError` already provides.
- The Director's own mandatory confirmation step, unchanged by this feature, remains the final safety
  net. The corrected gate, the corrected term helper, the visible warnings, and the extended schema
  each reduce, but do not eliminate, the chance an incorrect value reaches that prompt.
- A future feature may use the schema fields this delivery adds (FR-022, FR-023) to extend
  `headless/compare.py`'s own ranking logic; this delivery deliberately does not attempt that
  extension itself (FR-028).

## Out of Scope

- Merging this feature's branch to `main`, pushing it, or running `scripts/policy_extract.py`
  against the Director's own real `profile` vault item or any real browser.
- OCR for an image-only PDF with no text layer, and support for a new insurer.
- Any change to `headless/compare.py`'s own ranking logic beyond the alias-table extension (FR-030,
  FR-031) - the schema extension (FR-022, FR-023) is additive-only for the comparison engine.
- The Director-attended re-extraction of his own three real assets using this feature's own
  corrected pipeline - a separate session, after this specification and its implementation are both
  reviewed.
- Any change to `headless/report.py`'s own rendering beyond what an implementation of this
  specification finds strictly necessary to keep the provenance footer's own existing fields
  consistent with the extended `PolicyReference` shape.
