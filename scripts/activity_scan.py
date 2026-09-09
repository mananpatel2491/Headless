#!/usr/bin/env python3
"""activity_scan: rank public venues around a point for an evening out (spec 009-activity-scan).

Background: the Director has a fixed evening window (a chosen point, a start time,
an end time) and wants the options around that point ranked by what reviewers say
and by how far they are - without reading thirty search pages by hand. Yelp and
TripAdvisor refuse headless Chrome outright (recon 2026-09-09: a "Verifying the
device" wall, a blank page), so the one review source this scan reads is the Google
Maps list view, which renders fully and exposes a rating, a review count, a category,
an address, today's status, and each result's own coordinates in its link.

Site: `https://www.google.com/maps/search/<query> near <area>/` (list view), then
each shortlisted result's own place page for its weekly hours, website and phone.
Reads: result cards (name, link, rating label, text lines); place pages (hours table
rows, the website link, the phone and address buttons). Nothing typed, nothing
clicked - the results feed is scrolled with `evaluate` to load the full list.
Writes (up to): nothing on any site. Locally: `reports/activity/activity-scan-<date>.md`
and `.json` (public venue data only; the folder stays gitignored with the rest of
`reports/`).
Secrets / profile fields: none - the vault is never opened. The point to scan around
is a command-line argument (`--near`), never a value stored in this repository.
Handoff: none; read-only, like `probe.py`. There is no apply mode and none may be
added - the scan has nothing to fill. `--check` is the Lesson 4 live selector probe.

Usage:
    python scripts/activity_scan.py --near "42.4800,-83.3800" --area "Farmington Hills, MI"
    python scripts/activity_scan.py --near "<street address>" [--day friday --start 17:00 --end 22:00]
        [--radius-miles 20] [--details 30] [--queries-file FILE] [--show] [--profile-dir PATH]
    python scripts/activity_scan.py --near ... --check

Exit codes: 0 report written (or check completed); 1 a refusal (bad config, an
unparseable point, geocoding failed, `--apply`); 2 a usage error or a browser failure.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from headless import activities as act
from headless.capture import reports_dir_for
from headless.config import ConfigError, load_config
from headless.gates import GateRefused, Mode
from headless.session import Session

HANDOFF = "n/a (read-only errand)"
USER_AGENT = "headless-activity-scan/0.0.9 (+https://github.com/mananpatel2491/Headless)"
MAX_FEED_SCROLLS = 8


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--near", required=True, help='The point to rank around: "lat,lon" or a street address.')
    parser.add_argument("--area", default=None, help='The search-area label appended to every query (default: --near).')
    parser.add_argument("--day", default="friday", choices=act.DAYS, help="The day whose hours are checked.")
    parser.add_argument("--start", default="17:00", help="Window start, HH:MM (24h).")
    parser.add_argument("--end", default="22:00", help="Window end, HH:MM (24h).")
    parser.add_argument("--radius-miles", type=float, default=20.0, help="Drop venues farther than this (straight-line).")
    parser.add_argument("--details", type=int, default=60, help="How many top venues get their place page read for hours.")
    parser.add_argument("--queries-file", default=None, help='A file of "tag<TAB>query" lines replacing the built-in list.')
    parser.add_argument("--check", action="store_true", help="Read-only: report each dependent selector as found or missing.")
    parser.add_argument("--apply", action="store_true", help=argparse.SUPPRESS)  # always refused: read-only errand
    parser.add_argument("--show", action="store_true", help="Keep the window visible.")
    parser.add_argument("--profile-dir", dest="profile_dir", default=None, help="Override HEADLESS_PROFILE_DIR.")
    parser.add_argument("--preview-dir", dest="preview_dir", default=None, help="Override HEADLESS_PREVIEW_DIR (reports/ resolves beside it).")
    return parser


def _load_queries(path: str | None) -> list[tuple[str, str]]:
    if not path:
        return list(act.DEFAULT_QUERIES)
    queries = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tag, _, query = line.partition("\t")
        if not query:
            tag, query = "custom", tag
        queries.append((tag.strip(), query.strip()))
    return queries


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def resolve_near(text: str, fetch=None) -> tuple[float, float] | None:
    point = act.parse_near(text)
    if point is not None:
        return point
    if act.looks_like_coordinates(text):
        return None  # a pair, but out of range: never sent to a geocoder as an address
    fetch = fetch or _fetch
    try:
        body = fetch(act.nominatim_url(text))
    except Exception:
        return None
    return act.parse_geocode_response(body)


# --- Browser reads (the only place a page is touched) ---------------------------


def _scroll_feed_to_end(page) -> None:
    feed = page.locator(act.FEED_SELECTOR).first
    previous = -1
    stale_passes = 0
    for _ in range(MAX_FEED_SCROLLS):
        count = page.locator(f"{act.FEED_SELECTOR} {act.PLACE_LINK_SELECTOR}").count()
        if page.get_by_text(act.END_OF_LIST_TEXT).count() > 0:
            return
        # One slow page must not truncate the list: give up only after two
        # scrolls in a row loaded nothing new (verifier finding 16, 2026-09-09).
        stale_passes = stale_passes + 1 if count == previous else 0
        if stale_passes >= 2:
            return
        previous = count
        feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
        page.wait_for_timeout(1500)


def read_search_page(page, tag: str, query: str) -> list[act.Venue]:
    """One loaded search page -> its result cards as Venues (no scoring yet)."""
    venues: list[act.Venue] = []
    feed = page.locator(act.FEED_SELECTOR)
    if feed.count() == 0:
        print(f"note: no results feed for '{query}' (selector missing)")
        return venues
    _scroll_feed_to_end(page)
    position = 0
    for card in feed.first.locator(":scope > div").all():
        link = card.locator(act.PLACE_LINK_SELECTOR)
        if link.count() == 0:
            continue
        href = link.first.get_attribute("href") or ""
        name = (link.first.get_attribute("aria-label") or "").strip()
        parsed = act.parse_card_lines((card.inner_text() or "").split("\n"))
        rating_pair = None
        rating_locator = card.locator(act.RATING_SELECTOR)
        if rating_locator.count() > 0:
            rating_pair = act.parse_rating_label(rating_locator.first.get_attribute("aria-label") or "")
        if rating_pair is None and parsed["rating"] is not None:
            rating_pair = (parsed["rating"], parsed["reviews"])
        coords = act.parse_place_href(href)
        venues.append(
            act.Venue(
                name=name or parsed["name"],
                url=href,
                tag=tag,
                query=query,
                position=position,
                lat=coords[0] if coords else None,
                lon=coords[1] if coords else None,
                rating=rating_pair[0] if rating_pair else None,
                reviews=rating_pair[1] if rating_pair else None,
                category=parsed["category"],
                address=parsed["address"],
                hours_today=parsed["hours_today"],
                sponsored=parsed["sponsored"],
            )
        )
        position += 1
    return venues


def read_single_place(page, tag: str, query: str) -> act.Venue:
    """A query Google answers by opening one place page directly (no results feed):
    that page is the whole result. Name from the title, coordinates from the URL's
    own viewport, rating from the header's star label when it carries a count."""
    title = page.title() or ""
    name = title.replace(" - Google Maps", "").strip() or query
    coords = act.parse_place_href(page.url)
    venue = act.Venue(
        name=name, url=page.url, tag=tag, query=query, position=0,
        lat=coords[0] if coords else None, lon=coords[1] if coords else None,
    )
    rating_locator = page.locator(act.RATING_SELECTOR)
    if rating_locator.count() > 0:
        pair = act.parse_rating_label(rating_locator.first.get_attribute("aria-label") or "")
        if pair:
            venue.rating, venue.reviews = pair
    read_place_page(page, venue)
    return venue


