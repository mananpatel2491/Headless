"""Unit tests for headless/activities.py (spec 009-activity-scan): the parsers for
what a Google Maps result card and place page expose, the geography, the day-window
verdict, the score, duplicate folding, ranking, and the renderers. Browser-free.

Hours fixtures spell Google's own U+2013 as an escape, never as a literal (house style).
"""

from __future__ import annotations

import json

import pytest

from headless import activities as act

NEAR_POINT = (42.4800, -83.3800)  # a synthetic round-number point inside a public city, used by every doc
NOVI_PUTTING_EDGE_HREF = (
    "https://www.google.com/maps/place/Novi+Putting+Edge/data=!4m7!3m6!1s0x8824af17cfeff099:"
    "0x928dd057ba12892a!8m2!3d42.493349!4d-83.485421!16s%2Fg%2F1td6n2p6"
)


def _venue(**overrides) -> act.Venue:
    base = dict(name="Sample Venue", url="https://www.google.com/maps/place/x", tag="games", query="escape room")
    base.update(overrides)
    return act.Venue(**base)


# --- parsing ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("42.4800,-83.3800", (42.4800, -83.3800)),
        (" 42.4800 , -83.3800 ", (42.4800, -83.3800)),
        ("+42.48,-83.38", (42.48, -83.38)),
        ("42.48,-83.38,17z", (42.48, -83.38)),  # a pasted lat,lon,zoom triple
        ("42.48,-83.38,17", (42.48, -83.38)),
        ("1 Example Street, Farmington Hills, MI", None),
        ("95,0", None),
        ("", None),
    ],
)
def test_parse_near(text, expected):
    assert act.parse_near(text) == expected


def test_looks_like_coordinates_tells_an_out_of_range_pair_from_an_address():
    assert act.looks_like_coordinates("95,0") is True
    assert act.looks_like_coordinates("42.4800,-83.3800") is True
    assert act.looks_like_coordinates("+95,0") is True
    assert act.looks_like_coordinates("95,0,17z") is True
    assert act.looks_like_coordinates("1 Example Street") is False
    assert act.parse_near("95,0") is None


def test_parse_place_href_reads_the_embedded_coordinates():
    assert act.parse_place_href(NOVI_PUTTING_EDGE_HREF) == (42.493349, -83.485421)
    assert act.parse_place_href("https://www.google.com/maps/place/NoCoords") is None
    assert act.parse_place_href("") is None


def test_parse_place_href_falls_back_to_the_viewport_of_a_place_page_url():
    url = "https://www.google.com/maps/place/Topgolf/@42.6512,-83.2201,17z/data=!3m1!4b1"
    assert act.parse_place_href(url) == (42.6512, -83.2201)


@pytest.mark.parametrize(
    "label, expected",
    [
        ("4.2 stars 726 Reviews", (4.2, 726)),
        ("4.5 stars 2,680 Reviews", (4.5, 2680)),
        ("5.0 stars 1 Review", (5.0, 1)),
        ("Photo of the venue", None),
        ("", None),
    ],
)
def test_parse_rating_label(label, expected):
    assert act.parse_rating_label(label) == expected


def test_parse_card_lines_organic_card():
    lines = [
        "Heavner Canoe Rental",
        "Heavner Canoe Rental",
        "4.6(585)",
        "Canoe & kayak rental service ·  · 2775 Garden Rd",
        "Closed · Opens 11 AM Sat",
    ]
    parsed = act.parse_card_lines(lines)
    assert parsed["name"] == "Heavner Canoe Rental"
    assert parsed["sponsored"] is False
    assert (parsed["rating"], parsed["reviews"]) == (4.6, 585)
    assert parsed["category"] == "Canoe & kayak rental service"
    assert parsed["address"] == "2775 Garden Rd"
    assert parsed["hours_today"] == "Closed · Opens 11 AM Sat"


