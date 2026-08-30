# Data Model: Extraction Fidelity

**Feature**: 007-extraction-fidelity | **Date**: 2026-08-29

No database, no new persisted directory. The one existing persisted artifact this feature touches is
`reports/policy/<asset-key>.json` (spec 005, extended by spec 006), which gains one additive field
(`warnings`) plus whichever of this feature's own new schema fields a given confirmed candidate
actually carries. Everything else below is in-memory for the lifetime of one
`scripts/policy_extract.py` invocation, or is the description of a pure function's own contract.

## The candidate pipeline states (unchanged shape, corrected internals)

Spec 006's own four-state pipeline is unchanged in shape; this feature corrects what happens inside
two of its states and adds one new pass:

```text
converted-text -> de-glued -> proposed -> sanity-passed -> confirmed
```

| State | Produced by | What changes in this feature |
| :--- | :--- | :--- |
| `converted-text` | The layout-aware converter, or `pypdf` raw text on fallback (spec 006, unchanged) | No change to how conversion itself happens |
| `de-glued` | The new boundary-insertion transformation (FR-012 through FR-016) | **New state.** Runs once, immediately after conversion, before either generator or the term-derivation helper ever reads the text |
| `proposed` | The local-model generator, or the regex-based generator on fallback (spec 006, unchanged dispatch) | Both generators now read de-glued text; the local-model generator's own term handling now prefers an explicit phrase over date arithmetic (FR-010) |
| `sanity-passed` | The corrected mechanical sanity pass (FR-001 through FR-005, FR-025) | The literal-match check is corrected (per-token membership on both sides); the schema extension's own figure-shaped fields are gated the same way (FR-004, FR-025) |
| `confirmed` | `confirm_candidate`, extended to print the new warnings section (FR-019 through FR-021) | The Director's own accept-or-correct choice is otherwise unchanged; the confirmed reference now carries `warnings` (FR-017) |

## ConvertedDocument (de-glued in place)

Spec 006's own shape (`text`, `converter`) is unchanged; what changes is a guarantee about `text`'s
own content.

| Field | Type | Rules |
| :--- | :--- | :--- |
| `text` | `str` | **Amended (FR-012 through FR-016)**: always the de-glued form - every lowercase-to-uppercase and letter/digit boundary in the converted text has a space inserted at it, exactly once, before any other function ever reads this field. No digit, currency symbol, or existing punctuation character is altered. |
| `converter` | `str` | Unchanged from spec 006: the layout-aware converter's own name, or `"pypdf-raw"` on fallback. |

## ExtractionCandidate (extended)

Spec 006's own three fields (`insurer`, `premium`, `coverages`) plus `warnings` are unchanged in
name; this feature adds ten new fields, all additive.

```text
ExtractionCandidate(
    insurer: str, premium: dict, coverages: list, warnings: list,
    policy_number: str = "", effective_date: str = "", expiration_date: str = "",
    policy_level_deductibles: list = [], asset: dict = {},
    named_insureds: list = [], excluded_drivers: list = [],
    discounts: list = [], fees: list = [], subtotal: str = "",
)
```

| Field | Type | New / spec 006 | Gate treatment |
| :--- | :--- | :--- | :--- |
| `insurer` | `str` | Spec 006, unchanged | Exempt (text) |
| `premium.amount` | `str` | Spec 006, unchanged | Corrected figure gate (FR-001, FR-002) |
| `premium.term_months` | `str` | Spec 006, unchanged | Computed from `effective_date`/`expiration_date` when both parse (FR-024); otherwise exempt when it equals the phrase- or date-derived value (FR-011), else the corrected gate |
| `coverages[].line` | `str` | Spec 006, unchanged | Exempt (text) |
| `coverages[].limit` / `.deductible` / `.premium` | `str` | Spec 006, unchanged | Corrected figure gate |
| `warnings` | `list[str]` | Spec 006, unchanged shape | n/a - a list of value-free strings, never itself a gated value |
| `policy_number` | `str` | **New (FR-023)** | Corrected figure gate (FR-025) - a digit-run identifier, whether spaced or unspaced |
| `effective_date` / `expiration_date` | `str` | **New (FR-023)** | Date-parse check, not the figure gate (FR-026) |
| `policy_level_deductibles` | `list[{label, value}]` | **New (FR-022)** | `label` exempt (text); `value` under the corrected figure gate when non-empty (FR-025) |
| `asset` | `dict` - `{"address": str}` or `{"vehicle": str, "vin": str}` | **New (FR-023)** | Exempt (text) - a VIN is an alphanumeric identifier, not a figure (FR-027) |
| `named_insureds` / `excluded_drivers` | `list[str]` | **New (FR-023)** | Exempt (text) |
| `discounts` | `list[{label, value}]` | **New (FR-023)** | `label` exempt; `value` under the corrected figure gate when non-empty (FR-025) |
| `fees` | `list[{label, amount}]` | **New (FR-023)** | `label` exempt; `amount` under the corrected figure gate (FR-025) |
| `subtotal` | `str` | **New (FR-023)** | Corrected figure gate (FR-025) |

