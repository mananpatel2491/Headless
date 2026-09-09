# Feature Specification: Activity Scan (Rank Public Venues Around a Point for an Evening Out)

**Feature Branch**: `v0.0.9` (spec directory `009-activity-scan`)

**Created**: 2026-09-09

**Status**: Draft

**Input**: Retro-documentation of the v0.0.9 activity-scan errand. The errand is already
implemented and unit-tested (`headless/activities.py`, `scripts/activity_scan.py`,
`tests/test_activities.py`, `tests/test_activity_scan.py`, 140 tests). This document records what
the shipped code does as a Spec Kit set, after the orchestrator's own post-scan ranking patch
(2026-09-09, following the first live scan - see research.md D9 and D10), an Opus verifier's own
follow-on fix batch the same day, and a subsequent re-verification's own further fix batch, also
the same day.

## Why

The Director has a fixed evening window: a chosen point, a start time, and an end time. He
wants a ranked list of nearby options for that window. He does not want to read many search pages
by hand.

Recon on 2026-09-09 checked three review sources under headless Chrome. Google Maps' own list
view rendered fully: each result card carries a name, a rating, a review count, a category, an
address, today's hours, and its own coordinates. Yelp returned a "Verifying the device" wall.
TripAdvisor's attractions page rendered blank. The scan reads only Google Maps.

The Director's own first use rules out a movie or a dinner: an evening out is neither. The scan
excludes both categories by design.

This feature adds one read-only errand, `scripts/activity_scan.py`, and its pure logic module,
`headless/activities.py`. It writes no site data. It never has an apply mode.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The Director scans a point and gets ranked venues for his evening window (Priority: P1)

The Director gives a point and a day/time window. The scan searches a built-in list of activity
queries near that point, folds duplicate results, drops excluded categories and out-of-radius
venues, checks each top venue's own hours against the window, and writes a ranked Markdown and
JSON report.

**Why this priority**: this is the feature's whole purpose. Every other story supports or refines
this one scan.

**Independent Test**: stub the two browser-reading functions with fixed venue lists (one excluded,
one not) and run the script end to end. Assert the report contains the kept venue and omits the
excluded one, ranked by score.

**Acceptance Scenarios**:

1. **Given** a point and the default Friday 17:00-22:00 window, **When** the Director runs the
   scan with no other flags, **Then** the scan writes `reports/activity/activity-scan-<date>.md`
   and `.json` and prints `SCAN <path>`.
2. **Given** a result card whose category contains "movie theater", "cinema", "restaurant", or
   "fast food", **When** the scan ranks its results, **Then** that venue never appears in the
   report.
3. **Given** two result cards for the same venue at the same rounded coordinates, one sponsored
   and one not, **When** the scan folds duplicates, **Then** the report shows one entry, using the
   non-sponsored copy, and lists every query that found it.
4. **Given** a venue farther than `--radius-miles` from the point, **When** the scan ranks its
   results, **Then** that venue is dropped before scoring.
5. **Given** a shortlisted venue's own place page states its Friday hours, **When** the scan
   computes the day-window verdict, **Then** the venue's score reflects "closed", "open",
   "partial", or "unknown" exactly as the venue's own overlap with the window dictates.

---

### User Story 2 - The Director points the scan at a plain address, not only coordinates (Priority: P1)

`--near` accepts either `"lat,lon"` or a street address. When it is not a coordinate pair, the
scan resolves it once through Nominatim (OpenStreetMap) before it opens any browser session.

**Why this priority**: the Director's own chosen point is usually easier to state as an address
than to look up as coordinates first.

**Independent Test**: call the resolver with a fixture address and a stubbed HTTP fetch returning
a fixed geocode response. Assert it returns the expected point, and that a fetch failure returns
`None` rather than raising.

**Acceptance Scenarios**:

1. **Given** `--near "42.4800,-83.3800"`, **When** the scan resolves the point, **Then** it parses
   the pair directly and never makes a network call.
2. **Given** `--near` is an address, **When** the scan resolves the point, **Then** it sends
   exactly one Nominatim request and uses the first result.
3. **Given** the address cannot be resolved (empty result, network error, unparseable response),
   **When** the scan starts, **Then** it prints a refusal and exits before constructing any
   browser session.

---

### User Story 3 - The Director checks the scan's own selectors before he relies on it (Priority: P2)

