"""Unit tests for scripts/product_scan.py (spec 011-product-scan): the CLI's own
refusals, the check mode, and the scan pipeline with the browser-reading
functions faked, modeled on tests/test_activity_scan.py's fakes. Never a real
`Session`, never a network call, never a visible browser.
"""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.product_scan as product_scan
from headless import products as prod
from headless.gates import GateRefused, Mode


class FakeLocator:
    """A tiny stand-in for a Playwright Locator: a fixed list of elements, each a
    dict of attribute -> value, an optional "text", and an optional "sub"
    mapping of selector -> child elements for nested `locator()` calls."""

    def __init__(self, elements):
        self._elements = list(elements)

    def count(self):
        return len(self._elements)

    @property
    def first(self):
        return FakeLocator(self._elements[:1])

    def all(self):
        return [FakeLocator([element]) for element in self._elements]

    def get_attribute(self, name):
        return self._elements[0].get(name) if self._elements else None

    def inner_text(self):
        return self._elements[0].get("text", "") if self._elements else ""

    def locator(self, selector):
        if not self._elements:
            return FakeLocator([])
        return FakeLocator(self._elements[0].get("sub", {}).get(selector, []))


class FakePage:
    def __init__(self, url="https://www.amazon.com/s?k=x&page=1", title="Amazon.com : x", elements=None):
        self.url = url
        self._title = title
        # selector -> elements; an unregistered selector resolves to nothing, so a
        # test must register every element it expects the script to find.
        self._elements = elements if elements is not None else {}
        self.evaluate_calls: list[str] = []
        self.waits: list[int] = []

    def title(self):
        return self._title

    def wait_for_selector(self, selector, timeout=0):
        return None

    def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)

    def locator(self, selector):
        return FakeLocator(self._elements.get(selector, []))

    def evaluate(self, script):
        self.evaluate_calls.append(script)


class FakeSession:
    instances: list["FakeSession"] = []

    def __init__(self, config, mode, **kwargs):
        self.config = config
        self.mode = mode
        self.goto_calls: list[str] = []
        self.page = FakePage()
        FakeSession.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def goto(self, url):
        self.goto_calls.append(url)

    def probe(self, selectors):
        return [(selector, selector != "#never") for selector in selectors]


class RefusingSession:
    def __init__(self, *args, **kwargs):
        raise AssertionError("no Session may be constructed on this path")


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    FakeSession.instances.clear()
    monkeypatch.setenv("HEADLESS_PREVIEW_DIR", str(tmp_path / "previews"))
    monkeypatch.setenv("HEADLESS_PROFILE_DIR", str(tmp_path / "profile"))
    monkeypatch.setattr(product_scan, "Session", FakeSession)
    yield
    FakeSession.instances.clear()


def _filled(**overrides) -> prod.Listing:
    """A faithful mirror of the script's own `_fill_attributes`, so a fake
    search-read helper can stand in for the real `read_amazon_search`
    without losing the pack-flag step (fix batch A6)."""
    base = dict(site="amazon", title="Sample No Dig Landscape Edging Plastic 40 ft", url="https://www.amazon.com/dp/AAAAAAAAAA", origin="search")
    base.update(overrides)
    listing = prod.Listing(**base)
    attrs = prod.parse_attributes(listing.title)
    for key, value in attrs.items():
        setattr(listing, key, value)
    listing.price_per_ft = prod.price_per_ft(listing.price, listing.length_ft)
    if listing.length_ft is not None and prod.is_pack(listing.title):
        listing.flags.append("pack: per-piece length")
    return listing


# --- refusals before any Session ------------------------------------------------


def test_apply_is_refused_before_any_session(monkeypatch, capsys):
    monkeypatch.setattr(product_scan, "Session", RefusingSession)
    assert product_scan.main(["--query", "x", "--apply"]) == 1
    assert "REFUSED: product_scan is read-only; there is no apply mode" in capsys.readouterr().out


def test_empty_query_refused_before_any_session(monkeypatch, capsys):
    monkeypatch.setattr(product_scan, "Session", RefusingSession)
    assert product_scan.main(["--query", "   "]) == 1
    assert "REFUSED: --query must not be empty" in capsys.readouterr().out


