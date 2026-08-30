"""Unit tests for scripts/quote_compare.py: the multi-insurer orchestrator
(spec 005-insurance-quote-comparison, User Story 4, T035-T039).

`WALK_REGISTRY` is monkeypatched to fixture `Errand` subclasses whose
`run()` is stubbed - never a real `Session`/`Config`/vault construction,
matching plan.md's own documented convention for orchestrator testing
("fixture Errand subclasses whose run() is stubbed to return a fixed exit
code, never a real Errand.run() call").
"""

from __future__ import annotations

import json

import pytest

import scripts.quote_compare as quote_compare
from headless.capture import CurrentPolicy, QuoteCapture, write_capture
from headless.policydoc import PolicyReference, write_policy_reference
from headless.errand import Errand


class _CountingFakeVault:
    def __init__(self, secrets: dict[str, str]) -> None:
        self._secrets = secrets

    def get_secret(self, name: str) -> str:
        return self._secrets[name]

    def put_secret(self, name, value):
        raise AssertionError("quote_compare.py must never write to the vault")

    def delete_secret(self, name):
        raise AssertionError("quote_compare.py must never write to the vault")

    def self_test(self) -> bool:
        return True


def _profile_doc(companies, vehicles_primary_overrides: dict | None = None) -> dict:
    vehicle = {
        "type": "primary",
        "vin": "1SAMPLE0VIN000001",
        "currently_insured": "yes",
        "policy_doc": "/tmp/example-auto-policy.pdf",
    }
    if vehicles_primary_overrides:
        vehicle.update(vehicles_primary_overrides)
    return {
        "identities": [{"type": "self", "first_name": "Test"}],
        "addresses": [{"type": "home", "zip": "48000"}],
        "vehicles": [vehicle],
        "feature_configs": {"insurance": {"companies": companies}},
    }


def _make_fixture_errand(name: str, return_code: int = 0):
    calls: list[list[str]] = []

    class _Fixture(Errand):
        HANDOFF = "handoff"
        dependencies: list[str] = []

        def __init__(self) -> None:
            pass

        def run(self, argv=None) -> int:
            calls.append(list(argv or []))
            return return_code

    _Fixture.name = name
    _Fixture.calls = calls
    return _Fixture


@pytest.fixture(autouse=True)
def preview_dir_env(monkeypatch, tmp_path):
    # reports_dir_for(config) derives from config.preview_dir's own sibling
    # (research.md D4); point it at this test's own tmp tree so nothing
    # touches the real repository's reports/ directory.
    monkeypatch.setenv("HEADLESS_PREVIEW_DIR", str(tmp_path / "previews"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    return tmp_path


def _wire_vault(monkeypatch, profile_doc: dict) -> _CountingFakeVault:
    fake_vault = _CountingFakeVault({"profile": json.dumps(profile_doc)})
    monkeypatch.setattr(quote_compare, "open_vault", lambda config: fake_vault)
    return fake_vault


# --- T035: unmapped insurer --------------------------------------------


@pytest.mark.parametrize("mode_flags", [[], ["--check"], ["--apply"]], ids=["preview", "check", "apply"])
def test_unmapped_insurer_produces_a_not_mapped_yet_line_and_zero_construction(monkeypatch, mode_flags, capsys):
    progressive_cls = _make_fixture_errand("progressive")
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"progressive": progressive_cls})
    _wire_vault(monkeypatch, _profile_doc(["progressive", "geico"]))

    exit_code = quote_compare.main(mode_flags)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "not mapped yet: geico" in out
    # geico has no fixture registered at all - the only way to "construct"
    # it would be a KeyError, which would have failed this test outright.
    assert "geico" not in quote_compare.WALK_REGISTRY


# --- T036: malformed input refuses before any insurer's Errand is built ----


@pytest.mark.parametrize("mode_flags", [[], ["--check"], ["--apply"]], ids=["preview", "check", "apply"])
def test_missing_feature_configs_refuses_before_any_session(monkeypatch, mode_flags, capsys):
    progressive_cls = _make_fixture_errand("progressive")
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"progressive": progressive_cls})
    doc = {"identities": [], "addresses": [], "vehicles": []}  # no feature_configs at all
    _wire_vault(monkeypatch, doc)

    exit_code = quote_compare.main(mode_flags)

    assert exit_code == 1
    assert progressive_cls.calls == []
    out = capsys.readouterr().out
    assert "REFUSED" in out


