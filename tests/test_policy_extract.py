"""Unit tests for scripts/policy_extract.py's own orchestration (spec
005-insurance-quote-comparison, contracts/walk-capture-report.md section 9,
T019i). `open_vault` is monkeypatched to a `FakeVault` (never the real
`age` binary, never a passphrase prompt) and `extract_candidate`/
`confirm_candidate` are monkeypatched to canned fakes so this suite never
touches a real PDF or a real terminal.
"""

from __future__ import annotations

import json

import pytest

import scripts.policy_extract as policy_extract
from headless.capture import CurrentPolicy
from headless.policydoc import ExtractionCandidate, read_policy_reference

_ELIGIBLE_VEHICLE = {
    "type": "primary",
    "vin": "1SAMPLE0VIN000001",
    "currently_insured": "yes",
    "policy_doc": "/tmp/example-auto-policy.pdf",
}
_EXCLUDED_ADDRESS = {
    "type": "home",
    "line1": "1 Example Street",
    "currently_insured": "n/a",
    "policy_doc": "n/a",
}
_NO_POLICY_DOC_ADDRESS = {
    "type": "rental",
    "line1": "2 Example Street",
}

_PROFILE_DOC = {
    "addresses": [_EXCLUDED_ADDRESS, _NO_POLICY_DOC_ADDRESS],
    "vehicles": [_ELIGIBLE_VEHICLE],
}


class _CountingFakeVault:
    def __init__(self, secrets: dict[str, str]) -> None:
        self._secrets = secrets
        self.get_secret_calls = 0

    def get_secret(self, name: str) -> str:
        self.get_secret_calls += 1
        return self._secrets[name]

    def put_secret(self, name, value):
        raise AssertionError("policy_extract.py must never write to the vault")

    def delete_secret(self, name):
        raise AssertionError("policy_extract.py must never write to the vault")

    def self_test(self) -> bool:
        return True


@pytest.fixture
def fake_vault():
    return _CountingFakeVault({"profile": json.dumps(_PROFILE_DOC)})


@pytest.fixture(autouse=True)
def preview_dir_env(monkeypatch, tmp_path):
    # reports_dir_for(config) derives from config.preview_dir's own sibling
    # (research.md D4); point it at this test's own tmp tree so nothing
    # touches the real repository's reports/ directory.
    monkeypatch.setenv("HEADLESS_PREVIEW_DIR", str(tmp_path / "previews"))
    return tmp_path


@pytest.fixture
def wired(monkeypatch, fake_vault):
    monkeypatch.setattr(policy_extract, "open_vault", lambda config: fake_vault)
    extraction_calls: list[str] = []
    confirm_calls: list[str] = []

    def fake_extract_candidate(pdf_path):
        extraction_calls.append(str(pdf_path))
        return ExtractionCandidate(
            insurer="Sample Mutual",
            premium={"term_months": "6", "amount": "612.00"},
            coverages=[{"line": "collision", "limit": "500", "deductible": "500", "premium": ""}],
            warnings=[],
        )

    def fake_confirm_candidate(candidate):
        confirm_calls.append(candidate.insurer)
        return CurrentPolicy(insurer=candidate.insurer, premium=candidate.premium, coverages=candidate.coverages)

    monkeypatch.setattr(policy_extract, "extract_candidate", fake_extract_candidate)
    monkeypatch.setattr(policy_extract, "confirm_candidate", fake_confirm_candidate)
    return {"vault": fake_vault, "extraction_calls": extraction_calls, "confirm_calls": confirm_calls}


def test_processes_only_the_eligible_asset(wired, capsys):
    exit_code = policy_extract.main([])

    assert exit_code == 0
    assert wired["extraction_calls"] == ["/tmp/example-auto-policy.pdf"]
    out = capsys.readouterr().out
    # No note printed for the excluded asset (FR-062: silent skip).
    assert "addresses-home" not in out


def test_excluded_and_no_policy_doc_assets_never_reach_extraction(wired):
    policy_extract.main([])
    # Only the one eligible vehicle triggers extraction - neither the "n/a"
    # excluded address nor the address with no policy_doc field at all.
    assert len(wired["extraction_calls"]) == 1


def test_confirmed_extraction_is_cached_under_the_derived_asset_key(wired, tmp_path):
    policy_extract.main([])
    policy = read_policy_reference("vehicles-primary", tmp_path / "reports")
    assert policy is not None
    assert policy.insurer == "Sample Mutual"


def test_vault_read_happens_exactly_once_for_the_whole_run(wired):
    policy_extract.main([])
    assert wired["vault"].get_secret_calls == 1


def test_single_asset_path_argument_restricts_to_one_asset(wired):
    exit_code = policy_extract.main(["vehicles.primary"])
    assert exit_code == 0
    assert wired["extraction_calls"] == ["/tmp/example-auto-policy.pdf"]


