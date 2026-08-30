"""Unit tests for headless/compare.py: the deterministic comparison engine
(spec 005-insurance-quote-comparison, User Story 3, research.md D5/D10/D18,
T026-T028b).
"""

from __future__ import annotations

import pytest

from headless.capture import CurrentPolicy, QuoteCapture
from headless.compare import build_comparison, classify_line, normalize_line
from headless.report import render_report


def _current_policy(**overrides) -> CurrentPolicy:
    base = dict(
        insurer="Current Insurer",
        premium={"term_months": "6", "amount": "600.00"},
        coverages=[
            {"line": "Bodily Injury Liability", "limit": "100,000/300,000", "deductible": "", "premium": ""},
            {"line": "Collision", "limit": "500", "deductible": "500", "premium": ""},
        ],
    )
    base.update(overrides)
    return CurrentPolicy(**base)


def _quote(insurer: str, **overrides) -> QuoteCapture:
    base = dict(
        insurer=insurer,
        fetched_at="2026-08-26T12:00:00+00:00",
        premium={"term_months": "6", "amount": "600.00"},
        coverages=[
            {"line": "bodily_injury", "limit": "100,000/300,000", "deductible": "", "premium": ""},
            {"line": "collision", "limit": "500", "deductible": "500", "premium": ""},
        ],
        source_url="https://example.com/quote",
        package=None,
    )
    base.update(overrides)
    return QuoteCapture(**base)


# --- T026: normalization and classification ---------------------------------


def test_normalize_line_maps_differently_worded_names_to_the_same_key():
    assert normalize_line("Bodily Injury Liability") == normalize_line("BI")
    assert normalize_line("bodily injury") == "bodily_injury"


def test_normalize_line_unrecognized_name_is_its_own_stable_key():
    assert normalize_line("Roadside Assistance") == "roadside assistance"


def test_classify_line_better_when_captured_limit_strictly_exceeds_current():
    current = {"line": "collision", "limit": "500", "deductible": "500"}
    captured = {"line": "collision", "limit": "1000", "deductible": "500"}
    assert classify_line(current, captured) == "better"


def test_classify_line_equal_when_both_sides_match_exactly():
    current = {"line": "collision", "limit": "500", "deductible": "500"}
    captured = {"line": "collision", "limit": "500", "deductible": "500"}
    assert classify_line(current, captured) == "equal"


def test_classify_line_worse_when_captured_limit_is_lower():
    current = {"line": "collision", "limit": "500", "deductible": "500"}
    captured = {"line": "collision", "limit": "250", "deductible": "500"}
    assert classify_line(current, captured) == "worse"


def test_classify_line_missing_when_captured_field_value_is_empty_string():
    current = {"line": "collision", "limit": "500", "deductible": "500"}
    assert classify_line(current, {"line": "collision", "limit": "", "deductible": ""}) == "missing"
    assert classify_line(current, None) == "missing"


def test_classify_line_not_comparable_when_no_current_line_exists():
    captured = {"line": "roadside", "limit": "100", "deductible": ""}
    assert classify_line(None, captured) == "not_comparable"


def test_classify_line_not_comparable_on_differing_limit_arity():
    current = {"line": "bi", "limit": "100,000/300,000", "deductible": ""}
    captured = {"line": "bi", "limit": "300,000", "deductible": ""}
    assert classify_line(current, captured) == "not_comparable"


def test_classify_line_worse_wins_even_when_deductible_is_better():
    # A worse limit alongside a better deductible: worse dominates (module's
    # own documented combination rule).
    current = {"line": "collision", "limit": "500", "deductible": "1000"}
    captured = {"line": "collision", "limit": "250", "deductible": "250"}
    assert classify_line(current, captured) == "worse"


# --- T027: ranking rule -------------------------------------------------


