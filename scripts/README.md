# Agentic Skills (scripts/)

Two kinds of script live here: **maintenance** scripts that keep the repo honest, and
**errand** scripts that drive a site on the Director's behalf. Both follow the
Automation-First CLI pattern (`PATTERNS.md`): `argparse`, safe preview by default, runnable
from cron or CI.

## Maintenance

| Script | Description |
| :--- | :--- |
| `verify_structure.py` | Fails (exit 1) when a file on disk is missing from the `Project_Structure.md` Changelog. Part of the commit gate. `--dry-run` prints a read-only notice. |
| `check_env.py` | Environment self-test: Chrome (`chrome` channel), Playwright runtime + browser cache, profile directory, secrets vault, and (specs/002-commit-safety-gate) `core.hooksPath` activation. Prints PASS/FAIL/SKIP per row; opens no browser window. Not a browser errand; the errand contract below does not apply (no preview/apply/check modes, no `HANDOFF`). Usage: `python scripts/check_env.py`. |
| `scan_secrets.py` | Commit safety gate (specs/002-commit-safety-gate): credential and personal-identifier scanner, standard library only, runs under the macOS system `python3` as well as the project's `.venv`. Not a browser errand; never opens a browser or writes anything. Four mutually exclusive modes: `--staged` (added lines of `git diff --cached`, used by `.githooks/pre-commit`), `--paths FILE [FILE ...]` (complete content of named files), `--history` (every blob reachable from `HEAD`, used by the CI backstop), `--stdin-hook` (reads a Claude Code `PreToolUse` payload from stdin, used by `.claude/settings.json`). Exit `0` clean / `1` findings / `2` usage error in the first three modes; `--stdin-hook` always exits `0` and communicates a deny through its own JSON output (fail-open on anything it cannot parse). See `contracts/cli-and-hooks.md` for the full contract and `.scanignore` for the allowlist grammar. |
| `vault.py` | The local age-encrypted vault CLI (spec 004-age-vault): the only place the vault is ever written. Not a browser errand; never opens a browser. Subcommands: `init` (refuses if the vault file already exists), `set NAME` (value read via hidden `getpass`, never `argv`; v0.0.4.3: a PIPED stdin value is accepted too - `pbpaste | python scripts/vault.py set profile` - and is REQUIRED for values of 1024+ characters, which macOS terminals truncate at the hidden prompt; the interactive prompt refuses such values rather than storing a cut-off paste), `get NAME` (v0.0.4.1: prints NAME's raw value to stdout after the passphrase-gated decrypt - the one documented exception to the never-print-values rule, a Director-invoked terminal read for the fetch, edit in an editor, `set` round trip; no errand code path calls it), `unset NAME` (idempotent), `list` (item names only, never values), `path` (resolved vault file path, no `age` invocation), `verify` (v0.0.4.2: checks the stored profile item's STRUCTURE against `profile.template.json` - unknown fields, missing fields, wrong shapes, duplicate or absent `type` discriminators; findings are value-free paths; exit 0 when only warnings or clean, 1 on errors). Every read-or-write subcommand triggers its own passphrase prompt; nothing is cached across invocations. Exit `0` success / `1` a vault-level refusal / `2` a usage error. Usage: `python scripts/vault.py {init,set,get,unset,list,path,verify} [NAME]`. See `specs/004-age-vault/contracts/vault-and-cli.md` for the full contract. |
| `policy_extract.py` | Extract, confirm, and cache a current-policy reference from an insured asset's own `policy_doc` PDF (spec 005-insurance-quote-comparison, User Story 3, research.md D15; extraction pipeline replaced by spec 006-policy-extraction-v2, then corrected and extended by spec 007-extraction-fidelity). Not a browser errand; never opens a browser. Site: none. Reads: `profile`'s `addresses`/`vehicles` arrays (one passphrase prompt for the whole run, a direct JSON parse - never through `ProfileRegistry`, built for single-element addressing, not enumeration); the PDF named by each eligible element's `policy_doc`. Writes: `reports/policy/<asset-key>.json`, mode `0600` where the platform supports it - only for a candidate the Director explicitly confirmed (accepted or corrected) at the terminal prompt `confirm_candidate` prints. Candidate generation (v0.0.6): converts the PDF with layout awareness (`pymupdf4llm`, falling back to the existing `pypdf` raw-text path on an import failure or a raised call; v0.0.7 de-glues whichever text results, closing a converter-glued-phrase gap) and attempts a local-only Ollama model first, unless `--no-llm` is passed; falls back automatically to the unchanged v0.0.5 regex heuristics whenever the local-model attempt fails (connection refused, missing model, timeout, empty/non-JSON/schema-mismatched response - one value-free note each time), never a crash and never a partial candidate. A mechanical sanity pass strips any figure absent from the converted source text before the candidate ever reaches the confirmation prompt - v0.0.7 corrects this check to per-digit-run-token membership (a composite or spaced verbatim figure now survives; a hallucination sharing only a digit-run suffix/prefix with a real figure still fails) and corrects the term-derivation window to scan every policy-period label occurrence and window only the text after it (closing a mis-paired-unrelated-date defect), with an explicit "N-month" phrase now outranking date arithmetic for both generators. No call of any kind ever reaches a non-local endpoint - `HEADLESS_OLLAMA_URL` must resolve to `localhost`/`127.0.0.1` or the run refuses with a value-free `ConfigError` before any conversion or network call; the local-model request now also states an explicit context-window size, with a value-free warning when a long document risks silent truncation against it. The cached reference records which generator (`"regex-v1"` or `"local-llm:<model>"`) and which converter (`"pymupdf4llm"` or `"pypdf-raw"`) produced it, plus (v0.0.7) its own sanity-pass `warnings` list (a pre-v0.0.7 cache file with none reads back as `[]`) and ten additive schema fields (a policy number, explicit effective/expiration dates, a policy-level deductible, the insured asset, named insureds, excluded drivers, discounts, fees, a subtotal) when the document states them. The confirmation prompt itself now prints a distinct, labeled warnings section - a count, then each warning - ahead of the existing candidate JSON block whenever the sanity pass stripped or corrected anything, so the Director sees exactly what survived before he decides. `"n/a"` on `currently_insured` or `policy_doc` is silently skipped (the Director's own exclusion sentinel), as is an asset with no `policy_doc` set at all. Usage: `python scripts/policy_extract.py [asset.path] [--no-llm]` (e.g. `vehicles.primary`; omitted asset means every eligible asset; `--no-llm` skips the local-model attempt entirely). Exit `0` on completion (skipped/declined/zero-lines-parsed assets are not failures), `1` a vault-level refusal, `2` a usage error. See `specs/005-insurance-quote-comparison/contracts/walk-capture-report.md` section 9, `specs/006-policy-extraction-v2/contracts/extraction-v2.md`, and `specs/007-extraction-fidelity/contracts/fidelity.md`. |

