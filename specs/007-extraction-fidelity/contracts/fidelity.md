# Contracts: Extraction Fidelity

**Feature**: 007-extraction-fidelity | **Date**: 2026-08-29 (Opus verifier corrections applied 2026-08-30)

Seven stable interfaces: the **corrected sanity-pass gate**, the **corrected term-derivation rules**,
the **de-glue transformation**, the **extended schema fields** (with their gate treatment), the
**cache compatibility rule**, the **context-window guard**, and the **confirm-prompt warning display
format**.

## 1. The corrected sanity-pass gate (amends spec 006 contracts/extraction-v2.md section 2)

### Normalization (amended - identical tokenization on both sides)

Both the source text and a proposed figure value are tokenized by the *same* rule: strip every `$`
and `,` character - never whitespace, and never any other character - then take every maximal run of
`[0-9.]` characters (spec 006's own `_DIGIT_RUN_RE`, unchanged) as one token. A trailing all-zero
fractional part is then stripped from every token (spec 006's own unchanged rule: `"15000.00"`
normalizes to `"15000"`; `"753.25"` is unaffected).

This differs from spec 006's own current implementation in exactly one respect: spec 006 additionally
strips whitespace from the *proposed* value (never from the source) before comparing it as a single
token against the source's own token set. This feature removes that asymmetry - whitespace is never
stripped from either side before tokenizing, so a value that is legitimately more than one digit run
(a composite figure, a spaced identifier) is checked as the multiple tokens it actually is, on both
sides, identically.

### The membership rule (amended - per-token, not whole-blob)

A proposed figure passes the check only when **every** digit-run token extracted from it (by the
normalization above) is a member of the source's own digit-run token set. A proposed value carrying
zero digit-run tokens (no digit at all) is not a figure and passes through untouched - unchanged from
spec 006's own NIT-10 rule. A `"/"`-split value (spec 006's own split-limit convention) is still
checked as its own independent parts first, then each part's own digit-run tokens are checked against
the membership rule - unchanged from spec 006 in how the split itself works, changed only in how each
part is then compared.

**Never substring containment; never a whole-blob string match against a single token.** This is a
hard invariant, unchanged from spec 006's own FIX-FIRST-2 finding: a hallucinated figure sharing only
a digit-run suffix or prefix with a real, unrelated figure elsewhere in the source (for example, a
hallucinated `"50,000"` against a source that only ever states `"150,000"`) still fails the check
under this feature's own per-token rule, exactly as it already fails under spec 006's own rule -
this feature corrects an asymmetry in *how the proposed side is tokenized*, not the *strictness of
the comparison itself*.

### Worked shapes (structural, no real values)

| Proposed value (structural shape) | Source contains (structural shape) | Passes? |
| :--- | :--- | :--- |
| `"<A> each person/<B> each accident"` where `<A>` and `<B>` are dollar amounts | The source states `<A>` and `<B>`, verbatim, anywhere in the coverage table | Yes - both digit runs are members of the source's own token set |
| `"NNN NNN NNN"` (three digit groups separated by spaces) | The source states the same three digit groups, separated by whitespace, anywhere in the text | Yes - the source's own tokenizer already splits on whitespace, producing the same three tokens |
| `"<X>"` where `<X>` is a six-figure amount not stated anywhere in the source, but shares a trailing or leading digit run with a real, unrelated source figure | The source states only the unrelated figure | No - `<X>`'s own full digit-run token is not a member of the source's own token set |
| `"N/A"` or any value with no digit | (irrelevant) | Yes - not a figure, exempt |
| `"<A>/<B>"` where `<A>` is stated on one coverage line and `<B>` is stated on a wholly unrelated one (a RECOMBINATION of two real tokens that never actually co-occur) | The source states `<A>` and `<B>`, each verbatim, but never together, and never associated with each other | **Yes - a known, accepted gap (IMPORTANT 3, research.md D1)**, not a bug: per-token membership is insensitive to which tokens co-occur or in what combination; catching this would require associating a token with its own surrounding context, a strictly harder problem this feature does not attempt. The Director's own mandatory confirmation step is the backstop. |

