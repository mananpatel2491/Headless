# Contracts: Extraction Fidelity

**Feature**: 007-extraction-fidelity | **Date**: 2026-08-29

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

## 2. The corrected term-derivation rules (amends spec 006 contracts/extraction-v2.md section 2's
own Term derivation subsection)

| Rule | Spec 006 (current) | This feature (corrected) |
| :--- | :--- | :--- |
| Which label occurrences are searched | The first occurrence of a policy/premium-period label only | Every occurrence in the text |
| Window relative to each occurrence | 150 characters before and 150 characters after | Approximately 400 characters, after the occurrence's own end only - text before the occurrence is never included in any window |
| Which dates are used | The first two dates the date pattern finds inside the window, in the order they appear in the text | Every date that parses under the recognized United States date formats, across every window; the term is computed from the **maximum** and the **minimum** date collected |
| Fewer than two dates found across every window | Helper returns nothing; caller keeps whatever term its own generator proposed | Unchanged |
| An explicit "N-month"/"N month" phrase exists in the de-glued text (section 3, below) | The regex-based generator's own phrase pattern is checked before calling the helper; the local-model generator's own claim is unconditionally replaced by the date-derived value regardless of any phrase | The phrase's own value takes precedence over the date-derived value, for **both** generators - amends the override direction |
| Span-to-term mapping | 11-13 months -> `"12"`; 5-7 months -> `"6"`; otherwise the exact rounded count with a warning | Unchanged - only which dates feed this mapping changes |

**Precedence order, restated as one table** (both generators follow this order):

1. An explicit "N-month"/"N month" phrase in the de-glued text - if present, its value is
   authoritative.
2. Otherwise, the corrected date-derivation helper's own output (section 2, above) - if it derives a
   value, that value is authoritative, replacing whatever either generator itself proposed
   (unconditional replacement remains correct here, since a helper output at this step already means
   no phrase was found).
3. Otherwise, whatever value the generator itself proposed passes through unexamined by this
   contract - it remains subject to the ordinary sanity-pass check (section 1) like any other figure.

## 3. The de-glue transformation

| Property | Value |
| :--- | :--- |
| When it runs | Exactly once, immediately after `ConvertedDocument.text` is produced (by either converter), before any generator, the term-derivation helper, or the sanity pass reads it |
| Boundary rule 1 | Insert one space at every lowercase-to-uppercase letter boundary (a lowercase letter immediately followed by an uppercase letter) |
| Boundary rule 2 | Insert one space at every letter-to-digit boundary (a letter immediately followed by a digit) |
| Boundary rule 3 | Insert one space at every digit-to-letter boundary (a digit immediately followed by a letter) |
| What is never touched | Any digit's own value, any currency symbol, any punctuation character already present in the text, and any boundary not named by rules 1 through 3 |
| Known, accepted residual | A glued word pair sharing neither a case-transition boundary nor a letter/digit boundary (two lowercase words glued directly together, with no capital letter and no digit anywhere at the seam) is not recoverable by this transformation - it surfaces unresolved at the Director's own confirmation step |
| Worked shape (structural) | A label glued directly to its own digit and unit (`"Total6month"`-shaped) becomes three separate tokens after both boundary rules apply (letter-to-digit, then digit-to-letter) - the resulting text now matches spec 006's own existing "N-month"/"N month" phrase pattern |

## 4. Extended schema fields (candidate and confirmed-policy shapes)

| Field | Shape | Gate treatment | Failure behavior |
| :--- | :--- | :--- | :--- |
| `policy_number` | `str` | Corrected figure gate (section 1) | Cleared to `""`; value-free warning naming the field |
| `effective_date` / `expiration_date` | `str` | Date-parse check (must parse under the recognized United States date formats already used by the term-derivation helper) - **not** the figure gate | Cleared to `""`; value-free warning naming the field, worded distinctly from a figure-strip warning (`"could not be parsed as a date"`) |
| `term_months` | `str` | Computed from `effective_date`/`expiration_date` (via the same average-day arithmetic, section 2) when both parse; otherwise the existing spec 006 exemption/gate rule applies unchanged | Unchanged from spec 006 when the two dates do not both parse |
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

## 6. The context-window guard

| Property | Value |
| :--- | :--- |
| `options.num_ctx` | An explicit integer added to the local-model request's own `options` object, alongside the existing `"temperature": 0` |
| Length estimate | A simple, deterministic estimate (for example, character count divided by a fixed average characters-per-token constant) against the de-glued `ConvertedDocument.text`, computed before the request is built |
| Threshold | The same `num_ctx` value |
| On exceeding the threshold | One value-free warning is added to the resulting candidate's own `warnings` list, naming only the estimated count and the configured threshold - the request is still sent; this is a warning, not a refusal |

## 7. Confirm-prompt warning display format

| Condition | Printed output, in order |
| :--- | :--- |
| Candidate carries one or more warnings | (1) A labeled section: a count line (naming how many warnings follow), then each warning on its own line. (2) The existing "Extracted current-policy candidate..." header and full JSON block (spec 006, unchanged - the JSON still embeds the same `warnings` list). (3) The existing accept-correct-decline question. |
| Candidate carries zero warnings | Only (2) and (3), above - no warnings section prints. |

The warnings section is printed text only - it introduces no new prompt, no new question, and no
new accept/correct/decline outcome. The Director's own existing choice (accept as printed, correct
by hand, or decline) is unchanged.
