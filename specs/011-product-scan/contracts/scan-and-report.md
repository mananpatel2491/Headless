# Contracts: Product Scan

**Feature**: 011-product-scan | **Date**: 2026-09-11

Two stable interfaces: the **CLI contract** (every flag, every exit code, every stdout line) and
the **report file contract** (the Markdown and JSON shapes).

## 1. CLI contract

### Flags

| Flag | Required | Default | Behavior |
| :--- | :--- | :--- | :--- |
| `--query` | Yes | n/a | Non-empty after strip; refused otherwise |
| `--pages` | No | `2` | Integer, 1 through 5 inclusive; refused outside that range |
| `--sites` | No | `amazon` | Comma-separated list drawn from `amazon`, `homedepot`; an unknown id is refused |
| `--reference-url` | No | n/a | An Amazon or Walmart listing URL, read after every search page; any other host is refused before any browser opens |
| `--reference` | No | n/a | `"Title \| price \| length_ft [\| rating [\| reviews]]"` (three, four, or five pipe-separated parts - fix batch A4, 2026-09-11); malformed input, a zero/negative price or length, an out-of-range rating, or a negative review count is refused before any browser opens (fix batch B7) |
| `--min-height-in` | No | n/a (no height filter) | A listing whose parsed height is below this value is dropped from every tier table and counted; a listing with no parsable height is kept and flagged |
| `--check` | No | `False` | Read-only selector probe; see section 1.3 |
| `--apply` | No (hidden, `argparse.SUPPRESS`) | `False` | Always refused; see section 1.4 |
| `--show` | No | `False` | Keeps the browser window visible - the Director's own escape hatch past the Walmart reference wall |
| `--profile-dir` | No | `HEADLESS_PROFILE_DIR` | Overrides the Chrome profile directory |
| `--preview-dir` | No | `HEADLESS_PREVIEW_DIR` | Overrides the directory `reports/product/` resolves beside |

### 1.1 Stdout lines

CODE wins over an earlier draft of this contract on every line below (fix batch B3, 2026-09-11) -
each is copied from a real run.

| Line | When |
| :--- | :--- |
| `SCAN <markdown report path>` | A scan (non-`--check`) run completes and both report files are written |
| `  <'found  ' or 'MISSING'> <selector>` | Once per selector, per selected site, during `--check` |
| `CHECK <n> found, <m> missing` | Once, at the end of `--check` |
| `  '<site>' p<N>: <count> results` | Once per `(site, page)` pair, during a scan, before duplicate folding |
| `note: page skipped for '<site> p<N>' (wall: <title>)` | A wall (a title in `WALL_TITLES`, or a `/blocked?` URL) was detected on that site's own page 1; that site's remaining pages are skipped for this run |
| `note: page skipped for '<site> p<N>' (<ExceptionClassName>)` | A page's own navigation or read raised an exception; the scan continues with that site's remaining pages |
| `note: page skipped for '<site> p<N>' (zero cards)` | A page loaded with zero result cards or pods; this note ALSO lands in the written report's own `## Notes` section |
| `note: reference not readable headless (bot wall) - rerun with --show` | The reference page (when given) showed a wall; `--reference`'s own literal becomes the reference when it was also given |
| `note: <message>` | Any other non-fatal, value-free notice (for example, a session-cookie import/export failure inherited from `Session`) |
| `REFUSED: <reason>` | Any of the refusals in section 1.4 |
| `ERROR: <ExceptionClassName> (rerun with HEADLESS_DEBUG=1 for the traceback)` | An unhandled exception during the browser session |

### 1.2 Scan mode (default, no `--check`, no `--apply`)

1. Validate `--query` (non-empty), `--pages` (1 through 5), `--sites` (every id known), and
   `--reference` (when given, three, four, or five well-formed parts); any failure refuses before
   a `Session` is constructed.
2. Validate `--reference-url`'s own host (when given) against `REFERENCE_HOSTS`; any other host
   refuses before a `Session` is constructed.
3. Open a `Session(config, Mode.PREVIEW)` - headless Chrome unless `--show`.
4. For each site in `--sites`, for each page number 1 through `--pages`: navigate to that site's
   own search URL for that page (`search_url(site, query, page_number)`) and read its result cards
   or pods (`read_amazon_search`/`read_homedepot_search`), scrolling Home Depot's own lazy-loaded
   pods into view first. A wall on a site's own page 1 skips that site's remaining pages, with a
   note; any other exception, or a page with zero cards, skips only that page, with a note; either
   way the scan continues.