def test_unknown_site_refused_before_any_session(monkeypatch, capsys):
    monkeypatch.setattr(product_scan, "Session", RefusingSession)
    assert product_scan.main(["--query", "x", "--sites", "target"]) == 1
    assert "REFUSED: unknown site 'target' (known: amazon, homedepot)" in capsys.readouterr().out


def test_bad_pages_range_refused_before_any_session(monkeypatch, capsys):
    monkeypatch.setattr(product_scan, "Session", RefusingSession)
    assert product_scan.main(["--query", "x", "--pages", "6"]) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert product_scan.main(["--query", "x", "--pages", "0"]) == 1


def test_bad_literal_reference_refused_before_any_session(monkeypatch, capsys):
    monkeypatch.setattr(product_scan, "Session", RefusingSession)
    assert product_scan.main(["--query", "x", "--reference", "not a valid literal"]) == 1
    assert "REFUSED" in capsys.readouterr().out


def test_unsupported_reference_host_refused_before_any_session(monkeypatch, capsys):
    monkeypatch.setattr(product_scan, "Session", RefusingSession)
    assert product_scan.main(["--query", "x", "--reference-url", "https://www.lowes.com/x"]) == 1
    assert "REFUSED: unsupported reference host" in capsys.readouterr().out


def test_gate_refused_from_the_session_exits_one(monkeypatch, capsys):
    class RefusedSession(FakeSession):
        def __enter__(self):
            raise GateRefused("profile in use")

    monkeypatch.setattr(product_scan, "Session", RefusedSession)
    assert product_scan.main(["--query", "x", "--check"]) == 1
    assert "REFUSED: profile in use" in capsys.readouterr().out


def test_browser_failure_exits_two_with_class_name_only_and_debug_traceback(monkeypatch, capsys):
    class ExplodingSession(FakeSession):
        def __enter__(self):
            raise RuntimeError("DISTINCTIVE-STACK-TRACE-SHOULD-NEVER-APPEAR")

    monkeypatch.setattr(product_scan, "Session", ExplodingSession)
    assert product_scan.main(["--query", "x", "--check"]) == 2
    captured = capsys.readouterr()
    assert "ERROR: RuntimeError (rerun with HEADLESS_DEBUG=1 for the traceback)" in captured.out
    assert "DISTINCTIVE-STACK-TRACE-SHOULD-NEVER-APPEAR" not in captured.out
    assert captured.err == ""
    monkeypatch.setenv("HEADLESS_DEBUG", "1")
    assert product_scan.main(["--query", "x", "--check"]) == 2
    assert "RuntimeError" in capsys.readouterr().err


# --- check mode -------------------------------------------------------------------


def test_check_mode_probes_the_live_selectors(tmp_path, capsys):
    assert product_scan.main(["--query", "no dig landscape edging", "--check"]) == 0
    out = capsys.readouterr().out
    assert "CHECK 4 found, 0 missing" in out
    session = FakeSession.instances[0]
    assert session.mode is Mode.PREVIEW
    assert session.goto_calls == [prod.search_url("amazon", "no dig landscape edging", 1)]
    assert not (tmp_path / "reports").exists()  # check mode writes no report


def test_check_mode_multiple_sites(capsys):
    assert product_scan.main(["--query", "x", "--sites", "amazon,homedepot", "--check"]) == 0
    out = capsys.readouterr().out
    assert "CHECK 8 found, 0 missing" in out
    session = FakeSession.instances[0]
    assert session.goto_calls == [prod.search_url("amazon", "x", 1), prod.search_url("homedepot", "x", 1)]


def test_check_mode_reports_a_missing_selector_and_still_exits_zero(monkeypatch, capsys):
    class PartialSession(FakeSession):
        def probe(self, selectors):
            return [(selector, selector == prod.AMAZON_CARD_SELECTOR) for selector in selectors]

    monkeypatch.setattr(product_scan, "Session", PartialSession)
    assert product_scan.main(["--query", "x", "--check"]) == 0
    out = capsys.readouterr().out
    # fix batch B10, 2026-09-11: --check's dependent selectors are card-scoped
    # compounds, not the bare page-level selector.
    assert f"MISSING {prod.CHECK_SELECTORS['amazon'][1]}" in out
    assert "CHECK 1 found, 3 missing" in out