def test_no_worse_line_outranks_a_cheaper_quote_with_one_worse_line():
    # SC-006: a quote with zero worse lines, ahead of a cheaper quote that
    # has one worse line - regardless of price.
    flawless_but_pricier = _quote("flawless", premium={"term_months": "6", "amount": "700.00"})
    cheaper_but_worse = _quote(
        "cheaper",
        premium={"term_months": "6", "amount": "300.00"},
        coverages=[
            {"line": "bodily_injury", "limit": "100,000/300,000", "deductible": "", "premium": ""},
            {"line": "collision", "limit": "100", "deductible": "500", "premium": ""},  # worse limit
        ],
    )
    result = build_comparison(
        _current_policy(), {"flawless": flawless_but_pricier, "cheaper": cheaper_but_worse}
    )
    assert [rq.insurer for rq in result.ranked_quotes] == ["flawless", "cheaper"]
    assert result.recommended.insurer == "flawless"


def test_among_no_worse_line_quotes_lower_premium_ranks_first():
    cheap = _quote("cheap", premium={"term_months": "6", "amount": "300.00"})
    pricier = _quote("pricier", premium={"term_months": "6", "amount": "700.00"})
    result = build_comparison(_current_policy(), {"cheap": cheap, "pricier": pricier})
    assert [rq.insurer for rq in result.ranked_quotes] == ["cheap", "pricier"]


def test_premium_and_worse_line_tie_breaks_by_fewer_missing_lines():
    current = _current_policy(
        coverages=[
            {"line": "Collision", "limit": "500", "deductible": "500", "premium": ""},
            {"line": "Comprehensive", "limit": "500", "deductible": "500", "premium": ""},
        ]
    )
    fewer_missing = _quote(
        "fewer_missing",
        premium={"term_months": "6", "amount": "500.00"},
        coverages=[
            {"line": "collision", "limit": "500", "deductible": "500", "premium": ""},
            {"line": "comprehensive", "limit": "500", "deductible": "500", "premium": ""},
        ],
    )
    more_missing = _quote(
        "more_missing",
        premium={"term_months": "6", "amount": "500.00"},
        coverages=[{"line": "collision", "limit": "500", "deductible": "500", "premium": ""}],
    )
    result = build_comparison(current, {"fewer_missing": fewer_missing, "more_missing": more_missing})
    assert [rq.insurer for rq in result.ranked_quotes] == ["fewer_missing", "more_missing"]


def test_rule_trail_states_the_rule_in_plain_language_from_comparison_data():
    quote = _quote("progressive", premium={"term_months": "6", "amount": "500.00"})
    result = build_comparison(_current_policy(), {"progressive": quote})
    assert "recommended because" in result.rule_trail
    assert result.recommended.normalized_premium in result.rule_trail
    assert "600.00" in result.rule_trail  # current_policy's own raw premium appears


# --- FIX-FIRST 4 (Opus verifier, 2026-08-26): mixed-term figures must -----
# --- always carry their own term label, never sit bare beside a monthly --
# --- figure the reader could mistake it for.


def test_current_policy_normalized_premium_uses_the_same_fr067_rules():
    from headless.compare import current_policy_normalized_premium

    policy = _current_policy(premium={"term_months": "6", "amount": "600.00"})
    # 600.00 / 6 = 100.00 exactly - the same Decimal/ROUND_HALF_UP rule
    # every captured quote's own normalized_premium already uses.
    assert current_policy_normalized_premium(policy) == "100.00"


def test_current_policy_normalized_premium_none_when_unparseable():
    from headless.compare import current_policy_normalized_premium

    policy = _current_policy(premium={"term_months": "not-a-number", "amount": "600.00"})
    assert current_policy_normalized_premium(policy) is None


def test_current_premium_label_carries_its_own_term_and_monthly_equivalent():
    from headless.compare import current_premium_label

    policy = _current_policy(premium={"term_months": "6", "amount": "600.00"})
    label = current_premium_label(policy)
    assert "600.00" in label
    assert "6 months" in label
    assert "100.00" in label  # the monthly-equivalent figure, computed the same way


def test_rule_trail_never_shows_the_current_premium_without_its_term():
    # The exact regression FIX-FIRST 4 exists to close: "premium $90.00/mo
    # vs current $600.00" with no term label reads as though $600.00 were
    # also a monthly figure, which it is not (it is a 6-month premium).
    quote = _quote("progressive", premium={"term_months": "6", "amount": "540.00"})
    result = build_comparison(_current_policy(premium={"term_months": "6", "amount": "600.00"}), {"progressive": quote})
    assert "vs current $600.00 per 6 months" in result.rule_trail
    assert "100.00/mo equivalent" in result.rule_trail