**IMPORTANT 3 (Opus verifier, 2026-08-30)**: research.md's own original claim that this correction
closes the composite-figure gap "without weakening the check at all" is imprecise - the corrected
check is exact per-token, but recombination of two independently-present tokens (the row directly
above) is beyond what any per-token design can catch. The accurate claim is that the correction closes
Defect A "without weakening the PER-TOKEN EXACTNESS of the check" - the anti-hallucination invariant
(a token that is not present anywhere in the source still fails) is unchanged and unweakened; a token
that IS present, but recombined with another equally-present token it was never actually paired with
in the source, was always beyond this gate's own design, before and after this feature.

## 2. The corrected term-derivation rules (amends spec 006 contracts/extraction-v2.md section 2's
own Term derivation subsection)

| Rule | Spec 006 (current) | This feature (corrected) |
| :--- | :--- | :--- |
| Which label occurrences are searched | The first occurrence of a policy/premium-period label only | Every occurrence in the text, EXCEPT one immediately preceded (within ~20 characters) by "prior"/"previous"/"former"/"expiring" (case-insensitive) - IMPORTANT 4, below |
| Window relative to each occurrence | 150 characters before and 150 characters after | Approximately 400 characters, after the occurrence's own end only, capped at the START of the next label occurrence (whichever bound is reached first) - text before the occurrence is never included in any window |
| Which dates are used | The first two dates the date pattern finds inside the window, in the order they appear in the text | Every date that parses under the recognized United States date formats, across every SURVIVING window; the term is computed from the **maximum** and the **minimum** date collected |
| Fewer than two distinct dates found across every surviving window | Helper returns nothing; caller keeps whatever term its own generator proposed | Unchanged |
| More than two distinct dates found across every surviving window | n/a (spec 006 only ever considered the first two found) | One value-free warning is added, naming only the fact that more than two distinct dates were found - never a date value (IMPORTANT 4(ii)) |
| An explicit "N-month"/"N month" phrase exists in the de-glued text (section 3, below) | The regex-based generator's own phrase pattern is checked before calling the helper; the local-model generator's own claim is unconditionally replaced by the date-derived value regardless of any phrase | The phrase's own value takes precedence over the date-derived value, for **both** generators - amends the override direction |
| Span-to-term mapping | 11-13 months -> `"12"`; 5-7 months -> `"6"`; otherwise the exact rounded count with a warning | Unchanged - only which dates feed this mapping changes |

**IMPORTANT 4 (Opus verifier, 2026-08-30) - the prior-period exclusion**: a real declarations page can
carry more than one period section (a "Prior Policy Period" alongside the current one); without this
exclusion, the max-minus-min rule above would span a prior period's own start date to the current
period's own end date, deriving a false combined term with no warning. An occurrence preceded by one
of the four excluded words never contributes its own window as a "surviving" occurrence, AND every
date match found inside its own window is excluded from every OTHER occurrence's own window too - this
second part matters because an excluded occurrence positioned textually BEFORE a surviving one would
otherwise sweep its own forward window across the surviving occurrence's real dates too (both
occurrences' own windows are capped at the next label occurrence's own start, which is what makes this
symmetric regardless of which period is listed first). **Known, accepted residual**: a document using
a different word for its own prior-period label (not one of the four listed) is not excluded - the
multi-date warning (row above) still surfaces that more than two dates were found, for the Director's
own review, even when the exclusion itself does not recognize the phrasing (research.md D2's own
amendment).

**Precedence order, restated as ONE table (stated identically here and in section 4, below; both
generators, and the schema-extension's own `effective_date`/`expiration_date` fields, follow this same
order)**:

1. **VERIFIED explicit dates** - `effective_date` AND `expiration_date` are both present, both parse,
   AND both pass the ordinary figure gate (section 1) against the source's own digit-run tokens (BLOCK
   2(i): a date that merely parses to a valid calendar date but was never actually stated in the
   source is exactly as fabricated as any other hallucinated figure) - if both verify, the term
   computed from them (the same average-day arithmetic this section already uses) is authoritative,
   overriding every lower tier.
