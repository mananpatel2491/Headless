# Contracts: Policy Extraction v2

**Feature**: 006-policy-extraction-v2 | **Date**: 2026-08-29

Six stable interfaces: the **local-model request/response contract**, the **sanity-pass rules**
(normative tables), the **fallback matrix**, the **`scripts/policy_extract.py` CLI delta**, the
**provenance strings**, and the **new environment variables**.

## 1. The local-model request/response contract

### Request

| Property | Value |
| :--- | :--- |
| Method | `POST` |
| URL | `<HEADLESS_OLLAMA_URL>/api/generate` |
| Body (JSON) | `{"model": "<HEADLESS_OLLAMA_MODEL>", "prompt": "<the converted text plus the extraction instruction>", "format": "json", "stream": false, "think": false, "options": {"temperature": 0}}` |
| Timeout | 120 seconds (default), one attempt, no retry |
| Transport | An injectable callable (`Callable[[dict], dict]` or equivalent) - production wires it to `urllib.request`; every test wires it to a fake |

**`"think": false` is mandatory, not advisory.** Omitting it causes `qwen3.5` to spend its entire
token budget on internal reasoning and return an empty `response` field instead of an error
(research.md, verified empirically). The request body MUST always include it explicitly; this
contract does not rely on any Ollama-side default remaining `false`.

### Response (Ollama's own envelope)

| Field | Type | Contract's own concern |
| :--- | :--- | :--- |
| `response` | `str` | The only field this contract reads. Must be non-empty and must parse as JSON matching the candidate schema (section below). Every other field in Ollama's own envelope (`done`, `total_duration`, and similar) is ignored. |

### The candidate schema `response` must decode to

```json
{
  "insurer": "string",
  "premium": {"term_months": "string", "amount": "string"},
  "coverages": [
    {"line": "string", "limit": "string", "deductible": "string", "premium": "string"}
  ]
}
```

Identical to `ExtractionCandidate`'s own existing shape (spec 005) - a response that decodes to
anything else (a missing top-level key, `premium` as a non-object, `coverages` as a non-array, an
array element missing `line`) is a schema mismatch, handled per the fallback matrix below, never a
partial construction.

### Failure classification (every non-success outcome collapses to "failed local-model attempt")

| Condition | Classification |
| :--- | :--- |
| Connection refused, DNS failure, or any transport-level exception | Failed attempt (FR-012) |
| HTTP status indicating the requested model is not installed | Failed attempt (FR-012) |
| Timeout exceeded (120 seconds default) | Failed attempt (FR-008, FR-013) |
| `response` field is empty or missing entirely | Failed attempt (FR-011) - this is the `"think"`-omitted gotcha's own failure shape, treated identically whether or not `"think": false` was actually sent, since a future model or Ollama version could reproduce it independently of that flag |
| `response` field is present but is not valid JSON | Failed attempt (FR-010) |
| `response` field parses as JSON but does not match the candidate schema above | Failed attempt (FR-010) |
| `response` field parses as JSON, matches the schema, and reaches this point | Success - proceed to the sanity pass (section 2) |

Every "failed attempt" row produces exactly one value-free note and triggers the fallback in
section 3 - never a partial candidate built from whatever the response did contain.

## 2. The mechanical sanity pass (normative)

Runs against every candidate, from either generator, before it reaches `confirm_candidate`
(FR-017 through FR-020, FR-026).

### Normalization (applied to both sides of every comparison below)

1. Remove every `$` character.
2. Remove every `,` character.
3. Remove every whitespace character.
4. What remains is the value's own digit sequence (a split limit such as `"100,000/300,000"`
   normalizes to two digit sequences, `"100000"` and `"300000"`, both checked independently).

### Figure-by-figure rule

