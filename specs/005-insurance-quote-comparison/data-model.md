# Data Model: Insurance Quote Comparison

**Feature**: 005-insurance-quote-comparison | **Date**: 2026-08-25

No database. No new vault item: `companies` lives inside a new top-level `feature_configs.
insurance` object in the Director's existing `profile` document, read by direct JSON parse
(research.md D3, revised twice). There is no `current_policy` field anywhere in `profile` - each
insured asset carries its own `policy_doc` PDF path instead, turned into a confirmed reference by
`scripts/policy_extract.py` and cached under `reports/policy/` (research.md D15). One new resolver
rule inside `ProfileRegistry.get` (type-discriminated array addressing, research.md D13), two new
persisted-file families (`reports/captures/*.json`/`reports/quote-comparison-*.html`, and
`reports/policy/*.json`), five in-memory data shapes (`Step`'s four kinds, `QuoteCapture`,
`CurrentPolicy`, `ExtractionCandidate`, `ComparisonResult`), and one state-machine change
(`Errand.run()`'s dispatch loop, extended from `plan()` to `walk()`). Each is documented below, in
the order a single apply run touches them.

## Step: the walk's unit of work

`Step = FieldPlan | ClickStep | HumanStep | CaptureStep`. `FieldPlan` is unchanged from
`headless/fields.py` (spec 001). The three new kinds live in `headless/steps.py`:

| Type | Fields | Carries a `Source`? | Executable outside apply? |
| :--- | :--- | :--- | :--- |
| `FieldPlan` (existing) | `name: str`, `selector: str`, `source: Source`, `kind: str` | Yes | Preview resolves and records it (masked); check ignores it |
| `ClickStep` | `name: str`, `selector: str` | No | No - refuses with `GateRefused` outside apply, mirroring `Session.fill`'s existing guard |
| `HumanStep` | `name: str`, `instruction: str` | No | No - a handoff outside apply has nothing to hand off; not attempted in preview or check |
| `CaptureStep` | `name: str`, `extractors: dict[str, str]` (field key -> CSS selector) | No | No - preview never navigates far enough to reach a capturable page (SC-001) |

**Invariant - order is meaning**: a walk's steps execute strictly in the order `walk()` returns
them; there is no reordering, no parallel execution, no skipping a step because a later one looks
independent. This matches how a real multi-page form works - filling page 3's field before
clicking past page 2 is not meaningful.

**Invariant - no step type ever types outside the registry/vault/literal path**: `ClickStep` and
`HumanStep` carry no typed value at all. `CaptureStep` only reads. The only step kind that ever
writes a value into a page is `FieldPlan`, exactly as before this feature - the walk framework
adds new kinds of *interaction* (click, handoff, read), never a new way to *type*.

## Walk ordering and mode matrix

`Errand.walk(registry) -> list[Step]`. Default implementation: `return self.plan(registry)` -
every `FieldPlan` `plan()` already returns is automatically a valid one-element walk, so a
`plan()`-only errand needs no change at all.

| Mode | `FieldPlan` | `ClickStep` | `HumanStep` | `CaptureStep` |
| :--- | :--- | :--- | :--- | :--- |
| PREVIEW | Source resolved (pre-resolution loop, unchanged) and recorded masked in the preview JSON, exactly as today | Listed by name only (`{"kind": "click", "name": ...}`); never clicked | Listed by name only; never surfaced, never waited on | Listed by name only; never read |
| CHECK | Not touched; only `Errand.dependencies` is probed | Not touched | Not touched | Not touched |
| APPLY | `session.fill(field_plan, ...)`, unchanged | `session.click(step.selector)` | `session.handoff(step.instruction)` | `session.capture(step.extractors)`, result assembled and written (see QuoteCapture below) |

**Invariant - preview never navigates past the landing page**: in preview mode, the walk-execution
loop performs the errand's single initial `session.goto(self.url(args))` and nothing else - no
step's action executes. This is true regardless of how many `ClickStep`/`HumanStep`/`CaptureStep`
entries a walk declares (spec SC-001). A future insurer's walk can declare an arbitrarily deep
funnel; preview's behavior does not change with it.

**Invariant - check is walk-blind**: `--check` continues to probe only `Errand.dependencies` (a
flat list of selectors, unchanged shape from spec 001). It has no concept of "the walk's second
page" - a future insurer wanting `--check` coverage of a funnel page beyond the landing page would
need that selector added to `dependencies` directly, the same way every prior errand's `--check`
coverage already works. This feature does not extend `--check` to traverse a walk.

## `Errand.run()`: the state-machine delta

The existing state machine (`headless/errand.py`, spec 001): `load_config -> resolve_mode ->
open_vault -> plan(registry) -> pre-resolve every FieldPlan.source -> Session -> goto -> mode
branch -> PreviewRecord + write_artifacts -> stdout line -> exit code`.

This feature changes exactly two points in that sequence, both inside the existing `try` blocks
- no new exception class is added to `run()`'s own two catch-lists (pre-session and post-session),
because `ClickFailed` (below) is a `RuntimeError` subclass caught by the same `except
(FillFailed, ConfigError, GateRefused, SecretMissing, RegistryMissing)` post-session branch
`FillFailed` already falls into (it is added to that tuple; its message is engineered to be
value-free the same way `FillFailed`'s already is, so printing it is safe under the same rule):

```text
plan(registry) -> pre-resolve every FieldPlan.source                          [UNCHANGED CALL SHAPE]
    becomes
walk(registry) -> pre-resolve every FieldPlan.source found among walk()'s steps
    (ClickStep/HumanStep/CaptureStep entries are skipped by this loop entirely -
    they have no .source attribute to resolve)

mode branch:
  CHECK   -> probe(self.dependencies)                                          [UNCHANGED]
  PREVIEW -> for step in walk():
               if FieldPlan: resolve_source(...), append masked field record   [UNCHANGED for this case]
               else:         append {"kind": <click|human|capture>, "name": step.name}
                              to a new PreviewRecord.steps list
             (no navigation, no click, no handoff, no capture attempted)
  APPLY   -> for step in walk():
               if FieldPlan:    session.fill(step, vault, registry)            [UNCHANGED for this case]
               if ClickStep:    session.click(step.selector)
               if HumanStep:    session.handoff(step.instruction)
               if CaptureStep:  raw = session.capture(step.extractors)
                                 capture = capture.assemble_capture(
                                     insurer=self.name, source_url=session.page.url,
                                     fetched_at=<utc now>, raw_fields=raw)
                                 capture.write_capture(capture, reports_dir)
             session.handoff(self.HANDOFF)                                     [UNCHANGED - still
                                                                                  fires exactly once,
                                                                                  at the end]
```

**`PreviewRecord.steps`**: a new, additive field on `headless/preview.py`'s `PreviewRecord`
(default empty list, backward compatible with every existing preview JSON reader - the field is
additive, not a rename or a type change on an existing field). Holds only `{"kind": str, "name":
str}` entries for non-`FieldPlan` steps; never a selector, never an instruction string, never an
extractor mapping - consistent with `fields`'s own existing masking (a `FieldPlan`'s `selector` is
already recorded in cleartext today, since a selector is not the value being typed; a `HumanStep`'s
own `instruction` text is deliberately withheld from the preview artifact regardless, since an
instruction could describe what a page shows in enough detail to leak page content into a
persisted file - the safer default is name-only).

**Ordering guarantee**: within one apply run, no two steps execute concurrently - this codebase has
no concurrency inside one process for this seam, the same guarantee spec 004's data-model.md
already states for `AgeBackend`'s own state transition.

## `ClickFailed`

`headless/session.py`, alongside the existing `FillFailed`. Raised by `Session.click` when the
underlying Playwright locator action raises, for the same reason `FillFailed` exists: a raw
Playwright exception's call log can embed page content, so it is never allowed to propagate or be
printed directly.

| Field | Source |
| :--- | :--- |
| `step_name` | the `ClickStep.name` being executed |
| `selector` | the `ClickStep.selector` being executed |
| `cause_class` | `type(caught_exception).__name__` only, never the caught exception's own message |

Message shape: `f"click failed for {step_name!r} ({selector!r}): cause={cause_class}"` - no value
to redact (unlike `FillFailed`, a click has no typed value), so no `redact()` call is needed here.

## `Session.click` and `Session.capture`: new page operations

`Session.click(selector: str) -> None`: apply-mode only (raises `GateRefused` otherwise, matching
`Session.fill`'s existing guard verbatim); no retry on failure (matching `Session.fill`'s existing
"writes never retry" convention, unlike `goto`'s one retry for a transient navigation error);
wraps any Playwright locator-click exception into `ClickFailed`, never letting the raw exception
or its message propagate.

`Session.capture(extractors: dict[str, str]) -> dict[str, str]`: read-only, mirroring
`Session.probe`'s existing read-only shape (`probe(selectors) -> list[tuple[str, bool]]`). For each
`(field_key, selector)` pair: if `self.page.locator(selector).count() > 0`, the field's value is
that locator's extracted text (stripped); if the count is `0`, the field's value is `""` and
exactly one value-free note prints (`note: capture field '<field_key>' not found (selector
missing)`) - the loop continues to the next extractor regardless. `capture()` never raises for a
missing selector; it can only raise for something outside its own control (the page itself being
closed, a Playwright-internal failure unrelated to a specific selector), which `errand.py`'s
existing post-session generic `except Exception` branch already handles the same way it handles
any other unexpected browser-layer failure today.

## `ProfileRegistry.get`: type-discriminated array addressing (revised 2026-08-25)

`headless/profile.py`. New traversal rule, added to `ProfileRegistry.get`'s existing dotted-path
walk (spec 001) rather than to a new module - it extends the same method every `registry:` source
already calls, not a parallel resolver. General framework capability: not specific to insurance,
to Progressive, or to any one path.

```text
get(dotted):
  node = self._document
  for part in dotted.split("."):
    if isinstance(node, list):
      candidates = [el for el in node if isinstance(el, dict) and el.get("type") == part]
      if len(candidates) == 0:
        raise RegistryMissing(dotted)          # unchanged shape (FR-041)
      if len(candidates) > 1:
        raise RegistryAmbiguous(dotted)         # new (FR-042); value-free, path only
      node = candidates[0]
      continue                                  # traversal continues from the selected element
    if not isinstance(node, dict) or part not in node:
      raise RegistryMissing(dotted)             # unchanged (dict case, same as spec 001)
    node = node[part]
  if isinstance(node, (dict, list)):
    raise RegistryMissing(dotted)               # unchanged: a path fully consumed while still
                                                 # non-scalar still refuses (FR-044)
  return str(node)
```

**Invariant - a `type`-less element never matches**: an element of a list node with no `type` key
(`el.get("type")` returning `None`, which can never equal a real path segment string) is never a
match candidate for any segment - not an error, simply excluded from `candidates` (FR-043).

**Invariant - selection is total, not partial**: exact string equality only; there is no prefix,
case-insensitive, or fuzzy match. A segment either equals exactly one element's `type` field,
zero, or more than one - the trichotomy `RegistryMissing`/select/`RegistryAmbiguous` is exhaustive
(research.md D13).

**Invariant - unchanged behavior for the dict and scalar cases**: everything below the `if
isinstance(node, list)` branch is exactly spec 001's own original traversal, untouched by this
amendment. A `profile` document that never nests a `registry:` path through a list sees no
behavior change at all.

## `RegistryAmbiguous`

`headless/profile.py`, alongside the existing `RegistryMissing`. Raised when a dotted path's next
segment matches more than one list element's `type` field (FR-042).

```python
class RegistryAmbiguous(KeyError):
    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path

    def __str__(self) -> str:
        return f"registry path {self.path!r} matches more than one element by type"
```

Position-only message, mirroring `RegistryMissing`'s own shape exactly - never any matched
element's field content, since two elements sharing a `type` value could, in principle, differ in
every other field, and echoing either one's content back would leak whichever one happened to be
picked first. `Errand.run()`'s pre-session exception tuple (`headless/errand.py`) gains
`RegistryAmbiguous` alongside `ConfigError`/`GateRefused`/`SecretMissing`/`RegistryMissing`
(FR-045): `except (ConfigError, GateRefused, SecretMissing, RegistryMissing, RegistryAmbiguous) as
exc: print(f"REFUSED: {exc}")` - the same value-free-by-construction treatment every other
domain-shaped refusal in that tuple already receives, extended by exactly one class.

## `profile`'s own `feature_configs.insurance.companies` (revised a second time 2026-08-25)

Not a separate vault item (two earlier design proposals, both superseded - research.md D3,
revised twice). Lives inside the Director's existing `profile` document, under a top-level
`feature_configs` object, alongside the `identities`/`addresses`/`vehicles` arrays the section
above addresses. `scripts/quote_compare.py` reads it by parsing `profile`'s entire document
directly - `json.loads(vault.get_secret("profile"))` - and indexing the parsed `dict` with plain
Python, never through `ProfileRegistry.get` (which would refuse:
`feature_configs.insurance.companies` ends on a list with no further segment to select an element,
`RegistryMissing` per the section above's own unchanged-dict/list-ending rule).

**There is no `current_policy` field inside `feature_configs.insurance`, or anywhere in `profile`,
and none is ever planned** (spec FR-013, research.md D3's second revision, D15). See the
"Per-asset `policy_doc` extraction and confirmation" section below for what replaced it.

### `insurance.companies`

`headless/capture.py`. `parse_companies(raw_json_fragment: object) -> list[str]` (taking the
already-parsed `profile["feature_configs"]["insurance"]["companies"]` value) raises
`QuoteInputError` (see below) when the fragment is missing, not a JSON array, or contains any
non-string entry - `feature_configs` or `feature_configs.insurance` being absent from `profile`
raises the same error one level up, naming whichever piece is missing. A valid, empty array (`[]`)
is not an error - it means the Director has not yet listed any insurer to compare, and the
orchestrator's report renders with zero insurer rows plus whatever current-policy column state
applies, the same way a freshly initialized, empty vault's `list` command prints zero lines
without it being an error (spec 004's own precedent for "empty is a valid, unremarkable state").

### `QuoteInputError`

`headless/capture.py`, a `ValueError` subclass, position-only message - the same shape
`ProfileError` (`headless/profile.py`, spec 001) already established for `profile`'s own
malformed-JSON case, reused here for `profile`'s well-formed-JSON-but-wrong-shape
`feature_configs.insurance` sub-object rather than for `profile`'s own top-level JSON validity (a
`profile` value that is not valid JSON at all is still `ProfileError`'s own concern, raised before
`quote_compare.py`'s own parsing of `feature_configs.insurance` is ever reached). `scripts/
quote_compare.py` (not an `Errand` subclass) catches both `ProfileError` and `QuoteInputError`
directly at its own top level, before constructing any insurer's `Errand` subclass, printing
`REFUSED: {exc}` and exiting `1` - mirroring `errand.py`'s own `REFUSED:` convention for a
pre-session, value-free refusal rather than inventing a second print format.

## Per-asset `policy_doc` extraction and confirmation (added 2026-08-25, research.md D15)

`current_policy` is not hand-typed; it is derived, per insured asset, from that asset's own
`policy_doc` PDF, deterministically extracted and then Director-confirmed before it can ever be
compared against. Three new shapes and one file family, in `headless/policydoc.py`.

### `CurrentPolicy`

`headless/capture.py`. The confirmed current-policy reference shape - unchanged from this spec's
own original design, and now the shape both `ExtractionCandidate` (below) and the
`reports/policy/` cache file are built on.

| Field | Type | Rules |
| :--- | :--- | :--- |
| `insurer` | `str` | the current insurer's name, free text - read straight from the PDF's own extraction, or from the Director's own correction |
| `premium` | `dict` with `term_months: str`, `amount: str` | both required; string-typed (matching how every other typed value in this codebase is a string, e.g. `ProfileRegistry.get`'s own return type) rather than numeric, so a captured page's own text (which is always a string) and this reference's own value compare and normalize through the same code path with no numeric-parsing special case for one side only |
| `coverages` | `list[dict]`, each with `line: str`, `limit: str`, `deductible: str` (may be empty string), `premium: str` (may be empty string) | `line` and `limit` are required per entry; `deductible`/`premium` may be absent or empty (not every coverage line prices separately from the policy's overall premium) |

### `ExtractionCandidate`

The raw output of `extract_candidate(pdf_path: Path) -> ExtractionCandidate | None`. Shaped
identically to `CurrentPolicy` (`insurer`, `premium`, `coverages` - spec FR-052) plus one
additional field, `warnings: list[str]` (value-free notes about what the heuristics could not
confidently parse - never page text itself, only a structural note like `"no term detected"`).
Returns `None` (not an exception) when the PDF cannot be read at all, or when zero coverage lines
were parsed - both are the same "nothing to offer the Director" outcome data-model.md's own
`write_capture`-style optional-return convention already uses elsewhere in this document.
**An `ExtractionCandidate` is never itself a `CurrentPolicy`** - the type distinction exists
specifically so nothing can accidentally pass an unconfirmed candidate to `compare.
build_comparison`, which only ever accepts `CurrentPolicy | None` (see `ComparisonResult` below).

### Confirmation

`confirm_candidate(candidate: ExtractionCandidate, *, input_fn=input) -> CurrentPolicy | None`.
Prints the candidate (the deliberate, sole print-a-value exception this mechanism shares with
`vault.py get`, spec FR-053) and prompts, via the injectable `input_fn` (so tests never touch a
real terminal): accept as printed, or paste a corrected JSON document at a follow-up plain-text
prompt (not hidden - the same content was already shown moments before). Returns the confirmed
`CurrentPolicy` on either accept or a valid correction; returns `None` on decline or an
uncorrectable input - in every `None` case, no cache write follows (spec FR-054, FR-055).

### `PolicyReference` and the cache file

| Field | Type | Rules |
| :--- | :--- | :--- |
| every `CurrentPolicy` field | (embedded) | unchanged, embedded whole |
| `source_path` | `str` | the `policy_doc` path extraction ran against |
| `confirmed_at` | `str` (ISO 8601, UTC) | when `confirm_candidate` returned non-`None`, passed in by the caller, not computed inside `policydoc.py` itself (same "one place asks what time it is" convention `QuoteCapture.fetched_at` already established) |

`write_policy_reference(reference, reports_dir) -> Path`: writes
`reports_dir/policy/<asset-key>.json`, mode `0600` where the platform supports it (a no-op on
Windows, the same documented residual `scripts/vault.py`'s own `_encrypt_document` already
accepts). `<asset-key>` is derived from the asset's own array name and `type`, dots replaced with
hyphens: `vehicles.primary` becomes `vehicles-primary`. Whole-file replace on every write - unlike
`reports/captures/`, which accumulates, a policy reference has exactly one current value per
asset, the same single-current-value shape the vault file and `session-cookies.json` already use.

`read_policy_reference(asset_key, reports_dir) -> CurrentPolicy | None`: reads and parses the one
file for that key; `None` when it does not exist or fails to parse (spec FR-058) - a malformed
cache is treated exactly like a missing one, never a hard refusal, since a machine-written,
already-once-confirmed file degrading is a different trust situation from a Director-hand-typed
value failing validation (research.md D15's own rationale for this asymmetry).

### The `"n/a"` sentinel

`is_excluded(asset: dict) -> bool`: `True` when `asset.get("currently_insured") == "n/a"` or
`asset.get("policy_doc") == "n/a"` (spec FR-061). Checked by `scripts/policy_extract.py` before
attempting extraction for any asset (skipped silently, FR-062) and by `scripts/quote_compare.py`
before constructing any insurer's `Errand` for the targeted asset (FR-060, FR-063) - one function,
two callers, so the sentinel's own meaning is defined in exactly one place.

## `QuoteCapture`

`headless/capture.py`. The structured record one insurer's successful `CaptureStep` produces.

| Field | Type | Rules |
| :--- | :--- | :--- |
| `insurer` | `str` | the insurer id (matches a `feature_configs.insurance.companies` entry and a `WALK_REGISTRY` key, e.g. `"progressive"`) |
| `fetched_at` | `str` (ISO 8601, UTC) | passed in by the caller at capture time (`datetime.now(timezone.utc).isoformat()`), not computed inside `capture.py` itself - keeps the module free of a hidden `datetime.now()` call, matching `headless/preview.py`'s own `_utc_timestamp()` convention of being the one place "now" is asked for |
| `premium` | `dict` with `term_months: str`, `amount: str` | same shape as `CurrentPolicy.premium`, so both sides of a comparison share one shape |
| `coverages` | `list[dict]`, same shape as `CurrentPolicy.coverages` | an entry with `limit == ""` (extractor did not resolve) is a missing line, not an absent one - it still appears in the list, so the report can show *which* line was attempted and not found, rather than silently having fewer rows than expected |
| `source_url` | `str` | `session.page.url` at the moment the `CaptureStep` executed - the quote page's own URL, for the report's provenance footer |

**Invariant - `assemble_capture`'s field-key grammar**: `assemble_capture(insurer, source_url,
fetched_at, raw_fields: dict[str, str]) -> QuoteCapture` parses `raw_fields` (the flat mapping
`Session.capture()` returns) using a fixed, small vocabulary of dotted field keys:
`"premium.amount"`, `"premium.term_months"`, and `"coverage.<line-slug>.limit"` /
`"coverage.<line-slug>.deductible"` / `"coverage.<line-slug>.premium"`, where `<line-slug>` is a
stable, hand-chosen identifier the insurer's own walk module picks (e.g. `bodily_injury`,
`property_damage`, `collision`) - **not** the raw text a page displays for that line, since raw
page text is exactly what D5/D10's alias table exists to normalize downstream, one layer up, when
comparing against `current_policy`'s own free-text `line` names. A `raw_fields` key outside this
vocabulary is ignored (forward-compatible: a future insurer's walk can capture extra diagnostic
fields without `assemble_capture` needing to change first). A vocabulary key present in
`extractors` but absent from `raw_fields` (should not happen, since `Session.capture` always
returns an entry, empty string or not, for every extractor key it was given) is treated the same
as an empty-string value - `assemble_capture` never raises for a shape `Session.capture()` itself
cannot produce.

## `write_capture` / freshest-capture read

`write_capture(capture: QuoteCapture, reports_dir: Path) -> Path`: writes
`reports_dir/captures/<insurer>-<fetched_at, filesystem-safe>.json`, creating `captures/` if
needed. Captures accumulate - this call never overwrites or deletes an earlier capture for the
same insurer, unlike the vault file or `session-cookies.json`'s own whole-file-replace pattern;
each capture is its own immutable, timestamped file (closer to how `previews/`'s own
`<errand>-<timestamp>.json` files already accumulate one per run).

`read_freshest_capture(insurer: str, reports_dir: Path) -> QuoteCapture | None`: globs
`reports_dir/captures/<insurer>-*.json`, sorts by the timestamp embedded in the filename (not
filesystem mtime, which a copy or a backup tool could disturb), and parses the newest one. Returns
`None` when no capture file exists yet for that insurer - the caller (the comparison engine's
orchestration point, `scripts/quote_compare.py`) treats `None` as "capture failed / no data yet"
(spec FR-024), never as an error.

## `ComparisonResult`

`headless/compare.py`. Pure output of `build_comparison(current_policy: CurrentPolicy | None,
captures: dict[str, QuoteCapture]) -> ComparisonResult` - no file I/O, no vault access, no
browser; every input is already an in-memory, parsed object. `current_policy` is `None` exactly
when no confirmed current-policy reference existed for the targeted asset (data-model.md's own `CurrentPolicy`
section, FR-013) - a normal, non-error input, not a sentinel the caller has to special-case around
this function's boundary.

| Field | Type | Rules |
| :--- | :--- | :--- |
| `ranked_quotes` | `list[RankedQuote]` | ordered best-to-worst per FR-016's rule when `current_policy` is present, or by monthly-equivalent premium alone per FR-046 when it is `None`; empty when `captures` is empty |
| `recommended` | `RankedQuote \| None` | `ranked_quotes[0]` when non-empty, else `None` (no captures to recommend from - not an error, see the Edge Cases in spec.md) |
| `rule_trail` | `str` | a short, deterministic sentence built only from `recommended`'s own comparison data (spec FR-017, or FR-046's "no current policy on file" variant); empty string when `recommended is None` |
| `has_current_policy` | `bool` | `current_policy is not None` at the time this result was built - the report generator reads this one flag rather than re-deriving it, so `render_report`'s own logic for FR-047's marker never has to guess from `ranked_quotes`' own shape |

`RankedQuote` (nested): `insurer: str`, `capture: QuoteCapture`, `line_classifications: dict[str,
str]` (normalized coverage-line key -> one of `"better"`, `"equal"`, `"worse"`, `"missing"` when
`current_policy` is present; an **empty dict** when it is `None` - FR-046 computes no
classification at all in that case, rather than populating every key with a placeholder value),
`normalized_premium: str` (the captured premium, expressed at `current_policy`'s own term length
when one exists, or as a monthly-equivalent figure per FR-046 when it does not, for the ranking
comparison and the report's premium row).

**Invariant - determinism**: given the same `current_policy` (or `None`) and the same `captures`
mapping, `build_comparison` MUST return byte-identical `ranked_quotes` ordering and `rule_trail`
text, every time, on every run - no randomness, no wall-clock dependency (the wall clock only ever
appears inside a `QuoteCapture.fetched_at` value the caller already supplied, never read fresh
inside `compare.py` itself), no dictionary-iteration-order dependency (`captures`' keys are always
sorted before iteration, so Python's own dict-ordering-is-insertion-order behavior is never
silently relied upon to produce a stable result).

## Report input contract

`headless/report.py`'s `render_report(comparison: ComparisonResult, unmapped: list[str], failed:
list[str]) -> str`. Every argument is already fully resolved, in-memory data - `render_report`
itself performs no file I/O, no vault access, and constructs no browser. `unmapped` is the list of
`feature_configs.insurance.companies` entries with no `WALK_REGISTRY` key; `failed` is the list of mapped insurers
whose `read_freshest_capture` returned `None` this run (spec FR-024). An insurer id cannot appear
in more than one of `comparison.ranked_quotes`, `unmapped`, or `failed` in the same render call -
the orchestrator (`scripts/quote_compare.py`) is responsible for partitioning
`feature_configs.insurance.companies` into exactly these three buckets before calling `render_report`, so
`report.py` itself never has to resolve that ambiguity. `render_report` reads
`comparison.has_current_policy` to decide whether to render real current-policy values or FR-047's
"no current policy on file" marker - it never re-derives that fact from `ranked_quotes`' own
shape.

`write_report(html: str, reports_dir: Path) -> Path`: writes `reports_dir/quote-comparison-
<date, YYYY-MM-DD, UTC>.html`, overwriting any existing report from the same UTC date (unlike
captures, which accumulate - a report is a point-in-time snapshot of "the comparison as of the
last apply run today," not a history).
