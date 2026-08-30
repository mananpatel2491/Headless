# Implementation Plan: Policy Extraction v2

**Branch**: `v0.0.6` | **Date**: 2026-08-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-policy-extraction-v2/spec.md`

## Summary

Replace v0.0.5's regex-only candidate generation inside `scripts/policy_extract.py` with a
layout-aware PDF-to-Markdown conversion (`pymupdf4llm`, new hard dependency) followed by a local
(never cloud) Ollama model that proposes a candidate from the converted text, gated by a new
mechanical sanity pass that strips any figure absent from the source document. The v0.0.5 regex
heuristics remain in the codebase, unchanged, as the automatic fallback generator whenever the
local model is unavailable, unreachable, or produces an unusable response, and as the forced path
under a new `--no-llm` flag. The existing mandatory Director confirmation gate, the
`reports/policy/` cache, and `scripts/quote_compare.py`'s own consumption of a confirmed
reference are all untouched except for two additive provenance fields (which generator, which
converter). Decisions are recorded in [research.md](research.md) (D1-D10).

## Technical Context

**Language/Version**: Python 3.14 (this worktree's own `.venv`, unchanged from every prior
feature in this repository)

**Primary Dependencies**: `pymupdf4llm` (new, `requirements.txt`, an ordinary entry rather than a
separate optional-extras file - research.md D2). No new dependency for the local-model HTTP call
itself: the standard library's `urllib.request` serves that one POST call, the same "no dependency
this feature does not strictly need" discipline `scan_secrets.py` already established for this
repository (research.md D3).

**Storage**: no new persisted directory. `reports/policy/<asset-key>.json` (spec 005, unchanged
location and write discipline) gains two additive string fields (`generator`, `converter`).

**Testing**: `pytest>=8` (already a dependency). Every new external dependency this feature
introduces - the layout-aware converter and the local-model HTTP call - is exercised through an
injectable fake in the default suite (spec NFR-001); a separate, opt-in integration test gated by
`HEADLESS_TEST_OLLAMA=1` is the only test permitted to reach a real local model (spec NFR-002).

**Target Platform**: macOS (this Director's own machine, unchanged), but nothing in this feature
is platform-specific - `urllib.request` and `pymupdf4llm` are both cross-platform, and Ollama
itself ships for macOS, Windows, and Linux.

**Project Type**: package change (`headless/policydoc.py` modified; `headless/localllm.py` new;
`headless/config.py` modified) plus one CLI flag added to an existing maintenance-adjacent script
(`scripts/policy_extract.py`). No new errand, no new browser surface. Single project, same
structure every prior feature in this repository uses.

**Performance Goals**: not a latency-sensitive path - a Director-run extraction happens once per
asset, and the proven local-model round trip (3.3 seconds against a synthetic snippet,
research.md) is well inside the 120-second timeout this feature sets as a safety bound, not a
target to optimize toward. The unit suite covering the new module and the extended one must still
run in comparable time to v0.0.5's own equivalent addition (spec NFR-004), since nothing in the
default suite touches a real network, process, or filesystem PDF.

**Constraints**: no policy document text, converted text, or candidate content may ever reach a
network endpoint other than the local one FR-007 enforces (this is a structural `ConfigError`,
not a policy statement alone); no candidate may reach the cache or the comparison engine without
passing the unchanged confirmation gate; `scripts/policy_extract.py`'s exit codes are unchanged
from v0.0.5 in every case.

**Scale/Scope**: unchanged from v0.0.5 - one Director, per-asset one-shot extraction, no
concurrency, no batching.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

This feature **deliberately amends** one existing hard rule rather than only adding a new one, so
this gate records the amendment explicitly rather than treating it as a pass-through.

| Principle / Hard Rule | Status | Notes |
| :--- | :--- | :--- |
| I. Context-First Architecture Map | Pass (planned) | `Project_Structure.md` gains rows for `headless/localllm.py` (new) and updated descriptions for `headless/policydoc.py`, `headless/config.py`, `scripts/policy_extract.py`, `requirements.txt` - a `tasks.md` polish-phase task, not yet applied by this spec-authoring pass |
| II. Pattern Reference Integrity | Pass (planned) | `PATTERNS.md` gains one new entry ("Local-model extraction with a mechanical figure gate") documenting the pipeline, the sanity pass, and the fallback matrix - a `tasks.md` task |
| III. Automated Maintenance via Agentic Skills | Pass | `scripts/policy_extract.py` remains `argparse`-based, preview-adjacent in spirit (it never writes a cache entry without the Director's own confirmation), cross-platform |
| IV. Continuous Errand Validation | Pass | Every new code path (conversion fallback, local-model failure classification, the sanity pass, term derivation) gets unit tests before implementation, per `tasks.md`'s own tests-first ordering; `pytest -q`, `verify_structure.py`, and `scan_secrets.py --staged` continue to gate every commit unchanged |
| V. Infrastructure-as-Code and Cost Gating | Pass, trivially | No cloud resource of any kind - Ollama runs entirely on the Director's own machine, at $0/month, the same as every other local tool in this repository |
| **Secrets Hard Rule: "each insured asset's own `policy_doc` PDF is extracted (deterministic heuristics, `pypdf`, never an LLM) and Director-confirmed"** | **AMENDED (this feature's own purpose)** | This exact clause is what `spec.md` FR-004 through FR-029 and research.md D4 recast. The new rule: extraction may attempt a **local-only** model, but no candidate - from either generator - ever reaches the cache or the comparison engine without passing the mechanical sanity pass (FR-017 through FR-020) and the unchanged, mandatory confirmation gate (FR-025, FR-026). See "Constitutional amendment" below for the exact drafted replacement wording and the version-bump call. |
| **Registry Hard Rule: "a script may type a value only if it exists in the profile registry... LLM-derived values are structurally unwritable"** | Unaffected | This feature changes what may be *offered to the Director for review*, never what an errand may *type into a site*. FR-027 restates this explicitly; no wording change to this hard rule is needed. |

### Constitutional amendment (drafted here, applied during implementation)

**Version-bump call**: MINOR, `1.3.1 -> 1.4.0` - a hard rule's own substance changes (a flat
"never an LLM" becomes "a local model only, gated two ways"), the same class of change the age
vault's own `1.2.1 -> 1.3.0` bump recorded when the default secrets backend changed (not a
wording-only PATCH, since a PATCH by this file's own convention extends an existing rule's reach
without redefining it).

**Sync Impact Report line to add to `.specify/memory/constitution.md`'s own header comment**
(matching that file's existing convention exactly):

```text
- 1.3.1 -> 1.4.0 (MINOR: an existing hard rule is redefined, not merely extended - the first
  time this constitution has recast a rule rather than only adding to or clarifying one): policy
  extraction v2 (specs/006-policy-extraction-v2). The flat "never an LLM" clause inside the
  Secrets Hard Rules bullet is replaced: extraction may attempt a local-only model (never a
  cloud one, structurally refused by a value-free ConfigError on any non-localhost endpoint), but
  no candidate - regardless of which generator produced it - ever reaches the reports/policy/
  cache or the comparison engine without first passing a new mechanical sanity pass (every
  proposed figure must appear literally in the converted source document, or it is stripped) and
  the pre-existing, unchanged, mandatory Director confirmation step. The older, separate rule -
  nothing an LLM derives is ever typed into a site - is untouched. Templates unchanged.
