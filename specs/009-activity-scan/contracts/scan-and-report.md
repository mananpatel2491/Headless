# Contracts: Activity Scan

**Feature**: 009-activity-scan | **Date**: 2026-09-09

Two stable interfaces: the **CLI contract** (every flag, every exit code, every stdout line) and
the **report file contract** (the Markdown and JSON shapes).

## 1. CLI contract

### Flags

| Flag | Required | Default | Behavior |
| :--- | :--- | :--- | :--- |
| `--near` | Yes | n/a | `"lat,lon"` or a street address, resolved once through Nominatim when it is not a coordinate pair |
| `--area` | No | The raw `--near` text | Appended to every query as `"<query> near <area>"` |
| `--day` | No | `friday` | Must be one of `headless.activities.DAYS` (the seven lowercase day names) |
| `--start` | No | `17:00` | 24-hour `HH:MM` |
| `--end` | No | `22:00` | 24-hour `HH:MM`; a value at or before `--start` is read as continuing past midnight; identical to `--start` is a refusal |
| `--radius-miles` | No | `20.0` | A venue whose computed distance exceeds this is dropped before scoring |
| `--details` | No | `60` | How many top-ranked venues get a place-page visit for weekly hours, website, and phone |
| `--queries-file` | No | n/a (built-in list) | A file of `tag<TAB>query` lines, replacing `DEFAULT_QUERIES` entirely |
| `--check` | No | `False` | Read-only selector probe; see section 1.3 |
| `--apply` | No (hidden, `argparse.SUPPRESS`) | `False` | Always refused; see section 1.4 |
| `--show` | No | `False` | Keeps the browser window visible |
| `--profile-dir` | No | `HEADLESS_PROFILE_DIR` | Overrides the Chrome profile directory |
| `--preview-dir` | No | `HEADLESS_PREVIEW_DIR` | Overrides the directory `reports/activity/` resolves beside |

### 1.1 Stdout lines

| Line | When |
| :--- | :--- |
| `SCAN <markdown report path>` | A scan (non-`--check`) run completes and both report files are written |
| `  <'found  ' or 'MISSING'> <selector>` | Once per selector, during `--check` |
| `CHECK <n> found, <m> missing` | Once, at the end of `--check` |
| `  '<query>': <count> results` | Once per query, during a scan, before duplicate folding |
| `  '<query>': 1 result (Google opened the place directly)` | In place of the line above, once per query whose own page carried no results feed and opened one place directly |
| `note: query skipped for '<query>' (<ExceptionClass>)` | A query's own navigation or read raised an exception during a scan; the scan continues with the remaining queries |
| `note: no results feed for '<query>' (selector missing)` | A query's own search page loaded with no `role="feed"` container present |
| `note: details skipped for '<name>' (<ExceptionClass>)` | A shortlisted venue's own place-page visit, during detail enrichment, raised an exception; the venue stays in the report with `day_status` remaining `"unknown"` |
| `note: <message>` | Any other non-fatal, value-free notice (for example, a session-cookie import/export failure inherited from `Session`) |
| `REFUSED: <reason>` | Any of the refusals in section 1.4 |
| `ERROR: <ExceptionClassName> (rerun with HEADLESS_DEBUG=1 for the traceback)` | An unhandled exception during the browser session |

### 1.2 Scan mode (default, no `--check`, no `--apply`)

