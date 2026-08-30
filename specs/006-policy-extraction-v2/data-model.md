# Data Model: Policy Extraction v2

**Feature**: 006-policy-extraction-v2 | **Date**: 2026-08-29

No database, no new persisted directory. The one existing persisted artifact this feature touches
is `reports/policy/<asset-key>.json` (spec 005), which gains two additive fields. Everything else
below is in-memory for the lifetime of one `scripts/policy_extract.py` invocation, or is the
description of a pure function's own contract.

## The candidate pipeline states

A `policy_doc` PDF moves through four states before a figure is safe to compare against. Every
arrow in this pipeline is enforced by this feature or by v0.0.5 (unchanged); no state is ever
skipped, and no state after "converted" is reachable without the state before it having already
happened.

```text
converted-text -> proposed -> sanity-passed -> confirmed
```

| State | Produced by | Shape | Persisted? |
| :--- | :--- | :--- | :--- |
| `converted-text` | The layout-aware converter, or `pypdf` raw text on fallback (FR-001, FR-002) | `ConvertedDocument` (below) | No - in-memory only, for the duration of one asset's own extraction attempt |
| `proposed` | The local-model generator, or the regex-based generator on fallback (FR-004) | `ExtractionCandidate` (unchanged from v0.0.5) | No |
| `sanity-passed` | The mechanical sanity pass (FR-017 through FR-020) | `ExtractionCandidate` (same type; some figures possibly stripped, `warnings` possibly extended) | No |
| `confirmed` | `confirm_candidate` (unchanged from v0.0.5) - the Director's own accept-or-correct choice | `CurrentPolicy` | Yes - `write_policy_reference` writes it as `PolicyReference` (extended, below) to `reports/policy/<asset-key>.json` |

A candidate that never reaches `confirmed` (the Director declines, or a corrected document fails
to parse) is discarded with no cache write, exactly as v0.0.5 already behaves - this feature adds
no new discard path beyond the ones v0.0.5 already defines.

## ConvertedDocument

The in-memory result of the conversion step (FR-001, FR-002). Never written to disk; never
printed on its own (only a proposed candidate built from it is ever shown to the Director).

| Field | Type | Rules |
| :--- | :--- | :--- |
| `text` | `str` | The converted content - Markdown when the layout-aware converter served the run, plain text on `pypdf` fallback. Empty or absent text collapses to the same "nothing to offer the Director" outcome (`None`, FR-015) v0.0.5 already defines. |
| `converter` | `str` | The literal provenance string carried forward to `PolicyReference.converter` (FR-023): the layout-aware converter's own name, or `"pypdf-raw"` on fallback. Never a version string or a path - just which of the two code paths produced `text`. |

## ExtractionCandidate (unchanged shape, new generators)

Carried over from v0.0.5 without a field added or removed:

```text
ExtractionCandidate(insurer: str, premium: dict, coverages: list, warnings: list)
```

What changes in this feature is which code populates it (the local-model generator, or the
regex-based generator on fallback) and that it now passes through the sanity pass (below) before
it ever reaches `confirm_candidate`. A `warnings` entry this feature adds is a plain string, in the
same value-free convention v0.0.5's own warnings already use (`"no insurer detected"`,
`"no term detected"`) - never a figure's own value, never a fragment of source text.

**New warning shapes this feature introduces** (all value-free, naming only a field or a fact,
never a value):

- `"a proposed <field> did not appear in the document and was removed"` (FR-018)
- `"term_months derived from policy-period dates overrode the model's own claim"` (FR-020)
- `"term derived as <N> months, outside the two common terms"` (FR-021, when the computed span is
  not 11-13 or 5-7 months - `<N>` is the derived month count, a computed integer, not a value read
  from the document, so this is not a document-value leak)
- `"local model unavailable, fell back to the regex-based generator"` (FR-013)

## The mechanical sanity pass (a pure operation, not a new type)

The sanity pass is a function over an `ExtractionCandidate` and the `ConvertedDocument.text` it
was proposed from, returning a (possibly modified) `ExtractionCandidate` - not a new dataclass,
since its whole job is to filter and annotate the type that already exists.

| Input figure | Checked how (FR-017) | On failure (FR-018) |
| :--- | :--- | :--- |
| `premium.amount` | Strip `$`, commas, whitespace from both the proposed value and every substring of the source text; the proposed digit sequence must appear in the source's own digit sequence | Set to `""`; warning added |
| Each coverage line's `limit` | Same normalization; a split-limit value (`"100,000/300,000"`) is checked as its own two digit sequences, both required | Set to `""`; warning added |
| Each coverage line's `deductible` | Same normalization | Set to `""`; warning added |
| Each coverage line's `premium` | Same normalization | Set to `""`; warning added |
| `premium.term_months` | Exempt (FR-019) when derived by the helper below from two in-text dates; otherwise checked the same way as any other figure | Same as any other figure, when not exempt |
| `insurer` | Never checked (FR-028) - a text field, not a figure | n/a |
| Each coverage line's `line` (its own name/slug) | Never checked (FR-028) - a text field, not a figure | n/a |

