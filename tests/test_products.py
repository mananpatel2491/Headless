"""Unit tests for headless/products.py (spec 011-product-scan): the parsers for
a listing's price/rating/count text and title attributes, scoring, duplicate
folding, tiers, and the report renderers. Browser-free.

Every title in `parse_attributes` below is a real recon title, copied
verbatim from one of the three 2026-09-11 live-run JSON files named in the
fix-batch brief (`product-scan-2026-09-12.json` in this worktree's own
`reports/product/`, and the two under the fix-batch scratchpad's `run-4in/`
and `run-steel/` trees) - fix batch B16: fixtures are the FULL titles, not an
80-character truncation.
"""

from __future__ import annotations

import json
import re

import pytest

from headless import products as p


def _listing(**overrides) -> p.Listing:
    base = dict(site="amazon", title="Sample Listing", url="https://www.amazon.com/dp/AAAAAAAAAA", origin="search")
    base.update(overrides)
    return p.Listing(**base)


# --- price, rating, count ---------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("$43.99", 43.99),
        ("$\n41\n.\n97", 41.97),  # Home Depot's split spans
        ("Now $22.59", 22.59),
        ("31.58", 31.58),
        ("$1,234.00", 1234.0),
        ("no digits here", None),
        ("", None),
    ],
)
def test_parse_price(text, expected):
    assert p.parse_price(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("4.5 out of 5 stars", 4.5),
        ("4.5 out of 5", 4.5),
        ("(4.1)", 4.1),
        ("4.1", 4.1),
        ("", None),
    ],
)
def test_parse_rating(text, expected):
    assert p.parse_rating(text) == expected


def test_parse_rating_and_count_home_depot_slash_shape():
    assert p.parse_rating_and_count("(4.5 /\xa04091)") == (4.5, 4091)
    assert p.parse_rating_and_count("(4.5 / 4160)") == (4.5, 4160)


def test_parse_rating_and_count_walmart_stars_reviews_shape():
    assert p.parse_rating_and_count("4.1 out of 5 Stars. 15 reviews") == (4.1, 15)


def test_parse_rating_and_count_no_match():
    assert p.parse_rating_and_count("nothing here") is None
    assert p.parse_rating_and_count("") is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("5,118 ratings", 5118),
        ("(5,118)", 5118),
        ("158", 158),
        ("15 ratings", 15),
        ("5.1K", 5100),
        ("2.3M", 2300000),
        ("no digits", None),
        ("", None),
    ],
)
def test_parse_count(text, expected):
    assert p.parse_count(text) == expected


# --- search_url / canonical_url / slugify ------------------------------------------


def test_search_url_amazon_and_homedepot():
    assert p.search_url("amazon", "no dig landscape edging", 1) == "https://www.amazon.com/s?k=no+dig+landscape+edging&page=1"
    assert p.search_url("amazon", "no dig landscape edging", 2) == "https://www.amazon.com/s?k=no+dig+landscape+edging&page=2"
    assert p.search_url("homedepot", "no dig landscape edging", 1) == "https://www.homedepot.com/s/no%20dig%20landscape%20edging"
    assert p.search_url("homedepot", "no dig landscape edging", 2) == "https://www.homedepot.com/s/no%20dig%20landscape%20edging?Nao=24"
    assert p.search_url("homedepot", "no dig landscape edging", 3) == "https://www.homedepot.com/s/no%20dig%20landscape%20edging?Nao=48"


def test_search_url_unknown_site_raises():
    with pytest.raises(ValueError):
        p.search_url("target", "x", 1)


def test_canonical_url_amazon_from_href_asin():
    href = "/Bluepro-Landscape-Edging-Upgraded-Reinforced/dp/B0G4H2C41Y/ref=sr_1_1?dib=eyJ2IjoiMSJ9.Un5vlUM"
    assert p.canonical_url("amazon", href) == "https://www.amazon.com/dp/B0G4H2C41Y"


def test_canonical_url_amazon_falls_back_to_data_asin():
    assert p.canonical_url("amazon", "/some/link/with/no/asin/in/it", data_asin="B01MG4ARN7") == "https://www.amazon.com/dp/B01MG4ARN7"


def test_canonical_url_homedepot_strips_query_string():
    href = "/p/Vigoro-60-ft-No-Dig-Plastic-Landscape-Edging-Kit-3001-60HD-3/301459392"
    assert p.canonical_url("homedepot", href) == "https://www.homedepot.com" + href
    assert p.canonical_url("homedepot", href + "?some=query") == "https://www.homedepot.com" + href


def test_canonical_url_unknown_site_keeps_href():
    assert p.canonical_url("walmart", "https://www.walmart.com/ip/18656266943") == "https://www.walmart.com/ip/18656266943"


def test_wall_reason():
    assert p.wall_reason("Robot or human?", "https://www.walmart.com/blocked?url=x") == "Robot or human?"
    assert p.wall_reason("Access Denied", "https://www.lowes.com/search") == "Access Denied"
    assert p.wall_reason("Error Page", "https://www.homedepot.com/s/x") == "Error Page"
    assert p.wall_reason("", "https://www.walmart.com/blocked?url=x") == "blocked"
    assert p.wall_reason("Amazon.com : x", "https://www.amazon.com/s?k=x") is None


@pytest.mark.parametrize(
    "query, expected",
    [
        ("no dig landscape edging", "no-dig-landscape-edging"),
        ("4 inch tall landscape edging!!", "4-inch-tall-landscape-edging"),
        ("  -- leading and trailing -- ", "leading-and-trailing"),
        ("A" * 60, "a" * 40),
    ],
)
def test_slugify(query, expected):
    # fix batch A5/B9, 2026-09-11: the file-name slug - lower-cased, every
    # run of non-alphanumerics collapsed to one hyphen, trimmed, cut to 40.
    assert p.slugify(query) == expected


# --- parse_attributes: real recon titles --------------------------------------------