1. Load the active query list (`DEFAULT_QUERIES`, or `--queries-file`'s own lines).
2. Resolve `--near` to a coordinate pair (direct parse, or one Nominatim request).
3. Open a `Session(config, Mode.PREVIEW)` - headless Chrome unless `--show`.
4. For each query: navigate to its search URL and wait for the results feed. When the feed is
   present, scroll it to its own end - stopping at whichever of the following comes first: the
   page's own "reached the end of the list" text; two consecutive scrolls that each load no new
   card; or 8 scroll attempts (`MAX_FEED_SCROLLS`) - then parse every result card into a `Venue`,
   numbering each card's own `position`. When the feed is absent and the page's own URL contains
   "/maps/place/" (Google opened one place directly), read that page instead as the query's
   single result, at `position` 0. When navigating to, or reading, this query's own page raises an
   exception, the scan prints `note: query skipped for '<query>' (<ExceptionClass>)` and continues
   with the next query - one query's own failure never ends the whole scan.
5. Fold duplicates, locate every venue relative to the resolved point, exclude ruled-out
   categories and out-of-radius venues, score, and sort.
6. For the top `--details` venues, visit the place page and read weekly hours, website, and
   phone.
7. Re-score and re-sort using the day-window verdict just computed.
8. Write the Markdown and JSON reports under `reports/activity/`, at file mode `0600`.
9. Print `SCAN <markdown path>` and exit 0.

### 1.3 Check mode (`--check`)

1. Resolve `--near` exactly as in scan mode.
2. Open a `Session(config, Mode.PREVIEW)`.
3. Navigate to the first configured query's own search URL only.
4. Wait (best-effort, up to 15 seconds) for the results feed selector.
5. Probe, read-only, the feed selector, the feed-scoped place-link selector, and the rating
   selector.
6. Print one `found`/`MISSING` line per selector, then the summary line.
7. Exit 0, regardless of the found/missing count. Never scroll, never open a place page, never
   write a report.

### 1.4 Refusals (exit 1, no session, or no further action)

| Condition | Message | Session constructed? |
| :--- | :--- | :--- |
| `--apply` given | `REFUSED: activity_scan is read-only; there is no apply mode` | No - checked before any configuration or argument beyond parsing is resolved |
| A malformed `--start`/`--end` (does not parse as `HH:MM`, or its hour is outside 00-23 or its minute is outside 00-59 - `window_minutes` raises `ValueError`), or `--start == --end` | `REFUSED: <the underlying ValueError or ConfigError message>` | No |
| `--queries-file` resolves to zero usable lines | `REFUSED: no queries to run` | No |
| `--near` cannot be resolved: a coordinate-shaped pair - including one carrying a leading "+" or a trailing ",<zoom>" or ",<zoom>z" as pasted from a map URL (for example, "+95,0" or "95,0,17z") - that is out of range is refused directly, with no geocoder request at all (`looks_like_coordinates` tells it apart from an address); free text that is not coordinate-shaped is sent to Nominatim once, and a geocoding failure or an empty result then refuses the same way | `REFUSED: --near could not be resolved to a point (use "lat,lon" or a fuller address)` | No |
| A `GateRefused` raised inside the session (for example, the Chrome profile is already locked by another run) | `REFUSED: <the GateRefused message>` | Yes - the refusal surfaces from inside the `with Session(...)` block |

### 1.5 Exit codes

| Code | Meaning |
| :--- | :--- |
| `0` | A report was written, or `--check` completed |
| `1` | Any refusal in section 1.4 |
| `2` | An `argparse` usage error, or an unhandled exception during the browser session (the exception's own class name only is printed; the full traceback prints to stderr only when `HEADLESS_DEBUG=1`) |

## 2. Report file contract

### 2.1 File identity

| Property | Value |
| :--- | :--- |
| Directory | `reports/activity/` (created if absent) |
| Markdown filename | `activity-scan-<UTC date, YYYY-MM-DD>.md` |
| JSON filename | `activity-scan-<UTC date, YYYY-MM-DD>.json` |
| File mode | `0600` - written and re-chmodded to `0600` on every run, including a same-date overwrite |
| Overwrite behavior | A second run on the same UTC date overwrites both files for that date; a run on a new UTC date adds a new pair |

### 2.2 Markdown shape

```text
# Activity scan

- Near: <near_label> (<lat>, <lon>)
- Window: <Day> <start>-<end>
- Generated: <ISO 8601 UTC timestamp>
- Source: Google Maps list view via Headless (headless Chrome), <n> queries
- Venues after folding, exclusions and radius: <count>

...two lines of reading-aid prose about distance and hours being estimates...

## Top picks overall

| # | Venue | Rating | Distance | Category | Hours | Address | Found via |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
...(up to 15 rows)...

## <Tag>

| # | Venue | Rating | Distance | Category | Hours | Address | Found via |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
...(up to 6 rows, one table per tag present among the kept venues)...
```

- `Venue` renders as `[<name>](<website>)` when `website` is non-empty, else the plain name.
- `Rating` renders as `<rating:.1f> (<reviews>)` or `no rating`.
- `Distance` renders as `<miles:.1f> mi, ~<drive_minutes> min` or `distance unknown`.
- `Hours` renders as `<Day>: <hours text>` or `<Day>: not checked` when the venue's own
  `weekly_hours` has no entry for the configured day.
- `Category`/`Address` render as the venue's own value, or `?` when empty.
- `Found via` renders as the first two entries of the venue's own `matched_queries`, comma
  separated.

### 2.3 JSON shape

```json
{
  "meta": {
    "near": [42.4800, -83.3800],
    "near_label": "<raw --near text>",
    "area": "<resolved --area text>",
    "day": "<configured day>",
    "window": "<start>-<end>",
    "generated_at": "<ISO 8601 UTC timestamp>",
    "queries": [["<tag>", "<query>"], []]
  },
  "venues": [
    {
      "name": "", "url": "", "tag": "", "query": "", "position": null,
      "lat": null, "lon": null, "rating": null, "reviews": null,
      "category": "", "address": "", "hours_today": "",
      "sponsored": false, "miles": null, "drive_minutes": null,
      "weekly_hours": {}, "day_ranges": [], "window_overlap_minutes": null,
      "day_status": "unknown", "website": "", "phone": "",
      "matched_queries": [], "relevant": null, "score": 0.0, "excluded": false
    }
  ]
}
```

`venues` is a flat list, in the same rank order as the Markdown report's own "Top picks overall"
table (descending score, then ascending distance, then name). Every field mirrors `Venue`'s own
dataclass fields exactly (`asdict(venue)`).