5. Parse every collected listing's own title through `parse_attributes`, fold duplicates by
   `canonical_url`, score every kept listing, and rank the remainder into tiers, applying
   `--min-height-in` when given.
6. When `--reference-url` or `--reference` was given: read the reference page
   (`read_amazon_product`/`read_walmart_product`) when a supported URL was given; on a wall, print
   the fixed reference note and fall back to `--reference`'s own literal
   (`parse_reference_literal`) when it was also given. Parse, score, and locate the reference
   inside its own tier's ranked list.
7. Write the Markdown and JSON reports under `reports/product/`, at file mode `0600`.
8. Print `SCAN <markdown path>` and exit 0.

### 1.3 Check mode (`--check`)

1. Validate arguments exactly as scan mode's step 1 (`--reference-url`/`--reference` are accepted
   but never read in check mode).
2. Open a `Session(config, Mode.PREVIEW)`.
3. For each site in `--sites`: navigate to that site's own search URL for page 1 only.
4. Wait (best-effort, up to 15 seconds) for that site's own card/pod selector.
5. Probe, read-only, that site's own entry in `CHECK_SELECTORS` - EVERY selector past the card/pod
   itself is a descendant of it, never a bare page-level selector (fix batch B10, 2026-09-11):
   `CHECK_SELECTORS["amazon"] = (` `div[data-component-type="s-search-result"]`, that selector +
   `" h2 span"`, that selector + `" .a-price .a-offscreen"`, that selector +
   `' i[class*="a-icon-star"] .a-icon-alt'` `)`; `CHECK_SELECTORS["homedepot"] = (`
   `[data-testid="product-pod"]`, that selector + `' [data-testid="product-header"]'`, that
   selector + `' [data-testid="price-simple"]'`, that selector + `' [data-testid*="rating"]'` `)`.
6. Print one `found`/`MISSING` line per selector, then the summary line.
7. Exit 0, regardless of the found/missing count. Never scroll, never read a reference, never
   write a report, never visit any page beyond page 1 of any selected site.

### 1.4 Refusals (exit 1, no session, or no further action)

| Condition | Message | Session constructed? |
| :--- | :--- | :--- |
| `--apply` given | `REFUSED: product_scan is read-only; there is no apply mode` | No - checked before any configuration or argument beyond parsing is resolved |
| `--query` is empty, or empty after strip | `REFUSED: --query must not be empty` | No |
| `--pages` outside 1 through 5 | `REFUSED: --pages must be between 1 and 5` | No |
| `--sites` names an id outside `("amazon", "homedepot")` | `REFUSED: unknown site '<id>' (known: amazon, homedepot)` | No |
| `--reference` is not three, four, or five pipe-separated parts, or its price/length/rating/reviews does not parse or is out of range (fix batch A4/B7: price and length must be positive, rating 0-5, reviews >= 0) | `REFUSED: expected "Title \| price \| length_ft [\| rating [\| reviews]]"` | No |
| `--reference-url` names a host outside `REFERENCE_HOSTS` | `REFUSED: unsupported reference host '<host>'` | No |
| A `GateRefused` raised inside the session (for example, the Chrome profile is already locked by another run) | `REFUSED: <the GateRefused message>` | Yes - the refusal surfaces from inside the `with Session(...)` block |
| A `ConfigError` raised while resolving configuration | `REFUSED: <the ConfigError message>` | No |

### 1.5 Exit codes

