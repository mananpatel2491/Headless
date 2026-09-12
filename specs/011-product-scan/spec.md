# Feature Specification: Product Scan (Rank Public Retail Listings for a Wanted Product)

**Feature Branch**: `v0.0.11` (spec directory `011-product-scan`)

**Created**: 2026-09-11

**Status**: Draft

**Input**: Director request, 2026-09-11 ("using the headless repo," explore a product's options and
decide whether a chosen listing is the best value). This generalizes roadmap item 4 of the
Headless applications list (Director, 2026-08-25: "Amazon/Walmart search (no secrets, can ship any
time)") into a read-only errand that ranks public retail listings for any product query. This
document specifies `scripts/product_scan.py` and `headless/products.py` before their own code
lands, from the same brief the implementation builder works from in parallel. The orchestrator
reconciles any as-built delta against this document after an Opus verification.

## Why

A listing the Director was sent, for lawn edging: a 4 inch tall, no-dig HDPE plastic
roll with steel U-stakes, 40 feet for $31.58, or 100 feet for $66.49 (out of stock at the time of
writing). The listing's own title changed from "GOTGELIF" to "BSHAPPLUS" while its item id stayed
`18656266943` - the same physical product, relisted under a different brand name. The Director
asked whether that pick is the best value, or whether spending more buys a product that lasts
longer. This feature answers that question for any product query, not only this one.

Recon on 2026-09-11 (headless Chrome 151, shared profile, `scripts/probe.py` and read-only
Playwright reads) checked seven retail search surfaces.

| Site | Headless result | Verdict |
| :-- | :-- | :-- |
| Amazon (`www.amazon.com/s?k=<query>&page=N`) | Title `Amazon.com : <query>`; 48 cards on each of pages 1 and 2; every dependent selector resolved on every card; zero of 48 cards carried a sponsored label on this profile | Primary source, read by default |
| Home Depot (`www.homedepot.com/s/<query>`) | First visit: 24 `[data-testid="product-pod"]` pods (12 unique products, each pod duplicated once in the DOM). Every later visit within about ten minutes: title `Error Page`, body "Oops!! Something went wrong. Please refresh page", zero pods | Opt-in second source (`--sites amazon,homedepot`), read best-effort; an `Error Page` title is a wall, noted and skipped |
| Walmart (`www.walmart.com/ip/<id>`, `/search?q=`) | Redirects to `/blocked?url=...`, title `Robot or human?` | Reference-only: never a search site; a Walmart URL is read only through `--reference-url`, and the wall is expected, not a failure |
| Lowe's (`www.lowes.com/search?searchTerm=`) | Title `Access Denied` | Trap, never read |
| Google Shopping (`www.google.com/search?tbm=shop`) | Redirects to `/sorry/index` (a captcha wall) | Trap, never read |
| Menards (`www.menards.com/main/search.html`) | Empty title, blank page | Trap, never read |
| Target (`www.target.com/s?searchTerm=`) | The title and body text render, but none of the expected `data-test` card attributes exist | Deferred, not read this delivery |

Amazon is the one source that renders fully, carries every field the ranking needs (a title, a
price, a rating, a review count, and no sponsored labels to work around on this profile), and
needs no scroll. Home Depot renders once, then walls itself off on repeat visits, so it ships as
an opt-in, best-effort second source rather than the default. Walmart is exactly the listing the
Director's own question is about, but it is a bot wall behind every headless request; the errand
reads it only as a named reference, with `--show` as the Director's own escape hatch to pass the
wall by hand, and `--reference` as the fully headless fallback (typing the three public facts -
title, price, length - by hand).

This feature adds one read-only errand, `scripts/product_scan.py`, and its pure logic module,
`headless/products.py`. It writes no site data. It never has an apply mode.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The Director scans a product query and gets a ranked, tiered report (Priority: P1)

The Director gives a product query. The scan searches Amazon (the default site), parses each
result card into a `Listing`, folds duplicates, excludes non-matching categories of result
(a fence panel, a stakes-only pack), scores every kept listing, groups the scored listings into
three material tiers, and writes a ranked Markdown and JSON report.

**Why this priority**: this is the feature's whole purpose. Every other story supports or refines
this one scan.

**Independent Test**: stub the Amazon search read with a fixed set of listing titles drawn from
the 2026-09-11 recon (one excluded by category, one plastic, one metal). Run the script end to
end. Assert the report keeps the two kept listings, tiered correctly, and omits the excluded one.

**Acceptance Scenarios**:

1. **Given** a query and no other flags, **When** the Director runs the scan, **Then** it reads
   only Amazon across the default two pages, writes
   `reports/product/product-scan-<slug>-<date>.md` and `.json`, and prints `SCAN <path>`.
