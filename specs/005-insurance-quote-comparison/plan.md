# Implementation Plan: Insurance Quote Comparison

**Branch**: `v0.0.5` | **Date**: 2026-08-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-insurance-quote-comparison/spec.md`

## Summary

Extend `Errand` from a single-page form filler into a multi-page walk runner, and build the
program that walk enables: one insurer's real quote captured end to end (Progressive), a
deterministic engine that compares any number of captures against the Director's current policy,
and a self-contained HTML report that recommends one. Four kinds of `Step` (`FieldPlan`,
`ClickStep`, `HumanStep`, `CaptureStep`) replace the implicit "a walk is just a list of fields to
fill"; `Errand.walk(registry)` defaults to wrapping `plan()` so every existing errand is
unaffected. Two new vault items (`insurers`, `current_policy`) hold data `ProfileRegistry` cannot
address, because it refuses any dotted path that resolves to a list or an object. A new
orchestrating script, `scripts/quote_compare.py`, composes each mapped insurer's own `Errand`
subclass rather than reimplementing session/gate/vault machinery a second time, isolates one
insurer's failure from the rest, and - only in apply mode, only after every insurer's walk has
finished - runs the comparison engine and writes the report. Decisions are recorded in
[research.md](research.md) (D1-D10, plus the recon evidence for D8).

## Technical Context

**Language/Version**: Python 3.14 (venv per worktree, same as every prior feature in this
repository)

**Primary Dependencies**: one new Python package, `pypdf` (added to `requirements.txt`), added by
Director amendment (6) after this plan was first drafted: `scripts/policy_extract.py`'s own PDF
text extraction needs it, and nothing in `headless/`, `scripts/vault.py`, or `scripts/
quote_compare.py` has an equivalent capability already. Every other module stays standard-library
only. This feature extends the existing Playwright session (`headless/session.py`) with two new
page operations (`click`, `capture`); the comparison engine and report generator use the standard
library only (`dataclasses`, `json`, `datetime`, `html` for escaping captured text before it
reaches the report, `pathlib`). No templating engine is added - the report's HTML is built from
Python f-strings/string joins, the same "no framework where a function suffices" approach
`scripts/scan_secrets.py` already established for its own standard-library-only design.

**Storage**: two new persisted artifact classes, both under a new top-level `reports/` directory
(sibling to `previews/`, created on first use the same way): `reports/captures/<insurer>-
<timestamp-utc>.json` (one `QuoteCapture` per successful capture, accumulating over time - never
overwritten, only ever added to) and `reports/quote-comparison-<date>.html` (one report per apply
run, overwriting any earlier report from the same date). Neither is a database; neither is
version-controlled. Two new vault items (`insurers`, `current_policy`) live inside the existing
`age`-encrypted vault file (spec 004-age-vault), read via the unchanged `get_secret(name)`
contract - this feature adds no new persisted format to the vault itself, only two more named
strings inside the same JSON object every vault item already lives in.

**Testing**: `pytest>=8` (already a dependency). Every new module (`headless/steps.py`,
`headless/capture.py`, `headless/compare.py`, `headless/report.py`, `headless/insurers/
progressive.py`) is unit-testable without a browser: the step types are plain dataclasses, the
capture/compare/report modules are pure functions over JSON-shaped fixtures, and the walk
framework's dispatch logic is tested against a fake `Session` the same way `tests/test_session.py`
already fakes a page/context for its own screenshot-masking and cookie-persistence tests.
`scripts/quote_compare.py`'s own orchestration logic (per-insurer isolation, unmapped rows) is
tested against fixture `Errand` subclasses whose `run()` is stubbed to return a fixed exit code,
never a real `Errand.run()` call - matching the existing convention of never letting a real
browser or a real passphrase prompt into the default `pytest -q` run.

**Target Platform**: same as every prior feature - the Director's macOS machine (Chrome 151,
channel `chrome`) is the only platform this delivery is verified against; nothing in the walk
framework, the capture model, the comparison engine, or the report generator is
platform-conditional (unlike spec 004's `age_file` permission handling, which had a real
Windows-vs-POSIX difference to document).

**Project Type**: package extension (`headless/session.py`, `headless/errand.py`) plus four new
package modules (`headless/steps.py`, `headless/capture.py`, `headless/compare.py`,
`headless/report.py`) plus a new insurer-walk package (`headless/insurers/`, holding
`progressive.py` and the walk registry) plus one new orchestrating script
(`scripts/quote_compare.py`). Single project, same as every prior feature.

**Performance Goals**: not a latency-sensitive path for the same reason spec 004's vault decrypt
was not - a full multi-insurer apply run is bounded by how long a real quote funnel and the
Director's own `HumanStep` responses take, not by anything this feature's own code does. The
comparison engine and report generator, run over even a large capture history, must still be fast
enough that the unit suite covering them completes in well under a second (spec NFR-002, SC-004),
since none of that logic touches a browser, a subprocess, or a passphrase prompt.

**Constraints**: preview must never navigate past a walk's landing page, in any mode, for any
insurer (spec FR-006, SC-001) - this is the single constraint every other design decision in this
feature has to respect, since it is what keeps a `--preview` (the default, no-flags run) as safe
against every future insurer's walk as it already is against `probe.py` today. No LLM call may
appear anywhere in the comparison or report path (spec FR-020) - the entire engine is pure,
deterministic Python over JSON-shaped data. `reports/` must carry the same vault-grade
classification `previews/` already does (spec FR-015) - gitignored, from the first commit that
creates the directory, not added after the fact. One insurer's failure must never propagate past
`scripts/quote_compare.py`'s own per-insurer loop (spec FR-029, NFR-004). No walk this feature or
any future insurer walk built on it may ever gain a submit/pay/verify/otp step type (spec FR-010),
unchanged from the constitution's existing Hard Rule.

**Scale/Scope**: the largest feature this repository has shipped a spec for. Five new package
modules, one new insurer-walk package, one new orchestrating script, two extended existing modules
(`headless/session.py`, `headless/errand.py`), two new vault items, a new top-level gitignored
directory, and a new orchestration layer (composing existing `Errand` subclasses rather than
extending any single one) that no prior feature needed, because every prior feature was a single
script against a single site. See Complexity Tracking below for why this still ships as one
release rather than being split further.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against the constitution as it stands today (1.3.0, spec 004-age-vault's own bump);
this feature introduces no constitutional amendment of its own - nothing in it changes a Core
Principle, a Hard Rule, or the default secrets backend. Any wording addition (PATTERNS.md,
CLAUDE.md's Browser or Secrets sections gaining a sentence about `reports/` or the walk framework)
is a Polish-phase, implementation-time task, not something this spec-authoring delivery performs.

| Principle / rule | Status | Evidence |
| :--- | :--- | :--- |
| I. Context-First Architecture Map | PASS | `Project_Structure.md` gains a v0.0.5 Changelog row naming every file this feature touches or adds, plus new Application Layer rows for `headless/steps.py`, `headless/capture.py`, `headless/compare.py`, `headless/report.py`, `headless/insurers/`, `scripts/quote_compare.py`, and `reports/` - all deferred to the implementation delivery's Polish phase (tasks.md), not performed by this spec-authoring delivery. |
| II. Pattern Reference Integrity | PASS | `PATTERNS.md` gains new entries at implementation time (tasks.md Polish phase): the sanctioned-click pattern (`Session.click`, mirroring `Session.fill`'s existing "the only sanctioned way" framing), the walk-entry pattern (`Errand.walk()` defaulting to `plan()`), and `reports/`'s vault-grade classification (mirroring `previews/`'s own entry). This plan does not pre-empt their wording. |
| III. Automated Maintenance via Agentic Skills | PASS | `scripts/quote_compare.py` follows the Automation-First CLI pattern every prior script already establishes: `argparse` (via the shared `add_mode_arguments()` surface, spec FR-026), a safe preview-by-default, non-interactive beyond the vault's own passphrase prompts. It is a new architectural shape - an orchestrator composing other `Errand` subclasses rather than being one itself - documented explicitly in data-model.md and contracts/walk-capture-report.md rather than silently stretched to fit the existing single-site `Errand` contract. |
| IV. Continuous Errand Validation | PASS | Every new module's pure logic (step dispatch, capture assembly, coverage-line normalization and ranking, report rendering) gets unit tests with fixture data, no browser. The Progressive walk gains its own `--check` coverage of the landing-page selectors already verified (spec FR-031); every selector beyond the landing page ships only if implementation-time recon proves it resolves (spec FR-032) - the same "ship only working code" discipline `PATTERNS.md`'s commit-safety-gate entry already states for a different context, applied here to selectors instead of scanner patterns. |
| V. Infrastructure-as-Code and Cost Gating | PASS, unaffected | No cloud resource of any kind. Every artifact this feature writes (captures, the report) is local disk, gitignored, $0. |
| Gates hard rule (preview/apply/check, no submit) | PASS, extended, not weakened | The walk framework's four step kinds are a superset of what a `FieldPlan`-only errand could already do; no new mode exists, and FR-010 makes explicit, for the first time as a numbered requirement rather than an implicit practice, that the walk framework itself structurally cannot gain a submit/pay/verify/otp step type - closing that door for every future insurer walk built on it, not just this one. |
| Secrets hard rule | PASS, extended | `insurers`/`current_policy` are vault items like any other (FR-011), subject to the same per-run passphrase gate spec 004 already established; `reports/` inherits `previews/`'s existing vault-grade classification rather than inventing a new one (FR-015). No password or payment card value is ever asked for or stored by this feature - `current_policy` is coverage and premium data, not a credential. |
| Registry-only-source hard rule | PASS, not implicated | This rule governs what a script may *type* into a form; `insurers`/`current_policy` are read-only orchestration input, never typed anywhere - `CaptureStep` reads, it never writes. `ClickStep` types nothing; its only argument is a selector, hand-authored in the insurer's own walk module, the same way every existing `FieldPlan.selector` already is. |
| Browser hard rule | PASS, unaffected | No new browser-launch path; `Session.click`/`Session.capture` are new operations on the same session `Session.fill`/`Session.probe` already own. Headless-by-default for preview/check, windowed-and-quiet-until-handoff for apply, are unchanged; a `HumanStep` reuses the existing `handoff()` surfacing behavior rather than inventing a second one. |
| Public repository hygiene | PASS, unaffected | No new secret-shaped pattern this feature's own code introduces beyond what `insurers`/`current_policy`'s test fixtures need to stay obviously synthetic (spec FR-030, `.scanignore`'s existing convention) - no change to `scan_secrets.py` itself is anticipated, though the implementation delivery must re-verify this once real fixture text exists. |
| Spec-driven workflow | PASS | This delivery runs specify only (spec-authoring, this worktree, this session) on `v0.0.5`, per the mananUtils worktree protocol and this delivery's explicit brief. Plan, research, data-model, contracts, quickstart, tasks, and the requirements checklist are all produced in this same delivery, per this feature's brief - matching the shape spec 004's own delivery used, though unlike that delivery this one does not also implement the code; implementation, verification, and merge are separate, later, explicitly authorized runs. |

No violations; Complexity Tracking (below) documents why this feature's size is justified rather
than split, not a constitutional exception.

**Post-design re-check (after Phase 1)**: the data model (`Step` union, the walk mode matrix,
`QuoteCapture`/`CurrentPolicy`/`ComparisonResult`, the `Errand.run()` state-machine delta) and the
one contract document (`contracts/walk-capture-report.md`) introduce exactly the modules and one
script named in Technical Context above - no additional abstraction, no speculative extensibility
point beyond `headless/insurers/`'s own registry dict (which exists specifically because D1
requires a second insurer to be addable later without touching this feature's own files). PASS.

## Project Structure

### Documentation (this feature)

```text
specs/005-insurance-quote-comparison/
├── spec.md
├── plan.md                            # This file
├── research.md                        # Phase 0: decisions D1-D10, recon evidence
├── data-model.md                      # Phase 1: Step union, mode matrix, QuoteCapture,
│                                       #   CurrentPolicy, ComparisonResult, Errand.run() delta
├── quickstart.md                      # Phase 1: the Director's UAT script
├── contracts/
│   └── walk-capture-report.md         # per-mode walk table, Session.click/handoff/capture
│                                       #   contracts, capture/report file paths, quote_compare.py
│                                       #   CLI, report HTML structure
├── checklists/
│   └── requirements.md
└── tasks.md                           # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
headless/
├── steps.py                    # NEW: ClickStep, HumanStep, CaptureStep dataclasses;
│                                #   Step = FieldPlan | ClickStep | HumanStep | CaptureStep
├── session.py                  # UPDATED: Session.click(selector) (apply-only, no retry,
│                                #   raises ClickFailed - mirrors Session.fill's shape exactly);
│                                #   Session.capture(extractors) (read-only, mirrors
│                                #   Session.probe's existing read-only shape); ClickFailed
│                                #   exception class (mirrors FillFailed, no value to redact)
├── errand.py                   # UPDATED: Errand.walk(registry) (default wraps plan()); run()'s
│                                #   pre-resolution loop filters walk() for FieldPlan only;
│                                #   apply-mode dispatch loop handles all four Step kinds;
│                                #   preview-mode records FieldPlan sources (unchanged) plus
│                                #   lists other steps by kind/name; trailing handoff unchanged
├── capture.py                  # NEW: QuoteCapture, CurrentPolicy dataclasses;
│                                #   parse_current_policy(raw_json) -> CurrentPolicy;
│                                #   parse_insurers(raw_json) -> list[str]; assemble_capture(
│                                #   insurer, source_url, fetched_at, raw_fields) -> QuoteCapture;
│                                #   write_capture/read_freshest_capture; QuoteInputError
│                                #   (mirrors ProfileError's position-only-message shape)
├── compare.py                  # NEW: the coverage-line alias table; classify_line();
│                                #   rank_quotes(); ComparisonResult; build_comparison(
│                                #   current_policy: CurrentPolicy | None, captures) ->
│                                #   ComparisonResult. No I/O.
├── report.py                   # NEW: render_report(comparison, unmapped, failed) -> str (HTML,
│                                #   inline CSS, no external reference); write_report(html,
│                                #   reports_dir) -> Path. No I/O beyond the one write.
├── policydoc.py                # NEW (Director amendment 6): PDF extraction + confirmation +
│                                #   cache - extract_candidate(pdf_path) -> CurrentPolicy (pypdf,
│                                #   deterministic heuristics only, no LLM); confirm_candidate()
│                                #   (prints, prompts accept/correct); write_policy_reference()/
│                                #   read_policy_reference() against reports/policy/<asset-key>.json
└── insurers/
    ├── __init__.py              # NEW: WALK_REGISTRY: dict[str, type[Errand]]; {"progressive":
    │                             #   ProgressiveQuoteErrand} - the only entry in this delivery
    └── progressive.py           # NEW: ProgressiveQuoteErrand(Errand) - the landing fill/click
                                  #   (verified selectors) plus whatever recon (research.md D8)
                                  #   proves past it, HumanStep-bridged where it does not

