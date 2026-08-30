"""Unit tests for headless/policydoc.py: PDF extraction, Director
confirmation, and the reports/policy/ cache (spec 005-insurance-quote-comparison,
User Story 3, research.md D15, T019c-T019f).

Every extraction test uses a fake pypdf reader double (a `.pages` list of
objects exposing `extract_text()`) via `extract_candidate`'s own injectable
`reader_factory` - no real binary PDF asset is ever needed, and no `input()`
call ever reaches a real terminal (`confirm_candidate`'s own injectable
`input_fn`).
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from headless.capture import CurrentPolicy
from headless.localllm import LocalModelUnavailable
from headless.policydoc import (
    ConvertedDocument,
    ExtractionCandidate,
    PolicyReference,
    _LOCAL_MODEL_FALLBACK_NOTE,
    _deglue_text,
    _figure_present,
    _local_candidate_is_usable,
    _resolve_authoritative_term,
    _source_digit_tokens,
    apply_sanity_pass,
    confirm_candidate,
    convert_document,
    derive_asset_key,
    derive_term_from_dates,
    extract_candidate,
    extract_candidate_v2,
    generate_candidate_via_local_model,
    is_excluded,
    read_policy_reference,
    read_policy_reference_provenance,
    write_policy_reference,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SCRAMBLED_DECLARATIONS_TEXT = (FIXTURES_DIR / "declarations-scrambled.txt").read_text(encoding="utf-8")

# FIX-FIRST 4 (Opus verifier, 2026-08-29): a source whose only two dates
# are spelled by month name, so no digit token anywhere in the text could
# accidentally equal the derived term "12" (unlike SCRAMBLED_DECLARATIONS_
# TEXT's own numeric "12/01/2026" style dates, whose month component is
# itself the literal digits "12") - this is what makes the FR-019 exemption
# test below actually exercise the exemption, not merely pass because "12"
# happened to already be present as an unrelated token.
DATE_DERIVED_ONLY_TEXT = "Policy Period: January 5, 2025 To: January 5, 2026"

# spec 007-extraction-fidelity, FR-006 through FR-009, D2: an annual
# homeowners-style declarations text (synthetic, structure-only, NFR-002)
# with an unrelated statement date positioned BEFORE the policy-period
# label - exactly research.md's own Defect B shape - followed by the
# label and the real period's own two dates, a year apart, positioned
# AFTER it. Replaces SCRAMBLED_DECLARATIONS_TEXT for every test below that
# exercises successful date-derivation: SCRAMBLED_DECLARATIONS_TEXT's own
# real period dates sit entirely BEFORE its "Policy Period:" label (spec
# 006's original scrambled-column artifact), which the corrected,
# after-only window (FR-007) can no longer derive a term from at all - see
# test_derive_term_from_dates_known_residual_when_both_dates_precede_the_label.
STATEMENT_DATE_BEFORE_LABEL_TEXT = (
    "Sample Assurance Mutual Insurance Company\n"
    "Homeowners Declarations Page (synthetic test fixture - no real policy data)\n\n"
    "Statement Date: 11/01/2025\n\n"
    "Policy Period: From 01/01/2026 To 01/01/2027\n\n"
    "Coverages:\n"
    "Dwelling                         $300,000\n"
    "Medical Payments                 $5,000\n\n"
    "Total Policy Premium: $1,200.00\n"
)


class _FakePage:
    def __init__(self, text: str | None) -> None:
        self._text = text

    def extract_text(self) -> str | None:
        return self._text


class _FakeReader:
    def __init__(self, pages_text: list[str | None]) -> None:
        self.pages = [_FakePage(t) for t in pages_text]


def _reader(pages_text: list[str | None]):
    def factory(path):
        return _FakeReader(pages_text)

    return factory


def _raising_reader(exc: Exception):
    def factory(path):
        raise exc

    return factory


# --- extract_candidate: unreadable / empty --------------------------------


def test_extract_candidate_returns_none_when_the_reader_raises():
    result = extract_candidate(Path("whatever.pdf"), reader_factory=_raising_reader(OSError("bad file")))
    assert result is None


def test_extract_candidate_returns_none_for_a_blank_text_layer():
    result = extract_candidate(Path("x.pdf"), reader_factory=_reader([None, ""]))
    assert result is None


def test_extract_candidate_returns_none_when_zero_coverage_lines_parse():
    text = "Sample Mutual Insurance Company\nPolicy Period: 6 month term\nTotal Premium: $100.00"
    result = extract_candidate(Path("x.pdf"), reader_factory=_reader([text]))
    assert result is None


# --- extract_candidate: each heuristic on a clean input --------------------


_CLEAN_DECLARATIONS_TEXT = (
    "Sample Mutual Insurance Company\n"
    "Auto Policy Declarations Page\n\n"
    "Named Insured: Test Testerson\n"
    "Policy Period: 6 month term, effective 2026-01-01 to 2026-07-01\n\n"
    "Coverages:\n"
    "Bodily Injury Liability          100,000/300,000\n\n"
    "Total Premium: $612.00\n"
)


def test_extract_candidate_clean_input_detects_insurer_term_premium_and_a_line():
    candidate = extract_candidate(Path("x.pdf"), reader_factory=_reader([_CLEAN_DECLARATIONS_TEXT]))

    assert candidate is not None
    assert "Sample" in candidate.insurer
    assert candidate.premium == {"term_months": "6", "amount": "612.00"}
    line = next(c for c in candidate.coverages if c["line"] == "bodily_injury")
    assert line["limit"] == "100,000/300,000"
    assert candidate.warnings == []


def test_extract_candidate_detects_split_limit_pattern_in_isolation():
    text = "Uninsured Motorist   250,000/500,000"
    candidate = extract_candidate(Path("x.pdf"), reader_factory=_reader([text]))
    assert candidate is not None
    line = next(c for c in candidate.coverages if c["line"] == "uninsured_motorist")
    assert line["limit"] == "250,000/500,000"
    assert "no insurer detected" in candidate.warnings
    assert "no term detected" in candidate.warnings
    assert "no premium detected" in candidate.warnings


def test_extract_candidate_detects_deductible_line_pattern_in_isolation():
    text = "Collision   $500 deductible"
    candidate = extract_candidate(Path("x.pdf"), reader_factory=_reader([text]))
    assert candidate is not None
    line = next(c for c in candidate.coverages if c["line"] == "collision")
    assert line["deductible"] == "500"


def test_extract_candidate_detects_dollar_amount_pattern_as_a_limit_fallback():
    text = "Comprehensive   $250 deductible"
    candidate = extract_candidate(Path("x.pdf"), reader_factory=_reader([text]))
    assert candidate is not None
    line = next(c for c in candidate.coverages if c["line"] == "comprehensive")
    # No split-limit pattern here; the dollar-amount fallback provides the limit.
    assert line["limit"] == "250"


def test_extract_candidate_never_raises_on_hostile_text():
    hostile = "\x00\x01 not a declarations page at all $$$///"
    result = extract_candidate(Path("x.pdf"), reader_factory=_reader([hostile]))
    assert result is None  # degrades to None, never a crash


def test_extract_candidate_never_calls_an_llm_or_makes_a_network_call(monkeypatch):
    # SC-022's own unit-level half: no import of any LLM/network client
    # anywhere reachable from extract_candidate. A simple structural proxy:
    # patching socket.create_connection to always raise proves no network
    # call happens during a normal extraction run.
    import socket

    def _forbidden(*args, **kwargs):
        raise AssertionError("extract_candidate must never open a network connection")

    monkeypatch.setattr(socket, "create_connection", _forbidden)
    extract_candidate(Path("x.pdf"), reader_factory=_reader([_CLEAN_DECLARATIONS_TEXT]))


# --- confirm_candidate (T019d) ---------------------------------------------


def _candidate() -> ExtractionCandidate:
    return ExtractionCandidate(
        insurer="Sample Mutual",
        premium={"term_months": "6", "amount": "612.00"},
        coverages=[{"line": "collision", "limit": "500", "deductible": "500", "premium": ""}],
        warnings=[],
    )


def _responses(*values):
    it = iter(values)

    def input_fn(prompt: str) -> str:
        return next(it)

    return input_fn


def test_confirm_candidate_accept_returns_the_candidate_unchanged(capsys):
    confirmed = confirm_candidate(_candidate(), input_fn=_responses("a"))
    assert confirmed == CurrentPolicy(
        insurer="Sample Mutual",
        premium={"term_months": "6", "amount": "612.00"},
        coverages=[{"line": "collision", "limit": "500", "deductible": "500", "premium": ""}],
    )
    # FR-053's own deliberate exception: the candidate is printed.
    assert "Sample Mutual" in capsys.readouterr().out


def test_confirm_candidate_correct_returns_the_corrected_document():
    corrected_json = json.dumps(
        {
            "insurer": "Corrected Insurer",
            "premium": {"term_months": "12", "amount": "1200.00"},
            "coverages": [{"line": "comprehensive", "limit": "250", "deductible": "", "premium": ""}],
        }
    )
    confirmed = confirm_candidate(_candidate(), input_fn=_responses("c", corrected_json))
    assert confirmed.insurer == "Corrected Insurer"
    assert confirmed.premium == {"term_months": "12", "amount": "1200.00"}


def test_confirm_candidate_correct_with_all_thirteen_keys_keeps_every_new_field():
    # IMPORTANT 6 (Opus verifier, 2026-08-30): the prompt now names "the
    # same object printed above" rather than a stale "insurer/premium/
    # coverages" list - this proves a corrected paste retaining every one
    # of CurrentPolicy's own 13 keys (insurer, premium, coverages, plus
    # the ten schema-extension fields; warnings is NOT one of the 13,
    # since a confirmed CurrentPolicy never carries it) round-trips every
    # field, not only the original three.
    corrected_document = {
        "insurer": "Corrected Insurer",
        "premium": {"term_months": "12", "amount": "1200.00"},
        "coverages": [{"line": "comprehensive", "limit": "250", "deductible": "", "premium": ""}],
        "policy_number": "555 666 777",
        "effective_date": "01/01/2026",
        "expiration_date": "01/01/2027",
        "policy_level_deductibles": [{"label": "Wind/Hail", "value": "1,000"}],
        "asset": {"vehicle": "Sample Sedan LX", "vin": "TOTALLY-DISTINCTIVE-FIXTURE-VIN"},
        "named_insureds": ["Test Testerson"],
        "excluded_drivers": ["Sample Teen"],
        "discounts": [{"label": "Multi-Policy", "value": "50"}],
        "fees": [{"label": "Policy", "amount": "25"}],
        "subtotal": "800.00",
    }
    assert len(corrected_document) == 13
    confirmed = confirm_candidate(_candidate(), input_fn=_responses("c", json.dumps(corrected_document)))
    assert confirmed is not None
    for key, value in corrected_document.items():
        assert getattr(confirmed, key) == value


def test_confirm_candidate_correct_with_unparseable_json_returns_none():
    confirmed = confirm_candidate(_candidate(), input_fn=_responses("c", "{not valid json"))
    assert confirmed is None


def test_confirm_candidate_decline_returns_none():
    assert confirm_candidate(_candidate(), input_fn=_responses("d")) is None


def test_confirm_candidate_unrecognized_input_returns_none():
    assert confirm_candidate(_candidate(), input_fn=_responses("whatever")) is None


def test_confirm_candidate_never_calls_the_real_input_builtin(monkeypatch):
    def _forbidden(prompt=""):
        raise AssertionError("confirm_candidate must never call the real input()")

    monkeypatch.setattr("builtins.input", _forbidden)
    confirm_candidate(_candidate(), input_fn=_responses("d"))


# --- spec 007-extraction-fidelity, FR-019 through FR-021, D4 (User Story 3) -
# the confirm-prompt's own distinct warnings section.


def _candidate_with_warnings(*warnings: str) -> ExtractionCandidate:
    return ExtractionCandidate(
        insurer="Sample Mutual",
        premium={"term_months": "6", "amount": "612.00"},
        coverages=[{"line": "collision", "limit": "500", "deductible": "500", "premium": ""}],
        warnings=list(warnings),
    )


def test_confirm_candidate_prints_a_distinct_warnings_section_before_the_json_block_and_question(capsys):
    confirm_candidate(
        _candidate_with_warnings(
            "a proposed premium amount did not appear in the document and was removed",
            "a proposed collision limit did not appear in the document and was removed",
        ),
        input_fn=_responses("d"),
    )
    out = capsys.readouterr().out
    warnings_idx = out.find("2 warning(s)")
    json_header_idx = out.find("Extracted current-policy candidate")
    assert warnings_idx != -1
    assert json_header_idx != -1
    assert warnings_idx < json_header_idx  # FR-019: warnings section prints FIRST
    assert "a proposed premium amount did not appear in the document and was removed" in out
    assert "a proposed collision limit did not appear in the document and was removed" in out
    # FR-021: the section prints IN ADDITION to, never instead of, the full
    # JSON block - which already embeds the same warnings list.
    assert '"warnings"' in out


def test_confirm_candidate_prints_no_warnings_section_when_there_are_zero_warnings(capsys):
    confirm_candidate(_candidate(), input_fn=_responses("d"))
    out = capsys.readouterr().out
    assert "warning(s)" not in out
    assert "Extracted current-policy candidate" in out  # the rest still prints


def test_confirm_candidate_accepted_reference_carries_warnings_into_the_cache(tmp_path):
    # SC-006, SC-007: the Director accepts a candidate carrying warnings;
    # the resulting cache file's own JSON carries the same warnings list.
    # (confirm_candidate itself only returns a CurrentPolicy, which never
    # carries warnings - scripts/policy_extract.py threads the original
    # candidate's own warnings through to PolicyReference, reproduced here.)
    candidate = _candidate_with_warnings("a proposed premium amount did not appear in the document and was removed")
    confirmed = confirm_candidate(candidate, input_fn=_responses("a"))
    assert confirmed is not None
    reference = PolicyReference(
        policy=confirmed,
        asset_key="vehicles-primary",
        source_path="declarations.pdf",
        confirmed_at="2026-08-29T00:00:00+00:00",
        warnings=list(candidate.warnings),
    )
    path = write_policy_reference(reference, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["warnings"] == ["a proposed premium amount did not appear in the document and was removed"]


# --- PolicyReference / cache (T019e) ----------------------------------------


def _reference(asset_key="vehicles-primary") -> PolicyReference:
    return PolicyReference(
        policy=CurrentPolicy(
            insurer="Sample Mutual",
            premium={"term_months": "6", "amount": "612.00"},
            coverages=[{"line": "collision", "limit": "500", "deductible": "500", "premium": ""}],
        ),
        asset_key=asset_key,
        source_path="/tmp/example-policy.pdf",
        confirmed_at="2026-08-26T12:00:00+00:00",
    )


def test_write_policy_reference_writes_under_policy_at_mode_0600(tmp_path):
    path = write_policy_reference(_reference(), tmp_path)
    assert path.parent.name == "policy"
    assert path.name == "vehicles-primary.json"
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_write_policy_reference_content_has_policy_fields_and_provenance(tmp_path):
    path = write_policy_reference(_reference(), tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["insurer"] == "Sample Mutual"
    assert data["source_path"] == "/tmp/example-policy.pdf"
    assert data["confirmed_at"] == "2026-08-26T12:00:00+00:00"


def test_read_policy_reference_round_trips(tmp_path):
    write_policy_reference(_reference(), tmp_path)
    policy = read_policy_reference("vehicles-primary", tmp_path)
    assert policy is not None
    assert policy.insurer == "Sample Mutual"


def test_read_policy_reference_returns_none_for_a_missing_file(tmp_path):
    assert read_policy_reference("vehicles-primary", tmp_path) is None


def test_read_policy_reference_returns_none_for_a_malformed_file(tmp_path):
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    (policy_dir / "vehicles-primary.json").write_text("{not valid json", encoding="utf-8")
    assert read_policy_reference("vehicles-primary", tmp_path) is None


def test_read_policy_reference_provenance_round_trips(tmp_path):
    write_policy_reference(_reference(), tmp_path)
    provenance = read_policy_reference_provenance("vehicles-primary", tmp_path)
    # spec 007-extraction-fidelity, FR-017/FR-018: the tuple gained a 5th
    # element, warnings - [] here since _reference() never sets it.
    assert provenance == ("/tmp/example-policy.pdf", "2026-08-26T12:00:00+00:00", "regex-v1", "pypdf-raw", [])


def test_read_policy_reference_provenance_returns_none_for_a_missing_file(tmp_path):
    assert read_policy_reference_provenance("vehicles-primary", tmp_path) is None


# --- provenance fields (spec 006-policy-extraction-v2, FR-023, FR-024) -----


def test_policy_reference_to_dict_carries_generator_and_converter():
    reference = PolicyReference(
        policy=CurrentPolicy(insurer="Sample Mutual", premium={"term_months": "12", "amount": "1200.00"}, coverages=[]),
        asset_key="vehicles-primary",
        source_path="/tmp/example-policy.pdf",
        confirmed_at="2026-08-26T12:00:00+00:00",
        generator="local-llm:qwen3.5:35b",
        converter="pymupdf4llm",
    )
    data = reference.to_dict()
    assert data["generator"] == "local-llm:qwen3.5:35b"
    assert data["converter"] == "pymupdf4llm"


def test_read_policy_reference_provenance_defaults_to_unknown_for_a_pre_v006_cache_file(tmp_path):
    # data-model.md's own additive-only invariant: a v0.0.5-written cache
    # file has no generator/converter keys at all - absence is "unknown,"
    # never an error.
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    legacy_doc = {
        "insurer": "Sample Mutual",
        "premium": {"term_months": "6", "amount": "612.00"},
        "coverages": [],
        "source_path": "/tmp/example-policy.pdf",
        "confirmed_at": "2026-08-26T12:00:00+00:00",
    }
    (policy_dir / "vehicles-primary.json").write_text(json.dumps(legacy_doc), encoding="utf-8")
    provenance = read_policy_reference_provenance("vehicles-primary", tmp_path)
    # spec 007-extraction-fidelity, SC-006: warnings (absent from this
    # legacy document, same as generator/converter) defaults to [], never
    # an error.
    assert provenance == ("/tmp/example-policy.pdf", "2026-08-26T12:00:00+00:00", "unknown", "unknown", [])


def test_read_policy_reference_provenance_carries_warnings_when_present(tmp_path):
    # spec 007-extraction-fidelity, FR-017, FR-018, SC-006: a reference
    # confirmed with warnings round-trips them through the same provenance
    # reader.
    write_policy_reference(
        PolicyReference(
            policy=CurrentPolicy(insurer="Sample Mutual", premium={"term_months": "6", "amount": ""}, coverages=[]),
            asset_key="vehicles-primary",
            source_path="/tmp/example-policy.pdf",
            confirmed_at="2026-08-26T12:00:00+00:00",
            warnings=["a proposed premium amount did not appear in the document and was removed"],
        ),
        tmp_path,
    )
    provenance = read_policy_reference_provenance("vehicles-primary", tmp_path)
    assert provenance is not None
    assert provenance[4] == ["a proposed premium amount did not appear in the document and was removed"]


def test_derive_asset_key_dots_to_hyphens():
    assert derive_asset_key("vehicles", "primary") == "vehicles-primary"
    assert derive_asset_key("addresses", "home") == "addresses-home"


# --- is_excluded (T019f) ----------------------------------------------------


def test_is_excluded_true_for_n_a_currently_insured():
    assert is_excluded({"currently_insured": "n/a", "policy_doc": "/x.pdf"}) is True


def test_is_excluded_true_for_n_a_policy_doc():
    assert is_excluded({"currently_insured": "yes", "policy_doc": "n/a"}) is True


def test_is_excluded_false_for_absent_fields():
    assert is_excluded({}) is False


def test_is_excluded_false_for_real_values():
    assert is_excluded({"currently_insured": "yes", "policy_doc": "/x.pdf"}) is False


def test_is_excluded_never_mutates_its_input():
    asset = {"currently_insured": "n/a"}
    original = dict(asset)
    is_excluded(asset)
    assert asset == original


# --- derive_term_from_dates (spec 006-policy-extraction-v2, FR-021, D8) -----


def test_derive_term_from_dates_annual_span_yields_12():
    text = "Policy Period: From: 12/01/2025 To: 12/01/2026"
    result = derive_term_from_dates(text)
    assert result is not None
    assert result.term_months == "12"
    assert result.warning is None


def test_derive_term_from_dates_still_yields_12_when_both_dates_follow_the_label():
    # spec 007-extraction-fidelity, FR-007: the window is now after-only,
    # so order among the dates that DO follow the label no longer matters -
    # this reproduces the same "which one reads first" tolerance the old
    # reversed-order test proved, but with both dates correctly positioned
    # after the label (see the residual test immediately below for the
    # shape this correction can no longer recover).
    text = "Policy Period: To: 12/01/2025 From: 12/01/2026"
    result = derive_term_from_dates(text)
    assert result is not None
    assert result.term_months == "12"
    assert result.warning is None


def test_derive_term_from_dates_known_residual_when_both_dates_precede_the_label():
    # spec 007-extraction-fidelity, D2's own accepted trade-off: an
    # after-only window (FR-007) closes Defect B (an unrelated date before
    # the label mis-paired with the real start date) but, as a necessary
    # consequence, can no longer recover a document whose own real period
    # dates sit ENTIRELY before the label with nothing after it at all -
    # this is spec 006's own original scrambled-column artifact shape
    # ("12/01/2026To:12/01/2025From:Policy Period:", reconstructed,
    # research.md). Widening the window back to include "before" text
    # would reopen exactly the class of error this fix exists to close
    # (D2's own "Alternatives considered"), so this is a documented, known
    # residual, not a silent regression - the caller falls back to
    # whichever value its own generator (or an explicit de-glued phrase)
    # already proposed.
    text = "12/01/2026To:12/01/2025From:Policy Period:"
    assert derive_term_from_dates(text) is None


def test_derive_term_from_dates_semiannual_span_yields_6():
    text = "Policy Period: From: 01/01/2026 To: 07/01/2026"
    result = derive_term_from_dates(text)
    assert result is not None
    assert result.term_months == "6"
    assert result.warning is None


def test_derive_term_from_dates_odd_span_yields_exact_count_with_warning():
    text = "Policy Period: From: 01/01/2026 To: 04/01/2026"  # 3 months
    result = derive_term_from_dates(text)
    assert result is not None
    assert result.term_months == "3"
    assert result.warning is not None
    assert "outside the two common terms" in result.warning
    # Value-free: the warning names the computed count, never a document value.
    assert "01/01/2026" not in result.warning


def test_derive_term_from_dates_fewer_than_two_dates_returns_none():
    text = "Policy Period: From: 12/01/2025 (no end date stated anywhere)"
    assert derive_term_from_dates(text) is None


def test_derive_term_from_dates_no_period_label_returns_none():
    text = "12/01/2025 and 12/01/2026 appear here but no period label nearby"
    assert derive_term_from_dates(text) is None


def test_derive_term_from_dates_month_name_format_is_recognized():
    text = "Policy Period: December 1, 2025 to December 1, 2026"
    result = derive_term_from_dates(text)
    assert result is not None
    assert result.term_months == "12"


def test_derive_term_from_dates_known_false_negative_when_a_date_is_glued_to_preceding_digits():
    # NIT 7 (Opus verifier, 2026-08-29): a real date glued directly to
    # preceding, unrelated digits with no separator at all is
    # indistinguishable from a date fragment embedded inside a longer
    # digit run, so the leading negative lookbehind in _DATE_TOKEN_RE
    # skips it - a documented, accepted limitation, not a silent wrong
    # answer. Only "12/01/2025" is recognized here; "12/01/2026" (glued
    # directly onto "999" with no separator) is not, so fewer than two
    # dates are found near the label and the helper contributes nothing.
    text = "Policy Period: Invoice 99912/01/2026 to 12/01/2025"
    assert derive_term_from_dates(text) is None


# --- spec 007-extraction-fidelity, FR-006 through FR-011, D2 (User Story 2) -
# the corrected term-derivation window: scan every label occurrence,
# window after-only, max-minus-min, phrase precedence over date arithmetic.


def test_derive_term_from_dates_ignores_an_unrelated_date_positioned_before_the_label():
    # SC-003: a statement date before the label, followed by the label and
    # the real period's own two dates a year apart, after it. FR-007's
    # after-only window means the statement date can never enter any
    # window at all.
    result = derive_term_from_dates(STATEMENT_DATE_BEFORE_LABEL_TEXT)
    assert result is not None
    assert result.term_months == "12"
    assert result.warning is None


def test_derive_term_from_dates_scans_every_label_occurrence_not_only_the_first():
    # FR-006: the label appears twice - once in a summary section with no
    # dates nearby at all, and again in a detailed schedule with the real
    # period's own two dates immediately after it. Stopping at the first
    # occurrence (spec 006's own original behavior) would find nothing.
    text = (
        "Summary: Policy Period: see schedule below for exact dates.\n\n"
        "Detailed Schedule - Policy Period: 01/01/2026 to 01/01/2027\n"
    )
    result = derive_term_from_dates(text)
    assert result is not None
    assert result.term_months == "12"


def test_derive_term_from_dates_uses_max_minus_min_across_every_window_not_first_two_in_order():
    # FR-008: three dates altogether appear after the (single) label
    # occurrence - a renewal-notice-shaped date sitting between the real
    # start and end dates in reading order. The old "first two encountered"
    # rule would pair the real start date with the renewal-notice date
    # (10 months apart); the corrected max-minus-min rule spans the real
    # start and end dates instead (12 months), regardless of reading order.
    text = "Policy Period: 01/01/2026 renewal notice 11/01/2026 expires 01/01/2027"
    result = derive_term_from_dates(text)
    assert result is not None
    assert result.term_months == "12"
    # IMPORTANT 4 (Opus verifier, 2026-08-30): more than two distinct
    # dates survived (three), so the new value-free multi-date warning
    # fires alongside the correct term.
    assert result.warning is not None
    assert "more than two distinct dates" in result.warning


# --- IMPORTANT 4 (Opus verifier, 2026-08-30): a "Prior Policy Period" ----
# section must never contribute a date to the current period's own span.


def test_derive_term_from_dates_excludes_a_prior_period_immediately_before_the_current_one():
    # Two ADJACENT 6-month periods: a prior period ending exactly where
    # the current one begins. Without the exclusion, max-minus-min across
    # both periods' own dates would derive a false 12.
    text = "Prior Policy Period: 01/01/2026 to 07/01/2026\nPolicy Period: 07/01/2026 to 01/01/2027\n"
    result = derive_term_from_dates(text)
    assert result is not None
    assert result.term_months == "6"


def test_derive_term_from_dates_excludes_a_prior_period_listed_after_the_current_one():
    # The prior period section appears AFTER the current one in the text -
    # the exclusion must work regardless of reading order, and regardless
    # of whether the current period's own broad forward window happens to
    # sweep over the prior section's own text incidentally.
    text = "Policy Period: 07/01/2026 to 01/01/2027\nPrior Policy Period: 01/01/2026 to 07/01/2026\n"
    result = derive_term_from_dates(text)
    assert result is not None
    assert result.term_months == "6"


def test_derive_term_from_dates_excludes_a_previous_and_former_and_expiring_labeled_period_too():
    for word in ("Previous", "Former", "Expiring"):
        text = f"{word} Policy Period: 01/01/2026 to 07/01/2026\nPolicy Period: 07/01/2026 to 01/01/2027\n"
        result = derive_term_from_dates(text)
        assert result is not None, word
        assert result.term_months == "6", word


def test_resolve_authoritative_term_prefers_an_explicit_phrase_over_a_conflicting_date_derived_span():
    # SC-004, acceptance scenario 3: a de-glued "6-month" phrase alongside
    # two period dates that would derive a different term (12 months) - the
    # phrase wins.
    text = "Total 6 month Premium\nPolicy Period: 01/01/2026 to 01/01/2027"
    result = _resolve_authoritative_term(text)
    assert result is not None
    assert result.term_months == "6"
    assert result.source == "phrase"


def test_resolve_authoritative_term_falls_back_to_date_derivation_when_no_phrase_exists():
    result = _resolve_authoritative_term(STATEMENT_DATE_BEFORE_LABEL_TEXT)
    assert result is not None
    assert result.term_months == "12"
    assert result.source == "date"


def test_resolve_authoritative_term_returns_none_when_neither_a_phrase_nor_two_dates_exist():
    assert _resolve_authoritative_term("Sample Assurance Mutual Insurance Company\nTotal Premium: $1,200.00\n") is None


def test_a_glued_phrase_is_undetectable_before_deglue_but_wins_after_it():
    # SC-004: the phrase becomes detectable by spec 006's own existing term
    # pattern only once de-glued - this is the whole reason the de-glue
    # pass must run before the term-derivation helper ever reads the text.
    glued_text = "Total6monthPremium\nPolicy Period: 01/01/2026 to 01/01/2027"
    assert _resolve_authoritative_term(glued_text).source == "date"  # phrase not yet detectable
    deglued_text = _deglue_text(glued_text)
    result = _resolve_authoritative_term(deglued_text)
    assert result.source == "phrase"
    assert result.term_months == "6"


def test_generate_candidate_via_local_model_prefers_an_explicit_phrase_over_the_models_own_conflicting_claim():
    # SC-004, acceptance scenario 4: the local-model candidate's own
    # claimed term disagrees with a phrase found in the de-glued text - the
    # phrase wins, with a value-free note naming the phrase (not the date
    # derivation) as the correction's own source.
    document = ConvertedDocument(
        text="Total 6 month Premium\nPolicy Period: 01/01/2026 to 01/01/2027",
        converter="pymupdf4llm",
    )
    candidate = generate_candidate_via_local_model(
        document,
        model="m",
        url="http://localhost:11434",
        transport=lambda url, payload, timeout: _valid_local_model_response(term_months="12"),
    )
    assert candidate is not None
    assert candidate.premium["term_months"] == "6"
    assert "term_months derived from an explicit N-month phrase overrode the model's own claim" in candidate.warnings
    assert "term_months derived from policy-period dates overrode the model's own claim" not in candidate.warnings


# --- convert_document (spec 006-policy-extraction-v2, FR-001, FR-002, D2) ---


def test_convert_document_uses_the_layout_converter_when_it_succeeds():
    def fake_layout_converter(path):
        return "# Markdown Declarations\n\nSome converted text"

    document = convert_document(Path("x.pdf"), layout_converter=fake_layout_converter)
    assert document is not None
    assert document.converter == "pymupdf4llm"
    assert "Markdown Declarations" in document.text


def test_convert_document_falls_back_to_pypdf_raw_when_the_converter_raises():
    def failing_layout_converter(path):
        raise RuntimeError("pymupdf4llm not available")

    document = convert_document(
        Path("x.pdf"), reader_factory=_reader([_CLEAN_DECLARATIONS_TEXT]), layout_converter=failing_layout_converter
    )
    assert document is not None
    assert document.converter == "pypdf-raw"
    assert document.text == _CLEAN_DECLARATIONS_TEXT


def test_convert_document_falls_back_when_the_converter_returns_empty_text():
    document = convert_document(
        Path("x.pdf"), reader_factory=_reader([_CLEAN_DECLARATIONS_TEXT]), layout_converter=lambda p: ""
    )
    assert document is not None
    assert document.converter == "pypdf-raw"


def test_convert_document_returns_none_when_neither_path_yields_text():
    document = convert_document(Path("x.pdf"), reader_factory=_reader([""]), layout_converter=lambda p: "")
    assert document is None


def test_convert_document_never_calls_the_real_pymupdf4llm_when_a_fake_is_injected(monkeypatch):
    # NFR-001: no unit test ever performs a real PDF conversion.
    import headless.policydoc as policydoc_module

    def _forbidden(pdf_path: str) -> str:
        raise AssertionError("must never call the real pymupdf4llm default converter in a unit test")

    monkeypatch.setattr(policydoc_module, "_default_layout_converter", _forbidden)
    document = convert_document(Path("x.pdf"), layout_converter=lambda p: "converted text")
    assert document is not None
    assert document.converter == "pymupdf4llm"


# --- _deglue_text (spec 007-extraction-fidelity, FR-012 through FR-016, D3) -


def test_deglue_text_inserts_a_space_at_a_lowercase_to_uppercase_boundary():
    assert _deglue_text("PolicyPeriod") == "Policy Period"


def test_deglue_text_inserts_a_space_at_letter_to_digit_and_digit_to_letter_boundaries():
    # contracts/fidelity.md section 3's own worked shape: a label glued
    # directly to its own digit and unit becomes three separate tokens
    # after both boundary rules apply.
    assert _deglue_text("Total6month") == "Total 6 month"


def test_deglue_text_handles_all_three_boundary_rules_in_one_glued_run():
    assert _deglue_text("Total6monthPremium") == "Total 6 month Premium"


def test_deglue_text_leaves_a_same_case_glued_word_pair_unresolved():
    # FR-015: a known, accepted residual - "eachperson" has no case
    # transition and no digit anywhere at the seam, so there is no
    # boundary signal left for a pure regex to detect; it surfaces
    # unresolved at the Director's own confirmation step.
    assert _deglue_text("eachperson") == "eachperson"
    assert _deglue_text("Allperil") == "Allperil"


def test_deglue_text_never_alters_a_digit_currency_symbol_or_existing_punctuation():
    text = "$1,000.50 All-Perils, 6-month term, NNN-NN-NNNN"
    result = _deglue_text(text)
    # de-glue only ever INSERTS a space at a boundary - every other
    # character (digits, "$", ",", ".", "-") survives unchanged and in the
    # same relative order; stripping whitespace from both sides proves
    # nothing else was altered, added, or removed.
    assert "".join(result.split()) == "".join(text.split())


def test_deglue_text_handles_falsy_input():
    assert _deglue_text("") == ""
    assert _deglue_text(None) == ""


def test_deglue_text_leaves_already_spaced_text_unchanged():
    assert _deglue_text(_CLEAN_DECLARATIONS_TEXT) == _CLEAN_DECLARATIONS_TEXT


# --- BLOCK 1 (Opus verifier, 2026-08-30): the corrected, precise -----------
# letter<->digit rule must never fire inside a real identifier. Every
# shape below is the exact canonical set the verifier's own probe against
# the Director's three real declarations PDFs constructed.


def test_deglue_text_still_deglues_a_glued_label_and_figure():
    # The corrected rule's own positive case, re-confirmed: short digit
    # side, long letter side, <=2 transitions in the run.
    assert _deglue_text("Total6month") == "Total 6 month"


def test_deglue_text_leaves_a_vin_shaped_run_byte_identical():
    # A 17-character VIN-shaped run mixes letters and digits far more
    # densely than a glued label ever does (more than 2 transitions) -
    # condition (a) alone protects it; measured on the real PDFs, the OLD
    # blanket rule reduced VIN-shaped run survival 2 -> 0.
    vin_shaped = "1HGCM82633A123456"
    assert _deglue_text(vin_shaped) == vin_shaped


def test_deglue_text_leaves_a_long_letter_prefix_short_digit_suffix_identifier_unchanged():
    # 1 transition (<=2), but the digit-side segment is long (7 chars,
    # NOT <=3) - condition (b) protects it even with few transitions.
    assert _deglue_text("ABC1234567") == "ABC1234567"


def test_deglue_text_leaves_a_short_letter_suffix_unit_number_unchanged():
    # 1 transition, short digit side (1 char, <=3), but the letter-side
    # segment is only 1 character (NOT >=3) - condition (c) protects it.
    assert _deglue_text("Unit 4B") == "Unit 4B"


def test_deglue_text_leaves_a_label_glued_to_a_long_digit_run_glued_acceptable():
    # 1 transition, long digit side (5 chars, NOT <=3) - stays glued. This
    # is an accepted residual (FR-015): the sanity pass still tokenizes the
    # digit run "60500" on its own merits regardless of the adjacent
    # letters, so nothing is lost for figure-gating purposes.
    assert _deglue_text("Law60500") == "Law60500"


def test_deglue_text_camel_case_surname_residual_is_documented_and_accepted():
    # Known, accepted residual of rule 1 (lowercase-to-uppercase, UNCHANGED
    # by BLOCK 1): a camel-case surname glued by the same converter
    # artifact renders spaced - rule 1 cannot distinguish this from a
    # genuine glued word boundary without a maintained surname exception
    # list (rejected for the same reason D3 already rejects one for the
    # gluing detector itself). Surfaces unresolved at the Director's own
    # confirmation step (named_insureds is a text field, FR-027).
    assert _deglue_text("McDonald") == "Mc Donald"


def test_convert_document_applies_deglue_to_the_layout_converters_own_output():
    def fake_layout_converter(path):
        return "Total6month Premium"

    document = convert_document(Path("x.pdf"), layout_converter=fake_layout_converter)
    assert document is not None
    assert document.text == "Total 6 month Premium"


def test_convert_document_applies_deglue_to_the_pypdf_fallback_text_too():
    # FR-016: the transformation runs regardless of which converter
    # produced the text.
    document = convert_document(
        Path("x.pdf"), reader_factory=_reader(["Total6month Premium"]), layout_converter=lambda p: ""
    )
    assert document is not None
    assert document.converter == "pypdf-raw"
    assert document.text == "Total 6 month Premium"


# --- generate_candidate_via_local_model (spec 006-policy-extraction-v2, FR-004, FR-005, FR-010) ---


class _FakeConfig:
    def __init__(self, ollama_model: str = "test-model", ollama_url: str = "http://localhost:11434") -> None:
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url


def _valid_local_model_response(term_months: str = "") -> dict:
    return {
        "response": json.dumps(
            {
                "insurer": "Sample Assurance Mutual",
                "premium": {"term_months": term_months, "amount": "1200.00"},
                "coverages": [{"line": "medical_payments", "limit": "5,000", "deductible": "", "premium": ""}],
            }
        )
    }


def test_generate_candidate_via_local_model_receives_the_converted_text():
    seen_prompts = []

    def fake_transport(url, payload, timeout):
        seen_prompts.append(payload["prompt"])
        return _valid_local_model_response()

    document = ConvertedDocument(text=SCRAMBLED_DECLARATIONS_TEXT, converter="pymupdf4llm")
    candidate = generate_candidate_via_local_model(
        document, model="m", url="http://localhost:11434", transport=fake_transport
    )
    assert candidate is not None
    assert SCRAMBLED_DECLARATIONS_TEXT in seen_prompts[0]


def test_generate_candidate_via_local_model_derives_term_from_dates_when_omitted():
    # spec 007-extraction-fidelity: STATEMENT_DATE_BEFORE_LABEL_TEXT (not
    # SCRAMBLED_DECLARATIONS_TEXT - see the fixture's own comment above)
    # places an unrelated date before the label and the real period's own
    # two dates after it, which the corrected after-only window derives
    # correctly.
    document = ConvertedDocument(text=STATEMENT_DATE_BEFORE_LABEL_TEXT, converter="pymupdf4llm")
    candidate = generate_candidate_via_local_model(
        document,
        model="m",
        url="http://localhost:11434",
        transport=lambda url, payload, timeout: _valid_local_model_response(term_months=""),
    )
    assert candidate is not None
    assert candidate.premium["term_months"] == "12"
    # Omitted, not wrong - no "overrode" note (FR-020 only fires on disagreement).
    assert "term_months derived from policy-period dates overrode the model's own claim" not in candidate.warnings


def test_generate_candidate_via_local_model_overrides_a_wrong_claimed_term():
    document = ConvertedDocument(text=STATEMENT_DATE_BEFORE_LABEL_TEXT, converter="pymupdf4llm")
    candidate = generate_candidate_via_local_model(
        document,
        model="m",
        url="http://localhost:11434",
        transport=lambda url, payload, timeout: _valid_local_model_response(term_months="1"),
    )
    assert candidate is not None
    assert candidate.premium["term_months"] == "12"
    assert "term_months derived from policy-period dates overrode the model's own claim" in candidate.warnings


def test_generate_candidate_via_local_model_returns_none_on_failure():
    document = ConvertedDocument(text=SCRAMBLED_DECLARATIONS_TEXT, converter="pymupdf4llm")

    def failing_transport(url, payload, timeout):
        raise ConnectionRefusedError("refused")

    candidate = generate_candidate_via_local_model(
        document, model="m", url="http://localhost:11434", transport=failing_transport
    )
    assert candidate is None


# --- apply_sanity_pass (spec 006-policy-extraction-v2, FR-017 through FR-020, SC-002) ---


def test_apply_sanity_pass_strips_a_hallucinated_premium_amount():
    candidate = ExtractionCandidate(
        insurer="Sample Mutual",
        premium={"term_months": "6", "amount": "999999.99"},
        coverages=[],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _CLEAN_DECLARATIONS_TEXT)
    assert result.premium["amount"] == ""
    assert "a proposed premium amount did not appear in the document and was removed" in result.warnings


def test_apply_sanity_pass_strips_a_hallucinated_coverage_limit():
    candidate = ExtractionCandidate(
        insurer="Sample Mutual",
        premium={"term_months": "6", "amount": "612.00"},
        coverages=[{"line": "collision", "limit": "999999", "deductible": "", "premium": ""}],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _CLEAN_DECLARATIONS_TEXT)
    assert result.coverages[0]["limit"] == ""
    assert "a proposed collision limit did not appear in the document and was removed" in result.warnings


def test_apply_sanity_pass_strips_a_hallucinated_deductible():
    candidate = ExtractionCandidate(
        insurer="Sample Mutual",
        premium={"term_months": "6", "amount": "612.00"},
        coverages=[{"line": "collision", "limit": "500", "deductible": "999999", "premium": ""}],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _CLEAN_DECLARATIONS_TEXT)
    assert result.coverages[0]["deductible"] == ""
    assert "a proposed collision deductible did not appear in the document and was removed" in result.warnings


def test_apply_sanity_pass_leaves_a_clean_candidate_unchanged():
    candidate = ExtractionCandidate(
        insurer="Sample Mutual",
        premium={"term_months": "6", "amount": "612.00"},
        coverages=[{"line": "bodily_injury", "limit": "100,000/300,000", "deductible": "", "premium": ""}],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _CLEAN_DECLARATIONS_TEXT)
    assert result.premium["amount"] == "612.00"
    assert result.coverages[0]["limit"] == "100,000/300,000"
    assert result.warnings == []


def test_apply_sanity_pass_never_checks_insurer_or_coverage_line_name():
    candidate = ExtractionCandidate(
        insurer="TOTALLY-DISTINCTIVE-FIXTURE-VALUE Insurance Co",
        premium={"term_months": "", "amount": ""},
        coverages=[{"line": "not-a-real-coverage-line-name", "limit": "", "deductible": "", "premium": ""}],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _CLEAN_DECLARATIONS_TEXT)
    assert result.insurer == "TOTALLY-DISTINCTIVE-FIXTURE-VALUE Insurance Co"
    assert result.coverages[0]["line"] == "not-a-real-coverage-line-name"
    assert result.warnings == []


# --- FIX-FIRST 2 (Opus verifier, 2026-08-29): digit-run token matching ----
# not substring containment. An adversarial review proved the old
# substring-containment check accepted a hallucinated figure sharing a
# digit-run SUFFIX with a real, unrelated figure elsewhere in the source
# (e.g. "50,000" against a source that only ever states "150,000") - every
# case below is a reproduction of that exact class of false negative,
# now correctly stripped.

_TOKEN_MATCH_SOURCE_TEXT = (
    "Sample Assurance Mutual Insurance Company\n"
    "Coverage A: $150,000\n"
    "Coverage B: $2,500\n"
    "Coverage C: $300,000\n"
    "All Perils Deductible: $753.25\n"
    "Bodily Injury Liability          100,000/300,000\n"
    "Total Policy Premium: $15,000.00\n"
)


def test_apply_sanity_pass_strips_a_hallucination_sharing_a_digit_run_suffix_with_150000():
    # "1,500" is a literal substring of "150000" (the old bug's exact
    # reproduction) but is not itself the real figure - must be stripped.
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[{"line": "coverage_a", "limit": "1,500", "deductible": "", "premium": ""}],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _TOKEN_MATCH_SOURCE_TEXT)
    assert result.coverages[0]["limit"] == ""
    assert "a proposed coverage_a limit did not appear in the document and was removed" in result.warnings


def test_apply_sanity_pass_strips_a_hallucination_sharing_a_digit_run_suffix_with_2500():
    # "500" is a literal substring of "2500" - must be stripped.
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[{"line": "coverage_b", "limit": "500", "deductible": "", "premium": ""}],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _TOKEN_MATCH_SOURCE_TEXT)
    assert result.coverages[0]["limit"] == ""
    assert "a proposed coverage_b limit did not appear in the document and was removed" in result.warnings


def test_apply_sanity_pass_strips_a_hallucination_sharing_a_digit_run_prefix_with_300000():
    # "3,000" is a literal substring (prefix) of "300000" - must be stripped.
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": "3,000"},
        coverages=[],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _TOKEN_MATCH_SOURCE_TEXT)
    assert result.premium["amount"] == ""
    assert "a proposed premium amount did not appear in the document and was removed" in result.warnings


def test_apply_sanity_pass_survives_a_real_decimal_figure():
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[{"line": "deductible_line", "limit": "", "deductible": "753.25", "premium": ""}],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _TOKEN_MATCH_SOURCE_TEXT)
    assert result.coverages[0]["deductible"] == "753.25"
    assert result.warnings == []


def test_apply_sanity_pass_tolerates_a_trailing_00_against_an_integer_source_token():
    # "15,000" (proposed) vs the source's own "$15,000.00" - both normalize
    # to the same token ("15000") via the shared trailing-.00 tolerance.
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": "15,000"},
        coverages=[],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _TOKEN_MATCH_SOURCE_TEXT)
    assert result.premium["amount"] == "15,000"
    assert result.warnings == []


def test_apply_sanity_pass_survives_a_split_limit_when_both_tokens_exist():
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[{"line": "bodily_injury", "limit": "100,000/300,000", "deductible": "", "premium": ""}],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _TOKEN_MATCH_SOURCE_TEXT)
    assert result.coverages[0]["limit"] == "100,000/300,000"
    assert result.warnings == []


def test_apply_sanity_pass_never_flags_a_non_numeric_figure_value():
    # NIT 10: a value with no digit at all ("N/A") is not a figure - it
    # passes through untouched rather than being treated as an absent
    # figure worth a warning.
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[{"line": "coverage_a", "limit": "N/A", "deductible": "", "premium": ""}],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _TOKEN_MATCH_SOURCE_TEXT)
    assert result.coverages[0]["limit"] == "N/A"
    assert result.warnings == []


def test_apply_sanity_pass_exempts_a_date_derived_term_from_the_literal_check():
    # FIX-FIRST 4 (Opus verifier, 2026-08-29): SCRAMBLED_DECLARATIONS_TEXT's
    # own dates ("12/01/2026", "12/01/2025") each contain "12" as their own
    # month component, so a candidate claiming term_months "12" against
    # that fixture would pass the literal-match check on its own merits -
    # never actually exercising the FR-019 exemption this test claims to
    # prove. This fixture spells its dates by month name instead
    # ("January 5, 2025" / "January 5, 2026"), so no numeric "12" token
    # exists anywhere in the source text at all - verified directly:
    # `_source_digit_tokens(DATE_DERIVED_ONLY_TEXT)` is `{"5", "2025",
    # "2026"}`, and `derive_term_from_dates` still derives `"12"` from the
    # average-day month span between the two dates.
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "12", "amount": ""},
        coverages=[],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, DATE_DERIVED_ONLY_TEXT)
    assert result.premium["term_months"] == "12"
    assert not any("term_months did not appear" in w for w in result.warnings)


def test_apply_sanity_pass_strips_the_same_term_without_the_date_derivation_exemption():
    # The negative control FIX-FIRST 4 also requires: the same claimed
    # term_months, against a source with NO derivable policy-period dates
    # at all (so the FR-019 exemption never applies), is treated as an
    # ordinary un-exempt figure and correctly stripped - proving the
    # exemption above is actually doing something, not merely dormant.
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "12", "amount": ""},
        coverages=[],
        warnings=[],
    )
    no_dates_text = "Sample Assurance Mutual Insurance Company\nTotal Premium: $1,200.00\n"
    assert derive_term_from_dates(no_dates_text) is None
    result = apply_sanity_pass(candidate, no_dates_text)
    assert result.premium["term_months"] == ""
    assert "a proposed term_months did not appear in the document and was removed" in result.warnings


def test_apply_sanity_pass_still_checks_a_non_derived_term_months():
    candidate = ExtractionCandidate(
        insurer="Sample Mutual",
        premium={"term_months": "987", "amount": "612.00"},  # not derivable, not in source
        coverages=[],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _CLEAN_DECLARATIONS_TEXT)
    assert result.premium["term_months"] == ""
    assert "a proposed term_months did not appear in the document and was removed" in result.warnings


def test_apply_sanity_pass_never_strips_a_clean_regex_derived_candidate():
    # A regex match is always a substring of its own source (D5) - the
    # check must trivially pass for it.
    candidate = extract_candidate(Path("x.pdf"), reader_factory=_reader([_CLEAN_DECLARATIONS_TEXT]))
    assert candidate is not None
    result = apply_sanity_pass(candidate, _CLEAN_DECLARATIONS_TEXT)
    assert result.premium == candidate.premium
    assert result.coverages == candidate.coverages
    assert result.warnings == candidate.warnings


# --- spec 007-extraction-fidelity, FR-001 through FR-005, D1: the -------
# corrected per-token gate (User Story 1 / SC-001, SC-002). Every amount
# below is wholly synthetic (NFR-002) - structural reproductions of
# research.md's own reconstructed shapes, never a real figure.

_COMPOSITE_FIGURE_SOURCE_TEXT = (
    "Sample Assurance Mutual Insurance Company\n"
    "Personal Liability          12,345 each person/54,321 each accident\n"
    "All Perils Deductible: 2,222 All peril\n"
    "Policy Number: 111 222 333\n"
    "Coverage A: $150,000\n"
    "Coverage B: $2,500\n"
)


def test_figure_present_accepts_a_split_composite_figure_with_row_labels():
    # SC-001, contracts section 1's own worked shape: "<A> each person/<B>
    # each accident" - every digit run is a member of the source's own
    # token set, so the check passes even though each part also carries
    # label words the old whole-blob check would have choked on.
    source_tokens = _source_digit_tokens(_COMPOSITE_FIGURE_SOURCE_TEXT)
    assert _figure_present("12,345 each person/54,321 each accident", source_tokens) is True


def test_figure_present_accepts_a_labeled_deductible_cell():
    source_tokens = _source_digit_tokens(_COMPOSITE_FIGURE_SOURCE_TEXT)
    assert _figure_present("2,222 All peril", source_tokens) is True


def test_figure_present_accepts_a_spaced_digit_group_identifier():
    # SC-001: a policy-number-shaped value with internal spaces between
    # three digit groups - the source's own tokenizer already splits it the
    # same way, so each of the three groups is checked as its own token.
    source_tokens = _source_digit_tokens(_COMPOSITE_FIGURE_SOURCE_TEXT)
    assert _figure_present("111 222 333", source_tokens) is True


def test_figure_present_still_strips_a_digit_run_suffix_collision_under_the_corrected_gate():
    # SC-002, FR-005: the hard anti-hallucination invariant is unchanged -
    # "1,500" shares only a digit-run suffix with the source's own
    # "150,000" and must still fail, exactly as spec 006's own FIX-FIRST 2
    # already proved before this correction.
    source_tokens = _source_digit_tokens(_COMPOSITE_FIGURE_SOURCE_TEXT)
    assert _figure_present("1,500", source_tokens) is False


def test_figure_present_still_strips_a_digit_run_prefix_collision_under_the_corrected_gate():
    source_tokens = _source_digit_tokens(_COMPOSITE_FIGURE_SOURCE_TEXT)
    assert _figure_present("2,500 each person/9,999 each accident", source_tokens) is False


def test_figure_present_still_exempts_a_non_numeric_value_under_the_corrected_gate():
    source_tokens = _source_digit_tokens(_COMPOSITE_FIGURE_SOURCE_TEXT)
    assert _figure_present("N/A", source_tokens) is True


def test_apply_sanity_pass_leaves_a_verbatim_composite_figure_unchanged():
    # SC-001, acceptance scenario 1: the corrected sanity pass leaves the
    # composite figure exactly as printed, with no warning for that field.
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[
            {
                "line": "personal_liability",
                "limit": "12,345 each person/54,321 each accident",
                "deductible": "",
                "premium": "",
            }
        ],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _COMPOSITE_FIGURE_SOURCE_TEXT)
    assert result.coverages[0]["limit"] == "12,345 each person/54,321 each accident"
    assert result.warnings == []


def test_apply_sanity_pass_leaves_a_spaced_policy_number_shaped_figure_unchanged():
    # SC-001, acceptance scenario 2 (exercised via a coverage-line figure
    # field here - the dedicated policy_number field is added in the
    # schema-extension phase below and reuses this identical gate).
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[{"line": "identifier", "limit": "111 222 333", "deductible": "", "premium": ""}],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _COMPOSITE_FIGURE_SOURCE_TEXT)
    assert result.coverages[0]["limit"] == "111 222 333"
    assert result.warnings == []


def test_apply_sanity_pass_still_strips_a_hallucination_sharing_only_a_digit_run_with_a_composite_source():
    # SC-002, acceptance scenario 3: a figure sharing a digit-run
    # suffix/prefix with a real source figure, but equal to none of the
    # source's own tokens, is still stripped even under the corrected,
    # composite-figure-tolerant gate.
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[{"line": "coverage_a", "limit": "1,500", "deductible": "", "premium": ""}],
        warnings=[],
    )
    result = apply_sanity_pass(candidate, _COMPOSITE_FIGURE_SOURCE_TEXT)
    assert result.coverages[0]["limit"] == ""
    assert "a proposed coverage_a limit did not appear in the document and was removed" in result.warnings


# --- extract_candidate_v2: end-to-end dispatch (spec 006-policy-extraction-v2) ---


def test_extract_candidate_v2_end_to_end_derives_annual_term_via_local_model():
    # User Story 1 / SC-001: an annual, no-explicit-term-phrase declarations
    # shape with an unrelated date before the label (spec 007-extraction-
    # fidelity's own corrected after-only window), via a fake local-model
    # transport.
    def fake_layout_converter(path):
        return STATEMENT_DATE_BEFORE_LABEL_TEXT

    result = extract_candidate_v2(
        Path("declarations.pdf"),
        config=_FakeConfig(),
        layout_converter=fake_layout_converter,
        transport=lambda url, payload, timeout: _valid_local_model_response(term_months="1"),
    )
    assert result is not None
    candidate, generator_name, converter_name = result
    assert candidate.premium["term_months"] == "12"
    assert generator_name == "local-llm:test-model"
    assert converter_name == "pymupdf4llm"


def test_extract_candidate_v2_cached_reference_shape_carries_provenance(tmp_path):
    def fake_layout_converter(path):
        return SCRAMBLED_DECLARATIONS_TEXT

    result = extract_candidate_v2(
        Path("declarations.pdf"),
        config=_FakeConfig(),
        layout_converter=fake_layout_converter,
        transport=lambda url, payload, timeout: _valid_local_model_response(term_months="12"),
    )
    assert result is not None
    candidate, generator_name, converter_name = result
    confirmed = confirm_candidate(candidate, input_fn=_responses("a"))
    assert confirmed is not None
    reference = PolicyReference(
        policy=confirmed,
        asset_key="vehicles-primary",
        source_path="declarations.pdf",
        confirmed_at="2026-08-29T00:00:00+00:00",
        generator=generator_name,
        converter=converter_name,
    )
    path = write_policy_reference(reference, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["generator"] == "local-llm:test-model"
    assert data["converter"] == "pymupdf4llm"


def test_v2_pipeline_declined_confirmation_never_caches_regardless_of_generator(tmp_path):
    def fake_layout_converter(path):
        return SCRAMBLED_DECLARATIONS_TEXT

    result = extract_candidate_v2(
        Path("x.pdf"),
        config=_FakeConfig(),
        layout_converter=fake_layout_converter,
        transport=lambda url, payload, timeout: _valid_local_model_response(),
    )
    assert result is not None
    candidate, _generator_name, _converter_name = result
    confirmed = confirm_candidate(candidate, input_fn=_responses("d"))
    assert confirmed is None
    assert not (tmp_path / "policy").exists()


# --- extract_candidate_v2: fallback matrix (spec 006-policy-extraction-v2, US3) ---


def test_extract_candidate_v2_falls_back_to_regex_on_connection_failure():
    def fake_layout_converter(path):
        return SCRAMBLED_DECLARATIONS_TEXT

    def failing_transport(url, payload, timeout):
        raise ConnectionRefusedError("refused")

    result = extract_candidate_v2(
        Path("x.pdf"), config=_FakeConfig(), layout_converter=fake_layout_converter, transport=failing_transport
    )
    assert result is not None
    candidate, generator_name, _converter_name = result
    assert generator_name == "regex-v1"
    assert candidate.warnings.count("local model unavailable, fell back to the regex-based generator") == 1


def test_extract_candidate_v2_falls_back_to_regex_on_missing_model():
    def fake_layout_converter(path):
        return SCRAMBLED_DECLARATIONS_TEXT

    def failing_transport(url, payload, timeout):
        raise OSError("model not found")

    result = extract_candidate_v2(
        Path("x.pdf"), config=_FakeConfig(), layout_converter=fake_layout_converter, transport=failing_transport
    )
    assert result is not None
    assert result[1] == "regex-v1"


def test_extract_candidate_v2_falls_back_to_regex_on_timeout():
    def fake_layout_converter(path):
        return SCRAMBLED_DECLARATIONS_TEXT

    def failing_transport(url, payload, timeout):
        raise TimeoutError("timed out")

    result = extract_candidate_v2(
        Path("x.pdf"), config=_FakeConfig(), layout_converter=fake_layout_converter, transport=failing_transport
    )
    assert result is not None
    assert result[1] == "regex-v1"


def test_extract_candidate_v2_falls_back_to_regex_on_empty_response():
    def fake_layout_converter(path):
        return SCRAMBLED_DECLARATIONS_TEXT

    result = extract_candidate_v2(
        Path("x.pdf"),
        config=_FakeConfig(),
        layout_converter=fake_layout_converter,
        transport=lambda url, payload, timeout: {"response": ""},
    )
    assert result is not None
    candidate, generator_name, _converter_name = result
    assert generator_name == "regex-v1"
    assert "local model unavailable, fell back to the regex-based generator" in candidate.warnings


def test_extract_candidate_v2_falls_back_to_regex_on_non_json_response():
    def fake_layout_converter(path):
        return SCRAMBLED_DECLARATIONS_TEXT

    result = extract_candidate_v2(
        Path("x.pdf"),
        config=_FakeConfig(),
        layout_converter=fake_layout_converter,
        transport=lambda url, payload, timeout: {"response": "not valid json {{{"},
    )
    assert result is not None
    assert result[1] == "regex-v1"


def test_extract_candidate_v2_falls_back_to_regex_on_schema_mismatch():
    def fake_layout_converter(path):
        return SCRAMBLED_DECLARATIONS_TEXT

    result = extract_candidate_v2(
        Path("x.pdf"),
        config=_FakeConfig(),
        layout_converter=fake_layout_converter,
        transport=lambda url, payload, timeout: {"response": json.dumps({"not": "the right shape"})},
    )
    assert result is not None
    assert result[1] == "regex-v1"


def test_extract_candidate_v2_with_use_llm_false_never_calls_the_transport():
    def _forbidden_transport(url, payload, timeout):
        raise AssertionError("must never call the local-model transport when use_llm=False")

    result = extract_candidate_v2(
        Path("x.pdf"),
        config=_FakeConfig(),
        reader_factory=_reader([_CLEAN_DECLARATIONS_TEXT]),
        layout_converter=lambda p: "",  # force the pypdf-raw fallback path
        transport=_forbidden_transport,
        use_llm=False,
    )
    assert result is not None
    candidate, generator_name, converter_name = result
    assert generator_name == "regex-v1"
    assert converter_name == "pypdf-raw"
    assert "local model unavailable" not in " ".join(candidate.warnings)


def test_extract_candidate_v2_returns_none_for_an_empty_converted_document():
    # SC-007: a converted document with no extractable text at all still
    # yields None, never a crash.
    result = extract_candidate_v2(
        Path("x.pdf"),
        config=_FakeConfig(),
        reader_factory=_reader([""]),
        layout_converter=lambda p: "",
    )
    assert result is None


def test_extract_candidate_v2_returns_none_when_regex_fallback_finds_zero_coverage_lines():
    text = "Sample Mutual Insurance Company\nPolicy Period: 6 month term\nTotal Premium: $100.00"
    result = extract_candidate_v2(
        Path("x.pdf"),
        config=_FakeConfig(),
        reader_factory=_reader([text]),
        layout_converter=lambda p: "",
        use_llm=False,
    )
    assert result is None


# --- FIX-FIRST 1 (Opus verifier, 2026-08-29): schema-valid but unusable ---
# a local-model response with zero coverages, or every figure field empty,
# must never be confirmed as-is - it is treated exactly like a failed
# attempt (contracts/extraction-v2.md section 1's own classification
# table gains this row) and the regex-based generator runs instead.


def test_extract_candidate_v2_falls_back_to_regex_when_local_candidate_has_zero_coverages():
    def fake_layout_converter(path):
        return SCRAMBLED_DECLARATIONS_TEXT

    def empty_coverages_transport(url, payload, timeout):
        return {
            "response": json.dumps(
                {
                    "insurer": "Sample Assurance Mutual",
                    "premium": {"term_months": "12", "amount": ""},
                    "coverages": [],
                }
            )
        }

    result = extract_candidate_v2(
        Path("x.pdf"),
        config=_FakeConfig(),
        layout_converter=fake_layout_converter,
        transport=empty_coverages_transport,
    )
    assert result is not None
    candidate, generator_name, _converter_name = result
    assert generator_name == "regex-v1"
    assert _LOCAL_MODEL_FALLBACK_NOTE in candidate.warnings


def test_extract_candidate_v2_falls_back_to_regex_when_local_candidate_has_no_figures_at_all():
    def fake_layout_converter(path):
        return SCRAMBLED_DECLARATIONS_TEXT

    def all_empty_figures_transport(url, payload, timeout):
        return {
            "response": json.dumps(
                {
                    "insurer": "Sample Assurance Mutual",
                    "premium": {"term_months": "", "amount": ""},
                    "coverages": [
                        {"line": "medical_payments", "limit": "", "deductible": "", "premium": ""}
                    ],
                }
            )
        }

    result = extract_candidate_v2(
        Path("x.pdf"),
        config=_FakeConfig(),
        layout_converter=fake_layout_converter,
        transport=all_empty_figures_transport,
    )
    assert result is not None
    candidate, generator_name, _converter_name = result
    assert generator_name == "regex-v1"
    assert _LOCAL_MODEL_FALLBACK_NOTE in candidate.warnings
    # The Director never sees the empty candidate the model actually
    # returned - the regex-derived one (a real coverage line) wins instead.
    assert candidate.coverages
    assert any(c.get("line") == "medical_payments" and c.get("limit") for c in candidate.coverages)


def test_local_candidate_is_usable_true_when_at_least_one_figure_is_present():
    usable = ExtractionCandidate(
        insurer="X",
        premium={"term_months": "", "amount": ""},
        coverages=[{"line": "collision", "limit": "500", "deductible": "", "premium": ""}],
        warnings=[],
    )
    assert _local_candidate_is_usable(usable) is True


def test_local_candidate_is_usable_false_for_zero_coverages():
    unusable = ExtractionCandidate(insurer="X", premium={"term_months": "", "amount": ""}, coverages=[], warnings=[])
    assert _local_candidate_is_usable(unusable) is False


def test_local_candidate_is_usable_false_when_every_figure_is_empty():
    unusable = ExtractionCandidate(
        insurer="X",
        premium={"term_months": "", "amount": ""},
        coverages=[{"line": "collision", "limit": "", "deductible": "", "premium": ""}],
        warnings=[],
    )
    assert _local_candidate_is_usable(unusable) is False


# --- NIT 8 (Opus verifier, 2026-08-29): the fallback note survives even --
# when the regex path ALSO finds nothing, so a down/unusable local model
# stays distinguishable from a genuinely unreadable PDF.


def test_extract_candidate_v2_prints_the_fallback_note_when_regex_also_finds_nothing(capsys):
    # No auto-insurance coverage keyword anywhere in this text - the
    # regex-based generator's own _COVERAGE_KEYWORDS table cannot recognize
    # any line here (unlike SCRAMBLED_DECLARATIONS_TEXT, which does state
    # "Medical Payments" and would give the regex path a real line to find).
    no_coverage_keyword_text = "Sample Assurance Mutual Insurance Company\nTotal Premium: $1,200.00\n"

    def fake_layout_converter(path):
        return no_coverage_keyword_text

    def failing_transport(url, payload, timeout):
        raise ConnectionRefusedError("refused")

    result = extract_candidate_v2(
        Path("x.pdf"), config=_FakeConfig(), layout_converter=fake_layout_converter, transport=failing_transport
    )
    assert result is None  # the regex generator finds zero coverage lines in this text
    out = capsys.readouterr().out
    assert _LOCAL_MODEL_FALLBACK_NOTE in out


def test_extract_candidate_v2_prints_nothing_extra_when_use_llm_is_false_and_regex_finds_nothing(capsys):
    text = "Sample Mutual Insurance Company\nPolicy Period: 6 month term\nTotal Premium: $100.00"
    result = extract_candidate_v2(
        Path("x.pdf"),
        config=_FakeConfig(),
        reader_factory=_reader([text]),
        layout_converter=lambda p: "",
        use_llm=False,
    )
    assert result is None
    out = capsys.readouterr().out
    assert _LOCAL_MODEL_FALLBACK_NOTE not in out


# --- spec 007-extraction-fidelity, FR-022 through FR-027, D5 (User Story 4) -
# the schema extension's own ten new fields, gated the same way the
# corrected sanity pass already gates every existing figure. Every value
# below is wholly synthetic (NFR-002).

_SCHEMA_EXTENSION_SOURCE_TEXT = (
    "Sample Assurance Mutual Insurance Company\n"
    "Policy Number: 555 666 777\n"
    "Effective Date: 01/01/2026   Expiration Date: 01/01/2027\n"
    "Wind/Hail Deductible: 1,000\n"
    "Multi-Policy Discount: 50\n"
    "Policy Fee: 25\n"
    "Subtotal: 800.00\n"
)


def test_apply_sanity_pass_extended_figure_fields_pass_through_when_verbatim():
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[],
        warnings=[],
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
    result = apply_sanity_pass(candidate, _SCHEMA_EXTENSION_SOURCE_TEXT)
    assert result.policy_number == "555 666 777"
    assert result.effective_date == "01/01/2026"
    assert result.expiration_date == "01/01/2027"
    # FR-024: term_months is COMPUTED from the two dates - never read as a
    # separately proposed value once both parse.
    assert result.premium["term_months"] == "12"
    assert result.policy_level_deductibles[0]["value"] == "1,000"
    assert result.discounts[0]["value"] == "50"
    assert result.fees[0]["amount"] == "25"
    assert result.subtotal == "800.00"
    assert result.warnings == []


def test_apply_sanity_pass_strips_hallucinated_extended_figure_fields():
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[],
        warnings=[],
        policy_number="999 888 777",
        policy_level_deductibles=[{"label": "Wind/Hail", "value": "999999"}],
        discounts=[{"label": "Multi-Policy", "value": "999999"}],
        fees=[{"label": "Policy", "amount": "999999"}],
        subtotal="999999",
    )
    result = apply_sanity_pass(candidate, _SCHEMA_EXTENSION_SOURCE_TEXT)
    assert result.policy_number == ""
    assert result.policy_level_deductibles[0]["value"] == ""
    assert result.discounts[0]["value"] == ""
    assert result.fees[0]["amount"] == ""
    assert result.subtotal == ""
    assert "a proposed policy_number did not appear in the document and was removed" in result.warnings
    assert "a proposed Wind/Hail deductible value did not appear in the document and was removed" in result.warnings
    assert "a proposed Multi-Policy discount value did not appear in the document and was removed" in result.warnings
    assert "a proposed Policy fee amount did not appear in the document and was removed" in result.warnings
    assert "a proposed subtotal did not appear in the document and was removed" in result.warnings


def test_apply_sanity_pass_clears_an_unparseable_effective_or_expiration_date():
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[],
        warnings=[],
        effective_date="not-a-date",
        expiration_date="also-not-a-date",
    )
    result = apply_sanity_pass(candidate, _SCHEMA_EXTENSION_SOURCE_TEXT)
    assert result.effective_date == ""
    assert result.expiration_date == ""
    assert "effective_date could not be parsed as a date and was removed" in result.warnings
    assert "expiration_date could not be parsed as a date and was removed" in result.warnings
    # Neither date parsed: term_months is never computed from them, and
    # falls back to the ordinary (still-empty) handling.
    assert result.premium["term_months"] == ""


# --- BLOCK 2 (Opus verifier, 2026-08-30): a well-formed but fabricated ---
# date must never win term precedence. Every date/figure below is
# synthetic (NFR-002).


def test_apply_sanity_pass_clears_a_well_formed_but_fabricated_effective_or_expiration_date():
    # Both dates PARSE successfully (valid calendar dates) but neither is
    # actually stated anywhere in the source - the exact fabrication BLOCK
    # 2 exists to close: two internally consistent but invented dates must
    # not silently compute and win a term.
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[],
        warnings=[],
        effective_date="03/03/2099",
        expiration_date="03/03/2100",
    )
    result = apply_sanity_pass(candidate, _SCHEMA_EXTENSION_SOURCE_TEXT)
    assert result.effective_date == ""
    assert result.expiration_date == ""
    assert "a proposed effective_date did not appear in the document and was removed" in result.warnings
    assert "a proposed expiration_date did not appear in the document and was removed" in result.warnings
    assert result.premium["term_months"] == ""


def test_apply_sanity_pass_verified_dates_outrank_an_explicit_phrase_with_a_disagreement_warning():
    # The de-glued text states an explicit "6-month" phrase, but the
    # candidate's own effective_date/expiration_date are BOTH verified
    # (present in the source, both parse) a full year apart - per the ONE
    # precedence table, verified explicit dates win over a phrase, with a
    # value-free disagreement warning naming both sources' own term
    # values (structural counts, not sensitive).
    source_text = (
        "Sample Assurance Mutual Insurance Company\n"
        "Total 6 month Premium\n"
        "Effective Date: 01/01/2026   Expiration Date: 01/01/2027\n"
    )
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[],
        warnings=[],
        effective_date="01/01/2026",
        expiration_date="01/01/2027",
    )
    result = apply_sanity_pass(candidate, source_text)
    assert result.effective_date == "01/01/2026"
    assert result.expiration_date == "01/01/2027"
    assert result.premium["term_months"] == "12"
    assert (
        "term_months from verified explicit dates (12) overrode an explicit N-month phrase (6)"
        in result.warnings
    )


def test_apply_sanity_pass_verified_dates_matching_the_phrase_produce_no_disagreement_warning():
    source_text = (
        "Sample Assurance Mutual Insurance Company\n"
        "Total 12 month Premium\n"
        "Effective Date: 01/01/2026   Expiration Date: 01/01/2027\n"
    )
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[],
        warnings=[],
        effective_date="01/01/2026",
        expiration_date="01/01/2027",
    )
    result = apply_sanity_pass(candidate, source_text)
    assert result.premium["term_months"] == "12"
    assert not any("overrode" in w for w in result.warnings)


def test_apply_sanity_pass_verified_dates_outrank_the_generators_own_claim_with_a_disagreement_warning():
    # No phrase and no derivable date-window in the source at all (the two
    # explicit fields are the ONLY date information present) - verified
    # dates still outrank whatever the generator itself separately claimed.
    source_text = (
        "Sample Assurance Mutual Insurance Company\n"
        "Effective Date: 01/01/2026   Expiration Date: 01/01/2027\n"
    )
    candidate = ExtractionCandidate(
        insurer="Sample Assurance Mutual",
        premium={"term_months": "1", "amount": ""},
        coverages=[],
        warnings=[],
        effective_date="01/01/2026",
        expiration_date="01/01/2027",
    )
    result = apply_sanity_pass(candidate, source_text)
    assert result.premium["term_months"] == "12"
    assert "term_months from verified explicit dates (12) overrode the generator's own claim (1)" in result.warnings


def test_apply_sanity_pass_never_checks_any_of_the_new_text_fields():
    # T017: mirrors test_apply_sanity_pass_never_checks_insurer_or_coverage_
    # line_name - asset, named_insureds, excluded_drivers, and every entry
    # label are exempt (FR-027), regardless of source-text content.
    candidate = ExtractionCandidate(
        insurer="Sample Mutual",
        premium={"term_months": "", "amount": ""},
        coverages=[],
        warnings=[],
        asset={"address": "TOTALLY-DISTINCTIVE-FIXTURE-ADDRESS"},
        named_insureds=["TOTALLY-DISTINCTIVE-FIXTURE-NAME"],
        excluded_drivers=["TOTALLY-DISTINCTIVE-FIXTURE-DRIVER"],
        policy_level_deductibles=[{"label": "TOTALLY-DISTINCTIVE-FIXTURE-DEDUCTIBLE-LABEL", "value": ""}],
        discounts=[{"label": "TOTALLY-DISTINCTIVE-FIXTURE-DISCOUNT-LABEL", "value": ""}],
        fees=[{"label": "TOTALLY-DISTINCTIVE-FIXTURE-FEE-LABEL", "amount": ""}],
    )
    result = apply_sanity_pass(candidate, _CLEAN_DECLARATIONS_TEXT)
    assert result.asset == {"address": "TOTALLY-DISTINCTIVE-FIXTURE-ADDRESS"}
    assert result.named_insureds == ["TOTALLY-DISTINCTIVE-FIXTURE-NAME"]
    assert result.excluded_drivers == ["TOTALLY-DISTINCTIVE-FIXTURE-DRIVER"]
    assert result.policy_level_deductibles[0]["label"] == "TOTALLY-DISTINCTIVE-FIXTURE-DEDUCTIBLE-LABEL"
    assert result.discounts[0]["label"] == "TOTALLY-DISTINCTIVE-FIXTURE-DISCOUNT-LABEL"
    assert result.fees[0]["label"] == "TOTALLY-DISTINCTIVE-FIXTURE-FEE-LABEL"
    assert result.warnings == []


def test_generate_candidate_via_local_model_captures_the_ten_new_fields():
    # FR-029: the local-model generator reads the ten new fields from the
    # model's own response, same as insurer/premium/coverages already are.
    document = ConvertedDocument(text=_SCHEMA_EXTENSION_SOURCE_TEXT, converter="pymupdf4llm")

    def transport(url, payload, timeout):
        return {
            "response": json.dumps(
                {
                    "insurer": "Sample Assurance Mutual",
                    "premium": {"term_months": "", "amount": ""},
                    "coverages": [],
                    "policy_number": "555 666 777",
                    "effective_date": "01/01/2026",
                    "expiration_date": "01/01/2027",
                    "policy_level_deductibles": [{"label": "Wind/Hail", "value": "1,000"}],
                    "asset": {"address": "TOTALLY-DISTINCTIVE-FIXTURE-ADDRESS"},
                    "named_insureds": ["Test Testerson"],
                    "excluded_drivers": [],
                    "discounts": [{"label": "Multi-Policy", "value": "50"}],
                    "fees": [{"label": "Policy", "amount": "25"}],
                    "subtotal": "800.00",
                }
            )
        }

    candidate = generate_candidate_via_local_model(document, model="m", url="http://localhost:11434", transport=transport)
    assert candidate is not None
    assert candidate.policy_number == "555 666 777"
    assert candidate.effective_date == "01/01/2026"
    assert candidate.expiration_date == "01/01/2027"
    assert candidate.policy_level_deductibles == [{"label": "Wind/Hail", "value": "1,000"}]
    assert candidate.asset == {"address": "TOTALLY-DISTINCTIVE-FIXTURE-ADDRESS"}
    assert candidate.named_insureds == ["Test Testerson"]
    assert candidate.discounts == [{"label": "Multi-Policy", "value": "50"}]
    assert candidate.fees == [{"label": "Policy", "amount": "25"}]
    assert candidate.subtotal == "800.00"


def test_generate_candidate_via_local_model_defaults_the_ten_new_fields_when_the_model_omits_them():
    # The model's own response may omit every new field entirely (spec
    # 006's own original response shape) - none of this feature's own
    # additions may turn that into a schema-mismatch failure.
    document = ConvertedDocument(text=SCRAMBLED_DECLARATIONS_TEXT, converter="pymupdf4llm")
    candidate = generate_candidate_via_local_model(
        document, model="m", url="http://localhost:11434", transport=lambda url, payload, timeout: _valid_local_model_response()
    )
    assert candidate is not None
    assert candidate.policy_number == ""
    assert candidate.effective_date == ""
    assert candidate.expiration_date == ""
    assert candidate.policy_level_deductibles == []
    assert candidate.asset == {}
    assert candidate.named_insureds == []
    assert candidate.excluded_drivers == []
    assert candidate.discounts == []
    assert candidate.fees == []
    assert candidate.subtotal == ""
