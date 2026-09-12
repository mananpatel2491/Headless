# Data Model: Product Scan

**Feature**: 011-product-scan | **Date**: 2026-09-11

No database, no vault item, no profile field. The two persisted artifacts are
`reports/product/product-scan-<slug>-<UTC date>.md` and `.json` (fix batch A5/B9, 2026-09-11: the
query's own slug precedes the date) - a run of the SAME query the same UTC date replaces that pair;
a different query, or a run on a new UTC date, adds a new pair rather than overwriting an older
one. Everything else below is in-memory for the lifetime of one `scripts/product_scan.py`
invocation, or is the description of a pure function's own contract.

## The pipeline state flow

```text
sites x pages -> cards -> parse -> fold -> score -> rank (tiers) -> reference -> render
```

| State | Produced by | What it holds |
| :--- | :--- | :--- |
| `sites x pages` | `--sites` (default `("amazon",)`) crossed with page numbers 1 through `--pages` | Every `(site, page_number)` pair the scan reads |
| `cards` | `read_amazon_search(page, page_number)` or `read_homedepot_search(page, page_number)`, once per `(site, page_number)` pair | Every result card or pod on that page, as a `Listing`, each with its own `site`, `page`, and 0-based `position` already set, `origin="search"`, unparsed and unscored |
| `parse` | `headless.products.parse_attributes`, applied to each `Listing.title` | The same listings, with `height_in`, `length_ft`, `material`, `stake_count`, `stake_material`, `no_dig`, and `excluded_reason` filled in |
| `fold` | `headless.products.fold_duplicates` | The same listings, collapsed by `canonical_url`, the copy with the lower `(page, position)` kept (a non-sponsored copy always beating a sponsored one regardless of that pair), `found_on_pages` unioned |
| `score` | `headless.products.score_listing`, applied to each folded listing | Each listing's own `shrunk_rating`, `score`, and `flags` (`"unrated"`, `"length unknown"`, `"price unknown"`) |
| `rank` (tiers) | `headless.products.rank(listings, min_height_in)` -> a `RankResult` (fix batch B6, 2026-09-11) | `RankResult.tiers`: listings whose `excluded_reason` is set are dropped into `RankResult.excluded` FIRST; then, only when `min_height_in` is given, a listing below it is dropped into `RankResult.dropped_by_height` (a listing already excluded is never also counted here, even if it would also fail the height check); the remainder is grouped by `tier(material)` and sorted within each tier |
| `reference` | `read_amazon_product(page)` / `read_walmart_product(page)`, or `parse_reference_literal(text)` | One `Listing` with `origin="reference-url"` or `"reference-hand"`, parsed and scored exactly like a search-sourced listing, then located inside its own tier's ranked list for its rank sentence |
| `render` | `render_markdown` / `render_json` | The two report files (below) |

## Listing

```text
Listing(
    site: str, title: str, url: str, origin: str,   # "search" | "reference-url" | "reference-hand"
    price: float | None = None,
    rating: float | None = None, reviews: int | None = None,
    position: int | None = None, page: int | None = None,
    sponsored: bool = False,
    height_in: float | None = None, length_ft: float | None = None,
    material: str = "unknown",
    stake_count: int | None = None, stake_material: str | None = None,
    no_dig: bool = False,
    excluded_reason: str | None = None,
    price_per_ft: float | None = None,
    shrunk_rating: float | None = None,
    score: float = 0.0,
    flags: list[str] = [],
    found_on_pages: list[int] = [],
)
```

| Field | Set by | Notes |
| :--- | :--- | :--- |
| `site`, `title`, `url` | The search-page or reference-page parse | `url` is the listing's own product-page link before folding; after folding, `canonical_url(site, url)` is the fold key, not `url` itself |
| `origin` | The caller | `"search"` for every card or pod read from a search page; `"reference-url"` for a successful `--reference-url` read; `"reference-hand"` for `--reference`'s own literal |
| `price` | `parse_price` on the card's or product page's own price text | `None` when no digits are present |
| `rating`, `reviews` | `parse_rating`/`parse_count`, or `parse_rating_and_count` for a combined label | Both `None` for an unrated listing |
| `position`, `page` | The search-page parse | `position` is 0-based and a RUNNING index per site across every page read (fix batch B15, 2026-09-11: page 2's first card continues after page 1's own last position, never resets to 0); `page` is the 1-based page number requested. Both `None` for a reference listing |
| `sponsored` | The card's own sponsored marker | Decides which copy `fold_duplicates` keeps when two copies tie on `(page, position)` |
| `height_in`, `length_ft`, `material`, `stake_count`, `stake_material`, `no_dig`, `excluded_reason` | `parse_attributes(title)` | See spec.md FR-016 through FR-022 for the parsing order and rules; `excluded_reason` is set on the record before a `rank`-excluded listing is dropped from the ranked tables |
| `price_per_ft` | `price_per_ft(price, length_ft)` | `None` when either input is `None`; rounded to 3 decimal places otherwise |
| `shrunk_rating`, `score` | `score_listing` | `shrunk_rating` is the Bayesian-shrunk rating alone; `score` is the shrunk rating adjusted by the price, position, and sponsored terms, rounded to 4 decimal places |
| `flags` | `score_listing`, `rank`, and the caller's own pack check (`headless.products.is_pack`, fix batch A6) | `"unrated"` (no rating), `"length unknown"` / `"price unknown"` (no `price_per_ft`), `"height unknown"` (no `height_in`, kept rather than dropped by `--min-height-in`), `"pack: per-piece length"` (the title names a pack/piece count AND a length was parsed - such a listing's own `$/ft` prices one piece, not the whole roll, by design) |
| `found_on_pages` | `fold_duplicates` | Every page number, across every duplicate copy, that surfaced this listing; a reference listing's own value is always empty |