scripts/
├── quote_compare.py            # NEW: the orchestrator - reads feature_configs.insurance.
│                                 #   companies (profile, direct JSON parse) and the confirmed
│                                 #   current-policy reference from reports/policy/ (never from
│                                 #   profile directly, D3/D15), checks the targeted asset's own
│                                 #   "n/a" exclusion sentinel before any insurer runs,
                                  #   forwards standard mode flags to each mapped insurer's own
                                  #   Errand.run(), then (apply mode, after all insurers) runs
                                  #   compare.build_comparison() and report.render_report()/
                                  #   write_report()
└── policy_extract.py            # NEW (Director amendment 6): maintenance-adjacent script, not
                                  #   a browser errand - finds every addresses[]/vehicles[]
                                  #   element with a real (non-"n/a") policy_doc set, extracts a
                                  #   candidate via headless/policydoc.py, prints it, prompts
                                  #   accept/correct, caches the confirmed result under
                                  #   reports/policy/<asset-key>.json

.gitignore                      # UPDATED: reports/ added, mirroring previews/'s existing entry
                                 #   (reports/policy/ inherits the same entry, no separate line)

tests/
├── test_steps.py               # NEW: Step dataclass shape tests
├── test_session.py             # UPDATED: Session.click (apply-only refusal, no-retry,
│                                #   ClickFailed shape), Session.capture (found/missing extractor
│                                #   branches, value-free note)
├── test_errand.py              # UPDATED: walk() default-wraps-plan() test; the four-step-kind
│                                #   apply dispatch; preview-mode's zero-navigation-past-landing
│                                #   proof (SC-001); the HumanStep window-stays-visible proof
├── test_capture.py             # NEW: parse_current_policy/parse_insurers (valid + malformed,
│                                #   SC-008), assemble_capture, write/read-freshest-capture
├── test_compare.py             # NEW: alias-table normalization, per-line classification,
│                                #   ranking rule (SC-006), rule-trail text construction
├── test_report.py              # NEW: HTML structure, zero-external-reference proof (SC-002),
│                                #   value-free failure row proof (SC-003), provenance footer
│                                #   proof (SC-010)
├── test_insurers_progressive.py # NEW: the Progressive walk's own pure-logic tests (landing
│                                #   FieldPlan/ClickStep shape, dependencies list) - never a real
│                                #   browser call
└── test_quote_compare.py       # NEW: orchestrator tests against fixture Errand subclasses
                                  #   (unmapped-insurer zero-Session proof SC-007, one-insurer-
                                  #   failure-does-not-stop-others proof SC-005, malformed-
                                  #   current_policy-refuses-before-any-Session proof SC-008)

