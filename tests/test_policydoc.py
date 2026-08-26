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
from headless.policydoc import (
    ExtractionCandidate,
    PolicyReference,
    confirm_candidate,
    derive_asset_key,
    extract_candidate,
    is_excluded,
    read_policy_reference,
    read_policy_reference_provenance,
    write_policy_reference,
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
    assert provenance == ("/tmp/example-policy.pdf", "2026-08-26T12:00:00+00:00")


def test_read_policy_reference_provenance_returns_none_for_a_missing_file(tmp_path):
    assert read_policy_reference_provenance("vehicles-primary", tmp_path) is None


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
