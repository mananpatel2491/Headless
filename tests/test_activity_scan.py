"""Unit tests for scripts/activity_scan.py (spec 009-activity-scan): the CLI's own
refusals, the check mode, and the scan pipeline with the two browser-reading
functions stubbed - never a real `Session`, never a network call.
"""

from __future__ import annotations

import json
import stat

import pytest

import scripts.activity_scan as activity_scan
from headless import activities as act
from headless.gates import GateRefused, Mode


class FakeLocator:
    """A tiny stand-in for a Playwright Locator: a fixed list of elements, each a
    dict of attribute -> value, an optional "text", and an optional "sub" mapping
    of selector -> child elements for nested `locator()` calls."""

    evaluate_calls: list[str] = []

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

    def evaluate(self, script):
        FakeLocator.evaluate_calls.append(script)


class FakePage:
    def __init__(self, url="https://www.google.com/maps/search/x/", title="x - Google Maps", elements=None, texts=None):
        self.url = url
        self._title = title
        # selector -> elements; an unregistered selector resolves to nothing, so a
        # test must register every element it expects the script to find.
        self._elements = elements if elements is not None else {}
        self._texts = texts if texts is not None else {}
        self.waits: list[int] = []

    def title(self):
        return self._title

    def wait_for_selector(self, selector, timeout=0):
        return None

    def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)

    def locator(self, selector):
        return FakeLocator(self._elements.get(selector, []))

    def get_by_text(self, text):
        return FakeLocator([{}] * self._texts.get(text, 0))


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
    FakeLocator.evaluate_calls.clear()
    monkeypatch.setenv("HEADLESS_PREVIEW_DIR", str(tmp_path / "previews"))
    monkeypatch.setenv("HEADLESS_PROFILE_DIR", str(tmp_path / "profile"))
    monkeypatch.setattr(activity_scan, "Session", FakeSession)
    yield
    FakeSession.instances.clear()


def test_apply_is_refused_before_any_session(monkeypatch, capsys):
    monkeypatch.setattr(activity_scan, "Session", RefusingSession)
    assert activity_scan.main(["--near", "42.48,-83.38", "--apply"]) == 1
    assert "REFUSED" in capsys.readouterr().out


def test_unresolvable_near_refuses_before_any_session(monkeypatch, capsys):
    monkeypatch.setattr(activity_scan, "Session", RefusingSession)
    monkeypatch.setattr(activity_scan, "_fetch", lambda url: "[]")
    assert activity_scan.main(["--near", "nowhere at all"]) == 1
    assert "could not be resolved" in capsys.readouterr().out


def test_geocoding_failure_is_a_refusal_not_a_crash(monkeypatch):
    def boom(url):
        raise OSError("offline")

    assert activity_scan.resolve_near("1 Example Street", fetch=boom) is None
    assert activity_scan.resolve_near("42.1,-83.2", fetch=boom) == (42.1, -83.2)
    body = json.dumps([{"lat": "42.5", "lon": "-83.5"}])
    assert activity_scan.resolve_near("1 Example Street", fetch=lambda url: body) == (42.5, -83.5)


def test_bad_window_refuses(capsys):
    assert activity_scan.main(["--near", "42.48,-83.38", "--start", "22:00", "--end", "22:00"]) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert FakeSession.instances == []


def test_non_clock_time_refuses(capsys):
    assert activity_scan.main(["--near", "42.48,-83.38", "--start", "25:00"]) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert FakeSession.instances == []


def test_out_of_range_pair_is_refused_without_a_geocode_request(monkeypatch, capsys):
    calls: list[str] = []
    # Recorded, not raised: resolve_near swallows any fetch exception by design, so
    # a raising stub would pass even if the guard were gone (re-verification
    # finding 4, 2026-09-09).
    monkeypatch.setattr(activity_scan, "_fetch", lambda url: calls.append(url) or "[]")
    assert activity_scan.main(["--near", "95,0"]) == 1
    assert "could not be resolved" in capsys.readouterr().out
    assert calls == []
    assert FakeSession.instances == []
    assert activity_scan.main(["--near", "95,0,17z"]) == 1
    assert calls == []