def read_place_page(page, venue: act.Venue) -> None:
    """One loaded place page -> weekly hours, website, phone, full address."""
    rows = [(row.inner_text() or "") for row in page.locator(act.HOURS_ROW_SELECTOR).all()]
    venue.weekly_hours = act.parse_weekly_rows(rows)
    website = page.locator(act.WEBSITE_SELECTOR)
    if website.count() > 0:
        venue.website = website.first.get_attribute("href") or ""
    phone = page.locator(act.PHONE_SELECTOR)
    if phone.count() > 0:
        venue.phone = act.strip_prefix(phone.first.get_attribute("aria-label") or "", "Phone:")
    address = page.locator(act.ADDRESS_SELECTOR)
    if address.count() > 0:
        full = act.strip_prefix(address.first.get_attribute("aria-label") or "", "Address:")
        if full:
            venue.address = full


def _settle(page, selector: str, timeout_ms: int) -> None:
    try:
        page.wait_for_selector(selector, timeout=timeout_ms)
    except Exception:
        pass  # fail-soft: the caller's own count() decides what to do


# --- Modes ---------------------------------------------------------------------


def run_check(session: Session, url: str) -> int:
    session.goto(url)
    _settle(session.page, act.FEED_SELECTOR, 15000)
    results = session.probe(list(act.CHECK_SELECTORS))
    for selector, found in results:
        print(f"  {'found  ' if found else 'MISSING'} {selector}")
    found_count = sum(1 for _, found in results if found)
    print(f"CHECK {found_count} found, {len(results) - found_count} missing")
    return 0