def test_check_selectors_are_card_scoped_not_page_level():
    # fix batch B10: a page-level `h2 span` can resolve against something
    # that is not inside a search-result card at all - every selector past
    # the card/pod itself must be a descendant of it.
    amazon_card, amazon_title, amazon_price, amazon_rating = prod.CHECK_SELECTORS["amazon"]
    assert amazon_card == prod.AMAZON_CARD_SELECTOR
    for selector in (amazon_title, amazon_price, amazon_rating):
        assert selector.startswith(prod.AMAZON_CARD_SELECTOR + " ")
    hd_pod, hd_header, hd_price, hd_rating = prod.CHECK_SELECTORS["homedepot"]
    assert hd_pod == prod.HOMEDEPOT_POD_SELECTOR
    for selector in (hd_header, hd_price, hd_rating):
        assert selector.startswith(prod.HOMEDEPOT_POD_SELECTOR + " ")


# --- read_amazon_search / read_homedepot_search -----------------------------------


def _amazon_card(title, href, price_text, rating_text=None, reviews_label=None, sponsored=False, data_asin=None):
    sub = {
        prod.AMAZON_TITLE_SELECTOR: [{"text": title}],
        prod.AMAZON_LINK_SELECTOR: [{"href": href}],
        prod.AMAZON_PRICE_SELECTOR: [{"text": price_text}],
    }
    if rating_text:
        sub[prod.AMAZON_RATING_SELECTOR] = [{"text": rating_text}]
    if reviews_label:
        sub[prod.AMAZON_REVIEWS_SELECTOR] = [{"aria-label": reviews_label}]
    if sponsored:
        sub[prod.AMAZON_SPONSORED_SELECTOR] = [{}]
    element = {"sub": sub}
    if data_asin:
        element["data-asin"] = data_asin
    return element


def test_read_amazon_search_maps_cards_to_listings_with_attributes():
    card = _amazon_card(
        "Bluepro Landscape Edging, 2 Inch 100 ft Garden Border Edging | 150 Steel Stakes",
        "/Bluepro-Landscape-Edging/dp/B0G4H2C41Y/ref=sr_1_1",
        "$43.99",
        rating_text="4.5 out of 5 stars",
        reviews_label="158 ratings",
    )
    page = FakePage(elements={prod.AMAZON_CARD_SELECTOR: [card]})
    listings = product_scan.read_amazon_search(page, 1)
    assert len(listings) == 1
    listing = listings[0]
    assert listing.title.startswith("Bluepro")
    assert listing.url == "https://www.amazon.com/dp/B0G4H2C41Y"
    assert listing.price == 43.99
    assert (listing.rating, listing.reviews) == (4.5, 158)
    assert listing.height_in == 2.0 and listing.length_ft == 100.0
    assert listing.stake_count == 150 and listing.stake_material == "steel"
    assert listing.sponsored is False and listing.position == 0 and listing.page == 1


def test_read_amazon_search_sponsored_flag_and_fallback_link_and_data_asin():
    card = {
        "sub": {
            prod.AMAZON_TITLE_SELECTOR: [{"text": "Some Sponsored No Dig Landscape Edging 20 ft"}],
            prod.AMAZON_LINK_FALLBACK_SELECTOR: [{"href": "/x/ref=sr_1_1?no_asin_here"}],
            prod.AMAZON_PRICE_SELECTOR: [{"text": "$19.99"}],
            prod.AMAZON_SPONSORED_SELECTOR: [{}],
        },
        "data-asin": "B000000000",
    }
    page = FakePage(elements={prod.AMAZON_CARD_SELECTOR: [card]})
    listings = product_scan.read_amazon_search(page, 1)
    assert listings[0].sponsored is True
    assert listings[0].url == "https://www.amazon.com/dp/B000000000"