@pytest.mark.parametrize(
    "title, expected",
    [
        (
            "Bluepro Landscape Edging, 2 Inch 100 ft Garden Border Edging | 150 Steel Stakes, "
            "Upgraded Reinforced Design, Durable Plastic Landscaping Border for Flower Beds, Lawn & Yard",
            dict(height_in=2.0, length_ft=100.0, material="plastic", stake_count=150, stake_material="steel", no_dig=False, excluded_reason=None),
        ),
        (
            "MIXC Garden Edging Border, 100FT 2 Inch Tall Plastic Landscape Edging with 150 Stakes, "
            "Flexible Tool-Free Lawn Border for Yard, Flower Bed & Landscaping",
            dict(height_in=2.0, length_ft=100.0, material="plastic", stake_count=150, stake_material=None, no_dig=False, excluded_reason=None),
        ),
        (
            "EasyFlex Heavy Duty No-Dig Edging Kit - 100ft., Black",
            dict(height_in=None, length_ft=100.0, material="unknown", stake_count=None, no_dig=True),
        ),
        (
            # Bonviee "2 x 50FT 1.5\"" - the first (earlier) foot figure wins over
            # the later "2 x 50FT" per the range rule; stripping "150 Stainless
            # Steel Stakes" before material detection leaves no material word.
            "Bonviee 100FT Landscape Edging Kit with 150 Stainless Steel Stakes | 2 x 50FT 1.5\" Flexible Rolls "
            "| Easy Install | Professional Garden Edging Borders for Flower Beds, Yards, Tree Rings & Gardens",
            dict(height_in=1.5, length_ft=100.0, material="unknown", stake_count=150, stake_material="steel", no_dig=False),
        ),
        (
            # fix batch A1/B16 (2026-09-11): the full real title - "Paver" is
            # only a listed use, not a decorative stone claim, so the roll
            # tiers by "Plastic Mulch", not stone-look.
            "4-Inch x 33 FT Landscape Edging Border with 50 Spikes, No Dig Garden Edging Lawn Border Kit, "
            "Plastic Mulch Border Flexible for Garden Flower Beds Lawn Yard Pathway Paver (Black)",
            dict(height_in=4.0, length_ft=33.0, material="plastic", stake_count=50, stake_material=None, no_dig=True),
        ),
        (
            # fix batch B16: replaces the earlier 80-char-truncated "4.5 in.
            # Tall Decorative S" fixture, which has no verbatim match in the
            # fix batch's own live-run evidence - this is the real EasyFlex
            # title that evidence actually contains (kept as stone-look per
            # A1: "Stone-Look" is a decorative-material claim, not "paver").
            "EasyFlex No-Dig Landscape Edging with Anchoring Spikes, 2.7 in Tall Decorative "
            "Stone-Look Garden Border, 15 Foot Kit, Slate Gray",
            dict(height_in=2.7, length_ft=15.0, material="stone-look", stake_count=None, no_dig=True),
        ),
        (
            "EasyFlex 2.5\" Tall Wall No-Dig Landscape Edging Kit - 100 Foot, Black",
            dict(height_in=2.5, length_ft=100.0, no_dig=True),
        ),
        (
            "EasyFlex Tall Wall No-Dig Landscape Edging, 90' kit",
            dict(height_in=None, length_ft=90.0, no_dig=True),
        ),
        (
            # fix batch B16: the full real title actually names a height, a
            # length, and a stake count - the old 80-char truncation had cut
            # off exactly that part of the title, making "no height, no
            # length" true only by accident of truncation.
            "Amazon Basics Flexible Landscape Edging Coil for Garden Border, Flower Beds, Lawn and "
            "Pathways, 5 inch x 40ft, Brown, 10 Stakes",
            dict(height_in=5.0, length_ft=40.0, material="unknown", stake_count=10, stake_material=None, no_dig=False),
        ),
        (
            # excluded (fence, not edging); height 13, length 42.5.
            "42.5ft(L) x 13in(H) Animal Barrier Fence, 30 Panels No Dig Garden Fence for Dog",
            dict(height_in=13.0, length_ft=42.5, excluded_reason="fence, not edging", no_dig=True),
        ),
        (
            # U+00D7 multiplication sign, normalized to "x".
            "4 in × 40 FT Landscape Edging No Dig with 36 Spikes, Flexible Plastic Heavy-Duty",
            dict(height_in=4.0, length_ft=40.0, material="plastic", stake_count=36, stake_material=None, no_dig=True),
        ),
        (
            # fix batch B16: the full real title (the 80-char truncation cut
            # off right before "Anchoring Spikes").
            "Quibbay 3.15\" x 100' Landscape Edging, Flexible Garden Edging Borders with 150 Anchoring "
            "Spikes, Plastic Lawn Edging for Landscaping Garden Flower Beds Grass Yard Paver Pathway, Black",
            dict(height_in=3.15, length_ft=100.0, material="plastic", stake_count=150, stake_material=None),
        ),
        (
            # fix batch B16: the full real title.
            "SnugNiture Corrugated Metal Garden Edging,6\"×50'Sturdy Lawn Edging Border,Landscape "
            "Edging Border for Lawn, Flower Bed,Garden and Yard(Black)",
            dict(height_in=6.0, length_ft=50.0, material="metal"),
        ),
        (
            # fix batch B16: the full real title.
            "Metal Landscape Edging 6 Pack 40\" L x 6\" H | 20 FT Galvanized Bendable Metal Garden "
            "Edging,Hammer in Steel Landscape Edging with a Pair of Gloves and 7 Clips,Black",
            dict(height_in=6.0, length_ft=20.0, material="steel"),
        ),
        (
            # fix batch B11/B16 (2026-09-11): the full real title, an L x W x
            # H triple - height must come from the number followed by "H",
            # never an earlier "L"/"W" number ("15.5FT Kit" is the length).
            "Landscape Edging Stone for Lawn Edging,12 Pack 24 Bricks 15.5FT Kit | Landscape Edging "
            "Blocks for Flower Beds, Driveway, Yards, Easy to style, Yards. Each 16.3\" L x 3.5\" W x 2\" H",
            dict(height_in=2.0, length_ft=15.5, material="stone-look"),
        ),
        (
            # fix batch B16: the full real title (the 80-char truncation cut
            # off before "No-Dig Garden Edge Landscaping Edging").
            "Orgrimmar Garden Edging Kit 40PCS Pound-in Interlocking Black(20”x5.3”) | Plastic "
            "No-Dig Garden Edge Landscaping Edging",
            dict(height_in=5.3, length_ft=None, material="plastic", no_dig=True),
        ),
        (
            # fix batch A3/A6/B14/B16 (2026-09-11): the full real title - the
            # old 80-char truncation ended right before "Pieces are 4ft in
            # Length," which is where its own (previously unexplained)
            # length of 4 actually comes from once the real text is used;
            # "(Pack 6)" makes this a per-piece length, not a total.
            "TISHO 3\" x 48\" Black Rubber No Dig Landscape Garden Border Edging (Pack 6)，Made of "
            "100% Recycled Tires，Sturdy, Flexible and Reusable，Pieces are 4ft in Length (Color : Black)",
            dict(height_in=3.0, length_ft=4.0, material="rubber", no_dig=True),
        ),
        (
            "Vigoro60 ft.​ No-​Dig Plastic Landscape Edging Kit",
            dict(length_ft=60.0, material="plastic", no_dig=True),
        ),
        (
            # fix batch B16: the full real title (the trademark symbol is not
            # actually present on the live listing, and the truncation had
            # also cut off "Garden Lawn Border").
            "BSHAPPLUS 4in x 40ft No Dig Landscape Edging Kit with 45 Unbreakable Steel Stakes, "
            "Flexible HDPE Garden Lawn Border",
            dict(height_in=4.0, length_ft=40.0, material="plastic", stake_count=45, stake_material="steel", no_dig=True),
        ),
        (
            "GOTGELIF Landscape Edging 2inch Tall, 40/100ft No-Dig ... with 60/120 Spikes Plastic",
            dict(height_in=2.0, length_ft=40.0, material="plastic", stake_count=60, no_dig=True),
        ),
        (
            "5-Pack Steel Landscape Edging (39x4 in), Bendable Heavy Duty Metal",
            dict(height_in=4.0, length_ft=None, material="steel"),
        ),
    ],
)
def test_parse_attributes_real_titles(title, expected):
    parsed = p.parse_attributes(title)
    for key, value in expected.items():
        assert parsed[key] == value, f"{key}: expected {value!r}, got {parsed[key]!r} for {title!r}"


