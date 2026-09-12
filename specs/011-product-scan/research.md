# Research: Product Scan

**Feature**: 011-product-scan | **Date**: 2026-09-11

This document records the recon a session ran on 2026-09-11, against Amazon, Home Depot, Walmart,
Lowe's, Google Shopping, Menards, and Target, under headless Chrome, using `scripts/probe.py` and
short read-only Playwright scripts against the live query "no dig landscape edging" - the same
category as the Director's own lawn-edging question, chosen because it generalizes cleanly - and
the ten design decisions (D1-D10) that follow from it.

## Evidence

### Amazon renders fully and needs no scroll; Home Depot renders once, then walls itself

Amazon's own search page (`https://www.amazon.com/s?k=<query>`) rendered 48 cards on the first
load of both page 1 and page 2, with no scroll needed. Every card sits inside
`div[data-component-type="s-search-result"]` and carries a `data-asin` attribute. A card's title
reads from the first `h2 span` (for example, "Bluepro Landscape Edging, 2 Inch 100 ft Garden
Border Edging | 150 Steel Stakes, Upgraded Reinforced Design, Durable Plastic Landscaping Border
for Flower Beds, Lawn & Yard"); its own link, `a.a-link-normal.s-no-outline`, carries a
relative href such as `/Bluepro-Landscape-Edging-Upgraded-Reinforced/dp/B0G4H2C41Y/ref=sr_1_1?...`.
The first of two `.a-price .a-offscreen` spans carries the current price (`$43.99`; the second is
the list price). The rating reads from `i[class*="a-icon-star"] .a-icon-alt` ("4.5 out of 5
stars"); the review count reads from the `aria-label` of `[aria-label$="ratings"]` ("158 ratings"),
never its own abbreviated text ("(158)" is fine at this size, but "(5.1K)" for the same card's
5,118-review count is not). A sponsored marker (`.puis-sponsored-label-text`,
`span.puis-label-popover-default`) matched zero of 48 cards on this profile. An Amazon product
page (`/dp/B01MG4ARN7`) exposes the same facts for a single listing: `#productTitle`, the first
`.a-offscreen` inside `#corePrice_feature_div`, `#acrPopover`'s own `title` attribute ("4.5 out of
5 stars"), and `#acrCustomerReviewText` ("(5,118)").

Home Depot's own search page (`https://www.homedepot.com/s/<query>`) rendered 24
`[data-testid="product-pod"]` pods on its first load this session - 12 unique products, each pod
duplicated once in the DOM (the same `href`, the same text, twice). A pod's header,
`[data-testid="product-header"]`, carries the brand glued directly to the product name with a
zero-width space (U+200B) in between: `"Vigoro60 ft.​ No-​Dig Plastic Landscape Edging
Kit"`. Its link, the first `a[href*="/p/"]`, reads
`/p/Vigoro-60-ft-No-Dig-Plastic-Landscape-Edging-Kit-3001-60HD-3/301459392`. Its price,
`[data-testid="price-simple"]`, renders as three separate text nodes joined with no separator -
`"$\n41\n.\n97"` - which must be stripped and rejoined before it parses as a number. Its rating,
`[data-testid*="rating"]`, reads `"(4.5 /\xa04091)"` (rating, then a non-breaking space, then the
review count). Every later visit to the same search URL within about ten minutes, including a
fresh navigation and a `?Nao=24` page-2 request, returned the title `Error Page`, the body text
"Oops!! Something went wrong. Please refresh page," and zero pods, even after a 20-second selector
wait and a scroll. This is a wall, not a markup change: the selectors above are correct; the page
itself refused to render a second time.

Walmart (`www.walmart.com/ip/<id>` and `/search?q=`) redirected to `/blocked?url=...` with the
title "Robot or human?" on every headless attempt. Lowe's (`www.lowes.com/search?searchTerm=`)
returned the title "Access Denied." Google Shopping
(`www.google.com/search?tbm=shop`) redirected to `/sorry/index`, Google's own captcha wall.
Menards (`www.menards.com/main/search.html`) rendered an empty title and a blank page. Target
(`www.target.com/s?searchTerm=`) rendered a real title and real body text - "259 results for 'no
dig landscape edging'" appeared in the page's own text - but none of the expected
`[data-test*="ProductCard"]`-style attributes existed anywhere in the DOM; the listing data is
present as text but not addressable by any selector this recon could find, so it is deferred
rather than scraped by an unreliable text-only parse.

A Walmart product page's own selectors (`h1#main-title`, `span[itemprop="price"]`,
`[data-testid="reviews-and-ratings"] span.f7`, and a `(\d[\d,]*)\s+ratings` regex over the body
text for the review count) were read in the Director's own in-app browser, not under headless
Playwright, since every headless attempt at a Walmart page meets the bot wall above; they are
recorded for the `--show` (headed) reference path, and never proven under headless automation.

## D1. Amazon is the primary, default search site

**Decision**: `--sites` defaults to `"amazon"`. Amazon is read on every scan unless the Director
narrows `--sites` to exclude it.

**Rationale**: it is the only site of the seven recon checked that rendered completely, on both a
first and a later visit, with zero scroll required and zero sponsored labels to reason about on
this profile. Every field the scoring and reporting logic needs (a title, a price, a rating, a
review count) resolved on every one of 48 cards, twice.

**Alternatives considered**:

- Home Depot as the default instead of, or alongside, Amazon: rejected. Home Depot's own
  repeat-visit wall (the `Error Page` behavior below, D2) makes it unsuitable as a default a
  Director might run several times in one session.

## D2. Home Depot is opt-in, best-effort, after the `Error Page` behavior

**Decision**: Home Depot is read only when `--sites` names it explicitly
(`--sites amazon,homedepot`). A wall on its own first page skips its remaining pages for that run,
with a note, and never stops Amazon's own results.

**Rationale**: the first Home Depot visit this session rendered correctly; every later visit
within about ten minutes returned the `Error Page` wall. A site that walls itself off on repeat
visits cannot be a default a Director runs more than once without risking a confusing, empty
second-source result; making it opt-in and fail-soft keeps the errand honest about what it
actually delivered on any given run, while still letting the Director widen the field when the
site happens to cooperate.

**Alternatives considered**:

- Retrying Home Depot automatically after a wait: rejected. The wall persisted across a fresh
  navigation and a 20-second selector wait within the same recon session; nothing this errand
  could do differently in a few seconds would out-wait it, and adding a retry loop risks turning a
  quick, read-only scan into a slow one for no proven benefit.
- Treating the `Error Page` wall as a hard failure (exit non-zero): rejected. It is exactly the
  kind of site-side flake this repository's fail-soft precedent (`activity_scan.py`'s own
  per-query exception handling) already has a pattern for - note it, skip it, keep going.