## Errands

| Script | Description |
| :--- | :--- |
| `probe.py` | Open a URL in the Headless profile and write a preview artifact; prints the page title. Read-only (`HANDOFF = "n/a (read-only errand)"`); `--apply` still performs the handoff with an empty plan so the Director can seed a login. Usage: `python scripts/probe.py <URL> [--apply|--check] [--profile-dir PATH] [--headless] [--preview-dir PATH] [--no-screenshot]`. |
| `headless/insurers/progressive.py`'s `ProgressiveQuoteErrand` | Not invoked directly - composed by `quote_compare.py` (below) via `headless.insurers.WALK_REGISTRY["progressive"]`. See `Function_Mapping.md` for its own row. |

## Orchestrators

An orchestrator composes one or more existing `Errand` subclasses' own `.run()` calls rather
than being one itself - `Errand.url()`/`dependencies` are single-site concepts by design, and an
orchestrator's whole point is "more than one site in the same invocation." It still follows the
Automation-First CLI pattern (`argparse` via the shared `add_mode_arguments()` surface, safe
preview by default), but has no `HANDOFF` of its own - each composed `Errand`'s own run handles
its own handoff internally.

| Script | Description |
| :--- | :--- |
| `quote_compare.py` | The insurance multi-insurer orchestrator (spec 005-insurance-quote-comparison, User Story 4). Reads `profile`'s `feature_configs.insurance.companies` (direct JSON parse) and, for each id present in `headless.insurers.WALK_REGISTRY`, runs that insurer's own `Errand.run()` in the same mode this script itself was invoked in, forwarding the standard mode flags unchanged; an id with no registry entry becomes a "not mapped yet" row with zero `Session`/`Config`/browser-process construction for it. One insurer's failure is recorded value-free and never stops the rest. In apply mode, after every mapped insurer's walk has finished, it reads the confirmed current-policy reference from `reports/policy/vehicles-primary.json` (absent or unparseable is never a refusal - the comparison degrades to premium-only ranking), runs the comparison engine (`headless/compare.py`), and writes the self-contained HTML report (`headless/report.py`) to `reports/quote-comparison-<date>.html`. Before any insurer's `Errand` is constructed, in every mode, it checks whether the targeted asset (`vehicles.primary`) is excluded by the Director's own `"n/a"` sentinel; if so, zero insurer journeys run and (apply mode only) the report states the exclusion instead of a comparison table. Usage: `python scripts/quote_compare.py [--apply|--check] [--profile-dir PATH] [--headless|--show] [--preview-dir PATH] [--no-screenshot]`. Exit `0` when preview/check completed or a report was written in apply mode (regardless of individual insurer outcomes), `1` when `profile` itself was invalid JSON or `feature_configs.insurance.companies` was missing/malformed, `2` a usage error. See `specs/005-insurance-quote-comparison/contracts/walk-capture-report.md` section 4. |

## Errand contract

Every errand script:

1. Opens with a docstring stating the site, the background, the handoff point, and the
   secrets and profile fields it needs.
2. Declares `HANDOFF = "<the step the human takes>"` as a module constant.
3. Runs in **preview** mode with no flags (no site writes; artifact under `previews/`),
   in **check** mode with `--check` (read-only selector probe), and in **apply** mode with
   `--apply` (fills up to `HANDOFF`, then leaves the window open and prints "Your turn").
4. Never implements a submit, pay, e-verify, or OTP step.

**Walk etiquette** (spec 005-insurance-quote-comparison, optional - a `plan()`-only errand needs
none of this): an errand may override `walk(registry) -> list[Step]` instead of (or alongside)
`plan()` to declare a multi-page journey - a `FieldPlan` (unchanged), a `ClickStep` (a named
wizard-navigation click, apply-only, no retry), a `HumanStep` (a named mid-walk handoff: the
window surfaces, `Your turn: <instruction>` prints, the walk continues after the Director's Enter
press - it does not end there), or a `CaptureStep` (a named, read-only scrape into a flat field
mapping). The default `walk()` returns `plan(registry)` unchanged, so an errand that never
overrides it is completely unaffected. Preview never executes a step beyond the errand's own
initial page load, in any mode but apply - a `--apply`-only funnel exists specifically so the
default no-flags run stays exactly as safe as it always has been. See
`specs/005-insurance-quote-comparison/data-model.md` for the full contract and
`headless/insurers/progressive.py` for the one shipped example.
