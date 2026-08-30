# Quickstart: Policy Extraction v2

**Feature**: 006-policy-extraction-v2 | **Date**: 2026-08-29

Runnable validation scenarios that prove the feature end-to-end, once implemented. Contracts are
in [contracts/extraction-v2.md](contracts/extraction-v2.md); entities in
[data-model.md](data-model.md).

**Scenarios 1 through 3 below run against the Director's own real PDF and his own real Ollama
installation. This is Director-run UAT, not something a builder or an automated agent executes on
his behalf - his real declarations page, his real coverage figures, and his real premium are never
to be pasted into a session transcript, a commit, a test fixture, or this document. Every value
below is a placeholder for what he will actually see.**

## Prerequisites

- From the worktree root, the existing `.venv`, with the new dependency installed:
  ```bash
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- Ollama installed and running, with the configured model pulled:
  ```bash
  ollama list          # confirm qwen3.5:35b (or your own HEADLESS_OLLAMA_MODEL) is present
  ollama serve         # if not already running
  ```
- The Director's own `profile` vault item already has a real `policy_doc` path set on the asset
  he wants to re-extract (unchanged from v0.0.5 - `vault.py get profile`, edit, `vault.py set
  profile`, if this is not already the case).

## Scenario 1: re-running extraction against the real declarations PDF, with Ollama running (US1)

```bash
python scripts/policy_extract.py vehicles.primary
```

Expected: one passphrase prompt (the same single prompt v0.0.5 already required), then, for the
targeted asset:

1. A value-free note naming which converter served the run (the layout-aware converter, ordinarily
   - never `"pypdf-raw"` unless the converter itself is missing or failed).
2. The same "Extracted current-policy candidate (your own data, printed for your review)" header
   v0.0.5 already prints, followed by the candidate's own JSON - his real insurer name, his real
   premium, his real coverage lines, exactly as before. What changed is how that JSON was
   produced, not how it is shown to him.
3. If his real declarations page has no explicit "N-month" phrase (the annual-policy gap this
   feature exists to close), `premium.term_months` should already read the correct term, derived
   from his own policy-period dates - this is the concrete thing to check against his own real
   policy, since it is exactly the figure v0.0.5 could never have produced correctly for an annual
   policy.
4. The same "Accept as printed, correct it, or decline? [a/c/d]:" prompt v0.0.5 already offers.

His own review at step 4 is unchanged and remains the final word - if anything in the printed
candidate looks wrong, correcting it by hand (option `c`) works exactly as it always has.

## Scenario 2: inspecting the cached reference's new provenance fields (US1, US2)

After accepting a candidate in Scenario 1:

```bash
cat reports/policy/vehicles-primary.json
```

Expected: the same `insurer`/`premium`/`coverages`/`source_path`/`confirmed_at` fields v0.0.5
already wrote, plus two new fields:

```json
{
  "generator": "local-llm:qwen3.5:35b",
  "converter": "pymupdf4llm"
}
```

(Exact converter name depends on which package this feature's own implementation names as the
layout-aware converter, per `contracts/extraction-v2.md` section 5 - `pymupdf4llm` is the one
named throughout `research.md` and `plan.md`.) If Ollama had been unreachable for this run
instead, `generator` would read `"regex-v1"` and one value-free fallback note would have printed
before the candidate.

## Scenario 3: the `--no-llm` fallback check (US3)

```bash
python scripts/policy_extract.py vehicles.primary --no-llm
```

Expected: no note about a local model at all - the run behaves exactly as v0.0.5 always did, using
only the regex-based heuristics. Compare the resulting candidate against Scenario 1's own
local-model-generated candidate: any difference between the two is worth a closer look (it is
exactly the kind of gap this feature exists to close), but neither run should ever crash, and the
cached reference's own `generator` field should read `"regex-v1"` after this run.

## Scenario 4: Ollama not running (US3)

```bash
# with `ollama serve` stopped
python scripts/policy_extract.py vehicles.primary
```

Expected: one value-free note ("local model unavailable, fell back to the regex-based
generator"), then the same regex-based candidate Scenario 3 would have produced, then the same
confirmation prompt. The run completes with exit code `0`, the same as v0.0.5 already guarantees
for this asset regardless of how the candidate was produced.

## Scenario 5: confirming his real values never enter the repository

At no point in Scenarios 1 through 4 does anything the Director sees get written anywhere inside
this repository's own tracked tree:

- The candidate JSON is printed to his terminal only (the same documented, sole-purpose exception
  to this codebase's value-free-output convention v0.0.5 already established).
- The cached reference lands under `reports/policy/`, which is gitignored (unchanged from
  v0.0.5).
- The PDF itself, and the text this feature converts from it, exist only in memory for the
  duration of one asset's own extraction attempt and are never written to disk by this feature.
- His policy text is sent only to `http://localhost:11434` (or wherever his own
  `HEADLESS_OLLAMA_URL` points, provided it resolves to `localhost`/`127.0.0.1`) - a request to
  any other host is refused before it is ever constructed (Scenario 6).

```bash
git status
```

Expected: clean, or showing only files this delivery's own implementation intentionally modified
(source and test files, docs of record) - never a file under `reports/`, and never a captured
value from his own real document anywhere in a diff.

## Scenario 6: the localhost-only refusal (US2, does not require Ollama or a real PDF)

```bash
HEADLESS_OLLAMA_URL=https://example.com python scripts/policy_extract.py vehicles.primary
```

Expected: the run refuses immediately with a value-free configuration error naming only that
`HEADLESS_OLLAMA_URL` must resolve to `localhost` or `127.0.0.1` - no passphrase prompt, no PDF
conversion, no network call of any kind. This scenario is safe to run exactly as written (it uses
no real value and reaches no real endpoint) and is a good first check after implementation, before
ever touching a real document.
