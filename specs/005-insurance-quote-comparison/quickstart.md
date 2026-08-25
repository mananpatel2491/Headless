# Quickstart: Insurance Quote Comparison

**Feature**: 005-insurance-quote-comparison | **Date**: 2026-08-25 (amended 2026-08-25, eight
rounds - see spec.md's own amendment note)

Runnable validation scenarios that prove the feature end-to-end, once implemented. Contracts are
in [contracts/walk-capture-report.md](contracts/walk-capture-report.md); entities in
[data-model.md](data-model.md).

**Every scenario number below is stable and final** - `tasks.md` cross-references Scenario 3,
Scenario 5, and Scenario 7 by number; no amendment folded into this document renumbered a
scenario, only revised a scenario's own content where the underlying design changed.

**Scenarios 1 onward touch `~/.headless/` (or wherever `HEADLESS_AGE_FILE` points), prompt for a
real passphrase on a real terminal, and - from Scenario 4 onward - drive a real browser against
the real Progressive site. This is Director-run UAT, not something a builder or an automated agent
executes on the Director's behalf: a human has to be at the keyboard for the vault, and a human
has to be the one who presses Enter at every `HumanStep` and confirms every extraction candidate
this feature's own design requires.**

## Prerequisites

- From the worktree root, the existing `.venv`, plus `pip install -r requirements.txt` for
  `pypdf` (new this feature):
  ```bash
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- A vault already initialized (spec 004) with a `profile` item seeded. If not yet done, follow
  spec 004's own quickstart first.
- `scripts/vault.py get NAME`, `scripts/vault.py verify`, and `profile.template.json` (repository
  root) all already exist - shipped independently of this delivery, on `main` (research.md D12,
  D14). **This worktree's own `v0.0.5` branch forked before any of them landed and does not have
  them yet.** Run Scenario 1 from a clone or worktree that already has them (`main`, or a worktree
  created after they merged), not from this `v0.0.5` worktree, until it merges forward from or is
  rebased onto current `main`.
- `profile.template.json` is the enforced contract for `profile`'s shape (spec FR-048/FR-049): a
  wholly synthetic example of every field this delivery's shipped walks reference, kept current by
  its own drift test. Open it directly for the authoritative, up-to-date example - this document
  quotes only a short excerpt below, not the whole file, so the two never have a chance to drift
  from each other.

## Scenario 1: seeding `profile`'s household, insurance, and policy-document data (US2, US4)

`profile` holds three top-level JSON arrays (`identities`, `addresses`, `vehicles`, each element
carrying a `type` field) and a top-level `feature_configs` object
(`feature_configs.insurance.companies`) - not separate vault items (research.md D3, revised
twice). **There is no `current_policy` field anywhere.** Each insured asset instead carries its
own `policy_doc` (a filesystem path to that asset's policy PDF) and `currently_insured`.

```bash
python scripts/vault.py get profile
```

One passphrase prompt, then the current `profile` document's raw JSON prints to stdout - copy it
into an editor (Sublime, or any editor of choice).

Edit the copied document to match `profile.template.json`'s own shape (open that file directly for
the full, authoritative example). A short excerpt, showing only the fields the Progressive walk
references - never paste real data over this, and never paste your own real edited document into
any file this repository tracks. `policy_doc` here points at wherever your own real auto policy
PDF actually lives on disk (an absolute path); the example below uses a placeholder path only:

```json
{"identities": [{"type": "self", "first_name": "Test", "last_name": "Testerson", "dob": "1990-01-01", "email": "director@example.com", "phone": "555-0100", "licence": {"number": "D0000000", "state": "CA"}}], "addresses": [{"type": "home", "line1": "1 Example Street", "city": "Sampletown", "state": "CA", "zip": "90000", "dwelling_type": "single_family", "currently_insured": "n/a", "policy_doc": "n/a"}], "vehicles": [{"type": "primary", "vin": "1SAMPLE0VIN000001", "year": "2020", "make": "Sample", "model": "Model X", "currently_insured": "yes", "policy_doc": "/Users/example/Documents/auto-policy.pdf"}], "feature_configs": {"insurance": {"companies": ["progressive"]}}}
```

To exercise User Story 4's unmapped-row behavior later, list a second, deliberately unmapped
insurer id in `feature_configs.insurance.companies` instead: `["progressive", "geico"]`.

**The `"n/a"` sentinel**: the example above sets `addresses.home`'s `currently_insured` and
`policy_doc` to the literal string `"n/a"` - this delivery's auto-only scope never touches home
insurance, and `"n/a"` says so explicitly rather than leaving the fields simply absent (which
would mean "no data yet," a different state - spec FR-061). `vehicles.primary` carries a real
`policy_doc` because that is the one asset this delivery's own comparison targets (spec FR-060).

```bash
python scripts/vault.py set profile
```

At the hidden prompt, paste the edited document (one line), then confirm the passphrase again at
`age`'s own re-encrypt prompt.

**Caution**: do not save the plaintext document to a file at any point in this round trip - copy
it from the terminal, edit it in the editor's own in-memory buffer, and paste it back; saving it
to disk (even temporarily, even outside the repository) creates a plaintext copy of the vault's
own content the passphrase gate exists to prevent. Close the editor's unsaved buffer when done -
most editors, including Sublime, cache an unsaved buffer's content to their own local session-
restore state, which can persist it to disk on your behalf without an explicit save; closing the
buffer (not just the window) after the paste-back is the only way to be sure that cache is cleared.

## Scenario 2: confirming `profile` is readable and structurally sound (US1, US4)

```bash
python scripts/vault.py list
```

Expected: `profile`, and nothing else - there is no separate `insurers`/`current_policy`/
`insurance` item to list any more (research.md D3, revised twice). One passphrase prompt.

```bash
python scripts/vault.py get profile
```

Expected: the document prints back exactly as pasted in Scenario 1.

```bash
python scripts/vault.py verify
```

Expected: a clean or warnings-only report (exit `0`) - a structural comparison of the real,
decrypted `profile` document against `profile.template.json` (an unknown field is an ERROR, a
template field your document is missing is a WARN, a wrong kind or a missing/duplicate array
`type` is an ERROR). Run this any time after editing `profile`, and always before the first quote
run of a session - it catches a shape mistake before it becomes a confusing `REFUSED: registry
path ...` three steps later. `verify` (real data vs. the template) and this delivery's own drift
test, `pytest -k template` (this delivery's shipped code vs. the same template), are a
complementary pair, not overlapping checks.

## Scenario 3: the landing-page check (US2)

```bash
python scripts/quote_compare.py --check
```

Expected: a `progressive` section reporting the two landing selectors already verified before this
feature was scoped (`#zipCode_mma`, `#qsButton_mma`) as found; if `feature_configs.insurance.
companies` also names an unmapped id (`geico` in Scenario 1's second example), a line stating it
has no registered walk and was not probed. No window opens unless `--show` is passed. This step
never touches any current-policy reference (comparison has nothing to do with a landing-selector
probe).

## Scenario 4: the masked preview, every mapped insurer (US1, US2, US4)

```bash
python scripts/quote_compare.py
```

Expected: no window opens (default, invisible preview, same as every prior errand). For
`progressive`, a preview artifact under `previews/` showing the ZIP field's masked value (resolved
from `registry:addresses.home.zip`) and every other declared step (the landing click, any
`HumanStep`s and the `CaptureStep` the implementation delivery's recon actually proved) listed by
name only - no navigation past the landing page happens (spec SC-001). A summary line states which
`feature_configs.insurance.companies` entries are unmapped, if any. No capture is written and no
report is written in preview mode.

## Scenario 5: the real apply run - the passphrase gate, the HumanStep etiquette, the capture (US1, US2, US3)

```bash
python scripts/quote_compare.py --apply
```

Expected sequence, in order:

1. One or more passphrase prompts (`profile`'s own read for `feature_configs.insurance.
   companies`, then a further prompt from Progressive's own `Errand.run()` internally resolving
   its own registry paths, e.g. `addresses.home.zip` - see research.md D7's documented residual:
   this is not collapsed to a single prompt in this delivery).
2. No visible window yet - Chrome launches hidden, as every apply run already does.
3. The ZIP field fills and the quote-start button clicks, silently, with the window still hidden.
4. At the first point recon determined cannot be automated, the window surfaces and the terminal
   prints `Your turn: <instruction>` - read the instruction, complete that one step by hand in the
   now-visible window (a consent click, a verification code, whatever recon found), then press
   Enter in the terminal to continue. **Do this for every `HumanStep` the walk declares, in order**
   - the walk resumes automatically after each Enter press.
5. Once every `HumanStep` has been answered, the walk continues on its own to the quote page and
   reads it - no further Director action needed until the trailing handoff.
6. At the very end, one more `Your turn: <trailing HANDOFF text>` prompt - press Enter to finish.
7. `reports/captures/progressive-<timestamp>.json` now exists, holding the captured premium and
   coverage lines - never a full page dump, only the named extractor fields.
8. `reports/quote-comparison-<date>.html` now exists - this is the deliverable.

**Watch for**: a `note: capture field '<name>' not found (selector missing)` line during step 5 -
not a failure; one coverage line's selector did not resolve on the quote page this time, and the
comparison engine will show that line as missing for this quote rather than guessing a value.

## Scenario 6: opening the report (US3)

Open `reports/quote-comparison-<date>.html` directly in a browser - no server, no network
connection needed. Expected: a table with the current-policy reference's own column (or, if
Scenario 8 has not yet been run for `vehicles.primary`, a "no current-policy reference for
vehicles.primary - run scripts/policy_extract.py" marker in that column) plus one column per
successfully captured quote, each coverage-line cell marked better/worse/missing/equal (when a
confirmed reference exists) or shown unclassified (when it does not), a premium row, a
recommendation banner naming the top-ranked quote and the rule that produced it, one row for any
unmapped insurer, and a footer naming each included quote's capture timestamp and source URL.

## Scenario 7: one insurer's failure does not stop the others (US4)

With `feature_configs.insurance.companies` naming more than one mapped insurer (only reachable
once a second insurer has its own future spec and its own registered walk - not exercisable with
this delivery's own single mapped insurer, Progressive), a `--apply` run where one insurer's walk
hits a bot block or a drifted selector still produces a report: the failing insurer appears as a
value-free "no successful capture yet" row (or, if an older capture exists from a prior run, that
older capture is used instead, with its own older timestamp visible in the footer), and the report
still recommends the best of whatever succeeded.

## Scenario 8: extracting the current-policy reference from a real PDF (US3)

The report only compares against a real reference once one has been extracted and confirmed.

```bash
python scripts/policy_extract.py
```

Expected: one passphrase prompt (reading `profile` once); for `vehicles.primary` (the one asset
with a real `policy_doc` in Scenario 1's example), a candidate `CurrentPolicy`-shaped document
prints to the terminal - your own real policy data, on your own terminal, the same deliberate
exception `vault.py get` already established. Review it against your actual policy PDF:

- To accept it as printed: confirm at the prompt. `reports/policy/vehicles-primary.json` is
  written, mode `0600`, holding the confirmed figures plus provenance (`source_path`,
  `confirmed_at`).
- To correct it: choose the correction path, then paste a corrected JSON document (the same
  `CurrentPolicy` shape - `insurer`, `premium`, `coverages`) at the follow-up prompt.
- To decline entirely: nothing is cached, and this is not an error - re-run the command later
  after fixing the source PDF, or once the heuristics themselves are tuned (research.md D15's own
  accepted residual: extraction quality against a real PDF is proven only by this first real run).

`addresses.home` (its `policy_doc` set to `"n/a"` in Scenario 1's example) is skipped silently -
no candidate, no prompt, no note (spec FR-062).

Re-run `scripts/quote_compare.py --apply` (Scenario 5) afterward and re-open the report (Scenario
6): the current-policy column now shows real figures and real classifications instead of the "no
current-policy reference" marker.

## Scenario 9: the excluded-asset case (US3, US4)

Repeat Scenario 1 with `vehicles.primary`'s own `currently_insured` or `policy_doc` also set to
`"n/a"` (an unusual state for this delivery's own real use case, but the mechanism is generic and
must be proven). Run:

```bash
python scripts/quote_compare.py --apply
```

Expected: one clear, informative line states `vehicles.primary` is excluded per the Director's own
profile setting; zero insurer journeys run (no window, no `Session`, no `Config` resolution for
any mapped insurer); the report still writes, but its content states the exclusion in place of a
comparison table (spec FR-063, FR-064). Re-run Scenario 1 afterward to restore a real
`currently_insured`/`policy_doc` pair for the remaining scenarios below.

## Scenario 10: malformed input refuses cleanly (US1, US4)

```bash
python scripts/vault.py get profile
```

Copy the output, then edit `feature_configs.insurance.companies` to something invalid (a string
instead of an array, for example), and `vault.py set profile` it back.

```bash
python scripts/quote_compare.py --apply
```

Expected: `REFUSED: ...` naming only `feature_configs`/`insurance`/`companies` (never the pasted
content), exit `1`, no window opens, no insurer's `Errand` is constructed at all. Re-run Scenario 1
afterward to restore a working document.

## Scenario 11: unit-level proof, zero browser, zero prompts (SC-001, SC-004, SC-005, SC-006, SC-007, SC-008, SC-009, SC-016 through SC-023)

```bash
python -m pytest -q tests/test_steps.py tests/test_capture.py tests/test_compare.py \
  tests/test_report.py tests/test_insurers_progressive.py tests/test_quote_compare.py \
  tests/test_profile.py tests/test_policydoc.py
python -m pytest -q tests/test_errand.py -k walk
python -m pytest -q tests/test_session.py -k "click or capture"
```

Expected: every test passes with zero browser launches and zero passphrase prompts - every walk,
capture, comparison, registry-traversal, and extraction test uses a fixture `Session`/fake data, a
fixture JSON document, or a fixture PDF/`input_fn`, never the real `age` binary, a real Chrome
process, or a real terminal, matching the convention `tests/test_secrets.py` and
`tests/test_vault.py` already established for `AgeBackend` in spec 004.

## Scenario 12: report has zero external references (SC-002)

```bash
grep -E 'https?://|<script src=|<link rel="stylesheet" href=' reports/quote-comparison-*.html
```

Expected: no match outside the provenance footer's own plain-text `source_url` values - the
automated proof is `tests/test_report.py`'s own SC-002 test; this grep is a hand-run sanity check
against a real report, not a substitute for that test.

## Scenario 13: fixture hygiene (all user stories)

Every JSON example in this document, `profile.template.json` itself, and every fixture this
feature's own tests use (including any fixture PDF), is wholly synthetic: no real premium, no real
policy number, no real insurer-account identifier. Confirm this holds for the implementation
delivery's actual test fixtures:

```bash
python scripts/scan_secrets.py --paths tests/test_capture.py tests/test_compare.py tests/test_report.py tests/test_profile.py tests/test_policydoc.py
```

Expected: clean - zero findings.

## Scenario 14: revising `profile` again - a field recon proves is needed, or fixing a wrong path (US1, US2)

Implementation-time recon (spec FR-032) may find the Progressive walk needs a field
`profile.template.json` does not yet define, or the document may simply have a path wrong (a
`REFUSED: registry path ...` at run time, or a `vault.py verify` ERROR). Either way, the fix is
Scenario 1's own round trip, applied again: `vault.py get profile` -> edit -> `vault.py set
profile` -> `vault.py verify` to confirm the fix landed cleanly.

**If the fix was adding a genuinely new field a shipped walk now references**: the same change
must also extend `profile.template.json` itself at the repository root (spec FR-049) - the drift
test (FR-048) fails otherwise, on every future run of the unit suite, not only this one.

Then re-run the command that originally failed.

## Scenario 15: commit gate (all user stories)

```bash
python -m pytest -q
python scripts/verify_structure.py
git add -A
python scripts/scan_secrets.py --staged
```

Expected: the full unit suite passes (including this feature's new tests), `verify_structure.py`
reports SUCCESS with every changed/new file accounted for in `Project_Structure.md`'s Changelog,
and `scan_secrets.py --staged` reports clean. Deferred to the implementation delivery - this
spec-authoring delivery does not stage or run the gate, matching every prior spec's own precedent
of leaving this to `/speckit-implement`.

## `rm -rf previews` note

`previews/` stays exactly as disposable as it has always been - delete it freely at any time.
`reports/` is different: `reports/quote-comparison-*.html` is the feature's own deliverable,
`reports/captures/*.json` is the capture history the comparison engine draws on, and
`reports/policy/*.json` is the confirmed current-policy reference - do not routinely delete any of
these the way `previews/` is deleted. A stale capture or a stale policy reference simply means the
next comparison uses an older, still-honestly-timestamped one, or none.

## The REFUSED-path fix recipe

Every `REFUSED: registry path '<dotted.path>' not found or not a scalar` this feature can produce
(from Progressive's own `FieldPlan` resolution, e.g. `registry:addresses.home.zip`, or
`registry:vehicles.primary.currently_insured`) means one of: the `profile` document does not have
that exact dotted path; the path resolves to a list or a dict rather than a scalar (FR-044); or,
for a path that crosses an array (`identities`/`addresses`/`vehicles`), the segment after the
array either matched no element's `type` field (add one) or matched more than one
(`REFUSED: ... matches more than one element by type` - deduplicate the `type` values, FR-042).
Fix any of these with Scenario 14's own `get` -> edit -> `set` -> `verify` round trip.

A `REFUSED: ...` naming `feature_configs`, `insurance`, or `companies` means the same class of
problem, one level up in the same document - the same round trip fixes it.

A missing or wrong current-policy figure in the report is never a `REFUSED:` at all - it means
`scripts/policy_extract.py` (Scenario 8) has not yet been run, or its own candidate was declined -
re-run it, review the candidate against the real PDF, and confirm or correct.