## D3. Walmart is a reference-only site, behind a bot wall

**Decision**: Walmart is never a search site. A Walmart URL is read only through
`--reference-url`, after every search page has already been read. `--show` is the Director's own
escape hatch to pass the wall by hand; `--reference` is the fully headless fallback.

**Rationale**: Walmart is the retailer that carries the actual listing the Director's own question
is about, but every headless attempt at a Walmart page (a product page or a search page) meets the
same "Robot or human?" wall, with a redirect to `/blocked?url=...`. Reading it as a search site
would mean every scan wastes a request on a page that never renders; reading it as a
reference-only, best-effort target - one page, only when named, only after the search pages, with
a documented headed escape hatch and a hand-typed fallback - matches what the site will actually
allow while still letting the Director's own chosen listing enter the comparison.

**Alternatives considered**:

- Automating a bot-wall bypass (a stealth plugin, a residential proxy, a CAPTCHA solver): rejected
  outright. This repository's own hard rules never treat a site's own bot defense as an obstacle
  to engineer around; a wall observed live is recorded and respected, the same posture `PATTERNS.md`
  already documents for Progressive's own quote-start block.
- Dropping Walmart entirely, with no reference path at all: rejected. It is the one site the
  Director's own question is actually about; a scan that could not even state where the listing he
  was sent ranks would not answer the question this feature exists to answer.

## D4. Lowe's, Google Shopping, and Menards are traps; Target is deferred

**Decision**: Lowe's, Google Shopping, and Menards are never opened by this errand, not even as a
reference host. Target is not read this delivery.