CLAUDE.md                       # UPDATED (Polish): Secrets section names insurers/current_policy
                                  #   and reports/'s vault-grade classification; Browser section
                                  #   unchanged (no new browser-launch path)
.specify/memory/constitution.md # UPDATED (Polish): regenerated distillation; version bump
                                  #   assessed at implementation time against the actual wording
                                  #   change (likely PATCH: this feature extends existing hard
                                  #   rules' reach the way spec 003's session-cookie file did,
                                  #   rather than introducing a new one the way spec 002's commit
                                  #   gate or spec 004's default-backend change did - confirmed or
                                  #   revised once the actual CLAUDE.md diff exists)
PATTERNS.md                     # UPDATED (Polish): three new entries (sanctioned click, walk
                                  #   entry, reports/ vault-grade classification)
Project_Structure.md            # UPDATED (Polish): v0.0.5 Changelog row; new Application Layer
                                  #   rows for every new file/directory above
Function_Mapping.md             # UPDATED (Polish): a row for headless/insurers/progressive.py's
                                  #   ProgressiveQuoteErrand (site, reads, writes-up-to, secrets,
                                  #   handoff); a note that scripts/quote_compare.py is an
                                  #   orchestrator composing other errands, not an errand itself
scripts/README.md               # UPDATED (Polish): quote_compare.py documented in a new
                                  #   "Orchestrators" section, distinct from Maintenance and
                                  #   Errands; the errand contract gains a short amendment
                                  #   describing walk()/HumanStep etiquette for any future errand
                                  #   that adopts it