2. **Given** a title carrying both a stake phrase and a material word (for example, "150 Stainless
   Steel Stakes" on a plastic roll), **When** `parse_attributes` runs, **Then** the stake phrase is
   extracted and removed before the material rule runs, so the roll tiers as plastic, not metal.
3. **Given** two Home Depot pods for the same product, duplicated in the DOM, **When** the scan
   folds duplicates, **Then** the report shows one listing, keeping the copy with the lower
   `(page, position)` and the union of every page it was found on.
4. **Given** a listing with no parsable price or no parsable length, **When** the scan scores it,
   **Then** it is still ranked, carries the flag `price unknown` or `length unknown`, and its
   score's price component reads as a fixed penalty rather than a computed one.
5. **Given** a title matching an exclusion rule ("fence, not edging" or "stakes only"), **When**
   the scan ranks its results, **Then** that listing never appears in any tier table and is
   counted once under `## Excluded`.

---

### User Story 2 - The Director sees where the listing he was sent would rank (Priority: P1)

`--reference-url` or `--reference` names the listing the Director was actually sent. The scan
reads it (or accepts the hand-typed facts), scores and tiers it exactly like a search result, and
states its rank within its own tier.

**Why this priority**: this is the Director's actual question - not "what is out there," but
"is the listing already picked the right call." Every other feature in this errand serves
this comparison.

**Independent Test**: stub an Amazon product-page read returning a fixed title, price, and rating.
Run the scan with `--reference-url` pointing at that fixture and a small set of stubbed search
results. Assert the report's reference block names the correct rank and tier.

**Acceptance Scenarios**:

1. **Given** `--reference-url` pointing at an Amazon product page that reads successfully, **When**
   the scan renders the report, **Then** the reference's `origin` is `reference-url` and the
   reference block states its rank within its tier ("your pick would rank #k of n in the plastic
   tier").
2. **Given** `--reference-url` pointing at a Walmart product page, **When** that page shows the
   bot wall (title `Robot or human?`, or a `/blocked?` URL), **Then** the scan prints
   `note: reference not readable headless (bot wall) - rerun with --show` and falls back to
   `--reference` when it was also given.
3. **Given** `--reference "BSHAPPLUS 4in x 40ft No Dig Landscape Edging | 31.58 | 40"` with no
   `--reference-url`, **When** the scan runs, **Then** the reference is scored and tiered the same
   way a search result is, with `origin` set to `reference-hand`.
4. **Given** a malformed `--reference` value (not three pipe-separated parts, an unparsable price,
   or an unparsable length), **When** the CLI parses arguments, **Then** it refuses before opening
   any browser.
5. **Given** `--reference-url` naming a host outside `REFERENCE_HOSTS` (for example, a Lowe's
   URL), **When** the CLI parses arguments, **Then** it refuses before opening any browser.

---

### User Story 3 - The Director checks the scan's own selectors before he relies on it (Priority: P2)

`--check` opens page 1 of every selected site, probes that site's own dependent selectors, and
reports each as found or missing. It never scrolls, never reads a reference, and never writes a
report.

**Why this priority**: a retailer's own markup can change at any time. A cheap, read-only check
lets the Director confirm the scan still works before a real run, matching this repository's
Lesson 4.

**Independent Test**: stub the session's `probe` call to report every Amazon selector but one as
found. Assert the printed summary line names the correct found/missing counts and that no report
file is written.

**Acceptance Scenarios**:

1. **Given** `--check`, **When** the scan runs, **Then** it opens page 1 of every site named in
   `--sites` only, never scrolls a feed, and never opens a reference page.
2. **Given** `--check`, **When** it finishes, **Then** it prints one `found`/`MISSING` line per
   dependent selector for each selected site, then one summary line,
   `CHECK <n> found, <m> missing`, and exits 0 regardless of the count.

---

### User Story 4 - The Director opts into Home Depot as a second search site (Priority: P2)

`--sites amazon,homedepot` adds Home Depot's own search pages alongside Amazon's. Home Depot's
lazy-loaded pods are scrolled into view; a wall on Home Depot's own first page skips the rest of
its pages without affecting Amazon's results.

**Why this priority**: a second retailer widens the field the Director's question is answered
against, but Home Depot's own repeat-visit wall (recon 2026-09-11) means it can never be the
default - it has to be an opt-in, best-effort addition.

**Independent Test**: stub a Home Depot search read returning 24 pods for 12 unique products
(the observed DOM-duplication shape). Assert the folded report holds 12 listings, not 24.

**Acceptance Scenarios**:

1. **Given** `--sites amazon,homedepot`, **When** the scan runs, **Then** it reads both sites'
   search pages and folds their listings into one ranked, tiered set.
2. **Given** Home Depot's own search page returns the title `Error Page` on a later visit,
   **When** the scan reads that page, **Then** it prints
   `note: page skipped for 'homedepot p<N>' (wall: Error Page)`, skips Home Depot's remaining
   pages, and continues with Amazon's results.
3. **Given** a site id outside `("amazon", "homedepot")`, **When** `--sites` is parsed, **Then**
   the scan prints `REFUSED: unknown site '<id>' (known: amazon, homedepot)` and exits 1 before
   opening any browser.

### Edge Cases

- A title carrying more than one foot figure ("100FT Landscape Edging Kit ... 2 x 50FT 1.5"
  Flexible Rolls") keeps the first, larger, standalone foot figure - the assumption that the
  listed price belongs to the title's own first/default variant, not a smaller sub-roll figure
  named later in the same title.
- An inch-only length ("40\" L x 6\" H", "39 x 4 Inch", "20\"x5.3\"") gives `length_ft = None`; the
  height in the same title is still parsed correctly.
- Stake-phrase stripping happens before material matching, so "150 Stainless Steel Stakes" on a
  plastic roll never tiers that roll as metal.
- Home Depot's own pods duplicate in the DOM (24 pods, 12 unique hrefs, recon 2026-09-11); the
  fold key is the canonical product URL, never the card's own position in the DOM.
- Home Depot's second and later visits within about ten minutes return the title `Error Page` with
  zero pods, even after a scroll and a wait; the scan reads this as a wall, prints a note, and
  skips Home Depot's remaining pages rather than retrying.
- Walmart is never a search site. A Walmart URL is read only through `--reference-url`, and only
  after every search page has already been read.
- `--min-height-in` drops a listing whose parsed height falls below the threshold from every tier
  table, counted once under "dropped by height" in the header block. A listing with no parsable
  height at all is kept and flagged "height unknown" - it is never dropped by this rule alone.
- A query that returns zero listings on every selected site (every page walled or every page
  raising an exception) still writes a report, with every skip recorded under `## Notes`, and
  exits 0.
- `--reference-url` and `--reference` given together: a successful URL read wins; the literal
  supplies the reference only when the URL read fails, walls, or was refused for an unsupported
  host before it could even be attempted (in which case the whole run refuses before either is
  read).
- A sponsored Amazon card is never dropped, only penalized in its score; recon on this profile
  found zero sponsored cards across 48, so the check exists but is unexercised by any live run so
  far.
- Lowe's, Google Shopping, and Menards are never opened by this errand, not even as a reference
  host. Target's markup lacks the expected card attributes and is deferred, not read, in this
  delivery.

## Requirements *(mandatory)*

### Functional Requirements

**Query and site selection**

- **FR-001**: The scan MUST require `--query` and MUST refuse an empty value, or a value that is
  empty after stripping surrounding whitespace, with `REFUSED: --query must not be empty`.
- **FR-002**: `--pages` MUST default to 2. The scan MUST refuse a value outside 1 through 5.
- **FR-003**: `--sites` MUST default to `"amazon"`. Its value MUST be a comma-separated list drawn
  from `SITES = ("amazon", "homedepot")`. The scan MUST refuse any other site id with
  `REFUSED: unknown site '<id>' (known: amazon, homedepot)`.

**Search reads (Amazon, Home Depot)**

- **FR-004**: For each site named in `--sites` and each page number from 1 through `--pages`, the
  scan MUST open that site's own search URL for the given page and parse every result into a
  `Listing`.
- **FR-005**: `search_url(site, query, page_number)` MUST build the Amazon URL as
  `https://www.amazon.com/s?k=<quote_plus(query)>&page=<page_number>` and the Home Depot URL as
  `https://www.homedepot.com/s/<quote(query)>`, appending `?Nao=<24*(page_number-1)>` only when
  `page_number` is greater than 1.
- **FR-006**: Amazon needs no scroll: the scan MUST read the 48 cards a loaded search page already
  renders. An Amazon card's ASIN (its `data-asin` attribute, or the `/dp/<10 chars>` segment of its
  link) MUST feed `canonical_url`.
- **FR-007**: Home Depot's own pods are lazy-loaded: the scan MUST scroll with
  `page.evaluate("window.scrollBy(0, document.body.scrollHeight)")` and a wait, up to 6 attempts,
  stopping after two consecutive scrolls add no new pod - the same stale-pass rule
  `activity_scan.py` already uses for its own results feed.
- **FR-008**: A wall detected on a site's own page 1 (its title present in `WALL_TITLES`, or its
  URL containing `/blocked?`) MUST stop that site's remaining pages for this run, print
  `note: page skipped for '<site> p<N>' (wall: <title>)`, and MUST NOT stop any other selected
  site or the reference read.
- **FR-009**: An exception raised while navigating to, or reading, a search page MUST be caught,
  printed as `note: page skipped for '<site> p<N>' (<ExceptionClassName>)`, and the scan MUST
  continue with that site's remaining pages. A page that loads with zero cards or pods MUST print
  `note: page skipped for '<site> p<N>' (zero cards)` and MUST NOT stop the scan.

**Reference reading**

- **FR-010**: `--reference-url` MUST be accepted only for a host present in `REFERENCE_HOSTS`
  (`www.amazon.com`, `amazon.com`, `www.walmart.com`, `walmart.com`). Any other host MUST be
  refused with `REFUSED: unsupported reference host '<host>'`, before any browser opens (fix batch
  B3, 2026-09-11: the shipped message is this shorter form; the document is corrected to it).
- **FR-011**: The reference page, when given and its host is supported, MUST be read after every
  search page has already been read.
- **FR-012**: A wall on the reference page (its title present in `WALL_TITLES`, or its URL
  containing `/blocked?`) MUST print `note: reference not readable headless (bot wall) - rerun
  with --show` and MUST NOT raise. When `--reference` was also given, its literal value becomes
  the reference; otherwise the report carries no reference block.
- **FR-013**: `--reference` MUST accept three, four, or five pipe-separated parts - a title, a
  price (with or without a leading `$`, refused if it parses to zero or negative, or opens with a
  literal `-`), a length in feet (with or without a trailing `ft` or `'`, refused on the same
  zero/negative/leading-`-` terms), an OPTIONAL 4th part, a rating from 0 through 5 inclusive, and
  an OPTIONAL 5th part (only when a 4th is present), a review count of 0 or more (fix batch
  A4/B7, 2026-09-11). The reference `Listing` carries the parsed rating/reviews and is scored with
  them exactly like a search result, so the reference block and its table row show `4.1 (15)`
  instead of `-`. Any other shape, or a malformed 4th/5th part, MUST be refused with
  `REFUSED: expected "Title | price | length_ft [| rating [| reviews]]"`, before any browser opens
  (fix batch B3: the shipped message is this shorter form).
- **FR-014**: When both `--reference-url` and `--reference` are given, a reference-page read that
  succeeds MUST win; `--reference`'s literal value is used only when the URL read fails, walls, or
  was never attempted.
- **FR-015**: The reference `Listing`'s own `origin` field MUST read `"reference-url"` for a
  successful page read, and `"reference-hand"` for the literal.

**Attribute parsing (`headless/products.py`, no Playwright import)**

- **FR-016**: `parse_attributes` MUST first normalize a title's text: replace U+00D7 (`×`) with
  `x`, U+2011 (non-breaking hyphen) with `-`, U+201D/U+2033 with `"`, U+2019/U+2032 with `'`,
  remove U+200B, replace U+FF0C (`，`) with `,`, replace U+FF08/U+FF09 (`（`/`）`) with `(`/`)`
  (fix batch A6, 2026-09-11), and collapse repeated whitespace.
- **FR-017**: `parse_attributes` MUST extract a stake phrase (a count, an optional material word,
  and a noun such as "stakes" or "spikes") into `stake_count` and `stake_material` from the FIRST
  such COUNTED phrase only, and MUST remove EVERY stake/spike/nail/staple/anchor/peg/pin phrase
  from the working text before any later parsing step - counted or not (fix batch A2/B5,
  2026-09-11: an uncounted phrase, "with Metal Stakes," is stripped exactly like a counted one,
  and yields no `stake_count`/`stake_material` of its own) - so a stake phrase's own material word
  never feeds the roll's own material rule. The counted-phrase count MUST NOT be read starting on
  the trailing digits of a decimal fraction (fix batch B13: "7.8In Height Stakes" must never read
  a count of 8 off the ".8").
- **FR-018**: `parse_attributes` MUST parse `height_in` from a candidate matching an inch or
  double-quote unit, preferring a candidate whose following twelve characters name "tall," "high,"
  "height," or "(h)" over the first candidate when no such candidate exists; MUST reject a value
  outside 0.5 through 24; and MUST NOT read a candidate whose following eight characters name a
  length ("L," "long," "length") as a height. Both context windows (the twelve- and eight-character
  ones) MUST end at the first digit encountered - so a LATER dimension's own number (the "2" of a
  following `2.25" H`) can never fall inside an EARLIER candidate's own window - and MUST NOT end
  mid-word when no digit intervenes, extending to that word's own end instead (fix batch B11/B12,
  2026-09-11: a plain fixed-length cutoff both let a later `H`-marked height claim an earlier
  number, and manufactured a false `L` match by cutting a window off exactly after the "L" of
  "Landscape").
