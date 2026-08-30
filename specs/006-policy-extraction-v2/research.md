# Research: Policy Extraction v2

**Feature**: 006-policy-extraction-v2 | **Date**: 2026-08-29

This document records the evidence gathered before this feature was scoped, and the ten
design decisions (D1-D10) that follow from it. All ten were fixed by the Director before
`spec.md` was drafted and are not reopened here; where an implementation detail was left to
this spec's own discretion (a module's placement, an HTTP client choice), that choice is
recorded as a sub-decision under the D-number it serves, not as a new top-level decision.

## Evidence

### The real-document failure that scoped this feature

On 2026-08-29, against a real, three-page homeowners declarations PDF (values withheld by
policy; never reproduced in this repository at any point), `pypdf`'s own plain-text
extraction returned a full text layer (4,582 characters - the PDF is not an image-only,
OCR-requiring document) with its multi-column layout scrambled. The literal artifact this
produced, verified on this machine:

```text
12/01/2026To:12/01/2025From:Policy Period:
```

Two dates, a "To:" label, a "From:" label, and a "Policy Period:" label, all present but
interleaved and reversed relative to how a human reading the page would encounter them. No
v0.0.5 regex heuristic - all of which assume left-to-right, top-to-bottom reading order - can
recover a period, a premium, or a coverage limit from text in this shape. This is a structural
property of `pypdf`'s own column handling, not a defect the v0.0.5 heuristics could have been
tuned to survive; regex-only tuning against multi-column scrambling was considered and rejected
for exactly this reason (see Alternatives, below).

### Real-world learnings this feature must account for

- Home insurance policies are annual. A homeowners declarations page has no reason to contain an
  "N-month" phrase anywhere in its own text - the only reliable evidence of the policy's term is
  the pair of dates the policy period itself states (`12/01/2025` to `12/01/2026` in the example
  above). v0.0.5's own `_TERM_RE` (`\b(6|12)\s*[- ]?month`) can never match this document, at any
  confidence level, because the phrase it looks for is not there to find.
- Premium labels vary by insurer and product. The example document uses "Total Policy Premium,"
  a label v0.0.5's own `_PREMIUM_LINE_RE` (`Total Premium|Premium Due|Policy Premium`) already
  matches via its `Policy Premium` alternative, but the broader lesson - that a fixed, short
  alternation of label phrasings is inherently incomplete against real declarations pages this
  delivery has not yet seen - is what motivates handing candidate generation to a model that can
  read a whole converted page's context, rather than only ever adding one more alternative to a
  regex.

### The local-model seam, proven before this feature was scoped

