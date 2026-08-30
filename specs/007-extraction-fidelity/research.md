# Research: Extraction Fidelity

**Feature**: 007-extraction-fidelity | **Date**: 2026-08-29

This document records the evidence an independent audit gathered on 2026-08-29, against three of
the Director's own real declarations PDFs, before this feature was scoped, and the nine design
decisions (D1-D9) that follow from it. Every value below is a structural, reconstructed shape
standing in for what the audit actually observed - no real figure, name, policy number, premium, or
filesystem path appears anywhere in this document, matching this feature's own NFR-002 and this
repository's standing public-repository hygiene rule.

All nine decisions were fixed by the Director before `spec.md` was drafted and are not reopened
here; where an implementation detail was left to this spec's own discretion, that choice is recorded
as a sub-decision under the D-number it serves, not as a new top-level decision.

## Evidence

### Defect A: the sanity pass strips a verbatim composite figure

Reading `headless/policydoc.py`'s own current `_figure_present` (spec 006): it strips `$`, commas,
and whitespace from a proposed value, then requires the entire cleaned string to equal exactly one
token in the source's own digit-run token set. A real declarations page states many figures as more
than one digit run inside a single cell - a split personal-liability limit written on one line as two
dollar amounts and their own labels, or a per-row deductible carrying a row label alongside its own
figure. Each of these contains every one of its own digit runs verbatim in the source text, but
because whitespace is stripped and label words are never removed, the cleaned proposed string never
equals a single pure-digit source token, so the check fails and the whole figure is stripped as if it
had been invented.

The same mechanism strips a numeric identifier rendered with internal spaces between digit groups
(a spaced-out policy-number shape): the source's own tokenizer naturally splits it into separate
digit-run tokens at each whitespace boundary, but the current check strips whitespace from the
proposed value first, merging what should be several tokens into one that can never match any single
source token.

Probed live against one of the three real documents: feeding that document's own coverage-table text
back to itself as a candidate still stripped its own liability limits, because the table states them
as a composite string. Across the three confirmed caches the audit built this way, eight
decision-critical figures were destroyed - one auto policy's own reference ended up with no liability
limits recorded at all.

### Defect B: the term-derivation helper mis-pairs a date before the label

Reading `headless/policydoc.py`'s own current `_find_period_dates` (spec 006): it finds the *first*
occurrence of a policy-period label, opens a window 150 characters before and 150 characters after
that occurrence, and takes the *first two* dates its own date pattern finds inside that window, in
whatever order they appear in the text. A real declarations page frequently states an unrelated date
- a statement date, an issue date - within 150 characters of the label, ahead of the label's own two
real period dates. When that happens, the first "date" the current helper finds is the unrelated one,
not the real period's own start date.

Probed against the three real documents: on two of the three, this paired the unrelated date with
the real period's own start date and derived terms far short of any real policy term (reconstructed
as roughly three months and roughly zero months respectively - neither a real policy term).
Spec 006 FR-020 then let that wrong derived value override the local model's own correct claim,
because FR-020 does not ask whether the derivation itself was trustworthy, only whether it produced
a value at all. The third document escaped this defect only because it happened to have no unrelated
date positioned near its own label - not because the helper behaved correctly.

### Defect C: no schema slot for a policy-level deductible

A real declarations page can state a deductible that belongs to the policy as a whole, not to any one
coverage line - a stand-alone "All Perils" deductible, or a percentage wind/hail deductible carrying
its own stated dollar equivalent. Spec 006's own `ExtractionCandidate`/`CurrentPolicy` shapes have no
field for this: a coverage line's own `deductible` field only ever applies to that one line. A
policy-level deductible has nowhere to land in the current schema and is lost entirely, not merely
misfiled.

### Defect D: converter glue defeats phrase detection and corrupts values

The layout-aware converter (`pymupdf4llm`, spec 006) glues adjacent bold table cells together at
their own visual boundary when it converts a page to Markdown - reconstructed shapes such as a term
label glued directly to its own digit and unit ("Total6month"), or a two-word cell glued into one
run. This gluing has two effects: it can corrupt a value once it survives extraction into a cached
reference, and it defeats spec 006's own "N-month"/"6-month" phrase pattern, which requires the
digit and the word "month" to be separated by, at most, an optional space or hyphen - a glued phrase
never matches, forcing every annual or semiannual policy whose page glues this way into the
date-derivation path (Defect B) instead of the more direct phrase match.