def test_parse_card_lines_sponsored_card_with_ad_copy_and_price_level():
    lines = [
        "The Gregor Private Indoor Golf & Club",
        "Sponsored",
        "",
        "The Gregor Private Indoor Golf & Club",
        "5.0(18)",
        "Indoor golf course · $$ · 169 Clarkston Road",
        "Open 24 hours",
        "Reserve Your Tee Time",
        "Visit us for a night of fun.",
        "Visit Site",
    ]
    parsed = act.parse_card_lines(lines)
    assert parsed["sponsored"] is True
    assert (parsed["rating"], parsed["reviews"]) == (5.0, 18)
    assert parsed["category"] == "Indoor golf course"
    assert parsed["address"] == "169 Clarkston Road"
    assert parsed["hours_today"] == "Open 24 hours"


def test_parse_card_lines_unrated_card_still_finds_category():
    parsed = act.parse_card_lines(["New Place", "New Place", "Park · 1 Main St"])
    assert parsed["rating"] is None
    assert parsed["category"] == "Park"
    assert parsed["address"] == "1 Main St"


def test_parse_card_lines_empty():
    parsed = act.parse_card_lines([])
    assert parsed["name"] == "" and parsed["category"] == "" and parsed["rating"] is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Closed", []),
        ("", []),
        ("Open 24 hours", [[0, 1440]]),
        ("11 AM\u20137 PM", [[660, 1140]]),
        ("5\u20139 PM", [[1020, 1260]]),
        ("10\u20132 PM", [[600, 840]]),
        ("10 AM\u201412 AM", [[600, 1440]]),
        ("6 PM\u20131 AM", [[1080, 1500]]),
        ("11 AM-2 PM, 5-9 PM", [[660, 840], [1020, 1260]]),
        ("10:30 AM\u201311:45 PM", [[630, 1425]]),
    ],
)
def test_parse_hours_text(text, expected):
    assert act.parse_hours_text(text) == expected


def test_parse_weekly_rows_skips_non_day_rows_and_keeps_first_per_day():
    rows = [
        "WednesdayClosed",
        "Saturday11 AM\u20137 PM",
        "Friday, 5\u20139 PM",
        "5 stars, 455 reviews",
        "SaturdayDuplicate",
    ]
    assert act.parse_weekly_rows(rows) == {
        "wednesday": "Closed",
        "saturday": "11 AM\u20137 PM",
        "friday": "5\u20139 PM",
    }


def test_strip_prefix():
    assert act.strip_prefix("Address: 1 Main St", "Address:") == "1 Main St"
    assert act.strip_prefix("1 Main St", "Address:") == "1 Main St"
    assert act.strip_prefix("", "Phone:") == ""


def test_parse_geocode_response():
    body = json.dumps([{"lat": "42.4800", "lon": "-83.3800", "display_name": "x"}])
    assert act.parse_geocode_response(body) == (42.4800, -83.3800)
    assert act.parse_geocode_response("[]") is None
    assert act.parse_geocode_response("not json") is None
    assert act.parse_geocode_response(json.dumps([{"lat": "abc"}])) is None


def test_search_url_and_nominatim_url_encode_the_query():
    url = act.search_url("mini golf", "Farmington Hills, MI")
    assert url == "https://www.google.com/maps/search/mini+golf+near+Farmington+Hills%2C+MI/"
    assert "q=1+Example+St" in act.nominatim_url("1 Example St")
    assert "format=json" in act.nominatim_url("x")


# --- geography -------------------------------------------------------------------


def test_haversine_between_the_example_point_and_a_public_venue_is_about_five_miles():
    miles = act.haversine_miles(*NEAR_POINT, 42.493349, -83.485421)
    assert 5.2 < miles < 5.7


def test_haversine_zero_distance():
    assert act.haversine_miles(42.0, -83.0, 42.0, -83.0) == 0.0


def test_estimate_drive_minutes_grows_with_distance():
    assert act.estimate_drive_minutes(0) == 3
    assert act.estimate_drive_minutes(10) == 29
    assert act.estimate_drive_minutes(20) > act.estimate_drive_minutes(10)


def test_locate_fills_miles_and_leaves_unknown_for_missing_coords():
    known = _venue(lat=42.493349, lon=-83.485421)
    unknown = _venue(name="No coords")
    act.locate([known, unknown], NEAR_POINT)
    assert 5.2 < known.miles < 5.7 and known.drive_minutes > 3
    assert unknown.miles is None and unknown.drive_minutes is None


# --- window ----------------------------------------------------------------------