def test_parse_attributes_stake_phrase_stripped_before_material_detection():
    # research.md D-stakes: "150 Stainless Steel Stakes" must never make a
    # plastic roll register as "steel" via the general material rule.
    title = "Bonviee 100FT Landscape Edging Kit with 150 Stainless Steel Stakes | 2 x 50FT 1.5\" Flexible Rolls"
    parsed = p.parse_attributes(title)
    assert parsed["stake_material"] == "steel"
    assert parsed["material"] != "steel"


def test_parse_attributes_no_no_dig_phrase():
    parsed = p.parse_attributes("Some Product Without The Phrase")
    assert parsed["no_dig"] is False


def test_parse_attributes_stakes_only_excluded():
    parsed = p.parse_attributes("Replacement Stakes Only for Landscape Edging Kit")
    assert parsed["excluded_reason"] == "stakes only"


# --- fix batch A1/B4: material rule drops bare "paver" and bare "stone" ------------


def test_material_paver_alone_does_not_trigger_stone_look():
    # Real title (live JSON, run-4in): a bare "Paver" among the listed uses,
    # no other material word at all -> unknown, never stone-look.
    parsed = p.parse_attributes(
        "40ft Garden Landscape Edging,Landscape Edging with 40 Landscape Spikes,"
        "Paver Edging 2 Inch Tall,Terrace Board Black…"
    )
    assert parsed["material"] == "unknown"


@pytest.mark.parametrize(
    # synthetic, short phrases in the same shape as a real title (NFR-002) -
    # isolates the bare-"stone"/bare-"paver" regression directly.
    "title, expected_material",
    [
        ("Landscape Edging Border for Pavers and Walkways, Flexible Plastic", "plastic"),
        ("Stone Landscape Edging Border, Heavy Duty Plastic", "plastic"),
    ],
)
def test_material_bare_paver_and_bare_stone_no_longer_trigger_stone_look(title, expected_material):
    assert p.parse_attributes(title)["material"] == expected_material


@pytest.mark.parametrize(
    # fix batch A1: these keep classifying as stone-look - each real title
    # names an actual decorative-stone claim, not merely "Paver" among uses.
    "title",
    [
        # Beuta ... Polyrock
        "Beuta DIY No Dig Polyrock Landscape Edging w/Anchoring Spikes, Flexible Brick-Sized Border "
        "for Driveways Yards Trees or Gardens, Each 6-Brick Section 48\" L x 4\" W x 2.25\" H (4, Limewash)",
        # Faux Stone / Stone-Look (same title carries both)
        "Landscape Edging Garden Edging Border Faux Stone Edging,91FT x 2.75 in Tall | Decorative "
        "Stone-Look Garden Border for Flower Bed Edging,Pathway Yard Edging,Lawn Tree and Gardens,"
        "w/ Anchoring Spikes,Brown",
        # Stone Effect
        "Garden Edging Border NO DIG, with Landscape Edging Anchoring Spikes, Black Stone Effect "
        "Plastic Lawn Edging Fencing, Interlocking Yard Lawn Edging for Flower Bed | 24 Ft | 30Pcs | Black |",
        # Stone Texture
        "20-Pack No Dig Garden Edging Borders,20FT Plastic Lawn Edging | with Spikes & Stone Texture - "
        "Easy Interlocking Landscape Edging for Yard, Flower Bed, Driveway, Heavy-Duty & Easy Install",
        # 24 Bricks
        "Landscape Edging Stone for Lawn Edging,12 Pack 24 Bricks 15.5FT Kit | Landscape Edging Blocks "
        "for Flower Beds, Driveway, Yards, Easy to style, Yards. Each 16.3\" L x 3.5\" W x 2\" H",
    ],
)
def test_material_real_decorative_stone_titles_still_stone_look(title):
    assert p.parse_attributes(title)["material"] == "stone-look"


# --- fix batch A2/B5/B13: stake stripping and the decimal-fraction guard -----------


def test_parse_attributes_uncounted_stake_phrase_stripped_before_material():
    # fix batch A2/B5: "with Metal Stakes" (no count) must be stripped just
    # like a counted phrase, so the roll tiers by "Plastic," not "Metal."
    # stake_count/stake_material come from the FIRST COUNTED phrase only, so
    # an uncounted phrase yields both None (documented design choice).
    title = (
        "80FT Landscape Edging Border, 4 Inch Tall Plastic Garden Edging | Heavy Duty 80 Foot "
        "Lawn Edging Border with Metal Stakes for Large Yard Landscaping & Garden Edges"
    )
    parsed = p.parse_attributes(title)
    assert parsed["material"] == "plastic"
    assert parsed["stake_count"] is None
    assert parsed["stake_material"] is None
    assert parsed["height_in"] == 4.0


def test_parse_attributes_counted_pcs_stake_phrase_still_extracted():
    title = (
        "Jorvila No Dig Landscape Edging Kit, 1.5\" x 100' Plastic Garden Edging | 120 Pcs Metal "
        "Spikes, Plastic Material, Flexible Garden Border, Suitable for Lawn, Yard, Landscaping, Flower Beds"
    )
    parsed = p.parse_attributes(title)
    assert parsed["material"] == "plastic"
    assert parsed["stake_count"] == 120
    assert parsed["stake_material"] == "steel"
    assert parsed["height_in"] == 1.5
    assert parsed["length_ft"] == 100.0