- **FR-019**: `parse_attributes` MUST parse `length_ft` from the first candidate matching a foot or
  a LONE single-quote unit (never a double-quote, and never a single quote itself preceded or
  followed by another `'` or a `"` - fix batch A3/B2, 2026-09-11: `''` and `"` are inch marks, so
  `4'' X 100'` reads as 4 inches by 100 feet, never 4 feet by 100 feet), taking the first number
  when the title names a range or more than one variant; MUST reject a value outside 1 through
  1000; and MUST leave `length_ft` as `None` when every candidate on the title is an inch-only
  figure. A title-stated grand total (`"66FT Total"`, `"(Total 100 Ft)"`) MUST override every other
  length candidate (fix batch A6/B14).
- **FR-020**: `parse_attributes` MUST determine `material` on the stake-stripped text, in this
  precedence order: `steel` (cor-ten, corten, weathering steel, stainless, galvanized, or steel);
  `aluminum`; `metal` (a bare "metal" not already caught above); `rubber`; `stone-look` (a
  decorative-stone claim only - "faux stone," "stone effect," "stone look," "stone like," "stone
  texture," "polyrock," "bricks," "cobblestone," or "concrete" - fix batch A1/B4, 2026-09-11: a
  bare "stone" or "paver" no longer qualifies, since a title merely listing "Paver" among its uses
  is not a decorative-stone claim); `wood` (wood, timber, or bamboo); `plastic` (plastic,
  hdpe, polyethylene, a bare "pe," a bare "poly," pvc, polymer, or vinyl); `unknown` otherwise.