def test_read_amazon_search_no_cards_returns_empty_and_prints_nothing_itself(capsys):
    # fix batch B3 (FR-009), 2026-09-11: the "zero cards" note is a run_scan
    # responsibility now (so it can also land in the report's own Notes
    # section) - read_amazon_search itself stays silent and just returns [].
    page = FakePage(elements={})
    assert product_scan.read_amazon_search(page, 1) == []
    assert capsys.readouterr().out == ""


def test_read_amazon_search_position_continues_across_pages():
    # fix batch B15, 2026-09-11: position is a running index per site across
    # every page, not reset to 0 each page.
    card_a = _amazon_card("Card A No Dig Plastic Edging 40 ft", "/dp/AAAAAAAAAA", "$10.00")
    card_b = _amazon_card("Card B No Dig Plastic Edging 40 ft", "/dp/BBBBBBBBBB", "$10.00")
    page1 = FakePage(elements={prod.AMAZON_CARD_SELECTOR: [card_a]})
    page2 = FakePage(elements={prod.AMAZON_CARD_SELECTOR: [card_b]})
    first = product_scan.read_amazon_search(page1, 1, start_position=0)
    second = product_scan.read_amazon_search(page2, 2, start_position=len(first))
    assert first[0].position == 0
    assert second[0].position == 1


def _hd_pod(title, href, price_text, rating_text=None):
    sub = {
        prod.HOMEDEPOT_HEADER_SELECTOR: [{"text": title}],
        prod.HOMEDEPOT_LINK_SELECTOR: [{"href": href}],
        prod.HOMEDEPOT_PRICE_SELECTOR: [{"text": price_text}],
    }
    if rating_text:
        sub[prod.HOMEDEPOT_RATING_SELECTOR] = [{"text": rating_text}]
    return {"sub": sub}


def test_read_homedepot_search_dedupes_duplicated_pods_by_canonical_url():
    pod = _hd_pod(
        "Vigoro60 ft.​ No-​Dig Plastic Landscape Edging Kit",
        "/p/Vigoro-60-ft-No-Dig-Plastic-Landscape-Edging-Kit-3001-60HD-3/301459392",
        "$\n41\n.\n97",
        rating_text="(4.5 /\xa04091)",
    )
    page = FakePage(elements={prod.HOMEDEPOT_POD_SELECTOR: [pod, pod]})
    listings = product_scan.read_homedepot_search(page, 1)
    assert len(listings) == 1  # the DOM's own duplicate pod is folded, not double-counted
    listing = listings[0]
    assert listing.title == "Vigoro60 ft. No-Dig Plastic Landscape Edging Kit"
    assert listing.price == 41.97
    assert (listing.rating, listing.reviews) == (4.5, 4091)
    assert listing.length_ft == 60.0


def test_read_homedepot_search_24_pods_12_unique_folds_to_12_listings():
    # fix batch B18, 2026-09-11 (tasks.md correction): the exact DOM-duplication
    # shape recon 2026-09-11 observed - 24 pods, 12 unique hrefs - folds to 12,
    # not just a toy 2-pods-to-1 case.
    pods = []
    for index in range(12):
        pod = _hd_pod(
            f"Product {index} No Dig Plastic Edging 40 ft",
            f"/p/product-{index}/{1000 + index}",
            "$41.97",
        )
        pods.append(pod)
        pods.append(pod)  # each pod duplicated once in the DOM
    assert len(pods) == 24
    page = FakePage(elements={prod.HOMEDEPOT_POD_SELECTOR: pods})
    listings = product_scan.read_homedepot_search(page, 1)
    assert len(listings) == 12
    folded = prod.fold_duplicates(listings)
    assert len(folded) == 12


def test_read_homedepot_search_no_pods_returns_empty_and_prints_nothing_itself(capsys):
    page = FakePage(elements={})
    assert product_scan.read_homedepot_search(page, 1) == []
    assert capsys.readouterr().out == ""


def test_read_homedepot_search_position_continues_across_pages():
    pod_a = _hd_pod("Pod A", "/p/pod-a/1", "$10.00")
    pod_b = _hd_pod("Pod B", "/p/pod-b/2", "$10.00")
    page1 = FakePage(elements={prod.HOMEDEPOT_POD_SELECTOR: [pod_a]})
    page2 = FakePage(elements={prod.HOMEDEPOT_POD_SELECTOR: [pod_b]})
    first = product_scan.read_homedepot_search(page1, 1, start_position=0)
    second = product_scan.read_homedepot_search(page2, 2, start_position=len(first))
    assert first[0].position == 0
    assert second[0].position == 1