def test_rule_trail_worse_line_branch_also_labels_the_current_premiums_term():
    quote = _quote(
        "progressive",
        premium={"term_months": "6", "amount": "540.00"},
        coverages=[{"line": "collision", "limit": "100", "deductible": "500", "premium": ""}],  # worse limit
    )
    result = build_comparison(_current_policy(premium={"term_months": "6", "amount": "600.00"}), {"progressive": quote})
    assert "per 6 months" in result.rule_trail


def test_unparseable_premium_ranks_last_tagged_not_comparable():
    good = _quote("good", premium={"term_months": "6", "amount": "500.00"})
    bad = _quote("bad", premium={"term_months": "not-a-number", "amount": "500.00"})
    result = build_comparison(_current_policy(), {"good": good, "bad": bad})
    assert [rq.insurer for rq in result.ranked_quotes] == ["good", "bad"]
    bad_rq = result.ranked_quotes[-1]
    assert bad_rq.premium_comparable is False
    assert bad_rq.normalized_premium == "premium not comparable"


def test_normalized_premium_uses_decimal_rounding_half_up():
    # 100.00 / 3 = 33.333... -> ROUND_HALF_UP to 2dp -> 33.33
    quote = _quote("x", premium={"term_months": "3", "amount": "100.00"})
    result = build_comparison(None, {"x": quote})
    assert result.ranked_quotes[0].normalized_premium == "33.33"


# --- FIX-FIRST 5 (Opus verifier, 2026-08-26): Decimal("nan")/("inf") must --
# --- never reach build_comparison as a "successfully parsed" figure -------


@pytest.mark.parametrize("hostile_amount", ["nan", "NaN", "$NaN", "Infinity", "inf", "-inf"])
def test_non_finite_premium_amount_ranks_last_never_crashes(hostile_amount):
    good = _quote("good", premium={"term_months": "6", "amount": "500.00"})
    hostile = _quote("hostile", premium={"term_months": "6", "amount": hostile_amount})

    result = build_comparison(_current_policy(), {"good": good, "hostile": hostile})

    assert [rq.insurer for rq in result.ranked_quotes] == ["good", "hostile"]
    hostile_rq = result.ranked_quotes[-1]
    assert hostile_rq.premium_comparable is False
    assert hostile_rq.normalized_premium == "premium not comparable"


def test_non_finite_premium_amount_report_still_renders():
    hostile = _quote("hostile", premium={"term_months": "6", "amount": "Infinity"})
    result = build_comparison(_current_policy(), {"hostile": hostile})
    html = render_report(result, [], [], current_policy=_current_policy())
    assert "premium not comparable" in html


@pytest.mark.parametrize("hostile_deductible", ["nan", "Infinity", "-inf"])
def test_non_finite_deductible_is_not_comparable_never_crashes(hostile_deductible):
    current = {"line": "collision", "limit": "500", "deductible": "500"}
    captured = {"line": "collision", "limit": "500", "deductible": hostile_deductible}
    assert classify_line(current, captured) == "not_comparable"


def test_non_finite_current_deductible_is_not_comparable_never_crashes():
    current = {"line": "collision", "limit": "500", "deductible": "nan"}
    captured = {"line": "collision", "limit": "500", "deductible": "500"}
    assert classify_line(current, captured) == "not_comparable"


# --- T028: determinism -------------------------------------------------


def test_build_comparison_is_deterministic_regardless_of_dict_insertion_order():
    quote_a = _quote("aaa", premium={"term_months": "6", "amount": "500.00"})
    quote_b = _quote("bbb", premium={"term_months": "6", "amount": "400.00"})

    first = build_comparison(_current_policy(), {"aaa": quote_a, "bbb": quote_b})
    second = build_comparison(_current_policy(), {"bbb": quote_b, "aaa": quote_a})

    assert [rq.insurer for rq in first.ranked_quotes] == [rq.insurer for rq in second.ranked_quotes]
    assert first.rule_trail == second.rule_trail


# --- T028b: no-current-policy fallback (FR-046) -----------------------------