def test_single_asset_path_argument_for_a_nonexistent_asset_extracts_nothing(wired):
    exit_code = policy_extract.main(["vehicles.secondary"])
    assert exit_code == 0
    assert wired["extraction_calls"] == []


def test_malformed_asset_path_is_a_usage_error(wired, capsys):
    exit_code = policy_extract.main(["not-a-valid-path"])
    assert exit_code == 2
    assert "REFUSED" in capsys.readouterr().out


def test_declined_confirmation_caches_nothing(monkeypatch, fake_vault, tmp_path):
    monkeypatch.setattr(policy_extract, "open_vault", lambda config: fake_vault)
    monkeypatch.setattr(
        policy_extract,
        "extract_candidate",
        lambda pdf_path: ExtractionCandidate(
            insurer="X", premium={"term_months": "6", "amount": "1"}, coverages=[{"line": "collision", "limit": "1"}], warnings=[]
        ),
    )
    monkeypatch.setattr(policy_extract, "confirm_candidate", lambda candidate: None)

    exit_code = policy_extract.main([])

    assert exit_code == 0
    assert read_policy_reference("vehicles-primary", tmp_path / "reports") is None


def test_extraction_returning_none_moves_on_without_caching(monkeypatch, fake_vault, tmp_path):
    monkeypatch.setattr(policy_extract, "open_vault", lambda config: fake_vault)
    monkeypatch.setattr(policy_extract, "extract_candidate", lambda pdf_path: None)
    confirm_called = []
    monkeypatch.setattr(policy_extract, "confirm_candidate", lambda candidate: confirm_called.append(1))

    exit_code = policy_extract.main([])

    assert exit_code == 0
    assert confirm_called == []
    assert read_policy_reference("vehicles-primary", tmp_path / "reports") is None


def test_no_eligible_assets_exits_zero(monkeypatch, tmp_path):
    empty_vault = _CountingFakeVault({"profile": json.dumps({"addresses": [], "vehicles": []})})
    monkeypatch.setattr(policy_extract, "open_vault", lambda config: empty_vault)
    exit_code = policy_extract.main([])
    assert exit_code == 0


def test_malformed_profile_json_refuses(monkeypatch, capsys):
    bad_vault = _CountingFakeVault({"profile": "{not valid json"})
    monkeypatch.setattr(policy_extract, "open_vault", lambda config: bad_vault)
    exit_code = policy_extract.main([])
    assert exit_code == 1
    # NIT 7 (Opus verifier, 2026-08-26): the raised exception is profile's
    # own existing ProfileError (spec 001), not a new class.
    out = capsys.readouterr().out
    assert "REFUSED: vault item 'profile' is not valid JSON" in out


# --- T051d / SC-020: a zero-coverage-lines extraction never aborts the run -


def test_zero_coverage_lines_for_one_asset_does_not_abort_processing_the_rest(monkeypatch, tmp_path):
    # Two eligible assets: the vehicle's own PDF extracts nothing (None,
    # simulating zero coverage lines parsed - FR-058), the rental
    # address's own PDF extracts cleanly. Both must still be attempted.
    two_asset_doc = {
        "addresses": [
            {"type": "rental", "line1": "2 Example Street", "currently_insured": "yes", "policy_doc": "/tmp/rental.pdf"}
        ],
        "vehicles": [_ELIGIBLE_VEHICLE],
    }
    fake_vault = _CountingFakeVault({"profile": json.dumps(two_asset_doc)})
    monkeypatch.setattr(policy_extract, "open_vault", lambda config: fake_vault)

    def fake_extract_candidate(pdf_path):
        if "rental" in str(pdf_path):
            return None  # zero coverage lines parsed - the ordinary degrade, not a crash
        return ExtractionCandidate(
            insurer="Sample Mutual",
            premium={"term_months": "6", "amount": "612.00"},
            coverages=[{"line": "collision", "limit": "500", "deductible": "500", "premium": ""}],
            warnings=[],
        )

    confirm_calls = []
    monkeypatch.setattr(policy_extract, "extract_candidate", fake_extract_candidate)
    monkeypatch.setattr(
        policy_extract,
        "confirm_candidate",
        lambda candidate: confirm_calls.append(candidate.insurer)
        or CurrentPolicy(insurer=candidate.insurer, premium=candidate.premium, coverages=candidate.coverages),
    )

    exit_code = policy_extract.main([])

    assert exit_code == 0  # never a failure - a zero-lines extraction is an ordinary outcome
    # The rental asset (zero lines) produced no confirmation prompt at all;
    # the vehicle asset still reached confirmation and got cached.
    assert confirm_calls == ["Sample Mutual"]
    assert read_policy_reference("vehicles-primary", tmp_path / "reports") is not None
    assert read_policy_reference("addresses-rental", tmp_path / "reports") is None