def test_window_minutes():
    assert act.window_minutes("17:00", "22:00") == (1020, 1320)
    assert act.window_minutes("22:00", "02:00") == (1320, 1560)


@pytest.mark.parametrize("start, end", [("25:00", "26:30"), ("17:99", "22:00"), ("17:00", "24:00"), ("x", "22:00")])
def test_window_minutes_refuses_a_non_clock_time(start, end):
    with pytest.raises(ValueError):
        act.window_minutes(start, end)


def test_overlap_minutes():
    window = (1020, 1320)
    assert act.overlap_minutes([[600, 1140]], window) == 120
    assert act.overlap_minutes([[0, 1440]], window) == 300
    assert act.overlap_minutes([[1320, 1500]], window) == 0
    assert act.overlap_minutes([], window) == 0


@pytest.mark.parametrize(
    "friday, status, overlap",
    [
        ("10 AM\u201310 PM", "open", 300),
        ("10 AM\u20139 PM", "open", 240),
        ("10 AM\u20137 PM", "partial", 120),
        ("Closed", "closed", 0),
        ("9 AM\u20135 PM", "closed", 0),
        # verifier finding 3 (2026-09-09): unparseable text is unknown, never closed
        ("Hours might differ", "unknown", None),
        ("", "unknown", None),
    ],
)
def test_apply_day_window(friday, status, overlap):
    venue = _venue(weekly_hours={"friday": friday})
    act.apply_day_window(venue, "friday", (1020, 1320))
    assert venue.day_status == status
    assert venue.window_overlap_minutes == overlap


def test_apply_day_window_unknown_when_day_missing():
    venue = _venue()
    act.apply_day_window(venue, "friday", (1020, 1320))
    assert venue.day_status == "unknown" and venue.window_overlap_minutes is None


# --- score, fold, rank -----------------------------------------------------------


def test_score_shrinks_a_tiny_review_count_toward_the_prior():
    many = _venue(rating=4.6, reviews=600, miles=5.0)
    few = _venue(rating=5.0, reviews=3, miles=5.0)
    assert act.score_venue(many) > act.score_venue(few)


def test_score_penalizes_distance_and_a_closed_day():
    near = _venue(rating=4.5, reviews=100, miles=2.0)
    far = _venue(rating=4.5, reviews=100, miles=20.0)
    assert act.score_venue(near) - act.score_venue(far) == pytest.approx(0.72, abs=0.01)
    closed = _venue(rating=4.5, reviews=100, miles=2.0, day_status="closed")
    opened = _venue(rating=4.5, reviews=100, miles=2.0, day_status="open")
    assert act.score_venue(opened) - act.score_venue(closed) == pytest.approx(1.2, abs=0.01)


def test_score_unrated_venue_uses_the_prior():
    assert act.score_venue(_venue(miles=0.0)) == pytest.approx(4.0)


def test_fold_duplicates_prefers_the_organic_copy_and_unions_queries():
    sponsored = _venue(name="Putting Edge", lat=42.49335, lon=-83.48542, sponsored=True, query="mini golf")
    organic = _venue(name="Putting Edge", lat=42.4933494, lon=-83.4854212, query="outdoor mini golf")
    other = _venue(name="Other", lat=42.0, lon=-83.0, query="mini golf")
    folded = act.fold_duplicates([sponsored, organic, other])
    assert len(folded) == 2
    kept = next(v for v in folded if v.name == "Putting Edge")
    assert kept.sponsored is False
    assert kept.matched_queries == ["mini golf", "outdoor mini golf"]


def test_fold_duplicates_keeps_the_best_list_position():
    deep = _venue(name="Same", lat=42.1, lon=-83.1, position=12, query="a")
    shallow = _venue(name="Same", lat=42.1, lon=-83.1, position=2, query="b")
    unplaced = _venue(name="Same", lat=42.1, lon=-83.1, position=None, query="c")
    (kept,) = act.fold_duplicates([deep, shallow, unplaced])
    assert kept.position == 2
    assert kept.matched_queries == ["a", "b", "c"]