- **FR-021**: `parse_attributes` MUST set `no_dig` to `True` when "no dig" or "no-dig" appears
  anywhere in the normalized title.
- **FR-022**: `parse_attributes` MUST set `excluded_reason` to `"fence, not edging"` for a title
  that names an animal barrier, "fencing", fence panels (a "fence panels" or "N panels ... fence"
  phrase, in either order), or a trellis. A title that merely lists "fence" among its uses, that
  carries "fence" inside a brand name, or that describes a decorative "fence look" is edging and
  MUST NOT be excluded (post-batch live re-run finding, 2026-09-11). It MUST set the reason to
  `"stakes only"` for a title naming only stakes or spikes for sale (no roll or panel of its own);
  and to `None` otherwise.
- **FR-023**: `price_per_ft(price, length_ft)` MUST return `price / length_ft` rounded to 3
  decimal places, and MUST return `None` when either `price` or `length_ft` is `None`.
- **FR-023a** (fix batch A6, 2026-09-11): `is_pack(title)` MUST report `True` when the
  stake-stripped title names a pack or piece count (`"5 Piece"`, `"6 Pack"`, or the reversed real-
  title order `"(Pack 6)"`), so a stake count itself phrased as "Pcs" (`"120 Pcs Metal Spikes"`)
  is never mistaken for a physical multi-piece pack. When `is_pack(title)` is true AND a
  `length_ft` was parsed, the `Listing` MUST carry the flag `"pack: per-piece length"` - such a
  title's own `$/ft` prices one piece, not the whole roll, by design, and the report's own Length
  cell for that listing MUST read `"<length> ft (per piece)"`.