def test_homedepot_scroll_stops_after_two_stale_scrolls():
    class StuckPage(FakePage):
        def locator(self, selector):
            if selector == prod.HOMEDEPOT_POD_SELECTOR:
                return FakeLocator([{}] * 2)  # never grows
            return super().locator(selector)

    page = StuckPage()
    product_scan._scroll_homedepot_to_end(page)
    assert len(page.evaluate_calls) == 2
    assert all("scrollBy" in call for call in page.evaluate_calls)
    assert page.waits == [1200, 1200]


def test_homedepot_scroll_continues_while_pods_keep_growing():
    class GrowingPage(FakePage):
        def __init__(self):
            super().__init__()
            self._counts = iter([2, 4, 4, 4, 4, 4, 4, 4])

        def locator(self, selector):
            if selector == prod.HOMEDEPOT_POD_SELECTOR:
                return FakeLocator([{}] * next(self._counts))
            return super().locator(selector)

    page = GrowingPage()
    product_scan._scroll_homedepot_to_end(page)
    assert len(page.evaluate_calls) == 3  # one growth step buys one more scroll


# --- read_amazon_product / read_walmart_product -----------------------------------


def test_read_amazon_product_reads_reference_fields():
    page = FakePage(
        url="https://www.amazon.com/dp/B01MG4ARN7",
        elements={
            prod.AMAZON_PRODUCT_TITLE_SELECTOR: [{"text": "EasyFlex Heavy Duty No-Dig Edging Kit - 100ft., Black"}],
            prod.AMAZON_PRODUCT_PRICE_SELECTOR: [{"text": "$44.37"}],
            prod.AMAZON_PRODUCT_RATING_SELECTOR: [{"title": "4.5 out of 5 stars"}],
            prod.AMAZON_PRODUCT_REVIEWS_SELECTOR: [{"text": "(5,118)"}],
        },
    )
    listing = product_scan.read_amazon_product(page)
    assert listing.origin == "reference-url" and listing.site == "amazon"
    assert listing.price == 44.37
    assert (listing.rating, listing.reviews) == (4.5, 5118)
    assert listing.length_ft == 100.0


def test_read_amazon_product_missing_title_returns_none():
    assert product_scan.read_amazon_product(FakePage(elements={})) is None


def test_read_walmart_product_reads_reference_fields_including_body_review_count():
    page = FakePage(
        url="https://www.walmart.com/ip/18656266943",
        elements={
            prod.WALMART_TITLE_SELECTOR: [{"text": "BSHAPPLUS 4in x 40ft No Dig Landscape Edging Kit"}],
            prod.WALMART_PRICE_SELECTOR: [{"text": "$66.49"}],
            prod.WALMART_RATING_SELECTOR: [{"text": "(4.1)"}],
            "body": [{"text": "4.1 out of 5 Stars. 15 ratings"}],
        },
    )
    listing = product_scan.read_walmart_product(page)
    assert listing.site == "walmart" and listing.origin == "reference-url"
    assert listing.price == 66.49
    assert listing.rating == 4.1
    assert listing.reviews == 15
    assert listing.height_in == 4.0 and listing.length_ft == 40.0


def test_read_walmart_product_missing_title_returns_none():
    assert product_scan.read_walmart_product(FakePage(elements={})) is None


# --- scan pipeline -----------------------------------------------------------------


