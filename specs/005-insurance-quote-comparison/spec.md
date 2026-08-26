# Feature Specification: Insurance Quote Comparison

**Feature Branch**: `v0.0.5` (spec directory `005-insurance-quote-comparison`)

**Created**: 2026-08-25

**Status**: Draft (amended 2026-08-25, nine rounds, mid-delivery - see the amendment note below)

**Input**: User description: "The feature is not to get a quote from Progressive, but get quotes
from multiple insurance companies. My profile will contain the list of insurance companies I
like and for each company, the goal is to go through their quotation journey and fetch the
quote. You will also have a reference of my existing quote (the one I am using right now) so
you can compare each benefit line by line, and your goal is to recommend me the best quote to
go for, showing the comparison in nice pretty HTML."

**Amendment note**: this spec was drafted, then amended nine times in the same session as the
Director's own live profile document and tooling evolved. Every FR number below is final and
continuous (FR-001 through FR-066, plus FR-039b and FR-039c, none renumbered); FR-046 and FR-047
were inserted mid-list - their own amendment round decided the comparison engine and report
generator each needed a documented no-current-policy fallback after FR-021/FR-025 had already been
assigned, so they were given the next unused numbers rather than renumbering anything around them,
the same never-renumber discipline every amendment below follows. Where a later amendment corrected
an earlier one's design, the earlier FR's own text was rewritten in place (never left standing
alongside a contradicting later FR) and the correction is recorded in research.md under its own
dated decision. The nine amendments, briefly: (1) `scripts/vault.py get NAME` and `scripts/vault.py
verify`, shipped elsewhere as hotfixes v0.0.4.1 and v0.0.4.2, recorded here as fact; (2) an initial
registry reshape proposal (nested blocks under `vehicle`/`spouse`/`property`), superseded by (4);
(3) `identity.currently_insured` joins the Progressive walk, and `spouse`/rental-property data is
seeded but not wired in this delivery; (4) the Director's actual live profile document turned out
to use three top-level JSON arrays (`identities`, `addresses`, `vehicles`), each element
discriminated by a `type` field, resolved through `ProfileRegistry`'s own type-discriminated array
addressing - this array shape is what every FR below describes for `identities`/`addresses`/
`vehicles`, but the single `insurance` object this round originally proposed alongside it
(replacing the separate `insurers`/`current_policy` vault items this spec first proposed) is itself
superseded by (6) and (8) below; (5) `profile.template.json`, a repository-root file shipped on
`main` (not yet in this worktree), is the enforced contract for that shape, and this delivery's own
test suite is required to prove every path a shipped walk references actually resolves against it;
(6) `current_policy` is deleted from `profile` entirely - each insured asset's own `policy_doc` PDF
path is extracted and Director-confirmed instead (`scripts/policy_extract.py`,
`headless/policydoc.py`), and the insurer list moves one level deeper, to
`feature_configs.insurance.companies`; (7) the literal string `"n/a"` in `currently_insured` or
`policy_doc` becomes a defined, Director-decided exclusion sentinel, distinct from the field being
merely absent; (8) `addresses[]` gains a `dwelling_type` field and a third element type, `"work"`,
both seeded now for a future feature and excluded from this delivery's own scope by their own
sentinels; (9) `scripts/vault.py set`'s hidden prompt is confirmed to refuse any interactive value
of 1024 or more characters (the terminal's own canonical input-line limit) and to accept the same
value instead over piped stdin - both already shipped elsewhere as hotfixes v0.0.4.3 and v0.0.4.4,
recorded here as fact (FR-039c) because this feature's own quickstart profile-seeding round trip
needs the pipe path, not the hidden-prompt path, for a document this delivery's own shape produces.

## Why

The Director renews an insurance policy the same way most people do: by trusting whichever
quote he already has, because getting a second opinion means repeating a slow, form-heavy
online journey once per company he is willing to consider. Headless already proves it can walk
a single page and fill a single form (spec 001); this feature is the first to need more than
that - a real quotation journey is several pages deep, includes at least one step no script can
or should automate (a consent screen, a phone verification, a CAPTCHA), and only pays off once
its result is compared against something the Director already has, line by line, not just
glanced at.

That shape drives the scope of this delivery. Spec 005 is not "get a Progressive quote." It is
the reusable program that any future insurer walk plugs into: a walk framework that can cross a
multi-page journey and hand control to the Director mid-walk without losing its place, a
registry that can address one element of a household's data (a spouse, a second address, a
second car) without a code change per element, a capture model that turns a quote page into
structured data, a deterministic comparison engine that never lets an LLM touch a premium
figure, and an HTML report the Director can read offline. Progressive is the one insurer this
delivery maps end to end, because it is the one site already recon'd and the one account the
Director holds today. Every other insurer on his list is a "not mapped yet" row in the same
report until its own future spec does for it what this one does for Progressive.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The walk framework crosses a multi-page journey with human handoffs (Priority: P1)

An errand is no longer limited to one form on one page. It can declare an ordered walk of steps -
fill a field, click a wizard button, hand off to the Director for a step nothing should
automate, or read structured data off a page - and the framework carries that walk through every
mode (preview, apply, check) the way today's single-page errands already do, without breaking
any errand that has not been rewritten as a walk.

**Why this priority**: every other story in this feature depends on this one existing first. A
comparison engine has nothing to compare without a capture, a capture has nothing to read without
a walk that reaches the quote page, and a walk cannot reach the quote page without a way to cross
a consent screen or a phone-verification step that no automated click should ever attempt.

**Independent Test**: construct a fixture errand whose `walk()` returns one `FieldPlan`, one
`ClickStep`, one `HumanStep`, and one `CaptureStep` against a fake `Session`; run it in preview
mode and confirm only the initial page load and the `FieldPlan`'s masked value appear in the
preview artifact, with zero click, handoff, or capture calls recorded; run it in apply mode and
confirm all four steps fire in declared order, with the handoff printing the exact instruction
text and the run pausing for the fixture's confirmation callable.

**Acceptance Scenarios**:

1. **Given** an errand whose `plan()` is unchanged and whose `walk()` is not overridden, **When**
   it runs in any mode, **Then** the default `walk()` implementation returns exactly the same
   steps `plan()` already would, and every existing behavior (preview masking, apply filling, the
   pre-resolution loop, the trailing handoff) is identical to today - `probe.py` and every prior
   spec's own errand are unaffected by this feature existing.
2. **Given** a walk containing a `ClickStep`, **When** the run is in preview or check mode,
   **Then** the click is never attempted; the run goes only as far as the initial page load.
3. **Given** a walk containing a `ClickStep`, **When** the run is in apply mode, **Then** the
   click fires exactly once, through the same session that already owns the page, with no retry
   on failure.
4. **Given** a walk containing a `HumanStep`, **When** apply mode reaches it, **Then** the browser
   window is surfaced (if it was not already), the exact line `Your turn: <instruction>` prints,
   the run waits for the Director to press Enter, and the walk then continues with the next step -
   the run does not end at a `HumanStep` the way it ends at today's trailing handoff.
5. **Given** a walk containing two `HumanStep`s, **When** apply mode reaches the second one,
   **Then** the window is not hidden or minimized again between the two - once the Director is
   engaged, the window stays visible for the rest of that run.
6. **Given** a walk containing a `CaptureStep`, **When** apply mode reaches it, **Then** every
   named extractor is read from the page into a flat field-name-to-text mapping, with no click and
   no typed value anywhere in that step.
7. **Given** any plan source inside a walk (a `FieldPlan` with a `registry:` or `secret:` source),
   **When** the run starts in any mode, **Then** it is resolved before any browser window opens,
   exactly as the existing pre-resolution loop already guarantees for `plan()` - `ClickStep`,
   `HumanStep`, and `CaptureStep` carry no source and are never part of that loop.

---

### User Story 2 - The Progressive journey is captured end to end (Priority: P1)

The one insurer this delivery maps: starting from Progressive's public quote-start page, filling
what the Director's profile already supplies, crossing whatever the funnel requires by hand where
automation should not or cannot go, and finishing at a structured capture of that quote's premium
and coverage lines - never a purchase, never further than a quote.

**Why this priority**: without one real, working insurer walk, the framework from User Story 1 is
unproven and the comparison engine from User Story 3 has nothing real to compare. This is the
delivery's only end-to-end proof that the shape actually works against a live site, not just a
fixture.

**Independent Test**: with `"progressive"` added to the Director's `profile` document's
`feature_configs.insurance.companies` array, run `scripts/quote_compare.py --check` and confirm
the landing-page
selectors (`#zipCode_mma`, `#qsButton_mma`) both resolve; run `--apply` by hand (Director UAT,
since it needs the passphrase and a real terminal) and confirm a
`reports/captures/progressive-<timestamp>.json` file appears, shaped per data-model.md's
`QuoteCapture`.

**Acceptance Scenarios**:

1. **Given** the Director's `identities.self.first_name` and related registry paths resolve
   (Amendment 4's array-element addressing, FR-040 through FR-044), **When** the Progressive walk
   runs in apply mode, **Then** the ZIP field (`#zipCode_mma`, from `registry:addresses.home.zip`)
   fills and the quote-start button (`#qsButton_mma`) clicks, matching the landing-page selectors
   already verified before this feature was scoped.
2. **Given** the funnel reaches a point implementation-time recon proves cannot be automated (a
   consent screen, a CAPTCHA, a phone-verification step), **When** apply mode reaches it, **Then**
   a `HumanStep` bridges it - the walk never guesses at, or ships, a selector recon did not prove.
3. **Given** the walk reaches the quote page, **When** its `CaptureStep` runs, **Then** the
   premium and every coverage line the page exposes are read into a `QuoteCapture` and written to
   `reports/captures/progressive-<timestamp>.json`; the walk never clicks anything past that page.
4. **Given** Progressive's funnel refuses headless Chrome at some point during implementation-time
   recon, **When** that refusal is discovered, **Then** the shipped walk still works: every step
   recon actually proved resolves ships, every step recon could not cross becomes a `HumanStep`,
   and the refusal itself is recorded as evidence (research.md) for the repository's standing
   headless-user-agent question - the walk is never shipped shorter than recon proved just to
   avoid recording an inconvenient result, and never shipped with an unproven selector to look
   more complete than it is.
5. **Given** `--check` runs before a working vault or before recon exists for a funnel page,
   **When** it probes, **Then** it reports only the landing-page selectors this delivery actually
   ships as `dependencies` - it never probes a page recon has not reached.
6. **Given** an "are you currently insured?" question on a page implementation-time recon finds
   the Progressive walk reaching, **When** apply mode reaches that step, **Then** it fills or
   selects the answer from `registry:vehicles.primary.currently_insured` as a `FieldPlan`, never a
   `HumanStep` - this is the one funnel field beyond the landing page's ZIP this delivery
   pre-authorizes a registry-sourced answer for, still gated by the same "unproven selector never
   ships" rule as every other step past the landing page.
7. **Given** `profile.template.json` (the repository-root file that is the enforced contract for
   `profile`'s shape, Amendment 5), **When** the unit suite runs, **Then** every registry path the
   shipped Progressive walk references - including `vehicles.primary.currently_insured` - resolves
   against that template through `ProfileRegistry`, proven by a dedicated drift test (FR-048); a
   walk change referencing a field the template does not define fails that test.

---

### User Story 3 - The comparison engine and HTML report recommend a quote (Priority: P1)

Every captured quote is compared, line by line, against the Director's current policy, using
rules a person can audit - never a language model's judgment - and the result is one
self-contained HTML page the Director can open offline: a table with one column per quote, one
row per coverage line, a premium row, a recommendation with the reasoning that produced it, and a
provenance footer naming exactly when and where each number came from.

**Why this priority**: this is the actual deliverable the Director asked for. A framework that
can cross a funnel and a capture that can read a quote page are worthless without this - the
whole point was never "get a quote," it was "tell me which quote to go for and show your work."

**Independent Test**: build a small set of synthetic `QuoteCapture` fixtures and a synthetic
`current_policy`, run the comparison engine directly (no browser, no vault, no network), and
confirm the rendered HTML contains one column per fixture quote, correctly marks each coverage
cell better/worse/missing/equal, and recommends the fixture quote the ranking rule says it should.

**Acceptance Scenarios**:

1. **Given** a captured quote whose coverage lines are named differently from `current_policy`'s
   own names for the same coverage (e.g. "Bodily Injury Liability" vs. "BI"), **When** the
   comparison engine runs, **Then** the alias table normalizes both to the same line before
   matching, so the comparison is not defeated by wording alone.
2. **Given** two captured quotes, one with every coverage line at least as good as
   `current_policy` and a lower normalized premium, and one with a single line worse than
   `current_policy` but a lower premium still, **When** quotes are ranked, **Then** the first
   quote outranks the second regardless of price - no coverage line worse than current always
   outranks a cheaper quote that has one.
3. **Given** two quotes that both have no coverage line worse than current, **When** they are
   ranked, **Then** the one with the lower premium (normalized to `current_policy`'s own term
   length) ranks first; if premiums tie, the one with fewer missing coverage lines ranks first.
4. **Given** the top-ranked quote, **When** the report renders, **Then** its recommendation banner
   states the rule that produced the ranking in plain language (e.g. "recommended because: every
   line at least matches current, premium $X vs $Y"), built only from the same comparison data -
   never a free-form or LLM-authored justification.
5. **Given** the rendered report file, **When** it is opened in a browser with no network
   connection, **Then** every table, every color mark, and every piece of styling renders
   correctly - no external stylesheet, script, font, or image reference exists anywhere in the
   file.
6. **Given** a captured quote missing a coverage line current_policy has, **When** that line is
   compared, **Then** it is marked missing, not silently omitted and not treated as equal or
   worse by some inferred substitute value.
7. **Given** no confirmed current-policy reference exists for the targeted asset (no
   `policy_doc` set, no PDF found, extraction unconfirmed, or extraction found zero coverage
   lines - D15), **When** the comparison engine runs, **Then** it ranks captured quotes by
   monthly-equivalent premium alone (no coverage-line classification is computed, since there is
   nothing to compare against), and the report's current-policy column renders a plain
   "no current-policy reference for `<asset>` - run scripts/policy_extract.py" marker in every row
   instead of refusing to render.

---

### User Story 4 - Multiple insurers run in one invocation, unmapped ones included (Priority: P2)

The Director's `profile` document's `feature_configs.insurance.companies` array can name more
companies than this delivery has a walk for. Running the comparison once still produces one report
covering every
configured insurer: the ones this delivery maps run their walk and contribute a real capture; the
ones it does not map appear as "not mapped yet"; and any insurer whose walk fails this run (a bot
block, a selector that has drifted) appears as a value-free failure row - none of that stops the
rest of the report from being produced.

**Why this priority**: this is what actually makes the feature "multiple insurance companies,"
not "one insurance company." Ranked P2 rather than P1 because with exactly one insurer mapped in
this delivery (Progressive), the orchestration logic this story tests is real but its payoff is
mostly forward-looking - it matters far more once spec 006 or later adds a second mapped insurer,
which is why it still ships now rather than being deferred: the report's shape (unmapped and
failed rows alongside real ones) needs to be right from the first release, not retrofitted once a
second insurer exists.

**Independent Test**: seed `profile`'s `feature_configs.insurance.companies` with
`["progressive", "geico"]` (`"geico"` a fixture insurer with no registered walk) and run
`scripts/quote_compare.py` in preview mode; confirm the printed summary lists `progressive`'s
masked plan and states `geico` has no registered walk, with zero browser activity attempted for
`geico`.

**Acceptance Scenarios**:

1. **Given** an insurer id in `feature_configs.insurance.companies` with no entry in the
   code-level walk registry,
   **When** any mode runs, **Then** it produces a "not mapped yet" row and triggers no `Session`,
   no `Config` resolution, and no browser process for that id.
2. **Given** two mapped insurers where the first insurer's apply run returns a non-zero exit code
   (its own walk failure, refused gate, or exception), **When** the orchestrator continues,
   **Then** the second insurer's walk still runs to completion, and the first insurer's failure
   appears in the report as a value-free row - no stack trace, no partial capture data, no browser
   session detail.
3. **Given** at least one insurer has a prior capture file from an earlier invocation and this
   run's own attempt for that insurer fails, **When** the report renders, **Then** the comparison
   uses the freshest capture file that exists for that insurer (from any prior run), with its own
   `fetched_at` timestamp shown in the provenance footer, rather than showing nothing for an
   insurer that has ever been captured successfully.
4. **Given** `scripts/quote_compare.py --check` or the default preview run, **When** it executes,
   **Then** every standard errand flag (`--apply`, `--check`, `--profile-dir`, `--headless`,
   `--show`, `--preview-dir`, `--no-screenshot`) behaves identically to how it behaves on any
   single-site errand, forwarded uniformly to every mapped insurer's own run in the same
   invocation.

---

### Edge Cases

- A mapped insurer's funnel blocks the walk mid-journey (a bot-defense page, an unexpected
  redirect): the walk's own step fails with a value-free error the same way `FillFailed` and
  `ClickFailed` already do; the orchestrator records it and continues with the remaining
  insurers (User Story 4, Acceptance Scenario 2).
- A previously working selector drifts (the site redesigns a page): `--check` reports it as
  missing before any apply run is attempted, the same contract every prior errand's `--check`
  already provides; an apply run that hits a drifted selector mid-walk fails that one step
  value-free and the orchestrator still records the failure and moves on.
- `profile`'s `feature_configs.insurance` object is missing entirely, or its `companies` field is
  missing, not a JSON array, or contains a non-string entry: the run refuses before any insurer's
  browser session opens, naming only what is missing (never `profile`'s own content).
- No confirmed current-policy reference exists for the targeted asset - no `policy_doc` set, a
  `policy_doc` path that does not resolve to a real file, a PDF from which nothing parsed, or an
  extraction that was never confirmed (D15): none of these refuse the run. The report still
  renders - every quote's coverage lines are listed uncompared, and ranking falls back to
  monthly-equivalent premium alone (User Story 3, Acceptance Scenario 7). This is a deliberate
  change from this spec's own original design, where a malformed hand-typed `current_policy`
  refused the run; a PDF that does not parse cleanly is an ordinary, expected outcome of
  best-effort extraction, not a data-entry mistake, and is never treated as one (research.md D15).
- No capture exists yet for any mapped insurer (the very first run, or every attempt has always
  failed): the report still renders, showing only "not mapped yet" and "capture failed / no data
  yet" rows plus whatever current-policy column state applies - it never refuses to render just
  because no comparison data exists yet.
- A captured quote's term length differs from the confirmed current-policy reference's own term
  (e.g. six months vs. twelve): the ranking rule normalizes both to the same term before comparing
  premiums (FR-016); the report states the normalization it applied, not just a bare number.
- Two mapped insurers both fail in the same run: both appear as value-free failure rows; the
  report still renders using whatever capture history and unmapped rows remain, and the run's own
  exit code reflects that the report itself was written, not that every insurer individually
  succeeded (NFR-004).
- A `CaptureStep` extractor's selector does not resolve on the quote page (the site changed a
  label, or the coverage line simply is not offered): that one field captures as an empty string
  plus one value-free note; the rest of the `CaptureStep`'s extractors still run, and the
  comparison engine treats the empty field as a missing coverage line (User Story 3, Acceptance
  Scenario 6), never as a crash.
- The Director adds an insurer to `feature_configs.insurance.companies` that this delivery never
  intended to map (a name with no relationship to any future spec): it is simply an unmapped row
  until a future spec registers a walk for it; there is no error, no warning beyond the row itself.
- Two `quote_compare.py` invocations run close together (a stale terminal left an earlier run
  going): each independently resolves the vault and writes its own timestamped capture and report
  files; the freshest-file-wins read means whichever run's capture lands last is what the next
  report read picks up - the same last-write-wins acceptance the vault and session-cookie file
  already carry for their own concurrent-write edge cases.
- A dotted registry path reaches a list node (`identities`, `addresses`, `vehicles`) whose next
  segment matches **more than one** element's `type` field: the lookup refuses with a value-free
  `RegistryAmbiguous`, naming only the path and the fact of duplication - never any matched
  element's own content (FR-042).
- A dotted registry path reaches a list node whose next segment matches **zero** elements' `type`
  fields: the existing `RegistryMissing`, unchanged, naming only the path (FR-041).
- A list element has no `type` field at all: it is never a match candidate for any segment - it is
  silently skipped, not an error (FR-043).
- A dotted registry path is fully consumed while the current node is still a list or a dict (no
  further segment existed to select an element, or a selected element is itself addressed with no
  further scalar field named): the existing non-scalar refusal fires, unchanged from before this
  amendment (FR-044).
- The targeted asset's `policy_doc` field is absent entirely: `scripts/policy_extract.py` simply
  never attempts that asset (FR-050); `scripts/quote_compare.py`'s own report renders FR-047's
  "no current-policy reference for `<asset>` - run scripts/policy_extract.py" marker, and quotes
  are still compared with each other by premium alone (FR-046).
- The targeted asset's `policy_doc` names a path that does not exist on disk, or a file that is
  not a readable PDF: the same soft-degrade as an absent field (FR-058) - `policy_extract.py`
  moves on without caching anything for that asset, never raising past its own per-asset attempt.
- A PDF extracts cleanly as text but zero coverage lines match any of the deterministic heuristics
  (an unusual declarations-page layout, a scanned image PDF with no text layer at all): the same
  soft-degrade again (FR-058) - this is an expected, ordinary outcome of best-effort extraction
  against a real-world document, not a crash, and not treated differently from a missing PDF.
- The Director declines to confirm or correct a printed extraction candidate (closes the terminal,
  answers no, or otherwise does not complete the confirmation step): no cache file is written, and
  this is not an error - the next `policy_extract.py` run simply re-extracts and re-offers the same
  candidate from the same PDF.
- An asset's `currently_insured` or `policy_doc` field is the literal string `"n/a"`: an explicit,
  Director-decided exclusion (FR-061), distinct from the field being merely absent - `policy_extract.
  py` skips it silently (FR-062, no note, unlike a genuinely missing-but-expected PDF, which is
  also silent but for a different reason); if the excluded asset is the one `quote_compare.py`
  targets (FR-060), zero insurer journeys run in any mode and the apply-mode report states the
  exclusion plainly instead of a comparison table (FR-063, FR-064).

## Requirements *(mandatory)*

### Functional Requirements

**Walk framework (User Story 1)**

- **FR-001**: `Errand` MUST gain a `walk(registry) -> list[Step]` method, where `Step` is one of
  `FieldPlan` (existing, unchanged), `ClickStep`, `HumanStep`, or `CaptureStep`. The default
  implementation MUST return exactly `self.plan(registry)`, so every errand that does not
  override `walk()` behaves identically to today.
- **FR-002**: `ClickStep(name, selector)` MUST be executable only in apply mode; outside apply
  mode it MUST refuse with the existing `GateRefused`, mirroring `Session.fill`'s own guard.
  Execution MUST never retry on failure and MUST raise a value-free `ClickFailed` (naming only
  the step's name, selector, and the caught exception's class) on any Playwright locator error -
  never the raw exception or its message, which can embed page content.
- **FR-003**: `HumanStep(name, instruction)` MUST be executed through the existing
  `Session.handoff(instruction)` call: it surfaces the window (idempotent past the first call in
  a run), prints exactly `Your turn: <instruction>`, waits for the Director to confirm, and
  returns control to the walk - the walk MUST continue to its next step afterward, never end
  there.
- **FR-004**: Once any `HumanStep` in a run has surfaced the window, the window MUST NOT be
  hidden or minimized again for the remainder of that run, in any subsequent step of the same
  walk.
- **FR-005**: `CaptureStep(name, extractors)` MUST be read-only: for each named extractor, if its
  selector resolves, its text becomes that field's value; if it does not resolve, that field's
  value is an empty string and exactly one value-free note is printed for it - the step MUST NOT
  abort and MUST continue with its remaining extractors regardless of any single missing one.
- **FR-006**: PREVIEW mode over a walk MUST execute nothing beyond the walk's initial page load:
  every `FieldPlan`'s source MUST resolve and its masked value MUST be recorded exactly as today;
  every `ClickStep`, `HumanStep`, and `CaptureStep` MUST be listed by kind and name only, with
  zero clicks, zero handoffs, and zero capture attempts.
- **FR-007**: APPLY mode over a walk MUST execute every step in declared order, dispatching by
  type, and MUST still end with exactly one trailing `session.handoff(self.HANDOFF)` call after
  the last step, unchanged in shape from today's contract for a `plan()`-only errand.
- **FR-008**: CHECK mode MUST remain unchanged by this feature: it probes only `Errand.dependencies`
  (the landing page's own selectors) and never traverses a walk's later steps.
- **FR-009**: The existing pre-resolution loop (every plan source resolved before any browser
  window opens, in every mode) MUST keep this property for every `FieldPlan` inside `walk()`, not
  only inside `plan()`. `ClickStep`, `HumanStep`, and `CaptureStep` carry no `Source` and MUST
  never be part of this loop.
- **FR-010**: This feature MUST NOT add a submit, pay, verify, or one-time-code step type, and no
  walk this delivery ships MUST ever point a `ClickStep` at a purchase, submit, or payment
  control. Completing a quote wizard through to a `CaptureStep` is never a terminal action.

**Companies live inside `profile.feature_configs`; `current_policy` is deleted, replaced by per-asset PDF extraction (User Story 2, User Story 3, User Story 4) - revised a second time 2026-08-25**

- **FR-011**: The Director's `profile` vault item gains a top-level `feature_configs` object
  (alongside its existing `identities`/`addresses`/`vehicles` arrays - FR-040), holding this
  feature's own `insurance` sub-object. `scripts/quote_compare.py` reads
  `feature_configs.insurance.companies` (a JSON array of insurer id strings) by parsing `profile`'s
  raw JSON directly (`json.loads(vault.get_secret("profile"))`), never through `ProfileRegistry` -
  because `ProfileRegistry.get` refuses any dotted path that ends on a list, and `companies` is
  never a single scalar field an errand's `FieldPlan` would type into a form. There is no separate
  vault item for it - two earlier design proposals (`insurers` as its own vault item; a top-level
  `profile.insurance` object) are both superseded (research.md D3, revised twice).
- **FR-012**: A `profile` document whose `feature_configs` object is missing, whose
  `feature_configs.insurance` is missing, or whose `companies` is missing, not a JSON array, or
  contains a non-string entry, MUST raise a value-free refusal naming only what is missing (never
  `profile`'s own content), before any insurer's browser session opens.
- **FR-013**: There is no `current_policy` field anywhere in `profile`, and none is ever planned
  (research.md D3, second revision). Each insured asset - an `addresses[]` element (`"home"`, a
  future `"rental"`) or a `vehicles[]` element (`"primary"`, a future additional vehicle) - carries
  its own `policy_doc` field: a filesystem path to a PDF of the policy currently covering that
  asset. The comparison engine's own reference document, when one exists, comes only from a
  Director-confirmed cache under `reports/policy/` (FR-050 through FR-060) - never read directly
  from `profile`, and never hand-typed into the vault.

**Capture model (User Story 2)**

- **FR-014**: A successful `CaptureStep` at the end of an insurer's walk, in apply mode, MUST
  produce a `QuoteCapture` record and write it as JSON to
  `reports/captures/<insurer>-<timestamp-utc>.json`. When an insurer's funnel offers more than one
  coverage tier or package (e.g. basic/standard/premium), the walk MUST capture the funnel's own
  pre-selected (default) package, never a package the walk itself chooses or changes -
  implementation-time recon (FR-032) records which package that is, and the `QuoteCapture`'s own
  `package` field (data-model.md) names it so the report's provenance can state which tier the
  captured premium and coverage lines actually describe. If recon finds the funnel reaches a
  multi-tier page with no package pre-selected by default, the walk MUST add a `HumanStep` asking
  the Director to pick one before the terminal `CaptureStep` runs - the walk MUST NOT guess or
  default to an arbitrary tier itself.
- **FR-015**: `reports/` (both `captures/` and the rendered HTML report) MUST be excluded from
  version control and MUST carry the same vault-grade local-data classification `previews/`
  already carries under `CLAUDE.md`'s Secrets section - never committed, shared, or attached
  anywhere, since it can hold premiums, coverage limits, and implicitly the Director's own
  insurability profile.

**Comparison engine (User Story 3)**

- **FR-016**: Quotes MUST be ranked by, in order: (1) no coverage line worse than
  `current_policy`, strictly ahead of any quote with at least one worse line; (2) among quotes
  tied on (1), a lower premium normalized to `current_policy`'s own term length per FR-067(b);
  (3) ties on both broken by fewer missing coverage lines. A quote whose `premium.amount` or
  `premium.term_months` fails FR-067(a)'s parsing rule MUST be ranked last, after every quote
  whose premium parsed, with the reason "premium not comparable" shown in the report - never a
  crash, never a guessed figure. (When `current_policy` is absent, FR-046 governs instead.)
- **FR-017**: Coverage line names MUST be normalized through a small, hand-authored alias table
  before a captured quote's lines are matched against `current_policy`'s own lines, so wording
  differences between insurers do not defeat the comparison.
- **FR-018**: Each `current_policy` coverage line MUST be classified, per captured quote, as
  better, equal, worse, or missing relative to that same normalized line, using FR-067(c)'s
  limit-comparison rule and FR-067(d)'s deductible-comparison rule - missing exactly when the
  captured field's value is an empty string; a line whose limit or deductible is "not comparable"
  per FR-067(c)/(d) (a differing tuple arity, or either side unparseable) MUST be classified in
  its own "not comparable" class - never counted as better, worse, or equal, and never silently
  dropped from the report.
- **FR-019**: The top-ranked quote MUST be presented as the recommendation together with a rule
  trail: a short, deterministic string built only from the same comparison data (never a
  free-form or LLM-authored justification) stating the rule that produced the ranking.
- **FR-020**: The comparison engine MUST contain no call to any LLM anywhere in its path. Every
  number that reaches a report - a premium, a limit, a deductible, a ranking position - MUST
  originate from a capture file or from `current_policy`, never from anything a model derived.
- **FR-021**: The comparison MUST run over the freshest capture file that exists per insurer
  (by filename timestamp under `reports/captures/`), regardless of which prior invocation of
  `scripts/quote_compare.py` produced it, together with the confirmed current-policy reference
  read from `reports/policy/` (FR-057), when one exists.
- **FR-046** *(added, User Story 3)*: When no confirmed current-policy reference exists for the
  targeted asset (no cache file under `reports/policy/` at all, or a cache file that fails to
  parse - FR-057/FR-058 name every cause), the comparison engine MUST NOT compute a
  better/worse/equal/missing classification for any coverage line - there is nothing to compare
  against. It MUST still rank captured quotes, by monthly-equivalent premium computed per
  FR-067(b) (`Decimal(amount) / term_months`, quantized to 2 decimal places, `ROUND_HALF_UP`)
  ascending, with any quote whose premium fails FR-067(a)'s parsing rule ranked last per FR-016,
  and the rule trail MUST state plainly that no current-policy reference was on file and premium
  alone drove the ranking.
- **FR-067** *(added, User Story 3, comparison arithmetic - mid-list insertion, see the amendment
  note above)*: The comparison engine's parsing and normalization of every comparable figure MUST
  follow these rules exactly, so the byte-identical-output invariant data-model.md's
  `build_comparison` contract already requires is achievable with pure `Decimal` arithmetic and no
  float:
  (a) **Amount and term parsing**: a `premium.amount` value is parsed by stripping currency
  symbols, commas, and spaces, then parsing the remainder as a decimal number; `premium.
  term_months` is parsed as a positive integer. If either parse fails for a quote, that quote MUST
  be ranked last (FR-016) with the reason "premium not comparable" shown in the report - never a
  crash, never a guessed figure.
  (b) **Normalized premium**: the normalized premium is `Decimal(amount) / term_months`, quantized
  to 2 decimal places using `ROUND_HALF_UP`, presented in the report as a monthly figure. The
  report MUST state that this normalization was applied.
  (c) **Limit comparison**: a limit string parses to a tuple of integers by splitting on `"/"`,
  stripping `$` and commas from each part, and multiplying a part by 1000 when it ends in `k`/`K`.
  Two limits are compared only when their tuples have the same arity: element-wise `>=` on every
  position is "better or equal"; all-equal is "equal"; any position lower is "worse". A different
  arity between the two sides, or a side that fails to parse, classifies that line "not comparable"
  - its own class, never counted as better, worse, or equal, and listed distinctly in the report.
  (d) **Deductible comparison**: a deductible string parses the same way as an amount (FR-067(a)'s
  stripping rule) to a single number; a LOWER parsed deductible is better. An empty deductible on
  either side is "not comparable".
  (e) **Determinism**: every parse and every comparison this requirement defines uses Python's
  `Decimal` type only, never `float` - this is what makes data-model.md's `build_comparison`
  byte-identical-output invariant achievable in practice, not only in principle.

**Report generation (User Story 3)**

- **FR-022**: `scripts/quote_compare.py` (in apply mode, after every mapped insurer's walk has
  finished) MUST render one self-contained HTML report to
  `reports/quote-comparison-<date>.html`: inline CSS only, no external stylesheet, script, font,
  or image reference, and no JavaScript required to view it correctly.
- **FR-023**: The report MUST include one column per quote (including the current-policy
  reference's own column, or its FR-047 marker when none exists) and one row per normalized
  coverage line, with each cell visually marked better/worse/missing/equal relative to the current
  policy when a confirmed reference exists.
- **FR-024**: The report MUST include a premium row, a recommendation banner carrying the rule
  trail (FR-019 or FR-046), one row per unmapped insurer (FR-027), one row per insurer whose
  capture failed or does not yet exist, and a data-provenance footer naming each included
  capture's `fetched_at` timestamp and `source_url`, plus (FR-059) the current-policy reference's
  own `source_path` and `confirmed_at` when one exists.
- **FR-025**: A report MUST still be produced even when every mapped insurer's apply run failed
  this invocation, as long as `feature_configs.insurance.companies` itself parsed successfully - it
  renders whatever mix of real captures, unmapped rows, and failed rows the run actually has, never
  refusing to render for lack of a fresh comparison, and never refusing merely because no
  current-policy reference exists (FR-013, FR-058) - the report generator never has a reason to
  refuse over anything current-policy-related; every such problem degrades to FR-047's marker.
- **FR-047** *(added, User Story 3)*: When no confirmed current-policy reference exists for the
  targeted asset, the report's current-policy column MUST render a plain "no current-policy
  reference for `<asset>` - run scripts/policy_extract.py" marker in every row, rather than
  omitting the column or refusing to render the report.

**Multi-insurer orchestration (User Story 4)**

- **FR-026**: `scripts/quote_compare.py` MUST accept only the standard errand mode flags
  (`--apply`/`--check` mutually exclusive, `--profile-dir`, `--headless`/`--show` mutually
  exclusive, `--preview-dir`, `--no-screenshot`) through the same `add_mode_arguments()` surface
  every errand already shares; this feature MUST NOT introduce a new flag family.
- **FR-027**: An insurer id present in `feature_configs.insurance.companies` with no entry in the
  code-level walk registry MUST produce a "not mapped yet" report row and MUST trigger no
  `Session`, no `Config` resolution, and no browser process for that id, in any mode.
- **FR-028**: In preview and check mode, `scripts/quote_compare.py` MUST run every mapped
  insurer's own `Errand` subclass in that same mode, forwarding its own parsed flags, producing
  that insurer's own masked-plan or landing-selector-probe artifact exactly as a single-site
  errand already does, and MUST additionally state which configured insurers have no registered
  walk.
- **FR-029**: In apply mode, `scripts/quote_compare.py` MUST run every mapped insurer's own
  `Errand` subclass in sequence; one insurer's non-zero return code MUST be recorded value-free
  and MUST NOT prevent the remaining insurers' walks from running.
- **FR-030**: `scripts/quote_compare.py`'s own exit code MUST reflect only whether the report was
  successfully written, never whether every individual insurer's walk succeeded - a run with one
  or more insurer failures that still produces a report MUST exit `0`.

**Progressive walk (User Story 2)**

- **FR-031**: The code-level walk registry MUST hold exactly one entry in this delivery,
  `"progressive"`, whose walk begins by filling the ZIP field (`#zipCode_mma`, from
  `registry:addresses.home.zip`) and clicking the quote-start button (`#qsButton_mma`) - the two
  selectors verified before this feature was scoped.
- **FR-032**: No selector beyond the landing page MUST ship unless implementation-time recon
  (research.md, at most three headless scratch-profile walks against Progressive, synthetic data
  only) actually proves it resolves. Any point recon cannot cross or cannot verify MUST be
  bridged by a `HumanStep` instead of a guessed or assumed selector.
- **FR-033**: Implementation-time recon for this delivery MUST NEVER submit, use, or reference the
  Director's real identity, address, date of birth, or licence data, and MUST NEVER click a
  purchase, submit, or payment control at any point.
- **FR-034**: If Progressive's funnel refuses headless Chrome at some point during
  implementation-time recon, that refusal MUST be recorded as evidence in research.md for the
  repository's standing headless-user-agent question, and the walk MUST still ship whatever depth
  recon actually proved, bridging the rest with `HumanStep`s rather than being withheld entirely.
- **FR-035**: Where implementation-time recon (FR-032) finds an "are you currently insured?"
  question on a page the Progressive walk reaches, the walk MUST fill or select it from
  `registry:vehicles.primary.currently_insured` (a `FieldPlan` of kind `select` or `check`,
  whichever matches the control recon finds) rather than leaving it for a `HumanStep` - `currently_
  insured` lives on the insured asset itself (`addresses[]`/`vehicles[]`, D3's second revision),
  not on `identities`, since a household can have one policy status per asset, not one per person.
  The selector itself remains subject to FR-032's own "unproven selector never ships" rule - only
  the registry path and the field's semantic meaning are decided now.
- **FR-036**: No `FieldPlan`, `ClickStep`, `HumanStep`, or `CaptureStep` this delivery ships MUST
  reference `identities.spouse.*`, `addresses.rental.*`, `addresses.work.*`, or
  `addresses.*.dwelling_type` at any registry path. Each is seeded in the Director's profile for a
  future feature (`identities.spouse` for a future multi-driver mapping; `addresses.rental` for a
  future renters- or landlord-insurance spec; `addresses.work` and `dwelling_type` for a future
  property-insurance or commute-aware auto spec - FR-065, FR-066) and MUST NOT be wired into any
  walk before that future spec authorizes it.

**Vault CLI amendments (spec 004, shipped in v0.0.4.1 through v0.0.4.4, recorded here 2026-08-25)**

**Status**: none of `scripts/vault.py get NAME`, `scripts/vault.py verify`, or `set`'s
piped-stdin/1024-character-refusal behavior is something spec 005 asks to be built. The Director
wanted `get` immediately, so the orchestrator shipped it as hotfix v0.0.4.1 directly on `main`
(merge `f35988e`, commit `9cc3b20`, three tests, `scripts/README.md` and `Project_Structure.md`
already updated there) ahead of this delivery; once real-data-vs-template validation was also
wanted, `verify` shipped the same way as hotfix v0.0.4.2 (merge `cc01246`); once this delivery's
own `profile.template.json`-shaped document proved too large for `set`'s hidden interactive
prompt, the piped-stdin path and the 1024-character refusal shipped as hotfix v0.0.4.3 (merge
`a7e2e48`), and the prompt's own pipe-command hint shipped as hotfix v0.0.4.4 (merge `d55bc80`).
FR-037 through FR-039c below record all four contracts as already-shipped fact, because spec 005's
own quickstart (below) uses every one of them in the profile-editing and validation workflow - none
is new work for `/speckit-implement` to build. This worktree's own `v0.0.5` branch does not yet
contain any of the four hotfixes (it forked before all of them landed); see research.md D12 and
D17 for how that gap is expected to close.

- **FR-037**: `scripts/vault.py` provides a `get NAME` subcommand that decrypts the vault (one
  passphrase prompt) and prints only the raw string value of item `NAME` to stdout, followed by a
  single newline, with no other output, exit `0`, on success. This amends spec 004's own
  `scripts/vault.py` CLI contract (`specs/004-age-vault/contracts/vault-and-cli.md`'s section 3
  table), which did not originally include a `get` subcommand.
- **FR-038**: `get NAME` refuses with `REFUSED: item '<name>' not in the vault`, exit `1`, when
  `NAME` is absent from the decrypted document; every other failure (a missing vault file, a wrong
  passphrase, `age` unreachable) matches `list`'s own existing failure shape exactly.
- **FR-039**: `get`'s printed value is a deliberate, sole exception to the vault's own
  never-print-a-value convention (`list`'s existing "never a value" contract; every other note or
  error message this and every prior vault-touching feature produces). The exception is scoped to
  this one interactive, Director-invoked terminal command: `get`'s own value is never written to a
  log, a preview artifact, or a report, and is never read by any errand's automated code path - no
  code under `headless/` calls it - and every other output the vault CLI or any errand produces
  continues printing zero values.
- **FR-039b**: `scripts/vault.py verify` (shipped alongside `get`, as hotfix v0.0.4.2, `main`, not
  yet in this worktree) also exists and is also recorded, not built, by this delivery. It decrypts
  `profile` once (one passphrase prompt) and structurally compares it against
  `profile.template.json`: an unknown field is an ERROR, a template field absent from the real
  document is a WARN, a kind mismatch (e.g. a string where the template has an object) is an
  ERROR, a missing or duplicate `type` discriminator on an array element is an ERROR, an unknown
  array element `type` is checked against that array's first template element's own shape
  (accepted as legitimate, not an error), and any `_`-prefixed key is ignored entirely. Findings
  print as value-free `SEVERITY path: reason` lines - never a field's own value. Exit `0` when
  clean or warnings-only, `1` when any error was found, and it refuses before any passphrase
  prompt at all when `profile.template.json` itself is missing. `verify` and this delivery's own
  drift test (FR-048) are complementary, not overlapping: `verify` checks the Director's real,
  live `profile` document against the template; the drift test checks this delivery's own shipped
  *code* (its registry paths) against the same template - one guards data, the other guards code,
  both against the one shared contract file.
- **FR-039c**: `scripts/vault.py set NAME`'s hidden interactive prompt refuses any value of 1024
  or more characters (`REFUSED: value is 1024+ characters and may have been truncated by the
  terminal's input limit; pipe it instead: pbpaste | python scripts/vault.py set <name>`) rather
  than silently storing a value the terminal's own canonical input-line limit may have already
  truncated; the same command also accepts the value on piped stdin instead (`pbpaste | python
  scripts/vault.py set profile`; Windows: `Get-Clipboard | python scripts\vault.py set profile`),
  which has no such limit, and the interactive prompt itself prints the pipe-command hint before
  asking for a value, not only after a refusal. Shipped alongside `get`/`verify`, as hotfixes
  v0.0.4.3 and v0.0.4.4 (`main`, not yet in this worktree), and also recorded rather than built by
  this delivery (research.md D17) - `profile.template.json`'s own shape is 1235+ characters as raw
  JSON, past the 1024-character boundary by construction, so spec 005's own quickstart profile-
  editing round trip depends on this piped path working, not the hidden-prompt path.

**Type-discriminated array addressing in `ProfileRegistry.get` (framework requirement, added 2026-08-25)**

The Director's actual `profile` document holds `identities`, `addresses`, and `vehicles` as JSON
arrays, each element distinguished by a `type` field (e.g. `{"type": "self", "first_name": ...}`).
`ProfileRegistry.get`'s existing dotted-path traversal (`headless/profile.py`, spec 001) has no
way to address one array element - this is new, general framework capability, not specific to
Progressive or to insurance, and belongs in the walk framework's own foundational scope
(data-model.md covers the resolver's state machine).

- **FR-040**: When `ProfileRegistry.get`'s traversal reaches a list-valued node partway through a
  dotted path, the next path segment MUST select the unique element of that list whose `type`
  field equals that segment exactly (string equality); traversal MUST then continue from that
  element as if it were the node reached directly, unchanged from the existing dict-traversal
  behavior.
- **FR-041**: A segment matching zero elements' `type` fields MUST raise the existing
  `RegistryMissing(path)`, unchanged in shape from today's "path not found" case.
- **FR-042**: A segment matching more than one element's `type` field MUST raise a new
  `RegistryAmbiguous(path)`, a value-free error naming only the dotted path and the fact of
  duplication - never any matched element's own field content.
- **FR-043**: A list element with no `type` field MUST NOT be a match candidate for any segment;
  it is silently skipped, never an error and never a spurious match.
- **FR-044**: A dotted path that is fully consumed while the current node is still a list or a
  dict (no further segment existed to select an element, or the resolved element is itself a
  dict) MUST continue to raise the existing non-scalar `RegistryMissing`, unchanged from before
  this requirement existed.
- **FR-045**: `RegistryAmbiguous` MUST join `RegistryMissing`/`SecretMissing`/`ConfigError`/
  `GateRefused` in `Errand.run()`'s existing pre-session exception handling, printing
  `REFUSED: {exc}` and exiting `1` - the same value-free-by-construction treatment every other
  domain-shaped refusal in that tuple already receives.

**`profile.template.json` as the enforced schema contract (added 2026-08-25)**

A file `profile.template.json`, holding wholly synthetic values in the exact shape described
above (`identities`/`addresses`/`vehicles` arrays, the `insurance` object), exists at the
repository root - shipped by the orchestrator as a docs-only increment on `main`, ahead of and
independent of this delivery. It is the enforced contract of record for what a real `profile`
vault item's document must look like.

- **FR-048**: A unit test MUST load `profile.template.json` directly (a fixture file read, never
  through the vault, never prompting for a passphrase) and resolve, through `ProfileRegistry` (
  exercising FR-040 through FR-044's array addressing), every registry path any shipped walk in
  this delivery references - including the Progressive walk's full field list and
  `vehicles.primary.currently_insured`. Any path that fails to resolve against the template MUST
  fail this test, making it structurally impossible to merge a walk change that references a
  profile field the template does not define.
- **FR-049**: This delivery MUST NOT recreate or duplicate `profile.template.json` as a second
  file - it already exists at the repository root. If implementation-time recon (FR-032) proves
  the Progressive walk needs a field the template does not yet define, the same change that adds
  the walk's reference to that field MUST also extend `profile.template.json` itself, in the same
  commit; FR-048's drift test enforces this structurally, not merely as a convention.

**Policy PDF extraction and mandatory Director confirmation (added 2026-08-25, User Story 3)**

Replaces hand-typed `current_policy` (D3's second revision, research.md D15). Each insured asset
(an `addresses[]`/`vehicles[]` element) may carry a `policy_doc` field naming a PDF on disk; this
mechanism turns that PDF into the same `CurrentPolicy`-shaped reference the comparison engine has
always consumed, gated by a Director confirmation step nothing may bypass.

- **FR-050**: `scripts/policy_extract.py` (new; not a browser errand, not an `Errand` subclass)
  MUST, for every `addresses[]`/`vehicles[]` element in `profile` whose `policy_doc` field is set
  to a real path (never the literal string `"n/a"` - FR-062 governs that case separately), attempt
  extraction from the PDF at that path. `policy_doc` MUST be read by a direct parse of the whole
  `profile` document (iterating `addresses` and `vehicles`), never through `ProfileRegistry.get` -
  finding every asset with a field set is an enumeration `ProfileRegistry`'s own single-element
  `type`-addressing (FR-040) was never built for.
- **FR-051**: Extraction MUST use `pypdf` (a new runtime dependency) to read the PDF's text and
  MUST apply deterministic heuristics only - dollar-amount patterns, split-limit patterns (e.g.
  `100,000/300,000`), deductible-line detection, premium/term detection. It MUST NOT call an LLM
  at any point; this is the same constitutional rule FR-020 already states for the comparison
  engine, extended here to cover extraction as well.
- **FR-052**: The extracted candidate MUST be shaped identically to `CurrentPolicy`
  (`{"insurer", "premium": {"term_months", "amount"}, "coverages": [{"line", "limit", "deductible",
  "premium"}]}`) - unchanged from this spec's own original design for that shape.
- **FR-053**: The candidate MUST be printed to the Director's own terminal before anything is
  cached - a deliberate, sole-purpose exception to this codebase's value-free-output convention,
  the same documented exception class `vault.py get` already establishes (FR-039): scoped to this
  one interactive, Director-invoked command, reviewing his own data on his own terminal.
- **FR-054**: The Director MUST be offered exactly two paths forward after the candidate prints:
  accept it as printed, or supply a corrected JSON document at a follow-up prompt. Declining
  either path MUST leave no cache file written and MUST NOT be treated as an error.
- **FR-055**: Nothing MUST be cached, and nothing MUST ever reach the comparison engine, without
  the confirmation step in FR-054 - an unconfirmed candidate MUST be discarded, never silently
  used as though it were confirmed.
- **FR-056**: A confirmed reference MUST be written to `reports/policy/<asset-key>.json`
  (data-model.md derives `<asset-key>`), mode `0600` where the platform supports it, holding the
  confirmed `CurrentPolicy`-shaped document plus provenance (`source_path`, `confirmed_at`).
- **FR-057**: The comparison engine MUST read a confirmed current-policy reference only from
  `reports/policy/<asset-key>.json` - never from `profile` directly, and never from an unconfirmed
  extraction candidate.
- **FR-058**: A missing `policy_doc`, a `policy_doc` path that does not exist on disk, a file that
  is not a readable PDF, or a PDF from which zero coverage lines could be parsed, MUST NOT abort
  `scripts/policy_extract.py`'s processing of other assets, and MUST NOT block
  `scripts/quote_compare.py`'s own report: the report renders FR-047's "no current-policy
  reference" marker and quotes are still compared with each other and ranked (FR-046).
- **FR-059**: The report's provenance footer MUST include, for the targeted asset when a
  confirmed reference exists, that reference's own `source_path` and `confirmed_at` date,
  alongside each quote's own capture provenance (FR-024).
- **FR-060**: In this delivery, `scripts/quote_compare.py`'s own comparison MUST target exactly
  one asset key, `vehicles-primary` (the Progressive auto walk's own scope), reading
  `reports/policy/vehicles-primary.json` when present. A future homeowners- or renters-insurance
  spec would target a different asset key (`addresses-home` or `addresses-rental`) via its own
  orchestrator; this delivery MUST NOT read or write any other asset key's cache file.

**The `"n/a"` sentinel (added 2026-08-25, Director schema decision)**

On any `addresses[]`/`vehicles[]` element, the literal string `"n/a"` in `currently_insured` or in
`policy_doc` is an explicit, Director-decided exclusion - distinct from an absent field, which
means only "no data," never "excluded." `profile.template.json` records this convention; a future
insurance feature reading any asset's data MUST honor it the same way this delivery does.

- **FR-061**: The literal string `"n/a"` in an asset's `currently_insured` or `policy_doc` field
  MUST be treated as "this asset is excluded from every insurance feature this delivery (or any
  future one built on this framework) provides" - never as a real path, a real yes/no answer, or a
  value to type, extract, or compare. No consumer (a `FieldPlan`, `scripts/policy_extract.py`,
  `scripts/quote_compare.py`) MUST ever treat the string `"n/a"` as anything other than this
  sentinel.
- **FR-062**: `scripts/policy_extract.py` MUST skip, without printing a note and without treating
  it as an error, any asset whose `policy_doc` equals the literal string `"n/a"` - exactly the
  same silent skip an asset with no `policy_doc` field at all already receives (FR-050); both are
  simply never attempted, for different reasons (no data, versus an explicit exclusion), with the
  same observable behavior.
- **FR-063**: `scripts/quote_compare.py` MUST check, before constructing any insurer's `Errand`,
  in every mode, whether the targeted asset (FR-060: `vehicles.primary`) is excluded - either its
  `currently_insured` or its `policy_doc` field equals `"n/a"`. When excluded: zero insurer
  journeys run in any mode (no `Errand`, no `Session`, no `Config` resolution, for any mapped
  insurer), and one clear, informative line prints stating the asset is excluded per the
  Director's own profile setting - a deliberate no-op the Director's own data already decided,
  never treated as a failure.
- **FR-064**: In apply mode, when the targeted asset is excluded, `scripts/quote_compare.py` MUST
  still write a report (extending FR-025's "always produce something" guarantee to this case too)
  whose content states the exclusion plainly - "vehicles.primary excluded by profile (n/a)" - in
  place of a comparison table, rather than a bare refusal or an empty comparison built from zero
  attempted data.

**Two future-feature fields, seeded now, unused in this delivery (added 2026-08-25)**

- **FR-065**: `addresses[]` elements MAY carry a `dwelling_type` field (a dwelling classification -
  example values `single_family`, `condo`, `apartment`, `townhouse`, `commercial` - named
  `dwelling_type` rather than `type` because `type` is already the array's own selection
  discriminator, FR-040). No `FieldPlan`, `ClickStep`, `HumanStep`, or `CaptureStep` this delivery
  ships MUST reference `addresses.*.dwelling_type` at any registry path - it is seeded for a
  future property-insurance spec, not consumed by the auto-only Progressive walk this delivery
  ships.
- **FR-066**: A third `addresses[]` element type, `"work"` (`dwelling_type` `"commercial"`, both
  `currently_insured` and `policy_doc` set to the `"n/a"` sentinel), MAY exist in `profile` -
  seeded for a future feature (e.g. an auto funnel asking a commute or garaging-address question
  that would consume `addresses.work.*`). In this delivery it is excluded from insurance scope by
  its own sentinels (FR-061) exactly like any other excluded asset, and MUST NOT be wired into any
  walk this delivery ships, the same guard FR-036 already states for `identities.spouse.*` and
  `addresses.rental.*`.

### Non-Functional Requirements

- **NFR-001**: The rendered report MUST make zero external network requests when opened: no CDN
  reference, no remote font, no remote image, no remote script - fully self-contained, readable
  offline in any browser.
- **NFR-002**: The unit test suite covering this feature's new modules (the step types, the
  registry's array-element addressing, the capture model, the comparison engine, the report
  generator, and the Progressive walk's own pure logic) MUST run to completion in under one second
  combined, with zero browser launches and zero passphrase prompts, matching the existing
  convention `tests/test_secrets.py` and `tests/test_vault.py` already establish for `AgeBackend`.
- **NFR-003**: Every note or exception message this feature introduces (a missing capture
  extractor, a malformed `insurance` object, a duplicate registry `type` match, an insurer's walk
  failure) MUST be provably value-free - no message MUST ever contain a premium figure, a coverage
  limit, a policy number, or any fragment of a captured page's own text. The sole, explicitly
  scoped exception is `vault.py get`'s own designed stdout output (FR-039), which is not a note or
  an exception message in the sense this requirement governs.
- **NFR-004**: One insurer's walk failure MUST never raise past `scripts/quote_compare.py`'s
  per-insurer loop; the orchestrator's own exit code reflects whether the report was written, not
  whether every insurer individually succeeded (FR-030).

### Key Entities

- **Step**: the walk framework's unit of work. One of four kinds: `FieldPlan` (existing, a typed
  value filled from the registry, the vault, or a literal), `ClickStep` (a named wizard-navigation
  click, apply-only), `HumanStep` (a named mid-walk handoff to the Director, with an instruction
  string), or `CaptureStep` (a named, read-only scrape of a page into a flat field mapping).
- **Walk**: the ordered list of `Step`s an errand's `walk(registry)` returns. Every mode
  interprets the same list differently (data-model.md's mode matrix); there is exactly one walk
  per insurer's `Errand` subclass in this delivery.
- **`profile`'s array-and-object shape**: the Director's existing vault item holds three top-level
  JSON arrays (`identities`, `addresses`, `vehicles`, each element discriminated by a `type` field)
  and one top-level `feature_configs` object, holding this feature's own `insurance.companies`
  sub-object (a JSON array of insurer id strings). There is no `current_policy` field anywhere in
  `profile`, and none is ever planned (FR-013, research.md D3, second revision) - each insured
  asset's own `policy_doc` PDF path is the reference instead, extracted and Director-confirmed
  under `reports/policy/` (FR-050 through FR-060). `feature_configs.insurance` is read by the
  orchestrator through a direct JSON parse of the whole `profile` document, never through
  `ProfileRegistry` (FR-011); the three arrays are read through `ProfileRegistry`'s extended,
  array-element-addressing traversal (FR-040 through FR-044) exactly like any other registry path.
- **QuoteCapture**: the structured record one insurer's successful `CaptureStep` produces: the
  insurer id, when it was fetched, the premium, the coverage lines it found, and the quote page's
  URL. Written to `reports/captures/`, never committed.
- **ComparisonResult**: the pure output of the comparison engine: a ranked list of quotes (each
  with its per-line classification against the confirmed current-policy reference when one
  exists, or none when it does not), the recommended quote, and the rule trail that produced the
  ranking. Consumed only by the report generator; never partially constructed from anything but
  capture files and the confirmed reference read from `reports/policy/` (D15).
- **Report**: the self-contained HTML file `scripts/quote_compare.py` writes at the end of an
  apply run. Reads only from a `ComparisonResult` plus the unmapped and failed-insurer lists; never
  itself touches the vault, a browser, or an LLM.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A unit test proves preview mode over a walk containing `ClickStep`, `HumanStep`, and
  `CaptureStep` performs zero navigation beyond the walk's initial page load, and zero click,
  handoff, or capture calls.
- **SC-002**: A unit test proves a rendered report contains zero external URL references (no
  `<script src=`, `<link rel="stylesheet" href=`, remote image, or CDN reference) outside the
  provenance footer's own plain-text `source_url` values.
- **SC-003**: A unit test constructs a distinctive fixture-shaped failure string for a simulated
  insurer walk failure and proves that string never appears anywhere in the rendered report's
  failure row - only a value-free note does.
- **SC-004**: The unit suite covering the step types, the registry's array-element addressing, the
  capture model, the comparison engine, the report generator, and the Progressive walk's own pure
  logic completes in under one second combined, launching zero browsers and prompting for zero
  passphrases.
- **SC-005**: A fixture-driven orchestrator test proves one insurer's simulated walk failure (a
  fixture `Errand` subclass whose `run()` returns non-zero) does not stop a second,
  independently-configured insurer's walk from completing in the same invocation.
- **SC-006**: A unit test proves the ranking rule orders a quote with no coverage line worse than
  `current_policy` ahead of a cheaper quote that has one worse line, and among two quotes with no
  worse line, orders the lower normalized-premium quote first (FR-067(b)'s `Decimal`-based
  normalization); a further unit test proves a quote whose premium fails FR-067(a)'s parsing rule
  ranks last, tagged "premium not comparable", never causing a crash or a guessed figure.
- **SC-007**: A unit test proves an unmapped insurer id produces exactly one "not mapped yet"
  report row and zero attempted `Session`, `Config`, or browser-process constructions for that id.
- **SC-008**: A unit test proves a malformed `insurance` object (missing, or `companies` malformed)
  refuses before any insurer's `Session` is constructed, using a fixture spy that would record any
  such construction.
- **SC-009**: A unit test proves `CaptureStep`'s missing-extractor path returns an empty string
  for that one field, prints exactly one value-free note, and still runs every remaining
  extractor in the same step without raising.
- **SC-010**: A unit test proves the report's provenance footer names each included capture's
  `fetched_at` timestamp and `source_url`, and no other capture field is duplicated there.
- **SC-011**: A repository-wide grep for the distinctive synthetic premium and coverage-limit
  values this feature's own test fixtures use finds them only under `tests/` and
  `specs/005-insurance-quote-comparison/`, never inside a shipped module under `headless/` or
  `scripts/`.
- **SC-012**: This delivery's implementation-time recon (FR-032) is recorded in research.md with
  an explicit count of scratch-profile walks run (at most three, synthetic data only) and their
  outcome, including whether the funnel accepted or refused headless Chrome.
- **SC-013**: `python -m pytest -q`, `python scripts/verify_structure.py`, and
  `python scripts/scan_secrets.py --staged` all report clean with this feature's new and changed
  files staged - deferred to the implementation delivery, since this spec-authoring delivery does
  not touch code or stage anything, matching every prior spec's own precedent of leaving the
  commit gate to `/speckit-implement`.
- **SC-014**: A repository-wide grep proves no call into `vault.py get`'s underlying function
  exists anywhere under `headless/` or in any errand script - the exception FR-039 states is
  confirmed structurally absent from every automated code path, not merely asserted in prose.
- **SC-015**: A repository-wide grep proves no shipped `headless/insurers/progressive.py` step
  references `identities.spouse.`, `addresses.rental.`, `addresses.work.`, or `.dwelling_type` at
  any registry path (FR-036).
- **SC-016**: A unit test proves `ProfileRegistry.get("identities.self.first_name")` (and every
  sibling path the Progressive walk uses) resolves correctly against a fixture array-shaped
  document, and a fixture document with two elements sharing the same `type` value raises
  `RegistryAmbiguous` naming only the path, never either matched element's own content.
- **SC-017**: A unit test proves the plain absence of a confirmed current-policy reference (no
  `reports/policy/vehicles-primary.json`) renders a report with every current-policy cell marked
  with FR-047's "no current-policy reference" marker rather than refusing, while
  `feature_configs.insurance.companies`'s absence or malformation refuses before any insurer's
  `Session` is
  constructed.
- **SC-018**: The drift test (FR-048) passes when run against the real `profile.template.json`
  once this worktree has it (research.md's own worktree-gap note applies here too); until then,
  its own fixture-based unit-level logic - proven correct against a synthetic in-memory document
  standing in for the template - is a direct drop-in once the real file is present, requiring no
  further change to the test itself.
- **SC-019**: A unit test proves an extraction candidate is never written to
  `reports/policy/<asset-key>.json` without an explicit accept-or-correct confirmation - a fixture
  "decline" path leaves no cache file, and is not treated as an error (FR-054, FR-055).
- **SC-020**: A unit test proves a fixture PDF from which zero coverage lines could be parsed does
  not abort `scripts/policy_extract.py`'s processing of other assets and does not cause
  `scripts/quote_compare.py`'s own report to refuse (FR-058).
- **SC-021**: A unit test proves a confirmed cache file is written at mode `0600` and contains both
  the `CurrentPolicy`-shaped fields and its own provenance (`source_path`, `confirmed_at`) (FR-056).
- **SC-022**: A repository-wide grep or import-graph check proves no LLM client, API call, or
  prompt-construction code exists anywhere in `headless/policydoc.py` or
  `scripts/policy_extract.py` (FR-051).
- **SC-023**: A unit test proves an asset whose `policy_doc` is `"n/a"` is skipped by
  `scripts/policy_extract.py` with no note and no error, indistinguishable in outcome from an
  asset with no `policy_doc` field at all (FR-062); a separate unit test proves
  `scripts/quote_compare.py` performs zero insurer journeys and writes a report stating the
  exclusion when the targeted asset's `currently_insured` or `policy_doc` is `"n/a"` (FR-063,
  FR-064).

## Assumptions

- Progressive's landing page (`https://www.progressive.com/auto/`) loads under headless Chrome and
  its quote-start form selectors (`#zipCode_mma`, `#qsButton_mma`) resolve, verified by the
  orchestrator before this feature was scoped. Everything past that page is unverified at spec
  time; FR-032 and D8 (research.md) govern how implementation-time recon closes that gap.
- The Director's `profile` vault item holds three top-level JSON arrays and one top-level object,
  per `profile.template.json` (the enforced contract, repository root) and the Director's own live
  document, finalized across amendments 4, 5, 6, and 7: `identities` (elements discriminated by
  `type`; `"self"` and `"spouse"` share one field template - `first_name`/`last_name`/`dob`/
  `email`/`phone`, plus a nested `licence` object with its own `number`/`state` fields, i.e.
  `identities.self.licence.number` - **not** a flat `licence_number`/`licence_state` pair, an
  earlier draft's own assumption, now superseded; `identities` elements carry no
  `currently_insured` field - that moved to the asset arrays below); `addresses` (elements
  discriminated by `type`: `"home"` and a future `"rental"` share `line1`/`city`/`state`/`zip`,
  `currently_insured`, `policy_doc`, and `dwelling_type` [a dwelling classification - example
  values `single_family`/`condo`/`apartment`/`townhouse`/`commercial`; named `dwelling_type`
  rather than `type` because `type` is the array's own selection discriminator]; a third element,
  `"work"`, exists with `dwelling_type` `"commercial"` and both `currently_insured` and
  `policy_doc` set to the `"n/a"` sentinel); `vehicles` (elements discriminated by `type`;
  `"primary"` fields `vin`/`year`/`make`/`model`/`currently_insured`/`policy_doc`); and
  `feature_configs` (`insurance.companies`, a JSON array of insurer id strings - **there is no
  `current_policy` field anywhere in `profile`, and none is ever planned**, D3's second revision;
  each insured asset's own `policy_doc` PDF path is the reference instead, extracted and
  Director-confirmed per D15, FR-050 through FR-064). The literal string `"n/a"` in
  `currently_insured` or `policy_doc` is a defined, Director-decided exclusion sentinel (FR-061),
  never a real value. This delivery has not itself read `profile.template.json` (it is not yet in
  this worktree, per research.md D12/D14's own worktree-gap note) - every field name above is
  assumed from the amendment text that describes it, not independently verified against the file's
  own bytes, and self-diagnoses the same way any other wrong assumption already does through
  `ProfileRegistry`'s existing `REFUSED: registry path ...` error, naming the path, never a value.
- `pypdf` (a new runtime dependency this delivery adds to `requirements.txt`) is assumed
  installable and importable in the project's own `.venv` on the Director's machine; this delivery
  does not pin or verify a specific version, the same lightly-specified assumption spec 004 made
  for `age`'s own availability.
- Extraction quality against the Director's real policy PDF is unknowable at spec-authoring time -
  no real PDF has been seen or recon'd. This delivery specs the extraction pipeline as
  deliberately best-effort, with the mandatory Director confirmation step (FR-053 through FR-055)
  as the correctness backstop, not the heuristics themselves; heuristic tuning against whatever the
  first real extraction attempt actually produces is expected, ongoing follow-up work, not a defect
  in this delivery (research.md D15).
- `addresses.*.dwelling_type` and the `"work"` address element are both seeded in the Director's
  profile now for future features (a property-insurance spec, and a future auto-funnel commute or
  garaging-address question, respectively) and are both out of this delivery's own scope (FR-036,
  FR-065, FR-066) - present in the document, never read by anything this delivery ships.
- The Director's own Progressive account exists and the Headless Chrome profile can reach a
  logged-in or logged-out quote flow depending on which the funnel actually presents; this
  delivery does not assume which.
- `age` vault interaction (v0.0.4) is unchanged by this feature: any errand touching the vault -
  including `scripts/quote_compare.py`'s own read of `profile`'s `feature_configs.insurance`
  object, `scripts/policy_extract.py`'s own read of `profile`'s `addresses`/`vehicles` arrays, and
  each mapped insurer's own registry-sourced fields - still prompts for the passphrase on that
  call's own controlling terminal, every time, with no caching.
- Within a single `scripts/quote_compare.py` invocation, the passphrase is not necessarily
  prompted only once: the orchestrator's own read of `profile` constructs its own `AgeBackend`
  instance, and each mapped insurer's own `Errand.run()` call constructs a further, separate
  `AgeBackend` instance internally (today's existing `open_vault()` contract, unchanged by this
  feature) - so a single invocation with N mapped insurers prompts up to N+1 times, not once. This
  is a known, accepted residual of reusing each insurer's existing single-errand `Errand.run()`
  machinery unmodified rather than threading one shared vault instance through every insurer's
  run; it is recorded here rather than solved, since solving it would mean changing
  `Errand.run()`'s signature for every existing and future errand to accept an
  externally-constructed vault, a change this delivery's own scope (one mapped insurer) does not
  yet justify. Revisit if a later insurer count makes the prompt count materially worse.
- No aggregator or comparison-shopping site (a Zebra-style service) is used anywhere in this
  feature: every quote is fetched directly from its own insurer's site, because sharing the
  Director's identity data with a third-party aggregator is a materially different privacy
  decision than typing it into the insurer he is actually considering, and was never asked for.
- `reports/` is a new top-level directory, sibling to `previews/`, created on first use exactly
  the way `previews/` already is - no setup step, no migration.
- `profile.template.json` and `scripts/vault.py get` both already exist on `main`, ahead of and
  independent of this delivery (research.md D12 and D14); this worktree's own `v0.0.5` branch,
  forked before either landed, does not yet contain them. Neither gap is something this
  spec-authoring delivery is authorized to close (no merge, no pull, per its own brief) - both are
  recorded as known, expected gaps this specific worktree carries until it merges forward from, or
  is rebased onto, current `main`.

## Out of Scope

- Any second insurer's walk (a `"geico"`, `"statefarm"`, or similar entry in the code-level walk
  registry): each insurer's funnel is its own selector-mapping project, independently recon'd and
  independently specced, starting at spec 006 or later. Spec 005 delivers the framework and
  exactly one mapped insurer, Progressive.
- Any LLM-derived value anywhere in the comparison or recommendation path: the comparison engine
  is pure, deterministic Python; nothing a model infers is ever a premium, a limit, or a
  recommendation figure (FR-020), extending the constitution's existing "nothing an LLM derives is
  ever typed" rule to reading and comparing as well as typing.
- Storing quote history or trend data beyond the freshest capture per insurer: this delivery
  compares against the freshest capture on disk; it does not build a time series, a chart of
  premium changes over time, or any analysis beyond one point-in-time comparison per report.
- Any purchase, submission, verification, or one-time-code action, anywhere in any walk this
  delivery or any future insurer walk built on this framework ships: the walk framework itself has
  no step type for it (FR-010), and this is a permanent constraint, not a temporary scope
  boundary.
- Emailing, sharing, uploading, or otherwise transmitting the rendered report anywhere: it is
  written to local disk only, under the same vault-grade classification as everything else in
  `reports/` (FR-015).
- Any change to how headless Chrome identifies itself (a user-agent spoof, a stealth-mode
  browser plugin, or similar): if Progressive's funnel refuses headless Chrome during recon, the
  response is a `HumanStep`, never a user-agent workaround - that remains the repository's
  standing, unresolved question (`PATTERNS.md`'s "Quiet by default" entry), not something this
  feature attempts to solve.
- Hand-seeding a `current_policy` JSON object anywhere in the vault, by any means: this design was
  this spec's own original approach and is now permanently superseded (D3, second revision) - the
  current-policy reference comes only from `scripts/policy_extract.py`'s PDF extraction plus
  Director confirmation (FR-050 through FR-060), never from hand-typed JSON.
- OCR, or any other mechanism for reading a scanned-image PDF with no extractable text layer:
  `pypdf`'s own text extraction assumes a text-layer PDF (the ordinary case for an insurer-issued
  policy document); a scanned image with no text layer simply parses zero coverage lines, which is
  not a distinct failure mode this delivery handles specially - it degrades exactly like any other
  zero-lines-parsed extraction (FR-058), never crashes, and is never treated as a reason to add an
  OCR dependency.
- Heuristic-parsing quality beyond what implementation-time recon and the first real Director UAT
  extraction actually prove (research.md D15): the parsing rules this delivery ships are a
  starting point, not a tuned-and-final set - ongoing tuning against real insurer declarations-page
  layouts is expected, accepted follow-up work, not a defect to close before shipping.
- Extraction, caching, or comparison for any asset other than `vehicles.primary` (FR-060): a future
  homeowners- or renters-insurance spec would extend this delivery's own extraction mechanism
  (`scripts/policy_extract.py` is already asset-generic, FR-050) to a second asset key, but
  `scripts/quote_compare.py`'s own comparison targets exactly one asset in this delivery.
- Building any GUI, dashboard, or notification mechanism around the report beyond the HTML file
  itself: opening the file in a browser is the entire interface this delivery ships.
- Wiring `identities.spouse.*` into any walk: it is seeded in the Director's profile now for a
  future multi-driver mapping feature, not this one. No `FieldPlan`, `ClickStep`, `HumanStep`, or
  `CaptureStep` this delivery ships references it (FR-036, SC-015).
- Wiring `addresses.rental.*` or `addresses.work.*` into any walk: seeded now for a future
  renters-/landlord-insurance spec and a future commute-aware auto spec, respectively, not this
  one. The same guard (FR-036, SC-015) applies to both.
- Wiring `addresses.*.dwelling_type` into any walk: seeded now for a future property-insurance
  spec, not this one (FR-036, FR-065, SC-015).
- Implementing or testing `scripts/vault.py get NAME` as part of this delivery's own work: it is
  already shipped, on `main`, as hotfix v0.0.4.1, ahead of and independent of this feature (see
  the Vault CLI amendment status note above and research.md D12). This spec records its contract
  because spec 005's own quickstart uses it; building or testing it is not a tasks.md item here.
- Recreating or duplicating `profile.template.json` as a second file, anywhere: it already exists
  at the repository root, shipped independently of this delivery (FR-049, research.md D14). Any
  field this delivery's own recon proves is needed and the template does not yet define is added
  by extending that one file, in the same change that references it - never by inventing a second,
  parallel schema document.