Against a synthetic snippet reproducing the real document's own scrambled-column, annual-term
shape (no real value in the snippet at any point), a request to a local Ollama server returned a
valid, schema-conformant JSON candidate in 3.3 seconds and correctly derived `term_months`
`"12"` from the reversed period dates - proving the core value proposition (a model that can read
a whole converted page's context recovers information a line-by-line regex cannot) before any
implementation work began.

**Verified request/response shape**:

- Endpoint: `POST http://localhost:11434/api/generate`
- Payload: `{"model": "...", "prompt": "...", "format": "json", "stream": false,
  "think": false, "options": {"temperature": 0}}`
- Model used: `qwen3.5:35b`

**Critical gotcha, verified empirically**: omitting `"think": false` from the payload causes
`qwen3.5` to spend its entire token budget on its own internal reasoning and return an **empty**
`response` field - not an error, not a shorter answer, an empty string. The request MUST set
`"think": false` explicitly; there is no other way observed on this machine to prevent it.
Because a future model version, a misconfigured payload, or an unrelated Ollama upgrade could in
principle still hand back an empty response despite the flag being set, an empty response is
treated as a first-class failure mode in its own right (FR-011), not merely as evidence the
`think` flag was once forgotten.

**Residual observed, not a blocker**: a standalone deductible line ("All Perils Deductible:
$1,000") was not attached to the coverage row it belongs with in the naive prompt used for this
proof. This feature does not solve line-attachment as a parsing problem; it is absorbed by
prompt design (best-effort attachment, out of this spec's own normative requirements) and, when
attachment still fails, by the Director's own confirmation step - the same recourse he already
has for any other extraction gap.

**Installed local models on this machine** (`ollama list`): `qwen3.5:35b` (the default choice for
this feature), `qwen3-coder:30b`, `llama3.2:3b`. Any of the three could serve as
`HEADLESS_OLLAMA_MODEL`; `qwen3.5:35b` is the default because it is the one this feature's own
proof-of-concept ran against.

### Converter candidates evaluated (PyPI, verified available)

| Package | Version | License | Notes |
| :--- | :--- | :--- | :--- |
| `pymupdf4llm` | 1.28.2 | AGPL-3 / commercial dual | Purpose-built PDF-to-Markdown conversion with layout awareness - the only candidate of the three built specifically for feeding a language model a correctly-ordered page |
| `markitdown` | 0.1.7 | MIT | General-purpose, heavier dependency footprint (pulls in `requests`, `magika`, and others this codebase does not otherwise need) |
| `pdfplumber` | 0.11.10 | MIT (via `pdfminer.six`) | Layout-ordered text, but produces plain text, not Markdown - no heading/table structure a model's prompt could lean on |

## D1. Pipeline shape (Director decision)

**Decision**: `policy_doc` PDF -> layout-aware conversion -> local-model candidate proposal ->
mechanical sanity pass -> the existing mandatory Director confirmation gate (unchanged) -> the
existing `reports/policy/<asset-key>.json` cache (unchanged). Only the candidate-generation step
changes; `ExtractionCandidate`, `confirm_candidate`, `PolicyReference`,
`write_policy_reference`/`read_policy_reference`, and `scripts/quote_compare.py`'s own
consumption of a confirmed reference are all untouched by this feature.

**Rationale**: v0.0.5's own confirmation gate already carries the property this feature most
needs - nothing reaches a comparison without a human looking at it first - so the smallest, most
auditable change is to keep that gate exactly as it is and improve only what it is fed. Reusing
the existing `ExtractionCandidate` shape for a model-generated candidate (rather than inventing a
parallel type) means the confirmation prompt, the correction path, and every downstream consumer
need no awareness that a candidate's own origin changed.

## D2. Converter choice: one dependency, one fallback

**Decision**: exactly one converter dependency, `pymupdf4llm`, as an ordinary (not a separate
optional-extras) entry in `requirements.txt`. When it is unavailable (import failure) or its
conversion call raises, extraction falls back to the existing `pypdf` raw-text extraction path
(v0.0.5's own text-extraction call) - not to a second, independently-maintained converter.
`markitdown` and `pdfplumber` were both evaluated and rejected.

**Rationale**: `pymupdf4llm` is the only one of the three candidates built specifically for the
job this feature needs (a correctly-ordered page handed to a language model), and reusing the
already-present `pypdf` dependency as the fallback avoids adding a third PDF library to maintain
two conversion paths that could each drift independently. `pymupdf4llm`'s AGPL-3/commercial dual
license is accepted for this personal, never-distributed-as-a-service tool - a `requirements.txt`
reference does not relicense this repository, and Headless is not, and has no path to becoming,
a product anyone else runs (`CLAUDE.md`'s own scope statement).

**Alternatives considered**: `markitdown` (MIT, rejected for its heavier dependency footprint -
`requests`, `magika`, and others this codebase deliberately does not otherwise carry - for a
capability `pymupdf4llm` already provides more narrowly); `pdfplumber` (MIT, rejected because its
output is layout-ordered plain text, not Markdown - it would have fixed the column-scrambling
defect on its own, but would hand the local model a page with no heading or table structure to
lean on, which the real document's own multi-column declarations page benefits from); running
both `pymupdf4llm` and `pdfplumber` as two independent primary converters selected by document
shape (rejected as unnecessary complexity - one converter with a well-understood, already-present
fallback is simpler to reason about and test than two converters with their own selection logic).

## D3. The local-model seam: `headless/localllm.py`, injectable transport, localhost-only

**Decision**: a new module, `headless/localllm.py`, owns the local-model request/response
contract. It posts to `<HEADLESS_OLLAMA_URL>/api/generate` with the proven payload shape
(`"model"`, `"prompt"`, `"format": "json"`, `"stream": false`, `"think": false`,
`"options": {"temperature": 0}`); the model name comes from `HEADLESS_OLLAMA_MODEL` (default
`"qwen3.5:35b"`), the endpoint from `HEADLESS_OLLAMA_URL` (default
`"http://localhost:11434"`). The component that performs the HTTP call is an injectable callable,
so no unit test ever opens a real socket. The module refuses, at configuration-load time, any
`HEADLESS_OLLAMA_URL` whose host is not `localhost` or `127.0.0.1` - a value-free `ConfigError`,
raised before any conversion, extraction, or network call - so policy text can never leave the
Director's own machine. The call has a bounded timeout (default 120 seconds), one attempt, no
retry loop.

**Sub-decisions left open by the Director's own brief, resolved here**:

- **Module placement**: `headless/localllm.py`, a new module alongside `headless/policydoc.py`
  rather than folded into it - the same "thin package, one concern per module" pattern this
  codebase already follows for `headless/compare.py` (comparison) versus `headless/report.py`
  (rendering). `headless/policydoc.py` composes it; nothing else in `headless/` needs to know the
  local-model contract exists.
- **Configuration surface**: `ollama_model` and `ollama_url` become two new fields on the existing
  frozen `Config` dataclass (`headless/config.py`), resolved from `HEADLESS_OLLAMA_MODEL` and
  `HEADLESS_OLLAMA_URL` the same way `age_file` already is - validated once, at `load_config()`
  time, rather than deep inside the local-model call. This matches `age_file`'s own precedent
  exactly (an absolute-path rule enforced as a `ConfigError` at load time) and means the
  localhost-only refusal in FR-007 is provable with the same kind of test `test_config.py`
  already uses for every other `Config` field, rather than a new assertion shape specific to this
  one module.
- **HTTP client**: the standard library's `urllib.request`, not a new dependency such as
  `requests`. Every other Ollama or filesystem call anywhere in `headless/localllm.py` and
  `headless/policydoc.py` needs nothing beyond what this codebase already imports plus
  `pymupdf4llm`; adding an HTTP client dependency for one local POST call would be the same kind
  of unnecessary weight D2 already rejected `markitdown` for carrying.

**Rationale**: an injectable transport is this codebase's own established pattern for testing an
external call without ever making one (`AgeBackend`'s injected runner, `KeychainBackend`'s
`monkeypatch.setattr("headless.secrets.subprocess.run", ...)`, `extract_candidate`'s own
injectable `reader_factory`) - reusing it here rather than inventing a new mocking convention for
network calls keeps this feature's tests legible against the rest of the suite. Localhost-only
enforcement is the single load-bearing privacy property of this whole feature: everything else
(the sanity pass, the confirmation gate) protects against a wrong figure; this protects against
the Director's own policy data - his address, his coverage amounts, his premium - ever reaching a
network this machine does not control.

## D4. Constitutional recast of FR-051 (never an LLM -> local-only, confirm-gated, sanity-passed)

**Decision**: spec 005's own FR-051 ("Extraction MUST NOT call an LLM at any point") and the
constitution's own current hard-rule wording ("each insured asset's own `policy_doc` PDF is
extracted (deterministic heuristics, `pypdf`, never an LLM) and Director-confirmed") are both
recast, not simply extended. The new rule this feature establishes: no unconfirmed model output
ever becomes a figure; a model candidate is permitted only from a local model, only as input to
the existing confirmation gate, and only after the mechanical sanity pass (D5) has run against
it. The separate, older rule - "nothing an LLM derives is ever typed" (into a site, by an errand)
- is untouched; this feature does not change what a script may type, only what may be offered to
the Director for his own review before a human, not a script, decides what a `reports/policy/`
cache file will hold.

**Governance consequence**: this is a MINOR constitution bump (the current version is `1.3.1`),
not a wording-only PATCH, because a hard rule's own substance changes ("never an LLM" becomes
"only a local model, gated two ways"), the same class of change the age vault's own `1.2.1 ->
1.3.0` bump recorded when the default secrets backend changed. Actually amending `CLAUDE.md`'s
Secrets section and `.specify/memory/constitution.md`, with a Sync Impact Report line following
the existing convention in that file's own header comment, is implementation work for this
feature's own polish phase (tasks.md), not something this spec-authoring pass performs - the
draft wording for both documents is provided in `contracts/extraction-v2.md` and `tasks.md` so
the implementer has no open design question left to resolve.

**Verified compatible without change**: `tests/test_structural_grep.py`'s existing
`test_sc022_no_llm_or_ai_client_import_in_the_comparison_or_extraction_path` forbids the literal
tokens `openai`, `anthropic`, `genai`, `google.generativeai`, `langchain`, and `cohere` inside
`headless/compare.py`, `headless/policydoc.py`, and `scripts/policy_extract.py`. That test was
already scoped narrowly to cloud-provider client libraries, not to "no model of any kind" - a
local Ollama call made through the standard library's `urllib.request` (D3) introduces none of
those tokens into any of the three files it checks. Confirmed by reading the test directly
(`tests/test_structural_grep.py` lines 52-65): this feature requires no change to that test, and
its own continuing to pass unmodified is itself evidence the recast in this decision does not
reopen the door to a cloud model - only to a local one, still refused by a completely separate
mechanism (D3's `ConfigError`).

## D5. The mechanical sanity pass (the hallucination killer)

**Decision**: every figure string a candidate proposes - the premium amount, and each coverage
line's own limit, deductible, and premium - must appear literally in the converted source text
after normalizing both sides (strip currency symbols, commas, and whitespace; compare the
remaining digit sequences). Any proposed figure absent from the source is stripped from the
candidate and becomes a value-free warning ("a proposed `<field>` did not appear in the document
and was removed"), never the figure's own value and never a fragment of surrounding source text.
`term_months` is exempt from this literal-match rule only when it was derived by the deterministic
date-arithmetic helper (D8) from two policy-period dates found in the text - the derivation is our
own deterministic date arithmetic, not the model's claim, so there is nothing for a literal-match
check to verify against; when the model's own claimed term disagrees with our derivation, our
arithmetic wins, and the disagreement itself becomes a value-free note. Insurer name and coverage
line names are text, not figures - they are not subject to this check and continue to surface for
the Director's own eyes at the confirmation gate exactly as before.

**Rationale**: a local model removes the "the heuristic simply cannot see this pattern" failure
mode D1's own evidence documents, but introduces a different one - a model can produce a
plausible-looking figure that is not actually present anywhere in the source document. The
Director's own confirmation step (unchanged, D1) is the final safety net, but a hallucinated
figure that merely *looks* right is exactly the kind of error a human skimming a printed JSON
block is least likely to catch on his own; a mechanical, literal-presence check upstream of that
review is cheap to run, deterministic, and catches an entire class of error before it ever reaches
the Director's own attention. Running the same check against a regex-generated candidate too
(rather than only a model-generated one) costs nothing - a regex-derived figure is by construction
a substring of the source text it was matched from, so the check trivially passes for it, and the
pipeline gains one fewer conditional branch by applying it uniformly.

## D6. Fallback and degradation

**Decision**: any of - Ollama unreachable, the configured model missing, a non-JSON response, or
a response that does not match the expected candidate schema - collapses to one value-free note
plus automatic fallback to the v0.0.5 regex heuristics, which remain in the codebase unchanged as
the fallback generator. A converted-but-empty document continues to produce `None` (the same
"nothing to offer the Director" outcome v0.0.5 already defines for an unreadable PDF or a
zero-coverage-lines extraction). `scripts/policy_extract.py` gains a `--no-llm` flag that skips
the local-model attempt entirely, forcing every candidate through the regex-based generator; exit
codes are unchanged from v0.0.5 in every case.

**Rationale**: the same "degrade, do not refuse" discipline spec 005's own D15 already applied to
a PDF that fails to parse cleanly extends naturally to a local model that fails to respond
usefully - neither is a data-entry mistake worth a hard failure, both are ordinary outcomes of a
best-effort step against real-world conditions (an unstructured PDF; a model server that may or
may not be running on a given day) that should never block the Director from getting *some*
result for every eligible asset.

## D7. Provenance

**Decision**: the confirmed reference cached under `reports/policy/<asset-key>.json` gains two
new fields: which generator produced the confirmed candidate (`"regex-v1"` or
`"local-llm:<model-name>"`) and which converter produced the source text (the converter's own
name, or `"pypdf-raw"` on fallback). The comparison report's provenance footer passes both fields
through, alongside the `source_path` and `confirmed_at` fields it already surfaces.

**Rationale**: a Director inspecting a cached reference, or a report built from one, should always
be able to tell whether a given figure traces back to a deterministic regex match or a model's own
proposal - not because one is more trustworthy than the other after this feature's own gates run
(both pass through the same sanity pass and the same mandatory confirmation), but because
provenance is cheap to record and valuable the day a figure turns out to need a second look. This
is a minimal, additive field pass-through, not a report redesign - `headless/report.py`'s own
rendering logic changes only to display two more already-computed strings.

## D8. Term derivation

**Decision**: a new deterministic helper locates two dates, in common United States date formats,
appearing near a policy-period label in the converted text, and computes a term by calendar-month
arithmetic between them: a span of eleven to thirteen months yields `"12"`; a span of five to
seven months yields `"6"`; any other span yields the exact rounded month count as a string, with a
value-free warning that the term fell outside the two common terms. This helper is usable by both
the local-model generator and the regex-based generator - the annual-home-policy gap D1's own
evidence documents is a gap in v0.0.5's *regex* path just as much as it would be a gap in a naive
model-only path, and fixing it in one shared, tested function serves both.

**Rationale**: deriving a term from dates rather than reading a stated phrase is strictly more
general - every policy period this delivery is ever likely to see states its own start and end
date somewhere, while an explicit "N-month" phrase is, by the real evidence this feature was
scoped from, sometimes simply absent. Building this as a shared helper rather than duplicating the
date-finding logic inside each generator keeps the annual-term fix from silently regressing the
moment either generator's own code changes without the other.

## D9. Tests

**Decision**: every unit test in the default `pytest -q` run uses an injectable fake - a fake
converter, a fake local-model transport (a canned valid response, the empty-response case, a
malformed-JSON case, a schema-mismatch case), and a hand-constructed hallucinated-figure candidate
the sanity pass must strip. Zero real Ollama invocations, zero real network connections, and zero
real PDF file dependencies exist anywhere in that default run. A separate, opt-in integration
test, gated by `HEADLESS_TEST_OLLAMA=1`, runs the real local-model seam against the synthetic
scrambled snippet from this feature's own proof-of-concept and asserts schema validity only - not
exact values, since a real model's own wording is not guaranteed identical run to run. Whether the
scrambled-column fixture used by this suite is committed as a small binary fixture PDF
(`tests/fixtures/declarations-scrambled.pdf`, built once) or represented as a text fixture
standing in for the layout-aware converter's own output is left to the implementer - either
satisfies this decision, provided no fixture, in either form, contains a real value, name, policy
number, or premium.

**Rationale**: this mirrors v0.0.5's own testing discipline for `extract_candidate`
(`reader_factory` injection meant no real PDF asset was ever needed) exactly, extended to cover a
second external dependency (a local HTTP call) the same way. The opt-in integration test exists
because the proof this feature was scoped from is itself evidence a real model's behavior is worth
periodically re-verifying against - but gating it behind an explicit environment variable, rather
than running it by default, keeps the ordinary commit gate free of any dependency on Ollama being
installed and running on whatever machine runs `pytest -q` next, including CI.

## D10. Out of scope

**Decision**: this feature does not add OCR for an image-only PDF with no text layer; does not
add, or leave a code path toward, a cloud-hosted model of any kind, ever; does not permit
auto-accepting a candidate without the Director's own confirmation, at any confidence level; does
not register this feature's own local-model seam in this repository's separate
`local-llm-batch` parity-register process (which governs bulk, mechanically-validated jobs across
other personal tools - this feature's own seam has its own, stronger gate: the mechanical sanity
pass plus mandatory human confirmation on every single document, a stricter bar than that
process's own parity check); and does not change `headless/compare.py`'s comparison or ranking
logic, or `headless/report.py`'s rendering, beyond the provenance pass-through in D7.

**Rationale**: each of these is a deliberate boundary already implicit in the Director's own
framing of the feature (a reading-order and term-derivation fix, gated by confirmation) rather
than an invitation to redesign the comparison engine, the report, or this codebase's own
governance of bulk local-model jobs. Naming them here, rather than leaving them merely unmentioned,
gives the implementer and any later reviewer one place to check that a follow-up idea belongs in
its own future feature, not folded into this one.

## Alternatives considered (feature-level, not already covered under a specific D-number)

- **Regex-only tuning against the scrambled-column defect** (rejected): the observed artifact -
  labels and values interleaved and reversed relative to reading order - is not a shape any
  bounded set of regex alternations can reliably recover, because the information a regex would
  need (which digit run belongs to which label) has already been lost by the time `pypdf`'s own
  plain-text extraction hands back a string. This is why the real document already failed against
  v0.0.5 despite that delivery's own heuristics being deterministic and previously
  unit-tested clean; the fix has to happen upstream of regex matching, at the conversion step
  (D2), not inside it.
- **Cloud-hosted models of any kind** (rejected, permanently, not merely for this delivery): the
  Director's own real policy data - his address, his coverage amounts, his real premium - would
  leave his machine on every extraction run. No accuracy gain a cloud model might offer justifies
  that exposure for a personal tool whose entire secrets architecture (the `age` vault, the
  session-cookie mechanism, the vault-grade `reports/` classification) exists specifically to keep
  his data local. D3's localhost-only `ConfigError` makes this a structural refusal, not a policy
  statement alone.