def test_empty_queries_file_refuses(tmp_path, capsys):
    empty = tmp_path / "q.txt"
    empty.write_text("# nothing\n", encoding="utf-8")
    assert activity_scan.main(["--near", "42.48,-83.38", "--queries-file", str(empty)]) == 1
    assert "REFUSED: no queries to run" in capsys.readouterr().out
    assert FakeSession.instances == []


def test_gate_refused_from_the_session_exits_one(monkeypatch, capsys):
    class RefusedSession(FakeSession):
        def __enter__(self):
            raise GateRefused("profile in use")

    monkeypatch.setattr(activity_scan, "Session", RefusedSession)
    assert activity_scan.main(["--near", "42.48,-83.38", "--check"]) == 1
    assert "REFUSED: profile in use" in capsys.readouterr().out


def test_browser_failure_exits_two_with_class_name_only_and_debug_traceback(monkeypatch, capsys):
    class ExplodingSession(FakeSession):
        def __enter__(self):
            raise RuntimeError("DISTINCTIVE-STACK-TRACE-SHOULD-NEVER-APPEAR")

    monkeypatch.setattr(activity_scan, "Session", ExplodingSession)
    assert activity_scan.main(["--near", "42.48,-83.38", "--check"]) == 2
    captured = capsys.readouterr()
    assert "ERROR: RuntimeError (rerun with HEADLESS_DEBUG=1 for the traceback)" in captured.out
    assert "DISTINCTIVE-STACK-TRACE-SHOULD-NEVER-APPEAR" not in captured.out
    assert captured.err == ""
    monkeypatch.setenv("HEADLESS_DEBUG", "1")
    assert activity_scan.main(["--near", "42.48,-83.38", "--check"]) == 2
    assert "RuntimeError" in capsys.readouterr().err


def test_check_mode_probes_the_live_selectors(tmp_path, capsys):
    assert activity_scan.main(["--near", "42.48,-83.38", "--area", "Farmington Hills, MI", "--check"]) == 0
    out = capsys.readouterr().out
    assert "CHECK 3 found, 0 missing" in out
    session = FakeSession.instances[0]
    assert session.mode is Mode.PREVIEW
    assert session.goto_calls == [act.search_url(act.DEFAULT_QUERIES[0][1], "Farmington Hills, MI")]
    assert not (tmp_path / "reports").exists()  # check mode writes no report


def test_check_mode_reports_a_missing_selector_and_still_exits_zero(monkeypatch, capsys):
    class PartialSession(FakeSession):
        def probe(self, selectors):
            return [(selector, selector == act.FEED_SELECTOR) for selector in selectors]

    monkeypatch.setattr(activity_scan, "Session", PartialSession)
    assert activity_scan.main(["--near", "42.48,-83.38", "--check"]) == 0
    out = capsys.readouterr().out
    assert f"MISSING {act.RATING_SELECTOR}" in out
    assert "CHECK 1 found, 2 missing" in out