`--check` opens one search page, waits for the results feed, and reports each dependent selector
as found or missing. It never scrolls the feed, never opens a place page, and never writes a
report.

**Why this priority**: Google's own markup can change. A cheap, read-only check lets the Director
confirm the scan still works before a real run, matching this repository's Lesson 4.

**Independent Test**: stub the session's `probe` call to report every selector but one as found.
Assert the printed summary line names the correct found/missing counts and that no report file is
written.

**Acceptance Scenarios**:

1. **Given** `--check`, **When** the scan runs, **Then** it navigates to the first configured
   query's search URL only.
2. **Given** `--check`, **When** the scan finishes, **Then** it prints one `found`/`MISSING` line
   per dependent selector, then `CHECK <n> found, <m> missing`, and exits 0 regardless of the
   count.

---

### User Story 4 - The Director substitutes his own list of queries (Priority: P2)

`--queries-file` replaces the built-in query list with tab-separated `tag<TAB>query` lines from a
named file.

**Why this priority**: the built-in list reflects one evening's brief. A later evening may call
for a different set of activities.

**Independent Test**: write a fixture file with one tagged line, one comment line, one blank line,
and one line with no tab. Assert the loader keeps only the tagged and untagged lines, and that the
untagged line defaults to tag `"custom"`.

**Acceptance Scenarios**:

1. **Given** `--queries-file <path>`, **When** the scan loads its queries, **Then** it reads only
   that file and ignores the built-in `DEFAULT_QUERIES` list entirely.
2. **Given** a line in the file with no tab character, **When** the loader parses it, **Then** the
   whole line becomes the query under tag `"custom"`.
3. **Given** a blank line or a line starting with `#`, **When** the loader parses the file,
   **Then** it skips that line.

### Edge Cases

- A venue with no rating at all (an unrated new listing) uses the prior rating (4.0) in the score,
  per the Bayesian-shrink rule.
- A venue with no coordinates in its own place link counts as 15 miles away for scoring, and is
  never dropped for being "out of radius" by that assumed distance alone unless the configured
  radius is under 15.
- Hours spanning midnight ("6 PM-1 AM") extend past 1440 minutes on the day's own axis, rather
  than wrapping to a negative time.
- The results feed can hold more venues than the scan's own 8-scroll cap can load; the scan keeps
  whatever the feed loaded and moves on.
- A queries file that resolves to zero lines is a refusal (`"no queries to run"`), never a silent
  no-op scan.
- `--start` and `--end` given as the same value is a refusal, never a zero-width window.
- A query Google answers by opening one place page directly, with no results feed at all
  (observed live for the query "Topgolf"), is read as that query's own single result, at
  `position` 0, rather than treated as zero results.
- A `--near` value shaped like a coordinate pair - including one carrying a leading "+" or a
  trailing ",<zoom>" or ",<zoom>z" as pasted from a map URL (for example, "+95,0" or "95,0,17z") -
  but out of range is a refusal, with no geocoder request ever sent: `looks_like_coordinates`
  tells such a pair apart from free text worth sending to Nominatim as an address.
- A `--near` value carrying a leading "+" or a trailing ",<zoom>" or ",<zoom>z" that IS in range
  (for example, "+42.48,-83.38" or "42.48,-83.38,17z", a pasted lat,lon,zoom triple) parses to the
  plain pair, the same as if the "+" and the zoom segment were absent.

## Requirements *(mandatory)*

### Functional Requirements

**Search and scroll**

- **FR-001**: The scan MUST accept `--near` as a required argument: either `"lat,lon"` or free
  text resolved as an address.
- **FR-002**: For each `(tag, query)` pair in the active query list, the scan MUST open
  `https://www.google.com/maps/search/<query> near <area>/` and wait for the results feed selector
  before reading it.
- **FR-003**: The scan MUST scroll the results feed by calling
  `evaluate("el => el.scrollBy(0, el.scrollHeight)")` on the feed element, never a click or a
  keypress. The scan MUST stop scrolling at whichever of the following comes first: the page's own
  "reached the end of the list" text appears; two consecutive scrolls each load no new card; or the
  scan reaches 8 scroll attempts (`MAX_FEED_SCROLLS`). A single slow-loading scroll MUST NOT stop
  the scan early.
