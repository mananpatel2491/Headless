# Contracts: Insurance Quote Comparison

**Feature**: 005-insurance-quote-comparison | **Date**: 2026-08-25

Twelve stable interfaces: the **per-mode walk table**, the **`Session.click`/`handoff`/`capture`
contracts**, the **capture and report file paths**, the **`scripts/quote_compare.py` CLI**, the
**report HTML structure**, an **amendment to spec 004's vault CLI contract**
(`vault.py get NAME`, already shipped elsewhere - section 6), the **registry's type-discriminated
array addressing** (section 7), the **`profile.template.json` drift test** (section 8), the
**`scripts/policy_extract.py` extraction/confirmation/cache contract** (section 9), the
**`"n/a"` sentinel** (section 10), a second **amendment to spec 004's vault CLI contract**
(`vault.py verify`, also already shipped elsewhere - section 11), and a third **amendment to spec
004's vault CLI contract** (`vault.py set`'s piped-stdin path and 1024-character refusal, also
already shipped elsewhere - section 12).

## 1. Per-mode walk table

| Mode | What runs | What is written | What the Director sees |
| :--- | :--- | :--- | :--- |
| PREVIEW (default, no flags) | `session.goto(url)` only. Every `FieldPlan` source resolves and its masked value is recorded, exactly as spec 001. Every `ClickStep`/`HumanStep`/`CaptureStep` is listed by `{"kind", "name"}` only. | `previews/<errand>-<timestamp>.json` (+ `.png` unless `--no-screenshot`), unchanged shape plus the new `steps` list | Nothing - no window, unless `--show` |
| CHECK (`--check`) | `session.probe(self.dependencies)` only - unchanged from spec 001; a walk's later-page selectors are never probed unless added to `dependencies` directly | `previews/<errand>-<timestamp>.json` with `checks` populated, `steps` empty, unchanged shape | Nothing - no window, unless `--show` |
| APPLY (`--apply`) | Every step in `walk()` executes in order, dispatched by type (table below); the window is hidden at launch and surfaced only at the first `HumanStep` (or the trailing `self.HANDOFF` handoff, if the walk has none) | `previews/<errand>-<timestamp>.json` (unchanged); on a successful `CaptureStep`, one new `reports/captures/<insurer>-<timestamp>.json` | "Your turn: `<instruction>`" once per `HumanStep`, plus once more at the trailing `self.HANDOFF` |

### Apply-mode step dispatch

| Step kind | Call | On failure |
| :--- | :--- | :--- |
| `FieldPlan` | `session.fill(step, vault, registry)` (unchanged, spec 001) | `FillFailed` (unchanged) |
| `ClickStep` | `session.click(step.selector)` | `ClickFailed` (data-model.md) |
| `HumanStep` | `session.handoff(step.instruction)` | Cannot fail in the sense the others can - a closed page is detected by `handoff()`'s own existing `is_closed()` check (spec 001), unchanged |
| `CaptureStep` | `raw = session.capture(step.extractors)`; `capture.assemble_capture(...)`; `capture.write_capture(...)` | A missing extractor never raises (data-model.md's `Session.capture` contract); a write failure (disk full, permissions) propagates as an ordinary `OSError`, caught by `errand.py`'s existing post-session generic `except Exception` branch (class name only, no path content, matching how every other unexpected browser-layer failure is already handled) |

**Multi-tier funnels**: when an insurer's funnel offers more than one coverage package (e.g.
basic/standard/premium), the walk MUST capture the funnel's own pre-selected (default) package
only - never a package the walk itself picks or changes - and record which one in the resulting
`QuoteCapture.package` field (data-model.md, spec FR-014). When implementation-time recon finds a
multi-tier page with no default selection, the walk adds a `HumanStep` asking the Director to
choose before the terminal `CaptureStep` runs.

## 2. `Session.click` / `Session.handoff` / `Session.capture` contracts

### `Session.click(selector: str) -> None`