A candidate every one of whose coverage lines loses its own `limit` this way still reaches
`confirm_candidate` with an empty `coverages` entry for that line, not a dropped line entirely -
the Director's own correction path (typing a replacement JSON document) is how a stripped figure
gets a real value back, the same accept-or-correct choice he already has for any other extraction
gap.

## Term derivation (a pure helper, shared by both generators)

| Property | Value |
| :--- | :--- |
| Input | The converted text; a policy-period label to search near (the same label v0.0.5's own heuristics already look for) |
| Recognizes | Two dates in common United States formats (for example `MM/DD/YYYY`, `Month D, YYYY`) appearing near that label, regardless of which one reads as the start and which as the end - the real document's own reversed order (`"To:" date before `"From:"` date) is exactly the case this helper exists to survive |
| Computes | Calendar-month span between the two dates |
| Output | `term_months: str`, plus an optional warning when the span is not one of the two common terms |

| Computed span | `term_months` | Warning? |
| :--- | :--- | :--- |
| 11-13 months | `"12"` | No |
| 5-7 months | `"6"` | No |
| Anything else | The exact rounded month count, as a string | Yes - "term derived as `<N>` months, outside the two common terms" |
| Fewer than two dates found near the label | (helper returns nothing; the candidate's own `term_months` falls back to whatever the generator itself proposed, subject to the ordinary sanity-pass check) | n/a |

Both generators call this same helper (FR-022): the local-model generator uses it to override or
corroborate the model's own claimed term (FR-020); the regex-based generator uses it as a second
attempt whenever its own `"N-month"` phrase pattern does not match - closing the annual-home-
policy gap in the *regex* path too, not only in the new model-based one (research.md D8).

## PolicyReference (extended)

v0.0.5's shape, with two additive fields (FR-023). Every existing field, and `write_policy_
reference`/`read_policy_reference`'s own function signatures, are unchanged.

| Field | Type | v0.0.5 or new? | Rules |
| :--- | :--- | :--- | :--- |
| `policy` | `CurrentPolicy` | v0.0.5, unchanged | The confirmed document |
| `asset_key` | `str` | v0.0.5, unchanged | `<array-name>-<type>`, e.g. `vehicles-primary` |
| `source_path` | `str` | v0.0.5, unchanged | The PDF's own path |
| `confirmed_at` | `str` | v0.0.5, unchanged | ISO 8601 UTC timestamp |
| `generator` | `str` | **New (FR-023)** | `"regex-v1"` or `"local-llm:<model-name>"` - which code path produced the confirmed candidate before the Director's own review |
| `converter` | `str` | **New (FR-023)** | The layout-aware converter's own name, or `"pypdf-raw"` - which code path produced the source text the candidate was proposed from |

**Invariant - additive only**: a cache file written by v0.0.5 (before this feature existed) has
no `generator`/`converter` keys at all. `read_policy_reference`'s own existing tolerance for a
malformed or partial file (v0.0.5's already-documented "a malformed cache is treated exactly like
a missing one" behavior does not apply here, since a v0.0.5 file is not malformed, only older) is
not this feature's concern to redefine; a reader of the two new fields treats their absence as
"generator/converter unknown," a value-free state, never an error.

**Invariant - the confirm gate is not itself extended**: `confirm_candidate`'s own signature and
behavior are untouched (FR-025). The `generator`/`converter` values are attached to the
`PolicyReference` by the orchestrating script (`scripts/policy_extract.py`) at the moment it
constructs one, from information the pipeline already has in hand (which generator ultimately
produced the confirmed candidate; which converter produced the text it was built from) - never
derived by asking the Director, and never printed at the confirmation prompt itself, which
continues to show only the `CurrentPolicy`-shaped fields v0.0.5 already prints.

## The local-model request/response contract (dict shapes, not new dataclasses)

Deliberately kept as plain dictionaries passed through the injectable transport, not a
dataclass pair - this is an external HTTP contract this feature does not own the far side of, so
adding a Python type around it would suggest a stability guarantee only Ollama's own API can
actually provide. See `contracts/extraction-v2.md` for the full normative shape.

| Direction | Shape |
| :--- | :--- |
| Request body | `{"model": str, "prompt": str, "format": "json", "stream": false, "think": false, "options": {"temperature": 0}}` |
| Successful response body (Ollama's own envelope) | `{"response": "<JSON string matching the candidate schema>", ...other Ollama fields, ignored}` |
| Parsed candidate schema (what `response`'s own string must decode to) | `{"insurer": str, "premium": {"term_months": str, "amount": str}, "coverages": [{"line": str, "limit": str, "deductible": str, "premium": str}, ...]}` - identical to `ExtractionCandidate`'s own shape, so the same construction the regex generator already uses accepts either origin |
