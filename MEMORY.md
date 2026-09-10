# Headless - project memory

Read this at the start of every session (`CLAUDE.md` requires it). It is the operating
ledger: what the environment looks like, what each site is known to do, what has been run,
and what is open.

## Identity and environment

- Repo: `github.com/mananpatel2491/Headless` (private), personal identity `mananpatel2491`
  (git identity routed by remote URL via `~/.gitconfig-personal`; `gh` may need
  `GH_TOKEN=$(gh auth token -u mananpatel2491)` when another account is active).
- Machine: macOS, Python 3.14, Playwright 1.62, Google Chrome 151 installed. Headless launches
  the installed Chrome (`channel="chrome"`), headed, on its own persistent profile at
  `~/.headless/chrome-profile`.
- Secrets backend: as of v0.0.4 (2026-08-25, spec 004-age-vault), the default backend is a
  local, open-source, passphrase-encrypted `age` vault (`~/.headless/profile.age`), replacing
  the earlier plan to default to GCP Secret Manager plus PAM approval - the Director
  superseded that plan (a second Google account would have been needed solely to hold the
  approver role, since Google forbids approving one's own PAM grant, on top of a standing
  cloud dependency and its cost). `age` reads its passphrase from the terminal directly, never
  from anything Python passes it, so every secret- or registry-touching run needs the
  Director at the keyboard - this is the approval gate GCP's PAM was meant to provide, built
  instead from a property of the encryption tool itself. The macOS Keychain (`security` CLI,
  account `headless`) and GCP Secret Manager both remain selectable via
  `HEADLESS_SECRETS_BACKEND` (`keychain`, `gcp`) but neither is the default any more;
  `GcpBackend`'s code stays code-ready but inactive. (2026-09-09 correction: `gcloud` IS now
  installed on this machine, at `/opt/homebrew/bin/gcloud`, signed in to the Director's personal
  Google account with a personal project as its default, and `terraform` 1.15.8 is at
  `/opt/homebrew/bin/terraform`; `tflint` is absent. Neither has been used by this repository yet -
  see the Google Maps connector open item below.)
- Tooling gaps: `pwsh` absent, so `../worktree.ps1` cannot run; create worktrees by hand at
  `../worktrees/Headless/<branch>` with `git worktree add`.
- Commit safety gate active: `core.hooksPath=.githooks` must be set in every clone/worktree
  (see README); CI scans full history on every push.

## Known site traps