```

**Drafted replacement text for `CLAUDE.md`'s Secrets section** (the sentence beginning "each
insured asset carries its own `policy_doc` field... `scripts/policy_extract.py` turns it into a
confirmed reference via deterministic heuristics (`pypdf`, never an LLM)"):

```text
...each insured asset carries its own `policy_doc` field, a filesystem path to that asset's real
policy PDF; `scripts/policy_extract.py` (v0.0.6) turns it into a confirmed reference via a
layout-aware conversion and a local-only model (never a cloud one - a value-free `ConfigError`
refuses any non-localhost `HEADLESS_OLLAMA_URL`), falling back automatically to the v0.0.5 regex
heuristics whenever the local model is unavailable. No candidate from either generator reaches
the cache without first passing a mechanical check that strips any figure absent from the
converted document, and mandatory Director confirmation, cached under
`reports/policy/<asset-key>.json`.
```

Both drafts are provided so the implementer has no open wording decision left; applying them (and
updating `PATTERNS.md`, `Project_Structure.md`, `scripts/README.md`, `MEMORY.md`) is a `tasks.md`
polish-phase task, not performed by this spec-authoring pass.

### Verified compatible without change

`tests/test_structural_grep.py`'s existing `test_sc022_no_llm_or_ai_client_import_in_the_
comparison_or_extraction_path` forbids the tokens `openai`, `anthropic`, `genai`,
`google.generativeai`, `langchain`, `cohere` inside `headless/compare.py`, `headless/policydoc.py`,
and `scripts/policy_extract.py`. Confirmed by reading the test directly: it targets specific
cloud-provider client libraries, not "any model of any kind," and the local Ollama call this
feature adds (via `urllib.request`, to a `localhost`-only endpoint) introduces none of those
tokens into any of the three files it checks. **This test requires no modification** and continues
to pass unmodified - its own continued passing is itself evidence this feature's recast does not
reopen a path to a cloud model, which remains blocked by the entirely separate `ConfigError`
mechanism in `headless/config.py`.

## Project Structure

### Documentation (this feature)

```text
specs/006-policy-extraction-v2/
├── plan.md              # This file
├── research.md          # D1-D10, evidence
├── data-model.md         # Candidate pipeline states, ConvertedDocument, term derivation, PolicyReference extension
├── contracts/
│   └── extraction-v2.md  # Ollama request/response contract, sanity-pass tables, fallback matrix, CLI delta, provenance, env vars
├── quickstart.md          # Director re-UAT scenarios
├── tasks.md               # Tests-first task breakdown
└── checklists/
    └── requirements.md    # Specification quality checklist
