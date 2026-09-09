# Research: Activity Scan

**Feature**: 009-activity-scan | **Date**: 2026-09-09

This document records the recon an implementation session ran on 2026-09-09, against the live
Google Maps list view, Yelp, and TripAdvisor under headless Chrome, before this feature's own
code was written, and the thirteen design decisions (D1-D13) that follow from it. D9 and D10
record a second recon pass, against the first live scan's own output, later the same day. D11
through D13 record an Opus verifier's own fix batch and a subsequent re-verification's own
further fix batch, both also later the same day.

## Evidence

### Google Maps renders fully; Yelp and TripAdvisor refuse headless Chrome

Google Maps' own list view (`https://www.google.com/maps/search/<query> near <area>/`) renders
completely under headless Chrome 151 on the Headless profile. Each result card sits inside a
container with `role="feed"`. A card's own place link carries `href` containing `/maps/place/`
and embeds the venue's coordinates as `!3d<lat>!4d<lon>`. The same link's `aria-label` carries the
venue's name. A `span[role="img"]` inside the card carries an `aria-label` reading, for example,
"4.2 stars 726 Reviews". The card's own text lines read, in order: a repeated name, a combined
rating-and-review-count string like "4.6(585)", a category-and-address line joined by a middle
dot, and today's hours line starting with an open/closed status word.

A first page load renders about six results. Scrolling the feed element (never the page) loads
more, up to roughly 19 or 20 results, at which point the feed's own text carries "reached the end
of the list". A sponsored card carries a "Sponsored" line of its own and duplicates an organic
card already in the results.

A place page (opened by following a card's own link) exposes its weekly hours as `table tr` rows
whose text reads a day name immediately followed by that day's hours ("Saturday11 AM-7 PM",
using Google's own long-dash character between the two times; "FridayClosed"; "Open 24 hours").
The same page exposes a website link at `a[data-item-id="authority"]`, a phone button at
`button[data-item-id^="phone"]` (its own `aria-label` reading "Phone: ..."), and an address button
at `button[data-item-id="address"]` (its own `aria-label` reading "Address: ...").

Yelp's own search page, under the same headless Chrome profile, returned a "Verifying the
device..." interstitial (the page's own title stayed "yelp.com" with no results ever rendering).
TripAdvisor's attractions page rendered blank (title "tripadvisor.com", no content). Neither site
was probed further; neither is read by this feature.

## D1. Google Maps list view is the single review source

**Decision**: the scan reads only the Google Maps list view and each shortlisted result's own
place page. No other review source is read.

**Rationale**: it is the only one of the three sources recon checked that renders under headless
Chrome at all, and it already carries every field the scoring and reporting logic needs: a
rating, a review count, a category, an address, today's and (via the place page) weekly hours,
and each result's own coordinates.

**Alternatives considered**:

- Reading Yelp or TripAdvisor anyway, in headed (`--show`) mode: rejected for this delivery. A
  headed run might pass Yelp's own device check, but nothing in this recon proved that, and
  adding a second source before the first is proven correct in a real run would widen scope for a
  Director whose evening plan has already been served by one source.
- A hybrid approach, reading Google Maps for coordinates and hours and a second source for review
  sentiment: rejected as unnecessary complexity for a scan whose whole purpose is a fast ranked
  list, not a sentiment analysis.

## D2. No Google Places API and no Maps MCP connector

**Decision**: the scan reads the public Google Maps web pages directly. It never calls the
Google Places API and never uses a Maps-specific MCP connector.

**Rationale**: the MCP registry available in this environment lists no Google Maps connector as
of 2026-09-09. A Places API key needs a billed GCP project, which this repository's own Lesson 5
(cost gating, a $0/month target, a `terraform/` declaration before any cloud resource exists)
would require declaring before use - a real cost and a real infrastructure decision for a
personal errand that the free, public list view already serves. A Places API key would also need
to live outside the age vault (it is a service credential, not a Director-typed profile value),
which this repository has no established pattern for yet.

**Alternatives considered**:

- Provisioning a Places API key now: rejected. The recon proved the free web page already carries
  every field the scan needs; paying for an API before that is exhausted is premature.
- Revisiting this decision if the scan becomes a recurring, scheduled job rather than a one-off
  Director-run errand, where API rate limits or markup drift might argue for a paid, stable
  interface instead. Recorded as a future reconsideration point, not a commitment.

## D3. The point to scan around is a CLI argument, never a stored value

**Decision**: `--near` is read from the command line on every run. It is never written to the
profile registry, the vault, a config file, or any tracked file in this repository.

**Rationale**: this repository is public (`headless_public_repo_hygiene`). A home address or any
other chosen point is personal data. The scan needs the point only for
the duration of one run; there is no reason to persist it anywhere this repository's own commit
history could ever expose it.

**Alternatives considered**:

- Adding a `near` field to the profile registry, like an address already stored under
  `profile.addresses`: rejected. The registry's own existing address fields already carry that
  risk for the errands that must type them into a form; this scan has no form to fill and gains
  nothing from also reading that field, while avoiding the registry keeps this errand's own
  dependency list at zero secrets and zero vault items (FR-029, NFR-003).

## D4. `reports/activity/` stays inside the existing gitignored `reports/` tree

**Decision**: the two report files land under `reports/activity/`, a new sibling to
`reports/captures/` and `reports/policy/`, resolved the same way those two already are
(`reports_dir_for(config)`, no new environment variable, no new CLI flag).

**Rationale**: a venue listing itself is public data, unlike a captured quote or a confirmed
policy reference. But the report also carries the Director's own resolved chosen point (echoed
back for context) and his own evening-window choice, so it stays inside `reports/`'s existing
vault-grade, gitignored classification rather than becoming the one exception to it.