def test_parse_attributes_stake_count_decimal_fraction_is_never_read_as_a_count():
    # fix batch B13: "7.8In Height Stakes,20Pcs" must never read a count of 8
    # off the ".8" of "7.8"; resolved as None (the FIRST counted phrase rule
    # never reaches back across a decimal point, and the trailing ",20Pcs"
    # is not treated as a preceding-count phrase for a noun that already
    # passed) - documented choice, see research.md D-stakes.
    title = (
        "6 Inch Tall 20Ft Black Garden Edging Border with 7.8In Height Stakes,20Pcs | Decorative "
        "Landscape Edging with Garden Stakes for Easy to Install,Durable Garden Border for Defining "
        "Flower Bed,Lawn & Yard"
    )
    parsed = p.parse_attributes(title)
    assert parsed["stake_count"] is None
    assert parsed["stake_material"] is None


def test_parse_attributes_stake_count_decimal_inch_before_anchoring_stakes_is_none():
    title = (
        "Vashly No-Dig 20Ft Landscape Edging, 6 Inch Tall Garden Edging with 7.8 inch Anchoring "
        "Stakes Plastic Garden Edging Border Flower Bed Edging Borders Lawn Edging"
    )
    parsed = p.parse_attributes(title)
    assert parsed["stake_count"] is None
    assert parsed["stake_material"] is None


# --- fix batch A3/B2: the foot mark must be a lone single quote -------------------


@pytest.mark.parametrize(
    "title, expected_height, expected_length",
    [
        (
            "4'' X 100' Landscape Edging Border Kit, Black | Include 90 Anchoring Spikes, for Garden "
            "Lawn Grass Yard Home School",
            4.0,
            100.0,
        ),
        (
            "Metal Landscape Edging Border 6 Packs 42'' L x 4.5'' H, Galvanized Steel Garden Edging "
            "Border with 6 Stakes, Hammer-in Lawn Edging for Landscaping, Flower Bed, Yard, Pathway, "
            "Tree Ring (21ft Total)",
            4.5,
            21.0,  # fix batch B14's total marker, not the out-of-range 42
        ),
        (
            "Metal Landscape Edging 6 Pack,40'' L x 6'' H | Heavy Duty Rust-Proof, Easy to Cut & Bend,"
            "for Flower Beds, Lawn, Pathway & Garden Borders",
            6.0,
            None,  # only double-primes present - no lone single-quote or ft/foot candidate
        ),
    ],
)
def test_double_prime_is_never_a_foot_mark(title, expected_height, expected_length):
    parsed = p.parse_attributes(title)
    assert parsed["height_in"] == expected_height
    assert parsed["length_ft"] == expected_length


# --- fix batch B11/B12: height in an L x W x H triple, and the window fix ----------


def test_height_in_l_w_h_triple_comes_from_the_h_marked_number():
    title = (
        "Beuta DIY No Dig Polyrock Landscape Edging w/Anchoring Spikes, Flexible Brick-Sized Border "
        "for Driveways Yards Trees or Gardens, Each 6-Brick Section 48\" L x 4\" W x 2.25\" H (4, Limewash)"
    )
    assert p.parse_attributes(title)["height_in"] == 2.25


def test_height_in_l_w_h_triple_second_real_title():
    title = (
        "Landscape Edging Stone for Lawn Edging,12 Pack 24 Bricks 15.5FT Kit | Landscape Edging "
        "Blocks for Flower Beds, Driveway, Yards, Easy to style, Yards. Each 16.3\" L x 3.5\" W x 2\" H"
    )
    assert p.parse_attributes(title)["height_in"] == 2.0


def test_height_window_never_matches_a_mid_word_truncated_l():
    # fix batch B12: the 8-char length-marker window used to match the
    # truncated "L" of "Landscape" (the window cut ended exactly there),
    # dropping a valid height. The window must never split a word - and,
    # separately, a digit that starts a new dimension ("100'") ends the
    # window outright.
    title = "Gardzen 1.5\" x100' Landscape Edging Kit with 120 Spikes | Garden Edging Coil for Lawn Borders and Landscape Projects, Easy No Dig Installation with Durable Ground Stakes Included"
    parsed = p.parse_attributes(title)
    assert parsed["height_in"] == 1.5
    assert parsed["length_ft"] == 100.0


def test_height_h_marker_reads_from_the_real_worth_title():
    # The brief's own illustrative fragment ("WORTH ... 6-Pack 5.5\"H x
    # 40\"L Panels" -> height 5.5, length None) elides the real title's own
    # leading "20ft" - fix batch B16 requires the FULL verbatim title, whose
    # length is legitimately 20 (a real, earlier "20ft" candidate), not
    # None; the height fix (5.5, not the "L"-marked 40) still holds.
    title = (
        "WORTH Garden 20ft Landscape Edging Pre-Rusted 14-Gauge Corten Steel | Heavy Duty Metal "
        "Garden Edging Border, 6-Pack 5.5\"H x 40\"L Panels, No-Dig Hammer-in Lawn & Yard Edging "
        "with 7 Clamps & Gloves"
    )
    parsed = p.parse_attributes(title)
    assert parsed["height_in"] == 5.5
    assert parsed["length_ft"] == 20.0
    assert parsed["material"] == "steel"


# --- fix batch A6/B14: the total-length marker and per-piece packs ----------------


@pytest.mark.parametrize(
    "title, expected_length",
    [
        (
            "SnugNiture 2 Rolls Corrugated Metal Garden Edging,4\" x 50' Landscape Edging Border,"
            "Sturdy Metal Lawn Edging for Landscaping, Garden,Flower Bed and Yard(Total 100 Ft)",
            100.0,
        ),
        (
            "Garden Border Edging Roll【4 Inch High】 66FT Total (2 Rolls of 33FT) with 100 Hard "
            "Stakes, Flexible Plastic No Dig Landscape Edging for Lawn, Garden, Flower Beds, Paver "
            "& Walkway Edges",
            66.0,
        ),
    ],
)
def test_total_length_marker_wins_over_every_other_candidate(title, expected_length):
    assert p.parse_attributes(title)["length_ft"] == expected_length


def test_per_piece_length_is_not_mistaken_for_a_total():
    # "Pieces are 4ft in Length" is a per-piece figure, not a title-stated
    # grand total - the total-marker regexes must not fire on it.
    title = (
        "TISHO 3\" x 48\" Black Rubber No Dig Landscape Garden Border Edging (Pack 6)，Made of "
        "100% Recycled Tires，Sturdy, Flexible and Reusable，Pieces are 4ft in Length (Color : Black)"
    )
    assert p.parse_attributes(title)["length_ft"] == 4.0


