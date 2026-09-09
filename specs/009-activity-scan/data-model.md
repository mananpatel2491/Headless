# Data Model: Activity Scan

**Feature**: 009-activity-scan | **Date**: 2026-09-09

No database, no vault item, no profile field. The two persisted artifacts are
`reports/activity/activity-scan-<UTC date>.md` and `.json` - each run replaces or adds a
same-date pair; a run on a new UTC date adds a new pair rather than overwriting an older one.
Everything else below is in-memory for the lifetime of one `scripts/activity_scan.py`
invocation, or is the description of a pure function's own contract.

## The pipeline state flow

```text
queries -> cards -> fold -> locate -> rank -> details -> re-rank -> render
```

| State | Produced by | What it holds |
| :--- | :--- | :--- |
| `queries` | `_load_queries` (the built-in `DEFAULT_QUERIES` list, or a `--queries-file`) | A list of `(tag, query)` pairs |
| `cards` | `read_search_page`, once per query, after `_scroll_feed_to_end` - or `read_single_place` when that query's own page opened one place directly, with no results feed | Every result card on that query's own search page, or the one place Google opened directly, as a `Venue`, each with its own 0-based `position` already set, unscored, unlocated |
| `fold` | `headless.activities.fold_duplicates` | The same venues, collapsed by `(name, rounded lat, rounded lon)`, a non-sponsored copy winning over a sponsored one, `matched_queries` unioned, and the lower of the two copies' own `position` kept. The kept copy's own `tag` is whichever copy `fold_duplicates` keeps: ordinarily the first copy folded under that key (deterministic - query order), unless a later non-sponsored copy overrides an earlier sponsored one, in which case the later copy's own `tag` is kept instead. A venue surfaced under two tags is filed in the report under its one kept `tag` alone; `matched_queries` still lists every query that surfaced it |
| `locate` | `headless.activities.locate` | Every folded venue's own `miles`/`drive_minutes`, computed from the resolved point |
| `rank` (first pass) | `headless.activities.rank` | Excluded-category and out-of-radius venues dropped; each remaining venue's own `relevant` flag set (`relevance_hit`), then scored (`day_status` still `"unknown"` for every venue) and sorted |
| `details` | `read_place_page`, for the top `--details` ranked venues | Each visited venue's own `weekly_hours`, `website`, `phone`, and (when present) a fuller `address` |
| `re-rank` (second pass) | `headless.activities.rank`, called again | The same venues, re-scored with each enriched venue's own `day_status` now known, re-sorted |
| `render` | `render_markdown` / `render_json` | The two report files (below) |

## Venue

```text
Venue(
    name: str, url: str, tag: str, query: str,
    position: int | None = None,
    lat: float | None = None, lon: float | None = None,
    rating: float | None = None, reviews: int | None = None,
    category: str = "", address: str = "", hours_today: str = "",
    sponsored: bool = False,
    miles: float | None = None, drive_minutes: int | None = None,
    weekly_hours: dict[str, str] = {},
    day_ranges: list[list[int]] = [],
    window_overlap_minutes: int | None = None,
    day_status: str = "unknown",
    website: str = "", phone: str = "",
    matched_queries: list[str] = [],
    relevant: bool | None = None,
    score: float = 0.0,
    excluded: bool = False,
)
```

| Field | Set by | Notes |
| :--- | :--- | :--- |
| `name`, `url`, `tag`, `query` | The search page parse | `url` is the venue's own place-page link, used again for detail enrichment |
| `position` | The search page parse - the card's own 0-based place in that query's own result list; `0` for a query answered by a single place page | `fold_duplicates` keeps the lower of the two copies' own value; `score_venue` subtracts `0.015` for every place counted, when known |
| `lat`, `lon` | Parsed from the place link's own `!3d<lat>!4d<lon>` pair, or a place page's own `/@<lat>,<lon>,` viewport pair when that pair is absent | `None` when neither pattern is present |
| `rating`, `reviews` | The card's own rating label, or its own text-line rating when the label is absent | Both `None` for an unrated venue |
| `category`, `address`, `hours_today` | The card's own text lines | `category` drives the exclusion rule (FR-007); `hours_today` is read but not used for the day-window verdict (research.md D6) |
| `sponsored` | Whether any of the card's own text lines reads exactly "Sponsored" | Decides which copy `fold_duplicates` keeps |
| `miles`, `drive_minutes` | `locate` | `None`/`None` when `lat`/`lon` are `None` |
| `weekly_hours` | The place page's own hours table, for an enriched venue only | Empty `{}` for a venue never enriched |
| `day_ranges`, `window_overlap_minutes`, `day_status` | `apply_day_window` | `day_status` starts `"unknown"` and stays there for a venue never enriched, for a venue with no row for the configured day, or for a day whose own hours text parses to no time range and does not contain the word "closed" (an empty cell, or text such as "Hours might differ" that the range parser does not recognize - the hours were never really read, so the verdict is never "closed" in this case) |
| `website`, `phone` | The place page's own website link and phone button, for an enriched venue only | Empty strings otherwise |
| `matched_queries` | `fold_duplicates` | Every query (across every duplicate) that surfaced this venue; its first two entries render as the Markdown report's own "Found via" column |
| `relevant` | `relevance_hit`, via `rank`, before scoring | `True` when the venue's name or category echoes a query stem; `False` when it echoes none but at least one surfacing query carried a meaning-carrying token; `None` either before ranking or as the neutral verdict when no surfacing query carries a meaning-carrying token at all (for example, "cafe bar club"); `score_venue` adds `0.35` for `True`, subtracts `0.25` for `False`, and leaves the score unaffected for `None` |
| `score` | `score_venue`, via `rank` | Computed twice: once before enrichment (day-window neutral), once after (FR-014) |
| `excluded` | `rank` | `True` for a category this feature excludes (FR-007); such a venue is dropped from the kept list, but the flag itself is set on the record before it is dropped |

## The Markdown report (`activity-scan-<date>.md`)

| Section | Content |
| :--- | :--- |
| Header block | The resolved point (label and coordinates), the day and window, the generation timestamp, the source line (Google Maps list view, query count), and the kept-venue count after folding, exclusion, and the radius cut |
| "Top picks overall" | A table of the top 15 kept venues (rank, venue, rating, distance, category, the configured day's hours, address, and the first two of `matched_queries` under "Found via") |
| One table per tag | The top 6 kept venues for that tag, same columns |

## The JSON report (`activity-scan-<date>.json`)

```json
{
  "meta": {
    "near": [42.4800, -83.3800],
    "near_label": "<the raw --near text>",
    "area": "<the resolved --area text>",
    "day": "<the configured day>",
    "window": "<start>-<end>",
    "generated_at": "<ISO 8601 UTC timestamp>",
    "queries": [["<tag>", "<query>"], []]
  },
  "venues": [
    {}
  ]
}
```

Each entry in `venues` is one `Venue`, serialized as a flat dictionary (`asdict(venue)`). `venues`
lists every kept, ranked venue in the same order as the Markdown report's own "Top picks overall"
table - not grouped by tag in the JSON shape, since a reader can already group by each venue's
own `tag` field.