**Rationale**: Lowe's returned "Access Denied," Google Shopping redirected to a captcha wall, and
Menards rendered a blank page with an empty title - three more bot or access walls, none offering
even the narrow reference-page opening Walmart's own bot wall still allows (D3). Target's own page
rendered real content, but no selector this recon could find addresses a single product card; a
text-only parse of a rendered page with no addressable structure would be a fragile, unmaintainable
special case for one more site, not a second real source.

**Alternatives considered**:

- A text-position-based parse of Target's own rendered body text (splitting on price-like
  substrings): rejected. It would be the first selector-free parser in this errand's own design,
  breaking the pattern of ARIA-role and attribute-based reads this repository already prefers
  (`PATTERNS.md`), for one site whose real card markup this recon simply could not locate in the
  time available.
- Treating Target as a reference-only host, the way Walmart is treated: rejected. Walmart's own
  reference reading works because its selectors are known (from the Director's own in-app browser
  observation); Target has no known selectors for either a search read or a single-listing read.

## D5. Target is deferred to a later feature, not attempted this delivery

**Decision**: Target is recorded as a known gap, not a partial implementation. No selector
constant, no read function, and no test fixture exists for it in this delivery.

**Rationale**: recon found real content but no addressable card structure within the time this
recon session had. Shipping a guessed, unverified selector risks a silently broken read that looks
like a working feature; recording the gap honestly, with the option to revisit it once its markup
is understood, is the safer choice for a read-only errand whose whole value is trustworthy output.

**Alternatives considered**:

- Shipping a best-guess selector anyway, flagged experimental: rejected. This errand has no
  precedent for an unverified selector; `--check` exists specifically so every shipped selector is
  one recon has actually seen resolve.

## D6. The first-variant length assumption

**Decision**: when a title names more than one length (a range such as "40/100ft," or an explicit
multi-roll figure such as "2 x 50FT" following an earlier "100FT"), `parse_attributes` keeps the
first standalone foot figure the title names.

**Rationale**: a retail listing's own displayed price is for one specific variant - almost always
the first, or default, one a title names. "GOTGELIF Landscape Edging 2inch Tall, 40/100ft No-Dig
... with 60/120 Spikes Plastic" prices the 40-foot variant by default on most retail search
results; "Bonviee 100FT Landscape Edging Kit with 150 Stainless Steel Stakes | 2 x 50FT 1.5"
Flexible Rolls" is priced as the full 100-foot kit, and the "first standalone figure" rule
correctly keeps 100, not 50, because 100 appears earlier in the title than 2 x 50. This is a
recorded assumption, not a certainty: a listing whose displayed price actually belongs to a
non-default variant would be mispriced by this rule, and no selector recon found lets the scan
confirm which variant a search card's own displayed price actually reflects, short of opening
every one of them as a product page.

**Alternatives considered**:

- Reading every candidate length and reporting a price-per-foot range instead of one figure:
  rejected for this delivery. It would meaningfully complicate the score, the tier tables, and the
  report's own columns for a refinement the Director did not ask for; the simpler first-variant
  reading is stated as an assumption instead, so a reader of the report knows exactly what it
  means.
- Opening every card's own product page to confirm the priced variant: rejected. It would turn a
  two-page, dozens-of-cards-per-page scan into dozens of extra page visits, working against the
  errand's own purpose of a fast, read-only comparison.

**Fix batch addendum (2026-09-11): per-piece packs are a documented limit, not a fix.** A title
naming a pack or piece count ("5 Piece Steel Home Kit ... 4\" by 8'", "6 Pack 40\" L x 6\" H")
states a PER-PIECE length, not the whole roll's own length - `$/ft` for such a listing is
therefore wrong or missing by design, never corrected. `is_pack(title)` checks the
stake-stripped title against `\b\d+\s*(?:pack|pcs|piece|pc)s?\b` (the digit-first order the two
examples above use) OR the reversed order a real recon title also uses, `(Pack 6)` - the real
TISHO title (`TISHO 3" x 48" ... (Pack 6) ... Pieces are 4ft in Length`) names its pack count
word-then-digit, so the regex was widened beyond the letter of the digit-first pattern to cover
it, a deliberate choice recorded here rather than silently narrowing the fixture to fit the
original pattern. The check runs on the STAKE-STRIPPED text specifically so a stake count itself
phrased as "Pcs" ("120 Pcs Metal Spikes") is never mistaken for a physical multi-piece pack.
When `is_pack` is true and a length was parsed, the `Listing` carries the flag
`"pack: per-piece length"` and the report's own Length cell reads `"<length> ft (per piece)"`.