def test_scan_writes_markdown_and_json_reports(monkeypatch, tmp_path, capsys):
    def fake_search(page, tag, query):
        if query != "escape room":
            return []
        return [
            act.Venue(name="Sample Venue", url="https://www.google.com/maps/place/sample", tag=tag, query=query,
                      lat=42.49, lon=-83.48, rating=4.7, reviews=300, category="Escape room center",
                      address="1 Main St"),
            act.Venue(name="Cinema", url="https://www.google.com/maps/place/cinema", tag=tag, query=query,
                      lat=42.45, lon=-83.43, rating=4.9, reviews=900, category="Movie theater"),
        ]

    def fake_place(page, venue):
        venue.weekly_hours = {"friday": "10 AM\u201310 PM"}
        venue.website = "https://example.com"

    monkeypatch.setattr(activity_scan, "read_search_page", fake_search)
    monkeypatch.setattr(activity_scan, "read_place_page", fake_place)
    queries_file = tmp_path / "queries.txt"
    queries_file.write_text("games\tescape room\n# comment\n\ncreative\tpaint and sip\n", encoding="utf-8")

    exit_code = activity_scan.main([
        "--near", "42.4800,-83.3800", "--area", "Farmington Hills, MI", "--queries-file", str(queries_file),
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "SCAN " in out
    reports = tmp_path / "reports" / "activity"
    md_files = sorted(reports.glob("activity-scan-*.md"))
    json_files = sorted(reports.glob("activity-scan-*.json"))
    assert len(md_files) == 1 and len(json_files) == 1
    text = md_files[0].read_text(encoding="utf-8")
    assert "[Sample Venue](https://example.com)" in text
    assert "Cinema" not in text  # excluded category never reaches the report
    for path in (md_files[0], json_files[0]):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # A same-date rerun over files whose mode drifted must restore 0600: os.open's
    # mode applies only to a NEW file, so this is the chmod bracket's real job
    # (re-verification finding 3, 2026-09-09).
    for path in (md_files[0], json_files[0]):
        path.chmod(0o644)
    assert activity_scan.main([
        "--near", "42.4800,-83.3800", "--area", "Farmington Hills, MI", "--queries-file", str(queries_file),
    ]) == 0
    assert sorted(reports.glob("activity-scan-*.md")) == md_files  # overwritten, not duplicated
    for path in (md_files[0], json_files[0]):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["meta"]["queries"] == [["games", "escape room"], ["creative", "paint and sip"]]
    venue = payload["venues"][0]
    assert venue["day_status"] == "open" and venue["window_overlap_minutes"] == 300
    assert venue["miles"] is not None
    session = FakeSession.instances[0]
    # two search pages, then one place page for the one surviving venue
    assert len(session.goto_calls) == 3
    assert session.goto_calls[-1] == "https://www.google.com/maps/place/sample"


def _card(name, href, text, rating_label=None):
    sub = {act.PLACE_LINK_SELECTOR: [{"href": href, "aria-label": name}]}
    if rating_label:
        sub[act.RATING_SELECTOR] = [{"aria-label": rating_label}]
    return {"text": text, "sub": sub}


def _feed_page(cards, end_marker=True):
    feed = {"sub": {":scope > div": [{"text": "Results", "sub": {}}] + cards}}
    return FakePage(
        elements={act.FEED_SELECTOR: [feed], f"{act.FEED_SELECTOR} {act.PLACE_LINK_SELECTOR}": [{}] * len(cards)},
        texts={act.END_OF_LIST_TEXT: 1 if end_marker else 0},
    )


def test_read_search_page_maps_cards_to_venues_with_positions():
    organic = _card(
        "Heavner Canoe Rental",
        "https://www.google.com/maps/place/Heavner/data=!3d42.55!4d-83.6",
        "Heavner Canoe Rental\nHeavner Canoe Rental\n4.6(585)\nCanoe & kayak rental service ·  · 2775 Garden Rd\nClosed · Opens 11 AM Sat",
        rating_label="4.6 stars 585 Reviews",
    )
    sponsored = _card(
        "",  # no aria-label: the name falls back to the card text
        "https://www.google.com/maps/place/Sponsored/data=!3d42.7!4d-83.2",
        "Sponsored Place\nSponsored\n\nSponsored Place\n5.0(18)\nIndoor golf course · 169 Clarkston Road\nOpen 24 hours",
    )
    page = _feed_page([organic, sponsored])
    venues = activity_scan.read_search_page(page, "outdoors", "kayak canoe rental")
    assert [v.position for v in venues] == [0, 1]
    first, second = venues
    assert first.name == "Heavner Canoe Rental" and (first.lat, first.lon) == (42.55, -83.6)
    assert (first.rating, first.reviews) == (4.6, 585)
    assert first.category == "Canoe & kayak rental service" and first.address == "2775 Garden Rd"
    assert first.hours_today == "Closed · Opens 11 AM Sat" and first.sponsored is False
    assert second.name == "Sponsored Place" and second.sponsored is True
    assert (second.rating, second.reviews) == (5.0, 18)  # the card-text fallback
    assert second.tag == "outdoors" and second.query == "kayak canoe rental"


def test_read_search_page_without_a_feed_returns_nothing_and_a_note(capsys):
    assert activity_scan.read_search_page(FakePage(), "games", "escape room") == []
    assert "note: no results feed for 'escape room'" in capsys.readouterr().out


def test_scroll_stops_at_the_end_of_list_text_without_scrolling():
    page = _feed_page([_card("A", "https://www.google.com/maps/place/A", "A")], end_marker=True)
    activity_scan._scroll_feed_to_end(page)
    assert FakeLocator.evaluate_calls == []
    assert page.waits == []


def test_scroll_gives_up_only_after_two_scrolls_that_load_nothing_new():
    page = _feed_page([_card("A", "https://www.google.com/maps/place/A", "A")], end_marker=False)
    activity_scan._scroll_feed_to_end(page)
    assert len(FakeLocator.evaluate_calls) == 2
    assert all("scrollBy" in script for script in FakeLocator.evaluate_calls)
    assert page.waits == [1500, 1500]


def test_one_failed_query_is_skipped_and_the_scan_still_writes_a_report(monkeypatch, tmp_path, capsys):
    class FlakySession(FakeSession):
        def goto(self, url):
            super().goto(url)
            if "escape+room" in url:
                raise RuntimeError("navigation failed")

    monkeypatch.setattr(activity_scan, "Session", FlakySession)
    monkeypatch.setattr(activity_scan, "read_search_page", lambda page, tag, query: [
        act.Venue(name="Survivor", url="https://www.google.com/maps/place/s", tag=tag, query=query, lat=42.46, lon=-83.43,
                  rating=4.5, reviews=40, category="Bowling alley")])
    monkeypatch.setattr(activity_scan, "read_place_page", lambda page, venue: None)
    queries = tmp_path / "q.txt"
    queries.write_text("games\tescape room\ngames\tbowling alley\n", encoding="utf-8")
    assert activity_scan.main(["--near", "42.4800,-83.3800", "--queries-file", str(queries)]) == 0
    out = capsys.readouterr().out
    assert "note: query skipped for 'escape room' (RuntimeError)" in out
    payload = json.loads(next((tmp_path / "reports" / "activity").glob("*.json")).read_text(encoding="utf-8"))
    assert [v["name"] for v in payload["venues"]] == ["Survivor"]


def test_one_failed_place_page_is_noted_and_the_venue_stays_in_the_report(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(activity_scan, "read_search_page", lambda page, tag, query: [
        act.Venue(name="Kept", url="https://www.google.com/maps/place/k", tag=tag, query=query, lat=42.46, lon=-83.43,
                  rating=4.5, reviews=40, category="Bowling alley")])

    def boom(page, venue):
        raise RuntimeError("place page died")

    monkeypatch.setattr(activity_scan, "read_place_page", boom)
    queries = tmp_path / "q.txt"
    queries.write_text("games\tbowling alley\n", encoding="utf-8")
    assert activity_scan.main(["--near", "42.4800,-83.3800", "--queries-file", str(queries)]) == 0
    assert "note: details skipped for 'Kept' (RuntimeError)" in capsys.readouterr().out
    payload = json.loads(next((tmp_path / "reports" / "activity").glob("*.json")).read_text(encoding="utf-8"))
    assert payload["venues"][0]["name"] == "Kept" and payload["venues"][0]["day_status"] == "unknown"


def test_read_single_place_builds_one_venue_from_a_place_page():
    page = FakePage(
        url="https://www.google.com/maps/place/Topgolf/@42.6512,-83.2201,17z/data=!3m1!4b1",
        title="Topgolf - Google Maps",
        elements={
            act.RATING_SELECTOR: [{"aria-label": "4.5 stars 2,680 Reviews"}],
            act.HOURS_ROW_SELECTOR: [{"text": "FridayOpen 24 hours"}, {"text": "5 stars, 455 reviews"}],
            act.WEBSITE_SELECTOR: [{"href": "https://example.com/topgolf"}],
            act.PHONE_SELECTOR: [],
            act.ADDRESS_SELECTOR: [{"aria-label": "Address: 500 Great Lakes Crossing Dr"}],
        },
    )
    venue = activity_scan.read_single_place(page, "active", "Topgolf")
    assert venue.name == "Topgolf" and venue.position == 0
    assert (venue.lat, venue.lon) == (42.6512, -83.2201)
    assert (venue.rating, venue.reviews) == (4.5, 2680)
    assert venue.weekly_hours == {"friday": "Open 24 hours"}
    assert venue.website == "https://example.com/topgolf"
    assert venue.address == "500 Great Lakes Crossing Dr" and venue.phone == ""


def test_scan_uses_the_single_place_path_when_google_opens_a_place_directly(monkeypatch, tmp_path, capsys):
    class RedirectSession(FakeSession):
        def goto(self, url):
            super().goto(url)
            self.page = FakePage(
                url="https://www.google.com/maps/place/Solo/@42.46,-83.43,17z/",
                title="Solo - Google Maps",
                elements={act.FEED_SELECTOR: [], act.HOURS_ROW_SELECTOR: [{"text": "Friday5-11 PM"}],
                          act.RATING_SELECTOR: [{"aria-label": "4.8 stars 50 Reviews"}]},
            )

    monkeypatch.setattr(activity_scan, "Session", RedirectSession)
    monkeypatch.setattr(activity_scan, "read_search_page", lambda page, tag, query: pytest.fail("feed path used"))
    queries_file = tmp_path / "q.txt"
    queries_file.write_text("active\tTopgolf\n", encoding="utf-8")
    assert activity_scan.main(["--near", "42.4800,-83.3800", "--queries-file", str(queries_file), "--details", "0"]) == 0
    assert "'Topgolf': 1 result (Google opened the place directly)" in capsys.readouterr().out
    payload = json.loads(next((tmp_path / "reports" / "activity").glob("*.json")).read_text(encoding="utf-8"))
    assert [v["name"] for v in payload["venues"]] == ["Solo"]
    assert payload["venues"][0]["weekly_hours"] == {"friday": "5-11 PM"}


def test_load_queries_default_and_file(tmp_path):
    assert activity_scan._load_queries(None) == list(act.DEFAULT_QUERIES)
    path = tmp_path / "q.txt"
    path.write_text("outdoors\tkayak\nno tab line\n", encoding="utf-8")
    assert activity_scan._load_queries(str(path)) == [("outdoors", "kayak"), ("custom", "no tab line")]


def test_no_submit_pay_confirm_or_otp_anywhere_in_the_script():
    """CLAUDE.md's terminal-actions rule, checked structurally: the scan script
    never mentions a submit, pay, confirm, or one-time-code concept, and its
    parser exposes no such flag."""
    source = (activity_scan.REPO_ROOT / "scripts" / "activity_scan.py").read_text(encoding="utf-8").lower()
    for token in ("--submit", "--pay", "--confirm", "otp"):
        assert token not in source, f"{token!r} found in scripts/activity_scan.py"
    parser = activity_scan._build_parser()
    flags = {option for action in parser._actions for option in action.option_strings}
    assert {"--submit", "--pay", "--confirm", "--otp"}.isdisjoint(flags)
    assert "--apply" in flags  # present only so it can be refused explicitly