@pytest.mark.parametrize(
    "title, expected",
    [
        ("5 Piece Steel Home Kit Raw Steel Edging with 15 Edge Pins, 4\" by 8', 18-Gauge", True),
        ("Metal Landscape Edging 6 Pack 40\" L x 6\" H | 20 FT Galvanized Bendable Metal Garden Edging", True),
        (
            # the real, reversed-order title ("Pack 6," word before count) -
            # is_pack widened deliberately to cover it (documented below).
            "TISHO 3\" x 48\" Black Rubber No Dig Landscape Garden Border Edging (Pack 6)，Made of "
            "100% Recycled Tires，Sturdy, Flexible and Reusable，Pieces are 4ft in Length (Color : Black)",
            True,
        ),
        ("SnugNiture Corrugated Metal Garden Edging,6\"×50'Sturdy Lawn Edging Border,Landscape "
         "Edging Border for Lawn, Flower Bed,Garden and Yard(Black)", False),
        (
            # a stake count expressed as "Pcs" must not itself look like a
            # physical multi-piece pack - checked on the stake-stripped text.
            "Jorvila No Dig Landscape Edging Kit, 1.5\" x 100' Plastic Garden Edging | 120 Pcs Metal "
            "Spikes, Plastic Material, Flexible Garden Border, Suitable for Lawn, Yard, Landscaping, "
            "Flower Beds",
            False,
        ),
    ],
)
def test_is_pack(title, expected):
    # Note: `is_pack`'s own regex, `\b\d+\s*(?:pack|pcs|piece|pc)s?\b`, only
    # names the digit-first order the brief's own two examples use ("5
    # Piece", "6 Pack"); the real TISHO recon title uses the reversed order
    # ("(Pack 6)"), so the shipped regex additionally accepts a
    # word-then-count order to cover it (a deliberate widening beyond the
    # letter of the given pattern, documented in research.md D6 and
    # PATTERNS.md). A stake count phrased as "Pcs" ("120 Pcs Metal Spikes")
    # is excluded because `is_pack` checks the stake-stripped text.
    assert p.is_pack(title) is expected


# --- price_per_ft, scoring monotonicity, folding, tiers -----------------------------


def test_price_per_ft():
    assert p.price_per_ft(44.0, 100) == 0.44
    assert p.price_per_ft(None, 100) is None
    assert p.price_per_ft(44.0, None) is None
    assert p.price_per_ft(44.0, 0) is None


def test_score_better_rating_wins_at_equal_price():
    better = _listing(rating=4.8, reviews=500, price=44.0, length_ft=100)
    worse = _listing(rating=4.2, reviews=500, price=44.0, length_ft=100)
    assert p.score_listing(better) > p.score_listing(worse)


def test_score_cheaper_wins_at_equal_rating():
    cheap = _listing(rating=4.5, reviews=100, price=30.0, length_ft=100)
    pricey = _listing(rating=4.5, reviews=100, price=80.0, length_ft=100)
    assert p.score_listing(cheap) > p.score_listing(pricey)


def test_score_shrinks_a_tiny_review_count_toward_the_prior():
    five_with_three = _listing(rating=5.0, reviews=3, price=40.0, length_ft=100)
    four_six_with_600 = _listing(rating=4.6, reviews=600, price=40.0, length_ft=100)
    assert p.score_listing(four_six_with_600) > p.score_listing(five_with_three)


def test_score_unknown_price_per_ft_is_flagged_not_crashed():
    listing = _listing(rating=4.5, reviews=100, price=None, length_ft=None)
    score = p.score_listing(listing)
    assert isinstance(score, float)
    assert "price unknown" in listing.flags


def test_score_length_unknown_flag_when_price_known_but_length_missing():
    listing = _listing(rating=4.5, reviews=100, price=40.0, length_ft=None)
    p.score_listing(listing)
    assert "length unknown" in listing.flags


def test_score_unrated_flag_when_rating_is_none():
    # fix batch B3 (FR-024): a missing rating is flagged "unrated," not left
    # silently indistinguishable from a rated-at-the-prior listing.
    listing = _listing(rating=None, reviews=None, price=40.0, length_ft=100)
    p.score_listing(listing)
    assert "unrated" in listing.flags


def test_score_sponsored_penalty():
    organic = _listing(rating=4.5, reviews=100, price=40.0, length_ft=100, sponsored=False)
    sponsored = _listing(rating=4.5, reviews=100, price=40.0, length_ft=100, sponsored=True)
    assert p.score_listing(organic) - p.score_listing(sponsored) == pytest.approx(0.1, abs=0.001)


def test_score_position_is_a_weak_term():
    early = _listing(rating=4.5, reviews=100, price=40.0, length_ft=100, position=0)
    late = _listing(rating=4.5, reviews=100, price=40.0, length_ft=100, position=40)
    assert p.score_listing(early) - p.score_listing(late) == pytest.approx(0.2, abs=0.001)


def test_fold_duplicates_prefers_organic_and_keeps_best_position():
    sponsored = _listing(url="https://www.amazon.com/dp/X", position=5, page=1, sponsored=True)
    organic = _listing(url="https://www.amazon.com/dp/X", position=2, page=1, sponsored=False)
    (kept,) = p.fold_duplicates([sponsored, organic])
    assert kept.sponsored is False
    assert kept.position == 2


def test_fold_duplicates_unions_found_on_pages():
    page1 = _listing(url="https://www.amazon.com/dp/X", position=1, page=1)
    page2 = _listing(url="https://www.amazon.com/dp/X", position=1, page=2)
    (kept,) = p.fold_duplicates([page1, page2])
    assert kept.found_on_pages == [1, 2]


def test_fold_duplicates_distinct_urls_kept_separate():
    a = _listing(url="https://www.amazon.com/dp/A")
    b = _listing(url="https://www.amazon.com/dp/B")
    assert len(p.fold_duplicates([a, b])) == 2


@pytest.mark.parametrize(
    "material, expected_tier",
    [
        ("plastic", "plastic"),
        ("rubber", "plastic"),
        ("unknown", "plastic"),
        ("steel", "metal"),
        ("aluminum", "metal"),
        ("metal", "metal"),
        ("wood", "other"),
        ("stone-look", "other"),
    ],
)
def test_tier(material, expected_tier):
    assert p.tier(material) == expected_tier


def test_rank_excludes_and_sorts_by_score_then_price_per_ft_then_title():
    good = _listing(title="B Listing", rating=4.8, reviews=500, price=40.0, length_ft=100, material="plastic")
    cheaper_same_score_tier = _listing(title="A Listing", rating=4.8, reviews=500, price=40.0, length_ft=100, material="plastic")
    fenced = _listing(title="Fence", material="plastic", excluded_reason="fence, not edging")
    for listing in (good, cheaper_same_score_tier, fenced):
        listing.price_per_ft = p.price_per_ft(listing.price, listing.length_ft)
        listing.score = p.score_listing(listing)
    result = p.rank([good, cheaper_same_score_tier, fenced])
    assert [listing.title for listing in result.tiers["plastic"]] == ["A Listing", "B Listing"]
    assert result.tiers["metal"] == []
    assert result.tiers["other"] == []
    assert [listing.title for listing in result.excluded] == ["Fence"]
    assert result.dropped_by_height == []