**Fix batch addendum (2026-09-11): a title-stated grand total overrides every other length
candidate.** `SnugNiture 2 Rolls ... 4" x 50' ... (Total 100 Ft)` prices the FULL 100-foot total,
not the 50-foot half a naive first-candidate read would pick; `Garden Border Edging Roll [4 Inch
High] 66FT Total (2 Rolls of 33FT)` likewise states its own total explicitly. `_parse_length`
checks `"<N>ft/feet/foot/' total"` and `"total <N>ft/feet/foot/'"` (case-insensitive, full-width
parentheses normalized) BEFORE the ordinary range/first-candidate logic, and returns that value
outright when found. A per-piece length stated as "Pieces are 4ft in Length" (the TISHO title
above) does NOT match either total pattern - it is a per-piece figure, not a grand total, and is
correctly left to the pack-flag rule above instead.

## D7. Float prices, not `Decimal` - a deliberate contrast with `compare.py`

**Decision**: `parse_price` and `price_per_ft` use ordinary Python `float`, never `Decimal`.

**Rationale**: `headless/compare.py` (spec 005-insurance-quote-comparison) requires `Decimal`
exclusively, because it reconciles a real insurance quote against a real current policy, where a
one-cent rounding drift could misstate a coverage comparison the Director might act on
financially, and its own byte-identical-output invariant depends on `Decimal`'s exact arithmetic.
This feature carries no such requirement: every price it reads is a public retail listing price,
compared only to rank options against each other, never reconciled against a second document or
turned into a byte-identical artifact. A `float`'s ordinary rounding error (far smaller than a
cent at these magnitudes) changes nothing about which listing ranks above another; `Decimal`'s own
ceremony (explicit context, explicit quantization) buys nothing here that a rounded `float` does
not already give more simply.

**Alternatives considered**:

- `Decimal` everywhere, for consistency with `compare.py`: rejected. Consistency for its own sake,
  applied to a module with a materially different correctness requirement, would add ceremony
  without adding safety - the module docstring states this contrast explicitly so a later reader
  does not mistake the difference for an oversight.

## D8. No LLM anywhere - pure regex parsing, deterministic and testable

**Decision**: `headless/products.py` parses every title, price, and rating with hand-written
regular expressions and string rules. No LLM call, local or cloud, appears anywhere in this
feature.

**Rationale**: a title's own shape (a height, a length, a material word, a stake count) is regular
enough, and the recon evidence concrete enough, that a deterministic parser can be written and
exhaustively unit-tested against every title this recon actually observed. A regex-based parser is
testable byte-for-byte and never drifts between runs; an LLM-based parser would add cost, latency,
and non-determinism to a read-only errand whose whole value is a fast, repeatable answer, and this
repository's own hard rule that "nothing an LLM derives is ever typed" (`CLAUDE.md`) applies in
spirit here too - nothing an LLM derives should decide what a listing's own attributes are, when a
deterministic parse already does the job.

**Alternatives considered**:

- An LLM fallback for a title the regex parser cannot fully parse: rejected for this delivery. The
  recon evidence covers a wide enough variety of real titles that the regex rules, and their tests,
  already handle the observed shapes; a listing the parser cannot fully attribute simply carries
  `None` fields and an "unknown" tier, which is an honest, visible outcome rather than a guessed
  one.

## D9. Read-only forever - no apply mode, ever

**Decision**: `product_scan.py` has no `--apply` mode. The flag exists, hidden, only to be refused
with a fixed message. No purchase, cart addition, or availability check of any kind is in scope,
now or later.

**Rationale**: this errand's whole purpose is to inform a decision the Director makes himself; it
never needs to act on a retail site on his behalf. Matching `activity_scan.py`'s own precedent
(the first errand in this repository built with no apply mode at all, because it has no form to
fill), this feature has no terminal action, no form, and no handoff - there is nothing for an
apply mode to do.

**Alternatives considered**:

- Adding to a cart as a future `--apply` step, deferred rather than ruled out: rejected outright,
  not merely deferred. This repository's terminal-actions rule already reserves every purchase
  decision for the Director, in his own browser; automating a cart addition would blur that line
  for a feature whose only job is comparison.

## D10. Reports hold public data, but `reports/` stays gitignored

**Decision**: `reports/product/` is a new sibling to `reports/activity/`, `reports/captures/`, and
`reports/policy/`, resolved the same way (`reports_dir_for(config)`), and inherits the same
gitignored classification.

**Rationale**: every fact a product-scan report carries - a title, a price, a rating - is already
public on the retailer's own page. But the report also echoes the Director's own query and his own
chosen reference listing, which is his own shopping context even when every underlying fact is
public; consistency with every other `reports/` sub-folder is worth more than the narrow argument
that the listing rows alone are public data.

**Alternatives considered**:

- A new, non-gitignored top-level directory for product-scan reports, since the listing data
  itself is public: rejected, for the same reason `activity_scan.py`'s own D4 rejected this for
  venue reports - the query and the reference are still the Director's own planning detail.

## Fix batch addenda (2026-09-11, post-live-run and post-Opus-verification)

These decisions were made against real listing titles from three live scans (`no dig landscape
edging`, `4 inch tall landscape edging`, `steel landscape edging`), not the original recon alone -
see `MEMORY.md`'s own "Errands run" rows for the three runs' counts.