| Input state | Behavior | Output / observable effect |
| :--- | :--- | :--- |
| Mode is not APPLY | No locator action attempted | Raises `GateRefused("click is only permitted in apply mode")`, mirroring `Session.fill`'s exact wording pattern |
| Mode is APPLY, selector resolves and is clickable | One `locator.click()` call, no retry | Returns `None`; the page navigates or updates however the site's own JavaScript responds |
| Mode is APPLY, selector does not resolve or the click action raises | One attempted `locator.click()` call, no retry | Raises `ClickFailed` (data-model.md): `step_name`, `selector`, `cause_class` only - never the underlying Playwright exception or its message |

### `Session.handoff(handoff_text: str) -> bool` (unchanged from spec 001; reused verbatim for `HumanStep`)

| Input state | Behavior | Output / observable effect |
| :--- | :--- | :--- |
| First call this run (window still hidden, or never hidden) | `_restore_window()` (idempotent, best-effort - see `PATTERNS.md`'s "Quiet by default" entry), print, wait for `_confirm()` | The window becomes visible (best-effort; see the same residual spec 001 already documents) |
| Any later call this run (window already visible) | Same three calls; `_restore_window()` is a harmless no-op re-application of the same bounds | Window stays visible; no flicker, no re-hide |
| The page was closed by the Director before or during the wait | Same three calls; the post-wait `is_closed()` check | Returns `False` instead of raising - unchanged from spec 001 |

**HumanStep prompt line format (exact)**: `Your turn: <instruction>` - the literal string
`session.handoff()` already prints today, with `handoff_text` bound to the `HumanStep.instruction`
value. No new format, no new prefix, no per-kind distinction between a mid-walk `HumanStep` prompt
and the trailing `self.HANDOFF` prompt - both look identical on the terminal, because both are the
same call.

**Window-visibility rule**: once any `HumanStep` (or the trailing handoff) has surfaced the window
in a given run, nothing in that run's remaining steps hides it again - there is no code path that
calls `_hide_window()` more than once per `Session` instance (it is only ever called once, from
`__enter__`, before any step executes).

### `Session.capture(extractors: dict[str, str]) -> dict[str, str]`

| Input state | Behavior | Output / observable effect |
| :--- | :--- | :--- |
| An extractor's selector resolves (`locator.count() > 0`) | Read that locator's text, stripped | That field key maps to the extracted text in the returned dict |
| An extractor's selector does not resolve (`count() == 0`) | No locator read attempted for that key | That field key maps to `""`; exactly one line prints: `note: capture field '<field_key>' not found (selector missing)` |
| Every extractor in the same call | Each is attempted independently; one missing extractor never stops the rest | The returned dict always has exactly the same keys as `extractors`, regardless of how many resolved |
| The page itself is unusable (closed, crashed) | Not caught by `capture()` itself | Propagates as whatever Playwright exception is raised; caught by `errand.py`'s existing post-session generic handler, same as any other unexpected browser-layer failure |

`capture()` never aborts partway through its own `extractors` dict on a single missing selector -
this is the mechanical guarantee behind spec FR-005 and SC-009.

## 3. Capture and report file paths

| Artifact | Path | Written by | Read by | Accumulates or overwrites |
| :--- | :--- | :--- | :--- | :--- |
| One capture | `reports/captures/<insurer>-<fetched_at, filesystem-safe UTC timestamp>.json` | `capture.write_capture`, called from an insurer `Errand`'s apply-mode `CaptureStep` dispatch | `capture.read_freshest_capture` (globs, sorts by the embedded timestamp, takes the newest) | Accumulates - never overwritten or deleted by this feature |
| The report | `reports/quote-comparison-<date, YYYY-MM-DD UTC>.html` | `report.write_report`, called once by `scripts/quote_compare.py` at the end of an apply run | The Director, in a browser, by hand | Overwrites any earlier report from the same UTC date |

**`.gitignore`**: `reports/` (the whole directory - both `captures/` and every dated report),
mirroring the existing `previews/` entry exactly - added once, at the top level, not per-subpath.

**Classification**: identical to `previews/`'s existing vault-grade local-data classification
(`CLAUDE.md`'s Secrets section) - never committed, never shared, never attached anywhere, since a
capture or a report can hold a real premium, a real coverage limit, and implicitly the Director's
own insurability profile. Unlike `previews/`, which `PATTERNS.md` calls disposable ("delete
freely"), `reports/quote-comparison-*.html` is the feature's own deliverable and is not disposable
in the same sense - `reports/captures/` remains safe to prune by hand at any time (a stale capture
simply means the next comparison uses an older, still-honestly-timestamped one, or none, per
data-model.md's `read_freshest_capture` contract).

## 4. `scripts/quote_compare.py` CLI

No flag or environment variable beyond the standard mode flags every errand already shares. Not
an `Errand` subclass - see plan.md's Structure Decision and research.md D7 for why.

| Flag | Behavior |
| :--- | :--- |
| (none) | PREVIEW: if the targeted asset (`vehicles.primary`, FR-060) is excluded (FR-063), print the exclusion and stop. Otherwise run every mapped insurer's own `Errand.run()` in preview mode (its own masked-plan/step-list artifact under `previews/`); print which configured `feature_configs.insurance.companies` entries are unmapped. No capture, no report. |
| `--check` | Same exclusion check first; otherwise run every mapped insurer's own `Errand.run()` in check mode (its own landing-selector probe artifact). No capture, no report. |
| `--apply` | Same exclusion check first (FR-063/FR-064: if excluded, zero insurer journeys, one exclusion-stating report). Otherwise run every mapped insurer's own `Errand.run()` in apply mode, in sequence, recording each one's exit code; then run the comparison engine and write the report, once, regardless of individual insurer outcomes (as long as `feature_configs.insurance.companies` itself parsed - see below; no confirmed current-policy reference is required and its absence never blocks this step) |
| `--profile-dir`, `--headless`/`--show`, `--preview-dir`, `--no-screenshot` | Forwarded, unchanged in meaning, to every mapped insurer's own `Errand.run()` call, identically to how a single errand already accepts them |

### Startup sequence (every mode)

1. `config = load_config(overrides_from_own_argv)`.
2. `vault = open_vault(config)` (the orchestrator's own instance - see research.md D7's documented
   N+1-prompt residual).
3. `profile_doc = json.loads(vault.get_secret("profile"))`. On invalid JSON: this is `profile`'s
   own existing `ProfileError` (spec 001), not a new class this feature adds - print
   `REFUSED: {exc}`, exit `1`, no insurer's `Errand` is constructed.
4. `companies = capture.parse_companies(profile_doc.get("feature_configs", {}).get("insurance",
   {}).get("companies"))`. On `QuoteInputError` (missing `feature_configs`, missing `insurance`,
   missing or malformed `companies`): print `REFUSED: {exc}`, exit `1` - nothing downstream is
   trusted once this refuses (research.md D3, revised twice).
5. Find the targeted asset: the `vehicles` array element whose `type == "primary"` (FR-060).
   `excluded = policydoc.is_excluded(asset)` (data-model.md's `is_excluded`, FR-061). If `excluded`:
   in every mode, print one line naming the exclusion, construct zero insurers' `Errand` subclasses,
   and (apply mode only) write a report whose content states the exclusion (FR-064) - skip the
   remaining steps entirely for this invocation.
6. Partition `companies` into `mapped` (present in `WALK_REGISTRY`) and `unmapped` (not present).
7. Dispatch per mode, per the table above.

### Apply-mode sequence, after step 7 (only when the targeted asset is not excluded)

8. For each insurer in `mapped`, in the order `companies` lists them: construct that insurer's
   `Errand` subclass, call `.run(forwarded_argv)`, record `(insurer, exit_code)`. A non-zero
   `exit_code` is printed as `note: <insurer> walk failed (exit <code>)` - never the failed run's
   own stdout content re-printed a second time (that content already printed once, from the
   sub-run's own `errand.py` output, when it happened) - and the loop continues to the next
   insurer.
9. `failed = [insurer for insurer, code in results if read_freshest_capture(insurer, reports_dir)
   is None]` - an insurer counts as failed for the *report's* purposes only when it has never
   produced any capture, ever (not merely when *this run's* attempt returned non-zero - research.md
   D7/FR-021's "freshest capture regardless of which run produced it" rule).
10. `current_policy = policydoc.read_policy_reference("vehicles-primary", reports_dir)` (data-model.md;
    `None` when no cache file exists or it fails to parse - FR-057, FR-058, never a refusal here).
11. `comparison = compare.build_comparison(current_policy, {insurer: read_freshest_capture(insurer,
    reports_dir) for insurer in mapped if that capture exists})` - `build_comparison` itself
    branches on whether `current_policy` is `None` per FR-046.
12. `html = report.render_report(comparison, unmapped, failed)`;
    `path = report.write_report(html, reports_dir)`; print `REPORT {path}`.

**Exit code**: `0` when the report was written (step 12 completed, or the exclusion-case report
from step 5), regardless of how many individual insurers in step 8 failed and regardless of
whether a confirmed current-policy reference existed (spec FR-030, NFR-004); `1` when `profile`
itself was invalid JSON (step 3) or when `feature_configs.insurance.companies` was missing or
malformed (step 4) - never for a missing or unparseable current-policy cache, which is not a
refusal at all (step 10); `2` for a usage error (argparse's own handling of the standard mode
flags, unchanged from every other errand).

## 5. Report HTML structure

One self-contained HTML document, in this section order:

1. **Header**: report title, the UTC date it was generated, a one-line legend for the
   better/equal/worse/missing marks used in the table below.
2. **Recommendation banner**: the recommended insurer's name and normalized premium, and the rule
   trail (`ComparisonResult.rule_trail`) in full - or, when `ComparisonResult.recommended is None`
   (no captures exist yet for any mapped insurer), a plain statement that no comparison exists yet,
   never an empty or broken banner.
3. **Comparison table**: one column per entry in `ComparisonResult.ranked_quotes` plus one column
   for `current_policy` itself (always present, always first). When
   `ComparisonResult.has_current_policy` is `True`: one row per normalized coverage line that
   appears in `current_policy` or in any ranked quote (a line only a captured quote has, that
   `current_policy` lacks, still gets its own row - "missing" only ever describes a captured
   quote's cell, never `current_policy`'s own); the premium row shows each quote's
   `normalized_premium` alongside `current_policy`'s own raw `premium.amount` (already at its own
   term length by definition); every ranked quote's cells carry a better/worse/missing/equal mark.
   When `has_current_policy` is `False` (FR-047): the `current_policy` column's every row renders
   the fixed marker "no current policy on file" instead of a value; every coverage line that
   appears in any ranked quote still gets its own row, but no cell in any quote's own column
   carries a better/worse/missing/equal mark (`RankedQuote.line_classifications` is empty in this
   case, data-model.md) - each quote's own captured value is simply shown, unclassified; the
   premium row shows each quote's monthly-equivalent `normalized_premium` (FR-046) with no
   `current_policy` figure to compare it against.
4. **Unmapped insurers**: one row per entry in the `unmapped` argument, each stating only the
   insurer id and "not mapped yet" - no other column populated for that row.
5. **Failed insurers**: one row per entry in the `failed` argument, each stating only the insurer
   id and a fixed, value-free phrase ("no successful capture yet") - never a stack trace, never the
   sub-run's own exit code or error text.
6. **Provenance footer**: one line per quote actually included in the comparison table (not per
   unmapped or failed insurer, which have no capture to attribute), naming that quote's
   `fetched_at` timestamp, `source_url`, and `package` when the capture has one (FR-014) - and
   nothing else from that `QuoteCapture` (no premium, no coverage figure duplicated here; those
   already appear in the table above).

**Styling**: one `<style>` block in the document `<head>`, inline, no `@import`, no external
`url()` reference of any kind. Color marks (better/worse/missing/equal) use CSS classes defined in
that same block - no inline `style="color: ..."` attribute per cell, so the whole visual scheme
lives in one place and stays legible if the Director later opens the file's source directly.

**No JavaScript required**: the report is static markup; any JavaScript this feature might add in
a later polish pass (e.g. a column sort) MUST be optional and MUST NOT be required to read the
table's content or the recommendation - NFR-001 requires the page to render its full content with
JavaScript disabled.

## 6. Amendment to spec 004's vault CLI contract: `vault.py get NAME`

**Status**: already shipped, on `main`, as hotfix v0.0.4.1 (merge `f35988e`, commit `9cc3b20`),
ahead of and independent of this feature (research.md D12). This section records the shipped
contract because spec 005's own quickstart uses it; it is not new work this delivery's own
`tasks.md` builds or tests. It explicitly amends spec 004's own
`specs/004-age-vault/contracts/vault-and-cli.md` section 3 table, which did not originally include
a `get` subcommand.

| Subcommand | Precondition checked | Prompts | On success | On failure |
| :--- | :--- | :--- | :--- | :--- |
| `get NAME` | Vault file must exist; `NAME` must be present in the decrypted document | 1 (decrypt only, same as `list`) | Prints only `NAME`'s raw string value to stdout, followed by one newline, nothing else; exit `0` | Vault missing, wrong passphrase, or `age` unreachable: same value-free failure shape as `list` (`REFUSED: ...`, stdout, exit `1`); `NAME` absent from the decrypted document: `REFUSED: item '<name>' not in the vault`, exit `1` |

**The deliberate exception**: every other subcommand in spec 004's own table, and every note or
error message anywhere else in this repository's vault-touching code, is designed to never print
a value. `get` is the sole, deliberate exception, scoped to this one interactive, Director-invoked
terminal command (spec FR-039) - it exists specifically so the Director can read his own vault
item's current content and copy it elsewhere (an editor) to revise it, the way `vault.py set`
alone cannot support (`set` only ever writes a new value; it has no way to show the Director what
is there now to edit). No code under `headless/` calls `get`'s underlying function; it is reachable
only from `scripts/vault.py`'s own CLI (spec SC-014).

**This worktree's own gap**: `v0.0.5` forked from `main` before v0.0.4.1 landed, so `vault.py get`
does not run inside this specific worktree yet. See quickstart.md's own caution on this point
before attempting the round-trip scenario there.

## 7. `ProfileRegistry.get`: type-discriminated array addressing

New traversal rule inside `headless/profile.py` (research.md D13, spec FR-040 through FR-045).
General framework capability - every `registry:` source in every errand's `FieldPlan` gains this
for free, not only the Progressive walk's own paths.

| Traversal state | Behavior | Output / observable effect |
| :--- | :--- | :--- |
| Traversal reaches a list-valued node; the next path segment matches exactly one element's `type` field | Selects that element; traversal continues from it as the new current node | No error; the path resolves exactly as if the matched element had been reached by a plain dict key |
| ...matches zero elements' `type` fields | No element selected | Raises the existing `RegistryMissing(path)`, unchanged shape (FR-041) |
| ...matches more than one element's `type` field | No element selected | Raises `RegistryAmbiguous(path)` - value-free, naming only the path and the fact of duplication, never any matched element's own field content (FR-042) |
| An element in the list has no `type` field at all | Never a match candidate for any segment | Silently excluded from consideration - not an error (FR-043) |
| The dotted path is fully consumed while the current node is still a list or a dict | No further segment exists to select an element, or the resolved element is itself non-scalar | Raises the existing non-scalar `RegistryMissing`, unchanged from before this requirement (FR-044) |
| The current node is a `dict` (not a `list`) | Unchanged from spec 001 | Ordinary key lookup; `RegistryMissing` if the key is absent |
| The current node is a scalar and the path is fully consumed | Unchanged from spec 001 | Returns `str(node)` |

**`RegistryAmbiguous` in `Errand.run()`'s pre-session handling**: joins
`ConfigError`/`GateRefused`/`SecretMissing`/`RegistryMissing` in the existing tuple that prints
`REFUSED: {exc}` and exits `1` (FR-045) - the same treatment every other domain-shaped,
value-free-by-construction refusal in that tuple already receives.

**Example**: given a `profile` document whose `identities` array holds one element with
`"type": "self"` and one with `"type": "spouse"`, `ProfileRegistry.get("identities.self.
first_name")` resolves by: reaching the `identities` list, selecting the `"type": "self"` element,
then reading its own `first_name` key as an ordinary dict lookup. A document with two elements
both carrying `"type": "self"` would instead raise `RegistryAmbiguous("identities.self.
first_name")` at the selection step, before any `first_name` lookup is attempted.

## 8. `profile.template.json`: the drift test

Amends nothing in an existing contract - this is a new test-level contract this delivery adds
(research.md D14, spec FR-048/FR-049). Not a browser-touching contract: the test never opens a
vault, a browser, or prompts for a passphrase.

| Property | Value |
| :--- | :--- |
| File | `profile.template.json`, repository root - already exists on `main` (Amendment 5), not yet in this worktree |
| Content | Wholly synthetic values, in the exact `identities`/`addresses`/`vehicles`/`feature_configs` shape spec.md's Assumptions section describes (no `current_policy` field anywhere - D3, revised twice) |
| Test | Loads the file directly (`json.load`, a plain file read - no vault, no `get_secret`, no passphrase prompt); resolves every registry path any shipped walk in this delivery references (the Progressive walk's full field list, including `vehicles.primary.currently_insured`) through `ProfileRegistry.get`, exercising section 7's own array-addressing rule |
| On a path that fails to resolve | The test fails - this is the drift guard: a walk change referencing a field the template does not define cannot pass the suite |
| This delivery's own obligation | Never recreate or duplicate the file (FR-049); if recon proves a new field is needed, extend the one template file in the same change that wires the walk to reference it |

## 9. `scripts/policy_extract.py`: extraction, confirmation, and cache

Not an `Errand` subclass, not a browser errand - a maintenance-adjacent script, the same category
`scripts/vault.py` occupies (research.md D15).

| Step | Behavior |
| :--- | :--- |
| Startup | `vault = open_vault(load_config())`; `profile_doc = json.loads(vault.get_secret("profile"))` (one passphrase prompt total for the whole run - simpler than `quote_compare.py`'s own N+1 residual, since this script never constructs a second vault instance) |
| Asset discovery | Iterate `profile_doc.get("addresses", []) + profile_doc.get("vehicles", [])`; for each element, skip if `policydoc.is_excluded(element)` (FR-062, no note) or if `policy_doc` is absent; otherwise attempt extraction |
| Extraction | `candidate = policydoc.extract_candidate(Path(element["policy_doc"]))`; `None` (unreadable PDF, or zero coverage lines parsed) moves on to the next asset with no error (FR-058) |
| Confirmation | `confirmed = policydoc.confirm_candidate(candidate)` - prints the candidate, prompts accept-or-correct (FR-053, FR-054); `None` on decline means no cache write, not an error |
| Cache write | On a non-`None` `confirmed`: `asset_key` derived from the array name and the element's own `type` (data-model.md); `policydoc.write_policy_reference(PolicyReference(confirmed, source_path=element["policy_doc"], confirmed_at=<utc now>), reports_dir)` |
| CLI | `python scripts/policy_extract.py` (no argument): every eligible asset, in order. `python scripts/policy_extract.py <asset.path>` (e.g. `vehicles.primary`): only that one asset, for a targeted re-run after fixing a bad PDF or a bad correction |
| Exit code | `0` on completion, regardless of how many assets were skipped, declined, or extracted with zero lines (none of those are failures); non-zero only for a usage error or a vault-level refusal (a missing vault file, a wrong passphrase) |

## 10. The `"n/a"` sentinel

One function, two callers (data-model.md's `is_excluded`), so this convention's meaning lives in
exactly one place (spec FR-061).

| Field | Value | Meaning |
| :--- | :--- | :--- |
| `currently_insured` or `policy_doc` absent | (no key at all) | No data yet - not excluded, simply unknown; `policy_extract.py` skips it the same way as an explicit exclusion, but for a different reason and with a different message shape |
| `currently_insured` or `policy_doc` equal to `"n/a"` | the literal string `"n/a"` | Explicit, Director-decided exclusion - this asset is out of scope for every insurance feature, permanently, until the Director changes the value himself |
| Any other string | a real value | Used normally: `policy_doc` as a real PDF path, `currently_insured` as a real yes/no answer a walk may fill |

No consumer (a `FieldPlan`, `scripts/policy_extract.py`, `scripts/quote_compare.py`) ever branches
on `"n/a"` by accident - the check is always an explicit `== "n/a"` comparison, never a truthiness
or "looks like a path" heuristic that could misfire on a real value that happened to be short.

## 11. Amendment to spec 004's vault CLI contract: `vault.py verify`

**Status**: shipped, on `main`, as hotfix v0.0.4.2, ahead of and independent of this feature -
recorded here as fact, the same way section 6 records `get`. Not a `tasks.md` item.

| Property | Value |
| :--- | :--- |
| Precondition | `profile.template.json` must exist; refuses before any passphrase prompt if it does not |
| Prompts | 1 (decrypt `profile`, same as `list`/`get`) |
| Check | Structural comparison of the decrypted `profile` against `profile.template.json`: unknown field -> ERROR; template field absent from the real document -> WARN; a kind mismatch (e.g. a string where the template has an object) -> ERROR; a missing or duplicate `type` discriminator on an array element -> ERROR; an unknown array element `type` -> checked against that array's first template element's own shape (accepted, not an error); any `_`-prefixed key -> ignored entirely |
| Output | Value-free `SEVERITY path: reason` lines only - never a field's own value |
| Exit code | `0` clean or warnings-only; `1` any error found; refuses (no prompt at all) when the template file itself is missing |
| Relationship to this delivery's own drift test (FR-048) | Complementary, not overlapping: `verify` checks the Director's real, live `profile` data against the template; the drift test checks this delivery's own shipped *code* (its registry paths) against the same template - one guards data, the other guards code, both against one shared contract file |

## 12. Amendment to spec 004's vault CLI contract: `vault.py set`'s piped-stdin path and 1024-character refusal

**Status**: already shipped, on `main`, as hotfixes v0.0.4.3 (merge `a7e2e48`, commit `4a17be6`)
and v0.0.4.4 (merge `d55bc80`, commit `2d7799a`), ahead of and independent of this feature
(research.md D17). This section records the shipped contract because spec 005's own quickstart
profile-editing round trip depends on the piped-stdin path, not the hidden-prompt path, for a
document this feature's own array-and-`feature_configs` shape produces; it is not new work this
delivery's own `tasks.md` builds or tests. It explicitly amends spec 004's own `specs/004-age-vault/
contracts/vault-and-cli.md` section 3 table, which did not originally describe a stdin-piped input
path or a length refusal for `set`.

| Input path | Behavior | On success | On failure |
| :--- | :--- | :--- | :--- |
| Interactive (`python scripts/vault.py set NAME`, a real terminal) | Prints the pipe-command hint (`pbpaste \| python scripts/vault.py set NAME`) before prompting; hidden `getpass` prompt reads one value | Value stored, re-encrypted, exit `0` | A value of 1024 or more characters: `REFUSED: value is 1024+ characters and may have been truncated by the terminal's input limit; pipe it instead: pbpaste \| python scripts/vault.py set NAME`, exit `1` - never stored |
| Piped stdin (`pbpaste \| python scripts/vault.py set NAME`; Windows: `Get-Clipboard \| python scripts\vault.py set NAME`) | Reads the whole of stdin as the value, trailing newline stripped, no length limit | `value read from stdin (piped)` prints, then value stored, re-encrypted, exit `0` | Empty stdin: `REFUSED: empty value on stdin`, exit `1` |

**Why this exists**: macOS terminals cap one canonical (line-buffered) input line at 1024 bytes; a
value pasted past that boundary into a hidden prompt either truncates silently or stalls
indefinitely, verified empirically on the Director's own machine. `profile.template.json`'s own
shape (D14) is 1235+ characters as raw JSON - past that boundary by construction, not by any
unusual editing choice - so spec 005's own quickstart profile-editing round trip (Scenario 1) MUST
use the piped path, never the interactive one, for `set profile`.

**This worktree's own gap**: `v0.0.5` forked from `main` before v0.0.4.3/v0.0.4.4 landed, so
neither the piped-stdin acceptance nor the 1024-character refusal runs inside this specific
worktree yet - the same gap section 6 already documents for `get`.