**Alternatives considered**:

- A new top-level, non-gitignored directory for activity reports, since the venue data itself is
  public: rejected. The point and the window are still the Director's own planning detail;
  consistency with every other `reports/` sub-folder is worth more than the marginal argument
  that the venue rows alone are public.

## D5. Selectors are ARIA-role and attribute based, never a class name

**Decision**: every selector this feature depends on (`div[role="feed"]`,
`a[href*="/maps/place/"]`, `span[role="img"][aria-label*="star"]`, `table tr`,
`a[data-item-id="authority"]`, `button[data-item-id^="phone"]`, `button[data-item-id="address"]`)
targets an ARIA role or a stable attribute, never a generated class name.

**Rationale**: Google's own class names churn between releases; ARIA roles and the
`data-item-id`/`href`-shape attributes recon observed have not, matching this repository's own
existing precedent (`PATTERNS.md`'s architectural-pattern entries already favor role/attribute
selectors elsewhere in this codebase).

**Alternatives considered**:

- Matching on visible text (a venue's own category word, a status word) as the primary selector:
  used only as a fallback inside `parse_card_lines` (the category/address line, the
  hours-status line), never as a structural selector for locating an element on the page. Text
  can vary by locale and by category; the ARIA/attribute selectors above are the load-bearing
  ones.

## D6. Friday hours come from each shortlisted venue's own place page

**Decision**: the day-window verdict (FR-013) is computed only for the venues enriched by a
place-page visit (`--details`, default 60). The list view's own "today's hours" line is read and
stored (`hours_today`) but never used for the day-window verdict unless the configured `--day`
happens to be today.

**Rationale**: the list view shows only today's own open/closed status, never a full weekly
schedule. Only a venue's own place page states hours for every day of the week, which the scan
needs because the Director's evening window is not always tonight.

**Alternatives considered**:

- Deriving Friday's hours from today's status plus an assumed weekly pattern: rejected. Guessing
  a schedule risks a wrong verdict exactly where the Director needs it most (whether a venue is
  actually open for his own evening).

## D7. A Bayesian shrink toward a 4.0 prior, weighted by 25 phantom reviews

**Decision**: `score_venue` shrinks a venue's own rating toward a prior of 4.0 stars, weighted as
though 25 additional reviews already existed at that prior, before applying the distance penalty
and the day-window adjustment.

**Rationale**: a raw rating alone rewards a five-star venue with three reviews over a 4.6-star
venue with six hundred, which is a worse recommendation, not a better one. The shrink formula
(`(rating * reviews + 4.0 * 25) / (reviews + 25)`) pulls a small sample toward the prior while
barely moving a well-reviewed venue's own score.

**Alternatives considered**:

- A minimum-review-count filter (dropping any venue under, for example, ten reviews) instead of a
  shrink: rejected. A filter discards a genuinely good, newer venue outright rather than merely
  discounting its own uncertainty; the shrink keeps it in the list, ranked appropriately.

## D8. The scan reads only; the feed scroll uses `evaluate()`, never a click or a keypress

**Decision**: the entire errand never calls `.fill(`, `.type(`, `.press(`, `.click(`,
`.dblclick(`, `.select_option(`, `.check(`, or `.set_input_files(` on any page or locator. The
results feed is scrolled by calling `locator.evaluate("el => el.scrollBy(0, el.scrollHeight)")`
on the feed element itself.

**Rationale**: this matches `CLAUDE.md`'s own "Terminal actions are human-only" posture at its
strictest: this errand has no terminal action to reach at all, because it never interacts with
the page beyond reading it. Scrolling via `evaluate()` rather than a scroll-wheel keypress or a
click-and-drag keeps the existing structural test, `tests/test_no_direct_typing.py` (its own
`ast`-based scan of every file under `scripts/`), green with no exception needed for this file.

**Alternatives considered**:

- Scrolling with a simulated mouse wheel event or a `Page.keyboard.press("End")` call: rejected.
  Both would still be read-only in effect, but `evaluate()` is simpler, does not require the feed
  element to have keyboard focus, and avoids any question about whether a keypress-based scroll
  trips the structural scan's own forbidden-call list.

## D9. Relevance and list-position terms, extended exclusions (after the first live scan)

**Decision**: after the first live scan (2026-09-09) surfaced loosely related results deep in
several queries' own result lists, `score_venue` gained two more terms - a penalty of 0.015 for
every place a venue sits down its own query's result list, and a relevance term (plus 0.35 when
the venue's name or category echoes a query stem, minus 0.25 when it echoes none) - and
`EXCLUDED_CATEGORY_TERMS` grew from the original four movie/dinner terms to the full retail,
venue-for-hire, trade-service, and kid-only list.

**Rationale**: the first live scan showed that a high rating alone can float a loosely related
result to the top of a report: a window tinting shop answered "glass blowing class," a DJ service
answered "live music venue," billiards supply stores answered "billiards pool hall," wine stores
answered "winery vineyard," and an indoor playground answered "rock climbing gym." Every one of
these carries a high rating and none is the activity the query names. Google's own result order
already favors relevance and prominence, so a position penalty discounts the deep tail of a
result list without ruling it out outright; the relevance term catches what an in-category-only,
wrongly-matched listing still gets past that penalty.

**Alternatives considered**:

- An allowlist of activity categories, checked instead of the exclusion list: rejected. It would
  be too brittle across a query list this size, and across every future query the Director adds -
  a new activity type would need a new allowlist entry before it could ever appear in a report,
  where the exclusion list only needs a new entry for a category already proven wrong.
- A Google Places API type filter: rejected for the same reason D2 rejects the API outright - the
  free list view already carries every field the scan needs, and a type filter would still need a
  billed GCP project this errand has no reason to stand up.
- Trusting Google's own result order alone, with no position penalty and no relevance term:
  rejected as insufficient. The scan merges results from many separate queries into one ranked
  list; a position that is meaningful within one query's own list is not, by itself, comparable
  across queries without a term that discounts it.

## D10. A query that opens one place directly

**Decision**: when a query's own search page carries no results feed and its URL contains
"/maps/place/," the scan reads that single place page as the query's whole result, through
`read_single_place`, rather than treating the query as returning zero results.

**Rationale**: the first live scan observed this for the query "Topgolf" - Google answered with
the place page directly instead of a results list, because the query name matches one place
closely enough that Google skips the list view entirely. That place page's own URL carries a
`/@<lat>,<lon>,` viewport coordinate pair but no `!3d<lat>!4d<lon>` pair (the pair a result card's
own place link carries), so `parse_place_href` gained the viewport pair as a fallback.

**Alternatives considered**:

- Treating a feed-less page as zero results for that query: rejected - it would silently drop a
  well-matched venue (Topgolf itself) from every report run against a query that names it
  directly.
- Requiring the Director to reword a query that triggers this behavior: rejected - the scan
  should handle a page Google itself renders this way, rather than push a workaround onto the
  Director for every future query that happens to match one place exactly.

## D11. Named activity-rental phrases, not a bare "rental", keep a venue from exclusion

**Decision**: `KEPT_CATEGORY_TERMS` lists eight named activity-rental phrases ("kayak rental",
"canoe rental", "paddleboard rental", "boat rental", "bike rental", "bicycle rental", "ski
rental", "skate rental") instead of the bare word "rental".

**Rationale**: a bare "rental" keep-list, checked before any exclusion, rescued every category
containing the word "rental" regardless of what was being rented - "Tuxedo rental shop" and
"Party rental store" both survived exclusion despite naming no activity a Director would drive to
for an evening out. Naming the activity rentals this scan's own query list actually targets (a
kayak, a canoe, a paddleboard, a boat, a bike, a bicycle, skis, skates) keeps exactly the rental
categories those queries exist to find, while a costume, a tuxedo, or a party-supply rental falls
back to the ordinary retail exclusion ("store", "shop", "supply", "dealer") like any other rental
of a thing rather than an activity.

**Alternatives considered**:

- Keeping the bare "rental" term and instead adding "tuxedo", "costume", and "party" to
  `EXCLUDED_CATEGORY_TERMS` as a counter-exclusion: rejected. The keep-list is checked before any
  exclusion, so a counter-exclusion for one wrongly-rescued category would need to be checked
  before the keep-list too, doubling the ordering complexity for a fix a positive list already
  solves in one place.
- Removing the keep-list entirely and excluding "rental" wholesale: rejected. Several default
  queries name a rental activity directly ("kayak canoe rental", "paddleboard rental", "bike
  rental trail"); dropping the keep-list would exclude the very venues those queries exist to
  find.

## D12. Relevance is a whole-word-plus-inflection rule, with a neutral case for a meaningless query

**Decision**: `relevance_pattern` builds one whole-word regular expression per query, covering
each meaning-carrying token plus a small set of inflection roots (`_bases`), matched with a word
boundary on both sides. `relevance_hit` returns `True` on a match, `False` on no match when at
least one surfacing query carried a meaning-carrying token, and `None` (neutral, no score change)
when no surfacing query carried one at all (a `--queries-file` line such as "cafe bar club" has
no word left after the generic-word filter).

**Rationale**: an earlier prefix-based rule (matching a 4-character prefix, then a 5-character
prefix, of a query token against the venue's own text) produced false positives a whole-word rule
does not: a 5-character prefix still let "cooki" match "Cookies" for the query "cooking class,"
the same class of wrong match a 4-character prefix already produced for "comedy" against
"Comerica" and "mini" against "Mining." A whole-word match, plus a short, explicit list of
inflection roots, catches "painting" for "paint," "brewery" for "brew"/"brewer," and "trails" for
"trail" without ever matching inside an unrelated longer word. The neutral `None` case exists
because a query with no meaning-carrying token at all has nothing for a venue's name or category
to echo; scoring it `False` would penalize every venue that query surfaces for a property of the
query, not the venue.

**Alternatives considered**:

- A four-letter prefix match: rejected outright (already in production before this fix; "comedy"
  matched "Comerica," "mini" matched "Mining").
- A five-letter prefix match, considered as the next-smallest fix: rejected. "Cooking" trimmed to
  five letters ("cooki") still matches inside "Cookies," so a longer prefix narrows the false-hit
  surface without eliminating it, since English compounds and coined names can share any prefix
  length with an unrelated word.
- An allowlist of venue categories the relevance check treats as always relevant, instead of a
  token match against the name/category text: rejected as brittle for the same reason D9 rejects
  an exclusion-side allowlist - a new activity type or a coined venue name would need a new
  allowlist entry before this scan could ever score it correctly, where the whole-word rule
  handles a new query with no maintenance at all.

## D13. Unparseable hours are unknown, never closed; the chmod bracket for a same-date overwrite

**Decision**: `apply_day_window` reads a day's own hours text that parses to no time range and
does not contain the word "closed" (an empty cell, or a phrase like "Hours might differ" the
range parser does not recognize) as `day_status = "unknown"`, never `"closed"`. Separately, the
report writer chmods each output file to `0600` both before opening it and again after writing
it.

**Rationale**: a venue's hours were never actually read in the unparseable case; scoring it as
provably closed would apply the score's full closed-day penalty (-1.0) to a venue whose real
hours are unknown, which is a worse mistake than leaving the score unaffected. On the file mode:
`os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)`'s own `mode` argument applies only
when the call creates a new file - it has no effect on a file that already exists, so a same-date
second run over a file whose mode had drifted to something looser (`0644`, for example) would
otherwise leave that looser mode in place after being rewritten. Chmodding both before the open
(for an existing file) and after the write (for a newly created one) closes both cases.

**Alternatives considered**:

- Treating unparseable hours as "closed" (the conservative default before this fix): rejected -
  see Rationale.
- Chmodding only once, after the write: rejected once traced through `os.open`'s own semantics
  above - it would leave a pre-existing file's drifted mode in place until the write itself
  completed, and an interrupted run could still leave a wrong mode behind; chmodding before is
  cheap and closes that gap.

## Alternatives considered (feature-level, not already covered under a specific D-number)

- **Building this as a multi-insurer-style `Errand`/`walk()` subclass, like
  `ProgressiveQuoteErrand`**: rejected. The walk framework (spec 005) exists for a multi-step,
  apply-mode form-filling journey with a human handoff. This scan has no form, no click, and no
  handoff - it is closer in shape to `probe.py` (open a page, read it, write an artifact) than to
  any walk-based errand, so it is written as its own standalone script composing `Session`
  directly, the same way `probe.py` already does.
- **Writing the scan's pure logic directly inside `scripts/activity_scan.py`**: rejected,
  matching this repository's own "thin package, one script per errand" pattern
  (`PATTERNS.md`) - the parsers, the scoring, and the renderers are unit-testable without a
  browser and belong in `headless/activities.py`, leaving the script itself to own only the
  browser calls and the CLI surface.
