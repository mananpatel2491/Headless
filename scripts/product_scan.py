#!/usr/bin/env python3
"""product_scan: rank retail listings for a product query by price-per-foot and
rating (spec 011-product-scan).

Background: a listing the Director was sent (a Walmart lawn-edging listing, 4
inch tall, no-dig HDPE plastic roll with steel U-stakes, 40 ft for $31.58,
100 ft out of stock for $66.49) prompted the question of whether that pick is
the biggest bang for the buck, or whether spending more buys a product that
lasts longer. This errand generalizes that question to any product query: it
reads Amazon's search results (primary, on by default) and, opt-in, Home
Depot's, parses
each listing's title for its physical attributes (height, length, material,
stakes), scores by a Bayesian-shrunk rating minus a price-per-foot penalty,
and ranks by material tier. Walmart, Lowe's, Google Shopping, and Menards all
refuse headless Chrome (recon 2026-09-11: bot walls or blank/error pages), so
Walmart is read only as a `--reference-url`/`--reference` listing, never
searched, and Lowe's/Google Shopping/Menards are never read at all.

Site: `https://www.amazon.com/s?k=<query>&page=N` (primary) and, opt-in,
`https://www.homedepot.com/s/<query>` (`?Nao=24*(N-1)` for page N > 1); a
`--reference-url` product page on amazon.com or walmart.com.
Reads: search result cards/pods (title, price, rating, review count,
sponsored flag) and, for a reference URL, that product's own page.
Writes (up to): nothing on any site. Locally:
`reports/product/product-scan-<slug>-<date>.md` and `.json` (the query's own
slug precedes the UTC date, fix batch A5/B9, 2026-09-11; public retail data
only; the folder stays gitignored with the rest of `reports/`).
Secrets / profile fields: none - the vault is never opened.
Handoff: none; read-only, like `probe.py`/`activity_scan.py`. There is no
apply mode and none may be added. `--check` is the Lesson 4 live selector
probe.

Usage:
    python scripts/product_scan.py --query "no dig landscape edging"
        [--pages 2] [--sites amazon] [--reference-url URL]
        [--reference "Title | 31.58 | 40 | 4.1 | 15"] [--min-height-in 3]
        [--check] [--show] [--profile-dir PATH] [--preview-dir PATH]

Exit codes: 0 a report was written or `--check` completed; 1 a refusal (an
empty query, an unknown site, a `--pages` value out of range, a malformed
`--reference`, an unsupported `--reference-url` host, `--apply`); 2 a usage
error or an unhandled browser exception (`HEADLESS_DEBUG=1` for the
traceback).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from headless import products as prod
from headless.capture import reports_dir_for
from headless.config import ConfigError, load_config
from headless.gates import GateRefused, Mode
from headless.session import Session

HANDOFF = "n/a (read-only errand)"
MAX_HOMEDEPOT_SCROLLS = 6


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--query", required=True, help='The product search query, e.g. "no dig landscape edging".')
    parser.add_argument("--pages", type=int, default=2, help="Search result pages per site (1-5, default 2).")
    parser.add_argument("--sites", default="amazon", help="Comma list from: amazon, homedepot (default amazon).")
    parser.add_argument("--reference-url", dest="reference_url", default=None, help="The listing the Director was sent (amazon.com or walmart.com).")
    parser.add_argument("--reference", default=None, help='Hand-typed fallback: "Title | price | length_ft [| rating [| reviews]]".')
    parser.add_argument("--min-height-in", dest="min_height_in", type=float, default=None, help="Drop a ranked listing shorter than this (inches).")
    parser.add_argument("--check", action="store_true", help="Read-only: report each dependent selector as found or missing.")
    parser.add_argument("--apply", action="store_true", help=argparse.SUPPRESS)  # always refused: read-only errand
    parser.add_argument("--show", action="store_true", help="Keep the window visible.")
    parser.add_argument("--profile-dir", dest="profile_dir", default=None, help="Override HEADLESS_PROFILE_DIR.")
    parser.add_argument("--preview-dir", dest="preview_dir", default=None, help="Override HEADLESS_PREVIEW_DIR (reports/ resolves beside it).")
    return parser


def _clean_title(text: str) -> str:
    return (text or "").replace("​", "").strip()


def _fill_attributes(listing: prod.Listing) -> None:
    attributes = prod.parse_attributes(listing.title)
    for key, value in attributes.items():
        setattr(listing, key, value)
    listing.price_per_ft = prod.price_per_ft(listing.price, listing.length_ft)
    if listing.length_ft is not None and prod.pack_flag_applies(listing.title):
        listing.flags.append("pack: per-piece length")


# --- Browser reads (the only place a page is touched) ---------------------------


def read_amazon_search(page, page_number: int, start_position: int = 0) -> list[prod.Listing]:
    """One loaded Amazon search page -> its result cards as Listings.
    `position` is a running index per site across every page read (fix batch
    B15, 2026-09-11): the caller passes `start_position` continuing after the
    previous page's own last position, rather than resetting to 0 each page."""
    listings: list[prod.Listing] = []
    cards = page.locator(prod.AMAZON_CARD_SELECTOR)
    if cards.count() == 0:
        return listings
    for position, card in enumerate(cards.all(), start=start_position):
        title_locator = card.locator(prod.AMAZON_TITLE_SELECTOR)
        title = _clean_title(title_locator.first.inner_text()) if title_locator.count() else ""
        link = card.locator(prod.AMAZON_LINK_SELECTOR)
        if link.count() == 0:
            link = card.locator(prod.AMAZON_LINK_FALLBACK_SELECTOR)
        href = link.first.get_attribute("href") or "" if link.count() else ""
        url = prod.canonical_url("amazon", href, card.get_attribute("data-asin"))
        price_locator = card.locator(prod.AMAZON_PRICE_SELECTOR)
        price = prod.parse_price(price_locator.first.inner_text()) if price_locator.count() else None
        rating_locator = card.locator(prod.AMAZON_RATING_SELECTOR)
        rating = prod.parse_rating(rating_locator.first.inner_text()) if rating_locator.count() else None
        reviews_locator = card.locator(prod.AMAZON_REVIEWS_SELECTOR)
        if reviews_locator.count() == 0:
            reviews_locator = card.locator(prod.AMAZON_REVIEWS_FALLBACK_SELECTOR)
        reviews = prod.parse_count(reviews_locator.first.get_attribute("aria-label") or "") if reviews_locator.count() else None
        sponsored = card.locator(prod.AMAZON_SPONSORED_SELECTOR).count() > 0
        listing = prod.Listing(
            site="amazon", title=title, url=url, origin="search", price=price, rating=rating,
            reviews=reviews, position=position, page=page_number, sponsored=sponsored,
        )
        _fill_attributes(listing)
        listings.append(listing)
    return listings