@pytest.mark.parametrize(
    "category, excluded",
    [
        ("Movie theater", True),
        ("Indian restaurant", True),
        ("Billiards supply store", True),
        ("Wine store", True),
        ("Window tinting service", True),
        ("DJ service", True),
        ("Indoor playground", True),
        ("Wedding venue", True),
        ("Bowling supply shop", True),
        ("Elementary school", True),
        ("Preschool", True),
        ("Children's museum", True),
        ("Toy store", True),
        ("Comedy club", False),
        ("Canoe & kayak rental service", False),
        ("Rock climbing gym", False),
        ("Escape room center", False),
        ("Event venue", False),
        # verifier finding 2 (2026-09-09): whole-word matching, and only kid-only schools
        ("Dance school", False),
        ("Cooking school", False),
        ("Rock climbing school", False),
        ("Pottery workshop", False),
        ("Workshop", False),
        ("Bike rental shop", False),
        ("Kayak & canoe rental shop", False),
        ("Boat rental service", False),
        ("Bicycle rental service", False),
        # re-verification finding 5: only the named activity rentals are kept
        ("Tuxedo rental shop", True),
        ("Party rental store", True),
        ("Costume rental shop", True),
        # re-verification finding 6: the hyphenated spelling
        ("Co-working space", True),
        ("Coworking space", True),
        ("", False),
    ],
)
def test_is_excluded(category, excluded):
    assert act.is_excluded(category) is excluded


def test_query_tokens_drop_generic_words():
    assert act.query_tokens("hiking trails nature center") == ["hiking", "trails", "nature"]
    assert act.query_tokens("outdoor mini golf") == ["mini", "golf"]
    assert act.query_tokens("board game cafe") == ["board", "game"]
    assert act.query_tokens("near the park") == []


@pytest.mark.parametrize(
    "name, category, queries, hit",
    [
        ("Heavner Canoe Rental", "Canoe & kayak rental service", ["kayak canoe rental"], True),
        ("Novi Putting Edge", "Miniature golf course", ["outdoor mini golf"], True),
        ("BATL Grounds | Novi", "Event venue", ["axe throwing"], False),
        ("The Axe Parlor", "Adventure sports center", ["axe throwing"], True),
        ("Kensington Metropark", "Park", ["metropark"], True),
        ("Some Trail Loop", "Park", ["hiking trails nature center"], True),
        ("Some Trailhead", "Park", ["hiking trails nature center"], False),  # whole words, never a prefix
        ("Best Service Co", "Cleaning service", ["ice skating rink"], False),  # "ice" never matches "service"
        ("Huron River Hunting & Fishing Club", "Club", ["live music venue"], False),
        # verifier finding 4 (2026-09-09): prefix stems hit unrelated words
        ("Comerica Bank", "Bank", ["comedy club"], False),
        ("Mining Museum", "Museum", ["outdoor mini golf"], False),
        ("Insomnia Cookies", "Bakery", ["cooking class"], False),
        # inflections of a token still count
        ("Painting with a Twist", "Painting studio", ["paint and sip"], True),
        ("Santé", "Wine bar", ["winery vineyard"], True),
        ("Farmington Brewing Company", "Brewery", ["brewery with games"], True),
        ("Parmenter's Cider Mill", "Cider mill", ["cidery"], True),
        ("Detroit Archers", "Archery club", ["archery range"], True),
        ("Go-Kart World", "Go-kart track", ["go kart track"], True),
        ("Cooking with Class", "Cooking class", ["cooking class"], True),
    ],
)
def test_relevance_hit(name, category, queries, hit):
    venue = _venue(name=name, category=category, matched_queries=queries)
    assert act.relevance_hit(venue) is hit


def test_score_position_and_relevance_terms():
    base = _venue(rating=4.5, reviews=100, miles=2.0)
    deep = _venue(rating=4.5, reviews=100, miles=2.0, position=40)
    first = _venue(rating=4.5, reviews=100, miles=2.0, position=0)
    assert act.score_venue(first) == act.score_venue(base)
    assert act.score_venue(base) - act.score_venue(deep) == pytest.approx(0.6, abs=0.01)
    relevant = _venue(rating=4.5, reviews=100, miles=2.0, relevant=True)
    irrelevant = _venue(rating=4.5, reviews=100, miles=2.0, relevant=False)
    assert act.score_venue(relevant) - act.score_venue(base) == pytest.approx(0.35, abs=0.01)
    assert act.score_venue(base) - act.score_venue(irrelevant) == pytest.approx(0.25, abs=0.01)


