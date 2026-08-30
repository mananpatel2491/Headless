"""Unit tests for headless/capture.py: parse_companies, QuoteCapture
assembly, and the capture file family (spec 005-insurance-quote-comparison,
data-model.md, T016-T017).
"""

from __future__ import annotations

import json
import stat

import pytest

from headless.capture import (
    CurrentPolicy,
    QuoteCapture,
    QuoteInputError,
    assemble_capture,
    parse_companies,
    read_freshest_capture,
    write_capture,
)

# --- parse_companies (T016, SC-008's unit-level half) -----------------------


def test_parse_companies_accepts_a_valid_array():
    assert parse_companies(["progressive", "geico"]) == ["progressive", "geico"]


def test_parse_companies_accepts_the_empty_array():
    # A valid, empty array is not an error (data-model.md's own precedent).
    assert parse_companies([]) == []


def test_parse_companies_rejects_missing_fragment():
    with pytest.raises(QuoteInputError) as exc_info:
        parse_companies(None)
    message = str(exc_info.value)
    assert "feature_configs" in message
    assert "insurance" in message
    assert "companies" in message


def test_parse_companies_rejects_non_array():
    with pytest.raises(QuoteInputError):
        parse_companies("progressive")


def test_parse_companies_rejects_non_string_entry():
    with pytest.raises(QuoteInputError):
        parse_companies(["progressive", 123])


def test_parse_companies_never_echoes_fixture_content_in_the_error():
    distinctive = "TOTALLY-DISTINCTIVE-FIXTURE-VALUE"
    with pytest.raises(QuoteInputError) as exc_info:
        parse_companies([distinctive, 123])
    assert distinctive not in str(exc_info.value)


# --- assemble_capture (T017) -------------------------------------------------


def test_assemble_capture_builds_the_documented_shape():
    raw_fields = {
        "premium.amount": "612.00",
        "premium.term_months": "6",
        "coverage.collision.limit": "500",
        "coverage.collision.deductible": "500",
        "coverage.bodily_injury.limit": "100,000/300,000",
    }
    capture = assemble_capture(
        insurer="progressive",
        source_url="https://example.com/quote",
        fetched_at="2026-08-26T12:00:00+00:00",
        raw_fields=raw_fields,
        package="standard",
    )
    assert capture.insurer == "progressive"
    assert capture.source_url == "https://example.com/quote"
    assert capture.fetched_at == "2026-08-26T12:00:00+00:00"
    assert capture.package == "standard"
    assert capture.premium == {"amount": "612.00", "term_months": "6"}
    by_line = {c["line"]: c for c in capture.coverages}
    assert by_line["collision"]["limit"] == "500"
    assert by_line["collision"]["deductible"] == "500"
    assert by_line["bodily_injury"]["limit"] == "100,000/300,000"
    assert by_line["bodily_injury"]["deductible"] == ""


def test_assemble_capture_ignores_out_of_vocabulary_keys():
    raw_fields = {"premium.amount": "100", "premium.term_months": "6", "some.other.diagnostic": "x"}
    capture = assemble_capture(
        insurer="progressive", source_url="u", fetched_at="t", raw_fields=raw_fields
    )
    assert capture.coverages == []


def test_assemble_capture_package_defaults_to_none():
    capture = assemble_capture(insurer="progressive", source_url="u", fetched_at="t", raw_fields={})
    assert capture.package is None


def test_assemble_capture_missing_vocabulary_key_treated_as_empty_string():
    capture = assemble_capture(insurer="p", source_url="u", fetched_at="t", raw_fields={})
    assert capture.premium == {"amount": "", "term_months": ""}


# --- write_capture / read_freshest_capture -----------------------------------


def _capture(insurer="progressive", fetched_at="2026-08-26T12:00:00+00:00"):
    return QuoteCapture(
        insurer=insurer,
        fetched_at=fetched_at,
        premium={"amount": "100", "term_months": "6"},
        coverages=[{"line": "collision", "limit": "500", "deductible": "500", "premium": ""}],
        source_url="https://example.com",
        package=None,
    )


def test_write_capture_writes_under_captures_and_round_trips(tmp_path):
    capture = _capture()
    path = write_capture(capture, tmp_path)
    assert path.exists()
    assert path.parent.name == "captures"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["insurer"] == "progressive"
    assert data["coverages"][0]["line"] == "collision"


