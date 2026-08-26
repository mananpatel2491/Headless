# Research: Insurance Quote Comparison

**Feature**: 005-insurance-quote-comparison | **Date**: 2026-08-25

D1-D10 mirror the decisions the orchestrator made and fixed before this feature entered planning;
they are not re-opened here, only recorded with their evidence and the alternatives that were
considered and rejected, the same shape `specs/003-login-persistence/research.md` and
`specs/004-age-vault/research.md` already established for this repository.

## Verified facts, confirmed by the orchestrator before this feature was scoped

- `https://www.progressive.com/auto/` loads under headless Chrome; page title reads "Car
  Insurance: Get a Quick Auto Insurance Quote | Progressive".
- The quote-start form on that landing page: ZIP input `#zipCode_mma` (`name="ZipCode"`,
  `type="tel"`), submit button `#qsButton_mma`.
- A site-search form also exists on the same page (`#searchTerm`) - close enough in shape to the
  quote-start form that any selector chosen for the quote flow must be specific to it, not a
  loose match that could also hit the search box.
- The funnel past the landing page is **not** recon'd as of this feature's spec-authoring
  delivery. No selector past `#qsButton_mma` is verified. This spec-authoring delivery is barred
  from launching a browser (its own brief); implementation-time recon (D8 below) is the first
  point at which anything past the landing page can be verified.