- **Progressive (`www.progressive.com/auto/`), 2026-08-26** - refuses the automated quote-start
  submission under headless Chrome. Three bounded, synthetic-data-only recon walks (spec
  005-insurance-quote-comparison, research.md D8) all confirmed the two landing selectors
  (`#zipCode_mma`, `#qsButton_mma`) resolve, then found the same result across three different
  submission attempts (a direct click, an Enter keypress, a JS-dispatched click): three
  `Failed to load resource: 403 Forbidden` console errors and zero navigation away from the
  landing page within a 20-second wait, every time. Recorded as evidence for the repository's
  standing headless-user-agent question (`PATTERNS.md`'s "Quiet by default" entry) - untested
  whether a real `--apply` run (a real, non-headless windowed Chrome, per "quiet by default")
  hits the same block, since recon is headless-only by its own authorization (D8). The shipped
  Progressive walk (`headless/insurers/progressive.py`) therefore ships only the two landing
  steps; nothing past them is automated in this delivery.

- **Yelp (`www.yelp.com/search?...`), 2026-09-09** - a headless preview lands on a "Verifying the
  device..." interstitial (page title `yelp.com`), never the results; a bot check, not a login
  wall. Not read by any errand. Untested under a real windowed Chrome (the same open question as
  Progressive's block above).
- **TripAdvisor (`www.tripadvisor.com/Attractions-...`), 2026-09-09** - a headless preview renders a
  blank page (title `tripadvisor.com`, an empty screenshot): a client-side challenge that never
  completes under headless Chrome. Not read by any errand.
- **Google Maps list view (`www.google.com/maps/search/<query>/`), 2026-09-09** - renders fully
  under headless Chrome with no consent wall on this profile: `div[role="feed"]` holds the result
  cards, each with an `a[href*="/maps/place/"]` link (name in `aria-label`, coordinates as
  `!3d<lat>!4d<lon>` in the href) and a `span[role="img"]` star label; the feed loads about 20
  more cards per scroll until "You've reached the end of the list" (up to about 60 for a broad
  query). A query Google answers with one obvious place (`Topgolf`) skips the list and opens that
  place page directly (no feed; coordinates in the URL's `/@lat,lon,` viewport) - `activity_scan`
  reads that page as the single result. A place page exposes weekly hours as `table tr` rows
  (`"Saturday11 AM-7 PM"` with Google's own U+2013, `"FridayClosed"`, `"Open 24 hours"`), the
  website as `a[data-item-id="authority"]`, phone and address as `button[data-item-id^="phone"]` /
  `button[data-item-id="address"]` (`aria-label` "Phone: ..." / "Address: ..."). Class names churn;
  these role/attribute selectors are the ones the errand depends on (`--check` probes three).

## Errands run (dated)

| Date | Errand | Mode | Outcome |
| :--- | :--- | :--- | :--- |
| 2026-08-24 | `probe https://example.com` | preview | Ran twice against a temporary `HEADLESS_PROFILE_DIR`. Both runs exit 0, printed `Title: Example Domain`, and wrote a `previews/probe-<timestamp>.png/.json` pair. First run created the profile directory; second run reused it with no error, confirming the persistent-profile session survives between invocations (SC-001 groundwork; login persistence itself needs a real login-protected site, not yet run). |
| 2026-08-24 | `check_env` | n/a (self-test, no browser window) | Default (keychain) backend: 4/4 PASS in about 1.1s. `HEADLESS_SECRETS_BACKEND=gcp` with `HEADLESS_GCP_PROJECT` unset: `vault` row FAILs naming `HEADLESS_GCP_PROJECT`, other rows SKIP, exit 1 in about 0.07s (SC-004, SC-006). |
| 2026-08-25 | `check_env` | n/a (self-test, no browser window) | Director UAT of v0.0.1: 5/5 PASS (the `git_hooks` row, added in v0.0.2, brought the total from 4 to 5). |
| 2026-08-25 | `probe https://www.progressive.com/` | preview | Director UAT of v0.0.1: no window opened, correct. |
| 2026-08-25 | `probe https://www.progressive.com/ --apply` | apply | Director UAT of v0.0.1: window stayed hidden until "Your turn", correct; Director logged in by hand and pressed Enter. A following preview run of the same site then showed a logged-out page: the login did not persist. Root cause confirmed (specs/003-login-persistence): Chrome drops any cookie carrying no expiry (a session cookie, what most logins set) on every `launch_persistent_context` restart, even though a cookie with an expiry survives. Separately, the apply window showed Chrome's own "unsupported command-line flag: --no-sandbox" warning bar; root cause confirmed as Playwright adding `--no-sandbox` to every launch unless `chromium_sandbox=True` is passed. Both fixed in v0.0.3 (session cookie persistence on the launched-profile path; `chromium_sandbox=True` on every Chrome launch in the codebase). Site name only recorded here - no account details, no cookie names or values. |
| 2026-08-25 | `probe https://www.progressive.com/ --apply`, then `probe https://www.progressive.com/` | apply, preview | Director UAT of v0.0.3: the `--no-sandbox` warning bar is gone (confirmed by the Director). The seed exported 7 session cookies (login, loginrouter, account.apps and policyservicing hosts) and the following preview re-imported them, so persistence works as specified; the Director judged login state from the public homepage, which shows the same header for everyone, and accepted the automated proof instead of re-running. OPEN QUESTION, not a defect: whether this site honours a restored session under the headless `HeadlessChrome` user agent. One orchestrator check of the login URL 100 minutes after the seed landed on the login page, which an idle timeout explains as well as user-agent binding would; the discriminating test (seed, then headless and `--show` previews of the login URL within a minute) is in the session transcript and has not been run. |
| 2026-08-25 | `vault.py init` + `vault.py set profile` + `check_env` | n/a (vault maintenance, no browser errand) | Director UAT of v0.0.4: `check_env` 5/5 PASS with `vault PASS - age backend` after init (his first `set profile` before `init` was correctly refused with the init hint - the designed order guard). UAT-reported polish item, cosmetic only: every Playwright-using command on this machine (check_env, probe) prints a `Task was destroyed ... TargetClosedError` block AFTER its output - a Playwright 1.62 sync-API shutdown race on Python 3.14; exit codes are unaffected. Open: suppress or upstream-fix; fold into a later release. |
| 2026-09-09 | `probe` x3 (Google Maps search, Yelp search, TripAdvisor attractions) | preview | Recon for spec 009-activity-scan on the shared profile, sequential (the profile lock refuses a second concurrent run). Google Maps: title `mini golf near Farmington Hills, MI - Google Maps`, full list rendered. Yelp: device-verification interstitial. TripAdvisor: blank page. All three recorded above as site traps. |
| 2026-09-09 | `activity_scan --near <point> --area "Farmington Hills, MI" --day friday --start 17:00 --end 22:00 --radius-miles 22 --details 40` | scan (read-only) | First live run, about 10 minutes, exit 0: 35 queries, 1,300-odd cards, 675 venues after folding/exclusion/radius, 674 with coordinates, 653 rated, 40 place pages read for Friday hours. `Topgolf` returned no feed (Google opened the place page directly) - handled in the same session (`read_single_place`). The first ranking exposed a relevance gap: Google's deep result tail is loosely related (a window-tinting shop for "glass blowing class", a DJ service for "live music venue", billiards supply stores, a kids' playground), and a high rating alone floated them to the top - fixed in the same session with the non-activity category exclusions, the query-stem relevance term, and the list-position penalty (`headless/activities.py`, `score_venue`), then re-run (row below). The point scanned around is the Director's own and is not recorded here. |
| 2026-09-09 | `activity_scan --near <point> --area "Farmington Hills, MI" --day friday --start 17:00 --end 22:00 --radius-miles 22 --details 80` | scan (read-only) | Second live run with the corrected ranking, about 12 minutes, exit 0: 35 queries, 536 venues after folding/exclusion/radius (down from 675 - the retail, trade-service, venue-for-hire and kid-only categories now drop out), 358 relevant / 178 not, 80 place pages read (40 open in the window, 18 partial, 6 closed, the rest "not checked"). The top of the list is now activities (escape rooms, an aerial adventure park, axe throwing, a winery with live music, a pinball arcade, bowling, indoor golf, then parks and nature preserves). Residual false positive at rank 38: a house painter whose category is the single word "Painting", surfaced by "paint and sip" through the "pain" stem - an exact-category exclusion would fix it; left as a known limit of the heuristic. The report is the Director's own evening shortlist and is not recorded here. |
| 2026-09-09 | `activity_scan --near <point> --area "Farmington Hills, MI" --day saturday --start 17:00 --end 22:00 --radius-miles 22 --details 80` | scan (read-only) | Third live run, exit 0, after the Director corrected the date (12 September 2026 is a Saturday, not a Friday): same 35 queries, the Saturday hours verdict for the top 80, the report of record for the evening. Run on the code as it stood BEFORE the verifier fix batch of the same day (the batch changes exclusion and relevance details only; the shortlist the Director acted on was cross-checked by re-ranking the second run's own JSON for Saturday, which agreed on the top of the list). |
| 2026-09-09 | `maps_check --no-search` and `maps_check` (no key set) | n/a (connector self-test, no browser window) | First live runs of the v0.0.10 connector check from the v0.0.10 worktree, both exit 0: `server PASS - StatelessServer (protocol 2025-06-18)`, `tools PASS - search_places, lookup_weather, compute_routes, resolve_names, resolve_maps_urls` (five tools, two more than Google's documentation names), `search SKIP` (no key on this machine yet). The handshake and the tool listing need no key; a tool call does. |
| 2026-09-09 | `activity_scan --near <point> --area "Farmington Hills, MI" --check` | check | `CHECK 3 found, 0 missing` (`div[role="feed"]`, its `/maps/place/` link, the star `span[role="img"]`), exit 0, about 10 seconds. |

## Claude Code sessions (for resuming)

Record each working session's id here so it can be resumed with `claude --resume <id>`.

| Date | Session id | Notes |
| :--- | :--- | :--- |
| 2026-08-24 | `09a98ca6-0de1-49dc-83fb-d42e642c4b02` | Bootstrapped the repo from AVF (Director layer, Spec Kit 1.0.2), created the GitHub repo, spec 001 foundation |

## Open items

- **Spec 009 (activity scan, v0.0.9, 2026-09-09): implementation delivered, first live scans run,
  Director UAT pending.** A read-only errand (`scripts/activity_scan.py`, logic in
  `headless/activities.py`) that ranks public venues around a CLI-supplied point for an evening
  window, from the Google Maps list view (the one review source that renders under headless Chrome
  - Yelp and TripAdvisor both refuse, see the site traps above). No apply mode exists or may be
  added; `--check` probes the three list-view selectors. Ranking: Bayesian-shrunk rating (prior 4.0
  over 25 phantom reviews), minus 0.04 per straight-line mile, minus 0.015 per place down Google's
  own result list, plus 0.35 / minus 0.25 for a name or category that does / does not echo a query
  stem, then the day-window verdict from the place page's weekly hours (closed in the window minus
  1.0, open plus 0.2, partial plus 0.05, not enriched neutral); categories that are retail, trade
  services, venues for hire, kid-only, a movie, or a dinner are excluded outright. Decided against
  a Google Places API key or a Maps MCP connector for this feature (the MCP registry lists none as
  of 2026-09-09; a Places key needs a billed GCP project under Lesson 5's cost gate and would live
  outside the vault) - revisit only if the scan becomes a recurring errand. Open: the relevance
  heuristics are tuned on one evening's queries around one suburb; a second use with a different
  query list should re-check the exclusion terms and the stem matcher before trusting the top of
  the list; hours enrichment reads only the top `--details` venues (80 on the second run), so a
  deep result stays "not checked".
  **Opus verifier fix batch, same day, applied before commit: 1 BLOCK, 7 IMPORTANT, 5 MINOR, 3 NIT,
  all resolved.** BLOCK: the test suite's example-point constant and one test name attached a
  personal context to the scanned coordinate (public repo) - replaced by a synthetic round-number example point, the
  geocode fixture reduced to the sanctioned 4-decimal pair, the checklist now states the test suite
  was scanned too. IMPORTANT: bare-substring category exclusion deleted "Dance school", "Cooking
  school" and "Pottery workshop" (the very categories three default queries target) - now
  whole-word matching, only kid-only school kinds named, and a "rental" keep-list checked first;
  unparseable hours text ("Hours might differ") scored as closed (-1.0) - now "unknown"; the
  four-letter prefix stem gave "comedy" a hit on "Comerica" and "cooking" on "Cookies" - replaced by
  a whole-word-plus-inflections rule ("paint" still matches "Painting studio", "winery" matches
  "Wine bar"); the report writer lacked the repo's chmod-before-and-after 0600 bracket on a
  same-date overwrite - added, with a mode assertion; one failed query navigation aborted the whole
  35-query scan - now per-query fail-soft with a `note: query skipped` line; the feed reader and the
  scroll loop had zero test coverage - fakes extended (`get_by_text`, `evaluate`, nested
  `locator`), tests added; research.md still said `--details 30` - corrected. MINOR/NIT: six
  contract rows now have tests (MISSING selector, exit 2 plus debug traceback, GateRefused, empty
  queries, details-skipped note, check writes no report); an out-of-range coordinate pair is refused
  before any geocoder request; a non-clock `--start`/`--end` is refused; the single-place test asserts
  its stdout line; the Nominatim User-Agent names the repository; the scroll loop gives up only after
  two consecutive empty scrolls. Unit suite after the batch: 140 tests in the two new modules.
- **Spec 010 (Google Maps connector, v0.0.10, 2026-09-09): implementation delivered, Director
  actions pending.** `.mcp.json` registers Google's hosted Maps Grounding Lite MCP server
  project-wide with the key expanded from `HEADLESS_MAPS_API_KEY`; `headless/mapsmcp.py` plus
  `scripts/maps_check.py` are the Lesson 4 live check (25 unit tests, live handshake proven, see the
  errand row above); `terraform/` declares the two API enablements and one key restricted to
  `mapstools.googleapis.com` (`terraform validate` green; provider cache, state and tfvars
  gitignored, the lock file committed). PENDING, Director only: (1) pick the Google Cloud project
  (billing must be linked even inside the free cap) and run `terraform plan` then `apply` from
  `terraform/`; (2) `terraform output -raw maps_api_key` into the Keychain item `maps-api-key`
  (account `headless`) and export `HEADLESS_MAPS_API_KEY` from the login shell; (3) run
  `python scripts/maps_check.py` (one billable `search_places` call, well inside the 10,000 free
  events per month) and record the outcome here; (4) approve the project-scoped server the first
  time `claude` prompts in this repository; (5) acknowledge Grounding Lite's term that it must not
  be used with a model that trains on the data sent to it.
  **Opus verifier fix batch (2026-09-10), applied before commit: 1 BLOCK, 2 IMPORTANT, 4 MINOR, 6 NIT.**
  BLOCK: the check's HTTP-error path echoed a non-JSON response body verbatim, and on this machine
  every run goes through the employer's proxy, whose error pages quote the request line and headers -
  the verifier printed a planted key to stdout. Fixed mechanically: `Transport._redact` replaces the key
  value with `***` in every error text, and a non-JSON body is never shown (only its byte length); a
  test plants the key in a gateway page and proves it never reaches stdout. IMPORTANT: `--no-search`
  with the key set printed "key is not set" - the outcome now carries the skip reason; a blank or
  whitespace key counts as unset. MINOR/NIT: SSE continuation lines are joined and array payloads
  flattened per the SSE rule; the transport sends the protocol version the server negotiated; an
  unstructured `search_places` answer prints "answered" instead of an invented count of 1; the README
  terraform block gained the plan-review step; PATTERNS' export line and quickstart's citation
  corrected; header-absence and bare-HTTPError branches now tested. Suite after the batch: 25 tests in
  `tests/test_maps_check.py`. Groundwork that led here, same session: the MCP registry lists no Google Maps connector; Google's own hosted server, Maps
  Grounding Lite (`https://mapstools.googleapis.com/mcp`, Streamable HTTP, header `X-Goog-Api-Key`
  or OAuth scope `maps-platform.mapstools`, API service `mapstools.googleapis.com`, tools
  `search_places` / `lookup_weather` / `compute_routes`, 300 queries per minute) is an Essentials
  SKU with 10,000 free events per month, then $7 per 1,000 - within Lesson 5's $0 target at
  personal volume; an unauthenticated `initialize` POST to the endpoint already answers HTTP 200
  (`StatelessServer`), so authentication is enforced per tool call, not at the handshake. Claude
  Code registers it from a project-scoped `.mcp.json` (`type: "http"`, `url`, `headers` with
  `${VAR}` expansion; project-scoped servers need a one-time approval in an interactive session).
  Decided against a `check_env.py` row (that gate exits non-zero on anything but PASS and the
  connector is optional) - `maps_check.py` is the connector's own check. The age vault is
  deliberately not the key's home: `age` prompts on the controlling terminal and Claude Code
  launches an MCP server without one; the macOS Keychain plus a login-shell export is.
- **Spec 007 (extraction fidelity, v0.0.7, 2026-08-30): implementation delivered, Opus verifier
  fix batch applied, live-probe verification COMPLETE, Director UAT pending.** An independent
  audit against three of the Director's own real declarations PDFs probe-proved four defects in
  v0.0.6's own pipeline: the sanity pass stripped a verbatim composite figure (a split "each
  person/each accident" limit, a labeled deductible cell, a spaced policy number) because it
  tokenized the proposed side as one whole blob while the source side was already tokenized
  per-digit-run; the term-derivation helper mis-paired an unrelated date (a statement/issue date)
  positioned before the policy-period label with the real period's own start date on two of three
  real documents, silently overriding a correct local-model claim; the layout-aware converter's
  own glued table cells (`"Total6month"`-shaped) defeated the "N-month" phrase pattern; and
  stripped-figure warnings never reached the cache or the confirm prompt in a hard-to-miss way.
  Also added: ten additive schema fields, five new homeowners coverage-line alias-table keys, and
  a local-model context-window guard - see `Project_Structure.md`'s own v0.0.7 row for the full
  first-pass account.
  **Opus verifier fix batch, same day, applied before commit: 2 BLOCK, 4 IMPORTANT, 4 MINOR.**
  BLOCK 1 - the first-pass de-glue rule was blanket and, measured against the three real PDFs,
  corrupted real identifiers (a VIN-shaped run's own survival measured 2 -> 0, a mixed identifier's
  18 -> 0); corrected to a precise per-run rule (fires only when a maximal alphanumeric run has
  <= 2 letter<->digit transitions, a <= 3-character digit-side segment, and a >= 3-character
  letter-side segment at that boundary) - re-verified: 0 VIN-shaped and mixed-identifier
  discrepancies on two of three documents, and the one apparent discrepancy on the third
  (vehicles-primary, mixed-identifier metric 5->4) was traced to the probe's own overly broad
  detection heuristic flagging an ordinary glued label-plus-figure construct structurally
  identical to the canonical "Total6month" positive case (5 letters + 1 digit + 5 letters, 2
  transitions) - confirmed via a synthetic reproduction, not a real identifier at all; the
  narrower, more reliable VIN-shaped-only metric shows 0/0, 0/0, 2/2 (perfect preservation) across
  all three documents. BLOCK 2 - `effective_date`/`expiration_date` were only date-PARSE-checked,
  never verified present in the source, letting two fabricated but well-formed dates compute and
  win a term with zero warnings; both fields now also pass the ordinary figure gate, and the
  term-precedence rule is restated as ONE table (verified explicit dates > an explicit N-month
  phrase > window-derived dates > the generator's own claim), with a disagreement warning naming
  both sources and both term values when a higher tier overrides a lower one that produced a
  value. IMPORTANT 3 - `research.md`'s own "without weakening the check at all" claim narrowed to
  "without weakening the per-token exactness of the check" (a composite recombining two
  real-but-unrelated figures still passes by design; the Director's confirmation is the accepted
  backstop). IMPORTANT 4 - a "Prior Policy Period" section could span a prior period's own start
  date to the current period's own end date under the max-minus-min rule; fixed by excluding an
  occurrence preceded by "prior"/"previous"/"former"/"expiring" and capping every occurrence's own
  window at the next label occurrence's own start, plus a warning whenever more than two distinct
  dates survive. IMPORTANT 5 - the context guard was measured against the document text alone
  (under-counting the prompt template's own overhead) with no response reserve; now measures the
  FULL prompt against `num_ctx` minus a 1024-token reserve, and `DEFAULT_NUM_CTX` raised 8192 ->
  16384 after `ollama show qwen3.5:35b` (localhost, read-only, run once) confirmed this machine's
  own model supports a 262144 context length. IMPORTANT 6 - the "correct" branch's own prompt
  reworded from a stale "insurer/premium/coverages" list to "the same object printed above," with
  a new round-trip test proving all 13 `CurrentPolicy` keys survive a correction. MINOR 7/8/9/10
  resolved (documented residuals, Files Affected correction, no action needed) - see
  `PATTERNS.md`'s own fix-batch entry and `contracts/fidelity.md` for the full account.
  Unit suite after the fix batch: 646 passed, 9 skipped (up from the first-pass 629/9 and the
  574/9 v0.0.6 baseline); `verify_structure.py` green; opt-in browser suite green (8 passed);
  opt-in `HEADLESS_TEST_OLLAMA=1` integration test passed against the real local model with the
  corrected `num_ctx` payload.
  **Orchestrator-run, read-only live probe against the Director's own three real declarations
  PDFs, RE-RUN after the fix batch, extended with identifier-preservation counts: COMPLETE
  (2026-08-30), matching SC-005 exactly.** addresses-home: derived term 12 months, 0 verbatim
  figures stripped, 3/3 deliberately hallucinated figures stripped, 0 VIN-shaped runs (none
  present) and 3/3 mixed-identifier runs preserved. addresses-rental: derived term 12 months, 0
  stripped verbatim, 3/3 hallucinated stripped, 0 VIN-shaped (none present) and 15/15
  mixed-identifier runs preserved. vehicles-primary: derived term 6 months, 0 stripped verbatim,
  3/3 hallucinated stripped, 2/2 VIN-shaped runs preserved (byte-identical) and 4/5 mixed-identifier
  runs preserved by the probe's own broad heuristic - traced (see the fix-batch note above) to a
  false positive on an ordinary glued construct, not an identifier corruption; the real VIN metric
  on this same document shows perfect 2/2 preservation. No real figure, name, path, or identifier
  value was written anywhere in this repository by that probe (a throwaway scratchpad script, per
  NFR-002/NFR-004). **Pending**: the Director-attended re-extraction of his own three real assets
  into confirmed, cached references using this corrected pipeline - a separate, later session,
  explicitly out of this delivery's own scope (D9).
- **Spec 006 (policy extraction v2, v0.0.6, 2026-08-29): implementation delivered, Director UAT
  pending.** The Director's own first real declarations PDF (a three-page homeowners policy)
  exposed two independent gaps in v0.0.5's regex-only extraction: `pypdf`'s own plain-text
  extraction scrambled the multi-column layout, and an annual policy never states an "N-month"
  phrase v0.0.5's own term regex looks for. Fixed with a pipeline: layout-aware conversion
  (`pymupdf4llm`, `headless/policydoc.py`'s `convert_document`), a local-only Ollama model
  attempt (`headless/localllm.py`, falling back automatically to the unchanged v0.0.5 regex
  heuristics on any failure or `--no-llm`), a shared date-arithmetic term-derivation helper
  (`derive_term_from_dates`, an average-day month span not calendar-month arithmetic, used by
  both generators), and a mechanical sanity pass (`apply_sanity_pass`) that strips any figure not
  an exact digit-run-token match against the converted source text before the unchanged Director
  confirmation gate ever sees it. `PolicyReference` gains `generator`/`converter` provenance
  fields, surfaced in the comparison report's footer. `headless/config.py` gains
  `ollama_model`/`ollama_url`, with a value-free `ConfigError` refusing any
  non-`localhost`/`127.0.0.1` `HEADLESS_OLLAMA_URL` before any conversion or network call.
  **Opus verifier fix batch, same day, applied before commit**: 4 FIX-FIRST (a schema-valid but
  empty-coverages/all-empty-figures local-model response now folds into the ordinary
  failed-attempt fallback instead of being confirmed as-is; the sanity pass rewritten from
  substring containment to exact digit-run token matching, closing a real hallucination-detection
  gap an adversarial review found; docs reworded to the actual arithmetic/matching semantics; the
  one FR-019 exemption test rewritten against a fixture that actually exercises the exemption),
  1 IMPORTANT (a new test covers `scripts/quote_compare.py`'s own provenance 4-tuple wiring,
  previously untested), 6 NIT (the integration test now uses the real prompt builder and fails
  rather than skips on a schema mismatch; a tightened date-regex lookbehind plus a documented,
  tested known false negative; the local-model fallback note now prints even when the regex path
  also finds nothing; numeric leaves from the model are coerced to strings; a non-numeric figure
  value passes through untouched; this changelog row's own Files Affected list corrected) - see
  `Project_Structure.md`'s own v0.0.6 row for the full account. Unit suite green after the fix
  batch (574 passed, 9 skipped, up from the 478/8 v0.0.5 baseline), `verify_structure.py`
  SUCCESS, `scan_secrets.py --staged` clean, opt-in browser suite green (8 passed), and the
  opt-in `HEADLESS_TEST_OLLAMA=1` integration test run twice against the real local
  `qwen3.5:35b` server on this machine - passed both times (6.48s, then 6.66s after the fix
  batch), schema-valid response each time. Pending: the Director's own
  run against his real declarations PDF with his own Ollama running (quickstart.md Scenarios
  1-5) - this delivery's own brief is implementation-only and never touches `~/.headless/` or
  opens a real browser window.
- **Spec 005 (insurance quote comparison, v0.0.5, 2026-08-25/26): implementation delivered,
  Director UAT pending.** Walk framework (`headless/steps.py`, `Session.click`/`capture`,
  `Errand.walk()`), type-discriminated array addressing in `ProfileRegistry` plus
  `RegistryAmbiguous`, the `profile.template.json` drift test, the capture model
  (`headless/capture.py`), per-asset `policy_doc` PDF extraction and Director confirmation
  (`headless/policydoc.py`, `scripts/policy_extract.py`), the `Decimal`-only comparison engine
  (`headless/compare.py`), the self-contained HTML report generator (`headless/report.py`), the
  Progressive walk (landing-page-only, see the site-trap entry above), and the multi-insurer
  orchestrator (`scripts/quote_compare.py`) are all implemented and unit-tested. Pending: the
  Director's own `--apply` run against the real Progressive site (does the headless-only block
  found in recon also occur in a real, non-headless apply window - unverified either way);
  `scripts/policy_extract.py` against a real policy PDF (the heuristics are unproven against real
  declarations-page layouts, research.md D15's own accepted residual); the profile-seeding round
  trip (quickstart Scenarios 1-2); the full quickstart Scenarios 3-10.
- Run this repository's own `vault.py init` / `vault.py set profile` on this machine (spec
  004-age-vault; not yet done in this delivery, since the brief for that delivery excluded
  touching `~/.headless/`) and record the outcome in the "Errands run" table below.
- (Superseded 2026-08-25, spec 004-age-vault) ~~Install `gcloud`, create the Secret Manager
  project through `terraform/`, and switch `HEADLESS_SECRETS_BACKEND=gcp`~~: the GCP Secret
  Manager plus PAM plan is superseded by the local `age` vault above; `gcloud` install is no
  longer on the critical path to a working secrets backend, only to activating `gcp` as a
  non-default, explicitly-selected alternative.
- Seed the Headless Chrome profile with the logins the first real errands need (ITR portal,
  ticketing, insurance) by running `scripts/probe.py <url>` and logging in by hand.
- First real errand candidates (each its own spec): ITR portal walk (reuse `itr-wala` for the
  tax math; Headless owns only the portal steps up to Submit), movie-ticket availability,
  insurance quote collection, work-portal chores.