def test_malformed_companies_not_an_array_refuses(monkeypatch):
    progressive_cls = _make_fixture_errand("progressive")
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"progressive": progressive_cls})
    doc = _profile_doc("progressive")  # a string, not an array
    _wire_vault(monkeypatch, doc)

    exit_code = quote_compare.main([])

    assert exit_code == 1
    assert progressive_cls.calls == []


def test_missing_or_unparseable_policy_cache_does_not_refuse(monkeypatch, tmp_path):
    progressive_cls = _make_fixture_errand("progressive", return_code=0)
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"progressive": progressive_cls})
    _wire_vault(monkeypatch, _profile_doc(["progressive"]))

    exit_code = quote_compare.main(["--apply"])

    assert exit_code == 0
    report_files = list((tmp_path / "reports").glob("quote-comparison-*.html"))
    assert len(report_files) == 1
    assert "no current-policy reference for vehicles.primary" in report_files[0].read_text(encoding="utf-8")


# --- T036b: excluded-asset ---------------------------------------------


@pytest.mark.parametrize("mode_flags", [[], ["--check"], ["--apply"]], ids=["preview", "check", "apply"])
def test_excluded_asset_zero_insurer_construction_and_one_line(monkeypatch, mode_flags, capsys):
    progressive_cls = _make_fixture_errand("progressive")
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"progressive": progressive_cls})
    doc = _profile_doc(["progressive"], vehicles_primary_overrides={"currently_insured": "n/a"})
    _wire_vault(monkeypatch, doc)

    exit_code = quote_compare.main(mode_flags)

    assert exit_code == 0
    assert progressive_cls.calls == []
    out = capsys.readouterr().out
    assert "vehicles.primary excluded by profile (n/a)" in out


def test_excluded_asset_apply_mode_writes_a_report_stating_the_exclusion(monkeypatch, tmp_path):
    progressive_cls = _make_fixture_errand("progressive")
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"progressive": progressive_cls})
    doc = _profile_doc(["progressive"], vehicles_primary_overrides={"policy_doc": "n/a"})
    _wire_vault(monkeypatch, doc)

    exit_code = quote_compare.main(["--apply"])

    assert exit_code == 0
    report_files = list((tmp_path / "reports").glob("quote-comparison-*.html"))
    assert len(report_files) == 1
    content = report_files[0].read_text(encoding="utf-8")
    assert "excluded by profile (n/a)" in content
    assert "<table>" not in content


def test_excluded_asset_preview_mode_writes_no_report(monkeypatch, tmp_path):
    progressive_cls = _make_fixture_errand("progressive")
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"progressive": progressive_cls})
    doc = _profile_doc(["progressive"], vehicles_primary_overrides={"currently_insured": "n/a"})
    _wire_vault(monkeypatch, doc)

    quote_compare.main([])

    reports_dir = tmp_path / "reports"
    assert not reports_dir.exists() or not list(reports_dir.glob("quote-comparison-*.html"))


# --- T037: per-insurer isolation -----------------------------------------


def test_one_insurer_failure_does_not_stop_the_second_or_the_report(monkeypatch, tmp_path):
    failing_cls = _make_fixture_errand("failing", return_code=1)
    succeeding_cls = _make_fixture_errand("succeeding", return_code=0)
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"failing": failing_cls, "succeeding": succeeding_cls})
    _wire_vault(monkeypatch, _profile_doc(["failing", "succeeding"]))

    reports_dir = tmp_path / "reports"
    write_capture(
        QuoteCapture(
            insurer="succeeding",
            fetched_at="2026-08-26T12:00:00+00:00",
            premium={"term_months": "6", "amount": "500.00"},
            coverages=[],
            source_url="https://example.com",
        ),
        reports_dir,
    )

    exit_code = quote_compare.main(["--apply"])

    assert exit_code == 0
    assert failing_cls.calls == [["--apply"]]
    assert succeeding_cls.calls == [["--apply"]]  # still ran despite failing's own failure
    report_files = list(reports_dir.glob("quote-comparison-*.html"))
    assert len(report_files) == 1
    content = report_files[0].read_text(encoding="utf-8")
    assert "failing" in content
    assert "no successful capture yet" in content


# --- T038: freshest-capture-wins -----------------------------------------