- The Director's `profile` vault item is seeded; its top-level keys were originally confirmed
  `identity`, `address`, `vehicle`, `licence`. Sub-keys (`identity.first_name`,
  `address.home.zip`, and similar) were assumed, not directly confirmed key-by-key, and
  self-diagnose through `ProfileRegistry`'s existing `REFUSED: registry path ...` error if wrong
  (spec Assumptions). By Director amendment 2026-08-25 (six rounds across one session), the
  Director's actual live document turned out to hold three top-level JSON arrays (`identities`,
  `addresses`, `vehicles`, each element discriminated by a `type` field) plus a top-level
  `feature_configs` object (holding `insurance.companies`, this feature's own sub-object) -
  superseding an original assumption, an intermediate nested-block proposal (D11, superseded), and
  an intermediate top-level-`insurance` proposal (an earlier form of D3, also superseded). There is
  no `current_policy` field anywhere in this shape, by final Director decision (D3's second
  revision, D15) - each insured asset (an `addresses[]`/`vehicles[]` element) instead carries its
  own `policy_doc` PDF path. See D13 for the array-addressing mechanism the three arrays require
  and D14 for `profile.template.json`, the file that is now the enforced contract for this shape.
  Nothing in this repository independently re-verifies the Director's own document against that
  template - this delivery has not read the template's own bytes either (D14) - so every field
  name is still an assumption that self-diagnoses the same way any prior one already did.
- `ProfileRegistry.get` (`headless/profile.py`) raises `RegistryMissing` for any dotted path that
  resolves to a `dict` or a `list`, not only for a path that resolves to nothing - confirmed by
  reading the module directly (`if isinstance(node, (dict, list)): raise RegistryMissing(dotted)`).
  This is the fact that makes D3 below a structural necessity, not a style preference.
- v0.0.4 (spec 004-age-vault): any errand touching the vault prompts for the passphrase once per
  run, on that run's own controlling terminal, in every mode, with no caching across processes.
  v0.0.3 (spec 003-login-persistence): a seeded login persists across runs through the
  launched-profile session-cookie mechanism.

This is the evidence base for D1 through D18 (D11 through D18 were all added 2026-08-25,
mid-delivery, across the amendment rounds spec.md's own amendment note enumerates - see each
entry's own dating; D11 is superseded by D13 and left standing only as historical record; D3 was
revised twice in place, most recently to delete `current_policy` from `profile` entirely and
replace it with D15's own
extraction-and-confirmation mechanism).

## D1. Program shape: framework plus exactly one mapped insurer this delivery

- **Decision**: spec 005 delivers (a) the walk framework, (b) the quote capture model, (c) the
  deterministic comparison engine, (d) the HTML report generator, and (e) exactly one mapped
  insurer, Progressive. Every additional insurer is its own future spec (006 or later). The report
  renders a "not mapped yet" row for any insurer on the Director's `feature_configs.insurance.
  companies` list with no registered walk.
- **Rationale**: the Director's own brief describes a program ("get quotes from multiple
  insurance companies"), not a single errand - but each insurer's quote funnel is an independent,
  unrecon'd surface with its own selectors, its own bot-defense behavior, and its own unknown
  depth of automatable steps. Mapping a second or third insurer inside this same delivery would
  mean shipping selectors for sites nobody has looked at yet, which the Director's own recorded
  house rule (`PATTERNS.md`'s repeated "ship only working code" thread, most recently spec 002's
  false-positive correction) already rules out. Framework-plus-one-real-insurer is the smallest
  slice that proves the whole shape end to end while shipping zero unproven selectors.
- **Alternatives considered**: shipping the framework alone, with no real insurer, deferring
  Progressive to its own spec (rejected: an unexercised framework is exactly the kind of
  speculative structure `specs/004-age-vault/research.md` D3 already argued against for a
  different design choice - without one real walk crossing it, the framework's own shape cannot be
  validated, only guessed at); mapping two or three insurers now to make the comparison engine's
  "multiple companies" story feel more real at ship time (rejected: each additional insurer is
  its own recon project with its own unknown risk, and this delivery's own brief is explicit that
  each one is a future spec, not a checklist item to rush through here).

## D2. Walk model: four step kinds, `Errand.walk(registry)`, mode-specific execution

- **Decision**: `Step` is one of `FieldPlan` (existing), `ClickStep(name, selector)`,
  `HumanStep(name, instruction)`, or `CaptureStep(name, extractors)`. `Errand.walk(registry)`
  returns the ordered list; the default implementation wraps `plan(registry)` unchanged, so no
  existing or future `plan()`-only errand needs to change. Apply mode executes every step in
  order, dispatching by type. Preview mode resolves and records `FieldPlan` sources (masked) and
  lists every other step by kind and name, executing nothing beyond the initial page load - preview
  never navigates past the landing page, in any mode, for any insurer. Check mode is unchanged: it
  probes only `Errand.dependencies`, never a walk's later steps. `HumanStep` is executed through
  the existing `Session.handoff(instruction)` call (no new session method): it surfaces the window
  (a no-op past the first call in a run, since the window is already visible by then), prints
  `Your turn: <instruction>`, waits for the Director, and returns control to the walk - the walk
  continues afterward, it does not end there the way today's single trailing handoff does.
- **Rationale**: reusing `handoff()` verbatim for `HumanStep`, rather than inventing a second
  window-surfacing method, is the simplest design that satisfies "the window stays visible for the
  rest of the run after the first handoff" (spec FR-004): `_restore_window()` already applies its
  bounds/bring-to-front sequence unconditionally and harmlessly whether or not the window was
  already visible, so calling `handoff()` a second time for a second `HumanStep` is naturally
  idempotent with zero new code. Keeping `Errand.run()`'s existing unconditional trailing
  `session.handoff(self.HANDOFF)` call unchanged - rather than adding a conditional that skips it
  when the walk already contained a `HumanStep` - was a deliberate simplicity choice: a
  conditional there would be new branching logic in a state machine every existing and future
  errand depends on, to save the Director one extra Enter-press at the very end of a walk that
  already asked for several. `HANDOFF` for a walk-based errand is simply documented as whatever
  the walk's own author wants it to mean once the walk is done (for Progressive: reviewing the
  report, not a browser action) - no new mechanism required.
- **Alternatives considered**: giving `Errand.run()` a rule that skips the trailing handoff when
  the walk already contains a `HumanStep` (rejected: adds a new conditional to a state machine
  every prior and future errand shares, to solve a minor UX redundancy - one extra Enter-press -
  that costs nothing structurally and is fully backward-compatible to leave alone); a dedicated
  `Session.human_step(instruction)` method distinct from `handoff()` (rejected: the two have
  identical contracts - restore the window, print "Your turn: X", wait for confirmation - and a
  second method with the same body would be exactly the kind of "second, independently-reviewed
  implementation of the same job" spec 004's own D6 already argued against when it chose to reuse
  `_export_session_cookies`'s atomic-write shape rather than invent a new one); letting preview
  mode execute `ClickStep`s (on the theory that navigating a little further would make the preview
  more informative) (rejected outright: this is the one property spec.md itself states as a hard
  constraint, SC-001, precisely because a preview that clicks through a live funnel is no longer a
  safe, no-site-writes default - the entire "default run = PREVIEW" hard rule in `CLAUDE.md` exists
  to make a no-flags run always safe, and a walk that clicks during preview would quietly break
  that guarantee the first time any future insurer's `ClickStep` happened to sit behind a
  state-changing action).

## D3. `feature_configs.insurance.companies` inside `profile`; `current_policy` deleted, replaced by per-asset `policy_doc` - REVISED A SECOND TIME 2026-08-25

**This entry has now been rewritten in place twice. Its first form proposed `insurers`/
`current_policy` as two independent vault items; its second form (still visible in this
document's own edit history, not reproduced here) moved both inside a top-level `profile.insurance`
object. Both are superseded below by the Director's own finalized document shape. Rewritten in
place again, not left standing beside a third, newer decision, for the same reason every other
amendment in this document corrects rather than accumulates.**

- **Decision, part one - `feature_configs`**: the insurer list moves one level deeper than its
  second form proposed: `profile.feature_configs.insurance.companies` (a JSON array of insurer id
  strings), not `profile.insurance.companies`. `feature_configs` (snake_case) is the Director's own
  finalized top-level key for anything this repository's own features configure about his profile,
  as opposed to household data the profile describes for its own sake (`identities`/`addresses`/
  `vehicles`) - `insurance` is 005's own sub-object inside it, and a future feature would add its
  own sibling sub-object there rather than a new top-level key. Read by
  `scripts/quote_compare.py` via `json.loads(vault.get_secret("profile"))["feature_configs"]
  ["insurance"]["companies"]`, still never through `ProfileRegistry.get` (unchanged reasoning:
  `ProfileRegistry`'s scalar-only refusal governs `FieldPlan` sourcing, not a bulk document read).
- **Decision, part two - `current_policy` is deleted, permanently**: there is no `current_policy`
  field anywhere in `profile`, in either its `feature_configs.insurance` sub-object or anywhere
  else, and none is ever planned. The Director's own words: "current_policy info is meant to be
  provided via policyDoc. Instead of manually adding data in profile, intent is to provide pdf
  format policy doc reference for existing policy using which the asset is insured." Each insured
  asset - an `addresses[]` element (`home`, future `rental`) or a `vehicles[]` element (`primary`,
  future additional vehicles) - carries its own `policy_doc` field: a filesystem path to a PDF of
  the policy currently covering that specific asset, plus its own `currently_insured` field
  (moved here from `identities` in an earlier, now-superseded amendment - D13's own array
  addressing makes `registry:vehicles.primary.currently_insured` exactly as natural a path as
  `registry:identities.self.currently_insured` was). `scripts/policy_extract.py` (D15) turns that
  PDF into the same `CurrentPolicy`-shaped reference this spec has used since its original design -
  the shape is unchanged; only how it comes to exist has changed, from hand-typed JSON to
  deterministic PDF extraction plus mandatory Director confirmation, cached under `reports/policy/`
  rather than living inside `profile` at all. `policy_doc` itself, like `feature_configs`, is read
  by direct document parse (`scripts/policy_extract.py`'s own `json.loads` over the whole `profile`
  document, iterating `addresses` and `vehicles` to find every element with a `policy_doc` set) -
  not through `ProfileRegistry.get`, because finding "every asset that has this field set" is an
  enumeration over an array, not a single named lookup by `type`, and `ProfileRegistry`'s own
  addressing (D13) was built for the latter, not the former.
- **Rationale, part one**: `feature_configs` as a distinct top-level key, rather than nesting
  `insurance` directly under `profile`'s own root, keeps a clean separation between "data
  describing the Director's household" (`identities`/`addresses`/`vehicles`, useful to any future
  feature that needs an address or a name) and "configuration one specific feature reads to decide
  what to do" (`feature_configs.insurance`, meaningful only to this feature and any of its own
  future siblings) - the same separation of concerns `profile.template.json`'s own two-part shape
  (per-person/per-asset data, versus feature-specific settings) makes explicit.
- **Rationale, part two**: this is the single most consequential correction across all of this
  delivery's amendments, and it happened because the Director's own real intent - comparing quotes
  against a *document he already has*, not a number he would have to type and keep in sync by hand
  - only became clear once he started actually populating his real profile and reached for his
  policy PDF instead of re-typing its contents. Hand-typed JSON asks the Director to transcribe and
  maintain data a PDF he already possesses already states authoritatively; a policy renewal means
  re-typing a whole `current_policy` object by hand under the old design, versus dropping a new PDF
  path under this one. Per-asset `policy_doc` (not one flat `current_policy` on the whole profile)
  is what makes this correct for a household with more than one insured thing (a car and a rental
  home, each with its own policy, its own insurer, and its own renewal date) - a single flat
  `current_policy` field could only ever have represented one of them.
- **Alternatives considered**: keeping `current_policy` hand-typed inside `profile.feature_configs.
  insurance` and treating a PDF path as a documentation convenience only (rejected outright by the
  Director's own stated intent - the PDF is meant to be the source of truth, not a courtesy
  cross-reference to data still typed by hand elsewhere); one `policy_doc` field on `profile`
  itself rather than one per asset (rejected: a household can hold more than one active policy at
  once, and a single field cannot represent that - the per-asset placement is what let this design
  generalize to a future homeowners/renters comparison spec without another restructure); an LLM
  reading the PDF instead of deterministic heuristics (rejected by the same constitutional rule
  D5 already applies to the comparison engine itself, now extended explicitly to extraction: no
  model output may become a comparison figure, confirmed or not - see D15's own rationale for why
  human confirmation, not a model, is the correctness backstop for imperfect heuristic parsing).

## D4. `reports/`: a new sibling directory to `previews/`, derived location, not configurable

- **Decision**: `reports/` (holding `captures/<insurer>-<timestamp>.json` and
  `quote-comparison-<date>.html`) is a new top-level directory, resolved the same way
  `previews/` already is - relative to the repository root, created on first use, no new
  environment variable, no new CLI flag to override its location. `.gitignore` gains `reports/`,
  mirroring `previews/`'s existing entry.
- **Rationale**: `previews/`'s existing resolution rule (`headless/config.py`'s `preview_dir`)
  already has a documented, tested relative-path policy (FIX-FIRST 6, spec 001: resolve against
  the repo root, reject any other relative override). Giving `reports/` its own, independently
  configurable location would mean designing and testing a second version of that same policy for
  no benefit spec.md's own requirements ask for - nothing about this feature needs `reports/` to
  live anywhere other than beside `previews/`, and every prior feature that introduced a new
  persisted location (`session-cookies.json` in spec 003, the vault file in spec 004) only made a
  location configurable when the Director's own brief specifically asked for portability (the
  vault file's cross-platform default, spec 004 D2). Nothing in this feature's brief asks for that.
- **Alternatives considered**: making `reports/` configurable via a new `HEADLESS_REPORTS_DIR`
  environment variable, mirroring `HEADLESS_PREVIEW_DIR` (rejected: adds a second environment
  variable and a second relative-path-refusal policy to design, document, and test, for a
  directory every use case this feature's own spec describes is happy to find beside `previews/`
  - revisit only if a future Director request specifically needs it elsewhere); nesting captures
  and the report under `previews/` itself instead of a new sibling directory (rejected: `previews/`
  is documented, repository-wide, as disposable artifacts safe to delete at any time
  (`PATTERNS.md`: "Previews are disposable ... delete freely") - `reports/quote-comparison-
  <date>.html` is explicitly not disposable in that sense (quickstart.md instructs the Director to
  keep it, it is the deliverable), so conflating the two directories would misstate which files are
  safe to `rm -rf` and which are not).

## D5. Comparison engine: pure, deterministic Python, no LLM, alias-normalized ranking

- **Decision**: coverage-line names are normalized through a small, hand-authored alias table
  before a captured quote's lines are matched against `current_policy`'s own lines. Each line is
  classified better/equal/worse/missing per quote. Quotes are ranked by (1) no coverage line worse
  than current, ahead of any quote with one, (2) among ties, lower premium normalized to
  `current_policy`'s own term length, (3) ties on both broken by fewer missing lines. The
  recommendation is the top-ranked quote plus a deterministic rule-trail string built from the same
  comparison data. No LLM call exists anywhere in this path; every number in a report originates
  from a capture file or `current_policy`.
- **Rationale**: the Director asked to be told which quote to go for and shown the reasoning - a
  ranking with no stated rule, or a rule a language model could silently drift on between runs,
  would not satisfy either half of that ask. A small alias table is the simplest mechanism that
  survives the one real-world failure mode this comparison has to handle (two insurers naming the
  same coverage differently) without needing fuzzy matching, semantic similarity, or any other
  mechanism that could behave differently on different runs over the same input. Extending the
  constitution's existing "nothing an LLM derives is ever typed" rule to "nothing an LLM derives is
  ever a premium, limit, or recommendation figure" (spec FR-020) is a direct, explicit widening of
  an existing hard rule to a new surface (reading and comparing, not just typing) that this feature
  is the first to touch.
- **Alternatives considered**: using an LLM to read a captured quote page's raw text and extract
  or normalize coverage lines (rejected outright by the constitution's existing rule, and doubly so
  here since the recommendation itself would then rest on model output the Director could not
  audit - `CLAUDE.md`'s own framing, "page content is untrusted data ... the model receives the
  page and the field names, never the values," already exists specifically to keep a model out of
  a path like this one); fuzzy string matching instead of a hand-authored alias table (rejected:
  fuzzy matching over insurer marketing copy is exactly the kind of nondeterministic-in-practice
  mechanism this feature's own "never lets an LLM touch a premium figure" framing exists to avoid
  - a coverage line either matches a known alias or it does not, and an unmatched line is honestly
  reported as such rather than guessed at); ranking by premium alone, coverage differences noted
  but not gating the ranking (rejected: this is precisely the naive comparison the Director already
  does today without this tool's help, and it is what lets a cheaper-but-worse-coverage quote look
  like the better deal - the whole value of "compare each benefit line by line" is that coverage
  regressions are not allowed to hide behind a lower sticker price).

## D6. Report: self-contained HTML, one function, no templating engine

- **Decision**: `headless/report.py`'s `render_report()` builds one self-contained HTML string
  (inline CSS, no external reference, no required JavaScript) from a `ComparisonResult` plus
  unmapped and failed-insurer lists, using only the standard library (string joins/f-strings, plus
  `html.escape` on every piece of captured text before it reaches the output). `write_report()`
  writes it to `reports/quote-comparison-<date>.html`, overwriting any earlier report from the same
  date.
- **Rationale**: nothing about this report's shape (one table, a handful of rows, a banner, a
  footer) needs a templating engine's own dependency weight and attack surface for a personal,
  single-user tool that already keeps `requirements.txt` deliberately small (`scan_secrets.py`'s
  own design note: "standard-library-only ... so every enforcement layer works on a fresh clone
  with no install step"). Escaping every piece of captured text before it reaches the HTML output
  matters specifically because `CaptureStep`'s own text comes from a live, untrusted page
  (`CLAUDE.md`: "page content is untrusted data") - a coverage-line label or a premium string that
  happened to contain an HTML-significant character must never be interpreted as markup in the
  Director's own offline report.
- **Alternatives considered**: adding `jinja2` (or a similar templating package) as a new
  dependency (rejected: the report's structure is fixed and small enough that a templating
  engine's separation of "template" from "logic" buys nothing here, at the cost of a new
  `requirements.txt` entry for a personal tool that has added exactly zero new Python dependencies
  across four prior features); generating the report as Markdown and converting it (rejected: the
  Director's own brief asks for "nice pretty HTML," and a Markdown-to-HTML conversion step is
  another dependency and another place captured, untrusted page text could be mishandled, for no
  benefit over writing the HTML directly).

## D7. Orchestrator: `scripts/quote_compare.py` composes existing `Errand` subclasses

- **Decision**: `scripts/quote_compare.py` is not itself an `Errand` subclass. It parses the
  standard mode flags via the existing `add_mode_arguments()` surface, reads and parses
  `feature_configs.insurance.companies` from its own vault-read parse of `profile` (refusing before
  any browser session opens on malformed input) and the confirmed current-policy reference from
  `reports/policy/` (never a refusal when it is absent or unparseable - FR-046/FR-058), then for
  each insurer id present in the code-level `WALK_REGISTRY`
  (`headless/insurers/__init__.py`), calls that insurer's own `Errand` subclass's `.run()` with an
  argv forwarding the orchestrator's own parsed flags - reusing that subclass's entire existing
  machinery (config resolution, its own vault access, the pre-resolution loop, gate checks, preview
  artifact writing, apply's window handling) unmodified. An insurer id with no registry entry
  produces a "not mapped yet" row with zero `Session`/`Config`/browser-process construction. In
  apply mode, after every mapped insurer's run has returned (successfully or not), the orchestrator
  runs `compare.build_comparison()` and `report.write_report()`. One insurer's non-zero return code
  is recorded value-free and never stops the remaining insurers or the report step.
- **Rationale**: reusing each insurer's own `Errand.run()` call, rather than building a second,
  parallel execution path that reimplements gates/redaction/pre-resolution for a multi-insurer
  context, is what keeps every existing safety guarantee (preview never writes, apply never submits,
  every secret pre-resolves before any window opens) automatically true for every future insurer's
  walk with zero new code to audit for those properties - the cost is the accepted N+1-passphrase
  residual spec.md's Assumptions section documents (each mapped insurer's own `Errand.run()` call
  constructs its own fresh `AgeBackend` instance, exactly like it does today for any single-site
  errand run alone, since `open_vault()`'s existing per-call construction is unchanged by this
  feature). Value-free failure isolation per insurer directly implements spec FR-029/NFR-004 - it
  has to happen in the orchestrator's own loop, since `Errand.run()` already guarantees it never
  raises past its own boundary (every exception path in `errand.py`'s existing `run()` prints a
  value-free line and returns a non-zero int, never an unhandled exception), so the orchestrator
  only has to check that return code, never catch a raw exception itself.
- **Alternatives considered**: giving `scripts/quote_compare.py` its own `Session`/`Config`/vault
  construction, threading one shared vault instance through every insurer's walk to collapse the
  passphrase prompt count to exactly one per invocation (rejected for this delivery: doing so would
  mean changing `Errand.run()`'s own signature - and every existing and future errand's contract -
  to accept an externally-constructed vault instead of building its own, a change this delivery's
  scope of exactly one mapped insurer does not yet justify; recorded as a residual to revisit once
  a second mapped insurer makes the prompt count materially worse, not silently designed around
  now); making each insurer's walk failure abort the whole orchestrator run (rejected outright:
  this is precisely what User Story 4 and FR-029 exist to prevent - a comparison tool that goes
  dark the moment any one insurer's site has a bad day would defeat the point of comparing several
  at once).

## D8. Progressive walk depth: implementation-time recon, bounded and synthetic

- **Decision**: the shipped Progressive walk begins with the two selectors already verified before
  this feature was scoped (`#zipCode_mma` filled from `registry:addresses.home.zip`,
  `#qsButton_mma` clicked) and continues only as far as implementation-time recon actually proves.
  That recon is authorized for at most three headless, scratch-Chrome-profile walks against the
  real Progressive site, using wholly synthetic data - never the Director's real identity, address,
  date of birth, or licence data - and never clicking a purchase, submit, or payment control at any
  point. If the funnel refuses headless Chrome at some point during that recon, the refusal itself
  is recorded here as evidence for the repository's standing headless-user-agent question
  (`PATTERNS.md`'s "Quiet by default" entry); the walk still ships whatever depth recon proved,
  with a `HumanStep` bridging every point recon could not cross or verify. An unproven selector is
  never shipped, regardless of how confident a guess at it might be.
- **Rationale**: this delivery's own spec-authoring brief bars it from launching a browser at all,
  so nothing past the landing page can be verified in this delivery - the actual recon, and
  therefore the actual shipped walk depth, is necessarily an implementation-time activity, not
  something this research phase can perform or predict. Bounding it to three scratch-profile walks
  with synthetic data keeps the recon itself cheap, disposable (a scratch profile, not the
  Director's seeded Headless profile), and free of the exact privacy risk the walk framework exists
  to protect against once it is actually seeded with the Director's real data. Recording a
  headless-refusal outcome as evidence, rather than treating it as a delivery blocker, matches how
  this repository has already handled every other empirically-discovered platform limitation
  (`PATTERNS.md`'s own "hiding is best-effort, not a hard guarantee" and "this Chrome DOES report
  HeadlessChrome" entries) - state what was actually found, ship what actually works, and let a
  documented residual carry forward rather than blocking on a question this feature was never
  scoped to resolve.
- **Alternatives considered**: performing the funnel recon as part of this spec-authoring delivery
  (rejected: this delivery's own brief explicitly bars launching a browser; recon is implementation
  work, not specification work, and conflating the two would mean this document asserting selectors
  nobody has actually verified - the exact failure mode "ship only working code" exists to prevent);
  no bound at all on how many scratch-profile walks recon may perform (rejected: an unbounded recon
  budget against a live, unrecon'd site risks tripping the same kind of bot-defense behavior this
  feature's own edge cases already have to account for, before implementation has even started -
  three is enough to map a typical few-page quote funnel's happy path without turning recon itself
  into a stress test of Progressive's own bot defenses); using the Director's real seeded Headless
  profile for recon instead of a scratch profile (rejected: recon by definition explores unknown
  territory - a scratch profile means a discovery mistake during recon (an accidental click, an
  unexpected redirect) cannot touch the Director's own logged-in session state).

## D9. Out of scope

- **Decision**: this feature does not map any second insurer's walk (006 or later); does not let
  an LLM touch any premium, limit, or recommendation figure, in typing or in comparison; does not
  store quote history or trend data beyond the freshest capture per insurer; does not add a
  submit/pay/verify/otp step type, or ever click a purchase control, in this walk or any future
  insurer walk built on this framework; does not email, share, or transmit the rendered report
  anywhere; does not attempt any user-agent spoof or stealth-browser workaround if Progressive's
  funnel refuses headless Chrome; does not OCR a scanned-image PDF (see D15's own out-of-scope
  note); and does not build any GUI, dashboard, or notification mechanism beyond the HTML file
  itself.
- **Rationale**: each of these was named explicitly in the brief this feature was scoped from, as a
  boundary already decided rather than a question this research phase needed to resolve, the same
  shape spec 003's D9 and spec 004's D10 both already used for their own out-of-scope items.
- **Alternatives considered**: three specific alternatives were named in this feature's own brief
  and are recorded here for the same reason spec 004's D10 recorded its own rejected alternatives -
  as evidence the boundary was considered, not merely defaulted to. **Full multi-insurer mapping in
  one spec** (rejected: each insurer's funnel is its own independent selector-mapping project with
  its own unrecon'd risk - see D1). **LLM-assisted form detection or coverage-line extraction**
  (rejected by the constitution's existing "nothing an LLM derives is ever typed" rule, extended
  by this feature's own FR-020 to cover reading and comparing too - see D5). **Screenshot-only
  capture, comparing quotes visually rather than structurally** (rejected: a line-by-line
  comparison, which is what the Director explicitly asked for, needs structured data a screenshot
  cannot provide - `headless/session.py`'s own screenshot masking already establishes that a
  screenshot is a visual aid, not a data source, and this feature's `CaptureStep` needs the latter).
  **Aggregator or comparison-shopping sites (a Zebra-style third party)** (rejected: routing the
  Director's identity and coverage data through a third party the Director did not ask to trust is
  a materially different privacy decision than typing it directly into the insurer's own site he is
  actually considering - `CLAUDE.md`'s entire premise is a tool that operates *the Director's own*
  accounts on *his* behalf, not a broker relationship with a fourth party).

## D10. Coverage-line alias table: hand-authored, not learned

- **Decision**: the alias table `compare.py` uses to normalize coverage-line names is a small,
  hand-authored Python mapping (a handful of common US auto-insurance coverage categories - bodily
  injury liability, property damage liability, collision, comprehensive, uninsured/underinsured
  motorist, medical payments/personal injury protection - each mapped from a short list of common
  phrasings to one normalized key), extended by hand whenever a real insurer's own wording does not
  already match an existing entry. It is not learned, inferred, fuzzy-matched, or LLM-generated at
  any point.
- **Rationale**: this is a direct, narrower restatement of D5's own "no LLM anywhere in this path"
  decision, called out separately because the alias table specifically is the one piece of this
  feature most tempting to build as a learned or fuzzy-matched mechanism instead - and because
  Progressive's own actual coverage-line wording is not yet known at spec-authoring time (D8: the
  funnel is unrecon'd past the landing page), the table's exact starting contents are necessarily
  an implementation-time task informed by whatever recon or the Progressive quote page itself
  actually shows, not something this research phase can pre-populate correctly.
- **Alternatives considered**: covered under D5's own alternatives (fuzzy matching, LLM-assisted
  normalization); the one additional alternative specific to this table - a fully static table
  frozen at implementation time with no path to extend it for a second insurer's different wording
  later - was rejected because D1 already commits this repository to more insurers over time, each
  with its own coverage-line phrasing, and a table that cannot grow would silently start reporting
  a real coverage line as unmatched the moment a second insurer used different words for the same
  thing.

## D11. Registry shape restructure, first proposal (Director decision, 2026-08-25) - SUPERSEDED by D13

**Superseded the same day, once the Director's actual live document turned out to use true JSON
arrays rather than the nested-block shape proposed here. Left standing, unrewritten, as the
historical record of the decision trail - D13 is the current, authoritative design; nothing below
should be treated as this delivery's shipped shape.**

- **Decision**: while this feature was being specced, the Director began updating his `profile`
  vault item to a wider shape the orchestrator supplied, superseding the sub-key assumptions this
  research phase originally recorded. The new shape: `identity.first_name`/`.last_name`/`.dob`/
  `.email`/`.phone`/`.currently_insured` (`"yes"` or `"no"`, new field); `spouse.first_name`/
  `.last_name`/`.dob`/`.licence_number`/`.licence_state` (new top-level key); `address.home.line1`/
  `.city`/`.state`/`.zip` (unchanged); `vehicle.primary.vin`/`.year`/`.make`/`.model` (`vehicle.vin`
  and its siblings are gone - `vehicle` becomes a container of named blocks, `primary` being the
  only one this delivery addresses); `licence.number`/`.state` (unchanged); and
  `property.rental.line1`/`.city`/`.state`/`.zip`/`.type` (new top-level key). Every place this
  feature's own spec set named the old flat `vehicle.*` shape is updated to `vehicle.primary.*`;
  `spec.md`'s Assumptions and Out of Scope sections record the two new top-level keys as
  seeded-but-unused in this delivery (D-decision below, and FR-036/SC-015).
- **Rationale**: the driving fact is the same one D3 already established for `insurers`/
  `current_policy` - `ProfileRegistry.get` (`headless/profile.py`) refuses any dotted path that
  resolves to a `dict` or a `list`, not only one that resolves to nothing. A second car cannot ever
  be addressed as `vehicle[1]` or `vehicle.1.vin` under this registry's own existing design; the
  only way a second, third, or later vehicle can ever be added without a code change anywhere in
  `headless/profile.py` is for `vehicle` to already be a container of named, individually
  addressable blocks (`vehicle.primary`, later `vehicle.second`, and so on) rather than a single
  flat set of scalar fields. Restructuring `vehicle.vin` to `vehicle.primary.vin` now, before this
  feature's own Progressive walk (FR-031) ever references it in a shipped `FieldPlan`, costs
  nothing and avoids a second migration once a real second-car scenario arrives. Adding `spouse`
  and `property` as new top-level keys now, ahead of the specs that will actually use them, matches
  the Director's own stated intent (a household's insurance profile, not only one driver's) and
  costs this delivery nothing beyond an explicit "not wired yet" guard (FR-036), since a registry
  document can hold keys no current errand references without any structural cost - `profile.py`'s
  own dotted-path lookup simply never visits a branch nothing points at.
- **Alternatives considered**: keeping `vehicle.vin`/`.year`/`.make`/`.model` flat and addressing a
  second car with a differently-named top-level key (e.g. `vehicle2.vin`) instead of nesting under
  `vehicle` (rejected: this would mean every future car gets its own top-level key, growing the
  registry's own top-level key set without bound and giving `vehicle`/`vehicle2`/`vehicle3` no
  shared, discoverable relationship the way `vehicle.primary`/`vehicle.second` already has by
  construction - a walk mapping `vehicle.primary.vin` at least documents, in the path itself, that
  more entries of the same shape may exist alongside it); deferring the restructure until a second
  insurer's spec or a real second-car scenario actually needs it (rejected: the Director is
  updating his own profile document right now, during this feature's own spec-authoring window -
  waiting would mean this feature's own Progressive walk ships against a shape the Director's real
  vault item no longer matches, guaranteeing an avoidable `REFUSED: registry path 'vehicle.vin'...`
  the first time anyone actually runs it); seeding `spouse`/`property` only once their own future
  specs exist, rather than now (rejected by the Director's own instruction - he is populating the
  full household shape in one sitting, not incrementally per future feature, and this delivery's
  only obligation in response is to guarantee neither is wired prematurely, which FR-036 already
  does structurally rather than by leaving the data simply absent).

## D12. `scripts/vault.py get NAME`: already shipped, out of this delivery's own build scope

- **Decision**: the Director wanted `vault.py get NAME` immediately - a command to fetch the
  existing `profile` document to the terminal so he can copy it into an editor (Sublime), edit it
  to match D11's new shape, and paste the result back via `vault.py set profile`. Rather than wait
  for this delivery, the orchestrator shipped it directly as hotfix v0.0.4.1 on `main`
  (merge `f35988e`, commit `9cc3b20`, three tests, `scripts/README.md` and `Project_Structure.md`
  already updated there), ahead of and independent of spec 005. This feature's own spec set
  (FR-037 through FR-039) records that shipped contract as fact, because spec 005's own quickstart
  uses it in the profile-editing round trip - it is not a `tasks.md` item here, and no test or
  implementation work for `get` belongs to this delivery. This worktree's own `v0.0.5` branch,
  forked from `main` before v0.0.4.1 landed, does not yet contain that hotfix; running
  `vault.py get` inside this specific worktree will not work until `v0.0.5` merges forward from,
  or is rebased onto, current `main` - a mechanical step outside this spec-authoring delivery's own
  scope (no code, no merge, no browser, no `~/.headless/` touch, per this delivery's brief).
- **Rationale**: recording an already-shipped contract as spec fact, rather than re-specifying it
  as new work, keeps `tasks.md` honest about what this delivery actually has to build - duplicating
  `get`'s own implementation and test tasks here would misstate work that is already done and
  already merged, the exact kind of drift `Project_Structure.md`'s own Changelog discipline exists
  to prevent. Naming the exact merge and commit identifiers, rather than only a version number, is
  the same evidentiary standard this document already applies to every other verified fact (the
  landing-page selectors' own recon, `age`'s verified round trip in spec 004's own research.md) -
  a claim this document makes about code state should be traceable to a specific commit, not asserted
  from memory.
- **Alternatives considered**: waiting for spec 005's own implementation delivery to build `get`
  as originally requested (rejected by the Director's own urgency - he needed to start editing his
  profile now, and gating that on this feature's own full spec-through-implement cycle would have
  blocked D11's own restructure from happening promptly); this spec-authoring delivery attempting
  to reconcile or merge the hotfix into the `v0.0.5` worktree itself (rejected outright: this
  delivery's own brief bars touching code, merging, or branches - the hotfix's existence is a fact
  to record, not a change this session is authorized to pull in); silently omitting any mention
  that the `v0.0.5` worktree lacks the hotfix (rejected: a Director or a later session following
  this feature's own quickstart inside this specific worktree, without the caveat, would hit a
  confusing "command not found"-shaped failure with no documented explanation).

## D13. Type-discriminated array addressing in `ProfileRegistry.get` (Director amendment, 2026-08-25)

- **Decision**: the Director's actual live `profile` document holds `identities`, `addresses`,
  and `vehicles` as JSON arrays, each element carrying a `type` field that names what it is
  (`"self"`/`"spouse"`, `"home"`/`"rental"`, `"primary"`). `ProfileRegistry.get`'s dotted-path
  traversal (`headless/profile.py`) gains one new rule: when traversal reaches a list-valued node,
  the next path segment selects the unique element whose `type` field equals that segment exactly,
  and traversal continues from there as if that element had been reached directly. Zero matches
  raise the existing `RegistryMissing(path)`. More than one match raises a new
  `RegistryAmbiguous(path)` - value-free, naming only the path and the fact of duplication, never
  any matched element's own content. An element with no `type` field is never a match candidate.
  A path fully consumed while still pointing at a list or a dict continues to refuse exactly as it
  does today. This is new, general framework capability (`headless/profile.py`), not anything
  specific to insurance or to Progressive - it belongs in spec 005's own Foundational scope because
  the walk framework's own `FieldPlan` sources are the first, and so far only, consumer of a
  `registry:` path that needs it, but any future errand addressing the same `profile` document
  inherits it automatically.
- **Rationale**: this is the mechanism D11's own, superseded proposal was reaching for without
  quite getting there - D11 proposed a nested-block shape (`vehicle.primary.vin`) specifically so a
  second vehicle could become `vehicle.second` "with no code change," but a *dict* of named blocks
  still requires the Director (or a future feature) to invent a new key name (`second`, `third`)
  by hand for every additional entry, with no shared, machine-checkable relationship between them
  beyond convention. A true JSON array with a `type` discriminator is the more natural fit for
  "the same kind of thing, more than one of it" - which is exactly what the Director's own real
  document turned out to need for a spouse, a rental address, and eventually more than one vehicle
  - and `type`-based selection means `ProfileRegistry` itself can enforce "exactly one match or
  refuse," a guarantee a plain dict-of-blocks shape never had (nothing stopped two blocks from
  silently both being named `primary` under D11's own proposal; an array explicitly can hold two
  elements with the same `type`, which is exactly why `RegistryAmbiguous` exists - the shape makes
  a real failure mode possible that the dict shape's own key-uniqueness already prevented for free,
  so this feature has to detect and refuse it explicitly instead of getting the guarantee for
  nothing). Raising a distinct `RegistryAmbiguous` rather than reusing `RegistryMissing` for the
  duplicate case matters because the two failure modes need different remedies from the Director's
  own point of view: "this path does not exist yet" (add it) versus "this path is ambiguous right
  now" (deduplicate an entry that should not have two matches) are different edits to make, and
  collapsing them into one error class would make the message tell the Director less than it
  could.
- **Alternatives considered**: index-based array addressing (`identities.0.first_name`) instead of
  `type`-based (rejected: an index is not stable across an edit that reorders or inserts elements,
  and carries no meaning a person editing the document by hand could rely on - `type` is both
  stable and self-documenting, and matches how the Director already thinks about his own data,
  "myself" and "my spouse," not "element 0" and "element 1"); allowing a partial or prefix match on
  `type` instead of exact string equality (rejected: an exact-match requirement is what makes the
  zero-vs-one-vs-many-matches trichotomy simple and total - a partial-match rule would need its own
  tie-breaking policy for an ambiguous partial match, reintroducing the same problem exact matching
  avoids, for no benefit any real path in this document needs); making a `type`-less element a hard
  error instead of a silent non-match (rejected: a document may reasonably hold array elements this
  feature's own registry traversal never needs to select individually - forcing every element to
  carry a `type` field, whether or not anything ever addresses it by type, would be a constraint on
  the Director's own document shape this feature has no need to impose).

## D14. `profile.template.json`: the enforced schema contract (Director amendment, 2026-08-25)

- **Decision**: a file `profile.template.json`, holding wholly synthetic values in D13's own
  array-and-object shape, was shipped by the orchestrator as a docs-only increment directly on
  `main`, at the repository root, ahead of and independent of this delivery - the same pattern
  D12 already established for `scripts/vault.py get`. This delivery's own test suite gains a
  dedicated drift test (spec FR-048): it loads the template file directly (never through the
  vault, never prompting for a passphrase) and resolves every registry path any shipped walk in
  this delivery references - including the Progressive walk's full field list and
  `vehicles.primary.currently_insured` - through `ProfileRegistry`, exercising D13's own
  array-addressing rule. A path that fails to resolve against the template fails the test. This
  delivery does not recreate or duplicate the template as a second file (spec FR-049); if
  implementation-time recon proves a field is needed the template does not yet define, the same
  change that wires that field into the Progressive walk also extends the template itself, in the
  same commit - the drift test makes this a structural requirement, not a reviewer's reminder.
  This worktree's own `v0.0.5` branch, forked before the template landed, does not have the file
  yet; the drift test's own logic is proven correct in the meantime against a synthetic in-memory
  fixture standing in for it (spec SC-018), a direct drop-in once the real file is present.
- **Rationale**: a schema this delivery only describes in prose (spec.md's own Assumptions
  section) is exactly the kind of documentation that drifts silently from the code that actually
  depends on it - a future walk change could reference `identities.self.some_new_field` without
  anyone noticing the Director's own real document, or its own template, had never been told about
  it, and the failure would only surface at Director UAT time as a confusing `REFUSED: registry
  path ...` with no earlier warning. Making the template an executable test fixture, not only a
  documentation file, closes that gap: a walk change that outruns the template fails the unit
  suite (NFR-002's own zero-browser, zero-prompt, sub-second budget still applies - this is a pure
  in-memory JSON-and-dict-traversal test, no different in kind from any other fixture-driven test
  in this delivery), before it can ever reach a Director UAT session where the failure would be
  more expensive to diagnose. One template file, not one per feature or per test, is what makes
  this guarantee mean anything: if this delivery invented its own parallel copy instead of
  depending on the repository-root file, the two could drift from each other exactly the way a
  documentation-only description already can.
- **Alternatives considered**: describing the schema only in `spec.md`'s Assumptions section, with
  no executable check (rejected: exactly the silent-drift failure mode this decision exists to
  close - a prose description cannot fail a test run); this delivery authoring its own template
  file, independent of the repository-root one the Director's tooling already produced (rejected:
  two schema documents that are supposed to describe the same real `profile` shape, maintained in
  two places, is a needless invitation for them to disagree - the whole point of "one enforced
  contract" is that there is exactly one file to keep current); validating against the Director's
  own real, currently-seeded `profile` vault item instead of a synthetic template (rejected
  outright: that would mean the unit suite decrypting the real vault, prompting for a real
  passphrase, on every test run - directly violating NFR-002's zero-passphrase-prompts guarantee,
  the same reasoning every other test in this delivery's own suite already follows by using fixture
  data instead of the real vault).

## D15. Policy PDF extraction and mandatory Director confirmation (Director amendment, 2026-08-25)

- **Decision**: `scripts/policy_extract.py` (new; not a browser errand, not an `Errand` subclass -
  the same "maintenance-adjacent script" category `scripts/vault.py` and `scripts/scan_secrets.py`
  already establish) reads `profile` once (one passphrase prompt - simpler than
  `quote_compare.py`'s own N+1 residual, since this script constructs exactly one vault instance
  for its own single read), finds every `addresses[]`/`vehicles[]` element with a `policy_doc`
  field set, and for each one: extracts the PDF's text via `pypdf` (a new runtime dependency,
  `requirements.txt`), applies deterministic heuristics only (dollar-amount patterns, split-limit
  patterns such as `100,000/300,000`, deductible-line detection, premium/term detection - never an
  LLM call) to produce a candidate document shaped exactly like this spec's own long-standing
  `CurrentPolicy` (`{"insurer", "premium": {"term_months", "amount"}, "coverages": [{"line",
  "limit", "deductible", "premium"}]}`), prints that candidate to the Director's own terminal, and
  offers exactly two paths forward: accept it as printed, or supply a corrected JSON document at a
  follow-up plain-text prompt (not hidden - the candidate was already shown in the clear moments
  before, so there is nothing to protect by hiding the correction). Declining either path leaves no
  cache file written and is not an error. Only a confirmed document - accepted or corrected -
  gets written to `reports/policy/<asset-key>.json` (data-model.md derives `<asset-key>` from the
  asset's own array name and `type`, e.g. `vehicles-primary`), mode `0600`, with provenance
  (`source_path`, `confirmed_at`). `scripts/quote_compare.py`'s own comparison reads only that
  cache file, for the one asset key this delivery's own comparison targets (`vehicles-primary`,
  since Progressive is an auto insurer) - never `profile` directly, and never an unconfirmed
  candidate. A missing `policy_doc`, a path that does not exist, a file that is not a readable PDF,
  or a PDF from which zero coverage lines could be parsed, all collapse to the same outcome: no
  candidate to confirm, extraction moves on to the next eligible asset (or ends, if there is
  exactly one), and `quote_compare.py`'s own report renders "no current-policy reference for
  vehicles.primary - run scripts/policy_extract.py" instead of refusing - the same "never wasted
  run" property FR-046's own no-current-policy fallback ranking already provides, now serving two
  distinct causes (a genuinely absent reference, and an unconfirmed or unparseable one) through one
  shared mechanism rather than two.
- **Rationale**: printing the candidate to the terminal is the same deliberate, narrowly-scoped
  exception to this codebase's usual value-free-output convention `vault.py get` already
  established (spec FR-039) - here it is the Director's own policy data, printed for the Director's
  own review, on his own terminal, so he can confirm or correct it before it becomes the reference
  every quote is judged against. Mandatory confirmation - not an optional flag, not a "trust the
  extraction" fast path - exists because the extraction itself is explicitly best-effort: a
  declarations page's layout varies enough between insurers, and even between products from the
  same insurer, that no fixed set of deterministic heuristics can be verified correct against every
  real policy PDF that will ever exist, and this delivery has not seen the Director's own real one
  at spec-authoring time (implementation-time recon and Director UAT are what will actually prove
  or disprove any given heuristic, the same "unproven does not ship as authoritative" discipline
  D8 already applies to Progressive's own funnel selectors, applied here to parsed coverage figures
  instead of to selectors). The comparison engine's own no-LLM-anywhere rule (D5, FR-020) is only
  half the safety property this feature needs once a real, unstructured PDF enters the picture -
  a deterministic heuristic parser can still be *wrong* even though it is not a model, and the
  Director's own explicit confirmation, not a second layer of automated validation, is what closes
  that gap for a number that is about to drive a real recommendation. Caching the confirmed
  reference outside `profile` (under `reports/policy/`, already vault-grade per D4) rather than
  writing it back into the vault keeps the vault holding only what the Director himself typed or
  approved through `vault.py`'s own interface - `policy_extract.py` never touches the vault's write
  path at all, mirroring `AgeBackend.put_secret`'s own refusal (spec 004) that kept an errand from
  ever triggering a surprise vault re-encrypt: the same principle, applied to a second script that
  has its own reason to never be a vault-writer.
- **Alternatives considered**: skipping confirmation for a "high-confidence" extraction (a
  heuristic score above some threshold) (rejected: a threshold is itself an unverified, tunable
  guess about extraction quality this delivery has no real PDF to calibrate it against yet - and
  even a well-calibrated threshold would mean a comparison figure could reach the report without
  the Director ever having seen it, which is precisely the property this decision exists to
  prevent); an LLM-assisted extraction pass, with the Director confirming the LLM's output instead
  of a heuristic parser's (rejected: this would still put a model's output in front of the
  Director as if it were a neutral first draft, and the constitution's own "nothing an LLM derives
  is ever typed" rule reads naturally as covering "ever presented as a candidate figure" too - a
  deterministic parser's mistakes are at least reproducible and auditable in a way a model's are
  not, which matters when the thing being audited is the Director's own real premium); writing the
  confirmed reference back into `profile` itself, inside `feature_configs`, instead of a separate
  `reports/policy/` cache (rejected: `profile` is the document the Director edits by hand through
  `vault.py get`/`set`; a machine-written, machine-cached derivative belongs in the same
  vault-grade-but-machine-owned space `reports/captures/` already occupies for a different kind of
  derived, confirmed-by-construction data, not folded into the one document a human maintains
  directly); treating a zero-coverage-lines extraction as a hard refusal rather than a soft
  "no reference" fallback (rejected: this is exactly the asymmetry FR-058's own edge cases resolve
  deliberately - a corrupted or unreadable *vault* input warrants a hard, fail-fast refusal because
  it usually means a real typo the Director would want to know about immediately, but a PDF that
  simply does not parse cleanly is an expected, ordinary outcome of best-effort extraction against
  real-world documents, not a data-entry mistake, and should degrade the same way an insurer's own
  walk failure already does rather than blocking the whole report).

## D16. The `"n/a"` sentinel, `dwelling_type`, and the `"work"` address type (amendments 7 and 8, Director decision, 2026-08-25)

- **Decision**: the literal string `"n/a"` in an asset's `currently_insured` or `policy_doc` field
  (amendment 7) is an explicit, Director-decided exclusion - distinct from the field being merely
  absent, which means only "no data yet." `scripts/policy_extract.py` and `scripts/quote_compare.
  py` both treat it as a sentinel, never a real value (spec FR-061 through FR-064). Separately
  (amendment 8), `addresses[]` elements gain an optional `dwelling_type` field (a dwelling
  classification, e.g. `single_family`/`condo`/`apartment`/`townhouse`/`commercial` - named
  `dwelling_type` rather than `type` because `type` is already the array's own selection
  discriminator, D13) and a third element type, `"work"` (`dwelling_type` `"commercial"`, both
  `currently_insured` and `policy_doc` set to the `"n/a"` sentinel by construction). Both fields
  are seeded in `profile.template.json` now, for a future feature, and neither is read by anything
  this delivery ships (spec FR-036, FR-065, FR-066).
- **Rationale**: an absent field and an explicitly excluded one are different states a future
  feature (or the Director himself, reading his own document later) needs to tell apart - "no data
  yet, someone forgot to fill this in" is a data-quality problem worth flagging, while "`n/a`,
  decided" is a settled, permanent state that should never prompt a re-ask. Encoding that
  distinction as a sentinel value inside the existing field, rather than a separate boolean or a
  comment, keeps every consumer's check to one line (`headless/policydoc.py`'s own `is_excluded`)
  instead of a second field to keep in sync with the first. `dwelling_type` and the `"work"`
  address type are seeded now, ahead of the property-insurance and commute-aware-auto specs that
  will actually consume them, for the same reason D11's own `spouse`/`property` seeding was: the
  Director is populating his full household shape in one sitting, and this delivery's only
  obligation in response is the explicit "not wired yet" guard (FR-036) it already provides
  structurally, not incrementally seeding data per future feature.
- **Alternatives considered**: leaving an excluded asset's `currently_insured`/`policy_doc` fields
  simply absent, with no sentinel at all (rejected: this is indistinguishable from "no data yet,
  forgot to fill this in" - the Director's own point in choosing an explicit sentinel is that
  absence and decided-exclusion are different states worth telling apart, and a future feature
  reading the same document has no way to recover that distinction once it is collapsed to "field
  simply is not there"); a separate boolean field (e.g. `excluded: true`) instead of overloading
  `currently_insured`/`policy_doc` themselves (rejected: a second field can drift out of sync with
  the first - nothing stops `policy_doc` from holding a real path while `excluded` still says
  `true`, whereas the sentinel-in-place design makes the excluded state and the field's own
  would-be value the same field, structurally unable to disagree with itself); a hard schema-level
  `type` enum excluding `"work"` until its own future spec exists (rejected: the Director is
  seeding his real document now, ahead of the spec that will consume it, the same reasoning D11
  already used for `spouse`/`property` - forcing him to wait would just mean a second edit round
  later for no benefit this delivery's own FR-036 guard does not already provide).

## D17. `scripts/vault.py set`'s 1024-character interactive refusal and piped-stdin path: already shipped, out of this delivery's own build scope (amendment 9, 2026-08-25)

- **Decision**: `scripts/vault.py set NAME`'s hidden interactive prompt refuses any value of 1024
  or more characters (`REFUSED: value is 1024+ characters and may have been truncated by the
  terminal's input limit; pipe it instead: pbpaste | python scripts/vault.py set <name>`) rather
  than silently storing a value the terminal's own canonical input-line limit may have already
  truncated. The same command also accepts the value on piped stdin instead (`pbpaste | python
  scripts/vault.py set profile`; Windows: `Get-Clipboard | python scripts\vault.py set profile`),
  which has no such limit and still keeps the value out of argv, files, and the scrollback; the
  interactive prompt itself now prints the pipe-command hint before asking for a value, so the
  Director sees the escape hatch before pasting, not only after a refusal. Both behaviors were
  shipped directly on `main`, ahead of and independent of this delivery, as hotfixes v0.0.4.3
  (merge `a7e2e48`, commit `4a17be6`: the stdin-pipe acceptance and the 1024-character refusal) and
  v0.0.4.4 (merge `d55bc80`, commit `2d7799a`: the pipe hint printed before the prompt) - this
  delivery's own spec set (FR-039c) records both as shipped fact, the same pattern D12 already
  established for `get` and D14 for `profile.template.json`. This worktree's own `v0.0.5` branch,
  forked before either hotfix landed, does not yet contain them.
- **Rationale**: `profile.template.json`'s own shape (D14) is 1235+ characters as raw JSON - well
  past the 1024-character canonical-input-line limit macOS terminals impose on a single line fed
  into a hidden `getpass` prompt (verified empirically on the Director's own machine, per `scripts/
  vault.py`'s own module docstring: "a 2000-char line into getpass on a pty hangs"). Before this
  hotfix existed, the profile-editing round trip this feature's own quickstart depends on
  (`vault.py get profile` -> edit -> `vault.py set profile`) would have silently truncated or
  hung on exactly the document size this delivery's own array-and-`feature_configs` shape produces
  - a real, load-bearing gap this document has to record accurately once it was discovered, not
  merely note as a future concern. Recording the exact merge and commit identifiers, and the exact
  refusal message text, matches the evidentiary standard this document already applies to `get`'s
  own recording (D12) and to the landing-page selectors' own recon.
- **Alternatives considered**: describing the profile-editing round trip only via the hidden
  interactive prompt, without mentioning the piped-stdin path or the 1024-character refusal
  (rejected: this is precisely the failure mode an Opus verifier's own cross-reference pass caught
  in this delivery's own quickstart - an instruction that always fails once a real `profile`
  document reaches this delivery's own array-and-`feature_configs` size is worse than no
  instruction at all, since it looks correct until someone actually runs it); this delivery
  attempting to shorten `profile.template.json`'s own shape so it fits under 1024 characters and
  the interactive prompt keeps working (rejected outright: the template's shape is D14's own
  enforced contract, shipped independently of this delivery and not something a downstream spec is
  authorized to redesign to work around an unrelated terminal limit - the correct fix is the one
  `main` already shipped, a pipe, not a smaller document).

## D18. Comparison arithmetic: deterministic `Decimal` parsing and normalization for amounts, limits, and deductibles (ORCHESTRATOR DECISION, 2026-08-25)

- **Decision**: FR-016/FR-018/FR-046 previously left "normalized premium" and "better/worse"
  undefined at the arithmetic level. FR-067 now defines it exactly: (a) an amount parses by
  stripping currency symbols, commas, and spaces, then parsing as a decimal number; `term_months`
  parses as a positive integer; either failing for a quote ranks that quote last, tagged "premium
  not comparable," never a crash or a guess; (b) the normalized premium is `Decimal(amount) /
  term_months`, quantized to 2 decimal places with `ROUND_HALF_UP`, presented as a monthly figure,
  with the report stating the normalization was applied; (c) a limit string parses to a tuple of
  integers by splitting on `"/"`, stripping `$`/commas, and multiplying a trailing `k`/`K` part by
  1000; two limits compare only when their tuples share arity (element-wise `>=` is better-or-equal,
  all-equal is equal, any-lower is worse); a different arity or an unparseable side is its own
  "not comparable" class, never silently dropped; (d) a deductible parses the same way as an
  amount to a single number, lower is better, and an empty deductible on either side is "not
  comparable"; (e) every parse and comparison uses Python's `Decimal` type only, never `float`,
  which is what makes data-model.md's `build_comparison` byte-identical-output invariant achievable
  in practice, not only in principle.
- **Rationale**: a comparison engine the Director is meant to audit ("recommend me the best quote
  ... showing the comparison in nice pretty HTML") cannot leave "normalized premium" or
  "better/worse" as prose the implementer is free to interpret differently each time - two
  different interpretations of "normalize to the same term" or "compare a split limit" would
  produce two different, silently disagreeing recommendations from the same input data, which is
  exactly the kind of nondeterminism D5's own "no LLM anywhere in this path" decision already
  exists to prevent one layer up. `Decimal` rather than `float` is not a style preference here: a
  ranking rule that has to be byte-identical across runs (data-model.md's own invariant) cannot
  tolerate a binary floating-point rounding difference silently reordering two closely priced
  quotes between two runs of the same input. Ranking an unparseable premium last, with a stated
  reason, rather than raising or silently excluding the quote, keeps FR-025's "a report must still
  be produced" guarantee true even when one insurer's own captured text turns out to be malformed
  - the same soft-degrade discipline D15 already applies to a PDF that fails to parse, applied
  here to a captured page's own premium text instead.
- **Alternatives considered**: leaving the arithmetic underspecified in the spec and letting
  `/speckit-implement` choose a reasonable parsing scheme (rejected: this is precisely the gap an
  Opus verifier's own cross-reference pass flagged as unable to guarantee determinism or
  auditability without a written rule - two independently reasonable parsing schemes could
  disagree on a split-limit comparison or a currency-stripping regex, and neither the Director nor
  a later reviewer could tell from the spec alone which one shipped); using `float` for the
  normalized-premium division (rejected: `float` division of even simple decimal amounts can
  produce a value that differs in its last digit between platforms or Python versions, which is
  exactly the nondeterminism data-model.md's own byte-identical-output invariant forbids); treating
  an unparseable premium as a hard refusal of the whole comparison run (rejected: this would let
  one insurer's own malformed captured text take down a report FR-025 already promises to produce
  regardless of individual insurer trouble - the same "degrade, do not refuse" reasoning D15 and
  FR-058 already apply to a PDF that fails to parse); silently excluding a quote with an
  unparseable premium from `ranked_quotes` instead of ranking it last with a stated reason
  (rejected: this would make a real captured quote simply vanish from the report with no
  explanation, which is worse for the Director's own audit than an honestly labeled last-place
  row).