| Code | Meaning |
| :--- | :--- |
| `0` | A report was written, or `--check` completed |
| `1` | Any refusal in section 1.4 |
| `2` | An `argparse` usage error, or an unhandled exception during the browser session (the exception's own class name only is printed; the full traceback prints to stderr only when `HEADLESS_DEBUG=1`) |

## 2. Report file contract

CODE wins over an earlier draft of this contract on every shape below (fix batch B3/B6/B8/B9,
2026-09-11); every example is copied verbatim from a real render (a synthetic fixture in the same
shape as the recon evidence, per NFR-002 - never a real scan's own output).

### 2.1 File identity

| Property | Value |
| :--- | :--- |
| Directory | `reports/product/` (created if absent) |
| Markdown filename | `product-scan-<slug>-<UTC date, YYYY-MM-DD>.md` |
| JSON filename | `product-scan-<slug>-<UTC date, YYYY-MM-DD>.json` |
| `<slug>` | The query lower-cased, every run of non-alphanumerics collapsed to one hyphen, trimmed of leading/trailing hyphens, cut to 40 characters (fix batch A5) |
| File mode | `0600` - written and re-chmodded to `0600` on every run, including a same-date overwrite |
| Overwrite behavior | A second run of the SAME query on the same UTC date overwrites both files for that date; a different query, or a run on a new UTC date, adds a new pair (fix batch B9: the slug is what makes two different queries the same day coexist) |
| UTC date | The stamp is UTC, not local time - an evening run in the US lands on the next calendar day (fix batch B24, behavior unchanged, documented) |

### 2.2 Markdown shape

```text
# Product scan

- Query: no dig landscape edging
- Sites: amazon
- Pages: 2
- Generated: 2026-09-12T00:34:14Z
- Listings: 96 read, 77 unique after fold, 1 excluded, 1 dropped by height, 2 ranked

## Reference listing

- Origin: reference-hand
- Title: BSHAPPLUS Listing Plastic
- Price: $31.58
- $/ft: $0.789
- Height: -
- Length: 40 ft
- Material: plastic
- Rating: 4.1 (15)
- Score: 3.6430

Your pick would rank #3 of 3 in the plastic tier.


## Plastic

| # | Listing | Site | Price | $/ft | Height | Length | Material | Stakes | Rating | Score |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | [Bluepro Listing With a "Quote" and \| Pipe](https://www.amazon.com/dp/AAAAAAAAAA) | amazon | $43.99 | $0.440 | - | 100 ft | plastic | - | 4.5 (158) | 4.2117 |
| 2 | [EasyFlex Listing](https://www.amazon.com/dp/BBBBBBBBBB) | amazon | $87.98 | $0.880 | - | 100 ft | plastic | - | 4.6 (200) | 4.0933 |
| 3 | **BSHAPPLUS Listing Plastic (REFERENCE)** | reference | $31.58 | $0.789 | - | 40 ft | plastic | - | 4.1 (15) | 3.6430 |

## Notes

- note: page skipped for 'homedepot p1' (wall: Error Page)
- note: reference not readable headless (bot wall) - rerun with --show

## Excluded

- fence, not edging: 1
  - A Fenced Panel Product

## Dropped by height

- A Short Listing
```

Notes on the render above (each verified against the actual `render_markdown` output, fix batch
B3):

- The header block is `- Query:`, `- Sites:`, `- Pages:`, `- Generated:` as FOUR SEPARATE lines
  (never combined onto one, and never the earlier `(<pages> pages each)` phrasing), then the
  `- Listings:` line with the five counts in this fixed order and these fixed labels - `read`,
  `unique after fold`, `excluded`, `dropped by height`, `ranked` (fix batch B8: `unique` is the
  count BEFORE exclusion; exclusion itself runs before the height drop, so a short fence is
  counted as "excluded," never "dropped by height").
- The reference heading is `## Reference listing` (not `## Reference`), and every one of its own
  nine facts is its OWN line - `- Origin:`, `- Title:`, `- Price:`, `- $/ft:`, `- Height:`,
  `- Length:`, `- Material:`, `- Rating:`, `- Score:` - never combined multiple-fields-per-line.
- `Listing` renders as `[<title trimmed to 90 chars>](<url>)`, with a literal `|` inside the title
  escaped as `\|` (fix batch B1, 2026-09-11 - 28 of 78 rows broke in one live run before this fix;
  the real Bonviee recon title carries three `|` characters of its own).
- `Price`, `$/ft`, `Height`, `Length`, and `Rating` all render as `-` for an unknown value (CODE
  wins over an earlier draft's per-field phrases like "price unknown"/"no rating" - those phrases
  appear only as `flags` entries, never as a table cell's own text).
- `Length` gets `" (per piece)"` appended when the listing's own `flags` carry
  `"pack: per-piece length"` (fix batch A6) - for example, `"8 ft (per piece)"`.
- `Material` renders as the parsed value; `Stakes` renders as `<stake_count> <stake_material>`
  (for example, `45 steel`) or `-` when `stake_count` is `None`.
- `## Notes` lists every `note:` line the scan printed, or `- (none)` when it printed none.
- `## Excluded` lists a count for every distinct `excluded_reason` seen, each followed by the
  title (trimmed to 60 characters) of every listing dropped for that reason (fix batch B6) - or
  `- (none)` when nothing was excluded.
- `## Dropped by height` (fix batch B6, NEW) lists the title (trimmed to 60 characters) of every
  listing `--min-height-in` dropped, or `- (none)` when nothing was.
- The `## Reference listing` section is present only when a reference was given and successfully
  read or supplied by hand; it is omitted entirely otherwise.

### 2.3 JSON shape

```json
{
  "meta": {
    "query": "no dig landscape edging",
    "sites": ["amazon"],
    "pages": 2,
    "generated_at": "2026-09-12T00:34:14Z",
    "read": 96,
    "unique": 77,
    "excluded": 1,
    "dropped_by_height": 1,
    "ranked": 2,
    "notes": [
      "note: page skipped for 'homedepot p1' (wall: Error Page)",
      "note: reference not readable headless (bot wall) - rerun with --show"
    ]
  },
  "reference": {
    "site": "reference", "title": "BSHAPPLUS Listing Plastic", "url": "", "origin": "reference-hand",
    "price": 31.58, "rating": 4.1, "reviews": 15,
    "position": null, "page": null, "sponsored": false,
    "height_in": null, "length_ft": 40.0, "material": "plastic",
    "stake_count": null, "stake_material": null, "no_dig": false,
    "excluded_reason": null, "price_per_ft": 0.789, "shrunk_rating": 4.0375,
    "score": 3.643, "flags": [], "found_on_pages": [],
    "rank": 3, "tier": "plastic", "tier_size": 3
  },
  "tiers": {
    "plastic": [
      {
        "site": "amazon", "title": "Bluepro Listing With a \"Quote\" and | Pipe",
        "url": "https://www.amazon.com/dp/AAAAAAAAAA", "origin": "search",
        "price": 43.99, "rating": 4.5, "reviews": 158,
        "position": null, "page": null, "sponsored": false,
        "height_in": null, "length_ft": 100.0, "material": "plastic",
        "stake_count": null, "stake_material": null, "no_dig": false,
        "excluded_reason": null, "price_per_ft": 0.44, "shrunk_rating": 4.4317,
        "score": 4.2117, "flags": ["height unknown"], "found_on_pages": []
      }
    ],
    "metal": [],
    "other": []
  },
  "excluded": [
    {
      "site": "amazon", "title": "A Fenced Panel Product", "url": "https://www.amazon.com/dp/CCCCCCCCCC",
      "origin": "search", "price": null, "rating": null, "reviews": null,
      "position": null, "page": null, "sponsored": false,
      "height_in": null, "length_ft": null, "material": "plastic",
      "stake_count": null, "stake_material": null, "no_dig": false,
      "excluded_reason": "fence, not edging", "price_per_ft": null, "shrunk_rating": null,
      "score": 0.0, "flags": [], "found_on_pages": []
    }
  ]
}
```

`meta` is a FLAT object (fix batch B3: CODE's flat shape wins over an earlier draft's nested
`counts`/`excluded_reasons` object) whose five count keys - `read`, `unique`, `excluded`,
`dropped_by_height`, `ranked` - mirror the Markdown header's own five numbers by the same names.
`reference`, when present, is one `Listing` object with THREE extra keys (fix batch B3, NEW):
`"rank"` (its 1-based position within its own tier's list), `"tier"` (the tier name), and
`"tier_size"` (that tier's own count including the reference - the "of n" in the rank sentence).
Every list under `tiers` is sorted exactly as the Markdown report's own tables are (descending
score, then ascending price per foot, then title). `excluded` (fix batch B6, NEW) lists every
listing dropped for an `excluded_reason`, serialized the same way as a kept listing, for
auditability; a listing dropped only by `--min-height-in` is counted in `meta.dropped_by_height`
but not itself listed here (its own record carries no exclusion reason to audit).