- **FR-004**: The scan MUST parse each result card into a venue record: name, place-page URL, its
  own 0-based `position` in that query's own result list (the first card is 0), coordinates (from
  the `!3d<lat>!4d<lon>` pair embedded in the place link's own href), rating, review count,
  category, address, today's hours text, and a sponsored flag.

**Folding, locating, ranking**

- **FR-005**: The scan MUST fold two result records into one when their lowercased names match and
  their coordinates round to the same four decimal places. The folded record MUST keep a
  non-sponsored copy over a sponsored one, MUST union every query that found either copy into
  `matched_queries`, and MUST keep the lower of the two copies' own `position` value.
- **FR-006**: The scan MUST compute each venue's straight-line distance from the resolved point
  using the haversine formula, in miles. A venue with no coordinates has no computed distance and
  is treated as 15 miles away for scoring purposes only.
- **FR-007**: Before any exclusion check, the scan MUST check a venue's category text against a
  keep-list of named activity-rental phrases,
  `KEPT_CATEGORY_TERMS = ("kayak rental", "canoe rental", "paddleboard rental", "boat rental",
  "bike rental", "bicycle rental", "ski rental", "skate rental")`, each matched as a whole word: a
  category containing any of these phrases (for example, "Bike rental shop", "Kayak & canoe rental
  shop") is never excluded, because a rental business named this way is the activity itself. A
  category naming some other rental ("Tuxedo rental shop", "Party rental store", "Costume rental
  shop") is not on this list and is excluded normally - a bare "rental" keep-list would wrongly
  rescue it. The scan MUST then exclude a venue
  whose category text contains, case-insensitively and as a whole word (word-boundary matching,
  never a bare substring - so "shop" never matches inside "Pottery workshop"), any of: "movie
  theater", "cinema", "restaurant", "fast food" (never an evening outing for two adults); "store",
  "shop", "supply", "boutique", "dealer", "repair", "tinting", "roaster", "bubble tea", "florist",
  "framing" (retail, not an activity); "wedding venue", "banquet", "coworking", "co-working",
  "dj service", "event planner" (a venue or a service for hire, not a place to visit);
  "playground", "kids", "children", "toy", "elementary school", "primary school", "middle school",
  "high school", "preschool", "nursery", "day care", "daycare", "fitness program", "tutoring" (a
  kid-only place; naming only the kid-only school kinds, never a bare "school", keeps the "Dance
  school" and "Cooking school" categories two default queries exist to find). See FR-031 through
  FR-034 for the ranking refinements the first live scan (2026-09-09) added alongside this extended
  list.
- **FR-008**: The scan MUST drop a venue whose computed distance exceeds `--radius-miles` (default
  20). A venue with no computed distance is never dropped by this rule alone.
- **FR-009**: The scan MUST score a kept venue as: a Bayesian-shrunk rating (the venue's own
  rating and review count shrunk toward a prior of 4.0 stars with a weight of 25 phantom
  reviews), minus 0.04 for every mile of distance, minus 0.015 for every place down the venue's
  own query's Google result list when that place is known (FR-031), plus 0.35 when the venue's
  name or category echoes a query stem and minus 0.25 when it echoes none (FR-032), then adjusted
  by the day-window verdict (FR-013): minus 1.0 for "closed", plus 0.2 for "open", plus 0.05 for
  "partial", unchanged for "unknown".
- **FR-010**: The scan MUST sort kept venues by descending score, then by ascending distance, then
  by name, as a stable tiebreak order.

**Detail enrichment and the day-window verdict**

- **FR-011**: For the top `--details` ranked venues (default 60), the scan MUST open that venue's
  own place page and read its weekly hours table, its website link, and its phone and address
  buttons.
- **FR-012**: The scan MUST parse each weekly-hours table row into a `{day: hours-text}` mapping,
  keeping only rows whose text starts with a day name, and keeping the first such row per day.
- **FR-013**: The scan MUST compute a day-window verdict for the configured `--day` from that
  day's own hours text and the configured `--start`/`--end` window: "closed" when the venue's own
  hours have zero overlap with the window, "open" when the overlap is at least 80% of the window's
  length, "partial" for any smaller nonzero overlap, and "unknown" when the venue was not enriched
  (FR-011), or its hours for that day were never read, or the day's own hours text parses to no
  time range and does not contain the word "closed" (an empty cell, or text such as "Hours might
  differ" that the range parser does not recognize - the hours were never really read, so the
  verdict MUST be "unknown", never "closed").
- **FR-014**: After enrichment, the scan MUST re-score and re-rank every kept venue using the
  day-window verdict just computed.

**Reporting**

- **FR-015**: The scan MUST write two files under `reports/activity/`:
  `activity-scan-<UTC date>.md` and `activity-scan-<UTC date>.json`, both at file mode `0600`.
- **FR-016**: The Markdown report MUST open with the scan's own parameters (point, window,
  generation timestamp, source, venue count), followed by a "Top picks overall" table, then one
  table per tag, each row showing rank, venue name (linked to its website when known), rating,
  distance and drive-minutes estimate, category, the configured day's hours text, address, and the
  first two entries of `matched_queries` under a "Found via" column.
- **FR-017**: The JSON report MUST be a single object: `{"meta": {...the scan's own run
  parameters...}, "venues": [...every ranked venue as a flat dictionary...]}`.
- **FR-018**: On success, the scan MUST print exactly one line, `SCAN <markdown report path>`.

**Address resolution**

- **FR-019**: When `--near` does not parse as a `"lat,lon"` pair, the scan MUST resolve it as an
  address through exactly one Nominatim (OpenStreetMap) HTTP request, sent with a fixed,
  identifying User-Agent header.
- **FR-020**: When address resolution fails for any reason (a network error, an empty result, an
  unparseable response), the scan MUST print a refusal naming that `--near` could not be resolved
  and exit 1, without constructing a browser session.
- **FR-021**: `--area`, defaulting to the raw `--near` text when omitted, MUST be appended to every
  search query as `"<query> near <area>"`.

**Check mode**

- **FR-022**: `--check` MUST navigate to the first configured query's own search URL only, wait for
  the results feed, then report each of the feed selector, the feed-scoped place-link selector,
  and the rating selector as found or missing.
- **FR-023**: `--check` MUST print one line per selector (`found` or `MISSING`), then one summary
  line, `CHECK <found count> found, <missing count> missing`, and exit 0 regardless of the
  outcome.
- **FR-024**: `--check` MUST NOT scroll the results feed, open any place page, or write any report
  file.

**Custom queries**

- **FR-025**: `--queries-file`, when given, MUST replace the built-in `DEFAULT_QUERIES` list
  entirely with tab-separated `tag<TAB>query` lines read from the named file, skipping blank
  lines and lines starting with `#`. A line with no tab character MUST become a query under tag
  `"custom"`.
- **FR-026**: When `--queries-file` is omitted, the scan MUST run the built-in `DEFAULT_QUERIES`
  list unchanged.

**Read-only guarantee**

- **FR-027**: `--apply` MUST always be refused with the exact message `"REFUSED: activity_scan is
  read-only; there is no apply mode"` and exit 1, before any configuration beyond argument parsing
  is resolved and before any network or browser call.
- **FR-028**: The scan MUST never call `.fill(`, `.type(`, `.press(`, `.click(`, `.dblclick(`,
  `.select_option(`, `.check(`, or `.set_input_files(` on any page or locator object.
- **FR-029**: The scan MUST require no secret and no vault item. The point (`--near`) MUST be a
  command-line argument only, never written to or read from the profile registry or any vault
  item.

**Exit codes**

- **FR-030**: The scan MUST exit 1 for a malformed `--start`/`--end` value, identical `--start`
  and `--end`, an empty resolved query list, an unresolvable `--near`, or `--apply`; MUST exit 2
  for an argument-parsing error or an unhandled exception during the browser session (printing the
  exception's own class name, never its message, unless `HEADLESS_DEBUG=1`); and MUST exit 0
  whenever a report is written or `--check` completes.

**Ranking refinements and the single-place path (added after the first live scan, 2026-09-09;
see research.md D9 and D10)**

- **FR-031**: The scan MUST record, for each result, its own 0-based `position` - the place the
  result held in its own query's result list (the first card is `0`; a query answered by a single
  place page also records `0`, per FR-033). `score_venue` MUST subtract 0.015 for every place a
  venue's own `position` counts, when that value is known, and MUST leave the score unaffected
  when it is not.
- **FR-032**: The scan MUST set a venue's own `relevant` flag before scoring. The scan builds one
  whole-word pattern per query (`relevance_pattern`). The pattern starts from each
  meaning-carrying token of the query (`query_tokens`: the query's own words of three or more
  letters, minus a fixed generic-word set such as "near", "with", "class", or "venue"). The
  pattern also carries each token's own inflection roots (`_bases`): a token ending "ing" with
  more than 5 characters also contributes its root without "ing"; a token ending "ery" with more
  than 5 characters contributes its root without "ery" and the token minus its last letter; a
  token ending "es" with more than 4 characters contributes its root without "es"; a token
  ending "s" with more than 3 characters contributes its root without "s". The scan drops any
  resulting root with fewer than 3 characters. When a query carries no meaning-carrying token at
  all (for example, a `--queries-file` line reading "cafe bar club"), `relevance_pattern` returns
  no pattern for that query. The scan sets `relevant` to `True` when the venue's name or category
  contains, as a whole word with a boundary on both sides, any token or root above, optionally
  followed by one suffix from "e", "s", "es", "ing", "ed", "er", "ers", or "ery"; to `False` when
  no such word appears but at least one query that surfaced the venue did carry a
  meaning-carrying token; and to `None` (neutral, no score change) when no query that surfaced the
  venue carries a meaning-carrying token at all. Separately from every case above, `relevant`
  stays unset (`None`) until ranking runs. This is a whole-word rule, never a prefix rule: "paint"
  matches "Painting studio", "trails"
  matches "Trail Loop" but never "Trailhead", "winery" matches "Wine bar", "brewery" matches
  "Brewing Company", "cidery" matches "Cider mill", and "comedy" never matches "Comerica", "mini"
  never matches "Mining", "cooking" never matches "Cookies". Known residuals, both directions: a
  token that is also
  an ordinary word ("pool", "live", "game", "board", "rock", "mini") still matches that word
  wherever it appears as a word ("Board of Education", "Mini Storage"); and a compound or coined
  name that only starts with a token ("Trailhead", "Escapology", "Ziplining Adventures",
  "Brewhouse") misses the word-boundary match entirely, costing that venue the 0.6-point swing
  between a hit and a miss - Google's own list position and the venue's own rating still carry
  such a venue; the relevance term is a nudge, not a gate.
  `score_venue` MUST add 0.35 to the score when `relevant` is `True`, subtract 0.25 when it is
  `False`, and leave the score unaffected when it is `None`.
- **FR-033**: When a query's own page carries no results feed and its URL contains
  "/maps/place/" (Google opened one place directly, observed live for the query "Topgolf"), the
  scan MUST read that page as the query's single result instead of treating the query as zero
  results: the venue's own name from the page title with a trailing " - Google Maps" removed, its
  rating from the page's own star label when that label carries a review count, and its weekly
  hours, website, phone, and address read the same way as any other shortlisted venue's own place
  page. The scan MUST print `  '<query>': 1 result (Google opened the place directly)` for this
  case.
- **FR-034**: The place-link coordinate parser MUST fall back to a place page's own
  `/@<lat>,<lon>,` viewport coordinate pair when the page's own `!3d<lat>!4d<lon>` pair is absent
  from its URL.

**Fail-soft reads (Opus verifier fix batch, 2026-09-09)**

- **FR-035**: When navigating to, or reading, a single query's own search page raises an
  exception, the scan MUST catch it, print `note: query skipped for '<query>' (<ExceptionClass>)`,
  and continue with the remaining queries rather than let one query's own failure end the whole
  scan; the scan MUST still write its report from every query that succeeded. This closes the
  asymmetry between the query-page read (now fail-soft) and the per-venue detail-page read
  (FR-011, already fail-soft): both a query page and a place page are fail-soft.

### Non-Functional Requirements

- **NFR-001**: The default `pytest -q` run MUST exercise every path this feature adds through a
  stubbed session and stubbed browser-reading functions - zero real browser launches, zero real
  network calls.
- **NFR-002**: Every fixture and example in this feature's own document set and test suite MUST
  use only synthetic or already-public data (a public city label, a synthetic round-number
  coordinate pair, a reconstructed result-card shape) - no personal place name, no
  household-role reference, and no real address.
- **NFR-003**: The scan MUST NOT read or write any secret, vault item, or profile registry path.

### Key Entities

- **Venue**: one ranked result - name, place-page URL, tag, query, its own 0-based position in
  that query's result list, coordinates, rating, review count, category, address, today's hours
  text, sponsored flag, distance, drive-minutes estimate, weekly hours, day-window overlap and
  verdict, website, phone, matched queries, whether its name or category echoes a query
  (`relevant`), score, and an excluded flag.
- **DEFAULT_QUERIES**: the built-in list of 35 `(tag, query)` pairs, grouped into five tags
  (outdoors, active, games, creative, nightlife), chosen to exclude movies and dinner.
- **Day-window verdict**: one of "closed", "open", "partial", "unknown" - computed from a venue's
  own hours for the configured day against the configured start/end window.
- **Activity-scan report**: the two files this feature writes,
  `reports/activity/activity-scan-<date>.md` and `.json` - see
  `contracts/scan-and-report.md` for their exact shape.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The full `pytest -q` suite, including this feature's own 140 tests, passes with zero
  real browser launches and zero real network calls.
- **SC-002**: A unit test proves the Bayesian shrink ranks a venue with many reviews at a moderate
  rating above one with very few reviews at a perfect rating.
- **SC-003**: A unit test proves the score drops by approximately 0.72 across an 18-mile distance
  difference (0.04 per mile) and by approximately 1.2 between a "closed" and an "open" day-window
  verdict at the same distance and rating.
- **SC-004**: A unit test proves duplicate folding keeps the non-sponsored copy and unions every
  query that found either copy.
- **SC-005**: A unit test proves ranking drops an excluded category and an out-of-radius venue, and
  sorts the remainder by descending score.
- **SC-006**: A unit test proves the CLI never constructs a browser session when `--apply` is
  given, `--near` cannot be resolved, or `--start` equals `--end`.
- **SC-007**: A unit test proves `--check` reports exactly three selectors, prints the correct
  found/missing summary line, and writes no report file.
- **SC-008**: A unit test proves a stubbed end-to-end scan writes exactly one Markdown and one
  JSON report file, that an excluded-category venue never appears in either, and that a scored
  venue's `day_status`/`window_overlap_minutes` match its stubbed hours.
- **SC-009**: A unit test proves `--queries-file` fully replaces the built-in list and that an
  untagged line defaults to tag `"custom"`.
- **SC-010**: The existing structural test (`tests/test_no_direct_typing.py`) continues to pass
  against `scripts/activity_scan.py` - no direct fill, type, click, or similar call exists in that
  file.
- **SC-011**: Recon against the live Google Maps list view under headless Chrome (2026-09-09)
  confirmed every selector this feature depends on resolves; the same recon confirmed Yelp and
  TripAdvisor refuse headless Chrome and are never read by this feature.
- **SC-012**: A unit test proves the score drops by 0.015 for every place down a venue's own
  query's result list when that place is known, gains 0.35 when the venue's name or category
  echoes a query stem, and loses 0.25 when it echoes none.
- **SC-013**: A unit test proves a query answered by a single place page (no results feed) is
  read through `read_single_place` as that query's one result, at `position` 0, and that the
  place-link coordinate parser falls back to the page's own viewport pair when the
  `!3d<lat>!4d<lon>` pair is absent from its URL.

## Assumptions

- Google Maps' own list-view markup (the `role="feed"` container, the `/maps/place/` link shape,
  the `data-item-id` attributes on a place page) remains as recorded by the 2026-09-09 recon.
  `--check` exists precisely so a later drift is caught read-only, before a real scan is trusted.
- Nominatim's own free usage policy (a low request rate, a real User-Agent) is respected because
  the scan sends at most one geocoding request per run.
- The drive-minutes figure is a suburban estimate for reading and ranking, never a routing
  promise.
- English-language results are assumed (AM/PM hour formats, English day names, English category
  and status words).
- The Director runs this scan by hand, for one evening at a time; nothing in this feature
  schedules or repeats a scan automatically.

## Out of Scope

- Reading Yelp, TripAdvisor, or any review source besides the Google Maps list view.
- Any write action on any site - there is no `--apply` mode and none may be added.
- Booking, reserving, or otherwise confirming availability at any venue.
- Multi-day or recurring scans in a single run.
- Any UI beyond the two report files this feature writes.
- Caching or deduplicating results across separate scan runs.