**Scoring and tiers**

- **FR-024**: `score_listing` MUST compute a Bayesian-shrunk rating,
  `(rating * reviews + prior_rating * prior_weight) / (reviews + prior_weight)`, using
  `prior_rating = 4.0` and `prior_weight = 25`, reading a missing `rating` as `prior_rating` and a
  missing `reviews` as `0`, and MUST set the flag `"unrated"` when `rating` was missing.
- **FR-025**: `score_listing` MUST subtract `price_weight * price_per_ft` (`price_weight = 0.5`)
  from the shrunk rating when `price_per_ft` is known. When `price_per_ft` is `None`, it MUST
  instead subtract a fixed `0.5` and set the flag `"length unknown"` or `"price unknown"`
  (whichever of `length_ft` or `price` is the one missing).
- **FR-026**: `score_listing` MUST subtract `0.005` for every place the listing counts in its own
  SITE's own result order across every page read (`position`, a running index that continues after
  the previous page's own last position rather than resetting to 0 each page - fix batch B15,
  2026-09-11) when that value is known, MUST subtract `0.1` when the listing is sponsored, and MUST
  round the final score to 4 decimal places.
- **FR-027**: `tier(material)` MUST map `"plastic"`, `"rubber"`, and `"unknown"` to `"plastic"`;
  `"steel"`, `"aluminum"`, and `"metal"` to `"metal"`; and every other value to `"other"`.