MEMORY.md                       # UPDATED (Polish): the Director's decision recorded (this
                                  #   feature's own brief, 2026-08-25); an "Errands run" row once
                                  #   Director UAT produces a real outcome to record

headless/gates.py               # UNCHANGED - no new mode, no new flag; add_mode_arguments() is
                                  #   reused as-is by scripts/quote_compare.py (spec FR-026)
headless/profile.py              # UPDATED (Director amendment 4): ProfileRegistry.get gains
                                  #   type-discriminated array addressing (RegistryAmbiguous, the
                                  #   list-traversal branch - FR-040 through FR-044); its existing
                                  #   refusal of a path ending on a list or a dict is exactly why
                                  #   feature_configs.insurance.companies and policy_doc are read
                                  #   by direct JSON parse instead (D3)
headless/secrets.py              # UNCHANGED - profile is read through the existing
                                  #   get_secret(name) contract; no new backend behavior
headless/config.py               # UNCHANGED - no new environment variable; reports/ location is
                                  #   derived (sibling to previews/, repo-root-relative), not
                                  #   independently configurable, avoiding a second relative-path
                                  #   policy to design and test (see research.md D4's rationale)
requirements.txt                 # UPDATED (Director amendment 6): pypdf added, the one new
                                  #   Python dependency this feature adds