# --- fix batch B3/B6/B8: rank()'s own min_height_in, excluded, dropped_by_height ---


def test_rank_min_height_in_drops_short_listings_and_flags_unknown_height():
    tall = _listing(title="Tall", price=40.0, length_ft=100, material="plastic", height_in=6.0)
    short = _listing(title="Short", price=40.0, length_ft=100, material="plastic", height_in=1.0)
    unknown_height = _listing(title="Unknown", price=40.0, length_ft=100, material="plastic", height_in=None)
    for listing in (tall, short, unknown_height):
        listing.price_per_ft = p.price_per_ft(listing.price, listing.length_ft)
        listing.score = p.score_listing(listing)
    result = p.rank([tall, short, unknown_height], min_height_in=3)
    titles = [listing.title for listing in result.tiers["plastic"]]
    assert "Short" not in titles
    assert "Tall" in titles and "Unknown" in titles
    assert [listing.title for listing in result.dropped_by_height] == ["Short"]
    kept_unknown = next(listing for listing in result.tiers["plastic"] if listing.title == "Unknown")
    assert "height unknown" in kept_unknown.flags


def test_rank_exclusion_runs_before_height_drop():
    # fix batch B8: a fenced listing that ALSO fails the height check is
    # counted as excluded, never as dropped-by-height.
    fenced_and_short = _listing(title="Fenced Short", material="plastic", excluded_reason="fence, not edging", height_in=1.0)
    fenced_and_short.score = p.score_listing(fenced_and_short)
    result = p.rank([fenced_and_short], min_height_in=3)
    assert [listing.title for listing in result.excluded] == ["Fenced Short"]
    assert result.dropped_by_height == []


def test_rank_without_min_height_in_never_flags_or_drops_by_height():
    unknown_height = _listing(title="Unknown", price=40.0, length_ft=100, material="plastic", height_in=None)
    unknown_height.price_per_ft = p.price_per_ft(unknown_height.price, unknown_height.length_ft)
    unknown_height.score = p.score_listing(unknown_height)
    result = p.rank([unknown_height])
    assert result.dropped_by_height == []
    assert "height unknown" not in unknown_height.flags


def test_rank_result_is_a_dataclass_with_tiers_excluded_dropped_by_height():
    result = p.rank([])
    assert isinstance(result, p.RankResult)
    assert result.tiers == {"plastic": [], "metal": [], "other": []}
    assert result.excluded == []
    assert result.dropped_by_height == []


# --- parse_reference_literal ---------------------------------------------------------


def test_parse_reference_literal_dollar_and_ft():
    listing = p.parse_reference_literal("BSHAPPLUS 4in x 40ft No Dig Landscape Edging Plastic | $31.58 | 40 ft")
    assert listing.title == "BSHAPPLUS 4in x 40ft No Dig Landscape Edging Plastic"
    assert listing.price == 31.58
    assert listing.length_ft == 40.0
    assert listing.origin == "reference-hand"
    assert listing.height_in == 4.0
    assert listing.material == "plastic"


def test_parse_reference_literal_no_dollar_and_no_ft():
    listing = p.parse_reference_literal("Some Title | 31.58 | 40")
    assert listing.price == 31.58 and listing.length_ft == 40.0
    assert listing.rating is None and listing.reviews is None


def test_parse_reference_literal_optional_rating_and_reviews():
    # fix batch A4, 2026-09-11: a 4th (rating) and 5th (review count) part.
    listing = p.parse_reference_literal("Some Title | 31.58 | 40 | 4.1 | 15")
    assert listing.rating == 4.1
    assert listing.reviews == 15


def test_parse_reference_literal_rating_without_reviews_is_allowed():
    listing = p.parse_reference_literal("Some Title | 31.58 | 40 | 4.1")
    assert listing.rating == 4.1
    assert listing.reviews is None


@pytest.mark.parametrize(
    "text",
    [
        "not enough parts",
        "Title | price only",
        "Title | | 40",
        "Title | not-a-price | 40",
        "Title | 31.58 | not-a-length",
        "",
        # fix batch B7, 2026-09-11: a zero or negative price/length, and an
        # out-of-range rating or a negative review count, are all refused.
        "Title | 31.58 | 0",
        "Title | 31.58 | -5",
        "Title | $0 | 40",
        "Title | 31.58 | 40 | 6",
        "Title | 31.58 | 40 | 4.1 | -1",
    ],
)
def test_parse_reference_literal_malformed_raises(text):
    with pytest.raises(ValueError):
        p.parse_reference_literal(text)


def test_parse_reference_literal_flags_pack_when_length_is_per_piece():
    listing = p.parse_reference_literal("5 Piece Steel Home Kit Raw Steel Edging, 4\" by 8' | 40.0 | 8")
    assert "pack: per-piece length" in listing.flags


# --- rendering -------------------------------------------------------------------


def _scored(**overrides) -> p.Listing:
    listing = _listing(**overrides)
    listing.price_per_ft = p.price_per_ft(listing.price, listing.length_ft)
    listing.score = p.score_listing(listing)
    return listing


def _meta(**overrides) -> dict:
    base = dict(
        query="no dig landscape edging", sites=["amazon"], pages=2, generated_at="2026-09-11T00:00:00Z",
        read=2, unique=2, excluded=0, dropped_by_height=0, ranked=2, notes=[],
    )
    base.update(overrides)
    return base


def test_render_markdown_contains_reference_rank_sentence():
    a = _scored(title="Bluepro Listing", price=43.99, rating=4.5, reviews=158, length_ft=100.0, material="plastic")
    b = _scored(title="EasyFlex Listing", price=87.98, rating=4.6, reviews=200, length_ft=100.0, material="plastic")
    result = p.rank([a, b])
    reference = p.parse_reference_literal("BSHAPPLUS Listing Plastic | $31.58 | 40")
    reference.score = p.score_listing(reference)
    text = p.render_markdown(result, reference, _meta())
    assert "# Product scan" in text
    assert "## Reference listing" in text
    assert "rank #" in text and "in the plastic tier." in text
    assert "REFERENCE" in text
    assert "## Plastic" in text