def test_scan_writes_markdown_and_json_reports_at_0600(monkeypatch, tmp_path, capsys):
    def fake_amazon_search(page, page_number, start_position=0):
        return [_filled(title="Bluepro 2 Inch 100 ft No Dig Landscape Edging Plastic", price=43.99, rating=4.5, reviews=158, position=start_position, page=page_number)]

    monkeypatch.setattr(product_scan, "read_amazon_search", fake_amazon_search)
    exit_code = product_scan.main(["--query", "no dig landscape edging", "--pages", "1"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "SCAN " in out
    reports = tmp_path / "reports" / "product"
    md_files = sorted(reports.glob("product-scan-*.md"))
    json_files = sorted(reports.glob("product-scan-*.json"))
    assert len(md_files) == 1 and len(json_files) == 1
    for path in (md_files[0], json_files[0]):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # A same-date rerun over files whose mode drifted must restore 0600.
    for path in (md_files[0], json_files[0]):
        path.chmod(0o644)
    assert product_scan.main(["--query", "no dig landscape edging", "--pages", "1"]) == 0
    assert sorted(reports.glob("product-scan-*.md")) == md_files  # overwritten, not duplicated
    for path in (md_files[0], json_files[0]):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["meta"]["query"] == "no dig landscape edging"
    assert payload["tiers"]["plastic"][0]["title"].startswith("Bluepro")
    # fix batch A5, 2026-09-11: the file name carries the query's own slug.
    assert md_files[0].name.startswith("product-scan-no-dig-landscape-edging-")


def test_two_different_queries_the_same_day_do_not_overwrite_each_other(monkeypatch, tmp_path):
    # fix batch A5/B9, 2026-09-11: the slug goes BEFORE the date, so two
    # different queries scanned the same UTC day get two different file
    # pairs instead of one clobbering the other.
    monkeypatch.setattr(product_scan, "read_amazon_search", lambda page, page_number, start_position=0: [])
    assert product_scan.main(["--query", "no dig landscape edging", "--pages", "1"]) == 0
    assert product_scan.main(["--query", "4 inch tall landscape edging", "--pages", "1"]) == 0
    reports = tmp_path / "reports" / "product"
    md_files = sorted(path.name for path in reports.glob("product-scan-*.md"))
    assert md_files == sorted([
        next(name for name in md_files if "no-dig" in name),
        next(name for name in md_files if "4-inch-tall" in name),
    ])
    assert len(md_files) == 2


def test_wall_on_page_1_skips_that_sites_remaining_pages(monkeypatch, capsys):
    class WalledSession(FakeSession):
        def goto(self, url):
            super().goto(url)
            self.page = FakePage(url=url, title="Access Denied")

    monkeypatch.setattr(product_scan, "Session", WalledSession)
    assert product_scan.main(["--query", "x", "--pages", "3"]) == 0
    out = capsys.readouterr().out
    # fix batch B3, 2026-09-11: SPEC wins - the wall note carries a "wall: " prefix.
    assert "note: page skipped for 'amazon p1' (wall: Access Denied)" in out
    session = FakeSession.instances[0]
    assert session.goto_calls == [prod.search_url("amazon", "x", 1)]  # p2/p3 never visited


def test_multi_site_run_homedepot_walls_and_amazon_continues(monkeypatch, tmp_path, capsys):
    # fix batch B18, 2026-09-11 (tasks.md addition): a wall on ONE selected
    # site (Home Depot) must never affect a DIFFERENT selected site's own
    # results (Amazon) in the same multi-site run.
    class MultiSiteSession(FakeSession):
        def goto(self, url):
            super().goto(url)
            if "homedepot.com" in url:
                self.page = FakePage(url=url, title="Error Page")
            else:
                self.page = FakePage(url=url, title="Amazon.com : x")

    monkeypatch.setattr(product_scan, "Session", MultiSiteSession)
    monkeypatch.setattr(
        product_scan, "read_amazon_search",
        lambda page, page_number, start_position=0: [_filled(title="Amazon Survivor No Dig Landscape Edging Plastic 40 ft", price=30.0, rating=4.5, reviews=40, position=start_position, page=page_number)],
    )
    assert product_scan.main(["--query", "x", "--sites", "amazon,homedepot", "--pages", "1"]) == 0
    out = capsys.readouterr().out
    assert "note: page skipped for 'homedepot p1' (wall: Error Page)" in out
    reports = tmp_path / "reports" / "product"
    payload = json.loads(next(reports.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["tiers"]["plastic"][0]["title"].startswith("Amazon Survivor")


def test_one_page_exception_is_skipped_and_the_scan_still_writes_a_report(monkeypatch, tmp_path, capsys):
    class FlakySession(FakeSession):
        def goto(self, url):
            super().goto(url)
            if "page=1" in url:
                raise RuntimeError("navigation failed")

    monkeypatch.setattr(product_scan, "Session", FlakySession)
    monkeypatch.setattr(
        product_scan, "read_amazon_search",
        lambda page, page_number, start_position=0: [_filled(title="Survivor No Dig Landscape Edging Plastic 40 ft", price=30.0, rating=4.5, reviews=40, position=start_position, page=page_number)],
    )
    assert product_scan.main(["--query", "x", "--pages", "2"]) == 0
    out = capsys.readouterr().out
    assert "note: page skipped for 'amazon p1' (RuntimeError)" in out
    reports = tmp_path / "reports" / "product"
    payload = json.loads(next(reports.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["tiers"]["plastic"][0]["title"].startswith("Survivor")


def test_zero_cards_page_prints_a_note_and_it_lands_in_the_report(monkeypatch, tmp_path, capsys):
    # fix batch B3 (FR-009), 2026-09-11: a page with zero cards/pods prints
    # `note: page skipped for '<site> p<N>' (zero cards)` and that note
    # reaches the written report's own Notes section.
    monkeypatch.setattr(product_scan, "read_amazon_search", lambda page, page_number, start_position=0: [])
    assert product_scan.main(["--query", "x", "--pages", "1"]) == 0
    out = capsys.readouterr().out
    assert "note: page skipped for 'amazon p1' (zero cards)" in out
    reports = tmp_path / "reports" / "product"
    payload = json.loads(next(reports.glob("*.json")).read_text(encoding="utf-8"))
    assert "note: page skipped for 'amazon p1' (zero cards)" in payload["meta"]["notes"]


def test_reference_url_wall_falls_back_to_literal(monkeypatch, tmp_path, capsys):
    class WalledRefSession(FakeSession):
        def goto(self, url):
            super().goto(url)
            if "walmart.com" in url:
                self.page = FakePage(url=url, title="Robot or human?")
            else:
                self.page = FakePage(url=url, title="Amazon.com : x", elements={})

    monkeypatch.setattr(product_scan, "Session", WalledRefSession)
    monkeypatch.setattr(product_scan, "read_amazon_search", lambda page, page_number, start_position=0: [])
    args = [
        "--query", "x",
        "--reference-url", "https://www.walmart.com/ip/18656266943",
        "--reference", "BSHAPPLUS Listing Plastic | 31.58 | 40",
    ]
    assert product_scan.main(args) == 0
    out = capsys.readouterr().out
    assert "note: reference not readable headless (bot wall) - rerun with --show" in out
    reports = tmp_path / "reports" / "product"
    payload = json.loads(next(reports.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["reference"]["origin"] == "reference-hand"
    assert payload["reference"]["title"] == "BSHAPPLUS Listing Plastic"


def test_reference_literal_with_rating_and_reviews_flows_through_to_the_report(monkeypatch, tmp_path):
    # fix batch A4, 2026-09-11: the reference block/row shows "4.1 (15)"
    # instead of "-" once the literal carries an optional rating/reviews.
    monkeypatch.setattr(product_scan, "read_amazon_search", lambda page, page_number, start_position=0: [])
    args = ["--query", "x", "--reference", "BSHAPPLUS Listing Plastic | 31.58 | 40 | 4.1 | 15"]
    assert product_scan.main(args) == 0
    reports = tmp_path / "reports" / "product"
    payload = json.loads(next(reports.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["reference"]["rating"] == 4.1
    assert payload["reference"]["reviews"] == 15
    md_path = next(reports.glob("*.md"))
    assert "4.1 (15)" in md_path.read_text(encoding="utf-8")


def test_reference_url_read_populates_origin_reference_url(monkeypatch, tmp_path, capsys):
    class RefSession(FakeSession):
        def goto(self, url):
            super().goto(url)
            if "amazon.com/dp/" in url:
                self.page = FakePage(url=url, title="Amazon.com : EasyFlex", elements={
                    prod.AMAZON_PRODUCT_TITLE_SELECTOR: [{"text": "EasyFlex Heavy Duty No-Dig Edging Kit - 100ft., Black"}],
                    prod.AMAZON_PRODUCT_PRICE_SELECTOR: [{"text": "$44.37"}],
                })
            else:
                self.page = FakePage(url=url, title="Amazon.com : x", elements={})

    monkeypatch.setattr(product_scan, "Session", RefSession)
    monkeypatch.setattr(product_scan, "read_amazon_search", lambda page, page_number, start_position=0: [])
    args = ["--query", "x", "--reference-url", "https://www.amazon.com/dp/B01MG4ARN7"]
    assert product_scan.main(args) == 0
    reports = tmp_path / "reports" / "product"
    payload = json.loads(next(reports.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["reference"]["origin"] == "reference-url"
    assert payload["reference"]["price"] == 44.37


def test_min_height_in_drops_a_short_listing_and_flags_an_unknown_one(monkeypatch, tmp_path, capsys):
    def fake_amazon_search(page, page_number, start_position=0):
        short = _filled(title="Short 2 Inch 40 ft No Dig Plastic Edging", url="https://www.amazon.com/dp/EEEEEEEEEE", price=20.0, rating=4.5, reviews=10, position=start_position, page=page_number)
        unknown = _filled(title="Unknown Height Plastic Edging Coil 40 ft", url="https://www.amazon.com/dp/FFFFFFFFFF", price=25.0, rating=4.5, reviews=10, position=start_position + 1, page=page_number)
        return [short, unknown]

    monkeypatch.setattr(product_scan, "read_amazon_search", fake_amazon_search)
    assert product_scan.main(["--query", "x", "--pages", "1", "--min-height-in", "3"]) == 0
    reports = tmp_path / "reports" / "product"
    payload = json.loads(next(reports.glob("*.json")).read_text(encoding="utf-8"))
    titles = [listing["title"] for listing in payload["tiers"]["plastic"]]
    assert "Short 2 Inch 40 ft No Dig Plastic Edging" not in titles
    kept = next(listing for listing in payload["tiers"]["plastic"] if "Unknown Height" in listing["title"])
    assert "height unknown" in kept["flags"]
    assert payload["meta"]["dropped_by_height"] == 1


def test_zero_listings_overall_still_writes_a_report_and_exits_zero(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(product_scan, "read_amazon_search", lambda page, page_number, start_position=0: [])
    assert product_scan.main(["--query", "nothing matches this", "--pages", "1"]) == 0
    reports = tmp_path / "reports" / "product"
    assert len(list(reports.glob("product-scan-*.md"))) == 1


def test_pack_flag_flows_through_the_scan_pipeline_to_the_report(monkeypatch, tmp_path):
    # fix batch A6, 2026-09-11: a title naming a per-piece length gets the
    # "pack: per-piece length" flag and " (per piece)" in the report's own
    # Length cell - proven here through the real pipeline (_fill_attributes),
    # not just through headless/products.py's own unit tests.
    def fake_amazon_search(page, page_number, start_position=0):
        return [_filled(
            title="5 Piece Steel Home Kit Raw Steel Edging with 15 Edge Pins, 4\" by 8', 18-Gauge",
            url="https://www.amazon.com/dp/HHHHHHHHHH", price=40.0, rating=4.5, reviews=10,
            position=start_position, page=page_number,
        )]

    monkeypatch.setattr(product_scan, "read_amazon_search", fake_amazon_search)
    assert product_scan.main(["--query", "x", "--pages", "1"]) == 0
    reports = tmp_path / "reports" / "product"
    payload = json.loads(next(reports.glob("*.json")).read_text(encoding="utf-8"))
    listing = payload["tiers"]["metal"][0]
    assert listing["length_ft"] == 8.0
    assert "pack: per-piece length" in listing["flags"]
    md_path = next(reports.glob("*.md"))
    assert "8 ft (per piece)" in md_path.read_text(encoding="utf-8")


# --- subprocess sanity --------------------------------------------------------------


def test_subprocess_help_from_an_unrelated_cwd_exits_zero(tmp_path):
    script = Path(__file__).resolve().parent.parent / "scripts" / "product_scan.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"], cwd=str(tmp_path), capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "product_scan" in result.stdout