```

**Structure Decision**: single project, same as every prior feature. The walk framework's new
pieces land next to what they extend (`ClickFailed` in `session.py` beside `FillFailed`;
`walk()`'s dispatch in `errand.py` beside `run()`'s existing loop) rather than in a new module, the
same reasoning spec 004's plan gave for putting `AgeBackend` inside the existing `secrets.py`. Four
genuinely new concerns each earn their own file (`steps.py`, `capture.py`, `compare.py`,
`report.py`) because each has its own, independently testable responsibility with no natural home
in an existing module - the same reasoning `scan_secrets.py` and `vault.py` each earned their own
file in spec 002 and spec 004. `headless/insurers/` is a new *package*, not a single new module,
which is the one structural choice this plan makes beyond what the feature's own brief listed by
name (`headless/steps.py`, `headless/capture.py`, `headless/compare.py`, `headless/report.py`,
`scripts/quote_compare.py`): D1 already commits this repository to a second, third, and later
insurer each getting its own future spec and its own selector-mapping work, and a package with one
module per insurer (`progressive.py` today, a `geico.py` or similar alongside it later) is the
structure that scales to that without ever touching this feature's own files again - a single
`headless/insurers.py` module holding every insurer's walk inline would force every future
insurer's spec to edit a file this feature owns, which is exactly the kind of cross-spec coupling
D1 exists to avoid. `scripts/quote_compare.py` is a new script because it is a genuinely new
architectural shape (an orchestrator, not an `Errand` subclass) that has no existing file to extend.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Constitution Check above shows no violation, so this table is not required by the template's own
rule. It is filled anyway, because this plan's own Summary and Scale/Scope sections call this the
largest feature this repository has shipped a spec for, and that scale deserves its own
justification even without a constitutional gate forcing one.

| Concern | Why needed | Simpler alternative rejected because |
| :--- | :--- | :--- |
| Four new package modules plus a new package (`steps.py`, `capture.py`, `compare.py`, `report.py`, `insurers/`) in one release | Each piece is useless alone: a walk framework with nowhere to walk proves nothing (User Story 1 needs User Story 2's real insurer); a capture model with no comparison engine is just a JSON file nobody reads; a comparison engine with no report is a data structure, not the deliverable the Director actually asked for ("recommend me the best quote ... showing the comparison in nice pretty HTML"). | Splitting into "framework only" then "Progressive only" then "compare only" then "report only" across four specs would ship three of them with no way to independently verify they work - User Story 1's own Independent Test already requires a fixture that exercises all four step kinds together, and User Story 2's requires a real capture to feed User Story 3's engine. The dependency chain is real, not an artifact of how this plan organized the work. |
| A new orchestration layer (`scripts/quote_compare.py` composing other `Errand` subclasses) that no prior feature needed | Every prior feature was one script against one site; this is the first feature where "the errand" is inherently plural (the Director's own words: "get quotes from multiple insurance companies"). Reusing each insurer's own `Errand.run()` rather than inventing a second, parallel execution path is what keeps every existing gate, redaction, and pre-resolution guarantee intact for each insurer's own walk, at the cost of the N+1-passphrase-prompt residual spec.md's Assumptions section already names and accepts. | A single monolithic `Errand` subclass whose `plan()`/`walk()` somehow covered every insurer at once was never viable: different insurers have different landing URLs, different selectors, and different `dependencies` lists for `--check` - `Errand.url()` and `Errand.dependencies` are both single-site concepts by design, and forcing them to be multi-site would break `--check`'s existing per-selector reporting for every prior and future single-site errand that still relies on that same base class. |
| **Superseded row, kept for its own historical trail** (research.md D3 was revised twice after this row was written; the final design is `feature_configs.insurance.companies` inside `profile`, read by direct JSON parse, and `current_policy` deleted entirely in favor of per-asset `policy_doc` PDF extraction plus Director confirmation, D15) - this row's own original question, "why not a combined or outside-the-vault design," is still answered the same way below for `companies`; it says nothing about `policy_doc`, which did not exist when this row was drafted | `ProfileRegistry.get` structurally refuses a dotted path resolving to a list or a dict (documented in `headless/profile.py`'s own module docstring, confirmed by the orchestrator before this feature was scoped) - a list of company ids cannot live at a registry dotted path at all, by the registry's own existing design, not by any choice this feature makes. | Storing it outside the vault entirely (a plain JSON file in the repo, or a `.env` value) was rejected: this is personal configuration alongside personal financial data, the same class `CLAUDE.md`'s Secrets section already governs broadly. A separate vault item (this row's own original proposal) was itself superseded once the Director's real `profile` document turned out to already have a natural home for it (research.md D3, both revisions). |