2. Otherwise, an explicit "N-month"/"N month" phrase in the de-glued text - if present, its value is
   authoritative.
3. Otherwise, the corrected date-derivation helper's own output (the rules table, above) - if it
   derives a value, that value is authoritative, replacing whatever either generator itself proposed
   (unconditional replacement remains correct here, since a helper output at this step already means
   no phrase was found).
4. Otherwise, whatever value the generator itself proposed passes through unexamined by this
   contract - it remains subject to the ordinary sanity-pass check (section 1) like any other figure.

**BLOCK 2(iii) - disagreement warning**: whenever tier 1 (verified dates) wins and the NEXT
lower-precedence tier that actually produced a value (tier 2 or 3, recomputed identically regardless
of which tier wins; else tier 4, the generator's own raw claim) disagrees with it, exactly ONE
value-free warning is added, naming both sources and both term VALUES (a `"12"`/`"6"`-shaped month
count is structural, not sensitive, and is named directly - never a date or a dollar figure): for
example, `"term_months from verified explicit dates (12) overrode an explicit N-month phrase (6)"`.
No warning fires when the two tiers agree.

## 3. The de-glue transformation (PRECISION-CORRECTED by BLOCK 1, Opus verifier, 2026-08-30)

| Property | Value |
| :--- | :--- |
| When it runs | Exactly once, immediately after `ConvertedDocument.text` is produced (by either converter), before any generator, the term-derivation helper, or the sanity pass reads it |
| Boundary rule 1 (lowercase -> uppercase) | UNCHANGED - insert one space at every lowercase-to-uppercase letter boundary, unconditionally. No identifier-corruption risk (a VIN, a policy number, a unit number are conventionally all-uppercase or all-digits, never mixed-case). |
| Boundary rules 2/3 (letter<->digit), CORRECTED | Insert one space at a letter-to-digit or digit-to-letter boundary only when ALL of: (a) the maximal `[A-Za-z0-9]+` run containing that boundary has a total letter<->digit transition count <= 2; (b) the digit-side segment at that boundary has length <= 3; (c) the letter-side segment at that boundary has length >= 3 |
| Why the correction | Measured directly against the Director's own three real declarations PDFs: the ORIGINAL blanket rule (insert unconditionally at every letter<->digit boundary) also fired inside real identifiers - a 17-character VIN-shaped run's own survival measured 2 -> 0, and a mixed alphanumeric identifier's own survival measured 18 -> 0, across the three documents. An identifier is a text field (section 4, below), so nothing downstream would ever have stripped the corrupted result before it reached the Director. |
| What is never touched | Any digit's own value, any currency symbol, any punctuation character already present in the text, and any boundary not named by rules 1 through 3 |
| Known, accepted residual (rules 2/3) | A glued word pair sharing neither a case-transition boundary nor a QUALIFYING letter/digit boundary (two lowercase words glued directly together with no capital letter and no digit anywhere at the seam; or a label glued to a long digit run that itself looks identifier-shaped, e.g. `"Law60500"`-shaped, protected by condition (b)) is not recoverable by this transformation - it surfaces unresolved at the Director's own confirmation step. The sanity pass still tokenizes a glued digit run correctly on its own merits regardless of adjacent letters, so nothing is lost for figure-gating purposes even when the surrounding text stays glued. |
| Known, accepted residual (rule 1) | A camel-case surname glued into `named_insureds` by the same converter artifact (`"McDonald"`-shaped) renders spaced (`"Mc Donald"`-shaped) - rule 1 cannot distinguish a glued word boundary from a genuine internal case transition inside one real word without a maintained, language-specific surname exception list (rejected for the same reason a dictionary-based gluing detector is rejected, research.md D3). `named_insureds` is a text field, read at the Director's own confirmation step (section 4, below) - a spaced surname is a visible, low-stakes cosmetic residual, never a value gated, computed from, or compared against. |
| Worked shape (structural, still de-glues) | A label glued directly to its own digit and unit (`"Total6month"`-shaped) becomes three separate tokens: 1 transition (<=2), the digit segment is 1 character (<=3), and the letter segments are 5 characters each (>=3) - all three conditions hold at both boundaries, so both qualify. The resulting text matches spec 006's own existing "N-month"/"N month" phrase pattern. |
| Worked shape (structural, identifier survives byte-identical) | A 17-character VIN-shaped run mixes letters and digits with more than 2 transitions - condition (a) alone protects the entire run, unconditionally, regardless of any individual boundary's own digit/letter segment lengths. A shorter identifier with only 1 transition but a long digit segment (`"ABC1234567"`-shaped, a 7-character digit segment) is separately protected by condition (b); a short letter-suffix unit number (`"4B"`-shaped, a 1-character letter segment) is separately protected by condition (c). |

## 4. Extended schema fields (candidate and confirmed-policy shapes)

| Field | Shape | Gate treatment | Failure behavior |
| :--- | :--- | :--- | :--- |
| `policy_number` | `str` | Corrected figure gate (section 1) | Cleared to `""`; value-free warning naming the field |
| `effective_date` / `expiration_date` | `str` | **CORRECTED by BLOCK 2(i)**: BOTH a date-parse check (must parse under the recognized United States date formats already used by the term-derivation helper) AND the ordinary figure gate (section 1) against the field's own digit-run tokens - a date that merely parses to a valid calendar date but was never actually stated in the source is fabricated, exactly like any other hallucinated figure, and is no longer sufficient on parseability alone | A parse failure clears to `""` with a warning worded distinctly from a figure-strip warning (`"...could not be parsed as a date and was removed"`); a figure-gate failure (parses fine, but not present in the source) clears to `""` with the ordinary figure-strip wording (`"a proposed <field> did not appear in the document and was removed"`) |
| `term_months` | `str` | **CORRECTED by BLOCK 2(ii), FR-011 amended**: computed from `effective_date`/`expiration_date` (via the same average-day arithmetic, section 2) ONLY when both are VERIFIED (both parse AND both pass the figure gate, above) - this is now the HIGHEST-precedence source in section 2's own restated one-table precedence, never read as a separately proposed value in that case; otherwise the section 2 precedence (phrase, then date-window, then the generator's own claim) applies exactly as before | Unchanged from spec 006 when the two dates are not both verified; a disagreement with the next lower-precedence source that produced a value is surfaced per section 2's own BLOCK 2(iii) rule |
| `policy_level_deductibles[].label` | `str` | Exempt (text) | n/a |
| `policy_level_deductibles[].value` | `str` | Corrected figure gate, when non-empty | Cleared to `""`; warning naming the entry's own label plus "deductible value" |
| `asset` (`{"address": str}` or `{"vehicle": str, "vin": str}`) | `dict` | Exempt (text) - a VIN is an alphanumeric identifier, never digit-run-tokenized as a figure | n/a |
| `named_insureds` / `excluded_drivers` | `list[str]` | Exempt (text) | n/a |
| `discounts[].label` | `str` | Exempt (text) | n/a |
| `discounts[].value` | `str` | Corrected figure gate, when non-empty (an empty `value` is a valid, unremarkable state - not every discount states its own dollar or percentage figure) | Cleared to `""`; warning naming the entry's own label plus "discount value" |
| `fees[].label` | `str` | Exempt (text) | n/a |
| `fees[].amount` | `str` | Corrected figure gate | Cleared to `""`; warning naming the entry's own label plus "fee amount" |
| `subtotal` | `str` | Corrected figure gate | Cleared to `""`; warning naming the field |