### Defect E: stripped-figure warnings never reach the cache or a distinct confirm-prompt display

Reading `headless/policydoc.py`'s own `PolicyReference.to_dict()` (spec 006): it serializes the
policy fields, `source_path`, `confirmed_at`, `generator`, and `converter` - never `warnings`. Once a
candidate is confirmed into a `CurrentPolicy` and then a `PolicyReference`, its own sanity-pass
warnings are discarded; nothing about a confirmed cache file records what was stripped from it before
it was cached.

The warnings are not entirely invisible before that point: `confirm_candidate`'s own existing
JSON dump (spec 006) already embeds the same `warnings` list inside the full candidate block it
prints. But nothing about the prompt calls the Director's own attention to that list specifically -
it is one field among several inside a JSON body he is asked to review as a whole, with no summary
line, no count, and no separate presentation of its own. The audit confirmed all three of its own
corrupted caches (Defects A and B, above) with no explicit strip-count in front of the Director at
the moment he made that decision.

### Defect F: the coverage-line alias table has zero homeowners entries

Reading `headless/compare.py`'s own `_ALIASES` table (spec 005): it carries six normalized keys, all
of them auto-insurance concepts (`bodily_injury`, `property_damage`, `collision`, `comprehensive`,
`uninsured_motorist`, `medical_payments`). Spec 006's own real-world example that first scoped that
feature was a *homeowners* declarations page. A homeowners policy's own coverage lines - a dwelling
line, an other-structures line, a personal-property line, a loss-of-use line, a personal-liability
line, and a medical-payments-to-others line - have no alias-table entry at all today. `normalize_line`
already degrades gracefully for an unrecognized name (it normalizes to its own stable, lower-cased
key rather than raising), so two sources that happen to use identical wording for the same line still
compare correctly by coincidence; the real gap is that two real-world phrasings for the same
homeowners coverage (for example, a current policy's own "Personal Liability" line against a
competing quote's own "Liability to Others" phrasing for the identical coverage) normalize to two
different keys and never compare against each other at all, appearing as two unrelated lines instead
of one.

One entry the audit checked required no fix: `_ALIASES["medical_payments"]` already includes
"personal injury protection" and "pip" (spec 005's own original table), so an auto policy's own PIP
line already matches correctly today - confirmed by reading the table directly, not merely assumed.

### The P2 gap: no context-window guard

`headless/localllm.py`'s own request payload (spec 006) sets `"temperature": 0` but no explicit
`num_ctx` value, and nothing in the pipeline estimates the converted document's own length against
whatever context window the local model actually uses. A long enough converted document (a
multi-page declarations page after layout-aware conversion, or a document carrying an unusually
verbose coverage schedule) could silently truncate inside the model's own default context window,
which would present to the sanity pass as a plausible-looking, schema-valid, but incomplete
candidate - indistinguishable, from inside this pipeline, from a shorter document that was read in
full.

## D1. The corrected figure gate: per-token membership on both sides

**Decision**: tokenize the *proposed* value exactly the way the source text is already tokenized -
strip only `$` and `,` characters (never whitespace, never any other character), then extract every
maximal digit-run token from what remains, normalized by the existing trailing-zero-fraction rule.
Require *every* digit-run token extracted this way to be a member of the source's own digit-run
token set - never require the value's own single, un-split cleaned string to match one source token.

**Rationale**: the current check's defect is not the concept of a literal-match gate - the
anti-hallucination guarantee it enforces is exactly right - it is that the check applies the same
per-token tokenization to the source text but a different, whole-blob tokenization to the proposed
value. Making both sides go through the identical tokenization closes the composite-figure and
spaced-identifier gaps (Defect A) without weakening the per-token exactness of the check at all: a
hallucinated figure sharing only a digit-run suffix or prefix with a real, unrelated source figure
still fails, because that figure's own digit run is still checked for exact set membership, never
substring containment (spec 006's own FIX-FIRST-2 guarantee, unchanged and restated as FR-005). A
value with no digit run (a purely textual value like an insurer's own name, already exempt) is
unaffected, since it never reaches the per-token check to begin with.

**IMPORTANT 3 (Opus verifier, 2026-08-30) - a narrower, more honest claim than "without weakening the
check at all"**: the per-token rule closes Defect A (a composite or spaced figure built ENTIRELY from
the source's own tokens), but it deliberately does not, and cannot, detect RECOMBINATION - a proposed
figure built by joining two tokens that are each independently present in the source, but never
actually adjacent or associated with each other there (for example, a proposed `"<A>/<B>"` where the
source states `<A>` on one coverage line and `<B>` on a wholly unrelated one). Per-token membership
is, by design, insensitive to which tokens co-occur or in what combination - that is a strictly
harder problem (associating a token with its own surrounding context) this feature does not attempt
to solve. This is a known, accepted gap, not a silent weakening: the Director's own mandatory
confirmation step is the backstop the spec's own Assumptions section already names for exactly this
class of residual risk, the same way it is for every other gap this document records.

**Alternatives considered**: stripping label words (letters) from the proposed value before
comparing, rather than tokenizing by digit run (rejected - this would require a list of which words
are "labels," an open-ended and language-specific problem the digit-run approach avoids entirely by
simply ignoring every non-digit character rather than trying to recognize and remove it);
substring containment of the proposed value's own digits against a single concatenated source digit
blob (rejected in spec 006 already, for the same suffix/prefix-collision reason spec 006's own
FIX-FIRST-2 finding proved, and this feature's own FR-005 keeps that finding a hard invariant).

## D2. The corrected term-derivation window: scan every label, window after-only, max-minus-min

**Decision**: locate every occurrence of a policy/premium-period label in the converted text, not
only the first. For each occurrence, search a window of the text that begins immediately after that
occurrence and extends roughly 400 characters forward - never any text before the occurrence.
Collect every date that parses under the already-recognized United States date formats across every
such window, then compute the term as the average-day month span (the existing, unchanged
arithmetic) between the maximum and the minimum date collected, rather than between the first two
dates encountered in reading order. When the de-glued text (D4) contains an explicit "N-month"/"N
month" phrase, that phrase's own value takes precedence over this date-derived value, for both
generators - closing the override direction spec 006 FR-020 left open.

**Rationale**: an after-only window removes the entire class of error Defect B documents - an
unrelated date positioned before the label can no longer enter the window at all, since the window no
longer looks backward from the label. Scanning every occurrence, rather than stopping at the first,
protects against a declarations page that repeats the label (for example, once in a summary section
and again in a detailed schedule) where only one of the two occurrences sits near the real period
dates. Collecting every date and taking the max-minus-min span, rather than the first two encountered,
protects against a windowed span that happens to contain more than two dates (for example, a renewal
notice date alongside the real period's own two dates) - the real period's own start and end are, by
construction, the earliest and latest dates a policy-period context actually discusses, so max-minus-
min is the more general rule, not merely a fix for the one failure mode the audit happened to observe.
Preferring an explicit phrase over date arithmetic whenever one exists (rather than letting date
arithmetic override an explicit phrase, or letting the two run independently with no stated priority)
matches the plainer, more direct source of truth: a document that states its own term in words has
already answered the question date arithmetic exists to answer indirectly.

**Alternatives considered**: widening the existing before-and-after window instead of restricting it
to after-only (rejected - widening does not remove the class of error, it only changes how far away an
unrelated date has to be before it stops causing the same mistake); taking the two dates closest to
the label by character distance rather than every date in an after-only window (rejected as more
complex for no proven benefit - the after-only window already removes every before-the-label
candidate, and "closest by distance" would still need a tie-breaking rule the max-minus-min approach
does not need); always trusting the local model's own claimed term over any derived value
(rejected - this is the exact opposite of spec 006 FR-020's own reasoning, and the local model has no
way to verify its own claim against the document the way a deterministic date scan can).

**MINOR 7 (Opus verifier, 2026-08-30) - accepted residual, phrase false positive**: preferring an
explicit phrase unconditionally over date arithmetic (this D2's own decision, above) has its own
narrow failure mode this feature accepts rather than solves: a declarations page stating something
like "12 month rate guarantee" (a phrase about a RATE guarantee, not the policy's own term) would
still match `_TERM_RE` and outrank a correct date-derived term. This is accepted, not fixed, for the
same reason D2's own decision favors a stated phrase over indirect arithmetic in the first place - the
Director's own confirmation step is visible and immediate, and a wrong "12" sitting beside two dates
that plainly span a different number of months is one of the easier, more legible mistakes for a human
reviewer to catch at that step, unlike a silently wrong number with no textual anchor to compare it
against.

**IMPORTANT 4 (Opus verifier, 2026-08-30) - amendment, the multi-period residual**: scanning every
label occurrence and taking the max-minus-min span (this D2's own decision) initially introduced a
NEW class of error this decision's own original evidence never covered: a real declarations page can
carry more than one period section in the same document - a "Prior Policy Period" or "Previous
Period" alongside the current one - and max-minus-min across every window would then span a prior
period's own start date to the current period's own end date, deriving a false combined term with no
warning at all (a regression against spec 006's own regex-path behavior, which only ever inspected the
first occurrence and so never encountered this shape). Fixed by excluding a label occurrence
immediately preceded by "prior"/"previous"/"former"/"expiring" from contributing its own window, with
that occurrence's own dates additionally excluded from every OTHER occurrence's window too (an
excluded occurrence positioned textually BEFORE a surviving one would otherwise sweep its own
overly-broad forward window across the surviving occurrence's real dates and mark them "excluded" by
association - both reading orders are covered by capping every occurrence's own window at the START of
the next label occurrence, never past it). A residual this fix does not attempt to solve: a document
using a wholly different word for its own prior-period label (neither "prior," "previous," "former,"
nor "expiring") would not be excluded - the value-free warning this fix also adds (more than two
distinct dates survived) at least surfaces that a multi-date situation existed, for the Director's own
review, even on a document phrasing this exclusion list does not yet recognize.

**BLOCK 2 (Opus verifier, 2026-08-30) - amendment, verified explicit dates added as the new top tier**:
this D2's own two-tier precedence (phrase, then date-window arithmetic) is superseded by a four-tier
precedence once the schema extension's own `effective_date`/`expiration_date` fields exist (D5, FR-023):
VERIFIED explicit dates (both fields present in the source AND both parse) now outrank an explicit
phrase, which still outranks date-window arithmetic, which still outranks whatever the generator
itself separately proposed. The original two-tier order (phrase over date-window arithmetic) is
otherwise unchanged and is now the SECOND and THIRD tiers of the same table - see
contracts/fidelity.md section 2 for the restated, single canonical table.

## D3. The de-glue pass: boundary-insertion regex, run once at conversion time

**Decision**: insert a single space at every lowercase-to-uppercase letter boundary and at every
letter-to-digit or digit-to-letter boundary found in a converted document's own text, exactly once,
immediately after conversion and before any generator, the term-derivation helper, or the sanity pass
ever reads that text. No other boundary is touched, no digit's own value changes, and no model call
of any kind is involved.

**Rationale**: this is a narrow, deterministic fix targeted at the two boundary shapes the audit
actually observed causing harm - a label glued directly to its own digit and unit, and a two-word
phrase glued at a case transition. Running it exactly once, at conversion time, on the one place
every downstream consumer already reads from (`ConvertedDocument.text`), means every existing and
new caller benefits automatically with no change to any call site beyond the conversion step itself.

A glued word pair sharing neither a case-transition boundary nor a letter/digit boundary (two
lowercase words glued directly together with no capital letter and no digit anywhere at the seam) is
a real, accepted residual this pass does not solve - there is no boundary signal left in the text for
a pure regex to detect. This is recorded here explicitly, following the same "known, accepted
residual, surfaced at the Director's own review" discipline spec 006 already established for its own
comparable gaps (an unattached standalone deductible line; a date glued to preceding, unrelated
digits with no separator at all), rather than silently claiming a complete fix this feature cannot
actually deliver.

**Alternatives considered**: a dictionary-based word-boundary detector (rejected - it would need a
maintained word list, is language-specific, and is a materially larger piece of machinery for a
narrower class of gluing than the two boundary rules already cover); asking the local model to
de-glue the text as part of its own extraction prompt (rejected - this reintroduces exactly the kind
of unverifiable, model-dependent step the sanity pass exists to gate around, for a transformation
that a handful of regex substitutions already solve deterministically and for free); switching PDF
converters (rejected - spec 006's own D2 already evaluated and rejected the alternative converters
available, and this feature's own audit evidence is a narrower gluing behavior within the chosen
converter's own output, not a reason to revisit that earlier, broader evaluation).

**BLOCK 1 (Opus verifier, 2026-08-30) - amendment, the letter<->digit rule corrected from blanket to
precise**: measured directly against the Director's own three real declarations PDFs, this D3's own
original blanket letter<->digit insertion also fired INSIDE real identifiers - a 17-character
VIN-shaped run and a mixed alphanumeric policy/unit-number run both lost their own internal
digit-letter boundaries across the three documents (VIN-shaped run survival measured 2 -> 0; mixed
identifier survival measured 18 -> 0). An identifier is a text field (FR-027), so nothing downstream
would ever have stripped the corrupted result - it would have been cached and shown to the Director
exactly as corrupted. The corrected rule (contracts/fidelity.md section 3) makes rules 2/3
conditional on the shape of the surrounding maximal alphanumeric run: a boundary gains a space only
when the run's own total letter<->digit transition count is <= 2, the digit-side segment at that
boundary is <= 3 characters, and the letter-side segment there is >= 3 characters - a real identifier
mixes letters and digits far more densely, or carries a much longer digit run, than a glued
label-plus-figure ever does, so this precise rule still de-glues "Total6month"-shaped text while
leaving a VIN, a policy number, and a spaced unit number byte-identical. Rule 1
(lowercase-to-uppercase) is unaffected by this correction - it remains the simple, unconditional
boundary insertion D3's own original decision already established, since a case transition carries no
comparable identifier-corruption risk (a VIN, a policy number, and a unit number are conventionally
all-uppercase or all-digits, never mixed-case).

**BLOCK 1 - new, accepted residual (camel-case surnames)**: rule 1 (unchanged by this correction) has
its own pre-existing, now explicitly documented side effect: a camel-case surname glued into
`named_insureds` by the same converter artifact ("McDonald"-shaped) renders spaced ("Mc Donald"-shaped)
after de-gluing. Rule 1 cannot distinguish a glued word boundary from a genuine internal case
transition inside one real word without a maintained surname exception list - the same
"language-specific, open-ended, materially larger machinery" objection this D3's own "Alternatives
considered" section already raises against a dictionary-based detector for the gluing problem in
general applies equally here. `named_insureds` is a text field, read at the Director's own
confirmation step (FR-027) - a spaced rendering of his own named insured's surname is a visible,
low-stakes cosmetic residual, not a value ever gated, computed from, or compared against.

## D4. Warnings persist to the cache; the confirm prompt gets a distinct summary

**Decision**: the confirmed reference's own cache shape gains a `warnings` field (a plain list,
empty by default), carried through the existing read/write round trip with the same additive-only
compatibility rule spec 006's own `generator`/`converter` fields already established. The
confirmation prompt gains a distinct, explicitly labeled section - a count line, followed by each
warning on its own line - printed before the accept-correct-decline question, whenever the candidate
carries at least one warning; the section does not print at all when there are none. This section
prints in addition to, never instead of, the existing full JSON block.

**Rationale**: the warnings already exist and are already computed; the defect is entirely one of
visibility and persistence, not of missing information. Persisting `warnings` into the cache means a
later reader - the Director inspecting a cache file directly, or a future report - can see what a
given confirmed reference actually survived, the same reasoning spec 006's own `generator`/
`converter` provenance fields were added for. Giving the confirm prompt its own distinct summary,
rather than relying on the Director to notice the same list embedded inside a JSON body he is
reviewing for entirely different reasons, is a direct response to the audit's own finding: all three
of its corrupted caches were confirmed with the warnings technically present but not called out.

**Alternatives considered**: refusing to let the Director accept a candidate that carries any
warning at all (rejected - this would turn every ordinary, already-explained gap, such as spec 006's
own "no term detected" note on a document with a genuinely missing figure, into a hard block, which
contradicts the entire "confirmation is the final safety net, never removed" principle this feature's
own spec explicitly preserves); a separate confirmation question specifically for the warnings
(rejected as unnecessary complexity - a clearly labeled summary ahead of the existing single
accept-correct-decline question already gives the Director everything he needs to decide).

## D5. Schema extension: the fields a real declarations page actually states

**Decision**: extend `ExtractionCandidate` and `CurrentPolicy` with `policy_level_deductibles`,
`policy_number`, `effective_date`, `expiration_date`, `asset`, `named_insureds`,
`excluded_drivers`, `discounts`, `fees`, and `subtotal`. `term_months` stays on both shapes for
backward compatibility, computed from `effective_date`/`expiration_date` (via the same average-day
arithmetic D2 already uses) whenever both parse. A figure-shaped new field (a deductible's own
`value`, a discount's own `value`, a fee's own `amount`, `subtotal`, `policy_number`) is subject to
the corrected gate (D1); the two dates are subject to a date-parse check instead; every text field
(`asset`, `named_insureds`, `excluded_drivers`, and every `label`) is exempt, the same way an
insurer's own name already is. The comparison engine ignores every new field except through the
alias-table extension (D6) - no ranking-logic change in this delivery.

**Rationale**: Defect C is a genuine schema gap, not a bug in existing logic - there is simply no
field for a policy-level deductible to land in today. Extending the schema to also capture the other
fields a real declarations page routinely states (a policy number, the policy's own two explicit
dates, the insured asset itself, named insureds, excluded drivers, discounts, fees, a subtotal) is
groundwork for a future comparison feature and costs nothing to the comparison engine today, since
every one of these fields is additive and explicitly ignored except where the alias table already
needs to recognize a coverage-line name. Computing `term_months` from the two explicit dates, rather
than trusting either generator's own separately proposed term claim, removes an entire class of
disagreement this feature would otherwise have to arbitrate between three sources (the model's claim,
the date-derivation helper, and now two structured date fields) instead of one.

**Alternatives considered**: leaving `term_months` as a separately proposed value alongside the new
`effective_date`/`expiration_date` fields, with no computed relationship between them (rejected -
this reintroduces exactly the "which source wins" ambiguity spec 006 FR-020 and this feature's own
D2 already exist to resolve for the single-term-value case, now with a third source added for no
reason); a wholly new type for the extended shape rather than extending `ExtractionCandidate`/
`CurrentPolicy` in place (rejected - spec 006's own D1 already chose to reuse `ExtractionCandidate`
for a model-generated candidate specifically so no downstream consumer needs to change when a
candidate's own origin changes; introducing a second type now for an additive field set would break
that same reasoning for no benefit).

## D6. Alias-table extension: the real-world names this feature's own research identifies

**Decision**: extend `headless/compare.py`'s `_ALIASES` table with the real-world coverage-line names
Defect F identifies - mapping "Standard Collision"-shaped phrasing into the existing `collision` key,
mapping a "Liability to Others"-shaped phrasing into a new `personal_liability` key alongside a
"Personal Liability" canonical phrasing, and adding five new homeowners-specific keys (`dwelling`,
`other_structures`, `personal_property`, `loss_of_use`, `personal_liability`,
`medical_payments_to_others`) the table currently has none of. "Personal Injury Protection (PIP)"
needs no table change - `medical_payments`'s own existing alias tuple already recognizes it, verified
by reading the table directly rather than assumed.

**Rationale**: this is a hand-authored table extension, the same shape and the same safety property
every prior addition to this table already has (spec 005's own original six entries) - a fixed set of
known phrasings for a fixed set of coverage concepts, never a fuzzy-matching or inference mechanism.
Adding the homeowners-specific keys directly answers Defect F's own gap: a real homeowners policy's
coverage lines currently have nowhere to normalize to except their own literal wording, which only
works when two sources happen to use identical phrasing.

**Alternatives considered**: a fuzzy or similarity-based matcher instead of a fixed alias table
(rejected - `headless/compare.py`'s own module docstring already states "no fuzzy matching,
no learned weighting" as a standing rule, spec 005's own D5, and this feature has no reason to
reopen it); leaving PIP's own alias untouched but adding a redundant near-duplicate entry anyway "to
be safe" (rejected - a table is easier to reason about and maintain when every entry serves a real,
verified gap, not a duplicate of one already covered).

## D7. Context-window guard: an explicit `num_ctx` plus a length-estimate warning

**Decision**: add an explicit `num_ctx` value to the local-model request's own `options` object, and
check the converted document's own de-glued text against an estimated token count derived from that
value before the request is sent; when the estimate exceeds the configured threshold, add one
value-free warning naming only the estimated count and the threshold, never the document's own
content.

**Rationale**: an unset `num_ctx` leaves the actual context window to whatever the local model's own
default happens to be, which this pipeline has no visibility into and no way to detect a silent
truncation against. An explicit value, paired with a cheap length estimate against that same value,
turns an otherwise invisible failure mode (a plausible-looking but silently incomplete response) into
a value-free, actionable warning the Director can see at the same confirmation prompt D4 already
improves.

**Alternatives considered**: relying on the model's own response to signal truncation (rejected - a
model that runs out of context space to read from does not necessarily signal anything unusual in
its own output; it may simply propose a candidate built from only the part of the document its
context window actually held); refusing to call the local model at all above a fixed document-length
ceiling (rejected as unnecessarily strict - a warning that lets the Director decide, exactly parallel
to every other warning this pipeline already produces, is more consistent with this feature's own
D4 philosophy than a hard refusal for a failure mode that is only ever a risk, never a certainty).

## D8. Verification: synthetic fixtures plus a separate, orchestrator-run live probe

**Decision**: every unit test this feature adds uses a synthetic fixture that reproduces one
defect's own structural shape (a glued phrase, a statement date before a period label, a composite
verbatim figure, a spaced identifier) - never a real value, name, policy number, or premium. A
separate, read-only verification step against the Director's own three real declarations PDFs (paths
supplied by the orchestrator at run time, never written into any file this feature adds) is an
implementation-phase task, expecting derived terms of twelve, six, and twelve months respectively and
zero stripped-verbatim warnings across all three. The Director-attended re-extraction of the three
real assets into confirmed, cached references is explicitly out of this delivery's own scope -
a separate session, after this specification and its implementation are both reviewed.

**Rationale**: this mirrors spec 006's own D9 testing discipline exactly - a synthetic-only default
suite, plus a clearly separated, opt-in-style verification step for the one property no synthetic
fixture alone can prove (that the corrected pipeline actually behaves correctly against the real
documents that scoped it). Keeping that step out of the automated suite and out of every file this
feature writes is what lets this delivery stay spec-authoring-only, per its own brief, while still
recording exactly what a later implementation-phase session needs to verify and how.

## D9. Out of scope

**Decision**: this feature does not merge to `main`, does not push, and does not run
`scripts/policy_extract.py` against the Director's own real `profile` vault item or any real
browser. It does not add OCR, does not add a new insurer, and does not change
`headless/compare.py`'s own ranking logic beyond the alias-table extension (D6). The
Director-attended re-extraction of his own three real assets is a separate, later session.

**Rationale**: each of these is a deliberate boundary already implicit in the Director's own framing
of this feature as a fix-and-extend delivery scoped from a specific audit, not an invitation to
redesign the comparison engine, add new insurer support, or perform the real-document re-extraction
this feature's own corrected pipeline exists to make safe. Naming them here gives a later reviewer one
place to check that a follow-up idea belongs in its own future feature.

## Alternatives considered (feature-level, not already covered under a specific D-number)

- **Rewriting the sanity pass from scratch around a different design entirely** (rejected): spec
  006's own gate design - normalize both sides, compare digit-run tokens, exempt a non-numeric value
  - is correct in concept; the audit's own findings are about an inconsistency in how that design is
  applied to the two sides being compared, not a flaw in the design itself. A narrow, targeted
  correction (D1) is more auditable and lower-risk than a full rewrite of a mechanism that is
  otherwise proven (spec 006's own FIX-FIRST-2 finding, the suffix/prefix-collision guarantee, both
  remain load-bearing and untouched).
- **Deferring the schema extension (D5) to its own, later feature** (considered, not adopted): the
  Director's own approved plan bundles the schema extension into this same delivery because the
  corrected gate (D1) is a prerequisite for any of the new figure-shaped fields to be trustworthy the
  moment they exist - shipping the schema extension separately, before the gate fix, would recreate
  Defect A's own failure mode against a wider field set on day one.