- **FR-028**: `rank(listings, min_height_in=None)` MUST drop any listing whose `excluded_reason` is
  set. It MUST drop, and separately count, any listing whose `height_in` is known and below
  `min_height_in` when `min_height_in` is given; a listing whose `height_in` is `None` MUST be
  kept and flagged `"height unknown"`, never dropped by this rule alone. It MUST group every
  remaining listing by `tier(material)` and, within each tier, sort by descending `score`, then
  ascending `price_per_ft` (a listing with no `price_per_ft` sorts last), then ascending `title`.

**Folding**

- **FR-029**: `fold_duplicates(listings)` MUST key each listing by `canonical_url`, MUST keep the
  copy with the lower `(page, position)` pair, MUST union every page either copy names into the
  kept copy's own `found_on_pages`, and MUST prefer a non-sponsored copy over a sponsored one
  regardless of `(page, position)`.
- **FR-030**: `canonical_url(site, href)` MUST return `https://www.amazon.com/dp/<ASIN>` for an
  Amazon href (the ASIN from a `/dp/<10 chars>` segment, or the card's own `data-asin` attribute
  when the href carries none); `https://www.homedepot.com/p/<slug>/<id>` for a Home Depot href
  (the same path with its query string stripped); and the unmodified absolute href for any other
  site.

**Reporting**

- **FR-031**: The scan MUST write two files under `reports/product/`:
  `product-scan-<slug>-<UTC date>.md` and `product-scan-<slug>-<UTC date>.json`, where `<slug>` is
  the query lower-cased, every run of non-alphanumerics collapsed to one hyphen, trimmed of
  leading/trailing hyphens, and cut to 40 characters (fix batch A5/B9, 2026-09-11: the slug goes
  BEFORE the date, so two different queries scanned the same UTC day no longer overwrite each
  other) - both at file mode `0600`, chmod-bracketed before the write (for a pre-existing file) and
  after it (for a newly created one), matching `activity_scan.py`'s own bracket. A second run of
  the SAME query on the same UTC date MUST still overwrite both files for that date (documented,
  unchanged; the date itself is UTC, so an evening run in the US stamps the next day - fix batch
  B24).
- **FR-032**: The Markdown report MUST open with a header block (query, sites, pages, generation
  timestamp, and the five listing counts - read, unique after fold (BEFORE exclusion), excluded,
  dropped by height, and ranked, in that order - fix batch B8, 2026-09-11), followed, when a
  reference was given and readable, by a reference block (its origin, title, price, price per foot,
  height, length, material, stake count and material, rating, and score, plus the sentence stating
  its rank within its own tier), then one table per tier in the order plastic, metal, other (a
  literal `|` inside a title MUST be escaped as `\|` before it enters any table cell - fix batch B1,
  2026-09-11 - 28 of 78 rows broke in one live run before this fix), then `## Notes` (every `note:`
  line the scan printed), then `## Excluded` (a count for every distinct `excluded_reason` seen,
  each followed by the title, trimmed to 60 characters, of every listing dropped for it - fix batch
  B6), then `## Dropped by height` (the title, trimmed to 60 characters, of every listing dropped
  by `--min-height-in` - fix batch B6, empty as `- (none)` when nothing was dropped this way).