The local-model extraction prompt is extended to request every field in this table, using the same
"copied verbatim from the document, never invented, estimated, or inferred" instruction spec 006's
own prompt already states for `insurer`/`premium`/`coverages`.

## 5. Cache compatibility

| Field | Absent on a cache file written before... | Reader behavior |
| :--- | :--- | :--- |
| `warnings` | This feature | Empty list - never an error |
| Any of the ten schema-extension fields (section 4) | This feature | The field's own empty shape (`""`, `[]`, or `{}`) - never an error, never a `KeyError` |
| `generator` / `converter` | Spec 006 | Unchanged from spec 006: `"unknown"` |

A reader of a cache file this feature's own extended shape produces is unaffected when it does not yet
know about the new fields - a reader written for spec 006's own shape ignores extra keys it does not
recognize, the ordinary behavior of a JSON object reader in this codebase.

## 6. The context-window guard (CORRECTED by IMPORTANT 5, Opus verifier, 2026-08-30)

| Property | Value |
| :--- | :--- |
| `options.num_ctx` | An explicit integer added to the local-model request's own `options` object, alongside the existing `"temperature": 0`. Default `16384` - verified via `ollama show <model>` (localhost, read-only) against this machine's own configured model, which reports a context length of 262144 (well over the 16k floor this default targets). |
| Length estimate, CORRECTED | A simple, deterministic estimate (character count divided by a fixed average characters-per-token constant) against the FULL PROMPT actually sent to the model (`_build_extraction_prompt(document.text)`) - **not** the de-glued document text alone, which under-measured the request by the prompt template's own fixed instructional overhead. Computed before the request is built. |
| Threshold, CORRECTED | `num_ctx` minus a fixed response reserve (`DEFAULT_RESPONSE_RESERVE_TOKENS = 1024`), never the raw `num_ctx` value - `num_ctx` bounds the prompt AND the model's own response together, so measuring the prompt alone against the full window would let a prompt that leaves no room at all for a response still pass unremarked. |
| On exceeding the threshold | One value-free warning is added to the resulting candidate's own `warnings` list, naming only the estimated count and the reserve-adjusted threshold - never `num_ctx` itself when it differs from the threshold, and never the document's own content. The request is still sent; this is a warning, not a refusal. |