def test_a_prior_capture_is_used_when_this_runs_own_attempt_fails(monkeypatch, tmp_path):
    fixture_cls = _make_fixture_errand("progressive", return_code=1)  # this run's attempt fails
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"progressive": fixture_cls})
    _wire_vault(monkeypatch, _profile_doc(["progressive"]))

    reports_dir = tmp_path / "reports"
    write_capture(
        QuoteCapture(
            insurer="progressive",
            fetched_at="2026-08-20T08:00:00+00:00",
            premium={"term_months": "6", "amount": "480.00"},
            coverages=[],
            source_url="https://example.com/old-quote",
        ),
        reports_dir,
    )

    exit_code = quote_compare.main(["--apply"])

    assert exit_code == 0
    report_files = list(reports_dir.glob("quote-comparison-*.html"))
    content = report_files[0].read_text(encoding="utf-8")
    assert "2026-08-20T08:00:00+00:00" in content
    assert "no successful capture yet" not in content


# --- IMPORTANT 5 (Opus verifier, 2026-08-29): the provenance 4-tuple wiring
# through this orchestrator (lines ~222-231, `read_policy_reference_
# provenance`'s own 2-tuple -> 4-tuple change, spec 006-policy-extraction-v2
# FR-023/FR-024) had zero test coverage in this file - verified correct by
# manual live testing during that delivery, but unguarded against a future
# regression (the same "004 regression class" a frozen-dataclass field
# addition already burned this repository once, MEMORY.md).


def test_confirmed_policy_reference_provenance_reaches_the_report_footer(monkeypatch, tmp_path):
    progressive_cls = _make_fixture_errand("progressive", return_code=0)
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"progressive": progressive_cls})
    _wire_vault(monkeypatch, _profile_doc(["progressive"]))

    reports_dir = tmp_path / "reports"
    write_policy_reference(
        PolicyReference(
            policy=CurrentPolicy(
                insurer="Sample Assurance Mutual",
                premium={"term_months": "12", "amount": "1200.00"},
                coverages=[{"line": "medical_payments", "limit": "5,000", "deductible": "", "premium": ""}],
            ),
            asset_key="vehicles-primary",
            source_path="/tmp/example-declarations.pdf",
            confirmed_at="2026-08-29T00:00:00+00:00",
            generator="local-llm:qwen3.5:35b",
            converter="pymupdf4llm",
        ),
        reports_dir,
    )

    exit_code = quote_compare.main(["--apply"])

    assert exit_code == 0
    report_files = list(reports_dir.glob("quote-comparison-*.html"))
    assert len(report_files) == 1
    content = report_files[0].read_text(encoding="utf-8")
    assert "local-llm:qwen3.5:35b" in content
    assert "pymupdf4llm" in content


# --- T039: flag forwarding -----------------------------------------------


def test_flags_are_forwarded_unchanged_to_each_mapped_insurers_run(monkeypatch, tmp_path):
    fixture_cls = _make_fixture_errand("progressive")
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"progressive": fixture_cls})
    _wire_vault(monkeypatch, _profile_doc(["progressive"]))

    custom_profile_dir = str(tmp_path / "custom-profile")
    custom_preview_dir = str(tmp_path / "custom-previews")
    quote_compare.main(
        ["--profile-dir", custom_profile_dir, "--show", "--preview-dir", custom_preview_dir, "--no-screenshot"]
    )

    assert fixture_cls.calls == [
        ["--profile-dir", custom_profile_dir, "--show", "--preview-dir", custom_preview_dir, "--no-screenshot"]
    ]


def test_check_flag_is_forwarded(monkeypatch, tmp_path):
    fixture_cls = _make_fixture_errand("progressive")
    monkeypatch.setattr(quote_compare, "WALK_REGISTRY", {"progressive": fixture_cls})
    _wire_vault(monkeypatch, _profile_doc(["progressive"]))

    quote_compare.main(["--check"])

    assert fixture_cls.calls == [["--check"]]


# --- misc: profile itself invalid JSON --------------------------------------


def test_profile_not_valid_json_refuses(monkeypatch, capsys):
    monkeypatch.setattr(quote_compare, "open_vault", lambda config: _CountingFakeVault({"profile": "{not valid"}))
    exit_code = quote_compare.main([])
    assert exit_code == 1
    # NIT 7 (Opus verifier, 2026-08-26): the raised exception is profile's
    # own existing ProfileError (spec 001), not a new class - proven by
    # its own message shape ("vault item 'profile' is not valid JSON").
    out = capsys.readouterr().out
    assert "REFUSED: vault item 'profile' is not valid JSON" in out


def test_profile_not_a_json_object_refuses_via_profile_error(monkeypatch, capsys):
    monkeypatch.setattr(quote_compare, "open_vault", lambda config: _CountingFakeVault({"profile": "[]"}))
    exit_code = quote_compare.main([])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "REFUSED: vault item 'profile' must be a JSON object" in out