| Figure | Subject to the literal-match check? | Exemption |
| :--- | :--- | :--- |
| `premium.amount` | Yes | None |
| Coverage line `limit` | Yes | None |
| Coverage line `deductible` | Yes | None |
| Coverage line `premium` | Yes | None |
| `premium.term_months` | Yes, unless derived by the date-arithmetic helper (section 2's own Term derivation subsection) from two in-text policy-period dates | Derived-from-dates case only |
| `insurer` | No - a text field | Always exempt (FR-028) |
| Coverage line `line` (its own name/slug) | No - a text field | Always exempt (FR-028) |

A figure that fails the check is set to the empty string on the candidate and one warning is
appended, in the exact shape: `"a proposed <field> did not appear in the document and was
removed"` - `<field>` names the figure only (`"premium amount"`, `"collision deductible"`, and
similarly for each other figure kind), never the value that was removed and never a quoted
fragment of the source text.

### Term derivation (shared helper, used by both generators)

| Rule | Behavior |
| :--- | :--- |
| Locate two dates in common United States formats near a policy-period label in the converted text | Regardless of which reads first in the text - a reversed order (the real document's own `"To:"` date preceding its `"From:"` date) is an expected input, not a parse error |
| Compute the calendar-month span between them | An integer |
| Span 11-13 months | `term_months = "12"`, no warning |
| Span 5-7 months | `term_months = "6"`, no warning |
| Any other span | `term_months = "<N>"` (the exact rounded count), warning: `"term derived as <N> months, outside the two common terms"` |
| Fewer than two dates found | The helper contributes nothing; `term_months` is whatever the generator itself proposed, still subject to the ordinary literal-match check above |
| The generator's own claimed `term_months` disagrees with this helper's own derived value (local-model generator only - the regex generator only calls the helper when its own phrase pattern found nothing to begin with) | The helper's value replaces the generator's claim; warning: `"term_months derived from policy-period dates overrode the model's own claim"` |

## 3. Fallback matrix

| Trigger | Effect |
| :--- | :--- |
| `--no-llm` passed on the command line | No local-model request is ever constructed for any asset in this run; every candidate comes from the regex-based generator (unchanged from v0.0.5) |
| Local-model request fails per section 1's own classification table | One value-free note (`"local model unavailable, fell back to the regex-based generator"`); the regex-based generator runs for this asset; the run continues to the next asset afterward regardless of outcome |
| Layout-aware converter unavailable (import failure) or its conversion call raises | One value-free note naming the fallback; extraction proceeds using `pypdf`'s own raw-text extraction (v0.0.5's existing path) as the source text for whichever generator runs next |
| Converted text (from either converter) is empty or missing | No candidate (`None`) for this asset - the same "nothing to offer the Director" outcome v0.0.5 already defines for an unreadable PDF |
| Regex-based generator (run either as the primary path under `--no-llm`, or as the fallback) itself finds zero coverage lines | No candidate (`None`) for this asset - unchanged from v0.0.5 |

No row above changes `scripts/policy_extract.py`'s own exit code: `0` on completion regardless of
how many assets were skipped, declined, or extracted with zero lines; `1` on a vault-level
refusal; `2` on a usage error (FR-016).

## 4. `scripts/policy_extract.py` CLI delta

| Property | v0.0.5 | v2 (this feature) |
| :--- | :--- | :--- |
| Usage | `python scripts/policy_extract.py [asset.path]` | `python scripts/policy_extract.py [asset.path] [--no-llm]` |
| `--no-llm` | n/a (flag did not exist) | Skips the local-model attempt entirely for every asset processed in this run (section 3); every other argument and behavior is unchanged |
| Positional `asset.path` | Restricts to one asset (e.g. `vehicles.primary`) | Unchanged |
| Exit codes | `0`/`1`/`2` per v0.0.5's own contract | Unchanged |
| Startup vault read | One passphrase prompt for the whole run | Unchanged |

## 5. Provenance strings (exact literals)

| Field | Possible values | Meaning |
| :--- | :--- | :--- |
| `PolicyReference.generator` | `"regex-v1"` | The confirmed candidate was produced entirely by the v0.0.5 regex-based heuristics (either because `--no-llm` was passed, or because the local-model attempt failed and the regex path served as the fallback) |
| `PolicyReference.generator` | `"local-llm:<model-name>"` | The confirmed candidate originated from a successful local-model response; `<model-name>` is the literal value of `HEADLESS_OLLAMA_MODEL` used for that request (for example `"local-llm:qwen3.5:35b"`) |
| `PolicyReference.converter` | The layout-aware converter's own package name | The source text came from the layout-aware conversion path |
| `PolicyReference.converter` | `"pypdf-raw"` | The source text came from the `pypdf` fallback path (the converter was unavailable, or its call raised) |

Both fields are plain strings with no further structure; a reader (the Director inspecting a
cache file, or the report's own footer) treats an absent field on an older, v0.0.5-written cache
file as "unknown," never as an error (data-model.md's own additive-only invariant).

## 6. New environment variables

| Variable | Default | Validated where | Rule |
| :--- | :--- | :--- | :--- |
| `HEADLESS_OLLAMA_MODEL` | `qwen3.5:35b` | `headless/config.py`, at `load_config()` time | Any non-empty string is accepted - this codebase does not maintain its own list of valid model names, since the set of models a Director might pull is not this feature's concern to enumerate |
| `HEADLESS_OLLAMA_URL` | `http://localhost:11434` | `headless/config.py`, at `load_config()` time | MUST resolve to a URL whose host is `localhost` or `127.0.0.1`; any other host raises a value-free `ConfigError` before any conversion, extraction, or network call happens (FR-007) |

Both variables follow the same resolution precedence every other `Config` field already uses in
this codebase: a CLI override (if `scripts/policy_extract.py` is ever given one in a future
delivery - none is added by this one), then the environment, then the documented default.
