# Quickstart: Activity Scan

**Feature**: 009-activity-scan | **Date**: 2026-09-09

Runnable scenarios that exercise this feature. The point used in every example below is a
synthetic round-number point: `42.4800,-83.3800` (a round-number coordinate pair inside
Farmington Hills, Michigan, a public city name, not a real place rounded) is used purely as a
worked example, never as a record of a real chosen point.

## Prerequisites

- From the worktree root, the existing `.venv` (no new dependency - this feature adds no entry
  to `requirements.txt`).
- No vault item and no `profile` entry is needed. This errand opens the vault for nothing.

## Scenario 1: check mode (read-only, safe to run any time)

```bash
python scripts/activity_scan.py --near "42.4800,-83.3800" --check
```

Expected:

- One line per dependent selector (`found` or `MISSING`).
- A summary line, `CHECK <n> found, <m> missing`.
- No file written under `reports/activity/`.
- Exit code 0, regardless of the found/missing count.

## Scenario 2: a scan given a coordinate pair

```bash
python scripts/activity_scan.py --near "42.4800,-83.3800" --area "Farmington Hills, MI"
```

Expected:

- No network call to Nominatim - the point parses directly as `"lat,lon"`.
- A headless Chrome session runs every built-in query, folds duplicates, drops excluded
  categories and out-of-radius venues, enriches the top 60 kept venues, and re-ranks.
- `reports/activity/activity-scan-<today's UTC date>.md` and `.json` are written, both at file
  mode `0600`.
- The script prints `SCAN <the Markdown path>`.

## Scenario 3: a scan given a street address

```bash
python scripts/activity_scan.py --near "1 Example Street, Farmington Hills, MI"
```

`"1 Example Street"` is a deliberate placeholder, matching the same placeholder this feature's own
test suite uses for a resolvable-address fixture - never a real chosen point.

Expected:

- Exactly one Nominatim request resolves the address to a coordinate pair before any browser
  session opens.
- If Nominatim cannot resolve the address, the script prints `REFUSED: --near could not be
  resolved to a point (use "lat,lon" or a fuller address)` and exits 1 - no browser session is
  ever constructed.
- `--area`, left unset here, defaults to the raw address text.

## Scenario 4: a custom queries file

```bash
cat > /tmp/my-queries.txt <<'EOF'
games	bowling alley
outdoors	mini golf
EOF
python scripts/activity_scan.py --near "42.4800,-83.3800" --queries-file /tmp/my-queries.txt
```

Expected:

- The scan runs exactly the two queries in the file, never the built-in `DEFAULT_QUERIES` list.
- The report's "games" and "outdoors" tag tables reflect only these two queries' own results.

## Scenario 5: reading the report

```bash
cat reports/activity/activity-scan-<date>.md
```

Expected sections, in order: a header block (point, window, generation time, source,
kept-venue count), a "Top picks overall" table, then one table per tag present among the kept
venues. Every table row names a venue, its own raw Google rating and review count (the Bayesian
shrink feeds only the ranking score behind the scenes, never the rating printed in this table),
its distance and drive-minutes estimate, its category, its hours for the configured day, and its
address.

```bash
cat reports/activity/activity-scan-<date>.json
```

Expected: `{"meta": {}, "venues": []}`, where every venue entry carries the same fields the
Markdown report's own rows draw from, plus every field the Markdown report omits for space
(coordinates, the full weekly hours mapping, matched queries, the raw score).

Confirm nothing leaked to the repository:

```bash
git status
```

Expected: clean, or showing only files this delivery's own implementation and documentation
intentionally added - never a file under `reports/`, which stays gitignored like every other
`reports/` sub-folder.