def _scroll_homedepot_to_end(page) -> None:
    """Home Depot pods are lazy-loaded: scroll the whole page (not a feed
    element - there is no Home Depot equivalent to Google Maps' `role=feed`)
    up to `MAX_HOMEDEPOT_SCROLLS` times, stopping after two scrolls in a row
    that add no pods (the `activity_scan` stale-pass rule)."""
    previous = -1
    stale_passes = 0
    for _ in range(MAX_HOMEDEPOT_SCROLLS):
        count = page.locator(prod.HOMEDEPOT_POD_SELECTOR).count()
        stale_passes = stale_passes + 1 if count == previous else 0
        if stale_passes >= 2:
            return
        previous = count
        page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
        page.wait_for_timeout(1200)


def read_homedepot_search(page, page_number: int, start_position: int = 0) -> list[prod.Listing]:
    """One loaded Home Depot search page -> its result pods as Listings, folded
    by canonical URL (pods are duplicated in the DOM, recon 2026-09-11).
    `position` is a running index per site across every page read (fix batch
    B15, 2026-09-11), continuing after the previous page's own last position."""
    listings: list[prod.Listing] = []
    pods = page.locator(prod.HOMEDEPOT_POD_SELECTOR)
    if pods.count() == 0:
        return listings
    seen_urls: set[str] = set()
    position = start_position
    for pod in pods.all():
        header_locator = pod.locator(prod.HOMEDEPOT_HEADER_SELECTOR)
        title = _clean_title(header_locator.first.inner_text()) if header_locator.count() else ""
        link = pod.locator(prod.HOMEDEPOT_LINK_SELECTOR)
        href = link.first.get_attribute("href") or "" if link.count() else ""
        url = prod.canonical_url("homedepot", href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        price_locator = pod.locator(prod.HOMEDEPOT_PRICE_SELECTOR)
        price = prod.parse_price(price_locator.first.inner_text()) if price_locator.count() else None
        rating_locator = pod.locator(prod.HOMEDEPOT_RATING_SELECTOR)
        rating, reviews = (None, None)
        if rating_locator.count():
            pair = prod.parse_rating_and_count(rating_locator.first.inner_text())
            if pair:
                rating, reviews = pair
        listing = prod.Listing(
            site="homedepot", title=title, url=url, origin="search", price=price,
            rating=rating, reviews=reviews, position=position, page=page_number,
        )
        _fill_attributes(listing)
        listings.append(listing)
        position += 1
    return listings


def read_amazon_product(page) -> prod.Listing | None:
    """The reference reader for an `amazon.com` `--reference-url` (verified on
    `/dp/B01MG4ARN7`)."""
    title_locator = page.locator(prod.AMAZON_PRODUCT_TITLE_SELECTOR)
    if title_locator.count() == 0:
        return None
    title = _clean_title(title_locator.first.inner_text())
    price_locator = page.locator(prod.AMAZON_PRODUCT_PRICE_SELECTOR)
    price = prod.parse_price(price_locator.first.inner_text()) if price_locator.count() else None
    rating_locator = page.locator(prod.AMAZON_PRODUCT_RATING_SELECTOR)
    rating = None
    if rating_locator.count():
        rating = prod.parse_rating(rating_locator.first.get_attribute("title") or "")
    reviews_locator = page.locator(prod.AMAZON_PRODUCT_REVIEWS_SELECTOR)
    reviews = prod.parse_count(reviews_locator.first.inner_text()) if reviews_locator.count() else None
    listing = prod.Listing(site="amazon", title=title, url=page.url, origin="reference-url", price=price, rating=rating, reviews=reviews)
    _fill_attributes(listing)
    return listing


_WALMART_REVIEW_COUNT_RE = re.compile(r"(\d[\d,]*)\s+ratings?", re.IGNORECASE)


def read_walmart_product(page) -> prod.Listing | None:
    """The reference reader for a `walmart.com` `--reference-url` - headed
    only per recon 2026-09-11 (never verified under headless Playwright; a bot
    wall is the expected outcome and is handled by the caller via
    `products.wall_reason` before this is ever invoked)."""
    title_locator = page.locator(prod.WALMART_TITLE_SELECTOR)
    if title_locator.count() == 0:
        return None
    title = _clean_title(title_locator.first.inner_text())
    price_locator = page.locator(prod.WALMART_PRICE_SELECTOR)
    price = prod.parse_price(price_locator.first.inner_text()) if price_locator.count() else None
    rating_locator = page.locator(prod.WALMART_RATING_SELECTOR)
    rating = prod.parse_rating(rating_locator.first.inner_text()) if rating_locator.count() else None
    reviews = None
    body_locator = page.locator("body")
    if body_locator.count():
        match = _WALMART_REVIEW_COUNT_RE.search(body_locator.first.inner_text() or "")
        if match:
            reviews = int(match.group(1).replace(",", ""))
    listing = prod.Listing(site="walmart", title=title, url=page.url, origin="reference-url", price=price, rating=rating, reviews=reviews)
    _fill_attributes(listing)
    return listing


def _settle(page, selector: str, timeout_ms: int) -> None:
    try:
        page.wait_for_selector(selector, timeout=timeout_ms)
    except Exception:
        pass  # fail-soft: the caller's own count() decides what to do


# --- Modes ---------------------------------------------------------------------


def run_check(session: Session, query: str, sites: list[str]) -> int:
    total_found = 0
    total_selectors = 0
    for site in sites:
        print(f"  {site}:")
        session.goto(prod.search_url(site, query, 1))
        selectors = list(prod.CHECK_SELECTORS[site])
        _settle(session.page, selectors[0], 15000)
        for selector, found in session.probe(selectors):
            print(f"    {'found  ' if found else 'MISSING'} {selector}")
            total_selectors += 1
            total_found += 1 if found else 0
    print(f"CHECK {total_found} found, {total_selectors - total_found} missing")
    return 0


def run_scan(
    session: Session,
    sites: list[str],
    query: str,
    pages: int,
    min_height_in: float | None,
    reference_url: str | None,
    reference_site: str | None,
    reference_literal: prod.Listing | None,
    out_dir: Path,
) -> int:
    notes: list[str] = []

    def _note(text: str) -> None:
        print(text)
        notes.append(text)

    collected: list[prod.Listing] = []
    total_read = 0
    position_by_site: dict[str, int] = {}
    for site in sites:
        for page_number in range(1, pages + 1):
            try:
                session.goto(prod.search_url(site, query, page_number))
                _settle(session.page, prod.CHECK_SELECTORS[site][0], 15000)
                reason = prod.wall_reason(session.page.title() or "", session.page.url)
                if reason:
                    _note(f"note: page skipped for '{site} p{page_number}' (wall: {reason})")
                    break  # a wall on this page means the rest of this site's pages are skipped too
                start_position = position_by_site.get(site, 0)
                if site == "homedepot":
                    _scroll_homedepot_to_end(session.page)
                    found = read_homedepot_search(session.page, page_number, start_position)
                else:
                    found = read_amazon_search(session.page, page_number, start_position)
                print(f"  '{site}' p{page_number}: {len(found)} results")
                position_by_site[site] = start_position + len(found)
                if not found:
                    _note(f"note: page skipped for '{site} p{page_number}' (zero cards)")
            except Exception as exc:  # one page's failure must never sink the scan
                _note(f"note: page skipped for '{site} p{page_number}' ({type(exc).__name__})")
                continue
            total_read += len(found)
            collected.extend(found)

    unique_after_fold = prod.fold_duplicates(collected)
    listings = unique_after_fold

    reference = None
    if reference_url:
        try:
            session.goto(reference_url)
            _settle(session.page, "body", 15000)
            reason = prod.wall_reason(session.page.title() or "", session.page.url)
            if reason:
                _note("note: reference not readable headless (bot wall) - rerun with --show")
            elif reference_site == "amazon":
                reference = read_amazon_product(session.page)
            elif reference_site == "walmart":
                reference = read_walmart_product(session.page)
        except Exception:
            _note("note: reference not readable headless (bot wall) - rerun with --show")
    if reference is None and reference_literal is not None:
        reference = reference_literal

    for listing in listings:
        listing.score = prod.score_listing(listing)
    if reference is not None:
        reference.score = prod.score_listing(reference)

    rank_result = prod.rank(listings, min_height_in)
    ranked_count = sum(len(group) for group in rank_result.tiers.values())

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = generated_at[:10]
    slug = prod.slugify(query)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "query": query,
        "sites": sites,
        "pages": pages,
        "generated_at": generated_at,
        "read": total_read,
        "unique": len(unique_after_fold),
        "excluded": len(rank_result.excluded),
        "dropped_by_height": len(rank_result.dropped_by_height),
        "ranked": ranked_count,
        "notes": notes,
    }
    markdown = prod.render_markdown(rank_result, reference, meta)
    payload = prod.render_json(rank_result, reference, meta)
    md_path = out_dir / f"product-scan-{slug}-{stamp}.md"
    json_path = out_dir / f"product-scan-{slug}-{stamp}.json"
    for path, text in ((md_path, markdown), (json_path, payload)):
        # Same bracket as headless/capture.py and activity_scan.py: O_CREAT's
        # mode applies only to a new file, and a same-date rerun overwrites.
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
        print("REFUSED: product_scan is read-only; there is no apply mode")
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

        query = (args.query or "").strip()
        if not query:
            raise ConfigError("--query must not be empty")

        if not (1 <= args.pages <= 5):
            raise ConfigError("--pages must be between 1 and 5")

        sites = [site.strip() for site in args.sites.split(",") if site.strip()]
        if not sites:
            raise ConfigError("--sites must not be empty")
        for site in sites:
            if site not in prod.SITES:
                raise ConfigError(f"unknown site '{site}' (known: {', '.join(prod.SITES)})")

        reference_literal = None
        if args.reference:
            try:
                reference_literal = prod.parse_reference_literal(args.reference)
            except ValueError as exc:
                raise ConfigError(str(exc)) from exc

        reference_site = None
        if args.reference_url:
            host = urlparse(args.reference_url).netloc
            reference_site = prod.REFERENCE_HOSTS.get(host)
            if reference_site is None:
                raise ConfigError(f"unsupported reference host {host!r}")
    except (ConfigError, ValueError, OSError) as exc:
        print(f"REFUSED: {exc}")
        return 1

    out_dir = reports_dir_for(config) / "product"

    try:
        with Session(config, Mode.PREVIEW) as session:
            if args.check:
                return run_check(session, query, sites)
            return run_scan(
                session, sites, query, args.pages, args.min_height_in,
                args.reference_url, reference_site, reference_literal, out_dir,
            )
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