- **FR-033**: The JSON report MUST be a single object:
  `{"meta": {...}, "reference": {...} | null, "tiers": {"plastic": [...], "metal": [...],
  "other": [...]}, "excluded": [...]}`, where every listing entry is its `Listing` dataclass
  serialized as a flat dictionary and `excluded` lists every listing dropped for an
  `excluded_reason` (fix batch B6: a listing dropped only by `--min-height-in` is counted in
  `meta`'s own count but not itself listed here). `meta` is a FLAT object - `query`, `sites`,
  `pages`, `generated_at`, `read`, `unique`, `excluded`, `dropped_by_height`, `ranked`, `notes` -
  mirroring the Markdown header's own five counts by those same names (fix batch B3/B8: the
  shipped shape is flat, not the nested `counts`/`excluded_reasons` object an earlier draft of this
  document and its contract showed). `reference`, when present, carries two extra keys beyond its
  own `Listing` fields: `"rank"` (its 1-based position within its own tier's list) and `"tier"`
  (the tier name), plus `"tier_size"` (the tier's own count including the reference) - fix batch B3.
- **FR-034**: On success (a report written, or `--check` completed), the scan MUST print exactly
  one closing line for a scan run: `SCAN <markdown report path>`.

**Check mode**

- **FR-035**: `--check` MUST open page 1 of every site named in `--sites`, probe that site's own
  entry in `CHECK_SELECTORS` (Amazon: the card selector, then the card title/price/rating
  selectors EACH scoped as a descendant of the card selector; Home Depot: the pod selector, then
  the pod header/price/rating selectors each scoped as a descendant of the pod - fix batch B10,
  2026-09-11: a bare page-level selector, e.g. `h2 span` with no card ancestor, can resolve against
  something that is not actually inside a result card at all), print one `found`/`MISSING` line per
  selector, then one summary line, `CHECK <n> found, <m> missing`, write no report file, and exit 0
  regardless of the outcome. `--check` MUST NOT scroll any feed, MUST NOT read a reference, and
  MUST NOT visit any page beyond page 1 of each selected site.

**Read-only guarantee**

- **FR-036**: `--apply` MUST be hidden (`argparse.SUPPRESS`) and MUST always be refused with the
  exact message `"REFUSED: product_scan is read-only; there is no apply mode"`, exiting 1 before
  any configuration beyond argument parsing is resolved and before any network or browser call.
  There is no apply mode and none may be added.
- **FR-037**: The scan MUST never call `.fill(`, `.type(`, `.press(`, `.click(`, `.dblclick(`,
  `.select_option(`, `.check(`, or `.set_input_files(` on any page or locator object anywhere in
  `scripts/product_scan.py`.
- **FR-038**: The scan MUST require no secret and no vault item. `HANDOFF` MUST read
  `"n/a (read-only errand)"`.

**Exit codes**

- **FR-039**: The scan MUST exit 1 for any refusal named in this document (an empty query, an
  unknown site, a `--pages` value out of range, a malformed `--reference`, an unsupported
  `--reference-url` host, `--apply`, a `ConfigError`, or a `GateRefused` raised inside the
  session); MUST exit 2 for an `argparse` usage error or an unhandled exception during the browser
  session, printing the exception's own class name only (`ERROR: <ExceptionClassName> (rerun with
  HEADLESS_DEBUG=1 for the traceback)`, the full traceback going to stderr only when
  `HEADLESS_DEBUG=1`); and MUST exit 0 whenever a report is written or `--check` completes.
- **FR-040**: `scripts/product_scan.py` MUST insert the repository root onto `sys.path` at import
  time, the same bootstrap `activity_scan.py` already carries, so the script runs correctly from
  any working directory.

### Non-Functional Requirements

- **NFR-001**: The default `pytest -q` run MUST exercise every path this feature adds through a
  stubbed session and stubbed browser-reading functions - zero real browser launches, zero real
  network calls.
- **NFR-002**: Every fixture and example in this feature's own document set and test suite MUST
  use only public retail titles, prices, and ratings already observed in the 2026-09-11 recon, or
  a synthetic equivalent in the same shape - no account detail, no payment detail, and no data
  that is not already public on the retailer's own page.
- **NFR-003**: The scan MUST NOT read or write any secret, vault item, or profile registry path.
- **NFR-004**: A subprocess test MUST run `scripts/product_scan.py --help` from a working
  directory outside the repository and MUST exit 0, proving the `sys.path` bootstrap (FR-040)
  works standalone.

### Key Entities

- **Listing**: one ranked result - site, title, url (the site's own listing link), origin
  (`"search"`, `"reference-url"`, or `"reference-hand"`), price, rating, review count, its own
  0-based position and page number on the site it was read from, a sponsored flag, its parsed
  height, length, material, stake count and material, a no-dig flag, an exclusion reason, its
  derived price per foot, shrunk rating, score, a list of flags (`"unrated"`, `"length unknown"`,
  `"price unknown"`, `"height unknown"`), and the list of pages it was found on after folding.
- **SITES**: the two supported search-site ids, `("amazon", "homedepot")`.
- **REFERENCE_HOSTS**: the map from an accepted `--reference-url` host to the site id that reads
  it (`www.amazon.com`/`amazon.com` to `"amazon"`, `www.walmart.com`/`walmart.com` to
  `"walmart"`).
- **WALL_TITLES**: the three observed bot-wall or error-wall page titles,
  `("Robot or human?", "Access Denied", "Error Page")`, checked by `wall_reason` alongside a
  `/blocked?` URL.
- **Tier**: one of `"plastic"`, `"metal"`, `"other"` - the grouping `tier(material)` assigns a
  scored listing to, and the order the Markdown report's own tables appear in.
- **Product-scan report**: the two files this feature writes,
  `reports/product/product-scan-<slug>-<date>.md` and `.json` - see `contracts/scan-and-report.md`
  for their exact shape.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The full `pytest -q` suite, including this feature's own tests, passes with zero
  real browser launches and zero real network calls.
- **SC-002**: A unit test proves `parse_attributes` against every real recon title this feature's
  own brief names (the Bluepro, MIXC, EasyFlex, Bonviee, Vigoro, BSHAPPLUS, GOTGELIF, and the
  remaining titles listed in `research.md`'s evidence section), correctly extracting height,
  length, material, stake count and material, the no-dig flag, and any exclusion reason.
- **SC-003**: A unit test proves `parse_price` handles every observed price shape (`$43.99`,
  Home Depot's split spans `$\n41\n.\n97`, `Now $22.59`, a bare `31.58`, and `$1,234.00`), and
  that `price_per_ft` rounds to 3 decimal places.
- **SC-004**: A unit test proves `score_listing`'s own scoring monotonicity: a better-rated
  listing outranks a worse-rated one at an equal price per foot; a cheaper listing outranks a
  costlier one at an equal rating; and a 5.0 rating with 3 reviews does not outrank a 4.6 rating
  with 600.
- **SC-005**: A unit test proves `fold_duplicates` keys by `canonical_url`, keeps the lower
  `(page, position)` copy, unions `found_on_pages`, and prefers a non-sponsored copy over a
  sponsored one.
- **SC-006**: A unit test proves `tier` assigns every observed material correctly and that `rank`
  sorts each tier by descending score, then ascending price per foot, then title.
- **SC-007**: A unit test PINS the exact "would rank #k of n" sentence for a fixture whose scores
  are known ahead of time (for example, `"Your pick would rank #3 of 3 in the plastic tier."`), and
  separately proves both boundary cases - a reference that ranks #1 of n (beats every existing
  listing) and one that ranks #n+1 of n (beaten by all of them) - fix batch B17, 2026-09-11.
  `## Excluded` counting each `excluded_reason` correctly is proven by SC-006's own `rank` test.
- **SC-008**: A unit test proves `parse_reference_literal` parses `"Title | 31.58 | 40"` (with and
  without a leading `$` and a trailing `ft`/`'`, and with an optional 4th/5th rating/review-count
  part - fix batch A4) and raises on every malformed shape this feature's own brief names,
  including a zero/negative price or length, an out-of-range rating, and a negative review count
  (fix batch B7).
- **SC-009**: A unit test proves the CLI never constructs a browser session when `--apply` is
  given, `--query` is empty, `--sites` names an unknown site, `--reference` is malformed, or
  `--reference-url` names an unsupported host.
- **SC-010**: A unit test proves `--check` reports exactly the selectors in `CHECK_SELECTORS` for
  each selected site, prints the correct found/missing summary line, and writes no report file.
- **SC-011**: A unit test proves a wall on any search page never crashes the scan - it prints a
  note and the scan continues - and that a query returning zero listings on every selected site
  still writes a report and exits 0.
- **SC-012**: A unit test proves `--min-height-in` drops a listing below the threshold (counted
  under "dropped by height") and keeps an unknown-height listing, flagged, in its tier.
- **SC-013**: The existing structural test (`tests/test_no_direct_typing.py`) continues to pass
  against `scripts/product_scan.py` - no direct fill, type, click, or similar call exists in that
  file.
- **SC-014**: Recon against the live Amazon search, Amazon product, and Home Depot search pages
  under headless Chrome (2026-09-11) confirmed every selector this feature depends on for those
  two sites resolves; the same recon confirmed Walmart, Lowe's, Google Shopping, and Menards
  refuse headless Chrome outright, and that Target's markup lacks the expected card attributes.

## Assumptions

- Amazon's and Home Depot's own search and product markup (the selectors recon 2026-09-11
  recorded) remain as observed. `--check` exists precisely so a later drift is caught read-only,
  before a real scan is trusted.
- Price per foot is a reasonable value proxy for a sold-by-length product such as edging, fencing,
  or trim - it is not a general rule for every product category this errand might later be pointed
  at.
- The Director runs this scan by hand, for one product query at a time; nothing in this feature
  schedules or repeats a scan automatically.
- English-language listings are assumed (dollar prices, English unit words, English category and
  material words).
- A Walmart product page's own markup (recorded for the headed, `--show` path) is read from the
  Director's own in-app browser observation, not verified live under headless Playwright, since
  every headless attempt at that page meets the bot wall.

## Out of Scope

- Reading Walmart, Lowe's, Google Shopping, or Menards as a search site - Walmart is read only as
  a named reference, and the other three are never opened at all.
- Reading Target this delivery - its markup lacks the expected card attributes; a later feature
  may revisit it.
- Any write action on any site - there is no `--apply` mode and none may be added.
- Purchasing, adding to a cart, or otherwise confirming availability at any retailer.
- Comparing more than one product query in a single run.
- A general-purpose shopping or price-tracking tool - this errand answers one specific product's
  value question, not an open-ended marketplace search.
- Caching or deduplicating results across separate scan runs.