def run_scan(session: Session, args, near: tuple[float, float], area: str, queries, out_dir: Path) -> int:
    window = act.window_minutes(args.start, args.end)
    collected: list[act.Venue] = []
    for tag, query in queries:
        url = act.search_url(query, area)
        try:
            session.goto(url)
            _settle(session.page, act.FEED_SELECTOR, 15000)
            if session.page.locator(act.FEED_SELECTOR).count() == 0 and "/maps/place/" in session.page.url:
                found = [read_single_place(session.page, tag, query)]
                print(f"  '{query}': 1 result (Google opened the place directly)")
            else:
                found = read_search_page(session.page, tag, query)
                print(f"  '{query}': {len(found)} results")
        except Exception as exc:  # one query's page must never sink a 35-query scan
            print(f"note: query skipped for '{query}' ({type(exc).__name__})")
            continue
        collected.extend(found)

    venues = act.fold_duplicates(collected)
    act.locate(venues, near)
    ranked = act.rank(venues, args.radius_miles)

    for venue in ranked[: max(args.details, 0)]:
        try:
            session.goto(venue.url)
            _settle(session.page, act.HOURS_ROW_SELECTOR, 10000)
            read_place_page(session.page, venue)
        except Exception as exc:  # one venue's page must never sink the scan
            print(f"note: details skipped for '{venue.name}' ({type(exc).__name__})")
        act.apply_day_window(venue, args.day, window)
    ranked = act.rank(ranked, args.radius_miles)  # re-score with the day verdicts

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = generated_at[:10]
    out_dir.mkdir(parents=True, exist_ok=True)
    window_text = f"{args.start}-{args.end}"
    markdown = act.render_markdown(
        ranked, near_label=args.near, near=near, day=args.day, window_text=window_text,
        generated_at=generated_at, queries_run=len(queries),
    )
    payload = act.render_json(
        ranked, near=list(near), near_label=args.near, area=area, day=args.day,
        window=window_text, generated_at=generated_at, queries=[list(q) for q in queries],
    )
    md_path = out_dir / f"activity-scan-{stamp}.md"
    json_path = out_dir / f"activity-scan-{stamp}.json"
    for path, text in ((md_path, markdown), (json_path, payload)):
        # Same bracket as headless/capture.py: O_CREAT's mode applies only to a new
        # file, and a same-date rerun overwrites an existing one.
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # not there yet (the ordinary case) or Windows
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    print(f"SCAN {md_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.apply:
        print("REFUSED: activity_scan is read-only; there is no apply mode")
        return 1
    try:
        overrides: dict[str, object] = {}
        if args.profile_dir:
            overrides["profile_dir"] = args.profile_dir
        if args.preview_dir:
            overrides["preview_dir"] = args.preview_dir
        if args.show:
            overrides["show"] = True
        config = load_config(overrides)
        act.window_minutes(args.start, args.end)  # ValueError on a malformed HH:MM
        if args.start == args.end:
            raise ConfigError("--start and --end must differ")
        queries = _load_queries(args.queries_file)
        if not queries:
            raise ConfigError("no queries to run")
    except (ConfigError, ValueError, OSError) as exc:
        print(f"REFUSED: {exc}")
        return 1

    near = resolve_near(args.near)
    if near is None:
        print("REFUSED: --near could not be resolved to a point (use \"lat,lon\" or a fuller address)")
        return 1
    area = args.area or args.near
    out_dir = reports_dir_for(config) / "activity"

    try:
        with Session(config, Mode.PREVIEW) as session:
            if args.check:
                return run_check(session, act.search_url(queries[0][1], area))
            return run_scan(session, args, near, area, queries, out_dir)
    except GateRefused as exc:
        print(f"REFUSED: {exc}")
        return 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__} (rerun with HEADLESS_DEBUG=1 for the traceback)")
        if os.environ.get("HEADLESS_DEBUG") == "1":
            import traceback

            traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