def test_rank_drops_excluded_and_out_of_radius_and_sorts_by_score():
    good = _venue(name="Good", rating=4.8, reviews=500, miles=3.0, category="Escape room center")
    okay = _venue(name="Okay", rating=4.2, reviews=50, miles=8.0, category="Bowling alley")
    theater = _venue(name="Cinema", rating=4.9, reviews=900, miles=1.0, category="Movie theater")
    far = _venue(name="Far", rating=4.9, reviews=900, miles=40.0, category="Park")
    ranked = act.rank([okay, theater, far, good], radius_miles=20)
    assert [v.name for v in ranked] == ["Good", "Okay"]
    assert theater.excluded is True
    assert ranked[0].score > ranked[1].score
    assert good.relevant is True  # the whole word "escape" appears in "Escape room center"
    assert okay.relevant is False  # "Okay / Bowling alley" echoes nothing of "escape room"


def test_relevance_is_neutral_when_no_query_carries_a_meaning_token():
    assert act.relevance_pattern("cafe bar club") is None
    venue = _venue(name="Anything", category="Bar", query="cafe bar club", rating=4.5, reviews=100, miles=1.0)
    assert act.relevance_hit(venue) is None
    (ranked,) = act.rank([venue], radius_miles=20)
    assert ranked.relevant is None
    neutral = _venue(rating=4.5, reviews=100, miles=1.0)
    assert ranked.score == act.score_venue(neutral)


def test_relevance_pattern_never_raises_on_regex_specials():
    for query in ("R&B live music", "mini-golf (outdoor)", "[a-z]+ class", "c++ class", "\\ axe"):
        act.relevance_pattern(query)  # must not raise


def test_rank_marks_relevance_from_the_matched_queries():
    echo = _venue(name="Farmington Axe House", category="Adventure sports center", miles=1.0, query="axe throwing")
    silent = _venue(name="Grand Hall", category="Event venue", miles=1.0, query="axe throwing")
    ranked = act.rank([silent, echo], radius_miles=20)
    assert echo.relevant is True and silent.relevant is False
    assert ranked[0] is echo


# --- rendering -------------------------------------------------------------------


def test_render_markdown_and_json():
    venue = _venue(
        name="Sample Venue", rating=4.6, reviews=120, miles=4.2, drive_minutes=14,
        category="Escape room center", address="1 Main St", website="https://example.com",
        weekly_hours={"friday": "10 AM\u201310 PM"}, score=4.5,
    )
    text = act.render_markdown(
        [venue], near_label="42.48,-83.38", near=NEAR_POINT, day="friday", window_text="17:00-22:00",
        generated_at="2026-09-09T20:00:00Z", queries_run=3,
    )
    assert "# Activity scan" in text
    assert "## Top picks overall" in text
    assert "## Games" in text
    assert "| 1 | [Sample Venue](https://example.com) | 4.6 (120) | 4.2 mi, ~14 min | Escape room center |" in text
    assert "Friday: 10 AM\u201310 PM" in text
    assert "| Found via |" in text
    assert "| escape room |" in text  # the query that surfaced it
    payload = json.loads(act.render_json([venue], near=list(NEAR_POINT), day="friday"))
    assert payload["meta"]["day"] == "friday"
    assert payload["venues"][0]["name"] == "Sample Venue"
    assert payload["venues"][0]["weekly_hours"]["friday"] == "10 AM\u201310 PM"


def test_render_markdown_unknown_hours_and_missing_website():
    venue = _venue(name="Plain", rating=None, reviews=None)
    text = act.render_markdown(
        [venue], near_label="x", near=NEAR_POINT, day="friday", window_text="17:00-22:00",
        generated_at="t", queries_run=1,
    )
    assert "| 1 | Plain | no rating | distance unknown | ? | Friday: not checked | ? | escape room |" in text


def test_default_queries_are_tagged_and_unique():
    queries = [query for _, query in act.DEFAULT_QUERIES]
    assert len(queries) == len(set(queries))
    assert all(tag for tag, _ in act.DEFAULT_QUERIES)