def test_no_current_policy_has_current_policy_is_false():
    quote = _quote("progressive")
    result = build_comparison(None, {"progressive": quote})
    assert result.has_current_policy is False


def test_no_current_policy_line_classifications_are_empty():
    quote = _quote("progressive")
    result = build_comparison(None, {"progressive": quote})
    assert result.ranked_quotes[0].line_classifications == {}


def test_no_current_policy_ranks_by_monthly_equivalent_premium_ascending():
    cheap = _quote("cheap", premium={"term_months": "6", "amount": "300.00"})
    pricier = _quote("pricier", premium={"term_months": "6", "amount": "700.00"})
    result = build_comparison(None, {"cheap": cheap, "pricier": pricier})
    assert [rq.insurer for rq in result.ranked_quotes] == ["cheap", "pricier"]


def test_no_current_policy_rule_trail_states_no_reference_on_file():
    quote = _quote("progressive", premium={"term_months": "6", "amount": "300.00"})
    result = build_comparison(None, {"progressive": quote})
    assert "no current-policy reference on file" in result.rule_trail


def test_no_current_policy_unparseable_premium_still_ranks_last():
    good = _quote("good", premium={"term_months": "6", "amount": "500.00"})
    bad = _quote("bad", premium={"term_months": "", "amount": ""})
    result = build_comparison(None, {"good": good, "bad": bad})
    assert [rq.insurer for rq in result.ranked_quotes] == ["good", "bad"]


def test_empty_captures_produces_no_recommendation_and_empty_rule_trail():
    result = build_comparison(_current_policy(), {})
    assert result.ranked_quotes == []
    assert result.recommended is None
    assert result.rule_trail == ""


# --- spec 007-extraction-fidelity, FR-030, FR-031, D6: alias-table -------
# extension for homeowners coverage lines (research.md Defect F).


def test_normalize_line_maps_standard_collision_to_the_existing_collision_key():
    assert normalize_line("Standard Collision") == "collision"


def test_normalize_line_maps_liability_to_others_and_personal_liability_to_the_same_new_key():
    assert normalize_line("Liability to Others") == normalize_line("Personal Liability")
    assert normalize_line("Personal Liability") == "personal_liability"


@pytest.mark.parametrize(
    "phrasing,expected_key",
    [
        ("Dwelling", "dwelling"),
        ("Other Structures", "other_structures"),
        ("Personal Property", "personal_property"),
        ("Loss of Use", "loss_of_use"),
        ("Medical Payments to Others", "medical_payments_to_others"),
    ],
)
def test_normalize_line_recognizes_the_five_new_homeowners_keys(phrasing, expected_key):
    assert normalize_line(phrasing) == expected_key


def test_normalize_line_personal_injury_protection_pip_already_matched_medical_payments_no_table_change():
    # Regression control (D6's own rationale): this alias already existed
    # in spec 005's own original table (exact-phrasing entries, not
    # substring matches) - confirmed here, not merely assumed.
    assert normalize_line("Personal Injury Protection") == "medical_payments"
    assert normalize_line("PIP") == "medical_payments"


def test_homeowners_coverage_lines_compare_correctly_after_the_alias_extension():
    # SC-009's own end-to-end proof: a current policy's own "Personal
    # Liability" line against a competing quote's own "Liability to
    # Others" phrasing for the identical coverage now normalize to the
    # SAME key and compare against each other, rather than appearing as two
    # unrelated lines (research.md Defect F). Matching, non-empty
    # deductibles on both sides so the deductible sub-comparison itself
    # does not dominate the combined verdict via the module's own
    # documented "not_comparable wins over equal" combination rule
    # (unrelated to this alias change) - see `_combine`.
    current = _current_policy(
        coverages=[{"line": "Personal Liability", "limit": "300,000", "deductible": "0", "premium": ""}]
    )
    quote = _quote(
        "homeowners_insurer",
        coverages=[{"line": "liability to others", "limit": "300,000", "deductible": "0", "premium": ""}],
    )
    result = build_comparison(current, {"homeowners_insurer": quote})
    classifications = result.ranked_quotes[0].line_classifications
    assert classifications == {"personal_liability": "equal"}