## 7. Confirm-prompt warning display format

| Condition | Printed output, in order |
| :--- | :--- |
| Candidate carries one or more warnings | (1) A labeled section: a count line (naming how many warnings follow), then each warning on its own line. (2) The existing "Extracted current-policy candidate..." header and full JSON block (spec 006, unchanged - the JSON still embeds the same `warnings` list, now 14 keys total after this feature's own schema extension). (3) The existing accept-correct-decline question. |
| Candidate carries zero warnings | Only (2) and (3), above - no warnings section prints. |

The warnings section is printed text only - it introduces no new prompt, no new question, and no
new accept/correct/decline outcome. The Director's own existing choice (accept as printed, correct
by hand, or decline) is unchanged.

**IMPORTANT 6 (Opus verifier, 2026-08-30)**: the "correct" branch's own follow-up prompt now reads
"Paste the corrected JSON document (the same object printed above)" - naming the object the Director
was just shown, rather than a stale, literal "insurer/premium/coverages" list that predates this
feature's own ten-field schema extension. The reparse target (`CurrentPolicy.from_dict`) reads 13
keys (every key in the printed object except `warnings`, which a confirmed `CurrentPolicy` never
carries) - a corrected paste retaining all 13 keeps every one of the ten new fields, exactly as a
paste retaining only the original 3 (`insurer`/`premium`/`coverages`) already did before this feature.

**MINOR 8 (Opus verifier, 2026-08-30) - semantics, not a behavior change**: the `warnings` field on a
cached `PolicyReference` (section 5) always records the sanity pass's own findings AT THE MOMENT OF
REVIEW - the state the Director actually saw at this very prompt - never a live description of the
finally cached policy's own current state. If the Director chose "correct" and pasted a hand-typed
replacement, that replacement may address (or be unrelated to) exactly what a given warning named;
`warnings` still reflects what the sanity pass found before that correction, the same audit-trail role
`source_path`/`confirmed_at` already play for the reference as a whole.