**New warning shapes this feature introduces** (all value-free, naming only a field or a fact, never
a value):

- `"a proposed <field> did not appear in the document and was removed"` - unchanged wording from spec
  006, now also produced for a schema-extension figure field (FR-025).
- `"<field> could not be parsed as a date and was removed"` (FR-026) - for `effective_date`/
  `expiration_date`.
- `"term_months derived from an explicit N-month phrase overrode the model's own claim"` (FR-010) -
  a new variant of spec 006's own override note, naming the phrase rather than the date derivation
  as the winning source.
- `"converted document is long enough that the local model's context window may truncate it (an
  estimated <N> tokens against a <M>-token guard)"` (FR-032) - `<N>`/`<M>` are computed counts, not
  document content.

## CurrentPolicy (extended, mirrors ExtractionCandidate)

`headless/capture.py`'s own `CurrentPolicy` gains the same ten fields as `ExtractionCandidate`
(minus `warnings`, which a confirmed policy never carries - only the surrounding `PolicyReference`
does, per the section below), so `confirm_candidate`'s own accept/correct construction can carry
every field through unchanged. `to_dict()`/`from_dict()` are extended additively; a corrected JSON
document (the Director's own hand-typed correction at the confirmation prompt) omitting any of the
ten new fields defaults each one to its own empty shape (`""`, `[]`, or `{}`), never a `KeyError`.

## The corrected mechanical sanity pass (a pure operation, not a new type)

| Input figure | Checked how (FR-001, FR-002) | On failure (unchanged shape) |
| :--- | :--- | :--- |
| Any figure-shaped field (spec 006's own four, plus this feature's own six new ones under FR-025) | Strip only `$` and `,` from the proposed value (never whitespace); extract every maximal digit-run token from what remains, normalized by the existing trailing-zero rule; require **every** such token to be a member of the source's own digit-run token set | Set to `""`; warning added, naming only the field |
| A split value (`"/"`-separated, spec 006's own convention) | Each `"/"`-separated part is tokenized and checked independently, exactly as spec 006 already does for a split limit - unaffected by this feature's own per-token correction, which only changes how a *single* part's own cleaned string is compared, not the split itself | Same as any other figure |
| A value with zero digit-run tokens | Exempt (unchanged NIT-10 rule, spec 006) | n/a |
| `insurer`, coverage line `line`, `asset`, `named_insureds`, `excluded_drivers`, every `label` field | Never checked - text fields (FR-027, extending spec 006 FR-028) | n/a |
| `effective_date`, `expiration_date` | Date-parse check instead of the figure gate (FR-026) | Cleared to `""`; warning added |

**The corrected token-set comparison itself** (replacing spec 006's own whole-blob comparison):

```text
source_tokens = { normalize(t) for t in digit_runs(strip($,)(source_text)) }

proposed_tokens = { normalize(t) for t in digit_runs(strip($,)(proposed_value)) }

passes = proposed_tokens == {} or proposed_tokens ⊆ source_tokens
```

Where `digit_runs` extracts every maximal run of `[0-9.]` characters (spec 006's own
`_DIGIT_RUN_RE`, unchanged) and `normalize` is spec 006's own existing trailing-`.00`/`.0` rule,
unchanged. The only change from spec 006's own current implementation is that `strip($,)` (not
`strip($, whitespace)`) is now applied identically to both `source_text` and `proposed_value` before
either is tokenized, and membership is checked per-token (`⊆`) rather than as one merged string
(`==` against a single token).

## Term derivation (extended: scan every label, window after-only, max-minus-min, phrase preference)

| Property | Spec 006 (current) | This feature (corrected) |
| :--- | :--- | :--- |
| Label occurrences considered | The first only | Every occurrence (FR-006) |
| Window | 150 characters before and after each occurrence | Approximately 400 characters, after each occurrence only - never before (FR-007) |
| Dates considered | The first two found in the window, in reading order | Every date parsed across every window; the term uses the maximum and the minimum date collected (FR-008) |
| Fewer than two dates found | Helper returns nothing | Unchanged (FR-009) |
| An explicit "N-month"/"N month" phrase in the de-glued text | Only the regex-based generator's own phrase pattern checks this, before ever calling the helper; the local-model generator's own claim is always replaced by the date-derived value | **Amended (FR-010)**: the phrase, when present, takes precedence over the date-derived value for *both* generators |
| Span-to-term mapping (11-13 -> "12", 5-7 -> "6", otherwise the exact rounded count with a warning) | Spec 006's own unchanged arithmetic | Unchanged - only the inputs to this mapping (which dates are considered) change |

## PolicyReference (extended: warnings, plus whatever schema fields the confirmed policy carries)

Spec 006's own shape, with one additive field at the reference level (`warnings`); the schema
extension's own ten new fields live on `policy` (the embedded `CurrentPolicy`), not on
`PolicyReference` directly, since they describe the policy itself, not this reference's own
provenance.

| Field | Type | Spec 006 or new? | Rules |
| :--- | :--- | :--- | :--- |
| `policy` | `CurrentPolicy` (extended, above) | Spec 005/006, extended by this feature | The confirmed document, now carrying the ten new schema fields when present |
| `asset_key` | `str` | Spec 005, unchanged | `<array-name>-<type>` |
| `source_path` | `str` | Spec 005, unchanged | The PDF's own path |
| `confirmed_at` | `str` | Spec 005, unchanged | ISO 8601 UTC timestamp |
| `generator` | `str` | Spec 006, unchanged | `"regex-v1"` or `"local-llm:<model-name>"` |
| `converter` | `str` | Spec 006, unchanged | The layout-aware converter's own name, or `"pypdf-raw"` |
| `warnings` | `list[str]` | **New (FR-017)** | The sanity pass's own warnings list at the moment of confirmation - empty by default |

**Invariant - additive only (extends spec 006's own invariant)**: a cache file written before this
feature existed has no `warnings` key. A reader treats its absence as an empty list, never an error -
the same additive-only compatibility rule spec 006's own `generator`/`converter` fields already
established for a cache file written before spec 006 existed (FR-018).

**Invariant - the confirm gate is not itself extended**: `confirm_candidate`'s own accept/correct/
decline semantics are unchanged (FR-019 through FR-021 only add a printed section ahead of the
existing question); the ten new schema fields and the `warnings` field are attached by the
orchestrating script from information the pipeline already has in hand, never derived by asking the
Director a new question.

## The confirmation prompt's warnings section (a rendering rule, not a new type)

| Condition | Output |
| :--- | :--- |
| Candidate carries one or more warnings | Prints a labeled section (a count line, then each warning on its own line), followed by the existing full JSON block, followed by the existing accept-correct-decline question (FR-019, FR-021) |
| Candidate carries zero warnings | No warnings section prints; the existing full JSON block and question print exactly as spec 006 already defines (FR-020) |

## The local-model request's context-window guard (a value on an existing dict, not a new type)

| Property | Value |
| :--- | :--- |
| `options.num_ctx` | An explicit integer, added to the existing `options` object (`{"temperature": 0}` becomes `{"temperature": 0, "num_ctx": <value>}`) (FR-032) |
| Length-estimate check | Runs against the de-glued `ConvertedDocument.text`, before the request is built; compares an estimated token count to `num_ctx` |
| On exceeding the threshold | One value-free warning, naming only the estimated count and the threshold - never the document's own content |