**D-stone-look: bare "stone" and bare "paver" are dropped from the material rule.** Ten plain
plastic rolls in the first live run and seventeen in the second tiered as "other/stone-look" only
because their title lists "Paver" among its uses (`... Plastic Mulch Border Flexible for Garden
Flower Beds Lawn Yard Pathway Paver (Black)`), never because the product is actually a decorative
stone-look item. The rule now requires an actual decorative-stone claim - `faux stone`,
`stone effect`, `stone look`, `stone like`, `stone texture`, `polyrock`, `bricks`, `cobblestone`,
or `concrete` - and every listing that used to be stone-look only because of "paver" now
classifies by whatever material word is actually left in its own title (most say "Plastic" or
"PE"; a few have no other material word and land on "unknown," still tiered as "plastic" per
`tier()`'s own mapping). Real titles that keep classifying as stone-look under the new rule:
Beuta's three Polyrock listings, a "Faux Stone"/"Stone-Look" title, a "Stone Effect" title, a
"Stone Texture" title, and a "24 Bricks" title - each verified individually in
`tests/test_products.py`.

**D-stakes: an uncounted stake phrase is stripped exactly like a counted one, and a decimal
fraction is never read as a count.** `80FT Landscape Edging Border, 4 Inch Tall Plastic Garden
Edging | Heavy Duty 80 Foot Lawn Edging Border with Metal Stakes for Large Yard...` tiered as
METAL, not plastic, because "with Metal Stakes" carries no count, so the earlier span-based strip
(which only removed the FIRST COUNTED phrase) left "Metal Stakes" sitting in the text for the
material rule to find. The fix removes EVERY stake/spike/nail/staple/anchor/peg/pin phrase from
the working text before material, height, and length parsing - counted or not - while
`stake_count`/`stake_material` still come only from the first COUNTED phrase (an uncounted phrase
therefore yields `None` for both, a deliberate, simpler choice recorded here rather than inventing
a new "material without a count" concept). Separately, `7.8In Height Stakes,20Pcs` was parsed as
stake count 8 - lifted off the ".8" of the decimal fraction "7.8," because the preceding-count
regex had no guard against starting mid-decimal. A `(?<![\d.])` lookbehind now refuses to start a
count on a digit immediately preceded by another digit or a decimal point; for this exact title,
neither the "7.8" fraction nor the trailing ",20Pcs" (which follows the noun, not precedes it) is
read as a count, so `stake_count` is `None` - the trailing count is a plausible alternative
reading this fix batch did not implement, since the "count precedes the noun" rule is already
established and extending it to "or follows" would be a second, separately-tested code path for a
single observed title.

**D-quote: the foot mark must be a LONE single quote, and a total marker outranks it.**
`4'' X 100' Landscape Edging Border Kit` parsed length 4 ft (from the first `''`, misread as a
foot mark) instead of 100; `Metal Landscape Edging Border 6 Packs 42'' L x 4.5'' H` parsed length
42 (the double-prime height marker, misread as feet) instead of the title's own stated
`(21ft Total)`. A double prime (`''`) and a literal `"` are inch marks, never feet; the foot
candidate now requires a `'` neither preceded nor followed by another `'` or a `"`. Once a title
also states an explicit grand total (`"21ft Total"`, `"(Total 100 Ft)"`), that value wins outright
over any other candidate the fixed quote rule would otherwise pick.

**D-height-window: a context window must stop at the next dimension's own digit, and must never
end mid-word.** An `L x W x H` triple (`48" L x 4" W x 2.25" H`) let an EARLIER number's own
context window reach across a LATER number's own `H` marker, because the window was a bare
fixed-length character slice; height for that title read as 4 (the "W" figure) instead of 2.25
(the true "H" figure). Separately, the same fixed-length window manufactured a false `\bL\b` match
by cutting off exactly after the "L" of "Landscape" (`Gardzen 1.5" x100' Landscape Edging`),
dropping a valid height of 1.5 to `None`. Both windows (the twelve-character tall-context one and
the eight-character length-exclusion one) now stop at the first digit encountered - never letting
a later dimension's own number fall inside an earlier candidate's own window - and, when no digit
intervenes, extend to the end of whatever word the fixed length would otherwise have split.

**D-pipe-escape: a literal `|` inside a title breaks a Markdown table row.** 28 of 78 rows in one
live run rendered wrong because real Amazon titles use `|` as their own internal separator (the
real Bonviee title carries three: `Bonviee 100FT Landscape Edging Kit with 150 Stainless Steel
Stakes | 2 x 50FT 1.5" Flexible Rolls | Easy Install | Professional Garden Edging Borders...`).
Every title is now escaped (`\|`) before it enters a table cell.

**D-position: position is a running index per site across every page, not reset per page.** An
`80FT Landscape Edging Border, ...` on page 2 previously scored as if it were the FIRST result on
that page (`position=0`), understating its own list-position penalty; page 2's first card now
continues after page 1's own last position for that site.

**D-audit: excluded and height-dropped listings are returned, not just counted.** `rank()` now
returns a `RankResult` (tiers, excluded, dropped_by_height) instead of a bare tier dictionary, and
the JSON report gains a top-level `"excluded"` array plus `"rank"`/`"tier"`/`"tier_size"` on the
reference object, so a fence-category listing or a below-height one is auditable by title, not
only visible as a number in the header block.

**D-household-redaction (fix batch B20, orchestrator decision, 2026-09-11): this repository is
PUBLIC.** Every household-role reference to the person who chose the listing - in this document
set, in `PATTERNS.md`, `Project_Structure.md`, `MEMORY.md`, and the two code docstrings - is
replaced with "a listing the Director was sent" (or, where the phrasing needs a possessive, "his
household"),
consistent with `activity_scan.py`'s own household-role redaction precedent (`spec
009-activity-scan`'s own checklist). The bare item id `18656266943` is kept (it identifies a
public retail listing, not a person), and no affiliate token appears anywhere in this delivery.

**D-fence-precision (post-batch live re-run, orchestrator decision, 2026-09-11).** The fix batch
made every exclusion auditable by title, and the first audit of the three corrected live runs
showed the price of a bare "fence" substring: 17 of the 39 excluded titles were genuine edging -
a brand name ("AggFencer"), a use list ("for Lawn, Flower Bed, Garden Fence"), a "Mini Fence
Border" marketing phrase on 4-inch plastic rolls, corrugated-steel edging, and an EasyFlex
decorative kit described as a "Wood-Look Fence Garden Border". The rule now requires a real fence
claim: "animal barrier", "fencing", "fence panels" (or "N panels ... fence"), or "trellis". Every
one of the 11 real animal-barrier and decorative-fence titles in the live runs carries at least one
of these; none of the 17 wrongly excluded edging titles does. FR-022 is reworded to match.

**D-total-marker-pack (same re-run).** A "6 Packs ... (21ft Total)" listing parsed its stated total
correctly (fix batch B14) but still carried the per-piece caveat from A6. `pack_flag_applies`
(`is_pack` AND NOT `has_total_marker`) is now the one rule both listing builders use, so a stated
total is never labeled per-piece.