def test_render_markdown_pins_the_exact_rank_sentence_and_boundaries():
    # fix batch B17, 2026-09-11: SC-007 pinned to the exact sentence, plus
    # both boundary cases (rank #1 of n, and rank #n+1 of n).
    a = _scored(title="A Listing", rating=4.5, reviews=200, price=40.0, length_ft=100.0, material="plastic")
    b = _scored(title="B Listing", rating=4.5, reviews=200, price=50.0, length_ft=100.0, material="plastic")
    result = p.rank([a, b])
    reference = p.parse_reference_literal("Ref Listing Plastic | 90.0 | 100")  # priced worst of the three
    reference.score = p.score_listing(reference)
    text = p.render_markdown(result, reference, _meta())
    assert "Your pick would rank #3 of 3 in the plastic tier." in text

    ref_best = _listing(title="Best", score=10.0)
    ref_worst = _listing(title="Worst", score=0.0)
    group = [_listing(title="A", score=5.0), _listing(title="B", score=4.0)]
    assert p._reference_rank(ref_best, group) == (1, 3)
    assert p._reference_rank(ref_worst, group) == (3, 3)


def test_render_markdown_without_reference_has_no_reference_section():
    a = _scored(title="Only Listing", price=40.0, rating=4.5, reviews=100, length_ft=100.0)
    result = p.rank([a])
    meta = _meta(query="x", pages=1, read=1, unique=1, ranked=1, notes=["note: page skipped for 'homedepot p1' (wall: Error Page)"])
    text = p.render_markdown(result, None, meta)
    assert "## Reference listing" not in text
    assert "note: page skipped for 'homedepot p1' (wall: Error Page)" in text


def test_render_markdown_excluded_counts_and_titles_and_dropped_by_height_section():
    # fix batch B6, 2026-09-11: excluded listings are listed by title (60
    # chars) under their own reason, and a separate "## Dropped by height"
    # section appears (empty or populated).
    fenced = _listing(title="A Fenced Listing Title That Is Long Enough To Exercise The Sixty Character Trim Rule", material="plastic", excluded_reason="fence, not edging")
    short = _listing(title="A Short Listing", material="plastic", height_in=1.0, price=10.0, length_ft=10.0)
    short.price_per_ft = p.price_per_ft(short.price, short.length_ft)
    short.score = p.score_listing(short)
    result = p.rank([fenced, short], min_height_in=3)
    text = p.render_markdown(result, None, _meta(excluded=1, dropped_by_height=1, ranked=0, unique=2))
    assert "fence, not edging: 1" in text
    assert "A Fenced Listing Title That Is Long Enough To Exercise The S" in text  # trimmed to 60
    assert "## Dropped by height" in text
    assert "A Short Listing" in text.split("## Dropped by height", 1)[1]


def test_render_markdown_no_exclusions_or_drops_prints_none_placeholders():
    a = _scored(title="Only Listing", price=40.0, rating=4.5, reviews=100, length_ft=100.0)
    result = p.rank([a])
    text = p.render_markdown(result, None, _meta(query="x", pages=1, read=1, unique=1, ranked=1))
    excluded_section = text.split("## Excluded", 1)[1].split("## Dropped by height", 1)[0]
    dropped_section = text.split("## Dropped by height", 1)[1]
    assert "- (none)" in excluded_section
    assert "- (none)" in dropped_section


def test_render_markdown_header_line_names_all_five_counts():
    # fix batch B8, 2026-09-11: "read", "unique after fold" (before
    # exclusion), "excluded", "dropped by height", "ranked".
    a = _scored(title="Only Listing", price=40.0, rating=4.5, reviews=100, length_ft=100.0)
    fenced = _listing(title="Fenced", material="plastic", excluded_reason="fence, not edging")
    result = p.rank([a, fenced])
    text = p.render_markdown(result, None, _meta(query="x", pages=1, read=5, unique=2, excluded=1, dropped_by_height=0, ranked=1))
    assert "- Listings: 5 read, 2 unique after fold, 1 excluded, 0 dropped by height, 1 ranked" in text


def test_render_markdown_escapes_pipe_in_titles_for_table_integrity():
    # fix batch B1, 2026-09-11: 28 of 78 rows broke in a live run because the
    # real Bonviee title carries three literal "|" characters.
    bonviee = _scored(
        title='Bonviee 100FT Landscape Edging Kit with 150 Stainless Steel Stakes | 2 x 50FT 1.5" '
        "Flexible Rolls | Easy Install | Professional Garden Edging Borders for Flower Beds, Yards, "
        "Tree Rings & Gardens",
        price=43.99, rating=4.5, reviews=100, length_ft=100.0, material="plastic",
        url="https://www.amazon.com/dp/BBBBBBBBBB",
    )
    result = p.rank([bonviee])
    text = p.render_markdown(result, None, _meta(query="x", pages=1, read=1, unique=1, ranked=1))
    # Count only UNESCAPED "|" (a real column delimiter) - "\|" inside the
    # title must not itself count as a delimiter once escaped.
    unescaped_pipe = re.compile(r"(?<!\\)\|")
    header_columns = len(unescaped_pipe.findall(p._TABLE_HEADER))
    data_rows = [line for line in text.splitlines() if line.startswith("| 1 |")]
    assert data_rows, "expected the Bonviee row to render"
    for row in data_rows:
        assert len(unescaped_pipe.findall(row)) == header_columns, row
    assert "\\|" in text  # the title's own "|" characters were in fact escaped


def test_render_json_round_trips():
    a = _scored(title="Listing", price=40.0, rating=4.5, reviews=100, length_ft=100.0)
    result = p.rank([a])
    payload = json.loads(p.render_json(result, None, _meta(query="x", pages=1, read=1, unique=1, ranked=1)))
    assert payload["meta"]["query"] == "x"
    assert payload["reference"] is None
    assert payload["tiers"]["plastic"][0]["title"] == "Listing"
    assert payload["excluded"] == []


def test_render_json_excluded_shape_and_reference_rank_tier():
    # fix batch B6/B3, 2026-09-11: a top-level "excluded" array, and
    # "rank"/"tier"/"tier_size" on the reference object.
    kept = _scored(title="Kept Listing", price=40.0, rating=4.5, reviews=100, length_ft=100.0, material="plastic")
    fenced = _listing(title="Fence Listing", material="plastic", excluded_reason="fence, not edging", url="https://www.amazon.com/dp/FFFFFFFFFF")
    result = p.rank([kept, fenced])
    reference = p.parse_reference_literal("Reference Listing Plastic | 200.0 | 100")  # scores worst
    reference.score = p.score_listing(reference)
    payload = json.loads(p.render_json(result, reference, _meta(query="x", pages=1, read=2, unique=2, excluded=1, ranked=1)))
    assert len(payload["excluded"]) == 1
    assert payload["excluded"][0]["title"] == "Fence Listing"
    assert payload["excluded"][0]["excluded_reason"] == "fence, not edging"
    assert payload["reference"]["tier"] == "plastic"
    assert payload["reference"]["rank"] == 2
    assert payload["reference"]["tier_size"] == 2


