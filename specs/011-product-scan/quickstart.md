# Quickstart: Product Scan

**Feature**: 011-product-scan | **Date**: 2026-09-11

Runnable scenarios that exercise this feature. The query used in every example below,
`"no dig landscape edging"`, is the same public product category the 2026-09-11 recon checked -
never a record of the Director's own specific purchase decision.

## Prerequisites

- From the worktree root, the existing `.venv` (no new dependency - this feature adds no entry to
  `requirements.txt`).
- No vault item and no `profile` entry is needed. This errand opens the vault for nothing.

## Scenario 1: check mode (read-only, safe to run any time)

```bash
python scripts/product_scan.py --query "no dig landscape edging" --check
```

Expected:

- One line per Amazon selector (`found` or `MISSING`), since `--sites` defaults to `amazon`.
- A summary line, `CHECK <n> found, <m> missing`.
- No file written under `reports/product/`.
- Exit code 0, regardless of the found/missing count.

## Scenario 2: a default scan (Amazon only)

```bash
python scripts/product_scan.py --query "no dig landscape edging"
```

Expected:

- A headless Chrome session reads Amazon's own search results for pages 1 and 2 (the default
  `--pages`), parses every card's title for height, length, material, and stakes, folds
  duplicates, scores and tiers the kept listings.
- `reports/product/product-scan-<today's UTC date>.md` and `.json` are written, both at file mode
  `0600`.
- The script prints `SCAN <the Markdown path>`.

## Scenario 3: opting into Home Depot as a second source

```bash
python scripts/product_scan.py --query "no dig landscape edging" --sites amazon,homedepot
```

Expected:

- Amazon and Home Depot are both read. Home Depot's own lazy-loaded pods are scrolled into view
  before they are read.
- If Home Depot's own search page shows the `Error Page` wall (recon 2026-09-11 observed this on
  every visit after the first, within about ten minutes), the script prints
  `note: page skipped for 'homedepot p1' (wall: Error Page)`, skips Home Depot's remaining pages,
  and the report still writes from Amazon's own results.
- Home Depot's own duplicated pods (12 unique products rendered as 24 pods, recon 2026-09-11) fold
  into 12 listings, not 24.

## Scenario 4: comparing a specific listing (the Director's own reference)

```bash
python scripts/product_scan.py --query "no dig landscape edging" \
    --reference-url "https://www.amazon.com/dp/B01MG4ARN7"
```

Expected:

- The reference page is read after the search pages.
- The report opens with a `## Reference` section stating the listing's own price, price per foot,
  height, length, material, stakes, rating, and the sentence "your pick would rank #k of n in the
  `<tier>` tier."
- The same listing, marked **REFERENCE**, appears at its own rank inside its tier's table.

A Walmart reference URL meets the bot wall under headless Chrome (recon 2026-09-11: title
`Robot or human?`):

```bash
python scripts/product_scan.py --query "no dig landscape edging" \
    --reference-url "https://www.walmart.com/ip/18656266943" --show
```

`--show` opens a real, visible Chrome window so the Director can pass the wall by hand, the same
escape hatch this repository's Progressive walk documents for its own quote-start block.

## Scenario 5: a hand-typed reference, fully headless, with a height filter

```bash
python scripts/product_scan.py --query "no dig landscape edging" \
    --reference "BSHAPPLUS 4in x 40ft No Dig Landscape Edging Kit with 45 Unbreakable Steel Stakes | 31.58 | 40 | 4.1 | 15" \
    --min-height-in 3
```

Expected:

- No reference page is read at all; the reference is scored and tiered from the typed facts
  (title, price, length, and - fix batch A4, 2026-09-11 - an optional rating and review count),
  with `origin` set to `reference-hand`; the reference block and its table row show `4.1 (15)`
  instead of `-`.
- Every listing whose own parsed height is below 3 inches is dropped from every tier table and
  counted under "dropped by height" in the header block; a listing whose height could not be
  parsed at all is kept, flagged "height unknown."

When both `--reference-url` and `--reference` are given, a successful URL read wins; the literal
is used only when the URL read fails or walls (fix batch B19, 2026-09-11: an unsupported
`--reference-url` host refuses the WHOLE run before any browser opens - the literal is never
reached in that case, since the scan never starts at all).

## Scenario 6: reading the report

```bash
cat reports/product/product-scan-<slug>-<date>.md
```

`<slug>` is the query's own slug (fix batch A5, 2026-09-11: lower-cased, non-alphanumeric runs
collapsed to one hyphen, trimmed, cut to 40 characters) - for example,
`product-scan-no-dig-landscape-edging-2026-09-11.md`.

Expected sections, in order: a header block (query, sites, pages, generation time, and the five
listing counts - read, unique after fold, excluded, dropped by height, ranked), a
`## Reference listing` section (when a reference was given and readable), one table per tier
present among the kept listings (plastic, metal, other), `## Notes`, `## Excluded`, and
`## Dropped by height` (fix batch B6, 2026-09-11 - the latter two now also list each listing's own
title, not only a count).

```bash
cat reports/product/product-scan-<slug>-<date>.json
```

Expected: `{"meta": {}, "reference": null, "tiers": {"plastic": [], "metal": [], "other": []},
"excluded": []}`, where every listing entry carries the same fields the Markdown report's own rows
draw from, plus every field the Markdown report omits for space (the raw score, the shrunk rating,
the flags list, the pages a listing was found on). See `contracts/scan-and-report.md` section 2.3
for the full real shape, including the reference object's own `rank`/`tier`/`tier_size` keys.

Confirm nothing leaked to the repository:

```bash
git status
```

Expected: clean, or showing only files this delivery's own implementation and documentation
intentionally added - never a file under `reports/`, which stays gitignored like every other
`reports/` sub-folder.
