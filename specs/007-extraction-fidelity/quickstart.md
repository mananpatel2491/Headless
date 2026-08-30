# Quickstart: Extraction Fidelity

**Feature**: 007-extraction-fidelity | **Date**: 2026-08-29

Runnable validation scenarios that prove this feature end-to-end, once implemented. Contracts are in
[contracts/fidelity.md](contracts/fidelity.md); entities in [data-model.md](data-model.md).

**This document names two different audiences with two different scopes. Scenarios 1 and 2 are a
read-only reviewer probe - safe for anyone with this repository and the three real PDFs to run,
because they check terms and warning counts only, never print or record a real figure. Scenarios 3
through 5 are the Director's own later re-extraction session, explicitly out of this delivery
(research.md D8, D9) - a separate session, after this specification and its implementation are both
reviewed. Every value below is a placeholder or a structural description; no real figure, name,
policy number, premium, or filesystem path from any real document appears anywhere in this
document.**

## Prerequisites

- From the worktree root, the existing `.venv`, with this feature's own implementation installed (no
  new dependency - `pip install -r requirements.txt` needs no change from spec 006).
- For Scenarios 1 and 2 only: the three real declarations PDFs the audit used, at whatever paths the
  orchestrator supplies at run time. Never record those paths in this repository.
- For Scenarios 3 through 5 only (the Director's own later session, not run by this delivery): Ollama
  installed and running, with the configured model pulled, and the Director's own `profile` vault
  item already pointing each targeted asset's own `policy_doc` at its real PDF (unchanged from spec
  005/006).

## Scenario 1: the reviewer's own term-only probe (read-only, safe to run now)

For each of the three real declarations PDFs, run the corrected extraction pipeline against it
directly (bypassing the vault and the confirmation prompt - a read-only harness a later
implementation session provides for exactly this check) and report only the derived
`term_months` value and the count of any `"...did not appear in the document and was removed"`
warnings.

Expected, across the three documents:

- Derived terms: twelve months, six months, and twelve months, respectively (matching the real
  policy terms the audit already confirmed by hand against each document).
- Zero stripped-verbatim warnings on any of the three - every figure the corrected gate would have
  stripped under spec 006's own defect (Defect A) now passes, because it is genuinely present in the
  source, verbatim, once tokenized correctly.

Nothing about this scenario prints a real figure, a real insurer name, or a real coverage line - only
a term-months string (already a computed value, not document content) and a warning count (an
integer). This is the shape of check `research.md` D8 and `spec.md` SC-005 both describe as an
orchestrator-observed outcome, not something this repository's own automated `pytest -q` suite
asserts.

## Scenario 2: the reviewer's own composite-figure spot check (read-only, safe to run now)

Against the one document whose coverage table states a composite, multi-digit-run limit (the
document Defect A's own audit evidence names), run the corrected sanity pass and confirm that the
specific field the pre-fix pipeline stripped (a liability limit) now survives with a non-empty value.
Report only whether the field is non-empty - never its own actual figure.

Expected: the field is non-empty, and no `"...did not appear in the document and was removed"`
warning names that field.

## Scenario 3: the Director's own re-extraction against a corrected pipeline (Director-only, later
session)

```bash
python scripts/policy_extract.py vehicles.primary
```

Expected, once this feature is implemented and this scenario is actually run by the Director:

1. One passphrase prompt (unchanged from spec 005/006).
2. A value-free note naming which converter served the run (unchanged from spec 006).
3. If the sanity pass stripped anything, a distinct warnings section - a count, then each warning on
   its own line - printed **before** the existing candidate JSON block (this feature's own new
   behavior, FR-019 through FR-021). If nothing was stripped, this section does not print at all.
4. The same "Extracted current-policy candidate (your own data, printed for your review)" header and
   full JSON block spec 006 already prints - now including the ten new schema fields when the
   document states them, and still embedding the same `warnings` list inside the JSON body.
5. The same "Accept as printed, correct it, or decline? [a/c/d]:" prompt, unchanged.

The concrete thing for the Director to check against his own real policy at step 4: a composite or
split limit that spec 006's own pipeline previously stripped should now print with its real value,
and the derived `premium.term_months` should already read the correct term even when the page states
no explicit "N-month" phrase before de-gluing.

## Scenario 4: inspecting the cached reference's new fields (Director-only, later session)

After accepting a candidate in Scenario 3:

```bash
cat reports/policy/vehicles-primary.json
```

Expected: the same `insurer`/`premium`/`coverages`/`source_path`/`confirmed_at`/`generator`/
`converter` fields spec 006 already wrote, plus:

```json
{
  "warnings": [],
  "policy_number": "",
  "effective_date": "",
  "expiration_date": "",
  "policy_level_deductibles": [],
  "asset": {},
  "named_insureds": [],
  "excluded_drivers": [],
  "discounts": [],
  "fees": [],
  "subtotal": ""
}
```

(Each field's own actual value depends entirely on what the Director's real declarations page states
and what he confirmed - the empty shapes above are only what a reader should expect the *keys* to
look like, never a claim about what any real cache file's own values will be.) A non-empty
`warnings` list here means the confirmed reference survived at least one strip or a date-parse
failure - worth a second look against the printed candidate from Scenario 3, step 3.

## Scenario 5: confirming his real values still never enter the repository (Director-only, later
session)

Unchanged from spec 006's own equivalent scenario - nothing this feature adds changes where a real
value can land:

- The candidate JSON, and now the warnings section ahead of it, print to the Director's own terminal
  only - the same documented, sole-purpose exception to this codebase's value-free-output convention
  spec 006 already established.
- The cached reference lands under `reports/policy/`, gitignored, unchanged.
- The PDF itself, the converted text, and the de-glued text all exist only in memory for the duration
  of one asset's own extraction attempt.
- His policy text is still sent only to the local-only endpoint spec 006's own `ConfigError` already
  enforces - this feature adds no new network call and no new endpoint.

```bash
git status
```

Expected: clean, or showing only files this delivery's own implementation intentionally modified -
never a file under `reports/`, and never a captured value from a real document anywhere in a diff.