```

### Source code (repository root)

```text
headless/
├── policydoc.py          # MODIFIED: extraction becomes a dispatch (local-model generator, regex
│                          # generator on fallback) plus the new sanity pass and term-derivation
│                          # helper; ExtractionCandidate/confirm_candidate/PolicyReference/
│                          # write_policy_reference/read_policy_reference untouched except
│                          # PolicyReference's two new provenance fields
├── localllm.py            # NEW: the Ollama request/response contract, the injectable transport
│                          # seam, the localhost-only enforcement's own call site
├── config.py               # MODIFIED: two new Config fields (ollama_model, ollama_url) and the
│                          # localhost-only ConfigError validation
└── report.py               # MODIFIED (minimal): provenance footer gains the two new fields

scripts/
└── policy_extract.py     # MODIFIED: --no-llm flag; wiring to the new dispatch

requirements.txt          # MODIFIED: + pymupdf4llm

tests/
├── test_localllm.py                # NEW: request construction, every failure classification,
│                                    # the localhost-only refusal, the think-false requirement
├── test_policydoc.py                 # MODIFIED: dispatch, sanity pass, term derivation
├── test_policy_extract.py             # MODIFIED: --no-llm flag, provenance in the cached file
├── test_config.py                      # MODIFIED: ollama_model/ollama_url resolution and refusal
├── test_report.py                       # MODIFIED: provenance footer fields
├── test_structural_grep.py                # UNCHANGED (verified compatible, see Constitution
│                                          # Check above) - no task needed
└── fixtures/
    └── (a scrambled-column, no-explicit-term synthetic fixture - text or a small built-once PDF;
       implementer's choice per research.md D9)

CLAUDE.md, PATTERNS.md, Project_Structure.md, scripts/README.md, MEMORY.md,
.specify/memory/constitution.md, .env.example    # MODIFIED: docs of record (tasks.md polish phase)
```

**Structure Decision**: single project, same layout every prior feature in this repository uses.
No new top-level directory; `headless/localllm.py` is the only new source module.

## Complexity Tracking

> Filled because the Constitution Check above records a hard-rule amendment, not a pure addition.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| :--- | :--- | :--- |
| Recasting the Secrets Hard Rule's "never an LLM" clause, rather than adding a new rule alongside it | The old and new rules are mutually exclusive on the exact question of whether extraction may ever attempt a model - a new rule cannot coexist with the old one without contradiction, so the old clause has to be replaced, not supplemented (research.md D4) | Leaving the old rule in place and treating the local-model path as an undocumented exception was rejected: the whole reason this repository records hard rules in `CLAUDE.md` is so a rule's own current, true shape is never something a session has to reconstruct from feature history - an unrecorded exception to a still-published "never" rule is exactly the kind of drift `PATTERNS.md`'s own Principle II exists to prevent |