## Ranking output (`rank`)

`rank(listings, min_height_in=None) -> RankResult` (fix batch B6, 2026-09-11 - a dataclass, not a
bare dict, so the excluded and height-dropped listings stay auditable):

```text
RankResult(
    tiers: dict[str, list[Listing]],       # "plastic" | "metal" | "other"
    excluded: list[Listing],                # excluded_reason set - checked FIRST
    dropped_by_height: list[Listing],       # below min_height_in - checked SECOND,
)                                            # never both for the same listing
```

`tiers` groups every listing that survived both checks by `tier(material)`, each list sorted by
descending `score`, then ascending `price_per_ft` (a listing with no `price_per_ft` sorts last
within its tier), then ascending `title`. A listing whose `excluded_reason` is set is dropped into
`excluded`, checked FIRST, before the height rule ever runs (fix batch B8: a short fence is always
"excluded," never "dropped by height," even though it would also fail the height check). Only
then, when `min_height_in` is given, a listing whose known `height_in` falls below it is dropped
into `dropped_by_height`; a listing with no parsable height at all is kept and flagged `"height
unknown"` rather than dropped by this rule alone.

## The Markdown report (`product-scan-<slug>-<date>.md`)

| Section | Content |
| :--- | :--- |
| Header block | The query, the sites read, the page count, the generation timestamp, and the FIVE listing counts, in order: read, unique after fold (before exclusion), excluded, dropped by height, ranked (fix batch B8, 2026-09-11) |
| `## Reference listing` (present only when a reference was given and readable) | Its origin, title, price, price per foot, height, length, material, stake count and material, rating, score - each its OWN line - and the sentence "Your pick would rank #k of n in the `<tier>` tier." |
| One table per tier, in the order plastic, metal, other | `\| # \| Listing \| Site \| Price \| $/ft \| Height \| Length \| Material \| Stakes \| Rating \| Score \|` - the reference row, when it falls in that tier, is inserted at its own rank, in bold, with the label `REFERENCE`; a literal `\|` inside a title is escaped as `\\\|` first (fix batch B1) |
| `## Notes` | Every `note:` line the scan printed (walls, skipped pages, the zero-cards note, the reference-wall fallback), or `- (none)` |
| `## Excluded` | A count for every distinct `excluded_reason` seen, each followed by the title (trimmed to 60 characters) of every listing dropped for it (fix batch B6), or `- (none)` |
| `## Dropped by height` (fix batch B6, NEW) | The title (trimmed to 60 characters) of every listing `--min-height-in` dropped, or `- (none)` |

See `contracts/scan-and-report.md` section 2.2 for a full real render.

## The JSON report (`product-scan-<slug>-<date>.json`)

```json
{
  "meta": {
    "query": "<the --query text>",
    "sites": ["amazon"],
    "pages": 2,
    "generated_at": "<ISO 8601 UTC timestamp>",
    "read": 0, "unique": 0, "excluded": 0, "dropped_by_height": 0, "ranked": 0,
    "notes": []
  },
  "reference": null,
  "tiers": {
    "plastic": [],
    "metal": [],
    "other": []
  },
  "excluded": []
}
```

`meta` is a FLAT object (fix batch B3, 2026-09-11: CODE's shape wins over this document's own
earlier nested `counts`/`excluded_reasons` draft) whose five counts mirror the Markdown header's
own five, by the same names. `reference`, when a reference was given and readable (or supplied by
hand), is one `Listing` serialized as a flat dictionary, with THREE extra keys (fix batch B3, NEW):
`"rank"` (its 1-based position within its own tier's list), `"tier"` (the tier name it was scored
into), and `"tier_size"` (that tier's own count including the reference - the "of n" in the rank
sentence). `tiers` holds every kept, ranked listing, grouped and ordered exactly as the Markdown
report's own tables are. `excluded` (fix batch B6, NEW) holds every listing dropped for an
`excluded_reason`, serialized the same way, for auditability - a listing dropped only by
`--min-height-in` is not included here (it is counted in `meta.dropped_by_height` but not itself
serialized, since its own attributes carry no exclusion reason to audit). Every listing entry
mirrors `Listing`'s own dataclass fields exactly (`asdict(listing)`). See
`contracts/scan-and-report.md` section 2.3 for a full real render.