def test_a_fence_listing_never_reaches_the_markdown_or_json_report_tables():
    fenced = _listing(title="A Fence Listing", material="plastic", excluded_reason="fence, not edging", url="https://www.amazon.com/dp/GGGGGGGGGG")
    kept = _scored(title="A Kept Listing", price=40.0, rating=4.5, reviews=100, length_ft=100.0, material="plastic")
    result = p.rank([kept, fenced])
    md = p.render_markdown(result, None, _meta(query="x", pages=1, read=2, unique=2, excluded=1, ranked=1))
    payload = json.loads(p.render_json(result, None, _meta(query="x", pages=1, read=2, unique=2, excluded=1, ranked=1)))
    plastic_titles_md = md.split("## Plastic", 1)[1].split("## Notes", 1)[0]
    assert "A Fence Listing" not in plastic_titles_md
    assert all(listing["title"] != "A Fence Listing" for group in payload["tiers"].values() for listing in group)
    # it IS still auditable, in the Excluded section / excluded array:
    assert "A Fence Listing" in md.split("## Excluded", 1)[1]
    assert any(listing["title"] == "A Fence Listing" for listing in payload["excluded"])


# --- Post-batch live re-run findings (2026-09-11): fence precision, total-marker packs ---------

_KEPT_EDGING_WITH_FENCE_WORD = [
    # a brand name that merely contains "Fenc"
    "AggFencer Landscape Edging 4in Tall Garden Edging Borders No Dig 33ft | Flexible Landscaping Edging Kit for Flower Bed Lawn Yard Grass Black with 61 Pcs Spikes",
    # "fence" in a use list on corrugated steel edging
    "LAVEVE Corrugated Metal Garden Edging 6\" x 40Ft, Landscape Edging Border | Galvanized Steel Garden Border for Lawn, Yard Pathway, Flower Bed, Garden Fence, Paver Edging (Black)",
    # a decorative edging kit whose finish is described as a fence look
    "EasyFlex No-Dig Landscape Edging with Anchoring Spikes, 4.5 in. Tall Decorative Adirondack Wood-Look Fence Garden Border, 15 Foot Kit, White (3600WT-15C-6)",
    # "Mini Fence Borders" marketing on a plastic roll
    "VEVOR Landscape Edging, 66 ft x 4 in Plastic Garden Border Edging with 60 Spikes & 2 Ground Stakes, No Dig, Flexible Lawn Edgings Roll, UV-Resistant Mini Fence Borders for Flower Beds Yard Paver",
    # interlocking stone-look edging sold as "Garden Border Panels"
    "Imitation Stone Garden Fence Edging Border , Interlocking No Dig Stone Look Landscape Edging Fence for Flower Beds, Lawn, Yard & Pathway, Decorative Plastic Outdoor Garden Border Panels, 10PCS Gray",
    "Landscape Edging 33FT, 4IN Tall Garden Edging Borders with 50pcs Stakes, Plastic Lawn Edging Kit, Tools-Free Flexible Fence Edge DIY for Yard, Flowerbeds, Tree, Landscaping, Pathway, Grass, Black",
]

_REAL_FENCES = [
    "42.5ft(L) x 13in(H) Animal Barrier Fence, 30 Panels No Dig Garden Fence for Dog Rabbit, Rustproof Anti Digging Barrier, Garden Edging Border Ground Defense for Outdoor, Yard, Patio",
    "Decorative Garden Fence 17in x10ft, 10 Pack Rustproof Metal No Dig Fence Animal Barrier for Dog, Arched Flower Bed Edging Ornamental Wire Border Panel Fencing for Yard Patio Outdoor Decor",
    "Goovilla Garden Fence, Total 10ft(L) x 24in(H), 10 Pcs, Rustproof Metal | Garden Fencing Animal Barrier, Fence Panels,Black No Dig Fence,Decorative Garden Fences and Borders for Dogs,Flower Bed,Patio",
    "25 Panels Garden Fencing Animal Barrier, 17in (H) X 27ft (L) Dog Dig Fence Barrier, 1.25in Gap Rustproof Metal Stakes Decorative Garden Fence, Ground Defense Border Fence for Outdoor, Yard, Patio",
    "Thealyn 18\"H x 22\"W Decorative Metal Garden Border Fence, 5 Panels, 9.17Ft | Rust-resistant coating | No dig installation | Flexible design | Flower beds, paths, yards & landscape edging",
    "HIHADUUM 20Ft(L) X 13Inch(H) Animal Barrier Fence - 14 Pack Garden Fence Panels, Metal Garden Edging Fence Border No Dig Fencing for Dog Rabbits Ground Stakes Defense and Outdoor Patio Fence Extension",
]


@pytest.mark.parametrize("title", _KEPT_EDGING_WITH_FENCE_WORD)
def test_edging_that_merely_mentions_a_fence_is_not_excluded(title):
    assert p.parse_attributes(title)["excluded_reason"] is None


@pytest.mark.parametrize("title", _REAL_FENCES)
def test_a_real_fence_or_animal_barrier_is_excluded(title):
    assert p.parse_attributes(title)["excluded_reason"] == "fence, not edging"


_SIX_PACK_WITH_TOTAL = (
    "Metal Landscape Edging Border 6 Packs 42'' L x 4.5'' H, Galvanized Steel Garden Edging Border "
    "with 6 Stakes, Hammer-in Lawn Edging for Landscaping, Flower Bed, Yard, Pathway, Tree Ring (21ft Total)"
)


def test_a_pack_whose_title_states_its_total_is_not_flagged_per_piece():
    assert p.is_pack(_SIX_PACK_WITH_TOTAL) is True
    assert p.has_total_marker(_SIX_PACK_WITH_TOTAL) is True
    assert p.pack_flag_applies(_SIX_PACK_WITH_TOTAL) is False
    assert p.parse_attributes(_SIX_PACK_WITH_TOTAL)["length_ft"] == 21.0


def test_a_pack_without_a_stated_total_keeps_the_per_piece_flag():
    title = "5 Piece Steel Home Kit Raw Steel Edging with 15 Edge Pins, 4\" by 8', 18-Gauge"
    assert p.pack_flag_applies(title) is True
    assert p.has_total_marker(title) is False


def test_reference_literal_pack_with_total_carries_no_per_piece_flag():
    listing = p.parse_reference_literal(_SIX_PACK_WITH_TOTAL + " | 44.99 | 21")
    assert "pack: per-piece length" not in listing.flags