def test_write_capture_writes_at_mode_0600(tmp_path):
    # NIT 6 (Opus verifier, 2026-08-26): reports/ is vault-grade local data
    # - a capture must land at 0600 from creation, not write-then-chmod.
    path = write_capture(_capture(), tmp_path)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_write_capture_never_overwrites_an_earlier_capture_for_the_same_insurer(tmp_path):
    write_capture(_capture(fetched_at="2026-08-26T12:00:00+00:00"), tmp_path)
    write_capture(_capture(fetched_at="2026-08-26T13:00:00+00:00"), tmp_path)
    files = list((tmp_path / "captures").glob("progressive-*.json"))
    assert len(files) == 2


def test_read_freshest_capture_returns_none_when_no_file_exists(tmp_path):
    assert read_freshest_capture("progressive", tmp_path) is None


def test_read_freshest_capture_returns_the_newest_by_filename_timestamp(tmp_path):
    write_capture(_capture(fetched_at="2026-08-26T12:00:00+00:00"), tmp_path)
    write_capture(_capture(fetched_at="2026-08-26T18:00:00+00:00"), tmp_path)
    write_capture(_capture(fetched_at="2026-08-26T15:00:00+00:00"), tmp_path)

    freshest = read_freshest_capture("progressive", tmp_path)

    assert freshest is not None
    assert freshest.fetched_at == "2026-08-26T18:00:00+00:00"


def test_read_freshest_capture_scopes_by_insurer(tmp_path):
    write_capture(_capture(insurer="progressive"), tmp_path)
    write_capture(_capture(insurer="geico", fetched_at="2026-08-26T23:00:00+00:00"), tmp_path)

    freshest = read_freshest_capture("progressive", tmp_path)

    assert freshest is not None
    assert freshest.insurer == "progressive"


def test_read_freshest_capture_returns_none_for_a_malformed_file(tmp_path):
    captures_dir = tmp_path / "captures"
    captures_dir.mkdir(parents=True)
    (captures_dir / "progressive-20260826T120000Z.json").write_text("{not valid json", encoding="utf-8")
    assert read_freshest_capture("progressive", tmp_path) is None


# --- CurrentPolicy round trip (shape only, no parse function - D3) ----------


def test_current_policy_to_dict_and_from_dict_round_trip():
    policy = CurrentPolicy(
        insurer="Sample Mutual",
        premium={"term_months": "6", "amount": "600.00"},
        coverages=[{"line": "collision", "limit": "500", "deductible": "500", "premium": ""}],
    )
    round_tripped = CurrentPolicy.from_dict(json.loads(json.dumps(policy.to_dict())))
    assert round_tripped == policy


# --- spec 007-extraction-fidelity, FR-022, FR-023, D5: the ten schema----
# extension fields.


def test_current_policy_extended_fields_round_trip():
    policy = CurrentPolicy(
        insurer="Sample Mutual",
        premium={"term_months": "12", "amount": "1200.00"},
        coverages=[],
        policy_number="555 666 777",
        effective_date="01/01/2026",
        expiration_date="01/01/2027",
        policy_level_deductibles=[{"label": "Wind/Hail", "value": "1,000"}],
        asset={"vehicle": "Sample Sedan LX", "vin": "TOTALLY-DISTINCTIVE-FIXTURE-VIN"},
        named_insureds=["Test Testerson"],
        excluded_drivers=["Sample Teen"],
        discounts=[{"label": "Multi-Policy", "value": "50"}],
        fees=[{"label": "Policy", "amount": "25"}],
        subtotal="800.00",
    )
    round_tripped = CurrentPolicy.from_dict(json.loads(json.dumps(policy.to_dict())))
    assert round_tripped == policy


def test_current_policy_from_dict_defaults_the_ten_new_fields_when_absent():
    # data-model.md's own cache-compatibility rule: a document written
    # before this feature existed (or the Director's own hand-typed
    # correction omitting them) defaults every one of the ten new fields to
    # its own empty shape - never a KeyError.
    legacy_doc = {
        "insurer": "Sample Mutual",
        "premium": {"term_months": "6", "amount": "600.00"},
        "coverages": [],
    }
    policy = CurrentPolicy.from_dict(legacy_doc)
    assert policy.policy_number == ""
    assert policy.effective_date == ""
    assert policy.expiration_date == ""
    assert policy.policy_level_deductibles == []
    assert policy.asset == {}
    assert policy.named_insureds == []
    assert policy.excluded_drivers == []
    assert policy.discounts == []
    assert policy.fees == []
    assert policy.subtotal == ""
